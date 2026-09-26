"""Davaya tarihli, yazanı belli notlar (G214) — `/api/cases/{case_id}/notes*`.

Sözleşme SABİT (G215 frontend paneli buna göre paralel yazıldı):

* `GET    /api/cases/{case_id}/notes`            → 200, en yeni üstte, silinmişler hariç
* `POST   /api/cases/{case_id}/notes`            → 201 + tek not; gövde `{"body": str}`,
  trim sonrası 1..5000 karakter, aksi 422 (`schemas.CaseNoteCreate`)
* `DELETE /api/cases/{case_id}/notes/{note_id}`  → 204 (soft-delete, `deleted_at`);
  yazan değil ve yönetici değil → 403; not bu davada yok / silinmiş → 404

Dava görünürlüğü `auth_helpers.get_tenant_owned_case`'ten geçer (paylaşımlı havuz:
`tenant_id == X OR IS NULL`, soft-silinmiş dava görünmez) → görünmeyen davada TÜM
uçlar 404. Not satırı: `{id, body, author_name, author_email, created_at, can_delete}`;
`created_at` UTC ofsetli ISO8601.

Yazan kimliği token'dan ÜÇLÜ claim fallback'i ile okunur (`preferred_username | upn |
email`, küçük harf — `services.notifications.normalize_email`); ad `name` claim'i.
Yönetici tespiti `routes.config.require_admin`'in KENDİSİNE sorulur (ADMIN_EMAILS
kuralı tek yerde kalsın). `cases.notes` ("Genel not") bu modülün konusu DEĞİL.
"""
import datetime as dt
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from auth_helpers import get_tenant_owned_case
from database import get_db
from dependencies import get_current_tenant, get_current_user
from routes.config import require_admin
from schemas import CaseNoteCreate, CaseNoteRead
from services.notifications import normalize_email
import models

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_email(user: dict) -> str:
    return normalize_email(
        user.get("preferred_username")
        or user.get("upn")
        or user.get("email")
        or ""
    )


def _is_admin(user: dict) -> bool:
    """`require_admin` ile AYNI kural — kuralın kopyası tutulmaz, kendisi sorulur."""
    try:
        require_admin(user)
    except HTTPException:
        return False
    return True


def _utc_iso(value: Optional[dt.datetime]) -> str:
    """Ofsetli UTC ISO8601. Ofsetsiz değer (sqlite) UTC kabul edilir."""
    if value is None:
        value = dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat()


# `note` bilinçli `Any`: klasik `Column(...)` modelinde mypy örnek özniteliklerini
# `Column[str]` görür (routes/notifications.py::_serialize ile aynı desen).
def _can_delete(note: Any, email: str, is_admin: bool) -> bool:
    return is_admin or (bool(email) and normalize_email(note.author_email) == email)


def _serialize(note: Any, email: str, is_admin: bool) -> CaseNoteRead:
    return CaseNoteRead(
        id=note.id,
        body=note.body,
        author_name=note.author_name,
        author_email=note.author_email,
        created_at=_utc_iso(note.created_at),
        can_delete=_can_delete(note, email, is_admin),
    )


def _visible_case_or_404(db: Session, case_id: int, tenant_id: str) -> models.Case:
    case = get_tenant_owned_case(db, case_id, tenant_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Dava bulunamadı")
    return case


@router.get("/api/cases/{case_id}/notes", response_model=list[CaseNoteRead])
def list_case_notes(
    case_id: int,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _visible_case_or_404(db, case_id, tenant_id)
    email = _user_email(user)
    is_admin = _is_admin(user)
    notes = (
        db.query(models.CaseNote)
        .filter(models.CaseNote.case_id == case_id, models.CaseNote.deleted_at.is_(None))
        .order_by(models.CaseNote.created_at.desc(), models.CaseNote.id.desc())
        .all()
    )
    return [_serialize(n, email, is_admin) for n in notes]


@router.post("/api/cases/{case_id}/notes", response_model=CaseNoteRead, status_code=201)
def create_case_note(
    case_id: int,
    payload: CaseNoteCreate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _visible_case_or_404(db, case_id, tenant_id)
    email = _user_email(user)
    if not email:
        # Yazanı belli olmayan not bu tablonun amacına aykırı (kimlik claim'i eksik).
        raise HTTPException(status_code=403, detail="Kullanıcı e-postası alınamadı.")
    name = (user.get("name") or "").strip() or None
    note = models.CaseNote(
        case_id=case_id,
        body=payload.body,
        author_email=email,
        author_name=name,
        created_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    logger.info("Dava notu eklendi: case_id=%s note_id=%s", case_id, note.id)
    return _serialize(note, email, _is_admin(user))


@router.delete("/api/cases/{case_id}/notes/{note_id}", status_code=204)
def delete_case_note(
    case_id: int,
    note_id: int,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    _visible_case_or_404(db, case_id, tenant_id)
    note = (
        db.query(models.CaseNote)
        .filter(
            models.CaseNote.id == note_id,
            models.CaseNote.case_id == case_id,
            models.CaseNote.deleted_at.is_(None),
        )
        .first()
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Not bulunamadı")
    if not _can_delete(note, _user_email(user), _is_admin(user)):
        raise HTTPException(status_code=403, detail="Notu yalnız yazanı ya da yönetici silebilir")
    note.deleted_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    logger.info("Dava notu silindi: case_id=%s note_id=%s", case_id, note_id)
    return Response(status_code=204)
