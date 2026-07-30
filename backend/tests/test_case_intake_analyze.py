"""Otonom dava açma Faz 2 testleri — intake motoru saf fonksiyonları + route.

Gemini'ye AĞ ÇAĞRISI YAPILMAZ: çoğunluk oyu / doğrulayıcı / regex yardımcıları
gerçek unit test; route testi generator'ı monkeypatch'ler (kickoff dokümanı,
"Testler" maddesi).
"""
import io
import os
import zipfile

import pytest

# analyzer import'u GEMINI_MODEL_NAME yoksa ValueError fırlatır — app
# modüllerinden önce güvenli varsayılan (conftest DB/vault'u hallediyor).
os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import case_intake_analyzer  # noqa: E402
from case_intake_analyzer import (  # noqa: E402
    apply_verification,
    build_critical_claims,
    guess_doctype_code,
    majority_vote,
    norm_key,
    pick_ozet,
    regex_crosscheck,
    regex_prehints,
)
from routes.case_intake import resolve_upload_suffix  # noqa: E402


def _run(**overrides):
    """Tek ensemble koşusunun model_dump() çıktısını taklit eder."""
    base = {f: None for f in case_intake_analyzer.SCALAR_FIELDS}
    base["taraflar"] = []
    base["ozet"] = None
    base.update(overrides)
    return base


# ── norm_key ─────────────────────────────────────────────────────────────────

def test_norm_key_accent_case_whitespace():
    assert norm_key("İstanbul  Anadolu") == norm_key("ISTANBUL ANADOLU")
    assert norm_key(" 2024/123 ") == "2024/123"


# ── majority_vote ────────────────────────────────────────────────────────────

def test_majority_vote_full_agreement():
    runs = [_run(esas_no="2024/123") for _ in range(3)]
    merged, _ = majority_vote(runs)
    assert merged["esas_no"]["value"] == "2024/123"
    assert merged["esas_no"]["agreement"] == 1.0


def test_majority_vote_two_of_three_wins():
    runs = [_run(esas_no="2024/123"), _run(esas_no="2024/123"), _run(esas_no="2024/999")]
    merged, _ = majority_vote(runs)
    assert merged["esas_no"]["value"] == "2024/123"
    assert merged["esas_no"]["agreement"] == 0.67
    assert merged["esas_no"]["candidates"]["2024/123"] == 2
    assert merged["esas_no"]["candidates"]["2024/999"] == 1


def test_majority_vote_null_majority_wins():
    runs = [_run(), _run(), _run(esas_no="2024/1")]
    merged, _ = majority_vote(runs)
    assert merged["esas_no"]["value"] is None
    assert merged["esas_no"]["agreement"] == 0.67


def test_majority_vote_normalizes_but_keeps_first_raw():
    # Aksan/boşluk farkı aynı oy sepetine düşer; ilk görülen ham hal gösterilir
    runs = [
        _run(mahkeme="ANKARA 3. ASLİYE HUKUK MAHKEMESİ"),
        _run(mahkeme="Ankara 3. Asliye Hukuk Mahkemesi"),
        _run(mahkeme="ANKARA 3.  ASLIYE HUKUK MAHKEMESI"),
    ]
    merged, _ = majority_vote(runs)
    assert merged["mahkeme"]["agreement"] == 1.0
    assert merged["mahkeme"]["value"] == "ANKARA 3. ASLİYE HUKUK MAHKEMESİ"


def test_majority_vote_party_union_and_role_vote():
    from party_check import normalize_person_name

    runs = [
        _run(taraflar=[
            {"ad": "AHMET YILMAZ", "rol": "DAVACI", "tc_no": None},
            {"ad": "MEHMET ÖZ", "rol": "DAVALI", "tc_no": "***123*"},
        ]),
        _run(taraflar=[
            {"ad": "Ahmet Yılmaz", "rol": "DAVACI", "tc_no": None},
        ]),
        _run(taraflar=[
            {"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None},
        ]),
    ]
    _, parties = majority_vote(runs)
    by_name = {normalize_person_name(p["ad"]): p for p in parties}
    ahmet = by_name[normalize_person_name("AHMET YILMAZ")]
    assert ahmet["rol"] == "DAVACI"           # 2/3 oy
    assert ahmet["agreement"] == 1.0          # 3 koşunun 3'ünde görüldü
    mehmet = by_name[normalize_person_name("MEHMET ÖZ")]
    assert mehmet["tc_no"] == "***123*"
    assert mehmet["agreement"] == 0.33


def test_majority_vote_party_title_variants_merge():
    """'Av. X' ile 'X' aynı kişidir — oy bölünmez, agreement 1.0'ı aşmaz."""
    runs = [
        _run(taraflar=[
            {"ad": "Av. FATİH BEYAZIT", "rol": "VEKIL", "tc_no": None},
            {"ad": "FATİH BEYAZIT", "rol": "VEKIL", "tc_no": None},   # aynı koşuda çift varyant
        ]),
        _run(taraflar=[{"ad": "FATİH BEYAZIT", "rol": "VEKIL", "tc_no": None}]),
        _run(taraflar=[{"ad": "Av. FATİH BEYAZIT", "rol": "VEKIL", "tc_no": None}]),
    ]
    _, parties = majority_vote(runs)
    assert len(parties) == 1
    assert parties[0]["rol"] == "VEKIL"
    assert parties[0]["agreement"] == 1.0


# ── pick_ozet ────────────────────────────────────────────────────────────────

def test_pick_ozet_prefers_longest():
    runs = [_run(ozet="Kısa."), _run(ozet="Çok daha uzun ve bilgilendirici özet."), _run()]
    assert pick_ozet(runs) == "Çok daha uzun ve bilgilendirici özet."
    assert pick_ozet([_run(), _run()]) is None


# ── kritik alan doğrulayıcısı ────────────────────────────────────────────────

def test_build_critical_claims():
    merged, parties = majority_vote([
        _run(esas_no="2024/55", taraflar=[
            {"ad": "AHMET YILMAZ", "rol": "DAVACI", "tc_no": "***456*"},
            {"ad": "X SİGORTA A.Ş.", "rol": "SIGORTA_SIRKETI", "tc_no": None},
        ]),
    ])
    claims = build_critical_claims(merged, parties)
    alanlar = {c["alan"] for c in claims}
    assert "esas_no" in alanlar
    assert "tc_no:AHMET YILMAZ" in alanlar
    assert "rol:AHMET YILMAZ" in alanlar
    assert "rol:X SİGORTA A.Ş." in alanlar
    assert "tc_no:X SİGORTA A.Ş." not in alanlar   # TC'si yok → iddia üretilmez


def test_build_critical_claims_empty_when_nothing_critical():
    merged, parties = majority_vote([_run()])
    assert build_critical_claims(merged, parties) == []


def test_apply_verification_matches_and_marks_unknown():
    claims = [
        {"alan": "esas_no", "deger": "2024/55"},
        {"alan": "rol:AHMET", "deger": "DAVACI"},
    ]
    kontroller = [
        {"alan": "esas_no", "deger": "2024/55", "belgede_geciyor": True, "kanit": "ESAS NO: 2024/55"},
        # rol iddiası yanıtlanmadı → bilinmiyor (None) kalmalı
    ]
    out = apply_verification(claims, kontroller)
    assert out["esas_no"]["belgede_geciyor"] is True
    assert out["esas_no"]["kanit"] == "ESAS NO: 2024/55"
    assert out["rol:AHMET"]["belgede_geciyor"] is None


def test_apply_verification_verifier_failure_leaves_all_unknown():
    claims = [{"alan": "esas_no", "deger": "2024/55"}]
    out = apply_verification(claims, [])
    assert out["esas_no"] == {"deger": "2024/55", "belgede_geciyor": None, "kanit": None}


# ── belge türü kodu tahmini ──────────────────────────────────────────────────

DOCTYPES = [
    {"code": "TENSIP-ZPT____", "name": "Tensip Zaptı"},
    {"code": "DAVA-DLK______", "name": "Dava Dilekçesi"},
    {"code": "POLICE________", "name": "Sigorta Poliçesi"},
]


def test_guess_doctype_exact_label():
    # Pad'li kod olduğu gibi döner (doctype_code_padding kuralı)
    assert guess_doctype_code("Tensip Zaptı", DOCTYPES) == "TENSIP-ZPT____"


def test_guess_doctype_partial_containment():
    assert guess_doctype_code("Sigorta Poliçesi (Zeyilname)", DOCTYPES) == "POLICE________"


def test_guess_doctype_no_match_or_empty():
    assert guess_doctype_code("Bilinmeyen Tür", DOCTYPES) is None
    assert guess_doctype_code(None, DOCTYPES) is None
    assert guess_doctype_code("Tensip Zaptı", []) is None


# ── regex ipuçları / çapraz kontrol ──────────────────────────────────────────

TEXT = "T.C. ANKARA 3. ASLİYE HUKUK MAHKEMESİ ESAS NO: 2024/123 Duruşma 15.03.2024 günü"


def test_regex_prehints():
    hints = regex_prehints(TEXT)
    assert "2024/123" in hints["esas_no adayları"]
    assert "2024-03-15" in hints["belgede geçen tarihler"]
    assert regex_prehints(None) == {}
    assert regex_prehints("ipucu yok") == {}


def test_regex_crosscheck():
    merged, _ = majority_vote([_run(esas_no="2024/123")])
    assert regex_crosscheck(merged, TEXT) == {"esas_no": True}
    merged_bad, _ = majority_vote([_run(esas_no="2024/999")])
    assert regex_crosscheck(merged_bad, TEXT) == {"esas_no": False}
    assert regex_crosscheck(merged, None) == {"esas_no": None}
    merged_null, _ = majority_vote([_run()])
    assert regex_crosscheck(merged_null, TEXT) == {"esas_no": None}


# ── route: uzantı çözümü ─────────────────────────────────────────────────────

def test_resolve_upload_suffix():
    assert resolve_upload_suffix("belge.PDF") == ".pdf"
    assert resolve_upload_suffix("Tensip.UDF.ZIP") == ".udf"   # UDF zaten zip'tir
    assert resolve_upload_suffix("evrak.udf") == ".udf"
    assert resolve_upload_suffix("uzantisiz") == ""
    assert resolve_upload_suffix(None) == ""


# ── route: NDJSON stream (Gemini monkeypatch'li) ─────────────────────────────

@pytest.fixture()
def intake_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import case_intake

    async def fake_generator(file_path, file_hash=None, process_id=None, ensemble_n=None):
        yield {"status": "info", "message": "çıkarım başladı"}
        yield {
            "status": "complete",
            "data": {"esas_no": "2024/123", "hash": file_hash, "agreement": {"esas_no": 1.0}},
            "full_pdf_path": file_path,
        }

    monkeypatch.setattr(case_intake_analyzer, "analyze_intake_file_generator", fake_generator)

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "test@example.com"}
    return TestClient(app)


def _post_file(client, filename, content):
    return client.post(
        "/api/case-intake/analyze",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
    )


def _parse_ndjson(resp):
    import json as _json

    return [_json.loads(line) for line in resp.text.strip().splitlines()]


def test_analyze_route_streams_ndjson_and_caches_pdf(intake_client):
    from file_utils import safe_remove
    from routes.processing import PROCESS_CACHE

    resp = _post_file(intake_client, "tensip.pdf", b"%PDF-1.4\n%test icerik\n")
    assert resp.status_code == 200
    assert "application/x-ndjson" in resp.headers["content-type"]

    events = _parse_ndjson(resp)
    assert events[0]["status"] == "info"
    final = events[-1]
    assert final["status"] == "complete"
    assert final["data"]["esas_no"] == "2024/123"
    assert len(final["data"]["hash"]) == 64            # gerçek sha256 hesaplandı

    # Tam PDF /process hijyeniyle PROCESS_CACHE'e kondu
    process_id = final["process_id"]
    entry = PROCESS_CACHE.get(process_id)
    assert entry is not None
    assert entry["original_ext"] == ".pdf"
    assert os.path.exists(entry["path"])               # temp dosya silinmedi (cache sahipliği)

    # temizlik
    safe_remove(entry["path"])
    PROCESS_CACHE.delete(process_id)


def test_analyze_route_accepts_udf_zip_named_files(intake_client):
    """UYAP '.udf.zip' adlı dosya .udf olarak işlenir (kickoff tuzak listesi)."""
    from file_utils import safe_remove
    from routes.processing import PROCESS_CACHE

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", "<udf></udf>")

    resp = _post_file(intake_client, "Tensip Zaptı.udf.zip", buf.getvalue())
    assert resp.status_code == 200
    final = _parse_ndjson(resp)[-1]
    assert final["status"] == "complete"

    entry = PROCESS_CACHE.get(final["process_id"])
    assert entry["original_ext"] == ".udf"
    assert entry["path"].endswith(".udf")              # temp .udf uzantısıyla yazıldı
    safe_remove(entry["path"])
    PROCESS_CACHE.delete(final["process_id"])


def test_analyze_route_rejects_disallowed_extension(intake_client):
    resp = _post_file(intake_client, "zararli.exe", b"MZ\x90\x00")
    assert resp.status_code == 400


def test_analyze_route_rejects_spoofed_pdf(intake_client):
    # .pdf uzantılı ama PDF magic'i yok → validate_file_type 400 vermeli
    resp = _post_file(intake_client, "sahte.pdf", b"MZ\x90\x00sahte")
    assert resp.status_code == 400


def test_analyze_route_error_stream_deletes_temp(intake_client, monkeypatch):
    async def failing_generator(file_path, file_hash=None, process_id=None, ensemble_n=None):
        yield {"status": "error", "message": "tüm koşular geçersiz"}

    monkeypatch.setattr(case_intake_analyzer, "analyze_intake_file_generator", failing_generator)
    resp = _post_file(intake_client, "tensip.pdf", b"%PDF-1.4\nx\n")
    events = _parse_ndjson(resp)
    assert events[-1]["status"] == "error"
    assert "process_id" not in events[-1]
