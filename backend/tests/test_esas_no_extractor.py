"""esas_no_extractor testleri — regex denetim raporu Faz 1.1/1.2 + Faz 2.1.

Kritik regresyon korumaları:
- Karar numarası hiçbir kalıptan esas no olarak sızmamalı (Y1).
- E ile biten kelimeler Kalıp 3'e takılmamalı (GENELGE2022/3 vb.).
- Çıplak YYYY/N artık very_high değil low güvenle dönmeli.
"""
import pytest

from extractors.esas_no_extractor import extract_esas_no_candidates, find_best_esas_no


def _confidences(text):
    return {c["confidence"] for c in extract_esas_no_candidates(text)}


# ── Pozitif formatlar ────────────────────────────────────────────────────────

class TestFormats:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Esas No: 2023/145", "2023/145"),
            ("ESAS NO : 2023/145", "2023/145"),
            ("Esas Numarası: 2023/145", "2023/145"),
            ("Esas: 2023/145", "2023/145"),
            ("Dosya No: 2023/145", "2023/145"),
            ("DOSYA NUMARASI: 2023/145", "2023/145"),
            ("E. 2024/67", "2024/67"),
            ("E:2023/145", "2023/145"),
            ("E 2023/145", "2023/145"),
            ("2023/145 Esas", "2023/145"),
            ("2024/234 sayılı esas", "2024/234"),
        ],
    )
    def test_common_formats(self, text, expected):
        assert find_best_esas_no(text) == expected

    def test_keyword_anchored_is_very_high(self):
        cands = extract_esas_no_candidates("Esas No: 2023/145")
        assert any(c["confidence"] == "very_high" for c in cands)

    def test_e_prefix_is_high(self):
        cands = extract_esas_no_candidates("E. 2024/67")
        assert any(c["confidence"] == "high" for c in cands)


# ── Karar numarası sızması (Y1 regresyonu) ──────────────────────────────────

class TestKararFiltering:
    def test_karar_only_returns_none(self):
        # Eski davranış: "2023/456" very_high esas no dönerdi (Y1 hatası)
        assert find_best_esas_no("Karar No: 2023/456") is None

    def test_karar_number_first_still_finds_esas(self):
        # Belgede karar no esas no'dan ÖNCE geçse bile esas no dönmeli
        text = "Karar No: 2023/456 Esas No: 2023/145"
        assert find_best_esas_no(text) == "2023/145"

    def test_esas_then_karar(self):
        text = "Esas: 2023/145 Karar: 2023/456"
        assert find_best_esas_no(text) == "2023/145"

    def test_yargitay_kunye(self):
        # Yargıtay künyesi: E./K. kısaltmaları
        assert find_best_esas_no("E. 2023/145 K. 2023/456") == "2023/145"

    def test_k_abbreviation_only_returns_none(self):
        assert find_best_esas_no("K. 2023/456") is None

    def test_number_before_karar_word(self):
        assert find_best_esas_no("2023/456 sayılı karar") is None

    def test_same_number_as_esas_and_karar_kept(self):
        # Aynı sayı meşru olarak hem esas hem karar olabilir; ESAS çapası kazanır
        text = "2023/456 Esas 2023/456 Karar"
        assert find_best_esas_no(text) == "2023/456"


# ── Yanlış pozitif korumaları ────────────────────────────────────────────────

class TestFalsePositives:
    def test_word_ending_with_e_not_pattern3(self):
        # "GENELGE" → normalize sonrası "GENELGE2022/3"; E kalıbına takılmamalı.
        # Çıplak sayı olarak yalnız low güvenle dönebilir.
        cands = extract_esas_no_candidates("2022/3 sayılı genelge uyarınca")
        assert all(c["confidence"] == "low" for c in cands)

    def test_bare_number_is_low_confidence(self):
        # Eski davranış: çıplak YYYY/N very_high idi
        cands = extract_esas_no_candidates("Dosyanız 2023/999 hakkında bilgi")
        assert cands
        assert all(c["confidence"] == "low" for c in cands)

    def test_bare_number_still_returned_as_fallback(self):
        # Recall korunur: başka aday yoksa çıplak sayı yine döner
        assert find_best_esas_no("Dosyanız 2023/999 hakkında bilgi") == "2023/999"

    @pytest.mark.parametrize(
        "text",
        [
            "Esas No: 1980/5",   # yıl alt sınırın altında
            "Esas No: 2036/5",   # yıl üst sınırın üstünde
            "Esas No: 6100/119", # kanun maddesi görünümü
        ],
    )
    def test_year_range_filter(self, text):
        assert find_best_esas_no(text) is None


# ── Genel davranış ───────────────────────────────────────────────────────────

class TestGeneral:
    def test_empty_text(self):
        assert find_best_esas_no("") is None
        assert extract_esas_no_candidates("") == []

    def test_no_numbers(self):
        assert find_best_esas_no("Bu metinde numara yok.") is None

    def test_first_of_highest_confidence_wins(self):
        text = "Esas No: 2023/145 ... başka dosya Esas No: 2024/8"
        assert find_best_esas_no(text) == "2023/145"

    def test_lowercase_input(self):
        # turkish_upper normalizasyonu: küçük harfli metin de çalışmalı
        assert find_best_esas_no("esas no: 2023/145") == "2023/145"

    def test_multiline_spacing(self):
        text = "ESAS\nNO\n:\n2023/145"
        assert find_best_esas_no(text) == "2023/145"
