import os
import sys
import traceback
import logging
import argparse
import tempfile
import glob
import time
from datetime import datetime
from contextlib import asynccontextmanager

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

    try:
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
        from managers.admin_manager import seed_all_lists
        seed_all_lists()
        logging.info("Seed check completed.")
    except Exception as e:
        logging.warning(f"Seed failed: {e}")

    import threading
    threading.Thread(target=refresh_lists_background, daemon=True).start()
    logging.info("Background refresh thread started.")

    # KVKK: Cleanup orphaned temp files from previous sessions
    try:
        temp_dir = tempfile.gettempdir()
        patterns = ["tmp*.pdf", "tmp*.docx", "tmp*.doc", "tmp*.txt", "tmp*.udf"]
        cleaned_count = 0
        for pattern in patterns:
            for old_file in glob.glob(os.path.join(temp_dir, pattern)):
                try:
                    if time.time() - os.path.getmtime(old_file) > 3600:
                        os.remove(old_file)
                        cleaned_count += 1
                except Exception:
                    pass
        if cleaned_count > 0:
            logging.info(f"Startup cleanup: Removed {cleaned_count} orphaned temp files")
    except Exception as e:
        logging.warning(f"Startup cleanup failed: {e}")

    yield

    logging.info("API Shutting down...")


# --- APP SETUP ---
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 100 * 1024 * 1024):
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
                    content="Request body too large. Maximum: 100MB",
                    status_code=413,
                )
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware, max_size=100 * 1024 * 1024)

# --- ROUTES ---
from routes import config, clients, cases, documents, processing

app.include_router(config.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(processing.router)



@app.get("/")
def health_check():
    return {"status": "running", "message": "HukuDok API Active (Web Mode)"}


# Ensure DB migration on load
from database import check_and_migrate_tables
check_and_migrate_tables()


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
