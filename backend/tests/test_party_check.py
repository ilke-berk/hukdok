"""party_check (Tanıdık Sorgu / Çıkar Çatışması) birim testleri — DB'siz."""
from party_check import (
    check_parties,
    normalize_person_name,
    normalize_tc,
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
