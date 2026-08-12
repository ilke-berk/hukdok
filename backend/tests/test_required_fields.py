"""Zorunlu alan uyarısı testleri (kullanıcı kararı 2026-07-31 rev.2).

Kural: zorunlu alan eksikliği kaydı ENGELLEMEZ — dosya DERDEST açılır,
eksikler missing_required_fields ile panelde uyarı olarak görünür ve
get_cases(missing_required=True) ile filtrelenir. Testler gerçek sorgu
çalıştırmaz (conftest dummy DATABASE_URL).
"""
from types import SimpleNamespace

import pytest

from required_fields import (
    PARTY_TC_FIELD,
    REQUIRED_CASE_FIELDS,
    compute_missing_fields,
)


def _complete_case(**overrides):
    data = {f["field"]: f"deger-{f['field']}" for f in REQUIRED_CASE_FIELDS}
    data["parties"] = [
        {"name": "Ahmet YILMAZ", "role": "DAVACI", "party_type": "CLIENT"},
        {"name": "Karşı Kurum", "role": "DAVALI", "party_type": "COUNTER", "tc_no": "12345678901"},
    ]
    data.update(overrides)
    return data


# ── compute_missing_fields ───────────────────────────────────────────────────

def test_empty_case_reports_all_required_fields():
    missing = compute_missing_fields({}, [])
    fields = {m["field"] for m in missing}
    assert fields == {f["field"] for f in REQUIRED_CASE_FIELDS}


def test_complete_case_reports_nothing():
    assert compute_missing_fields(_complete_case()) == []


def test_whitespace_only_value_counts_as_missing():
    data = _complete_case(esas_no="   ")
    missing = compute_missing_fields(data)
    assert [m["field"] for m in missing] == ["esas_no"]
    assert missing[0]["label"] == "Esas No"


def test_counter_party_without_tc_flags_rule():
    data = _complete_case()
    data["parties"] = [
        {"name": "Karşı Kurum", "role": "DAVALI", "party_type": "COUNTER"},
    ]
    missing = compute_missing_fields(data)
    assert [m["field"] for m in missing] == [PARTY_TC_FIELD["field"]]


def test_no_counter_parties_skips_tc_rule():
    data = _complete_case()
    data["parties"] = [{"name": "Ahmet", "role": "DAVACI", "party_type": "CLIENT"}]
    assert compute_missing_fields(data) == []


def test_parties_accepts_objects_with_attributes():
    data = _complete_case()
    parties = [SimpleNamespace(party_type="COUNTER", tc_no=None, name="X")]
    missing = compute_missing_fields(data, parties)
    assert [m["field"] for m in missing] == [PARTY_TC_FIELD["field"]]


# ── SQL ikizi (compute_missing_fields'ın sorgu karşılığı) ────────────────────
#
# G046'da korele EXISTS'li SQLAlchemy koşulu (`_missing_required_clause`)
# kaldırıldı: sıcak yol artık denormalize `missing_required_bucket` kolonunu
# okuyor. SQL ikizinin yeni görevi backfill + denetim; ayrıntılı kilitleme
# tests/test_g046_missing_required.py'de.

def test_missing_required_sql_covers_every_required_field():
    from required_fields import missing_required_sql

    sql = missing_required_sql()
    for f in REQUIRED_CASE_FIELDS:
        assert f"cases.{f['field']}" in sql, f"{f['field']} SQL ikizinde yok"
    # Karşı taraf TC kuralı da SQL'e çevrilmiş olmalı
    assert "case_parties" in sql


# ── API: rota sırası + parametre geçişi ──────────────────────────────────────

@pytest.fixture()
def cases_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from routes import cases as cases_routes

    app = FastAPI()
    app.include_router(cases_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    return TestClient(app)


def test_api_get_cases_passes_missing_required_param(cases_app, monkeypatch):
    from routes import cases as cases_routes

    seen = {}

    def fake_get_cases(**kwargs):
        seen.update(kwargs)
        return [], 0

    monkeypatch.setattr(cases_routes, "get_cases", fake_get_cases)
    r = cases_app.get("/api/cases", params={"missing_required": "true"})
    assert r.status_code == 200
    assert seen["missing_required"] is True

    seen.clear()
    r = cases_app.get("/api/cases")
    assert r.status_code == 200
    assert seen["missing_required"] is False


def test_api_check_duplicate_route_not_shadowed(cases_app, monkeypatch):
    # /api/cases/check-duplicate, /api/cases/{case_id}'den ÖNCE tanımlı olmalı
    from routes import cases as cases_routes

    seen = {}

    def fake_find(esas_no, court=None, tenant_id=None):
        seen["args"] = (esas_no, court, tenant_id)
        return [{"id": 1, "tracking_no": "T", "esas_no": esas_no,
                 "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "status": "DERDEST",
                 "court_match": True}]

    monkeypatch.setattr(cases_routes, "find_duplicate_cases", fake_find)
    r = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1", "court": "ANKARA"})
    assert r.status_code == 200
    assert seen["args"] == ("2024/1", "ANKARA", "tenant-1")
    assert r.json()["matches"][0]["court_match"] is True
