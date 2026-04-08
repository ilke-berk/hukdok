import os
import msal
import logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

import vault

# Global variable to hold the MSAL app instances (Dictionary for Multi-Config)
_MSAL_APPS = {}
logger = logging.getLogger("AuthGraph")


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


def get_graph_token(config_type: str = "default") -> str:
    """
    Acquires a token from MSAL.
    config_type: 'default' or 'upload'
    """
    app = _get_msal_app(config_type)

    # 1. Look in cache first
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" in result:
        # success
        return result["access_token"]
    else:
        logger.error(f"Graph token failed ({config_type}): {result.get('error')}")
        raise RuntimeError(f"Graph token failed: {result}")
