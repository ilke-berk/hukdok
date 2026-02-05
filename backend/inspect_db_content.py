import sqlite3
import os

def inspect_db():
    db_path = os.path.join("backend", "data", "hukudok.db")
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, source_ids FROM clients LIMIT 5")
    rows = cursor.fetchall()
    
    print(f"Inspecting {db_path}:")
    for row in rows:
        print(row)
        
    conn.close()

if __name__ == "__main__":
    inspect_db()
