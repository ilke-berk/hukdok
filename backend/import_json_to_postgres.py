"""
Import data from JSON to PostgreSQL database.
This script expects DATABASE_URL to be set to PostgreSQL connection string.
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

def import_data():
    """Import data from JSON to PostgreSQL"""
    print("=" * 60)
    print("IMPORTING DATA TO POSTGRESQL")
    print("=" * 60)
    
    # Check DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url or not db_url.startswith("postgresql"):
        print("\nERROR: DATABASE_URL must be set to PostgreSQL connection string!")
        print(f"Current: {db_url}")
        print("\nExample:")
        print('  $env:DATABASE_URL="postgresql://hukudok_user:password@host:5432/hukudok"')
        return False
    
    print(f"\nDatabase URL: {db_url[:50]}...")
    
    try:
        # Load data from JSON
        data_file = Path(__file__).parent / "migration_data.json"
        if not data_file.exists():
            print(f"\nERROR: {data_file} not found!")
            print("Please run export_sqlite_to_json.py first.")
            return False
        
        print(f"Loading data from {data_file}...")
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"Export timestamp: {data.get('export_timestamp')}")
        
        # Import database and models
        from database import SessionLocal, Base, engine
        import models
        
        # Create all tables
        print("\nCreating tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully!")
        
        db = SessionLocal()
        
        # Import each table
        print("\n" + "-" * 60)
        
        # 1. Lawyers
        print("Importing Lawyers...")
        for item in data.get("lawyers", []):
            # Check if exists
            existing = db.query(models.Lawyer).filter(models.Lawyer.code == item["code"]).first()
            if existing:
                # Update
                existing.name = item["name"]
                existing.active = item.get("active", True)
                existing.sequence = item.get("sequence", 0)
            else:
                # Insert (preserve ID)
                lawyer = models.Lawyer(
                    id=item["id"],
                    code=item["code"],
                    name=item["name"],
                    active=item.get("active", True),
                    sequence=item.get("sequence", 0)
                )
                db.add(lawyer)
        db.commit()
        print(f"  Imported {len(data.get('lawyers', []))} lawyers")
        
        # 2. Clients
        print("Importing Clients...")
        for item in data.get("clients", []):
            existing = db.query(models.Client).filter(models.Client.name == item["name"]).first()
            if existing:
                # Update
                existing.source_ids = item.get("source_ids")
                existing.tc_no = item.get("tc_no")
                existing.email = item.get("email")
                existing.phone = item.get("phone")
                existing.address = item.get("address")
                existing.notes = item.get("notes")
                existing.contact_type = item.get("contact_type", "Client")
                existing.client_type = item.get("client_type")
                existing.category = item.get("category")
                existing.active = item.get("active", True)
            else:
                client = models.Client(
                    id=item["id"],
                    name=item["name"],
                    source_ids=item.get("source_ids"),
                    tc_no=item.get("tc_no"),
                    email=item.get("email"),
                    phone=item.get("phone"),
                    address=item.get("address"),
                    notes=item.get("notes"),
                    contact_type=item.get("contact_type", "Client"),
                    client_type=item.get("client_type"),
                    category=item.get("category"),
                    active=item.get("active", True)
                )
                db.add(client)
        db.commit()
        print(f"  Imported {len(data.get('clients', []))} clients")
        
        # 3. DocTypes
        print("Importing DocTypes...")
        for item in data.get("doctypes", []):
            existing = db.query(models.DocType).filter(models.DocType.code == item["code"]).first()
            if existing:
                existing.name = item["name"]
                existing.active = item.get("active", True)
                existing.sequence = item.get("sequence", 0)
            else:
                doctype = models.DocType(
                    id=item["id"],
                    code=item["code"],
                    name=item["name"],
                    active=item.get("active", True),
                    sequence=item.get("sequence", 0)
                )
                db.add(doctype)
        db.commit()
        print(f"  Imported {len(data.get('doctypes', []))} doctypes")
        
        # 4. Statuses
        print("Importing Statuses...")
        for item in data.get("statuses", []):
            existing = db.query(models.Status).filter(models.Status.code == item["code"]).first()
            if existing:
                existing.name = item["name"]
                existing.active = item.get("active", True)
                existing.sequence = item.get("sequence", 0)
            else:
                status = models.Status(
                    id=item["id"],
                    code=item["code"],
                    name=item["name"],
                    active=item.get("active", True),
                    sequence=item.get("sequence", 0)
                )
                db.add(status)
        db.commit()
        print(f"  Imported {len(data.get('statuses', []))} statuses")
        
        # 5. Email Recipients
        print("Importing Email Recipients...")
        for item in data.get("email_recipients", []):
            existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == item["email"]).first()
            if existing:
                existing.name = item["name"]
                existing.description = item.get("description")
                existing.active = item.get("active", True)
                existing.sequence = item.get("sequence", 0)
            else:
                recipient = models.EmailRecipient(
                    id=item["id"],
                    name=item["name"],
                    email=item["email"],
                    description=item.get("description"),
                    active=item.get("active", True),
                    sequence=item.get("sequence", 0)
                )
                db.add(recipient)
        db.commit()
        print(f"  Imported {len(data.get('email_recipients', []))} email recipients")
        
        db.close()
        
        print("\n" + "=" * 60)
        print("SUCCESS: All data imported to PostgreSQL!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = import_data()
    sys.exit(0 if success else 1)
