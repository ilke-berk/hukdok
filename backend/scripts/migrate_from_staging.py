"""
Staging DB'sindeki (production backup) case_documents kayıtlarını local DB'ye taşır.

Eşleştirme sırası:
  1. esas_no tam eşleşme
  2. esas_no LIKE eşleşme (local'de "2019/371;2026/179" gibi birleşik esas_no'lar)
  3. Local'de hiç yoksa staging'den case + case_parties kopyalanır, belge yeni ID'ye eklenir

Hariç tutulanlar:
  - esas_no = '9/9'       (test belgesi)
  - esas_no = '2026/1379' (belirsiz - manuel karar bekliyor)
  - esas_no = '2000/399'  (belirsiz - manuel karar bekliyor)

Ayrıca analysis_cache tablosu da staging'den local'e kopyalanır (AI analiz sonuçları).
"""

import sys, os
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv("../.env")

LOCAL_URL   = os.getenv("DATABASE_URL", "").replace("@postgres:", "@localhost:")
STAGING_URL = LOCAL_URL.rsplit("/hukudok", 1)[0] + "/hukudok_staging"

SKIP_ESAS = {"9/9", "2026/1379", "2000/399"}


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def dict_fetchall(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_case_mapping(s_cur, l_cur):
    """staging case_id → local case_id  (None = local'de yok)"""
    s_cur.execute("""
        SELECT DISTINCT c.id, c.esas_no
        FROM cases c
        JOIN case_documents cd ON cd.case_id = c.id
        WHERE c.esas_no IS NOT NULL AND c.esas_no NOT IN %s
    """, (tuple(SKIP_ESAS),))
    rows = s_cur.fetchall()

    mapping = {}
    not_found = []

    for staging_id, esas_no in rows:
        # 1. Tam eşleşme
        l_cur.execute("SELECT id FROM cases WHERE esas_no = %s LIMIT 1", (esas_no,))
        row = l_cur.fetchone()
        if row:
            mapping[staging_id] = row[0]
            continue

        # 2. LIKE eşleşme (birleşik esas_no'lar)
        l_cur.execute("SELECT id FROM cases WHERE esas_no LIKE %s LIMIT 1",
                      (f"%{esas_no}%",))
        row = l_cur.fetchone()
        if row:
            mapping[staging_id] = row[0]
            continue

        mapping[staging_id] = None
        not_found.append((staging_id, esas_no))

    return mapping, not_found


def create_case_in_local(s_cur, l_cur, staging_case_id):
    """Staging'deki davayı local'e kopyala, yeni local case_id döndür."""
    s_cur.execute("SELECT * FROM cases WHERE id = %s", (staging_case_id,))
    rows = dict_fetchall(s_cur)
    if not rows:
        return None
    cd = rows[0].copy()
    del cd["id"]

    # Local'deki ekstra kolonlar (yeni şema) için alan ekle, staging'dekiler kalır
    local_cols_query = """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'cases' AND table_schema = 'public'
    """
    l_cur.execute(local_cols_query)
    local_case_cols = {r[0] for r in l_cur.fetchall()}
    for col in local_case_cols - set(cd.keys()) - {"id"}:
        cd[col] = None  # Yeni kolonlar boş

    # Sadece local'de olan kolonları gönder
    cd = {k: v for k, v in cd.items() if k in local_case_cols and k != "id"}

    cols = ", ".join(cd.keys())
    placeholders = ", ".join(["%s"] * len(cd))
    l_cur.execute(f"INSERT INTO cases ({cols}) VALUES ({placeholders}) RETURNING id",
                  list(cd.values()))
    new_id = l_cur.fetchone()[0]

    # case_parties kopyala
    s_cur.execute("SELECT * FROM case_parties WHERE case_id = %s", (staging_case_id,))
    parties = dict_fetchall(s_cur)

    l_cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='case_parties' AND table_schema='public'")
    local_party_cols = {r[0] for r in l_cur.fetchall()}

    for p in parties:
        pd = {k: v for k, v in p.items() if k in local_party_cols and k != "id"}
        pd["case_id"] = new_id
        pd["client_id"] = None  # Party ID'leri farklı, bağlantı kesilebilir
        pc = ", ".join(pd.keys())
        pp = ", ".join(["%s"] * len(pd))
        l_cur.execute(f"INSERT INTO case_parties ({pc}) VALUES ({pp})", list(pd.values()))

    return new_id


def migrate_documents(s_cur, l_cur, case_mapping):
    """Belgeleri staging'den local'e aktar."""
    s_cur.execute("""
        SELECT cd.*, c.esas_no AS _case_esas_no
        FROM case_documents cd
        JOIN cases c ON cd.case_id = c.id
        WHERE c.esas_no IS NOT NULL AND c.esas_no NOT IN %s
    """, (tuple(SKIP_ESAS),))
    docs = dict_fetchall(s_cur)

    l_cur.execute("""SELECT column_name FROM information_schema.columns
                     WHERE table_name='case_documents' AND table_schema='public'""")
    local_doc_cols = {r[0] for r in l_cur.fetchall()}

    inserted = skipped_mapped = skipped_nocase = already_exists = 0
    no_case_docs = []

    for doc in docs:
        staging_case_id = doc["case_id"]
        doc.pop("_case_esas_no", None)

        local_case_id = case_mapping.get(staging_case_id)
        if local_case_id is None:
            skipped_nocase += 1
            no_case_docs.append(doc["stored_filename"])
            continue

        # Zaten var mı?
        l_cur.execute("SELECT id FROM case_documents WHERE stored_filename = %s",
                      (doc["stored_filename"],))
        if l_cur.fetchone():
            already_exists += 1
            continue

        dd = {k: v for k, v in doc.items() if k in local_doc_cols and k != "id"}
        dd["case_id"] = local_case_id
        dd["case_party_id"] = None  # Party ID'leri eşleştirilemiyor
        dd.setdefault("email_sent", None)
        dd.setdefault("email_error", None)

        dc = ", ".join(dd.keys())
        dp = ", ".join(["%s"] * len(dd))
        l_cur.execute(f"INSERT INTO case_documents ({dc}) VALUES ({dp})", list(dd.values()))
        inserted += 1

    return inserted, skipped_mapped, skipped_nocase, already_exists, no_case_docs


def migrate_analysis_cache(s_cur, l_cur):
    """AI analiz sonuçlarını aktar (file_hash primary key, çakışmayı atla)."""
    s_cur.execute("SELECT file_hash, data_json, created_at, updated_at FROM analysis_cache")
    rows = dict_fetchall(s_cur)

    copied = skipped = 0
    for row in rows:
        l_cur.execute("SELECT 1 FROM analysis_cache WHERE file_hash = %s", (row["file_hash"],))
        if l_cur.fetchone():
            skipped += 1
            continue
        l_cur.execute("""
            INSERT INTO analysis_cache (file_hash, data_json, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (row["file_hash"], row["data_json"], row["created_at"], row["updated_at"]))
        copied += 1

    return copied, skipped


# ── Ana akış ──────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}")
    print("  STAGING → LOCAL MIGRATION")
    print(f"{'='*70}")
    print(f"  Staging : {STAGING_URL[:60]}...")
    print(f"  Local   : {LOCAL_URL[:60]}...")
    print(f"{'='*70}\n")

    s_conn = psycopg2.connect(STAGING_URL)
    l_conn = psycopg2.connect(LOCAL_URL)
    s_cur = s_conn.cursor()
    l_cur = l_conn.cursor()

    try:
        # 1. Case mapping
        print("⏳ Case ID eşleştirmesi yapılıyor...")
        case_mapping, not_found = build_case_mapping(s_cur, l_cur)
        matched = sum(1 for v in case_mapping.values() if v is not None)
        print(f"   ✓ Eşleşen dava          : {matched}")
        print(f"   ✗ Local'de olmayan dava  : {len(not_found)}")

        # 2. Local'de olmayan davaları oluştur
        if not_found:
            print(f"\n⏳ {len(not_found)} dava local'e oluşturuluyor...")
            for staging_id, esas_no in not_found:
                new_id = create_case_in_local(s_cur, l_cur, staging_id)
                if new_id:
                    case_mapping[staging_id] = new_id
                    print(f"   + Staging case {staging_id} ({esas_no}) → local case {new_id}")
                else:
                    print(f"   ! Staging case {staging_id} ({esas_no}) oluşturulamadı")

        # 3. Belgeleri aktar
        print(f"\n⏳ Belgeler aktarılıyor...")
        ins, sk_map, sk_no, exists, no_case = migrate_documents(s_cur, l_cur, case_mapping)
        print(f"   ✓ Eklenen belge          : {ins}")
        print(f"   ~ Zaten vardı (atlandı)  : {exists}")
        print(f"   ✗ Case bulunamadı        : {sk_no}")

        # 4. Analysis cache
        print(f"\n⏳ AI analiz cache aktarılıyor...")
        ac_copied, ac_skipped = migrate_analysis_cache(s_cur, l_cur)
        print(f"   ✓ Kopyalanan cache       : {ac_copied}")
        print(f"   ~ Zaten vardı (atlandı)  : {ac_skipped}")

        # 5. Commit
        l_conn.commit()
        print(f"\n{'='*70}")
        print(f"  ✅ MİGRASYON TAMAMLANDI")
        print(f"     Belge eklendi: {ins}  |  Cache eklendi: {ac_copied}")
        if no_case:
            print(f"\n  ⚠️  Case eşleşemeyen belgeler ({len(no_case)} adet):")
            for fn in no_case:
                print(f"     - {fn}")
        print(f"{'='*70}\n")

    except Exception as e:
        l_conn.rollback()
        print(f"\n❌ HATA: {e}")
        raise
    finally:
        s_cur.close()
        l_cur.close()
        s_conn.close()
        l_conn.close()


if __name__ == "__main__":
    main()
