import psycopg2, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("../.env")

db = os.getenv("DATABASE_URL","").replace("@postgres:","@localhost:")
staging = db.rsplit("/hukudok", 1)[0] + "/hukudok_staging"

s = psycopg2.connect(staging)
l = psycopg2.connect(db)
sc = s.cursor()
lc = l.cursor()

SKIP = ("9/9","2026/1379","2000/399")

sc.execute("SELECT COUNT(*) FROM case_documents cd JOIN cases c ON cd.case_id=c.id WHERE c.esas_no NOT IN %s", (SKIP,))
print("Tasinacak belge:", sc.fetchone()[0])

sc.execute("SELECT DISTINCT c.id, c.esas_no FROM cases c JOIN case_documents cd ON cd.case_id=c.id WHERE c.esas_no NOT IN %s", (SKIP,))
rows = sc.fetchall()
exact=like=none_list=0
missing=[]
for sid, esas in rows:
    lc.execute("SELECT id FROM cases WHERE esas_no=%s LIMIT 1",(esas,))
    if lc.fetchone(): exact+=1; continue
    lc.execute("SELECT id FROM cases WHERE esas_no LIKE %s LIMIT 1",(f"%{esas}%",))
    if lc.fetchone(): like+=1; continue
    none_list+=1
    missing.append((sid, esas))

print(f"Tam eslesme: {exact}")
print(f"LIKE eslesme (birlesmis esas_no): {like}")
print(f"Local'de yok (yeni olusturulacak): {none_list}")
if missing:
    print("  Yeni olusturulacak davalar:")
    for sid, esas in missing:
        print(f"    staging_id={sid}  esas_no={esas}")

s.close(); l.close()
