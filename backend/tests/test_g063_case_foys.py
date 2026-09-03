"""G063 — `case_foys`: SistemNo → kart + müvekkil föy eşleme tablosu.

Kullanıcı kararı (18.08): dava TEK kart kalır, müvekkiller kartın altında, kart
föy bazında BÖLÜNMEZ — ama karşı tarafın teslimleri sonsuza dek SistemNo
anahtarlıdır ve bir kartta birden çok SistemNo yaşar (1.211 mevcut kart 2+ föyü
birleşik taşıyor; TKU'da 1.537 çok üyeli grup / 4.030 satır). `cases.sistem_no`
tek kolonu bunu taşıyamaz; `case_foys` kartı bölmeden föyleri altına asar.

Katmanlar (test_g062 düzeni):

1. **Şema** — model/migrasyon kilitleri; kısıt `("index", ...)` op'unda (G041),
   kolonlarda `index=True` yok (G042), FK'lar index'li (G043). Ayrıca
   `cases.sistem_no`/`cases.tku_no`ya DOKUNULMADIĞI mekanik olarak kilitlenir.
2. **sqlite (StaticPool)** — davranış. G049 dersi: fixture migrasyonun index
   SQL'lerini sqlite'a OLDUĞU GİBİ uygular ve `PRAGMA foreign_keys=ON` ile FK
   aksiyonlarını açar; böylece hem idempotentlik hem RESTRICT birim koşuda
   GERÇEK kısıt kırmızısından döner, ön kontrol yeşilinden değil.
3. **dbtest (gerçek Postgres)** — 3-ortam kuralı: DATABASE_URL yoksa/şema
   göçmemişse (to_regclass) SKIP, FAIL değil. Yazımlar dış transaction'la
   TAMAMEN geri alınır — gerçek veritabanına iz bırakılmaz.
"""
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import database
import models
from database import _MIGRATIONS, Base
from db_errors import unique_violation_constraint
from managers import foy_map
from managers.foy_map import (
    get_case_foys,
    get_foy,
    map_sistem_no_to_case,
    upsert_foy,
)

TABLO = "case_foys"


def _index_ops(table):
    """`("index", table, [...])` op'larındaki SQL'lerin düz listesi."""
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


def _index_sql_by_name(table):
    """{index adı: SQL} — ad `... IF NOT EXISTS <ad> ON ...` kalıbından okunur."""
    sonuc = {}
    for sql in _index_ops(table):
        parcalar = sql.split()
        sonuc[parcalar[parcalar.index("EXISTS") + 1]] = sql
    return sonuc


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema
# ═══════════════════════════════════════════════════════════════════════════

def test_model_ve_kolonlar_gorev_taslagina_uygun():
    row = models.CaseFoy
    assert row.__tablename__ == TABLO
    columns = row.__table__.columns
    # Çekirdek = kimlik + bağ. Per-föy EK alanlar (dava değeri, son durum,
    # hizmet türü…) G063 turunda BİLİNÇLİ açılmadı — kolon seti FAZ F tam eşleme
    # turunda 68 sütunluk eşleme tablosuyla kararlaştırılır (YAGNI).
    # G113 (2026-09-03, kullanıcı kararı): kapsam işareti üçlüsü eklendi —
    # veri ekibinin Silinen_Föyler / Kapsam_Dışı sayfaları föyü SİLMEZ,
    # işaretler (belge koruma şartı). Küme yine TAM eşitlikle kilitli.
    assert set(columns.keys()) == {
        "id", "sistem_no", "case_id", "case_party_id", "tku_no", "hasar_no",
        "source", "created_at", "updated_at",
        "kapsam_durumu", "kapsam_gerekcesi", "kapsam_tarihi",
    }
    assert columns["sistem_no"].type.length == 50
    assert columns["tku_no"].type.length == 50
    assert columns["hasar_no"].type.length == 100
    assert columns["source"].type.length == 100
    # G113 sözleşmesi: NULL = kapsamda (varsayılan hâl, backfill YOK).
    assert columns["kapsam_durumu"].type.length == 20
    assert columns["kapsam_durumu"].nullable
    assert columns["kapsam_gerekcesi"].nullable
    assert columns["kapsam_tarihi"].nullable
    # Zorunlular: anahtarsız ya da kartsız föy eşlemeyi anlamsızlaştırır
    assert not columns["sistem_no"].nullable
    assert not columns["case_id"].nullable
    # Müvekkil bağı NULL kalabilir: föyün hangi tarafa ait olduğu ilk teslimde
    # bilinmeyebilir (partili aktarım).
    assert columns["case_party_id"].nullable


def test_fk_davranislari():
    """Kabul kriterinin şema karşılığı: iki FK de SESSİZ kopmaya kapalı."""
    fk_case = list(models.CaseFoy.__table__.c.case_id.foreign_keys)[0]
    assert fk_case.column.table.name == "cases"
    # ondelete BİLİNÇLİ VERİLMEDİ (NO ACTION/RESTRICT): dava soft-delete
    # kullanır, hard-delete föy bağını sessizce koparmamalı. CASCADE olsaydı
    # föy envanteri tek DELETE ile buharlaşırdı.
    assert fk_case.ondelete is None

    fk_party = list(models.CaseFoy.__table__.c.case_party_id.foreign_keys)[0]
    assert fk_party.column.table.name == "case_parties"
    # CaseDocument.case_party_id'nin SET NULL tuzağının tekrarı istenmiyor
    assert fk_party.ondelete == "RESTRICT"
    assert list(models.CaseDocument.__table__.c.case_party_id.foreign_keys)[0].ondelete == "SET NULL"

    # Kartın ORM ilişkisi de silmeyi taşımaz: cascade delete YOK, karar DB'nin
    # (passive_deletes="all") — ORM çocuğun FK'sını NULL'lamaya kalkışamaz.
    iliski = models.Case.foys.property
    assert not iliski.cascade.delete
    assert not iliski.cascade.delete_orphan
    assert iliski.passive_deletes == "all"


def test_kolonlarda_index_true_yok():
    """G042 dersi: `id` index'i PK ikizi olurdu; kalan index'ler (unique dahil)
    migrasyonda tanımlı — modeldeki `index=True`/`unique=True` ikiz `ix_*`
    üretir ve iki kurulum yolu FARKLI ADLA aynı index'i kurardı."""
    columns = models.CaseFoy.__table__.columns
    for ad in ("id", "sistem_no", "case_id", "case_party_id", "tku_no"):
        assert not columns[ad].index, f"{ad}: index migrasyonda tanımlı, modelde değil"
    assert not columns["sistem_no"].unique, "UNIQUE migrasyonda tanımlı (G041)"


def test_unique_ve_indexler_index_opunda_ve_idempotent():
    """G041 tuzağı: kısıt tablo op'una gömülürse HİÇ koşmaz."""
    sqls = _index_sql_by_name(TABLO)
    assert sqls, f"{TABLO} için ('index', ...) op'u yok"

    tekil = sqls.get("uq_case_foys_sistem_no")
    assert tekil, "uq_case_foys_sistem_no migrasyonda tanımlı değil"
    assert "UNIQUE" in tekil.upper()
    assert "(sistem_no)" in tekil

    # G043 FK kuralı: index'siz FK kolonu kalmaz (bekçi:
    # test_g043_index_ve_avukat_filtresi.py::test_index_siz_fk_kolonu_kalmadi)
    assert "(case_id)" in sqls["idx_case_foys_case"]
    assert "(case_party_id)" in sqls["idx_case_foys_case_party"]
    # Görev taslağının açık kalemi: "tku_no VARCHAR(50) index'li"
    assert "(tku_no)" in sqls["idx_case_foys_tku"]

    for sql in sqls.values():
        assert "IF NOT EXISTS" in sql, sql


def test_tablo_op_u_bilincli_yok_create_all_yaratiyor():
    """Tablo modelde tanımlı → create_all yaratır; ('table', ...) op'u ölü kod
    olurdu (init_db create_all'ı ÖNCE koşturur — G045/G062 ile aynı yol)."""
    assert not [op for op in _MIGRATIONS if op[0] == "table" and op[1] == TABLO]
    assert TABLO in Base.metadata.tables


def test_indexler_dusurulecekler_listesiyle_catismiyor():
    """Madde 29 (G042 temizliği) yeni index'lerden birini düşürüyor olmamalı."""
    dusurulen = {ad for adlar in database._DUSURULECEK_INDEXLER.values() for ad in adlar}
    assert TABLO not in database._DUSURULECEK_INDEXLER
    assert dusurulen.isdisjoint({
        "uq_case_foys_sistem_no", "idx_case_foys_case",
        "idx_case_foys_case_party", "idx_case_foys_tku",
    })


def test_cases_sistem_no_ve_tku_no_dokunulmadi():
    """Görevin 'dokunma' kalemi mekanik kilit: föy tablosu bu iki kolonun
    yerine geçmez, nihai tekilleştirme FAZ F aktarım turunun işidir."""
    columns = models.Case.__table__.columns
    assert columns["sistem_no"].type.length == 100
    assert columns["sistem_no"].unique and columns["sistem_no"].index
    assert columns["tku_no"].type.length == 100
    assert columns["tku_no"].index and not columns["tku_no"].unique

    cases_kolon_oplari = [op for op in _MIGRATIONS if op[0] == "columns" and op[1] == "cases"]
    spec = next(o[2]["sistem_no"] for o in cases_kolon_oplari if "sistem_no" in o[2])
    assert spec[0] == "VARCHAR(100)"
    assert spec[1] == [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_sistem_no ON cases(sistem_no)"
    ]
    # Föy tablosu İKİNCİ bir yazıcı doğurmadı: tek yazma yolu cases'in bu iki
    # kolonuna hiç dokunmaz ("cases.sistem_no" metni yalnız docstring'de geçer,
    # `case.sistem_no` ataması hiç yok).
    kaynak = Path(foy_map.__file__).read_text(encoding="utf-8")
    for yasak in ("case.sistem_no", "case.tku_no", "Case.sistem_no", "Case.tku_no"):
        assert yasak not in kaynak, f"foy_map {yasak} kolonuna dokunuyor"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite (kısıt + FK aksiyonları migrasyondan uygulanır, G049)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env():
    """Paylaşılan in-memory sqlite + migrasyon index'leri + FK zorlaması.

    G049 dersi: `create_all` yalnız MODELDEKİ kısıtları kurar;
    `uq_case_foys_sistem_no` migrasyonda tanımlı olduğu için fixture'a OLDUĞU
    GİBİ uygulanır. `PRAGMA foreign_keys=ON` olmadan sqlite FK aksiyonlarını
    (RESTRICT) hiç çalıştırmaz ve silme testi sahte yeşil verirdi.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops(TABLO):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _dava(db, tracking_no="HA.X.0001.2026", **extra):
    case = models.Case(
        tracking_no=tracking_no, status="DERDEST",
        maddi_tazminat=0, manevi_tazminat=0, **extra,
    )
    db.add(case)
    db.flush()
    return case


def _taraf(db, case, name, role="Davacı", party_type="CLIENT"):
    party = models.CaseParty(case_id=case.id, name=name, role=role, party_type=party_type)
    db.add(party)
    db.flush()
    return party


def test_dort_foy_tek_kart_dort_muvekkil(db_env):
    """Kabul kriteri (id-7189/7190/7191/7192 senaryosu): 4 föy → 1 kart, 4
    farklı case_party bağı. Kart BÖLÜNMEZ; föyler kartın altında yaşar."""
    db = db_env()
    try:
        case = _dava(db)
        muvekkiller = [_taraf(db, case, ad) for ad in ("Ali V.", "Ayşe K.", "Mert D.", "Zeynep T.")]
        # id-7189/7190/7191/7192: aynı olayın (TKU-784) dört föyü, dört müvekkil
        eslesme = zip(muvekkiller, (7189, 7190, 7191, 7192), strict=True)
        for i, (party, no) in enumerate(eslesme, start=1):
            upsert_foy(
                db, case,
                sistem_no=f"SSTMN-{no}",
                case_party_id=party.id,
                tku_no="TKU-784",
                hasar_no=f"HSR-{i}",
                source="HUKDOK_TESLIM_2026-08-10",
            )
        db.commit()

        foyler = get_case_foys(db, case.id)
        assert [f.sistem_no for f in foyler] == [
            "SSTMN-7189", "SSTMN-7190", "SSTMN-7191", "SSTMN-7192",
        ]
        assert {f.case_id for f in foyler} == {case.id}                  # tek kart
        assert len({f.case_party_id for f in foyler}) == 4               # dört taraf
        # Föyler arası FARKLI kalan kimlik alanı ezilmedi (10.08 ölçümü:
        # Hasar No 144 grupta föyler arası farklı)
        assert [f.hasar_no for f in foyler] == ["HSR-1", "HSR-2", "HSR-3", "HSR-4"]
        assert {f.tku_no for f in foyler} == {"TKU-784"}                 # ortak olay
        assert len(case.foys) == 4
    finally:
        db.close()


def test_ayni_sistem_no_ikinci_upsertte_ikilenmiyor_gunceleniyor(db_env):
    """Kabul kriteri: aktarımın idempotency anahtarı. Teslim partiler hâlinde
    ve düzeltme listeleriyle tekrar gelecek — satır İKİLENMEZ, güncellenir."""
    db = db_env()
    try:
        case = _dava(db)
        ilk = upsert_foy(db, case, sistem_no="SSTMN-9425", hasar_no="HSR-1",
                         source="HUKDOK_TESLIM_2026-08-10")
        db.commit()

        ikinci = upsert_foy(db, case, sistem_no="SSTMN-9425", hasar_no="HSR-2",
                            source="DUZELTME_2026-08-18")
        db.commit()

        assert ikinci.id == ilk.id                       # aynı satır
        assert len(get_case_foys(db, case.id)) == 1      # ikilenmedi
        assert ikinci.hasar_no == "HSR-2"                # güncellendi
        assert ikinci.source == "DUZELTME_2026-08-18"
    finally:
        db.close()


def test_upsert_bosluk_farkiyla_gelen_ayni_foyu_ikilemiyor(db_env):
    """Anahtar normalize edilir: "  SSTMN-9425 " ile "SSTMN-9425" aynı föydür.
    Normalize edilmeseydi unique kısıt ikisini AYRI föy sayardı."""
    db = db_env()
    try:
        case = _dava(db)
        ilk = upsert_foy(db, case, sistem_no="SSTMN-9425")
        ikinci = upsert_foy(db, case, sistem_no="  SSTMN-9425 ")
        db.commit()

        assert ikinci.id == ilk.id
        assert len(get_case_foys(db, case.id)) == 1
        assert get_foy(db, "SSTMN-9425") is not None
    finally:
        db.close()


def test_verilmeyen_alan_korunuyor_bosaltilmiyor(db_env):
    """`None` "boşalt" değil "bu teslimde yok" demektir — partili teslimde
    eksik sütun mevcut değeri silmemeli."""
    db = db_env()
    try:
        case = _dava(db)
        party = _taraf(db, case, "Ali V.")
        upsert_foy(db, case, sistem_no="SSTMN-1", case_party_id=party.id,
                   tku_no="TKU-1", hasar_no="HSR-1", source="ILK")
        db.commit()

        satir = upsert_foy(db, case, sistem_no="SSTMN-1", hasar_no="HSR-2")
        db.commit()

        assert satir.hasar_no == "HSR-2"          # verilen güncellendi
        assert satir.case_party_id == party.id    # verilmeyenler korundu
        assert satir.tku_no == "TKU-1"
        assert satir.source == "ILK"
    finally:
        db.close()


def test_sistem_no_kirpilmaz_reddedilir(db_env):
    """Kimlik alanı: kırpma iki farklı föyü tek satıra çökertirdi (unique!) —
    sessiz veri kaybı yerine gürültülü ret."""
    db = db_env()
    try:
        case = _dava(db)
        with pytest.raises(ValueError, match="sistem_no"):
            upsert_foy(db, case, sistem_no="S" * 51)
        with pytest.raises(ValueError, match="sistem_no"):
            upsert_foy(db, case, sistem_no="   ")
        with pytest.raises(ValueError, match="sistem_no"):
            upsert_foy(db, case, sistem_no=None)
        db.commit()
        assert get_case_foys(db, case.id) == []
    finally:
        db.close()


def test_kimlik_disi_alanlar_kolon_sinirina_kirpiliyor(db_env):
    """Taşan hasar numarası föyün tamamını düşürmez (orantılılık,
    stage_decisions._clamped gerekçesi) — kimlik alanının aksine."""
    db = db_env()
    try:
        case = _dava(db)
        satir = upsert_foy(db, case, sistem_no="SSTMN-1", tku_no="T" * 80,
                           hasar_no="H" * 150, source="S" * 300)
        db.commit()

        assert len(satir.tku_no) == 50
        assert len(satir.hasar_no) == 100
        assert len(satir.source) == 100
    finally:
        db.close()


def test_capraz_kart_taraf_bagi_reddediliyor(db_env):
    """Föy kartın altında yaşar; tarafı da o kartın tarafı olmak zorunda."""
    db = db_env()
    try:
        case = _dava(db)
        baska = _dava(db, tracking_no="HA.X.0002.2026")
        yabanci = _taraf(db, baska, "Başkasının Müvekkili")

        with pytest.raises(ValueError, match="case_party_id"):
            upsert_foy(db, case, sistem_no="SSTMN-1", case_party_id=yabanci.id)
        with pytest.raises(ValueError, match="case_party_id"):
            upsert_foy(db, case, sistem_no="SSTMN-1", case_party_id=999999)
        db.commit()
        assert get_case_foys(db, case.id) == []
    finally:
        db.close()


def test_foy_kart_degistirince_eski_taraf_bagi_dusuyor(db_env):
    """Düzeltme listesi föyü doğru karta taşıyabilir; eski kartın tarafını yeni
    kartın föyünde tutmak sessiz veri çöpü olurdu."""
    db = db_env()
    try:
        case = _dava(db)
        hedef = _dava(db, tracking_no="HA.X.0002.2026")
        party = _taraf(db, case, "Ali V.")
        upsert_foy(db, case, sistem_no="SSTMN-1", case_party_id=party.id, tku_no="TKU-1")
        db.commit()

        tasinan = upsert_foy(db, hedef, sistem_no="SSTMN-1", source="DUZELTME")
        db.commit()

        assert tasinan.case_id == hedef.id
        assert tasinan.case_party_id is None      # eski kartın tarafı düştü
        assert tasinan.tku_no == "TKU-1"          # kimlik alanları korundu
        assert get_case_foys(db, case.id) == []
        assert [f.sistem_no for f in get_case_foys(db, hedef.id)] == ["SSTMN-1"]
    finally:
        db.close()


def test_taraf_silme_foy_bagi_varken_engelleniyor(db_env):
    """Kabul kriteri (RESTRICT): `CaseDocument.case_party_id`nin SET NULL
    tuzağının tekrarı istenmiyor — föyün hangi müvekkile ait olduğu bir taraf
    silmesiyle sessizce unutulamaz."""
    db = db_env()
    try:
        case = _dava(db)
        party = _taraf(db, case, "Ali V.")
        bagsiz = _taraf(db, case, "Karşı Taraf", role="Davalı", party_type="COUNTER")
        upsert_foy(db, case, sistem_no="SSTMN-1", case_party_id=party.id)
        db.commit()

        db.delete(party)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        assert get_foy(db, "SSTMN-1").case_party_id == party.id   # bağ duruyor
        # Föy bağı OLMAYAN taraf serbestçe silinebilir — kısıt geniş değil, dar
        db.delete(bagsiz)
        db.commit()
        assert len(get_case_foys(db, case.id)) == 1
    finally:
        db.close()


def test_dava_soft_delete_foyleri_silmiyor(db_env):
    """Kabul kriteri: envanter korunur. Dava silmesi SOFT'tur
    (routes/cases.py: deleted_at + deleted_by + active=False) — föy satırları
    ve aktarımın idempotency anahtarı yerinde kalır."""
    db = db_env()
    try:
        case = _dava(db)
        party = _taraf(db, case, "Ali V.")
        for no in ("SSTMN-1", "SSTMN-2"):
            upsert_foy(db, case, sistem_no=no, case_party_id=party.id)
        db.commit()

        case.deleted_at = datetime(2026, 8, 19, 0, 0, 0)
        case.deleted_by = "test@lexis.com.tr"
        case.delete_reason = "mükerrer kayıt"
        case.active = False
        db.commit()

        foyler = get_case_foys(db, case.id)
        assert [f.sistem_no for f in foyler] == ["SSTMN-1", "SSTMN-2"]
        assert all(f.case_party_id == party.id for f in foyler)
        assert map_sistem_no_to_case(db, ["SSTMN-1", "SSTMN-2"]) == {
            "SSTMN-1": case.id, "SSTMN-2": case.id,
        }
    finally:
        db.close()


def test_map_sistem_no_to_case_toplu_ve_bilinmeyeni_atlıyor(db_env):
    """Aktarımın sıcak sorgusu: elindeki föy listesini TEK turda çözer.
    Bilinmeyen anahtar sözlükte YOKTUR (None değeri değil) — 'kartı var mı'
    sorusu `in` ile sorulur."""
    db = db_env()
    try:
        case = _dava(db)
        baska = _dava(db, tracking_no="HA.X.0002.2026")
        upsert_foy(db, case, sistem_no="SSTMN-1")
        upsert_foy(db, case, sistem_no="SSTMN-2")
        upsert_foy(db, baska, sistem_no="SSTMN-3")
        db.commit()

        sonuc = map_sistem_no_to_case(
            db, ["SSTMN-1", " SSTMN-3 ", "SSTMN-1", "YOK-1", None, "  "]
        )
        assert sonuc == {"SSTMN-1": case.id, "SSTMN-3": baska.id}
        assert "YOK-1" not in sonuc
        assert map_sistem_no_to_case(db, []) == {}
        assert map_sistem_no_to_case(db, None) == {}
    finally:
        db.close()


def test_get_foy_bilinmeyen_ve_bos_anahtarda_none(db_env):
    db = db_env()
    try:
        case = _dava(db)
        upsert_foy(db, case, sistem_no="SSTMN-1")
        db.commit()

        assert get_foy(db, "YOK") is None
        assert get_foy(db, "") is None
        assert get_foy(db, None) is None
    finally:
        db.close()


def test_ham_insert_mukerrer_sistem_no_kisita_takiliyor(db_env):
    """Son savunma: tek yazma yolunu atlayan ham INSERT'i kısıt durdurur —
    yani idempotentlik ön kontrolün değil ŞEMANIN garantisi (G049)."""
    db = db_env()
    try:
        case = _dava(db)
        upsert_foy(db, case, sistem_no="SSTMN-1")
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                text("INSERT INTO case_foys (sistem_no, case_id) VALUES ('SSTMN-1', :c)"),
                {"c": case.id},
            )
        db.rollback()
        assert len(get_case_foys(db, case.id)) == 1
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. dbtest — gerçek Postgres (3-ortam kuralı: to_regclass + SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg():
    """Gerçek Postgres bağlantısı; DB yoksa YA DA şema göçmemişse modül SKIP.

    Çıplak CI Postgres'i bağlantı verir ama tablo sunmaz — to_regclass kontrolü
    o ortamı FAIL yerine SKIP yapar (test_g062 deseni). Testler yazdıklarını dış
    transaction'la geri alır; gerçek veritabanına kalıcı satır bırakılmaz.
    """
    url = os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL postgresql:// değil")

    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G063 dbtest atlandı")

    try:
        eksik = [
            t for t in ("cases", "case_parties", TABLO)
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar() is None
        ]
    except Exception as exc:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema sorgulanamadı ({type(exc).__name__})")
    if eksik:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema göçmemiş — eksik tablo: {', '.join(eksik)} (migrasyon koşmamış)")

    conn.rollback()          # örtük transaction'ı kapat — testler kendi begin'ini kurar
    try:
        yield conn
    finally:
        conn.close()
        engine.dispose()


def _benzersiz_tracking() -> str:
    return f"HA.G063.{os.getpid()}.{uuid.uuid4().hex[:8]}"


def _benzersiz_sistem_no() -> str:
    return f"G063-{uuid.uuid4().hex[:12]}"


def _kart(pg, tracking):
    """Gerçek şemaya YALNIZ kart yazar (dış transaction açık)."""
    return pg.execute(
        text("INSERT INTO cases (tracking_no, status) VALUES (:t, 'DERDEST') RETURNING id"),
        {"t": tracking},
    ).scalar()


def _kart_ve_taraf(pg, tracking):
    """Gerçek şemaya kart + taraf yazar, id'lerini döner (dış transaction açık)."""
    case_id = _kart(pg, tracking)
    party_id = pg.execute(
        text("INSERT INTO case_parties (case_id, name, role, party_type) "
             "VALUES (:c, 'Ali V.', 'Davacı', 'CLIENT') RETURNING id"),
        {"c": case_id},
    ).scalar()
    return case_id, party_id


@pytest.mark.dbtest
def test_unique_index_gercek_semada_var(pg):
    """Kabul kriteri: `sistem_no` UNIQUE'i HER kurulum yolunda doğuyor —
    burada yaşayan şema ölçülür (sıfırdan kurulum yolu test_migration_path'in
    genel taramasında)."""
    tanim = pg.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'uq_case_foys_sistem_no'"
    )).scalar()
    fk_indexleri = [r[0] for r in pg.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = 'case_foys'"
    )).all()]
    pg.rollback()
    assert tanim, "uq_case_foys_sistem_no şemada yok — index op'u koşmamış"
    assert "UNIQUE" in tanim.upper() and "sistem_no" in tanim
    for ad in ("idx_case_foys_case", "idx_case_foys_case_party", "idx_case_foys_tku"):
        assert ad in fk_indexleri, f"{ad} şemada yok"


@pytest.mark.dbtest
def test_upsert_gercek_postgreste_idempotent(pg):
    """Aynı föyün ikinci yazımı satır ikilemez; dört föy tek kartta yaşar."""
    tracking = _benzersiz_tracking()
    anahtarlar = [_benzersiz_sistem_no() for _ in range(4)]
    trans = pg.begin()
    session = Session(bind=pg)
    try:
        case = models.Case(tracking_no=tracking, status="DERDEST")
        session.add(case)
        session.flush()
        party = models.CaseParty(case_id=case.id, name="Ali V.", role="Davacı",
                                 party_type="CLIENT")
        session.add(party)
        session.flush()

        for no in anahtarlar:
            upsert_foy(session, case, sistem_no=no, case_party_id=party.id,
                       tku_no="TKU-784", source="g063-dbtest")
        # İkinci tur (düzeltme listesi): aynı anahtarlar, güncellenen hasar no
        for no in anahtarlar:
            upsert_foy(session, case, sistem_no=no, hasar_no="HSR-9",
                       source="g063-dbtest-2")
        session.flush()

        foyler = get_case_foys(session, case.id)
        assert len(foyler) == 4
        assert {f.hasar_no for f in foyler} == {"HSR-9"}
        assert {f.case_party_id for f in foyler} == {party.id}    # korundu
        assert map_sistem_no_to_case(session, anahtarlar) == {no: case.id for no in anahtarlar}
    finally:
        session.close()
        trans.rollback()

    kalan = pg.execute(
        text("SELECT count(*) FROM cases WHERE tracking_no = :t"), {"t": tracking}
    ).scalar()
    pg.rollback()
    assert kalan == 0


@pytest.mark.dbtest
def test_ham_mukerrer_insert_kisit_adiyla_donuyor(pg):
    """Son savunma: tek yazma yolunu atlayan ham INSERT'i kısıt durdurur ve
    ihlal edilen kısıt ADI ile döner (db_errors sözleşmesi)."""
    tracking = _benzersiz_tracking()
    sistem_no = _benzersiz_sistem_no()
    trans = pg.begin()
    try:
        case_id = _kart(pg, tracking)
        pg.execute(
            text("INSERT INTO case_foys (sistem_no, case_id) VALUES (:s, :c)"),
            {"s": sistem_no, "c": case_id},
        )
        with pytest.raises(IntegrityError) as exc:
            pg.execute(
                text("INSERT INTO case_foys (sistem_no, case_id) VALUES (:s, :c)"),
                {"s": sistem_no, "c": case_id},
            )
        assert unique_violation_constraint(exc.value) == "uq_case_foys_sistem_no"
    finally:
        trans.rollback()


@pytest.mark.dbtest
def test_taraf_silme_gercek_postgreste_restrict_ile_engelleniyor(pg):
    """Kabul kriteri, gerçek FK aksiyonuyla: föy bağı olan taraf silinemez."""
    tracking = _benzersiz_tracking()
    trans = pg.begin()
    try:
        case_id, party_id = _kart_ve_taraf(pg, tracking)
        pg.execute(
            text("INSERT INTO case_foys (sistem_no, case_id, case_party_id) "
                 "VALUES (:s, :c, :p)"),
            {"s": _benzersiz_sistem_no(), "c": case_id, "p": party_id},
        )
        with pytest.raises(IntegrityError) as exc:
            pg.execute(text("DELETE FROM case_parties WHERE id = :p"), {"p": party_id})
        assert getattr(exc.value.orig, "pgcode", None) == "23503"   # foreign_key_violation
        # Engelin kaynağı BU tablo olmalı — başka bir FK'nın yeşili sayılmasın
        assert "case_foys" in str(exc.value.orig)
    finally:
        trans.rollback()


@pytest.mark.dbtest
def test_kart_hard_delete_foy_varken_engelleniyor(pg):
    """`case_id` FK'sında ondelete VERİLMEDİ: dava hard-delete'i föy envanterini
    sessizce buharlaştıramaz (soft-delete zaten satırlara dokunmaz)."""
    tracking = _benzersiz_tracking()
    trans = pg.begin()
    try:
        # Taraf BİLİNÇLİ yazılmıyor: `case_parties.case_id` FK'sı da
        # ondelete'siz — o da 23503 verir ve test yanlış sebeple yeşile düşerdi.
        case_id = _kart(pg, tracking)
        pg.execute(
            text("INSERT INTO case_foys (sistem_no, case_id) VALUES (:s, :c)"),
            {"s": _benzersiz_sistem_no(), "c": case_id},
        )
        with pytest.raises(IntegrityError) as exc:
            pg.execute(text("DELETE FROM cases WHERE id = :c"), {"c": case_id})
        assert getattr(exc.value.orig, "pgcode", None) == "23503"
        assert "case_foys" in str(exc.value.orig)
    finally:
        trans.rollback()
