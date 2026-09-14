"""G191 — bağlantı ve sunucu ayarları (performans denetimi D5, D6).

Kapsam:
- `database._build_connect_args`: statement_timeout + idle_in_transaction_session_timeout
  + lock_timeout seçenekleri; 0 verilen seçenek bağlantıya HİÇ gönderilmez.
- env varsayılanları (60000 / 5000) ve migrate.py muafiyeti (üçü de 0).
- compose `postgres.command:` parametreleri; shared_buffers/work_mem/max_connections
  bilinçli varsayılanda.
- `_ensure_pg_stat_statements`: preload yoksa WARNING + False, uygulama ayakta.
- dbtest (gerçek Postgres, scratch DB; ulaşılamıyorsa fixture SKIP eder):
  * `database` modülünün açtığı bağlantıda ayarlar env değeri, migrate.py yolunda 0;
  * kilit senaryosu: lock_timeout=200 ms → LockNotAvailable 1 sn içinde, havuz rehin
    alınmaz;
  * uzun süren TEK ifade idle sayılmaz (gece aktarımı etkilenmez), gerçek boşta bekleme
    oturumu kestirir.
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

import database
from database import _build_connect_args
from test_migration_path import _scratch_database

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ─── _build_connect_args ─────────────────────────────────────────────────────

def test_connect_args_uc_secenek_sirali():
    args = _build_connect_args(30000, idle_ms=60000, lock_ms=5000)
    assert args["connect_timeout"] == 5
    assert args["options"] == (
        "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000 -c lock_timeout=5000"
    )


@pytest.mark.parametrize(
    ("statement_ms", "idle_ms", "lock_ms", "beklenen"),
    [
        (30000, 0, 5000, "-c statement_timeout=30000 -c lock_timeout=5000"),
        (30000, 60000, 0, "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000"),
        (0, 60000, 0, "-c idle_in_transaction_session_timeout=60000"),
        (0, 0, 5000, "-c lock_timeout=5000"),
    ],
)
def test_connect_args_sifir_verilen_secenek_yok(statement_ms, idle_ms, lock_ms, beklenen):
    args = _build_connect_args(statement_ms, idle_ms=idle_ms, lock_ms=lock_ms)
    assert args["options"] == beklenen


def test_connect_args_hepsi_sifir_options_yok():
    """migrate.py yolu: üçü de 0 → options anahtarı hiç yok."""
    assert _build_connect_args(0, idle_ms=0, lock_ms=0) == {"connect_timeout": 5}


def test_env_varsayilanlari_kaynakta():
    src = (BACKEND_DIR / "database.py").read_text(encoding="utf-8")
    assert 'os.getenv("DB_IDLE_TX_TIMEOUT_MS", "60000")' in src
    assert 'os.getenv("DB_LOCK_TIMEOUT_MS", "5000")' in src
    assert isinstance(database.DB_IDLE_TX_TIMEOUT_MS, int)
    assert isinstance(database.DB_LOCK_TIMEOUT_MS, int)


def test_migrate_yeni_envleri_de_sifirlar():
    import importlib

    import migrate

    importlib.reload(migrate)
    assert os.environ.get("DB_STATEMENT_TIMEOUT_MS") == "0"
    assert os.environ.get("DB_IDLE_TX_TIMEOUT_MS") == "0"
    assert os.environ.get("DB_LOCK_TIMEOUT_MS") == "0"


# Not: compose `postgres.command:` ve `.env.example` burada test EDİLMEZ — konteynerde
# yalnız backend/ mount'lu, repo kökü görünmez. Compose parametreleri canlı sunucuda
# `SHOW` ile doğrulanır (görev raporu); pg_stat_statements'ın preload ile tutarlılığı
# aşağıdaki dbtest'te.

# ─── pg_stat_statements kurulumu (birim) ─────────────────────────────────────

class _ListHandler(logging.Handler):
    """dictConfig caplog'u söküyor — adlandırılmış logger'a doğrudan handler."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture()
def db_logs():
    handler = _ListHandler()
    lg = logging.getLogger("database")
    prev_level = lg.level
    lg.addHandler(handler)
    lg.setLevel(logging.DEBUG)
    yield handler
    lg.removeHandler(handler)
    lg.setLevel(prev_level)


class _FakeConn:
    def __init__(self, patlayan=None):
        self.patlayan = patlayan
        self.sqls = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, clause):
        sql = str(clause)
        self.sqls.append(sql)
        if self.patlayan and self.patlayan in sql:
            raise RuntimeError('pg_stat_statements must be loaded via "shared_preload_libraries"')

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_pg_stat_statements_preload_yoksa_warning_ve_ayakta(db_logs):
    conn = _FakeConn(patlayan="FROM pg_stat_statements")
    assert database._ensure_pg_stat_statements(conn) is False
    assert conn.rollbacks == 1
    assert any("CREATE EXTENSION IF NOT EXISTS pg_stat_statements" in s for s in conn.sqls)
    warnings = [r for r in db_logs.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert [r for r in db_logs.records if r.levelno >= logging.ERROR] == []


def test_pg_stat_statements_basarili_yol(db_logs):
    conn = _FakeConn()
    assert database._ensure_pg_stat_statements(conn) is True
    assert conn.rollbacks == 0
    assert [r for r in db_logs.records if r.levelno >= logging.WARNING] == []


def test_migrasyon_pg_stat_statements_kurar():
    """Bekçi: şema migrasyonunun sonunda uzantı adımı çağrılır."""
    import inspect

    src = inspect.getsource(database.check_and_migrate_tables)
    assert "_ensure_pg_stat_statements(conn)" in src


# ─── dbtest: gerçek Postgres ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg_admin():
    """Bakım bağlantısı (test_migration_path kalıbı); DB yoksa modülün dbtest'leri SKIP."""
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")
    engine = create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G191 dbtest atlandı")
    yield engine
    engine.dispose()


_AYAR_KODU = """
import json
import database
from sqlalchemy import text
with database.engine.connect() as c:
    rows = c.execute(text(
        "SELECT name, setting FROM pg_settings WHERE name IN "
        "('statement_timeout', 'idle_in_transaction_session_timeout', 'lock_timeout')"
    )).all()
print("G191-AYAR " + json.dumps({n: s for n, s in rows}))
"""


def _oturum_ayarlari(pg_admin, migrate_yolu: bool) -> dict:
    """Ayrı süreçte `database` modülünü import edip motorun bağlantısındaki
    oturum ayarlarını okur. migrate_yolu=True → önce `import migrate` (entrypoint
    sırası). Env'de sıfırdan farklı değerler VERİLİR: migrate yolunun 0'ı env'i
    ezerek ürettiği görülsün."""
    env = dict(os.environ)
    env.update(
        DATABASE_URL=pg_admin.url.render_as_string(hide_password=False),
        DB_STATEMENT_TIMEOUT_MS="25000",
        DB_IDLE_TX_TIMEOUT_MS="45678",
        DB_LOCK_TIMEOUT_MS="3456",
    )
    kod = ("import migrate\n" if migrate_yolu else "") + _AYAR_KODU
    sonuc = subprocess.run(
        [sys.executable, "-c", kod],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stderr[-2000:]
    satir = next(s for s in sonuc.stdout.splitlines() if s.startswith("G191-AYAR "))
    return json.loads(satir[len("G191-AYAR "):])


@pytest.mark.dbtest
def test_uygulama_baglantisinda_ayarlar_env_degeri(pg_admin):
    assert _oturum_ayarlari(pg_admin, migrate_yolu=False) == {
        "statement_timeout": "25000",
        "idle_in_transaction_session_timeout": "45678",
        "lock_timeout": "3456",
    }


@pytest.mark.dbtest
def test_migrate_yolundan_acilan_baglantida_ayarlar_sifir(pg_admin):
    assert _oturum_ayarlari(pg_admin, migrate_yolu=True) == {
        "statement_timeout": "0",
        "idle_in_transaction_session_timeout": "0",
        "lock_timeout": "0",
    }


@pytest.mark.dbtest
def test_kilit_bekleyen_update_lock_timeout_ile_hizla_duser(pg_admin):
    with _scratch_database(pg_admin, "g191kilit") as base:
        with base.begin() as conn:
            conn.execute(text("CREATE TABLE g191_kilit (id INT PRIMARY KEY, v INT NOT NULL)"))
            conn.execute(text("INSERT INTO g191_kilit VALUES (1, 0)"))

        tutan = create_engine(base.url, poolclass=NullPool, connect_args=_build_connect_args(0))
        # Tek yuvalı havuz: hata sonrası yuva geri dönmezse ikinci checkout 1 sn'de
        # TimeoutError alır — "havuz rehin alınmaz" bununla ölçülür.
        bekleyen = create_engine(
            base.url,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
            connect_args=_build_connect_args(0, idle_ms=0, lock_ms=200),
        )
        try:
            with tutan.connect() as a:
                a.execute(text("SELECT v FROM g191_kilit WHERE id = 1 FOR UPDATE"))

                bas = time.monotonic()
                with pytest.raises(OperationalError) as info:
                    with bekleyen.begin() as b:
                        b.execute(text("UPDATE g191_kilit SET v = v + 1 WHERE id = 1"))
                gecen = time.monotonic() - bas

                assert gecen < 1.0, f"lock_timeout 200 ms iken {gecen:.2f} sn beklendi"
                assert getattr(info.value.orig, "pgcode", None) == "55P03"  # lock_not_available

                with bekleyen.connect() as b2:
                    assert b2.execute(text("SELECT 1")).scalar() == 1
                a.rollback()

            # Kilit kalkınca aynı havuz yazabiliyor: bağlantı kalıcı bozulmadı.
            with bekleyen.begin() as b3:
                b3.execute(text("UPDATE g191_kilit SET v = v + 1 WHERE id = 1"))
            with tutan.connect() as kontrol:
                assert kontrol.execute(text("SELECT v FROM g191_kilit WHERE id = 1")).scalar() == 1
        finally:
            tutan.dispose()
            bekleyen.dispose()


@pytest.mark.dbtest
def test_uzun_tek_ifade_idle_sayilmaz_bosta_bekleme_kesilir(pg_admin):
    """Gece aktarımı (tek transaction ~93 sn) sürekli ifade koşturur → etkilenmez;
    transaction açıkken ifadesiz beklemek ise oturumu kestirir."""
    with _scratch_database(pg_admin, "g191idle") as base:
        motor = create_engine(
            base.url,
            poolclass=NullPool,
            connect_args=_build_connect_args(0, idle_ms=300, lock_ms=0),
        )
        try:
            # (a) 1 sn'lik TEK ifade, 300 ms'lik sınırın üç katı: aktif → kesilmez.
            with motor.begin() as conn:
                ayar = conn.execute(
                    text("SELECT setting FROM pg_settings WHERE name = 'idle_in_transaction_session_timeout'")
                ).scalar()
                assert ayar == "300"
                conn.execute(text("SELECT pg_sleep(1.0)"))
                assert conn.execute(text("SELECT 1")).scalar() == 1
            # commit başarıyla döndü (begin bloğu istisnasız kapandı)

            # (b) transaction açık, ifade yok, 1.5 sn → sunucu oturumu keser.
            with pytest.raises(OperationalError):
                with motor.connect() as conn:
                    conn.execute(text("SELECT 1"))  # autobegin → transaction açık
                    time.sleep(1.5)
                    conn.execute(text("SELECT 1"))
        finally:
            motor.dispose()


@pytest.mark.dbtest
def test_pg_stat_statements_gercek_sunucuda_preload_ile_tutarli(pg_admin):
    """Preload'lu sunucuda (recreate sonrası compose) uzantı kurulur ve görünüm okunur;
    preload'suz sunucuda (CI çıplak Postgres) False döner ve bağlantı kullanılabilir kalır."""
    with _scratch_database(pg_admin, "g191pgss") as base:
        with base.connect() as conn:
            preload = conn.execute(text("SHOW shared_preload_libraries")).scalar() or ""
            conn.rollback()
            hazir = database._ensure_pg_stat_statements(conn)
            assert hazir is ("pg_stat_statements" in preload)
            if hazir:
                assert conn.execute(text("SELECT count(*) FROM pg_stat_statements")).scalar() >= 0
            assert conn.execute(text("SELECT 1")).scalar() == 1
