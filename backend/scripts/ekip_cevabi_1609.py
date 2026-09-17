#!/usr/bin/env python3
"""Veri ekibinin 16.09.2026 cevabındaki (Ek-5) kart düzeltmeleri — tek koşu, dokuz adım.

Kaynak: HANYALOĞLU-ACAR master veri ekibi, 16.09 — "16.09 tarihli cevabınızı, düzeltme
dosyanızı ve son hâl listenizi aldık" + `HUKDOK_CEVAP_EKI_5_2026-09-16.xlsx` (10 sayfa).
Ek repoya GİRMEZ, yolu `--ek5` ile verilir; prod'da aynı script + aynı xlsx koşar
(`ekip_cevabi_1509.py` deseni).

**Kart numaraları:** Ek-5'in bütün numaraları 16.09'da PROD'dan ürettiğimiz listeden
gelir — ölçüldü (17.09, lokal = 16.09 prod kopyası). Föy dönüşü yine de föy numarasıyla
çözülür: föyün BUGÜN hangi kartta olduğu DB'den okunur, listeden değil.

**Neden var:** 13.09'da ekibe "uyguladık" dediğimiz düzenlemeler (G179 föy taşıma ve
kapatmalar, G180 ayırma) yalnız lokal DB'de koşmuştu; 16.09'da lokal prod dump'ıyla
yenilenince kayboldu ve prod'a hiç girmedi (Ek-5 › 09, 74 kart). G179'un sabit tabloları
lokal kart id'leri taşıdığı için (14362-14364 SMOKE kartları prod'da GERÇEK dosyalar)
o script prod'da yeniden KOŞULMAZ; bu script aynı kararları prod id'leriyle uygular.

Adımlar (hepsi tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Kart 14393 onarımı** (›10): 15.09 paketi (16.09 prod) Dosya No köprüsüyle H-5441'i
   uygulamada 24.07'de açılmış Kayseri kartına bağlayıp künyesini ezdi (kök neden
   `hukdok_aktarim._tek_aday_kunye_celiskisi` ile kapandı). Paketin o karta yazdığı
   tarihçe satırlarının `old_value`'ları geri yazılır, eklediği taraflar/avukatlar
   silinir, esas 2026/371'e döner (2015/1367 esas satırı silinir — başka davanın),
   H-5441 föyü 13002'ye (H-5440 ile aynı dava) taşınır. Klasördeki `2.554.00` KALIR.
2. **Klasör** (›10): 3946/2850/1763/3021'den ekibin uydurduğu `2.55x.00` çıkar,
   MİCRO numarası `27.00x.00` kalır.
3. **Föy dönüşü** (›09 "Düzenleme", 40): föy 13.09'da ekibin gördüğü karta döner.
   Kaynak kartın BÜTÜN föyleri aynı hedefe gidiyorsa kartlar birleşir
   (`mukerrer_kart_birlestir.birlestir`, KALAN = hedef — belgeler/taraflar/klasör
   taşınır); ön koşul reddederse ya da föyler farklı kartlara gidiyorsa yalnız föy
   taşınır, föysüz VE belgesiz kalan kaynak kart kapanır.
4. **Mükerrer kartlar** (›04 10 çift, ›05 15 yeni kart, ›03-A Yozgat): KALAN = ekibin
   "kalması önerilen"i / föylü kart. İstisnalar `CIFT_ISTISNALARI`'nda (5295↔5567 kalan
   5567 — kullanıcı kararı 17.09; Yozgat ve 5567 esas kontrolsüz). Ön koşul reddederse
   RET raporda kalır, zorlanmaz. ›05'te 5 çiftte müvekkil kümesi elle giriş hatasıyla
   farklı → müvekkil kontrolü kapalı; kalan karta taşınan "avukat adı müvekkil" tarafı
   silinir. 13397↔14408 gerçekten ayrı sigorta → birleşmez, bağ kurulur.
5. **Kapatma** (›09 "Kapatma", ›07, 4356): HK kopyalarında belgeler G179'un gösterdiği
   gerçek karta taşınır; föylü kart kapatılmaz (RET). Birleşme adımındaki kartlar
   burada ATLANIR.
6. **Ayırma** (›09 "Ayırma" 23 + ›08 arabuluculuk/dava 26 kart):
   `birlesik_kart_ayir.karti_ayir` (13.09 kart modeli: arabuluculuk ile dava ayrı kart
   + ilişki bağı). Tek grup kalan kart ATLANDI; 4370 bu turda ayrılmaz (`AYIRMA_ATLA`).
7. **Karar künyesi** (›01): güncel turun (kartın esası) karar alanları boş olmalı;
   son YEREL satırı eski turun esasını taşımıyorsa (13478: 2025/69 + karar 2023/386)
   satırın esası eski tura düzeltilir ve güncel tur için kararsız satır eklenir —
   tek yazma yolu `managers/stage_decisions.py`, slot fotoğrafı oradan tazelenir.
   Güncel turda karar yokken `karar_durumu` duruyorsa boşaltılır. i-12288: dokunulmaz.
8. **Dosya son durumu** (›02): esası yeni tura geçmiş kartta "İstinafda" → "Derdest".
9. **İlişkili dosya bağı** (›05 13397↔14408 ayrı müvekkil kartları, ›03-B arabuluculuk+dava, ›03-C danışmanlık+dava — kullanıcı
   kararı 17.09: ayrı kart + bağ, ›03-A Bursa 2025/1542 — üç ayrı müvekkil, birleşmez).

İkinci koşu 0 değişiklik: birleşmiş/kapanmış kart `deleted_at` ile tanınır, föyü
hedefteki satır atlanır, eşit alan/var olan bağ atlanır.

    docker compose exec -T backend python scripts/ekip_cevabi_1609.py \\
        --ek5 /app/data/HUKDOK_CEVAP_EKI_5_2026-09-16.xlsx                  # kuru koşu
    docker compose exec -T backend python scripts/ekip_cevabi_1609.py \\
        --ek5 … --apply --kim ilke                                          # yazar
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager, stage_decisions
from scripts import birlesik_kart_ayir as bka
from scripts import mukerrer_kart_birlestir as mb
from scripts.ekip_cevabi_1209 import SABIT_KAPATMALAR as G179_KAPATMALAR
from scripts.ekip_cevabi_1209 import Sonuc, _canli_kart, _client_taraf, _sayfa, _tam_sayi

logger = logging.getLogger("EkipCevabi1609")
DEGISTIREN = "ekip_cevabi_1609"
KAYNAK = "ekip cevabı 16.09.2026 (Ek-5)"
ILISKI_TURU = "ILGILI"

SAYFA_KUNYE = "01_KARAR_KUNYESI_11"
SAYFA_SON_DURUM = "02_SON_DURUM_CELISKISI"
SAYFA_AYNI_DAVA = "03_AYNI_DAVA_COK_KART"
SAYFA_MUKERRER = "04_MUKERRER_KART"
SAYFA_YENI_KART = "05_YENI_KART_CAKISMASI"
SAYFA_DENEME = "07_DENEME_GORUNUMLU"
SAYFA_ACIK = "08_ACIK_KALANLAR"
SAYFA_1309 = "09_1309_KARARLARI_CANLIDA_YOK"

# ─── Sabit tablolar (kaynak: Ek-5 › 10 + ölçüm 17.09) ────────────────────────
KART_14393 = 14393
KART_14393_FOY = ("H-5441", 13002)          # föy → H-5440 ile aynı dava
KART_14393_PAKET = "HUKDOK_TESLIM_HUKDOK_TESLIM_PAKETI_2026-09-15"
KART_14393_YABANCI_ESAS = "2015/1367"       # H-5441'in esası — 14393'ün esas tarihçesinden çıkar

# (kart, çıkarılacak parça, kalan MİCRO parçası)
KLASOR_CIKAR: Tuple[Tuple[int, str, str], ...] = (
    (3946, "2.555.00", "27.002.00"),
    (2850, "2.556.00", "27.003.00"),
    (1763, "2.557.00", "27.004.00"),
    (3021, "2.558.00", "27.005.00"),
)

# (kalan, mükerrer) → birleştirme seçenekleri. Anahtar ekibin önerdiği yön DEĞİL,
# uygulanacak yön; ekibin çifti ters yazdıysa `_ciftleri_oku` iki yönü de tanır.
CIFT_ISTISNALARI: Dict[Tuple[int, int], Dict[str, bool]] = {
    # ›04: güncel bilgi 5567'de (mahkeme İstanbul, esasında yeni tur) — kullanıcı kararı 17.09
    (5567, 5295): {"mahkeme_kontrolu": False, "esas_kontrolu": False},
    # ›03-A Yozgat İdare 2019/83: hekim + Ak kartı; 2668 yeni turun esasını da taşıyor
    (2668, 2669): {"muvekkil_ayrimi": True, "esas_kontrolu": False},
    # ›05: uygulamada açılan kartın müvekkil kümesi elle giriş hatasıyla farklı (avukat adı
    # müvekkil yazılmış, "Dr" eki, sigorta eksik) — esas + mahkeme aynı; kullanıcı kararı 17.09
    (13161, 14395): {"muvekkil_ayrimi": True},
    (14579, 14412): {"muvekkil_ayrimi": True},
    (3964, 14345): {"muvekkil_ayrimi": True},
    (14601, 14371): {"muvekkil_ayrimi": True},
    (14608, 14387): {"muvekkil_ayrimi": True},
}
# ›05: gerçekten farklı sigorta (Axa + hekim ↔ Türk Nippon) — müvekkil kartı ayrı kalır,
# birleşmez, ilişki bağı kurulur (kullanıcı kararı 17.09).
CIFT_YERINE_ILISKI: Tuple[Tuple[int, int, str], ...] = (
    (13397, 14408, "›05: Kocaeli 2. İdare 2022/1034 — Axa ve Türk Nippon ayrı müvekkil kartları"),
)
# Birleşmede kalan karta taşınan ama müvekkil OLMAYAN adlar (büronun avukatı müvekkil
# kutusuna yazılmış) — belge/föy bağı yoksa silinir.
MUVEKKIL_OLMAYAN_ADLAR = ("Ayşe Gül Hanyaloğlu",)
# ›08 listesindeki 4370: ARB-16909'un Müvekkil Tipi boş → ofis no S0.CEMAL üretiliyor;
# 13.09 ayırmasında yoktu — bu turda ayrılmaz (kullanıcı kararı 17.09).
AYIRMA_ATLA = {4370: "ARB-16909 Müvekkil Tipi boş (ofis no S0.CEMAL üretiliyor) — ekipten bekleniyor"}
YOZGAT = (2668, 2669)
SON_DURUM_ESKI, SON_DURUM_YENI = "İstinafda", "Derdest"
KUNYE_ATLA = {"i-12288"}                    # ›01: ekip talimatı geri çekti

_FOY_NO = re.compile(r"\b(?:H|C|DN|ARB|SSTMN|SVC|THKM|id|i)-\d+\b")
_KART_PARANTEZ = re.compile(r"kart (\d+) \(")
_TARAF = re.compile(r"^(.*) \(([^()]*)\)$")
_ILK_TUR = re.compile(r"esas (\S+) · karar (\S+)")


# ─── Ek-5 okuma ──────────────────────────────────────────────────────────────

def _metin(deger) -> str:
    return " ".join(str(deger or "").split())


def _satirlar(wb, sayfa: str) -> Tuple[List[str], List[Sequence]]:
    satirlar = list(_sayfa(wb, sayfa).iter_rows(values_only=True))
    return [_metin(b) for b in satirlar[0]], [s for s in satirlar[1:] if any(c is not None for c in s)]


def _kolon(basliklar: Sequence[str], ad: str) -> int:
    hedef = _metin(ad).casefold()
    for i, b in enumerate(basliklar):
        if b.casefold() == hedef:
            return i
    raise ValueError(f"Ek-5 başlığı bulunamadı: {ad!r} — başlıklar: {list(basliklar)}")


def ek5_oku(yol: Path) -> Dict[str, list]:
    import openpyxl
    wb = openpyxl.load_workbook(yol, data_only=True, read_only=True)
    veri: Dict[str, list] = {k: [] for k in (
        "foy_donus", "kapatma", "ayirma", "cift", "kunye", "son_durum", "iliski")}

    b, satirlar = _satirlar(wb, SAYFA_1309)
    i_sinif, i_kart, i_1309 = _kolon(b, "Sınıf"), _kolon(b, "Kart"), _kolon(b, "13.09 listenizde")
    for s in satirlar:
        sinif, kart = _metin(s[i_sinif]), _tam_sayi(s[i_kart])
        if not kart:
            continue
        if sinif.startswith("Düzenleme"):
            foyler = _FOY_NO.findall(_metin(s[i_1309]))
            if foyler:
                veri["foy_donus"].append((foyler[0], kart))
        elif sinif.startswith("Kapatma"):
            veri["kapatma"].append((kart, "›09: 13.09'da kapatıldığı bildirildi"))
        elif sinif.startswith("Ayırma"):
            veri["ayirma"].append(kart)
        elif sinif.startswith("Bilgi"):
            veri["kapatma"].append((kart, "›09: föysüz kaldı, dava föyleri başka kartta toplandı"))

    b, satirlar = _satirlar(wb, SAYFA_ACIK)
    i_konu, i_bizde = _kolon(b, "Konu"), _kolon(b, "Bizdeki karşılığı")
    for s in satirlar:
        if _metin(s[i_konu]).startswith("Arabuluculuk föyü ile dava föyü"):
            for kart in _KART_PARANTEZ.findall(_metin(s[i_bizde])):
                if int(kart) not in veri["ayirma"]:
                    veri["ayirma"].append(int(kart))

    b, satirlar = _satirlar(wb, SAYFA_DENEME)
    i_kart = _kolon(b, "Kart")
    for s in satirlar:
        kart = _tam_sayi(s[i_kart])
        if kart and all(k != kart for k, _ in veri["kapatma"]):
            veri["kapatma"].append((kart, "›07: deneme kaydı (karşı taraf 'Test', esas 8/8 · 9/9)"))

    b, satirlar = _satirlar(wb, SAYFA_MUKERRER)
    i_kalan, i_muk = _kolon(b, "Kalması önerilen kart"), _kolon(b, "Mükerrer kart")
    for s in satirlar:
        kalan, muk = _tam_sayi(s[i_kalan]), _tam_sayi(s[i_muk])
        if kalan and muk:
            veri["cift"].append((kalan, muk, "›04: föysüz mükerrer kart"))

    b, satirlar = _satirlar(wb, SAYFA_YENI_KART)
    i_yeni, i_foylu = _kolon(b, "Yeni kart"), _kolon(b, "Bizde föyü olan kart")
    for s in satirlar:
        yeni, foylu = _tam_sayi(s[i_yeni]), _tam_sayi(s[i_foylu])
        if yeni and foylu:
            veri["cift"].append((foylu, yeni, "›05: 25.05 sonrası açılan kart, föylü davanın ikinci kartı"))

    b, satirlar = _satirlar(wb, SAYFA_AYNI_DAVA)
    i_sinif = _kolon(b, "Sınıf")
    i_esas, i_kart = _kolon(b, "Esas"), _kolon(b, "Kart")
    gruplar: Dict[Tuple[str, str], List[int]] = {}
    for s in satirlar:
        kart = _tam_sayi(s[i_kart])
        if not kart:
            continue
        sinif = _metin(s[i_sinif])[:1]
        esas = _metin(s[i_esas]).split(";")[-1]            # "2026/646;2019/83" → dava anahtarı 2019/83
        gruplar.setdefault((sinif, esas), []).append(kart)
    for (sinif, esas), kartlar in gruplar.items():
        if sinif == "A" and set(kartlar) == set(YOZGAT):
            veri["cift"].append((*YOZGAT, "›03-A: Yozgat İdare 2019/83 iki kart"))
        elif sinif in ("A", "B", "C") and len(kartlar) > 1:
            etiket = {"A": "aynı dava, ayrı müvekkil kartları", "B": "arabuluculuk + dava",
                      "C": "danışmanlık + dava"}[sinif]
            for diger in kartlar[1:]:
                veri["iliski"].append((kartlar[0], diger, f"›03-{sinif}: {etiket} ({esas})"))

    b, satirlar = _satirlar(wb, SAYFA_KUNYE)
    i_foy, i_kart, i_zincir = (_kolon(b, "Föy (SistemNo)"), _kolon(b, "Kart"),
                               _kolon(b, "Doğru yeri (bizdeki aşama zinciri)"))
    for s in satirlar:
        foy, kart = _metin(s[i_foy]), _tam_sayi(s[i_kart])
        eslesme = _ILK_TUR.search(_metin(s[i_zincir]).split("→")[0])
        if kart and foy not in KUNYE_ATLA and eslesme:
            veri["kunye"].append((kart, foy, eslesme.group(1), eslesme.group(2)))

    b, satirlar = _satirlar(wb, SAYFA_SON_DURUM)
    i_kart = _kolon(b, "Kart")
    for s in satirlar:
        kart = _tam_sayi(s[i_kart])
        if kart:
            veri["son_durum"].append(kart)
    wb.close()
    return veri


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _foy_tasi(db, foy: models.CaseFoy, hedef: models.Case, kim: str, kanit: str) -> None:
    """Föyü hedef karta geçirir; taraf bağı hedefte aynı adlı CLIENT'a, yoksa sıfır
    (`ekip_cevabi_1209._foy_tasi` ile aynı; tarihçe imzası bu cevabın)."""
    eski_id = foy.case_id
    yeni_taraf: Optional[int] = None
    if foy.case_party_id:
        eski_taraf = db.get(models.CaseParty, foy.case_party_id)
        if eski_taraf is not None and eski_taraf.name:
            hedef_taraf = _client_taraf(db, hedef.id, eski_taraf.name)
            yeni_taraf = hedef_taraf.id if hedef_taraf is not None else None
    foy.case_id = hedef.id
    foy.case_party_id = yeni_taraf
    db.flush()
    _tarihce(db, eski_id, "foy_tasima", foy.sistem_no, f"→ #{hedef.id} {hedef.tracking_no}", kim, kanit)
    _tarihce(db, hedef.id, "foy_tasima", f"#{eski_id}", foy.sistem_no, kim, kanit)
    eski = db.get(models.Case, eski_id)
    if eski is not None:
        case_manager.refresh_missing_required(db, eski)
    case_manager.refresh_missing_required(db, hedef)


def _kapat(db, kart: models.Case, sebep: str, kim: str) -> None:
    kart.deleted_at = func.now()
    kart.deleted_by = kim
    kart.delete_reason = f"{KAYNAK}: {sebep}"[:500]
    kart.active = False
    _tarihce(db, kart.id, "kapatma", kart.tracking_no, None, kim, sebep)
    db.flush()


def _foy_sayisi(db, case_id: int) -> int:
    return db.query(models.CaseFoy).filter(models.CaseFoy.case_id == case_id).count()


def _kolon_degeri(kolon: str, ham: Optional[str]):
    """Tarihçedeki metni kart kolonunun Python tipine çevirir."""
    if ham is None or ham == "":
        return None
    tip = models.Case.__table__.c[kolon].type
    try:
        python_tipi = tip.python_type
    except NotImplementedError:
        return ham
    if python_tipi is date:
        return date.fromisoformat(ham[:10])
    if python_tipi is Decimal:
        return Decimal(ham)
    if python_tipi is int:
        return int(ham)
    return ham


# ─── Adım 1: kart 14393 ──────────────────────────────────────────────────────

def kart_14393_onar(db, *, kim: str, sonuc: Sonuc) -> None:
    kanit = "›10: 15.09 paketi köprüyle H-5441'i bu karta bağlayıp künyeyi ezdi — 24.07 hâline dönüş"
    kart = _canli_kart(db, KART_14393)
    if kart is None:
        sonuc.ekle("k14393", f"#{KART_14393}", "RET", "kart yok/silinmiş")
        return
    satirlar = (db.query(models.CaseHistory)
                .filter(models.CaseHistory.case_id == KART_14393,
                        models.CaseHistory.source.startswith(KART_14393_PAKET, autoescape=True))
                .order_by(models.CaseHistory.id).all())
    if not satirlar:
        sonuc.ekle("k14393", f"#{KART_14393}", "RET", "paketin tarihçe satırı bulunamadı")
        return
    kolonlar = set(models.Case.__table__.c.keys())
    degisen: List[str] = []

    # Föy önce: taraf bağı (case_party_id) paketin eklediği tarafı gösteriyor.
    sistem_no, hedef_id = KART_14393_FOY
    foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sistem_no).one_or_none()
    hedef = _canli_kart(db, hedef_id)
    if foy is not None and hedef is not None and foy.case_id == KART_14393:
        _foy_tasi(db, foy, hedef, kim, kanit)
        degisen.append(f"{sistem_no} → #{hedef_id}")

    # Başka davanın esas satırı önce silinir (güncel olsa bile) — sonra esas geri yazılır.
    for e in db.query(models.CaseEsasNumber).filter(
            models.CaseEsasNumber.case_id == KART_14393,
            models.CaseEsasNumber.esas_no == KART_14393_YABANCI_ESAS).all():
        db.delete(e)
        degisen.append(f"esas satırı -{e.esas_no}")
    db.flush()

    for satir in satirlar:
        alan = satir.field_name
        if alan == "esas_no":
            eski = satir.old_value or None
            if kart.esas_no != eski:
                court = next((s.old_value for s in satirlar if s.field_name == "court"), kart.court)
                case_manager.sync_current_esas(db, kart, eski, court=court, source=f"{DEGISTIREN} ({kim})")
                _tarihce(db, kart.id, alan, satir.new_value, eski, kim, kanit)
                degisen.append(f"esas {satir.new_value}→{eski}")
        elif alan in kolonlar:
            eski = _kolon_degeri(alan, satir.old_value)
            if getattr(kart, alan) != eski:
                _tarihce(db, kart.id, alan, getattr(kart, alan), eski, kim, kanit)
                setattr(kart, alan, eski)
                degisen.append(alan)
        elif alan == "taraf" and satir.new_value:
            eslesme = _TARAF.match(satir.new_value)
            if not eslesme:
                continue
            for taraf in [p for p in kart.parties
                          if p.name == eslesme.group(1) and (p.role or "") == eslesme.group(2)]:
                bagli = db.query(models.CaseDocument).filter(
                    models.CaseDocument.case_party_id == taraf.id).count()
                bagli += db.query(models.CaseFoy).filter(models.CaseFoy.case_party_id == taraf.id).count()
                if bagli:
                    sonuc.ekle("k14393", f"#{KART_14393} taraf {taraf.name}", "RET",
                               f"{bagli} belge/föy bu tarafa bağlı — silinmedi")
                    continue
                kart.parties.remove(taraf)
                _tarihce(db, kart.id, "taraf", satir.new_value, None, kim, kanit)
                degisen.append(f"taraf -{taraf.name}")
        elif alan == "avukat" and satir.new_value:
            for avukat in [a for a in kart.lawyers if a.name == satir.new_value]:
                kart.lawyers.remove(avukat)
                _tarihce(db, kart.id, "avukat", satir.new_value, None, kim, kanit)
                degisen.append(f"avukat -{avukat.name}")
    db.flush()

    case_manager.refresh_missing_required(db, kart)
    if degisen:
        sonuc.ekle("k14393", f"#{KART_14393}", "YAPILDI", ", ".join(degisen))
    else:
        sonuc.ekle("k14393", f"#{KART_14393}", "ATLANDI", "zaten 24.07 hâlinde")


# ─── Adım 2: klasör ──────────────────────────────────────────────────────────

def klasorleri_temizle(db, kalemler: Sequence[Tuple[int, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for case_id, cikar, kalan_parca in kalemler:
        hedef = f"#{case_id} -{cikar}"
        kart = _canli_kart(db, case_id)
        if kart is None:
            sonuc.ekle("klasor", hedef, "RET", "kart yok/silinmiş")
            continue
        parcalar = [_metin(p) for p in (kart.klasor_no_2 or "").split(";") if p.strip()]
        if cikar not in parcalar:
            sonuc.ekle("klasor", hedef, "ATLANDI", "numara listede yok")
            continue
        if kalan_parca not in parcalar:
            sonuc.ekle("klasor", hedef, "RET", f"MİCRO numarası {kalan_parca} listede yok: {parcalar}")
            continue
        eski = kart.klasor_no_2
        kart.klasor_no_2 = ";".join(p for p in parcalar if p != cikar)
        _tarihce(db, case_id, "klasor_no_2", eski, kart.klasor_no_2, kim,
                 f"›10: {cikar} ekibin kendi ürettiği numara, MİCRO {kalan_parca} kalır")
        sonuc.ekle("klasor", hedef, "YAPILDI", f"{eski!r} → {kart.klasor_no_2!r}")


# ─── Adım 3: föy dönüşü ──────────────────────────────────────────────────────

def foyleri_dondur(db, satirlar: Sequence[Tuple[str, int]], *, kim: str, sonuc: Sonuc) -> None:
    kanit = "›09: 13.09 kararı (föy bu kartta) prod'a hiç girmemişti"
    kaynaklar: Dict[int, List[Tuple[models.CaseFoy, models.Case]]] = {}
    for sistem_no, hedef_id in satirlar:
        hedef_metin = f"{sistem_no} → #{hedef_id}"
        foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sistem_no).one_or_none()
        hedef = _canli_kart(db, hedef_id)
        if foy is None or hedef is None:
            sonuc.ekle("foy", hedef_metin, "RET", "föy yok" if foy is None else "hedef kart yok/silinmiş")
            continue
        if foy.case_id == hedef_id:
            sonuc.ekle("foy", hedef_metin, "ATLANDI", "föy zaten hedefte")
            continue
        kaynaklar.setdefault(foy.case_id, []).append((foy, hedef))

    for kaynak_id, kalemler in kaynaklar.items():
        kaynak = db.get(models.Case, kaynak_id)
        hedefler = {h.id for _, h in kalemler}
        tasinacak = {f.sistem_no for f, _ in kalemler}
        kaynak_foyleri = {f.sistem_no for f in db.query(models.CaseFoy)
                          .filter(models.CaseFoy.case_id == kaynak_id)}
        ret = "föyler farklı kartlara gidiyor" if len(hedefler) > 1 else ""
        if not ret and kaynak_foyleri != tasinacak:
            ret = f"kaynak kartta başka föy var ({', '.join(sorted(kaynak_foyleri - tasinacak))})"
        if not ret:
            hedef = kalemler[0][1]
            with db.begin_nested():
                b = mb.birlestir(db, hedef, kaynak, kim=kim, tarihce_alani="ekip_cevabi_1609_birlestirme",
                                 sebep_etiketi=f"{KAYNAK} ›09")
            if not b.ret:
                for foy, _ in kalemler:
                    sonuc.ekle("foy", f"{foy.sistem_no} → #{hedef.id}", "YAPILDI",
                               f"#{kaynak_id} kartı birleşti ({b.tasinan})")
                continue
            ret = b.ret
        for foy, hedef in kalemler:
            _foy_tasi(db, foy, hedef, kim, kanit)
            sonuc.ekle("foy", f"{foy.sistem_no} → #{hedef.id}", "YAPILDI",
                       f"kart birleşmedi ({ret}) → yalnız föy #{kaynak_id}'den taşındı")
        if kaynak is not None and kaynak.deleted_at is None and _foy_sayisi(db, kaynak_id) == 0:
            if kaynak.documents:
                sonuc.ekle("foy", f"#{kaynak_id}", "RET",
                           f"föysüz kaldı ama {len(kaynak.documents)} belgesi var — kapatılmadı, insan kararı")
            else:
                _kapat(db, kaynak, "›09: föyleri 13.09 kartlarına döndü, föysüz ve belgesiz kaldı", kim)
                sonuc.ekle("foy", f"#{kaynak_id}", "YAPILDI", "föysüz + belgesiz kaynak kart kapandı")


# ─── Adım 4: mükerrer kartlar ────────────────────────────────────────────────

def ciftleri_birlestir(db, ciftler: Sequence[Tuple[int, int, str]], *, kim: str, sonuc: Sonuc) -> None:
    for oneri_kalan, oneri_muk, kanit in ciftler:
        kalan_id, muk_id = oneri_kalan, oneri_muk
        if (oneri_muk, oneri_kalan) in CIFT_ISTISNALARI:
            kalan_id, muk_id = oneri_muk, oneri_kalan
        secenek = CIFT_ISTISNALARI.get((kalan_id, muk_id), {})
        hedef = f"#{kalan_id} ← #{muk_id}"
        if any({kalan_id, muk_id} == {a, b} for a, b, _ in CIFT_YERINE_ILISKI):
            sonuc.ekle("cift", hedef, "ATLANDI", "ayrı müvekkil kartı — birleşmez, ilişki adımında bağlanır")
            continue
        kalan, muk = db.get(models.Case, kalan_id), db.get(models.Case, muk_id)
        if kalan is None or muk is None:
            sonuc.ekle("cift", hedef, "RET", "kart bulunamadı")
            continue
        if muk.deleted_at is not None:
            sonuc.ekle("cift", hedef, "ATLANDI", f"mükerrer zaten kapalı ({muk.delete_reason!r})")
            continue
        with db.begin_nested():
            b = mb.birlestir(db, kalan, muk, kim=kim, tarihce_alani="ekip_cevabi_1609_birlestirme",
                             sebep_etiketi=f"{KAYNAK} {kanit}", **secenek)
        temizlenen = _muvekkil_olmayanlari_sil(db, kalan, kim) if not b.ret else []
        sonuc.ekle("cift", hedef, "RET" if b.ret else "YAPILDI",
                   b.ret or f"{kanit}; taşınan={b.tasinan}"
                   + (f" · müvekkil olmayan taraf silindi: {', '.join(temizlenen)}" if temizlenen else ""))


def _muvekkil_olmayanlari_sil(db, kart: models.Case, kim: str) -> List[str]:
    silinen: List[str] = []
    for taraf in list(kart.parties):
        if taraf.party_type != "CLIENT" or taraf.name not in MUVEKKIL_OLMAYAN_ADLAR:
            continue
        bagli = (db.query(models.CaseDocument).filter(models.CaseDocument.case_party_id == taraf.id).count()
                 + db.query(models.CaseFoy).filter(models.CaseFoy.case_party_id == taraf.id).count())
        if bagli:
            continue
        kart.parties.remove(taraf)
        _tarihce(db, kart.id, "taraf", f"{taraf.name} (CLIENT)", None, kim,
                 "›05 birleşmesi: büronun avukatı müvekkil kutusuna yazılmıştı")
        silinen.append(taraf.name)
    db.flush()
    return silinen


# ─── Adım 5: kapatma ─────────────────────────────────────────────────────────

def kartlari_kapat(db, kapatmalar: Sequence[Tuple[int, str]], atla: Set[int], *, kim: str, sonuc: Sonuc) -> None:
    belge_hedefi = {k: (h, s) for k, h, s in G179_KAPATMALAR if h is not None}
    for case_id, sebep in kapatmalar:
        hedef_metin = f"#{case_id}"
        if case_id in atla:
            sonuc.ekle("kapatma", hedef_metin, "ATLANDI", "birleştirme adımının kartı")
            continue
        kart = db.get(models.Case, case_id)
        if kart is None:
            sonuc.ekle("kapatma", hedef_metin, "RET", "kart yok")
            continue
        if kart.deleted_at is not None:
            sonuc.ekle("kapatma", hedef_metin, "ATLANDI", f"zaten kapalı ({kart.delete_reason!r})")
            continue
        foy_sayisi = _foy_sayisi(db, case_id)
        if foy_sayisi:
            sonuc.ekle("kapatma", hedef_metin, "RET", f"kartta {foy_sayisi} föy var — kapatılmaz")
            continue
        tasinan = 0
        if case_id in belge_hedefi:
            hedef_id, g179_sebep = belge_hedefi[case_id]
            hedef = _canli_kart(db, hedef_id)
            if hedef is None:
                sonuc.ekle("kapatma", hedef_metin, "RET", f"belge hedefi #{hedef_id} yok/silinmiş")
                continue
            for d in list(kart.documents):
                kart.documents.remove(d)
                hedef.documents.append(d)
                d.case_party_id = None
                tasinan += 1
            if tasinan:
                _tarihce(db, hedef_id, "belge_tasima", f"#{case_id} {kart.tracking_no}", f"{tasinan} belge", kim,
                         g179_sebep)
            sebep = f"{sebep} · {g179_sebep}"
        _kapat(db, kart, sebep, kim)
        sonuc.ekle("kapatma", hedef_metin, "YAPILDI",
                   kart.tracking_no + (f" · {tasinan} belge taşındı" if tasinan else "")
                   + (f" · {len(kart.documents)} belge kartla gizlendi" if kart.documents else ""))


# ─── Adım 6: ayırma ──────────────────────────────────────────────────────────

def kartlari_ayir(db, kart_idler: Sequence[int], *, kim: str, sonuc: Sonuc) -> None:
    kullanilan: Dict[str, int] = {}
    for kart_id in kart_idler:
        if kart_id in AYIRMA_ATLA:
            sonuc.ekle("ayirma", f"#{kart_id}", "ATLANDI", AYIRMA_ATLA[kart_id])
            continue
        kart = db.get(models.Case, kart_id)
        if kart is not None and kart.deleted_at is not None:
            sonuc.ekle("ayirma", f"#{kart_id}", "ATLANDI", f"kart kapalı ({kart.delete_reason!r})")
            continue
        kalem = bka.karti_ayir(db, kart_id, kullanilan, kim=kim)
        aciklama = kalem.aciklama
        if kalem.yeni_kartlar:
            aciklama += " · " + " · ".join(f"yeni #{i} {t} ({', '.join(f)})" for i, t, f in kalem.yeni_kartlar)
        sonuc.ekle("ayirma", f"#{kart_id}", kalem.sonuc, aciklama)


# ─── Adım 7: karar künyesi ───────────────────────────────────────────────────

def _satir_icerigi(row: models.CaseStageDecision) -> Dict[str, object]:
    return {alan: getattr(row, alan) for alan in stage_decisions.CONTENT_FIELDS}


def kunyeleri_duzelt(db, kalemler: Sequence[Tuple[int, str, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    source = f"{DEGISTIREN} ({kim})"
    for kart_id, sistem_no, eski_esas, eski_karar in kalemler:
        hedef_metin = f"#{kart_id} {sistem_no}"
        kart = _canli_kart(db, kart_id)
        if kart is None:
            foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sistem_no).one_or_none()
            kart = _canli_kart(db, foy.case_id) if foy is not None else None
        if kart is None or not kart.esas_no:
            sonuc.ekle("kunye", hedef_metin, "RET", "kart yok ya da esası boş")
            continue
        yerel = (db.query(models.CaseStageDecision)
                 .filter(models.CaseStageDecision.case_id == kart.id,
                         models.CaseStageDecision.stage == "YEREL")
                 .order_by(models.CaseStageDecision.sira_no).all())
        son = yerel[-1] if yerel else None
        degisen: List[str] = []
        try:
            if son is not None and son.esas_no == kart.esas_no and son.karar_no == eski_karar:
                # 13478 deseni: eski turun kararı güncel esasın satırında
                icerik = _satir_icerigi(son)
                icerik["esas_no"] = eski_esas
                if stage_decisions.update_stage_decision(db, kart, son, source=source,
                                                         dogrulama_durumu=son.dogrulama_durumu, **icerik):
                    degisen.append(f"sira {son.sira_no} esas {kart.esas_no}→{eski_esas}")
                son = None
            if son is None or son.esas_no != kart.esas_no:
                stage_decisions.add_stage_decision(db, kart, stage="YEREL", mahkeme=kart.court,
                                                   esas_no=kart.esas_no, source=source)
                degisen.append(f"güncel tur satırı ({kart.esas_no}, kararsız)")
            else:
                icerik = _satir_icerigi(son)
                if son.karar_no or son.karar_tarihi:
                    sonuc.ekle("kunye", hedef_metin, "RET",
                               f"güncel turda karar var ({son.karar_no} {son.karar_tarihi}) — insan kararı")
                    continue
                if son.karar_durumu:
                    eski_durum = son.karar_durumu
                    icerik["karar_durumu"] = None
                    stage_decisions.update_stage_decision(db, kart, son, source=source,
                                                          dogrulama_durumu=son.dogrulama_durumu, **icerik)
                    degisen.append(f"güncel turda karar yok → karar_durumu {eski_durum!r} boşaldı")
        except stage_decisions.ProtectedStageDecisionError as hata:
            sonuc.ekle("kunye", hedef_metin, "RET", str(hata))
            continue
        if kart.esas_no:
            case_manager.add_historical_esas(db, kart, eski_esas, court=kart.court, source=source)
        if degisen:
            _tarihce(db, kart.id, "karar_kunyesi", eski_karar, None, kim,
                     f"›01: karar {eski_karar} eski tura ({eski_esas}) ait; güncel esas {kart.esas_no} kararsız")
            sonuc.ekle("kunye", hedef_metin, "YAPILDI", "; ".join(degisen) + f" · kart karar_no={kart.karar_no!r}")
        else:
            sonuc.ekle("kunye", hedef_metin, "ATLANDI", f"zincir zaten doğru · kart karar_no={kart.karar_no!r}")


# ─── Adım 8: dosya son durumu ────────────────────────────────────────────────

def son_durumlari_duzelt(db, kart_idler: Sequence[int], *, kim: str, sonuc: Sonuc) -> None:
    for kart_id in kart_idler:
        hedef = f"#{kart_id}"
        kart = _canli_kart(db, kart_id)
        if kart is None:
            sonuc.ekle("son_durum", hedef, "RET", "kart yok/silinmiş")
            continue
        if kart.dosya_son_durumu != SON_DURUM_ESKI:
            sonuc.ekle("son_durum", hedef, "ATLANDI", f"son durum {kart.dosya_son_durumu!r}")
            continue
        _tarihce(db, kart_id, "dosya_son_durumu", kart.dosya_son_durumu, SON_DURUM_YENI, kim,
                 "›02: istinaf kaldırdı, dosya yerelde yeni esasla derdest")
        kart.dosya_son_durumu = SON_DURUM_YENI
        sonuc.ekle("son_durum", hedef, "YAPILDI", f"{SON_DURUM_ESKI} → {SON_DURUM_YENI}")


# ─── Adım 9: ilişki ──────────────────────────────────────────────────────────

def iliskileri_kur(db, ciftler: Sequence[Tuple[int, int, str]], *, kim: str, sonuc: Sonuc) -> None:
    for a_id, b_id, kanit in ciftler:
        hedef = f"#{a_id} ↔ #{b_id}"
        a, b = _canli_kart(db, a_id), _canli_kart(db, b_id)
        if a is None or b is None:
            sonuc.ekle("iliski", hedef, "RET", "kart yok/silinmiş")
            continue
        if bka._iliski_var(db, a_id, b_id):
            sonuc.ekle("iliski", hedef, "ATLANDI", "bağ zaten var")
            continue
        db.add(models.CaseRelation(source_case_id=a_id, target_case_id=b_id, relation_type=ILISKI_TURU,
                                   created_by=kim, note=f"{KAYNAK}: {kanit}"[:500]))
        db.flush()
        sonuc.ekle("iliski", hedef, "YAPILDI", f"{a.tracking_no} ↔ {b.tracking_no}")


# ─── Koşu ────────────────────────────────────────────────────────────────────

ADIM_ADLARI = {
    "k14393": "1. Kart 14393 onarımı", "klasor": "2. Klasör (2.55x)",
    "foy": "3. Föy dönüşü (13.09)", "cift": "4. Mükerrer kart",
    "kapatma": "5. Kapatma", "ayirma": "6. Ayırma",
    "kunye": "7. Karar künyesi", "son_durum": "8. Dosya son durumu",
    "iliski": "9. İlişkili dosya",
}


def kos(session_factory, *, ek5: Path, apply: bool = False, kim: str = DEGISTIREN,
        kart_14393: bool = True) -> Sonuc:
    veri = ek5_oku(ek5)
    sonuc = Sonuc()
    db = session_factory()
    try:
        if kart_14393:
            kart_14393_onar(db, kim=kim, sonuc=sonuc)
            klasorleri_temizle(db, KLASOR_CIKAR, kim=kim, sonuc=sonuc)
        foyleri_dondur(db, veri["foy_donus"], kim=kim, sonuc=sonuc)
        ciftleri_birlestir(db, veri["cift"], kim=kim, sonuc=sonuc)
        cift_kartlari = {k for a, b, _ in veri["cift"] for k in (a, b)}
        kartlari_kapat(db, veri["kapatma"], cift_kartlari, kim=kim, sonuc=sonuc)
        kartlari_ayir(db, veri["ayirma"], kim=kim, sonuc=sonuc)
        kunyeleri_duzelt(db, veri["kunye"], kim=kim, sonuc=sonuc)
        son_durumlari_duzelt(db, veri["son_durum"], kim=kim, sonuc=sonuc)
        iliskileri_kur(db, list(CIFT_YERINE_ILISKI) + veri["iliski"], kim=kim, sonuc=sonuc)
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
                f"Ek-5 (16.09.2026) kart düzeltmeleri — {'UYGULANDI' if apply else 'KURU KOŞU'}",
                "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET"))
        satirlar.append(f"  {ad:26} {y:4} yapıldı · {a:4} atlandı · {r:3} ret")
    gosterilecek = sonuc.kalemler if ayrinti else [k for k in sonuc.kalemler if k.sonuc == "RET"]
    if gosterilecek:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in gosterilecek)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ek-5 (16.09.2026) kart düzeltmeleri")
    ayristirici.add_argument("--ek5", required=True, type=Path, help="HUKDOK_CEVAP_EKI_5_2026-09-16.xlsx")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    ayristirici.add_argument("--ayrinti", action="store_true", help="bütün kalemleri bas (yalnız RET değil)")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, ek5=args.ek5, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply, ayrinti=args.ayrinti))
    return 0


if __name__ == "__main__":
    sys.exit(main())
