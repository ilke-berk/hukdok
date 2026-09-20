#!/usr/bin/env python3
"""Korunan alanların KAYNAĞI — veri ekibinin Ek-6 › 03 sorusunun cevabı (salt okunur).

Ekip (17.09): "Koruduğunuz 23 alanın çoğu bizimkinden yeni; on beş föyü ilgilendiriyor,
on üçünde bizde olmayan bir 2026 esası var, sekizinde esas ile mahkeme birlikte değişmiş.
Bu 23 alanı ne ile güncellediniz — karar ya da tebligat belgesi mi, dosya sorgusu mu,
avukat notu mu? Kaynağını bilirsek kendi kaydımızı da aynı düzende güncelleriz."

Bu script hiçbir şey YAZMAZ: Ek-6 › 03'teki (kart, alan) çiftleri için `case_history`
satırlarını okur, `source` imzasını sınıflar ve CSV üretir. Sınıflar:

* `BELGE`            — imza `belge:<ad>` (`routes/processing.py`) ya da
                       `intake-enrich: <ad>` (`routes/case_intake.py`): değeri belge yazdı.
                       Belge adı `case_documents`te bulunursa SharePoint bağlantısı da yazılır.
* `BELGEDEN_TURETME` — `auto-enrich` / `auto-stage` / `auto-teblig`: belge işlemenin
                       türettiği alan (belge adı imzada yok, aynı kartın belgeleri listelenir).
* `PANELDEN_ELLE`    — `update_case` / takip paneli: kullanıcı elle yazdı.
* `PAKET`            — `HUKDOK_TESLIM_*`: paketin kendi yazdığı değer (korunan alanda
                       beklenmez; çıkarsa korumanın yanlış tetiklendiğini gösterir).
* `KAYNAK_YOK`       — `source` NULL (eski elle düzenlemeler, `models.py` şerhi).
* `TARIHCE_YOK`      — o alan için hiç `case_history` satırı yok.

`esas_no` için `case_esas_numbers` satırının kendi `source`/`stage` bilgisi de yazılır
(tek yazma yolu `case_manager.sync_current_esas` oraya imza bırakır).

    docker compose exec -T backend python scripts/korunan_alan_kaynaklari.py \\
        --ek6 /app/data/HUKDOK_CEVAP_EKI_6_2026-09-17.xlsx --rapor /app/data/korunan_kaynak.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from scripts.ekip_cevabi_1209 import _kolon, _sayfa, _tam_sayi

logger = logging.getLogger("KorunanAlanKaynaklari")

EK6_KORUNAN_SAYFASI = "03_KORUNAN_23_ALAN"

# Ekin "Alan" sütunu → kart kolonu
ALAN_KOLONU = {"esas": "esas_no", "yerel mahkeme": "court", "mahkeme": "court"}

BASLIKLAR = ("foy", "dosya_no", "kart", "alan", "kolon", "korunan_deger", "paket_degeri",
             "bugunku_deger", "kaynak_sinifi", "degistiren", "kaynak_imzasi", "degisim_zamani",
             "belge", "sharepoint_url", "esas_tarihcesi")


@dataclass
class Kalem:
    foy: str
    dosya_no: str
    kart: int
    alan: str
    kolon: str
    korunan_deger: str
    paket_degeri: str
    bugunku_deger: str = ""
    kaynak_sinifi: str = ""
    degistiren: str = ""
    kaynak_imzasi: str = ""
    degisim_zamani: str = ""
    belge: str = ""
    sharepoint_url: str = ""
    esas_tarihcesi: str = ""

    def satir(self) -> List[str]:
        return [str(getattr(self, b) or "") for b in BASLIKLAR]


def ek6_oku(yol: Path) -> List[Kalem]:
    import openpyxl
    wb = openpyxl.load_workbook(yol, data_only=True, read_only=True)
    try:
        satirlar = list(_sayfa(wb, EK6_KORUNAN_SAYFASI).iter_rows(values_only=True))
        basliklar = satirlar[0]
        i_foy = _kolon(basliklar, "Föy")
        i_dosya = _kolon(basliklar, "Dosya No")
        i_kart = _kolon(basliklar, "Kart")
        i_alan = _kolon(basliklar, "Alan")
        i_korunan = _kolon(basliklar, "Sizin koruduğunuz değer")
        i_paket = _kolon(basliklar, "Paketimizdeki değer")
        kalemler = []
        for satir in satirlar[1:]:
            kart = _tam_sayi(satir[i_kart])
            alan = str(satir[i_alan] or "").strip()
            if kart is None or not alan:
                continue
            kalemler.append(Kalem(
                foy=str(satir[i_foy] or ""), dosya_no=str(satir[i_dosya] or ""), kart=kart, alan=alan,
                kolon=ALAN_KOLONU.get(alan.casefold(), ""),
                korunan_deger=str(satir[i_korunan] or ""), paket_degeri=str(satir[i_paket] or ""),
            ))
        return kalemler
    finally:
        wb.close()


def _sinifla(source: Optional[str]) -> Tuple[str, str]:
    """(sınıf, belge adı) — imza metninden."""
    if source is None or not source.strip():
        return "KAYNAK_YOK", ""
    imza = source.strip()
    for onek in ("belge:", "intake-enrich:"):
        if imza.casefold().startswith(onek):
            return "BELGE", imza[len(onek):].strip()
    if imza.startswith("HUKDOK_TESLIM"):
        return "PAKET", ""
    if imza.split(":")[0].strip() in ("auto-enrich", "auto-stage", "auto-teblig"):
        return "BELGEDEN_TURETME", ""
    if imza.startswith("update_case") or imza.startswith("tracking"):
        return "PANELDEN_ELLE", ""
    return "DIGER", ""


def _kaynak_satiri(db, kart: int, kolon: str, korunan: str) -> Optional[models.CaseHistory]:
    """Korunan değeri YAZAN tarihçe satırı; bulunamazsa o alanın en yeni satırı."""
    satirlar = (db.query(models.CaseHistory)
                .filter(models.CaseHistory.case_id == kart, models.CaseHistory.field_name == kolon)
                .order_by(models.CaseHistory.changed_at.desc(), models.CaseHistory.id.desc()).all())
    for satir in satirlar:
        if (satir.new_value or "").strip() == korunan.strip():
            return satir
    return satirlar[0] if satirlar else None


def kalemleri_doldur(db, kalemler: Sequence[Kalem]) -> None:
    for kalem in kalemler:
        kart = db.get(models.Case, kalem.kart)
        if kart is None:
            kalem.kaynak_sinifi = "KART_YOK"
            continue
        if not kalem.kolon:
            kalem.kaynak_sinifi = "ALAN_TANINMADI"
            continue
        kalem.bugunku_deger = str(getattr(kart, kalem.kolon) or "")
        satir = _kaynak_satiri(db, kalem.kart, kalem.kolon, kalem.korunan_deger)
        if satir is None:
            kalem.kaynak_sinifi = "TARIHCE_YOK"
        else:
            kalem.kaynak_sinifi, belge_adi = _sinifla(satir.source)
            kalem.degistiren = satir.changed_by or ""
            kalem.kaynak_imzasi = satir.source or ""
            kalem.degisim_zamani = satir.changed_at.isoformat() if satir.changed_at else ""
            kalem.belge = belge_adi
        if kalem.kaynak_sinifi in ("BELGE", "BELGEDEN_TURETME"):
            _belgeyi_bagla(db, kalem)
        if kalem.kolon == "esas_no":
            kalem.esas_tarihcesi = _esas_tarihcesi(db, kalem.kart, kalem.korunan_deger)


def _belgeyi_bagla(db, kalem: Kalem) -> None:
    sorgu = db.query(models.CaseDocument).filter(models.CaseDocument.case_id == kalem.kart)
    if kalem.belge:
        belge = sorgu.filter(models.CaseDocument.original_filename == kalem.belge).first()
        if belge is not None:
            kalem.sharepoint_url = belge.sharepoint_url or ""
            return
    # İmzada ad yok (auto-*) ya da ad tutmadı: kartın belgeleri listelenir
    belgeler = sorgu.order_by(models.CaseDocument.id).all()
    if not kalem.belge:
        kalem.belge = " ; ".join(b.original_filename for b in belgeler[:5])
    kalem.sharepoint_url = " ; ".join(b.sharepoint_url for b in belgeler[:5] if b.sharepoint_url)


def _esas_tarihcesi(db, kart: int, esas_no: str) -> str:
    satirlar = (db.query(models.CaseEsasNumber)
                .filter(models.CaseEsasNumber.case_id == kart)
                .order_by(models.CaseEsasNumber.id).all())
    return " ; ".join(
        f"{s.esas_no} ({s.stage}{'·güncel' if s.is_current else ''}, kaynak={s.source or '—'})"
        for s in satirlar) or "—"


def kos(session_factory, *, ek6: Path) -> List[Kalem]:
    kalemler = ek6_oku(ek6)
    db = session_factory()
    try:
        kalemleri_doldur(db, kalemler)
    finally:
        db.close()
    return kalemler


def csv_yaz(kalemler: Sequence[Kalem], yol: Path) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    with yol.open("w", encoding="utf-8-sig", newline="") as f:      # BOM: Türkçe Excel
        yazici = csv.writer(f, delimiter=";")
        yazici.writerow(BASLIKLAR)
        for kalem in kalemler:
            yazici.writerow(kalem.satir())


def ozet_metni(kalemler: Sequence[Kalem]) -> str:
    sayim: dict = {}
    for kalem in kalemler:
        sayim[kalem.kaynak_sinifi] = sayim.get(kalem.kaynak_sinifi, 0) + 1
    satirlar = ["=" * 78, f"Korunan alanların kaynağı — {len(kalemler)} alan (Ek-6 › 03)", "=" * 78]
    for sinif, adet in sorted(sayim.items(), key=lambda x: (-x[1], x[0])):
        satirlar.append(f"  {sinif:20} {adet:3}")
    satirlar.append("  " + "-" * 74)
    for kalem in kalemler:
        satirlar.append(f"  #{kalem.kart:<6} {kalem.foy:12} {kalem.alan:14} {kalem.kaynak_sinifi:18} "
                        f"{kalem.korunan_deger!r} ← {kalem.kaynak_imzasi or '—'}")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Korunan alanların kaynağı (salt okunur)")
    ayristirici.add_argument("--ek6", required=True, type=Path,
                             help="HUKDOK_CEVAP_EKI_6_2026-09-17.xlsx")
    ayristirici.add_argument("--rapor", type=Path, default=None, help="CSV çıktısı")
    args = ayristirici.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    kalemler = kos(SessionLocal, ek6=args.ek6)
    if args.rapor:
        csv_yaz(kalemler, args.rapor)
        logger.info(f"Rapor yazıldı: {args.rapor}")
    print(ozet_metni(kalemler))
    return 0


if __name__ == "__main__":
    sys.exit(main())
