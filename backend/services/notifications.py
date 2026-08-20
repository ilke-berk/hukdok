"""Uygulama içi bildirimin TEK yazma yolu (G081).

`models.Notification` satırları YALNIZ buradan açılır. Sebep: `dedupe_key`
idempotency anahtarı bir DB kısıtıdır (`uq_notifications_dedupe`, database.py
madde 37) ve kısıtın çakışmasını "hata" değil "zaten var" olarak yorumlayan
mantık tek yerde durmalıdır — üretici tarafta (gece tarayıcısı, yükleme
retry'ı) her çağrının try/except yazması hem tekrar hem de sessiz sapma
kaynağı olurdu.

İdempotency sözleşmesi:
  - `dedupe_key` DOLU → aynı anahtarla ikinci çağrı satır İKİLEMEZ; mevcut
    kaydın id'si döner ve mevcut satır GÜNCELLENMEZ (okundu işareti, gövde,
    tarih — hepsi ilk yazımdaki hâliyle kalır). Kullanıcının okuduğu bir
    bildirimi gece işi yeniden "okunmamış" yapmaz.
  - `dedupe_key` BOŞ/NULL → dedupe uygulanmaz, her çağrı yeni satır açar
    (Postgres UNIQUE index'i çok NULL'a izin verir). Bilinçli tekrar
    üretilebilen bildirimler için.

Yarış davranışı: iki süreç aynı anahtarla aynı anda yazarsa ikincinin INSERT'i
birincinin COMMIT'ini bekler ve ardından IntegrityError alır; SAVEPOINT geri
alınıp satır yeniden okunur (READ COMMITTED'da yeni statement yeni snapshot
görür) ve o id döner. `begin_nested()` bilinçli: düz `rollback()` çağıranın
aynı oturumdaki işini de geri alırdı.

Kanal: yalnız uygulama içi. **E-posta gönderimi bu sistemin parçası değildir**
(kullanıcı kararı, 2026-08-20) — bu modül ağ çağrısı yapmaz.

Log sözleşmesi: bu modül ERROR üretmez. Dedupe çakışması NORMAL akıştır
(DEBUG), beklenmedik DB hatası çağırana yükselir — nihai başarısızlığı
loglamak çağıranın işidir.
"""
import datetime as dt
import logging
from typing import Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


def normalize_email(value: Optional[str]) -> str:
    """Alıcı e-postasının kanonik hâli — sorgu ve yazma AYNI dönüşümü kullanır.

    Bildirim sahipliği e-posta eşitliğine dayanır; token'dan gelen UPN'in
    büyük/küçük harfi sağlayıcıya göre değişebilir (`Ad.Soyad@…` vs
    `ad.soyad@…`). Kayıt küçük harfle yazılır, okuma da küçük harfle sorar.
    """
    return (value or "").strip().lower()


def create_notification(
    db: Session,
    *,
    recipient_email: str,
    type: str,
    title: str,
    body: Optional[str] = None,
    severity: str = "info",
    tenant_id: Optional[str] = None,
    case_id: Optional[int] = None,
    document_id: Optional[int] = None,
    due_date: Optional[dt.date] = None,
    dedupe_key: Optional[str] = None,
) -> int:
    """Bildirim satırını açar (ya da dedupe ile mevcut olanı bulur) ve id döner.

    Çağrı BAŞARILIYSA satır commit edilmiştir — çağıranın ayrıca commit'lemesi
    gerekmez. Zorunlu alanlar boşsa `ValueError` yükselir: alıcısı ya da başlığı
    olmayan bildirim kullanıcıya hiçbir şey söylemez, sessizce yazılmasındansa
    üretim yerinde patlaması yeğdir.
    """
    email = normalize_email(recipient_email)
    if not email:
        raise ValueError("recipient_email zorunlu")
    ntype = (type or "").strip()
    if not ntype:
        raise ValueError("type zorunlu")
    baslik = (title or "").strip()
    if not baslik:
        raise ValueError("title zorunlu")

    key = (dedupe_key or "").strip() or None
    if key is not None:
        mevcut = _find_by_dedupe(db, key)
        if mevcut is not None:
            logger.debug("Bildirim zaten var (dedupe_key=%s)", key)
            return mevcut

    row = models.Notification(
        tenant_id=tenant_id,
        recipient_email=email,
        type=ntype,
        severity=(severity or "info").strip() or "info",
        title=baslik,
        body=body,
        case_id=case_id,
        document_id=document_id,
        due_date=due_date,
        dedupe_key=key,
    )
    try:
        # SAVEPOINT: çakışmada yalnız bu INSERT geri alınır, çağıranın aynı
        # oturumdaki işi ayakta kalır.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        if key is None:
            raise
        mevcut = _find_by_dedupe(db, key)
        if mevcut is None:
            # Tekillik dışında bir kısıt patladı (FK vb.) — yutulmaz.
            raise
        logger.debug("Bildirim yarışı dedupe ile çözüldü (dedupe_key=%s)", key)
        return mevcut

    db.commit()
    return cast(int, row.id)


def _find_by_dedupe(db: Session, dedupe_key: str) -> Optional[int]:
    """Anahtara sahip satırın id'si (yoksa None)."""
    row = (
        db.query(models.Notification.id)
        .filter(models.Notification.dedupe_key == dedupe_key)
        .first()
    )
    return int(row[0]) if row else None
