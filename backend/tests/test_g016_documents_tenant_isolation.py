"""G016 — GET /api/documents tenant/sahip izolasyonu.

Bağlantısız (case_id NULL) belgeler eskiden tenant kısıtını deliyordu: filtredeki
üçüncü `case_id IS NULL` şartı yüzünden her kullanıcı her bağlantısız belgeyi
listeliyordu. Kural artık `auth_helpers.get_tenant_owned_document` ile aynı —
bağlantısızı yalnız yükleyen görür.

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu
koşulur; `routes.documents.SessionLocal` monkeypatch'lenir.
"""
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"
USER_A = {"tid": T1, "preferred_username": "a@hanyaloglu.com"}
USER_B = {"tid": T2, "preferred_username": "b@lexisbio.com"}


@pytest.fixture()
def db_env(monkeypatch):
    """Paylaşılan in-memory sqlite + routes.documents.SessionLocal yönlendirmesi."""
    from database import Base
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
    yield SimpleNamespace(sessions=maker, route=documents, models=models)
    engine.dispose()


def _seed(db_env):
    """İki tenant'ın davaları + her kullanıcının bağlantısız belgesi."""
    models = db_env.models
    db = db_env.sessions()
    try:
        case1 = models.Case(tracking_no="2026/T1-1", tenant_id=T1)
        case2 = models.Case(tracking_no="2026/T2-1", tenant_id=T2)
        case_legacy = models.Case(tracking_no="2026/LEGACY-1", tenant_id=None)
        db.add_all([case1, case2, case_legacy])
        db.flush()

        def _doc(name, case_id, uploader, mode):
            return models.CaseDocument(
                case_id=case_id,
                original_filename=name,
                stored_filename=name,
                link_mode=mode,
                uploaded_by_email=uploader,
            )

        db.add_all([
            _doc("t1-bagli.pdf", case1.id, USER_A["preferred_username"], "LINKED"),
            _doc("t2-bagli.pdf", case2.id, USER_B["preferred_username"], "LINKED"),
            _doc("legacy-bagli.pdf", case_legacy.id, USER_A["preferred_username"], "LINKED"),
            _doc("a-bagsiz.pdf", None, USER_A["preferred_username"], "UNLINKED"),
            _doc("b-bagsiz.pdf", None, USER_B["preferred_username"], "UNLINKED"),
            _doc("sahipsiz-bagsiz.pdf", None, None, "UNLINKED"),
        ])
        db.commit()
    finally:
        db.close()


def _names(db_env, tenant_id, user, **kw):
    docs = db_env.route.get_all_documents(tenant_id=tenant_id, user=user, **kw)
    return {d["original_filename"] for d in docs}


# ─── Bağlantısız belgelerde izolasyon (asıl açık) ────────────────────────────

def test_unlinked_documents_isolated_between_users(db_env):
    _seed(db_env)
    a = _names(db_env, T1, USER_A, link_mode="UNLINKED")
    b = _names(db_env, T2, USER_B, link_mode="UNLINKED")

    assert a == {"a-bagsiz.pdf"}, "A başkasının bağlantısız belgesini görüyor"
    assert b == {"b-bagsiz.pdf"}, "B başkasının bağlantısız belgesini görüyor"
    assert not (a & b)


def test_unlinked_document_without_uploader_is_hidden(db_env):
    """uploaded_by_email NULL → sahip doğrulanamaz, kimseye listelenmez."""
    _seed(db_env)
    assert "sahipsiz-bagsiz.pdf" not in _names(db_env, T1, USER_A)
    assert "sahipsiz-bagsiz.pdf" not in _names(db_env, T2, USER_B)


def test_identity_claim_fallback_and_case_insensitive(db_env):
    """preferred_username yoksa upn, o da yoksa email; karşılaştırma harf duyarsız."""
    _seed(db_env)
    for claim in ("preferred_username", "upn", "email"):
        user = {"tid": T1, claim: "A@Hanyaloglu.COM"}
        assert "a-bagsiz.pdf" in _names(db_env, T1, user), claim


def test_tokenless_identity_sees_no_unlinked(db_env):
    """Üç claim de yoksa fail-closed: hiçbir bağlantısız belge dönmez."""
    _seed(db_env)
    got = _names(db_env, T1, {"tid": T1})
    assert not any(n.endswith("bagsiz.pdf") for n in got)
    assert "t1-bagli.pdf" in got, "bağlı belgeler etkilenmemeliydi"


# ─── Bağlı belgelerin mevcut davranışı korunuyor ─────────────────────────────

def test_linked_documents_behaviour_unchanged(db_env):
    _seed(db_env)
    a = _names(db_env, T1, USER_A, link_mode="LINKED")
    b = _names(db_env, T2, USER_B, link_mode="LINKED")

    # tenant_id NULL (legacy paylaşımlı havuz) her tenant'a görünür
    assert a == {"t1-bagli.pdf", "legacy-bagli.pdf"}
    assert b == {"t2-bagli.pdf", "legacy-bagli.pdf"}


def test_deleted_case_documents_hidden(db_env):
    """Soft-delete edilmiş davanın belgeleri listelenmez (mevcut davranış)."""
    from datetime import datetime

    _seed(db_env)
    models = db_env.models
    db = db_env.sessions()
    try:
        case = db.query(models.Case).filter(models.Case.tenant_id == T1).first()
        case.deleted_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    assert "t1-bagli.pdf" not in _names(db_env, T1, USER_A)


def test_deleted_document_hidden(db_env):
    """Soft-delete edilmiş bağlantısız belge sahibine de görünmez."""
    from datetime import datetime

    _seed(db_env)
    models = db_env.models
    db = db_env.sessions()
    try:
        doc = db.query(models.CaseDocument).filter(
            models.CaseDocument.original_filename == "a-bagsiz.pdf"
        ).first()
        doc.deleted_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    assert "a-bagsiz.pdf" not in _names(db_env, T1, USER_A)


# ─── Sözleşme bekçileri ──────────────────────────────────────────────────────

def test_endpoint_reads_identity(db_env):
    """Uç sahip kontrolü yapabilmek için kimliği okumalı — `user` bağımlılığı şart."""
    sig = inspect.signature(db_env.route.get_all_documents)
    assert "user" in sig.parameters, "get_all_documents kimlik bağımlılığını kaybetmiş"


def test_endpoint_uses_shared_tenant_helper(db_env):
    """Elle yazılmış or_(tenant_id==x, is_(None)) kopyası geri gelmemeli."""
    src = inspect.getsource(db_env.route.get_all_documents)
    assert "tenant_filter_clause" in src
    assert "tenant_id.is_(None)" not in src
