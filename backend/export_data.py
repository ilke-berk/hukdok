import sys
import os
import csv
from datetime import datetime

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Lawyer, Client, DocType, Status

def export_to_csv():
    # Setup export dir
    base_dir = os.path.dirname(os.path.abspath(__file__))
    export_dir = os.path.join(base_dir, "data", "exports")
    os.makedirs(export_dir, exist_ok=True)
    
    db = SessionLocal()
    try:
        # 1. Export Lawyers
        lawyers = db.query(Lawyer).all()
        path = os.path.join(export_dir, "avukatlar.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Kod", "Isim", "Aktif"])
            for l in lawyers:
                writer.writerow([l.id, l.code, l.name, l.active])
        print(f"✅ Avukatlar dışa aktarıldı: {path}")

        # 2. Export Clients
        clients = db.query(Client).all()
        path = os.path.join(export_dir, "muvekkiller_ornek.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Isim", "Kaynak_IDleri", "Aktif"])
            # Limit to first 100 to avoid huge file if just checking
            for c in clients[:100]:
                writer.writerow([c.id, c.name, c.source_ids, c.active])
        print(f"✅ Müvekkiller (İlk 100) dışa aktarıldı: {path}")

        # 3. Export DocTypes
        doctypes = db.query(DocType).all()
        path = os.path.join(export_dir, "belge_turleri.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Kod", "Isim", "Aktif"])
            for d in doctypes:
                writer.writerow([d.id, d.code, d.name, d.active])
        print(f"✅ Belge Türleri dışa aktarıldı: {path}")

        # 4. Export Statuses
        statuses = db.query(Status).all()
        path = os.path.join(export_dir, "durumlar.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Kod", "Isim", "Aktif"])
            for s in statuses:
                writer.writerow([s.id, s.code, s.name, s.active])
        print(f"✅ Durumlar dışa aktarıldı: {path}")
        
        print(f"\n📂 Tüm dosyalar burada: {export_dir}")

    finally:
        db.close()

if __name__ == "__main__":
    export_to_csv()
