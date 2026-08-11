"""Faz 3-A testleri: SharePoint yükleme outbox/retry kuyruğu (upload_queue).

Kapsam:
- enqueue_upload: spool kopyası + pending satır + worker uyandırma; hata halinde
  None (fallback sözleşmesi) ve yarım spool dosyasının temizlenmesi
- convert_pdfa_and_queue_uploads: asıl yol outbox, enqueue None dönerse eski
  tek-denemeli BackgroundTasks fallback'i
- _attempt_upload: başarı (uploaded + spool silinir + _record_upload_result +
  hukukbot hook kapısı), geçici hata (WARNING + backoff), nihai hata (ERROR +
  extra doc_id/outbox_id + spool KORUNUR), spool kaybı, ham satırında belge
  güncellemesi olmaması
- G011 atomiklik: satırın 'uploaded' geçişi ile belgenin sharepoint_url yazımı
  TEK transaction — belge yazımı ya da commit düşerse satır pending'e geri
  sarılır (kalıcı "uploaded + URL'süz" durum oluşmaz), sonraki tarama dener
- _scan_once: startup reconcile — vadesi gelenler işlenir, gelecektekiler beklet
- _purge_terminal_spools: failed 30 gün sonra, uploaded hemen temizlenir
- worker yaşam döngüsü: idempotent start, taramada exception'a dayanıklılık, stop
- bekçiler: partial index migration op'u, model default'ları, lifespan çağrısı

DB'ye/ağa inilmez (conftest sözleşmesi): SessionLocal fake'lenir, SQLAlchemy
filter ifadeleri fake'te no-op'tur — kod Python tarafında durum guard'larını
yeniden kontrol eder, testler bu defansif davranışa yaslanır.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ─── ortak fake'ler ──────────────────────────────────────────────────────────

class _FakeRow:
    """models.UploadOutbox satırı gibi davranan düz nesne."""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.document_id = kw.get("document_id")
        self.kind = kw.get("kind", "islenmis")
        self.spool_path = kw.get("spool_path")
        self.target_filename = kw.get("target_filename", "belge.pdf")
        self.target_folder = kw.get("target_folder", "02_YEDEK_ARSIV")
        self.status = kw.get("status", "pending")
        self.attempts = kw.get("attempts", 0)
        self.next_attempt_at = kw.get("next_attempt_at")
        self.last_error = kw.get("last_error")
        self.created_at = kw.get("created_at")
        self.done_at = kw.get("done_at")


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
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _FakeQuery(self.rows)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def refresh(self, row):
        if getattr(row, "id", None) is None:
            row.id = 42


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


@pytest.fixture(autouse=True)
def _reset_worker_state():
    """Modül-global worker/event durumu testler arasında taşınmasın.

    stop_upload_worker thread yoksa event'lere dokunmadan döner — _wake
    assert'leri deterministik olsun diye burada açıkça temizlenir."""
    from services import upload_queue

    upload_queue.stop_upload_worker()
    upload_queue._wake.clear()
    upload_queue._stop.clear()
    yield
    upload_queue.stop_upload_worker()
    upload_queue._wake.clear()
    upload_queue._stop.clear()


@pytest.fixture
def root_log_records():
    """Kök logger'a düşen TÜM kayıtlar. document_pipeline modül logger'ı değil
    `logging.error` (kök) kullanır — "nihai olmayan arızada hiç ERROR yok"
    iddiası ancak buradan doğrulanabilir."""
    handler = _ListHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler.records
    root.removeHandler(handler)


@pytest.fixture
def queue_log_records():
    """caplog BİLİNÇLİ değil (test_faz2_alerting ile aynı gerekçe): dictConfig
    pytest capture handler'ını söker; adlandırılmış logger'a takılan handler
    config'den etkilenmez."""
    handler = _ListHandler()
    target = logging.getLogger("services.upload_queue")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _use_spool(monkeypatch, tmp_path):
    spool = tmp_path / "spool"
    monkeypatch.setenv("UPLOAD_SPOOL_DIR", str(spool))
    return spool


# ─── enqueue_upload ──────────────────────────────────────────────────────────

def test_enqueue_copies_to_spool_writes_row_and_wakes_worker(monkeypatch, tmp_path):
    from services import upload_queue

    spool = _use_spool(monkeypatch, tmp_path)
    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4 icerik")

    session = _FakeSession(rows=[])
    monkeypatch.setattr(upload_queue, "SessionLocal", lambda: session)

    outbox_id = upload_queue.enqueue_upload(
        "islenmis", str(src), "yeni.pdf", "02_YEDEK_ARSIV", document_id=7
    )

    assert outbox_id == 42
    assert len(session.added) == 1
    row = session.added[0]
    assert row.kind == "islenmis"
    assert row.document_id == 7
    assert row.target_filename == "yeni.pdf"
    assert row.target_folder == "02_YEDEK_ARSIV"
    assert row.status == "pending" and row.attempts == 0
    # Spool kopyası kaynağın birebir kopyası; kaynak dosyaya dokunulmaz
    spool_file = Path(row.spool_path)
    assert spool_file.parent == spool
    assert spool_file.read_bytes() == b"%PDF-1.4 icerik"
    assert src.exists()
    assert session.commits == 1 and session.closed
    assert upload_queue._wake.is_set()


def test_enqueue_missing_source_returns_none(monkeypatch, tmp_path):
    from services import upload_queue

    _use_spool(monkeypatch, tmp_path)
    db_calls = []
    monkeypatch.setattr(
        upload_queue, "SessionLocal", lambda: db_calls.append(1) or _FakeSession([])
    )

    assert upload_queue.enqueue_upload(
        "ham", str(tmp_path / "yok.pdf"), "a.pdf", "01_HAM_ARSIV"
    ) is None
    assert db_calls == [], "kaynak dosya yokken DB'ye inilmemeli"
    assert not upload_queue._wake.is_set()


def test_enqueue_db_error_cleans_partial_spool_and_returns_none(monkeypatch, tmp_path):
    from services import upload_queue

    spool = _use_spool(monkeypatch, tmp_path)
    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"x")

    class _BoomSession:
        def add(self, row):
            raise RuntimeError("db koptu")

        def close(self):
            pass

    monkeypatch.setattr(upload_queue, "SessionLocal", _BoomSession)

    assert upload_queue.enqueue_upload("ham", str(src), "a.pdf", "01_HAM_ARSIV") is None
    # Yarım kalan spool kopyası bırakılmaz (KVKK + çöp birikimi)
    assert list(spool.glob("*")) == []


# ─── convert_pdfa_and_queue_uploads entegrasyonu ─────────────────────────────

def _run_convert(monkeypatch, tmp_path, enqueue_returns):
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4 kaynak")
    pdfa = tmp_path / "pdfa.pdf"
    pdfa.write_bytes(b"%PDF-1.4 pdfa")

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", lambda p, **kw: str(pdfa))
    monkeypatch.setattr(document_pipeline, "save_case_document", lambda **kw: 7)

    calls = []

    def fake_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        calls.append((kind, source_path, target_filename, target_folder, document_id))
        return enqueue_returns.get(kind)

    monkeypatch.setattr(upload_queue, "enqueue_upload", fake_enqueue)

    bg = _FakeBackgroundTasks()
    results, timings = {}, {}
    pdfa_out, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=bg,
        source_path=str(src),
        ham_filename="2026-08-10_kaynak.pdf",
        ham_folder="01_HAM_ARSIV",
        islenmis_folder="02_YEDEK_ARSIV",
        new_filename="yeni.pdf",
        original_filename="kaynak.pdf",
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
        ham_source_path=None,
    )
    return (pdfa_out, doc_id), calls, bg, str(pdfa), str(src)


def test_convert_enqueues_both_uploads_without_background_tasks(monkeypatch, tmp_path):
    (pdfa_out, doc_id), calls, bg, pdfa, src = _run_convert(
        monkeypatch, tmp_path, enqueue_returns={"ham": 1, "islenmis": 2}
    )

    assert doc_id == 7 and pdfa_out == pdfa
    assert [(c[0], c[4]) for c in calls] == [("ham", 7), ("islenmis", 7)]
    ham_call, islenmis_call = calls
    assert ham_call[1] == src and ham_call[2] == "2026-08-10_kaynak.pdf" and ham_call[3] == "01_HAM_ARSIV"
    assert islenmis_call[1] == pdfa and islenmis_call[2] == "yeni.pdf" and islenmis_call[3] == "02_YEDEK_ARSIV"
    # Asıl yol outbox: fire-and-forget upload task'ı kuyruklanmaz
    assert bg.tasks == []


def test_convert_falls_back_to_background_tasks_when_enqueue_fails(monkeypatch, tmp_path):
    from services import document_pipeline

    _, calls, bg, pdfa, src = _run_convert(
        monkeypatch, tmp_path, enqueue_returns={"ham": None, "islenmis": None}
    )

    assert len(calls) == 2
    # Eski tek-denemeli yol: davranış Faz 3-A öncesinden kötü olmasın
    assert [(t[0], t[1]) for t in bg.tasks] == [
        (document_pipeline.async_ham_upload, (src, "2026-08-10_kaynak.pdf", "01_HAM_ARSIV")),
        (document_pipeline.async_islenmis_upload, (pdfa, "yeni.pdf", "02_YEDEK_ARSIV", 7)),
    ]


# ─── _attempt_upload ─────────────────────────────────────────────────────────

def _spooled_row(tmp_path, **kw):
    spool_file = tmp_path / kw.pop("spool_name", "spool_kopya.pdf")
    spool_file.write_bytes(b"%PDF-1.4 spool")
    return _FakeRow(spool_path=str(spool_file), **kw)


def _patch_session(monkeypatch, rows):
    from services import upload_queue

    sessions = []

    def factory():
        s = _FakeSession(rows)
        sessions.append(s)
        return s

    monkeypatch.setattr(upload_queue, "SessionLocal", factory)
    return sessions


def test_attempt_success_marks_uploaded_deletes_spool_and_opens_hook(monkeypatch, tmp_path):
    from services import upload_queue, document_pipeline, export_publisher

    row = _spooled_row(tmp_path, id=5, document_id=7, kind="islenmis")
    spool_path = row.spool_path
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint",
        lambda *a, **kw: {"webUrl": "https://sp/yeni.pdf"},
    )
    recorded, notified = [], []

    def fake_record(doc_id, url, db=None):
        # db is not None: belge yazımı outbox satırının transaction'ına
        # katılıyor (G011 atomik yol) — imza değişse bu bekçi düşer
        recorded.append((doc_id, url, db is not None))
        return True

    monkeypatch.setattr(document_pipeline, "_record_upload_result", fake_record)
    monkeypatch.setattr(
        export_publisher, "notify_hukukbot", lambda doc_id: notified.append(doc_id)
    )

    upload_queue._attempt_upload(5)

    assert row.status == "uploaded"
    assert row.attempts == 1
    assert row.done_at is not None and row.last_error is None
    assert not os.path.exists(spool_path)
    assert row.spool_path is None
    assert recorded == [(7, "https://sp/yeni.pdf", True)]
    assert notified == [7]  # hook yalnız URL commit'inde (BULGULAR #1)


def test_attempt_success_ham_touches_no_document(monkeypatch, tmp_path):
    from services import upload_queue, document_pipeline, export_publisher

    row = _spooled_row(tmp_path, id=6, document_id=7, kind="ham")
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint", lambda *a, **kw: {"webUrl": "https://sp/h.pdf"}
    )
    monkeypatch.setattr(
        document_pipeline, "_record_upload_result",
        lambda *a, **kw: pytest.fail("ham satırı belge kaydına dokunmamalı"),
    )
    monkeypatch.setattr(
        export_publisher, "notify_hukukbot",
        lambda *a: pytest.fail("ham satırı hukukbot hook'u açmamalı"),
    )

    upload_queue._attempt_upload(6)
    assert row.status == "uploaded"


def test_attempt_transient_failure_schedules_backoff_with_warning(
    monkeypatch, tmp_path, queue_log_records
):
    from services import upload_queue, document_pipeline

    row = _spooled_row(tmp_path, id=5, document_id=7, kind="islenmis")
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader

    def boom(*a, **kw):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(uploader, "upload_file_to_sharepoint", boom)
    recorded = []

    def fake_record(doc_id, url, db=None):
        # Başarısız denemede belge yazımı KENDİ session'ını açar (db=None):
        # satır pending kalacağı için atomiklik gerekmiyor
        recorded.append((doc_id, url, db))
        return False

    monkeypatch.setattr(document_pipeline, "_record_upload_result", fake_record)

    before = datetime.now(timezone.utc)
    upload_queue._attempt_upload(5)

    assert row.status == "pending"  # nihai DEĞİL — retry bekliyor
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert row.next_attempt_at >= before + timedelta(seconds=upload_queue.RETRY_BACKOFF_SECONDS[0] - 1)
    assert "429" in row.last_error
    assert os.path.exists(row.spool_path)  # payload retry için durur
    assert recorded == [(7, None, None)]  # belge kartı 'failed' + attempts artışı görür
    # Geçici hata WARNING'dir — ERROR-oranı alarmını (≥5/5dk) çaldırmamalı
    warnings = [r for r in queue_log_records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and not [r for r in queue_log_records if r.levelno >= logging.ERROR]
    assert warnings[0].doc_id == 7 and warnings[0].outbox_id == 5


def test_attempt_final_failure_marks_failed_with_error_and_keeps_spool(
    monkeypatch, tmp_path, queue_log_records
):
    from services import upload_queue, document_pipeline

    row = _spooled_row(
        tmp_path, id=5, document_id=7, kind="islenmis",
        attempts=upload_queue.MAX_ATTEMPTS - 1,
    )
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("503 kalıcı")),
    )
    monkeypatch.setattr(document_pipeline, "_record_upload_result", lambda *a, **kw: False)

    upload_queue._attempt_upload(5)

    assert row.status == "failed"
    assert row.attempts == upload_queue.MAX_ATTEMPTS
    assert row.done_at is not None
    # Spool dosyası saklama süresi boyunca KALIR — elle kurtarma şansı
    assert os.path.exists(row.spool_path)
    errors = [r for r in queue_log_records if r.levelno == logging.ERROR]
    assert len(errors) == 1, "nihai başarısızlık tam BİR ERROR üretmeli"
    assert errors[0].doc_id == 7 and errors[0].outbox_id == 5 and errors[0].kind == "islenmis"


def test_attempt_missing_spool_fails_immediately(monkeypatch, tmp_path, queue_log_records):
    from services import upload_queue, document_pipeline

    row = _FakeRow(id=5, document_id=7, kind="islenmis", spool_path=str(tmp_path / "yok.pdf"))
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint",
        lambda *a, **kw: pytest.fail("spool yokken upload denenmemeli"),
    )
    recorded = []
    monkeypatch.setattr(
        document_pipeline, "_record_upload_result",
        lambda doc_id, url, db=None: recorded.append((doc_id, url)) or False,
    )

    upload_queue._attempt_upload(5)

    assert row.status == "failed" and row.done_at is not None
    assert recorded == [(7, None)]  # belge 'pending'de asılı kalmasın
    assert [r for r in queue_log_records if r.levelno == logging.ERROR]


def test_attempt_skips_non_pending_rows(monkeypatch, tmp_path):
    from services import upload_queue

    row = _spooled_row(tmp_path, id=5, status="uploaded", attempts=1)
    _patch_session(monkeypatch, [row])

    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint",
        lambda *a, **kw: pytest.fail("terminal satır yeniden yüklenmemeli"),
    )

    upload_queue._attempt_upload(5)
    assert row.attempts == 1  # dokunulmadı


# ─── G011: outbox 'uploaded' + belge URL yazımı atomik mi ────────────────────

class _FakeDocRow:
    """models.CaseDocument satırının yükleme alanları."""

    def __init__(self, **kw):
        self.id = kw.get("id", 7)
        self.sharepoint_url = kw.get("sharepoint_url")
        self.upload_status = kw.get("upload_status", "pending")
        self.upload_attempts = kw.get("upload_attempts", 0)


class _TxSession:
    """Transaction semantiğini taklit eden session: commit izlenen nesnelerin o
    anki halini KALICI yapar, rollback son kalıcı hale geri sarar.

    _FakeSession yalnız commit/rollback sayar; Python nesnesindeki mutasyonu
    geri almadığı için "arıza sonrası satır pending'e döndü mü" sorusunu
    cevaplayamaz — atomiklik iddiası bu yüzden burada kanıtlanır. journal,
    her commit'te kalıcılaşan (satır statüleri, belge URL'si) çiftini tutar:
    "uploaded ama URL'süz" bir ara durumun HİÇ kalıcı olmadığı böyle görülür.
    """

    def __init__(self, outbox_rows, doc=None, fail_doc_query=False, fail_commit_no=None):
        self.outbox_rows = outbox_rows
        self.doc = doc
        self.fail_doc_query = fail_doc_query
        self.fail_commit_no = fail_commit_no
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.journal = []
        self._durable = self._snapshot()

    def _snapshot(self):
        tracked = [o for o in list(self.outbox_rows) + [self.doc] if o is not None]
        return [(obj, dict(obj.__dict__)) for obj in tracked]

    def query(self, model):
        import models

        if model is models.CaseDocument:
            if self.fail_doc_query:
                raise RuntimeError("DB koptu (belge yazımı)")
            return _FakeQuery([self.doc] if self.doc is not None else [])
        return _FakeQuery(self.outbox_rows)

    def commit(self):
        self.commits += 1
        if self.fail_commit_no == self.commits:
            raise RuntimeError("commit koptu")
        self._durable = self._snapshot()
        self.journal.append(
            ([r.status for r in self.outbox_rows], getattr(self.doc, "sharepoint_url", None))
        )

    def rollback(self):
        self.rollbacks += 1
        for obj, state in self._durable:
            obj.__dict__.clear()
            obj.__dict__.update(state)

    def close(self):
        self.closed = True


def _patch_tx_sessions(monkeypatch, rows, doc, **result_session_kwargs):
    """SessionLocal → _TxSession. _attempt_upload iki session açar: (1) deneme
    sayacı, (2) sonuç yazımı. Arıza enjeksiyonu YALNIZ ikinciye uygulanır."""
    from services import upload_queue

    sessions = []

    def factory():
        kw = result_session_kwargs if len(sessions) == 1 else {}
        s = _TxSession(rows, doc, **kw)
        sessions.append(s)
        return s

    monkeypatch.setattr(upload_queue, "SessionLocal", factory)
    return sessions


def _patch_uploader_ok(monkeypatch, web_url="https://sp/yeni.pdf"):
    import sharepoint.sharepoint_uploader_graph as uploader

    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint", lambda *a, **kw: {"webUrl": web_url}
    )


def test_attempt_success_writes_row_and_document_in_one_transaction(monkeypatch, tmp_path):
    """Başarı yolu: satır 'uploaded' ile belge URL'si TEK commit'te kalıcılaşır."""
    from services import upload_queue, export_publisher

    row = _spooled_row(tmp_path, id=5, document_id=7, kind="islenmis")
    doc = _FakeDocRow(id=7)
    sessions = _patch_tx_sessions(monkeypatch, [row], doc)
    _patch_uploader_ok(monkeypatch)

    notified = []
    monkeypatch.setattr(
        export_publisher,
        "notify_hukukbot",
        # Hook anındaki kalıcı durumu da kaydet: URL commit'inden SONRA mı?
        lambda doc_id: notified.append((doc_id, list(sessions[1].journal))),
    )

    upload_queue._attempt_upload(5)

    assert row.status == "uploaded"
    assert doc.sharepoint_url == "https://sp/yeni.pdf"
    assert doc.upload_status == "uploaded" and doc.upload_attempts == 1

    result_session = sessions[1]
    # İlk (ve tek) durum commit'i satırı 'uploaded' yaparken belge URL'sini de
    # taşır; hiçbir kalıcı ara durumda "uploaded ama URL'süz" yok
    assert result_session.journal[0] == (["uploaded"], "https://sp/yeni.pdf")
    assert not [
        j for j in result_session.journal if j[0] == ["uploaded"] and j[1] is None
    ]
    assert notified[0][0] == 7
    assert notified[0][1][0][1] == "https://sp/yeni.pdf", "hook URL kalıcı olmadan açılmamalı"


def test_attempt_success_doc_write_failure_rolls_back_outbox_row(
    monkeypatch, tmp_path, queue_log_records, root_log_records
):
    """G011 çift-arıza penceresi: belge yazımı düşerse satır 'uploaded'da
    KALMAZ — pending'e geri sarılır, sonraki tarama yeniden dener."""
    from services import upload_queue, export_publisher

    row = _spooled_row(tmp_path, id=5, document_id=7, kind="islenmis")
    spool_path = row.spool_path
    doc = _FakeDocRow(id=7)
    sessions = _patch_tx_sessions(monkeypatch, [row], doc, fail_doc_query=True)
    _patch_uploader_ok(monkeypatch)
    monkeypatch.setattr(
        export_publisher,
        "notify_hukukbot",
        lambda *a: pytest.fail("URL kalıcı değilken hukukbot hook'u açılmamalı"),
    )

    upload_queue._attempt_upload(5)

    # Kalıcı durum: satır PENDING, belge dokunulmamış — "uploaded + URL'süz" yok
    assert row.status == "pending" and row.done_at is None
    assert doc.sharepoint_url is None and doc.upload_status == "pending"
    assert doc.upload_attempts == 0
    assert sessions[1].rollbacks == 1 and sessions[1].journal == []
    # Deneme sayacı ÖNCEKİ session'da commit edildi → zehirli-dosya bekçisi durur
    assert row.attempts == 1
    # Payload retry için durur ve satır yeniden vadesi gelmiş sayılır
    assert os.path.exists(spool_path)
    assert upload_queue._is_due(row, datetime.now(timezone.utc))
    # Retry edilebilir arıza → WARNING; nihai değil, ERROR yok (alarm sözleşmesi)
    assert len([r for r in queue_log_records if r.levelno == logging.WARNING]) == 1
    assert not [r for r in root_log_records if r.levelno >= logging.ERROR]


def test_attempt_success_commit_failure_leaves_no_half_written_state(
    monkeypatch, tmp_path, queue_log_records, root_log_records
):
    """Süreç ölümü/commit arızası penceresi: iki yazımın ARASINDA commit
    olmadığı için kalıcı sonuç ya 'ikisi de' ya 'hiçbiri'dir."""
    from services import upload_queue, export_publisher

    row = _spooled_row(tmp_path, id=5, document_id=7, kind="islenmis")
    doc = _FakeDocRow(id=7)
    # Sonuç session'ının İLK commit'i = satır+belge yazımının tek commit'i
    sessions = _patch_tx_sessions(monkeypatch, [row], doc, fail_commit_no=1)
    _patch_uploader_ok(monkeypatch)
    monkeypatch.setattr(
        export_publisher,
        "notify_hukukbot",
        lambda *a: pytest.fail("commit düştüyse hook açılmamalı"),
    )

    upload_queue._attempt_upload(5)

    assert sessions[1].journal == [], "hiçbir ara durum kalıcılaşmamalı"
    assert row.status == "pending" and row.done_at is None
    assert doc.sharepoint_url is None and doc.upload_status == "pending"
    assert os.path.exists(row.spool_path)  # payload retry için durur
    assert len([r for r in queue_log_records if r.levelno == logging.WARNING]) == 1
    assert not [r for r in root_log_records if r.levelno >= logging.ERROR]


# ─── zamanlama yardımcıları ──────────────────────────────────────────────────

def test_backoff_schedule_grows_and_caps():
    from services import upload_queue

    assert upload_queue._next_delay_seconds(1) == upload_queue.RETRY_BACKOFF_SECONDS[0]
    delays = [upload_queue._next_delay_seconds(n) for n in range(1, upload_queue.MAX_ATTEMPTS + 3)]
    assert delays == sorted(delays), "backoff monoton artmalı"
    assert delays[-1] == upload_queue.RETRY_BACKOFF_SECONDS[-1], "takvim sonunda tavana sabitlenmeli"


def test_is_due_rules():
    from services.upload_queue import _is_due

    now = datetime.now(timezone.utc)
    assert _is_due(_FakeRow(status="pending", next_attempt_at=None), now)
    assert _is_due(_FakeRow(status="pending", next_attempt_at=now - timedelta(seconds=1)), now)
    assert not _is_due(_FakeRow(status="pending", next_attempt_at=now + timedelta(hours=1)), now)
    assert not _is_due(_FakeRow(status="uploaded", next_attempt_at=None), now)
    # Defansif: naive timestamp UTC sayılır, karşılaştırma patlamaz
    assert _is_due(_FakeRow(status="pending", next_attempt_at=datetime(2020, 1, 1)), now)


def test_scan_once_processes_due_rows_in_id_order(monkeypatch):
    from services import upload_queue

    now = datetime.now(timezone.utc)
    rows = [
        _FakeRow(id=1, status="pending", next_attempt_at=None),
        _FakeRow(id=2, status="pending", next_attempt_at=now - timedelta(minutes=5)),
        _FakeRow(id=3, status="pending", next_attempt_at=now + timedelta(hours=2)),
        _FakeRow(id=4, status="uploaded"),
    ]
    _patch_session(monkeypatch, rows)
    monkeypatch.setattr(upload_queue, "_purge_terminal_spools", lambda db, now: None)

    attempted = []
    monkeypatch.setattr(upload_queue, "_attempt_upload", lambda oid: attempted.append(oid))

    assert upload_queue._scan_once() == 2
    assert attempted == [1, 2]  # startup reconcile: NULL + vadesi geçmiş; gelecektekiler bekler


# ─── janitor ─────────────────────────────────────────────────────────────────

def test_purge_removes_old_failed_and_any_uploaded_spools(monkeypatch, tmp_path):
    from services import upload_queue

    now = datetime.now(timezone.utc)
    old_failed = _spooled_row(
        tmp_path, spool_name="eski_failed.pdf", id=1, status="failed",
        done_at=now - timedelta(days=upload_queue.FAILED_SPOOL_RETENTION_DAYS + 5),
    )
    fresh_failed = _spooled_row(
        tmp_path, spool_name="taze_failed.pdf", id=2, status="failed",
        done_at=now - timedelta(days=1),
    )
    uploaded_leftover = _spooled_row(tmp_path, spool_name="uploaded_artik.pdf", id=3, status="uploaded")
    pending = _spooled_row(tmp_path, spool_name="bekleyen.pdf", id=4, status="pending")
    rows = [old_failed, fresh_failed, uploaded_leftover, pending]

    session = _FakeSession(rows)
    upload_queue._purge_terminal_spools(session, now)

    assert old_failed.spool_path is None  # saklama süresi doldu → silindi
    assert fresh_failed.spool_path is not None and os.path.exists(fresh_failed.spool_path)
    assert uploaded_leftover.spool_path is None  # başarı anında silinemeyen artık
    assert pending.spool_path is not None and os.path.exists(pending.spool_path)


# ─── worker yaşam döngüsü ────────────────────────────────────────────────────

def test_worker_start_is_idempotent_and_survives_scan_errors(monkeypatch):
    from services import upload_queue

    scans = []

    def fake_scan():
        scans.append(1)
        if len(scans) == 1:
            raise RuntimeError("ilk tarama patlasın — worker ölmemeli")
        return 0

    monkeypatch.setattr(upload_queue, "_scan_once", fake_scan)

    assert upload_queue.start_upload_worker() is True
    assert upload_queue.start_upload_worker() is False  # zaten koşuyor

    # İlk tarama exception'la bitti; wake ikinci taramayı tetikler → hayatta
    deadline = time.time() + 5
    while len(scans) < 2 and time.time() < deadline:
        upload_queue._wake.set()
        time.sleep(0.02)
    assert len(scans) >= 2, "worker taramadaki exception'dan sonra yaşamalı"

    upload_queue.stop_upload_worker()
    assert upload_queue._worker_thread is None


# ─── bekçiler ────────────────────────────────────────────────────────────────

def test_migrations_have_upload_outbox_partial_index():
    from database import _MIGRATIONS

    ops = [op for op in _MIGRATIONS if op[0] == "index" and op[1] == "upload_outbox"]
    assert len(ops) == 1, "upload_outbox partial index op'u tam bir kez olmalı"
    joined = " ".join(ops[0][2])
    assert "idx_upload_outbox_pending" in joined
    assert "WHERE status = 'pending'" in joined


def test_upload_outbox_model_defaults():
    import models

    table = models.UploadOutbox.__table__
    assert table.c.status.default.arg == "pending"
    assert table.c.attempts.default.arg == 0
    assert table.c.document_id.nullable
    fk = list(table.c.document_id.foreign_keys)[0]
    assert fk.ondelete == "CASCADE"


def test_lifespan_starts_upload_worker():
    """Bekçi: api.py lifespan'i worker'ı başlatmayı bırakırsa kuyruk sessizce
    ölür (satırlar birikir, kimse işlemez) — kaynak taraması bunu yakalar."""
    api_src = (Path(__file__).resolve().parent.parent / "api.py").read_text(encoding="utf-8")
    assert "start_upload_worker()" in api_src
    assert "stop_upload_worker()" in api_src


def test_init_db_imports_models_for_create_all():
    """Bekçi: init_db gövdesinde gerçek `import models` olmalı. migrate.py
    yalnız database'i import eder; bu satır yokken Base.metadata boş kalır ve
    create_all YENİ tabloları sessizce atlar (Faz 3-A'da upload_outbox ile
    yakalandı — tablo ancak lifespan'deki yedek init_db'de oluşuyordu; 3-E o
    yedeği kaldıracak)."""
    import ast
    import inspect

    import database

    tree = ast.parse(inspect.getsource(database.init_db))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert "models" in imports, "init_db create_all'dan önce models'i import etmeli"
