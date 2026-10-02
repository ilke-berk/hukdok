"""Hizmet kayıtları (G248) — `/api/cases/{case_id}/hizmetler*`.

"Bu kartta bu müvekkile bu hizmet verildi" satırları; tek yazma yolu
`managers/case_hizmetleri.py`, `cases.hizmet_turu` oradan TÜRETİLEN özettir.

Sözleşme SABİT (G252/G253 arayüzü buna göre yazılır):

* `GET    /api/cases/{case_id}/hizmetler` → 200, satır listesi
  `{id, case_party_id, muvekkil_adi, hizmet_turu, kaynak ("foy"|"elle"), foy_id, sistem_no}`
  (sıra: müvekkil adı → hizmet adı).
* `POST   /api/cases/{case_id}/hizmetler` gövde `{case_party_id, hizmet_turu}` → 201 + satır;
  aynı (müvekkil, hizmet) zaten varsa (elle ya da föyden) yeni satır AÇILMAZ → 200 + mevcut satır.
* `PUT    /api/cases/{case_id}/hizmetler/{case_party_id}` gövde `{"hizmet_turleri": [...]}` →
  200 + kartın güncel satır listesi. Müvekkilin ELLE kümesi verilen kümeye getirilir (eksik
  eklenir, fazla elle satır silinir; föy kaynaklı satıra dokunulmaz); boş liste = elle
  satırların tamamı silinir; aynı küme ikinci kez → değişiklik yok.
* `DELETE /api/cases/{case_id}/hizmetler/{hizmet_id}` → 204; föy kaynaklı satır → 409.

Hatalar: görünmeyen dava (başka tenant / soft-silinmiş) → 404; satır bu kartta yok → 404;
taraf bu kartın müvekkili değil ya da hizmet adı `service_types` listesinde yok → 422
(hiçbir satır yazılmaz); föy kaynaklı satırı silme → 409 (yalnız aktarım değiştirir).

Yetki `PUT /api/cases/{id}` ile aynı: oturumlu kullanıcı + tenant filtresi
(`auth_helpers.get_tenant_owned_case` — paylaşımlı havuz: `tenant_id == X OR IS NULL`).
"""
import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from auth_helpers import get_tenant_owned_case
from database import get_db
from dependencies import get_current_tenant, get_current_user
from managers import case_hizmetleri
from managers.case_manager import PANEL_SOURCE
from schemas import CaseHizmetCreate, CaseHizmetKumesi, CaseHizmetRead

logger = logging.getLogger(__name__)

router = APIRouter()


def _degistiren(user: dict) -> str:
    """Tarihçe imzası — `PATCH /tracking` ile aynı kural."""
    return user.get("name") or user.get("preferred_username") or "unknown"


def _gorunen_kart(db: Session, case_id: int, tenant_id: str) -> Any:
    case = get_tenant_owned_case(db, case_id, tenant_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Dava bulunamadı")
    return case


def _satir(db: Session, case_id: int, hizmet_id: int) -> dict:
    return next(s for s in case_hizmetleri.kart_hizmet_listesi(db, case_id) if s["id"] == hizmet_id)


@router.get("/api/cases/{case_id}/hizmetler", response_model=List[CaseHizmetRead])
def list_case_hizmetleri(
    case_id: int,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _gorunen_kart(db, case_id, tenant_id)
    return case_hizmetleri.kart_hizmet_listesi(db, case_id)


@router.post("/api/cases/{case_id}/hizmetler", response_model=CaseHizmetRead, status_code=201)
def add_case_hizmeti(
    case_id: int,
    payload: CaseHizmetCreate,
    response: Response,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    case = _gorunen_kart(db, case_id, tenant_id)
    try:
        row, yeni = case_hizmetleri.elle_ekle(
            db, case, payload.case_party_id, payload.hizmet_turu,
            changed_by=_degistiren(user), source=PANEL_SOURCE,
        )
    except case_hizmetleri.HizmetHatasi as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    if not yeni:
        response.status_code = 200      # tekrar: yeni satır açılmadı, mevcut satır döner
    else:
        logger.info("Hizmet kaydı eklendi: case_id=%s hizmet_id=%s", case_id, row.id)
    return _satir(db, case_id, row.id)


@router.put("/api/cases/{case_id}/hizmetler/{case_party_id}", response_model=List[CaseHizmetRead])
def set_case_party_hizmetleri(
    case_id: int,
    case_party_id: int,
    payload: CaseHizmetKumesi,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    case = _gorunen_kart(db, case_id, tenant_id)
    try:
        degisti = case_hizmetleri.elle_kumesini_yaz(
            db, case, case_party_id, payload.hizmet_turleri,
            changed_by=_degistiren(user), source=PANEL_SOURCE,
        )
    except case_hizmetleri.HizmetHatasi as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    if degisti:
        logger.info("Hizmet kümesi yazıldı: case_id=%s case_party_id=%s", case_id, case_party_id)
    return case_hizmetleri.kart_hizmet_listesi(db, case_id)


@router.delete("/api/cases/{case_id}/hizmetler/{hizmet_id}", status_code=204)
def delete_case_hizmeti(
    case_id: int,
    hizmet_id: int,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    case = _gorunen_kart(db, case_id, tenant_id)
    try:
        silindi = case_hizmetleri.elle_sil(
            db, case, hizmet_id, changed_by=_degistiren(user), source=PANEL_SOURCE,
        )
    except case_hizmetleri.FoyKaynakliSatir as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not silindi:
        raise HTTPException(status_code=404, detail="Hizmet kaydı bulunamadı")
    db.commit()
    logger.info("Hizmet kaydı silindi: case_id=%s hizmet_id=%s", case_id, hizmet_id)
    return Response(status_code=204)
