import os
import requests
import logging
from urllib.parse import urlparse, quote
from dotenv import load_dotenv
from pathlib import Path
from functools import lru_cache

from auth_graph import get_graph_token

GRAPH = "https://graph.microsoft.com/v1.0"
logger = logging.getLogger("SharePointUploader")


def _load_env():
    import sys
    if getattr(sys, 'frozen', False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    
    load_dotenv(dotenv_path=env_path, override=True)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_ssl_verify_option():
    """Returns the SSL verification option (path to cert or True/False)."""
    ssl_cert = os.getenv("SSL_CERT_FILE")
    if ssl_cert and os.path.exists(ssl_cert):
        return ssl_cert
    return True


@lru_cache(maxsize=1)
def _get_site_and_drive_id(token: str, config_type: str = "default") -> tuple[str, str]:
    _load_env()
    
    # Always use the main SHAREPOINT_SITE_URL (Single-Site Mode)
    site_url = os.getenv("SHAREPOINT_SITE_URL")
    
    if config_type == "upload":
        logger.debug("Uploader: Using main site for upload (config='upload' -> default site).")

    drive_name = os.getenv(
        "SP_DRIVE_NAME", "Belgeler"
    )  # Default to "Belgeler" (Documents)

    if not site_url:
        raise RuntimeError(f"Missing env: SHAREPOINT_SITE_URL (config: {config_type})")

    u = urlparse(site_url)
    hostname = u.netloc
    site_path = u.path if u.path else "/"

    # 1. Get Site ID
    logger.debug(f"Fetching Site ID for {hostname} ({config_type})")
    r = requests.get(
        f"{GRAPH}/sites/{hostname}:{site_path}", headers=_headers(token), timeout=60
    )
    r.raise_for_status()
    site_id = r.json()["id"]

    # 2. Get Drives (Document Libraries)
    logger.debug(f"Fetching Drives for Site ID: {site_id}")
    r = requests.get(
        f"{GRAPH}/sites/{site_id}/drives", headers=_headers(token), timeout=60
    )
    r.raise_for_status()
    drives = r.json().get("value", [])
    if not drives:
        raise RuntimeError("No drives found on SharePoint site.")

    # 3. Find specific Drive (e.g. "Belgeler")
    for d in drives:
        # Check both 'name' (internal) and decoded name just in case
        if d.get("name") == drive_name or d.get("name") == "Documents":
            # Note: "Belgeler" usually maps to "Documents" (internal name) in some tenants, or stays localized.
            # We search for the drive name specified in ENV or fallback to checking the list.
            return site_id, d["id"]

    # If explicit name not found, try searching loosely or fallback
    names = [d.get("name") for d in drives]

    # Fallback: If drive_name is "Belgeler" but not found, look for "Documents"
    if drive_name == "Belgeler" and "Documents" in names:
        for d in drives:
            if d.get("name") == "Documents":
                return site_id, d["id"]

    raise RuntimeError(f"Drive '{drive_name}' not found. Available: {names}")


def _create_upload_session(
    session: requests.Session,
    token: str,
    drive_id: str,
    filename: str,
    folder_name: str,
) -> str:
    # Pattern: /drives/{id}/root:/{folder}/{filename}:/createUploadSession
    path = quote(f"{folder_name}/{filename}")
    url = f"{GRAPH}/drives/{drive_id}/root:/{path}:/createUploadSession"

    body = {"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}}
    r = session.post(
        url,
        headers=_headers(token) | {"Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["uploadUrl"]


def upload_file_to_sharepoint(
    filepath: str,
    target_filename: str,
    target_folder_name: str,
    content_type: str = "application/pdf",
    use_date_subfolder: bool = False,
    metadata: dict = None,
) -> dict:
    """
    SharePoint'e Graph ile upload (Secure Cloud Archive Mode).
    Uses 'upload' configuration (New Site).
    
    Args:
        filepath: Yüklenecek dosyanın yerel yolu
        target_filename: SharePoint'teki dosya adı
        target_folder_name: Hedef klasör adı (örn: "01_HAM_ARSIV")
        content_type: MIME type
        use_date_subfolder: True ise YYYY-MM-DD formatında alt klasör oluşturur
        
    Returns:
        SharePoint API response
    """
    # Use Default (Main) config
    token = get_graph_token(config_type="default")

    # _get_site_and_drive_id is now Cached
    _site_id, drive_id = _get_site_and_drive_id(token, config_type="default")
    
    # Tarih bazlı alt klasör oluştur
    if use_date_subfolder:
        from datetime import datetime
        date_folder = datetime.now().strftime("%Y-%m-%d")
        target_folder_name = f"{target_folder_name}/{date_folder}"
        logger.info(f"📅 Tarih klasörü kullanılıyor: {target_folder_name}")

    # 1. Dosya Boyutunu Kontrol Et
    file_size = os.path.getsize(filepath)
    safe_path = quote(f"{target_folder_name}/{target_filename}")

    # Create Session for connection reuse
    session = requests.Session()
    session.verify = get_ssl_verify_option()

    try:
        # --- SMALL FILE UPLOAD (< 4MB) ---
        if file_size < 4 * 1024 * 1024:
            # Small file upload
            upload_url = f"{GRAPH}/drives/{drive_id}/root:/{safe_path}:/content"

            with open(filepath, "rb") as f:
                r = session.put(
                    upload_url,
                    headers=_headers(token) | {"Content-Type": content_type},
                    data=f,
                    timeout=180,
                )
            r.raise_for_status()
            data = r.json()
            if metadata:
                _update_list_item_fields(session, token, drive_id, data["id"], metadata)
            return data

        # --- LARGE FILE UPLOAD (> 4MB) ---
        logger.info(f"📦 Büyük Dosya Modu (>4MB) - Chunk Upload: {target_filename}")

        upload_url = _create_upload_session(
            session, token, drive_id, target_filename, target_folder_name
        )
        chunk_size = 5 * 1024 * 1024  # 5MB chunks

        with open(filepath, "rb") as f:
            start = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                length = len(chunk)
                end = start + length - 1

                headers = {
                    "Content-Length": str(length),
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                }

                # Chunk'ı gönder (Session Reuse)
                r = session.put(upload_url, headers=headers, data=chunk, timeout=300)

                if r.status_code in (200, 201):
                    logger.info(f"✅ Upload Tamamlandı: {target_filename}")
                    data = r.json()
                    if metadata:
                        _update_list_item_fields(session, token, drive_id, data["id"], metadata)
                    return data

                if r.status_code != 202:
                    raise RuntimeError(f"Upload chunk failed: {r.status_code} {r.text}")

                start += length

        raise RuntimeError("Upload session finished without 200/201 response.")

    except Exception as e:
        logger.error(f"SharePoint Upload Error: {e}")
        raise e
    finally:
        session.close()

def _update_list_item_fields(session, token, drive_id, item_id, fields):
    """Updates the ListItem fields for a given DriveItem."""
    logger.info(f"📝 Metadata Güncelleniyor: {fields}")
    url = f"{GRAPH}/drives/{drive_id}/items/{item_id}/listItem/fields"
    
    r = session.patch(
        url,
        headers=_headers(token) | {"Content-Type": "application/json"},
        json=fields,
        timeout=30
    )
    if r.status_code != 200:
        logger.error(f"⚠️ Metadata update failed: {r.text}")
        # We don't raise exception here to not fail the whole upload if just metadata fails
    else:
        logger.info("✅ Metadata başarıyla işlendi.")

