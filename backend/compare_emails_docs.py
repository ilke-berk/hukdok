"""
Production belgelerini gönderilen e-postalarla karşılaştırır.
Mail gönderilmemiş belgeleri listeler.

Kullanım:
  python compare_emails_docs.py                        # 16 Nisan'dan itibaren
  python compare_emails_docs.py --since 2026-04-14     # belirli tarihten
  python compare_emails_docs.py --db-url postgresql://... --since 2026-04-14

Eşleşme katmanları:
  strict  → ±60 dk pencere — kesinlikle gönderilmiş
  loose   → -2sa / +4sa    — büyük ihtimalle gönderilmiş (gecikmeli bg task)
  day     → aynı gün       — batch yükleme olabilir
  none    → eşleşme yok    — şüpheli, incelenmeli
"""

import sys, os, re, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import requests
from sharepoint.auth_graph import get_graph_token

GRAPH  = "https://graph.microsoft.com/v1.0"
SENDER = os.getenv("EMAIL_SENDER", "arsiv@lexisbio.onmicrosoft.com")
IST    = timezone(timedelta(hours=3))


# ── 1. Graph API ──────────────────────────────────────────────────────────────

def fetch_sent_emails(since_iso: str) -> list[dict]:
    try:
        token = get_graph_token()
    except Exception as e:
        print(f"❌ Token alınamadı: {e}")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    test = requests.get(
        f"{GRAPH}/users/{SENDER}/mailFolders/sentItems/messages?$top=1",
        headers=headers, timeout=15,
    )
    if test.status_code == 403:
        print("\n❌ Mail.Read izni yok!")
        print("   Azure Portal → App Registrations → API Permissions →")
        print("   Microsoft Graph → Application permissions → Mail.Read → Grant admin consent\n")
        sys.exit(1)
    if not test.ok:
        print(f"❌ Graph API hatası: {test.status_code} {test.text[:200]}")
        sys.exit(1)

    url = (
        f"{GRAPH}/users/{SENDER}/mailFolders/sentItems/messages"
        f"?$filter=sentDateTime ge {since_iso}"
        f"&$select=subject,sentDateTime,toRecipients"
        f"&$orderby=sentDateTime asc"
        f"&$top=100"
    )

    all_msgs = []
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        if not r.ok:
            print(f"❌ Mail fetch hatası: {r.status_code} {r.text[:200]}")
            break
        data = r.json()
        all_msgs.extend(data.get("value", []))
        url = data.get("@odata.nextLink")

    return all_msgs


# ── 2. Veritabanı ─────────────────────────────────────────────────────────────

def fetch_documents(since: str, db_url: str) -> list[dict]:
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute("""
            SELECT d.id, d.stored_filename, d.belge_turu_adi, d.muvekkil_adi,
                   d.uploaded_by, d.uploaded_at AT TIME ZONE 'Europe/Istanbul',
                   c.tracking_no, c.responsible_lawyer_name
            FROM case_documents d
            LEFT JOIN cases c ON d.case_id = c.id
            WHERE d.uploaded_at >= %s
            ORDER BY d.uploaded_at
        """, (since + " 00:00:00+03",))
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "filename": r[1], "belge_turu": r[2] or "",
                "muvekkil": r[3] or "", "uploaded_by": r[4] or "",
                "uploaded_at": r[5], "tracking_no": r[6] or "",
                "lawyer": r[7] or "",
            }
            for r in rows
        ]
    except ImportError:
        return _fetch_docs_sqlalchemy(since)
    except Exception as e:
        print(f"❌ DB bağlantı hatası: {e}")
        sys.exit(1)


def _fetch_docs_sqlalchemy(since: str) -> list[dict]:
    from database import SessionLocal
    from models import CaseDocument
    from sqlalchemy.orm import joinedload

    cutoff = datetime.fromisoformat(since + "T00:00:00+03:00")
    db = SessionLocal()
    try:
        docs = (
            db.query(CaseDocument)
            .options(joinedload(CaseDocument.case))
            .filter(CaseDocument.uploaded_at >= cutoff)
            .order_by(CaseDocument.uploaded_at)
            .all()
        )
        return [
            {
                "id": d.id,
                "filename": d.stored_filename,
                "belge_turu": d.belge_turu_adi or "",
                "muvekkil": d.muvekkil_adi or "",
                "uploaded_by": d.uploaded_by or "",
                "uploaded_at": d.uploaded_at,
                "tracking_no": d.case.tracking_no if d.case else "",
                "lawyer": d.case.responsible_lawyer_name if d.case else "",
            }
            for d in docs
        ]
    finally:
        db.close()


# ── 3. Yardımcı fonksiyonlar ─────────────────────────────────────────────────

def normalize(text: str) -> str:
    tr = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    return re.sub(r"[^a-z0-9]", "", text.lower().translate(tr))


def parse_subject(subject: str) -> dict:
    for pat in [r"\[HukDok\]\s*(.+?)\s*-\s*(.+?)(?:\s*\|\s*(.+))?$",
                r"\[HukuDok\]\s*(.+?)\s*-\s*(.+?)(?:\s*\|\s*(.+))?$"]:
        m = re.match(pat, subject)
        if m:
            return {"belge_turu": m.group(1).strip(),
                    "muvekkil": m.group(2).strip(),
                    "sender": (m.group(3) or "").strip()}
    return {"belge_turu": "", "muvekkil": subject, "sender": ""}


def name_match(a: str, b: str) -> bool:
    """İki normalize ismin yeterince örtüşüp örtüşmediğini kontrol eder."""
    if not a or not b:
        return False
    # Prefix kontrolü (6 karakter)
    if len(a) >= 6 and a[:6] in b:
        return True
    if len(b) >= 6 and b[:6] in a:
        return True
    # Token tabanlı: ≥4 karakterli ortak kelime varsa eşleşme
    a_tokens = set(re.findall(r'[a-z0-9]{4,}', a))
    b_tokens = set(re.findall(r'[a-z0-9]{4,}', b))
    return bool(a_tokens & b_tokens)


def to_utc(dt) -> datetime | None:
    try:
        if getattr(dt, "tzinfo", None):
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=IST).astimezone(timezone.utc)
    except Exception:
        return None


def to_ist_date(dt):
    utc = to_utc(dt)
    return utc.astimezone(IST).date() if utc else None


# ── 4. Eşleştirme ─────────────────────────────────────────────────────────────

def match_doc(doc: dict, emails: list[dict]) -> tuple[dict | None, str | None]:
    """
    Returns (email | None, confidence | None)
    confidence: 'strict' | 'loose' | 'day' | None
    """
    doc_n    = normalize(doc["muvekkil"])
    doc_utc  = to_utc(doc["uploaded_at"])
    doc_date = to_ist_date(doc["uploaded_at"])

    strict_hit = loose_hit = day_hit = None

    for email in emails:
        subj = email.get("subject", "")
        if "[HukDok]" not in subj and "[HukuDok]" not in subj:
            continue

        mail_n = normalize(parse_subject(subj)["muvekkil"])
        if not name_match(doc_n, mail_n):
            continue

        sent_str = email.get("sentDateTime", "")
        try:
            sent_dt = datetime.fromisoformat(sent_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Gün eşleştirmesi (İstanbul tarihi)
        if doc_date and day_hit is None:
            try:
                if sent_dt.astimezone(IST).date() == doc_date:
                    day_hit = email
            except Exception:
                pass

        if doc_utc:
            diff = (sent_dt - doc_utc).total_seconds()
            # strict: ±60 dk  (batch yükleme + gecikmeli bg task)
            if -3600 <= diff <= 3600 and strict_hit is None:
                strict_hit = email
            # loose: -2sa / +4sa  (ağır SharePoint yüklemeleri, sunucu yükü)
            elif -7200 <= diff <= 14400 and loose_hit is None:
                loose_hit = email

    if strict_hit:
        return strict_hit, "strict"
    if loose_hit:
        return loose_hit, "loose"
    if day_hit:
        return None, "day"
    return None, None


def any_email_for_client(doc_n: str, emails: list[dict]) -> bool:
    """Bu müvekkil için HİÇ mail gönderilmiş mi? (zaman fark etmez)"""
    for email in emails:
        subj = email.get("subject", "")
        if "[HukDok]" not in subj and "[HukuDok]" not in subj:
            continue
        if name_match(doc_n, normalize(parse_subject(subj)["muvekkil"])):
            return True
    return False


# ── 5. Ana akış ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since",  default="2026-04-16")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    since_iso = args.since + "T00:00:00Z"

    print(f"\n{'='*72}")
    print(f"  E-posta / Belge Karşılaştırması — {args.since} itibaren")
    print(f"  Gönderen: {SENDER}")
    print(f"{'='*72}\n")

    print("📬 Gönderilen e-postalar çekiliyor...")
    emails = fetch_sent_emails(since_iso)
    print(f"   → {len(emails)} [HukDok/HukuDok] maili bulundu\n")

    print("📂 Veritabanından belgeler çekiliyor...")
    docs = fetch_documents(args.since, args.db_url)
    print(f"   → {len(docs)} belge bulundu\n")

    matched      = []  # (doc, email, 'strict')
    maybe        = []  # (doc, email|None, 'loose'|'day')
    suspicious   = []  # doc — hiç mail yok veya zamanlama tutmuyor

    for doc in docs:
        email, conf = match_doc(doc, emails)
        if conf == "strict":
            matched.append((doc, email, conf))
        elif conf in ("loose", "day"):
            maybe.append((doc, email, conf))
        else:
            suspicious.append(doc)

    # ── Özet ──
    print(f"{'='*72}")
    print(f"  ✅ Kesin eşleşen   (mail gönderilmiş)       : {len(matched)}")
    print(f"  ⚠️  Muhtemelen eşleşen (geniş pencere/gün)  : {len(maybe)}")
    print(f"  ❌ Şüpheli         (mail gitmemiş olabilir) : {len(suspicious)}")
    print(f"{'='*72}\n")

    # ── Şüpheli belgeler ──
    if suspicious:
        print("❌ ŞÜPHELİ BELGELER:\n")
        print(f"{'ID':<5} {'Tarih':<17} {'Durum':<22} {'Dosya adı':<50} {'Müvekkil'}")
        print("-" * 130)
        for d in suspicious:
            dt     = str(d["uploaded_at"])[:16]
            doc_n  = normalize(d["muvekkil"])
            status = "zamanlama tutmadı" if any_email_for_client(doc_n, emails) else "❗ hiç mail yok"
            print(f"{d['id']:<5} {dt:<17} {status:<22} {d['filename'][:48]:<50} {d['muvekkil'][:28]}")
    else:
        print("✅ Şüpheli belge yok.\n")

    # ── Muhtemelen eşleşenler ──
    if maybe:
        print(f"\n⚠️  MUHTEMELEN GÖNDERİLMİŞ (doğrulama önerilebilir, {len(maybe)} adet):\n")
        print(f"{'ID':<5} {'Tarih':<17} {'Pencere':<8} {'Dosya adı':<50} {'Müvekkil'}")
        print("-" * 110)
        for d, email, conf in maybe:
            dt     = str(d["uploaded_at"])[:16]
            reason = "loose" if conf == "loose" else "gün"
            print(f"{d['id']:<5} {dt:<17} {reason:<8} {d['filename'][:48]:<50} {d['muvekkil'][:28]}")

    # ── Eşleşen örnek ──
    if matched:
        print(f"\n✅ EŞLEŞENLERİN ÖRNEĞİ (ilk 5):\n")
        for doc, email, _ in matched[:5]:
            print(f"  • {doc['filename'][:48]:<50} ←→  {email['subject'][:60]}")

    print()


if __name__ == "__main__":
    main()
