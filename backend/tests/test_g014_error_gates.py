"""G014 — hata yutan kapılar: mükerrer dava tespiti + ofis no sıra tahsisi.

Kilitlenen sözleşme: "hata ≠ boş veri". İki uç arıza anında BAŞARILI görünen
bir cevap üretiyordu:

  1. `find_duplicate_cases` istisnada boş liste döndürüyordu →
     `/api/cases/check-duplicate` HTTP 200 + `{"matches": []}` → mükerrer dava
     kapısı sessizce açılıyor, aynı esas no ikinci kez kaydedilebiliyordu.
  2. `/api/cases/client-sequence` istisnada sabit `{"sequence": 1}` döndürüyordu
     → gerçek sıradan bağımsız numara önerisi, 409 çakışması.

Her ikisi de artık 503 ({"detail": ...}) veriyor. Testler DB'siz: SessionLocal
sahte bir oturumla değiştirilip sorgu anında patlatılıyor (conftest dummy URL).
"""
import pytest
from sqlalchemy.exc import OperationalError


class _BoomSession:
    """Sorguda patlayan sahte DB oturumu; close() çağrıldı mı izler."""

    def __init__(self):
        self.closed = False

    def query(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    def close(self):
        self.closed = True


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
    # raise_server_exceptions=False: 503'ü HTTP yanıtı olarak görmek istiyoruz,
    # beklenmedik istisna sızarsa da test 500 ile ayırt eder.
    return TestClient(app, raise_server_exceptions=False)


# ── 1. Mükerrer dava kapısı ──────────────────────────────────────────────────

def test_find_duplicate_cases_propagates_db_error(monkeypatch):
    """Manager katmanı: istisna yutulup boş liste DÖNMEZ, oturum yine kapanır."""
    from managers import case_manager

    session = _BoomSession()
    monkeypatch.setattr(case_manager, "SessionLocal", lambda: session)

    with pytest.raises(OperationalError):
        case_manager.find_duplicate_cases("2024/123", court="ANKARA", tenant_id="tenant-1")
    assert session.closed is True, "db.close() finally'si kaybolmuş"


def test_check_duplicate_route_does_not_report_no_match_on_db_error(cases_app, monkeypatch):
    """Route katmanı: DB hatasında 200 + boş matches YOK; 503 var."""
    from routes import cases as cases_routes

    def boom(esas_no, court=None, tenant_id=None):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(cases_routes, "find_duplicate_cases", boom)
    r = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1", "court": "ANKARA"})

    assert r.status_code == 503, "mükerrer kapısı hata anında hâlâ 'sorun yok' diyor"
    assert r.json().get("matches") is None, "hata yanıtında matches alanı olmamalı"
    assert r.json().get("detail"), "gövde {'detail': ...} sözleşmesine uymuyor"


def test_check_duplicate_logs_single_error(cases_app, monkeypatch, caplog):
    """Log sözleşmesi: nihai başarısızlık TEK ERROR (manager artık log yazmıyor)."""
    from routes import cases as cases_routes

    def boom(esas_no, court=None, tenant_id=None):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(cases_routes, "find_duplicate_cases", boom)
    with caplog.at_level("ERROR"):
        cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1"})

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1, f"beklenen 1 ERROR, bulunan {len(errors)}"


# ── 2. Ofis no sıra tahsisi ──────────────────────────────────────────────────

def test_client_sequence_does_not_fall_back_to_one_on_db_error(cases_app, monkeypatch):
    """DB hatasında sabit 1 DÖNMEZ — dolu numara önerip 409 üretiyordu."""
    from routes import cases as cases_routes

    session = _BoomSession()
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get("/api/cases/client-sequence", params={"client_name": "AHMET YILMAZ"})

    assert r.status_code == 503
    assert "sequence" not in r.json(), "hata yanıtı hâlâ bir sıra numarası öneriyor"
    assert r.json().get("detail")
    assert session.closed is True, "db.close() finally'si kaybolmuş"


def test_client_sequence_name_block_path_also_fails_loud(cases_app, monkeypatch):
    """name_block (tercih edilen) yolu da aynı sözleşmeye tabi."""
    from routes import cases as cases_routes

    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: _BoomSession())
    r = cases_app.get(
        "/api/cases/client-sequence",
        params={"client_name": "AHMET YILMAZ", "name_block": "AHMETYILMA"},  # 10 karakter
    )
    assert r.status_code == 503
    assert "sequence" not in r.json()


def test_empty_client_name_still_returns_sequence_one(cases_app, monkeypatch):
    """Bilinçli erken çıkış (routes/cases.py:146) hata DEĞİL — davranışı korunur:
    isim yokken sorgu hiç çalışmaz, öneri 1'dir."""
    from routes import cases as cases_routes

    session = _BoomSession()  # sorguya inilirse patlar → erken çıkış kanıtı
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get("/api/cases/client-sequence", params={"client_name": ""})

    assert r.status_code == 200
    assert r.json() == {"sequence": 1}
    assert session.closed is True
