import threading
import logging
from typing import List, Dict, Any, Optional

# --- LOGGER IMPORT ---
try:
    from log_manager import TechnicalLogger
except ImportError:

    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger

import json
from pathlib import Path


class DynamicConfig:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DynamicConfig, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.__lawyers: List[Dict] = []
        self.__statuses: List[Dict] = []
        self.__doctypes: List[Dict] = []
        self.__clients: List[str] = []  # Müvekkil listesi eklendi
        self.__email_recipients: List[Dict] = []  # E-posta alıcıları eklendi
        self.__mojibake_map: Dict[str, str] = {}

        self._load_mojibake_map()  # Load on init

        self._initialized = True
        TechnicalLogger.log("INFO", "DynamicConfig Singleton Initialized")

    def _load_mojibake_map(self):
        try:
            import sys
            if getattr(sys, 'frozen', False):
                base_path = Path(sys.executable).parent
            else:
                base_path = Path(__file__).resolve().parent

            map_path = base_path / "data" / "mojibake_map.json"
            if map_path.exists():
                with open(map_path, "r", encoding="utf-8") as f:
                    self.__mojibake_map = json.load(f)
                TechnicalLogger.log(
                    "INFO", f"Loaded Mojibake Map ({len(self.__mojibake_map)} items)"
                )
            else:
                TechnicalLogger.log(
                    "WARNING", "Mojibake map not found. Using empty map."
                )
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Failed to load mojibake map: {e}")

    @classmethod
    def get_instance(cls):
        """Static access method."""
        if cls._instance is None:
            cls()
        return cls._instance

    # --- Getters ---
    def get_lawyers(self) -> List[Dict]:
        return self.__lawyers

    def get_statuses(self) -> List[Dict]:
        return self.__statuses

    def get_doctypes(self) -> List[Dict]:
        return self.__doctypes
    
    def get_clients(self) -> List[str]:
        """Müvekkil listesini döndür"""
        return self.__clients

    def get_email_recipients(self) -> List[Dict]:
        """E-posta alıcı listesini döndür"""
        return self.__email_recipients

    def get_mojibake_map(self) -> Dict[str, str]:
        return self.__mojibake_map

    # --- Setters ---
    def set_lawyers(self, lawyers: List[Dict]):
        with self._lock:
            self.__lawyers = lawyers
            TechnicalLogger.log(
                "INFO", f"DynamicConfig: Lawyers updated ({len(lawyers)} items)"
            )

    def set_statuses(self, statuses: List[Dict]):
        with self._lock:
            self.__statuses = statuses
            TechnicalLogger.log(
                "INFO", f"DynamicConfig: Statuses updated ({len(statuses)} items)"
            )

    def set_doctypes(self, doctypes: List[Dict]):
        with self._lock:
            self.__doctypes = doctypes
            TechnicalLogger.log(
                "INFO", f"DynamicConfig: Doctypes updated ({len(doctypes)} items)"
            )
    
    def set_clients(self, clients: List[str]):
        """Müvekkil listesini güncelle"""
        with self._lock:
            self.__clients = clients
            TechnicalLogger.log(
                "INFO", f"DynamicConfig: Clients updated ({len(clients)} items)"
            )

    def set_email_recipients(self, recipients: List[Dict]):
        """E-posta alıcı listesini güncelle"""
        with self._lock:
            self.__email_recipients = recipients
            TechnicalLogger.log(
                "INFO", f"DynamicConfig: Email recipients updated ({len(recipients)} items)"
            )

