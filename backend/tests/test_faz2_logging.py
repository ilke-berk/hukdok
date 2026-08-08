"""Faz 2-B testleri: merkezi loglama (dictConfig + JSON formatter + request-id).

Kapsam:
- JsonFormatter: zorunlu alanlar, Türkçe karakter (ensure_ascii=False), extra
  alanların geçişi, exc_info → exception alanı
- RequestIdFilter + contextvar damgası
- configure_logging: idempotans, LOG_FORMAT=json seçimi, uvicorn.access susturma
- RequestIdMiddleware (saf ASGI): kimlik üretimi/korunması/sanitizasyonu,
  erişim satırı + muaf yollar, istisna yolunda ERROR + re-raise
- Gerçek app entegrasyonu: yanıt X-Request-ID taşır (middleware kayıtlı)
- Bekçiler: backend'de modül seviyesinde basicConfig kalmadı, compose'da
  LOG_FORMAT=json var
"""
import json
import logging
import sys
from pathlib import Path

import pytest

import logging_setup
from logging_setup import (
    ACCESS_LOG_EXEMPT_PATHS,
    JsonFormatter,
    RequestIdFilter,
    RequestIdMiddleware,
    configure_logging,
    request_id_var,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _record(msg="merhaba dünya", level=logging.INFO, exc_info=None, **extra):
    rec = logging.LogRecord(
        "test.logger", level, __file__, 42, msg, (), exc_info
    )
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


# ─── JsonFormatter ───────────────────────────────────────────────────────────

def test_json_formatter_required_fields():
    out = json.loads(JsonFormatter().format(_record()))
    assert out["severity"] == "INFO"
    assert out["logger"] == "test.logger"
    assert out["message"] == "merhaba dünya"
    assert out["request_id"] == "-"  # filter'dan geçmedi → varsayılan
    assert out["timestamp"].endswith("+00:00")  # UTC, RFC3339
    assert ":" in out["location"]


def test_json_formatter_turkish_not_escaped():
    line = JsonFormatter().format(_record(msg="ğüşiöçİĞÜŞÖÇ"))
    # ensure_ascii=False: GCP/log okuyucuda ğ çorbası olmasın
    assert "ğüşiöçİĞÜŞÖÇ" in line
    assert "\\u" not in line


def test_json_formatter_extra_fields_pass_through():
    out = json.loads(
        JsonFormatter().format(_record(status_code=200, duration_ms=12))
    )
    assert out["status_code"] == 200
    assert out["duration_ms"] == 12


def test_json_formatter_exception_field():
    try:
        raise ValueError("patladı")
    except ValueError:
        rec = _record(msg="hata", level=logging.ERROR, exc_info=sys.exc_info())
    out = json.loads(JsonFormatter().format(rec))
    assert out["severity"] == "ERROR"
    assert "ValueError: patladı" in out["exception"]
    # Traceback tek JSON satırında kalmalı (satır başına bir nesne garantisi)
    assert "\n" not in JsonFormatter().format(rec)


def test_json_formatter_non_serializable_extra_uses_str():
    out = json.loads(JsonFormatter().format(_record(weird=Path("/tmp"))))
    assert isinstance(out["weird"], str)


# ─── RequestIdFilter / contextvar ────────────────────────────────────────────

def test_request_id_filter_stamps_from_contextvar():
    token = request_id_var.set("abc123def456")
    try:
        rec = _record()
        assert RequestIdFilter().filter(rec) is True
        assert rec.request_id == "abc123def456"
    finally:
        request_id_var.reset(token)
    rec2 = _record()
    RequestIdFilter().filter(rec2)
    assert rec2.request_id == "-"


# ─── configure_logging ───────────────────────────────────────────────────────

def test_configure_logging_idempotent_single_stdout_handler():
    configure_logging()
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.INFO
    # request_id filtresi handler'da: TÜM kayıtlar damgalanır
    assert any(isinstance(f, RequestIdFilter) for f in root.handlers[0].filters)


def test_configure_logging_json_format_via_env(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging()
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)
    # Geri al: sonraki testler text varsayılanıyla koşsun
    monkeypatch.delenv("LOG_FORMAT")
    configure_logging()
    assert not isinstance(
        logging.getLogger().handlers[0].formatter, JsonFormatter
    )


def test_configure_logging_silences_uvicorn_access():
    configure_logging()
    access = logging.getLogger("uvicorn.access")
    # Erişim satırını RequestIdMiddleware üretir; uvicorn'unki kimliksiz
    # kopya olurdu → WARNING altı akmaz
    assert access.level == logging.WARNING
    assert access.propagate is False


# ─── RequestIdMiddleware (saf ASGI) ──────────────────────────────────────────

def _mw_client(seen=None, app=None):
    from starlette.testclient import TestClient

    if app is None:
        async def app(scope, receive, send):  # noqa: ANN001
            if seen is not None:
                seen["rid"] = request_id_var.get()
            await send(
                {"type": "http.response.start", "status": 200, "headers": []}
            )
            await send({"type": "http.response.body", "body": b"ok"})

    return TestClient(RequestIdMiddleware(app))


def test_middleware_generates_id_and_sets_contextvar():
    seen = {}
    r = _mw_client(seen).get("/foo")
    rid = r.headers["x-request-id"]
    assert len(rid) == 12 and all(c in "0123456789abcdef" for c in rid)
    # Downstream app istek sırasında AYNI kimliği contextvar'dan gördü
    assert seen["rid"] == rid


def test_middleware_fresh_id_per_request():
    client = _mw_client()
    first = client.get("/foo").headers["x-request-id"]
    second = client.get("/foo").headers["x-request-id"]
    assert first != second


def test_middleware_preserves_incoming_id():
    seen = {}
    r = _mw_client(seen).get("/foo", headers={"X-Request-ID": "gelen-id_1.2"})
    assert r.headers["x-request-id"] == "gelen-id_1.2"
    assert seen["rid"] == "gelen-id_1.2"


def test_middleware_sanitizes_hostile_incoming_id():
    r = _mw_client().get(
        "/foo", headers={"X-Request-ID": "abc 123<script>;{}"}
    )
    # Yalnız [A-Za-z0-9._-] kalır — header log satırına yazılıyor (injection)
    assert r.headers["x-request-id"] == "abc123script"


def test_middleware_access_log_line(caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        _mw_client().get("/api/deneme?q=1", headers={"X-Request-ID": "iz-42"})
    records = [r for r in caplog.records if r.name == "access"]
    assert len(records) == 1
    rec = records[0]
    assert rec.request_id == "iz-42"
    assert rec.method == "GET"
    assert rec.path == "/api/deneme"
    assert rec.status_code == 200
    assert rec.duration_ms >= 0
    assert "GET /api/deneme 200" in rec.getMessage()


def test_middleware_exempt_paths_produce_no_access_log(caplog):
    client = _mw_client()
    with caplog.at_level(logging.INFO, logger="access"):
        for path in ACCESS_LOG_EXEMPT_PATHS:
            r = client.get(path)
            # Muaf yol log üretmez ama kimlik başlığı yine de döner
            assert "x-request-id" in r.headers
    assert [r for r in caplog.records if r.name == "access"] == []


def test_middleware_exception_logs_error_and_reraises(caplog):
    async def boom(scope, receive, send):  # noqa: ANN001
        raise RuntimeError("kasıtlı patlama")

    client = _mw_client(app=boom)
    with caplog.at_level(logging.INFO, logger="access"):
        with pytest.raises(RuntimeError, match="kasıtlı patlama"):
            client.get("/patla", headers={"X-Request-ID": "hata-iz"})
    records = [r for r in caplog.records if r.name == "access"]
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.ERROR
    assert rec.request_id == "hata-iz"
    assert rec.status_code == 500
    assert rec.exc_info is not None  # traceback kimlikli satırda taşınır


def test_middleware_passes_non_http_scopes_through():
    # lifespan scope'u dokunulmadan geçmeli (uygulama başlatması kırılmasın)
    called = {}

    async def app(scope, receive, send):  # noqa: ANN001
        called["type"] = scope["type"]

    import asyncio

    asyncio.run(RequestIdMiddleware(app)({"type": "lifespan"}, None, None))
    assert called["type"] == "lifespan"


# ─── Gerçek app entegrasyonu ─────────────────────────────────────────────────

def test_api_responses_carry_request_id():
    # `with` bloğu bilinçli YOK: lifespan (init_db, scheduler) çalışmasın
    from starlette.testclient import TestClient

    from api import app

    client = TestClient(app)
    r = client.get("/healthz")
    assert "x-request-id" in r.headers
    # Gelen kimlik tam middleware yığınından (CORS/SlowAPI dahil) sağ çıkar
    r2 = client.get("/healthz", headers={"X-Request-ID": "e2e-iz-77"})
    assert r2.headers["x-request-id"] == "e2e-iz-77"


# ─── Bekçiler ────────────────────────────────────────────────────────────────

def test_no_basicconfig_left_in_backend():
    """Regresyon bekçisi: dağınık basicConfig geri sızmasın (Faz 2-B).

    Yeni modülde loglama ihtiyacı = logging.getLogger; yapılandırma yalnız
    logging_setup.configure_logging'de yaşar.
    """
    offenders = []
    for py in BACKEND_DIR.rglob("*.py"):
        rel = py.relative_to(BACKEND_DIR).as_posix()
        if rel.startswith(("tests/", "__pycache__")) or "/__pycache__/" in rel:
            continue
        if "logging.basicConfig(" in py.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert offenders == []


@pytest.mark.skipif(
    not (REPO_ROOT / "docker-compose.yml").exists(),
    reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)",
)
def test_compose_sets_json_log_format():
    src = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "LOG_FORMAT=json" in src, (
        "backend service'inde LOG_FORMAT=json olmalı; yoksa prod loglar text "
        "akar ve Faz 2-C'nin severity tabanlı GCP alarmları eşleşmez"
    )
