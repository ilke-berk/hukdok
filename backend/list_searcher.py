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
    
    def __init__(self, normalized_file: str = "data/normalized_client_list.json"):
        self.keyword_processor = KeywordProcessor(case_sensitive=True)
        self.client_map = {} # normalized_name -> enhanced structure or list (backward compatible)
        
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent
            
        # Check AppData First
        # Fix: normalized_file comes as "data/..." so we take .name to get just filename
        app_data_path = Path.home() / "AppData" / "Local" / "HukuDok" / "data" / Path(normalized_file).name
        bundled_path = base_dir / normalized_file
        
        if app_data_path.exists():
            self.normalized_path = app_data_path
            logger.info(f"Using AppData client list: {self.normalized_path}")
        else:
            self.normalized_path = bundled_path
            logger.info(f"Using Bundled client list: {self.normalized_path}")
        
        self._load_data()
        
    def _load_data(self):
        """Loads data from JSON and builds the keyword processor"""
        if not self.normalized_path.exists():
            logger.error(f"❌ Normalized file not found: {self.normalized_path}")
            return
            
        try:
            with open(self.normalized_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.client_map = data.get("clients", {})
            
            count = 0
            for normalized_name, value in self.client_map.items():
                if normalized_name and len(normalized_name) > 2:
                    # We map the normalized name to itself in FlashText
                    # This allows us to look up the 'originals' or metadata later
                    self.keyword_processor.add_keyword(normalized_name, normalized_name)
                    count += 1
                    
            logger.info(f"✅ Loaded {count} keywords into FlashText processor")
            
        except Exception as e:
            logger.error(f"❌ Error loading client list: {e}")
            
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
        
    def get_original_entries(self, normalized_name: str) -> List[str]:
        """
        Returns the original SharePoint entries for a normalized name.
        Supports both old format (list) and new format (dict with raw_variants).
        """
        value = self.client_map.get(normalized_name, [])
        
        # Handle new enhanced structure
        if isinstance(value, dict):
            return value.get("raw_variants", [])
        # Handle old format (backward compatibility)
        elif isinstance(value, list):
            return value
        else:
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

# Singleton instance
_searcher_instance = None

def get_list_searcher():
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = ListSearcher()
    return _searcher_instance

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
