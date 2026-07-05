"""2026/1379 davasını staging'den local'e ekler."""
import psycopg2, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("../.env")

LOCAL_URL   = os.getenv("DATABASE_URL", "").replace("@postgres:", "@localhost:")
STAGING_URL = LOCAL_URL.rsplit("/hukudok", 1)[0] + "/hukudok_staging"
TARGET_ESAS = "2026/1379"

s = psycopg2.connect(STAGING_URL)
l = psycopg2.connect(LOCAL_URL)
sc, lc = s.cursor(), l.cursor()

def local_cols(table):
    lc.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s AND table_schema='public'", (table,))
    return {r[0] for r in lc.fetchall()}

def dict_rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

try:
    # 1. Case
    sc.execute("SELECT * FROM cases WHERE esas_no = %s", (TARGET_ESAS,))
    rows = dict_rows(sc)
    if not rows:
        print(f"HATA: staging'de {TARGET_ESAS} bulunamadı"); sys.exit(1)

    case = rows[0].copy()
    staging_case_id = case.pop("id")
    allowed = local_cols("cases")
    case = {k: v for k, v in case.items() if k in allowed}
    for col in allowed - set(case.keys()) - {"id"}:
        case[col] = None

    c_cols = ", ".join(case.keys())
    c_vals = ", ".join(["%s"] * len(case))
    lc.execute(f"INSERT INTO cases ({c_cols}) VALUES ({c_vals}) RETURNING id", list(case.values()))
    new_id = lc.fetchone()[0]
    print(f"✓ Dava oluşturuldu → local case_id={new_id}")

    # 2. Parties
    sc.execute("SELECT * FROM case_parties WHERE case_id = %s", (staging_case_id,))
    parties = dict_rows(sc)
    allowed_p = local_cols("case_parties")
    for p in parties:
        pd = {k: v for k, v in p.items() if k in allowed_p and k != "id"}
        pd["case_id"] = new_id
        pd["client_id"] = None
        pc = ", ".join(pd.keys())
        pp = ", ".join(["%s"] * len(pd))
        lc.execute(f"INSERT INTO case_parties ({pc}) VALUES ({pp})", list(pd.values()))
    print(f"✓ {len(parties)} taraf eklendi")

    # 3. Documents
    sc.execute("SELECT * FROM case_documents WHERE case_id = %s", (staging_case_id,))
    docs = dict_rows(sc)
    allowed_d = local_cols("case_documents")
    for doc in docs:
        dd = {k: v for k, v in doc.items() if k in allowed_d and k != "id"}
        dd["case_id"] = new_id
        dd["case_party_id"] = None
        dd.setdefault("email_sent", None)
        dd.setdefault("email_error", None)
        dc = ", ".join(dd.keys())
        dp = ", ".join(["%s"] * len(dd))
        lc.execute(f"INSERT INTO case_documents ({dc}) VALUES ({dp})", list(dd.values()))
    print(f"✓ {len(docs)} belge eklendi")

    l.commit()
    print(f"\n✅ {TARGET_ESAS} davası ve belgeleri başarıyla local'e eklendi.")

except Exception as e:
    l.rollback()
    print(f"❌ HATA: {e}"); raise
finally:
    sc.close(); lc.close(); s.close(); l.close()
