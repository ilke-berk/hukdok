#!/usr/bin/env python3
"""`cases.missing_required_bucket` toplu tazeleme — KURAL DEĞİŞİKLİĞİ sonrası (G158).

    docker compose exec -T backend python scripts/backfill_missing_required.py            # kuru koşu
    docker compose exec -T backend python scripts/backfill_missing_required.py --apply    # yazar

Bayrak türetilmiş kolondur; tek yazma yolu `case_manager.refresh_missing_required`.
Kural (`required_fields.py`) değiştiğinde mevcut satırlar doğru yollardan
yazılmış olsa da yeni kurala göre bayattır — bu script onları migrasyon 33'ün
backfill'iyle AYNI `missing_bucket_sql` ifadesiyle yeniden hesaplar (ikinci
bir kural listesi yoktur). İkinci koşu 0 satır değiştirir (idempotent).

İlk kullanım: M5 — çoklu avukatlı (`case_lawyers` ≥ 2), kutusu boş kart artık
"eksik sorumlu avukat" sayılmaz. Bayat bayrağın SEBEBİ kural değişikliği
değilse (bir yazma yolu kaçmışsa) bu script'i değil
`audit_missing_required_flags` çıktısını kullan ve o yolu düzelt.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modülleri için


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Yaz (varsayılan: kuru koşu, yalnız sayar)")
    args = parser.parse_args()

    from managers.case_manager import backfill_missing_required_flags

    rapor = backfill_missing_required_flags(apply=args.apply)
    mod = "UYGULANDI" if args.apply else "KURU KOŞU"
    # Elle koşulan script: çıktı stdout'a (loglama yapılandırması yalnız
    # logging_setup.configure_logging'de yaşar — Faz 2-B bekçisi).
    print(
        f"[{mod}] toplam kart: {rapor['toplam']} | kurala göre değişecek: {rapor['degisecek']} "
        f"| yazılan: {rapor['uygulanan']}"
    )
    if not args.apply and rapor["degisecek"]:
        print("Yazmak için: --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
