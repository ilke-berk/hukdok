"""Mükerrer dava kontrolü — esas no/mahkeme normalize eşleşme testleri.

find_duplicate_cases DB'ye bağımlı; burada onun dayandığı saf karşılaştırma
fonksiyonları (case_matcher) kilitlenir. Route testi test_required_fields'ta.
"""
from case_matcher import _court_similarity, _esas_no_similarity


def test_esas_no_exact_match():
    assert _esas_no_similarity("2024/123", "2024/123") == 50


def test_esas_no_whitespace_tolerant():
    assert _esas_no_similarity("2024/123", "2024 / 123") == 50


def test_esas_no_zero_padding_tolerant():
    assert _esas_no_similarity("2024/123", "2024/000123") == 50


def test_esas_no_different_number_no_match():
    assert _esas_no_similarity("2024/123", "2024/124") == 0


def test_esas_no_different_year_no_match():
    assert _esas_no_similarity("2023/123", "2024/123") == 0


def test_esas_no_empty_no_match():
    assert _esas_no_similarity("", "2024/123") == 0
    assert _esas_no_similarity("2024/123", "") == 0


def test_court_exact_match_turkish_normalized():
    score, _ = _court_similarity(
        "İSTANBUL 5. TÜKETİCİ MAHKEMESİ", "ISTANBUL 5. TUKETICI MAHKEMESI"
    )
    assert score == 50


def test_court_city_and_type_match_different_number():
    score, _ = _court_similarity(
        "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "ANKARA 7. ASLİYE HUKUK MAHKEMESİ"
    )
    assert score == 25


def test_court_different_city_no_match():
    score, _ = _court_similarity(
        "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "İZMİR 3. ASLİYE HUKUK MAHKEMESİ"
    )
    assert score == 0
