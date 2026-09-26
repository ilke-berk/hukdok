"""G214 — `case_notes`: davaya tarihli, yazanı belli notlar.

Kilitlenen davranışlar (sözleşme SABİT — G215 frontend paneli buna göre yazıldı):
  1. listeleme: en yeni üstte, silinmişler hariç, satır şekli + `can_delete`,
  2. POST doğrulaması: trim sonrası 1..5000 karakter (boş / yalnız boşluk /
     5001 → 422), 201 + tek not, gövde trim'lenmiş saklanır,
  3. DELETE: yazan 204, başkası 403, yönetici (ADMIN_EMAILS) 204, başka davanın
     notu / olmayan / zaten silinmiş not 404, silinen not listeden düşer,
  4. dava görünürlüğü: soft-silinmiş dava ve tenant dışı dava → TÜM uçlar 404;
     NULL tenant (paylaşımlı havuz) görünür,
  5. oturumsuz istek 401,
  6. migrasyon: ("table", ...) op'u + index AYRI koşulsuz ("index", ...) op'unda;
     dbtest: create_all önceden koşmuş DB'de de index var, table op'u DDL'i
     tablo yokken kurar ve ON DELETE CASCADE çalışır.

DB'siz katman süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar;
dbtest katmanı gerçek Postgres scratch DB'si ister (yoksa SKIP).
"""
import datetime as dt
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import database
from test_migration_path import _live_indexes, _run_init_db, _scratch_database

T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
MAIL_A = "avukat.a@hanyaloglu.com"
MAIL_B = "avukat.b@hanyaloglu.com"
MAIL_ADMIN = "yonetici@hanyaloglu.com"
USER_A = {"tid": T1, "preferred_username": "Avukat.A@Hanyaloglu.com", "name": "Avukat A"}
USER_B = {"tid": T1, "preferred_username": MAIL_B, "name": "Avukat B"}
USER_ADMIN = {"tid": T1, "upn": MAIL_ADMIN, "name": "Yönetici"}
USER_T2 = {"tid": T2, "preferred_username": "diger@baska.com"}

INDEX_ADI = "idx_case_notes_case_created"


def _case_notes_ops():
    return [op for op in database._MIGRATIONS if op[1] == "case_notes"]


@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import Base, get_db
    from dependencies import get_current_user
    import models
    from routes import case_notes as route_mod

    monkeypatch.setenv("ADMIN_EMAILS", f"{MAIL_ADMIN}, baska.yonetici@x.com")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_conn, _rec):  # sqlite'ta FK eylemleri varsayılan KAPALI
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _client(user=USER_A):
        app = FastAPI()
        app.include_router(route_mod.router)
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user

        def _db_override():
            db = maker()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db_override
        return TestClient(app, raise_server_exceptions=False)

    def _case(tracking_no, tenant_id=None, deleted=False):
        db = maker()
        try:
            case = models.Case(
                tracking_no=tracking_no,
                status="DERDEST",
                tenant_id=tenant_id,
                deleted_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc) if deleted else None,
            )
            db.add(case)
            db.commit()
            return case.id
        finally:
            db.close()

    def _note(case_id, body="not", author=MAIL_A, created=None, deleted=False):
        db = maker()
        try:
            note = models.CaseNote(
                case_id=case_id,
                body=body,
                author_email=author,
                author_name=None,
                created_at=created or dt.datetime(2026, 9, 20, 10, 0, tzinfo=dt.timezone.utc),
                deleted_at=dt.datetime(2026, 9, 21, tzinfo=dt.timezone.utc) if deleted else None,
            )
            db.add(note)
            db.commit()
            return note.id
        finally:
            db.close()

    def _row(note_id):
        db = maker()
        try:
            return db.get(models.CaseNote, note_id)
        finally:
            db.close()

    yield SimpleNamespace(client=_client, case=_case, note=_note, row=_row)
    engine.dispose()


# ─── 1. Listeleme ────────────────────────────────────────────────────────────

def test_liste_en_yeni_ustte_silinmisler_haric(env):
    cid = env.case("HA.T.1")
    eski = env.note(cid, "eski", created=dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.timezone.utc))
    yeni = env.note(cid, "yeni", created=dt.datetime(2026, 9, 25, 9, 0, tzinfo=dt.timezone.utc))
    orta = env.note(cid, "orta", created=dt.datetime(2026, 9, 10, 9, 0, tzinfo=dt.timezone.utc))
    env.note(cid, "silik", created=dt.datetime(2026, 9, 26, 9, 0, tzinfo=dt.timezone.utc), deleted=True)
    baska = env.case("HA.T.2")
    env.note(baska, "başka dava")

    r = env.client().get(f"/api/cases/{cid}/notes")

    assert r.status_code == 200
    assert [n["id"] for n in r.json()] == [yeni, orta, eski]


def test_liste_satir_sekli_ve_can_delete(env, monkeypatch):
    cid = env.case("HA.T.1")
    kendi = env.note(cid, "benim", author=MAIL_A)
    elin = env.note(cid, "onun", author=MAIL_B,
                    created=dt.datetime(2026, 9, 19, tzinfo=dt.timezone.utc))

    satirlar = {n["id"]: n for n in env.client(USER_A).get(f"/api/cases/{cid}/notes").json()}

    assert set(satirlar[kendi]) == {"id", "body", "author_name", "author_email", "created_at", "can_delete"}
    assert satirlar[kendi]["can_delete"] is True
    assert satirlar[elin]["can_delete"] is False
    ts = dt.datetime.fromisoformat(satirlar[kendi]["created_at"])
    assert ts.utcoffset() == dt.timedelta(0), "created_at UTC ofsetli değil"
    assert ts == dt.datetime(2026, 9, 20, 10, 0, tzinfo=dt.timezone.utc)

    yonetici = env.client(USER_ADMIN).get(f"/api/cases/{cid}/notes").json()
    assert all(n["can_delete"] for n in yonetici), "yönetici her notu silebilmeli"


# ─── 2. POST ─────────────────────────────────────────────────────────────────

def test_post_201_trimlenmis_govde_ve_yazan_kimligi(env):
    cid = env.case("HA.T.1")

    r = env.client(USER_A).post(f"/api/cases/{cid}/notes", json={"body": "  Duruşma ertelendi.  "})

    assert r.status_code == 201
    not_ = r.json()
    assert not_["body"] == "Duruşma ertelendi."
    assert not_["author_email"] == MAIL_A, "yazan e-postası küçük harfe indirgenmedi"
    assert not_["author_name"] == "Avukat A"
    assert not_["can_delete"] is True
    assert dt.datetime.fromisoformat(not_["created_at"]).utcoffset() == dt.timedelta(0)
    assert env.row(not_["id"]).body == "Duruşma ertelendi."

    liste = env.client(USER_A).get(f"/api/cases/{cid}/notes").json()
    assert [n["id"] for n in liste] == [not_["id"]]


@pytest.mark.parametrize("govde", ["", "   \n\t ", "x" * 5001, "  " + "x" * 5001 + "  "])
def test_post_gecersiz_govde_422(env, govde):
    cid = env.case("HA.T.1")

    r = env.client().post(f"/api/cases/{cid}/notes", json={"body": govde})

    assert r.status_code == 422
    assert env.client().get(f"/api/cases/{cid}/notes").json() == []


def test_post_sinir_5000_karakter_trim_sonrasi_kabul(env):
    cid = env.case("HA.T.1")

    r = env.client().post(f"/api/cases/{cid}/notes", json={"body": "   " + "x" * 5000 + "   "})

    assert r.status_code == 201
    assert len(r.json()["body"]) == 5000


def test_post_body_eksik_422(env):
    cid = env.case("HA.T.1")
    assert env.client().post(f"/api/cases/{cid}/notes", json={}).status_code == 422


# ─── 3. DELETE ───────────────────────────────────────────────────────────────

def test_yazan_silebilir_204_ve_listeden_duser(env):
    cid = env.case("HA.T.1")
    nid = env.note(cid, author=MAIL_A)

    r = env.client(USER_A).delete(f"/api/cases/{cid}/notes/{nid}")

    assert r.status_code == 204
    assert env.row(nid).deleted_at is not None, "silme SOFT olmalı (satır durur)"
    assert env.client(USER_A).get(f"/api/cases/{cid}/notes").json() == []


def test_baskasinin_notu_403(env):
    cid = env.case("HA.T.1")
    nid = env.note(cid, author=MAIL_A)

    r = env.client(USER_B).delete(f"/api/cases/{cid}/notes/{nid}")

    assert r.status_code == 403
    assert env.row(nid).deleted_at is None


def test_yonetici_baskasinin_notunu_silebilir_204(env):
    cid = env.case("HA.T.1")
    nid = env.note(cid, author=MAIL_A)

    r = env.client(USER_ADMIN).delete(f"/api/cases/{cid}/notes/{nid}")

    assert r.status_code == 204
    assert env.row(nid).deleted_at is not None


def test_baska_davanin_notu_404(env):
    cid = env.case("HA.T.1")
    diger = env.case("HA.T.2")
    nid = env.note(diger, author=MAIL_A)

    r = env.client(USER_A).delete(f"/api/cases/{cid}/notes/{nid}")

    assert r.status_code == 404
    assert env.row(nid).deleted_at is None


def test_olmayan_ve_silinmis_not_404(env):
    cid = env.case("HA.T.1")
    silik = env.note(cid, author=MAIL_A, deleted=True)

    assert env.client(USER_A).delete(f"/api/cases/{cid}/notes/999999").status_code == 404
    assert env.client(USER_A).delete(f"/api/cases/{cid}/notes/{silik}").status_code == 404


# ─── 4. Dava görünürlüğü ─────────────────────────────────────────────────────

def _uc_kodlari(env, user, cid, nid):
    c = env.client(user)
    return (
        c.get(f"/api/cases/{cid}/notes").status_code,
        c.post(f"/api/cases/{cid}/notes", json={"body": "x"}).status_code,
        c.delete(f"/api/cases/{cid}/notes/{nid}").status_code,
    )


def test_silinmis_dava_tum_uclar_404(env):
    cid = env.case("HA.T.1", deleted=True)
    nid = env.note(cid, author=MAIL_A)

    assert _uc_kodlari(env, USER_A, cid, nid) == (404, 404, 404)
    assert env.row(nid).deleted_at is None


def test_tenant_disi_dava_tum_uclar_404(env):
    cid = env.case("HA.T.1", tenant_id=T1)
    nid = env.note(cid, author="diger@baska.com")

    assert _uc_kodlari(env, USER_T2, cid, nid) == (404, 404, 404)
    assert env.row(nid).deleted_at is None


def test_kendi_tenantinin_ve_paylasimli_havuzun_davasi_gorunur(env):
    kendi = env.case("HA.T.1", tenant_id=T1)
    havuz = env.case("HA.T.2", tenant_id=None)

    assert env.client(USER_A).get(f"/api/cases/{kendi}/notes").status_code == 200
    assert env.client(USER_T2).get(f"/api/cases/{havuz}/notes").status_code == 200


def test_olmayan_dava_404(env):
    assert env.client().get("/api/cases/424242/notes").status_code == 404


# ─── 5. Oturum ───────────────────────────────────────────────────────────────

def test_oturumsuz_401(env):
    cid = env.case("HA.T.1")
    nid = env.note(cid)
    c = env.client(user=None)

    assert c.get(f"/api/cases/{cid}/notes").status_code == 401
    assert c.post(f"/api/cases/{cid}/notes", json={"body": "x"}).status_code == 401
    assert c.delete(f"/api/cases/{cid}/notes/{nid}").status_code == 401


def _duz_yollar(routes):
    """FastAPI `include_router`ı sarmalar (`_IncludedRouter`) — düzleştir (G081 deseni)."""
    for r in routes:
        ic = getattr(r, "original_router", None)
        if ic is not None:
            yield from _duz_yollar(ic.routes)
            continue
        for method in getattr(r, "methods", []) or []:
            yield (r.path, method)


def test_router_uygulamaya_kayitli():
    from api import app

    yollar = set(_duz_yollar(app.routes))
    assert ("/api/cases/{case_id}/notes", "GET") in yollar
    assert ("/api/cases/{case_id}/notes", "POST") in yollar
    assert ("/api/cases/{case_id}/notes/{note_id}", "DELETE") in yollar


# ─── 6. Migrasyon ────────────────────────────────────────────────────────────

def test_migrasyon_table_op_ve_ayri_kosulsuz_index_op():
    ops = _case_notes_ops()
    turler = [op[0] for op in ops]
    assert turler == ["table", "index"], turler

    table_op, index_op = ops
    assert "ON DELETE CASCADE" in table_op[2]
    assert table_op[3] == [], "index table op'una gömülmemeli (koşullu op tuzağı)"
    assert index_op[2] == [
        f"CREATE INDEX IF NOT EXISTS {INDEX_ADI} ON case_notes (case_id, created_at)"
    ]


def test_model_fk_cascade_ve_kolonlar():
    import models

    tablo = models.CaseNote.__table__
    assert {c.name for c in tablo.columns} == {
        "id", "case_id", "body", "author_email", "author_name", "created_at", "deleted_at",
    }
    fk = next(iter(tablo.c.case_id.foreign_keys))
    assert fk.column.table.name == "cases" and fk.ondelete == "CASCADE"
    assert tablo.c.created_at.server_default is not None
    assert tablo.c.created_at.type.timezone is True
    assert tablo.c.deleted_at.nullable is True


# ─── dbtest: gerçek Postgres (scratch DB; yoksa SKIP) ────────────────────────

@pytest.fixture(scope="module")
def pg_admin():
    """test_migration_path.admin_engine'in yereli (fixture import F811 üretir)."""
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")
    admin = create_engine(
        url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        admin.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G214 dbtest atlandı")
    yield admin
    admin.dispose()


@pytest.mark.dbtest
def test_pg_create_all_onceden_kosmus_dbde_index_var(pg_admin):
    """create_all tabloyu index'siz yaratır; ("table", ...) op'u atlanır; index
    yine de koşulsuz ("index", ...) op'undan gelir. İkinci koşu şemayı değiştirmez."""
    with _scratch_database(pg_admin, "g214_createall") as engine:
        database.Base.metadata.create_all(bind=engine)
        assert INDEX_ADI not in _live_indexes(engine), "create_all index üretmiş — kurgu geçersiz"

        _run_init_db(engine)
        once = _live_indexes(engine)
        assert INDEX_ADI in once
        assert "(case_id, created_at)" in once[INDEX_ADI]

        _run_init_db(engine)
        assert _live_indexes(engine) == once


@pytest.mark.dbtest
def test_pg_table_op_tablo_yokken_kurar_ve_cascade_calisir(pg_admin):
    """create_all'ın koşmadığı yol: tablo yoksa ("table", ...) op'u DDL'i kurar,
    index op'u ardından index'i ekler; dava satırı silinince notlar da gider."""
    with _scratch_database(pg_admin, "g214_tableop") as engine:
        _run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE case_notes"))

        original = database.engine
        database.engine = engine
        try:
            database.check_and_migrate_tables()
        finally:
            database.engine = original

        assert INDEX_ADI in _live_indexes(engine)
        with engine.begin() as conn:
            cid = conn.execute(text(
                "INSERT INTO cases (tracking_no, status, active) VALUES ('HA.G214.1', 'DERDEST', true) "
                "RETURNING id"
            )).scalar()
            conn.execute(text(
                "INSERT INTO case_notes (case_id, body, author_email) VALUES (:c, 'not', 'a@b.c')"
            ), {"c": cid})
            assert conn.execute(text("SELECT created_at FROM case_notes")).scalar() is not None
            conn.execute(text("DELETE FROM cases WHERE id = :c"), {"c": cid})
            assert conn.execute(text("SELECT COUNT(*) FROM case_notes")).scalar() == 0
