"""Faz 1-A testleri: migrasyon adımı ayrıştırma + /healthz ucu.

Kapsam:
- migrate.py çıkış kodları — entrypoint'in fail-fast davranışının dayanağı
  (set -e, migrate.py 1 dönerse konteyner ayağa kalkmaz)
- api.py'de import-time migrasyon çağrısı YOK — uvicorn --workers N'e geçişte
  her worker'ın import sırasında DDL koşmasını engelleyen düzeltmenin bekçisi
- docker-entrypoint.sh migrate.py'yi uvicorn'dan ÖNCE çağırıyor
- /healthz: docker-compose healthcheck'in çağırdığı uç — lifespan (DB)
  gerektirmeden 200 döner ve rate limit'ten muaftır
"""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ─── migrate.py ──────────────────────────────────────────────────────────────

def test_migrate_main_success(monkeypatch):
    import database
    import migrate

    calls = {"n": 0}

    def fake_init_db():
        calls["n"] += 1

    monkeypatch.setattr(database, "init_db", fake_init_db)
    assert migrate.main() == 0
    assert calls["n"] == 1


def test_migrate_main_failure_returns_1(monkeypatch):
    import database
    import migrate

    def boom():
        raise RuntimeError("Migration failed for cases.xyz")

    monkeypatch.setattr(database, "init_db", boom)
    assert migrate.main() == 1


# ─── import-time DDL bekçileri ───────────────────────────────────────────────

def test_api_source_has_no_import_time_migration():
    src = (BACKEND_DIR / "api.py").read_text(encoding="utf-8")
    assert "check_and_migrate_tables" not in src, (
        "api.py import zamanında migrasyon çağırmamalı: migrasyon entrypoint'te "
        "migrate.py ile tek seferlik koşar; import-time DDL çoklu worker'da "
        "yarışa girer (Faz 1-A)"
    )


def test_entrypoint_runs_migrate_before_uvicorn():
    src = (BACKEND_DIR / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "python migrate.py" in src, "entrypoint migrate.py adımını kaybetmiş"
    # Komut satırlarına bak (yorumlardaki "uvicorn" kelimesine değil)
    assert src.index("python migrate.py") < src.index("exec uvicorn"), (
        "migrasyon adımı uvicorn'dan ÖNCE koşmalı"
    )


# ─── /healthz ────────────────────────────────────────────────────────────────

def _client():
    # `with` bloğu bilinçli YOK: lifespan (init_db, scheduler, thread'ler)
    # çalışmaz — healthz'in DB'siz 200 vermesi tam da istenen garanti.
    from starlette.testclient import TestClient
    from api import app

    return TestClient(app)


def test_healthz_returns_200_without_lifespan():
    r = _client().get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # version: imaja gömülen git SHA (APP_VERSION env); test ortamında env yok
    # → "dev" fallback'i. deploy.sh sağlık kapısı bu alanı SHA ile karşılaştırır.
    assert body["version"], "healthz 'version' alanı boş olmamalı"


def test_healthz_exempt_from_rate_limit():
    # Global limit 100/dk (api.py default_limits). Sağlık yoklaması hiçbir
    # koşulda 429 görmemeli: unhealthy işareti frontend depends_on'u ve deploy
    # sağlık kapısını (Faz 1-C) yanlış tetikler. 105 istek limitin üstüne çıkar;
    # exempt bozulursa 429'lar burada yakalanır.
    client = _client()
    statuses = {client.get("/healthz").status_code for _ in range(105)}
    assert statuses == {200}
