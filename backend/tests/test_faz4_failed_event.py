"""Faz 4-B (G001): analiz akışının "failed" terminal olayı.

Kilitlenen davranışlar:
  1. `analyze_file_generator`'ın nihai başarısızlık yolları artık varsayılan
     veriyle `complete` DEĞİL, `_failed_event` sözleşmesiyle `failed` döner.
  2. `error_kod` etiketleri hata tipine doğru eşlenir.
  3. Log sözleşmesi: `failed` üretimi YENİ ERROR satırı eklemez.
  4. /process passthrough'u `failed`'i değiştirmeden iletir; counter_task
     iptal edilir, PROCESS_CACHE yazılmaz, temp dosya silinir.
  5. Geçiş şimi: dönüşüm adımları intake (case_intake_analyzer) için ESKİ
     default-data'lı `complete` olayını üretmeyi sürdürür.

conftest sözleşmesi gereği ağa/DB'ye çıkılmaz; Gemini çağrısına hiç gelinmez
(adım fonksiyonları monkeypatch'lenir).
"""
import asyncio
import io
import json
import os
import threading
from typing import Any, Dict, List

import pytest
from google.genai import errors as genai_errors

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import analyzer  # noqa: E402
import gemini_client  # noqa: E402


def _client_error(code: int, message: str = "hata") -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"message": message, "status": "X"}})


def _server_error(code: int, message: str = "hata") -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": message, "status": "X"}})


def _drive(file_path: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """analyze_file_generator'ı sonuna kadar sürer, olayları döndürür."""

    async def _run():
        return [event async for event in analyzer.analyze_file_generator(file_path, **kwargs)]

    return asyncio.run(_run())


def _assert_failed_contract(event: Dict[str, Any], error_kod: str) -> None:
    """Terminal olayın dondurulmuş sözleşmeye birebir uyduğunu doğrular."""
    assert set(event) == {"status", "error_ozet", "error_kod"}   # process_id/data YOK
    assert event["status"] == "failed"
    assert event["error_kod"] == error_kod
    assert isinstance(event["error_ozet"], str) and event["error_ozet"].strip()


def _assert_terminal_failed(events: List[Dict[str, Any]], error_kod: str) -> Dict[str, Any]:
    """`failed` SON olaydır ve akışta hiç `complete` geçmez."""
    assert [e for e in events if e["status"] == "complete"] == []
    _assert_failed_contract(events[-1], error_kod)
    return events[-1]


@pytest.fixture()
def pdf_ready(monkeypatch, tmp_path):
    """Akışı Gemini çağrısının hemen öncesine kadar getirir (ağ/PDF I/O yok)."""
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    # Metin 50 karakterden kısa → ön çıkarıcılar (DB/liste araması) atlanır
    monkeypatch.setattr(analyzer, "is_scanned_pdf", lambda path: (False, "kisa"))
    monkeypatch.setattr(analyzer.pdf_utils, "extract_key_pages", lambda path: path)
    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4\ntest\n")
    return str(pdf)


def _raise_at_prompt_build(monkeypatch, exc: BaseException) -> None:
    """try bloğunun içinden (Gemini adımından önce) hata fırlatır."""

    def _boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(analyzer, "_build_prompt_and_config", _boom)


# ── Sözleşme yardımcıları ────────────────────────────────────────────────────


def test_failed_event_shape_is_frozen():
    event = analyzer._failed_event("Mesaj", "gemini_blocked")
    assert event == {"status": "failed", "error_ozet": "Mesaj", "error_kod": "gemini_blocked"}
    # Varsayılan etiket
    assert analyzer._failed_event("Mesaj")["error_kod"] == "analysis_error"


def test_failed_event_contract_documented_in_docstring():
    """Sözleşme koddaki docstring'de belgeli (frontend'le ortak referans)."""
    doc = analyzer._failed_event.__doc__ or ""
    for token in ('"status": "failed"', "error_ozet", "error_kod",
                  "gemini_saturated", "gemini_blocked", "gemini_truncated",
                  "pdf_page_limit", "analysis_error"):
        assert token in doc
    # G010: nihai başarısızlıkta WARNING loglayan ön-koşul yolları belgeli
    assert "İSTİSNA" in doc and "WARNING" in doc


def test_api_error_kod_mapping():
    assert analyzer._api_error_kod(gemini_client.GeminiCircuitOpenError("m", 42.0)) == "gemini_saturated"
    assert analyzer._api_error_kod(_client_error(429)) == "gemini_saturated"
    assert analyzer._api_error_kod(_server_error(503)) == "gemini_saturated"
    assert analyzer._api_error_kod(_server_error(500)) == "gemini_saturated"
    # Kota/yetki doygunluk değildir
    assert analyzer._api_error_kod(_client_error(403)) == "analysis_error"
    assert analyzer._api_error_kod(RuntimeError("bilinmez")) == "analysis_error"
    # Eski string arayüzü (geriye uyum) — _api_error_ozet ile aynı sınıflandırma
    assert analyzer._api_error_kod("429 RESOURCE_EXHAUSTED") == "gemini_saturated"


# ── Ön koşul yolları: artık default-data'lı "complete" yok ───────────────────


def test_missing_api_key_yields_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "")
    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    event = _assert_terminal_failed(_drive(str(pdf)), "analysis_error")
    assert "API anahtarı" in event["error_ozet"]


def test_vanished_file_yields_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    event = _assert_terminal_failed(_drive(str(tmp_path / "yok.pdf")), "analysis_error")
    assert "bulunamadı" in event["error_ozet"]


def test_udf_conversion_failure_yields_failed(monkeypatch, tmp_path):
    import udf_converter

    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")

    def _boom(path, *args, **kwargs):
        raise RuntimeError("bozuk udf")

    monkeypatch.setattr(udf_converter, "convert_udf_to_pdf", _boom)
    udf = tmp_path / "tensip.udf"
    udf.write_bytes(b"PK\x03\x04")

    events = _drive(str(udf))
    event = _assert_terminal_failed(events, "analysis_error")
    assert event["error_ozet"] == "UDF dönüşüm hatası: bozuk udf"


def test_format_conversion_failure_yields_failed(monkeypatch, tmp_path):
    from pdf import format_converter

    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")

    def _boom(path, *args, **kwargs):
        raise RuntimeError("dönüştürücü yok")

    monkeypatch.setattr(format_converter, "ensure_pdf", _boom)
    docx = tmp_path / "dilekce.docx"
    docx.write_bytes(b"PK\x03\x04")

    events = _drive(str(docx))
    event = _assert_terminal_failed(events, "analysis_error")
    assert event["error_ozet"].startswith("Dosya dönüşüm hatası (.docx)")


# ── Mod kararı (_step_decide_mode): nihai hatalar "failed" ──────────────────
# G010: bu adım eskiden default-data'lı `status:"error"` üretiyordu; sözleşme
# dışıydı ve `error_kod` telemetrisi kayıptı.


def _make_pdf(path, pages: int) -> str:
    """`pages` sayfalık, metin dolu gerçek bir PDF üretir (stub yok)."""
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Sayfa {i + 1} icerigi. " * 20)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_page_limit_yields_failed_with_own_kod(monkeypatch, tmp_path):
    """MAX_PDF_PAGES aşımı → `pdf_page_limit`. Uçtan uca gerçek pdf_utils yolu.

    Sayfa kırpma (extract_key_pages) 4 sayfayı 3'e indirir; limit 2 olduğu için
    kırpma sonrası da aşılır — gerçek akışta bu yolun ULAŞILABİLİR olduğunun
    kanıtı (eski `except PdfPageLimitError` dalı ana try'da ölüydü).
    """
    from pdf import pdf_utils

    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(pdf_utils, "MAX_PDF_PAGES", 2)

    events = _drive(_make_pdf(tmp_path / "kalin.pdf", 4))

    event = _assert_terminal_failed(events, "pdf_page_limit")
    assert "Maksimum 2 sayfa" in event["error_ozet"]


def test_page_limit_keeps_single_error_log(monkeypatch, tmp_path, log_calls):
    """Log sözleşmesi: sayfa limiti nihai hatadır → TEK ERROR, ikinci eklenmez."""
    from pdf import pdf_utils

    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(pdf_utils, "MAX_PDF_PAGES", 2)

    _assert_terminal_failed(_drive(_make_pdf(tmp_path / "kalin.pdf", 4)), "pdf_page_limit")
    assert len(_levels(log_calls, "ERROR")) == 1


def test_pdf_parse_timeout_yields_failed(monkeypatch, tmp_path):
    """Ayrıştırma zaman aşımı da nihai → `failed` (eskiden `status:"error"`)."""
    import time as _time

    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(analyzer.pdf_utils, "extract_key_pages", lambda path: path)
    monkeypatch.setattr(analyzer.settings, "pdf_parse_timeout_seconds", 0.05)
    monkeypatch.setattr(analyzer, "is_scanned_pdf", lambda path: _time.sleep(1))

    pdf = tmp_path / "yavas.pdf"
    pdf.write_bytes(b"%PDF-1.4\ntest\n")

    event = _assert_terminal_failed(_drive(str(pdf)), "analysis_error")
    assert "zaman aşımına" in event["error_ozet"]


# ── Handler zinciri: her nihai hata kendi etiketiyle "failed" ────────────────


def test_file_not_found_handler_yields_failed(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, FileNotFoundError("gitti"))
    event = _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert "Dosya bulunamadı" in event["error_ozet"]


def test_json_decode_handler_yields_failed(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, json.JSONDecodeError("bozuk", "{", 0))
    event = _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert "çözümlenemedi" in event["error_ozet"]


def test_truncated_response_yields_gemini_truncated(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, analyzer.GeminiTruncatedError("MAX_TOKENS"))
    event = _assert_terminal_failed(_drive(pdf_ready), "gemini_truncated")
    assert "uzunluk sınırına" in event["error_ozet"]


def test_blocked_response_yields_gemini_blocked(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, analyzer.GeminiBlockedError("SAFETY"))
    event = _assert_terminal_failed(_drive(pdf_ready), "gemini_blocked")
    assert "Güvenlik" in event["error_ozet"]


def test_empty_response_yields_analysis_error(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, analyzer.GeminiResponseError("boş"))
    event = _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert "boş yanıt" in event["error_ozet"]


def test_plain_value_error_yields_analysis_error(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, ValueError("beklenmedik"))
    event = _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert "işlenemedi" in event["error_ozet"]


def test_circuit_open_yields_gemini_saturated(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, gemini_client.GeminiCircuitOpenError("açık", 42.0))
    event = _assert_terminal_failed(_drive(pdf_ready), "gemini_saturated")
    assert "devre dışı" in event["error_ozet"]


def test_rate_limit_yields_gemini_saturated(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, _client_error(429))
    event = _assert_terminal_failed(_drive(pdf_ready), "gemini_saturated")
    assert "Rate Limit" in event["error_ozet"]


def test_unavailable_yields_gemini_saturated(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, _server_error(503))
    _assert_terminal_failed(_drive(pdf_ready), "gemini_saturated")


def test_unknown_exception_yields_analysis_error(monkeypatch, pdf_ready):
    _raise_at_prompt_build(monkeypatch, RuntimeError("bilinmez"))
    event = _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert "teknik bir sorun" in event["error_ozet"]


# ── Log sözleşmesi: "failed" YENİ ERROR satırı eklemez ───────────────────────


@pytest.fixture()
def log_calls(monkeypatch):
    calls: List[tuple] = []
    monkeypatch.setattr(
        analyzer.TechnicalLogger,
        "log",
        staticmethod(lambda level, message, *a, **kw: calls.append((level, message))),
    )
    return calls


def _levels(calls: List[tuple], level: str) -> List[str]:
    return [message for lvl, message in calls if lvl == level]


def test_failed_adds_no_error_log_when_path_logs_warning(monkeypatch, tmp_path, log_calls):
    """API anahtarı yok yolu WARNING'di — `failed` bunu ERROR'a yükseltmez."""
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "")
    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    _assert_terminal_failed(_drive(str(pdf)), "analysis_error")
    assert _levels(log_calls, "ERROR") == []
    assert len(_levels(log_calls, "WARNING")) == 1


def test_failed_keeps_single_error_log_on_final_failure(monkeypatch, pdf_ready, log_calls):
    """Nihai başarısızlıkta TEK ERROR (handler'ınki) — `failed` ikinciyi eklemez."""
    _raise_at_prompt_build(monkeypatch, RuntimeError("bilinmez"))
    _assert_terminal_failed(_drive(pdf_ready), "analysis_error")
    assert len(_levels(log_calls, "ERROR")) == 1


# ── Geçiş şimi: intake akışı ESKİ olayı görmeye devam eder ───────────────────


def test_conversion_steps_keep_legacy_complete_for_intake(monkeypatch, tmp_path):
    """case_intake_analyzer bu adımları paylaşır ve `complete`i hata mesajına
    çevirir; bayraksız çağrıda eski olay birebir korunmalı."""
    import udf_converter

    def _boom(path, *args, **kwargs):
        raise RuntimeError("bozuk udf")

    monkeypatch.setattr(udf_converter, "convert_udf_to_pdf", _boom)
    udf = tmp_path / "tensip.udf"
    udf.write_bytes(b"PK\x03\x04")

    # intake'in kurduğu state sözlüğü (legacy_complete_on_error ANAHTARI YOK)
    state = {"file_path": str(udf), "temp_pdf_from_udf": None, "failed": False}

    async def _run():
        loop = asyncio.get_running_loop()
        return [e async for e in analyzer._step_udf_conversion(state, "hash", {}, loop)]

    events = asyncio.run(_run())
    assert events[-1]["status"] == "complete"
    assert events[-1]["data"]["ozet"] == "UDF dönüşüm hatası: bozuk udf"
    assert state["failed"] is True


# ── /process passthrough ─────────────────────────────────────────────────────


@pytest.fixture()
def process_app(monkeypatch):
    """/process route'u: analyzer + counter + case_matcher fake'lenir."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import case_matcher
    from managers import counter_manager
    from dependencies import get_current_user
    from routes import processing

    monkeypatch.setattr(case_matcher, "find_matching_case", lambda *a, **kw: None)

    counter_released = threading.Event()

    class _FakeCounter:
        def __init__(self, value):
            self.value = value
            self.calls = 0

        def reserve_next_counter(self):
            self.calls += 1
            if self.value is None:
                # Analiz "complete"e ulaşmazsa iptal edilecek: iş parçacığı
                # testin sonuna kadar bloklu kalır (gerçek SharePoint gecikmesi)
                counter_released.wait(timeout=5)
                return "GEC______"
            return self.value

    state = {"counter": _FakeCounter("OFS-1")}
    monkeypatch.setattr(counter_manager, "get_counter_manager", lambda: state["counter"])

    # PROCESS_CACHE.set çağrıldı mı? (failed yolunda çağrılmamalı)
    cache_sets: List[tuple] = []
    monkeypatch.setattr(
        processing.PROCESS_CACHE, "set", lambda key, payload: cache_sets.append((key, payload))
    )

    # counter_task gerçekten iptal ediliyor mu?
    created: List[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def _spy_create_task(coro, **kwargs):
        task = real_create_task(coro, **kwargs)
        if getattr(coro, "__name__", "") == "fetch_counter":
            created.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", _spy_create_task)

    app = FastAPI()
    app.include_router(processing.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "test@example.com"}

    class _Harness:
        def __init__(self):
            self.client = TestClient(app)
            self.counter_tasks = created
            self.cache_sets = cache_sets

        def use_counter(self, value):
            state["counter"] = _FakeCounter(value)

        def post(self):
            return self.client.post(
                "/process",
                files={"file": ("belge.pdf", io.BytesIO(b"%PDF-1.4\ntest\n"), "application/pdf")},
            )

    try:
        yield _Harness()
    finally:
        counter_released.set()


def _events(resp) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in resp.text.strip().splitlines()]


def test_process_passes_failed_through_unchanged(monkeypatch, process_app):
    seen = {}

    async def fake_generator(file_path, file_hash=None, process_id=None, preset_belge_turu_kodu=None):
        seen["temp_path"] = file_path
        yield {"status": "info", "message": "başladı"}
        yield analyzer._failed_event("Servis doygun. (Kod: ab12cd34)", "gemini_saturated")

    monkeypatch.setattr(analyzer, "analyze_file_generator", fake_generator)
    process_app.use_counter(None)   # complete gelmeyecek → counter await edilmemeli

    resp = process_app.post()
    assert resp.status_code == 200
    events = _events(resp)

    assert events[0]["status"] == "info"
    # Passthrough: olay AYNEN iletilir — process_id/data/_api_benchmark eklenmez
    assert events[-1] == {
        "status": "failed",
        "error_ozet": "Servis doygun. (Kod: ab12cd34)",
        "error_kod": "gemini_saturated",
    }
    # PROCESS_CACHE yazılmadı, temp dosya silindi
    assert process_app.cache_sets == []
    assert not os.path.exists(seen["temp_path"])
    # counter_task finally'de iptal edildi (sarkan task yok)
    assert len(process_app.counter_tasks) == 1
    assert process_app.counter_tasks[0].cancelled()


def test_process_complete_path_still_carries_process_id(monkeypatch, process_app):
    async def fake_generator(file_path, file_hash=None, process_id=None, preset_belge_turu_kodu=None):
        yield {"status": "complete", "data": {"esas_no": "2024/1"}, "full_pdf_path": file_path}

    monkeypatch.setattr(analyzer, "analyze_file_generator", fake_generator)

    resp = process_app.post()
    final = _events(resp)[-1]
    assert final["status"] == "complete"
    assert final["process_id"]
    assert final["data"]["ofis_dosya_no"] == "OFS-1"
    assert len(process_app.cache_sets) == 1
