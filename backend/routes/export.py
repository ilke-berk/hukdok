"""
Hukukbot export API'si (docs/hukukbot-aktarim/PLAN.md §2).

Hukukbot'un hukdok arşivinden belge çekmesini sağlar. Aktarımın kaynağı
export_outbox tablosudur, case_documents DEĞİL (BULGULAR #1 — async SharePoint
upload yarışı). Outbox satırını açan hook Faz 3'te devreye girer; bu router
Faz 1'de altyapıyı kurar.

Kimlik doğrulama: X-API-Key header'ı (HUKDOK_EXPORT_API_KEY env). Router,
uygulamanın Azure AD auth dependency'sinin tamamen DIŞINDADIR. Ek katman
olarak /export host nginx'e hiç bağlanmaz — yalnızca iç Docker network'ünden
erişilir (BULGULAR #5, #11).
"""
import hmac
import logging
import os
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func

from database import SessionLocal
from file_utils import _normalize_doctype_code
import models

logger = logging.getLogger(__name__)


# ── Kimlik doğrulama ─────────────────────────────────────────────────────────

_weak_key_warned = False


def _key_is_weak(key: str) -> bool:
    """32 karakterden kısa veya 'dev-' önekli placeholder anahtarları zayıf sayar."""
    return len(key) < 32 or key.lower().startswith("dev-")


def require_export_api_key(x_api_key: Optional[str] = Header(default=None)):
    """X-API-Key header'ını HUKDOK_EXPORT_API_KEY env değeriyle karşılaştırır.

    Env tanımlı değilse export API kapalıdır (fail-closed): her istek 503 alır.
    Anahtar zayıfsa (kısa veya 'dev-' önekli) yalnızca DEV_MODE=true iken kabul
    edilir; prod'da yine 503 (fail-closed). Karşılaştırma sabit zamanlıdır
    (timing attack'a karşı).
    """
    global _weak_key_warned
    expected = os.getenv("HUKDOK_EXPORT_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Export API yapılandırılmamış")
    if _key_is_weak(expected) and os.getenv("DEV_MODE", "").lower() != "true":
        if not _weak_key_warned:
            logger.critical(
                "HUKDOK_EXPORT_API_KEY zayıf (kısa veya 'dev-' önekli) — export API "
                "kapatıldı. Güçlü rastgele bir anahtar tanımlayın (örn. openssl rand -hex 32)."
            )
            _weak_key_warned = True
        raise HTTPException(status_code=503, detail="Export API anahtarı zayıf yapılandırılmış")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik API anahtarı")


router = APIRouter(prefix="/export", dependencies=[Depends(require_export_api_key)])


# ── Filtre yardımcıları ──────────────────────────────────────────────────────

def get_type_allowlist() -> set[str]:
    """Env'deki tür allowlist'ini normalize edilmiş kod kümesi olarak döndürür.

    HUKDOK_EXPORT_TYPES virgülle ayrılmış kısa kodlar içerir (örn.
    "GEREKCELI-KRR,ARA-KRR,BILIRKISI-RPR"); aday liste için bkz.
    docs/hukukbot-aktarim/KOD_LISTESI.md. Boş/tanımsız ise tür filtresi
    uygulanmaz (tüm türler geçer). DB'de pad'li ve kısa kodlar karışık
    olduğundan karşılaştırma her zaman normalize edilerek yapılır (BULGULAR #7).

    Faz 3'teki outbox hook'u da aynı allowlist'i bu fonksiyondan okumalıdır.
    """
    raw = os.getenv("HUKDOK_EXPORT_TYPES", "")
    return {_normalize_doctype_code(c) for c in raw.split(",") if c.strip()}


def _doc_passes_filters(doc, allowlist: set[str], types_filter: set[str]) -> bool:
    """Belgenin export filtrelerinden geçip geçmediğini söyler.

    - link_mode != "TEST" (BULGULAR #3; UNLINKED bilinçli olarak dahildir)
    - sharepoint_url dolu olmalı (outbox tabanlı listede zaten garanti, savunma amaçlı)
    - Kendisi veya davası soft-delete edilmiş belge elenir; case_id=None (UNLINKED) dahil kalır.
      Filtre dinamiktir: kayıt restore edilirse belgeleri tekrar akar — istenen davranış.
    - conversion_status NULL olmalı (Faz 3-F): pending/failed belgelerin arşiv
      kopyası PDF değil orijinaldir (ör. .udf) — ingest'e açılmaz. Gece job'ı
      dönüşümü tamamlayınca statü NULL'lanır ve belge akmaya başlar.
    - Tür, env allowlist'ine VE istekteki types= filtresine uymalı (normalize edilerek)
    """
    if doc is None or doc.link_mode == "TEST" or not doc.sharepoint_url:
        return False
    if doc.conversion_status is not None:
        return False
    if doc.deleted_at is not None:
        return False
    if doc.case is not None and doc.case.deleted_at is not None:
        return False
    code = _normalize_doctype_code(doc.belge_turu_kodu or "")
    if allowlist and code not in allowlist:
        return False
    if types_filter and code not in types_filter:
        return False
    return True


def _summary(outbox_row, doc) -> dict:
    return {
        "outbox_id": outbox_row.id,
        "document_id": outbox_row.document_id,
        "status": outbox_row.status,
        "attempts": outbox_row.attempts,
        "created_at": outbox_row.created_at.isoformat() if outbox_row.created_at else None,
        "belge_turu_kodu": doc.belge_turu_kodu,
        "belge_turu_adi": doc.belge_turu_adi,
        "tracking_no": doc.case.tracking_no if doc.case else None,
        "stored_filename": doc.stored_filename,
    }


# ── Endpoint'ler ─────────────────────────────────────────────────────────────

@router.get("/documents")
def list_export_documents(
    status: Optional[str] = Query(default="pending"),
    after_id: Optional[int] = Query(default=None),
    types: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Aktarılabilir belgeleri OUTBOX üzerinden listeler.

    Normal reconcile status=pending ile sorar; cursor YOKTUR (BULGULAR #9 —
    cursor ya sessiz kayıp ya kuyruk kilidi üretir). after_id yalnızca
    backfill modu içindir (outbox id'sine göre). Tür filtresi Python'da
    normalize edilerek uygulanır — SQL IN kullanılamaz (BULGULAR #7).
    """
    allowlist = get_type_allowlist()
    types_filter = {_normalize_doctype_code(t) for t in types.split(",") if t.strip()} if types else set()

    db = SessionLocal()
    try:
        q = (
            db.query(models.ExportOutbox)
            .options(joinedload(models.ExportOutbox.document).joinedload(models.CaseDocument.case))
            .order_by(models.ExportOutbox.id.asc())
        )
        if status:
            q = q.filter(models.ExportOutbox.status == status)
        if after_id is not None:
            q = q.filter(models.ExportOutbox.id > after_id)

        items = []
        # Tür karşılaştırması SQL'e inemediği için limit Python tarafında
        # uygulanır; satırlar id sırasıyla parça parça çekilir.
        for row in q.yield_per(200):
            doc = row.document
            if not _doc_passes_filters(doc, allowlist, types_filter):
                continue
            items.append(_summary(row, doc))
            if len(items) >= limit:
                break

        return {"items": items, "count": len(items)}
    finally:
        db.close()


@router.get("/documents/{document_id}")
def get_export_document(document_id: int):
    """Tek belgenin aktarım metadata'sını döndürür (belge id'siyle)."""
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        if doc.deleted_at is not None or (doc.case is not None and doc.case.deleted_at is not None):
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        # Faz 3-F: dönüşümü tamamlanmamış belge export yüzeyinde yok sayılır
        # (arşiv kopyası PDF değil — liste zaten filtreler, bu savunma katmanı).
        if doc.conversion_status is not None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        outbox = (
            db.query(models.ExportOutbox)
            .filter(models.ExportOutbox.document_id == document_id)
            .first()
        )
        case = doc.case
        return {
            "document_id": doc.id,
            "outbox_id": outbox.id if outbox else None,
            "outbox_status": outbox.status if outbox else None,
            "belge_turu_kodu": doc.belge_turu_kodu,
            "belge_turu_adi": doc.belge_turu_adi,
            "ai_summary": doc.ai_summary,
            "esas_no": doc.esas_no or (case.esas_no if case else None),
            "muvekkil_adi": doc.muvekkil_adi or (doc.case_party.name if doc.case_party else None),
            "avukat_kodu": doc.avukat_kodu,
            "link_mode": doc.link_mode,
            "tracking_no": case.tracking_no if case else None,
            "case": {
                "id": case.id,
                "tracking_no": case.tracking_no,
                "esas_no": case.esas_no,
                "court": case.court,
                "subject": case.subject,
                "status": case.status,
            } if case else None,
            "sharepoint_url": doc.sharepoint_url,
            "stored_filename": doc.stored_filename,
            "original_filename": doc.original_filename,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        }
    finally:
        db.close()


@router.get("/documents/{document_id}/file")
def download_export_document(document_id: int):
    """Belge PDF'ini SharePoint'ten indirip döndürür.

    routes/documents.py:239'daki akışın aynısı — Graph kimlik bilgileri
    hukdok'ta kalır, hukukbot yalnızca bu endpoint'i görür. Upload'ı hiç
    tamamlanmamış (sharepoint_url NULL) kayıtlar 404 alır (BULGULAR #3).
    """
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        if doc.deleted_at is not None or (doc.case is not None and doc.case.deleted_at is not None):
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        # Faz 3-F: dönüşümü tamamlanmamış belgenin arşiv kopyası PDF değil,
        # orijinaldir (ör. .udf) — hukukbot'a dosya olarak da verilmez.
        if doc.conversion_status is not None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        if not doc.sharepoint_url or not doc.stored_filename:
            raise HTTPException(status_code=404, detail="Belge SharePoint'e yüklenmemiş")

        folder_name = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
        stored_filename = str(doc.stored_filename)
        try:
            from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint
            content, content_type = download_file_from_sharepoint(folder_name, stored_filename)
        except Exception as e:
            logger.error(f"Export SharePoint download error for doc {document_id}: {e}")
            raise HTTPException(status_code=502, detail="Belge SharePoint'ten alınamadı") from e

        safe_name = (
            unicodedata.normalize("NFKD", stored_filename)
            .encode("ascii", "ignore")
            .decode("ascii")
            or "belge"
        )
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
        return Response(content=content, media_type=content_type or "application/octet-stream", headers=headers)
    finally:
        db.close()


class NackPayload(BaseModel):
    reason: str = ""


@router.post("/outbox/{outbox_id}/ack")
def ack_outbox(outbox_id: int):
    """Hukukbot belgeyi başarıyla işleyince çağırır — satır 'delivered' olur.

    Idempotent: zaten delivered olan satırda delivered_at değişmez.
    """
    db = SessionLocal()
    try:
        row = db.query(models.ExportOutbox).filter(models.ExportOutbox.id == outbox_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Outbox kaydı bulunamadı")
        if row.status != "delivered":
            row.status = "delivered"
            row.delivered_at = func.now()
            row.nack_reason = None
            db.commit()
            db.refresh(row)
        return {"outbox_id": row.id, "status": row.status}
    finally:
        db.close()


@router.post("/outbox/{outbox_id}/nack")
def nack_outbox(outbox_id: int, payload: NackPayload):
    """Hukukbot N başarısız denemeden sonra çağırır (BULGULAR #9).

    Satır 'failed' olur, pending sorgusundan düşer ve manuel incelemeye kalır.
    """
    db = SessionLocal()
    try:
        row = db.query(models.ExportOutbox).filter(models.ExportOutbox.id == outbox_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Outbox kaydı bulunamadı")
        row.status = "failed"
        row.attempts = (row.attempts or 0) + 1
        row.nack_reason = payload.reason or None
        db.commit()
        return {"outbox_id": row.id, "status": row.status, "attempts": row.attempts}
    finally:
        db.close()
