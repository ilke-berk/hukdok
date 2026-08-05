import logging

from fastapi import APIRouter, Depends

from auth_helpers import tenant_filter_clause
from dependencies import get_current_tenant
from schemas import PartyCheckRequest, PartyCheckResponse
from database import SessionLocal
from party_check import check_parties
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/parties/check", response_model=PartyCheckResponse)
def api_check_parties(req: PartyCheckRequest, tenant_id: str = Depends(get_current_tenant)):
    """Tanıdık sorgu: girilen taraf isimlerini/TC'lerini cari kayıtları ve
    geçmiş dosya taraflarıyla karşılaştırır. Salt okunur; kayıt engellemez."""
    db = SessionLocal()
    try:
        client_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no,
                "cari_kod": r.cari_kod, "category": r.category,
                "contact_type": r.contact_type,
            }
            for r in (
                db.query(
                    models.Client.id, models.Client.name, models.Client.tc_no,
                    models.Client.cari_kod, models.Client.category,
                    models.Client.contact_type,
                )
                .filter(models.Client.active.is_(True))
                .filter(models.Client.deleted_at.is_(None))
                .filter(tenant_filter_clause(models.Client, tenant_id))
                .all()
            )
        ]

        party_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no, "role": r.role,
                "party_type": r.party_type, "client_id": r.client_id,
                "case_id": r.case_id, "tracking_no": r.tracking_no,
                "case_subject": r.subject, "case_status": r.status,
            }
            for r in (
                db.query(
                    models.CaseParty.id, models.CaseParty.name,
                    models.CaseParty.tc_no, models.CaseParty.role,
                    models.CaseParty.party_type, models.CaseParty.client_id,
                    models.CaseParty.case_id, models.Case.tracking_no,
                    models.Case.subject, models.Case.status,
                )
                .join(models.Case, models.CaseParty.case_id == models.Case.id)
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .filter(models.Case.deleted_at.is_(None))
                .all()
            )
        ]

        results = check_parties(
            [q.model_dump() for q in req.parties],
            client_rows,
            party_rows,
            exclude_case_id=req.exclude_case_id,
        )
        return {"results": results}
    finally:
        db.close()
