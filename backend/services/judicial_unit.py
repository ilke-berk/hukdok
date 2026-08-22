"""Mahkeme adından Yargı Birimi (judicial_unit) türetme — tek kaynak.

scripts/backfill_judicial_unit.py (eski kayıtların geriye dönük doldurması) ve
sihirbaz merge akışı (routes/case_intake) aynı kalıpları buradan kullanır.
Saf modül: DB/dosya erişimi yok.
"""

import re


def normalize_court(s: str) -> str:
    s = (s or "").replace("ı", "i").replace("İ", "I")
    s = (s.replace("ğ", "g").replace("Ğ", "G").replace("ü", "u").replace("Ü", "U")
          .replace("ş", "s").replace("Ş", "S").replace("ö", "o").replace("Ö", "O")
          .replace("ç", "c").replace("Ç", "C"))
    return re.sub(r"\s+", " ", s.upper()).strip()


# Sıra ÖNEMLİ: özgül kalıplar genel olanlardan önce (İCRA CEZA, İCRA'dan önce vb.).
# (regex — normalize edilmiş metinde aranır, kanonik değer, court_types parent_code)
PATTERNS: "list[tuple[str, str, str]]" = [
    (r"\bICRA CEZA\b",                    "İCRA CEZA HAKİMLİĞİ",                  "Ceza"),
    (r"\bICRA HUKUK\b",                   "İCRA HUKUK MAHKEMESİ",                 "Hukuk"),
    (r"\bICRA\b",                         "İCRA DAİRESİ",                         "İcra"),
    (r"\bCOCUK AGIR CEZA\b",              "ÇOCUK AĞIR CEZA MAHKEMESİ",            "Ceza"),
    (r"\bAGIR CEZA\b",                    "AĞIR CEZA MAHKEMESİ",                  "Ceza"),
    (r"\bSULH CEZA\b",                    "SULH CEZA HAKİMLİĞİ",                  "Ceza"),
    (r"\bASLIYE CEZA\b",                  "ASLİYE CEZA MAHKEMESİ",                "Ceza"),
    (r"\bINFAZ HAKIMLIG",                 "İNFAZ HAKİMLİĞİ",                      "Ceza"),
    (r"\bCOCUK MAHKEMESI\b",              "ÇOCUK MAHKEMESİ",                      "Ceza"),
    (r"FIKRI.{0,4}SINAI HAKLAR CEZA",     "FİKRİ VE SINAİ HAKLAR CEZA MAHKEMESİ", "Ceza"),
    (r"FIKRI.{0,4}SINAI HAKLAR HUKUK",    "FİKRİ VE SINAİ HAKLAR HUKUK MAHKEMESİ", "Hukuk"),
    # Hakem heyeti / tahkim MAHKEME DEĞİL, ayrı mercidir — bu yüzden ikisi de çıplak
    # `\bTUKETICI\b` sıfatından ÖNCE gelir (G071): "İzmir İl Tüketici Hakem Heyeti"
    # aksi halde TÜKETİCİ MAHKEMESİ yazılıyordu. TAHKİM, HAKEM HEYETİ'nden önce
    # KALIR: "Sigorta Tahkim … hakem heyeti" tüketici hakem heyeti değildir.
    (r"\bTAHKIM\b",                       "TAHKİM HEYETİ",                        "Tahkim"),
    (r"\bHAKEM HEYETI\b",                 "TÜKETİCİ HAKEM HEYETİ",                "Hukuk"),
    (r"\bTUKETICI\b",                     "TÜKETİCİ MAHKEMESİ",                   "Hukuk"),
    (r"\bASLIYE TICARET\b|\bTICARET MAHKEMESI\b", "ASLİYE TİCARET MAHKEMESİ",     "Hukuk"),
    (r"\bASLIYE HUKUK\b",                 "ASLİYE HUKUK MAHKEMESİ",               "Hukuk"),
    (r"\bSULH HUKUK\b",                   "SULH HUKUK MAHKEMESİ",                 "Hukuk"),
    (r"\bIS MAHKEMESI\b",                 "İŞ MAHKEMESİ",                         "Hukuk"),
    (r"\bAILE MAHKEMESI\b",               "AİLE MAHKEMESİ",                       "Hukuk"),
    (r"\bKADASTRO\b",                     "KADASTRO MAHKEMESİ",                   "Hukuk"),
    # Yargıtay daireleri — genel "HUKUK/CEZA DAIRESI" alternatifinden ÖNCE gelmeli (G069):
    # aksi halde TEMYİZ mercii İSTİNAF'a (Bölge Adliye) yazılır. İlk derece mahkemesi
    # kalıplarından SONRA durur ki "… Asliye Hukuk Mahkemesi (Yargıtay bozması)" gibi
    # atıflar mahkemenin kendi türünü bozmasın.
    # Ad neden "YARGITAY" değil: judicial_unit bir yargı BİRİMİ (court_types) alanıdır ve
    # her değer tek bir parent_code taşır; Yargıtay hem hukuk hem ceza dairesi barındırır.
    # Kardeş kurum Bölge Adliye de bu yüzden tek değil İKİ kanonik değerle taşınır.
    (r"\bYARGITAY\b.*(\bCEZA\b|\bCD\b)",  "YARGITAY CEZA DAİRESİ",                "Ceza"),
    (r"\bYARGITAY\b.*(\bHUKUK\b|\bHD\b)", "YARGITAY HUKUK DAİRESİ",               "Hukuk"),
    # BAM/istinaf daireleri — ASLIYE eşleşmez ("ADLIYE" farklı kelime), yine de İCRA'dan sonra
    (r"(BOLGE ADLIYE|ISTINAF|BAM\b).*(CEZA)|CEZA DAIRESI",   "BÖLGE ADLİYE MAH. CEZA DAİRESİ",  "Ceza"),
    (r"(BOLGE ADLIYE|ISTINAF|BAM\b).*(HUKUK)|HUKUK DAIRESI", "BÖLGE ADLİYE MAH. HUKUK DAİRESİ", "Hukuk"),
    # "İdari Dava Dairesi" = BİM dairesi; "İdare Mahkeme" hem MAHKEMESİ hem MAHKEMELERİ (çoğul) yakalar
    (r"\bBOLGE IDARE\b|IDAR[EI] DAVA DAIRESI", "BÖLGE İDARE MAHKEMESİ",           "İdari Yargı"),
    (r"\bIDARE MAHKEME",                  "İDARE MAHKEMESİ",                      "İdari Yargı"),
    (r"\bVERGI\b",                        "VERGİ MAHKEMESİ",                      "İdari Yargı"),
    (r"\bDANISTAY\b",                     "DANIŞTAY",                             "İdari Yargı"),
    (r"ARABULUCU",                        "ARABULUCULUK BÜROSU",                  "Arabuluculuk"),
    (r"NOTERLIG|NOTERLIK",                "NOTERLİK",                             "Hukuk"),
    (r"SAVCILI[GK]",                      "CUMHURİYET BAŞSAVCILIĞI",              "Savcılık"),
]

_COMPILED = [(re.compile(rx), name, parent) for rx, name, parent in PATTERNS]


def derive_judicial_unit(court: str) -> "str | None":
    norm = normalize_court(court)
    if not norm:
        return None
    for rx, name, _parent in _COMPILED:
        if rx.search(norm):
            return name
    return None
