"""G093 testleri: konfigürasyon çürümesi uyarıları.

- (a) DEV_MODE=true + ENV != development → açılışta CRITICAL (CORS wildcard
  + prod tehlikesi satırda); ENV=development ya da DEV_MODE kapalıyken sessiz.
- (b) SHAREPOINT_CLIENT_SECRET_EXPIRES_AT: tanımsızken sessiz; ≤30 gün WARNING;
  geçmiş CRITICAL; bozuk format bir kez WARNING ve istisna yok; secret'ın kendisi
  hiçbir satırda yok.

caplog BİLİNÇLİ kullanılmıyor: api'nin ilk import'u configure_logging() ile
kök handler'ları değiştirir (bkz. test_faz2_alerting). Handler doğrudan hedef
logger'a takılır.
"""
import logging
from datetime import date

import pytest

from sharepoint import auth_graph

SECRET_VALUE = "cok-gizli-secret-degeri-XYZ"


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def root_records():
    # api'nin İLK import'u configure_logging() ile kök handler'ları sıfırlar;
    # handler ondan SONRA takılmalı, yoksa ilk testte sökülür.
    import api  # noqa: F401

    handler = _ListHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler.records
    root.removeHandler(handler)


@pytest.fixture
def auth_records():
    handler = _ListHandler()
    target = logging.getLogger("AuthGraph")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _messages(records, level):
    return [r.getMessage() for r in records if r.levelno == level]


# ─── (a) DEV_MODE prod guard ─────────────────────────────────────────────────

def test_dev_mode_outside_development_logs_critical(monkeypatch, root_records):
    import api

    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("ENV", "production")
    assert api.warn_if_dev_mode_outside_development() is True
    crits = _messages(root_records, logging.CRITICAL)
    assert len(crits) == 1
    msg = crits[0]
    assert "DEV_MODE=true" in msg
    assert "allow_origin_regex" in msg and "allow_credentials" in msg
    assert "PROD'DA TEHLİKELİDİR" in msg


def test_dev_mode_with_env_unset_logs_critical(monkeypatch, root_records):
    import api

    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    assert api.warn_if_dev_mode_outside_development() is True
    assert len(_messages(root_records, logging.CRITICAL)) == 1


def test_dev_mode_in_development_is_silent(monkeypatch, root_records):
    import api

    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("ENV", "development")
    assert api.warn_if_dev_mode_outside_development() is False
    assert _messages(root_records, logging.CRITICAL) == []


@pytest.mark.parametrize("dev_mode", [None, "", "false", "0"])
def test_dev_mode_off_is_silent(monkeypatch, root_records, dev_mode):
    import api

    if dev_mode is None:
        monkeypatch.delenv("DEV_MODE", raising=False)
    else:
        monkeypatch.setenv("DEV_MODE", dev_mode)
    monkeypatch.setenv("ENV", "production")
    assert api.warn_if_dev_mode_outside_development() is False
    assert _messages(root_records, logging.CRITICAL) == []


def test_g5_guard_still_present_in_lifespan():
    # Mevcut G5 guard'ı (ters yön) aynen duruyor; yeni guard lifespan'den çağrılıyor.
    import inspect

    import api

    src = inspect.getsource(api.lifespan)
    assert "ALLOW_DEV_TENANT" in src and "dev auth bypass DEVRE DIŞI" in src
    assert "warn_if_dev_mode_outside_development()" in src
    assert "check_client_secret_expiry()" in src


# ─── (b) SharePoint secret expiry ────────────────────────────────────────────

TODAY = date(2026, 8, 22)


@pytest.fixture(autouse=True)
def _secret_in_env(monkeypatch):
    # Secret'ın kendisi env'de dursun: hiçbir log satırına sızmadığı doğrulanır.
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", SECRET_VALUE)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_expiry_unset_is_silent(monkeypatch, auth_records, value):
    if value is None:
        monkeypatch.delenv(auth_graph.SECRET_EXPIRES_AT_ENV, raising=False)
    else:
        monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, value)
    assert auth_graph.check_client_secret_expiry(today=TODAY) is None
    assert auth_records == []


def test_expiry_far_away_is_silent(monkeypatch, auth_records):
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, "2027-03-15")
    assert auth_graph.check_client_secret_expiry(today=TODAY) is None
    assert auth_records == []


@pytest.mark.parametrize("days", [30, 12, 0])
def test_expiry_within_threshold_warns_with_days(monkeypatch, auth_records, days):
    from datetime import timedelta

    exp = TODAY + timedelta(days=days)
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, exp.isoformat())
    assert auth_graph.check_client_secret_expiry(today=TODAY) == "warning"
    warns = _messages(auth_records, logging.WARNING)
    assert len(warns) == 1 and len(auth_records) == 1
    assert f"{days} gün sonra" in warns[0]
    assert exp.isoformat() in warns[0]


def test_expiry_threshold_plus_one_is_silent(monkeypatch, auth_records):
    from datetime import timedelta

    exp = TODAY + timedelta(days=auth_graph.SECRET_EXPIRY_WARN_DAYS + 1)
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, exp.isoformat())
    assert auth_graph.check_client_secret_expiry(today=TODAY) is None
    assert auth_records == []


def test_expiry_past_logs_critical(monkeypatch, auth_records):
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, "2026-08-01")
    assert auth_graph.check_client_secret_expiry(today=TODAY) == "critical"
    crits = _messages(auth_records, logging.CRITICAL)
    assert len(crits) == 1 and len(auth_records) == 1
    assert "DOLDU" in crits[0] and "21 gün önce" in crits[0]


def test_expiry_malformed_warns_once_and_does_not_raise(monkeypatch, auth_records):
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, "yarin")
    assert auth_graph.check_client_secret_expiry(today=TODAY) == "warning"
    warns = _messages(auth_records, logging.WARNING)
    assert len(warns) == 1 and len(auth_records) == 1
    assert "ayrıştırılamadı" in warns[0] and "yarin" in warns[0]


@pytest.mark.parametrize("value", ["yarin", "2026-08-01", "2026-09-01", "2027-03-15"])
def test_secret_itself_never_logged(monkeypatch, auth_records, value):
    monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, value)
    auth_graph.check_client_secret_expiry(today=TODAY)
    for rec in auth_records:
        assert SECRET_VALUE not in rec.getMessage()


def test_threshold_is_single_constant():
    # .env.example kabulü göz denetimiyle: repo kökü konteynere mount edilmez.
    assert auth_graph.SECRET_EXPIRY_WARN_DAYS == 30
