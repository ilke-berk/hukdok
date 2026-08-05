"""Otonom dava açma Faz 7 testleri — zenginleştirme modu.

Üç katman:
1. Saf servis fonksiyonları (inject_case_candidates / annotate_enrich_status /
   mark_existing_parties) + case_manager.enrich_changes — DB'siz unit test.
2. merge route'u case_id ile — get_case + DB bağlam yükleyicileri + hakem
   monkeypatch'li (test_case_intake_merge desenleri).
3. apply route'u — enrich_case + pipeline fonksiyonları monkeypatch'li,
   accept_incoming_file GERÇEK (expired izolasyonu POP semantiğiyle kanıtlanır;
   test_case_intake_commit desenleri).
"""
import os
from datetime import date, datetime
from types import SimpleNamespace

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

from managers.case_manager import enrich_changes  # noqa: E402
from services.case_intake import (  # noqa: E402
    annotate_enrich_status,
    build_draft,
    detect_conflicts,
    inject_case_candidates,
    mark_existing_parties,
)


def _doc(filename, process_id=None, **extraction):
    extraction.setdefault("taraflar", [])
    return {
        "process_id": process_id or f"pid-{filename}",
        "filename": filename,
        "extraction": extraction,
    }


def _case_row(**overrides):
    row = {
        "id": 55,
        "tracking_no": "2024/0055",
        "esas_no": "2024/123",
        "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
        "status": "DERDEST",
        "file_type": "Hukuk",
        "subject": None,
        "sub_type_extra": None,
        "opening_date": None,
        "maddi_tazminat": 0.0,
        "manevi_tazminat": 0.0,
        "judicial_unit": None,
        "hasar_dosya_no": None,
        "hukuk_no": None,
        "updated_at": "2026-08-01T12:00:00",
        "parties": [
            {"id": 71, "name": "Ahmet YILMAZ", "role": "Davacı",
             "party_type": "CLIENT", "client_id": 12, "tc_no": "12345678901"},
            {"id": 72, "name": "Quick Sigorta Anonim Şirketi", "role": "Davalı",
             "party_type": "COUNTER", "client_id": None, "tc_no": None},
        ],
    }
    row.update(overrides)
    return row


# ── inject_case_candidates ───────────────────────────────────────────────────

def test_inject_same_value_merges_into_existing_candidate():
    docs = [_doc("tensip.pdf", esas_no="2024/123")]
    draft, _ = build_draft(docs, [])
    inject_case_candidates(draft["fields"], _case_row())
    esas = draft["fields"]["esas_no"]
    # Yeni aday üretilmedi; mevcut adayın kaynaklarına "kayıtlı dava" eklendi
    assert len(esas["candidates"]) == 1
    assert "kayıtlı dava" in esas["candidates"][0]["sources"]
    assert esas["value"] == "2024/123"


def test_inject_different_value_creates_conflict_for_arbiter():
    docs = [_doc("tensip.pdf", esas_no="2025/7")]
    draft, conflicts = build_draft(docs, [])
    assert conflicts == []  # belgeler kendi aralarında hemfikirdi
    inject_case_candidates(draft["fields"], _case_row(esas_no="2024/123"))
    conflicts = detect_conflicts(draft["fields"])
    assert [c["alan"] for c in conflicts] == ["esas_no"]
    saved = next(
        c for c in draft["fields"]["esas_no"]["candidates"]
        if "kayıtlı dava" in c["sources"]
    )
    assert saved["value"] == "2024/123"
    assert saved["count"] == 0
    # Belge önerisi taslak değeri olarak DURUYOR — karar kullanıcının/hakemin
    assert draft["fields"]["esas_no"]["value"] == "2025/7"


def test_inject_empty_case_value_adds_nothing():
    docs = [_doc("tensip.pdf", esas_no="2025/7")]
    draft, _ = build_draft(docs, [])
    inject_case_candidates(draft["fields"], _case_row(esas_no=None, court=""))
    assert len(draft["fields"]["esas_no"]["candidates"]) == 1
    assert draft["fields"]["court"]["candidates"] == []


def test_inject_money_zero_treated_as_empty():
    docs = [_doc("dilekce.pdf", belge_turu_tahmini="Dava Dilekçesi",
                 maddi_tazminat=50000.0)]
    draft, _ = build_draft(docs, [])
    inject_case_candidates(draft["fields"], _case_row(maddi_tazminat=0.0))
    assert len(draft["fields"]["maddi_tazminat"]["candidates"]) == 1  # 0 aday olmadı


# ── annotate_enrich_status ───────────────────────────────────────────────────

def test_annotate_statuses_fill_confirm_conflict_keep():
    docs = [_doc(
        "tensip.pdf",
        esas_no="2024/123",             # kayıtlı değerle aynı → confirm
        mahkeme="İSTANBUL 1. ASLİYE HUKUK MAHKEMESİ",  # farklı → conflict
        dava_konusu=None,
    )]
    draft, _ = build_draft(docs, [])
    case = _case_row(subject="Tazminat")  # belge önerisi yok → keep
    annotate_enrich_status(draft["fields"], case)
    f = draft["fields"]
    assert f["esas_no"]["enrich"] == {"status": "confirm", "current": "2024/123"}
    assert f["court"]["enrich"]["status"] == "conflict"
    assert f["subject"]["enrich"] == {"status": "keep", "current": "Tazminat"}
    # dava file_type dolu, belge yargı türü çıkarmadı → keep
    assert f["file_type"]["enrich"]["status"] == "keep"
    # her iki taraf da boş → enrich bilgisi yazılmaz
    assert "enrich" not in f["hukuk_no"]


def test_annotate_fill_when_case_empty_and_doc_has_value():
    docs = [_doc("atama.pdf", hasar_dosya_no="HSR-2024-9")]
    draft, _ = build_draft(docs, [])
    annotate_enrich_status(draft["fields"], _case_row())
    assert draft["fields"]["hasar_dosya_no"]["enrich"]["status"] == "fill"


def test_annotate_money_zero_case_value_is_fill():
    docs = [_doc("dilekce.pdf", belge_turu_tahmini="Dava Dilekçesi",
                 maddi_tazminat=50000.0)]
    draft, _ = build_draft(docs, [])
    annotate_enrich_status(draft["fields"], _case_row(maddi_tazminat=0.0))
    assert draft["fields"]["maddi_tazminat"]["enrich"]["status"] == "fill"


# ── mark_existing_parties ────────────────────────────────────────────────────

def test_mark_existing_parties_by_tc_name_and_corporate_suffix():
    parties = [
        {"name": "Ahmet Yilmaz (yazım farklı)", "tc_no": "12345678901"},   # TC eşleşir
        {"name": "QUICK SİGORTA A.Ş.", "tc_no": None},                     # ünvan eşitlemesi
        {"name": "Yepyeni Kişi", "tc_no": None},                           # eklenecek
    ]
    mark_existing_parties(parties, _case_row()["parties"])
    assert parties[0]["existing"]["case_party_id"] == 71
    assert parties[1]["existing"]["case_party_id"] == 72
    assert parties[1]["existing"]["name"] == "Quick Sigorta Anonim Şirketi"
    assert parties[2]["existing"] is None


# ── Alan listesi senkronu ────────────────────────────────────────────────────
# ENRICH_FIELDS (manager beyaz listesi) ile EnrichFieldsIn (route şeması) el
# ile senkron iki liste — ayrışırlarsa alan sessizce uygulanmaz. Bu test
# ayrışmayı derleme anında yakalar (sertleştirme planı İş 1).

def test_enrich_field_whitelist_matches_schema():
    from managers.case_manager import ENRICH_FIELDS
    from schemas_intake import EnrichFieldsIn

    assert set(ENRICH_FIELDS) == set(EnrichFieldsIn.model_fields)


def test_enrich_case_field_map_subset_of_whitelist():
    # Merge'in fill/confirm durumu verdiği her alan apply'da da uygulanabilir
    # olmalı — aksi halde sihirbaz tik'letir ama manager sessizce atlar.
    from managers.case_manager import ENRICH_FIELDS
    from services.case_intake import ENRICH_CASE_FIELD_MAP

    assert set(ENRICH_CASE_FIELD_MAP) <= set(ENRICH_FIELDS)


# ── enrich_changes (exclude_unset semantiği) ─────────────────────────────────

def test_enrich_changes_only_sent_fields_and_skips_noop():
    current = {"esas_no": "2024/123", "court": "ANKARA", "subject": None}
    fields = {"esas_no": "2025/7", "court": "ANKARA"}  # subject GÖNDERİLMEDİ
    changes = enrich_changes(current, fields)
    assert changes == [("esas_no", "2024/123", "2025/7")]  # court no-op, listede yok


def test_enrich_changes_none_deletes_field():
    changes = enrich_changes({"hukuk_no": "HK-1"}, {"hukuk_no": None})
    assert changes == [("hukuk_no", "HK-1", None)]


def test_enrich_changes_parses_dates_and_skips_invalid():
    current = {"opening_date": date(2024, 1, 10), "atama_tarihi": None}
    changes = enrich_changes(current, {
        "opening_date": "2024-02-20",
        "atama_tarihi": "saçma-tarih",
    })
    assert changes == [("opening_date", date(2024, 1, 10), date(2024, 2, 20))]


def test_enrich_changes_date_same_value_is_noop():
    changes = enrich_changes(
        {"opening_date": date(2024, 1, 10)}, {"opening_date": "2024-01-10"}
    )
    assert changes == []


def test_enrich_changes_money_numeric_compare():
    current = {"maddi_tazminat": 50000.0, "manevi_tazminat": None}
    changes = enrich_changes(current, {
        "maddi_tazminat": 50000,      # 50000 == 50000.0 → no-op
        "manevi_tazminat": 100000.0,
    })
    assert changes == [("manevi_tazminat", None, 100000.0)]


def test_enrich_changes_ignores_non_whitelisted_field():
    assert enrich_changes({}, {"status": "KARAR", "tracking_no": "X"}) == []


# ── merge route (case_id) ────────────────────────────────────────────────────

CLIENT_ROWS = [
    {"id": 12, "name": "Ahmet YILMAZ", "tc_no": "12345678901",
     "cari_kod": "000012", "category": "Doktor", "contact_type": "Client"},
]


@pytest.fixture()
def merge_env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import case_intake_analyzer
    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager
    from routes import case_intake

    monkeypatch.setattr(
        case_intake, "_load_merge_context",
        lambda tenant_id: {
            "client_rows": CLIENT_ROWS,
            "party_rows": [],
            "known_courts": ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"],
        },
    )
    monkeypatch.setattr(case_intake, "_load_known_policies", lambda client_ids: [])
    monkeypatch.setattr(case_intake, "_load_client_case_rows", lambda client_ids: {})

    get_case_calls = []

    def fake_get_case(case_id, tenant_id=None):
        get_case_calls.append((case_id, tenant_id))
        return _case_row() if case_id == 55 else None

    monkeypatch.setattr(case_manager, "get_case", fake_get_case)

    arbiter_calls = []

    async def fake_arbiter(conflicts, doc_summaries):
        arbiter_calls.append(conflicts)
        # Hakem kayıtlı davanın esas no'sunu seçiyor (istinaf değil, aynı dosya)
        return [{"alan": "esas_no", "secilen_deger": "2024/123",
                 "gerekce": "Kayıtlı dava aynı dosya."}]

    monkeypatch.setattr(case_intake_analyzer, "arbitrate_conflicts", fake_arbiter)

    dup_calls = []
    import case_matcher
    monkeypatch.setattr(
        case_matcher, "find_matching_case",
        lambda **kwargs: dup_calls.append(kwargs) or None,
    )

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "t@example.com"}
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    return SimpleNamespace(
        client=TestClient(app),
        arbiter_calls=arbiter_calls,
        get_case_calls=get_case_calls,
        dup_calls=dup_calls,
    )


def _merge_payload(case_id=55, esas_no="2025/7"):
    return {
        "case_id": case_id,
        "documents": [
            {"process_id": "pid-tensip", "filename": "tensip.pdf", "extraction": {
                "esas_no": esas_no, "mahkeme": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
                "belge_turu_tahmini": "Tensip Zaptı", "hasar_dosya_no": "HSR-9",
                "taraflar": [
                    {"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None},
                    {"ad": "Yeni Müdahil", "rol": "MUDAHIL", "tc_no": None},
                ],
            }},
        ],
    }


def test_merge_enrich_mode_full_draft(merge_env):
    from routes.processing import PROCESS_CACHE

    PROCESS_CACHE.set("pid-tensip", {"path": "/tmp/pid-tensip.pdf"})
    try:
        resp = merge_env.client.post("/api/case-intake/merge", json=_merge_payload())
        assert resp.status_code == 200
        draft = resp.json()

        assert draft["mode"] == "enrich"
        assert draft["case"]["id"] == 55
        assert draft["case"]["tracking_no"] == "2024/0055"
        # Eşzamanlılık imzası özet üzerinden frontend'e taşınır (409 koruması)
        assert draft["case"]["updated_at"] == "2026-08-01T12:00:00"
        assert merge_env.get_case_calls == [(55, "tenant-1")]

        # esas_no: belge 2025/7 vs kayıtlı 2024/123 → hakem tetiklendi,
        # kayıtlı değeri seçti; durum confirm'e döndü
        assert len(merge_env.arbiter_calls) == 1
        esas = draft["fields"]["esas_no"]
        assert esas["value"] == "2024/123"
        assert esas["enrich"]["status"] == "confirm"
        assert any("kayıtlı dava" in c["sources"] for c in esas["candidates"])

        # mahkeme aynı → confirm; hasar dosya no davada boş → fill
        assert draft["fields"]["court"]["enrich"]["status"] == "confirm"
        assert draft["fields"]["hasar_dosya_no"]["enrich"]["status"] == "fill"

        # Taraflar: kayıtlı olan işaretli, yeni öneri işaretsiz
        ahmet = next(p for p in draft["parties"] if p["name"] == "AHMET YILMAZ")
        assert ahmet["existing"]["case_party_id"] == 71
        yeni = next(p for p in draft["parties"] if p["name"] == "Yeni Müdahil")
        assert yeni["existing"] is None

        # Mükerrer kontrol bu modda atlanır
        assert merge_env.dup_calls == []
        assert draft["duplicate_case"] is None
    finally:
        PROCESS_CACHE.delete("pid-tensip")


def test_merge_enrich_no_conflict_when_values_agree(merge_env):
    from routes.processing import PROCESS_CACHE

    PROCESS_CACHE.set("pid-tensip", {"path": "/tmp/pid-tensip.pdf"})
    try:
        resp = merge_env.client.post(
            "/api/case-intake/merge", json=_merge_payload(esas_no="2024/123")
        )
        assert resp.status_code == 200
        assert merge_env.arbiter_calls == []  # kayıtlı değerle uyum — hakem yok
        assert resp.json()["fields"]["esas_no"]["enrich"]["status"] == "confirm"
    finally:
        PROCESS_CACHE.delete("pid-tensip")


def test_merge_unknown_case_404(merge_env):
    resp = merge_env.client.post("/api/case-intake/merge", json=_merge_payload(case_id=999))
    assert resp.status_code == 404


def test_merge_without_case_id_stays_new_mode(merge_env):
    from routes.processing import PROCESS_CACHE

    payload = _merge_payload()
    del payload["case_id"]
    PROCESS_CACHE.set("pid-tensip", {"path": "/tmp/pid-tensip.pdf"})
    try:
        resp = merge_env.client.post("/api/case-intake/merge", json=payload)
        assert resp.status_code == 200
        draft = resp.json()
        assert draft["mode"] == "new"
        assert draft["case"] is None
        assert merge_env.get_case_calls == []
        assert "enrich" not in draft["fields"]["esas_no"]
    finally:
        PROCESS_CACHE.delete("pid-tensip")


# ── apply route ──────────────────────────────────────────────────────────────

CASE_UPDATED_AT = datetime(2026, 8, 1, 12, 0, 0)


@pytest.fixture()
def apply_env(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager, client_manager
    from routes import case_intake
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    calls = {"enrich": [], "resolve": [], "convert": [], "cleanup": [], "policies": []}

    def fake_enrich_case(case_id, fields, parties, changed_by, source, tenant_id=None,
                         expected_updated_at=None):
        calls["enrich"].append({
            "case_id": case_id, "fields": fields, "parties": parties,
            "changed_by": changed_by, "source": source, "tenant_id": tenant_id,
            "expected_updated_at": expected_updated_at,
        })
        if case_id == 999:
            return None
        # Gerçek imza kontrolüyle aynı yol: dava DB'de CASE_UPDATED_AT anında
        # güncellenmiş gibi davranır — bayat imza alan yazılmadan reddedilir.
        if case_manager.is_stale_case(CASE_UPDATED_AT, expected_updated_at):
            return {"error": "stale_case"}
        return {
            "tracking_no": "2024/0055",
            "updated_fields": [
                {"field": k, "old": None, "new": str(v)} for k, v in fields.items()
            ],
            "added_parties": [p["name"] for p in parties],
        }

    monkeypatch.setattr(case_manager, "enrich_case", fake_enrich_case)

    def fake_resolve(case_id, user, avukat_kodu):
        calls["resolve"].append(case_id)
        return "AVK1"

    monkeypatch.setattr(document_pipeline, "validate_tenant_and_resolve_lawyer", fake_resolve)

    doc_ids = iter(range(61, 99))

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
        calls["policies"].append({"client_id": client_id, "policies": policies})
        return {"saved": len(policies), "skipped": 0}

    monkeypatch.setattr(client_manager, "save_client_policies", fake_save_policies)

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {"path": str(p), "original_path": None, "original_ext": ".pdf"})
        return p

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com",
    }
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    return SimpleNamespace(client=TestClient(app), calls=calls, put_cache=put_cache)


def _apply_payload(**overrides):
    payload = {
        "case_id": 55,
        "fields": {"esas_no": "2025/7", "hasar_dosya_no": "HSR-9"},
        "parties": [
            {"name": "Yeni Müdahil", "role": "Müdahil", "party_type": "THIRD"},
        ],
        "documents": [],
        "policies": [],
        "options": {"send_email": False},
    }
    payload.update(overrides)
    return payload


def test_apply_partial_update_passes_only_sent_fields(apply_env):
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["case"] == {"id": 55, "tracking_no": "2024/0055"}
    assert [u["field"] for u in body["updated_fields"]] == ["esas_no", "hasar_dosya_no"]
    assert body["added_parties"] == ["Yeni Müdahil"]

    call = apply_env.calls["enrich"][0]
    # exclude_unset: yalnız gönderilen anahtarlar manager'a ulaşır
    assert set(call["fields"].keys()) == {"esas_no", "hasar_dosya_no"}
    assert call["tenant_id"] == "tenant-1"
    assert call["changed_by"] == "Test Kullanıcı"
    assert call["parties"][0]["party_type"] == "THIRD"


def test_apply_source_signature_contains_document_names(apply_env):
    apply_env.put_cache("pid-t")
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        documents=[{
            "process_id": "pid-t", "new_filename": "2024-01-15_TENSIP.pdf",
            "original_filename": "tensip.pdf", "belge_turu_kodu": "TENSIP-ZPT____",
        }],
    ))
    assert r.status_code == 200
    assert apply_env.calls["enrich"][0]["source"] == "intake-enrich: tensip.pdf"
    # belge kayıtlı davaya bağlandı
    assert apply_env.calls["convert"][0]["linked_case_id"] == 55
    assert r.json()["documents"][0]["status"] == "queued"


def test_apply_source_signature_without_documents(apply_env):
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload())
    assert r.status_code == 200
    assert apply_env.calls["enrich"][0]["source"] == "intake-enrich"


def test_apply_unknown_case_404(apply_env):
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(case_id=999))
    assert r.status_code == 404


def test_apply_expired_document_isolated(apply_env):
    apply_env.put_cache("pid-alive")
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        documents=[
            {"process_id": "pid-gone", "new_filename": "a.pdf"},
            {"process_id": "pid-alive", "new_filename": "b.pdf"},
        ],
    ))
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs[0]["status"] == "expired"
    assert "yeniden yükleyin" in docs[0]["error_ozet"]
    assert docs[1]["status"] == "queued"
    # dava güncellemesi belge hatasından etkilenmedi
    assert len(apply_env.calls["enrich"]) == 1


def test_apply_empty_fields_archives_documents_only(apply_env):
    apply_env.put_cache("pid-only-doc")
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        fields={}, parties=[],
        documents=[{"process_id": "pid-only-doc", "new_filename": "ek.pdf"}],
    ))
    assert r.status_code == 200
    body = r.json()
    assert body["updated_fields"] == []
    assert body["added_parties"] == []
    assert apply_env.calls["enrich"][0]["fields"] == {}
    assert body["documents"][0]["status"] == "queued"


def test_apply_policies_fed_like_commit(apply_env):
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        policies=[{"client_id": 12, "police_no": "928/4",
                   "baslangic_tarihi": "2024-05-01", "bitis_tarihi": "2025-05-01"}],
    ))
    assert r.status_code == 200
    assert r.json()["policies"] == {"saved": 1, "skipped": 0}
    assert apply_env.calls["policies"][0]["client_id"] == 12


def test_apply_enrich_failure_500(apply_env, monkeypatch):
    from managers import case_manager

    monkeypatch.setattr(
        case_manager, "enrich_case",
        lambda *a, **k: {"error": "enrich_failed"},
    )
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload())
    assert r.status_code == 500


# ── Eşzamanlılık koruması: 409 + yeniden birleştir (sertleştirme İş 2) ───────

def test_is_stale_case_signature():
    from managers.case_manager import is_stale_case

    now = datetime(2026, 8, 1, 12, 0, 0)
    assert is_stale_case(now, None) is False          # imza yok → kontrol atlanır
    assert is_stale_case(now, "") is False
    assert is_stale_case(now, "2026-08-01T12:00:00") is False   # güncel imza
    assert is_stale_case(now, "2026-08-01T11:59:59") is True    # bayat imza
    assert is_stale_case(None, "2026-08-01T12:00:00") is True   # dava imzasız, istemci imzalı
    assert is_stale_case(now, "saçma-değer") is True            # ayrıştırılamayan → bayat


def test_apply_stale_signature_409_consumes_nothing(apply_env):
    from routes.processing import PROCESS_CACHE

    apply_env.put_cache("pid-stale")
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        expected_updated_at="2026-08-01T11:00:00",  # dava 12:00'de güncellenmişti
        documents=[{"process_id": "pid-stale", "new_filename": "tensip.pdf"}],
    ))
    try:
        assert r.status_code == 409
        assert "yeniden birleştirilecek" in r.json()["detail"]
        # Belge TÜKETİLMEDİ: arşiv döngüsü hiç koşmadı, cache girdisi duruyor —
        # frontend'in re-merge + yeniden Kaydet akışı güvenli.
        assert PROCESS_CACHE.touch("pid-stale") is True
        assert apply_env.calls["convert"] == []
        # enrich_case bayat imzayı aldı ve alan yazmadan reddetti
        assert apply_env.calls["enrich"][0]["expected_updated_at"] == "2026-08-01T11:00:00"
    finally:
        PROCESS_CACHE.delete("pid-stale")


def test_apply_current_signature_200(apply_env):
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload(
        expected_updated_at="2026-08-01T12:00:00",
    ))
    assert r.status_code == 200
    assert apply_env.calls["enrich"][0]["expected_updated_at"] == "2026-08-01T12:00:00"


def test_apply_without_signature_skips_check(apply_env):
    # Geriye uyum: eski istemci imza göndermez → kontrol yok, davranış değişmez
    r = apply_env.client.post("/api/case-intake/apply", json=_apply_payload())
    assert r.status_code == 200
    assert apply_env.calls["enrich"][0]["expected_updated_at"] is None
