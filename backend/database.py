"""
Database configuration with PostgreSQL and SQLite support.

Environment Variables:
- DATABASE_URL: Full database connection string
  - PostgreSQL: postgresql://user:password@host:port/database
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pathlib import Path
import sys
from datetime import datetime, timedelta
import json
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# Get database URL from environment
# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Enforce PostgreSQL
if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    logger.error("❌ CRITICAL: DATABASE_URL is not set or not a PostgreSQL URL.")
    logger.error("   PostgreSQL is now MANDATORY. SQLite support has been removed.")
    logger.error("   Please set DATABASE_URL in .env file.")
    sys.exit(1)

# PostgreSQL Configuration
logger.info("🐘 Using PostgreSQL database")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Verify connections before using
    pool_size=10,            # Connection pool size
    max_overflow=20,         # Max overflow connections
    pool_recycle=3600,       # Recycle connections after 1 hour
    echo=False               # Set to True for SQL query logging
)


# SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
class Base(DeclarativeBase):
    pass

def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initializes the database: Creates tables if not exist and runs migrations."""
    logger.info("🛠️ Initializing Database...")
    try:
        # Import models here to ensure they are registered in Base.metadata
        import models
        # Create all tables defined in models (including AnalysisCache)
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created/verified.")
        
        # Run additional migrations (column updates etc.)
        check_and_migrate_tables()
    except Exception as e:
        logger.error(f"❌ Database Initialization Failed: {e}")
        # We might want to re-raise here if DB is critical
        raise e

def check_and_migrate_tables():
    """
    Checks if required columns exist, adds them if not.
    Works for both SQLite and PostgreSQL.
    """
    try:
        from sqlalchemy import text, inspect
        
        # Get database type
        db_type = engine.dialect.name
        logger.info(f"Running migrations for {db_type}")
        
        with engine.connect() as conn:
            inspector = inspect(engine)
            
            # 1. SEQUENCE MIGRATION for Lawyers, DocTypes, Statuses
            # ... (Existing logic for sequence)
            for table in ["lawyers", "doctypes", "statuses"]:
                if table not in inspector.get_table_names(): continue
                columns = [col['name'] for col in inspector.get_columns(table)]
                if "sequence" not in columns:
                    try:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN sequence INTEGER DEFAULT 0'))
                        conn.commit()
                        logger.info(f"Added sequence to {table}")
                    except Exception as e: logger.error(f"Migration error for {table}.sequence: {e}")

            # 2. CLIENTS MIGRATION (cari_kod, category)
            if "clients" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("clients")]
                if "cari_kod" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN cari_kod VARCHAR(20)'))
                        conn.commit()
                        logger.info("Added cari_kod to clients")
                    except Exception as e: logger.error(f"Migration error for clients.cari_kod: {e}")
                
                if "category" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN category VARCHAR(50)'))
                        conn.commit()
                        logger.info("Added category to clients")
                    except Exception as e: logger.error(f"Migration error for clients.category: {e}")

                if "birth_year" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN birth_year INTEGER'))
                        conn.commit()
                        logger.info("Added birth_year to clients")
                    except Exception as e: logger.error(f"Migration error for clients.birth_year: {e}")

                if "gender" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN gender VARCHAR(20)'))
                        conn.commit()
                        logger.info("Added gender to clients")
                    except Exception as e: logger.error(f"Migration error for clients.gender: {e}")

                if "specialty" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN specialty VARCHAR(100)'))
                        conn.commit()
                        logger.info("Added specialty to clients")
                    except Exception as e: logger.error(f"Migration error for clients.specialty: {e}")

                if "mobile_phone" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN mobile_phone VARCHAR(50)'))
                        conn.commit()
                        logger.info("Added mobile_phone to clients")
                    except Exception as e: logger.error(f"Migration error for clients.mobile_phone: {e}")

            # 3. CASES MIGRATION (service_type)
            if "cases" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("cases")]
                if "service_type" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE cases ADD COLUMN service_type VARCHAR(20)'))
                        conn.commit()
                        logger.info("Added service_type to cases")
                    except Exception as e: logger.error(f"Migration error for cases.service_type: {e}")

            # 4. CASE_PARTIES MIGRATION (birth_year, gender)
            if "case_parties" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("case_parties")]
                if "birth_year" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_parties ADD COLUMN birth_year INTEGER'))
                        conn.commit()
                        logger.info("Added birth_year to case_parties")
                    except Exception as e: logger.error(f"Migration error for case_parties.birth_year: {e}")
                
                if "gender" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_parties ADD COLUMN gender VARCHAR(20)'))
                        conn.commit()
                        logger.info("Added gender to case_parties")
                    except Exception as e: logger.error(f"Migration error for case_parties.gender: {e}")

    except Exception as e:
        logger.error(f"Global migration error: {e}")


# --- DATABASE MANAGER (Ported from db_manager.py) ---

class DatabaseManager:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_db(self):
        return SessionLocal()

    def get_cache(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves analysis result from DB by hash (PostgreSQL)."""
        from models import AnalysisCache
        db = self._get_db()
        try:
            cache_entry = db.query(AnalysisCache).filter(AnalysisCache.file_hash == file_hash).first()
            if cache_entry and cache_entry.data_json:
                return json.loads(cache_entry.data_json)
            return None
        except Exception as e:
            logger.error(f"DB Read Failed (PG): {e}")
            return None
        finally:
            db.close()

    def save_cache(self, file_hash: str, data: Dict[str, Any]):
        """Saves (Upserts) analysis result to DB (PostgreSQL)."""
        from models import AnalysisCache
        db = self._get_db()
        try:
            timestamp = time.time()
            data["_cache_ts"] = timestamp
            json_str = json.dumps(data, ensure_ascii=False)

            cache_entry = db.query(AnalysisCache).filter(AnalysisCache.file_hash == file_hash).first()
            if cache_entry:
                cache_entry.data_json = json_str
                cache_entry.updated_at = datetime.now()
            else:
                new_entry = AnalysisCache(
                    file_hash=file_hash,
                    data_json=json_str
                )
                db.add(new_entry)
            
            db.commit()
        except Exception as e:
            logger.error(f"DB Save Failed (PG): {e}")
            db.rollback()
        finally:
            db.close()

    def cleanup_cache(self, days: int = None):
        """Removes entries older than 'days'."""
        from models import AnalysisCache
        if days is None:
            days = int(os.getenv("CACHE_EXPIRY_DAYS", "30"))

        cutoff_date = datetime.now() - timedelta(days=days)
        
        db = self._get_db()
        try:
            deleted_count = db.query(AnalysisCache).filter(AnalysisCache.updated_at < cutoff_date).delete()
            db.commit()
            if deleted_count > 0:
                logger.info(f"DB Cleanup: Removed {deleted_count} old entries.")
        except Exception as e:
            logger.error(f"DB Cleanup Failed (PG): {e}")
            db.rollback()
        finally:
            db.close()

# --- CLIENT DATA HELPERS ---

def get_normalized_clients() -> Dict[str, Any]:
    """
    Fetches all clients from DB and normalizes them for FlashText/Search.
    Returns: Dict[normalized_name -> List[original_name]]
    """
    from models import Client
    from client_normalizer import clean_name, PRE_COMPILED_SPLIT_PATTERN

    db = SessionLocal()
    try:
        clients = db.query(Client).filter(Client.active == True).all()
        normalized_map: Dict[str, list] = {}
        for c in clients:
            raw_name = c.name
            parts = PRE_COMPILED_SPLIT_PATTERN.split(raw_name)
            for part in parts:
                cleaned = clean_name(part)
                if cleaned:
                    if cleaned not in normalized_map:
                        normalized_map[cleaned] = []
                    if raw_name not in normalized_map[cleaned]:
                        normalized_map[cleaned].append(raw_name)
        return normalized_map
    except Exception as e:
        logger.error(f"Error fetching normalized clients: {e}")
        return {}
    finally:
        db.close()
