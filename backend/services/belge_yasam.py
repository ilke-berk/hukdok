"""Word yaşam döngüsü iş mantığı (G284, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §6.2 K12-K15, §6.3, §6.5).

Beş adım, HTTP bilmez (route `routes/belge_yasam.py` hataları koda çevirir):

- `yeni_belge`: `sablonlar/bos.docx` kopyası `03_TASLAKLAR/<ofis_no>/<ad>.docx` olarak SENKRON yüklenir (kullanıcı
  Word'ü hemen açacak); ad çakışmasında `get_file_meta_from_sharepoint` ile bakılır (küçük dosya yüklemesi aynı adı
  sormadan EZER — CLAUDE.md "arşivde ad çakışması"), varsa `-2`, `-3` … (en çok `AD_DENEME_SINIRI`, sonra 409);
  kayıt `save_case_document(yon=GIDEN, kaynak=WORD, durum=TASLAK)` + `sharepoint_url`/`word_url` = Graph `webUrl`.
- `surum_kaydet`: taslak `.docx` indirilir → sha256 → `belge_surumleri` yeni satır (`surum_no = max+1`, `kesin=False`);
  `degisti` = sha önceki satırdan farklı mı. SharePoint'in otomatik kayıtları DEĞİL, yalnız bilinçli kayıt (K13).
- `surumler`: `surum_no` artan liste.
- `kesinlestir` (K14): taslak `.docx` indirilir → `pdf_converter.convert_to_pdfa2b(bütçe)` → AYNI satır KESIN
  (`kesinlesme_tarihi`, `kesinlestiren_email`, `stored_filename=<ad>.pdf`, `sharepoint_url=None` → URL commit'i
  `upload_queue`'da: bildirim + Hukukbot allowlist o anda, G282 kapısı artık geçirir) → iki kuyruk: `islenmis` PDF/A +
  `ham` `.docx`; son sürüm satırı `kesin=True`. `convert_pdfa_and_queue_uploads` KULLANILMAZ (yeni satır açardı).
  Taslak `.docx` `03_TASLAKLAR`'da KALIR. İdempotent: `confirm_idempotency` anahtarı `kesinlestir:<uuid>`.
- `yeni_surum_taslagi`: KESIN belgeden yeni TASLAK (`<ad>-v{n}.docx`, `onceki_document_id`), aynı kuralla idempotent
  (`yeni-surum:<uuid>`). Kaynak `.docx` taslak klasöründeki kopyadır (ham arşivdekiyle aynı bayt; tarih önekli ham adı
  kayıtta tutulmaz).

SharePoint/Graph çağrıları bu modülün `_sharepoint_*` sarmalayıcılarından geçer (testte monkeypatch). Log sözleşmesi:
deneme/4xx WARNING, nihai 5xx TEK ERROR (route `_hata`).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.settings import settings
from database import SessionLocal
from file_utils import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, sanitize_filename
import models
from services import confirm_idempotency, document_pipeline, upload_queue

SABLON_DIZINI = Path(__file__).resolve().parent.parent / "sablonlar"
SABLONLAR: dict[str, str] = {"bos": "bos.docx"}
DOCX_UZANTI = ".docx"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
AD_DENEME_SINIRI = 20
BELGE_KAYNAGI = "WORD"
KESINLESTIR_ONEKI = "kesinlestir:"
YENI_SURUM_ONEKI = "yeni-surum:"


class BelgeYasamHatasi(Exception):
    """Route'un HTTP'ye çevirdiği hata: `status`, kullanıcı `mesaj`ı, `error_kod`."""

    def __init__(self, status: int, mesaj: str, error_kod: str):
        super().__init__(mesaj)
        self.status = status
        self.mesaj = mesaj
        self.error_kod = error_kod


# ── SharePoint sarmalayıcıları (testte sahte) ─────────────────────────────────

def _sharepoint_yukle(yol: str, ad: str, klasor: str) -> dict:
    from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint

    return upload_file_to_sharepoint(yol, ad, klasor, content_type=DOCX_MIME, use_date_subfolder=False) or {}


def _sharepoint_indir(klasor: str, ad: str) -> tuple[bytes, str]:
    from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint

    return download_file_from_sharepoint(klasor, ad)


def _sharepoint_meta(klasor: str, ad: str) -> Optional[dict]:
    from sharepoint.sharepoint_uploader_graph import get_file_meta_from_sharepoint

    return get_file_meta_from_sharepoint(klasor, ad)


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def klasor_adi(ofis_no: Optional[str], case_id: int) -> str:
    """Taslak alt klasörü: ofis no'daki yol ayraçları ve yasak karakterler `-` (ayrıştırma YOK, karar 023); boşsa `kart-<id>`."""
    temiz = re.sub(r'[\\/:*?"<>|#%]', "-", (ofis_no or "").strip()).strip(" .")
    return temiz or f"kart-{case_id}"


def taslak_klasoru(ofis_no: Optional[str], case_id: int) -> str:
    return f"{settings.sharepoint_folder_taslak_name}/{klasor_adi(ofis_no, case_id)}"


def docx_adi(ad: str) -> str:
    """`sanitize_filename` + `.docx` zorunlu; gövde boşsa 422 (ad UYDURULMAZ)."""
    ham = os.path.basename((ad or "").strip().replace("\\", "/"))
    govde = ham[: -len(DOCX_UZANTI)] if ham.lower().endswith(DOCX_UZANTI) else ham
    if govde.lower().endswith(".doc"):
        govde = govde[:-4]
    govde = govde.strip(" .")
    if not govde.strip("_-"):
        raise BelgeYasamHatasi(422, "Belge adı boş ya da geçersiz.", "belge_adi")
    try:
        temiz = sanitize_filename(f"{govde}{DOCX_UZANTI}")
    except Exception as e:  # sanitize HTTPException fırlatır (file_utils) — burada HTTP bilinmez
        raise BelgeYasamHatasi(422, f"Belge adı geçersiz: {getattr(e, 'detail', e)}", "belge_adi") from None
    if not temiz or not Path(temiz).stem.strip(" ._-") or not temiz.lower().endswith(DOCX_UZANTI):
        raise BelgeYasamHatasi(422, "Belge adı boş ya da geçersiz.", "belge_adi")
    return temiz


def benzersiz_ad(klasor: str, ad: str) -> str:
    """SharePoint'te aynı ad varsa `-2`, `-3` … (`AD_DENEME_SINIRI`); aşarsa 409. Yalnız okur."""
    govde, uzanti = Path(ad).stem, Path(ad).suffix
    aday = ad
    for n in range(1, AD_DENEME_SINIRI + 1):
        if n > 1:
            aday = f"{govde}-{n}{uzanti}"
        try:
            meta = _sharepoint_meta(klasor, aday)
        except Exception as e:
            raise BelgeYasamHatasi(502, "SharePoint'e ulaşılamadı (ad denetimi).", "sharepoint") from e
        if not meta:
            return aday
    raise BelgeYasamHatasi(409, f"Aynı adlı {AD_DENEME_SINIRI} taslak var; farklı bir ad verin.", "ad_cakismasi")


def _sha256(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def _kullanici_adi(user: dict) -> str:
    return user.get("name") or user.get("preferred_username") or "Bilinmeyen"


def _kullanici_eposta(user: dict) -> Optional[str]:
    return user.get("preferred_username") or user.get("upn") or user.get("email") or None


def _owner_id(user: dict) -> Optional[str]:
    return (_kullanici_eposta(user) or "").strip().lower() or None


def _belge_oku(db, doc_id: int, tenant_id: str, user: dict) -> models.CaseDocument:
    from auth_helpers import get_tenant_owned_document

    doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
    if doc is None:
        raise BelgeYasamHatasi(404, "Belge bulunamadı.", "belge")
    return doc


def _taslak_indir(doc: models.CaseDocument, docx_ad: str) -> bytes:
    """Taslak klasöründen `.docx`; boş/hata 502, boyut 413."""
    klasor = taslak_klasoru(doc.case.tracking_no if doc.case is not None else None, int(doc.case_id or 0))
    try:
        icerik, _mime = _sharepoint_indir(klasor, docx_ad)
    except Exception as e:
        raise BelgeYasamHatasi(502, "Taslak SharePoint'ten alınamadı.", "sharepoint") from e
    if not icerik:
        raise BelgeYasamHatasi(502, "Taslak SharePoint'ten boş geldi.", "sharepoint")
    if len(icerik) > MAX_UPLOAD_BYTES:
        raise BelgeYasamHatasi(413, f"Belge çok büyük. Maksimum {MAX_UPLOAD_MB}MB.", "boyut")
    return icerik


def _docx_adi_kayittan(doc: models.CaseDocument) -> str:
    """Taslağın SharePoint'teki adı: `original_filename` (`.docx`; kesinleşince `stored_filename` `.pdf` olur, bu kalır)."""
    ad = str(doc.original_filename or doc.stored_filename or "")
    if not ad.lower().endswith(DOCX_UZANTI):
        ad = f"{Path(ad).stem}{DOCX_UZANTI}"
    return ad


def _surum_ekle(db, doc_id: int, sha: str, etag: Optional[str], not_: Optional[str], kesin: bool, user: dict) -> models.BelgeSurumu:
    son_no = db.query(models.BelgeSurumu.surum_no).filter(models.BelgeSurumu.document_id == doc_id).order_by(
        models.BelgeSurumu.surum_no.desc()).first()
    satir = models.BelgeSurumu(
        document_id=doc_id,
        surum_no=(son_no[0] if son_no else 0) + 1,
        sha256=sha,
        sharepoint_etag=etag,
        aciklama_notu=(not_ or None),
        kesin=kesin,
        olusturan_email=_kullanici_eposta(user),
    )
    db.add(satir)
    return satir


def _etag(klasor: str, ad: str) -> Optional[str]:
    try:
        meta = _sharepoint_meta(klasor, ad) or {}
    except Exception:
        return None
    return meta.get("eTag") or meta.get("etag")


# ── 1. Yeni belge ─────────────────────────────────────────────────────────────

def yeni_belge(
    kart: Any,
    tur_kodu: str,
    tur_adi: Optional[str],
    ad: str,
    case_party_id: Optional[int],
    user: dict,
    sablon: str = "bos",
) -> dict[str, Any]:
    """Şablon kopyasını taslak klasörüne yükler, TASLAK/GIDEN/WORD belge satırı açar. Yanıt `{document_id, word_url, word_ac}`."""
    sablon_dosyasi = SABLON_DIZINI / SABLONLAR.get(sablon or "bos", "")
    if not sablon_dosyasi.name or not sablon_dosyasi.exists():
        raise BelgeYasamHatasi(422, f"Şablon tanınmadı: {sablon}", "sablon")
    docx_ad = docx_adi(ad)
    klasor = taslak_klasoru(kart.tracking_no, int(kart.id))
    docx_ad = benzersiz_ad(klasor, docx_ad)

    gecici = tempfile.mkdtemp(prefix="belge_yasam_yeni_")
    try:
        yol = os.path.join(gecici, docx_ad)
        shutil.copy2(sablon_dosyasi, yol)
        try:
            sonuc = _sharepoint_yukle(yol, docx_ad, klasor)
        except Exception as e:
            raise BelgeYasamHatasi(502, "Taslak SharePoint'e yüklenemedi.", "sharepoint") from e
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
    web_url = (sonuc or {}).get("webUrl")
    if not web_url:
        raise BelgeYasamHatasi(502, "SharePoint yükleme yanıtında bağlantı yok.", "sharepoint")

    doc_id = document_pipeline.save_case_document(
        case_id=kart.id,
        original_filename=docx_ad,
        stored_filename=docx_ad,
        belge_turu_kodu=tur_kodu,
        belge_turu_adi=tur_adi,
        case_party_id=case_party_id,
        lawyer_id=None,
        esas_no=kart.esas_no,
        is_test_mode=False,
        uploaded_by=_kullanici_adi(user),
        uploaded_by_email=_kullanici_eposta(user),
        yon="GIDEN",
        kaynak=BELGE_KAYNAGI,
        durum="TASLAK",
    )
    if doc_id is None:
        raise BelgeYasamHatasi(500, "Belge kaydı açılamadı.", "belge_kaydi")
    _url_yaz(int(doc_id), web_url)
    return {"document_id": int(doc_id), "word_url": web_url, "word_ac": word_ac(web_url)}


def word_ac(web_url: str) -> str:
    """Masaüstü Word protokol bağlantısı (`ms-word:ofe|u|<url>`); yoksa tarayıcı `word_url`'i Word Online'da açar."""
    return f"ms-word:ofe|u|{web_url}"


def _url_yaz(doc_id: int, web_url: str, *, onceki_document_id: Optional[int] = None) -> None:
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if doc is None:
            return
        doc.sharepoint_url = web_url
        doc.word_url = web_url
        doc.upload_status = "uploaded"
        if onceki_document_id is not None:
            doc.onceki_document_id = onceki_document_id
        db.commit()
    finally:
        db.close()


# ── 2-3. Sürüm kaydet / sürümler ──────────────────────────────────────────────

def surum_kaydet(doc_id: int, tenant_id: str, user: dict, not_: Optional[str] = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        doc = _belge_oku(db, doc_id, tenant_id, user)
        if (doc.durum or "KESIN") != "TASLAK" or not doc.word_url:
            raise BelgeYasamHatasi(409, "Yalnız Word taslağının sürümü kaydedilir.", "taslak_degil")
        docx_ad = _docx_adi_kayittan(doc)
        klasor = taslak_klasoru(doc.case.tracking_no if doc.case is not None else None, int(doc.case_id or 0))
        icerik = _taslak_indir(doc, docx_ad)
        sha = _sha256(icerik)
        onceki = db.query(models.BelgeSurumu.sha256).filter(models.BelgeSurumu.document_id == doc.id).order_by(
            models.BelgeSurumu.surum_no.desc()).first()
        satir = _surum_ekle(db, int(doc.id), sha, _etag(klasor, docx_ad), not_, False, user)
        db.commit()
        return {"surum_no": int(satir.surum_no), "sha256": sha, "degisti": (onceki is None) or (onceki[0] != sha)}
    finally:
        db.close()


def surumler(doc_id: int, tenant_id: str, user: dict) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        doc = _belge_oku(db, doc_id, tenant_id, user)
        satirlar = db.query(models.BelgeSurumu).filter(models.BelgeSurumu.document_id == doc.id).order_by(
            models.BelgeSurumu.surum_no.asc()).all()
        return [
            {
                "surum_no": s.surum_no,
                "sha256": s.sha256,
                "not": s.aciklama_notu,
                "olusturan_email": s.olusturan_email,
                "olusturulma": s.olusturulma.isoformat() if s.olusturulma else None,
                "kesin": bool(s.kesin),
            }
            for s in satirlar
        ]
    finally:
        db.close()


# ── 4. Kesinleştir ────────────────────────────────────────────────────────────

def _idempotent(onek: str, istek_kimligi: str, user: dict):
    anahtar = f"{onek}{istek_kimligi}"
    verdict, replay = confirm_idempotency.begin(anahtar, _owner_id(user))
    if verdict == "replay" and replay is not None:
        return anahtar, False, {"document_id": replay.get("document_id"), "reused": True}
    if verdict == "in_progress":
        raise BelgeYasamHatasi(409, "Bu işlem sunucuda halen sürüyor. Lütfen bekleyin ve TEKRAR GÖNDERMEYİN.", "suruyor")
    return anahtar, verdict == "proceed", None


def kesinlestir(doc_id: int, tenant_id: str, user: dict, istek_kimligi: str, background_tasks: Any = None) -> dict[str, Any]:
    """K14: aynı satır KESIN; PDF/A + iki arşiv kuyruğu; URL commit'i kuyrukta (bildirim/Hukukbot o anda)."""
    anahtar, aktif, replay = _idempotent(KESINLESTIR_ONEKI, istek_kimligi, user)
    if replay is not None:
        return replay
    basarili = False
    try:
        sonuc = _kesinlestir_kos(doc_id, tenant_id, user, background_tasks)
        basarili = True
        if aktif:
            confirm_idempotency.complete(anahtar, sonuc)
        return sonuc
    finally:
        if aktif and not basarili:
            confirm_idempotency.release(anahtar)


def _kesinlestir_kos(doc_id: int, tenant_id: str, user: dict, background_tasks: Any) -> dict[str, Any]:
    from pdf import pdf_converter
    from pdf.format_converter import ConversionBusyError
    from services.archive_names import unique_islenmis_name

    db = SessionLocal()
    try:
        doc = _belge_oku(db, doc_id, tenant_id, user)
        if (doc.durum or "KESIN") != "TASLAK":
            raise BelgeYasamHatasi(409, "Belge zaten kesinleşmiş.", "zaten_kesin")
        docx_ad = _docx_adi_kayittan(doc)
        klasor = taslak_klasoru(doc.case.tracking_no if doc.case is not None else None, int(doc.case_id or 0))
        icerik = _taslak_indir(doc, docx_ad)
        belge_id = int(doc.id)
        belge_turu_kodu = doc.belge_turu_kodu
    finally:
        db.close()

    gecici = tempfile.mkdtemp(prefix="belge_yasam_kesin_")
    geri_dusus_var = False  # kuyruk arızasında dosyayı BackgroundTasks görevi tüketir → dizin silinmez
    try:
        docx_yol = os.path.join(gecici, docx_ad)
        with open(docx_yol, "wb") as f:
            f.write(icerik)
        try:
            pdfa_yol = pdf_converter.convert_to_pdfa2b(docx_yol, time_budget_seconds=settings.pdf_araclari_butce_saniye)
        except ConversionBusyError as e:
            raise BelgeYasamHatasi(503, document_pipeline.CONVERSION_BUSY_DETAIL, "sistem_mesgul") from e
        except Exception as e:
            raise BelgeYasamHatasi(422, "Taslak PDF/A'ya dönüştürülemedi; Word dosyasını kontrol edin.", "donusum_basarisiz") from e
        if not pdfa_yol or not os.path.exists(pdfa_yol):
            raise BelgeYasamHatasi(422, "Taslak PDF/A'ya dönüştürülemedi.", "donusum_basarisiz")

        pdf_ad = unique_islenmis_name(f"{Path(docx_ad).stem}.pdf", exclude_doc_id=belge_id)
        sha = _sha256(icerik)
        simdi = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == belge_id).first()
            if doc is None:
                raise BelgeYasamHatasi(404, "Belge bulunamadı.", "belge")
            doc.durum = "KESIN"
            doc.kesinlesme_tarihi = simdi
            doc.kesinlestiren_email = _kullanici_eposta(user)
            doc.stored_filename = pdf_ad
            doc.sharepoint_url = None  # URL commit'i upload_queue'da → bildirim + Hukukbot o anda (G282 kapısı geçer)
            doc.upload_status = "pending"
            doc.conversion_status = None
            _surum_ekle(db, belge_id, sha, _etag(klasor, docx_ad), "Kesinleştirme", True, user)
            db.commit()
        finally:
            db.close()

        ham_folder = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
        islenmis_folder = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
        ham_ad = f"{simdi.strftime('%Y-%m-%d')}_{docx_ad}"
        if upload_queue.enqueue_upload("islenmis", pdfa_yol, pdf_ad, islenmis_folder, document_id=belge_id) is None:
            geri_dusus_var = _geri_dusus(background_tasks, document_pipeline.async_islenmis_upload, pdfa_yol, pdf_ad, islenmis_folder, belge_id) or geri_dusus_var
        if upload_queue.enqueue_upload("ham", docx_yol, ham_ad, ham_folder) is None:
            geri_dusus_var = _geri_dusus(background_tasks, document_pipeline.async_ham_upload, docx_yol, ham_ad, ham_folder) or geri_dusus_var
        return {"document_id": belge_id, "reused": False, "belge_turu_kodu": belge_turu_kodu}
    finally:
        # Kuyruk payload'ı spool'a kopyalandı; geçici dizin silinir (geri düşüş görevi varsa dosyayı o tüketir, dizin kalır).
        if not geri_dusus_var:
            shutil.rmtree(gecici, ignore_errors=True)


def _geri_dusus(background_tasks: Any, gorev: Any, *args: Any) -> bool:
    """Kuyruk arızasında eski tek-denemeli BackgroundTasks yolu (document_pipeline ile aynı karar); görev eklendiyse True."""
    if background_tasks is None:
        return False
    background_tasks.add_task(gorev, *args)
    return True


# ── 5. Yeni sürüm taslağı ─────────────────────────────────────────────────────

def yeni_surum_taslagi(doc_id: int, tenant_id: str, user: dict, istek_kimligi: str) -> dict[str, Any]:
    anahtar, aktif, replay = _idempotent(YENI_SURUM_ONEKI, istek_kimligi, user)
    if replay is not None:
        return replay
    basarili = False
    try:
        sonuc = _yeni_surum_kos(doc_id, tenant_id, user)
        basarili = True
        if aktif:
            confirm_idempotency.complete(anahtar, sonuc)
        return sonuc
    finally:
        if aktif and not basarili:
            confirm_idempotency.release(anahtar)


def _yeni_surum_kos(doc_id: int, tenant_id: str, user: dict) -> dict[str, Any]:
    db = SessionLocal()
    try:
        doc = _belge_oku(db, doc_id, tenant_id, user)
        if (doc.durum or "KESIN") != "KESIN":
            raise BelgeYasamHatasi(409, "Yalnız kesinleşmiş belgeden yeni sürüm taslağı açılır.", "kesin_degil")
        docx_ad = _docx_adi_kayittan(doc)
        kart = doc.case
        if kart is None:
            raise BelgeYasamHatasi(409, "Belge bir dava kartına bağlı değil.", "kartsiz")
        kart_id, ofis_no, esas_no = int(kart.id), kart.tracking_no, kart.esas_no
        tur_kodu = str(doc.belge_turu_kodu) if doc.belge_turu_kodu else None
        tur_adi = str(doc.belge_turu_adi) if doc.belge_turu_adi else None
        taraf_id = int(doc.case_party_id) if doc.case_party_id is not None else None
        icerik = _taslak_indir(doc, docx_ad)
        # Zincirdeki sıra: bu belgeden daha önce açılmış taslaklar + 2 (v2, v3, …); ad çakışması ayrıca denetlenir.
        kardes = db.query(models.CaseDocument.id).filter(models.CaseDocument.onceki_document_id == doc.id).count()
        n = kardes + 2
    finally:
        db.close()

    govde = re.sub(r"-v\d+$", "", Path(docx_ad).stem)
    klasor = taslak_klasoru(ofis_no, kart_id)
    yeni_ad = benzersiz_ad(klasor, f"{govde}-v{n}{DOCX_UZANTI}")
    gecici = tempfile.mkdtemp(prefix="belge_yasam_surum_")
    try:
        yol = os.path.join(gecici, yeni_ad)
        with open(yol, "wb") as f:
            f.write(icerik)
        try:
            sonuc = _sharepoint_yukle(yol, yeni_ad, klasor)
        except Exception as e:
            raise BelgeYasamHatasi(502, "Yeni taslak SharePoint'e yüklenemedi.", "sharepoint") from e
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
    web_url = (sonuc or {}).get("webUrl")
    if not web_url:
        raise BelgeYasamHatasi(502, "SharePoint yükleme yanıtında bağlantı yok.", "sharepoint")

    yeni_id = document_pipeline.save_case_document(
        case_id=kart_id,
        original_filename=yeni_ad,
        stored_filename=yeni_ad,
        belge_turu_kodu=tur_kodu,
        belge_turu_adi=tur_adi,
        case_party_id=taraf_id,
        lawyer_id=None,
        esas_no=esas_no,
        is_test_mode=False,
        uploaded_by=_kullanici_adi(user),
        uploaded_by_email=_kullanici_eposta(user),
        yon="GIDEN",
        kaynak=BELGE_KAYNAGI,
        durum="TASLAK",
    )
    if yeni_id is None:
        raise BelgeYasamHatasi(500, "Belge kaydı açılamadı.", "belge_kaydi")
    _url_yaz(int(yeni_id), web_url, onceki_document_id=doc_id)
    return {"document_id": int(yeni_id), "reused": False, "word_url": web_url, "word_ac": word_ac(web_url)}
