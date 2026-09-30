"""G236 — yeni kartın numarasını SUNUCU verir + önizleme ucu + istek kimliği, GERÇEK Postgres.

`test_g196_status_kapisi` kalıbı: scratch veritabanı (`hukudok_migtest_*`, `test_migration_path`
altyapısı — gerçek `hukudok` DB'sine asla yazılmaz, DB yoksa SKIP), `init_db()` koşmuş şema,
gerçek `api.app` route'ları ve gerçek `add_case`. Eşzamanlılık iddiaları (sıra tahsisi, kısmi
UNIQUE index) sqlite'ta kanıtlanamaz — satır kilidi ve `ON CONFLICT` Postgres davranışıdır.

Kilitlenenler:
* İstemcinin `tracking_no`'su yeni kayıtta yok sayılır; kart karar 023 formatında numara alır.
* Aynı müvekkil koduyla paralel kayıtlar farklı ardışık sıra alır, 409 yok.
* Müvekkilsiz kayıt 422 (kart yok, sayaç artmaz); avukat/durum hataları ondan önce gelir.
* `GET /api/cases/ofis-no-onizleme` sayacı artırmaz; ardından yapılan kayıt önizlenen numarayı alır.
* Düzenleme (PUT) numarayı değiştirmez.
* `istek_kimligi`: aynı kimlikle ardışık/paralel istek → tek kart, sayaç bir kez, `reused: true`;
  intake commit tekrarında belgeler ikinci kez bağlanmaz; silinmiş/başka tenant kartı sızmaz.
* Migrasyon 57: kolon + kısmi UNIQUE index iki kurulum yolunda da yerinde.
* `add_case`'i doğrudan çağıran (bayraksız) yol kendi numarasını kullanmaya devam eder.
"""
import os
import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import models  # noqa: E402
import test_migration_path as mig  # noqa: E402
from managers import case_manager  # noqa: E402

pytestmark = pytest.mark.dbtest

admin_engine = mig.admin_engine

YER_TUTUCU = "X1.XXXXXXXXXX.0001.HUKUK.00000"


@pytest.fixture(scope="module")
def pg_engine(admin_engine):
    with mig._scratch_database(admin_engine, "g236") as engine:
        mig._run_init_db(engine)
        yield engine


@pytest.fixture()
def pg(pg_engine, monkeypatch, tmp_path):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın (test_g196 deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from routes import cases as cases_route
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    Fabrika = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    monkeypatch.setattr(cases_route, "SessionLocal", Fabrika)

    # Intake commit'in belge hattı sahte: dönüşüm yerine davaya bir belge satırı yazar
    # (tekrar eden commit'in "zaten arşivli" tespiti gerçek `get_case_document_filenames`
    # ile sınansın diye).
    convert_calls: list = []

    def fake_convert(**kwargs):
        convert_calls.append(kwargs)
        db = Fabrika()
        try:
            belge = models.CaseDocument(
                case_id=kwargs["linked_case_id"],
                original_filename=kwargs["original_filename"],
                stored_filename=kwargs["new_filename"],
            )
            db.add(belge)
            db.commit()
            belge_id = belge.id
        finally:
            db.close()
        pdfa = tmp_path / f"pdfa_{len(convert_calls)}.pdf"
        pdfa.write_bytes(b"%PDF pdfa")
        return (str(pdfa), belge_id)

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", fake_convert)
    monkeypatch.setattr(document_pipeline, "schedule_cleanup", lambda *a, **k: None)
    monkeypatch.setattr(document_pipeline, "validate_tenant_and_resolve_lawyer", lambda case_id, user: None)

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {
            "path": str(p), "original_path": None, "original_ext": ".pdf",
            "owner": "admin@example.com",
        })

    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield SimpleNamespace(
            app=app, client=TestClient(app), engine=pg_engine, Fabrika=Fabrika,
            convert_calls=convert_calls, put_cache=put_cache,
        )
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


# ─── yardımcılar ─────────────────────────────────────────────────────────────

def _muvekkil_ekle(pg, ad, kategori=None) -> int:
    db = pg.Fabrika()
    try:
        c = models.Client(name=ad, category=kategori, contact_type="Client", client_type="Individual", active=True)
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def _taraf(ad, client_id=None, rol="Davacı", tip="CLIENT"):
    return {"name": ad, "role": rol, "party_type": tip, "client_id": client_id}


def _sayac(pg, kod):
    with pg.engine.connect() as conn:
        return conn.execute(text("SELECT son_sira FROM ofis_no_sayaclari WHERE kod = :k"), {"k": kod}).scalar()


def _kart(pg, cid):
    with pg.engine.connect() as conn:
        satir = conn.execute(text(
            "SELECT id, tracking_no, ofis_no_kodu, ofis_no_sira, istek_kimligi, status FROM cases WHERE id = :i"
        ), {"i": cid}).mappings().first()
    return dict(satir) if satir is not None else None


def _kart_sayisi(pg, kod=None) -> int:
    with pg.engine.connect() as conn:
        if kod is None:
            return conn.execute(text("SELECT count(*) FROM cases")).scalar()
        return conn.execute(text("SELECT count(*) FROM cases WHERE ofis_no_kodu = :k"), {"k": kod}).scalar()


def _paralel(pg, n, istek):
    """`istek(client)`'i n ayrı thread'de AYNI ANDA koşturur; yanıtları döner."""
    from starlette.testclient import TestClient

    bariyer = threading.Barrier(n)
    yanitlar: list = [None] * n
    hatalar: list = []

    def calis(i):
        try:
            client = TestClient(pg.app)
            bariyer.wait(timeout=10)
            yanitlar[i] = istek(client)
        except Exception as exc:  # pragma: no cover — hata test gövdesinde raporlanır
            hatalar.append(exc)

    isler = [threading.Thread(target=calis, args=(i,)) for i in range(n)]
    for t in isler:
        t.start()
    for t in isler:
        t.join(timeout=60)
    assert not hatalar, hatalar
    assert all(y is not None for y in yanitlar)
    return yanitlar


# ─── numarayı sunucu verir ───────────────────────────────────────────────────

def test_yer_tutucu_numara_yok_sayilir_kart_karar_023_numarasi_alir(pg):
    cid = _muvekkil_ekle(pg, "Dr. Mehmet Öztürk", "Doktor")
    r = pg.client.post("/api/cases", json={
        "tracking_no": YER_TUTUCU, "file_type": "Ceza", "parties": [_taraf("Dr. Mehmet Öztürk", cid)],
    })
    assert r.status_code == 200, r.text
    govde = r.json()
    assert govde["tracking_no"] == "DR.M.OZTURK-0001-CEZ"
    assert "reused" not in govde
    kart = _kart(pg, govde["id"])
    assert kart["tracking_no"] == "DR.M.OZTURK-0001-CEZ"
    assert (kart["ofis_no_kodu"], kart["ofis_no_sira"]) == ("DR.M.OZTURK", 1)
    assert kart["istek_kimligi"] is None
    assert _sayac(pg, "DR.M.OZTURK") == 1

    # numarasız istek de çalışır; sıra kod başına sayılır, tür kodu dosya türünden
    r = pg.client.post("/api/cases", json={"parties": [_taraf("Dr. Mehmet Öztürk", cid)]})
    assert r.status_code == 200, r.text
    assert r.json()["tracking_no"] == "DR.M.OZTURK-0002-HUK"
    with pg.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM cases WHERE tracking_no = :t"), {"t": YER_TUTUCU}).scalar() == 0


def test_kayitsiz_muvekkil_adindan_kategori_cikar_ve_danis_musteri_acmaz(pg):
    # Kayıtsız kişi → BR; şirket işaretli ad → KR. DANIŞ kalıcı müvekkil AÇMAZ ama numara alır.
    r = pg.client.post("/api/cases", json={"parties": [_taraf("Ayşe Danışan")], "status": "DANIŞ"})
    assert r.status_code == 200, r.text
    assert r.json()["tracking_no"] == "BR.A.DANISAN-0001-HUK"
    with pg.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM clients WHERE name = 'Ayşe Danışan'")).scalar() == 0

    r = pg.client.post("/api/cases", json={"parties": [_taraf("Enthone Kimya San. ve Tic. A.Ş.")]})
    assert r.status_code == 200, r.text
    assert r.json()["tracking_no"] == "KR.ENTHONE-0001-HUK"


def test_sigortaci_muvekkilde_sigortali_blogu_taraftan_gelir(pg):
    db = pg.Fabrika()
    try:
        if db.query(models.SigortaKisaKodu).filter(models.SigortaKisaKodu.kod == "AXA").first() is None:
            db.add(models.SigortaKisaKodu(kod="AXA", ad="AXA Sigorta", eslesme_anahtarlari=["AXA"], aktif=True))
            db.commit()
    finally:
        db.close()
    cid = _muvekkil_ekle(pg, "AXA Sigorta A.Ş.", "Sigorta")
    onceki = _sayac(pg, "AXA") or 0

    r = pg.client.get("/api/cases/ofis-no-onizleme", params={"muvekkiller": [str(cid)]})
    assert r.status_code == 200, r.text
    assert r.json()["kod"] == "AXA"
    assert r.json()["sigortali_eksik"] is True

    r = pg.client.get("/api/cases/ofis-no-onizleme", params={
        "muvekkiller": [str(cid)], "sigortali": ["Dr. Emre Altunç"], "file_type": "Hukuk",
    })
    assert r.status_code == 200, r.text
    onizleme = r.json()
    assert onizleme["onizleme"] == f"AXA-{onceki + 1:04d}-DR.E.ALTUNC-HUK"
    assert onizleme["sigortali_eksik"] is False

    r = pg.client.post("/api/cases", json={"file_type": "Hukuk", "parties": [
        _taraf("AXA Sigorta A.Ş.", cid, rol="Davalı"),
        _taraf("Dr. Emre Altunç", rol="Sigortalı", tip="COUNTER"),
    ]})
    assert r.status_code == 200, r.text
    assert r.json()["tracking_no"] == onizleme["onizleme"]


def test_paralel_kayitlar_farkli_ardisik_sira_alir_409_yok(pg):
    cid = _muvekkil_ekle(pg, "Paralel Hasta", "Hasta")
    n = 6
    yanitlar = _paralel(pg, n, lambda c: c.post("/api/cases", json={
        "tracking_no": YER_TUTUCU, "parties": [_taraf("Paralel Hasta", cid)],
    }))
    assert [y.status_code for y in yanitlar] == [200] * n, [y.text for y in yanitlar]
    numaralar = sorted(y.json()["tracking_no"] for y in yanitlar)
    assert numaralar == [f"HS.P.HASTA-{i:04d}-HUK" for i in range(1, n + 1)]
    assert len({y.json()["id"] for y in yanitlar}) == n
    assert _sayac(pg, "HS.P.HASTA") == n


# ─── müvekkilsiz kayıt ───────────────────────────────────────────────────────

def test_muvekkilsiz_kayit_422_kart_acilmaz(pg):
    once = _kart_sayisi(pg)
    for govde in (
        {"tracking_no": YER_TUTUCU, "court": "X Mahkemesi"},
        {"parties": [_taraf("Karşı Taraf", tip="COUNTER", rol="Davalı")]},
        {"status": "DANIŞ"},
        {"parties": [_taraf("   ")]},
    ):
        r = pg.client.post("/api/cases", json=govde)
        assert r.status_code == 422, (govde, r.text)
        assert "üvekkil" in r.json()["detail"]
    assert _kart_sayisi(pg) == once

    # Doğrulama sırası: üçlü dışı durum 400'ü müvekkil kontrolünden ÖNCE gelir
    r = pg.client.post("/api/cases", json={"status": "Arşivde"})
    assert r.status_code == 400, r.text

    # Intake commit yolu da aynı kapıdan geçer; belge tüketilmez
    pg.put_cache("g236-muvekkilsiz")
    r = pg.client.post("/api/case-intake/commit", json={
        "case": {"tracking_no": YER_TUTUCU, "esas_no": "2026/1"},
        "documents": [{"process_id": "g236-muvekkilsiz", "new_filename": "2026-01-01_X_TENSIP-ZPT____.pdf",
                       "belge_turu_kodu": "TENSIP-ZPT____"}],
    })
    assert r.status_code == 422, r.text
    assert pg.convert_calls == []
    assert _kart_sayisi(pg) == once


# ─── önizleme ────────────────────────────────────────────────────────────────

def test_onizleme_sayaci_artirmaz_ardindan_kayit_onizlenen_numarayi_alir(pg):
    cid = _muvekkil_ekle(pg, "Önizleme Kliniği", "Özel Hastane")
    istek = {"muvekkiller": [str(cid)], "file_type": "İcra"}
    r1 = pg.client.get("/api/cases/ofis-no-onizleme", params=istek)
    r2 = pg.client.get("/api/cases/ofis-no-onizleme", params=istek)
    assert r1.status_code == 200, r1.text
    assert r1.json() == r2.json()
    onizleme = r1.json()
    assert onizleme["onizleme"] == "OH.ONIZLEME-0001-ICR"
    assert onizleme["kod"] == "OH.ONIZLEME"
    assert onizleme["sigortali_eksik"] is False
    assert "Kaydedince verilecek" in onizleme["aciklama"]
    assert _sayac(pg, "OH.ONIZLEME") is None          # sayaç satırı bile doğmadı
    assert _kart_sayisi(pg, "OH.ONIZLEME") == 0

    r = pg.client.post("/api/cases", json={"file_type": "İcra", "parties": [_taraf("Önizleme Kliniği", cid)]})
    assert r.status_code == 200, r.text
    assert r.json()["tracking_no"] == onizleme["onizleme"]

    # Kayıttan sonra önizleme bir sonraki sırayı gösterir; ad ile sorgu da aynı müvekkili bulur
    r = pg.client.get("/api/cases/ofis-no-onizleme", params={"muvekkiller": ["Önizleme Kliniği"], "file_type": "İcra"})
    assert r.json()["onizleme"] == "OH.ONIZLEME-0002-ICR"
    assert _sayac(pg, "OH.ONIZLEME") == 1


def test_onizleme_muvekkilsiz_ve_bilinmeyen_id_422(pg):
    assert pg.client.get("/api/cases/ofis-no-onizleme").status_code == 422
    assert pg.client.get("/api/cases/ofis-no-onizleme", params={"muvekkiller": ["  "]}).status_code == 422
    assert pg.client.get("/api/cases/ofis-no-onizleme", params={"muvekkiller": ["99999999"]}).status_code == 422


# ─── düzenleme ───────────────────────────────────────────────────────────────

def test_duzenleme_numarayi_degistirmez(pg):
    cid = _muvekkil_ekle(pg, "Düzenleme Bireysel", "Bireysel")
    r = pg.client.post("/api/cases", json={"parties": [_taraf("Düzenleme Bireysel", cid)], "court": "X Mahkemesi"})
    assert r.status_code == 200, r.text
    kart_id, numara = r.json()["id"], r.json()["tracking_no"]
    assert numara == "BR.D.BIREYSEL-0001-HUK"

    for govde in (
        {"tracking_no": "ELLE/9999", "court": "Y Mahkemesi", "parties": [_taraf("Düzenleme Bireysel", cid)]},
        {"court": "Z Mahkemesi", "file_type": "Ceza", "parties": [_taraf("Düzenleme Bireysel", cid)]},
    ):
        r = pg.client.put(f"/api/cases/{kart_id}", json=govde)
        assert r.status_code == 200, r.text
        kart = _kart(pg, kart_id)
        assert kart["tracking_no"] == numara
        assert (kart["ofis_no_kodu"], kart["ofis_no_sira"]) == ("BR.D.BIREYSEL", 1)
    with pg.engine.connect() as conn:
        assert conn.execute(text("SELECT court FROM cases WHERE id = :i"), {"i": kart_id}).scalar() == "Z Mahkemesi"
    assert _sayac(pg, "BR.D.BIREYSEL") == 1


# ─── istek kimliği ───────────────────────────────────────────────────────────

def test_ayni_istek_kimligi_ardisik_tek_kart_sayac_bir_kez(pg):
    cid = _muvekkil_ekle(pg, "Kimlik Ardışık", "Hasta")
    kimlik = str(uuid.uuid4())
    govde = {"istek_kimligi": kimlik, "parties": [_taraf("Kimlik Ardışık", cid)]}

    r1 = pg.client.post("/api/cases", json=govde)
    assert r1.status_code == 200, r1.text
    assert "reused" not in r1.json()
    assert _kart(pg, r1.json()["id"])["istek_kimligi"] == kimlik

    r2 = pg.client.post("/api/cases", json=govde)
    assert r2.status_code == 200, r2.text
    assert r2.json()["reused"] is True
    assert (r2.json()["id"], r2.json()["tracking_no"]) == (r1.json()["id"], "HS.K.ARDISIK-0001-HUK")
    assert _kart_sayisi(pg, "HS.K.ARDISIK") == 1
    assert _sayac(pg, "HS.K.ARDISIK") == 1


def test_ayni_istek_kimligi_paralel_tek_kart_sayac_bir_kez(pg):
    cid = _muvekkil_ekle(pg, "Kimlik Paralel", "Hasta")
    kimlik = str(uuid.uuid4())
    n = 6
    yanitlar = _paralel(pg, n, lambda c: c.post("/api/cases", json={
        "istek_kimligi": kimlik, "parties": [_taraf("Kimlik Paralel", cid)],
    }))
    assert [y.status_code for y in yanitlar] == [200] * n, [y.text for y in yanitlar]
    assert {y.json()["id"] for y in yanitlar} == {yanitlar[0].json()["id"]}
    assert {y.json()["tracking_no"] for y in yanitlar} == {"HS.K.PARALEL-0001-HUK"}
    assert sum(1 for y in yanitlar if y.json().get("reused") is True) == n - 1
    assert _kart_sayisi(pg, "HS.K.PARALEL") == 1
    assert _sayac(pg, "HS.K.PARALEL") == 1


def test_kimliksiz_istek_her_seferinde_yeni_kart_gecersiz_kimlik_422(pg):
    cid = _muvekkil_ekle(pg, "Kimliksiz Kişi", "Bireysel")
    govde = {"parties": [_taraf("Kimliksiz Kişi", cid)]}
    idler = {pg.client.post("/api/cases", json=govde).json()["id"] for _ in range(2)}
    assert len(idler) == 2
    assert _sayac(pg, "BR.K.KISI") == 2

    for bozuk in ("abc", "1234", "7b0e6c1e-6a0e-4c58-9d5c"):
        r = pg.client.post("/api/cases", json={**govde, "istek_kimligi": bozuk})
        assert r.status_code == 422, (bozuk, r.text)
        r = pg.client.post("/api/case-intake/commit", json={"case": {**govde, "istek_kimligi": bozuk}})
        assert r.status_code == 422, (bozuk, r.text)
    assert _sayac(pg, "BR.K.KISI") == 2


def test_silinmis_ya_da_baska_tenant_karti_donmez_ikinci_kart_da_acilmaz(pg):
    cid = _muvekkil_ekle(pg, "Kimlik Silinen", "Hasta")
    for durum_sql in ("deleted_at = now()", "tenant_id = 'tenant-baska'"):
        kimlik = str(uuid.uuid4())
        govde = {"istek_kimligi": kimlik, "parties": [_taraf("Kimlik Silinen", cid)]}
        r = pg.client.post("/api/cases", json=govde)
        assert r.status_code == 200, r.text
        with pg.engine.begin() as conn:
            conn.execute(text(f"UPDATE cases SET {durum_sql} WHERE id = :i"), {"i": r.json()["id"]})
        once_kart, once_sayac = _kart_sayisi(pg, "HS.K.SILINEN"), _sayac(pg, "HS.K.SILINEN")

        r2 = pg.client.post("/api/cases", json=govde)
        assert r2.status_code == 409, r2.text
        assert "id" not in r2.json()
        assert _kart_sayisi(pg, "HS.K.SILINEN") == once_kart
        assert _sayac(pg, "HS.K.SILINEN") == once_sayac      # geri alınan kayıt sırayı yakmadı


def test_intake_commit_tekrari_ikinci_kart_acmaz_belgeyi_ikinci_kez_baglamaz(pg):
    cid = _muvekkil_ekle(pg, "Dr. İntake Tekrar", "Doktor")
    kimlik = str(uuid.uuid4())
    istek = {
        "case": {
            "tracking_no": YER_TUTUCU, "istek_kimligi": kimlik, "esas_no": "2026/55",
            "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "parties": [_taraf("Dr. İntake Tekrar", cid)],
        },
        "documents": [{"process_id": "g236-belge", "new_filename": "2026-01-15_INTAKE_TENSIP-ZPT____.pdf",
                       "belge_turu_kodu": "TENSIP-ZPT____", "esas_no": "2026/55"}],
    }
    pg.put_cache("g236-belge")
    r1 = pg.client.post("/api/case-intake/commit", json=istek)
    assert r1.status_code == 200, r1.text
    ilk = r1.json()
    assert ilk["case"]["tracking_no"] == "DR.I.TEKRAR-0001-HUK"
    assert (ilk["case"]["reused"], ilk["case"]["idempotent_reuse"]) == (False, False)
    assert ilk["documents"][0]["status"] == "queued"
    assert len(pg.convert_calls) == 1

    # Tekrar: yanıt kayboldu, kullanıcı aynı taslakla yeniden gönderdi (cache tükenmiş)
    r2 = pg.client.post("/api/case-intake/commit", json=istek)
    assert r2.status_code == 200, r2.text
    ikinci = r2.json()
    assert ikinci["case"]["id"] == ilk["case"]["id"]
    assert ikinci["case"]["tracking_no"] == "DR.I.TEKRAR-0001-HUK"
    assert (ikinci["case"]["reused"], ikinci["case"]["idempotent_reuse"]) == (True, True)
    assert ikinci["documents"] == [{
        "process_id": "g236-belge", "status": "queued",
        "document_id": ilk["documents"][0]["document_id"], "error_ozet": None,
    }]
    assert len(pg.convert_calls) == 1
    with pg.engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM case_documents WHERE case_id = :i"), {"i": ilk["case"]["id"]}
        ).scalar() == 1
    assert _kart_sayisi(pg, "DR.I.TEKRAR") == 1
    assert _sayac(pg, "DR.I.TEKRAR") == 1


# ─── korunan eski yollar ─────────────────────────────────────────────────────

def test_dogrudan_add_case_cagrisi_kendi_numarasini_kullanir(pg):
    """Aktarım/script yolu (`scripts/kartsiz_foy_kart_ac.py`): bayraksız, müvekkilsiz, numaralı."""
    sonuc = case_manager.add_case({"tracking_no": "G236/ELLE-1", "court": "X"})
    assert sonuc["tracking_no"] == "G236/ELLE-1"
    kart = _kart(pg, sonuc["id"])
    assert (kart["ofis_no_kodu"], kart["ofis_no_sira"], kart["istek_kimligi"]) == (None, None, None)
    assert case_manager.add_case({"tracking_no": "G236/ELLE-1"}) == {"error": "duplicate_tracking_no"}


def test_client_sequence_ucu_hala_calisir(pg):
    """İNSAN ONAYLI TEST TAŞIMA (G239, insan kararı 30.09): uç KALKTI → 404 (test adı
    tarihsel). G236'da istemcisi kalmadığı hâlde çalışır bırakılmıştı; G237 sonrası
    çağıranı yok, sıra kayıt anında sayaçtan tahsis ediliyor — gövdede sıra dönmez."""
    r = pg.client.get("/api/cases/client-sequence", params={"client_name": "Hiç Olmayan Müvekkil"})
    assert r.status_code == 404, r.text
    assert "sequence" not in r.json()
    r = pg.client.get("/api/cases/client-sequence", params={"client_name": "x", "name_block": "ABCDEFGHIJ"})
    assert r.status_code == 404, r.text
    assert "sequence" not in r.json()


# ─── migrasyon 57 ────────────────────────────────────────────────────────────

def _istek_kimligi_semasi(engine):
    with engine.connect() as conn:
        kolon = conn.execute(text(
            "SELECT data_type, character_maximum_length, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'cases' AND column_name = 'istek_kimligi'"
        )).first()
        index = conn.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_cases_istek_kimligi'"
        )).scalar()
    return (tuple(kolon) if kolon else None), index


def test_migrasyon_57_iki_kurulum_yolunda_ayni_sema(pg_engine, admin_engine):
    kolon, index = _istek_kimligi_semasi(pg_engine)          # create_all yolu
    assert kolon == ("character varying", 36, "YES")
    assert "UNIQUE" in index and "(istek_kimligi)" in index and "istek_kimligi IS NOT NULL" in index

    # Çıplak yol: kolon YOK → ("columns", ...) op'u ekler, KOŞULSUZ ("index", ...) op'u kısıtı kurar
    with mig._scratch_database(admin_engine, "g236_ciplak") as engine:
        mig._run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE cases DROP COLUMN istek_kimligi"))
        assert _istek_kimligi_semasi(engine) == (None, None)
        mig._run_init_db(engine)
        assert _istek_kimligi_semasi(engine) == (kolon, index)
        mig._run_init_db(engine)                              # idempotent
        assert _istek_kimligi_semasi(engine) == (kolon, index)


def test_kismi_unique_index_kimliksiz_kartlari_kapsamaz_kimligi_tekil_tutar(pg):
    from sqlalchemy.exc import IntegrityError

    kimlik = str(uuid.uuid4())
    with pg.engine.begin() as conn:
        conn.execute(text("INSERT INTO cases (tracking_no, status) VALUES ('G236/IDX-1', 'DERDEST'), "
                          "('G236/IDX-2', 'DERDEST')"))
        conn.execute(text("INSERT INTO cases (tracking_no, status, istek_kimligi) "
                          "VALUES ('G236/IDX-3', 'DERDEST', :k)"), {"k": kimlik})
    with pytest.raises(IntegrityError):
        with pg.engine.begin() as conn:
            conn.execute(text("INSERT INTO cases (tracking_no, status, istek_kimligi) "
                              "VALUES ('G236/IDX-4', 'DERDEST', :k)"), {"k": kimlik})
