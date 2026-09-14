"""Index envanteri + temizlik listesi testleri (FAZ D 6.2, G042).

İki katman:

* **DB'siz birim testleri** — `scripts/index_envanteri.py`'nin sınıflandırma
  kuralı (unique/primary zorunlu dışlama, ikiz tespiti) ve `database.py`'deki
  düşürme listesinin iç tutarlılığı. Her ortamda koşar.
* **`dbtest` testleri** — gerçek Postgres'te scratch veritabanı üzerinde:
  sahte bir UNIQUE index listeye GİRMİYOR, `ix_cases_tracking_no` listede YOK,
  düşürülen PK ikizlerinin KAPSAMASI şemada duruyor.

Scratch DB altyapısı `test_migration_path.py`'den yeniden kullanılır (gerçek
`hukudok` veritabanına asla yazılmaz; DB yoksa SKIP).
"""
import pytest

import database
from scripts.index_envanteri import (
    ADAY_IKIZ,
    KORUMALI_UNIQUE,
    IndexInfo,
    classify,
    collect_indexes,
    safe_drop_candidates,
)
from test_migration_path import (  # noqa: F401 — fixture'lar pytest tarafından toplanır
    _live_indexes,
    _run_init_db,
    _scratch_database,
    admin_engine,
)


def _index(name, table="t", **kwargs):
    """Varsayılanı 'sıradan, taranmamış btree' olan IndexInfo kurucusu."""
    alan = dict(
        table_name=table, index_name=name, is_unique=False, is_primary=False,
        indkey="1", indclass="1978", indcollation="0", indoption="0",
        access_method="btree", predicate="", expressions="",
        size_bytes=8192, idx_scan=0, index_oid=hash(name) % 100000,
        has_constraint=False, indexdef=f"CREATE INDEX {name} ON t (c)",
    )
    alan.update(kwargs)
    return IndexInfo(**alan)


def _tum_dusurulecekler():
    return [ad for adlar in database._DUSURULECEK_INDEXLER.values() for ad in adlar]


# ─── DB'siz: sınıflandırma kuralı ────────────────────────────────────────────

def test_unique_index_hic_taranmamis_olsa_bile_adaya_girmez():
    """PAZARLIKSIZ KURAL — `ix_cases_tracking_no` senaryosunun birim karşılığı.

    UNIQUE kısıt doğrulaması `idx_scan`'i artırmaz; kusursuz çalışan bir unique
    index ömrü boyunca 0 görünür. Ölçüt `idx_scan` DEĞİL `indisunique` olmalı.
    """
    tekil = _index("ux_tekil", is_unique=True, idx_scan=0, has_constraint=False)
    siradan = _index("ix_siradan", indkey="2", idx_scan=0)

    classify([tekil, siradan])

    assert tekil.verdict == KORUMALI_UNIQUE
    assert tekil.guards_uniqueness_alone, "pg_constraint karşılığı yok → tekilliği tek başına tutuyor"
    assert [i.index_name for i in safe_drop_candidates([tekil, siradan])] == ["ix_siradan"]


def test_primary_key_adaya_girmez_ikizi_girer():
    """PK ikizi: aynı imzalı non-unique index düşer, PK'nın kendisi kalır."""
    pk = _index("t_pkey", is_unique=True, is_primary=True, has_constraint=True, idx_scan=0)
    ikiz = _index("ix_t_id", idx_scan=999)

    classify([pk, ikiz])

    assert pk.verdict == KORUMALI_UNIQUE
    assert ikiz.verdict == ADAY_IKIZ, "çok taransa bile birebir ikiz — tarama PK'ya geçer"
    assert [i.index_name for i in safe_drop_candidates([pk, ikiz])] == ["ix_t_id"]


def test_ikiz_grubunda_yalniz_bir_index_dusurulur():
    """İki non-unique ikizden EN ÇOK TARANAN kalır; ikisi birden düşmez."""
    sicak = _index("idx_sicak", idx_scan=1_810_671)
    soguk = _index("ix_soguk", idx_scan=0)

    classify([sicak, soguk])

    assert [i.index_name for i in safe_drop_candidates([sicak, soguk])] == ["ix_soguk"]


def test_ayni_kolonun_farkli_access_methodu_ikiz_sayilmaz():
    """`idx_cases_tku_no` (btree) ile `idx_cases_tku_no_trgm` (GIN) aynı kolonu tutar.

    İmza access method'u içermeseydi biri "ikiz" diye düşürülür, `ILIKE '%x%'`
    ile `= 'x'` sorgularından biri index'siz kalırdı.
    """
    btree = _index("idx_tku", idx_scan=5)
    gin = _index("idx_tku_trgm", access_method="gin", indclass="16385", idx_scan=5)

    classify([btree, gin])

    assert safe_drop_candidates([btree, gin], include_unscanned=False) == []


def test_kismi_index_tam_index_ile_ikiz_sayilmaz():
    """Kısmi index (WHERE ...) farklı satır kümesini tutar — ikiz değildir."""
    tam = _index("idx_tam", idx_scan=3)
    kismi = _index("idx_kismi", predicate="(status = 'pending')", idx_scan=3)

    classify([tam, kismi])

    assert safe_drop_candidates([tam, kismi], include_unscanned=False) == []


# ─── DB'siz: düşürme listesinin iç tutarlılığı ───────────────────────────────

def test_ix_cases_tracking_no_dusurme_listesinde_yok():
    """Ofis dosya no tekilliğini TEK BAŞINA tutan index — ayrı ve açık assertion."""
    assert "ix_cases_tracking_no" not in _tum_dusurulecekler()
    assert "uq_cases_sistem_no" not in _tum_dusurulecekler()


def test_dusurulen_trigramlar_trgm_sozlugunden_de_cikarildi():
    """Tuzak: sözlükte kalsalardı pg_trgm bloğu her açılışta yeniden yaratırdı."""
    dusen_trgm = [ad for ad in _tum_dusurulecekler() if ad.endswith("_trgm")]
    assert dusen_trgm, "trigram temizliği listeden düşmüş"
    cakisan = sorted(set(dusen_trgm) & set(database._TRGM_INDEXES))
    assert cakisan == [], f"hem düşürülüyor hem yeniden yaratılıyor: {cakisan}"


def test_dusurulen_indexler_migrasyonda_yeniden_yaratilmiyor():
    """Aynı ad hem CREATE hem DROP edilirse her açılış bir yarat-sil döngüsü olur."""
    import re

    yaratilanlar = set()
    for op in database._MIGRATIONS:
        sqls = op[3] if op[0] == "table" else (op[2] if op[0] == "index" else [])
        for sql in sqls:
            match = re.search(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", sql, re.I)
            if match:
                yaratilanlar.add(match.group(1))
        if op[0] == "columns":
            for spec in op[2].values():
                for sql in ([] if isinstance(spec, str) else spec[1]):
                    match = re.search(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", sql, re.I)
                    if match:
                        yaratilanlar.add(match.group(1))

    cakisan = sorted(yaratilanlar & set(_tum_dusurulecekler()))
    assert cakisan == [], f"hem yaratılıyor hem düşürülüyor: {cakisan}"


def test_dusurulecek_indexler_droplari_migrasyona_islendi():
    """Her ad gerçekten bir ("index", tablo, [DROP INDEX IF EXISTS ...]) op'unda."""
    droplar = {
        sql for op in database._MIGRATIONS if op[0] == "index"
        for sql in op[2] if sql.upper().startswith("DROP")
    }
    for ad in _tum_dusurulecekler():
        assert f"DROP INDEX IF EXISTS {ad}" in droplar, f"{ad} için DROP op'u yok"
    assert len(droplar) == len(_tum_dusurulecekler()), "mükerrer DROP ifadesi var"


# ─── dbtest: gerçek Postgres ─────────────────────────────────────────────────

@pytest.mark.dbtest
def test_sahte_unique_index_scratch_dbde_listeye_girmiyor(admin_engine):  # noqa: F811
    """Kabul kriteri: kurulan sahte bir UNIQUE index güvenli listeye GİRMEZ.

    Kurulum bilinçli olarak `ix_cases_tracking_no`'yu taklit eder: `CREATE UNIQUE
    INDEX` ile kurulur (pg_constraint karşılığı YOKTUR), hiç taranmaz. Yanına
    aynı imzalı bir PK ikizi konur — script'in "hiçbir şey bulamadığı için"
    değil, doğru ayrımı yaptığı için geçtiği görülsün.
    """
    with _scratch_database(admin_engine, "idxenv") as engine:
        with engine.begin() as conn:
            from sqlalchemy import text

            conn.execute(text("CREATE TABLE g042 (id SERIAL PRIMARY KEY, tekil TEXT, other TEXT)"))
            conn.execute(text("CREATE UNIQUE INDEX ux_g042_tekil ON g042 (tekil)"))
            conn.execute(text("CREATE INDEX ix_g042_id ON g042 (id)"))
            conn.execute(text("CREATE INDEX ix_g042_other ON g042 (other)"))

        with engine.connect() as conn:
            indexes = classify(collect_indexes(conn))

        by_name = {i.index_name: i for i in indexes}
        adaylar = [i.index_name for i in safe_drop_candidates(indexes)]

        assert "ux_g042_tekil" not in adaylar, "UNIQUE index güvenli listeye girdi — kural delindi"
        assert by_name["ux_g042_tekil"].verdict == KORUMALI_UNIQUE
        assert by_name["ux_g042_tekil"].guards_uniqueness_alone
        assert "g042_pkey" not in adaylar
        # Doğru ayrım: PK ikizi ve hiç taranmamış sıradan index adaya girer
        assert by_name["ix_g042_id"].verdict == ADAY_IKIZ
        assert "ix_g042_id" in adaylar
        assert "ix_g042_other" in adaylar


@pytest.mark.dbtest
def test_gercek_semada_ix_cases_tracking_no_korunuyor(admin_engine):  # noqa: F811
    """Sıfırdan kurulan gerçek şemada: index VAR, unique, ve adayların dışında."""
    with _scratch_database(admin_engine, "idxreal") as engine:
        _run_init_db(engine)

        with engine.connect() as conn:
            indexes = classify(collect_indexes(conn))

        by_name = {i.index_name: i for i in indexes}
        assert "ix_cases_tracking_no" in by_name, "ofis no tekillik index'i şemada yok"
        assert by_name["ix_cases_tracking_no"].is_unique
        assert "ix_cases_tracking_no" not in [i.index_name for i in safe_drop_candidates(indexes)]


@pytest.mark.dbtest
def test_dusurulecek_indexler_init_db_sonrasi_semada_kalmiyor(admin_engine):  # noqa: F811
    """Liste gerçekten uygulanıyor mu — ve İKİNCİ koşuda geri gelmiyor mu?"""
    with _scratch_database(admin_engine, "idxdrop") as engine:
        _run_init_db(engine)
        kalan = sorted(ad for ad in _tum_dusurulecekler() if ad in _live_indexes(engine))
        assert kalan == [], "düşürülmesi gereken index'ler duruyor: " + ", ".join(kalan)

        _run_init_db(engine)          # idempotency: yarat-sil döngüsü olmamalı
        kalan = sorted(ad for ad in _tum_dusurulecekler() if ad in _live_indexes(engine))
        assert kalan == [], "ikinci koşu düşürülen index'leri geri getirdi: " + ", ".join(kalan)


@pytest.mark.dbtest
def test_dusurulen_ikizlerin_kapsamasi_semada_duruyor(admin_engine):  # noqa: F811
    """Temizliğin ASIL güvenlik iddiası: ikiz düştü, kapsama kaybolmadı.

    `create_all()` modelin `index=True` karşılıklarını (ix_*_id, ix_*_case_id)
    yaratır; migrasyon onları düşürür. Her düşen ad için aynı tablo+kolon+access
    method'u tutan BAŞKA bir index kalmalıdır — trigram kalemleri hariç, onlar
    bilinçli olarak karşılıksız düşer (prod'da hiç taranmamışlar).

    Karşılaştırma script'in imza fonksiyonuyla DEĞİL, `pg_get_indexdef` metnini
    normalize ederek yapılır — üretim kodunu kendi mantığıyla doğrulamamak için.
    """
    from sqlalchemy import text

    def normalize(name, definition):
        # Adı ve UNIQUE anahtar sözcüğünü at: geriye tablo + access method + kolonlar kalır
        return definition.replace(f" {name} ", " X ").replace("CREATE UNIQUE INDEX", "CREATE INDEX")

    with _scratch_database(admin_engine, "idxcover") as engine:
        import models

        database_engine = database.engine
        database.engine = engine
        try:
            models.Base.metadata.create_all(bind=engine)
        finally:
            database.engine = database_engine

        once = {ad: normalize(ad, d) for ad, d in _live_indexes(engine).items()}
        dusenler = [ad for ad in _tum_dusurulecekler() if ad in once]
        assert len(dusenler) >= 25, f"create_all beklenen ikizleri yaratmadı ({len(dusenler)})"

        _run_init_db(engine)

        sonra = {ad: normalize(ad, d) for ad, d in _live_indexes(engine).items()}
        karsiliksiz = sorted(
            ad for ad in dusenler
            if not ad.endswith("_trgm") and once[ad] not in sonra.values()
        )
        assert karsiliksiz == [], (
            "Bu index'ler düşürüldü ama kapsamalarını taşıyan başka index YOK: "
            + ", ".join(karsiliksiz)
        )
        assert all(ad not in sonra for ad in dusenler)

        # Trigram tarafı: sözlükten çıkarıldıkları için yeniden yaratılmıyorlar
        with engine.connect() as conn:
            trgm = conn.execute(text(
                "SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname LIKE '%_trgm'"
            )).scalar()
        assert trgm == len(database._TRGM_INDEXES), "trigram index sayısı sözlükle uyuşmuyor"


# ─── G189: trigram index'leri boş legacy kolonlardan `case_foys`a ─────────────
#
# 14.09 performans denetimi D2: `cases.tku_no`/`sistem_no` 14.578 kartta 0 dolu,
# arama bu kimlikleri `case_foys` üzerinden buluyor (G123) ve oradaki üç kol
# index'sizdi. Yeni index'ler `_TRGM_INDEXES`e (G043 deseni), eskiler
# `_DUSURULECEK_INDEXLER`e (G042 deseni) girer.

G189_FOY_TRGM = {
    "idx_case_foys_tku_no_trgm": ("case_foys", "tku_no"),
    "idx_case_foys_sistem_no_trgm": ("case_foys", "sistem_no"),
    "idx_case_foys_onceki_tracking_no_trgm": ("case_foys", "onceki_tracking_no"),
}
G189_LEGACY_TRGM = ["idx_cases_tku_no_trgm", "idx_cases_sistem_no_trgm"]
G189_LEGACY_BTREE = "idx_cases_tku_no"


def _migrasyonun_yarattigi_index_sqlleri():
    """Tüm op türlerindeki CREATE INDEX ifadeleri (table gövdesi + columns post-SQL + index)."""
    sqller = []
    for op in database._MIGRATIONS:
        if op[0] == "table":
            sqller.extend(op[3])
        elif op[0] == "index":
            sqller.extend(op[2])
        elif op[0] == "columns":
            for spec in op[2].values():
                if not isinstance(spec, str):
                    sqller.extend(spec[1])
    return [s for s in sqller if s.strip().upper().startswith("CREATE")]


def test_g189_foy_trigram_indexleri_sozlukte_dogru_tablo_ve_kolonla():
    for ad, beklenen in G189_FOY_TRGM.items():
        assert database._TRGM_INDEXES.get(ad) == beklenen, f"{ad} sözlükte yok ya da yanlış hedefte"


def test_g189_legacy_cases_indexleri_dusuruluyor_ve_sozlukte_yok():
    """Sözlükte kalsalardı pg_trgm bloğu her açılışta yeniden yaratırdı (G042 dersi)."""
    dusen_cases = database._DUSURULECEK_INDEXLER["cases"]
    for ad in G189_LEGACY_TRGM + [G189_LEGACY_BTREE]:
        assert ad in dusen_cases, f"{ad} düşürme listesinde yok"
        assert ad not in database._TRGM_INDEXES, f"{ad} hem düşürülüyor hem yeniden yaratılıyor"
    # Tekillik kısıtı ve föy tarafının btree'si bu görevin konusu değil
    assert "uq_cases_sistem_no" not in _tum_dusurulecekler()
    assert "idx_case_foys_tku" not in _tum_dusurulecekler()


def test_g189_idx_cases_tku_no_kaynagi_migrasyondan_kaldirildi():
    """Madde 22'nin post-SQL'i kalsaydı kolonsuz eski kurulum btree'yi geri getirirdi."""
    yaratan = [s for s in _migrasyonun_yarattigi_index_sqlleri() if f" {G189_LEGACY_BTREE} " in f" {s} "]
    assert yaratan == [], f"{G189_LEGACY_BTREE} hâlâ yaratılıyor: {yaratan}"
    # uq_cases_sistem_no'nun kaynağı yerinde
    assert any(" uq_cases_sistem_no " in f" {s} " for s in _migrasyonun_yarattigi_index_sqlleri())


def test_g189_sozlukten_gin_trgm_ddl_uretimi():
    for ad in G189_FOY_TRGM:
        tablo, kolon = database._TRGM_INDEXES[ad]
        assert database._trgm_index_ddl(ad, tablo, kolon) == (
            f"CREATE INDEX IF NOT EXISTS {ad} ON case_foys USING gin ({kolon} gin_trgm_ops)"
        )


def test_g189_foy_trigram_indexleri_index_opuna_yazilmadi():
    """("index", ...) op'ları pg_trgm extension'ından ÖNCE koşar — sıfırdan kurulum ölürdü."""
    for ad in G189_FOY_TRGM:
        assert all(ad not in sql for sql in _migrasyonun_yarattigi_index_sqlleri())


@pytest.mark.dbtest
def test_g189_init_db_foy_trigramlarini_yaratir_legacy_indexleri_dusurur(request):
    """Sıfırdan kurulum + eski kurulum taklidi; ikinci init_db aynı index kümesini verir."""
    from sqlalchemy import text

    admin = request.getfixturevalue("admin_engine")
    with _scratch_database(admin, "g189") as engine:
        _run_init_db(engine)
        ilk = _live_indexes(engine)
        for ad, (tablo, kolon) in G189_FOY_TRGM.items():
            assert ad in ilk, f"{ad} sıfırdan kurulumda oluşmadı"
            assert f"ON public.{tablo} USING gin ({kolon} gin_trgm_ops)" in ilk[ad]
        for ad in G189_LEGACY_TRGM + [G189_LEGACY_BTREE]:
            assert ad not in ilk, f"{ad} sıfırdan kurulumda duruyor"
        assert "uq_cases_sistem_no" in ilk or "ix_cases_sistem_no" in ilk, (
            "cases.sistem_no tekillik index'i şemada yok — dokunulmaması gerekiyordu"
        )

        # Eski kurulum taklidi: G189 öncesi şemanın üç index'i elle geri kurulur
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX {G189_LEGACY_BTREE} ON cases (tku_no)"))
            for ad, kolon in zip(G189_LEGACY_TRGM, ["tku_no", "sistem_no"], strict=True):
                conn.execute(text(f"CREATE INDEX {ad} ON cases USING gin ({kolon} gin_trgm_ops)"))

        _run_init_db(engine)
        ikinci = _live_indexes(engine)
        kalan = sorted(ad for ad in G189_LEGACY_TRGM + [G189_LEGACY_BTREE] if ad in ikinci)
        assert kalan == [], "eski kurulumdaki legacy index'ler düşmedi: " + ", ".join(kalan)
        assert ikinci == ilk, "ikinci init_db index kümesini değiştirdi (idempotent değil)"

        _run_init_db(engine)
        assert _live_indexes(engine) == ilk


@pytest.mark.dbtest
def test_g189_arama_foy_kollari_trigram_indexini_kullanabiliyor(request):
    """Uygulanabilirlik sınavı: `_term_case_id_selects`in üç föy kolu yeni index'e düşebiliyor.

    Ölçülen HIZ değil ifade eşleşmesi. Kolun WHERE ifadesi (`stmt.whereclause`,
    arama kodunun ürettiğinin AYNISI) `case_foys` üzerinde tek başına EXPLAIN edilir:
    scratch hacminde JOIN sırası planlayıcıya `idx_case_foys_case` üzerinden filtre
    seçeneği verir ve sınav index'i değil JOIN maliyetini ölçmüş olurdu. Tek tablolu,
    sıralamasız sorguda seq scan kapalıyken geriye yalnız trigram bitmap'i kalır —
    ifade index'le eşleşmiyorsa plan seq scan'e düşer ve test kırmızı olur.
    Gerçek hacimli önce/sonra (JOIN'li kol) ölçümü görev raporunda.
    """
    from sqlalchemy import select, text

    import models
    from managers.case_manager import _term_case_id_selects

    admin = request.getfixturevalue("admin_engine")
    with _scratch_database(admin, "g189plan") as engine:
        _run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO cases (tracking_no, status, active, tenant_id)
                SELECT 'HA.G189.' || lpad(i::text, 5, '0') || '.X', 'DERDEST', true, NULL
                FROM generate_series(1, 4000) AS i
            """))
            conn.execute(text("""
                INSERT INTO case_foys (sistem_no, case_id, tku_no, onceki_tracking_no)
                SELECT 'SSTMN-' || i, c.id, 'TKU-' || lpad((i % 1500)::text, 4, '0'),
                       CASE WHEN i % 40 = 0 THEN 'HA.ESKI.' || i || '.X' END
                FROM generate_series(1, 12000) AS i
                JOIN cases c ON c.tracking_no = 'HA.G189.' || lpad((1 + i % 4000)::text, 5, '0') || '.X'
            """))
            conn.execute(text("ANALYZE cases"))
            conn.execute(text("ANALYZE case_foys"))

        def derle(stmt):
            return str(stmt.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))

        kollar = {}
        for stmt in _term_case_id_selects("TKU-0042", False):
            kosul = derle(stmt.whereclause)
            for ad, (_tablo, kolon) in G189_FOY_TRGM.items():
                if kosul.startswith(f"case_foys.{kolon} ILIKE"):
                    kollar[ad] = derle(select(models.CaseFoy.id).where(stmt.whereclause))
        assert set(kollar) == set(G189_FOY_TRGM), f"föy kolları bulunamadı: {sorted(kollar)}"

        with engine.connect() as conn:
            conn.execute(text("SET enable_seqscan = off"))
            for ad, sql in kollar.items():
                plan = "\n".join(r[0] for r in conn.execute(text(f"EXPLAIN {sql}")).all())
                assert f"Bitmap Index Scan on {ad}" in plan, f"{ad} kullanılamadı:\n{plan}"
