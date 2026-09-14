"""G192 — düşük etkili backend kalemleri (14.09 performans denetimi D8, D10, D11, D15).

Dört bağımsız düzeltmenin sözleşmesi; hepsi davranışı korur, yalnız DB'ye giden
iş azalır:

* **D8** `GET /api/cases` `offset` tavanı (`le=10000`) — aşım 422, tavan 200.
* **D11** N+1'ler: `routes/cases.py` ilişki bloğu karşı kartları tek `IN` sorgusuyla,
  `routes/clients.py` poliçe listesi belge URL'lerini tek `case_documents` sorgusuyla çeker.
* **D15** `upload_queue._scan_once` vade filtresi SQL'de: backoff'taki satır DB'den
  hiç çekilmez (Python `_is_due` devre dışıyken bile işlenmez).
* **D10 (seçenek B)** `create_all`'ın ürettiği PK ikizi index'lerin TAMAMI
  `_DUSURULECEK_INDEXLER`'de — kapsama `Base.metadata` taramasından türetilir, elle
  liste değil; `models.py` değişmez, düşürme op'u her `init_db`'de idempotent koşar.

DB'siz testler süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar; sorgu
sayısı `before_cursor_execute` dinleyicisiyle ölçülür. `dbtest`'ler scratch
Postgres kullanır (`test_migration_path` altyapısı; DB yoksa SKIP).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
import test_migration_path as mig

admin_engine = mig.admin_engine

TENANT = "tenant-hanyaloglu"
USER = {"tid": TENANT, "preferred_username": "g192@hanyaloglu.com"}


# ─── ortak altyapı ───────────────────────────────────────────────────────────

def _sqlite_maker():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


class _SqlSayaci:
    """Engine'den geçen her SQL ifadesini (boşlukları sadeleştirip) kaydeder."""

    def __init__(self, engine):
        self.ifadeler: list[str] = []
        event.listen(engine, "before_cursor_execute", self._kaydet)

    def _kaydet(self, conn, cursor, statement, parameters, context, executemany):
        self.ifadeler.append(" ".join(statement.split()))

    def sifirla(self):
        self.ifadeler.clear()

    def selectler(self, *parcalar):
        return [
            s for s in self.ifadeler
            if s.upper().startswith("SELECT") and all(p in s for p in parcalar)
        ]


def _app(router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_current_tenant] = lambda: TENANT
    return TestClient(app, raise_server_exceptions=False)


# ─── D8: offset tavanı ───────────────────────────────────────────────────────

@pytest.fixture()
def cases_liste_app(monkeypatch):
    from routes import cases as cases_routes

    cagrilar = []

    def fake_get_cases(**kwargs):
        cagrilar.append(kwargs)
        return [], 0

    monkeypatch.setattr(cases_routes, "get_cases", fake_get_cases)
    return _app(cases_routes.router), cagrilar


def test_offset_tavani_asilinca_422_ve_manager_cagrilmaz(cases_liste_app):
    client, cagrilar = cases_liste_app

    r = client.get("/api/cases", params={"offset": 10001})

    assert r.status_code == 422
    assert cagrilar == [], "tavan aşımında DB'ye inilmemeli"


def test_offset_tavaninin_kendisi_kabul_edilir(cases_liste_app):
    client, cagrilar = cases_liste_app

    r = client.get("/api/cases", params={"offset": 10000})

    assert r.status_code == 200
    assert cagrilar[-1]["offset"] == 10000


def test_limit_tavani_yerinde(cases_liste_app):
    client, _ = cases_liste_app

    assert client.get("/api/cases", params={"limit": 200}).status_code == 200
    assert client.get("/api/cases", params={"limit": 201}).status_code == 422


# ─── D11: ilişki bloğu N+1 ───────────────────────────────────────────────────

@pytest.fixture()
def iliski_ortami(monkeypatch):
    from routes import cases as cases_routes
    from services import case_relations_auto

    engine, maker = _sqlite_maker()
    monkeypatch.setattr(cases_routes, "SessionLocal", maker)

    # Otomatik/öneri katmanı bu görevin konusu değil: sorgu sayımı yalnız elle
    # bağ bloğunu ölçsün diye susturulur; `haric` argümanı gözlem için saklanır.
    haricler = []
    monkeypatch.setattr(case_relations_auto, "iliskileri_bul", lambda db, case, tenant_id: [])

    def fake_oneriler(db, case, tenant_id, haric):
        haricler.append(set(haric))
        return []

    monkeypatch.setattr(case_relations_auto, "onerileri_bul", fake_oneriler)

    sayac = _SqlSayaci(engine)
    yield _app(cases_routes.router), maker, sayac, haricler
    engine.dispose()


def _kart(db, tracking_no, **alanlar):
    kart = models.Case(tracking_no=tracking_no, status="DERDEST", tenant_id=TENANT, **alanlar)
    db.add(kart)
    db.flush()
    return kart


def _iliskili_kartlar(maker, onek, adet):
    """Ana kart + `adet` elle bağlı kart; bağ yönü karışık (kaynak/hedef)."""
    db = maker()
    try:
        ana = _kart(db, f"{onek}.ANA")
        idler = []
        for i in range(adet):
            kart = _kart(db, f"{onek}.K{i:02d}")
            db.add(models.CaseParty(case_id=kart.id, name=f"Taraf {i}", role="Davacı",
                                    party_type="CLIENT"))
            kaynak, hedef = (ana.id, kart.id) if i % 2 == 0 else (kart.id, ana.id)
            db.add(models.CaseRelation(source_case_id=kaynak, target_case_id=hedef,
                                       relation_type="ILGILI", note=f"not {i}"))
            idler.append(kart.id)
        db.commit()
        return ana.id, idler
    finally:
        db.close()


def test_iliski_blogu_bes_karsi_karti_tek_selectle_ceker(iliski_ortami):
    client, maker, sayac, _ = iliski_ortami
    ana_id, idler = _iliskili_kartlar(maker, "G192A", 5)
    sayac.sifirla()

    r = client.get(f"/api/cases/{ana_id}/relations")

    assert r.status_code == 200
    manual = r.json()["manual"]
    assert [m["id"] for m in manual] == idler, "liste sırası manual_rows sırası olmalı"
    assert [m["parties"][0]["name"] for m in manual] == [f"Taraf {i}" for i in range(5)]

    karsi_kart_selectleri = sayac.selectler("FROM cases", "cases.id IN")
    assert len(karsi_kart_selectleri) == 1, sayac.ifadeler
    # Kalan tek `cases.id = ?` sorgusu ana kartın sahiplik kontrolüdür (get_tenant_owned_case)
    assert len(sayac.selectler("FROM cases", "cases.id = ?")) == 1, sayac.ifadeler
    assert len(sayac.selectler("FROM case_parties")) == 1, sayac.ifadeler


def test_iliski_sorgu_sayisi_iliski_adedinden_bagimsiz(iliski_ortami):
    client, maker, sayac, _ = iliski_ortami
    tek_id, _ = _iliskili_kartlar(maker, "G192T", 1)
    cok_id, _ = _iliskili_kartlar(maker, "G192C", 6)

    sayac.sifirla()
    assert client.get(f"/api/cases/{tek_id}/relations").status_code == 200
    tek_sayi = len(sayac.ifadeler)

    sayac.sifirla()
    assert client.get(f"/api/cases/{cok_id}/relations").status_code == 200
    cok_sayi = len(sayac.ifadeler)

    assert tek_sayi == cok_sayi, f"1 ilişki {tek_sayi} sorgu, 6 ilişki {cok_sayi} sorgu"


def test_silinmis_ve_reddedilen_kart_elle_listede_yok_ret_yine_haric(iliski_ortami):
    from services import case_relations_auto

    client, maker, sayac, haricler = iliski_ortami
    db = maker()
    try:
        ana = _kart(db, "G192S.ANA")
        canli1 = _kart(db, "G192S.CANLI1")
        silinmis = _kart(db, "G192S.SILINMIS", deleted_at=datetime.now(timezone.utc))
        reddedilen = _kart(db, "G192S.RED")
        canli2 = _kart(db, "G192S.CANLI2")
        for hedef, tur, not_ in (
            (canli1, "ILGILI", "birinci"),
            (silinmis, "ILGILI", "silinmiş"),
            (reddedilen, case_relations_auto.ONERI_RED, None),
            (canli2, "BIRLESEN", "ikinci"),
        ):
            db.add(models.CaseRelation(source_case_id=ana.id, target_case_id=hedef.id,
                                       relation_type=tur, note=not_))
        db.commit()
        ana_id, beklenen = ana.id, [canli1.id, canli2.id]
        red_id = reddedilen.id
    finally:
        db.close()

    r = client.get(f"/api/cases/{ana_id}/relations")

    assert r.status_code == 200
    manual = r.json()["manual"]
    assert [m["id"] for m in manual] == beklenen
    assert [(m["relation_type"], m["note"], m["is_manual"]) for m in manual] == [
        ("ILGILI", "birinci", True), ("BIRLESEN", "ikinci", True),
    ]
    assert all(m["relation_id"] for m in manual)
    assert red_id in haricler[-1], "reddedilen öneri hariç kümesinden düşmüş"


def test_elle_bag_yoksa_karsi_kart_sorgusu_kosmaz(iliski_ortami):
    client, maker, sayac, _ = iliski_ortami
    ana_id, _ = _iliskili_kartlar(maker, "G192B", 0)
    sayac.sifirla()

    r = client.get(f"/api/cases/{ana_id}/relations")

    assert r.status_code == 200
    assert r.json()["manual"] == []
    assert sayac.selectler("cases.id IN") == []


# ─── D11: poliçe listesi N+1 ─────────────────────────────────────────────────

@pytest.fixture()
def police_ortami(monkeypatch):
    from routes import clients as clients_routes

    engine, maker = _sqlite_maker()
    monkeypatch.setattr(clients_routes, "SessionLocal", maker)
    sayac = _SqlSayaci(engine)
    yield _app(clients_routes.router), maker, sayac
    engine.dispose()


def _musteri(db):
    musteri = models.Client(name="Dr. G192 Test", tenant_id=None)
    db.add(musteri)
    db.flush()
    return musteri


def test_police_listesi_belge_urllerini_tek_sorguda_bulur(police_ortami):
    client, maker, sayac = police_ortami
    db = maker()
    try:
        musteri = _musteri(db)
        for ad, url, silinmis in (
            ("a.pdf", "https://sp/eski-a", False),
            ("a.pdf", "https://sp/yeni-a", False),
            ("a.pdf", "https://sp/silinmis-a", True),   # en yeni canlı değil
            ("a.pdf", None, False),                     # URL'siz kayıt link olamaz
            ("b.pdf", "https://sp/b", False),
        ):
            db.add(models.CaseDocument(
                original_filename=ad, stored_filename=f"std_{ad}", sharepoint_url=url,
                deleted_at=datetime.now(timezone.utc) if silinmis else None,
            ))
            db.flush()
        for i, ad in enumerate(["a.pdf", "b.pdf", "yok.pdf", None, "a.pdf"]):
            db.add(models.ClientPolicy(client_id=musteri.id, police_no=f"P{i}", source_document=ad))
        db.commit()
        musteri_id = musteri.id
    finally:
        db.close()
    sayac.sifirla()

    r = client.get(f"/api/clients/{musteri_id}/policies")

    assert r.status_code == 200
    urller = {p["police_no"]: p["document_url"] for p in r.json()["policies"]}
    assert urller == {
        "P0": "https://sp/yeni-a",
        "P1": "https://sp/b",
        "P2": None,
        "P3": None,
        "P4": "https://sp/yeni-a",
    }
    assert len(sayac.selectler("FROM case_documents")) == 1, sayac.ifadeler


def test_kaynak_belgesiz_policelerde_belge_sorgusu_kosmaz(police_ortami):
    client, maker, sayac = police_ortami
    db = maker()
    try:
        musteri = _musteri(db)
        db.add(models.ClientPolicy(client_id=musteri.id, police_no="P0", source_document=None))
        db.commit()
        musteri_id = musteri.id
    finally:
        db.close()
    sayac.sifirla()

    r = client.get(f"/api/clients/{musteri_id}/policies")

    assert r.status_code == 200
    assert [p["document_url"] for p in r.json()["policies"]] == [None]
    assert sayac.selectler("FROM case_documents") == []


# ─── D15: outbox vade filtresi SQL'de ────────────────────────────────────────

def _outbox_satiri(**alanlar):
    varsayilan = dict(kind="islenmis", target_filename="belge.pdf",
                      target_folder="02_YEDEK_ARSIV", status="pending", attempts=0)
    varsayilan.update(alanlar)
    return models.UploadOutbox(**varsayilan)


def test_scan_once_vadesi_gelmemis_satiri_dbden_hic_cekmez(monkeypatch):
    from services import upload_queue

    engine, maker = _sqlite_maker()
    monkeypatch.setattr(upload_queue, "SessionLocal", maker)
    monkeypatch.setattr(upload_queue, "_purge_terminal_spools", lambda db, now: None)
    # Python yardımcısı devre dışı: gelecek vadeli satır ancak SQL elerse işlenmez
    monkeypatch.setattr(upload_queue, "_is_due", lambda row, now: True)
    denenen = []
    monkeypatch.setattr(upload_queue, "_attempt_upload", denenen.append)

    now = datetime.now(timezone.utc)
    db = maker()
    try:
        db.add_all([
            _outbox_satiri(id=1, next_attempt_at=None),                        # startup reconcile
            _outbox_satiri(id=2, next_attempt_at=now - timedelta(minutes=5)),  # vadesi geçmiş
            _outbox_satiri(id=3, next_attempt_at=now + timedelta(hours=2)),    # backoff'ta
            _outbox_satiri(id=4, status="uploaded", next_attempt_at=None),
        ])
        db.commit()
    finally:
        db.close()
    sayac = _SqlSayaci(engine)

    assert upload_queue._scan_once() == 2
    assert denenen == [1, 2]

    tarama = sayac.selectler("FROM upload_outbox")
    assert len(tarama) == 1, sayac.ifadeler
    assert "upload_outbox.next_attempt_at IS NULL" in tarama[0]
    assert "upload_outbox.next_attempt_at <=" in tarama[0]


@pytest.mark.dbtest
def test_scan_once_sorgusu_postgreste_parcali_pending_indexine_duser(admin_engine, monkeypatch):
    """Bekçi: SQL'e taşınan vade koşulu `idx_upload_outbox_pending` kullanımını bozmaz."""
    from services import upload_queue

    with mig._scratch_database(admin_engine, "g192scan") as engine:
        mig._run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO upload_outbox (kind, target_filename, target_folder, status, attempts, next_attempt_at)
                SELECT 'islenmis', 'b' || i || '.pdf', '02_YEDEK_ARSIV',
                       CASE WHEN i % 50 = 0 THEN 'pending' ELSE 'uploaded' END, 0,
                       CASE WHEN i % 100 = 0 THEN now() + interval '1 hour'
                            WHEN i % 150 = 0 THEN now() - interval '1 hour' END
                FROM generate_series(1, 3000) AS i
            """))
            conn.execute(text("ANALYZE upload_outbox"))

        monkeypatch.setattr(upload_queue, "SessionLocal", sessionmaker(bind=engine))
        monkeypatch.setattr(upload_queue, "_purge_terminal_spools", lambda db, now: None)
        denenen = []
        monkeypatch.setattr(upload_queue, "_attempt_upload", denenen.append)

        yakalanan = []

        def kaydet(conn, cursor, statement, parameters, context, executemany):
            if "FROM upload_outbox" in statement:
                yakalanan.append((statement, parameters))

        event.listen(engine, "before_cursor_execute", kaydet)
        try:
            islenen = upload_queue._scan_once()
        finally:
            event.remove(engine, "before_cursor_execute", kaydet)

        # 60 pending (i % 50); 30'u gelecek vadeli (i % 100) → 30 işlenir
        assert islenen == 30 == len(denenen)
        assert len(yakalanan) == 1
        sql, parametreler = yakalanan[0]
        with engine.connect() as conn:
            conn.exec_driver_sql("SET enable_seqscan = off")
            plan = "\n".join(r[0] for r in conn.exec_driver_sql("EXPLAIN " + sql, parametreler).all())
        assert "idx_upload_outbox_pending" in plan, plan


# ─── D10: PK ikizi index'ler ─────────────────────────────────────────────────

def _model_pk_ikizleri():
    """{tablo: [(index_adı, [pk kolonları])]} — `create_all`'ın PK ile birebir aynı yarattığı index'ler."""
    ikizler: dict = {}
    for tablo in models.Base.metadata.sorted_tables:
        pk = [c.name for c in tablo.primary_key.columns]
        for idx in tablo.indexes:
            if pk and [c.name for c in idx.columns] == pk:
                ikizler.setdefault(tablo.name, []).append((idx.name, pk))
    return ikizler


def test_model_pk_ikizlerinin_tamami_dusurme_listesinde_dogru_tabloda():
    ikizler = _model_pk_ikizleri()
    assert ikizler, "Base.metadata taraması hiç PK ikizi bulamadı — tarama bozuk"

    eksik = sorted(
        f"{tablo}.{ad}"
        for tablo, liste in ikizler.items()
        for ad, _pk in liste
        if ad not in database._DUSURULECEK_INDEXLER.get(tablo, [])
    )
    assert eksik == [], "create_all'ın yarattığı PK ikizi düşürülmüyor: " + ", ".join(eksik)


def test_parcali_pending_indexleri_dusurme_listesinde_degil():
    """Kısmi index PK ikizi değildir; müşterileri var (gece dönüşüm taraması, outbox worker)."""
    tumu = {ad for adlar in database._DUSURULECEK_INDEXLER.values() for ad in adlar}
    assert "idx_case_docs_conversion_pending" not in tumu
    assert "idx_upload_outbox_pending" not in tumu


@pytest.mark.dbtest
def test_init_db_pk_ikizlerini_dusurur_pk_indexlerini_korur_idempotent(admin_engine):
    ikizler = _model_pk_ikizleri()
    ikiz_adlari = sorted(ad for liste in ikizler.values() for ad, _pk in liste)

    with mig._scratch_database(admin_engine, "g192pk") as engine:
        mig._run_init_db(engine)
        ilk = mig._live_indexes(engine)
        kalan = [ad for ad in ikiz_adlari if ad in ilk]
        assert kalan == [], "init_db sonrası PK ikizi duruyor: " + ", ".join(kalan)

        with engine.connect() as conn:
            pk_tablolari = {r[0] for r in conn.execute(text("""
                SELECT c.relname FROM pg_index x
                JOIN pg_class c ON c.oid = x.indrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE x.indisprimary AND n.nspname = 'public'
            """)).all()}
        eksik_pk = sorted(set(ikizler) - pk_tablolari)
        assert eksik_pk == [], "PRIMARY KEY index'i kaybolmuş: " + ", ".join(eksik_pk)

        # Eski kurulum taklidi: G192 öncesi şemada ikizler yerinde duruyordu
        # (create_all mevcut tabloyu atladığı için kendiliğinden gitmezlerdi).
        with engine.begin() as conn:
            for tablo, liste in ikizler.items():
                for ad, pk in liste:
                    conn.execute(text(f"CREATE INDEX {ad} ON {tablo} ({', '.join(pk)})"))

        mig._run_init_db(engine)
        assert mig._live_indexes(engine) == ilk, "eski kurulumdaki PK ikizleri düşmedi"

        mig._run_init_db(engine)
        assert mig._live_indexes(engine) == ilk, "ikinci init_db index kümesini değiştirdi"
