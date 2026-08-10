"""routes/export.py guard testleri (plan 2.1/5).

Faz 1'de yazılan güvenlik guard'larını kilitler: zayıf anahtar tespiti,
fail-closed davranışı, tür allowlist normalizasyonu (pad'li kod tuzağı).
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.export as export


STRONG_KEY = "a" * 64  # 32+ karakter, 'dev-' öneki yok


@pytest.fixture(autouse=True)
def _reset_warn_flag(monkeypatch):
    """CRITICAL log tek-seferlik bayrağını her testte sıfırla."""
    monkeypatch.setattr(export, "_weak_key_warned", False)


# ── _key_is_weak ─────────────────────────────────────────────────────────────

class TestKeyIsWeak:
    @pytest.mark.parametrize(
        "key",
        [
            "kisa",                      # < 32 karakter
            "a" * 31,                    # sınırın hemen altı
            "dev-local-export-key",      # dev- öneki + kısa
            "dev-" + "a" * 40,           # dev- öneki, uzun olsa da zayıf
            "DEV-" + "a" * 40,           # büyük harf önek de yakalanır
        ],
    )
    def test_weak(self, key):
        assert export._key_is_weak(key) is True

    @pytest.mark.parametrize("key", [STRONG_KEY, "f3" * 16])
    def test_strong(self, key):
        assert export._key_is_weak(key) is False

    def test_exactly_32_chars_is_strong(self):
        assert export._key_is_weak("x" * 32) is False


# ── require_export_api_key ───────────────────────────────────────────────────

class TestRequireExportApiKey:
    def test_missing_env_fails_closed_503(self, monkeypatch):
        monkeypatch.delenv("HUKDOK_EXPORT_API_KEY", raising=False)
        with pytest.raises(HTTPException) as exc:
            export.require_export_api_key(x_api_key="herhangi")
        assert exc.value.status_code == 503

    def test_weak_key_without_dev_mode_fails_closed_503(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", "dev-local-key")
        monkeypatch.delenv("DEV_MODE", raising=False)
        with pytest.raises(HTTPException) as exc:
            export.require_export_api_key(x_api_key="dev-local-key")
        assert exc.value.status_code == 503

    def test_weak_key_with_dev_mode_accepted(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", "dev-local-key")
        monkeypatch.setenv("DEV_MODE", "true")
        # İstisna fırlatmamalı
        export.require_export_api_key(x_api_key="dev-local-key")

    def test_weak_key_with_dev_mode_wrong_header_401(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", "dev-local-key")
        monkeypatch.setenv("DEV_MODE", "true")
        with pytest.raises(HTTPException) as exc:
            export.require_export_api_key(x_api_key="yanlis")
        assert exc.value.status_code == 401

    def test_strong_key_correct_header_passes(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", STRONG_KEY)
        monkeypatch.delenv("DEV_MODE", raising=False)
        export.require_export_api_key(x_api_key=STRONG_KEY)

    @pytest.mark.parametrize("header", [None, "", "yanlis-anahtar"])
    def test_strong_key_bad_header_401(self, header, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_API_KEY", STRONG_KEY)
        monkeypatch.delenv("DEV_MODE", raising=False)
        with pytest.raises(HTTPException) as exc:
            export.require_export_api_key(x_api_key=header)
        assert exc.value.status_code == 401


# ── get_type_allowlist ───────────────────────────────────────────────────────

class TestGetTypeAllowlist:
    def test_normalizes_codes(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_TYPES", "GEREKCELI-KRR, ARA-KRR ,bilirkisi-rpr")
        assert export.get_type_allowlist() == {"GEREKCELIKRR", "ARAKRR", "BILIRKISIRPR"}

    def test_empty_env_means_no_filter(self, monkeypatch):
        monkeypatch.setenv("HUKDOK_EXPORT_TYPES", "")
        assert export.get_type_allowlist() == set()

    def test_unset_env_means_no_filter(self, monkeypatch):
        monkeypatch.delenv("HUKDOK_EXPORT_TYPES", raising=False)
        assert export.get_type_allowlist() == set()


# ── _doc_passes_filters ──────────────────────────────────────────────────────

def _doc(link_mode="AUTO", sharepoint_url="https://sp/x.pdf", kod="ARA-KRR_______", case=None, deleted_at=None):
    return SimpleNamespace(
        link_mode=link_mode, sharepoint_url=sharepoint_url, belge_turu_kodu=kod, case=case,
        deleted_at=deleted_at,
    )


class TestDocPassesFilters:
    def test_padded_code_passes_short_allowlist(self):
        # Bilinen tuzak: DB'de pad'li kod, env'de kısa kod
        assert export._doc_passes_filters(_doc(), {"ARAKRR"}, set()) is True

    def test_code_not_in_allowlist_rejected(self):
        assert export._doc_passes_filters(_doc(kod="GEREKCELI-KRR"), {"ARAKRR"}, set()) is False

    def test_types_filter_applies_after_allowlist(self):
        doc = _doc()
        assert export._doc_passes_filters(doc, {"ARAKRR"}, {"GEREKCELIKRR"}) is False
        assert export._doc_passes_filters(doc, {"ARAKRR"}, {"ARAKRR"}) is True

    def test_test_link_mode_rejected(self):
        assert export._doc_passes_filters(_doc(link_mode="TEST"), set(), set()) is False

    def test_unlinked_mode_included(self):
        # UNLINKED bilinçli olarak dahil (BULGULAR #3)
        assert export._doc_passes_filters(_doc(link_mode="UNLINKED"), set(), set()) is True

    def test_missing_sharepoint_url_rejected(self):
        assert export._doc_passes_filters(_doc(sharepoint_url=None), set(), set()) is False
        assert export._doc_passes_filters(_doc(sharepoint_url=""), set(), set()) is False

    def test_none_doc_rejected(self):
        assert export._doc_passes_filters(None, set(), set()) is False

    def test_no_filters_everything_passes(self):
        assert export._doc_passes_filters(_doc(kod=None), set(), set()) is True

    def test_deleted_case_rejected(self):
        # Soft-delete edilmiş davanın belgesi export hattından akmaz
        case = SimpleNamespace(deleted_at="2026-08-05T00:00:00")
        assert export._doc_passes_filters(_doc(case=case), set(), set()) is False

    def test_deleted_document_rejected(self):
        # Soft-delete edilmiş belgenin kendisi de akmaz (restore → tekrar akar)
        assert export._doc_passes_filters(_doc(deleted_at="2026-08-10T00:00:00"), set(), set()) is False

    def test_live_case_passes(self):
        case = SimpleNamespace(deleted_at=None)
        assert export._doc_passes_filters(_doc(case=case), set(), set()) is True

    def test_unlinked_no_case_passes(self):
        # case_id=None (UNLINKED) belgeler bilinçli olarak dahil kalır
        assert export._doc_passes_filters(_doc(case=None), set(), set()) is True
