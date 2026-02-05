
import json
import os
import logging
from pathlib import Path
from difflib import SequenceMatcher

# Logger Setup
logger = logging.getLogger("MuvekkilMatcherV2")


class HibridMatcher:
    def __init__(self):
        self.clients = []
        self.load_clients()

    def load_clients(self):
        try:
            import sys
            if getattr(sys, 'frozen', False):
                current_dir = Path(sys.executable).parent
            else:
                current_dir = Path(__file__).resolve().parent
            
            json_path = current_dir / "data" / "normalized_client_list.json"
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.clients = list(data.get("clients", {}).keys())
        except Exception as e:
            logger.error(f"HibridMatcher Load Error: {e}")

    def filtrele(self, hook_tespit, diger_isimler, avukat_var):
        """
        Şimdilik basit pass-through veya list checking.
        """
        # 1. Eğer hook_tespit zaten listedeyse onayla
        if hook_tespit:
            ts = hook_tespit.upper().replace("İ", "I")
            if ts in self.clients:
                return hook_tespit, "cache_hit", 100.0
        
        # 2. Diğer isimlerden listede olan var mı?
        if diger_isimler:
            for isim in diger_isimler:
                name_upper = isim.upper().replace("İ", "I")
                if name_upper in self.clients:
                    return isim, "liste_düzeltmesi", 95.0

        # Bulunamadıysa LLM ne dediyse o
        return hook_tespit, "fallback", 0.0

# Global Singleton Instance
_MATCHER_INSTANCE = None

def get_hibrid_matcher():
    global _MATCHER_INSTANCE
    if _MATCHER_INSTANCE is None:
        _MATCHER_INSTANCE = HibridMatcher()
    return _MATCHER_INSTANCE

def yenile_matcher():
    """
    Called by api.py background task to reload data from JSON
    """
    matcher = get_hibrid_matcher()
    matcher.load_clients()
    logger.info("✅ HibridMatcher: Liste yenilendi.")
