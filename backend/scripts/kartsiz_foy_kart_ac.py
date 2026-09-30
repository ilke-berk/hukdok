#!/usr/bin/env python3
"""Teslim paketinde kartı olmayan föyler için dava kartı açar (G126).

Aktarım kart AÇMAZ (hukdok_aktarim "Kart YARATILMAZ" kuralı: eşleşmeyen satır
raporda kalır). 04.09 paketinde 217 föy (210 DosyaNo) bizde hiçbir karta
düşmüyordu — 186'sı aktif, 170'i 2026 iş kabullü. Kullanıcı kararı (05.09):
"217 kartsız föy için kart açalım". Bu script o boşluğu kapatır; aktarım
sonraki koşuda föyleri DosyaNo köprüsüyle bu kartlara bağlar ve tüm alanları
(taraf, avukat, esas, tarih, tıbbi tasnif, ham satır) kendisi yazar.

Kural: kart MİNİMAL açılır (ofis no, klasör no, durum, tür, konu, mahkeme,
esas, dava tarihi); taraf/avukat YAZILMAZ — aktarımın işi (add_case'in
"otomatik cari kart" davranışı da böylece tetiklenmez). Ofis numarası karar 023
formatındadır (G239): her parçası `services/ofis_no` üreticisinden, sıra
`ofis_no_sayaclari` sayacından (`sira_tahsis_et`) — numara AYRIŞTIRILMAZ, eski
"isim bloğu başına max+1" taraması kalktı. Kategori föyün `Müvekkil Tipi`nden,
sigortalı bloğu föyün ham `Sigortalı` sütunundan gelir. Kuru koşuda sayaç
ilerlemez (tahsis geri alınır). Aynı DosyaNo'daki föyler TEK karta gider
(kart bölünmez, G063).

    docker compose exec -T backend python scripts/kartsiz_foy_kart_ac.py \\
        --input /tmp/paket.xlsx [--rapor-dizini /tmp/kart]      # kuru koşu
    docker compose exec -T backend python scripts/kartsiz_foy_kart_ac.py \\
        --input /tmp/paket.xlsx --apply                          # açar

İdempotent: açılan kartın klasör no'su DosyaNo olduğundan ikinci koşuda o
föyler "kartlı" sayılır, 0 kart açılır. Gerçek paket repoya girmez (A.2).
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager, foy_map
from scripts import hukdok_aktarim as ha
from services import ofis_no

logger = logging.getLogger("KartsizFoy")

# Aynı DosyaNo'da farklı tür (ARB + HUKUK): kartın türü davanın "asıl" türü.
TUR_ONCELIGI = ("HUKUK", "IDARE", "CEZA", "ICRA", "SAVCILIK", "TAHKIM", "DANISMANLIK", "ARABULUCULUK")


@dataclass
class KartAdayi:
    dosya_no: str
    sistem_nolar: List[str]
    muvekkil: str
    muvekkil_tipi: str
    file_type: str
    status: str
    subject: Optional[str]
    court: Optional[str]
    esas_no: Optional[str]
    opening_date: Optional[str]
    tracking_no: str = ""
    # Karar 023 parçaları (G239): `ofis_numarasi` doldurur, kart kolonlarına yazılır.
    ofis_no_kodu: Optional[str] = None
    ofis_no_sira: Optional[int] = None
    # Föylerin ham satırları (orijinal başlıklar) — sigortalı bloğunun kaynağı.
    ham_satirlar: List[Dict[str, Any]] = field(default_factory=list)
    case_id: Optional[int] = None
    hata: Optional[str] = None
    notlar: List[str] = field(default_factory=list)


def kartsiz_foyler(db, satirlar: Sequence[ha.HamSatir]) -> List[ha.HamSatir]:
    """Ne SistemNo'su ne DosyaNo parçası bir karta düşen föyler (aktarımın
    'Kart bulunamadı' kümesi; belirsiz eşleşmeler — DosyaNo 2+ kart — HARİÇ)."""
    sistem_nolar = [ha._metin(s.degerler.get("sistem_no")) for s in satirlar]
    foy_haritasi = foy_map.map_sistem_no_to_case(db, [s for s in sistem_nolar if s])
    dosya_haritasi = ha._dosya_no_haritasi(db)
    sonuc = []
    for satir in satirlar:
        sistem_no = ha._metin(satir.degerler.get("sistem_no"))
        if not sistem_no or sistem_no in foy_haritasi:
            continue
        parcalar = ha._dosya_no_parcalari(satir.degerler.get("dosya_no"))
        if not parcalar:
            continue                      # Dosya No boş: köprü yok, kart da açılmaz (rapor)
        if ha._dosya_no_adaylari(dosya_haritasi, parcalar):   # parçalar zaten normalize anahtar
            continue                      # kart var (tek, belirsiz ya da noktasız ikincil) — aktarımın işi
        sonuc.append(satir)
    return sonuc


def _ilk(deger: Any) -> Optional[str]:
    metin = ha._metin(deger)
    if metin is None:
        return None
    return ha._AYRAC.split(metin)[0].strip() or None


def _tarih_iso(deger: Any) -> Optional[str]:
    tarih = ha._tarih(deger, "opening_date") if deger is not None else None
    return tarih.isoformat() if isinstance(tarih, date) else None


def _tur(satirlar: Sequence[ha.HamSatir]) -> str:
    anahtarlar = {ha._baslik_anahtari(ha._metin(s.degerler.get("ana_tur")) or "") for s in satirlar}
    for tur in TUR_ONCELIGI:
        if tur in anahtarlar:
            return ha.ANA_TUR_ESLEMESI[tur]
    return "Hukuk"


def kart_adaylari(foyler: Sequence[ha.HamSatir]) -> List[KartAdayi]:
    """Kartsız föyleri DosyaNo'ya göre gruplar; grup başına bir kart adayı."""
    gruplar: Dict[str, List[ha.HamSatir]] = {}
    for satir in foyler:
        gruplar.setdefault(ha._metin(satir.degerler.get("dosya_no")) or "", []).append(satir)
    def _oncelik(satir: ha.HamSatir) -> int:
        tur = ha._baslik_anahtari(ha._metin(satir.degerler.get("ana_tur")) or "")
        return TUR_ONCELIGI.index(tur) if tur in TUR_ONCELIGI else len(TUR_ONCELIGI)

    def _ilk_dolu(satirlar: Sequence[ha.HamSatir], alan: str, donustur=ha._metin) -> Optional[str]:
        for s in satirlar:
            deger = donustur(s.degerler.get(alan))
            if deger:
                return deger
        return None

    adaylar = []
    for dosya_no, satirlar in sorted(gruplar.items()):
        # Asıl davanın föyü (HUKUK/İDARE…) önce, arabuluculuk sonra: künye
        # (esas, mahkeme, konu, tarih) asıl davadan; o boşsa öbür föyden.
        sirali = sorted(satirlar, key=_oncelik)
        aktif = any(ha._baslik_anahtari(ha._metin(s.degerler.get("durum")) or "") == "AKTIF" for s in satirlar)
        adaylar.append(KartAdayi(
            dosya_no=dosya_no,
            sistem_nolar=[ha._metin(s.degerler.get("sistem_no")) or "" for s in satirlar],
            muvekkil=_ilk_dolu(sirali, "muvekkil", _ilk) or "",
            muvekkil_tipi=_ilk_dolu(sirali, "muvekkil_tipi") or "",
            file_type=_tur(satirlar),
            status="DERDEST" if aktif else "MAHZEN",
            subject=_ilk_dolu(sirali, "dava_konusu"),
            court=_ilk_dolu(sirali, "yerel_mahkeme"),
            esas_no=_ilk_dolu(sirali, "esas"),
            opening_date=_ilk_dolu(sirali, "dava_tarihi", _tarih_iso),
            ham_satirlar=[dict(s.ham) for s in sirali if s.ham],
        ))
    return adaylar


def _muvekkiller(aday: KartAdayi) -> List[Dict[str, Any]]:
    """Üreticinin müvekkil listesi: ad + kategori (föyün `Müvekkil Tipi`, DB-2026-002).

    Tip üreticiye HAM verilir — `ofis_no` kategori adını kendisi çözer ("Diğer Sağlık
    Çalışanı" → SC, "Sigorta" → şirket kodu, "Kurum" → KR); boş/tanınmayan tipte ad
    kuralı (şirket işareti → KR, yoksa BR) geçerlidir. Göç (G238) de föy tipini böyle okur.
    """
    return [{"name": aday.muvekkil, "category": aday.muvekkil_tipi or None}]


def musteri_kodu(aday: KartAdayi, kod_listeleri: Optional[ofis_no.KodListeleri] = None) -> str:
    """Adayın müvekkil kodu — numaranın ilk bloğu (`DR.H.ARTUC`, `QUICK`), `cases.ofis_no_kodu`.

    Sıradan bağımsızdır: `scripts/birlesik_kart_ayir.py` müvekkil ayrımında "hangi grup
    kartta kalır" sorusunu kartın `ofis_no_kodu` kolonuyla karşılaştırarak yanıtlar.
    Ad boşsa/çözülemiyorsa `ValueError` (yer tutucu kod üretilmez).
    """
    return ofis_no.musteri_kodu(_muvekkiller(aday), kod_listeleri)[0]


def kart_kodu(kart: Any, kod_listeleri: Optional[ofis_no.KodListeleri] = None) -> str:
    """Kartın müvekkil kodu — `cases.ofis_no_kodu` kolonu; numara AYRIŞTIRILMAZ.

    Kolon boşsa (göç öncesi kart: numarası eski formatta) kod, kartın CLIENT taraflarından
    üreticinin kendisiyle hesaplanır (kategori bağlı müvekkil kaydından) — eski ve yeni
    numaralı kartlar aynı ölçüyle kıyaslanır. Müvekkilsiz kartta boş metin döner (boş kod
    hiçbir kartla eşleşmez).
    """
    kod = str(getattr(kart, "ofis_no_kodu", None) or "").strip()
    if kod:
        return kod
    muvekkiller = [
        {"name": p.name, "category": getattr(getattr(p, "client", None), "category", None)}
        for p in (getattr(kart, "parties", None) or [])
        if (getattr(p, "party_type", None) or "") == "CLIENT" and (p.name or "").strip()
    ]
    try:
        return ofis_no.musteri_kodu(muvekkiller, kod_listeleri)[0]
    except ValueError:
        return ""


def ofis_numarasi(db, aday: KartAdayi, kullanilan: Dict[str, int]) -> str:
    """Karar 023 numarası: `services/ofis_no` üreticisi + sayaçtan sıra (`sira_tahsis_et`).

    Sıra çağıranın transaction'ında tahsis edilir — commit edilmezse geri döner (kuru koşu
    sayaç yakmaz). `aday.ofis_no_kodu`/`ofis_no_sira` doldurulur, `kullanilan` bu koşuda kod
    başına verilen son sırayı taşır (rapor). Müvekkil adı çözülemezse `ValueError`.
    """
    kl = ofis_no.kod_listelerini_yukle(db)
    muvekkiller = _muvekkiller(aday)
    kod, secilen = ofis_no.musteri_kodu(muvekkiller, kl)
    sigortali = None
    if ofis_no.sigortaci_mi(secilen.get("name"), secilen.get("category")):
        sigortali = ofis_no.sigortali_sec(
            foys=[{"ham_veri": ham} for ham in aday.ham_satirlar], parties=[],
            muvekkiller=muvekkiller, kod_listeleri=kl,
        )
    sira = ofis_no.sira_tahsis_et(db, kod)
    aday.ofis_no_kodu, aday.ofis_no_sira = kod, sira
    kullanilan[kod] = sira
    return ofis_no.numara_kur(kod, sira, sigortali, ofis_no.tur_kodu(aday.file_type))


def kartlari_ac(session_factory, *, girdi: Path, sheet: str = "Sheet",
                apply: bool = False, rapor_dizini: Optional[Path] = None) -> List[KartAdayi]:
    satirlar, _ = ha.xlsx_oku(girdi, sheet=sheet)
    db = session_factory()
    try:
        adaylar = kart_adaylari(kartsiz_foyler(db, satirlar))
        kullanilan: Dict[str, int] = {}
        for aday in adaylar:
            if not aday.muvekkil:
                aday.hata = "Müvekkil boş — ofis numarası üretilemez"
                continue
            try:
                aday.tracking_no = ofis_numarasi(db, aday, kullanilan)
            except ValueError as exc:
                aday.hata = f"Ofis numarası üretilemedi: {exc}"
        # Sıra tahsisi bu oturumun transaction'ında: --apply'da kalıcılaşır (kart
        # açılamazsa numara atlanır — mükerrere tercih edilir), kuru koşuda geri alınır.
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    if apply:
        for aday in adaylar:
            if aday.hata:
                continue
            sonuc = case_manager.add_case({
                "tracking_no": aday.tracking_no, "status": aday.status,
                "file_type": aday.file_type, "subject": aday.subject, "court": aday.court,
                "esas_no": aday.esas_no, "opening_date": aday.opening_date,
                "klasor_no_2": aday.dosya_no, "parties": [], "lawyers": [],
                "notes": f"Teslim paketinden açıldı (kartsız föy): {', '.join(aday.sistem_nolar)}",
            })
            if not sonuc or sonuc.get("error"):
                aday.hata = f"add_case: {sonuc.get('error') if sonuc else 'None'}"
                logger.warning(f"{aday.dosya_no} kart açılamadı: {aday.hata}")
            else:
                aday.case_id = sonuc.get("id")
                _ofis_no_kolonlarini_yaz(session_factory, aday)
    if rapor_dizini is not None:
        rapor_dizini.mkdir(parents=True, exist_ok=True)
        yol = rapor_dizini / f"acilan-kartlar_{datetime.now():%Y%m%d-%H%M%S}.csv"
        with open(yol, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["dosya_no", "sistem_nolar", "tracking_no", "case_id", "muvekkil",
                        "muvekkil_tipi", "file_type", "status", "esas_no", "court", "hata"])
            for a in adaylar:
                w.writerow([a.dosya_no, " ; ".join(a.sistem_nolar), a.tracking_no, a.case_id or "",
                            a.muvekkil, a.muvekkil_tipi, a.file_type, a.status, a.esas_no or "",
                            a.court or "", a.hata or ""])
    return adaylar


def _ofis_no_kolonlarini_yaz(session_factory, aday: KartAdayi) -> None:
    """Açılan karta `ofis_no_kodu`/`ofis_no_sira` yazar.

    `add_case` kendi numarasıyla gelen (bayraksız) çağrıda bu iki kolonu boş bırakır;
    numarayı ayrıştırmadan okuyan her yol (mükerrer raporu, kart ayırma, göçün "zaten
    yeni formatta" sırası) kolonlara bakar — boş kalmamalı.
    """
    db = session_factory()
    try:
        db.query(models.Case).filter(models.Case.id == aday.case_id).update(
            {"ofis_no_kodu": aday.ofis_no_kodu, "ofis_no_sira": aday.ofis_no_sira},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def ozet_metni(adaylar: Sequence[KartAdayi], *, apply: bool) -> str:
    foy = sum(len(a.sistem_nolar) for a in adaylar)
    hatali = [a for a in adaylar if a.hata]
    satirlar = [
        f"kartsız föy: {foy} · kart adayı (DosyaNo grubu): {len(adaylar)} · hatalı: {len(hatali)}",
        f"açılan kart: {sum(1 for a in adaylar if a.case_id)}" if apply else "kuru koşu — kart açılmadı (--apply)",
    ]
    for a in adaylar[:8]:
        satirlar.append(f"  {a.dosya_no:14} {a.tracking_no:32} {a.status:8} {a.file_type:12} {a.muvekkil[:30]}")
    if len(adaylar) > 8:
        satirlar.append(f"  … ({len(adaylar) - 8} aday daha, rapor CSV'de)")
    for a in hatali[:5]:
        satirlar.append(f"  HATA {a.dosya_no}: {a.hata}")
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Kartsız föyler için dava kartı açar (G126)")
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet", default="Sheet")
    parser.add_argument("--apply", action="store_true", help="kartları aç (varsayılan kuru koşu)")
    parser.add_argument("--rapor-dizini", default=None)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from logging_setup import configure_logging

    configure_logging()
    import database

    adaylar = kartlari_ac(
        database.SessionLocal, girdi=Path(args.input), sheet=args.sheet, apply=args.apply,
        rapor_dizini=Path(args.rapor_dizini) if args.rapor_dizini else None,
    )
    print(ozet_metni(adaylar, apply=args.apply))
    return 1 if any(a.hata for a in adaylar) else 0


if __name__ == "__main__":
    sys.exit(main())
