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

ALLOWED_EXTENSIONS = {".pdf", ".udf"}


def safe_remove(file_path: str, retries: int = 3, delay: float = 1.0) -> bool:
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
            detail=f"İzin verilmeyen dosya uzantısı: {ext}. Sadece PDF ve UDF yüklenebilir.",
        )

    if len(filename) > 200:
        name = Path(filename).stem[:150]
        filename = name + ext
        TechnicalLogger.log("WARNING", f"Filename truncated to 200 chars: {filename}")

    filename = filename.replace(" ", "_")
    filename = re.sub(r"[_.]{2,}", "_", filename)

    TechnicalLogger.log("INFO", f"Filename sanitized: {filename}")
    return filename


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
            detail=f"İzin verilmeyen dosya tipi: {ext}. Sadece PDF ve UDF dosyaları yüklenebilir.",
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

        elif ext == ".udf":
            if header.startswith(b"PK"):
                # ZIP tabanlı UDF — içinde content.xml olmalı
                import zipfile
                try:
                    with zipfile.ZipFile(file_path, "r") as z:
                        if "content.xml" in z.namelist():
                            TechnicalLogger.log("INFO", f"Valid ZIP-based UDF file: {file_path}")
                            return True
                except zipfile.BadZipFile:
                    pass
                TechnicalLogger.log("ERROR", f"PK header but not a valid UDF ZIP: {file_path}")
                raise HTTPException(status_code=400, detail="UDF dosyası bozuk veya geçersiz format.")
            elif header.startswith(b"<?xml") or header.startswith(b"<udf"):
                # XML tabanlı UDF — ilk 512 byte içinde <udf etiketi aranır
                with open(file_path, "rb") as f:
                    preview = f.read(512)
                if b"<udf" in preview:
                    TechnicalLogger.log("INFO", f"Valid XML-based UDF file: {file_path}")
                    return True
                TechnicalLogger.log("ERROR", f"XML header but no <udf tag found: {file_path}")
                raise HTTPException(status_code=400, detail="UDF dosyası bozuk veya geçersiz format.")
            else:
                TechnicalLogger.log("ERROR", f"Invalid UDF format, magic bytes: {header.hex()}")
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
                detail="Dosya formatı tanınmıyor veya desteklenmiyor. Sadece PDF ve UDF dosyaları kabul edilir.",
            )

    except IOError as e:
        TechnicalLogger.log("ERROR", f"File read error during validation: {e}")
        raise HTTPException(status_code=500, detail="Dosya doğrulama sırasında hata oluştu.")


def validate_file_size(file_path: str) -> bool:
    """Dosya boyutunu kontrol eder - DoS saldırılarını engeller. Max: 100 MB"""
    try:
        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)

        if size > validate_file_size.MAX_BYTES:
            security_logger.log_event(
                "OVERSIZED_FILE_REJECTED",
                "WARNING",
                f"File too large: {size_mb:.2f}MB",
                {"file": file_path, "size_mb": size_mb, "limit_mb": validate_file_size.MAX_MB},
            )
            TechnicalLogger.log(
                "WARNING",
                f"File too large: {size_mb:.2f}MB (max: {validate_file_size.MAX_MB}MB)",
                {"file": file_path},
            )
            raise HTTPException(
                status_code=413,
                detail=f"Dosya çok büyük: {size_mb:.2f}MB. Maksimum dosya boyutu: {validate_file_size.MAX_MB}MB",
            )

        TechnicalLogger.log("INFO", f"File size OK: {size_mb:.2f}MB", {"file": file_path})
        return True

    except OSError as e:
        TechnicalLogger.log("ERROR", f"Error checking file size: {e}")
        raise HTTPException(status_code=500, detail="Dosya boyutu kontrol edilemedi.")

validate_file_size.MAX_MB = 50
validate_file_size.MAX_BYTES = validate_file_size.MAX_MB * 1024 * 1024


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


def get_doctype_label(code: str) -> Optional[str]:
    """Resolves document type code to its label. Returns original code if lookup fails."""
    if not code:
        return None

    try:
        from managers.config_manager import DynamicConfig

        doctypes = DynamicConfig.get_instance().get_doctypes()
        for doc in doctypes:
            c = doc.get("kod") or doc.get("code") or doc.get("value")
            if c == code:
                return doc.get("aciklama") or doc.get("label") or doc.get("name") or code
    except Exception as e:
        TechnicalLogger.log("WARNING", f"Doctype lookup failed for {code}: {e}")

    return code
