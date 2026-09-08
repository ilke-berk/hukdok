"""G147 — Teslim hattı ikinci SharePoint kimliği/site'ı (`config_type="teslim"`).

Görev: gorevler/gorev/G147.md. Veri ekibi Hanyaloğlu tenant'ında, arşiv site'ı
LexisBio'da; yalnız teslim hattı (gözcü listeleme/indirme + cevap paketi) ikinci
kimlik/site ile gider, arşiv/outbox/sayaç/e-posta `default` ile aynen kalır.

Katmanlar (ağa çıkılmaz — conftest sözleşmesi; msal app ve session sahte):

1. `auth_graph._get_msal_app("teslim")` — üç env doluyken `TESLIM_*` ile kurulur;
   biri boşken default sete düşer + BİR KEZ INFO; `_MSAL_APPS` iki anahtarı ayrı tutar;
   secret önce vault; secret log'a sızmaz.
2. `sharepoint_uploader_graph._get_site_and_drive_id(token, "teslim")` — site URL ve
   drive adı önceliği; cache anahtarı `(token, config_type)`, `maxsize>=2`: iki config
   art arda çağrılınca ikinci turda Graph'a GİTMEZ.
3. `list_folder_children` / `download_file_from_sharepoint` / `upload_file_to_sharepoint`
   `config_type="teslim"` ile token'ı o config'le alır, 401'de AYNI config'i yeniler;
   config'siz çağrı `"default"` (outbox yolu değişmedi).
4. `sharepoint_tara` ve `teslim_cevap.cevap_yukle` sahte `_spu` fonksiyonlarına
   `config_type="teslim"` geçer (G109/G110 sqlite kalıbı).
5. `check_client_secret_expiry(env_name=...)` ikinci env adıyla aynı üç dal; lifespan
   ikinci çağrıyı taşır.
"""
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sharepoint.auth_graph as auth_graph
import sharepoint.sharepoint_uploader_graph as spu
from database import Base
from services import app_settings
from services import teslim_cevap as tc
from services import teslim_kutusu as tk
from test_faz3_graph_retry import _FakeResponse, _FakeSession, _ListHandler
from test_g107_teslim_kutusu import _iki_satir, _index_ops, _kart, _paket
from test_g110_teslim_cevap import _anahtar, _dort_satir, _teslim, _uygulanmis_teslim

TESLIM_SITE = "https://hanyaloglu.sharepoint.com/sites/hukdok_arsiv"
ARSIV_SITE = "https://lexisbio.sharepoint.com/sites/hukukarsivtest"
ADMIN = "yonetici@hanyaloglu-acar.av.tr"
GIZLI_TESLIM = "teslim-gizli-deger-XYZ"
GIZLI_ARSIV = "arsiv-gizli-deger-ABC"


# ═══════════════════════════════════════════════════════════════════════════
# Ortak sahteler
# ═══════════════════════════════════════════════════════════════════════════

class _FakeMsalApp:
    """`msal.ConfidentialClientApplication` yerine: kurucu argümanlarını saklar."""
    kurulanlar: list = []

    def __init__(self, client_id, authority, client_credential):
        self.client_id = client_id
        self.authority = authority
        self.client_credential = client_credential
        _FakeMsalApp.kurulanlar.append(self)


@pytest.fixture()
def msal_sahte(monkeypatch):
    """msal app sahte + `.env` yüklemesi kapalı (override=True env'i ezerdi) + vault boş
    (env'e düşer) + `_MSAL_APPS` ve düşüş bayrağı temiz; test sonunda anahtarlar `pop`."""
    _FakeMsalApp.kurulanlar = []
    monkeypatch.setattr(auth_graph.msal, "ConfidentialClientApplication", _FakeMsalApp)
    monkeypatch.setattr(auth_graph, "_load_env", lambda: None)
    monkeypatch.setattr(auth_graph.vault, "get_secret", lambda key: None)
    monkeypatch.setattr(auth_graph, "_teslim_dusus_loglandi", False)
    for anahtar in ("default", "teslim"):
        auth_graph._MSAL_APPS.pop(anahtar, None)
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "tenant-arsiv")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "client-arsiv")
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", GIZLI_ARSIV)
    monkeypatch.setenv("TESLIM_SHAREPOINT_TENANT_ID", "tenant-teslim")
    monkeypatch.setenv("TESLIM_SHAREPOINT_CLIENT_ID", "client-teslim")
    monkeypatch.setenv("TESLIM_SHAREPOINT_CLIENT_SECRET", GIZLI_TESLIM)
    yield _FakeMsalApp
    for anahtar in ("default", "teslim"):
        auth_graph._MSAL_APPS.pop(anahtar, None)


@pytest.fixture()
def auth_records():
    """AuthGraph logger'ına liste handler; düşüş INFO'sunu görmek için seviye geçici INFO
    (dictConfig'in bıraktığı seviye WARNING olabilir; test sonunda geri alınır)."""
    handler = _ListHandler()
    target = logging.getLogger("AuthGraph")
    eski_seviye = target.level
    target.setLevel(logging.INFO)
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)
    target.setLevel(eski_seviye)


@pytest.fixture()
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(spu, "_get_shared_session", lambda: session)
    monkeypatch.setattr(spu, "_load_env", lambda: None)
    return session


@pytest.fixture()
def id_calls(monkeypatch):
    """`_get_site_and_drive_id` sahtesi: gelen config_type'ları kaydeder."""
    calls = []

    def fake_ids(token, config_type="default"):
        calls.append(config_type)
        return ("site-1", "drive-1")

    monkeypatch.setattr(spu, "_get_site_and_drive_id", fake_ids)
    return calls


@pytest.fixture()
def token_calls(monkeypatch):
    """`spu.get_graph_token` sahtesi: `(config_type, force_refresh)` çiftlerini kaydeder."""
    calls = []

    def fake_token(config_type="default", force_refresh=False):
        calls.append((config_type, force_refresh))
        return f"tok{len(calls)}"

    monkeypatch.setattr(spu, "get_graph_token", fake_token)
    return calls


def _infolar(records):
    return [r.getMessage() for r in records if r.levelno == logging.INFO and "arşiv kimliği" in r.getMessage()]


# ═══════════════════════════════════════════════════════════════════════════
# 1. auth_graph — ikinci kimlik seti
# ═══════════════════════════════════════════════════════════════════════════

class TestMsalApp:
    def test_teslim_ucu_doluyken_teslim_setiyle_kurulur(self, msal_sahte, auth_records):
        """Kabul: `TESLIM_SHAREPOINT_*` üçlüsü doluyken teslim tenant/client ile kurulur, INFO yok."""
        app = auth_graph._get_msal_app("teslim")

        assert app.client_id == "client-teslim"
        assert app.authority == "https://login.microsoftonline.com/tenant-teslim"
        assert app.client_credential == GIZLI_TESLIM
        assert _infolar(auth_records) == []

    def test_default_degismedi(self, msal_sahte):
        app = auth_graph._get_msal_app()
        assert (app.client_id, app.authority) == ("client-arsiv", "https://login.microsoftonline.com/tenant-arsiv")
        assert app.client_credential == GIZLI_ARSIV

    @pytest.mark.parametrize("eksik", [
        "TESLIM_SHAREPOINT_TENANT_ID", "TESLIM_SHAREPOINT_CLIENT_ID", "TESLIM_SHAREPOINT_CLIENT_SECRET",
    ])
    def test_biri_bosken_default_sete_duser_info_tek_sefer(self, msal_sahte, auth_records, monkeypatch, eksik):
        """Kabul: dörtlüden biri boşsa default kimlik, tek INFO; istisna yok."""
        monkeypatch.delenv(eksik, raising=False)

        app = auth_graph._get_msal_app("teslim")

        assert app.client_id == "client-arsiv"
        assert app.authority == "https://login.microsoftonline.com/tenant-arsiv"
        assert app.client_credential == GIZLI_ARSIV
        assert len(_infolar(auth_records)) == 1
        assert "TESLIM_SHAREPOINT_TENANT_ID" in _infolar(auth_records)[0]

        # Yeniden kurulsa da (force_refresh eski-msal yolu app'i düşürür) INFO ikilenmez
        auth_graph._MSAL_APPS.pop("teslim")
        auth_graph._get_msal_app("teslim")
        assert len(_infolar(auth_records)) == 1

    def test_bos_dize_de_tanimsiz_sayilir(self, msal_sahte, auth_records, monkeypatch):
        monkeypatch.setenv("TESLIM_SHAREPOINT_TENANT_ID", "   ")
        app = auth_graph._get_msal_app("teslim")
        assert app.client_id == "client-arsiv"
        assert len(_infolar(auth_records)) == 1

    def test_msal_apps_iki_anahtari_ayri_tutar(self, msal_sahte):
        """Kabul: `_MSAL_APPS` anahtarı config_type; iki app ayrı nesne, ayrı token cache."""
        varsayilan = auth_graph._get_msal_app("default")
        teslim = auth_graph._get_msal_app("teslim")

        assert auth_graph._MSAL_APPS["default"] is varsayilan
        assert auth_graph._MSAL_APPS["teslim"] is teslim
        assert varsayilan is not teslim
        assert auth_graph._get_msal_app("teslim") is teslim  # cache
        assert len(msal_sahte.kurulanlar) == 2

    def test_dususte_bile_teslim_anahtari_ayri_app(self, msal_sahte, monkeypatch):
        """Düşüşte default kimlik kullanılır ama anahtar `teslim` kalır — `force_refresh`
        yolu (`_MSAL_APPS.pop(config_type)`) config'e sadık kalsın."""
        monkeypatch.delenv("TESLIM_SHAREPOINT_CLIENT_SECRET", raising=False)
        varsayilan = auth_graph._get_msal_app("default")
        teslim = auth_graph._get_msal_app("teslim")
        assert teslim is not varsayilan and set(auth_graph._MSAL_APPS) >= {"default", "teslim"}

    def test_secret_once_vault_sonra_env(self, msal_sahte, monkeypatch):
        """Kabul: secret sırası default ile aynı — vault dolu ise env'i ezer."""
        sorulan = []

        def vault_secret(key):
            sorulan.append(key)
            return "vault-teslim" if key == "TESLIM_SHAREPOINT_CLIENT_SECRET" else None

        monkeypatch.setattr(auth_graph.vault, "get_secret", vault_secret)
        app = auth_graph._get_msal_app("teslim")
        assert app.client_credential == "vault-teslim"
        assert sorulan == ["TESLIM_SHAREPOINT_CLIENT_SECRET"]

    def test_tenant_veya_client_yokken_vault_sorulmaz(self, msal_sahte, monkeypatch):
        """Vault bulamayınca WARNING basar; teslim tanımsız prod'da her açılışta sahte
        uyarı olmasın diye tenant/client boşsa secret hiç aranmaz."""
        sorulan = []
        monkeypatch.setattr(auth_graph.vault, "get_secret", lambda key: sorulan.append(key))
        monkeypatch.delenv("TESLIM_SHAREPOINT_TENANT_ID", raising=False)
        auth_graph._get_msal_app("teslim")
        assert sorulan == ["SHAREPOINT_CLIENT_SECRET"]  # yalnız default seti

    def test_secret_loga_sizmaz(self, msal_sahte, auth_records, monkeypatch):
        auth_graph._get_msal_app("teslim")
        monkeypatch.delenv("TESLIM_SHAREPOINT_CLIENT_ID", raising=False)
        auth_graph._MSAL_APPS.pop("teslim")
        auth_graph._get_msal_app("teslim")
        for rec in auth_records:
            assert GIZLI_TESLIM not in rec.getMessage() and GIZLI_ARSIV not in rec.getMessage()

    def test_bilinmeyen_config_valueerror(self, msal_sahte):
        """`"upload"` dalı ölü koddu: config uzayı `default | teslim`."""
        with pytest.raises(ValueError, match="upload"):
            auth_graph._get_msal_app("upload")
        assert "upload" not in auth_graph._MSAL_APPS

    def test_get_graph_token_teslim_configi_ile_app_secer(self, msal_sahte, monkeypatch):
        """`get_graph_token("teslim", force_refresh=True)` teslim app'ini yeniler, default'a dokunmaz."""
        secilen = []

        class _App:
            def __init__(self, ad):
                self.ad = ad

            def remove_tokens_for_client(self):
                secilen.append(("remove", self.ad))

            def acquire_token_for_client(self, scopes):
                secilen.append(("acquire", self.ad))
                return {"access_token": f"tok-{self.ad}"}

        apps = {"default": _App("default"), "teslim": _App("teslim")}
        monkeypatch.setattr(auth_graph, "_get_msal_app", lambda config_type="default": apps[config_type])

        assert auth_graph.get_graph_token("teslim", force_refresh=True) == "tok-teslim"
        assert secilen == [("remove", "teslim"), ("acquire", "teslim")]


# ═══════════════════════════════════════════════════════════════════════════
# 2. site/drive çözümü — config'e göre + cache anahtarı
# ═══════════════════════════════════════════════════════════════════════════

def _site_yaniti(site_id):
    return _FakeResponse(200, {"id": site_id})


def _drive_yaniti(*adlar):
    return _FakeResponse(200, {"value": [{"id": f"drive-{ad}", "name": ad} for ad in adlar]})


@pytest.fixture()
def site_env(monkeypatch):
    spu._get_site_and_drive_id.cache_clear()
    monkeypatch.setenv("SHAREPOINT_SITE_URL", ARSIV_SITE)
    for ad in ("TESLIM_SHAREPOINT_SITE_URL", "TESLIM_SP_DRIVE_NAME", "SP_DRIVE_NAME"):
        monkeypatch.delenv(ad, raising=False)
    yield
    spu._get_site_and_drive_id.cache_clear()


class TestSiteAndDrive:
    def test_teslim_site_url_doluyken_o_host_ve_yol(self, fake_session, site_env, monkeypatch):
        """Kabul: `TESLIM_SHAREPOINT_SITE_URL` doluyken Graph `sites/{host}:{path}` o host/path ile."""
        monkeypatch.setenv("TESLIM_SHAREPOINT_SITE_URL", TESLIM_SITE)
        fake_session.get_script = [_site_yaniti("site-h"), _drive_yaniti("Belgeler", "Documents")]

        assert spu._get_site_and_drive_id("tok-t", "teslim") == ("site-h", "drive-Belgeler")

        assert fake_session.gets[0]["url"] == f"{spu.GRAPH}/sites/hanyaloglu.sharepoint.com:/sites/hukdok_arsiv"
        assert fake_session.gets[0]["headers"] == {"Authorization": "Bearer tok-t"}
        assert fake_session.gets[1]["url"] == f"{spu.GRAPH}/sites/site-h/drives"

    def test_teslim_site_url_bosken_arsiv_sitesine_duser(self, fake_session, site_env):
        fake_session.get_script = [_site_yaniti("site-l"), _drive_yaniti("Belgeler")]

        assert spu._get_site_and_drive_id("tok-t", "teslim") == ("site-l", "drive-Belgeler")
        assert fake_session.gets[0]["url"] == f"{spu.GRAPH}/sites/lexisbio.sharepoint.com:/sites/hukukarsivtest"

    def test_default_config_teslim_envini_gormez(self, fake_session, site_env, monkeypatch):
        """Arşiv çağrıları `SHAREPOINT_SITE_URL`'de kalır — teslim env'i onları etkilemez."""
        monkeypatch.setenv("TESLIM_SHAREPOINT_SITE_URL", TESLIM_SITE)
        monkeypatch.setenv("TESLIM_SP_DRIVE_NAME", "Teslimler")
        fake_session.get_script = [_site_yaniti("site-l"), _drive_yaniti("Teslimler", "Belgeler")]

        assert spu._get_site_and_drive_id("tok-d", "default") == ("site-l", "drive-Belgeler")
        assert fake_session.gets[0]["url"].startswith(f"{spu.GRAPH}/sites/lexisbio.sharepoint.com:")

    @pytest.mark.parametrize("teslim_ad,genel_ad,beklenen", [
        ("Teslimler", "Arsiv", "Teslimler"),   # TESLIM_SP_DRIVE_NAME önce
        (None, "Arsiv", "Arsiv"),              # sonra SP_DRIVE_NAME
        (None, None, "Belgeler"),              # sonra Belgeler
        ("", "", "Belgeler"),                  # boş dize tanımsız sayılır
    ])
    def test_drive_adi_onceligi(self, fake_session, site_env, monkeypatch, teslim_ad, genel_ad, beklenen):
        if teslim_ad is not None:
            monkeypatch.setenv("TESLIM_SP_DRIVE_NAME", teslim_ad)
        if genel_ad is not None:
            monkeypatch.setenv("SP_DRIVE_NAME", genel_ad)
        fake_session.get_script = [_site_yaniti("s"), _drive_yaniti("Teslimler", "Arsiv", "Belgeler")]

        assert spu._get_site_and_drive_id("tok", "teslim") == ("s", f"drive-{beklenen}")

    def test_site_url_hic_yoksa_runtimeerror_iki_env_adiyla(self, fake_session, site_env, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_SITE_URL", raising=False)
        with pytest.raises(RuntimeError, match="TESLIM_SHAREPOINT_SITE_URL / SHAREPOINT_SITE_URL"):
            spu._get_site_and_drive_id("tok", "teslim")
        assert fake_session.gets == []

    def test_cache_anahtari_configi_ayirir_ikinci_turda_grapha_gitmez(self, fake_session, site_env, monkeypatch):
        """Kabul: anahtar `(token, config_type)`, `maxsize>=2` — aynı token farklı config iki
        ayrı çözüm (4 GET); iki config art arda tekrar çağrılınca GET sayısı artmaz."""
        monkeypatch.setenv("TESLIM_SHAREPOINT_SITE_URL", TESLIM_SITE)
        fake_session.get_script = [
            _site_yaniti("site-l"), _drive_yaniti("Belgeler"),
            _site_yaniti("site-h"), _drive_yaniti("Belgeler"),
        ]

        assert spu._get_site_and_drive_id("tok", "default") == ("site-l", "drive-Belgeler")
        assert spu._get_site_and_drive_id("tok", "teslim") == ("site-h", "drive-Belgeler")
        assert len(fake_session.gets) == 4

        # outbox upload ↔ gece gözcüsü art arda: ikinci tur cache'ten
        for _ in range(3):
            assert spu._get_site_and_drive_id("tok", "default") == ("site-l", "drive-Belgeler")
            assert spu._get_site_and_drive_id("tok", "teslim") == ("site-h", "drive-Belgeler")
        assert len(fake_session.gets) == 4
        assert spu._get_site_and_drive_id.cache_info().maxsize >= 2

    def test_maxsize_dort(self):
        assert spu._get_site_and_drive_id.cache_info().maxsize == 4


# ═══════════════════════════════════════════════════════════════════════════
# 3. Graph çağrıları — token config'i ve 401 yenilemesi config'e sadık
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigTokenYolu:
    def test_list_teslim_token_teslim_configiyle(self, fake_session, id_calls, token_calls):
        fake_session.get_script = [_FakeResponse(200, {"value": [{"id": "1", "name": "a.xlsx", "file": {}}]})]

        dosyalar = spu.list_folder_children("03_VERI_TESLIM/gelen", config_type="teslim")

        assert [d["name"] for d in dosyalar] == ["a.xlsx"]
        assert token_calls == [("teslim", False)]
        assert id_calls == ["teslim"]

    def test_list_401_ayni_configi_yeniler(self, fake_session, id_calls, token_calls):
        """Kabul: 401 → `force_refresh=True` + AYNI `config_type` (`_with_fresh_token_on_401`)."""
        fake_session.get_script = [
            _FakeResponse(401, text="token süresi doldu"),
            _FakeResponse(200, {"value": []}),
        ]

        assert spu.list_folder_children("03_VERI_TESLIM/gelen", config_type="teslim") == []
        assert token_calls == [("teslim", False), ("teslim", True)]
        assert id_calls == ["teslim", "teslim"]
        assert fake_session.gets[1]["headers"]["Authorization"] == "Bearer tok2"

    def test_download_teslim_401_ayni_configi_yeniler(self, fake_session, id_calls, token_calls):
        fake_session.get_script = [
            _FakeResponse(401),
            _FakeResponse(200, headers={"Content-Type": "application/x"}, content=b"xlsx"),
        ]

        icerik, ctype = spu.download_file_from_sharepoint("03_VERI_TESLIM/gelen", "a.xlsx", config_type="teslim")

        assert (icerik, ctype) == (b"xlsx", "application/x")
        assert token_calls == [("teslim", False), ("teslim", True)]
        assert id_calls == ["teslim", "teslim"]

    def test_upload_teslim_401_ayni_configi_yeniler(self, tmp_path, fake_session, id_calls, token_calls):
        yol = tmp_path / "eslesme.csv"
        yol.write_bytes(b"a;b\n")
        fake_session.put_script = [_FakeResponse(401), _FakeResponse(200, {"id": "it-t"})]

        data = spu.upload_file_to_sharepoint(
            str(yol), "eslesme.csv", "03_VERI_TESLIM/cevap/X", content_type="text/csv", config_type="teslim",
        )

        assert data["id"] == "it-t"
        assert token_calls == [("teslim", False), ("teslim", True)]
        assert id_calls == ["teslim", "teslim"]
        assert fake_session.puts[1]["headers"]["Authorization"] == "Bearer tok2"

    def test_geriye_uyum_configsiz_upload_default(self, tmp_path, fake_session, id_calls, token_calls):
        """Kabul: outbox yolu değişmedi — config'siz çağrı `get_graph_token("default")`."""
        yol = tmp_path / "k.pdf"
        yol.write_bytes(b"pdf")
        fake_session.put_script = [_FakeResponse(200, {"id": "it-d"})]

        spu.upload_file_to_sharepoint(str(yol), "k.pdf", "01_HAM_ARSIV")

        assert token_calls == [("default", False)]
        assert id_calls == ["default"]

    def test_geriye_uyum_configsiz_list_ve_download_default(self, fake_session, id_calls, token_calls):
        fake_session.get_script = [
            _FakeResponse(200, {"value": []}),
            _FakeResponse(200, headers={}, content=b"x"),
        ]
        spu.list_folder_children("F")
        spu.download_file_from_sharepoint("F", "a")
        assert token_calls == [("default", False), ("default", False)]
        assert id_calls == ["default", "default"]

    def test_with_fresh_token_varsayilan_default(self, token_calls):
        assert spu._with_fresh_token_on_401(lambda token: token) == "tok1"
        assert token_calls == [("default", False)]

    def test_config_type_yalniz_anahtar_argumani(self, tmp_path):
        """Keyword-only: konumsal geçilemez (mevcut çağıranların konumsal listesi bozulmasın)."""
        with pytest.raises(TypeError):
            spu.list_folder_children("F", "teslim")
        with pytest.raises(TypeError):
            spu.download_file_from_sharepoint("F", "a", "teslim")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Teslim hattı — gözcü + cevap paketi teslim config'iyle
# ═══════════════════════════════════════════════════════════════════════════

def test_teslim_sp_config_tek_sabit():
    assert tk.TESLIM_SP_CONFIG == "teslim" == auth_graph.CONFIG_TESLIM == spu.CONFIG_TESLIM


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """G110 `env` ikizi: sqlite + index'ler + spool + üç kart; cevap klasörü env'i kurulu."""
    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "03_VERI_TESLIM")
    for ad in ("TESLIM_KAPI_HATA_ORANI", "TESLIM_KAPI_ESLESMEYEN_ORANI", "TESLIM_KAPI_ALAN_DEGISIKLIGI"):
        monkeypatch.delenv(ad, raising=False)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for tablo in ("case_foys", "aktarim_teslimleri", "notifications"):
            for sql in _index_ops(tablo):
                conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(tk, "SessionLocal", maker)
    monkeypatch.setattr(app_settings, "SessionLocal", maker)

    db = maker()
    try:
        for i in (1, 2, 3):
            _kart(db, f"HA.G147.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()

    yield SimpleNamespace(db=maker, spool=tmp_path / "teslim_spool")
    engine.dispose()


@pytest.fixture()
def sahte_sp(monkeypatch):
    """`_spu` üçlüsü yerine kwargs kaydeden sahteler (G109/G110 kalıbı)."""
    sp = SimpleNamespace(list_kw=[], download_kw=[], upload_kw=[])

    def _list(folder_name, **kw):
        sp.list_kw.append((folder_name, kw))
        return [{"id": "item-1", "name": "HUKDOK_TESLIM_G147.xlsx", "eTag": '"1"',
                 "file": {"mimeType": "application/octet-stream"}}]

    def _download(folder_name, filename, **kw):
        sp.download_kw.append((folder_name, filename, kw))
        return _paket(_iki_satir("g147")), "application/octet-stream"

    def _upload(filepath, target_filename, target_folder_name, content_type="application/pdf", **kw):
        sp.upload_kw.append((Path(filepath).name, target_folder_name, kw))
        return {"id": f"item-{len(sp.upload_kw)}", "name": target_filename}

    monkeypatch.setattr(spu, "list_folder_children", _list)
    monkeypatch.setattr(spu, "download_file_from_sharepoint", _download)
    monkeypatch.setattr(spu, "upload_file_to_sharepoint", _upload)
    return sp


def test_sharepoint_tara_listeleme_ve_indirme_teslim_configiyle(env, sahte_sp):
    """Kabul: gözcünün iki Graph çağrısı `config_type="teslim"` ile gider; klasör yolu aynı."""
    _anahtar(env, True)

    sayac = tk.sharepoint_tara()

    assert sayac == {"yeni": 1, "yinelenen": 0, "atlanan": 0}
    assert sahte_sp.list_kw == [("03_VERI_TESLIM/gelen", {"config_type": "teslim"})]
    assert sahte_sp.download_kw == [("03_VERI_TESLIM/gelen", "HUKDOK_TESLIM_G147.xlsx", {"config_type": "teslim"})]


def test_cevap_yukleme_teslim_configiyle(env, sahte_sp):
    """Kabul: cevap paketinin her dosyası `config_type="teslim"` ile yüklenir."""
    _anahtar(env, True)
    tid = _uygulanmis_teslim(env, satirlar=_dort_satir())
    teslim = _teslim(env, tid)

    assert teslim.durum == tk.DURUM_UYGULANDI and teslim.cevap_yuklendi is True
    assert sahte_sp.upload_kw, "cevap paketi yüklenmedi"
    assert all(kw == {"config_type": "teslim"} for _ad, _klasor, kw in sahte_sp.upload_kw)
    assert all(klasor == "03_VERI_TESLIM/cevap/HUKDOK_TESLIM_X" for _ad, klasor, _kw in sahte_sp.upload_kw)
    assert tc is not None  # modül import edildi (şerh + çağrı aynı dosyada)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Secret bitiş tarihi — ikinci env adı, lifespan ikinci çağrı
# ═══════════════════════════════════════════════════════════════════════════

TODAY = date(2026, 9, 8)
TESLIM_EXP = auth_graph.TESLIM_SECRET_EXPIRES_AT_ENV


class TestTeslimSecretExpiry:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("TESLIM_SHAREPOINT_CLIENT_SECRET", GIZLI_TESLIM)
        monkeypatch.delenv(auth_graph.SECRET_EXPIRES_AT_ENV, raising=False)
        monkeypatch.delenv(TESLIM_EXP, raising=False)

    def test_env_adi_sabit(self):
        assert TESLIM_EXP == "TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT"

    def test_tanimsiz_sessiz(self, auth_records):
        assert auth_graph.check_client_secret_expiry(today=TODAY, env_name=TESLIM_EXP) is None
        assert auth_records == []

    def test_esik_ici_warning_teslim_etiketi(self, monkeypatch, auth_records):
        monkeypatch.setenv(TESLIM_EXP, "2026-09-20")
        assert auth_graph.check_client_secret_expiry(today=TODAY, env_name=TESLIM_EXP) == "warning"
        assert len(auth_records) == 1 and auth_records[0].levelno == logging.WARNING
        mesaj = auth_records[0].getMessage()
        assert "12 gün sonra" in mesaj and "Veri teslim" in mesaj

    def test_gecmis_critical_teslim_env_adlari(self, monkeypatch, auth_records):
        monkeypatch.setenv(TESLIM_EXP, "2026-09-01")
        assert auth_graph.check_client_secret_expiry(today=TODAY, env_name=TESLIM_EXP) == "critical"
        mesaj = auth_records[0].getMessage()
        assert "DOLDU" in mesaj and "7 gün önce" in mesaj
        assert "TESLIM_SHAREPOINT_CLIENT_SECRET ve TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT" in mesaj
        assert GIZLI_TESLIM not in mesaj

    def test_bozuk_deger_warning_yok_sayilir(self, monkeypatch, auth_records):
        monkeypatch.setenv(TESLIM_EXP, "yarin")
        assert auth_graph.check_client_secret_expiry(today=TODAY, env_name=TESLIM_EXP) == "warning"
        assert "TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT" in auth_records[0].getMessage()

    def test_iki_env_birbirinden_bagimsiz(self, monkeypatch, auth_records):
        """Teslim tarihi geçmiş olsa da default çağrı (env'i boş) sessiz kalır ve tersi."""
        monkeypatch.setenv(TESLIM_EXP, "2026-09-01")
        assert auth_graph.check_client_secret_expiry(today=TODAY) is None
        assert auth_records == []
        monkeypatch.setenv(auth_graph.SECRET_EXPIRES_AT_ENV, "2027-03-15")
        monkeypatch.delenv(TESLIM_EXP, raising=False)
        assert auth_graph.check_client_secret_expiry(today=TODAY, env_name=TESLIM_EXP) is None
        assert auth_records == []

    def test_lifespan_ikinci_cagriyi_tasir(self):
        import inspect

        import api

        src = inspect.getsource(api.lifespan)
        assert "check_client_secret_expiry()" in src
        assert 'check_client_secret_expiry(env_name="TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT")' in src


# ═══════════════════════════════════════════════════════════════════════════
# 6. Ölü env adı repoda yok
# ═══════════════════════════════════════════════════════════════════════════

def test_upload_sharepoint_adi_kodda_gecmez():
    # Bayat ad parçalı yazılır: kabul grep'i (`grep -rn UPLOAD_SHAREPOINT backend docs`) bu dosyaya takılmasın.
    bayat_ad = "UPLOAD_" + "SHAREPOINT"
    kok = Path(__file__).resolve().parent.parent
    dosyalar = [p for p in kok.rglob("*.py") if "tests" not in p.parts and ".venv" not in p.parts]
    kirli = [str(p) for p in dosyalar if bayat_ad in p.read_text(encoding="utf-8", errors="ignore")]
    assert kirli == []
    ornek = kok.parent / ".env.example"
    if ornek.is_file():
        metin = ornek.read_text(encoding="utf-8")
        assert bayat_ad not in metin
        assert "TESLIM_SHAREPOINT_TENANT_ID" in metin and "TESLIM_SHAREPOINT_SITE_URL" in metin
