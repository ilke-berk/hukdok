"""G268 — DOWNLOAD_CACHE payload temizliği (plan K2, §5 "payload temizliği").

`routes.processing._cleanup_process_cache` TTL'i dolan DOWNLOAD_CACHE kayıtlarından YALNIZ
`kaynak == "pdf_araclari"` olanların dosyasını siler; `/confirm` kayıtlarının dosyası eskisi gibi
`schedule_cleanup`'a bırakılır (dokunulmaz). PDF aracı uçları isteğin başında bu süpürmeyi çağırır.
"""
import os
import time

import pytest


@pytest.fixture()
def cache(monkeypatch, tmp_path):
    from managers.ttl_cache import DiskTTLCache
    from routes import processing

    yeni = DiskTTLCache(tmp_path / "download", ttl_seconds=60)
    monkeypatch.setattr(processing, "DOWNLOAD_CACHE", yeni)
    return yeni


def _eskit(cache, key, saniye=120):
    meta = cache._meta_path(key)
    eski = time.time() - saniye
    os.utime(meta, (eski, eski))


def test_pdf_araclari_payloadi_silinir_process_kaydi_kalir(cache, tmp_path):
    from routes.processing import _cleanup_process_cache

    pdf_arac = tmp_path / "arac.pdf"
    confirm = tmp_path / "confirm.pdf"
    pdf_arac.write_bytes(b"%PDF-1.4 arac")
    confirm.write_bytes(b"%PDF-1.4 confirm")
    cache.set("arac-1", {"path": str(pdf_arac), "filename": "a.pdf", "owner": "x", "kaynak": "pdf_araclari"})
    cache.set("confirm-1", {"path": str(confirm), "filename": "c.pdf", "owner": "x"})
    cache.set("taze-1", {"path": str(pdf_arac), "filename": "t.pdf", "owner": "x", "kaynak": "pdf_araclari"})
    _eskit(cache, "arac-1")
    _eskit(cache, "confirm-1")

    _cleanup_process_cache()

    assert not pdf_arac.exists(), "pdf_araclari payload'ı silinmeli"
    assert confirm.exists(), "/confirm kaydının dosyasına dokunulmaz"
    assert cache.get("arac-1") is None and cache.get("confirm-1") is None
    assert cache.get("taze-1") is not None  # TTL dolmayan girdi kalır


def test_evict_yoksa_dosya_hatasi_yutulur(cache, tmp_path):
    from routes.processing import _cleanup_process_cache

    cache.set("arac-2", {"path": str(tmp_path / "yok.pdf"), "filename": "a.pdf", "owner": "x", "kaynak": "pdf_araclari"})
    _eskit(cache, "arac-2")
    _cleanup_process_cache()  # safe_remove: olmayan dosya hata değil
    assert cache.get("arac-2") is None


def test_uclar_supurmeyi_cagirir(monkeypatch, tmp_path):
    """Yükleme ve işlem uçları isteğin başında `_cleanup_process_cache` çağırır (plan §5)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import fitz

    from dependencies import get_current_user
    from routes import pdf_araclari as route_mod

    monkeypatch.setenv("PDF_ARACLARI_DIR", str(tmp_path / "pdf_araclari"))
    sayac = {"n": 0}
    monkeypatch.setattr(route_mod, "_cleanup_process_cache", lambda: sayac.__setitem__("n", sayac["n"] + 1))
    app = FastAPI()
    app.include_router(route_mod.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "a@x.com"}
    client = TestClient(app, raise_server_exceptions=False)

    with fitz.open() as doc:
        doc.new_page()
        pdf = doc.tobytes()
    r = client.post("/api/pdf-araclari/yukle", files={"file": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    assert sayac["n"] == 1
    r = client.post("/api/pdf-araclari/islem", json={"islem": "bol", "girdiler": [r.json()["id"]], "parametreler": {"her_n": 1}})
    assert r.status_code == 200, r.text
    assert sayac["n"] == 2
