"""
Gönderilen e-postaları kontrol eder.
Kullanım (production sunucuda):
  docker exec hukudok-automator-main-backend-1 python check_sent_emails.py
  docker exec hukudok-automator-main-backend-1 python check_sent_emails.py --since 2026-04-16
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Backend dizinini path'e ekle
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import requests
from sharepoint.auth_graph import get_graph_token

GRAPH = "https://graph.microsoft.com/v1.0"


def check_sent_emails(since: str = "2026-04-16", sender: str = None):
    if sender is None:
        sender = os.getenv("EMAIL_SENDER", "arsiv@lexisbio.onmicrosoft.com")

    print(f"\n{'='*60}")
    print(f"Gönderen  : {sender}")
    print(f"Başlangıç : {since}")
    print(f"{'='*60}\n")

    try:
        token = get_graph_token()
    except Exception as e:
        print(f"❌ Token alınamadı: {e}")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # ISO 8601 formatında tarih filtresi
    since_iso = f"{since}T00:00:00Z"

    url = (
        f"{GRAPH}/users/{sender}/mailFolders/sentItems/messages"
        f"?$filter=sentDateTime ge {since_iso}"
        f"&$select=subject,toRecipients,ccRecipients,sentDateTime,hasAttachments"
        f"&$orderby=sentDateTime desc"
        f"&$top=100"
    )

    all_messages = []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        if not resp.ok:
            print(f"❌ Graph API hatası: {resp.status_code} — {resp.text[:300]}")
            return
        data = resp.json()
        all_messages.extend(data.get("value", []))
        url = data.get("@odata.nextLink")  # sayfalama

    if not all_messages:
        print("⚠️  Bu tarihten sonra gönderilen e-posta bulunamadı.")
        print("   → Ya hiç mail gönderilmedi, ya da Mail.Read izni eksik.\n")
        return

    print(f"✅ Toplam {len(all_messages)} e-posta bulundu:\n")
    print(f"{'Tarih':<22} {'Konu':<50} {'Alıcı'}")
    print("-" * 100)

    for msg in all_messages:
        sent_dt = msg.get("sentDateTime", "")
        # UTC → Türkiye saati (+3)
        try:
            dt = datetime.fromisoformat(sent_dt.replace("Z", "+00:00"))
            sent_local = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        except Exception:
            sent_local = sent_dt[:16]

        subject = msg.get("subject", "")[:48]
        recipients = msg.get("toRecipients", [])
        to_str = ", ".join(r["emailAddress"]["address"] for r in recipients[:3])
        if len(recipients) > 3:
            to_str += f" (+{len(recipients)-3})"

        ek = "📎" if msg.get("hasAttachments") else "  "
        print(f"{sent_local:<22} {ek} {subject:<48} {to_str}")

    print(f"\n{'='*60}")
    print(f"Toplam: {len(all_messages)} mail, {since} tarihinden itibaren")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-04-16", help="Başlangıç tarihi YYYY-MM-DD")
    parser.add_argument("--sender", default=None, help="Gönderici e-posta (varsayılan: .env'den)")
    args = parser.parse_args()
    check_sent_emails(since=args.since, sender=args.sender)
