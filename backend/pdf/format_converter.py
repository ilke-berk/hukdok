"""
Format Dönüştürücü Modül
Görüntü (TIFF/JPEG/PNG) ve Office (Word/Excel) dosyalarını normal PDF'e çevirir.

PDF/A üretmez — çıktı standart PDF'tir. Hem analyzer'ın analiz öncesi
normalizasyon adımı hem de pdf_converter'ın PDF/A hattı bu modülü kullanır,
böylece dönüşüm mantığı tek yerde durur.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageSequence

try:
    from managers.log_manager import TechnicalLogger
except ImportError:
    # Fallback logger
    class TechnicalLogger:
        @staticmethod
        def log(level, message, metadata=None):
            import logging
            logging.log(getattr(logging, level, logging.INFO), message)


IMAGE_EXTENSIONS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}
OFFICE_EXTENSIONS = {".docx", ".doc", ".xlsx", ".xls"}
CONVERTIBLE_EXTENSIONS = IMAGE_EXTENSIONS | OFFICE_EXTENSIONS

# udf_converter ile aynı limitler: dev taramalar PDF'e gömülmeden önce küçültülür
MAX_IMAGE_PIXELS = 89478485
MAX_IMAGE_WIDTH = 10000
MAX_IMAGE_HEIGHT = 10000

LIBREOFFICE_TIMEOUT = 120

# Aynı anda en fazla 2 soffice süreci — her biri ~200MB RAM tüketebilir
_office_semaphore = threading.Semaphore(2)


def ensure_pdf(source_path: str, output_path: Optional[str] = None) -> str:
    """
    Kaynak dosyayı normal PDF'e çevirir (görüntü → Pillow, Office → LibreOffice).

    Args:
        source_path: Kaynak dosya yolu
        output_path: Çıktı PDF yolu (verilmezse temp dosya üretilir)

    Returns:
        Üretilen PDF'in yolu

    Raises:
        ValueError: Uzantı CONVERTIBLE_EXTENSIONS içinde değilse
        RuntimeError: Dönüşüm başarısız olursa
    """
    ext = Path(source_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return image_to_pdf(source_path, output_path)
    if ext in OFFICE_EXTENSIONS:
        return office_to_pdf(source_path, output_path)
    raise ValueError(f"Desteklenmeyen format: {ext}")


def _normalize_frame(frame: Image.Image) -> Image.Image:
    """PDF'e gömülemeyen modları (P/RGBA/CMYK/I;16/1...) RGB'ye çevirir, dev kareleri küçültür."""
    img = frame
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    else:
        # ImageSequence iterator'ı aynı buffer'ı yeniden kullanır — kopya şart
        img = img.copy()

    width, height = img.size
    if width * height > MAX_IMAGE_PIXELS or width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        TechnicalLogger.log("WARNING", f"Oversized image frame {width}x{height}, resizing to fit limits")
        img.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.LANCZOS)
        width, height = img.size
        if width * height > MAX_IMAGE_PIXELS:
            scale = (MAX_IMAGE_PIXELS / (width * height)) ** 0.5
            img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    return img


def image_to_pdf(source_path: str, output_path: Optional[str] = None) -> str:
    """
    Görüntüyü (çok sayfalı TIFF dahil) PDF'e çevirir (Pillow).

    Returns:
        Üretilen PDF'in yolu

    Raises:
        RuntimeError: Görüntü açılamaz veya PDF üretilemezse
    """
    if output_path is None:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"imgpdf_{os.getpid()}_{uuid.uuid4().hex[:8]}.pdf",
        )

    try:
        with Image.open(source_path) as img:
            frames = [_normalize_frame(frame) for frame in ImageSequence.Iterator(img)]

        if not frames:
            raise RuntimeError("Görüntüde sayfa bulunamadı")

        frames[0].save(
            output_path,
            "PDF",
            save_all=True,
            append_images=frames[1:],
        )
    except RuntimeError:
        raise
    except Exception as e:
        TechnicalLogger.log("ERROR", f"Görüntü → PDF hatası: {e}")
        raise RuntimeError(
            "Görüntü dosyası PDF'e dönüştürülemedi. Dosya bozuk veya desteklenmeyen bir format olabilir."
        ) from e

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("Görüntü → PDF dönüşümü çıktı üretemedi")

    TechnicalLogger.log("INFO", f"Görüntü → PDF tamamlandı: {output_path} ({len(frames)} sayfa)")
    return output_path


def office_to_pdf(source_path: str, output_path: Optional[str] = None) -> str:
    """
    Word/Excel dosyasını LibreOffice headless ile PDF'e çevirir.

    Returns:
        Üretilen PDF'in yolu

    Raises:
        FileNotFoundError: LibreOffice kurulu değilse
        RuntimeError: Dönüşüm başarısız veya timeout olursa
    """
    lo_executable = find_libreoffice()
    if not lo_executable:
        raise FileNotFoundError("LibreOffice bulunamadı! Lütfen kurulum yapın.")

    ext = Path(source_path).suffix.lower()
    export_filter = "calc_pdf_Export" if ext in (".xlsx", ".xls") else "writer_pdf_Export"
    convert_target = f"pdf:{export_filter}"
    if ext in (".xlsx", ".xls") and os.getenv("EXCEL_PDF_SINGLE_PAGE_SHEETS") == "1":
        # Geniş sayfaları tek PDF sayfasına sığdırır (LibreOffice >= 7.2)
        convert_target += ':{"SinglePageSheets":{"type":"boolean","value":"true"}}'

    # Paralel soffice çağrıları ortak profil kilidinde çakışır — her çağrıya
    # benzersiz profil; aynı stem'li eşzamanlı dosyalar için benzersiz outdir.
    work_dir = tempfile.mkdtemp(prefix="lo_out_")
    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")

    lo_command = [
        lo_executable,
        "--headless",
        f"-env:UserInstallation=file:///{profile_dir.replace(os.sep, '/').lstrip('/')}",
        "--convert-to", convert_target,
        "--outdir", work_dir,
        source_path,
    ]

    try:
        with _office_semaphore:
            result = subprocess.run(
                lo_command,
                capture_output=True,
                text=True,
                timeout=LIBREOFFICE_TIMEOUT,
            )

        produced_pdf = os.path.join(work_dir, Path(source_path).stem + ".pdf")
        if not os.path.exists(produced_pdf):
            error_msg = (result.stderr or result.stdout or "").strip() or "Dosya oluşturulamadı"
            raise RuntimeError(f"LibreOffice dönüşüm hatası: {error_msg}")

        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"officepdf_{os.getpid()}_{uuid.uuid4().hex[:8]}.pdf",
            )
        shutil.move(produced_pdf, output_path)
        TechnicalLogger.log("INFO", f"Office → PDF tamamlandı: {source_path} → {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        TechnicalLogger.log("ERROR", f"LibreOffice timeout ({LIBREOFFICE_TIMEOUT}s aşıldı): {source_path}")
        raise RuntimeError("Office → PDF dönüşümü timeout") from None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)


def find_libreoffice() -> Optional[str]:
    """LibreOffice executable'ını bul."""
    # Windows için olası yollar
    possible_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "soffice",  # PATH'te varsa (Linux/Mac)
    ]

    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return None
