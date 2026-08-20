"""G078 — `GET /api/documents/recent` (pano akışı) sözleşmesi.

Uç, avukat panosundaki "Yeni İşlenen — son 24 saat" bölümünü besler. G077 ile
kaldırılan `GET /api/documents`'in yerine geçmez: o uç bağlantısız belgeleri
BAĞLAMAK içindi; bu uç yalnız dava bağlamı OLAN belgeleri kronolojik akış
olarak okur (`case_id IS NULL` satırlar hiç dönmez).

Kilitlenen davranışlar:
  1. saat penceresi (`since_hours`) ve `limit` sınırları (dışında 422),
  2. yetki: `auth_helpers.get_tenant_owned_document` ile AYNI kural —
     dava tenant'ı eşleşmeli (NULL = paylaşılan legacy), silinmiş dava ve
     silinmiş belge dönmez,
  3. `email_sent`/`email_error` üç durumuyla payload'a girer (yalnız OKUNUR),
  4. kaldırılan bağlama uçları geri gelmedi, `link_mode` modeli değişmedi.

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde GERÇEK
sorgu koşulur; `routes.documents.SessionLocal` monkeypatch'lenir (desen:
G077 ile düşen `test_g016_documents_tenant_isolation.py`).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"
USER_A = {"tid": T1, "preferred_username": "a@hanyaloglu.com"}

NOW = datetime.now(timezone.utc)


def _ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


@pytest.fixture()
def client_factory(monkeypatch):
    """Paylaşılan in-memory sqlite + tenant'a göre TestClient üreten fabrika."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import Base
    from dependencies import get_current_tenant, get_current_user
    import models  # noqa: F401 — Base.metadata dolsun
    from routes import documents

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(documents, "SessionLocal", maker)

    def _make(tenant_id: str = T1, user: dict = USER_A):
        app = FastAPI()
        app.include_router(documents.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_tenant] = lambda: tenant_id
        return TestClient(app, raise_server_exceptions=False)

    _make.sessions = maker  # type: ignore[attr-defined]
    _make.models = models  # type: ignore[attr-defined]
    _make.route = documents  # type: ignore[attr-defined]
    yield _make
    engine.dispose()


def _seed(factory):
    """İki tenant + legacy dava; farklı yaşta, mail durumu farklı belgeler."""
    models = factory.models
    db = factory.sessions()
    try:
        case1 = models.Case(tracking_no="2026/T1-1", tenant_id=T1, esas_no="2026/111")
        case2 = models.Case(tracking_no="2026/T2-1", tenant_id=T2, esas_no="2026/222")
        legacy = models.Case(tracking_no="2026/LEGACY-1", tenant_id=None, esas_no="2026/999")
        silinmis = models.Case(
            tracking_no="2026/T1-SILINMIS", tenant_id=T1, deleted_at=_ago(48)
        )
        db.add_all([case1, case2, legacy, silinmis])
        db.flush()

        party = models.CaseParty(
            case_id=case1.id, name="Ayşe Yılmaz", role="Davacı", party_type="CLIENT"
        )
        db.add(party)
        db.flush()

        def _doc(name, case_id, hours_ago, **kw):
            return models.CaseDocument(
                case_id=case_id,
                original_filename=name,
                stored_filename=name,
                link_mode="LINKED" if case_id else "UNLINKED",
                uploaded_at=_ago(hours_ago),
                uploaded_by="Test Kullanıcı",
                uploaded_by_email=USER_A["preferred_username"],
                **kw,
            )

        db.add_all([
            # T1 — mailin üç durumu
            _doc("t1-mail-ok.pdf", case1.id, 1, email_sent=True,
                 belge_turu_adi="Tebligat", case_party_id=party.id),
            _doc("t1-mail-hata.pdf", case1.id, 2, email_sent=False,
                 email_error="SMTP 550", muvekkil_adi="Ali Veli"),
            _doc("t1-mailsiz.pdf", case1.id, 3),
            # Pencere dışı (25 saat)
            _doc("t1-eski.pdf", case1.id, 25),
            # Diğer tenant + legacy paylaşımlı havuz
            _doc("t2-bagli.pdf", case2.id, 1),
            _doc("legacy-bagli.pdf", legacy.id, 5),
            # Silinmiş dava / silinmiş belge / bağlantısız belge
            _doc("silinmis-davanin-belgesi.pdf", silinmis.id, 1),
            _doc("silinmis-belge.pdf", case1.id, 1, deleted_at=_ago(0.5)),
            _doc("bagsiz.pdf", None, 1),
        ])
        db.commit()
    finally:
        db.close()


def _names(client, **params):
    r = client.get("/api/documents/recent", params=params)
    assert r.status_code == 200, r.text
    return {row["original_filename"] for row in r.json()}


# ─── 1. Saat penceresi ───────────────────────────────────────────────────────

def test_default_window_is_last_24_hours(client_factory):
    _seed(client_factory)
    got = _names(client_factory(T1, USER_A))

    assert "t1-mail-ok.pdf" in got
    assert "t1-eski.pdf" not in got, "25 saatlik belge 24 saatlik pencereye sızdı"


def test_wider_window_includes_older_document(client_factory):
    _seed(client_factory)
    got = _names(client_factory(T1, USER_A), since_hours=48)

    assert "t1-eski.pdf" in got, "since_hours genişletilince eski belge dönmeli"


def test_results_are_newest_first_and_limited(client_factory):
    _seed(client_factory)
    client = client_factory(T1, USER_A)

    rows = client.get("/api/documents/recent", params={"limit": 2}).json()
    assert len(rows) == 2, "limit gövdeye uygulanmamış"
    assert [r["original_filename"] for r in rows] == ["t1-mail-ok.pdf", "t1-mail-hata.pdf"]


# ─── 2. Parametre sınırları (dışında 422) ────────────────────────────────────

@pytest.mark.parametrize(
    "params",
    [
        {"since_hours": 0},
        {"since_hours": 721},
        {"since_hours": -1},
        {"limit": 0},
        {"limit": 201},
    ],
)
def test_out_of_range_parameters_are_rejected(client_factory, params):
    _seed(client_factory)
    r = client_factory(T1, USER_A).get("/api/documents/recent", params=params)

    assert r.status_code == 422, f"{params} sınır dışı ama kabul edildi"


@pytest.mark.parametrize("params", [{"since_hours": 1}, {"since_hours": 720}, {"limit": 1}, {"limit": 200}])
def test_boundary_parameters_are_accepted(client_factory, params):
    _seed(client_factory)
    r = client_factory(T1, USER_A).get("/api/documents/recent", params=params)

    assert r.status_code == 200, f"{params} sınır İÇİNDE ama reddedildi"


# ─── 3. Yetki: tenant sızıntısı + soft-delete ────────────────────────────────

def test_other_tenant_documents_are_not_leaked(client_factory):
    _seed(client_factory)
    a = _names(client_factory(T1, USER_A))
    b = _names(client_factory(T2, {"tid": T2, "preferred_username": "b@lexisbio.com"}))

    assert "t2-bagli.pdf" not in a, "T1 kullanıcısı T2 belgesini görüyor"
    assert "t1-mail-ok.pdf" not in b, "T2 kullanıcısı T1 belgesini görüyor"


def test_legacy_null_tenant_case_is_shared(client_factory):
    """tenant_id NULL = paylaşılan legacy havuz → her tenant görür."""
    _seed(client_factory)

    assert "legacy-bagli.pdf" in _names(client_factory(T1, USER_A))
    assert "legacy-bagli.pdf" in _names(
        client_factory(T2, {"tid": T2, "preferred_username": "b@lexisbio.com"})
    )


def test_deleted_case_and_deleted_document_are_hidden(client_factory):
    _seed(client_factory)
    got = _names(client_factory(T1, USER_A))

    assert "silinmis-davanin-belgesi.pdf" not in got, "silinmiş davanın belgesi döndü"
    assert "silinmis-belge.pdf" not in got, "soft-delete edilmiş belge döndü"


def test_unlinked_documents_never_returned(client_factory):
    """case_id IS NULL satır yükleyene bile dönmez — pano akışı dava bağlamı ister."""
    _seed(client_factory)
    got = _names(client_factory(T1, USER_A))

    assert "bagsiz.pdf" not in got
    rows = client_factory(T1, USER_A).get("/api/documents/recent").json()
    assert all(r["case_id"] is not None for r in rows), "payload'da case_id NULL satır var"


# ─── 4. Payload alanları + mail durumunun üç hali ────────────────────────────

def _by_name(client, name):
    rows = client.get("/api/documents/recent", params={"since_hours": 48}).json()
    return next(r for r in rows if r["original_filename"] == name)


def test_payload_contains_pano_fields(client_factory):
    _seed(client_factory)
    row = _by_name(client_factory(T1, USER_A), "t1-mail-ok.pdf")

    assert row["case_id"] is not None
    assert row["tracking_no"] == "2026/T1-1"
    assert row["esas_no"] == "2026/111", "belgede esas yoksa davanın esas'ı dönmeli"
    assert row["belge_turu_adi"] == "Tebligat"
    assert row["muvekkil_adi"] == "Ayşe Yılmaz", "taraf adı payload'da yok"
    assert row["case_party_name"] == "Ayşe Yılmaz"
    assert row["uploaded_by"] == "Test Kullanıcı"
    assert row["uploaded_at"], "uploaded_at boş"
    assert isinstance(row["id"], int)


def test_email_status_three_states(client_factory):
    """Mail GÖNDERİMİ değişmiyor; yalnız durumu panoda görünür oluyor."""
    _seed(client_factory)
    client = client_factory(T1, USER_A)

    ok = _by_name(client, "t1-mail-ok.pdf")
    assert ok["email_sent"] is True and ok["email_error"] is None

    hata = _by_name(client, "t1-mail-hata.pdf")
    assert hata["email_sent"] is False and hata["email_error"] == "SMTP 550"

    mailsiz = _by_name(client, "t1-mailsiz.pdf")
    assert mailsiz["email_sent"] is None and mailsiz["email_error"] is None


def test_document_own_esas_no_wins_over_case(client_factory):
    _seed(client_factory)
    models = client_factory.models
    db = client_factory.sessions()
    try:
        doc = db.query(models.CaseDocument).filter(
            models.CaseDocument.original_filename == "t1-mailsiz.pdf"
        ).first()
        doc.esas_no = "2026/777"
        db.commit()
    finally:
        db.close()

    assert _by_name(client_factory(T1, USER_A), "t1-mailsiz.pdf")["esas_no"] == "2026/777"


# ─── 5. Sözleşme bekçileri: kaldırılan uçlar geri gelmedi ────────────────────

def test_removed_link_endpoints_did_not_return(client_factory):
    """G077 kaldırdı: `GET /api/documents` ve `PATCH /api/documents/{id}/link`."""
    paths = {
        (route.path, method)
        for route in client_factory.route.router.routes
        for method in route.methods
    }

    assert ("/api/documents", "GET") not in paths, "G077 ile kaldırılan liste ucu dirildi"
    assert not any(p.endswith("/link") for p, _ in paths), "belge bağlama ucu geri gelmiş"
    assert ("/api/documents/recent", "GET") in paths


def test_link_mode_model_unchanged(client_factory):
    """`link_mode` veri modeli G078'in kapsamı dışında — dokunulmadı."""
    models = client_factory.models
    col = models.CaseDocument.__table__.columns["link_mode"]

    assert col.nullable is False
    assert col.default.arg == "UNLINKED"


def test_endpoint_uses_shared_tenant_helper(client_factory):
    """Elle yazılmış or_(tenant_id==x, is_(None)) kopyası girmesin."""
    import inspect

    src = inspect.getsource(client_factory.route.get_recent_documents)
    assert "tenant_filter_clause" in src
    assert "tenant_id.is_(None)" not in src
