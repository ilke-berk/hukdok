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

TARİHÇE — G031'de bu dosya iki testle BUGÜNKÜ KUSURU kilitliyordu (`("table", ...)`
ve `("columns", ...)` op'larına iliştirilmiş index SQL'lerinin sıfırdan kurulumda
hiç koşmaması). FAZ D 6.1 (G041) birincisini düzeltti: ilgili test ters çevrildi
(`test_table_op_index_niyetleri_semada_karsilikli`) ve ADI değil KAPSAMAYI —
(tablo, kolonlar, unique, kısmi) imzasını — kilitliyor. İkincisi düzeltilmedi,
DARALTILDI: iddiası "hiç çalışmıyor" değil, "yalnız kolon sonradan eklendiğinde
çalışıyor"dur; her iki yön de test edilir.
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

# Hem migrasyondaki DDL'i hem pg_indexes.indexdef'i ayrıştırır: tek fark
# "USING btree" parçasıdır (opsiyonel). Bilinçli olarak database.py'nin kendi
# ayrıştırıcısından BAĞIMSIZ — üretim kodunu kendi regex'iyle doğrulamak
# kendini onaylayan bir test olurdu.
_INDEX_SIG_RE = re.compile(
    r"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"\w]+\s+"
    r"ON\s+(?:[\"\w]+\.)?(?P<table>[\"\w]+)\s*(?:USING\s+\w+\s*)?"
    r"\((?P<cols>[^()]*)\)\s*(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)

_TABLE_UNIQUE_RE = re.compile(
    r"CONSTRAINT\s+(?P<name>\w+)\s+UNIQUE\s*\((?P<cols>[^()]*)\)", re.IGNORECASE
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


def _index_signature(sql):
    """(tablo, (kolon,...), unique?, kısmi?) — index'in ADDAN BAĞIMSIZ kimliği.

    G041 kararı: tablo op'larındaki üç index kalemi mevcut kurulumlarda BAŞKA
    adla (modeldeki `index=True`nin ürettiği `ix_*`) zaten var. Aynı kolona
    ikinci bir index eklemek yerine kapsama üzerinden doğrularız.
    """
    match = _INDEX_SIG_RE.match(sql.strip())
    if not match:
        return None
    columns = []
    for raw in match.group("cols").split(","):
        parts = raw.strip().strip('"').split()
        if not parts:                        # boş kolon listesi → ayrıştırılamadı
            return None
        columns.append(parts[0].strip('"').lower())   # DESC/ASC/opclass atılır
    return (
        match.group("table").strip('"').lower(),
        tuple(columns),
        bool(match.group("unique")),
        bool(match.group("rest").strip().rstrip(";")),   # WHERE → kısmi index
    )


def _live_index_signatures(engine):
    """{imza: [index adı, ...]} — şemada gerçekten var olan index'ler."""
    signatures: dict = {}
    for name, definition in _live_indexes(engine).items():
        signature = _index_signature(definition)
        if signature:
            signatures.setdefault(signature, []).append(name)
    return signatures


def _table_op_index_names():
    """`("table", ...)` op'larının 4. elemanındaki index adları."""
    names = []
    for op in database._MIGRATIONS:
        if op[0] == "table":
            names.extend(_index_names(op[3]))
    return names


def _table_op_unique_constraints():
    """`("table", ...)` CREATE gövdesindeki `CONSTRAINT x UNIQUE (...)` kalemleri."""
    found = []
    for op in database._MIGRATIONS:
        if op[0] != "table":
            continue
        for match in _TABLE_UNIQUE_RE.finditer(op[2]):
            columns = tuple(c.strip().lower() for c in match.group("cols").split(","))
            found.append((op[1], match.group("name"), columns))
    return found


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


def test_table_op_index_niyetleri_semada_karsilikli(fresh_db):
    """G031'in kilitlediği kusurun TERSİ (FAZ D 6.1 / G041).

    `("table", ...)` op'ları `if table in tables: continue` ile korunur ve
    `tables`, `init_db()`'nin ÖNCE koşturduğu `create_all()`'dan sonra okunur →
    modelde tanımlı tablolarda op atlanır, gövdesindeki `CREATE INDEX` ifadeleri
    o kurulumda hiç koşmaz. G041 bu kalemleri koşulsuz çalışan `("index", ...)`
    op'una taşıdı.

    Doğrulama ADLA DEĞİL KAPSAMAYLA yapılır: üç kalem (idx_stage_logs_case,
    idx_export_outbox_status, idx_client_policies_client) mevcut kurulumlarda
    modelin `index=True` karşılığı sayesinde BAŞKA ADLA zaten vardı; aynı kolona
    ikinci index eklemek mükerrer üretirdi (G041 kararı, database.py madde 28).
    Aranan şey "şu adlı index" değil, "şu tablo+kolonlar üzerinde bir index".
    """
    hedefler = []
    for op in database._MIGRATIONS:
        if op[0] != "table":
            continue
        for sql in op[3]:
            signature = _index_signature(sql)
            assert signature, f"index SQL'i ayrıştırılamadı: {sql}"
            hedefler.append((sql, signature))
    assert hedefler, "table op'larında hiç index SQL'i yok — test anlamsızlaştı"
    # G041 görev dosyasındaki somut örnekler gerçekten bu listede mi?
    assert "idx_case_relations_source" in _table_op_index_names()
    assert "idx_export_outbox_status" in _table_op_index_names()

    canli = _live_index_signatures(fresh_db)
    karsiliksiz = sorted(sql.strip() for sql, signature in hedefler if signature not in canli)
    assert karsiliksiz == [], (
        "Bu tablo-op index niyetlerinin şemada karşılığı yok:\n  " + "\n  ".join(karsiliksiz)
    )


def test_table_op_unique_kisitlari_semada_karsilikli(fresh_db):
    """Tablo op'larının gövdesindeki `CONSTRAINT ... UNIQUE (...)` kalemleri.

    Index'lerle aynı sebeple hiç koşmuyorlardı; G041 ikisini de
    `CREATE UNIQUE INDEX IF NOT EXISTS` olarak taşıdı (ALTER TABLE ADD
    CONSTRAINT idempotent değil, ikinci koşuda patlardı). PG unique kısıtı
    zaten unique index ile uyguladığı için kapsama denk.
    """
    kisitlar = _table_op_unique_constraints()
    assert kisitlar, "table op'larında hiç UNIQUE kısıt yok — test anlamsızlaştı"
    assert {name for _, name, _ in kisitlar} >= {"uq_case_relation", "uq_daily_report"}

    canli = _live_index_signatures(fresh_db)
    eksik = [
        f"{name} → {table}({', '.join(columns)})"
        for table, name, columns in kisitlar
        if (table, columns, True, False) not in canli
    ]
    assert eksik == [], "Bu UNIQUE kısıtların şemada karşılığı yok: " + ", ".join(eksik)


def test_columns_op_post_sqlleri_yalnizca_kolon_sonradan_eklendiginde_kosuyor(fresh_db):
    """G031'in ikinci testi — DARALTILDI (FAZ D 6.1 kararı, G041).

    Eski adı `..._bugun_hic_calismiyor` idi ve YANILTICIYDI: post SQL'ler
    "hiç" değil, "kolon create_all tarafından zaten yaratılmışsa"
    çalışmıyor. Kolon gerçekten sonradan eklendiğinde koşuyorlar — prod'da
    ölçüldü (idx_clients_tenant, idx_clients_deleted_at mevcut), ters yönü
    `test_columns_op_post_sqli_kolon_eklendiginde_kosuyor` kanıtlıyor.

    Bu test kalan gerçek boşluğu kilitler: SIFIRDAN kurulan bir veritabanında
    10 post-SQL index'inin hiçbiri oluşmaz. En kritiği `uq_cases_sistem_no` —
    yeni bir kurulumda cases.sistem_no TEKİLLİĞİ ZORLANMAZ (models.py'de
    unique=True yok). G041 kapsamı tablo op'larıydı; bu kalem FAZ D'nin index
    görevine (G043) devredildi, kapanınca bu testin de yönü çevrilmeli.
    """
    beklenen_yok = _columns_op_post_index_names()
    assert beklenen_yok, "columns op'larında hiç post index SQL'i yok — test anlamsızlaştı"
    assert "uq_cases_sistem_no" in beklenen_yok

    indexes = _live_indexes(fresh_db)
    olusanlar = sorted(name for name in beklenen_yok if name in indexes)
    assert olusanlar == [], (
        "Bu post-SQL index'leri sıfırdan kurulumda artık oluşuyor: " + ", ".join(olusanlar) +
        ". Boşluk kapandıysa bu testi ters çevirin (bkz. docstring, G043)."
    )


def test_columns_op_post_sqli_kolon_eklendiginde_kosuyor(admin_engine):
    """Yukarıdaki testin TERS YÖNÜ: mekanizma bozuk değil, koşulu dar.

    `clients` tablosu `tenant_id` kolonu OLMADAN önceden yaratılır; init_db
    kolonu ekler ve spec'in post SQL'i (idx_clients_tenant) koşar. Bu ayrım
    olmadan "post SQL'ler çalışmıyor" cümlesi mekanizmayı haksız yere suçlar.
    """
    import models

    with _scratch_database(admin_engine, "colpost") as engine:
        with engine.begin() as conn:
            conn.execute(CreateTable(models.Client.__table__))
            conn.execute(text("ALTER TABLE clients DROP COLUMN tenant_id"))

        assert "idx_clients_tenant" not in _live_indexes(engine)

        _run_init_db(engine)

        assert "tenant_id" in _live_columns(engine)["clients"]
        assert "idx_clients_tenant" in _live_indexes(engine), (
            "kolon sonradan eklendiği halde post SQL koşmadı"
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
    mekanizmasının tamamına değil. G041 `ix_clients_name`'i tam da bu yüzden
    "index" op'una taşıdı: create_all'ın kapatamadığı boşluğu migrasyon kapatır.
    """
    import models

    with _scratch_database(admin_engine, "preexisting") as engine:
        with engine.begin() as conn:
            conn.execute(CreateTable(models.Client.__table__))

        onceki = _live_indexes(engine)
        assert "ix_clients_name" not in onceki, "CreateTable index de üretmiş — test kurgusu geçersiz"

        # create_all TEK BAŞINA mevcut tabloya models.py index'ini eklemiyor —
        # G041 sonrası bu davranış init_db üzerinden ölçülemez (migrasyon kapatıyor).
        database.Base.metadata.create_all(bind=engine)
        assert "ix_clients_name" not in _live_indexes(engine), (
            "create_all mevcut tabloya index eklemiş — bu testin dayandığı davranış değişti"
        )

        _run_init_db(engine)

        columns = _live_columns(engine)
        indexes = _live_indexes(engine)

        # G041: migrasyonun "index" op'u create_all'ın bıraktığı boşluğu kapatıyor.
        # Prod'da ix_clients_name'in yokluğunun sebebi tam olarak bu boşluktu.
        assert "ix_clients_name" in indexes, (
            "ix_clients_name migrasyonla da oluşmadı — G041'in kapattığı boşluk geri geldi"
        )
        # Migrasyonun kendi ("index", "clients", ...) op'u mevcut tabloya index ekler
        assert "idx_clients_tc_no" in indexes
        # Diğer tablolar normal kuruldu (kurulum yarıda kalmadı)
        assert "cases" in columns
        assert "tenant_id" in columns["clients"]


def test_esas_geri_donusu_kismi_unique_kisitini_ihlal_etmiyor(admin_engine):
    """G049 — `sync_current_esas` GERÇEK Postgres'te, gerçek kısıtla.

    G045 denetimi burada patlamıştı: `uq_case_esas_current` kısmi unique
    index'i yalnız MİGRASYONDA tanımlıdır, sqlite birim testleri ise
    `create_all` ile kurulur — kısıt harness'ın kör noktasındaydı ve tarihçedeki
    daha eski bir esasa GERİ DÖNÜŞ prod'da `duplicate key ...
    uq_case_esas_current` ile 500 üretirken testler yeşildi. (Kör noktanın
    kendisi de kapandı: test_g045 fixture'ı artık migrasyon index'lerini
    sqlite'a uyguluyor — bu test onun Postgres'teki ikizi ve son sözü.)

    Üç geçiş sırası da denenir: ileri (yeni numara), geri (tarihçedeki eski
    numara — patlayan yol), tekrar (aynı numaranın yeniden yazımı, aktarımın
    idempotency şartı). Her adımdan sonra "dava başına en fazla bir güncel
    satır + kolon o satırın kopyası" invariantı doğrulanır.

    Postgres'siz ortamda `admin_engine` fixture'ı tüm modülü sebebiyle birlikte
    SKIP eder ("Gerçek Postgres'e ulaşılamadı ...") — bu test sqlite'ta
    KOŞULAMAZ, çünkü ölçtüğü şey tam olarak migrasyonla kurulan şemadır.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import sessionmaker

    import models
    from managers.case_manager import sync_current_esas

    with _scratch_database(admin_engine, "esascurrent") as engine:
        _run_init_db(engine)
        assert "uq_case_esas_current" in _live_indexes(engine), (
            "kısmi unique index kurulmamış — bu testin ölçtüğü şey yok"
        )

        session = sessionmaker(bind=engine, autoflush=False)()
        try:
            case = models.Case(tracking_no="HA.G049.0001.2026", status="DERDEST")
            session.add(case)
            session.flush()

            def _uygula(esas_no):
                """Esası yazar, commit eder, invariantı doğrular, tarihçeyi döner."""
                sync_current_esas(session, case, esas_no, source="g049-test")
                session.commit()
                rows = (
                    session.query(models.CaseEsasNumber)
                    .filter(models.CaseEsasNumber.case_id == case.id)
                    .order_by(models.CaseEsasNumber.id)
                    .all()
                )
                guncel = [r.esas_no for r in rows if r.is_current]
                assert len(guncel) <= 1, f"birden çok güncel satır: {guncel}"
                assert guncel == [case.esas_no], (
                    f"kolon={case.esas_no!r} ile güncel satır {guncel} ayrıştı"
                )
                return [(r.esas_no, bool(r.is_current)) for r in rows]

            # 1. ileri — ilk satır
            assert _uygula("2017/325") == [("2017/325", True)]
            # 2. ileri — yeni numara, eskisi tarihçede kalır
            assert _uygula("2024/145") == [("2017/325", False), ("2024/145", True)]
            # 3. GERİ — hedefin id'si KÜÇÜK; G045'te tam burada patlıyordu
            assert _uygula("2017/325") == [("2017/325", True), ("2024/145", False)]
            # 4. TEKRAR — idempotency: yeni satır açılmaz, kısıt yine tutar
            assert _uygula("2017/325") == [("2017/325", True), ("2024/145", False)]

            case_id = case.id
        finally:
            session.close()

        # Kısıt yalnız akışı değil, doğrudan INSERT'i de reddetmeli: aktarım
        # scriptleri `sync_current_esas`i atlarsa son savunma budur.
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO case_esas_numbers (case_id, esas_no, stage, is_current) "
                        "VALUES (:case_id, '2030/1', 'YEREL', true)"
                    ),
                    {"case_id": case_id},
                )


def test_unique_index_mukerrer_veride_anlasilir_hatayla_duruyor(admin_engine):
    """Savunmacı UNIQUE (G041): ham PG hatası yerine tablo/kolon/grup sayısı.

    Mükerrer varken migrasyonun DURMASI kasıtlıdır (sessizce atlamak şemayı
    sessizce saptırırdı); denetlenen şey duruşun anlaşılırlığıdır. NULL'lu
    satırlar yanlış alarm üretmemeli: PG'de çoklu NULL unique index'i ihlal
    etmez, oysa GROUP BY NULL'ları eşit sayar.
    """
    with _scratch_database(admin_engine, "uqguard") as engine:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (a INTEGER, b INTEGER)"))
            conn.execute(text("INSERT INTO t (a, b) VALUES (1, 1), (1, 1), (2, 2)"))

        sql = "CREATE UNIQUE INDEX IF NOT EXISTS uq_t_ab ON t (a, b)"
        with engine.connect() as conn:
            rapor = database._unique_index_duplicate_report(conn, sql)
            assert rapor is not None
            assert "uq_t_ab" in rapor and "t(a, b)" in rapor
            assert "1 mükerrer grup" in rapor
            assert "×2" in rapor, "örnek anahtar/adet raporda yok: " + rapor

            # NULL'lar mükerrer sayılmaz
            conn.execute(text("DELETE FROM t WHERE a = 1"))
            conn.execute(text("INSERT INTO t (a, b) VALUES (NULL, NULL), (NULL, NULL)"))
            conn.commit()
            assert database._unique_index_duplicate_report(conn, sql) is None

            # Index gerçekten yaratılabiliyor ve ikinci çağrıda kontrol atlanıyor
            conn.execute(text(sql))
            conn.commit()
            assert database._unique_index_duplicate_report(conn, sql) is None


def test_mukerrer_veride_migrasyon_fail_fast_duruyor(admin_engine, monkeypatch):
    """Kontrol gerçekten migrasyon yoluna bağlı mı — konteyner kalkmamalı.

    `_unique_index_duplicate_report`'un tek başına doğru cevap vermesi yetmez;
    `check_and_migrate_tables` onu "index" op'undan ÖNCE çağırmazsa savunma
    ölü koddur.
    """
    with _scratch_database(admin_engine, "uqstop") as engine:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE dup_probe (a INTEGER)"))
            conn.execute(text("INSERT INTO dup_probe (a) VALUES (5), (5)"))

        monkeypatch.setattr(database, "_MIGRATIONS", [
            ("index", "dup_probe",
             ["CREATE UNIQUE INDEX IF NOT EXISTS uq_dup_probe ON dup_probe (a)"]),
        ])
        monkeypatch.setattr(database, "engine", engine)

        with pytest.raises(RuntimeError, match="mükerrer grup"):
            database.check_and_migrate_tables()

        assert "uq_dup_probe" not in _live_indexes(engine)
