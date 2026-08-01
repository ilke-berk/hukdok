"""
Eski davaların judicial_unit (Yargı Birimi) alanını mahkeme adından türetir.

Arka plan (2026-07-31): Yargı Birimi form seçimi bugüne dek payload'a
girmediği için hiçbir kayıtta yok (0/14.345). Bilgi mahkeme adının içinde
("Şişli 1. Sulh Hukuk Mahkemesi" → SULH HUKUK MAHKEMESİ) — bu script onu
bilinen kalıplarla çıkarır ve YALNIZ judicial_unit'i boş kayıtlara yazar
(elle girilmiş değer ezilmez; tekrar çalıştırmak güvenlidir).

Yazılan değerler court_types referans sözlüğüyle hizalıdır; sözlükte
olmayan hedefler (örn. TAHKİM HEYETİ) --apply sırasında court_types'a da
eklenir ki dava formundaki Yargı Birimi seçicisinde görünebilsinler.

Kullanım (konteynerde; DB host'u 'postgres' yalnız orada çözülür):
  docker compose exec backend python scripts/backfill_judicial_unit.py           # kuru çalıştırma
  docker compose exec backend python scripts/backfill_judicial_unit.py --apply   # DB'ye yaz
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv("../.env")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

import models
from database import SessionLocal

# Kalıplar + türetme tek kaynaktan: sihirbaz merge akışı da aynı modülü kullanır
from services.judicial_unit import PATTERNS, derive_judicial_unit, normalize_court as _normalize


def _slug(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", _normalize(name)).strip("-")[:40]


def ensure_court_types(db, used_names: "set[str]", apply: bool) -> "list[str]":
    """Kanonik hedeflerden court_types'ta olmayanları (normalize kıyasla) ekler."""
    existing = {_normalize(ct.name) for ct in db.query(models.CourtType.name).all()}
    parent_by_name = {name: parent for _rx, name, parent in PATTERNS}
    missing = [n for n in sorted(used_names) if _normalize(n) not in existing]
    if apply and missing:
        next_seq = db.query(models.CourtType).count()
        for i, name in enumerate(missing):
            db.add(models.CourtType(
                code=_slug(name), name=name,
                parent_code=parent_by_name[name], active=True, sequence=next_seq + i,
            ))
    return missing


def run(apply: bool):
    db = SessionLocal()
    try:
        rows = db.query(
            models.Case.id, models.Case.court, models.Case.judicial_unit
        ).all()

        updates: "defaultdict[str, list[int]]" = defaultdict(list)
        unmatched: Counter = Counter()
        already_filled = no_court = 0

        for cid, court, ju in rows:
            if ju and str(ju).strip():
                already_filled += 1
                continue
            if not court or not str(court).strip():
                no_court += 1
                continue
            derived = derive_judicial_unit(court)
            if derived:
                updates[derived].append(cid)
            else:
                unmatched[str(court).strip()] += 1

        total_update = sum(len(v) for v in updates.values())
        print(f"Toplam kayıt         : {len(rows)}")
        print(f"Zaten dolu (atlandı) : {already_filled}")
        print(f"Mahkeme adı boş      : {no_court}")
        print(f"Türetilen            : {total_update}")
        print(f"Eşleşmeyen           : {sum(unmatched.values())}")
        print()
        print("── Türetilen dağılım ────────────────────────────────")
        for name, ids in sorted(updates.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(ids):>6}  {name}")

        missing_ref = ensure_court_types(db, set(updates.keys()), apply)
        if missing_ref:
            print()
            print("court_types sözlüğünde olmayan hedefler"
                  + (" (eklendi):" if apply else " (--apply ile eklenecek):"))
            for n in missing_ref:
                print(f"  + {n}")

        if unmatched:
            print()
            print("── Eşleşmeyen mahkeme adları (ilk 40) ───────────────")
            for court, cnt in unmatched.most_common(40):
                print(f"  {cnt:>5}  {court}")

        if not apply:
            print("\nKuru çalıştırma — DB'ye yazılmadı. Yazmak için: --apply")
            return

        for name, ids in updates.items():
            for i in range(0, len(ids), 1000):
                db.query(models.Case).filter(models.Case.id.in_(ids[i:i + 1000])).update(
                    {models.Case.judicial_unit: name}, synchronize_session=False
                )
        db.commit()
        print(f"\n✅ {total_update} kayda judicial_unit yazıldı"
              + (f", {len(missing_ref)} court_types girdisi eklendi." if missing_ref else "."))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="judicial_unit geriye dönük doldurma")
    parser.add_argument("--apply", action="store_true", help="DB'ye yaz (varsayılan: kuru çalıştırma)")
    args = parser.parse_args()
    run(apply=args.apply)
