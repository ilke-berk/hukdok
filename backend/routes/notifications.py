"""Uygulama içi bildirim okuma/işaretleme uçları (G081).

`/api/notifications*`: kullanıcının KENDİ bildirimlerini listeler, okunmamış
sayısını verir, tek tek ya da toptan okundu işaretler. Satırları YAZAN taraf
`services/notifications.create_notification`'dır — bu modül yalnız okur ve
`read_at` damgalar.

Yetki modeli: sahiplik `recipient_email` eşitliğidir; tenant değil. Bildirim
kişiye yazılır ve iki tenant ortak havuzda çalışır (CLAUDE.md tenant modeli) —
tenant filtresi burada sahipliği daraltmaz, yalnız yanlış negatif üretirdi.
BAŞKASININ bildirimi hiçbir uçta görünmez; başkasının id'si 404 döner (403
DEĞİL: 403 "bu id var ama senin değil" bilgisini sızdırır, id enumeration'a
davetiyedir).

Kullanıcı kimliği ÜÇLÜ fallback ile okunur (`preferred_username | upn | email`)
— Azure token'ında hangi claim'in dolu geldiği sağlayıcı ayarına göre değişir
(bkz. routes/activity.py:_get_user_email, aynı desen).

Uç `/api` altındadır → konteyner nginx'inin mevcut `/api` proxy kuralı yeterli;
`/export` benzeri bir istisna GEREKMEZ (nginx.conf:62).
"""
import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from dependencies import get_current_user
from services.notifications import normalize_email
import models

logger = logging.getLogger(__name__)

router = APIRouter()

# Liste ucunun tavanı: bildirim paneli sayfalamaz, "son N" okur.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _get_user_email(user: dict) -> str:
    """Azure token'ından alıcı kimliği — üçlü claim fallback'i (upn tuzağı)."""
    return normalize_email(
        user.get("preferred_username")
        or user.get("upn")
        or user.get("email")
        or ""
    )


def _require_user_email(user: dict) -> str:
    email = _get_user_email(user)
    if not email:
        # Kimliksiz istek hiçbir satırın sahibi olamaz; boş liste dönmek
        # "bildirimin yok" der ve gerçek arızayı (claim eksikliği) gizlerdi.
        raise HTTPException(status_code=403, detail="Kullanıcı e-postası alınamadı.")
    return email


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _serialize(row) -> dict:
    return {
        "id": row.id,
        "type": row.type,
        "severity": row.severity,
        "title": row.title,
        "body": row.body,
        "case_id": row.case_id,
        "document_id": row.document_id,
        "due_date": _iso(row.due_date),
        "read_at": _iso(row.read_at),
        "is_read": row.read_at is not None,
        "created_at": _iso(row.created_at),
    }


def _visible(db, email: str):
    """Kullanıcının görebildiği satırlar: kendi bildirimleri, kapatılmamış olanlar."""
    return db.query(models.Notification).filter(
        models.Notification.recipient_email == email,
        models.Notification.dismissed_at.is_(None),
    )


@router.get("/api/notifications")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Kullanıcının bildirimleri — yeniden eskiye, en çok `limit` satır."""
    email = _require_user_email(user)

    q = _visible(db, email)
    if unread_only:
        q = q.filter(models.Notification.read_at.is_(None))

    rows = (
        q.order_by(
            models.Notification.created_at.desc(),
            models.Notification.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [_serialize(r) for r in rows]


@router.get("/api/notifications/count")
def unread_count(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Okunmamış bildirim sayısı (zil rozeti)."""
    email = _require_user_email(user)

    adet = (
        _visible(db, email)
        .filter(models.Notification.read_at.is_(None))
        .count()
    )
    return {"unread": adet}


@router.post("/api/notifications/read-all")
def mark_all_read(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Kullanıcının okunmamış TÜM bildirimlerini okundu işaretler."""
    email = _require_user_email(user)

    guncellenen = (
        _visible(db, email)
        .filter(models.Notification.read_at.is_(None))
        .update(
            {"read_at": dt.datetime.now(dt.timezone.utc)},
            synchronize_session=False,
        )
    )
    db.commit()
    return {"success": True, "updated": guncellenen}


@router.post("/api/notifications/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Tek bildirimi okundu işaretler. Başkasının bildirimi → 404."""
    email = _require_user_email(user)

    row = _visible(db, email).filter(models.Notification.id == notification_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı.")

    # İdempotent: ikinci çağrı ilk okuma zamanını EZMEZ.
    if row.read_at is None:
        row.read_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    return {"success": True, "read_at": _iso(row.read_at)}
