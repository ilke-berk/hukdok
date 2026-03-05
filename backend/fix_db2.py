import sys
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    res1 = db.execute(text("SELECT setval('cases_id_seq', (SELECT COALESCE(MAX(id), 1) FROM cases));"))
    res2 = db.execute(text("SELECT setval('case_parties_id_seq', (SELECT COALESCE(MAX(id), 1) FROM case_parties));"))
    db.commit()
    print('Cases sequence updated:', res1.scalar())
    print('Case Parties sequence updated:', res2.scalar())
except Exception as e:
    print('Error:', e)
