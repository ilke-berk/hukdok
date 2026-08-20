"""Belge listeleme/indirme/silme, taraf-belge bağı ve yetki belgesi UDF üretimi.

`/api/documents*`, `/api/cases/{case_id}/documents` ve `/api/yetki-belgesi/udf`
route'ları; `api.py` include_router ile bağlanır. Dış bağımlılıklar fonksiyon içinde
lazy import edilir: SharePoint Graph (indirme), `email_sender` (bildirimi yeniden
gönderme), `yetki_belgesi_generator` (UDF). Silme SOFT'tur — SharePoint arşiv kopyası
silinmez.
"""
import logging
import mimetypes
import os
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from auth_helpers import get_tenant_owned_document, tenant_filter_clause
from dependencies import get_current_user, get_current_tenant
from database import SessionLocal
import models

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Yetki Belgesi UDF ─────────────────────────────────────────────────────────

class YetkiBelgesiAvukat(BaseModel):
    ad: str
    tc: str = ""
    sicil: str = ""
    address: str = ""

class YetkiBelgesiMuvekkil(BaseModel):
    ad: str
    adres: str = ""
    il: str = ""
    tc_vergi: str = ""
    client_type: str = "Individual"

class YetkiBelgesiDayanak(BaseModel):
    noterlik: str = ""
    tarih: str = ""
    yevmiye: str = ""

class YetkiBelgesiRequest(BaseModel):
    veren: YetkiBelgesiAvukat
    yetkililar: List[YetkiBelgesiAvukat]
    buro_adres: str = ""
    muvekkil: YetkiBelgesiMuvekkil
    dayanak: YetkiBelgesiDayanak
    kapsam: str = "İlgili Vekaletnamedeki yetkilerin tamamı"


@router.post("/api/yetki-belgesi/udf")
def create_yetki_belgesi_udf(
    req: YetkiBelgesiRequest,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Yetki belgesi verilerinden .udf dosyası üretir ve döndürür."""
    try:
        from yetki_belgesi_generator import generate_yetki_belgesi_udf
        import unicodedata
        udf_bytes = generate_yetki_belgesi_udf(req.model_dump())
        actor = user.get("preferred_username") or user.get("email") or user.get("oid") or "unknown"
        logger.info(
            f"Yetki belgesi UDF üretildi: actor={actor} tenant={tenant_id} "
            f"muvekkil={req.muvekkil.ad!r} veren={req.veren.ad!r} "
            f"yetkili_sayisi={len(req.yetkililar)}"
        )
        # HTTP header latin-1 zorunluluğu — Türkçe karakterleri ASCII'ye dönüştür
        raw_name = req.muvekkil.ad[:20].replace(" ", "_")
        safe_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
        safe_name = safe_name or "belge"
        filename = f"yetki_belgesi_{safe_name}.udf"
        return Response(
            content=udf_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Yetki belgesi UDF üretim hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Yetki belgesi oluşturulamadı. Lütfen tekrar deneyin.") from e


@router.get("/api/cases/{case_id}/documents")
def get_case_documents(
    case_id: int,
    party_id: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Bir davaya ait belgeleri listeler.
    - party_id filtresi verilmezse → tüm belgeler
    - party_id=null → sadece dava geneli belgeler (case_party_id IS NULL)
    - party_id=123 → sadece o tarafa ait belgeler
    """
    db = SessionLocal()
    try:
        from auth_helpers import get_tenant_owned_case
        case = get_tenant_owned_case(db, case_id, tenant_id)
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        q = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.case_id == case_id)
            .filter(models.CaseDocument.deleted_at.is_(None))
        )
        if party_id is not None:
            if party_id.lower() == "null":
                q = q.filter(models.CaseDocument.case_party_id.is_(None))
            else:
                try:
                    q = q.filter(models.CaseDocument.case_party_id == int(party_id))
                except ValueError:
                    raise HTTPException(status_code=400, detail="party_id sayı veya 'null' olmalı") from None

        docs = q.order_by(models.CaseDocument.uploaded_at.desc()).all()

        def _party_name(d):
            if d.case_party:
                return d.case_party.name
            return None

        return [
            {
                "id": d.id,
                "case_id": d.case_id,
                "original_filename": d.original_filename,
                "stored_filename": d.stored_filename,
                "belge_turu_kodu": d.belge_turu_kodu,
                "belge_turu_adi": d.belge_turu_adi,
                "ai_summary": d.ai_summary,
                "muvekkil_adi": d.muvekkil_adi,
                "case_party_id": d.case_party_id,
                "case_party_name": _party_name(d),
                "avukat_kodu": d.avukat_kodu,
                "esas_no": d.esas_no,
                "link_mode": d.link_mode,
                "uploaded_by": d.uploaded_by,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                "email_sent": d.email_sent,
                "email_error": d.email_error,
            }
            for d in docs
        ]
    finally:
        db.close()


@router.get("/api/documents/recent")
def get_recent_documents(
    since_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    tenant_id: str = Depends(get_current_tenant),
):
    """Avukat panosunun "Yeni İşlenen" akışı: son N saatte işlenmiş belgeler.

    G077 ile kaldırılan `GET /api/documents` ucunun DEVAMI DEĞİLDİR: o uç
    bağlantısız belgeleri bağlamak içindi ve diriltilmiyor. Buranın tek işi
    dava bağlamı OLAN belgeleri kronolojik akış olarak vermektir:

    - `case_id IS NULL` (TEST/UNLINKED) satırlar hiç dönmez → inner join.
      Kimlik (`user`) bağımlılığı bu yüzden gerekmez: sahiplik kuralı yalnız
      bağlantısız belgeler içindi, onlar zaten kapsam dışı. Kimlik doğrulaması
      `get_current_tenant` zincirinde (get_current_user) yapılır.
    - Yetki kuralı `auth_helpers.get_tenant_owned_document` ile AYNI: davanın
      tenant'ı eşleşmeli (NULL = paylaşılan legacy havuz), silinmiş dava ve
      silinmiş belge dönmez.

    `email_sent`/`email_error` yalnızca OKUNUR — bu uç mail göndermez, mevcut
    gönderim davranışını değiştirmez (kullanıcı kararı: durum panoda görünsün).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    db = SessionLocal()
    try:
        rows = (
            db.query(models.CaseDocument, models.Case)
            .join(models.Case, models.CaseDocument.case_id == models.Case.id)
            .options(joinedload(models.CaseDocument.case_party))
            .filter(
                models.CaseDocument.deleted_at.is_(None),
                models.CaseDocument.uploaded_at >= cutoff,
                models.Case.deleted_at.is_(None),
                tenant_filter_clause(models.Case, tenant_id),
            )
            .order_by(models.CaseDocument.uploaded_at.desc(), models.CaseDocument.id.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": d.id,
                "case_id": d.case_id,
                "tracking_no": c.tracking_no,
                # Belgede geçen esas no önce; yoksa davanın güncel esas'ı
                # (cases.esas_no türetilmiştir — case_esas_numbers'tan senkronlanır).
                "esas_no": d.esas_no or c.esas_no,
                "original_filename": d.original_filename,
                "belge_turu_kodu": d.belge_turu_kodu,
                "belge_turu_adi": d.belge_turu_adi,
                "case_party_name": d.case_party.name if d.case_party else None,
                "muvekkil_adi": (d.case_party.name if d.case_party else None) or d.muvekkil_adi,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                "uploaded_by": d.uploaded_by,
                "email_sent": d.email_sent,
                "email_error": d.email_error,
            }
            for d, c in rows
        ]
    finally:
        db.close()


@router.delete("/api/documents/{doc_id}")
def api_delete_document(
    doc_id: int,
    reason: str = Query(..., min_length=3, max_length=500),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Soft-delete: kayıt DB'de kalır, listelerden gizlenir, admin geri alabilir.

    Dava/müvekkil silme kalıbının (routes/cases.py) belge karşılığı. SharePoint
    arşiv kopyasına dokunulmaz. Gerekçe zorunlu (query param — DELETE body bazı
    proxy'lerde düşer). get_tenant_owned_document silinmişi görmez → çifte silme
    doğal 404.
    """
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        doc.deleted_at = func.now()
        doc.deleted_by = (
            user.get("preferred_username") or user.get("upn") or user.get("email") or "Unknown"
        )
        doc.delete_reason = reason.strip()
        db.commit()
        logger.info(
            f"Belge soft-delete: id={doc_id} file={doc.stored_filename!r} "
            f"case_id={doc.case_id} by={doc.deleted_by}"
        )
        return {"status": "success", "message": "Belge arşive taşındı"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Belge silme hatası ({doc_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Belge silinemedi. Lütfen tekrar deneyin.") from e
    finally:
        db.close()


@router.get("/api/documents/{doc_id}/email-status")
def get_document_email_status(
    doc_id: int,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Belgenin e-posta gönderim durumunu döndürür."""
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        return {
            "doc_id": doc_id,
            "email_sent": doc.email_sent,
            "email_error": doc.email_error,
        }
    finally:
        db.close()


@router.get("/api/documents/{doc_id}/download")
def download_document(
    doc_id: int,
    inline: bool = False,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """
    Belgeyi backend üzerinden SharePoint'ten proxy olarak indirir.
    Son kullanıcının Microsoft tenant üyesi olmasına gerek yoktur.

    inline=True ile çağrılırsa tarayıcıda görüntülenebilir tipte (PDF/resim vb.)
    ve `Content-Disposition: inline` ile döner — diske indirme yerine okuma için.
    """
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        if not doc.stored_filename:
            raise HTTPException(status_code=404, detail="Belge dosya adı bulunamadı")

        folder_name = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

        try:
            from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint
            content, _ = download_file_from_sharepoint(folder_name, doc.stored_filename)
        except Exception as e:
            logger.error(f"SharePoint download error for doc {doc_id}: {e}")
            raise HTTPException(status_code=502, detail="Belge SharePoint'ten alınamadı") from e

        raw_name = doc.original_filename or doc.stored_filename
        safe_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii") or "belge"

        if inline:
            # Tarayıcıda okuma için: doğru MIME tipi + inline disposition.
            media_type = mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
            disposition = "inline"
        else:
            media_type = "application/octet-stream"
            disposition = "attachment"

        headers = {"Content-Disposition": f'{disposition}; filename="{safe_name}"'}
        return Response(content=content, media_type=media_type, headers=headers)
    finally:
        db.close()


@router.patch("/api/documents/{doc_id}/party")
def assign_document_party(
    doc_id: int,
    payload: dict,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Belgenin müvekkil (case_party) atamasını değiştirir.
    Body: { "case_party_id": 123 }  → o tarafa ata
    Body: { "case_party_id": null } → dava geneline çek
    """
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        # payload'da anahtar yoksa hata ver; null kesin olarak kabul edilir
        if "case_party_id" not in payload:
            raise HTTPException(status_code=400, detail="case_party_id alanı gerekli (null gönderilebilir)")

        new_party_id = payload["case_party_id"]

        if new_party_id is not None:
            party = db.query(models.CaseParty).filter(
                models.CaseParty.id == new_party_id,
                models.CaseParty.case_id == doc.case_id,
            ).first()
            if not party:
                raise HTTPException(status_code=404, detail="Bu davaya ait taraf bulunamadı")

        doc.case_party_id = new_party_id
        db.commit()

        party_name = None
        if new_party_id:
            party = db.query(models.CaseParty).filter(models.CaseParty.id == new_party_id).first()
            party_name = party.name if party else None

        logger.info(f"Document #{doc_id} party updated → {new_party_id} ({party_name})")
        return {"status": "success", "case_party_id": new_party_id, "case_party_name": party_name}
    finally:
        db.close()


class ResendEmailPayload(BaseModel):
    to: List[str]
    cc: List[str] = []
    message: Optional[str] = None
    messages: Optional[Dict[str, str]] = None


@router.post("/api/documents/{doc_id}/resend-email")
def resend_document_email(
    doc_id: int,
    payload: ResendEmailPayload,
    tenant_id: str = Depends(get_current_tenant),
    user: dict = Depends(get_current_user),
):
    """Mevcut belgeyi SharePoint'ten indirip yeniden e-posta gönderir."""
    if not payload.to:
        raise HTTPException(status_code=400, detail="En az bir alıcı gerekli")

    db = SessionLocal()
    tmp_path = None
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        folder_name = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
        try:
            from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint
            content, _ = download_file_from_sharepoint(folder_name, doc.stored_filename)
        except Exception as e:
            logger.error(f"SharePoint download error for doc {doc_id}: {e}")
            raise HTTPException(status_code=502, detail="Belge SharePoint'ten alınamadı") from e

        suffix = Path(doc.stored_filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        sender_name = user.get("name") or user.get("preferred_username") or None
        # Belge türünü koddan taze çöz: eski kayıtlarda belge_turu_adi'ye ham kod
        # (örn. "ARA-KRR") sızmış olabilir; koddan çözüm tam adı ("Ara Karar") verir.
        from file_utils import get_doctype_label
        belge_turu = get_doctype_label(doc.belge_turu_kodu) or doc.belge_turu_adi or "Belge"
        metadata = {
            "muvekkil_adi": doc.muvekkil_adi or "Bilinmeyen Müvekkil",
            "belge_turu": belge_turu,
            "tarih": "",
        }

        from email_sender import send_document_notification
        result = send_document_notification(
            avukat_kodu=doc.avukat_kodu,
            filename=doc.original_filename or doc.stored_filename,
            pdf_path=tmp_path,
            metadata=metadata,
            custom_to=payload.to,
            custom_cc=payload.cc,
            custom_message=payload.message,
            custom_messages=payload.messages,
            sender_name=sender_name,
        )

        success = result.get("success", False)
        doc.email_sent = success
        doc.email_error = None if success else result.get("message", "Bilinmeyen hata")
        db.commit()

        if not success:
            raise HTTPException(status_code=422, detail=result.get("message", "E-posta gönderilemedi"))
        return {"success": True, "message": result.get("message", "")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend email error for doc {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="E-posta gönderilemedi") from e
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        db.close()
