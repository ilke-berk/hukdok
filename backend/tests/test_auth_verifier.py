"""`auth_verifier.py` — kimlik kapısının karakterizasyonu (G059).

Kapsam raporunda (2026-08-13) bu dosya **%25**'ti: 48 ifadenin 36'sı hiç
çalışmıyordu. Sistemin kimlik kapısı ve tenant doğrulaması burada.

Bu testler sahte bir "doğrulama" kurmuyor: **gerçek bir RSA anahtar çifti**
üretilip token'lar gerçekten RS256 ile imzalanıyor ve `jwt.decode` gerçek
kriptografik doğrulamayı koşuyor. Taklit edilen tek şey **JWKS ağ çağrısı**
(`PyJWKClient.get_signing_key_from_jwt`) — testte ağa çıkmak yasak.

Buradaki hiçbir değer gerçek değildir: tenant id'ler, client id ve e-postalar
uydurma; anahtar çifti test koşusunda üretiliyor ve diske yazılmıyor.
"""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from auth_verifier import AuthVerifier

TENANT = "11111111-1111-1111-1111-111111111111"
BASKA_TENANT = "22222222-2222-2222-2222-222222222222"
CLIENT_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(scope="module")
def anahtar():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def baska_anahtar():
    """İmzası tutmayan token üretmek için ikinci, ilgisiz anahtar."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(anahtar, **claims):
    """Verilen claim'lerle gerçekten RS256 imzalı token üretir."""
    govde = {
        "tid": TENANT,
        "aud": CLIENT_ID,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "preferred_username": "test@ornek.gecersiz",
    }
    govde.update(claims)
    return jwt.encode(govde, anahtar, algorithm="RS256")


@pytest.fixture(autouse=True)
def _ortam(monkeypatch, anahtar):
    """Ağ yok, sınıf-düzeyi JWKS cache'i her testte temiz, env izole."""
    monkeypatch.setenv("ALLOWED_TENANTS", f"{TENANT}, {BASKA_TENANT}")
    monkeypatch.setenv("AZURE_CLIENT_ID", CLIENT_ID)
    for k in ("ENV", "ALLOW_DEV_TENANT", "DEV_MODE"):
        monkeypatch.delenv(k, raising=False)

    # `_jwks_clients` SINIF düzeyinde ve testler arası sızar — her testte sıfırla.
    monkeypatch.setattr(AuthVerifier, "_jwks_clients", {})

    class _SahteJWKS:
        def __init__(self, *a, **kw):
            pass

        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=anahtar.public_key())

    monkeypatch.setattr("auth_verifier.PyJWKClient", _SahteJWKS)
    yield


# ── Kabul yolu ───────────────────────────────────────────────────────────────

def test_gecerli_token_kabul_ediliyor(anahtar):
    claims = AuthVerifier.verify_token(_token(anahtar))
    assert claims is not None
    assert claims["tid"] == TENANT


def test_api_onekli_audience_da_kabul(anahtar):
    """Azure AD token'ın `aud`'unu `api://<client_id>` biçiminde de verebilir."""
    assert AuthVerifier.verify_token(_token(anahtar, aud=f"api://{CLIENT_ID}")) is not None


# ── Ret yolları — her biri kabul edilseydi kırmızıya dönecek biçimde ─────────

def test_bos_token_reddediliyor(caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        assert AuthVerifier.verify_token("") is None
    assert any("empty" in r.getMessage().lower() for r in caplog.records)


def test_izinsiz_tenant_reddediliyor(anahtar, caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, tid="99999999-9999-9999-9999-999999999999")) is None
    assert any("unauthorized" in r.getMessage().lower() for r in caplog.records)


def test_allowlistteki_ikinci_tenant_da_kabul(anahtar):
    """`ALLOWED_TENANTS` virgüllü ve boşluklu — ayrıştırma doğru çalışmalı."""
    assert AuthVerifier.verify_token(_token(anahtar, tid=BASKA_TENANT)) is not None


def test_suresi_gecmis_token_reddediliyor(anahtar, caplog):
    gecmis = datetime.now(timezone.utc) - timedelta(hours=1)
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, exp=gecmis)) is None
    assert any("expired" in r.getMessage().lower() for r in caplog.records)


def test_imzasi_tutmayan_token_reddediliyor(baska_anahtar, caplog):
    """Token BAŞKA bir anahtarla imzalandı; JWKS doğru açık anahtarı veriyor.
    Kriptografik doğrulama gerçekten koşuyor — sahte bir kontrol değil."""
    with caplog.at_level(logging.ERROR, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(baska_anahtar)) is None
    assert any("invalid token" in r.getMessage().lower() for r in caplog.records)


def test_yanlis_audience_reddediliyor(anahtar):
    assert AuthVerifier.verify_token(_token(anahtar, aud="baska-uygulama")) is None


def test_AZURE_CLIENT_ID_yoksa_reddediliyor(anahtar, monkeypatch, caplog):
    """Yapılandırma eksikse kapı AÇIK KALMAMALI — fail-closed."""
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    with caplog.at_level(logging.ERROR, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar)) is None
    assert any("AZURE_CLIENT_ID" in r.getMessage() for r in caplog.records)


def test_bicimi_bozuk_token_reddediliyor(caplog):
    with caplog.at_level(logging.ERROR, logger="AuthVerifier"):
        assert AuthVerifier.verify_token("bu.bir.jwt.degil") is None


def test_ALLOWED_TENANTS_bossa_hicbir_tenant_gecmiyor(anahtar, monkeypatch):
    """Env boşsa allowlist boş kümedir → fail-closed (herkese açık DEĞİL)."""
    monkeypatch.setenv("ALLOWED_TENANTS", "")
    assert AuthVerifier.verify_token(_token(anahtar)) is None


# ── DEV bypass — güvenlik kritik: prod'da KAPALI olmalı ──────────────────────

_UC_KOSUL = {"ENV": "development", "ALLOW_DEV_TENANT": "true", "DEV_MODE": "true"}


def test_dev_bypass_uc_kosul_birdeyken_aciliyor(baska_anahtar, monkeypatch, caplog):
    """Bypass imzayı DOĞRULAMADAN kabul eder — o yüzden token bilerek geçersiz
    bir anahtarla imzalandı. Geçiyorsa bypass gerçekten devrede demektir."""
    for k, v in _UC_KOSUL.items():
        monkeypatch.setenv(k, v)
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        claims = AuthVerifier.verify_token(_token(baska_anahtar, tid="dev-tenant"))
    assert claims is not None
    assert any("DEV bypass" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("eksik", sorted(_UC_KOSUL))
def test_dev_bypass_tek_kosul_eksikse_KAPALI(baska_anahtar, monkeypatch, eksik):
    """Üç koşuldan biri eksikse bypass ÇALIŞMAMALI. Prod'da `DEV_MODE`
    tanımsızdır — bu testler o kapının kazayla açılmasını yakalar."""
    for k, v in _UC_KOSUL.items():
        if k != eksik:
            monkeypatch.setenv(k, v)
    monkeypatch.delenv(eksik, raising=False)
    assert AuthVerifier.verify_token(_token(baska_anahtar, tid="dev-tenant")) is None


def test_dev_bypass_baska_tenantla_calismiyor(baska_anahtar, monkeypatch):
    """Üç koşul açık olsa bile `tid` tam olarak 'dev-tenant' değilse bypass yok →
    imza doğrulamasına düşer ve geçersiz imza reddedilir."""
    for k, v in _UC_KOSUL.items():
        monkeypatch.setenv(k, v)
    assert AuthVerifier.verify_token(_token(baska_anahtar, tid=TENANT)) is None


# ── get_user_from_token: `upn` claim tuzağı (kayıtlı arıza) ──────────────────

def test_kullanici_preferred_username_onceligi(anahtar):
    claims = {"preferred_username": "a@ornek.gecersiz", "upn": "b@ornek.gecersiz",
              "email": "c@ornek.gecersiz"}
    assert AuthVerifier.get_user_from_token(_token(anahtar, **claims)) == "a@ornek.gecersiz"


def test_kullanici_upn_fallbacki(anahtar):
    """KAYITLI TUZAK: `preferred_username` yokken `upn` okunmazsa admin kontrolü
    bozulur — bu bir kez gerçekten yaşandı."""
    token = _token(anahtar, preferred_username=None, upn="b@ornek.gecersiz")
    assert AuthVerifier.get_user_from_token(token) == "b@ornek.gecersiz"


def test_kullanici_email_fallbacki(anahtar):
    token = _token(anahtar, preferred_username=None, email="c@ornek.gecersiz")
    assert AuthVerifier.get_user_from_token(token) == "c@ornek.gecersiz"


def test_kullanici_hicbiri_yoksa_Unknown(anahtar):
    assert AuthVerifier.get_user_from_token(_token(anahtar, preferred_username=None)) == "Unknown"


def test_kullanici_gecersiz_tokende_None(baska_anahtar):
    """Doğrulama başarısızsa kullanıcı adı DÖNMEZ — 'Unknown' bile değil."""
    assert AuthVerifier.get_user_from_token(_token(baska_anahtar)) is None
