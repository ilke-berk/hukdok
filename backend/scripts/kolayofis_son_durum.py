#!/usr/bin/env python3
"""KolayOfis "Dosyalar Raporu" çıktısından dosya son durumlarını tazeler.

Kaynak: veri ekibinin kendi sisteminden (KolayOfis) alınan föy düzeyi çıktı (SistemNo
tekil): 17.09 `<tarih>_KolayOfis_DosyalarRaporu.xlsx` (yalnız Aktif, son durum sütunu
başlıksız) ve 20.09'dan itibaren `MASTER_DOSYA_DURUM_RAPORU_<tarih>.xlsx` (Aktif + Arşiv,
aynı 18 sütun, başlık yazılı). Rapor repoya GİRMEZ, yolu `--rapor` ile verilir.

**Neden var:** son durum ekranlarda ve raporlarda başlık üzerinden aranan alandır
(`cases.dosya_son_durumu`). Teslim paketinin yazdığı değerler ekibin kendi sistemine
göre geride kalıyor; bu script iki kaynağı hizalar. Bir sonraki teslim paketi
"paket kazanır" kuralıyla alanı yeniden yazar — bu koşu o pakete kadar geçerli bir
tazelemedir, kalıcı çözüm paketin güncel gelmesidir.

Adımlar (hepsi tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Liste düzeltmesi** (`file_statuses`): panelin açılır listesi ekibin 22.09'daki
   41 değerlik başlık listesiyle hizalanır — `İstinafda` → `İstinafta` (20.09'daki ters
   yönlü düzeltme GERİ ALINIR: ekip "İstinafda" yazımının kendi hatası olduğunu 22.09'da
   bildirdi, Türkçe ünsüz sertleşmesi; bizde 547 föy düzeltildi), eksik `Soruşturma`,
   `Derdest` ve `İnfaz` eklenir (icra/savcılık sözlüğü). `Kapalı` listeden SİLİNMEZ,
   23.09'dan itibaren PASİFE çekilir (seçilemez; eski kayıt bozulmaz).
2. **Kart yazım birliği:** `Bekletici Mesele/ceza-hukuk Dosyası` → listedeki tek yazım;
   `İstinafda` → `İstinafta` (20.09 koşusunun 114 kartı + paketin 382 kartı, tarihçeli);
   `İnfaz İcradan` → `İnfaz` (23.09, 112 föysüz kart).
3. **Kapalı boşaltma:** kartlardaki `Kapalı` → boş (tarihçeli) — aşağıda.
4. **Son durum tazeleme:** rapordaki föy satırı kartına çözülür, değer normalize edilir
   ve kartın alanı farklıysa tarihçeli yazılır.

Rapordaki yazım kusurları (17.09.2026 çıktısında ölçüldü, 20.09 çıktısında sıfırlandı):

* `Delliller Toplanıyor` (118 satır) — bizdeki doğru yazıma (`Deliller Toplanıyor`) çevrilir.
* `Islah ` (12 satır) — sondaki boşluk kırpılır (`_metin` boşluk-normalize eder).
* `Lütfen Seçiniz` (28) ve boş hücre (118) — YAZILMAZ; dolu kutuyu boşaltmak veri kaybıdır.
* `Kapalı` (219 föy, 20.09 çıktısı) — ekibe göre "Yerel Mahkeme Karar Durumu"
  havuzundan son durum hanesine SIZMIŞ bir değerdir, temizlik kuyruklarında; biz de
  yazmayız (yer tutucu sayılır). Kartta zaten duran `Kapalı` boşaltılmaz.

**Kart değeri kuralı (ekip, 22.09 + 23.09):** `Son Durum` föyün kendi iş akışını
gösterir; bir kartın föyleri farklı değer söylüyorsa kartın değeri öncelik sırasıyla
seçilir (`ONCELIK`, ekibin 23.09 Ek-1 › SEVIYE_SOZLUGU'ndaki 41 değer birebir):

1. **yargı aşaması** (dava seviyesi: İstinafta, Bilirkişide, Bozma Sonrası Yargılama, …);
2. **dava sonucu** (taraf yönünden: Kesin Lehe/Aleyhe, Sulh İle Kapatma, İnfaz, …);
3. **büro ilişkisinin sonu** (İstifa, Azil, Müvekkil Vefatı, Kapama Müvekkil Talimatıyla, İade);
4. **hizmet aşaması** (Lexis Rapor Gönderildi/Hazırlanıyor, Dava Açılması Bekleniyor).

En güçlü kademede tek değer varsa kart onu alır. 2. kademede birden çok sonuç "karışık
sonuç"tur (müvekkil başına farklı): hepsi `AGIRLIK` içindeyse EN AĞIRI alınır (Kesin Aleyhe
> Sulh İle Kapatma > Kesin Lehe — aleyhe kesinleşmiş dava listede gözden kaçmasın), föyler
kendi değerini korur. Aynı kademede başka her çoklu değer (iki yargı aşaması = gerçek
çelişki; iki büro sonu/hizmet aşaması; ağırlık listesi dışı sonuç) ve sözlükte olmayan
değer `CELISKI` döner, karta DOKUNULMAZ.

**Ek katmanı (`--ek`, 23.09):** ekibin çelişki cevabı (Ek-1) master raporundan YENİDİR:
FOYLER › "Bugünkü Son Durum" ve T3_GUNCEL'in "KAPANDI" satırları (föy listesi → değer)
master'ın üzerine yazar; ekte boş/yer tutucu gelen föy master değerini de düşürür. Mailde
yazılı olup ekte olmayan föy değerleri `MAIL_FOY_DEGERLERI`'ndedir.

**`Kapalı` (23.09):** ekip "son durum olarak kullanılmaz, boş sayın" dedi; kartlardaki
`Kapalı` (27.04 ilk içe aktarımından, tarihçesiz ~5.800 kart) tarihçeli BOŞALTILIR ve
panel listesinde pasife çekilir (`LISTE_PASIF`). `İnfaz İcradan` → `İnfaz` (ekip izni).

Ekibin "okuma kuyruğunda" dediği kartlar (`INCELEME_KUYRUGU_FOYLERI`; 23.09'da 16 kartın
15'i kapandı, açık tek kart H-7059/H-7060) föy anahtarıyla tanınır (kart id'si prod ile
lokalde farklı olabilir) ve `BEKLIYOR` ile atlanır; ekip bildirince küme boşaltılır.

    docker compose exec -T backend python scripts/kolayofis_son_durum.py \\
        --rapor /tmp/ek/MASTER_DOSYA_DURUM_RAPORU_2026-09-20.xlsx \\
        --ek /tmp/ek/HUKDOK_CELISKI_CEVABI_2026-09-23.xlsx                   # kuru koşu
    docker compose exec -T backend python scripts/kolayofis_son_durum.py \\
        --rapor … --ek … --apply --kim ilke                                 # yazar

İkinci koşu 0 değişiklik: eşit alan `ATLANDI` döner, liste düzeltmesi idempotenttir.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

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
# `Kapalı` 22.09'dan itibaren: karar durumu havuzundan sızmış değer (ekip), yazılmaz.
YER_TUTUCU_SON_DURUM = frozenset({"lütfen seçiniz", "lutfen seciniz", "seçiniz", "kapalı"})

# Adım 1 — panel listesi (`file_statuses`) düzeltmeleri (ekibin 22.09 listesi, 41 değer).
LISTE_YAZIM: Tuple[Tuple[str, str], ...] = (("İstinafda", "İstinafta"),)
LISTE_EKLE: Tuple[str, ...] = ("Soruşturma", "Derdest", "İnfaz")
# 23.09: son durum değil (ekip §5) — satır silinmez (eski tarihçe okunur kalır), seçilemez.
LISTE_PASIF: Tuple[str, ...] = ("Kapalı",)

# Adım 2 — kartlardaki tek seferlik yazım birliği (eski aktarımların bıraktığı hâl).
KART_YAZIM: Tuple[Tuple[str, str], ...] = (
    ("Bekletici Mesele/ceza-hukuk Dosyası", "Bekletici Mesele/Ceza-Hukuk Dosyası"),
    ("İstinafda", "İstinafta"),
    ("İnfaz İcradan", "İnfaz"),                     # ekip 23.09 §4: düz İnfaz'a çevrilebilir
)

# Adım 3 — kartta boşaltılan değerler (ekip 23.09 §5: "Kapalı'yı son durum olarak boş sayın").
KART_BOSALT: Tuple[str, ...] = ("Kapalı",)

# Kart değeri kademesi (ekip 23.09 Ek-1 › SEVIYE_SOZLUGU, 41 değer): 1 yargı aşaması (dava
# seviyesi) · 2 dava sonucu (taraf yönünden) · 3 büro ilişkisinin sonu · 4 hizmet aşaması.
# Sözlükte olmayan değer SINIFLANMAMIŞTIR; karışan kart çelişkide kalır.
ONCELIK: Dict[str, int] = {
    **dict.fromkeys((
        "Ön İnceleme", "Deliller Toplanıyor", "Tanık", "Bilirkişide", "Bilirkişi Kusur Raporu Alındı",
        "Bilirkişi Maluliyet Raporu Alındı", "Bilirkişi Tazminat Raporu Alındı", "Islah",
        "Sözlü Yargılama", "Karar Yazımı Bekleniyor", "Karar Tebliği Bekleniyor",
        "Karar Kesinleşmesi Bekleniyor", "İstinafta", "Temyizde", "Karar Düzeltmede",
        "Kanun Yararına Bozmada", "Tehiri İcra", "Bozma Sonrası Yargılama",
        "Bekletici Mesele/Ceza-Hukuk Dosyası", "Bekletici Mesele/MSK", "Uyuşmazlık Mahkemesinde",
        "İncelemede", "Birleşme", "Soruşturma", "Davaya Dönüştü", "Derdest",
    ), 1),
    **dict.fromkeys((
        "Kesin Aleyhe", "Sulh İle Kapatma", "Kesin Lehe", "İnfaz", "İnfaz İcradan", "İnfaz Haricen",
        "Aciz Vesikası",
    ), 2),
    **dict.fromkeys(("İstifa", "Azil", "Müvekkil Vefatı", "Kapama Müvekkil Talimatıyla", "İade"), 3),
    **dict.fromkeys(("Lexis Rapor Hazırlanıyor", "Lexis Rapor Gönderildi", "Dava Açılması Bekleniyor"), 4),
}
KADEME_ADLARI = {1: "yargı aşaması", 2: "dava sonucu", 3: "büro ilişkisinin sonu", 4: "hizmet aşaması"}
# Karışık sonuçta kartın göstereceği sıra (en ağır önce) — ekip 23.09 §2.
AGIRLIK: Tuple[str, ...] = ("Kesin Aleyhe", "Sulh İle Kapatma", "Kesin Lehe")

# Ekibin okuma kuyruğu: "kartı şimdilik değiştirmeyin". 23.09 T3_GUNCEL'de 16 kartın 15'i
# kapandı, açık kalan #14186. Föy anahtarı (kart id'si ortamlar arasında farklı olabilir).
INCELEME_KUYRUGU_FOYLERI = frozenset({"H-7059", "H-7060"})

# Mailde yazılı, ekte olmayan föy değerleri (ek katmanıyla aynı öncelikte, master'ı ezer).
MAIL_FOY_DEGERLERI: Dict[str, str] = {
    # 23.09 §1 #5009: iki föyün hanesi bizde boştu; aynı davanın ileri adımı alındı.
    "H-16736": "Bilirkişi Tazminat Raporu Alındı",
    "H-16969": "Bilirkişi Tazminat Raporu Alındı",
}

# Ek-1 sayfa/başlık adları (ekip 23.09 çelişki cevabı).
EK_FOYLER = ("FOYLER", ("SistemNo",), ("Bugünkü Son Durum",))
EK_T3 = ("T3_GUNCEL", ("Föyler",), ("Bugünkü değer",), ("Durum",))

ADIM_ADLARI = {
    "liste": "Panel listesi",
    "kart_yazim": "Kart yazım birliği",
    "kart_bosalt": "Kapalı boşaltma",
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


def _sayfa_satirlari(wb, sayfa: str, *baslik_adaylari: Sequence[str]):
    """Sayfanın satırlarını istenen sütunların değerleri olarak verir (başlık toleranslı)."""
    if sayfa not in wb.sheetnames:
        raise ValueError(f"Ekte {sayfa!r} sayfası yok — sayfalar: {wb.sheetnames}")
    it = wb[sayfa].iter_rows(values_only=True)
    basliklar = [str(h) if h is not None else "" for h in next(it)]
    indeksler = []
    for adaylar in baslik_adaylari:
        i = _sutun_indeksi(basliklar, adaylar)
        if i is None:
            raise ValueError(f"{sayfa}: {adaylar[0]!r} sütunu yok — başlıklar: {basliklar}")
        indeksler.append(i)
    for row in it:
        yield [row[i] if i < len(row) else None for i in indeksler]


def ek_oku(yol: Path) -> Dict[str, Optional[str]]:
    """Ekip çelişki cevabından (Ek-1) föy → bugünkü değer; None = "boş say" (master'ı da düşürür).

    FOYLER › "Bugünkü Son Durum" her satırı; T3_GUNCEL yalnız "KAPANDI" satırları (hücredeki
    föy listesinin hepsi aynı değeri alır). İkisi çelişirse FOYLER kazanır (satır düzeyi).
    """
    import openpyxl

    wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
    try:
        degerler: Dict[str, Optional[str]] = {}
        sayfa, *basliklar = EK_T3
        for foyler, deger, durum in _sayfa_satirlari(wb, sayfa, *basliklar):
            if not str(durum or "").strip().upper().startswith("KAPANDI"):
                continue
            for sistem_no in str(foyler or "").split(","):
                if sistem_no.strip():
                    degerler[sistem_no.strip()] = _degeri_normalize(deger)
        sayfa, *basliklar = EK_FOYLER
        for sistem_no, deger in _sayfa_satirlari(wb, sayfa, *basliklar):
            sistem_no = _metin(sistem_no)
            if sistem_no:
                degerler[sistem_no] = _degeri_normalize(deger)
        return degerler
    finally:
        wb.close()


def satirlari_birlestir(master: Sequence[Tuple[str, str]], ek: Dict[str, Optional[str]]
                        ) -> List[Tuple[str, str]]:
    """Master satırları + ek katmanı (ek kazanır; None düşürür)."""
    birlesik: Dict[str, Optional[str]] = dict(master)
    birlesik.update(ek)
    return [(s, d) for s, d in birlesik.items() if d]


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

    for ad in LISTE_PASIF:
        satir = adlar.get(ad)
        if satir is None or not satir.active:
            sonuc.ekle("liste", f"{ad} (pasif)", "ATLANDI", "listede yok ya da zaten pasif")
            continue
        satir.active = False
        sonuc.ekle("liste", f"{ad} (pasif)", "YAPILDI", "son durum değil (ekip 23.09) — seçilemez")
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


# ─── Adım 3: Kapalı boşaltma ─────────────────────────────────────────────────

def kartlari_bosalt(db, *, kim: str, sonuc: Sonuc) -> None:
    for deger in KART_BOSALT:
        kartlar = db.query(models.Case).filter(
            models.Case.deleted_at.is_(None), models.Case.dosya_son_durumu == deger).all()
        if not kartlar:
            sonuc.ekle("kart_bosalt", deger, "ATLANDI", "bu değerde kart yok")
            continue
        for kart in kartlar:
            _tarihce(db, kart.id, "dosya_son_durumu", kart.dosya_son_durumu, None, kim,
                     f"ekip 23.09 §5: {deger!r} son durum değil, boş sayılır")
            kart.dosya_son_durumu = None
        sonuc.ekle("kart_bosalt", deger, "YAPILDI", f"{len(kartlar)} kart boşaltıldı")
    db.flush()


# ─── Adım 4: son durum tazeleme ──────────────────────────────────────────────

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


def kart_degeri(degerler: Dict[str, List[str]]) -> Tuple[Optional[str], str]:
    """Föy değerlerinden kartın değeri: (değer | None, gerekçe) — ekibin 23.09 kademe kuralı.

    Tek değer → o. Birden çok: en güçlü kademede (`ONCELIK`) tek değer varsa o; 2. kademede
    hepsi `AGIRLIK` içindeyse en ağırı (karışık sonuç); aksi hâlde None (çelişki).
    """
    if len(degerler) == 1:
        return next(iter(degerler)), ""
    sinifsiz = sorted(d for d in degerler if d not in ONCELIK)
    if sinifsiz:
        return None, f"sınıflanmamış değer: {sinifsiz}"
    kademe = min(ONCELIK[d] for d in degerler)
    adaylar = sorted(d for d in degerler if ONCELIK[d] == kademe)
    digerleri = sorted(d for d in degerler if ONCELIK[d] != kademe)
    ad = KADEME_ADLARI[kademe]
    if len(adaylar) == 1:
        return adaylar[0], f"kademe kuralı: {ad} {adaylar[0]!r} baskın, föy {digerleri}"
    if kademe == 2 and all(d in AGIRLIK for d in adaylar):
        agir = min(adaylar, key=AGIRLIK.index)
        return agir, f"kademe kuralı: karışık sonuç {adaylar} → en ağırı {agir!r}"
    return None, f"aynı kademede birden çok değer ({ad}): {adaylar}"


def son_durumlari_tazele(db, satirlar: Sequence[Tuple[str, str]], *, kim: str, sonuc: Sonuc,
                         ek_foyleri: FrozenSet[str] = frozenset()) -> None:
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
        foyler = sorted(f for fs in degerler.values() for f in fs)
        if INCELEME_KUYRUGU_FOYLERI.intersection(foyler):
            sonuc.ekle("son_durum", hedef, "BEKLIYOR", f"ekibin okuma kuyruğunda (23.09): {', '.join(foyler)}")
            continue
        yeni, gerekce = kart_degeri(degerler)
        if yeni is None:
            ayrinti = " | ".join(f"{d} ({', '.join(f)})" for d, f in sorted(degerler.items()))
            sonuc.ekle("son_durum", hedef, "CELISKI", f"{gerekce} — föyler: {ayrinti}")
            continue
        if kart.dosya_son_durumu == yeni:
            sonuc.ekle("son_durum", hedef, "ATLANDI", f"zaten {yeni!r}")
            continue
        eski = kart.dosya_son_durumu
        kaynak = "ekip cevabı 23.09" if ek_foyleri.intersection(foyler) else "KolayOfis raporu"
        kanit = f"{kaynak} ({', '.join(sorted(degerler[yeni]))})" + (f"; {gerekce}" if gerekce else "")
        _tarihce(db, case_id, "dosya_son_durumu", eski, yeni, kim, kanit)
        kart.dosya_son_durumu = yeni
        sonuc.ekle("son_durum", hedef, "YAPILDI", f"{eski or '(boş)'} → {yeni}" + (f" ({gerekce})" if gerekce else ""))
    db.flush()


# ─── Koşu ────────────────────────────────────────────────────────────────────

def kos(session_factory, *, rapor: Path, ek: Optional[Path] = None, apply: bool = False,
        kim: str = DEGISTIREN) -> Sonuc:
    # Mail değerleri o cevabın parçasıdır: yalnız ek verildiğinde katmana girer.
    ek_degerleri: Dict[str, Optional[str]] = {**ek_oku(ek), **MAIL_FOY_DEGERLERI} if ek is not None else {}
    satirlar = satirlari_birlestir(raporu_oku(rapor), ek_degerleri)
    ek_foyleri = frozenset(ek_degerleri)
    sonuc = Sonuc()
    db = session_factory()
    try:
        listeyi_duzelt(db, kim=kim, sonuc=sonuc)
        kart_yazimini_birle(db, kim=kim, sonuc=sonuc)
        kartlari_bosalt(db, kim=kim, sonuc=sonuc)
        son_durumlari_tazele(db, satirlar, kim=kim, sonuc=sonuc, ek_foyleri=ek_foyleri)
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
        y, a, r, c, b = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET", "CELISKI", "BEKLIYOR"))
        satirlar.append(f"  {ad:22} {y:4} yapıldı · {a:4} atlandı · {r:3} ret · {c:3} çelişki · {b:3} bekliyor")
    gosterilecek = sonuc.kalemler if ayrinti else [k for k in sonuc.kalemler if k.sonuc in ("CELISKI", "BEKLIYOR")]
    if gosterilecek:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in gosterilecek)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="KolayOfis raporundan dosya son durumu tazeleme")
    ayristirici.add_argument("--rapor", required=True, type=Path,
                             help="<tarih>_KolayOfis_DosyalarRaporu.xlsx")
    ayristirici.add_argument("--ek", type=Path, default=None,
                             help="ekip çelişki cevabı (HUKDOK_CELISKI_CEVABI_<tarih>.xlsx) — master'ı ezer")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    ayristirici.add_argument("--ayrinti", action="store_true", help="bütün kalemleri bas (yalnız çelişki değil)")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, rapor=args.rapor, ek=args.ek, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply, ayrinti=args.ayrinti))
    return 0


if __name__ == "__main__":
    sys.exit(main())
