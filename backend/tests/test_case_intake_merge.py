"""Otonom dava açma Faz 3 testleri — merge servisi saf fonksiyonları + route'lar.

Gemini'ye ve DB'ye erişim YOK: birleştirme/poliçe/hakem-uygulama fonksiyonları
gerçek unit test; merge route'u DB bağlam yükleyicileri ve hakem çağrısı
monkeypatch'lenerek test edilir (plan "Test" bölümü).
"""
import os
from datetime import date

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

from services.case_intake import (  # noqa: E402
    apply_arbitration,
    build_doc_summaries,
    build_draft,
    client_priors,
    detect_conflicts,
    match_client,
    merge_fields,
    merge_parties,
    merge_policies,
    parse_iso_date,
    policy_overlap_warnings,
    suggest_known_court,
)


def _doc(filename, process_id=None, **extraction):
    extraction.setdefault("taraflar", [])
    return {
        "process_id": process_id or f"pid-{filename}",
        "filename": filename,
        "extraction": extraction,
    }


CLIENT_ROWS = [
    {"id": 12, "name": "Ahmet YILMAZ", "tc_no": "12345678901",
     "cari_kod": "000012", "category": "Doktor", "contact_type": "Client"},
    {"id": 33, "name": "XYZ SİGORTA A.Ş.", "tc_no": None,
     "cari_kod": "000033", "category": "Sigorta Şirketi", "contact_type": "Other"},
]


# ── parse_iso_date ───────────────────────────────────────────────────────────

def test_parse_iso_date_variants():
    assert parse_iso_date("2024-03-15") == date(2024, 3, 15)
    assert parse_iso_date("15.03.2024") == date(2024, 3, 15)
    assert parse_iso_date(date(2024, 3, 15)) == date(2024, 3, 15)
    assert parse_iso_date("saçma") is None
    assert parse_iso_date(None) is None


# ── merge_fields: çoğunluk oyu ───────────────────────────────────────────────

def test_merge_fields_majority_and_denominator():
    """Payda alanı DOLU belge sayısıdır — poliçe belgesinin esas_no'suz olması
    esas_no güvenini düşürmez (plan örneği: 3/4 → 0.75)."""
    docs = [
        _doc("tensip.pdf", esas_no="2024/123"),
        _doc("dilekce.pdf", esas_no="2024/123"),
        _doc("teblig.pdf", esas_no="2023/98"),
        _doc("police.pdf"),  # esas_no yok — paydaya girmez
    ]
    fields = merge_fields(docs)
    esas = fields["esas_no"]
    assert esas["value"] == "2024/123"
    assert esas["agreement"] == 0.67
    assert len(esas["candidates"]) == 2
    assert set(esas["sources"]) == {"tensip.pdf", "dilekce.pdf"}


def test_merge_fields_esas_no_tie_breaks_by_newest_belge_tarihi():
    docs = [
        _doc("eski-teblig.pdf", esas_no="2022/50", belge_tarihi="2022-01-10"),
        _doc("yeni-tensip.pdf", esas_no="2024/1", belge_tarihi="2024-02-01"),
    ]
    fields = merge_fields(docs)
    assert fields["esas_no"]["value"] == "2024/1"


def test_merge_fields_confidence_composes_ensemble_agreement():
    docs = [
        _doc("a.pdf", esas_no="2024/5", agreement={"esas_no": 0.67}),
        _doc("b.pdf", esas_no="2024/5", agreement={"esas_no": 1.0}),
    ]
    fields = merge_fields(docs)
    # belge-arası 1.0 × ensemble ort. (0.835) ≈ 0.83-0.84 (float yuvarlaması)
    assert fields["esas_no"]["agreement"] == 1.0
    assert fields["esas_no"]["confidence"] == pytest.approx(0.835, abs=0.01)


def test_merge_fields_subject_prefers_dilekce():
    docs = [
        _doc("tensip.pdf", belge_turu_tahmini="Tensip Zaptı", dava_konusu="Tazminat"),
        _doc("teblig.pdf", belge_turu_tahmini="Tebligat", dava_konusu="Tazminat"),
        _doc("dilekce.pdf", belge_turu_tahmini="Dava Dilekçesi",
             dava_konusu="Tıbbi uygulama hatasından doğan maddi ve manevi tazminat"),
    ]
    fields = merge_fields(docs)
    assert fields["subject"]["value"].startswith("Tıbbi uygulama")


def test_merge_fields_opening_date_explicit_wins():
    docs = [
        _doc("tensip.pdf", dava_acilis_tarihi="2024-01-15"),
        _doc("dilekce.pdf", belge_turu_tahmini="Dava Dilekçesi", belge_tarihi="2023-12-01"),
    ]
    fields = merge_fields(docs)
    assert fields["opening_date"]["value"] == "2024-01-15"
    assert "derived_from" not in fields["opening_date"]


def test_merge_fields_opening_date_derived_from_earliest_dilekce():
    docs = [
        _doc("dilekce.pdf", belge_turu_tahmini="Dava Dilekçesi", belge_tarihi="2023-12-01"),
        _doc("cevap.pdf", belge_turu_tahmini="Cevap Dilekçesi", belge_tarihi="2024-02-01"),
        _doc("police.pdf", belge_turu_tahmini="Sigorta Poliçesi", belge_tarihi="2023-05-01"),
    ]
    fields = merge_fields(docs)
    assert fields["opening_date"]["value"] == "2023-12-01"   # poliçe tarihi DEĞİL
    assert fields["opening_date"]["derived_from"] == "belge_tarihi"
    assert fields["opening_date"]["confidence"] == 0.4


def test_merge_fields_verification_and_regex_flags():
    docs = [
        _doc(
            "tensip.pdf", esas_no="2024/7",
            verification={"esas_no": {"deger": "2024/7", "belgede_geciyor": True, "kanit": "ESAS NO: 2024/7"}},
            regex_check={"esas_no": True},
        ),
        _doc("dilekce.pdf", esas_no="2024/7", regex_check={"esas_no": None}),
    ]
    fields = merge_fields(docs)
    assert fields["esas_no"]["verified"] is True
    assert fields["esas_no"]["regex_check"] is True


def test_merge_fields_empty_docs():
    fields = merge_fields([_doc("bos.pdf")])
    assert fields["esas_no"]["value"] is None
    assert fields["opening_date"]["value"] is None


# ── çelişki tespiti + hakem uygulaması ───────────────────────────────────────

def test_detect_conflicts_only_on_multiple_candidates():
    docs = [
        _doc("a.pdf", esas_no="2024/1", mahkeme="ANKARA 1. ASLİYE HUKUK MAHKEMESİ"),
        _doc("b.pdf", esas_no="2023/9", mahkeme="ANKARA 1. ASLİYE HUKUK MAHKEMESİ"),
    ]
    conflicts = detect_conflicts(merge_fields(docs))
    assert [c["alan"] for c in conflicts] == ["esas_no"]
    assert len(conflicts[0]["adaylar"]) == 2


def test_apply_arbitration_switches_value_and_reports_unapplied():
    docs = [
        _doc("teblig.pdf", esas_no="2022/50", belge_tarihi="2024-03-01"),
        _doc("tensip.pdf", esas_no="2024/1", belge_tarihi="2024-02-01"),
    ]
    fields = merge_fields(docs)
    # Beraberlikte en yeni belge_tarihi kazanmıştı (teblig) — hakem tensibi seçiyor
    assert fields["esas_no"]["value"] == "2022/50"
    unapplied = apply_arbitration(fields, [
        {"alan": "esas_no", "secilen_deger": "2024/1", "gerekce": "Tensip mahkemenin kendi kaydı."},
        {"alan": "esas_no", "secilen_deger": "2099/999", "gerekce": "uydurma"},
        {"alan": "court", "secilen_deger": "X", "gerekce": "aday yok"},
    ])
    assert fields["esas_no"]["value"] == "2024/1"
    assert fields["esas_no"]["arbiter"]["gerekce"] == "Tensip mahkemenin kendi kaydı."
    assert fields["esas_no"]["sources"] == ["tensip.pdf"]
    assert len(unapplied) == 2


def test_build_doc_summaries_shape():
    docs = [_doc("a.pdf", belge_turu_tahmini="Tensip Zaptı", esas_no="2024/1", ozet="Özet.")]
    s = build_doc_summaries(docs)
    assert s[0]["dosya"] == "a.pdf"
    assert s[0]["esas_no"] == "2024/1"
    assert s[0]["ozet"] == "Özet."


# ── taraf birleştirme ────────────────────────────────────────────────────────

def test_merge_parties_dedupes_accents_and_prefers_litigation_role():
    """Hekim dilekçede DAVALI, iki poliçede SIGORTALI — rolü DAVALI kalmalı."""
    docs = [
        _doc("dilekce.pdf", taraflar=[
            {"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None},
            {"ad": "Av. Fatih BEYAZIT", "rol": "VEKIL", "tc_no": None},
        ]),
        _doc("police1.pdf", taraflar=[{"ad": "Ahmet Yılmaz", "rol": "SIGORTALI", "tc_no": "12345678901"}]),
        _doc("police2.pdf", taraflar=[{"ad": "AHMET YILMAZ", "rol": "SIGORTALI", "tc_no": None}]),
    ]
    parties = merge_parties(docs, client_rows=[])
    assert len(parties) == 1                       # vekil listeye girmez, aksan tekilleşir
    p = parties[0]
    assert p["rol"] == "DAVALI"
    assert p["tc_no"] == "12345678901"             # herhangi bir belgedeki TC korunur
    assert p["doc_count"] == 3
    assert p["party_type"] == "CLIENT"             # SIGORTALI görülen hekim → müvekkil adayı


def test_merge_parties_party_type_mapping():
    docs = [
        _doc("dilekce.pdf", taraflar=[
            {"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None},      # kayıtlı cari → CLIENT
            {"ad": "MEHMET ÖZ", "rol": "DAVACI", "tc_no": None},         # eşleşmesiz davacı → COUNTER
            {"ad": "XYZ SİGORTA A.Ş.", "rol": "DAVALI", "tc_no": None},  # contact_type=Other → COUNTER
            {"ad": "VELİ KAYA", "rol": "MUDAHIL", "tc_no": None},        # müdahil → THIRD
        ]),
    ]
    parties = {p["name"]: p for p in merge_parties(docs, CLIENT_ROWS)}
    assert parties["AHMET YILMAZ"]["party_type"] == "CLIENT"
    assert parties["AHMET YILMAZ"]["match"]["client_id"] == 12
    assert parties["AHMET YILMAZ"]["match"]["name"] == "Ahmet YILMAZ"   # kanonik ad önerisi
    assert parties["MEHMET ÖZ"]["party_type"] == "COUNTER"
    assert parties["XYZ SİGORTA A.Ş."]["party_type"] == "COUNTER"
    assert parties["VELİ KAYA"]["party_type"] == "THIRD"


def test_merge_parties_dedupes_corporate_suffix_variants():
    """Duman testi 2026-07-30: hastane "... ANONİM ŞİRKETİ" ve "... A. Ş."
    yazımlarıyla iki ayrı taraf oluyordu — şirket eki eşitlenerek tekilleşmeli."""
    docs = [
        _doc("dilekce.pdf", taraflar=[
            {"ad": "YAŞAM ÖZEL SAĞLIK HİZMETLERİ TİCARET VE SANAYİ ANONİM ŞİRKETİ", "rol": "DAVALI", "tc_no": None},
        ]),
        _doc("tensip.pdf", taraflar=[
            {"ad": "Yaşam Özel Sağlık Hizmetleri Ticaret Ve Sanayi A. Ş.", "rol": "DAVALI", "tc_no": None},
        ]),
    ]
    parties = merge_parties(docs, client_rows=[])
    assert len(parties) == 1
    assert parties[0]["doc_count"] == 2


def test_merge_parties_uncensored_tc_preferred():
    docs = [
        _doc("a.pdf", taraflar=[{"ad": "ALİ CAN", "rol": "DAVACI", "tc_no": "***456*"}]),
        _doc("b.pdf", taraflar=[{"ad": "ALİ CAN", "rol": "DAVACI", "tc_no": "10000000146"}]),
    ]
    parties = merge_parties(docs, [])
    assert parties[0]["tc_no"] == "10000000146"


def test_match_client_tc_beats_name():
    m = match_client("Farklı İsim", "12345678901", CLIENT_ROWS)
    assert m["matched_on"] == "tc_no"
    assert m["client_id"] == 12
    assert m["score"] == 1.0
    assert match_client("Hiç Kimse", None, CLIENT_ROWS) is None


# ── poliçe birleştirme ───────────────────────────────────────────────────────

def _police_doc(filename, police_no, baslangic, bitis, sirket="ABC SİGORTA",
                sigortali="AHMET YILMAZ", turu="ZORUNLU", retroaktif=None):
    return _doc(
        filename,
        belge_turu_tahmini="Sigorta Poliçesi",
        police_no=police_no,
        police_turu=turu,
        sigorta_sirketi=sirket,
        police_baslangic_tarihi=baslangic,
        police_bitis_tarihi=bitis,
        retroaktif_tarihi=retroaktif,
        teminat_limiti=1000000.0,
        taraflar=[
            {"ad": sigortali, "rol": "SIGORTALI", "tc_no": None},
            {"ad": sirket, "rol": "SIGORTA_SIRKETI", "tc_no": None},
        ],
    )


def test_merge_policies_builds_list_and_marks_relevant():
    """Poliçeler oya girmez — liste; açılış tarihi hangi döneme düşüyorsa o relevant."""
    docs = [
        _police_doc("police-2023.pdf", "928/3", "2023-05-01", "2024-05-01"),
        _police_doc("police-2024.pdf", "928/4", "2024-05-01", "2025-05-01"),
    ]
    parties = merge_parties(docs, CLIENT_ROWS)
    policies, warnings = merge_policies(docs, "2024-01-15", parties)
    assert len(policies) == 2
    by_no = {p["police_no"]: p for p in policies}
    assert by_no["928/3"]["relevant"] is True
    assert by_no["928/4"]["relevant"] is False
    assert by_no["928/3"]["sigortali"] == "AHMET YILMAZ"
    assert by_no["928/3"]["client_id"] == 12          # hekim cari eşleşmesinden
    # Uç uca dönemler (eski bitiş == yeni başlangıç) yenileme desenidir — uyarı YOK
    assert not any(w["code"] == "POLICY_PERIOD_OVERLAP" for w in warnings)


def test_merge_policies_retroaktif_extends_coverage():
    docs = [_police_doc("p.pdf", "1", "2024-05-01", "2025-05-01", retroaktif="2020-01-01")]
    policies, _ = merge_policies(docs, "2023-06-01", merge_parties(docs, []))
    assert policies[0]["relevant"] is True


def test_merge_policies_dedupes_same_policy_across_docs():
    docs = [
        _police_doc("kopya1.pdf", "928/4", "2024-05-01", "2025-05-01"),
        _police_doc("kopya2.pdf", "928/4", "2024-05-01", "2025-05-01"),
    ]
    policies, _ = merge_policies(docs, None, [])
    assert len(policies) == 1


def test_merge_policies_merges_known_and_flags_saved():
    docs = [_police_doc("p.pdf", "928/4", "2024-05-01", "2025-05-01")]
    known = [
        {   # aynı poliçe zaten kayıtlı → belge kopyası saved=True, ayrı satır yok
            "id": 1, "client_id": 12, "client_name": "Ahmet YILMAZ",
            "police_no": "928/4", "police_turu": "ZORUNLU", "sigorta_sirketi": "ABC SİGORTA",
            "baslangic_tarihi": date(2024, 5, 1), "bitis_tarihi": date(2025, 5, 1),
            "retroaktif_tarihi": None, "sigortali_kurum": None, "teminat_limiti": None,
        },
        {   # farklı dönem — 'kayıtlı poliçe' kaynağıyla listeye girer
            "id": 2, "client_id": 12, "client_name": "Ahmet YILMAZ",
            "police_no": "801/1", "police_turu": "TAMAMLAYICI", "sigorta_sirketi": "DEF SİGORTA",
            "baslangic_tarihi": date(2022, 1, 1), "bitis_tarihi": date(2023, 1, 1),
            "retroaktif_tarihi": None, "sigortali_kurum": None, "teminat_limiti": 500000,
        },
    ]
    policies, _ = merge_policies(docs, None, [], known_policies=known)
    assert len(policies) == 2
    by_no = {p["police_no"]: p for p in policies}
    assert by_no["928/4"]["saved"] is True
    assert by_no["928/4"]["source"] == "p.pdf"        # belge kopyası korunur
    assert by_no["801/1"]["source"] == "kayıtlı poliçe"
    assert by_no["801/1"]["saved"] is True


def test_merge_policies_period_mismatch_warning():
    """Faz 2 regresyon notu: hiçbir dönem açılış tarihini kapsamıyorsa uyarı."""
    docs = [_police_doc("p.pdf", "1", "2020-01-01", "2021-01-01")]
    _, warnings = merge_policies(docs, "2024-06-01", [])
    assert any(w["code"] == "POLICY_PERIOD_MISMATCH" for w in warnings)


def test_policy_overlap_only_same_company_and_type():
    a = {"police_no": "1", "police_turu": "ZORUNLU", "sigorta_sirketi": "ABC",
         "baslangic": "2024-01-01", "bitis": "2025-01-01"}
    b = {**a, "police_no": "2", "sigorta_sirketi": "DEF"}          # farklı şirket
    c = {**a, "police_no": "3", "police_turu": "TAMAMLAYICI"}      # farklı tür
    d = {**a, "police_no": "4", "baslangic": "2024-06-01", "bitis": "2025-06-01"}
    assert policy_overlap_warnings([a, b]) == []
    assert policy_overlap_warnings([a, c]) == []
    assert len(policy_overlap_warnings([a, d])) == 1


# ── DB destekli zenginleştirme yardımcıları ──────────────────────────────────

def test_suggest_known_court():
    known = ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "İSTANBUL 1. TÜKETİCİ MAHKEMESİ"]
    # Normalize eşit (aksan/boşluk farkı) → bilinen yazım önerilir
    assert suggest_known_court("ankara 3. asliye  hukuk mahkemesi", known) == known[0]
    # Birebir aynı yazım → öneri yok
    assert suggest_known_court(known[0], known) is None
    # Alakasız → öneri yok
    assert suggest_known_court("VAN 2. AĞIR CEZA MAHKEMESİ", known) is None
    assert suggest_known_court(None, known) is None


def test_client_priors_most_common():
    rows = [
        {"file_type": "Hukuk", "sub_type": "ASLIYE-HUKUK", "responsible_lawyer_name": "AGH", "subject": None},
        {"file_type": "Hukuk", "sub_type": "ASLIYE-HUKUK", "responsible_lawyer_name": "AGH", "subject": "Malpraktis"},
        {"file_type": "Ceza", "sub_type": None, "responsible_lawyer_name": "MEH", "subject": "Malpraktis"},
    ]
    priors = client_priors(rows)
    assert priors["file_type"] == {"value": "Hukuk", "count": 2, "total": 3}
    assert priors["responsible_lawyer_name"]["value"] == "AGH"
    assert priors["subject"]["total"] == 2
    assert client_priors([]) == {}


# ── build_draft entegrasyonu ─────────────────────────────────────────────────

def test_build_draft_assembles_and_reports_conflicts():
    docs = [
        _doc("tensip.pdf", esas_no="2024/1", mahkeme="ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
             belge_turu_tahmini="Tensip Zaptı", belge_turu_kodu_tahmini="TENSIP-ZPT____",
             dava_acilis_tarihi="2024-01-15", belge_tarihi="2024-02-01",
             taraflar=[{"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None}]),
        _doc("dilekce.pdf", esas_no="2023/9", mahkeme="ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
             belge_turu_tahmini="Dava Dilekçesi", dava_konusu="Tazminat",
             belge_tarihi="2024-01-10",
             taraflar=[{"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None}]),
        _police_doc("police.pdf", "928/4", "2023-05-01", "2024-05-01"),
    ]
    draft, conflicts = build_draft(
        docs, CLIENT_ROWS,
        known_courts=["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"],
    )
    assert [c["alan"] for c in conflicts] == ["esas_no"]
    assert draft["fields"]["court"]["value"] == "ANKARA 3. ASLİYE HUKUK MAHKEMESİ"
    assert "known_court_suggestion" not in draft["fields"]["court"]   # birebir aynı yazım
    assert draft["fields"]["opening_date"]["value"] == "2024-01-15"
    assert draft["policies"][0]["relevant"] is True
    assert draft["documents"][0]["belge_turu_kodu"] == "TENSIP-ZPT____"
    assert all(d["status"] == "ok" for d in draft["documents"])
    ahmet = next(p for p in draft["parties"] if p["name"] == "AHMET YILMAZ")
    assert ahmet["party_type"] == "CLIENT"


# ── poliçe besleme dedupe anahtarı (client_manager) ──────────────────────────

def test_policy_dedupe_key_normalizes():
    from managers.client_manager import _policy_dedupe_key

    assert _policy_dedupe_key(" 928/4 ", date(2024, 5, 1)) == _policy_dedupe_key("928/4", "2024-05-01")
    assert _policy_dedupe_key("928/4", date(2024, 5, 1)) != _policy_dedupe_key("928/4", date(2025, 5, 1))


# ── route: merge + keepalive ─────────────────────────────────────────────────

@pytest.fixture()
def merge_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import case_intake_analyzer
    import case_matcher
    from dependencies import get_current_tenant, get_current_user
    from routes import case_intake

    monkeypatch.setattr(
        case_intake, "_load_merge_context",
        lambda tenant_id: {
            "client_rows": CLIENT_ROWS,
            "party_rows": [],
            "known_courts": ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"],
        },
    )
    monkeypatch.setattr(
        case_intake, "_load_known_policies",
        lambda client_ids: [{
            "id": 7, "client_id": 12, "client_name": "Ahmet YILMAZ",
            "police_no": "801/1", "police_turu": "TAMAMLAYICI", "sigorta_sirketi": "DEF SİGORTA",
            "baslangic_tarihi": date(2022, 1, 1), "bitis_tarihi": date(2022, 12, 31),
            "retroaktif_tarihi": None, "sigortali_kurum": None, "teminat_limiti": None,
        }],
    )
    monkeypatch.setattr(
        case_intake, "_load_client_case_rows",
        lambda client_ids: {12: [
            {"file_type": "Hukuk", "sub_type": "ASLIYE-HUKUK",
             "responsible_lawyer_name": "AGH", "subject": "Malpraktis"},
        ]},
    )

    arbiter_calls = []

    async def fake_arbiter(conflicts, doc_summaries):
        arbiter_calls.append(conflicts)
        return [{"alan": "esas_no", "secilen_deger": "2024/1",
                 "gerekce": "Tensip mahkemenin kendi kaydı."}]

    monkeypatch.setattr(case_intake_analyzer, "arbitrate_conflicts", fake_arbiter)
    monkeypatch.setattr(
        case_matcher, "find_matching_case",
        lambda **kwargs: {"case_id": 88, "tracking_no": "2024/0088", "esas_no": "2024/1",
                          "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "score": 95,
                          "confidence": "HIGH"},
    )

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "test@example.com"}
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    client = TestClient(app)
    client.arbiter_calls = arbiter_calls
    return client


def _merge_payload():
    return {"documents": [
        {"process_id": "pid-tensip", "filename": "tensip.pdf", "extraction": {
            "esas_no": "2024/1", "mahkeme": "ankara 3. asliye hukuk mahkemesi",
            "belge_turu_tahmini": "Tensip Zaptı", "belge_turu_kodu_tahmini": "TENSIP-ZPT____",
            "dava_acilis_tarihi": "2024-01-15", "belge_tarihi": "2024-02-01",
            "taraflar": [{"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None}],
        }},
        {"process_id": "pid-dilekce", "filename": "dilekce.pdf", "extraction": {
            "esas_no": "2023/9", "mahkeme": "ankara 3. asliye hukuk mahkemesi",
            "belge_turu_tahmini": "Dava Dilekçesi", "dava_konusu": "Tazminat",
            "belge_tarihi": "2024-01-10",
            "taraflar": [{"ad": "AHMET YILMAZ", "rol": "DAVALI", "tc_no": None}],
        }},
        {"process_id": "pid-police", "filename": "police.pdf", "extraction": {
            "belge_turu_tahmini": "Sigorta Poliçesi", "police_no": "928/4",
            "police_turu": "ZORUNLU", "sigorta_sirketi": "ABC SİGORTA",
            "police_baslangic_tarihi": "2023-05-01", "police_bitis_tarihi": "2024-05-01",
            "taraflar": [{"ad": "Ahmet Yılmaz", "rol": "SIGORTALI", "tc_no": None}],
        }},
    ]}


def test_merge_route_full_draft(merge_client):
    from routes.processing import PROCESS_CACHE

    for pid in ("pid-tensip", "pid-dilekce"):   # pid-police kasıtlı olarak cache'te yok
        PROCESS_CACHE.set(pid, {"path": f"/tmp/{pid}.pdf"})
    try:
        resp = merge_client.post("/api/case-intake/merge", json=_merge_payload())
        assert resp.status_code == 200
        draft = resp.json()

        # Hakem çelişkiyi çözdü (esas_no 1-1 beraberlikti)
        assert len(merge_client.arbiter_calls) == 1
        assert draft["fields"]["esas_no"]["value"] == "2024/1"
        assert draft["fields"]["esas_no"]["arbiter"]["gerekce"].startswith("Tensip")

        # Mahkeme bilinen yazımla önerildi (belgeler küçük harfle çıkarmıştı)
        assert draft["fields"]["court"]["known_court_suggestion"] == "ANKARA 3. ASLİYE HUKUK MAHKEMESİ"

        # Taraf: kayıtlı cariye bağlandı, tanıdık sorgu bilgisi iliştirildi
        ahmet = next(p for p in draft["parties"] if p["name"] == "AHMET YILMAZ")
        assert ahmet["party_type"] == "CLIENT"
        assert ahmet["match"]["client_id"] == 12
        assert "check" in ahmet

        # Poliçeler: belge poliçesi (relevant, client_id'li) + kayıtlı poliçe
        by_no = {p["police_no"]: p for p in draft["policies"]}
        assert by_no["928/4"]["relevant"] is True
        assert by_no["928/4"]["client_id"] == 12
        assert by_no["801/1"]["saved"] is True

        # Mükerrer dava + priors + expired belge işareti
        assert draft["duplicate_case"]["id"] == 88
        assert draft["priors"]["12"]["responsible_lawyer_name"]["value"] == "AGH"
        police_doc = next(d for d in draft["documents"] if d["process_id"] == "pid-police")
        assert police_doc["status"] == "expired"
        assert any(w["code"] == "DOCUMENT_EXPIRED" for w in draft["warnings"])
    finally:
        for pid in ("pid-tensip", "pid-dilekce"):
            PROCESS_CACHE.delete(pid)


def test_merge_route_no_conflict_skips_arbiter(merge_client):
    from routes.processing import PROCESS_CACHE

    payload = _merge_payload()
    payload["documents"][1]["extraction"]["esas_no"] = "2024/1"   # çelişki kalmadı
    for pid in ("pid-tensip", "pid-dilekce", "pid-police"):
        PROCESS_CACHE.set(pid, {"path": f"/tmp/{pid}.pdf"})
    try:
        resp = merge_client.post("/api/case-intake/merge", json=payload)
        assert resp.status_code == 200
        assert merge_client.arbiter_calls == []                    # hakem hiç çağrılmadı
        assert resp.json()["fields"]["esas_no"]["agreement"] == 1.0
    finally:
        for pid in ("pid-tensip", "pid-dilekce", "pid-police"):
            PROCESS_CACHE.delete(pid)


def test_merge_route_arbiter_failure_keeps_majority(merge_client, monkeypatch):
    import case_intake_analyzer
    from routes.processing import PROCESS_CACHE

    async def failing_arbiter(conflicts, doc_summaries):
        raise RuntimeError("Gemini 500")

    monkeypatch.setattr(case_intake_analyzer, "arbitrate_conflicts", failing_arbiter)
    for pid in ("pid-tensip", "pid-dilekce", "pid-police"):
        PROCESS_CACHE.set(pid, {"path": f"/tmp/{pid}.pdf"})
    try:
        resp = merge_client.post("/api/case-intake/merge", json=_merge_payload())
        assert resp.status_code == 200
        draft = resp.json()
        assert any(w["code"] == "ARBITER_FAILED" for w in draft["warnings"])
        assert draft["fields"]["esas_no"]["value"] is not None     # çoğunluk sonucu duruyor
    finally:
        for pid in ("pid-tensip", "pid-dilekce", "pid-police"):
            PROCESS_CACHE.delete(pid)


def test_keepalive_route_refreshes_and_reports_expired(merge_client):
    from routes.processing import PROCESS_CACHE

    PROCESS_CACHE.set("pid-alive", {"path": "/tmp/x.pdf"})
    try:
        resp = merge_client.post(
            "/api/case-intake/keepalive",
            json={"process_ids": ["pid-alive", "pid-gone"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refreshed"] == ["pid-alive"]
        assert body["expired"] == ["pid-gone"]
    finally:
        PROCESS_CACHE.delete("pid-alive")


def test_ttl_cache_touch_resets_clock():
    from managers.ttl_cache import TTLCache

    cache = TTLCache(ttl_seconds=1800)
    cache.set("k", {"path": "x"})
    entry_before = cache.get("k")
    assert cache.touch("k") is True
    assert cache.get("k")["_ts"] >= entry_before["_ts"]
    assert cache.touch("yok") is False
