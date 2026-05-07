import logging
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

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
):
    """Yetki belgesi verilerinden .udf dosyası üretir ve döndürür."""
    try:
        from yetki_belgesi_generator import generate_yetki_belgesi_udf
        import unicodedata
        udf_bytes = generate_yetki_belgesi_udf(req.model_dump())
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
        raise HTTPException(status_code=500, detail="Yetki belgesi oluşturulamadı. Lütfen tekrar deneyin.")


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
        from sqlalchemy import or_
        case = db.query(models.Case).filter(
            models.Case.id == case_id,
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        ).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        q = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.case_id == case_id)
        )
        if party_id is not None:
            if party_id.lower() == "null":
                q = q.filter(models.CaseDocument.case_party_id.is_(None))
            else:
                try:
                    q = q.filter(models.CaseDocument.case_party_id == int(party_id))
                except ValueError:
                    raise HTTPException(status_code=400, detail="party_id sayı veya 'null' olmalı")

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


@router.get("/api/documents")
def get_all_documents(
    limit: int = 50,
    link_mode: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant),
):
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        q = (
            db.query(models.CaseDocument)
            .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
            .filter(or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None), models.CaseDocument.case_id.is_(None)))
        )
        if link_mode:
            q = q.filter(models.CaseDocument.link_mode == link_mode.upper())
        docs = q.order_by(models.CaseDocument.uploaded_at.desc()).limit(limit).all()
        return [
            {
                "id": d.id,
                "case_id": d.case_id,
                "original_filename": d.original_filename,
                "stored_filename": d.stored_filename,
                "belge_turu_kodu": d.belge_turu_kodu,
                "belge_turu_adi": d.belge_turu_adi,
                "muvekkil_adi": d.muvekkil_adi,
                "case_party_id": d.case_party_id,
                "case_party_name": d.case_party.name if d.case_party else None,
                "avukat_kodu": d.avukat_kodu,
                "esas_no": d.esas_no,
                "link_mode": d.link_mode,
                "uploaded_by": d.uploaded_by,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            }
            for d in docs
        ]
    finally:
        db.close()


@router.patch("/api/documents/{doc_id}/link")
def link_document_to_case(
    doc_id: int,
    payload: dict,
    tenant_id: str = Depends(get_current_tenant),
):
    """Bağlantısız bir belgeyi sonradan bir davaya bağlar. Body: { "case_id": 123 }"""
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        new_case_id = payload.get("case_id")
        if not new_case_id:
            raise HTTPException(status_code=400, detail="case_id gerekli")
        case = db.query(models.Case).filter(
            models.Case.id == new_case_id,
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        ).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")
        doc.case_id = new_case_id
        doc.link_mode = "LINKED"
        db.commit()
        return {"status": "success", "message": f"Belge #{doc_id} dava #{new_case_id}'ye bağlandı"}
    finally:
        db.close()


@router.get("/api/documents/{doc_id}/email-status")
def get_document_email_status(
    doc_id: int,
    _: str = Depends(get_current_tenant),
):
    """Belgenin e-posta gönderim durumunu döndürür."""
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
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
    tenant_id: str = Depends(get_current_tenant),
):
    """
    Belgeyi backend üzerinden SharePoint'ten proxy olarak indirir.
    Son kullanıcının Microsoft tenant üyesi olmasına gerek yoktur.
    """
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        if not doc.stored_filename:
            raise HTTPException(status_code=404, detail="Belge dosya adı bulunamadı")

        folder_name = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

        try:
            from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint
            content, content_type = download_file_from_sharepoint(folder_name, doc.stored_filename)
        except Exception as e:
            logger.error(f"SharePoint download error for doc {doc_id}: {e}")
            raise HTTPException(status_code=502, detail="Belge SharePoint'ten alınamadı")

        raw_name = doc.original_filename or doc.stored_filename
        safe_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii") or "belge"
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
        return Response(content=content, media_type=content_type, headers=headers)
    finally:
        db.close()


@router.patch("/api/documents/{doc_id}/party")
def assign_document_party(
    doc_id: int,
    payload: dict,
    tenant_id: str = Depends(get_current_tenant),
):
    """Belgenin müvekkil (case_party) atamasını değiştirir.
    Body: { "case_party_id": 123 }  → o tarafa ata
    Body: { "case_party_id": null } → dava geneline çek
    """
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
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
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        folder_name = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
        try:
            from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint
            content, _ = download_file_from_sharepoint(folder_name, doc.stored_filename)
        except Exception as e:
            logger.error(f"SharePoint download error for doc {doc_id}: {e}")
            raise HTTPException(status_code=502, detail="Belge SharePoint'ten alınamadı")

        suffix = Path(doc.stored_filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        sender_name = user.get("name") or user.get("preferred_username") or None
        metadata = {
            "muvekkil_adi": doc.muvekkil_adi or "Bilinmeyen Müvekkil",
            "belge_turu": doc.belge_turu_adi or "Belge",
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

        return {"success": success, "message": result.get("message", "")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend email error for doc {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="E-posta gönderilemedi")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        db.close()
