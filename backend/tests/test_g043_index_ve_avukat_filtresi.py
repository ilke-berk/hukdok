"""Eksik index'ler + avukat filtresinin SQL'e taşınması (FAZ D 6.2-b / E7, G043).

İki katman:

* **DB'siz birim testleri** — katlama haritasının Python/SQL ikizliği, ön-eleme
  koşulunun SUPERSET özelliği (asıl doğruluk iddiası), migrasyon listesinin iç
  tutarlılığı. Her ortamda koşar.
* **`dbtest` testleri** — gerçek Postgres'te scratch veritabanı: yeni index'ler
  sıfırdan kurulumda gerçekten doğuyor mu, index'siz FK kaldı mı, planlayıcı
  fonksiyonel/kısmi index'leri sorguya UYGULAYABİLİYOR mu (ifade eşleşmesi) ve
  eski/yeni avukat filtresi aynı id kümesini mi veriyor.

Scratch DB altyapısı `test_migration_path.py`'den yeniden kullanılır (gerçek
`hukudok` veritabanına asla yazılmaz; DB yoksa SKIP).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import database
import models
from managers.case_manager import _lawyer_filter_case_ids, _lawyer_prefilter, _sql_folded
from managers.config_manager import DynamicConfig
from managers.lawyer_resolver import (
    _TR_FOLD,
    _norm_name,
    _resolve_lawyer_aliases,
    _split_persons,
    _value_matches,
)
from test_migration_path import (  # noqa: F401 — fixture'lar pytest tarafından toplanır
    _live_indexes,
    _run_init_db,
    _scratch_database,
    admin_engine,
)

# G043'ün eklediği index'ler (madde 30 + trigram sözlüğü).
YENI_INDEXLER = [
    "idx_case_documents_case_party",
    "idx_case_lawyers_lawyer",
    "ix_case_parties_client_id",   # mevcut kurulumlarda VARDI, sıfırdan kurulumda yoktu
    "idx_cases_status_sicak",
    "idx_cases_tracking_name_block",
]
YENI_TRGM_INDEX = "idx_cases_resp_lawyer_fold_trgm"


def _index_op_sqlleri():
    """Tüm ("index", ...) op'larındaki DDL ifadeleri."""
    return [sql for op in database._MIGRATIONS if op[0] == "index" for sql in op[2]]


def _sql_katlama_haritasi():
    """SQL translate() argümanlarının Python sözlük karşılığı.

    `strict=True`: dizgi uzunlukları farklıysa test burada patlar — sessizce
    kırpılmış bir harita üzerinden yanlış "eşit" hükmü verilmesin.
    """
    return dict(zip(database.SQL_FOLD_FROM, database.SQL_FOLD_TO, strict=True))


# ─── DB'siz: katlama haritasının Python/SQL ikizliği ─────────────────────────

def test_sql_katlama_haritasi_python_tr_fold_ile_birebir_ayni():
    """SQL translate() argümanları `_TR_FOLD`un TAM karşılığı olmalı.

    Bir karakter kayarsa hata çıkmaz: SQL sessizce farklı katlar, ön-eleme bazı
    adları ıskalar ve `_value_matches` onları hiç görmez → sonuç kümesi küçülür.
    Bu yüzden eşitlik iki yönlü denetlenir.
    """
    assert len(database.SQL_FOLD_FROM) == len(database.SQL_FOLD_TO), (
        "translate() kaynak/hedef dizgileri aynı uzunlukta olmalı, yoksa PG "
        "fazla karakterleri SİLER"
    )
    sql_harita = _sql_katlama_haritasi()
    python_harita = {chr(k): v for k, v in _TR_FOLD.items()}

    assert sql_harita == python_harita


def test_katlama_python_ve_sql_ayni_sonucu_verir_ornek_adlarda():
    """Gerçek avukat adlarında iki katlama aynı ASCII çıktıyı üretmeli."""
    sql_harita = str.maketrans(_sql_katlama_haritasi())
    for ad in ["TUGCE UNGOR", "Tuğçe Üngör Yanık", "AYSE GUL HANYALOGLU",
               "Cavide Işıl Bozdağ", "BÜŞRA KÜLLÜ", "İBRAHİM BAHADIR DOĞRU"]:
        # _norm_name = translate + lower + noktalama/ünvan temizliği; SQL tarafı
        # yalnız ilk ikisini yapar → SQL çıktısı Python token'larını İÇERMELİ.
        sql_ciktisi = ad.translate(sql_harita).lower()
        for token in _norm_name(ad).split():
            assert token in sql_ciktisi, f"{ad!r}: {token!r} SQL katlamasında yok"


def test_trgm_index_ifadesi_ile_sorgu_ifadesi_ayni_katlamayi_kullanir():
    """Index DDL'i ve çalışan sorgu AYNI translate argümanlarını taşımalı.

    Postgres ifade index'ini ayrıştırılmış ifade ağacıyla eşler; argüman farklıysa
    index sorguya HİÇ uygulanmaz — hata vermez, sessizce yavaşlar.
    """
    tablo, ifade = database._TRGM_INDEXES[YENI_TRGM_INDEX]
    assert tablo == "cases"
    assert ifade == f"({database.sql_folded_expr('responsible_lawyer_name')})"

    sorgu_sql = str(
        _sql_folded(models.Case.responsible_lawyer_name).compile(
            dialect=database.engine.dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    assert f"'{database.SQL_FOLD_FROM}'" in sorgu_sql
    assert f"'{database.SQL_FOLD_TO}'" in sorgu_sql
    assert "lower(" in sorgu_sql and "coalesce(" in sorgu_sql.lower()


# ─── DB'siz: ön-elemenin SUPERSET özelliği (asıl doğruluk iddiası) ───────────

def _prefilter_tokenlari(selected):
    """`_lawyer_filter_case_ids` ile aynı token kümesini üretir (test ikizi)."""
    aliases = _resolve_lawyer_aliases(selected)
    if aliases is None:
        return set(_norm_name(selected).split())
    core_tokens, code_norm, _surname, _uniq = aliases
    tokens = {t for t in core_tokens if t}
    if code_norm:
        tokens.add(code_norm)
    return tokens


@pytest.mark.parametrize("value", [
    "Av. Serap Turgal",
    "SERAP TURGAL",
    "Serap",
    "Turgal",
    "Av. Ayşe Gül Hanyaloğlu, Serap Turgal",
    "SERAPTUR",
    "stj. av. serap turgal",
    "Turgal,Serap",
])
def test_on_eleme_python_esleşmesini_asla_eleyemez(value):
    """SUPERSET İSPATININ birim karşılığı.

    `_value_matches` üç kuralının HİÇBİRİ, katlanmış değerde token kümesinden en az
    bir öğe geçmeden sağlanamaz (kural 1 kodun kendisi, kural 2 en az bir çekirdek
    token, kural 3 soyadın kendisi). Bu tutmazsa SQL ön-elemesi doğru satırları
    eler ve filtre SESSİZCE eksik sonuç verir.
    """
    DynamicConfig.get_instance().set_lawyers([
        {"code": "SERAPTUR", "name": "SERAP TURGAL"},
        {"code": "AYSEGULH", "name": "AYSE GUL HANYALOGLU"},
    ])
    aliases = _resolve_lawyer_aliases("SERAPTUR")
    assert aliases is not None
    core_tokens, code_norm, surname, uniq = aliases

    if not _value_matches(value, core_tokens, code_norm, surname, uniq):
        pytest.skip("bu değer zaten eşleşmiyor — superset iddiası devreye girmez")

    sql_harita = str.maketrans(_sql_katlama_haritasi())
    katlanmis = value.translate(sql_harita).lower()
    tokens = _prefilter_tokenlari("SERAPTUR")
    assert any(t in katlanmis for t in tokens), (
        f"{value!r} eşleşiyor ama ön-eleme token'larının hiçbiri katlanmış metinde yok"
    )


def test_cozulemeyen_secimde_de_on_eleme_superset():
    """aliases=None dalı: `sel_norm in _norm_name(part)` doğruysa her token geçer."""
    DynamicConfig.get_instance().set_lawyers([{"code": "XXX", "name": "BASKA KISI"}])
    secim = "serap turgal"
    sel_norm = _norm_name(secim)
    sql_harita = str.maketrans(_sql_katlama_haritasi())

    for value in ["Av. Serap Turgal", "SERAP TURGAL YILMAZ", "x, serap turgal"]:
        assert any(sel_norm in _norm_name(p) for p in _split_persons(value))
        katlanmis = value.translate(sql_harita).lower()
        assert any(t in katlanmis for t in sel_norm.split())


def test_token_yoksa_sorgu_hic_kosmaz():
    """Çekirdek token da kod da yoksa üç kural da eşleşemez → boş küme, SQL yok.

    `or_()` boş argümanla derlenirse SQLAlchemy her satırı geçiren bir koşul
    üretirdi; erken çıkış hem doğruluk hem de tam tablo taraması koruması.
    """
    DynamicConfig.get_instance().set_lawyers([{"code": "", "name": ""}])

    class _PatlayanDB:
        def query(self, *args, **kwargs):
            raise AssertionError("token yokken DB'ye hiç gidilmemeli")

    assert _lawyer_filter_case_ids(_PatlayanDB(), "   ", None) == set()


def test_on_eleme_kosulu_her_token_icin_bir_like_uretir():
    """Koşul OR'lu LIKE zinciri olmalı (AND olsaydı superset bozulurdu)."""
    # pyformat paramstyle'da literal '%' çift yazılır → karşılaştırmadan önce sadeleştir
    kosul = str(
        _lawyer_prefilter(models.Case.responsible_lawyer_name, {"serap", "turgal"}).compile(
            dialect=database.engine.dialect,
            compile_kwargs={"literal_binds": True},
        )
    ).replace("%%", "%")
    assert kosul.count("LIKE") == 2
    assert " OR " in kosul and " AND " not in kosul
    assert "'%serap%'" in kosul and "'%turgal%'" in kosul


# ─── DB'siz: migrasyon listesinin iç tutarlılığı ─────────────────────────────

def test_yeni_indexler_index_opunda_ve_if_not_exists():
    """Her yeni index koşulsuz koşan ("index", ...) op'unda ve idempotent olmalı.

    ("table"/"columns", ...) op'ları KOŞULLUDUR — modelde tanımlı bir tablo
    create_all'la doğduğunda gövdelerindeki index hiç koşmaz (G041 dersi).
    """
    sqller = _index_op_sqlleri()
    for ad in YENI_INDEXLER:
        eslesen = [s for s in sqller if f" {ad} " in f" {s} "]
        assert len(eslesen) == 1, f"{ad}: ('index', ...) op'unda tam 1 kez olmalı"
        assert "IF NOT EXISTS" in eslesen[0], f"{ad}: IF NOT EXISTS yok → ikinci açılışta patlar"


def test_kismi_index_yalniz_sicak_statuleri_kapsar():
    """cases.status index'i arşiv (MAHZEN) satırlarını DIŞARIDA bırakmalı."""
    ddl = next(s for s in _index_op_sqlleri() if "idx_cases_status_sicak" in s)
    assert "WHERE status <> 'MAHZEN'" in ddl, "kısmi olmayan index tablonun %79'unu boşuna tutar"


def test_tracking_no_index_i_route_ile_ayni_ifadeyi_kullanir():
    """routes/cases.py:139 `substr(tracking_no, 4, 10)` kullanıyor — index de öyle."""
    ddl = next(s for s in _index_op_sqlleri() if "idx_cases_tracking_name_block" in s)
    assert "substr(tracking_no, 4, 10)" in ddl


def test_yeni_trgm_index_i_index_opuna_yazilmadi():
    """BİLİNÇLİ: trigram index'i ("index", ...) op'una girerse sıfırdan kurulum ÖLÜR.

    "index" op'ları migrasyon döngüsünde, `CREATE EXTENSION pg_trgm`den ÖNCE koşar;
    gin_trgm_ops yokken DDL patlar ve fail-fast konteyneri durdurur.
    """
    assert YENI_TRGM_INDEX in database._TRGM_INDEXES
    assert all(YENI_TRGM_INDEX not in sql for sql in _index_op_sqlleri())


def test_yeni_indexler_dusurulecekler_listesiyle_catismiyor():
    """Madde 29 düşürüp madde 30 aynı adı ekleyemez (sonsuz git-gel olurdu)."""
    dusurulen = {ad for adlar in database._DUSURULECEK_INDEXLER.values() for ad in adlar}
    assert dusurulen.isdisjoint(set(YENI_INDEXLER) | {YENI_TRGM_INDEX})


# ─── dbtest: gerçek şema ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def g043_db(admin_engine):  # noqa: F811 — fixture import edildi
    """Sıfırdan init_db() koşmuş, avukat filtresi için veri basılmış scratch DB."""
    with _scratch_database(admin_engine, "g043") as engine:
        _run_init_db(engine)
        with engine.connect() as conn:
            # 2.400 dava: planlayıcının seq scan yerine index'i seçmesi için yeterli
            # hacim; adlar bilinçli olarak Türkçe karakterli (katlama sınavı).
            conn.execute(text("""
                INSERT INTO cases (tracking_no, status, active, tenant_id, responsible_lawyer_name)
                SELECT
                    'HA.' || (ARRAY['HANYALOGLU','ACARYUCELL','TURGALSERA'])[1 + (i % 3)]
                        || '.' || lpad((i / 3)::text, 4, '0') || '.X',
                    CASE WHEN i % 5 = 0 THEN 'DERDEST' ELSE 'MAHZEN' END,
                    true, NULL,
                    (ARRAY['Av. Serap Turgal', 'TUGCE UNGOR', 'Tuğçe Üngör',
                           'AYSE GUL HANYALOGLU', 'Av. Ayşe Gül Hanyaloğlu, Serap Turgal',
                           'Başka Biri', NULL])[1 + (i % 7)]
                FROM generate_series(1, 2400) AS i
            """))
            conn.execute(text("ANALYZE cases"))
            conn.commit()
        yield engine


@pytest.mark.dbtest
def test_yeni_indexler_sifirdan_kurulumda_semada_var(g043_db):
    """Migrasyon gerçekten koştu mu — ad değil TANIM üzerinden doğrulanır."""
    indexler = _live_indexes(g043_db)
    for ad in YENI_INDEXLER + [YENI_TRGM_INDEX]:
        assert ad in indexler, f"{ad} sıfırdan kurulumda oluşmadı"

    assert "WHERE ((status)::text <> 'MAHZEN'::text)" in indexler["idx_cases_status_sicak"]
    assert '"substr"(' in indexler["idx_cases_tracking_name_block"] or "substr(" in \
        indexler["idx_cases_tracking_name_block"]
    assert "gin" in indexler[YENI_TRGM_INDEX] and "translate" in indexler[YENI_TRGM_INDEX]


@pytest.mark.dbtest
def test_index_siz_fk_kolonu_kalmadi(g043_db):
    """Kabul kriterinin kaynağı olan sorgunun kendisi bekçiye dönüştürülür.

    Index'siz FK yalnız JOIN'i değil, referans verilen satırın silinmesini de
    tam tablo taramasına zorlar.
    """
    with g043_db.connect() as conn:
        eksik = conn.execute(text("""
            SELECT c.conrelid::regclass::text, a.attname
            FROM pg_constraint c
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
            WHERE c.contype = 'f'
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid
                  AND (i.indkey::int2[])[0:array_length(c.conkey, 1) - 1] = c.conkey
              )
            ORDER BY 1, 2
        """)).all()
    assert eksik == [], f"index'siz FK kolonu: {eksik}"


@pytest.mark.dbtest
def test_fonksiyonel_index_tracking_no_sorgusunda_kullaniliyor(g043_db):
    """routes/cases.py:139'un birebir sorgusu index taramasına düşmeli."""
    with g043_db.connect() as conn:
        plan = "\n".join(r[0] for r in conn.execute(text(
            "EXPLAIN SELECT tracking_no FROM cases "
            "WHERE substr(tracking_no, 4, 10) = 'HANYALOGLU' AND tenant_id IS NULL"
        )).all())
    assert "idx_cases_tracking_name_block" in plan, f"index kullanılmadı:\n{plan}"


@pytest.mark.dbtest
def test_kismi_status_index_i_sicak_degerde_kullanilir_mahzende_kullanilmaz(g043_db):
    """Kısmi index'in iki yüzü: DERDEST'te devreye girer, MAHZEN'de giremez."""
    with g043_db.connect() as conn:
        sicak = "\n".join(r[0] for r in conn.execute(text(
            "EXPLAIN SELECT count(*) FROM cases WHERE active AND status = 'DERDEST'"
        )).all())
        soguk = "\n".join(r[0] for r in conn.execute(text(
            "EXPLAIN SELECT count(*) FROM cases WHERE active AND status = 'MAHZEN'"
        )).all())
    assert "idx_cases_status_sicak" in sicak, f"sıcak değerde index kullanılmadı:\n{sicak}"
    assert "idx_cases_status_sicak" not in soguk, (
        "MAHZEN kısmi index'in DIŞINDA — kullanılması imkansız olmalı"
    )


@pytest.mark.dbtest
def test_avukat_on_elemesi_fonksiyonel_trgm_indexini_kullanabiliyor(g043_db):
    """İfade eşleşmesi sınavı: sorgunun ürettiği katlama index'inkiyle aynı mı?

    Az satırda planlayıcı seq scan'i tercih edebilir; burada ölçülen HIZ değil
    UYGULANABİLİRLİK — seq scan kapatıldığında index'e düşüyorsa ifadeler eşleşiyor
    demektir. Gerçek kazanç ölçümü görev raporunda (47,4 ms → 3,0 ms).
    """
    kosul = str(
        _lawyer_prefilter(models.Case.responsible_lawyer_name, {"serap", "turgal"}).compile(
            dialect=g043_db.dialect, compile_kwargs={"literal_binds": True},
        )
    )
    with g043_db.connect() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(r[0] for r in conn.execute(text(
            f"EXPLAIN SELECT id FROM cases WHERE {kosul}"
        )).all())
    assert YENI_TRGM_INDEX in plan, f"ifadeler eşleşmiyor, index uygulanamadı:\n{plan}"


def _eski_lawyer_filter(db, selected, tenant_id):
    """G043 ÖNCESİ implementasyon — eşdeğerlik sınavının referansı.

    Bilinçli olarak kopyalandı: davranış eşdeğerliği iddiası ancak eski kodun
    kendisine karşı ölçülebilir.
    """
    from managers.case_manager import _apply_tenant_filter
    aliases = _resolve_lawyer_aliases(selected)
    matched = set()
    if aliases is None:
        sel_norm = _norm_name(selected)
        if not sel_norm:
            return matched
        q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(
            models.Case.active.is_(True))
        q = _apply_tenant_filter(q, tenant_id)
        for cid, rn in q.all():
            if any(sel_norm in _norm_name(p) for p in _split_persons(rn)):
                matched.add(cid)
        for cid, nm in db.query(models.CaseLawyer.case_id, models.CaseLawyer.name).all():
            if sel_norm in _norm_name(nm):
                matched.add(cid)
        return matched
    core_tokens, code_norm, surname, surname_unique = aliases
    q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(
        models.Case.active.is_(True))
    q = _apply_tenant_filter(q, tenant_id)
    for cid, rn in q.all():
        if _value_matches(rn, core_tokens, code_norm, surname, surname_unique):
            matched.add(cid)
    for cid, nm in db.query(models.CaseLawyer.case_id, models.CaseLawyer.name).all():
        if _value_matches(nm, core_tokens, code_norm, surname, surname_unique):
            matched.add(cid)
    return matched


@pytest.mark.dbtest
def test_avukat_filtresi_eski_davranisla_birebir_ayni(g043_db):
    """En az 10 avukat + çözülemeyen seçimler: id kümeleri BİREBİR aynı olmalı.

    Ön-eleme bir satırı yanlışlıkla elerse burada `eksik` olarak görünür —
    performans iyileştirmesinin sessizce sonuç kaybettirmediğinin tek kanıtı bu.
    """
    lawyers = [
        {"code": "SERAPTUR", "name": "SERAP TURGAL"},
        {"code": "TUGCEUNG", "name": "TUGCE UNGOR"},
        {"code": "AYSEGULH", "name": "AYSE GUL HANYALOGLU"},
        {"code": "AYSEACAR", "name": "AYSE ACAR YUCEL"},
        {"code": "BBA", "name": "BARIŞ YÜCEL"},
        {"code": "H&A", "name": "Hanyaloğlu & Acar"},
        {"code": "DIS", "name": "Başka Büro / Harici"},
        {"code": "BUSRAKUL", "name": "BÜŞRA KÜLLÜ"},
        {"code": "CAVIDEIS", "name": "CAVİDE IŞIL BOZDAĞ"},
        {"code": "EMINEGUZ", "name": "EMİNE GÜZEL"},
        {"code": "MUHAMMED", "name": "MUHAMMED BULUTGÖÇER"},
    ]
    DynamicConfig.get_instance().set_lawyers(lawyers)
    secimler = (
        [lw["code"] for lw in lawyers]
        + [lw["name"] for lw in lawyers]
        + ["Serap Turgal", "üngör", "bilinmeyen kisi", "", "   "]
    )

    session = sessionmaker(bind=g043_db)()
    try:
        farklar = []
        for secim in secimler:
            eski = _eski_lawyer_filter(session, secim, None)
            yeni = _lawyer_filter_case_ids(session, secim, None)
            if eski != yeni:
                farklar.append((secim, sorted(eski - yeni)[:5], sorted(yeni - eski)[:5]))
        assert farklar == [], f"eski/yeni id kümesi farklı: {farklar}"
        # Sınav anlamlı olsun: en az bir seçim gerçekten dava bulmuş olmalı
        assert _lawyer_filter_case_ids(session, "SERAPTUR", None), "test verisi eşleşme üretmedi"
    finally:
        session.close()
