"""Müvekkil bilgilendirme ana anahtarı (app_settings, 2026-09-01 kullanıcı kararı).

Kilitlenen davranışlar:

1. **Varsayılan KAPALI** — `app_settings` satırı yokken `client_notice_enabled()`
   False döner; dolayısıyla `should_notify_client` hiçbir belge türünde True
   olmaz. Deploy sonrası özellik, yönetici açana kadar kapalı başlar.
2. **Kapı iki katmanlı** — ana anahtar (DB) VE belge türü filtresi
   (`doctype_allows_client_notice`); anahtar açıkken tür filtresi bağımsız
   uygulanmaya devam eder.
3. **Sunucu tarafı kapı** — asıl karar `should_notify_client`'tadır ve
   `/confirm` gövdesindeki `send_client_notice` bayrağı onu AŞAMAZ (arayüz
   kutuyu göstermese bile bayat/elle istek mail üretemez). Tripwire testi
   confirm akışının bu fonksiyonu çağırmaya devam ettiğini bekçiler.
4. **Yönetici uçları** — GET/PUT `/api/admin/settings*` yalnız ADMIN_EMAILS'e,
   bilinmeyen anahtar 404; yazım `updated_by` izi bırakır ve kalıcıdır.
5. **client-notice-target** — `eligible` ana anahtarı da içerir;
   `feature_enabled` alanı arayüze "özellik kapalı" mesajı için ayrı gelir.
6. **Okuma hatası güvenli** — ayar okunamazsa (DB arızası) istisna yükselmez,
   WARNING loglanır ve varsayılan (kapalı) kullanılır; confirm akışı düşmez.

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde gerçek
sorgu koşulur; servis oturumu `app_settings.SessionLocal` monkeypatch'iyle
sqlite'a yönlendirilir (G082 deseni).
"""
import inspect
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ADMIN_MAIL = "yonetici@hanyaloglu-acar.av.tr"
USER_MAIL = "avukat@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"

SETTINGS_URL = "/api/admin/settings"
KEY = "client_notice_enabled"


@pytest.fixture()
def env(monkeypatch):
    """sqlite motoru + app_settings servisi sqlite'a bağlanmış hâlde."""
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    from services import app_settings as svc

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr(svc, "SessionLocal", maker)

    yield SimpleNamespace(models=models, service=svc, db=maker, engine=engine)
    engine.dispose()


# ─── 1+2: varsayılan kapalı, iki katmanlı kapı ───────────────────────────────

def test_varsayilan_kapali(env):
    import email_sender

    assert env.service.client_notice_enabled() is False
    assert email_sender.should_notify_client("TEBLIGAT______") is False
    assert email_sender.should_notify_client(None) is False


def test_acilinca_tum_turlerde_hazirlanir(env):
    import email_sender

    env.service.set_setting_bool(KEY, True, updated_by=ADMIN_MAIL)
    assert env.service.client_notice_enabled() is True
    assert email_sender.should_notify_client("TEBLIGAT______") is True
    assert email_sender.should_notify_client(None) is True

    env.service.set_setting_bool(KEY, False, updated_by=ADMIN_MAIL)
    assert email_sender.should_notify_client("TEBLIGAT______") is False


def test_tur_filtresi_anahtar_acikken_de_uygulanir(env, monkeypatch):
    import email_sender

    env.service.set_setting_bool(KEY, True)
    monkeypatch.setattr(email_sender, "CLIENT_NOTIFY_ALL_DOCTYPES", False)
    monkeypatch.setattr(email_sender, "CLIENT_NOTIFICATION_DOCTYPES", {"KARAR-BLG"})

    assert email_sender.doctype_allows_client_notice("KARAR-BLG") is True
    assert email_sender.doctype_allows_client_notice("TEBLIGAT______") is False
    assert email_sender.should_notify_client("KARAR-BLG") is True
    assert email_sender.should_notify_client("TEBLIGAT______") is False


def test_bilinmeyen_anahtar_yazilamaz(env):
    with pytest.raises(KeyError):
        env.service.set_setting_bool("olmayan_ayar", True)


def test_deger_kalicidir_ve_iz_tasir(env):
    env.service.set_setting_bool(KEY, True, updated_by=ADMIN_MAIL)

    db = env.db()
    try:
        row = db.query(env.models.AppSetting).filter_by(key=KEY).one()
        assert row.value == "true"
        assert row.updated_by == ADMIN_MAIL
    finally:
        db.close()

    listed = {s["key"]: s for s in env.service.list_settings()}
    assert listed[KEY]["value"] is True
    assert listed[KEY]["updated_by"] == ADMIN_MAIL
    assert listed[KEY]["label"]


# ─── 6: okuma hatası güvenli tarafa düşer ────────────────────────────────────

def test_okuma_hatasi_varsayilana_duser_warning_error_yok(env, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    def _patla():
        raise RuntimeError("DB yok")

    monkeypatch.setattr(env.service, "SessionLocal", _patla)
    assert env.service.client_notice_enabled() is False

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert warnings and not errors


def test_yazma_hatasi_yukselir(env, monkeypatch):
    """Yönetici ucu sessizce 'kaydettim' diyemez — yazım hatası istisnadır."""

    def _patla():
        raise RuntimeError("DB yok")

    monkeypatch.setattr(env.service, "SessionLocal", _patla)
    with pytest.raises(RuntimeError):
        env.service.set_setting_bool(KEY, True)


# ─── 3: confirm kapısı tripwire ──────────────────────────────────────────────

def test_confirm_akisi_ana_anahtari_soruyor():
    """`/confirm` gövdesindeki `send_client_notice` bayrağı sunucu kapısını
    aşamaz: akış kararı `should_notify_client`'tan almalı. Fonksiyon çağrısı
    kaldırılırsa bu bekçi düşer (davranış testi confirm'in dosya/SharePoint
    zincirini gerektirdiğinden tripwire bilinçli tercihtir)."""
    from routes import processing

    src = inspect.getsource(processing)
    assert "should_notify_client(belge_turu_kodu)" in src
    assert "send_client_notice" in src


# ─── 4: yönetici uçları ──────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(env, monkeypatch):
    """routes.admin uygulaması; kimlik get_current_user override'ıyla verilir."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import admin as route_mod

    monkeypatch.setenv("ADMIN_EMAILS", ADMIN_MAIL)

    def _client(email=ADMIN_MAIL):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {
            "preferred_username": email, "tid": T1,
        }
        return TestClient(app, raise_server_exceptions=False)

    return _client


def test_admin_listeler_ve_acar(env, admin_client):
    client = admin_client()

    r = client.get(SETTINGS_URL)
    assert r.status_code == 200
    listed = {s["key"]: s for s in r.json()["settings"]}
    assert listed[KEY]["value"] is False

    r = client.put(f"{SETTINGS_URL}/{KEY}", json={"value": True})
    assert r.status_code == 200
    assert r.json()["value"] is True

    listed = {s["key"]: s for s in client.get(SETTINGS_URL).json()["settings"]}
    assert listed[KEY]["value"] is True
    assert listed[KEY]["updated_by"] == ADMIN_MAIL
    assert env.service.client_notice_enabled() is True


def test_admin_olmayan_403(env, admin_client):
    client = admin_client(email=USER_MAIL)

    assert client.get(SETTINGS_URL).status_code == 403
    assert client.put(f"{SETTINGS_URL}/{KEY}", json={"value": True}).status_code == 403
    assert env.service.client_notice_enabled() is False


def test_bilinmeyen_anahtar_404(env, admin_client):
    client = admin_client()

    r = client.put(f"{SETTINGS_URL}/olmayan_ayar", json={"value": True})
    assert r.status_code == 404


# ─── 5: client-notice-target ucu ─────────────────────────────────────────────

@pytest.fixture()
def target_env(env, monkeypatch):
    """routes.cases uygulaması + sqlite'a bağlı SessionLocal + örnek dava."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant
    from routes import cases as route_mod

    monkeypatch.setattr(route_mod, "SessionLocal", env.db)

    db = env.db()
    try:
        case = env.models.Case(
            tracking_no="2026/1000",
            esas_no="2026/1",
            court="Ankara 1. Asliye Hukuk Mahkemesi",
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        case_id = case.id
    finally:
        db.close()

    app = FastAPI()
    app.include_router(route_mod.router)
    app.dependency_overrides[get_current_tenant] = lambda: T1
    client = TestClient(app, raise_server_exceptions=False)

    return SimpleNamespace(client=client, case_id=case_id, url=f"/api/cases/{case_id}/client-notice-target")


def test_target_kapaliyken_eligible_false(env, target_env):
    r = target_env.client.get(target_env.url)
    assert r.status_code == 200
    data = r.json()
    assert data["eligible"] is False
    assert data["feature_enabled"] is False


def test_target_acikken_eligible_true(env, target_env):
    env.service.set_setting_bool(KEY, True)

    data = target_env.client.get(target_env.url).json()
    assert data["eligible"] is True
    assert data["feature_enabled"] is True


def test_target_tur_filtresi_kapatirsa_feature_yine_acik(env, target_env, monkeypatch):
    """Arayüz mesaj ayrımı: tür filtresi engelliyorsa eligible=False ama
    feature_enabled=True kalır ('özellik kapalı' denmez)."""
    import email_sender

    env.service.set_setting_bool(KEY, True)
    monkeypatch.setattr(email_sender, "CLIENT_NOTIFY_ALL_DOCTYPES", False)
    monkeypatch.setattr(email_sender, "CLIENT_NOTIFICATION_DOCTYPES", {"KARAR-BLG"})

    data = target_env.client.get(f"{target_env.url}?belge_turu_kodu=TEBLIGAT______").json()
    assert data["eligible"] is False
    assert data["feature_enabled"] is True

    data = target_env.client.get(f"{target_env.url}?belge_turu_kodu=KARAR-BLG").json()
    assert data["eligible"] is True
