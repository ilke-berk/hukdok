import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from database import SessionLocal
import models

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/cases/{case_id}/documents")
def get_case_documents(
    case_id: int,
    party_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Bir davaya ait belgeleri listeler.
    - party_id filtresi verilmezse → tüm belgeler
    - party_id=null → sadece dava geneli belgeler (case_party_id IS NULL)
    - party_id=123 → sadece o tarafa ait belgeler
    """
    db = SessionLocal()
    try:
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
            }
            for d in docs
        ]
    finally:
        db.close()


@router.get("/api/documents")
def get_all_documents(
    limit: int = 50,
    link_mode: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        q = db.query(models.CaseDocument)
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
    user: dict = Depends(get_current_user),
):
    """Bağlantısız bir belgeyi sonradan bir davaya bağlar. Body: { "case_id": 123 }"""
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        new_case_id = payload.get("case_id")
        if not new_case_id:
            raise HTTPException(status_code=400, detail="case_id gerekli")
        case = db.query(models.Case).filter(models.Case.id == new_case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")
        doc.case_id = new_case_id
        doc.link_mode = "LINKED"
        db.commit()
        return {"status": "success", "message": f"Belge #{doc_id} dava #{new_case_id}'ye bağlandı"}
    finally:
        db.close()
