"""Raporlama uçları (G130 + G131): `/api/reports/*`.

Test aşamasında yalnız yöneticiler (`require_admin`, `routes/config.py`) +
`get_current_tenant`; tenant ve soft-delete kuralı motorda (K2). Sözleşme
`docs/plan/raporlama-plani-2026-09-06.md` §2.4 — G133/G134 frontend'i buna göre yazılır.

Uçlar:
- `GET /catalog`, `POST /preview` (G130) — önizleme LOGLANMAZ (K4).
- `GET/POST /templates`, `PUT/DELETE /templates/{id}` (G131, K5): sahip yalnız
  `olusturan` düzenler/siler (403); GET kendi + `paylasimli=true`; soft delete.
- `POST /export` (G131, K3/K4): COUNT → tavan (413) → koşu satırı (`kosu_baslat`)
  → dosya `RAPOR_CIKTI_DIZINI/<run_id>-<slug>.<ext>` (`cikti.ciktiyi_yaz`) →
  `kosu_bitir` (sha256/boyut) → best-effort temizlik → aynı dosya `FileResponse`
  (`X-Rapor-Kosu-Id` başlığı). Hata yolunda koşu satırı `hata` ile KALIR.
- `GET /runs`, `GET /runs/{id}/download` (G131): tüm yöneticilerin koşuları;
  temizlenmiş dosya 410; yol `routes/admin.py::api_teslim_rapor_indir` deseniyle
  denetlenir (dizin altı + izinli uzantı, aksi 404).

`SessionLocal` modül düzeyinde (testler `routes.reports.SessionLocal`'ı
sqlite fabrikasına monkeypatch'ler — `routes/admin.py` deseni).

Gövde doğrulama BİLİNÇLİ elle: FastAPI'nin varsayılan 422 gövdesi `[{loc,msg,type}]`
listesidir; sözleşme tek `{"alan","sebep"}` ister (`schemas_rapor.pydantic_hatasini_cevir`).

`/chat` BURADA YOK — G132.
"""
import datetime as dt
import logging
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import models
from auth_helpers import tenant_filter_clause
from config.settings import settings
from database import SessionLocal
from dependencies import get_current_tenant
from routes.config import require_admin
from schemas_rapor import (
    ExportIstegi, KosuListesi, OnizlemeCevabi, OnizlemeIstegi, RaporDogrulamaHatasi, RaporKosusu, RaporSablonu,
    SablonIstegi, pydantic_hatasini_cevir,
)
from services.rapor import cikti, kosu_logu, motor, registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

RUNS_LIMIT_MAX = 200


def _kullanici_epostasi(user: dict) -> str:
    """`routes/activity._get_user_email` üçlüsü; küçük harf (require_admin ile aynı)."""
    return str(user.get("preferred_username") or user.get("upn") or user.get("email") or "").lower()


def _dogrula(model, govde: dict[str, Any]):
    try:
        return model.model_validate(govde)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=pydantic_hatasini_cevir(e).detay()) from None


# ─── G130: katalog + önizleme ────────────────────────────────────────────────

@router.get("/catalog")
def api_catalog(
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Kayıt defteri: veri kaynakları, kolonlar (tip/filtre/sıralama/seçenek) + limitler."""
    db = SessionLocal()
    try:
        return registry.katalog(db, motor.limitler())
    finally:
        db.close()


@router.post("/preview", response_model=OnizlemeCevabi)
def api_preview(
    govde: dict[str, Any] = Body(...),
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Tanımı doğrular, sayfalı önizleme döner. Önizleme LOGLANMAZ (K4)."""
    istek = _dogrula(OnizlemeIstegi, govde)
    db = SessionLocal()
    try:
        kolonlar, satirlar, toplam = motor.onizle(db, istek.tanim, tenant_id, istek.sayfa, istek.sayfa_boyu)
    except RaporDogrulamaHatasi as e:
        raise HTTPException(status_code=422, detail=e.detay()) from None
    finally:
        db.close()
    return OnizlemeCevabi(
        kolonlar=kolonlar, satirlar=satirlar, toplam=toplam, sayfa=istek.sayfa, sayfa_boyu=istek.sayfa_boyu,
    )


# ─── G131: şablonlar ─────────────────────────────────────────────────────────

def _sablon_cevabi(s: models.ReportTemplate) -> RaporSablonu:
    return RaporSablonu.model_validate(s)


def _sablon_sorgusu(db: Session, tenant_id: str):
    return db.query(models.ReportTemplate).filter(
        models.ReportTemplate.deleted_at.is_(None),
        tenant_filter_clause(models.ReportTemplate, tenant_id),
    )


def _sablon_veya_404(db: Session, sablon_id: int, tenant_id: str) -> models.ReportTemplate:
    sablon = _sablon_sorgusu(db, tenant_id).filter(models.ReportTemplate.id == sablon_id).first()
    if sablon is None:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return sablon


def _sahibi_dogrula(sablon: models.ReportTemplate, eposta: str) -> None:
    if (sablon.olusturan or "").lower() != eposta:
        raise HTTPException(status_code=403, detail="Yalnız şablonun sahibi düzenleyebilir")


def _tanimi_dogrula_422(istek_tanim) -> None:
    try:
        motor.tanimi_dogrula(istek_tanim)
    except RaporDogrulamaHatasi as e:
        raise HTTPException(status_code=422, detail=e.detay()) from None


@router.get("/templates", response_model=list[RaporSablonu])
def api_templates_list(
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Kendi şablonları + paylaşımlılar (silinmişler hariç), ad sırasıyla."""
    eposta = _kullanici_epostasi(user)
    db = SessionLocal()
    try:
        sablonlar = (
            _sablon_sorgusu(db, tenant_id)
            .filter(or_(func.lower(models.ReportTemplate.olusturan) == eposta,
                        models.ReportTemplate.paylasimli.is_(True)))
            .order_by(models.ReportTemplate.ad.asc(), models.ReportTemplate.id.asc())
            .all()
        )
        return [_sablon_cevabi(s) for s in sablonlar]
    finally:
        db.close()


@router.post("/templates", response_model=RaporSablonu, status_code=201)
def api_templates_create(
    govde: dict[str, Any] = Body(...),
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    istek = _dogrula(SablonIstegi, govde)
    _tanimi_dogrula_422(istek.tanim)
    db = SessionLocal()
    try:
        sablon = models.ReportTemplate(
            ad=istek.ad, aciklama=istek.aciklama, tanim=istek.tanim.model_dump(),
            olusturan=_kullanici_epostasi(user), paylasimli=istek.paylasimli, tenant_id=tenant_id,
        )
        db.add(sablon)
        db.commit()
        db.refresh(sablon)
        return _sablon_cevabi(sablon)
    finally:
        db.close()


@router.put("/templates/{sablon_id}", response_model=RaporSablonu)
def api_templates_update(
    sablon_id: int,
    govde: dict[str, Any] = Body(...),
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Tam gövde (kısmi değil); başkasının şablonu 403."""
    istek = _dogrula(SablonIstegi, govde)
    _tanimi_dogrula_422(istek.tanim)
    db = SessionLocal()
    try:
        sablon = _sablon_veya_404(db, sablon_id, tenant_id)
        _sahibi_dogrula(sablon, _kullanici_epostasi(user))
        sablon.ad = istek.ad
        sablon.aciklama = istek.aciklama
        sablon.tanim = istek.tanim.model_dump()
        sablon.paylasimli = istek.paylasimli
        sablon.updated_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        db.refresh(sablon)
        return _sablon_cevabi(sablon)
    finally:
        db.close()


@router.delete("/templates/{sablon_id}", status_code=204, response_class=Response)
def api_templates_delete(
    sablon_id: int,
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft delete (`deleted_at` + `deleted_by`); başkasının şablonu 403."""
    eposta = _kullanici_epostasi(user)
    db = SessionLocal()
    try:
        sablon = _sablon_veya_404(db, sablon_id, tenant_id)
        _sahibi_dogrula(sablon, eposta)
        sablon.deleted_at = dt.datetime.now(dt.timezone.utc)
        sablon.deleted_by = eposta
        db.commit()
    finally:
        db.close()
    return Response(status_code=204)


# ─── G131: export ────────────────────────────────────────────────────────────

def _indirme_adi(kaynak: str, format: str, anlik: dt.datetime) -> str:
    """Plan §2.4: `hukdok-rapor-<kaynak>-<YYYYMMDD-HHMM>.<ext>`."""
    return f"hukdok-rapor-{kaynak}-{anlik.strftime('%Y%m%d-%H%M')}.{format}"


@router.post("/export")
def api_export(
    govde: dict[str, Any] = Body(...),
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Excel/CSV indirme — TEK log yolu (K7): koşu satırı + saklanan dosya + aynı dosya cevap."""
    istek = _dogrula(ExportIstegi, govde)
    eposta = _kullanici_epostasi(user)
    db = SessionLocal()
    try:
        try:
            sorgu = motor.sorgu_kur(istek.tanim, tenant_id)
            kolonlar = motor.kolon_basliklari(istek.tanim)
        except RaporDogrulamaHatasi as e:
            raise HTTPException(status_code=422, detail=e.detay()) from None
        if istek.sablon_id is not None:
            _sablon_veya_404(db, istek.sablon_id, tenant_id)

        toplam = int(db.execute(select(func.count()).select_from(sorgu.order_by(None).subquery())).scalar_one())
        limit = int(settings.rapor_max_satir)
        if toplam > limit:
            raise HTTPException(status_code=413, detail={"sebep": "satir_limiti", "toplam": toplam, "limit": limit})

        baslangic = dt.datetime.now(dt.timezone.utc)
        dosya_adi = _indirme_adi(istek.kaynak, istek.format, baslangic)
        run = kosu_logu.kosu_baslat(
            db, tanim=istek.tanim.model_dump(), format=istek.format, kaynak=istek.kaynak,
            veri_kaynagi=istek.tanim.veri_kaynagi, kolon_sayisi=len(kolonlar), satir_sayisi=toplam,
            kullanici=eposta, tenant_id=tenant_id, dosya_adi=dosya_adi, sablon_id=istek.sablon_id,
        )
        run_id: int = run.id
        hedef = kosu_logu.cikti_yolu(run_id, dosya_adi)
        sayac = time.perf_counter()
        try:
            ozet = cikti.ciktiyi_yaz(istek.format, kolonlar, motor.satirlari_akit(db, istek.tanim, tenant_id), hedef)
        except Exception as exc:
            sure_ms = int((time.perf_counter() - sayac) * 1000)
            logger.error("Rapor export basarisiz run=%s kullanici=%s: %s", run.id, eposta, exc)
            try:
                if hedef.exists():
                    hedef.unlink()
            except OSError:
                pass
            db.rollback()
            kosu_logu.kosu_bitir(db, run, sure_ms=sure_ms, hata=f"{type(exc).__name__}: {exc}")
            raise HTTPException(status_code=500, detail="Rapor üretilemedi") from None
        sure_ms = int((time.perf_counter() - sayac) * 1000)
        kosu_logu.kosu_bitir(
            db, run, dosya_yolu=str(hedef), dosya_boyutu=ozet.dosya_boyutu, sha256=ozet.sha256,
            satir_sayisi=ozet.satir_sayisi, sure_ms=sure_ms,
        )
        kosu_logu.temizle_sessiz(db)
    finally:
        db.close()
    return FileResponse(
        path=str(hedef), media_type=cikti.MEDYA_TURLERI[istek.format], filename=dosya_adi,
        headers={"X-Rapor-Kosu-Id": str(run_id)},
    )


# ─── G131: koşular ───────────────────────────────────────────────────────────

_KOSU_ALANLARI = (
    "id", "sablon_id", "format", "kaynak", "veri_kaynagi", "kolon_sayisi", "satir_sayisi", "kullanici",
    "baslangic", "sure_ms", "dosya_adi", "dosya_boyutu", "sha256", "hata",
)


def _kosu_cevabi(run: models.ReportRun) -> RaporKosusu:
    veri: dict[str, Any] = {alan: getattr(run, alan) for alan in _KOSU_ALANLARI}
    veri["sablon_adi"] = run.sablon.ad if run.sablon is not None else None
    veri["dosya_mevcut"] = kosu_logu.dosya_mevcut(run)
    veri["tanim"] = run.tanim or {}
    return RaporKosusu.model_validate(veri)


def _kosu_sorgusu(db: Session, tenant_id: str):
    return db.query(models.ReportRun).filter(tenant_filter_clause(models.ReportRun, tenant_id))


@router.get("/runs", response_model=KosuListesi)
def api_runs(
    limit: int = Query(50, ge=1, le=RUNS_LIMIT_MAX),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Tüm yöneticilerin koşuları, yeni → eski."""
    db = SessionLocal()
    try:
        sorgu = _kosu_sorgusu(db, tenant_id)
        toplam = sorgu.count()
        kosular = (
            sorgu.order_by(models.ReportRun.baslangic.desc(), models.ReportRun.id.desc())
            .offset(offset).limit(limit).all()
        )
        return KosuListesi(toplam=toplam, kosular=[_kosu_cevabi(r) for r in kosular])
    finally:
        db.close()


@router.get("/runs/{run_id}/download")
def api_run_download(
    run_id: int,
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Saklanan çıktıyı verir. Temizlenmiş (yol NULL / dosya yok) → 410; yol dizin
    dışında ya da izinsiz uzantıda → 404 (traversal savunması, admin.py deseni)."""
    db = SessionLocal()
    try:
        run = _kosu_sorgusu(db, tenant_id).filter(models.ReportRun.id == run_id).first()
        if run is None:
            raise HTTPException(status_code=404, detail="Koşu bulunamadı")
        yol: Optional[str] = run.dosya_yolu
        dosya_adi, format = run.dosya_adi, run.format
    finally:
        db.close()
    if not yol:
        raise HTTPException(status_code=410, detail="Çıktı saklama süresi doldu")
    if not kosu_logu.yol_guvenli_mi(yol):
        raise HTTPException(status_code=404, detail="Çıktı bulunamadı")
    dosya = Path(yol)
    if not dosya.is_file():
        raise HTTPException(status_code=410, detail="Çıktı saklama süresi doldu")
    return FileResponse(
        path=str(dosya), media_type=cikti.MEDYA_TURLERI.get(format, "application/octet-stream"),
        filename=dosya_adi, headers={"X-Rapor-Kosu-Id": str(run_id)},
    )
