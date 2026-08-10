"""Faz 3-B testleri: Graph çağrılarına transport retry + 401 token yenileme +
chunk resume (sharepoint_uploader_graph + auth_graph).

Kapsam:
- Retry politikası: total=3, backoff_factor=1, forcelist {429,500,502,503,504},
  PUT/POST/PATCH açıkça izinli (urllib3 2.x varsayılanında YOKLAR),
  respect_retry_after_header — paylaşılan session'a mount edilmiş
- Küçük dosya PUT'u gövdeyi belleğe okur (stream, transport retry'ında geri
  sarılamaz; 4 MB tavanı chunk eşiğiyle sınırlı)
- 401 → get_graph_token(force_refresh=True) ile BİR kez daha; ikinci 401 nihai
- Chunk akışı: 202 ilerlemesi sunucu beyanıyla, ConnectionError/416'da
  nextExpectedRanges'ten devam, resume bütçesi, 202'de ilerleme yoksa sonsuz
  döngü koruması, chunk PUT'larının Authorization taşımaması
- get_graph_token(force_refresh=True): remove_tokens_for_client çağrılır;
  yoksa (eski msal) app düşürülüp yeniden kurulur; healthz damgası korunur
- Log sözleşmesi: uploader deneme başına ERROR üretmez (WARNING) — nihai
  ERROR üst katmanların işi (ERROR-oranı alarmı hıçkırıkta çalmasın)

Ağa çıkılmaz (conftest sözleşmesi): session ve msal app fake'lenir. caplog
BİLİNÇLİ değil (test_faz2_alerting ile aynı gerekçe): dictConfig pytest
capture handler'ını söker; adlandırılmış logger'a takılan handler etkilenmez.
"""
import logging

import pytest
import requests

import health
import sharepoint.auth_graph as auth_graph
import sharepoint.sharepoint_uploader_graph as spu


# ─── ortak fake'ler ──────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text="", content=b""):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.text = text
        self.content = content

    def json(self):
        if self._json is None:
            raise ValueError("gövde JSON değil")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class _FakeSession:
    """Sıralı senaryo oynatan session: çağrılar kaydedilir, yanıtlar metod
    başına kuyruktan gelir; kuyruk elemanı Exception ise fırlatılır."""

    def __init__(self):
        self.puts, self.gets, self.posts, self.patches = [], [], [], []
        self.put_script, self.get_script, self.post_script, self.patch_script = [], [], [], []

    def _play(self, script, record):
        if not script:
            raise AssertionError(f"Beklenmeyen çağrı: {record}")
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def put(self, url, **kw):
        self.puts.append({"url": url, **kw})
        return self._play(self.put_script, ("PUT", url))

    def get(self, url, **kw):
        self.gets.append({"url": url, **kw})
        return self._play(self.get_script, ("GET", url))

    def post(self, url, **kw):
        self.posts.append({"url": url, **kw})
        return self._play(self.post_script, ("POST", url))

    def patch(self, url, **kw):
        self.patches.append({"url": url, **kw})
        return self._play(self.patch_script, ("PATCH", url))


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture()
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(spu, "_get_shared_session", lambda: session)
    return session


@pytest.fixture()
def fake_ids(monkeypatch):
    monkeypatch.setattr(
        spu, "_get_site_and_drive_id",
        lambda token, config_type="default": ("site-1", "drive-1"),
    )


@pytest.fixture()
def token_calls(monkeypatch):
    """spu.get_graph_token'ı fake'ler; force_refresh argümanlarını kaydeder,
    'tok1', 'tok2', ... döndürür."""
    calls = []

    def fake_token(config_type="default", force_refresh=False):
        calls.append(force_refresh)
        return f"tok{len(calls)}"

    monkeypatch.setattr(spu, "get_graph_token", fake_token)
    return calls


@pytest.fixture()
def uploader_log_records():
    handler = _ListHandler()
    target = logging.getLogger("SharePointUploader")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _write_file(tmp_path, name, payload: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(payload)
    return str(p)


# ─── retry politikası ────────────────────────────────────────────────────────

class TestRetryPolicy:
    def test_politika_degerleri_plandaki_gibi(self):
        retry = spu._build_retry()
        assert retry.total == 3
        assert retry.backoff_factor == 1
        assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
        assert retry.respect_retry_after_header is True

    def test_put_post_patch_acikca_izinli(self):
        # urllib3 2.x varsayılan allowed_methods'unda PUT/POST/PATCH yok —
        # izinli olmazlarsa upload'lar 429/5xx'te hiç retry görmez.
        allowed = {m.upper() for m in spu._build_retry().allowed_methods}
        assert {"GET", "PUT", "POST", "PATCH"} <= allowed

    def test_session_adapterlari_retry_ile_mount_edilmis(self):
        session = spu._build_session()
        for url in ("https://graph.microsoft.com/v1.0/drives", "http://x/y"):
            adapter = session.get_adapter(url)
            assert adapter.max_retries.total == 3

    def test_paylasilan_session_tekil(self, monkeypatch):
        monkeypatch.setattr(spu, "_shared_session", None)
        monkeypatch.setattr(spu, "_load_env", lambda: None)
        s1 = spu._get_shared_session()
        s2 = spu._get_shared_session()
        assert s1 is s2


# ─── küçük dosya yolu ────────────────────────────────────────────────────────

class TestSmallUpload:
    def test_govde_bellege_okunur_stream_degil(self, tmp_path, fake_session, fake_ids, token_calls):
        path = _write_file(tmp_path, "kucuk.pdf", b"pdf-icerik")
        fake_session.put_script = [_FakeResponse(200, {"id": "it1", "webUrl": "https://sp/it1"})]

        data = spu.upload_file_to_sharepoint(path, "kucuk.pdf", "01_HAM_ARSIV")

        assert data["id"] == "it1"
        put = fake_session.puts[0]
        # bytes gövde: transport retry aynı gövdeyi güvenle yeniden gönderebilir
        assert isinstance(put["data"], bytes) and put["data"] == b"pdf-icerik"
        assert put["headers"]["Authorization"] == "Bearer tok1"
        assert token_calls == [False]

    def test_401de_token_zorla_yenilenir_ikinci_deneme_gecer(
        self, tmp_path, fake_session, fake_ids, token_calls, uploader_log_records
    ):
        path = _write_file(tmp_path, "kucuk.pdf", b"x")
        fake_session.put_script = [
            _FakeResponse(401, text="token suresi doldu"),
            _FakeResponse(200, {"id": "it2"}),
        ]

        data = spu.upload_file_to_sharepoint(path, "kucuk.pdf", "01_HAM_ARSIV")

        assert data["id"] == "it2"
        assert token_calls == [False, True]  # ikinci çağrı force_refresh=True
        assert fake_session.puts[1]["headers"]["Authorization"] == "Bearer tok2"
        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]

    def test_iki_401_nihai_hatadir_yenileme_dongusu_yok(self, tmp_path, fake_session, fake_ids, token_calls):
        path = _write_file(tmp_path, "kucuk.pdf", b"x")
        fake_session.put_script = [_FakeResponse(401), _FakeResponse(401)]

        with pytest.raises(requests.HTTPError):
            spu.upload_file_to_sharepoint(path, "kucuk.pdf", "01_HAM_ARSIV")

        assert token_calls == [False, True]
        assert len(fake_session.puts) == 2

    def test_gecici_hata_error_degil_warning(
        self, tmp_path, fake_session, fake_ids, token_calls, uploader_log_records
    ):
        # Nihai ERROR üst katmanın işi (upload_queue failed / async_* fallback);
        # uploader deneme başına ERROR üretse ERROR-oranı alarmı hıçkırıkta çalardı.
        path = _write_file(tmp_path, "kucuk.pdf", b"x")
        fake_session.put_script = [requests.ConnectionError("ağ koptu")]

        with pytest.raises(requests.ConnectionError):
            spu.upload_file_to_sharepoint(path, "kucuk.pdf", "01_HAM_ARSIV")

        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]
        assert [r for r in uploader_log_records if r.levelno == logging.WARNING]

    def test_metadata_hatasi_uploadi_dusurmez_error_uretmez(
        self, tmp_path, fake_session, fake_ids, token_calls, uploader_log_records
    ):
        path = _write_file(tmp_path, "kucuk.pdf", b"x")
        fake_session.put_script = [_FakeResponse(200, {"id": "it3"})]
        fake_session.patch_script = [_FakeResponse(400, text="alan hatası")]

        data = spu.upload_file_to_sharepoint(path, "k.pdf", "F", metadata={"Alan": "deger"})

        assert data["id"] == "it3"
        assert len(fake_session.patches) == 1  # denendi ama upload'ı düşürmedi
        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]


# ─── chunk'lı yol ────────────────────────────────────────────────────────────

@pytest.fixture()
def small_chunks(monkeypatch):
    """Eşik/parça boylarını test boyutlarına indir: 4 bayt eşik, 4 bayt chunk."""
    monkeypatch.setattr(spu, "_SMALL_FILE_LIMIT", 4)
    monkeypatch.setattr(spu, "_CHUNK_SIZE", 4)


class TestChunkUpload:
    UPLOAD_URL = "https://up.sharepoint.example/sess-1"

    def _arm_session_create(self, fake_session):
        fake_session.post_script = [_FakeResponse(200, {"uploadUrl": self.UPLOAD_URL})]

    def test_mutlu_yol_uc_parca(self, tmp_path, fake_session, fake_ids, token_calls, small_chunks):
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")  # 10 bayt
        self._arm_session_create(fake_session)
        fake_session.put_script = [
            _FakeResponse(202, {"nextExpectedRanges": ["4-9"]}),
            _FakeResponse(202, {"nextExpectedRanges": ["8-9"]}),
            _FakeResponse(201, {"id": "big1", "webUrl": "https://sp/big1"}),
        ]

        data = spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")

        assert data["id"] == "big1"
        assert len(fake_session.posts) == 1  # tek createUploadSession
        sent = [(p["headers"]["Content-Range"], p["data"]) for p in fake_session.puts]
        assert sent == [
            ("bytes 0-3/10", b"0123"),
            ("bytes 4-7/10", b"4567"),
            ("bytes 8-9/10", b"89"),
        ]
        # uploadUrl ön-yetkili: chunk PUT'ları Authorization taşımaz
        assert all("Authorization" not in p["headers"] for p in fake_session.puts)
        assert all(p["url"] == self.UPLOAD_URL for p in fake_session.puts)

    def test_baglanti_hatasinda_kaldigi_yerden_devam(
        self, tmp_path, fake_session, fake_ids, token_calls, small_chunks, uploader_log_records
    ):
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")
        self._arm_session_create(fake_session)
        fake_session.put_script = [
            _FakeResponse(202, {"nextExpectedRanges": ["4-9"]}),
            requests.ConnectionError("iç retry bütçesi de tükendi"),
            _FakeResponse(202, {"nextExpectedRanges": ["6-9"]}),
            _FakeResponse(201, {"id": "big2"}),
        ]
        # Sunucu yalnız ilk 2 baytı almış: devam ofseti sunucu beyanından gelir
        fake_session.get_script = [_FakeResponse(200, {"nextExpectedRanges": ["2-9"]})]

        data = spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")

        assert data["id"] == "big2"
        assert fake_session.gets[0]["url"] == self.UPLOAD_URL  # durum sorgusu
        sent = [(p["headers"]["Content-Range"], p["data"]) for p in fake_session.puts]
        assert sent == [
            ("bytes 0-3/10", b"0123"),
            ("bytes 4-7/10", b"4567"),  # kopan deneme
            ("bytes 2-5/10", b"2345"),  # sunucunun dediği ofsetten seek
            ("bytes 6-9/10", b"6789"),
        ]
        # geçici hata + devam: ERROR yok, WARNING var
        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]
        assert [r for r in uploader_log_records if r.levelno == logging.WARNING]

    def test_resume_butcesi_tukenince_nihai_hata(
        self, tmp_path, fake_session, fake_ids, token_calls, small_chunks
    ):
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")
        self._arm_session_create(fake_session)
        fake_session.put_script = [requests.ConnectionError(f"kopma {i}") for i in range(4)]
        fake_session.get_script = [
            _FakeResponse(200, {"nextExpectedRanges": ["0-9"]}) for _ in range(3)
        ]

        with pytest.raises(RuntimeError, match="bütçesi tükendi"):
            spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")

        assert len(fake_session.puts) == 1 + spu._CHUNK_RESUME_BUDGET
        assert len(fake_session.gets) == spu._CHUNK_RESUME_BUDGET

    def test_416_zaten_alinmis_aralikta_sunucuya_hizalanir(
        self, tmp_path, fake_session, fake_ids, token_calls, small_chunks
    ):
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")
        self._arm_session_create(fake_session)
        fake_session.put_script = [
            _FakeResponse(416, text="invalidRange"),
            _FakeResponse(202, {"nextExpectedRanges": ["8-9"]}),
            _FakeResponse(201, {"id": "big3"}),
        ]
        fake_session.get_script = [_FakeResponse(200, {"nextExpectedRanges": ["4-9"]})]

        data = spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")

        assert data["id"] == "big3"
        assert fake_session.puts[1]["headers"]["Content-Range"] == "bytes 4-7/10"

    def test_202de_ilerleme_yoksa_sonsuz_dongu_korumasi(
        self, tmp_path, fake_session, fake_ids, token_calls, small_chunks
    ):
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")
        self._arm_session_create(fake_session)
        fake_session.put_script = [_FakeResponse(202, {"nextExpectedRanges": ["0-9"]})]

        with pytest.raises(RuntimeError, match="ilerlemiyor"):
            spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")

    def test_durum_sorgusu_da_duserse_nihai_hata(
        self, tmp_path, fake_session, fake_ids, token_calls, small_chunks
    ):
        # nextExpectedRanges boş = oturum sunucuda kapanmış; kaldığı yer yok —
        # nihai hata fırlar, dış katman baştan yükler (replace güvenli).
        path = _write_file(tmp_path, "buyuk.pdf", b"0123456789")
        self._arm_session_create(fake_session)
        fake_session.put_script = [requests.ConnectionError("kopma")]
        fake_session.get_script = [_FakeResponse(200, {"nextExpectedRanges": []})]

        with pytest.raises(RuntimeError, match="durum sorgusu da başarısız"):
            spu.upload_file_to_sharepoint(path, "buyuk.pdf", "01_HAM_ARSIV")


# ─── indirme yolu ────────────────────────────────────────────────────────────

class TestDownload:
    def test_401_yenileme_indirmede_de_calisir(self, monkeypatch, fake_session, fake_ids, token_calls):
        monkeypatch.setattr(spu, "_load_env", lambda: None)
        fake_session.get_script = [
            _FakeResponse(401),
            _FakeResponse(200, headers={"Content-Type": "application/pdf"}, content=b"pdf-bytes"),
        ]

        content, ctype = spu.download_file_from_sharepoint("02_YEDEK_ARSIV", "a.pdf")

        assert (content, ctype) == (b"pdf-bytes", "application/pdf")
        assert token_calls == [False, True]
        assert fake_session.gets[1]["headers"]["Authorization"] == "Bearer tok2"


# ─── auth_graph force_refresh ────────────────────────────────────────────────

class TestForceRefresh:
    def test_force_refresh_remove_tokens_cagirir_ve_healthz_damgasi_korunur(self, monkeypatch):
        calls = {"removed": 0, "acquired": 0}

        class _FakeApp:
            def remove_tokens_for_client(self):
                calls["removed"] += 1

            def acquire_token_for_client(self, scopes):
                calls["acquired"] += 1
                return {"access_token": "yeni-token"}

        monkeypatch.setattr(auth_graph, "_get_msal_app", lambda config_type="default": _FakeApp())

        token = auth_graph.get_graph_token(force_refresh=True)

        assert token == "yeni-token"
        assert calls == {"removed": 1, "acquired": 1}
        # Başarılı alım /healthz graph_token_age_seconds damgasını atmalı
        assert health.signals_snapshot()["graph_token_age_seconds"] is not None

    def test_normal_cagri_cache_dusurmez(self, monkeypatch):
        class _FakeApp:
            def __init__(self):
                self.removed = 0

            def remove_tokens_for_client(self):
                self.removed += 1

            def acquire_token_for_client(self, scopes):
                return {"access_token": "t"}

        app = _FakeApp()
        monkeypatch.setattr(auth_graph, "_get_msal_app", lambda config_type="default": app)

        assert auth_graph.get_graph_token() == "t"
        assert app.removed == 0

    def test_eski_msal_fallbacki_app_dusurulup_yeniden_kurulur(self, monkeypatch):
        class _OldApp:  # remove_tokens_for_client YOK (msal<1.27 senaryosu)
            def acquire_token_for_client(self, scopes):
                raise AssertionError("düşürülen eski app kullanılmamalı")

        class _NewApp:
            def __init__(self):
                self.acquired = 0

            def acquire_token_for_client(self, scopes):
                self.acquired += 1
                return {"access_token": "taze"}

        old_app, new_app = _OldApp(), _NewApp()
        apps = iter([old_app, new_app])
        monkeypatch.setattr(
            auth_graph, "_get_msal_app", lambda config_type="default": next(apps)
        )
        auth_graph._MSAL_APPS["default"] = old_app
        try:
            token = auth_graph.get_graph_token(force_refresh=True)

            assert token == "taze"
            assert new_app.acquired == 1
            assert "default" not in auth_graph._MSAL_APPS  # cache düşürüldü
        finally:
            auth_graph._MSAL_APPS.pop("default", None)
