"""PDF/A dönüşümü için conversion_pending katmanı + gece retry job'ı (Faz 3-F, plan 3.8 Katman 2).

/confirm'de dönüşüm TÜM yollara rağmen başarısızsa (Katman 1 fallback'leri
dahil — e5df7b5) belge artık 500 ile kaybolmaz: orijinal KENDİ uzantısıyla
işlenmiş arşive yüklenir, CaseDocument conversion_status='pending' ile açılır
ve orijinalin bir kopyası buradaki conversion spool'una konur. Bu modül o
kopyanın sahibidir ve gece job'ı (retry_pending_conversions) ile akışı
tamamlar: PDF/A üret → işlenmiş arşive yükle → statüyü düşür → hukukbot'a
ANCAK O ZAMAN aç (notify_hukukbot).

KARAR NOTU (kalıcı saklama yeri): upload_outbox spool kopyası KULLANILAMAZ —
o kopya yükleme başarısında silinir (upload_queue._attempt_upload), oysa
dönüşüm kaynağı gecelerce yaşamalı. Bu yüzden ayrı conversion spool dizini
açıldı (3-A get_spool_dir deseni: backend-data volume'ü → restart/recreate
atlatır, worker'lar arası ortak).

KARAR NOTU (yükleme yolu): gece job'ı PDF/A'yı upload_outbox'a DEĞİL, senkron
yükler — outbox'a verilse statü düşürme + stored_filename güncelleme +
hukukbot açılışı outbox worker'ının başarı yoluna sızmak zorunda kalırdı
(sıkı bağlaşım); SharePoint hıçkırığında bir sonraki gece yeniden denemek
(dönüşüm dahil) ucuz ve idempotenttir. Uploader'ın kendi 3-B retry'ı zaten
kısa hıçkırıkları kapatır.

Loglama sözleşmesi (Faz 2-C ERROR-oranı alarmı ≥5/5dk canlı): deneme
başarısızlığı WARNING; yalnız NİHAİ başarısızlık (MAX_CONVERSION_ATTEMPTS
tükendi ya da spool kayboldu) tek ERROR — plan 3.8(c) gereği TechnicalLogger
üzerinden (standart logging'e delege eder → alarm sayar, SharePoint teknik
loguna da düşer).

Eşzamanlılık: job yalnız lider worker'ın APScheduler'ında koşar (api.py
lifespan, is_leader kapısı); tabloyu başka yazan yok. Deneme sayacı dönüşümden
ÖNCE commit edilir (upload_queue disiplini) — GS'yi çökerten zehirli bir dosya
crash döngüsünde MAX'ta nihai failed'a düşer, sonsuza dek denenmez.
"""
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, cast

from database import SessionLocal
from file_utils import safe_remove
from managers.log_manager import TechnicalLogger
import models

logger = logging.getLogger(__name__)

# Gece başına bir deneme → ~5 gün pencere: geçici ortam arızaları (GS/LO
# güncellemesi, bellek baskısı) kapansın; deterministik bozuk dosya 5 ERROR
# üretmeden tek nihai ERROR'la düşsün.
MAX_CONVERSION_ATTEMPTS = 5

# Nihai failed belgelerin spool dosyası elle kurtarma için saklanır
# (conversion_status='pending', conversion_attempts=0 → gece job'ı yeniden
# dener), sonra KVKK gereği silinir. Ölçüm doc.uploaded_at (oluşturulma)
# üzerinden yaklaşıktır: nihai failed en geç ~MAX gece sonra oluşur, bu yüzden
# tavana MAX payı eklidir (35 gün ≈ failed'dan itibaren ≥30 gün).
FAILED_SPOOL_RETENTION_DAYS = 35

# Soft-delete edilen belgenin spool'u: restore şansı için 30 gün bekler.
DELETED_SPOOL_RETENTION_DAYS = 30

# Hiçbir belgenin referans etmediği spool dosyaları (doc insert'inden önce
# çökme artığı) bu yaştan sonra süpürülür.
ORPHAN_SPOOL_AGE_DAYS = 2

_LAST_ERROR_MAX_CHARS = 500


def get_conversion_spool_dir() -> Path:
    """Spool dizini: CONVERSION_SPOOL_DIR env'i ya da <backend>/data/conversion_spool.

    Konteynerde <backend> = /app ve /app/data backend-data volume'üdür →
    kopya restart/recreate'i atlatır. Host'ta backend/data (gitignore).
    """
    override = os.getenv("CONVERSION_SPOOL_DIR", "").strip()
    if override:
        spool = Path(override)
    else:
        spool = Path(__file__).resolve().parent.parent / "data" / "conversion_spool"
    spool.mkdir(parents=True, exist_ok=True)
    return spool


def spool_original(source_path: str, suffix: str) -> Optional[str]:
    """Orijinali conversion spool'una kopyalar; başarıda kopya yolu, hatada None.

    None dönüşünde çağıran (document_pipeline) pending katmanını KURAMAZ ve
    bugünkü davranışa (HTTPException 500, gerçek neden) düşer — katman arızası
    akışı eskisinden kötü yapmamalı.
    """
    try:
        if not source_path or not os.path.exists(source_path):
            raise FileNotFoundError(f"Kaynak dosya yok: {source_path}")
        ext = (suffix or Path(source_path).suffix or ".bin").lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        target = get_conversion_spool_dir() / f"{uuid.uuid4().hex}{ext}"
        shutil.copy2(source_path, target)
        return str(target)
    except Exception as e:
        logger.warning(f"Conversion spool kopyası alınamadı ({source_path}): {e}")
        return None


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Defansif: TIMESTAMPTZ normalde tz-aware döner; naive gelirse UTC say.
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _finalize_failed(doc_id: int, attempts: int, reason: str) -> None:
    """Belgeyi nihai failed yapar — bu modülün TEK ERROR log noktası (plan 3.8c)."""
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if doc is not None:
            doc.conversion_status = "failed"
            db.commit()
    except Exception as db_err:
        try:
            db.rollback()
        except Exception:
            pass
        # Statü yazılamadı → satır pending kaldı, bir SONRAKİ gece yeniden
        # nihai karara varır (attempts zaten MAX'ta) — geçici durum, WARNING.
        logger.warning(f"Dönüşüm nihai-failed statüsü yazılamadı (doc={doc_id}): {db_err}")
        return
    finally:
        db.close()
    TechnicalLogger.log(
        "ERROR",
        f"PDF dönüşümü NİHAİ başarısız (doc={doc_id}, {attempts} deneme): "
        f"{str(reason)[:_LAST_ERROR_MAX_CHARS]} — orijinal arşivde kendi "
        "uzantısıyla duruyor; spool dosyası elle kurtarma için saklanıyor.",
    )


def _process_one(doc_id: int, islenmis_folder: str) -> str:
    """Tek pending belge için tek gece denemesi; sonuç etiketi döndürür."""
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if doc is None or doc.conversion_status != "pending" or doc.deleted_at is not None:
            return "skipped"
        spool_path = doc.conversion_spool_path
        stored_filename = str(doc.stored_filename or "")

        if not spool_path or not os.path.exists(spool_path):
            # Kaynak kayıp (volume silindi / elle temizlik) — retry imkânsız.
            attempts = (doc.conversion_attempts or 0) + 1
            doc.conversion_attempts = attempts
            db.commit()
            _finalize_failed(doc_id, attempts, f"Spool dosyası diskte yok: {spool_path}")
            return "failed_final"

        # Deneme sayacı dönüşümden ÖNCE commit: crash-loop zehirli dosya bekçisi.
        doc.conversion_attempts = (doc.conversion_attempts or 0) + 1
        db.commit()
        attempt_no = doc.conversion_attempts
    except Exception:
        # Sayaç commit'i düştüyse dönüşüme GEÇME (bekçi sayaca dayanır);
        # istisna retry_pending_conversions'ta WARNING'e düşer.
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()

    # ── Dönüşüm (Katman 1 fallback'leri convert_to_pdfa2b'nin içinde) ──
    pdfa_path: Optional[str] = None
    conv_error: Optional[Exception] = None
    try:
        from pdf.pdf_converter import convert_to_pdfa2b
        pdfa_path = convert_to_pdfa2b(spool_path)
        if not (pdfa_path and os.path.exists(pdfa_path)):
            conv_error = RuntimeError("PDF/A-2b dönüşümü başarısız - dosya oluşturulamadı")
    except Exception as e:
        conv_error = e

    if conv_error is not None:
        if attempt_no >= MAX_CONVERSION_ATTEMPTS:
            _finalize_failed(doc_id, attempt_no, str(conv_error))
            return "failed_final"
        logger.warning(
            f"Gece PDF dönüşümü başarısız (doc={doc_id}, deneme "
            f"{attempt_no}/{MAX_CONVERSION_ATTEMPTS}), yarın yeniden: {conv_error}",
            extra={"doc_id": doc_id},
        )
        return "retry"

    # ── Yükleme (senkron; uploader'ın 3-B iç retry'ı dahil) ──
    pdf_name = Path(stored_filename).with_suffix(".pdf").name
    # 2026-09-01: benzersizleştirme öncesi açılmış eski kayıtlarla stem
    # çakışması olabilir — .pdf adı başka belgeye aitse onun dosyasını ezme.
    # exclude self: kendi satırları/önceki gece denemeleri çakışma sayılmaz,
    # aynı ada yeniden yüklemek kendi dosyamız için idempotenttir.
    from services.archive_names import unique_islenmis_name
    pdf_name = unique_islenmis_name(pdf_name, exclude_doc_id=doc_id)
    web_url = None
    try:
        from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint
        response_data = upload_file_to_sharepoint(
            pdfa_path, pdf_name, islenmis_folder, use_date_subfolder=False
        )
        web_url = (response_data or {}).get("webUrl")
    except Exception as upload_err:
        # Dönüşüm BAŞARILIYDI — deneme "tüketilmedi": sayaç geri alınır ki art
        # arda SharePoint kesintili geceler dönüşülebilir belgeyi MAX'a itmesin.
        # (Geri alma sırasında çökülürse sayaç kalır — muhafazakâr, zararsız.)
        _decrement_attempts(doc_id)
        if pdfa_path != spool_path:
            safe_remove(pdfa_path)
        logger.warning(
            f"Gece dönüşümü tamam ama arşiv yüklemesi başarısız (doc={doc_id}), "
            f"yarın yeniden (dönüşüm dahil): {upload_err}",
            extra={"doc_id": doc_id},
        )
        return "upload_retry"

    # ── Başarı: önce yarışan orijinal-yükleme satırları etkisizleştirilir ──
    # (upload_outbox'ta bekleyen islenmis-orijinal satırı sonradan tamamlanıp
    # sharepoint_url'i .udf'e geri EZMESİN), sonra belge tek transaction'da
    # tamamlanır, en son hukukbot açılır (plan 3.8: "ANCAK O ZAMAN").
    try:
        from services.upload_queue import supersede_pending_uploads
        supersede_pending_uploads(doc_id, kind="islenmis")
    except Exception as sup_err:
        logger.warning(f"Orijinal-yükleme satırları etkisizleştirilemedi (doc={doc_id}): {sup_err}")

    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if doc is None:
            return "skipped"
        doc.stored_filename = pdf_name
        doc.upload_attempts = (doc.upload_attempts or 0) + 1
        if web_url:
            doc.sharepoint_url = web_url
            doc.upload_status = "uploaded"
        else:
            # Dosya arşivde ama URL alınamadı (metadata soft-fail) —
            # _record_upload_result semantiğiyle aynı: failed göstergesi dürüst,
            # hukukbot URL'siz belgeyi zaten almaz.
            doc.upload_status = "failed"
        doc.conversion_status = None
        doc.conversion_spool_path = None
        db.commit()
    except Exception as db_err:
        try:
            db.rollback()
        except Exception:
            pass
        # PDF arşive gitti ama belge güncellenemedi — satır pending kaldı, bir
        # sonraki gece yeniden dener (yükleme overwrite, zararsız). Sayaç geri
        # alınır ki DB arızası dolu geceler MAX'ı tüketmesin.
        _decrement_attempts(doc_id)
        if pdfa_path != spool_path:
            safe_remove(pdfa_path)
        logger.warning(f"Gece dönüşümü belgeye işlenemedi (doc={doc_id}): {db_err}")
        return "upload_retry"
    finally:
        db.close()

    safe_remove(spool_path)
    if pdfa_path != spool_path:
        safe_remove(pdfa_path)

    if web_url:
        try:
            from services.export_publisher import notify_hukukbot
            notify_hukukbot(doc_id)
        except Exception as hook_err:
            TechnicalLogger.log("ERROR", f"Hukukbot export hook error (doc={doc_id}): {hook_err}")

    logger.info(
        f"Gece PDF dönüşümü tamamlandı: doc={doc_id} → {pdf_name} "
        f"(deneme {attempt_no}, url={'var' if web_url else 'yok'})",
        extra={"doc_id": doc_id},
    )
    return "completed"


def _decrement_attempts(doc_id: int) -> None:
    db = SessionLocal()
    try:
        doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
        if doc is not None and (doc.conversion_attempts or 0) > 0:
            doc.conversion_attempts = doc.conversion_attempts - 1
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _janitor(now: Optional[datetime] = None) -> None:
    """Spool temizliği (KVKK): nihai failed + soft-delete + sahipsiz dosyalar.

    Yalnız gece job'ının sonunda, aynı thread'de koşar — in-flight satır yok.
    """
    now = now or datetime.now(timezone.utc)
    referenced: set = set()
    db = SessionLocal()
    try:
        rows = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.conversion_spool_path.isnot(None))
            .all()
        )
        for doc in rows:
            # cast: modeller eski stil Column() ile tanımlı, mypy örnek alanını
            # Column[str] / Column[datetime] görür (Mapped[] geçişine kadar).
            path = cast(Optional[str], doc.conversion_spool_path)
            if not path:
                continue
            referenced.add(path)
            cutoff_reason = None
            if doc.deleted_at is not None:
                deleted_at = _as_utc(cast(Optional[datetime], doc.deleted_at))
                if deleted_at and deleted_at < now - timedelta(days=DELETED_SPOOL_RETENTION_DAYS):
                    cutoff_reason = "soft-delete"
            elif doc.conversion_status == "failed":
                created = _as_utc(doc.uploaded_at)
                if created and created < now - timedelta(days=FAILED_SPOOL_RETENTION_DAYS):
                    cutoff_reason = "nihai failed"
            if cutoff_reason is None:
                continue
            if os.path.exists(path) and not safe_remove(path):
                continue  # silinemedi — pointer korunur, sonraki gece dener
            doc.conversion_spool_path = None
            referenced.discard(path)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            logger.info(
                f"Conversion spool temizlendi ({cutoff_reason}, doc={doc.id}): {path}",
                extra={"doc_id": doc.id},
            )
    finally:
        db.close()

    # Sahipsiz dosyalar (doc insert'inden önce çökme artığı)
    try:
        orphan_cutoff = now - timedelta(days=ORPHAN_SPOOL_AGE_DAYS)
        for f in get_conversion_spool_dir().iterdir():
            if not f.is_file() or str(f) in referenced:
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < orphan_cutoff:
                safe_remove(str(f))
                logger.info(f"Sahipsiz conversion spool dosyası silindi: {f}")
    except Exception as e:
        logger.warning(f"Conversion spool orphan süpürmesi başarısız: {e}")


def retry_pending_conversions() -> dict:
    """Gece job'ı: pending dönüşümleri yeniden dener (APScheduler, yalnız lider).

    Dönüş: sonuç sayaçları (smoke/test için). Hiçbir istisna yukarı taşmaz —
    scheduler'ı öldürmemeli; tarama arızası geçicidir (WARNING).
    """
    counts = {"completed": 0, "retry": 0, "upload_retry": 0, "failed_final": 0, "skipped": 0}
    try:
        db = SessionLocal()
        try:
            ids = [
                row.id
                for row in (
                    db.query(models.CaseDocument.id)
                    .filter(
                        models.CaseDocument.conversion_status == "pending",
                        models.CaseDocument.deleted_at.is_(None),
                    )
                    .order_by(models.CaseDocument.id)
                    .all()
                )
            ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Gece dönüşüm taraması başarısız (DB): {e}")
        return counts

    if ids:
        logger.info(f"Gece dönüşüm taraması: {len(ids)} bekleyen belge.")
    islenmis_folder = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
    for doc_id in ids:
        try:
            outcome = _process_one(doc_id, islenmis_folder)
        except Exception as e:
            logger.warning(f"Gece dönüşüm denemesi beklenmedik hata (doc={doc_id}): {e}")
            continue
        counts[outcome] = counts.get(outcome, 0) + 1

    try:
        _janitor()
    except Exception as e:
        logger.warning(f"Conversion spool temizliği başarısız: {e}")

    if ids:
        logger.info(f"Gece dönüşüm taraması bitti: {counts}")
    return counts
