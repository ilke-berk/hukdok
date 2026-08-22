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

Üreticiler
----------
`notify_document_processed` (G082): belge arşive yüklenip `sharepoint_url`
COMMIT edildikten sonra davanın sorumlu avukat(lar)ına "belge işlendi"
bildirimi yazar. Alıcı `services.notification_targeting` (G080) ile çözülür;
mail gönderim yollarına DOKUNULMAZ — mailin kime gittiği değişmez, bildirim
metni yalnız o mailin sonucunu bilgi olarak taşır.
"""
import datetime as dt
import logging
import os
from typing import Any, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# ─── Retention (G097) ────────────────────────────────────────────────────────
#
# Tablo başka hiçbir yoldan küçülmez: her eşik daralması yeni satır açar
# (süre×alıcı başına 4'e kadar), `dismissed_at`'i yazan uç yok. Purge kuralı
# tek cümle: **okunmuş VE N günden eski satır silinir; okunmamış satır ASLA
# silinmez** — kullanıcı görmediği uyarıyı kaybetmesin. Okunmamış-ama-eski
# satırlar sayılıp loglanır ("okunmayan uyarı birikiyor mu" ölçüm noktası).
#
# N `config/settings.py` sözleşmesiyle okunur: boot'ta bir kez, bozuk değer
# uygulamayı DÜŞÜRMEZ (WARNING + varsayılan). settings.py'ye alan eklenmedi —
# bildirim politikası limit/bütçe değil, kendi modülünde durur (confirm
# idempotency RETENTION_DAYS'i gibi).
DEFAULT_NOTIFICATION_RETENTION_DAYS = 90


def _parse_retention_days(raw: Optional[str]) -> int:
    """`NOTIFICATION_RETENTION_DAYS` değerini toleranslı ayrıştırır.

    Boş/eksik → varsayılan. Sayı değilse ya da 1'den küçükse WARNING +
    varsayılan: 0 gün "bugün okunanı bu gece sil" demek olurdu, negatif anlamsız.
    """
    if raw is None or not raw.strip():
        return DEFAULT_NOTIFICATION_RETENTION_DAYS
    try:
        gun = int(raw.strip())
    except (TypeError, ValueError):
        gun = 0
    if gun < 1:
        logger.warning(
            "Gecersiz env degeri NOTIFICATION_RETENTION_DAYS=%r — varsayilan kullaniliyor: %s",
            raw, DEFAULT_NOTIFICATION_RETENTION_DAYS,
        )
        return DEFAULT_NOTIFICATION_RETENTION_DAYS
    return gun


#: Okunmuş bildirimin saklanma süresi (gün). Tek kaynak; tüketici burayı okur.
NOTIFICATION_RETENTION_DAYS = _parse_retention_days(os.environ.get("NOTIFICATION_RETENTION_DAYS"))


def _retention_cutoff(bugun: Optional[dt.date]) -> dt.datetime:
    """`created_at < cutoff` sınırı (UTC, tz-aware — kolon timestamptz)."""
    gun = bugun or dt.datetime.now(dt.timezone.utc).date()
    baslangic = dt.datetime(gun.year, gun.month, gun.day, tzinfo=dt.timezone.utc)
    return baslangic - dt.timedelta(days=NOTIFICATION_RETENTION_DAYS)


def count_unread_stale(bugun: Optional[dt.date] = None, db: Optional[Session] = None) -> int:
    """Okunmamış ama retention sınırından eski satır sayısı (silinmez, ölçülür)."""
    session = db if db is not None else SessionLocal()
    try:
        cutoff = _retention_cutoff(bugun)
        return int(
            session.query(models.Notification.id)
            .filter(models.Notification.read_at.is_(None))
            .filter(models.Notification.created_at < cutoff)
            .count()
        )
    finally:
        if db is None:
            session.close()


def purge_old_notifications(bugun: Optional[dt.date] = None, db: Optional[Session] = None) -> int:
    """Okunmuş (`read_at IS NOT NULL`) ve N günden eski bildirimleri siler.

    Okunmamış satıra DOKUNMAZ. `bugun` yalnız test/elle koşu içindir (sınır
    UTC gün başından geriye N gün). Silinen satır sayısını döner; commit
    burada yapılır. İstisna çağırana yükselir — nihai başarısızlığı loglamak
    çağıranın işidir (modül sözleşmesi).
    """
    session = db if db is not None else SessionLocal()
    try:
        cutoff = _retention_cutoff(bugun)
        silinen = (
            session.query(models.Notification)
            .filter(models.Notification.read_at.isnot(None))
            .filter(models.Notification.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        session.commit()
        return int(silinen or 0)
    except Exception:
        session.rollback()
        raise
    finally:
        if db is None:
            session.close()

# "Belge işlendi" bildiriminin tür etiketi (frontend filtresi bunu tüketecek).
DOC_PROCESSED_TYPE = "belge_islendi"

# Müvekkil bilgilendirme mailinin sonucu bildirim METNİNDE bilgi olarak geçer:
# None = hiç gönderilmedi/atlandı, True = gönderildi, False = denendi ve hata.
DOC_PROCESSED_MAIL_TEXT: dict[Optional[bool], str] = {
    True: "Müvekkil bilgilendirmesi gönderildi.",
    False: "Müvekkil bilgilendirmesi gönderilemedi.",
    None: "Müvekkil bilgilendirmesi gönderilmedi.",
}


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


# ─── Üretici: "belge işlendi" (G082) ─────────────────────────────────────────

def mail_status_text(email_sent: Optional[bool]) -> str:
    """Belgenin müvekkil-maili durumunu bildirim cümlesine çevirir.

    `email_sent` üç değerlidir (`models.CaseDocument.email_sent`): None hiç
    denenmedi/atlandı, True gönderildi, False denendi ve hata aldı. Bildirim
    metni bu durumu yalnız BİLGİ olarak taşır — bu modül mail göndermez ve
    mevcut mail yollarına dokunmaz.
    """
    if email_sent is None:
        return DOC_PROCESSED_MAIL_TEXT[None]
    return DOC_PROCESSED_MAIL_TEXT[bool(email_sent)]


def document_processed_dedupe_key(document_id: int, recipient_email: str) -> str:
    """"Belge işlendi" bildiriminin idempotency anahtarı.

    Önek G082 tanımındaki `doc-processed:<doc_id>`; alıcı e-postası BİLİNÇLİ
    olarak anahtara eklenir. Sebep: `dedupe_key` GLOBAL tekildir
    (`uq_notifications_dedupe`) ve bir bildirim satırı TEK `recipient_email`
    taşır — çıplak anahtar, iki sorumlusu olan davada ("Tuğçe Üngör
    Yanık;Serap Turgal", G080 bu ayracı bilinçli destekler) ikinci avukatın
    bildirimini sessizce yutardı. Tek alıcılı davada (ölçülen normal hâl)
    davranış tanımdakiyle aynıdır: aynı belge için ikinci çağrı satır İKİLEMEZ.
    """
    return f"doc-processed:{document_id}:{normalize_email(recipient_email)}"


def _case_label(case: Any) -> str:
    """Bildirim gövdesindeki dava künyesi: ofis dosya no + esas no + mahkeme."""
    parcalar = []
    for deger in (
        getattr(case, "tracking_no", None),
        getattr(case, "esas_no", None),
        getattr(case, "court", None),
    ):
        metin = (deger or "").strip() if isinstance(deger, str) else ""
        if metin:
            parcalar.append(metin)
    return " · ".join(parcalar)


def notify_document_processed(document_id: int, db: Optional[Session] = None) -> list[int]:
    """Arşivlenen belge için davanın sorumlu avukat(lar)ına bildirim üretir.

    ÇAĞRI ZAMANI: yalnız `sharepoint_url` COMMIT edildikten sonra
    (`upload_queue._attempt_upload` başarı yolu). Yükleme başarısızsa bildirim
    ÜRETİLMEZ — kullanıcıya "işlendi" demek yanlış bilgi olurdu.

    Alıcı çözülemezse (sorumlu alanı boş, dış avukat, tanınmayan yazım) bildirim
    üretilmez ve **WARNING** loglanır: bu nihai bir başarısızlık değildir, belge
    arşive girmiştir — log sözleşmesi gereği ERROR YAZILMAZ.

    `db` verilmezse kendi oturumunu açar (yükleme akışının transaction'ından
    yapısal olarak ayrık kalsın). Yazılan/mevcut bildirim id'lerini döner.
    """
    if not document_id:
        return []
    session = db if db is not None else SessionLocal()
    try:
        doc = (
            session.query(models.CaseDocument)
            .filter(models.CaseDocument.id == document_id)
            .first()
        )
        if doc is None:
            logger.warning(
                "Belge işlendi bildirimi üretilemedi: belge kaydı yok (doc=%s)",
                document_id,
            )
            return []

        case = None
        case_id = cast(Optional[int], doc.case_id)
        if case_id:
            case = session.query(models.Case).filter(models.Case.id == case_id).first()

        from services.notification_targeting import resolve_case_recipients
        recipients = resolve_case_recipients(session, case) if case is not None else []
        if not recipients:
            sorumlu = getattr(case, "responsible_lawyer_name", None) if case is not None else None
            logger.warning(
                "Belge işlendi bildirimi hedefsiz: sorumlu avukat çözülemedi "
                "(doc=%s, case=%s, sorumlu=%r)",
                document_id, case_id, sorumlu,
            )
            return []

        belge_adi = (
            cast(Optional[str], doc.belge_turu_adi)
            or cast(Optional[str], doc.original_filename)
            or "Belge"
        )
        kunye = _case_label(case)
        title = f"Belge işlendi: {belge_adi}"
        satirlar = [f"Dava: {kunye}"] if kunye else []
        satirlar.append(f"Belge: {cast(Optional[str], doc.original_filename) or belge_adi}")
        satirlar.append(mail_status_text(cast(Optional[bool], doc.email_sent)))
        body = "\n".join(satirlar)

        ids: list[int] = []
        for email in recipients:
            ids.append(
                create_notification(
                    session,
                    recipient_email=email,
                    type=DOC_PROCESSED_TYPE,
                    title=title,
                    body=body,
                    severity="info",
                    tenant_id=cast(Optional[str], getattr(case, "tenant_id", None)),
                    case_id=case_id,
                    document_id=document_id,
                    dedupe_key=document_processed_dedupe_key(document_id, email),
                )
            )
        logger.info(
            "Belge işlendi bildirimi yazıldı (doc=%s, alıcı=%s)",
            document_id, len(ids),
        )
        return ids
    finally:
        if db is None:
            session.close()
