"""Ortak test altyapısı.

Uygulama modüllerinin import zinciri yan etki taşır; saf birim testleri
DB'ye/ağa/keyring'e dokunmadan çalışsın diye burada üç önlem alınır:

1. database.py, DATABASE_URL postgresql değilse sys.exit(1) çağırır → herhangi
   bir app modülü import edilmeden ÖNCE dummy bir URL set edilir. create_engine
   bağlantı açmaz (lazy); bu testler hiçbir zaman gerçek sorgu çalıştırmaz.
2. vault.py import'u keyring/dosya sistemine dokunabilir (CI ortamında keyring
   backend'i yok) → hafif bir stub ile değiştirilir. get_secret env'e düşer.
3. TechnicalLogger ERROR/CRITICAL loglarda SharePoint'e senkron upload dener →
   autouse fixture ile no-op'lanır (testte ağ çağrısı yasak).
"""
import os
import sys
import types

import pytest

# (1) DB guard — app modüllerinden önce çalışmalı
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@localhost:5432/hukudok_test"
)

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
