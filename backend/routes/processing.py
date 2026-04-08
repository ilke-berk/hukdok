import os
import asyncio
import hashlib
import json
import logging
import time
import uuid
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import StreamingResponse, FileResponse

from dependencies import get_current_user
from database import SessionLocal
from managers.config_manager import DynamicConfig
from managers.log_manager import TechnicalLogger
from file_utils import safe_remove, sanitize_filename, normalize_date_for_sharepoint, get_doctype_label, ALLOWED_EXTENSIONS, validate_file_size, validate_file_type
import models

router = APIRouter()
logger = logging.getLogger(__name__)

# Download cache: stores temp file paths keyed by UUID for frontend download
DOWNLOAD_CACHE: dict = {}

# Process cache: keeps full PDF alive between /process and /confirm (Faz 3)
PROCESS_CACHE: dict = {}  # process_id → {path, original_ext, ts}


def _cleanup_process_cache():
    """Remove PROCESS_CACHE entries older than 30 minutes and delete their files."""
    cutoff = time.time() - 1800  # 30 min
    stale = [k for k, v in list(PROCESS_CACHE.items()) if v["ts"] < cutoff]
    for k in stale:
        entry = PROCESS_CACHE.pop(k, None)
        if entry:
            safe_remove(entry["path"])
            logger.info(f"PROCESS_CACHE TTL expired: {k} → {entry['path']}")

# Document type → case status auto-mapping
DOCTYPE_TO_STATUS_MAP = {
    "KARAR": "KARAR",
    "TEMYIZ": "TEMYIZ",
    "INFAZ": "INFAZ",
    "FERAGAT": "KAPALI",
    "ISLAH": "DERDEST",
}
DTYPE_TO_STATUS_MAP_ITEMS = list(DOCTYPE_TO_STATUS_MAP.items())


def refresh_lists_background():
    """Background Task: Updates Singleton Config from Database."""
    logging.info("Background: Loading lists from Database...")
    try:
        from managers.admin_manager import get_lawyers, get_statuses, get_doctypes, get_email_recipients, get_case_subjects
        from managers import cache_manager as _cache_manager

        new_lawyers = get_lawyers()
        new_statuses = get_statuses()
        new_doctypes = get_doctypes()
        new_recipients = get_email_recipients()
        new_subjects = get_case_subjects()

        config = DynamicConfig.get_instance()
        updated = False

        if new_subjects:
            config.set_case_subjects(new_subjects)
            updated = True
        if new_lawyers:
            config.set_lawyers(new_lawyers)
            updated = True
        if new_statuses:
            config.set_statuses(new_statuses)
            updated = True
        if new_doctypes:
            config.set_doctypes(new_doctypes)
            updated = True
        if new_recipients:
            config.set_email_recipients(new_recipients)
            updated = True

        if updated and _cache_manager:
            full_data = {
                "lawyers": config.get_lawyers(),
                "statuses": config.get_statuses(),
                "doctypes": config.get_doctypes(),
                "case_subjects": config.get_case_subjects(),
                "email_recipients": config.get_email_recipients(),
                "last_updated": datetime.now().isoformat(),
            }
            _cache_manager.save_cache(full_data)

        from muvekkil_matcher_v2 import yenile_matcher
        yenile_matcher()
        from list_searcher import get_list_searcher
        get_list_searcher()._load_data()
        logging.info("Matcher and Searcher refreshed from DB.")

    except Exception as e:
        logging.error(f"Background Update Failed: {e}")


def _save_case_document(
    case_id,
    original_filename: str,
    stored_filename: str,
    belge_turu_kodu: str = None,
    belge_turu_adi: str = None,
    ai_summary: str = None,
    muvekkil_adi: str = None,
    avukat_kodu: str = None,
    esas_no: str = None,
    is_test_mode: bool = False,
    uploaded_by: str = None,
):
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
            uploaded_by=uploaded_by,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        db.close()
        logging.info(f"CaseDocument saved: ID={doc_id}, mode={link_mode}, case_id={case_id}")
        return doc_id
    except Exception as e:
        logging.error(f"CaseDocument save error: {e}")
        return None


def _auto_update_case_status(case_id: int, belge_turu_kodu: str, uploaded_by: str = None):
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
            history = models.CaseHistory(
                case_id=case_id,
                field_name="status",
                old_value=old_status,
                new_value=new_status,
            )
            db.add(history)
            db.commit()
            logging.info(f"Case {case_id} status auto-updated: {old_status} → {new_status}")
            db.close()
            return True

        db.close()
        return False
    except Exception as e:
        logging.error(f"Auto status update error: {e}")
        return False


def _auto_enrich_case_data(case_id: int, avukat_kodu: str = None, karsi_taraf: str = None, uploaded_by: str = None):
    if not case_id:
        return {}

    updated_fields = {}
    try:
        db = SessionLocal()
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            return {}

        if avukat_kodu and (
            not case.responsible_lawyer_name
            or case.responsible_lawyer_name == "Atanmadı"
            or case.responsible_lawyer_name.strip() == ""
        ):
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
                            new_value=avukat_adi,
                        )
                        db.add(history)
                        updated_fields["lawyer"] = avukat_adi
                        break
            except Exception as e:
                logging.warning(f"Avukat lookup error (Enrichment): {e}")

        if karsi_taraf:
            has_counter = any(p.party_type == "COUNTER" for p in case.parties)
            if not has_counter:
                new_party = models.CaseParty(
                    case_id=case_id, name=karsi_taraf, role="Karşı Taraf", party_type="COUNTER"
                )
                db.add(new_party)
                history = models.CaseHistory(
                    case_id=case_id,
                    field_name="karşı_taraf",
                    old_value="Yok",
                    new_value=karsi_taraf,
                )
                db.add(history)
                updated_fields["counter_party"] = karsi_taraf

        if updated_fields:
            db.commit()

        return updated_fields
    except Exception as e:
        logging.error(f"Auto-Enrich error: {e}")
        return {}
    finally:
        db.close()


@router.post("/refresh")
@router.post("/api/refresh")
@router.post("/api/config/refresh")
async def refresh_config_endpoint(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    background_tasks.add_task(refresh_lists_background)
    return {"status": "refresh_started", "message": "Listeler arka planda güncelleniyor..."}


@router.post("/preview-email-body")
async def preview_email_body(
    request: Request,
    recipient_name: str = Form("İlgili"),
    muvekkil_adi: str = Form(None),
    muvekkiller_json: str = Form(None),
    belge_turu_kodu: str = Form(None),
    tarih: str = Form(None),
    teblig_tarihi: str = Form(None),
    user: dict = Depends(get_current_user),
):
    """E-posta AI mesajı önizlemesi oluşturur (gönderim yapmaz)."""
    from email_sender import generate_email_preview

    try:
        muvekkiller = json.loads(muvekkiller_json) if muvekkiller_json else []
    except Exception:
        muvekkiller = []

    muvekkil_text = muvekkil_adi or (muvekkiller[0] if muvekkiller else "Müvekkil")

    def format_date_tr(date_str: str) -> str:
        if not date_str:
            return ""
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return date_str

    teblig_tarihi_normalized = normalize_date_for_sharepoint(teblig_tarihi) if teblig_tarihi else None

    context = {
        "muvekkil_text": f"{muvekkil_text} isimli müvekkilin",
        "belge_turu": get_doctype_label(belge_turu_kodu) or "Belge",
        "tarih_str": format_date_tr(tarih),
        "teblig_tarihi_str": format_date_tr(teblig_tarihi_normalized),
    }

    body = generate_email_preview(recipient_name, context)
    return {"body": body}


@router.post("/process")
async def analyze_file_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Step 1: Analyze File (Stream)"""
    from analyzer import analyze_file_generator
    from managers.counter_manager import get_counter_manager

    api_start = time.perf_counter()
    api_timings = {}

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"İzin verilmeyen dosya uzantısı: {suffix}")

    temp_path = None
    try:
        sha256 = hashlib.sha256()
        total_bytes = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            temp_path = tmp_file.name
            while chunk := await file.read(65536):
                total_bytes += len(chunk)
                if total_bytes > validate_file_size.MAX_BYTES:
                    raise HTTPException(status_code=413, detail=f"Dosya çok büyük. Maksimum {validate_file_size.MAX_MB}MB.")
                sha256.update(chunk)
                tmp_file.write(chunk)
        file_hash = sha256.hexdigest()
        TechnicalLogger.log("INFO", f"Temp file created: {temp_path} ({total_bytes} bytes, hash: {file_hash[:8]}...)")
        validate_file_type(temp_path)
    except HTTPException:
        safe_remove(temp_path)
        raise
    except Exception as e:
        safe_remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Dosya yükleme hatası: {str(e)}")

    # Faz 3: cleanup stale cache entries on each /process call
    _cleanup_process_cache()
    process_id = str(uuid.uuid4())

    async def event_stream():
        cached_full_pdf_path = None
        try:
            async def fetch_counter():
                try:
                    loop = asyncio.get_running_loop()
                    counter = get_counter_manager()
                    ofis_dosya_no = await asyncio.wait_for(
                        loop.run_in_executor(None, counter.get_next_counter),
                        timeout=10.0,
                    )
                    return ofis_dosya_no
                except asyncio.TimeoutError:
                    TechnicalLogger.log("ERROR", "SharePoint counter timeout (10s)")
                    return "TIMEOUT___"
                except Exception as e:
                    TechnicalLogger.log("ERROR", f"SharePoint counter error: {e}")
                    return "XXXXXXXXX"

            t2 = time.perf_counter()
            counter_task = asyncio.create_task(fetch_counter())

            t1 = time.perf_counter()
            generator = analyze_file_generator(temp_path, file_hash=file_hash, process_id=process_id)
            final_data = None

            async for step in generator:
                if step["status"] == "complete":
                    api_timings["analyzer"] = round((time.perf_counter() - t1) * 1000, 2)
                    final_data = step.get("data", {})

                    # Faz 3: cache full PDF path
                    full_pdf_path = step.pop("full_pdf_path", None)
                    if full_pdf_path:
                        cached_full_pdf_path = full_pdf_path
                        original_ext = Path(full_pdf_path).suffix.lower()
                        PROCESS_CACHE[process_id] = {
                            "path": full_pdf_path,
                            "original_ext": original_ext,
                            "ts": time.time(),
                        }
                        TechnicalLogger.log("INFO", f"PROCESS_CACHE stored: {process_id} → {full_pdf_path}")

                    if final_data and "ofis_dosya_no" not in final_data:
                        ofis_dosya_no = await counter_task
                        final_data["ofis_dosya_no"] = ofis_dosya_no
                    else:
                        try:
                            _ = await counter_task
                        except Exception:
                            pass

                    api_timings["counter_fetch"] = round((time.perf_counter() - t2) * 1000, 2)

                    try:
                        t_match = time.perf_counter()
                        from case_matcher import find_matching_case

                        matching_muvekkiller = list(final_data.get("muvekkiller") or [])
                        if final_data.get("muvekkil_adi"):
                            matching_muvekkiller.append(final_data.get("muvekkil_adi"))

                        match_result = await asyncio.get_running_loop().run_in_executor(
                            None,
                            find_matching_case,
                            final_data.get("esas_no"),
                            list(set(matching_muvekkiller)),
                            final_data.get("avukat_kodu"),
                            final_data.get("belgede_gecen_isimler", []),
                        )

                        final_data["suggested_case"] = match_result
                        api_timings["case_match"] = round((time.perf_counter() - t_match) * 1000, 2)
                    except Exception as match_err:
                        TechnicalLogger.log("WARNING", f"CaseMatcher error (skipped): {match_err}")
                        final_data["suggested_case"] = None

                    api_timings["total"] = round((time.perf_counter() - api_start) * 1000, 2)
                    final_data["_api_benchmark"] = api_timings
                    step["data"] = final_data
                    step["process_id"] = process_id

                yield json.dumps(step) + "\n"

        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log("ERROR", f"Streaming Error [ID: {error_id}]: {e}")
            yield json.dumps({"status": "error", "message": f"Beklenmedik hata: {str(e)}"}) + "\n"
        finally:
            # Faz 3: if temp_path was cached, don't delete it — PROCESS_CACHE TTL handles cleanup.
            # For UDF files, temp_path is the original UDF (not the cached PDF), so always delete it.
            if cached_full_pdf_path and cached_full_pdf_path == temp_path:
                TechnicalLogger.log("INFO", f"Skipping temp file deletion (in PROCESS_CACHE): {temp_path}")
            else:
                if safe_remove(temp_path, retries=3):
                    TechnicalLogger.log("INFO", f"Deleted temp analysis file: {temp_path}")
                else:
                    TechnicalLogger.log("WARNING", f"Failed to delete temp file: {temp_path}")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/api/download/{file_id}")
async def download_file(file_id: str):
    if file_id not in DOWNLOAD_CACHE:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı veya süresi doldu.")

    file_info = DOWNLOAD_CACHE[file_id]
    file_path = file_info["path"]
    filename = file_info["filename"]

    if not os.path.exists(file_path):
        del DOWNLOAD_CACHE[file_id]
        raise HTTPException(status_code=404, detail="Dosya diskte bulunamadı.")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")


@router.post("/confirm")
async def confirm_process(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    new_filename: str = Form(...),
    process_id: Optional[str] = Form(None),
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
    linked_case_id: Optional[int] = Form(None),
    is_test_mode: bool = Form(False),
    ai_ozet: str = Form(None),
    custom_email_message: str = Form(None),
    extra_attachment_files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    """Step 2: Confirm Process - Rename, Upload to SharePoint, Link to Case"""
    from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
    from managers.counter_manager import get_counter_manager
    from managers.log_manager import LogManager

    import time as perf_time

    confirm_start = perf_time.perf_counter()
    timings = {}

    current_user_name = user.get("name") or user.get("preferred_username") or "Bilinmeyen"

    try:
        muvekkiller = json.loads(muvekkiller_json) if muvekkiller_json else []
        belgede_gecen_isimler = json.loads(belgede_gecen_isimler_json) if belgede_gecen_isimler_json else []
        custom_to = json.loads(custom_to_json) if custom_to_json else []
        custom_cc = json.loads(custom_cc_json) if custom_cc_json else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in form fields")

    results = {}

    # Auto-lookup lawyer code from case if not provided
    if not avukat_kodu and linked_case_id:
        db_fetch = SessionLocal()
        try:
            case_fetch = db_fetch.query(models.Case).filter(models.Case.id == linked_case_id).first()
            if case_fetch and case_fetch.responsible_lawyer_name:
                lawyers = DynamicConfig.get_instance().get_lawyers()
                for l in lawyers:
                    if l.get("name") == case_fetch.responsible_lawyer_name:
                        avukat_kodu = l.get("code")
                        break
        except Exception as e:
            logging.warning(f"Avukat lookup error (Confirm): {e}")
        finally:
            db_fetch.close()

    # Faz 3: Use PROCESS_CACHE if process_id provided; fall back to file upload
    temp_path = None
    _from_cache = False

    if process_id and process_id in PROCESS_CACHE:
        cache_entry = PROCESS_CACHE.pop(process_id)
        cached_path = cache_entry["path"]
        if os.path.exists(cached_path):
            temp_path = cached_path
            suffix = cache_entry.get("original_ext", ".pdf")
            _from_cache = True
            TechnicalLogger.log("INFO", f"PROCESS_CACHE hit: {process_id} → {cached_path}")
        else:
            TechnicalLogger.log("WARNING", f"PROCESS_CACHE path missing on disk: {cached_path}")

    if not _from_cache:
        if not file:
            raise HTTPException(status_code=400, detail="Dosya veya geçerli bir process_id gereklidir.")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"İzin verilmeyen dosya uzantısı: {suffix}")
        try:
            total_bytes = 0
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                temp_path = tmp_file.name
                while chunk := await file.read(65536):
                    total_bytes += len(chunk)
                    if total_bytes > validate_file_size.MAX_BYTES:
                        raise HTTPException(status_code=413, detail=f"Dosya çok büyük. Maksimum {validate_file_size.MAX_MB}MB.")
                    tmp_file.write(chunk)
            TechnicalLogger.log("INFO", f"Temp file created for upload: {temp_path} ({total_bytes} bytes)")
            validate_file_type(temp_path)
        except HTTPException:
            safe_remove(temp_path)
            raise
        except Exception as e:
            safe_remove(temp_path)
            raise HTTPException(status_code=500, detail=f"Failed to save temp file: {e}")

    source_path = temp_path
    log_id = None
    muvekkil_kodu = None

    try:
        new_filename = sanitize_filename(new_filename)
    except HTTPException as e:
        TechnicalLogger.log("WARNING", f"Filename sanitization failed: {e.detail}")
        raise e

    def _async_increment():
        try:
            counter = get_counter_manager()
            counter.increment_counter()
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Async Counter Error: {e}")

    background_tasks.add_task(_async_increment)
    timings["1_counter"] = 0.00

    HAM_FOLDER = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
    ISLENMIS_FOLDER = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

    original_filename = (file.filename if file else None) or new_filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized_original = sanitize_filename(original_filename)
    ham_filename = f"{date_str}_{sanitized_original}"

    def _async_ham_upload():
        try:
            upload_file_to_sharepoint(source_path, ham_filename, HAM_FOLDER, use_date_subfolder=False)
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log("ERROR", f"Async Ham Upload Error [ID: {error_id}]: {e}")

    # Faz 4: ham upload is queued AFTER PDF/A succeeds so both archives are consistent
    pdfa_temp_file = None
    try:
        from pdf.pdf_converter import convert_to_pdfa2b

        step_start = perf_time.perf_counter()
        pdfa_temp_file = convert_to_pdfa2b(source_path)
        timings["3a_pdfa_convert"] = perf_time.perf_counter() - step_start

        if pdfa_temp_file and os.path.exists(pdfa_temp_file):
            # Create the database record before adding background tasks so we have doc_id
            belge_turu_label = get_doctype_label(belge_turu_kodu) if belge_turu_kodu else None
            clean_muvekkil = (muvekkiller[0] if muvekkiller else None) or muvekkil_adi

            doc_id = _save_case_document(
                case_id=linked_case_id,
                original_filename=original_filename,
                stored_filename=new_filename,
                belge_turu_kodu=belge_turu_kodu,
                belge_turu_adi=belge_turu_label,
                ai_summary=ai_ozet,
                muvekkil_adi=clean_muvekkil,
                avukat_kodu=avukat_kodu,
                esas_no=esas_no,
                is_test_mode=is_test_mode,
                uploaded_by=current_user_name,
            )
            results["case_document_id"] = doc_id

            def _async_islenmis_upload(temp_file_path, doc_id_to_update=None):
                try:
                    response_data = upload_file_to_sharepoint(
                        temp_file_path,
                        new_filename,
                        ISLENMIS_FOLDER,
                        use_date_subfolder=False,
                    )
                    
                    # Update database with SharePoint URL upon successful upload
                    if doc_id_to_update and response_data and "webUrl" in response_data:
                        try:
                            db_upd = SessionLocal()
                            doc_rec = db_upd.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id_to_update).first()
                            if doc_rec:
                                doc_rec.sharepoint_url = response_data["webUrl"]
                                db_upd.commit()
                                logging.info(f"✅ SharePoint URL updated for Doc ID {doc_id_to_update}: {response_data['webUrl']}")
                        except Exception as db_err:
                            logging.error(f"Failed to update SharePoint URL in DB for Doc ID {doc_id_to_update}: {db_err}")
                        finally:
                            db_upd.close()
                            
                except Exception as e:
                    error_id = str(uuid.uuid4())[:8]
                    TechnicalLogger.log("ERROR", f"Async Processed Upload Error [ID: {error_id}]: {e}")

            # Both archives queued together only after successful PDF/A conversion
            background_tasks.add_task(_async_ham_upload)
            background_tasks.add_task(_async_islenmis_upload, pdfa_temp_file, doc_id)
            timings["2_ham_upload"] = 0.00
            timings["3b_gizli_upload"] = 0.00
            results["sharepoint_ham"] = f"Arka Plana Atıldı ({ham_filename})"
            results["sharepoint_islenmis"] = "Arka Plana Atıldı (PDF/A-2b)"
        else:
            raise Exception("PDF/A-2b dönüşümü başarısız - dosya oluşturulamadı")

    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Processed Upload Error [ID: {error_id}]: {e}")
        raise HTTPException(status_code=500, detail=f"SharePoint arşiv yüklemesi başarısız. (Hata: {error_id})")

    final_local_path = pdfa_temp_file if (pdfa_temp_file and os.path.exists(pdfa_temp_file)) else source_path
    timings["4_local_save"] = 0.00
    results["local_save"] = "Atlandı (Web Mode)"
    results["final_path"] = None

    timings["5_logging"] = 0.00

    # Extra ekleri temp dosyaya kaydet
    extra_temp_paths = []
    for extra_file in extra_attachment_files:
        if extra_file and extra_file.filename:
            try:
                extra_suffix = Path(extra_file.filename).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=extra_suffix) as etmp:
                    etmp.write(await extra_file.read())
                    extra_temp_paths.append(etmp.name)
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Extra attachment save error: {e}")

    def _async_send_email(pdf_path, filename, avukat_kodu, email_metadata, to_list, cc_list, msg=None, extra_paths=None):
        try:
            from email_sender import send_document_notification
            result = send_document_notification(
                avukat_kodu=avukat_kodu,
                filename=filename,
                pdf_path=pdf_path,
                metadata=email_metadata,
                custom_to=to_list,
                custom_cc=cc_list,
                custom_message=msg,
                extra_attachment_paths=extra_paths,
            )
            if not result["success"]:
                logging.warning(f"E-posta gönderilemedi: {result['message']}")
        except Exception as e:
            TechnicalLogger.log("ERROR", f"Async Email Error: {e}")
        finally:
            # Extra temp dosyalarını temizle
            if extra_paths:
                for ep in extra_paths:
                    safe_remove(ep)

    avukat_adi = ""
    if avukat_kodu:
        try:
            lawyers = DynamicConfig.get_instance().get_lawyers()
            for lawyer in lawyers:
                if lawyer.get("code") == avukat_kodu:
                    avukat_adi = lawyer.get("name", "")
                    break
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Avukat name lookup error: {e}")

    clean_client_name = (muvekkiller[0] if muvekkiller else None) or muvekkil_adi

    email_metadata = {
        "muvekkil_adi": clean_client_name or muvekkil_kodu or "Bilinmeyen Müvekkil",
        "muvekkiller": muvekkiller or [],
        "belge_turu": get_doctype_label(belge_turu_kodu) or "Belge",
        "tarih": tarih or "",
        "avukat_adi": avukat_adi,
        "teblig_tarihi": normalize_date_for_sharepoint(teblig_tarihi) if teblig_tarihi else None,
    }

    email_file_path = final_local_path

    if send_email and email_file_path and os.path.exists(email_file_path):
        background_tasks.add_task(
            _async_send_email, email_file_path, new_filename, avukat_kodu, email_metadata, custom_to, custom_cc,
            custom_email_message or None, extra_temp_paths or None
        )
        timings["7_email"] = 0.00
        results["email"] = "Arka Plana Atıldı"
    elif not send_email:
        results["email"] = "Kullanıcı tarafından atlandı"
    else:
        results["email"] = "Dosya bulunamadı"

    download_id = None
    if email_file_path and os.path.exists(email_file_path):
        download_id = str(uuid.uuid4())
        DOWNLOAD_CACHE[download_id] = {
            "path": email_file_path,
            "filename": new_filename,
            "timestamp": perf_time.time(),
        }
        results["download_id"] = download_id

    def _async_cleanup(temp_path, down_id=None):
        import time as t
        t.sleep(30)
        if safe_remove(temp_path, retries=5):
            logging.info(f"Cleanup: Temp file deleted: {temp_path}")
        else:
            logging.warning(f"Cleanup: Could not delete: {temp_path}")
        if down_id and down_id in DOWNLOAD_CACHE:
            del DOWNLOAD_CACHE[down_id]

    # Her iki temp dosyayı da temizle (source_path her zaman; pdfa farklıysa o da)
    background_tasks.add_task(_async_cleanup, source_path)
    if pdfa_temp_file and pdfa_temp_file != source_path:
        background_tasks.add_task(_async_cleanup, pdfa_temp_file, download_id)

    results["link_mode"] = "TEST" if is_test_mode else ("LINKED" if linked_case_id else "UNLINKED")

    if linked_case_id and not is_test_mode:
        if belge_turu_kodu:
            results["auto_status_update"] = _auto_update_case_status(
                linked_case_id, belge_turu_kodu, current_user_name
            )
        else:
            results["auto_status_update"] = False

        results["auto_enrichment"] = _auto_enrich_case_data(
            linked_case_id, avukat_kodu, karsi_taraf, current_user_name
        )
    else:
        results["auto_status_update"] = False
        results["auto_enrichment"] = {}

    total_time = perf_time.perf_counter() - confirm_start
    timings["TOTAL"] = total_time

    return {"status": "completed", "results": results, "timings": timings}
