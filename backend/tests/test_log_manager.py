"""TechnicalLogger buffer davranışı testleri.

2026-07-29 OOM incelemesi: buffer sınırsız büyüyordu ve yalnızca başarılı
SharePoint upload'ında sıfırlanıyordu. Artık tavanlı (deque maxlen) ve
kısmi boşaltma yapılıyor.
"""
import pytest

from managers.log_manager import TechnicalLogger


@pytest.fixture(autouse=True)
def _clean_buffer():
    with TechnicalLogger._lock:
        TechnicalLogger._buffer.clear()
    yield
    with TechnicalLogger._lock:
        TechnicalLogger._buffer.clear()


class TestBufferCap:
    def test_buffer_bounded(self):
        cap = TechnicalLogger._MAX_BUFFER_ENTRIES
        for i in range(cap + 50):
            TechnicalLogger.log("INFO", f"kayit {i}")
        assert len(TechnicalLogger._buffer) == cap
        # En eski kayıtlar düşmüş, en yeniler durmalı
        assert TechnicalLogger._buffer[-1]["message"] == f"kayit {cap + 49}"

    def test_message_truncated(self):
        TechnicalLogger.log("INFO", "x" * (TechnicalLogger._MAX_MESSAGE_CHARS + 5000))
        entry = TechnicalLogger._buffer[-1]
        assert len(entry["message"]) <= TechnicalLogger._MAX_MESSAGE_CHARS

    def test_error_does_not_block_caller(self, monkeypatch):
        # ERROR flush'ı artık ayrı thread'de — çağıran senkron upload beklemez.
        # conftest sync_to_cloud'u no-op'lar; burada thread'in gerçekten
        # spawn edildiğini değil, log çağrısının istisnasız döndüğünü doğruluyoruz.
        TechnicalLogger.log("ERROR", "hata kaydı")
        assert TechnicalLogger._buffer[-1]["level"] == "ERROR"


class TestPartialSync:
    def test_sync_keeps_entries_added_during_upload(self, monkeypatch):
        """Upload sürerken eklenen kayıtlar kaybolmamalı (eski davranış:
        komple sıfırlama aradaki kayıtları siliyordu)."""
        import managers.log_manager as lm

        with TechnicalLogger._lock:
            TechnicalLogger._buffer.append({"timestamp": "t1", "level": "INFO", "message": "a", "details": {}})

        def fake_upload(**kwargs):
            # Upload sırasında yeni kayıt gelir
            with TechnicalLogger._lock:
                TechnicalLogger._buffer.append(
                    {"timestamp": "t2", "level": "INFO", "message": "b", "details": {}}
                )

        monkeypatch.setattr(lm, "upload_file_to_sharepoint", fake_upload)
        # conftest sync_to_cloud'u no-op'ladığı için iç implementasyon çağrılır
        TechnicalLogger._sync_to_cloud_locked()

        remaining = [e["message"] for e in TechnicalLogger._buffer]
        assert remaining == ["b"]
