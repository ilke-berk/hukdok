import os
import sys
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

# --- STARTUP DEBUG LOGGING (CRITICAL FOR DEBUGGING EXE) ---
def write_startup_log(msg):
    try:
        from config_manager import get_log_dir
        log_dir = get_log_dir()
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


write_startup_log("DEBUG: API Loading started...")

import uvicorn
import shutil
import time
import uuid
import logging
import argparse


import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, File, UploadFile, Form, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict
from dotenv import load_dotenv
from pathlib import Path
import tempfile


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
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: ContactType = ContactType.CLIENT
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None

class ClientRead(BaseModel):
    id: int
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: str = "Client"
    active: bool
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: Optional[ContactType] = None
    active: Optional[bool] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class CasePartyCreate(BaseModel):
    client_id: Optional[int] = None
    name: str
    role: str
    party_type: str # "CLIENT", "COUNTER", "THIRD"
    birth_year: Optional[int] = None
    gender: Optional[str] = None

class CaseCreate(BaseModel):
    tracking_no: str
    esas_no: Optional[str] = None
    merci_no: Optional[str] = None
    status: str = "DERDEST"
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: Optional[float] = 0
    manevi_tazminat: Optional[float] = 0
    parties: List[CasePartyCreate] = []

class CaseRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    merci_no: Optional[str] = None
    status: str
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: float = 0
    manevi_tazminat: float = 0
    created_at: datetime
    parties: List[CasePartyCreate] = []
    history: List[Dict[str, Any]] = []
    documents: List[Dict[str, Any]] = []
    
    model_config = ConfigDict(from_attributes=True)




# --- Imports and Settings ---
try:
    write_startup_log("Attempting to import modules...")
    from sharepoint_uploader_graph import upload_file_to_sharepoint

    from analyzer import analyze_file_generator
    from admin_manager import get_lawyers, get_statuses, get_doctypes, get_email_recipients, get_case_subjects
    from log_manager import LogManager, TechnicalLogger

    from config_manager import DynamicConfig

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

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: Load from cache for fast startup. Use refresh button for updates."""
    logging.info("🚀 API Starting...")
    write_startup_log("🚀 API Startup Event triggered")
    
    # Initialize Database (Create Tables & Migrate)
    try:
        from database import init_db
        init_db()
    except Exception as e:
        logging.critical(f"🔥 Database Init Failed: {e}")
        write_startup_log(f"🔥 Database Init Failed: {e}")

    config = DynamicConfig.get_instance()

    # Load Local Cache
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
        patterns = ["tmp*.pdf", "tmp*.docx", "tmp*.doc", "tmp*.txt", "tmp*.udf"]
        cleaned_count = 0
        
        for pattern in patterns:
            for old_file in glob.glob(os.path.join(temp_dir, pattern)):
                try:
                    file_age = time.time() - os.path.getmtime(old_file)
                    if file_age > 3600:  
                        os.remove(old_file)
                        cleaned_count += 1
                except Exception as e:
                    pass
        
        if cleaned_count > 0:
            logging.info(f"🧹 Startup cleanup: Removed {cleaned_count} orphaned temp files")
    except Exception as e:
        logging.warning(f"⚠️ Startup cleanup failed: {e}")
        
    yield
    
    logging.info("🛑 API Shutting down...")


# Initialize FastAPI
app = FastAPI(lifespan=lifespan)

# --- CORS ---
# SUPER PERMISSIVE FOR DEV: Allow EVERYTHING (REGEX)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*", # Allow all origins via regex
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
        # Custom import to avoid circular dependency issues at top level if any
        from config_manager import get_log_dir
        
        # Security log location
        log_dir = get_log_dir()
        
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
    """Background Task: Updates Singleton Config from Database (Admin-only mode)."""
    logging.info("🔄 Background: Loading lists from Database...")
    try:
        # Load Directly from DB (Admin-managed)
        new_lawyers = get_lawyers()
        new_statuses = get_statuses()
        new_doctypes = get_doctypes()
        new_recipients = get_email_recipients()
        new_subjects = get_case_subjects()

        # Update Singleton
        config = DynamicConfig.get_instance()
        updated = False

        if new_subjects:
            config.set_case_subjects(new_subjects)
            logging.info(f"✅ Background: {len(new_subjects)} subjects loaded from DB.")
            updated = True

        if new_lawyers:
            config.set_lawyers(new_lawyers)
            logging.info(f"✅ Background: {len(new_lawyers)} lawyers loaded from DB.")
            updated = True
        
        if new_statuses:
            config.set_statuses(new_statuses)
            logging.info(f"✅ Background: {len(new_statuses)} statuses loaded from DB.")
            updated = True
            
        if new_doctypes:
            config.set_doctypes(new_doctypes)
            logging.info(f"✅ Background: {len(new_doctypes)} doctypes loaded from DB.")
            updated = True
        
        if new_recipients:
            config.set_email_recipients(new_recipients)
            logging.info(f"✅ Background: {len(new_recipients)} recipients loaded from DB.")
            updated = True
            
        # 3. Persist to JSON Cache
        if updated and cache_manager:
            full_data = {
                "lawyers": config.get_lawyers(),
                "statuses": config.get_statuses(),
                "doctypes": config.get_doctypes(),
                "case_subjects": config.get_case_subjects(),
                "email_recipients": config.get_email_recipients(),
                "last_updated": datetime.now().isoformat()
            }
            cache_manager.save_cache(full_data)
        
        # 4. Refresh Matcher and Searcher (from DB)
        from muvekkil_matcher_v2 import yenile_matcher
        yenile_matcher()
        from list_searcher import get_list_searcher
        get_list_searcher()._load_data()
        logging.info("✅ Matcher and Searcher refreshed from DB.")

    except Exception as e:
        logging.error(f"⚠️ Background Update Failed: {e}")

# Startup logic migrated to lifespan contextmanager above
# --- CONFIG ---
# (CORS moved to top for priority)

# SSL Cert Fix
ssl_cert = os.getenv("SSL_CERT_FILE")
if ssl_cert and os.path.exists(ssl_cert):
    os.environ["REQUESTS_CA_BUNDLE"] = ssl_cert

# --- ARGS ---
def get_port():
    parser = argparse.ArgumentParser(description="HukuDok Backend API")
    parser.add_argument("--port", type=int, default=8001, help="Port to run the API on")
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
    
    # 2. Null byte injection engelleme (text_utils içinde de var ama burada kalsın)
    filename = filename.replace('\x00', '')
    
    # 3. Güvenli karakter temizliği (Merkezi fonksiyon kullanımı)
    from text_utils import sanitize_filename_text
    filename = sanitize_filename_text(filename)
    
    # safe_pattern = re.compile(r'[^a-zA-ZğüşıöçĞÜŞİÖÇ0-9._\-() ]') -> text_utils içinde daha kapsamlısı var
    # filename = safe_pattern.sub('_', filename)
    
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
    lawyers = config.get_lawyers()
    if not lawyers:
        from admin_manager import get_lawyers
        lawyers = get_lawyers()
    return lawyers

@app.get("/config/statuses")
@app.get("/api/config/statuses")
def get_statuses_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of statuses for dropdown."""
    config = DynamicConfig.get_instance()
    statuses = config.get_statuses()
    if not statuses:
        from admin_manager import get_statuses
        statuses = get_statuses()
    return statuses

@app.get("/config/doctypes")
@app.get("/api/config/doctypes")
def get_doctypes_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of document types for dropdown."""
    config = DynamicConfig.get_instance()
    doctypes = config.get_doctypes()
    if not doctypes:
        from admin_manager import get_doctypes
        doctypes = get_doctypes()
    return doctypes

@app.get("/config/case_subjects")
@app.get("/api/config/case_subjects")
def get_case_subjects_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of case subjects."""
    config = DynamicConfig.get_instance()
    subjects = config.get_case_subjects()
    if not subjects:
        from admin_manager import get_case_subjects
        subjects = get_case_subjects()
    return subjects

@app.post("/api/config/case_subjects")
def api_add_case_subject(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_case_subject(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add case subject")
    return {"status": "success", "message": "Case subject added"}

@app.delete("/api/config/case_subjects/{code}")
def api_delete_case_subject(code: str, user: dict = Depends(get_current_user)):
    success = delete_case_subject(code)
    if not success:
        raise HTTPException(status_code=404, detail="Case subject not found or failed to delete")
    return {"status": "success", "message": "Case subject deleted"}

@app.get("/config/email_recipients")
@app.get("/api/config/email_recipients")
def get_email_recipients_endpoint(user: dict = Depends(get_current_user)):
    """Returns list of email recipients (names and emails)."""
    config = DynamicConfig.get_instance()
    data = config.get_email_recipients()
    return JSONResponse(content=data, headers={"Content-Type": "application/json; charset=utf-8"})


# --- ADD / DELETE ENDPOINTS ---
from admin_manager import (
    add_lawyer, delete_lawyer,
    add_status, delete_status,
    add_doctype, delete_doctype,
    add_email_recipient, delete_email_recipient,
    add_case_subject, delete_case_subject,
    reorder_list, add_client, add_case, get_case, get_cases, update_case, search_cases
)
from database import check_and_migrate_tables

# --- FAZ 1: Belge türü → Dava durumu eşleştirme tablosu ---
# Admin paneli ile genişletilebilir, şimdilik kodda sabit.
# Format: belge_turu_kodu_prefix → yeni_dava_durumu
DOCTYPE_TO_STATUS_MAP = {
    "KARAR":    "KARAR",      # Karar belgesi → Dava durumu KARAR
    "TEMYIZ":   "TEMYIZ",    # Temyiz dilekçesi → Dava TEMYIZ'e geçer
    "INFAZ":    "INFAZ",     # İnfaz belgesi → Dava INFAZ'a geçer
    "FERAGAT":  "KAPALI",    # Feragat → Dava kapanır
    "ISLAH":    "DERDEST",   # Islah dilekçesi → Dava aktif devam eder
}

def _auto_update_case_status(case_id: int, belge_turu_kodu: str, uploaded_by: str = None):
    """
    Faz 1: Belge türüne göre dava durumunu otomatik günceller.
    Örn: KARAR-BLG yüklenince dava → KARAR durumuna geçer.
    """
    if not case_id or not belge_turu_kodu:
        return False
    try:
        db = SessionLocal()
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            db.close()
            return False

        new_status = None
        kod_upper = belge_turu_kodu.upper()
        for prefix, status in DTYPE_TO_STATUS_MAP_ITEMS:
            if kod_upper.startswith(prefix):
                new_status = status
                break

        if new_status and new_status != case.status:
            old_status = case.status
            case.status = new_status
            # Geçmişe kaydet
            history = models.CaseHistory(
                case_id=case_id,
                field_name="status",
                old_value=old_status,
                new_value=new_status
            )
            db.add(history)
            db.commit()
            logging.info(f"✅ [Faz1] Dava {case_id} durumu otomatik güncellendi: {old_status} → {new_status} (Belge: {belge_turu_kodu})")
            db.close()
            return True

        db.close()
        return False
    except Exception as e:
        logging.error(f"❌ [Faz1] Otomatik durum güncelleme hatası: {e}")
        return False

def _auto_enrich_case_data(case_id: int, avukat_kodu: str = None, karsi_taraf: str = None, uploaded_by: str = None):
    """
    Faz 1.5: Eksik dava bilgilerini belgeden okunan verilerle otomatik tamamlar.
    """
    if not case_id:
        return {}
    
    updated_fields = {}
    try:
        db = SessionLocal()
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            return {}

        # 1. Avukat Eksikse Tamamla
        if avukat_kodu and (not case.responsible_lawyer_name or case.responsible_lawyer_name == "Atanmadı" or case.responsible_lawyer_name.strip() == ""):
            try:
                lawyers = DynamicConfig.get_instance().get_lawyers()
                for lawyer in lawyers:
                    if lawyer.get("code") == avukat_kodu:
                        avukat_adi = lawyer.get("name")
                        old_avukat = case.responsible_lawyer_name
                        case.responsible_lawyer_name = avukat_adi
                        history = models.CaseHistory(
                            case_id=case_id,
                            field_name="responsible_lawyer_name",
                            old_value=old_avukat or "Yok",
                            new_value=avukat_adi
                        )
                        db.add(history)
                        updated_fields["lawyer"] = avukat_adi
                        logging.info(f"✨ [Auto-Enrich] Dava {case_id} Sorumlu Avukat atandı: {avukat_adi}")
                        break
            except Exception as e:
                logging.warning(f"Avukat lookup hatası (Enrichment): {e}")

        # 2. Karşı Taraf Eksikse Tamamla
        if karsi_taraf:
            has_counter = any(p.party_type == "COUNTER" for p in case.parties)
            if not has_counter:
                new_party = models.CaseParty(case_id=case_id, name=karsi_taraf, role="Karşı Taraf", party_type="COUNTER")
                db.add(new_party)
                history = models.CaseHistory(
                    case_id=case_id,
                    field_name="karşı_taraf",
                    old_value="Yok",
                    new_value=karsi_taraf
                )
                db.add(history)
                updated_fields["counter_party"] = karsi_taraf
                logging.info(f"✨ [Auto-Enrich] Dava {case_id} Karşı Taraf Eklendi: {karsi_taraf}")

        if updated_fields:
            db.commit()
            
        return updated_fields
    except Exception as e:
        logging.error(f"❌ [Auto-Enrich] Hata: {e}")
        return {}
    finally:
        db.close()

# Dict → List of tuples for prefix matching
DTYPE_TO_STATUS_MAP_ITEMS = list(DOCTYPE_TO_STATUS_MAP.items())

def _save_case_document(
    case_id: int | None,
    original_filename: str,
    stored_filename: str,
    belge_turu_kodu: str = None,
    belge_turu_adi: str = None,
    ai_summary: str = None,
    muvekkil_adi: str = None,
    avukat_kodu: str = None,
    esas_no: str = None,
    is_test_mode: bool = False,
    uploaded_by: str = None
) -> int | None:
    """
    Faz 1: Yüklenen belgeyi case_documents tablosuna kaydeder.
    is_test_mode=True ise case_id olmasa da kaydeder (TEST modu).
    """
    try:
        db = SessionLocal()

        if case_id:
            link_mode = "LINKED"
        elif is_test_mode:
            link_mode = "TEST"
        else:
            link_mode = "UNLINKED"

        doc = models.CaseDocument(
            case_id=case_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            belge_turu_kodu=belge_turu_kodu,
            belge_turu_adi=belge_turu_adi,
            ai_summary=ai_summary,
            muvekkil_adi=muvekkil_adi,
            avukat_kodu=avukat_kodu,
            esas_no=esas_no,
            link_mode=link_mode,
            uploaded_by=uploaded_by
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        db.close()
        logging.info(f"✅ [Faz1] CaseDocument kaydedildi: ID={doc_id}, mode={link_mode}, case_id={case_id}")
        return doc_id
    except Exception as e:
        logging.error(f"❌ [Faz1] CaseDocument kayıt hatası: {e}")
        return None


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
    success = add_client(client.model_dump())
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

@app.post("/api/cases")
def api_add_case(case_data: CaseCreate, user: dict = Depends(get_current_user)):
    result = add_case(case_data.model_dump())
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save case")
    return {"status": "success", "message": "Case saved", **result}

@app.get("/api/incomplete-tasks")
def get_incomplete_tasks(user: dict = Depends(get_current_user)):
    """Yarım kalan dava ve müvekkil kayıtlarını tespit eder."""
    db = SessionLocal()
    try:
        incomplete_cases = []
        incomplete_clients = []

        # 1. Eksik Davalar
        cases = db.query(models.Case).filter(models.Case.active == True).all()
        for c in cases:
            missing = []
            if not c.court:
                missing.append("Mahkeme")
            if not c.responsible_lawyer_name:
                missing.append("Avukat")
            if not c.subject:
                missing.append("Konu")

            # CLIENT party olup client_id bağlı olmayan taraf var mı?
            for p in c.parties:
                if p.party_type == "CLIENT" and not p.client_id:
                    missing.append(f"Müvekkil bağlantısı ({p.name})")

            # Hiç CLIENT party yoksa
            client_parties = [p for p in c.parties if p.party_type == "CLIENT"]
            if len(client_parties) == 0:
                missing.append("Müvekkil yok")

            if missing:
                incomplete_cases.append({
                    "id": c.id,
                    "type": "case",
                    "esas_no": c.esas_no or c.tracking_no,
                    "court": c.court or "",
                    "status": c.status,
                    "missing_fields": missing,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                })

        # 2. Eksik Müvekkiller
        clients = db.query(models.Client).filter(models.Client.active == True).all()
        for cl in clients:
            missing = []
            if not cl.phone:
                missing.append("Telefon")
            if not cl.email:
                missing.append("E-posta")
            if not cl.tc_no:
                missing.append("TC No")
            if not cl.address:
                missing.append("Adres")

            # En az 2 alan eksikse "yarım" say (tek alan eksik normalde tolere edilir)
            if len(missing) >= 2:
                incomplete_clients.append({
                    "id": cl.id,
                    "type": "client",
                    "name": cl.name,
                    "client_type": cl.client_type or "Belirtilmemiş",
                    "missing_fields": missing,
                })

        return {
            "incomplete_cases": incomplete_cases,
            "incomplete_clients": incomplete_clients[:20],  # En fazla 20 müvekkil göster
            "total_incomplete_cases": len(incomplete_cases),
            "total_incomplete_clients": len(incomplete_clients),
        }
    except Exception as e:
        logger.error(f"Incomplete Tasks Error: {e}")
        return {"incomplete_cases": [], "incomplete_clients": [], "total_incomplete_cases": 0, "total_incomplete_clients": 0}
    finally:
        db.close()

@app.get("/api/cases", response_model=List[CaseRead])
def get_cases_api(user: dict = Depends(get_current_user)):
    """Returns list of cases."""
    return get_cases()

@app.get("/api/cases/client-sequence")
def get_client_case_sequence(client_name: str, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        from sqlalchemy import func
        # Find how many distinct cases this client name is attached to as a CLIENT
        count = db.query(func.count(func.distinct(models.CaseParty.case_id)))\
                  .filter(models.CaseParty.party_type == "CLIENT")\
                  .filter(models.CaseParty.name.ilike(client_name))\
                  .scalar()
        
        return {"sequence": (count or 0) + 1}
    except Exception as e:
        logger.error(f"Error getting client sequence: {e}")
        return {"sequence": 1}
    finally:
        db.close()

@app.get("/api/cases/search")
def api_search_cases(q: str, user: dict = Depends(get_current_user)):
    return search_cases(q)

@app.get("/api/cases/{case_id}")
def api_get_case(case_id: int, user: dict = Depends(get_current_user)):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

@app.put("/api/cases/{case_id}")
def api_update_case(case_id: int, case_data: CaseCreate, user: dict = Depends(get_current_user)):
    success = update_case(case_id, case_data.model_dump())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update case")
    return {"status": "success", "message": "Case updated"}

@app.delete("/api/cases/{case_id}")
def api_delete_case(case_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        db.delete(case)
        db.commit()
        return {"status": "success", "message": "Case deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
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
        update_data = client_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(client, key, value)
        
        db.commit()
        db.refresh(client)
        return {"status": "success", "message": "Client updated", "client": client}
    except Exception as e:
        logger.error(f"Error updating client: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/api/clients/{client_id}")
def api_delete_client(client_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        client = db.query(models.Client).filter(models.Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # First: detach any case_party references to avoid FK violation
        db.query(models.CaseParty).filter(models.CaseParty.client_id == client_id).update(
            {"client_id": None}, synchronize_session=False
        )
        
        db.delete(client)
        db.commit()
        return {"status": "success", "message": "Client deleted"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# --- FAZ 1: BELGE ENDPOİNT'LERİ ---

@app.get("/api/cases/{case_id}/documents")
def get_case_documents(case_id: int, user: dict = Depends(get_current_user)):
    """Belirli bir davaya ait tüm yüklenen belgeleri listeler."""
    db = SessionLocal()
    try:
        docs = db.query(models.CaseDocument).filter(
            models.CaseDocument.case_id == case_id
        ).order_by(models.CaseDocument.uploaded_at.desc()).all()
        return [
            {
                "id": d.id,
                "case_id": d.case_id,
                "original_filename": d.original_filename,
                "stored_filename": d.stored_filename,
                "belge_turu_kodu": d.belge_turu_kodu,
                "belge_turu_adi": d.belge_turu_adi,
                "ai_summary": d.ai_summary,
                "muvekkil_adi": d.muvekkil_adi,
                "avukat_kodu": d.avukat_kodu,
                "esas_no": d.esas_no,
                "link_mode": d.link_mode,
                "uploaded_by": d.uploaded_by,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            }
            for d in docs
        ]
    finally:
        db.close()

@app.get("/api/documents")
def get_all_documents(
    limit: int = 50,
    link_mode: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Tüm yüklenen belgeleri listeler. link_mode ile filtrele: LINKED, TEST, UNLINKED"""
    db = SessionLocal()
    try:
        q = db.query(models.CaseDocument)
        if link_mode:
            q = q.filter(models.CaseDocument.link_mode == link_mode.upper())
        docs = q.order_by(models.CaseDocument.uploaded_at.desc()).limit(limit).all()
        return [
            {
                "id": d.id,
                "case_id": d.case_id,
                "original_filename": d.original_filename,
                "stored_filename": d.stored_filename,
                "belge_turu_kodu": d.belge_turu_kodu,
                "belge_turu_adi": d.belge_turu_adi,
                "muvekkil_adi": d.muvekkil_adi,
                "avukat_kodu": d.avukat_kodu,
                "esas_no": d.esas_no,
                "link_mode": d.link_mode,
                "uploaded_by": d.uploaded_by,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            }
            for d in docs
        ]
    finally:
        db.close()

@app.patch("/api/documents/{doc_id}/link")
def link_document_to_case(
    doc_id: int,
    payload: dict,
    user: dict = Depends(get_current_user)
):
    """
    Bağlantısız (UNLINKED/TEST) bir belgeyi sonradan bir davaya bağlar.
    Body: { "case_id": 123 }
    """
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        new_case_id = payload.get("case_id")
        if not new_case_id:
            raise HTTPException(status_code=400, detail="case_id gerekli")
        case = db.query(models.Case).filter(models.Case.id == new_case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")
        doc.case_id = new_case_id
        doc.link_mode = "LINKED"
        db.commit()
        return {"status": "success", "message": f"Belge #{doc_id} dava #{new_case_id}'ye bağlandı"}
    finally:
        db.close()

# --- END FAZ 1 BELGE ENDPOİNT'LERİ ---

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
                        try:
                            _ = await counter_task
                        except: pass

                    api_timings["counter_fetch"] = round((time.perf_counter() - t2) * 1000, 2)

                    # --- FAZ 1: OTOMATİK DAVA EŞLEŞTİRME ---
                    try:
                        t_match = time.perf_counter()
                        from case_matcher import find_matching_case
                        
                        match_result = await asyncio.get_running_loop().run_in_executor(
                            None,
                            find_matching_case,
                            final_data.get("esas_no"),
                            final_data.get("muvekkiller") or ([final_data.get("muvekkil_adi")] if final_data.get("muvekkil_adi") else []),
                            final_data.get("avukat_kodu"),
                        )
                        
                        if match_result:
                            final_data["suggested_case"] = match_result
                            TechnicalLogger.log(
                                "INFO",
                                f"🎯 Dava önerisi: #{match_result['case_id']} "
                                f"({match_result['esas_no']}) "
                                f"Skor={match_result['score']} Güven={match_result['confidence']}"
                            )
                        else:
                            final_data["suggested_case"] = None

                        api_timings["case_match"] = round((time.perf_counter() - t_match) * 1000, 2)
                    except Exception as match_err:
                        TechnicalLogger.log("WARNING", f"CaseMatcher hatası (atlandı): {match_err}")
                        final_data["suggested_case"] = None
                    # --- END FAZ 1 ---

                    api_timings["total"] = round((time.perf_counter() - api_start) * 1000, 2)
                    
                    # Benchmark print removed as requested
                    
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

# --- DOWNLOAD CACHE ---
import uuid
DOWNLOAD_CACHE = {}

@app.get("/api/download/{file_id}")
async def download_file(file_id: str):
    if file_id not in DOWNLOAD_CACHE:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı veya süresi doldu.")
    
    file_info = DOWNLOAD_CACHE[file_id]
    file_path = file_info["path"]
    filename = file_info["filename"]
    
    if not os.path.exists(file_path):
        del DOWNLOAD_CACHE[file_id]
        raise HTTPException(status_code=404, detail="Dosya diskte bulunamadı.")
        
    # FileResponse automatically handles streaming/ranges
    return FileResponse(
        path=file_path, 
        filename=filename, 
        media_type='application/pdf',
        # Background task to clean up after download? 
        # Better to let the scheduled cleanup handle it, or remove from cache immediately.
        # We'll remove from cache to prevent multi-download, but keep file for the main cleanup task.
    )


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
    teblig_tarihi: str = Form(None),
    # --- FAZ 1: Dava Bağlantısı ---
    linked_case_id: Optional[int] = Form(None),   # Seçilen dava ID'si (opsiyonel)
    is_test_mode: bool = Form(False),              # Test modunda dava zorunlu değil
    ai_ozet: str = Form(None),                     # Analiz özeti (belge kaydı için)
    user: dict = Depends(get_current_user)         # Auth (Form endpoint'lerinde Depends sona gelmeli)
):
    """Step 2: Confirm Process (Web Mode) - Rename, Upload to SharePoint, Link to Case"""
    import time as perf_time
    confirm_start = perf_time.perf_counter()
    timings = {}

    # Kullanıcı bilgisi
    current_user_name = user.get("name") or user.get("preferred_username") or "Bilinmeyen"

    # Parse JSON fields from Form
    try:
        muvekkiller = json.loads(muvekkiller_json) if muvekkiller_json else []
        belgede_gecen_isimler = json.loads(belgede_gecen_isimler_json) if belgede_gecen_isimler_json else []
        custom_to = json.loads(custom_to_json) if custom_to_json else []
        custom_cc = json.loads(custom_cc_json) if custom_cc_json else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in form fields")

    results = {}
    
    # 0. Avukat Bilgisini Dava Kaydından Bul (Eğer gönderilmediyse)
    if not avukat_kodu and linked_case_id:
        db_fetch = SessionLocal()
        try:
            case_fetch = db_fetch.query(models.Case).filter(models.Case.id == linked_case_id).first()
            if case_fetch and case_fetch.responsible_lawyer_name:
                lawyers = DynamicConfig.get_instance().get_lawyers()
                for l in lawyers:
                    if l.get("name") == case_fetch.responsible_lawyer_name:
                        avukat_kodu = l.get("code")
                        logging.info(f"🔍 [Auto-Avukat] Dava {linked_case_id} için avukat kodu bulundu: {avukat_kodu}")
                        break
        except Exception as e:
            logging.warning(f"Avukat lookup hatası (Confirm): {e}")
        finally:
            db_fetch.close()
    
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
    
    # 8. Download Preparation (Web Mode)
    # Store the filePath in cache so frontend can fetch it
    download_id = None
    if email_file_path and os.path.exists(email_file_path):
        download_id = str(uuid.uuid4())
        DOWNLOAD_CACHE[download_id] = {
            "path": email_file_path,
            "filename": new_filename,
            "timestamp": perf_time.time()
        }
        results["download_id"] = download_id
        logging.info(f"💾 Download hazırlandı ID: {download_id}")

    # 9. Temizlik Görevi (En son çalışır) - KVKK-compliant
    def _async_cleanup(temp_path, down_id=None):
        import time
        # Frontend'in indirmesi için süre tanı (30 saniye)
        # E-posta gönderimi için de gerekli
        time.sleep(30) 
        
        if safe_remove(temp_path, retries=5):  
            logging.info(f"🗑️ [Cleanup] Geçici dosya silindi: {temp_path}")
        else:
            logging.warning(f"⚠️ [Cleanup] Dosya silinemedi: {temp_path}")
            
        # Cache'den de temizle
        if down_id and down_id in DOWNLOAD_CACHE:
            del DOWNLOAD_CACHE[down_id]

    # Sadece PDF/A-2b temp dosyası oluşturulduysa sil (source_path source ise silme)
    if pdfa_temp_file and pdfa_temp_file != source_path:
        background_tasks.add_task(_async_cleanup, pdfa_temp_file, download_id)

    # --- FAZ 1: CaseDocument Kaydı + Otomatik Dava Durum Güncellemesi ---
    belge_turu_label = _get_doctype_label(belge_turu_kodu) if belge_turu_kodu else None
    clean_muvekkil = (muvekkiller[0] if muvekkiller else None) or muvekkil_adi

    # Belgeyi kaydet
    doc_id = _save_case_document(
        case_id=linked_case_id,
        original_filename=file.filename,
        stored_filename=new_filename,
        belge_turu_kodu=belge_turu_kodu,
        belge_turu_adi=belge_turu_label,
        ai_summary=ai_ozet,
        muvekkil_adi=clean_muvekkil,
        avukat_kodu=avukat_kodu,
        esas_no=esas_no,
        is_test_mode=is_test_mode,
        uploaded_by=current_user_name
    )
    results["case_document_id"] = doc_id
    results["link_mode"] = "TEST" if is_test_mode else ("LINKED" if linked_case_id else "UNLINKED")

    # Otomatik dava durum güncellemesi (sadece gerçek bir davaya bağlıysa)
    if linked_case_id and not is_test_mode:
        if belge_turu_kodu:
            status_updated = _auto_update_case_status(linked_case_id, belge_turu_kodu, current_user_name)
            results["auto_status_update"] = status_updated
        else:
            results["auto_status_update"] = False
            
        # --- FAZ 1.5: EKSİK VERİ TAMAMLAMA ---
        enriched_data = _auto_enrich_case_data(linked_case_id, avukat_kodu, karsi_taraf, current_user_name)
        results["auto_enrichment"] = enriched_data
    else:
        results["auto_status_update"] = False
        results["auto_enrichment"] = {}

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
    PORT = int(os.getenv("PORT", 8001)) # Default to 8001
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