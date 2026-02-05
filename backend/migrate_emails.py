import json
import os
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models

def migrate_emails():
    print("🚀 Starting Email Migration...")
    
    # 1. Initialize DB (Create tables)
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created/verified.")
    except Exception as e:
        print(f"❌ Failed to init database: {e}")
        return

    # 2. Locate JSON file
    # Check if frozen (bundled) or dev
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        # Assuming script is in backend/ and data is in backend/data/
        base_path = Path(__file__).resolve().parent
    
    json_path = base_path / "data" / "email_recipients.json"
    
    if not json_path.exists():
        print(f"⚠️ JSON file not found at: {json_path}")
        # Try alternate location just in case
        json_path = base_path.parent / "data" / "email_recipients.json"
        if not json_path.exists():
            print(f"❌ JSON file not found at alternate: {json_path}")
            return
            
    print(f"📂 Found JSON at: {json_path}")
    
    # 3. Read JSON
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"📊 Creating {len(data)} email recipients...")
    except Exception as e:
        print(f"❌ Failed to read JSON: {e}")
        return
        
    # 4. Write to DB
    db = SessionLocal()
    count = 0
    try:
        for idx, item in enumerate(data):
            email = item.get("email")
            name = item.get("name")
            description = item.get("description", "")
            
            if not email:
                print(f"⚠️ Skipping item with no email: {item}")
                continue
                
            # Check existing
            existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
            if existing:
                print(f"🔹 Skipping existing: {email}")
                continue
                
            new_recipient = models.EmailRecipient(
                name=name,
                email=email,
                description=description,
                active=True,
                sequence=idx  # Preserve order
            )
            db.add(new_recipient)
            count += 1
            
        db.commit()
        print(f"✅ Successfully migrated {count} email recipients.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_emails()
