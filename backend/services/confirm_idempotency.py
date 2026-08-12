"""/confirm idempotency kaydı (Faz 3-D, plan madde 3.5).

Sorun: nginx 504'ünden (ya da ağ kopmasından) sonra kullanıcı "onayla"ya
tekrar basıyor; frontend aynı process_id + dosya fallback'iyle /confirm'i
yeniden çağırıyor ve pipeline ikinci kez koşuyor → mükerrer belge kaydı,
mükerrer arşiv yüklemesi, mükerrer e-posta (nginx.conf'ta "mukerrer kayit
kaynagi" diye belgeliydi).

Anahtar seçimi (karar, 3-D): process_id — Idempotency-Key header'ı DEĞİL,
file_hash de DEĞİL. Gerekçe:
  - process_id /confirm formunda ZATEN taşınıyor (Index.tsx her zaman ekler,
    retry'da da aynı kalır) → frontend değişikliği gerektirmez; header
    yaklaşımı Faz 4'ün frontend paketini beklerdi.
  - file_hash /confirm'e ULAŞMIYOR (form alanı yok, PROCESS_CACHE girdisinde
    saklanmıyor); yeniden hesaplamak mümkün ama anlamsal olarak YANLIŞ anahtar:
    aynı dosya bilerek iki kez yüklenebilir (örn. aynı dilekçe iki ayrı davaya)
    — hash dedup meşru tekrarları da yutar. process_id ise tam istenen kapsam:
    "bir sihirbaz oturumu = bir belge kaydı"; kullanıcı sihirbazı baştan
    koşturursa yeni process_id üretilir ve bu bilinçli yeni bir işlemdir.

Kayıt YERİ kararı: DB (models.ConfirmReceipt), süreç içi dict değil —
uvicorn restart'ında kayıt yaşar ve Faz 3-E'nin --workers 2 geçişinde
worker'lar arasında tutarlı kalır (süreç içi sözlük iki durumda da kaçırırdı).

Verdikt akışı (begin):
  ("proceed", None)    → kayıt açıldı (ya da bayat in_progress devralındı);
                         pipeline normal koşar
  ("replay", payload)  → aynı process_id daha önce TAMAMLANMIŞ; saklanan
                         yanıt pipeline koşmadan aynen döndürülür
  ("in_progress", None)→ ilk istek hâlâ koşuyor (504 retry'ının tam kendisi)
                         → 409 "tekrar göndermeyin"
  ("bypass", None)     → DB arızası: idempotency kapısı atlanır, pipeline
                         korumasız koşar — kapı arızası /confirm'i bugünden
                         kötü yapmamalı (upload_queue fallback felsefesi)

Log sözleşmesi (Faz 2-C alarmı ≥5 ERROR/5dk): bu modül hiçbir koşulda ERROR
üretmez — kapı arızaları WARNING'dir (pipeline yine koşar, kullanıcıya
yansıyan nihai başarısızlık yoktur); replay/claim olayları INFO.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, cast

from sqlalchemy.exc import IntegrityError

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# in_progress satırın "bayat" sayılma eşiği. Canlı bir /confirm en fazla
# ~300 sn sürebilir (nginx proxy_read_timeout; GS tavanı 240 sn) — 30 dk
# PROCESS_CACHE TTL'iyle hizalıdır ve yaşayan hiçbir isteği devralmaz.
# Bayat satır = önceki süreç pipeline ortasında öldü (deploy/OOM); belge
# yaratılmadan öldüyse route satırı release eder ve kullanıcı hemen tekrar
# dener. Belge yaratıldıysa route release ETMEZ: satır in_progress kalır,
# aradaki retry'lar 409 alır — ama kilit KALICI DEĞİLDİR; bu eşik dolunca
# begin() satırı devralır (proceed) ve pipeline yeniden koşabilir. Bilinçli
# takas: sonsuza dek kilitli kalmaktansa, 30 dk sonra mükerrer belge riskini
# göze alıp akışı açıyoruz (bkz. routes/processing.py, /confirm except bloğu).
STALE_IN_PROGRESS_SECONDS = 30 * 60

# Tamamlanmış kayıtların tutulma süresi: replay penceresi gerçekte dakikalar;
# 7 gün denetim payıyla birlikte tabloyu sınırlı tutar (begin içinde fırsatçı
# temizlik).
RETENTION_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _age_seconds(ts: Optional[datetime]) -> float:
    """Satır zaman damgasının yaşı; naive damga (test/sqlite) UTC varsayılır."""
    if ts is None:
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_utcnow() - ts).total_seconds()


def begin(process_id: str, owner: Optional[str]) -> Tuple[str, Optional[dict]]:
    """İdempotency kapısı: kaydı aç ya da mevcut kaydın verdiktini döndür.

    Dönüş: (verdikt, replay_payload) — modül docstring'indeki akış.
    """
    db = None
    try:
        db = SessionLocal()

        # Fırsatçı temizlik: RETENTION_DAYS'ten eski kayıtlar (statüden
        # bağımsız) düşer. Tablo küçük (gün başına onlarca satır) — indeks
        # gerektirmez; commit aşağıdaki INSERT'le birlikte gider.
        try:
            cutoff = _utcnow() - timedelta(days=RETENTION_DAYS)
            db.query(models.ConfirmReceipt).filter(
                models.ConfirmReceipt.created_at < cutoff,
            ).delete(synchronize_session=False)
        except Exception:
            db.rollback()

        try:
            db.add(models.ConfirmReceipt(
                process_id=process_id, owner=owner, status="in_progress",
            ))
            db.commit()
            return ("proceed", None)
        except IntegrityError:
            db.rollback()

        row = db.query(models.ConfirmReceipt).filter(
            models.ConfirmReceipt.process_id == process_id
        ).first()
        if row is None:
            # INSERT çakıştı ama satır yok (yarışta silinmiş) — korumasız
            # koşmaktansa çakışma say: kullanıcı bir sonraki denemede geçer.
            return ("in_progress", None)

        row_owner = (row.owner or "").strip().lower()
        requester = (owner or "").strip().lower()
        if row_owner and requester and row_owner != requester:
            # process_id UUID'dir; sahibi farklı bir tekrar ancak patolojik
            # (sızmış id) olabilir — yanıt sızdırmadan generic çakışma dön.
            logger.warning("ConfirmReceipt owner mismatch: %s", process_id)
            return ("in_progress", None)

        if row.status == "completed":
            if not row.response_json:
                logger.warning(
                    "ConfirmReceipt completed ama yanıt boş: %s", process_id
                )
                return ("in_progress", None)
            try:
                # cast: modeller eski stil Column() ile tanımlı, mypy örnek
                # alanını Column[str] görüyor (Mapped[] geçişine kadar).
                payload = json.loads(cast(str, row.response_json))
            except ValueError:
                logger.warning(
                    "ConfirmReceipt yanıtı çözümlenemedi: %s", process_id
                )
                return ("in_progress", None)
            return ("replay", payload)

        # in_progress: yaşayan istek mi, önceki süreçten kalan bayat kilit mi?
        last_touch = cast(Optional[datetime], row.updated_at or row.created_at)
        if _age_seconds(last_touch) < STALE_IN_PROGRESS_SECONDS:
            return ("in_progress", None)

        # Bayat kilit devralma — optimistic guard: iki eşzamanlı devralma
        # denemesinden yalnız biri satırı güncelleyebilir (counter_manager'ın
        # ETag deseniyle aynı ruh).
        seen_updated = row.updated_at
        claimed = db.query(models.ConfirmReceipt).filter(
            models.ConfirmReceipt.process_id == process_id,
            models.ConfirmReceipt.updated_at == seen_updated,
            models.ConfirmReceipt.status == "in_progress",
        ).update(
            {"updated_at": _utcnow(), "owner": owner},
            synchronize_session=False,
        )
        db.commit()
        if claimed:
            logger.info(
                "Bayat in_progress /confirm kaydı devralındı: %s", process_id
            )
            return ("proceed", None)
        return ("in_progress", None)

    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        logger.warning("İdempotency kapısı atlandı (DB arızası): %s", e)
        return ("bypass", None)
    finally:
        if db is not None:
            db.close()


def complete(process_id: str, payload: dict) -> None:
    """Başarılı /confirm yanıtını kaydet — sonraki retry'lar replay alır.

    Best-effort: yazılamazsa WARNING'le geçilir; satır in_progress kalır ve
    STALE eşiğinden sonra devralınabilir (olası mükerrer, bugünkü davranış).
    """
    try:
        db = SessionLocal()
        try:
            db.query(models.ConfirmReceipt).filter(
                models.ConfirmReceipt.process_id == process_id
            ).update(
                {
                    "status": "completed",
                    "response_json": json.dumps(payload, ensure_ascii=False, default=str),
                    "updated_at": _utcnow(),
                },
                synchronize_session=False,
            )
            db.commit()
        except Exception:
            # Faz 3-E (3.6): açık transaction bağlantıda kalmasın; istisna
            # dıştaki except'te WARNING'e düşer (rollback hatası dahil).
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            "ConfirmReceipt tamamlanamadı (%s): %s", process_id, e
        )


def release(process_id: str) -> None:
    """Kaydı sil — pipeline BELGE YARATMADAN düştüğünde çağrılır; retry serbest.

    Belge yaratıldıktan sonra düşen istek için route bunu ÇAĞIRMAZ: satır
    in_progress kalır ve retry 409 alır (yeniden koşmak belgeyi mükerrer
    yaratırdı); bayat eşiği dolunca kilit kendiliğinden çözülür.
    """
    try:
        db = SessionLocal()
        try:
            db.query(models.ConfirmReceipt).filter(
                models.ConfirmReceipt.process_id == process_id
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            # Faz 3-E (3.6): complete() ile aynı gerekçe.
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            "ConfirmReceipt bırakılamadı (%s): %s", process_id, e
        )
