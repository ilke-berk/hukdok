"""G062 — `case_stage_decisions`: aşama/karar tarihçesi + BELİRSİZ damgası + son-aşama senkronu.

Kaynak: KARAR_ASAMALARI_TASARIM_PAKETI_2026-08-17. Karar künyesi `cases`te
aşama başına TEK SLOT'tu; ikinci karar eskisini eziyordu (kanıt vakası
id-2271: Danıştay 2023 Bozma + 2026 Onama). Desen `case_esas_numbers`ın
(G045/G049) karar ikizi: aşama etiketli satırlar + tek yazma yolu
(`managers/stage_decisions.py`) + türetilmiş tek-slot fotoğraf.

Katmanlar (test_g045 düzeni):

1. **Şema** — model/migrasyon/registry kilitleri; kısıt `("index", ...)`
   op'unda (G041), kolonlarda `index=True` yok (G042).
2. **sqlite (StaticPool)** — davranış. G049 dersi uygulanır: fixture
   migrasyonun index SQL'lerini sqlite'a OLDUĞU GİBİ uygular, böylece
   `uq_case_stage_decision` birim koşuda da GERÇEKTEN zorlanır — mükerrer
   testi kısıt kırmızısından döner, ön kontrol yeşilinden değil.
3. **dbtest (gerçek Postgres)** — 3-ortam kuralı: DATABASE_URL yoksa/şema
   göçmemişse (to_regclass) SKIP, FAIL değil (çıplak CI Postgres'i tablo
   sunmaz; deploy kapısı migrasyonlu kendi Postgres'ini kurar; lokal konteyner
   dolu şema sunar). Yazımlar dış transaction'la TAMAMEN geri alınır —
   gerçek veritabanına iz bırakılmaz.
"""
import os
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from database import _MIGRATIONS, Base
from db_errors import unique_violation_constraint
from managers import seed_data, stage_decisions
from managers.stage_decisions import (
    DECISION_STAGES,
    DOGRULAMA_DURUMLARI,
    DuplicateStageDecisionError,
    add_stage_decision,
    delete_stage_decision,
    get_stage_decisions,
)

TABLO = "case_stage_decisions"

# Karar listeleri (G060) — testin bağımsız referansı seed sabitleridir;
# fixture bu satırları doğrudan yazar (tam seed_all_lists koşusu gereksiz).
_KARAR_LISTELERI = (
    (models.LocalDecision, seed_data.LOCAL_DECISIONS),
    (models.AppealDecision, seed_data.APPEAL_DECISIONS),
    (models.CassationDecision, seed_data.CASSATION_DECISIONS),
    (models.RevisionDecision, seed_data.REVISION_DECISIONS),
)


def _index_ops(table):
    """`("index", table, [...])` op'larındaki SQL'lerin düz listesi."""
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema
# ═══════════════════════════════════════════════════════════════════════════

def test_model_ve_kolonlar_gorev_taslagina_uygun():
    row = models.CaseStageDecision
    assert row.__tablename__ == TABLO
    columns = row.__table__.columns
    assert set(columns.keys()) == {
        "id", "case_id", "stage", "sira_no", "mahkeme", "esas_no", "karar_no",
        "karar_tarihi", "karar_durumu", "teblig_tarihi", "basvuran_taraf",
        "aciklama", "dogrulama_durumu", "kaynak_id", "source", "created_at",
    }
    # Sınırlar cases'teki kardeş slot kolonlarıyla hizalı — fotoğraf kopyası
    # hedef kolondan asla uzun olamaz (taşma 500'ü fotoğrafta üretirdi)
    assert columns["stage"].type.length == 20            # case_esas_numbers.stage ile aynı
    assert columns["mahkeme"].type.length == 200         # istinaf_mahkemesi 200
    assert columns["esas_no"].type.length == 50
    assert columns["karar_no"].type.length == 50
    assert columns["karar_durumu"].type.length == 100    # *_karar_durumu kolonları 100
    assert columns["basvuran_taraf"].type.length == 50   # istinaf_basvuran_taraf 50
    assert columns["dogrulama_durumu"].type.length == 20
    assert columns["source"].type.length == 100
    # Zorunlular: davasız/aşamasız/sırasız satır tarihçeyi anlamsızlaştırır
    assert not columns["case_id"].nullable
    assert not columns["stage"].nullable
    assert not columns["sira_no"].nullable
    assert not columns["dogrulama_durumu"].nullable


def test_dogrulama_damgasi_iki_katmanda_belirsiz():
    """Python default'u VE server_default: tek yazma yolunu atlayan ham INSERT
    bile damgasız satır bırakamaz (tahmin yasağının şema karşılığı)."""
    col = models.CaseStageDecision.__table__.columns["dogrulama_durumu"]
    assert col.default is not None and col.default.arg == "BELIRSIZ"
    assert col.server_default is not None and str(col.server_default.arg) == "BELIRSIZ"


def test_fk_davranislari():
    fk_case = list(models.CaseStageDecision.__table__.c.case_id.foreign_keys)[0]
    assert fk_case.ondelete == "CASCADE"    # case_esas_numbers ile aynı gerekçe
    fk_kaynak = list(models.CaseStageDecision.__table__.c.kaynak_id.foreign_keys)[0]
    assert fk_kaynak.column.table.name == TABLO   # self-FK: karar soy zinciri
    # Kaynak silinirse türeyen kayıt ÖKSÜZ kalır ama SİLİNMEZ
    assert fk_kaynak.ondelete == "SET NULL"
    assert models.Case.stage_decisions.property.cascade.delete_orphan


def test_id_ve_case_id_uzerinde_index_true_yok():
    """G042 dersi: `id` index'i PK ikizi olurdu; `case_id`yi
    uq_case_stage_decision (case_id, stage, sira_no) ÖNEK kolonuyla karşılar.
    `kaynak_id`nin FK index'i modelde DEĞİL migrasyonda tanımlı (`index=True`
    ikiz `ix_*` üretirdi — G042'nin temizlediği sınıf)."""
    columns = models.CaseStageDecision.__table__.columns
    assert not columns["id"].index
    assert not columns["case_id"].index
    assert not columns["kaynak_id"].index, "FK index'i migrasyonda tanımlı, modelde değil"


def test_unique_kisit_index_opunda_ve_idempotent():
    """G041 tuzağı: kısıt tablo op'una gömülürse HİÇ koşmaz."""
    sqls = _index_ops(TABLO)
    assert sqls, f"{TABLO} için ('index', ...) op'u yok"
    tekil = next((s for s in sqls if "uq_case_stage_decision" in s), None)
    assert tekil, "uq_case_stage_decision migrasyonda tanımlı değil"
    assert "UNIQUE" in tekil.upper()
    assert "(case_id, stage, sira_no)" in tekil
    # G043 FK kuralı: kaynak_id self-FK'sı index'siz kalamaz (bekçi:
    # test_g043_index_ve_avukat_filtresi.py::test_index_siz_fk_kolonu_kalmadi)
    kaynak = next((s for s in sqls if "idx_case_stage_decisions_kaynak" in s), None)
    assert kaynak and "(kaynak_id)" in kaynak
    for sql in sqls:
        assert "IF NOT EXISTS" in sql, sql


def test_tablo_op_u_bilincli_yok_create_all_yaratiyor():
    """Tablo modelde tanımlı → create_all yaratır; ('table', ...) op'u ölü kod
    olurdu (init_db create_all'ı ÖNCE koşturur — G045 madde 32 ile aynı yol)."""
    assert not [op for op in _MIGRATIONS if op[0] == "table" and op[1] == TABLO]
    assert TABLO in Base.metadata.tables


def test_asama_kumesi_esas_ikiziyle_hizali_onceki_haric():
    """Etiket seti case_esas_numbers ile AYNI, ONCEKI HARİÇ — o yalnız esas
    numarası kavramıdır (görevsizlik öncesi numara), kararın aşaması olamaz."""
    from managers.case_manager import ESAS_STAGES

    assert DECISION_STAGES == ("YEREL", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME")
    assert set(DECISION_STAGES) == set(ESAS_STAGES) - {"ONCEKI"}


def test_dogrulama_etiket_kumesi():
    assert DOGRULAMA_DURUMLARI == ("UYAP", "BELGE", "TURETILDI", "BELIRSIZ")


def test_stage_g060_listesi_eslesmesi():
    """Her aşamanın kapalı havuzu G060'ın resmi liste modeline bağlı."""
    assert stage_decisions.STAGE_DECISION_LISTS == {
        "YEREL": models.LocalDecision,
        "ISTINAF": models.AppealDecision,
        "TEMYIZ": models.CassationDecision,
        "KARAR_DUZELTME": models.RevisionDecision,
    }


def test_fotograf_haritasi_gercek_kolonlara_isaret_ediyor():
    for stage, mapping in stage_decisions._PHOTO_COLUMNS.items():
        assert stage in DECISION_STAGES
        for row_field, case_column in mapping.items():
            assert row_field in models.CaseStageDecision.__table__.columns, row_field
            assert hasattr(models.Case, case_column), case_column


def test_fotograf_haritasi_yasakli_kolonlara_dokunmuyor():
    """`karar_turu`/`karar_lehine` türetmesi kapsam dışı (görev tanımı);
    `esas_no`/`court`un tek yazma yolu sync_current_esas — fotoğraf bu
    kolonlara İŞARET EDEMEZ (ikinci yazıcı = ikinci doğruluk kaynağı)."""
    hedefler = {c for mapping in stage_decisions._PHOTO_COLUMNS.values() for c in mapping.values()}
    assert not hedefler & {"karar_turu", "karar_lehine", "esas_no", "court", "yeni_esas_no"}


def test_yerel_fotografi_gorev_tanimindaki_ucluyle_sinirli():
    assert stage_decisions._PHOTO_COLUMNS["YEREL"] == {
        "karar_no": "karar_no",
        "karar_tarihi": "karar_tarihi",
        "karar_durumu": "yerel_karar_durumu",
    }


def test_semada_stage_decision_read_var():
    from schemas import CaseStageDecisionRead

    ornek = CaseStageDecisionRead(id=1, case_id=2, stage="TEMYIZ", sira_no=1)
    assert ornek.dogrulama_durumu == "BELIRSIZ"
    assert CaseStageDecisionRead.model_config.get("from_attributes") is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite (kısıt migrasyondan uygulanır, G049)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env():
    """Paylaşılan in-memory sqlite + migrasyon index'leri + G060 seed'leri.

    G049 dersi: `create_all` yalnız MODELDEKİ kısıtları kurar; migrasyonda
    tanımlı `uq_case_stage_decision` fixture'a OLDUĞU GİBİ uygulanır ki
    mükerrer testi burada da gerçek kısıt kırmızısından dönsün. Karar
    listeleri seed sabitlerinden doğrudan yazılır (kapalı havuz doğrulamasının
    okuyacağı tablolar).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops(TABLO):
            conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = maker()
    try:
        for model, degerler in _KARAR_LISTELERI:
            for idx, (code, name) in enumerate(degerler):
                db.add(model(code=code, name=name, active=True, sequence=idx))
        db.commit()
    finally:
        db.close()
    yield maker
    engine.dispose()


def _dava(db, tracking_no="HA.X.0001.2026", **extra):
    case = models.Case(
        tracking_no=tracking_no, status="DERDEST",
        maddi_tazminat=0, manevi_tazminat=0, **extra,
    )
    db.add(case)
    db.flush()
    return case


def test_id_2271_ayni_asamadan_iki_karar_ikisi_de_duruyor(db_env):
    """Kabul kriteri: TEMYIZ sira 1 Bozma + sira 2 Onama — ikisi de duruyor,
    fotoğraf = Onama (tek slot artık son kararın türetilmiş kopyası)."""
    db = db_env()
    try:
        case = _dava(db)
        bozma = add_stage_decision(
            db, case, stage="TEMYIZ", mahkeme="Danıştay 8. Daire",
            esas_no="2023/100", karar_no="2023/500", karar_tarihi=date(2023, 5, 1),
            karar_durumu="Bozma", dogrulama_durumu="BELGE", source="g062-test",
        )
        onama = add_stage_decision(
            db, case, stage="TEMYIZ", mahkeme="Danıştay 8. Daire",
            esas_no="2026/40", karar_no="2026/90", karar_tarihi=date(2026, 2, 10),
            karar_durumu="Onama", dogrulama_durumu="UYAP",
        )
        db.commit()

        rows = get_stage_decisions(db, case.id)
        assert [(r.stage, r.sira_no, r.karar_durumu) for r in rows] == [
            ("TEMYIZ", 1, "Bozma"),
            ("TEMYIZ", 2, "Onama"),
        ]
        # İkinci karar birincinin ÜSTÜNE YAZMADI — id-2271'in çözdüğü kusur
        assert bozma.id != onama.id
        assert rows[0].karar_no == "2023/500" and rows[0].karar_tarihi == date(2023, 5, 1)

        db.refresh(case)
        assert case.temyiz_karar_durumu == "Onama"
        assert case.temyiz_karar_no == "2026/90"
        assert case.temyiz_karar_tarihi == date(2026, 2, 10)
        assert case.temyiz_mahkemesi == "Danıştay 8. Daire"
        assert case.temyiz_esas_no == "2026/40"
    finally:
        db.close()


def test_sira_no_otomatik_ve_asama_basina_bagimsiz(db_env):
    db = db_env()
    try:
        case = _dava(db)
        assert add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul").sira_no == 1
        assert add_stage_decision(db, case, stage="TEMYIZ").sira_no == 1
        assert add_stage_decision(db, case, stage="YEREL", karar_durumu="Red/Esastan").sira_no == 2
        db.commit()
    finally:
        db.close()


def test_siralama_sira_no_ile_tarihle_degil(db_env):
    """Tasarım paketi: 170 föyde tarihler güvenilmez — fotoğraf ve sıra
    `sira_no`dan okunur; daha ESKİ tarihli sira 2 yine 'son karar'dır."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma",
                           karar_tarihi=date(2026, 1, 1))
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama",
                           karar_tarihi=date(2023, 1, 1))   # tarih geride
        db.commit()

        rows = get_stage_decisions(db, case.id)
        assert [r.karar_durumu for r in rows] == ["Bozma", "Onama"]
        db.refresh(case)
        assert case.temyiz_karar_durumu == "Onama"           # sira 2 kazanır
        assert case.temyiz_karar_tarihi == date(2023, 1, 1)
    finally:
        db.close()


def test_ara_siraya_yazim_fotografi_bozmuyor(db_env):
    """Aktarım satırları ters sırayla gelebilir: önce sira 2, sonra sira 1 —
    fotoğraf her yazımda EN YÜKSEK sira_no'dan okunur, son yazılandan değil."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="TEMYIZ", sira_no=2, karar_durumu="Onama")
        add_stage_decision(db, case, stage="TEMYIZ", sira_no=1, karar_durumu="Bozma")
        db.commit()

        db.refresh(case)
        assert case.temyiz_karar_durumu == "Onama"
        assert [r.sira_no for r in get_stage_decisions(db, case.id)] == [1, 2]
    finally:
        db.close()


def test_dogrulama_damgasi_verilmezse_belirsiz_gecersizse_red(db_env):
    db = db_env()
    try:
        case = _dava(db)
        assert add_stage_decision(db, case, stage="YEREL").dogrulama_durumu == "BELIRSIZ"
        assert add_stage_decision(
            db, case, stage="YEREL", dogrulama_durumu="UYAP"
        ).dogrulama_durumu == "UYAP"

        with pytest.raises(ValueError, match="doğrulama durumu"):
            add_stage_decision(db, case, stage="YEREL", dogrulama_durumu="TAHMIN")
        db.commit()
        # Hatalı deneme satır bırakmadı
        assert len(get_stage_decisions(db, case.id)) == 2
    finally:
        db.close()


def test_asama_kapali_kume_onceki_dahil_reddediliyor(db_env):
    db = db_env()
    try:
        case = _dava(db)
        with pytest.raises(ValueError, match="karar aşaması"):
            add_stage_decision(db, case, stage="ISTINAAF")
        with pytest.raises(ValueError, match="karar aşaması"):
            add_stage_decision(db, case, stage="ONCEKI")   # yalnız esas kavramı
        assert get_stage_decisions(db, case.id) == []
    finally:
        db.close()


def test_karar_durumu_kapali_havuz_stage_e_gore(db_env):
    """Kabul kriteri: değer stage'in G060 listesinde yoksa yazım reddedilir —
    komşu aşamanın havuzu da GEÇMEZ (Onama temyiz havuzudur, istinafın değil)."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama")
        add_stage_decision(db, case, stage="ISTINAF", karar_durumu="Kaldırma/Yeniden Hüküm")
        add_stage_decision(db, case, stage="KARAR_DUZELTME", karar_durumu="Karar Düzeltme Ret")

        with pytest.raises(ValueError, match="geçersiz karar durumu"):
            add_stage_decision(db, case, stage="ISTINAF", karar_durumu="Onama")
        with pytest.raises(ValueError, match="geçersiz karar durumu"):
            add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Uydurma Sonuç")

        # None serbest: sonuç henüz bilinmeden satır doğabilir (damga BELIRSIZ)
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu=None)
        db.commit()
        assert len(get_stage_decisions(db, case.id)) == 4
    finally:
        db.close()


def test_mukerrer_sira_gercek_kisit_kirmizisiyla_donuyor(db_env):
    """Kabul kriteri (G049 dersi): mükerrer (case_id, stage, sira_no) yazımı
    UniqueViolation'dan DuplicateStageDecisionError'a çevrilir; oturum
    SAVEPOINT sayesinde kullanılabilir kalır, tarihçe bozulmaz."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="YEREL", sira_no=1, karar_durumu="Kabul")

        with pytest.raises(DuplicateStageDecisionError, match="sira_no=1"):
            add_stage_decision(db, case, stage="YEREL", sira_no=1, karar_durumu="Beraat")

        # Oturum bozulmadı: sıradaki meşru yazım geçer, ilk satır el değmeden duruyor
        add_stage_decision(db, case, stage="YEREL", sira_no=2, karar_durumu="Beraat")
        db.commit()
        rows = get_stage_decisions(db, case.id)
        assert [(r.sira_no, r.karar_durumu) for r in rows] == [(1, "Kabul"), (2, "Beraat")]
        db.refresh(case)
        assert case.yerel_karar_durumu == "Beraat"
    finally:
        db.close()


def test_bozma_sonrasi_yeni_yerel_kaynak_zinciri(db_env):
    """`kaynak_id`: bozma → yeni yerel karar soy bağı; çapraz dava bağı reddedilir."""
    db = db_env()
    try:
        case = _dava(db)
        baska = _dava(db, tracking_no="HA.X.0002.2026")
        bozma = add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma")

        yeni = add_stage_decision(
            db, case, stage="YEREL", karar_durumu="Red/Esastan", kaynak_id=bozma.id,
        )
        db.commit()
        assert yeni.kaynak_id == bozma.id

        with pytest.raises(ValueError, match="kaynak_id"):
            add_stage_decision(db, baska, stage="YEREL", kaynak_id=bozma.id)
        with pytest.raises(ValueError, match="kaynak_id"):
            add_stage_decision(db, case, stage="YEREL", kaynak_id=999999)
    finally:
        db.close()


def test_silmede_fotograf_onceki_siraya_dusuyor_sonra_temizleniyor(db_env):
    """Kabul kriteri: silme (admin düzeltme yolu) fotoğrafı bir önceki
    sira_no'ya döndürür; aşamada satır kalmazsa fotoğraf temizlenir."""
    db = db_env()
    try:
        case = _dava(db)
        ilk = add_stage_decision(
            db, case, stage="TEMYIZ", karar_no="2023/500",
            karar_tarihi=date(2023, 5, 1), karar_durumu="Bozma",
        )
        son = add_stage_decision(
            db, case, stage="TEMYIZ", karar_no="2026/90",
            karar_tarihi=date(2026, 2, 10), karar_durumu="Onama",
        )
        db.commit()
        db.refresh(case)
        assert case.temyiz_karar_durumu == "Onama"

        assert delete_stage_decision(db, case, son.id) is True
        db.commit()
        db.refresh(case)
        assert case.temyiz_karar_durumu == "Bozma"        # önceki sıraya düştü
        assert case.temyiz_karar_no == "2023/500"

        assert delete_stage_decision(db, case, ilk.id) is True
        db.commit()
        db.refresh(case)
        assert case.temyiz_karar_durumu is None           # satır kalmadı → temiz
        assert case.temyiz_karar_no is None
        assert get_stage_decisions(db, case.id) == []
    finally:
        db.close()


def test_silme_yanlis_davadan_veya_yok_satirda_false(db_env):
    db = db_env()
    try:
        case = _dava(db)
        baska = _dava(db, tracking_no="HA.X.0002.2026")
        row = add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.commit()

        assert delete_stage_decision(db, baska, row.id) is False   # başkasının satırı
        assert delete_stage_decision(db, case, 999999) is False    # yok
        assert len(get_stage_decisions(db, case.id)) == 1
    finally:
        db.close()


def test_kaynak_silinince_tureyen_karar_oksuz_ama_yasiyor(db_env):
    """ON DELETE SET NULL'un davranış karşılığı: kaynağın silinmesi türeyen
    kaydı SİLMEZ, yalnız soy bağını düşürür."""
    db = db_env()
    try:
        case = _dava(db)
        bozma = add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma")
        yeni = add_stage_decision(db, case, stage="YEREL", kaynak_id=bozma.id)
        db.commit()

        assert delete_stage_decision(db, case, bozma.id) is True
        db.commit()

        rows = get_stage_decisions(db, case.id)
        assert [(r.stage, r.id) for r in rows] == [("YEREL", yeni.id)]
        assert rows[0].kaynak_id is None                   # öksüz ama yaşıyor
        db.refresh(case)
        assert case.temyiz_karar_durumu is None            # temyiz fotoğrafı temizlendi
    finally:
        db.close()


def test_fotograf_baska_asamaya_ve_korunan_kolonlara_dokunmuyor(db_env):
    """Senkron yalnız yazılan aşamanın slot kolonlarını tazeler; dava kimliği
    (esas_no/court) ve kapsam dışı kaba alanlar (karar_turu/karar_lehine) ile
    tarihçesi yazılmamış aşamaların elle girilmiş değerleri el değmeden durur."""
    db = db_env()
    try:
        case = _dava(
            db, esas_no="2020/1", court="Ankara 5. Asliye Hukuk",
            karar_turu="KABUL", karar_lehine="LEHINE",
            istinaf_karar_durumu="Kaldırma", istinaf_basvuru_tarihi=date(2024, 1, 1),
        )
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama",
                           basvuran_taraf="Davalı", aciklama="onandı")
        db.commit()
        db.refresh(case)

        assert case.esas_no == "2020/1"                    # tek yazma yolu sync_current_esas
        assert case.court == "Ankara 5. Asliye Hukuk"
        assert case.karar_turu == "KABUL" and case.karar_lehine == "LEHINE"
        assert case.istinaf_karar_durumu == "Kaldırma"     # başka aşamaya dokunulmadı
        assert case.istinaf_basvuru_tarihi == date(2024, 1, 1)
        assert case.temyiz_eden_durumu == "Davalı"         # başvuranın temyiz ikizi
        assert case.temyiz_karar_aciklama == "onandı"
    finally:
        db.close()


def test_uzun_metin_kolon_sinirina_kirpiliyor_500_yok(db_env):
    """Taşan mahkeme adı kaydı düşürmez (orantılılık, sync_current_esas
    gerekçesi); kırpılmış kopya fotoğrafa da sığar (hedef kolon aynı sınırda)."""
    db = db_env()
    try:
        case = _dava(db)
        uzun = "Çok Uzun Mahkeme Adı " * 20                # ~420 karakter
        row = add_stage_decision(db, case, stage="ISTINAF", mahkeme=uzun,
                                 source="x" * 300)
        db.commit()

        assert len(row.mahkeme) == 200
        assert len(row.source) == 100
        db.refresh(case)
        assert case.istinaf_mahkemesi == row.mahkeme
    finally:
        db.close()


def test_sira_no_bir_den_baslar(db_env):
    db = db_env()
    try:
        case = _dava(db)
        with pytest.raises(ValueError, match="sira_no"):
            add_stage_decision(db, case, stage="YEREL", sira_no=0)
        assert get_stage_decisions(db, case.id) == []
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. dbtest — gerçek Postgres (3-ortam kuralı: to_regclass + SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg():
    """Gerçek Postgres bağlantısı; DB yoksa YA DA şema göçmemişse modül SKIP.

    test_case_matcher_sql deseni: çıplak CI Postgres'i bağlantı verir ama
    tablo sunmaz — to_regclass kontrolü o ortamı FAIL yerine SKIP yapar.
    Testler yazdıklarını dış transaction'la geri alır; gerçek veritabanına
    kalıcı satır bırakılmaz.
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
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G062 dbtest atlandı")

    try:
        eksik = [
            t for t in ("cases", TABLO)
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar() is None
        ]
    except Exception as exc:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema sorgulanamadı ({type(exc).__name__})")
    if eksik:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema göçmemiş — eksik tablo: {', '.join(eksik)} (çıplak Postgres, migrasyon koşmamış)")

    conn.rollback()          # örtük transaction'ı kapat — testler kendi begin'ini kurar
    try:
        yield conn
    finally:
        conn.close()
        engine.dispose()


def _benzersiz_tracking() -> str:
    return f"HA.G062.{os.getpid()}.{uuid.uuid4().hex[:8]}"


@pytest.mark.dbtest
def test_unique_index_gercek_semada_var(pg):
    """Kabul kriteri: kısıt her kurulum yolunda doğuyor — bu ortamın şemasında
    gerçekten var mı? (Sıfırdan kurulum yolu test_migration_path'in genel
    taramasında; burada yaşayan şema ölçülür.)"""
    tanim = pg.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = 'uq_case_stage_decision'"
    )).scalar()
    pg.rollback()
    assert tanim, "uq_case_stage_decision şemada yok — index op'u koşmamış"
    assert "UNIQUE" in tanim.upper()
    for kolon in ("case_id", "stage", "sira_no"):
        assert kolon in tanim


@pytest.mark.dbtest
def test_mukerrer_yazim_gercek_postgreste_duzgun_donuyor(pg):
    """G049 dersi: geri dönüş yolu GERÇEK kırmızıyla — kısıt Postgres'te
    patlar, manager 23505'i sınıflandırır, oturum kullanılabilir kalır.
    Dış transaction sonunda TAMAMEN geri alınır (gerçek DB'ye iz yok)."""
    tracking = _benzersiz_tracking()
    trans = pg.begin()
    session = Session(bind=pg)
    try:
        case = models.Case(tracking_no=tracking, status="DERDEST")
        session.add(case)
        session.flush()

        add_stage_decision(session, case, stage="TEMYIZ", sira_no=1, source="g062-dbtest")
        with pytest.raises(DuplicateStageDecisionError, match="sira_no=1"):
            add_stage_decision(session, case, stage="TEMYIZ", sira_no=1)

        # Oturum SAVEPOINT sayesinde yaşıyor: otomatik atama 2'yi bulur
        assert add_stage_decision(session, case, stage="TEMYIZ").sira_no == 2
        session.flush()
        assert [r.sira_no for r in get_stage_decisions(session, case.id)] == [1, 2]
    finally:
        session.close()
        trans.rollback()

    # Hijyen: hiçbir satır kalmadı
    kalan = pg.execute(
        text("SELECT count(*) FROM cases WHERE tracking_no = :t"), {"t": tracking}
    ).scalar()
    pg.rollback()
    assert kalan == 0


@pytest.mark.dbtest
def test_kisit_ve_server_default_ham_insertte_de_calisiyor(pg):
    """Son savunma (G049): tek yazma yolunu atlayan ham INSERT'i kısıt durdurur
    ve `dogrulama_durumu` server_default'u ham satıra da BELIRSIZ damgası basar."""
    tracking = _benzersiz_tracking()
    trans = pg.begin()
    try:
        case_id = pg.execute(
            text("INSERT INTO cases (tracking_no, status) VALUES (:t, 'DERDEST') RETURNING id"),
            {"t": tracking},
        ).scalar()
        pg.execute(
            text(f"INSERT INTO {TABLO} (case_id, stage, sira_no) VALUES (:c, 'YEREL', 1)"),
            {"c": case_id},
        )
        damga = pg.execute(
            text(f"SELECT dogrulama_durumu FROM {TABLO} WHERE case_id = :c"), {"c": case_id}
        ).scalar()
        assert damga == "BELIRSIZ"

        with pytest.raises(IntegrityError) as exc:
            pg.execute(
                text(f"INSERT INTO {TABLO} (case_id, stage, sira_no) VALUES (:c, 'YEREL', 1)"),
                {"c": case_id},
            )
        assert unique_violation_constraint(exc.value) == "uq_case_stage_decision"
    finally:
        trans.rollback()
