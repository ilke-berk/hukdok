"""case_matcher testleri — eşleştirme skorları (plan 2.1/3).

Saf skorlayıcılar doğrudan; find_matching_case ise DB katmanı (`_fetch_*`)
monkeypatch'lenerek sahte dava anlık görüntüleriyle test edilir.

Sahte yükleyiciler bilinçli olarak DARALTMA YAPMAZ (bütün davaları, bütün
taraflarıyla döndürür). Böylece testler yalnız skorlamayı ölçmekle kalmaz,
G054'ün güvenlik savını da kilitler: skorlama SQL ön filtresine BAĞIMLI
olmamalı — eşleşmeyen taraf sonucu değiştirmemeli. SQL'in kendisi gerçek
Postgres'e karşı `tests/test_case_matcher_sql.py` ile ölçülür.
"""
from types import SimpleNamespace

import pytest

import case_matcher
import database
from case_matcher import (
    _court_similarity,
    _esas_no_similarity,
    _normalize,
    _score_cases,
    find_matching_case,
)


# ── _normalize ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("İstanbul Tüketici Mahkemesi", "ISTANBUL TUKETICI MAHKEMESI"),
        ("ğüşöçİ", "GUSOCI"),
        ("  boşluklu  ", "BOSLUKLU"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize(raw, expected):
    assert _normalize(raw) == expected


# ── _esas_no_similarity ──────────────────────────────────────────────────────

class TestEsasNoSimilarity:
    @pytest.mark.parametrize(
        "doc,case",
        [
            ("2024/1234", "2024/1234"),
            ("2024/1234", "2024/001234"),   # sıfır dolgu farkı
            ("2024/001234", "2024/1234"),
            ("2024 / 1234", "2024/1234"),   # boşluk toleransı
            ("2024-1234", "2024/1234"),     # ayraç farkı
        ],
    )
    def test_matches_score_50(self, doc, case):
        assert _esas_no_similarity(doc, case) == 50

    @pytest.mark.parametrize(
        "doc,case",
        [
            ("2024/1234", "2024/12345"),    # kısmi eşleşme YOK
            ("2023/1234", "2024/1234"),     # yıl farklı
            ("", "2024/1234"),
            (None, "2024/1234"),
            ("2024/1234", ""),
        ],
    )
    def test_non_matches_score_0(self, doc, case):
        assert _esas_no_similarity(doc, case) == 0


# ── _court_similarity ────────────────────────────────────────────────────────

class TestCourtSimilarity:
    def test_exact_match_50(self):
        score, reason = _court_similarity(
            "İstanbul 5. Tüketici Mahkemesi", "ISTANBUL 5. TÜKETİCİ MAHKEMESİ"
        )
        assert score == 50
        assert "+50" in reason

    def test_city_and_type_match_25(self):
        # Numara farklı ama şehir + tür aynı
        score, _ = _court_similarity(
            "İstanbul 5. Tüketici Mahkemesi", "İstanbul 3. Tüketici Mahkemesi"
        )
        assert score == 25

    def test_different_city_0(self):
        score, _ = _court_similarity(
            "Ankara 5. Tüketici Mahkemesi", "İstanbul 5. Tüketici Mahkemesi"
        )
        # Şehir eşleşmedi (tam eşleşme de yok) → 0
        assert score == 0

    def test_same_city_different_type_0(self):
        score, _ = _court_similarity(
            "İstanbul 2. Ağır Ceza Mahkemesi", "İstanbul 2. Tüketici Mahkemesi"
        )
        # "AGIR"+"CEZA" ile "TUKETICI" kesişmez → tür eşleşmesi yok.
        assert score == 0

    @pytest.mark.parametrize("doc,case", [("", "X"), (None, "X"), ("X", None)])
    def test_empty_inputs_0(self, doc, case):
        score, reason = _court_similarity(doc, case)
        assert score == 0
        assert reason == ""


# ── find_matching_case (sahte DB ile uçtan uca skorlama) ─────────────────────

class _FakeSession:
    """Sorguları sahte yükleyiciler karşılıyor — oturumun tek işi kapanmak."""

    def close(self):
        pass


def _party(name, party_type="CLIENT"):
    return SimpleNamespace(name=name, role="", party_type=party_type)


def _case(id, esas_no, court, parties, tracking_no="TRK", status="Açık"):
    return SimpleNamespace(
        id=id,
        tracking_no=tracking_no,
        esas_no=esas_no,
        court=court,
        responsible_lawyer_name="Av. Test",
        status=status,
        active=True,
        parties=parties,
    )


def _party_row(p):
    return {"name": p.name, "role": p.role, "party_type": p.party_type}


@pytest.fixture
def with_cases(monkeypatch):
    """case_matcher'ın üç DB yükleyicisini bellek içi sahtelerle değiştirir."""

    def _install(cases):
        def _parties(db, doc_names_norm):
            return {c.id: [_party_row(p) for p in c.parties] for c in cases if c.parties}

        def _case_rows(db, party_case_ids, esas_no, mahkeme, narrow):
            return [
                {"id": c.id, "esas_no": c.esas_no or "", "court": c.court or ""}
                for c in cases
            ]

        def _display(db, case_ids):
            wanted = set(case_ids)
            info = {
                c.id: {
                    "tracking_no": c.tracking_no,
                    "responsible_lawyer_name": c.responsible_lawyer_name or "",
                    "status": c.status or "",
                }
                for c in cases
                if c.id in wanted
            }
            parties = {c.id: [_party_row(p) for p in c.parties] for c in cases if c.id in wanted}
            return info, parties

        monkeypatch.setattr(case_matcher, "_fetch_candidate_parties", _parties)
        monkeypatch.setattr(case_matcher, "_fetch_case_rows", _case_rows)
        monkeypatch.setattr(case_matcher, "_fetch_display", _display)
        monkeypatch.setattr(database, "SessionLocal", _FakeSession)

    return _install


class TestFindMatchingCase:
    def test_esas_and_court_exact_is_high(self, with_cases):
        with_cases([
            _case(1, "2024/123", "İstanbul 5. Tüketici Mahkemesi", [_party("Ali Veli")]),
        ])
        best = find_matching_case(
            esas_no="2024/123", mahkeme="İstanbul 5. Tüketici Mahkemesi"
        )
        assert best["case_id"] == 1
        assert best["score"] == 100
        assert best["confidence"] == "HIGH"

    def test_client_exact_plus_partial_court_is_medium(self, with_cases):
        with_cases([
            _case(1, "2024/999", "İstanbul 3. Tüketici Mahkemesi", [_party("Ali Veli")]),
        ])
        best = find_matching_case(
            muvekkiller=["Ali Veli"], mahkeme="İstanbul 5. Tüketici Mahkemesi"
        )
        # müvekkil tam +30, şehir+tür +25 = 55
        assert best["score"] == 55
        assert best["confidence"] == "MEDIUM"

    def test_below_min_score_returns_none(self, with_cases):
        with_cases([
            _case(1, "2024/999", "Ankara 1. İş Mahkemesi", [_party("Ali Veli")]),
        ])
        # Yalnızca müvekkil tam eşleşmesi = 30 < min_score(40)
        assert find_matching_case(muvekkiller=["Ali Veli"]) is None

    def test_min_score_override(self, with_cases):
        with_cases([
            _case(1, "2024/999", "Ankara 1. İş Mahkemesi", [_party("Ali Veli")]),
        ])
        best = find_matching_case(muvekkiller=["Ali Veli"], min_score=20)
        assert best["score"] == 30

    def test_counter_party_is_weak_signal(self, with_cases):
        with_cases([
            _case(1, "2024/1", "X", [
                _party("Ali Veli", "CLIENT"),
                _party("Zeta Sigorta AŞ", "COUNTER"),
            ]),
        ])
        best = find_matching_case(
            muvekkiller=["Ali Veli"],
            belgede_gecen_isimler=["Zeta Sigorta AŞ"],
            min_score=20,
        )
        # müvekkil tam +30, karşı taraf tam +12 = 42
        assert best["score"] == 42
        assert "Karşı taraf" in " ".join(best["match_reasons"])

    def test_short_names_ignored(self, with_cases):
        with_cases([_case(1, "2024/1", "X", [_party("Ali")])])
        # 4 karakterden kısa adaylar taramaya girmez
        assert find_matching_case(muvekkiller=["Ali"]) is None

    def test_candidates_sorted_best_first(self, with_cases):
        with_cases([
            _case(1, "2024/111", "İstanbul 1. Tüketici Mahkemesi", [_party("Ali Veli")]),
            _case(2, "2024/222", "İstanbul 1. Tüketici Mahkemesi", [_party("Ali Veli")]),
        ])
        best = find_matching_case(
            esas_no="2024/222",
            muvekkiller=["Ali Veli"],
            mahkeme="İstanbul 1. Tüketici Mahkemesi",
        )
        assert best["case_id"] == 2
        assert best["confidence"] == "HIGH"
        # Diğer aday listede, best kendisi listede değil
        assert [c["case_id"] for c in best["all_candidates"]] == [1]

    def test_empty_db_returns_none(self, with_cases):
        with_cases([])
        assert find_matching_case(esas_no="2024/1") is None

    def test_partial_name_match(self, with_cases):
        with_cases([
            _case(1, "2024/1", "X", [_party("Mehmet Ali Yılmaz")]),
        ])
        best = find_matching_case(
            muvekkiller=["Mehmet Ali Yılmaz Mirasçıları"], min_score=10
        )
        # Kısmi eşleşme (içerme, iki taraf da ≥6 karakter) → +15
        assert best["score"] == 15


# ── Aday daraltmanın güvenlik savı (G054) ────────────────────────────────────

_COURT = "İstanbul 5. Tüketici Mahkemesi"


def _row(name, party_type="CLIENT"):
    return {"name": name, "role": "", "party_type": party_type}


class TestOnFiltreGuvenligi:
    """SQL ön filtresi eşleşmeyen tarafları çekmiyor — skorlama etkilenmemeli."""

    @pytest.mark.parametrize(
        "doc_names",
        [
            ["Ali Veli"],                    # tam eşleşme
            ["Ali Veli Mirasçıları"],        # kısmi eşleşme (içerme)
            ["Bulunmayan Kişi"],             # hiç eşleşme yok
        ],
    )
    def test_eslesmeyen_taraflar_skoru_degistirmez(self, doc_names):
        case_rows = [{"id": 1, "esas_no": "2024/1", "court": _COURT}]
        matching = _row("Ali Veli")
        full = {1: [_row("Zeta Sigorta AŞ", "COUNTER"), matching, _row("Hasan Kaya", "THIRD")]}
        narrowed = {1: [matching]}

        args = (doc_names, None, _COURT, 10)
        assert _score_cases(case_rows, full, *args) == _score_cases(case_rows, narrowed, *args)

    def test_ayni_adli_iki_taraftan_ILKI_puanlanir(self):
        """Puan taraf SIRASINA bağlı (`break`) — ön filtre sırayı korumalı.

        İki taraf aynı ada normalize oluyorsa yalnız ilki puanlanır; müvekkil
        (+30) ile karşı taraf (+12) arasındaki fark buna bağlıdır. Bu yüzden
        `_fetch_candidate_parties` satırları `case_parties.id` ile sıralar.
        """
        case_rows = [{"id": 1, "esas_no": "", "court": ""}]
        client_first = {1: [_row("Ali Veli", "CLIENT"), _row("ALİ VELİ", "COUNTER")]}
        counter_first = {1: [_row("ALİ VELİ", "COUNTER"), _row("Ali Veli", "CLIENT")]}

        args = (["Ali Veli"], None, None, 1)
        assert _score_cases(case_rows, client_first, *args)[0]["score"] == 30
        assert _score_cases(case_rows, counter_first, *args)[0]["score"] == 12

    def test_taraf_bilgisi_olmayan_dava_skorlanabilir(self):
        """Ön filtre hiç taraf getirmese de esas/mahkeme puanı üretilebilmeli."""
        case_rows = [{"id": 7, "esas_no": "2024/123", "court": _COURT}]
        candidates = _score_cases(case_rows, {}, [], "2024/123", _COURT, 40)
        assert [c["case_id"] for c in candidates] == [7]
        assert candidates[0]["score"] == 100
