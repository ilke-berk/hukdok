import os
import time
import msal
import logging
from datetime import date, datetime
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

import vault
# /healthz sinyalleri (Faz 2-A): stdlib-only modül, script bağlamlarında da güvenli
import health

# Global variable to hold the MSAL app instances (Dictionary for Multi-Config)
_MSAL_APPS = {}
logger = logging.getLogger("AuthGraph")

# G093 (O7): client secret bitiş tarihi uyarı eşiği (gün). Entra'daki secret'ın
# ömrü başka hiçbir yerde izlenmiyor; bu eşiğin altında açılışta WARNING,
# tarih geçince CRITICAL basılır. 30 gün = bir rotasyon turu için rahat pay.
SECRET_EXPIRY_WARN_DAYS = 30
SECRET_EXPIRES_AT_ENV = "SHAREPOINT_CLIENT_SECRET_EXPIRES_AT"


def check_client_secret_expiry(today: Optional[date] = None) -> Optional[str]:
    """Açılışta (lifespan) bir kez koşar; yalnız log basar, asla istisna atmaz.

    `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` (ISO tarih, örn. 2027-03-15):
    - tanımsız/boş → sessiz, hiçbir şey olmaz (geriye tam uyumlu)
    - kalan gün ≤ SECRET_EXPIRY_WARN_DAYS → WARNING (kalan gün sayısıyla)
    - tarih geçmiş → CRITICAL
    - ayrıştırılamıyor → bir kez WARNING, yok sayılır (toleranslı ayrıştırma;
      config/settings.py sözleşmesiyle aynı — konfig hatası uygulamayı düşürmez)
    Secret'ın KENDİSİ bu fonksiyona hiç girmez; log satırlarında yalnız tarih var.
    Dönüş: basılan seviye adı ("warning"/"critical") ya da None — test kolaylığı.
    /healthz'e bilinçli EKLENMEZ (gövde dışarıya açık).
    """
    raw = (os.getenv(SECRET_EXPIRES_AT_ENV) or "").strip()
    if not raw:
        return None
    try:
        expires_at = datetime.fromisoformat(raw).date()
    except ValueError:
        logger.warning(
            "%s=%r ayrıştırılamadı (ISO tarih bekleniyor, örn. 2027-03-15) — "
            "secret ömrü izlenmiyor, değer yok sayıldı.", SECRET_EXPIRES_AT_ENV, raw,
        )
        return "warning"
    today = today or date.today()
    remaining = (expires_at - today).days
    if remaining < 0:
        logger.critical(
            "SharePoint client secret'ının süresi DOLDU (%s, %d gün önce) — Graph "
            "çağrıları 401 dönecek, arşivleme akışı durur. Entra'da yeni secret "
            "üretilip SHAREPOINT_CLIENT_SECRET ve %s güncellenmeli.",
            expires_at.isoformat(), -remaining, SECRET_EXPIRES_AT_ENV,
        )
        return "critical"
    if remaining <= SECRET_EXPIRY_WARN_DAYS:
        logger.warning(
            "SharePoint client secret'ının süresi %d gün sonra doluyor (%s) — "
            "Entra'da rotasyon planlanmalı.", remaining, expires_at.isoformat(),
        )
        return "warning"
    return None


def _get_msal_app(config_type: str = "default") -> msal.ConfidentialClientApplication:
    """
    Returns the cached MSAL app instance for the specified config.
    config_type: 'default' (Metadata/Old) or 'upload' (File Upload/New)
    """
    global _MSAL_APPS
    if config_type in _MSAL_APPS:
        return _MSAL_APPS[config_type]

    import sys
    if getattr(sys, 'frozen', False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent / ".env"

    load_dotenv(dotenv_path=env_path, override=True)

    # Always use default (Old/Main Archive) credentials
    if config_type == "upload":
        # Just log for clarity, but use default creds
        logger.debug("Auth: Using default credentials for upload (Single-Tenant Mode).")

    tenant_id = os.getenv("SHAREPOINT_TENANT_ID")
    client_id = os.getenv("SHAREPOINT_CLIENT_ID")
    # Try vault first, then env
    client_secret = vault.get_secret("SHAREPOINT_CLIENT_SECRET")
    if not client_secret:
        client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise RuntimeError(
            "Missing env: SHAREPOINT_TENANT_ID / SHAREPOINT_CLIENT_ID / SHAREPOINT_CLIENT_SECRET"
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret,
    )
    
    _MSAL_APPS[config_type] = app
    logger.info(f"MSAL Application Initialized ({config_type})")
    return app


def get_graph_token(config_type: str = "default", force_refresh: bool = False) -> str:
    """
    Acquires a token from MSAL.
    config_type: 'default' or 'upload'
    force_refresh: True ise MSAL cache'i düşürülür ve AAD'den taze token istenir.
    Graph 401 döndüğünde çağıran bir kez bununla tekrar dener (Faz 3-B):
    cache'teki token süresi dolmadan sunucuda geçersizleşmiş olabilir
    (secret rotasyonu, revoke, koşullu erişim).
    """
    app = _get_msal_app(config_type)

    if force_refresh:
        try:
            # msal>=1.27: bu client'ın cache'lenmiş app token'larını düşürür
            app.remove_tokens_for_client()
        except Exception:
            # Eski msal ya da beklenmedik durum: app nesnesini atmak da cache'i
            # sıfırlar (client-credential akışı durumsuz, yeniden kurmak ucuz)
            _MSAL_APPS.pop(config_type, None)
            app = _get_msal_app(config_type)
        logger.info(f"Graph token cache düşürüldü, taze token alınacak ({config_type})")

    result = None
    for attempt in range(2):
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" in result:
            # MSAL cache'ten dönüş de "auth çalışıyor" sinyalidir; /healthz
            # graph_token_age_seconds bu damgadan hesaplanır.
            health.record_graph_token_ok()
            return result["access_token"]
        if attempt == 0:
            logger.warning(f"Graph token alınamadı, 5sn sonra tekrar deneniyor: {result.get('error')}")
            time.sleep(5)

    logger.error(f"Graph token failed ({config_type}): {result.get('error')}")
    health.record_graph_token_fail()
    raise RuntimeError(f"Graph token failed: {result}")
