import os
import json
import sys
import asyncio
from datetime import datetime

# Force UTF-8 (Fix for Windows)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import logging
from dotenv import load_dotenv
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from typing import List, Dict, Optional, Tuple, Any, AsyncGenerator


# --- LOGGER IMPORT ---
try:
    from managers.log_manager import TechnicalLogger
except ImportError:
    # Fallback if logger missing
    class MockTechnicalLogger:
        @staticmethod
        def log(*args, **kwargs):
            logging.info(f"[MockLog] {args} {kwargs}")

    TechnicalLogger = MockTechnicalLogger

# Loglama merkezi: logging_setup.configure_logging (Faz 2-B) — api.py kurar.

# Load Environment Variables
from pathlib import Path
import uuid  # For error masking
import vault  # Import Vault
import hashlib
import random  # Retry jitter için
import time  # Benchmark için

if getattr(sys, 'frozen', False):
    # PyInstaller EXE: .env is in the same folder as the executable
    env_path = Path(sys.executable).parent / ".env"
else:
    # Dev Mode: .env is in the project root (parent of backend)
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=env_path, override=True)
GOOGLE_API_KEY = vault.get_secret("GEMINI_API_KEY")  # Use Vault

# Kullanıcının .env dosyasından modeli almaya zorluyoruz.
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")

if not GEMINI_MODEL_NAME:
    TechnicalLogger.log("ERROR", "GEMINI_MODEL_NAME environment variable is NOT set.")
    raise ValueError(
        "HATA: GEMINI_MODEL_NAME çevresel değişkeni bulunamadı! Lütfen .env dosyasını kontrol edin."
    )

if not GOOGLE_API_KEY:
    TechnicalLogger.log("ERROR", "GEMINI_API_KEY not found in .env file.")

# Gemini client (google-genai) — genai.configure globali yerine ortak modül
import gemini_client
from gemini_client import get_client as get_gemini_client
import health  # /healthz Gemini hata sayacı (Faz 2-A)
from config.settings import settings

# Retry'lar DAHİL toplam süre bütçesi (Faz 3-C). Container nginx
# proxy_read_timeout 300 sn; /process NDJSON stream'inde retry penceresi
# boyunca event akmaz → sessiz pencere 300 sn'yi aşarsa nginx 504 döner ve
# backend boşa retry'lamış olur. Bütçe "yeni bekleme/deneme BAŞLATMA"
# kapısıdır: en kötü durumda son deneme bütçenin hemen altında başlar ve
# HTTP timeout'a (120 sn, gemini_client.GEMINI_HTTP_TIMEOUT_MS) kadar
# sürebilir → toplam ≈ 170 + 120 = 290 sn < 300. (wait_for_files_active'in
# ayrı 120 sn tavanı kendi yield'inden sonra koşar, bu bütçeye girmez.)
# Faz 5-A: değerin evi config/settings.py (env: GEMINI_RETRY_DEADLINE_SECONDS);
# alias korunur, aritmetiğin bekçisi test_faz3_gemini_retry settings'ten okur.
GEMINI_RETRY_DEADLINE_SECONDS = settings.gemini_retry_deadline_seconds


async def _gemini_call_with_retry(gen_config, payload, max_retries: int = 5, stats: Optional[Dict] = None, model: Optional[str] = None):
    """Gemini API çağrısını geçici hatalarda jitter'lı exponential backoff ile retry eder.

    Sınıflandırma KOD bazlıdır (gemini_client.classify_transient):
    APIError.code ∈ {429,500,502,503,504} + httpx.TransportError. 429
    (kota/rate-limit) uzun backoff (base 5s), sunucu/ağ hataları kısa (base 1s);
    jitter'lı, tavan 30s. Retry'lar dahil toplam süre
    GEMINI_RETRY_DEADLINE_SECONDS bütçesiyle sınırlıdır.

    Devre kesici (model-başına): art arda 429/503 eşiği aşınca 60 sn açılır;
    açıkken çağrı Gemini'ye gitmeden GeminiCircuitOpenError ile hızlı-fail
    eder. Hızlı-fail NİHAİ başarısızlıktır (kullanıcıya yansır) → healthz
    sayacına işlenir; log sözleşmesinde nihai ERROR'u çağıranın handler'ı
    üretir, burası WARNING bırakır.

    health sözleşmesi (Faz 2-A): record_gemini_error() YALNIZ nihai
    başarısızlıkta çağrılır; atlatılan geçici hatalar sayılmaz.

    stats: verilirse retry_count ve retry_wait_ms alanları doldurulur (benchmark için).
    model: verilirse GEMINI_MODEL_NAME yerine kullanılır (intake motoru GEMINI_INTAKE_MODEL geçirir).
    """
    MAX_WAIT = 30.0  # saniye
    mdl = model or GEMINI_MODEL_NAME

    # Kesici kontrolü yalnız girişte: çağrı başladıktan sonra kesici açılsa da
    # eldeki retry döngüsü kendi bütçesiyle sürer (zaten zaman-sınırlı);
    # kesicinin amacı YENİ çağrıların yığılmasını önlemektir.
    remaining_open = gemini_client.circuit_open_remaining(mdl)
    if remaining_open > 0:
        health.record_gemini_error()
        TechnicalLogger.log(
            "WARNING",
            f"⛔ Gemini devre kesici açık (model={mdl}, {remaining_open:.0f} sn) — "
            f"çağrı yapılmadan reddedildi",
        )
        raise gemini_client.GeminiCircuitOpenError(mdl, remaining_open)

    client = get_gemini_client(GOOGLE_API_KEY)
    deadline = time.monotonic() + GEMINI_RETRY_DEADLINE_SECONDS
    for attempt in range(max_retries + 1):
        try:
            response = await client.aio.models.generate_content(
                model=mdl, contents=payload, config=gen_config
            )
            gemini_client.circuit_record_success(mdl)
            return response
        except Exception as e:
            kind = gemini_client.classify_transient(e)
            if kind is None:
                # Kalıcı hata (400/403/404... ya da API dışı) — retry anlamsız
                health.record_gemini_error()
                raise

            api_code = e.code if isinstance(e, genai_errors.APIError) else None
            if api_code in gemini_client.SATURATION_API_CODES:
                # Açılış olayının WARNING logu gemini_client içinde (tek nokta)
                gemini_client.circuit_record_failure(mdl)

            if attempt >= max_retries:
                # Retry hakkı bitti → nihai başarısızlık (ERROR'u çağıran loglar)
                health.record_gemini_error()
                raise

            # 429: uzun (5,10,20…), sunucu/ağ: kısa (1,2,4,8,16…); + jitter, tavan 30s
            base = 5.0 if kind == "429" else 1.0
            wait_sec = min(base * (2 ** attempt) + random.uniform(0, base), MAX_WAIT)

            if time.monotonic() + wait_sec > deadline:
                # Deadline bütçesi doldu: bekleme/deneme başlatma, nihai hatayı dön
                TechnicalLogger.log(
                    "WARNING",
                    f"⏱️ Gemini deadline bütçesi doldu ({GEMINI_RETRY_DEADLINE_SECONDS:.0f} sn) — "
                    f"retry bırakılıyor (Deneme {attempt + 1}/{max_retries})",
                )
                health.record_gemini_error()
                raise

            if stats is not None:
                stats["retry_count"] = stats.get("retry_count", 0) + 1
                stats["retry_wait_ms"] = stats.get("retry_wait_ms", 0) + wait_sec * 1000
            label = str(api_code) if api_code is not None else f"ağ/{e.__class__.__name__}"
            TechnicalLogger.log(
                "WARNING",
                f"⏳ Gemini geçici hata ({label}) — {wait_sec:.1f}s sonra tekrar denenecek "
                f"(Deneme {attempt + 1}/{max_retries})",
            )
            await asyncio.sleep(wait_sec)


# --- SYSTEM INSTRUCTION ---
# --- PROMPT IMPORT ---
try:
    from prompts import get_system_instruction
except ImportError:
    TechnicalLogger.log("ERROR", "prompts.py not found. Using fallback.")

    def get_system_instruction(dynamic_lawyers=None):
        return "ERROR"


# Import local pdf_utils
try:
    from pdf import pdf_utils
except ImportError:
    try:
        from .pdf import pdf_utils
    except ImportError:
        TechnicalLogger.log(
            "WARNING", "pdf_utils not found. Conditional OCR might fail."
        )

        pdf_utils = None

if pdf_utils is not None:
    PdfPageLimitError = pdf_utils.PdfPageLimitError
else:
    # pdf_utils yoksa bu hata hiç üretilmez; except cümlesi için yer tutucu
    class PdfPageLimitError(ValueError):
        pass

# --- DYNAMIC CONFIG ---
from managers.config_manager import DynamicConfig

# ---HİBRİT MÜVEKKİL MATCHER ---
from muvekkil_matcher_v2 import get_hibrid_matcher
# --- LIST SEARCHER ---
from list_searcher import get_list_searcher


def fix_mojibake(text: str) -> str:
    """
    Common Turkish mojibake replacements.
    """
    config = DynamicConfig.get_instance()
    # If get_mojibake_map isn't ready yet, fallback to empty or basic
    replacements = getattr(config, "get_mojibake_map", lambda: {})()

    if not replacements:
        return text

    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def is_scanned_pdf(pdf_path: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if a PDF requires OCR using advanced Hybrid/Garbage checks via pdf_utils.
    Returns: (needs_ocr: bool, extracted_text: str|None)
    """
    if not pdf_utils:
        TechnicalLogger.log("WARNING", "PDF Utils missing, forcing OCR mode.")
        return True, None

    needs_ocr, text, reason = pdf_utils.load_and_analyze_pdf(pdf_path)

    if needs_ocr:
        if reason == "ENCODING_ERROR" and text:
            cleaned_text = fix_mojibake(text)
            # Tamir başarılı mı? Hâlâ mojibake kalıpları varsa veya hiç değişmediyse OCR'a düş
            import re as _re
            _mojibake_patterns = [r"Ã¼", r"ÅŸ", r"Ä°", r"Ã§", r"Å\?", r"Ã¶", r"ÄŸ"]
            still_broken = any(_re.search(p, cleaned_text) for p in _mojibake_patterns)
            if still_broken or cleaned_text == text:
                TechnicalLogger.log(
                    "WARNING",
                    f"Mojibake repair failed ({reason}), falling back to OCR.",
                    {"file": pdf_path},
                )
                return True, None
            TechnicalLogger.log(
                "INFO",
                f"Mojibake Detected ({reason}). Repair successful.",
                {"file": pdf_path},
            )
            return False, cleaned_text

        TechnicalLogger.log(
            "INFO", "PDF Analysis: OCR Required", {"file": pdf_path, "reason": reason}
        )
        return True, None
    else:
        TechnicalLogger.log(
            "INFO",
            "PDF Analysis: Digital text detected. Using Text mode.",
            {"file": pdf_path},
        )
        return False, text


def upload_to_gemini(path: str, mime_type: str = "application/pdf") -> Any:
    """
    Uploads the given file to Gemini.
    """
    client = get_gemini_client(GOOGLE_API_KEY)
    file = client.files.upload(
        file=path,
        config=genai_types.UploadFileConfig(
            mime_type=mime_type,
            # Eski SDK display_name'i dosya adından otomatik dolduruyordu
            display_name=Path(path).name,
        ),
    )
    TechnicalLogger.log(
        "INFO",
        "Uploaded file to Gemini",
        {"display_name": file.display_name, "uri": file.uri},
    )
    return file


def _file_state_name(file: Any) -> str:
    """Yeni SDK'da file.state enum'dur (FileState); string dönerse de çalışır."""
    state = getattr(file, "state", None)
    return getattr(state, "name", None) or str(state or "")


async def wait_for_files_active(files: List[Any], deadline_seconds: float = 120.0) -> None:
    """
    Waits for the uploaded files to be processed and active.

    deadline_seconds: PROCESSING'de takılı dosya isteği sonsuza dek asmasın —
    toplam bekleme bu süreyi aşarsa TimeoutError fırlatılır.
    """
    logging.info("Waiting for file processing...")
    client = get_gemini_client(GOOGLE_API_KEY)
    deadline = time.monotonic() + deadline_seconds
    for name in (file.name for file in files):
        file = client.files.get(name=name)
        while _file_state_name(file) == "PROCESSING":
            if time.monotonic() > deadline:
                error_msg = (
                    f"File {file.name} stuck in PROCESSING (>{deadline_seconds:.0f}s)"
                )
                TechnicalLogger.log("ERROR", error_msg)
                raise TimeoutError(error_msg)
            await asyncio.sleep(1)
            file = client.files.get(name=name)
        if _file_state_name(file) != "ACTIVE":
            error_msg = f"File {file.name} failed to process state: {_file_state_name(file)}"
            TechnicalLogger.log("ERROR", error_msg)
            raise Exception(error_msg)
    logging.info("...File is ready for processing.")


def calculate_file_hash(file_path: str) -> str:
    """Calculates SHA256 hash of the file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        TechnicalLogger.log("ERROR", f"Hash calculation failed: {e}")
        return "HASH_CALCULATION_FAILED"


def get_default_json() -> Dict[str, Any]:
    """Returns a default JSON structure in case of failure."""
    return {
        "tarih": datetime.now().strftime("%Y-%m-%d"),
        "muvekkiller": [],
        "muvekkil_adi": "",
        "karsi_taraf": "", # Yeni alan
        "belgede_gecen_isimler": [],
        "belge_turu_kodu": "",
        "belge_kaynagi": "XXXX",
        "avukat_kodu": None,
        "esas_no": "",
        "court": None,
        "durum": "G",
        "ozet": "Analysis Failed",
    }


# --- CACHE MECHANISM (PostgreSQL) ---


# =====================================================================
# analyze_file_generator yardımcıları
# (Davranış birebir korunur: yield sıraları, benchmark zamanlayıcıları,
#  loglar ve try/except kapsamları orijinal akıştaki gibidir.)
# =====================================================================


def _failed_event(error_ozet: str, error_kod: str = "analysis_error") -> Dict[str, str]:
    """Nihai başarısızlık terminal olayını üretir (Faz 4-B).

    SÖZLEŞME (frontend ile ORTAK referans — birebir uyulur):

        {"status": "failed",
         "error_ozet": "<kullanıcıya gösterilecek Türkçe mesaj>",
         "error_kod": "<etiket>"}

    - `error_kod` etiketleri:
        * `gemini_saturated` — devre kesici açık / 429 / 5xx (servis doygun)
        * `gemini_blocked`   — güvenlik/gizlilik filtresi
        * `gemini_truncated` — uzunluk sınırı (MAX_TOKENS) nedeniyle kesik yanıt
        * `analysis_error`   — diğer tüm nihai başarısızlıklar
      Etiket uzayı KAPALI değildir (ileride örn. şema doğrulaması için yeni
      etiket eklenebilir); tüketiciler tanımadıkları etiketi `analysis_error`
      gibi ele almalıdır.
    - `failed` SON olaydır: ardından `complete` GELMEZ, olay `process_id`
      TAŞIMAZ (confirm adımı yok → PROCESS_CACHE yazılmaz).
    - Bu olayın üretilmesi YENİ bir ERROR log satırı EKLEMEZ; nihai ERROR'lar
      zaten çağıran handler'da yazılır (deneme-düzeyi hatalar WARNING kalır).
    - Beklenmedik istisnada route'un ürettiği `{"status": "error", "message"}`
      olayı bu sözleşmenin dışındadır ve aynen korunur.
    """
    return {"status": "failed", "error_ozet": error_ozet, "error_kod": error_kod}


# GEÇİŞ ŞİMİ (Faz 4-B): aşağıdaki iki dönüşüm adımı case_intake_analyzer ile
# PAYLAŞILIR ve intake akışı bugün default-data'lı `complete` olayını kendi
# `error` olayına çeviriyor. Intake kendi terminal olay sözleşmesine sahip
# (bu görevin kapsamı dışı) → adımlar varsayılan olarak ESKİ olayı üretmeyi
# sürdürür; analyze_file_generator state'e `legacy_complete_on_error: False`
# koyarak olayı bastırır ve `state["error_ozet"]` üzerinden `failed` üretir.
# Intake de `failed`e geçtiğinde bu bayrak ve legacy dal silinmelidir.


async def _step_udf_conversion(
    state: Dict[str, Any],
    file_hash: str,
    benchmark: Dict[str, Any],
    loop: asyncio.AbstractEventLoop,
) -> AsyncGenerator[Dict[str, Any], None]:
    """UDF → PDF dönüşüm adımı. state: file_path, temp_pdf_from_udf, failed."""
    yield {
        "status": "info",
        "message": "📄 UYAP UDF formatı tespit edildi, PDF'e dönüştürülüyor..."
    }
    try:
        from udf_converter import convert_udf_to_pdf

        # Convert UDF to temporary PDF
        t_udf = time.perf_counter()
        temp_pdf_from_udf, udf_img_warnings = await loop.run_in_executor(
            None, convert_udf_to_pdf, state["file_path"], None
        )
        benchmark["udf_conversion"] = round((time.perf_counter() - t_udf) * 1000, 2)
        state["temp_pdf_from_udf"] = temp_pdf_from_udf

        TechnicalLogger.log("INFO", f"UDF converted to PDF: {temp_pdf_from_udf}")

        # Now analyze the converted PDF instead
        state["file_path"] = temp_pdf_from_udf

        if udf_img_warnings:
            yield {
                "status": "warning",
                "message": f"⚠️ {len(udf_img_warnings)} görsel PDF'e aktarılamadı (bozuk veya desteklenmeyen format). Belgenin geri kalanı dönüştürüldü."
            }

        yield {
            "status": "info",
            "message": "✅ UDF dönüştürme tamamlandı, analiz başlıyor..."
        }

    except Exception as e:
        TechnicalLogger.log("ERROR", f"UDF conversion failed: {e}")
        state["error_ozet"] = f"UDF dönüşüm hatası: {str(e)}"
        if state.get("legacy_complete_on_error", True):
            default_data = get_default_json()
            default_data["hash"] = file_hash
            default_data["ozet"] = state["error_ozet"]
            yield {"status": "complete", "data": default_data}
        state["failed"] = True


async def _step_format_conversion(
    state: Dict[str, Any],
    file_hash: str,
    benchmark: Dict[str, Any],
    loop: asyncio.AbstractEventLoop,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Görüntü/Office → PDF dönüşüm adımı. state: file_path, temp_converted_pdf, failed."""
    from pdf.format_converter import IMAGE_EXTENSIONS, ensure_pdf

    file_ext = Path(state["file_path"]).suffix.lower()
    if file_ext in IMAGE_EXTENSIONS:
        message = "🖼️ Görüntü formatı tespit edildi, PDF'e dönüştürülüyor..."
    else:
        message = f"📄 Office formatı ({file_ext}) tespit edildi, PDF'e dönüştürülüyor..."
    yield {"status": "info", "message": message}

    try:
        t_conv = time.perf_counter()
        temp_converted_pdf = await loop.run_in_executor(
            None, ensure_pdf, state["file_path"]
        )
        benchmark["format_conversion"] = round((time.perf_counter() - t_conv) * 1000, 2)
        state["temp_converted_pdf"] = temp_converted_pdf

        TechnicalLogger.log("INFO", f"{file_ext} converted to PDF: {temp_converted_pdf}")

        # Now analyze the converted PDF instead
        state["file_path"] = temp_converted_pdf

        yield {
            "status": "info",
            "message": "✅ PDF dönüştürme tamamlandı, analiz başlıyor..."
        }

    except Exception as e:
        TechnicalLogger.log("ERROR", f"Format conversion failed ({file_ext}): {e}")
        state["error_ozet"] = f"Dosya dönüşüm hatası ({file_ext}): {str(e)}"
        if state.get("legacy_complete_on_error", True):
            default_data = get_default_json()
            default_data["hash"] = file_hash
            default_data["ozet"] = state["error_ozet"]
            yield {"status": "complete", "data": default_data}
        state["failed"] = True


async def _step_page_trim(
    file_path: str,
    benchmark: Dict[str, Any],
    loop: asyncio.AbstractEventLoop,
) -> Tuple[str, Optional[str]]:
    """Sayfa kırpma adımı. Döner: (file_path, temp_trimmed_pdf)."""
    temp_trimmed_pdf = None
    t_trim = time.perf_counter()
    try:
        trimmed = await loop.run_in_executor(
            None, pdf_utils.extract_key_pages, file_path
        )
        if trimmed != file_path:
            temp_trimmed_pdf = trimmed
            file_path = trimmed
            TechnicalLogger.log("INFO", f"Sayfa kırpma uygulandı → {trimmed}")
    except Exception as e:
        TechnicalLogger.log("WARNING", f"Sayfa kırpma başarısız, tam dosya kullanılıyor: {e}")
    benchmark["page_trim"] = round((time.perf_counter() - t_trim) * 1000, 2)
    return file_path, temp_trimmed_pdf


async def _step_decide_mode(
    file_path: str,
    file_hash: str,
    state: Dict[str, Any],
    benchmark: Dict[str, Any],
    loop: asyncio.AbstractEventLoop,
) -> AsyncGenerator[Dict[str, Any], None]:
    """OCR/TEXT mod kararı. state: needs_ocr, extracted_text, failed."""
    t1 = time.perf_counter()
    try:
        # Tavanın evi config/settings.py (env: PDF_PARSE_TIMEOUT_SECONDS, Faz 5-A)
        needs_ocr, extracted_text = await asyncio.wait_for(
            loop.run_in_executor(None, is_scanned_pdf, file_path),
            timeout=settings.pdf_parse_timeout_seconds,
        )
    except asyncio.TimeoutError:
        TechnicalLogger.log(
            "ERROR",
            f"PDF parse timeout ({settings.pdf_parse_timeout_seconds:.0f}s): {file_path}",
        )
        default_data = get_default_json()
        default_data["hash"] = file_hash
        default_data["ozet"] = "PDF ayrıştırma zaman aşımına uğradı. Dosya çok büyük veya bozuk olabilir."
        yield {"status": "error", "message": "PDF işlenemedi: zaman aşımı.", "data": default_data}
        state["failed"] = True
        return
    except ValueError as e:
        TechnicalLogger.log("ERROR", f"PDF rejected: {e}")
        default_data = get_default_json()
        default_data["hash"] = file_hash
        default_data["ozet"] = str(e)
        yield {"status": "error", "message": str(e), "data": default_data}
        state["failed"] = True
        return
    benchmark["pdf_analysis"] = round((time.perf_counter() - t1) * 1000, 2)

    if needs_ocr:
        TechnicalLogger.log(
            "INFO",
            "Taranmış veya hibrit belge algılandı, OCR moduna geçiliyor...",
            {"file": file_path},
        )
        yield {
            "status": "info",
            "message": "Belge analizi derinleştiriliyor. Okuma moduna geçiliyor, işlem biraz sürebilir...",
        }
    else:
        TechnicalLogger.log(
            "INFO", "Hızlı Mod: Metin temiz ve yeterli seviyede.", {"file": file_path}
        )
        yield {
            "status": "info",
            "message": "✅ Metin algılandı. Hızlı analiz yapılıyor...",
        }

    state["needs_ocr"] = needs_ocr
    state["extracted_text"] = extracted_text


def _pre_extract_hearing(pre_extracted: Dict[str, Any], extracted_text: str) -> None:
    """Sonraki duruşma tarihi + saati regex çıkarımı (pre_extracted'ı yerinde günceller)."""
    try:
        import re as _re
        _D = r'\d{1,2}[./\-]\d{1,2}[./\-]\d{4}'  # tarih: 1-2 haneli gün/ay
        _T = r'\d{1,2}[:.]\d{2}'                  # saat: 09:43 veya 09.43
        # (pattern, date_group, time_group_or_None)
        _hearing_patterns = [
            # "DD/MM/YYYY günü saat HH:MM" — tensip ve duruşma zaptı
            (rf'({_D})\s+g[uü]n[uü]\s+saat\s+({_T})', 1, 2),
            # "DD/MM/YYYY tarihinde/tarihine saat HH:MM"
            (rf'({_D})\s+tarihinde?\s+saat\s+({_T})', 1, 2),
            # "duruşmanın DD/MM/YYYY" — saatsiz
            (rf'duru[sş]man[ıi]n\s+({_D})', 1, None),
            # "DD/MM/YYYY tarihine/tarihinde bırakılmasına"
            (rf'({_D})\s+tarihine?\s+b[ıi]rak', 1, None),
            # "bırakılmasına ... DD/MM/YYYY" (max 80 karakter aralık, tek satır)
            (rf'b[ıi]rak[ıi]lmas[ıi]na[^.{{}}]{{0,80}}?({_D})', 1, None),
            # "ertelenmesine ... DD/MM/YYYY"
            (rf'ertelenmesine[^.{{}}]{{0,80}}?({_D})', 1, None),
        ]
        def _set_hearing(raw_date: str, raw_time: Optional[str]) -> bool:
            raw_date = raw_date.replace("-", "/").replace(".", "/")
            parts = raw_date.split("/")
            if len(parts) == 3 and len(parts[2]) == 4:
                pre_extracted["sonraki_durusma_tarihi"] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                if raw_time:
                    # saat ayracını normalize et (09.43 → 09:43)
                    pre_extracted["sonraki_durusma_saati"] = raw_time.replace(".", ":")
                TechnicalLogger.log("INFO", f"📅 [PRE] Sonraki duruşma: {pre_extracted['sonraki_durusma_tarihi']} {pre_extracted.get('sonraki_durusma_saati') or ''}")
                return True
            return False

        for pat, dg, tg in _hearing_patterns:
            m = _re.search(pat, extracted_text, _re.IGNORECASE)
            if m and _set_hearing(m.group(dg), m.group(tg) if tg else None):
                break

        # Etiket-pencere kalıbı (tebligat zarfı form yerleşimi):
        # "Duruşma Günü / Duruşma Saati" etiketli form alanlarında değerler
        # etiketten ÖNCE gelebilir (PDF metin sırası). Etiketin çevresindeki
        # pencerede etikete en yakın tarih + saat aranır.
        if not pre_extracted.get("sonraki_durusma_tarihi"):
            for lbl in _re.finditer(r'duru[sş]ma\s+g[uü]n[uü]', extracted_text, _re.IGNORECASE):
                before = extracted_text[max(0, lbl.start() - 200):lbl.start()]
                after = extracted_text[lbl.end():lbl.end() + 200]
                for window, nearest_last in ((before, True), (after, False)):
                    dates = _re.findall(_D, window)
                    if not dates:
                        continue
                    # Noktalı tarihler (17.11.2026) saat kalıbına da uyar; önce tarihleri sil
                    times = _re.findall(_T, _re.sub(_D, " ", window))
                    raw_date = dates[-1] if nearest_last else dates[0]
                    raw_time = (times[-1] if nearest_last else times[0]) if times else None
                    if _set_hearing(raw_date, raw_time):
                        break
                if pre_extracted.get("sonraki_durusma_tarihi"):
                    break
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[PRE] Duruşma tarihi çıkarımı hatası: {e}")


def _pre_extract_fields(
    pre_extracted: Dict[str, Any],
    extracted_text: str,
    preset_belge_turu_kodu: Optional[str],
) -> None:
    """Regex/List ön çıkarıcılar (LLM'den önce). pre_extracted'ı yerinde doldurur."""
    # 1. Tarih (Regex)
    try:
        from extractors.date_extractor import find_best_date
        pre_extracted["tarih"] = find_best_date(extracted_text)
        if pre_extracted["tarih"]:
            TechnicalLogger.log("INFO", f"📅 [PRE] Tarih bulundu: {pre_extracted['tarih']}")
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[PRE] Tarih çıkarımı hatası: {e}")

    # 2. Esas No (Regex)
    try:
        from extractors.esas_no_extractor import find_best_esas_no
        pre_extracted["esas_no"] = find_best_esas_no(extracted_text)
        if pre_extracted["esas_no"]:
            TechnicalLogger.log("INFO", f"🔢 [PRE] Esas No bulundu: {pre_extracted['esas_no']}")
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[PRE] Esas No çıkarımı hatası: {e}")


    # 4. Müvekkil Adayları (FlashText)
    try:
        searcher = get_list_searcher()
        pre_extracted["muvekkil_candidates"] = searcher.search(extracted_text)
        if pre_extracted["muvekkil_candidates"]:
            TechnicalLogger.log("INFO", f"👤 [PRE] Müvekkil adayları: {pre_extracted['muvekkil_candidates']}", {"count": len(pre_extracted["muvekkil_candidates"])})
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[PRE] Müvekkil arama hatası: {e}")

    # 5. Mahkeme Adı (Hibrit Regex)
    try:
        from extractors.court_extractor import find_court_name
        pre_extracted["court"] = find_court_name(extracted_text)
        if pre_extracted["court"]:
            TechnicalLogger.log("INFO", f"🏛️ [PRE] Mahkeme bulundu: {pre_extracted['court']}")
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[PRE] Mahkeme çıkarımı hatası: {e}")

    # 6. Sonraki Duruşma Tarihi + Saati (Regex — duruşma/tensip zaptı ve tebligat belgeleri için)
    from constants import is_hearing_doctype
    if is_hearing_doctype(preset_belge_turu_kodu):
        _pre_extract_hearing(pre_extracted, extracted_text)


def _detect_missing_fields(pre_extracted: Dict[str, Any]) -> List[str]:
    """Ön çıkarımda bulunamayan alanları listeler."""
    missing_fields = []
    if not pre_extracted["tarih"]:
        missing_fields.append("tarih")
    if not pre_extracted["esas_no"]:
        missing_fields.append("esas_no")
    if not pre_extracted["muvekkil_candidates"]:
        missing_fields.append("muvekkil")
    if not pre_extracted["court"]:
        missing_fields.append("court")
    return missing_fields


def _build_prompt_and_config(
    pre_extracted: Dict[str, Any],
    missing_fields: List[str],
    preset_belge_turu_kodu: Optional[str],
    benchmark: Dict[str, Any],
) -> Tuple[Any, List[Dict]]:
    """Dinamik promptu ve GenerateContentConfig'i kurar. Döner: (gen_config, lawyers)."""
    # Promptu dinamik oluştur (Singleton Konfigürasyon Kullan)
    t_prompt = time.perf_counter()
    config = DynamicConfig.get_instance()
    lawyers = config.get_lawyers()
    statuses = config.get_statuses()
    doctypes = config.get_doctypes()

    # 🆕 YENİ: Dinamik prompt oluştur (eksik alanlar ve ön çıkarım bilgisi ile)
    sys_inst = get_system_instruction(
        dynamic_lawyers=lawyers,
        dynamic_doctypes=doctypes,
        dynamic_statuses=statuses,
        candidates=pre_extracted["muvekkil_candidates"],
        missing_fields=missing_fields,
        pre_extracted=pre_extracted,
        belge_turu_kodu=preset_belge_turu_kodu,
    )

    gen_config = genai_types.GenerateContentConfig(system_instruction=sys_inst)
    benchmark["prompt_build"] = round((time.perf_counter() - t_prompt) * 1000, 2)
    return gen_config, lawyers


async def _step_ai_call(
    state: Dict[str, Any],
    gen_config: Any,
    needs_ocr: bool,
    extracted_text: Optional[str],
    file_path: str,
    benchmark: Dict[str, Any],
    ai_stats: Dict[str, Any],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Gemini çağrısı (OCR/TEXT modu). state: uploaded_file, response."""
    if needs_ocr:
        # --- OCR MODE ---
        benchmark["mode"] = "OCR"
        TechnicalLogger.log("INFO", "MODE: OCR Activated")
        t_up = time.perf_counter()
        uploaded_file = upload_to_gemini(file_path)
        state["uploaded_file"] = uploaded_file
        benchmark["upload_ms"] = round((time.perf_counter() - t_up) * 1000, 2)
        yield {"status": "info", "message": "⏳ Dosya işleniyor..."}
        t_wait = time.perf_counter()
        await wait_for_files_active([uploaded_file])
        benchmark["wait_active_ms"] = round((time.perf_counter() - t_wait) * 1000, 2)
        t_gen = time.perf_counter()
        response = await _gemini_call_with_retry(gen_config, [uploaded_file], stats=ai_stats)
        benchmark["generate_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)
    else:
        # --- TEXT MODE ---
        benchmark["mode"] = "TEXT"
        TechnicalLogger.log("INFO", "MODE: TEXT Activated")

        # Validate text length again
        if extracted_text and len(extracted_text) < 50:
            # Fallback to OCR if text is suspiciously short (redundant check)
            benchmark["mode"] = "TEXT->OCR_FALLBACK"
            TechnicalLogger.log(
                "WARNING",
                "Text too short, falling back to OCR",
                {"len": len(extracted_text)},
            )
            t_up = time.perf_counter()
            uploaded_file = upload_to_gemini(file_path)
            state["uploaded_file"] = uploaded_file
            benchmark["upload_ms"] = round((time.perf_counter() - t_up) * 1000, 2)
            t_gen = time.perf_counter()
            response = await _gemini_call_with_retry(gen_config, [uploaded_file], stats=ai_stats)
            benchmark["generate_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)
        else:
            t_gen = time.perf_counter()
            response = await _gemini_call_with_retry(gen_config, extracted_text, stats=ai_stats)
            benchmark["generate_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)

    state["response"] = response


def _record_token_usage(response: Any, benchmark: Dict[str, Any]) -> None:
    """⏱️ Token sayıları — generate_ms'in belge boyutuyla mı orantılı olduğunu
    test etmek için (lokal-prod hız farkı: eşzamanlılık mı, belge boyutu mu?)."""
    try:
        um = getattr(response, "usage_metadata", None)
        if um is not None:
            benchmark["prompt_tokens"] = getattr(um, "prompt_token_count", None)
            benchmark["output_tokens"] = getattr(um, "candidates_token_count", None)
            benchmark["total_tokens"] = getattr(um, "total_token_count", None)
    except Exception as e:
        TechnicalLogger.log("WARNING", f"usage_metadata okunamadı: {e}")


# ── Yanıt doğrulama (Faz 3-C): finish_reason KOD bazlı okunur ────────────────
# Eskiden response.text None ise her durumda "güvenlik filtresi" deniyordu;
# MAX_TOKENS kesilmesi ve nedensiz boş yanıt yanlış etiketleniyordu.

class GeminiResponseError(ValueError):
    """Boş/kullanılamaz Gemini yanıtı (neden bilinmiyor ya da sıradışı)."""


class GeminiTruncatedError(GeminiResponseError):
    """Yanıt MAX_TOKENS ile kesildi — güvenlik filtresi DEĞİL."""


class GeminiBlockedError(GeminiResponseError):
    """Yanıt/istek güvenlik-gizlilik filtresine takıldı (finish/block_reason kanıtlı)."""


# FinishReason enum'ından (SDK 2.11.0, koddan doğrulandı) filtre/engel anlamına
# gelenler. RECITATION/BLOCKLIST vb. de kullanıcıya "içerik engellendi" olarak
# yansıtılır — teknik ayrıntı log'da durur.
_BLOCK_FINISH_REASONS = frozenset({
    "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY",
})


def _finish_reason_name(response: Any) -> str:
    """İlk adayın finish_reason'ını enum adı olarak döndürür ('' = yok)."""
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    if reason is None:
        return ""
    return getattr(reason, "name", None) or str(reason)


def _ensure_response_text(response: Any, context: str = "Gemini") -> str:
    """response.text'i döndürür; boş/kesik yanıtta finish_reason'a göre TİPLİ hata atar.

    MAX_TOKENS'ta metin kısmen gelmiş olsa da hata atılır: kesik JSON'u parse
    etmeye çalışmak yanıltıcı "bozuk çıktı" teşhisi üretir, oysa neden belli.
    """
    reason = _finish_reason_name(response)
    if reason == "MAX_TOKENS":
        raise GeminiTruncatedError(
            f"{context} yanıtı uzunluk sınırına takıldı (finish_reason=MAX_TOKENS)."
        )

    text = getattr(response, "text", None)
    if text is not None:
        return text

    if reason in _BLOCK_FINISH_REASONS:
        raise GeminiBlockedError(
            f"{context} yanıtı engellendi (finish_reason={reason})."
        )

    # Aday hiç yoksa istek tarafı engellenmiş olabilir: prompt_feedback'e bak
    block = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
    block_name = (getattr(block, "name", None) or str(block)) if block else ""
    if block_name and block_name != "BLOCKED_REASON_UNSPECIFIED":
        raise GeminiBlockedError(
            f"{context} isteği engellendi (block_reason={block_name})."
        )

    raise GeminiResponseError(
        f"{context} yanıtı boş döndü (finish_reason={reason or 'yok'})."
    )


def _extract_first_json(text):
    text = text.strip()
    # Find first '{'
    start_idx = text.find("{")
    if start_idx == -1:
        return None

    balance = 0
    for i in range(start_idx, len(text)):
        char = text[i]
        if char == "{":
            balance += 1
        elif char == "}":
            balance -= 1

        if balance == 0:
            return text[start_idx : i + 1]
    return None


def _parse_gemini_json(result_text: str) -> Dict[str, Any]:
    """3. Robust JSON Parsing (Brace Counting)"""
    # Optional Cleanup
    cleaned_text = result_text.replace("```json", "").replace("```", "")

    json_str = _extract_first_json(cleaned_text)

    if json_str:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: Try raw text if extraction failed logically but structure exists
            data = json.loads(cleaned_text)
    else:
        # No JSON found by key, try raw (risky but fallback)
        data = json.loads(cleaned_text)
    return data


def _apply_preset_and_karsi_taraf(
    data: Dict[str, Any],
    preset_belge_turu_kodu: Optional[str],
    debug_info: List[str],
) -> None:
    """Belge türü preset'i ve karşı taraf alanlarını düzenler."""
    # 🛡️ Belge Türü: Kullanıcı önceden seçtiyse onu kullan, aksi halde boş bırak
    if preset_belge_turu_kodu:
        data["belge_turu_kodu"] = preset_belge_turu_kodu.strip().upper()
        debug_info.append(f"- Belge Türü: Kullanıcı Önceden Seçti ({preset_belge_turu_kodu})")
    else:
        data["belge_turu_kodu"] = ""
        debug_info.append("- Belge Türü: Kullanıcıya Bırakıldı")

    # 🛡️ Karşı Taraf: UI formu için sıfırla, ama AI önerisini sakla
    # QuickCaseModal yeni dava açarken bu öneriyi kullanır
    ai_karsi_taraf = data.get("karsi_taraf", "")
    data["suggested_karsi_taraf"] = ai_karsi_taraf  # QuickCaseModal için
    data["karsi_taraf"] = ""                         # Belge onay formu için kullanıcıya bırak
    debug_info.append(f"- Karşı Taraf: Kullanıcıya Bırakıldı (AI önerisi: {ai_karsi_taraf or 'yok'})")


def _resolve_tarih_esas_court(
    data: Dict[str, Any],
    pre_extracted: Dict[str, Any],
    debug_info: List[str],
) -> None:
    """Tarih / Esas No / Mahkeme alanlarında regex ↔ LLM önceliğini uygular."""
    # 📅 TARİH
    if pre_extracted.get("tarih"):
        data["tarih"] = pre_extracted["tarih"]
        debug_info.append(f"- Tarih: REGEX ({pre_extracted['tarih']})")
    else:
        # LLM'nin bulduğu değer kalır
        debug_info.append(f"- Tarih: LLM ({data.get('tarih', 'BOŞ')})")

    # 🔢 ESAS NO
    if pre_extracted.get("esas_no"):
        data["esas_no"] = pre_extracted["esas_no"]
        debug_info.append(f"- Esas No: REGEX ({pre_extracted['esas_no']})")
    else:
        # LLM'nin bulduğu değer kalır
        debug_info.append(f"- Esas No: LLM ({data.get('esas_no', 'BOŞ')})")


    # 🏛️ MAHKEME
    ai_court = data.get("court", "")
    regex_court = pre_extracted.get("court", "")

    if regex_court:
        # Eğer AI boşsa veya regex daha uzunsa regex'i kullan
        if not ai_court or len(regex_court) > len(ai_court):
            data["court"] = regex_court
            debug_info.append(f"- Mahkeme: REGEX ({regex_court})")
        else:
            # AI daha detaylı veya tam (örn: Dava Dairesi dahil), AI'da kal ama regex'i logla
            debug_info.append(f"- Mahkeme: LLM (Regex de buldu: {regex_court})")
    elif ai_court:
         debug_info.append(f"- Mahkeme: LLM ({ai_court})")
    else:
         debug_info.append("- Mahkeme: BOŞ")


def _resolve_muvekkil_fields(
    data: Dict[str, Any],
    pre_extracted: Dict[str, Any],
    lawyers: List[Dict],
    debug_info: List[str],
) -> None:
    """👤 MÜVEKKİL (Hibrit Matcher hala gerekli) — avukat filtresi + liste doğrulama."""
    try:
        hook_muvekkil = data.get("muvekkil_adi")
        diger_isimler = data.get("belgede_gecen_isimler", [])
        avukat_var = data.get("avukat_kodu") is not None

        # 🛡️ AVUKAT FİLTRESİ: Sadece TAM isim eşleşmesi (kelime parçaları değil)
        import re as _re
        lawyer_names_upper = set()
        for lawyer in lawyers:
            name = lawyer.get("name", "")
            if name:
                full = name.upper()
                lawyer_names_upper.add(full)
                # "Av." / "Dr." öneksiz hali de ekle
                stripped = _re.sub(r'^(AV\.|DR\.|UZM\.)\s*', '', full).strip()
                lawyer_names_upper.add(stripped)
        # İ/I normalize edilmiş set (eşleşme için)
        lawyer_normalized = {n.replace("İ", "I") for n in lawyer_names_upper}

        # hook_muvekkil avukat mı? (normalize ederek karşılaştır)
        if hook_muvekkil and hook_muvekkil.upper().replace("İ", "I") in lawyer_normalized:
            TechnicalLogger.log("WARNING", f"⚠️ AVUKAT FİLTRE: '{hook_muvekkil}' avukat olarak tespit edildi, müvekkil olarak kullanılmayacak!")
            hook_muvekkil = None

        # Diğer isimlerden avukatları çıkar (sadece TAM isim eşleşmesi)
        filtered_isimler = []
        for isim in diger_isimler:
            isim_n = isim.upper().replace("İ", "I") if isim else ""
            if isim_n not in lawyer_normalized:
                filtered_isimler.append(isim)
            else:
                TechnicalLogger.log("INFO", f"⚠️ Avukat (tam isim) listesinden çıkarıldı: {isim}")


        # Güncellenmiş listeyi kaydet (GEÇİCİ - Aşağıda tekrar filtrelenecek)
        data["belgede_gecen_isimler"] = filtered_isimler

        matcher = get_hibrid_matcher()
        sonuc, kaynak, skor = matcher.filtrele(
            hook_tespit=hook_muvekkil,
            diger_isimler=filtered_isimler,
            avukat_var=avukat_var
        )

        # Sonucu güncelle
        data["muvekkil_adi"] = sonuc
        data["muvekkil_kaynak"] = kaynak  # Debug için
        data["muvekkil_benzerlik"] = round(skor, 1) if skor > 0 else 0

        # 🆕 MÜVEKKİLLER LİSTESİ FİLTRELEMESİ (SIKI MOD)
        # SADECE pre_extracted["muvekkil_candidates"] içindeki isimler kabul edilir
        raw_muvekkiller = data.get("muvekkiller", [])
        validated_muvekkiller = []

        # Pre-extraction candidates'ı set olarak al (hızlı lookup için)
        pre_cand_upper = set()
        pre_cand_map = {}  # upper -> original
        if pre_extracted.get("muvekkil_candidates"):
            for cand in pre_extracted["muvekkil_candidates"]:
                cand_upper = cand.upper().replace("İ", "I")
                pre_cand_upper.add(cand_upper)
                pre_cand_map[cand_upper] = cand

        for muv in raw_muvekkiller:
            if not muv:
                continue
            muv_upper = muv.upper().replace("İ", "I")

            # Avukat mı?
            is_lawyer = False
            for lawyer_name in lawyer_names_upper:
                if lawyer_name in muv_upper or muv_upper in lawyer_name:
                    is_lawyer = True
                    break

            if is_lawyer:
                TechnicalLogger.log("INFO", f"⚠️ Müvekkil listesinden avukat çıkarıldı: {muv}")
                continue

            # 🛡️ SIKI FİLTRE: Sadece SharePoint listesindekiler kabul edilir
            if muv_upper in pre_cand_upper:
                # Standart ismi kullan (SharePoint'teki haliyle)
                validated_muvekkiller.append(pre_cand_map[muv_upper])
            else:
                # Listede yok - "Diğer İsimler"e bırak, müvekkillere ekleme
                TechnicalLogger.log("INFO", f"ℹ️ Müvekkil listesinde yok, atlandı: {muv}")

        # Pre-extraction'da bulunan ama LLM'nin muvekkiller'inde olmayan adayları da ekle
        for cand in pre_extracted.get("muvekkil_candidates", []):
            cand_upper = cand.upper().replace("İ", "I")
            if cand_upper not in {m.upper().replace("İ", "I") for m in validated_muvekkiller}:
                validated_muvekkiller.append(cand)



        # Duplicate temizle (sıra koruyarak)
        seen = set()
        unique_muvekkiller = []
        for m in validated_muvekkiller:
            m_key = m.upper().replace("İ", "I")
            if m_key not in seen:
                seen.add(m_key)
                unique_muvekkiller.append(m)

        data["muvekkiller"] = unique_muvekkiller

        # 🆕 İLK ELEMANI ANA MÜVEKKİL YAP
        if unique_muvekkiller and not data.get("muvekkil_adi"):
            data["muvekkil_adi"] = unique_muvekkiller[0]
            TechnicalLogger.log("INFO", f"📌 Ana müvekkil listeden atandı: {unique_muvekkiller[0]}")

        # Pre-extraction'da aday bulunduysa belirt
        if pre_extracted.get("muvekkil_candidates"):
            debug_info.append(f"- Müvekkil: HİBRİT [Pre-Adaylar: {len(pre_extracted['muvekkil_candidates'])}] → {data.get('muvekkil_adi')} ({kaynak})")
        else:
            debug_info.append(f"- Müvekkil: HİBRİT (Aday Yok) → {data.get('muvekkil_adi')} ({kaynak})")

        debug_info.append(f"- Müvekkil Listesi: {len(unique_muvekkiller)} kişi (Avukatlar ve duplikasyonlar çıkarıldı)")

        # 🆕 SON TEMİZLİK: Müvekkiller listesinde olanları "belgede_gecen_isimler"den çıkar
        # Böylece dropdown'da duplicate görünmez.
        final_muvekkil_uppers = {m.upper().replace("İ", "I") for m in unique_muvekkiller}
        cleaned_diger_isimler = []
        for isim in data.get("belgede_gecen_isimler", []):
            isim_upper = isim.upper().replace("İ", "I")
            # Eğer müvekkiller listesinde yoksa ekle
            if isim_upper not in final_muvekkil_uppers:
                cleaned_diger_isimler.append(isim)

        data["belgede_gecen_isimler"] = cleaned_diger_isimler

        # Önemli durumları logla
        if kaynak == "fallback" and hook_muvekkil != sonuc:
            TechnicalLogger.log("WARNING", f"⚠️ HOOK YANLIŞTI! '{hook_muvekkil}' yerine '{sonuc}' kullanıldı")
        elif kaynak == "bulunamadi":
            TechnicalLogger.log("WARNING", f"ℹ️ Listede bulunamadı: '{hook_muvekkil}' (Yeni müvekkil olabilir)")

    except Exception as e:
        TechnicalLogger.log("ERROR", f"Hibrit filtreleme hatası: {e}")
        debug_info.append(f"- Müvekkil: HATA ({data.get('muvekkil_adi')})")


def _apply_hearing_fields(
    data: Dict[str, Any],
    pre_extracted: Dict[str, Any],
    debug_info: List[str],
) -> None:
    """📅 SONRAKI DURUŞMA TARİHİ + SAATİ — Regex öncelikli, AI fallback"""
    if pre_extracted.get("sonraki_durusma_tarihi"):
        data["sonraki_durusma_tarihi"] = pre_extracted["sonraki_durusma_tarihi"]
        debug_info.append(f"- Sonraki Duruşma: REGEX ({pre_extracted['sonraki_durusma_tarihi']})")
    elif data.get("sonraki_durusma_tarihi"):
        debug_info.append(f"- Sonraki Duruşma: LLM ({data['sonraki_durusma_tarihi']})")
    # else: alanda null kalır, kullanıcı manuel girer

    if pre_extracted.get("sonraki_durusma_saati"):
        data["sonraki_durusma_saati"] = pre_extracted["sonraki_durusma_saati"]
    elif not data.get("sonraki_durusma_saati"):
        data["sonraki_durusma_saati"] = None

    # Plausibility guard: geçersiz ISO tarih veya belge tarihinden ÖNCEKİ duruşma
    # tarihi elenir (tebligatta zarf/evrak tarihinin duruşma günüyle karışmasına
    # karşı). Geçmiş tarihler elenmez — arşiv belgesi yüklemelerinde meşrudur.
    hd = data.get("sonraki_durusma_tarihi")
    if hd:
        from datetime import date as _date
        try:
            hd_parsed = _date.fromisoformat(str(hd))
            belge_tarihi = data.get("tarih") or pre_extracted.get("tarih")
            if belge_tarihi:
                try:
                    if hd_parsed < _date.fromisoformat(str(belge_tarihi)):
                        TechnicalLogger.log("WARNING", f"⚠️ Duruşma tarihi ({hd}) belge tarihinden ({belge_tarihi}) önce — elendi.")
                        data["sonraki_durusma_tarihi"] = None
                        data["sonraki_durusma_saati"] = None
                except ValueError:
                    pass  # belge tarihi parse edilemedi, guard atlanır
        except ValueError:
            TechnicalLogger.log("WARNING", f"⚠️ Duruşma tarihi geçersiz formatta — elendi: {hd!r}")
            data["sonraki_durusma_tarihi"] = None
            data["sonraki_durusma_saati"] = None


def _apply_filename_format(data: Dict[str, Any], debug_info: List[str]) -> None:
    """🆕 DOSYA ADI ÖN İSİM FORMATLAMA (YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad)"""
    try:
        _tr_map = str.maketrans("ÇçĞğİıÖöŞşÜü", "CcGgIiOoSsUu")

        def _to_ascii(s: str) -> str:
            return s.translate(_tr_map)

        def _format_client(full_name: str, count: int) -> str:
            """Returns A.Soyad or A.Soyad_vd per naming standard."""
            name = full_name.strip()
            if not name:
                return "XXXXX"
            # Strip titles
            import re as _re2
            name = _re2.sub(r'\b(AV|DR|PROF|UZM|DOÇ)\.?\s*', '', name, flags=_re2.IGNORECASE).strip()
            parts = name.split()
            if not parts:
                return "XXXXX"
            if len(parts) == 1:
                w = _to_ascii(parts[0])
                result = w[0].upper() + w[1:].lower()
            else:
                initial = _to_ascii(parts[0][0]).upper()
                surname_raw = _to_ascii(parts[-1])
                surname = surname_raw[0].upper() + surname_raw[1:].lower()
                result = f"{initial}.{surname}"
            if count > 1:
                result += "_vd"
            return result

        client_list = data.get("muvekkiller", [])
        if not client_list and data.get("muvekkil_adi"):
            client_list = [data.get("muvekkil_adi")]
        if not isinstance(client_list, list):
            client_list = [client_list] if isinstance(client_list, str) else []

        if client_list:
            client_str = _format_client(str(client_list[0]), len(client_list))
            data["dosya_icin_ozel_isim"] = client_str
            debug_info.append(f"- Dosya İsim: {client_str} ({len(client_list)} müvekkil)")
        else:
            debug_info.append("- Dosya İsim: OLUŞTURULAMADI (Liste boş)")

    except Exception as e:
        TechnicalLogger.log("ERROR", f"Dosya formatlama hatası: {e}")
        debug_info.append(f"- Dosya Formatı: HATA ({str(e)})")


def _api_error_ozet(err: Any, error_id: str) -> str:
    """Genel API hatası için kullanıcıya gösterilecek özet metnini üretir.

    Faz 3-C: Exception nesnesi geçirilirse sınıflandırma KOD bazlıdır
    (GeminiCircuitOpenError / APIError.code); string geçilirse eski
    string-eşleme davranışı fallback olarak korunur.
    """
    if isinstance(err, gemini_client.GeminiCircuitOpenError):
        return (
            f"⚠️ Yapay zeka servisi art arda hata verdiği için kısa süreliğine "
            f"devre dışı bırakıldı (koruma devrede). Lütfen 1 dakika sonra "
            f"tekrar deneyin. (Kod: {error_id})"
        )

    api_code = err.code if isinstance(err, genai_errors.APIError) else None
    err_str = str(err)
    if api_code == 429 or "429" in err_str or "resource exhausted" in err_str.lower():
        return (
            f"⚠️ Yapay zeka API sınırına ulaşıldı (Rate Limit). "
            f"Lütfen birkaç dakika bekleyip tekrar deneyin. (Kod: {error_id})"
        )
    elif (
        api_code in (500, 502, 503, 504)
        or "503" in err_str
        or "service is currently unavailable" in err_str.lower()
    ):
        return (
            f"⚠️ Yapay zeka servisi şu an geçici olarak kullanılamıyor (503). "
            f"Lütfen kısa süre sonra tekrar deneyin. (Kod: {error_id})"
        )
    elif api_code == 403 or "403" in err_str or "quota" in err_str.lower():
        return (
            f"API Erişim Hatası (Kota Aşımı veya Yetki Sorunu). (Kod: {error_id})"
        )
    else:
        return (
            f"Analiz teknik bir sorun nedeniyle tamamlanamadı. (Kod: {error_id})"
        )


def _api_error_kod(err: Any) -> str:
    """Genel API hatasını `failed` olayının `error_kod` etiketine eşler.

    `_api_error_ozet` ile AYNI kod bazlı sınıflandırmayı kullanır (kullanıcı
    mesajı ile makine etiketi ayrışmasın). Kota/yetki (403) doygunluk değildir
    → `analysis_error`.
    """
    if isinstance(err, gemini_client.GeminiCircuitOpenError):
        return "gemini_saturated"

    api_code = err.code if isinstance(err, genai_errors.APIError) else None
    err_str = str(err)
    if api_code == 429 or "429" in err_str or "resource exhausted" in err_str.lower():
        return "gemini_saturated"
    if (
        api_code in (500, 502, 503, 504)
        or "503" in err_str
        or "service is currently unavailable" in err_str.lower()
    ):
        return "gemini_saturated"
    return "analysis_error"


def _cleanup_temp_files(
    uploaded_file: Any,
    temp_pdf_from_udf: Optional[str],
    temp_trimmed_pdf: Optional[str],
    process_id: Optional[str],
) -> None:
    """Geçici dosyaları temizler (Gemini upload, UDF PDF, kırpılmış PDF)."""
    if uploaded_file:
        try:
            client = get_gemini_client(GOOGLE_API_KEY)
            if client:
                client.files.delete(name=uploaded_file.name)
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Error deleting Gemini file: {e}")

    if temp_pdf_from_udf and os.path.exists(temp_pdf_from_udf):
        if process_id:
            # Faz 3: PROCESS_CACHE owns this file — TTL cleanup will delete it
            TechnicalLogger.log("INFO", f"Skipping UDF PDF cleanup (cached as process_id={process_id}): {temp_pdf_from_udf}")
        else:
            try:
                os.remove(temp_pdf_from_udf)
                TechnicalLogger.log("INFO", f"Cleaned up temp UDF PDF: {temp_pdf_from_udf}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Error deleting temp UDF PDF: {e}")

    if temp_trimmed_pdf and os.path.exists(temp_trimmed_pdf):
        try:
            os.remove(temp_trimmed_pdf)
            TechnicalLogger.log("INFO", f"Cleaned up trimmed PDF: {temp_trimmed_pdf}")
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Error deleting trimmed PDF: {e}")


async def analyze_file_generator(
    file_path: str,
    file_hash: Optional[str] = None,
    process_id: Optional[str] = None,
    preset_belge_turu_kodu: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generator that yields status updates and finally the result.
    Yields: {"status": "info"/"warning"/"error"/"complete"/"failed", ...}

    İKİ terminal olay vardır (Faz 4-B):
      * Başarı: {"status": "complete", "data": {...}, "full_pdf_path": "..."}
      * Nihai başarısızlık: `_failed_event` sözleşmesi — {"status": "failed",
        "error_ozet": ..., "error_kod": ...}. Varsayılan veriyle "complete"
        dönen eski (sessiz veri kaybı) yol KALDIRILDI.

    file_hash: Önceden hesaplanmışsa geçirilir, tekrar diskten okuma yapılmaz.
    process_id: Faz 3 PROCESS_CACHE için — verilirse UDF temp PDF silinmez (cache'e alınır).
    """

    # ⏱️ BENCHMARK: Zamanlama başlat
    benchmark = {}
    total_start = time.perf_counter()

    # 0. Hash — dışarıdan verilmişse hesaplama atlanır
    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    if file_hash is None:
        file_hash = await loop.run_in_executor(None, calculate_file_hash, file_path)
    benchmark["hash_calculation"] = round((time.perf_counter() - t0) * 1000, 2)

    # Note: Cache logic removed for clarity as it was disabled.

    if not GOOGLE_API_KEY:
        TechnicalLogger.log(
            "WARNING", "Skipping analysis because GEMINI_API_KEY is missing."
        )
        yield _failed_event(
            "Yapay zeka servisi yapılandırılmamış (API anahtarı tanımlı değil). "
            "Lütfen sistem yöneticisine bildirin."
        )
        return

    if not os.path.exists(file_path):
        TechnicalLogger.log("WARNING", f"File vanished before processing: {file_path}")
        yield _failed_event(
            "Dosya işlem sırasında bulunamadı (silinmiş veya taşınmış olabilir). "
            "Lütfen tekrar yükleyin."
        )
        return

    # 1. PDF olmayan formatlar (UDF/görüntü/Office) önce PDF'e çevrilir
    from pdf.format_converter import CONVERTIBLE_EXTENSIONS

    file_ext = Path(file_path).suffix.lower()
    temp_pdf_from_udf = None

    if file_ext == '.udf':
        udf_state = {
            "file_path": file_path, "temp_pdf_from_udf": None, "failed": False,
            "legacy_complete_on_error": False,
        }
        async for event in _step_udf_conversion(udf_state, file_hash, benchmark, loop):
            yield event
        file_path = udf_state["file_path"]
        temp_pdf_from_udf = udf_state["temp_pdf_from_udf"]
        if udf_state["failed"]:
            yield _failed_event(udf_state["error_ozet"])
            return
    elif file_ext in CONVERTIBLE_EXTENSIONS:
        conv_state = {
            "file_path": file_path, "temp_converted_pdf": None, "failed": False,
            "legacy_complete_on_error": False,
        }
        async for event in _step_format_conversion(conv_state, file_hash, benchmark, loop):
            yield event
        file_path = conv_state["file_path"]
        # Cleanup/cache sahipliği UDF temp PDF'iyle aynı yoldan yürür
        temp_pdf_from_udf = conv_state["temp_converted_pdf"]
        if conv_state["failed"]:
            yield _failed_event(conv_state["error_ozet"])
            return

    # 1.5. Page Trim — LLM'e sadece ilk 2 + son sayfa gönderilir
    full_pdf_path = file_path   # arşiv için tam PDF (Faz 3'te cache'e konacak)
    file_path, temp_trimmed_pdf = await _step_page_trim(file_path, benchmark, loop)

    # 2. Decide Mode (Async wrapper for heavy pdf logic)
    mode_state = {"needs_ocr": None, "extracted_text": None, "failed": False}
    async for event in _step_decide_mode(file_path, file_hash, mode_state, benchmark, loop):
        yield event
    if mode_state["failed"]:
        return
    needs_ocr = mode_state["needs_ocr"]
    extracted_text = mode_state["extracted_text"]

    ai_state = {"uploaded_file": None}
    try:
        # === PRE-EXTRACTION PHASE (Regex/List çıkarıcılar LLM'den önce) ===
        pre_extracted = {
            "tarih": None,
            "esas_no": None,
            "muvekkil_candidates": [],
            "court": None,
            "sonraki_durusma_tarihi": None,
            "sonraki_durusma_saati": None,
        }

        t2 = time.perf_counter()  # Pre-extraction timer start
        if extracted_text and len(extracted_text) > 50:
            yield {"status": "info", "message": "Analiz yapılıyor..."}
            _pre_extract_fields(pre_extracted, extracted_text, preset_belge_turu_kodu)

        # === MISSING FIELDS DETECTION ===
        missing_fields = _detect_missing_fields(pre_extracted)

        benchmark["pre_extraction"] = round((time.perf_counter() - t2) * 1000, 2)

        # Log what we found/missing
        TechnicalLogger.log("INFO", f"🎯 [PRE] Eksik alanlar: {missing_fields if missing_fields else 'YOK (Sadece özet istenecek)'}")

        gen_config, lawyers = _build_prompt_and_config(
            pre_extracted, missing_fields, preset_belge_turu_kodu, benchmark
        )


        # ⏱️ ai_call alt-metrikleri — darboğazın upload/wait/generate/retry'dan
        # hangisi olduğunu ayırmak için (lokal vs prod hız farkı teşhisi).
        ai_stats = {"retry_count": 0, "retry_wait_ms": 0}
        t3 = time.perf_counter()  # AI call timer start

        async for event in _step_ai_call(
            ai_state, gen_config, needs_ocr, extracted_text, file_path, benchmark, ai_stats
        ):
            yield event
        response = ai_state["response"]

        benchmark["retry_count"] = ai_stats["retry_count"]
        benchmark["retry_wait_ms"] = round(ai_stats["retry_wait_ms"], 2)
        benchmark["ai_call"] = round((time.perf_counter() - t3) * 1000, 2)

        # ⏱️ Token sayıları — generate_ms'in belge boyutuyla mı orantılı olduğunu
        # test etmek için (lokal-prod hız farkı: eşzamanlılık mı, belge boyutu mu?).
        _record_token_usage(response, benchmark)

        # Faz 3-C: finish_reason KOD bazlı okunur — MAX_TOKENS kesilmesi ve
        # boş yanıt artık "güvenlik filtresi" diye yanlış etiketlenmez; gerçek
        # filtre engeli finish/block_reason kanıtıyla GeminiBlockedError olur.
        result_text = _ensure_response_text(response)

        logging.info(f"GEMINI HAM CEVAP: {result_text}")

        # 3. Robust JSON Parsing (Brace Counting)
        data = _parse_gemini_json(result_text)

        # 4. Hash'i sonuca ekle
        data["hash"] = file_hash

        debug_info = []

        # 🛡️ Belge Türü + Karşı Taraf düzenlemesi
        _apply_preset_and_karsi_taraf(data, preset_belge_turu_kodu, debug_info)


        # === POST-PROCESSING: Pre-Extracted Değerleri Uygula ===
        # Artık regex'leri tekrar çalıştırmıyoruz, pre-extraction'daki sonuçları kullan
        _resolve_tarih_esas_court(data, pre_extracted, debug_info)

        # 👤 MÜVEKKİL (Hibrit Matcher hala gerekli)
        _resolve_muvekkil_fields(data, pre_extracted, lawyers, debug_info)

        # 📅 SONRAKI DURUŞMA TARİHİ + SAATİ — Regex öncelikli, AI fallback
        _apply_hearing_fields(data, pre_extracted, debug_info)

        # 🆕 DOSYA ADI ÖN İSİM FORMATLAMA (YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad)
        _apply_filename_format(data, debug_info)

        # Debug info artık özete eklenmez, sadece terminale loglanır
        TechnicalLogger.log("DEBUG", f"Post-processing: {debug_info}")

        # ⏱️ BENCHMARK: Toplam süreyi hesapla ve logla
        benchmark["total"] = round((time.perf_counter() - total_start) * 1000, 2)

        # Görünür çıktı için print kullanılıyordu, loglara ve _benchmark içine alındı.

        logging.info(f"⏱️ BENCHMARK: {benchmark}")

        # Ayrıca data içine de ekle ki frontend'de görülebilsin
        data["_benchmark"] = benchmark

        TechnicalLogger.log(
            "INFO",
            "Gemini Analysis Successful",
            {"file": file_path, "doc_type": data.get("belge_turu_kodu")},
        )
        yield {"status": "complete", "data": data, "full_pdf_path": full_pdf_path}

    # Handler zinciri (sıra korunur): her biri artık `failed` terminal olayı
    # üretir — log satırları ve teşhis mantığı aynen kalır.
    except FileNotFoundError:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"File not found: {file_path}")
        yield _failed_event(
            f"Dosya bulunamadı. Lütfen dosya yolunu kontrol edin. (Kod: {error_id})"
        )

    except PdfPageLimitError as e:
        # ValueError alt sınıfı — aşağıdaki handler "Güvenlik Filtresi" diye
        # yanlış teşhis koymasın, kullanıcı sayfa limitini görsün
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"PDF page limit exceeded: {e}")
        yield _failed_event(f"{e} (Kod: {error_id})")

    except json.JSONDecodeError as e:
        # ValueError alt sınıfı — bozuk LLM çıktısı güvenlik filtresi değildir
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Gemini JSON parse error [ErrorID: {error_id}]: {e}")
        yield _failed_event(
            f"Yapay zeka yanıtı çözümlenemedi (bozuk çıktı). Lütfen tekrar deneyin. (Kod: {error_id})"
        )

    except GeminiResponseError as e:
        # Faz 3-C: boş/kesik/engellenmiş yanıt — neden finish_reason'dan geliyor
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Gemini response error [ErrorID: {error_id}]: {e}")
        if isinstance(e, GeminiTruncatedError):
            ozet = (
                f"Yapay zeka yanıtı uzunluk sınırına takıldı ve kesildi (belge "
                f"çok yoğun olabilir). Lütfen tekrar deneyin. (Kod: {error_id})"
            )
            kod = "gemini_truncated"
        elif isinstance(e, GeminiBlockedError):
            ozet = (
                f"Yapay zeka yanıtı engellendi (Güvenlik/Gizlilik Filtresi). (Kod: {error_id})"
            )
            kod = "gemini_blocked"
        else:
            ozet = (
                f"Yapay zeka boş yanıt döndürdü. Lütfen tekrar deneyin. (Kod: {error_id})"
            )
            kod = "analysis_error"
        yield _failed_event(ozet, kod)

    except ValueError as e:
        # Faz 3-C: filtre engeli artık kanıtla (GeminiBlockedError) raporlanır;
        # buraya düşen ValueError'a güvenlik filtresi teşhisi KONMAZ.
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Gemini Value Error [ErrorID: {error_id}]: {e}")
        yield _failed_event(
            f"Yapay zeka yanıtı işlenemedi. Lütfen tekrar deneyin. (Kod: {error_id})"
        )

    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log(
            "ERROR",
            f"Gemini Analysis Failed for {file_path} [ErrorID: {error_id}]: {e}",
            {"trace": str(e)},
        )

        yield _failed_event(_api_error_ozet(e, error_id), _api_error_kod(e))
    finally:
        _cleanup_temp_files(
            ai_state["uploaded_file"], temp_pdf_from_udf, temp_trimmed_pdf, process_id
        )
