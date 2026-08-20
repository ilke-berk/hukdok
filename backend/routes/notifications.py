"""Uygulama içi bildirim okuma/işaretleme uçları (G081) + idari görünüm (G087).

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

İdari görünüm uçları (G087) — `/overview` ve `/unresolved-targets` — bu sahiplik
kuralının DIŞINDADIR: başkalarının süre/duruşma uyarılarını ve okunma durumunu
yayınlarlar. Kapıları bilinçli olarak `require_admin` DEĞİL olağan
`get_current_user`dır (kullanıcı kararı, 2026-08-20): sistemde rol kavramı yok,
"idari pano" bir `localStorage` toggle'ıdır ve ofis ortak havuzda çalışır. Gevşeme
YALNIZ bu iki salt-okuma ucuna aittir; yukarıdaki kişisel uçlar hâlâ kimsenin
başkasının satırını görmesine/işaretlemesine izin vermez.

Uç `/api` altındadır → konteyner nginx'inin mevcut `/api` proxy kuralı yeterli;
`/export` benzeri bir istisna GEREKMEZ (nginx.conf:62).
"""
import datetime as dt
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

from auth_helpers import tenant_filter_clause
from database import get_db
from dependencies import get_current_tenant, get_current_user
# Tür etiketleri tarayıcının tanımından okunur; ikinci bir kopya tutulmaz
# (deadline_scanner tek yazma yolu, etiketler orada tanımlı).
from services.deadline_scanner import DURUSMA_TYPE, SURE_TYPE
from services.notification_targeting import unresolved_targets
from services.notifications import normalize_email
import models

logger = logging.getLogger(__name__)

router = APIRouter()

# Liste ucunun tavanı: bildirim paneli sayfalamaz, "son N" okur.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# İdari görünüm (G087) sınırları — Query(ge/le) ile 422'ye bağlanır.
OVERVIEW_TYPES: tuple[str, ...] = (SURE_TYPE, DURUSMA_TYPE)
OVERVIEW_DEFAULT_DAYS = 30
OVERVIEW_MAX_DAYS = 365
OVERVIEW_DEFAULT_LIMIT = 100
OVERVIEW_MAX_LIMIT = 500

# due_date NULL olan satır sona düşsün: sqlite NULL'ı başa, Postgres sona
# koyar — coalesce sıralamayı iki motorda da AYNI yapar.
_UZAK_TARIH = dt.date(9999, 12, 31)


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


def _overview_serialize(row) -> dict:
    """İdari özet satırı — kişisel `_serialize`dan AYRI tutulur.

    Gövde (`body`) bilinçli olarak yayınlanmaz: idari görünümün sorusu "kime
    gitti, okundu mu", uyarının tam metni değil. Alıcı adresi ise burada
    ZORUNLU alandır (kişisel uçta gereksizdi — orada alıcı zaten istek sahibi).
    """
    return {
        "id": row.id,
        "type": row.type,
        "severity": row.severity,
        "title": row.title,
        "recipient_email": row.recipient_email,
        "case_id": row.case_id,
        "due_date": _iso(row.due_date),
        "read_at": _iso(row.read_at),
        "is_read": row.read_at is not None,
        "created_at": _iso(row.created_at),
    }


@router.get("/api/notifications/overview")
def notifications_overview(
    days: int = Query(default=OVERVIEW_DEFAULT_DAYS, ge=1, le=OVERVIEW_MAX_DAYS),
    limit: int = Query(default=OVERVIEW_DEFAULT_LIMIT, ge=1, le=OVERVIEW_MAX_LIMIT),
    unread_only: bool = Query(default=False),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
    db=Depends(get_db),
):
    """Süre/duruşma uyarılarının idari özeti: kime gitti, okundu mu (G087).

    SALT OKUMA: hiçbir satırın `read_at`ine dokunmaz, `db.commit()` çağırmaz —
    idari panelde bir uyarıya bakmak avukatın okunmamış sayacını düşürmez.

    Kapsam yalnız `OVERVIEW_TYPES` (süre + duruşma); "belge işlendi" gibi
    operasyonel bildirimler bu takip görünümünün konusu değildir.

    Pencere `created_at` üzerindedir — soru "hangi uyarı GÖNDERİLDİ"dir.
    `due_date` üzerinden kesmek, süresi geçmiş ama okunmamış uyarıyı
    listeden düşürür ve takip görünümünün asıl işini bozardı.

    `total`/`unread` sayaçları `limit` UYGULANMADAN hesaplanır: tavana
    dayanıldığında panel "12 uyarının 5'i okunmamış" diyebilsin.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    # Tenant kuralı paylaşılan havuz desenidir (tenant_id == X OR IS NULL);
    # bildirim satırı tenant'ını yazıldığı davadan devralır ve ofis kayıtları
    # bilinçli NULL'dır — düz eşitlik listeyi boşaltırdı (CLAUDE.md tenant modeli).
    q = db.query(models.Notification).filter(
        models.Notification.type.in_(OVERVIEW_TYPES),
        models.Notification.dismissed_at.is_(None),
        models.Notification.created_at >= cutoff,
        tenant_filter_clause(models.Notification, tenant_id),
    )

    toplam = q.count()
    okunmamis = q.filter(models.Notification.read_at.is_(None)).count()

    if unread_only:
        q = q.filter(models.Notification.read_at.is_(None))

    rows = (
        q.order_by(
            func.coalesce(models.Notification.due_date, _UZAK_TARIH).asc(),
            models.Notification.id.asc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "days": days,
        "limit": limit,
        "total": toplam,
        "unread": okunmamis,
        "items": [_overview_serialize(r) for r in rows],
    }


@router.get("/api/notifications/unresolved-targets")
def unresolved_target_summary(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Hedefe çözülemeyen sorumlu adları + dava sayıları (G087).

    Gövdeyi `services.notification_targeting.unresolved_targets` üretir; bu uç
    yalnız HTTP kabuğudur (sıralama ve gruplama orada, tek kaynak).

    Tenant DARALTMASI YOK — bilinçli: sayaç `cases` üzerinden hesaplanır ve
    dava havuzu iki tenant arasında PAYLAŞILIR (`tenant_id` NULL, CLAUDE.md).
    Bir tenant'a daraltmak "97 dava hedefsiz" ölçümünü sessizce eksiltirdi.
    """
    rows: list[dict[str, Any]] = unresolved_targets(db)
    return {
        "items": rows,
        "total_names": len(rows),
        "total_cases": sum(int(r.get("case_count") or 0) for r in rows),
    }


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
