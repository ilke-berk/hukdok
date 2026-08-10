"""Soft-delete sözleşme testleri (2026-08-05 paketi) — DB'siz.

Gerçek DB yok (conftest dummy URL); burada model/şema/route sözleşmeleri
kilitlenir. Sorgu filtrelerinin davranışı (silinen dava listede görünmez vs.)
_apply_tenant_filter + auth_helpers merkezlerinden geçer; onların deleted_at
filtresi içerdiği kaynak düzeyinde doğrulanır.
"""
import inspect

import pytest
from fastapi import HTTPException
from fastapi.params import Query as QueryParam

import models
from managers.case_manager import TRACKING_FIELDS, tracking_changes


# ─── Model kolonları (migration kayıt testlerinin model tarafı) ──────────────

def test_case_has_soft_delete_columns():
    for col in ("deleted_at", "deleted_by", "delete_reason"):
        assert hasattr(models.Case, col), f"models.Case.{col} yok"


def test_client_has_soft_delete_columns():
    for col in ("deleted_at", "deleted_by", "delete_reason"):
        assert hasattr(models.Client, col), f"models.Client.{col} yok"


def test_case_document_has_soft_delete_columns():
    for col in ("deleted_at", "deleted_by", "delete_reason"):
        assert hasattr(models.CaseDocument, col), f"models.CaseDocument.{col} yok"


def test_case_has_tku_sistem_no_columns():
    assert hasattr(models.Case, "tku_no")
    assert hasattr(models.Case, "sistem_no")
    # sistem_no unique olmalı (eski sistem kayıt kimliği)
    assert models.Case.sistem_no.property.columns[0].unique is True
    # tku_no unique OLMAMALI (olay grup anahtarı — aynı olayın föyleri paylaşır)
    assert not models.Case.tku_no.property.columns[0].unique


def test_case_has_hukmedilen_columns():
    for col in ("hukmedilen_maddi", "hukmedilen_manevi", "hukmedilen_toplam"):
        assert hasattr(models.Case, col), f"models.Case.{col} yok"
        # NULL = girilmedi ayrımı için default olmamalı
        assert models.Case.__table__.columns[col].default is None


# ─── DELETE uçları gerekçe zorunluluğu ───────────────────────────────────────

def _reason_param(fn):
    sig = inspect.signature(fn)
    return sig.parameters.get("reason")


def _assert_required_query(p):
    assert isinstance(p.default, QueryParam)
    # Query(...) → zorunlu; FastAPI/pydantic sürümüne göre Ellipsis veya
    # PydanticUndefined olarak saklanır
    try:
        from pydantic_core import PydanticUndefined
        required_markers = (..., PydanticUndefined)
    except ImportError:  # pydantic v1
        required_markers = (...,)
    assert p.default.default in required_markers, "reason zorunlu olmaktan çıkarılmış"


def test_case_delete_requires_reason():
    from routes.cases import api_delete_case
    p = _reason_param(api_delete_case)
    assert p is not None, "DELETE /api/cases reason parametresi kaldırılmış"
    _assert_required_query(p)


def test_client_delete_requires_reason():
    from routes.clients import api_delete_client
    p = _reason_param(api_delete_client)
    assert p is not None, "DELETE /api/clients reason parametresi kaldırılmış"
    _assert_required_query(p)


def test_document_delete_requires_reason():
    from routes.documents import api_delete_document
    p = _reason_param(api_delete_document)
    assert p is not None, "DELETE /api/documents reason parametresi kaldırılmış"
    _assert_required_query(p)


# ─── Restore ucu ─────────────────────────────────────────────────────────────

def test_restore_rejects_unknown_record_type():
    from routes.admin import api_restore_record
    # record_type doğrulaması DB'ye dokunmadan önce çalışır
    # ("document" 2026-08-10'da geçerli tip oldu — bilinmeyen örnek: hearing)
    with pytest.raises(HTTPException) as exc:
        api_restore_record("hearing", 1, user={}, tenant_id="t")
    assert exc.value.status_code == 400


# ─── Merkezi filtreler kaynak düzeyinde ──────────────────────────────────────

def test_central_filters_contain_deleted_at():
    """_apply_tenant_filter ve auth_helpers deleted_at filtrelemeli —
    filtre yanlışlıkla kaldırılırsa silinen kayıtlar tüm listelere geri sızar."""
    import auth_helpers
    from managers import case_manager

    src = inspect.getsource(case_manager._apply_tenant_filter)
    assert "deleted_at.is_(None)" in src

    for fn in (
        auth_helpers.get_tenant_owned_case,
        auth_helpers.get_tenant_owned_hearing,
        auth_helpers.get_tenant_owned_client,
        auth_helpers.get_tenant_owned_document,
    ):
        assert "deleted_at.is_(None)" in inspect.getsource(fn), fn.__name__


def test_client_sequence_deliberately_ignores_soft_delete():
    """client-sequence silinen davaların numara aralığını SAYMAYA devam etmeli
    (aynı numara yeniden önerilmesin — unique kısıt silinenleri de kapsıyor)."""
    from routes import cases as cases_route
    src = inspect.getsource(cases_route.get_client_case_sequence)
    assert "deleted_at.is_(None)" not in src, (
        "client-sequence'e deleted_at filtresi eklenmiş — bilinçli açık olmalıydı"
    )


# ─── Hükmedilen tutarlar takip sözleşmesi ────────────────────────────────────

def test_hukmedilen_in_tracking_fields():
    for f in ("hukmedilen_maddi", "hukmedilen_manevi", "hukmedilen_toplam"):
        assert f in TRACKING_FIELDS


def test_tracking_changes_picks_hukmedilen():
    data = {"hukmedilen_maddi": 150000.0, "hukmedilen_toplam": None}
    changes = dict(tracking_changes(data))
    assert changes["hukmedilen_maddi"] == 150000.0
    # None gönderilen alan silinir (exclude_unset semantiği) — listeye girer
    assert "hukmedilen_toplam" in changes
    assert changes["hukmedilen_toplam"] is None
    # gönderilmeyen alan listeye girmez
    assert "hukmedilen_manevi" not in changes
