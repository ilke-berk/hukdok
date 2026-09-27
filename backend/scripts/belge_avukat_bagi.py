#!/usr/bin/env python3
"""Belgelerin avukat bağı: `case_documents.avukat_kodu` → `lawyer_id` doldurma (G226, karar 27.09).

Belge hattı G226'dan beri avukatı `lawyers.id` ile yazar (`document_pipeline.resolve_case_lawyer_id`);
bu betik ESKİ belgeleri bağlar. Yalnız `lawyer_id` BOŞ ve `avukat_kodu` DOLU satırlara bakar:

* kod `lawyers.code`'a birebir (boşluk/büyük-küçük harf farkı yok sayılır) eşlenir;
* listede artık bulunmayan eski kodlar sabit haritayla çevrilir (`ESKI_KOD_HARITASI`, 27.09 ölçümü:
  TUY 5 · BYU 5 · AGH 1 belge — aynı kişilerin eski kısaltmaları);
* eşleşmeyen kod RAPORLANIR, belge bağsız kalır (tahmin yapılmaz);
* `avukat_kodu`'ya DOKUNULMAZ (salt okunur geçiş kolonu; G231 kaldırır);
* idempotent: bağlı belge bir daha ele alınmaz, ikinci koşu 0 satır bağlar;
* silinmiş (soft-delete) belgeler de bağlanır — G231 önkoşulu "`lawyer_id IS NULL AND
  avukat_kodu IS NOT NULL` = 0" onları da sayar.

**Envanter kapısı (G224):** aynı transaction içinde ÖNCE ve SONRA avukat envanteri ölçülür
(`services/avukat_envanteri.olc`); `karsilastir` İHLAL verirse (bir avukatın belge sayısı düştü vb.)
`--apply` bile olsa commit EDİLMEZ, geri alınır ve çıkış kodu 1 döner. Kuru koşu da kapıyı koşar.

    docker compose exec -T backend python scripts/belge_avukat_bagi.py            # kuru koşu (varsayılan)
    docker compose exec -T backend python scripts/belge_avukat_bagi.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any, Dict, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from services import avukat_envanteri as env

#: Listede artık olmayan eski kısaltma → bugünkü `lawyers.code` (27.09 kullanıcı kararı, G226).
ESKI_KOD_HARITASI: Dict[str, str] = {"TUY": "TUGCEUNG", "BYU": "BBA", "AGH": "AYSEGULH"}


def _kod_anahtari(kod: Optional[str]) -> str:
    return (kod or "").strip().upper()


def hedef_kod(kod: Optional[str]) -> str:
    """Belgedeki kodun bağlanacağı `lawyers.code` (eski kısaltma haritadan çevrilir)."""
    anahtar = _kod_anahtari(kod)
    return ESKI_KOD_HARITASI.get(anahtar, anahtar)


def kos(fabrika, *, apply: bool = False) -> Dict[str, Any]:
    """Betiğin gövdesi (testten fabrikayla çağrılır).

    Dönen: ``{durum, baglanan: {(kod, hedef): n}, eslesmeyen: {kod: n}, zaten_bagli, fark, ihlal}``.
    """
    db = fabrika()
    try:
        once = env.olc(db)
        kod_id = {_kod_anahtari(lw.code): lw.id for lw in db.query(models.Lawyer).all() if lw.code}
        zaten_bagli = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.lawyer_id.isnot(None))
            .count()
        )
        adaylar = (
            db.query(models.CaseDocument)
            .filter(
                models.CaseDocument.lawyer_id.is_(None),
                models.CaseDocument.avukat_kodu.isnot(None),
                models.CaseDocument.avukat_kodu != "",
            )
            .order_by(models.CaseDocument.id)
            .all()
        )
        baglanan: Counter = Counter()
        eslesmeyen: Counter = Counter()
        for belge in adaylar:
            hedef = hedef_kod(belge.avukat_kodu)
            lawyer_id = kod_id.get(hedef) if hedef else None
            if lawyer_id is None:
                eslesmeyen[belge.avukat_kodu] += 1
                continue
            belge.lawyer_id = lawyer_id
            baglanan[(belge.avukat_kodu, hedef)] += 1
        db.flush()

        sonra = env.olc(db)
        fark = env.karsilastir(once, sonra)
        ihlal = env.ihlaller(fark)
        if ihlal:
            db.rollback()
            durum = "GERI ALINDI (envanter IHLAL)"
        elif apply:
            db.commit()
            durum = "UYGULANDI"
        else:
            db.rollback()
            durum = "KURU KOSU (yazilmadi)"
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "durum": durum,
        "baglanan": dict(baglanan),
        "eslesmeyen": dict(eslesmeyen),
        "zaten_bagli": zaten_bagli,
        "fark": fark,
        "ihlal": ihlal,
    }


def ozet_metni(sonuc: Dict[str, Any]) -> str:
    satirlar = ["=" * 78, f"Belge avukat bağı (case_documents.lawyer_id) — {sonuc['durum']}", "=" * 78]
    toplam = sum(sonuc["baglanan"].values())
    satirlar.append(f"  zaten bağlı belge (koşu öncesi): {sonuc['zaten_bagli']}")
    satirlar.append(f"  bağlanan belge: {toplam}")
    for (kod, hedef), n in sorted(sonuc["baglanan"].items(), key=lambda kv: (-kv[1], kv[0])):
        cevrim = f" (eski kod → {hedef})" if _kod_anahtari(kod) != hedef else ""
        satirlar.append(f"    {n:6}  {kod}{cevrim}")
    satirlar.append(f"  eşleşmeyen belge: {sum(sonuc['eslesmeyen'].values())}")
    for kod, n in sorted(sonuc["eslesmeyen"].items(), key=lambda kv: (-kv[1], kv[0])):
        satirlar.append(f"    {n:6}  {kod}  (listede karşılığı yok — bağsız kaldı)")
    satirlar.append("  " + "-" * 74)
    satirlar.append("  " + env.fark_metni(sonuc["fark"]).replace("\n", "\n  "))
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Belgelerin avukat bağı: avukat_kodu → lawyer_id")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, apply=args.apply)
    print(ozet_metni(sonuc))
    return 1 if sonuc["ihlal"] else 0


if __name__ == "__main__":
    sys.exit(main())
