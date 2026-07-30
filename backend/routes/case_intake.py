"""Otonom dava açma — case intake route'ları (Faz 2 + Faz 3).

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
"""
import asyncio
import hashlib
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from auth_helpers import tenant_filter_clause
from dependencies import get_current_tenant, get_current_user
from file_utils import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    safe_remove,
    validate_file_type,
)
from managers.log_manager import TechnicalLogger
from routes.processing import PROCESS_CACHE, _cleanup_process_cache
from schemas_intake import CaseIntakeMergeRequest, KeepaliveRequest

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


# =====================================================================
# Faz 3 — merge + keepalive
# =====================================================================


def _load_merge_context(tenant_id: str) -> Dict[str, Any]:
    """Merge için DB bağlamı: cariler, geçmiş dosya tarafları, bilinen mahkemeler.

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
        return {"client_rows": client_rows, "party_rows": party_rows, "known_courts": known_courts}
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
    from party_check import check_parties
    from services.case_intake import (
        apply_arbitration,
        build_doc_summaries,
        build_draft,
        client_priors,
        merge_parties,
    )

    loop = asyncio.get_running_loop()
    docs = [d.model_dump() for d in req.documents]

    # 1. Keepalive: listelenen tüm process_id'lerin TTL'i tazelenir; süresi
    #    dolmuş belge birleştirmeye girer ama taslakta expired işaretlenir
    #    (commit adımı o belgeyi arşivleyemeyecek — kullanıcı bilgilendirilir).
    expired_ids = {d["process_id"] for d in docs if not PROCESS_CACHE.touch(d["process_id"])}

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
    )

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

    # 6. Mükerrer dava kontrolü
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
        },
    )
    return draft


@router.post("/api/case-intake/keepalive")
def keepalive_case_intake(
    req: KeepaliveRequest,
    user: dict = Depends(get_current_user),
):
    """PROCESS_CACHE TTL tazeler; süresi dolanlar expired listesinde döner."""
    refreshed = [pid for pid in req.process_ids if PROCESS_CACHE.touch(pid)]
    expired = [pid for pid in req.process_ids if pid not in set(refreshed)]
    return {"refreshed": refreshed, "expired": expired}
