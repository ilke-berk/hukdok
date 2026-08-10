"""Faz 0 (0-A) sertleştirme garantileri.

- 0.2: hata yolunda DB session'ı daima kapanır (pool tükenmesi düzeltmesi) —
  SessionLocal sahte session'la değiştirilir, query/commit patlatılır,
  close çağrısı doğrulanır.
- 0.9: PROCESS_CACHE sahiplik kontrolü — başka kullanıcının process_id'si
  tüketilemez/tazelenemez, girdi sahibinde kalır (varlık sızdırılmaz).
- 0.10: extra ekler ana dosyayla aynı doğrulamadan geçer (uzantı + boyut +
  magic-byte); geçemeyen ek e-postaya girmez, adı atlananlar listesinde döner.

DB'ye/ağa erişim yok.
"""
import asyncio
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")


# ── 0.2: session sızıntıları ─────────────────────────────────────────────────


class _LeakProbeSession:
    """query/commit'te patlayan, close çağrısını kaydeden sahte session."""

    def __init__(self, fail_on: str):
        self.fail_on = fail_on
        self.closed = False

    def query(self, *args, **kwargs):
        if self.fail_on == "query":
            raise RuntimeError("boom (query)")
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None

    def add(self, obj):
        pass

    def commit(self):
        if self.fail_on == "commit":
            raise RuntimeError("boom (commit)")

    def refresh(self, obj):
        pass

    def close(self):
        self.closed = True


def _probe_factory(fail_on: str):
    made = []

    def factory():
        s = _LeakProbeSession(fail_on)
        made.append(s)
        return s

    return factory, made


def test_save_case_document_closes_session_on_error(monkeypatch):
    from services import document_pipeline

    factory, made = _probe_factory("commit")
    monkeypatch.setattr(document_pipeline, "SessionLocal", factory)

    doc_id = document_pipeline.save_case_document(
        case_id=None, original_filename="a.pdf", stored_filename="b.pdf"
    )
    assert doc_id is None
    assert made and all(s.closed for s in made)


def test_save_hearing_date_closes_session_on_error(monkeypatch):
    from services import document_pipeline

    factory, made = _probe_factory("query")
    monkeypatch.setattr(document_pipeline, "SessionLocal", factory)

    results = {}
    document_pipeline.save_hearing_date(
        linked_case_id=1,
        belge_turu_kodu="DURUSMA",
        sonraki_durusma_tarihi="2026-09-10",
        sonraki_durusma_saati=None,
        avukat_adi="",
        new_filename="x.pdf",
        current_user_name="test",
        results=results,
    )
    assert results["hearing_date_saved"] is None
    assert made and all(s.closed for s in made)


def test_auto_update_case_status_closes_session_on_error(monkeypatch):
    from routes import processing

    factory, made = _probe_factory("query")
    monkeypatch.setattr(processing, "SessionLocal", factory)

    assert processing._auto_update_case_status(1, "KARAR", "test") is False
    assert made and all(s.closed for s in made)


def test_auto_enrich_case_data_closes_session_on_error(monkeypatch):
    from routes import processing

    factory, made = _probe_factory("query")
    monkeypatch.setattr(processing, "SessionLocal", factory)

    assert processing._auto_enrich_case_data(1, "AVK1", "Karşı Taraf", "test") == {}
    assert made and all(s.closed for s in made)


# ── 0.9: PROCESS_CACHE sahiplik ──────────────────────────────────────────────


def _purge_cache_entry(cache, key):
    """Test temizliği: girdiyi VE (3-E adopt'unun cache dizinine taşıdığı)
    payload dosyasını düşürür — modül-genel cache'te artık bırakma."""
    from file_utils import safe_remove

    entry = cache.pop(key) or {}
    safe_remove(entry.get("path"))
    if entry.get("original_path"):
        safe_remove(entry.get("original_path"))


def test_accept_incoming_file_owner_mismatch_preserves_entry(tmp_path):
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF fake")
    PROCESS_CACHE.set("pid-owned", {"path": str(p), "original_path": None, "owner": "sahip@example.com"})
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(document_pipeline.accept_incoming_file(
                "pid-owned", None, PROCESS_CACHE, owner="saldirgan@example.com"
            ))
        assert exc.value.status_code == 400
        # Girdi tüketilmedi — gerçek sahibi hâlâ kullanabilir
        assert PROCESS_CACHE.get("pid-owned") is not None
    finally:
        _purge_cache_entry(PROCESS_CACHE, "pid-owned")


def test_accept_incoming_file_owner_match_consumes(tmp_path):
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF fake")
    PROCESS_CACHE.set("pid-owned2", {"path": str(p), "original_path": None, "owner": "sahip@example.com"})
    temp_path = None
    try:
        temp_path, ham_path = asyncio.run(document_pipeline.accept_incoming_file(
            "pid-owned2", None, PROCESS_CACHE, owner="  Sahip@Example.COM "
        ))
        # 3-E: set() payload'ı cache dizinine TAŞIR — dönen yol adopt sonrası
        # konumdur; içerik ve tüketim semantiği aynen korunur.
        assert os.path.exists(temp_path)
        assert Path(temp_path).parent == PROCESS_CACHE._dir
        assert Path(temp_path).read_bytes() == b"%PDF fake"
        assert ham_path == temp_path
        assert PROCESS_CACHE.get("pid-owned2") is None  # POP edildi
    finally:
        _purge_cache_entry(PROCESS_CACHE, "pid-owned2")
        if temp_path:
            from file_utils import safe_remove
            safe_remove(temp_path)


def test_accept_incoming_file_legacy_entry_without_owner_denied(tmp_path):
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF fake")
    PROCESS_CACHE.set("pid-legacy", {"path": str(p), "original_path": None})
    try:
        with pytest.raises(HTTPException):
            asyncio.run(document_pipeline.accept_incoming_file(
                "pid-legacy", None, PROCESS_CACHE, owner="biri@example.com"
            ))
    finally:
        _purge_cache_entry(PROCESS_CACHE, "pid-legacy")


def test_touch_owned_semantics():
    from routes.processing import PROCESS_CACHE, _touch_owned

    PROCESS_CACHE.set("pid-touch", {"path": "/tmp/x.pdf", "owner": "sahip@example.com"})
    try:
        assert _touch_owned(PROCESS_CACHE, "pid-touch", "sahip@example.com") is True
        assert _touch_owned(PROCESS_CACHE, "pid-touch", "baskasi@example.com") is False
        assert _touch_owned(PROCESS_CACHE, "pid-yok", "sahip@example.com") is False
        # Yanlış sahip denemesi girdiyi silmez
        assert PROCESS_CACHE.get("pid-touch") is not None
    finally:
        PROCESS_CACHE.delete("pid-touch")


# ── 0.10: extra ek doğrulaması ───────────────────────────────────────────────


class _FakeUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._pos:]
        else:
            chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_save_extra_attachments_validates_each_file(monkeypatch):
    from file_utils import safe_remove
    from services import document_pipeline

    files = [
        _FakeUpload("gecerli.pdf", b"%PDF-1.4 icerik"),
        _FakeUpload("zararli.exe", b"MZ\x90\x00 calistirabilir"),
        _FakeUpload("sahte.pdf", b"MZ\x90\x00 pdf degil"),
    ]
    saved, skipped = asyncio.run(document_pipeline.save_extra_attachments(files))
    try:
        assert [s["name"] for s in saved] == ["gecerli.pdf"]
        assert os.path.exists(saved[0]["path"])
        assert set(skipped) == {"zararli.exe", "sahte.pdf"}
    finally:
        for s in saved:
            safe_remove(s["path"])


def test_save_extra_attachments_enforces_size_limit(monkeypatch):
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "MAX_UPLOAD_BYTES", 10)
    files = [_FakeUpload("buyuk.pdf", b"%PDF-1.4 " + b"x" * 100)]
    saved, skipped = asyncio.run(document_pipeline.save_extra_attachments(files))
    assert saved == []
    assert skipped == ["buyuk.pdf"]


# ── 0.7: MAX_PDF_PAGES ölü kod düzeltmesi ────────────────────────────────────


def test_pdf_page_limit_error_is_valueerror_and_wired_to_analyzer():
    import analyzer
    from pdf.pdf_utils import PdfPageLimitError

    assert issubclass(PdfPageLimitError, ValueError)
    assert analyzer.PdfPageLimitError is PdfPageLimitError


def test_load_and_analyze_pdf_reraises_page_limit(monkeypatch):
    from pdf import pdf_utils

    class _FakeDoc:
        def __len__(self):
            return pdf_utils.MAX_PDF_PAGES + 1

        def close(self):
            pass

    monkeypatch.setattr(pdf_utils.fitz, "open", lambda p: _FakeDoc())
    # Önceki davranış: genel except yutup (True, None, "ERROR: ...") döndürüyordu
    with pytest.raises(pdf_utils.PdfPageLimitError):
        pdf_utils.load_and_analyze_pdf("dummy.pdf")


# ── 0.5: e-posta kill-switch ─────────────────────────────────────────────────


def test_email_config_returns_kill_switch_flags(monkeypatch):
    import email_sender

    monkeypatch.setattr(email_sender, "_load_env", lambda: None)
    monkeypatch.delenv("EMAIL_ENABLED", raising=False)
    monkeypatch.delenv("EMAIL_TEST_MODE", raising=False)
    cfg = email_sender._get_email_config()
    assert cfg["enabled"] is True  # anahtar yoksa açık (mevcut prod davranışı)
    assert cfg["test_mode"] is False

    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("EMAIL_TEST_MODE", "true")
    cfg = email_sender._get_email_config()
    assert cfg["enabled"] is False
    assert cfg["test_mode"] is True


def test_email_pre_check_honors_kill_switch(monkeypatch, tmp_path):
    import email_sender
    from services import document_pipeline

    p = tmp_path / "f.pdf"
    p.write_bytes(b"%PDF")
    monkeypatch.setattr(
        email_sender, "_get_email_config",
        lambda: {"sender": "s@x.com", "enabled": False, "test_mode": False},
    )
    reason = document_pipeline.email_pre_check(str(p), ["a@b.com"])
    assert reason is not None and "EMAIL_ENABLED" in reason


def test_send_document_email_kill_switch_blocks_network(monkeypatch, tmp_path):
    import email_sender

    p = tmp_path / "f.pdf"
    p.write_bytes(b"%PDF")
    monkeypatch.setattr(
        email_sender, "_get_email_config",
        lambda: {"sender": "s@x.com", "enabled": False, "test_mode": False},
    )

    def _no_net(*a, **k):
        raise AssertionError("kill-switch açıkken ağ çağrısı yapılmamalı")

    monkeypatch.setattr(email_sender, "get_graph_token", _no_net)
    result = email_sender.send_document_email(["a@b.com"], "konu", "gövde", str(p), "f.pdf")
    assert result["success"] is False
    assert "kapalı" in result["message"]


# ── 0.6: e-posta ek limiti + arşiv referansı ─────────────────────────────────


def _email_env(monkeypatch, sent):
    import email_sender

    monkeypatch.setattr(
        email_sender, "_get_email_config",
        lambda: {"sender": "s@x.com", "enabled": True, "test_mode": False},
    )
    monkeypatch.setattr(email_sender, "get_graph_token", lambda: "tok")

    class _Resp:
        status_code = 202
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["payload"] = json
        return _Resp()

    monkeypatch.setattr(email_sender.requests, "post", fake_post)
    return email_sender


def test_send_document_email_oversize_falls_back_to_archive_note(monkeypatch, tmp_path):
    sent = {}
    email_sender = _email_env(monkeypatch, sent)

    big = tmp_path / "buyuk.pdf"
    big.write_bytes(b"%PDF" + b"0" * (4 * 1024 * 1024))
    result = email_sender.send_document_email(["a@b.com"], "konu", "gövde", str(big), "buyuk.pdf")

    assert result["success"] is True
    msg = sent["payload"]["message"]
    assert msg["attachments"] == []  # Graph ~4 MB'ta keserdi; ek yerine referans
    assert "ek limitini" in msg["body"]["content"]
    assert "buyuk.pdf" in msg["body"]["content"]


def test_send_document_email_small_attachment_still_attached(monkeypatch, tmp_path):
    sent = {}
    email_sender = _email_env(monkeypatch, sent)

    small = tmp_path / "kucuk.pdf"
    small.write_bytes(b"%PDF kucuk")
    result = email_sender.send_document_email(["a@b.com"], "konu", "gövde", str(small), "kucuk.pdf")

    assert result["success"] is True
    msg = sent["payload"]["message"]
    assert [a["name"] for a in msg["attachments"]] == ["kucuk.pdf"]
    assert "ek limitini" not in msg["body"]["content"]
