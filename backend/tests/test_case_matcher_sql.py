"""case_matcher SQL ön filtresi — GERÇEK Postgres'e karşı (G054).

`tests/test_case_matcher.py` skorlamayı DB'siz kilitler; bu dosya tamamlayıcısıdır:
aday daraltma SQL'e taşındığı için "SQL normalizasyonu Python `_normalize` ile
aynı mı" sorusunun cevabı ancak gerçek veritabanında ölçülebilir.

Neden gerekli: ön filtre `find_matching_case`in geniş `except`i altında koşuyor —
SQL'deki bir yazım hatası istisnaya, istisna `None`a, `None` da SESSİZ eşleşme
kaybına dönerdi. Bu testler o yolu açıkça sürer.

Bağlantı `DATABASE_URL`den okunur, salt-okunur sorgular koşar (DDL/DML YOK).
DB'ye ulaşılamıyorsa testler SKIP olur, FAIL değil — konteynersiz saf birim
koşusu yeşil kalmalı.

Marker: `dbtest` (pyproject.toml'da kayıtlı); dışlamak için `-m "not dbtest"`.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import case_matcher
from case_matcher import (
    _SQL_ALPHABET_RE,
    _SQL_FOLD_FROM,
    _SQL_FOLD_TO,
    _SQL_UNMODELLED_CHARS,
    _fetch_candidate_parties,
    _fetch_case_rows,
    _normalize,
)

pytestmark = pytest.mark.dbtest

# `case_matcher` yorumundaki izinli aralıklar — testin kendi bağımsız kaynağı
# (üretim sabitinden türetilseydi kendini onaylayan bir test olurdu).
_ALLOWED = [chr(c) for c in list(range(0x20, 0x180)) + list(range(0x300, 0x370))]
_EXCEPTIONS = [chr(c) for c in (0x85, 0xA0, 0xDF, 0x149)]


@pytest.fixture(scope="module")
def conn():
    """Salt-okunur bağlantı; DB yoksa tüm modül SKIP."""
    url = os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL postgresql:// değil")

    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    # Bağlanma denemesi ile testin kendisi AYRI try bloklarında: aynı blokta
    # olsalardı başarısız bir assert de "skip"e dönüşür, kırmızı gizlenirdi.
    try:
        connection = engine.connect()
        connection.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — SQL ön filtre testi atlandı")

    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


class _Session:
    """`_fetch_*` yalnız `execute` kullanır — connection'ı olduğu gibi geçiriyoruz."""

    def __init__(self, conn):
        self.execute = conn.execute


# ── SQL katlamasının `_normalize` ile denkliği ───────────────────────────────

def test_sql_katlama_izinli_alfabede_normalize_ile_ayni(conn):
    """İzinli aralıktaki HER karakter için SQL katlaması == `_normalize`.

    Bu, ön filtrenin Türkçe kaybı üretmemesinin temel savı: `İ/ı/Ş/Ğ/Ü/Ö/Ç`
    ve birleşik işaretler dâhil tüm alfabe karakter karakter denk.
    """
    chars = [c for c in _ALLOWED if c not in _EXCEPTIONS]
    rows = conn.execute(
        text(
            "SELECT c, btrim(translate(upper(c), :f, :t))"
            " FROM unnest(CAST(:arr AS text[])) AS c"
        ),
        {"f": _SQL_FOLD_FROM, "t": _SQL_FOLD_TO, "arr": chars},
    ).fetchall()

    assert len(rows) == len(chars)
    mismatched = [(hex(ord(c)), got, _normalize(c)) for c, got in rows if got != _normalize(c)]
    assert mismatched == []


def test_sql_katlama_turkce_adlarda_normalize_ile_ayni(conn):
    """Türkçe harf içeren gerçek ad/mahkeme örneklerinde denklik (okunur kanıt)."""
    samples = [
        "İstanbul 5. Tüketici Mahkemesi",
        "ŞANLIURFA 2. ASLİYE HUKUK MAHKEMESİ",
        "Muğla 1. Ağır Ceza Mahkemesi",
        "Çiğdem Öztürk",
        "ışık gümüşoğlu",
        "  Şükrü ÇELİK  ",
        "Dr. Oğuzhan Çimen",
        "AXA SİGORTA A.Ş.",
        "Büyükçekmece Sağlık ve Eğitim Hizmetleri A.Ş.",
        "Ali" + chr(0x307) + " Akkuş",          # i + birleşik nokta (kayıtlarda VAR)
        "ĞÜŞÖÇİ ıiİI",
        "Zeynep Yılmaz-Öz",
    ]
    rows = conn.execute(
        text(
            "SELECT s, btrim(translate(upper(s), :f, :t))"
            " FROM unnest(CAST(:arr AS text[])) AS s"
        ),
        {"f": _SQL_FOLD_FROM, "t": _SQL_FOLD_TO, "arr": samples},
    ).fetchall()
    assert [(s, got) for s, got in rows if got != _normalize(s)] == []


def test_emule_edilemeyen_karakterler_kapiya_takilir(conn):
    """İstisnalar ve alfabe dışı karakterler ön filtreyi ATLAMALI (şüphede tut)."""
    params: dict = {}
    predicate = case_matcher._sql_unmodelled("s", params)
    rows = conn.execute(
        text(f"SELECT s, {predicate} FROM unnest(CAST(:arr AS text[])) AS s"),
        {
            **params,
            "arr": [
                "Straße",                 # U+00DF — Python upper 'SS'e açar
                "co" + chr(0x149) + "x",  # U+0149 — Python upper iki karaktere açar
                chr(0xA0) + "Ali",        # NBSP — Python strip kırpar, btrim kırpmaz
                chr(0x85) + "Veli",       # NEL — aynı gerekçe
                "Ali" + chr(0x4E00),      # alfabe dışı (CJK)
                "Ali" + chr(0x410),       # alfabe dışı (Kiril)
            ],
        },
    ).fetchall()
    assert [s for s, flagged in rows if not flagged] == []


def test_alfabedeki_karakterler_kapiya_takilmaz(conn):
    """Normal Türkçe metin kapıya takılmamalı — yoksa filtre hiçbir şeyi elemez."""
    params: dict = {}
    predicate = case_matcher._sql_unmodelled("s", params)
    rows = conn.execute(
        text(f"SELECT s, {predicate} FROM unnest(CAST(:arr AS text[])) AS s"),
        {**params, "arr": ["Ali Veli", "İstanbul 5. Tüketici Mahkemesi", "Ali" + chr(0x307) + " Akkuş"]},
    ).fetchall()
    assert [s for s, flagged in rows if flagged] == []


# ── Ön filtrenin gerçek veriyi kaçırmaması ───────────────────────────────────

def test_on_filtre_gercek_taraf_adlarini_getirir(conn):
    """DB'deki gerçek taraf adlarıyla sorulunca kendi davası ön filtreden geçmeli."""
    rows = conn.execute(text(
        "SELECT case_id, name FROM case_parties"
        " WHERE length(name) >= 6 ORDER BY id LIMIT 40"
    )).fetchall()
    if not rows:
        pytest.skip("case_parties boş")

    session = _Session(conn)
    for case_id, name in rows:
        found = _fetch_candidate_parties(session, [_normalize(name)])
        assert case_id in found, f"ön filtre kaçırdı: {name!r} (dava {case_id})"


def test_on_filtre_gercek_esas_ve_mahkemeyi_getirir(conn):
    """Gerçek esas no + mahkeme ile sorulunca dava aday listesinde olmalı."""
    rows = conn.execute(text(
        "SELECT id, esas_no, court FROM cases WHERE active IS TRUE"
        " AND coalesce(esas_no,'') <> '' AND coalesce(court,'') <> ''"
        " ORDER BY id LIMIT 25"
    )).fetchall()
    if not rows:
        pytest.skip("uygun dava kaydı yok")

    session = _Session(conn)
    for case_id, esas_no, court in rows:
        ids = {r["id"] for r in _fetch_case_rows(session, [], esas_no, None, narrow=True)}
        assert case_id in ids, f"esas no ön filtresi kaçırdı: {esas_no!r}"
        ids = {r["id"] for r in _fetch_case_rows(session, [], None, court, narrow=True)}
        assert case_id in ids, f"mahkeme ön filtresi kaçırdı: {court!r}"


def test_daraltma_kapali_iken_tum_aktif_davalar_gelir(conn):
    """`narrow=False` (min_score ≤ 0) daraltmayı kapatır — eski davranışın aynısı."""
    total = conn.execute(text("SELECT count(*) FROM cases WHERE active IS TRUE")).scalar()
    rows = _fetch_case_rows(_Session(conn), [], None, None, narrow=False)
    assert len(rows) == total


def test_find_matching_case_gercek_db_uzerinde_bulur(conn):
    """Uçtan uca: gerçek bir davanın esas no + mahkemesi HIGH güvenle bulunmalı.

    `find_matching_case` geniş bir `except` altında koştuğu için SQL hatası
    sessizce `None` üretir; bu test o sessizliği kırar.
    """
    row = conn.execute(text(
        "SELECT id, esas_no, court FROM cases WHERE active IS TRUE"
        " AND coalesce(esas_no,'') <> '' AND coalesce(court,'') <> ''"
        " ORDER BY id LIMIT 1"
    )).fetchone()
    if row is None:
        pytest.skip("uygun dava kaydı yok")

    case_id, esas_no, court = row
    best = case_matcher.find_matching_case(esas_no=esas_no, mahkeme=court)
    assert best is not None
    ids = [best["case_id"]] + [c["case_id"] for c in best["all_candidates"]]
    assert case_id in ids
    assert best["score"] >= 50


def test_sabitler_beklenen_kod_noktalarini_tasir():
    """Görünmez karakterli sabitler kodlama kazasına karşı kilitli (DB gerekmez)."""
    assert [ord(c) for c in _SQL_UNMODELLED_CHARS] == [0x85, 0xA0, 0xDF, 0x149]
    assert [ord(c) for c in _SQL_ALPHABET_RE] == [
        ord("["), ord("^"), 0x20, ord("-"), 0x17F, 0x300, ord("-"), 0x36F, ord("]")
    ]
    assert _SQL_FOLD_FROM == "İĞÜŞÖÇ"
    assert _SQL_FOLD_TO == "IGUSOC"
    assert len(_SQL_FOLD_FROM) == len(_SQL_FOLD_TO)
