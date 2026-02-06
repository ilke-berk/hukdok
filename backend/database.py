"""
Database configuration with PostgreSQL and SQLite support.

Environment Variables:
- DATABASE_URL: Full database connection string
  - PostgreSQL: postgresql://user:password@host:port/database
  - SQLite: sqlite:///./data/hukudok.db (fallback)
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Determine database type and configure engine accordingly
if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    # PostgreSQL Configuration (Production)
    logger.info("🐘 Using PostgreSQL database")
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,      # Verify connections before using
        pool_size=10,            # Connection pool size
        max_overflow=20,         # Max overflow connections
        pool_recycle=3600,       # Recycle connections after 1 hour
        echo=False               # Set to True for SQL query logging
    )
else:
    # SQLite Configuration (Development/Fallback)
    logger.info("💾 Using SQLite database (fallback/development mode)")
    
    # Determine DB Path (Works for Dev and PyInstaller Frozen)
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        BASE_DIR = Path(sys.executable).parent
        DB_DIR = BASE_DIR / "data"
    else:
        # Running as script
        BASE_DIR = Path(__file__).resolve().parent
        DB_DIR = BASE_DIR / "data"
    
    # Ensure data directory exists
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    DB_PATH = DB_DIR / "hukudok.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # SQLite specific
        echo=False
    )


# SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
            for table in ["lawyers", "doctypes", "statuses"]:
                if table not in inspector.get_table_names():
                    logger.warning(f"Table {table} does not exist, skipping migration")
                    continue
                    
                columns = [col['name'] for col in inspector.get_columns(table)]
                
                if "sequence" not in columns:
                    logger.info(f"Migrating table {table}: Adding sequence column...")
                    try:
                        if db_type == "postgresql":
                            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN sequence INTEGER DEFAULT 0'))
                        else:  # SQLite
                            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN sequence INTEGER DEFAULT 0'))
                        conn.commit()
                    except Exception as e:
                        logger.error(f"Migration error for {table}.sequence: {e}")

            # 2. CLIENT FIELDS MIGRATION
            if "clients" not in inspector.get_table_names():
                logger.warning("Table clients does not exist, skipping migration")
                return
                
            columns = [col['name'] for col in inspector.get_columns("clients")]
            
            new_fields = {
                "tc_no": "VARCHAR",
                "email": "VARCHAR",
                "phone": "VARCHAR",
                "address": "VARCHAR",
                "notes": "TEXT",
                "contact_type": "VARCHAR",
                "client_type": "VARCHAR",
                "category": "VARCHAR"
            }

            for field, type_ in new_fields.items():
                if field not in columns:
                    logger.info(f"Migrating table clients: Adding {field} column...")
                    try:
                        if db_type == "postgresql":
                            conn.execute(text(f'ALTER TABLE clients ADD COLUMN {field} {type_}'))
                        else:  # SQLite
                            conn.execute(text(f'ALTER TABLE clients ADD COLUMN {field} {type_}'))
                        conn.commit()
                    except Exception as e:
                        logger.error(f"Migration error for clients.{field}: {e}")

    except Exception as e:
        logger.error(f"Global migration error: {e}")

