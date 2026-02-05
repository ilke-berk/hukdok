import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
import sys

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
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create Engine
# check_same_thread=False is needed for SQLite with FastAPI (multi-threaded)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
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
    """Checks if 'sequence' column exists, adds it if not."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # 1. SEQUENCE MIGRATION
            for table in ["lawyers", "doctypes", "statuses"]:
                try:
                    result = conn.execute(text(f"PRAGMA table_info({table})"))
                    columns = [row[1] for row in result.fetchall()]
                    if "sequence" not in columns:
                        print(f"Migrating table {table}: Adding sequence column...")
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN sequence INTEGER DEFAULT 0"))
                        conn.commit()
                except Exception as e:
                    print(f"Migration error for {table}: {e}")

            # 2. CLIENT FIELDS MIGRATION
            try:
                result = conn.execute(text("PRAGMA table_info(clients)"))
                columns = [row[1] for row in result.fetchall()]
                
                new_fields = {
                    "tc_no": "VARCHAR",
                    "email": "VARCHAR",
                    "phone": "VARCHAR",
                    "address": "VARCHAR",
                    "notes": "VARCHAR"
                }

                for field, type_ in new_fields.items():
                    if field not in columns:
                        print(f"Migrating table clients: Adding {field} column...")
                        conn.execute(text(f"ALTER TABLE clients ADD COLUMN {field} {type_}"))
                        conn.commit()
            except Exception as e:
                print(f"Migration error for clients: {e}")

    except Exception as e:

        print(f"Global migration error: {e}")
