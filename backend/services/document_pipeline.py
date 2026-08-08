"""Belge onay hattı (/confirm) adım fonksiyonları.

routes/processing.py içindeki /confirm endpoint'i bu modüldeki adımları
aynı sırayla çağıran ince bir orkestratördür. Fonksiyonlar endpoint'teki
davranışı birebir korur; endpoint yereli olan değişkenler açık parametre
olarak geçirilir (results/timings sözlükleri yerinde mutasyona uğratılır).
"""
import os
import asyncio
import logging
import tempfile
import uuid
import time as perf_time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, BackgroundTasks, UploadFile

from database import SessionLocal
from managers.config_manager import DynamicConfig
from managers.log_manager import TechnicalLogger
from file_utils import safe_remove, normalize_date_for_sharepoint, get_doctype_label, ALLOWED_EXTENSIONS, validate_file_type, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
import models

logger = logging.getLogger(__name__)


def save_case_document(
    case_id,
    original_filename: str,
    stored_filename: str,
    belge_turu_kodu: str = None,
    belge_turu_adi: str = None,
    ai_summary: str = None,
    muvekkil_adi: str = None,
    case_party_id: int = None,
    avukat_kodu: str = None,
    esas_no: str = None,
    is_test_mode: bool = False,
    uploaded_by: str = None,
    uploaded_by_email: str = None,
):
    db = None
    try:
        db = SessionLocal()
        if case_id:
            link_mode = "LINKED"
        elif is_test_mode:
            link_mode = "TEST"
        else:
            link_mode = "UNLINKED"

        # case_party_id çöz: önce dışarıdan verilen değere bak, yoksa muvekkil_adi ile eşleştir
        resolved_party_id = case_party_id
        if resolved_party_id is None and case_id and muvekkil_adi:
            try:
                clean_name = muvekkil_adi.strip()
                # Önce tam eşleşme dene, sonra isim başlangıcıyla (kısmi ad farklarına karşı)
                party = (
                    db.query(models.CaseParty).filter(
                        models.CaseParty.case_id == case_id,
                        models.CaseParty.party_type == "CLIENT",
                        models.CaseParty.name.ilike(clean_name),
                    ).first()
                    or db.query(models.CaseParty).filter(
                        models.CaseParty.case_id == case_id,
                        models.CaseParty.party_type == "CLIENT",
                        models.CaseParty.name.ilike(f"%{clean_name}%"),
                    ).first()
                )
                if party:
                    resolved_party_id = party.id
            except Exception as e:
                logging.warning(f"case_party_id resolution failed for '{muvekkil_adi}': {e}")

        doc = models.CaseDocument(
            case_id=case_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            belge_turu_kodu=belge_turu_kodu,
            belge_turu_adi=belge_turu_adi,
            ai_summary=ai_summary,
            muvekkil_adi=muvekkil_adi,
            case_party_id=resolved_party_id,
            avukat_kodu=avukat_kodu,
            esas_no=esas_no,
            link_mode=link_mode,
            uploaded_by=uploaded_by,
            uploaded_by_email=uploaded_by_email,
        )
        db.add(doc)

        # Belge yüklendiğinde ilişkili davanın updated_at'ini güncelle
        # böylece ana sayfada "son belge eklenen davalar" öne çıksın
        if case_id:
            case = db.query(models.Case).filter(
                models.Case.id == case_id,
                models.Case.deleted_at.is_(None),  # soft-delete: silinmiş davaya dokunma
            ).first()
            if case:
                case.updated_at = datetime.now()

        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        logging.info(f"CaseDocument saved: ID={doc_id}, mode={link_mode}, case_id={case_id}, party_id={resolved_party_id}")
        return doc_id
    except Exception as e:
        logging.error(f"CaseDocument save error: {e}")
        return None
    finally:
        if db is not None:
            db.close()


def validate_tenant_and_resolve_lawyer(linked_case_id: int, user: dict, avukat_kodu: Optional[str]) -> Optional[str]:
    """IDOR-6: linked_case_id verildiyse tenant ownership doğrular.

    Belge SharePoint'e gitmeden ve save_case_document çağrılmadan önce reddetmeliyiz.
    Avukat kodu verilmemişse davanın sorumlu avukatından çözer ve döndürür.
    """
    from auth_helpers import get_tenant_owned_case
    user_tenant = user.get("tid")
    if not user_tenant:
        raise HTTPException(status_code=403, detail="Token'da tenant bilgisi bulunamadı")
    db_fetch = SessionLocal()
    try:
        case_fetch = get_tenant_owned_case(db_fetch, linked_case_id, user_tenant)
        if not case_fetch:
            raise HTTPException(status_code=404, detail="Belirtilen dava bulunamadı")
        # Auto-lookup lawyer code from case if not provided
        if not avukat_kodu and case_fetch.responsible_lawyer_name:
            try:
                lawyers = DynamicConfig.get_instance().get_lawyers()
                for lw in lawyers:
                    if lw.get("name") == case_fetch.responsible_lawyer_name:
                        avukat_kodu = lw.get("code")
                        break
            except Exception as e:
                logging.warning(f"Avukat lookup error (Confirm): {e}")
    finally:
        db_fetch.close()
    return avukat_kodu


async def accept_incoming_file(
    process_id: Optional[str], file: Optional[UploadFile], process_cache, owner: Optional[str]
) -> tuple:
    """Faz 3: Use PROCESS_CACHE if process_id provided; fall back to file upload.

    owner: isteği yapan kullanıcının kimliği — girdiyi yalnız /process'te
    cache'e koyan kullanıcı tüketebilir.

    Returns:
        (source_for_pdfa, original_for_ham) — cache hit'te dönüştürülmüş PDF +
        orijinal ham dosya; cache miss'te ikisi de yüklenen dosyanın kendisidir.
    """
    temp_path = None
    original_path = None
    _from_cache = False

    if process_id:
        cache_entry = process_cache.get(process_id)
        if cache_entry:
            entry_owner = (cache_entry.get("owner") or "").strip().lower()
            requester = (owner or "").strip().lower()
            if not requester or not entry_owner or requester != entry_owner:
                # Mask existence to avoid leaking valid process_ids to non-owners;
                # girdi sahibinde kalır, cache miss gibi davranılır.
                TechnicalLogger.log("WARNING", f"PROCESS_CACHE owner mismatch: {process_id}")
                cache_entry = None
            else:
                cache_entry = process_cache.pop(process_id)
        if cache_entry:
            cached_path = cache_entry["path"]
            if os.path.exists(cached_path):
                temp_path = cached_path
                cached_original = cache_entry.get("original_path")
                if cached_original and os.path.exists(cached_original):
                    original_path = cached_original
                _from_cache = True
                TechnicalLogger.log("INFO", f"PROCESS_CACHE hit: {process_id} → {cached_path} (original: {original_path})")
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
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail=f"Dosya çok büyük. Maksimum {MAX_UPLOAD_MB}MB.")
                    tmp_file.write(chunk)
            TechnicalLogger.log("INFO", f"Temp file created for upload: {temp_path} ({total_bytes} bytes)")
            validate_file_type(temp_path)
        except HTTPException:
            safe_remove(temp_path)
            raise
        except Exception as e:
            safe_remove(temp_path)
            logger.error(f"Geçici dosya kaydetme hatası: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Dosya kaydedilemedi. Lütfen tekrar deneyin.") from e

    return temp_path, original_path or temp_path


def async_increment_counter():
    try:
        from managers.counter_manager import get_counter_manager
        counter = get_counter_manager()
        counter.increment_counter()
    except Exception as e:
        TechnicalLogger.log("ERROR", f"Async Counter Error: {e}")


def async_ham_upload(source_path: str, ham_filename: str, ham_folder: str):
    try:
        from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
        upload_file_to_sharepoint(source_path, ham_filename, ham_folder, use_date_subfolder=False)
    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Async Ham Upload Error [ID: {error_id}]: {e}")


def async_islenmis_upload(temp_file_path, new_filename: str, islenmis_folder: str, doc_id_to_update=None):
    try:
        from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
        response_data = upload_file_to_sharepoint(
            temp_file_path,
            new_filename,
            islenmis_folder,
            use_date_subfolder=False,
        )

        # Update database with SharePoint URL upon successful upload
        url_saved = False
        if doc_id_to_update and response_data and "webUrl" in response_data:
            db_upd = SessionLocal()
            try:
                doc_rec = db_upd.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id_to_update).first()
                if doc_rec:
                    doc_rec.sharepoint_url = response_data["webUrl"]
                    db_upd.commit()
                    url_saved = True
                    logging.info(f"✅ SharePoint URL updated for Doc ID {doc_id_to_update}: {response_data['webUrl']}")
            except Exception as db_err:
                logging.error(f"Failed to update SharePoint URL in DB for Doc ID {doc_id_to_update}: {db_err}")
            finally:
                db_upd.close()

        # Hukukbot aktarımı (Faz 3): outbox satırı yalnızca URL commit'inden
        # SONRA açılır (BULGULAR #1). Hook hatası arşivleme akışını deviremez.
        if url_saved:
            try:
                from services.export_publisher import notify_hukukbot
                notify_hukukbot(doc_id_to_update)
            except Exception as hook_err:
                TechnicalLogger.log("ERROR", f"Hukukbot export hook error (doc={doc_id_to_update}): {hook_err}")

    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Async Processed Upload Error [ID: {error_id}]: {e}")


def convert_pdfa_and_queue_uploads(
    background_tasks: BackgroundTasks,
    source_path: str,
    ham_filename: str,
    ham_folder: str,
    islenmis_folder: str,
    new_filename: str,
    original_filename: str,
    belge_turu_kodu: Optional[str],
    muvekkiller: list,
    muvekkil_adi: Optional[str],
    ai_ozet: Optional[str],
    linked_case_id: Optional[int],
    case_party_id: Optional[int],
    avukat_kodu: Optional[str],
    esas_no: Optional[str],
    is_test_mode: bool,
    user: dict,
    current_user_name: str,
    results: dict,
    timings: dict,
    ham_source_path: Optional[str] = None,
):
    """PDF/A dönüşümü + DB kaydı + iki SharePoint arşiv yüklemesinin kuyruklanması.

    Faz 4: ham upload is queued AFTER PDF/A succeeds so both archives are consistent.
    Başarıda (pdfa_temp_file, doc_id) döndürür; başarısızlıkta HTTPException(500) fırlatır.
    """
    pdfa_temp_file = None
    doc_id = None
    try:
        from pdf.pdf_converter import convert_to_pdfa2b

        step_start = perf_time.perf_counter()
        pdfa_temp_file = convert_to_pdfa2b(source_path)
        timings["3a_pdfa_convert"] = perf_time.perf_counter() - step_start

        if pdfa_temp_file and os.path.exists(pdfa_temp_file):
            # Create the database record before adding background tasks so we have doc_id
            belge_turu_label = get_doctype_label(belge_turu_kodu) if belge_turu_kodu else None
            clean_muvekkil = (muvekkiller[0] if muvekkiller else None) or muvekkil_adi

            current_user_email = user.get("preferred_username") or user.get("upn") or user.get("email") or None
            doc_id = save_case_document(
                case_id=linked_case_id,
                original_filename=original_filename,
                stored_filename=new_filename,
                belge_turu_kodu=belge_turu_kodu,
                belge_turu_adi=belge_turu_label,
                ai_summary=ai_ozet,
                muvekkil_adi=clean_muvekkil,
                case_party_id=case_party_id,
                avukat_kodu=avukat_kodu,
                esas_no=esas_no,
                is_test_mode=is_test_mode,
                uploaded_by=current_user_name,
                uploaded_by_email=current_user_email,
            )
            results["case_document_id"] = doc_id

            # Both archives queued together only after successful PDF/A conversion.
            # HAM arşive orijinal ham dosya gider (dönüştürülmüş formatlarda
            # source_path analiz PDF'i olabilir — bkz. accept_incoming_file).
            background_tasks.add_task(async_ham_upload, ham_source_path or source_path, ham_filename, ham_folder)
            background_tasks.add_task(async_islenmis_upload, pdfa_temp_file, new_filename, islenmis_folder, doc_id)
            timings["2_ham_upload"] = 0.00
            timings["3b_gizli_upload"] = 0.00
            results["sharepoint_ham"] = f"Arka Plana Atıldı ({ham_filename})"
            results["sharepoint_islenmis"] = "Arka Plana Atıldı (PDF/A-2b)"
        else:
            raise Exception("PDF/A-2b dönüşümü başarısız - dosya oluşturulamadı")

    except HTTPException:
        raise
    except (RuntimeError, ValueError) as e:
        # Dönüşüm katmanının kullanıcıya dönük mesajları (pdf_converter RuntimeError,
        # udf_converter ValueError) — "SharePoint başarısız" deyip gerçek nedeni
        # gizlemek kullanıcıyı yanlış yere bakmaya itiyordu (2026-08-05 arızası).
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Processed Upload Error [ID: {error_id}]: {e}")
        raise HTTPException(status_code=500, detail=f"{e} (Hata: {error_id})") from e
    except Exception as e:
        error_id = str(uuid.uuid4())[:8]
        TechnicalLogger.log("ERROR", f"Processed Upload Error [ID: {error_id}]: {e}")
        raise HTTPException(status_code=500, detail=f"SharePoint arşiv yüklemesi başarısız. (Hata: {error_id})") from e

    return pdfa_temp_file, doc_id


async def save_extra_attachments(extra_attachment_files: list) -> tuple[list, list]:
    """Extra ekleri ana dosyayla aynı doğrulamadan (uzantı + boyut + magic-byte)
    geçirip temp dosyaya kaydeder. Geçemeyen ek e-postaya eklenmez.

    Returns:
        (kaydedilenler, atlanan dosya adları) — atlananlar results'a yazılıp
        kullanıcıya gösterilir.
    """
    extra_temp_paths = []
    skipped = []
    for extra_file in extra_attachment_files:
        if not (extra_file and extra_file.filename):
            continue
        filename = extra_file.filename
        extra_suffix = Path(filename).suffix.lower()
        if extra_suffix not in ALLOWED_EXTENSIONS:
            TechnicalLogger.log("WARNING", f"Extra attachment rejected (uzantı {extra_suffix or '(yok)'}): {filename}")
            skipped.append(filename)
            continue
        tmp_path = None
        try:
            total_bytes = 0
            with tempfile.NamedTemporaryFile(delete=False, suffix=extra_suffix) as etmp:
                tmp_path = etmp.name
                # Chunk'lı okuma: tek seferlik read() 50 MB'a kadar tek
                # parça bytes tahsis ediyordu (ana upload zaten chunk'lı)
                while chunk := await extra_file.read(65536):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail=f"Ek çok büyük. Maksimum {MAX_UPLOAD_MB}MB.")
                    etmp.write(chunk)
            validate_file_type(tmp_path)
            extra_temp_paths.append({"path": tmp_path, "name": filename})
        except HTTPException as e:
            safe_remove(tmp_path)
            TechnicalLogger.log("WARNING", f"Extra attachment rejected: {filename} — {e.detail}")
            skipped.append(filename)
        except Exception as e:
            safe_remove(tmp_path)
            TechnicalLogger.log("WARNING", f"Extra attachment save error ({filename}): {e}")
            skipped.append(filename)
    return extra_temp_paths, skipped


def send_email_sync(pdf_path, filename, avukat_kodu, email_metadata, to_list, cc_list, msg=None, messages=None, extra_paths=None, sender_name=None, doc_id=None, subject_prefix="[HukDok]"):
    def _update_email_status(success: bool, error_msg: str = None):
        if not doc_id:
            return
        db_upd = SessionLocal()
        try:
            doc_rec = db_upd.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
            if doc_rec:
                doc_rec.email_sent = success
                doc_rec.email_error = None if success else error_msg
                db_upd.commit()
        except Exception as db_err:
            logging.error(f"Email status DB update error (doc_id={doc_id}): {db_err}")
        finally:
            db_upd.close()

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
            custom_messages=messages,
            extra_attachment_paths=extra_paths,
            sender_name=sender_name,
            subject_prefix=subject_prefix,
        )
        if result["success"]:
            TechnicalLogger.log("INFO", f"E-posta gönderildi: {filename} → {len(to_list)} alıcı")
            _update_email_status(True)
        else:
            TechnicalLogger.log("WARNING", f"E-posta gönderilemedi: {filename} — {result['message']}")
            _update_email_status(False, result["message"])
        return result
    except Exception as e:
        TechnicalLogger.log("ERROR", f"Email Error: {e}")
        _update_email_status(False, str(e))
        return {"success": False, "message": str(e)}
    finally:
        # Extra temp dosyalarını temizle
        if extra_paths:
            for ep in extra_paths:
                safe_remove(ep.get("path"))


def resolve_lawyer_name(avukat_kodu: Optional[str]) -> str:
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
    return avukat_adi


def build_email_metadata(muvekkiller, muvekkil_adi, muvekkil_kodu, belge_turu_kodu, tarih, avukat_adi, teblig_tarihi) -> dict:
    clean_client_name = (muvekkiller[0] if muvekkiller else None) or muvekkil_adi
    return {
        "muvekkil_adi": clean_client_name or muvekkil_kodu or "Bilinmeyen Müvekkil",
        "muvekkiller": muvekkiller or [],
        "belge_turu": get_doctype_label(belge_turu_kodu) or "Belge",
        "tarih": tarih or "",
        "avukat_adi": avukat_adi,
        "teblig_tarihi": normalize_date_for_sharepoint(teblig_tarihi) if teblig_tarihi else None,
    }


def email_pre_check(email_file_path, custom_to) -> str | None:
    """Gönderim kesinlikle olmayacaksa neden döndürür, yoksa None."""
    if not email_file_path or not os.path.exists(email_file_path):
        return "Dosya bulunamadı"
    try:
        from email_sender import _get_email_config
        cfg = _get_email_config()
        if not cfg["enabled"]:
            return "E-posta özelliği kapalı (EMAIL_ENABLED=false)"
        if not custom_to and not cfg["test_mode"]:
            return "Alıcı listesi boş"
    except Exception:
        pass
    return None


async def send_notification_email(
    email_file_path,
    new_filename: str,
    avukat_kodu: Optional[str],
    email_metadata: dict,
    custom_to: list,
    custom_cc: list,
    custom_email_message: Optional[str],
    custom_messages,
    extra_temp_paths: list,
    current_user_name: str,
    doc_id,
    results: dict,
    timings: dict,
):
    """Avukata belge bildirimi e-postası (send_email=True akışı)."""
    pre_check_error = email_pre_check(email_file_path, custom_to)
    if pre_check_error:
        results["email"] = f"Gönderilemedi: {pre_check_error}"
        results["email_warning"] = pre_check_error
        results["email_success"] = False
        TechnicalLogger.log("WARNING", f"E-posta ön-kontrol başarısız: {pre_check_error} — {new_filename}")
    else:
        t_email = perf_time.perf_counter()
        email_result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: send_email_sync(
                email_file_path, new_filename, avukat_kodu, email_metadata,
                custom_to, custom_cc, custom_email_message or None,
                custom_messages or None, extra_temp_paths or None,
                current_user_name, doc_id
            )
        )
        timings["7_email"] = round((perf_time.perf_counter() - t_email) * 1000, 2)
        if email_result.get("success"):
            results["email"] = "Gönderildi"
            results["email_warning"] = None
            results["email_success"] = True
        else:
            results["email"] = f"Gönderilemedi: {email_result.get('message', 'Bilinmeyen hata')}"
            results["email_warning"] = email_result.get("message", "Bilinmeyen hata")
            results["email_success"] = False


async def send_client_notice_email(
    email_file_path,
    new_filename: str,
    avukat_kodu: Optional[str],
    avukat_adi: str,
    email_metadata: dict,
    client_notice_message: Optional[str],
    current_user_name: str,
    results: dict,
    timings: dict,
):
    """Müvekkil bilgilendirme metnini davanın sorumlu avukatına ayrı e-posta olarak gönderir."""
    # Sorumlu avukatın e-postasını çöz (avukat_kodu → lawyers config).
    lawyer_email = ""
    lawyer_name = avukat_adi or "İlgili Avukat"
    if avukat_kodu:
        try:
            for lw in DynamicConfig.get_instance().get_lawyers():
                if lw.get("code") == avukat_kodu:
                    lawyer_email = (lw.get("email") or "").strip()
                    lawyer_name = lw.get("name") or lawyer_name
                    break
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Müvekkil bildirimi avukat email lookup hatası: {e}")

    if not lawyer_email:
        results["client_notice"] = "Gönderilemedi: Sorumlu avukatın e-postası yok"
        results["client_notice_warning"] = "Sorumlu avukatın e-posta adresi bulunamadı"
        results["client_notice_success"] = False
        TechnicalLogger.log("WARNING", f"Müvekkil bildirimi atlandı: sorumlu avukat e-postası yok — {new_filename}")
    else:
        notice_recipient = f"{lawyer_name} <{lawyer_email}>"
        t_notice = perf_time.perf_counter()
        # doc_id geçilmez: belgenin (avukat) email_sent durumunu ezmemeli.
        # subject_prefix: "[Müvekkil Bilgilendirme]" — ayrı, ayırt edilebilir konu.
        notice_result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: send_email_sync(
                email_file_path, new_filename, avukat_kodu, email_metadata,
                [notice_recipient], [], client_notice_message or None,
                None, None,
                current_user_name, None, "[Müvekkil Bilgilendirme]"
            )
        )
        timings["7b_client_notice"] = round((perf_time.perf_counter() - t_notice) * 1000, 2)
        if notice_result.get("success"):
            results["client_notice"] = "Gönderildi"
            results["client_notice_warning"] = None
            results["client_notice_success"] = True
        else:
            results["client_notice"] = f"Gönderilemedi: {notice_result.get('message', 'Bilinmeyen hata')}"
            results["client_notice_warning"] = notice_result.get("message", "Bilinmeyen hata")
            results["client_notice_success"] = False


async def async_cleanup(temp_path, down_id=None, download_cache=None):
    # asyncio.sleep: senkron time.sleep(30) her /confirm'de 1-3 anyio
    # threadpool token'ını 30 sn işgal edip havuzu kurutuyordu
    await asyncio.sleep(30)
    if safe_remove(temp_path, retries=5):
        logging.info(f"Cleanup: Temp file deleted: {temp_path}")
    else:
        logging.warning(f"Cleanup: Could not delete: {temp_path}")
    if down_id:
        download_cache.delete(down_id)


def schedule_cleanup(background_tasks: BackgroundTasks, source_path, pdfa_temp_file, download_id, download_cache, ham_source_path=None):
    """Temp dosyaları temizle (source_path her zaman; pdfa ve ham orijinal farklıysa onlar da)."""
    if ham_source_path and ham_source_path != source_path:
        background_tasks.add_task(async_cleanup, ham_source_path)
    if pdfa_temp_file and pdfa_temp_file != source_path:
        background_tasks.add_task(async_cleanup, source_path)
        background_tasks.add_task(async_cleanup, pdfa_temp_file, download_id, download_cache)
    else:
        background_tasks.add_task(async_cleanup, source_path, download_id, download_cache)


def save_hearing_date(
    linked_case_id: int,
    belge_turu_kodu: Optional[str],
    sonraki_durusma_tarihi: Optional[str],
    sonraki_durusma_saati: Optional[str],
    avukat_adi: str,
    new_filename: str,
    current_user_name: str,
    results: dict,
):
    """Duruşma/tensip zaptı veya tebligattan gelen sonraki duruşma tarihini ajandaya kaydet."""
    from constants import is_hearing_doctype
    if sonraki_durusma_tarihi and is_hearing_doctype(belge_turu_kodu):
        db_h = None
        try:
            from datetime import date as _date
            parsed_hearing = _date.fromisoformat(sonraki_durusma_tarihi)
            db_h = SessionLocal()

            # Dedup: aynı duruşma hem tebligattan hem zabıttan gelebilir
            existing = (
                db_h.query(models.HearingDate)
                .filter(
                    models.HearingDate.case_id == linked_case_id,
                    models.HearingDate.hearing_date == parsed_hearing,
                    models.HearingDate.hearing_time == (sonraki_durusma_saati or None),
                )
                .first()
            )
            if existing:
                results["hearing_date_saved"] = sonraki_durusma_tarihi
                results["hearing_time_saved"] = sonraki_durusma_saati or None
                logging.info(f"HearingDate zaten mevcut, duplicate atlandı: case_id={linked_case_id}, tarih={parsed_hearing}, saat={sonraki_durusma_saati}")
                return

            case_h = db_h.query(models.Case).filter(
                models.Case.id == linked_case_id,
                models.Case.deleted_at.is_(None),
            ).first()
            hearing = models.HearingDate(
                case_id=linked_case_id,
                hearing_date=parsed_hearing,
                hearing_time=sonraki_durusma_saati or None,
                lawyer_name=avukat_adi or (case_h.responsible_lawyer_name if case_h else None),
                extracted_from_doc=new_filename,
                created_by=current_user_name,
            )
            db_h.add(hearing)
            db_h.commit()
            results["hearing_date_saved"] = sonraki_durusma_tarihi
            results["hearing_time_saved"] = sonraki_durusma_saati or None
            logging.info(f"HearingDate kaydedildi: case_id={linked_case_id}, tarih={parsed_hearing}, saat={sonraki_durusma_saati}")
        except Exception as e:
            logging.error(f"HearingDate kaydetme hatası: {e}")
            results["hearing_date_saved"] = None
            results["hearing_time_saved"] = None
        finally:
            if db_h is not None:
                db_h.close()
    else:
        results["hearing_date_saved"] = None
        results["hearing_time_saved"] = None
