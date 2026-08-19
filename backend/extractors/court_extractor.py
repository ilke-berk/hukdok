"""
court_extractor.py
------------------
Türk hukuki belgelerinden mahkeme adını tespit eden hibrit modül.

Strateji:
  1. HEADER  — İlk 20 satır; en güvenilir (T.C. başlığı altında)
  2. BODY    — "Hüküm veren … mahkemesi" / "karar veren" kalıpları
  Başarısız olursa None döner → LLM prompt'una bırakılır.

İki katmanın da AYRIŞTIRMASI `services/court_name.py` kapısında yapılır (G067):
bu modül yalnız ADAY METNİ seçer, kimliği kapı üretir. Yer/tür doğrulaması,
kelime sınırı ve daire okuması orada tek yerde tanımlıdır.

Mahkeme türleri ve il listesi DynamicConfig üzerinden DB'den okunur.
DB boşsa _FALLBACK_ILLER + judicial_unit'in kanonik tür adları devreye girer.
"""

import re
import logging

from services.court_name import CourtName, parse_court_name
from services.judicial_unit import PATTERNS
from text_utils import turkish_upper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback listesi — DynamicConfig boş/erişilemezse kullanılır
# ---------------------------------------------------------------------------
_FALLBACK_ILLER = [
    "ADANA","ADIYAMAN","AFYONKARAHİSAR","AĞRI","AKSARAY","AMASYA","ANKARA","ANTALYA",
    "ARDAHAN","ARTVİN","AYDIN","BALIKESİR","BARTIN","BATMAN","BAYBURT","BİLECİK",
    "BİNGÖL","BİTLİS","BOLU","BURDUR","BURSA","ÇANAKKALE","ÇANKIRI","ÇORUM",
    "DENİZLİ","DİYARBAKIR","DÜZCE","EDİRNE","ELAZIĞ","ERZİNCAN","ERZURUM","ESKİŞEHİR",
    "GAZİANTEP","GİRESUN","GÜMÜŞHANE","HAKKARİ","HATAY","IĞDIR","ISPARTA","İSTANBUL",
    "İZMİR","KAHRAMANMARAŞ","KARABÜK","KARAMAN","KARS","KASTAMONU","KAYSERİ",
    "KİLİS","KIRIKKALE","KIRKLARELİ","KIRŞEHİR","KOCAELİ","KONYA","KÜTAHYA",
    "MALATYA","MANİSA","MARDİN","MERSİN","MUĞLA","MUŞ","NEVŞEHİR","NİĞDE",
    "ORDU","OSMANİYE","RİZE","SAKARYA","SAMSUN","SİİRT","SİNOP","SİVAS",
    "ŞANLIURFA","ŞIRNAK","TEKİRDAĞ","TOKAT","TRABZON","TUNCELİ","UŞAK",
    "VAN","YALOVA","YOZGAT","ZONGULDAK",
]

# Tür adlarının İKİNCİ bir kopyası tutulmaz: fallback'te de kanonik sözlük
# (judicial_unit.PATTERNS) tek kaynaktır.
_FALLBACK_TUR_ADLARI = tuple(ad for _rx, ad, _parent in PATTERNS)

# ---------------------------------------------------------------------------
# DynamicConfig listelerinin süreç-içi kopyası (config değişince yenilenir)
# ---------------------------------------------------------------------------
_pattern_cache: "tuple[tuple[str, ...], tuple[str, ...]] | None" = None
_pattern_cache_key: tuple | None = None


def _config_listeleri() -> "tuple[tuple[str, ...], tuple[str, ...]]":
    """(yerler, turler) — DynamicConfig'den okur, boş/erişilemezse fallback'e düşer."""
    global _pattern_cache, _pattern_cache_key

    court_names: list[str] = []
    city_names: list[str] = []
    try:
        from managers.config_manager import DynamicConfig
        config = DynamicConfig()
        court_names = [ct["name"] for ct in config.get_court_types() if ct.get("name")]
        city_names = [c["name"] for c in config.get_cities() if c.get("name")]
    except Exception:
        pass  # Fallback'e düşer

    cache_key = (tuple(court_names), tuple(city_names))
    if _pattern_cache is not None and _pattern_cache_key == cache_key:
        return _pattern_cache

    yerler = tuple(city_names) if city_names else tuple(_FALLBACK_ILLER)
    turler = tuple(court_names) if court_names else _FALLBACK_TUR_ADLARI
    _pattern_cache = (yerler, turler)
    _pattern_cache_key = cache_key
    logger.debug(f"[COURT] Liste kaynağı yenilendi ({len(turler)} tür, {len(yerler)} yer).")
    return _pattern_cache


def _coz(aday: str) -> CourtName | None:
    yerler, turler = _config_listeleri()
    return parse_court_name(aday, yerler=yerler, turler=turler)


# ---------------------------------------------------------------------------
# Katman 1: Header (ilk 20 satır)
# ---------------------------------------------------------------------------
_HEADER_LINES = 20


def _extract_from_header(text: str) -> CourtName | None:
    """T.C. başlığının altındaki yapıyı tarar (İL / MAHKEME TÜRÜ / DAİRE)."""
    # str.upper() değil turkish_upper: "mahkemesi".upper() → "MAHKEMESI" (İ'siz)
    # olur ve kalıplardaki MAHKEMESİ ile eşleşmez (IGNORECASE de kurtarmaz).
    header_text = turkish_upper("\n".join(text.splitlines()[:_HEADER_LINES]))
    return _coz(header_text)


# ---------------------------------------------------------------------------
# Katman 2: Body regex ("hüküm veren / karar veren" kalıpları)
# ---------------------------------------------------------------------------
# Kalıplar BÜYÜK harf: metin turkish_upper ile büyütülür ve Python re'nin
# IGNORECASE'i 'i' ↔ 'İ' çiftini eşleyemez ("mahkemesi" kalıbı "MAHKEMESİ"
# metnini yakalayamıyordu — body katmanı fiilen hiç çalışmıyordu).
_VERDICT_PHRASES = [
    r"HÜKÜM\s+VEREN\s+(.{5,80}?MAHKEME(?:Sİ|Ğİ)?)",
    r"KARAR\s+VEREN\s+(.{5,80}?MAHKEME(?:Sİ|Ğİ)?)",
    r"(.{5,80}?MAHKEME(?:Sİ|Ğİ)?)'NCE\s+VERİLEN",
    r"(.{5,80}?MAHKEME(?:Sİ|Ğİ)?)\s+TARAFINDAN",
]


def _extract_from_body(text: str) -> CourtName | None:
    upper = turkish_upper(text)  # str.upper() Türkçe i→İ dönüşümünü yapmaz
    for phrase in _VERDICT_PHRASES:
        m = re.search(phrase, upper)
        if not m or not m.lastindex:
            continue
        sonuc = _coz(m.group(1))
        if sonuc is not None:
            return sonuc
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def find_court_identity(text: str) -> CourtName | None:
    """Belgeden YAPISAL mahkeme kimliğini çıkarır (yer · sıra · tür · daire · güven).

    `find_court_name`'in yapısal ikizi: güven damgasına bakması gereken çağıranlar
    (analiz hattının çapraz kontrolü) bunu kullanır.
    """
    if not text or len(text) < 20:
        return None

    for katman, cikar in (("Header", _extract_from_header), ("Body", _extract_from_body)):
        sonuc = cikar(text)
        if sonuc is not None and sonuc.duz_ad():
            logger.info(f"[COURT] {katman} ile bulundu: {sonuc.duz_ad()} (güven={sonuc.guven})")
            return sonuc

    logger.info("[COURT] Bulunamadı — LLM'e bırakılıyor.")
    return None


def find_court_name(text: str) -> str | None:
    """
    Belgeden mahkeme adını tespit eder.

    Returns:
        Temiz mahkeme adı (örn: "ANKARA BÖLGE İDARE MAHKEMESİ 10. İDARİ DAVA DAİRESİ")
        veya None (bulunamazsa — LLM'e bırakılacak).
    """
    sonuc = find_court_identity(text)
    return sonuc.duz_ad() if sonuc is not None else None
