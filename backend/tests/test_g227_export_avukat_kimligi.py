"""G227 — Hukukbot export'u kurumsal avukat kimliği taşır + `GET /export/lawyers`.

Kilitlenenler:
1. `GET /export/documents/{id}` ve `GET /export/documents` kayıtlarında `avukat_kimlik`
   (`case_documents.lawyer_id` → `lawyers.kimlik`) + `avukat_adi`; bağsız belgede ikisi null;
   `avukat_kodu` (DEPRECATED, G231 kalkar) ham değeriyle aynen durur.
2. `GET /export/lawyers`: `[{"kimlik", "ad", "aktif"}]` kimlik sırasıyla, pasif avukat
   `aktif:false` ile listede; `id`/e-posta/telefon/tc_no/sicil_no/gorev SIZMAZ.
3. Liste ucu anahtarsız istekte mevcut export ucuyla AYNI ret kodunu verir (router bağımlılığı).
4. `lawyers.id` hiçbir export yanıtında görünmez.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import routes.export as export
from database import Base

STRONG_KEY = "b" * 64
BASLIK = {"X-API-Key": STRONG_KEY}


@pytest.fixture()
def fabrika():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture()
def istemci(fabrika, monkeypatch):
    monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", STRONG_KEY)
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
    monkeypatch.setattr(export, "SessionLocal", fabrika)
    app = FastAPI()
    app.include_router(export.router)
    return TestClient(app)


@pytest.fixture()
def veri(fabrika):
    """İki avukat (biri pasif, kimlik sırası ekleme sırasından FARKLI) + üç belge."""
    db = fabrika()
    # Ekleme sırası kimlik sırasının tersi: sıralamanın kimlikten geldiğini kanıtlar.
    pasif = models.Lawyer(kimlik="AVK-00002", code="ESKIAVUK", name="Eski Avukat", active=False,
                          sequence=1, email="eski@ofis.test", phone="5550000000", tc_no="11111111111",
                          sicil_no="SICIL-9", gorev="DIŞ AVUKAT", address="Adres", city="İstanbul")
    tugce = models.Lawyer(kimlik="AVK-00001", code="TUGCEUNG", name="Tuğçe Ungör Yanık", active=True,
                          sequence=2, email="tugce@ofis.test", phone="5551111111", tc_no="22222222222",
                          sicil_no="SICIL-1", gorev="AVUKAT")
    db.add_all([pasif, tugce])
    db.flush()
    bagli = models.CaseDocument(original_filename="a.pdf", stored_filename="A.pdf",
                                sharepoint_url="https://sp/a.pdf", belge_turu_kodu="ARA-KRR_______",
                                link_mode="UNLINKED", lawyer_id=tugce.id, avukat_kodu="TUG")
    bagsiz = models.CaseDocument(original_filename="b.pdf", stored_filename="B.pdf",
                                 sharepoint_url="https://sp/b.pdf", belge_turu_kodu="ARA-KRR_______",
                                 link_mode="UNLINKED", lawyer_id=None, avukat_kodu=None)
    pasife_bagli = models.CaseDocument(original_filename="c.pdf", stored_filename="C.pdf",
                                       sharepoint_url="https://sp/c.pdf", belge_turu_kodu="ARA-KRR_______",
                                       link_mode="UNLINKED", lawyer_id=pasif.id, avukat_kodu="ESK")
    db.add_all([bagli, bagsiz, pasife_bagli])
    db.flush()
    for doc in (bagli, bagsiz, pasife_bagli):
        db.add(models.ExportOutbox(document_id=doc.id, status="pending"))
    db.commit()
    ids = {"bagli": bagli.id, "bagsiz": bagsiz.id, "pasife_bagli": pasife_bagli.id,
           "tugce": tugce.id, "pasif": pasif.id}
    db.close()
    return ids


# ── 1. belge kayıtları ───────────────────────────────────────────────────────

def test_tek_belge_avukat_kimligi_ve_adi(istemci, veri):
    yanit = istemci.get(f"/export/documents/{veri['bagli']}", headers=BASLIK)
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["avukat_kimlik"] == "AVK-00001"
    assert govde["avukat_adi"] == "Tuğçe Ungör Yanık"
    # GEÇİŞ: avukat_kodu ham değeriyle aynen durur (yeni hesaplama yok)
    assert govde["avukat_kodu"] == "TUG"


def test_tek_belge_bagsizda_null(istemci, veri):
    govde = istemci.get(f"/export/documents/{veri['bagsiz']}", headers=BASLIK).json()
    assert govde["avukat_kimlik"] is None
    assert govde["avukat_adi"] is None
    assert govde["avukat_kodu"] is None


def test_tek_belge_pasif_avukat_kimligi_de_gelir(istemci, veri):
    govde = istemci.get(f"/export/documents/{veri['pasife_bagli']}", headers=BASLIK).json()
    assert govde["avukat_kimlik"] == "AVK-00002"
    assert govde["avukat_adi"] == "Eski Avukat"


def test_listeleme_kayitlarinda_avukat_alanlari(istemci, veri):
    yanit = istemci.get("/export/documents", headers=BASLIK)
    assert yanit.status_code == 200
    kayitlar = {k["document_id"]: k for k in yanit.json()["items"]}
    assert set(kayitlar) == {veri["bagli"], veri["bagsiz"], veri["pasife_bagli"]}
    assert kayitlar[veri["bagli"]]["avukat_kimlik"] == "AVK-00001"
    assert kayitlar[veri["bagli"]]["avukat_adi"] == "Tuğçe Ungör Yanık"
    assert kayitlar[veri["bagsiz"]]["avukat_kimlik"] is None
    assert kayitlar[veri["bagsiz"]]["avukat_adi"] is None
    assert kayitlar[veri["pasife_bagli"]]["avukat_kimlik"] == "AVK-00002"
    assert kayitlar[veri["pasife_bagli"]]["avukat_adi"] == "Eski Avukat"


def test_belge_yanitlarinda_lawyer_id_sizmaz(istemci, veri):
    tek = istemci.get(f"/export/documents/{veri['bagli']}", headers=BASLIK).json()
    liste = istemci.get("/export/documents", headers=BASLIK).json()["items"]
    for kayit in [tek, *liste]:
        assert "lawyer_id" not in kayit
        assert "avukat_id" not in kayit


# ── 2. /export/lawyers ───────────────────────────────────────────────────────

def test_lawyers_ucu_kimlik_sirasi_ve_pasif(istemci, veri):
    yanit = istemci.get("/export/lawyers", headers=BASLIK)
    assert yanit.status_code == 200
    assert yanit.json() == [
        {"kimlik": "AVK-00001", "ad": "Tuğçe Ungör Yanık", "aktif": True},
        {"kimlik": "AVK-00002", "ad": "Eski Avukat", "aktif": False},
    ]


def test_lawyers_ucu_hassas_alan_sizdirmaz(istemci, veri):
    yanit = istemci.get("/export/lawyers", headers=BASLIK)
    govde_metni = yanit.text
    for kayit in yanit.json():
        assert set(kayit) == {"kimlik", "ad", "aktif"}
    # Değer düzeyinde de sızıntı yok (anahtar adı değişse bile yakalanır)
    for hassas in ("eski@ofis.test", "tugce@ofis.test", "5550000000", "5551111111",
                   "11111111111", "22222222222", "SICIL-9", "SICIL-1", "DIŞ AVUKAT",
                   "ESKIAVUK", "TUGCEUNG"):
        assert hassas not in govde_metni


def test_lawyers_ucu_bos_tabloda_bos_liste(istemci):
    yanit = istemci.get("/export/lawyers", headers=BASLIK)
    assert yanit.status_code == 200
    assert yanit.json() == []


# ── 3. kimlik doğrulama ──────────────────────────────────────────────────────

@pytest.mark.parametrize("baslik", [{}, {"X-API-Key": "yanlis-anahtar"}])
def test_lawyers_ucu_anahtarsiz_ayni_ret_kodu(istemci, veri, baslik):
    mevcut = istemci.get("/export/documents", headers=baslik)
    yeni = istemci.get("/export/lawyers", headers=baslik)
    assert mevcut.status_code == 401
    assert yeni.status_code == mevcut.status_code


def test_lawyers_ucu_env_yokken_fail_closed(istemci, veri, monkeypatch):
    monkeypatch.delenv("HUKDOK_EXPORT_API_KEY", raising=False)
    mevcut = istemci.get("/export/documents", headers=BASLIK)
    yeni = istemci.get("/export/lawyers", headers=BASLIK)
    assert mevcut.status_code == 503
    assert yeni.status_code == mevcut.status_code
