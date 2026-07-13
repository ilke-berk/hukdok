import os
import re
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from dependencies import security_logger
from managers.log_manager import TechnicalLogger

ALLOWED_EXTENSIONS = {
    ".pdf", ".udf",
    ".tif", ".tiff", ".jpg", ".jpeg", ".png",
    ".docx", ".doc", ".xlsx", ".xls",
}

SUPPORTED_FORMATS_LABEL = "PDF, UDF, Word, Excel, TIFF, JPG ve PNG"

# Upload boyut limiti (Faz 4.4'te env'e taşınacak: MAX_UPLOAD_MB)
MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def safe_remove(file_path: Optional[str], retries: int = 3, delay: float = 1.0) -> bool:
    """KVKK-compliant file removal with retry mechanism."""
    if not file_path or not os.path.exists(file_path):
        return True

    for attempt in range(retries):
        try:
            os.remove(file_path)
            logging.info(f"File removed successfully: {file_path}")
            return True
        except PermissionError as e:
            if attempt < retries - 1:
                logging.warning(f"File locked, retry {attempt + 1}/{retries}: {file_path}")
                time.sleep(delay)
            else:
                logging.error(f"Failed to remove file after {retries} attempts: {file_path} - {e}")
                return False
        except Exception as e:
            logging.error(f"Unexpected error removing file: {file_path} - {e}")
            return False

    return False


def sanitize_filename(filename: str) -> str:
    """Dosya adını güvenli hale getirir - Filename Injection Prevention."""
    from text_utils import sanitize_filename_text

    filename = os.path.basename(filename)
    filename = filename.replace("\x00", "")
    filename = sanitize_filename_text(filename)

    ext = Path(filename).suffix.lower()

    if not ext:
        raise HTTPException(status_code=400, detail="Geçersiz dosya formatı.")

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"İzin verilmeyen dosya uzantısı: {ext}. Sadece {SUPPORTED_FORMATS_LABEL} yüklenebilir.",
        )

    if len(filename) > 200:
        name = Path(filename).stem[:150]
        filename = name + ext
        TechnicalLogger.log("WARNING", f"Filename truncated to 200 chars: {filename}")

    filename = filename.replace(" ", "_")
    # Ardışık ayraçlar yalnızca GÖVDEDE tekilleştirilir; uzantı dışarıda
    # tutulur, yoksa "KARARI_.pdf" → "KARARI_pdf" olur (bkz. text_utils
    # sanitize_filename_text içindeki uyarı).
    stem, ext = Path(filename).stem, Path(filename).suffix
    filename = re.sub(r"[_.]{2,}", "_", stem) + ext

    TechnicalLogger.log("INFO", f"Filename sanitized: {filename}")
    return filename


# Magic-byte imzaları: uzantı → kabul edilen header prefix'leri
_MAGIC_SIGNATURES = {
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG",),
    # OLE Compound File (legacy Office)
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}

# ZIP (PK) tabanlı formatlar: uzantı → arşiv içinde bulunması gereken marker
_ZIP_MARKERS = {
    ".udf": "content.xml",
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
}


def _validate_zip_marker(file_path: str, ext: str) -> bool:
    """PK header'lı dosyanın arşiv içeriğiyle uzantısının eşleştiğini doğrular."""
    import zipfile

    marker = _ZIP_MARKERS[ext]
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            if marker in z.namelist():
                TechnicalLogger.log("INFO", f"Valid ZIP-based {ext} file: {file_path}")
                return True
    except zipfile.BadZipFile:
        pass
    TechnicalLogger.log("ERROR", f"PK header but not a valid {ext} archive: {file_path}")
    raise HTTPException(
        status_code=400,
        detail=f"Dosya bozuk veya uzantısıyla ({ext}) uyumsuz bir format içeriyor.",
    )


def validate_file_type(file_path: str) -> bool:
    """Dosya tipini magic bytes ile doğrular. Extension spoofing saldırılarını engeller."""
    ext = Path(file_path).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        security_logger.log_event(
            "INVALID_FILE_EXTENSION",
            "WARNING",
            f"Rejected file with invalid extension: {ext}",
            {"file": file_path, "extension": ext},
        )
        TechnicalLogger.log("WARNING", f"Rejected file with invalid extension: {ext}")
        raise HTTPException(
            status_code=400,
            detail=f"İzin verilmeyen dosya tipi: {ext}. Sadece {SUPPORTED_FORMATS_LABEL} dosyaları yüklenebilir.",
        )

    try:
        with open(file_path, "rb") as f:
            header = f.read(8)

        if header.startswith(b"%PDF"):
            if ext == ".pdf":
                TechnicalLogger.log("INFO", f"Valid PDF file: {file_path}")
                return True
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Dosya formatı uyumsuz. Lütfen dosya uzantısını kontrol edin.",
                )

        elif ext in _MAGIC_SIGNATURES:
            if any(header.startswith(sig) for sig in _MAGIC_SIGNATURES[ext]):
                TechnicalLogger.log("INFO", f"Valid {ext} file: {file_path}")
                return True
            TechnicalLogger.log("ERROR", f"Invalid {ext} magic bytes: {header.hex()} for {file_path}")
            raise HTTPException(
                status_code=400,
                detail="Dosya formatı uyumsuz. Lütfen dosya uzantısını kontrol edin.",
            )

        elif ext in _ZIP_MARKERS and header.startswith(b"PK"):
            return _validate_zip_marker(file_path, ext)

        elif ext == ".udf" and (header.startswith(b"<?xml") or header.startswith(b"<udf")):
            # XML tabanlı UDF — ilk 512 byte içinde <udf etiketi aranır
            with open(file_path, "rb") as f:
                preview = f.read(512)
            if b"<udf" in preview:
                TechnicalLogger.log("INFO", f"Valid XML-based UDF file: {file_path}")
                return True
            TechnicalLogger.log("ERROR", f"XML header but no <udf tag found: {file_path}")
            raise HTTPException(status_code=400, detail="UDF dosyası bozuk veya geçersiz format.")

        else:
            hex_header = header.hex()
            security_logger.log_event(
                "UNKNOWN_FILE_SIGNATURE",
                "ERROR",
                "Unknown or potentially malicious file type",
                {"file": file_path, "signature": hex_header[:16]},
            )
            TechnicalLogger.log("ERROR", f"Unknown file signature: {hex_header} for {file_path}")
            raise HTTPException(
                status_code=400,
                detail=f"Dosya formatı tanınmıyor veya desteklenmiyor. Sadece {SUPPORTED_FORMATS_LABEL} dosyaları kabul edilir.",
            )

    except IOError as e:
        TechnicalLogger.log("ERROR", f"File read error during validation: {e}")
        raise HTTPException(status_code=500, detail="Dosya doğrulama sırasında hata oluştu.") from e


def validate_file_size(file_path: str) -> bool:
    """Dosya boyutunu kontrol eder - DoS saldırılarını engeller. Max: 100 MB"""
    try:
        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)

        if size > MAX_UPLOAD_BYTES:
            security_logger.log_event(
                "OVERSIZED_FILE_REJECTED",
                "WARNING",
                f"File too large: {size_mb:.2f}MB",
                {"file": file_path, "size_mb": size_mb, "limit_mb": MAX_UPLOAD_MB},
            )
            TechnicalLogger.log(
                "WARNING",
                f"File too large: {size_mb:.2f}MB (max: {MAX_UPLOAD_MB}MB)",
                {"file": file_path},
            )
            raise HTTPException(
                status_code=413,
                detail=f"Dosya çok büyük: {size_mb:.2f}MB. Maksimum dosya boyutu: {MAX_UPLOAD_MB}MB",
            )

        TechnicalLogger.log("INFO", f"File size OK: {size_mb:.2f}MB", {"file": file_path})
        return True

    except OSError as e:
        TechnicalLogger.log("ERROR", f"Error checking file size: {e}")
        raise HTTPException(status_code=500, detail="Dosya boyutu kontrol edilemedi.") from e

def normalize_date_for_sharepoint(date_str: str) -> Optional[str]:
    """Converts various date formats to SharePoint-friendly ISO 8601 (YYYY-MM-DD)."""
    if not date_str:
        return None

    date_str = date_str.strip()
    formats = [
        "%y%m%d",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%Y%m%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 1900:
                continue
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _normalize_doctype_code(code: str) -> str:
    """Kod karşılaştırması için normalize eder.

    Config kodları sabit genişliğe alt çizgiyle doldurulur ("ARA-KRR_______")
    ve maile/dosya adına ayraçları farklı biçimlerde ulaşabilir. Büyük harfe
    çevirip harf/rakam dışındaki her şeyi atarak ("ARA-KRR" == "ARA-KRR_______"
    == "ARAKRR") sağlam eşleşme sağlar.
    """
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def get_doctype_label(code: str) -> Optional[str]:
    """Resolves document type code to its label. Returns original code if lookup fails."""
    if not code:
        return None

    target = _normalize_doctype_code(code)

    try:
        from managers.config_manager import DynamicConfig

        doctypes = DynamicConfig.get_instance().get_doctypes()
        for doc in doctypes:
            c = doc.get("kod") or doc.get("code") or doc.get("value")
            if _normalize_doctype_code(c) == target:
                return doc.get("aciklama") or doc.get("label") or doc.get("name") or code
    except Exception as e:
        TechnicalLogger.log("WARNING", f"Doctype lookup failed for {code}: {e}")

    return code
