#!/usr/bin/env python3
"""Dava tarihçesi (`case_history`) tek seferlik temizliği — aktarım gürültüsünü siler.

Kullanıcı kararı (11.09.2026): kart geçmişi paneli aktarım paketlerinin ve
yazım birliği turunun her hücre yazımını ayrı satır olarak gösteriyordu (lokalde
140.153 satır, kart başına ~10). Bu bir olay günlüğü değil, dolgu izi. Temizlik
yalnız GERÇEK olayları bırakır; kalan her satırın bir okuyucusu vardır.

KALAN satırlar (silinmez):
* Kullanıcı imzalı satır: `source` NULL ya da otomatik imza taşımayan
  (`intake-enrich:`, elle panel) — kesim-sonrası status koruması bunları okur
  (`scripts/hukdok_aktarim.kesim_sonrasi_kullanici_kaydi`).
* Mahkeme / esas / status gerçekten değiştiyse: eski değer dolu VE normalize
  anahtarı yeni değerden farklı (`_anahtar`). Yalnız biçim farkı (büyük/küçük
  harf, aksan, noktalama, boşluk) ya da boş → dolu ilk dolum SİLİNİR — güncel
  değer zaten güncel biçimdedir.
* Föy bağlama satırı `case_foys.sistem_no` (föy başına bir): hem "bu föy pakete
  bağlandı" olayıdır hem de AKTARIM provenance imzasıdır —
  `case_manager._is_aktarim_kaydi` / `required_fields.aktarim_kaydi_sql` kartın
  aktarımdan geldiğini bu imzadan okur, eksik-alan kovası (`AKTARIM`/`MANUAL`)
  buna bağlıdır. Silinirse 6.466 kart kova değiştirir.
* Birleştirme satırları (`mukerrer_birlestirme`, `tku_birlestirme`): soft-delete
  edilen kartın izi, geri alma haritası.

SİLİNEN satırlar: yukarıdakiler dışında kalan `HUKDOK_TESLIM*` ve `yazim_birligi`
imzalı her satır (avukat/taraf ekleme, alan dolumu, föy-müvekkil bağı, biçim
düzeltmesi). Silmeden önce silinecek satırlar CSV'ye dökülür (geri alma yedeği).

    docker compose exec -T backend python scripts/tarihce_temizligi.py                 # kuru koşu
    docker compose exec -T backend python scripts/tarihce_temizligi.py --apply --yedek /tmp/silinen.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from sqlalchemy import or_

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from required_fields import AKTARIM_SOURCE_PREFIX
from scripts.tku_kart_birlestir import mahkeme_uyumu
from services.case_relations_auto import esas_anahtari

YAZIM_BIRLIGI = "yazim_birligi"
KORUNAN_ALANLAR = ("court", "esas_no", "status")
FOY_BAGLAMA_ALANI = "case_foys.sistem_no"
BIRLESTIRME_ALANLARI = ("mukerrer_birlestirme", "tku_birlestirme")
_TR = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iIgGuUsSoOcC")


def _anahtar(deger: Optional[str]) -> str:
    """Biçim farkını yutan karşılaştırma anahtarı: TR sadeleştirme + NFD aksan
    atma + büyük harf + yalnız harf/rakam//. "İstanbul 4. İdare Mahkemesi" ve
    "ISTANBUL 4.IDARE MAHKEMESI" aynı; "Ankara 5." ile "Ankara 15." farklı."""
    metin = (deger or "").translate(_TR)
    metin = unicodedata.normalize("NFD", metin)
    metin = "".join(ch for ch in metin if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9/]", "", metin.upper())


def otomatik_imza(source: Optional[str]) -> bool:
    return bool(source) and (source.startswith(AKTARIM_SOURCE_PREFIX) or source == YAZIM_BIRLIGI)


def karar(h: models.CaseHistory) -> Optional[str]:
    """Satır silinecekse sebep etiketi, kalacaksa None."""
    if not otomatik_imza(h.source):
        return None                                        # kullanıcı / belge işleme / birleştirme
    if h.field_name in BIRLESTIRME_ALANLARI or h.field_name == FOY_BAGLAMA_ALANI:
        return None
    if h.field_name in KORUNAN_ALANLAR:
        eski = (h.old_value or "").strip()
        if not eski:
            return "ilk dolum"
        if h.field_name == "esas_no":
            # Kimlik sayılmayan esas (yer tutucu '2022/', '2022/???', ';' birleşik
            # kalıntı) gerçek değişim kuramaz — esas_anahtari ile aynı ilke.
            eski_a, yeni_a = esas_anahtari(h.old_value), esas_anahtari(h.new_value)
            if not eski_a or not yeni_a:
                return "yer tutucu esas"
            return "yalnız biçim" if eski_a == yeni_a else None
        if h.field_name == "court":
            # Yapısal mahkeme kimliği aynıysa (Mahkemesi/Mahkemeleri, eksik "1.",
            # sıfatıyla eki, harf/aksan) biçim farkıdır — tku_kart_birlestir ile aynı kapı.
            return "yalnız biçim" if mahkeme_uyumu(h.old_value, h.new_value) is None else None
        if _anahtar(h.old_value) == _anahtar(h.new_value):
            return "yalnız biçim"
        return None                                        # gerçek değişim — kalır
    return "dolgu izi"


@dataclass
class Sonuc:
    okunan: int = 0
    silinen: int = 0
    kalan: int = 0
    sebep: Dict[str, int] = field(default_factory=dict)
    kalan_alan: Dict[str, int] = field(default_factory=dict)
    silinen_kart: set = field(default_factory=set)


def _satirlar(db) -> Iterable[models.CaseHistory]:
    return (db.query(models.CaseHistory)
            .filter(or_(models.CaseHistory.source.startswith(AKTARIM_SOURCE_PREFIX, autoescape=True),
                        models.CaseHistory.source == YAZIM_BIRLIGI))
            .order_by(models.CaseHistory.id)
            .yield_per(5000))


def temizle(session_factory, *, apply: bool = False, yedek: Optional[str] = None,
            parti: int = 5000) -> Sonuc:
    sonuc = Sonuc()
    db = session_factory()
    yazici = None
    dosya = None
    try:
        if yedek:
            dosya = open(yedek, "w", newline="", encoding="utf-8-sig")
            yazici = csv.writer(dosya, delimiter=";")
            yazici.writerow(["id", "case_id", "field_name", "old_value", "new_value",
                             "changed_at", "changed_by", "source", "sebep"])
        silinecek: List[int] = []
        for h in _satirlar(db):
            sonuc.okunan += 1
            sebep = karar(h)
            if sebep is None:
                sonuc.kalan += 1
                sonuc.kalan_alan[h.field_name] = sonuc.kalan_alan.get(h.field_name, 0) + 1
                continue
            sonuc.silinen += 1
            sonuc.sebep[sebep] = sonuc.sebep.get(sebep, 0) + 1
            sonuc.silinen_kart.add(h.case_id)
            if yazici:
                yazici.writerow([h.id, h.case_id, h.field_name, h.old_value, h.new_value,
                                 h.changed_at.isoformat() if h.changed_at else "", h.changed_by, h.source, sebep])
            silinecek.append(h.id)
        if apply:
            for i in range(0, len(silinecek), parti):
                (db.query(models.CaseHistory)
                 .filter(models.CaseHistory.id.in_(silinecek[i:i + parti]))
                 .delete(synchronize_session=False))
            db.commit()
        else:
            db.rollback()
    finally:
        if dosya:
            dosya.close()
        db.close()
    return sonuc


def ozet_metni(s: Sonuc, *, apply: bool) -> str:
    satirlar = [
        "=" * 66,
        f"Tarihçe temizliği — {'YAZILDI' if apply else 'KURU KOŞU'}",
        "=" * 66,
        f"  okunan otomatik satır : {s.okunan}",
        f"  silinen               : {s.silinen} ({len(s.silinen_kart)} kart)",
    ]
    for k, v in sorted(s.sebep.items(), key=lambda x: -x[1]):
        satirlar.append(f"      {k}: {v}")
    satirlar.append(f"  kalan (otomatik imzalı): {s.kalan}")
    for k, v in sorted(s.kalan_alan.items(), key=lambda x: -x[1]):
        satirlar.append(f"      {k}: {v}")
    satirlar.append("=" * 66)
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="case_history tek seferlik aktarım gürültüsü temizliği")
    parser.add_argument("--apply", action="store_true", help="sil (varsayılan kuru koşu)")
    parser.add_argument("--yedek", default=None, help="silinecek satırların CSV dökümü (geri alma yedeği)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from logging_setup import configure_logging

    configure_logging()
    import database

    if args.apply and not args.yedek:
        print("--apply için --yedek zorunlu (silinen satırların dökümü)")
        return 2
    sonuc = temizle(database.SessionLocal, apply=args.apply, yedek=args.yedek)
    print(ozet_metni(sonuc, apply=args.apply))
    if args.yedek:
        print(f"  yedek: {args.yedek}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
