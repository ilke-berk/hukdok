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

                # Excel import alanları (cari_mikro_guncellendi.xlsx)
                new_client_columns = {
                    "il":                  "VARCHAR(100)",
                    "sektor":              "VARCHAR(200)",
                    "yevmiye_no":          "VARCHAR(50)",
                    "noterlik":            "VARCHAR(200)",
                    "vekaletname_tarihi":  "DATE",
                    "vekil_avukatlar":     "TEXT",
                    "gecerlilik_tarihi":   "DATE",
                    "vekalet_no":          "VARCHAR(50)",
                    "buro_vekalet_no":     "VARCHAR(50)",
                }
                for col_name, col_type in new_client_columns.items():
                    if col_name not in columns:
                        try:
                            conn.execute(text(f'ALTER TABLE clients ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                            logger.info(f"Added {col_name} to clients")
                        except Exception as e:
                            logger.error(f"Migration error for clients.{col_name}: {e}")

            # 3. CASES MIGRATION (service_type + new import fields)
            if "cases" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("cases")]
                if "service_type" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE cases ADD COLUMN service_type VARCHAR(20)'))
                        conn.commit()
                        logger.info("Added service_type to cases")
                    except Exception as e: logger.error(f"Migration error for cases.service_type: {e}")

                # New fields for case import (Dava Açılış Excel)
                new_case_columns = {
                    "acceptance_date": "DATE",                    # İş Kabul Tarihi
                    "bureau_type": "VARCHAR(100)",                # Büro Özel Türü
                    "sub_type_extra": "VARCHAR(200)",             # Ek Alt Kırılım
                }
                for col_name, col_type in new_case_columns.items():
                    if col_name not in columns:
                        try:
                            conn.execute(text(f'ALTER TABLE cases ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                            logger.info(f"Added {col_name} to cases")
                        except Exception as e: logger.error(f"Migration error for cases.{col_name}: {e}")

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

            # 5. CASE_DOCUMENTS MIGRATION (case_party_id, sharepoint_url, email_sent, email_error)
            if "case_documents" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("case_documents")]

                if "sharepoint_url" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_documents ADD COLUMN sharepoint_url TEXT'))
                        conn.commit()
                        logger.info("Added sharepoint_url to case_documents")
                    except Exception as e: logger.error(f"Migration error for case_documents.sharepoint_url: {e}")

                if "email_sent" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_documents ADD COLUMN email_sent BOOLEAN'))
                        conn.commit()
                        logger.info("Added email_sent to case_documents")
                    except Exception as e: logger.error(f"Migration error for case_documents.email_sent: {e}")

                if "email_error" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_documents ADD COLUMN email_error TEXT'))
                        conn.commit()
                        logger.info("Added email_error to case_documents")
                    except Exception as e: logger.error(f"Migration error for case_documents.email_error: {e}")

                if "case_party_id" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_documents ADD COLUMN case_party_id INTEGER REFERENCES case_parties(id) ON DELETE SET NULL'))
                        conn.commit()
                        logger.info("Added case_party_id to case_documents")
                        # Backfill: mevcut muvekkil_adi değerlerini case_parties ile eşleştir
                        conn.execute(text("""
                            UPDATE case_documents cd
                            SET case_party_id = cp.id
                            FROM case_parties cp
                            WHERE cd.case_id = cp.case_id
                              AND cd.muvekkil_adi IS NOT NULL
                              AND cd.case_party_id IS NULL
                              AND UPPER(cd.muvekkil_adi) = UPPER(cp.name)
                        """))
                        conn.commit()
                        logger.info("Backfilled case_party_id from muvekkil_adi")
                    except Exception as e: logger.error(f"Migration error for case_documents.case_party_id: {e}")

            # 6. CASE_RELATIONS TABLE
            if "case_relations" not in inspector.get_table_names():
                try:
                    conn.execute(text("""
                        CREATE TABLE case_relations (
                            id SERIAL PRIMARY KEY,
                            source_case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                            target_case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                            relation_type VARCHAR(30) NOT NULL DEFAULT 'ILGILI',
                            note TEXT,
                            created_by VARCHAR(100),
                            created_at TIMESTAMPTZ DEFAULT now(),
                            CONSTRAINT uq_case_relation UNIQUE (source_case_id, target_case_id)
                        )
                    """))
                    conn.execute(text("CREATE INDEX idx_case_relations_source ON case_relations(source_case_id)"))
                    conn.execute(text("CREATE INDEX idx_case_relations_target ON case_relations(target_case_id)"))
                    conn.commit()
                    logger.info("Created case_relations table")
                except Exception as e:
                    logger.error(f"Migration error for case_relations: {e}")

            # 7. CASES TRACKING MIGRATION
            if "cases" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("cases")]

                # Rename eski kolonlar
                rename_map = {
                    "istinaf_tarihi":  "istinaf_basvuru_tarihi",
                    "istinaf_sonucu":  "istinaf_karar_durumu",
                    "temyiz_tarihi":   "temyiz_basvuru_tarihi",
                    "temyiz_sonucu":   "temyiz_karar_durumu",
                }
                for old_name, new_name in rename_map.items():
                    if old_name in columns and new_name not in columns:
                        try:
                            conn.execute(text(f'ALTER TABLE cases RENAME COLUMN {old_name} TO {new_name}'))
                            conn.commit()
                            logger.info(f"Renamed cases.{old_name} → {new_name}")
                        except Exception as e:
                            logger.error(f"Migration rename error for cases.{old_name}: {e}")
                # Kolon listesini yenile
                columns = [col['name'] for col in inspector.get_columns("cases")]

                tracking_columns = {
                    # Mevcut (ilk set)
                    "case_stage":                   "VARCHAR(50)",
                    "dosya_son_durumu":             "VARCHAR(100)",
                    "karar_tarihi":                 "DATE",
                    "karar_turu":                   "VARCHAR(50)",
                    "karar_lehine":                 "VARCHAR(20)",
                    "istinaf_basvuru_tarihi":        "DATE",
                    "istinaf_karar_durumu":          "VARCHAR(100)",
                    "istinaf_karar_tarihi":          "DATE",
                    "temyiz_basvuru_tarihi":         "DATE",
                    "temyiz_karar_durumu":           "VARCHAR(100)",
                    "temyiz_karar_tarihi":           "DATE",
                    "kesinlesme_tarihi":             "DATE",
                    "infaz_tarihi":                  "DATE",
                    # Yeni — Yerel Karar
                    "karar_no":                     "VARCHAR(50)",
                    "karar_teblig_tarihi":          "DATE",
                    "karar_aciklama":               "TEXT",
                    # Yeni — İstinaf
                    "istinaf_mahkemesi":            "VARCHAR(200)",
                    "istinaf_esas_no":              "VARCHAR(50)",
                    "istinaf_karar_no":             "VARCHAR(50)",
                    "istinaf_karar_aciklama":       "TEXT",
                    "istinaf_teblig_tarihi":        "DATE",
                    # Yeni — Temyiz
                    "temyiz_mahkemesi":             "VARCHAR(200)",
                    "temyiz_esas_no":               "VARCHAR(50)",
                    "temyiz_karar_no":              "VARCHAR(50)",
                    "temyiz_eden_durumu":           "VARCHAR(100)",
                    "temyiz_karar_aciklama":        "TEXT",
                    "temyiz_teblig_tarihi":         "DATE",
                    # Yeni — Karar Düzeltme
                    "karar_duzeltme_durumu":        "VARCHAR(100)",
                    "karar_duzeltme_esas_no":       "VARCHAR(50)",
                    "karar_duzeltme_karar_no":      "VARCHAR(50)",
                    "karar_duzeltme_tarihi":        "DATE",
                    "karar_duzeltme_teblig_tarihi": "DATE",
                    "karar_duzeltme_aciklama":      "TEXT",
                    "yeni_esas_no":                 "VARCHAR(100)",
                }
                for col_name, col_type in tracking_columns.items():
                    if col_name not in columns:
                        try:
                            conn.execute(text(f'ALTER TABLE cases ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                            logger.info(f"Added {col_name} to cases")
                        except Exception as e:
                            logger.error(f"Migration error for cases.{col_name}: {e}")

            # 8. EXCEL IMPORT ALANLARI (BIRLESIK_SONUC_v5)
            if "cases" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("cases")]
                excel_import_columns = {
                    "klasor_no_2":    "TEXT",           # Eski sistem no — gizli, aranabilir
                    "atama_tarihi":   "DATE",          # Atama Tarihi
                    "hasar_dosya_no": "VARCHAR(200)",  # Hasar Dosya Numarası
                    "hukuk_no":       "VARCHAR(100)",  # Hukuk Numarası
                }
                for col_name, col_type in excel_import_columns.items():
                    if col_name not in columns:
                        try:
                            conn.execute(text(f'ALTER TABLE cases ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                            logger.info(f"Added {col_name} to cases")
                        except Exception as e:
                            logger.error(f"Migration error for cases.{col_name}: {e}")

            # 8b. HEARING_DATES MIGRATION (hearing_time)
            if "hearing_dates" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("hearing_dates")]
                if "hearing_time" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE hearing_dates ADD COLUMN hearing_time VARCHAR(10)'))
                        conn.commit()
                        logger.info("Added hearing_time to hearing_dates")
                    except Exception as e:
                        logger.error(f"Migration error for hearing_dates.hearing_time: {e}")

            # 10. TENANT ISOLATION — cases.tenant_id
            if "cases" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("cases")]
                if "tenant_id" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE cases ADD COLUMN tenant_id VARCHAR(100)'))
                        conn.execute(text('CREATE INDEX IF NOT EXISTS idx_cases_tenant ON cases(tenant_id)'))
                        conn.commit()
                        logger.info("Added tenant_id to cases")
                    except Exception as e:
                        logger.error(f"Migration error for cases.tenant_id: {e}")

            # 9. CASE_STAGE_LOGS TABLE
            if "case_stage_logs" not in inspector.get_table_names():
                try:
                    conn.execute(text("""
                        CREATE TABLE case_stage_logs (
                            id SERIAL PRIMARY KEY,
                            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                            stage VARCHAR(50) NOT NULL,
                            changed_at TIMESTAMPTZ DEFAULT NOW(),
                            changed_by VARCHAR(100),
                            source VARCHAR(20) DEFAULT 'MANUAL',
                            note TEXT
                        )
                    """))
                    conn.execute(text("CREATE INDEX idx_stage_logs_case ON case_stage_logs(case_id)"))
                    conn.commit()
                    logger.info("Created case_stage_logs table")
                except Exception as e:
                    logger.error(f"Migration error for case_stage_logs: {e}")

            # 11. CASE_DOCUMENTS — uploaded_by_email
            if "case_documents" in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns("case_documents")]
                if "uploaded_by_email" not in columns:
                    try:
                        conn.execute(text('ALTER TABLE case_documents ADD COLUMN uploaded_by_email VARCHAR(200)'))
                        conn.execute(text('CREATE INDEX IF NOT EXISTS idx_case_docs_uploader_email ON case_documents(uploaded_by_email)'))
                        conn.commit()
                        logger.info("Added uploaded_by_email to case_documents")
                    except Exception as e:
                        logger.error(f"Migration error for case_documents.uploaded_by_email: {e}")

            # 12. DAILY_ACTIVITY_REPORTS TABLE
            if "daily_activity_reports" not in inspector.get_table_names():
                try:
                    conn.execute(text("""
                        CREATE TABLE daily_activity_reports (
                            id SERIAL PRIMARY KEY,
                            tenant_id VARCHAR(200),
                            user_email VARCHAR(200) NOT NULL,
                            report_date DATE NOT NULL,
                            total_documents INTEGER DEFAULT 0,
                            mailed_documents INTEGER DEFAULT 0,
                            unmailed_documents INTEGER DEFAULT 0,
                            error_documents INTEGER DEFAULT 0,
                            unmailed_doc_ids TEXT,
                            is_acknowledged BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW(),
                            CONSTRAINT uq_daily_report UNIQUE (user_email, report_date)
                        )
                    """))
                    conn.execute(text("CREATE INDEX idx_daily_reports_user ON daily_activity_reports(user_email, is_acknowledged)"))
                    conn.commit()
                    logger.info("Created daily_activity_reports table")
                except Exception as e:
                    logger.error(f"Migration error for daily_activity_reports: {e}")

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
