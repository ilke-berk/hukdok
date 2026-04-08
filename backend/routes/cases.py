import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from dependencies import get_current_user
from schemas import CaseCreate, CaseListRead
from database import SessionLocal
from managers.admin_manager import add_case, get_case, get_cases, get_case_stats, update_case, search_cases
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/cases")
def api_add_case(case_data: CaseCreate, user: dict = Depends(get_current_user)):
    result = add_case(case_data.model_dump())
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save case")
    return {"status": "success", "message": "Case saved", **result}


@router.get("/api/cases/stats")
def api_get_case_stats(user: dict = Depends(get_current_user)):
    return get_case_stats()


@router.get("/api/cases", response_model=List[CaseListRead])
def get_cases_api(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    lawyer: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    return get_cases(limit=limit, offset=offset, status=status, lawyer=lawyer, q=q)


@router.get("/api/cases/client-sequence")
def get_client_case_sequence(client_name: str, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        if not client_name:
            return {"sequence": 1}

        clean_name = client_name.strip().upper()
        for suffix in [" DR.", " DR"]:
            if clean_name.endswith(suffix):
                clean_name = clean_name[: -len(suffix)].strip()
                break

        query_pattern = f"{clean_name}%"
        count = (
            db.query(func.count(func.distinct(models.CaseParty.case_id)))
            .filter(models.CaseParty.party_type == "CLIENT")
            .filter(models.CaseParty.name.ilike(query_pattern))
            .scalar()
        )
        return {"sequence": (count or 0) + 1}
    except Exception as e:
        logger.error(f"Error getting client sequence: {e}")
        return {"sequence": 1}
    finally:
        db.close()


@router.get("/api/cases/search")
def api_search_cases(q: str, user: dict = Depends(get_current_user)):
    return search_cases(q)


@router.get("/api/cases/{case_id}")
def api_get_case(case_id: int, user: dict = Depends(get_current_user)):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.put("/api/cases/{case_id}")
def api_update_case(case_id: int, case_data: CaseCreate, user: dict = Depends(get_current_user)):
    success = update_case(case_id, case_data.model_dump())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update case")
    return {"status": "success", "message": "Case updated"}


@router.delete("/api/cases/{case_id}")
def api_delete_case(case_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        db.delete(case)
        db.commit()
        return {"status": "success", "message": "Case deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/api/incomplete-tasks")
def get_incomplete_tasks(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        incomplete_cases = []
        incomplete_clients = []

        cases = (
            db.query(models.Case)
            .options(selectinload(models.Case.parties))
            .filter(models.Case.active == True)
            .order_by(models.Case.created_at.desc())
            .limit(100)
            .all()
        )

        for c in cases:
            missing = []
            if not c.court:
                missing.append("Mahkeme")
            if not c.responsible_lawyer_name:
                missing.append("Avukat")
            if not c.subject:
                missing.append("Konu")

            client_parties = [p for p in c.parties if p.party_type == "CLIENT"]
            for p in client_parties:
                if not p.client_id:
                    missing.append(f"Müvekkil bağlantısı ({p.name})")

            if len(client_parties) == 0:
                missing.append("Müvekkil yok")

            if missing:
                incomplete_cases.append(
                    {
                        "id": c.id,
                        "type": "case",
                        "esas_no": c.esas_no or c.tracking_no,
                        "court": c.court or "",
                        "status": c.status,
                        "missing_fields": missing,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                )

        clients = (
            db.query(models.Client)
            .filter(models.Client.active == True)
            .order_by(models.Client.updated_at.desc())
            .limit(50)
            .all()
        )

        for cl in clients:
            missing = []
            if not cl.phone and not cl.mobile_phone:
                missing.append("Telefon")
            if not cl.email:
                missing.append("E-posta")
            if not cl.tc_no:
                missing.append("TC No")

            if len(missing) >= 2:
                incomplete_clients.append(
                    {
                        "id": cl.id,
                        "type": "client",
                        "name": cl.name,
                        "client_type": cl.client_type or "Belirtilmemiş",
                        "missing_fields": missing,
                    }
                )

        return {
            "incomplete_cases": incomplete_cases[:30],
            "incomplete_clients": incomplete_clients[:20],
            "total_incomplete_cases": len(incomplete_cases),
            "total_incomplete_clients": len(incomplete_clients),
        }
    except Exception as e:
        logger.error(f"Incomplete Tasks Error: {e}")
        return {
            "incomplete_cases": [],
            "incomplete_clients": [],
            "total_incomplete_cases": 0,
            "total_incomplete_clients": 0,
        }
    finally:
        db.close()
