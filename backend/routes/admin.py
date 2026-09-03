"""Admin uçları — soft-delete edilen kayıtların listesi/geri alma + özellik ayarları.

Silinen kayıtları görebilen TEK yol burasıdır; tüm kullanıcı-yüzü sorgular
(case_manager, auth_helpers) deleted_at IS NULL filtreler. require_admin
routes/config.py'deki ADMIN_EMAILS tabanlı kontroldür.

Özellik ayarları (`/api/admin/settings`): services/app_settings.py registry'sindeki
aç/kapa anahtarları — yönetim paneli "Özellikler" sekmesi buradan okur/yazar.

Veri teslim defteri (`/api/admin/aktarim/*`, G108): veri ekibinin teslim
paketleri için "yedek giriş yolu" + gündüz işlemleri — defteri oku, xlsx yükle,
kuru koş, raporları indir, bilinçli onayla uygula, taramayı tetikle. Durum
makinesi `services/teslim_kutusu.py`'de; buradaki uçlar yalnız çağırır. İstek
başına TEK oturum açılır ve servis fonksiyonlarına `db=` ile verilir (test
yalnız bu modülün `SessionLocal`'ını değiştirir). Sözleşme gorevler/gorev/G108.md
"SÖZLEŞME" tablosunda dondurulmuştur (G111 paneli buna göre yazıldı).
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_

from auth_helpers import tenant_filter_clause
from database import SessionLocal
from dependencies import get_current_tenant
from routes.config import require_admin
from schemas import AktarimTeslimiOut, AktarimTeslimiOzetOut, AppSettingUpdate, TeslimUygulaRequest
from services import app_settings
from services import teslim_kutusu as tk
import models

router = APIRouter()
logger = logging.getLogger(__name__)

#: Yükleme ucunun kabul ettiği en büyük teslim paketi (bayt) — sözleşme: 50 MB.
TESLIM_YUKLEME_SINIRI = 50 * 1024 * 1024
#: Rapor indirme ucunun servis ettiği uzantılar → içerik türü.
_RAPOR_TURLERI = {".csv": "text/csv; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


def _admin_email(user: dict) -> str:
    return str(user.get("preferred_username") or user.get("upn") or user.get("email") or "")


# ─── ÖZELLİK AYARLARI ────────────────────────────────────────────────────────

@router.get("/api/admin/settings")
def api_get_app_settings(user: dict = Depends(require_admin)):
    """Bilinen tüm aç/kapa ayarları + etkin değerleri (satır yoksa varsayılan)."""
    return {"settings": app_settings.list_settings()}


@router.put("/api/admin/settings/{key}")
def api_update_app_setting(
    key: str,
    payload: AppSettingUpdate,
    user: dict = Depends(require_admin),
):
    """Ayarı açar/kapatır. Yalnız registry'deki anahtarlar kabul edilir."""
    if key not in app_settings.SETTINGS_REGISTRY:
        raise HTTPException(status_code=404, detail="Bilinmeyen ayar")
    email = user.get("preferred_username") or user.get("upn") or user.get("email")
    try:
        app_settings.set_setting_bool(key, payload.value, updated_by=email)
    except Exception as e:
        logger.error(f"Ayar yazılamadı ({key}={payload.value}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ayar kaydedilemedi. Lütfen tekrar deneyin.") from e
    logger.info(f"[ADMIN-SETTING] {key} = {payload.value} (by={email})")
    return {"status": "success", "key": key, "value": payload.value}


# ─── VERİ TESLİM DEFTERİ (G108) ──────────────────────────────────────────────

def _teslim_veya_404(db, teslim_id: int) -> models.AktarimTeslimi:
    teslim = db.get(models.AktarimTeslimi, teslim_id)
    if teslim is None:
        raise HTTPException(status_code=404, detail="Teslim bulunamadı")
    return teslim


def _rapor_dizini(teslim: models.AktarimTeslimi) -> Optional[Path]:
    """Teslimin rapor klasörü (varsa ve gerçekten dizinse)."""
    if not teslim.rapor_dizini:
        return None
    dizin = Path(str(teslim.rapor_dizini))
    return dizin if dizin.is_dir() else None


def _rapor_dosyalari(dizin: Optional[Path]) -> list:
    if dizin is None:
        return []
    return sorted(
        (p for p in dizin.iterdir() if p.is_file() and p.suffix.lower() in _RAPOR_TURLERI),
        key=lambda p: p.name,
    )


@router.get("/api/admin/aktarim/teslimler")
def api_teslimler(
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_admin),
):
    """Defter (en yeni önce) + kapı eşikleri + otomasyon anahtarı."""
    db = SessionLocal()
    try:
        satirlar = (
            db.query(models.AktarimTeslimi)
            .order_by(models.AktarimTeslimi.created_at.desc(), models.AktarimTeslimi.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "teslimler": [AktarimTeslimiOzetOut.model_validate(t) for t in satirlar],
            "esikler": tk.kapi_esikleri(),
            "etkin": app_settings.veri_teslim_otomasyonu_etkin(db=db),
        }
    finally:
        db.close()


@router.get("/api/admin/aktarim/teslimler/{teslim_id}")
def api_teslim(teslim_id: int, user: dict = Depends(require_admin)):
    """Tek teslim, `durum_gecmisi` ve `spool_path` dahil."""
    db = SessionLocal()
    try:
        return AktarimTeslimiOut.model_validate(_teslim_veya_404(db, teslim_id))
    finally:
        db.close()


def _dosyayi_oku(file: UploadFile) -> bytes:
    """Yükleme gövdesini sınıra kadar okur; sınırı aşarsa 413 (belleğe tamamı alınmaz).

    Senkron okuma bilinçli: uç `def`tir (threadpool'da koşar) — ardındaki kuru
    koşu saniyeler sürer, event loop'u tutmamalı.
    """
    parcalar: list = []
    toplam = 0
    while True:
        parca = file.file.read(1024 * 1024)
        if not parca:
            break
        toplam += len(parca)
        if toplam > TESLIM_YUKLEME_SINIRI:
            raise HTTPException(
                status_code=413,
                detail=f"Dosya {TESLIM_YUKLEME_SINIRI // (1024 * 1024)} MB sınırını aşıyor",
            )
        parcalar.append(parca)
    return b"".join(parcalar)


@router.post("/api/admin/aktarim/teslimler", status_code=201)
def api_teslim_yukle(
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
):
    """Elle yükleme (yedek giriş yolu): deftere kaydet + doğrula + kuru koş + kapı.

    Otomasyon anahtarından BAĞIMSIZ çalışır. Otomatik uygulama YAPILMAZ — kapı
    "otomatik" dese bile satır `kuru_kosuldu`da kalır, yönetici "Uygula" der.
    Aynı içerik ikinci kez → 201 + `durum="yinelenen"` (defter izi).
    """
    dosya_adi = (file.filename or "").strip()
    if not dosya_adi.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Yalnız .xlsx teslim paketi kabul edilir")
    icerik = _dosyayi_oku(file)
    if not icerik:
        raise HTTPException(status_code=400, detail="Dosya boş")

    db = SessionLocal()
    try:
        teslim_id = tk.teslim_kaydet(icerik=icerik, dosya_adi=dosya_adi, kaynak="yukleme", db=db)
        durum = tk.teslimi_isle(teslim_id, otomatik_uygula=False, db=db)
    except Exception as e:
        db.rollback()
        logger.error(f"Teslim yüklemesi başarısız ({dosya_adi}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Teslim kaydedilemedi. Lütfen tekrar deneyin.") from e
    finally:
        db.close()
    logger.info(f"[ADMIN-TESLIM] #{teslim_id} yüklendi: {dosya_adi} → {durum} (by={_admin_email(user)})")
    return {"id": teslim_id, "durum": durum}


@router.post("/api/admin/aktarim/teslimler/{teslim_id}/kuru-kos")
def api_teslim_kuru_kos(teslim_id: int, user: dict = Depends(require_admin)):
    """Yeniden doğrula + kuru koş + kapı (`teslimi_isle`, uygulama YOK).

    Yalnız işlenebilir durumlarda (`alindi`/`dogrulandi`/`kuru_kosuldu`/
    `inceleme_bekliyor`); nihai ya da `uygulaniyor` satırda 409.
    """
    db = SessionLocal()
    try:
        teslim = _teslim_veya_404(db, teslim_id)
        if teslim.durum not in tk.ISLENEBILIR_DURUMLAR:
            raise HTTPException(
                status_code=409,
                detail=f"'{teslim.durum}' durumundaki teslim kuru koşulamaz",
            )
        try:
            durum = tk.teslimi_isle(teslim_id, otomatik_uygula=False, db=db)
        except ValueError as e:                        # yarış: durum bu arada değişti
            db.rollback()
            raise HTTPException(status_code=409, detail=str(e)) from e
        except Exception as e:
            db.rollback()
            logger.error(f"Teslim #{teslim_id} kuru koşu başarısız: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Kuru koşu başarısız. Lütfen tekrar deneyin.") from e
        db.expire_all()
        teslim = _teslim_veya_404(db, teslim_id)
        logger.info(f"[ADMIN-TESLIM] #{teslim_id} kuru koşu → {durum} (by={_admin_email(user)})")
        return {
            "id": teslim_id,
            "durum": durum,
            "kapi_karari": teslim.kapi_karari,
            "kapi_gerekcesi": teslim.kapi_gerekcesi,
        }
    finally:
        db.close()


@router.post("/api/admin/aktarim/teslimler/{teslim_id}/uygula")
def api_teslim_uygula(
    teslim_id: int,
    payload: TeslimUygulaRequest,
    user: dict = Depends(require_admin),
):
    """Gerçek yazım — bilinçli onay (`{"onay": true}`) şart; anahtardan bağımsız.

    Yalnız `kuru_kosuldu` / `inceleme_bekliyor` satırda; diğerinde 409.
    `uygulayan` = yöneticinin e-postası.
    """
    if not payload.onay:
        raise HTTPException(status_code=400, detail="Uygulama için açık onay (onay=true) gerekir")
    email = _admin_email(user)
    if not email:
        raise HTTPException(status_code=403, detail="Yönetici kimliği çözülemedi")
    db = SessionLocal()
    try:
        teslim = _teslim_veya_404(db, teslim_id)
        if teslim.durum not in (tk.DURUM_KURU_KOSULDU, tk.DURUM_INCELEME):
            raise HTTPException(
                status_code=409,
                detail=f"'{teslim.durum}' durumundaki teslim uygulanamaz",
            )
        try:
            durum = tk.teslim_uygula(teslim_id, uygulayan=email, db=db)
        except ValueError as e:                        # yarış: durum bu arada değişti
            db.rollback()
            raise HTTPException(status_code=409, detail=str(e)) from e
        except Exception as e:
            db.rollback()
            logger.error(f"Teslim #{teslim_id} uygulama ucu başarısız: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Uygulama başarısız. Lütfen tekrar deneyin.") from e
        logger.info(f"[ADMIN-TESLIM] #{teslim_id} uygula → {durum} (by={email})")
        return {"id": teslim_id, "durum": durum}
    finally:
        db.close()


@router.get("/api/admin/aktarim/teslimler/{teslim_id}/raporlar")
def api_teslim_raporlar(teslim_id: int, user: dict = Depends(require_admin)):
    """Rapor klasöründeki CSV/TXT dosyaları (ad + boyut); klasör yoksa boş liste."""
    db = SessionLocal()
    try:
        teslim = _teslim_veya_404(db, teslim_id)
        dosyalar = _rapor_dosyalari(_rapor_dizini(teslim))
    finally:
        db.close()
    return {"dosyalar": [{"ad": p.name, "boyut": p.stat().st_size} for p in dosyalar]}


@router.get("/api/admin/aktarim/teslimler/{teslim_id}/raporlar/{ad:path}")
def api_teslim_rapor_indir(teslim_id: int, ad: str, user: dict = Depends(require_admin)):
    """Tek rapor dosyasını indirir. Yol bileşeni (`..`, `/`, `\\`) 400; listede olmayan ad 404.

    `{ad:path}` bilinçli: `..%2F` çözümlenince tek segment kalıbına uymayıp
    404'e düşerdi — burada yakalanıp 400 ile açıkça reddedilir.
    """
    if (
        not ad
        or ad != Path(ad).name
        or ".." in ad
        or "/" in ad
        or "\\" in ad
        or ad.startswith(".")
    ):
        raise HTTPException(status_code=400, detail="Geçersiz rapor adı")
    db = SessionLocal()
    try:
        teslim = _teslim_veya_404(db, teslim_id)
        dizin = _rapor_dizini(teslim)
    finally:
        db.close()
    if dizin is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    dosya = dizin / ad
    kok = dizin.resolve()
    if (
        dosya.suffix.lower() not in _RAPOR_TURLERI
        or not dosya.is_file()
        or kok not in dosya.resolve().parents
    ):
        raise HTTPException(status_code=404, detail="Rapor bulunamadı")
    return FileResponse(path=str(dosya), media_type=_RAPOR_TURLERI[dosya.suffix.lower()], filename=ad)


@router.post("/api/admin/aktarim/tara")
def api_teslim_tara(user: dict = Depends(require_admin)):
    """SharePoint teslim klasörünü tara + yeni alınanları kuru koşuya sok (G116).

    Anahtar kapalıyken hiçbir şey yapmaz ve bunu `not` ile söyler
    (`sharepoint_tara` ÇAĞRILMAZ). Açıkken `teslim_kutusu.sharepoint_tara()`
    sayaçlarını (`yeni`/`yinelenen`/`atlanan`, `not` YOK) döner; ardından bu
    çağrıda `alindi`ya düşen her teslim `created_at` sırasıyla
    `teslimi_isle(otomatik_uygula=False)` ile kuru koşuya girer (gündüz kuralı:
    uygulama yalnız gece turunda ya da admin "Uygula" ile) ve sonuç `islenen`
    listesine `{"id", "durum"}` olarak eklenir. Uç senkrondur (kuru koşu tam
    pakette ~45 sn; konteyner nginx 300 sn).

    Hata: `sharepoint_tara` istisnası (Graph/klasör) → 502 + `detail`, log
    WARNING (deneme düzeyi — ERROR yok). Tek teslimin işleme istisnası tarama
    sonucunu düşürmez: `islenen`e `{"id", "durum": "hata", "mesaj"}` girer, WARNING.
    """
    db = SessionLocal()
    try:
        if not app_settings.veri_teslim_otomasyonu_etkin(db=db):
            return {"yeni": 0, "yinelenen": 0, "not": "Veri teslim otomasyonu kapalı — tarama yapılmadı"}
        # Bu çağrıda alınanları ayırt etmek için tarama öncesi en büyük defter id'si
        son = db.query(models.AktarimTeslimi.id).order_by(models.AktarimTeslimi.id.desc()).first()
        onceki_son_id = int(son[0]) if son else 0
        try:
            sayac = tk.sharepoint_tara(db=db)
        except Exception as exc:
            db.rollback()
            logger.warning("SharePoint teslim taraması başarısız (%s): %s", type(exc).__name__, exc)
            raise HTTPException(
                status_code=502, detail=f"SharePoint taraması başarısız: {str(exc)[:200]}",
            ) from exc
        yeni_idler = [
            int(tid)
            for (tid,) in (
                db.query(models.AktarimTeslimi.id)
                .filter(models.AktarimTeslimi.id > onceki_son_id)
                .filter(models.AktarimTeslimi.durum == tk.DURUM_ALINDI)
                .order_by(models.AktarimTeslimi.created_at, models.AktarimTeslimi.id)
                .all()
            )
        ]
        islenen = []
        for teslim_id in yeni_idler:
            try:
                durum = tk.teslimi_isle(teslim_id, otomatik_uygula=False, db=db)
                islenen.append({"id": teslim_id, "durum": durum})
            except Exception as exc:
                db.rollback()
                logger.warning("Teslim #%s tarama sonrası işlenemedi (%s): %s", teslim_id, type(exc).__name__, exc)
                islenen.append({"id": teslim_id, "durum": "hata", "mesaj": str(exc)[:200]})
        return {
            "yeni": sayac["yeni"], "yinelenen": sayac["yinelenen"], "atlanan": sayac["atlanan"],
            "islenen": islenen,
        }
    finally:
        db.close()


@router.get("/api/admin/deleted-records")
def api_deleted_records(
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft-delete edilmiş dava + müvekkil + belge kayıtları (en yeni silinen önce)."""
    db = SessionLocal()
    try:
        cases = (
            db.query(models.Case)
            .filter(models.Case.deleted_at.isnot(None))
            .filter(tenant_filter_clause(models.Case, tenant_id))
            .order_by(models.Case.deleted_at.desc())
            .all()
        )
        clients = (
            db.query(models.Client)
            .filter(models.Client.deleted_at.isnot(None))
            .filter(tenant_filter_clause(models.Client, tenant_id))
            .order_by(models.Client.deleted_at.desc())
            .all()
        )
        # Belgede tenant davadan gelir (CaseDocument'ta tenant_id yok);
        # UNLINKED (case_id NULL) belgeler de listelenir — auth_helpers ile aynı kalıp.
        documents = (
            db.query(models.CaseDocument)
            .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
            .filter(models.CaseDocument.deleted_at.isnot(None))
            .filter(or_(
                models.Case.tenant_id == tenant_id,
                models.Case.tenant_id.is_(None),
                models.CaseDocument.case_id.is_(None),
            ))
            .order_by(models.CaseDocument.deleted_at.desc())
            .all()
        )
        return {
            "cases": [
                {
                    "id": c.id,
                    "tracking_no": c.tracking_no,
                    "esas_no": c.esas_no,
                    "court": c.court,
                    "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
                    "deleted_by": c.deleted_by,
                    "delete_reason": c.delete_reason,
                }
                for c in cases
            ],
            "clients": [
                {
                    "id": c.id,
                    "name": c.name,
                    "cari_kod": c.cari_kod,
                    "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
                    "deleted_by": c.deleted_by,
                    "delete_reason": c.delete_reason,
                }
                for c in clients
            ],
            "documents": [
                {
                    "id": d.id,
                    "stored_filename": d.stored_filename,
                    "belge_turu_adi": d.belge_turu_adi,
                    "case_id": d.case_id,
                    "case_tracking_no": d.case.tracking_no if d.case else None,
                    "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
                    "deleted_by": d.deleted_by,
                    "delete_reason": d.delete_reason,
                }
                for d in documents
            ],
        }
    finally:
        db.close()


@router.post("/api/admin/restore/{record_type}/{record_id}")
def api_restore_record(
    record_type: str,
    record_id: int,
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft-delete edilmiş kaydı geri alır.

    Dava: deleted_* temizlenir + active=True (silmede False yazılmıştı).
    Müvekkil: yalnız deleted_* temizlenir — active'e DOKUNULMAZ (silme öncesi
    pasiflik durumu korunur; active kullanıcı-düzenlenebilir bir alan).
    Belge: yalnız deleted_* temizlenir (başka durum alanı yok).
    Restore'da benzersizlik çakışması olamaz: tracking_no/sistem_no unique
    kısıtları silinen kayıtları da kapsıyordu.
    """
    if record_type not in ("case", "client", "document"):
        raise HTTPException(status_code=400, detail="record_type 'case', 'client' veya 'document' olmalı")

    db = SessionLocal()
    try:
        if record_type == "case":
            row = (
                db.query(models.Case)
                .filter(models.Case.id == record_id)
                .filter(models.Case.deleted_at.isnot(None))
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .first()
            )
        elif record_type == "document":
            row = (
                db.query(models.CaseDocument)
                .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
                .filter(models.CaseDocument.id == record_id)
                .filter(models.CaseDocument.deleted_at.isnot(None))
                .filter(or_(
                    models.Case.tenant_id == tenant_id,
                    models.Case.tenant_id.is_(None),
                    models.CaseDocument.case_id.is_(None),
                ))
                .first()
            )
        else:
            row = (
                db.query(models.Client)
                .filter(models.Client.id == record_id)
                .filter(models.Client.deleted_at.isnot(None))
                .filter(tenant_filter_clause(models.Client, tenant_id))
                .first()
            )
        if not row:
            raise HTTPException(status_code=404, detail="Silinmiş kayıt bulunamadı")

        row.deleted_at = None
        row.deleted_by = None
        row.delete_reason = None
        if isinstance(row, models.Case):
            row.active = True
        db.commit()
        logger.info(
            f"[ADMIN-RESTORE] {record_type} id={record_id} geri alındı "
            f"(by={user.get('preferred_username') or user.get('upn') or user.get('email')})"
        )
        return {"status": "success", "message": "Kayıt geri alındı"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Restore hatası ({record_type}/{record_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Geri alma başarısız. Lütfen tekrar deneyin.") from e
    finally:
        db.close()
