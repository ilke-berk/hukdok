"""G216 — `POST /api/transcribe`: ses → Gemini Türkçe metin.

Kilitlenen sözleşme (G217 frontend buna göre yazıldı):
  1. başarı 200 `{"metin": str}` strip'li; boş yanıt → "",
  2. oturumsuz 401,
  3. tür beyaz listesi; `;codecs=` parametresi atılarak karşılaştırılır, aksi 415,
  4. > 2 MB → 413, boş dosya / `ses` alanı yok → 422,
  5. Gemini geçici hata (retry'lar tükenince) / kalıcı hata / devre açık → 503 +
     sabit mesaj; denemeler WARNING, nihai TEK ERROR,
  6. ne ses baytı ne transkript metni loga düşer (caplog),
  7. ses diske taşmaz (multipart spool rollover'ı hiç tetiklenmez),
  8. router `api.app`'e kayıtlı.

Gemini ağ çağrısı yok: `gemini_client.get_client` sahte istemciyle değiştirilir.
"""
import logging
import tempfile
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

import gemini_client

URL = "/api/transcribe"
USER = {"tid": "tenant-x", "preferred_username": "avukat@hanyaloglu.com"}
TRANSKRIPT = "Davacı vekili Av. Ayşe Yılmaz, İstanbul 3. Asliye Hukuk Mahkemesi."
SES_ISARETI = b"GIZLI-SES-ISARETI"
SERVIS_YOK = "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin."


class _FakeModels:
    def __init__(self, davranislar):
        # davranislar: sırayla dönülecek str (metin) ya da fırlatılacak istisna
        self.davranislar = list(davranislar)
        self.cagrilar = []

    async def generate_content(self, model, contents, config):
        self.cagrilar.append({"model": model, "contents": contents, "config": config})
        d = self.davranislar.pop(0) if len(self.davranislar) > 1 else self.davranislar[0]
        if isinstance(d, BaseException):
            raise d
        return SimpleNamespace(text=d)


def _server_error(code=503):
    return genai_errors.ServerError(code, {"error": {"message": "overloaded", "status": "X"}})


def _client_error(code=400):
    return genai_errors.ClientError(code, {"error": {"message": "GIZLI-HATA-GOVDESI", "status": "X"}})


@pytest.fixture(autouse=True)
def _temiz_kesici():
    gemini_client.reset_circuits_for_tests()
    yield
    gemini_client.reset_circuits_for_tests()


@pytest.fixture()
def gemini(monkeypatch):
    """Sahte Gemini: `kur(*davranislar)` → _FakeModels. Retry beklemesi sıfırlanır."""
    monkeypatch.setenv("GEMINI_MODEL_NAME", "test-model")

    async def _uyuma(_s):
        return None

    monkeypatch.setattr(gemini_client, "_transcribe_sleep", _uyuma)
    kutu = {}

    def kur(*davranislar):
        models = _FakeModels(davranislar)
        kutu["models"] = models
        fake = SimpleNamespace(aio=SimpleNamespace(models=models))
        monkeypatch.setattr(gemini_client, "get_client", lambda api_key=None: fake)
        return models

    return kur


def _client(user=USER):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import transcribe as route_mod

    app = FastAPI()
    app.include_router(route_mod.router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _post(client, data=SES_ISARETI + b"\x00" * 100, tur="audio/webm", ad="kayit.webm"):
    return client.post(URL, files={"ses": (ad, data, tur)})


# ─── 1. başarı ───────────────────────────────────────────────────────────────

def test_basari_metin_strip_ve_gemini_cagrisi(gemini):
    models = gemini(f"  {TRANSKRIPT}\n ")
    r = _post(_client())
    assert r.status_code == 200
    assert r.json() == {"metin": TRANSKRIPT}
    assert len(models.cagrilar) == 1
    cagri = models.cagrilar[0]
    assert cagri["model"] == "test-model"
    prompt, part = cagri["contents"]
    assert prompt == gemini_client.TRANSCRIBE_PROMPT
    assert "Türkçe konuşmayı birebir yazıya dök" in prompt
    assert "yorum, özet, açıklama ekleme; yalnız metni döndür" in prompt
    assert part.inline_data.mime_type == "audio/webm"
    assert part.inline_data.data.startswith(SES_ISARETI)


def test_konusma_yoksa_bos_string(gemini):
    gemini(None)
    r = _post(_client())
    assert r.status_code == 200
    assert r.json() == {"metin": ""}


# ─── 2. oturum ───────────────────────────────────────────────────────────────

def test_oturumsuz_401(gemini):
    models = gemini(TRANSKRIPT)
    r = _post(_client(user=None))
    assert r.status_code == 401
    assert models.cagrilar == []


# ─── 3. tür ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "tur,beklenen_mime",
    [
        ("audio/webm;codecs=opus", "audio/webm"),
        ("audio/ogg; codecs=opus", "audio/ogg"),
        ("audio/mp4", "audio/mp4"),
        ("audio/mpeg", "audio/mpeg"),
        ("AUDIO/WAV", "audio/wav"),
    ],
)
def test_kabul_edilen_turler_parametre_atilir(gemini, tur, beklenen_mime):
    models = gemini(TRANSKRIPT)
    r = _post(_client(), tur=tur)
    assert r.status_code == 200, r.text
    assert models.cagrilar[0]["contents"][1].inline_data.mime_type == beklenen_mime


@pytest.mark.parametrize("tur", ["video/webm", "audio/flac", "application/octet-stream", "text/plain"])
def test_desteklenmeyen_tur_415(gemini, tur):
    models = gemini(TRANSKRIPT)
    r = _post(_client(), tur=tur)
    assert r.status_code == 415
    assert models.cagrilar == []


# ─── 4. boyut / boş ──────────────────────────────────────────────────────────

def test_iki_mb_ustu_413(gemini):
    models = gemini(TRANSKRIPT)
    r = _post(_client(), data=b"a" * (2 * 1024 * 1024 + 1))
    assert r.status_code == 413
    assert models.cagrilar == []


def test_cok_buyuk_govde_413_akista_kesilir(gemini):
    models = gemini(TRANSKRIPT)
    r = _post(_client(), data=b"a" * (3 * 1024 * 1024))
    assert r.status_code == 413
    assert models.cagrilar == []


def test_tam_iki_mb_kabul(gemini):
    gemini(TRANSKRIPT)
    r = _post(_client(), data=b"a" * (2 * 1024 * 1024))
    assert r.status_code == 200


def test_bos_dosya_422(gemini):
    models = gemini(TRANSKRIPT)
    r = _post(_client(), data=b"")
    assert r.status_code == 422
    assert models.cagrilar == []


def test_ses_alani_yok_422(gemini):
    models = gemini(TRANSKRIPT)
    r = _client().post(URL, files={"baska": ("k.webm", b"abc", "audio/webm")})
    assert r.status_code == 422
    assert models.cagrilar == []


# ─── 5. Gemini hataları → 503 ────────────────────────────────────────────────

def test_gecici_hata_retry_tukenince_503_warning_ve_tek_error(gemini, caplog):
    models = gemini(_server_error(503))
    with caplog.at_level(logging.DEBUG):
        r = _post(_client())
    assert r.status_code == 503
    assert r.json() == {"detail": SERVIS_YOK}
    assert len(models.cagrilar) == 1 + gemini_client.TRANSCRIBE_MAX_RETRIES
    uyarilar = [
        x for x in caplog.records
        if x.levelno == logging.WARNING and "Transkripsiyon" in x.getMessage()
    ]
    assert len(uyarilar) == gemini_client.TRANSCRIBE_MAX_RETRIES
    hatalar = [x for x in caplog.records if x.levelno >= logging.ERROR]
    assert len(hatalar) == 1
    assert "sonuc=hata" in hatalar[0].getMessage()


def test_gecici_hata_sonra_basari_200(gemini):
    models = gemini(_server_error(503), f" {TRANSKRIPT} ")
    r = _post(_client())
    assert r.status_code == 200
    assert r.json() == {"metin": TRANSKRIPT}
    assert len(models.cagrilar) == 2


def test_kalici_hata_retry_yok_503(gemini):
    models = gemini(_client_error(400))
    r = _post(_client())
    assert r.status_code == 503
    assert r.json() == {"detail": SERVIS_YOK}
    assert len(models.cagrilar) == 1


def test_devre_acikken_gemini_cagrilmaz_503(gemini):
    models = gemini(TRANSKRIPT)
    for _ in range(gemini_client.CIRCUIT_FAILURE_THRESHOLD):
        gemini_client.circuit_record_failure("test-model")
    r = _post(_client())
    assert r.status_code == 503
    assert r.json() == {"detail": SERVIS_YOK}
    assert models.cagrilar == []


def test_anahtar_yoksa_503(gemini, monkeypatch):
    gemini(TRANSKRIPT)
    monkeypatch.setattr(gemini_client, "get_client", lambda api_key=None: None)
    r = _post(_client())
    assert r.status_code == 503


# ─── 6. log gizliliği ────────────────────────────────────────────────────────

def _tum_log_metni(records):
    parcalar = []
    for x in records:
        parcalar.append(x.getMessage())
        parcalar.append(repr(x.__dict__))
    return "\n".join(parcalar)


def test_loglarda_transkript_ve_ses_yok_basari(gemini, caplog):
    gemini(TRANSKRIPT)
    with caplog.at_level(logging.DEBUG):
        r = _post(_client())
    assert r.status_code == 200
    metin = _tum_log_metni(caplog.records)
    assert "Ayşe Yılmaz" not in metin
    assert TRANSKRIPT not in metin
    assert SES_ISARETI.decode() not in metin
    ozet = [x for x in caplog.records if x.name == "routes.transcribe" and x.levelno == logging.INFO]
    assert len(ozet) == 1
    mesaj = ozet[0].getMessage()
    assert "boyut=" in mesaj and "tur=audio/webm" in mesaj and "sure_ms=" in mesaj and "sonuc=ok" in mesaj


def test_loglarda_icerik_yok_hata(gemini, caplog):
    gemini(_client_error(400))
    with caplog.at_level(logging.DEBUG):
        r = _post(_client())
    assert r.status_code == 503
    metin = _tum_log_metni(caplog.records)
    assert SES_ISARETI.decode() not in metin
    assert "GIZLI-HATA-GOVDESI" not in metin  # istisna metni (Gemini yanıt gövdesi) loglanmaz


# ─── 7. disk yok ─────────────────────────────────────────────────────────────

def test_ses_diske_tasmaz(gemini, monkeypatch):
    """1 MB'ı aşan (Starlette'in varsayılan spool tavanı) kayıt bile bellekte kalır."""
    gemini(TRANSKRIPT)

    def _yasak(self):
        raise AssertionError("SpooledTemporaryFile diske taştı")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", _yasak)
    r = _post(_client(), data=b"a" * (2 * 1024 * 1024))
    assert r.status_code == 200, r.text


# ─── 8. kayıt ────────────────────────────────────────────────────────────────

def test_router_api_app_e_kayitli():
    """Tam uygulamada uç var ve oturum ister: kayıtsız olsa 404/405 dönerdi.
    `with` bloğu bilinçli YOK — lifespan (init_db, scheduler) koşmasın."""
    from fastapi.testclient import TestClient

    from api import app

    r = TestClient(app).post(URL, files={"ses": ("k.webm", b"abc", "audio/webm")})
    assert r.status_code == 401
