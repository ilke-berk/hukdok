"""Merkezi loglama (Faz 2-B): tek dictConfig + JSON formatter + request-id.

Önceki durum: 11 modülde dağınık `logging.basicConfig` — Python'da ilk çağrı
kazanır, sonrakiler sessiz no-op'tur; aktif format import sırasına bağlıydı.
Artık tek yapılandırma noktası burasıdır: api.py (uvicorn), migrate.py ve CLI
koşuları (`vault.py`, `udf_converter.py`, ...) başta `configure_logging()`
çağırır; modüller yalnız `logging.getLogger(...)` kullanır.

Ortam değişkenleri:
- LOG_FORMAT=json|text (varsayılan text). Konteynerde compose json set eder;
  GCP Ops Agent'ın log tabanlı alarmları (Faz 2-C) severity alanını buradan okur.
- LOG_LEVEL (varsayılan INFO).

Request-id: RequestIdMiddleware her HTTP isteğe kimlik atar (gelen X-Request-ID
korunur, yoksa üretilir), contextvar'a koyar ve yanıt başlığında döndürür.
Handler'a bağlı RequestIdFilter kimliği her log kaydına işler — istek sırasında
üretilen tüm loglar (`asyncio.create_task` ile kopan pipeline dahil; contextvar
task'a kopyalanır) aynı kimliği taşır, bir `/confirm` yolculuğu
`docker logs hukdok_backend | grep <id>` ile uçtan uca izlenir.
`threading.Thread` contextvar KOPYALAMAZ — arkaplan thread'lerinin loglarında
"-" görünmesi bilinçlidir (istek bağlamı yok).
"""
import contextvars
import json
import logging
import logging.config
import os
import re
import time
import uuid
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# Gelen X-Request-ID sanitizasyonu: header log satırına yazıldığı için kontrol
# karakterleri / log injection ayıklanır, uzunluk sınırlanır.
_RID_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_RID_MAX = 64


class RequestIdFilter(logging.Filter):
    """Her kayda contextvar'daki request_id'yi işler (istek dışı bağlamda '-')."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


# JsonFormatter'ın "extra" ayıklaması: standart LogRecord alanları bunlar;
# geri kalan her alan çağrıdaki extra={...}'dan gelmiştir, JSON'a aynen girer.
# ("taskName" py3.12'de eklendi — konteyner 3.10'da yok, ileriye dönük.
# "color_message" uvicorn'un ANSI'li kopyası — düz message zaten var.)
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "request_id", "taskName", "color_message"}


class JsonFormatter(logging.Formatter):
    """Satır başına tek JSON nesnesi (GCP Ops Agent'ın ayrıştırdığı biçim).

    Alan adı uzlaşımı GCP structured logging ile hizalı: `severity` LogEntry
    önem düzeyine eşlenir — Faz 2-C'deki ERROR-oranı alarmının filtresi budur.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "location": f"{record.module}:{record.lineno}",
            # Faz 3-E: uvicorn --workers N'de satırın hangi worker'dan geldiği
            # (süreç-içi durumlar — devre kesici, health sayaçları — worker
            # başına olduğundan) teşhiste gerekir.
            "pid": record.process,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Tek dictConfig; tekrar çağrılması güvenlidir (aynı sonucu kurar)."""
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    logging.config.dictConfig(
        {
            "version": 1,
            # Import sırasından bağımsızlık: önceden getLogger ile yaratılmış
            # logger'lar (SecurityEvents'in dosya handler'ı dahil) devre dışı
            # kalmaz — yalnız kök handler'lar buradakiyle değiştirilir.
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "text": {
                    "format": (
                        "%(asctime)s %(levelname)s [%(name)s] "
                        "[%(request_id)s] %(message)s"
                    ),
                },
                "json": {"()": JsonFormatter},
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    # stderr DEĞİL: bazı toplayıcılar stderr satırını koşulsuz
                    # ERROR sayar; önem düzeyi JSON'daki severity'den gelmeli.
                    "stream": "ext://sys.stdout",
                    "formatter": "json" if log_format == "json" else "text",
                    "filters": ["request_id"],
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
            "loggers": {
                # uvicorn CLI logging'i app import'undan ÖNCE kurar; bu kayıtlar
                # onun handler'larını bizimkilerle değiştirir (tek biçim aksın).
                "uvicorn": {
                    "level": "INFO", "handlers": ["stdout"], "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO", "handlers": ["stdout"], "propagate": False,
                },
                # Erişim satırını RequestIdMiddleware üretir (kimlik + süre ile);
                # uvicorn.access'inki aynı isteğin kimliksiz kopyası olurdu.
                "uvicorn.access": {
                    "level": "WARNING", "handlers": ["stdout"], "propagate": False,
                },
            },
        }
    )


# Erişim logu üretilmeyen yollar: sağlık yoklamaları (compose 30 sn +
# uptime check bölgeleri) log hacmini boğar, bilgi değeri sıfır.
ACCESS_LOG_EXEMPT_PATHS = frozenset({"/healthz", "/"})

_access_logger = logging.getLogger("access")


class RequestIdMiddleware:
    """Saf ASGI middleware: request-id ataması + istek başına tek erişim satırı.

    BaseHTTPMiddleware bilinçli kullanılmadı: her isteği ek bir task + anyio
    memory-stream katmanından geçirir (Faz 0'daki event-loop hassasiyetinin
    komşusu); saf sarmalayıcının ek maliyeti yoktur ve contextvar, downstream
    app ile aynı task bağlamında kalır.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = _RID_SAFE.sub("", incoming)[:_RID_MAX] or uuid.uuid4().hex[:12]

        path = scope.get("path", "")
        method = scope.get("method", "-")
        # Gerçek istemci IP'si nginx arkasında X-Forwarded-For'dadır
        # (bkz. rate_limiting._rate_limit_key — backend portu dışa kapalı, spoof edilemez).
        xff = headers.get(b"x-forwarded-for", b"").decode("latin-1")
        client_ip = (
            xff.split(",")[0].strip()
            if xff
            else (scope.get("client") or ("-",))[0]
        )

        status_box = {"status": None}

        async def send_with_rid(message):
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
                raw = list(message.get("headers") or [])
                raw.append((b"x-request-id", rid.encode("latin-1")))
                message["headers"] = raw
            await send(message)

        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_rid)
            if path not in ACCESS_LOG_EXEMPT_PATHS:
                duration_ms = round((time.perf_counter() - start) * 1000)
                status = status_box["status"] or 0
                _access_logger.info(
                    f"{method} {path} {status} {duration_ms}ms",
                    extra={
                        "method": method,
                        "path": path,
                        "status_code": status,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                    },
                )
        except Exception:
            # ServerErrorMiddleware bizden dışarıda: istisna 500'e dönmeden önce
            # kimlikli tek ERROR satırı düşülür (uvicorn'un kendi traceback'i
            # contextvar reset'inden sonra aktığı için request_id taşımaz).
            duration_ms = round((time.perf_counter() - start) * 1000)
            _access_logger.error(
                f"{method} {path} 500 {duration_ms}ms",
                exc_info=True,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            raise
        finally:
            request_id_var.reset(token)
