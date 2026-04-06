import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from schemas import ClientCreate, ClientRead, ClientUpdate
from database import SessionLocal
from admin_manager import add_client
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/clients")
def api_add_client(client: ClientCreate, user: dict = Depends(get_current_user)):
    success = add_client(client.model_dump())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save client")
    return {"status": "success", "message": "Client saved"}


@router.get("/api/clients", response_model=List[ClientRead])
def get_clients_api(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        clients = (
            db.query(models.Client)
            .filter(models.Client.active == True)
            .order_by(models.Client.name.asc())
            .all()
        )
        return clients
    finally:
        db.close()


@router.put("/api/clients/{client_id}")
def api_update_client(client_id: int, client_data: ClientUpdate, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        client = db.query(models.Client).filter(models.Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        update_data = client_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(client, key, value)

        db.commit()
        db.refresh(client)
        return {"status": "success", "message": "Client updated", "client": client}
    except Exception as e:
        logger.error(f"Error updating client: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/api/clients/{client_id}")
def api_delete_client(client_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        client = db.query(models.Client).filter(models.Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        db.query(models.CaseParty).filter(models.CaseParty.client_id == client_id).update(
            {"client_id": None}, synchronize_session=False
        )

        db.delete(client)
        db.commit()
        return {"status": "success", "message": "Client deleted"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
