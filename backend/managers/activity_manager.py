"""
Günlük Aktivite Raporu Yöneticisi

Gece yarısı tetiklenir; önceki günün belge yükleme istatistiklerini
kullanıcı bazında DailyActivityReport tablosuna kaydeder.

Backend kapalıyken kaçırılan günler startup sırasında catch_up_missed_reports()
ile tamamlanır.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone, time as dt_time
from collections import defaultdict

logger = logging.getLogger("ActivityManager")

# Türkiye saati UTC+3
TZ_TURKEY = timezone(timedelta(hours=3))

# Geriye dönük kaç günü kontrol edelim (catch-up)
MAX_CATCHUP_DAYS = 30


def _build_report_for_date(db, target_date: date, force_user_email: str = None) -> int:
    """
    Belirtilen gün için tüm kullanıcıların raporunu oluşturur/günceller.

    Gruplama önceliği:
      1. force_user_email verilmişse → tüm belgeler o e-posta altında
      2. uploaded_by_email doluysa    → o e-posta altında
      3. ikisi de yoksa               → uploaded_by (isim) anahtar olarak kullanılır
         (eski belgeler; rapor yine oluşur ama kullanıcıya modal gösterilemez)

    Döndürür: kaç kullanıcı/isim grubu için rapor yazıldı.
    """
    from models import CaseDocument, DailyActivityReport

    next_date = target_date + timedelta(days=1)
    day_start_utc = datetime.combine(target_date, dt_time.min).replace(tzinfo=TZ_TURKEY).astimezone(timezone.utc)
    day_end_utc = datetime.combine(next_date, dt_time.min).replace(tzinfo=TZ_TURKEY).astimezone(timezone.utc)

    docs = (
        db.query(CaseDocument)
        .filter(
            CaseDocument.uploaded_at >= day_start_utc,
            CaseDocument.uploaded_at < day_end_utc,
        )
        .all()
    )

    if not docs:
        return 0

    groups: dict[str, list] = defaultdict(list)
    for doc in docs:
        if force_user_email:
            key_email = force_user_email
        elif doc.uploaded_by_email:
            key_email = doc.uploaded_by_email
        else:
            # Eski belge — isim ile grupla (modal gösterilemez ama istatistik toplanır)
            key_email = f"__name__{doc.uploaded_by or 'bilinmeyen'}"
        groups[key_email].append(doc)

    count = 0
    for user_email, user_docs in groups.items():
        mailed_ids = [d.id for d in user_docs if d.email_sent is True]
        unmailed_ids = [d.id for d in user_docs if d.email_sent is None]
        error_ids = [d.id for d in user_docs if d.email_sent is False]
        total = len(user_docs)
        mailed = len(mailed_ids)
        unmailed = len(unmailed_ids)
        errors = len(error_ids)

        existing = (
            db.query(DailyActivityReport)
            .filter(
                DailyActivityReport.report_date == target_date,
                DailyActivityReport.user_email == user_email,
            )
            .first()
        )

        if existing:
            existing.total_documents = total
            existing.mailed_documents = mailed
            existing.unmailed_documents = unmailed
            existing.error_documents = errors
            existing.mailed_doc_ids = json.dumps(mailed_ids)
            existing.unmailed_doc_ids = json.dumps(unmailed_ids)
            existing.error_doc_ids = json.dumps(error_ids)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(DailyActivityReport(
                user_email=user_email,
                report_date=target_date,
                total_documents=total,
                mailed_documents=mailed,
                unmailed_documents=unmailed,
                error_documents=errors,
                mailed_doc_ids=json.dumps(mailed_ids),
                unmailed_doc_ids=json.dumps(unmailed_ids),
                error_doc_ids=json.dumps(error_ids),
                is_acknowledged=False,
            ))
        count += 1

    db.commit()
    return count


def generate_daily_reports():
    """
    Bir önceki günün raporunu oluşturur.
    APScheduler tarafından her gece 00:00 (Türkiye) çağrılır.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        yesterday = datetime.now(TZ_TURKEY).date() - timedelta(days=1)
        count = _build_report_for_date(db, yesterday)
        if count:
            logger.info(f"Günlük rapor tamamlandı ({yesterday}): {count} kullanıcı.")
        else:
            logger.info(f"Günlük rapor: {yesterday} için yüklenmiş belge yok.")
    except Exception as e:
        logger.error(f"Günlük rapor hatası: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def catch_up_missed_reports():
    """
    Backend kapalıyken kaçırılan günlerin raporlarını tamamlar.
    Backend her başladığında çağrılır.

    Son MAX_CATCHUP_DAYS gün içinde raporu olmayan ve belgesi olan
    her gün için rapor oluşturur.
    """
    from database import SessionLocal
    from models import DailyActivityReport, CaseDocument

    db = SessionLocal()
    try:
        today = datetime.now(TZ_TURKEY).date()
        yesterday = today - timedelta(days=1)
        cutoff = today - timedelta(days=MAX_CATCHUP_DAYS)

        # Mevcut rapor tarihleri
        existing_dates: set[date] = {
            row.report_date
            for row in db.query(DailyActivityReport.report_date)
            .filter(DailyActivityReport.report_date >= cutoff)
            .distinct()
            .all()
        }

        # cutoff'tan dünüe kadar: raporu olmayan ve belgesi olan günler
        missed: list[date] = []
        check = cutoff
        while check <= yesterday:
            if check not in existing_dates:
                next_day = check + timedelta(days=1)
                day_start = datetime.combine(check, dt_time.min).replace(tzinfo=TZ_TURKEY).astimezone(timezone.utc)
                day_end = datetime.combine(next_day, dt_time.min).replace(tzinfo=TZ_TURKEY).astimezone(timezone.utc)
                has_docs = (
                    db.query(CaseDocument.id)
                    .filter(
                        CaseDocument.uploaded_at >= day_start,
                        CaseDocument.uploaded_at < day_end,
                        CaseDocument.uploaded_by_email.isnot(None),
                    )
                    .first()
                )
                if has_docs:
                    missed.append(check)
            check += timedelta(days=1)

        if not missed:
            logger.info("Catch-up: eksik rapor yok.")
            return

        logger.info(f"Catch-up: {len(missed)} kaçırılmış gün tespit edildi: {missed}")
        for d in missed:
            count = _build_report_for_date(db, d)
            logger.info(f"Catch-up: {d} → {count} kullanıcı raporu oluşturuldu.")

    except Exception as e:
        logger.error(f"Catch-up hatası: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def send_unmailed_summary(doc_ids: list[int], report_date: date, user_email: str):
    """
    Mailsiz kaydedilen belgeler için özet bildirim e-postası gönderir
    (PDF eki olmadan — sadece liste).
    """
    from database import SessionLocal
    from models import CaseDocument
    from email_sender import _get_email_config

    config = _get_email_config()
    if not config["enabled"]:
        logger.info("E-posta özelliği kapalı, özet bildirimi atlandı.")
        return

    db = SessionLocal()
    try:
        docs = db.query(CaseDocument).filter(CaseDocument.id.in_(doc_ids)).all()
        if not docs:
            return

        lines = []
        for i, doc in enumerate(docs, 1):
            case_info = f" (Dava ID: {doc.case_id})" if doc.case_id else " (Dava bağlantısı yok)"
            lines.append(f"  {i}. {doc.stored_filename}{case_info}")

        date_str = report_date.strftime("%d.%m.%Y")
        body = (
            f"Sayın Kullanıcı,\n\n"
            f"{date_str} tarihinde aşağıdaki belgeler e-posta gönderilmeden arşivlendi:\n\n"
            + "\n".join(lines)
            + "\n\nBu belgeler için gerekli e-posta bildirimini ilgili dava sayfasından yapabilirsiniz.\n\n"
            "Saygılarımızla,\nHukuDok Belge Arşiv Sistemi"
        )

        sender = config["sender"]
        if not user_email:
            logger.warning("Özet bildirim: alıcı adresi yok, atlandı.")
            return

        import requests
        from sharepoint.auth_graph import get_graph_token

        token = get_graph_token()
        payload = {
            "message": {
                "subject": f"[HukuDok] Mailsiz Arşiv Özeti — {date_str}",
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": user_email}}],
            },
            "saveToSentItems": "true",
        }
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if resp.status_code == 202:
            logger.info(f"Özet bildirim gönderildi → {user_email}")
        else:
            logger.error(f"Özet bildirim gönderilemedi: {resp.status_code} {resp.text[:200]}")

    except Exception as e:
        logger.error(f"Özet bildirim hatası: {e}", exc_info=True)
    finally:
        db.close()
