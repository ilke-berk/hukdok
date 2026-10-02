#!/usr/bin/env python3
"""Hizmet kayıtlarını (`case_hizmetleri`) föylerden GERİYE DÖNÜK doldurur (G249).

Kullanıcı kararı 01.10.2026 (G248): hizmet türü kartın değil KART × MÜVEKKİL
çiftinin özelliğidir. Aktarım G249'dan beri her föy için bir föy kaynaklı hizmet
satırı yazar; bu script BUGÜNE DEK aktarılmış föylerin satırlarını bir kerede
açar — paket beklemeden. Yazıcı aktarımla AYNIDIR
(`managers/case_hizmetleri.foydan_yaz`, upsert anahtarı `foy_id`): sonraki
aktarım koşusu aynı satırları `DEGISMEDI` bulur.

Föy başına kural (`foydan_yaz` sözleşmesi):
* kapsamda + müvekkil tarafına bağlı + hizmeti `service_types` listesinde →
  satır yazılır (ilk yazım tarihçesizdir — kaynak föyün kendisi),
* kapsam dışı (`kapsam_durumu` dolu), müvekkil bağı yok, bağlı taraf müvekkil
  değil, hizmeti boş ya da listede yok → satır YAZILMAZ, föy sebebiyle raporlanır.
Kart özeti (`cases.hizmet_turu`) satır yazılan kartta satırlardan yeniden kurulur
(DISTINCT, Türkçe alfabetik, " ; "): kardeş föyleri farklı hizmet taşıyan kartta
tek değer yerine birleşim görünür. Satır almayan karta DOKUNULMAZ.

Varsayılan KURU KOŞUdur (yazar, sonda geri alır); `--apply` TEK transaction'da
yazar. İkinci koşu 0 değişiklik (idempotent). Beklenmeyen DB hatasında koşu
tamamen geri alınır ve çıkış kodu 1'dir.

**Toplu işlem prensibi (CLAUDE.md, 02.10 kararı):** script dokunduğu kartları
koşu boyunca kilitler — KURU KOŞU DAHİL. Prod'da kuru koşu YOK (prod dump'ının
kopyasında koşulur); `--apply` prod'da mesai dışında ve yedekten SONRA.

    docker compose exec -T backend python scripts/hizmet_kayitlari_doldur.py            # kuru koşu
    docker compose exec -T backend python scripts/hizmet_kayitlari_doldur.py --ayrinti  # atlanan föyleri tek tek
    docker compose exec -T backend python scripts/hizmet_kayitlari_doldur.py --apply    # yazar (insan adımı)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_hizmetleri

logger = logging.getLogger("HizmetKayitlariDoldur")
#: Föyün kendi teslim imzası yoksa (elle açılmış föy) satırın `source`u.
DEGISTIREN = "hizmet_kayitlari_doldur"
_PARCA = 500
#: Özet çıktısında sebep başına listelenen föy sayısı (`--ayrinti` hepsini basar).
_ORNEK_SINIRI = 20

SEBEP_ACIKLAMALARI: Dict[str, str] = {
    case_hizmetleri.SEBEP_KAPSAM_DISI: "kapsam dışı föy",
    case_hizmetleri.SEBEP_TARAF_YOK: "müvekkil bağı yok",
    case_hizmetleri.SEBEP_MUVEKKIL_DEGIL: "bağlı taraf müvekkil değil",
    case_hizmetleri.SEBEP_HIZMET_BOS: "hizmet türü boş",
    case_hizmetleri.SEBEP_LISTEDE_YOK: "hizmet türü listede yok",
}


@dataclass
class DoldurmaSonucu:
    apply: bool = False
    yazildi: bool = False
    foy_toplam: int = 0
    eklenen: int = 0
    guncellenen: int = 0
    silinen: int = 0
    degismeyen: int = 0
    #: {sebep: [(SistemNo, kart id, föydeki hizmet değeri)]} — satır yazılmayan föyler
    atlananlar: Dict[str, List[Tuple[str, int, Optional[str]]]] = field(default_factory=dict)
    #: {hizmet adı: yazılan satır sayısı} — bu koşuda eklenen satırların dağılımı
    dagilim: Dict[str, int] = field(default_factory=dict)
    satir_alan_kart: int = 0           # bu koşuda satırı eklenen/değişen/silinen kart
    ozeti_degisen_kart: int = 0        # `cases.hizmet_turu` özeti değişen kart
    hatalar: List[Tuple[str, str]] = field(default_factory=list)   # (SistemNo, hata)

    @property
    def atlanan(self) -> int:
        return sum(len(v) for v in self.atlananlar.values())

    @property
    def degisiklik(self) -> int:
        """Bu koşunun yazdığı satır değişikliği (ikinci koşuda 0)."""
        return self.eklenen + self.guncellenen + self.silinen

    @property
    def cikis_kodu(self) -> int:
        return 1 if self.hatalar else 0


def _kart_ozetleri(db, case_idleri: List[int]) -> Dict[int, Optional[str]]:
    ozetler: Dict[int, Optional[str]] = {}
    for i in range(0, len(case_idleri), _PARCA):
        for cid, ozet in (
            db.query(models.Case.id, models.Case.hizmet_turu)
            .filter(models.Case.id.in_(case_idleri[i:i + _PARCA]))
        ):
            ozetler[cid] = ozet
    return ozetler


def doldur(session_factory, *, apply: bool = False) -> DoldurmaSonucu:
    """Bütün föyleri dolaşır, hizmet satırlarını `foydan_yaz` ile yazar.

    TEK transaction: `apply` değilse (ya da hata varsa) tamamen geri alınır.
    Föy başına SAVEPOINT — beklenmeyen DB hatası hangi föyde çıktığıyla
    raporlanır, sonra koşu geri alınır (yarım doldurma bırakılmaz).
    """
    sonuc = DoldurmaSonucu(apply=apply)
    db = session_factory()
    try:
        foy_idleri = [fid for (fid,) in db.query(models.CaseFoy.id).order_by(models.CaseFoy.id)]
        sonuc.foy_toplam = len(foy_idleri)
        # Özeti değişebilecek kartlar: föyü olanlar + bugün hizmet satırı taşıyanlar
        # (föyü başka karta gitmiş satırın eski kartı da buradadır).
        kart_idleri = sorted(
            {cid for (cid,) in db.query(models.CaseFoy.case_id).distinct()}
            | {cid for (cid,) in db.query(models.CaseHizmeti.case_id).distinct()}
        )
        ozet_once = _kart_ozetleri(db, kart_idleri)
        dokunulan: set = set()

        for i in range(0, len(foy_idleri), _PARCA):
            parca = foy_idleri[i:i + _PARCA]
            foyler = (
                db.query(models.CaseFoy)
                .filter(models.CaseFoy.id.in_(parca))
                .order_by(models.CaseFoy.id)
                .all()
            )
            onceki_kart = {
                foy_id: case_id for foy_id, case_id in
                db.query(models.CaseHizmeti.foy_id, models.CaseHizmeti.case_id)
                .filter(models.CaseHizmeti.foy_id.in_(parca))
            }
            for foy in foyler:
                foy_id, sistem_no, case_id = foy.id, foy.sistem_no, foy.case_id
                hizmet = foy.hizmet_turu
                try:
                    with db.begin_nested():
                        yazim = case_hizmetleri.foydan_yaz(db, foy, source=foy.source or DEGISTIREN)
                except SQLAlchemyError as exc:
                    db.expire_all()
                    sonuc.hatalar.append((sistem_no, f"{type(exc).__name__}: {exc}"))
                    logger.warning(f"Föy {sistem_no} hizmet satırı yazılamadı: {exc}")
                    continue
                if yazim.durum == case_hizmetleri.FOY_EKLENDI:
                    sonuc.eklenen += 1
                    ad = yazim.satir.hizmet_turu
                    sonuc.dagilim[ad] = sonuc.dagilim.get(ad, 0) + 1
                    dokunulan.add(case_id)
                elif yazim.durum == case_hizmetleri.FOY_GUNCELLENDI:
                    sonuc.guncellenen += 1
                    dokunulan.update({case_id, onceki_kart.get(foy_id, case_id)})
                elif yazim.durum == case_hizmetleri.FOY_SILINDI:
                    sonuc.silinen += 1
                    dokunulan.add(onceki_kart.get(foy_id, case_id))
                elif yazim.durum == case_hizmetleri.FOY_DEGISMEDI:
                    sonuc.degismeyen += 1
                if yazim.sebep:
                    sonuc.atlananlar.setdefault(yazim.sebep, []).append((sistem_no, case_id, hizmet))

        db.flush()
        sonuc.satir_alan_kart = len(dokunulan)
        ozet_sonra = _kart_ozetleri(db, kart_idleri)
        sonuc.ozeti_degisen_kart = sum(
            1 for cid, ozet in ozet_sonra.items() if ozet_once.get(cid) != ozet
        )

        if sonuc.hatalar:
            # Yarım doldurma bırakılmaz; nihai başarısızlık TEK ERROR (log sözleşmesi).
            logger.error(
                f"Hizmet kaydı doldurma GERİ ALINDI: {len(sonuc.hatalar)} föyde DB hatası"
            )
            db.rollback()
        elif apply:
            db.commit()
            sonuc.yazildi = True
        else:
            db.rollback()
    finally:
        db.close()
    return sonuc


def ozet_metni(sonuc: DoldurmaSonucu, *, ayrinti: bool = False) -> str:
    """Koşunun tek ekranlık özeti (stdout)."""
    if sonuc.hatalar:
        mod = "GERİ ALINDI (DB hatası)"
    elif sonuc.yazildi:
        mod = "YAZILDI"
    else:
        mod = "KURU KOŞU (geri alındı)"
    fiil = "yazıldı" if sonuc.yazildi else "yazılacak"
    satirlar = [
        "=" * 78,
        f"Hizmet kayıtları geriye dönük doldurma — {mod}",
        "=" * 78,
        f"  föy (toplam)        : {sonuc.foy_toplam}",
        f"  {fiil + ' satır':<20}: {sonuc.eklenen}",
        f"  güncellenen satır   : {sonuc.guncellenen}",
        f"  silinen satır       : {sonuc.silinen}",
        f"  değişmeyen satır    : {sonuc.degismeyen}",
        f"  atlanan föy         : {sonuc.atlanan}",
    ]
    for sebep, foyler in sorted(sonuc.atlananlar.items()):
        satirlar.append(f"    {SEBEP_ACIKLAMALARI.get(sebep, sebep):<26}: {len(foyler)}")
        gosterilen = foyler if ayrinti else foyler[:_ORNEK_SINIRI]
        for sistem_no, case_id, hizmet in gosterilen:
            satirlar.append(f"      {sistem_no} (kart {case_id}) hizmet={hizmet!r}")
        if len(foyler) > len(gosterilen):
            satirlar.append(f"      … {len(foyler) - len(gosterilen)} föy daha (--ayrinti)")
    satirlar.append(f"  satırı değişen kart : {sonuc.satir_alan_kart}")
    satirlar.append(f"  özeti değişen kart  : {sonuc.ozeti_degisen_kart}")
    if sonuc.dagilim:
        satirlar.append(f"  hizmet dağılımı ({fiil} satır):")
        for ad, sayi in sorted(sonuc.dagilim.items(), key=lambda kv: (-kv[1], kv[0])):
            satirlar.append(f"    {sayi:>6}  {ad}")
    for sistem_no, hata in sonuc.hatalar:
        satirlar.append(f"  HATA {sistem_no}: {hata}")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hizmet kayıtlarını (case_hizmetleri) föylerden geriye dönük doldurur (G249)",
    )
    parser.add_argument("--apply", action="store_true",
                        help="yaz (varsayılan kuru koşu; prod'da mesai dışı + yedekten sonra)")
    parser.add_argument("--ayrinti", action="store_true",
                        help="atlanan föylerin tamamını listele (varsayılan: sebep başına ilk "
                             f"{_ORNEK_SINIRI})")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Loglama TEK noktadan yapılandırılır (Faz 2-B bekçisi: dağınık basicConfig yasak).
    from logging_setup import configure_logging

    configure_logging()

    import database

    sonuc = doldur(database.SessionLocal, apply=args.apply)
    print(ozet_metni(sonuc, ayrinti=args.ayrinti))
    return sonuc.cikis_kodu


if __name__ == "__main__":
    sys.exit(main())
