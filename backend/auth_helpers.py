"""Tenant izolasyonu için ortak yardımcı fonksiyonlar.

`tenant_id IS NULL` kayıtları "paylaşılan/legacy" olarak değerlendirilir ve her tenant
için görünür olur. Yeni eklenen kayıtlar oluşturucu tenant ile damgalanır.
"""
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models


def tenant_filter_clause(model, tenant_id: str):
    """`tenant_id == X OR tenant_id IS NULL` clause'u — NULL = paylaşılan legacy."""
    return or_(model.tenant_id == tenant_id, model.tenant_id.is_(None))


def get_tenant_owned_case(db: Session, case_id: int, tenant_id: str):
    """Davayı yalnızca istek sahibi tenant'a (veya legacy NULL'a) ait ise döndürür."""
    return (
        db.query(models.Case)
        .filter(
            models.Case.id == case_id,
            tenant_filter_clause(models.Case, tenant_id),
        )
        .first()
    )


def get_tenant_owned_hearing(db: Session, hearing_id: int, tenant_id: str):
    """Duruşmayı, bağlı olduğu davanın tenant'ı eşleşiyorsa döndürür."""
    return (
        db.query(models.HearingDate)
        .join(models.Case, models.HearingDate.case_id == models.Case.id)
        .filter(
            models.HearingDate.id == hearing_id,
            tenant_filter_clause(models.Case, tenant_id),
        )
        .first()
    )


def get_tenant_owned_document(
    db: Session,
    doc_id: int,
    tenant_id: str,
    user: Optional[dict] = None,
):
    """Belge → dava → tenant zincirini doğrular.

    UNLINKED/TEST belgeler (case_id IS NULL) için yalnızca yükleyen kullanıcı
    erişebilir; bu sayede başka tenant'taki bir kullanıcı doc_id enumeration ile
    bağlantısız belgelere ulaşamaz.
    """
    doc = (
        db.query(models.CaseDocument)
        .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
        .filter(
            models.CaseDocument.id == doc_id,
            or_(
                models.Case.tenant_id == tenant_id,
                models.Case.tenant_id.is_(None),
                models.CaseDocument.case_id.is_(None),
            ),
        )
        .first()
    )
    if doc is None:
        return None

    # case_id NULL → yalnızca yükleyen sahip kabul edilir
    if doc.case_id is None:
        if not user:
            return None
        upn = (user.get("preferred_username") or user.get("upn") or "").lower()
        uploader = (doc.uploaded_by_email or "").lower()
        if not upn or not uploader or upn != uploader:
            return None

    return doc


def get_tenant_owned_client(db: Session, client_id: int, tenant_id: str):
    """Müvekkili yalnızca istek sahibi tenant'a (veya legacy NULL'a) ait ise döndürür."""
    return (
        db.query(models.Client)
        .filter(
            models.Client.id == client_id,
            tenant_filter_clause(models.Client, tenant_id),
        )
        .first()
    )
