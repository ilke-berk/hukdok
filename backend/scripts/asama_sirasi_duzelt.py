#!/usr/bin/env python3
"""Teslim paketinin YALNIZ aşama katmanını (Karar_Asamalari) yeniden uygular.

Neden (veri ekibi 02.10 kontrolü, 1_KARAR_KUNYESI): aşama fotoğrafı en yüksek
`sira_no`dan alınıyor, `sira_no` ise paketin `AsamaNo` sırasıydı; ekip eski turları
sona eklediği için kartta ESKİ tur görünüyordu (#617 istinaf 2018/2209, #13247
2021/4915, #2152 Danıştay 15. D.). `hukdok_aktarim.asamalari_yaz` artık paketi
"Güncel?" → karar tarihi → AsamaNo ile sıralıyor ve `sira_no`ları o sıraya çekiyor.

Tüm paketi yeniden koşmak kart alanlarını, tarafları ve avukatları da yeniden yazar
(elle düzeltmeler paket kazanır kuralıyla geri dönerdi). Bu script yalnız aşama
katmanını koşar: ana sayfa yalnız föy→kart haritası ve başvuran taraf/başvuru
tarihi yedeği için OKUNUR, kart alanına yazılmaz. Kapsam dışı föylerin aşama
satırları atlanır (aktarımla aynı kural).

Tek transaction; `--apply` yoksa sonda geri alınır. Kilit uyarısı: aşama yazılan
kartlar koşu boyunca kilitlenir — prod'da mesai (09:00–18:00 TR) DIŞINDA, kuru koşu
prod'da DEĞİL prod dump'ının kopyasında (CLAUDE.md "Prod'da mesai içinde toplu
yazma yok").

    docker compose exec -T backend python scripts/asama_sirasi_duzelt.py --input /tmp/paket.xlsx
    docker compose exec -T backend python scripts/asama_sirasi_duzelt.py --input /tmp/paket.xlsx --apply

İkinci koşu 0: aynı paketle sıra zaten hedeftedir, içerik birebir aynıdır.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers import foy_map
from scripts import hukdok_aktarim as ha

logger = logging.getLogger("AsamaSirasiDuzelt")


def kos(session_factory, *, girdi: Path, apply: bool,
        source: Optional[str] = None) -> ha.AktarimSonucu:
    """Aşama katmanını uygular; `apply=False` ise sonda geri alır."""
    satirlar, _ = ha.xlsx_oku(girdi)
    asama_satirlari = ha.asama_satirlarini_oku(girdi)
    kapsam_disi = set(ha.kapsam_kayitlarini_oku(girdi))
    asama_satirlari = [
        s for s in asama_satirlari
        if (ha._metin(s.degerler.get("sistem_no")) or "") not in kapsam_disi
    ]
    kaynak = (source or f"{ha.AKTARIM_SOURCE_PREFIX}_{girdi.name}")[:100]
    sonuc = ha.AktarimSonucu(okunan=len(asama_satirlari), dry_run=not apply, kaynak_imzasi=kaynak)

    db = session_factory()
    try:
        ha._statement_timeout_yukselt(db, ha.VARSAYILAN_TIMEOUT_MS)
        foy_haritasi = foy_map.map_sistem_no_to_case(
            db, [ha._metin(s.degerler.get("sistem_no")) for s in asama_satirlari]
        )
        ha.asamalari_yaz(
            db, asama_satirlari, foy_haritasi=foy_haritasi,
            foy_satirlari={ha._metin(s.degerler.get("sistem_no")) or "": s for s in satirlar},
            source=kaynak, sonuc=sonuc,
        )
        db.flush()
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return sonuc


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(
        description="Teslim paketinin yalnız aşama katmanını uygular (sıra düzeltmesi dahil)")
    ayristirici.add_argument("--input", required=True, help="teslim paketi (.xlsx)")
    ayristirici.add_argument("--apply", action="store_true", help="yaz (yoksa kuru koşu)")
    ayristirici.add_argument("--source", default=None, help="imza (varsayılan HUKDOK_TESLIM_<dosya>)")
    args = ayristirici.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()
    sonuc = kos(SessionLocal, girdi=Path(args.input), apply=args.apply, source=args.source)
    print(
        f"aşama satırı : {sonuc.okunan} okundu · {sonuc.asama_eklenen} eklendi · "
        f"{sonuc.asama_guncellenen} güncellendi · {sonuc.asama_ikinci_tur} ikinci tur · "
        f"{sonuc.asama_sira_duzeltilen} sıra düzeltildi · {sonuc.asama_belgeli_korunan} belgeli korundu"
    )
    print(f"çelişki      : {len(sonuc.celiskiler)} kart×aşama yazılmadı (kardeş föyler uzlaşmadı)")
    print(f"yazıldı mı   : {'EVET' if args.apply else 'HAYIR (kuru koşu)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
