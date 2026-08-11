"""Teknik hata arşivi: standart logging + tavanlı RAM tamponu + SharePoint yedeği.

`TechnicalLogger` kayıtları standart logging'e delege eder (K10) VE tavanlı RAM
tamponunda biriktirip ERROR/CRITICAL'de ayrı thread'de SharePoint yedek arşivine JSON
olarak yükler; mesajlar `mask_sensitive_data` ile maskelenir. Dış bağımlılık: Graph API
(`sharepoint/`), threading.

Not: bu modülde bir zamanlar SharePoint 'log' listesine satır açan `LogManager` da vardı;
`init_log/complete_log/fail_log` hiçbir yerden çağrılmadığı için 2026-08-12'de silindi
(G028). Liste yazımı zaten durmuştu, tüm belge metadata'sı Postgres'te.
"""
import os
import logging
import socket
from datetime import datetime

logger = logging.getLogger("LogManager")


# --- TECHNICAL LOGGER ---
# Import'lar bilerek burada (dosya ortasında): pyproject `per-file-ignores` bu dosyaya
# E402 muafiyeti verir. Taşımak sırf kozmetik olur, diff'i büyütmemek için bırakıldı.
import threading
import re
import json
from collections import deque
from typing import Deque, Dict, Optional

try:
    from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
except ImportError:
    upload_file_to_sharepoint = None


def mask_sensitive_data(text: str) -> str:
    """Masks TCKN (11 digits), Credit Cards, and Emails in logs."""
    if not isinstance(text, str):
        return text
    text = re.sub(r"\b\d{11,16}\b", "***********", text)
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "***@***.com", text
    )
    return text


# Faz 3.3 (K10): seviye adı → logging sabiti eşlemesi
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class TechnicalLogger:
    # Tavanlı buffer: SharePoint'e ulaşılamayan ya da hiç ERROR üretmeyen
    # prod'da sınırsız büyüyüp kalıcı anonim bellek tüketiyordu (2026-07-29
    # OOM incelemesi). Tavana ulaşınca en eski kayıt düşer.
    _MAX_BUFFER_ENTRIES = 2000
    _MAX_MESSAGE_CHARS = 4000
    _buffer: Deque[Dict] = deque(maxlen=_MAX_BUFFER_ENTRIES)
    _lock = threading.Lock()
    _sync_lock = threading.Lock()
    # Faz 3.3 (K10): kayıtlar standart logging'e de delege edilir; handler ve
    # format tek yerden (root logging config) yönetilir. API yüzeyi değişmedi.
    _std_logger = logging.getLogger("TechnicalLogger")

    @staticmethod
    def log(level: str, message: str, details: Optional[Dict] = None):
        """
        Logs a technical event to RAM buffer.
        If level is CRITICAL/ERROR, triggers immediate sync to Cloud.
        """
        timestamp = datetime.now().isoformat()
        masked_message = mask_sensitive_data(str(message)[: TechnicalLogger._MAX_MESSAGE_CHARS])
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": masked_message,
            "details": details or {},
        }

        # Standart logging'e delege (K10 — tek handler/format)
        std_level = _LEVEL_MAP.get(str(level).upper(), logging.INFO)
        if details:
            TechnicalLogger._std_logger.log(std_level, "%s | %s", masked_message, details)
        else:
            TechnicalLogger._std_logger.log(std_level, "%s", masked_message)

        # Add to RAM buffer
        with TechnicalLogger._lock:
            TechnicalLogger._buffer.append(log_entry)

        # Immediate sync for critical errors. Ayrı thread'de: senkron SharePoint
        # upload'ı çağıranı (async yolda event loop'un kendisini) kilitliyordu.
        if level in ["ERROR", "CRITICAL"]:
            threading.Thread(
                target=TechnicalLogger.sync_to_cloud,
                name="technical-log-sync",
                daemon=True,
            ).start()

    @staticmethod
    def sync_to_cloud():
        """
        Dumps RAM buffer to a JSON file and uploads to SharePoint.
        Then clears the buffer.
        """
        # Zaten koşan bir senkron varsa yenisini başlatma — kayıtlar buffer'da,
        # sıradaki senkron alır (ERROR başına thread yığılmasını önler)
        if not TechnicalLogger._sync_lock.acquire(blocking=False):
            return
        try:
            TechnicalLogger._sync_to_cloud_locked()
        finally:
            TechnicalLogger._sync_lock.release()

    @staticmethod
    def _sync_to_cloud_locked():
        with TechnicalLogger._lock:
            if not TechnicalLogger._buffer:
                return

            data_to_sync = list(TechnicalLogger._buffer)

        if upload_file_to_sharepoint is None:
            return

        try:
            # Create a temp JSON file
            # Use AppData for logs (Writable by user)
            from pathlib import Path
            LOGS_DIR = Path.home() / "AppData" / "Local" / "HukuDok" / "logs"
            LOGS_DIR.mkdir(parents=True, exist_ok=True)

            # Faz 3-E: pid eklendi — uvicorn --workers N'de iki worker aynı
            # saniyede senkronlarsa aynı SharePoint adına yazar (replace),
            # bir worker'ın ERROR partisi sessizce kaybolurdu.
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_filename = f"technical_log_{timestamp_str}_{socket.gethostname()}_p{os.getpid()}.json"
            temp_filepath = os.path.join(LOGS_DIR, temp_filename)
            TARGET_SP_FOLDER = os.getenv(
                "SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV"
            )

            with open(temp_filepath, "w", encoding="utf-8") as f:
                json.dump(data_to_sync, f, ensure_ascii=False, indent=2)

            # Upload
            upload_file_to_sharepoint(
                filepath=temp_filepath,
                target_filename=temp_filename,
                target_folder_name=TARGET_SP_FOLDER,
                content_type="application/json",
            )

            # Clean up temp file
            os.remove(temp_filepath)

            # Yalnızca senkronlanan kayıtları düş: upload sürerken eklenen
            # yeni kayıtlar buffer'da kalır (önceden komple sıfırlanıp
            # aradaki kayıtlar kayboluyordu)
            with TechnicalLogger._lock:
                synced_ids = set(map(id, data_to_sync))
                remaining = [e for e in TechnicalLogger._buffer if id(e) not in synced_ids]
                TechnicalLogger._buffer.clear()
                TechnicalLogger._buffer.extend(remaining)

        except Exception as e:
            logger.error(f"Technical Sync Failed: {e}")
