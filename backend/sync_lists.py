import logging
import sys
from datetime import datetime
from sqlalchemy.orm import Session

# Local imports
from database import SessionLocal, engine, Base
import models
from list_manager import (
    get_lawyer_list_from_sharepoint,
    get_status_list_from_sharepoint,
    get_doctype_list_from_sharepoint
)
from sharepoint_muvekkil_manager import get_client_list_from_sharepoint

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SyncManager")

def init_db():
    """Create tables if they don't exist."""
    logger.info("Initializing Database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")

def sync_lawyers(db: Session):
    logger.info("Syncing Lawyers...")
    try:
        lawyers = get_lawyer_list_from_sharepoint()
        if not lawyers:
            logger.warning("No lawyers found in SharePoint.")
            return
            
        count = 0
        for item in lawyers:
            code = item.get("code")
            name = item.get("name")
            
            # Upsert (Update if exists, Insert if new)
            existing = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
            if existing:
                existing.name = name
                existing.active = True
                existing.updated_at = datetime.now()
            else:
                new_record = models.Lawyer(code=code, name=name)
                db.add(new_record)
            count += 1
            
        db.commit()
        logger.info(f"✅ Synced {count} lawyers.")
        log_sync(db, "Lawyers", "SUCCESS", count)
    except Exception as e:
        logger.error(f"❌ Lawyer Sync Failed: {e}")
        db.rollback()
        log_sync(db, "Lawyers", "FAILED", 0)

def sync_doctypes(db: Session):
    logger.info("Syncing DocTypes...")
    try:
        items = get_doctype_list_from_sharepoint()
        if not items:
            logger.warning("No doctypes found.")
            return

        count = 0
        for item in items:
            code = item.get("code")
            name = item.get("name")
            
            existing = db.query(models.DocType).filter(models.DocType.code == code).first()
            if existing:
                existing.name = name
                existing.active = True
                existing.updated_at = datetime.now()
            else:
                new_record = models.DocType(code=code, name=name)
                db.add(new_record)
            count += 1
            
        db.commit()
        logger.info(f"✅ Synced {count} doctypes.")
        log_sync(db, "DocTypes", "SUCCESS", count)
    except Exception as e:
        logger.error(f"❌ DocType Sync Failed: {e}")
        db.rollback()
        log_sync(db, "DocTypes", "FAILED", 0)

def sync_statuses(db: Session):
    logger.info("Syncing Statuses...")
    try:
        items = get_status_list_from_sharepoint()
        if not items:
            logger.warning("No statuses found.")
            return

        count = 0
        for item in items:
            code = item.get("code")
            name = item.get("name")
            
            existing = db.query(models.Status).filter(models.Status.code == code).first()
            if existing:
                existing.name = name
                existing.active = True
                existing.updated_at = datetime.now()
            else:
                new_record = models.Status(code=code, name=name)
                db.add(new_record)
            count += 1
            
        db.commit()
        logger.info(f"✅ Synced {count} statuses.")
        log_sync(db, "Statuses", "SUCCESS", count)
    except Exception as e:
        logger.error(f"❌ Status Sync Failed: {e}")
        db.rollback()
        log_sync(db, "Statuses", "FAILED", 0)

def sync_clients(db: Session):
    logger.info("Syncing Clients (Muvekkil) with Normalization...")
    try:
        from client_normalizer import clean_name, PRE_COMPILED_SPLIT_PATTERN
        import json
        
        # 1. Fetch Raw Data from SharePoint
        items = get_client_list_from_sharepoint()
        if not items:
            logger.warning("No clients found in SharePoint.")
            return

        # 2. Normalize and Aggregate in Memory
        # Map: normalized_name -> { "source_ids": set(), "original_names": set() }
        normalized_map = {}
        
        for item in items:
            sp_id = str(item.get("id"))
            raw_name = item.get("name", "")
            
            if not raw_name:
                continue

            # CLEANUP: Handle if `sp_id` is a JSON string (recursive dump fix)
            sp_ids = [sp_id]
            try:
                # If it looks like a list string "['1', ...]" or "[\"1\", ...]"
                if sp_id.startswith("[") and sp_id.endswith("]"):
                    loaded = json.loads(sp_id)
                    if isinstance(loaded, list):
                        sp_ids = loaded
                    else:
                        sp_ids = [sp_id]
                
                # Recursive cleanup for double encoding like "[\"['1']\"]"
                # Just flatten everything to strings
                final_sp_ids = []
                for x in sp_ids:
                    if isinstance(x, str) and x.startswith("[") and x.endswith("]"):
                        try:
                            inner = json.loads(x)
                            if isinstance(inner, list):
                                final_sp_ids.extend([str(i) for i in inner])
                            else:
                                final_sp_ids.append(str(x))
                        except:
                            final_sp_ids.append(str(x))
                    else:
                        final_sp_ids.append(str(x))
                sp_ids = final_sp_ids

            except Exception:
                pass # Fallback to original sp_id as single item
                
            # Split (e.g. "Ahmet Yılmaz ve Ayşe Demir")
            parts = PRE_COMPILED_SPLIT_PATTERN.split(raw_name)
            
            for part in parts:
                cleaned = clean_name(part)
                if cleaned:
                    if cleaned not in normalized_map:
                        normalized_map[cleaned] = {
                            "source_ids": set(),
                            "original_names": set()
                        }
                    for sid in sp_ids:
                         normalized_map[cleaned]["source_ids"].add(str(sid))
                    normalized_map[cleaned]["original_names"].add(raw_name)

        logger.info(f"Normalization Complete. Reduced {len(items)} raw items to {len(normalized_map)} unique clients.")

        # 3. Upsert to Database
        count = 0
        for name, data in normalized_map.items():
            source_ids_str = json.dumps(list(data["source_ids"]))
            
            existing = db.query(models.Client).filter(models.Client.name == name).first()
            if existing:
                existing.source_ids = source_ids_str
                existing.active = True
                existing.updated_at = datetime.now()
            else:
                new_record = models.Client(name=name, source_ids=source_ids_str)
                db.add(new_record)
            count += 1
            
        # 4. Deactivate clients not in current list (Optional, but good for cleanup)
        # For now, let's just commit the updates
            
        db.commit()
        logger.info(f"✅ Synced {count} normalized clients.")
        log_sync(db, "Clients", "SUCCESS", count)
        
    except Exception as e:
        logger.error(f"❌ Client Sync Failed: {e}")
        db.rollback()
        log_sync(db, "Clients", "FAILED", 0)

def log_sync(db: Session, name, status, count):
    try:
        log = db.query(models.SyncLog).filter(models.SyncLog.list_name == name).first()
        if log:
            log.last_sync = datetime.now()
            log.status = status
            log.item_count = count
        else:
            log = models.SyncLog(list_name=name, status=status, item_count=count)
            db.add(log)
        db.commit()
    except:
        pass

def run_full_sync():
    init_db()
    db = SessionLocal()
    try:
        sync_lawyers(db)
        sync_statuses(db)
        sync_doctypes(db)
        sync_clients(db)
    finally:
        db.close()

if __name__ == "__main__":
    run_full_sync()
