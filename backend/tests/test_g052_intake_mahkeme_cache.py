"""G052 — intake mahkeme sözlüğünün TTL cache'i (`routes/case_intake.py`).

Sözlük `Case.court` üzerinde DISTINCT tam tarama; her merge çağrısında
koşuyordu. Buradaki testler üç şeyi kanıtlar:

1. **Davranış eşdeğerliği** — cache'li sözlük, ham (cache'siz) sorgunun
   döndürdüğünün BİREBİR aynısı; sıralama dahil, ardışık çağrılarda.
2. **Cache gerçekten kullanılıyor** — sıcak çağrıda DB'ye tek SQL bile gitmiyor
   (engine dinleyicisiyle sayılır), TTL içinde eklenen mahkeme bilinçli görünmüyor.
3. **TTL çalışıyor** — süre dolunca tazeleniyor. Saat SAHTELENİR (`time.sleep`
   yok): `managers.ttl_cache` modülünün `time`'ı sahte bir saatle değiştirilir.

Cache süreç-globaldir → her testin başında ve sonunda sıfırlanır.
"""
import types
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_helpers import tenant_filter_clause
from database import Base
import models
from routes import case_intake as intake_route

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"


@pytest.fixture()
def courts_db(monkeypatch):
    """Paylaşılan in-memory sqlite + SQL sayacı (test_party_check.py:345 deseni)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    stats = {"sql": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            stats["sql"] += 1

    # database.SessionLocal: `_load_merge_context` içeride import eder.
    import database

    monkeypatch.setattr(database, "SessionLocal", maker)
    intake_route.reset_known_courts_cache_for_tests()
    yield SimpleNamespace(sessions=maker, stats=stats, engine=engine)
    intake_route.reset_known_courts_cache_for_tests()
    event.remove(engine, "before_cursor_execute", _count)
    engine.dispose()


def _seed_case(env, tracking_no, tenant_id, court, active=True):
    db = env.sessions()
    try:
        db.add(models.Case(
            tracking_no=tracking_no, tenant_id=tenant_id, court=court,
            status="DERDEST", active=active,
        ))
        db.commit()
    finally:
        db.close()


def _uncached_courts(db, tenant_id):
    """Cache ÖNCESİ hâlin birebir kopyası — eşdeğerlik testinin hakemi."""
    return [
        r[0] for r in (
            db.query(models.Case.court)
            .filter(models.Case.active.is_(True), models.Case.court.isnot(None))
            .filter(tenant_filter_clause(models.Case, tenant_id))
            .distinct()
            .all()
        )
        if r[0]
    ]


def _fake_clock(monkeypatch, start=1_000_000.0):
    """`managers.ttl_cache`in saatini sahteler; ilerletme fonksiyonu döndürür."""
    from managers import ttl_cache

    now = [start]
    monkeypatch.setattr(ttl_cache, "time", types.SimpleNamespace(time=lambda: now[0]))
    return now


# ── 1. davranış eşdeğerliği ─────────────────────────────────────────────────

def test_known_courts_matches_uncached_query_exactly(courts_db):
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")
    _seed_case(courts_db, "X1.T1.0002", T1, "İSTANBUL ANADOLU 13. TÜKETİCİ MAHKEMESİ")
    _seed_case(courts_db, "X1.NUL.0003", None, "İZMİR 1. İŞ MAHKEMESİ")  # paylaşımlı havuz
    _seed_case(courts_db, "X1.T1.0004", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")  # tekrar
    _seed_case(courts_db, "X1.T1.0005", T1, None)                                 # court NULL
    _seed_case(courts_db, "X1.T1.0006", T1, "PASİF MAHKEME", active=False)        # pasif dava

    db = courts_db.sessions()
    try:
        beklenen = _uncached_courts(db, T1)
        # 5+ ardışık çağrı: hepsi ham sorguyla BİREBİR aynı (sıralama dahil)
        for _ in range(5):
            assert intake_route._known_courts(db, T1) == beklenen
    finally:
        db.close()

    assert "PASİF MAHKEME" not in beklenen
    assert None not in beklenen
    assert set(beklenen) == {
        "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
        "İSTANBUL ANADOLU 13. TÜKETİCİ MAHKEMESİ",
        "İZMİR 1. İŞ MAHKEMESİ",
    }


# ── 2. cache gerçekten kullanılıyor ─────────────────────────────────────────

def test_hot_call_issues_no_sql_at_all(courts_db):
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    db = courts_db.sessions()
    try:
        courts_db.stats["sql"] = 0
        soguk = intake_route._known_courts(db, T1)
        assert courts_db.stats["sql"] == 1

        courts_db.stats["sql"] = 0
        for _ in range(5):
            assert intake_route._known_courts(db, T1) == soguk
        assert courts_db.stats["sql"] == 0  # sıcak yol DB'ye hiç gitmiyor
    finally:
        db.close()


def test_new_court_stays_invisible_within_ttl(courts_db):
    """İNVALİDASYON YOK: TTL içinde eklenen mahkeme bilinçli olarak görünmez —
    cache'in kullanıldığının ve rapordaki bedelin kanıtı."""
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    db = courts_db.sessions()
    try:
        assert intake_route._known_courts(db, T1) == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]

        _seed_case(courts_db, "X1.T1.0002", T1, "BURSA 2. TÜKETİCİ MAHKEMESİ")
        assert intake_route._known_courts(db, T1) == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]

        intake_route.reset_known_courts_cache_for_tests()
        assert set(intake_route._known_courts(db, T1)) == {
            "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "BURSA 2. TÜKETİCİ MAHKEMESİ",
        }
    finally:
        db.close()


def test_cache_key_isolates_tenants(courts_db):
    _seed_case(courts_db, "X1.T1.0001", T1, "T1 MAHKEMESİ")
    _seed_case(courts_db, "X1.T2.0002", T2, "T2 MAHKEMESİ")
    _seed_case(courts_db, "X1.NUL.0003", None, "PAYLAŞILAN MAHKEME")

    db = courts_db.sessions()
    try:
        # Dönüşümlü sorgu: iki tenant'ın girdisi aynı anda cache'te durabilir,
        # birbirine sızmamalı.
        for _ in range(2):
            assert set(intake_route._known_courts(db, T1)) == {"T1 MAHKEMESİ", "PAYLAŞILAN MAHKEME"}
            assert set(intake_route._known_courts(db, T2)) == {"T2 MAHKEMESİ", "PAYLAŞILAN MAHKEME"}
    finally:
        db.close()


def test_caller_mutation_does_not_corrupt_cache(courts_db):
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    db = courts_db.sessions()
    try:
        birinci = intake_route._known_courts(db, T1)
        birinci.append("UYDURMA MAHKEME")
        assert intake_route._known_courts(db, T1) == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]
    finally:
        db.close()


# ── 3. TTL — saat sahtelenerek ──────────────────────────────────────────────

def test_cache_expires_after_ttl_with_fake_clock(courts_db, monkeypatch):
    now = _fake_clock(monkeypatch)
    ttl = intake_route._KNOWN_COURTS_TTL_SECONDS
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    db = courts_db.sessions()
    try:
        assert intake_route._known_courts(db, T1) == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]
        _seed_case(courts_db, "X1.T1.0002", T1, "BURSA 2. TÜKETİCİ MAHKEMESİ")

        # TTL DOLMADAN: hâlâ cache'ten
        now[0] += ttl - 1
        courts_db.stats["sql"] = 0
        assert intake_route._known_courts(db, T1) == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]
        assert courts_db.stats["sql"] == 0

        # TTL DOLDUKTAN SONRA: girdi süpürülür, sözlük tazelenir
        now[0] += 2
        courts_db.stats["sql"] = 0
        assert set(intake_route._known_courts(db, T1)) == {
            "ANKARA 3. ASLİYE HUKUK MAHKEMESİ", "BURSA 2. TÜKETİCİ MAHKEMESİ",
        }
        assert courts_db.stats["sql"] == 1
    finally:
        db.close()


def test_ttl_is_configurable_for_tests(courts_db, monkeypatch):
    """`reset_..._for_tests(ttl_seconds=...)` TTL'i gerçekten değiştirir."""
    now = _fake_clock(monkeypatch)
    intake_route.reset_known_courts_cache_for_tests(ttl_seconds=10)
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    db = courts_db.sessions()
    try:
        intake_route._known_courts(db, T1)
        _seed_case(courts_db, "X1.T1.0002", T1, "BURSA 2. TÜKETİCİ MAHKEMESİ")

        now[0] += 11  # varsayılan TTL'in (300) çok altında ama 10'un üstünde
        assert len(intake_route._known_courts(db, T1)) == 2
    finally:
        db.close()


# ── 4. merge bağlamı gerçekten cache'i kullanıyor ───────────────────────────

def test_merge_context_serves_courts_from_cache(courts_db):
    """`_load_merge_context` mahkemeleri `_known_courts` üzerinden alır."""
    _seed_case(courts_db, "X1.T1.0001", T1, "ANKARA 3. ASLİYE HUKUK MAHKEMESİ")

    ctx = intake_route._load_merge_context(T1)
    assert ctx["known_courts"] == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]

    _seed_case(courts_db, "X1.T1.0002", T1, "BURSA 2. TÜKETİCİ MAHKEMESİ")
    ctx2 = intake_route._load_merge_context(T1)
    assert ctx2["known_courts"] == ["ANKARA 3. ASLİYE HUKUK MAHKEMESİ"]  # TTL içinde
