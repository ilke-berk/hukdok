"""G099: `cache_manager.ensure_cache_dir` iki worker'ın makedirs yarışında
sahte ERROR basmamalı.

Eski kod `exists` → `makedirs` sırasıyla TOCTOU'ya açıktı: 2 uvicorn worker
aynı anda girince ikincisi EEXIST ile ERROR logluyordu (2026-08-22'de iki
açılışta da gözlendi). `exist_ok=True` ile dizin varken/yokken sessiz; gerçek
hata (izin) hâlâ tek ERROR ve istisna çağırana yükselmez.

Handler doğrudan "CacheManager" logger'ına takılır (caplog değil — repo
deseni, bkz. test_g093_config_warnings).
"""
import logging
import os
import threading

import pytest

from managers import cache_manager


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def kayitlar():
    logger = logging.getLogger("CacheManager")
    handler = _ListHandler()
    eski_seviye = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(eski_seviye)


@pytest.fixture
def cache_dizini(tmp_path, monkeypatch):
    hedef = tmp_path / "HukuDok" / "cache"
    monkeypatch.setattr(cache_manager, "CACHE_DIR", hedef)
    return hedef


def test_dizin_zaten_varken_hic_log_yok(cache_dizini, kayitlar):
    """Yarışı kaybeden worker'ın gördüğü durum: dizin var. ERROR OLMAMALI."""
    cache_dizini.mkdir(parents=True)
    cache_manager.ensure_cache_dir()
    assert cache_dizini.is_dir()
    assert kayitlar == []


def test_dizin_yokken_yaratilir_ve_log_yok(cache_dizini, kayitlar):
    assert not cache_dizini.exists()
    cache_manager.ensure_cache_dir()
    assert cache_dizini.is_dir()
    assert kayitlar == []


def test_exist_ok_kullaniliyor_on_kontrol_yok(cache_dizini, monkeypatch):
    """Yarışın kendisi `exists` ön kontrolüydü; makedirs exist_ok=True ile
    çağrılmalı. Çağrı argümanı casuslanır."""
    cagrilar = []

    def sahte_makedirs(path, *args, **kwargs):
        cagrilar.append((path, kwargs))

    monkeypatch.setattr(os, "makedirs", sahte_makedirs)
    cache_manager.ensure_cache_dir()
    assert len(cagrilar) == 1
    assert cagrilar[0][1].get("exist_ok") is True


def test_gercek_hata_tek_ERROR_ve_istisna_yukselmez(cache_dizini, kayitlar, monkeypatch):
    """İzin hatası gerçek başarısızlıktır: tek ERROR; açılış cache yüzünden durmaz."""

    def patlayan_makedirs(path, *args, **kwargs):
        raise PermissionError("salt-okunur dosya sistemi")

    monkeypatch.setattr(os, "makedirs", patlayan_makedirs)
    cache_manager.ensure_cache_dir()  # istisna fırlatmamalı
    hatalar = [r for r in kayitlar if r.levelno == logging.ERROR]
    assert len(hatalar) == 1
    assert "salt-okunur" in hatalar[0].getMessage()


def test_eszamanli_cagrilar_ERROR_basmaz(cache_dizini, kayitlar):
    """2 worker senaryosu: aynı anda N çağrı → dizin var, hiçbir ERROR yok.
    exist_ok ile sonuç deterministiktir; test bunu kilitler."""
    engel = threading.Barrier(8)

    def calistir():
        engel.wait()
        cache_manager.ensure_cache_dir()

    isler = [threading.Thread(target=calistir) for _ in range(8)]
    for t in isler:
        t.start()
    for t in isler:
        t.join()
    assert cache_dizini.is_dir()
    assert [r for r in kayitlar if r.levelno >= logging.WARNING] == []
