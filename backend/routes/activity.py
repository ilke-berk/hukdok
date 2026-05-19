"""
Günlük Aktivite Raporu API Rotaları
"""

import json
import logging
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from database import get_db
from dependencies import get_current_user
from routes.config import require_admin
from managers.activity_manager import (
    _build_report_for_date,
    catch_up_missed_reports,
    TZ_TURKEY,
)
import models

logger = logging.getLogger("ActivityRoutes")

router = APIRouter()


def _get_user_email(user: dict) -> str:
    return (
        user.get("preferred_username")
        or user.get("upn")
        or user.get("email")
        or ""
    )


# ---------------------------------------------------------------------------
# KULLANICI ENDPOINT'LERİ
# ---------------------------------------------------------------------------

def _hydrate_docs(db, ids: list[int]) -> list[dict]:
    """Verilen belge ID'leri için modal'da gösterilecek detayları çeker."""
    if not ids:
        return []
    docs = (
        db.query(models.CaseDocument)
        .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
        .filter(models.CaseDocument.id.in_(ids))
        .all()
    )
    by_id = {d.id: d for d in docs}
    out = []
    for doc_id in ids:
        d = by_id.get(doc_id)
        if not d:
            continue
        out.append({
            "id": d.id,
            "filename": d.stored_filename or "",
            "belge_turu": d.belge_turu_adi or "",
            "muvekkil": d.muvekkil_adi or "",
            "tracking_no": d.case.tracking_no if d.case else "",
            "case_id": d.case_id,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "email_error": d.email_error or "",
        })
    return out


@router.get("/api/activity/daily-report")
def get_pending_report(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Kullanıcının onaylanmamış en son günlük raporunu döner. Yoksa null."""
    user_email = _get_user_email(user)
    if not user_email:
        return None

    report = (
        db.query(models.DailyActivityReport)
        .filter(
            models.DailyActivityReport.user_email == user_email,
            models.DailyActivityReport.is_acknowledged.is_(False),
        )
        .order_by(models.DailyActivityReport.report_date.desc())
        .first()
    )

    if not report:
        return None

    mailed_ids = json.loads(report.mailed_doc_ids or "[]")
    unmailed_ids = json.loads(report.unmailed_doc_ids or "[]")
    error_ids = json.loads(report.error_doc_ids or "[]")

    return {
        "id": report.id,
        "report_date": report.report_date.isoformat(),
        "total_documents": report.total_documents,
        "mailed_documents": report.mailed_documents,
        "unmailed_documents": report.unmailed_documents,
        "error_documents": report.error_documents,
        "has_unmailed": report.unmailed_documents > 0,
        "mailed_docs": _hydrate_docs(db, mailed_ids),
        "unmailed_docs": _hydrate_docs(db, unmailed_ids),
        "error_docs": _hydrate_docs(db, error_ids),
    }


def _serialize_report_full(db, report) -> dict:
    """Raporu detaylı belge listeleriyle birlikte döner."""
    mailed_ids = json.loads(report.mailed_doc_ids or "[]")
    unmailed_ids = json.loads(report.unmailed_doc_ids or "[]")
    error_ids = json.loads(report.error_doc_ids or "[]")
    return {
        "id": report.id,
        "report_date": report.report_date.isoformat(),
        "user_email": report.user_email,
        "total_documents": report.total_documents,
        "mailed_documents": report.mailed_documents,
        "unmailed_documents": report.unmailed_documents,
        "error_documents": report.error_documents,
        "has_unmailed": report.unmailed_documents > 0,
        "is_acknowledged": report.is_acknowledged,
        "mailed_docs": _hydrate_docs(db, mailed_ids),
        "unmailed_docs": _hydrate_docs(db, unmailed_ids),
        "error_docs": _hydrate_docs(db, error_ids),
    }


@router.get("/api/activity/history")
def get_user_history(
    days: int = Query(default=30, ge=1, le=180),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Kullanıcının kendi geçmiş raporlarının özet listesi (son N gün)."""
    user_email = _get_user_email(user)
    if not user_email:
        return []

    cutoff = dt.date.today() - dt.timedelta(days=days)
    reports = (
        db.query(models.DailyActivityReport)
        .filter(
            models.DailyActivityReport.user_email == user_email,
            models.DailyActivityReport.report_date >= cutoff,
        )
        .order_by(models.DailyActivityReport.report_date.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "report_date": r.report_date.isoformat(),
            "total_documents": r.total_documents,
            "mailed_documents": r.mailed_documents,
            "unmailed_documents": r.unmailed_documents,
            "error_documents": r.error_documents,
            "is_acknowledged": r.is_acknowledged,
        }
        for r in reports
    ]


@router.get("/api/activity/history/{report_id}")
def get_user_history_detail(
    report_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Kullanıcının kendi raporunun detayını döner (3 kategori belge listeli)."""
    user_email = _get_user_email(user)
    if not user_email:
        raise HTTPException(status_code=403, detail="Kullanıcı e-postası alınamadı.")

    report = (
        db.query(models.DailyActivityReport)
        .filter(
            models.DailyActivityReport.id == report_id,
            models.DailyActivityReport.user_email == user_email,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı.")

    return _serialize_report_full(db, report)


@router.post("/api/activity/daily-report/{report_id}/acknowledge")
def acknowledge_report(
    report_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Raporu onaylandı olarak işaretler."""
    user_email = _get_user_email(user)

    report = (
        db.query(models.DailyActivityReport)
        .filter(
            models.DailyActivityReport.id == report_id,
            models.DailyActivityReport.user_email == user_email,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı.")

    report.is_acknowledged = True
    db.commit()
    return {"success": True}


@router.post("/api/activity/daily-report/{report_id}/send-emails")
def send_missing_emails(
    report_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Mailsiz belgeler için özet bildirim gönderir, raporu onaylar."""
    user_email = _get_user_email(user)

    report = (
        db.query(models.DailyActivityReport)
        .filter(
            models.DailyActivityReport.id == report_id,
            models.DailyActivityReport.user_email == user_email,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı.")

    unmailed_ids: list[int] = json.loads(report.unmailed_doc_ids or "[]")
    report_date = report.report_date

    report.is_acknowledged = True
    db.commit()

    if unmailed_ids:
        background_tasks.add_task(_bg_send_summary, unmailed_ids, report_date, user_email)
        return {"success": True, "message": f"{len(unmailed_ids)} belge için bildirim e-postası gönderiliyor."}

    return {"success": True, "message": "Gönderilecek mailsiz belge yok."}


def _bg_send_summary(doc_ids: list[int], report_date, user_email: str):
    try:
        from managers.activity_manager import send_unmailed_summary
        send_unmailed_summary(doc_ids, report_date, user_email)
    except Exception as e:
        logger.error(f"Arka plan özet mail hatası: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# TEST / ADMIN ENDPOINT'LERİ
# ---------------------------------------------------------------------------

@router.post("/api/activity/admin/trigger")
def admin_trigger_report(
    target_date: Optional[str] = Query(
        default=None,
        description="YYYY-MM-DD. Boş bırakılırsa bugün kullanılır.",
    ),
    force_user_email: Optional[str] = Query(
        default=None,
        description="Dolu olursa o tarihteki TÜM belgeler bu e-posta altında gruplanır (eski belgeler için).",
    ),
    user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """[ADMIN] Belirtilen tarih için raporu elle tetikler ve tanı bilgisi döner."""
    # Tarihi çözümle
    if target_date:
        try:
            parsed = dt.date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Geçersiz tarih. YYYY-MM-DD kullanın.")
    else:
        parsed = dt.date.today()

    # Tarih aralığını UTC'ye çevir
    next_day = parsed + dt.timedelta(days=1)
    day_start_utc = (
        dt.datetime.combine(parsed, dt.time.min)
        .replace(tzinfo=TZ_TURKEY)
        .astimezone(dt.timezone.utc)
    )
    day_end_utc = (
        dt.datetime.combine(next_day, dt.time.min)
        .replace(tzinfo=TZ_TURKEY)
        .astimezone(dt.timezone.utc)
    )

    # Tanı sorguları
    try:
        total_docs = (
            db.query(models.CaseDocument)
            .filter(
                models.CaseDocument.uploaded_at >= day_start_utc,
                models.CaseDocument.uploaded_at < day_end_utc,
            )
            .count()
        )
        docs_with_email = (
            db.query(models.CaseDocument)
            .filter(
                models.CaseDocument.uploaded_at >= day_start_utc,
                models.CaseDocument.uploaded_at < day_end_utc,
                models.CaseDocument.uploaded_by_email.isnot(None),
            )
            .count()
        )
    except Exception as e:
        logger.error(f"Tanı sorgusu hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Veritabanı sorgu hatası oluştu.")

    docs_without_email = total_docs - docs_with_email

    # Raporu oluştur
    try:
        count = _build_report_for_date(db, parsed, force_user_email=force_user_email or None)
    except Exception as e:
        logger.error(f"Rapor oluşturma hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Rapor oluşturma sırasında bir hata oluştu.")

    msg_parts = [f"{parsed} tarihi için {count} grup raporu oluşturuldu/güncellendi."]
    if docs_without_email > 0 and not force_user_email:
        msg_parts.append(
            f"{docs_without_email} eski belgenin e-posta alanı boş — "
            f"'Kullanıcı e-postası' alanını doldurup tekrar deneyin."
        )

    return {
        "success": True,
        "target_date": parsed.isoformat(),
        "force_user_email": force_user_email,
        "users_reported": count,
        "diagnosis": {
            "total_docs_in_range": total_docs,
            "docs_with_email": docs_with_email,
            "docs_without_email": docs_without_email,
            "date_range_utc": f"{day_start_utc.isoformat()} → {day_end_utc.isoformat()}",
        },
        "message": (
            " ".join(msg_parts) if total_docs > 0
            else f"{parsed} tarihinde hiç belge bulunamadı."
        ),
    }


@router.post("/api/activity/admin/catch-up")
def admin_catch_up(user: dict = Depends(require_admin)):
    """[ADMIN] Kaçırılmış günlerin raporlarını tamamlar."""
    try:
        catch_up_missed_reports()
    except Exception as e:
        logger.error(f"Catch-up hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Catch-up işlemi sırasında bir hata oluştu.")
    return {"success": True, "message": "Catch-up tamamlandı."}


@router.delete("/api/activity/admin/reset")
def admin_reset_report(
    target_date: Optional[str] = Query(default=None, description="YYYY-MM-DD. Boş = bugün."),
    user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """[ADMIN] Belirtilen tarihteki raporları siler."""
    if target_date:
        try:
            parsed = dt.date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Geçersiz tarih formatı.")
    else:
        parsed = dt.date.today()

    deleted = (
        db.query(models.DailyActivityReport)
        .filter(models.DailyActivityReport.report_date == parsed)
        .delete()
    )
    db.commit()
    return {"success": True, "deleted_count": deleted, "date": parsed.isoformat()}


@router.get("/api/activity/admin/report/{report_id}")
def admin_get_report_detail(
    report_id: int,
    user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """[ADMIN] Belirli bir raporun detayını (3 kategori belge listeli) döner."""
    report = (
        db.query(models.DailyActivityReport)
        .filter(models.DailyActivityReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadı.")
    return _serialize_report_full(db, report)


@router.get("/api/activity/admin/list")
def admin_list_reports(
    user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """[ADMIN] Son 30 gündeki tüm raporları listeler."""
    cutoff = dt.date.today() - dt.timedelta(days=30)
    reports = (
        db.query(models.DailyActivityReport)
        .filter(models.DailyActivityReport.report_date >= cutoff)
        .order_by(models.DailyActivityReport.report_date.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "user_email": r.user_email,
            "display": (
                r.user_email.replace("__name__", "")
                if r.user_email.startswith("__name__")
                else r.user_email
            ),
            "is_legacy": r.user_email.startswith("__name__"),
            "report_date": r.report_date.isoformat(),
            "total": r.total_documents,
            "mailed": r.mailed_documents,
            "unmailed": r.unmailed_documents,
            "errors": r.error_documents,
            "acknowledged": r.is_acknowledged,
        }
        for r in reports
    ]
