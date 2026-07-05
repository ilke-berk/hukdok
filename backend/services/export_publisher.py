"""
Hukukbot aktarımı — outbox hook'u + webhook publisher (Faz 3).

Akış (docs/hukukbot-aktarim/PLAN.md §1, §3): SharePoint upload'ı başarıyla
bitip sharepoint_url DB'ye yazıldığı anda (document_pipeline.async_islenmis_upload)
notify_hukukbot çağrılır:

1. enqueue_document — belge export filtrelerinden geçiyorsa export_outbox'a
   "pending" satır açar. Satırın YALNIZCA bu anda açılması bilinçlidir:
   outbox id sırası = aktarılabilirlik sırası, async upload yarışı yok
   (BULGULAR #1).
2. publish_webhook — hukukbot'a POST {document_id, outbox_id} atar (backoff'lu
   retry). Ulaşamazsa sorun değil: satır pending kalır, hukukbot'un periyodik
   reconcile'ı toparlar (BULGULAR #8). Webhook yalnızca gecikmeyi sıfırlar,
   doğruluk garantisi outbox + reconcile'dadır.

HUKUKBOT_WEBHOOK_URL tanımsızsa webhook adımı atlanır — Faz 4'te ortak
hukuk_shared network'ü kurulup env doldurulana kadar sistem reconcile
temposunda çalışır.

Buradaki hiçbir hata yukarı fırlatılmaz: arşivleme hattı hukukbot
entegrasyonu yüzünden ASLA devrilmemeli.
"""
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

WEBHOOK_RETRIES = 3
WEBHOOK_BACKOFF_SECONDS = (2, 4)  # denemeler arası bekleme (1→2, 2→3)
WEBHOOK_TIMEOUT_SECONDS = 60      # hukukbot ingest'i senkron işleyebilir; kısa tutma


def enqueue_document(document_id: int) -> Optional[int]:
    """Belge aktarım filtrelerinden geçiyorsa outbox'a pending satır açar.

    Filtreler export listesindekiyle aynı (routes/export.py): tür allowlist'i
    normalize edilerek (BULGULAR #7), link_mode != "TEST" (BULGULAR #3),
    sharepoint_url dolu. Idempotent: satır zaten varsa id'sini döndürür.
    Filtreden düşen veya hata alan belge için None döner, hata fırlatmaz.
    """
    from database import SessionLocal
    from file_utils import _normalize_doctype_code
    from routes.export import get_type_allowlist
    import models

    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == document_id).first()
        if not doc:
            return None
        if doc.link_mode == "TEST" or not doc.sharepoint_url:
            return None
        allowlist = get_type_allowlist()
        code = _normalize_doctype_code(doc.belge_turu_kodu or "")
        if allowlist and code not in allowlist:
            return None

        existing = (
            db.query(models.ExportOutbox)
            .filter(models.ExportOutbox.document_id == document_id)
            .first()
        )
        if existing:
            return existing.id

        row = models.ExportOutbox(document_id=document_id, status="pending", attempts=0)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(f"Export outbox: belge {document_id} kuyruğa alındı (outbox_id={row.id})")
        return row.id
    except Exception as e:
        # Eşzamanlı ikinci enqueue unique constraint'e takılabilir — kabul,
        # satır diğer yazar tarafından açılmıştır.
        db.rollback()
        logger.error(f"Export outbox enqueue hatası (doc={document_id}): {e}")
        return None
    finally:
        db.close()


def _bump_attempts(outbox_id: int, tries: int) -> None:
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        row = db.query(models.ExportOutbox).filter(models.ExportOutbox.id == outbox_id).first()
        if row:
            row.attempts = (row.attempts or 0) + tries
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Export outbox attempts güncellenemedi (outbox={outbox_id}): {e}")
    finally:
        db.close()


def publish_webhook(document_id: int, outbox_id: int) -> bool:
    """Hukukbot'a webhook POST'u atar; başarıda True.

    Kalıcı başarısızlık sessizce kabul edilir (satır pending kalır,
    reconcile toparlar). Deneme sayısı outbox.attempts'e işlenir.
    """
    url = os.getenv("HUKUKBOT_WEBHOOK_URL", "").strip()
    if not url:
        logger.debug("HUKUKBOT_WEBHOOK_URL tanımsız — webhook atlandı, reconcile toparlayacak.")
        return False

    import requests

    headers = {"X-API-Key": os.getenv("HUKUKBOT_INGEST_API_KEY", "")}
    payload = {"document_id": document_id, "outbox_id": outbox_id}

    tries = 0
    ok = False
    for i in range(WEBHOOK_RETRIES):
        tries += 1
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=WEBHOOK_TIMEOUT_SECONDS)
            if r.status_code < 300:
                ok = True
                break
            logger.warning(f"Hukukbot webhook {r.status_code} döndü (doc={document_id}, deneme {tries}/{WEBHOOK_RETRIES})")
        except Exception as e:
            logger.warning(f"Hukukbot webhook hatası (doc={document_id}, deneme {tries}/{WEBHOOK_RETRIES}): {e}")
        if i < WEBHOOK_RETRIES - 1:
            time.sleep(WEBHOOK_BACKOFF_SECONDS[min(i, len(WEBHOOK_BACKOFF_SECONDS) - 1)])

    _bump_attempts(outbox_id, tries)
    if ok:
        logger.info(f"Hukukbot webhook iletildi: doc={document_id}, outbox={outbox_id}")
    else:
        logger.warning(
            f"Hukukbot webhook {tries} denemede iletilemedi (doc={document_id}) — "
            "satır pending kaldı, reconcile toparlayacak."
        )
    return ok


def notify_hukukbot(document_id: int) -> None:
    """Outbox hook'u: kuyruğa al + webhook'la haber ver. Hata fırlatmaz."""
    try:
        outbox_id = enqueue_document(document_id)
        if outbox_id is not None:
            publish_webhook(document_id, outbox_id)
    except Exception as e:
        logger.error(f"Hukukbot notify hatası (doc={document_id}): {e}")
