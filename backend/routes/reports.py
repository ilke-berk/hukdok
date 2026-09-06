"""Raporlama uçları (G130): `GET /api/reports/catalog`, `POST /api/reports/preview`.

Test aşamasında yalnız yöneticiler (`require_admin`, `routes/config.py`) +
`get_current_tenant`; tenant ve soft-delete kuralı motorda (K2). Sözleşme
`docs/plan/raporlama-plani-2026-09-06.md` §2.4 — G133 frontend'i buna göre yazılır.

`SessionLocal` modül düzeyinde (testler `routes.reports.SessionLocal`'ı
sqlite fabrikasına monkeypatch'ler — `routes/admin.py` deseni).

Gövde doğrulama BİLİNÇLİ elle: FastAPI'nin varsayılan 422 gövdesi `[{loc,msg,type}]`
listesidir; sözleşme tek `{"alan","sebep"}` ister (`schemas_rapor.pydantic_hatasini_cevir`).

`/export`, `/templates`, `/runs`, `/chat` BURADA YOK — G131/G132.
"""
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError

from database import SessionLocal
from dependencies import get_current_tenant
from routes.config import require_admin
from schemas_rapor import OnizlemeCevabi, OnizlemeIstegi, RaporDogrulamaHatasi, pydantic_hatasini_cevir
from services.rapor import motor, registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
    try:
        istek = OnizlemeIstegi.model_validate(govde)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=pydantic_hatasini_cevir(e).detay()) from None
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
