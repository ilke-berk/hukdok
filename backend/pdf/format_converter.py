"""
Format Dönüştürücü Modül
Görüntü (TIFF/JPEG/PNG) ve Office (Word/Excel) dosyalarını normal PDF'e çevirir.

PDF/A üretmez — çıktı standart PDF'tir. Hem analyzer'ın analiz öncesi
normalizasyon adımı hem de pdf_converter'ın PDF/A hattı bu modülü kullanır,
böylece dönüşüm mantığı tek yerde durur.
"""

import functools
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

import fitz
from PIL import Image, ImageSequence

from config.settings import settings

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

# Evi config/settings.py (env: LIBREOFFICE_TIMEOUT, Faz 5-A); alias korunur.
LIBREOFFICE_TIMEOUT = settings.libreoffice_timeout_seconds

# Aynı anda en fazla 2 soffice süreci — her biri ~200MB RAM tüketebilir
_office_semaphore = threading.Semaphore(2)

# Görüntü dönüşümü tek tek: eşzamanlı dev taramalar ana süreçte GB mertebesinde
# tepe tahsis yapıp glibc arena'larında kalıcı RSS bırakıyor (2026-07-29 OOM)
_image_semaphore = threading.Semaphore(1)


class ConversionBusyError(Exception):
    """Dönüşüm semaforu bütçeli yolda zamanında alınamadı (Faz 5-A, plan 5.2).

    RuntimeError DEĞİL bilinçli: "dönüşüm başarısız" (belge sorunu →
    conversion_pending katmanı) ile "sistem dolu" (istek sorunu → 503,
    kullanıcı birkaç dakika sonra tekrar dener) ayrı akışlardır; generic
    RuntimeError/Exception sarmalayıcıları bu tipi yutmamalıdır.
    """


def acquire_conversion_slot(semaphore, deadline: Optional[float], label: str) -> None:
    """Dönüşüm semaforunu alır; bütçeli yolda bekleme tavanlıdır (plan 5.2).

    deadline None → bloklayan acquire (bugüne kadarki davranış: gece retry
    job'ı ve /process normalizasyonu istek bütçesine bağlanmaz). deadline
    (time.monotonic tabanlı) verildiyse bekleme, acquire tavanı ile kalan
    bütçenin küçüğüyle sınırlanır; dolarsa ConversionBusyError.
    """
    if deadline is None:
        semaphore.acquire()
        return
    wait_cap = min(
        settings.conversion_acquire_timeout_seconds,
        max(deadline - time.monotonic(), 0.0),
    )
    if wait_cap <= 0 or not semaphore.acquire(timeout=wait_cap):
        TechnicalLogger.log(
            "WARNING",
            f"Dönüşüm kuyruğu dolu ({label}) — {wait_cap:.0f} sn içinde slot açılmadı",
        )
        raise ConversionBusyError(label)


def _clip_timeout(base_seconds: float, deadline: Optional[float], floor: float = 1.0) -> float:
    """Alt-bileşen timeout'u: kendi tavanı ile kalan bütçenin küçüğü (≥ floor).

    deadline None → tavan aynen (bütçesiz yol). floor, subprocess'e 0/negatif
    timeout gitmesin diye — bütçe fiilen bitmişse zaten anında TimeoutExpired
    ile dönüşüm-hatası yoluna (PDF fallback / conversion_pending) düşülür.
    """
    if deadline is None:
        return base_seconds
    return max(min(base_seconds, deadline - time.monotonic()), floor)


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
    """PDF'e gömülemeyen modları RGB'ye çevirir, dev kareleri küçültür.

    Boyut kararı ORİJİNAL mod üzerinde verilir: 1-bit G4 tarama (mode "1")
    RGB'ye açılınca 24 kat şişer; önce açıp sonra ölçmek 600 dpi A4 sayfayı
    limitlerin altında bırakıp kare başına ~100 MB tahsis ettiriyordu.
    """
    img = frame
    width, height = img.size
    oversized = width * height > MAX_IMAGE_PIXELS or width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT

    if oversized:
        TechnicalLogger.log("WARNING", f"Oversized image frame {width}x{height}, resizing to fit limits")
        # LANCZOS 1-bit üzerinde çalışmaz; griye aç (RGB değil — 3x küçük)
        if img.mode == "1":
            img = img.convert("L")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        else:
            img = img.copy()
        img.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.LANCZOS)
        width, height = img.size
        if width * height > MAX_IMAGE_PIXELS:
            img = img.resize(
                (int(width * (MAX_IMAGE_PIXELS / (width * height)) ** 0.5),
                 int(height * (MAX_IMAGE_PIXELS / (width * height)) ** 0.5)),
                Image.LANCZOS,
            )
        return img

    if img.mode in ("RGB", "L", "1"):
        # "1" olduğu gibi kalır (PDF'e CCITT ile gömülür). ImageSequence
        # iterator'ı aynı buffer'ı yeniden kullanır — kopya şart.
        return img.copy()
    return img.convert("RGB")


def _merge_single_page_pdfs(page_paths: List[str], output_path: str) -> None:
    """Tek sayfalık PDF'leri sırayla tek dosyada birleştirir (fitz)."""
    merged = fitz.open()
    try:
        for page_path in page_paths:
            with fitz.open(page_path) as page_doc:
                merged.insert_pdf(page_doc)
        merged.save(output_path)
    finally:
        merged.close()


def image_to_pdf(
    source_path: str,
    output_path: Optional[str] = None,
    deadline: Optional[float] = None,
) -> str:
    """
    Görüntüyü (çok sayfalı TIFF dahil) PDF'e çevirir (Pillow).

    Kareler tek tek işlenip tek sayfalık ara PDF'lere yazılır ve fitz ile
    birleştirilir — tüm kareleri aynı anda bellekte tutmak çok sayfalı
    taramalarda GB mertebesine çıkıyordu (2026-07-29 OOM kök nedeni).

    deadline (time.monotonic tabanlı, Faz 5-A): verilirse semafor beklemesi
    tavanlıdır; None → bloklayan acquire (bütçesiz yollar, eski davranış).

    Returns:
        Üretilen PDF'in yolu

    Raises:
        RuntimeError: Görüntü açılamaz veya PDF üretilemezse
        ConversionBusyError: Bütçeli yolda dönüşüm kuyruğu doluysa
    """
    if output_path is None:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"imgpdf_{os.getpid()}_{uuid.uuid4().hex[:8]}.pdf",
        )

    page_paths: List[str] = []
    # Faz 5-A (5.2): acquire try'ın DIŞINDA — ConversionBusyError aşağıdaki
    # generic RuntimeError sarmalayıcısına yakalanmadan çağırana taşınmalı.
    acquire_conversion_slot(_image_semaphore, deadline, "görüntü dönüşümü")
    try:
        try:
            with Image.open(source_path) as img:
                page_count = getattr(img, "n_frames", 1)
                if page_count <= 1:
                    frame = _normalize_frame(img)
                    try:
                        frame.save(output_path, "PDF")
                    finally:
                        frame.close()
                    page_count = 1
                else:
                    for raw_frame in ImageSequence.Iterator(img):
                        frame = _normalize_frame(raw_frame)
                        page_path = os.path.join(
                            tempfile.gettempdir(),
                            f"imgpg_{os.getpid()}_{uuid.uuid4().hex[:8]}.pdf",
                        )
                        try:
                            frame.save(page_path, "PDF")
                        finally:
                            frame.close()
                        page_paths.append(page_path)
                    _merge_single_page_pdfs(page_paths, output_path)
        except RuntimeError:
            raise
        except Exception as e:
            # Faz 3-F: deneme-düzeyi WARNING — dönüşüm hatası belge için nihai değil
            # (arşiv yolunda conversion_pending katmanı + gece retry; analiz yolunda
            # nihai ERROR'u stream/intake handler'ları üretir).
            TechnicalLogger.log("WARNING", f"Görüntü → PDF hatası: {e}")
            raise RuntimeError(
                "Görüntü dosyası PDF'e dönüştürülemedi. Dosya bozuk veya desteklenmeyen bir format olabilir."
            ) from e
    finally:
        _image_semaphore.release()
        for page_path in page_paths:
            try:
                os.remove(page_path)
            except OSError:
                pass

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("Görüntü → PDF dönüşümü çıktı üretemedi")

    TechnicalLogger.log("INFO", f"Görüntü → PDF tamamlandı: {output_path} ({page_count} sayfa)")
    return output_path


def office_to_pdf(
    source_path: str,
    output_path: Optional[str] = None,
    deadline: Optional[float] = None,
) -> str:
    """
    Word/Excel dosyasını LibreOffice headless ile PDF'e çevirir.

    deadline (time.monotonic tabanlı, Faz 5-A): verilirse semafor beklemesi
    tavanlı, LO alt-süreç timeout'u kalan bütçeyle kırpılır; None → eski davranış.

    Returns:
        Üretilen PDF'in yolu

    Raises:
        FileNotFoundError: LibreOffice kurulu değilse
        RuntimeError: Dönüşüm başarısız veya timeout olursa
        ConversionBusyError: Bütçeli yolda dönüşüm kuyruğu doluysa
    """
    ext = Path(source_path).suffix.lower()
    export_filter = "calc_pdf_Export" if ext in (".xlsx", ".xls") else "writer_pdf_Export"
    convert_target = f"pdf:{export_filter}"
    if ext in (".xlsx", ".xls") and os.getenv("EXCEL_PDF_SINGLE_PAGE_SHEETS") == "1":
        # Geniş sayfaları tek PDF sayfasına sığdırır (LibreOffice >= 7.2)
        convert_target += ':{"SinglePageSheets":{"type":"boolean","value":"true"}}'
    return _soffice_to_pdf(source_path, convert_target, output_path, deadline=deadline)


def html_to_pdf(source_path: str, output_path: Optional[str] = None) -> str:
    """
    HTML dosyasını LibreOffice headless ile PDF'e çevirir (aynı semafor/timeout).

    Yalnız iç kullanım içindir (e-posta gövdesi → sanal belge, expand-eml):
    .html CONVERTIBLE_EXTENSIONS'a BİLEREK eklenmez — upload yolları HTML kabul
    etmez, bu fonksiyon beyaz listeden bağımsız çağrılır.

    Returns:
        Üretilen PDF'in yolu

    Raises:
        FileNotFoundError: LibreOffice kurulu değilse
        RuntimeError: Dönüşüm başarısız veya timeout olursa
    """
    # HTML, Writer/Web bileşeninde açılır — writer_pdf_Export bu bileşende
    # geçersizdir, doğru dışa aktarma filtresi writer_web_pdf_Export.
    return _soffice_to_pdf(source_path, "pdf:writer_web_pdf_Export", output_path)


def _soffice_to_pdf(
    source_path: str,
    convert_target: str,
    output_path: Optional[str] = None,
    deadline: Optional[float] = None,
) -> str:
    """Ortak soffice hattı: benzersiz profil + outdir, semafor, grup kill."""
    lo_executable = find_libreoffice()
    if not lo_executable:
        raise FileNotFoundError("LibreOffice bulunamadı! Lütfen kurulum yapın.")

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

    # Faz 5-A (5.2): LO alt-süreç timeout'u tavan ile kalan bütçenin küçüğü.
    # Efektif değer semafor beklemesinden SONRA hesaplanır (bekleme de bütçeden).
    lo_timeout = LIBREOFFICE_TIMEOUT
    try:
        acquire_conversion_slot(_office_semaphore, deadline, "Office dönüşümü")
        try:
            lo_timeout = _clip_timeout(LIBREOFFICE_TIMEOUT, deadline)
            # soffice bir wrapper script: timeout'ta yalnız wrapper'ı öldürmek
            # soffice.bin'i yetim bırakır (~200 MB). Yeni oturum + grup kill şart.
            popen_kwargs = {"start_new_session": True} if os.name == "posix" else {}
            proc = subprocess.Popen(
                lo_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # LO çıktısı ham bayt içerebilir; errors="replace" olmadan
                # decode UnicodeDecodeError fırlatır (bkz. pdf_converter GS notu)
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
            try:
                lo_stdout, lo_stderr = proc.communicate(timeout=lo_timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.communicate()
                raise
        finally:
            _office_semaphore.release()

        produced_pdf = os.path.join(work_dir, Path(source_path).stem + ".pdf")
        if not os.path.exists(produced_pdf):
            # stderr kırpılır: tam çıktı TechnicalLogger buffer'ına gömülüp
            # kalıcı MB'lık kayıtlar üretiyordu
            error_msg = ((lo_stderr or lo_stdout or "").strip() or "Dosya oluşturulamadı")[:2048]
            raise RuntimeError(f"LibreOffice dönüşüm hatası: {error_msg}")

        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"officepdf_{os.getpid()}_{uuid.uuid4().hex[:8]}.pdf",
            )
        shutil.move(produced_pdf, output_path)
        TechnicalLogger.log("INFO", f"LibreOffice → PDF tamamlandı: {source_path} → {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        # Faz 3-F: deneme-düzeyi WARNING (yukarıdaki görüntü dalıyla aynı gerekçe)
        TechnicalLogger.log("WARNING", f"LibreOffice timeout ({lo_timeout:.0f}s aşıldı): {source_path}")
        raise RuntimeError("LibreOffice → PDF dönüşümü timeout") from None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)


@functools.lru_cache(maxsize=1)
def find_libreoffice() -> Optional[str]:
    """LibreOffice executable'ını bul (sonuç cache'lenir — binary yolu değişmez;
    aksi halde her dönüşüm fazladan `--version` alt süreçleri doğuruyordu)."""
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
