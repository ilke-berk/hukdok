"""Ofis dosya numarası üreticisi — karar 023'ün TEK kanonik kaynağı (G235).

Format: ``<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>``

    DR.M.OZTURK-0003-HUK          kişi müvekkil
    KR.ENTHONE-0015-CEZ           kurum müvekkil
    AXA-3297-DR.E.ALTUNC-HUK      sigortacı müvekkil + sigortalı hekim
    SG-0001-HUK                   listede olmayan sigortacı, sigortalı yok

Bu modül G235'te yalnız KURULDU: hiçbir mevcut akış onu çağırmaz. Canlı tahsis
G236'da (`add_case`), göç G238'de (`scripts/ofis_no_gocu.py`) bağlanır. Şartname
`docs/kararlar/023-ofis-no-formati.md`.

Terimler
    *kategori kodu*   `DR`/`SC`/`HS`/`OH`/`KR`/`BR`/`DG` — iki harf.
    *müvekkil kodu*   numaranın İLK bloğunun tamamı: `DR.M.OZTURK`, `KR.INKA`, `AXA`.
                      Sıra bu kod başına sayılır (karar 023 §8) — `ofis_no_sayaclari.kod`
                      ve `cases.ofis_no_kodu` bunu taşır.

Kod listeleri (kategori → kod, sigorta şirketi → kod + eşleşme kelimeleri) DB'de
düzenlenebilir (`client_categories.ofis_no_kodu`, `sigorta_kisa_kodlari`); saf
fonksiyonlar listeyi parametre alır (`KodListeleri`), verilmezse karar 023'ün
varsayılan tablosu kullanılır. Kod değişikliği yalnız YENİ numaraları etkiler —
bu modül verilmiş numaraya hiç dokunmaz.

Boş/çözülemeyen ad `ValueError`dır: yer tutucu numara (`XXXXXXXXXX`, `KURUM`)
ÜRETİLMEZ.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import models

# ─── Sabitler ────────────────────────────────────────────────────────────────

#: Listede olmayan sigortacının kodu. Sabit geri dönüştür — `sigorta_kisa_kodlari`
#: tablosunda satırı YOKTUR ve hiçbir listeye kod olarak yazılamaz.
SG_KODU = "SG"

#: Kod biçimi: 2-10 büyük ASCII harf (kategori ve sigorta kodları için ortak).
KOD_BICIMI = re.compile(r"^[A-Z]{2,10}$")

#: Kanonik kategori anahtarı (`client_categories.code`) → varsayılan kod.
VARSAYILAN_KATEGORI_KODLARI: dict[str, str] = {
    "DOKTOR": "DR",
    "SAGLIK-CALISANI": "SC",
    "HASTA": "HS",
    "OZEL-HASTANE": "OH",
    "KURUM": "KR",
    "BIREYSEL": "BR",
    "DIGER": "DG",
}

#: Kişi kategorileri — ad `<baş harf>.<SOYAD>` olur; kalanı kurumdur (ilk anlamlı kelime).
KISI_KATEGORILERI = frozenset({"DOKTOR", "SAGLIK-CALISANI", "HASTA", "BIREYSEL"})

#: Kategori ADI (ASCII büyük harf) içinde aranan parça → kanonik anahtar. SIRA ÖNEMLİ:
#: "OZEL HASTANE" "HASTA"dan, "SAGLIK CALISANI" ("Diğer Sağlık Çalışanı" föy tipi)
#: "DIGER"den önce gelmeli. Klinik → OH, Acente/Dernek → KR (karar 023 §2).
_KATEGORI_AD_PARCALARI: tuple[tuple[str, str], ...] = (
    ("SAGLIK CALISANI", "SAGLIK-CALISANI"),
    ("OZEL HASTANE", "OZEL-HASTANE"),
    ("KLINIK", "OZEL-HASTANE"),
    ("DOKTOR", "DOKTOR"),
    ("HASTA", "HASTA"),
    ("ACENTE", "KURUM"),
    ("DERNEK", "KURUM"),
    ("KURUM", "KURUM"),
    ("BIREYSEL", "BIREYSEL"),
    ("DIGER", "DIGER"),
)

#: Çok müvekkilde ad önceliği (karar 023 §5, karar 002): Doktor > Sağlık Çalışanı >
#: Hasta > Bireysel > Diğer/kategorisiz > Özel Hastane > Kurum.
_ONCELIK: dict[Optional[str], int] = {
    "DOKTOR": 0,
    "SAGLIK-CALISANI": 1,
    "HASTA": 2,
    "BIREYSEL": 3,
    "DIGER": 4,
    None: 4,
    "OZEL-HASTANE": 5,
    "KURUM": 6,
}

#: Karar 023 §3 sigorta tablosu: (kod, ad, müvekkil adında aranan kelimeler).
#: Eşleşme KELİME bazlıdır (ASCII büyük harf); "AKSIGORTA" bitişik yazım içindir.
VARSAYILAN_SIGORTA_KODLARI: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("AK", "AK Sigorta", ("AK", "AKSIGORTA")),
    ("ANADOLU", "Anadolu Sigorta", ("ANADOLU",)),
    ("AXA", "AXA Sigorta", ("AXA",)),
    ("CORPUS", "Corpus Sigorta", ("CORPUS",)),
    ("QUICK", "Quick Sigorta", ("QUICK",)),
    ("EUREKO", "Eureko Sigorta", ("EUREKO",)),
    ("NIPPON", "Nippon Sigorta", ("NIPPON",)),
    ("SOMPO", "Sompo Sigorta", ("SOMPO",)),
    ("KORU", "Koru Sigorta", ("KORU",)),
    ("HDI", "HDI Sigorta", ("HDI",)),
    ("ZIRAAT", "Ziraat Sigorta", ("ZIRAAT",)),
)

#: Kurum adlarında anlamsız jenerik kelimeler — `frontend/src/lib/caseNumberUtils.ts`
#: `CORP_STOP` kümesinin birebir kopyası (karar 023 §2).
CORP_STOP = frozenset({
    "SIGORTA", "HAYAT", "ANONIM", "TURK", "SIRKETI", "KOOPERATIFI",
    "TIC", "TICARETI", "SAN", "SANAYI", "SANAYII",
    "INS", "INSAAT", "TAAHHUT",
    "LTD", "STI", "AS",
    "HASTANE", "HASTANESI", "SAGLIK", "HIZ", "HIZMETLERI", "HIZM",
    "OZEL", "TIBBI", "MALZ",
    "SITE", "SITESI", "YONETICILIGI", "YONETIM", "KURULU", "MERKEZ",
    "VE", "VEYA",
    "PAZ", "PAZARLAMA", "DAG", "DAGITIM",
    "ORG", "ORGANIZASYON", "YAPIM", "TANITIM",
    "URETIM", "ISLETMECILIGI", "DANISMANLIK",
    "GLOBAL", "SISTEMLERI", "HIZMETLER",
})

#: Kişi adından HER ZAMAN atılan unvanlar.
_UNVAN_KESIN = frozenset({"DR", "PROF", "DOC", "UZM", "OPR", "ECZ", "YRD"})
#: Yalnız NOKTALI yazıldığında unvan sayılanlar ("Hem.", "Av.") — noktasız hali
#: gerçek bir soyad olabilir ("Ali Uz").
_UNVAN_NOKTALI = frozenset({"HEM", "UZ", "OP", "AV", "DT", "EBE", "ARS", "GOR", "STJ"})
#: Sigortalının sağlık çalışanı (hekim dışı) olduğunu gösteren unvanlar.
_SAGLIK_CALISANI_UNVANLARI = frozenset({"HEM", "EBE"})

#: Dosya türü (ASCII büyük harf) → tür kodu (karar 023 §9). Haritada olmayan → HUK.
_TUR_KODLARI: dict[str, str] = {
    "HUKUK": "HUK",
    "CEZA": "CEZ",
    "ICRA": "ICR",
    "ARABULUCULUK": "ARB",
    "SAVCILIK": "SAV",
    "IDARE": "IDR",
    "IDARI YARGI": "IDR",
    "TAHKIM": "THK",
    "VERGI": "VRG",
    "DANISMANLIK": "DAN",
}
VARSAYILAN_TUR_KODU = "HUK"

#: Adda şirket işareti (kategorisiz müvekkilde KR/BR ayrımı, karar 023 §2).
#: `SAN.`/`TIC.` yalnız NOKTALI sayılır ("Ali San" kişidir).
_SIRKET_ISARETI = re.compile(
    r"\bA\.\s?S\b"
    r"|\b(?:LTD|STI|INC|GMBH|LLC|CORP|ANONIM|LIMITED|SIRKETI|SIRKET|KOOPERATIFI|HOLDING)\b"
    r"|\b(?:SAN|TIC)\."
)
_SIRKET_AS = re.compile(r"(?<!\w)AŞ(?!\w)")

_TR_ASCII = str.maketrans("ıİğĞüÜşŞöÖçÇ", "IIgGuUsSoOcC")


class KodCakismasi(ValueError):
    """Kod başka bir listede (ya da aynı listede) zaten kullanılıyor."""


# ─── Metin yardımcıları ──────────────────────────────────────────────────────

def ascii_buyuk(metin: Optional[str]) -> str:
    """Türkçe harfleri ASCII'ye indirip büyütür (İ/ı→I, Ö→O …); diğer aksanlar da düşer."""
    s = (metin or "").translate(_TR_ASCII).upper()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _kelimeler(metin: Optional[str]) -> list[str]:
    """Yalnız harf dizileri (ASCII büyük) — kelime bazlı eşleşme için."""
    return re.findall(r"[A-Z]+", ascii_buyuk(metin))


def _al(nesne: Any, *adlar: str) -> Any:
    """Sözlükten ya da nesneden ilk dolu alanı okur."""
    for ad in adlar:
        deger = nesne.get(ad) if isinstance(nesne, Mapping) else getattr(nesne, ad, None)
        if deger:
            return deger
    return None


def kod_dogrula(kod: Optional[str]) -> str:
    """Kod biçimini doğrular (2-10 büyük ASCII harf); geçersizse `ValueError`."""
    temiz = (kod or "").strip()
    if not KOD_BICIMI.match(temiz):
        raise ValueError("Kod 2-10 büyük ASCII harf olmalı")
    return temiz


# ─── Kod listeleri ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SigortaKodu:
    kod: str
    anahtarlar: tuple[str, ...]


@dataclass(frozen=True)
class KodListeleri:
    """Üreticinin okuduğu kod listeleri (yalnız AKTİF satırlar).

    `kategori`: kanonik anahtar (`DOKTOR` …) → kod. `ozel_kategori`: yönetimin
    eklediği, kanonik olmayan kategori ADI (ASCII büyük) → kod. `sigorta`: sıralı
    şirket kodları; eşleşme ilk tutan satırdadır.
    """
    kategori: Mapping[str, str] = field(default_factory=lambda: dict(VARSAYILAN_KATEGORI_KODLARI))
    sigorta: tuple[SigortaKodu, ...] = field(
        default_factory=lambda: tuple(SigortaKodu(k, a) for k, _ad, a in VARSAYILAN_SIGORTA_KODLARI)
    )
    ozel_kategori: Mapping[str, str] = field(default_factory=dict)


def varsayilan_kod_listeleri() -> KodListeleri:
    """Karar 023 tablolarının kendisi (DB'siz)."""
    return KodListeleri()


def anahtarlari_temizle(anahtarlar: Optional[Iterable[str]]) -> list[str]:
    """Eşleşme kelimelerini ASCII büyük harfe indirir, boşları ve tekrarları atar."""
    temiz: list[str] = []
    for a in anahtarlar or []:
        kelime = " ".join(_kelimeler(a))
        if kelime and kelime not in temiz:
            temiz.append(kelime)
    return temiz


def kod_listelerini_yukle(db: Session) -> KodListeleri:
    """Kod listelerini DB'den okur. Pasif satır eşleşmede KULLANILMAZ.

    Kategori: `client_categories.ofis_no_kodu` dolu AKTİF satırlar; kanonik
    anahtarlı satır varsayılanın üzerine yazar, kodu boş/pasif kanonik satırda
    karar 023 varsayılanı geçerli kalır. Sigorta: `sigorta_kisa_kodlari` AKTİF
    satırları (id sırası) — tablo DB'nin tek kaynağıdır, pasife alınan şirket `SG`'ye düşer.
    """
    kategori = dict(VARSAYILAN_KATEGORI_KODLARI)
    ozel: dict[str, str] = {}
    satirlar = (
        db.query(models.ClientCategory)
        .filter(models.ClientCategory.ofis_no_kodu.isnot(None))
        .order_by(models.ClientCategory.sequence, models.ClientCategory.id)
        .all()
    )
    for satir in satirlar:
        if satir.active is False or not satir.ofis_no_kodu:
            continue
        if satir.code in VARSAYILAN_KATEGORI_KODLARI:
            kategori[str(satir.code)] = str(satir.ofis_no_kodu)
        else:
            ozel[ascii_buyuk(str(satir.name)).strip()] = str(satir.ofis_no_kodu)
    sigorta = tuple(
        SigortaKodu(str(s.kod), tuple(anahtarlari_temizle(s.eslesme_anahtarlari) or [str(s.kod)]))
        for s in db.query(models.SigortaKisaKodu)
        .filter(models.SigortaKisaKodu.aktif.is_(True))
        .order_by(models.SigortaKisaKodu.id)
        .all()
    )
    return KodListeleri(kategori=kategori, sigorta=sigorta, ozel_kategori=ozel)


# ─── Kategori ────────────────────────────────────────────────────────────────

def sirket_isareti_var(ad: Optional[str]) -> bool:
    """Adda şirket işareti (A.Ş., AŞ, Ltd., Şti., San., Tic., Inc., GmbH …) var mı?"""
    return bool(_SIRKET_AS.search(ad or "") or _SIRKET_ISARETI.search(ascii_buyuk(ad)))


def _kategori_anahtari(kategori_adi: Optional[str]) -> Optional[str]:
    """Kategori adı/kodu → kanonik anahtar; tanınmıyorsa (ya da boşsa) None."""
    norm = " ".join(_kelimeler(kategori_adi))
    if not norm:
        return None
    for parca, anahtar in _KATEGORI_AD_PARCALARI:
        if parca in norm:
            return anahtar
    return None


def _kategori_coz(
    kategori_adi: Optional[str], muvekkil_adi: Optional[str], kl: KodListeleri
) -> tuple[str, bool, Optional[str]]:
    """(kod, kişi mi, kanonik anahtar) — tek çözüm yolu; öncelik de buradan okunur."""
    anahtar = _kategori_anahtari(kategori_adi)
    if anahtar is not None:
        kod = kl.kategori.get(anahtar) or VARSAYILAN_KATEGORI_KODLARI[anahtar]
        return kod, anahtar in KISI_KATEGORILERI, anahtar
    ozel = kl.ozel_kategori.get(ascii_buyuk(kategori_adi).strip()) if kategori_adi else None
    if ozel:
        # Yönetimin eklediği kategori: kodu bir kişi kategorisinin koduysa kişi, değilse kurum.
        kisi = any(kl.kategori.get(a) == ozel for a in KISI_KATEGORILERI)
        return ozel, kisi, None
    # Kategorisiz (ya da tanınmayan): şirket işareti varsa KR, yoksa BR.
    anahtar = "KURUM" if sirket_isareti_var(muvekkil_adi) else "BIREYSEL"
    kod = kl.kategori.get(anahtar) or VARSAYILAN_KATEGORI_KODLARI[anahtar]
    return kod, anahtar in KISI_KATEGORILERI, None


def kategori_kodu(
    kategori_adi: Optional[str], muvekkil_adi: Optional[str], kod_listeleri: Optional[KodListeleri] = None
) -> str:
    """Müvekkilin kategori kodu (DR/SC/HS/OH/KR/BR/DG).

    Klinik → OH, Acente/Dernek → KR. Kategorisiz müvekkil: adında şirket işareti
    varsa KR, yoksa BR. Sigortacı ayrımı burada DEĞİL `musteri_kodu`'ndadır.
    """
    return _kategori_coz(kategori_adi, muvekkil_adi, kod_listeleri or varsayilan_kod_listeleri())[0]


# ─── Ad blokları ─────────────────────────────────────────────────────────────

def _kisi_kelimeleri(ad: Optional[str]) -> list[str]:
    """Kişi adının unvansız kelimeleri (ASCII büyük harf)."""
    norm = ascii_buyuk(ad)
    norm = re.sub(r"\([^)]*\)", " ", norm)          # "(DR. ÖZEL)" gibi parantez notu
    norm = norm.replace("'", "").replace("’", "")   # O'Brien → OBRIEN
    parcalar = [(m.group(1), bool(m.group(2))) for m in re.finditer(r"([A-Z]+)(\.?)", norm)]
    kelimeler: list[str] = []
    onceki_dr = False
    for i, (kelime, noktali) in enumerate(parcalar):
        if kelime in _UNVAN_KESIN or (noktali and kelime in _UNVAN_NOKTALI):
            onceki_dr = kelime == "DR" and i > 0
            continue
        # Sonda "DR.ÖZEL" / "DR ÖZEL" (özel hekim notu) — ad değil.
        if kelime == "OZEL" and onceki_dr:
            onceki_dr = False
            continue
        onceki_dr = False
        kelimeler.append(kelime)
    return kelimeler


def kisi_blogu(kod: str, ad: Optional[str]) -> str:
    """`DR.M.OZTURK` — ilk adın baş harfi + son kelime (soyad); unvan ve noktalama atılır.

    Tek kelimelik ad baş harfsiz yazılır (`HS.MADONNA`). Boş ad `ValueError`.
    """
    kelimeler = _kisi_kelimeleri(ad)
    if not kelimeler:
        raise ValueError("Kişi adı boş — ofis no bloğu üretilemez")
    if len(kelimeler) == 1:
        return f"{kod}.{kelimeler[0]}"
    return f"{kod}.{kelimeler[0][0]}.{kelimeler[-1]}"


def kurum_blogu(kod: str, ad: Optional[str]) -> str:
    """`KR.ENTHONE` — jenerik kelimeler (`CORP_STOP`) atılır, ilk anlamlı kelime alınır.

    Ad kesilmez. Tüm kelimeler jenerikse ham ilk kelime kullanılır; boş ad `ValueError`.
    """
    norm = ascii_buyuk(ad).replace(".", "").replace("'", "").replace("’", "")   # A.Ş. → AS
    ham = re.findall(r"[A-Z]+", norm)
    if not ham:
        raise ValueError("Kurum adı boş — ofis no bloğu üretilemez")
    anlamli = [k for k in ham if k not in CORP_STOP and len(k) > 1]
    return f"{kod}.{(anlamli or ham)[0]}"


# ─── Sigortacı ───────────────────────────────────────────────────────────────

def sigortaci_mi(ad: Optional[str], kategori_adi: Optional[str] = None) -> bool:
    """Müvekkil sigorta şirketi mi? Kategori adında ya da kendi adında "sigorta" geçer."""
    return "SIGORTA" in ascii_buyuk(kategori_adi) or "SIGORTA" in ascii_buyuk(ad)


def sigorta_kodu(ad: Optional[str], kod_listeleri: Optional[KodListeleri] = None) -> Optional[str]:
    """Sigortacının şirket kodu; listede (aktif) eşleşme yoksa None (çağıran `SG` yazar)."""
    kl = kod_listeleri or varsayilan_kod_listeleri()
    kelimeler = _kelimeler(ad)
    for satir in kl.sigorta:
        for anahtar in satir.anahtarlar:
            aranan = anahtar.split()
            n = len(aranan)
            if n and any(kelimeler[i:i + n] == aranan for i in range(len(kelimeler) - n + 1)):
                return satir.kod
    return None


def _muvekkil_alanlari(muvekkil: Any) -> tuple[str, Optional[str]]:
    ad = str(_al(muvekkil, "name", "ad") or "").strip()
    kategori = _al(muvekkil, "category", "kategori")
    return ad, (str(kategori) if kategori else None)


def musteri_kodu(
    muvekkiller: Sequence[Any], kod_listeleri: Optional[KodListeleri] = None
) -> tuple[str, Any]:
    """Numaranın ilk bloğu (müvekkil kodu) + adı/kodu veren müvekkil.

    Müvekkil: `name` (+ `category`) alanlı sözlük ya da nesne. Kurallar (karar 023 §5):
    sigortacı varsa kod sigortacınındır (listede yoksa `SG`); yoksa ad önceliği
    Doktor > Sağlık Çalışanı > Hasta > Bireysel > Diğer/kategorisiz > Özel Hastane > Kurum.
    Adı dolu müvekkil yoksa `ValueError`.
    """
    kl = kod_listeleri or varsayilan_kod_listeleri()
    adaylar = [(ad, kat, m) for m in muvekkiller for ad, kat in [_muvekkil_alanlari(m)] if ad]
    if not adaylar:
        raise ValueError("Müvekkil yok — ofis no üretilemez")

    sigortacilar = [(ad, m) for ad, kat, m in adaylar if sigortaci_mi(ad, kat)]
    if sigortacilar:
        for ad, m in sigortacilar:
            kod = sigorta_kodu(ad, kl)
            if kod:
                return kod, m
        return SG_KODU, sigortacilar[0][1]

    cozumler = [(_kategori_coz(kat, ad, kl), ad, m) for ad, kat, m in adaylar]
    (kod, kisi, _anahtar), ad, secilen = min(cozumler, key=lambda c: _ONCELIK[c[0][2]])
    return (kisi_blogu(kod, ad) if kisi else kurum_blogu(kod, ad)), secilen


# ─── Sigortalı bloğu ─────────────────────────────────────────────────────────

def _hekim_mi(ad: Optional[str]) -> bool:
    return "DR" in _kelimeler(ad)


def _sigortali_blogu_addan(ad: Optional[str], kl: KodListeleri) -> str:
    """Kategorisi bilinmeyen sigortalının bloğu: unvan/şirket işaretinden çıkarılır.

    `Hem.`/`Ebe` → SC; hastane/klinik → OH; başka şirket → KR; aksi halde hekim (DR).
    """
    kelimeler = set(_kelimeler(ad))
    if not _hekim_mi(ad):
        if kelimeler & {"HASTANE", "HASTANESI", "KLINIK", "KLINIGI", "POLIKLINIK", "POLIKLINIGI"}:
            return kurum_blogu(kl.kategori.get("OZEL-HASTANE") or "OH", ad)
        if sirket_isareti_var(ad):
            return kurum_blogu(kl.kategori.get("KURUM") or "KR", ad)
        if kelimeler & _SAGLIK_CALISANI_UNVANLARI or "HEMSIRE" in kelimeler:
            ham = re.sub(r"\b(HEMSIRE|HEM|EBE)\b\.?", " ", ascii_buyuk(ad))
            return kisi_blogu(kl.kategori.get("SAGLIK-CALISANI") or "SC", ham)
    return kisi_blogu(kl.kategori.get("DOKTOR") or "DR", ad)


#: Çok adlı "Sigortalı" değerinin ayracı: `;` ya da unvanla başlayan yeni satır
#: ("Dr.A\nDr.B"). Unvansız satır sonu ayraç DEĞİL — sarılmış tek addır ("Ferda Korkmaz \nÖzkanoğlu").
_SIGORTALI_AYRACI = re.compile(r";|\n(?=\s*(?:DR|PROF|DOC|UZM|OPR|OP)\b)")
_VE_DIGERLERI = re.compile(r"\s+VE\s+DIG(?:ERLERI|ERLER|\.)?\s*$", re.IGNORECASE)
_KURUM_KELIMELERI = frozenset({"HASTANE", "HASTANESI", "KLINIK", "KLINIGI", "POLIKLINIK", "POLIKLINIGI"})


def _sigortali_adlari(ad: Optional[str]) -> list[str]:
    """Ham "Sigortalı" değerini tek tek adlara böler (boş parçalar atılır)."""
    ham = str(ad or "")
    # Ayraç ASCII büyük kopyada aranır (uzunluk korunur: Türkçe harfler tek karaktere iner),
    # parçalar ham metinden kesilir.
    norm = ham.translate(_TR_ASCII).upper()
    if len(norm) != len(ham):
        norm = ham
    parcalar: list[str] = []
    bas = 0
    for m in _SIGORTALI_AYRACI.finditer(norm):
        parcalar.append(ham[bas:m.start()])
        bas = m.end()
    parcalar.append(ham[bas:])
    temiz: list[str] = []
    for parca in parcalar:
        p = parca.strip()
        kesim = _VE_DIGERLERI.search(p.translate(_TR_ASCII))
        if kesim:
            p = p[:kesim.start()].strip()
        if p:
            temiz.append(p)
    return temiz


def _kurum_adi_mi(ad: Optional[str]) -> bool:
    return not _hekim_mi(ad) and bool(set(_kelimeler(ad)) & _KURUM_KELIMELERI or sirket_isareti_var(ad))


def _tek_sigortali(ad: Optional[str]) -> Optional[str]:
    """Çok adlı değerden TEK sigortalıyı seçer (karar 023 §7): ilk `Dr` unvanlı ad,
    yoksa kurum olmayan ilk ad, o da yoksa ilk ad. Adlar ASLA kaynaştırılmaz."""
    adlar = _sigortali_adlari(ad)
    if not adlar:
        return None
    for olcut in (_hekim_mi, lambda a: not _kurum_adi_mi(a)):
        for aday in adlar:
            if olcut(aday):
                return aday
    return adlar[0]


def sigortali_sec(
    case: Any = None,
    foys: Optional[Iterable[Any]] = None,
    parties: Optional[Iterable[Any]] = None,
    muvekkiller: Optional[Sequence[Any]] = None,
    kod_listeleri: Optional[KodListeleri] = None,
) -> Optional[str]:
    """Sigortalı bloğu (`DR.E.ALTUNC`) ya da None — TEK kişi, kendi kategori koduyla.

    Yalnız sigortacı müvekkilli kartta çağrılır. Kaynak önceliği (karar 023 §7 + §5):

    1. föy `ham_veri["Sigortalı"]` (kapsam dışı işaretli föy atlanır; `;` ayraçlı çok
       adlı değerde adlar kaynaştırılmaz — `_tek_sigortali`: ilk hekim, yoksa ilk kişi)
    2. `case_parties.role == "Sigortalı"`
    3. sigortacıyla BİRLİKTE müvekkil olan kişi/kurum (§5 — öncelik `musteri_kodu` sırası)
    4. "Diğer Davalı" içindeki ilk hekim (adında `Dr` unvanı)

    `foys`/`parties` verilmezse `case.foys`/`case.parties` okunur. Bulunamazsa None:
    blok yazılmaz, kart "sigortalı eksik" listesine düşer (göç onu bekletmez).
    """
    kl = kod_listeleri or varsayilan_kod_listeleri()
    foy_listesi = list(foys if foys is not None else (getattr(case, "foys", None) or []))
    taraflar = list(parties if parties is not None else (getattr(case, "parties", None) or []))

    def _dene(ad: Any) -> Optional[str]:
        # Alan `;` ile birden çok kişi/kurum taşıyabilir — blok TEK addan üretilir.
        tek = _tek_sigortali(str(ad)) if ad else None
        try:
            return _sigortali_blogu_addan(tek, kl) if tek else None
        except ValueError:
            return None

    for foy in foy_listesi:
        if _al(foy, "kapsam_durumu"):
            continue
        ham = _al(foy, "ham_veri")
        blok = _dene(ham.get("Sigortalı")) if isinstance(ham, Mapping) else None
        if blok:
            return blok

    for taraf in taraflar:
        if _al(taraf, "role") == "Sigortalı":
            blok = _dene(_al(taraf, "name"))
            if blok:
                return blok

    ortaklar: list[Any] = list(muvekkiller) if muvekkiller is not None else [
        {"name": _al(t, "name"), "category": _al(_al(t, "client"), "category") if _al(t, "client") else None}
        for t in taraflar if _al(t, "party_type") == "CLIENT"
    ]
    sigortaci_olmayan = [m for m in ortaklar for ad, kat in [_muvekkil_alanlari(m)] if ad and not sigortaci_mi(ad, kat)]
    if sigortaci_olmayan:
        try:
            return musteri_kodu(sigortaci_olmayan, kl)[0]
        except ValueError:
            pass

    for taraf in taraflar:
        if _al(taraf, "role") == "Diğer Davalı" and _hekim_mi(_al(taraf, "name")):
            blok = _dene(_al(taraf, "name"))
            if blok:
                return blok
    return None


# ─── Tür + numara ────────────────────────────────────────────────────────────

def tur_kodu(file_type: Optional[str]) -> str:
    """`cases.file_type` → üç harfli tür kodu; boş ya da haritada olmayan → `HUK`."""
    return _TUR_KODLARI.get(" ".join(_kelimeler(file_type)), VARSAYILAN_TUR_KODU)


def numara_kur(kod: str, sira: int, sigortali: Optional[str], tur: str) -> str:
    """Parçalardan numarayı kurar (saf). Sıra 4 haneye sıfırla doldurulur, 9999'dan sonra uzar."""
    if not kod or not str(kod).strip():
        raise ValueError("Müvekkil kodu boş — ofis no üretilemez")
    if not isinstance(sira, int) or isinstance(sira, bool) or sira < 1:
        raise ValueError("Sıra 1 ya da daha büyük bir tam sayı olmalı")
    if not tur:
        raise ValueError("Tür kodu boş — ofis no üretilemez")
    parcalar = [str(kod), f"{sira:04d}"]
    if sigortali:
        parcalar.append(str(sigortali))
    parcalar.append(str(tur))
    return "-".join(parcalar)


# ─── Sayaç ───────────────────────────────────────────────────────────────────

_SIRA_TAHSIS_SQL = text(
    "INSERT INTO ofis_no_sayaclari (kod, son_sira, updated_at) "
    "VALUES (:kod, 1, CURRENT_TIMESTAMP) "
    "ON CONFLICT (kod) DO UPDATE SET "
    "son_sira = ofis_no_sayaclari.son_sira + 1, updated_at = CURRENT_TIMESTAMP "
    "RETURNING son_sira"
)


def sira_tahsis_et(db: Session, kod: str) -> int:
    """Müvekkil kodunun bir sonraki sırasını ATOMİK tahsis eder.

    Tek ifade (`INSERT … ON CONFLICT DO UPDATE … RETURNING`): satır kilidi çağıranın
    transaction'ı bitene dek tutulur, iki eşzamanlı çağrı asla aynı sırayı almaz.
    COMMIT ETMEZ — tahsis kartın kaydıyla aynı transaction'da yaşar; kayıt geri
    alınırsa sıra da geri döner (numara boşa yanmaz).
    """
    temiz = (kod or "").strip()
    if not temiz:
        raise ValueError("Müvekkil kodu boş — sıra tahsis edilemez")
    return int(db.execute(_SIRA_TAHSIS_SQL, {"kod": temiz}).scalar_one())


def siradaki(db: Session, kod: str) -> int:
    """Sayacı ARTIRMADAN bir sonraki sıra (`son_sira + 1`; sayaç yoksa 1)."""
    satir = db.get(models.OfisNoSayaci, (kod or "").strip())
    return (int(satir.son_sira) if satir is not None else 0) + 1


def onizle(
    db: Session,
    muvekkiller: Sequence[Any],
    file_type: Optional[str] = None,
    *,
    case: Any = None,
    foys: Optional[Iterable[Any]] = None,
    parties: Optional[Iterable[Any]] = None,
    kod_listeleri: Optional[KodListeleri] = None,
) -> dict[str, Any]:
    """"Bu kayıtla verilecek numara" — sayacı ARTIRMAZ (sıra = son_sira + 1).

    Önizlemedir: araya başka kayıt girerse gerçek tahsis (`sira_tahsis_et`) farklı
    sıra verebilir. Dönen sözlük: `numara`, `kod`, `sira`, `sigortali`, `tur`.
    """
    kl = kod_listeleri or kod_listelerini_yukle(db)
    kod, secilen = musteri_kodu(muvekkiller, kl)
    sigortali = None
    if sigortaci_mi(*_muvekkil_alanlari(secilen)):
        sigortali = sigortali_sec(case, foys, parties, muvekkiller=muvekkiller, kod_listeleri=kl)
    tur = tur_kodu(file_type)
    sira = siradaki(db, kod)
    return {
        "numara": numara_kur(kod, sira, sigortali, tur),
        "kod": kod,
        "sira": sira,
        "sigortali": sigortali,
        "tur": tur,
    }


# ─── Kod listesi yönetimi (admin uçları çağırır) ─────────────────────────────

def _kategori_kodlari_db(db: Session) -> set[str]:
    """Kategori tarafında KULLANILAN kodlar: DB'de yazılı olanlar + kanonik varsayılanlar."""
    yazili = {
        str(k) for (k,) in db.query(models.ClientCategory.ofis_no_kodu)
        .filter(models.ClientCategory.ofis_no_kodu.isnot(None)).all()
    }
    return yazili | set(VARSAYILAN_KATEGORI_KODLARI.values())


def sigorta_kodu_kullanilabilir(db: Session, kod: str, *, haric_id: Optional[int] = None) -> str:
    """Sigorta kodu yazılabilir mi? Biçim + `SG` + kategori kodu + mevcut satır çakışması."""
    temiz = kod_dogrula(kod)
    if temiz == SG_KODU:
        raise KodCakismasi(f"'{SG_KODU}' listede olmayan sigortacının sabit kodudur")
    if temiz in _kategori_kodlari_db(db):
        raise KodCakismasi(f"'{temiz}' bir kategori kodu — sigorta kodu olamaz")
    sorgu = db.query(models.SigortaKisaKodu.id).filter(models.SigortaKisaKodu.kod == temiz)
    if haric_id is not None:
        sorgu = sorgu.filter(models.SigortaKisaKodu.id != haric_id)
    if sorgu.first() is not None:
        raise KodCakismasi(f"'{temiz}' kodu zaten kayıtlı")
    return temiz


def kategori_kodu_kullanilabilir(db: Session, kod: str) -> str:
    """Kategori kodu yazılabilir mi? Biçim + `SG` + sigorta kodu (aktif/pasif) çakışması.

    İki kategori aynı kodu paylaşabilir (Klinik → OH gibi); sıra müvekkil kodu başınadır.
    """
    temiz = kod_dogrula(kod)
    if temiz == SG_KODU:
        raise KodCakismasi(f"'{SG_KODU}' listede olmayan sigortacının sabit kodudur")
    if db.query(models.SigortaKisaKodu.id).filter(models.SigortaKisaKodu.kod == temiz).first() is not None:
        raise KodCakismasi(f"'{temiz}' bir sigorta şirketi kodu — kategori kodu olamaz")
    return temiz
