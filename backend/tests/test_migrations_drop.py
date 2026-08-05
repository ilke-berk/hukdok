"""Migration listesi tutarlılık testleri — tazminat_talep_tarihi geri alımı.

Gerçek DB yok (conftest dummy URL); burada bildirimsel listenin kendisi
kilitlenir: drop edilen kolon "columns" op'larında ve modelde YENİDEN
tanımlı olmamalı (yoksa her açılışta drop→add döngüsü oluşur).
"""
from database import _MIGRATIONS


def _column_ops(table):
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == table:
            yield from op[2].keys()


def _drop_ops(table):
    for op in _MIGRATIONS:
        if op[0] == "drop" and op[1] == table:
            yield from op[2]


def test_dropped_columns_not_re_added_by_columns_ops():
    for table in {op[1] for op in _MIGRATIONS if op[0] == "drop"}:
        dropped = set(_drop_ops(table))
        added = set(_column_ops(table))
        assert not (dropped & added), (
            f"{table}: {dropped & added} hem drop hem columns op'unda — "
            "kolon her açılışta silinip yeniden eklenir"
        )


def test_dropped_columns_not_in_model():
    import models

    assert not hasattr(models.Case, "tazminat_talep_tarihi"), (
        "Model kolonu duruyor — create_all temiz DB'de kolonu yeniden yaratır"
    )


def test_tazminat_talep_tarihi_drop_registered():
    assert "tazminat_talep_tarihi" in set(_drop_ops("cases"))


def test_judicial_unit_column_registered():
    assert "judicial_unit" in set(_column_ops("cases"))


def test_soft_delete_columns_registered():
    # 2026-08-05 paketi: soft-delete (dava + müvekkil)
    case_cols = set(_column_ops("cases"))
    client_cols = set(_column_ops("clients"))
    for col in ("deleted_at", "deleted_by", "delete_reason"):
        assert col in case_cols, f"cases.{col} migration'da kayıtlı değil"
        assert col in client_cols, f"clients.{col} migration'da kayıtlı değil"


def test_tku_sistem_no_columns_registered():
    case_cols = set(_column_ops("cases"))
    assert "tku_no" in case_cols
    assert "sistem_no" in case_cols


def test_hukmedilen_columns_registered():
    case_cols = set(_column_ops("cases"))
    for col in ("hukmedilen_maddi", "hukmedilen_manevi", "hukmedilen_toplam"):
        assert col in case_cols, f"cases.{col} migration'da kayıtlı değil"


def test_migration_ops_have_known_kinds():
    known = {"rename", "columns", "table", "index", "drop"}
    assert {op[0] for op in _MIGRATIONS} <= known
