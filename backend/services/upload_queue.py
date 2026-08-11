"""SharePoint arşiv yüklemeleri için kalıcı outbox/retry kuyruğu (Faz 3-A).

Eski akış fire-and-forget'ti: /confirm yanıtından sonra BackgroundTasks tek
deneme yapar, süreç ölürse (OOM, deploy) yükleme sessizce kaybolur, geçici bir
SharePoint hatası belgeyi kalıcı "failed" bırakırdı — planın deyişiyle "en
büyük sessiz veri kaybı yolu". Yeni akış export_publisher.py desenidir:

1. enqueue_upload — payload spool dizinine KOPYALANIR (kaynak temp dosya 30 sn
   sonra silinir; kopya kuyruğun kendi malıdır) ve upload_outbox'a pending
   satır yazılır. Bu, /confirm yanıtı dönmeden commit edilir: kullanıcı
   "başarılı" gördüyse yükleme garanti kayıttadır.
2. Tek worker thread satırları sırayla işler; geçici hatada üstel backoff ile
   yeniden dener (RETRY_BACKOFF_SECONDS), MAX_ATTEMPTS tüketilince satır nihai
   "failed" olur. Açılışta start_upload_worker'ın ilk taraması önceki süreçten
   kalan pending satırları da alır (startup reconcile).
3. "islenmis" satırlarında her deneme document_pipeline._record_upload_result
   ile belgeye işlenir (upload_attempts artar, uploaded/failed görünür);
   hukukbot outbox hook'u YALNIZ URL commit'inde açılır — davranış korunur.

Loglama sözleşmesi (Faz 2-C ERROR-oranı alarmı ≥5 ERROR/5dk çalıyor): geçici /
retry edilebilir hatalar WARNING, yalnız NİHAİ başarısızlık ERROR. Worker
thread'inde request_id "-" görünür (bilinçli); izlenebilirlik extra alanlarıyla
taşınır (doc_id/outbox_id/kind → JSON formatter geçirir).

Eşzamanlılık: uvicorn tek worker varsayımı — satırları yalnız bu süreçteki tek
thread işler, süreç içi yarış yoktur. uvicorn --workers 2 geçişinde (Faz 3-E)
bu worker süreç-tekil yapılmalı (yoksa aynı satır iki kez yüklenir; overwrite
zararsız ama gereksiz) — bkz. takip dosyasındaki 3-E önkoşulları.

Faz 3-F statü eki: 'superseded' — gece dönüşüm job'ı PDF'i yükleyip belgeyi
tamamladıktan sonra, aynı belgenin hâlâ bekleyen islenmis-orijinal satırı
etkisizleştirilir (tamamlanırsa _record_upload_result sharepoint_url'i PDF'ten
orijinale geri EZERDİ). Worker superseded satırı işlemez; upload sırasında
yakalanırsa sonuç belgeye İŞLENMEZ; spool dosyası janitor'da hemen temizlenir.
"""
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from database import SessionLocal
from file_utils import safe_remove
import models

logger = logging.getLogger(__name__)

# İlk deneme hemen; sonraki denemeler arası bekleme. Toplam ~23 saat pencere:
# gecelik Graph/token arızaları ve uzun SharePoint kesintileri kapansın diye.
RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600, 3 * 3600, 6 * 3600, 12 * 3600)
MAX_ATTEMPTS = 8

# Worker uyandırma periyodu: enqueue Event ile anında uyandırır, bu yalnız
# backoff vadesi dolan satırların tavan gecikmesidir.
POLL_INTERVAL_SECONDS = 60

# Nihai failed satırların spool dosyası bu süre saklanır (elle kurtarma şansı:
# status='pending', attempts=0 yapılırsa worker yeniden dener), sonra KVKK
# gereği silinir; satır kayıt olarak kalır.
FAILED_SPOOL_RETENTION_DAYS = 30

_LAST_ERROR_MAX_CHARS = 2000

_wake = threading.Event()
_stop = threading.Event()
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()


def get_spool_dir() -> Path:
    """Spool dizini: UPLOAD_SPOOL_DIR env'i ya da <backend>/data/upload_spool.

    Konteynerde <backend> = /app ve /app/data backend-data volume'üdür →
    spool konteyner recreate'ini de atlatır. Host'ta backend/data (gitignore).
    """
    override = os.getenv("UPLOAD_SPOOL_DIR", "").strip()
    if override:
        spool = Path(override)
    else:
        spool = Path(__file__).resolve().parent.parent / "data" / "upload_spool"
    spool.mkdir(parents=True, exist_ok=True)
    return spool


def enqueue_upload(
    kind: str,
    source_path: str,
    target_filename: str,
    target_folder: str,
    document_id: Optional[int] = None,
) -> Optional[int]:
    """Payload'ı spool'a kopyalayıp outbox'a pending satır açar; worker'ı uyandırır.

    Başarıda outbox id, hatada None döner — HATA FIRLATMAZ. None dönüşünde
    çağıran (document_pipeline) eski tek-denemeli BackgroundTasks yoluna düşer:
    kuyruk arızası arşivlemeyi eskisinden daha kötü yapmamalı.
    """
    spool_path: Optional[Path] = None
    try:
        if not source_path or not os.path.exists(source_path):
            raise FileNotFoundError(f"Kaynak dosya yok: {source_path}")

        suffix = Path(target_filename).suffix or Path(source_path).suffix
        spool_path = get_spool_dir() / f"{uuid.uuid4().hex}{suffix.lower()}"
        shutil.copy2(source_path, spool_path)

        db = SessionLocal()
        try:
            row = models.UploadOutbox(
                document_id=document_id,
                kind=kind,
                spool_path=str(spool_path),
                target_filename=target_filename,
                target_folder=target_folder,
                status="pending",
                attempts=0,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            outbox_id = row.id
        except Exception:
            # Faz 3-E (3.6): açık transaction'ı bırak; dıştaki except fallback'e
            # düşürür (rollback da patlarsa yine aynı yere düşer — bare yeterli).
            db.rollback()
            raise
        finally:
            db.close()

        logger.info(
            f"Upload outbox: {kind} kuyruğa alındı ({target_filename})",
            extra={"doc_id": document_id, "outbox_id": outbox_id, "kind": kind},
        )
        _wake.set()
        return outbox_id
    except Exception as e:
        # Kuyruğa yazılamadı (DB/disk) — çağıran fallback'e düşecek; nihai veri
        # kaybı değil, o yüzden WARNING (nihai kayıp ERROR'u fallback'in kendi
        # hata yolunda üretilir).
        if spool_path is not None:
            safe_remove(str(spool_path))
        logger.warning(
            f"Upload outbox enqueue hatası ({kind}, {target_filename}): {e} — "
            "tek denemeli fallback devrede",
            extra={"doc_id": document_id, "kind": kind},
        )
        return None


def _next_delay_seconds(attempts: int) -> int:
    """attempts. denemeden SONRAKİ bekleme (attempts >= 1)."""
    idx = min(max(attempts - 1, 0), len(RETRY_BACKOFF_SECONDS) - 1)
    return RETRY_BACKOFF_SECONDS[idx]


def _is_due(row, now: datetime) -> bool:
    if row.status != "pending":
        return False
    if row.next_attempt_at is None:
        return True
    next_at = row.next_attempt_at
    if next_at.tzinfo is None:
        # Defansif: TIMESTAMPTZ normalde tz-aware döner; naive gelirse UTC say.
        next_at = next_at.replace(tzinfo=timezone.utc)
    return next_at <= now


def _record_doc_attempt(kind: str, document_id, web_url) -> bool:
    """islenmis satırının denemesini belge kaydına işler (Faz 2-C sözleşmesi).

    True dönüşü sharepoint_url'in commit edildiği anlamına gelir — hukukbot
    outbox hook'u yalnız o zaman açılır (BULGULAR #1).
    """
    if kind != "islenmis" or not document_id:
        return False
    from services.document_pipeline import _record_upload_result
    return _record_upload_result(document_id, web_url)


def _finalize_failed(db, row, reason: str) -> None:
    """Satırı nihai failed yapar — Faz 3-A'daki TEK ERROR log noktası."""
    row.status = "failed"
    row.done_at = datetime.now(timezone.utc)
    row.last_error = (reason or "")[:_LAST_ERROR_MAX_CHARS]
    db.commit()
    logger.error(
        f"SharePoint yüklemesi NİHAİ başarısız ({row.kind}, {row.target_filename}, "
        f"{row.attempts} deneme): {reason}",
        extra={
            "doc_id": row.document_id,
            "outbox_id": row.id,
            "kind": row.kind,
            "attempts": row.attempts,
        },
    )


def _attempt_upload(outbox_id: int) -> None:
    """Tek satır için tek yükleme denemesi; durum geçişini DB'ye işler.

    Deneme sayacı yüklemeden ÖNCE commit edilir: süreç upload ortasında ölürse
    açılış reconcile'ı satırı kaldığı sayaçla yeniden dener — crash döngüsüne
    giren zehirli bir dosya MAX_ATTEMPTS'te nihai failed'a düşer, sonsuz
    döngüye girmez.
    """
    db = SessionLocal()
    try:
        row = db.query(models.UploadOutbox).filter(models.UploadOutbox.id == outbox_id).first()
        if row is None or row.status != "pending":
            return

        if not row.spool_path or not os.path.exists(row.spool_path):
            # Spool kayıp (volume silindi / elle temizlik) — retry imkânsız,
            # nihai kayıp. Belge tarafına da işle ki 'pending'de asılı kalmasın.
            row.attempts = (row.attempts or 0) + 1
            _finalize_failed(db, row, f"Spool dosyası diskte yok: {row.spool_path}")
            _record_doc_attempt(row.kind, row.document_id, None)
            return

        row.attempts = (row.attempts or 0) + 1
        db.commit()

        # Deneme anındaki alanları kopyala; upload sırasında session açık kalmasın
        # (yükleme dakikalar sürebilir, pool bağlantısını işgal etmesin).
        attempt_no = row.attempts
        kind, doc_id = row.kind, row.document_id
        spool_path = row.spool_path
        target_filename, target_folder = row.target_filename, row.target_folder
    except Exception:
        # Faz 3-E (3.6): sayaç commit'i düştüyse upload'a GEÇME (zehirli dosya
        # bekçisi sayaca dayanır); istisna _worker_loop'ta WARNING'e düşer.
        db.rollback()
        raise
    finally:
        db.close()

    web_url = None
    error: Optional[Exception] = None
    try:
        from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
        response_data = upload_file_to_sharepoint(
            spool_path, target_filename, target_folder, use_date_subfolder=False
        )
        web_url = (response_data or {}).get("webUrl")
    except Exception as e:
        error = e

    db = SessionLocal()
    try:
        row = db.query(models.UploadOutbox).filter(models.UploadOutbox.id == outbox_id).first()
        if row is None:
            return

        if row.status == "superseded":
            # Faz 3-F: gece dönüşüm job'ı bu satırı upload SIRASINDA
            # etkisizleştirdi — dosya yüklendiyse zararsız kopyadır ama sonuç
            # belgeye İŞLENMEZ (sharepoint_url gece yazılan PDF'i göstermeye
            # devam eder) ve hukukbot hook'u açılmaz.
            if safe_remove(spool_path):
                row.spool_path = None
                db.commit()
            logger.info(
                f"Upload outbox: satır gece dönüşümüyle etkisizleştirilmiş, "
                f"sonuç belgeye işlenmedi (outbox={outbox_id})",
                extra={"doc_id": doc_id, "outbox_id": outbox_id, "kind": kind},
            )
            return

        if error is None:
            row.status = "uploaded"
            row.done_at = datetime.now(timezone.utc)
            row.last_error = None
            db.commit()
            logger.info(
                f"Upload outbox: {kind} yüklendi ({target_filename}, deneme {attempt_no})",
                extra={"doc_id": doc_id, "outbox_id": outbox_id, "kind": kind},
            )
            # Önce durum commit'i, sonra dosya silme: ters sırada commit
            # başarısız olursa satır pending kalır ve sonraki deneme spool'u
            # bulamayıp başarılı yüklemeyi "failed" sanırdı. Silme başaramazsa
            # pointer kalır, janitor (_purge_terminal_spools) toparlar.
            if safe_remove(spool_path):
                row.spool_path = None
                db.commit()

            url_saved = _record_doc_attempt(kind, doc_id, web_url)
            if url_saved:
                try:
                    from services.export_publisher import notify_hukukbot
                    notify_hukukbot(doc_id)
                except Exception as hook_err:
                    from managers.log_manager import TechnicalLogger
                    TechnicalLogger.log(
                        "ERROR", f"Hukukbot export hook error (doc={doc_id}): {hook_err}"
                    )
            return

        # Başarısız deneme: belge sayacına işle, sonra retry mi nihai mi karar ver.
        _record_doc_attempt(kind, doc_id, None)
        if attempt_no >= MAX_ATTEMPTS:
            _finalize_failed(db, row, str(error))
        else:
            delay = _next_delay_seconds(attempt_no)
            row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            row.last_error = str(error)[:_LAST_ERROR_MAX_CHARS]
            db.commit()
            logger.warning(
                f"SharePoint yüklemesi başarısız ({kind}, {target_filename}, deneme "
                f"{attempt_no}/{MAX_ATTEMPTS}), {delay} sn sonra yeniden: {error}",
                extra={"doc_id": doc_id, "outbox_id": outbox_id, "kind": kind},
            )
    except Exception as db_err:
        db.rollback()
        # Sonuç DB'ye işlenemedi — satır pending kaldı, sonraki tarama yeniden
        # dener (başarılıysa overwrite zararsız). Geçici durum → WARNING.
        logger.warning(
            f"Upload outbox durum güncellenemedi (outbox={outbox_id}): {db_err}",
            extra={"doc_id": doc_id, "outbox_id": outbox_id, "kind": kind},
        )
    finally:
        db.close()


def _purge_terminal_spools(db, now: datetime) -> None:
    """Terminal satırların spool dosyalarını temizler (KVKK); satır denetim izi
    olarak kalır, spool_path NULL'lanır.

    - uploaded: dosya normalde başarı anında silinir; safe_remove o an
      başaramadıysa buradan toparlanır (bekleme yok).
    - superseded (Faz 3-F): satır etkisizleştirilmiştir, dosyanın retry değeri
      yok — bekleme olmadan temizlenir.
    - failed: FAILED_SPOOL_RETENTION_DAYS boyunca saklanır — elle kurtarma
      şansı (status='pending', attempts=0 → worker yeniden dener) — sonra silinir.

    Worker thread'iyle aynı thread'de koşar; in-flight satırlarla yarışmaz.
    """
    cutoff = now - timedelta(days=FAILED_SPOOL_RETENTION_DAYS)
    rows = (
        db.query(models.UploadOutbox)
        .filter(
            models.UploadOutbox.status.in_(("uploaded", "failed", "superseded")),
            models.UploadOutbox.spool_path.isnot(None),
        )
        .all()
    )
    for row in rows:
        if row.status not in ("uploaded", "failed", "superseded") or not row.spool_path:
            continue  # defansif: testlerdeki fake filter no-op olabilir
        if row.status == "failed":
            done_at = row.done_at or row.created_at
            if done_at is None:
                continue
            if done_at.tzinfo is None:
                done_at = done_at.replace(tzinfo=timezone.utc)
            if done_at > cutoff:
                continue
        if not safe_remove(row.spool_path):
            continue  # dosya silinemedi — pointer'ı koru, sonraki tarama dener
        row.spool_path = None
        try:
            db.commit()
        except Exception:
            # Faz 3-E (3.6): DB düştüyse sıradaki satırların commit'i de düşer —
            # rollback'le bırak, istisna _worker_loop'ta WARNING'e düşsün.
            db.rollback()
            raise
        if row.status == "failed":
            logger.info(
                f"Upload outbox: failed satırın spool dosyası "
                f"{FAILED_SPOOL_RETENTION_DAYS} gün sonra silindi (outbox={row.id})",
                extra={"doc_id": row.document_id, "outbox_id": row.id},
            )


def supersede_pending_uploads(document_id: int, kind: str) -> int:
    """Belgenin bekleyen <kind> satırlarını 'superseded' yapar (Faz 3-F).

    Gece dönüşüm job'ı PDF'i senkron yükleyip belgeyi tamamlamadan HEMEN önce
    çağırır: bekleyen islenmis-orijinal satırı sonradan tamamlanıp
    _record_upload_result ile sharepoint_url'i orijinale geri ezmesin.
    Upload'ı o anda süren satır pre-check'i çoktan geçmiştir — o pencere
    _attempt_upload'ın sonuç-yazma adımındaki superseded guard'ıyla kapanır.
    Hata fırlatmaz; etkisizleştirilen satır sayısını döndürür.
    """
    if not document_id:
        return 0
    db = SessionLocal()
    try:
        rows = (
            db.query(models.UploadOutbox)
            .filter(
                models.UploadOutbox.document_id == document_id,
                models.UploadOutbox.kind == kind,
                models.UploadOutbox.status == "pending",
            )
            .all()
        )
        count = 0
        for row in rows:
            # Defansif yeniden kontrol (testlerdeki fake filter no-op olabilir)
            if row.status != "pending" or row.kind != kind or row.document_id != document_id:
                continue
            row.status = "superseded"
            row.done_at = datetime.now(timezone.utc)
            row.last_error = "Gece dönüşümü PDF'i yükledi — orijinal-yükleme satırı etkisizleştirildi"
            count += 1
        if count:
            db.commit()
            logger.info(
                f"Upload outbox: {count} bekleyen {kind} satırı etkisizleştirildi "
                f"(gece dönüşümü tamamlandı)",
                extra={"doc_id": document_id, "kind": kind},
            )
        return count
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(
            f"Upload outbox supersede başarısız (doc={document_id}): {e}",
            extra={"doc_id": document_id, "kind": kind},
        )
        return 0
    finally:
        db.close()


def _scan_once() -> int:
    """Vadesi gelen pending satırları sırayla işler; işlenen sayısını döndürür.

    Worker başlarken ilk çağrı startup reconcile'dır: önceki süreçten kalan
    satırlar (next_attempt_at NULL ya da geçmiş) burada toparlanır.
    """
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        _purge_terminal_spools(db, now)
        pending = (
            db.query(models.UploadOutbox)
            .filter(models.UploadOutbox.status == "pending")
            .order_by(models.UploadOutbox.id)
            .all()
        )
        due_ids = [row.id for row in pending if _is_due(row, now)]
    finally:
        db.close()

    for outbox_id in due_ids:
        if _stop.is_set():
            break
        _attempt_upload(outbox_id)
    return len(due_ids)


def _worker_loop() -> None:
    logger.info("Upload outbox worker başladı (startup reconcile ilk taramada).")
    while not _stop.is_set():
        try:
            _scan_once()
        except Exception as e:
            # Tarama arızası (ör. DB down) geçicidir; DB-down zaten /healthz'te
            # 503 üretir. Worker asla ölmemeli.
            logger.warning(f"Upload outbox taraması başarısız: {e}")
        _wake.wait(timeout=POLL_INTERVAL_SECONDS)
        _wake.clear()
    logger.info("Upload outbox worker durdu.")


def start_upload_worker() -> bool:
    """Worker thread'ini başlatır (idempotent). Lifespan'den çağrılır.

    Faz 3-E notu: uvicorn --workers N'e geçişte bu çağrı süreç-tekil
    yapılmalı — her worker kendi thread'ini açarsa aynı satır N kez yüklenir.
    """
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return False
        _stop.clear()
        _wake.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop, name="upload-outbox-worker", daemon=True
        )
        _worker_thread.start()
        return True


def stop_upload_worker(timeout: float = 5.0) -> None:
    """Worker'ı durdurur (shutdown/test). Yarım kalan satır pending kalır —
    deneme sayacı önceden commit edildiği için açılış reconcile'ı devralır."""
    global _worker_thread
    with _worker_lock:
        thread = _worker_thread
        if thread is None:
            return
        _stop.set()
        _wake.set()
        thread.join(timeout=timeout)
        _worker_thread = None
        _stop.clear()
        _wake.clear()
