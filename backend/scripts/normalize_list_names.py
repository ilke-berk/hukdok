#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Referans listelerindeki adları saklama formatına çevirir: her kelimenin ilk harfi
büyük, kalanı küçük ("DOKTOR" → "Doktor", "özel müvekkil" → "Özel Müvekkil").

Kural yeni eklemelerde/düzenlemelerde zaten uygulanıyor (normalize_list_name);
bu script kural öncesinde girilmiş eski kayıtları toplu olarak hizalar.

Ne yapar:
  - 13 referans listesinin tamamını tarar (avukat ve e-posta alıcısı adları dahil).
  - Formatı bozuk her ad için update_item çağırır → ad düzelir VE eski adı taşıyan
    dava / müvekkil / belge kayıtları da yeni ada güncellenir (DEPENDENCIES).
  - Aynı ada iki farklı yazımla sahip kayıtlar (örn. "DOKTOR" + "Doktor") çakışma
    verir; bunlar birleştirme gerektirdiği için raporlanır, dokunulmaz —
    yönetim panelindeki "sil → başka değere taşı" akışıyla elle birleştirin.

Güvenlik:
  - VARSAYILAN DRY-RUN: hiçbir şey yazmaz, sadece ne yapacağını raporlar.
  - Yazmak için açıkça `--apply` ver.
  - Idempotent: tekrar çalıştırmak zararsız.

DİKKAT — avukat listesi:
  Adlar ASCII BÜYÜK HARFLE girilmişse I/İ ayrımı kaybolmuştur; kural 'KERIM'i
  'Kerım' yapar (doğrusu 'Kerim'). Türkçe yazılmış adlar ('KEZİBAN' → 'Keziban')
  sorunsuzdur. Avukatları toplu geçirmeden önce dry-run çıktısını okuyun; şüpheli
  olanları yönetim panelinden elle düzeltmek daha güvenlidir.

Kullanım (prod, mesai dışı):
  docker compose exec -T backend python scripts/normalize_list_names.py                       # dry-run, tüm listeler
  docker compose exec -T backend python scripts/normalize_list_names.py --only doctypes cities
  docker compose exec -T backend python scripts/normalize_list_names.py --skip lawyers --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

from database import SessionLocal  # noqa: E402
from managers.reference_lists import (  # noqa: E402
    LIST_REGISTRY, DuplicateItemError, normalize_list_name, update_item,
)


def run(apply_changes: bool, only: list = None, skip: list = None):
    scanned = 0
    fixed = 0
    propagated = 0
    conflicts = []   # (liste, mevcut_ad, hedef_ad)
    failures = []    # (liste, kimlik, sebep)

    selected = {
        lt: spec for lt, spec in LIST_REGISTRY.items()
        if (not only or lt in only) and lt not in (skip or [])
    }
    if only:
        bilinmeyen = set(only) - set(LIST_REGISTRY)
        if bilinmeyen:
            print(f"UYARI: bilinmeyen liste(ler) yok sayıldı: {', '.join(sorted(bilinmeyen))}")
    print(f"Taranacak liste: {', '.join(selected) or '(yok)'}\n")

    for list_type, spec in selected.items():
        db = SessionLocal()
        try:
            rows = db.query(spec.model).all()
            targets = [
                (getattr(r, spec.key), r.name, normalize_list_name(r.name))
                for r in rows if getattr(r, "name", None)
            ]
        finally:
            db.close()

        scanned += len(targets)
        bozuk = [t for t in targets if t[1] != t[2]]
        if not bozuk:
            continue

        print(f"\n{list_type} — {len(bozuk)}/{len(targets)} kayıt formata uymuyor")
        for identifier, old_name, new_name in bozuk:
            print(f"  {old_name!r} → {new_name!r}")
            if not apply_changes:
                continue
            try:
                result = update_item(list_type, identifier, {"name": new_name})
            except DuplicateItemError as e:
                # Aynı ad başka bir yazımla zaten listede — birleştirme kararı kullanıcının
                conflicts.append((list_type, old_name, new_name))
                print(f"    ATLANDI (çakışma): {e}")
                continue
            if not result:
                failures.append((list_type, identifier, "update_item başarısız"))
                print("    HATA: güncellenemedi")
                continue
            fixed += 1
            propagated += result["updated"]
            if result["updated"]:
                print(f"    → bağlı {result['updated']} kayıt da güncellendi")

    print("\n" + "=" * 60)
    print(f"Taranan ad: {scanned}")
    if apply_changes:
        print(f"Düzeltilen: {fixed}  |  Yansıyan bağlı kayıt: {propagated}")
        if conflicts:
            print(f"\nÇakışma nedeniyle atlanan {len(conflicts)} kayıt "
                  "(yönetim panelinden 'sil → başka değere taşı' ile birleştirin):")
            for list_type, old_name, new_name in conflicts:
                print(f"  {list_type}: {old_name!r} → {new_name!r} zaten var")
        if failures:
            print(f"\nHata alan {len(failures)} kayıt:")
            for list_type, identifier, reason in failures:
                print(f"  {list_type}/{identifier}: {reason}")
    else:
        print("DRY-RUN — hiçbir şey yazılmadı. Uygulamak için: --apply")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Referans listesi adlarını başlık formatına çevirir")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri veritabanına yaz")
    parser.add_argument("--only", nargs="+", metavar="LISTE",
                        help=f"Yalnızca bu listeler ({', '.join(LIST_REGISTRY)})")
    parser.add_argument("--skip", nargs="+", metavar="LISTE", help="Bu listeleri atla")
    args = parser.parse_args()
    run(args.apply, args.only, args.skip)
