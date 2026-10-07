"""G284 — Word yaşam döngüsü: `POST /api/cases/{id}/belgeler/yeni`, `POST /api/documents/{id}/surum`,
`GET /api/documents/{id}/surumler`, `POST /api/documents/{id}/kesinlestir`, `POST /api/documents/{id}/yeni-surum-taslagi`.

Kalıp: `test_pdf_araclari_kart.py` (bare FastAPI + `dependency_overrides`, süreç-içi sqlite StaticPool, modül
`SessionLocal`'ları monkeypatch). SharePoint (`services.belge_yasam._sharepoint_{yukle,indir,meta}`) sahte — bellek içi
"sürücü"; `pdf_converter.convert_to_pdfa2b` sahte; `upload_queue.enqueue_upload` sahte.

Kilitlenen davranışlar:
  1. yeni: bos.docx kopyası `03_TASLAKLAR/<ofis_no>/<ad>.docx` (senkron), ad çakışmasında `-2`/`-3`, 20 sonrası 409;
     satır TASLAK/GIDEN/WORD + `sharepoint_url`=`word_url`=webUrl; yanıt `word_ac` = `ms-word:ofe|u|…`; 404 kart (tenant,
     silinmiş), 422 tür / ad / taraf; 502 SharePoint.
  2. sürüm: `surum_no` artan, sha256 + `degisti`; taslak değilse / `word_url` boşsa 409; 413 boyut; sürüm listesi.
  3. kesinleştir: AYNI satır KESIN (`kesinlesme_tarihi`, `kesinlestiren_email`, `stored_filename` `.pdf`, `sharepoint_url`
     NULL), `convert_to_pdfa2b` bütçesi `pdf_araclari_butce_saniye`, iki kuyruk (islenmis PDF/A + ham docx), son sürüm
     `kesin=True`; idempotent (aynı kimlik → `reused`, tek dönüşüm; farklı kullanıcı 409); zaten KESIN 409; meşgul 503;
     dönüşüm hatası 422; `convert_pdfa_and_queue_uploads` ÇAĞRILMAZ; export kapısı artık geçirir (allowlist içi tür).
  4. yeni sürüm taslağı: KESIN'den `<ad>-v2.docx`, `onceki_document_id`; ikinci kez `-v3`; TASLAK'tan 409; idempotent.
  5. `sablonlar/bos.docx` geçerli zip + `word/document.xml`; Dockerfile `COPY . .` + `.dockerignore` dışlamıyor.
  6. Log sözleşmesi: 502'de TEK ERROR, 4xx'te ERROR yok.
"""
import logging
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parent.parent
T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"
USER_A = {"tid": T1, "preferred_username": "a@hanyaloglu.com", "name": "Ayşe Avukat"}
USER_B = {"tid": T1, "preferred_username": "b@hanyaloglu.com"}
OFIS_NO = "DR.M.OZTURK-0003-HUK"
TURLER = [
    {"code": "DAVA-DLK______", "name": "Dava Dilekçesi"},
    {"code": "ARA-KRR_______", "name": "Ara Karar"},
]
TASLAK = "03_TASLAKLAR"


@pytest.fixture(autouse=True)
def _limiter_sifirla():
    from rate_limiting import limiter

    limiter.reset()
    yield
    limiter.reset()


class SahteSurucu:
    """Bellek içi SharePoint: `{klasör/ad: bytes}`; webUrl deterministik."""

    def __init__(self):
        self.dosyalar: dict[str, bytes] = {}
        self.yuklemeler: list[dict] = []
        self.indirmeler: list[str] = []
        self.hata_ver: str | None = None  # "yukle" | "indir" | "meta"

    def anahtar(self, klasor, ad):
        return f"{klasor}/{ad}"

    def yukle(self, yol, ad, klasor):
        if self.hata_ver == "yukle":
            raise RuntimeError("Graph 500")
        with open(yol, "rb") as f:
            veri = f.read()
        self.dosyalar[self.anahtar(klasor, ad)] = veri
        self.yuklemeler.append({"klasor": klasor, "ad": ad, "boyut": len(veri)})
        return {"id": "x", "name": ad, "webUrl": f"https://sp.test/{klasor}/{ad}"}

    def indir(self, klasor, ad):
        if self.hata_ver == "indir":
            raise RuntimeError("Graph 503")
        self.indirmeler.append(self.anahtar(klasor, ad))
        veri = self.dosyalar.get(self.anahtar(klasor, ad))
        if veri is None:
            raise FileNotFoundError(ad)
        return veri, "application/octet-stream"

    def meta(self, klasor, ad):
        if self.hata_ver == "meta":
            raise RuntimeError("Graph 500")
        veri = self.dosyalar.get(self.anahtar(klasor, ad))
        if veri is None:
            return None
        return {"id": "x", "name": ad, "size": len(veri), "webUrl": f"https://sp.test/{klasor}/{ad}", "eTag": f"etag-{len(veri)}"}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    import database
    from database import Base
    import models
    import pdf.pdf_converter as pdf_converter
    from routes import belge_yasam as route_mod
    from services import archive_names, belge_yasam, confirm_idempotency, document_pipeline, upload_queue

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for mod in (route_mod, belge_yasam, document_pipeline, confirm_idempotency, archive_names, upload_queue, database):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    monkeypatch.setattr(route_mod, "_belge_turleri", lambda: TURLER)

    surucu = SahteSurucu()
    monkeypatch.setattr(belge_yasam, "_sharepoint_yukle", surucu.yukle)
    monkeypatch.setattr(belge_yasam, "_sharepoint_indir", surucu.indir)
    monkeypatch.setattr(belge_yasam, "_sharepoint_meta", surucu.meta)

    db = maker()
    kart = models.Case(tracking_no=OFIS_NO, tenant_id=T1, esas_no="2026/111")
    kart_b = models.Case(tracking_no="KR.ENTHONE-0015-CEZ", tenant_id=T2, esas_no="2026/222")
    silinmis = models.Case(tracking_no="SG-0001-HUK", tenant_id=T1, deleted_at=datetime.now(timezone.utc))
    ofissiz = models.Case(tracking_no="", tenant_id=T1)  # kolon NOT NULL; boş ofis no → klasör `kart-<id>`
    db.add_all([kart, kart_b, silinmis, ofissiz])
    db.commit()
    taraf = models.CaseParty(case_id=kart.id, name="Mehmet Öztürk", role="Davacı", party_type="CLIENT")
    taraf_b = models.CaseParty(case_id=kart_b.id, name="Enthone", role="Davalı", party_type="CLIENT")
    db.add_all([taraf, taraf_b])
    db.commit()
    ids = SimpleNamespace(kart=kart.id, kart_b=kart_b.id, silinmis=silinmis.id, ofissiz=ofissiz.id, taraf=taraf.id, taraf_b=taraf_b.id)
    db.close()

    convert_calls: list[dict] = []
    convert_hata: dict = {"exc": None}

    def _sahte_pdfa(source_path, time_budget_seconds=None):
        if convert_hata["exc"] is not None:
            raise convert_hata["exc"]
        hedef = tmp_path / f"pdfa_{len(convert_calls)}.pdf"
        shutil.copy2(source_path, hedef)
        convert_calls.append({"source": source_path, "budget": time_budget_seconds, "out": str(hedef)})
        return str(hedef)

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", _sahte_pdfa)

    enqueue_calls: list[dict] = []
    enqueue_sonuc: dict = {"none": False}

    def _sahte_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        with open(source_path, "rb") as f:
            veri = f.read()
        enqueue_calls.append({"kind": kind, "source": source_path, "filename": target_filename,
                              "folder": target_folder, "document_id": document_id, "boyut": len(veri)})
        return None if enqueue_sonuc["none"] else len(enqueue_calls)

    monkeypatch.setattr(upload_queue, "enqueue_upload", _sahte_enqueue)

    pipeline_calls: list = []
    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads",
                        lambda *a, **k: pipeline_calls.append((a, k)) or (None, None))

    yield SimpleNamespace(sessions=maker, models=models, ids=ids, surucu=surucu, convert_calls=convert_calls,
                          convert_hata=convert_hata, enqueue_calls=enqueue_calls, enqueue_sonuc=enqueue_sonuc,
                          pipeline_calls=pipeline_calls, route=route_mod, servis=belge_yasam, tmp=tmp_path)
    engine.dispose()


@pytest.fixture()
def client_factory(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user

    def _make(user: dict = USER_A):
        app = FastAPI()
        app.include_router(env.route.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_tenant] = lambda: user["tid"]
        return TestClient(app, raise_server_exceptions=False)

    return _make


def _yeni(client, case_id, ad="Cevap Dilekcesi", **ek):
    govde = {"belge_turu_kodu": "DAVA-DLK", "ad": ad, **ek}
    return client.post(f"/api/cases/{case_id}/belgeler/yeni", json=govde)


def _belge(env, doc_id):
    db = env.sessions()
    try:
        doc = db.query(env.models.CaseDocument).filter(env.models.CaseDocument.id == doc_id).first()
        db.refresh(doc)
        db.expunge(doc)
        return doc
    finally:
        db.close()


def _surumler(env, doc_id):
    db = env.sessions()
    try:
        return [(s.surum_no, s.sha256, s.kesin, s.aciklama_notu) for s in
                db.query(env.models.BelgeSurumu).filter(env.models.BelgeSurumu.document_id == doc_id)
                .order_by(env.models.BelgeSurumu.surum_no).all()]
    finally:
        db.close()


# ── 5. Şablon ve imaj ────────────────────────────────────────────────────────

class TestSablon:
    def test_bos_docx_gecerli_zip_ve_document_xml(self):
        yol = BACKEND / "sablonlar" / "bos.docx"
        assert yol.exists()
        with zipfile.ZipFile(yol) as z:
            assert z.testzip() is None
            adlar = z.namelist()
            assert "[Content_Types].xml" in adlar and "word/document.xml" in adlar and "_rels/.rels" in adlar
            assert b"<w:document" in z.read("word/document.xml")

    def test_dockerfile_copy_kapsar_ve_dockerignore_dislamaz(self):
        dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
        assert re.search(r"^COPY \. \.", dockerfile, re.M)
        ignore = (BACKEND / ".dockerignore").read_text(encoding="utf-8") if (BACKEND / ".dockerignore").exists() else ""
        satirlar = [s.strip() for s in ignore.splitlines() if s.strip() and not s.startswith("#")]
        assert not any(s.rstrip("/") == "sablonlar" or s.startswith("sablonlar/") for s in satirlar)

    def test_servis_sablon_dizini_imajdaki_yola_karsilik(self, env):
        assert env.servis.SABLON_DIZINI == BACKEND / "sablonlar"
        assert (env.servis.SABLON_DIZINI / env.servis.SABLONLAR["bos"]).exists()


# ── 1. Yeni belge ─────────────────────────────────────────────────────────────

class TestYeniBelge:
    def test_sablon_kopyasi_taslak_klasorune_senkron_yuklenir_ve_satir_acilir(self, env, client_factory):
        client = client_factory()
        r = _yeni(client, env.ids.kart, case_party_id=env.ids.taraf)
        assert r.status_code == 200, r.text
        g = r.json()
        assert g["word_url"] == f"https://sp.test/{TASLAK}/{OFIS_NO}/Cevap_Dilekcesi.docx"  # sanitize: boşluk → _
        assert g["word_ac"] == f"ms-word:ofe|u|{g['word_url']}"
        assert env.surucu.yuklemeler == [{"klasor": f"{TASLAK}/{OFIS_NO}", "ad": "Cevap_Dilekcesi.docx",
                                          "boyut": (BACKEND / "sablonlar" / "bos.docx").stat().st_size}]
        doc = _belge(env, g["document_id"])
        assert (doc.yon, doc.kaynak, doc.durum) == ("GIDEN", "WORD", "TASLAK")
        assert doc.sharepoint_url == g["word_url"] and doc.word_url == g["word_url"]
        assert doc.original_filename == "Cevap_Dilekcesi.docx" and doc.stored_filename == "Cevap_Dilekcesi.docx"
        assert doc.belge_turu_kodu == "DAVA-DLK______" and doc.belge_turu_adi == "Dava Dilekçesi"
        assert doc.case_party_id == env.ids.taraf and doc.link_mode == "LINKED"
        assert doc.uploaded_by == "Ayşe Avukat" and doc.uploaded_by_email == "a@hanyaloglu.com"
        assert env.enqueue_calls == [] and env.pipeline_calls == []  # kuyruk yok: senkron yükleme
        assert _surumler(env, doc.id) == []

    def test_ad_cakismasi_eki_ve_uzanti_zorlamasi(self, env, client_factory):
        client = client_factory()
        for beklenen in ("Dilekce.docx", "Dilekce-2.docx", "Dilekce-3.docx"):
            r = _yeni(client, env.ids.kart, ad="Dilekce.DOCX")
            assert r.status_code == 200, r.text
            assert r.json()["word_url"].endswith(f"/{beklenen}")
        r = _yeni(client, env.ids.kart, ad="rapor")  # uzantısız ad → `.docx` eklenir
        assert r.status_code == 200 and r.json()["word_url"].endswith("/rapor.docx")
        r = _yeni(client, env.ids.kart, ad="eski.doc")  # `.doc` → `.docx` (şablon docx)
        assert r.status_code == 200 and r.json()["word_url"].endswith("/eski.docx")

    def test_ad_cakismasi_siniri_409(self, env, client_factory):
        client = client_factory()
        klasor = f"{TASLAK}/{OFIS_NO}"
        env.surucu.dosyalar[f"{klasor}/X.docx"] = b"a"
        for n in range(2, 21):
            env.surucu.dosyalar[f"{klasor}/X-{n}.docx"] = b"a"
        r = _yeni(client, env.ids.kart, ad="X")
        assert r.status_code == 409 and r.json()["detail"]["error_kod"] == "ad_cakismasi"
        assert env.surucu.yuklemeler == []

    def test_ofissiz_kart_klasoru_ve_bos_ad_422(self, env, client_factory):
        client = client_factory()
        r = _yeni(client, env.ids.ofissiz, ad="Not")
        assert r.status_code == 200 and f"/{TASLAK}/kart-{env.ids.ofissiz}/Not.docx" in r.json()["word_url"]
        for kotu in (".docx", "   ", "___"):
            r = _yeni(client, env.ids.kart, ad=kotu)
            assert r.status_code == 422, kotu
            assert r.json()["detail"]["error_kod"] == "belge_adi"

    def test_404_kart_422_tur_ve_taraf(self, env, client_factory):
        client = client_factory()
        assert _yeni(client, env.ids.kart_b).status_code == 404  # başka tenant
        assert _yeni(client, env.ids.silinmis).status_code == 404
        assert _yeni(client, 99999).status_code == 404
        r = client.post(f"/api/cases/{env.ids.kart}/belgeler/yeni", json={"belge_turu_kodu": "YOK", "ad": "a"})
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "belge_turu"
        r = _yeni(client, env.ids.kart, case_party_id=env.ids.taraf_b)
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "taraf"
        r = client.post(f"/api/cases/{env.ids.kart}/belgeler/yeni", json={"belge_turu_kodu": "DAVA-DLK", "ad": "a", "sablon": "yok"})
        assert r.status_code == 422
        assert env.surucu.yuklemeler == []

    def test_sharepoint_hatasi_502_tek_error(self, env, client_factory, caplog):
        client = client_factory()
        env.surucu.hata_ver = "yukle"
        with caplog.at_level(logging.WARNING):
            r = _yeni(client, env.ids.kart)
        assert r.status_code == 502 and r.json()["detail"]["error_kod"] == "sharepoint"
        assert sum(1 for rec in caplog.records if rec.levelno >= logging.ERROR) == 1
        db = env.sessions()
        try:
            assert db.query(env.models.CaseDocument).count() == 0  # satır açılmadı
        finally:
            db.close()
        env.surucu.hata_ver = "meta"
        r = _yeni(client, env.ids.kart)
        assert r.status_code == 502


# ── 2-3. Sürüm ────────────────────────────────────────────────────────────────

def _taslak_ac(env, client, ad="Taslak"):
    r = _yeni(client, env.ids.kart, ad=ad)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _taslak_yaz(env, doc_id, veri: bytes):
    doc = _belge(env, doc_id)
    klasor = f"{TASLAK}/{OFIS_NO}"
    env.surucu.dosyalar[f"{klasor}/{doc.original_filename}"] = veri


class TestSurum:
    def test_surum_kaydet_artan_no_sha_ve_degisti(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        r = client.post(f"/api/documents/{doc_id}/surum", json={"not": "ilk hali"})
        assert r.status_code == 200, r.text
        g1 = r.json()
        assert g1["surum_no"] == 1 and g1["degisti"] is True and len(g1["sha256"]) == 64
        r = client.post(f"/api/documents/{doc_id}/surum", json={})
        assert r.json() == {"surum_no": 2, "sha256": g1["sha256"], "degisti": False}
        _taslak_yaz(env, doc_id, b"yeni icerik")
        r = client.post(f"/api/documents/{doc_id}/surum")
        assert r.status_code == 200 and r.json()["surum_no"] == 3 and r.json()["degisti"] is True
        assert [(n, k, nt) for n, _s, k, nt in _surumler(env, doc_id)] == [(1, False, "ilk hali"), (2, False, None), (3, False, None)]

        r = client.get(f"/api/documents/{doc_id}/surumler")
        assert r.status_code == 200
        liste = r.json()
        assert [s["surum_no"] for s in liste] == [1, 2, 3]
        assert liste[0]["not"] == "ilk hali" and liste[0]["olusturan_email"] == "a@hanyaloglu.com"
        assert all(s["kesin"] is False for s in liste) and liste[0]["olusturulma"]

    def test_taslak_degil_veya_word_url_bos_409_boyut_413_404(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        db = env.sessions()
        try:
            doc = db.get(env.models.CaseDocument, doc_id)
            doc.word_url = None
            db.commit()
        finally:
            db.close()
        r = client.post(f"/api/documents/{doc_id}/surum")
        assert r.status_code == 409 and r.json()["detail"]["error_kod"] == "taslak_degil"
        db = env.sessions()
        try:
            doc = db.get(env.models.CaseDocument, doc_id)
            doc.word_url = "https://sp.test/x"
            doc.durum = "KESIN"
            db.commit()
        finally:
            db.close()
        assert client.post(f"/api/documents/{doc_id}/surum").status_code == 409
        assert client.post("/api/documents/99999/surum").status_code == 404
        assert client.get("/api/documents/99999/surumler").status_code == 404
        assert client_factory({"tid": T2, "preferred_username": "x@lexisbio.com"}).get(f"/api/documents/{doc_id}/surumler").status_code == 404

        doc2 = _taslak_ac(env, client, ad="Buyuk")
        from file_utils import MAX_UPLOAD_BYTES
        _taslak_yaz(env, doc2, b"x" * (MAX_UPLOAD_BYTES + 1))
        r = client.post(f"/api/documents/{doc2}/surum")
        assert r.status_code == 413 and r.json()["detail"]["error_kod"] == "boyut"

    def test_sharepoint_indirme_hatasi_502(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        env.surucu.hata_ver = "indir"
        r = client.post(f"/api/documents/{doc_id}/surum")
        assert r.status_code == 502 and r.json()["detail"]["error_kod"] == "sharepoint"
        assert _surumler(env, doc_id) == []


# ── 4. Kesinleştir ────────────────────────────────────────────────────────────

class TestKesinlestir:
    def test_ayni_satir_kesin_iki_kuyruk_son_surum_kesin(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client, ad="Cevap")
        _taslak_yaz(env, doc_id, b"docx-icerik")
        client.post(f"/api/documents/{doc_id}/surum", json={"not": "son"})
        kimlik = str(uuid.uuid4())
        r = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": kimlik})
        assert r.status_code == 200, r.text
        assert r.json() == {"document_id": doc_id, "reused": False}

        doc = _belge(env, doc_id)
        assert doc.durum == "KESIN" and doc.yon == "GIDEN" and doc.kaynak == "WORD"
        assert doc.kesinlesme_tarihi is not None and doc.kesinlestiren_email == "a@hanyaloglu.com"
        assert doc.stored_filename == "Cevap.pdf" and doc.original_filename == "Cevap.docx"
        assert doc.sharepoint_url is None and doc.upload_status == "pending"  # URL commit'i kuyrukta
        assert doc.word_url is not None  # taslak .docx 03_TASLAKLAR'da kalır (salt okunur gösterim)
        db = env.sessions()
        try:
            assert db.query(env.models.CaseDocument).count() == 1  # yeni satır YOK
        finally:
            db.close()

        assert len(env.convert_calls) == 1
        from config.settings import settings
        assert env.convert_calls[0]["budget"] == settings.pdf_araclari_butce_saniye
        assert env.convert_calls[0]["source"].endswith("Cevap.docx")
        assert env.pipeline_calls == []  # convert_pdfa_and_queue_uploads KULLANILMAZ

        turler = [(c["kind"], c["filename"], c["folder"], c["document_id"]) for c in env.enqueue_calls]
        bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert turler == [
            ("islenmis", "Cevap.pdf", os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV"), doc_id),
            ("ham", f"{bugun}_Cevap.docx", os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV"), None),
        ]
        assert env.enqueue_calls[1]["boyut"] == len(b"docx-icerik")
        assert not os.path.exists(env.enqueue_calls[1]["source"])  # geçici dizin silindi (kuyruk kopyaladı)

        surumler = _surumler(env, doc_id)
        assert [(n, k, nt) for n, _s, k, nt in surumler] == [(1, False, "son"), (2, True, "Kesinleştirme")]
        liste = client.get(f"/api/documents/{doc_id}/surumler").json()
        assert [s["kesin"] for s in liste] == [False, True]

    def test_idempotent_ayni_kimlik_reused_tek_donusum_farkli_kullanici_409(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        kimlik = str(uuid.uuid4())
        r1 = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": kimlik})
        r2 = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": kimlik})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json() == {"document_id": doc_id, "reused": True}
        assert len(env.convert_calls) == 1 and len(env.enqueue_calls) == 2
        assert len(_surumler(env, doc_id)) == 1
        r3 = client_factory(USER_B).post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": kimlik})
        assert r3.status_code == 409
        # yeni kimlikle: belge artık KESIN → 409, kayıt bırakılır (yeniden denenebilir)
        r4 = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())})
        assert r4.status_code == 409 and r4.json()["detail"]["error_kod"] == "zaten_kesin"
        assert client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": "x"}).status_code == 422

    def test_mesgul_503_donusum_hatasi_422_satir_degismez(self, env, client_factory, caplog):
        from pdf.format_converter import ConversionBusyError

        client = client_factory()
        doc_id = _taslak_ac(env, client)
        env.convert_hata["exc"] = ConversionBusyError("dolu")
        r = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 503 and r.json()["detail"]["error_kod"] == "sistem_mesgul"
        env.convert_hata["exc"] = RuntimeError("LibreOffice düştü")
        caplog.clear()  # 503 meşgul 5xx'tir (TEK ERROR, sözleşme gereği); 4xx'te ERROR olmadığı ayrı ölçülür
        with caplog.at_level(logging.WARNING):
            r = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "donusum_basarisiz"
        assert not any(rec.levelno >= logging.ERROR for rec in caplog.records)  # 4xx'te ERROR yok
        doc = _belge(env, doc_id)
        assert doc.durum == "TASLAK" and doc.sharepoint_url is not None and doc.stored_filename.endswith(".docx")
        assert env.enqueue_calls == [] and _surumler(env, doc_id) == []
        # düzelince aynı belge kesinleşir
        env.convert_hata["exc"] = None
        assert client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())}).status_code == 200

    def test_kuyruk_arizasinda_geri_dusus_gorevi(self, env, client_factory, monkeypatch):
        """`enqueue_upload` None dönerse (kuyruk arızası) eski tek-denemeli BackgroundTasks yolu: görev anında dosya durur."""
        from services import document_pipeline

        gorevler: list[tuple] = []
        monkeypatch.setattr(document_pipeline, "async_islenmis_upload",
                            lambda yol, ad, klasor, doc_id=None: gorevler.append(("islenmis", ad, klasor, doc_id, os.path.exists(yol))))
        monkeypatch.setattr(document_pipeline, "async_ham_upload",
                            lambda yol, ad, klasor: gorevler.append(("ham", ad, klasor, os.path.exists(yol))))
        client = client_factory()
        doc_id = _taslak_ac(env, client, ad="Ariza")
        env.enqueue_sonuc["none"] = True
        r = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 200, r.text
        # TestClient arkaplan görevlerini yanıttan önce koşturur
        assert [g[0] for g in gorevler] == ["islenmis", "ham"]
        assert gorevler[0][1] == "Ariza.pdf" and gorevler[0][3] == doc_id and gorevler[0][4] is True
        assert gorevler[1][1].endswith("_Ariza.docx") and gorevler[1][3] is True
        assert _belge(env, doc_id).durum == "KESIN"

    def test_export_kapisi_kesinlesince_gecirir(self, env, client_factory, monkeypatch):
        """G282 kapısı: TASLAK iken `enqueue_document` None; KESIN ama URL'siz (kuyruk henüz yazmadı) yine None;
        URL commit edilince (upload_queue anı) allowlist içi tür `export_outbox` satırı açar. Allowlist env'den
        (`HUKDOK_EXPORT_TYPES`); boşsa her tür geçer. `enqueue_document` `database.SessionLocal`'ı kullanır (env patch'li)."""
        from services import export_publisher

        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        assert export_publisher.enqueue_document(doc_id) is None  # TASLAK + URL dolu → geçmez
        r = client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 200
        assert export_publisher.enqueue_document(doc_id) is None  # KESIN ama sharepoint_url NULL → geçmez
        db = env.sessions()
        try:
            doc = db.get(env.models.CaseDocument, doc_id)
            doc.sharepoint_url = "https://sp.test/02_YEDEK_ARSIV/Taslak.pdf"  # upload_queue'nun yazacağı an
            db.commit()
        finally:
            db.close()
        assert export_publisher.enqueue_document(doc_id) is not None
        db = env.sessions()
        try:
            assert db.query(env.models.ExportOutbox).filter(env.models.ExportOutbox.document_id == doc_id).count() == 1
        finally:
            db.close()


# ── 5. Yeni sürüm taslağı ─────────────────────────────────────────────────────

class TestYeniSurumTaslagi:
    def test_kesinden_v2_ve_v3_onceki_bagi_idempotent(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client, ad="Cevap")
        _taslak_yaz(env, doc_id, b"kesin-docx")
        assert client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())}).status_code == 200
        kimlik = str(uuid.uuid4())
        r = client.post(f"/api/documents/{doc_id}/yeni-surum-taslagi", json={"istek_kimligi": kimlik})
        assert r.status_code == 200, r.text
        g = r.json()
        assert g["reused"] is False and g["word_url"].endswith(f"/{TASLAK}/{OFIS_NO}/Cevap-v2.docx")
        assert g["word_ac"].startswith("ms-word:ofe|u|")
        yeni = _belge(env, g["document_id"])
        assert (yeni.durum, yeni.yon, yeni.kaynak) == ("TASLAK", "GIDEN", "WORD")
        assert yeni.onceki_document_id == doc_id and yeni.original_filename == "Cevap-v2.docx"
        assert yeni.belge_turu_kodu == "DAVA-DLK______" and yeni.case_id == env.ids.kart
        assert env.surucu.dosyalar[f"{TASLAK}/{OFIS_NO}/Cevap-v2.docx"] == b"kesin-docx"  # içerik kesinleşen docx
        eski = _belge(env, doc_id)
        assert eski.durum == "KESIN" and eski.stored_filename == "Cevap.pdf"  # gönderilen değişmez

        r2 = client.post(f"/api/documents/{doc_id}/yeni-surum-taslagi", json={"istek_kimligi": kimlik})
        assert r2.json()["document_id"] == g["document_id"] and r2.json()["reused"] is True
        r3 = client.post(f"/api/documents/{doc_id}/yeni-surum-taslagi", json={"istek_kimligi": str(uuid.uuid4())})
        assert r3.status_code == 200 and r3.json()["word_url"].endswith("/Cevap-v3.docx")
        db = env.sessions()
        try:
            assert db.query(env.models.CaseDocument).count() == 3
        finally:
            db.close()

    def test_taslaktan_409_404_ve_sharepoint_502(self, env, client_factory):
        client = client_factory()
        doc_id = _taslak_ac(env, client)
        r = client.post(f"/api/documents/{doc_id}/yeni-surum-taslagi", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 409 and r.json()["detail"]["error_kod"] == "kesin_degil"
        assert client.post("/api/documents/99999/yeni-surum-taslagi", json={"istek_kimligi": str(uuid.uuid4())}).status_code == 404
        assert client.post(f"/api/documents/{doc_id}/kesinlestir", json={"istek_kimligi": str(uuid.uuid4())}).status_code == 200
        env.surucu.hata_ver = "indir"
        r = client.post(f"/api/documents/{doc_id}/yeni-surum-taslagi", json={"istek_kimligi": str(uuid.uuid4())})
        assert r.status_code == 502
        db = env.sessions()
        try:
            assert db.query(env.models.CaseDocument).count() == 1
        finally:
            db.close()


# ── Rota bekçileri ────────────────────────────────────────────────────────────

class TestRotalar:
    def test_bes_rota_ve_api_py_kaydi(self):
        from routes import belge_yasam as route_mod

        yollar = sorted({(r.path, tuple(sorted(r.methods))) for r in route_mod.router.routes})
        assert yollar == [
            ("/api/cases/{case_id}/belgeler/yeni", ("POST",)),
            ("/api/documents/{document_id}/kesinlestir", ("POST",)),
            ("/api/documents/{document_id}/surum", ("POST",)),
            ("/api/documents/{document_id}/surumler", ("GET",)),
            ("/api/documents/{document_id}/yeni-surum-taslagi", ("POST",)),
        ]
        api_py = (BACKEND / "api.py").read_text(encoding="utf-8")
        assert "app.include_router(belge_yasam.router)" in api_py
        nginx_yolu = BACKEND.parent / "nginx.conf"
        if nginx_yolu.exists():  # konteynerde /app yalnız backend'dir (repo kökü yok) — host/CI'da koşar
            nginx = nginx_yolu.read_text(encoding="utf-8")
            assert "belgeler/yeni" not in nginx and "kesinlestir" not in nginx  # her yol /api altında, nginx değişmedi
