"""lawyer_resolver testleri — isim normalize + alias çözümleme (plan 2.1/2).

DynamicConfig monkeypatch'lenir; DB'ye dokunulmaz.
"""
import types

import pytest

from managers import lawyer_resolver
from managers.lawyer_resolver import (
    _norm_name,
    _resolve_lawyer_aliases,
    _split_persons,
    _value_matches,
    canonicalize_lawyers,
    resolve_lawyer,
    resolve_lawyers_field,
)

# Soyad dağılımı bilinçli: "hanyaloglu" ve "turgal" benzersiz, "yanik" iki kez
LAWYERS = [
    {"code": "AGH", "name": "Ayşe Gül Hanyaloğlu"},
    {"code": "STL", "name": "Serap Turgal"},
    {"code": "TUY", "name": "Tuğçe Üngör Yanık"},
    {"code": "MYK", "name": "Mehmet Yanık"},
]


class _FakeConfig:
    def __init__(self, lawyers):
        self._lawyers = lawyers

    def get_lawyers(self):
        return self._lawyers


@pytest.fixture
def with_lawyers(monkeypatch):
    """Config'e istenen avukat listesini enjekte eder."""

    def _install(lawyers=LAWYERS):
        fake = types.SimpleNamespace(get_instance=lambda: _FakeConfig(lawyers))
        monkeypatch.setattr(lawyer_resolver, "DynamicConfig", fake)

    return _install


# ── _norm_name ───────────────────────────────────────────────────────────────

class TestNormName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Av. Serap TURGAL", "serap turgal"),          # ünvan + büyük harf
            ("Tuğçe ÜNGÖR", "tugce ungor"),                # Türkçe katlama
            ("Stj. Av. Ali Veli", "ali veli"),             # çoklu ünvan
            ("Serap-Turgal", "serap turgal"),              # noktalama
            ("  Mehmet   Yanık  ", "mehmet yanik"),        # boşluk sadeleşir
            ("", ""),
            (None, ""),
        ],
    )
    def test_variants(self, raw, expected):
        assert _norm_name(raw) == expected


# ── _split_persons ───────────────────────────────────────────────────────────

class TestSplitPersons:
    def test_all_separators(self):
        parts = _split_persons("A Bc, D Ef ve G Hı / J K & L M; N O")
        assert len(parts) == 6

    def test_ve_case_insensitive(self):
        assert len(_split_persons("Ali Veli VE Ayşe Can")) == 2

    def test_single_person_no_split(self):
        assert _split_persons("Serap Turgal") == ["Serap Turgal"]

    def test_empty(self):
        assert _split_persons("") == []
        assert _split_persons(None) == []


# ── resolve_lawyer ───────────────────────────────────────────────────────────

class TestResolveLawyer:
    def test_code_match(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("AGH")["code"] == "AGH"

    def test_code_match_lowercase(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("agh")["code"] == "AGH"

    def test_two_tokens_ascii_uppercase(self, with_lawyers):
        # Tutarsız kayıt formatı: ASCII'ye katlanmış büyük harf
        with_lawyers()
        assert resolve_lawyer("TUGCE UNGOR")["code"] == "TUY"

    def test_full_name_with_title(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("Av. Serap Turgal")["code"] == "STL"

    def test_unique_surname_single_token(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("Hanyaloğlu")["code"] == "AGH"

    def test_ambiguous_surname_single_token_returns_none(self, with_lawyers):
        # "Yanık" iki avukatta var → tek token güvenle çözülemez
        with_lawyers()
        assert resolve_lawyer("Yanık") is None

    def test_single_common_token_not_enough(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("Serap Demir") is None

    def test_unknown_name(self, with_lawyers):
        with_lawyers()
        assert resolve_lawyer("John Doe") is None

    @pytest.mark.parametrize("raw", ["", None, "   "])
    def test_empty_input(self, raw, with_lawyers):
        with_lawyers()
        assert resolve_lawyer(raw) is None

    def test_empty_config_and_db_returns_none(self, with_lawyers, monkeypatch):
        with_lawyers([])
        monkeypatch.setattr(lawyer_resolver, "get_lawyers", lambda: [])
        assert resolve_lawyer("Serap Turgal") is None


# ── resolve_lawyers_field ────────────────────────────────────────────────────

class TestResolveLawyersField:
    def test_mixed_field(self, with_lawyers):
        with_lawyers()
        out = resolve_lawyers_field("Av. Serap Turgal, TUGCE UNGOR ve John Doe")
        assert len(out) == 3
        assert out[0][0]["code"] == "STL"
        assert out[1][0]["code"] == "TUY"
        assert out[2][0] is None
        assert out[2][1] == "John Doe"

    def test_duplicates_deduped(self, with_lawyers):
        # Kod ve tam ad aynı avukata çözülür → tek kayıt
        with_lawyers()
        out = resolve_lawyers_field("AGH ve Ayşe Gül Hanyaloğlu")
        assert len(out) == 1
        assert out[0][0]["code"] == "AGH"


# ── _resolve_lawyer_aliases + _value_matches ─────────────────────────────────

class TestAliasesAndValueMatches:
    def test_resolve_by_code(self, with_lawyers):
        with_lawyers()
        core, code, surname, unique = _resolve_lawyer_aliases("AGH")
        assert code == "agh"
        assert surname == "hanyaloglu"
        assert unique is True
        assert core == {"ayse", "gul", "hanyaloglu"}

    def test_resolve_by_name_nonunique_surname(self, with_lawyers):
        with_lawyers()
        _, _, surname, unique = _resolve_lawyer_aliases("Mehmet Yanık")
        assert surname == "yanik"
        assert unique is False

    def test_unresolvable_returns_none(self, with_lawyers):
        with_lawyers()
        assert _resolve_lawyer_aliases("Bilinmeyen Kişi") is None

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("Ayşe Hanyaloğlu", True),       # 2 ortak token
            ("AGH", True),                    # kod
            ("Hanyaloğlu", True),             # benzersiz soyad
            ("Mehmet Öz", False),
            ("Ayşe Demir, Veli Can", False),  # tek ortak token yetmez
            ("Veli Can ve Ayşe Gül Hanyaloğlu", True),  # çoklu alanda ikinci kişi
        ],
    )
    def test_value_matches(self, value, expected, with_lawyers):
        with_lawyers()
        core, code, surname, unique = _resolve_lawyer_aliases("AGH")
        assert _value_matches(value, core, code, surname, unique) is expected


# ── canonicalize_lawyers ─────────────────────────────────────────────────────

class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def first(self):
        return None  # Lawyer tablosunda FK satırı yok → lawyer_id None kalır


class _FakeDb:
    def query(self, *a, **k):
        return _FakeQuery()


class TestCanonicalizeLawyers:
    def test_structural_input_canonicalized(self, with_lawyers):
        with_lawyers()
        rows, canonical, unresolved = canonicalize_lawyers(
            _FakeDb(),
            [{"name": "TUGCE UNGOR"}, {"name": "John Doe"}],
            None,
        )
        assert [r["name"] for r in rows] == ["Tuğçe Üngör Yanık", "John Doe"]
        assert canonical == "Tuğçe Üngör Yanık, John Doe"
        assert unresolved == ["John Doe"]

    def test_free_text_fallback(self, with_lawyers):
        with_lawyers()
        rows, canonical, unresolved = canonicalize_lawyers(
            _FakeDb(), None, "Av. Serap Turgal ve AGH"
        )
        assert [r["name"] for r in rows] == ["Serap Turgal", "Ayşe Gül Hanyaloğlu"]
        assert unresolved == []

    def test_duplicate_canonical_names_collapse(self, with_lawyers):
        with_lawyers()
        rows, canonical, _ = canonicalize_lawyers(
            _FakeDb(), [{"name": "AGH"}, {"name": "Ayşe Gül Hanyaloğlu"}], None
        )
        assert len(rows) == 1
        assert canonical == "Ayşe Gül Hanyaloğlu"

    def test_empty_input(self, with_lawyers):
        with_lawyers()
        rows, canonical, unresolved = canonicalize_lawyers(_FakeDb(), None, None)
        assert rows == []
        assert canonical is None
        assert unresolved == []
