"""Word yaşam döngüsü uçları (G284, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §6.3).

`POST /api/cases/{id}/belgeler/yeni` · `POST /api/documents/{id}/surum` · `GET /api/documents/{id}/surumler` ·
`POST /api/documents/{id}/kesinlestir` · `POST /api/documents/{id}/yeni-surum-taslagi`.

İş mantığı `services/belge_yasam.py` (HTTP bilmez; `BelgeYasamHatasi(status, mesaj, error_kod)` burada HTTP'ye çevrilir).
Hata gövdesi PDF araçlarıyla aynı: `{"detail": {"mesaj", "error_kod"}}`; log sözleşmesi 4xx WARNING, 5xx TEK ERROR.
Her yol `/api/` altında → nginx DEĞİŞMEZ (K10). Hız sınırı uca özel `30/minute` (PDF araçlarıyla aynı).
"""
from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from auth_helpers import get_tenant_owned_case
from database import SessionLocal
from db_errors import KAYIT_MESGUL_DETAIL, KayitMesgulError
from dependencies import get_current_tenant, get_current_user
from file_utils import _normalize_doctype_code
from managers.config_manager import DynamicConfig
import models
from rate_limiting import limiter
from services import belge_yasam

router = APIRouter()
logger = logging.getLogger(__name__)

HIZ_SINIRI = "30/minute"
KART_BULUNAMADI = "Belirtilen dava bulunamadı."


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YeniBelgeIstegi(_StrictModel):
    belge_turu_kodu: str = Field(min_length=1, max_length=64)
    ad: str = Field(min_length=1, max_length=255)
    sablon: Literal["bos"] = "bos"
    case_party_id: Optional[int] = Field(default=None, ge=1)


class SurumIstegi(_StrictModel):
    # `not` Python anahtar sözcüğü — alan adı sözleşmede `not` (§6.3), modelde takma ad.
    not_: Optional[str] = Field(default=None, alias="not", max_length=2000)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class KimlikliIstek(_StrictModel):
    istek_kimligi: uuid.UUID


def _hata(status: int, detail: str, error_kod: str, exc: Optional[Exception] = None) -> HTTPException:
    """Log sözleşmesi: 4xx WARNING, 5xx TEK ERROR."""
    if status >= 500:
        logger.error(f"Belge yaşam döngüsü hatası [{error_kod}]: {exc or detail}")
    else:
        logger.warning(f"Belge yaşam döngüsü reddi [{error_kod}]: {exc or detail}")
    return HTTPException(status_code=status, detail={"mesaj": detail, "error_kod": error_kod})


def _cevir(e: Exception) -> HTTPException:
    if isinstance(e, belge_yasam.BelgeYasamHatasi):
        return _hata(e.status, e.mesaj, e.error_kod, e)
    if isinstance(e, KayitMesgulError):
        return HTTPException(status_code=409, detail=KAYIT_MESGUL_DETAIL)
    if isinstance(e, HTTPException):
        return e
    return _hata(500, "Belge işlemi tamamlanamadı.", "belge_yasam", e)


def _belge_turleri() -> list[dict]:
    turler = DynamicConfig.get_instance().get_doctypes()
    if not turler:
        from managers.reference_lists import get_doctypes

        turler = get_doctypes()
    return turler or []


def _belge_turu_coz(kod: str) -> tuple[str, Optional[str]]:
    """Kanonik (`_` pad'li) kod + ad; `_normalize_doctype_code` ile eşleşir (padding tuzağı); yoksa 422."""
    hedef = _normalize_doctype_code(kod)
    if hedef:
        for tur in _belge_turleri():
            ham = tur.get("kod") or tur.get("code") or tur.get("value")
            if ham and _normalize_doctype_code(str(ham)) == hedef:
                return str(ham), tur.get("aciklama") or tur.get("label") or tur.get("name") or None
    raise _hata(422, f"Belge türü kodu tanınmadı: {kod}", "belge_turu", ValueError(kod))


def _kart_bul(case_id: int, tenant_id: str) -> SimpleNamespace:
    db = SessionLocal()
    try:
        kart = get_tenant_owned_case(db, case_id, tenant_id)
        if kart is None:
            raise HTTPException(status_code=404, detail=KART_BULUNAMADI)
        return SimpleNamespace(id=kart.id, tracking_no=kart.tracking_no, esas_no=kart.esas_no)
    finally:
        db.close()


def _taraf_dogrula(case_party_id: Optional[int], case_id: int) -> None:
    if case_party_id is None:
        return
    db = SessionLocal()
    try:
        taraf = (
            db.query(models.CaseParty.id)
            .filter(models.CaseParty.id == case_party_id, models.CaseParty.case_id == case_id)
            .first()
        )
    finally:
        db.close()
    if taraf is None:
        raise _hata(422, "Taraf bu davanın tarafı değil.", "taraf", ValueError(case_party_id))


@router.post("/api/cases/{case_id}/belgeler/yeni")
@limiter.limit(HIZ_SINIRI)
async def yeni_belge(
    request: Request,
    case_id: int,
    istek: YeniBelgeIstegi,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, Any]:
    """K15: `bos.docx` → `03_TASLAKLAR/<ofis_no>/<ad>.docx` (senkron), TASLAK/GIDEN/WORD satır; yanıt `{document_id, word_url, word_ac}`."""
    kart = _kart_bul(case_id, tenant_id)
    tur_kodu, tur_adi = _belge_turu_coz(istek.belge_turu_kodu)
    _taraf_dogrula(istek.case_party_id, kart.id)
    try:
        return await run_in_threadpool(
            belge_yasam.yeni_belge, kart, tur_kodu, tur_adi, istek.ad, istek.case_party_id, user, istek.sablon,
        )
    except Exception as e:
        raise _cevir(e) from None


@router.post("/api/documents/{document_id}/surum")
@limiter.limit(HIZ_SINIRI)
async def surum_kaydet(
    request: Request,
    document_id: int,
    istek: Optional[SurumIstegi] = None,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, Any]:
    """K13: bilinçli sürüm kaydı; yanıt `{surum_no, sha256, degisti}`; taslak değilse 409, boyut 413, SharePoint 502."""
    try:
        return await run_in_threadpool(belge_yasam.surum_kaydet, document_id, tenant_id, user, istek.not_ if istek else None)
    except Exception as e:
        raise _cevir(e) from None


@router.get("/api/documents/{document_id}/surumler")
async def surumler(
    document_id: int,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    try:
        return await run_in_threadpool(belge_yasam.surumler, document_id, tenant_id, user)
    except Exception as e:
        raise _cevir(e) from None


@router.post("/api/documents/{document_id}/kesinlestir")
@limiter.limit(HIZ_SINIRI)
async def kesinlestir(
    request: Request,
    document_id: int,
    istek: KimlikliIstek,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, Any]:
    """K14: aynı satır KESIN + PDF/A + iki arşiv kuyruğu; idempotent (`istek_kimligi`); zaten KESIN 409; meşgul 503."""
    try:
        sonuc = await run_in_threadpool(
            belge_yasam.kesinlestir, document_id, tenant_id, user, str(istek.istek_kimligi), background_tasks,
        )
    except Exception as e:
        raise _cevir(e) from None
    return {"document_id": sonuc.get("document_id"), "reused": bool(sonuc.get("reused"))}


@router.post("/api/documents/{document_id}/yeni-surum-taslagi")
@limiter.limit(HIZ_SINIRI)
async def yeni_surum_taslagi(
    request: Request,
    document_id: int,
    istek: KimlikliIstek,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, Any]:
    """K14 düzeltme yolu: KESIN belgeden yeni TASLAK (`<ad>-v{n}.docx`, `onceki_document_id`); idempotent."""
    try:
        sonuc = await run_in_threadpool(
            belge_yasam.yeni_surum_taslagi, document_id, tenant_id, user, str(istek.istek_kimligi),
        )
    except Exception as e:
        raise _cevir(e) from None
    return {
        "document_id": sonuc.get("document_id"),
        "reused": bool(sonuc.get("reused")),
        "word_url": sonuc.get("word_url"),
        "word_ac": sonuc.get("word_ac"),
    }
