import sqlite3
import json
import time
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# --- LOGGER IMPORT ---
try:
    from log_manager import TechnicalLogger
except ImportError:

    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger

import sys
if getattr(sys, 'frozen', False):
    DB_PATH = Path(sys.executable).parent / "data" / "analysis_cache.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "data" / "analysis_cache.db"


class DatabaseManager:
    _instance = None

    def __init__(self):
        self._ensure_db_dir()
        self._init_db()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_db_dir(self):
        if not DB_PATH.parent.exists():
            try:
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                TechnicalLogger.log("ERROR", f"Failed to create DB directory: {e}")

    def _get_connection(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Create Analysis Cache Table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_cache (
                        file_hash TEXT PRIMARY KEY,
                        data_json TEXT,
                        created_at REAL,
                        updated_at REAL
                    )
                """
                )
                # Create Index for fast lookups (Primary Key is already indexed but good practice)
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_updated_at ON analysis_cache (updated_at)
                """
                )
                conn.commit()
        except Exception as e:
            TechnicalLogger.log("ERROR", f"DB Init Failed: {e}")

    def get_cache(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves analysis result from DB by hash."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT data_json FROM analysis_cache WHERE file_hash = ?",
                    (file_hash,),
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return None
        except Exception as e:
            TechnicalLogger.log("ERROR", f"DB Read Failed: {e}")
            return None

    def save_cache(self, file_hash: str, data: Dict[str, Any]):
        """Saves (Upserts) analysis result to DB."""
        try:
            # Ensure timestamp is in data
            timestamp = time.time()
            data["_cache_ts"] = timestamp

            json_str = json.dumps(data, ensure_ascii=False)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO analysis_cache (file_hash, data_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(file_hash) DO UPDATE SET
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at
                """,
                    (file_hash, json_str, timestamp, timestamp),
                )
                conn.commit()
                # TechnicalLogger.log("INFO", f"Saved to DB: {file_hash}")
        except Exception as e:
            TechnicalLogger.log("ERROR", f"DB Save Failed: {e}")

    def cleanup_cache(self, days: int = None):
        """Removes entries older than 'days'."""
        if days is None:
            days = int(os.getenv("CACHE_EXPIRY_DAYS", "30"))

        cutoff = time.time() - (days * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM analysis_cache WHERE updated_at < ?", (cutoff,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    TechnicalLogger.log(
                        "INFO", f"DB Cleanup: Removed {deleted_count} old entries."
                    )
        except Exception as e:
            TechnicalLogger.log("ERROR", f"DB Cleanup Failed: {e}")
