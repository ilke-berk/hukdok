"""Admin uçları — soft-delete edilen kayıtların listesi ve geri alma.

Silinen kayıtları görebilen TEK yol burasıdır; tüm kullanıcı-yüzü sorgular
(case_manager, auth_helpers) deleted_at IS NULL filtreler. require_admin
routes/config.py'deki ADMIN_EMAILS tabanlı kontroldür.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from auth_helpers import tenant_filter_clause
from database import SessionLocal
from dependencies import get_current_tenant
from routes.config import require_admin
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/admin/deleted-records")
def api_deleted_records(
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft-delete edilmiş dava + müvekkil kayıtları (en yeni silinen önce)."""
    db = SessionLocal()
    try:
        cases = (
            db.query(models.Case)
            .filter(models.Case.deleted_at.isnot(None))
            .filter(tenant_filter_clause(models.Case, tenant_id))
            .order_by(models.Case.deleted_at.desc())
            .all()
        )
        clients = (
            db.query(models.Client)
            .filter(models.Client.deleted_at.isnot(None))
            .filter(tenant_filter_clause(models.Client, tenant_id))
            .order_by(models.Client.deleted_at.desc())
            .all()
        )
        return {
            "cases": [
                {
                    "id": c.id,
                    "tracking_no": c.tracking_no,
                    "esas_no": c.esas_no,
                    "court": c.court,
                    "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
                    "deleted_by": c.deleted_by,
                    "delete_reason": c.delete_reason,
                }
                for c in cases
            ],
            "clients": [
                {
                    "id": c.id,
                    "name": c.name,
                    "cari_kod": c.cari_kod,
                    "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
                    "deleted_by": c.deleted_by,
                    "delete_reason": c.delete_reason,
                }
                for c in clients
            ],
        }
    finally:
        db.close()


@router.post("/api/admin/restore/{record_type}/{record_id}")
def api_restore_record(
    record_type: str,
    record_id: int,
    user: dict = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft-delete edilmiş kaydı geri alır.

    Dava: deleted_* temizlenir + active=True (silmede False yazılmıştı).
    Müvekkil: yalnız deleted_* temizlenir — active'e DOKUNULMAZ (silme öncesi
    pasiflik durumu korunur; active kullanıcı-düzenlenebilir bir alan).
    Restore'da benzersizlik çakışması olamaz: tracking_no/sistem_no unique
    kısıtları silinen kayıtları da kapsıyordu.
    """
    if record_type not in ("case", "client"):
        raise HTTPException(status_code=400, detail="record_type 'case' veya 'client' olmalı")

    db = SessionLocal()
    try:
        if record_type == "case":
            row = (
                db.query(models.Case)
                .filter(models.Case.id == record_id)
                .filter(models.Case.deleted_at.isnot(None))
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .first()
            )
        else:
            row = (
                db.query(models.Client)
                .filter(models.Client.id == record_id)
                .filter(models.Client.deleted_at.isnot(None))
                .filter(tenant_filter_clause(models.Client, tenant_id))
                .first()
            )
        if not row:
            raise HTTPException(status_code=404, detail="Silinmiş kayıt bulunamadı")

        row.deleted_at = None
        row.deleted_by = None
        row.delete_reason = None
        if isinstance(row, models.Case):
            row.active = True
        db.commit()
        logger.info(
            f"[ADMIN-RESTORE] {record_type} id={record_id} geri alındı "
            f"(by={user.get('preferred_username') or user.get('upn') or user.get('email')})"
        )
        return {"status": "success", "message": "Kayıt geri alındı"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Restore hatası ({record_type}/{record_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Geri alma başarısız. Lütfen tekrar deneyin.") from e
    finally:
        db.close()
