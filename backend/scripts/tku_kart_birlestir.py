#!/usr/bin/env python3
"""TKU kart birleştirmesi — aynı davanın müvekkil başına açılmış kartlarını tek karta toplar.

Kullanıcı kararı (11.09.2026): veri ekibinin defterinde her müvekkil ayrı föydür
ve aynı davanın föyleri aynı TKU'yu paylaşır (TKU-1014: Axa föyü + Dr. Şimşek
föyü, Tarsus 3. AHM 2014/394). Eski aktarım bu föyleri AYRI kartlara açmıştı.
Hedef yapı sistemde zaten var (903 kart: bir kart, altında birden çok föy,
üstünde birden çok müvekkil — örn. #89); bu script dağınık kalan grupları o
şekle getirir. Föyler DEĞİŞMEZ; kartlar birleşir.

Kapsam kuralı — TKU tek başına yetmez: ekip TKU'yu farklı davaları
ilişkilendirmek için de kullanıyor (480 grup farklı mahkeme/esas —
`services/case_relations_auto.py` bunları bağ olarak gösterir, birleştirilmez).
Grup = aynı TKU + aynı esas numarası + birden çok canlı kart; mahkeme anahtarı
(`_baslik_anahtari`) ve dosya türü farklıysa o kart REDDEDİLİR (rapora düşer).

Taşıma yolu `scripts/mukerrer_kart_birlestir.birlestir` (G127) ile AYNIDIR —
belge koruma şartı, taraf tekilleştirme, aşama/esas tarihçesi, soft delete —
yalnız "müvekkil kümeleri aynı olmalı" koşulu `muvekkil_ayrimi=True` ile
gevşer ve taşınan föy sönen kartın ofis numarasını `onceki_tracking_no`da
taşır (arama bulur, avukatın bildiği numara kaybolmaz).

Kalan kart: en çok belgesi olan; eşitlikte en çok föyü olan; eşitlikte en eski
(küçük id). Bir kart birden çok grupta geçerse (birden çok TKU'lu kart) ilk
birleştirme sonraki gruplarda kalan karta yeniden eşlenir; grup tek karta
inerse atlanır.

    docker compose exec -T backend python scripts/tku_kart_birlestir.py            # kuru koşu
    docker compose exec -T backend python scripts/tku_kart_birlestir.py --rapor /tmp/tku.csv
    docker compose exec -T backend python scripts/tku_kart_birlestir.py --tku TKU-1014 --apply --kim ilke
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from extractors.court_extractor import _config_listeleri
from scripts import mukerrer_kart_birlestir as mb
from scripts.hukdok_aktarim import _baslik_anahtari
from services.case_relations_auto import esas_anahtari
from services.court_name import GUVEN_YOK, parse_court_name
from services.judicial_unit import normalize_court

logger = logging.getLogger("TkuKartBirlestir")
DEGISTIREN = "tku_kart_birlestir"
TARIHCE_ALANI = "tku_birlestirme"
SEBEP_ETIKETI = "TKU kart birleştirmesi"


@dataclass
class Grup:
    tku_no: str
    esas_no: str
    kart_idler: List[int]
    kalan_id: Optional[int] = None
    sonuclar: List[mb.BirlestirmeSonucu] = field(default_factory=list)
    atlandi: Optional[str] = None            # grup düzeyi: önceki birleştirme tek karta indirdi
    sonen_muvekkiller: Dict[int, str] = field(default_factory=dict)


def gruplari_bul(db, *, tku: Optional[Sequence[str]] = None) -> List[Grup]:
    """Aynı TKU + aynı esas numaralı föyleri birden çok CANLI kartta olan gruplar.

    Esas anahtarı `services.case_relations_auto.esas_anahtari`: boşluk/harf
    farkı yutulur ("2020 / 1777" = "2020/1777"), yer tutucu ('2021/', '2014/???')
    ve boş esas KİMLİK SAYILMAZ — o kartlar gruba girmez (aynı TKU'daki tüm
    '2021/' kartlarını aynı dava ilan etmek felaket olurdu; lokalde 208 kart
    '2014/???'). Bu kartlar ekibe soruya gider, rapora değil.
    """
    q = (db.query(models.CaseFoy.tku_no, models.Case.esas_no, models.Case.id)
         .join(models.Case, models.Case.id == models.CaseFoy.case_id)
         .filter(models.Case.deleted_at.is_(None),
                 models.CaseFoy.tku_no.isnot(None), models.CaseFoy.tku_no != "")
         .distinct())
    if tku:
        q = q.filter(models.CaseFoy.tku_no.in_(list(tku)))
    kume: Dict[Tuple[str, str], Set[int]] = {}
    for tku_no, esas, cid in q:
        anahtar = esas_anahtari(esas)
        if not anahtar:
            continue
        kume.setdefault((tku_no.strip(), anahtar), set()).add(cid)
    return [Grup(t, e, sorted(ids)) for (t, e), ids in sorted(kume.items()) if len(ids) > 1]


def mahkeme_uyumu(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """İki mahkeme adı aynı mahkeme mi? Uyumluysa None, değilse RET sebebi.

    Sıra: (1) biri boşsa uyumlu (eski aktarım mahkemesiz kart açmış olabilir);
    (2) düz normalize eşitse uyumlu; (3) yapısal kimlik (G067
    `court_name.parse_court_name`): yer + kanonik tür + daire aynı olmalı, sıra
    numarası aynı ya da bir tarafta YOK ("Şanlıurfa İdare Mahkemesi" =
    "Şanlıurfa 1. İdare Mahkemesi"; tek mahkemeli yerde "1." yazılmaz). Bu
    yol "Mahkemesi/Mahkemeleri", "(tüketici Mahkemesi sıfatıyla)" eki, büyük/
    küçük harf ve aksan farkını yutar; "Ankara 5." ≠ "Ankara 15." ve
    "Antalya 1." ≠ "Antalya 2." farklı kalır. Kimliği çıkmayan ad (güven YOK)
    eşleşme ÜRETMEZ — şüphe sessizlik lehine (esas_anahtari ile aynı ilke).
    """
    a_m, b_m = (a or "").strip(), (b or "").strip()
    if not a_m or not b_m:
        return None
    if normalize_court(a_m) == normalize_court(b_m):
        return None
    yerler, turler = _config_listeleri()
    ka = parse_court_name(a_m, yerler=yerler, turler=turler)
    kb = parse_court_name(b_m, yerler=yerler, turler=turler)
    if ka is None or kb is None or ka.guven == GUVEN_YOK or kb.guven == GUVEN_YOK:
        return f"mahkeme farklı ({a_m!r} ≠ {b_m!r}; yapısal kimlik çıkarılamadı)"
    if (ka.yer or "") != (kb.yer or "") or (ka.tur_kanonik or "") != (kb.tur_kanonik or ""):
        return f"mahkeme farklı ({a_m!r} ≠ {b_m!r})"
    if (ka.daire_no, ka.daire_adi) != (kb.daire_no, kb.daire_adi):
        return f"mahkeme farklı ({a_m!r} ≠ {b_m!r}; daire)"
    if ka.sira is not None and kb.sira is not None and ka.sira != kb.sira:
        return f"mahkeme farklı ({a_m!r} ≠ {b_m!r}; sıra {ka.sira} ≠ {kb.sira})"
    return None


def kalan_sec(db, kartlar: Sequence[models.Case]) -> models.Case:
    """En çok belge → en çok föy → en eski kart."""
    def anahtar(c: models.Case):
        belge = db.query(func.count(models.CaseDocument.id)).filter(models.CaseDocument.case_id == c.id).scalar()
        foy = db.query(func.count(models.CaseFoy.id)).filter(models.CaseFoy.case_id == c.id).scalar()
        return (-int(belge or 0), -int(foy or 0), c.id)
    return min(kartlar, key=anahtar)


def _tur_anahtari(deger: Optional[str]) -> str:
    return _baslik_anahtari(deger)


def _muvekkiller(c: models.Case) -> str:
    return "; ".join(p.name for p in c.parties if p.party_type == "CLIENT")


def gruplari_birlestir(session_factory, *, apply: bool = False, kim: str = DEGISTIREN,
                       tku: Optional[Sequence[str]] = None, limit: Optional[int] = None) -> List[Grup]:
    """Grupları bulur ve birleştirir; `apply=False` her şeyi geri alır (rapor yine üretilir)."""
    db = session_factory()
    try:
        gruplar = gruplari_bul(db, tku=tku)
        if limit:
            gruplar = gruplar[:limit]
        yeniden_esle: Dict[int, int] = {}          # sönen id → kalan id (zincir)
        for g in gruplar:
            idler: List[int] = []
            for cid in g.kart_idler:
                while cid in yeniden_esle:
                    cid = yeniden_esle[cid]
                if cid not in idler:
                    idler.append(cid)
            if len(idler) < 2:
                g.atlandi = "önceki grupta birleşti (tek kart kaldı)"
                continue
            kartlar = [db.get(models.Case, i) for i in idler]
            kalan = kalan_sec(db, kartlar)
            g.kalan_id = kalan.id
            for k in kartlar:
                if k.id == kalan.id:
                    continue
                g.sonen_muvekkiller[k.id] = _muvekkiller(k)
                ret = None
                if _tur_anahtari(k.file_type) != _tur_anahtari(kalan.file_type):
                    ret = f"dosya türü farklı ({kalan.file_type!r} ≠ {k.file_type!r})"
                else:
                    ret = mahkeme_uyumu(kalan.court, k.court)
                if ret:
                    g.sonuclar.append(mb.BirlestirmeSonucu(
                        kalan.id, k.id, ret=ret,
                        kalan_tracking_no=kalan.tracking_no, mukerrer_tracking_no=k.tracking_no))
                    continue
                with db.begin_nested():
                    sonuc = mb.birlestir(db, kalan, k, kim=kim, muvekkil_ayrimi=True, mahkeme_kontrolu=False,
                                         tarihce_alani=TARIHCE_ALANI, sebep_etiketi=SEBEP_ETIKETI)
                g.sonuclar.append(sonuc)
                if not sonuc.ret:
                    yeniden_esle[k.id] = kalan.id
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return gruplar


def rapor_yaz(gruplar: Sequence[Grup], yol: str, *, apply: bool) -> None:
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["tku_no", "esas_no", "kalan_id", "kalan_ofis_no", "sonen_id", "sonen_ofis_no",
                    "sonen_muvekkiller", "durum", "detay"])
        for g in gruplar:
            if g.atlandi:
                w.writerow([g.tku_no, g.esas_no, "", "", "", "", "", "ATLANDI", g.atlandi])
                continue
            for s in g.sonuclar:
                if s.ret:
                    w.writerow([g.tku_no, g.esas_no, s.kalan_id, s.kalan_tracking_no, s.mukerrer_id,
                                s.mukerrer_tracking_no, g.sonen_muvekkiller.get(s.mukerrer_id, ""), "RET", s.ret])
                else:
                    tasinan = ", ".join(f"{k} {v}" for k, v in sorted(s.tasinan.items()))
                    w.writerow([g.tku_no, g.esas_no, s.kalan_id, s.kalan_tracking_no, s.mukerrer_id,
                                s.mukerrer_tracking_no, g.sonen_muvekkiller.get(s.mukerrer_id, ""),
                                "BİRLEŞTİ" if apply else "PLAN", tasinan])


def ozet_metni(gruplar: Sequence[Grup], *, apply: bool) -> str:
    grup = sum(1 for g in gruplar if not g.atlandi)
    atlanan = sum(1 for g in gruplar if g.atlandi)
    sonuclar = [s for g in gruplar for s in g.sonuclar]
    ok = [s for s in sonuclar if not s.ret]
    ret = [s for s in sonuclar if s.ret]
    sebepler: Dict[str, int] = {}
    for s in ret:
        anahtar = s.ret.split("(")[0].strip()
        sebepler[anahtar] = sebepler.get(anahtar, 0) + 1
    foy = sum(s.tasinan.get("foy", 0) for s in ok)
    belge = sum(s.tasinan.get("belge", 0) for s in ok)
    taraf = sum(s.tasinan.get("taraf_tasinan", 0) for s in ok)
    satirlar = [
        "=" * 70,
        f"TKU kart birleştirmesi — {'YAZILDI' if apply else 'KURU KOŞU (geri alındı)'}",
        "=" * 70,
        f"  grup (TKU+esas)     : {grup} (atlanan {atlanan})",
        f"  sönen kart          : {len(ok)} {'birleşti' if apply else 'birleşecek'}",
        f"  taşınan föy         : {foy}",
        f"  taşınan belge       : {belge}",
        f"  taşınan taraf       : {taraf} (müvekkil + kalanda olmayan karşı taraf)",
        f"  reddedilen kart     : {len(ret)}",
    ]
    for sebep, n in sorted(sebepler.items(), key=lambda x: -x[1]):
        satirlar.append(f"      {sebep}: {n}")
    satirlar.append("=" * 70)
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TKU kart birleştirmesi (aynı dava, müvekkil başına kart)")
    parser.add_argument("--apply", action="store_true", help="yaz (varsayılan kuru koşu)")
    parser.add_argument("--kim", default=DEGISTIREN, help="deleted_by / tarihçe imzası")
    parser.add_argument("--tku", action="append", default=None, help="yalnız bu TKU (tekrarlanabilir)")
    parser.add_argument("--limit", type=int, default=None, help="ilk N grup")
    parser.add_argument("--rapor", default=None, help="plan/sonuç CSV yolu")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from logging_setup import configure_logging

    configure_logging()
    import database

    gruplar = gruplari_birlestir(database.SessionLocal, apply=args.apply, kim=args.kim,
                                 tku=args.tku, limit=args.limit)
    if args.rapor:
        rapor_yaz(gruplar, args.rapor, apply=args.apply)
    print(ozet_metni(gruplar, apply=args.apply))
    if args.rapor:
        print(f"  rapor: {args.rapor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
