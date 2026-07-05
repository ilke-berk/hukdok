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
from managers.ttl_cache import TTLCache
from file_utils import safe_remove, sanitize_filename, normalize_date_for_sharepoint, get_doctype_label, ALLOWED_EXTENSIONS, validate_file_size, validate_file_type
import models
from services import document_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)

# Download cache: temp file paths keyed by UUID for frontend download (1h TTL safety net)
DOWNLOAD_CACHE = TTLCache(ttl_seconds=3600)

# Process cache: keeps full PDF alive between /process and /confirm (30 min TTL)
PROCESS_CACHE = TTLCache(ttl_seconds=1800)


def _cleanup_process_cache():
    """Remove PROCESS_CACHE entries older than TTL and delete their backing files."""
    def _evict(k, entry):
        safe_remove(entry.get("path"))
        logger.info(f"PROCESS_CACHE TTL expired: {k} → {entry.get('path')}")
    PROCESS_CACHE.cleanup_stale(on_evict=_evict)
    # Piggyback download cache cleanup on the same trigger.
    DOWNLOAD_CACHE.cleanup_stale(
        on_evict=lambda k, v: logger.info(f"DOWNLOAD_CACHE TTL expired: {k}")
    )

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

    sender_name = user.get("name") or user.get("preferred_username") or None
    body = generate_email_preview(recipient_name, context, sender_name=sender_name)
    return {"body": body}


@router.post("/preview-client-email-body")
async def preview_client_email_body(
    request: Request,
    client_name: str = Form("Müvekkil"),
    belge_turu_kodu: str = Form(None),
    tarih: str = Form(None),
    teblig_tarihi: str = Form(None),
    ai_ozet: str = Form(None),
    karsi_taraf: str = Form(None),
    sonraki_durusma_tarihi: str = Form(None),
    sonraki_durusma_saati: str = Form(None),
    user: dict = Depends(get_current_user),
):
    """Müvekkil bilgilendirme metni önizlemesi oluşturur (gönderim yapmaz).

    Metin, belgenin AI özetine (ai_ozet) dayanır; bu yüzden gelişmeyi anlatabilir.
    """
    from email_sender import generate_client_email_preview

    def format_date_tr(date_str: str) -> str:
        if not date_str:
            return ""
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return date_str

    teblig_tarihi_normalized = normalize_date_for_sharepoint(teblig_tarihi) if teblig_tarihi else None

    # Bir sonraki duruşma metnini birleştir (örn. "10/09/2026 saat 12:00").
    sonraki_durusma = ""
    if sonraki_durusma_tarihi:
        sonraki_durusma = format_date_tr(normalize_date_for_sharepoint(sonraki_durusma_tarihi) or sonraki_durusma_tarihi)
        if sonraki_durusma_saati:
            sonraki_durusma += f" saat {sonraki_durusma_saati}"

    context = {
        "belge_turu": get_doctype_label(belge_turu_kodu) or "Belge",
        "tarih_str": format_date_tr(tarih),
        "teblig_tarihi_str": format_date_tr(teblig_tarihi_normalized),
        "ozet": ai_ozet or "",
        "karsi_taraf": karsi_taraf or "",
        "sonraki_durusma": sonraki_durusma,
    }

    sender_name = user.get("name") or user.get("preferred_username") or None
    body = generate_client_email_preview(client_name, context, sender_name=sender_name)
    return {"body": body}


@router.post("/process")
async def analyze_file_endpoint(
    request: Request,
    file: UploadFile = File(...),
    belge_turu_kodu: Optional[str] = Form(None),
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
        logger.error(f"Dosya yükleme hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dosya yüklenemedi. Lütfen tekrar deneyin.")

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
            generator = analyze_file_generator(temp_path, file_hash=file_hash, process_id=process_id, preset_belge_turu_kodu=belge_turu_kodu or None)
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
                        PROCESS_CACHE.set(process_id, {
                            "path": full_pdf_path,
                            "original_ext": original_ext,
                        })
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
                            final_data.get("belgede_gecen_isimler", []),
                            final_data.get("court"),
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


def _download_owner_id(user: dict) -> str:
    raw = user.get("preferred_username") or user.get("upn") or user.get("email") or ""
    return raw.strip().lower()


@router.get("/api/download/{file_id}")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    file_info = DOWNLOAD_CACHE.get(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı veya süresi doldu.")

    requester = _download_owner_id(user)
    owner = (file_info.get("owner") or "").strip().lower()
    if not requester or not owner or requester != owner:
        # Mask existence to avoid leaking valid file_ids to non-owners.
        raise HTTPException(status_code=404, detail="Dosya bulunamadı veya süresi doldu.")

    file_path = file_info["path"]
    filename = file_info["filename"]

    if not os.path.exists(file_path):
        DOWNLOAD_CACHE.delete(file_id)
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
    send_client_notice: bool = Form(False),
    client_notice_message: str = Form(None),
    teblig_tarihi: str = Form(None),
    linked_case_id: Optional[int] = Form(None),
    case_party_id: Optional[int] = Form(None),
    is_test_mode: bool = Form(False),
    ai_ozet: str = Form(None),
    custom_email_message: str = Form(None),
    custom_messages_json: str = Form(None),
    extra_attachment_files: list[UploadFile] = File(default=[]),
    sonraki_durusma_tarihi: str = Form(None),
    sonraki_durusma_saati: str = Form(None),
    user: dict = Depends(get_current_user),
):
    """Step 2: Confirm Process - Rename, Upload to SharePoint, Link to Case"""
    import time as perf_time

    confirm_start = perf_time.perf_counter()
    timings = {}

    current_user_name = user.get("name") or user.get("preferred_username") or "Bilinmeyen"

    try:
        muvekkiller = json.loads(muvekkiller_json) if muvekkiller_json else []
        belgede_gecen_isimler = json.loads(belgede_gecen_isimler_json) if belgede_gecen_isimler_json else []
        custom_to = json.loads(custom_to_json) if custom_to_json else []
        custom_cc = json.loads(custom_cc_json) if custom_cc_json else []
        custom_messages = json.loads(custom_messages_json) if custom_messages_json else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in form fields")

    results = {}

    # IDOR-6: linked_case_id verildiyse önce tenant ownership doğrula.
    # Belge SharePoint'e gitmeden ve save_case_document çağrılmadan önce reddetmeliyiz.
    if linked_case_id:
        avukat_kodu = document_pipeline.validate_tenant_and_resolve_lawyer(linked_case_id, user, avukat_kodu)

    # Faz 3: Use PROCESS_CACHE if process_id provided; fall back to file upload
    temp_path = await document_pipeline.accept_incoming_file(process_id, file, PROCESS_CACHE)

    source_path = temp_path
    log_id = None
    muvekkil_kodu = None

    try:
        new_filename = sanitize_filename(new_filename)
    except HTTPException as e:
        TechnicalLogger.log("WARNING", f"Filename sanitization failed: {e.detail}")
        raise e

    background_tasks.add_task(document_pipeline.async_increment_counter)
    timings["1_counter"] = 0.00

    HAM_FOLDER = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
    ISLENMIS_FOLDER = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

    original_filename = (file.filename if file else None) or new_filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized_original = sanitize_filename(original_filename)
    ham_filename = f"{date_str}_{sanitized_original}"

    # Faz 4: ham upload is queued AFTER PDF/A succeeds so both archives are consistent
    pdfa_temp_file, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=background_tasks,
        source_path=source_path,
        ham_filename=ham_filename,
        ham_folder=HAM_FOLDER,
        islenmis_folder=ISLENMIS_FOLDER,
        new_filename=new_filename,
        original_filename=original_filename,
        belge_turu_kodu=belge_turu_kodu,
        muvekkiller=muvekkiller,
        muvekkil_adi=muvekkil_adi,
        ai_ozet=ai_ozet,
        linked_case_id=linked_case_id,
        case_party_id=case_party_id,
        avukat_kodu=avukat_kodu,
        esas_no=esas_no,
        is_test_mode=is_test_mode,
        user=user,
        current_user_name=current_user_name,
        results=results,
        timings=timings,
    )

    final_local_path = pdfa_temp_file if (pdfa_temp_file and os.path.exists(pdfa_temp_file)) else source_path
    timings["4_local_save"] = 0.00
    results["local_save"] = "Atlandı (Web Mode)"
    results["final_path"] = None

    timings["5_logging"] = 0.00

    # Extra ekleri temp dosyaya kaydet
    extra_temp_paths = await document_pipeline.save_extra_attachments(extra_attachment_files)

    avukat_adi = document_pipeline.resolve_lawyer_name(avukat_kodu)

    email_metadata = document_pipeline.build_email_metadata(
        muvekkiller, muvekkil_adi, muvekkil_kodu, belge_turu_kodu, tarih, avukat_adi, teblig_tarihi
    )

    email_file_path = final_local_path

    if send_email:
        await document_pipeline.send_notification_email(
            email_file_path=email_file_path,
            new_filename=new_filename,
            avukat_kodu=avukat_kodu,
            email_metadata=email_metadata,
            custom_to=custom_to,
            custom_cc=custom_cc,
            custom_email_message=custom_email_message,
            custom_messages=custom_messages,
            extra_temp_paths=extra_temp_paths,
            current_user_name=current_user_name,
            doc_id=doc_id,
            results=results,
            timings=timings,
        )
    else:
        results["email"] = "Kullanıcı tarafından atlandı"
        results["email_warning"] = None
        results["email_success"] = None

    # --- MÜVEKKİL BİLGİLENDİRME (SORUMLU AVUKATA) ---
    # Müvekkil bilgilendirme metni müvekkile DEĞİL, davanın sorumlu avukatına
    # "[Müvekkil Bilgilendirme]" konu başlığıyla, AYRI bir e-posta olarak gönderilir.
    # Avukat metni gözden geçirip müvekkiline iletir.
    # Şimdilik tüm belge türlerinde gönderilir; should_notify_client ileride sınırlayacak.
    from email_sender import should_notify_client
    if (
        send_email
        and send_client_notice
        and should_notify_client(belge_turu_kodu)
        and email_file_path and os.path.exists(email_file_path)
    ):
        await document_pipeline.send_client_notice_email(
            email_file_path=email_file_path,
            new_filename=new_filename,
            avukat_kodu=avukat_kodu,
            avukat_adi=avukat_adi,
            email_metadata=email_metadata,
            client_notice_message=client_notice_message,
            current_user_name=current_user_name,
            results=results,
            timings=timings,
        )
    else:
        results["client_notice"] = "Atlandı"
        results["client_notice_success"] = None

    download_id = None
    if email_file_path and os.path.exists(email_file_path):
        download_id = str(uuid.uuid4())
        DOWNLOAD_CACHE.set(download_id, {
            "path": email_file_path,
            "filename": new_filename,
            "owner": _download_owner_id(user),
        })
        results["download_id"] = download_id

    # Her iki temp dosyayı da temizle (source_path her zaman; pdfa farklıysa o da)
    document_pipeline.schedule_cleanup(background_tasks, source_path, pdfa_temp_file, download_id, DOWNLOAD_CACHE)

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

        # Duruşma/tensip zaptından gelen sonraki duruşma tarihini ajandaya kaydet
        document_pipeline.save_hearing_date(
            linked_case_id=linked_case_id,
            belge_turu_kodu=belge_turu_kodu,
            sonraki_durusma_tarihi=sonraki_durusma_tarihi,
            sonraki_durusma_saati=sonraki_durusma_saati,
            avukat_adi=avukat_adi,
            new_filename=new_filename,
            current_user_name=current_user_name,
            results=results,
        )
    else:
        results["auto_status_update"] = False
        results["auto_enrichment"] = {}
        results["hearing_date_saved"] = None

    total_time = perf_time.perf_counter() - confirm_start
    timings["TOTAL"] = total_time

    return {"status": "completed", "results": results, "timings": timings}
