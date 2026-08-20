#!/usr/bin/env python3
"""Aynı davayı gösteren kart gruplarını çıkarır — SALT OKUNUR onay listesi.

    docker compose exec -T backend python scripts/mukerrer_kart_raporu.py \\
        --rapor-dizini /tmp/rapor

Hiçbir tabloya yazmaz, hiçbir kartı birleştirmez. Ürünü iki CSV'dir; kararı
insan verir.

Neden birleştirme YOK
---------------------
`tracking_no` müvekkil isim bloğu taşıyan ofis dosya numarasıdır. Tek davada
birden çok müvekkil varsa (tıbbi malpraktiste kural: aynı davada birkaç hekim)
her müvekkilin ayrı ofis dosyası olması DOĞRUDUR — 2026-08-20 ölçümünde aynı-dava
çiftlerinin 149'undan 121'i farklı isim bloğu taşıyor. Bunları birleştirmek ofis
numaralarını yok eder ve `case_documents` bağlarını riske atar.

Geriye asıl şüpheli sınıf kalır: **aynı dava + aynı müvekkil + iki kart**
(ölçümde 28 çift). Bu script onu ayrı bir dosyaya çıkarır.

İki dosya
---------
1. `mukerrer-kart-suphesi_<damga>.csv` — aynı dava, AYNI isim bloğu. Gerçek
   mükerrer kart adayları; belge ve föy sayıları da yazılır ki hangi kartın
   yaşayacağına bakarak karar verilebilsin.
2. `ayni-dava-gruplari_<damga>.csv` — aynı davayı gösteren TÜM kart grupları
   (farklı müvekkilli olanlar dahil), kart başına bir satır. Bu dosya
   birleştirme listesi DEĞİL, envanterdir.

"Aynı dava" tanımı tek yerden gelir: `services.case_relations_auto.siniflandir`
— panelde `AYNI_DAVA` rozetini üreten fonksiyonun aynısı. Aday çiftler ise
panelin tek-kart sorgusu yerine küme temelli iki SQL ile üretilir (14 bin kartta
kart başına sorgu atmamak için); dedektörlerin anlamı aynıdır:

* TKU ortaklığı (`case_foys.tku_no` + legacy `cases.tku_no`)
* Esas + mahkeme + tür ikizliği — TKU'nun kör noktası (199 grubun 24'ünde TKU yok)
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("MukerrerKartRaporu")


def _isim_blogu(tracking_no: str) -> str:
    """Ofis numarasının 10 karakterlik müvekkil bloğu ('D1.B_GURER....0001…')."""
    metin = tracking_no or ""
    return metin[3:13] if len(metin) >= 13 else ""


def _tku_ciftleri(db) -> Dict[Tuple[int, int], Set[str]]:
    """Aynı TKU değerini paylaşan kart çiftleri → {(kucuk_id, buyuk_id): {tku…}}."""
    import models

    kart_tkulari: Dict[int, Set[str]] = defaultdict(set)
    foy_satirlari = (
        db.query(models.CaseFoy.case_id, models.CaseFoy.tku_no)
        .filter(models.CaseFoy.tku_no.isnot(None))
        .distinct()
        .all()
    )
    for case_id, tku in foy_satirlari:
        temiz = (tku or "").strip()
        if temiz:
            kart_tkulari[case_id].add(temiz)

    kart_satirlari = (
        db.query(models.Case.id, models.Case.tku_no)
        .filter(models.Case.tku_no.isnot(None), models.Case.deleted_at.is_(None))
        .all()
    )
    for case_id, tku in kart_satirlari:
        temiz = (tku or "").strip()
        if temiz:
            kart_tkulari[case_id].add(temiz)

    tku_kartlari: Dict[str, Set[int]] = defaultdict(set)
    for case_id, tkular in kart_tkulari.items():
        for tku in tkular:
            tku_kartlari[tku].add(case_id)

    ciftler: Dict[Tuple[int, int], Set[str]] = defaultdict(set)
    for tku, kartlar in tku_kartlari.items():
        if len(kartlar) < 2:
            continue
        sirali = sorted(kartlar)
        for i, sol in enumerate(sirali):
            for sag in sirali[i + 1:]:
                ciftler[(sol, sag)].add(tku)
    return ciftler


def _esas_ciftleri(db, kartlar: Dict[int, object]) -> Set[Tuple[int, int]]:
    """Aynı esas + aynı mahkeme + aynı tür kart çiftleri (TKU'dan bağımsız)."""
    from services.case_relations_auto import _mahkeme_anahtari, esas_anahtari

    kovalar: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    for kart_id, kart in kartlar.items():
        esas = esas_anahtari(getattr(kart, "esas_no", None))
        mahkeme = _mahkeme_anahtari(getattr(kart, "court", None))
        tur = (getattr(kart, "file_type", None) or "").strip()
        if not (esas and mahkeme and tur):
            continue
        kovalar[(esas, mahkeme, tur)].append(kart_id)

    ciftler: Set[Tuple[int, int]] = set()
    for uyeler in kovalar.values():
        if len(uyeler) < 2:
            continue
        sirali = sorted(uyeler)
        for i, sol in enumerate(sirali):
            for sag in sirali[i + 1:]:
                ciftler.add((sol, sag))
    return ciftler


def _sayimlar(db, kart_idler: Iterable[int]) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Kart başına belge ve föy sayısı — hangi kartın yaşayacağına bakarken gerekli."""
    from sqlalchemy import func

    import models

    idler = sorted(set(kart_idler))
    if not idler:
        return {}, {}
    belge = dict(
        db.query(models.CaseDocument.case_id, func.count(models.CaseDocument.id))
        .filter(models.CaseDocument.case_id.in_(idler))
        .group_by(models.CaseDocument.case_id)
        .all()
    )
    foy = dict(
        db.query(models.CaseFoy.case_id, func.count(models.CaseFoy.id))
        .filter(models.CaseFoy.case_id.in_(idler))
        .group_by(models.CaseFoy.case_id)
        .all()
    )
    return belge, foy


def _taraf_adlari(kart, party_type: str) -> List[str]:
    return sorted({
        (p.name or "").strip()
        for p in (getattr(kart, "parties", None) or [])
        if (p.party_type or "") == party_type and (p.name or "").strip()
    })


def _muvekkil(kart) -> str:
    return " / ".join(_taraf_adlari(kart, "CLIENT")[:3])


def _karsi_taraf(kart) -> str:
    return " / ".join(_taraf_adlari(kart, "COUNTER")[:3])


def _karsi_taraf_ortak(sol, sag) -> str:
    """Mükerrer kart mı, yoksa esas numarası yanlış girilmiş İKİ AYRI dava mı?

    Ayırt eden şey karşı taraftır: aynı mahkeme + aynı esas ama karşı taraflar
    bambaşkaysa (canlı örnek: Gaziantep 2. Tüketici 2017/1210 kartlarından biri
    'Çeliksoy', diğeri 'Oğul' davalı) bu bir mükerrer kayıt DEĞİL, bir veri
    hatasıdır. İnsan onayının ilk baktığı kolon budur.
    """
    from party_check import normalize_party_key

    sol_taraf = {normalize_party_key(ad) for ad in _taraf_adlari(sol, "COUNTER")}
    sag_taraf = {normalize_party_key(ad) for ad in _taraf_adlari(sag, "COUNTER")}
    if not sol_taraf or not sag_taraf:
        return "BILINMIYOR"
    return "EVET" if sol_taraf & sag_taraf else "HAYIR"


def gruplari_kur(
    ciftler: Sequence[Tuple[int, int, str]],
) -> Tuple[Dict[int, Set[int]], Dict[int, Set[str]]]:
    """Aynı dava çiftlerini GEÇİŞLİ olarak birleştirir: A-B ve B-C → {A, B, C}.

    Çift listesi yeterli değildir: TKU-1230 üç kart için üç çift üretir ve üçünü
    ayrı ayrı göstermek onay listesini üç kat şişirirdi. Zincir hâlinde gelen
    çiftler (A-B önce, B-C sonra) iki ayrı grubu birleştirir.
    """
    grup_no: Dict[int, int] = {}
    gruplar: Dict[int, Set[int]] = {}
    kanitlar: Dict[int, Set[str]] = defaultdict(set)
    for sol_id, sag_id, kanit in ciftler:
        hedef = grup_no.get(sol_id) or grup_no.get(sag_id) or len(gruplar) + 1
        uyeler = gruplar.setdefault(hedef, set())
        for kid in (sol_id, sag_id):
            eski = grup_no.get(kid)
            if eski and eski != hedef:
                uyeler |= gruplar.pop(eski, set())
                for tasinan in uyeler:
                    grup_no[tasinan] = hedef
                kanitlar[hedef] |= kanitlar.pop(eski, set())
            uyeler.add(kid)
            grup_no[kid] = hedef
        kanitlar[hedef].add(kanit)
    return gruplar, kanitlar


def _csv_yaz(yol: Path, basliklar: Sequence[str], satirlar: Iterable[Sequence[object]]) -> Path:
    """UTF-8 BOM + ';' — Türkçe Excel dosyayı çift tıklamayla doğru açar
    (hukdok_aktarim.py rapor yazımıyla aynı sözleşme)."""
    with open(yol, "w", newline="", encoding="utf-8-sig") as dosya:
        yazici = csv.writer(dosya, delimiter=";")
        yazici.writerow(basliklar)
        yazici.writerows(satirlar)
    return yol


def raporu_uret(SessionFactory, rapor_dizini: Path) -> Dict[str, object]:
    """İki CSV'yi üretir ve özet sözlüğü döndürür. Hiçbir tabloya yazmaz."""
    from sqlalchemy.orm import selectinload

    import models
    from services.case_relations_auto import AYNI_DAVA, kart_ozeti, siniflandir

    db = SessionFactory()
    try:
        kart_listesi = (
            db.query(models.Case)
            .options(selectinload(models.Case.parties))
            .filter(models.Case.deleted_at.is_(None))
            .all()
        )
        kartlar = {kart.id: kart for kart in kart_listesi}
        logger.info(f"{len(kartlar)} aktif kart okundu")

        tku_ciftleri = {
            cift: tkular for cift, tkular in _tku_ciftleri(db).items()
            if cift[0] in kartlar and cift[1] in kartlar
        }
        esas_ciftleri = _esas_ciftleri(db, kartlar)
        logger.info(f"aday çift: TKU {len(tku_ciftleri)} · esas ikizi {len(esas_ciftleri)}")

        # "Aynı dava" hükmünü panelle AYNI fonksiyon verir.
        ayni_dava_ciftleri: List[Tuple[int, int, str]] = []
        for cift in sorted(set(tku_ciftleri) | esas_ciftleri):
            sol, sag = kartlar[cift[0]], kartlar[cift[1]]
            if siniflandir(kart_ozeti(sol), kart_ozeti(sag)) != AYNI_DAVA:
                continue
            tkular = tku_ciftleri.get(cift, set())
            kanit = ", ".join(sorted(tkular)) if tkular else "esas+mahkeme"
            ayni_dava_ciftleri.append((cift[0], cift[1], kanit))

        ilgili_idler = {kid for sol, sag, _ in ayni_dava_ciftleri for kid in (sol, sag)}
        belge_sayisi, foy_sayisi = _sayimlar(db, ilgili_idler)

        rapor_dizini.mkdir(parents=True, exist_ok=True)
        damga = datetime.now().strftime("%Y%m%d-%H%M%S")

        # ── 1. Mükerrer kart şüphesi: aynı dava + AYNI müvekkil isim bloğu ──
        supheli: List[Sequence[object]] = []
        for sol_id, sag_id, kanit in ayni_dava_ciftleri:
            sol, sag = kartlar[sol_id], kartlar[sag_id]
            blok_sol, blok_sag = _isim_blogu(sol.tracking_no), _isim_blogu(sag.tracking_no)
            if not blok_sol or blok_sol != blok_sag:
                continue
            supheli.append((
                _karsi_taraf_ortak(sol, sag),
                kanit, sol.file_type, sol.court, sol.esas_no, blok_sol,
                sol_id, sol.tracking_no, _muvekkil(sol), _karsi_taraf(sol),
                belge_sayisi.get(sol_id, 0), foy_sayisi.get(sol_id, 0),
                sag_id, sag.tracking_no, _muvekkil(sag), _karsi_taraf(sag),
                belge_sayisi.get(sag_id, 0), foy_sayisi.get(sag_id, 0),
            ))
        # Karşı tarafı ortak olanlar başa: gerçek mükerrer adayları listenin
        # tepesinde dursun, esas numarası yanlış girilmiş çiftler aşağıda.
        supheli.sort(key=lambda satir: {"EVET": 0, "BILINMIYOR": 1}.get(str(satir[0]), 2))
        supheli_yol = _csv_yaz(
            rapor_dizini / f"mukerrer-kart-suphesi_{damga}.csv",
            ("karsi_taraf_ortak", "kanit", "tur", "mahkeme", "esas_no", "isim_blogu",
             "kart_a", "ofis_no_a", "muvekkil_a", "karsi_taraf_a", "belge_a", "foy_a",
             "kart_b", "ofis_no_b", "muvekkil_b", "karsi_taraf_b", "belge_b", "foy_b"),
            supheli,
        )

        # ── 2. Aynı dava grupları envanteri (kart başına bir satır) ──
        gruplar, kanitlar = gruplari_kur(ayni_dava_ciftleri)

        envanter: List[Sequence[object]] = []
        for grup_id, uyeler in sorted(gruplar.items()):
            bloklar = {_isim_blogu(kartlar[kid].tracking_no) for kid in uyeler}
            tek_muvekkil = "EVET" if len(bloklar) == 1 else "HAYIR"
            kanit = ", ".join(sorted(kanitlar[grup_id]))
            for kid in sorted(uyeler):
                kart = kartlar[kid]
                envanter.append((
                    grup_id, kanit, len(uyeler), tek_muvekkil,
                    kid, kart.tracking_no, _isim_blogu(kart.tracking_no),
                    kart.file_type, kart.court, kart.esas_no,
                    _muvekkil(kart), _karsi_taraf(kart),
                    belge_sayisi.get(kid, 0), foy_sayisi.get(kid, 0),
                ))
        envanter_yol = _csv_yaz(
            rapor_dizini / f"ayni-dava-gruplari_{damga}.csv",
            ("grup", "kanit", "grup_kart_sayisi", "tek_muvekkil",
             "kart_id", "ofis_no", "isim_blogu", "tur", "mahkeme", "esas_no",
             "muvekkil", "karsi_taraf", "belge_sayisi", "foy_sayisi"),
            envanter,
        )

        return {
            "kart": len(kartlar),
            "tku_cifti": len(tku_ciftleri),
            "esas_cifti": len(esas_ciftleri),
            "ayni_dava_cifti": len(ayni_dava_ciftleri),
            "mukerrer_suphesi": len(supheli),
            "karsi_taraf_ortak": sum(1 for satir in supheli if satir[0] == "EVET"),
            "grup": len(gruplar),
            "grup_karti": len(ilgili_idler),
            "raporlar": [supheli_yol, envanter_yol],
        }
    finally:
        db.close()


def ozet_metni(ozet: Dict[str, object]) -> str:
    satirlar = [
        "=" * 78,
        "Aynı dava / mükerrer kart raporu (SALT OKUNUR)",
        "=" * 78,
        f"  taranan kart      : {ozet['kart']}",
        f"  aday çift         : TKU {ozet['tku_cifti']} · esas ikizi {ozet['esas_cifti']}",
        f"  aynı dava çifti   : {ozet['ayni_dava_cifti']}",
        f"  aynı dava grubu   : {ozet['grup']} ({ozet['grup_karti']} kart)",
        f"  mükerrer şüphesi  : {ozet['mukerrer_suphesi']} çift (aynı dava + AYNI müvekkil)",
        f"    karşı taraf ortak: {ozet['karsi_taraf_ortak']} (gerçek mükerrer adayı; "
        "kalanında esas no yanlış girilmiş olabilir)",
    ]
    for yol in ozet["raporlar"]:  # type: ignore[union-attr]
        satirlar.append(f"  rapor             : {yol}")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aynı davayı gösteren kart gruplarını CSV'ye çıkarır (yazmaz)",
    )
    parser.add_argument("--rapor-dizini", default="aktarim-raporlari",
                        help="CSV'lerin yazılacağı dizin")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from logging_setup import configure_logging

    configure_logging()

    import database

    ozet = raporu_uret(database.SessionLocal, Path(args.rapor_dizini))
    print(ozet_metni(ozet))
    return 0


if __name__ == "__main__":
    sys.exit(main())
