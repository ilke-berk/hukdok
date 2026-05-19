import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from auth_helpers import get_tenant_owned_client, tenant_filter_clause
from dependencies import get_current_tenant, get_current_user
from schemas import ClientCreate, ClientRead, ClientUpdate
from database import SessionLocal
from managers.admin_manager import add_client
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
            .filter(models.Client.active == True)
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
        raise HTTPException(status_code=500, detail="Müvekkil bilgileri güncellenemedi. Lütfen tekrar deneyin.")
    finally:
        db.close()


@router.delete("/api/clients/{client_id}")
def api_delete_client(
    client_id: int,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        client = get_tenant_owned_client(db, client_id, tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        db.query(models.CaseParty).filter(models.CaseParty.client_id == client_id).update(
            {"client_id": None}, synchronize_session=False
        )

        db.delete(client)
        db.commit()
        return {"status": "success", "message": "Client deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting client {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Müvekkil silinemedi. Lütfen tekrar deneyin.")
    finally:
        db.close()
