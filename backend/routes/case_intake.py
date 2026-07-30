"""Otonom dava açma — case intake route'ları (Faz 2).

POST /api/case-intake/analyze: tek belge alır, intake çıkarım motorunu
(case_intake_analyzer) koşturur ve /process ile aynı şekilli NDJSON stream
döner. Terminal olay:

    {"status": "complete", "process_id": "<uuid>",
     "data": {...CaseIntakeExtraction..., "belge_turu_kodu_tahmini": "...",
              "agreement": {alan: skor}, "verification": {...}}}

Tam PDF, /process ile aynı hijyenle PROCESS_CACHE'e konur — Faz 4 commit
adımı belgeyi process_id ile oradan alacak.
"""
import hashlib
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from dependencies import get_current_user
from file_utils import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    safe_remove,
    validate_file_type,
)
from managers.log_manager import TechnicalLogger
from routes.processing import PROCESS_CACHE, _cleanup_process_cache

router = APIRouter()
logger = logging.getLogger(__name__)


def resolve_upload_suffix(filename: Optional[str]) -> str:
    """Uzantı çözümü. UYAP UDF'leri bazen '.udf.zip' adıyla gelir (UDF zaten
    bir zip arşividir) — bunlar '.udf' olarak işlenir; beyaz liste değişmez."""
    name = (filename or "").lower()
    if name.endswith(".udf.zip"):
        return ".udf"
    return Path(name).suffix


@router.post("/api/case-intake/analyze")
async def analyze_case_intake_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Dava açılış belgesini analiz eder (NDJSON stream)."""
    from case_intake_analyzer import analyze_intake_file_generator

    suffix = resolve_upload_suffix(file.filename)
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"İzin verilmeyen dosya uzantısı: {suffix or '(yok)'}")

    temp_path = None
    try:
        sha256 = hashlib.sha256()
        total_bytes = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            temp_path = tmp_file.name
            while chunk := await file.read(65536):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"Dosya çok büyük. Maksimum {MAX_UPLOAD_MB}MB.")
                sha256.update(chunk)
                tmp_file.write(chunk)
        file_hash = sha256.hexdigest()
        TechnicalLogger.log(
            "INFO",
            f"[INTAKE] Temp file created: {temp_path} ({total_bytes} bytes, hash: {file_hash[:8]}...)",
        )
        validate_file_type(temp_path)
    except HTTPException:
        safe_remove(temp_path)
        raise
    except Exception as e:
        safe_remove(temp_path)
        logger.error(f"[INTAKE] Dosya yükleme hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dosya yüklenemedi. Lütfen tekrar deneyin.") from e

    _cleanup_process_cache()
    process_id = str(uuid.uuid4())

    async def event_stream():
        cached_full_pdf_path = None
        try:
            generator = analyze_intake_file_generator(
                temp_path, file_hash=file_hash, process_id=process_id
            )
            async for step in generator:
                if step["status"] == "complete":
                    # Tam PDF'i /process hijyeniyle cache'le: dönüştürülmüş
                    # formatlarda (UDF/görüntü/Office) orijinal dosya da saklanır —
                    # commit adımında HAM arşive orijinal gider.
                    full_pdf_path = step.pop("full_pdf_path", None)
                    if full_pdf_path:
                        cached_full_pdf_path = full_pdf_path
                        original_path = temp_path if full_pdf_path != temp_path else None
                        PROCESS_CACHE.set(process_id, {
                            "path": full_pdf_path,
                            "original_path": original_path,
                            "original_ext": suffix,
                        })
                        TechnicalLogger.log(
                            "INFO",
                            f"[INTAKE] PROCESS_CACHE stored: {process_id} → {full_pdf_path} (original: {original_path})",
                        )
                    step["process_id"] = process_id
                yield json.dumps(step, ensure_ascii=False, default=str) + "\n"
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log("ERROR", f"[INTAKE] Streaming Error [ID: {error_id}]: {e}")
            yield json.dumps(
                {"status": "error", "message": f"Beklenmedik hata: {str(e)}"}, ensure_ascii=False
            ) + "\n"
        finally:
            # temp_path cache'e girdiyse (analiz PDF'i veya orijinal olarak)
            # silinmez — PROCESS_CACHE TTL temizliği sahiplenir.
            if cached_full_pdf_path:
                TechnicalLogger.log(
                    "INFO", f"[INTAKE] Temp dosya cache'te bırakıldı: {temp_path}"
                )
            else:
                if safe_remove(temp_path, retries=3):
                    TechnicalLogger.log("INFO", f"[INTAKE] Temp analiz dosyası silindi: {temp_path}")
                else:
                    TechnicalLogger.log("WARNING", f"[INTAKE] Temp dosya silinemedi: {temp_path}")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
