#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Track B — Mevcut dava verisindeki sorumlu avukat alanını canonical hale getirir.

Ne yapar:
  - Her aktif davanın `responsible_lawyer_name` değerini merkezi resolver'dan geçirir.
  - Çözülenler için: `responsible_lawyer_name`'i canonical forma yazar ve
    `case_lawyers` (lawyer_id FK) ilişkisini yeniden kurar.
  - Değişiklikleri `case_history`'ye (denetim izi) kaydeder — orijinal değer korunur.
  - Çözülemeyenleri `unmatched_lawyers.csv`'ye döker (elle düzeltme kuyruğu).

Güvenlik:
  - VARSAYILAN DRY-RUN: hiçbir şey yazmaz, sadece ne yapacağını raporlar.
  - Yazmak için açıkça `--apply` ver.
  - Idempotent: tekrar çalıştırmak zararsız (zaten canonical olanı tekrar yazmaz).

Kullanım (prod, mesai dışı):
  docker compose exec -T backend python normalize_lawyers.py            # dry-run
  docker compose exec -T backend python normalize_lawyers.py --apply    # uygula
"""
import argparse
import csv

import models
from database import SessionLocal
from managers.admin_manager import resolve_lawyers_field


def run(apply_changes: bool):
    db = SessionLocal()
    total = 0
    name_changes = 0
    relinked = 0
    cases_with_unresolved = 0
    unresolved_rows = []  # (case_id, tracking_no, raw, unresolved_part)

    try:
        cases = db.query(models.Case).filter(models.Case.active == True).all()
        print(f"Taranan aktif dava: {len(cases)}")

        for c in cases:
            total += 1
            raw = c.responsible_lawyer_name
            if not raw or not raw.strip():
                continue

            resolved = resolve_lawyers_field(raw)
            if not resolved:
                continue

            canonical_names = []
            caselawyers = []   # (code|None, name)
            row_unresolved = []
            for (m, part) in resolved:
                if m:
                    canonical_names.append(m.get("name"))
                    caselawyers.append((m.get("code"), m.get("name")))
                else:
                    canonical_names.append(part)
                    caselawyers.append((None, part))
                    row_unresolved.append(part)

            canonical = ", ".join(canonical_names)
            need_name_change = (canonical != raw)

            if row_unresolved:
                cases_with_unresolved += 1
                for u in row_unresolved:
                    unresolved_rows.append((c.id, c.tracking_no, raw, u))

            if apply_changes:
                # case_lawyers'i her zaman yeniden kur (FK'leri canonical'e bağla)
                db.query(models.CaseLawyer).filter(models.CaseLawyer.case_id == c.id).delete()
                for (code, name) in caselawyers:
                    lid = None
                    if code:
                        lrow = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
                        lid = lrow.id if lrow else None
                    db.add(models.CaseLawyer(case_id=c.id, lawyer_id=lid, name=name))
                relinked += 1

                if need_name_change:
                    db.add(models.CaseHistory(
                        case_id=c.id,
                        field_name="responsible_lawyer_name",
                        old_value=raw,
                        new_value=canonical,
                    ))
                    c.responsible_lawyer_name = canonical

            if need_name_change:
                name_changes += 1
                if total <= 0 or name_changes <= 20:
                    print(f"  [{c.tracking_no}] '{raw}'  ->  '{canonical}'")

        if apply_changes:
            db.commit()

        if unresolved_rows:
            with open("unmatched_lawyers.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["case_id", "tracking_no", "responsible_lawyer_name", "unresolved_part"])
                w.writerows(unresolved_rows)

        print()
        print("=" * 56)
        print(f"{'[UYGULANDI]' if apply_changes else '[DRY-RUN]'} TAMAMLANDI")
        print(f"  Toplam aktif dava           : {total}")
        print(f"  Canonical'e çevrilecek ad   : {name_changes}")
        if apply_changes:
            print(f"  case_lawyers yeniden kuruldu : {relinked}")
        print(f"  Çözülemeyen içeren dava      : {cases_with_unresolved}")
        if unresolved_rows:
            print(f"  -> Detay: unmatched_lawyers.csv ({len(unresolved_rows)} satır)")
        if not apply_changes:
            print("  NOT: Hiçbir şey yazılmadı. Uygulamak için: --apply")
        print("=" * 56)

    except Exception as e:
        print(f"[KRİTİK HATA] {e}")
        if apply_changes:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sorumlu avukat alanını canonical hale getirir.")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri DB'ye yaz (varsayılan: dry-run)")
    args = parser.parse_args()
    run(apply_changes=args.apply)
