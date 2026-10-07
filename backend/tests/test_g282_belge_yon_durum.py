"""G282 — Belge yönü/kaynağı/durumu + sürüm defteri (migrasyon 61, plan §6.2 K11-K14).

Kilitlenen davranışlar:
  1. `constants.normalize_belge_*`: boş → varsayılan, büyük harf, bilinmeyen → ValueError.
  2. Model + migrasyon: yeni kolonlar varsayılanlarla (GELEN/BELGE_HATTI/KESIN); `belge_surumleri`
     UNIQUE (document_id, surum_no) migrasyonun KOŞULSUZ ("index") op'undan; CHECK'ler ve backfill de
     ayrı ("index") op'larında (koşullu "columns"/"table" op'una gömülü DEĞİL); backfill yalnız
     ARSIV_AKTARIM önekli satırı değiştirir.
  3. `save_case_document` varsayılanla GELEN/BELGE_HATTI/KESIN yazar, parametreyle TASLAK/GIDEN/PDF_ARACLARI;
     geçersiz değer ValueError (DB'ye dokunmadan).
  4. `export_publisher.enqueue_document`: TASLAK belge URL'li ve allowlist içi türde bile outbox satırı AÇMAZ;
     KESIN açar.
  5. `upload_queue._notify_document_processed`: TASLAK → bildirim servisi hiç çağrılmaz; KESIN → çağrılır.
  6. Kart yanıtı `documents[]` yeni alanlar + `surum_sayisi` (tek GROUP BY; kartın sorgu sayısı 7).
  7. `GET /api/cases/{id}/documents?yon=&durum=` filtreleri; geçersiz değer 422.
  8. Rapor kataloğu `belgeler`: `yon`/`kaynak`/`durum` kapalı liste kolonları; asistan ipucu.
  9. `settings.sharepoint_folder_taslak_name` varsayılanı.

DB yok (conftest dummy URL) → süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşulur.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
USER_A = {"tid": T1, "preferred_username": "a@hanyaloglu.com"}


# ── 1. normalize ─────────────────────────────────────────────────────────────

class TestNormalize:
    def test_varsayilanlar(self):
        from constants import normalize_belge_durumu, normalize_belge_kaynagi, normalize_belge_yonu

        assert normalize_belge_yonu(None) == "GELEN" and normalize_belge_yonu("") == "GELEN"
        assert normalize_belge_kaynagi(None) == "BELGE_HATTI"
        assert normalize_belge_durumu("  ") == "KESIN"

    def test_buyuk_harf_ve_turkce_i(self):
        from constants import normalize_belge_durumu, normalize_belge_kaynagi, normalize_belge_yonu

        assert normalize_belge_yonu("giden") == "GIDEN"
        assert normalize_belge_yonu("gİden") == "GIDEN"
        assert normalize_belge_kaynagi("pdf_araclari") == "PDF_ARACLARI"
        assert normalize_belge_durumu("taslak") == "TASLAK"

    @pytest.mark.parametrize("fn,deger", [
        ("normalize_belge_yonu", "ICERI"),
        ("normalize_belge_kaynagi", "EMAIL"),
        ("normalize_belge_durumu", "ONAYLI"),
        ("normalize_belge_durumu", "TASLAK____"),  # padding YOK
    ])
    def test_bilinmeyen_value_error(self, fn, deger):
        import constants

        with pytest.raises(ValueError):
            getattr(constants, fn)(deger)

    def test_listeler(self):
        from constants import BELGE_DURUMLARI, BELGE_KAYNAKLARI, BELGE_YONLERI

        assert BELGE_YONLERI == ("GELEN", "GIDEN")
        assert BELGE_KAYNAKLARI == ("BELGE_HATTI", "PDF_ARACLARI", "WORD", "ARSIV_AKTARIM", "TESLIM")
        assert BELGE_DURUMLARI == ("TASLAK", "KESIN")


# ── ortak sqlite ortamı ──────────────────────────────────────────────────────

def _index_ddls(tablo: str) -> list[str]:
    import database

    return [ddl for op in database._MIGRATIONS if op[0] == "index" and op[1] == tablo for ddl in op[2]]


@pytest.fixture()
def env():
    from database import Base
    import models  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Migrasyon 61'in koşulsuz op'undaki UNIQUE sqlite'ta da kurulur (DO $$ blokları Postgres'e özgü, atlanır)
        for ddl in _index_ddls("belge_surumleri"):
            conn.execute(text(ddl))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield SimpleNamespace(engine=engine, sessions=maker, models=models)
    engine.dispose()


def _dava(env, tracking_no="2026/T1-1"):
    db = env.sessions()
    try:
        c = env.models.Case(tracking_no=tracking_no, tenant_id=T1, esas_no="2026/111")
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def _belge(env, case_id, **ek):
    db = env.sessions()
    try:
        d = env.models.CaseDocument(case_id=case_id, original_filename="d.pdf", stored_filename="d.pdf",
                                    link_mode="LINKED", **ek)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


# ── 2. model + migrasyon ─────────────────────────────────────────────────────

class TestModelVeMigrasyon:
    def test_varsayilanlar_modelden(self, env):
        cid = _dava(env)
        did = _belge(env, cid)
        db = env.sessions()
        d = db.get(env.models.CaseDocument, did)
        assert (d.yon, d.kaynak, d.durum) == ("GELEN", "BELGE_HATTI", "KESIN")
        assert d.word_url is None and d.kesinlesme_tarihi is None and d.kesinlestiren_email is None
        assert d.onceki_document_id is None and d.surumler == []
        db.close()

    def test_surum_defteri_unique(self, env):
        cid = _dava(env)
        did = _belge(env, cid)
        db = env.sessions()
        db.add(env.models.BelgeSurumu(document_id=did, surum_no=1, sha256="a" * 64, olusturan_email="a@x"))
        db.add(env.models.BelgeSurumu(document_id=did, surum_no=2, sha256="b" * 64, kesin=True, aciklama_notu="son"))
        db.commit()
        d = db.get(env.models.CaseDocument, did)
        assert [s.surum_no for s in d.surumler] == [1, 2]
        assert d.surumler[1].kesin is True and d.surumler[1].aciklama_notu == "son"
        db.add(env.models.BelgeSurumu(document_id=did, surum_no=2, sha256="c" * 64))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_not_kolonu_adi(self, env):
        """`not` Python anahtar sözcüğü: öznitelik `aciklama_notu`, DB kolonu `not`."""
        assert env.models.BelgeSurumu.__table__.c["not"].name == "not"
        assert env.models.BelgeSurumu.aciklama_notu.property.columns[0].name == "not"

    def test_onceki_document_bagi(self, env):
        cid = _dava(env)
        eski = _belge(env, cid, durum="KESIN", yon="GIDEN")
        yeni = _belge(env, cid, durum="TASLAK", yon="GIDEN", onceki_document_id=eski)
        db = env.sessions()
        assert db.get(env.models.CaseDocument, yeni).onceki_document_id == eski
        db.close()

    def test_migrasyon_61_op_yapisi(self):
        """Kalıcı kısıt/index/backfill KOŞULSUZ ("index") op'larında; koşullu op'lara gömülü değil."""
        import database

        ops = database._MIGRATIONS
        columns_ops = [op for op in ops if op[0] == "columns" and op[1] == "case_documents" and "yon" in op[2]]
        assert len(columns_ops) == 1
        kolonlar = columns_ops[0][2]
        assert kolonlar["yon"] == "VARCHAR(8) NOT NULL DEFAULT 'GELEN'"
        assert kolonlar["kaynak"] == "VARCHAR(16) NOT NULL DEFAULT 'BELGE_HATTI'"
        assert kolonlar["durum"] == "VARCHAR(8) NOT NULL DEFAULT 'KESIN'"
        assert "ON DELETE SET NULL" in kolonlar["onceki_document_id"]
        for ddl in kolonlar.values():
            assert "CHECK" not in ddl and "INDEX" not in ddl  # kısıt koşullu op'ta DEĞİL

        table_ops = [op for op in ops if op[0] == "table" and op[1] == "belge_surumleri"]
        assert len(table_ops) == 1 and table_ops[0][3] == []  # index listesi boş: hepsi ayrı op'ta
        assert "ON DELETE RESTRICT" in table_ops[0][2]

        docs_index = " ".join(_index_ddls("case_documents"))
        for ad in ("ck_case_docs_yon", "ck_case_docs_kaynak", "ck_case_docs_durum"):
            assert ad in docs_index and f"conname = '{ad}'" in docs_index  # pg_constraint yoklamalı
        assert "idx_case_docs_case_durum" in docs_index and "idx_case_docs_durum_yon" in docs_index
        assert "UPDATE case_documents SET kaynak = 'ARSIV_AKTARIM'" in docs_index
        assert "uploaded_by LIKE 'ARSIV_AKTARIM:%' AND kaynak = 'BELGE_HATTI'" in docs_index
        assert any("uq_belge_surumleri_no" in d and "UNIQUE" in d for d in _index_ddls("belge_surumleri"))

    def test_backfill_yalniz_arsiv_aktarim(self, env):
        cid = _dava(env)
        arsiv = _belge(env, cid, uploaded_by="ARSIV_AKTARIM:ilke")
        normal = _belge(env, cid, uploaded_by="İlke Berk")
        elle = _belge(env, cid, uploaded_by="ARSIV_AKTARIM:ilke", kaynak="PDF_ARACLARI")  # başka kaynak: dokunulmaz
        ddl = next(d for d in _index_ddls("case_documents") if d.startswith("UPDATE case_documents SET kaynak"))
        with env.engine.begin() as conn:
            conn.execute(text(ddl))
            conn.execute(text(ddl))  # idempotent
        db = env.sessions()
        assert db.get(env.models.CaseDocument, arsiv).kaynak == "ARSIV_AKTARIM"
        assert db.get(env.models.CaseDocument, normal).kaynak == "BELGE_HATTI"
        assert db.get(env.models.CaseDocument, elle).kaynak == "PDF_ARACLARI"
        for did in (arsiv, normal, elle):
            d = db.get(env.models.CaseDocument, did)
            assert (d.yon, d.durum) == ("GELEN", "KESIN")
        db.close()


# ── 3. save_case_document ────────────────────────────────────────────────────

class TestSaveCaseDocument:
    @pytest.fixture()
    def pipeline(self, env, monkeypatch):
        from services import document_pipeline

        monkeypatch.setattr(document_pipeline, "SessionLocal", env.sessions)
        return document_pipeline

    def test_varsayilan_gelen_kesin(self, env, pipeline):
        cid = _dava(env)
        did = pipeline.save_case_document(case_id=cid, original_filename="a.pdf", stored_filename="a.pdf")
        db = env.sessions()
        d = db.get(env.models.CaseDocument, did)
        assert (d.yon, d.kaynak, d.durum) == ("GELEN", "BELGE_HATTI", "KESIN")
        db.close()

    def test_parametreyle_taslak(self, env, pipeline):
        cid = _dava(env)
        did = pipeline.save_case_document(case_id=cid, original_filename="a.pdf", stored_filename="a.pdf",
                                          yon="giden", kaynak="pdf_araclari", durum="taslak")
        db = env.sessions()
        d = db.get(env.models.CaseDocument, did)
        assert (d.yon, d.kaynak, d.durum) == ("GIDEN", "PDF_ARACLARI", "TASLAK")
        db.close()

    def test_gecersiz_deger_db_dokunmadan(self, env, pipeline):
        cid = _dava(env)
        with pytest.raises(ValueError):
            pipeline.save_case_document(case_id=cid, original_filename="a.pdf", stored_filename="a.pdf", durum="ONAY")
        db = env.sessions()
        assert db.query(env.models.CaseDocument).count() == 0
        db.close()

    def test_convert_pdfa_imzasi_uc_parametre(self):
        import inspect

        from services import document_pipeline

        p = inspect.signature(document_pipeline.convert_pdfa_and_queue_uploads).parameters
        assert p["yon"].default == "GELEN" and p["kaynak"].default == "BELGE_HATTI" and p["durum"].default == "KESIN"


# ── 4. export filtresi ───────────────────────────────────────────────────────

class _ModelSession:
    def __init__(self, rows):
        self._rows = rows
        self.added = []

    def query(self, model):
        rows = self._rows.get(model, [])

        class _Q:
            def filter(self_inner, *a, **k):
                return self_inner

            def first(self_inner):
                return rows[0] if rows else None

        return _Q()

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass

    def refresh(self, row):
        row.id = 99

    def rollback(self):
        pass

    def close(self):
        pass


class TestExportFiltresi:
    def _doc(self, durum):
        return SimpleNamespace(link_mode="LINKED", sharepoint_url="https://sp/x", case=None,
                               conversion_status=None, belge_turu_kodu="ARA-KRR", durum=durum)

    def _patch(self, monkeypatch, doc, existing=None):
        import database
        import models

        session = _ModelSession({models.CaseDocument: [doc], models.ExportOutbox: [existing] if existing else []})
        monkeypatch.setattr(database, "SessionLocal", lambda: session)
        return session

    def test_taslak_outbox_acmaz(self, monkeypatch):
        from services import export_publisher

        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        session = self._patch(monkeypatch, self._doc("TASLAK"))
        assert export_publisher.enqueue_document(7) is None
        assert session.added == []

    def test_kesin_outbox_acar(self, monkeypatch):
        from services import export_publisher

        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        session = self._patch(monkeypatch, self._doc("KESIN"))
        assert export_publisher.enqueue_document(7) == 99
        assert len(session.added) == 1 and session.added[0].status == "pending"

    def test_durum_alani_olmayan_eski_nesne_gecer(self, monkeypatch):
        """SimpleNamespace'li eski testler `durum` taşımaz → KESIN sayılır (savunma)."""
        from services import export_publisher

        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        doc = self._doc("KESIN")
        del doc.durum
        self._patch(monkeypatch, doc, existing=SimpleNamespace(id=55))
        assert export_publisher.enqueue_document(7) == 55


# ── 5. bildirim kapısı ───────────────────────────────────────────────────────

class TestBildirimKapisi:
    def _kur(self, env, monkeypatch, durum):
        from services import upload_queue

        monkeypatch.setattr(upload_queue, "SessionLocal", env.sessions)
        cid = _dava(env)
        did = _belge(env, cid, durum=durum, sharepoint_url="https://sp/x")
        cagrilar = []
        import services.notifications as svc

        monkeypatch.setattr(svc, "notify_document_processed", lambda document_id: cagrilar.append(document_id))
        return upload_queue, did, cagrilar

    def test_taslak_bildirim_yok(self, env, monkeypatch, caplog):
        upload_queue, did, cagrilar = self._kur(env, monkeypatch, "TASLAK")
        with caplog.at_level("WARNING"):
            upload_queue._notify_document_processed(did)
        assert cagrilar == []
        assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]

    def test_kesin_bildirim_var(self, env, monkeypatch):
        upload_queue, did, cagrilar = self._kur(env, monkeypatch, "KESIN")
        upload_queue._notify_document_processed(did)
        assert cagrilar == [did]

    def test_kayit_yoksa_kapi_acik(self, env, monkeypatch):
        """Belge yoksa eski yol: servis çağrılır, kendi WARNING'ini basar."""
        upload_queue, did, cagrilar = self._kur(env, monkeypatch, "KESIN")
        upload_queue._notify_document_processed(did + 1000)
        assert cagrilar == [did + 1000]

    def test_db_hatasi_kapi_acik(self, env, monkeypatch, caplog):
        from services import upload_queue

        def _patla():
            raise RuntimeError("db yok")

        monkeypatch.setattr(upload_queue, "SessionLocal", _patla)
        assert upload_queue._belge_kesin_mi(1) is True


# ── 6-7. kart yanıtı ve liste filtresi ───────────────────────────────────────

@pytest.fixture()
def client(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager
    from routes import cases, documents

    monkeypatch.setattr(case_manager, "SessionLocal", env.sessions)
    monkeypatch.setattr(documents, "SessionLocal", env.sessions)
    app = FastAPI()
    app.include_router(cases.router)
    app.include_router(documents.router)
    app.dependency_overrides[get_current_user] = lambda: USER_A
    app.dependency_overrides[get_current_tenant] = lambda: T1
    return TestClient(app, raise_server_exceptions=False)


class TestKartVeListe:
    def _seed(self, env):
        cid = _dava(env)
        gelen = _belge(env, cid)
        giden = _belge(env, cid, yon="GIDEN", kaynak="WORD", durum="KESIN",
                       kesinlesme_tarihi=datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc), kesinlestiren_email="a@x")
        taslak = _belge(env, cid, yon="GIDEN", kaynak="PDF_ARACLARI", durum="TASLAK", word_url="https://sp/t.docx",
                        onceki_document_id=giden)
        db = env.sessions()
        db.add(env.models.BelgeSurumu(document_id=giden, surum_no=1, sha256="a" * 64))
        db.add(env.models.BelgeSurumu(document_id=giden, surum_no=2, sha256="b" * 64, kesin=True))
        db.commit()
        db.close()
        return cid, gelen, giden, taslak

    def test_kart_yaniti_alanlari(self, env, client):
        cid, gelen, giden, taslak = self._seed(env)
        r = client.get(f"/api/cases/{cid}")
        assert r.status_code == 200, r.text
        docs = {d["id"]: d for d in r.json()["documents"]}
        assert docs[gelen]["yon"] == "GELEN" and docs[gelen]["kaynak"] == "BELGE_HATTI" and docs[gelen]["durum"] == "KESIN"
        assert docs[gelen]["surum_sayisi"] == 0 and docs[gelen]["word_url"] is None
        assert docs[giden]["surum_sayisi"] == 2 and docs[giden]["kesinlesme_tarihi"].startswith("2026-10-07")
        assert docs[taslak]["durum"] == "TASLAK" and docs[taslak]["word_url"] == "https://sp/t.docx"
        assert docs[taslak]["kesinlesme_tarihi"] is None
        # G285: yeni sürüm taslağı bağı kart yanıtında
        assert docs[taslak]["onceki_document_id"] == giden and docs[gelen]["onceki_document_id"] is None

    def test_kart_surum_sayisi_tek_sorgu(self, env, client):
        """Belge sayısı artsa da sorgu sayısı sabit (N+1 yok)."""
        from sqlalchemy import event

        cid, *_ = self._seed(env)
        for _ in range(5):
            _belge(env, cid)

        sayac = {"n": 0}

        def _say(*a, **k):
            sayac["n"] += 1

        event.listen(env.engine, "before_cursor_execute", _say)
        try:
            assert client.get(f"/api/cases/{cid}").status_code == 200
            az = sayac["n"]
            for _ in range(10):
                _belge(env, cid)
            sayac["n"] = 0
            assert client.get(f"/api/cases/{cid}").status_code == 200
            cok = sayac["n"]
        finally:
            event.remove(env.engine, "before_cursor_execute", _say)
        assert az == cok

    def test_liste_filtreleri(self, env, client):
        cid, gelen, giden, taslak = self._seed(env)
        hepsi = client.get(f"/api/cases/{cid}/documents").json()
        assert {d["id"] for d in hepsi} == {gelen, giden, taslak}
        assert all({"yon", "kaynak", "durum", "word_url", "kesinlesme_tarihi"} <= set(d) for d in hepsi)
        assert {d["id"] for d in client.get(f"/api/cases/{cid}/documents?yon=GIDEN").json()} == {giden, taslak}
        assert {d["id"] for d in client.get(f"/api/cases/{cid}/documents?durum=taslak").json()} == {taslak}
        assert {d["id"] for d in client.get(f"/api/cases/{cid}/documents?yon=GIDEN&durum=KESIN").json()} == {giden}
        assert {d["id"] for d in client.get(f"/api/cases/{cid}/documents?yon=GELEN&durum=TASLAK").json()} == set()

    def test_liste_gecersiz_deger_422(self, env, client):
        cid, *_ = self._seed(env)
        assert client.get(f"/api/cases/{cid}/documents?yon=ICERI").status_code == 422
        assert client.get(f"/api/cases/{cid}/documents?durum=ONAYLI").status_code == 422


# ── 8. rapor kataloğu ────────────────────────────────────────────────────────

class TestRaporKatalogu:
    def test_belgeler_kolonlari(self):
        from services.rapor import registry

        kolonlar = registry.BELGELER.kolonlar
        for anahtar, liste in (("yon", ("GELEN", "GIDEN")), ("kaynak", ("BELGE_HATTI", "PDF_ARACLARI", "WORD",
                                                                          "ARSIV_AKTARIM", "TESLIM")),
                               ("durum", ("TASLAK", "KESIN"))):
            k = kolonlar[anahtar]
            assert k.tip == "liste" and k.secenekler == liste, anahtar
            assert k.grup == "Belge"

    def test_asistan_ipucu(self):
        from services.rapor import asistan, registry

        assert "belgeler" in asistan.KAYNAK_IPUCLARI
        assert "belgeler" in registry.KAYNAKLAR
        ipucu = asistan.KAYNAK_IPUCLARI["belgeler"]
        assert "GIDEN" in ipucu and "KESIN" in ipucu and "TASLAK" in ipucu


# ── 9. ayar ──────────────────────────────────────────────────────────────────

def test_taslak_klasoru_ayari():
    from config.settings import settings

    assert settings.sharepoint_folder_taslak_name == "03_TASLAKLAR"
