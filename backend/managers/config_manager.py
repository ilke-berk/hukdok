import threading
import logging
from typing import List, Dict, Any, Optional

# --- LOGGER IMPORT ---
try:
    from managers.log_manager import TechnicalLogger
except ImportError:

    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger

import json
from pathlib import Path
import os
import sys

# --- PATH HELPERS ---
def get_app_base_path() -> Path:
    """Returns %LocalAppData%/HukuDok"""
    return Path.home() / "AppData" / "Local" / "HukuDok"

def get_data_dir() -> Path:
    """Returns %LocalAppData%/HukuDok/data (Created if not exists)"""
    p = get_app_base_path() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_log_dir() -> Path:
    """Returns %LocalAppData%/HukuDok/logs (Created if not exists)"""
    p = get_app_base_path() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p

# --- CLASS DEFINITION ---
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
        self.__clients: List[str] = []
        self.__email_recipients: List[Dict] = []
        self.__case_subjects: List[Dict] = []
        self.__file_types: List[Dict] = []
        self.__court_types: List[Dict] = []
        self.__party_roles: List[Dict] = []
        self.__bureau_types: List[Dict] = []
        self.__cities: List[Dict] = []
        self.__specialties: List[Dict] = []
        self.__client_categories: List[Dict] = []
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

    def get_case_subjects(self) -> List[Dict]:
        return self.__case_subjects

    def set_case_subjects(self, subjects: List[Dict]):
        with self._lock:
            self.__case_subjects = subjects
            TechnicalLogger.log("INFO", f"DynamicConfig: Case Subjects updated ({len(subjects)} items)")

    def get_file_types(self) -> List[Dict]:
        return self.__file_types

    def set_file_types(self, items: List[Dict]):
        with self._lock:
            self.__file_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: File Types updated ({len(items)} items)")

    def get_court_types(self) -> List[Dict]:
        return self.__court_types

    def set_court_types(self, items: List[Dict]):
        with self._lock:
            self.__court_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Court Types updated ({len(items)} items)")

    def get_party_roles(self) -> List[Dict]:
        return self.__party_roles

    def set_party_roles(self, items: List[Dict]):
        with self._lock:
            self.__party_roles = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Party Roles updated ({len(items)} items)")

    def get_bureau_types(self) -> List[Dict]:
        return self.__bureau_types

    def set_bureau_types(self, items: List[Dict]):
        with self._lock:
            self.__bureau_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Bureau Types updated ({len(items)} items)")

    def get_cities(self) -> List[Dict]:
        return self.__cities

    def set_cities(self, items: List[Dict]):
        with self._lock:
            self.__cities = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Cities updated ({len(items)} items)")

    def get_specialties(self) -> List[Dict]:
        return self.__specialties

    def set_specialties(self, items: List[Dict]):
        with self._lock:
            self.__specialties = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Specialties updated ({len(items)} items)")

    def get_client_categories(self) -> List[Dict]:
        return self.__client_categories

    def set_client_categories(self, items: List[Dict]):
        with self._lock:
            self.__client_categories = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Client Categories updated ({len(items)} items)")

