"""date_extractor testleri — tarih adayı skorlama (plan 2.1/4).

LLM hakemi (ask_llm_referee) monkeypatch'lenir; Gemini'ye asla çıkılmaz.
conftest'teki vault stub'ı sayesinde import ağ/keyring'e dokunmaz.
"""

import pytest

import extractors.date_extractor as de
from extractors.date_extractor import advanced_regex_scan, find_best_date


def _dates_of(candidates):
    return {c.date_str for c in candidates}


# ── advanced_regex_scan ──────────────────────────────────────────────────────

class TestAdvancedRegexScan:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Belge 15.01.2024 tarihinde imzalandı.", "15.01.2024"),
            ("Belge 15/01/2024 tarihinde imzalandı.", "15.01.2024"),
            ("Belge 15-01-2024 tarihinde imzalandı.", "15.01.2024"),
            ("Belge 5.1.2024 tarihinde imzalandı.", "05.01.2024"),  # tek haneli
            ("Duruşma 15 Ocak 2024 günü yapıldı.", "15.01.2024"),   # yazılı ay
            ("Karar 3 Eylül 2023 tarihlidir.", "03.09.2023"),
        ],
    )
    def test_formats(self, text, expected):
        assert expected in _dates_of(advanced_regex_scan(text))

    def test_future_dates_filtered(self):
        assert advanced_regex_scan("Vade 31.12.2099 tarihidir.") == []

    def test_invalid_day_skipped(self):
        assert advanced_regex_scan("Hatalı 32.01.2024 değeri.") == []

    def test_pre_1990_skipped(self):
        assert advanced_regex_scan("Doğum 15.01.1980 tarihi.") == []

    def test_recency_boost_and_age_penalty(self):
        text = "İlk 10.01.2019 sonra 10.01.2023 ve son 10.01.2024 tarihleri."
        cands = {c.date_str: c for c in advanced_regex_scan(text)}
        # En yeni 2 tarih +25 alır; 2023 ayrıca 1 yıl farkla -5 yer
        assert cands["10.01.2024"].recency_score == 25
        assert cands["10.01.2023"].recency_score == 20
        # 2019 top-2 dışında, 5 yıl fark → -25
        assert cands["10.01.2019"].recency_score == -25

    def test_decision_keyword_outscores_plain_date(self):
        text = (
            "Tebliğ tarihi 10.01.2024 olarak kaydedilmiştir. "
            + "dolgu " * 100
            + "Oy birliğiyle karar verildi 12.02.2024."
        )
        cands = sorted(advanced_regex_scan(text), key=lambda c: c.final_score, reverse=True)
        assert cands[0].date_str == "12.02.2024"

    def test_negative_keywords_penalized(self):
        text = "Sözleşme 15.03.2024 tarihinde imzalandı. Vade tarihi 20.03.2024 idi."
        cands = {c.date_str: c for c in advanced_regex_scan(text)}
        assert cands["15.03.2024"].final_score > cands["20.03.2024"].final_score

    def test_empty_text(self):
        assert advanced_regex_scan("") == []

    @pytest.mark.parametrize(
        "text",
        [
            "Taksitle 5 ay 2020 ödendi.",       # "AY" ⊂ "MAYIS" yanlış pozitifi
            "Bkz. 5 EK 2023 sayılı belge.",     # "EK" ⊂ "EKİM" yanlış pozitifi
            "Toplam 3 mart? hayır 3 marti 2022", # "MARTI" ⊅ ay (ters yön)
        ],
    )
    def test_month_substring_false_positives_rejected(self, text):
        assert advanced_regex_scan(text) == []

    def test_month_prefix_abbreviation_accepted(self):
        # ≥3 harfli önek kısaltması geçerli sayılır ("Oca" → Ocak)
        assert "15.01.2024" in _dates_of(advanced_regex_scan("Belge 15 Oca 2024 tarihli."))


# ── find_best_date ───────────────────────────────────────────────────────────

class TestFindBestDate:
    def test_empty_text_returns_none(self):
        # Tarih uydurulmaz (eski davranış: bugünün tarihi) — LLM'e devredilir
        assert find_best_date("") is None

    def test_no_candidates_returns_none(self):
        assert find_best_date("Tarihsiz bir metin.") is None

    def test_confident_single_candidate_skips_llm(self, monkeypatch):
        def _fail(*a, **k):
            raise AssertionError("Güvenli adayda LLM hakemi çağrılmamalı")

        monkeypatch.setattr(de, "ask_llm_referee", _fail)
        # Belge sonunda (pozisyon +40) + "imza"/"tarih" bağlamı → skor ≥50
        text = "dolgu " * 200 + "imza tarihi: 15.01.2024"
        assert find_best_date(text) == "2024-01-15"

    def test_ambiguous_calls_llm_and_uses_json_answer(self, monkeypatch):
        monkeypatch.setattr(
            de,
            "ask_llm_referee",
            lambda text, cands: '{"selected_date": "2023-05-10", "reasoning": "test"}',
        )
        # İki eş güçlü aday (aynı bağlam + benzer pozisyon) → fark <20 → hakem devreye girer
        text = "tarih 10.05.2023 ve tarih 11.05.2023 " + "dolgu " * 50
        assert find_best_date(text) == "2023-05-10"

    def test_llm_bare_date_string_accepted(self, monkeypatch):
        # JSON değil düz tarih dönerse ISO regex fallback'i yakalar
        monkeypatch.setattr(de, "ask_llm_referee", lambda text, cands: "2023-05-11")
        text = "tarih 10.05.2023 ve tarih 11.05.2023 " + "dolgu " * 50
        assert find_best_date(text) == "2023-05-11"

    def test_llm_hallucinated_date_rejected(self, monkeypatch):
        # Hakem aday listesinde OLMAYAN bir tarih uydurursa reddedilir,
        # en yüksek skorlu adaya düşülür
        monkeypatch.setattr(
            de,
            "ask_llm_referee",
            lambda text, cands: '{"selected_date": "1999-12-31", "reasoning": "uydurma"}',
        )
        text = "tarih 10.05.2023 ve tarih 11.05.2023 " + "dolgu " * 50
        assert find_best_date(text) in {"2023-05-10", "2023-05-11"}

    def test_llm_bare_hallucinated_date_rejected(self, monkeypatch):
        # Düz string dönüşünde de aday doğrulaması uygulanır
        monkeypatch.setattr(de, "ask_llm_referee", lambda text, cands: "1999-12-31")
        text = "tarih 10.05.2023 ve tarih 11.05.2023 " + "dolgu " * 50
        assert find_best_date(text) in {"2023-05-10", "2023-05-11"}

    def test_llm_failure_falls_back_to_top_candidate(self, monkeypatch):
        monkeypatch.setattr(de, "ask_llm_referee", lambda text, cands: None)
        text = "tarih 10.05.2023 ve tarih 11.05.2023 " + "dolgu " * 50
        result = find_best_date(text)
        # Hakem çöktü → en yüksek skorlu aday ISO formatında döner
        assert result in {"2023-05-10", "2023-05-11"}
