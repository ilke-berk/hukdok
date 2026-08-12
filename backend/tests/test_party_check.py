"""party_check (Tanıdık Sorgu / Çıkar Çatışması) birim testleri.

İlk bölüm DB'siz saf birim testleridir. Sonda G017 bölümü iki eklentiyi
kapsar: hazırlanmış aday satırları (`prepare_candidate_rows`) ve route'un
süreç-içi aday TTL cache'i (`routes/parties.py`) — cache testleri süreç içi
sqlite üzerinde GERÇEK sorgu koşar (`routes.parties.SessionLocal` yönlendirilir).
En sondaki G053 bölümü bantlı/erken çıkışlı eşik kapısını (`_levenshtein_within`)
kısayolsuz tam matris referansına karşı doğrular.
"""
from types import SimpleNamespace

import pytest

from party_check import (
    _levenshtein_within,
    check_parties,
    normalize_person_name,
    normalize_tc,
    prepare_candidate_rows,
)


def _client(id=1, name="AHMET YILMAZ", tc_no=None, contact_type="Client", **kw):
    return {
        "id": id, "name": name, "tc_no": tc_no,
        "cari_kod": kw.get("cari_kod"), "category": kw.get("category"),
        "contact_type": contact_type,
    }


def _party(case_id=100, name="AHMET YILMAZ", party_type="COUNTER", role="Davalı",
           tc_no=None, client_id=None, tracking_no="X1.AHMETYILMA.0001.DD.24"):
    return {
        "id": case_id * 10, "name": name, "tc_no": tc_no, "role": role,
        "party_type": party_type, "client_id": client_id, "case_id": case_id,
        "tracking_no": tracking_no, "case_subject": "Tazminat", "case_status": "DERDEST",
    }


def _q(name, tc_no=None, party_type="COUNTER"):
    return {"name": name, "tc_no": tc_no, "party_type": party_type}


# ── Normalizasyon ────────────────────────────────────────────────────────────

def test_normalize_turkish_upper_and_diacritics():
    assert normalize_person_name("ilker öztürk") == normalize_person_name("İLKER ÖZTÜRK")


def test_normalize_strips_doctor_title():
    assert normalize_person_name("DR. AHMET YILMAZ") == normalize_person_name("Ahmet Yılmaz")
    assert normalize_person_name("Prof. Dr. Ayşe Kaya") == normalize_person_name("AYŞE KAYA")


def test_normalize_does_not_mangle_names_starting_with_av():
    # "AVNİ" içindeki AV unvan değildir
    assert "AVNI" in normalize_person_name("Avni Yılmaz")


def test_normalize_tc():
    assert normalize_tc("12345678901") == "12345678901"
    assert normalize_tc("123 456 789 01") == "12345678901"
    assert normalize_tc("1234567890") is None      # 10 hane
    assert normalize_tc("") is None
    assert normalize_tc(None) is None


def test_match_includes_record_tc():
    # Eşleşen kaydın TC'si ekranda karşılaştırma için döner
    clients = [_client(name="AHMET YILMAZ", tc_no="12345678901")]
    res = check_parties([_q("Ahmet Yılmaz")], clients, [])
    assert res[0]["matches"][0]["tc_no"] == "12345678901"


# ── Eşleşme kademeleri ───────────────────────────────────────────────────────

def test_tc_match_is_certain_and_beats_name():
    clients = [_client(tc_no="12345678901", name="FARKLI İSİM")]
    res = check_parties([_q("Ahmet Yılmaz", tc_no="12345678901")], clients, [])
    assert len(res[0]["matches"]) == 1
    m = res[0]["matches"][0]
    assert m["matched_on"] == "tc_no"
    assert m["strength"] == "certain"
    assert m["tc_no"] == "12345678901"


def test_exact_name_match_probable_case_insensitive():
    clients = [_client(name="AHMET YILMAZ")]
    res = check_parties([_q("ahmet yılmaz")], clients, [])
    assert res[0]["matches"][0]["matched_on"] == "name_exact"
    assert res[0]["matches"][0]["strength"] == "probable"


def test_fuzzy_match_typo_in_surname():
    clients = [_client(name="AHMET YILMAZ")]
    res = check_parties([_q("Ahmet Yilmas")], clients, [])  # soyisimde 1 harf
    assert res[0]["matches"][0]["matched_on"] == "name_fuzzy"
    assert res[0]["matches"][0]["strength"] == "possible"


def test_same_first_name_different_surname_no_match():
    # "Sadece isim yetmez, soyisim de eşleşmeli" — Ali Veli ↔ Ali Beki eşleşmez
    parties = [_party(name="Ali Beki")]
    res = check_parties([_q("Ali Veli")], [], parties)
    assert res[0]["matches"] == []

    parties = [_party(name="Recep Çelik")]
    res = check_parties([_q("Recep İvedik")], [], parties)
    assert res[0]["matches"] == []

    parties = [_party(name="Abdulhamit Okşan")]
    res = check_parties([_q("Abdulhamit Soysal")], [], parties)
    assert res[0]["matches"] == []


def test_word_order_swap_is_exact():
    clients = [_client(name="SOYSAL ABDULHAMIT")]
    res = check_parties([_q("Abdulhamit Soysal")], clients, [])
    assert res[0]["matches"][0]["matched_on"] == "name_exact"


def test_combining_diacritics_normalized():
    # Bazı kayıtlarda 'i̇' (i + U+0307 birleşik nokta) var — exact eşleşmeli
    parties = [_party(name="Abdulhami̇t Soysal Dr.", party_type="THIRD", role="Diğer Davalı")]
    res = check_parties([_q("Abdulhamit Soysal", party_type="THIRD")], [], parties)
    assert res[0]["matches"][0]["matched_on"] == "name_exact"


def test_different_token_count_no_fuzzy():
    clients = [_client(name="AHMET CAN YILMAZ")]
    res = check_parties([_q("Ahmet Yilmaz")], clients, [])
    assert res[0]["matches"] == []


def test_fuzzy_beyond_threshold_no_match():
    clients = [_client(name="AHMET YILMAZ")]
    res = check_parties([_q("Mehmet Demir")], clients, [])
    assert res[0]["matches"] == []


def test_short_name_skipped():
    clients = [_client(name="ALİ")]
    res = check_parties([_q("ALİ")], clients, [])
    assert res[0]["matches"] == []


def test_corporate_names_skip_fuzzy_but_allow_exact():
    clients = [_client(name="ANADOLU SİGORTA A.Ş.")]
    exact = check_parties([_q("Anadolu Sigorta A.Ş.")], clients, [])
    assert len(exact[0]["matches"]) == 1
    fuzzy = check_parties([_q("ANADOLU SİGORTE A.Ş.")], clients, [])
    assert fuzzy[0]["matches"] == []


def test_doctor_title_matches_bare_name():
    # Başvuran hekim senaryosu: "DR. AHMET YILMAZ" ↔ "AHMET YILMAZ"
    parties = [_party(name="AHMET YILMAZ", party_type="THIRD", role="Başvuran")]
    res = check_parties([_q("Dr. Ahmet Yılmaz", party_type="THIRD")], [], parties)
    assert res[0]["matches"][0]["matched_on"] == "name_exact"


# ── Çıkar çatışması bayrağı ─────────────────────────────────────────────────

def test_counter_matching_client_record_is_conflict():
    clients = [_client(name="AHMET YILMAZ", contact_type="Client")]
    res = check_parties([_q("Ahmet Yılmaz", party_type="COUNTER")], clients, [])
    assert res[0]["conflict"] is True


def test_counter_matching_other_contact_is_not_conflict():
    clients = [_client(name="AHMET YILMAZ", contact_type="Other")]
    res = check_parties([_q("Ahmet Yılmaz", party_type="COUNTER")], clients, [])
    assert res[0]["conflict"] is False
    assert len(res[0]["matches"]) == 1


def test_client_query_with_past_counter_history_is_not_conflict():
    # Müvekkil ile çıkar çatışması olmaz (2026-08-01 kararı): taraf-değişimi
    # geçmişi bilgi olarak listelenir ama conflict bayrağı kalkmaz.
    parties = [_party(name="AHMET YILMAZ", party_type="COUNTER")]
    res = check_parties([_q("Ahmet Yılmaz", party_type="CLIENT")], [], parties)
    assert res[0]["conflict"] is False
    assert res[0]["matches"][0]["party_type"] == "COUNTER"


def test_client_query_counter_history_not_conflict_after_tc_cleanup():
    # TC temizliği sonrası conflict yeniden hesabı da CLIENT geçmişini çatışma saymaz
    parties = [_party(name="AHMET YILMAZ", party_type="COUNTER", tc_no="12345678901")]
    res = check_parties(
        [_q("Ahmet Yılmaz", tc_no="12345678901", party_type="CLIENT")], [], parties
    )
    assert res[0]["conflict"] is False
    assert res[0]["matches"][0]["matched_on"] == "tc_no"


def test_client_query_expected_client_match_suppressed():
    # CLIENT sorgusunun cari eşleşmesi ve geçmiş CLIENT görünümleri beklenir → raporlanmaz
    clients = [_client(name="AHMET YILMAZ")]
    parties = [_party(name="AHMET YILMAZ", party_type="CLIENT", role="Davacı")]
    res = check_parties([_q("Ahmet Yılmaz", party_type="CLIENT")], clients, parties)
    assert res[0]["matches"] == []
    assert res[0]["conflict"] is False


def test_client_query_tc_match_different_name_reported():
    # Aynı TC farklı isim = veri hatası → raporlanır
    clients = [_client(name="BAŞKA BİRİ", tc_no="12345678901")]
    res = check_parties([_q("Ahmet Yılmaz", tc_no="12345678901", party_type="CLIENT")], clients, [])
    assert len(res[0]["matches"]) == 1
    assert res[0]["matches"][0]["matched_on"] == "tc_no"


# ── TC ile kesinleştirme / temizleme ────────────────────────────────────────

def test_tc_mismatch_clears_name_match():
    # "Aynı isim, farklı kişi": kayıtta TC var ve sorgu TC'sinden farklı → eleme
    clients = [_client(name="AHMET YILMAZ", tc_no="99999999999")]
    res = check_parties([_q("Ahmet Yılmaz", tc_no="12345678901")], clients, [])
    assert res[0]["matches"] == []
    assert res[0]["conflict"] is False


def test_tc_given_but_record_has_no_tc_keeps_name_match():
    clients = [_client(name="AHMET YILMAZ", tc_no=None)]
    res = check_parties([_q("Ahmet Yılmaz", tc_no="12345678901")], clients, [])
    assert len(res[0]["matches"]) == 1  # kesinleştirilemez, sarı kalır


def test_invalid_tc_ignored_falls_back_to_name():
    clients = [_client(name="AHMET YILMAZ", tc_no="99999999999")]
    res = check_parties([_q("Ahmet Yılmaz", tc_no="123")], clients, [])
    assert len(res[0]["matches"]) == 1
    assert res[0]["matches"][0]["matched_on"] == "name_exact"


# ── Diğer kenar durumlar ────────────────────────────────────────────────────

def test_exclude_case_id_drops_self_match():
    parties = [_party(case_id=42, name="AHMET YILMAZ")]
    res = check_parties([_q("Ahmet Yılmaz")], [], parties, exclude_case_id=42)
    assert res[0]["matches"] == []


def test_case_party_match_includes_case_info():
    parties = [_party(case_id=7, name="AHMET YILMAZ", tracking_no="X1.TEST.0007")]
    res = check_parties([_q("Ahmet Yılmaz")], [], parties)
    m = res[0]["matches"][0]
    assert m["source"] == "case_party"
    assert m["tracking_no"] == "X1.TEST.0007"
    assert m["role"] == "Davalı"
    assert m["case_status"] == "DERDEST"


def test_multiple_queries_independent_results():
    clients = [_client(name="AHMET YILMAZ")]
    res = check_parties([_q("Ahmet Yılmaz"), _q("Zeynep Demir")], clients, [])
    assert len(res) == 2
    assert len(res[0]["matches"]) == 1
    assert res[1]["matches"] == []


def test_dedupe_case_party_rows_same_person():
    # Aynı dosyada aynı isim iki kez (veri tekrarı) → tek kayıt raporu
    parties = [
        _party(case_id=5, name="AHMET YILMAZ", role="Davalı"),
        _party(case_id=5, name="AHMET YILMAZ", role="Davalı"),
    ]
    res = check_parties([_q("Ahmet Yılmaz")], [], parties)
    assert len(res[0]["matches"]) == 1


# ── G017: hazırlanmış aday satırları ────────────────────────────────────────

# Davranış değişikliği YOK iddiasının testi: aynı senaryolar ham satırlarla ve
# prepare_candidate_rows'tan geçmiş satırlarla birebir aynı sonucu vermeli.
_PREPARE_SCENARIOS = [
    ([_client(name="AHMET YILMAZ")], [], _q("ahmet yılmaz")),
    ([_client(name="AHMET YILMAZ")], [], _q("Ahmet Yilmas")),
    ([_client(name="ANADOLU SİGORTA A.Ş.")], [], _q("Anadolu Sigorte A.Ş.")),
    ([_client(name="AHMET YILMAZ", tc_no="99999999999")], [],
     _q("Ahmet Yılmaz", tc_no="12345678901")),
    ([_client(tc_no="12345678901", name="FARKLI İSİM")], [],
     _q("Ahmet Yılmaz", tc_no="12345678901")),
    ([_client(name="AHMET YILMAZ")], [_party(name="AHMET YILMAZ", party_type="CLIENT")],
     _q("Ahmet Yılmaz", party_type="CLIENT")),
    ([], [_party(case_id=5, name="AHMET YILMAZ"), _party(case_id=5, name="Ahmet Yılmaz")],
     _q("Ahmet Yılmaz")),
    ([_client(id=3, name="AHMET YILMAZ")], [_party(case_id=8, name="AHMET YILMAZ", client_id=3)],
     _q("Ahmet Yılmaz")),
    ([], [_party(name="Ali Beki")], _q("Ali Veli")),
]


@pytest.mark.parametrize("clients,parties,query", _PREPARE_SCENARIOS)
def test_prepared_rows_give_identical_results(clients, parties, query):
    raw = check_parties([query], clients, parties)
    prepared = check_parties(
        [query], prepare_candidate_rows(clients), prepare_candidate_rows(parties)
    )
    assert prepared == raw


def test_prepared_rows_do_not_leak_internal_fields():
    # `_key`/`_tc` satır içi hazırlık alanları; yanıtta görünmemeli
    clients = prepare_candidate_rows([_client(name="AHMET YILMAZ")])
    parties = prepare_candidate_rows([_party(name="AHMET YILMAZ")])
    res = check_parties([_q("Ahmet Yılmaz")], clients, parties)
    assert res[0]["matches"]
    for m in res[0]["matches"]:
        assert [k for k in m if k.startswith("_")] == []


def test_prepare_does_not_mutate_input_rows():
    rows = [_client(name="AHMET YILMAZ")]
    snapshot = dict(rows[0])
    prepared = prepare_candidate_rows(rows)
    assert rows[0] == snapshot
    assert prepared[0]["_key"][0] == normalize_person_name("AHMET YILMAZ")
    assert prepared[0]["_tc"] is None


def test_prepare_shares_one_key_per_distinct_name():
    # Aynı isim onlarca dosyada tekrar ediyor → anahtar isim başına bir kez
    prepared = prepare_candidate_rows([
        _party(case_id=1, name="AHMET YILMAZ"),
        _party(case_id=2, name="AHMET YILMAZ"),
        _party(case_id=3, name="ZEYNEP DEMİR"),
    ])
    assert prepared[0]["_key"] is prepared[1]["_key"]
    assert prepared[2]["_key"] is not prepared[0]["_key"]


def test_normalize_person_name_is_memoized():
    normalize_person_name.cache_clear()
    first = normalize_person_name("Dr. Ahmet Yılmaz")
    hits_before = normalize_person_name.cache_info().hits
    second = normalize_person_name("Dr. Ahmet Yılmaz")
    assert first == second
    assert normalize_person_name.cache_info().hits == hits_before + 1


# ── G017: route'un aday TTL cache'i (süreç içi sqlite üzerinde) ──────────────

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"


@pytest.fixture()
def parties_db(monkeypatch):
    """Paylaşılan in-memory sqlite + `routes.parties.SessionLocal` yönlendirmesi.

    Aday cache'i süreç-globaldir → test öncesi ve sonrası sıfırlanır, yoksa bir
    testin adayları diğerine sızar.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    from routes import parties as parties_route

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(parties_route, "SessionLocal", maker)
    parties_route.reset_candidate_cache_for_tests()
    yield SimpleNamespace(sessions=maker, route=parties_route, models=models)
    parties_route.reset_candidate_cache_for_tests()
    engine.dispose()


def _seed_client(env, name, tenant_id, tc_no=None):
    db = env.sessions()
    try:
        row = env.models.Client(
            name=name, tenant_id=tenant_id, contact_type="Client", active=True, tc_no=tc_no
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _seed_case_party(env, name, tenant_id, tracking_no):
    db = env.sessions()
    try:
        case = env.models.Case(tracking_no=tracking_no, tenant_id=tenant_id, status="DERDEST")
        db.add(case)
        db.flush()
        db.add(env.models.CaseParty(
            case_id=case.id, name=name, role="Davalı", party_type="COUNTER"
        ))
        db.commit()
    finally:
        db.close()


def _names(rows):
    return {r["name"] for r in rows}


def test_candidate_rows_are_prepared_and_usable(parties_db):
    _seed_client(parties_db, "AHMET YILMAZ", T1)
    _seed_case_party(parties_db, "ZEYNEP DEMİR", T1, "X1.TEST.0001")

    clients, parties = parties_db.route._candidate_rows(T1)
    assert "_key" in clients[0] and "_tc" in clients[0]
    assert "_key" in parties[0] and "_tc" in parties[0]

    # Cache'ten gelen satırlarla çatışma tespiti çalışıyor
    res = check_parties([_q("Ahmet Yilmas", party_type="COUNTER")], clients, parties)
    assert res[0]["conflict"] is True
    assert res[0]["matches"][0]["matched_on"] == "name_fuzzy"  # soyisimde 1 harf


def test_candidate_cache_serves_repeat_request_from_memory(parties_db):
    _seed_client(parties_db, "AHMET YILMAZ", T1)
    clients, _ = parties_db.route._candidate_rows(T1)
    assert _names(clients) == {"AHMET YILMAZ"}

    # TTL içinde eklenen kayıt BİLİNÇLİ olarak görünmez (invalidasyon yok,
    # tazelik garantisi TTL'dir) — cache'in gerçekten kullanıldığının kanıtı.
    _seed_client(parties_db, "ZEYNEP DEMİR", T1)
    cached, _ = parties_db.route._candidate_rows(T1)
    assert _names(cached) == {"AHMET YILMAZ"}

    parties_db.route.reset_candidate_cache_for_tests()
    fresh, _ = parties_db.route._candidate_rows(T1)
    assert _names(fresh) == {"AHMET YILMAZ", "ZEYNEP DEMİR"}


def test_candidate_cache_key_isolates_tenants(parties_db):
    _seed_client(parties_db, "T1 MÜVEKKİLİ", T1)
    _seed_client(parties_db, "T2 MÜVEKKİLİ", T2)
    _seed_client(parties_db, "PAYLAŞILAN CARİ", None)  # legacy NULL havuz
    _seed_case_party(parties_db, "T1 KARŞI TARAF", T1, "X1.T1.0001")
    _seed_case_party(parties_db, "T2 KARŞI TARAF", T2, "X1.T2.0001")

    # Dönüşümlü sorgu: tek-girdi politikası (tenant değişince eski indeks
    # düşer) izolasyonu da tazeliği de bozmamalı.
    for _ in range(2):
        clients, parties = parties_db.route._candidate_rows(T1)
        assert _names(clients) == {"T1 MÜVEKKİLİ", "PAYLAŞILAN CARİ"}
        assert _names(parties) == {"T1 KARŞI TARAF"}

        clients, parties = parties_db.route._candidate_rows(T2)
        assert _names(clients) == {"T2 MÜVEKKİLİ", "PAYLAŞILAN CARİ"}
        assert _names(parties) == {"T2 KARŞI TARAF"}


def test_candidate_cache_expires_and_refetches(parties_db):
    # Negatif TTL: her girdi anında bayat sayılır (saat çözünürlüğüne bağlı
    # yarış olmadan süre dolumunu test eder).
    parties_db.route.reset_candidate_cache_for_tests(ttl_seconds=-1)
    _seed_client(parties_db, "AHMET YILMAZ", T1)
    assert len(parties_db.route._candidate_rows(T1)[0]) == 1

    _seed_client(parties_db, "ZEYNEP DEMİR", T1)
    assert len(parties_db.route._candidate_rows(T1)[0]) == 2


# ── G053: bantlı / erken çıkışlı eşik kapısı ────────────────────────────────

# `_levenshtein_within` tam mesafe DÖNDÜRMEZ; "mesafe ≤ eşik mi" sorusunu
# yanıtlar. Doğruluğu, tam matris referansına karşı kanıtlanır — kısayolların
# (bant, erken çıkış, eşit-uzunluk hızlı yolu) hiçbiri sonucu değiştirmemeli.


def _reference_levenshtein(a: str, b: str) -> int:
    """Kısayolsuz tam matris Levenshtein — yalnız test referansı."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i]
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[n]


def _all_strings(alphabet, max_len):
    out = [""]
    frontier = [""]
    for _ in range(max_len):
        frontier = [s + ch for s in frontier for ch in alphabet]
        out.extend(frontier)
    return out


def test_within_matches_reference_exhaustively_on_short_strings():
    # 3 harflik alfabede 0-4 uzunluktaki TÜM dizeler (121) × TÜM dizeler ×
    # kullanılan iki eşik = 29.282 karşılaştırma; tek fark bile kabul edilmez.
    strings = _all_strings("ABC", 4)
    assert len(strings) == 121
    checked = 0
    for a in strings:
        for b in strings:
            distance = _reference_levenshtein(a, b)
            for threshold in (1, 2):
                assert _levenshtein_within(a, b, threshold) is (distance <= threshold), (
                    a, b, threshold, distance
                )
                checked += 1
    assert checked == 121 * 121 * 2


def test_within_matches_reference_on_longer_perturbed_words():
    # Uzun kelimeler (eşik 2 yolu) — tohumlu üretim, deterministik.
    import random

    rnd = random.Random(53)
    alphabet = "AEIKLMNRSTUYZ"
    for _ in range(2000):
        base = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(5, 12)))
        variant = list(base)
        for _ in range(rnd.randint(0, 4)):
            pos = rnd.randrange(len(variant)) if variant else 0
            op = rnd.choice(("sub", "del", "ins"))
            if op == "sub" and variant:
                variant[pos] = rnd.choice(alphabet)
            elif op == "del" and variant:
                del variant[pos]
            else:
                variant.insert(pos, rnd.choice(alphabet))
        other = "".join(variant)
        distance = _reference_levenshtein(base, other)
        for threshold in (1, 2):
            assert _levenshtein_within(base, other, threshold) is (distance <= threshold), (
                base, other, threshold, distance
            )


@pytest.mark.parametrize("a,b,threshold,expected", [
    ("", "", 1, True),                    # iki boş dize
    ("", "A", 1, True),                   # boş ↔ tek harf: mesafe 1
    ("", "AB", 1, False),                 # boş ↔ iki harf: eşik aşıldı
    ("", "AB", 2, True),
    ("A", "A", 1, True),                  # tek karakter, birebir aynı
    ("A", "B", 1, True),
    ("A", "B", 2, True),
    ("AHMET", "AHMET", 1, True),          # birebir aynı dize (matris kurulmaz)
    ("AHMET", "AHMETLER", 1, False),      # uzunluk farkı eşikten büyük → bant yok
    ("AHMET", "AHMETLER", 2, False),
    ("YILMAZ", "YILMAS", 1, True),        # eşiğe eşit mesafe → eşik AŞILMADI
    ("YILMAZ", "YALMAS", 1, False),       # mesafe 2 > eşik 1
    ("YILMAZ", "YALMAS", 2, True),
])
def test_within_edge_cases(a, b, threshold, expected):
    assert _levenshtein_within(a, b, threshold) is expected
    assert (_reference_levenshtein(a, b) <= threshold) is expected


def test_within_equal_length_shortcut_does_not_leak_to_threshold_two():
    # Eşit uzunlukta eşik 1 için "en fazla bir harf farkı" kısayolu geçerlidir,
    # eşik 2 için DEĞİL: baştan silme + sona ekleme mesafeyi 2'de tutar ama
    # dizeler her konumda farklıdır. Kısayol eşik 2'ye sızarsa bu test kırılır.
    a, b = "ABCDEFGHIJ", "BCDEFGHIJA"
    assert _reference_levenshtein(a, b) == 2
    assert sum(x != y for x, y in zip(a, b, strict=True)) == 10
    assert _levenshtein_within(a, b, 2) is True
    assert _levenshtein_within(a, b, 1) is False


def test_turkish_dotted_i_pairs_still_match_after_banding():
    # Türkçe yolu (turkish_upper + NFD combining-strip + diakritik katlama)
    # değişmedi: İ/I ve ı/i çiftleri aynı kademeye düşmeye devam ediyor.
    clients = [_client(name="İlker Işık")]
    exact = check_parties([_q("ilker ışık")], clients, [])
    assert exact[0]["matches"][0]["matched_on"] == "name_exact"

    fuzzy = check_parties([_q("İlker Işıl")], clients, [])   # soyadında 1 harf
    assert fuzzy[0]["matches"][0]["matched_on"] == "name_fuzzy"

    assert _levenshtein_within(
        normalize_person_name("IŞIK"), normalize_person_name("ışık"), 1
    ) is True
