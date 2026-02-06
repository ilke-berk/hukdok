import os
import sys
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

# --- STARTUP DEBUG LOGGING (CRITICAL FOR DEBUGGING EXE) ---
def write_startup_log(msg):
    try:
        log_dir = Path.home() / "AppData" / "Local" / "HukuDok" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "startup_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass # Fallback if we can't write to disk

write_startup_log("--- BACKEND STARTUP INITIATED ---")
write_startup_log(f"CWD: {os.getcwd()}")
write_startup_log(f"Executable: {sys.executable}")
write_startup_log(f"Arguments: {sys.argv}")

# Force UTF-8 (Fix for Windows Console)
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

print("DEBUG: API Loading started...", flush=True)
write_startup_log("DEBUG: API Loading started...")

import uvicorn
import shutil
import time
import uuid
import logging
import argparse
print("DEBUG: Base imports done.", flush=True)

import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, File, UploadFile, Form, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import tempfile
import tempfile
print("DEBUG: FastAPI imports done.", flush=True)

# --- Pydantic Models for Config Updates ---
from database import SessionLocal
import models
class ConfigItem(BaseModel):
    code: str
    name: str

class EmailItem(BaseModel):
    name: str
    email: str
    description: Optional[str] = ""

class DeleteRequest(BaseModel):
    code: Optional[str] = None
    email: Optional[str] = None

class ReorderRequest(BaseModel):
    type: str # lawyers, statuses, doctypes, emails
    ordered_ids: List[str] # List of codes or emails

# Contact Type Enum for validation
from enum import Enum

class ContactType(str, Enum):
    CLIENT = "Client"
    OTHER = "Other"

class ClientCreate(BaseModel):
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    contact_type: ContactType = ContactType.CLIENT  # Enum validation

class ClientRead(BaseModel):
    id: int
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    contact_type: str = "Client"  # Return as string for frontend compatibility
    active: bool

    class Config:
        orm_mode = True

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    contact_type: Optional[ContactType] = None  # Enum validation
    active: Optional[bool] = None 
    class Config:
        from_attributes = True




# --- Imports and Settings ---
try:
    write_startup_log("Attempting to import modules...")
    from sharepoint_uploader_graph import upload_file_to_sharepoint
    print("DEBUG: sharepoint_uploader_graph imported.", flush=True)
    from analyzer import analyze_file_generator
    print("DEBUG: analyzer imported.", flush=True)
    from list_manager import get_lawyer_list_from_sharepoint, get_status_list_from_sharepoint, get_doctype_list_from_sharepoint
    print("DEBUG: list_manager imported.", flush=True)
    from sharepoint_muvekkil_manager import get_client_list_from_sharepoint
    print("DEBUG: sharepoint_muvekkil_manager imported.", flush=True)
    from log_manager import LogManager, TechnicalLogger
    print("DEBUG: log_manager imported.", flush=True)
    from config_manager import DynamicConfig
    print("DEBUG: config_manager imported.", flush=True)
    from counter_manager import get_counter_manager
    write_startup_log("All local modules imported successfully.")
    
    # --- SECURITY: Safe File Removal Utility (KVKK Compliance) ---
    def safe_remove(file_path: str, retries: int = 3, delay: float = 1.0) -> bool:
        """
        KVKK-compliant file removal with retry mechanism.
        
        Handles Windows file locking issues by retrying removal.
        
        Args:
            file_path: Path to file to remove
            retries: Number of retry attempts (default: 3)
            delay: Delay between retries in seconds (default: 1.0)
            
        Returns:
            True if file was removed successfully, False otherwise
        """
        if not file_path or not os.path.exists(file_path):
            return True  # File doesn't exist, consider it "removed"
        
        for attempt in range(retries):
            try:
                os.remove(file_path)
                logging.info(f"🗑️ File removed successfully: {file_path}")
                return True
            except PermissionError as e:
                if attempt < retries - 1:
                    logging.warning(f"⚠️ File locked, retry {attempt + 1}/{retries}: {file_path}")
                    import time
                    time.sleep(delay)
                else:
                    logging.error(f"❌ Failed to remove file after {retries} attempts: {file_path} - {e}")
                    return False
            except Exception as e:
                logging.error(f"❌ Unexpected error removing file: {file_path} - {e}")
                return False
        
        return False

except Exception as ie:
    error_msg = f"CRITICAL IMPORT ERROR: {ie}"
    print(error_msg, flush=True)
    write_startup_log(error_msg)
    write_startup_log(traceback.format_exc())
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Optional: Cache Manager
try:
    import threading
    import cache_manager
except ImportError:
    logging.warning("Cache/Threading module missing.")
    cache_manager = None


# Env Load
load_dotenv()
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# Initialize Log Manager
try:
    log_manager = LogManager()
    LOG_MANAGER_AVAILABLE = True
except Exception:
    LOG_MANAGER_AVAILABLE = False
    class MockLogManager:
        def init_log(self, original_filename): return "MOCK_999", None
        def complete_log(self, *args): pass
        def fail_log(self, *args): pass
    log_manager = MockLogManager()

# Rate Limiting Setup
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize FastAPI
app = FastAPI()

# --- CORS ---
# SUPER PERMISSIVE FOR DEV: Allow EVERYTHING
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hukukoid.com",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:5173",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- REQUEST SIZE LIMIT MIDDLEWARE (DoS Protection) ---
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits maximum request body size to prevent DoS attacks.
    Already have file size validation (100MB), this is backup at HTTP level.
    """
    def __init__(self, app, max_size: int = 100 * 1024 * 1024):  # 100MB
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: StarletteRequest, call_next):
        # Check Content-Length header
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > self.max_size:
                TechnicalLogger.log(
                    "WARNING", 
                    "Request too large blocked",
                    {"size_mb": content_length / 1024 / 1024, "max_mb": self.max_size / 1024 / 1024}
                )
                return Response(
                    content="Request body too large. Maximum: 100MB",
                    status_code=413  # Payload Too Large
                )
        
        response = await call_next(request)
        return response

# Add middleware
app.add_middleware(RequestSizeLimitMiddleware, max_size=100 * 1024 * 1024)


# --- SECURITY EVENT LOGGER ---
class SecurityEventLogger:
    """Dedicated logger for security events with file persistence."""
    
    def __init__(self):
        # Security log location
        log_dir = Path.home() / "AppData" / "Local" / "HukuDok" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_file = log_dir / "security.log"
        
        # Configure file logger
        self.logger = logging.getLogger("SecurityEvents")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        handler = logging.FileHandler(self.log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(handler)
    
    def log_event(self, event_type: str, severity: str, detail: str, metadata: dict = None):
        """
        Log a security event.
        
        Args:
            event_type: Type of security event (e.g., 'PATH_TRAVERSAL_BLOCKED')
            severity: INFO, WARNING, ERROR
            detail: Human-readable description
            metadata: Additional context (dict)
        """
        event_data = {
            "type": event_type,
            "severity": severity,
            "detail": detail,
            "metadata": metadata or {}
        }
        
        log_message = json.dumps(event_data, ensure_ascii=False)
        
        if severity == "ERROR":
            self.logger.error(log_message)
        elif severity == "WARNING":
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

# Initialize security logger
security_logger = SecurityEventLogger()

# --- AUTHENTICATION ---
from auth_verifier import AuthVerifier
security_scheme = HTTPBearer()

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=True))):
    """Validates the Bearer token. Strict Mode (No Mock User)."""
    
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    claims = AuthVerifier.verify_token(token)
    
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    return claims

# --- BACKGROUND UPDATE TASK ---
# --- BACKGROUND UPDATE TASK ---
def refresh_lists_background():
    """Background Task: Syncs SharePoint -> DB, then Updates Singleton Config from DB."""
    logging.info("🔄 Background: Starting list update...")
    try:
        # 0. SYNC SharePoint -> Database
        try:
            from sync_lists import run_full_sync
            logging.info("🔄 Triggering Database Sync...")
            run_full_sync()
            logging.info("✅ Database Sync Complete.")
        except Exception as sync_e:
            logging.error(f"❌ Database Sync Failed: {sync_e}")
            # Continue anyway, maybe we can read old data from DB or fallback to SP
            
        # 1. Fetch Data (Now fetches from DB because of list_manager updates)
        new_lawyers = get_lawyer_list_from_sharepoint()
        new_statuses = get_status_list_from_sharepoint()
        new_doctypes = get_doctype_list_from_sharepoint()
        new_clients = get_client_list_from_sharepoint()

        # 1b. Fetch local email recipients (Now from DB)
        try:
            from list_manager import get_email_recipients_from_db
            new_recipients = get_email_recipients_from_db()
            logging.info(f"✅ Background: {len(new_recipients)} email recipients loaded from DB.")
        except Exception as e:
            logging.error(f"⚠️ Failed to load email recipients: {e}")

        # 2. Update Singleton
        config = DynamicConfig.get_instance()
        updated = False

        if new_lawyers:
            config.set_lawyers(new_lawyers)
            logging.info(f"✅ Background: {len(new_lawyers)} lawyers updated.")
            updated = True
        
        if new_statuses:
            config.set_statuses(new_statuses)
            logging.info(f"✅ Background: {len(new_statuses)} statuses updated.")
            updated = True
            
        if new_doctypes:
            config.set_doctypes(new_doctypes)
            logging.info(f"✅ Background: {len(new_doctypes)} doctypes updated.")
            updated = True
        
        if new_clients:
            config.set_clients(new_clients)
            logging.info(f"✅ Background: {len(new_clients)} clients updated.")
            updated = True
        
        if new_recipients:
            config.set_email_recipients(new_recipients)
            updated = True
            
            # MÜVEKKİL LİSTESİNİ JSON'A YAZ (Matcher için)
            try:
                from pathlib import Path
                import json
                from datetime import datetime
                import os
                
                # Absolute path kullan (Electron farklı dizinden çalışabiliyor)
                # Write to AppData (Writable)
                app_data_dir = Path.home() / "AppData" / "Local" / "HukuDok" / "data"
                app_data_dir.mkdir(parents=True, exist_ok=True)
                muvekkil_json_path = app_data_dir / "muvekkil_listesi.json"
                
                muvekkil_data = {
                    "metadata": {
                        "kaynak": "SharePoint - Muvekkil Listesi",
                        "son_guncelleme": datetime.now().isoformat(),
                        "toplam_muvekkil": len(new_clients),
                        "durum": "AKTIF"
                    },
                    "muvekiller": new_clients  # Now preserves full dict structure with IDs
                }
                
                with open(muvekkil_json_path, 'w', encoding='utf-8') as f:
                    json.dump(muvekkil_data, f, ensure_ascii=False, indent=2)
                
                logging.info(f"✅ muvekkil_listesi.json güncellendi ({len(new_clients)} müvekkil)")
                logging.info(f"   Dosya: {muvekkil_json_path}")
                
                # 1. normalized_client_list.json'u yeniden oluştur
                from client_normalizer import process_client_list
                process_client_list()
                logging.info("✅ normalized_client_list.json yenilendi")
                
                # 2. Matcher'ı yenile
                from muvekkil_matcher_v2 import yenile_matcher
                yenile_matcher()
                logging.info("✅ Müvekkil matcher yenilendi")
                
                # 3. ListSearcher singleton'ını yenile
                from list_searcher import get_list_searcher
                searcher = get_list_searcher()
                searcher._load_data()  # Reload from updated JSON
                logging.info("✅ ListSearcher yenilendi")
                
            except Exception as json_error:
                logging.error(f"⚠️ muvekkil_listesi.json yazma hatası: {json_error}")
                import traceback
                logging.error(traceback.format_exc())

        # 3. Persist to JSON Cache
        if updated and cache_manager:
            full_data = {
                "lawyers": config.get_lawyers(),
                "statuses": config.get_statuses(),
                "doctypes": config.get_doctypes(),
                "clients": config.get_clients(),
                "email_recipients": config.get_email_recipients(),
                "last_updated": datetime.now().isoformat()
            }
            cache_manager.save_cache(full_data)
    except Exception as e:
        logging.error(f"⚠️ Background Update Failed: {e}")

@app.on_event("startup")
def startup_event():
    """Startup: Load from cache for fast startup. Use refresh button for updates."""
    logging.info("🚀 API Starting...")
    write_startup_log("🚀 API Startup Event triggered")
    config = DynamicConfig.get_instance()

    # Load Local Cache (hızlı açılış)
    if cache_manager:
        cached_data = cache_manager.load_cache()
        if cached_data:
            lawyers = cached_data.get("lawyers", [])
            statuses = cached_data.get("statuses", [])
            doctypes = cached_data.get("doctypes", [])
            clients = cached_data.get("clients", [])
            
            config.set_lawyers(lawyers)
            config.set_statuses(statuses)
            config.set_doctypes(doctypes)
            config.set_clients(clients)
            email_recipients = cached_data.get("email_recipients", [])
            if email_recipients:
                config.set_email_recipients(email_recipients)
            
            logging.info(f"📦 Cache Loaded: {len(lawyers)} lawyers, {len(statuses)} statuses, {len(clients)} clients, {len(email_recipients)} email recipients.")
        else:
            logging.warning("📦 Cache empty. Use refresh button to load data.")

    # Start Background Refresh (Non-blocking)
    import threading
    threading.Thread(target=refresh_lists_background, daemon=True).start()
    logging.info("🔄 Startup: Background refresh thread started.")
    
    # SECURITY: Cleanup orphaned temp files from previous sessions (KVKK)
    try:
        import glob
        temp_dir = tempfile.gettempdir()
        # Look for common temp file patterns from our app
        patterns = ["tmp*.pdf", "tmp*.docx", "tmp*.doc", "tmp*.txt", "tmp*.udf"]
        cleaned_count = 0
        
        for pattern in patterns:
            for old_file in glob.glob(os.path.join(temp_dir, pattern)):
                try:
                    # Only remove files older than 1 hour (safety check)
                    file_age = time.time() - os.path.getmtime(old_file)
                    if file_age > 3600:  # 1 hour in seconds
                        os.remove(old_file)
                        cleaned_count += 1
                except Exception as e:
                    pass  # Ignore errors for individual files
        
        if cleaned_count > 0:
            logging.info(f"🧹 Startup cleanup: Removed {cleaned_count} orphaned temp files")
    except Exception as e:
        logging.warning(f"⚠️ Startup cleanup failed: {e}")

# --- CONFIG ---
# (CORS moved to top for priority)

# SSL Cert Fix
ssl_cert = os.getenv("SSL_CERT_FILE")
if ssl_cert and os.path.exists(ssl_cert):
    os.environ["REQUESTS_CA_BUNDLE"] = ssl_cert

# --- ARGS ---
def get_port():
    parser = argparse.ArgumentParser(description="HukuDok Backend API")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the API on")
    args, _ = parser.parse_known_args()
    return args.port


PORT = get_port()

# --- HELPER: Filename Sanitization ---
def sanitize_filename(filename: str) -> str:
    """
    Dosya adını güvenli hale getirir - Filename Injection Prevention.
    
    Engellenen saldırılar:
    - Path traversal (../, \\, etc.)
    - Null byte injection
    - Special characters
    - Invalid extensions
    """
    from pathlib import Path
    import re
    
    # 1. Path traversal karakterlerini engelle - basename sadece dosya adını alır
    filename = os.path.basename(filename)
    
    # 2. Null byte injection engelleme
    filename = filename.replace('\x00', '')
    
    # 3. Sadece güvenli karakterlere izin ver
    # Türkçe karakterler + alfanumerik + tire, alt çizgi, nokta, parantez, boşluk
    safe_pattern = re.compile(r'[^a-zA-ZğüşıöçĞÜŞİÖÇ0-9._\-() ]')
    filename = safe_pattern.sub('_', filename)
    
    # 4. Uzantı kontrolü - sadece PDF, DOCX ve UDF
    allowed_extensions = {'.pdf', '.docx', '.doc', '.udf'}
    ext = Path(filename).suffix.lower()
    
    if not ext:
        raise HTTPException(status_code=400, detail="Geçersiz dosya formatı.")
    
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"İzin verilmeyen dosya uzantısı: {ext}. Sadece PDF ve DOCX yüklenebilir."
        )
    
    # 5. Uzunluk kontrolü (Windows max path: 260, dosya adı ~200 güvenli)
    if len(filename) > 200:
        name = Path(filename).stem[:150]  # Extension hariç, 150 karakter
        filename = name + ext
        TechnicalLogger.log("WARNING", f"Filename truncated to 200 chars: {filename}")
    
    # 6. Boşlukları alt çizgiye çevir (opsiyonel, SharePoint uyumluluğu için)
    filename = filename.replace(' ', '_')
    
    # 7. Ardışık nokta/alt çizgi temizle
    filename = re.sub(r'[_.]{2,}', '_', filename)
    
    TechnicalLogger.log("INFO", f"Filename sanitized: {filename}")
    return filename

# --- HELPER: File Type Validation ---
def validate_file_type(file_path: str) -> bool:
    """
    Dosya tipini magic bytes (file signature) ile doğrular.
    Extension spoofing saldırılarını engeller.
    
    Örnek saldırı: malicious.exe → malicious.pdf.exe → renamed to malicious.pdf
    Magic bytes kontrolü ile gerçek dosya tipini tespit ederiz.
    """
    from pathlib import Path
    
    # 1. Extension check (temel kontrol)
    allowed_extensions = {'.pdf', '.docx', '.doc', '.udf'}
    ext = Path(file_path).suffix.lower()
    
    if ext not in allowed_extensions:
        security_logger.log_event(
            "INVALID_FILE_EXTENSION",
            "WARNING",
            f"Rejected file with invalid extension: {ext}",
            {"file": file_path, "extension": ext}
        )
        TechnicalLogger.log("WARNING", f"Rejected file with invalid extension: {ext}")
        raise HTTPException(
            status_code=400, 
            detail=f"İzin verilmeyen dosya tipi: {ext}. Sadece PDF ve DOCX dosyaları yüklenebilir."
        )
    
    # 2. Magic bytes check (advanced - prevents spoofing)
    # PDF: %PDF (25 50 44 46)
    # DOCX/DOC: PK (50 4B) - ZIP format (Office Open XML)
    # DOC (old): D0 CF 11 E0 A1 B1 1A E1 (OLE2)
    
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)  # İlk 8 byte yeterli
        
        # PDF magic bytes
        if header.startswith(b'%PDF'):
            if ext == '.pdf':
                TechnicalLogger.log("INFO", f"Valid PDF file: {file_path}")
                return True
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Dosya formatı uyumsuz. Lütfen dosya uzantısını kontrol edin."
                )
        
        # UDF files - check extension FIRST before magic bytes
        # (UDF can be XML or ZIP, so check before generic PK handler)
        elif ext == '.udf':
            if header.startswith(b'<?xml') or header.startswith(b'<udf') or header.startswith(b'PK'):
                TechnicalLogger.log("INFO", f"Valid UDF file: {file_path}")
                return True
            else:
                TechnicalLogger.log("ERROR", f"Invalid UDF format, magic bytes: {header.hex()}")
                raise HTTPException(
                    status_code=400,
                    detail="UDF dosyası bozuk veya geçersiz format."
                )
        
        # DOCX/XLSX magic bytes (ZIP - PK)
        elif header.startswith(b'PK'):
            if ext in ['.docx', '.doc']:
                TechnicalLogger.log("INFO", f"Valid DOCX file: {file_path}")
                return True
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Dosya formatı tanınmıyor."
                )
        
        # DOC (old format) magic bytes
        elif header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
            if ext == '.doc':
                TechnicalLogger.log("INFO", f"Valid DOC (legacy) file: {file_path}")
                return True
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Dosya formatı tanınmıyor."
                )
        
        # UDF format (can be XML or ZIP)
        elif header.startswith(b'<?xml') or header.startswith(b'<udf') or header.startswith(b'PK'):
            if ext == '.udf':
                TechnicalLogger.log("INFO", f"Valid UDF file: {file_path}")
                return True
            elif ext in ['.docx', '.doc'] and header.startswith(b'PK'):
                # It's a DOCX, not UDF
                TechnicalLogger.log("INFO", f"Valid DOCX file: {file_path}")
                return True
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Dosya formatı tanınmıyor."
                )
        
        # Unknown file type
        else:
            hex_header = header.hex()
            security_logger.log_event(
                "UNKNOWN_FILE_SIGNATURE",
                "ERROR",
                "Unknown or potentially malicious file type",
                {"file": file_path, "signature": hex_header[:16]}
            )
            TechnicalLogger.log("ERROR", f"Unknown file signature: {hex_header} for {file_path}")
            raise HTTPException(
                status_code=400,
                detail="Dosya formatı tanınmıyor veya desteklenmiyor. Sadece PDF ve DOCX dosyaları kabul edilir."
            )
    
    except IOError as e:
        TechnicalLogger.log("ERROR", f"File read error during validation: {e}")
        raise HTTPException(status_code=500, detail="Dosya doğrulama sırasında hata oluştu.")

# --- HELPER: File Size Validation ---
def validate_file_size(file_path: str) -> bool:
    """
    Dosya boyutunu kontrol eder - DoS saldırılarını engeller.
    
    Max limit: 100 MB (hukuki belgeler için yeterli)
    """
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB in bytes
    
    try:
        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)
        
        if size > MAX_FILE_SIZE:
            security_logger.log_event(
                "OVERSIZED_FILE_REJECTED",
                "WARNING",
                f"File too large: {size_mb:.2f}MB",
                {"file": file_path, "size_mb": size_mb, "limit_mb": MAX_FILE_SIZE / 1024 / 1024}
            )
            TechnicalLogger.log(
                "WARNING", 
                f"File too large: {size_mb:.2f}MB (max: {MAX_FILE_SIZE / 1024 / 1024}MB)",
                {"file": file_path}
            )
            raise HTTPException(
                status_code=413,  # 413 Payload Too Large
                detail=f"Dosya çok büyük: {size_mb:.2f}MB. Maksimum dosya boyutu: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        TechnicalLogger.log("INFO", f"File size OK: {size_mb:.2f}MB", {"file": file_path})
        return True
    
    except OSError as e:
        TechnicalLogger.log("ERROR", f"Error checking file size: {e}")
        raise HTTPException(status_code=500, detail="Dosya boyutu kontrol edilemedi.")
def _normalize_date_for_sharepoint(date_str: str) -> Optional[str]:
    """
    Converts various date formats (YYMMDD, DD.MM.YYYY, YYYY-MM-DD) to SharePoint-friendly ISO 8601 (YYYY-MM-DD).
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try common formats
    formats = [
        "%y%m%d",       # 200310 -> 2020-03-10
        "%d.%m.%Y",     # 14.01.2026
        "%Y-%m-%d",     # 2026-01-14
        "%Y%m%d",       # 20260114
        "%d/%m/%Y",     # 14/01/2026
        "%d-%m-%Y"      # 14-01-2026
    ]
    
    from datetime import datetime
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Validation: Year should be reasonable (e.g., > 1900)
            if dt.year < 1900: 
                continue 
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # If explicitly passed distinct components (rare here but possible in future)
    return None

def _get_doctype_label(code: str) -> str:
    """
    Resolves document type code (e.g. 'ARB-TUTNK-SON_') to its label (e.g. 'Ara Karar').
    Returns original code if lookup fails.
    """
    if not code:
        return None
        
    try:
        from config_manager import DynamicConfig
        doctypes = DynamicConfig.get_instance().get_doctypes()
        for doc in doctypes:
            # Assuming structure {'kod': 'TOTAL', 'aciklama': 'Toplu Liste', ...} 
            # or {'code': '...', 'label': '...'} - checking standard patterns
            c = doc.get('kod') or doc.get('code') or doc.get('value')
            if c == code:
                return doc.get('aciklama') or doc.get('label') or doc.get('name') or code
    except Exception as e:
        TechnicalLogger.log("WARNING", f"Doctype lookup failed for {code}: {e}")
        
    return code



# --- ENDPOINTS ---


@app.get("/")
def health_check():
    return {"status": "running", "message": "HukuDok API Active (Web Mode)"}

# --- CONFIG ENDPOINTS (Dropdown Lists) ---
@app.get("/config/lawyers")
@app.get("/api/config/lawyers")
def get_lawyers_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of lawyers for dropdown."""
    config = DynamicConfig.get_instance()
    return config.get_lawyers()
@app.get("/config/statuses")
@app.get("/api/config/statuses")
def get_statuses_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of statuses for dropdown."""
    config = DynamicConfig.get_instance()
    return config.get_statuses()
@app.get("/config/doctypes")
@app.get("/api/config/doctypes")
def get_doctypes_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of document types for dropdown."""
    config = DynamicConfig.get_instance()
    return config.get_doctypes()

@app.get("/config/email_recipients")
@app.get("/api/config/email_recipients")
def get_email_recipients_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of email recipients (names and emails)."""
    config = DynamicConfig.get_instance()
    data = config.get_email_recipients()
    # ensure_ascii=False is CRITICAL for Turkish characters
    return JSONResponse(content=data, headers={"Content-Type": "application/json; charset=utf-8"})

    # ensure_ascii=False is CRITICAL for Turkish characters
    return JSONResponse(content=data, headers={"Content-Type": "application/json; charset=utf-8"})

# --- ADD / DELETE ENDPOINTS ---
from list_manager import (
    add_lawyer, delete_lawyer, 
    add_status, delete_status, 
    add_doctype, delete_doctype, 
    add_email_recipient, delete_email_recipient,
    reorder_list, add_client
)
from database import check_and_migrate_tables


# Ensure DB Migration
check_and_migrate_tables()

# 1. LAWYERS
@app.post("/api/config/lawyers")
def api_add_lawyer(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_lawyer(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add lawyer")
    return {"status": "success", "message": "Lawyer added"}

@app.delete("/api/config/lawyers/{code}")
def api_delete_lawyer(code: str, user: dict = Depends(get_current_user)):
    success = delete_lawyer(code)
    if not success:
        raise HTTPException(status_code=404, detail="Lawyer not found or failed to delete")
    return {"status": "success", "message": "Lawyer deleted"}

# 2. STATUSES
@app.post("/api/config/statuses")
def api_add_status(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_status(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add status")
    return {"status": "success", "message": "Status added"}

@app.delete("/api/config/statuses/{code}")
def api_delete_status(code: str, user: dict = Depends(get_current_user)):
    success = delete_status(code)
    if not success:
        raise HTTPException(status_code=404, detail="Status not found or failed to delete")
    return {"status": "success", "message": "Status deleted"}

# 3. DOCTYPES
@app.post("/api/config/doctypes")
def api_add_doctype(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_doctype(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add doctype")
    return {"status": "success", "message": "Doctype added"}

@app.delete("/api/config/doctypes/{code}")
def api_delete_doctype(code: str, user: dict = Depends(get_current_user)):
    success = delete_doctype(code)
    if not success:
        raise HTTPException(status_code=404, detail="Doctype not found or failed to delete")
    return {"status": "success", "message": "Doctype deleted"}

# 4. EMAILS
@app.post("/api/config/email_recipients")
def api_add_email(item: EmailItem, user: dict = Depends(get_current_user)):
    success = add_email_recipient(item.name, item.email, item.description)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add email (maybe duplicate?)")
    return {"status": "success", "message": "Email recipient added"}

@app.delete("/api/config/email_recipients")
def api_delete_email(request: DeleteRequest, user: dict = Depends(get_current_user)):
    """Pass email in body because emails contain special chars"""
    if not request.email:
        raise HTTPException(status_code=400, detail="Email required")
    success = delete_email_recipient(request.email)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"status": "success", "message": "Email deleted"}

@app.post("/api/config/reorder")
def api_reorder_list(request: ReorderRequest, user: dict = Depends(get_current_user)):
    success = reorder_list(request.type, request.ordered_ids)
    if not success:
        raise HTTPException(status_code=500, detail="Reorder failed")
    return {"status": "success", "message": "List reordered"}

@app.post("/api/clients")
def api_add_client(client: ClientCreate, user: dict = Depends(get_current_user)):
    success = add_client(client.dict())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save client")
    return {"status": "success", "message": "Client saved"}

@app.get("/api/clients", response_model=List[ClientRead])
def get_clients_api(user: dict = Depends(get_current_user)):
    """Returns full list of clients from DB."""
    db = SessionLocal()
    try:
        clients = db.query(models.Client).filter(models.Client.active == True).order_by(models.Client.name.asc()).all()
        return clients
    finally:
        db.close()

@app.put("/api/clients/{client_id}")
def api_update_client(client_id: int, client_data: ClientUpdate, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        client = db.query(models.Client).filter(models.Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Update fields
        update_data = client_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(client, key, value)
        
        db.commit()
        db.refresh(client)
        return {"status": "success", "message": "Client updated", "client": client}
    except Exception as e:
        print(f"Error updating client: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/refresh")
@app.post("/api/refresh")
@app.post("/api/config/refresh")
async def refresh_config_endpoint(background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Manually triggers a refresh of all lists from SharePoint."""
    background_tasks.add_task(refresh_lists_background)
    return {"status": "refresh_started", "message": "Listeler arka planda güncelleniyor..."}

@app.post("/process")
@limiter.limit("10/minute")
async def analyze_file_endpoint(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Step 1: Analyze File (Stream) - Web Mode (UploadFile)"""
    
    # ⏱️ API BENCHMARK: Toplam istek süresi
    api_start = time.perf_counter()
    api_timings = {}
    
    # 1. Save Uploaded File to Temp
    try:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            temp_path = tmp_file.name
        
        TechnicalLogger.log("INFO", f"Temp file created for analysis: {temp_path} ({len(content)} bytes)")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dosya yükleme hatası: {str(e)}")

    async def event_stream():
        try:
            # 🚀 PARALLEL EXECUTION: Analyzer ve Counter'ı aynı anda başlat
            
            async def fetch_counter():
                """SharePoint counter'ı async olarak çek"""
                try:
                    loop = asyncio.get_running_loop()
                    counter = get_counter_manager()
                    ofis_dosya_no = await asyncio.wait_for(
                        loop.run_in_executor(None, counter.get_next_counter),
                        timeout=10.0
                    )
                    TechnicalLogger.log("INFO", f"Counter okundu: {ofis_dosya_no} (onay bekleniyor)")
                    return ofis_dosya_no
                except asyncio.TimeoutError:
                    TechnicalLogger.log("ERROR", "SharePoint counter timeout (10s)")
                    return "TIMEOUT___"
                except Exception as e:
                    TechnicalLogger.log("ERROR", f"SharePoint counter hatası: {e}")
                    return "XXXXXXXXX"
            
            # Counter'ı paralel başlat (arka planda çalışacak)
            t2 = time.perf_counter()
            counter_task = asyncio.create_task(fetch_counter())
            
            # Analyzer'ı çalıştır (ana iş)
            t1 = time.perf_counter()
            generator = analyze_file_generator(temp_path)
            final_data = None
            
            async for step in generator:
                if step["status"] == "complete":
                    api_timings["analyzer"] = round((time.perf_counter() - t1) * 1000, 2)
                    final_data = step.get("data", {})
                    
                    # Counter task'ın bitmesini bekle
                    if final_data and "ofis_dosya_no" not in final_data:
                        ofis_dosya_no = await counter_task
                        final_data["ofis_dosya_no"] = ofis_dosya_no
                    else: 
                        # Eğer analyzer hata verdiyse counter task'ı iptal etmeye gerek yok ama await etmeliyiz
                         try:
                             _ = await counter_task # Consume task
                         except: pass

                    api_timings["counter_fetch"] = round((time.perf_counter() - t2) * 1000, 2)
                    api_timings["total"] = round((time.perf_counter() - api_start) * 1000, 2)
                    
                    # Benchmark çıktısını logla
                    print(f"\n{'='*60}")
                    print(f"⏱️ API ENDPOINT BENCHMARK (ms):")
                    for key, value in api_timings.items():
                        print(f"   {key}: {value} ms")
                    print(f"{'='*60}\n")
                    
                    # Frontend'e de gönder
                    final_data["_api_benchmark"] = api_timings
                    step["data"] = final_data
                
                yield json.dumps(step) + "\n"
                
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log("ERROR", f"Streaming Error [ID: {error_id}]: {e}")
            yield json.dumps({"status": "error", "message": f"Beklenmedik hata: {str(e)}"}) + "\n"
        finally:
            # Cleanup Temp File (KVKK-compliant with retry)
            if safe_remove(temp_path, retries=3):
                TechnicalLogger.log("INFO", f"Deleted temp analysis file: {temp_path}")
            else:
                TechnicalLogger.log("WARNING", f"Failed to delete temp file: {temp_path}")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@app.post("/confirm")
@limiter.limit("20/minute")
async def confirm_process(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    new_filename: str = Form(...),
    muvekkil_adi: str = Form(None),
    karsi_taraf: str = Form(None),
    avukat_kodu: str = Form(None),
    belge_turu_kodu: str = Form(None),
    tarih: str = Form(None),
    esas_no: str = Form(None),
    muvekkiller_json: str = Form(None),
    belgede_gecen_isimler_json: str = Form(None),
    custom_to_json: str = Form(None),
    custom_cc_json: str = Form(None),
    send_email: bool = Form(True),
    teblig_tarihi: str = Form(None)
):
    """Step 2: Confirm Process (Web Mode) - Rename, Upload to SharePoint"""
    import time as perf_time
    confirm_start = perf_time.perf_counter()
    timings = {}
    
    # Parse JSON fields from Form
    try:
        muvekkiller = json.loads(muvekkiller_json) if muvekkiller_json else []
        belgede_gecen_isimler = json.loads(belgede_gecen_isimler_json) if belgede_gecen_isimler_json else []
        custom_to = json.loads(custom_to_json) if custom_to_json else []
        custom_cc = json.loads(custom_cc_json) if custom_cc_json else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in form fields")

    results = {}
    
    # 1. Save Uploaded File to Temp (for SharePoint Upload)
    suffix = Path(file.filename).suffix
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            temp_path = tmp_file.name
        TechnicalLogger.log("INFO", f"Temp file created for upload: {temp_path}")
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Failed to save temp file: {e}")

    source_path = temp_path
    log_id = None
    muvekkil_kodu = None

    # Security: Sanitize filename to prevent injection attacks
    try:
        new_filename = sanitize_filename(new_filename)
    except HTTPException as e:
        TechnicalLogger.log("WARNING", f"Filename sanitization failed: {e.detail}")
        raise e
    
    # Counter Increment: Arka plana at (ASENKRON)
    def _async_increment():
        try:
            from counter_manager import get_counter_manager
            counter = get_counter_manager()
            counter.increment_counter()
            logging.info("✅ [Async] Counter arka planda başarıyla artırıldı.")
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Async Counter Error: {e}")

    background_tasks.add_task(_async_increment)
    timings["1_counter"] = 0.00  # Asenkron olduğu için süre 0
    logging.info("⏱️ [1] Counter işlemi arka plana atıldı (Süre: 0.00s)")


    HAM_FOLDER = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
    ISLENMIS_FOLDER = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

    # 2. Ham Dosya Yüklemesi (ASENKRON)
    # CRITICAL: Use original filename (from upload), NOT temp filename
    # This preserves forensic evidence and file provenance (KVKK/Legal requirement)
    original_filename = file.filename  # ✅ Frontend'den gelen orijinal dosya adı
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    # CRITICAL: Sanitize filename to prevent Path Traversal
    sanitized_original = sanitize_filename(original_filename)
    ham_filename = f"{date_str}_{sanitized_original}"

    def _async_ham_upload():
        try:
            upload_file_to_sharepoint(
                source_path, 
                ham_filename,
                HAM_FOLDER,
                use_date_subfolder=False
            )
            logging.info(f"✅ [Async] HAM Arşiv yüklendi: {ham_filename}")
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log("ERROR", f"Async Ham Upload Error [ID: {error_id}]: {e}")
            if log_id: log_manager.fail_log(log_id, f"Ham arşiv hatası: {e}")

    background_tasks.add_task(_async_ham_upload)
    timings["2_ham_upload"] = 0.00
    results["sharepoint_ham"] = f"Arka Plana Atıldı ({ham_filename})"
    logging.info("⏱️ [2] HAM Upload arka plana atıldı")

    # 3. İşlenmiş Dosya Yüklemesi (PDF/A-2b Dönüşümü)
    pdfa_temp_file = None
    try:
        from pdf_converter import convert_to_pdfa2b
        
        # 3a. PDF/A-2b Dönüşümü (SENKRON - Yerel kayıt için gerekli)
        step_start = perf_time.perf_counter()
        pdfa_temp_file = convert_to_pdfa2b(source_path)
        timings["3a_pdfa_convert"] = perf_time.perf_counter() - step_start
        logging.info(f"⏱️ [3a] PDF/A-2b dönüşümü: {timings['3a_pdfa_convert']:.2f}s")
        
        if pdfa_temp_file and os.path.exists(pdfa_temp_file):
            file_size_kb = os.path.getsize(pdfa_temp_file) / 1024
            
            # 3b. SharePoint'e yükleme (ASENKRON)
            def _async_gizli_upload_and_cleanup(temp_file_path):
                try:
                    upload_file_to_sharepoint(
                        temp_file_path,
                        new_filename,
                        ISLENMIS_FOLDER,
                        use_date_subfolder=False,
                        metadata={
                            "Muvekkil": (
                                ", ".join(muvekkiller) 
                                if muvekkiller and len(muvekkiller) > 0 
                                else (muvekkil_adi or muvekkil_kodu)
                            ),
                            "Karsi_Taraf": karsi_taraf,
                            "Avukat": avukat_kodu,
                            "BelgeTuru": _get_doctype_label(belge_turu_kodu),
                            "EsasNo": esas_no,
                            "Tarih": _normalize_date_for_sharepoint(tarih)
                        }
                    )
                    logging.info(f"✅ [Async] Gizli Arşiv yüklendi: {new_filename} ({file_size_kb:.1f}KB)")
                except Exception as e:
                    error_id = str(uuid.uuid4())[:8]
                    TechnicalLogger.log("ERROR", f"Async Processed Upload Error [ID: {error_id}]: {e}")
                    if log_id: log_manager.fail_log(log_id, f"İşlenmiş dosya yükleme hatası: {e}")

            background_tasks.add_task(_async_gizli_upload_and_cleanup, pdfa_temp_file)
            timings["3b_gizli_upload"] = 0.00
            results["sharepoint_islenmis"] = "Arka Plana Atıldı (PDF/A-2b)"
            logging.info("⏱️ [3b] Gizli Upload arka plana atıldı")

        else:
            raise Exception("PDF/A-2b dönüşümü başarısız - dosya oluşturulamadı")
            
    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Processed Upload Error [ID: {error_id}]: {e}")
        if log_id: log_manager.fail_log(log_id, f"İşlenmiş dosya yükleme hatası: {e}")
        raise HTTPException(status_code=500, detail=f"SharePoint arşiv yüklemesi başarısız. (Hata: {error_id})")

    # 4. Yerel Kayıt - Web modunda atlanır
    final_local_path = pdfa_temp_file if (pdfa_temp_file and os.path.exists(pdfa_temp_file)) else source_path
    timings["4_local_save"] = 0.00
    results["local_save"] = "Atlandı (Web Mode)"
    results["final_path"] = None
    logging.info("⏱️ [4] Yerel kayıt: Atlandı (Web Mode)")

    # 5. Loglama (Update Log)
    step_start = perf_time.perf_counter()
    try:
        if log_id:
            import hashlib
            sha256_hash = ""
            try:
                hash_target = final_local_path if final_local_path else source_path
                with open(hash_target,"rb") as f:
                    bytes = f.read()
                    sha256_hash = hashlib.sha256(bytes).hexdigest()
            except Exception as h_err:
                sha256_hash = f"Hash_Error: {h_err}"

            log_manager.complete_log(log_id, new_filename, sha256_hash)
            results["log_update"] = "Güncellendi"
        timings["5_logging"] = perf_time.perf_counter() - step_start
    except Exception as e:
        timings["5_logging"] = perf_time.perf_counter() - step_start
        TechnicalLogger.log("ERROR", f"Log Update Failed: {e}")

    def _async_send_email(pdf_path, filename, avukat_kodu, email_metadata, to_list, cc_list):
        try:
            from email_sender import send_document_notification
            result = send_document_notification(
                avukat_kodu=avukat_kodu,
                filename=filename,
                pdf_path=pdf_path,
                metadata=email_metadata,
                custom_to=to_list,
                custom_cc=cc_list
            )
            if result["success"]:
                logging.info(f"✅ [Async] E-posta gönderildi: {filename}")
            else:
                logging.warning(f"⚠️ [Async] E-posta gönderilemedi: {result['message']}")
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Async Email Error: {e}")
    
    # E-posta için metadata hazırla
    # Avukat kodundan isim lookup
    avukat_adi = ""
    if avukat_kodu:
        try:
            lawyers = DynamicConfig.get_instance().get_lawyers()
            for lawyer in lawyers:
                if lawyer.get("code") == avukat_kodu:
                    avukat_adi = lawyer.get("name", "")
                    break
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Avukat isim lookup hatası: {e}")
    
    # E-posta için Müvekkil İsmi belirleme
    clean_client_name = None
    if muvekkiller and len(muvekkiller) > 0:
        clean_client_name = muvekkiller[0]
    
    if not clean_client_name:
        clean_client_name = muvekkil_adi
        
    email_metadata = {
        "muvekkil_adi": clean_client_name or muvekkil_kodu or "Bilinmeyen Müvekkil",
        "muvekkiller": muvekkiller or [],
        "belge_turu": _get_doctype_label(belge_turu_kodu) or "Belge",
        "tarih": tarih or "",
        "avukat_adi": avukat_adi,
        "teblig_tarihi": _normalize_date_for_sharepoint(teblig_tarihi) if teblig_tarihi else None,
    }
    
    # E-posta gönderimi (Her dosya için ayrı email)
    email_file_path = final_local_path  # PDF/A-2b dönüştürülmüş temp dosya
    
    if send_email and email_file_path and os.path.exists(email_file_path):
        background_tasks.add_task(
            _async_send_email, 
            email_file_path,
            new_filename,
            avukat_kodu,
            email_metadata,
            custom_to,
            custom_cc
        )
        timings["7_email"] = 0.00
        results["email"] = "Arka Plana Atıldı"
        logging.info(f"⏱️ [7] E-posta gönderimi arka plana atıldı (To: {len(custom_to)}, CC: {len(custom_cc)})")
    elif not send_email:
        results["email"] = "Kullanıcı tarafından atlandı"
        logging.info("ℹ️ [7] E-posta gönderimi atlandı (send_email=False)")
    else:
        results["email"] = "Dosya bulunamadı"
        logging.warning(f"⚠️ [7] E-posta gönderilemedi - dosya yok: {email_file_path}")
    
    # 8. Temizlik Görevi (En son çalışır) - KVKK-compliant
    def _async_cleanup(temp_path):
        import time
        # E-posta gönderimi için biraz bekle (garanti olsun)
        time.sleep(10)
        if safe_remove(temp_path, retries=5):  # Extra retries for email attachment
            logging.info(f"🗑️ [Cleanup] Geçici dosya silindi: {temp_path}")
        else:
            logging.warning(f"⚠️ [Cleanup] Dosya silinemedi: {temp_path}")

    # Sadece PDF/A-2b temp dosyası oluşturulduysa sil (source_path source ise silme)
    if pdfa_temp_file and pdfa_temp_file != source_path:
        background_tasks.add_task(_async_cleanup, pdfa_temp_file)

    # TOPLAM SÜRE ÖZET LOGU
    total_time = perf_time.perf_counter() - confirm_start
    timings["TOTAL"] = total_time
    
    logging.info(f"""
╔══════════════════════════════════════════════════════════════╗
║  ⏱️ CONFIRM İŞLEM SÜRELERİ (ASYNC)                           ║
╠══════════════════════════════════════════════════════════════╣
║  [1] Counter artırma:     {timings.get('1_counter', 0):>6.2f}s (ASYNC)                     ║
║  [2] HAM Arşiv yükleme:   {timings.get('2_ham_upload', 0):>6.2f}s (ASYNC)                     ║
║  [3a] PDF/A-2b dönüşüm:   {timings.get('3a_pdfa_convert', 0):>6.2f}s (SYNC)                      ║
║  [3b] Gizli Arşiv yükle:  {timings.get('3b_gizli_upload', 0):>6.2f}s (ASYNC)                     ║
║  [4] Yerel kayıt:         {timings.get('4_local_save', 0):>6.2f}s                          ║
║  [5] Loglama:             {timings.get('5_logging', 0):>6.2f}s                          ║
║  [7] E-posta gönderimi:   {timings.get('7_email', 0):>6.2f}s (ASYNC)                     ║
╠══════════════════════════════════════════════════════════════╣
║  TOPLAM:                  {total_time:>6.2f}s                          ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    return {"status": "completed", "results": results, "timings": timings}

# --- BATCH EMAIL ENDPOINT (DEVRE DIŞI) ---
# Her dosya artık /confirm sırasında kendi emailini alıyor.
# Bu endpoint gelecekte tekrar aktifleştirilebilir.
# 
# @app.post("/api/batch-email")
# @limiter.limit("5/minute")
# async def send_batch_email_endpoint(...):
#     ...
# --- END BATCH EMAIL ---

if __name__ == "__main__":
    try:
        msg = f"Starting API on port {PORT}"
        logging.info(msg)
        write_startup_log(msg)
        write_startup_log("Running uvicorn...")
        uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
    except Exception as e:
        err_msg = f"CRITICAL STARTUP ERROR: {e}"
        logging.critical(err_msg)
        write_startup_log(err_msg)
        write_startup_log(traceback.format_exc())
        import traceback
        traceback.print_exc()
        sys.exit(1)