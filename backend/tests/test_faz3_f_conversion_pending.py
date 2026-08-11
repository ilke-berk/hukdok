"""Faz 3-F testleri: conversion_pending katmanı (plan 3.8 Katman 2).

Kapsam:
- document_pipeline pending katmanı: dönüşüm nihai başarısızlığında 500 YOK —
  belge conversion_status='pending' + spool kopyasıyla açılır, orijinal KENDİ
  uzantısıyla iki arşive kuyruklanır (".pdf adıyla sızma" koruması), results
  uyarı alanları dolar; katman kurulamazsa (spool/DB) eski 500 taban çizgisi
- /confirm route: pending akışında e-posta eki + indirme adı gerçek uzantıyla
- conversion_retry gece job'ı: başarı (PDF üret → yükle → statü düş → hukukbot
  ANCAK O ZAMAN), deneme WARNING / tek nihai ERROR sözleşmesi, spool kaybı,
  upload-hatasında sayaç iadesi, silinmiş belge atlanır, spool yardımcıları
- upload_queue 'superseded': gece job'ı bekleyen islenmis-orijinal satırını
  etkisizleştirir; upload sırasında yakalanırsa sonuç belgeye işlenmez;
  janitor superseded spool'u bekletmeden temizler
- hukukbot filtreleri: enqueue_document conversion_status'lu belgeyi almaz
  (_doc_passes_filters tarafı test_export_filters.py'de)
- bekçiler: migration op 27 + model kolonları (scheduler needle bekçisi
  test_faz3_e_hardening.py'de)

DB'ye/ağa inilmez (conftest sözleşmesi): SessionLocal fake'lenir; fake filter
no-op'tur — kod Python tarafında durum guard'larını yeniden kontrol eder.
"""
import io
import logging
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


# ─── ortak fake'ler (test_faz3_upload_outbox kalıbı) ─────────────────────────

class _FakeDoc:
    """models.CaseDocument gibi davranan düz nesne."""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.conversion_status = kw.get("conversion_status", "pending")
        self.conversion_attempts = kw.get("conversion_attempts", 0)
        self.conversion_spool_path = kw.get("conversion_spool_path")
        self.stored_filename = kw.get("stored_filename", "2026-08-11_TEST_BELGE.udf")
        self.sharepoint_url = kw.get("sharepoint_url")
        self.upload_status = kw.get("upload_status", "pending")
        self.upload_attempts = kw.get("upload_attempts", 0)
        self.deleted_at = kw.get("deleted_at")
        self.uploaded_at = kw.get("uploaded_at")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _FakeQuery(self.rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _ModelSession:
    """Model sınıfına göre farklı sonuç listeleri dönen fake (export testleri)."""

    def __init__(self, results_by_model):
        self.results_by_model = results_by_model

    def query(self, model):
        return _FakeQuery(self.results_by_model.get(model, []))

    def add(self, row):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def refresh(self, row):
        pass


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


@pytest.fixture
def retry_logs():
    handler = _ListHandler()
    target = logging.getLogger("services.conversion_retry")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


@pytest.fixture
def tech_logs():
    """TechnicalLogger standart logging'e 'TechnicalLogger' adıyla delege eder."""
    handler = _ListHandler()
    target = logging.getLogger("TechnicalLogger")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _errors(records):
    return [r for r in records if r.levelno >= logging.ERROR]


def _use_conv_spool(monkeypatch, tmp_path):
    spool = tmp_path / "conv_spool"
    monkeypatch.setenv("CONVERSION_SPOOL_DIR", str(spool))
    return spool


# ═════════════════════════════════════════════════════════════════════════════
# 1) spool yardımcıları
# ═════════════════════════════════════════════════════════════════════════════


def test_spool_original_copies_with_own_extension(monkeypatch, tmp_path):
    from services import conversion_retry

    spool = _use_conv_spool(monkeypatch, tmp_path)
    src = tmp_path / "orijinal.udf"
    src.write_bytes(b"PK\x03\x04 udf icerik")

    out = conversion_retry.spool_original(str(src), ".udf")
    assert out is not None
    out_path = Path(out)
    assert out_path.parent == spool and out_path.suffix == ".udf"
    assert out_path.read_bytes() == b"PK\x03\x04 udf icerik"
    assert src.exists()  # kaynak dosyaya dokunulmaz


def test_spool_original_missing_source_returns_none(monkeypatch, tmp_path):
    from services import conversion_retry

    _use_conv_spool(monkeypatch, tmp_path)
    assert conversion_retry.spool_original(str(tmp_path / "yok.udf"), ".udf") is None


# ═════════════════════════════════════════════════════════════════════════════
# 2) document_pipeline pending katmanı
# ═════════════════════════════════════════════════════════════════════════════


def _run_convert_with_failure(monkeypatch, tmp_path, conv_exc=None, new_filename="yeni.pdf"):
    """Dönüşümü patlatıp convert_pdfa_and_queue_uploads'u çağırır."""
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    src = tmp_path / "analiz.pdf"
    src.write_bytes(b"%PDF-1.4 analiz")
    orijinal = tmp_path / "orijinal.udf"
    orijinal.write_bytes(b"PK\x03\x04 orijinal")

    def boom(path):
        raise conv_exc or ValueError(".udf dosyası PDF'e dönüştürülemedi (tablo hatası)")

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", boom)

    saved = []

    def fake_save(**kw):
        saved.append(kw)
        return 7

    monkeypatch.setattr(document_pipeline, "save_case_document", fake_save)

    enqueued = []

    def fake_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        enqueued.append((kind, source_path, target_filename, target_folder, document_id))
        return len(enqueued)

    monkeypatch.setattr(upload_queue, "enqueue_upload", fake_enqueue)

    bg = _FakeBackgroundTasks()
    results, timings = {}, {}
    out = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=bg,
        source_path=str(src),
        ham_filename="2026-08-11_orijinal.udf",
        ham_folder="01_HAM_ARSIV",
        islenmis_folder="02_YEDEK_ARSIV",
        new_filename=new_filename,
        original_filename="orijinal.udf",
        belge_turu_kodu=None,
        muvekkiller=[],
        muvekkil_adi=None,
        ai_ozet=None,
        linked_case_id=None,
        case_party_id=None,
        avukat_kodu=None,
        esas_no=None,
        is_test_mode=False,
        user={},
        current_user_name="test",
        results=results,
        timings=timings,
        ham_source_path=str(orijinal),
    )
    return out, saved, enqueued, bg, results, str(orijinal)


def test_pending_layer_no_500_creates_doc_and_queues_original(monkeypatch, tmp_path, tech_logs):
    spool = _use_conv_spool(monkeypatch, tmp_path)
    (pdfa_out, doc_id), saved, enqueued, bg, results, orijinal = _run_convert_with_failure(
        monkeypatch, tmp_path
    )

    # 500 yok; PDF/A yok ama belge var
    assert (pdfa_out, doc_id) == (None, 7)
    assert results["case_document_id"] == 7
    assert results["conversion_pending"] is True
    assert "gece" in results["conversion_warning"]
    assert "tablo hatası" in results["conversion_warning"]  # gerçek neden gizlenmez

    # Belge kaydı: pending statü + spool kopyası + KENDİ uzantısıyla arşiv adı
    kw = saved[0]
    assert kw["conversion_status"] == "pending"
    assert kw["stored_filename"] == "yeni.udf"
    spool_files = list(spool.glob("*"))
    assert len(spool_files) == 1 and spool_files[0].suffix == ".udf"
    assert kw["conversion_spool_path"] == str(spool_files[0])
    assert spool_files[0].read_bytes() == b"PK\x03\x04 orijinal"

    # İki arşive de ORİJİNAL kuyruklanır (islenmis'e .udf adıyla — maske yok)
    assert [(c[0], c[1], c[2], c[4]) for c in enqueued] == [
        ("ham", orijinal, "2026-08-11_orijinal.udf", 7),
        ("islenmis", orijinal, "yeni.udf", 7),
    ]
    assert bg.tasks == []  # outbox başarılı → fallback kuyruklanmaz

    # Log sözleşmesi: bu belge için nihai DEĞİL → ERROR yok, WARNING var
    assert _errors(tech_logs) == []
    assert any("conversion_pending katmanı devrede" in r.getMessage() for r in tech_logs)


def test_pending_layer_missing_output_also_covered(monkeypatch, tmp_path):
    """convert exception atmayıp var olmayan yol döndürse de katman devrede."""
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    _use_conv_spool(monkeypatch, tmp_path)
    src = tmp_path / "kaynak.udf"
    src.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", lambda p: str(tmp_path / "yok.pdf"))
    monkeypatch.setattr(document_pipeline, "save_case_document", lambda **kw: 9)
    monkeypatch.setattr(upload_queue, "enqueue_upload", lambda *a, **k: 1)

    results, timings = {}, {}
    pdfa_out, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=_FakeBackgroundTasks(),
        source_path=str(src),
        ham_filename="h.udf", ham_folder="H", islenmis_folder="I",
        new_filename="yeni.pdf", original_filename="kaynak.udf",
        belge_turu_kodu=None, muvekkiller=[], muvekkil_adi=None, ai_ozet=None,
        linked_case_id=None, case_party_id=None, avukat_kodu=None, esas_no=None,
        is_test_mode=False, user={}, current_user_name="t",
        results=results, timings=timings, ham_source_path=None,
    )
    assert (pdfa_out, doc_id) == (None, 9)
    assert results["conversion_pending"] is True
    assert "dosya oluşturulamadı" in results["conversion_warning"]


def test_pending_layer_spool_failure_falls_back_to_500(monkeypatch, tmp_path, tech_logs):
    from services import conversion_retry

    monkeypatch.setattr(conversion_retry, "spool_original", lambda *a, **k: None)
    with pytest.raises(HTTPException) as exc:
        _run_convert_with_failure(monkeypatch, tmp_path)
    assert exc.value.status_code == 500
    assert "tablo hatası" in exc.value.detail  # gerçek neden korunur (Katman 1)
    assert len(_errors(tech_logs)) == 1  # eski davranışın tek ERROR'u


def test_pending_layer_doc_save_failure_falls_back_to_500_and_cleans_spool(monkeypatch, tmp_path, tech_logs):
    from services import document_pipeline
    import pdf.pdf_converter as pdf_converter

    spool = _use_conv_spool(monkeypatch, tmp_path)
    src = tmp_path / "analiz.pdf"
    src.write_bytes(b"%PDF")
    orijinal = tmp_path / "orijinal.udf"
    orijinal.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b",
                        lambda p: (_ for _ in ()).throw(ValueError("dönüşüm hatası")))
    monkeypatch.setattr(document_pipeline, "save_case_document", lambda **kw: None)

    with pytest.raises(HTTPException) as exc:
        document_pipeline.convert_pdfa_and_queue_uploads(
            background_tasks=_FakeBackgroundTasks(),
            source_path=str(src), ham_filename="h.udf", ham_folder="H",
            islenmis_folder="I", new_filename="yeni.pdf", original_filename="orijinal.udf",
            belge_turu_kodu=None, muvekkiller=[], muvekkil_adi=None, ai_ozet=None,
            linked_case_id=None, case_party_id=None, avukat_kodu=None, esas_no=None,
            is_test_mode=False, user={}, current_user_name="t",
            results={}, timings={}, ham_source_path=str(orijinal),
        )
    assert exc.value.status_code == 500
    assert list(spool.glob("*")) == []  # yarım spool kopyası temizlendi
    assert len(_errors(tech_logs)) == 1


def test_pending_filename_keeps_pdf_when_original_is_pdf(monkeypatch, tmp_path):
    """Orijinal zaten .pdf ise (cache-miss PDF senaryosu) ad .pdf kalır — maske yok."""
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    _use_conv_spool(monkeypatch, tmp_path)
    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b",
                        lambda p: (_ for _ in ()).throw(FileNotFoundError("gs yok")))
    saved = []
    monkeypatch.setattr(document_pipeline, "save_case_document",
                        lambda **kw: saved.append(kw) or 5)
    monkeypatch.setattr(upload_queue, "enqueue_upload", lambda *a, **k: 1)

    results = {}
    document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=_FakeBackgroundTasks(),
        source_path=str(src), ham_filename="h.pdf", ham_folder="H",
        islenmis_folder="I", new_filename="yeni.pdf", original_filename="kaynak.pdf",
        belge_turu_kodu=None, muvekkiller=[], muvekkil_adi=None, ai_ozet=None,
        linked_case_id=None, case_party_id=None, avukat_kodu=None, esas_no=None,
        is_test_mode=False, user={}, current_user_name="t",
        results=results, timings={}, ham_source_path=None,
    )
    assert saved[0]["stored_filename"] == "yeni.pdf"
    assert results["archived_filename"] == "yeni.pdf"


# ═════════════════════════════════════════════════════════════════════════════
# 3) /confirm route — pending akışında ek/indirme adı gerçek uzantıyla
# ═════════════════════════════════════════════════════════════════════════════


def _valid_udf_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", "<udf>bozuk ama zip-gecerli</udf>")
    return buf.getvalue()


def test_confirm_route_pending_uses_real_extension_for_email_and_download(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import processing
    from services import document_pipeline

    def fake_convert(**kwargs):
        kwargs["results"].update({
            "case_document_id": 903,
            "conversion_pending": True,
            "archived_filename": "2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.udf",
            "conversion_warning": "PDF dönüşümü gece tamamlanacak",
        })
        return (None, 903)

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", fake_convert)

    email_calls = []

    async def fake_send_email(**kwargs):
        email_calls.append(kwargs)
        kwargs["results"]["email"] = "Gönderildi"

    monkeypatch.setattr(document_pipeline, "send_notification_email", fake_send_email)
    monkeypatch.setattr(document_pipeline, "schedule_cleanup", lambda *a, **k: None)

    downloads = []
    monkeypatch.setattr(
        processing.DOWNLOAD_CACHE, "set",
        lambda key, value: downloads.append((key, value)),
    )

    app = FastAPI()
    app.include_router(processing.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test", "preferred_username": "test@example.com", "tid": "t1",
    }
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/confirm",
        data={
            "new_filename": "2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf",
            "send_email": "true",
            "is_test_mode": "true",
        },
        files={"file": ("orijinal.udf", _valid_udf_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"]["conversion_pending"] is True

    # E-posta eki ve indirme kaydı .udf adıyla — .pdf maskesi yok
    assert email_calls[0]["new_filename"].endswith(".udf")
    assert len(downloads) == 1
    assert downloads[0][1]["filename"].endswith(".udf")


# ═════════════════════════════════════════════════════════════════════════════
# 4) conversion_retry gece job'ı
# ═════════════════════════════════════════════════════════════════════════════


def _patch_sessions(monkeypatch, rows):
    from services import conversion_retry

    sessions = []

    def factory():
        s = _FakeSession(rows)
        sessions.append(s)
        return s

    monkeypatch.setattr(conversion_retry, "SessionLocal", factory)
    return sessions


def _night_env(monkeypatch, tmp_path, doc, convert=None, upload=None):
    """Gece job'ı için ortak monkeypatch seti kurar."""
    from services import upload_queue
    import pdf.pdf_converter as pdf_converter
    import sharepoint.sharepoint_uploader_graph as spg
    from services import export_publisher

    _use_conv_spool(monkeypatch, tmp_path)
    _patch_sessions(monkeypatch, [doc])

    pdfa = tmp_path / "gece_pdfa.pdf"

    def default_convert(path):
        pdfa.write_bytes(b"%PDF-1.4 gece")
        return str(pdfa)

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", convert or default_convert)

    uploads = []

    def default_upload(path, name, folder, use_date_subfolder=False):
        uploads.append((path, name, folder))
        return {"webUrl": "https://sp/yeni.pdf"}

    monkeypatch.setattr(spg, "upload_file_to_sharepoint", upload or default_upload)

    superseded = []
    monkeypatch.setattr(
        upload_queue, "supersede_pending_uploads",
        lambda doc_id, kind: superseded.append((doc_id, kind)) or 1,
    )

    notified = []
    monkeypatch.setattr(
        export_publisher, "notify_hukukbot",
        lambda doc_id: notified.append((doc_id, doc.conversion_status)),
    )
    return SimpleNamespace(uploads=uploads, superseded=superseded, notified=notified, pdfa=pdfa)


def _pending_doc(tmp_path, **kw):
    spool_file = tmp_path / kw.pop("spool_name", "spool_orijinal.udf")
    spool_file.write_bytes(b"PK\x03\x04 spool")
    return _FakeDoc(conversion_spool_path=str(spool_file), **kw)


def test_night_success_completes_flow_and_opens_hukukbot_last(monkeypatch, tmp_path, retry_logs, tech_logs):
    from services import conversion_retry

    doc = _pending_doc(tmp_path, id=7, stored_filename="2026-08-11_X_ARA-KRR.udf")
    env = _night_env(monkeypatch, tmp_path, doc)

    counts = conversion_retry.retry_pending_conversions()

    assert counts["completed"] == 1
    # Belge tamamlandı: .pdf adı + URL + statüler
    assert doc.stored_filename == "2026-08-11_X_ARA-KRR.pdf"
    assert doc.sharepoint_url == "https://sp/yeni.pdf"
    assert doc.upload_status == "uploaded"
    assert doc.conversion_status is None
    assert doc.conversion_spool_path is None
    assert doc.conversion_attempts == 1
    # Yükleme .pdf adıyla yapıldı
    assert env.uploads == [(str(env.pdfa), "2026-08-11_X_ARA-KRR.pdf", "02_YEDEK_ARSIV")]
    # Yarışan orijinal-yükleme satırları etkisizleştirildi
    assert env.superseded == [(7, "islenmis")]
    # Hukukbot ANCAK statü düştükten SONRA açıldı
    assert env.notified == [(7, None)]
    # Spool ve pdfa temp temizlendi
    assert not (tmp_path / "spool_orijinal.udf").exists()
    assert not env.pdfa.exists()
    # Log sözleşmesi: ERROR yok
    assert _errors(retry_logs) == [] and _errors(tech_logs) == []


def test_night_conversion_failure_warns_and_stays_pending(monkeypatch, tmp_path, retry_logs, tech_logs):
    from services import conversion_retry

    doc = _pending_doc(tmp_path, id=3)
    env = _night_env(
        monkeypatch, tmp_path, doc,
        convert=lambda p: (_ for _ in ()).throw(ValueError("hala bozuk")),
    )

    counts = conversion_retry.retry_pending_conversions()

    assert counts["retry"] == 1
    assert doc.conversion_status == "pending"
    assert doc.conversion_attempts == 1
    assert env.uploads == [] and env.notified == []
    assert _errors(retry_logs) == [] and _errors(tech_logs) == []
    assert any("yarın yeniden" in r.getMessage() for r in retry_logs)


def test_night_final_failure_single_error(monkeypatch, tmp_path, retry_logs, tech_logs):
    from services import conversion_retry

    doc = _pending_doc(
        tmp_path, id=4, conversion_attempts=conversion_retry.MAX_CONVERSION_ATTEMPTS - 1
    )
    env = _night_env(
        monkeypatch, tmp_path, doc,
        convert=lambda p: (_ for _ in ()).throw(RuntimeError("deterministik bozuk")),
    )

    counts = conversion_retry.retry_pending_conversions()

    assert counts["failed_final"] == 1
    assert doc.conversion_status == "failed"
    assert doc.conversion_attempts == conversion_retry.MAX_CONVERSION_ATTEMPTS
    # TEK nihai ERROR (TechnicalLogger üzerinden); modül logger'ında ERROR yok
    all_errors = _errors(retry_logs) + _errors(tech_logs)
    assert len(all_errors) == 1
    assert "NİHAİ başarısız" in all_errors[0].getMessage()
    assert env.notified == []
    # Spool dosyası elle kurtarma için DURUYOR
    assert Path(doc.conversion_spool_path).exists()


def test_night_missing_spool_terminal_error(monkeypatch, tmp_path, retry_logs, tech_logs):
    from services import conversion_retry

    doc = _FakeDoc(id=5, conversion_spool_path=str(tmp_path / "yok.udf"))
    _night_env(monkeypatch, tmp_path, doc)

    counts = conversion_retry.retry_pending_conversions()

    assert counts["failed_final"] == 1
    assert doc.conversion_status == "failed"
    assert len(_errors(retry_logs) + _errors(tech_logs)) == 1


def test_night_upload_failure_refunds_attempt(monkeypatch, tmp_path, retry_logs, tech_logs):
    from services import conversion_retry

    doc = _pending_doc(tmp_path, id=6, conversion_attempts=2)
    env = _night_env(
        monkeypatch, tmp_path, doc,
        upload=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sharepoint kapali")),
    )

    counts = conversion_retry.retry_pending_conversions()

    assert counts["upload_retry"] == 1
    assert doc.conversion_status == "pending"
    # Dönüşüm başarılıydı → deneme tüketilmedi (SharePoint kesintisi MAX'ı yemesin)
    assert doc.conversion_attempts == 2
    assert env.notified == []
    assert not env.pdfa.exists()  # pdfa temp temizlendi
    assert Path(doc.conversion_spool_path).exists()  # spool duruyor
    assert _errors(retry_logs) == [] and _errors(tech_logs) == []


def test_night_upload_without_weburl_completes_but_no_hook(monkeypatch, tmp_path):
    from services import conversion_retry

    doc = _pending_doc(tmp_path, id=8)
    env = _night_env(monkeypatch, tmp_path, doc, upload=lambda *a, **k: {})

    counts = conversion_retry.retry_pending_conversions()

    assert counts["completed"] == 1
    assert doc.conversion_status is None
    assert doc.stored_filename.endswith(".pdf")
    assert doc.upload_status == "failed"  # URL commit edilmedi → dürüst gösterge
    assert doc.sharepoint_url is None
    assert env.notified == []  # hook YALNIZ URL commit'inde (BULGULAR #1)


def test_night_skips_deleted_document(monkeypatch, tmp_path):
    from services import conversion_retry

    doc = _pending_doc(tmp_path, id=9, deleted_at=datetime.now(timezone.utc))
    _night_env(monkeypatch, tmp_path, doc)

    assert conversion_retry._process_one(9, "02_YEDEK_ARSIV") == "skipped"
    assert doc.conversion_attempts == 0 and doc.conversion_status == "pending"


def test_night_scan_db_error_is_warning_not_crash(monkeypatch, retry_logs):
    from services import conversion_retry

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(conversion_retry, "SessionLocal", boom)
    counts = conversion_retry.retry_pending_conversions()
    assert counts["completed"] == 0
    assert _errors(retry_logs) == []
    assert any("taraması başarısız" in r.getMessage() for r in retry_logs)


def test_janitor_purges_failed_deleted_and_orphan_spools(monkeypatch, tmp_path):
    from services import conversion_retry

    spool = _use_conv_spool(monkeypatch, tmp_path)
    spool.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    old_failed = spool / "failed.udf"
    old_failed.write_bytes(b"x")
    fresh_failed = spool / "fresh_failed.udf"
    fresh_failed.write_bytes(b"x")
    deleted_spool = spool / "deleted.udf"
    deleted_spool.write_bytes(b"x")
    orphan = spool / "orphan.udf"
    orphan.write_bytes(b"x")
    pending_spool = spool / "pending.udf"
    pending_spool.write_bytes(b"x")

    docs = [
        _FakeDoc(id=1, conversion_status="failed", conversion_spool_path=str(old_failed),
                 uploaded_at=now - timedelta(days=40)),
        _FakeDoc(id=2, conversion_status="failed", conversion_spool_path=str(fresh_failed),
                 uploaded_at=now - timedelta(days=3)),
        _FakeDoc(id=3, conversion_status="pending", conversion_spool_path=str(deleted_spool),
                 deleted_at=now - timedelta(days=31)),
        _FakeDoc(id=4, conversion_status="pending", conversion_spool_path=str(pending_spool),
                 uploaded_at=now - timedelta(days=100)),
    ]
    _patch_sessions(monkeypatch, docs)

    # Orphan yaş eşiğini geçmiş göster
    import os
    old = (now - timedelta(days=3)).timestamp()
    os.utime(orphan, (old, old))

    conversion_retry._janitor(now)

    assert not old_failed.exists() and docs[0].conversion_spool_path is None
    assert fresh_failed.exists() and docs[1].conversion_spool_path is not None
    assert not deleted_spool.exists() and docs[2].conversion_spool_path is None
    assert not orphan.exists()
    assert pending_spool.exists()  # canlı pending spool'a dokunulmaz


# ═════════════════════════════════════════════════════════════════════════════
# 5) upload_queue 'superseded'
# ═════════════════════════════════════════════════════════════════════════════


class _FakeOutboxRow:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.document_id = kw.get("document_id", 7)
        self.kind = kw.get("kind", "islenmis")
        self.spool_path = kw.get("spool_path")
        self.target_filename = kw.get("target_filename", "belge.udf")
        self.target_folder = kw.get("target_folder", "02_YEDEK_ARSIV")
        self.status = kw.get("status", "pending")
        self.attempts = kw.get("attempts", 0)
        self.next_attempt_at = kw.get("next_attempt_at")
        self.last_error = kw.get("last_error")
        self.created_at = kw.get("created_at")
        self.done_at = kw.get("done_at")


def test_supersede_marks_only_matching_pending_rows(monkeypatch):
    from services import upload_queue

    rows = [
        _FakeOutboxRow(id=1, document_id=7, kind="islenmis", status="pending"),
        _FakeOutboxRow(id=2, document_id=7, kind="ham", status="pending"),
        _FakeOutboxRow(id=3, document_id=7, kind="islenmis", status="uploaded"),
        _FakeOutboxRow(id=4, document_id=8, kind="islenmis", status="pending"),
    ]
    session = _FakeSession(rows)
    monkeypatch.setattr(upload_queue, "SessionLocal", lambda: session)

    count = upload_queue.supersede_pending_uploads(7, kind="islenmis")

    assert count == 1
    assert rows[0].status == "superseded" and rows[0].done_at is not None
    assert rows[1].status == "pending"    # ham satırına dokunulmaz
    assert rows[2].status == "uploaded"
    assert rows[3].status == "pending"    # başka belgenin satırı
    assert session.commits == 1


def test_attempt_upload_superseded_midflight_skips_doc_update_and_hook(monkeypatch, tmp_path):
    from services import upload_queue, document_pipeline, export_publisher
    import sharepoint.sharepoint_uploader_graph as spg

    spool_file = tmp_path / "spool.udf"
    spool_file.write_bytes(b"PK\x03\x04")
    row = _FakeOutboxRow(id=11, document_id=7, spool_path=str(spool_file), status="pending")
    session_rows = [row]

    def factory():
        return _FakeSession(session_rows)

    monkeypatch.setattr(upload_queue, "SessionLocal", factory)

    recorded = []
    monkeypatch.setattr(
        document_pipeline, "_record_upload_result",
        lambda doc_id, url: recorded.append((doc_id, url)) or True,
    )
    notified = []
    monkeypatch.setattr(
        export_publisher, "notify_hukukbot", lambda doc_id: notified.append(doc_id)
    )

    def upload_and_race(path, name, folder, use_date_subfolder=False):
        # Gece job'ı upload sürerken satırı etkisizleştirdi
        row.status = "superseded"
        return {"webUrl": "https://sp/orijinal.udf"}

    monkeypatch.setattr(spg, "upload_file_to_sharepoint", upload_and_race)

    upload_queue._attempt_upload(11)

    assert row.status == "superseded"      # uploaded'a çekilmez
    assert recorded == [] and notified == []  # belgeye işlenmez, hook yok
    assert not spool_file.exists() and row.spool_path is None  # spool temizlendi


def test_purge_removes_superseded_spool_immediately(tmp_path):
    from services import upload_queue

    spool_file = tmp_path / "superseded.udf"
    spool_file.write_bytes(b"x")
    row = _FakeOutboxRow(
        id=12, status="superseded", spool_path=str(spool_file),
        done_at=datetime.now(timezone.utc),
    )
    db = _FakeSession([row])

    upload_queue._purge_terminal_spools(db, datetime.now(timezone.utc))

    assert not spool_file.exists() and row.spool_path is None


# ═════════════════════════════════════════════════════════════════════════════
# 6) hukukbot hook girişi — enqueue_document conversion filtresi
# ═════════════════════════════════════════════════════════════════════════════


def _publisher_doc(conversion_status):
    return SimpleNamespace(
        link_mode="LINKED", sharepoint_url="https://sp/x", case=None,
        conversion_status=conversion_status, belge_turu_kodu="ARA-KRR",
    )


def _patch_publisher_db(monkeypatch, doc, existing_outbox_id=55):
    import database
    import models

    session = _ModelSession({
        models.CaseDocument: [doc],
        models.ExportOutbox: [SimpleNamespace(id=existing_outbox_id)],
    })
    monkeypatch.setattr(database, "SessionLocal", lambda: session)


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_enqueue_document_skips_conversion_status(monkeypatch, status):
    from services import export_publisher

    monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
    _patch_publisher_db(monkeypatch, _publisher_doc(status))
    assert export_publisher.enqueue_document(7) is None


def test_enqueue_document_passes_when_conversion_completed(monkeypatch):
    from services import export_publisher

    monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
    _patch_publisher_db(monkeypatch, _publisher_doc(None))
    # Filtreden geçer → mevcut outbox satırının id'si döner (idempotent yol)
    assert export_publisher.enqueue_document(7) == 55


# ═════════════════════════════════════════════════════════════════════════════
# 7) bekçiler — migration + model kolonları
# ═════════════════════════════════════════════════════════════════════════════


def test_migration_op_adds_conversion_columns_with_partial_index():
    import database

    for op in database._MIGRATIONS:
        if op[0] == "columns" and op[1] == "case_documents" and "conversion_status" in op[2]:
            cols = op[2]
            assert "conversion_attempts" in cols and "conversion_spool_path" in cols
            ddl = cols["conversion_status"]
            assert isinstance(ddl, tuple)
            index_sqls = " ".join(ddl[1])
            assert "idx_case_docs_conversion_pending" in index_sqls
            assert "WHERE conversion_status = 'pending'" in index_sqls
            break
    else:
        raise AssertionError("case_documents conversion_status migration op'u yok")


def test_model_has_conversion_columns():
    import models

    cols = models.CaseDocument.__table__.c
    assert "conversion_status" in cols
    assert "conversion_attempts" in cols
    assert "conversion_spool_path" in cols
    assert cols["conversion_status"].nullable is True
