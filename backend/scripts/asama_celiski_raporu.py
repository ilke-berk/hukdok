#!/usr/bin/env python3
"""Aşama çelişki raporu — ince CLI (G157). Mantık `services/asama_celiski_raporu.py`.

Üretim (paket + DB → ekibe giden xlsx; SALT OKUNUR, hiçbir tabloya yazmaz):

    docker compose exec -T backend python scripts/asama_celiski_raporu.py \\
        --paket /tmp/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --cikti-dizini /tmp/rapor [--tarih 2026-09-10]

Geri okuma (ekibin CEVAPLI xlsx'i → sınıf başına HATA/BELİRSİZ/SEBEBİ VAR + Düzeltme_Logu beklentisi):

    docker compose exec -T backend python scripts/asama_celiski_raporu.py \\
        --cevap /tmp/HUKDOK_ASAMA_CELISKILERI_2026-09-06_CEVAPLI.xlsx [--beklenti-csv /tmp/beklenti.csv]

Gerçek paket ve cevap dosyası repoya girmez (A.2).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import hukdok_aktarim as ha
from services import asama_celiski_raporu as acr

logger = logging.getLogger("AsamaCeliskiRaporuCLI")


def uretim_ozeti(yol: Path, celiskiler: List[acr.CeliskiGrubu]) -> str:
    sayim = acr.sinif_sayimi(celiskiler)
    satirlar = ["=" * 70, "Aşama çelişki raporu (G157)", "=" * 70]
    for sinif, (no, ad, _) in acr.SINIFLAR.items():
        satirlar.append(f"  S{no} {ad:<34} {sayim[sinif]:>5}")
    e8 = sum(1 for c in celiskiler if c.etiket)
    satirlar.append(f"  {'Toplam':<37} {len(celiskiler):>5}   (E-8 etiketli: {e8})")
    satirlar.append(f"  xlsx: {yol}")
    satirlar.append("=" * 70)
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None, *, session_factory: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Aşama çelişki raporu üretir ya da ekibin cevabını geri okur (G157)")
    parser.add_argument("--paket", help="teslim paketi xlsx (Sheet + Karar_Asamalari)")
    parser.add_argument("--cikti-dizini", help="xlsx'in yazılacağı dizin")
    parser.add_argument("--tarih", default=date.today().isoformat(), help="dosya adındaki tarih (YYYY-MM-DD)")
    parser.add_argument("--cevap", help="ekibin CEVAPLI xlsx'i (geri okuma kipi)")
    parser.add_argument("--beklenti-csv", help="geri okuma: HATA satırlarını bu CSV'ye yaz")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from logging_setup import configure_logging

    configure_logging()

    if args.cevap:
        try:
            ozet = acr.cevaplari_oku(Path(args.cevap))
        except ha.AktarimHatasi as exc:
            logger.error(f"Cevap dosyası okunamadı: {exc}")
            return ha.CIKIS_GIRDI
        print(acr.cevap_ozeti_metni(ozet))
        if args.beklenti_csv:
            print(f"  beklenti csv: {acr.beklenti_csv_yaz(ozet.beklentiler, Path(args.beklenti_csv))}")
        return ha.CIKIS_TAMAM

    if not args.paket or not args.cikti_dizini:
        parser.error("--paket ve --cikti-dizini (üretim) ya da --cevap (geri okuma) gerekli")
    if session_factory is None:
        from database import SessionLocal

        session_factory = SessionLocal
    db = session_factory()
    try:
        yol, celiskiler = acr.rapor_uret(db, Path(args.paket), Path(args.cikti_dizini), tarih=args.tarih)
    except ha.AktarimHatasi as exc:
        logger.error(f"Rapor üretilemedi: {exc}")
        return ha.CIKIS_GIRDI
    finally:
        db.close()
    print(uretim_ozeti(yol, celiskiler))
    return ha.CIKIS_TAMAM


if __name__ == "__main__":
    sys.exit(main())
