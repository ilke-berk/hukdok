"""G087 — İdari bildirim görünümü uçları: dağılım + hedefsiz sayacı.

İki yeni SALT OKUMA ucu kilitlenir:

* `GET /api/notifications/overview` — süre/duruşma uyarıları kime gitti, okundu mu;
* `GET /api/notifications/unresolved-targets` — sorumlusu hedefe çözülemeyen davalar.

Kilitlenen davranışlar:

1. **Kapı `get_current_user`** — admin ayrımı YOKTUR (kullanıcı kararı, 2026-08-20:
   sistemde rol kavramı yok, "idari pano" bir localStorage toggle'ı). Giriş yapan
   HERKES özeti görür; kimliksiz istek 401, token'da tenant yoksa 403.
2. **Tenant sızıntısı yok** — paylaşılan havuz deseni (`tenant_id == X OR IS NULL`):
   NULL satır görünür, BAŞKA tenant'ın satırı görünmez.
3. **Kapsam** — yalnız süre/duruşma türleri; "belge işlendi" gibi operasyonel
   bildirimler ve kapatılmış (dismissed) satırlar özete girmez.
4. **Salt okuma** — özeti çağırmak `read_at` damgalamaz, avukatın okunmamış
   sayacını DÜŞÜRMEZ.
5. **Regresyon bekçisi** — G081'in kişisel uçlarındaki sahiplik kuralı bu görevde
   GEVŞEMEDİ: başkasının bildirimi listede yok, id'si 404, `read-all` başkasının
   satırını işaretlemez. Yeni uçların yayınladığı bilgi, kişisel uçlara sızmaz.

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu
koşulur; hedefsiz sayacı da gerçek `cases`/`lawyers` satırlarından hesaplanır.
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
USER_A = {"tid": T1, "preferred_username": "avukat.a@hanyaloglu.com"}
USER_B = {"tid": T1, "preferred_username": "avukat.b@hanyaloglu.com"}
USER_T2 = {"tid": T2, "preferred_username": "avukat.c@baska.com"}
MAIL_A = "avukat.a@hanyaloglu.com"
MAIL_B = "avukat.b@hanyaloglu.com"

OFIS = "hanyaloglu-acar.av.tr"

OVERVIEW = "/api/notifications/overview"
HEDEFSIZ = "/api/notifications/unresolved-targets"


@pytest.fixture()
def env(monkeypatch):
    """sqlite motoru + oturum fabrikası + TestClient üreten fabrika."""
    monkeypatch.delenv("NOTIFICATION_DOMAINS", raising=False)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import Base, get_db
    from dependencies import get_current_user
    import models  # noqa: F401 — Base.metadata dolsun
    from routes import notifications as route_mod
    from services import deadline_scanner

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _client(user=USER_A):
        """`user=None` → kimlik doğrulaması OVERRIDE EDİLMEZ (gerçek kapı koşar)."""
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

    yield SimpleNamespace(
        models=models,
        route=route_mod,
        scanner=deadline_scanner,
        db=maker,
        client=_client,
    )
    engine.dispose()


def _bildirim(env, **kw):
    """Bildirim satırını DOĞRUDAN yazar (dedupe yolu G081'in konusu)."""
    kw.setdefault("recipient_email", MAIL_A)
    kw.setdefault("type", env.scanner.SURE_TYPE)
    kw.setdefault("severity", "warning")
    kw.setdefault("title", "Süre yaklaşıyor: İstinaf — 3 gün kaldı")
    kw.setdefault("body", "Dava: 2024/1 · Ankara 1. Asliye")
    kw.setdefault("tenant_id", None)
    kw.setdefault("due_date", dt.date(2026, 9, 1))
    kw.setdefault("created_at", dt.datetime.now(dt.timezone.utc))
    db = env.db()
    try:
        row = env.models.Notification(**kw)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _satir(env, notification_id: int):
    db = env.db()
    try:
        return db.get(env.models.Notification, notification_id)
    finally:
        db.close()


# ─── Yetki kapısı: admin ayrımı YOK, kimliksiz 401 ───────────────────────────

def test_kimliksiz_istek_401_doner(env):
    """Kapı gevşetildi ama AÇILMADI: token'sız istek iki uçta da 401."""
    c = env.client(user=None)
    assert c.get(OVERVIEW).status_code == 401
    assert c.get(HEDEFSIZ).status_code == 401


def test_giris_yapan_herkes_baskasinin_uyarisini_gorur(env):
    """Rol ayrımı yok: B kullanıcısı A'ya giden uyarıyı özet ucundan görür."""
    _bildirim(env, recipient_email=MAIL_A)

    r = env.client(user=USER_B).get(OVERVIEW)
    assert r.status_code == 200
    alicilar = [x["recipient_email"] for x in r.json()["items"]]
    assert alicilar == [MAIL_A]


def test_tokende_tenant_yoksa_403(env):
    """`tid` claim'i olmayan token özet ucunu açamaz (get_current_tenant kapısı)."""
    r = env.client(user={"preferred_username": MAIL_A}).get(OVERVIEW)
    assert r.status_code == 403


def test_hedefsiz_ucu_tenant_claimi_olmadan_da_calisir(env):
    """Hedefsiz sayacı `cases` havuzunu okur; tenant daraltması bilinçli YOK."""
    r = env.client(user={"preferred_username": MAIL_A}).get(HEDEFSIZ)
    assert r.status_code == 200


# ─── Özet ucu: alan seti, kapsam, sıralama ───────────────────────────────────

def test_overview_alan_seti_ve_okunma_durumu(env):
    """Satır alıcıyı, okunma damgasını ve dava bağını taşır; gövdeyi TAŞIMAZ."""
    okundu = dt.datetime(2026, 8, 19, 7, 30, tzinfo=dt.timezone.utc)
    nid = _bildirim(env, recipient_email=MAIL_B, read_at=okundu)

    kayit = env.client().get(OVERVIEW).json()["items"][0]
    assert set(kayit) == {
        "id", "type", "severity", "title", "recipient_email",
        "case_id", "due_date", "read_at", "is_read", "created_at",
    }
    assert kayit["id"] == nid
    assert kayit["recipient_email"] == MAIL_B
    assert kayit["type"] == env.scanner.SURE_TYPE
    assert kayit["due_date"] == "2026-09-01"
    assert kayit["is_read"] is True
    assert kayit["read_at"].startswith("2026-08-19T07:30")


def test_overview_yalniz_sure_ve_durusma_turlerini_kapsar(env):
    """Operasyonel bildirim (belge işlendi) süreli işler takibine girmez."""
    from services.notifications import DOC_PROCESSED_TYPE

    _bildirim(env, type=env.scanner.SURE_TYPE, title="Süre")
    _bildirim(env, type=env.scanner.DURUSMA_TYPE, title="Duruşma")
    _bildirim(env, type=DOC_PROCESSED_TYPE, title="Belge işlendi")

    govde = env.client().get(OVERVIEW).json()
    assert govde["total"] == 2
    assert {x["type"] for x in govde["items"]} == {
        env.scanner.SURE_TYPE,
        env.scanner.DURUSMA_TYPE,
    }


def test_overview_kapatilmis_bildirimi_gostermez(env):
    _bildirim(env, title="Açık")
    _bildirim(env, title="Kapatılmış", dismissed_at=dt.datetime.now(dt.timezone.utc))

    govde = env.client().get(OVERVIEW).json()
    assert [x["title"] for x in govde["items"]] == ["Açık"]
    assert govde["total"] == 1


def test_overview_son_gune_gore_siralanir(env):
    """En yakın son gün başta: panel "önce yanan iş"i gösterir."""
    _bildirim(env, title="Uzak", due_date=dt.date(2026, 9, 20))
    _bildirim(env, title="Yakın", due_date=dt.date(2026, 9, 2))
    _bildirim(env, title="Tarihsiz", due_date=None)

    basliklar = [x["title"] for x in env.client().get(OVERVIEW).json()["items"]]
    assert basliklar == ["Yakın", "Uzak", "Tarihsiz"]


# ─── Tenant sızıntısı ────────────────────────────────────────────────────────

def test_overview_baska_tenanti_sizdirmaz(env):
    """Paylaşılan havuz: NULL görünür, başka tenant'ın satırı GÖRÜNMEZ."""
    _bildirim(env, title="Paylasimli", tenant_id=None)
    _bildirim(env, title="Bizim", tenant_id=T1)
    _bildirim(env, title="Yabanci", tenant_id=T2)

    govde = env.client(user=USER_A).get(OVERVIEW).json()
    assert sorted(x["title"] for x in govde["items"]) == ["Bizim", "Paylasimli"]
    assert govde["total"] == 2

    yabanci = env.client(user=USER_T2).get(OVERVIEW).json()
    assert sorted(x["title"] for x in yabanci["items"]) == ["Paylasimli", "Yabanci"]


# ─── Parametreler: pencere, limit, sayaçlar, 422 ─────────────────────────────

def test_overview_gun_penceresi_eski_satiri_duser(env):
    eski = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=40)
    _bildirim(env, title="Eski", created_at=eski)
    _bildirim(env, title="Yeni")

    varsayilan = env.client().get(OVERVIEW).json()
    assert [x["title"] for x in varsayilan["items"]] == ["Yeni"]

    genis = env.client().get(OVERVIEW, params={"days": 90}).json()
    assert sorted(x["title"] for x in genis["items"]) == ["Eski", "Yeni"]
    assert genis["days"] == 90


def test_overview_sayaclar_limitten_ONCE_hesaplanir(env):
    """`total`/`unread` tavana dayanınca da gerçeği söyler."""
    _bildirim(env, title="A", due_date=dt.date(2026, 9, 1))
    _bildirim(env, title="B", due_date=dt.date(2026, 9, 2),
              read_at=dt.datetime.now(dt.timezone.utc))
    _bildirim(env, title="C", due_date=dt.date(2026, 9, 3))

    govde = env.client().get(OVERVIEW, params={"limit": 1}).json()
    assert govde["total"] == 3
    assert govde["unread"] == 2
    assert govde["limit"] == 1
    assert [x["title"] for x in govde["items"]] == ["A"]


def test_overview_unread_only_okunmus_satiri_duser(env):
    _bildirim(env, title="Okunmus", read_at=dt.datetime.now(dt.timezone.utc))
    _bildirim(env, title="Okunmamis")

    govde = env.client().get(OVERVIEW, params={"unread_only": "true"}).json()
    assert [x["title"] for x in govde["items"]] == ["Okunmamis"]
    # Sayaçlar filtreden ETKİLENMEZ: pencerede 2 satır var, 1'i okunmamış.
    assert (govde["total"], govde["unread"]) == (2, 1)


@pytest.mark.parametrize("params", [
    {"days": 0},
    {"days": 366},
    {"days": -1},
    {"limit": 0},
    {"limit": 501},
])
def test_overview_sinir_disi_parametre_422(env, params):
    """Tarih aralığı ve limit sınırlıdır — sınır dışı istek 422 ile döner."""
    assert env.client().get(OVERVIEW, params=params).status_code == 422


# ─── Salt okuma sözleşmesi ───────────────────────────────────────────────────

def test_overview_okunmamis_sayacini_ETKILEMEZ(env):
    """İdari panelde uyarıya bakmak avukatın zil rozetini düşürmez."""
    nid = _bildirim(env, recipient_email=MAIL_A)

    c = env.client(user=USER_A)
    assert c.get("/api/notifications/count").json()["unread"] == 1
    assert c.get(OVERVIEW).status_code == 200
    assert c.get("/api/notifications/count").json()["unread"] == 1
    assert _satir(env, nid).read_at is None


# ─── Hedefsiz sayacı ─────────────────────────────────────────────────────────

def _hedefsiz_veri(env):
    """Çözülen bir avukat + çözülemeyen iki sorumlu adı (biri silinmiş davada)."""
    db = env.db()
    try:
        db.add(env.models.Lawyer(
            code="ST", name="Serap Turgal", gorev="AVUKAT",
            email=f"serap@{OFIS}", active=True, sequence=0,
        ))
        db.add_all([
            env.models.Case(tracking_no="C-1", responsible_lawyer_name="Serap Turgal"),
            env.models.Case(tracking_no="C-2", responsible_lawyer_name="Av. Serap Turgal"),
            env.models.Case(tracking_no="C-3", responsible_lawyer_name="Arşiv Dosya Yöneticisi"),
            env.models.Case(tracking_no="C-4", responsible_lawyer_name="Arşiv Dosya Yöneticisi"),
            env.models.Case(tracking_no="C-5", responsible_lawyer_name="ARSIV DOSYA YONETICISI"),
            env.models.Case(tracking_no="C-6", responsible_lawyer_name="Asu Barış Karamık"),
            env.models.Case(tracking_no="C-7", responsible_lawyer_name="Silinmiş Sorumlu",
                            deleted_at=dt.datetime.now(dt.timezone.utc)),
        ])
        db.commit()
    finally:
        db.close()


def test_hedefsiz_sayaci_ad_ve_dava_adedini_toplamiyla_verir(env):
    _hedefsiz_veri(env)

    govde = env.client().get(HEDEFSIZ).json()
    items = govde["items"]
    # Aynı kişinin üç yazımı TEK satırda toplanır; sıra dava sayısına göre azalan.
    assert [x["case_count"] for x in items] == [3, 1]
    # Etiket, ada göre sıralı sorgunun İLK ham yazımıdır — hangi yazımın önce
    # geldiği sıralama collation'ına bağlıdır (sqlite ASCII vs Postgres TR),
    # bu yüzden kabul edilen yazım KÜMESİ doğrulanır, tek bir yazım değil.
    assert items[0]["name"] in {"Arşiv Dosya Yöneticisi", "ARSIV DOSYA YONETICISI"}
    assert items[1]["name"] == "Asu Barış Karamık"
    assert govde["total_names"] == 2
    assert govde["total_cases"] == 4


def test_hedefsiz_sayaci_bos_havuzda_sifir_doner(env):
    """Hedefsiz dava yoksa boş liste geçerli sonuçtur, 404 değil."""
    govde = env.client().get(HEDEFSIZ).json()
    assert govde == {"items": [], "total_names": 0, "total_cases": 0}


# ─── Regresyon bekçisi: G081 sahiplik kuralı GEVŞEMEDİ ───────────────────────

def test_kisisel_liste_hala_yalniz_kendi_satirlarini_verir(env):
    """Özet ucu A'nın satırını yayınlasa da kişisel liste B'ye onu VERMEZ."""
    _bildirim(env, recipient_email=MAIL_A, title="A icin")
    _bildirim(env, recipient_email=MAIL_B, title="B icin")

    kendi = env.client(user=USER_B).get("/api/notifications").json()
    assert [x["title"] for x in kendi] == ["B icin"]


def test_kisisel_okundu_ucu_baskasinin_id_sini_404_reddeder(env):
    """Başkasının id'si 404 (403 DEĞİL) ve satır okunmamış KALIR."""
    nid = _bildirim(env, recipient_email=MAIL_A)

    r = env.client(user=USER_B).post(f"/api/notifications/{nid}/read")
    assert r.status_code == 404
    assert _satir(env, nid).read_at is None


def test_read_all_baskasinin_satirina_dokunmaz(env):
    a_id = _bildirim(env, recipient_email=MAIL_A, title="A icin")
    b_id = _bildirim(env, recipient_email=MAIL_B, title="B icin")

    r = env.client(user=USER_B).post("/api/notifications/read-all")
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert _satir(env, a_id).read_at is None
    assert _satir(env, b_id).read_at is not None
