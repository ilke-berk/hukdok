"""G033 — "DB hatası → kapı KAPALI kalır" karakterizasyon ağı (FAZ 0.2 / 0.3 / 0.4).

FAZ 0'da düzeltilen üç hata-yutan kapının backend ayağını regresyona karşı kilitler.
Arıza modeli sinsiydi: DB patladığında uçlar HTTP 200 + **boş/uydurma veri** dönüyor,
çağıran taraf bunu "sorun yok" diye okuyup kapıyı sessizce açıyordu.

Kilitlenen sözleşme tek cümle: **hata ≠ boş sonuç.** Bu yüzden her vaka için hem
başarı hem hata yolu assert'lenir — yalnız hata yolunu test etmek mutasyona karşı
zayıftır (uç her koşulda 503 dönse de testler yeşil kalırdı).

`test_g014_error_gates.py` ile bilinçli kısmi örtüşme var: orası düzeltmenin kendisini
(manager katmanı + tek-ERROR log sözleşmesi) kilitler, burası **başarı/hata çiftini** ve
konfig ucunu kilitler. Testler DB'siz: SessionLocal / manager fonksiyonu monkeypatch'li,
uçlar `TestClient` üzerinden konuşur (desen: `tests/test_case_intake_commit.py`).
"""
import pytest
from sqlalchemy.exc import OperationalError


# ── Sahte DB katmanı ─────────────────────────────────────────────────────────

class _BoomSession:
    """Sorguya inildiği anda patlayan oturum; close() çağrıldı mı izler."""

    def __init__(self):
        self.closed = False

    def query(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    def close(self):
        self.closed = True


class _FakeQuery:
    """routes/cases.py'nin kullandığı zinciri taşıyan asgari sorgu ikizi."""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Sabit satır kümesi dönen sağlıklı oturum ikizi."""

    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def query(self, *args, **kwargs):
        return _FakeQuery(self._rows)

    def close(self):
        self.closed = True


# ── Uygulama fixture'ları ────────────────────────────────────────────────────

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
    # raise_server_exceptions=False: 503'ü HTTP yanıtı olarak görmek istiyoruz;
    # beklenmedik istisna sızarsa test onu 500 olarak ayırt eder.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def config_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import config as config_routes

    app = FastAPI()
    app.include_router(config_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    return TestClient(app, raise_server_exceptions=False)


# ── FAZ 0.2 — mükerrer dava kapısı ───────────────────────────────────────────

def test_duplicate_gate_success_reports_real_matches(cases_app, monkeypatch):
    """FAZ 0.2 başarı yolu: eşleşme VARSA uç onu aynen taşır (kapı kapanabilsin).

    Hata yolunun karşı kutbu: bu test olmadan uç her koşulda 503 dönse de
    "hata ≠ boş" iddiası yeşil kalırdı.
    """
    from routes import cases as cases_routes

    monkeypatch.setattr(
        cases_routes, "find_duplicate_cases",
        lambda esas_no, court=None, tenant_id=None: [
            {"id": 7, "esas_no": esas_no, "court": court, "tracking_no": "34.AHMETYILMA.0007."},
        ],
    )
    r = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1", "court": "ANKARA"})

    assert r.status_code == 200
    assert [m["id"] for m in r.json()["matches"]] == [7]


def test_duplicate_gate_success_reports_genuine_empty(cases_app, monkeypatch):
    """FAZ 0.2 başarı yolu: GERÇEKTEN eşleşme yoksa boş liste meşrudur (200)."""
    from routes import cases as cases_routes

    monkeypatch.setattr(
        cases_routes, "find_duplicate_cases",
        lambda esas_no, court=None, tenant_id=None: [],
    )
    r = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1"})

    assert r.status_code == 200
    assert r.json() == {"matches": []}


def test_duplicate_gate_db_error_is_not_an_empty_200(cases_app, monkeypatch):
    """FAZ 0.2 hata yolu: DB hatası "mükerrer yok" DEĞİLDİR — 200 + boş matches yok."""
    from routes import cases as cases_routes

    def boom(esas_no, court=None, tenant_id=None):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(cases_routes, "find_duplicate_cases", boom)
    r = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1"})

    assert r.status_code == 503, "mükerrer kapısı hata anında hâlâ 'sorun yok' diyor"
    assert "matches" not in r.json(), "hata yanıtı eşleşme listesi taşımamalı"
    assert r.json().get("detail"), "gövde {'detail': ...} sözleşmesine uymuyor"


def test_duplicate_gate_error_is_distinguishable_from_empty(cases_app, monkeypatch):
    """FAZ 0.2 çekirdek iddia: "bilinmiyor" ile "eşleşme yok" AYNI yanıt olamaz.

    Kapıyı açan da kapatan da çağıran taraftır; ikisini ayırt edemezse FAZ 0.2
    düzeltmesi anlamsızlaşır. Bu test tam olarak o ayrımı kilitler.
    """
    from routes import cases as cases_routes

    monkeypatch.setattr(
        cases_routes, "find_duplicate_cases",
        lambda esas_no, court=None, tenant_id=None: [],
    )
    empty = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1"})

    def boom(esas_no, court=None, tenant_id=None):
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(cases_routes, "find_duplicate_cases", boom)
    failed = cases_app.get("/api/cases/check-duplicate", params={"esas_no": "2024/1"})

    assert empty.status_code != failed.status_code
    assert empty.json() != failed.json()


# ── FAZ 0.4 — ofis no sıra tahsisi ───────────────────────────────────────────

def test_sequence_success_returns_max_plus_one(cases_app, monkeypatch):
    """FAZ 0.4 başarı yolu (isim bloğu): öneri mevcut EN YÜKSEK sıra + 1'dir.

    Değerin 1 OLMAMASI kritik: hata yolundaki eski sabit "1" fallback'i ile
    başarı yolunu ayırt eden şey budur.
    """
    from routes import cases as cases_routes

    session = _FakeSession([("34.AHMETYILMA.0003.HA",), ("34.AHMETYILMA.0007.HA",)])
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get(
        "/api/cases/client-sequence",
        params={"client_name": "AHMET YILMAZ", "name_block": "AHMETYILMA"},  # 10 karakter
    )

    assert r.status_code == 200
    assert r.json() == {"sequence": 8}
    assert session.closed is True


def test_sequence_success_client_name_fallback_path(cases_app, monkeypatch):
    """FAZ 0.4 başarı yolu (fallback): name_block yokken de max+1 — COUNT değil."""
    from routes import cases as cases_routes

    session = _FakeSession([("34.AHMETYILMA.0012.HA",), ("34.AHMETYILMA.0004.HA",)])
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get("/api/cases/client-sequence", params={"client_name": "Ahmet Yılmaz Dr."})

    assert r.status_code == 200
    assert r.json() == {"sequence": 13}, "iki kayıt var diye 3 dönerse COUNT'a geri dönülmüş"


def test_sequence_db_error_does_not_silently_return_one(cases_app, monkeypatch):
    """FAZ 0.4 hata yolu: DB hatasında sessizce {"sequence": 1} DÖNMEZ.

    Eski hâl gerçek sıradan bağımsız "1" önerip dolu bir ofis numarası üretiyor,
    kayıt 409'a düşüyordu (2026-07-16 çakışma kaydı).
    """
    from routes import cases as cases_routes

    session = _BoomSession()
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get("/api/cases/client-sequence", params={"client_name": "AHMET YILMAZ"})

    assert r.status_code == 503
    assert "sequence" not in r.json(), "hata yanıtı hâlâ bir sıra numarası öneriyor"
    assert r.json().get("detail")
    assert session.closed is True, "db.close() finally'si kaybolmuş"


def test_sequence_empty_client_name_early_exit_is_not_an_error(cases_app, monkeypatch):
    """FAZ 0.4 sınır: boş isimdeki erken çıkış (routes/cases.py:145) hata DEĞİL.

    Sorguya hiç inilmediği için 200 + {"sequence": 1} meşrudur; _BoomSession
    sorguya inilseydi patlardı — erken çıkışın kanıtı budur. Bu davranış
    bilinçlidir, 503'e çevirme.
    """
    from routes import cases as cases_routes

    session = _BoomSession()
    monkeypatch.setattr(cases_routes, "SessionLocal", lambda: session)

    r = cases_app.get("/api/cases/client-sequence", params={"client_name": ""})

    assert r.status_code == 200
    assert r.json() == {"sequence": 1}
    assert session.closed is True


# ── FAZ 0.3 — zorunlu alan kapısını besleyen konfig ucu ──────────────────────

def test_required_case_fields_success_is_never_empty(config_app):
    """FAZ 0.3 başarı yolu: uç zorunlu alan listesini TAM döner.

    Zorunlu alan kapısını besleyen kaynak budur; boş liste = kapı tamamen açık
    (hiçbir alan zorunlu değil). Tek doğruluk kaynağı backend/required_fields.py.
    """
    from required_fields import PARTY_TC_FIELD, REQUIRED_CASE_FIELDS

    r = config_app.get("/api/config/required_case_fields")

    assert r.status_code == 200
    body = r.json()
    assert body["fields"] == REQUIRED_CASE_FIELDS
    assert len(body["fields"]) > 0, "zorunlu alan listesi boşalırsa kapı sessizce açılır"
    assert body["party_rule"] == PARTY_TC_FIELD


def test_required_case_fields_survives_db_outage(config_app, monkeypatch):
    """FAZ 0.3 hata yolu: erişilebilir her oturum fabrikası patlasa da liste boşalmaz.

    Kilitlenen tasarım kararı: zorunlu alan tanımı statik modülden gelir, DB'ye
    hiç inilmez. Uç bir gün DB okumasına çevrilir ve hata yutan bir fallback
    eklenirse (bkz. reference_lists.get_items → istisnada []), bu test kırmızıya
    döner. `reference_lists` SessionLocal'ı modül düzeyinde bağladığı için
    (`from database import SessionLocal`) her iki bağ da ayrı ayrı yamalanır —
    yalnız `database`i yamalamak o yolu kaçırırdı.
    """
    import database
    from managers import reference_lists

    def boom():
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(database, "SessionLocal", boom)
    monkeypatch.setattr(reference_lists, "SessionLocal", boom)

    r = config_app.get("/api/config/required_case_fields")

    assert r.status_code == 200
    assert len(r.json()["fields"]) > 0, "DB arızası zorunlu alan kapısını açmamalı"


def test_reference_list_endpoint_swallows_db_error_today(config_app, monkeypatch):
    """FAZ 0.3 BULGU (karakterizasyon — düzeltme DEĞİL, bugünkü hâlin fotoğrafı).

    Genel referans listesi uçları (`/api/config/lawyers` vb.) DB hatasında
    `reference_lists.get_items` sayesinde HTTP 200 + `[]` döner. Yani "liste
    gerçekten boş" ile "DB çöktü" çağıran taraftan AYIRT EDİLEMEZ; frontend'in
    G019 ile eklediği CONFIG_LIST_ERROR ayrımı bu uçta karşılıksız kalır.

    Bu uçlar zorunlu alan kapısını BESLEMEZ (o kapı yukarıdaki statik uçtan
    beslenir), bu yüzden G033 kapsamında davranış değiştirilmedi — bulgu görev
    raporuna NOT olarak yazıldı, ayrı görev konusudur. Test bugünkü davranışı
    kilitler: biri bunu 503'e çevirdiğinde bilinçli bir karar olduğunu görsün.
    """
    from types import SimpleNamespace

    from managers import reference_lists
    from routes import config as config_routes

    # Süreç-içi cache boş → uç DB fallback'ine iner.
    monkeypatch.setattr(
        config_routes.DynamicConfig, "get_instance",
        staticmethod(lambda: SimpleNamespace(get_lawyers=lambda: [])),
    )

    def boom():
        raise OperationalError("SELECT 1", {}, RuntimeError("db down"))

    monkeypatch.setattr(reference_lists, "SessionLocal", boom)

    r = config_app.get("/api/config/lawyers")

    assert r.status_code == 200
    assert r.json() == [], "davranış değişti — bilinçliyse bu testi ve G033 raporunu güncelle"
