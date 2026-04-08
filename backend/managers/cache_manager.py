import os
import json
import shutil
import logging

# Logger Setup
logger = logging.getLogger("CacheManager")
logging.basicConfig(level=logging.INFO)

import sys
from pathlib import Path

# Use AppData for cache (Writable)
CACHE_DIR = Path.home() / "AppData" / "Local" / "HukuDok" / "cache"

CACHE_FILE = CACHE_DIR / "list_cache.json"


def ensure_cache_dir():
    """Ensures that the cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        try:
            os.makedirs(CACHE_DIR)
        except Exception as e:
            logger.error(f"Failed to create cache directory: {e}")


def load_cache():
    """
    Loads list data from the local JSON cache.
    Returns: dict with keys 'lawyers', 'statuses', 'doctypes' (or empty if failed).
    """
    if not os.path.exists(CACHE_FILE):
        logger.info("Cache file not found. Starting fresh.")
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("Cache loaded successfully.")
            return data
    except json.JSONDecodeError:
        logger.warning("Cache file is corrupt. Ignoring.")
        return {}
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        return {}


def save_cache(data):
    """
    Saves list data to the local JSON cache using atomic write.
    Args:
        data (dict): The data to save.
    """
    ensure_cache_dir()

    # Use a temp file for atomic write safety
    temp_file = os.path.join(CACHE_DIR, "list_cache.tmp")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Atomically replace the old file
        shutil.move(temp_file, CACHE_FILE)
        logger.info("Cache saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
