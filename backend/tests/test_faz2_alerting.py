"""Faz 2-C testleri: client-error beacon ucu + CaseDocument.upload_status.

Kapsam:
- /api/client-error: auth'suz 204, alan beyaz listesi + kırpma, gövde tavanı
  (413), bozuk gövde (400), IP başına hız limiti (429), severity=ERROR log
  kaydı ve extra alanların JSON formatter'a geçecek biçimde record'a işlenmesi
- migration bekçisi: _MIGRATIONS'ta upload_status/upload_attempts op'u +
  backfill + partial index
- _record_upload_result: başarı/başarısızlık geçişleri, attempts artışı,
  hukukbot hook kapısı (True yalnız URL commit'inde)
"""
import json
import logging

import pytest


# ─── /api/client-error ───────────────────────────────────────────────────────

def _client():
    # `with` bloğu bilinçli YOK: lifespan (init_db, scheduler, thread'ler)
    # çalışmasın (test_faz2_monitoring ile aynı gerekçe).
    from starlette.testclient import TestClient

    from api import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Hız limiti sayaçları testler arasında taşınmasın (tek in-memory storage)."""
    from rate_limiting import limiter

    limiter.reset()
    yield
    limiter.reset()


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def client_error_records():
    """caplog BİLİNÇLİ kullanılmıyor: api'nin ilk import'u configure_logging()
    ile kök handler'ları değiştirir ve pytest'in capture handler'ını söker
    (import sırasına göre uçuşkan olurdu). Adlandırılmış logger'a doğrudan
    takılan handler dictConfig'den etkilenmez ("client_error" config'de yok)."""
    handler = _ListHandler()
    target = logging.getLogger("client_error")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _post(client, payload, **kwargs):
    # sendBeacon düz string gönderir (Content-Type: text/plain) — testler de
    # JSON header'ı bilinçli koymaz; uç gövdeyi ham okumak zorunda.
    body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    return client.post("/api/client-error", content=body, **kwargs)


def test_client_error_returns_204_and_logs_error(client_error_records):
    r = _post(_client(), {
        "kind": "error",
        "message": "Cannot read properties of undefined",
        "stack": "TypeError: ...\n  at App.tsx:10",
        "url": "https://hukukoid.com/cases",
        "line": 10,
        "col": 5,
    })
    assert r.status_code == 204
    assert len(client_error_records) == 1
    rec = client_error_records[0]
    assert rec.levelname == "ERROR"  # JSON formatter'da severity=ERROR olur
    assert rec.event == "client_error"
    assert rec.client_kind == "error"
    assert rec.client_message == "Cannot read properties of undefined"
    assert rec.client_url == "https://hukukoid.com/cases"
    assert rec.client_line == 10
    assert rec.client_col == 5


def test_client_error_requires_no_auth_header():
    # Bilinçli tasarım: auth kırıkken de rapor gelebilmeli — token yok, yine 204.
    r = _post(_client(), {"kind": "error", "message": "auth yokken de çalışır"})
    assert r.status_code == 204


def test_client_error_whitelist_and_truncation(client_error_records):
    r = _post(_client(), {
        "kind": "csoktu",              # beyaz liste dışı değer → unknown
        "message": "x" * 5000,          # 2000'e kırpılır
        "line": "42",                   # string int'e zorlanır
        "col": "abc",                   # çevrilemez → düşer
        "evil_extra": "sizmamali",      # listede yok → sessizce düşer
    })
    assert r.status_code == 204
    assert len(client_error_records) == 1
    rec = client_error_records[0]
    assert rec.client_kind == "unknown"
    assert len(rec.client_message) == 2000
    assert rec.client_line == 42
    assert rec.client_col is None
    assert not hasattr(rec, "evil_extra")
    assert not hasattr(rec, "client_evil_extra")


def test_client_error_oversized_body_413():
    r = _post(_client(), json.dumps({"message": "y" * (17 * 1024)}))
    assert r.status_code == 413


def test_client_error_malformed_body_400():
    client = _client()
    assert _post(client, "bu json değil {{{").status_code == 400
    assert _post(client, json.dumps(["liste", "gövde"])).status_code == 400


def test_client_error_rate_limited_per_ip():
    client = _client()
    for _ in range(10):
        assert _post(client, {"kind": "error", "message": "m"}).status_code == 204
    # 11. istek aynı IP kovasından → 429 (auth'suz ucun spam koruması)
    assert _post(client, {"kind": "error", "message": "m"}).status_code == 429


# ─── migration bekçisi ───────────────────────────────────────────────────────

def test_migrations_add_upload_status_with_backfill_and_index():
    from database import _MIGRATIONS

    ops = [
        op for op in _MIGRATIONS
        if op[0] == "columns" and op[1] == "case_documents" and "upload_status" in op[2]
    ]
    assert len(ops) == 1, "case_documents.upload_status migration op'u tam bir kez olmalı"
    spec = ops[0][2]["upload_status"]
    assert isinstance(spec, tuple), "backfill + index için (DDL, [post_sql]) biçimi gerekir"
    ddl, post_sql = spec
    assert "DEFAULT 'pending'" in ddl
    joined = " ".join(post_sql)
    # Backfill: URL'i olan eski kayıtlar uploaded, olmayanlar failed
    assert "'uploaded'" in joined and "'failed'" in joined
    assert "sharepoint_url" in joined
    # Partial index: retry taraması uploaded çoğunluğunu taramasın
    assert "idx_case_docs_upload_status" in joined
    assert "upload_status <> 'uploaded'" in joined
    assert ops[0][2].get("upload_attempts") == "INTEGER DEFAULT 0"


def test_model_columns_have_pending_defaults():
    import models

    table = models.CaseDocument.__table__
    assert table.c.upload_status.default.arg == "pending"
    assert table.c.upload_attempts.default.arg == 0


# ─── _record_upload_result ───────────────────────────────────────────────────

class _FakeDoc:
    def __init__(self):
        self.sharepoint_url = None
        self.upload_status = "pending"
        self.upload_attempts = 0


class _FakeSession:
    def __init__(self, doc):
        self._doc = doc
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._doc

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_record_upload_result_success_marks_uploaded(monkeypatch):
    from services import document_pipeline

    doc = _FakeDoc()
    session = _FakeSession(doc)
    monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: session)

    assert document_pipeline._record_upload_result(7, "https://sp/x.pdf") is True
    assert doc.sharepoint_url == "https://sp/x.pdf"
    assert doc.upload_status == "uploaded"
    assert doc.upload_attempts == 1
    assert session.committed and session.closed


def test_record_upload_result_failure_marks_failed(monkeypatch):
    from services import document_pipeline

    doc = _FakeDoc()
    doc.upload_attempts = 2  # önceki denemelerin üstüne sayar
    session = _FakeSession(doc)
    monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: session)

    # False dönüşü hukukbot outbox hook'unu kapalı tutar (BULGULAR #1)
    assert document_pipeline._record_upload_result(7, None) is False
    assert doc.sharepoint_url is None
    assert doc.upload_status == "failed"
    assert doc.upload_attempts == 3
    assert session.committed and session.closed


def test_record_upload_result_missing_doc_is_noop(monkeypatch):
    from services import document_pipeline

    session = _FakeSession(doc=None)
    monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: session)

    assert document_pipeline._record_upload_result(7, "https://sp/x.pdf") is False
    assert session.closed and not session.committed


def test_record_upload_result_without_doc_id_touches_no_db(monkeypatch):
    from services import document_pipeline

    def _boom():
        raise AssertionError("doc_id yokken DB'ye inilmemeli")

    monkeypatch.setattr(document_pipeline, "SessionLocal", _boom)
    assert document_pipeline._record_upload_result(None, "https://sp/x.pdf") is False
