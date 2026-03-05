import logging
from datetime import datetime
from database import SessionLocal
import models
from config_manager import DynamicConfig

logger = logging.getLogger("AdminManager")

# --- DATA RETRIEVAL (DB ONLY) ---

def get_lawyers():
    """Retrieves all active lawyers from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.Lawyer).filter(models.Lawyer.active == True).order_by(models.Lawyer.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching lawyers: {e}")
        return []

def get_statuses():
    """Retrieves all active statuses from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.Status).filter(models.Status.active == True).order_by(models.Status.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching statuses: {e}")
        return []

def get_doctypes():
    """Retrieves all active document types from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.DocType).filter(models.DocType.active == True).order_by(models.DocType.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching doctypes: {e}")
        return []

def get_case_subjects():
    """Retrieves all active case subjects from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.CaseSubject).filter(models.CaseSubject.active == True).order_by(models.CaseSubject.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching subjects: {e}")
        return []

def get_email_recipients():
    """Retrieves all active email recipients from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.EmailRecipient).filter(models.EmailRecipient.active == True).order_by(models.EmailRecipient.sequence.asc()).all()
            return [{"name": i.name, "email": i.email, "description": i.description} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        return []

# --- CRUD OPERATIONS ---

def add_lawyer(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.Lawyer(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("lawyers")
        return True
    except Exception as e:
        logger.error(f"Add Lawyer Error: {e}")
        return False
    finally:
        db.close()

def delete_lawyer(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("lawyers")
            return True
        return False
    finally:
        db.close()

def add_status(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.Status(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("statuses")
        return True
    except Exception as e:
        logger.error(f"Add Status Error: {e}")
        return False
    finally:
        db.close()

def delete_status(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.Status).filter(models.Status.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("statuses")
            return True
        return False
    finally:
        db.close()

def add_doctype(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.DocType(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("doctypes")
        return True
    except Exception as e:
        logger.error(f"Add Doctype Error: {e}")
        return False
    finally:
        db.close()

def delete_doctype(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.DocType).filter(models.DocType.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("doctypes")
            return True
        return False
    finally:
        db.close()

def add_email_recipient(name: str, email: str, description: str = ""):
    try:
        db = SessionLocal()
        existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.name = name
                existing.description = description
                db.commit()
                refresh_cache("emails")
                return True
            return False
        
        from sqlalchemy import func
        max_seq = db.query(func.max(models.EmailRecipient.sequence)).scalar()
        new_seq = (max_seq if max_seq is not None else -1) + 1
        
        new_item = models.EmailRecipient(name=name, email=email, description=description, active=True, sequence=new_seq)
        db.add(new_item)
        db.commit()
        refresh_cache("emails")
        return True
    except Exception as e:
        logger.error(f"Add Email Error: {e}")
        return False
    finally:
        db.close()

def delete_email_recipient(email: str):
    try:
        db = SessionLocal()
        item = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("emails")
            return True
        return False
    finally:
        db.close()

def add_case_subject(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.CaseSubject(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("case_subjects")
        return True
    except Exception as e:
        logger.error(f"Add Subject Error: {e}")
        return False
    finally:
        db.close()

def delete_case_subject(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.CaseSubject).filter(models.CaseSubject.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("case_subjects")
            return True
        return False
    finally:
        db.close()

def add_client(data: dict):
    try:
        db = SessionLocal()
        name = data.get("name", "").strip().upper()
        if not name: return False

        existing = db.query(models.Client).filter(models.Client.name == name).first()
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

def reorder_list(list_type: str, ordered_ids: list):
    try:
        db = SessionLocal()
        model = None
        if list_type == "lawyers": model = models.Lawyer
        elif list_type == "statuses": model = models.Status
        elif list_type == "doctypes": model = models.DocType
        elif list_type == "emails": model = models.EmailRecipient
        elif list_type == "case_subjects": model = models.CaseSubject

        if not model: return False

        for idx, identifier in enumerate(ordered_ids):
            # Email list uses 'email' as identifier, others use 'code'
            filter_col = model.email if list_type == "emails" else model.code
            item = db.query(model).filter(filter_col == identifier).first()
            if item:
                item.sequence = idx
        
        db.commit()
        refresh_cache(list_type)
        return True
    except Exception as e:
        logger.error(f"Reorder Error: {e}")
        return False
    finally:
        db.close()

from datetime import datetime, date

def get_case(case_id: int):
    try:
        db = SessionLocal()
        item = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not item: return None
        
        # Build response with parties and history
        result = {
            "id": item.id,
            "tracking_no": item.tracking_no,
            "esas_no": item.esas_no,
            "merci_no": item.merci_no,
            "status": item.status,
            "file_type": item.file_type,
            "sub_type": item.sub_type,
            "subject": item.subject,
            "court": item.court,
            "opening_date": item.opening_date.isoformat() if item.opening_date else None,
            "responsible_lawyer_name": item.responsible_lawyer_name,
            "uyap_lawyer_name": item.uyap_lawyer_name,
            "maddi_tazminat": float(item.maddi_tazminat),
            "manevi_tazminat": float(item.manevi_tazminat),
            "parties": [{"name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender} for p in item.parties],
            "history": [{"field": h.field_name, "old": h.old_value, "new": h.new_value, "date": h.changed_at.isoformat()} for h in sorted(item.history, key=lambda x: x.changed_at, reverse=True)],
            "documents": [{"id": d.id, "original_filename": d.original_filename, "stored_filename": d.stored_filename, "belge_turu_kodu": d.belge_turu_kodu, "belge_turu_adi": d.belge_turu_adi, "ai_summary": d.ai_summary, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None} for d in item.documents]
        }
        return result
    except Exception as e:
        logger.error(f"Get Case Error: {e}")
        return None
    finally:
        db.close()

def get_cases():
    try:
        db = SessionLocal()
        items = db.query(models.Case).filter(models.Case.active == True).order_by(models.Case.created_at.desc()).all()
        cases_list = []
        for item in items:
            result = {
                "id": item.id,
                "tracking_no": item.tracking_no,
                "esas_no": item.esas_no,
                "merci_no": item.merci_no,
                "status": item.status,
                "file_type": item.file_type,
                "sub_type": item.sub_type,
                "subject": item.subject,
                "court": item.court,
                "opening_date": item.opening_date.isoformat() if item.opening_date else None,
                "responsible_lawyer_name": item.responsible_lawyer_name,
                "uyap_lawyer_name": item.uyap_lawyer_name,
                "maddi_tazminat": float(item.maddi_tazminat) if item.maddi_tazminat else 0,
                "manevi_tazminat": float(item.manevi_tazminat) if item.manevi_tazminat else 0,
                "parties": [{"name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender} for p in item.parties],
                "history": [{"field": h.field_name, "old": h.old_value, "new": h.new_value, "date": h.changed_at.isoformat()} for h in sorted(item.history, key=lambda x: x.changed_at, reverse=True)],
                "created_at": getattr(item, 'created_at', None)
            }
            cases_list.append(result)
        return cases_list
    except Exception as e:
        logger.error(f"Get Cases Error: {e}")
        return []
    finally:
        db.close()

def update_case(case_id: int, data: dict):
    try:
        db = SessionLocal()
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case: return False
        
        # Fields to track for history
        tracked_fields = ["esas_no", "court", "status", "merci_no"]
        
        # 1. Update Case and Record History
        for field in tracked_fields:
            new_val = data.get(field)
            old_val = getattr(case, field)
            if new_val is not None and str(new_val) != str(old_val):
                # Add to history
                history_entry = models.CaseHistory(
                    case_id=case_id,
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else "",
                    new_value=str(new_val)
                )
                db.add(history_entry)
                setattr(case, field, new_val)

        # Update non-tracked main fields
        case.file_type = data.get("file_type", case.file_type)
        case.sub_type = data.get("sub_type", case.sub_type)
        case.subject = data.get("subject", case.subject)
        case.responsible_lawyer_name = data.get("responsible_lawyer_name", case.responsible_lawyer_name)
        case.uyap_lawyer_name = data.get("uyap_lawyer_name", case.uyap_lawyer_name)
        case.maddi_tazminat = data.get("maddi_tazminat", case.maddi_tazminat)
        case.manevi_tazminat = data.get("manevi_tazminat", case.manevi_tazminat)
        
        if data.get("opening_date"):
            try:
                case.opening_date = datetime.strptime(data.get("opening_date"), "%Y-%m-%d").date()
            except: pass

        # 2. Sync Parties (Delete and Re-add for simplicity in this version)
        db.query(models.CaseParty).filter(models.CaseParty.case_id == case_id).delete()
        parties = data.get("parties", [])
        for p in parties:
            client_id = p.get("client_id")
            party_type = p.get("party_type")
            name = p.get("name")
            
            # Otomatik Müşteri Oluşturma Yükseltmesi
            if party_type == "CLIENT" and name and not client_id:
                existing_client = db.query(models.Client).filter(models.Client.name == name.strip().upper()).first()
                if existing_client:
                    client_id = existing_client.id
                else:
                    new_client = models.Client(
                        name=name.strip().upper(),
                        contact_type="Client",
                        client_type="Gerçek Kişi",
                        active=True
                    )
                    db.add(new_client)
                    db.flush()
                    client_id = new_client.id

            party = models.CaseParty(
                case_id=case_id,
                client_id=client_id,
                name=name,
                role=p.get("role"),
                party_type=party_type,
                birth_year=p.get("birth_year"),
                gender=p.get("gender")
            )
            db.add(party)
            
        case.updated_at = datetime.now()
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Update Case Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def search_cases(query: str):
    try:
        db = SessionLocal()
        if not query or len(query) < 2: return []
        
        from sqlalchemy import or_
        
        # 1. Search in main Case table
        q = f"%{query}%"
        main_results = db.query(models.Case).filter(
            models.Case.active == True,
            or_(
                models.Case.tracking_no.ilike(q),
                models.Case.esas_no.ilike(q),
                models.Case.merci_no.ilike(q),
                models.Case.court.ilike(q),
                models.Case.responsible_lawyer_name.ilike(q),
                models.Case.uyap_lawyer_name.ilike(q),
                models.Case.notes.ilike(q)
            )
        ).all()
        
        case_ids = {c.id for c in main_results}
        
        # 2. Search in History (for old Esas No, etc.)
        history_results = db.query(models.CaseHistory).filter(
            models.CaseHistory.old_value.ilike(q)
        ).all()
        
        for h in history_results:
            if h.case_id not in case_ids:
                case = db.query(models.Case).filter(models.Case.id == h.case_id, models.Case.active == True).first()
                if case:
                    main_results.append(case)
                    case_ids.add(case.id)

        # 3. Search in Parties (Client name, Counterparty name, etc.)
        party_results = db.query(models.CaseParty).filter(
            models.CaseParty.name.ilike(q)
        ).all()
        
        for p in party_results:
            if p.case_id not in case_ids:
                case = db.query(models.Case).filter(models.Case.id == p.case_id, models.Case.active == True).first()
                if case:
                    main_results.append(case)
                    case_ids.add(case.id)
        
        # Return summary for search results
        return [
            {
                "id": c.id,
                "tracking_no": c.tracking_no,
                "esas_no": c.esas_no,
                "court": c.court,
                "status": c.status
            } for c in main_results
        ]
    except Exception as e:
        logger.error(f"Search Cases Error: {e}")
        return []
    finally:
        db.close()

def add_case(data: dict):
    try:
        db = SessionLocal()
        
        # Handle opening date — çoklu format desteği
        opening_date = None
        date_str = data.get("opening_date")
        if date_str:
            date_str = str(date_str).strip()
            # Deneyeceğimiz tüm formatlar (öncelik sırasına göre)
            DATE_FORMATS = [
                "%Y-%m-%d",   # 2024-12-08  (HTML input type=date)
                "%d.%m.%Y",   # 08.12.2024  (Türkçe standart)
                "%d/%m/%Y",   # 08/12/2024
                "%d%m%Y",     # 08122024    (8 haneli bitişik)
                "%Y%m%d",     # 20241208    (8 haneli ISO bitişik)
                "%d%m%y",     # 081224      (6 haneli, günlük belge)
                "%y%m%d",     # 241208      (6 haneli, YYMMDD)
            ]
            for fmt in DATE_FORMATS:
                try:
                    opening_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not opening_date:
                logger.warning(f"Tarih parse edilemedi, atlanıyor: '{date_str}'")

        # 1. Create Case
        new_case = models.Case(
            tracking_no=data.get("tracking_no"),
            esas_no=data.get("esas_no"),
            merci_no=data.get("merci_no"),
            status=data.get("status", "DERDEST"),
            file_type=data.get("file_type"),
            sub_type=data.get("sub_type"),
            subject=data.get("subject"),
            court=data.get("court"),
            opening_date=opening_date,
            responsible_lawyer_name=data.get("responsible_lawyer_name"),
            uyap_lawyer_name=data.get("uyap_lawyer_name"),
            maddi_tazminat=data.get("maddi_tazminat", 0),
            manevi_tazminat=data.get("manevi_tazminat", 0)
        )
        db.add(new_case)
        db.flush()  # Get the case ID
        
        # 2. Add Parties
        parties = data.get("parties", [])
        for p in parties:
            client_id = p.get("client_id")
            party_type = p.get("party_type")
            name = p.get("name")
            
            # Otomatik Müşteri Oluşturma Yükseltmesi
            if party_type == "CLIENT" and name and not client_id:
                existing_client = db.query(models.Client).filter(models.Client.name == name.strip().upper()).first()
                if existing_client:
                    client_id = existing_client.id
                else:
                    new_client = models.Client(
                        name=name.strip().upper(),
                        contact_type="Client",
                        client_type="Gerçek Kişi",
                        active=True
                    )
                    db.add(new_client)
                    db.flush()
                    client_id = new_client.id

            party = models.CaseParty(
                case_id=new_case.id,
                client_id=client_id,
                name=name,
                role=p.get("role"),
                party_type=party_type,
                birth_year=p.get("birth_year"),
                gender=p.get("gender")
            )
            db.add(party)
            
        db.commit()
        # Return the new case object (for frontend linking)
        return {
            "id": new_case.id,
            "tracking_no": new_case.tracking_no,
            "esas_no": new_case.esas_no,
            "court": new_case.court or "",
            "status": new_case.status,
            "responsible_lawyer_name": new_case.responsible_lawyer_name or "",
        }
    except Exception as e:
        logger.error(f"Add Case Error: {e}")
        db.rollback()
        return None
    finally:
        db.close()

# --- UTILITIES ---

def refresh_cache(list_type: str):
    """Helper to update DynamicConfig singleton without a restart."""
    config = DynamicConfig.get_instance()
    if list_type == "lawyers":
        config.set_lawyers(get_lawyers())
    elif list_type == "statuses":
        config.set_statuses(get_statuses())
    elif list_type == "doctypes":
        config.set_doctypes(get_doctypes())
    elif list_type in ["emails", "email_recipients"]:
        config.set_email_recipients(get_email_recipients())
    elif list_type == "case_subjects":
        # Simplified refresh for subjects
        db = SessionLocal()
        items = db.query(models.CaseSubject).filter(models.CaseSubject.active == True).order_by(models.CaseSubject.sequence.asc()).all()
        config.set_case_subjects([{"code": i.code, "name": i.name} for i in items])
        db.close()
