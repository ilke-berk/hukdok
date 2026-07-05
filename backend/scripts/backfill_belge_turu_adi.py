"""
Tek seferlik onarim: CaseDocument.belge_turu_adi alanina ham kod sizmis
kayitlari (orn. "ARA-KRR", "VEKALET") doctype tam adina ("Ara Karar",
"Vekaletname") cevirir.

Kok neden get_doctype_label'daki padding uyumsuzluguydu (config kodu
"ARA-KRR_______" iken gelen kod "ARA-KRR" oldugu icin eslesemiyordu) ve
duzeltildi. Bu script, hata duzelmeden once kaydedilmis eski satirlari
toplu olarak onarir. Yeni kayitlar zaten dogru ad ile yazilir.

Calistirma (prod, mesai disi):
    docker compose exec backend python scripts/backfill_belge_turu_adi.py           # onizleme (dry-run)
    docker compose exec backend python scripts/backfill_belge_turu_adi.py --apply   # uygula
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

from database import SessionLocal
import models


def _norm(code: str) -> str:
    """Kod karsilastirmasi icin normalize eder (padding/ayrac/buyuk-kucuk harf)."""
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        # kod(normalize) -> tam ad haritasi
        doctypes = db.query(models.DocType).all()
        by_norm = {_norm(d.code): d.name for d in doctypes if d.code and d.name}

        docs = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.belge_turu_kodu.isnot(None))
            .all()
        )

        fixed = 0
        for d in docs:
            proper = by_norm.get(_norm(d.belge_turu_kodu))
            if proper and (d.belge_turu_adi or "") != proper:
                print(f"  #{d.id}: {d.belge_turu_adi!r} -> {proper!r}")
                if apply:
                    d.belge_turu_adi = proper
                fixed += 1

        if apply:
            db.commit()
            print(f"\nUYGULANDI: {fixed} kayit guncellendi.")
        else:
            print(f"\nDRY-RUN: {fixed} kayit guncellenecek. Uygulamak icin --apply ekleyin.")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
