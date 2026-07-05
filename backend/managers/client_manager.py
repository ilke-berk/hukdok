"""Müvekkil (Client) yazma işlemleri."""
import logging

from database import SessionLocal
import models

logger = logging.getLogger("AdminManager")


def add_client(data: dict, tenant_id: str = None):
    try:
        db = SessionLocal()
        name = data.get("name", "").strip()
        if not name: return False

        # Mevcut müvekkil (aynı isimde) varsa: yalnızca aynı tenant'a veya legacy NULL'a aitse güncelle.
        existing_q = db.query(models.Client).filter(models.Client.name.ilike(name))
        if tenant_id:
            from sqlalchemy import or_
            existing_q = existing_q.filter(
                or_(models.Client.tenant_id == tenant_id, models.Client.tenant_id.is_(None))
            )
        existing = existing_q.first()
        if existing:
            existing.tc_no = data.get("tc_no")
            existing.phone = data.get("phone")
            existing.email = data.get("email")
            existing.address = data.get("address")
            existing.notes = data.get("notes")
            existing.contact_type = data.get("contact_type", "Client")
            existing.client_type = data.get("client_type")
            existing.category = data.get("category")
            existing.birth_year = data.get("birth_year")
            existing.gender = data.get("gender")
            existing.specialty = data.get("specialty")
            existing.active = True
            db.commit()
            return True

        new_client = models.Client(
            name=name,
            tc_no=data.get("tc_no"),
            phone=data.get("phone"),
            email=data.get("email"),
            address=data.get("address"),
            notes=data.get("notes"),
            contact_type=data.get("contact_type", "Client"),
            client_type=data.get("client_type"),
            category=data.get("category"),
            birth_year=data.get("birth_year"),
            gender=data.get("gender"),
            specialty=data.get("specialty"),
            tenant_id=tenant_id,
            active=True
        )
        db.add(new_client)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Add Client Error: {e}")
        return False
    finally:
        db.close()
