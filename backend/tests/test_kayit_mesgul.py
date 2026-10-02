"""Kilitli kayda yazma → 409 "kayıt meşgul" (02.10.2026 olayı).

Olay: 01.10 akşamı teslim paketinin gerçek uygulaması, 02.10 sabahı kuru koşusu
binlerce kartı TEK transaction'da dakikalarca kilitli tuttu. O sırada panelden
avukat adı değişikliği ve #3469'un aşama geçişi `lock_timeout` (5 sn) ile düştü;
manager hatayı yutup False döndüğü için kullanıcı "Dava bulunamadı"(404) /
"Güncelleme başarısız"(400) gördü ve ERROR logu basıldı.

Sözleşme:
- `db_errors.is_lock_timeout` SQLSTATE 55P03'ü tanır (gerçek Postgres hatasıyla),
  UNIQUE ihlali ve öteki hatalar kilit SAYILMAZ.
- `update_case_tracking` ve `reference_lists.update_item` kilit hatasında
  `KayitMesgulError` yükseltir; öteki hatalarda eski `False` davranışı sürer.
- HTTP: 409 + `KAYIT_MESGUL_DETAIL`; hiçbir alan yazılmaz; ERROR basılmaz (WARNING).
- Hatayı yutmayan yollar için `OperationalError` ağı: kilit → 409, öteki → 503 (değişmedi).
"""
import logging
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import test_migration_path as mig
from db_errors import KAYIT_MESGUL_DETAIL, KayitMesgulError, is_lock_timeout, is_unique_violation
from managers import case_manager, reference_lists

admin_engine = mig.admin_engine

# Test bağlantısının kilit bekleme sınırı: prod 5 sn, test hızlı düşsün.
_TEST_LOCK_MS = 300


def _errorlar(caplog):
    return [k.getMessage() for k in caplog.records if k.levelno >= logging.ERROR]


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — sınıflandırma ve manager dalları
# ═══════════════════════════════════════════════════════════════════════════

class _SurucuHatasi(Exception):
    def __init__(self, pgcode):
        super().__init__(f"pgcode={pgcode}")
        self.pgcode = pgcode


def _sa_hatasi(pgcode):
    return OperationalError("UPDATE cases ...", {}, _SurucuHatasi(pgcode))


def test_is_lock_timeout_yalniz_55P03():
    assert is_lock_timeout(_sa_hatasi("55P03")) is True
    assert is_lock_timeout(_SurucuHatasi("55P03")) is True       # sarmalanmamış sürücü hatası
    assert is_lock_timeout(_sa_hatasi("57014")) is False         # statement_timeout
    assert is_lock_timeout(_sa_hatasi("23505")) is False         # unique
    assert is_lock_timeout(ValueError("x")) is False


class _CommitPatlar:
    """Sorguda gerçek kartı döndürür, commit'te verilen hatayı fırlatır."""

    def __init__(self, hata):
        self.hata = hata
        self.geri_alindi = False

    def __call__(self):
        return self

    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return SimpleNamespace(case_stage=None, status="DERDEST", tenant_id=None)

    def add(self, _obj):
        pass

    def commit(self):
        raise self.hata

    def rollback(self):
        self.geri_alindi = True

    def close(self):
        pass


def test_update_case_tracking_kilitte_kayit_mesgul_error_basmaz(monkeypatch, caplog):
    sahte = _CommitPatlar(_sa_hatasi("55P03"))
    monkeypatch.setattr(case_manager, "SessionLocal", sahte)
    monkeypatch.setattr(case_manager, "_apply_tenant_filter", lambda q, _t: q)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(KayitMesgulError) as exc:
            case_manager.update_case_tracking(1, {"case_stage": "KAPALI"}, changed_by="avukat")
    assert str(exc.value) == KAYIT_MESGUL_DETAIL
    assert sahte.geri_alindi
    assert _errorlar(caplog) == []


def test_update_case_tracking_baska_hatada_eski_false_davranisi(monkeypatch, caplog):
    sahte = _CommitPatlar(_sa_hatasi("57014"))
    monkeypatch.setattr(case_manager, "SessionLocal", sahte)
    monkeypatch.setattr(case_manager, "_apply_tenant_filter", lambda q, _t: q)
    with caplog.at_level(logging.WARNING):
        assert case_manager.update_case_tracking(1, {"case_stage": "KAPALI"}, changed_by="avukat") is False
    assert len(_errorlar(caplog)) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. dbtest — scratch Postgres, gerçek satır kilidi
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_engine(admin_engine):
    with mig._scratch_database(admin_engine, "kayitmesgul") as engine:
        mig._run_init_db(engine)
        yield engine


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın (test_g196 deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from routes.config import require_admin

    # Uygulama motoru gibi lock_timeout'lu, ama test için kısa.
    uygulama = create_engine(
        pg_engine.url, poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": f"-c lock_timeout={_TEST_LOCK_MS}"},
    )
    Fabrika = sessionmaker(bind=uygulama, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    app.dependency_overrides[require_admin] = lambda: user
    limiter.reset()
    try:
        yield SimpleNamespace(client=TestClient(app), engine=pg_engine)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()
        uygulama.dispose()


def _kart_ac(pg, **alanlar) -> int:
    with pg.engine.begin() as conn:
        return conn.execute(text(
            "INSERT INTO cases (tracking_no, status, responsible_lawyer_name) "
            "VALUES (:t, 'DERDEST', :avukat) RETURNING id"
        ), {"t": alanlar.get("tracking_no", "KM-0001"), "avukat": alanlar.get("avukat")}).scalar()


@contextmanager
def _toplu_islem_kilidi(pg, case_id):
    """Aktarımın yaptığı gibi: açık transaction kartın satırını kilitli tutar."""
    conn = pg.engine.connect()
    tx = conn.begin()
    conn.execute(text("UPDATE cases SET updated_at = now() WHERE id = :id"), {"id": case_id})
    try:
        yield
    finally:
        tx.rollback()
        conn.close()


def _alan(pg, case_id, kolon):
    with pg.engine.connect() as conn:
        return conn.execute(text(f"SELECT {kolon} FROM cases WHERE id = :id"), {"id": case_id}).scalar()


@pytest.mark.dbtest
def test_pg_gercek_kilit_hatasi_55P03_unique_degil(pg):
    cid = _kart_ac(pg, tracking_no="KM-SINIF")
    with _toplu_islem_kilidi(pg, cid):
        db = case_manager.SessionLocal()
        try:
            with pytest.raises(OperationalError) as exc:
                db.execute(text("UPDATE cases SET case_stage = 'KAPALI' WHERE id = :id"), {"id": cid})
        finally:
            db.rollback()
            db.close()
    assert is_lock_timeout(exc.value)
    assert not is_unique_violation(exc.value)


@pytest.mark.dbtest
def test_pg_takip_paneli_kilitli_kartta_409_yazmaz_kilit_kalkinca_200(pg, caplog):
    cid = _kart_ac(pg, tracking_no="KM-TAKIP")
    with _toplu_islem_kilidi(pg, cid):
        with caplog.at_level(logging.WARNING):
            r = pg.client.patch(f"/api/cases/{cid}/tracking", json={"case_stage": "KAPALI", "note": None})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == KAYIT_MESGUL_DETAIL
    assert _alan(pg, cid, "case_stage") is None
    with pg.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM case_stage_logs WHERE case_id = :id"), {"id": cid}).scalar() == 0
    assert _errorlar(caplog) == []

    # Toplu işlem bitti → aynı istek geçer
    r = pg.client.patch(f"/api/cases/{cid}/tracking", json={"case_stage": "KAPALI", "note": None})
    assert r.status_code == 200, r.text
    assert _alan(pg, cid, "case_stage") == "KAPALI"


@pytest.mark.dbtest
def test_pg_avukat_adi_degisikligi_kilitli_kartta_409_hicbir_sey_degismez(pg, caplog):
    with pg.engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO lawyers (kimlik, code, name, active, sequence) "
            "VALUES ('AVK-00901', 'KMA', 'Barış Yücel Test', true, 0)"
        ))
    cid = _kart_ac(pg, tracking_no="KM-AVUKAT", avukat="Barış Yücel Test")

    with _toplu_islem_kilidi(pg, cid):
        with caplog.at_level(logging.WARNING):
            r = pg.client.post("/api/config/update", json={
                "type": "lawyers", "code": "KMA", "fields": {"name": "Barış Yücel Yeni"},
            })
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == KAYIT_MESGUL_DETAIL
    # Tek transaction: ne liste öğesi ne kart değişti (kısmi yayılım yok)
    with pg.engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM lawyers WHERE code = 'KMA'")).scalar() == "Barış Yücel Test"
    assert _alan(pg, cid, "responsible_lawyer_name") == "Barış Yücel Test"
    assert _errorlar(caplog) == []


@pytest.mark.dbtest
def test_pg_kilit_beklemesi_havuzu_rehin_almaz(pg):
    """Kilit varken paralel iki istek de sınırlı sürede 409 döner (birbirini beklemez)."""
    cid = _kart_ac(pg, tracking_no="KM-PARALEL")
    sonuclar: list = []

    def _istek():
        r = pg.client.patch(f"/api/cases/{cid}/tracking", json={"karar_no": "2026/1"})
        sonuclar.append(r.status_code)

    with _toplu_islem_kilidi(pg, cid):
        is_parcaciklari = [threading.Thread(target=_istek) for _ in range(2)]
        for t in is_parcaciklari:
            t.start()
        for t in is_parcaciklari:
            t.join(timeout=10)
    assert sonuclar == [409, 409]


# ═══════════════════════════════════════════════════════════════════════════
# 3. HTTP ağı — hatayı yutmayan yollar
# ═══════════════════════════════════════════════════════════════════════════

def test_operational_error_agi_kilitte_409_digerinde_503(monkeypatch):
    from starlette.testclient import TestClient

    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from routes import cases as cases_route

    hata = {"kod": "55P03"}

    def _patlat(*_a, **_k):
        raise _sa_hatasi(hata["kod"])

    monkeypatch.setattr(cases_route, "update_case_tracking", _patlat)
    app.dependency_overrides[get_current_user] = lambda: {"name": "Test"}
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch("/api/cases/1/tracking", json={"karar_no": "1"})
        assert r.status_code == 409 and r.json()["detail"] == KAYIT_MESGUL_DETAIL
        hata["kod"] = "08006"   # bağlantı koptu → eski 503 davranışı
        r = client.patch("/api/cases/1/tracking", json={"karar_no": "1"})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()
        limiter.reset()
