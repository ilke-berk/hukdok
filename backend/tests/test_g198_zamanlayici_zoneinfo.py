"""G198 bekçisi: zamanlayıcı pytz'siz, zoneinfo'lu; import hatası YUTULMAZ.

- (a) `api.py` kaynağında `pytz` importu yok (APScheduler 3.11 pytz'yi bağımlılıktan
  çıkardı; requirements'ta hiç olmadığı için dolaylı gelişi kesilince zamanlayıcı
  sessizce kapanırdı). Zamanlayıcı ve üç CronTrigger `ZoneInfo("Europe/Istanbul")`.
- (b) zamanlayıcı bloğunda `ImportError` → ERROR düzeyinde TEK kayıt (WARNING değil),
  istisna mesajı satırda; lifespan düşmez, telafi thread'leri başlamaz.
- (c) lider worker'da üç iş kayıtlı; başlamış zamanlayıcının `next_run_time`'ı TR
  saatiyle 00:00 / 02:30 / 06:00.

Zamanlayıcı kodu lifespan'in İÇİNDE kalmak zorunda (Faz 3-E / G085 / G097 AST
bekçileri onu orada arar) → testler gerçek lifespan'i, yan etkili dış çağrıları
susturarak koşturur. api modülü collection sırasında import edilir →
`configure_logging()` kök handler'ları caplog kurulmadan ÖNCE değiştirir.
"""
import ast
import asyncio
import logging
import re
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import api
import managers.activity_manager as activity_manager
import managers.seed_data as seed_data
import routes.processing as processing
import services.deadline_scanner as deadline_scanner
import services.singleton_lock as singleton_lock
import services.teslim_kutusu as teslim_kutusu
import services.upload_queue as upload_queue
import sharepoint.auth_graph as auth_graph

TR = ZoneInfo("Europe/Istanbul")
API_KAYNAK = Path(api.__file__).read_text(encoding="utf-8")
ZAMANLAYICI_ISLERI = {"daily_activity_report": (0, 0), "conversion_retry": (2, 30), "deadline_scan": (6, 0)}


@pytest.fixture
def sessiz_lifespan(monkeypatch, tmp_path):
    """Lifespan'i lider olarak koşturur; zamanlayıcı dışındaki yan etkiler susturulur.
    Telafi thread'lerinin hedefleri çağrı kaydeden no-op'lardır."""
    cagrilar: list[str] = []
    monkeypatch.setattr(api, "write_startup_log", lambda _msg: None)
    monkeypatch.setattr(api, "cache_manager", None)
    monkeypatch.setattr(api, "refresh_lists_background", lambda: None)
    monkeypatch.setattr(auth_graph, "check_client_secret_expiry", lambda: None)
    monkeypatch.setattr(singleton_lock, "try_acquire_leader", lambda: True)
    monkeypatch.setattr(seed_data, "seed_all_lists", lambda: None)
    monkeypatch.setattr(upload_queue, "start_upload_worker", lambda: None)
    monkeypatch.setattr(upload_queue, "stop_upload_worker", lambda: None)
    monkeypatch.setattr(processing, "_cleanup_process_cache", lambda: None)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(activity_manager, "catch_up_missed_reports", lambda: cagrilar.append("catch_up"))
    monkeypatch.setattr(deadline_scanner, "boot_catch_up_scan", lambda: cagrilar.append("scan"))
    monkeypatch.setattr(teslim_kutusu, "boot_toparla", lambda: cagrilar.append("teslim"))

    def _kos(icinde=None):
        app = SimpleNamespace(state=SimpleNamespace())

        async def _govde():
            async with api.lifespan(app):
                if icinde is not None:
                    icinde(app)

        asyncio.run(_govde())
        return app

    return _kos, cagrilar


def test_api_kaynaginda_pytz_yok():
    assert not re.search(r"^\s*(import pytz|from pytz\b)", API_KAYNAK, re.MULTILINE)
    assert "pytz." not in API_KAYNAK


def test_zamanlayici_zoneinfo_kullanir():
    assert "from zoneinfo import ZoneInfo" in API_KAYNAK
    cagrilar = [
        n for n in ast.walk(ast.parse(API_KAYNAK))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ZoneInfo"
    ]
    # BackgroundScheduler + üç CronTrigger, hepsi literal "Europe/Istanbul"
    assert len(cagrilar) == 4
    assert all(isinstance(c.args[0], ast.Constant) and c.args[0].value == "Europe/Istanbul" for c in cagrilar)


def test_import_hatasi_tek_error_olarak_loglanir(sessiz_lifespan, monkeypatch, caplog):
    kos, cagrilar = sessiz_lifespan
    # sys.modules'ta None → `from apscheduler.schedulers.background import ...` ImportError
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", None)
    with caplog.at_level(logging.INFO):
        app = kos()

    assert not hasattr(app.state, "scheduler")
    ilgili = [r for r in caplog.records if "Zamanlayıcı başlatılamadı" in r.getMessage()]
    assert len(ilgili) == 1
    assert ilgili[0].levelno == logging.ERROR
    assert "apscheduler.schedulers.background" in ilgili[0].getMessage()
    assert [r for r in caplog.records if r.levelno == logging.ERROR] == ilgili
    assert not [r for r in caplog.records if r.levelno == logging.WARNING and "apscheduler" in r.getMessage()]
    assert cagrilar == []  # zamanlayıcı kalkmadıysa telafi thread'leri de başlamaz


def test_lider_worker_uc_isi_tr_saatiyle_kaydeder(sessiz_lifespan, caplog):
    kos, _ = sessiz_lifespan
    gorulen: dict[str, tuple] = {}

    def _incele(app):
        scheduler = app.state.scheduler
        assert scheduler.running
        assert scheduler.timezone == TR
        for job in scheduler.get_jobs():
            assert job.trigger.timezone == TR
            nrt = job.next_run_time
            assert nrt is not None and nrt.utcoffset().total_seconds() == 3 * 3600
            nrt_tr = nrt.astimezone(TR)
            gorulen[job.id] = (nrt_tr.hour, nrt_tr.minute)

    with caplog.at_level(logging.INFO):
        app = kos(_incele)

    assert gorulen == ZAMANLAYICI_ISLERI
    assert not app.state.scheduler.running  # lifespan kapanışı zamanlayıcıyı durdurur
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    loglanan = {r.getMessage() for r in caplog.records}
    for job_id in ZAMANLAYICI_ISLERI:
        assert any(m.startswith(f"Zamanlayıcı işi {job_id} — sonraki koşu ") for m in loglanan)
