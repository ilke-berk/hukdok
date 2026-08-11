"""Otonom dava açma — case intake route'ları (Faz 2 + Faz 3 + Faz 4).

POST /api/case-intake/analyze: tek belge alır, intake çıkarım motorunu
(case_intake_analyzer) koşturur ve /process ile aynı şekilli NDJSON stream
döner. Terminal olay:

    {"status": "complete", "process_id": "<uuid>",
     "data": {...CaseIntakeExtraction..., "belge_turu_kodu_tahmini": "...",
              "agreement": {alan: skor}, "verification": {...}}}

Tam PDF, /process ile aynı hijyenle PROCESS_CACHE'e konur — Faz 4 commit
adımı belgeyi process_id ile oradan alacak.

POST /api/case-intake/merge (Faz 3): oturumdaki N belgenin çıkarımlarını tek
dava kartı taslağında birleştirir — durumsuz, saf birleştirme mantığı
services/case_intake.py'de; DB bağlamı (cariler, kayıtlı poliçeler, bilinen
mahkeme adları, geçmiş dava örüntüleri) burada yüklenir. esas_no/mahkeme
çelişkisinde hakem LLM (Katman 3) çağrılır; çelişki yoksa çağrılmaz.

POST /api/case-intake/keepalive (Faz 3): PROCESS_CACHE TTL tazeler — sihirbaz
review adımında 10 dk'da bir çağırır (hazırlık raporu Risk 4 sigortası).

POST /api/case-intake/commit (Faz 4): sihirbazın tek "Kaydet ve Arşivle"
adımı — dava kaydı atomik, belge arşivleme belge-başı best-effort, poliçe
beslemesi best-effort (kesin kararlar 1-5, bkz. Faz 4 kickoff dokümanı).
"""
import asyncio
import base64
import email
import email.message
import email.policy
import hashlib
import html as html_lib
import json
import logging
import mimetypes
import os
import re
import tempfile
import uuid
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from auth_helpers import tenant_filter_clause
from dependencies import get_current_tenant, get_current_user
from file_utils import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    safe_remove,
    sanitize_filename,
    validate_file_type,
)
from managers.log_manager import TechnicalLogger
from pdf.format_converter import ConversionBusyError
from routes.processing import DOWNLOAD_CACHE, PROCESS_CACHE, _cleanup_process_cache, _owner_id, _touch_owned
from schemas_intake import (
    CaseIntakeApplyRequest,
    CaseIntakeCommitRequest,
    CaseIntakeMergeRequest,
    CommitDocumentIn,
    CommitOptions,
    CommitPolicyIn,
    KeepaliveRequest,
)
from services.html_sanitizer import DOC_PREFIX, DOC_SUFFIX, html_to_text, sanitize_email_html

router = APIRouter()
logger = logging.getLogger(__name__)


def resolve_upload_suffix(filename: Optional[str]) -> str:
    """Uzantı çözümü. UYAP UDF'leri bazen '.udf.zip' adıyla gelir (UDF zaten
    bir zip arşividir) — bunlar '.udf' olarak işlenir; beyaz liste değişmez."""
    name = (filename or "").lower()
    if name.endswith(".udf.zip"):
        return ".udf"
    return Path(name).suffix


# =====================================================================
# .eml genişletme — sihirbaza özel
# (plan: docs/arsiv/eml-intake-gelistirme-plani-2026-08-01.md).
# .eml ALLOWED_EXTENSIONS'a GİRMEZ; doğrulama burada yereldir. Parçalar
# frontend'te normal dosya gibi listeye eklenir — analiz/merge/commit/arşiv
# hattı bu endpoint'ten habersizdir.
# =====================================================================

_EML_HEADER_RE = re.compile(rb"^(From|Received|Subject|MIME-Version):", re.IGNORECASE | re.MULTILINE)

# Gövde HTML temizliği services/html_sanitizer.py'ye taşındı (G023).
#
# GÜVENLİK (SSRF): gövde soffice ile PDF'e çevrilirken LibreOffice uzak kaynak
# taşıyan attribute'ları GERÇEKTEN çeker — `<table background="http://...">`
# ile kanıtlandı. Regex tabanlı temizlik (G015) saldırganın baytlarını çıktıya
# aynen geçirdiği için sınıfı kapatamadı; artık girdi tokenize edilip çıktı
# SIFIRDAN kanonik olarak yeniden yazılıyor. Politikanın tamamı (düşürülen
# etiketler, attribute allowlist'i, değer kapıları) sanitizer modülündedir.

EML_BODY_FILENAME = "E-posta_govdesi.pdf"


def _looks_like_eml(head: bytes) -> bool:
    """İlk ~32 KB'de RFC822 başlıklarından en az İKİSİ aranır (.eml'in magic
    byte'ı yoktur — düz metin başlıklarıyla tanınır). Pencere 32 KB: gerçek
    Outlook maillerinde ARC/DKIM imza blokları From:/Subject:'i birkaç KB
    geriye itiyor (ölçüldü: From ~5.6 KB, MIME-Version ~17 KB)."""
    found = {m.group(1).lower() for m in _EML_HEADER_RE.finditer(head)}
    return len(found) >= 2


def _email_header_html(msg: email.message.EmailMessage) -> str:
    """Konu/Kimden/Kime/Tarih tablosu — konu satırı hasar no + esas no taşıdığı
    için modele mutlaka gitmeli."""
    rows = [
        ("Konu", msg.get("Subject")),
        ("Kimden", msg.get("From")),
        ("Kime", msg.get("To")),
        ("Tarih", msg.get("Date")),
    ]
    cells = "".join(
        f"<tr><td><b>{html_lib.escape(label)}</b></td>"
        f"<td>{html_lib.escape(str(value))}</td></tr>"
        for label, value in rows
        if value
    )
    return f'<table border="1" cellpadding="4" cellspacing="0">{cells}</table><hr>'


def _plain_body_document(header_html: str, text: str) -> str:
    """Düz metin gövdesi — tamamı kaçışlanır, markup olarak yorumlanacak bayt
    kalmaz. Belge iskeleti sanitizer'ınkiyle aynı sabitten gelir."""
    return (
        DOC_PREFIX
        + header_html
        + f'<pre style="white-space:pre-wrap">{html_lib.escape(text)}</pre>'
        + DOC_SUFFIX
    )


def _build_body_html(msg: email.message.EmailMessage) -> Optional[str]:
    """Gövdeyi (HTML tercihli) başlık tablosuyla birleşik tek HTML'e çevirir.

    HTML gövde tokenizer ile yeniden serileştirilir (services/html_sanitizer).
    Temizlik patlarsa ya da boyut tavanı aşılırsa ham HTML soffice'e ASLA
    gitmez — görünür metin çıkarılıp düz-metin yoluna düşülür (fail-closed).
    """
    part = msg.get_body(preferencelist=("html", "plain"))
    if part is None:
        return None
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return None
        content = payload.decode("utf-8", errors="replace")

    header_html = _email_header_html(msg)
    if part.get_content_type() == "text/html":
        try:
            return sanitize_email_html(content, body_prefix=header_html)
        except Exception as e:
            TechnicalLogger.log(
                "WARNING",
                f"[INTAKE-EML] HTML temizliği yapılamadı, düz metin yoluna düşüldü: {e}",
            )
            content = html_to_text(content)
    return _plain_body_document(header_html, content)


def _render_body_pdf(body_html: str) -> bytes:
    """Gövde HTML → PDF (soffice). Karmaşık HTML dönüşümü patlarsa gövde düz
    metne indirilip yeniden denenir (plan risk maddesi)."""
    from pdf.format_converter import html_to_pdf

    def _convert(html_text: str) -> bytes:
        html_path = None
        pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8-sig", suffix=".html", delete=False
            ) as f:
                html_path = f.name
                f.write(html_text)
            pdf_path = html_to_pdf(html_path)
            with open(pdf_path, "rb") as pf:
                return pf.read()
        finally:
            safe_remove(html_path)
            safe_remove(pdf_path)

    try:
        return _convert(body_html)
    except Exception as e:
        TechnicalLogger.log(
            "WARNING", f"[INTAKE-EML] HTML gövde dönüşümü başarısız, düz metin fallback: {e}"
        )
        return _convert(_plain_body_document("", html_to_text(body_html)))


@router.post("/api/case-intake/expand-eml")
async def expand_eml(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Tek .eml'i parçalara açar: gövde sanal belge (PDF) + izinli ekler.

    Yanıt JSON (base64): {"body": {...}|null, "attachments": [...], "skipped": [...]}.
    Orijinal .eml arşivlenmez; parçalar frontend'te normal dosya olarak akar.
    """
    data = bytearray()
    while chunk := await file.read(65536):
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Dosya çok büyük. Maksimum {MAX_UPLOAD_MB}MB.")

    if not _looks_like_eml(bytes(data[:32768])):
        raise HTTPException(
            status_code=400,
            detail="Geçerli bir e-posta (.eml) dosyası değil — RFC822 başlıkları bulunamadı.",
        )

    try:
        msg = email.message_from_bytes(bytes(data), policy=email.policy.default)
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE-EML] Parse hatası: {e}")
        raise HTTPException(status_code=400, detail="E-posta dosyası okunamadı (bozuk format).") from e

    # ── Gövde → sanal belge PDF'i ────────────────────────────────────────
    body_entry: Optional[Dict[str, str]] = None
    body_html = _build_body_html(msg)
    if body_html is not None:
        loop = asyncio.get_running_loop()
        try:
            pdf_bytes = await loop.run_in_executor(None, _render_body_pdf, body_html)
            body_entry = {
                "filename": sanitize_filename(EML_BODY_FILENAME),
                "data_b64": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log(
                "ERROR", f"[INTAKE-EML] Gövde PDF dönüşümü başarısız [ID: {error_id}]: {e}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"E-posta gövdesi PDF'e dönüştürülemedi (Hata: {error_id}).",
            ) from e

    # ── Ekler ────────────────────────────────────────────────────────────
    attachments: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    total_bytes = 0
    for i, part in enumerate(msg.iter_attachments(), start=1):
        ctype = part.get_content_type()
        raw_name = part.get_filename()
        display_name = raw_name or f"ek_{i}"

        # İç içe .eml (attached message) Faz 1'de açılmaz.
        if ctype == "message/rfc822" or (raw_name or "").lower().endswith(".eml"):
            skipped.append({
                "filename": raw_name or f"ek_{i}.eml",
                "reason": "iç içe e-posta desteklenmiyor",
            })
            continue

        # iter_attachments inline/cid gövde parçalarını zaten dışarıda bırakır;
        # yine de ek olarak işaretlenmiş Content-ID'li görseller (imza logoları) elenir.
        if part.get("Content-ID") and part.get_content_maintype() == "image":
            skipped.append({"filename": display_name, "reason": "inline görsel"})
            continue

        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            skipped.append({"filename": display_name, "reason": "içerik çözülemedi"})
            continue

        if not raw_name:
            raw_name = f"ek_{i}{mimetypes.guess_extension(ctype) or ''}"

        # Whitelist kontrolü sanitize'dan ÖNCE — sanitize_filename izin dışı
        # uzantıda HTTPException fırlatır, burada sessizce atlanmalı.
        suffix = resolve_upload_suffix(raw_name)
        if suffix not in ALLOWED_EXTENSIONS:
            skipped.append({
                "filename": raw_name,
                "reason": f"uzantı desteklenmiyor ({suffix or 'uzantısız'})",
            })
            continue

        if len(payload) > MAX_UPLOAD_BYTES:
            skipped.append({
                "filename": raw_name,
                "reason": f"boyut aşımı (maksimum {MAX_UPLOAD_MB}MB)",
            })
            continue
        total_bytes += len(payload)
        if total_bytes > MAX_UPLOAD_BYTES:
            skipped.append({
                "filename": raw_name,
                "reason": f"toplam boyut aşımı (maksimum {MAX_UPLOAD_MB}MB)",
            })
            continue

        attachments.append({
            "filename": sanitize_filename(raw_name),
            "data_b64": base64.b64encode(payload).decode("ascii"),
        })

    TechnicalLogger.log(
        "INFO",
        "[INTAKE-EML] Genişletme tamamlandı",
        {
            "body": body_entry is not None,
            "attachments": [a["filename"] for a in attachments],
            "skipped": skipped,
        },
    )
    return {"body": body_entry, "attachments": attachments, "skipped": skipped}


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

    # Faz 3-E: süpürme artık disk taraması + payload silme → executor'da.
    await asyncio.get_running_loop().run_in_executor(None, _cleanup_process_cache)
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
                        # Faz 3-E: set() payload'ı volume'e taşır → executor'da
                        # (routes/processing.py'deki /process ile aynı gerekçe).
                        await asyncio.get_running_loop().run_in_executor(
                            None,
                            PROCESS_CACHE.set,
                            process_id,
                            {
                                "path": full_pdf_path,
                                "original_path": original_path,
                                "original_ext": suffix,
                                "owner": _owner_id(user),
                            },
                        )
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


# =====================================================================
# Faz 3 — merge + keepalive
# =====================================================================


def _load_merge_context(tenant_id: str) -> Dict[str, Any]:
    """Merge için DB bağlamı: cariler, geçmiş dosya tarafları, bilinen mahkemeler,
    kanonik dava konusu + uzmanlık listeleri.

    parties route'unun sorgu şekliyle birebir (check_parties aynı satırları bekler).
    """
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        client_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no,
                "cari_kod": r.cari_kod, "category": r.category,
                "contact_type": r.contact_type,
            }
            for r in (
                db.query(
                    models.Client.id, models.Client.name, models.Client.tc_no,
                    models.Client.cari_kod, models.Client.category,
                    models.Client.contact_type,
                )
                .filter(models.Client.active.is_(True))
                .filter(models.Client.deleted_at.is_(None))
                .filter(tenant_filter_clause(models.Client, tenant_id))
                .all()
            )
        ]
        party_rows = [
            {
                "id": r.id, "name": r.name, "tc_no": r.tc_no, "role": r.role,
                "party_type": r.party_type, "client_id": r.client_id,
                "case_id": r.case_id, "tracking_no": r.tracking_no,
                "case_subject": r.subject, "case_status": r.status,
            }
            for r in (
                db.query(
                    models.CaseParty.id, models.CaseParty.name,
                    models.CaseParty.tc_no, models.CaseParty.role,
                    models.CaseParty.party_type, models.CaseParty.client_id,
                    models.CaseParty.case_id, models.Case.tracking_no,
                    models.Case.subject, models.Case.status,
                )
                .join(models.Case, models.CaseParty.case_id == models.Case.id)
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .filter(models.Case.deleted_at.is_(None))
                .all()
            )
        ]
        known_courts = [
            r[0] for r in (
                db.query(models.Case.court)
                .filter(models.Case.active.is_(True), models.Case.court.isnot(None))
                .filter(tenant_filter_clause(models.Case, tenant_id))
                .distinct()
                .all()
            )
            if r[0]
        ]
        # Kanonik listeler (dava konusu + uzmanlık): merge bekçisi liste dışı
        # AI değerini boşaltır. Liste yüklenemezse bekçi devre dışı kalır
        # (None → build_draft dokunmaz), merge durmaz.
        known_subjects: Optional[List[str]] = None
        known_specialties: Optional[List[str]] = None
        try:
            from managers.reference_lists import get_case_subjects, get_specialties

            known_subjects = [
                s.get("name") for s in (get_case_subjects() or []) if s.get("name")
            ] or None
            known_specialties = [
                s.get("name") for s in (get_specialties() or []) if s.get("name")
            ] or None
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Konu/uzmanlık listesi alınamadı: {e}")
        return {
            "client_rows": client_rows,
            "party_rows": party_rows,
            "known_courts": known_courts,
            "known_subjects": known_subjects,
            "known_specialties": known_specialties,
        }
    finally:
        db.close()


def _load_known_policies(client_ids: List[int]) -> List[Dict[str, Any]]:
    """Eşleşen hekimlerin kayıtlı poliçeleri (client_policies) — merge listesine karışır."""
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        rows = (
            db.query(models.ClientPolicy, models.Client.name)
            .join(models.Client, models.ClientPolicy.client_id == models.Client.id)
            .filter(models.ClientPolicy.client_id.in_(client_ids))
            .all()
        )
        return [
            {
                "id": p.id,
                "client_id": p.client_id,
                "client_name": client_name,
                "police_no": p.police_no,
                "police_turu": p.police_turu,
                "sigorta_sirketi": p.sigorta_sirketi,
                "baslangic_tarihi": p.baslangic_tarihi,
                "bitis_tarihi": p.bitis_tarihi,
                "retroaktif_tarihi": p.retroaktif_tarihi,
                "sigortali_kurum": p.sigortali_kurum,
                "teminat_limiti": p.teminat_limiti,
            }
            for p, client_name in rows
        ]
    finally:
        db.close()


def _load_client_case_rows(client_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Eşleşen müvekkillerin geçmiş dava örüntüleri (zenginleştirme 4 — priors)."""
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        rows = (
            db.query(
                models.CaseParty.client_id, models.Case.file_type,
                models.Case.sub_type, models.Case.responsible_lawyer_name,
                models.Case.subject,
            )
            .join(models.Case, models.CaseParty.case_id == models.Case.id)
            .filter(models.CaseParty.client_id.in_(client_ids))
            .filter(models.Case.active.is_(True))
            .all()
        )
        by_client: Dict[int, List[Dict[str, Any]]] = {}
        for client_id, file_type, sub_type, lawyer, subject in rows:
            by_client.setdefault(client_id, []).append({
                "file_type": file_type,
                "sub_type": sub_type,
                "responsible_lawyer_name": lawyer,
                "subject": subject,
            })
        return by_client
    finally:
        db.close()


@router.post("/api/case-intake/merge")
async def merge_case_intake(
    req: CaseIntakeMergeRequest,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Oturumdaki belge çıkarımlarını tek dava kartı taslağında birleştirir (durumsuz)."""
    import case_intake_analyzer
    from case_matcher import find_matching_case
    from managers import case_manager
    from party_check import check_parties
    from services.case_intake import (
        annotate_enrich_status,
        apply_arbitration,
        build_doc_summaries,
        build_draft,
        client_priors,
        detect_conflicts,
        inject_case_candidates,
        mark_existing_parties,
        merge_parties,
    )

    loop = asyncio.get_running_loop()
    docs = [d.model_dump() for d in req.documents]

    # 0. Zenginleştirme modu (Faz 7): hedef dava yüklenir (tenant süzgeçli) —
    # değerleri aşağıda "kayıtlı dava" kaynaklı aday olarak taslağa katılır.
    case_row: Optional[Dict[str, Any]] = None
    if req.case_id is not None:
        case_row = await loop.run_in_executor(
            None, partial(case_manager.get_case, req.case_id, tenant_id)
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Zenginleştirilecek dava bulunamadı.")

    # 1. Keepalive: listelenen tüm process_id'lerin TTL'i tazelenir; süresi
    #    dolmuş belge birleştirmeye girer ama taslakta expired işaretlenir
    #    (commit adımı o belgeyi arşivleyemeyecek — kullanıcı bilgilendirilir).
    requester = _owner_id(user)
    expired_ids = {d["process_id"] for d in docs if not _touch_owned(PROCESS_CACHE, d["process_id"], requester)}

    # 2. DB bağlamı + eşleşen hekimlerin kayıtlı poliçeleri
    ctx = await loop.run_in_executor(None, _load_merge_context, tenant_id)
    parties_preview = merge_parties(docs, ctx["client_rows"])
    matched_ids = sorted({
        p["match"]["client_id"] for p in parties_preview
        if p.get("match") and p["match"].get("client_id") is not None
    })
    known_policies: List[Dict[str, Any]] = []
    if matched_ids:
        known_policies = await loop.run_in_executor(None, _load_known_policies, matched_ids)

    # 3. Saf birleştirme
    draft, conflicts = build_draft(
        docs, ctx["client_rows"],
        known_policies=known_policies,
        known_courts=ctx["known_courts"],
        known_subjects=ctx.get("known_subjects"),
        known_specialties=ctx.get("known_specialties"),
    )

    # 3b. Zenginleştirme: kayıtlı dava değerleri adaylara katılır; esas_no/
    # mahkeme farkı yeni çelişki doğurabilir → hakem listesi yeniden kurulur
    # (kayıtlı değer de artık aday olduğundan hakem onu seçebilir).
    if case_row is not None:
        inject_case_candidates(draft["fields"], case_row)
        conflicts = detect_conflicts(draft["fields"])

    # 4. Katman 3 — hakem (yalnız çelişkide; hatası taslağı düşürmez)
    if conflicts:
        try:
            kararlar = await case_intake_analyzer.arbitrate_conflicts(
                conflicts, build_doc_summaries(docs)
            )
            unapplied = apply_arbitration(draft["fields"], kararlar)
            for karar in unapplied:
                draft["warnings"].append({
                    "code": "ARBITER_UNAPPLIED",
                    "message": (
                        f"Hakem kararı uygulanamadı ({karar.get('alan')}): seçilen değer "
                        "adaylar arasında bulunamadı — çoğunluk oyu sonucu korunuyor."
                    ),
                })
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Hakem çağrısı hatası: {e}")
            draft["warnings"].append({
                "code": "ARBITER_FAILED",
                "message": (
                    "Belgeler arası çelişki hakem tarafından çözülemedi — "
                    "çoğunluk oyu sonucu gösteriliyor, adayları kontrol edin."
                ),
            })

    # 4b. Yargı Birimi: mahkeme adından türetilir (hakem SONRASI — nihai mahkeme
    # değeri üzerinden; backfill script'iyle aynı kalıplar, tek kaynak).
    try:
        from services.judicial_unit import derive_judicial_unit

        court_value = draft["fields"].get("court", {}).get("value")
        ju = derive_judicial_unit(court_value) if court_value else None
        draft["fields"]["judicial_unit"] = {
            "value": ju,
            "agreement": None,
            "confidence": None,
            "candidates": [],
            "sources": [],
            **({"derived_from": "court"} if ju else {}),
        }
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE] Yargı birimi türetme hatası: {e}")

    # 4c. Zenginleştirme: nihai (hakem + türetme sonrası) değerler üzerinden
    # alan başına fill/confirm/conflict/keep durumu + taraf eşleme + dava özeti.
    draft["mode"] = "enrich" if case_row is not None else "new"
    draft["case"] = None
    if case_row is not None:
        annotate_enrich_status(draft["fields"], case_row)
        mark_existing_parties(draft["parties"], case_row.get("parties") or [])
        draft["case"] = {
            "id": case_row["id"],
            "tracking_no": case_row["tracking_no"],
            "esas_no": case_row["esas_no"],
            "court": case_row["court"],
            "status": case_row["status"],
            # Eşzamanlılık imzası — apply expected_updated_at olarak geri yollar
            "updated_at": case_row.get("updated_at"),
        }

    # 5. Tanıdık sorgu (çıkar çatışması) — taraf satırlarına iliştirilir
    try:
        queries = [
            {"name": p["name"], "tc_no": p.get("tc_no"), "party_type": p["party_type"]}
            for p in draft["parties"]
        ]
        check_results = check_parties(queries, ctx["client_rows"], ctx["party_rows"])
        for party, result in zip(draft["parties"], check_results, strict=True):
            party["check"] = {
                "conflict": result["conflict"],
                "matches": result["matches"][:5],
            }
            if result["conflict"]:
                draft["warnings"].append({
                    "code": "PARTY_CONFLICT",
                    "message": f"Tanıdık sorgu uyarısı: {party['name']} için çıkar çatışması riski — eşleşmeleri inceleyin.",
                })
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE] Tanıdık sorgu hatası (merge): {e}")

    # 6. Mükerrer dava kontrolü (zenginleştirme modunda anlamsız — hedef belli)
    if case_row is None:
        try:
            client_names = [p["name"] for p in draft["parties"] if p["party_type"] == "CLIENT"]
            other_names = [p["name"] for p in draft["parties"] if p["party_type"] != "CLIENT"]
            dup = await loop.run_in_executor(None, lambda: find_matching_case(
                esas_no=draft["fields"]["esas_no"]["value"],
                muvekkiller=client_names,
                belgede_gecen_isimler=other_names,
                mahkeme=draft["fields"]["court"]["value"],
            ))
            if dup:
                draft["duplicate_case"] = {
                    "id": dup["case_id"],
                    "tracking_no": dup["tracking_no"],
                    "esas_no": dup["esas_no"],
                    "court": dup["court"],
                    "score": dup["score"],
                    "confidence": dup["confidence"],
                }
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Mükerrer dava kontrolü hatası: {e}")

    # 7. Müvekkil geçmişi örüntüleri (düşük-güvenli ön-dolgu önerileri)
    if matched_ids:
        try:
            case_rows_by_client = await loop.run_in_executor(
                None, _load_client_case_rows, matched_ids
            )
            for client_id, case_rows in case_rows_by_client.items():
                priors = client_priors(case_rows)
                if priors:
                    draft["priors"][str(client_id)] = priors
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Müvekkil geçmişi örüntüsü hatası: {e}")

    # 8. Süresi dolmuş belgeleri işaretle
    if expired_ids:
        for doc_summary in draft["documents"]:
            if doc_summary["process_id"] in expired_ids:
                doc_summary["status"] = "expired"
        draft["warnings"].append({
            "code": "DOCUMENT_EXPIRED",
            "message": (
                f"{len(expired_ids)} belgenin işlem önbelleği süresi dolmuş — "
                "bu belgeler kaydetme adımında arşivlenemez, yeniden yüklenmeleri gerekir."
            ),
        })

    TechnicalLogger.log(
        "INFO",
        "[INTAKE] Merge tamamlandı",
        {
            "documents": len(docs),
            "parties": len(draft["parties"]),
            "policies": len(draft["policies"]),
            "conflicts": len(conflicts),
            "warnings": [w["code"] for w in draft["warnings"]],
            "mode": draft["mode"],
            "case_id": req.case_id,
        },
    )
    return draft


# =====================================================================
# Faz 4 — commit (+ Faz 7 apply ile paylaşılan yardımcılar)
# =====================================================================


async def _archive_intake_documents(
    documents: List[CommitDocumentIn],
    case_id: int,
    avukat_kodu: Optional[str],
    background_tasks: BackgroundTasks,
    user: dict,
    current_user_name: str,
    options: CommitOptions,
) -> List[Dict[str, Any]]:
    """Belge-başı best-effort arşiv döngüsü (karar 4) — commit + apply ortak.

    Sarmalayıcı BİLEREK geniş except Exception: confirm yolundaki GS
    UnicodeDecodeError arızası (ValueError alt sınıfı) dar except'leri
    deliyordu — tek belge hatası kalan belgeleri düşürmemeli. accept POP →
    PDF/A → kuyruk → cleanup; expired/failed izolasyonu yanıt satırında döner.
    """
    from services import document_pipeline

    loop = asyncio.get_running_loop()
    ham_folder = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
    islenmis_folder = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
    date_str = datetime.now().strftime("%Y-%m-%d")
    avukat_adi = document_pipeline.resolve_lawyer_name(avukat_kodu) if options.send_email else ""

    doc_results: List[Dict[str, Any]] = []
    for doc in documents:
        entry: Dict[str, Any] = {
            "process_id": doc.process_id,
            "status": "queued",
            "document_id": None,
            "error_ozet": None,
        }
        temp_path = None
        ham_source_path = None
        pdfa_temp_file = None
        try:
            try:
                temp_path, ham_source_path = await document_pipeline.accept_incoming_file(
                    doc.process_id, None, PROCESS_CACHE, owner=_owner_id(user)
                )
            except HTTPException:
                # accept_incoming_file cache girdisini POP eder; girişte yoksa /
                # dosya diskten silinmişse 400 fırlatır → bu belge süresi dolmuş.
                entry["status"] = "expired"
                entry["error_ozet"] = (
                    "İşlem önbelleği süresi dolmuş — belgeyi dava kartından yeniden yükleyin."
                )
                doc_results.append(entry)
                continue

            new_filename = sanitize_filename(doc.new_filename)
            original_filename = doc.original_filename or doc.new_filename
            ham_filename = f"{date_str}_{sanitize_filename(original_filename)}"

            # step_results: pipeline adımlarının serbest anahtarları yanıt
            # sözleşmesine sızmasın diye entry'den ayrı tutulur.
            step_results: Dict[str, Any] = {}
            timings: Dict[str, Any] = {}
            pdfa_temp_file, doc_id = await loop.run_in_executor(
                None,
                partial(
                    document_pipeline.convert_pdfa_and_queue_uploads,
                    background_tasks=background_tasks,
                    source_path=temp_path,
                    ham_filename=ham_filename,
                    ham_source_path=ham_source_path,
                    ham_folder=ham_folder,
                    islenmis_folder=islenmis_folder,
                    new_filename=new_filename,
                    original_filename=original_filename,
                    belge_turu_kodu=doc.belge_turu_kodu,
                    muvekkiller=[],
                    muvekkil_adi=doc.muvekkil_adi,
                    ai_ozet=doc.ai_ozet,
                    linked_case_id=case_id,
                    case_party_id=None,
                    avukat_kodu=avukat_kodu,
                    esas_no=doc.esas_no,
                    is_test_mode=False,
                    user=user,
                    current_user_name=current_user_name,
                    results=step_results,
                    timings=timings,
                ),
            )
            entry["document_id"] = doc_id
            # Faz 3-F: dönüşüm pending'e düştüyse belge kaydedildi ama arşivde
            # şimdilik orijinal duruyor — yanıt satırında görünür olsun
            # (status "queued" kalır: belge kaybolmadı, akış başarılı).
            if step_results.get("conversion_pending"):
                entry["conversion_pending"] = True
                entry["error_ozet"] = step_results.get("conversion_warning")

            if options.send_email:
                email_file_path = (
                    pdfa_temp_file
                    if (pdfa_temp_file and os.path.exists(pdfa_temp_file))
                    else temp_path
                )
                email_metadata = document_pipeline.build_email_metadata(
                    [], doc.muvekkil_adi, None, doc.belge_turu_kodu, None, avukat_adi, None
                )
                await document_pipeline.send_notification_email(
                    email_file_path=email_file_path,
                    new_filename=new_filename,
                    avukat_kodu=avukat_kodu,
                    email_metadata=email_metadata,
                    custom_to=options.email_to,
                    custom_cc=[],
                    custom_email_message=None,
                    custom_messages=None,
                    extra_temp_paths=[],
                    current_user_name=current_user_name,
                    doc_id=doc_id,
                    results=step_results,
                    timings=timings,
                )
                entry["email"] = step_results.get("email")

            document_pipeline.schedule_cleanup(
                background_tasks, temp_path, pdfa_temp_file, None, DOWNLOAD_CACHE,
                ham_source_path=ham_source_path,
            )
        except ConversionBusyError:
            # Faz 5-A (plan 5.2): dönüşüm kuyruğu dolu — sistem arızası değil,
            # ERROR üretilmez (WARNING'i semafor attı). Cache girdisi POP
            # edildiğinden bu belge için retry = dava kartından yeniden yükleme.
            entry["status"] = "failed"
            entry["error_ozet"] = (
                "Sistem şu anda meşgul, belge arşivlenmedi — birkaç dakika sonra "
                "dava kartından yeniden yükleyin."
            )
            safe_remove(pdfa_temp_file)
            safe_remove(temp_path)
            if ham_source_path and ham_source_path != temp_path:
                safe_remove(ham_source_path)
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            TechnicalLogger.log(
                "ERROR",
                f"[INTAKE-COMMIT] Belge arşivleme hatası [ID: {error_id}] "
                f"(case={case_id}, process={doc.process_id}): {e}",
            )
            entry["status"] = "failed"
            entry["error_ozet"] = (
                f"Belge arşivlenemedi (Hata: {error_id}) — dava kartından yeniden yükleyin."
            )
            # Cache'ten POP edilen dosyaların TTL sahibi artık yok — burada temizlenir.
            safe_remove(pdfa_temp_file)
            safe_remove(temp_path)
            if ham_source_path and ham_source_path != temp_path:
                safe_remove(ham_source_path)
        doc_results.append(entry)
    return doc_results


async def _feed_intake_policies(
    policies: List[CommitPolicyIn],
    case_id: int,
    current_user_name: str,
) -> Dict[str, Any]:
    """Poliçe beslemesi — best-effort (karar 5): hata dava kaydını GERİ ALMAZ.

    save_client_policies idempotent (dedupe = normalize police_no + dönem başı).
    """
    from managers import client_manager

    loop = asyncio.get_running_loop()
    policy_result: Dict[str, Any] = {"saved": 0, "skipped": 0}
    if not policies:
        return policy_result
    by_client: Dict[int, List[Dict[str, Any]]] = {}
    for pol in policies:
        by_client.setdefault(pol.client_id, []).append(pol.model_dump(exclude={"client_id"}))
    for cid, pol_list in by_client.items():
        try:
            saved_info = await loop.run_in_executor(
                None,
                partial(
                    client_manager.save_client_policies,
                    cid, pol_list, created_by=current_user_name,
                ),
            )
            policy_result["saved"] += saved_info["saved"]
            policy_result["skipped"] += saved_info["skipped"]
        except Exception as e:
            TechnicalLogger.log(
                "ERROR",
                f"[INTAKE-COMMIT] Poliçe beslemesi hatası (case={case_id}, client={cid}): {e}",
            )
            policy_result["error"] = (
                "Poliçelerin bir kısmı kaydedilemedi — müvekkil kartından elle ekleyebilirsiniz."
            )
    return policy_result


@router.post("/api/case-intake/commit")
async def commit_case_intake(
    req: CaseIntakeCommitRequest,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Tek "Kaydet": dava (atomik) + belge arşivleme + poliçe beslemesi.

    Karar 4: dava oluşturma transactional; belge arşivleme belge-başı
    best-effort — başarısız/TTL-dolmuş belge akışı öldürmez, yanıtta
    failed/expired döner. 409'da (duplicate tracking_no) HİÇBİR belge
    tüketilmemiştir — frontend'in tek otomatik retry'ı güvenlidir.
    """
    from managers import case_manager
    from services import document_pipeline

    loop = asyncio.get_running_loop()
    current_user_name = user.get("name") or user.get("preferred_username") or "Bilinmeyen"

    # 1. Dava — atomik. status sunucuda DERDEST'e zorlanır (karar 1 — istemciye
    # güvenme). Zorunlu alan eksikliği kaydı ENGELLEMEZ (kullanıcı kararı
    # 2026-07-31 rev.2): eksikler yanıtla döner, panelde uyarı olarak görünür.
    from required_fields import compute_missing_fields

    case_dict = req.case.model_dump()
    missing_fields = compute_missing_fields(case_dict, case_dict.get("parties"))
    case_dict["status"] = "DERDEST"
    case_result = await loop.run_in_executor(None, case_manager.add_case, case_dict)
    idempotent_reuse = False
    if case_result and case_result.get("error") == "duplicate_tracking_no":
        # Faz 3-D (plan 3.5): 409 artık nihai değil — yanıtı kaybolan önceki
        # commit'in KENDİ davasına çarpmış olabiliriz (çift tıklama / timeout
        # sonrası tekrar). Muhafazakâr eşleşme tutarsa mevcut dava idempotent
        # sonuç olarak döner; eski "sıra numarasını artırıp tekrar deneyin"
        # yolu bu senaryoda aynı davayı İKİNCİ kez açtırıyordu.
        match = await loop.run_in_executor(
            None, partial(case_manager.find_idempotent_commit_match, case_dict, tenant_id)
        )
        if match:
            idempotent_reuse = True
            case_result = match
            TechnicalLogger.log(
                "INFO",
                "[INTAKE-COMMIT] 409 idempotent çözüldü — mevcut dava döndürülüyor",
                {"case_id": match["id"], "tracking_no": match.get("tracking_no")},
            )
        else:
            # Gerçek çakışma (nihai): [TRACKING_NO_COLLISION] ERROR telemetrisi
            # Faz 3-D'de add_case'ten buraya taşındı (orada WARNING) — sayaç
            # önerisi hâlâ dolu numara üretiyorsa buradan görülür (2026-07-16).
            TechnicalLogger.log(
                "ERROR",
                "[TRACKING_NO_COLLISION] Önerilen ofis numarası zaten kayıtlı",
                details={"tracking_no": req.case.tracking_no},
            )
            raise HTTPException(
                status_code=409,
                detail=f"Bu ofis numarası zaten kayıtlı: {req.case.tracking_no}. "
                       "Sıra numarasını artırıp tekrar deneyin.",
            )
    if not case_result or case_result.get("error"):
        raise HTTPException(status_code=500, detail="Dava kaydedilemedi.")
    case_id = case_result["id"]

    # Avukat kodu davanın sorumlusundan BİR KEZ çözülür (dava az önce bizim
    # oluşturduğumuz — belge başına tenant sorgusu israf). Hata belge akışını
    # durdurmaz: kod boş kalır, arşivleme devam eder.
    avukat_kodu: Optional[str] = None
    try:
        avukat_kodu = await loop.run_in_executor(
            None, document_pipeline.validate_tenant_and_resolve_lawyer, case_id, user, None
        )
    except Exception as e:
        TechnicalLogger.log(
            "WARNING", f"[INTAKE-COMMIT] Avukat çözümü hatası (case={case_id}): {e}"
        )

    # 2. Belge-başı best-effort döngü (karar 4) — apply ile ortak yardımcı.
    # İdempotent yeniden kullanımda davada aynı stored_filename ile ZATEN
    # kayıtlı belgeler yeniden arşivlenmez (ilk commit arşivlemişti; retry'ın
    # cache girdileri çoğu kez tükenmiştir ve "expired" raporu yanıltıcı olur)
    # — mevcut belge id'siyle "queued" raporlanır. İlk commit'in yarım
    # bıraktığı belgeler normal döngüden geçer: cache'i yaşıyorsa arşivlenir.
    docs_to_archive = list(req.documents)
    reused_doc_entries: List[Dict[str, Any]] = []
    if idempotent_reuse and req.documents:
        existing_by_name = await loop.run_in_executor(
            None, case_manager.get_case_document_filenames, case_id
        )
        docs_to_archive = []
        for d in req.documents:
            try:
                lookup_name = sanitize_filename(d.new_filename)
            except HTTPException:
                # Arşiv döngüsü aynı adı aynı şekilde reddedecek — oraya bırak.
                docs_to_archive.append(d)
                continue
            existing_id = existing_by_name.get(lookup_name)
            if existing_id is not None:
                reused_doc_entries.append({
                    "process_id": d.process_id,
                    "status": "queued",
                    "document_id": existing_id,
                    "error_ozet": None,
                })
            else:
                docs_to_archive.append(d)

    doc_results = await _archive_intake_documents(
        docs_to_archive, case_id, avukat_kodu, background_tasks,
        user, current_user_name, req.options,
    )
    if reused_doc_entries:
        # Yanıt, isteğin belge sırasını korur (frontend satır eşlemesi).
        by_pid = {e["process_id"]: e for e in list(doc_results) + reused_doc_entries}
        doc_results = [by_pid[d.process_id] for d in req.documents if d.process_id in by_pid]

    # 3. Poliçe beslemesi — best-effort (karar 5) — apply ile ortak yardımcı.
    # (İdempotent yeniden kullanımda da güvenli: save_client_policies kendi
    # içinde dedupe eder — tekrar besleme "skipped" sayar.)
    policy_result = await _feed_intake_policies(req.policies, case_id, current_user_name)

    TechnicalLogger.log(
        "INFO",
        "[INTAKE-COMMIT] Commit tamamlandı",
        {
            "case_id": case_id,
            "tracking_no": case_result.get("tracking_no"),
            "documents": {
                s: sum(1 for d in doc_results if d["status"] == s)
                for s in ("queued", "failed", "expired")
            },
            "policies": policy_result,
        },
    )
    return {
        "case": {
            "id": case_id,
            "tracking_no": case_result.get("tracking_no"),
            # Yeniden kullanımda mevcut davanın gerçek durumu döner (yeni
            # kayıtta sunucu zorlaması DERDEST).
            "status": case_result.get("status") if idempotent_reuse else case_dict["status"],
            "missing_required_fields": missing_fields,
            # Faz 3-D: retry'ın mevcut davaya çözüldüğünün işareti (frontend
            # bilmeyen alanı yok sayar; teşhis ve gelecek UI mesajı için).
            "idempotent_reuse": idempotent_reuse,
        },
        "documents": doc_results,
        "policies": policy_result,
    }


# =====================================================================
# Faz 7 — apply (zenginleştirme modu)
# =====================================================================


@router.post("/api/case-intake/apply")
async def apply_case_intake(
    req: CaseIntakeApplyRequest,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Zenginleştirme modunun tek "Kaydet"i: MEVCUT davaya kısmi güncelleme.

    commit'ten farkı: dava oluşturmaz — yalnız kullanıcının tik'lediği alanlar
    uygulanır (exclude_unset; gönderilmeyen alan dokunulmaz, None silinir),
    taraflarda yalnız EKLEME yapılır, her değişiklik "intake-enrich: <belge>"
    imzalı CaseHistory'ye yazılır. Belge arşivleme + poliçe beslemesi commit'in
    belge-başı best-effort döngüsüyle birebir aynıdır.
    """
    from managers import case_manager
    from services import document_pipeline

    loop = asyncio.get_running_loop()
    current_user_name = user.get("name") or user.get("preferred_username") or "Bilinmeyen"

    # CaseHistory kaynak imzası (karar 2): "intake-enrich: <belge adı>".
    # Çok belgede ilk ikisi + sayaç; kolon sınırına (300) kırpılır.
    doc_names = [d.original_filename or d.new_filename for d in req.documents]
    source_sig = "intake-enrich"
    if doc_names:
        source_sig += f": {', '.join(doc_names[:2])}"
        if len(doc_names) > 2:
            source_sig += f" +{len(doc_names) - 2}"
    source_sig = source_sig[:300]

    # 1. Kısmi güncelleme + yalnız-EKLEME taraflar (tek transaction).
    # Bayat imza kontrolü bu adımın İÇİNDE, alan yazımından önce koşar —
    # 409'da hiçbir alan yazılmaz, belge arşivi (adım 3) hiç başlamadığından
    # PROCESS_CACHE girdileri de tüketilmez → frontend'in re-merge'ü güvenli.
    fields = req.fields.model_dump(exclude_unset=True)
    parties = [p.model_dump() for p in req.parties]
    result = await loop.run_in_executor(
        None,
        partial(
            case_manager.enrich_case, req.case_id, fields, parties,
            changed_by=current_user_name, source=source_sig, tenant_id=tenant_id,
            expected_updated_at=req.expected_updated_at,
        ),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Zenginleştirilecek dava bulunamadı.")
    if result.get("error") == "stale_case":
        raise HTTPException(
            status_code=409,
            detail="Dava bu ekran açıldıktan sonra güncellendi — "
                   "öneriler güncel değerlerle yeniden birleştirilecek.",
        )
    if result.get("error"):
        raise HTTPException(status_code=500, detail="Dava güncellenemedi.")

    # 2. Avukat kodu (commit ile aynı: hata belge akışını durdurmaz).
    avukat_kodu: Optional[str] = None
    try:
        avukat_kodu = await loop.run_in_executor(
            None, document_pipeline.validate_tenant_and_resolve_lawyer, req.case_id, user, None
        )
    except Exception as e:
        TechnicalLogger.log(
            "WARNING", f"[INTAKE-APPLY] Avukat çözümü hatası (case={req.case_id}): {e}"
        )

    # 3+4. Belge arşivleme + poliçe beslemesi — commit ile ortak yardımcılar.
    doc_results = await _archive_intake_documents(
        req.documents, req.case_id, avukat_kodu, background_tasks,
        user, current_user_name, req.options,
    )
    policy_result = await _feed_intake_policies(req.policies, req.case_id, current_user_name)

    TechnicalLogger.log(
        "INFO",
        "[INTAKE-APPLY] Zenginleştirme tamamlandı",
        {
            "case_id": req.case_id,
            "tracking_no": result.get("tracking_no"),
            "updated_fields": [u["field"] for u in result["updated_fields"]],
            "added_parties": result["added_parties"],
            "documents": {
                s: sum(1 for d in doc_results if d["status"] == s)
                for s in ("queued", "failed", "expired")
            },
            "policies": policy_result,
        },
    )
    return {
        "case": {"id": req.case_id, "tracking_no": result.get("tracking_no")},
        "updated_fields": result["updated_fields"],
        "added_parties": result["added_parties"],
        "documents": doc_results,
        "policies": policy_result,
    }


@router.post("/api/case-intake/keepalive")
def keepalive_case_intake(
    req: KeepaliveRequest,
    user: dict = Depends(get_current_user),
):
    """PROCESS_CACHE TTL tazeler; süresi dolanlar expired listesinde döner."""
    requester = _owner_id(user)
    refreshed = [pid for pid in req.process_ids if _touch_owned(PROCESS_CACHE, pid, requester)]
    expired = [pid for pid in req.process_ids if pid not in set(refreshed)]
    return {"refreshed": refreshed, "expired": expired}
