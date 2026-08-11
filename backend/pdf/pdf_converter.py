"""
PDF/A-2b Dönüştürücü Modül
Tüm dosyaları (PDF/Office/görüntü/UDF) PDF/A-2b formatına dönüştürür.

Bu modül GhostScript (PDF → PDF/A), LibreOffice (Word/Excel → PDF) ve
Pillow (TIFF/JPG/PNG → PDF) kullanarak dosyaları arşivleme standardı
olan PDF/A-2b formatına dönüştürür.
"""

import functools
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from config.settings import settings
from pdf.format_converter import (
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    ConversionBusyError,
    _clip_timeout,
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


def convert_to_pdfa2b(source_path: str, time_budget_seconds: Optional[float] = None) -> str:
    """
    Dosyayı PDF/A-2b formatına dönüştürür.

    Args:
        source_path: Kaynak dosya yolu (PDF veya DOCX)
        time_budget_seconds: Faz 5-A (plan 5.2) istek zaman bütçesi — verilirse
            zincirdeki alt bileşenler (semafor beklemeleri, LO ve GS alt-süreç
            timeout'ları) kalan bütçeden pay alır; nginx 300 sn penceresi
            içinde bitmeyecek zincir kurulamaz. None → bütçesiz (gece retry
            job'ı ve /process normalizasyonu — bugüne kadarki davranış aynen).

    Returns:
        PDF/A-2b formatındaki dosyanın yolu (temp file veya orijinal)

    Raises:
        ConversionBusyError: Bütçeli yolda dönüşüm kuyruğu doluysa (çağıran
            503 "sistem meşgul" üretir; conversion_pending katmanına DÜŞMEZ)
        Exception: Dönüşüm başarısız olursa
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Kaynak dosya bulunamadı: {source_path}")

    deadline = (
        time.monotonic() + time_budget_seconds if time_budget_seconds is not None else None
    )

    file_ext = Path(source_path).suffix.lower()

    # Temp dosya oluştur
    temp_dir = tempfile.gettempdir()
    output_filename = f"pdfa2b_{os.getpid()}_{Path(source_path).stem}.pdf"
    output_path = os.path.join(temp_dir, output_filename)

    try:
        if file_ext == '.pdf':
            # PDF → PDF/A-2b dönüşümü (GhostScript)
            TechnicalLogger.log("INFO", f"PDF → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _pdf_to_pdfa2b(source_path, output_path, deadline)

        elif file_ext in OFFICE_EXTENSIONS:
            # Word/Excel → PDF/A-2b dönüşümü (LibreOffice)
            TechnicalLogger.log("INFO", f"Office → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _office_to_pdfa2b(source_path, output_path, deadline)

        elif file_ext in IMAGE_EXTENSIONS:
            # TIFF/JPG/PNG → PDF/A-2b dönüşümü (Pillow)
            TechnicalLogger.log("INFO", f"Görüntü → PDF/A-2b dönüşümü başlatılıyor: {source_path}")
            return _image_to_pdfa2b(source_path, output_path, deadline)

        elif file_ext == '.udf':
             # UDF → PDF dönüşümü (UDF Converter)
             TechnicalLogger.log("INFO", f"UDF → PDF dönüşümü başlatılıyor: {source_path}")
             return _udf_to_pdfa2b(source_path, output_path, deadline)

        else:
            raise ValueError(f"Desteklenmeyen format: {file_ext}")

    except ConversionBusyError:
        # Faz 5-A (5.2): "sistem dolu" bir dönüşüm hatası DEĞİLDİR — aşağıdaki
        # sarmalayıcılara (fallback / RuntimeError) yakalanmadan çağırana gider.
        raise
    except UnicodeDecodeError as e:
        # ValueError'ın alt sınıfı — aşağıdaki bilinçli ValueError dalına takılıp
        # PDF fallback'ini atlamasın (2026-07-13 prod arızası)
        # Faz 3-F: deneme-düzeyi log WARNING — dönüşüm hatası artık belge için
        # nihai değil (conversion_pending katmanı + gece retry); nihai tek
        # ERROR'u akış sahibi üretir (gece job'ı MAX'ta / pipeline katman-arızasında).
        TechnicalLogger.log("WARNING", f"PDF/A-2b dönüşüm hatası (decode): {e}")
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
        # Faz 3-F: deneme-düzeyi WARNING (yukarıdaki decode dalıyla aynı gerekçe)
        TechnicalLogger.log("WARNING", f"PDF/A-2b dönüşüm hatası: {e}")
        if file_ext != '.pdf':
            # Orijinal PDF olmayan dosya .pdf adıyla arşive sızamaz — fallback yok.
            # "Dosya bozuk" deme: neden bilinmiyor, dosya sağlam olabilir
            # (2026-08-05: sağlam UDF'e 7 kez "bozuk" denildi).
            raise RuntimeError(
                f"{file_ext} dosyası PDF'e dönüştürülemedi "
                "(beklenmeyen dönüşüm hatası — teknik kayıt alındı)."
            ) from e
        # PDF için fallback: orijinal dosyayı döndür
        TechnicalLogger.log("WARNING", "Dönüşüm başarısız, orijinal dosya kullanılıyor (fallback)")
        return source_path


def _gs_timeout() -> int:
    """GhostScript zaman tavanı, saniye — evi config/settings.py
    (env: GS_TIMEOUT_SECONDS, Faz 5-A; bozuk değerde varsayılana düşme
    toleransı artık settings katmanında).

    nginx katmanları (host + konteyner) /confirm için 300s'e izin veriyor;
    varsayılan 240s. Bütçeli yolda (plan 5.2) efektif değer kalan bütçeyle
    ayrıca kırpılır. Çağrı anında okunur: testler settings attribute'unu
    monkeypatch'leyebilir."""
    return settings.gs_timeout_seconds


def _pdf_to_pdfa2b(source_pdf: str, output_pdf: str, deadline: Optional[float] = None) -> str:
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
    
    # Faz 5-A (5.2): tavan ile kalan istek bütçesinin küçüğü (deadline=None →
    # tavan aynen). Bütçe LO/semafor beklemesinde eridiyse GS kısa timeout'la
    # düşer → çağıran zincir mevcut hata yoluna (fallback / pending) gider.
    gs_timeout = _clip_timeout(_gs_timeout(), deadline)
    try:
        step_start = time.perf_counter()
        result = subprocess.run(
            gs_command,
            capture_output=True,
            text=True,
            # GS çıktısı taramalı PDF'lerde ham Latin-1 bayt içerebilir (örn. 0xae);
            # errors="replace" olmadan decode UnicodeDecodeError fırlatır
            encoding="utf-8",
            errors="replace",
            timeout=gs_timeout
        )
        elapsed = time.perf_counter() - step_start

        if result.returncode == 0 and os.path.exists(output_pdf):
            file_size = os.path.getsize(output_pdf) / 1024  # KB
            TechnicalLogger.log("INFO", f"✅ PDF → PDF/A-2b başarılı ({elapsed:.1f}s): {output_pdf} ({file_size:.1f} KB)")
            return output_pdf
        else:
            # stderr kırpılır: taranmış PDF'lerde GS nesne başına uyarı basar,
            # tam çıktı TechnicalLogger buffer'ına MB'lık kalıcı kayıt gömüyordu
            error_msg = (result.stderr or "Bilinmeyen hata")[:2048]
            raise Exception(f"GhostScript hatası: {error_msg}")

    except subprocess.TimeoutExpired:
        # Faz 3-F: deneme-düzeyi WARNING — nihai ERROR akış sahibinde
        TechnicalLogger.log("WARNING", f"GhostScript timeout ({gs_timeout:.0f}s aşıldı)")
        raise Exception(f"PDF/A-2b dönüşümü timeout ({gs_timeout:.0f}s)") from None


def _office_to_pdfa2b(source_office: str, output_pdf: str, deadline: Optional[float] = None) -> str:
    """
    LibreOffice ile Word/Excel → PDF → PDF/A-2b dönüşümü.

    Args:
        source_office: Kaynak Word/Excel dosyası
        output_pdf: Çıktı PDF/A-2b dosyası

    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    intermediate_pdf = office_to_pdf(source_office, deadline=deadline)
    TechnicalLogger.log("INFO", "Office → PDF tamamlandı, PDF/A-2b'ye dönüştürülüyor...")
    return _pdfa_or_intermediate(intermediate_pdf, output_pdf, deadline)


def _image_to_pdfa2b(source_image: str, output_pdf: str, deadline: Optional[float] = None) -> str:
    """
    Pillow ile görüntü (TIFF/JPG/PNG) → PDF → PDF/A-2b dönüşümü.

    Args:
        source_image: Kaynak görüntü dosyası
        output_pdf: Çıktı PDF/A-2b dosyası

    Returns:
        Dönüştürülmüş PDF/A-2b dosya yolu
    """
    intermediate_pdf = image_to_pdf(source_image, deadline=deadline)
    TechnicalLogger.log("INFO", "Görüntü → PDF tamamlandı, PDF/A-2b'ye dönüştürülüyor...")
    return _pdfa_or_intermediate(intermediate_pdf, output_pdf, deadline)


def _pdfa_or_intermediate(intermediate_pdf: str, output_pdf: str, deadline: Optional[float] = None) -> str:
    """Ara PDF'i PDF/A-2b'ye dönüştürür; GS başarısız olursa ara PDF ile devam eder.

    Office/görüntü kaynaklarında elimizde zaten geçerli bir PDF var — PDF/A adımı
    çökse bile kullanıcıya hata dönmek yerine o PDF arşivlenir (son çare fallback).
    Bütçeli yolda (5.2) GS payı kalan bütçeye kırpılmıştır; bütçe biterse de aynı
    fallback işler — belge normal PDF olarak arşivlenir, istek 504'e sürüklenmez."""
    try:
        result = _pdf_to_pdfa2b(intermediate_pdf, output_pdf, deadline)
    except Exception as e:
        TechnicalLogger.log("WARNING", f"PDF/A-2b adımı başarısız ({e}), ara PDF kullanılıyor (fallback)")
        return intermediate_pdf
    if os.path.exists(intermediate_pdf) and intermediate_pdf != result:
        os.remove(intermediate_pdf)
    return result


def _udf_to_pdfa2b(source_udf: str, output_pdf: str, deadline: Optional[float] = None) -> str:
    """
    UDF → PDF dönüşümü (GhostScript atlanır, ReportLab çıktısı direkt kullanılır).
    GhostScript PDF/A-2b modunda ICC profili olmadan geçersiz dosya üretebilir.
    """
    try:
        from udf_converter import convert_udf_to_pdf
        TechnicalLogger.log("INFO", f"UDF → PDF dönüştürülüyor: {source_udf}")
        _, img_warnings = convert_udf_to_pdf(source_udf, output_pdf, deadline=deadline)
        if img_warnings:
            TechnicalLogger.log("WARNING", f"UDF görsel uyarıları ({len(img_warnings)}): {'; '.join(img_warnings)}")
        if not os.path.exists(output_pdf):
            raise Exception("UDF converter PDF oluşturamadı.")
        TechnicalLogger.log("INFO", f"UDF → PDF tamamlandı: {output_pdf}")
        return output_pdf
    except ImportError:
        # Faz 3-F: deneme-düzeyi WARNING — nihai ERROR akış sahibinde
        # (gece job'ı MAX'ta / pipeline katman-arızasında)
        TechnicalLogger.log("WARNING", "UDF Converter modülü bulunamadı!")
        raise
    except ConversionBusyError:
        # "Sistem dolu" dönüşüm hatası değildir — yanıltıcı log'suz yukarı taşı
        raise
    except Exception as e:
        TechnicalLogger.log("WARNING", f"UDF → PDF hatası: {e}")
        raise


@functools.lru_cache(maxsize=1)
def _find_ghostscript() -> Optional[str]:
    """GhostScript executable'ını bul (sonuç cache'lenir — binary yolu değişmez;
    aksi halde her dönüşüm fazladan `--version` alt süreçleri doğuruyordu)."""
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


