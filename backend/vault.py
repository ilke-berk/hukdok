import os
import json
import keyring
from dotenv import load_dotenv
import logging
from typing import Optional
from pathlib import Path

# Logger Ayarı - Ana logger ile çakışmaması için getLogger
logger = logging.getLogger("Vault")

SERVICE_NAME = "HukuDok_Automator"
KEYS_TO_MIGRATE = ["SHAREPOINT_CLIENT_SECRET", "GEMINI_API_KEY"]

import sys

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
if getattr(sys, 'frozen', False):
    ENV_PATH = Path(sys.executable).parent / ".env"
else:
    ENV_PATH = BASE_DIR / ".env"
# vault_sync.json should be in AppData (Writable)
DATA_DIR = Path.home() / "AppData" / "Local" / "HukuDok" / "data"
SYNC_STATE_FILE = DATA_DIR / "vault_sync.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_env_mtime() -> float:
    """Returns the modification time of .env file."""
    try:
        if ENV_PATH.exists():
            return ENV_PATH.stat().st_mtime
    except Exception:
        pass
    return 0.0


def _get_last_synced_mtime() -> float:
    """Returns the stored timestamp of the last successful sync."""
    try:
        if SYNC_STATE_FILE.exists():
            with open(SYNC_STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_mtime", 0.0)
    except Exception:
        pass
    return 0.0


def _update_last_synced_mtime(mtime: float):
    """Updates the stored timestamp."""
    try:
        _ensure_data_dir()
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump({"last_mtime": mtime}, f)
    except Exception as e:
        logger.warning(f"Failed to update vault sync state: {e}")


def sync_env_to_vault_if_needed():
    """
    Smart Sync: Checks if .env is newer than the last sync.
    If so, updates Vault with values from .env.
    """
    env_mtime = _get_env_mtime()
    last_sync = _get_last_synced_mtime()

    # If .env is missing or hasn't changed since last sync, skip
    if env_mtime == 0 or env_mtime <= last_sync:
        return

    logger.info(f".env change detected (Newer than last sync). Updating Vault...")

    # Reload env to ensure we captured the changes
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    updated_count = 0
    for key in KEYS_TO_MIGRATE:
        val = os.getenv(key)
        if val:
            try:
                keyring.set_password(SERVICE_NAME, key, val)
                updated_count += 1
            except Exception as e:
                logger.error(f"Failed to update vault for {key}: {e}")

    if updated_count > 0:
        logger.info(f"Smart Sync: Updated {updated_count} secrets in Windows Vault.")
        _update_last_synced_mtime(env_mtime)
    else:
        logger.info("Smart Sync: No relevant keys found in .env to update.")


def get_secret(key_name: str) -> Optional[str]:
    """
    Retrieves secret from Vault, performing a Smart Sync check first.
    """
    # 1. Smart Sync (.env newer? -> Update Vault)
    sync_env_to_vault_if_needed()

    # 2. Try Vault
    try:
        secret = keyring.get_password(SERVICE_NAME, key_name)
        if secret:
            return secret
    except Exception as e:
        logger.error(f"Vault access failed: {e}")

    # 3. Fallback: Direct Env Read (Soft Fail)
    # sync_env_to_vault_if_needed already loaded env if available
    val = os.getenv(key_name)
    if val:
        return val

    logger.warning(f"Secret '{key_name}' not found in Vault or .env")
    return None


def migrate_all():
    """Manually triggers sync mechanism."""
    logging.info("--- Vault Migration / Verify ---")
    sync_env_to_vault_if_needed()
    for key in KEYS_TO_MIGRATE:
        val = get_secret(key)
        status = "OK" if val else "MISSING"
        logging.info(f"{key}: {status}")



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_all()
