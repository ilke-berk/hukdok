import logging
import requests
from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, GRAPH, _headers, _load_env

# DB Imports
from database import SessionLocal
import models

# Logger kurulumu
logger = logging.getLogger("ListManager")


def get_lawyer_list_from_sharepoint():
    """
    Retrieves lawyers from the local database.
    Falls back to SharePoint if DB is empty or fails.
    Returns:
        list: [{'code': 'AGH', 'name': 'Ayşe...'}, ...]
    """
    try:
        db = SessionLocal()
        try:
            lawyers_db = db.query(models.Lawyer).filter(models.Lawyer.active == True).all()
            if lawyers_db:
                result = [{"code": l.code, "name": l.name} for l in lawyers_db]
                logger.info(f"ListManager: {len(result)} lawyers loaded from DATABASE.")
                return result
        except Exception as db_e:
            logger.error(f"ListManager DB Error: {db_e}")
        finally:
            db.close()
            
        return []

    except Exception as e:
        logger.error(f"ListManager HATA: {e}")
        return []

def _fetch_lawyers_direct_sharepoint():
    """Direct SharePoint fetch (Legacy)."""
    _load_env()
    LIST_NAME = "AvukatListesi"
    lawyers = []
    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor (Online)...")
        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)
        
        # 1. Listeyi Bul
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()
        lists = r.json().get("value", [])
        target_list_id = None
        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break
        if not target_list_id: return []
        
        # 2. Öğeleri Çek
        items_url = f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()
        items = r.json().get("value", [])
        for item in items:
            fields = item.get("fields", {})
            name = fields.get("Title")
            code = fields.get("kKisaKod")
            if name and code:
                lawyers.append({"code": code, "name": name})
        logger.info(f"ListManager: {len(lawyers)} avukat SharePoint'ten çekildi.")
        return lawyers
    except Exception as e:
        logger.error(f"SharePoint Fetch Error: {e}")
        return []


def get_status_list_from_sharepoint():
    """
    Retrieves statuses from the local database.
    Returns:
        list: [{'code': 'B', 'name': 'Büro...'}, ...]
    """
    try:
        db = SessionLocal()
        try:
            items_db = db.query(models.Status).filter(models.Status.active == True).all()
            if items_db:
                result = [{"code": i.code, "name": i.name} for i in items_db]
                logger.info(f"ListManager: {len(result)} statuses loaded from DATABASE.")
                return result
        except Exception as db_e:
            logger.error(f"ListManager DB Error (Status): {db_e}")
        finally:
            db.close()
            
        return []

    except Exception as e:
        logger.error(f"ListManager Status HATA: {e}")
        return []

def _fetch_statuses_direct_sharepoint():
    _load_env()
    LIST_NAME = "durum"
    statuses = []
    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor (Online)...")
        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)
        
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()
        lists = r.json().get("value", [])
        target_list_id = None
        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break
        if not target_list_id: return []
        
        items_url = f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()
        items = r.json().get("value", [])
        for item in items:
            fields = item.get("fields", {})
            name = fields.get("Title")
            code = (fields.get("Kod") or fields.get("OData__x004b_od") or fields.get("KisaKod") or fields.get("Kisakod"))
            if name and code:
                statuses.append({"code": code, "name": name})
        return statuses
    except Exception as e:
        logger.error(f"Status Fetch Error: {e}")
        return []


def get_doctype_list_from_sharepoint():
    """
    Retrieves doctypes from the local database.
    Returns:
        list: [{'code': 'DAVA-DLK', 'name': 'Dava Dilekçesi'}, ...]
    """
    try:
        db = SessionLocal()
        try:
            items_db = db.query(models.DocType).filter(models.DocType.active == True).all()
            if items_db:
                result = [{"code": i.code, "name": i.name} for i in items_db]
                logger.info(f"ListManager: {len(result)} doctypes loaded from DATABASE.")
                return result
        except Exception as db_e:
            logger.error(f"ListManager DB Error (DocType): {db_e}")
        finally:
            db.close()
            
        return []

    except Exception as e:
        logger.error(f"ListManager DocType HATA: {e}")
        return []

def _fetch_doctypes_direct_sharepoint():
    _load_env()
    LIST_NAME = "BelgeTuru"
    doctypes = []
    try:
        logger.info(f"ListManager: '{LIST_NAME}' verisi çekiliyor (Online)...")
        token = get_graph_token()
        site_id, _ = _get_site_and_drive_id(token)
        headers = _headers(token)
        
        r = requests.get(f"{GRAPH}/sites/{site_id}/lists", headers=headers)
        r.raise_for_status()
        lists = r.json().get("value", [])
        target_list_id = None
        for lst in lists:
            if lst.get("displayName") == LIST_NAME or lst.get("name") == LIST_NAME:
                target_list_id = lst["id"]
                break
        if not target_list_id: return []
        
        items_url = f"{GRAPH}/sites/{site_id}/lists/{target_list_id}/items?expand=fields"
        r = requests.get(items_url, headers=headers)
        r.raise_for_status()
        items = r.json().get("value", [])
        for item in items:
            fields = item.get("fields", {})
            code = fields.get("Title")
            name = (fields.get("field_1") or fields.get("OrijinalAdi") or fields.get("Aciklama"))
            if code:
                final_name = name if name else code
                doctypes.append({"code": code, "name": final_name})
        return doctypes
    except Exception as e:
        logger.error(f"DocType Fetch Error: {e}")
        return []



# --- CRUD OPERATIONS ---

def add_client(data: dict):
    """
    Adds a new client with extended details.
    data: {name, tc_no, phone, email, address, notes}
    """
    try:
        db = SessionLocal()
        name = data.get("name", "").strip().upper()
        if not name: return False

        # Check existing
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
            existing.active = True
            db.commit()
            logger.info(f"Client updated: {name}")
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
            active=True
        )
        db.add(new_client)
        db.commit()
        logger.info(f"Client added: {name}")
        return True
    except Exception as e:
        logger.error(f"Add Client Error: {e}")
        return False
    finally:
        db.close()

# 1. LAWYER CRUD
def add_lawyer(code: str, name: str):
    try:
        db = SessionLocal()
        new_lawyer = models.Lawyer(code=code, name=name, active=True)
        db.add(new_lawyer)
        db.commit()
        logger.info(f"ListManager: Lawyer added: {code} - {name}")
        
        # Update Cache/Config immediately
        update_lawyer_cache(db)
        return True
    except Exception as e:
        logger.error(f"ListManager Add Lawyer Error: {e}")
        return False
    finally:
        db.close()

def delete_lawyer(code: str):
    try:
        db = SessionLocal()
        lawyer = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
        if lawyer:
            db.delete(lawyer)
            db.commit()
            logger.info(f"ListManager: Lawyer deleted: {code}")
            
            update_lawyer_cache(db)
            return True
        return False
    except Exception as e:
        logger.error(f"ListManager Delete Lawyer Error: {e}")
        return False
    finally:
        db.close()


def update_lawyer_cache(db):
    """Helper to refresh DynamicConfig after DB change."""
    # Order by SEQUENCE
    lawyers_db = db.query(models.Lawyer).filter(models.Lawyer.active == True).order_by(models.Lawyer.sequence.asc()).all()
    if lawyers_db:
        result = [{"code": l.code, "name": l.name} for l in lawyers_db]
        from config_manager import DynamicConfig
        DynamicConfig.get_instance().set_lawyers(result)


# 2. STATUS CRUD
def add_status(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.Status(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        logger.info(f"ListManager: Status added: {code} - {name}")
        update_status_cache(db)
        return True
    except Exception as e:
        logger.error(f"ListManager Add Status Error: {e}")
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
            logger.info(f"ListManager: Status deleted: {code}")
            update_status_cache(db)
            return True
        return False
    except Exception as e:
        logger.error(f"ListManager Delete Status Error: {e}")
        return False
    finally:
        db.close()


def update_status_cache(db):
    # Order by SEQUENCE
    items_db = db.query(models.Status).filter(models.Status.active == True).order_by(models.Status.sequence.asc()).all()
    if items_db:
        result = [{"code": i.code, "name": i.name} for i in items_db]
        from config_manager import DynamicConfig
        DynamicConfig.get_instance().set_statuses(result)


# 3. DOCTYPE CRUD
def add_doctype(code: str, name: str):
    try:
        db = SessionLocal()
        new_item = models.DocType(code=code, name=name, active=True)
        db.add(new_item)
        db.commit()
        logger.info(f"ListManager: DocType added: {code} - {name}")
        update_doctype_cache(db)
        return True
    except Exception as e:
        logger.error(f"ListManager Add DocType Error: {e}")
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
            logger.info(f"ListManager: DocType deleted: {code}")
            update_doctype_cache(db)
            return True
        return False
    except Exception as e:
        logger.error(f"ListManager Delete DocType Error: {e}")
        return False
    finally:
        db.close()


def update_doctype_cache(db):
    # Order by SEQUENCE
    items_db = db.query(models.DocType).filter(models.DocType.active == True).order_by(models.DocType.sequence.asc()).all()
    if items_db:
        result = [{"code": i.code, "name": i.name} for i in items_db]
        from config_manager import DynamicConfig
        DynamicConfig.get_instance().set_doctypes(result)


# 4. EMAIL RECIPIENT CRUD (DB)

def get_email_recipients_from_db():
    """Retrieves email recipients from the local database."""
    try:
        db = SessionLocal()
        try:
            items_db = db.query(models.EmailRecipient).filter(models.EmailRecipient.active == True).order_by(models.EmailRecipient.sequence.asc()).all()
            if items_db:
                result = [{"name": i.name, "email": i.email, "description": i.description} for i in items_db]
                logger.info(f"ListManager: {len(result)} email recipients loaded from DATABASE.")
                return result
        except Exception as db_e:
            logger.error(f"ListManager DB Error (Email): {db_e}")
        finally:
            db.close()
            
        return []

    except Exception as e:
        logger.error(f"ListManager Email HATA: {e}")
        return []

def add_email_recipient(name: str, email: str, description: str = ""):
    try:
        db = SessionLocal()
        # Check duplicate
        existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if existing:
            if not existing.active:
                 # Reactivate if it was deleted
                 existing.active = True
                 existing.name = name
                 existing.description = description
                 db.commit()
                 update_email_cache(db)
                 return True
            return False # Already exists and active
        
        # Get max sequence for appending
        from sqlalchemy import func
        max_seq = db.query(func.max(models.EmailRecipient.sequence)).scalar()
        new_seq = (max_seq if max_seq is not None else -1) + 1

        new_item = models.EmailRecipient(
            name=name, 
            email=email, 
            description=description, 
            active=True,
            sequence=new_seq
        )
        db.add(new_item)
        db.commit()
        
        update_email_cache(db)
        return True
    except Exception as e:
        logger.error(f"ListManager Add Email Error: {e}")
        return False
    finally:
        db.close()

def update_email_cache(db):
    items_db = db.query(models.EmailRecipient).filter(models.EmailRecipient.active == True).order_by(models.EmailRecipient.sequence.asc()).all()
    if items_db:
        result = [{"name": i.name, "email": i.email, "description": i.description} for i in items_db]
        from config_manager import DynamicConfig
        DynamicConfig.get_instance().set_email_recipients(result)


def reorder_list(list_type: str, ordered_ids: list):
    """
    Reorders the specified list based on the provided list of IDs/Codes.
    list_type: 'lawyers', 'statuses', 'doctypes', 'emails'
    ordered_ids: List of codes (or emails) in the new order.
    """
    try:
        if list_type == "emails":
            # Handle DB Types (Now same as others)
            db = SessionLocal()
            try:
                # Iterate and update sequence.
                for idx, email in enumerate(ordered_ids):
                    # Find item by email (unique key for emails)
                    item = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
                    if item:
                        item.sequence = idx
                
                db.commit()
                update_email_cache(db)
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Reorder Email Error: {e}")
                return False
            finally:
                db.close()


        else:
            # Handle Database Types
            db = SessionLocal()
            try:
                model = None
                if list_type == "lawyers": model = models.Lawyer
                elif list_type == "statuses": model = models.Status
                elif list_type == "doctypes": model = models.DocType
                
                if not model:
                    return False

                # Bulk update is complex for ordering logic in simple SQL. 
                # Simplest way: Iterate and update sequence.
                # Since lists are small (<100), this is fine.
                
                # Fetch all relevant items to avoid N queries if possible, but update requires finding.
                # Let's just loop.
                for idx, code in enumerate(ordered_ids):
                    # Find item by code
                    item = db.query(model).filter(model.code == code).first()
                    if item:
                        item.sequence = idx
                
                db.commit()
                
                # Update Cache
                if list_type == "lawyers": update_lawyer_cache(db)
                elif list_type == "statuses": update_status_cache(db)
                elif list_type == "doctypes": update_doctype_cache(db)
                
                return True
            except Exception as e:
                db.rollback()
                logger.error(f"Reorder DB Error: {e}")
                return False
            finally:
                db.close()

    except Exception as e:
        logger.error(f"Reorder General Error: {e}")
        return False

def delete_email_recipient(email: str):
    try:
        db = SessionLocal()
        item = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if item:
            # Soft delete or Hard delete? 
            # Let's do hard delete to match previous behavior, 
            # or soft delete (active=False) if we want to keep history.
            # For now, hard delete is fine for this simple list.
            db.delete(item)
            db.commit()
            update_email_cache(db)
            return True
        return False
    except Exception as e:
        logger.error(f"ListManager Delete Email Error: {e}")
        return False


