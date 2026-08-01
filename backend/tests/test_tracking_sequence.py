"""Ofis no sıra önerisi — max_tracking_sequence testleri (Faz 6.3).

Bilinen bug (2026-07-16): COUNT tabanlı öneri, araya silinmiş kayıt girince
dolu numarayı yeniden önerip UniqueViolation/409 üretiyordu. max+1 semantiği
burada kilitlenir; route yalnız SQL filtre + bu saf fonksiyondur.
"""
from routes.cases import max_tracking_sequence


def test_gapless_sequence():
    nos = ["HD.YILMAZAHME.0001.11000", "HD.YILMAZAHME.0002.11000"]
    assert max_tracking_sequence(nos) + 1 == 3


def test_deleted_record_gap_does_not_collide():
    # 3 numaralı dava silinmiş: COUNT=3 → öneri 4 olurdu ama 4 DOLU.
    # max+1 → 5 önerir, çakışmaz.
    nos = [
        "HD.YILMAZAHME.0001.11000",
        "HD.YILMAZAHME.0002.11000",
        "HD.YILMAZAHME.0004.11000",
    ]
    assert max_tracking_sequence(nos) + 1 == 5


def test_empty_list_starts_at_one():
    assert max_tracking_sequence([]) + 1 == 1


def test_malformed_numbers_ignored():
    nos = ["ESKI-FORMAT-123", None, "", "HD.YILMAZAHME.0007.11000"]
    assert max_tracking_sequence(nos) == 7


def test_all_malformed_yields_zero():
    assert max_tracking_sequence(["X", "2024/123", None]) == 0


def test_padding_underscore_name_block_matches_pattern():
    # İsim bloğu '_' ile pad'li olabilir (doctype kodlarındaki gibi) —
    # desen 10 karakteri serbest bırakır
    nos = ["HD.KAYA______.0012.10000"]
    assert max_tracking_sequence(nos) == 12
