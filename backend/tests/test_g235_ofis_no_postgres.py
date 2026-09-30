"""G235 — ofis no sayacı eşzamanlılığı + migrasyon 56, GERÇEK Postgres'e karşı.

`test_migration_path.py` kalıbı: her test kendi scratch veritabanını
(`hukudok_migtest_*`) yaratır ve sonunda düşürür; gerçek veritabanına yazılmaz.
DB'ye ulaşılamıyorsa testler SKIP olur (konteynersiz saf birim koşusu yeşil kalır).

Kilitlenenler:
* `sira_tahsis_et`: ayrı bağlantılardan paralel çağrılar hiç aynı sırayı almaz.
* Migrasyon 56 iki yoldan da aynı şemaya varır ve idempotenttir:
  - `create_all` yolu (tablolar/kolonlar modelden doğar, op'lar atlanır),
  - çıplak yol (tablolar/kolonlar YOK → `("table", ...)`/`("columns", ...)` op'ları koşar).
"""
import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import database
from services import ofis_no

pytestmark = pytest.mark.dbtest

_SCRATCH_PREFIX = "hukudok_migtest_"
_TABLOLAR = ("ofis_no_sayaclari", "sigorta_kisa_kodlari")
_KOLONLAR = {"client_categories": ("ofis_no_kodu",), "cases": ("ofis_no_kodu", "ofis_no_sira")}
_INDEXLER = ("uq_sigorta_kisa_kodlari_kod", "uq_cases_ofis_no_kod_sira")


@pytest.fixture(scope="module")
def admin_engine():
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")
    engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool,
                           connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G235 Postgres testi atlandı")
    yield engine
    engine.dispose()


def _scratch(admin_engine, suffix):
    """Boş scratch DB yaratır; (engine, temizle) döner. Ad scratch önekli olmak ZORUNDA."""
    name = f"{_SCRATCH_PREFIX}{os.getpid()}_g235_{suffix}"
    assert name.startswith(_SCRATCH_PREFIX) and name != admin_engine.url.database
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(admin_engine.url.set(database=name), poolclass=NullPool,
                           connect_args={"connect_timeout": 5})

    def temizle():
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = :name AND pid <> pg_backend_pid()"),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))

    return engine, temizle


def _database_engine_ile(engine, fn):
    """`database` modül-global engine'ini yalnız çağrı boyunca değiştirir."""
    original = database.engine
    database.engine = engine
    try:
        fn()
    finally:
        database.engine = original


@pytest.fixture(scope="module")
def kurulu_db(admin_engine):
    """Sıfırdan `init_db()` koşmuş scratch DB (create_all yolu)."""
    engine, temizle = _scratch(admin_engine, "fresh")
    try:
        _database_engine_ile(engine, database.init_db)
        yield engine
    finally:
        temizle()


def _g235_semasi(engine):
    """G235'in şema çıktısı: (tablo, kolon, tür, null?) + index tanımları."""
    tablolar = list(_TABLOLAR) + list(_KOLONLAR)
    with engine.connect() as conn:
        kolonlar = conn.execute(text(
            "SELECT table_name, column_name, data_type, character_maximum_length, is_nullable "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = ANY(:t) ORDER BY table_name, column_name"
        ), {"t": tablolar}).all()
        indexler = conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname = ANY(:i) ORDER BY indexname"
        ), {"i": list(_INDEXLER) + ["ofis_no_sayaclari_pkey", "sigorta_kisa_kodlari_pkey"]}).all()
    g235_kolonlari = [
        tuple(k) for k in kolonlar
        if k[0] in _TABLOLAR or k[1] in _KOLONLAR.get(k[0], ())
    ]
    return {"kolonlar": g235_kolonlari, "indexler": [tuple(i) for i in indexler]}


# ─── migrasyon 56 ────────────────────────────────────────────────────────────

def test_migrasyon_56_sifirdan_kurulumda_tam(kurulu_db):
    sema = _g235_semasi(kurulu_db)
    adlar = {(k[0], k[1]) for k in sema["kolonlar"]}
    assert {("ofis_no_sayaclari", "kod"), ("ofis_no_sayaclari", "son_sira"), ("ofis_no_sayaclari", "updated_at"),
            ("sigorta_kisa_kodlari", "kod"), ("sigorta_kisa_kodlari", "ad"),
            ("sigorta_kisa_kodlari", "eslesme_anahtarlari"), ("sigorta_kisa_kodlari", "aktif"),
            ("client_categories", "ofis_no_kodu"),
            ("cases", "ofis_no_kodu"), ("cases", "ofis_no_sira")} <= adlar
    indexler = dict(sema["indexler"])
    assert set(indexler) == set(_INDEXLER) | {"ofis_no_sayaclari_pkey", "sigorta_kisa_kodlari_pkey"}
    assert "UNIQUE" in indexler["uq_sigorta_kisa_kodlari_kod"]
    assert "UNIQUE" in indexler["uq_cases_ofis_no_kod_sira"]
    assert "WHERE (ofis_no_kodu IS NOT NULL)" in indexler["uq_cases_ofis_no_kod_sira"]
    # cases parçaları NULL'a açık: mevcut kartlar numaralanmadan durur (G238'e kadar)
    null = {(k[0], k[1]): k[4] for k in sema["kolonlar"]}
    assert null[("cases", "ofis_no_kodu")] == "YES" and null[("cases", "ofis_no_sira")] == "YES"
    assert null[("ofis_no_sayaclari", "son_sira")] == "NO"


def test_migrasyon_56_ikinci_kosuda_degismez(kurulu_db):
    once = _g235_semasi(kurulu_db)
    _database_engine_ile(kurulu_db, database.init_db)
    _database_engine_ile(kurulu_db, database.check_and_migrate_tables)
    assert _g235_semasi(kurulu_db) == once


def test_migrasyon_56_ciplak_yol_ayni_semaya_varir(admin_engine, kurulu_db):
    """G235 öncesi şema (tablolar/kolonlar YOK) → op'lar GERÇEKTEN koşar, sonuç create_all yoluyla aynı."""
    engine, temizle = _scratch(admin_engine, "ciplak")
    try:
        _database_engine_ile(engine, database.init_db)
        with engine.connect() as conn:                      # G235 öncesine geri sar
            for index in _INDEXLER:
                conn.execute(text(f"DROP INDEX IF EXISTS {index}"))
            for tablo in _TABLOLAR:
                conn.execute(text(f"DROP TABLE {tablo}"))
            for tablo, kolonlar in _KOLONLAR.items():
                for kolon in kolonlar:
                    conn.execute(text(f"ALTER TABLE {tablo} DROP COLUMN {kolon}"))
            conn.commit()
        assert _g235_semasi(engine) == {"kolonlar": [], "indexler": []}

        _database_engine_ile(engine, database.check_and_migrate_tables)
        ciplak = _g235_semasi(engine)
        assert ciplak == _g235_semasi(kurulu_db)

        _database_engine_ile(engine, database.check_and_migrate_tables)     # idempotent
        assert _g235_semasi(engine) == ciplak
    finally:
        temizle()


def test_kisitlar_veritabaninda_zorlaniyor(kurulu_db):
    Oturum = sessionmaker(bind=kurulu_db)
    db = Oturum()
    try:
        db.execute(text("INSERT INTO sigorta_kisa_kodlari (kod, ad, eslesme_anahtarlari, aktif) "
                        "VALUES ('AXA', 'AXA Sigorta', '[\"AXA\"]', true)"))
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO sigorta_kisa_kodlari (kod, ad, eslesme_anahtarlari, aktif) "
                            "VALUES ('AXA', 'Başka', '[]', true)"))
        db.rollback()

        kart = ("INSERT INTO cases (tracking_no, ofis_no_kodu, ofis_no_sira) VALUES (:no, :kod, :sira)")
        db.execute(text(kart), {"no": "AXA-0001-HUK", "kod": "AXA", "sira": 1})
        db.execute(text(kart), {"no": "ESKI.1", "kod": None, "sira": None})
        db.execute(text(kart), {"no": "ESKI.2", "kod": None, "sira": None})   # NULL'lar çakışmaz
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text(kart), {"no": "AXA-0001-CEZ", "kod": "AXA", "sira": 1})   # aynı kod+sıra
        db.rollback()
    finally:
        db.execute(text("DELETE FROM cases"))
        db.execute(text("DELETE FROM sigorta_kisa_kodlari"))
        db.commit()
        db.close()


# ─── sayaç eşzamanlılığı ─────────────────────────────────────────────────────

def test_sira_tahsis_paralel_baglantilarda_tekil_ve_ardisik(kurulu_db):
    """İki (ve daha çok) bağlantıdan paralel N çağrı → N farklı, ardışık sıra."""
    is_parcacigi, cagri = 4, 25
    Oturum = sessionmaker(bind=kurulu_db)
    baslat = threading.Barrier(is_parcacigi)
    sonuclar: list = []
    hatalar: list = []
    kilit = threading.Lock()

    def kos():
        db = Oturum()                                   # her iş parçacığı KENDİ bağlantısı
        try:
            baslat.wait(timeout=10)
            for _ in range(cagri):
                sira = ofis_no.sira_tahsis_et(db, "AXA")
                db.commit()
                with kilit:
                    sonuclar.append(sira)
        except Exception as exc:                        # pragma: no cover - hata yolunda test kırılır
            with kilit:
                hatalar.append(exc)
        finally:
            db.close()

    parcaciklar = [threading.Thread(target=kos) for _ in range(is_parcacigi)]
    for p in parcaciklar:
        p.start()
    for p in parcaciklar:
        p.join(timeout=60)

    toplam = is_parcacigi * cagri
    assert hatalar == []
    assert sorted(sonuclar) == list(range(1, toplam + 1))
    db = Oturum()
    try:
        assert db.execute(text("SELECT son_sira FROM ofis_no_sayaclari WHERE kod = 'AXA'")).scalar_one() == toplam
        assert ofis_no.siradaki(db, "AXA") == toplam + 1
        assert ofis_no.sira_tahsis_et(db, "DR.M.OZTURK") == 1      # başka kod etkilenmedi
        db.rollback()
    finally:
        db.close()


def test_sira_tahsis_acik_transaction_digerini_bekletir_ayni_sirayi_vermez(kurulu_db):
    """Commit edilmemiş tahsis satırı kilitler: ikinci bağlantı bekler ve SONRAKİ sırayı alır."""
    Oturum = sessionmaker(bind=kurulu_db)
    a, b = Oturum(), Oturum()
    try:
        ilk = ofis_no.sira_tahsis_et(a, "KORU")          # a açık (commit yok)
        ikinci: list = []
        t = threading.Thread(target=lambda: (ikinci.append(ofis_no.sira_tahsis_et(b, "KORU")), b.commit()))
        t.start()
        t.join(timeout=1.0)
        assert t.is_alive() and ikinci == []             # b, a'nın kilidini bekliyor
        a.commit()
        t.join(timeout=10)
        assert not t.is_alive()
        assert ikinci == [ilk + 1]
    finally:
        a.close()
        b.close()
