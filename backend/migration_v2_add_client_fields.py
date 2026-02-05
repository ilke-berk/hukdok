import sqlite3
import os
from pathlib import Path

def migrate_database():
    """
    Migration to add client_type and category to clients table.
    """
    # Dev environment path (current directory is root, backend is likely subdirectory)
    # Trying relative path from where script is run (hukudok-automator-main)
    # The script is in backend/, so data/ is in backend/data/
    
    current_dir = Path(__file__).resolve().parent
    db_path = current_dir / "data" / "hukudok.db"
    
    print(f"Looking for database at: {db_path}")

    if not db_path.exists():
        # Fallback to AppData if not found locally (maybe user IS using AppData in some config?)
        app_data_path = Path.home() / "AppData" / "Local" / "HukuDok" / "data" / "hukudok.db"
        if app_data_path.exists():
             db_path = app_data_path
             print(f"Found database in AppData: {db_path}")
        else:
             print(f"Database not found at {db_path} or {app_data_path}.")
             return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(clients)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "client_type" not in columns:
            print("Adding client_type column...")
            cursor.execute("ALTER TABLE clients ADD COLUMN client_type TEXT")
            
        if "category" not in columns:
            print("Adding category column...")
            cursor.execute("ALTER TABLE clients ADD COLUMN category TEXT")
            
        conn.commit()
        print("Migration successful.")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
