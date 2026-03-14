import sqlite3
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Use the same database models for consistency
from models import Base, Client, Lawyer, Case, CaseStatus, DocumentType, CaseParty, AnalysisCache

# Configuration
# NOTE: Inside container, postgres service name is 'postgres'
# But if running from host, it should be 'localhost'
CHOSEN_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hukudok_user:dv3clS_gcjnKgCn7suoaZU@localhost:5432/hukudok")
SQLITE_DB_PATH = "hukudok.db" # This should be in the same folder

def migrate():
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ SQLite database not found at {SQLITE_DB_PATH}")
        return

    print(f"🐘 Connecting to PostgreSQL at {CHOSEN_DATABASE_URL}")
    pg_engine = create_engine(CHOSEN_DATABASE_URL)
    PgSession = sessionmaker(bind=pg_engine)
    pg_session = PgSession()

    print(f"📂 Connecting to SQLite at {SQLITE_DB_PATH}")
    sl_conn = sqlite3.connect(SQLITE_DB_PATH)
    sl_conn.row_factory = sqlite3.Row
    sl_cur = sl_conn.cursor()

    # Tables to migrate in order
    tables = [
        ("lawyers", Lawyer),
        ("statuses", CaseStatus),
        ("doctypes", DocumentType),
        ("clients", Client),
        ("cases", Case),
        ("case_parties", CaseParty),
        ("analysis_cache", AnalysisCache)
    ]

    try:
        # 1. Clear existing data in PG (Be careful!)
        print("⚠️  Cleaning existing data in PostgreSQL...")
        for _, model in reversed(tables):
            pg_session.query(model).delete()
        pg_session.commit()

        for table_name, model in tables:
            print(f"⏳ Migrating {table_name}...")
            sl_cur.execute(f"SELECT * FROM {table_name}")
            rows = sl_cur.fetchall()
            
            objects = []
            for row in rows:
                data = dict(row)
                # Map SQLite boolean/int to Python types if needed
                if 'active' in data: data['active'] = bool(data['active'])
                # Create model instance
                obj = model(**data)
                objects.append(obj)
            
            if objects:
                pg_session.bulk_save_objects(objects)
                pg_session.commit()
                print(f"✅ Migrated {len(objects)} rows for {table_name}")
            else:
                print(f"ℹ️  No data found for {table_name}")

        print("\n🚀 Migration COMPLETED successfully!")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        pg_session.rollback()
    finally:
        sl_conn.close()
        pg_session.close()

if __name__ == "__main__":
    migrate()
