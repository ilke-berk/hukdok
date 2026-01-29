"""
PDF/A-2b Dönüştürücü Modül
Tüm dosyaları (PDF/DOCX) PDF/A-2b formatına dönüştürür.

Bu modül GhostScript ve LibreOffice kullanarak dosyaları arşivleme standardı
olan PDF/A-2b formatına dönüştürür.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

try:
    from log_manager import TechnicalLogger
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
            
        elif file_ext in ['.docx', '.doc']:
            # DOCX → PDF/A-2b dönüşümü (LibreOffice)
            TechnicalLogger.log("INFO", f"DOCX → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _docx_to_pdfa2b(source_path, output_path)
            
        elif file_ext == '.udf':
             # UDF → PDF/A-2b dönüşümü (UDF Converter + GhostScript)
             TechnicalLogger.log("INFO", f"UDF → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
             return _udf_to_pdfa2b(source_path, output_path)

        else:
            raise ValueError(f"Desteklenmeyen format: {file_ext}")
            
    except Exception as e:
        TechnicalLogger.log("ERROR", f"PDF/A-2b dönüşüm hatası: {e}")
        # Fallback: Orijinal dosyayı döndür
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
        raise Exception("PDF/A-2b dönüşümü timeout")


def _docx_to_pdfa2b(source_docx: str, output_pdf: str) -> str:
    """
    LibreOffice ile DOCX → PDF → PDF/A-2b dönüşümü.
    
    Args:
        source_docx: Kaynak DOCX dosyası
        output_pdf: Çıktı PDF/A-2b dosyası
        
    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    lo_executable = _find_libreoffice()
    
    if not lo_executable:
        raise FileNotFoundError("LibreOffice bulunamadı! Lütfen kurulum yapın.")
    
    # LibreOffice komut satırı
    output_dir = os.path.dirname(output_pdf)
    
    lo_command = [
        lo_executable,
        "--headless",
        "--convert-to", "pdf:writer_pdf_Export",
        "--outdir", output_dir,
        source_docx
    ]
    
    try:
        result = subprocess.run(
            lo_command,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # LibreOffice çıktı dosyası adını tahmin et
        expected_output = os.path.join(
            output_dir,
            Path(source_docx).stem + ".pdf"
        )
        
        if os.path.exists(expected_output):
            # Temp PDF'i PDF/A-2b'ye dönüştür
            TechnicalLogger.log("INFO", "DOCX → PDF tamamlandı, PDF/A-2b'ye dönüştürülüyor...")
            final_output = _pdf_to_pdfa2b(expected_output, output_pdf)
            
            # Temp PDF'i temizle
            if os.path.exists(expected_output) and expected_output != final_output:
                os.remove(expected_output)
                
            return final_output
        else:
            error_msg = result.stderr or "Dosya oluşturulamadı"
            raise Exception(f"LibreOffice dönüşüm hatası: {error_msg}")
            
    except subprocess.TimeoutExpired:
        TechnicalLogger.log("ERROR", "LibreOffice timeout (120s aşıldı)")
        raise Exception("DOCX → PDF dönüşümü timeout")


def _udf_to_pdfa2b(source_udf: str, output_pdf: str) -> str:
    """
    UDF → PDF → PDF/A-2b dönüşümü.
    
    Args:
        source_udf: Kaynak UDF dosyası
        output_pdf: Çıktı PDF/A-2b dosyası
        
    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    temp_pdf = None
    try:
        # 1. UDF'i normal PDF'e dönüştür (udf_converter modülü ile)
        from udf_converter import convert_udf_to_pdf
        
        # Temp intermediate PDF path
        temp_dir = tempfile.gettempdir()
        temp_pdf = os.path.join(temp_dir, f"inter_udf_{os.getpid()}_{Path(source_udf).stem}.pdf")
        
        # Sync conversion
        TechnicalLogger.log("INFO", f"Ara katman: UDF → PDF dönüştürülüyor ({source_udf})")
        convert_udf_to_pdf(source_udf, temp_pdf)
        
        if not os.path.exists(temp_pdf):
             raise Exception("UDF converter geçici PDF oluşturamadı.")
             
        # 2. Normal PDF'i PDF/A-2b'ye dönüştür (GhostScript ile)
        TechnicalLogger.log("INFO", "PDF → PDF/A-2b dönüştürülüyor...")
        final_output = _pdf_to_pdfa2b(temp_pdf, output_pdf)
        
        return final_output
        
    except ImportError:
        TechnicalLogger.log("ERROR", "UDF Converter modülü bulunamadı!")
        raise
    except Exception as e:
        TechnicalLogger.log("ERROR", f"UDF → PDF/A-2b hatası: {e}")
        raise
    finally:
        # Ara PDF'i temizle
        if temp_pdf and os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except:
                pass


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


def _find_libreoffice() -> Optional[str]:
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
                timeout=5
            )
            if result.returncode == 0:
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None


# Test fonksiyonu
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("PDFConverterTest")

    logger.info("PDF/A-2b Dönüştürücü Test")
    logger.info("-" * 50)
    
    # GhostScript kontrolü
    gs = _find_ghostscript()
    if gs:
        logger.info(f"✅ GhostScript bulundu: {gs}")
    else:
        logger.error("❌ GhostScript bulunamadı!")
    
    # LibreOffice kontrolü
    lo = _find_libreoffice()
    if lo:
        logger.info(f"✅ LibreOffice bulundu: {lo}")
    else:
        logger.error("❌ LibreOffice bulunamadı!")
    
    # Test dosyası varsa dönüştür
    test_file = "test.pdf"
    if os.path.exists(test_file):
        logger.info(f"\nTest dosyası dönüştürülüyor: {test_file}")
        try:
            result = convert_to_pdfa2b(test_file)
            logger.info(f"✅ Başarılı: {result}")
        except Exception as e:
            logger.error(f"❌ Hata: {e}")
    else:
        logger.warning(f"\n⚠️ Test dosyası bulunamadı: {test_file}")
