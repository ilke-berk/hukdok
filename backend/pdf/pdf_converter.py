"""
PDF/A-2b Dönüştürücü Modül
Tüm dosyaları (PDF/Office/görüntü/UDF) PDF/A-2b formatına dönüştürür.

Bu modül GhostScript (PDF → PDF/A), LibreOffice (Word/Excel → PDF) ve
Pillow (TIFF/JPG/PNG → PDF) kullanarak dosyaları arşivleme standardı
olan PDF/A-2b formatına dönüştürür.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from pdf.format_converter import (
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    image_to_pdf,
    office_to_pdf,
)

try:
    from managers.log_manager import TechnicalLogger
except ImportError:
    # Fallback logger
    class TechnicalLogger:
        @staticmethod
        def log(level, message, metadata=None):
            import logging
            logging.log(getattr(logging, level, logging.INFO), message)


def convert_to_pdfa2b(source_path: str) -> str:
    """
    Dosyayı PDF/A-2b formatına dönüştürür.
    
    Args:
        source_path: Kaynak dosya yolu (PDF veya DOCX)
        
    Returns:
        PDF/A-2b formatındaki dosyanın yolu (temp file veya orijinal)
        
    Raises:
        Exception: Dönüşüm başarısız olursa
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Kaynak dosya bulunamadı: {source_path}")
    
    file_ext = Path(source_path).suffix.lower()
    
    # Temp dosya oluştur
    temp_dir = tempfile.gettempdir()
    output_filename = f"pdfa2b_{os.getpid()}_{Path(source_path).stem}.pdf"
    output_path = os.path.join(temp_dir, output_filename)
    
    try:
        if file_ext == '.pdf':
            # PDF → PDF/A-2b dönüşümü (GhostScript)
            TechnicalLogger.log("INFO", f"PDF → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _pdf_to_pdfa2b(source_path, output_path)

        elif file_ext in OFFICE_EXTENSIONS:
            # Word/Excel → PDF/A-2b dönüşümü (LibreOffice)
            TechnicalLogger.log("INFO", f"Office → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _office_to_pdfa2b(source_path, output_path)

        elif file_ext in IMAGE_EXTENSIONS:
            # TIFF/JPG/PNG → PDF/A-2b dönüşümü (Pillow)
            TechnicalLogger.log("INFO", f"Görüntü → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _image_to_pdfa2b(source_path, output_path)

        elif file_ext == '.udf':
             # UDF → PDF dönüşümü (UDF Converter)
             TechnicalLogger.log("INFO", f"UDF → PDF dönüşümü başlatılıyor: {source_path}")
             return _udf_to_pdfa2b(source_path, output_path)

        else:
            raise ValueError(f"Desteklenmeyen format: {file_ext}")

    except UnicodeDecodeError as e:
        # ValueError'ın alt sınıfı — aşağıdaki bilinçli ValueError dalına takılıp
        # PDF fallback'ini atlamasın (2026-07-13 prod arızası)
        TechnicalLogger.log("ERROR", f"PDF/A-2b dönüşüm hatası (decode): {e}")
        if file_ext != '.pdf':
            raise RuntimeError(
                f"{file_ext} dosyası PDF'e dönüştürülemedi. "
                "Dosya bozuk veya desteklenmeyen bir format olabilir."
            ) from e
        TechnicalLogger.log("WARNING", "Dönüşüm başarısız, orijinal dosya kullanılıyor (fallback)")
        return source_path
    except ValueError:
        # Desteklenmeyen format veya UDF dönüşüm hatası — fallback yapma, yukarı taşı
        raise
    except Exception as e:
        TechnicalLogger.log("ERROR", f"PDF/A-2b dönüşüm hatası: {e}")
        if file_ext != '.pdf':
            # Orijinal PDF olmayan dosya .pdf adıyla arşive sızamaz — fallback yok
            raise RuntimeError(
                f"{file_ext} dosyası PDF'e dönüştürülemedi. "
                "Dosya bozuk veya desteklenmeyen bir format olabilir."
            ) from e
        # PDF için fallback: orijinal dosyayı döndür
        TechnicalLogger.log("WARNING", "Dönüşüm başarısız, orijinal dosya kullanılıyor (fallback)")
        return source_path


def _pdf_to_pdfa2b(source_pdf: str, output_pdf: str) -> str:
    """
    GhostScript ile PDF → PDF/A-2b dönüşümü.
    
    Args:
        source_pdf: Kaynak PDF dosyası
        output_pdf: Çıktı PDF/A-2b dosyası
        
    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    # GhostScript komut satırı (Windows)
    gs_executable = _find_ghostscript()
    
    if not gs_executable:
        raise FileNotFoundError("GhostScript bulunamadı! Lütfen kurulum yapın.")
    
    gs_command = [
        gs_executable,
        "-dPDFA=2",              # PDF/A-2b standardı
        "-dBATCH",               # Batch mode
        "-dNOPAUSE",             # Pause etme
        "-dNOOUTERSAVE",
        "-sColorConversionStrategy=RGB",
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={output_pdf}",
        source_pdf
    ]
    
    try:
        result = subprocess.run(
            gs_command,
            capture_output=True,
            text=True,
            # GS çıktısı taramalı PDF'lerde ham Latin-1 bayt içerebilir (örn. 0xae);
            # errors="replace" olmadan decode UnicodeDecodeError fırlatır
            encoding="utf-8",
            errors="replace",
            timeout=60
        )
        
        if result.returncode == 0 and os.path.exists(output_pdf):
            file_size = os.path.getsize(output_pdf) / 1024  # KB
            TechnicalLogger.log("INFO", f"✅ PDF → PDF/A-2b başarılı: {output_pdf} ({file_size:.1f} KB)")
            return output_pdf
        else:
            error_msg = result.stderr or "Bilinmeyen hata"
            raise Exception(f"GhostScript hatası: {error_msg}")
            
    except subprocess.TimeoutExpired:
        TechnicalLogger.log("ERROR", "GhostScript timeout (60s aşıldı)")
        raise Exception("PDF/A-2b dönüşümü timeout") from None


def _office_to_pdfa2b(source_office: str, output_pdf: str) -> str:
    """
    LibreOffice ile Word/Excel → PDF → PDF/A-2b dönüşümü.

    Args:
        source_office: Kaynak Word/Excel dosyası
        output_pdf: Çıktı PDF/A-2b dosyası

    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    intermediate_pdf = office_to_pdf(source_office)
    try:
        TechnicalLogger.log("INFO", "Office → PDF tamamlandı, PDF/A-2b'ye dönüştürülüyor...")
        return _pdf_to_pdfa2b(intermediate_pdf, output_pdf)
    finally:
        if os.path.exists(intermediate_pdf) and intermediate_pdf != output_pdf:
            os.remove(intermediate_pdf)


def _image_to_pdfa2b(source_image: str, output_pdf: str) -> str:
    """
    Pillow ile görüntü (TIFF/JPG/PNG) → PDF → PDF/A-2b dönüşümü.

    Args:
        source_image: Kaynak görüntü dosyası
        output_pdf: Çıktı PDF/A-2b dosyası

    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    intermediate_pdf = image_to_pdf(source_image)
    try:
        TechnicalLogger.log("INFO", "Görüntü → PDF tamamlandı, PDF/A-2b'ye dönüştürülüyor...")
        return _pdf_to_pdfa2b(intermediate_pdf, output_pdf)
    finally:
        if os.path.exists(intermediate_pdf) and intermediate_pdf != output_pdf:
            os.remove(intermediate_pdf)


def _udf_to_pdfa2b(source_udf: str, output_pdf: str) -> str:
    """
    UDF → PDF dönüşümü (GhostScript atlanır, ReportLab çıktısı direkt kullanılır).
    GhostScript PDF/A-2b modunda ICC profili olmadan geçersiz dosya üretebilir.
    """
    try:
        from udf_converter import convert_udf_to_pdf
        TechnicalLogger.log("INFO", f"UDF → PDF dönüştürülüyor: {source_udf}")
        _, img_warnings = convert_udf_to_pdf(source_udf, output_pdf)
        if img_warnings:
            TechnicalLogger.log("WARNING", f"UDF görsel uyarıları ({len(img_warnings)}): {'; '.join(img_warnings)}")
        if not os.path.exists(output_pdf):
            raise Exception("UDF converter PDF oluşturamadı.")
        TechnicalLogger.log("INFO", f"UDF → PDF tamamlandı: {output_pdf}")
        return output_pdf
    except ImportError:
        TechnicalLogger.log("ERROR", "UDF Converter modülü bulunamadı!")
        raise
    except Exception as e:
        TechnicalLogger.log("ERROR", f"UDF → PDF hatası: {e}")
        raise


def _find_ghostscript() -> Optional[str]:
    """GhostScript executable'ını bul."""
    # Windows için olası yollar
    possible_paths = [
        r"C:\Program Files\gs\gs10.06.0\bin\gswin64c.exe",  # Latest installed version
        r"C:\Program Files\gs\gs10.03.1\bin\gswin64c.exe",
        r"C:\Program Files\gs\gs10.03.0\bin\gswin64c.exe",
        r"C:\Program Files\gs\gs10.02.1\bin\gswin64c.exe",
        "gswin64c.exe",  # PATH'te varsa
        "gs",  # Linux/Mac
    ]
    
    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None


