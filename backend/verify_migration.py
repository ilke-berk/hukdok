from database import SessionLocal
import models

def verify_migration():
    db = SessionLocal()
    try:
        count = db.query(models.EmailRecipient).count()
        print(f"✅ Total Email Recipients in DB: {count}")
        
        items = db.query(models.EmailRecipient).all()
        for item in items:
            print(f" - {item.name}: {item.email} (Seq: {item.sequence})")
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_migration()
