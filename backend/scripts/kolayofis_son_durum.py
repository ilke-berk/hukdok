#!/usr/bin/env python3
"""KolayOfis "Dosyalar Raporu" çıktısından dosya son durumlarını tazeler.

Kaynak: veri ekibinin kendi sisteminden (KolayOfis) alınan
`<tarih>_KolayOfis_DosyalarRaporu.xlsx`. Dosya FÖY düzeyindedir (SistemNo tekil) ve
yalnız "Aktif" dosyaları taşır; kapalı/arşiv kartlara dokunmaz. Rapor repoya GİRMEZ,
yolu `--rapor` ile verilir.

**Neden var:** son durum ekranlarda ve raporlarda başlık üzerinden aranan alandır
(`cases.dosya_son_durumu`). Teslim paketinin yazdığı değerler ekibin kendi sistemine
göre geride kalıyor; bu script iki kaynağı hizalar. Bir sonraki teslim paketi
"paket kazanır" kuralıyla alanı yeniden yazar — bu koşu o pakete kadar geçerli bir
tazelemedir, kalıcı çözüm paketin güncel gelmesidir.

Adımlar (hepsi tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Liste düzeltmesi** (`file_statuses`): panelin açılır listesi ekibin başlıklarıyla
   hizalanır — `İstinafta` → `İstinafda` (509 kart ekibin yazımını kullanıyor, liste
   yazımı hiçbir kartta geçmiyordu), eksik `Kapalı` ve `Soruşturma` eklenir.
2. **Kart yazım birliği:** `Bekletici Mesele/ceza-hukuk Dosyası` taşıyan kartlar
   listedeki tek yazıma (`…/Ceza-Hukuk…`) çekilir.
3. **Son durum tazeleme:** rapordaki föy satırı kartına çözülür, değer normalize edilir
   ve kartın alanı farklıysa tarihçeli yazılır.

Rapordaki yazım kusurları (17.09.2026 çıktısında ölçüldü):

* `Delliller Toplanıyor` (118 satır) — ekibin başlık listesinde de aynı hata var;
  bizdeki doğru yazıma (`Deliller Toplanıyor`) çevrilir.
* `Islah ` (12 satır) — sondaki boşluk kırpılır (`_metin` boşluk-normalize eder).
* `Lütfen Seçiniz` (28) ve boş hücre (118) — YAZILMAZ; dolu kutuyu boşaltmak veri kaybıdır.

Bir kart birden çok föy taşıyabilir: föyler farklı son durum söylüyorsa karta
DOKUNULMAZ (`CELISKI`), tek tek bakılması gerekir.

    docker compose exec -T backend python scripts/kolayofis_son_durum.py \\
        --rapor /app/data/2026_09_17_KolayOfis_DosyalarRaporu.xlsx          # kuru koşu
    docker compose exec -T backend python scripts/kolayofis_son_durum.py \\
        --rapor … --apply --kim ilke                                        # yazar

İkinci koşu 0 değişiklik: eşit alan `ATLANDI` döner, liste düzeltmesi idempotenttir.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers.seed_data import _karar_kodu
from scripts.ekip_cevabi_1209 import Sonuc
from scripts.hukdok_aktarim import _baslik_anahtari, _metin

logger = logging.getLogger("KolayOfisSonDurum")
DEGISTIREN = "kolayofis_son_durum"
KAYNAK = "KolayOfis Dosyalar Raporu"

# Rapordaki son durum sütunu bazı çıktılarda BAŞLIKSIZ gelir (17.09 çıktısı): başlık
# adıyla bulunamazsa "Buro Özel Türü" ile "Yerel Mahkeme Karar Durumu" arasındaki
# sütuna düşülür — ikisi de adlıdır, araları tek sütundur.
BASLIK_SISTEM_NO = ("SistemNo", "Sistem No")
BASLIK_SON_DURUM = ("Son Durum", "Dosya Son Durumu")
BASLIK_SOL = ("Buro Özel Türü", "Büro Özel Türü")
BASLIK_SAG = ("Yerel Mahkeme Karar Durumu",)

# Rapordaki yazım → bizdeki tek yazım (anahtar boşluk-normalize edilmiş hâliyle aranır).
YAZIM_DUZELTME: Dict[str, str] = {
    "Delliller Toplanıyor": "Deliller Toplanıyor",
    "Bekletici Mesele/ceza-hukuk Dosyası": "Bekletici Mesele/Ceza-Hukuk Dosyası",
}

# Değer değil, "seçilmedi": yazılmaz (boş hücre zaten `_metin` ile None olur).
YER_TUTUCU_SON_DURUM = frozenset({"lütfen seçiniz", "lutfen seciniz", "seçiniz"})

# Adım 1 — panel listesi (`file_statuses`) düzeltmeleri.
LISTE_YAZIM: Tuple[Tuple[str, str], ...] = (("İstinafta", "İstinafda"),)
LISTE_EKLE: Tuple[str, ...] = ("Kapalı", "Soruşturma")

# Adım 2 — kartlardaki tek seferlik yazım birliği (eski aktarımların bıraktığı hâl).
KART_YAZIM: Tuple[Tuple[str, str], ...] = (
    ("Bekletici Mesele/ceza-hukuk Dosyası", "Bekletici Mesele/Ceza-Hukuk Dosyası"),
)

ADIM_ADLARI = {
    "liste": "Panel listesi",
    "kart_yazim": "Kart yazım birliği",
    "son_durum": "Son durum tazeleme",
}


# ─── Rapor okuma ─────────────────────────────────────────────────────────────

def _sutun_indeksi(basliklar: Sequence[str], adaylar: Sequence[str]) -> Optional[int]:
    anahtarlar = [_baslik_anahtari(b) for b in basliklar]
    for aday in adaylar:
        hedef = _baslik_anahtari(aday)
        for i, anahtar in enumerate(anahtarlar):
            if anahtar == hedef:
                return i
    return None


def _son_durum_indeksi(basliklar: Sequence[str]) -> int:
    dogrudan = _sutun_indeksi(basliklar, BASLIK_SON_DURUM)
    if dogrudan is not None:
        return dogrudan
    sol = _sutun_indeksi(basliklar, BASLIK_SOL)
    sag = _sutun_indeksi(basliklar, BASLIK_SAG)
    if sol is not None and sag is not None and sag - sol == 2:
        logger.warning("Son durum sütunu başlıksız — %s ile %s arasındaki sütun alındı",
                       basliklar[sol], basliklar[sag])
        return sol + 1
    raise ValueError(f"Raporda son durum sütunu bulunamadı — başlıklar: {list(basliklar)}")


def _degeri_normalize(ham) -> Optional[str]:
    """Boşluk-normalize + bilinen yazım düzeltmesi; yer tutucu ve boş hücre None."""
    deger = _metin(ham)
    if deger is None:
        return None
    if deger.casefold() in YER_TUTUCU_SON_DURUM:
        return None
    return YAZIM_DUZELTME.get(deger, deger)


def raporu_oku(yol: Path, sheet: str = "Sheet") -> List[Tuple[str, str]]:
    """(SistemNo, son durum) çiftleri — yazılmayacak satırlar düşürülmüştür."""
    import openpyxl

    wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
    try:
        ws = wb[sheet] if sheet in wb.sheetnames else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        basliklar = [str(h) if h is not None else "" for h in next(it)]
        i_sistem = _sutun_indeksi(basliklar, BASLIK_SISTEM_NO)
        if i_sistem is None:
            raise ValueError(f"Raporda SistemNo sütunu yok — başlıklar: {basliklar}")
        i_durum = _son_durum_indeksi(basliklar)
        satirlar: List[Tuple[str, str]] = []
        for row in it:
            # read_only satırları başlıktan kısa gelebilir (sondaki boş hücreler düşer).
            sistem_no = _metin(row[i_sistem]) if i_sistem < len(row) else None
            deger = _degeri_normalize(row[i_durum]) if i_durum < len(row) else None
            if sistem_no and deger:
                satirlar.append((sistem_no, deger))
        return satirlar
    finally:
        wb.close()


# ─── Ortak yardımcılar ───────────────────────────────────────────────────────

def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _liste_kodu(ad: str, kullanilan: set) -> str:
    """Mevcut satırların kod üslubu tireli (`KESIN-LEHE`); çakışmada sonek."""
    taban = _karar_kodu(ad).replace("_", "-") or "DEGER"
    aday, n = taban, 2
    while aday in kullanilan:
        aday = f"{taban}-{n}"
        n += 1
    return aday


# ─── Adım 1: panel listesi ───────────────────────────────────────────────────

def listeyi_duzelt(db, *, kim: str, sonuc: Sonuc) -> None:
    satirlar = db.query(models.FileStatus).all()
    adlar = {s.name: s for s in satirlar}
    kodlar = {s.code for s in satirlar}
    sira = max((s.sequence or 0) for s in satirlar) + 1 if satirlar else 0

    for eski, yeni in LISTE_YAZIM:
        hedef = f"{eski} → {yeni}"
        if yeni in adlar:
            sonuc.ekle("liste", hedef, "ATLANDI", "doğru yazım zaten listede")
            continue
        satir = adlar.get(eski)
        if satir is None:
            sonuc.ekle("liste", hedef, "ATLANDI", "eski yazım listede yok")
            continue
        satir.name = yeni
        adlar[yeni] = satir
        sonuc.ekle("liste", hedef, "YAPILDI", "liste yazımı kartlardaki hâle çekildi")

    for ad in LISTE_EKLE:
        if ad in adlar:
            sonuc.ekle("liste", ad, "ATLANDI", "listede var")
            continue
        kod = _liste_kodu(ad, kodlar)
        kodlar.add(kod)
        db.add(models.FileStatus(code=kod, name=ad, active=True, sequence=sira))
        sira += 1
        kullanim = db.query(models.Case).filter(
            models.Case.deleted_at.is_(None), models.Case.dosya_son_durumu == ad).count()
        sonuc.ekle("liste", ad, "YAPILDI", f"listeye eklendi ({kullanim} kartta kullanılıyor)")
    db.flush()


# ─── Adım 2: kart yazım birliği ──────────────────────────────────────────────

def kart_yazimini_birle(db, *, kim: str, sonuc: Sonuc) -> None:
    for eski, yeni in KART_YAZIM:
        kartlar = db.query(models.Case).filter(
            models.Case.deleted_at.is_(None), models.Case.dosya_son_durumu == eski).all()
        if not kartlar:
            sonuc.ekle("kart_yazim", f"{eski} → {yeni}", "ATLANDI", "bu yazımda kart yok")
            continue
        for kart in kartlar:
            _tarihce(db, kart.id, "dosya_son_durumu", kart.dosya_son_durumu, yeni, kim,
                     "yazım birliği: listedeki tek yazım")
            kart.dosya_son_durumu = yeni
        sonuc.ekle("kart_yazim", f"{eski} → {yeni}", "YAPILDI", f"{len(kartlar)} kart")
    db.flush()


# ─── Adım 3: son durum tazeleme ──────────────────────────────────────────────

def _foy_kartlari(db, sistem_nolar: Sequence[str]) -> Dict[str, int]:
    """SistemNo → canlı kart id (föyü olmayan ya da kartı silinmiş satır listeye girmez)."""
    eslesme: Dict[str, int] = {}
    parca = 500
    for i in range(0, len(sistem_nolar), parca):
        dilim = sistem_nolar[i:i + parca]
        satirlar = (db.query(models.CaseFoy.sistem_no, models.CaseFoy.case_id)
                    .join(models.Case, models.Case.id == models.CaseFoy.case_id)
                    .filter(models.Case.deleted_at.is_(None), models.CaseFoy.sistem_no.in_(dilim))
                    .all())
        for sistem_no, case_id in satirlar:
            eslesme[sistem_no] = case_id
    return eslesme


def son_durumlari_tazele(db, satirlar: Sequence[Tuple[str, str]], *, kim: str, sonuc: Sonuc) -> None:
    eslesme = _foy_kartlari(db, [s for s, _ in satirlar])
    kart_degerleri: Dict[int, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for sistem_no, deger in satirlar:
        case_id = eslesme.get(sistem_no)
        if case_id is None:
            sonuc.ekle("son_durum", sistem_no, "RET", "föy bizde yok / kartı silinmiş")
            continue
        kart_degerleri[case_id][deger].append(sistem_no)

    for case_id, degerler in kart_degerleri.items():
        kart = db.get(models.Case, case_id)
        hedef = f"#{case_id} {kart.tracking_no if kart is not None else ''}".strip()
        if kart is None or kart.deleted_at is not None:
            sonuc.ekle("son_durum", hedef, "RET", "kart yok/silinmiş")
            continue
        if len(degerler) > 1:
            ayrinti = " | ".join(f"{d} ({', '.join(f)})" for d, f in sorted(degerler.items()))
            sonuc.ekle("son_durum", hedef, "CELISKI", f"föyler farklı: {ayrinti}")
            continue
        yeni = next(iter(degerler))
        if kart.dosya_son_durumu == yeni:
            sonuc.ekle("son_durum", hedef, "ATLANDI", f"zaten {yeni!r}")
            continue
        eski = kart.dosya_son_durumu
        _tarihce(db, case_id, "dosya_son_durumu", eski, yeni, kim,
                 f"KolayOfis raporu ({', '.join(sorted(degerler[yeni]))})")
        kart.dosya_son_durumu = yeni
        sonuc.ekle("son_durum", hedef, "YAPILDI", f"{eski or '(boş)'} → {yeni}")
    db.flush()


# ─── Koşu ────────────────────────────────────────────────────────────────────

def kos(session_factory, *, rapor: Path, apply: bool = False, kim: str = DEGISTIREN) -> Sonuc:
    satirlar = raporu_oku(rapor)
    sonuc = Sonuc()
    db = session_factory()
    try:
        listeyi_duzelt(db, kim=kim, sonuc=sonuc)
        kart_yazimini_birle(db, kim=kim, sonuc=sonuc)
        son_durumlari_tazele(db, satirlar, kim=kim, sonuc=sonuc)
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


def ozet_metni(sonuc: Sonuc, *, apply: bool, ayrinti: bool = False) -> str:
    satirlar = ["=" * 78,
                f"KolayOfis son durum tazeleme — {'UYGULANDI' if apply else 'KURU KOŞU'}",
                "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r, c = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET", "CELISKI"))
        satirlar.append(f"  {ad:22} {y:4} yapıldı · {a:4} atlandı · {r:3} ret · {c:3} çelişki")
    gosterilecek = sonuc.kalemler if ayrinti else [k for k in sonuc.kalemler if k.sonuc == "CELISKI"]
    if gosterilecek:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in gosterilecek)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="KolayOfis raporundan dosya son durumu tazeleme")
    ayristirici.add_argument("--rapor", required=True, type=Path,
                             help="<tarih>_KolayOfis_DosyalarRaporu.xlsx")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    ayristirici.add_argument("--ayrinti", action="store_true", help="bütün kalemleri bas (yalnız çelişki değil)")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, rapor=args.rapor, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply, ayrinti=args.ayrinti))
    return 0


if __name__ == "__main__":
    sys.exit(main())
