"""
court_extractor.py
------------------
Türk hukuki belgelerinden mahkeme adını tespit eden hibrit modül.

Strateji:
  1. HEADER REGEX  — İlk 20 satır; en güvenilir (T.C. başlığı altında)
  2. BODY REGEX    — "Hüküm veren … mahkemesi" / "karar veren" kalıpları
  Başarısız olursa None döner → LLM prompt'una bırakılır.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Türk mahkeme türleri — önce uzun olanlar kontrol edilmeli (greedy match)
# ---------------------------------------------------------------------------
MAHKEME_TURLERI = [
    # Bölge / Üst
    r"BÖLGE\s+ADLİYE\s+MAHKEMESİ",
    r"BÖLGE\s+İDARE\s+MAHKEMESİ",
    r"BÖLGE\s+ADLİYE\s+MAHKEMESİ",
    # Yargıtay / Danıştay
    r"YARGITAY",
    r"DANIŞTAY",
    r"ANAYASA\s+MAHKEMESİ",
    r"UYUŞMAZLIK\s+MAHKEMESİ",
    # Hukuk
    r"ASLİYE\s+HUKUK\s+MAHKEMESİ",
    r"ASLİYE\s+TİCARET\s+MAHKEMESİ",
    r"SULH\s+HUKUK\s+MAHKEMESİ",
    r"TÜKETİCİ\s+MAHKEMESİ",
    r"AİLE\s+MAHKEMESİ",
    r"İŞ\s+MAHKEMESİ",
    r"FİKRİ\s+VE\s+SINAİ\s+HAKLAR\s+(?:HUKUK\s+)?MAHKEMESİ",
    r"KADASTRO\s+MAHKEMESİ",
    r"İCRA\s+HUKUK\s+MAHKEMESİ",
    # Ceza
    r"AĞIR\s+CEZA\s+MAHKEMESİ",
    r"ASLİYE\s+CEZA\s+MAHKEMESİ",
    r"SULH\s+CEZA\s+(?:MAHKEMESİ|HÂKİMLİĞİ|HAKİMLİĞİ)",
    r"ÇOCUK\s+(?:AĞIR\s+CEZA\s+)?MAHKEMESİ",
    r"(?:MİLLİ\s+)?GÜVENLİK\s+MAHKEMESİ",
    # İdare
    r"İDARE\s+MAHKEMESİ",
    r"VERGİ\s+MAHKEMESİ",
    # Genel
    r"MAHKEMESİ",          # fallback
]

# Türkçe sıra sayıları (daire numarası sözel olarak yazılabilir)
TURKISH_ORDINALS = [
    "BİRİNCİ", "İKİNCİ", "ÜÇÜNCÜ", "DÖRDÜNCÜ", "BEŞİNCİ",
    "ALTINCI", "YEDİNCİ", "SEKİZİNCİ", "DOKUZUNCU", "ONUNCU",
    "ON BİRİNCİ", "ON İKİNCİ", "ON ÜÇÜNCÜ", "ON DÖRDÜNCÜ", "ON BEŞİNCİ",
    "ON ALTINCI", "ON YEDİNCİ", "ON SEKİZİNCİ", "ON DOKUZUNCU", "YİRMİNCİ",
]

# Türkçe karakterler dahil büyük harf sınıfı
TR_UPPER = r"[A-ZÇĞİIÖŞÜ]"

# Daire/bölüm eklentileri — hem rakam ("10.") hem Türkçe sözel ("ÜÇÜNCÜ") destekli
DAIRE_PATTERN = rf"""
    (?:                                    # bölüm/daire eki (opsiyonel)
      \s*[\n\r]*\s*                        # olası satır sonu
      (?:                                  # numara bölümü
        \d+\.                             # rakam: "3.", "10."
        |(?:{'|'.join(TURKISH_ORDINALS)})  # sözel: "ÜÇÜNCÜ", "BİRİNCİ" vb.
        |{TR_UPPER}+\.?                    # Roma rakamı veya diğer: "XI."
      )
      \s*
      (?:{TR_UPPER}+\s+)?                  # opsiyonel sıfat: "İDARİ ", "HUKUK " vb.
      (?:{TR_UPPER}+\s+)?                  # ikinci sıfat: "DAVA "
      DAİRESİ
    )?
"""

# Türkçe il adları (kısa liste — UTF-8 büyük harf)
ILLER = [
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

# İlçe mahkemesi için tam regex (örn: "Bursa 5. Asliye Hukuk Mahkemesi")
def _build_full_pattern() -> re.Pattern:
    il_alt = "|".join(re.escape(il) for il in ILLER)
    turu_alt = "|".join(MAHKEME_TURLERI)
    pattern = rf"""
        (?P<il>{il_alt})          # İl adı (ör: ANKARA)
        (?:\s+(?P<sira>\d+)\.)?   # Sıra numarası (ör: 10.) — opsiyonel
        \s+
        (?P<tur>{turu_alt})       # Mahkeme türü
        {DAIRE_PATTERN}           # Daire (ör: 3. Hukuk Dairesi) — opsiyonel
    """
    return re.compile(pattern, re.VERBOSE | re.IGNORECASE)


_FULL_PATTERN = _build_full_pattern()

# ---------------------------------------------------------------------------
# Katman 1: Header regex (ilk 20 satır)
# ---------------------------------------------------------------------------
_HEADER_LINES = 20

def _extract_from_header(text: str) -> str | None:
    """
    T.C. başlığının altındaki yapıyı tarar.
    Tipik format:
        T.C.
        [İL]
        [MAHKEME TÜRÜ]
        [DAİRE] (opsiyonel — rakam veya Türkçe sözel sıra sayısı)
    """
    lines = text.splitlines()
    header_lines = lines[:_HEADER_LINES]
    header_text = "\n".join(header_lines).upper()

    # Üst mahkemeler (şehir gerektirmeyen)
    for keyword in ["YARGITAY", "DANIŞTAY", "ANAYASA MAHKEMESİ", "UYUŞMAZLIK MAHKEMESİ"]:
        if keyword in header_text:
            daire_m = re.search(
                rf"{re.escape(keyword)}\s*[\n\r]+\s*(\d+)\.\s*((?:HUKUK|CEZA|İDARİ)?\s*DAİRESİ)",
                header_text
            )
            if daire_m:
                return f"{keyword} {daire_m.group(1)}. {daire_m.group(2).strip()}"
            return keyword

    # İl + Mahkeme türü + sıra numarası
    match = _FULL_PATTERN.search(header_text)
    if match:
        court_base = _format_match(match)
        
        # Dairenin sonraki satırda olup olmadığını ayrıca kontrol et
        # (Regex bazen aynı satırda arayıp kaçırabilir)
        if "DAİRESİ" in header_text and "DAİRESİ" not in match.group(0):
            daire_m = _find_daire_after(header_text, match.end())
            if daire_m:
                return f"{court_base} {daire_m}"
        return court_base

    return None


def _find_daire_after(text: str, start_pos: int) -> str | None:
    """
    Mahkeme adından sonra gelen DAİRE bilgisini bulur.
    Hem rakamsal (3.) hem sözel (ÜÇÜNCÜ) sıra sayısı desteklenir.
    """
    ordinal_alt = "|".join(re.escape(o) for o in TURKISH_ORDINALS)
    pattern = re.compile(
        rf"(?:(\d+)\.\s*|({ordinal_alt})\s+)"  # numara
        rf"([A-ZÇĞİIÖŞÜ]+\s+)*"               # sıfatlar (İDARİ, HUKUK, DAVA vb.)
        rf"DAİRESİ",
        re.IGNORECASE
    )
    remaining = text[start_pos:]
    m = pattern.search(remaining)
    if not m:
        return None
    
    # Hangi grup eşleşti?
    num = m.group(1)      # rakam (örn: "3")
    word = m.group(2)     # sözel (örn: "ÜÇÜNCÜ")
    raw = m.group(0).strip()
    
    # Title-case düzelt
    raw_title = raw.title().replace("I ", "I ")  # Türkçe title
    return raw_title


# ---------------------------------------------------------------------------
# Katman 2: Body regex ("hüküm veren / karar veren" kalıpları)
# ---------------------------------------------------------------------------
_VERDICT_PHRASES = [
    r"hüküm\s+veren\s+(.{5,80}?mahkeme(?:si|ği)?)",
    r"karar\s+veren\s+(.{5,80}?mahkeme(?:si|ği)?)",
    r"mahkemece\s+verilen\s+karar",         # basit işaret
    r"(.{5,80}?mahkeme(?:si|ği)?)'nce\s+verilen",
    r"(.{5,80}?mahkeme(?:si|ği)?)\s+tarafından",
]

def _extract_from_body(text: str) -> str | None:
    upper = text.upper()

    for phrase in _VERDICT_PHRASES:
        m = re.search(phrase, upper, re.IGNORECASE)
        if m:
            candidate = m.group(1) if m.lastindex else ""
            # Extracted string içinde mahkeme türü var mı?
            type_m = _FULL_PATTERN.search(candidate)
            if type_m:
                return _format_match(type_m)
            # Üst mahkeme mi?
            for kw in ["YARGITAY", "DANIŞTAY", "ANAYASA MAHKEMESİ"]:
                if kw in candidate:
                    return kw

    return None


# ---------------------------------------------------------------------------
# Yardımcı: match nesnesini temiz stringe çevir
# ---------------------------------------------------------------------------
def _format_match(match: re.Match) -> str:
    il   = (match.group("il")   or "").strip().upper()
    sira = (match.group("sira") or "").strip()
    tur  = (match.group("tur")  or "").strip().upper()

    parts = [il]
    if sira:
        parts.append(f"{sira}.")
    parts.append(tur)

    # Daire bilgisini bütün match içinden ayıkla (Hem rakamsal hem sözel destekli)
    full_str = match.group(0).upper()
    
    # 1. Rakamsal kontrol (örn: "3. HUKUK DAİRESİ")
    daire_rakam = re.search(r"(\d+)\.\s*([A-ZÇĞİIÖŞÜ]+\s+)*DAİRESİ", full_str, re.IGNORECASE)
    if daire_rakam:
        parts.append(daire_rakam.group(0).strip().upper())
    else:
        # 2. Sözel kontrol (örn: "ÜÇÜNCÜ İDARİ DAVA DAİRESİ")
        ordinal_alt = "|".join(TURKISH_ORDINALS)
        daire_sozel = re.search(rf"({ordinal_alt})\s+([A-ZÇĞİIÖŞÜ]+\s+)*DAİRESİ", full_str, re.IGNORECASE)
        if daire_sozel:
            parts.append(daire_sozel.group(0).strip().upper())

    return " ".join(p for p in parts if p).upper()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def find_court_name(text: str) -> str | None:
    """
    Belgeden mahkeme adını tespit eder.
    
    Returns:
        Temiz mahkeme adı (örn: "Ankara Bölge İdare Mahkemesi 10. İdari Dava Dairesi")
        veya None (bulunamazsa — LLM'e bırakılacak).
    """
    if not text or len(text) < 20:
        return None

    # Katman 1: Header
    result = _extract_from_header(text)
    if result:
        logger.info(f"🏛️ [COURT] Header regex ile bulundu: {result}")
        return result

    # Katman 2: Body bağlamsal
    result = _extract_from_body(text)
    if result:
        logger.info(f"🏛️ [COURT] Body regex ile bulundu: {result}")
        return result

    logger.info("🏛️ [COURT] Bulunamadı — LLM'e bırakılıyor.")
    return None
