import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query

from auth_helpers import get_tenant_owned_client, tenant_filter_clause
from dependencies import get_current_tenant, get_current_user
from schemas import (
    ClientCreate,
    ClientPolicyRead,
    ClientPolicySaveRequest,
    ClientRead,
    ClientUpdate,
)
from database import SessionLocal
from managers.client_manager import add_client, save_client_policies
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/clients")
def api_add_client(
    client: ClientCreate,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    # Hanyaloğlu Acar + LexisBio ortak çalıştığı için yeni müvekkiller paylaşımlı (tenant_id=NULL).
    # tenant_id parametresi token doğrulaması için gerekli ama damgalamada kullanılmıyor.
    success = add_client(client.model_dump())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save client")
    return {"status": "success", "message": "Client saved"}


@router.get("/api/clients", response_model=List[ClientRead])
def get_clients_api(tenant_id: str = Depends(get_current_tenant)):
    db = SessionLocal()
    try:
        clients = (
            db.query(models.Client)
            .filter(models.Client.active.is_(True))
            .filter(models.Client.deleted_at.is_(None))
            .filter(tenant_filter_clause(models.Client, tenant_id))
            .order_by(models.Client.name.asc())
            .all()
        )
        return clients
    finally:
        db.close()


@router.put("/api/clients/{client_id}")
def api_update_client(
    client_id: int,
    client_data: ClientUpdate,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        update_data = client_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(client, key, value)

        db.commit()
        db.refresh(client)
        return {"status": "success", "message": "Client updated", "client": client}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating client: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Müvekkil bilgileri güncellenemedi. Lütfen tekrar deneyin.") from e
    finally:
        db.close()


# ─── Müvekkil poliçeleri (otonom dava açma Faz 3, plan Kararlar #3) ──────────


def _policy_row_for_overlap(p: models.ClientPolicy) -> dict:
    """ORM satırını services.case_intake.policy_overlap_warnings şekline çevirir."""
    return {
        "police_no": p.police_no,
        "police_turu": p.police_turu,
        "sigorta_sirketi": p.sigorta_sirketi,
        "baslangic": str(p.baslangic_tarihi) if p.baslangic_tarihi else None,
        "bitis": str(p.bitis_tarihi) if p.bitis_tarihi else None,
    }


@router.get("/api/clients/{client_id}/policies")
def api_list_client_policies(
    client_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    """Müvekkilin kayıtlı poliçeleri + dönem çakışması uyarıları."""
    from services.case_intake import policy_overlap_warnings

    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        rows = (
            db.query(models.ClientPolicy)
            .filter(models.ClientPolicy.client_id == client_id)
            .order_by(models.ClientPolicy.baslangic_tarihi.desc().nullslast(),
                      models.ClientPolicy.id.desc())
            .all()
        )
        # Kaynak belge linki: source_document yalnız dosya adı tutar; arşivdeki
        # SharePoint URL'si case_documents'tan ada göre bulunur (en yeni kayıt).
        policies_out = []
        for r in rows:
            item = ClientPolicyRead.model_validate(r).model_dump()
            item["document_url"] = None
            if r.source_document:
                doc = (
                    db.query(models.CaseDocument.sharepoint_url)
                    .filter(models.CaseDocument.original_filename == r.source_document,
                            models.CaseDocument.sharepoint_url.isnot(None))
                    .order_by(models.CaseDocument.id.desc())
                    .first()
                )
                item["document_url"] = doc[0] if doc else None
            policies_out.append(item)
        return {
            "policies": policies_out,
            "warnings": policy_overlap_warnings([_policy_row_for_overlap(r) for r in rows]),
        }
    finally:
        db.close()


@router.post("/api/clients/{client_id}/policies")
def api_save_client_policies(
    client_id: int,
    req: ClientPolicySaveRequest,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Poliçe listesini idempotent besler — intake sihirbazı ve müvekkil kartı kullanır."""
    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
    finally:
        db.close()

    created_by = user.get("preferred_username") or user.get("upn") or user.get("email")
    try:
        result = save_client_policies(
            client_id, [p.model_dump() for p in req.policies], created_by=created_by
        )
    except Exception as e:
        logger.error(f"Error saving client policies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Poliçeler kaydedilemedi. Lütfen tekrar deneyin.") from e
    return {"status": "success", **result}


@router.delete("/api/clients/{client_id}/policies/{policy_id}")
def api_delete_client_policy(
    client_id: int,
    policy_id: int,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        deleted = (
            db.query(models.ClientPolicy)
            .filter(models.ClientPolicy.id == policy_id,
                    models.ClientPolicy.client_id == client_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        if not deleted:
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"status": "success", "message": "Policy deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting policy {policy_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Poliçe silinemedi. Lütfen tekrar deneyin.") from e
    finally:
        db.close()


@router.delete("/api/clients/{client_id}")
def api_delete_client(
    client_id: int,
    reason: str = Query(..., min_length=3, max_length=500),
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Soft-delete: kayıt DB'de kalır, listelerden gizlenir, admin geri alabilir.

    CaseParty.client_id BİLİNÇLİ NULL'lanmaz (eski hard-delete davranışıydı) —
    bağlar kopmadığı için restore sıfır maliyetli; taraf görünümleri zaten
    `p.client.name if p.client else p.name` ile çalışıyor.
    Client.active'e DOKUNULMAZ (kullanıcı-düzenlenebilir "pasif cari" alanı).
    """
    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        from sqlalchemy import func
        client.deleted_at = func.now()
        client.deleted_by = (
            user.get("preferred_username") or user.get("upn") or user.get("email") or "Unknown"
        )
        client.delete_reason = reason.strip()
        db.commit()
        return {"status": "success", "message": "Client archived"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting client {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Müvekkil silinemedi. Lütfen tekrar deneyin.") from e
    finally:
        db.close()
