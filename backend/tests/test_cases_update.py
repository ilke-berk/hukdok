"""update_case taraf senkronu — diff_case_parties saf eşleme testleri.

Amaç (Faz 6.1): taraf listesi değişmeden yapılan güncellemede mevcut
case_party id'leri SABİT kalmalı ki case_documents.case_party_id bağları
(FK SET NULL) öksüzleşmesin. DB'ye dokunulmaz; update_case'in kullandığı
saf diff fonksiyonu kilitlenir.
"""
from managers.case_manager import diff_case_parties


def _p(id, name, tc=None):
    return {"id": id, "name": name, "tc_no": tc}


def _inc(name, role="Davacı", tc=None, **kw):
    return {"name": name, "role": role, "party_type": "CLIENT", "tc_no": tc, **kw}


def test_unchanged_parties_all_matched_ids_stable():
    existing = [_p(1, "Ahmet Yılmaz"), _p(2, "Quick Sigorta A.Ş.")]
    incoming = [_inc("Ahmet Yılmaz"), _inc("Quick Sigorta A.Ş.", role="Davalı")]
    updates, inserts, deletes = diff_case_parties(existing, incoming)
    assert [pid for pid, _ in updates] == [1, 2]
    assert inserts == [] and deletes == []


def test_role_change_keeps_id():
    existing = [_p(5, "Ahmet Yılmaz")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("Ahmet Yılmaz", role="Davalı")]
    )
    assert updates[0][0] == 5
    assert updates[0][1]["role"] == "Davalı"
    assert inserts == [] and deletes == []


def test_added_party_is_insert():
    existing = [_p(1, "Ahmet Yılmaz")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("Ahmet Yılmaz"), _inc("Yeni Kişi")]
    )
    assert [pid for pid, _ in updates] == [1]
    assert [i["name"] for i in inserts] == ["Yeni Kişi"]
    assert deletes == []


def test_removed_party_is_delete():
    existing = [_p(1, "Ahmet Yılmaz"), _p(2, "Giden Kişi")]
    updates, inserts, deletes = diff_case_parties(existing, [_inc("Ahmet Yılmaz")])
    assert [pid for pid, _ in updates] == [1]
    assert inserts == []
    assert deletes == [2]


def test_corporate_suffix_normalization_matches():
    # "A.Ş." ↔ "ANONİM ŞİRKETİ" aynı anahtara düşer (normalize_party_key)
    existing = [_p(3, "Quick Sigorta Anonim Şirketi")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("QUICK SİGORTA A.Ş.", role="Davalı")]
    )
    assert updates[0][0] == 3
    assert inserts == [] and deletes == []


def test_word_order_insensitive_match():
    existing = [_p(7, "Yılmaz Ahmet")]
    updates, inserts, deletes = diff_case_parties(existing, [_inc("Ahmet Yılmaz")])
    assert updates[0][0] == 7
    assert inserts == [] and deletes == []


def test_tc_match_survives_name_correction():
    # İsim düzeltilmiş ama TC aynı → aynı satır güncellenir, silinmez
    existing = [_p(9, "Ahmet Yilmaz (hatalı)", tc="12345678901")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("Ahmet Yılmaz", tc="12345678901")]
    )
    assert updates[0][0] == 9
    assert inserts == [] and deletes == []


def test_name_match_survives_tc_correction():
    # TC düzeltilmiş ama isim aynı → TC düzeltmesi sayılır, satır korunur
    existing = [_p(4, "Ahmet Yılmaz", tc="11111111111")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("Ahmet Yılmaz", tc="22222222222")]
    )
    assert updates[0][0] == 4
    assert inserts == [] and deletes == []


def test_duplicate_names_consume_one_each():
    existing = [_p(1, "Ahmet Yılmaz"), _p(2, "Ahmet Yılmaz")]
    updates, inserts, deletes = diff_case_parties(
        existing, [_inc("Ahmet Yılmaz"), _inc("Ahmet Yılmaz", role="Davalı")]
    )
    assert sorted(pid for pid, _ in updates) == [1, 2]
    assert inserts == [] and deletes == []


def test_full_replacement():
    existing = [_p(1, "Eski Kişi")]
    updates, inserts, deletes = diff_case_parties(existing, [_inc("Yepyeni Kişi")])
    assert updates == []
    assert [i["name"] for i in inserts] == ["Yepyeni Kişi"]
    assert deletes == [1]


def test_empty_incoming_deletes_all():
    existing = [_p(1, "A Kişi"), _p(2, "B Kişi")]
    updates, inserts, deletes = diff_case_parties(existing, [])
    assert updates == [] and inserts == []
    assert deletes == [1, 2]


def test_empty_name_never_matches_blank_key():
    # Adı boş gelen satır isim anahtarıyla eşleşmemeli (çöp eşleşme koruması)
    existing = [_p(1, "")]
    updates, inserts, deletes = diff_case_parties(existing, [_inc("")])
    assert updates == []
    assert len(inserts) == 1
    assert deletes == [1]
