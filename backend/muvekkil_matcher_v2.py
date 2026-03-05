
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
            from database import get_normalized_clients
            normalized_map = get_normalized_clients()
            # normalized_map değerler artık list[str] — key'ler normalized isimler
            self.clients = set(normalized_map.keys())  # Hızlı lookup için set
            logger.info(f"✅ HibridMatcher: {len(self.clients)} clients loaded from DB.")
        except Exception as e:
            logger.error(f"HibridMatcher Load Error: {e}")
            self.clients = set()

    def filtrele(self, hook_tespit, diger_isimler, avukat_var):
        """
        Müvekkil doğrulama: liste üzerine kontrol eder.
        İ/İ Normalize sonra arar.
        """
        def normalize(s: str) -> str:
            return s.upper().replace("İ", "I")

        clients_normalized = {normalize(c) for c in self.clients}

        # 1. hook_tespit listede mi?
        if hook_tespit:
            if normalize(hook_tespit) in clients_normalized:
                return hook_tespit, "cache_hit", 100.0

        # 2. Diger isimlerden listede olan var mı?
        if diger_isimler:
            for isim in diger_isimler:
                if normalize(isim) in clients_normalized:
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
    HibridMatcher + ListSearcher ikisini birden yeniler.
    api.py background task veya /refresh endpoint'inden çağrılabilir.
    """
    matcher = get_hibrid_matcher()
    matcher.load_clients()
    logger.info("✅ HibridMatcher: Liste yenilendi.")

    try:
        from list_searcher import yenile_list_searcher
        yenile_list_searcher()
    except Exception as e:
        logger.warning(f"ListSearcher yenilenirken hata: {e}")
