import logging
from datetime import datetime
from database import SessionLocal
import models
from sqlalchemy.orm import selectinload
from managers.config_manager import DynamicConfig

logger = logging.getLogger("AdminManager")

# --- DATA RETRIEVAL (DB ONLY) ---

def get_lawyers():
    """Retrieves all active lawyers from the local database."""
    try:
        db = SessionLocal()
        try:
            items = db.query(models.Lawyer).filter(models.Lawyer.active == True).order_by(models.Lawyer.sequence.asc()).all()
            return [{"code": i.code, "name": i.name, "tc_no": i.tc_no, "sicil_no": i.sicil_no,
                     "gorev": i.gorev, "email": i.email, "phone": i.phone, "address": i.address} for i in items]
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

def add_lawyer(code: str, name: str, tc_no: str = None, sicil_no: str = None,
               gorev: str = None, email: str = None, phone: str = None, address: str = None):
    try:
        db = SessionLocal()
        new_item = models.Lawyer(code=code, name=name, active=True,
                                 tc_no=tc_no or None, sicil_no=sicil_no or None,
                                 gorev=gorev or None, email=email or None,
                                 phone=phone or None, address=address or None)
        db.add(new_item)
        db.commit()
        refresh_cache("lawyers")
        return True
    except Exception as e:
        logger.error(f"Add Lawyer Error: {e}")
        return False
    finally:
        db.close()

def update_lawyer(code: str, tc_no: str = None, sicil_no: str = None,
                  gorev: str = None, email: str = None, phone: str = None, address: str = None):
    """Updates lawyer fields."""
    try:
        db = SessionLocal()
        item = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
        if not item:
            return False
        if tc_no is not None:
            item.tc_no = tc_no or None
        if sicil_no is not None:
            item.sicil_no = sicil_no or None
        if gorev is not None:
            item.gorev = gorev or None
        if email is not None:
            item.email = email or None
        if phone is not None:
            item.phone = phone or None
        if address is not None:
            item.address = address or None
        db.commit()
        refresh_cache("lawyers")
        return True
    except Exception as e:
        logger.error(f"Update Lawyer Error: {e}")
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

def reorder_list(list_type: str, ordered_ids: list):
    try:
        db = SessionLocal()
        model = None
        if list_type == "lawyers": model = models.Lawyer
        elif list_type == "statuses": model = models.Status
        elif list_type == "doctypes": model = models.DocType
        elif list_type == "emails": model = models.EmailRecipient
        elif list_type == "case_subjects": model = models.CaseSubject
        elif list_type == "file_types": model = models.FileType
        elif list_type == "court_types": model = models.CourtType
        elif list_type == "party_roles": model = models.PartyRole
        elif list_type == "bureau_types": model = models.BureauType
        elif list_type == "cities": model = models.City
        elif list_type == "specialties": model = models.Specialty
        elif list_type == "client_categories": model = models.ClientCategory
        elif list_type == "file_statuses": model = models.FileStatus

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

def _apply_tenant_filter(query, tenant_id: str):
    """Sorguya tenant izolasyon filtresi uygular.
    tenant_id'si NULL olan kayıtlar (eski/migrasyon öncesi) her tenant'a görünür.
    """
    if tenant_id:
        from sqlalchemy import or_
        return query.filter(
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        )
    return query


def get_case(case_id: int, tenant_id: str = None):
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        item = query.first()
        if not item: return None
        
        # Build response with parties and history
        result = {
            "id": item.id,
            "tracking_no": item.tracking_no,
            "esas_no": item.esas_no,
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
            "acceptance_date": item.acceptance_date.isoformat() if item.acceptance_date else None,
            "bureau_type": item.bureau_type,
            "sub_type_extra": item.sub_type_extra,
            "atama_tarihi": item.atama_tarihi.isoformat() if item.atama_tarihi else None,
            "hasar_dosya_no": item.hasar_dosya_no,
            "hukuk_no": item.hukuk_no,
            "klasor_no_2": item.klasor_no_2,
            "notes": item.notes,
            "parties": [{"id": p.id, "name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender} for p in item.parties],
            "lawyers": [{"name": l.name, "lawyer_id": l.lawyer_id} for l in item.lawyers],
            "history": [{"field": h.field_name, "old": h.old_value, "new": h.new_value, "date": h.changed_at.isoformat()} for h in sorted(item.history, key=lambda x: x.changed_at, reverse=True)],
            "documents": [{"id": d.id, "original_filename": d.original_filename, "stored_filename": d.stored_filename, "sharepoint_url": d.sharepoint_url, "belge_turu_kodu": d.belge_turu_kodu, "belge_turu_adi": d.belge_turu_adi, "ai_summary": d.ai_summary, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None, "case_party_id": d.case_party_id, "case_party_name": d.case_party.name if d.case_party else None} for d in item.documents],
            # Takip alanları
            "case_stage": item.case_stage,
            "dosya_son_durumu": item.dosya_son_durumu,
            "karar_tarihi": item.karar_tarihi.isoformat() if item.karar_tarihi else None,
            "karar_turu": item.karar_turu,
            "karar_lehine": item.karar_lehine,
            "karar_no": item.karar_no,
            "karar_teblig_tarihi": item.karar_teblig_tarihi.isoformat() if item.karar_teblig_tarihi else None,
            "karar_aciklama": item.karar_aciklama,
            "istinaf_basvuru_tarihi": item.istinaf_basvuru_tarihi.isoformat() if item.istinaf_basvuru_tarihi else None,
            "istinaf_karar_durumu": item.istinaf_karar_durumu,
            "istinaf_karar_tarihi": item.istinaf_karar_tarihi.isoformat() if item.istinaf_karar_tarihi else None,
            "istinaf_mahkemesi": item.istinaf_mahkemesi,
            "istinaf_esas_no": item.istinaf_esas_no,
            "istinaf_karar_no": item.istinaf_karar_no,
            "istinaf_karar_aciklama": item.istinaf_karar_aciklama,
            "istinaf_teblig_tarihi": item.istinaf_teblig_tarihi.isoformat() if item.istinaf_teblig_tarihi else None,
            "temyiz_basvuru_tarihi": item.temyiz_basvuru_tarihi.isoformat() if item.temyiz_basvuru_tarihi else None,
            "temyiz_karar_durumu": item.temyiz_karar_durumu,
            "temyiz_karar_tarihi": item.temyiz_karar_tarihi.isoformat() if item.temyiz_karar_tarihi else None,
            "temyiz_mahkemesi": item.temyiz_mahkemesi,
            "temyiz_esas_no": item.temyiz_esas_no,
            "temyiz_karar_no": item.temyiz_karar_no,
            "temyiz_eden_durumu": item.temyiz_eden_durumu,
            "temyiz_karar_aciklama": item.temyiz_karar_aciklama,
            "temyiz_teblig_tarihi": item.temyiz_teblig_tarihi.isoformat() if item.temyiz_teblig_tarihi else None,
            "karar_duzeltme_durumu": item.karar_duzeltme_durumu,
            "karar_duzeltme_esas_no": item.karar_duzeltme_esas_no,
            "karar_duzeltme_karar_no": item.karar_duzeltme_karar_no,
            "karar_duzeltme_tarihi": item.karar_duzeltme_tarihi.isoformat() if item.karar_duzeltme_tarihi else None,
            "karar_duzeltme_teblig_tarihi": item.karar_duzeltme_teblig_tarihi.isoformat() if item.karar_duzeltme_teblig_tarihi else None,
            "karar_duzeltme_aciklama": item.karar_duzeltme_aciklama,
            "yeni_esas_no": item.yeni_esas_no,
            "kesinlesme_tarihi": item.kesinlesme_tarihi.isoformat() if item.kesinlesme_tarihi else None,
            "infaz_tarihi": item.infaz_tarihi.isoformat() if item.infaz_tarihi else None,
        }
        return result
    except Exception as e:
        logger.error(f"Get Case Error: {e}")
        return None
    finally:
        db.close()

def get_case_stats(tenant_id: str = None):
    from sqlalchemy import func
    try:
        db = SessionLocal()
        stats = {"total": 0, "active": 0, "closed": 0, "appeal": 0, "danis_active": 0, "statuses": {}}
        base_query = db.query(models.Case.status, func.count(models.Case.id)).filter(models.Case.active == True)
        base_query = _apply_tenant_filter(base_query, tenant_id)
        counts = base_query.group_by(models.Case.status).all()

        for status, count in counts:
            stats["total"] += count
            stats["statuses"][status] = count

            s = (status or "").upper()
            if s == "DERDEST":
                stats["active"] += count
            elif s in ("KAPALI", "MAHZEN"):
                stats["closed"] += count
            elif s == "TEMYIZ":
                stats["appeal"] += count

        for status, count in stats["statuses"].items():
            if (status or "").upper().startswith("DANI"):
                stats["danis_active"] += count

        return stats
    except Exception as e:
        logger.error(f"Get Case Stats Error: {e}")
        return {"total": 0, "active": 0, "closed": 0, "appeal": 0, "danis_active": 0, "statuses": {}}
    finally:
        db.close()

def get_cases(limit: int = 50, offset: int = 0, status: str = None, lawyer: str = None, q: str = None, exact: bool = False, tenant_id: str = None):
    try:
        db = SessionLocal()
        query = db.query(models.Case).options(
            selectinload(models.Case.parties),
            selectinload(models.Case.lawyers)
        ).filter(models.Case.active == True)
        query = _apply_tenant_filter(query, tenant_id)

        if status and status != "ALL":
            query = query.filter(models.Case.status == status)
        
        if lawyer and lawyer != "ALL":
            # Search in responsible_lawyer_name or in case_lawyers relationship
            from sqlalchemy import or_
            lawyer_pattern = f"%{lawyer}%"
            query = query.filter(or_(
                models.Case.responsible_lawyer_name.ilike(lawyer_pattern),
                models.Case.lawyers.any(models.CaseLawyer.name.ilike(lawyer_pattern))
            ))

        min_len = 1 if exact else 2
        if q and len(q) >= min_len:
            from sqlalchemy import or_, and_
            terms = q.strip().split()
            term_filters = []

            for term in terms:
                if not exact and len(term) < 2: continue
                search_pattern = term if exact else f"%{term}%"

                if exact:
                    # Exact mode: case number fields exact match + tüm diğer alanlar contains
                    contains = f"%{term}%"
                    conditions = [
                        models.Case.esas_no.ilike(search_pattern),
                        models.Case.tracking_no.ilike(search_pattern),
                        models.Case.klasor_no_2.ilike(search_pattern),
                        models.Case.court.ilike(contains),
                        models.Case.subject.ilike(contains),
                        models.Case.responsible_lawyer_name.ilike(contains),
                        models.Case.uyap_lawyer_name.ilike(contains),
                        models.Case.parties.any(models.CaseParty.name.ilike(contains)),
                        models.Case.lawyers.any(models.CaseLawyer.name.ilike(contains)),
                    ]
                else:
                    # Normal mode: search all fields
                    conditions = [
                        models.Case.tracking_no.ilike(search_pattern),
                        models.Case.esas_no.ilike(search_pattern),
                        models.Case.klasor_no_2.ilike(search_pattern),  # Eski sistem no
                        models.Case.court.ilike(search_pattern),
                        models.Case.subject.ilike(search_pattern),
                        models.Case.notes.ilike(search_pattern),
                        models.Case.responsible_lawyer_name.ilike(search_pattern),
                        models.Case.uyap_lawyer_name.ilike(search_pattern),
                        models.Case.parties.any(models.CaseParty.name.ilike(search_pattern)),
                        models.Case.lawyers.any(models.CaseLawyer.name.ilike(search_pattern)),
                        models.Case.history.any(models.CaseHistory.old_value.ilike(search_pattern)),
                    ]

                term_filters.append(or_(*conditions))
            
            if term_filters:
                query = query.filter(and_(*term_filters))

        # Relevance sıralaması: sorgu varsa exact > prefix > partial > diğer
        if q and len(q.strip()) >= min_len:
            from sqlalchemy import case as sa_case
            raw = q.strip()
            relevance = sa_case(
                (models.Case.esas_no.ilike(raw), 1),
                (models.Case.tracking_no.ilike(raw), 1),
                (models.Case.klasor_no_2.ilike(raw), 1),
                (models.Case.esas_no.ilike(f"{raw}%"), 2),
                (models.Case.tracking_no.ilike(f"{raw}%"), 2),
                (models.Case.klasor_no_2.ilike(f"{raw}%"), 2),
                else_=3,
            )
            items = query.order_by(relevance, models.Case.updated_at.desc()).offset(offset).limit(limit).all()
        else:
            items = query.order_by(models.Case.updated_at.desc()).offset(offset).limit(limit).all()
        
        cases_list = []
        for item in items:
            result = {
                "id": item.id,
                "tracking_no": item.tracking_no,
                "esas_no": item.esas_no,
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
                "acceptance_date": item.acceptance_date.isoformat() if item.acceptance_date else None,
                "bureau_type": item.bureau_type,
                "sub_type_extra": item.sub_type_extra,
                "hasar_dosya_no": item.hasar_dosya_no,
                "hukuk_no": item.hukuk_no,
                "parties": [{"id": p.id, "name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender} for p in item.parties],
                "lawyers": [{"name": l.name, "lawyer_id": l.lawyer_id} for l in item.lawyers],
                "created_at": item.created_at.isoformat() if hasattr(item, 'created_at') and item.created_at else None
            }
            cases_list.append(result)
        return cases_list
    except Exception as e:
        logger.error(f"Get Cases Advanced Error: {e}")
        return []
    finally:
        db.close()

def update_case(case_id: int, data: dict, tenant_id: str = None):
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case: return False
        
        # Fields to track for history
        tracked_fields = ["esas_no", "court", "status"]
        
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
        case.bureau_type = data.get("bureau_type", case.bureau_type)
        case.sub_type_extra = data.get("sub_type_extra", case.sub_type_extra)
        case.hasar_dosya_no = data.get("hasar_dosya_no", case.hasar_dosya_no)
        case.hukuk_no = data.get("hukuk_no", case.hukuk_no)
        case.klasor_no_2 = data.get("klasor_no_2", case.klasor_no_2)
        case.notes = data.get("notes", case.notes)

        if data.get("opening_date"):
            try:
                case.opening_date = datetime.strptime(data.get("opening_date"), "%Y-%m-%d").date()
            except: pass

        if data.get("acceptance_date"):
            try:
                case.acceptance_date = datetime.strptime(data.get("acceptance_date"), "%Y-%m-%d").date()
            except: pass

        if data.get("atama_tarihi"):
            try:
                case.atama_tarihi = datetime.strptime(data.get("atama_tarihi"), "%Y-%m-%d").date()
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
                existing_client = db.query(models.Client).filter(
                    models.Client.name.ilike(name.strip())
                ).first()
                if existing_client:
                    client_id = existing_client.id
                else:
                    new_client = models.Client(
                        name=name.strip(),
                        contact_type="Client",
                        client_type="Individual",
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
            
        # 3. Sync Lawyers
        db.query(models.CaseLawyer).filter(models.CaseLawyer.case_id == case_id).delete()
        lawyers = data.get("lawyers", [])
        lawyer_names = []
        for l in lawyers:
            name = l.get("name")
            if name:
                db.add(models.CaseLawyer(
                    case_id=case_id,
                    lawyer_id=l.get("lawyer_id"),
                    name=name
                ))
                lawyer_names.append(name)
        
        # Backward compatibility for existing field
        if lawyer_names:
            case.responsible_lawyer_name = ", ".join(lawyer_names)
            
        case.updated_at = datetime.now()
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Update Case Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def search_cases(query: str, exact: bool = False, active_only: bool = False, tenant_id: str = None):
    status = "DERDEST" if active_only else None
    return get_cases(q=query, limit=500, exact=exact, status=status, tenant_id=tenant_id)

def add_case(data: dict, tenant_id: str = None):
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
            status=data.get("status", "DERDEST"),
            file_type=data.get("file_type"),
            sub_type=data.get("sub_type"),
            subject=data.get("subject"),
            court=data.get("court"),
            opening_date=opening_date,
            responsible_lawyer_name=data.get("responsible_lawyer_name"),
            uyap_lawyer_name=data.get("uyap_lawyer_name"),
            maddi_tazminat=data.get("maddi_tazminat", 0),
            manevi_tazminat=data.get("manevi_tazminat", 0),
            bureau_type=data.get("bureau_type"),
            sub_type_extra=data.get("sub_type_extra"),
            hasar_dosya_no=data.get("hasar_dosya_no"),
            hukuk_no=data.get("hukuk_no"),
            klasor_no_2=data.get("klasor_no_2"),
            notes=data.get("notes"),
        )

        # Handle acceptance_date
        acceptance_date_str = data.get("acceptance_date")
        if acceptance_date_str:
            try:
                new_case.acceptance_date = datetime.strptime(str(acceptance_date_str).strip(), "%Y-%m-%d").date()
            except:
                pass

        # Handle atama_tarihi
        atama_tarihi_str = data.get("atama_tarihi")
        if atama_tarihi_str:
            try:
                new_case.atama_tarihi = datetime.strptime(str(atama_tarihi_str).strip(), "%Y-%m-%d").date()
            except:
                pass

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
                existing_client = db.query(models.Client).filter(
                    models.Client.name.ilike(name.strip())
                ).first()
                if existing_client:
                    client_id = existing_client.id
                else:
                    new_client = models.Client(
                        name=name.strip(),
                        contact_type="Client",
                        client_type="Individual",
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
            
        # 3. Add Lawyers
        lawyers = data.get("lawyers", [])
        lawyer_names = []
        for l in lawyers:
            name = l.get("name")
            if name:
                db.add(models.CaseLawyer(
                    case_id=new_case.id,
                    lawyer_id=l.get("lawyer_id"),
                    name=name
                ))
                lawyer_names.append(name)
                
        # Backward compatibility for existing field
        if lawyer_names and not new_case.responsible_lawyer_name:
            new_case.responsible_lawyer_name = ", ".join(lawyer_names)
            
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

# ─── FILE TYPES ──────────────────────────────────────────────────────────────

def get_file_types():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.FileType).filter(models.FileType.active == True).order_by(models.FileType.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching file_types: {e}")
        return []

def add_file_type(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.FileType(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("file_types")
        return True
    except Exception as e:
        logger.error(f"Add FileType Error: {e}")
        return False
    finally:
        db.close()

def delete_file_type(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.FileType).filter(models.FileType.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("file_types")
            return True
        return False
    finally:
        db.close()

# ─── COURT TYPES ─────────────────────────────────────────────────────────────

def get_court_types(parent_code: str = None):
    try:
        db = SessionLocal()
        try:
            q = db.query(models.CourtType).filter(models.CourtType.active == True)
            if parent_code:
                q = q.filter(models.CourtType.parent_code == parent_code)
            items = q.order_by(models.CourtType.parent_code.asc(), models.CourtType.sequence.asc()).all()
            return [{"code": i.code, "name": i.name, "parent_code": i.parent_code} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching court_types: {e}")
        return []

def add_court_type(code: str, name: str, parent_code: str):
    try:
        db = SessionLocal()
        new_item = models.CourtType(code=code, name=name, parent_code=parent_code, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("court_types")
        return True
    except Exception as e:
        logger.error(f"Add CourtType Error: {e}")
        return False
    finally:
        db.close()

def delete_court_type(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.CourtType).filter(models.CourtType.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("court_types")
            return True
        return False
    finally:
        db.close()

# ─── PARTY ROLES ─────────────────────────────────────────────────────────────

def get_party_roles():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.PartyRole).filter(models.PartyRole.active == True).order_by(models.PartyRole.sequence.asc()).all()
            return [{"code": i.code, "name": i.name, "role_type": i.role_type} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching party_roles: {e}")
        return []

def add_party_role(code: str, name: str, role_type: str = "MAIN"):
    try:
        db = SessionLocal()
        new_item = models.PartyRole(code=code, name=name, role_type=role_type, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("party_roles")
        return True
    except Exception as e:
        logger.error(f"Add PartyRole Error: {e}")
        return False
    finally:
        db.close()

def delete_party_role(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.PartyRole).filter(models.PartyRole.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("party_roles")
            return True
        return False
    finally:
        db.close()

# ─── BUREAU TYPES ─────────────────────────────────────────────────────────────

def get_bureau_types():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.BureauType).filter(models.BureauType.active == True).order_by(models.BureauType.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching bureau_types: {e}")
        return []

def add_bureau_type(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.BureauType(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("bureau_types")
        return True
    except Exception as e:
        logger.error(f"Add BureauType Error: {e}")
        return False
    finally:
        db.close()

def delete_bureau_type(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.BureauType).filter(models.BureauType.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("bureau_types")
            return True
        return False
    finally:
        db.close()

# ─── CITIES ──────────────────────────────────────────────────────────────────

def get_cities():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.City).filter(models.City.active == True).order_by(models.City.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching cities: {e}")
        return []

def add_city(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.City(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("cities")
        return True
    except Exception as e:
        logger.error(f"Add City Error: {e}")
        return False
    finally:
        db.close()

def delete_city(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.City).filter(models.City.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("cities")
            return True
        return False
    finally:
        db.close()

# ─── SPECIALTIES ──────────────────────────────────────────────────────────────

def get_specialties():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.Specialty).filter(models.Specialty.active == True).order_by(models.Specialty.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching specialties: {e}")
        return []

def add_specialty(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.Specialty(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("specialties")
        return True
    except Exception as e:
        logger.error(f"Add Specialty Error: {e}")
        return False
    finally:
        db.close()

def delete_specialty(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.Specialty).filter(models.Specialty.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("specialties")
            return True
        return False
    finally:
        db.close()

# ─── CLIENT CATEGORIES ───────────────────────────────────────────────────────

def get_client_categories():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.ClientCategory).filter(models.ClientCategory.active == True).order_by(models.ClientCategory.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching client_categories: {e}")
        return []

def add_client_category(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.ClientCategory(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("client_categories")
        return True
    except Exception as e:
        logger.error(f"Add ClientCategory Error: {e}")
        return False
    finally:
        db.close()

def delete_client_category(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.ClientCategory).filter(models.ClientCategory.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("client_categories")
            return True
        return False
    finally:
        db.close()

# ─── SEED DATA ───────────────────────────────────────────────────────────────

def seed_all_lists():
    """Seed tüm tabloları başlangıç verileriyle doldurur (yalnızca boşsa)."""
    _seed_file_types()
    _seed_court_types()
    _seed_party_roles()
    _seed_bureau_types()
    _seed_cities()
    _seed_specialties()
    _seed_client_categories()
    _seed_file_statuses()

def _seed_file_types():
    db = SessionLocal()
    try:
        items = [
            ("Ceza",        "Ceza"),
            ("Hukuk",       "Hukuk"),
            ("İcra",        "İcra"),
            ("İdare",       "İdare"),
            ("İdari Yargı", "İdari Yargı"),
            ("Arabuluculuk","Arabuluculuk"),
            ("Savcılık",    "Savcılık"),
            ("Tahkim",      "Tahkim"),
            ("Vergi",       "Vergi"),
            ("Danışmanlık", "Danışmanlık"),
        ]
        added = 0
        for idx, (code, name) in enumerate(items):
            if not db.query(models.FileType).filter_by(code=code).first():
                db.add(models.FileType(code=code, name=name, active=True, sequence=idx))
                added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new file_types")
    except Exception as e:
        logger.error(f"Seed FileTypes Error: {e}")
    finally:
        db.close()

def _seed_court_types():
    db = SessionLocal()
    try:
        data = {
            "Ceza": [
                "AĞIR CEZA MAHKEMESİ", "ASLİYE CEZA MAHKEMESİ",
                "Bölge Adliye Mah. Ceza Dairesi", "ÇOCUK AĞIR CEZA MAHKEMESİ",
                "ÇOCUK MAHKEMESİ", "FİKRİ VE SINAİ HAKLAR CEZA MAHKEMESİ",
                "İCRA CEZA HAKİMLİĞİ", "İNFAZ HAKİMLİĞİ",
                "İSTİNAF CEZA DAİRESİ (İLK DERECE)", "SULH CEZA HAKİMLİĞİ",
                "YARGITAY CEZA DAİRESİ (İLK DERECE)",
            ],
            "Hukuk": [
                "AİLE MAHKEMESİ", "ASLİYE HUKUK MAHKEMESİ", "ASLİYE TİCARET MAHKEMESİ",
                "BAM HUKUK DAİRESİ (İLK DERECE)", "BÖLGE ADLİYE MAH. HUKUK DAİRESİ",
                "FİKRİ VE SINAİ HAKLAR HUKUK MAHKEMESİ", "İCRA HUKUK MAHKEMESİ",
                "İŞ MAHKEMESİ", "KADASTRO MAHKEMESİ", "KADASTRO MAHKEMESİ (MÜŞ)",
                "SULH HUKUK MAHKEMESİ", "TÜKETİCİ MAHKEMESİ",
            ],
            "İcra": ["İCRA DAİRESİ"],
            "İdari Yargı": ["BÖLGE İDARE MAHKEMESİ", "İDARE MAHKEMESİ", "VERGİ MAHKEMESİ"],
            "İdare": ["BÖLGE İDARE MAHKEMESİ", "İDARE MAHKEMESİ", "VERGİ MAHKEMESİ"],
            "Arabuluculuk": ["ARABULUCULUK DAİRE BAŞKANLIĞI", "ARABULUCULUK MERKEZİ"],
            "Savcılık": ["CUMHURİYET BAŞSAVCILIĞI"],
            "Tahkim": ["TAHKIM MAHKEMESİ", "MİLLETLERARASI TAHKİM", "TOBB TAHKİM MAHKEMESİ"],
            "Vergi": ["VERGİ MAHKEMESİ", "BÖLGE İDARE MAHKEMESİ (VERGİ)", "DANIŞTAY"],
            "Danışmanlık": [],
        }
        added = 0
        seq = db.query(models.CourtType).count()
        existing_keys = {
            (r.name, r.parent_code)
            for r in db.query(models.CourtType.name, models.CourtType.parent_code).all()
        }
        for parent, names in data.items():
            for name in names:
                if (name, parent) not in existing_keys:
                    code = (parent[:3] + "-" + name[:6]).upper().replace(" ", "")
                    db.add(models.CourtType(code=f"{code}-{seq}", name=name, parent_code=parent, active=True, sequence=seq))
                    seq += 1
                    added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new court_types")
    except Exception as e:
        logger.error(f"Seed CourtTypes Error: {e}")
    finally:
        db.close()

def _seed_party_roles():
    db = SessionLocal()
    try:
        main_roles = [
            "Davacı", "Davalı", "Müşteki", "Sanık", "İhbar Olunan", "Müdahil",
            "Şüpheli", "Borçlu", "Başvurucu", "Feri Müdahil", "Müdahil Davalı",
        ]
        third_roles = ["Tanık", "Bilirkişi", "Uzman", "Arabulucu", "Diğer"]

        def _norm(name):
            return name.upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")

        existing = {r.name for r in db.query(models.PartyRole).all()}
        seq = db.query(models.PartyRole).count()
        added = 0
        for name in main_roles:
            if name not in existing:
                db.add(models.PartyRole(code=_norm(name), name=name, role_type="MAIN", active=True, sequence=seq))
                seq += 1
                added += 1
        for name in third_roles:
            if name not in existing:
                db.add(models.PartyRole(code="3-" + _norm(name), name=name, role_type="THIRD", active=True, sequence=seq))
                seq += 1
                added += 1
        db.commit()
        if added:
            logger.info(f"Seeded {added} new party_roles")
    except Exception as e:
        logger.error(f"Seed PartyRoles Error: {e}")
    finally:
        db.close()

def _seed_bureau_types():
    db = SessionLocal()
    try:
        if db.query(models.BureauType).count() > 0:
            return
        names = ["ALEYHE", "DR ÖZEL", "HASTANE ÖZEL MÜVEKKİL", "LEXİS", "RÜCU", "VEKALETLİ TAKİP", "VEKALETSİZ TAKİP", "ÖZEL"]
        for idx, name in enumerate(names):
            code = name.replace(" ", "-")
            db.add(models.BureauType(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} bureau_types")
    except Exception as e:
        logger.error(f"Seed BureauTypes Error: {e}")
    finally:
        db.close()

def _seed_cities():
    db = SessionLocal()
    try:
        if db.query(models.City).count() > 0:
            return
        names = [
            "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Artvin",
            "Aydın", "Balıkesir", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa",
            "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Edirne", "Elazığ",
            "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
            "Hatay", "Isparta", "Mersin", "İstanbul", "İzmir", "Kars", "Kastamonu", "Kayseri",
            "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
            "Kahramanmaraş", "Mardin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Rize",
            "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Tekirdağ", "Tokat", "Trabzon",
            "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray", "Bayburt",
            "Karaman", "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan", "Iğdır", "Yalova",
            "Karabük", "Kilis", "Osmaniye", "Düzce", "Delft", "Girne", "London", "Salmiya",
        ]
        import locale
        sorted_names = sorted(names, key=lambda x: x.lower())
        for idx, name in enumerate(sorted_names):
            code = name.upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("I", "I")
            db.add(models.City(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} cities")
    except Exception as e:
        logger.error(f"Seed Cities Error: {e}")
    finally:
        db.close()

def _seed_specialties():
    db = SessionLocal()
    try:
        if db.query(models.Specialty).count() > 0:
            return
        names = [
            "Acil Tıp", "Aile Hekimliği", "Anesteziyoloji ve Reanimasyon", "Ağız ve Diş Sağlığı",
            "Beyin ve Sinir Cerrahisi (Nöroşirurji)", "Deri ve Zührevi Hastalıkları", "Diş Tabibi",
            "Enfeksiyon Hastalıkları ve Klinik Mikrobiyoloji", "Fiziksel Tıp ve Rehabilitasyon",
            "Gastroenteroloji", "Genel Cerrahisi", "Göz Hastalıkları", "Göğüs Cerrahisi",
            "Göğüs Hastalıkları", "Hematoloji", "Kadın Hastalıkları ve Doğum",
            "Kalp ve Damar Cerrahisi", "Kardiyoloji", "Kulak Burun Boğaz Hastalıkları",
            "Nefroloji", "Nöroloji", "Ortodonti", "Ortopedi ve Travmatoloji", "Perinatoloji",
            "Plastik Rekonstrüktif ve Estetik Cerrahi", "Pratisyen Tabip",
            "Radyasyon Onkolojisi", "Radyoloji (Radyodiyagnostik)", "Ruh Sağlığı ve Hastalıkları",
            "Spor Hekimliği", "Sualtı Hekimliği ve Hiperbarik Tip", "Tıbbi Biyokimya",
            "Tıbbi Patoloji", "Yoğun Bakım", "Çocuk Acil", "Çocuk Cerrahisi",
            "Çocuk Endokrinolojisi", "Çocuk Enfeksiyon Hastalıkları",
            "Çocuk Hematolojisi ve Onkolojisi", "Çocuk Nörolojisi",
            "Çocuk Sağlığı ve Hastalıkları", "Çocuk Ürolojisi", "Üroloji",
            "İç Hastalıkları", "Adli Tıp",
        ]
        sorted_names = sorted(names, key=lambda x: x.lower())
        for idx, name in enumerate(sorted_names):
            code = name[:20].upper().replace(" ", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C").replace("(", "").replace(")", "")
            db.add(models.Specialty(code=f"{code}-{idx}", name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} specialties")
    except Exception as e:
        logger.error(f"Seed Specialties Error: {e}")
    finally:
        db.close()

def _seed_client_categories():
    db = SessionLocal()
    try:
        if db.query(models.ClientCategory).count() > 0:
            return
        items = [
            ("DOKTOR", "Doktor"),
            ("KURUM", "Kurum"),
            ("OZEL-HASTANE", "Özel Hastane"),
            ("BIREYSEL", "Bireysel"),
            ("SIGORTA", "Sigorta Şirketi"),
            ("DIGER", "Diğer"),
        ]
        for idx, (code, name) in enumerate(items):
            db.add(models.ClientCategory(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(items)} client_categories")
    except Exception as e:
        logger.error(f"Seed ClientCategories Error: {e}")
    finally:
        db.close()


# ─── FILE STATUSES ────────────────────────────────────────────────────────────

def get_file_statuses():
    try:
        db = SessionLocal()
        try:
            items = db.query(models.FileStatus).filter(models.FileStatus.active == True).order_by(models.FileStatus.sequence.asc()).all()
            return [{"code": i.code, "name": i.name} for i in items]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error fetching file_statuses: {e}")
        return []

def add_file_status(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.FileStatus(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        refresh_cache("file_statuses")
        return True
    except Exception as e:
        logger.error(f"Add FileStatus Error: {e}")
        return False
    finally:
        db.close()

def delete_file_status(code: str):
    try:
        db = SessionLocal()
        item = db.query(models.FileStatus).filter(models.FileStatus.code == code).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache("file_statuses")
            return True
        return False
    finally:
        db.close()

def _seed_file_statuses():
    db = SessionLocal()
    try:
        if db.query(models.FileStatus).count() > 0:
            return
        names = [
            "Aciz Vesikası", "Azil", "Bekletici Mesele/Ceza-Hukuk Dosyası",
            "Bekletici Mesele/MSK", "Bilirkişi Kusur Raporu Alındı",
            "Bilirkişi Maluliyet Raporu Alındı", "Bilirkişi Tazminat Raporu Alındı",
            "Bilirkişide", "Birleşme", "Bozma Sonrası Yargılama",
            "Dava Açılması Bekleniyor", "Davaya Dönüştü", "Deliller Toplanıyor",
            "Islah", "İade", "İncelemede", "İnfaz Haricen", "İnfaz İcradan",
            "İstifa", "İstinafta", "Kanun Yararına Bozmada",
            "Kapama Müvekkil Talimatıyla", "Karar Düzeltmede",
            "Karar Kesinleşmesi Bekleniyor", "Karar Tebliği Bekleniyor",
            "Karar Yazımı Bekleniyor", "Kesin Aleyhe", "Kesin Lehe",
            "Lexis Rapor Gönderildi", "Lexis Rapor Hazırlanıyor", "Müvekkil Vefatı",
            "Ön İnceleme", "Sözlü Yargılama", "Sulh İle Kapatma", "Tanık",
            "Tehiri İcra", "Temyizde", "Uyuşmazlık Mahkemesinde",
        ]
        for idx, name in enumerate(names):
            code = name.upper().replace(" ", "-").replace("/", "-").replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")
            db.add(models.FileStatus(code=code, name=name, active=True, sequence=idx))
        db.commit()
        logger.info(f"Seeded {len(names)} file_statuses")
    except Exception as e:
        logger.error(f"Seed FileStatuses Error: {e}")
    finally:
        db.close()


# ─── UTILITIES ───────────────────────────────────────────────────────────────

def update_case_tracking(case_id: int, data: dict, changed_by: str, source: str = "MANUAL", tenant_id: str = None) -> bool:
    """Dava takip bilgilerini günceller ve aşama değişmişse CaseStageLog kaydı ekler."""
    db = SessionLocal()
    try:
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return False

        old_stage = case.case_stage
        new_stage = data.get("case_stage")
        note = data.pop("note", None)

        tracking_fields = [
            "case_stage",
            "dosya_son_durumu",
            # Dosya durumu
            "status",
            # Yerel Karar
            "karar_tarihi", "karar_turu", "karar_lehine",
            "karar_no", "karar_teblig_tarihi", "karar_aciklama",
            # İstinaf
            "istinaf_basvuru_tarihi", "istinaf_karar_durumu", "istinaf_karar_tarihi",
            "istinaf_mahkemesi", "istinaf_esas_no", "istinaf_karar_no",
            "istinaf_karar_aciklama", "istinaf_teblig_tarihi",
            # Temyiz
            "temyiz_basvuru_tarihi", "temyiz_karar_durumu", "temyiz_karar_tarihi",
            "temyiz_mahkemesi", "temyiz_esas_no", "temyiz_karar_no",
            "temyiz_eden_durumu", "temyiz_karar_aciklama", "temyiz_teblig_tarihi",
            # Karar Düzeltme
            "karar_duzeltme_durumu", "karar_duzeltme_esas_no", "karar_duzeltme_karar_no",
            "karar_duzeltme_tarihi", "karar_duzeltme_teblig_tarihi",
            "karar_duzeltme_aciklama", "yeni_esas_no",
            # Kesinleşme / İnfaz
            "kesinlesme_tarihi", "infaz_tarihi",
        ]
        for field in tracking_fields:
            if field in data and data[field] is not None:
                setattr(case, field, data[field])

        if new_stage and new_stage != old_stage:
            log = models.CaseStageLog(
                case_id=case_id,
                stage=new_stage,
                changed_by=changed_by,
                source=source,
                note=note,
            )
            db.add(log)

        db.commit()
        return True
    except Exception as e:
        logger.error(f"update_case_tracking error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_case_stage_log(case_id: int, tenant_id: str = None) -> list:
    """Davanın aşama tarihçesini döner. tenant_id verilirse, dava o tenant'a (veya legacy NULL'a) ait değilse boş liste döner."""
    db = SessionLocal()
    try:
        # Önce davanın bu tenant tarafından görülebildiğini doğrula
        case_q = db.query(models.Case).filter(models.Case.id == case_id)
        case_q = _apply_tenant_filter(case_q, tenant_id)
        if not case_q.first():
            return []

        logs = (
            db.query(models.CaseStageLog)
            .filter(models.CaseStageLog.case_id == case_id)
            .order_by(models.CaseStageLog.changed_at.asc())
            .all()
        )
        return logs
    except Exception as e:
        logger.error(f"get_case_stage_log error: {e}")
        return []
    finally:
        db.close()


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
        config.set_case_subjects(get_case_subjects())
    elif list_type == "file_types":
        config.set_file_types(get_file_types())
    elif list_type == "court_types":
        config.set_court_types(get_court_types())
    elif list_type == "party_roles":
        config.set_party_roles(get_party_roles())
    elif list_type == "bureau_types":
        config.set_bureau_types(get_bureau_types())
    elif list_type == "cities":
        config.set_cities(get_cities())
    elif list_type == "specialties":
        config.set_specialties(get_specialties())
    elif list_type == "client_categories":
        config.set_client_categories(get_client_categories())
    elif list_type == "file_statuses":
        config.set_file_statuses(get_file_statuses())
