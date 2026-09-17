#!/usr/bin/env python3
"""Kapanmamış parantezli 5 hücre — veri ekibine 17.09.2026 cevabında verilen söz.

**Kök neden (ölçüm 17.09, lokal = prod kopyası):** beş hücrenin hiçbirinde tarihçe satırı
yok; kartlar 27.04.2026 00:02-00:03'te ilk yüklemeyle (`import_excel_cases.py`) açıldı.
Teslim paketleri bu hataları getirmez: paket ham satırlarında (`case_foys.ham_veri`) taraf ve
mahkeme sütunlarında dengesiz parantez 0 (yalnız serbest metin "Karar Açıklaması"nda 5);
aktarım tarafları yalnız-ekleme ile yazar, mevcut adı değiştirmez; 7634/8996/12398'in föyü
yok. DB'nin tamamında dengesiz parantezli aktif taraf/mahkeme tam bu beştir → aktarıma kontrol
EKLENMEDİ (kullanıcı kararı 17.09); script sonunda kalan sayısı raporlanır (bekçi).

Düzeltmeler (değerler kullanıcı onaylı, 17.09) — yalnız parantez; yazım (i/ı) ayrı iştir:

* 4829 · Diğer Davalı (taraf 22632): hastane adı + tüzel kişi parantezi kapatılır.
* 13353 · Diğer Davalı (taraf 45317): aynı.
* 7634 ve 8996 · Karşı Taraf (29408, 32350): "( Kendi adına Asaleten" sıfatı taraf ADI değildir
  (tanıdık sorgusu / çatışma kontrolü adla eşleşir) ve kesik → yalnız ad kalır; eski değer
  tarihçede.
* 12398 · Yerel mahkeme: mahkeme adına gömülü eski mahkeme + esas
  ("( Eski--istanbul Anadolu 10. Atm)2013/720)") esas tarihçesine taşınır —
  `case_manager.add_historical_esas` (aşama ONCEKI, `is_current`'a dokunmaz; güncel esas
  2014/700 aynen kalır), mahkeme adı temizlenir.

Her satır beklenen ESKİ değeri taşımıyorsa dokunulmaz (RET — biri elle düzeltmiş olabilir);
yeni değeri zaten taşıyorsa ATLANDI. Tek transaction; `--apply` yoksa geri alınır.
İkinci koşu 0 değişiklik.

    docker compose exec -T backend python scripts/parantez_duzeltme.py                 # kuru koşu
    docker compose exec -T backend python scripts/parantez_duzeltme.py --apply --kim ilke
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Sequence, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager
from scripts.ekip_cevabi_1209 import Sonuc

logger = logging.getLogger("ParantezDuzeltme")
DEGISTIREN = "parantez_duzeltme"
KAYNAK = "kapanmamış parantez düzeltmesi (ekibe söz 17.09.2026; kaynak 27.04 ilk yükleme)"

# (kart, taraf satırı, eski ad, yeni ad)
TARAF_DUZELTMELERI: Tuple[Tuple[int, int, str, str], ...] = (
    (4829, 22632,
     "Bayindir Söğütözü Hastanesi(Bayek Sağlik Tedavi Hizmetleri ve İşletmeciliği A.Ş.",
     "Bayindir Söğütözü Hastanesi (Bayek Sağlik Tedavi Hizmetleri ve İşletmeciliği A.Ş.)"),
    (13353, 45317,
     "Özel Sante Plus Hastanesi ( Be Ka Sağlik Eğitim Tibbi Malzeme Tekstil Turizm Gida İnş. San. ve Tic. Ltd. Şti.",
     "Özel Sante Plus Hastanesi (Be Ka Sağlik Eğitim Tibbi Malzeme Tekstil Turizm Gida İnş. San. ve Tic. Ltd. Şti.)"),
    (7634, 29408, "Fatma Serap Aydoğdu ( Kendi adına Asaleten", "Fatma Serap Aydoğdu"),
    (8996, 32350, "Fatma Serap Aydoğdu ( Kendi adına Asaleten", "Fatma Serap Aydoğdu"),
)

# (kart, eski mahkeme, yeni mahkeme, eski esas, eski esasın mahkemesi)
MAHKEME_DUZELTMELERI: Tuple[Tuple[int, str, str, str, str], ...] = (
    (12398,
     "İstanbul Anadolu 1. Asliye Ticaret Mahkemesi( Eski--istanbul Anadolu 10. Atm)2013/720)",
     "İstanbul Anadolu 1. Asliye Ticaret Mahkemesi",
     "2013/720", "İstanbul Anadolu 10. Asliye Ticaret Mahkemesi"),
)

ADIM_ADLARI = {"taraf": "1. Taraf adı", "mahkeme": "2. Mahkeme + eski esas"}


def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan, old_value=eski, new_value=yeni,
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim})"[:300],
    ))


def taraflari_duzelt(db, kalemler, *, kim: str, sonuc: Sonuc) -> None:
    for kart_id, taraf_id, eski, yeni in kalemler:
        hedef = f"kart {kart_id} taraf {taraf_id}"
        taraf = db.get(models.CaseParty, taraf_id)
        if taraf is None or taraf.case_id != kart_id:
            sonuc.ekle("taraf", hedef, "RET", "taraf satırı yok ya da başka kartta")
            continue
        if taraf.name == yeni:
            sonuc.ekle("taraf", hedef, "ATLANDI", "zaten düzeltilmiş")
            continue
        if taraf.name != eski:
            sonuc.ekle("taraf", hedef, "RET", f"beklenmeyen değer {taraf.name!r} — elle bakılmalı")
            continue
        taraf.name = yeni
        _tarihce(db, kart_id, "taraf", f"{eski} ({taraf.role})", f"{yeni} ({taraf.role})", kim)
        sonuc.ekle("taraf", hedef, "YAPILDI", f"{eski!r} → {yeni!r}")
    db.flush()


def mahkemeleri_duzelt(db, kalemler, *, kim: str, sonuc: Sonuc) -> None:
    for kart_id, eski, yeni, eski_esas, eski_esas_mahkemesi in kalemler:
        hedef = f"kart {kart_id}"
        kart = db.get(models.Case, kart_id)
        if kart is None:
            sonuc.ekle("mahkeme", hedef, "RET", "kart yok")
            continue
        yapilan = []
        if kart.court == eski:
            kart.court = yeni
            _tarihce(db, kart_id, "court", eski, yeni, kim)
            yapilan.append(f"mahkeme {yeni!r}")
        elif kart.court != yeni:
            sonuc.ekle("mahkeme", hedef, "RET", f"beklenmeyen mahkeme {kart.court!r} — elle bakılmalı")
            continue
        if case_manager.add_historical_esas(db, kart, eski_esas, court=eski_esas_mahkemesi,
                                            source=f"{DEGISTIREN} ({kim})"):
            yapilan.append(f"esas tarihçesi {eski_esas} ({eski_esas_mahkemesi}, ONCEKI)")
        if yapilan:
            sonuc.ekle("mahkeme", hedef, "YAPILDI", " · ".join(yapilan))
        else:
            sonuc.ekle("mahkeme", hedef, "ATLANDI", "zaten düzeltilmiş")
    db.flush()


def _dengesiz(kolon):
    return func.length(kolon) - func.length(func.replace(kolon, "(", "")) != \
        func.length(kolon) - func.length(func.replace(kolon, ")", ""))


def kalan_dengesiz(db) -> Tuple[int, int]:
    """Aktif kartlarda dengesiz parantezli taraf adı / mahkeme sayısı (bekçi ölçümü)."""
    taraf = (db.query(func.count(models.CaseParty.id))
             .join(models.Case, models.Case.id == models.CaseParty.case_id)
             .filter(models.Case.deleted_at.is_(None), _dengesiz(models.CaseParty.name)).scalar())
    mahkeme = (db.query(func.count(models.Case.id))
               .filter(models.Case.deleted_at.is_(None), models.Case.court.isnot(None),
                       _dengesiz(models.Case.court)).scalar())
    return int(taraf or 0), int(mahkeme or 0)


def kos(session_factory, *, apply: bool = False, kim: str = DEGISTIREN) -> Tuple[Sonuc, Tuple[int, int]]:
    sonuc = Sonuc()
    db = session_factory()
    try:
        taraflari_duzelt(db, TARAF_DUZELTMELERI, kim=kim, sonuc=sonuc)
        mahkemeleri_duzelt(db, MAHKEME_DUZELTMELERI, kim=kim, sonuc=sonuc)
        kalan = kalan_dengesiz(db)
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return sonuc, kalan


def ozet_metni(sonuc: Sonuc, kalan: Tuple[int, int], *, apply: bool) -> str:
    satirlar = ["=" * 78, f"Kapanmamış parantez düzeltmesi — {'UYGULANDI' if apply else 'KURU KOŞU'}", "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET"))
        satirlar.append(f"  {ad:26} {y:4} yapıldı · {a:4} atlandı · {r:3} ret")
    if sonuc.kalemler:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in sonuc.kalemler)
    satirlar.append("  " + "-" * 74)
    satirlar.append(f"  Düzeltme sonrası dengesiz parantez (aktif kart): taraf {kalan[0]} · mahkeme {kalan[1]}")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Kapanmamış parantezli 5 hücrenin düzeltmesi")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc, kalan = kos(SessionLocal, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, kalan, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
