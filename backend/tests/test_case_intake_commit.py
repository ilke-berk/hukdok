"""Otonom dava açma Faz 4 testleri — POST /api/case-intake/commit.

DB'ye/ağa/Ghostscript'e erişim YOK: add_case, validate_tenant_and_resolve_lawyer,
convert_pdfa_and_queue_uploads, schedule_cleanup, save_client_policies
monkeypatch'lidir. accept_incoming_file GERÇEK çalışır (tmp_path dosyalarıyla
beslenen PROCESS_CACHE üzerinden) — böylece "409'da hiçbir belge tüketilmez"
ve "cache-miss → expired" garantileri gerçek POP semantiğiyle kanıtlanır.
"""
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")


@pytest.fixture()
def env(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager, client_manager
    from routes import case_intake
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    calls = {
        "add_case": [], "resolve": [], "convert": [],
        "cleanup": [], "policies": [], "email": [],
    }

    def fake_add_case(data):
        calls["add_case"].append(data)
        return {
            "id": 123, "tracking_no": data.get("tracking_no"),
            "esas_no": data.get("esas_no"), "court": data.get("court") or "",
            "status": "DERDEST",
            "responsible_lawyer_name": data.get("responsible_lawyer_name") or "",
        }

    monkeypatch.setattr(case_manager, "add_case", fake_add_case)

    def fake_resolve(case_id, user, avukat_kodu):
        calls["resolve"].append(case_id)
        return "AVK1"

    monkeypatch.setattr(document_pipeline, "validate_tenant_and_resolve_lawyer", fake_resolve)

    doc_ids = iter(range(41, 99))

    def fake_convert(**kwargs):
        calls["convert"].append(kwargs)
        pdfa = tmp_path / f"pdfa_{len(calls['convert'])}.pdf"
        pdfa.write_bytes(b"%PDF pdfa")
        return (str(pdfa), next(doc_ids))

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", fake_convert)
    monkeypatch.setattr(
        document_pipeline, "schedule_cleanup",
        lambda *a, **k: calls["cleanup"].append((a, k)),
    )

    def fake_save_policies(client_id, policies, created_by=None):
        calls["policies"].append(
            {"client_id": client_id, "policies": policies, "created_by": created_by}
        )
        return {"saved": len(policies), "skipped": 0}

    monkeypatch.setattr(client_manager, "save_client_policies", fake_save_policies)

    async def fake_send_email(**kwargs):
        calls["email"].append(kwargs)
        kwargs["results"]["email"] = "Gönderildi"

    monkeypatch.setattr(document_pipeline, "send_notification_email", fake_send_email)

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
    return SimpleNamespace(
        client=TestClient(app), calls=calls, put_cache=put_cache, cache=PROCESS_CACHE,
    )


def _payload(**overrides):
    payload = {
        "case": {
            "tracking_no": "2026/0456",
            "esas_no": "2024/1",
            # İstemci bilerek DERDEST-dışı gönderiyor: sunucu zorlamalı (karar 1)
            "status": "KARAR",
            "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
            "responsible_lawyer_name": "Av. Deniz",
            "parties": [
                {"name": "Ahmet YILMAZ", "role": "DAVACI",
                 "party_type": "CLIENT", "client_id": 12},
            ],
        },
        "documents": [],
        "policies": [],
        "options": {"send_email": False},
    }
    payload.update(overrides)
    return payload


def _doc(pid, filename="2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf", **extra):
    d = {"process_id": pid, "new_filename": filename, "belge_turu_kodu": "TENSIP-ZPT____",
         "ai_ozet": "Özet", "esas_no": "2024/1", "muvekkil_adi": "Ahmet YILMAZ"}
    d.update(extra)
    return d


# ── mutlu yol ────────────────────────────────────────────────────────────────

def test_commit_case_only_creates_case_and_forces_derdest(env):
    # Zorunlu alan eksikliği kaydı ENGELLEMEZ (kullanıcı kararı 2026-07-31 rev.2):
    # dava DERDEST açılır, eksikler yanıtla döner (panelde uyarı için).
    r = env.client.post("/api/case-intake/commit", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["id"] == 123
    assert body["case"]["tracking_no"] == "2026/0456"
    assert body["case"]["status"] == "DERDEST"
    assert len(body["case"]["missing_required_fields"]) > 0
    assert body["documents"] == []
    assert body["policies"] == {"saved": 0, "skipped": 0}
    # status istemcinin gönderdiği KARAR değil, sunucuda zorlanmış DERDEST
    assert len(env.calls["add_case"]) == 1
    assert env.calls["add_case"][0]["status"] == "DERDEST"
    assert env.calls["add_case"][0]["parties"][0]["client_id"] == 12


def test_commit_complete_case_has_no_missing_fields(env):
    payload = _payload()
    payload["case"].update({
        "file_type": "Hukuk",
        "judicial_unit": "ASLİYE HUKUK MAHKEMESİ",
        "sub_type": "ASLİYE HUKUK MAHKEMESİ",
        "sub_type_extra": "Üroloji",
        "opening_date": "2024-01-10",
        "subject": "Maddi-manevi tazminat",
        "uyap_lawyer_name": "Av. Deniz",
        "service_type": "00100",
        "acceptance_date": "2024-01-05",
        "bureau_type": "LEXİS",
        "atama_tarihi": "2024-01-02",
    })
    payload["case"]["parties"].append(
        {"name": "Karşı Kurum", "role": "DAVALI", "party_type": "COUNTER", "tc_no": "12345678901"}
    )
    r = env.client.post("/api/case-intake/commit", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["status"] == "DERDEST"
    assert body["case"]["missing_required_fields"] == []
    assert env.calls["add_case"][0]["status"] == "DERDEST"


def test_commit_happy_path_all_documents_queued(env):
    env.put_cache("pid-a")
    env.put_cache("pid-b")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[_doc("pid-a"), _doc("pid-b", filename="2024-02-01_AHMET-YILMAZ_TEBLIGAT______.pdf")],
    ))
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert [d["status"] for d in docs] == ["queued", "queued"]
    assert [d["document_id"] for d in docs] == [41, 42]
    assert all(d["error_ozet"] is None for d in docs)
    # cache tüketildi (POP semantiği) + temizlik her belge için kuyruklandı
    assert env.cache.pop("pid-a") is None
    assert env.cache.pop("pid-b") is None
    assert len(env.calls["cleanup"]) == 2
    # pipeline confirm imzasıyla çağrıldı: yeni davaya bağlı, test modu kapalı
    kw = env.calls["convert"][0]
    assert kw["linked_case_id"] == 123
    assert kw["avukat_kodu"] == "AVK1"
    assert kw["is_test_mode"] is False
    assert kw["belge_turu_kodu"] == "TENSIP-ZPT____"
    # sanitize_filename padding alt çizgilerini teke indirir (confirm ile aynı)
    assert kw["ham_filename"].endswith("_2024-01-15_AHMET-YILMAZ_TENSIP-ZPT_.pdf")
    # avukat çözümü tek sefer (belge başına değil)
    assert env.calls["resolve"] == [123]


# ── 409 yolu (karar 3) ───────────────────────────────────────────────────────

def test_commit_duplicate_tracking_no_409_consumes_no_document(env, monkeypatch):
    from managers import case_manager

    monkeypatch.setattr(
        case_manager, "add_case", lambda data: {"error": "duplicate_tracking_no"}
    )
    env.put_cache("pid-dup")
    r = env.client.post(
        "/api/case-intake/commit", json=_payload(documents=[_doc("pid-dup")])
    )
    assert r.status_code == 409
    assert "2026/0456" in r.json()["detail"]
    # add_case adım 1'de patladı: belge tüketilmedi, retry güvenli
    assert env.cache.touch("pid-dup") is True
    assert env.calls["convert"] == []


def test_commit_add_case_failure_500(env, monkeypatch):
    from managers import case_manager

    monkeypatch.setattr(case_manager, "add_case", lambda data: None)
    r = env.client.post("/api/case-intake/commit", json=_payload())
    assert r.status_code == 500


# ── belge-başı hata izolasyonu (karar 4) ─────────────────────────────────────

def test_commit_cache_miss_document_expired_others_queued(env):
    env.put_cache("pid-alive")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[_doc("pid-gone"), _doc("pid-alive")],
    ))
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs[0]["status"] == "expired"
    assert docs[0]["document_id"] is None
    assert "yeniden yükleyin" in docs[0]["error_ozet"]
    assert docs[1]["status"] == "queued"
    assert len(env.calls["convert"]) == 1


def test_commit_pdfa_failure_isolated_and_temp_cleaned(env, monkeypatch):
    from services import document_pipeline

    real_convert = document_pipeline.convert_pdfa_and_queue_uploads

    def flaky_convert(**kwargs):
        if "BOZUK" in kwargs["new_filename"]:
            raise Exception("PDF/A-2b dönüşümü başarısız")
        return real_convert(**kwargs)

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", flaky_convert)
    bad_path = env.put_cache("pid-bad")
    env.put_cache("pid-good")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[
            _doc("pid-bad", filename="2024-01-15_BOZUK.pdf"),
            _doc("pid-good"),
        ],
    ))
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs[0]["status"] == "failed"
    assert "Hata:" in docs[0]["error_ozet"]
    assert docs[1]["status"] == "queued"
    assert docs[1]["document_id"] is not None
    # POP edilen temp dosyanın TTL sahibi yok — hata yolunda silinmeli
    assert not bad_path.exists()


def test_commit_unicode_decode_error_does_not_kill_flow(env, monkeypatch):
    """Confirm arızası regresyonu (2026-07-13): UnicodeDecodeError, ValueError
    alt sınıfıdır ve dar except'leri deler — belge sarmalayıcısı yutmalı."""
    from services import document_pipeline

    def gs_boom(**kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", gs_boom)
    env.put_cache("pid-gs")
    r = env.client.post(
        "/api/case-intake/commit", json=_payload(documents=[_doc("pid-gs")])
    )
    assert r.status_code == 200
    assert r.json()["documents"][0]["status"] == "failed"
    assert r.json()["case"]["id"] == 123


# ── poliçe beslemesi (karar 5) ───────────────────────────────────────────────

def test_commit_policies_grouped_by_client_and_saved(env):
    policies = [
        {"client_id": 12, "police_no": "928/4", "police_turu": "ZORUNLU",
         "sigorta_sirketi": "XYZ SİGORTA", "baslangic_tarihi": "2024-05-01",
         "bitis_tarihi": "2025-05-01", "source_document": "police.pdf"},
        {"client_id": 12, "police_no": "928/4", "police_turu": "ZORUNLU",
         "sigorta_sirketi": "XYZ SİGORTA", "baslangic_tarihi": "2025-05-01",
         "bitis_tarihi": "2026-05-01", "source_document": "police2.pdf"},
        {"client_id": 34, "police_no": "111", "police_turu": "TAMAMLAYICI",
         "sigorta_sirketi": "ABC SİGORTA", "baslangic_tarihi": "2024-01-01",
         "bitis_tarihi": "2025-01-01", "source_document": "police3.pdf"},
    ]
    r = env.client.post("/api/case-intake/commit", json=_payload(policies=policies))
    assert r.status_code == 200
    assert r.json()["policies"] == {"saved": 3, "skipped": 0}
    assert [c["client_id"] for c in env.calls["policies"]] == [12, 34]
    first = env.calls["policies"][0]
    assert first["created_by"] == "Test Kullanıcı"
    assert len(first["policies"]) == 2
    assert "client_id" not in first["policies"][0]
    assert first["policies"][0]["baslangic_tarihi"] == date(2024, 5, 1)


def test_commit_policy_error_does_not_affect_case_or_documents(env, monkeypatch):
    from managers import client_manager

    def boom(client_id, policies, created_by=None):
        raise Exception("DB down")

    monkeypatch.setattr(client_manager, "save_client_policies", boom)
    env.put_cache("pid-x")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[_doc("pid-x")],
        policies=[{"client_id": 12, "police_no": "928/4", "baslangic_tarihi": "2024-05-01"}],
    ))
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["id"] == 123
    assert body["documents"][0]["status"] == "queued"
    assert "error" in body["policies"]


# ── e-posta (karar 2: varsayılan KAPALI) ─────────────────────────────────────

def test_commit_email_off_by_default(env):
    env.put_cache("pid-e1")
    # options hiç gönderilmiyor → send_email varsayılanı false olmalı
    payload = _payload(documents=[_doc("pid-e1")])
    del payload["options"]
    r = env.client.post("/api/case-intake/commit", json=payload)
    assert r.status_code == 200
    assert env.calls["email"] == []
    assert "email" not in r.json()["documents"][0]


def test_commit_email_sent_when_toggled_on(env):
    env.put_cache("pid-e2")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[_doc("pid-e2")], options={"send_email": True},
    ))
    assert r.status_code == 200
    assert len(env.calls["email"]) == 1
    assert env.calls["email"][0]["avukat_kodu"] == "AVK1"
    assert r.json()["documents"][0]["email"] == "Gönderildi"


def test_commit_email_recipients_passed_through(env):
    env.put_cache("pid-e3")
    r = env.client.post("/api/case-intake/commit", json=_payload(
        documents=[_doc("pid-e3")],
        options={"send_email": True, "email_to": ["muvekkil@example.com", "avukat@example.com"]},
    ))
    assert r.status_code == 200
    assert env.calls["email"][0]["custom_to"] == ["muvekkil@example.com", "avukat@example.com"]


# ── avukat çözümü hatası akışı durdurmaz ─────────────────────────────────────

def test_commit_lawyer_resolution_failure_is_non_fatal(env, monkeypatch):
    from services import document_pipeline

    def resolve_boom(case_id, user, avukat_kodu):
        raise Exception("tenant lookup failed")

    monkeypatch.setattr(document_pipeline, "validate_tenant_and_resolve_lawyer", resolve_boom)
    env.put_cache("pid-l")
    r = env.client.post(
        "/api/case-intake/commit", json=_payload(documents=[_doc("pid-l")])
    )
    assert r.status_code == 200
    assert r.json()["documents"][0]["status"] == "queued"
    assert env.calls["convert"][0]["avukat_kodu"] is None
