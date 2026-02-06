"""
Export all data from SQLite database to JSON format.
This will be used to migrate data to PostgreSQL.
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# CRITICAL: Force SQLite usage by removing DATABASE_URL
if "DATABASE_URL" in os.environ:
    print("Removing DATABASE_URL to force SQLite usage...")
    del os.environ["DATABASE_URL"]


def export_data():
    """Export all tables to JSON"""
    print("=" * 60)
    print("EXPORTING DATA FROM SQLITE")
    print("=" * 60)
    
    try:
        # Import database and models
        from database import SessionLocal
        import models
        
        db = SessionLocal()
        
        # Export data from each table
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "database_type": "sqlite",
        }
        
        # 1. Lawyers
        print("\nExporting Lawyers...")
        lawyers = db.query(models.Lawyer).all()
        data["lawyers"] = [
            {
                "id": l.id,
                "code": l.code,
                "name": l.name,
                "active": l.active,
                "sequence": l.sequence if hasattr(l, 'sequence') else 0,
            }
            for l in lawyers
        ]
        print(f"  Exported {len(data['lawyers'])} lawyers")
        
        # 2. Clients
        print("Exporting Clients...")
        clients = db.query(models.Client).all()
        data["clients"] = [
            {
                "id": c.id,
                "name": c.name,
                "source_ids": c.source_ids,
                "tc_no": c.tc_no if hasattr(c, 'tc_no') else None,
                "email": c.email if hasattr(c, 'email') else None,
                "phone": c.phone if hasattr(c, 'phone') else None,
                "address": c.address if hasattr(c, 'address') else None,
                "notes": c.notes if hasattr(c, 'notes') else None,
                "contact_type": c.contact_type if hasattr(c, 'contact_type') else "Client",
                "client_type": c.client_type if hasattr(c, 'client_type') else None,
                "category": c.category if hasattr(c, 'category') else None,
                "active": c.active,
            }
            for c in clients
        ]
        print(f"  Exported {len(data['clients'])} clients")
        
        # 3. DocTypes
        print("Exporting DocTypes...")
        doctypes = db.query(models.DocType).all()
        data["doctypes"] = [
            {
                "id": d.id,
                "code": d.code,
                "name": d.name,
                "active": d.active,
                "sequence": d.sequence if hasattr(d, 'sequence') else 0,
            }
            for d in doctypes
        ]
        print(f"  Exported {len(data['doctypes'])} doctypes")
        
        # 4. Statuses
        print("Exporting Statuses...")
        statuses = db.query(models.Status).all()
        data["statuses"] = [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "active": s.active,
                "sequence": s.sequence if hasattr(s, 'sequence') else 0,
            }
            for s in statuses
        ]
        print(f"  Exported {len(data['statuses'])} statuses")
        
        # 5. Email Recipients
        print("Exporting Email Recipients...")
        email_recipients = db.query(models.EmailRecipient).all()
        data["email_recipients"] = [
            {
                "id": e.id,
                "name": e.name,
                "email": e.email,
                "description": e.description,
                "active": e.active,
                "sequence": e.sequence if hasattr(e, 'sequence') else 0,
            }
            for e in email_recipients
        ]
        print(f"  Exported {len(data['email_recipients'])} email recipients")
        
        db.close()
        
        # Save to file
        output_file = Path(__file__).parent / "migration_data.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 60)
        print(f"SUCCESS: Data exported to {output_file}")
        print("=" * 60)
        
        # Summary
        print("\nSummary:")
        print(f"  - Lawyers: {len(data['lawyers'])}")
        print(f"  - Clients: {len(data['clients'])}")
        print(f"  - DocTypes: {len(data['doctypes'])}")
        print(f"  - Statuses: {len(data['statuses'])}")
        print(f"  - Email Recipients: {len(data['email_recipients'])}")
        print(f"\nTotal records: {sum([len(data[k]) for k in ['lawyers', 'clients', 'doctypes', 'statuses', 'email_recipients']])}")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = export_data()
    sys.exit(0 if success else 1)
