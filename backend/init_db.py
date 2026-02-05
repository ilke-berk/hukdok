#!/usr/bin/env python3
"""
Database Initialization Script for Production
Runs on first container startup to populate DB from SharePoint
"""
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DBInit")

def check_db_empty():
    """Check if database is empty (needs initialization)"""
    from database import SessionLocal, DB_PATH
    import models
    
    # Check if DB file exists and has data
    if not DB_PATH.exists():
        logger.info("Database file doesn't exist. Will be created.")
        return True
    
    # Check if tables have data
    db = SessionLocal()
    try:
        lawyer_count = db.query(models.Lawyer).count()
        status_count = db.query(models.Status).count()
        doctype_count = db.query(models.DocType).count()
        
        is_empty = (lawyer_count == 0 and status_count == 0 and doctype_count == 0)
        
        if is_empty:
            logger.info("Database tables are empty. Initialization needed.")
        else:
            logger.info(f"Database has data: {lawyer_count} lawyers, {status_count} statuses, {doctype_count} doctypes")
        
        return is_empty
    finally:
        db.close()

def initialize_database():
    """Initialize database with data from SharePoint"""
    logger.info("=" * 60)
    logger.info("STARTING DATABASE INITIALIZATION")
    logger.info("=" * 60)
    
    try:
        # 1. Create tables
        from database import Base, engine
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created successfully")
        
        # 2. Run full sync from SharePoint
        from sync_lists import sync_lawyers, sync_statuses, sync_doctypes, sync_clients
        from database import SessionLocal
        
        db = SessionLocal()
        try:
            logger.info("Starting data sync from SharePoint...")
            
            sync_lawyers(db)
            sync_statuses(db)
            sync_doctypes(db)
            sync_clients(db)
            
            logger.info("=" * 60)
            logger.info("✅ DATABASE INITIALIZATION COMPLETE")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"❌ Sync failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        # Check if initialization needed
        if check_db_empty():
            success = initialize_database()
            sys.exit(0 if success else 1)
        else:
            logger.info("Database already initialized. Skipping.")
            sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
