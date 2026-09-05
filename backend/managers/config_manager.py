"""Süreç-içi dinamik konfigürasyon: referans listelerinin singleton kopyası.

`DynamicConfig` (thread-kilitli singleton) avukat/statü/belge türü/şehir… listelerini
ve mojibake düzeltme haritasını RAM'de tutar; açılışta ve `/refresh` ile doldurulur,
analyzer + route'lar DB'ye her istekte gitmemek için buradan okur. Süreç-içi olduğu
için refresh thread'i bilinçli worker-BAŞINA koşar. Dış bağımlılık: threading,
`managers/log_manager` (TechnicalLogger) ve `managers/data/mojibake_map.json`.
"""
import threading
import logging
from typing import List, Dict

# --- LOGGER IMPORT ---
try:
    from managers.log_manager import TechnicalLogger
except ImportError:

    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger  # type: ignore[misc,assignment]

import json
from pathlib import Path

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
    _initialized: bool = False

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
        self.__file_statuses: List[Dict] = []
        self.__alleged_faults: List[Dict] = []
        self.__appealing_parties: List[Dict] = []
        # Karar sonucu resmi listeleri (G060)
        self.__local_decisions: List[Dict] = []
        self.__appeal_decisions: List[Dict] = []
        self.__cassation_decisions: List[Dict] = []
        self.__revision_decisions: List[Dict] = []
        # Belgeleme olayı listeleri (G103)
        self.__event_types: List[Dict] = []
        self.__judgment_roles: List[Dict] = []
        # Müvekkil Tipi / Hizmet Türü listeleri (G119)
        self.__client_types: List[Dict] = []
        self.__service_types: List[Dict] = []
        # G124 listeleri — tek sözlükte; getter/setter'lar getattr sözleşmesini
        # (refresh_cache → set_<liste>) korur, gövde `_g124_get/_g124_set`.
        self.__g124_lists: Dict[str, List[Dict]] = {
            k: [] for k in (
                "currencies", "medical_processes", "medical_events", "patient_harms",
                "applied_methods", "cassation_courts", "appeal_courts",
                "defendant_administrations",
            )
        }
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

    def get_file_statuses(self) -> List[Dict]:
        return self.__file_statuses

    def set_file_statuses(self, items: List[Dict]):
        with self._lock:
            self.__file_statuses = items
            TechnicalLogger.log("INFO", f"DynamicConfig: File Statuses updated ({len(items)} items)")

    # FAZ F'nin iki kapalı listesi (G044). LIST_REGISTRY'deki `setter` adı
    # buradaki metoda getattr ile bağlanır (reference_lists.refresh_cache) —
    # setter yoksa liste her güncellendiğinde AttributeError'a düşer.
    def get_alleged_faults(self) -> List[Dict]:
        return self.__alleged_faults

    def set_alleged_faults(self, items: List[Dict]):
        with self._lock:
            self.__alleged_faults = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Alleged Faults updated ({len(items)} items)")

    def get_appealing_parties(self) -> List[Dict]:
        return self.__appealing_parties

    def set_appealing_parties(self, items: List[Dict]):
        with self._lock:
            self.__appealing_parties = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Appealing Parties updated ({len(items)} items)")

    # Karar sonucu resmi listeleri (G060) — aynı getattr sözleşmesi.
    def get_local_decisions(self) -> List[Dict]:
        return self.__local_decisions

    def set_local_decisions(self, items: List[Dict]):
        with self._lock:
            self.__local_decisions = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Local Decisions updated ({len(items)} items)")

    def get_appeal_decisions(self) -> List[Dict]:
        return self.__appeal_decisions

    def set_appeal_decisions(self, items: List[Dict]):
        with self._lock:
            self.__appeal_decisions = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Appeal Decisions updated ({len(items)} items)")

    def get_cassation_decisions(self) -> List[Dict]:
        return self.__cassation_decisions

    def set_cassation_decisions(self, items: List[Dict]):
        with self._lock:
            self.__cassation_decisions = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Cassation Decisions updated ({len(items)} items)")

    def get_revision_decisions(self) -> List[Dict]:
        return self.__revision_decisions

    def set_revision_decisions(self, items: List[Dict]):
        with self._lock:
            self.__revision_decisions = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Revision Decisions updated ({len(items)} items)")

    # Belgeleme olayı listeleri (G103) — aynı getattr sözleşmesi.
    def get_event_types(self) -> List[Dict]:
        return self.__event_types

    def set_event_types(self, items: List[Dict]):
        with self._lock:
            self.__event_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Event Types updated ({len(items)} items)")

    def get_judgment_roles(self) -> List[Dict]:
        return self.__judgment_roles

    def set_judgment_roles(self, items: List[Dict]):
        with self._lock:
            self.__judgment_roles = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Judgment Roles updated ({len(items)} items)")

    # Müvekkil Tipi / Hizmet Türü listeleri (G119) — aynı getattr sözleşmesi.
    def get_client_types(self) -> List[Dict]:
        return self.__client_types

    def set_client_types(self, items: List[Dict]):
        with self._lock:
            self.__client_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Client Types updated ({len(items)} items)")

    def get_service_types(self) -> List[Dict]:
        return self.__service_types

    def set_service_types(self, items: List[Dict]):
        with self._lock:
            self.__service_types = items
            TechnicalLogger.log("INFO", f"DynamicConfig: Service Types updated ({len(items)} items)")

    # ─── G124 listeleri (para birimi + teslim havuzları) ─────────────────
    def _g124_get(self, key: str) -> List[Dict]:
        return self.__g124_lists[key]

    def _g124_set(self, key: str, items: List[Dict]):
        with self._lock:
            self.__g124_lists[key] = items
            TechnicalLogger.log("INFO", f"DynamicConfig: {key} updated ({len(items)} items)")

    def get_currencies(self) -> List[Dict]:                 return self._g124_get("currencies")
    def set_currencies(self, items: List[Dict]):            self._g124_set("currencies", items)
    def get_medical_processes(self) -> List[Dict]:          return self._g124_get("medical_processes")
    def set_medical_processes(self, items: List[Dict]):     self._g124_set("medical_processes", items)
    def get_medical_events(self) -> List[Dict]:             return self._g124_get("medical_events")
    def set_medical_events(self, items: List[Dict]):        self._g124_set("medical_events", items)
    def get_patient_harms(self) -> List[Dict]:              return self._g124_get("patient_harms")
    def set_patient_harms(self, items: List[Dict]):         self._g124_set("patient_harms", items)
    def get_applied_methods(self) -> List[Dict]:            return self._g124_get("applied_methods")
    def set_applied_methods(self, items: List[Dict]):       self._g124_set("applied_methods", items)
    def get_cassation_courts(self) -> List[Dict]:           return self._g124_get("cassation_courts")
    def set_cassation_courts(self, items: List[Dict]):      self._g124_set("cassation_courts", items)
    def get_appeal_courts(self) -> List[Dict]:              return self._g124_get("appeal_courts")
    def set_appeal_courts(self, items: List[Dict]):         self._g124_set("appeal_courts", items)
    def get_defendant_administrations(self) -> List[Dict]:  return self._g124_get("defendant_administrations")
    def set_defendant_administrations(self, items: List[Dict]): self._g124_set("defendant_administrations", items)

