import os
import sys
import traceback
import logging
import argparse
import tempfile
import glob
import shutil
import threading
import time
from datetime import datetime
from contextlib import asynccontextmanager

# Kök logger yapılandırması — bu olmadan kök logger WARNING seviyesinde kalır
# ve tüm logging.info() çağrıları sessizce düşer.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# --- STARTUP DEBUG LOGGING ---
def write_startup_log(msg):
    try:
        from managers.config_manager import get_log_dir
        log_dir = get_log_dir()
        log_file = log_dir / "startup_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass

write_startup_log("--- BACKEND STARTUP INITIATED ---")
write_startup_log(f"CWD: {os.getcwd()}")
write_startup_log(f"Executable: {sys.executable}")
write_startup_log(f"Arguments: {sys.argv}")

# Force UTF-8 (Fix for Windows Console)
if sys.stdout and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

write_startup_log("DEBUG: API Loading started...")

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

try:
    write_startup_log("Attempting to import modules...")
    from managers.config_manager import DynamicConfig
    from managers.log_manager import LogManager, TechnicalLogger
    from routes.processing import refresh_lists_background
    write_startup_log("All local modules imported successfully.")
except Exception as ie:
    error_msg = f"CRITICAL IMPORT ERROR: {ie}"
    print(error_msg, flush=True)
    write_startup_log(error_msg)
    write_startup_log(traceback.format_exc())
    traceback.print_exc()
    sys.exit(1)

try:
    from managers import cache_manager
except ImportError:
    logging.warning("Cache module missing.")
    cache_manager = None

load_dotenv()

try:
    log_manager = LogManager()
except Exception:
    log_manager = None

ssl_cert = os.getenv("SSL_CERT_FILE")
if ssl_cert and os.path.exists(ssl_cert):
    os.environ["REQUESTS_CA_BUNDLE"] = ssl_cert


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("API Starting...")
    write_startup_log("API Startup Event triggered")

    # G5: dev auth bypass'ı için üç env koşulu birden gerekir (bkz. auth_verifier).
    # Kombinasyon DEV_MODE olmadan görülürse muhtemel yanlış prod konfigürasyonudur.
    if (os.getenv("ENV") == "development" and os.getenv("ALLOW_DEV_TENANT") == "true"
            and os.getenv("DEV_MODE", "").lower() != "true"):
        logging.critical(
            "ENV=development + ALLOW_DEV_TENANT=true ayarlı ama DEV_MODE=true değil — "
            "dev auth bypass DEVRE DIŞI. Bu değişkenler prod ortamında set edilmemeli."
        )

    try:
        # Konteynerde migrasyonlar entrypoint'teki migrate.py'de zaten koştu;
        # burası host-run (python api.py) için yedek ve tek worker'da zararsız.
        # uvicorn --workers N'e geçmeden önce bu çağrı kaldırılmalı/kapılanmalı
        # (worker başına lifespan koşar → DDL yarışı; bkz. Faz 3-E notu).
        from database import init_db
        init_db()
    except Exception as e:
        logging.critical(f"Database Init Failed: {e}")
        write_startup_log(f"Database Init Failed: {e}")

    config = DynamicConfig.get_instance()

    if cache_manager:
        cached_data = cache_manager.load_cache()
        if cached_data:
            config.set_lawyers(cached_data.get("lawyers", []))
            config.set_statuses(cached_data.get("statuses", []))
            config.set_doctypes(cached_data.get("doctypes", []))
            config.set_clients(cached_data.get("clients", []))
            email_recipients = cached_data.get("email_recipients", [])
            if email_recipients:
                config.set_email_recipients(email_recipients)
            logging.info("Cache loaded successfully.")
        else:
            logging.warning("Cache empty. Use refresh button to load data.")

    # Seed static lists if tables are empty
    try:
        from managers.seed_data import seed_all_lists
        seed_all_lists()
        logging.info("Seed check completed.")
    except Exception as e:
        logging.warning(f"Seed failed: {e}")

    import threading
    threading.Thread(target=refresh_lists_background, daemon=True).start()
    logging.info("Background refresh thread started.")

    # Günlük aktivite raporu zamanlayıcısı (her gece 00:00 Türkiye saatiyle)
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from managers.activity_manager import generate_daily_reports, catch_up_missed_reports
        import pytz

        scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Istanbul"))
        scheduler.add_job(
            generate_daily_reports,
            CronTrigger(hour=0, minute=0, timezone=pytz.timezone("Europe/Istanbul")),
            id="daily_activity_report",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logging.info("Günlük rapor zamanlayıcısı başlatıldı (her gece 00:00 TR).")

        # Backend kapalıyken kaçırılan günleri arka planda tamamla
        threading.Thread(target=catch_up_missed_reports, daemon=True).start()
        logging.info("Catch-up thread başlatıldı.")
    except ImportError:
        logging.warning("apscheduler yüklü değil — günlük rapor zamanlayıcısı devre dışı.")

    # KVKK: Cleanup orphaned temp files from previous sessions
    try:
        temp_dir = tempfile.gettempdir()
        patterns = [
            "tmp*.pdf", "tmp*.docx", "tmp*.doc", "tmp*.txt", "tmp*.udf",
            "tmp*.xlsx", "tmp*.xls", "tmp*.tif", "tmp*.tiff", "tmp*.jpg", "tmp*.jpeg", "tmp*.png",
            # format_converter/pdf_converter ara çıktıları
            "imgpdf_*.pdf", "officepdf_*.pdf", "pdfa2b_*.pdf",
        ]
        cleaned_count = 0
        for pattern in patterns:
            for old_file in glob.glob(os.path.join(temp_dir, pattern)):
                try:
                    if time.time() - os.path.getmtime(old_file) > 3600:
                        os.remove(old_file)
                        cleaned_count += 1
                except Exception:
                    pass
        # LibreOffice çağrısı yarıda kesilirse kalan geçici dizinler
        for dir_pattern in ("lo_out_*", "lo_profile_*"):
            for old_dir in glob.glob(os.path.join(temp_dir, dir_pattern)):
                try:
                    if os.path.isdir(old_dir) and time.time() - os.path.getmtime(old_dir) > 3600:
                        shutil.rmtree(old_dir, ignore_errors=True)
                        cleaned_count += 1
                except Exception:
                    pass
        if cleaned_count > 0:
            logging.info(f"Startup cleanup: Removed {cleaned_count} orphaned temp files")
    except Exception as e:
        logging.warning(f"Startup cleanup failed: {e}")

    yield

    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)

    logging.info("API Shutting down...")


# --- APP SETUP ---
app = FastAPI(lifespan=lifespan)

# CORS beyaz listesi (G2): ALLOWED_ORIGINS env'den okunur; tanımsızsa güvenli
# default (prod domain + lokal geliştirme portları). Prod'da API aynı origin'den
# nginx ile proxy'lendiği için tarayıcı akışı bu listeye bağımlı değildir.
# DEV_MODE=true iken (yalnızca lokal geliştirme) tüm origin'lere izin verilir;
# prod'da DEV_MODE false/tanımsız olmak zorundadır (bkz. G5/G10 guard'ları).
_DEFAULT_ORIGINS = (
    "https://hukukoid.com,https://www.hukukoid.com,"
    "http://localhost:8080,http://localhost:8000,http://localhost:5173"
)
if os.getenv("DEV_MODE", "").strip().lower() == "true":
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )
else:
    allowed_origins = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )

def _rate_limit_key(request):
    """Nginx proxy arkasında gerçek istemci IP'si X-Forwarded-For'dadır; doğrudan
    bağlantı IP'si kullanılırsa tüm kullanıcılar tek limit kovasını paylaşır.
    Backend portu yalnızca localhost + iç Docker ağına açık olduğundan header
    spoof'u dış istemciler için mümkün değildir."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Referans listelerine mükerrer kayıt girişimi tüm add endpoint'lerinden
# yükselebilir; tek noktadan 409'a çevrilir (route'larda try/except tekrarı yerine).
from managers.reference_lists import DuplicateItemError, ItemInUseError  # noqa: E402


@app.exception_handler(DuplicateItemError)
async def duplicate_item_handler(request, exc: DuplicateItemError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ItemInUseError)
async def item_in_use_handler(request, exc: ItemInUseError):
    # Kullanımdaki liste öğesi silinemez; arayüz "kaç kayıt etkileniyor" bilgisini
    # usage alanından okuyup boşalt/taşı seçeneklerini sunar.
    return JSONResponse(status_code=409, content={"detail": str(exc), "usage": exc.usage})
# default_limits yalnızca middleware kayıtlıysa uygulanır — bu satır olmadan
# hiçbir uçta hız sınırı yoktur.
app.add_middleware(SlowAPIMiddleware)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 50 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: StarletteRequest, call_next):
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > self.max_size:
                TechnicalLogger.log(
                    "WARNING",
                    "Request too large blocked",
                    {"size_mb": content_length / 1024 / 1024},
                )
                return Response(
                    content="Request body too large. Maximum: 50MB",
                    status_code=413,
                )
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware, max_size=50 * 1024 * 1024)

# --- ROUTES ---
from routes import admin, config, clients, cases, debug, documents, processing, activity, export, parties, case_intake

app.include_router(config.router)
# Soft-delete geri alma (yalnız admin) — silinenleri gören tek yol
app.include_router(admin.router)
# Bellek teşhisi (yalnız admin) — 2026-07-29 OOM incelemesi
app.include_router(debug.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(parties.router)
app.include_router(documents.router)
app.include_router(processing.router)
# Otonom dava açma — intake analiz endpoint'i (Faz 2)
app.include_router(case_intake.router)
app.include_router(activity.router)
# Hukukbot export API'si: Azure AD auth'un DIŞINDA, X-API-Key ile korunur.
# Host nginx'e bağlanmaz — yalnızca iç Docker network'ünden erişilir (BULGULAR #5).
app.include_router(export.router)



@app.get("/")
def health_check():
    return {"status": "running", "message": "HukuDok API Active (Web Mode)"}


# Derin sağlık ucu (Faz 2-A): docker-compose healthcheck + deploy sağlık
# kapısı (Faz 1-C) + GCP uptime check (container nginx location = /healthz)
# hep buraya bakar. DB SELECT 1 + süreç içi sinyaller (health.py); DB fail →
# 503 "unhealthy", Gemini/Graph sorunları → 200 "degraded" (yalnız görünürlük).
# limiter.exempt: sağlık yoklaması hiçbir koşulda 429'a takılmamalı
# (unhealthy → frontend depends_on + deploy kapısı yanlış alarm verir).
import health  # noqa: E402

# TTL cache: yoklamalar (compose 30 sn + uptime check bölgeleri + deploy
# kapısının 3 sn'lik poll'u) üst üste binince DB'ye inmesin (plan: "cache'li").
_HEALTHZ_CACHE_TTL_SECONDS = 10.0
_healthz_lock = threading.Lock()
_healthz_cache: dict = {"at": 0.0, "payload": None, "code": 200}


def _healthz_db_ok() -> bool:
    # Sync endpoint threadpool'da koşar — bloklayan SELECT 1 event loop'a
    # dokunmaz. pool_pre_ping'li ortak engine kullanılır (ayrı bağlantı yok).
    try:
        from sqlalchemy import text as _sa_text

        from database import engine

        with engine.connect() as conn:
            conn.execute(_sa_text("SELECT 1"))
        return True
    except Exception as e:
        logging.getLogger("healthz").warning(f"/healthz DB kontrolü başarısız: {e}")
        return False


@app.get("/healthz")
@limiter.exempt
def healthz(response: Response):
    now = time.monotonic()
    with _healthz_lock:
        fresh = now - _healthz_cache["at"] < _HEALTHZ_CACHE_TTL_SECONDS
        if _healthz_cache["payload"] is not None and fresh:
            response.status_code = _healthz_cache["code"]
            return _healthz_cache["payload"]
    # Hesap kilit DIŞINDA: DB kontrolü uzarsa eşzamanlı yoklamalar kilitte
    # kuyruklanmasın (en kötü ihtimal birkaç mükerrer SELECT 1).
    # version: imaja build'de gömülen git SHA (APP_VERSION); lokalde "dev".
    # deploy.sh sağlık kapısı bunu beklenen SHA ile karşılaştırır.
    payload, code = health.evaluate(
        db_ok=_healthz_db_ok(), version=os.getenv("APP_VERSION", "dev")
    )
    with _healthz_lock:
        _healthz_cache.update(at=time.monotonic(), payload=payload, code=code)
    response.status_code = code
    return payload


def get_port():
    parser = argparse.ArgumentParser(description="HukuDok Backend API")
    parser.add_argument("--port", type=int, default=8001, help="Port to run the API on")
    args, _ = parser.parse_known_args()
    return args.port


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8001))
    try:
        msg = f"Starting API on port {PORT}"
        logging.info(msg)
        write_startup_log(msg)
        uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
    except Exception as e:
        err_msg = f"CRITICAL STARTUP ERROR: {e}"
        logging.critical(err_msg)
        write_startup_log(err_msg)
        write_startup_log(traceback.format_exc())
        traceback.print_exc()
        sys.exit(1)
