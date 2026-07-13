import re
from typing import List, Dict, Optional

from text_utils import turkish_upper

# --- PRE-COMPILED PATTERNS ---
# Normalizasyon: tüm boşluklar atılır, ardından Türkçe-uyumlu büyük harfe
# çevrilir (turkish_upper). Bu sayede kalıplar IGNORECASE'e ihtiyaç duymaz;
# Python re'nin IGNORECASE'i Türkçe İ/ı çiftlerinde yanlış davranır.
PRE_COMPILED_NORM_PATTERN = re.compile(r'\s+')

# Türkçe büyük harf sınıfı (lookbehind'lar için)
_TR_UPPER = r'A-ZÇĞİIÖŞÜ'

# Esas No kalıpları: (compiled, confidence, karar_filtresi_uygulansın_mı)
# Anahtar kelimeyle çapalanan kalıplara (1 ve 2) karar filtresi UYGULANMAZ:
# aynı sayı hem esas hem karar olarak geçebilir ("2023/456 Esas, 2023/456 Karar")
# ve açık ESAS/DOSYA çapası sayının esas no olduğunu garanti eder.
PRE_COMPILED_ESAS_PATTERNS = [
    # Kalıp 1: ESASNO:YYYY/N — anahtar kelime ZORUNLU (ESAS veya DOSYA).
    # Önceden tüm önekler opsiyoneldi; çıplak YYYY/N her bağlamda very_high
    # sayılıyordu (karar no sızması dahil). Çıplak eşleşme artık Kalıp 4 (low).
    (re.compile(r'(?:ESAS|DOSYA)(?:NO|NUMARASI|SAYISI)?:?(\d{4}/\d+)'), 'very_high', False),

    # Kalıp 2: YYYY/N(SAYILI)ESAS (sayı önce)
    (re.compile(r'(\d{4}/\d+)(?:SAYILI)?ESAS(?!NO|NUMARASI)'), 'very_high', False),

    # Kalıp 3: E.YYYY/N, E:YYYY/N veya EYYYY/N ("E 2023/145" boşluksuz hali).
    # Lookbehind, E ile biten kelimelere takılmayı önler ("GENELGE2022/3" vb.)
    (re.compile(rf'(?<![{_TR_UPPER}])E[.:]?(\d{{4}}/\d+)'), 'high', True),

    # Kalıp 4: Çıplak YYYY/N — bağlam çapası yok, en düşük güven.
    # (?<!\d) daha uzun sayı dizilerinin ortasından eşleşmeyi engeller.
    (re.compile(r'(?<!\d)(\d{4}/\d+)'), 'low', True),
]

# Karar No kalıpları — bu sayılar esas no adaylarından elenir
PRE_COMPILED_KARAR_PATTERNS = [
    # "2023/456KARAR" (sayı önce)
    re.compile(r'(\d{4}/\d+)(?:SAYILI)?KARAR'),
    # "KARARNO:2023/456" (anahtar kelime önce)
    re.compile(r'KARAR(?:NO|NUMARASI|SAYISI)?:?(\d{4}/\d+)'),
    # "K.2023/456" — Yargıtay/Danıştay künyesi ("E. 2023/145 K. 2023/456")
    re.compile(rf'(?<![{_TR_UPPER}])K[.:]?(\d{{4}}/\d+)'),
]


def extract_esas_no_candidates(text: str) -> List[Dict]:
    """
    Esas numarasını regex ile tespit eder.

    Türk hukuk sisteminde yaygın formatlar:
    - 2023/145 Esas
    - E. 2024/67
    - Esas No: 2023/145
    - E:2023/145
    - Esas: 2024/234 Karar: 2024/456
    """
    if not text:
        return []

    # 1. Normalizasyon: boşlukları at + Türkçe-uyumlu büyük harf
    normalized_text = turkish_upper(PRE_COMPILED_NORM_PATTERN.sub('', text))

    # 2. Karar numaralarını topla (esas adaylarından elenecek)
    karar_numbers = set()
    for karar_pattern in PRE_COMPILED_KARAR_PATTERNS:
        karar_numbers.update(karar_pattern.findall(normalized_text))

    results = []

    for i, (pattern, confidence_level, filter_karar) in enumerate(PRE_COMPILED_ESAS_PATTERNS, 1):
        for match in pattern.findall(normalized_text):
            # Karar numarası filtresi: yalnız anahtar kelimesiz kalıplarda.
            if filter_karar and match in karar_numbers:
                continue

            # Yıl kontrolü (1990 - 2035 arası mantıklı)
            try:
                year = int(match.split('/')[0])
                if 1990 <= year <= 2035:
                    results.append({
                        'esas_no': match,
                        'pattern': f'Normalized Pattern {i}',
                        'confidence': confidence_level
                    })
            except ValueError:
                continue

    return results


def find_best_esas_no(text: str) -> Optional[str]:
    """Metin içindeki en iyi esas numarasını döndürür."""
    if not text:
        return None

    results = extract_esas_no_candidates(text)
    if not results:
        return None

    # Öncelik sırası: very_high > high > low
    for confidence_level in ['very_high', 'high', 'low']:
        matches = [r for r in results if r['confidence'] == confidence_level]
        if matches:
            # İlk eşleşmeyi döndür
            return matches[0]['esas_no']

    # Fallback: ilk sonucu döndür
    return results[0]['esas_no']
