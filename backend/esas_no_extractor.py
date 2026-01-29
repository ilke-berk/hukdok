import re
from typing import List, Dict, Optional

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

# --- PRE-COMPILED PATTERNS ---
# 1. Normalization Pattern (Whitespace removal)
PRE_COMPILED_NORM_PATTERN = re.compile(r'\s+')

# 2. Esas No Patterns
# Each tuple is (Compiled Pattern, Confidence Level)
PRE_COMPILED_ESAS_PATTERNS = [
    # Pattern 1: ESASNO:YYYY/NNN (En yüksek öncelik)
    (re.compile(r'(?:ESAS|DOSYA)?(?:NO|NUMARASI|SAYISI)?:?(\d{4}/\d+)', re.IGNORECASE), 'very_high'),
    
    # Pattern 2: YYYY/NNNESAS (Sayı önce)
    (re.compile(r'(\d{4}/\d+)(?:SAYILI)?ESAS(?!NO|NUMARASI)', re.IGNORECASE), 'very_high'),
    
    # Pattern 3: E.YYYY/NNN veya E:YYYY/NNN
    (re.compile(r'E[.:]?(\d{4}/\d+)', re.IGNORECASE), 'high'),
]

# 3. Karar No Pattern
PRE_COMPILED_KARAR_PATTERN = re.compile(r'(\d{4}/\d+)KARAR', re.IGNORECASE)

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

    # 1. Normalizasyon: Tüm boşlukları kaldır (Pre-compiled)
    normalized_text = PRE_COMPILED_NORM_PATTERN.sub('', text)
    
    # 2. Normalized Text için Patternler (Using Global Pre-compiled Patterns)
    # patterns listesi artık global PRE_COMPILED_ESAS_PATTERNS
    
    results = []
    
    # Karar numaralarını da normalized text üzerinden bul ve filtrele
    # "2023/1968KARAR" gibi (Pre-compiled)
    karar_matches = PRE_COMPILED_KARAR_PATTERN.findall(normalized_text)
    karar_numbers = set(karar_matches)
    
    for i, (pattern, confidence_level) in enumerate(PRE_COMPILED_ESAS_PATTERNS, 1):
        matches = pattern.findall(normalized_text)
        if matches:
            for match in matches:
                # Karar numarası kontrolü:
                # Sadece düşük güvenilirlikli veya karışabilecek patternlar için kontrol et
                # Pattern 1 (ESASNO:...) ve Pattern 2 (...ESAS) çok spesifik, bunları filtreleme!
                if i == 3 and match in karar_numbers:
                    continue
                    
                # Yıl kontrolü (2010-2030 arası mantıklı)
                try:
                    parts = match.split('/')
                    year = int(parts[0])
                    # Yıl mantıklı bir aralıkta mı? (1990 - 2035)
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
