"""Otomatik dava ilişkisi tespiti — TKU grubu + esas/mahkeme ikizi (okuma yolu).

`GET /api/cases/{id}/relations` yanıtındaki `automatic` listesini bu modül üretir.
İlişkiler HİÇBİR TABLOYA YAZILMAZ, her istekte yeniden hesaplanır; `case_relations`
tablosu kullanıcının elle kurduğu bağların evi olarak kalır (`is_manual=True`).

Neden yazılmıyor
----------------
İlişkinin kaynağı `case_foys.tku_no` — yani aktarımın HER koşusunda tazelenen bir
veri. Türetilmiş ilişki satırı yazmak, aktarımın "aynı girdiyle ikinci koşu 0
değişiklik" sözleşmesini (`scripts/hukdok_aktarim.py`) ikinci bir yazıcıyla delerdi:
föy bir karttan diğerine taşındığında bayat ilişki satırları geride kalırdı. Okurken
hesaplamak idempotentliği bedavaya getirir, migrasyon istemez.

İki dedektör (2026-08-20 lokal ölçümü, 8.156 föy / 14.345 kart)
--------------------------------------------------------------
* **TKU ortaklığı** — ekip TKU numarasını yalnız "aynı davanın föyleri" için değil,
  farklı davaları İLİŞKİLENDİRMEK için de kullanmış: 593 grup birden çok karta,
  400'ü birden çok mahkemeye, 369'u birden çok dosya türüne yayılıyor. 807 kart
  çifti aşağıdaki türlere artıksız bölünüyor.
* **Esas + mahkeme + tür ikizi** — TKU'nun kör noktası: aynı mahkemede aynı esas
  numarasıyla duran 199 kart grubunun 24'ünde hiçbir kartın TKU'su yok.

Kartlar BİRLEŞTİRİLMEZ. `tracking_no` müvekkil isim bloğu taşıyan ofis dosya
numarasıdır; tek davada birden çok müvekkil varsa her müvekkilin ayrı ofis dosyası
olması doğrudur — aynı ölçümde AYNI_DAVA çiftlerinin 149'undan 121'i farklı isim
bloğu taşıyor. Bu modül kartları bağlar, birleştirmez.

TKU okuması iki kolondan yapılır: `case_foys.tku_no` (aktarımın yazdığı, tek gerçek
kaynak) ve `cases.tku_no` (eski Full_Rapor_TKU aktarımının bıraktığı legacy kolon;
aktarım buraya bilinçli yazmaz ama prod'da dolu olabilir).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session, selectinload

import models
from auth_helpers import tenant_filter_clause
from services.judicial_unit import normalize_court

# ── İlişki türleri ────────────────────────────────────────────────────────────
# Elle kurulan bağların türleriyle (ICRA_CEZA, ASIL_TEMYIZ, BIRLESEN…) aynı alanı
# paylaşırlar ama kesişmezler: bunlar YALNIZ otomatik katmanda üretilir.
AYNI_DAVA = "AYNI_DAVA"                      # aynı tür + aynı mahkeme + aynı esas
YENIDEN_ACILAN = "YENIDEN_ACILAN"            # aynı tür, farklı esas/mahkeme
ARABULUCULUK_ONCULU = "ARABULUCULUK_ONCULU"  # arabuluculuk ↔ dava
ICRA_PARALEL = "ICRA_PARALEL"
CEZA_PARALEL = "CEZA_PARALEL"
SAVCILIK_PARALEL = "SAVCILIK_PARALEL"
ADLI_IDARI_PARALEL = "ADLI_IDARI_PARALEL"    # Hukuk ↔ İdare (aynı olay, iki yargı kolu)
ILGILI = "ILGILI"

# Güven puanı: panelde sıralama içindir, olasılık DEĞİLDİR. AYNI_DAVA en tepede
# durmalı — kullanıcının ilk görmesi gereken "bu aslında tek dava" uyarısıdır.
GUVEN_PUANI: Dict[str, int] = {
    AYNI_DAVA: 95,
    ARABULUCULUK_ONCULU: 80,
    ICRA_PARALEL: 80,
    CEZA_PARALEL: 80,
    SAVCILIK_PARALEL: 80,
    ADLI_IDARI_PARALEL: 80,
    YENIDEN_ACILAN: 70,
    ILGILI: 60,
}

# Panelin taşıyabileceği üst sınır. Ölçülen en kalabalık TKU grubu 6 kart, en
# kalabalık esas ikizi 4 kart; sınır patolojik veriye (tek harfli esas no gibi)
# karşı emniyet supabıdır, normal veride hiç devreye girmez.
AZAMI_ILISKI = 25

_TUR_PARALEL = (
    ("Arabuluculuk", ARABULUCULUK_ONCULU),
    ("İcra", ICRA_PARALEL),
    ("Ceza", CEZA_PARALEL),
    ("Savcılık", SAVCILIK_PARALEL),
)


@dataclass(frozen=True)
class KartOzeti:
    """Sınıflandırıcının ihtiyaç duyduğu asgari kart alanları (DB'siz test için)."""
    id: int
    file_type: Optional[str] = None
    court: Optional[str] = None
    esas_no: Optional[str] = None


# Kimlik sayılan esas biçimi: dört haneli yıl + '/' + EN AZ BİR RAKAM. Ölçümde
# (2026-08-20, 14.345 kart) 13.506 kart bu kalıba uyuyor; kalanların büyük kısmı
# numarası girilmemiş yer tutucular: 397 kart 'YYYY/' ve 208 kart '2014/???'.
# Bunları kimlik saymak felakettir — aynı mahkemedeki tüm '2019/' kartları
# birbirinin ikizi ilan edilirdi.
_ESAS_KALIBI = re.compile(r"^\d{4}/\d")


def esas_anahtari(deger: Optional[str]) -> str:
    """Esas numarasını karşılaştırılabilir hâle getirir ('2020 / 1777' → '2020/1777').

    Kimlik olarak KULLANILAMAYACAK değer boş string döner ve asla eşleşme üretmez:
    boş/eksik değerler, yer tutucular ('2021/', '2014/???') ve kalıba uymayan tekil
    yazımlar. "Bu iki kart aynı davadır" hükmü veren bir anahtarda şüphe, eşleşme
    değil sessizlik lehine çözülür.
    """
    metin = (deger or "").strip()
    if not metin:
        return ""
    anahtar = re.sub(r"\s+", "", metin).upper()
    return anahtar if _ESAS_KALIBI.match(anahtar) else ""


def _mahkeme_anahtari(deger: Optional[str]) -> str:
    metin = (deger or "").strip()
    return normalize_court(metin) if metin else ""


def _tur(deger: Optional[str]) -> str:
    return (deger or "").strip()


def siniflandir(kaynak: KartOzeti, hedef: KartOzeti) -> str:
    """İki kart arasındaki ilişki türünü ALANLARDAN türetir (saf fonksiyon).

    Sıra önemlidir: tür farkı kalemlerinde Arabuluculuk, İcra'dan önce bakılır —
    bir grup hem arabuluculuk hem icra kartı taşıyorsa kullanıcıya anlatılması
    gereken öncelikli hikâye arabuluculuk zinciridir.
    """
    kaynak_tur, hedef_tur = _tur(kaynak.file_type), _tur(hedef.file_type)
    esas = esas_anahtari(kaynak.esas_no)
    mahkeme = _mahkeme_anahtari(kaynak.court)

    if kaynak_tur and kaynak_tur == hedef_tur:
        ayni_esas = bool(esas) and esas == esas_anahtari(hedef.esas_no)
        ayni_mahkeme = bool(mahkeme) and mahkeme == _mahkeme_anahtari(hedef.court)
        if ayni_esas and ayni_mahkeme:
            return AYNI_DAVA
        return YENIDEN_ACILAN

    turler = {kaynak_tur, hedef_tur}
    for tur_adi, iliski in _TUR_PARALEL:
        if tur_adi in turler:
            return iliski
    if {"Hukuk", "İdare"} <= turler:
        return ADLI_IDARI_PARALEL
    return ILGILI


def _tku_kumesi(db: Session, case) -> Set[str]:
    """Kartın taşıdığı TKU değerleri — föy satırları + legacy kart kolonu."""
    degerler: Set[str] = set()
    kart_tku = (getattr(case, "tku_no", None) or "").strip()
    if kart_tku:
        degerler.add(kart_tku)
    satirlar = (
        db.query(models.CaseFoy.tku_no)
        .filter(models.CaseFoy.case_id == case.id, models.CaseFoy.tku_no.isnot(None))
        .distinct()
        .all()
    )
    for (deger,) in satirlar:
        temiz = (deger or "").strip()
        if temiz:
            degerler.add(temiz)
    return degerler


def _tku_eslesmeleri(
    db: Session, tkular: Sequence[str], haric_case_id: int, tenant_id: str
) -> Dict[int, Set[str]]:
    """TKU değerlerini paylaşan diğer kartlar → {case_id: {tku, …}}."""
    if not tkular:
        return {}
    liste = sorted(tkular)
    sonuc: Dict[int, Set[str]] = {}

    foy_satirlari = (
        db.query(models.CaseFoy.case_id, models.CaseFoy.tku_no)
        .join(models.Case, models.Case.id == models.CaseFoy.case_id)
        .filter(
            models.CaseFoy.tku_no.in_(liste),
            models.CaseFoy.case_id != haric_case_id,
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .distinct()
        .all()
    )
    for case_id, tku in foy_satirlari:
        sonuc.setdefault(case_id, set()).add((tku or "").strip())

    kart_satirlari = (
        db.query(models.Case.id, models.Case.tku_no)
        .filter(
            models.Case.tku_no.in_(liste),
            models.Case.id != haric_case_id,
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .all()
    )
    for case_id, tku in kart_satirlari:
        sonuc.setdefault(case_id, set()).add((tku or "").strip())

    return sonuc


def _esas_eslesmeleri(db: Session, case, tenant_id: str) -> Set[int]:
    """Aynı esas + aynı mahkeme + aynı tür kartlar (TKU'dan bağımsız dedektör).

    Esas numarası SQL'de tam eşitlikle aranır (`ix_cases_esas_no` kullanılsın diye);
    mahkeme ve tür karşılaştırması Python'da, normalize edilmiş değerler üzerinden
    yapılır. Mahkeme eşitliği ŞARTTIR: esas numaraları mahkemeler arasında serbestçe
    tekrar eder, tek başına esas eşleşmesi rastlantıdır.
    """
    ham = (case.esas_no or "").strip()
    if not esas_anahtari(ham):
        return set()  # yer tutucu/eksik esas ikizlik kanıtı değildir
    adaylar = (
        db.query(models.Case.id, models.Case.court, models.Case.file_type)
        .filter(
            models.Case.esas_no.in_({ham, case.esas_no}),
            models.Case.id != case.id,
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .all()
    )
    mahkeme = _mahkeme_anahtari(case.court)
    tur = _tur(case.file_type)
    if not mahkeme or not tur:
        return set()
    return {
        aday_id
        for aday_id, aday_court, aday_tur in adaylar
        if _mahkeme_anahtari(aday_court) == mahkeme and _tur(aday_tur) == tur
    }


def kart_ozeti(kart: Any) -> KartOzeti:
    """ORM `Case` → sınıflandırıcının gördüğü sade özet.

    `kart: Any` bilinçli: models.py klasik `Column(...)` tanımları kullanıyor, yani
    mypy için `case.court` bir `Column[str]`. Köprüyü tek noktada toplamak, ORM
    tiplerini modülün geri kalanından uzak tutar.
    """
    return KartOzeti(
        id=kart.id, file_type=kart.file_type, court=kart.court, esas_no=kart.esas_no
    )


def _gerekce(tkular: Set[str], esas_ikizi: bool, esas_no: Optional[str]) -> str:
    parcalar: List[str] = []
    if tkular:
        etiketler = ", ".join(sorted(t for t in tkular if t))
        parcalar.append(f"Aynı TKU grubu ({etiketler})")
    if esas_ikizi:
        numara = (esas_no or "").strip()
        parcalar.append(f"aynı mahkemede aynı esas ({numara})" if numara else "aynı mahkeme + esas")
    return " · ".join(parcalar) if parcalar else "İlişkili kayıt"


def iliskileri_bul(db: Session, case: Any, tenant_id: str) -> List[Tuple[Any, str, str, int]]:
    """Kartın otomatik ilişkilerini döndürür: (diğer kart, tür, gerekçe, puan).

    Sıralama: güven puanı azalan, sonra kart id — böylece "bu aslında tek dava"
    uyarısı listenin başında durur ve sıra istekler arasında kararlıdır.
    """
    tkular = _tku_kumesi(db, case)
    tku_eslesme = _tku_eslesmeleri(db, sorted(tkular), case.id, tenant_id)
    esas_eslesme = _esas_eslesmeleri(db, case, tenant_id)

    aday_idler = set(tku_eslesme) | esas_eslesme
    if not aday_idler:
        return []

    kartlar = (
        db.query(models.Case)
        .options(selectinload(models.Case.parties))
        .filter(models.Case.id.in_(sorted(aday_idler)))
        .all()
    )

    kaynak_ozet = kart_ozeti(case)
    sonuc: List[Tuple[Any, str, str, int]] = []
    for kart in kartlar:
        ozet = kart_ozeti(kart)
        tur = siniflandir(kaynak_ozet, ozet)
        gerekce = _gerekce(
            tku_eslesme.get(ozet.id, set()), ozet.id in esas_eslesme, ozet.esas_no
        )
        sonuc.append((kart, tur, gerekce, GUVEN_PUANI.get(tur, GUVEN_PUANI[ILGILI])))

    sonuc.sort(key=lambda satir: (-satir[3], satir[0].id))
    return sonuc[:AZAMI_ILISKI]
