"""update_case_tracking exclude_unset semantiği (Faz 1).

Route, CaseTrackingUpdate'i model_dump(exclude_unset=True) ile dict'e çevirir;
manager tracking_changes ile uygular. Sözleşme:
- Gönderilmeyen alan dict'e girmez → dokunulmaz.
- None (null) gönderilen alan dict'e girer → alan SİLİNİR.
DB'ye dokunulmaz; route dump'ı + saf tracking_changes kilitlenir.
"""
from datetime import date

from managers.case_manager import TRACKING_FIELDS, tracking_changes
from schemas import CaseTrackingUpdate


def _route_dump(payload: dict) -> dict:
    """Route'un yaptığı dönüşümün birebir kopyası."""
    return CaseTrackingUpdate.model_validate(payload).model_dump(exclude_unset=True)


def test_unsent_fields_absent_from_changes():
    changes = tracking_changes(_route_dump({"karar_no": "2026/12"}))
    assert changes == [("karar_no", "2026/12")]


def test_explicit_null_is_a_delete():
    # Tarih sil + kaydet → DB null (plandaki elle senaryonun birim karşılığı)
    changes = tracking_changes(_route_dump({"karar_tarihi": None}))
    assert changes == [("karar_tarihi", None)]


def test_mixed_set_and_null():
    changes = dict(tracking_changes(_route_dump({
        "karar_turu": "KABUL",
        "karar_teblig_tarihi": None,
    })))
    assert changes["karar_turu"] == "KABUL"
    assert changes["karar_teblig_tarihi"] is None
    assert len(changes) == 2


def test_empty_payload_touches_nothing():
    assert tracking_changes(_route_dump({})) == []


def test_note_is_not_a_tracking_field():
    # note yalnız CaseStageLog'a gider; alan olarak case'e yazılmaz
    changes = tracking_changes(_route_dump({"case_stage": "ISTINAF", "note": "geçiş"}))
    assert changes == [("case_stage", "ISTINAF")]


def test_date_fields_parse_to_date():
    changes = dict(tracking_changes(_route_dump({"kesinlesme_tarihi": "2026-08-01"})))
    assert changes["kesinlesme_tarihi"] == date(2026, 8, 1)


def test_schema_covers_all_tracking_fields():
    # Şemada olmayan alan route'tan geçemez; TRACKING_FIELDS ile şema uyumu
    schema_fields = set(CaseTrackingUpdate.model_fields)
    missing = [f for f in TRACKING_FIELDS if f not in schema_fields and f != "status"]
    # "status" takip formunda yok ama manager eski çağrılar için tutuyor
    assert missing == []


def test_unknown_key_in_raw_dict_ignored():
    # Manager'a route dışından ham dict gelirse bilinmeyen anahtar uygulanmaz
    assert tracking_changes({"tracking_no": "HACK"}) == []
