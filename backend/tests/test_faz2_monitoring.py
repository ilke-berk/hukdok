"""Faz 2-A testleri: derin /healthz + süreç içi sağlık sinyalleri (health.py).

Kapsam:
- health.evaluate: durum eşlemesi (ok/degraded/unhealthy ↔ 200/503) — saf fonksiyon
- sinyal kayıtları: Gemini hata penceresi (1 saat), Graph token yaş/başarısızlık
- /healthz ucu: DB kontrolü monkeypatch'lenerek 200/503 + TTL cache davranışı
- nginx.conf bekçisi: container nginx'te `location = /healthz` var (SPA
  try_files'ın sağlık ucunu yutup körlük yaratmasının kalıcı düzeltmesi)
"""
import time
from pathlib import Path

import pytest

import health

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


# Sinyal + cache sıfırlama her testten önce conftest'teki autouse
# _clean_health_signals ile yapılır; buradaki helper yalnız test İÇİNDE
# cache tazelemek içindir (ör. DB'nin geri gelmesini simüle etmek).
def _reset_healthz_cache():
    import api

    with api._healthz_lock:
        api._healthz_cache.update(at=0.0, payload=None, code=200)


# ─── health.evaluate (saf fonksiyon) ─────────────────────────────────────────

def test_evaluate_ok():
    payload, code = health.evaluate(db_ok=True, version="abc1234")
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["version"] == "abc1234"  # deploy.sh kapısı kök seviyede bekler
    assert payload["checks"]["db"] == "ok"
    assert payload["checks"]["gemini_errors_last_hour"] == 0
    assert payload["checks"]["graph_token_age_seconds"] is None


def test_evaluate_db_fail_is_unhealthy_503():
    payload, code = health.evaluate(db_ok=False, version="dev")
    assert code == 503
    assert payload["status"] == "unhealthy"
    assert payload["checks"]["db"] == "fail"


def test_evaluate_gemini_error_is_degraded_200():
    health.record_gemini_error()
    payload, code = health.evaluate(db_ok=True, version="dev")
    # Degraded görünürlük sinyalidir; 503 olsaydı Gemini kesintisi konteyneri
    # "unhealthy" işaretler ve uptime alarmı yanlış yere öterdi.
    assert code == 200
    assert payload["status"] == "degraded"
    assert payload["checks"]["gemini_errors_last_hour"] == 1


def test_evaluate_gemini_errors_outside_window_pruned():
    old = time.time() - (health.GEMINI_ERROR_WINDOW_SECONDS + 60)
    health._gemini_error_times.append(old)  # pencere dışı hatayı doğrudan enjekte
    payload, code = health.evaluate(db_ok=True, version="dev")
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["gemini_errors_last_hour"] == 0


def test_evaluate_graph_fail_after_ok_is_degraded():
    health.record_graph_token_ok()
    health.record_graph_token_fail()
    payload, code = health.evaluate(db_ok=True, version="dev")
    assert code == 200
    assert payload["status"] == "degraded"
    assert payload["checks"]["graph_token_last_fail_age_seconds"] is not None


def test_evaluate_graph_ok_after_fail_recovers():
    health.record_graph_token_fail()
    health.record_graph_token_ok()
    payload, _ = health.evaluate(db_ok=True, version="dev")
    assert payload["status"] == "ok"
    assert payload["checks"]["graph_token_age_seconds"] is not None
    assert payload["checks"]["graph_token_age_seconds"] >= 0


def test_db_fail_wins_over_degraded_signals():
    health.record_gemini_error()
    payload, code = health.evaluate(db_ok=False, version="dev")
    assert code == 503
    assert payload["status"] == "unhealthy"


# ─── /healthz ucu ────────────────────────────────────────────────────────────

def _client():
    # `with` bloğu bilinçli YOK: lifespan (init_db, scheduler, thread'ler)
    # çalışmasın; healthz'in lifespan'a ihtiyaç duymaması istenen garanti.
    from starlette.testclient import TestClient

    from api import app

    return TestClient(app)


def test_healthz_db_ok_returns_200(monkeypatch):
    import api

    monkeypatch.setattr(api, "_healthz_db_ok", lambda: True)
    r = _client().get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["checks"]["db"] == "ok"


def test_healthz_db_fail_returns_503(monkeypatch):
    import api

    monkeypatch.setattr(api, "_healthz_db_ok", lambda: False)
    r = _client().get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["db"] == "fail"


def test_healthz_ttl_cache_prevents_probe_storm(monkeypatch):
    import api

    calls = {"n": 0}

    def counting_db_ok():
        calls["n"] += 1
        return True

    monkeypatch.setattr(api, "_healthz_db_ok", counting_db_ok)
    client = _client()
    for _ in range(20):
        assert client.get("/healthz").status_code == 200
    # TTL (10 sn) içinde tek canlı DB kontrolü: compose + uptime check +
    # deploy kapısı üst üste yoklarsa DB'ye yalnız ilki iner.
    assert calls["n"] == 1


def test_healthz_cached_failure_recovers_after_reset(monkeypatch):
    import api

    monkeypatch.setattr(api, "_healthz_db_ok", lambda: False)
    client = _client()
    assert client.get("/healthz").status_code == 503
    # DB döndü: cache tazelenince (testte reset ile simüle) 200'e dönmeli
    monkeypatch.setattr(api, "_healthz_db_ok", lambda: True)
    _reset_healthz_cache()
    assert client.get("/healthz").status_code == 200


# ─── konfig bekçileri ────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (REPO_ROOT / "nginx.conf").exists(),
    reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)",
)
def test_container_nginx_proxies_healthz():
    src = (REPO_ROOT / "nginx.conf").read_text(encoding="utf-8")
    assert "location = /healthz" in src, (
        "container nginx'te exact-match /healthz location olmalı; yoksa SPA "
        "try_files index.html döndürür ve uptime check backend ölümünü görmez"
    )
    assert "proxy_pass http://backend:8001/healthz" in src
