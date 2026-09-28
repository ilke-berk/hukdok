"""G233 — `GET /api/hearing-dates?lawyer=` seçimi dava listesi filtresiyle AYNI sözleşmeyle çözülür.

- `?lawyer=<kimlik>` (harf duyarsız) → o avukatın duruşmaları; pasif avukatın kimliği de adına iner (G225).
- `?lawyer=<ad>` (liste yazımı ya da toleranslı yazım) → bugünkü sonuç AYNEN.
- `?lawyer=<eski kod>` → 1 sürüm geriye uyumlu (G231'de kalkar); bilinmeyen değer → boş liste (500 değil).
- Parametresiz çağrı ve tenant/soft-delete süzgeci değişmez.

Eski kodda kırmızıdır: kimlik (`AVK-00001`) ada inmiyordu, eski kod artık çözülmüyordu → boş liste.
"""
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import models
from managers import lawyer_resolver, reference_lists
from managers.config_manager import DynamicConfig

TENANT = "tenant-a"


def _translate(deger, kaynak, hedef):
    if deger is None:
        return None
    return deger.translate(str.maketrans(kaynak, hedef))


@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.create_function("translate", 3, _translate)
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    from routes import cases as cases_routes
    monkeypatch.setattr(cases_routes, "SessionLocal", Fabrika)
    config = DynamicConfig.get_instance()
    onceki = config.get_lawyers()
    yield Fabrika
    config.set_lawyers(onceki)
    engine.dispose()


@pytest.fixture()
def veri(fabrika):
    """Serap (AVK-00001, kod SERAPTUR) · Tuğçe (AVK-00002) · Pasif Kemal (AVK-00003).

    Duruşmalar (lawyer_name liste yazımında):
      h_serap  → Serap Turgal, kendi tenant'ı
      h_tugce  → Tuğçe Ungör Yanık, tenant NULL (paylaşımlı havuz)
      h_kemal  → Kemal Pasif (pasif avukat)
      h_baska  → Serap Turgal ama BAŞKA tenant'ın davası (süzülür)
      h_silik  → Serap Turgal ama silinmiş dava (süzülür)
    """
    db = fabrika()
    db.add_all([
        models.Lawyer(kimlik="AVK-00001", code="SERAPTUR", name="Serap Turgal", active=True, sequence=1),
        models.Lawyer(kimlik="AVK-00002", code="TUGCEUNG", name="Tuğçe Ungör Yanık", active=True, sequence=2),
        models.Lawyer(kimlik="AVK-00003", code="KEMALPAS", name="Kemal Pasif", active=False, sequence=3),
    ])
    k_serap = models.Case(tracking_no="G233.1", status="DERDEST", tenant_id=TENANT)
    k_tugce = models.Case(tracking_no="G233.2", status="DERDEST", tenant_id=None)
    k_kemal = models.Case(tracking_no="G233.3", status="DERDEST", tenant_id=TENANT)
    k_baska = models.Case(tracking_no="G233.4", status="DERDEST", tenant_id="tenant-b")
    k_silik = models.Case(tracking_no="G233.5", status="DERDEST", tenant_id=TENANT,
                          deleted_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    db.add_all([k_serap, k_tugce, k_kemal, k_baska, k_silik])
    db.flush()
    duruslar = {
        "h_serap": models.HearingDate(case_id=k_serap.id, hearing_date=date(2026, 10, 1), lawyer_name="Serap Turgal"),
        "h_tugce": models.HearingDate(case_id=k_tugce.id, hearing_date=date(2026, 10, 2),
                                      lawyer_name="Tuğçe Ungör Yanık"),
        "h_kemal": models.HearingDate(case_id=k_kemal.id, hearing_date=date(2026, 10, 3), lawyer_name="Kemal Pasif"),
        "h_baska": models.HearingDate(case_id=k_baska.id, hearing_date=date(2026, 10, 4), lawyer_name="Serap Turgal"),
        "h_silik": models.HearingDate(case_id=k_silik.id, hearing_date=date(2026, 10, 5), lawyer_name="Serap Turgal"),
    }
    db.add_all(list(duruslar.values()))
    db.commit()
    ids = {ad: h.id for ad, h in duruslar.items()}
    db.close()
    reference_lists.refresh_cache("lawyers")
    return ids


@pytest.fixture()
def istemci(fabrika):
    from dependencies import get_current_tenant, get_current_user
    from routes import cases as cases_routes

    app = FastAPI()
    app.include_router(cases_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "u@example.com", "tid": TENANT}
    app.dependency_overrides[get_current_tenant] = lambda: TENANT
    return TestClient(app, raise_server_exceptions=False)


def _idler(istemci, lawyer=None):
    params = {} if lawyer is None else {"lawyer": lawyer}
    r = istemci.get("/api/hearing-dates", params=params)
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()}


# ── kimlik ───────────────────────────────────────────────────────────────────

def test_kimlik_avukatin_durusmalarini_doner(istemci, veri):
    assert _idler(istemci, "AVK-00001") == {veri["h_serap"]}
    assert _idler(istemci, "avk-00001") == {veri["h_serap"]}
    assert _idler(istemci, "AVK-00002") == {veri["h_tugce"]}


def test_pasif_avukatin_kimligi_adina_iner(istemci, veri):
    assert "AVK-00003" not in [lw["kimlik"] for lw in DynamicConfig.get_instance().get_lawyers()]
    assert _idler(istemci, "AVK-00003") == {veri["h_kemal"]}


def test_bilinmeyen_kimlik_bos(istemci, veri):
    assert _idler(istemci, "AVK-09999") == set()


# ── ad + eski kod (geriye uyum) ──────────────────────────────────────────────

def test_ad_bugunku_sonucu_aynen_doner(istemci, veri):
    assert _idler(istemci, "Serap Turgal") == {veri["h_serap"]}
    assert _idler(istemci, "Tuğçe Ungör Yanık") == {veri["h_tugce"]}
    # Toleranslı yazım listedeki yazıma iner (27.09 davranışı)
    assert _idler(istemci, "TUGCE UNGOR") == {veri["h_tugce"]}
    assert _idler(istemci, "Av. Serap Turgal") == {veri["h_serap"]}


def test_eski_kod_geriye_uyumlu(istemci, veri):
    # GERİYE UYUM (G231'de kalkar): eski `?lawyer=<kod>` yer imleri.
    assert _idler(istemci, "SERAPTUR") == {veri["h_serap"]}


def test_bilinmeyen_deger_bos_500_degil(istemci, veri):
    assert _idler(istemci, "Hiç Kimse") == set()
    assert _idler(istemci, "XYZKOD") == set()


# ── değişmeyenler ────────────────────────────────────────────────────────────

def test_parametresiz_cagri_tenant_ve_silme_suzgeci(istemci, veri):
    assert _idler(istemci) == {veri["h_serap"], veri["h_tugce"], veri["h_kemal"]}


def test_secim_cozumu_dava_listesiyle_ayni_yol(veri):
    """Duruşma ve dava filtresi aynı `_secimdeki_avukat` sözleşmesine bağlı (kopya mantık yok)."""
    liste = DynamicConfig.get_instance().get_lawyers()
    for secim in ("AVK-00001", "avk-00002", "Serap Turgal", "SERAPTUR"):
        hedef = lawyer_resolver._secimdeki_avukat(secim, liste)
        assert hedef is not None
        assert lawyer_resolver.secimi_liste_adina_cevir(secim) == hedef["name"]
    assert lawyer_resolver.secimi_liste_adina_cevir("AVK-09999") is None
    assert lawyer_resolver.secimi_liste_adina_cevir("") is None
