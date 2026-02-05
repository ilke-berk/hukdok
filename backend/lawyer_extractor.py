import re
from typing import List, Dict, Optional, Tuple
from config_manager import DynamicConfig
import logging

# Düşük öncelikli avukatlar (Override edilmeye müsait)
LOW_PRIORITY_LAWYERS = [
    "AYŞE GÜL HANYALOĞLU",
    "AYŞE ACAR YÜCEL",
    "AYŞE ACAR" 
]

def normalize_text(text: str) -> str:
    """Türkçe karakterleri normalize eder ve büyük harfe çevirir (Efficient)."""
    if not text: return ""
    table = str.maketrans({
        'i': 'İ', 'ı': 'I', 'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö',
        'ç': 'Ç', 'â': 'A', 'î': 'I', 'û': 'U'
    })
    return text.translate(table).upper()

def find_best_lawyer(text: str) -> Optional[str]:
    """
    Metin içinde geçen avukatları arar ve öncelik sırasına göre en iyisini döndürür.
    Optimization: Avoids regex compilation inside loop.
    """
    if not text:
        return None

    config = DynamicConfig.get_instance()
    lawyers = config.get_lawyers()

    if not lawyers:
        return None

    # Pre-normalize the full text once
    normalized_text = normalize_text(text)
    
    detected_lawyers = [] 
    
    # Pre-calculate normalized names for efficiency
    # In a persistent process, this should be cached in ConfigManager, but for now we optimize just the loop
    for lawyer in lawyers:
        code = lawyer.get('code')
        name = lawyer.get('name')
        if not name or not code:
            continue

        normalized_name = normalize_text(name)
        
        # Fast String Search (No Regex Compilation per item)
        if normalized_name in normalized_text:
            # Check low priority list
            is_low_priority = any(lp in normalized_name for lp in LOW_PRIORITY_LAWYERS)
            detected_lawyers.append({
                'code': code,
                'name': name,
                'priority': 0 if is_low_priority else 1
            })
        


    if not detected_lawyers:
        return None

    # Sort by Priority (Desc), then by Name Length (Desc - "Ayşe Gül" > "Ayşe")
    # Priority 1 (High) comes before 0 (Low)
    # Longest match preferred (more specific)
    detected_lawyers.sort(key=lambda x: (x['priority'], len(x['name'])), reverse=True)
    
    best_match = detected_lawyers[0]
    
    # Log logic (simulate logging since we can't easily import TechnicalLogger directly cleanly without circular deps potential, 
    # but actual usage is in analyzer.py where logging exists)
    
    return best_match['code']
