"""G081 — `notifications` şeması, yazma yolu (dedupe) ve okuma uçları.

Kilitlenen davranışlar:
  1. `create_notification` idempotency: aynı `dedupe_key` ikinci kez satır
     İKİLEMEZ, mevcut id döner ve mevcut satır güncellenmez,
  2. sahiplik: hiçbir uçta BAŞKA kullanıcının bildirimi görünmez; başkasının
     id'si 404 (403 değil — id enumeration'a bilgi sızmasın),
  3. kimlik üçlü claim fallback'i (`preferred_username | upn | email`) ve
     e-posta büyük/küçük harf normalizasyonu,
  4. `case_id`/`document_id` SET NULL: silinen dava/belge bildirimi ÖKSÜZ
     bırakır, SİLMEZ,
  5. migrasyonun index seti (G041: kısıtlar ("index", ...) op'unda; G042:
     başka index yok; G043: FK kolonları index'siz kalmaz).

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde GERÇEK
sorgu koşulur. UNIQUE kısıtı `create_all`dan DEĞİL, `database._MIGRATIONS`
içindeki gerçek DDL'den kurulur — böylece dedupe testleri prod'da koşacak
ifadenin ta kendisini sınar. Yabancı anahtar eylemleri için sqlite'ta
`PRAGMA foreign_keys=ON` şart (varsayılan KAPALI'dır).
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
USER_A = {"tid": T1, "preferred_username": "avukat.a@hanyaloglu.com"}
USER_B = {"tid": T1, "preferred_username": "avukat.b@hanyaloglu.com"}
MAIL_A = "avukat.a@hanyaloglu.com"
MAIL_B = "avukat.b@hanyaloglu.com"


def _notifications_index_ddls() -> list[str]:
    """Migrasyondaki `notifications` index op'unun DDL'leri (tek kaynak)."""
    import database

    return [
        ddl
        for op in database._MIGRATIONS
        if op[0] == "index" and op[1] == "notifications"
        for ddl in op[2]
    ]


@pytest.fixture()
def env():
    """sqlite motoru + oturum fabrikası + TestClient üreten fabrika."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import Base, get_db
    from dependencies import get_current_user
    import models  # noqa: F401 — Base.metadata dolsun
    from routes import notifications as route_mod
    from services import notifications as svc

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_conn, _rec):  # sqlite'ta FK eylemleri varsayılan KAPALI
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _notifications_index_ddls():
            conn.execute(text(ddl))

    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _client(user: dict = USER_A):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: user

        def _db_override():
            db = maker()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db_override
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(
        models=models,
        service=svc,
        route=route_mod,
        sessions=maker,
        db=maker,
        client=_client,
    )
    engine.dispose()


def _yaz(env, **kw):
    """create_notification kısayolu — kendi oturumunu açar ve kapatır."""
    kw.setdefault("recipient_email", MAIL_A)
    kw.setdefault("type", "durusma_yaklasti")
    kw.setdefault("title", "Duruşma yaklaşıyor")
    db = env.db()
    try:
        return env.service.create_notification(db, **kw)
    finally:
        db.close()


def _satirlar(env):
    db = env.db()
    try:
        return db.query(env.models.Notification).order_by(env.models.Notification.id).all()
    finally:
        db.close()


# ─── 1. Yazma yolu: dedupe idempotency ───────────────────────────────────────

def test_ayni_dedupe_key_satir_ikilemez(env):
    ilk = _yaz(env, dedupe_key="durusma:12:2026-09-01")
    ikinci = _yaz(env, dedupe_key="durusma:12:2026-09-01")

    assert ikinci == ilk, "aynı dedupe_key farklı id üretti"
    assert len(_satirlar(env)) == 1, "dedupe_key çakışmasında satır ikilendi"


def test_dedupe_mevcut_satiri_guncellemez(env):
    """Okunmuş bir bildirimi gece işi yeniden okunmamış yapmamalı."""
    nid = _yaz(env, dedupe_key="k1", title="İlk başlık")

    db = env.db()
    try:
        row = db.get(env.models.Notification, nid)
        row.read_at = dt.datetime(2026, 8, 20, 10, 0, 0)
        db.commit()
    finally:
        db.close()

    tekrar = _yaz(env, dedupe_key="k1", title="İkinci başlık", severity="critical")

    assert tekrar == nid
    row = _satirlar(env)[0]
    assert row.title == "İlk başlık", "dedupe çakışması mevcut satırı ezdi"
    assert row.severity == "info"
    assert row.read_at is not None, "okundu işareti dedupe ile sıfırlandı"


def test_dedupe_key_yoksa_her_cagri_yeni_satir(env):
    a = _yaz(env)
    b = _yaz(env)

    assert a != b
    assert len(_satirlar(env)) == 2, "dedupe_key NULL iken satırlar birleştirildi"


def test_farkli_dedupe_key_ayri_satir(env):
    _yaz(env, dedupe_key="k1")
    _yaz(env, dedupe_key="k2")

    assert len(_satirlar(env)) == 2


def test_bos_dedupe_key_null_sayilir(env):
    """Boş string UNIQUE kısıtında GERÇEK bir değerdir; NULL'a indirgenmeli."""
    a = _yaz(env, dedupe_key="   ")
    b = _yaz(env, dedupe_key="")

    assert a != b, "boş dedupe_key ikinci bildirimi yuttu"
    assert all(r.dedupe_key is None for r in _satirlar(env))


def test_yaris_durumunda_integrityerror_dedupe_ile_cozulur(env, monkeypatch):
    """Ön kontrol yarışı kaybederse UNIQUE kısıtı devreye girer ve id yine tektir.

    İki süreç aynı anda yazarsa ikincinin ön kontrolü satırı HENÜZ göremez;
    gerçek koruma DB kısıtıdır. Burada o an ön kontrolü bir kez kör ederek
    IntegrityError kolu koşturulur.
    """
    ilk = _yaz(env, dedupe_key="yaris:1")

    gercek = env.service._find_by_dedupe
    cagri = {"n": 0}

    def kor_ilk_cagri(db, key):
        cagri["n"] += 1
        return None if cagri["n"] == 1 else gercek(db, key)

    monkeypatch.setattr(env.service, "_find_by_dedupe", kor_ilk_cagri)
    ikinci = _yaz(env, dedupe_key="yaris:1")

    assert cagri["n"] >= 2, "IntegrityError kolu hiç koşmadı"
    assert ikinci == ilk
    assert len(_satirlar(env)) == 1


def test_dedupe_disi_integrityerror_yutulmaz(env):
    """Tekillik dışında bir kısıt (FK) patlarsa hata çağırana yükselmeli."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        _yaz(env, case_id=999999, dedupe_key="fk:1")

    assert _satirlar(env) == []


@pytest.mark.parametrize(
    "kw",
    [
        {"recipient_email": ""},
        {"recipient_email": "   "},
        {"type": ""},
        {"title": "  "},
    ],
)
def test_zorunlu_alan_bos_ise_valueerror(env, kw):
    with pytest.raises(ValueError):
        _yaz(env, **kw)

    assert _satirlar(env) == [], "geçersiz bildirim yazıldı"


def test_alici_epostasi_kucuk_harfe_normalize_edilir(env):
    _yaz(env, recipient_email="  Avukat.A@Hanyaloglu.COM ")

    assert _satirlar(env)[0].recipient_email == MAIL_A


def test_yazilan_alanlar_satira_gecer(env):
    db = env.db()
    try:
        case = env.models.Case(tracking_no="2026/G081-1", tenant_id=T1)
        db.add(case)
        db.commit()
        case_id = case.id
    finally:
        db.close()

    nid = _yaz(
        env,
        type="eksik_alan",
        severity="warning",
        title="Zorunlu alan eksik",
        body="Esas numarası boş.",
        tenant_id=T1,
        case_id=case_id,
        due_date=dt.date(2026, 9, 1),
        dedupe_key="eksik:1",
    )

    row = _satirlar(env)[0]
    assert row.id == nid
    assert (row.type, row.severity, row.body) == ("eksik_alan", "warning", "Esas numarası boş.")
    assert row.tenant_id == T1
    assert row.case_id == case_id
    assert row.due_date == dt.date(2026, 9, 1)
    assert row.read_at is None and row.dismissed_at is None


# ─── 2. Okuma ucu: sahiplik ──────────────────────────────────────────────────

def test_liste_yalniz_kendi_bildirimlerini_doner(env):
    _yaz(env, recipient_email=MAIL_A, title="A'nın bildirimi")
    _yaz(env, recipient_email=MAIL_B, title="B'nin bildirimi")

    a = env.client(USER_A).get("/api/notifications").json()
    b = env.client(USER_B).get("/api/notifications").json()

    assert [r["title"] for r in a] == ["A'nın bildirimi"]
    assert [r["title"] for r in b] == ["B'nin bildirimi"]


def test_liste_payload_alanlari(env):
    _yaz(env, severity="critical", body="gövde", due_date=dt.date(2026, 9, 1))

    row = env.client(USER_A).get("/api/notifications").json()[0]

    assert row["type"] == "durusma_yaklasti"
    assert row["severity"] == "critical"
    assert row["title"] == "Duruşma yaklaşıyor"
    assert row["body"] == "gövde"
    assert row["due_date"] == "2026-09-01"
    assert row["read_at"] is None and row["is_read"] is False
    assert row["created_at"]
    assert isinstance(row["id"], int)


def test_unread_only_ve_siralama(env):
    ilk = _yaz(env, title="1")
    _yaz(env, title="2")
    _yaz(env, title="3")

    client = env.client(USER_A)
    assert [r["title"] for r in client.get("/api/notifications").json()] == ["3", "2", "1"]

    client.post(f"/api/notifications/{ilk}/read")
    kalan = client.get("/api/notifications", params={"unread_only": True}).json()

    assert [r["title"] for r in kalan] == ["3", "2"]


def test_limit_govdeye_uygulanir(env):
    for i in range(3):
        _yaz(env, title=str(i))

    rows = env.client(USER_A).get("/api/notifications", params={"limit": 2}).json()

    assert len(rows) == 2


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"limit": -1}])
def test_limit_sinir_disi_reddedilir(env, params):
    assert env.client(USER_A).get("/api/notifications", params=params).status_code == 422


def test_okunmamis_sayisi(env):
    nid = _yaz(env)
    _yaz(env, title="ikinci")
    _yaz(env, recipient_email=MAIL_B, title="B")

    client = env.client(USER_A)
    assert client.get("/api/notifications/count").json() == {"unread": 2}

    client.post(f"/api/notifications/{nid}/read")
    assert client.get("/api/notifications/count").json() == {"unread": 1}
    assert env.client(USER_B).get("/api/notifications/count").json() == {"unread": 1}


def test_kapatilan_bildirim_listede_ve_sayimda_yok(env):
    nid = _yaz(env, title="kapatıldı")
    _yaz(env, title="duruyor")

    db = env.db()
    try:
        db.get(env.models.Notification, nid).dismissed_at = dt.datetime(2026, 8, 20, 9, 0, 0)
        db.commit()
    finally:
        db.close()

    client = env.client(USER_A)
    assert [r["title"] for r in client.get("/api/notifications").json()] == ["duruyor"]
    assert client.get("/api/notifications/count").json() == {"unread": 1}


# ─── 3. Okundu işaretleme + sahiplik doğrulaması ─────────────────────────────

def test_okundu_isaretleme(env):
    nid = _yaz(env)

    r = env.client(USER_A).post(f"/api/notifications/{nid}/read")

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True and r.json()["read_at"]
    assert _satirlar(env)[0].read_at is not None


def test_ikinci_okundu_cagrisi_ilk_zamani_ezmez(env):
    nid = _yaz(env)
    client = env.client(USER_A)

    ilk = client.post(f"/api/notifications/{nid}/read").json()["read_at"]
    ikinci = client.post(f"/api/notifications/{nid}/read").json()["read_at"]

    assert ikinci == ilk


def test_baskasinin_bildirimini_okundu_yapmak_404(env):
    nid = _yaz(env, recipient_email=MAIL_B)

    r = env.client(USER_A).post(f"/api/notifications/{nid}/read")

    assert r.status_code == 404, "başkasının bildirimi 403 ile varlığını sızdırdı"
    assert _satirlar(env)[0].read_at is None, "başkasının bildirimi okundu işaretlendi"


def test_olmayan_bildirim_404(env):
    assert env.client(USER_A).post("/api/notifications/999/read").status_code == 404


def test_toptan_okundu_yalniz_kendi_satirlarini_tutar(env):
    _yaz(env, title="a1")
    _yaz(env, title="a2")
    _yaz(env, recipient_email=MAIL_B, title="b1")

    r = env.client(USER_A).post("/api/notifications/read-all")

    assert r.status_code == 200 and r.json()["updated"] == 2
    okunmamis = {row.title for row in _satirlar(env) if row.read_at is None}
    assert okunmamis == {"b1"}, "toptan okundu başkasının bildirimine dokundu"
    assert env.client(USER_B).get("/api/notifications/count").json() == {"unread": 1}


# ─── 4. Kimlik: üçlü claim fallback'i ────────────────────────────────────────

@pytest.mark.parametrize(
    "user",
    [
        {"tid": T1, "preferred_username": MAIL_A},
        {"tid": T1, "upn": MAIL_A},
        {"tid": T1, "email": MAIL_A},
        {"tid": T1, "preferred_username": "Avukat.A@Hanyaloglu.com"},
    ],
)
def test_kimlik_uclu_fallback_ve_harf_duyarsizligi(env, user):
    _yaz(env)

    rows = env.client(user).get("/api/notifications").json()

    assert len(rows) == 1, f"claim {sorted(user)} ile bildirim bulunamadı"


def test_epostasiz_kullanici_403(env):
    _yaz(env)
    client = env.client({"tid": T1})

    assert client.get("/api/notifications").status_code == 403
    assert client.get("/api/notifications/count").status_code == 403
    assert client.post("/api/notifications/read-all").status_code == 403
    assert client.post("/api/notifications/1/read").status_code == 403


def test_activity_ile_ayni_claim_sirasi(env):
    """`routes/activity.py:_get_user_email` ile AYNI desen (Azure upn tuzağı)."""
    from routes.activity import _get_user_email as activity_email

    user = {"upn": "X@Y.com", "email": "z@y.com"}

    assert env.route._get_user_email(user) == activity_email(user).lower()


# ─── 5. Şema: SET NULL, öksüz bırakır silmez ─────────────────────────────────

def test_silinen_dava_ve_belge_bildirimi_oksuz_birakir(env):
    db = env.db()
    try:
        case = env.models.Case(tracking_no="2026/G081-2", tenant_id=T1)
        db.add(case)
        db.flush()
        doc = env.models.CaseDocument(
            case_id=case.id,
            original_filename="karar.pdf",
            stored_filename="karar.pdf",
        )
        db.add(doc)
        db.commit()
        case_id, doc_id = case.id, doc.id
    finally:
        db.close()

    nid = _yaz(env, case_id=case_id, document_id=doc_id, dedupe_key="oksuz:1")

    db = env.db()
    try:
        # Belge önce: case_documents.case_id FK'si SET NULL DEĞİL, dava ancak
        # belgesi düştükten sonra silinebilir.
        db.execute(text("DELETE FROM case_documents WHERE id = :i"), {"i": doc_id})
        db.execute(text("DELETE FROM cases WHERE id = :i"), {"i": case_id})
        db.commit()
    finally:
        db.close()

    row = _satirlar(env)[0]
    assert row.id == nid, "bildirim dava/belge ile birlikte silindi"
    assert row.case_id is None and row.document_id is None
    assert row.title == "Duruşma yaklaşıyor"


def test_fk_kolonlari_set_null_bildirir(env):
    """Model tarafındaki bekçi: CASCADE'e kayarsa bildirim sessizce yok olurdu."""
    tablo = env.models.Notification.__table__
    eylemler = {fk.parent.name: fk.ondelete for fk in tablo.foreign_keys}

    assert eylemler == {"case_id": "SET NULL", "document_id": "SET NULL"}


def test_sema_kolonlari(env):
    kolonlar = env.models.Notification.__table__.columns

    assert kolonlar["recipient_email"].nullable is False
    assert kolonlar["type"].nullable is False
    assert kolonlar["title"].nullable is False
    assert kolonlar["severity"].nullable is False
    for ad in ("tenant_id", "body", "case_id", "document_id", "due_date",
               "dedupe_key", "read_at", "dismissed_at", "created_at"):
        assert kolonlar[ad].nullable is True, f"{ad} nullable olmalı"


# ─── 6. Migrasyon: kısıt/index seti (G041 · G042 · G043) ─────────────────────

def test_index_seti_migrasyonda_ve_kosulsuz(env):
    ddls = _notifications_index_ddls()

    assert len(ddls) == 4, f"index seti değişmiş: {ddls}"
    assert all("IF NOT EXISTS" in d for d in ddls), "index op'u idempotent değil"
    adlar = {
        "uq_notifications_dedupe",
        "idx_notifications_recipient",
        "idx_notifications_case",
        "idx_notifications_document",
    }
    assert {ad for ad in adlar if any(ad in d for d in ddls)} == adlar
    assert any("UNIQUE" in d and "dedupe_key" in d for d in ddls)


def test_tablo_icin_olu_table_opu_yazilmadi(env):
    """G041: tabloyu create_all yaratır → ("table", "notifications", ...) ölü kod."""
    import database

    assert not [op for op in database._MIGRATIONS
                if op[0] == "table" and op[1] == "notifications"]


def test_modelde_ekstra_index_yok(env):
    """G042: index'ler migrasyonda tek kaynakta; modelde index=True kopyası olmasın."""
    tablo = env.models.Notification.__table__

    assert tablo.indexes == set(), f"modelde index tanımı var: {tablo.indexes}"


# ─── 7. Uçların uygulamaya bağlanması ────────────────────────────────────────

def _duz_yollar(routes):
    """FastAPI 0.141 `include_router`ı sarmalar (`_IncludedRouter`) — düzleştir."""
    for r in routes:
        ic = getattr(r, "original_router", None)
        if ic is not None:
            yield from _duz_yollar(ic.routes)
            continue
        for method in getattr(r, "methods", []) or []:
            yield (r.path, method)


def test_router_api_uygulamasina_baglandi(env):
    from api import app

    yollar = set(_duz_yollar(app.routes))

    assert ("/api/notifications", "GET") in yollar
    assert ("/api/notifications/count", "GET") in yollar
    assert ("/api/notifications/{notification_id}/read", "POST") in yollar
    assert ("/api/notifications/read-all", "POST") in yollar
