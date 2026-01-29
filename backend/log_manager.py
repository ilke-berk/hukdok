import os
import requests
import logging
import socket
import getpass
from datetime import datetime

# Mevcut auth modüllerin (Bunlar sende zaten var, dokunmuyoruz)
from auth_graph import get_graph_token
from sharepoint_uploader_graph import _get_site_and_drive_id, _headers

GRAPH = "https://graph.microsoft.com/v1.0"
# Senin listenin adı 'log' olduğu için varsayılanı değiştirdik
LOG_LIST_NAME = os.getenv("SHAREPOINT_LOG_LIST_NAME", "log")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LogManager")


class LogManager:
    def __init__(self):
        pass

    def _get_list_id_by_name(self, token, site_id, list_name):
        """SharePoint Listesinin ID'sini ismine göre bulur."""
        url = f"{GRAPH}/sites/{site_id}/lists"
        try:
            r = requests.get(url, headers=_headers(token), timeout=30)
            r.raise_for_status()
            lists = r.json().get("value", [])

            for lst in lists:
                # SharePoint bazen display name bazen name kullanır, ikisine de bakalım
                if lst.get("displayName") == list_name or lst.get("name") == list_name:
                    return lst["id"]
            return None
        except Exception as e:
            logger.error(f"Error finding list '{list_name}': {e}")
            return None

    def init_log(self, original_filename: str):
        """
        Step 1: Create an initial log entry in SharePoint to reserve an ID.
        Returns:
            tuple: (log_item_id, error_message)
            - log_item_id: The auto-increment int ID from SharePoint.
            - error_message: None if success, string if failed.
        """
        try:
            token = get_graph_token()
            site_id, _ = _get_site_and_drive_id(token)

            list_id = self._get_list_id_by_name(token, site_id, LOG_LIST_NAME)
            if not list_id:
                return None, f"SharePoint list '{LOG_LIST_NAME}' not found."

            # Prepare initial item
            hostname = socket.gethostname()
            try:
                username = os.getlogin()
            except:
                username = "Unknown"

            # INTERNAL NAME MAPPING (Based on Debug Inspection)
            # field_1: Kullanici
            # field_2: Bilgisayar
            # field_3: Orijinal_Dosya
            # field_4: Yeni_Dosya
            # field_5: Durum
            # field_6: Dosya_Hash_SHA256

            item_data = {
                "fields": {
                    "Title": original_filename,
                    "field_1": username,
                    "field_2": hostname,
                    "field_3": original_filename,
                    "field_4": "-",
                    "field_5": "ISLENIYOR",
                    "field_6": "-",
                }
            }

            # Create Item
            post_url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items"
            r = requests.post(
                post_url, headers=_headers(token), json=item_data, timeout=30
            )

            # Hata detayını yakala
            if not r.ok:
                logger.error(f"SharePoint Init Error: {r.text}")
                return None, f"SharePoint Init Error: {r.status_code} - {r.text}"

            r.raise_for_status()

            data = r.json()
            item_id = data.get("id")  # This is the Auto-ID

            logger.info(f"Log initialized. ID: {item_id} for file: {original_filename}")
            return item_id, None

        except Exception as e:
            logger.error(f"Failed to init log: {e}")
            return None, str(e)

    def complete_log(self, log_item_id: str, final_filename: str, file_hash: str = ""):
        """
        Step 2: Update the log entry with success status and final filename.
        """
        if not log_item_id:
            logger.warning("No log_item_id provided to complete_log.")
            return

        try:
            token = get_graph_token()
            site_id, _ = _get_site_and_drive_id(token)
            list_id = self._get_list_id_by_name(token, site_id, LOG_LIST_NAME)

            patch_url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items/{log_item_id}"

            update_data = {
                "fields": {
                    "field_5": "SUCCESS",  # Durum
                    "field_4": final_filename,  # Yeni_Dosya
                    "field_6": file_hash,  # Hash
                }
            }

            r = requests.patch(
                patch_url, headers=_headers(token), json=update_data, timeout=30
            )
            if not r.ok:
                logger.error(f"SharePoint Complete Error: {r.text}")
                return False
            r.raise_for_status()

            logger.info(
                f"Log completed for ID: {log_item_id}. Final Name: {final_filename}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to complete log {log_item_id}: {e}")
            return False

    def fail_log(self, log_item_id: str, error_msg: str):
        """
        Step 3: Mark the log as failed if something goes wrong.
        """
        if not log_item_id:
            return

        try:
            token = get_graph_token()
            site_id, _ = _get_site_and_drive_id(token)
            list_id = self._get_list_id_by_name(token, site_id, LOG_LIST_NAME)

            patch_url = f"{GRAPH}/sites/{site_id}/lists/{list_id}/items/{log_item_id}"

            update_data = {
                "fields": {
                    "field_5": "ERROR",  # Durum
                    "field_4": f"HATA: {error_msg[:100]}",  # Yeni_Dosya'ya hata mesajı
                }
            }

            requests.patch(
                patch_url, headers=_headers(token), json=update_data, timeout=30
            )
        except Exception as e:
            logger.error(f"Failed to mark log as error {log_item_id}: {e}")


# --- TECHNICAL LOGGER MERGE ---
import threading
import re
import json
from typing import Optional, Dict, List

try:
    from sharepoint_uploader_graph import upload_file_to_sharepoint
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


class TechnicalLogger:
    _buffer: List[Dict] = []
    _lock = threading.Lock()

    @staticmethod
    def log(level: str, message: str, details: Optional[Dict] = None):
        """
        Logs a technical event to RAM buffer.
        If level is CRITICAL/ERROR, triggers immediate sync to Cloud.
        """
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": mask_sensitive_data(str(message)),
            "details": details or {},
        }

        # Add to RAM buffer
        with TechnicalLogger._lock:
            TechnicalLogger._buffer.append(log_entry)

        # Immediate sync for critical errors
        if level in ["ERROR", "CRITICAL"]:
            TechnicalLogger.sync_to_cloud()

    @staticmethod
    def sync_to_cloud():
        """
        Dumps RAM buffer to a JSON file and uploads to SharePoint.
        Then clears the buffer.
        """
        with TechnicalLogger._lock:
            if not TechnicalLogger._buffer:
                return

            data_to_sync = list(TechnicalLogger._buffer)

        if not upload_file_to_sharepoint:
            return

        try:
            # Create a temp JSON file
            # Use AppData for logs (Writable by user)
            from pathlib import Path
            LOGS_DIR = Path.home() / "AppData" / "Local" / "HukuDok" / "logs"
            LOGS_DIR.mkdir(parents=True, exist_ok=True)

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_filename = f"technical_log_{timestamp_str}_{socket.gethostname()}.json"
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

            # Clear buffer only on success
            with TechnicalLogger._lock:
                TechnicalLogger._buffer = []

        except Exception as e:
            logger.error(f"Technical Sync Failed: {e}")
