"""Faz 5-B (G003, plan 5.3): HTTP durum kodu disiplini.

Kilitlenen davranışlar:
  1. UNIQUE ihlali tespiti SQLSTATE 23505 + kısıt ADI ile yapılır; mesaj
     metnine bakan eski eşleme kalktı (yanlış pozitif: `uq_cases_sistem_no`).
  2. Mükerrer referans-listesi kaydı → 409 (api.py'deki DuplicateItemError
     handler'ı), gerçek arıza → 500.
  3. Olmayan/görünmeyen dava güncellemesi → 404 (eskiden 500).
  4. Doygunluk sinyalleri → 503, gövde biçimi 5-A'nın /confirm 503'üyle aynı
     ({"detail": "..."}) — 4-A frontend'i bunu zaten işliyor.
  5. Log sözleşmesi: 503 ağı yeni deneme-düzeyi ERROR üretmez.
"""
import logging
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from db_errors import (
    UNIQUE_VIOLATION_SQLSTATE,
    is_unique_violation,
    unique_violation_constraint,
)
from managers.case_manager import TRACKING_NO_UNIQUE_INDEX


# ── Yardımcılar: gerçek psycopg2 hatasının şekli ─────────────────────────────
# Canlı DB'de doğrulanan alanlar: orig.pgcode == "23505",
# orig.diag.constraint_name == "ix_cases_tracking_no" (UNIQUE INDEX ihlalinde
# de dolar). psycopg3'te kod `sqlstate` altındadır.


def _pg_error(pgcode: str, constraint: str = None, attr: str = "pgcode"):
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    setattr(orig, attr, pgcode)
    return IntegrityError("INSERT ...", {}, orig)


# ── db_errors ────────────────────────────────────────────────────────────────


def test_unique_violation_detected_by_sqlstate_not_message():
    exc = _pg_error(UNIQUE_VIOLATION_SQLSTATE, "ix_cases_tracking_no")
    assert is_unique_violation(exc) is True
    assert unique_violation_constraint(exc) == "ix_cases_tracking_no"


def test_psycopg3_sqlstate_attribute_also_supported():
    exc = _pg_error(UNIQUE_VIOLATION_SQLSTATE, "ix_cases_tracking_no", attr="sqlstate")
    assert is_unique_violation(exc, "ix_cases_tracking_no") is True


def test_other_sqlstates_are_not_unique_violations():
    # 23503 = foreign_key_violation, 23502 = not_null_violation
    assert is_unique_violation(_pg_error("23503", "cases_client_id_fkey")) is False
    assert unique_violation_constraint(_pg_error("23502")) is None
    assert is_unique_violation(RuntimeError("duplicate key value violates unique")) is False


def test_constraint_name_must_match_when_given():
    """Aynı tabloda başka bir UNIQUE (uq_cases_sistem_no) tracking_no
    çakışması sanılmamalı — eski string eşlemesinin yanlış pozitifi."""
    sistem_no = _pg_error(UNIQUE_VIOLATION_SQLSTATE, "uq_cases_sistem_no")
    assert is_unique_violation(sistem_no) is True                      # UNIQUE, evet
    assert is_unique_violation(sistem_no, TRACKING_NO_UNIQUE_INDEX) is False


def test_unknown_constraint_name_does_not_match_a_named_expectation():
    unnamed = _pg_error(UNIQUE_VIOLATION_SQLSTATE, None)
    assert unique_violation_constraint(unnamed) == ""
    assert is_unique_violation(unnamed) is True
    assert is_unique_violation(unnamed, TRACKING_NO_UNIQUE_INDEX) is False


def test_case_manager_no_longer_string_matches():
    """Bekçi: tespit metne geri dönerse bu test kırılır."""
    import inspect

    from managers import case_manager

    src = inspect.getsource(case_manager.add_case)
    assert '"tracking_no" in str' not in src
    assert "is_unique_violation" in src


# ── Referans listeleri: mükerrer kayıt → DuplicateItemError → 409 ────────────


def test_add_item_converts_unique_violation_to_duplicate_error(monkeypatch):
    """Ön kontrolü atlatan çakışma (yarış / harf varyantı) 500 değil 409."""
    from managers import reference_lists

    class _FakeQuery:
        def filter(self, *a, **kw):
            return self

        def all(self):
            return []

        def first(self):
            return None

    class _FakeSession:
        def query(self, *a, **kw):
            return _FakeQuery()

        def add(self, obj):
            pass

        def commit(self):
            raise _pg_error(UNIQUE_VIOLATION_SQLSTATE, "ix_statuses_code")

        def close(self):
            pass

    monkeypatch.setattr(reference_lists, "SessionLocal", _FakeSession)
    with pytest.raises(reference_lists.DuplicateItemError) as exc:
        reference_lists.add_item("statuses", code="X1", name="Yeni Durum")
    assert "zaten listede mevcut" in str(exc.value)


def test_add_item_keeps_false_for_real_failures(monkeypatch):
    from managers import reference_lists

    class _FakeSession:
        def query(self, *a, **kw):
            raise RuntimeError("DB patladı")

        def close(self):
            pass

    monkeypatch.setattr(reference_lists, "SessionLocal", _FakeSession)
    assert reference_lists.add_item("statuses", code="X1", name="Yeni Durum") is False


# ── Route katmanı (gerçek api.app: middleware + exception handler'lar dahil) ──


@pytest.fixture()
def client(monkeypatch):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın.
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from routes.config import require_admin

    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    app.dependency_overrides[require_admin] = lambda: user
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def _case_payload():
    return {"tracking_no": "2026/0001", "esas_no": "2026/1", "parties": [], "lawyers": []}


# 404 — olmayan kayıt


def test_update_missing_case_is_404_not_500(client, monkeypatch):
    from routes import cases

    monkeypatch.setattr(cases, "update_case", lambda *a, **kw: None)
    resp = client.put("/api/cases/9999", json=_case_payload())
    assert resp.status_code == 404
    assert "bulunamadı" in resp.json()["detail"]


def test_update_case_real_failure_stays_500(client, monkeypatch):
    from routes import cases

    monkeypatch.setattr(cases, "update_case", lambda *a, **kw: False)
    resp = client.put("/api/cases/1", json=_case_payload())
    assert resp.status_code == 500


def test_update_case_success_unchanged(client, monkeypatch):
    from routes import cases

    monkeypatch.setattr(cases, "update_case", lambda *a, **kw: True)
    resp = client.put("/api/cases/1", json=_case_payload())
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# 409 — mükerrer referans-listesi kaydı


def test_duplicate_config_item_is_409(client, monkeypatch):
    from managers.reference_lists import DuplicateItemError
    from routes import config as config_routes

    def _dup(*a, **kw):
        raise DuplicateItemError('"Yeni Durum" zaten listede mevcut')

    monkeypatch.setattr(config_routes, "add_status", _dup)
    resp = client.post("/api/config/statuses", json={"code": "X1", "name": "Yeni Durum"})
    assert resp.status_code == 409
    assert resp.json() == {"detail": '"Yeni Durum" zaten listede mevcut'}


def test_config_add_real_failure_stays_500(client, monkeypatch):
    from routes import config as config_routes

    monkeypatch.setattr(config_routes, "add_status", lambda *a, **kw: False)
    resp = client.post("/api/config/statuses", json={"code": "X1", "name": "Yeni Durum"})
    assert resp.status_code == 500


def test_duplicate_email_recipient_is_409(client, monkeypatch):
    from managers.reference_lists import DuplicateItemError
    from routes import config as config_routes

    def _dup(*a, **kw):
        raise DuplicateItemError('"a@b.com" zaten listede mevcut')

    monkeypatch.setattr(config_routes, "add_email_recipient", _dup)
    resp = client.post(
        "/api/config/email_recipients", json={"name": "A", "email": "a@b.com"}
    )
    assert resp.status_code == 409


# 400 — doğrulama


def test_missing_required_field_is_400(client):
    resp = client.request(
        "DELETE", "/api/config/email_recipients", json={"email": ""}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email required"


# 503 — doygunluk


def test_conversion_timeout_is_503_with_busy_body(client, monkeypatch, caplog):
    from routes import cases
    from services import document_pipeline

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="gs", timeout=240)

    monkeypatch.setattr(cases, "update_case", _timeout)
    with caplog.at_level(logging.WARNING):
        resp = client.put("/api/cases/1", json=_case_payload())
    assert resp.status_code == 503
    # 5-A /confirm 503'üyle AYNI gövde biçimi ve AYNI metin
    assert resp.json() == {"detail": document_pipeline.CONVERSION_BUSY_DETAIL}
    assert "TEKRAR YÜKLEMEYİN" in resp.json()["detail"]
    # Log sözleşmesi: doygunluk deneme-düzeyidir → ERROR değil WARNING
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_db_unavailable_is_503(client, monkeypatch):
    from routes import cases

    def _down(*a, **kw):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(cases, "update_case", _down)
    resp = client.put("/api/cases/1", json=_case_payload())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "TEKRAR GÖNDERMEYİN" in detail


def test_saturation_handlers_are_registered():
    from api import app

    assert subprocess.TimeoutExpired in app.exception_handlers
    assert OperationalError in app.exception_handlers


def test_conversion_busy_503_body_shape_is_shared():
    """3 numaralı bulgu: /confirm'ün 5-A gövdesi ile yeni 503'ler aynı biçimde
    ({"detail": str}) — 4-A frontend'i tek yol biliyor, ikinci şekil çıkmasın."""
    from services import document_pipeline

    assert isinstance(document_pipeline.CONVERSION_BUSY_DETAIL, str)
