"""Faz 3-C: Gemini retry sınıflandırıcısı (kod bazlı) + finish_reason +
deadline bütçesi + devre kesici testleri.

conftest sözleşmesi gereği ağa çıkılmaz: SDK client'ı fake'lenir, hatalar
gerçek google-genai exception sınıflarıyla (ClientError/ServerError) üretilir.
Devre kesici saati gemini_client._monotonic dolaylamasından kontrol edilir.
"""
import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

# analyzer import'u GEMINI_MODEL_NAME yoksa ValueError fırlatır — app
# modüllerinden önce güvenli varsayılan (conftest DB/vault'u hallediyor).
os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import analyzer  # noqa: E402
import gemini_client  # noqa: E402
import health  # noqa: E402


def _client_error(code: int, message: str = "hata") -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"message": message, "status": "X"}})


def _server_error(code: int, message: str = "hata") -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": message, "status": "X"}})


class _FakeAioModels:
    """Sıradaki outcome'u döndürür/fırlatır; çağrı sayısını tutar."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_content(self, model=None, contents=None, config=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes):
        self.aio = SimpleNamespace(models=_FakeAioModels(outcomes))

    @property
    def calls(self):
        return self.aio.models.calls


@pytest.fixture
def no_sleep(monkeypatch):
    """Retry beklemelerini kaydedip atlar (test süresi + determinizm)."""
    sleeps = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return sleeps


def _use_fake_client(monkeypatch, fake):
    monkeypatch.setattr(analyzer, "get_gemini_client", lambda key=None: fake)


def _gemini_error_count() -> int:
    return health.signals_snapshot()["gemini_errors_last_hour"]


# ── Sınıflandırma: kod bazlı, string eşleme yok ──────────────────────────────


def test_classify_transient_api_codes():
    assert gemini_client.classify_transient(_client_error(429)) == "429"
    for code in (500, 502, 503, 504):
        assert gemini_client.classify_transient(_server_error(code)) == "server"
    # Kalıcı hatalar retry edilmez — mesaj içeriği ne derse desin
    assert gemini_client.classify_transient(_client_error(400, "429 yazan 400")) is None
    assert gemini_client.classify_transient(_client_error(403, "quota")) is None
    assert gemini_client.classify_transient(_client_error(404)) is None


def test_classify_transient_httpx_transport():
    assert gemini_client.classify_transient(httpx.ConnectError("ağ yok")) == "transport"
    assert gemini_client.classify_transient(httpx.ReadTimeout("yavaş")) == "transport"
    assert gemini_client.classify_transient(httpx.RemoteProtocolError("koptu")) == "transport"


def test_classify_transient_other_exceptions():
    assert gemini_client.classify_transient(ValueError("503 gibi görünen metin")) is None
    assert gemini_client.classify_transient(RuntimeError("unavailable")) is None


# ── Devre kesici birim testleri ──────────────────────────────────────────────


def test_circuit_opens_at_threshold_per_model(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(gemini_client, "_monotonic", lambda: clock["now"])

    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD - 1):
        assert gemini_client.circuit_record_failure("model-a") is False
    assert gemini_client.circuit_open_remaining("model-a") == 0.0

    assert gemini_client.circuit_record_failure("model-a") is True
    remaining = gemini_client.circuit_open_remaining("model-a")
    assert remaining == pytest.approx(gemini_client.CIRCUIT_OPEN_SECONDS)
    # Model-başına izolasyon: başka model etkilenmez
    assert gemini_client.circuit_open_remaining("model-b") == 0.0


def test_circuit_half_open_and_success_reset(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(gemini_client, "_monotonic", lambda: clock["now"])

    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("m")
    assert gemini_client.circuit_open_remaining("m") > 0

    # Açık süre dolunca çağrılara izin verilir (yarı-açık)...
    clock["now"] += gemini_client.CIRCUIT_OPEN_SECONDS + 1
    assert gemini_client.circuit_open_remaining("m") == 0.0
    # ...ama sayaç sıfırlanmadığından ilk 429/503 kesiciyi ANINDA yeniden açar
    assert gemini_client.circuit_record_failure("m") is True
    assert gemini_client.circuit_open_remaining("m") > 0

    # Başarı tam kapatır: sayaç sıfır, tek hata yeniden açamaz
    gemini_client.circuit_record_success("m")
    assert gemini_client.circuit_open_remaining("m") == 0.0
    assert gemini_client.circuit_record_failure("m") is False
    assert gemini_client.circuit_open_remaining("m") == 0.0


# ── _gemini_call_with_retry: retry + health sözleşmesi ───────────────────────


def test_transient_503_retried_then_success(monkeypatch, no_sleep):
    resp = SimpleNamespace(text="ok")
    fake = _FakeClient([_server_error(503), _server_error(503), resp])
    _use_fake_client(monkeypatch, fake)

    stats = {"retry_count": 0, "retry_wait_ms": 0}
    out = asyncio.run(
        analyzer._gemini_call_with_retry(None, "içerik", stats=stats, model="m-basari")
    )
    assert out is resp
    assert fake.calls == 3
    assert stats["retry_count"] == 2
    # 503 kısa backoff: base 1s → ilk bekleme [1, 2) — 429'un 5s tabanı DEĞİL
    assert 1.0 <= no_sleep[0] < 2.0
    # Geçici hatalar atlatıldı → healthz sayacına İŞLENMEZ (Faz 2-A sözleşmesi)
    assert _gemini_error_count() == 0
    # Başarı kesici sayacını sıfırladı: eşik-1 yeni hata kesiciyi açamaz
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD - 1):
        gemini_client.circuit_record_failure("m-basari")
    assert gemini_client.circuit_open_remaining("m-basari") == 0.0


def test_429_uses_long_backoff(monkeypatch, no_sleep):
    resp = SimpleNamespace(text="ok")
    fake = _FakeClient([_client_error(429), resp])
    _use_fake_client(monkeypatch, fake)

    asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-429"))
    assert 5.0 <= no_sleep[0] < 10.0


def test_transport_error_retried(monkeypatch, no_sleep):
    resp = SimpleNamespace(text="ok")
    fake = _FakeClient([httpx.ConnectError("ağ koptu"), resp])
    _use_fake_client(monkeypatch, fake)

    out = asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-net"))
    assert out is resp
    assert fake.calls == 2
    assert _gemini_error_count() == 0


def test_permanent_error_fails_immediately(monkeypatch, no_sleep):
    fake = _FakeClient([_client_error(400)])
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(genai_errors.ClientError):
        asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-400"))
    assert fake.calls == 1  # retry yok
    assert no_sleep == []
    assert _gemini_error_count() == 1  # nihai başarısızlık → tek kayıt
    # 400 doygunluk sinyali değildir → kesici beslenmez
    assert gemini_client.circuit_open_remaining("m-400") == 0.0


def test_retry_budget_exhaustion_records_single_final_error(monkeypatch, no_sleep):
    err = _server_error(503)
    fake = _FakeClient([err, err])
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(genai_errors.ServerError):
        asyncio.run(
            analyzer._gemini_call_with_retry(None, "x", max_retries=1, model="m-son")
        )
    assert fake.calls == 2  # ilk deneme + 1 retry
    assert _gemini_error_count() == 1


# ── Deadline bütçesi ─────────────────────────────────────────────────────────


def test_deadline_budget_stops_retries(monkeypatch, no_sleep):
    # Bütçe 0 → ilk geçici hatada bekleme başlatılamaz, nihai hata döner
    monkeypatch.setattr(analyzer, "GEMINI_RETRY_DEADLINE_SECONDS", 0.0)
    err = _server_error(503)
    fake = _FakeClient([err, err, err])
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(genai_errors.ServerError):
        asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-butce"))
    assert fake.calls == 1  # ikinci deneme hiç başlamadı
    assert no_sleep == []
    assert _gemini_error_count() == 1


def test_deadline_budget_stays_under_nginx_window():
    # Bütçe + tek deneme HTTP tavanı, container nginx 300 sn'nin altında kalmalı.
    # Faz 5-A: değerlerin evi config/settings.py — bekçi settings üzerinden okur
    # ve modül alias'larının settings'le eşzamanlı kaldığını da doğrular.
    from config.settings import settings

    assert analyzer.GEMINI_RETRY_DEADLINE_SECONDS == settings.gemini_retry_deadline_seconds
    assert gemini_client.GEMINI_HTTP_TIMEOUT_MS == settings.gemini_http_timeout_ms
    worst_case = (
        settings.gemini_retry_deadline_seconds + settings.gemini_http_timeout_ms / 1000
    )
    assert worst_case < settings.request_time_budget_seconds == 300


# ── Devre kesici entegrasyonu ────────────────────────────────────────────────


def test_call_fast_fails_when_circuit_open(monkeypatch, no_sleep):
    fake = _FakeClient([])
    _use_fake_client(monkeypatch, fake)
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("m-acik")

    with pytest.raises(gemini_client.GeminiCircuitOpenError):
        asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-acik"))
    assert fake.calls == 0  # Gemini'ye hiç gidilmedi
    # Hızlı-fail NİHAİ başarısızlıktır: kullanıcıya yansır → healthz'e işlenir
    assert _gemini_error_count() == 1


def test_call_proceeds_for_other_model_when_circuit_open(monkeypatch, no_sleep):
    resp = SimpleNamespace(text="ok")
    fake = _FakeClient([resp])
    _use_fake_client(monkeypatch, fake)
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("m-diger")

    out = asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-temiz"))
    assert out is resp
    assert fake.calls == 1


def test_consecutive_saturation_across_calls_opens_circuit(monkeypatch, no_sleep):
    # Art arda ÇAĞRILAR (retry'lar dahil) doygunluk sayacını besler: eşik kadar
    # 429/503 sonrası kesici açılır, sonraki çağrı Gemini'ye gitmeden düşer.
    err = _server_error(503)
    n = gemini_client.CIRCUIT_FAILURE_THRESHOLD
    fake = _FakeClient([err] * n + [SimpleNamespace(text="asla dönmez")])
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(genai_errors.ServerError):
        asyncio.run(
            analyzer._gemini_call_with_retry(None, "x", max_retries=n - 1, model="m-seri")
        )
    assert fake.calls == n
    assert gemini_client.circuit_open_remaining("m-seri") > 0

    with pytest.raises(gemini_client.GeminiCircuitOpenError):
        asyncio.run(analyzer._gemini_call_with_retry(None, "x", model="m-seri"))
    assert fake.calls == n  # ek çağrı yok


# ── finish_reason okuma ──────────────────────────────────────────────────────


def _fake_response(text=None, finish=None, block=None):
    resp = SimpleNamespace(text=text)
    resp.candidates = (
        [SimpleNamespace(finish_reason=SimpleNamespace(name=finish))] if finish else []
    )
    resp.prompt_feedback = (
        SimpleNamespace(block_reason=SimpleNamespace(name=block)) if block else None
    )
    return resp


def test_ensure_text_returns_text_on_stop():
    resp = _fake_response(text='{"a": 1}', finish="STOP")
    assert analyzer._ensure_response_text(resp) == '{"a": 1}'


def test_max_tokens_reported_as_truncation_not_safety():
    # Kısmi metin gelmiş olsa bile MAX_TOKENS "kesildi" olarak raporlanır
    resp = _fake_response(text='{"yarim', finish="MAX_TOKENS")
    with pytest.raises(analyzer.GeminiTruncatedError):
        analyzer._ensure_response_text(resp)
    # GeminiBlockedError DEĞİL — güvenlik filtresi teşhisi konmaz
    with pytest.raises(analyzer.GeminiResponseError) as exc_info:
        analyzer._ensure_response_text(resp)
    assert not isinstance(exc_info.value, analyzer.GeminiBlockedError)


def test_safety_finish_reason_reported_as_blocked():
    resp = _fake_response(text=None, finish="SAFETY")
    with pytest.raises(analyzer.GeminiBlockedError):
        analyzer._ensure_response_text(resp)
    resp2 = _fake_response(text=None, finish="PROHIBITED_CONTENT")
    with pytest.raises(analyzer.GeminiBlockedError):
        analyzer._ensure_response_text(resp2)


def test_prompt_block_reason_reported_as_blocked():
    resp = _fake_response(text=None, block="PROHIBITED_CONTENT")
    with pytest.raises(analyzer.GeminiBlockedError):
        analyzer._ensure_response_text(resp)


def test_empty_response_without_reason_is_generic():
    resp = _fake_response(text=None)
    with pytest.raises(analyzer.GeminiResponseError) as exc_info:
        analyzer._ensure_response_text(resp)
    assert not isinstance(exc_info.value, analyzer.GeminiBlockedError)
    assert not isinstance(exc_info.value, analyzer.GeminiTruncatedError)


def test_response_error_is_valueerror_subclass():
    # analyze_file_generator except zinciri ValueError'dan ÖNCE yakalar; alt
    # sınıf olması eski davranışa güvenen kodu (except ValueError) kırmaz
    assert issubclass(analyzer.GeminiResponseError, ValueError)


# ── _api_error_ozet: kod bazlı kullanıcı mesajları ───────────────────────────


def test_api_error_ozet_code_based():
    assert "Rate Limit" in analyzer._api_error_ozet(_client_error(429, "x"), "id1")
    assert "geçici olarak kullanılamıyor" in analyzer._api_error_ozet(_server_error(503, "x"), "id2")
    # 500/502/504 de kod üzerinden geçici-servis mesajına düşer
    assert "geçici olarak kullanılamıyor" in analyzer._api_error_ozet(_server_error(502, "x"), "id3")
    assert "Erişim" in analyzer._api_error_ozet(_client_error(403, "x"), "id4")
    assert "teknik bir sorun" in analyzer._api_error_ozet(RuntimeError("bilinmez"), "id5")


def test_api_error_ozet_circuit_open_message():
    err = gemini_client.GeminiCircuitOpenError("m", 42.0)
    ozet = analyzer._api_error_ozet(err, "id6")
    assert "devre dışı" in ozet
    assert "1 dakika" in ozet


def test_api_error_ozet_string_fallback():
    # Eski string arayüzü korunur (geriye uyum)
    assert "Rate Limit" in analyzer._api_error_ozet("429 RESOURCE_EXHAUSTED", "id7")


# ── Soft-fail çağrı noktaları: email_sender + date_extractor ─────────────────


def test_email_guard_skips_when_circuit_open():
    import email_sender

    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("em-model")

    class _NeverCalled:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise AssertionError("kesici açıkken Gemini'ye gidilmemeli")

    out = email_sender._breaker_guarded_generate(_NeverCalled(), "em-model", "p")
    assert out is None
    # Gemini'ye gidilmedi → health sayacına İŞLENMEZ
    assert _gemini_error_count() == 0


def test_email_guard_feeds_breaker_on_saturation():
    import email_sender

    class _Always429:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise _client_error(429)

    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        with pytest.raises(genai_errors.ClientError):
            email_sender._breaker_guarded_generate(_Always429(), "em-m2", "p")
    assert gemini_client.circuit_open_remaining("em-m2") > 0


def test_email_guard_success_resets_and_returns_response():
    import email_sender

    resp = SimpleNamespace(text="gövde")

    class _Ok:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                return resp

    gemini_client.circuit_record_failure("em-m3")
    out = email_sender._breaker_guarded_generate(_Ok(), "em-m3", "p")
    assert out is resp
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD - 1):
        gemini_client.circuit_record_failure("em-m3")
    assert gemini_client.circuit_open_remaining("em-m3") == 0.0  # sayaç sıfırlanmıştı


def test_date_referee_skips_when_circuit_open(monkeypatch):
    from extractors import date_extractor

    monkeypatch.setattr(date_extractor, "get_model_name", lambda: "dt-model")
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("dt-model")

    def _no_client():
        raise AssertionError("kesici açıkken client bile istenmemeli")

    monkeypatch.setattr(date_extractor, "get_gemini_client", _no_client)
    assert date_extractor.ask_llm_referee("metin", []) is None
    assert _gemini_error_count() == 0
