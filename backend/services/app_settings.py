"""Uygulama düzeyi aç/kapa ayarlarının TEK okuma/yazma yolu.

`models.AppSetting` anahtar-değer satırlarını yönetir. Referans listelerinden
(managers/reference_lists) farkı: burada seed yoktur — satır yoksa
`SETTINGS_REGISTRY`'deki varsayılan geçerlidir; satır yalnız yönetici ayarı
DEĞİŞTİRDİĞİNDE yazılır (routes/admin.py uçları). Yani "kapalı" varsayılanlı
bir özellik, deploy sonrası hiçbir migrasyon/seed gerektirmeden kapalı başlar.

Okuma yolu belge onay akışının (confirm) içinden de çağrılır; bu yüzden
DB hatasında istisna YÜKSELTİLMEZ — WARNING loglanır ve varsayılan döner
(varsayılanlar güvenli taraftır: özellik kapalı). Yazma yolundaki hata ise
çağırana yükselir (yönetici ucu 500 görmeli, sessizce "kaydettim" dememeli).

`db` verilmezse fonksiyonlar kendi kısa oturumunu açar/kapatır (G082'deki
servis deseni) — testler `app_settings.SessionLocal`'ı monkeypatch'ler.
"""
import logging
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# Bilinen ayarların kayıt defteri — yönetici ucu yalnız buradaki anahtarları
# kabul eder (serbest anahtar yazımı kapalı). Şimdilik hepsi bool.
#
# client_notice_enabled: Müvekkil bilgilendirme maili ("[Müvekkil Bilgilendirme]"
# konulu, sorumlu avukata giden ve avukatın müvekkile ilettiği metin) üretilsin
# mi? Varsayılan KAPALI — kullanıcı kararı (2026-09-01): yönetici panelinden
# açılana kadar hiçbir belgede gitmez.
SETTINGS_REGISTRY: dict[str, dict[str, Any]] = {
    "client_notice_enabled": {
        "default": False,
        "label": "Müvekkil bilgilendirme maili",
        "description": (
            "Belge onayında, sorumlu avukata müvekkile iletmesi için "
            "\"[Müvekkil Bilgilendirme]\" konulu ayrı bir e-posta hazırlanır. "
            "Kapalıyken bu mail hiçbir belgede gönderilmez."
        ),
    },
}


def _parse_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def _get_row(session: Session, key: str) -> Optional[models.AppSetting]:
    return session.query(models.AppSetting).filter(models.AppSetting.key == key).first()


def get_setting_bool(key: str, db: Optional[Session] = None) -> bool:
    """Ayarın etkin değerini döndürür (satır yoksa registry varsayılanı).

    DB hatasında varsayılana düşer (WARNING) — okuma yolu confirm akışını
    düşürmemeli; varsayılanlar güvenli (kapalı) taraftır.
    """
    spec = SETTINGS_REGISTRY[key]
    default: bool = spec["default"]
    session: Optional[Session] = db
    own_session = session is None
    try:
        if session is None:
            session = SessionLocal()
        row = _get_row(session, key)
        raw = cast(Optional[str], row.value) if row is not None else None
        return _parse_bool(raw, default)
    except Exception as e:
        logger.warning(f"Ayar okunamadı ({key}) — varsayılan ({default}) kullanılıyor: {e}")
        return default
    finally:
        if own_session and session is not None:
            session.close()


def set_setting_bool(key: str, value: bool, updated_by: Optional[str] = None,
                     db: Optional[Session] = None) -> None:
    """Ayarı yazar (upsert). Bilinmeyen anahtar KeyError; DB hatası yükselir."""
    if key not in SETTINGS_REGISTRY:
        raise KeyError(key)
    session: Optional[Session] = db
    own_session = session is None
    if session is None:
        session = SessionLocal()
    try:
        row = _get_row(session, key)
        if row is None:
            row = models.AppSetting(key=key)
            session.add(row)
        row.value = "true" if value else "false"
        row.updated_by = updated_by
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def list_settings(db: Optional[Session] = None) -> list[dict[str, Any]]:
    """Yönetici paneli için tüm bilinen ayarlar + etkin değerleri."""
    session: Optional[Session] = db
    own_session = session is None
    if session is None:
        session = SessionLocal()
    try:
        rows = {cast(str, r.key): r for r in session.query(models.AppSetting).all()}
        out: list[dict[str, Any]] = []
        for key, spec in SETTINGS_REGISTRY.items():
            row = rows.get(key)
            updated_at = row.updated_at if row is not None else None
            out.append({
                "key": key,
                "value": _parse_bool(cast(Optional[str], row.value) if row is not None else None, spec["default"]),
                "default": spec["default"],
                "label": spec["label"],
                "description": spec["description"],
                "updated_by": cast(Optional[str], row.updated_by) if row is not None else None,
                "updated_at": updated_at.isoformat() if updated_at is not None else None,
            })
        return out
    finally:
        if own_session:
            session.close()


def client_notice_enabled(db: Optional[Session] = None) -> bool:
    """Müvekkil bilgilendirme özelliği açık mı? (yönetici anahtarı)"""
    return get_setting_bool("client_notice_enabled", db=db)
