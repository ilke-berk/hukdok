from flashtext import KeywordProcessor
import json
from pathlib import Path
import logging
from typing import List, Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)

class ListSearcher:
    """
    FlashText based high-performance client searcher.
    Loads normalized client list and searches in text.
    """
    
    def __init__(self):
        self.keyword_processor = KeywordProcessor(case_sensitive=True)
        self.client_map = {} 
        self._load_data()
        
    def _load_data(self):
        """Loads data from Database and builds the keyword processor"""
        try:
            from database import get_normalized_clients
            normalized_map = get_normalized_clients()

            self.client_map = normalized_map
            
            # Flash text processor'u sıfırla ve yeniden yüKle
            from flashtext import KeywordProcessor
            self.keyword_processor = KeywordProcessor(case_sensitive=True)

            count = 0
            for normalized_name in self.client_map:
                if normalized_name and len(normalized_name) > 2:
                    self.keyword_processor.add_keyword(normalized_name, normalized_name)
                    count += 1

            logger.info(f"✅ Loaded {count} clients into FlashText processor from DB")

        except Exception as e:
            logger.error(f"❌ Error loading client list from DB: {e}")

    def reload(self):
        """Veri tabanından müvekkil listesini yeniden yükler. (Yeni müvekkil eklenince çağrılır)"""
        logger.info("🔄 ListSearcher: Yenileniyor...")
        self._load_data()
        logger.info(f"✅ ListSearcher: {len(self.client_map)} müvekkil yülendi.")
            
    def search(self, text: str) -> List[str]:
        """
        Searches for clients in the given text.
        Returns a list of UNIQUE normalized names found.
        """
        if not text:
            return []
            
        # Text normalization for search:
        # 1. Replace apostrophes with space to separate suffixes (e.g. TUTUMLU'NUN -> TUTUMLU NUN)
        # 2. Uppercase Turkish
        # 3. Collapse multiple spaces
        from client_normalizer import turkish_upper
        import re
        
        # Replace common apostrophes
        text_cleaned = text.replace("'", " ").replace("'", " ").replace("`", " ")
        
        # Uppercase
        text_upper = turkish_upper(text_cleaned)
        
        # Collapse whitespace (FlashText sensitive to exact spacing in keywords)
        text_upper = " ".join(text_upper.split())
        
        # Extract keywords
        found_keywords = self.keyword_processor.extract_keywords(text_upper)
        
        # Deduplicate results
        return list(set(found_keywords))
        
    def get_original_entries(self, normalized_name: str) -> list:
        """
        Returns the original DB entries for a normalized name.
        Handles list, dict, and legacy string formats.
        """
        value = self.client_map.get(normalized_name, [])
        if isinstance(value, dict):
            return value.get("raw_variants", [])
        elif isinstance(value, list):
            return value
        elif isinstance(value, str):  # Legacy / Eski format
            return [value]
        return []
    
    def get_metadata(self, normalized_name: str) -> Dict[str, Any]:
        """
        Returns full metadata for a normalized name (new enhanced structure).
        Returns dict with keys: raw_variants, count, source_ids
        """
        value = self.client_map.get(normalized_name, {})
        
        # If new enhanced structure, return as-is
        if isinstance(value, dict) and "raw_variants" in value:
            return value
        # If old format, convert to enhanced structure
        elif isinstance(value, list):
            return {
                "raw_variants": value,
                "count": len(value),
                "source_ids": ["legacy"] * len(value)
            }
        else:
            return {"raw_variants": [], "count": 0, "source_ids": []}

_searcher_instance = None

def get_list_searcher():
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = ListSearcher()
    return _searcher_instance

def yenile_list_searcher():
    """Liste yenileme — yeni müvekkil eklenince veya /refresh endpoint'inden çağrılır."""
    searcher = get_list_searcher()
    searcher.reload()
    logger.info("✅ ListSearcher yenilendi.")

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    searcher = ListSearcher()
    # Print some stats from instance
    logger.info(f"Keywords loaded: {len(searcher.keyword_processor.get_all_keywords())}")
    
    test_text = "BU BİR DENEMEDİR. VAHAP DÖŞ TARAFINDAN YAPILMIŞTIR. AYRICA NİHAN HİLAL HOŞAĞASI DA BURADADIR."
    from client_normalizer import turkish_upper
    logger.info(f"Normalized Text: {turkish_upper(test_text)}")
    
    results = searcher.search(test_text)
    logger.info(f"Test Text: {test_text}")
    logger.info(f"Found: {results}")
    
    for res in results:
        logger.info(f"Originals for {res}: {searcher.get_original_entries(res)}")
