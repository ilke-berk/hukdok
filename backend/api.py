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

# Merkezi loglama (Faz 2-B): dağınık basicConfig'lerin yerini alan tek
# dictConfig — JSON formatter + request-id için bkz. logging_setup.py.
# Diğer import'lardan ÖNCE koşmalı ki import sırasında akan loglar da biçimli
# olsun (bu olmadan kök logger WARNING'de kalır, logging.info sessizce düşer).
from logging_setup import RequestIdMiddleware, configure_logging

configure_logging()

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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

try:
    write_startup_log("Attempting to import modules...")
    from config.settings import settings
    from managers.config_manager import DynamicConfig
    from managers.log_manager import TechnicalLogger
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

    # Faz 3-E: lifespan'deki yedek init_db KALDIRILDI — migrasyonun tek sahibi
    # entrypoint'teki migrate.py (3-A'daki "import models" düzeltmesinden beri
    # tek başına eksiksiz). --workers N'de her worker lifespan koşar → burada
    # DDL, worker'lar arası yarış + statement_timeout'lu app engine'inde uzun
    # backfill demekti. Host-run (python api.py) için: önce `python migrate.py`.

    # Süreç-tekil arkaplan işleri (aşağıda) yalnız lider worker'da başlar;
    # kilit süreç ölünce çekirdekçe bırakılır, yeniden doğan worker devralır.
    from services.singleton_lock import try_acquire_leader
    is_leader = try_acquire_leader()
    if not is_leader:
        logging.info("Worker lider değil — süreç-tekil arkaplan işleri bu worker'da atlanıyor.")

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

    # Refresh thread'i BİLEREK worker-BAŞINA koşar (3-E kararı): DynamicConfig,
    # matcher ve searcher süreç İÇİ singleton'lardır — yalnız liderde koşsaydı
    # diğer worker'lar taze cache dosyası yokken boş listelerle kalırdı.
    # Duplikasyonun tek gerçek zararı cache dosyası yazma yarışıydı →
    # cache_manager.save_cache tekil temp adla atomik yazacak şekilde düzeltildi.
    # Bilinen sınır: /refresh endpoint'i yalnız isteği işleyen worker'ı tazeler;
    # diğeri kendi refresh'ine (boot ya da kendi /refresh'i) kadar bayat kalır —
    # liste değişiklikleri nadir, kabul edilen takas.
    import threading
    threading.Thread(target=refresh_lists_background, daemon=True).start()
    logging.info("Background refresh thread started.")

    # Günlük aktivite raporu zamanlayıcısı (her gece 00:00 Türkiye saatiyle).
    # Faz 3-E: yalnız lider worker'da — N worker'da N kopya rapor/e-posta üretirdi.
    if is_leader:
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
            # Faz 3-F: gece dönüşüm retry job'ı — conversion_pending belgeleri
            # yeniden dener (PDF/A üret → arşive yükle → statüyü düşür →
            # hukukbot'u AÇ). Aynı scheduler'da (yeni thread/scheduler YOK,
            # 3-E devri) → yalnız lider worker'da koşar. 02:30 TR: gece yarısı
            # raporu (00:00) ve host pg_dump'ı (03:30) ile çakışmaz.
            from services.conversion_retry import retry_pending_conversions
            scheduler.add_job(
                retry_pending_conversions,
                CronTrigger(hour=2, minute=30, timezone=pytz.timezone("Europe/Istanbul")),
                id="conversion_retry",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            # G085: yaklaşan süre/duruşma tarayıcısı — AYNI scheduler (yeni
            # thread/scheduler YOK, 3-E devri) → yalnız lider worker'da koşar;
            # iki worker'da koşsaydı aynı avukata çift bildirim yazılırdı
            # (dedupe onu yutar ama yarışı beslemenin anlamı yok). 06:00 TR:
            # gece işleri (00:00 rapor, 02:30 dönüşüm, 03:30 pg_dump) bitmiş
            # olur ve uyarı mesai başlangıcında hazır durur.
            from services.deadline_scanner import scan_deadlines
            scheduler.add_job(
                scan_deadlines,
                CronTrigger(hour=6, minute=0, timezone=pytz.timezone("Europe/Istanbul")),
                id="deadline_scan",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            scheduler.start()
            app.state.scheduler = scheduler
            logging.info(
                "Günlük rapor zamanlayıcısı başlatıldı (her gece 00:00 TR; dönüşüm retry 02:30 TR; "
                "süre/duruşma taraması 06:00 TR)."
            )

            # Backend kapalıyken kaçırılan günleri arka planda tamamla
            threading.Thread(target=catch_up_missed_reports, daemon=True).start()
            logging.info("Catch-up thread başlatıldı.")
        except ImportError:
            logging.warning("apscheduler yüklü değil — günlük rapor zamanlayıcısı devre dışı.")

    # SharePoint yükleme outbox worker'ı (Faz 3-A): ilk taraması startup
    # reconcile'dır — önceki süreçten kalan pending yüklemeleri toparlar.
    # Faz 3-E: yalnız lider worker'da — her worker kendi thread'ini açarsa
    # aynı satır N kez yüklenir. Lider ölürse yeni lider lifespan'de devralır;
    # o pencerede enqueue edilen satırlar birikir, devralan reconcile işler.
    if is_leader:
        try:
            from services.upload_queue import start_upload_worker
            start_upload_worker()
        except Exception as e:
            # Worker yoksa enqueue edilen satırlar birikir, sonraki açılış işler —
            # yine de retry sistemi devre dışı demek: gerçek arıza sinyali, ERROR.
            logging.error(f"Upload outbox worker başlatılamadı: {e}")

    # Faz 3-E (3.7): PROCESS_CACHE/DOWNLOAD_CACHE artık disk destekli — boot'ta
    # TTL süpürmesi önceki süreçten kalan bayat girdileri (ve payload
    # dosyalarını) temizler; taze girdiler restart'ı ATLATIR (özelliğin amacı).
    # Claim-atomik olduğundan iki worker'ın eşzamanlı süpürmesi güvenlidir.
    try:
        from routes.processing import _cleanup_process_cache
        _cleanup_process_cache()
    except Exception as e:
        logging.warning(f"Cache boot süpürmesi başarısız: {e}")

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

    try:
        from services.upload_queue import stop_upload_worker
        stop_upload_worker()
    except Exception as e:
        logging.warning(f"Upload outbox worker durdurulamadı: {e}")

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

# Limiter rate_limiting.py'de yaşar: routes/client_errors.py per-endpoint
# limit dekoratörü için aynı instance'ı import eder (Faz 2-C).
from rate_limiting import limiter  # noqa: E402

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


# Kapalı havuz dışı karar durumu (G066): istemci HATALI DEĞER gönderdi → 400.
# 422 DEĞİL, çünkü 422 bu uygulamada şema doğrulamasının (FastAPI/Pydantic)
# imzasıdır; buradaki ret referans verisine bağlıdır, gövde şeması geçerlidir.
# 500 hiç değil (G003 durum kodu disiplini): kod bozuk değil, değer yanlış.
from managers.stage_decisions import InvalidDecisionStatusError  # noqa: E402


@app.exception_handler(InvalidDecisionStatusError)
async def invalid_decision_status_handler(request, exc: InvalidDecisionStatusError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ─── 503 "sistem meşgul" ağı (Faz 5-B, plan 5.3) ──────────────────────────────
# Doygunluk sinyalleri 500'e mahkûm edilmemeli: 500 "kod bozuk, tekrar deneme
# boşuna" der; kullanıcı ya vazgeçer ya da aynı belgeyi tekrar tekrar yükleyip
# yükü artırır. Gövde biçimi 5-A'nın /confirm 503'üyle AYNI: {"detail": "..."}
# ve metin son kullanıcıya hitap eder (4-A sözleşmesi: detail gösterilebilir).
# 4-A frontend'i 502/503/504'ü zaten işliyor → frontend değişikliği gerekmez.
import subprocess  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from services import document_pipeline  # noqa: E402


@app.exception_handler(subprocess.TimeoutExpired)
async def conversion_timeout_handler(request, exc: subprocess.TimeoutExpired):
    """Ghostscript / LibreOffice zaman aşımı bir istek handler'ına kadar
    ulaştıysa: belge bozuk değil, sistem yetişemiyor demektir.

    Normal /confirm yolunda dönüşüm hataları conversion_pending katmanına
    (Faz 3-F) düşer ve buraya HİÇ gelmez; bu handler o katmanın kapsamadığı
    çağrı yollarının 500 üretmesini engelleyen ağdır. Log: doygunluk
    WARNING'i alt-bileşende zaten atıldı, burada YENİ ERROR üretilmez.
    """
    logging.warning(f"Dönüşüm alt süreci zaman aşımına uğradı ({exc.cmd}) — 503 döndürülüyor")
    return JSONResponse(
        status_code=503, content={"detail": document_pipeline.CONVERSION_BUSY_DETAIL}
    )


# Bağlantı kopması / havuz tükenmesi / statement_timeout — hepsi geçici
# doygunluktur (ProgrammingError gibi kalıcı SQL hataları DAHİL DEĞİL, onlar
# gerçek 500'dür). "TEKRAR GÖNDERMEYİN": çoğu yazma ucu idempotent değil.
DB_BUSY_DETAIL = (
    "Sistem şu anda yoğun, işleminiz tamamlanamadı — TEKRAR GÖNDERMEYİN, "
    "birkaç dakika sonra tekrar deneyin."
)


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request, exc: OperationalError):
    logging.error(f"Veritabanı erişilemedi ({request.url.path}) — 503 döndürülüyor: {exc}")
    return JSONResponse(status_code=503, content={"detail": DB_BUSY_DETAIL})
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
                    content=f"Request body too large. Maximum: {self.max_size // (1024 * 1024)}MB",
                    status_code=413,
                )
        return await call_next(request)


# Limitin evi config/settings.py (env: REQUEST_SIZE_LIMIT_MB, Faz 5-A);
# MAX_UPLOAD_MB'den ayrı düğme (multipart ek yükü bağımsız ayarlanabilsin),
# varsayılan ikisi de 50 → bugünkü davranış aynen.
app.add_middleware(
    RequestSizeLimitMiddleware, max_size=settings.request_size_limit_mb * 1024 * 1024
)

# En dışta (add_middleware LIFO — son eklenen en dış katmandır): 413/429/CORS
# kısa devreleri dahil her yanıt X-Request-ID taşır ve erişim satırı alır.
app.add_middleware(RequestIdMiddleware)

# --- ROUTES ---
from routes import admin, config, clients, cases, debug, documents, processing, activity, export, parties, case_intake, client_errors, notifications

app.include_router(config.router)
# Frontend hata beacon'ı — bilinçli auth'suz (auth kırıkken de rapor gelsin);
# IP limiti + gövde tavanı + alan beyaz listesi korumaları modülün içinde.
app.include_router(client_errors.router)
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
# Uygulama içi bildirim (G081) — `/api` altında, nginx istisnası gerektirmez
app.include_router(notifications.router)
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
        # log_config=None: uvicorn kendi dictConfig'iyle merkezi kurulumu
        # ezmesin (dev yolu; konteynerde CLI import'tan önce kurar, sorun yok).
        uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False, log_config=None)
    except Exception as e:
        err_msg = f"CRITICAL STARTUP ERROR: {e}"
        logging.critical(err_msg)
        write_startup_log(err_msg)
        write_startup_log(traceback.format_exc())
        traceback.print_exc()
        sys.exit(1)
