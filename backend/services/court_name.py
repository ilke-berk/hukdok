"""Mahkeme adı için yapısal kimlik kapısı — yer · sıra · kanonik tür · daire.

Serbest string üretmek yerine adı bileşenlerine ayırır ve HER bileşeni kapalı bir
listeye karşı doğrular. Doğrulanamayan bileşen ÜRETİLMEZ (tahmin yasağı): sözlükte
olmayan yer boş bırakılır, asla "en yakın" bir başka yere dönüştürülmez.

Neden gerekti (2026-08-19 ölçümleri, G067):
  - `BAĞRI 1. ASLİYE HUKUK MAHKEMESİ` → `AĞRI …` (il alternasyonunda kelime sınırı yoktu)
  - `T.C. / TATVAN / 2. ASLİYE HUKUK MAHKEMESİ` → `VAN 2. …` (kendi kart verimizden)
  - `MANAVGAT`/`İSTANBUL ANADOLU` gibi yargı yerleri hiç tanınmıyordu (yalnız 81 il vardı)
  - `YARGITAY 11. HUKUK DAİRESİ` tek satırda daireyi düşürüyordu

Tasarım kuralları:
  - **Saf modül**: DB/dosya erişimi yok; il listesi çağıranın verdiği `yerler`
    argümanıyla gelir (`judicial_unit.py` deseni).
  - **Tür sözlüğünün İKİNCİ kopyası yoktur**: kanonik tür tek kaynaktan,
    `services.judicial_unit.PATTERNS` / `derive_judicial_unit` üzerinden okunur.
    Bu modüldeki tek tür bilgisi, kanonik sözlükte karşılığı olmayan ÜST MAHKEME
    kimlikleridir (`UST_MAHKEMELER`) — bunlar bir mahkeme "türü" değil, yer
    gerektirmeyen tekil kurumlardır.
  - **Kelime sınırı zorunlu**: yer eşleşmesi Türkçe harf sınıfıyla sınırlanır;
    `BAĞRI`→`AĞRI`, `TATVAN`→`VAN`, `GELİBOLU`→`BOLU` sızıntıları böyle kapanır.
  - **Güven damgası**: TAM (yer+tür doğrulandı ya da üst mahkeme) / KISMI (tür
    doğrulandı, yer tanınmadı) / YOK (tür bile tanınmadı).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

from services.judicial_unit import PATTERNS, derive_judicial_unit, normalize_court
from text_utils import turkish_upper

# ---------------------------------------------------------------------------
# Güven damgası — dış sözleşme (G068 kilidi buna bağlanacak)
# ---------------------------------------------------------------------------
GUVEN_TAM = "TAM"
GUVEN_KISMI = "KISMI"
GUVEN_YOK = "YOK"

# Türkçe büyük harf sınıfı (düzeltme işaretliler dahil). Kelime sınırı için
# `\b` YETMEZ: `re` için 'Ğ' kelime karakteri sayılır ama sınıfı biz kurmalıyız
# ki "BAĞRI" içindeki "AĞRI" eşleşmesin.
TR_HARF = "A-ZÇĞİIÖŞÜÂÎÛ"
_KELIME = rf"[{TR_HARF}]+"
_SINIR_ONCE = rf"(?<![{TR_HARF}])"
_SINIR_SONRA = rf"(?![{TR_HARF}])"

# Kurum sonekleri (tür ADI değil, sonek). Tür kanonik sözlükten doğrulandıktan
# SONRA yüzeyi sağa genişletmek için kullanılır.
_TUR_SON = (
    r"(?:MAHKEMESİ|MAHKEMELERİ|HÂKİMLİĞİ|HAKİMLİĞİ|DAİRESİ|DAİRELERİ|"
    r"HEYETİ|BAŞSAVCILIĞI|MÜDÜRLÜĞÜ|BÜROSU|NOTERLİĞİ)"
)
# Kanonik sözlük ve çağıranın listesi sustuğunda BAŞVURULAN son çare. Bilinçli
# olarak yalnız yargısal sonekler: "TAPU MÜDÜRLÜĞÜ" gibi kurumlar mahkeme diye
# üretilmemeli (savcılık/noter/arabulucu zaten judicial_unit kalıplarında var).
_MAHKEME_SON = r"(?:MAHKEMESİ|MAHKEMELERİ|HÂKİMLİĞİ|HAKİMLİĞİ|DAİRESİ|DAİRELERİ)"

# Sözel sıra sayıları → rakam. Daire numarasının "basamak düşmesi" ancak
# daire_no sayı olarak taşınırsa ölçülebilir (G067 karar 4).
SOZEL_SIRA: dict[str, int] = {
    "BİRİNCİ": 1, "İKİNCİ": 2, "ÜÇÜNCÜ": 3, "DÖRDÜNCÜ": 4, "BEŞİNCİ": 5,
    "ALTINCI": 6, "YEDİNCİ": 7, "SEKİZİNCİ": 8, "DOKUZUNCU": 9, "ONUNCU": 10,
    "ON BİRİNCİ": 11, "ONBİRİNCİ": 11, "ON İKİNCİ": 12, "ONİKİNCİ": 12,
    "ON ÜÇÜNCÜ": 13, "ONÜÇÜNCÜ": 13, "ON DÖRDÜNCÜ": 14, "ONDÖRDÜNCÜ": 14,
    "ON BEŞİNCİ": 15, "ONBEŞİNCİ": 15, "ON ALTINCI": 16, "ONALTINCI": 16,
    "ON YEDİNCİ": 17, "ONYEDİNCİ": 17, "ON SEKİZİNCİ": 18, "ONSEKİZİNCİ": 18,
    "ON DOKUZUNCU": 19, "ONDOKUZUNCU": 19, "YİRMİNCİ": 20,
}

# Yer gerektirmeyen tekil kurumlar. judicial_unit.PATTERNS bunları kanonik tür
# olarak taşımaz (YARGITAY hiç yok, DANIŞTAY var) ve "11. HUKUK DAİRESİ" alt
# dizesi BAM kalıbına düşer — bu yüzden üst mahkeme kimliği ÖNCE okunur.
UST_MAHKEMELER: tuple[str, ...] = (
    "ANAYASA MAHKEMESİ",
    "UYUŞMAZLIK MAHKEMESİ",
    "YARGITAY",
    "DANIŞTAY",
)

# ---------------------------------------------------------------------------
# Yargı yeri sözlüğü — adliye yerleri + bileşik yargı yerleri
# ---------------------------------------------------------------------------
# NEDEN burada: `cities` tablosu panelden yönetilen ve kullanıcıya adres/şehir
# seçtiren bir UI listesidir (routes/config.py). Oraya yüzlerce adliye yeri
# basmak o listeyi bozar. Kapsam bilinçli olarak EKSİK kalabilir: sözlükte
# olmayan yer `None` üretir (KISMI güven), YANLIŞ yer üretmez.
#
# NEDEN panele TAŞINMIYOR (G070 kararı, 2026-08-19): bu sözlük kullanıcı verisi
# değil AYRIŞTIRICI bilgisidir. Panelde yönetilse yanlış/eksik bir girdi doğrudan
# belge okumasını bozar ve hatayı kimsenin göremeyeceği bir yere taşır (`cities`in
# aksine — orada yanlış girdi yalnız bir dropdown'ı bozar). Sözlük kodda kalır,
# kapsamı GÖZLE değil TESTLE ölçülür: `tests/test_g070_yer_kapsami.py`.
#
# BAKIM KURALI (G070): buraya yalnız GERÇEK yargı yeri adı, yalnız KANONİK
# yazımıyla girer ve yalnız kendi kart verimizde ÖLÇÜLDÜĞÜ için girer (tahminle
# liste şişirilmez). Kısaltma ("İSTANBUL AND.", "EREĞLİ KDZ") ve yazım bozulması
# ("BAKİRKÖY", "DİYARBAKİR") GİRMEZ: eşleşen yüzey aynı zamanda kimliktir, ikinci
# bir yazım aynı yargı yerine İKİNCİ bir kimlik açar ve modülün varlık sebebini
# (gruplama/mükerrer tespiti) çürütür. Varyant→kanonik eşlemesi ayrı bir görevdir.
BILESIK_YARGI_YERLERI: tuple[str, ...] = (
    "İSTANBUL ANADOLU",
    "ANKARA BATI",
)

YARGI_YERLERI: tuple[str, ...] = (
    # İstanbul çevresi
    "BAKIRKÖY", "KARTAL", "KADIKÖY", "ŞİŞLİ", "BEYOĞLU", "ÜSKÜDAR", "EYÜP",
    "GAZİOSMANPAŞA", "KÜÇÜKÇEKMECE", "BÜYÜKÇEKMECE", "SİLİVRİ", "ŞİLE",
    "PENDİK", "MALTEPE", "SULTANBEYLİ", "BEYKOZ", "ÇATALCA", "TUZLA",
    "SARIYER", "FATİH", "BEŞİKTAŞ", "BAĞCILAR", "ZEYTİNBURNU", "ÜMRANİYE",
    # Kocaeli / Sakarya / Yalova / Bilecik
    "GEBZE", "KÖRFEZ", "KANDIRA", "KARAMÜRSEL", "AKYAZI", "HENDEK", "GEYVE",
    "KARASU", "ÇINARCIK", "BOZÜYÜK", "SÖĞÜT", "OSMANELİ", "GÖLCÜK", "KOCAALİ",
    # Bursa / Balıkesir / Çanakkale
    "İNEGÖL", "GEMLİK", "MUSTAFAKEMALPAŞA", "KARACABEY", "ORHANGAZİ", "İZNİK",
    "YENİŞEHİR", "MUDANYA", "BANDIRMA", "EDREMİT", "AYVALIK", "BURHANİYE",
    "GÖNEN", "SUSURLUK", "BİGADİÇ", "SINDIRGI", "DURSUNBEY", "ERDEK",
    "GELİBOLU", "BİGA", "ÇAN", "AYVACIK", "EZİNE", "BAYRAMİÇ",
    # İzmir / Manisa / Aydın / Muğla / Denizli
    "KARŞIYAKA", "BERGAMA", "ÖDEMİŞ", "TORBALI", "TİRE", "MENEMEN", "ALİAĞA",
    "ÇEŞME", "URLA", "SELÇUK", "KINIK", "KİRAZ", "BAYINDIR", "FOÇA", "KARABURUN",
    "SEFERİHİSAR", "DİKİLİ", "AKHİSAR", "SALİHLİ", "TURGUTLU", "SOMA",
    "ALAŞEHİR", "KULA", "SARIGÖL", "DEMİRCİ", "GÖRDES", "KIRKAĞAÇ",
    "NAZİLLİ", "SÖKE", "KUŞADASI", "DİDİM", "ÇİNE", "GERMENCİK",
    "BODRUM", "FETHİYE", "MARMARİS", "MİLAS", "DATÇA", "KÖYCEĞİZ", "ORTACA",
    "YATAĞAN", "SEYDİKEMER", "ÇİVRİL", "TAVAS", "ACIPAYAM", "SARAYKÖY", "BULDAN",
    # Antalya / Isparta / Burdur
    "ALANYA", "MANAVGAT", "SERİK", "KAŞ", "KUMLUCA", "KORKUTELİ", "GAZİPAŞA",
    "ELMALI", "FİNİKE", "YALVAÇ", "EĞİRDİR", "ŞARKİKARAAĞAÇ", "SENİRKENT",
    "GÖLHİSAR", "TEFENNİ", "KEMER", "BUCAK",
    # İç Anadolu
    "POLATLI", "ÇUBUK", "ŞEREFLİKOÇHİSAR", "BEYPAZARI", "KIZILCAHAMAM",
    "HAYMANA", "NALLIHAN", "ELMADAĞ", "KALECİK", "SİNCAN", "GÖLBAŞI",
    "KESKİN", "EREĞLİ", "AKŞEHİR", "ÇUMRA", "BEYŞEHİR", "SEYDİŞEHİR", "ILGIN",
    "KULU", "CİHANBEYLİ", "KARAPINAR", "DEVELİ", "BÜNYAN", "YAHYALI",
    "PINARBAŞI", "ÜRGÜP", "AVANOS", "GÜLŞEHİR", "DERİNKUYU", "ERMENEK",
    "KAMAN", "MUCUR", "SORGUN", "YERKÖY", "BOĞAZLIYAN", "AKDAĞMADENİ",
    "SUNGURLU", "OSMANCIK", "İSKİLİP", "SİVRİHİSAR", "ÇİFTELER", "ÇEKEREK",
    "BAYAT",
    # Ege/İç Batı
    "SANDIKLI", "DİNAR", "BOLVADİN", "EMİRDAĞ", "ŞUHUT", "TAVŞANLI", "SİMAV",
    "GEDİZ", "EMET", "BANAZ", "EŞME", "SİVASLI", "ALTINTAŞ",
    # Karadeniz
    "BAFRA", "ÇARŞAMBA", "VEZİRKÖPRÜ", "TERME", "ALAÇAM", "AKÇAABAT",
    "VAKFIKEBİR", "ARAKLI", "SÜRMENE", "MAÇKA", "ÜNYE", "FATSA", "BULANCAK",
    "ÇAYKARA", "ESPİYE",
    "ŞEBİNKARAHİSAR", "TİREBOLU", "GÖRELE", "TOSYA", "TAŞKÖPRÜ", "İNEBOLU",
    "CİDE", "DEVREKANİ", "SAFRANBOLU", "ÇAYCUMA", "DEVREK", "ALAPLI",
    "BOYABAT", "GERZE", "AYANCIK", "DURAĞAN", "AMASRA", "AKÇAKOCA",
    "GEREDE", "MUDURNU", "GÖYNÜK", "MERZİFON", "SULUOVA", "TAŞOVA",
    "GÜMÜŞHACIKÖY", "TURHAL", "ERBAA", "NİKSAR", "ZİLE", "REŞADİYE",
    "ÇAYELİ", "ARDEŞEN", "FINDIKLI", "HOPA", "ARHAVİ", "BORÇKA", "YUSUFELİ",
    "ŞAVŞAT", "KELKİT", "ŞİRAN",
    # Doğu / Güneydoğu
    "TATVAN", "AHLAT", "ERCİŞ", "ÖZALP", "MURADİYE", "BAŞKALE", "ÇALDIRAN",
    "ERGANİ", "BİSMİL", "SİLVAN", "ÇERMİK", "SİVEREK", "VİRANŞEHİR",
    "BİRECİK", "SURUÇ", "AKÇAKALE", "CEYLANPINAR", "HALFETİ", "BOZOVA",
    "NİZİP", "İSLAHİYE", "DOĞANŞEHİR", "KOVANCILAR", "OLTU", "HORASAN",
    "PASİNLER", "İSPİR", "TORTUM", "KAĞIZMAN", "SARIKAMIŞ", "DOĞUBAYAZIT",
    "PATNOS", "ELEŞKİRT", "TUTAK", "BULANIK", "MALAZGİRT", "VARTO",
    "KOZLUK", "KURTALAN", "KIZILTEPE", "MİDYAT", "NUSAYBİN", "DERİK",
    "CİZRE", "SİLOPİ", "YÜKSEKOVA", "ŞEMDİNLİ", "SOLHAN", "TERCAN", "GÖLE",
    "HINIS", "KARAYAZI", "LİCE", "NURDAĞI",
    # Akdeniz / Çukurova
    "CEYHAN", "KOZAN", "KARAİSALI", "KARATAŞ", "TARSUS", "SİLİFKE", "ANAMUR",
    "ERDEMLİ", "MUT", "GÜLNAR", "İSKENDERUN", "DÖRTYOL", "REYHANLI",
    "KIRIKHAN", "SAMANDAĞ", "ERZİN", "YAYLADAĞI", "ALTINÖZÜ", "KAHTA",
    "BESNİ", "ELBİSTAN", "AFŞİN", "PAZARCIK", "TÜRKOĞLU", "GÖKSUN",
    "KADİRLİ", "DÜZİÇİ", "ANDIRIN", "İMAMOĞLU",
    # Trakya
    "ÇORLU", "ÇERKEZKÖY", "MALKARA", "HAYRABOLU", "MURATLI", "ŞARKÖY",
    "KEŞAN", "UZUNKÖPRÜ", "İPSALA", "LÜLEBURGAZ", "BABAESKİ", "VİZE",
    "PINARHİSAR",
    # Sivas / Erzincan çevresi
    "ŞARKIŞLA", "SUŞEHRİ", "GEMEREK", "ZARA", "DİVRİĞİ", "KANGAL",
)


# ---------------------------------------------------------------------------
# Yapısal kimlik
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CourtName:
    """Mahkeme adının doğrulanmış bileşenleri.

    `tur_yuzey`/`daire_yuzey` metindeki YAZILIŞI korur (görüntüleme ve geri uyum
    için); `tur_kanonik`/`daire_adi`/`daire_no` kimliği taşır (arama, gruplama,
    mükerrer tespiti). `ham`, kimliğin okunduğu metin parçasıdır.
    """

    ham: str
    yer: str | None
    sira: int | None
    tur_yuzey: str | None
    tur_kanonik: str | None
    daire_no: int | None
    daire_adi: str | None
    daire_yuzey: str | None
    guven: str

    def duz_ad(self) -> str:
        """Bileşenleri tek satırlık mahkeme adına çevirir (uydurma parça eklemez)."""
        parcalar: list[str] = []
        if self.yer:
            parcalar.append(self.yer)
        if self.sira is not None:
            parcalar.append(f"{self.sira}.")
        if self.tur_yuzey:
            parcalar.append(self.tur_yuzey)
        if self.daire_yuzey:
            parcalar.append(self.daire_yuzey)
        return " ".join(parcalar)


# ---------------------------------------------------------------------------
# Derlenmiş yardımcılar
# ---------------------------------------------------------------------------
# Kanonik tür çapaları: judicial_unit.PATTERNS'ten OKUNUR (kopya değil).
_TUR_CAPALARI: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rx), ad) for rx, ad, _parent in PATTERNS
]

_SOZEL_ALT = "|".join(re.escape(s) for s in sorted(SOZEL_SIRA, key=len, reverse=True))

# Daire yan cümlesi: "12. HUKUK DAİRESİ" / "ÜÇÜNCÜ İDARİ DAVA DAİRESİ" / "43. HD"
_DAIRE_GOVDE = (
    rf"(?:(?P<no>\d+)\s*\.|(?P<sozel>{_SOZEL_ALT}){_SINIR_SONRA})\s*"
    rf"(?P<ad>(?:{_KELIME}\s+){{0,2}}(?:DAİRESİ|DAİRELERİ)|HD|CD){_SINIR_SONRA}"
)
_DAIRE_RE = re.compile(_DAIRE_GOVDE)
_DAIRE_BAS_RE = re.compile(rf"\s*{_DAIRE_GOVDE}")

_UST_RE = re.compile(
    _SINIR_ONCE
    + "(?:"
    + "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in UST_MAHKEMELER)
    + ")"
    + _SINIR_SONRA
)

_TUR_SON_RE = re.compile(rf"\s*{_TUR_SON}{_SINIR_SONRA}")
# Genel yolda YALNIZ kurum soneki aranır; adın solu `_yuzey_geriye_yur` ile
# kelime kelime açılır. Açgözlü çok kelimeli bir kalıp, tanınmayan yeri tür
# adının içine yutardı ("İSTANBUL BÖLGE ADLİYE MAHKEMESİ" tek parça olurdu).
_GENEL_TUR_RE = re.compile(rf"{_SINIR_ONCE}{_MAHKEME_SON}{_SINIR_SONRA}")
_SIRA_RE = re.compile(r"(\d+)\s*\.\s*$")
# Yer ile mahkeme arasında KALMASINA izin verilen dolgu (harf taşımaz).
_BOS_GECIS_RE = re.compile(r"[\s\d./,()\-:'’|]*")
_GECIS_ISTISNA = ("ADLİYESİ",)


def _bosluk_sadelestir(metin: str) -> str:
    return re.sub(r"\s+", " ", metin).strip()


@lru_cache(maxsize=32)
def _yer_regex(adaylar: tuple[str, ...]) -> re.Pattern[str] | None:
    if not adaylar:
        return None
    sirali = sorted(adaylar, key=len, reverse=True)
    alt = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in sirali)
    return re.compile(_SINIR_ONCE + "(?:" + alt + ")" + _SINIR_SONRA)


@lru_cache(maxsize=32)
def _yer_adaylari(yerler: tuple[str, ...]) -> tuple[str, ...]:
    """Çağıranın verdiği il listesi + modüldeki yargı yeri sözlüğü."""
    temiz: set[str] = set()
    for ad in yerler:
        norm = _bosluk_sadelestir(turkish_upper(ad or ""))
        if len(norm) >= 3:
            temiz.add(norm)
    temiz.update(YARGI_YERLERI)
    temiz.update(BILESIK_YARGI_YERLERI)
    return tuple(sorted(temiz))


@lru_cache(maxsize=32)
def _tur_regex(turler: tuple[str, ...]) -> re.Pattern[str] | None:
    """Çağıranın verdiği tür ADLARI için yüzey eşleştiricisi (kanonikleştirme DEĞİL)."""
    temiz = {
        _bosluk_sadelestir(turkish_upper(t or ""))
        for t in turler
        if t and len(t.strip()) >= 3
    }
    if not temiz:
        return None
    sirali = sorted(temiz, key=len, reverse=True)
    alt = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in sirali)
    return re.compile(_SINIR_ONCE + "(?:" + alt + ")" + _SINIR_SONRA)


def _kelime_basi(metin: str, i: int) -> int:
    while i > 0 and re.match(rf"[{TR_HARF}]", metin[i - 1]):
        i -= 1
    return i


def _kelime_sonu(metin: str, i: int) -> int:
    while i < len(metin) and re.match(rf"[{TR_HARF}]", metin[i]):
        i += 1
    return i


def _daire_coz(eslesme: re.Match[str]) -> tuple[int | None, str, str]:
    """(daire_no, daire_adi, daire_yuzey) — kısaltmalar kanonik ada açılır."""
    no_txt = eslesme.group("no")
    sozel = eslesme.group("sozel")
    no: int | None = None
    if no_txt:
        no = int(no_txt)
    elif sozel:
        no = SOZEL_SIRA.get(_bosluk_sadelestir(sozel))

    ad = _bosluk_sadelestir(eslesme.group("ad") or "")
    if ad == "HD":
        ad = "HUKUK DAİRESİ"
    elif ad == "CD":
        ad = "CEZA DAİRESİ"
    return no, ad, _bosluk_sadelestir(eslesme.group(0))


def _tur_capasi(norm: str) -> tuple[int, int, str] | None:
    """judicial_unit kalıplarından EN SOLDAKİ eşleşmenin (baş, son, kanonik) üçlüsü.

    Kalıplar normalize edilmiş metinde aranır; normalize_court karakter-karakter
    çalıştığı için (boşluk zaten sadeleştirilmiş) indisler ham metinle örtüşür.
    Örtüşmezse çapa kullanılmaz — yanlış kesme yapmaktansa genel yola düşülür.
    """
    jnorm = normalize_court(norm)
    if len(jnorm) != len(norm):
        return None
    en_iyi: tuple[int, int, str] | None = None
    for rx, ad in _TUR_CAPALARI:
        m = rx.search(jnorm)
        if m and (en_iyi is None or m.start() < en_iyi[0]):
            en_iyi = (m.start(), m.end(), ad)
    return en_iyi


def _yer_bul(onek: str, adaylar: tuple[str, ...]) -> str | None:
    """Öneğin SONUNA en yakın doğrulanmış yeri döner; arada harf varsa vazgeçer."""
    rx = _yer_regex(adaylar)
    if rx is None:
        return None
    son: re.Match[str] | None = None
    for m in rx.finditer(onek):
        son = m
    if son is None:
        return None
    gecis = onek[son.end():]
    for istisna in _GECIS_ISTISNA:
        gecis = gecis.replace(istisna, " ")
    if not _BOS_GECIS_RE.fullmatch(gecis):
        return None
    return _bosluk_sadelestir(son.group(0))


def _sira_ve_yer(onek: str, adaylar: tuple[str, ...]) -> tuple[int | None, str | None]:
    m = _SIRA_RE.search(onek)
    sira = int(m.group(1)) if m else None
    kalan = onek[: m.start()] if m else onek
    return sira, _yer_bul(kalan, adaylar)


def _guven(yer: str | None, kanonik: str | None) -> str:
    if not kanonik:
        return GUVEN_YOK
    return GUVEN_TAM if yer else GUVEN_KISMI


def _ust_mahkeme(norm: str, capa_bas: int | None) -> CourtName | None:
    """Üst mahkeme kimliği — yer gerektirmez, daire satır sonu de İSTEMEZ."""
    m = _UST_RE.search(norm)
    if not m:
        return None
    if capa_bas is not None and capa_bas < m.start():
        return None  # daha solda gerçek bir mahkeme var; üst mahkeme atıftır

    kurum = _bosluk_sadelestir(m.group(0))
    son = m.end()
    daire_no: int | None = None
    daire_adi: str | None = None
    daire_yuzey: str | None = None
    dm = _DAIRE_BAS_RE.match(norm, son)
    if dm:
        daire_no, daire_adi, daire_yuzey = _daire_coz(dm)
        son = dm.end()

    return CourtName(
        ham=_bosluk_sadelestir(norm[m.start():son]),
        yer=None,
        sira=None,
        tur_yuzey=kurum,
        tur_kanonik=kurum,
        daire_no=daire_no,
        daire_adi=daire_adi,
        daire_yuzey=daire_yuzey,
        # Üst mahkeme yer GEREKTİRMEZ; yer alanı boş kaldığı için damga KISMI'dir
        # (TAM yalnız yer + tür birlikte doğrulandığında verilir).
        guven=_guven(None, kurum),
    )


def _yuzey_geriye_yur(norm: str, bas: int, adaylar: tuple[str, ...]) -> int:
    """Genel yolda tür yüzeyini sola doğru en çok 3 kelime genişletir.

    Doğrulanmış bir yere ya da harf olmayan bir sınıra çarpınca durur — böylece
    tanınmayan yer tür adının içine sızsa bile yer alanına GEÇMEZ.
    """
    yer_kumesi = set(adaylar)
    i = bas
    for _ in range(3):
        j = i
        while j > 0 and norm[j - 1] == " ":
            j -= 1
        k = _kelime_basi(norm, j)
        if k == j:
            break
        kelime = norm[k:j]
        if kelime in yer_kumesi:
            break
        i = k
    return i


def parse_court_name(
    metin: str,
    *,
    yerler: Sequence[str] = (),
    turler: Sequence[str] = (),
) -> CourtName | None:
    """Serbest metinden/addan yapısal mahkeme kimliği çıkarır.

    Args:
        metin: mahkeme adı ya da adı içeren metin parçası (büyük/küçük harf farketmez).
        yerler: çağıranın verdiği resmi il listesi (DynamicConfig `cities` ya da fallback).
        turler: çağıranın verdiği mahkeme türü ADLARI — yalnız YÜZEY eşleştirmesinde
            kullanılır; kanonik değer daima judicial_unit'ten okunur.

    Returns:
        `CourtName` ya da hiçbir mahkeme izi yoksa None. Güveni `GUVEN_YOK` olan
        sonuç "tür bile doğrulanamadı" demektir; kimlik olarak KULLANILMAMALIDIR.
    """
    if not metin:
        return None
    norm = _bosluk_sadelestir(turkish_upper(metin))
    if not norm:
        return None

    adaylar = _yer_adaylari(tuple(yerler))
    capa = _tur_capasi(norm)

    ust = _ust_mahkeme(norm, capa[0] if capa else None)
    if ust is not None:
        return ust

    bas: int
    son: int
    if capa is not None:
        bas, son = _kelime_basi(norm, capa[0]), _kelime_sonu(norm, capa[1])
    else:
        yuzey_rx = _tur_regex(tuple(turler))
        m = yuzey_rx.search(norm) if yuzey_rx else None
        if m is None:
            m = _GENEL_TUR_RE.search(norm)
        if m is None:
            return None
        bas = _yuzey_geriye_yur(norm, m.start(), adaylar)
        son = m.end()

    # Kurum soneki hemen sağdaysa yüzeye dahil et ("TÜKETİCİ" + " MAHKEMESİ")
    sonek = _TUR_SON_RE.match(norm, son)
    if sonek:
        son = sonek.end()

    # Daire: önce çapanın İÇİNDE ara (BAM kalıbı daireyi de yutar), sonra sağında
    daire_no: int | None = None
    daire_adi: str | None = None
    daire_yuzey: str | None = None
    ic = _DAIRE_RE.search(norm, bas, son)
    if ic:
        daire_no, daire_adi, daire_yuzey = _daire_coz(ic)
        tur_yuzey = _bosluk_sadelestir(norm[bas:ic.start()])
        kimlik_son = son
    else:
        tur_yuzey = _bosluk_sadelestir(norm[bas:son])
        kimlik_son = son
        dis = _DAIRE_BAS_RE.match(norm, son)
        if dis:
            daire_no, daire_adi, daire_yuzey = _daire_coz(dis)
            kimlik_son = dis.end()

    if not tur_yuzey:
        return None

    sira, yer = _sira_ve_yer(norm[:bas], adaylar)
    kanonik = derive_judicial_unit(f"{tur_yuzey} {daire_adi or ''}".strip())
    kimlik_bas = bas
    if yer:
        yer_bas = norm.rfind(yer, 0, bas)
        if yer_bas >= 0:
            kimlik_bas = yer_bas

    return CourtName(
        ham=_bosluk_sadelestir(norm[kimlik_bas:kimlik_son]),
        yer=yer,
        sira=sira,
        tur_yuzey=tur_yuzey,
        tur_kanonik=kanonik,
        daire_no=daire_no,
        daire_adi=daire_adi,
        daire_yuzey=daire_yuzey,
        guven=_guven(yer, kanonik),
    )


def bilinen_yer(ad: str, yerler: Iterable[str] = ()) -> bool:
    """Verilen metnin tamamı doğrulanmış bir yer mi (test/çağıran kolaylığı)."""
    norm = _bosluk_sadelestir(turkish_upper(ad or ""))
    if not norm:
        return False
    return norm in set(_yer_adaylari(tuple(yerler)))
