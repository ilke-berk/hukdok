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
_MSAL_APPS: dict = {}
logger = logging.getLogger("AuthGraph")

# G147: iki kimlik seti. `default` = arşiv (LexisBio tenant'ı: belge arşivi,
# ofis-no sayacı, `log` listesi, e-posta, hukukbot export'u — DEĞİŞMEZ);
# `teslim` = yalnız veri teslim hattı (gözcü listeleme/indirme + cevap paketi),
# Hanyaloğlu tenant'ındaki ikinci uygulama kaydı. `teslim` için üç env'den biri
# bile boşsa default sete düşülür (geriye tam uyumlu: prod `.env` değişmeden
# davranış aynı). Eski `"upload"` config'i ölü koddu — kaldırıldı.
CONFIG_DEFAULT = "default"
CONFIG_TESLIM = "teslim"
CONFIG_TYPES = (CONFIG_DEFAULT, CONFIG_TESLIM)
#: config → env öneki (`<önek>TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET`).
_ENV_PREFIX = {CONFIG_DEFAULT: "SHAREPOINT_", CONFIG_TESLIM: "TESLIM_SHAREPOINT_"}
#: `teslim` → default düşüşü bir kez INFO basar (süreç ömrü boyunca).
_teslim_dusus_loglandi = False

# G093 (O7): client secret bitiş tarihi uyarı eşiği (gün). Entra'daki secret'ın
# ömrü başka hiçbir yerde izlenmiyor; bu eşiğin altında açılışta WARNING,
# tarih geçince CRITICAL basılır. 30 gün = bir rotasyon turu için rahat pay.
SECRET_EXPIRY_WARN_DAYS = 30
SECRET_EXPIRES_AT_ENV = "SHAREPOINT_CLIENT_SECRET_EXPIRES_AT"
#: G147: teslim kimliğinin secret bitiş tarihi (lifespan ikinci çağrı; tanımsızsa sessiz).
TESLIM_SECRET_EXPIRES_AT_ENV = "TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT"


def check_client_secret_expiry(
    today: Optional[date] = None, env_name: str = SECRET_EXPIRES_AT_ENV,
) -> Optional[str]:
    """Açılışta (lifespan) bir kez koşar; yalnız log basar, asla istisna atmaz.

    `env_name` (varsayılan `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT`; G147 ikinci çağrı
    `TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` ile) ISO tarih, örn. 2027-03-15:
    - tanımsız/boş → sessiz, hiçbir şey olmaz (geriye tam uyumlu)
    - kalan gün ≤ SECRET_EXPIRY_WARN_DAYS → WARNING (kalan gün sayısıyla)
    - tarih geçmiş → CRITICAL
    - ayrıştırılamıyor → bir kez WARNING, yok sayılır (toleranslı ayrıştırma;
      config/settings.py sözleşmesiyle aynı — konfig hatası uygulamayı düşürmez)
    Secret'ın KENDİSİ bu fonksiyona hiç girmez; log satırlarında yalnız tarih ve
    env ADI var. Dönüş: basılan seviye adı ("warning"/"critical") ya da None —
    test kolaylığı. /healthz'e bilinçli EKLENMEZ (gövde dışarıya açık).
    """
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return None
    # `<X>_CLIENT_SECRET_EXPIRES_AT` → `<X>_CLIENT_SECRET`: mesajda güncellenecek env adı
    secret_env = env_name[: -len("_EXPIRES_AT")] if env_name.endswith("_EXPIRES_AT") else env_name
    etiket = "Veri teslim SharePoint" if env_name == TESLIM_SECRET_EXPIRES_AT_ENV else "SharePoint"
    try:
        expires_at = datetime.fromisoformat(raw).date()
    except ValueError:
        logger.warning(
            "%s=%r ayrıştırılamadı (ISO tarih bekleniyor, örn. 2027-03-15) — "
            "secret ömrü izlenmiyor, değer yok sayıldı.", env_name, raw,
        )
        return "warning"
    today = today or date.today()
    remaining = (expires_at - today).days
    if remaining < 0:
        logger.critical(
            "%s client secret'ının süresi DOLDU (%s, %d gün önce) — Graph "
            "çağrıları 401 dönecek, arşivleme akışı durur. Entra'da yeni secret "
            "üretilip %s ve %s güncellenmeli.",
            etiket, expires_at.isoformat(), -remaining, secret_env, env_name,
        )
        return "critical"
    if remaining <= SECRET_EXPIRY_WARN_DAYS:
        logger.warning(
            "%s client secret'ının süresi %d gün sonra doluyor (%s) — "
            "Entra'da rotasyon planlanmalı.", etiket, remaining, expires_at.isoformat(),
        )
        return "warning"
    return None


def _load_env() -> None:
    import sys
    if getattr(sys, 'frozen', False):
        env_path = Path(sys.executable).parent / ".env"
    else:
        env_path = Path(__file__).resolve().parent.parent / ".env"

    load_dotenv(dotenv_path=env_path, override=True)


def _read_credentials(config_type: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """`<önek>TENANT_ID` / `CLIENT_ID` env'den; `CLIENT_SECRET` önce vault, sonra env.

    Tenant ya da client id boşsa secret HİÇ aranmaz: `vault.get_secret` bulamayınca
    WARNING basar, teslim kimliği tanımsız prod'da her açılışta sahte uyarı olurdu.
    """
    prefix = _ENV_PREFIX[config_type]
    tenant_id = (os.getenv(f"{prefix}TENANT_ID") or "").strip() or None
    client_id = (os.getenv(f"{prefix}CLIENT_ID") or "").strip() or None
    client_secret: Optional[str] = None
    if tenant_id and client_id:
        client_secret = vault.get_secret(f"{prefix}CLIENT_SECRET")
        if not client_secret:
            client_secret = os.getenv(f"{prefix}CLIENT_SECRET")
    return tenant_id, client_id, client_secret


def _get_msal_app(config_type: str = CONFIG_DEFAULT) -> msal.ConfidentialClientApplication:
    """Returns the cached MSAL app instance for the specified config.

    config_type: `"default"` (arşiv — `SHAREPOINT_*`) ya da `"teslim"` (veri teslim
    hattı — `TESLIM_SHAREPOINT_*`; üçlüden biri boşsa default sete düşer ve BİR KEZ
    INFO basar). `_MSAL_APPS` anahtarı config_type'tır: düşüşte bile ayrı bir app
    (ayrı token cache) kurulur — anahtar uzayı değişmez, `force_refresh` yolu
    (`get_graph_token`) config'e sadık kalır.
    """
    global _MSAL_APPS, _teslim_dusus_loglandi
    if config_type in _MSAL_APPS:
        return _MSAL_APPS[config_type]
    if config_type not in CONFIG_TYPES:
        raise ValueError(f"Bilinmeyen SharePoint config_type: {config_type!r} (beklenen: {CONFIG_TYPES})")

    _load_env()

    tenant_id, client_id, client_secret = _read_credentials(config_type)
    if config_type == CONFIG_TESLIM and not all([tenant_id, client_id, client_secret]):
        if not _teslim_dusus_loglandi:
            logger.info(
                "Veri teslim SharePoint kimliği tanımsız (TESLIM_SHAREPOINT_TENANT_ID / "
                "CLIENT_ID / CLIENT_SECRET), arşiv kimliği kullanılıyor."
            )
            _teslim_dusus_loglandi = True
        tenant_id, client_id, client_secret = _read_credentials(CONFIG_DEFAULT)

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


def get_graph_token(config_type: str = CONFIG_DEFAULT, force_refresh: bool = False) -> str:
    """
    Acquires a token from MSAL.
    config_type: 'default' (arşiv) or 'teslim' (veri teslim hattı, G147)
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
