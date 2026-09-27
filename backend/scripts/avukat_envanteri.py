"""Avukat envanteri betiği — geçiş adımlarının "önce fotoğraf → adım → karşılaştır" kapısı (G224).

Salt okunurdur: DB'ye yazmaz. Ölçüm `services/avukat_envanteri.py`'dedir.

Kullanım (konteynerde; dosya yolu KONTEYNER yoludur):
    docker compose exec -T backend python scripts/avukat_envanteri.py --kaydet /app/avukat_envanteri_once.json
    # ... veri adımı ...
    docker compose exec -T backend python scripts/avukat_envanteri.py --karsilastir /app/avukat_envanteri_once.json

`--karsilastir` İHLAL bulursa listeler ve çıkış kodu 1 döner (adım geri alınır);
`--kaydet` ile birlikte verilirse şimdiki fotoğraf ayrıca o dosyaya yazılır.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import avukat_envanteri as env


def fotograf_al(fabrika) -> dict:
    db = fabrika()
    try:
        return env.olc(db)
    finally:
        db.close()


def kaydet(foto: dict, yol: str) -> None:
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(foto, f, ensure_ascii=False, indent=2)


def oku(yol: str) -> dict:
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def kos(fabrika, kaydet_yolu: Optional[str], karsilastir_yolu: Optional[str]) -> int:
    """Betiğin gövdesi (testten fabrikayla çağrılır). Dönen: çıkış kodu."""
    once = oku(karsilastir_yolu) if karsilastir_yolu else None
    foto = fotograf_al(fabrika)
    print(env.ozet_metni(foto))
    if kaydet_yolu:
        kaydet(foto, kaydet_yolu)
        print(f"fotoğraf yazıldı: {kaydet_yolu}")
    if once is None:
        return 0
    fark = env.karsilastir(once, foto)
    print(env.fark_metni(fark))
    return 1 if env.ihlaller(fark) else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Avukat envanteri: fotoğraf al / karşılaştır")
    ayristirici.add_argument("--kaydet", metavar="DOSYA", help="şimdiki fotoğrafı JSON olarak yaz")
    ayristirici.add_argument("--karsilastir", metavar="ONCE_JSON",
                             help="önceki fotoğrafla karşılaştır; İHLAL varsa çıkış kodu 1")
    args = ayristirici.parse_args(argv)
    if not args.kaydet and not args.karsilastir:
        ayristirici.error("--kaydet ya da --karsilastir verilmeli")

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    return kos(SessionLocal, args.kaydet, args.karsilastir)


if __name__ == "__main__":
    sys.exit(main())
