"""Paylaşılan hız sınırlayıcı (slowapi) — Faz 2-C'de api.py'den ayrıldı.

app kurulumu (api.py) bu instance'ı app.state.limiter'a bağlar; route
modülleri per-endpoint limit dekoratörü için buradan import eder — api'yi
import etmek döngü yaratırdı (api routes'u import ediyor).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from config.settings import settings


def _rate_limit_key(request):
    """Nginx proxy arkasında gerçek istemci IP'si X-Forwarded-For'dadır; doğrudan
    bağlantı IP'si kullanılırsa tüm kullanıcılar tek limit kovasını paylaşır.
    Backend portu yalnızca localhost + iç Docker ağına açık olduğundan header
    spoof'u dış istemciler için mümkün değildir."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# Varsayılan kovanın evi config/settings.py (env: RATE_LIMIT_DEFAULT, Faz 5-A).
limiter = Limiter(key_func=_rate_limit_key, default_limits=[settings.rate_limit_default])
