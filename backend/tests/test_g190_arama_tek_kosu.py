"""G190 — arama tek koşu (D4) + boş legacy kolların çıkarılması (D1/D2) + kanıtlı trgm index'i.

Kaynak: 14.09 performans denetimi. `get_cases(q=..., with_total=True)` eskiden
`query.count()` ve sayfa sorgusunda AYNI UNION/INTERSECT ağacını iki kez
koşuyordu. Artık süzülmüş + sıralanmış id listesi tek sorguda gelir; toplam
listenin uzunluğu, sayfa listenin dilimidir.

İddialar SQL SAYARAK kilitlenir (`before_cursor_execute`, G051 deseni): "UNION
içeren ifade sayısı" motora giden ham SQL'den okunur, varsayımdan değil.
sqlite + StaticPool deseni G055 ile aynı; terimler ASCII (sqlite `lower()`
Türkçe diakritik eşitlemez — harness sınırı, ürün davranışı değil).

Index kısmı (§5) G189 deseni: sözlük/düşürme listesi tutarlılığı DB'siz, kurulum
ve plan uygulanabilirliği `dbtest` scratch veritabanında. Ölçülen önce/sonra
EXPLAIN tablosu görev raporunda ve karar 018'in G190 ekinde.
"""
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
import test_migration_path as mig
from database import Base

# Scratch Postgres bakım bağlantısı (test_perf_olcum deseni; DB yoksa dbtest SKIP)
admin_engine = mig.admin_engine


@pytest.fixture()
def db_env(monkeypatch):
    from managers import case_manager

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)

    statements: list = []

    def _kaydet(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _kaydet)
    yield SimpleNamespace(sessions=maker, manager=case_manager, statements=statements)
    event.remove(engine, "before_cursor_execute", _kaydet)
    engine.dispose()


def _dava(db_env, tracking_no, **extra):
    created = db_env.manager.add_case({"tracking_no": tracking_no, **extra})
    assert created and "id" in created, created
    return created["id"]


def _parti_ekle(db_env, case_id, name):
    db = db_env.sessions()
    try:
        db.add(models.CaseParty(case_id=case_id, name=name, role="Davacı", party_type="CLIENT"))
        db.commit()
    finally:
        db.close()


def _updated_at_yaz(db_env, case_id, zaman):
    """Sıralamayı deterministik kurmak için `updated_at`i elle sabitler."""
    db = db_env.sessions()
    try:
        db.get(models.Case, case_id).updated_at = zaman
        db.commit()
    finally:
        db.close()


def _union_sqls(db_env):
    return [s for s in db_env.statements if "UNION" in s.upper()]


def _cagir(db_env, **kwargs):
    db_env.statements.clear()
    return db_env.manager.get_cases(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 1. D4 — UNION'lı id sorgusu TEK kez koşar
# ═══════════════════════════════════════════════════════════════════════════

def test_with_total_true_union_id_sorgusu_tek_kez_kosuyor(db_env):
    """Kabul: `get_cases(q, with_total=True)` → UNION içeren ifade sayısı = 1.

    Eski kodda 2'ydi (`query.count()` + sayfa sorgusu aynı ağacı ayrı ayrı koşar).
    """
    for i in range(3):
        _dava(db_env, f"T.{i:04d}.2026", subject="Tazminat davasi")

    items, total = _cagir(db_env, q="tazminat", with_total=True)

    assert total == 3 and len(items) == 3
    assert len(_union_sqls(db_env)) == 1, (
        "UNION ağacı birden çok kez koştu:\n" + "\n---\n".join(_union_sqls(db_env))
    )
    assert not [s for s in db_env.statements if "count(" in s.lower()], (
        "arama yolunda COUNT kaldı — toplam id listesinin uzunluğu olmalı"
    )


def test_cok_terimli_intersect_de_tek_kosu(db_env):
    """INTERSECT-of-UNION tek ifadedir: çok terimli aramada da UNION'lı ifade = 1."""
    ikisi_de = _dava(db_env, "T.0100.2026", subject="Tazminat davasi")
    _parti_ekle(db_env, ikisi_de, "Mehmet Murat")
    _dava(db_env, "T.0101.2026", subject="Tazminat davasi")

    items, total = _cagir(db_env, q="tazminat murat", with_total=True)

    assert total == 1 and [i["id"] for i in items] == [ikisi_de]
    union_sqls = _union_sqls(db_env)
    assert len(union_sqls) == 1 and "INTERSECT" in union_sqls[0].upper()


def test_with_total_false_yolu_da_tek_kosu_ve_count_yok(db_env):
    """E3 yolu (her tuş vuruşu) bozulmadı: UNION bir kez, COUNT hiç."""
    for i in range(3):
        _dava(db_env, f"T.02{i:02d}.2026", subject="Tazminat davasi")

    items, total = _cagir(db_env, q="tazminat", limit=2, with_total=False)

    assert total == -1 and len(items) == 2
    assert len(_union_sqls(db_env)) == 1
    assert not [s for s in db_env.statements if "count(" in s.lower()]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Toplam = sayfaların birleşimi (tekrar/atlama yok) ve sıra korunuyor
# ═══════════════════════════════════════════════════════════════════════════

def test_uc_sayfa_birlesimi_toplamla_ayni_tekrar_atlama_yok(db_env):
    """Kabul: üç sayfa dolaşılır, birleşim `total` ile karşılaştırılır.

    `updated_at` bilinçli EŞİT verilir (id tiebreaker'ı sınanır) ve biri
    relevance 1 (tam tracking_no eşleşmesi) olduğu hâlde EN ESKİ yapılır: sıra
    relevance → updated_at → id üçlüsünden sapmamalı.
    """
    ayni_an = datetime(2026, 9, 1, 12, 0, 0)
    eslesen = []
    for i in range(7):
        case_id = _dava(db_env, f"G190.{i:04d}.2026", subject="Rucu davasi")
        _updated_at_yaz(db_env, case_id, ayni_an)
        eslesen.append(case_id)
    tam_eslesme = _dava(db_env, "RUCU", subject="Baska konu")
    _updated_at_yaz(db_env, tam_eslesme, ayni_an - timedelta(days=30))
    eslesen.append(tam_eslesme)
    _dava(db_env, "G190.9999.2026", subject="Kira davasi")  # eşleşmeyen

    sayfalar = []
    toplamlar = set()
    for offset in (0, 3, 6):
        items, total = db_env.manager.get_cases(q="rucu", limit=3, offset=offset, with_total=True)
        sayfalar.append([i["id"] for i in items])
        toplamlar.add(total)

    birlesik = [case_id for sayfa in sayfalar for case_id in sayfa]
    assert toplamlar == {8}, f"sayfalar farklı toplam döndü: {toplamlar}"
    assert [len(s) for s in sayfalar] == [3, 3, 2]
    assert len(birlesik) == len(set(birlesik)) == 8, f"tekrar var: {sayfalar}"
    assert set(birlesik) == set(eslesen), "atlanan ya da fazladan satır var"

    # Relevance 1 en eskisi olsa da başta; eşit updated_at'te id azalan
    beklenen = [tam_eslesme] + sorted(eslesen[:7], reverse=True)
    assert birlesik == beklenen

    # Sayfalı sıra, sayfasız tek çağrının sırasıyla birebir aynı
    hepsi, _ = db_env.manager.get_cases(q="rucu", limit=50, with_total=True)
    assert [i["id"] for i in hepsi] == birlesik


def test_toplam_dilimi_asan_offsette_de_dogru(db_env):
    """Sayfa boş kalsa bile toplam kaybolmaz (id listesi tam küme)."""
    for i in range(2):
        _dava(db_env, f"T.03{i:02d}.2026", subject="Tazminat davasi")

    items, total = db_env.manager.get_cases(q="tazminat", limit=10, offset=10, with_total=True)

    assert items == [] and total == 2


def test_tek_kosu_satir_sozlesmesini_degistirmiyor(db_env):
    """`with_total=True` (id listesi yolu) ile `False` (sayfa sorgusu yolu) aynı satırları üretir."""
    case_id = _dava(db_env, "T.0400.2026", subject="Tazminat davasi", esas_no="2024/15")
    _parti_ekle(db_env, case_id, "Ahmet Yilmaz")

    sayili, total = db_env.manager.get_cases(q="tazminat", with_total=True)
    sayisiz, eksi = db_env.manager.get_cases(q="tazminat", with_total=False)

    assert total == 1 and eksi == -1
    assert sayili == sayisiz
    assert [p["name"] for p in sayili[0]["parties"]] == ["Ahmet Yilmaz"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Kollar — boş legacy kollar yok, exact modun eksik kolları korunuyor
# ═══════════════════════════════════════════════════════════════════════════

def _kollar_sql(case_manager, exact):
    return [
        str(s.compile(compile_kwargs={"literal_binds": True}))
        for s in case_manager._term_case_id_selects("TKU-784", exact)
    ]


@pytest.mark.parametrize("exact", [False, True])
def test_legacy_cases_tku_sistem_kollari_yok_foy_kollari_var(exact):
    """`cases.tku_no`/`sistem_no` yazıcısız ve boş (D2) — kol olarak aranmaz."""
    from managers import case_manager

    birlesik = " | ".join(_kollar_sql(case_manager, exact))
    assert "cases.tku_no" not in birlesik.replace("case_foys.tku_no", "")
    assert "cases.sistem_no" not in birlesik.replace("case_foys.sistem_no", "")
    assert "case_foys.tku_no" in birlesik and "case_foys.sistem_no" in birlesik


def test_kol_sayilari_normal_15_exact_13():
    from managers import case_manager

    assert len(case_manager._term_case_id_selects("x", False)) == 15
    assert len(case_manager._term_case_id_selects("x", True)) == 13


def test_exact_modda_notes_ve_old_value_kollari_yok():
    """Kabul: exact modda `notes`/`case_history.old_value` kolları yine yok."""
    from managers import case_manager

    exact = " | ".join(_kollar_sql(case_manager, True))
    normal = " | ".join(_kollar_sql(case_manager, False))
    assert "cases.notes" not in exact and "case_history.old_value" not in exact
    assert "cases.notes" in normal and "case_history.old_value" in normal


def test_relevance_legacy_kolonlara_bakmiyor(db_env):
    """Sıralama ifadesi de boş kolonları okumaz (id sorgusunun ORDER BY'ı)."""
    _dava(db_env, "T.0500.2026", subject="Tazminat davasi")

    _cagir(db_env, q="tazminat", with_total=True)

    id_sorgusu = _union_sqls(db_env)[0]
    order_by = id_sorgusu.upper().rsplit("ORDER BY", 1)[1]
    assert "TKU_NO" not in order_by and "SISTEM_NO" not in order_by
    assert "ESAS_NO" in order_by and "TRACKING_NO" in order_by


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sözleşme — imza ve dönüş şekli değişmedi
# ═══════════════════════════════════════════════════════════════════════════

def test_get_cases_imzasi_degismedi():
    from managers import case_manager

    params = inspect.signature(case_manager.get_cases).parameters
    assert [(p.name, p.default) for p in params.values()] == [
        ("limit", 50), ("offset", 0), ("status", None), ("lawyer", None), ("q", None),
        ("exact", False), ("tenant_id", None), ("file_type", None), ("urgent_days", None),
        ("missing_required", False), ("missing_bucket", None), ("olay_turu", None),
        ("hizmet_turu", None), ("with_total", True),
    ]


def test_bos_sonucta_donus_sekli(db_env):
    _dava(db_env, "T.0600.2026", subject="Kira davasi")

    items, total = db_env.manager.get_cases(q="tazminat", with_total=True)

    assert items == [] and total == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Kanıtlı trgm index'leri — dört kol geri geldi, iki aday reddedildi
# ═══════════════════════════════════════════════════════════════════════════

G190_TRGM = {
    "idx_cases_court_trgm": ("cases", "court"),
    "idx_cases_subject_trgm": ("cases", "subject"),
    "idx_cases_esas_no_trgm": ("cases", "esas_no"),
    "idx_cases_tracking_no_trgm": ("cases", "tracking_no"),
}
# Ölçüldü, EKLENMEDİ (gerekçe raporda): kazanç ≤0,3 ms / kolon arama kapsamı kullanıcı kararında
G190_REDDEDILEN = ["idx_case_esas_numbers_esas_no_trgm", "idx_case_history_old_value_trgm"]


def _dusurulecekler():
    return {ad for adlar in database._DUSURULECEK_INDEXLER.values() for ad in adlar}


def test_g190_dort_trigram_sozlukte_dogru_hedefle():
    for ad, beklenen in G190_TRGM.items():
        assert database._TRGM_INDEXES.get(ad) == beklenen, f"{ad} sözlükte yok ya da yanlış hedefte"
        assert database._trgm_index_ddl(ad, *beklenen) == (
            f"CREATE INDEX IF NOT EXISTS {ad} ON {beklenen[0]} USING gin ({beklenen[1]} gin_trgm_ops)"
        )


def test_g190_dort_trigram_dusurme_listesinden_cikti():
    """İkisinde birden kalsaydı her açılışta DROP (migrasyon) + CREATE (pg_trgm bloğu) olurdu."""
    assert _dusurulecekler().isdisjoint(G190_TRGM), sorted(_dusurulecekler() & set(G190_TRGM))
    # Karar 018'in ölçüm istenmeyen iki trigram'ı düşmüş kalır
    assert {"idx_cases_klasor_no_2_trgm", "idx_cases_resp_lawyer_trgm"} <= _dusurulecekler()


def test_g190_reddedilen_adaylar_eklenmedi():
    for ad in G190_REDDEDILEN:
        assert ad not in database._TRGM_INDEXES, f"{ad} ölçümle reddedildi, sözlüğe girmemeli"


@pytest.mark.dbtest
def test_g190_init_db_trigramlari_kurar_kararli_tutar_ve_arama_kollari_kullanir(admin_engine):
    """Sıfırdan kurulum dört index'i yaratır; ikinci init_db onları DÜŞÜRÜP YENİDEN KURMAZ
    (oid sabit); aramanın kendi WHERE ifadesi index'e düşebilir.

    Plan sınavı G189 deseni: kolun `whereclause`u tek tablolu sorguda, seq scan
    kapalıyken EXPLAIN edilir — ifade index'le eşleşmiyorsa plan seq scan'e düşer.
    Hacimli önce/sonra ölçümü görev raporunda.
    """
    from managers.case_manager import _term_case_id_selects

    oid_sql = text("SELECT relname, oid FROM pg_class WHERE relname = ANY(:adlar)")
    with mig._scratch_database(admin_engine, "g190") as engine:
        mig._run_init_db(engine)
        ilk = mig._live_indexes(engine)
        for ad, (tablo, kolon) in G190_TRGM.items():
            assert ad in ilk, f"{ad} sıfırdan kurulumda oluşmadı"
            assert f"ON public.{tablo} USING gin ({kolon} gin_trgm_ops)" in ilk[ad]
        with engine.connect() as conn:
            oid_once = dict(conn.execute(oid_sql, {"adlar": list(G190_TRGM)}).all())

        mig._run_init_db(engine)
        with engine.connect() as conn:
            oid_sonra = dict(conn.execute(oid_sql, {"adlar": list(G190_TRGM)}).all())
        assert oid_sonra == oid_once, "ikinci init_db index'i düşürüp yeniden kurdu (git-gel)"
        assert mig._live_indexes(engine) == ilk

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO cases (tracking_no, status, active, tenant_id, court, subject, esas_no)
                SELECT 'HA.G190.' || lpad(i::text, 5, '0') || '.X', 'DERDEST', true, NULL,
                       'Sisli ' || (i % 40) || '. Sulh Hukuk', 'Tazminat ' || i, '2024/' || i
                FROM generate_series(1, 4000) AS i
            """))
            conn.execute(text("ANALYZE cases"))

        def derle(stmt):
            return str(stmt.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))

        kollar = {}
        for stmt in _term_case_id_selects("Sulh", False):
            kosul = derle(stmt.whereclause)
            for ad, (_tablo, kolon) in G190_TRGM.items():
                if kosul.startswith(f"cases.{kolon} ILIKE"):
                    kollar[ad] = derle(select(models.Case.id).where(stmt.whereclause))
        assert set(kollar) == set(G190_TRGM), f"arama kolları bulunamadı: {sorted(kollar)}"

        with engine.connect() as conn:
            conn.execute(text("SET enable_seqscan = off"))
            for ad, sql in kollar.items():
                plan = "\n".join(r[0] for r in conn.execute(text(f"EXPLAIN {sql}")).all())
                assert f"Bitmap Index Scan on {ad}" in plan, f"{ad} kullanılamadı:\n{plan}"
