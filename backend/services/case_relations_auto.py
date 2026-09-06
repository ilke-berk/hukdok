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
* **Hasar dosya numarası** (G128, 06.09.2026) — sigortanın hasar numarası tanım
  gereği TEK olaydır; föy (`case_foys.hasar_no`) ve kart (`cases.hasar_dosya_no`)
  kolonlarından okunur, ikisi de ";" ile çok değerli. Lokal ölçüm (05.09): 237
  çiftin 61'i TKU'da yok.

Öneri katmanı (G128) — `onerileri_bul`
--------------------------------------
Aynı HASTA adı (karşı taraf, kişi) + aynı DOKTOR adı (müvekkil/sigortalı, kişi)
taşıyan kartlar "aynı tıbbi vaka olabilir" önerisidir: otomatik BAĞLANMAZ, panelde
ayrı bölümde durur, avukat "Bağla" derse `case_relations`a elle bağ olarak yazılır,
"Reddet" derse `relation_type=ONERI_RED` satırı düşer ve bir daha önerilmez.
Sigorta/kurum adları doktor yerine SAYILMAZ — ölçümde AXA üzerinden 4.660 sahte çift
çıkıyordu; kişi + kişi eşleşmesi 1.176 çift, 528'i TKU ile örtüşüyor (%45'i TKU'nun
bilmediği, çoğu TKU'suz kart). Ad karşılaştırması `party_check.normalize_party_key`
(unvan/aksan/şirket eki yutulur), kelime bazlı tam eşleşme; bulanık eşleşme YOK.

Kartlar BİRLEŞTİRİLMEZ. `tracking_no` müvekkil isim bloğu taşıyan ofis dosya
numarasıdır; tek davada birden çok müvekkil varsa her müvekkilin ayrı ofis dosyası
olması doğrudur — aynı ölçümde AYNI_DAVA çiftlerinin 149'undan 121'i farklı isim
bloğu taşıyor. Bu modül kartları bağlar, birleştirmez.

TKU okuması iki kolondan yapılır: `case_foys.tku_no` (aktarımın yazdığı, tek gerçek
kaynak) ve `cases.tku_no` (eski Full_Rapor_TKU aktarımının bıraktığı legacy kolon;
aktarım buraya bilinçli yazmaz ama prod'da dolu olabilir).

Kapsam dışı föy (G113, `case_foys.kapsam_durumu IS NOT NULL` — veri ekibinin
`Silinen_Föyler` / `Kapsam_Dışı` sayfaları) TKU okumasına GİRMEZ: mükerrer ya da
malpraktis dışı bir föyün TKU'su üzerinden kartları birbirine bağlamak, ekibin
geri çektiği bir bağı panelde yaşatmak olurdu. Föy silinmez, yalnız süzülür; legacy
`cases.tku_no` kolonunun kapsam bilgisi yoktur, olduğu gibi okunmaya devam eder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

import models
from auth_helpers import tenant_filter_clause
from party_check import _is_corporate, normalize_party_key
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
# Öneri katmanı (G128): reddedilen öneri `case_relations`ta bu türle durur —
# panelde gösterilmez, yalnız "bir daha önerme" kaydıdır.
ONERI_RED = "ONERI_RED"
ONERI_PUANI = 50                              # ILGILI'nin (60) altında: onay bekler

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
        .filter(
            models.CaseFoy.case_id == case.id,
            models.CaseFoy.tku_no.isnot(None),
            models.CaseFoy.kapsam_durumu.is_(None),      # G113: kapsam dışı föy süzülür
        )
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
            models.CaseFoy.kapsam_durumu.is_(None),      # G113: kapsam dışı föy süzülür
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


# Hasar numarası yer tutucuları: teslimde "0" ve "-" doluluk sayılıyor.
_HASAR_YER_TUTUCU = frozenset({"", "0", "-", "—", "?"})


def hasar_parcalari(deger: Optional[str]) -> Set[str]:
    """';' ile çok değerli hasar numarasını anahtar kümesine çevirir (4+ karakter)."""
    sonuc: Set[str] = set()
    for ham in (deger or "").replace("\n", ";").split(";"):
        temiz = "".join(ham.split()).upper()
        if temiz not in _HASAR_YER_TUTUCU and len(temiz) >= 4:
            sonuc.add(temiz)
    return sonuc


def _hasar_kumesi(db: Session, case) -> Set[str]:
    """Kartın hasar numaraları — kart kolonu + kapsamdaki föyler."""
    degerler = hasar_parcalari(getattr(case, "hasar_dosya_no", None))
    satirlar = (
        db.query(models.CaseFoy.hasar_no)
        .filter(
            models.CaseFoy.case_id == case.id,
            models.CaseFoy.hasar_no.isnot(None),
            models.CaseFoy.kapsam_durumu.is_(None),
        )
        .all()
    )
    for (deger,) in satirlar:
        degerler |= hasar_parcalari(deger)
    return degerler


def _hasar_eslesmeleri(
    db: Session, hasarlar: Set[str], haric_case_id: int, tenant_id: str
) -> Dict[int, Set[str]]:
    """Hasar numarasını paylaşan diğer kartlar → {case_id: {hasar, …}}.

    SQL LIKE ile aday daraltılır (kolonlar ';' ile çok değerli), kesin eşleşme
    Python'da `hasar_parcalari` üzerinden yapılır — "3509162150001" içinde
    "9162150" gibi alt dizi rastlantıları böylece elenir.
    """
    if not hasarlar:
        return {}
    liste = sorted(hasarlar)
    sonuc: Dict[int, Set[str]] = {}
    foy_satirlari = (
        db.query(models.CaseFoy.case_id, models.CaseFoy.hasar_no)
        .join(models.Case, models.Case.id == models.CaseFoy.case_id)
        .filter(
            or_(*[models.CaseFoy.hasar_no.like(f"%{h}%") for h in liste]),
            models.CaseFoy.case_id != haric_case_id,
            models.CaseFoy.kapsam_durumu.is_(None),
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .all()
    )
    kart_satirlari = (
        db.query(models.Case.id, models.Case.hasar_dosya_no)
        .filter(
            or_(*[models.Case.hasar_dosya_no.like(f"%{h}%") for h in liste]),
            models.Case.id != haric_case_id,
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .all()
    )
    for case_id, deger in list(foy_satirlari) + list(kart_satirlari):
        ortak = hasar_parcalari(deger) & hasarlar
        if ortak:
            sonuc.setdefault(case_id, set()).update(ortak)
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


def _gerekce(tkular: Set[str], esas_ikizi: bool, esas_no: Optional[str],
             hasarlar: Optional[Set[str]] = None) -> str:
    parcalar: List[str] = []
    if tkular:
        etiketler = ", ".join(sorted(t for t in tkular if t))
        parcalar.append(f"Aynı TKU grubu ({etiketler})")
    if esas_ikizi:
        numara = (esas_no or "").strip()
        parcalar.append(f"aynı mahkemede aynı esas ({numara})" if numara else "aynı mahkeme + esas")
    if hasarlar:
        parcalar.append(f"aynı hasar dosya no ({', '.join(sorted(hasarlar))})")
    return " · ".join(parcalar) if parcalar else "İlişkili kayıt"


def iliskileri_bul(db: Session, case: Any, tenant_id: str) -> List[Tuple[Any, str, str, int]]:
    """Kartın otomatik ilişkilerini döndürür: (diğer kart, tür, gerekçe, puan).

    Sıralama: güven puanı azalan, sonra kart id — böylece "bu aslında tek dava"
    uyarısı listenin başında durur ve sıra istekler arasında kararlıdır.
    """
    tkular = _tku_kumesi(db, case)
    tku_eslesme = _tku_eslesmeleri(db, sorted(tkular), case.id, tenant_id)
    esas_eslesme = _esas_eslesmeleri(db, case, tenant_id)
    hasar_eslesme = _hasar_eslesmeleri(db, _hasar_kumesi(db, case), case.id, tenant_id)

    aday_idler = set(tku_eslesme) | esas_eslesme | set(hasar_eslesme)
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
            tku_eslesme.get(ozet.id, set()), ozet.id in esas_eslesme, ozet.esas_no,
            hasar_eslesme.get(ozet.id),
        )
        sonuc.append((kart, tur, gerekce, GUVEN_PUANI.get(tur, GUVEN_PUANI[ILGILI])))

    sonuc.sort(key=lambda satir: (-satir[3], satir[0].id))
    return sonuc[:AZAMI_ILISKI]


# ── Öneri katmanı: aynı hasta + aynı doktor (G128) ────────────────────────
_KURUM_KELIMELERI = frozenset({
    "BAKANLIGI", "BAKANLIK", "VALILIGI", "VALILIK", "UNIVERSITESI", "UNIVERSITE",
    "HASTANESI", "HASTANE", "REKTORLUGU", "BELEDIYESI", "BELEDIYE", "KURUMU", "KURUM",
    "MERKEZI", "MUDURLUGU", "SAGLIK", "TIP", "KLINIK", "POLIKLINIK", "VAKFI", "VAKIF",
})
_AZAMI_ADAY = 200


def kisi_anahtari(ad: Optional[str]) -> str:
    """Kişi adının karşılaştırma anahtarı; kurum/sigorta adı ise boş döner."""
    anahtar = normalize_party_key(ad or "")
    if not anahtar or len(anahtar) < 6 or _is_corporate(anahtar):
        return ""
    if set(anahtar.split()) & _KURUM_KELIMELERI:
        return ""
    return anahtar


def _kisi_kumeleri(parties: Sequence[Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """({hasta anahtarı: görünen ad}, {doktor anahtarı: görünen ad}): hasta = karşı
    taraf kişileri, doktor = müvekkil/üçüncü taraf kişileri (sigorta ve kurum düşer).
    Anahtar kelime-sıralı normalize (karşılaştırma), görünen ad kayıttaki yazım
    (gerekçe metni)."""
    hasta: Dict[str, str] = {}
    doktor: Dict[str, str] = {}
    for p in parties:
        ad = getattr(p, "name", None) or ""
        anahtar = kisi_anahtari(ad)
        if not anahtar:
            continue
        if p.party_type == "COUNTER":
            hasta.setdefault(anahtar, ad.strip())
        elif p.party_type in ("CLIENT", "THIRD"):
            doktor.setdefault(anahtar, ad.strip())
    return hasta, doktor


def onerileri_bul(db: Session, case: Any, tenant_id: str,
                  haric_idler: Optional[Set[int]] = None) -> List[Tuple[Any, str, str, int]]:
    """Aynı hasta + aynı doktor taşıyan kartlar: (kart, tür, gerekçe, puan).

    Otomatik katmandan AYRI döner (route `suggested`); `haric_idler` otomatik
    ilişkiler, elle bağlar ve reddedilen öneriler — bunlar yeniden önerilmez.
    Aday daraltma: hastanın en uzun kelimesi SQL LIKE ile aranır, kesin karar
    Python'da tam anahtar eşitliğiyle verilir (bulanık eşleşme yok).
    """
    hasta, doktor = _kisi_kumeleri(getattr(case, "parties", None) or [])
    if not hasta or not doktor:
        return []
    haric = set(haric_idler or ()) | {case.id}

    kelimeler = {max(h.split(), key=len) for h in hasta}
    kelimeler = {k for k in kelimeler if len(k) >= 4}
    if not kelimeler:
        return []
    aday_satirlari = (
        db.query(models.CaseParty.case_id)
        .join(models.Case, models.Case.id == models.CaseParty.case_id)
        .filter(
            models.CaseParty.party_type == "COUNTER",
            or_(*[models.CaseParty.name.ilike(f"%{k}%") for k in sorted(kelimeler)]),
            models.CaseParty.case_id != case.id,
            models.Case.deleted_at.is_(None),
            tenant_filter_clause(models.Case, tenant_id),
        )
        .distinct()
        .limit(_AZAMI_ADAY)
        .all()
    )
    aday_idler = {cid for (cid,) in aday_satirlari} - haric
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
        k_hasta, k_doktor = _kisi_kumeleri(kart.parties)
        ortak_hasta = set(hasta) & set(k_hasta)
        ortak_doktor = set(doktor) & set(k_doktor)
        if not ortak_hasta or not ortak_doktor:
            continue
        tur = siniflandir(kaynak_ozet, kart_ozeti(kart))
        hasta_adlari = ", ".join(hasta[a] for a in sorted(ortak_hasta))
        doktor_adlari = ", ".join(doktor[a] for a in sorted(ortak_doktor))
        gerekce = (f"Aynı hasta ({hasta_adlari}) + aynı doktor ({doktor_adlari}) — "
                   "aynı tıbbi vaka olabilir, onay bekler")
        sonuc.append((kart, tur, gerekce, ONERI_PUANI))
    sonuc.sort(key=lambda satir: satir[0].id)
    return sonuc[:AZAMI_ILISKI]
