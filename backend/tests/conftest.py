"""Ortak test altyapısı.

Uygulama modüllerinin import zinciri yan etki taşır; saf birim testleri
DB'ye/ağa/keyring'e dokunmadan çalışsın diye burada üç önlem alınır:

1. database.py, DATABASE_URL postgresql değilse sys.exit(1) çağırır → herhangi
   bir app modülü import edilmeden ÖNCE dummy bir URL set edilir. create_engine
   bağlantı açmaz (lazy); bu testler hiçbir zaman gerçek sorgu çalıştırmaz.
   TEK İSTİSNA: tests/test_migration_path.py (dbtest marker'lı) bilinçli olarak
   gerçek Postgres'e bağlanır — ama buradaki dummy URL'e/global engine'e kalıcı
   dokunmaz: kendi scratch veritabanını yaratıp düşürür, DB yoksa SKIP olur.
2. vault.py import'u keyring/dosya sistemine dokunabilir (CI ortamında keyring
   backend'i yok) → hafif bir stub ile değiştirilir. get_secret env'e düşer.
3. TechnicalLogger ERROR/CRITICAL loglarda SharePoint'e senkron upload dener →
   autouse fixture ile no-op'lanır (testte ağ çağrısı yasak).
"""
import os
import sys
import tempfile
import types

import pytest

# (1) DB guard — app modüllerinden önce çalışmalı
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@localhost:5432/hukudok_test"
)

# (1b) Faz 3-E: PROCESS_CACHE/DOWNLOAD_CACHE disk destekli (DiskTTLCache) ve
# dizinleri modül import'unda çözülür — test koşusu gerçek backend/data (konteynerde
# /app/data volume'ü!) dizinlerini kirletmesin diye app modülleri import edilmeden
# ÖNCE geçici dizine yönlendirilir. setdefault: bilinçli dış override'a saygı.
_CACHE_TMP = tempfile.mkdtemp(prefix="hukdok-test-cache-")
os.environ.setdefault("PROCESS_CACHE_DIR", os.path.join(_CACHE_TMP, "process"))
os.environ.setdefault("DOWNLOAD_CACHE_DIR", os.path.join(_CACHE_TMP, "download"))
# Faz 3-F: conversion spool da aynı gerekçeyle tmp'ye (dizin çağrı anında
# çözülür ama testin gerçek /app/data'ya yazmaması için emniyet ağı).
os.environ.setdefault("CONVERSION_SPOOL_DIR", os.path.join(_CACHE_TMP, "conversion"))

# (2) vault stub — gerçek modülün public API'siyle aynı imzalar
if "vault" not in sys.modules:
    _vault = types.ModuleType("vault")
    _vault.get_secret = lambda key_name: os.getenv(key_name) or None
    _vault.sync_env_to_vault_if_needed = lambda: None
    _vault.migrate_all = lambda: None
    sys.modules["vault"] = _vault


@pytest.fixture(autouse=True)
def _no_cloud_sync(monkeypatch):
    """(3) TechnicalLogger buluta senkronu her testte kapat."""
    from managers.log_manager import TechnicalLogger

    monkeypatch.setattr(TechnicalLogger, "sync_to_cloud", staticmethod(lambda: None))


@pytest.fixture(autouse=True)
def _clean_health_signals():
    """/healthz süreç-global sinyallerini (Faz 2-A) her testten önce sıfırla.

    Gemini hata yollarını tetikleyen testler (faz0, analyzer, email_sender)
    health.py sayaçlarını doldurur; healthz testleri deterministik durum
    bekler. api import edilmişse endpoint'in TTL cache'i de temizlenir —
    yoksa bir testin 503'ü sonraki testin /healthz yanıtına sızar.
    Faz 3-C devre kesici state'i de süreç-globaldir → aynı gerekçeyle sıfırlanır.
    """
    import gemini_client
    import health

    health.reset_for_tests()
    gemini_client.reset_circuits_for_tests()
    if "api" in sys.modules:
        api = sys.modules["api"]
        with api._healthz_lock:
            api._healthz_cache.update(at=0.0, payload=None, code=200)
    yield
