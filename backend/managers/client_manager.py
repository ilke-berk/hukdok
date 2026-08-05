"""Müvekkil (Client) yazma işlemleri."""
import logging
import re
import unicodedata

from database import SessionLocal
import models

logger = logging.getLogger("AdminManager")


def _policy_dedupe_key(police_no, baslangic_tarihi) -> tuple:
    """Poliçe tekilleştirme anahtarı: normalize no + dönem başı.

    Aynı poliçenin ikinci beslemesi (sihirbaz tekrar koşusu, aynı belge iki
    davada) yeni satır AÇMAZ; aynı numaralı yenileme (farklı dönem) ayrı kayıttır.
    services.case_intake._policy_key ile aynı semantik.
    """
    s = str(police_no or "").strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return (re.sub(r"\s+", " ", s), str(baslangic_tarihi or ""))


def save_client_policies(client_id: int, policies: list, created_by: str = None) -> dict:
    """Poliçe listesini müvekkil kaydına idempotent besler (Faz 3).

    policies: [{police_no, police_turu, sigorta_sirketi, baslangic_tarihi,
                bitis_tarihi, retroaktif_tarihi, sigortali_kurum,
                teminat_limiti, source_document}]
    Döner: {"saved": n, "skipped": n} — skipped = zaten kayıtlı (dedupe anahtarı).
    """
    db = SessionLocal()
    try:
        existing = db.query(models.ClientPolicy).filter(
            models.ClientPolicy.client_id == client_id
        ).all()
        existing_keys = {
            _policy_dedupe_key(p.police_no, p.baslangic_tarihi) for p in existing
        }
        saved = skipped = 0
        for p in policies:
            key = _policy_dedupe_key(p.get("police_no"), p.get("baslangic_tarihi"))
            if key in existing_keys:
                skipped += 1
                continue
            existing_keys.add(key)
            db.add(models.ClientPolicy(
                client_id=client_id,
                police_no=p.get("police_no"),
                police_turu=p.get("police_turu"),
                sigorta_sirketi=p.get("sigorta_sirketi"),
                baslangic_tarihi=p.get("baslangic_tarihi"),
                bitis_tarihi=p.get("bitis_tarihi"),
                retroaktif_tarihi=p.get("retroaktif_tarihi"),
                sigortali_kurum=p.get("sigortali_kurum"),
                teminat_limiti=p.get("teminat_limiti"),
                source_document=p.get("source_document"),
                created_by=created_by,
            ))
            saved += 1
        db.commit()
        return {"saved": saved, "skipped": skipped}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def add_client(data: dict, tenant_id: str = None):
    try:
        db = SessionLocal()
        name = data.get("name", "").strip()
        if not name:
            return False

        # Mevcut müvekkil (aynı isimde) varsa: yalnızca aynı tenant'a veya legacy NULL'a aitse güncelle.
        # Soft-delete edilmiş kayıt UPSERT hedefi OLMAZ — aynı isimle yeni kayıt açılır
        # (silinen kayıt sessizce diriltilmesin; geri alma yalnız admin panelinden).
        existing_q = db.query(models.Client).filter(
            models.Client.name.ilike(name),
            models.Client.deleted_at.is_(None),
        )
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
