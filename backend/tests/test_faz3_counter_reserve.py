"""Faz 3-D (plan 3.4) — ofis numarası atomik rezervasyonu testleri.

Ağ yok: Graph katmanı sahte bir "counter sunucusu" ile taklit edilir; sunucu
gerçek ETag/If-Match semantiğini uygular (bayat ETag'le PATCH → 412). Böylece
"iki eşzamanlı tahsis asla aynı numarayı alamaz" garantisi gerçek çakışma
mekaniğiyle kanıtlanır.
"""
import logging
import os
import threading

import pytest
import requests

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

from managers import counter_manager  # noqa: E402


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture()
def counter_logs():
    """dictConfig pytest caplog'u söküyor (Faz 2-C notu) — adlandırılmış
    logger'a doğrudan handler takılır."""
    handler = ListHandler()
    lg = logging.getLogger("SharePointCounterManager")
    prev_level = lg.level
    lg.addHandler(handler)
    lg.setLevel(logging.DEBUG)
    yield handler
    lg.removeHandler(handler)
    lg.setLevel(prev_level)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


class FakeCounterServer:
    """SharePoint Counter listesinin ETag semantiğini uygulayan sahte uç.

    _get_session() yerine geçer: get/patch imzaları requests.Session ile aynı.
    """

    def __init__(self, value=42):
        self.value = value
        self.version = 1
        self.lock = threading.Lock()
        self.patch_calls = []
        self.force_412_times = 0     # sıradaki N PATCH'i koşulsuz 412'le
        self.fail_patch_status = None  # None değilse her PATCH bu kodu döner

    @property
    def etag(self):
        return f'"etag-{self.version}"'

    def get(self, url, headers=None, timeout=None):
        if url.endswith("/lists"):
            return FakeResponse(200, {"value": [
                {"displayName": "Counter", "name": "Counter", "id": "LIST1"},
            ]})
        if url.endswith("/columns"):
            return FakeResponse(200, {"value": [
                {"displayName": "Current_Count", "name": "field_1"},
                {"displayName": "Last_Updated", "name": "field_2"},
                {"displayName": "Updated_By", "name": "field_3"},
            ]})
        if "/items" in url:
            with self.lock:
                return FakeResponse(200, {"value": [{
                    "id": "1", "eTag": self.etag,
                    "fields": {"field_1": self.value},
                }]})
        raise AssertionError(f"beklenmeyen GET: {url}")

    def patch(self, url, headers=None, json=None, timeout=None):
        with self.lock:
            self.patch_calls.append({"headers": dict(headers or {}), "json": json})
            if self.fail_patch_status is not None:
                return FakeResponse(self.fail_patch_status)
            if self.force_412_times > 0:
                self.force_412_times -= 1
                return FakeResponse(412)
            if (headers or {}).get("If-Match") != self.etag:
                return FakeResponse(412)
            self.value = json["fields"]["field_1"]
            self.version += 1
            return FakeResponse(200)


@pytest.fixture()
def fake_graph(monkeypatch):
    """Graph plumbing'i sahteye bağla; uykuları kaydet (gerçek bekleme yok)."""
    server = FakeCounterServer(value=42)
    sleeps = []
    monkeypatch.setattr(counter_manager, "_get_session", lambda: server)
    monkeypatch.setattr(counter_manager, "get_graph_token", lambda: "tok")
    monkeypatch.setattr(counter_manager, "_get_site_and_drive_id", lambda tok: ("SITE1", "DRIVE1"))
    monkeypatch.setattr(counter_manager.time, "sleep", lambda s: sleeps.append(s))
    server.sleeps = sleeps
    return server


def _fresh_manager():
    return counter_manager.SharePointCounterManager()


def test_reserve_okur_artirir_okunani_dondurur(fake_graph):
    cm = _fresh_manager()
    assert cm.reserve_next_counter() == "000000042"
    # Sayaç sunucuda +1 oldu, PATCH okunan ETag'i If-Match ile taşıdı
    assert fake_graph.value == 43
    call = fake_graph.patch_calls[-1]
    assert call["headers"]["If-Match"] == '"etag-1"'
    assert call["json"]["fields"]["field_1"] == 43
    # Ardışık tahsisler ardışık numara verir
    assert cm.reserve_next_counter() == "000000043"
    assert fake_graph.value == 44


def test_412_cakismasinda_backoff_ile_tekrar_dener(fake_graph, counter_logs):
    fake_graph.force_412_times = 1
    cm = _fresh_manager()
    assert cm.reserve_next_counter() == "000000042"
    # İlk deneme 412 yedi → bir backoff uykusu + WARNING, ikinci deneme geçti
    assert len(fake_graph.sleeps) == 1
    assert fake_graph.sleeps[0] >= counter_manager._CONFLICT_BACKOFF_BASE_SECONDS
    warnings = [r for r in counter_logs.records if r.levelno == logging.WARNING]
    assert any("ETag conflict" in r.getMessage() for r in warnings)


def test_tukenen_cakisma_tek_error_ile_duser(fake_graph, counter_logs):
    fake_graph.force_412_times = 99
    cm = _fresh_manager()
    with pytest.raises(Exception, match="ETag conflict"):
        cm.reserve_next_counter()
    assert len(fake_graph.patch_calls) == counter_manager.RESERVE_MAX_ATTEMPTS
    # Son denemeden sonra uyunmaz
    assert len(fake_graph.sleeps) == counter_manager.RESERVE_MAX_ATTEMPTS - 1
    # Log sözleşmesi: denemeler WARNING, nihai başarısızlık TEK ERROR
    errors = [r for r in counter_logs.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_412_disi_hata_retry_etmez_ve_cacheleri_dusurur(fake_graph):
    fake_graph.fail_patch_status = 403
    cm = _fresh_manager()
    with pytest.raises(Exception, match="counter güncellenemedi"):
        cm.reserve_next_counter()
    assert len(fake_graph.patch_calls) == 1
    assert fake_graph.sleeps == []
    # Liste/kolon cache'leri düştü — sonraki çağrı yeniden çözümleyecek
    assert cm._list_id_cache is None
    assert cm._field_map_cache is None


def test_eszamanli_iki_tahsis_farkli_numara_alir(fake_graph):
    """Gerçek ETag semantiği altında yarış: kaybeden 412 yer, taze değeri okur.

    Eski akışın (salt oku + /confirm'de artır) tam da veremediği garanti.
    """
    cm = _fresh_manager()
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        num = cm.reserve_next_counter()
        with lock:
            results.append(num)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 2
    assert len(set(results)) == 2, f"aynı numara iki kez verildi: {results}"
    assert fake_graph.value == 44  # 42 ve 43 tahsis edildi


def test_get_next_counter_salt_okur(fake_graph):
    cm = _fresh_manager()
    assert cm.get_next_counter() == "000000042"
    assert fake_graph.value == 42
    assert fake_graph.patch_calls == []


def test_factory_surec_tekil_instance_doner(monkeypatch):
    monkeypatch.setattr(counter_manager, "_manager_singleton", None)
    a = counter_manager.get_counter_manager()
    b = counter_manager.get_counter_manager()
    assert a is b


def test_confirm_artik_sayac_artirmaz_process_reserve_kullanir():
    """Bekçi: /confirm'deki arka plan artırma kalktı, /process atomik tahsis
    kullanıyor; eski API'ler geri sızarsa bu test kırılır."""
    import inspect

    from routes import processing
    from services import document_pipeline

    src = inspect.getsource(processing)
    assert "reserve_next_counter" in src
    assert "async_increment_counter" not in src
    assert not hasattr(document_pipeline, "async_increment_counter")
    # Salt-okur get_next_counter'la tahsis yapılmıyor (yalnız reserve çağrılıyor)
    assert "get_next_counter" not in src
    # increment_counter API'si tamamen kalktı — yarım kalmış çağrı kalmasın
    assert not hasattr(counter_manager.SharePointCounterManager, "increment_counter")
