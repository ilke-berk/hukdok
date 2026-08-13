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
#
# NOT (G057): bu bir WINDOWS yoludur ve masaüstü çağından kalmadır. Linux
# konteynerinde `Path.home()/"AppData"/...` diye bir yer yoktur; prod'da
# 2026-08-13'te bakıldı — `/root/AppData` HİÇ OLUŞMAMIŞ. Zararsız olmasının
# sebebi yolun hiç yazılmaması: senkron yalnız `.env` keyring'e taşınacaksa
# koşar, konteynerde ise backend null olduğu için o yola zaten girilmiyor.
# BİLEREK düzeltilmedi — düzeltmek konteynerde yeni bir yazılabilir dizin
# ihtiyacı doğurur ve bugün hiçbir şeyi çözmez. Ölü ama sessiz olmasın diye
# burada işaretlendi.
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


# ── Düz metin backend'e sır YAZMA koruması (G057) ────────────────────────────
#
# Konteynerde `docker-compose.yml` `PYTHON_KEYRING_BACKEND=...null.Keyring`
# veriyor; null backend hiçbir şey saklamaz ve `get_secret` aşağıdaki env
# fallback'ine düşer — bugünkü prod davranışı budur.
#
# AMA o env satırı düşerse keyring backend'i ÖNCELİĞE göre kendi seçer ve bu
# imajda kurulu backend'lerin en yüksek öncelikli olanı
# `keyrings.alt.file.PlaintextKeyring`'dir (0.5; fail=0, null=-1). O durumda
# `set_password` iki sırrı da DÜZ METİN dosyaya yazardı. Prod'da 2026-08-13'te
# ölçüldü: aktif backend null, düz metin dosyası yok — yani bugün güvenli, ama
# güvenliği tek bir yorumsuz compose satırına yaslıydı.
#
# Bu kapı o yaslanmayı kaldırır: yazma yolu düz metin bir backend gördüğünde
# YAZMAZ. Okuma yolu etkilenmez (env fallback zaten var), yani işlevsel kayıp
# yok — yalnız sırların diske düz metin düşmesi engellenir.
# Windows geliştirme makinesindeki `WinVaultKeyring` bu kapıya TAKILMAZ.
_UNSAFE_BACKEND_MODULE_PREFIX = "keyrings.alt"

# Uyarı süreç başına BİR kez: `get_secret` her çağrıda sync'i yokluyor, her
# seferinde WARNING basmak log sözleşmesini gürültüye boğardı.
_unsafe_backend_warned = False


def _backend_write_safe() -> tuple[bool, str]:
    """Aktif keyring backend'ine sır yazmak güvenli mi? (güvenli_mi, backend_adı)"""
    try:
        kr = keyring.get_keyring()
    except Exception as e:  # backend çözülemedi — yazma, oku ve devam et
        return False, f"<backend okunamadı: {type(e).__name__}>"
    ad = f"{type(kr).__module__}.{type(kr).__name__}"
    return (not type(kr).__module__.startswith(_UNSAFE_BACKEND_MODULE_PREFIX)), ad


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

    safe, backend_name = _backend_write_safe()
    if not safe:
        global _unsafe_backend_warned
        if not _unsafe_backend_warned:
            _unsafe_backend_warned = True
            logger.warning(
                f"Keyring backend '{backend_name}' sırları DÜZ METİN saklar — "
                "senkron atlandı, sırlar yalnız ortam değişkeninden okunacak. "
                "Beklenen ayar: PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring"
            )
        return

    logger.info(".env change detected (Newer than last sync). Updating Vault...")

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
    from logging_setup import configure_logging

    configure_logging()
    migrate_all()
