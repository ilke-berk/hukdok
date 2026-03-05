import sys
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    res = db.execute(text("SELECT setval('clients_id_seq', (SELECT COALESCE(MAX(id), 1) FROM clients));"))
    db.commit()
    print('Sequence updated:', res.scalar())
except Exception as e:
    print('Error:', e)
