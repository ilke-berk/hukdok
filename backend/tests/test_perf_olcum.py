"""`scripts/perf_olcum.py` testleri (G183) — salt okunur performans ölçüm raporu.

İki katman:

* **DB'siz birim testleri** — salt okunur süzgeci ve modüldeki bütün SQL metinlerinin
  taranması, Markdown biçimleme, `EXPLAIN (FORMAT JSON)` özet ayrıştırıcısı (sahte plan).
* **`dbtest`** — scratch veritabanında (`test_migration_path` altyapısı; gerçek
  `hukudok` DB'sine asla yazılmaz, DB yoksa SKIP) script uçtan uca koşar, çıktıda altı
  bölüm başlığı vardır; CLI bağlantısı sunucu tarafında yazmayı reddeder.
"""
import datetime as dt
import json
import re

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

import test_migration_path as mig
from scripts import index_envanteri, perf_olcum

# Scratch DB fixture'ı `test_migration_path`'ten yeniden kullanılır (modül özniteliği
# olarak bağlanınca pytest onu bu modülde de toplar).
admin_engine = mig.admin_engine

# Görev sözleşmesinin taradığı sözcükler — script'in kendi süzgecinden BAĞIMSIZ
# yazıldı (üretim kodunu kendi regex'iyle doğrulamak kendini onaylayan test olurdu).
_YAZMA_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|VACUUM)\b", re.IGNORECASE)
_BAS_RE = re.compile(r"^\s*(SELECT|SHOW|EXPLAIN)\b", re.IGNORECASE)


def _script_sql_metinleri():
    """Script'in koşabileceği HER SQL metni: sabitler + üretilen SHOW/satır verisi +
    derlenmiş arama sorgusu + yeniden kullanılan index envanteri sorgusu."""
    metinler = {
        ad: deger for ad, deger in vars(perf_olcum).items()
        if ad.endswith("_SQL") and isinstance(deger, str)
    }
    for ayar in perf_olcum.AYARLAR:
        metinler[f"show:{ayar}"] = perf_olcum.show_sql(ayar)
    metinler["satir_verisi"] = perf_olcum.satir_verisi_sql('"case_history"')
    sql, _params, _adlar = perf_olcum.arama_sorgusu(postgresql.dialect(), "Bora")
    metinler["arama_explain"] = sql
    metinler["index_envanteri.INVENTORY_SQL"] = index_envanteri.INVENTORY_SQL
    return metinler


# ─── DB'siz: salt okunur ─────────────────────────────────────────────────────

def test_script_sql_metinlerinde_yazma_sozcugu_yok():
    metinler = _script_sql_metinleri()
    # Tarama boş kümede geçmesin: sabitlerin gerçekten toplandığını kilitle
    assert {"BUYUK_TABLOLAR_SQL", "BAGLANTILAR_SQL", "DURUM_DAGILIMI_SQL",
            "KIMLIK_DOLULUK_SQL", "STAT_SIFIRLAMA_SQL", "AYAR_KAYNAK_SQL"} <= set(metinler)
    for ad, sql in metinler.items():
        assert not _YAZMA_RE.search(sql), f"{ad} yazma sözcüğü içeriyor: {_YAZMA_RE.search(sql).group(0)}"
        assert _BAS_RE.match(sql), f"{ad} SELECT/SHOW/EXPLAIN ile başlamıyor"


def test_script_sql_metinleri_kendi_suzgecinden_de_geciyor():
    for ad, sql in _script_sql_metinleri().items():
        assert perf_olcum.salt_okunur_dogrula(sql) == sql, ad


def test_script_her_sql_calistirmasi_suzgecten_geciyor():
    """Sabit dışı bir yerde (satır içi text(), f-string) süzgeçsiz SQL koşulmasın.

    Kaynak kodda `text(` çağrılarının hepsi `text(salt_okunur_dogrula(` biçimindedir;
    tek `exec_driver_sql` çağrısı `arama_sorgusu`'nun (içeride süzgeçten geçen) çıktısını koşar.
    `collect_indexes` ayrı modüldedir — onun sorgusu yukarıdaki taramada.
    """
    kaynak = open(perf_olcum.__file__, encoding="utf-8").read()
    kod = re.sub(r'"""[\s\S]*?"""', "", kaynak)          # docstring'ler
    kod = re.sub(r"#[^\n]*", "", kod)                    # yorumlar
    text_cagrilari = re.findall(r"\btext\(([^)\n]*)", kod)
    assert text_cagrilari, "tarama hiçbir text() çağrısı bulamadı"
    assert [c for c in text_cagrilari if not c.startswith("salt_okunur_dogrula(")] == []
    assert re.findall(r"exec_driver_sql\(([^,)\n]*)", kod) == ["sql"]
    assert re.search(r"sql, params, adlar = arama_sorgusu\(", kod)
    assert re.search(r"sql = salt_okunur_dogrula\(EXPLAIN_ONEKI \+ str\(derlenmis\)\)", kod)


@pytest.mark.parametrize("sql", [
    "DELETE FROM cases",
    "UPDATE cases SET status = 'X'",
    "SELECT 1; DROP TABLE cases",
    "VACUUM (FULL, ANALYZE) case_history",
    "ANALYZE cases",
    "WITH silinen AS (DELETE FROM cases RETURNING id) SELECT count(*) FROM silinen",
    "EXPLAIN ANALYZE INSERT INTO cases (tracking_no) VALUES ('x')",
    "SELECT pg_stat_reset()",
    "SELECT pg_stat_reset_single_table_counters(1)",
    "SET statement_timeout = 0",
    "CREATE INDEX x ON cases (id)",
])
def test_suzgec_yazma_sqlini_reddeder(sql):
    with pytest.raises(ValueError):
        perf_olcum.salt_okunur_dogrula(sql)


def test_suzgec_kolon_adlarini_yazma_sanmaz():
    """`deleted_at`/`updated_at`/`last_autovacuum` tam sözcük değildir."""
    sql = "SELECT deleted_at, updated_at, created_at, last_autovacuum, pg_stat_get_db_stat_reset_time(1) FROM x"
    assert perf_olcum.salt_okunur_dogrula(sql) == sql


def test_kos_reddedilen_sqli_baglantiya_hic_gondermez():
    class SahteBaglanti:
        cagrilar = []

        def execute(self, *args, **kwargs):
            self.cagrilar.append(args)
            raise AssertionError("süzgeçten geçmeyen SQL bağlantıya ulaştı")

    baglanti = SahteBaglanti()
    with pytest.raises(ValueError):
        perf_olcum._kos(baglanti, "DROP TABLE cases")
    assert baglanti.cagrilar == []


def test_show_sql_yalniz_sabit_listeden():
    assert perf_olcum.show_sql("work_mem") == "SHOW work_mem"
    with pytest.raises(ValueError):
        perf_olcum.show_sql("all; DROP TABLE cases")
    with pytest.raises(ValueError):
        perf_olcum.show_sql("data_directory")


def test_denetimin_istedigi_sekiz_ayar_listede():
    assert set(perf_olcum.AYARLAR) == {
        "shared_buffers", "effective_cache_size", "work_mem", "random_page_cost", "max_connections",
        "idle_in_transaction_session_timeout", "lock_timeout", "shared_preload_libraries",
    }


# ─── DB'siz: Markdown biçimleme ──────────────────────────────────────────────

def test_md_tablo_bicimi():
    tablo = perf_olcum.md_tablo(
        ("Ad", "Sayı", "Bayrak", "Boş"),
        [("a|b\nc", 14338, True, None), ("x", 0, False, "  ")],
    )
    assert tablo.splitlines() == [
        "| Ad | Sayı | Bayrak | Boş |",
        "| --- | --- | --- | --- |",
        "| a\\|b c | 14.338 | evet | — |",
        "| x | 0 | hayır | — |",
    ]


def test_md_tablo_bos_ve_uyumsuz_satir():
    assert perf_olcum.md_tablo(("A",), []) == "_(satır yok)_"
    with pytest.raises(ValueError):
        perf_olcum.md_tablo(("A", "B"), [("tek",)])


def test_tr_sayi_ve_tr_zaman():
    assert perf_olcum.tr_sayi(1234567) == "1.234.567"
    assert perf_olcum.tr_sayi(91.456, 1) == "91,5"
    assert perf_olcum.tr_sayi(12345.678, 2) == "12.345,68"
    utc = dt.datetime(2026, 9, 14, 21, 30, tzinfo=dt.timezone.utc)
    assert perf_olcum.tr_zaman(utc) == "2026-09-15 00:30:00"          # TR = UTC+3
    assert perf_olcum.tr_zaman(utc.replace(tzinfo=None)) == "2026-09-15 00:30:00"
    assert perf_olcum.tr_zaman(None) == "—"


# ─── DB'siz: EXPLAIN özet ayrıştırıcısı ──────────────────────────────────────

def _sahte_plan():
    """UNION'lu arama planının kısaltılmış biçimi: HashAggregate → Append → 3 kol."""
    return [{
        "Plan": {
            "Node Type": "Aggregate", "Strategy": "Hashed",
            "Actual Rows": 5, "Actual Loops": 1,
            "Shared Hit Blocks": 27010, "Shared Read Blocks": 12,
            "Plans": [{
                "Node Type": "Append", "Actual Rows": 7, "Actual Loops": 1,
                "Plans": [
                    {   # kol 1: düz seq scan
                        "Node Type": "Seq Scan", "Relation Name": "cases", "Alias": "cases",
                        "Actual Rows": 2, "Actual Loops": 1, "Actual Total Time": 5.25,
                        "Rows Removed by Filter": 14578,
                        "Shared Hit Blocks": 4635, "Shared Read Blocks": 0,
                    },
                    {   # kol 2: join — föy seq scan + cases pkey index scan (3 döngü)
                        "Node Type": "Nested Loop", "Actual Rows": 3, "Actual Loops": 1,
                        "Actual Total Time": 176.0,
                        "Shared Hit Blocks": 8000, "Shared Read Blocks": 10,
                        "Plans": [
                            {"Node Type": "Seq Scan", "Relation Name": "case_foys", "Parallel Aware": False,
                             "Actual Rows": 3, "Actual Loops": 1, "Rows Removed by Filter": 8137,
                             "Shared Hit Blocks": 7990, "Shared Read Blocks": 10},
                            {"Node Type": "Index Only Scan", "Relation Name": "cases", "Index Name": "cases_pkey",
                             "Actual Rows": 1, "Actual Loops": 3,
                             "Shared Hit Blocks": 10, "Shared Read Blocks": 0},
                        ],
                    },
                    {   # kol 3: trigram bitmap
                        "Node Type": "Bitmap Heap Scan", "Relation Name": "cases",
                        "Actual Rows": 2, "Actual Loops": 1, "Actual Total Time": 0.8,
                        "Rows Removed by Index Recheck": 1,
                        "Shared Hit Blocks": 6, "Shared Read Blocks": 2,
                        "Plans": [{"Node Type": "Bitmap Index Scan", "Index Name": "idx_cases_court_trgm",
                                   "Actual Rows": 3, "Actual Loops": 1}],
                    },
                ],
            }],
        },
        "Planning Time": 1.234,
        "Execution Time": 182.5,
    }]


def test_explain_ozeti_kollari_adlandirir_ve_ozetler():
    adlar = ["cases.esas_no", "case_foys.tku_no", "cases.court"]
    ozet = perf_olcum.explain_ozeti(json.dumps(_sahte_plan()), adlar)

    assert ozet.uyari is None
    assert (ozet.planlama_ms, ozet.calisma_ms) == (1.234, 182.5)
    assert (ozet.buffer_hit, ozet.buffer_read) == (27010, 12)
    assert [k.kol for k in ozet.kollar] == adlar

    seq, join, bitmap = ozet.kollar
    assert (seq.kok_dugum, seq.seq_scan, seq.satir, seq.elenen) == ("Seq Scan", True, 2, 14578)
    assert (seq.buffer_hit, seq.buffer_read, seq.sure_ms) == (4635, 0, 5.25)
    assert seq.taramalar == ["Seq Scan cases"]

    assert join.kok_dugum == "Nested Loop"
    assert join.seq_scan is True, "alt ağaçtaki föy seq scan'i kolu Seq Scan'li yapar"
    assert join.taramalar == ["Seq Scan case_foys", "Index Only Scan cases [cases_pkey]"]
    assert (join.satir, join.elenen, join.buffer_hit, join.buffer_read) == (3, 8137, 8000, 10)

    assert bitmap.seq_scan is False
    assert bitmap.taramalar == ["Bitmap Heap Scan cases", "Bitmap Index Scan [idx_cases_court_trgm]"]


def test_explain_ozeti_python_listesini_de_kabul_eder():
    """psycopg2 `json` tipini zaten ayrıştırıp liste döndürür."""
    ozet = perf_olcum.explain_ozeti(_sahte_plan(), ["a.b", "c.d", "e.f"])
    assert [k.kol for k in ozet.kollar] == ["a.b", "c.d", "e.f"]


def test_explain_ozeti_dongu_sayisini_carpar():
    plan = _sahte_plan()
    kol = plan[0]["Plan"]["Plans"][0]["Plans"][0]
    kol.update({"Actual Loops": 4, "Actual Rows": 2.5, "Actual Total Time": 1.5, "Rows Removed by Filter": 10})
    ozet = perf_olcum.explain_ozeti(plan, ["a.b", "c.d", "e.f"])
    assert (ozet.kollar[0].satir, ozet.kollar[0].elenen, ozet.kollar[0].sure_ms) == (10, 40, 6.0)


def test_explain_ozeti_kol_sayisi_tutmazsa_uyarir_uydurmaz():
    ozet = perf_olcum.explain_ozeti(_sahte_plan(), ["tek.kol", "iki.kol"])
    assert ozet.uyari and "kol sayısını" in ozet.uyari
    assert [k.kol for k in ozet.kollar] == ["kol 1", "kol 2", "kol 3"], "ad kaydırılarak yanlış eşlenmemeli"


def test_explain_ozeti_append_yoksa_uyarir():
    plan = [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "cases"}, "Execution Time": 1.0}]
    ozet = perf_olcum.explain_ozeti(plan, ["cases.esas_no"])
    assert ozet.kollar == [] and "Append" in ozet.uyari


def test_render_plan_tablosu():
    ozet = perf_olcum.explain_ozeti(_sahte_plan(), ["cases.esas_no", "case_foys.tku_no", "cases.court"])
    metin = perf_olcum.render_plan("Bora", ozet)
    assert "**Seq Scan'li kol:** 2 / 3" in metin
    assert "| Kol | Kök düğüm | Taramalar |" in metin
    assert "| case_foys.tku_no | Nested Loop | Seq Scan case_foys; Index Only Scan cases [cases_pkey] | evet |" in metin


def test_kol_adlari_uygulamanin_arama_kollarindan_turer():
    from managers import case_manager

    adlar = perf_olcum.kol_adlari(case_manager._term_case_id_selects("Bora", exact=False))
    assert len(adlar) == len(case_manager._term_case_id_selects("Bora", exact=False))
    assert not [a for a in adlar if a.startswith("kol ")], adlar
    assert adlar[0] == "cases.esas_no"
    assert {"case_esas_numbers.esas_no", "case_foys.tku_no", "case_foys.sistem_no",
            "case_foys.onceki_tracking_no", "case_parties.name", "case_history.old_value"} <= set(adlar)


def test_arama_sorgusu_explain_analyze_buffers_ve_bind_parametreli():
    sql, params, adlar = perf_olcum.arama_sorgusu(postgresql.dialect(), "Bora")
    assert sql.startswith("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT")
    assert "Bora" not in sql, "terim SQL metnine gömülmemeli, bind parametresi olmalı"
    assert "%Bora%" in params.values()
    assert sql.count("UNION") == len(adlar) - 1


# ─── dbtest: scratch veritabanında uçtan uca ─────────────────────────────────

@pytest.fixture(scope="module")
def olcum_db(admin_engine):
    with mig._scratch_database(admin_engine, "perfolcum") as engine:
        mig._run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO cases (tracking_no, status, esas_no, responsible_lawyer_name) VALUES "
                "('G183/1', 'DERDEST', '2024/1', 'Av. Bora Test'), "
                "('G183/2', 'MAHZEN', '2024/2', NULL)"
            ))
            # G195 (kullanıcı kararı 14.09): TEMYIZ satırı kısıttan ÖNCE var olan bozuk
            # satırdır — prod'un birebir taklidi. Kısıt düşürülür, satır eklenir, kısıt
            # migrasyonun kendi DDL'iyle NOT VALID geri gelir (mevcut satırı taramaz).
            import database

            conn.execute(text("ALTER TABLE cases DROP CONSTRAINT ck_cases_status_uclu"))
            conn.execute(text(
                "INSERT INTO cases (tracking_no, status, esas_no, responsible_lawyer_name) VALUES "
                "('G183/3', 'TEMYIZ', '2024/3', NULL)"
            ))
            conn.execute(text(database.case_status_check_ddl()))
            case_id = conn.execute(text("SELECT id FROM cases WHERE tracking_no = 'G183/1'")).scalar()
            conn.execute(
                text("INSERT INTO case_foys (sistem_no, case_id, tku_no) VALUES ('SSTMN-1', :c, 'TKU-1')"),
                {"c": case_id},
            )
        yield engine


def _bolum_basliklari(metin):
    return [satir[3:] for satir in metin.splitlines() if satir.startswith("## ")]


@pytest.mark.dbtest
def test_uctan_uca_terimsiz_alti_bolum_ve_out_dosyasi(olcum_db, tmp_path, capsys):
    hedef = tmp_path / "perf.md"
    assert perf_olcum.main(["--out", str(hedef)], engine=olcum_db) == 0

    metin = hedef.read_text(encoding="utf-8")
    assert capsys.readouterr().out == metin, "stdout ile --out dosyası aynı rapor"
    assert _bolum_basliklari(metin) == list(perf_olcum.BOLUM_BASLIKLARI)
    assert "Ölçülemedi" not in metin, metin
    assert metin.startswith("# HukuDok performans ölçümü")
    assert "| Sürüm (APP_VERSION) |" in metin and "| Zaman (TR) |" in metin

    arama = metin.split("## 6. Arama planı", 1)[1]
    assert "Atlandı" in arama and "EXPLAIN (ANALYZE" not in arama

    # Veri dağılımı: üçlü dışı TEMYIZ bayraklı, föy kimlikleri sayıldı
    assert "| TEMYIZ | 1 | 0 | evet |" in metin
    assert "| DERDEST | 1 | 0 | hayır |" in metin
    assert "| case_foys | 1 | 1 | 1 | 0 |" in metin
    # Şişme ve ayarlar gerçekten ölçüldü
    assert "| cases |" in metin.split("## 2.", 1)[0]
    assert "| shared_buffers |" in metin
    assert "idle in transaction:" in metin


@pytest.mark.dbtest
def test_uctan_uca_terimle_arama_plani_kol_kol(olcum_db):
    from managers import case_manager

    with olcum_db.connect() as conn:
        metin = perf_olcum.rapor_uret(conn, term="Bora", surum="test-sha")

    assert _bolum_basliklari(metin) == list(perf_olcum.BOLUM_BASLIKLARI)
    assert "Ölçülemedi" not in metin, metin
    assert "| Sürüm (APP_VERSION) | test-sha |" in metin
    arama = metin.split("## 6. Arama planı", 1)[1]
    assert "Atlandı" not in arama
    assert "**Uyarı:**" not in arama, arama
    for ad in perf_olcum.kol_adlari(case_manager._term_case_id_selects("Bora", exact=False)):
        assert f"| {ad} |" in arama, f"{ad} kolu plan tablosunda yok"


@pytest.mark.dbtest
def test_cli_baglantisi_sunucu_tarafinda_salt_okunur(olcum_db):
    ro = perf_olcum.salt_okunur_engine(olcum_db.url)
    try:
        with ro.connect() as conn:
            assert conn.execute(text("SHOW default_transaction_read_only")).scalar() == "on"
            with pytest.raises(DBAPIError):
                conn.execute(text("CREATE TABLE g183_yazma_denemesi (id int)"))
    finally:
        ro.dispose()
