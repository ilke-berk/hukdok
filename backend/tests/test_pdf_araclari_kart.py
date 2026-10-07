"""G269 — PDF araçları ↔ dava kartı: `POST /api/pdf-araclari/karta-bagla` + `POST /api/pdf-araclari/karttan-al`.

Kalıp: `test_pdf_araclari_uclari.py` (bare FastAPI + `dependency_overrides`) + `test_g282_belge_yon_durum.py`
(süreç-içi sqlite, StaticPool; modül `SessionLocal`'ları monkeypatch). PDF/A adımı (`pdf.pdf_converter.convert_to_pdfa2b`)
ve kuyruk (`upload_queue.enqueue_upload`) sahtedir — Ghostscript/SharePoint yok; SharePoint indirme (`_sharepoint_indir`) sahte.

Kilitlenen davranışlar:
  1. KESIN → MEVCUT hat (`convert_pdfa_and_queue_uploads`): kaynak PDF_ARACLARI, yön istekten, ham+işlenmiş iki kuyruk,
     bütçe `pdf_araclari_butce_saniye`, `lawyer_id` boş, esas no karttan, çalışma dosyası SİLİNMEZ, PDF/A geçicisi silinir.
  2. TASLAK → PDF/A YOK, `save_case_document(durum=TASLAK)` + TEK `islenmis` kuyruğu `03_TASLAKLAR/<ofis_no>`; G282
     filtreleri: export_outbox satırı YOK, bildirim YOK.
  3. Idempotent: aynı `istek_kimligi` + kullanıcı → aynı `document_id`, `reused: true`, tek satır; farklı kullanıcı 409;
     sürüyor 409; belge yaratılmadan düşen istek (503 meşgul, 409 kilit, 4xx doğrulama) kaydı bırakır.
  4. 404 sahiplik / kart (tenant, soft-delete); 422 tür (padding normalize), ad (`.pdf` zorlanır), taraf, yön/durum.
  5. Hukukbot: allowlist içi tür outbox satırı AÇAR, dışı AÇMAZ (mevcut kural); `belge_islendi` yolu KESIN'de çağrılır.
  6. `save_case_document` kilit beklemesi (`is_lock_timeout`) → `KayitMesgulError`; `convert_pdfa_and_queue_uploads`
     yeni parametresinin varsayılanı None (/confirm ve intake değişmedi).
  7. `karttan-al`: KESIN belge işlenmiş arşivden, TASLAK belge taslak klasöründen; `Dosya` yanıtı + indirme; 404 URL yok /
     başka tenant / silinmiş; 502 SharePoint (`error_kod: sharepoint`); 413 boyut; dönüşüm hatası 422; uzantı korunur.
"""
import inspect
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"
USER_A = {"tid": T1, "preferred_username": "a@hanyaloglu.com", "name": "Ayşe Avukat"}
USER_B = {"tid": T1, "preferred_username": "b@hanyaloglu.com"}
OFIS_NO = "DR.M.OZTURK-0003-HUK"
TURLER = [
    {"code": "DAVA-DLK______", "name": "Dava Dilekçesi"},
    {"code": "ARA-KRR_______", "name": "Ara Karar"},
]


def _pdf_bytes(metinler=("BIR", "IKI", "UC")) -> bytes:
    with fitz.open() as doc:
        for m in metinler:
            page = doc.new_page(width=600, height=800)
            page.insert_text((50, 100), m, fontsize=20)
        return doc.tobytes()


@pytest.fixture(autouse=True)
def _limiter_sifirla():
    from rate_limiting import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """sqlite + sahte PDF/A + sahte kuyruk + sahte tür listesi; tohum: kart A (T1), taraf, kart B (T2), silinmiş, paylaşımlı."""
    import database
    from database import Base
    import models
    import pdf.pdf_converter as pdf_converter
    from routes import pdf_araclari as route_mod
    from routes import processing
    from services import archive_names, confirm_idempotency, document_pipeline, upload_queue

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for mod in (route_mod, document_pipeline, confirm_idempotency, archive_names, upload_queue, database):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    monkeypatch.setenv("PDF_ARACLARI_DIR", str(tmp_path / "pdf_araclari"))
    monkeypatch.setattr(route_mod, "_belge_turleri", lambda: TURLER)

    db = maker()
    kart = models.Case(tracking_no=OFIS_NO, tenant_id=T1, esas_no="2026/111")
    kart_b = models.Case(tracking_no="KR.ENTHONE-0015-CEZ", tenant_id=T2, esas_no="2026/222")
    silinmis = models.Case(tracking_no="SG-0001-HUK", tenant_id=T1, deleted_at=datetime.now(timezone.utc))
    paylasimli = models.Case(tracking_no="2024/1234", tenant_id=None, esas_no="2024/9")
    db.add_all([kart, kart_b, silinmis, paylasimli])
    db.commit()
    taraf = models.CaseParty(case_id=kart.id, name="Mehmet Öztürk", role="Davacı", party_type="CLIENT")
    taraf_b = models.CaseParty(case_id=kart_b.id, name="Enthone", role="Davalı", party_type="CLIENT")
    db.add_all([taraf, taraf_b])
    db.commit()
    ids = SimpleNamespace(kart=kart.id, kart_b=kart_b.id, silinmis=silinmis.id, paylasimli=paylasimli.id,
                          taraf=taraf.id, taraf_b=taraf_b.id)
    db.close()

    convert_calls: list[dict] = []

    def _sahte_pdfa(source_path, time_budget_seconds=None):
        hedef = tmp_path / f"pdfa_{len(convert_calls)}.pdf"
        shutil.copy2(source_path, hedef)
        convert_calls.append({"source": source_path, "budget": time_budget_seconds, "out": str(hedef)})
        return str(hedef)

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", _sahte_pdfa)

    enqueue_calls: list[dict] = []

    def _sahte_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        enqueue_calls.append({"kind": kind, "source": source_path, "filename": target_filename,
                              "folder": target_folder, "document_id": document_id})
        return len(enqueue_calls)

    monkeypatch.setattr(upload_queue, "enqueue_upload", _sahte_enqueue)

    yield SimpleNamespace(sessions=maker, models=models, ids=ids, convert_calls=convert_calls,
                          enqueue_calls=enqueue_calls, route=route_mod, processing=processing, tmp=tmp_path)
    engine.dispose()


@pytest.fixture()
def client_factory(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user

    def _make(user: dict = USER_A):
        app = FastAPI()
        app.include_router(env.route.router)
        app.include_router(env.processing.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_tenant] = lambda: user["tid"]
        return TestClient(app, raise_server_exceptions=False)

    return _make


def _yukle(client, icerik: bytes | None = None, ad="dilekce.pdf") -> dict:
    r = client.post("/api/pdf-araclari/yukle", files={"file": (ad, icerik or _pdf_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def _bagla(client, env, dosya_id=None, **ek):
    govde = {
        "id": dosya_id or _yukle(client)["id"],
        "case_id": env.ids.kart,
        "belge_turu_kodu": "DAVA-DLK",
        "dosya_adi": "dilekce_son.pdf",
        "istek_kimligi": str(uuid.uuid4()),
    }
    govde.update(ek)
    return client.post("/api/pdf-araclari/karta-bagla", json=govde)


def _belgeler(env):
    db = env.sessions()
    try:
        return db.query(env.models.CaseDocument).order_by(env.models.CaseDocument.id).all()
    finally:
        db.close()


def _fisler(env):
    db = env.sessions()
    try:
        return db.query(env.models.ConfirmReceipt).all()
    finally:
        db.close()


def _url_yaz(env, doc_id, url="https://sp/x.pdf"):
    db = env.sessions()
    try:
        doc = db.get(env.models.CaseDocument, doc_id)
        doc.sharepoint_url = url
        db.commit()
    finally:
        db.close()


# ── 1. KESIN yolu ────────────────────────────────────────────────────────────

class TestKartaBaglaKesin:
    def test_kesin_mevcut_hat(self, client_factory, env):
        from config.settings import settings

        client = client_factory()
        dosya = _yukle(client)
        calisma_yolu = env.processing.DOWNLOAD_CACHE.get(dosya["id"])["path"]
        kimlik = str(uuid.uuid4())
        r = _bagla(client, env, dosya_id=dosya["id"], istek_kimligi=kimlik, case_party_id=env.ids.taraf)
        assert r.status_code == 200, r.text
        assert r.json() == {"document_id": r.json()["document_id"], "reused": False}

        [doc] = _belgeler(env)
        assert doc.id == r.json()["document_id"]
        assert doc.case_id == env.ids.kart and doc.link_mode == "LINKED"
        assert (doc.yon, doc.kaynak, doc.durum) == ("GELEN", "PDF_ARACLARI", "KESIN")
        assert doc.belge_turu_kodu == "DAVA-DLK______"  # kanonik (pad'li) kod
        assert doc.stored_filename == "dilekce_son.pdf" and doc.original_filename == "dilekce.pdf"
        assert doc.esas_no == "2026/111" and doc.lawyer_id is None and doc.case_party_id == env.ids.taraf
        assert doc.uploaded_by == "Ayşe Avukat" and doc.uploaded_by_email == "a@hanyaloglu.com"
        assert doc.ai_summary is None and doc.conversion_status is None and doc.email_sent is None

        # PDF/A: tezgâh bütçesiyle, çalışma dosyasından
        [cv] = env.convert_calls
        assert cv["source"] == calisma_yolu and cv["budget"] == settings.pdf_araclari_butce_saniye
        # İki arşiv kuyruğu: ham = çalışma PDF'i tarihli adla, işlenmiş = PDF/A
        ham, islenmis = env.enqueue_calls
        assert ham["kind"] == "ham" and ham["folder"] == "01_HAM_ARSIV" and ham["source"] == calisma_yolu
        assert ham["filename"].endswith("_dilekce_son.pdf") and ham["document_id"] == doc.id
        assert islenmis["kind"] == "islenmis" and islenmis["folder"] == "02_YEDEK_ARSIV"
        assert islenmis["filename"] == "dilekce_son.pdf" and islenmis["source"] == cv["out"]
        # Çalışma dosyası yerinde (zincir sürer), PDF/A geçicisi arka planda silindi
        assert os.path.exists(calisma_yolu) and env.processing.DOWNLOAD_CACHE.get(dosya["id"])
        assert not os.path.exists(cv["out"])
        # Idempotency fişi: önekli anahtar, tamamlandı
        [fis] = _fisler(env)
        assert fis.process_id == f"pdf_araclari:{kimlik}" and fis.status == "completed"
        assert fis.owner == "a@hanyaloglu.com"

    def test_yon_giden_kucuk_harf_normalize(self, client_factory, env):
        r = _bagla(client_factory(), env, yon="giden")
        assert r.status_code == 200, r.text
        assert _belgeler(env)[0].yon == "GIDEN"

    def test_tur_kodu_padding_normalize(self, client_factory, env):
        r = _bagla(client_factory(), env, belge_turu_kodu="ara-krr")
        assert r.status_code == 200, r.text
        assert _belgeler(env)[0].belge_turu_kodu == "ARA-KRR_______"

    @pytest.mark.parametrize("ad,beklenen", [("rapor.docx", "rapor.pdf"), ("rapor", "rapor.pdf"), ("  mazbata.PDF ", "mazbata.pdf")])
    def test_pdf_uzantisi_zorlanir(self, client_factory, env, ad, beklenen):
        r = _bagla(client_factory(), env, dosya_adi=ad)
        assert r.status_code == 200, r.text
        assert _belgeler(env)[0].stored_filename == beklenen


# ── 2. idempotency ───────────────────────────────────────────────────────────

class TestIdempotency:
    def test_ayni_istek_yeni_belge_acmaz(self, client_factory, env):
        client = client_factory()
        dosya_id = _yukle(client)["id"]
        kimlik = str(uuid.uuid4())
        r1 = _bagla(client, env, dosya_id=dosya_id, istek_kimligi=kimlik)
        assert r1.status_code == 200, r1.text
        kuyruk = len(env.enqueue_calls)
        r2 = _bagla(client, env, dosya_id=dosya_id, istek_kimligi=kimlik)
        assert r2.status_code == 200, r2.text
        assert r2.json() == {"document_id": r1.json()["document_id"], "reused": True}
        assert len(_belgeler(env)) == 1 and len(env.enqueue_calls) == kuyruk and len(env.convert_calls) == 1

    def test_cache_suresi_dolsa_da_replay(self, client_factory, env):
        """Replay sahiplik kontrolünden ÖNCE: dosya TTL ile gitmiş olsa da aynı belge döner."""
        client = client_factory()
        kimlik = str(uuid.uuid4())
        r1 = _bagla(client, env, istek_kimligi=kimlik)
        assert r1.status_code == 200
        r2 = _bagla(client, env, dosya_id="yok-artik", istek_kimligi=kimlik)
        assert r2.status_code == 200 and r2.json()["reused"] is True

    def test_farkli_kullanici_ayni_kimlik_409(self, client_factory, env):
        kimlik = str(uuid.uuid4())
        assert _bagla(client_factory(USER_A), env, istek_kimligi=kimlik).status_code == 200
        r = _bagla(client_factory(USER_B), env, istek_kimligi=kimlik)
        assert r.status_code == 409
        assert len(_belgeler(env)) == 1

    def test_suruyor_409(self, client_factory, env):
        kimlik = str(uuid.uuid4())
        db = env.sessions()
        db.add(env.models.ConfirmReceipt(process_id=f"pdf_araclari:{kimlik}", owner="a@hanyaloglu.com",
                                         status="in_progress"))
        db.commit()
        db.close()
        r = _bagla(client_factory(), env, istek_kimligi=kimlik)
        assert r.status_code == 409 and "TEKRAR GÖNDERMEYİN" in r.json()["detail"]
        assert _belgeler(env) == []

    def test_dogrulama_hatasi_kaydi_birakir(self, client_factory, env):
        kimlik = str(uuid.uuid4())
        client = client_factory()
        assert _bagla(client, env, istek_kimligi=kimlik, belge_turu_kodu="YOK").status_code == 422
        assert _fisler(env) == []
        assert _bagla(client, env, istek_kimligi=kimlik).status_code == 200

    def test_mesgul_503_kaydi_birakir(self, client_factory, env, monkeypatch):
        import pdf.pdf_converter as pdf_converter
        from pdf.format_converter import ConversionBusyError

        def _dolu(*a, **k):
            raise ConversionBusyError("PDF/A")

        monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", _dolu)
        client = client_factory()
        kimlik = str(uuid.uuid4())
        r = _bagla(client, env, istek_kimligi=kimlik)
        assert r.status_code == 503 and r.json()["detail"]["error_kod"] == "sistem_mesgul"
        assert _belgeler(env) == [] and _fisler(env) == [] and env.enqueue_calls == []

    def test_kilitli_kart_409_kaydi_birakir(self, client_factory, env, monkeypatch):
        from db_errors import KAYIT_MESGUL_DETAIL, KayitMesgulError
        from services import document_pipeline

        def _kilitli(*a, **k):
            raise KayitMesgulError()

        monkeypatch.setattr(document_pipeline, "save_case_document", _kilitli)
        for durum in ("KESIN", "TASLAK"):
            r = _bagla(client_factory(), env, durum=durum)
            assert r.status_code == 409, r.text
            assert r.json()["detail"] == KAYIT_MESGUL_DETAIL
        assert _belgeler(env) == [] and _fisler(env) == []


# ── 3. doğrulamalar ──────────────────────────────────────────────────────────

class TestDogrulama:
    def test_baskasinin_dosyasi_404(self, client_factory, env):
        dosya_id = _yukle(client_factory(USER_B))["id"]
        r = _bagla(client_factory(USER_A), env, dosya_id=dosya_id)
        assert r.status_code == 404 and _belgeler(env) == []

    @pytest.mark.parametrize("kart", ["kart_b", "silinmis", "yok"])
    def test_kart_404(self, client_factory, env, kart):
        case_id = 99999 if kart == "yok" else getattr(env.ids, kart)
        r = _bagla(client_factory(), env, case_id=case_id)
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Belirtilen dava bulunamadı."

    def test_paylasimli_kart_tenant_null_bulunur(self, client_factory, env):
        r = _bagla(client_factory(), env, case_id=env.ids.paylasimli, durum="TASLAK")
        assert r.status_code == 200, r.text
        assert env.enqueue_calls[0]["folder"] == "03_TASLAKLAR/2024-1234"  # yol ayracı klasör adında `-`

    @pytest.mark.parametrize("kod", ["YOK-TUR", "", "   "])
    def test_tur_422(self, client_factory, env, kod):
        r = _bagla(client_factory(), env, belge_turu_kodu=kod)
        assert r.status_code == 422, r.text
        if kod.strip():
            assert r.json()["detail"]["error_kod"] == "belge_turu"

    @pytest.mark.parametrize("ad", ["   ", ".pdf", "...", "___.pdf", "../../"])
    def test_ad_bos_422(self, client_factory, env, ad):
        r = _bagla(client_factory(), env, dosya_adi=ad)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["error_kod"] == "dosya_adi"
        assert _belgeler(env) == []

    def test_ad_yol_karakterleri_temizlenir(self, client_factory, env):
        r = _bagla(client_factory(), env, dosya_adi="../gizli/<dilekce>.pdf")
        assert r.status_code == 200, r.text
        ad = _belgeler(env)[0].stored_filename
        assert "/" not in ad and "<" not in ad and ad.endswith(".pdf")

    def test_taraf_baska_kartin_422(self, client_factory, env):
        r = _bagla(client_factory(), env, case_party_id=env.ids.taraf_b)
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "taraf"
        assert _belgeler(env) == []

    @pytest.mark.parametrize("alan,deger", [("yon", "ICERI"), ("durum", "ONAYLI"), ("durum", "TASLAK____"), ("ekstra", 1)])
    def test_yon_durum_ekstra_422(self, client_factory, env, alan, deger):
        assert _bagla(client_factory(), env, **{alan: deger}).status_code == 422

    def test_istek_kimligi_uuid_degilse_422(self, client_factory, env):
        assert _bagla(client_factory(), env, istek_kimligi="abc").status_code == 422


# ── 4. TASLAK yolu + G282 filtreleri ─────────────────────────────────────────

class TestKartaBaglaTaslak:
    def test_taslak_pdfa_yok_tek_kuyruk(self, client_factory, env):
        client = client_factory()
        dosya = _yukle(client)
        calisma_yolu = env.processing.DOWNLOAD_CACHE.get(dosya["id"])["path"]
        r = _bagla(client, env, dosya_id=dosya["id"], durum="taslak", yon="GIDEN", case_party_id=env.ids.taraf)
        assert r.status_code == 200, r.text
        [doc] = _belgeler(env)
        assert (doc.yon, doc.kaynak, doc.durum) == ("GIDEN", "PDF_ARACLARI", "TASLAK")
        assert doc.belge_turu_kodu == "DAVA-DLK______" and doc.belge_turu_adi == "Dava Dilekçesi"
        assert doc.esas_no == "2026/111" and doc.case_party_id == env.ids.taraf and doc.lawyer_id is None
        assert doc.kesinlesme_tarihi is None and doc.word_url is None
        assert env.convert_calls == []  # PDF/A YOK
        [kuyruk] = env.enqueue_calls  # TEK yükleme, ham arşiv YOK
        assert kuyruk == {"kind": "islenmis", "source": calisma_yolu, "filename": "dilekce_son.pdf",
                          "folder": f"03_TASLAKLAR/{OFIS_NO}", "document_id": doc.id}
        assert os.path.exists(calisma_yolu)
        assert _fisler(env)[0].status == "completed"

    def test_taslak_klasoru_ayardan(self, client_factory, env, monkeypatch):
        from config.settings import settings

        monkeypatch.setattr(settings, "sharepoint_folder_taslak_name", "99_TASLAK")
        assert _bagla(client_factory(), env, durum="TASLAK").status_code == 200
        assert env.enqueue_calls[0]["folder"] == f"99_TASLAK/{OFIS_NO}"

    def test_ayni_adli_ikinci_taslak_ezmez(self, client_factory, env):
        client = client_factory()
        assert _bagla(client, env, durum="TASLAK").status_code == 200
        assert _bagla(client, env, durum="TASLAK").status_code == 200
        adlar = [d.stored_filename for d in _belgeler(env)]
        assert adlar == ["dilekce_son.pdf", "dilekce_son_2.pdf"]

    def test_taslak_export_ve_bildirime_girmez(self, client_factory, env, monkeypatch):
        import services.notifications as bildirim
        from services import export_publisher, upload_queue

        monkeypatch.setenv("HUKDOK_EXPORT_TYPES", "DAVA-DLK")  # allowlist İÇİ tür bile olsa
        r = _bagla(client_factory(), env, durum="TASLAK")
        doc_id = r.json()["document_id"]
        _url_yaz(env, doc_id)  # yükleme başarılı, URL commit edildi
        assert export_publisher.enqueue_document(doc_id) is None
        db = env.sessions()
        assert db.query(env.models.ExportOutbox).count() == 0
        db.close()
        cagrilar: list[int] = []
        monkeypatch.setattr(bildirim, "notify_document_processed", lambda document_id: cagrilar.append(document_id))
        upload_queue._notify_document_processed(doc_id)
        assert cagrilar == []


# ── 5. Hukukbot allowlist + bildirim (KESIN, mevcut kural) ───────────────────

class TestHukukbotVeBildirim:
    def test_allowlist_ici_tur_outbox_acar(self, client_factory, env, monkeypatch):
        from services import export_publisher

        monkeypatch.setenv("HUKDOK_EXPORT_TYPES", "ARA-KRR")
        doc_id = _bagla(client_factory(), env, belge_turu_kodu="ARA-KRR").json()["document_id"]
        _url_yaz(env, doc_id)
        outbox_id = export_publisher.enqueue_document(doc_id)
        assert outbox_id is not None
        db = env.sessions()
        [satir] = db.query(env.models.ExportOutbox).all()
        assert satir.id == outbox_id and satir.document_id == doc_id and satir.status == "pending"
        db.close()

    def test_allowlist_disi_tur_outbox_acmaz(self, client_factory, env, monkeypatch):
        from services import export_publisher

        monkeypatch.setenv("HUKDOK_EXPORT_TYPES", "ARA-KRR")
        doc_id = _bagla(client_factory(), env, belge_turu_kodu="DAVA-DLK").json()["document_id"]
        _url_yaz(env, doc_id)
        assert export_publisher.enqueue_document(doc_id) is None
        db = env.sessions()
        assert db.query(env.models.ExportOutbox).count() == 0
        db.close()

    def test_url_yokken_outbox_acilmaz(self, client_factory, env, monkeypatch):
        """Satır yalnız URL commit'inden sonra (mevcut sıra) — yeni kayıt URL'siz girmez."""
        from services import export_publisher

        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        doc_id = _bagla(client_factory(), env).json()["document_id"]
        assert export_publisher.enqueue_document(doc_id) is None

    def test_kesin_belge_islendi_bildirimi_yolu(self, client_factory, env, monkeypatch):
        import services.notifications as bildirim
        from services import upload_queue

        doc_id = _bagla(client_factory(), env).json()["document_id"]
        _url_yaz(env, doc_id)
        cagrilar: list[int] = []
        monkeypatch.setattr(bildirim, "notify_document_processed", lambda document_id: cagrilar.append(document_id))
        upload_queue._notify_document_processed(doc_id)
        assert cagrilar == [doc_id]


# ── 6. pipeline birim: kilit → KayitMesgulError; imza ────────────────────────

class _KilitliOturum:
    def __init__(self, ic):
        self._ic = ic

    def __getattr__(self, ad):
        return getattr(self._ic, ad)

    def commit(self):
        raise OperationalError("UPDATE cases", {}, Exception("canceling statement due to lock timeout"))


class TestPipelineKilit:
    def test_save_case_document_kilit_kayit_mesgul(self, env, monkeypatch, caplog):
        from db_errors import KayitMesgulError
        from services import document_pipeline

        monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: _KilitliOturum(env.sessions()))
        monkeypatch.setattr(document_pipeline, "is_lock_timeout", lambda e: True)
        with pytest.raises(KayitMesgulError):
            document_pipeline.save_case_document(case_id=env.ids.kart, original_filename="a.pdf",
                                                 stored_filename="a.pdf")
        assert _belgeler(env) == []
        assert not [r for r in caplog.records if r.levelname == "ERROR"]  # geçici → WARNING

    def test_save_case_document_baska_hata_none(self, env, monkeypatch):
        from services import document_pipeline

        monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: _KilitliOturum(env.sessions()))
        monkeypatch.setattr(document_pipeline, "is_lock_timeout", lambda e: False)
        assert document_pipeline.save_case_document(case_id=env.ids.kart, original_filename="a.pdf",
                                                    stored_filename="a.pdf") is None

    def test_convert_pdfa_kilit_500e_dusmez(self, env, monkeypatch):
        from fastapi import BackgroundTasks

        from db_errors import KayitMesgulError
        from services import document_pipeline

        def _kilitli(*a, **k):
            raise KayitMesgulError()

        monkeypatch.setattr(document_pipeline, "save_case_document", _kilitli)
        kaynak = env.tmp / "k.pdf"
        kaynak.write_bytes(_pdf_bytes())
        with pytest.raises(KayitMesgulError):
            document_pipeline.convert_pdfa_and_queue_uploads(
                background_tasks=BackgroundTasks(), source_path=str(kaynak), ham_filename="h.pdf",
                ham_folder="01", islenmis_folder="02", new_filename="n.pdf", original_filename="o.pdf",
                belge_turu_kodu=None, muvekkiller=[], muvekkil_adi=None, ai_ozet=None, linked_case_id=env.ids.kart,
                case_party_id=None, lawyer_id=None, esas_no=None, is_test_mode=False, user=USER_A,
                current_user_name="x", results={}, timings={},
            )
        assert env.enqueue_calls == []

    def test_convert_imza_butce_varsayilani_none(self):
        """/confirm ve intake çağrıları değişmedi: yeni parametre None → settings.confirm_conversion_budget_seconds."""
        from services import document_pipeline

        p = inspect.signature(document_pipeline.convert_pdfa_and_queue_uploads).parameters
        assert p["conversion_budget_seconds"].default is None

    def test_convert_varsayilan_butce_confirm(self, env, monkeypatch):
        from fastapi import BackgroundTasks

        from config.settings import settings
        from services import document_pipeline

        kaynak = env.tmp / "k.pdf"
        kaynak.write_bytes(_pdf_bytes())
        _, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
            background_tasks=BackgroundTasks(), source_path=str(kaynak), ham_filename="h.pdf",
            ham_folder="01", islenmis_folder="02", new_filename="n.pdf", original_filename="o.pdf",
            belge_turu_kodu=None, muvekkiller=[], muvekkil_adi=None, ai_ozet=None, linked_case_id=env.ids.kart,
            case_party_id=None, lawyer_id=None, esas_no=None, is_test_mode=False, user=USER_A,
            current_user_name="x", results={}, timings={},
        )
        assert doc_id and env.convert_calls[0]["budget"] == settings.confirm_conversion_budget_seconds
        [doc] = _belgeler(env)
        assert (doc.yon, doc.kaynak, doc.durum) == ("GELEN", "BELGE_HATTI", "KESIN")


# ── 7. karttan-al ────────────────────────────────────────────────────────────

def _arsiv_belgesi(env, case_id=None, **ek):
    db = env.sessions()
    try:
        alanlar = dict(case_id=case_id if case_id is not None else env.ids.kart, original_filename="dilekce.pdf",
                       stored_filename="2026-10-07_dilekce.pdf", link_mode="LINKED", sharepoint_url="https://sp/d.pdf",
                       uploaded_by_email="a@hanyaloglu.com")
        alanlar.update(ek)
        d = env.models.CaseDocument(**alanlar)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


@pytest.fixture()
def sahte_sharepoint(env, monkeypatch):
    cagrilar: list[tuple[str, str]] = []
    icerik = {"bytes": _pdf_bytes(("ARSIV1", "ARSIV2"))}

    def _indir(klasor, dosya_adi):
        cagrilar.append((klasor, dosya_adi))
        return icerik["bytes"], "application/pdf"

    monkeypatch.setattr(env.route, "_sharepoint_indir", _indir)
    return SimpleNamespace(cagrilar=cagrilar, icerik=icerik)


class TestKarttanAl:
    def test_kesin_belge_islenmis_arsivden(self, client_factory, env, sahte_sharepoint):
        client = client_factory()
        doc_id = _arsiv_belgesi(env)
        r = client.post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) == {"id", "ad", "sayfa", "boyut", "sayfalar"}
        assert d["ad"] == "dilekce.pdf" and d["sayfa"] == 2 and d["boyut"] > 0
        assert sahte_sharepoint.cagrilar == [("02_YEDEK_ARSIV", "2026-10-07_dilekce.pdf")]
        kayit = env.processing.DOWNLOAD_CACHE.get(d["id"])
        assert kayit["kaynak"] == "pdf_araclari" and kayit["owner"] == "a@hanyaloglu.com"
        assert Path(kayit["path"]).name == f"{d['id']}.pdf"
        # Zincir: indir + önizleme çalışır
        r = client.get(f"/api/download/{d['id']}")
        assert r.status_code == 200 and 'filename="dilekce.pdf"' in r.headers["content-disposition"]
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert [p.get_text().strip() for p in doc] == ["ARSIV1", "ARSIV2"]
        assert client.get(f"/api/pdf-araclari/onizleme/{d['id']}/2?genislik=100").status_code == 200

    def test_taslak_belge_taslak_klasorunden(self, client_factory, env, sahte_sharepoint):
        doc_id = _arsiv_belgesi(env, durum="TASLAK", kaynak="PDF_ARACLARI", stored_filename="taslak.pdf")
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 200, r.text
        assert sahte_sharepoint.cagrilar == [(f"03_TASLAKLAR/{OFIS_NO}", "taslak.pdf")]

    def test_karttan_al_sonra_karta_bagla_zinciri(self, client_factory, env, sahte_sharepoint):
        """Duruşma dosyası birleştirme senaryosu: arşivden al → yüklenenle birleştir → yeni belge olarak bağla."""
        client = client_factory()
        doc_id = _arsiv_belgesi(env)
        arsiv = client.post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id}).json()
        yeni = _yukle(client, _pdf_bytes(("EK",)), ad="ek.pdf")
        r = client.post("/api/pdf-araclari/islem", json={"islem": "birlestir", "girdiler": [arsiv["id"], yeni["id"]],
                                                         "parametreler": {}, "cikti_adi": "durusma_dosyasi.pdf"})
        assert r.status_code == 200, r.text
        [birlesik] = r.json()["ciktilar"]
        assert birlesik["sayfa"] == 3
        r = _bagla(client, env, dosya_id=birlesik["id"], dosya_adi="durusma_dosyasi.pdf")
        assert r.status_code == 200, r.text
        assert [d.stored_filename for d in _belgeler(env)] == ["2026-10-07_dilekce.pdf", "durusma_dosyasi.pdf"]

    @pytest.mark.parametrize("senaryo", ["url_bos", "baska_tenant", "silinmis", "yok", "ad_bos"])
    def test_404(self, client_factory, env, sahte_sharepoint, senaryo):
        if senaryo == "url_bos":
            doc_id = _arsiv_belgesi(env, sharepoint_url=None)
        elif senaryo == "baska_tenant":
            doc_id = _arsiv_belgesi(env, case_id=env.ids.kart_b)
        elif senaryo == "silinmis":
            doc_id = _arsiv_belgesi(env, deleted_at=datetime.now(timezone.utc))
        elif senaryo == "ad_bos":
            doc_id = _arsiv_belgesi(env, stored_filename="")
        else:
            doc_id = 424242
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 404, r.text
        assert sahte_sharepoint.cagrilar == []

    def test_sharepoint_hatasi_502(self, client_factory, env, monkeypatch, caplog):
        def _patla(klasor, ad):
            raise RuntimeError("Graph 503")

        monkeypatch.setattr(env.route, "_sharepoint_indir", _patla)
        doc_id = _arsiv_belgesi(env)
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 502
        assert r.json()["detail"]["error_kod"] == "sharepoint"
        assert len([x for x in caplog.records if x.levelname == "ERROR"]) == 1  # nihai TEK ERROR

    def test_bos_icerik_502(self, client_factory, env, sahte_sharepoint):
        sahte_sharepoint.icerik["bytes"] = b""
        doc_id = _arsiv_belgesi(env)
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 502 and r.json()["detail"]["error_kod"] == "sharepoint"

    def test_boyut_413(self, client_factory, env, sahte_sharepoint, monkeypatch):
        monkeypatch.setattr(env.route, "MAX_UPLOAD_BYTES", 100)
        doc_id = _arsiv_belgesi(env)
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 413 and r.json()["detail"]["error_kod"] == "boyut"

    def test_office_uzantisi_korunur_donusum_hatasi_422(self, client_factory, env, sahte_sharepoint, monkeypatch):
        """Arşivde Office/UDF de olabilir: dönüştürücüye kendi uzantısıyla gider; başarısızlık 422."""
        gorulen: list[str] = []

        def _patla(kaynak, cikti_dizini, deadline=None):
            gorulen.append(Path(kaynak).suffix)
            raise RuntimeError("LibreOffice yok")

        monkeypatch.setattr(env.route.cekirdek, "pdf_ye_cevir", _patla)
        sahte_sharepoint.icerik["bytes"] = b"PK\x03\x04 sahte docx"
        doc_id = _arsiv_belgesi(env, stored_filename="dilekce.docx", original_filename="dilekce.docx")
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "donusum_basarisiz"
        assert gorulen == [".docx"]

    def test_mesgul_503(self, client_factory, env, sahte_sharepoint, monkeypatch):
        from pdf.format_converter import ConversionBusyError

        def _dolu(*a, **k):
            raise ConversionBusyError("PDF aracı")

        monkeypatch.setattr(env.route, "acquire_conversion_slot", _dolu)
        doc_id = _arsiv_belgesi(env)
        r = client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id})
        assert r.status_code == 503 and r.json()["detail"]["error_kod"] == "sistem_mesgul"

    def test_gecici_dizin_silinir(self, client_factory, env, sahte_sharepoint, monkeypatch):
        import tempfile

        olusanlar = []
        orijinal = tempfile.mkdtemp

        def _izle(*a, **k):
            d = orijinal(*a, **k)
            olusanlar.append(d)
            return d

        monkeypatch.setattr(env.route.tempfile, "mkdtemp", _izle)
        doc_id = _arsiv_belgesi(env)
        assert client_factory().post("/api/pdf-araclari/karttan-al", json={"document_id": doc_id}).status_code == 200
        assert olusanlar and not os.path.exists(olusanlar[0])


# ── 8. bekçi ─────────────────────────────────────────────────────────────────

NGINX = Path(__file__).resolve().parent.parent.parent / "nginx.conf"


def test_yeni_uclar_api_altinda():
    from routes import pdf_araclari as route_mod

    yollar = {str(r.path) for r in route_mod.router.routes}
    assert "/api/pdf-araclari/karta-bagla" in yollar and "/api/pdf-araclari/karttan-al" in yollar
    assert all(y.startswith("/api/") for y in yollar)


@pytest.mark.skipif(not NGINX.exists(), reason="repo kökü görünmüyor (konteynerde yalnız backend/)")
def test_nginx_dokunulmadi():
    assert "pdf-araclari" not in NGINX.read_text(encoding="utf-8")
