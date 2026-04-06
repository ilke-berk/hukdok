import json
import logging
from typing import Optional

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth_verifier import AuthVerifier
from config_manager import get_log_dir

security_scheme = HTTPBearer()


class SecurityEventLogger:
    """Dedicated logger for security events with file persistence."""

    def __init__(self):
        log_dir = get_log_dir()
        self.log_file = log_dir / "security.log"

        self.logger = logging.getLogger("SecurityEvents")
        self.logger.setLevel(logging.INFO)

        handler = logging.FileHandler(self.log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(handler)

    def log_event(self, event_type: str, severity: str, detail: str, metadata: dict = None):
        event_data = {
            "type": event_type,
            "severity": severity,
            "detail": detail,
            "metadata": metadata or {},
        }
        log_message = json.dumps(event_data, ensure_ascii=False)

        if severity == "ERROR":
            self.logger.error(log_message)
        elif severity == "WARNING":
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)


security_logger = SecurityEventLogger()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=True)),
):
    """Validates the Bearer token. Strict Mode (No Mock User)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    claims = AuthVerifier.verify_token(token)

    if not claims:
        raise HTTPException(status_code=401, detail="Invalid token")

    return claims
