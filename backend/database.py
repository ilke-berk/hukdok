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
import sys
from datetime import datetime, timedelta
import json
import time
from typing import Dict, Any, Optional

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
    """Initializes the database: Creates tables if not exist and runs migrations.

    Yapısal migrasyon hatası uygulamayı BAŞLATMAZ (sessiz şema sapması yerine
    fail-fast). Yalnızca performans amaçlı adımlar (pg_trgm) non-fatal'dır.
    """
    logger.info("🛠️ Initializing Database...")
    try:
        # Import models here to ensure they are registered in Base.metadata
        # Create all tables defined in models (including AnalysisCache)
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created/verified.")

        # Run additional migrations (column updates etc.)
        check_and_migrate_tables()
    except Exception as e:
        logger.error(f"❌ Database Initialization Failed: {e}")
        raise e


# ─── ŞEMA MİGRASYONLARI (bildirimsel) ────────────────────────────────────────
#
# Sıra önemlidir (rename'ler ilgili kolon eklemelerinden önce gelmeli).
# Op türleri:
#   ("rename",  tablo, {eski_kolon: yeni_kolon})
#   ("columns", tablo, {kolon: DDL | (DDL, [kolon eklendikten sonra çalışacak SQL, ...])})
#   ("table",   tablo, CREATE_SQL, [index SQL, ...])
#   ("index",   tablo, [CREATE INDEX IF NOT EXISTS SQL, ...])  — mevcut tabloya idempotent index
_MIGRATIONS = [
    # 1. SEQUENCE for Lawyers, DocTypes, Statuses
    ("columns", "lawyers",  {"sequence": "INTEGER DEFAULT 0"}),
    ("columns", "doctypes", {"sequence": "INTEGER DEFAULT 0"}),
    ("columns", "statuses", {"sequence": "INTEGER DEFAULT 0"}),

    # 2. CLIENTS (cari_kod, category, demografi + Excel import alanları)
    ("columns", "clients", {
        "cari_kod":           "VARCHAR(20)",
        "category":           "VARCHAR(50)",
        "birth_year":         "INTEGER",
        "gender":             "VARCHAR(20)",
        "specialty":          "VARCHAR(100)",
        "mobile_phone":       "VARCHAR(50)",
        # Excel import alanları (cari_mikro_guncellendi.xlsx)
        "il":                 "VARCHAR(100)",
        "sektor":             "VARCHAR(200)",
        "yevmiye_no":         "VARCHAR(50)",
        "noterlik":           "VARCHAR(200)",
        "vekaletname_tarihi": "DATE",
        "vekil_avukatlar":    "TEXT",
        "gecerlilik_tarihi":  "DATE",
        "vekalet_no":         "VARCHAR(50)",
        "buro_vekalet_no":    "VARCHAR(50)",
    }),

    # 3. CASES (service_type + Dava Açılış Excel alanları)
    ("columns", "cases", {
        "service_type":    "VARCHAR(20)",
        "acceptance_date": "DATE",             # İş Kabul Tarihi
        "bureau_type":     "VARCHAR(100)",     # Büro Özel Türü
        "sub_type_extra":  "VARCHAR(200)",     # Ek Alt Kırılım
    }),

    # 4. CASE_PARTIES (birth_year, gender)
    ("columns", "case_parties", {
        "birth_year": "INTEGER",
        "gender":     "VARCHAR(20)",
    }),

    # 5. CASE_DOCUMENTS (sharepoint_url, email_sent, email_error, case_party_id)
    ("columns", "case_documents", {
        "sharepoint_url": "TEXT",
        "email_sent":     "BOOLEAN",
        "email_error":    "TEXT",
        "case_party_id": (
            "INTEGER REFERENCES case_parties(id) ON DELETE SET NULL",
            # Backfill: mevcut muvekkil_adi değerlerini case_parties ile eşleştir
            ["""
                UPDATE case_documents cd
                SET case_party_id = cp.id
                FROM case_parties cp
                WHERE cd.case_id = cp.case_id
                  AND cd.muvekkil_adi IS NOT NULL
                  AND cd.case_party_id IS NULL
                  AND UPPER(cd.muvekkil_adi) = UPPER(cp.name)
            """],
        ),
    }),

    # 6. CASE_RELATIONS
    ("table", "case_relations", """
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
    """, [
        "CREATE INDEX idx_case_relations_source ON case_relations(source_case_id)",
        "CREATE INDEX idx_case_relations_target ON case_relations(target_case_id)",
    ]),

    # 7. CASES TRACKING — önce eski kolon adları düzeltilir, sonra yeniler eklenir
    ("rename", "cases", {
        "istinaf_tarihi": "istinaf_basvuru_tarihi",
        "istinaf_sonucu": "istinaf_karar_durumu",
        "temyiz_tarihi":  "temyiz_basvuru_tarihi",
        "temyiz_sonucu":  "temyiz_karar_durumu",
    }),
    ("columns", "cases", {
        # Mevcut (ilk set)
        "case_stage":                   "VARCHAR(50)",
        "dosya_son_durumu":             "VARCHAR(100)",
        "karar_tarihi":                 "DATE",
        "karar_turu":                   "VARCHAR(50)",
        "karar_lehine":                 "VARCHAR(20)",
        "istinaf_basvuru_tarihi":       "DATE",
        "istinaf_karar_durumu":         "VARCHAR(100)",
        "istinaf_karar_tarihi":         "DATE",
        "temyiz_basvuru_tarihi":        "DATE",
        "temyiz_karar_durumu":          "VARCHAR(100)",
        "temyiz_karar_tarihi":          "DATE",
        "kesinlesme_tarihi":            "DATE",
        "infaz_tarihi":                 "DATE",
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
    }),

    # 8. EXCEL IMPORT ALANLARI (BIRLESIK_SONUC_v5)
    ("columns", "cases", {
        "klasor_no_2":    "TEXT",            # Eski sistem no — gizli, aranabilir
        "atama_tarihi":   "DATE",            # Atama Tarihi
        "hasar_dosya_no": "VARCHAR(200)",    # Hasar Dosya Numarası
        "hukuk_no":       "VARCHAR(100)",    # Hukuk Numarası
    }),

    # 8b. HEARING_DATES (hearing_time)
    ("columns", "hearing_dates", {"hearing_time": "VARCHAR(10)"}),

    # 10. TENANT ISOLATION — cases.tenant_id
    ("columns", "cases", {
        "tenant_id": ("VARCHAR(100)", ["CREATE INDEX IF NOT EXISTS idx_cases_tenant ON cases(tenant_id)"]),
    }),

    # 10b. TENANT ISOLATION — clients.tenant_id (IDOR-1)
    # Mevcut müvekkiller NULL ile bırakılır → her iki tenant erişmeye devam eder.
    # Yeni eklenenler add_client(data, tenant_id=...) ile damgalanır.
    ("columns", "clients", {
        "tenant_id": ("VARCHAR(100)", ["CREATE INDEX IF NOT EXISTS idx_clients_tenant ON clients(tenant_id)"]),
    }),

    # 9. CASE_STAGE_LOGS
    ("table", "case_stage_logs", """
        CREATE TABLE case_stage_logs (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            stage VARCHAR(50) NOT NULL,
            changed_at TIMESTAMPTZ DEFAULT NOW(),
            changed_by VARCHAR(100),
            source VARCHAR(20) DEFAULT 'MANUAL',
            note TEXT
        )
    """, [
        "CREATE INDEX idx_stage_logs_case ON case_stage_logs(case_id)",
    ]),

    # 11. CASE_DOCUMENTS — uploaded_by_email
    ("columns", "case_documents", {
        "uploaded_by_email": (
            "VARCHAR(200)",
            ["CREATE INDEX IF NOT EXISTS idx_case_docs_uploader_email ON case_documents(uploaded_by_email)"],
        ),
    }),

    # 12. DAILY_ACTIVITY_REPORTS
    ("table", "daily_activity_reports", """
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
    """, [
        "CREATE INDEX idx_daily_reports_user ON daily_activity_reports(user_email, is_acknowledged)",
    ]),

    # 12b. DAILY_ACTIVITY_REPORTS — mailed_doc_ids, error_doc_ids
    ("columns", "daily_activity_reports", {
        "mailed_doc_ids": "TEXT",
        "error_doc_ids":  "TEXT",
    }),

    # 14. EXPORT_OUTBOX — hukukbot aktarım kuyruğu (docs/hukukbot-aktarim/PLAN.md §1)
    ("table", "export_outbox", """
        CREATE TABLE export_outbox (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL UNIQUE REFERENCES case_documents(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            nack_reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            delivered_at TIMESTAMPTZ
        )
    """, [
        "CREATE INDEX idx_export_outbox_status ON export_outbox(status)",
    ]),

    # 15. PERFORMANS INDEX'LERİ (KALITE_DENETIM_RAPORU §index eksikleri)
    # cases(updated_at, id): liste sıralaması ORDER BY updated_at DESC, id DESC ile birebir.
    ("index", "cases", [
        "CREATE INDEX IF NOT EXISTS idx_cases_updated_at_id ON cases (updated_at DESC, id DESC)",
    ]),
    ("index", "case_parties", [
        "CREATE INDEX IF NOT EXISTS idx_case_parties_case ON case_parties (case_id)",
    ]),
    ("index", "case_lawyers", [
        "CREATE INDEX IF NOT EXISTS idx_case_lawyers_case ON case_lawyers (case_id)",
    ]),
    ("index", "case_history", [
        "CREATE INDEX IF NOT EXISTS idx_case_history_case ON case_history (case_id)",
    ]),
    # case_id index'i models.HearingDate'te index=True ile zaten var (ix_ adı bilinçli
    # yeniden kullanılıyor → mevcut kurulumlarda no-op); hearing_date acil filtre için yeni.
    ("index", "hearing_dates", [
        "CREATE INDEX IF NOT EXISTS ix_hearing_dates_case_id ON hearing_dates (case_id)",
        "CREATE INDEX IF NOT EXISTS idx_hearing_dates_date ON hearing_dates (hearing_date)",
    ]),

    # 16. TANIDIK SORGU — case_parties.tc_no + TC lookup index'leri
    ("columns", "case_parties", {"tc_no": "VARCHAR(20)"}),
    ("index", "case_parties", [
        "CREATE INDEX IF NOT EXISTS idx_case_parties_tc_no ON case_parties (tc_no)",
    ]),
    ("index", "clients", [
        "CREATE INDEX IF NOT EXISTS idx_clients_tc_no ON clients (tc_no)",
    ]),
]

# 13. TRIGRAM ARAMA INDEX'LERI (pg_trgm) — yalnızca performans, hatası fatal değil.
# Arama ilike '%term%' (baştan wildcard) kullanıyor → B-tree index işe yaramaz,
# her sorgu full table scan. GIN + gin_trgm_ops index'i bu kalıbı hızlandırır.
_TRGM_INDEXES = {
    # cases — kimlik ve metin alanları
    "idx_cases_esas_no_trgm":     ("cases", "esas_no"),
    "idx_cases_tracking_no_trgm": ("cases", "tracking_no"),
    "idx_cases_klasor_no_2_trgm": ("cases", "klasor_no_2"),
    "idx_cases_court_trgm":       ("cases", "court"),
    "idx_cases_subject_trgm":     ("cases", "subject"),
    "idx_cases_resp_lawyer_trgm": ("cases", "responsible_lawyer_name"),
    "idx_cases_uyap_lawyer_trgm": ("cases", "uyap_lawyer_name"),
    # ilişkili tablolar — taraf / avukat adları
    "idx_case_parties_name_trgm": ("case_parties", "name"),
    "idx_case_lawyers_name_trgm": ("case_lawyers", "name"),
}


def check_and_migrate_tables():
    """Şemayı _MIGRATIONS listesine göre günceller (idempotent).

    Yapısal bir adım başarısız olursa RuntimeError fırlatır → init_db başarısız
    olur ve uygulama ayağa kalkmaz. Önceki davranış (logla ve devam et) sessiz
    şema sapmasına yol açıyordu.
    """
    from sqlalchemy import text, inspect

    db_type = engine.dialect.name
    logger.info(f"Running migrations for {db_type}")

    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        def _exec(sql: str, context: str):
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration error for {context}: {e}")
                raise RuntimeError(f"Migration failed for {context}: {e}") from e

        for op in _MIGRATIONS:
            kind, table = op[0], op[1]
            if kind == "rename":
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                for old_name, new_name in op[2].items():
                    if old_name in columns and new_name not in columns:
                        _exec(f'ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}',
                              f"{table}.{old_name}→{new_name}")
                        logger.info(f"Renamed {table}.{old_name} → {new_name}")

            elif kind == "columns":
                if table not in tables:
                    continue
                columns = {col["name"] for col in inspector.get_columns(table)}
                for col_name, spec in op[2].items():
                    if col_name in columns:
                        continue
                    ddl, post_sql = (spec, []) if isinstance(spec, str) else spec
                    _exec(f'ALTER TABLE {table} ADD COLUMN {col_name} {ddl}', f"{table}.{col_name}")
                    for sql in post_sql:
                        _exec(sql, f"{table}.{col_name} (post)")
                    logger.info(f"Added {col_name} to {table}")

            elif kind == "table":
                if table in tables:
                    continue
                create_sql, index_sqls = op[2], op[3]
                _exec(create_sql, table)
                for sql in index_sqls:
                    _exec(sql, f"{table} (index)")
                tables.add(table)
                logger.info(f"Created {table} table")

            elif kind == "index":
                if table not in tables:
                    continue
                for sql in op[2]:
                    _exec(sql, f"{table} (index)")

        # pg_trgm — performans amaçlı; yetki/uzantı eksikse uygulamayı durdurmaz
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
            for idx_name, (tbl, col) in _TRGM_INDEXES.items():
                if tbl not in tables:
                    continue
                try:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} "
                        f"ON {tbl} USING gin ({col} gin_trgm_ops)"
                    ))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Trigram index error for {idx_name}: {e}")
            logger.info("Trigram (pg_trgm) arama index'leri hazır")
        except Exception as e:
            conn.rollback()
            logger.error(f"pg_trgm extension/index migration error: {e}")

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
        clients = db.query(Client).filter(Client.active.is_(True)).all()
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
