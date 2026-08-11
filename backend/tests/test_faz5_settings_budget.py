"""Faz 5-A (plan 5.1 + 5.2) — merkezi settings + istek zaman bütçesi testleri.

5.1 (davranış-nötr göç): config/settings.py varsayılanlarının taşınma öncesi
sabitlerle birebir aynı olduğu TABLO bekçisiyle kilitlenir; modül alias'larının
settings'e bağlandığı, env plumbing'inin (yeni Settings örneğiyle) ve bozuk-env
toleransının çalıştığı doğrulanır.

5.2 (bilinçli değişiklik): LO+GS+semafor beklemelerinin /confirm dönüşüm
bütçesine sığdığı ARİTMETİK bekçisi; semafor dolunca ConversionBusyError →
/confirm 503 + JSON detail; pending katmanına düşmeme; gece yolunun bütçeye
BAĞLANMADIĞI kaynak bekçisi.

conftest sözleşmesi: ağ/DB yok — route testleri in-memory sqlite + fake
pipeline adımlarıyla koşar (test_faz3_confirm_idempotency kalıbı).
"""
import logging
import os
import threading
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from config.settings import Settings, settings  # noqa: E402
from pdf import format_converter as fc  # noqa: E402


class _FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def tech_logs():
    handler = _ListHandler()
    target = logging.getLogger("TechnicalLogger")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _errors(records):
    return [r for r in records if r.levelno >= logging.ERROR]


# ═════════════════════════════════════════════════════════════════════════════
# 1) 5.1 — davranış-nötr göç bekçileri
# ═════════════════════════════════════════════════════════════════════════════


def test_settings_defaults_frozen_to_premigration_values():
    """TABLO bekçisi: her varsayılan, taşınma ÖNCESİ koddaki sabite eşit olmalı.

    Bu test kırmızıysa ya bilinçli bir limit değişikliği yapılmıştır (tabloyu
    ve karar notunu birlikte güncelle) ya da göç davranışı bozmuştur.
    """
    s = Settings()
    assert s.max_upload_mb == 50                      # file_utils.MAX_UPLOAD_MB
    assert s.request_size_limit_mb == 50              # api.py middleware 50 MB
    assert s.max_pdf_pages == 500                     # pdf_utils.MAX_PDF_PAGES
    assert s.pdf_parse_timeout_seconds == 60.0        # analyzer/intake wait_for
    assert s.gs_timeout_seconds == 240                # pdf_converter._gs_timeout
    assert s.libreoffice_timeout_seconds == 120       # format_converter sabiti
    assert s.email_max_single_mb == 3                 # email_sender (0-C)
    assert s.email_max_total_mb == 3
    assert s.counter_fetch_timeout_seconds == 10.0    # processing fetch_counter
    assert s.process_cache_ttl_seconds == 1800
    assert s.download_cache_ttl_seconds == 3600
    assert s.rate_limit_default == "100/minute"
    assert s.gemini_retry_deadline_seconds == 170.0   # 3-C bütçesi
    assert s.gemini_http_timeout_ms == 120_000
    # 5.2'nin yeni düğmeleri (bilinçli eklendi):
    assert s.request_time_budget_seconds == 300.0     # nginx penceresi
    assert s.confirm_conversion_budget_seconds == 270.0
    assert s.conversion_acquire_timeout_seconds == 30.0


def test_module_aliases_bound_to_settings():
    import analyzer
    import email_sender
    import file_utils
    import gemini_client
    from pdf import pdf_utils

    assert file_utils.MAX_UPLOAD_MB == settings.max_upload_mb
    assert file_utils.MAX_UPLOAD_BYTES == settings.max_upload_mb * 1024 * 1024
    assert pdf_utils.MAX_PDF_PAGES == settings.max_pdf_pages
    assert fc.LIBREOFFICE_TIMEOUT == settings.libreoffice_timeout_seconds
    assert email_sender.MAX_SINGLE_MB == settings.email_max_single_mb
    assert email_sender.MAX_TOTAL_MB == settings.email_max_total_mb
    assert analyzer.GEMINI_RETRY_DEADLINE_SECONDS == settings.gemini_retry_deadline_seconds
    assert gemini_client.GEMINI_HTTP_TIMEOUT_MS == settings.gemini_http_timeout_ms


def test_env_plumbing_with_fresh_settings(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "80")
    monkeypatch.setenv("GS_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("RATE_LIMIT_DEFAULT", "50/minute")
    s = Settings()
    assert s.max_upload_mb == 80
    assert s.gs_timeout_seconds == 90
    assert s.rate_limit_default == "50/minute"


def test_libreoffice_env_accepts_both_alias_names(monkeypatch):
    monkeypatch.setenv("LIBREOFFICE_TIMEOUT", "77")
    assert Settings().libreoffice_timeout_seconds == 77
    monkeypatch.delenv("LIBREOFFICE_TIMEOUT")
    monkeypatch.setenv("LIBREOFFICE_TIMEOUT_SECONDS", "88")
    assert Settings().libreoffice_timeout_seconds == 88


def test_tolerant_parsing_garbage_and_empty_fall_back_to_defaults(monkeypatch):
    # Eski _gs_timeout'un ValueError-fallback sözleşmesinin genellenmiş hali:
    # bozuk env HİÇBİR alan için uygulamayı düşürmez.
    monkeypatch.setenv("MAX_UPLOAD_MB", "elli")
    monkeypatch.setenv("GS_TIMEOUT_SECONDS", "hizli")
    monkeypatch.setenv("COUNTER_FETCH_TIMEOUT_SECONDS", "")
    s = Settings()
    assert s.max_upload_mb == 50
    assert s.gs_timeout_seconds == 240
    assert s.counter_fetch_timeout_seconds == 10.0


# ═════════════════════════════════════════════════════════════════════════════
# 2) 5.2 — zaman bütçesi aritmetiği (bekçiler)
# ═════════════════════════════════════════════════════════════════════════════


def test_confirm_conversion_budget_leaves_response_margin():
    # Dönüşüm payı + ≥30 sn yanıt payı (DB/kuyruk/e-posta) nginx penceresine sığar.
    assert (
        settings.confirm_conversion_budget_seconds + 30
        <= settings.request_time_budget_seconds
    )


def test_worst_office_chain_fits_confirm_budget():
    """En kötü zincir (Office): LO payı + GS payı ≤ dönüşüm bütçesi < 300.

    Statik toplama DEĞİL deadline-kırpma aritmetiği (3-C deseni): LO tavanını
    aynen alır, GS kalan bütçeye kırpılır → 120 + 150 = 270 (eski 120+240=360
    garanti-504 penceresi kapandı).
    """
    budget = settings.confirm_conversion_budget_seconds
    lo_share = min(settings.libreoffice_timeout_seconds, budget)
    gs_share = min(settings.gs_timeout_seconds, budget - lo_share)
    assert lo_share + gs_share <= budget < settings.request_time_budget_seconds
    # Varsayılanlarla beklenen paylar (bilinçli değişiklikte tabloyu güncelle):
    assert (lo_share, gs_share) == (120, 150)


def test_pdf_only_path_keeps_full_gs_timeout():
    # Salt-PDF yolunda (LO yok) GS bugünkü 240'ı AYNEN alır — davranış korunur.
    deadline = time.monotonic() + settings.confirm_conversion_budget_seconds
    clipped = fc._clip_timeout(settings.gs_timeout_seconds, deadline)
    assert round(clipped) == settings.gs_timeout_seconds == 240


def test_clip_timeout_units():
    assert fc._clip_timeout(240, None) == 240          # bütçesiz yol: tavan aynen
    d = time.monotonic() + 30
    assert 29 <= fc._clip_timeout(240, d) <= 30        # kalan bütçeye kırpılır
    past = time.monotonic() - 5
    assert fc._clip_timeout(240, past) == 1.0          # taban: 0/negatif gitmez


# ═════════════════════════════════════════════════════════════════════════════
# 3) 5.2 — acquire_conversion_slot birimleri
# ═════════════════════════════════════════════════════════════════════════════


class _RecordingSem:
    def __init__(self):
        self.calls = []

    def acquire(self, *a, **k):
        self.calls.append((a, k))
        return True

    def release(self):
        pass


def test_acquire_without_deadline_blocks_like_before():
    # Gece job'ı / /process yolu: deadline yok → argümansız (bloklayan) acquire.
    sem = _RecordingSem()
    fc.acquire_conversion_slot(sem, None, "test")
    assert sem.calls == [((), {})]


def test_acquire_with_deadline_uses_timeout_and_succeeds():
    sem = threading.Semaphore(1)
    fc.acquire_conversion_slot(sem, time.monotonic() + 60, "test")
    assert sem.acquire(blocking=False) is False  # slot gerçekten alındı
    sem.release()


def test_acquire_busy_when_slot_held(monkeypatch):
    monkeypatch.setattr(settings, "conversion_acquire_timeout_seconds", 0.05)
    sem = threading.Semaphore(1)
    sem.acquire()
    t0 = time.monotonic()
    with pytest.raises(fc.ConversionBusyError):
        fc.acquire_conversion_slot(sem, time.monotonic() + 60, "test")
    assert time.monotonic() - t0 < 5  # tavan bekleme; sonsuz blok yok


def test_acquire_busy_when_budget_already_exhausted():
    sem = threading.Semaphore(1)
    with pytest.raises(fc.ConversionBusyError):
        fc.acquire_conversion_slot(sem, time.monotonic() - 1, "test")
    assert sem.acquire(blocking=False) is True  # semafor tüketilmedi
    sem.release()


def test_acquire_wait_capped_by_remaining_budget(monkeypatch):
    # Kalan bütçe acquire tavanından KÜÇÜKSE bekleme kalanla sınırlanır.
    monkeypatch.setattr(settings, "conversion_acquire_timeout_seconds", 30.0)
    sem = _RecordingSem()
    fc.acquire_conversion_slot(sem, time.monotonic() + 0.5, "test")
    ((args, kwargs),) = [sem.calls[0]]
    assert not args
    assert 0 < kwargs["timeout"] <= 0.5


# ═════════════════════════════════════════════════════════════════════════════
# 4) 5.2 — convert_to_pdfa2b bütçe iletimi + Busy geçirgenliği
# ═════════════════════════════════════════════════════════════════════════════


def test_convert_threads_deadline_to_gs_and_none_without_budget(tmp_path, monkeypatch):
    import pdf.pdf_converter as pc

    src = tmp_path / "belge.pdf"
    src.write_bytes(b"%PDF-1.4")
    seen = {}

    def fake_gs(s, o, deadline=None):
        seen["deadline"] = deadline
        return s

    monkeypatch.setattr(pc, "_pdf_to_pdfa2b", fake_gs)

    pc.convert_to_pdfa2b(str(src), time_budget_seconds=100.0)
    assert seen["deadline"] is not None
    assert 0 < seen["deadline"] - time.monotonic() <= 100.0

    pc.convert_to_pdfa2b(str(src))
    assert seen["deadline"] is None  # bütçesiz çağrı (gece yolu) eski davranış


def test_convert_busy_passes_through_wrappers(tmp_path, monkeypatch):
    # Busy, non-PDF dalının generic RuntimeError sarmalayıcısına YAKALANMAZ.
    import pdf.pdf_converter as pc

    src = tmp_path / "belge.docx"
    src.write_bytes(b"PK\x03\x04")

    def busy(s, o=None, deadline=None):
        raise fc.ConversionBusyError("Office dönüşümü")

    monkeypatch.setattr(pc, "office_to_pdf", busy)
    with pytest.raises(fc.ConversionBusyError):
        pc.convert_to_pdfa2b(str(src), time_budget_seconds=100.0)


def test_night_job_source_never_passes_budget():
    # Gece retry job'ı istek bütçesine BAĞLANMAZ (karar): kaynak bekçisi.
    import inspect

    from services import conversion_retry

    assert "time_budget_seconds" not in inspect.getsource(conversion_retry)


# ═════════════════════════════════════════════════════════════════════════════
# 5) 5.2 — pipeline: Busy pending katmanına düşmez, bütçe settings'ten gider
# ═════════════════════════════════════════════════════════════════════════════


def _pipeline_kwargs(src, results, timings, bg):
    return dict(
        background_tasks=bg,
        source_path=str(src),
        ham_filename="h.pdf",
        ham_folder="H",
        islenmis_folder="I",
        new_filename="yeni.pdf",
        original_filename="kaynak.pdf",
        belge_turu_kodu=None,
        muvekkiller=[],
        muvekkil_adi=None,
        ai_ozet=None,
        linked_case_id=None,
        case_party_id=None,
        avukat_kodu=None,
        esas_no=None,
        is_test_mode=False,
        user={},
        current_user_name="t",
        results=results,
        timings=timings,
        ham_source_path=None,
    )


def test_pipeline_busy_raises_without_doc_or_pending(monkeypatch, tmp_path, tech_logs):
    import pdf.pdf_converter as pdf_converter
    from services import document_pipeline

    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4")

    captured = {}

    def busy(path, **kw):
        captured.update(kw)
        raise fc.ConversionBusyError("Office dönüşümü")

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", busy)
    saved = []
    monkeypatch.setattr(
        document_pipeline, "save_case_document", lambda **kw: saved.append(kw) or 7
    )

    results, timings = {}, {}
    with pytest.raises(fc.ConversionBusyError):
        document_pipeline.convert_pdfa_and_queue_uploads(
            **_pipeline_kwargs(src, results, timings, _FakeBackgroundTasks())
        )

    # Bütçe settings'ten gitti; belge/pending yan etkisi ve ERROR logu yok
    assert captured["time_budget_seconds"] == settings.confirm_conversion_budget_seconds
    assert saved == []
    assert "case_document_id" not in results
    assert "conversion_pending" not in results
    assert _errors(tech_logs) == []


def test_busy_detail_contract():
    from services import document_pipeline

    d = document_pipeline.CONVERSION_BUSY_DETAIL
    assert "meşgul" in d
    assert "TEKRAR YÜKLEMEYİN" in d
    assert "tekrar deneyin" in d


# ═════════════════════════════════════════════════════════════════════════════
# 6) 5.2 — /confirm 503 + idempotency release (route)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def sqlite_sessions():
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield maker
    engine.dispose()


@pytest.fixture()
def confirm_busy_env(sqlite_sessions, monkeypatch, tmp_path):
    """test_faz3_confirm_idempotency kalıbının 5-A odaklı kopyası: dönüşüm Busy atar."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import processing
    from routes.processing import PROCESS_CACHE
    from services import confirm_idempotency, document_pipeline

    monkeypatch.setattr(confirm_idempotency, "SessionLocal", sqlite_sessions)

    def busy_convert(**kwargs):
        raise fc.ConversionBusyError("Office dönüşümü")

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", busy_convert)

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {
            "path": str(p), "original_path": None, "original_ext": ".pdf",
            "owner": "test@example.com",
        })
        return p

    app = FastAPI()
    app.include_router(processing.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    client = TestClient(app, raise_server_exceptions=False)
    return SimpleNamespace(
        client=client, put_cache=put_cache, sessions=sqlite_sessions,
        svc=confirm_idempotency,
    )


def _receipt_row(sessions, pid):
    import models

    db = sessions()
    try:
        return db.query(models.ConfirmReceipt).filter(
            models.ConfirmReceipt.process_id == pid
        ).first()
    finally:
        db.close()


def test_confirm_busy_returns_503_with_detail_and_releases_receipt(confirm_busy_env):
    from services import document_pipeline

    confirm_busy_env.put_cache("pid-busy1")
    r = confirm_busy_env.client.post(
        "/confirm",
        data={
            "new_filename": "2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf",
            "send_email": "false",
            "is_test_mode": "true",
            "process_id": "pid-busy1",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"] == document_pipeline.CONVERSION_BUSY_DETAIL
    # Belge yaratılmadan düşen istek: kapı release etti → retry ANINDA serbest
    assert _receipt_row(confirm_busy_env.sessions, "pid-busy1") is None
    verdict, _ = confirm_busy_env.svc.begin("pid-busy1", "test@example.com")
    assert verdict == "proceed"


# ═════════════════════════════════════════════════════════════════════════════
# 7) 5.2 — intake commit: Busy belgeyi failed + "meşgul" mesajıyla işaretler
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def intake_busy_env(monkeypatch, tmp_path):
    """test_case_intake_commit env kalıbının Busy odaklı kopyası."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager
    from routes import case_intake
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    def fake_add_case(data):
        return {
            "id": 123, "tracking_no": data.get("tracking_no"),
            "esas_no": data.get("esas_no"), "court": data.get("court") or "",
            "status": "DERDEST",
            "responsible_lawyer_name": data.get("responsible_lawyer_name") or "",
        }

    monkeypatch.setattr(case_manager, "add_case", fake_add_case)
    monkeypatch.setattr(
        document_pipeline, "validate_tenant_and_resolve_lawyer",
        lambda case_id, user, avukat_kodu: "AVK1",
    )

    def busy_convert(**kwargs):
        raise fc.ConversionBusyError("UDF dönüşümü")

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", busy_convert)
    monkeypatch.setattr(document_pipeline, "schedule_cleanup", lambda *a, **k: None)

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {
            "path": str(p), "original_path": None, "original_ext": ".pdf",
            "owner": "test@example.com",
        })
        return p

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    return SimpleNamespace(client=TestClient(app), put_cache=put_cache)


def test_intake_commit_busy_marks_doc_failed_without_error_log(intake_busy_env, tech_logs):
    intake_busy_env.put_cache("pid-ibusy")
    r = intake_busy_env.client.post(
        "/api/case-intake/commit",
        json={
            "case": {
                "tracking_no": "2026/0456",
                "esas_no": "2024/1",
                "status": "KARAR",
                "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
                "responsible_lawyer_name": "Av. Deniz",
                "parties": [
                    {"name": "Ahmet YILMAZ", "role": "DAVACI",
                     "party_type": "CLIENT", "client_id": 12},
                ],
            },
            "documents": [{
                "process_id": "pid-ibusy",
                "new_filename": "2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf",
                "belge_turu_kodu": "TENSIP-ZPT____",
                "esas_no": "2024/1",
            }],
            "policies": [],
            "options": {"send_email": False},
        },
    )
    assert r.status_code == 200
    doc = r.json()["documents"][0]
    assert doc["status"] == "failed"
    assert "meşgul" in doc["error_ozet"]
    assert "yeniden yükleyin" in doc["error_ozet"]
    # Sistem doluluğu ERROR üretmez ([INTAKE-COMMIT] ERROR'u generic dala aittir)
    assert _errors(tech_logs) == []
