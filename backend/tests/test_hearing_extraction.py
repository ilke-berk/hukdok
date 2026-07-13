"""Duruşma tarihi çıkarımı testleri — tebligat zinciri genişletmesi.

Kapsam:
- constants.is_hearing_doctype (keyword gate, padding'li kodlar dahil)
- analyzer._pre_extract_hearing (cümle-tipi kalıplar + tebligat etiket-pencere)
- analyzer._apply_hearing_fields (plausibility guard)
- document_pipeline.save_hearing_date (dedup; SessionLocal fake'lenir)

conftest'teki DB guard + vault stub sayesinde import ağa/DB'ye dokunmaz.
"""
import os

os.environ.setdefault("GEMINI_MODEL_NAME", "test-model")

import pytest

from constants import is_hearing_doctype
from analyzer import _pre_extract_hearing, _apply_hearing_fields


def _fresh_pre():
    return {"sonraki_durusma_tarihi": None, "sonraki_durusma_saati": None}


# Örnek e-tebligat zarfının anonimleştirilmiş metni: değerler etiketlerden
# ÖNCE gelir (PDF metin çıkarma sırası), duruşma bilgisi form alanında yazar.
TEBLIGAT_FORM_TEXT = """3. Tüketici Mahkemesi
Dosya No: 2022/185 Esas
TEBLİĞ MAZBATASI
İSTANBUL
T.C.
Davalı VELİ YILDIZ Vekili Av. AYLİN DEMİR
Mühür ve İmza
17/11/2026
10:25
İstanbul 3. Tüketici Mahkemesi Duruşma Salonu
Duruşma Günü
Duruşma Saati
Duruşma Yeri
T.C.
E-TEBLİGAT
BU ZARFTA Ara Karar Evrakı - 07/07/2026  VARDIR.
"""


# ── is_hearing_doctype ───────────────────────────────────────────────────────

class TestHearingDoctypeGate:
    @pytest.mark.parametrize(
        "code",
        ["TEBLIGAT", "TEBLIGAT______", "TEBLIG", "DURUSMA-ZPT", "TENSIP___", "ZABIT", "TUTANAK"],
    )
    def test_hearing_types_accepted(self, code):
        assert is_hearing_doctype(code) is True

    @pytest.mark.parametrize("code", ["ARA-KRR_______", "DILEKCE", "", None])
    def test_other_types_rejected(self, code):
        assert is_hearing_doctype(code) is False


# ── _pre_extract_hearing ─────────────────────────────────────────────────────

class TestPreExtractHearing:
    def test_tebligat_form_layout_value_before_label(self):
        pre = _fresh_pre()
        _pre_extract_hearing(pre, TEBLIGAT_FORM_TEXT)
        assert pre["sonraki_durusma_tarihi"] == "2026-11-17"
        assert pre["sonraki_durusma_saati"] == "10:25"

    def test_tebligat_label_before_value(self):
        pre = _fresh_pre()
        _pre_extract_hearing(pre, "Duruşma Günü: 17/11/2026\nDuruşma Saati: 10:25\n")
        assert pre["sonraki_durusma_tarihi"] == "2026-11-17"
        assert pre["sonraki_durusma_saati"] == "10:25"

    def test_dotted_date_not_mistaken_for_time(self):
        pre = _fresh_pre()
        _pre_extract_hearing(pre, "17.11.2026\n10:25\nDuruşma Günü\nDuruşma Saati\n")
        assert pre["sonraki_durusma_tarihi"] == "2026-11-17"
        assert pre["sonraki_durusma_saati"] == "10:25"

    def test_sentence_pattern_regression(self):
        # Duruşma zaptındaki cümle-tipi kalıp çalışmaya devam etmeli
        pre = _fresh_pre()
        _pre_extract_hearing(
            pre,
            "Duruşmanın 15/09/2026 günü saat 10:00'a bırakılmasına karar verildi.",
        )
        assert pre["sonraki_durusma_tarihi"] == "2026-09-15"
        assert pre["sonraki_durusma_saati"] == "10:00"

    def test_no_hearing_info_stays_none(self):
        # Zarf tarihi var ama duruşma bilgisi yok → alan boş kalmalı
        pre = _fresh_pre()
        _pre_extract_hearing(pre, "BU ZARFTA Ara Karar Evrakı - 07/07/2026  VARDIR.")
        assert pre["sonraki_durusma_tarihi"] is None
        assert pre["sonraki_durusma_saati"] is None


# ── _apply_hearing_fields (plausibility guard) ───────────────────────────────

class TestApplyHearingFields:
    def test_hearing_before_doc_date_discarded(self):
        data = {"tarih": "2026-07-07", "sonraki_durusma_tarihi": "2026-07-01", "sonraki_durusma_saati": "10:00"}
        _apply_hearing_fields(data, _fresh_pre(), [])
        assert data["sonraki_durusma_tarihi"] is None
        assert data["sonraki_durusma_saati"] is None

    def test_hearing_after_doc_date_kept(self):
        data = {"tarih": "2026-07-07", "sonraki_durusma_tarihi": "2026-11-17", "sonraki_durusma_saati": "10:25"}
        _apply_hearing_fields(data, _fresh_pre(), [])
        assert data["sonraki_durusma_tarihi"] == "2026-11-17"
        assert data["sonraki_durusma_saati"] == "10:25"

    def test_past_hearing_without_doc_date_kept(self):
        # Arşiv yüklemeleri: belge tarihi yoksa geçmiş duruşma tarihi elenmez
        data = {"tarih": None, "sonraki_durusma_tarihi": "2020-01-15", "sonraki_durusma_saati": None}
        _apply_hearing_fields(data, _fresh_pre(), [])
        assert data["sonraki_durusma_tarihi"] == "2020-01-15"

    def test_invalid_iso_discarded(self):
        data = {"tarih": "2026-07-07", "sonraki_durusma_tarihi": "17/11/2026", "sonraki_durusma_saati": "10:25"}
        _apply_hearing_fields(data, _fresh_pre(), [])
        assert data["sonraki_durusma_tarihi"] is None
        assert data["sonraki_durusma_saati"] is None

    def test_regex_result_overrides_llm(self):
        pre = {"sonraki_durusma_tarihi": "2026-11-17", "sonraki_durusma_saati": "10:25"}
        data = {"tarih": "2026-07-07", "sonraki_durusma_tarihi": "2026-12-01", "sonraki_durusma_saati": "09:00"}
        _apply_hearing_fields(data, pre, [])
        assert data["sonraki_durusma_tarihi"] == "2026-11-17"
        assert data["sonraki_durusma_saati"] == "10:25"


# ── save_hearing_date (dedup) ────────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """HearingDate insert'lerini store listesinde biriktiren minimal session."""

    def __init__(self, store):
        self._store = store

    def query(self, model):
        import models
        if model is models.HearingDate:
            return _FakeQuery(self._store[0] if self._store else None)
        return _FakeQuery(None)  # Case sorgusu → avukat fallback'i None kalır

    def add(self, obj):
        self._store.append(obj)

    def commit(self):
        pass

    def close(self):
        pass


class TestSaveHearingDateDedup:
    def _call(self, store, belge_turu_kodu="TEBLIGAT______", tarih="2026-11-17"):
        from services import document_pipeline
        results = {}
        document_pipeline.save_hearing_date(
            linked_case_id=1,
            belge_turu_kodu=belge_turu_kodu,
            sonraki_durusma_tarihi=tarih,
            sonraki_durusma_saati="10:25",
            avukat_adi="Av. Test",
            new_filename="test.pdf",
            current_user_name="tester",
            results=results,
        )
        return results

    @pytest.fixture
    def fake_db(self, monkeypatch):
        from services import document_pipeline
        store = []
        monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: _FakeSession(store))
        return store

    def test_tebligat_saves_hearing(self, fake_db):
        results = self._call(fake_db)
        assert results["hearing_date_saved"] == "2026-11-17"
        assert len(fake_db) == 1

    def test_duplicate_skipped(self, fake_db):
        self._call(fake_db)
        results = self._call(fake_db)  # aynı kayıt ikinci kez
        assert results["hearing_date_saved"] == "2026-11-17"  # idempotent
        assert len(fake_db) == 1  # mükerrer satır yok

    def test_non_hearing_doctype_skipped(self, fake_db):
        results = self._call(fake_db, belge_turu_kodu="ARA-KRR_______")
        assert results["hearing_date_saved"] is None
        assert len(fake_db) == 0
