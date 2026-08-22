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


def _iss_v2(tid):
    return f"https://login.microsoftonline.com/{tid}/v2.0"


def _iss_v1(tid):
    return f"https://sts.windows.net/{tid}/"


_ISS_YOK = object()


def _token(anahtar, **claims):
    """Verilen claim'lerle gerçekten RS256 imzalı token üretir.

    `iss` verilmezse `tid`'den v2 biçimiyle türetilir (G092 — issuer artık
    doğrulanıyor); `iss=_ISS_YOK` ile claim tamamen düşürülür.
    """
    govde = {
        "tid": TENANT,
        "aud": CLIENT_ID,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "preferred_username": "test@ornek.gecersiz",
    }
    govde.update(claims)
    if govde.get("iss") is _ISS_YOK:
        del govde["iss"]
    elif "iss" not in govde:
        govde["iss"] = _iss_v2(govde["tid"])
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
    # G092 tek-seferlik gözlem bayrağı da sınıf düzeyinde — testler arası sızmasın.
    monkeypatch.setattr(AuthVerifier, "_scope_audience_warned", False)

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


# ── Issuer doğrulaması (G092) — tid'den türetilir, iki biçim de kabul ────────

def test_iss_v2_bicimi_kabul(anahtar):
    assert AuthVerifier.verify_token(_token(anahtar, iss=_iss_v2(TENANT))) is not None


def test_iss_v1_bicimi_kabul(anahtar):
    assert AuthVerifier.verify_token(_token(anahtar, iss=_iss_v1(TENANT))) is not None


def test_iss_yanlis_reddediliyor(anahtar, caplog):
    """Doğru tenant + doğru imza + doğru aud; YALNIZ `iss` yanlış → ret."""
    with caplog.at_level(logging.ERROR, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, iss="https://saldirgan.gecersiz/v2.0")) is None
    assert any("invalid token" in r.getMessage().lower() for r in caplog.records)


def test_iss_baska_tenantin_issi_reddediliyor(anahtar):
    """`iss` allowlist'teki BAŞKA tenant'a ait olsa bile `tid` ile uyuşmuyorsa ret —
    sabit bir tenant listesine değil, token'ın kendi tid'ine bağlanır."""
    assert AuthVerifier.verify_token(_token(anahtar, tid=TENANT, iss=_iss_v2(BASKA_TENANT))) is None


def test_iss_claimi_yoksa_reddediliyor(anahtar, caplog):
    with caplog.at_level(logging.ERROR, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, iss=_ISS_YOK)) is None
    assert any("iss" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("iss_uret", [_iss_v2, _iss_v1])
def test_iss_ikinci_tenant_kendi_issiyle_geciyor(anahtar, iss_uret):
    """`ALLOWED_TENANTS`'taki ikinci tenant kendi iss'iyle (v1 ve v2) geçer."""
    assert AuthVerifier.verify_token(_token(anahtar, tid=BASKA_TENANT, iss=iss_uret(BASKA_TENANT))) is not None


# ── scp/aud gözlem modu (G092) — davranışsız, süreç başına bir WARNING ──────

def _gozlem_kayitlari(caplog):
    return [r for r in caplog.records if "gözlem" in r.getMessage()]


def test_scp_eksik_token_kabul_ama_bir_kez_warning(anahtar, caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, aud=f"api://{CLIENT_ID}")) is not None
    kayitlar = _gozlem_kayitlari(caplog)
    assert len(kayitlar) == 1
    assert kayitlar[0].levelno == logging.WARNING
    assert "access_as_user=False" in kayitlar[0].getMessage()


def test_scp_yanlis_token_kabul_ama_warning(anahtar, caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        token = _token(anahtar, aud=f"api://{CLIENT_ID}", scp="User.Read")
        assert AuthVerifier.verify_token(token) is not None
    kayitlar = _gozlem_kayitlari(caplog)
    assert len(kayitlar) == 1
    assert "'User.Read'" in kayitlar[0].getMessage()


def test_ciplak_client_id_audience_kabul_ama_bir_kez_warning(anahtar, caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(_token(anahtar, aud=CLIENT_ID, scp="access_as_user")) is not None
    kayitlar = _gozlem_kayitlari(caplog)
    assert len(kayitlar) == 1
    assert "ciplak_client_id=True" in kayitlar[0].getMessage()
    assert CLIENT_ID in kayitlar[0].getMessage()


def test_api_onekli_aud_ve_dogru_scp_warning_basmiyor(anahtar, caplog):
    """Hedef biçim (api:// aud + access_as_user scp) gözlem üretmez."""
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        token = _token(anahtar, aud=f"api://{CLIENT_ID}", scp="access_as_user Baska.Scope")
        assert AuthVerifier.verify_token(token) is not None
    assert _gozlem_kayitlari(caplog) == []


def test_gozlem_log_seli_yok_ayni_surecte_tek_warning(anahtar, caplog):
    with caplog.at_level(logging.WARNING, logger="AuthVerifier"):
        for _ in range(3):
            assert AuthVerifier.verify_token(_token(anahtar)) is not None
    assert len(_gozlem_kayitlari(caplog)) == 1


def test_gozlem_logunda_ham_token_yok(anahtar, caplog):
    token = _token(anahtar)
    with caplog.at_level(logging.DEBUG, logger="AuthVerifier"):
        assert AuthVerifier.verify_token(token) is not None
    for r in caplog.records:
        assert token not in r.getMessage()
        # imza parçası bile sızmamalı
        assert token.rsplit(".", 1)[1] not in r.getMessage()


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
