"""
vekalet_listesi.xlsx dosyasından avukatları veritabanına aktarır.
Yeni avukatlar eklenir; mevcutlar tüm alanlar bakımından güncellenir.
Kullanim: python import_lawyers_excel.py [--db-url postgresql://...]
"""
import sys
import os
import argparse
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
_script_dir = Path(__file__).parent
for _env in [_script_dir / ".env", _script_dir.parent / ".env"]:
    if _env.exists():
        load_dotenv(_env)
        print(f".env yuklendi: {_env}")
        break

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--db-url", default=None)
_args, _ = _ap.parse_known_args()
if _args.db_url:
    os.environ["DATABASE_URL"] = _args.db_url

sys.path.insert(0, str(_script_dir))

import openpyxl
from database import SessionLocal
import models


EXCEL_PATH = r"C:\Users\ilkeb\OneDrive\Masaüstü\vekalet_listesi.xlsx"


def latinize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name.upper())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn" and c.isalpha())


def make_code(name: str) -> str:
    cleaned = re.sub(r"[^A-Z]", " ", latinize(name)).split()
    if not cleaned:
        return "AV"
    if len(cleaned) == 1:
        return cleaned[0][:8]
    initials = "".join(p[0] for p in cleaned[:-1])
    last = cleaned[-1][:6]
    return (initials + last)[:12]


def ensure_unique_code(base: str, existing: set) -> str:
    code = base
    suffix = 2
    while code in existing:
        code = f"{base}{suffix}"
        suffix += 1
    return code


def safe_digits(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"[^0-9]", "", str(v))
    return s if s else None


def clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def run():
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb.active

    # Kolon sırası: İsim | tcKNo | Görev | E-Mail | Cep Tel | AdresEv | sicil no
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    db = SessionLocal()
    try:
        existing_codes: set = {r[0] for r in db.query(models.Lawyer.code).all()}

        added = 0
        updated = 0
        skipped = 0

        for row in rows:
            if not any(v is not None for v in row):
                continue

            cols = list(row) + [None] * 7  # padding
            name_raw, tc_raw, gorev_raw, email_raw, phone_raw, address_raw, sicil_raw = cols[:7]

            if not name_raw:
                continue

            name    = str(name_raw).strip()
            tc_no   = safe_digits(tc_raw)
            gorev   = clean_str(gorev_raw)
            email   = clean_str(email_raw)
            phone   = clean_str(phone_raw)
            address = clean_str(address_raw)
            sicil_no = safe_digits(sicil_raw)

            existing = db.query(models.Lawyer).filter(
                models.Lawyer.name.ilike(name)
            ).first()

            if existing:
                # Tüm alanları güncelle (boş gelenleri de yaz)
                existing.tc_no   = tc_no   or existing.tc_no
                existing.sicil_no = sicil_no or existing.sicil_no
                existing.gorev   = gorev   or existing.gorev
                existing.email   = email   or existing.email
                existing.phone   = phone   or existing.phone
                existing.address = address or existing.address
                updated += 1
                print(f"  GUNCELLENDI: {name}")
            else:
                code_base = make_code(name)
                code = ensure_unique_code(code_base, existing_codes)
                existing_codes.add(code)

                lawyer = models.Lawyer(
                    code=code, name=name, active=True,
                    tc_no=tc_no, sicil_no=sicil_no,
                    gorev=gorev, email=email, phone=phone, address=address,
                )
                db.add(lawyer)
                added += 1
                print(f"  EKLENDI: {name} [{code}]  TC:{tc_no}  Sicil:{sicil_no}  Mail:{email}  Tel:{phone}")

        db.commit()
        print(f"\nTamamlandi: {added} eklendi, {updated} guncellendi, {skipped} atlandi.")

    except Exception as e:
        db.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        db.close()

    try:
        from managers.admin_manager import refresh_cache
        refresh_cache("lawyers")
        print("Config cache guncellendi.")
    except Exception:
        print("Cache guncellenemedi (sunucu calismiyor olabilir).")


if __name__ == "__main__":
    run()
