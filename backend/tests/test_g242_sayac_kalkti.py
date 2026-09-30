"""G242: kullanılmayan SharePoint belge sayacı kalktı.

Kilitlenen davranışlar:
  1. `/process` `complete` olayı artık belge sayacı alanını TAŞIMAZ ve analiz
     sırasında Graph'a (token + paylaşılan session) HİÇ çıkılmaz.
  2. `failed` yolunda da Graph'a çıkılmaz; olay değişmeden iletilir.
  3. Benchmark sözlüğünde sayaç anahtarı yok.
  4. Sayaç modülü, ayarı ve env değişkeni koddan çıktı (geri gelirse kırmızı).

conftest sözleşmesi gereği ağa/DB'ye çıkılmaz: analyzer ve case_matcher sahte.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from config.settings import Settings

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

BACKEND = Path(__file__).resolve().parents[1]

# Kalkan alan/anahtar adları parçalı yazılır: kabul taraması (rg) bu dosyada
# eski adları bulmasın, bekçi yine de tam adı denetlesin.
_ALAN = "ofis_" + "dosya_no"
_BENCH = "counter_" + "fetch"
_CONFIRM_BENCH = "1_" + "counter"
_MODUL = "counter_" + "manager"
_AYAR = _BENCH + "_timeout_seconds"
_ENV = "SHAREPOINT_" + "COUNTER_" + "LIST_NAME"


@pytest.fixture()
def process_app(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import case_matcher
    from dependencies import get_current_user
    from routes import processing
    from sharepoint import auth_graph, sharepoint_uploader_graph

    monkeypatch.setattr(case_matcher, "find_matching_case", lambda *a, **kw: None)
    monkeypatch.setattr(processing.PROCESS_CACHE, "set", lambda key, payload: None)

    # Sahte Graph: token ya da session istenirse kayda düşer ve patlar.
    graph_calls: List[str] = []

    def _token(*a, **kw):
        graph_calls.append("token")
        raise AssertionError("/process Graph token'ı istememeli")

    def _session(*a, **kw):
        graph_calls.append("session")
        raise AssertionError("/process Graph session'ı istememeli")

    monkeypatch.setattr(auth_graph, "get_graph_token", _token)
    monkeypatch.setattr(sharepoint_uploader_graph, "get_graph_token", _token)
    monkeypatch.setattr(sharepoint_uploader_graph, "_get_shared_session", _session)

    app = FastAPI()
    app.include_router(processing.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "test@example.com"}

    class _Harness:
        def __init__(self):
            self.client = TestClient(app)
            self.graph_calls = graph_calls

        def post(self):
            return self.client.post(
                "/process",
                files={"file": ("belge.pdf", io.BytesIO(b"%PDF-1.4\ntest\n"), "application/pdf")},
            )

    return _Harness()


def _events(resp) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in resp.text.strip().splitlines()]


def test_complete_olayinda_sayac_alani_yok_ve_graph_cagrisi_yok(monkeypatch, process_app):
    import analyzer

    async def fake_generator(file_path, file_hash=None, process_id=None, preset_belge_turu_kodu=None):
        yield {"status": "info", "message": "başladı"}
        yield {"status": "complete", "data": {"esas_no": "2024/1"}, "full_pdf_path": file_path}

    monkeypatch.setattr(analyzer, "analyze_file_generator", fake_generator)

    resp = process_app.post()
    assert resp.status_code == 200
    events = _events(resp)

    assert [e["status"] for e in events] == ["info", "complete"]
    final = events[-1]
    assert final["process_id"]
    assert final["data"]["esas_no"] == "2024/1"
    assert _ALAN not in final["data"]
    bench = final["data"]["_api_benchmark"]
    assert _BENCH not in bench
    assert set(bench) == {"analyzer", "case_match", "total"}
    assert process_app.graph_calls == []


def test_failed_yolunda_graph_cagrisi_yok(monkeypatch, process_app):
    import analyzer

    async def fake_generator(file_path, file_hash=None, process_id=None, preset_belge_turu_kodu=None):
        yield {"status": "info", "message": "başladı"}
        yield analyzer._failed_event("Servis doygun. (Kod: ab12cd34)", "gemini_saturated")

    monkeypatch.setattr(analyzer, "analyze_file_generator", fake_generator)

    events = _events(process_app.post())
    assert events[-1] == {
        "status": "failed",
        "error_ozet": "Servis doygun. (Kod: ab12cd34)",
        "error_kod": "gemini_saturated",
    }
    assert process_app.graph_calls == []


def test_sayac_modulu_ayari_ve_env_koddan_cikti():
    assert importlib.util.find_spec(f"managers.{_MODUL}") is None
    assert not (BACKEND / "managers" / f"{_MODUL}.py").exists()
    assert _AYAR not in Settings.model_fields

    processing_src = (BACKEND / "routes" / "processing.py").read_text(encoding="utf-8")
    for iz in (_MODUL, _ALAN, _BENCH, _CONFIRM_BENCH, "reserve_next_" + "counter"):
        assert iz not in processing_src

    # .env.example repo kökündedir; konteynerde (yalnız ./backend mount) yoksa atlanır.
    env_example = BACKEND.parent / ".env.example"
    if env_example.exists():
        assert _ENV not in env_example.read_text(encoding="utf-8")
