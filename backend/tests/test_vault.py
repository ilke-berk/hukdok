"""`vault.py` — sır çekme yolunun karakterizasyonu (G057).

Bu dosya yeni davranış tanımlamaz; **bugünkü sözleşmeyi dondurur.** `vault.py`
kapsam raporunda %0'dı ve her iki dış entegrasyonun da kritik yolunda:
`analyzer.py`, `gemini_client.py` (GEMINI_API_KEY) ve `sharepoint/auth_graph.py`
(SHAREPOINT_CLIENT_SECRET). Bu sınıf iki kez prod arızası üretti (2026-07-13
confirm 500'ü, 2026-07-10 hukukbot 403'ü).

GÜVENLİK KURALI — bu dosyadaki hiçbir test gerçek keyring'e ya da gerçek `.env`e
DOKUNMAZ. Backend sahte bir nesneyle değiştirilir, `.env` `tmp_path`e yazılır,
senkron durumu izole edilir. Test hiçbir koşulda diske gerçek sır yazamaz.
"""
import importlib.util
import logging
from pathlib import Path

import pytest

# KAPSAMIN %0 OLMASININ SEBEBİ BUYDU — ihmal değil, düzenek.
# `conftest.py:41-46` `sys.modules["vault"]`i hafif bir stub ile değiştiriyor
# (bilinçli: saf birim testleri keyring'e/dosya sistemine dokunmasın). Sonuç:
# düz `import vault` bu dosyada da stub'ı getirir ve gerçek `vault.py` test
# koşusunda HİÇ import edilmez → kapsam %0 görünür.
# Stub'a DOKUNMUYORUZ (diğer ~1200 test ona yaslanıyor); gerçek modülü dosya
# yolundan ayrı bir adla yüklüyoruz. Kapsam dosya yoluna göre sayıldığı için
# `vault.py` bu koşuda gerçekten ölçülür.
_VAULT_PATH = Path(__file__).resolve().parent.parent / "vault.py"
_spec = importlib.util.spec_from_file_location("vault_gercek", _VAULT_PATH)
vault = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vault)


class _SahteBackend:
    """keyring backend taklidi — modül adı `type()` üzerinden okunduğu için
    gerçek bir sınıf gerekiyor; alt sınıflarla modül adı değiştirilir."""

    def __init__(self, deger=None, patlat=False):
        self.deger = deger
        self.patlat = patlat
        self.yazilanlar = {}

    def get_password(self, servis, anahtar):
        if self.patlat:
            raise RuntimeError("vault erisilemez")
        return self.deger

    def set_password(self, servis, anahtar, deger):
        if self.patlat:
            raise RuntimeError("vault yazilamaz")
        self.yazilanlar[anahtar] = deger


class _DuzMetinBackend(_SahteBackend):
    """`keyrings.alt` ailesini taklit eder — modül adı testte zorlanır."""


# `_backend_write_safe` modül ADINA bakıyor; sahte sınıfın modülü bu test
# dosyası olduğu için düz metin taklidini adıyla zorluyoruz.
_DuzMetinBackend.__module__ = "keyrings.alt.file"


@pytest.fixture(autouse=True)
def _izole(monkeypatch, tmp_path):
    """Her testi gerçek dünyadan yalıtır: keyring, .env yolu, senkron durumu."""
    monkeypatch.setattr(vault, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(vault, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(vault, "SYNC_STATE_FILE", tmp_path / "state" / "vault_sync.json")
    monkeypatch.setattr(vault, "_unsafe_backend_warned", False)
    # Varsayılan: güvenli ama boş backend. Testler gerektiğinde değiştirir.
    _kur(monkeypatch, _SahteBackend())
    # Ortam değişkenleri sızmasın
    for k in vault.KEYS_TO_MIGRATE:
        monkeypatch.delenv(k, raising=False)
    yield


def _kur(monkeypatch, backend):
    """Aktif keyring'i sahte backend ile değiştirir."""
    monkeypatch.setattr(vault.keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(vault.keyring, "get_password", backend.get_password)
    monkeypatch.setattr(vault.keyring, "set_password", backend.set_password)
    return backend


# ── get_secret: okuma yolu ───────────────────────────────────────────────────

def test_keyring_deger_dondururse_o_kullanilir(monkeypatch):
    _kur(monkeypatch, _SahteBackend(deger="vault-degeri"))
    assert vault.get_secret("GEMINI_API_KEY") == "vault-degeri"


def test_keyring_None_dondurunce_env_fallbacki_calisiyor(monkeypatch):
    """PROD'UN GERÇEK YOLU: konteynerde backend null → get_password None döner."""
    _kur(monkeypatch, _SahteBackend(deger=None))
    monkeypatch.setenv("GEMINI_API_KEY", "env-degeri")
    assert vault.get_secret("GEMINI_API_KEY") == "env-degeri"


def test_keyring_patlarsa_da_env_fallbacki_calisiyor(monkeypatch, caplog):
    """Keyring istisnası sırrı KAYBETTİRMEZ; tek ERROR log'lanır."""
    _kur(monkeypatch, _SahteBackend(patlat=True))
    monkeypatch.setenv("GEMINI_API_KEY", "env-degeri")
    with caplog.at_level(logging.ERROR, logger="Vault"):
        assert vault.get_secret("GEMINI_API_KEY") == "env-degeri"
    hatalar = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(hatalar) == 1, "nihai olmayan bir hata için tek ERROR (log sözleşmesi)"


def test_hicbir_yerde_yoksa_None_ve_WARNING(monkeypatch, caplog):
    """Sessiz boş dize DEĞİL: çağıran 'anahtar yok'u ayırt edebilmeli."""
    _kur(monkeypatch, _SahteBackend(deger=None))
    with caplog.at_level(logging.WARNING, logger="Vault"):
        assert vault.get_secret("GEMINI_API_KEY") is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_loglara_sirrin_DEGERI_yazilmiyor(monkeypatch, caplog):
    """Sızıntı kapısı: log'da anahtar ADI olabilir, DEĞERİ asla."""
    _kur(monkeypatch, _SahteBackend(patlat=True))
    monkeypatch.setenv("GEMINI_API_KEY", "COK-GIZLI-DEGER-42")
    with caplog.at_level(logging.DEBUG, logger="Vault"):
        vault.get_secret("GEMINI_API_KEY")
    tum_log = " ".join(r.getMessage() for r in caplog.records)
    assert "COK-GIZLI-DEGER-42" not in tum_log
    assert "GEMINI_API_KEY" in tum_log or tum_log  # anahtar adı serbest


# ── sync_env_to_vault_if_needed: yazma yolu ──────────────────────────────────

def test_env_yoksa_hicbir_sey_yazilmiyor(monkeypatch):
    backend = _kur(monkeypatch, _SahteBackend())
    vault.sync_env_to_vault_if_needed()
    assert backend.yazilanlar == {}


def test_env_bayatsa_hicbir_sey_yazilmiyor(monkeypatch, tmp_path):
    """`.env` son senkrondan yeni DEĞİLSE yazma yoluna hiç girilmez."""
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=x\n", encoding="utf-8")
    backend = _kur(monkeypatch, _SahteBackend())
    monkeypatch.setattr(vault, "_get_last_synced_mtime", lambda: env.stat().st_mtime + 100)
    vault.sync_env_to_vault_if_needed()
    assert backend.yazilanlar == {}


def test_env_yeniyse_yalniz_KEYS_TO_MIGRATE_yaziliyor(monkeypatch, tmp_path):
    """Alakasız anahtarlar vault'a taşınmaz — yüzey dar tutulur."""
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=g-degeri\n"
        "SHAREPOINT_CLIENT_SECRET=s-degeri\n"
        "DATABASE_URL=postgresql://alakasiz\n",
        encoding="utf-8",
    )
    backend = _kur(monkeypatch, _SahteBackend())
    monkeypatch.setattr(vault, "_get_last_synced_mtime", lambda: 0.0)
    vault.sync_env_to_vault_if_needed()
    assert set(backend.yazilanlar) == set(vault.KEYS_TO_MIGRATE)
    assert "DATABASE_URL" not in backend.yazilanlar


# ── Düz metin backend koruması (G057'nin asıl bulgusu) ───────────────────────

def test_duz_metin_backendde_sir_YAZILMIYOR(monkeypatch, tmp_path, caplog):
    """`PYTHON_KEYRING_BACKEND` düşerse keyring önceliğe göre seçer ve bu imajda
    en yüksek öncelikli kurulu backend `keyrings.alt.file.PlaintextKeyring`tir.
    O durumda sırlar düz metin dosyaya yazılırdı — bu kapı onu keser."""
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g\nSHAREPOINT_CLIENT_SECRET=s\n", encoding="utf-8")
    backend = _kur(monkeypatch, _DuzMetinBackend())
    monkeypatch.setattr(vault, "_get_last_synced_mtime", lambda: 0.0)

    with caplog.at_level(logging.WARNING, logger="Vault"):
        vault.sync_env_to_vault_if_needed()

    assert backend.yazilanlar == {}, "düz metin backend'e sır YAZILDI — koruma delinmiş"
    assert any("DÜZ METİN" in r.getMessage() for r in caplog.records)


def test_duz_metin_uyarisi_surec_basina_BIR_kez(monkeypatch, tmp_path, caplog):
    """`get_secret` her çağrıda senkronu yokluyor; uyarı her seferinde basarsa
    log sözleşmesi gürültüye boğulur."""
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g\n", encoding="utf-8")
    _kur(monkeypatch, _DuzMetinBackend())
    monkeypatch.setattr(vault, "_get_last_synced_mtime", lambda: 0.0)

    with caplog.at_level(logging.WARNING, logger="Vault"):
        for _ in range(5):
            vault.sync_env_to_vault_if_needed()

    uyarilar = [r for r in caplog.records if "DÜZ METİN" in r.getMessage()]
    assert len(uyarilar) == 1, f"5 çağrıda {len(uyarilar)} uyarı — bir kez olmalıydı"


def test_duz_metin_backendde_OKUMA_hala_calisiyor(monkeypatch):
    """Koruma yalnız YAZMAYI keser; okuma yolu (env fallback) bozulmaz —
    yani işlevsel kayıp yok, uygulama sırrını almaya devam eder."""
    _kur(monkeypatch, _DuzMetinBackend(deger=None))
    monkeypatch.setenv("GEMINI_API_KEY", "env-degeri")
    assert vault.get_secret("GEMINI_API_KEY") == "env-degeri"


def test_backend_cozulemezse_yazilmiyor_ama_patlamiyor(monkeypatch, tmp_path):
    """`get_keyring()` istisna atarsa: sır yazma YOK, çağıran çökmüyor."""
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g\n", encoding="utf-8")

    def _patla():
        raise RuntimeError("backend cozulemedi")

    monkeypatch.setattr(vault.keyring, "get_keyring", _patla)
    monkeypatch.setattr(vault, "_get_last_synced_mtime", lambda: 0.0)
    vault.sync_env_to_vault_if_needed()  # istisna sızmamalı

    guvenli, ad = vault._backend_write_safe()
    assert guvenli is False
    assert "okunamadı" in ad


def test_null_backend_guvenli_sayiliyor(monkeypatch):
    """Prod'un gerçek yapılandırması (`keyring.backends.null.Keyring`) kapıya
    TAKILMAMALI — o backend zaten hiçbir şey saklamıyor, yazma no-op."""
    import keyring.backends.null

    _kur(monkeypatch, keyring.backends.null.Keyring())
    guvenli, ad = vault._backend_write_safe()
    assert guvenli is True
    assert ad == "keyring.backends.null.Keyring"
