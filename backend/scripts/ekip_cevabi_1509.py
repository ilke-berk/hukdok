#!/usr/bin/env python3
"""Veri ekibinin 15.09.2026 cevabındaki (Ek-4) kart düzeltmeleri — tek koşu, yedi adım.

Kaynak: HANYALOĞLU-ACAR master veri ekibi, 15.09 — "13.09 listeniz ve Ek-3
cevaplarınız üzerine" + `HUKDOK_CEVAP_EKI_4_2026-09-15.xlsx` (12 sayfa). Ek repoya
GİRMEZ, yolu `--ek4` ile verilir; prod'da aynı script + aynı xlsx koşar
(`ekip_cevabi_1209.py` deseni).

**Sıra:** bu script 15.09 PAKETİ UYGULANDIKTAN SONRA koşar. Paket, Ek-4'ün işaret
ettiği 17 föyü sisteme sokuyor ve kart bağlarını değiştiriyor.

**Kart numarası:** Ek-4'ün numaraları 13.09'da gönderdiğimiz listeden geliyor, o liste
ise yerel bir kopyadan üretilmişti (16.09 ölçümü: 234 kart tutmuyor). Bu yüzden her
kart önce id ile, bulunamazsa satırdaki FÖY NUMARASI ile çözülür — föy tek güvenilir
anahtar.

Adımlar (hepsi tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Konu düzeltmesi** — `02_RUCU_KARTLARI`: "Önerdiğimiz konu" (hepsi "Rücuen Alacak").
   Değer `case_subjects` listesinde OLMALI; kart zaten o konudaysa ATLANDI.
2. **Sabit künye düzeltmesi** — Ek-2 › 06 (11.09) iki kalemi lokalde uygulanmış ama
   canlı sisteme hiç girmemişti; 3. adımdaki birleştirmenin ön koşulu (esas eşitliği)
   bunlara bağlı.
3. **Aynı dava iki kart** — `03_AYNI_DAVA_IKI_KART`. KALAN = ekibin listesindeki ESKİ
   kart: numarasını master köprüleri tanıyor, klasör listesi onda. Föy + künye yeni
   karttan taşınır (`mukerrer_kart_birlestir.birlestir`; klasör listeleri birleşir —
   ekibin Ek-2 › 06'daki "yanına ekleyin" isteği).
4. **Eski esaslı kart** — `05_ESKI_ESAS_KARTI`: bozma/yeniden yargılamada dosya yeni
   esas aldığında KULLANICI KARARI (16.09) tek karttır. Paket eski esası güncel kartın
   tarihçesine (`ONCEKI`) zaten yazıyor; bu adım eksikse tamamlar, eski kartın
   belgelerini ve kapsam işaretli föy kayıtlarını güncel karta taşır, sonra eski kartı
   kapatır. Eski kartta CANLI föy varsa dokunmaz (RET) — insan kararı.
5. **Ana tür düzeltmesi** — `09_TUR_CELISKISI`: yalnız föy türü kartın Ana Tür'ünden
   farklı olan satırlar. Ofis numarasındaki tür kodu çelişkisi (8 kart) BU ADIMDA
   DEĞİL — ofis numarası değişmez, karar insanındır.
6. **Klasör numarası öneki** — `10_AXA_KLASOR`: AXA föylerinin DosyaNo'suna kök öneki
   eklendi (`21458` → `1.21458.00`); kartın listesindeki öneksiz numara yenisiyle
   DEĞİŞTİRİLİR (sıra korunur). Önerisi soru olan satır atlanır.
7. **İlişkili dosya bağı** — `06_ILISKILI_ONERI` (+ `01_SORULARINIZ` 14321/14322).
   `CaseRelation` TEK YÖNLÜ yazılır (`ILGILI`); DB kısıtı yönlü olduğu için iki yön de
   kontrol edilir, okuyan taraf (kart ekranı) simetrik davranır.

Ek-4 › 12'nin kapatma önerilerinden yalnız `KAPATILACAK_KARTLAR` uygulanır: 14342 canlı
sistemde GERÇEK dosyadır (ekibin bulgusu yerel kopyaya aitti), 5546'nın müvekkil
kontrolü bizde açıktır.

İkinci koşu 0 değişiklik: birleşmiş/kapanmış kart `deleted_at` ile tanınır, eşit alan
atlanır, var olan ilişki atlanır.

    docker compose exec -T backend python scripts/ekip_cevabi_1509.py \\
        --ek4 /app/data/HUKDOK_CEVAP_EKI_4_2026-09-15.xlsx                  # kuru koşu
    docker compose exec -T backend python scripts/ekip_cevabi_1509.py \\
        --ek4 … --apply --kim ilke                                          # yazar
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager
from managers.reference_lists import tr_upper
from scripts import mukerrer_kart_birlestir as mb
from scripts.ekip_cevabi_1209 import Sonuc, _canli_kart, _foy_tasi, _sayfa, _tam_sayi

logger = logging.getLogger("EkipCevabi1509")
DEGISTIREN = "ekip_cevabi_1509"
KAYNAK = "ekip cevabı 15.09.2026 (Ek-4)"
ILISKI_TURU = "ILGILI"

SAYFA_KONU = "02_RUCU_KARTLARI"
SAYFA_CIFT = "03_AYNI_DAVA_IKI_KART"
SAYFA_ESKI_ESAS = "05_ESKI_ESAS_KARTI"
SAYFA_ILISKI = "06_ILISKILI_ONERI"
SAYFA_TUR = "09_TUR_CELISKISI"
SAYFA_KLASOR = "10_AXA_KLASOR"

# Ek-2 › 06 (11.09): lokalde 13.09'da uygulandı, canlı sisteme girmedi. 3. adımdaki
# birleştirme esas eşitliği ister; 4181'in künyesi başka davanın olduğu için şart.
SABIT_DUZELTMELER: Tuple[Tuple[int, str, Optional[str], str], ...] = (
    (4181, "klasor_no_2", "1735.002",
     "Ek-2 › 06: ARB-15159'un numarası; 1735.001.00 dava dosyasının (H-15052, ayrı kart)"),
    (4181, "court", None, "Ek-2 › 06: arabuluculuk kartı — künye başka davanın, mahkeme boşaltılır"),
    (4181, "esas_no", None, "Ek-2 › 06: arabuluculuk kartı — künye başka davanın, esas boşaltılır"),
    (2223, "klasor_no_2", "2.051.00",
     "Ek-2 › 06: 1464.001.00 başka müvekkilin numarası (H-10329); bu kart id-10225'in"),
)
# Ek-4 › 12'den yalnız bu kart kapatılır (deneme kaydı: karşı taraf "Test 2", esas 9/99).
KAPATILACAK_KARTLAR: Tuple[Tuple[int, str], ...] = (
    (14336, "Ek-4 › 12: deneme kaydı (X1.I_KUTLUK…0002.ICRAA, 'Test 2' · 9/99)"),
)
# Ek-4 › 01 soru 1: aynı olayın iki ayrı yargılaması — ayrı kart + ilişki bağı.
SABIT_ILISKILER: Tuple[Tuple[int, int, str], ...] = (
    (14321, 14322, "Ek-4 › 01: aynı olayın iki yargılaması (mahkeme davası + hakem heyeti başvurusu)"),
)

_FOY_NO = re.compile(r"\b(?:H|C|DN|ARB|SSTMN|THKM|id|i)-\d+\b")
_DOSYA_NO = re.compile(r"(\d+(?:\.\d+)+)")


# ─── Ek-4 okuma ──────────────────────────────────────────────────────────────

def _metin(deger) -> str:
    return " ".join(str(deger or "").split())


def _kolonlar(basliklar: Sequence, ad: str) -> List[int]:
    """Aynı başlıktan birden çok olabilir (Ek-4 › 06'da iki 'Föy (bizde)')."""
    hedef = " ".join(ad.split()).casefold()
    return [i for i, b in enumerate(basliklar) if " ".join(str(b or "").split()).casefold() == hedef]


def _kolon(basliklar: Sequence, *adaylar: str) -> int:
    for aday in adaylar:
        bulunan = _kolonlar(basliklar, aday)
        if bulunan:
            return bulunan[0]
    raise ValueError(f"Ek-4 başlığı bulunamadı: {adaylar} — başlıklar: {list(basliklar)}")


def _satirlar(wb, sayfa: str) -> Tuple[Sequence, List[Sequence]]:
    satirlar = list(_sayfa(wb, sayfa).iter_rows(values_only=True))
    return satirlar[0], satirlar[1:]


def _klasor_ciftleri(bizde: str, mevcut: set) -> List[Tuple[str, str]]:
    """'H-15774 1.21458.00' + kartın listesi → [('21458', '1.21458.00')].

    Eşleşme: yeni numaranın ORTA parçası kartın listesinde tek başına varsa.
    """
    ciftler: List[Tuple[str, str]] = []
    for yeni in _DOSYA_NO.findall(bizde):
        parcalar = yeni.split(".")
        if len(parcalar) == 3 and parcalar[1] in mevcut and yeni not in mevcut:
            ciftler.append((parcalar[1], yeni))
    return ciftler


def ek4_oku(yol: Path) -> Dict[str, list]:
    """Ek-4'ün altı sayfasını okur. Kart kimliği: (id, föy hücresi) — id tutmazsa föy."""
    import openpyxl
    wb = openpyxl.load_workbook(yol, data_only=True, read_only=True)
    veri: Dict[str, list] = {"konu": [], "cift": [], "eski_esas": [], "tur": [], "klasor": [], "iliski": []}

    basliklar, satirlar = _satirlar(wb, SAYFA_KONU)
    i_kart, i_konu = _kolon(basliklar, "Kart"), _kolon(basliklar, "Önerdiğimiz konu")
    for s in satirlar:
        kart, konu = _tam_sayi(s[i_kart]), _metin(s[i_konu])
        if kart and konu and konu != "—":
            veri["konu"].append((kart, konu))

    basliklar, satirlar = _satirlar(wb, SAYFA_CIFT)
    i_eski, i_yeni = _kolon(basliklar, "Föysüz kart"), _kolon(basliklar, "Föyün bağlı olduğu kart")
    i_foy = _kolon(basliklar, "Föy (bizde)")
    for s in satirlar:
        eski, yeni = _tam_sayi(s[i_eski]), _tam_sayi(s[i_yeni])
        if eski and yeni:
            veri["cift"].append(((eski, ""), (yeni, _metin(s[i_foy])),
                                 "Ek-4 › 03: aynı dava iki kartta (DosyaNo + mahkeme + esas aynı)"))

    basliklar, satirlar = _satirlar(wb, SAYFA_ESKI_ESAS)
    i_eski, i_guncel = _kolon(basliklar, "Eski esaslı kart"), _kolon(basliklar, "Güncel kart")
    i_foy = _kolon(basliklar, "Föy (bizde)")
    for s in satirlar:
        eski, guncel = _tam_sayi(s[i_eski]), _tam_sayi(s[i_guncel])
        if eski and guncel:
            veri["eski_esas"].append(((guncel, _metin(s[i_foy])), (eski, ""),
                                      "Ek-4 › 05: bozma/yeniden yargılama — eski esas tarihçede"))

    basliklar, satirlar = _satirlar(wb, SAYFA_TUR)
    i_kart, i_bizde = _kolon(basliklar, "Kart"), _kolon(basliklar, "Bizde")
    for s in satirlar:
        kart = _tam_sayi(s[i_kart])
        turler = {p.split(":", 1)[1].strip() for p in _metin(s[i_bizde]).split("·") if ":" in p}
        if kart and len(turler) == 1:
            veri["tur"].append((kart, turler.pop()))

    basliklar, satirlar = _satirlar(wb, SAYFA_KLASOR)
    i_kart = _kolon(basliklar, "Kart")
    i_sizde, i_bizde = _kolon(basliklar, "Klasör listesi (sizde)"), _kolon(basliklar, "Föy · DosyaNo (bizde)")
    for s in satirlar:
        kart = _tam_sayi(s[i_kart])
        if not kart:
            continue
        mevcut = {_metin(p) for p in _metin(s[i_sizde]).split(";") if p.strip()}
        for eski_no, yeni_no in _klasor_ciftleri(_metin(s[i_bizde]), mevcut):
            veri["klasor"].append((kart, eski_no, yeni_no))

    basliklar, satirlar = _satirlar(wb, SAYFA_ILISKI)
    i_a, i_b = _kolon(basliklar, "Kart 1"), _kolon(basliklar, "Kart 2")
    foy_kolonlari = _kolonlar(basliklar, "Föy (bizde)")
    i_fa = foy_kolonlari[0] if foy_kolonlari else None
    i_fb = foy_kolonlari[1] if len(foy_kolonlari) > 1 else None
    for s in satirlar:
        a, b = _tam_sayi(s[i_a]), _tam_sayi(s[i_b])
        if a and b:
            veri["iliski"].append(((a, _metin(s[i_fa]) if i_fa is not None else ""),
                                   (b, _metin(s[i_fb]) if i_fb is not None else ""),
                                   "Ek-4 › 06: aynı klasör numarası, farklı tür"))
    wb.close()
    return veri


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _liste_adi(db, model, ad: str) -> Optional[str]:
    for satir in db.query(model.name).all():
        if tr_upper(satir[0] or "") == tr_upper(ad):
            return satir[0]
    return None


def _karti_coz(db, kimlik: Tuple[Optional[int], str]) -> Tuple[Optional[models.Case], str]:
    """(kart, not) — id tutmazsa satırdaki föy numarasıyla çözer (16.09 kart no ölçümü)."""
    case_id, foy_hucresi = kimlik
    if case_id:
        kart = _canli_kart(db, case_id)
        if kart is not None:
            return kart, ""
    for sistem_no in _FOY_NO.findall(foy_hucresi or ""):
        foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sistem_no).first()
        if foy is None:
            continue
        kart = _canli_kart(db, foy.case_id)
        if kart is not None:
            return kart, f"#{case_id} yok → föy {sistem_no} ile #{kart.id}"
    return None, f"#{case_id} yok, föy ile de çözülemedi"


# ─── Adım 1 ve 5: kart alanı (konu · ana tür) ────────────────────────────────

def alanlari_yaz(db, kalemler: Sequence[Tuple[int, str]], *, kolon: str, model, adim: str,
                 kanit: str, kim: str, sonuc: Sonuc) -> None:
    for case_id, ham in kalemler:
        hedef = f"#{case_id} {kolon}"
        kart = _canli_kart(db, case_id)
        if kart is None:
            sonuc.ekle(adim, hedef, "RET", "kart yok/silinmiş")
            continue
        kanonik = _liste_adi(db, model, ham)
        if kanonik is None:
            sonuc.ekle(adim, hedef, "RET", f"{ham!r} listede yok ({model.__tablename__})")
            continue
        eski = getattr(kart, kolon)
        if tr_upper(eski or "") == tr_upper(kanonik):
            sonuc.ekle(adim, hedef, "ATLANDI", f"zaten {kanonik!r}")
            continue
        setattr(kart, kolon, kanonik)
        _tarihce(db, case_id, kolon, eski, kanonik, kim, kanit)
        case_manager.refresh_missing_required(db, kart)
        sonuc.ekle(adim, hedef, "YAPILDI", f"{eski!r} → {kanonik!r}")


# ─── Adım 2: sabit künye düzeltmeleri ────────────────────────────────────────

def sabit_duzeltmeler(db, kalemler: Sequence[Tuple[int, str, Optional[str], str]], *,
                      kim: str, sonuc: Sonuc) -> None:
    for case_id, kolon, yeni, kanit in kalemler:
        hedef = f"#{case_id} {kolon}"
        kart = _canli_kart(db, case_id)
        if kart is None:
            sonuc.ekle("sabit", hedef, "RET", "kart yok/silinmiş")
            continue
        eski = getattr(kart, kolon)
        if (eski or None) == (yeni or None):
            sonuc.ekle("sabit", hedef, "ATLANDI", f"zaten {yeni!r}")
            continue
        if kolon == "esas_no":
            # Türetilmiş kolon: tek yazma yolu esas tarihçesi (E8), boşaltma dahil.
            case_manager.sync_current_esas(db, kart, yeni, court=kart.court,
                                           source=f"{DEGISTIREN} ({kim})")
        else:
            setattr(kart, kolon, yeni)
        _tarihce(db, case_id, kolon, eski, yeni, kim, kanit)
        case_manager.refresh_missing_required(db, kart)
        sonuc.ekle("sabit", hedef, "YAPILDI", f"{eski!r} → {yeni!r}")


# ─── Adım 3: aynı dava iki kart ──────────────────────────────────────────────

def ciftleri_birlestir(db, ciftler: Sequence[Tuple[Tuple, Tuple, str]], *, kim: str, sonuc: Sonuc) -> None:
    """KALAN = çiftin İLK kartı (ekibin listesindeki eski numara)."""
    for kalan_kimlik, mukerrer_kimlik, _kanit in ciftler:
        kalan, not_a = _karti_coz(db, kalan_kimlik)
        mukerrer, not_b = _karti_coz(db, mukerrer_kimlik)
        hedef = f"#{kalan_kimlik[0]} ↔ #{mukerrer_kimlik[0]}"
        notlar = " · ".join(n for n in (not_a, not_b) if n)
        if kalan is None or mukerrer is None:
            sonuc.ekle("cift", hedef, "ATLANDI", notlar or "kart yok/silinmiş")
            continue
        if kalan.id == mukerrer.id:
            sonuc.ekle("cift", hedef, "ATLANDI", f"tek karta inmiş (#{kalan.id})")
            continue
        with db.begin_nested():
            s = mb.birlestir(db, kalan, mukerrer, kim=kim, muvekkil_ayrimi=True, mahkeme_kontrolu=False,
                             tarihce_alani="ekip_cevabi_1509_birlestirme", sebep_etiketi=KAYNAK)
        if s.ret:
            sonuc.ekle("cift", hedef, "RET", f"{s.ret}{' · ' + notlar if notlar else ''}")
            continue
        sonuc.ekle("cift", hedef, "YAPILDI",
                   f"kalan #{kalan.id} {kalan.tracking_no} ← #{mukerrer.id} ({s.tasinan})"
                   + (f" · {notlar}" if notlar else ""))


# ─── Adım 4: eski esaslı kartı kapat ─────────────────────────────────────────

def eski_esas_kartlari(db, ciftler: Sequence[Tuple[Tuple, Tuple, str]], *, kim: str, sonuc: Sonuc) -> None:
    for guncel_kimlik, eski_kimlik, kanit in ciftler:
        guncel, not_a = _karti_coz(db, guncel_kimlik)
        eski, not_b = _karti_coz(db, eski_kimlik)
        hedef = f"#{eski_kimlik[0]} → #{guncel_kimlik[0]}"
        if guncel is None or eski is None:
            sonuc.ekle("eski_esas", hedef, "ATLANDI", " · ".join(n for n in (not_a, not_b) if n) or "kart yok")
            continue
        if guncel.id == eski.id:
            sonuc.ekle("eski_esas", hedef, "ATLANDI", "tek kart")
            continue
        canli_foy = [f for f in eski.foys if not f.kapsam_durumu]
        if canli_foy:
            sonuc.ekle("eski_esas", hedef, "RET",
                       f"eski kartta {len(canli_foy)} canlı föy var — insan kararı")
            continue
        eklenen = case_manager.add_historical_esas(
            db, guncel, eski.esas_no, court=eski.court, source=f"{DEGISTIREN} ({kim})")
        tasinan = 0
        for belge in list(eski.documents):
            belge.case_id = guncel.id
            belge.case_party_id = None
            tasinan += 1
        for foy in list(eski.foys):                       # kapsam işaretli (tombstone) föyler
            _foy_tasi(db, foy, guncel, kim, kanit)
        db.flush()
        eski.deleted_at = func.now()
        eski.deleted_by = kim
        eski.delete_reason = f"{KAYNAK}: eski esaslı kart, güncel kart #{guncel.id} {guncel.tracking_no}"[:500]
        eski.active = False
        _tarihce(db, eski.id, "kapatma", eski.tracking_no, f"→ #{guncel.id}", kim, kanit)
        _tarihce(db, guncel.id, "eski_esas", eski.esas_no, guncel.esas_no, kim, kanit)
        case_manager.refresh_missing_required(db, guncel)
        sonuc.ekle("eski_esas", hedef, "YAPILDI",
                   f"#{eski.id} kapandı (esas {eski.esas_no}"
                   + (" tarihçeye eklendi" if eklenen is not None else " tarihçede zaten vardı")
                   + (f", {tasinan} belge taşındı" if tasinan else "") + ")")


# ─── Adım 6: klasör numarası öneki ───────────────────────────────────────────

def klasorleri_duzelt(db, kalemler: Sequence[Tuple[int, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for case_id, eski_no, yeni_no in kalemler:
        hedef = f"#{case_id} {eski_no} → {yeni_no}"
        kart = _canli_kart(db, case_id)
        if kart is None:
            sonuc.ekle("klasor", hedef, "RET", "kart yok/silinmiş")
            continue
        parcalar = [_metin(p) for p in (kart.klasor_no_2 or "").split(";") if p.strip()]
        if yeni_no in parcalar:
            sonuc.ekle("klasor", hedef, "ATLANDI", "yeni numara zaten listede")
            continue
        if eski_no not in parcalar:
            sonuc.ekle("klasor", hedef, "RET", f"{eski_no!r} kartın listesinde yok: {parcalar}")
            continue
        eski_liste = kart.klasor_no_2
        kart.klasor_no_2 = ";".join(yeni_no if p == eski_no else p for p in parcalar)
        _tarihce(db, case_id, "klasor_no_2", eski_liste, kart.klasor_no_2, kim,
                 "Ek-4 › 10: AXA föy numarasına kök öneki eklendi")
        sonuc.ekle("klasor", hedef, "YAPILDI", f"{eski_liste!r} → {kart.klasor_no_2!r}")


# ─── Adım 7: ilişkili dosya bağı ─────────────────────────────────────────────

def _iliski_var(db, a_id: int, b_id: int) -> bool:
    return db.query(models.CaseRelation).filter(
        ((models.CaseRelation.source_case_id == a_id) & (models.CaseRelation.target_case_id == b_id))
        | ((models.CaseRelation.source_case_id == b_id) & (models.CaseRelation.target_case_id == a_id))
    ).first() is not None


def iliskileri_kur(db, ciftler: Sequence[Tuple[Tuple, Tuple, str]], *, kim: str, sonuc: Sonuc) -> None:
    for a_kimlik, b_kimlik, kanit in ciftler:
        a, not_a = _karti_coz(db, a_kimlik)
        b, not_b = _karti_coz(db, b_kimlik)
        hedef = f"#{a_kimlik[0]} ↔ #{b_kimlik[0]}"
        notlar = " · ".join(n for n in (not_a, not_b) if n)
        if a is None or b is None:
            sonuc.ekle("iliski", hedef, "ATLANDI", notlar or "kart yok/silinmiş")
            continue
        if a.id == b.id:
            sonuc.ekle("iliski", hedef, "ATLANDI", "tek karta inmiş")
            continue
        if _iliski_var(db, a.id, b.id):
            sonuc.ekle("iliski", hedef, "ATLANDI", "bağ zaten var")
            continue
        db.add(models.CaseRelation(source_case_id=a.id, target_case_id=b.id,
                                   relation_type=ILISKI_TURU, created_by=DEGISTIREN, note=kanit[:500]))
        db.flush()
        sonuc.ekle("iliski", hedef, "YAPILDI",
                   f"{a.tracking_no} ↔ {b.tracking_no}" + (f" · {notlar}" if notlar else ""))


# ─── Adım 8: kart kapatma ────────────────────────────────────────────────────

def kartlari_kapat(db, kapatmalar: Sequence[Tuple[int, str]], *, kim: str, sonuc: Sonuc) -> None:
    for case_id, sebep in kapatmalar:
        hedef = f"#{case_id}"
        kart = db.get(models.Case, case_id)
        if kart is None:
            sonuc.ekle("kapatma", hedef, "RET", "kart yok")
            continue
        if kart.deleted_at is not None:
            sonuc.ekle("kapatma", hedef, "ATLANDI", f"zaten kapalı ({kart.delete_reason!r})")
            continue
        if kart.foys:
            sonuc.ekle("kapatma", hedef, "RET", f"kartta {len(kart.foys)} föy var — kapatılmaz")
            continue
        kart.deleted_at = func.now()
        kart.deleted_by = kim
        kart.delete_reason = f"{KAYNAK}: {sebep}"[:500]
        kart.active = False
        _tarihce(db, case_id, "kapatma", kart.tracking_no, None, kim, sebep)
        db.flush()
        sonuc.ekle("kapatma", hedef, "YAPILDI", kart.tracking_no)


# ─── Koşu ────────────────────────────────────────────────────────────────────

ADIM_ADLARI = {
    "konu": "1. Konu (Rücuen Alacak)", "sabit": "2. Sabit künye düzeltmesi",
    "cift": "3. Aynı dava iki kart", "eski_esas": "4. Eski esaslı kart",
    "tur": "5. Ana tür", "klasor": "6. Klasör numarası",
    "iliski": "7. İlişkili dosya", "kapatma": "8. Kart kapatma",
}


def kos(session_factory, *, ek4: Path, apply: bool = False, kim: str = DEGISTIREN) -> Sonuc:
    veri = ek4_oku(ek4)
    sonuc = Sonuc()
    db = session_factory()
    try:
        alanlari_yaz(db, veri["konu"], kolon="subject", model=models.CaseSubject, adim="konu",
                     kanit="Ek-4 › 02: 'Rücu' kartlarının konusu", kim=kim, sonuc=sonuc)
        sabit_duzeltmeler(db, SABIT_DUZELTMELER, kim=kim, sonuc=sonuc)
        ciftleri_birlestir(db, veri["cift"], kim=kim, sonuc=sonuc)
        eski_esas_kartlari(db, veri["eski_esas"], kim=kim, sonuc=sonuc)
        alanlari_yaz(db, veri["tur"], kolon="file_type", model=models.FileType, adim="tur",
                     kanit="Ek-4 › 09: föyün türü kartın Ana Tür'ünden farklı", kim=kim, sonuc=sonuc)
        klasorleri_duzelt(db, veri["klasor"], kim=kim, sonuc=sonuc)
        iliskileri_kur(db, [((a, ""), (b, ""), k) for a, b, k in SABIT_ILISKILER] + veri["iliski"],
                       kim=kim, sonuc=sonuc)
        kartlari_kapat(db, KAPATILACAK_KARTLAR, kim=kim, sonuc=sonuc)
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


def ozet_metni(sonuc: Sonuc, *, apply: bool) -> str:
    satirlar = ["=" * 78,
                f"Ek-4 (15.09.2026) kart düzeltmeleri — {'UYGULANDI' if apply else 'KURU KOŞU'}",
                "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET"))
        satirlar.append(f"  {ad:26} {y:4} yapıldı · {a:4} atlandı · {r:3} ret")
    sorunlu = [k for k in sonuc.kalemler if k.sonuc == "RET"]
    if sorunlu:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  RET  [{k.adim}] {k.hedef}: {k.aciklama}" for k in sorunlu)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ek-4 (15.09.2026) kart düzeltmeleri")
    ayristirici.add_argument("--ek4", required=True, type=Path, help="HUKDOK_CEVAP_EKI_4_2026-09-15.xlsx")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, ek4=args.ek4, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
