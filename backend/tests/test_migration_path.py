"""Migrasyon YOLU testi — gerçek Postgres'e karşı (G031).

`tests/test_migrations_drop.py` yalnız `_MIGRATIONS` listesinin iç tutarlılığını
kilitler (gerçek DB yok). Bu dosya tamamlayıcısıdır: sıfırdan boş bir
veritabanında `init_db()` gerçekten koşturulur, sonuç `information_schema` /
`pg_indexes` üzerinden ölçülür.

Çalışma şekli:

* Bağlantı `MIGRATION_TEST_DATABASE_URL` yoksa `DATABASE_URL`'den okunur.
  conftest.py'nin dummy URL'ine DOKUNULMAZ — buradaki engine ayrıdır.
* Her test kendi **scratch** veritabanını yaratır (`hukudok_migtest_*`) ve
  sonunda — hata yolunda da — düşürür. Gerçek veritabanına asla yazılmaz;
  `_assert_safe_scratch_name` bunu isim düzeyinde zorlar.
* **DB'ye ulaşılamıyorsa testler SKIP olur, FAIL değil** — konteynersiz saf
  birim koşusu yeşil kalmalı.

Marker: `dbtest` (pyproject.toml'da kayıtlı). İşaretsiz koşuda da çalışırlar;
dışlamak için `-m "not dbtest"`.

DİKKAT — `test_table_op_index_sqlleri_bugun_hic_calismiyor` BUGÜNKÜ KUSURU
iddia eder (xfail değil, geçen bir assertion). FAZ D 6.1 kusuru düzeltince o
test bilinçli olarak TERS ÇEVRİLECEK; ayrıntı testin docstring'inde.
"""
import os
import re
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

import database

pytestmark = pytest.mark.dbtest

_SCRATCH_PREFIX = "hukudok_migtest_"

_INDEX_NAME_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


# ─── yardımcılar ─────────────────────────────────────────────────────────────

def _index_names(sqls):
    """SQL listesindeki CREATE INDEX ifadelerinden index adlarını çıkarır."""
    names = []
    for sql in sqls:
        match = _INDEX_NAME_RE.search(sql)
        if match:
            names.append(match.group(1))
    return names


def _table_op_index_names():
    """`("table", ...)` op'larının 4. elemanındaki index adları."""
    names = []
    for op in database._MIGRATIONS:
        if op[0] == "table":
            names.extend(_index_names(op[3]))
    return names


def _columns_op_post_index_names():
    """`("columns", ...)` op'larının post-SQL'lerindeki index adları.

    Spec `(DDL, [post SQL, ...])` biçimindeyse post SQL'ler YALNIZ kolon
    gerçekten eklendiğinde koşar (database.py:570-573).
    """
    names = []
    for op in database._MIGRATIONS:
        if op[0] != "columns":
            continue
        for spec in op[2].values():
            if not isinstance(spec, str):
                names.extend(_index_names(spec[1]))
    return names


def _assert_safe_scratch_name(name: str, real_db: str) -> None:
    """DROP/CREATE DATABASE yalnız scratch adlarında serbest.

    Gerçek `hukudok` veritabanına dokunmama kabul kriteridir; koruma isim
    düzeyinde ve testten bağımsız doğrulanabilir olsun diye ayrı fonksiyonda.
    """
    if not name.startswith(_SCRATCH_PREFIX) or name == real_db:
        raise RuntimeError(
            f"Güvenlik: '{name}' scratch veritabanı adı değil (gerçek: '{real_db}') — "
            "DROP/CREATE DATABASE reddedildi"
        )


def _live_columns(engine):
    """{tablo: {kolon, ...}} — public şemadaki mevcut kolonlar."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )).all()
    result: dict = {}
    for table, column in rows:
        result.setdefault(table, set()).add(column)
    return result


def _live_indexes(engine):
    """{index_adı: tanım} — public şemadaki mevcut index'ler."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"
        )).all()
    return {name: definition for name, definition in rows}


def _schema_snapshot(engine):
    """İdempotency karşılaştırması için deterministik şema fotoğrafı."""
    with engine.connect() as conn:
        columns = conn.execute(text("""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, column_name
        """)).all()
        indexes = conn.execute(text("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY indexname
        """)).all()
    return {
        "columns": [tuple(row) for row in columns],
        "indexes": [tuple(row) for row in indexes],
    }


def _run_init_db(engine):
    """init_db() modül-global `engine`'i kullanır → yalnız çağrı boyunca değiştir."""
    original = database.engine
    database.engine = engine
    try:
        database.init_db()
    finally:
        database.engine = original


@contextmanager
def _scratch_database(admin_engine, suffix):
    """Boş bir scratch veritabanı yaratır, engine'ini verir, sonunda düşürür."""
    base_url = admin_engine.url          # URL nesnesi: parola maskelenmez
    name = f"{_SCRATCH_PREFIX}{os.getpid()}_{suffix}"
    _assert_safe_scratch_name(name, base_url.database)

    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    engine = create_engine(
        base_url.set(database=name),
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        yield engine
    finally:
        # Teardown hata yolunda da koşar: açık bağlantılar kesilir, DB düşer.
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


# ─── fixture'lar ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_engine():
    """CREATE/DROP DATABASE için bakım bağlantısı; DB yoksa tüm modül SKIP."""
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")

    engine = create_engine(
        url,
        isolation_level="AUTOCOMMIT",   # CREATE/DROP DATABASE transaction içinde çalışmaz
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — migrasyon yolu testi atlandı")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def fresh_db(admin_engine):
    """Boş scratch DB üzerinde bir kez init_db() koşmuş engine."""
    with _scratch_database(admin_engine, "fresh") as engine:
        _run_init_db(engine)
        yield engine


# ─── testler ─────────────────────────────────────────────────────────────────

def test_scratch_isim_korumasi_gercek_veritabanini_reddeder():
    """Gerçek veritabanına DROP/CREATE gitmesini isim düzeyinde engelle (DB gerekmez)."""
    with pytest.raises(RuntimeError):
        _assert_safe_scratch_name("hukudok", "hukudok")
    with pytest.raises(RuntimeError):
        _assert_safe_scratch_name("hukudok_test", "hukudok")
    with pytest.raises(RuntimeError):
        _assert_safe_scratch_name(f"{_SCRATCH_PREFIX}1_fresh", f"{_SCRATCH_PREFIX}1_fresh")
    # Meşru ad: prefix'li ve gerçek veritabanından farklı
    _assert_safe_scratch_name(f"{_SCRATCH_PREFIX}1_fresh", "hukudok")


def test_bos_veritabaninda_tum_migrasyon_adimlari_uygulaniyor(fresh_db):
    """Sıfırdan kurulum: her op'un sonucu şemada gerçekten var mı?

    Adım SAYISI (2026-08-12: 39) bilinçli olarak assert EDİLMEZ — yeni migrasyon
    eklendiğinde kırılan bir sayaç değil, her op'u tek tek doğrulayan bir kontrol
    isteniyor. `rename` op'u burada kapsam dışıdır: sıfırdan kurulumda eski kolon
    adları hiç oluşmaz, dolayısıyla rename adımı bilinçli olarak atlanır.
    """
    columns = _live_columns(fresh_db)
    indexes = _live_indexes(fresh_db)

    eksik = []
    for op in database._MIGRATIONS:
        kind, table = op[0], op[1]
        if kind == "columns":
            for column in op[2]:
                if column not in columns.get(table, set()):
                    eksik.append(f"kolon {table}.{column}")
        elif kind == "table":
            if table not in columns:
                eksik.append(f"tablo {table}")
        elif kind == "drop":
            for column in op[2]:
                if column in columns.get(table, set()):
                    eksik.append(f"{table}.{column} drop edilmemiş")
        elif kind == "index":
            for index_name in _index_names(op[2]):
                if index_name not in indexes:
                    eksik.append(f"index {index_name}")

    assert not eksik, "init_db() sonrası eksik migrasyon çıktıları: " + ", ".join(eksik)


def test_ikinci_init_db_kosusu_semayi_degistirmiyor(fresh_db):
    """İdempotency: aynı DB'de ikinci koşu hata vermez ve şemayı oynatmaz."""
    before = _schema_snapshot(fresh_db)
    _run_init_db(fresh_db)          # hata fırlatırsa test kırmızı olur
    after = _schema_snapshot(fresh_db)

    assert after["columns"] == before["columns"], "ikinci koşu kolonları değiştirdi"
    assert after["indexes"] == before["indexes"], "ikinci koşu index'leri değiştirdi"


def test_table_op_index_sqlleri_bugun_hic_calismiyor(fresh_db):
    """BUGÜNKÜ KUSURU KİLİTLER — FAZ D 6.1 düzeltince TERS ÇEVRİLECEK.

    `("table", ...)` op'ları `if table in tables: continue` ile korunuyor;
    `tables` ise `init_db()`'nin ÖNCE koşturduğu `create_all()`'dan sonra
    okunuyor. İlgili tabloların hepsi models.py'de tanımlı olduğu için
    create_all onları zaten yaratır → op atlanır → op'a iliştirilmiş
    `CREATE INDEX` ifadeleri HİÇ çalışmaz. (Bu index'lerin models.py'de
    karşılığı da yok, yani hiçbir yoldan oluşmuyorlar.)

    FAZ D 6.1 bunu düzelttiğinde: bu testi silmek yerine assertion'ı ters
    çevirin (index'ler artık OLUŞMALI) — kusurun geri gelmesini yakalar.
    """
    olmamasi_gerekenler = _table_op_index_names()
    assert olmamasi_gerekenler, "table op'larında hiç index SQL'i yok — test anlamsızlaştı"
    # Görev dosyasındaki somut örnekler listede gerçekten var mı?
    assert "idx_case_relations_source" in olmamasi_gerekenler
    assert "idx_export_outbox_status" in olmamasi_gerekenler

    indexes = _live_indexes(fresh_db)
    olusanlar = sorted(name for name in olmamasi_gerekenler if name in indexes)
    assert olusanlar == [], (
        "Bu index'ler artık oluşuyor: " + ", ".join(olusanlar) + ". Kusur düzeltilmişse "
        "bu testi ters çevirin (bkz. docstring, FAZ D 6.1)."
    )


def test_columns_op_post_index_sqlleri_bugun_hic_calismiyor(fresh_db):
    """AYNI KUSURUN İKİNCİ YÜZÜ — FAZ D 6.1 ile birlikte TERS ÇEVRİLECEK.

    `("columns", ...)` op'unda `(DDL, [post SQL])` biçimindeki spec'lerin post
    SQL'leri yalnız kolon GERÇEKTEN eklendiğinde koşar. Sıfırdan kurulumda
    kolonu create_all zaten yarattığı için op atlanır → post SQL'ler hiç
    çalışmaz. Ölçüldü (2026-08-12): 10 index'in tamamı oluşmuyor.

    En kritiği `uq_cases_sistem_no`: sıfırdan kurulan bir veritabanında
    cases.sistem_no TEKİLLİĞİ ZORLANMAZ (models.py'de unique=True yok).
    Mevcut prod veritabanında index var (kolon oraya migrasyonla eklenmişti).
    """
    beklenen_yok = _columns_op_post_index_names()
    assert beklenen_yok, "columns op'larında hiç post index SQL'i yok — test anlamsızlaştı"
    assert "uq_cases_sistem_no" in beklenen_yok

    indexes = _live_indexes(fresh_db)
    olusanlar = sorted(name for name in beklenen_yok if name in indexes)
    assert olusanlar == [], (
        "Bu post-SQL index'leri artık oluşuyor: " + ", ".join(olusanlar) +
        ". Kusur düzeltilmişse bu testi ters çevirin (bkz. docstring, FAZ D 6.1)."
    )


def test_trigram_indexleri_sifirdan_kurulumda_olusuyor(fresh_db):
    """pg_trgm bloğu tablo/kolon varlığına baktığı için sıfırdan kurulumda ÇALIŞIR.

    Kusurlu iki yolun (table op / columns post-SQL) aksine bu adım sağlıklı —
    karşılaştırma noktası olarak kilitlenir.
    """
    indexes = _live_indexes(fresh_db)
    eksik = sorted(name for name in database._TRGM_INDEXES if name not in indexes)
    assert eksik == [], "trigram index'leri oluşmadı: " + ", ".join(eksik)


def test_create_all_mevcut_tabloya_index_eklemiyor(admin_engine):
    """Sıfırdan kurulum ≠ büyümüş şema.

    `create_all()` var olan tabloyu atlar; models.py'deki `index=True`
    karşılıkları o tabloya SONRADAN eklenmez. Prod'da `ix_clients_name`
    bu yüzden yok. Boş scratch DB'de create_all index'i yaratacağı için
    fark ancak `clients` tablosu ÖNCEDEN (index'siz) yaratılarak gösterilebilir:
    `CreateTable` yalnız CREATE TABLE üretir, index'ler ayrı DDL'dir.

    Ters yön de aynı testte: `("index", "clients", ...)` op'u mevcut tabloya
    index eklemeyi BAŞARIR — yani boşluk create_all'a özgüdür, migrasyon
    mekanizmasının tamamına değil.
    """
    import models

    with _scratch_database(admin_engine, "preexisting") as engine:
        with engine.begin() as conn:
            conn.execute(CreateTable(models.Client.__table__))

        onceki = _live_indexes(engine)
        assert "ix_clients_name" not in onceki, "CreateTable index de üretmiş — test kurgusu geçersiz"

        _run_init_db(engine)

        columns = _live_columns(engine)
        indexes = _live_indexes(engine)

        # create_all mevcut clients tablosuna models.py index'ini EKLEMEDİ
        assert "ix_clients_name" not in indexes, (
            "create_all mevcut tabloya index eklemiş — bu testin dayandığı davranış değişti"
        )
        # Ama migrasyonun kendi ("index", "clients", ...) op'u mevcut tabloya
        # index eklemeyi başardı — boşluk yalnız create_all tarafında.
        assert "idx_clients_tc_no" in indexes
        # Diğer tablolar normal kuruldu (kurulum yarıda kalmadı)
        assert "cases" in columns
        assert "tenant_id" in columns["clients"]
