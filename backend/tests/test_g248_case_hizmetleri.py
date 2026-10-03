"""G248 — `case_hizmetleri`: kart × müvekkil × hizmet satırları + türetilmiş kart özeti.

Kilitlenen davranışlar (sözleşme SABİT — G249-G253 buna yazar):
  1. şema: ("table", ...) op'u + AYRI koşulsuz ("index", ...) op'u (iki FK index'i +
     iki kısmi UNIQUE); `cases.hizmet_turu` veritabanında TEXT'e koşulsuz/idempotent
     genişler (tip yoklamalı DO bloğu — model bildirimi G119 kilidiyle String(100) kalır),
  2. manager (tek yazma yolu): taraf aynı kartın MÜVEKKİLİ olmalı, hizmet adı
     `service_types` listesinden; elle satır tekrar etmez; `cases.hizmet_turu`
     özeti satırlardan türetilir (" ; ", Türkçe alfabetik, boşta NULL),
  3. çoklu seçim (`elle_kumesini_yaz`): küme ekler + siler, föy satırına dokunmaz,
     geçersiz ad hiçbir şey yazdırmaz, aynı küme ikinci kez tarihçe üretmez,
  4. föy kaynaklı satır (`foydan_yaz`): upsert anahtarı `foy_id`, kapsam dışı föyün
     satırı silinir, tanınmayan hizmet mevcut satırı yerinde bırakır,
  5. `update_case`: karttan düşen müvekkilin elle satırları tarihçeli silinir; föyü
     olan taraf çıkarılamaz,
  6. API dört uç: yetki, tenant, 201/200 tekrar, 422, föy satırı silme 409,
  7. `reference_lists`: yeniden adlandırma/taşıma satırlara yayılır, kısmi UNIQUE
     çakışmasında elle satır birleşir, özet yenilenir; `clear` modu reddedilir.

DB'siz katman süreç içi sqlite (StaticPool, `PRAGMA foreign_keys=ON`, migrasyonun
index SQL'leri OLDUĞU GİBİ uygulanır — G049 dersi) üzerinde GERÇEK sorgu koşar;
dbtest katmanı gerçek Postgres scratch DB'si ister (yoksa SKIP).
"""
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import database
import models
from managers import case_hizmetleri as ch
from test_migration_path import _live_indexes, _run_init_db, _scratch_database

TABLO = "case_hizmetleri"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
USER = {"tid": T1, "preferred_username": "avukat@hanyaloglu.com", "name": "Avukat A"}
USER_T2 = {"tid": T2, "preferred_username": "diger@baska.com", "name": "Başka"}

# "Çeviri" bilinçli: Türkçe alfabede "Danışmanlık"tan ÖNCE gelir; düz kod noktası
# sırası onu sona atardı (özet sıralaması sınavı).
HIZMETLER = [
    ("DANISMANLIK", "Danışmanlık"),
    ("LEXIS-RAPOR", "Lexis Rapor"),
    ("VEKALETLI-TAKIP", "Vekaletli Takip"),
    ("CEVIRI", "Çeviri"),
]

INDEX_ADLARI = {
    "idx_case_hizmetleri_case",
    "idx_case_hizmetleri_party",
    "uq_case_hizmetleri_foy",
    "uq_case_hizmetleri_elle",
}


def _ops(tablo=TABLO):
    return [op for op in database._MIGRATIONS if op[1] == tablo]


def _index_sqlleri(tablo=TABLO):
    return [sql for op in database._MIGRATIONS if op[0] == "index" and op[1] == tablo for sql in op[2]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema — DB'siz
# ═══════════════════════════════════════════════════════════════════════════

def test_migrasyon_table_op_ve_ayri_kosulsuz_index_op():
    turler = [op[0] for op in _ops()]
    assert turler == ["table", "index"], turler

    table_op, index_op = _ops()
    assert table_op[3] == [], "index table op'una gömülmemeli (koşullu op tuzağı, G041)"
    ddl = " ".join(table_op[2].split())
    assert "case_party_id INTEGER NOT NULL REFERENCES case_parties(id) ON DELETE RESTRICT" in ddl
    assert "foy_id INTEGER REFERENCES case_foys(id) ON DELETE RESTRICT" in ddl
    assert "case_id INTEGER NOT NULL REFERENCES cases(id)," in ddl, "case_id FK'sı ondelete'siz (föy deseni)"
    assert "hizmet_turu VARCHAR(100) NOT NULL" in ddl

    sqller = index_op[2]
    assert all("IF NOT EXISTS" in s for s in sqller), "idempotent değil → ikinci açılışta patlar"
    adlar = {s.split()[s.split().index("EXISTS") + 1] for s in sqller}
    assert adlar == INDEX_ADLARI
    foy = next(s for s in sqller if "uq_case_hizmetleri_foy" in s)
    elle = next(s for s in sqller if "uq_case_hizmetleri_elle" in s)
    assert foy.startswith("CREATE UNIQUE INDEX") and foy.endswith("(foy_id) WHERE foy_id IS NOT NULL")
    assert elle.startswith("CREATE UNIQUE INDEX")
    assert elle.endswith("(case_id, case_party_id, hizmet_turu) WHERE foy_id IS NULL")


def test_ozet_kolonu_genisletmesi_kosulsuz_opta_ve_tip_yoklamali():
    """`cases.hizmet_turu` TEXT'e koşulsuz ("index", ...) op'unda genişler; ALTER tip
    yoklamalıdır (kolon zaten TEXT ise DDL koşmaz → ikinci açılış kilitsiz no-op).
    Gerçek şema etkisi dbtest'lerde (sıfırdan kurulum + VARCHAR(100)'lü mevcut kurulum)."""
    genisletme = [s for s in _index_sqlleri("cases") if "hizmet_turu TYPE TEXT" in s]
    assert len(genisletme) == 1
    sql = genisletme[0]
    assert sql.startswith("DO $$") and sql.endswith("END $$")
    assert "data_type <> 'text'" in sql and "column_name = 'hizmet_turu'" in sql
    assert "ALTER TABLE cases ALTER COLUMN hizmet_turu TYPE TEXT;" in sql


def test_model_kolonlar_fklar_ve_pk_ikizi_yok():
    tablo = models.CaseHizmeti.__table__
    assert {c.name for c in tablo.columns} == {
        "id", "case_id", "case_party_id", "hizmet_turu", "foy_id", "source", "created_by", "created_at",
    }
    assert tablo.c.id.index is not True, "PK'da index=True PK ikizi üretir (G192 bekçisi)"
    assert tablo.c.case_id.nullable is False and tablo.c.case_party_id.nullable is False
    assert tablo.c.hizmet_turu.nullable is False and tablo.c.hizmet_turu.type.length == 100
    assert tablo.c.foy_id.nullable is True

    def _fk(kolon):
        return next(iter(tablo.c[kolon].foreign_keys))

    assert _fk("case_id").column.table.name == "cases" and _fk("case_id").ondelete is None
    assert _fk("case_party_id").column.table.name == "case_parties"
    assert _fk("case_party_id").ondelete == "RESTRICT"
    assert _fk("foy_id").column.table.name == "case_foys" and _fk("foy_id").ondelete == "RESTRICT"


def test_ozet_metni_distinct_turkce_alfabetik():
    assert ch.ozet_metni([]) is None
    assert ch.ozet_metni(["Lexis Rapor"]) == "Lexis Rapor"
    assert ch.ozet_metni(["Vekaletli Takip", "Çeviri", "Danışmanlık", "Çeviri"]) == (
        "Çeviri ; Danışmanlık ; Vekaletli Takip"
    )
    # ı < i, ş s'den sonra — Türkçe alfabe
    assert ch.ozet_metni(["Şikayet", "Sulh", "İcra", "Islah"]) == "Islah ; İcra ; Sulh ; Şikayet"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def ortam(monkeypatch):
    """Paylaşılan in-memory sqlite + migrasyonun `case_hizmetleri` index'leri + FK zorlaması;
    `case_manager` / `reference_lists` oturumları aynı veritabanına yönlenir."""
    from managers import case_manager, reference_lists

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_conn, _rec):  # sqlite'ta FK eylemleri (RESTRICT) varsayılan KAPALI
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    database.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_sqlleri():
            conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    monkeypatch.setattr(reference_lists, "SessionLocal", maker)
    monkeypatch.setattr(reference_lists, "refresh_cache", lambda *a, **k: None)

    statements: list = []

    @event.listens_for(engine, "before_cursor_execute")
    def _kaydet(conn, cursor, stmt, params, ctx, many):
        statements.append(stmt)

    db = maker()
    for sira, (kod, ad) in enumerate(HIZMETLER):
        db.add(models.ServiceType(code=kod, name=ad, active=True, sequence=sira))
    db.commit()
    db.close()

    yield SimpleNamespace(maker=maker, manager=case_manager, lists=reference_lists, statements=statements)
    engine.dispose()


_SIRA = [0]


def _dava(db, tenant_id=None, deleted=False, **extra):
    import datetime as dt

    _SIRA[0] += 1
    case = models.Case(
        tracking_no=f"G248-{_SIRA[0]:04d}", status="DERDEST", active=True,
        maddi_tazminat=0, manevi_tazminat=0, tenant_id=tenant_id,
        deleted_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc) if deleted else None,
        **extra,
    )
    db.add(case)
    db.flush()
    return case


def _taraf(db, case, name, party_type="CLIENT", role="Davalı"):
    party = models.CaseParty(case_id=case.id, name=name, role=role, party_type=party_type)
    db.add(party)
    db.flush()
    return party


def _foy(db, case, party, sistem_no, hizmet_turu="Lexis Rapor", **extra):
    foy = models.CaseFoy(
        sistem_no=sistem_no, case_id=case.id, case_party_id=party.id if party is not None else None,
        hizmet_turu=hizmet_turu, source="HUKDOK_TESLIM_TEST", **extra,
    )
    db.add(foy)
    db.flush()
    return foy


def _satirlar(db, case_id):
    return sorted(
        (r.case_party_id, r.hizmet_turu, r.foy_id is not None)
        for r in db.query(models.CaseHizmeti).filter(models.CaseHizmeti.case_id == case_id).all()
    )


def _tarihce(db, case_id):
    return [
        (h.old_value, h.new_value, h.changed_by, h.source)
        for h in db.query(models.CaseHistory)
        .filter(models.CaseHistory.case_id == case_id, models.CaseHistory.field_name == "hizmet")
        .order_by(models.CaseHistory.id).all()
    ]


def _ozet(db, case_id):
    db.expire_all()
    return db.get(models.Case, case_id).hizmet_turu


# ─── tekil elle satır ────────────────────────────────────────────────────────

def test_elle_ekle_satir_ozet_ve_tarihce(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")

    row, yeni = ch.elle_ekle(db, case, ali.id, "  Lexis   Rapor ", changed_by="Avukat A", source="panel")
    db.commit()

    assert yeni is True and row.id is not None
    assert (row.hizmet_turu, row.foy_id, row.source, row.created_by) == ("Lexis Rapor", None, "panel", "Avukat A")
    assert _ozet(db, case.id) == "Lexis Rapor"
    assert _tarihce(db, case.id) == [("", "Ali Veli — Lexis Rapor", "Avukat A", "panel")]
    db.close()


def test_ayni_elle_satir_iki_kez_tek_satir(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")

    ilk, yeni1 = ch.elle_ekle(db, case, ali.id, "Lexis Rapor", changed_by="a")
    ikinci, yeni2 = ch.elle_ekle(db, case, ali.id, "Lexis Rapor", changed_by="a")
    db.commit()

    assert (yeni1, yeni2) == (True, False)
    assert ikinci.id == ilk.id
    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", False)]
    assert len(_tarihce(db, case.id)) == 1, "tekrar tarihçe üretmemeli"
    db.close()


def test_kismi_unique_elle_tekrarini_veritabaninda_da_engeller(ortam):
    """Manager'ı atlayan ham INSERT bile aynı (kart, müvekkil, hizmet) elle satırını ikileyemez."""
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    db.add(models.CaseHizmeti(case_id=case.id, case_party_id=ali.id, hizmet_turu="Lexis Rapor"))
    db.flush()
    db.add(models.CaseHizmeti(case_id=case.id, case_party_id=ali.id, hizmet_turu="Lexis Rapor"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.close()


def test_baska_kartin_tarafi_ve_muvekkil_olmayan_taraf_reddedilir(ortam):
    db = ortam.maker()
    case = _dava(db)
    baska = _dava(db)
    yabanci = _taraf(db, baska, "Başka Kartın Müvekkili")
    karsi = _taraf(db, case, "Karşı Taraf", party_type="COUNTER", role="Davacı")

    with pytest.raises(ch.GecersizHizmetTarafi):
        ch.elle_ekle(db, case, yabanci.id, "Lexis Rapor")
    with pytest.raises(ch.GecersizHizmetTarafi):
        ch.elle_ekle(db, case, karsi.id, "Lexis Rapor")
    with pytest.raises(ch.GecersizHizmetTarafi):
        ch.elle_ekle(db, case, 424242, "Lexis Rapor")
    db.commit()

    assert _satirlar(db, case.id) == [] and _satirlar(db, baska.id) == []
    assert _ozet(db, case.id) is None
    db.close()


def test_listede_olmayan_ve_bos_hizmet_reddedilir(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")

    for kotu in ("Uydurma Hizmet", "", "   ", None, "lexis rapor"):   # ad TAM eşleşir (harf duyarlı)
        with pytest.raises(ch.GecersizHizmetTuru):
            ch.elle_ekle(db, case, ali.id, kotu)
    assert issubclass(ch.GecersizHizmetTuru, ch.HizmetHatasi)
    assert _satirlar(db, case.id) == []
    db.close()


def test_ozet_cok_hizmette_birlesik_silinince_null(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")

    r1, _ = ch.elle_ekle(db, case, ali.id, "Vekaletli Takip", changed_by="a")
    r2, _ = ch.elle_ekle(db, case, ali.id, "Çeviri", changed_by="a")
    r3, _ = ch.elle_ekle(db, case, ayse.id, "Vekaletli Takip", changed_by="a")   # aynı ad, başka müvekkil
    r4, _ = ch.elle_ekle(db, case, ayse.id, "Danışmanlık", changed_by="a")
    db.commit()
    assert _ozet(db, case.id) == "Çeviri ; Danışmanlık ; Vekaletli Takip"   # DISTINCT + Türkçe sıra

    assert ch.elle_sil(db, case, r1.id, changed_by="a") is True
    db.commit()
    assert _ozet(db, case.id) == "Çeviri ; Danışmanlık ; Vekaletli Takip", "öteki müvekkilde hâlâ var"

    for r in (r2, r3, r4):
        assert ch.elle_sil(db, case, r.id, changed_by="a") is True
    db.commit()
    assert _satirlar(db, case.id) == []
    assert _ozet(db, case.id) is None
    assert _tarihce(db, case.id)[-1][:2] == ("Ayşe Kaya — Danışmanlık", "")
    db.close()


def test_elle_sil_baska_kartin_satiri_ve_foy_satiri(ortam):
    db = ortam.maker()
    case = _dava(db)
    baska = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    veli = _taraf(db, baska, "Veli Can")
    baska_satir, _ = ch.elle_ekle(db, baska, veli.id, "Danışmanlık")
    foy = _foy(db, case, ali, "SSTMN-1")
    assert ch.foydan_yaz(db, foy).durum == ch.FOY_EKLENDI
    db.commit()
    foy_satiri = db.query(models.CaseHizmeti).filter(models.CaseHizmeti.foy_id == foy.id).one()

    assert ch.elle_sil(db, case, baska_satir.id) is False, "başka kartın satırı bu karttan silinemez"
    assert ch.elle_sil(db, case, 424242) is False
    with pytest.raises(ch.FoyKaynakliSatir):
        ch.elle_sil(db, case, foy_satiri.id)
    db.commit()

    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True)]
    assert _satirlar(db, baska.id) == [(veli.id, "Danışmanlık", False)]
    db.close()


def test_foyun_verdigi_hizmet_elle_tekrar_yazilmaz(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    foy = _foy(db, case, ali, "SSTMN-1", hizmet_turu="Lexis Rapor")
    ch.foydan_yaz(db, foy)
    db.commit()

    row, yeni = ch.elle_ekle(db, case, ali.id, "Lexis Rapor")
    db.commit()

    assert yeni is False and row.foy_id == foy.id, "mevcut föy satırı döner, yeni satır açılmaz"
    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True)]
    db.close()


# ─── çoklu seçim: elle_kumesini_yaz ──────────────────────────────────────────

def test_kume_ekler_ve_siler_tek_tarihce_kaydi(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ch.elle_kumesini_yaz(db, case, ali.id, ["Lexis Rapor", "Danışmanlık"], changed_by="Avukat A", source="panel")
    db.commit()
    assert _satirlar(db, case.id) == [(ali.id, "Danışmanlık", False), (ali.id, "Lexis Rapor", False)]

    degisti = ch.elle_kumesini_yaz(
        db, case, ali.id, ["Danışmanlık", "Çeviri", "Çeviri"], changed_by="Avukat A", source="panel",
    )
    db.commit()

    assert degisti is True
    assert _satirlar(db, case.id) == [(ali.id, "Danışmanlık", False), (ali.id, "Çeviri", False)]
    assert _ozet(db, case.id) == "Çeviri ; Danışmanlık"
    assert _tarihce(db, case.id) == [
        ("", "Ali Veli — Danışmanlık ; Lexis Rapor", "Avukat A", "panel"),
        ("Ali Veli — Danışmanlık ; Lexis Rapor", "Ali Veli — Çeviri ; Danışmanlık", "Avukat A", "panel"),
    ]
    db.close()


def test_kume_ayni_kume_ikinci_kez_degisiklik_ve_tarihce_yok(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    assert ch.elle_kumesini_yaz(db, case, ali.id, ["Lexis Rapor", "Danışmanlık"], changed_by="a") is True
    db.commit()
    idler = sorted(r.id for r in db.query(models.CaseHizmeti).all())

    assert ch.elle_kumesini_yaz(db, case, ali.id, ["Danışmanlık", "Lexis Rapor"], changed_by="a") is False
    db.commit()

    assert sorted(r.id for r in db.query(models.CaseHizmeti).all()) == idler, "satırlar yeniden yazılmamalı"
    assert len(_tarihce(db, case.id)) == 1
    db.close()


def test_kume_foy_satirina_dokunmaz(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    foy = _foy(db, case, ali, "SSTMN-1", hizmet_turu="Lexis Rapor")
    ch.foydan_yaz(db, foy)
    db.commit()

    # föyün adı kümede YOK: föy satırı yerinde kalır, elle satır eklenir
    assert ch.elle_kumesini_yaz(db, case, ali.id, ["Danışmanlık"], changed_by="a") is True
    db.commit()
    assert _satirlar(db, case.id) == [(ali.id, "Danışmanlık", False), (ali.id, "Lexis Rapor", True)]

    # föyün adı kümede VAR: elle ikizi açılmaz (föy zaten veriyor) → değişiklik yok
    assert ch.elle_kumesini_yaz(db, case, ali.id, ["Danışmanlık", "Lexis Rapor"], changed_by="a") is False
    # boş küme: yalnız ELLE satırlar silinir
    assert ch.elle_kumesini_yaz(db, case, ali.id, [], changed_by="a") is True
    db.commit()

    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True)]
    assert _ozet(db, case.id) == "Lexis Rapor"
    assert _tarihce(db, case.id)[-1][:2] == ("Ali Veli — Danışmanlık", "")
    db.close()


def test_kume_listede_olmayan_ad_hicbir_satiri_degistirmez(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ch.elle_kumesini_yaz(db, case, ali.id, ["Lexis Rapor"], changed_by="a")
    db.commit()

    with pytest.raises(ch.GecersizHizmetTuru):
        ch.elle_kumesini_yaz(db, case, ali.id, ["Danışmanlık", "Uydurma Hizmet"], changed_by="a")
    db.commit()

    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", False)], "geçerli ad da yazılmamalı, eski satır silinmemeli"
    assert _ozet(db, case.id) == "Lexis Rapor"
    assert len(_tarihce(db, case.id)) == 1
    db.close()


def test_kume_baska_kartin_tarafi_ve_muvekkil_olmayan_taraf(ortam):
    db = ortam.maker()
    case = _dava(db)
    baska = _dava(db)
    yabanci = _taraf(db, baska, "Başka Kartın Müvekkili")
    karsi = _taraf(db, case, "Karşı Taraf", party_type="COUNTER", role="Davacı")

    with pytest.raises(ch.GecersizHizmetTarafi):
        ch.elle_kumesini_yaz(db, case, yabanci.id, ["Lexis Rapor"])
    with pytest.raises(ch.GecersizHizmetTarafi):
        ch.elle_kumesini_yaz(db, case, karsi.id, ["Lexis Rapor"])
    db.commit()
    assert db.query(models.CaseHizmeti).count() == 0
    db.close()


def test_kume_iki_muvekkile_farkli_kume_ozet_birlesim(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")

    ch.elle_kumesini_yaz(db, case, ali.id, ["Vekaletli Takip", "Lexis Rapor"], changed_by="a")
    ch.elle_kumesini_yaz(db, case, ayse.id, ["Lexis Rapor", "Danışmanlık"], changed_by="a")
    db.commit()

    assert _ozet(db, case.id) == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    liste = ch.kart_hizmet_listesi(db, case.id)
    assert [(s["muvekkil_adi"], s["hizmet_turu"], s["kaynak"]) for s in liste] == [
        ("Ali Veli", "Lexis Rapor", "elle"), ("Ali Veli", "Vekaletli Takip", "elle"),
        ("Ayşe Kaya", "Danışmanlık", "elle"), ("Ayşe Kaya", "Lexis Rapor", "elle"),
    ]
    db.close()


# ─── föy kaynaklı satır: foydan_yaz ──────────────────────────────────────────

def test_foydan_yaz_upsert_anahtari_foy_id(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")
    foy = _foy(db, case, ali, "SSTMN-1", hizmet_turu="Lexis Rapor")

    ilk = ch.foydan_yaz(db, foy)
    db.commit()
    assert (ilk.durum, ilk.satir.foy_id, ilk.satir.source) == (ch.FOY_EKLENDI, foy.id, "HUKDOK_TESLIM_TEST")
    assert _tarihce(db, case.id) == [], "föy satırının ilk yazımı tarihçesiz"
    assert ch.foydan_yaz(db, foy).durum == ch.FOY_DEGISMEDI

    foy.hizmet_turu = "Vekaletli Takip"
    foy.case_party_id = ayse.id
    son = ch.foydan_yaz(db, foy, source="HUKDOK_TESLIM_2")
    db.commit()

    assert son.durum == ch.FOY_GUNCELLENDI and son.satir.id == ilk.satir.id, "satır YERİNDE güncellenir"
    assert _satirlar(db, case.id) == [(ayse.id, "Vekaletli Takip", True)]
    assert _ozet(db, case.id) == "Vekaletli Takip"
    assert _tarihce(db, case.id) == [
        ("Ali Veli — Lexis Rapor", "Ayşe Kaya — Vekaletli Takip", "HUKDOK_TESLIM_2", "HUKDOK_TESLIM_2"),
    ]
    db.close()


def test_foydan_yaz_iki_foy_ayni_muvekkile_ayni_hizmet(ortam):
    """Kısmi UNIQUE föy satırlarını kapsamaz: iki föy aynı müvekkile aynı hizmeti taşıyabilir."""
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    f1 = _foy(db, case, ali, "SSTMN-1")
    f2 = _foy(db, case, ali, "SSTMN-2")

    assert ch.foydan_yaz(db, f1).durum == ch.FOY_EKLENDI
    assert ch.foydan_yaz(db, f2).durum == ch.FOY_EKLENDI
    db.commit()

    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True), (ali.id, "Lexis Rapor", True)]
    assert _ozet(db, case.id) == "Lexis Rapor"
    liste = ch.kart_hizmet_listesi(db, case.id)
    assert sorted(s["sistem_no"] for s in liste) == ["SSTMN-1", "SSTMN-2"]
    db.close()


def test_foydan_yaz_kapsam_disi_siler_isaret_kalkinca_geri_gelir(ortam):
    import datetime as dt

    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    foy = _foy(db, case, ali, "SSTMN-1")
    ch.foydan_yaz(db, foy)
    db.commit()

    foy.kapsam_durumu, foy.kapsam_tarihi = "KAPSAM_DISI", dt.date(2026, 9, 30)
    sonuc = ch.foydan_yaz(db, foy)
    db.commit()
    assert (sonuc.durum, sonuc.sebep) == (ch.FOY_SILINDI, ch.SEBEP_KAPSAM_DISI)
    assert _satirlar(db, case.id) == [] and _ozet(db, case.id) is None
    assert _tarihce(db, case.id)[-1][:2] == ("Ali Veli — Lexis Rapor", "")
    assert (ch.foydan_yaz(db, foy).durum, ch.foydan_yaz(db, foy).sebep) == (ch.FOY_ATLANDI, ch.SEBEP_KAPSAM_DISI)

    foy.kapsam_durumu = None
    assert ch.foydan_yaz(db, foy).durum == ch.FOY_EKLENDI
    db.commit()
    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True)]
    assert _ozet(db, case.id) == "Lexis Rapor"
    db.close()


def test_foydan_yaz_yazilamayan_foy_atlanir_mevcut_satir_kalir(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    karsi = _taraf(db, case, "Karşı Taraf", party_type="COUNTER", role="Davacı")

    tarafsiz = _foy(db, case, None, "SSTMN-1")
    karsi_foy = _foy(db, case, karsi, "SSTMN-2")
    hizmetsiz = _foy(db, case, ali, "SSTMN-3", hizmet_turu=None)
    taninmayan = _foy(db, case, ali, "SSTMN-4", hizmet_turu="Eski Ad")
    for foy, sebep in ((tarafsiz, ch.SEBEP_TARAF_YOK), (karsi_foy, ch.SEBEP_MUVEKKIL_DEGIL),
                       (hizmetsiz, ch.SEBEP_HIZMET_BOS), (taninmayan, ch.SEBEP_LISTEDE_YOK)):
        sonuc = ch.foydan_yaz(db, foy)
        assert (sonuc.durum, sonuc.sebep) == (ch.FOY_ATLANDI, sebep)
    assert _satirlar(db, case.id) == []

    # Yeniden adlandırılmış hizmet: paket eski adı taşıyor → satır yeni adıyla YERİNDE kalır
    foy = _foy(db, case, ali, "SSTMN-5", hizmet_turu="Lexis Rapor")
    ch.foydan_yaz(db, foy)
    foy.hizmet_turu = "Listeden Kalkmış Ad"
    sonuc = ch.foydan_yaz(db, foy)
    db.commit()

    assert (sonuc.durum, sonuc.sebep) == (ch.FOY_ATLANDI, ch.SEBEP_LISTEDE_YOK)
    assert sonuc.satir is not None and sonuc.satir.hizmet_turu == "Lexis Rapor"
    assert _satirlar(db, case.id) == [(ali.id, "Lexis Rapor", True)]
    db.close()


def test_foydan_yaz_foy_baska_karta_tasininca_satir_izler(ortam):
    db = ortam.maker()
    eski = _dava(db)
    yeni = _dava(db)
    ali = _taraf(db, eski, "Ali Veli")
    ali2 = _taraf(db, yeni, "Ali Veli")
    foy = _foy(db, eski, ali, "SSTMN-1")
    ch.foydan_yaz(db, foy)
    db.commit()

    foy.case_id, foy.case_party_id = yeni.id, ali2.id
    assert ch.foydan_yaz(db, foy).durum == ch.FOY_GUNCELLENDI
    db.commit()
    assert _satirlar(db, eski.id) == [] and _ozet(db, eski.id) is None
    assert _satirlar(db, yeni.id) == [(ali2.id, "Lexis Rapor", True)] and _ozet(db, yeni.id) == "Lexis Rapor"

    # föy tarafsız hâlde üçüncü karta taşındı: eski kartta satır bırakılmaz
    ucuncu = _dava(db)
    foy.case_id, foy.case_party_id = ucuncu.id, None
    sonuc = ch.foydan_yaz(db, foy)
    db.commit()
    assert (sonuc.durum, sonuc.sebep) == (ch.FOY_SILINDI, ch.SEBEP_TARAF_YOK)
    assert db.query(models.CaseHizmeti).count() == 0 and _ozet(db, yeni.id) is None
    db.close()


# ─── toplu yolun sorgusuz ön kararı (aktarım / doldurma) ─────────────────────

def test_yazmasiz_sonuc_foydan_yaz_ile_ayni_karari_verir_ve_sorgu_kosmaz(ortam):
    """Toplu çağıran yazma gerektirmeyen föyü `foydan_yaz`a hiç sokmaz. Ön karar tekil
    yolla BİREBİR olmalı: değişmedi/atlandı → aynı (durum, sebep, satır); eklenecek /
    güncellenecek / silinecek föy → None (iş `foydan_yaz`a kalır)."""
    db = ortam.maker()
    case, baska = _dava(db), _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    karsi = _taraf(db, case, "Karşı Taraf", party_type="COUNTER", role="Davacı")
    ali_baska = _taraf(db, baska, "Ali Veli")

    # Satırı OLAN föyler: önce yazılır, sonra föy değişir (paketin yeni hâli).
    satirli = [_foy(db, case, ali, f"S-{i}") for i in range(1, 7)]
    for foy in satirli:
        assert ch.foydan_yaz(db, foy).durum == ch.FOY_EKLENDI
    db.commit()
    ayni, hizmeti_degisen, kapsamdan_cikan, adi_kalkan, tarafsiz_tasinan, tasinan = satirli
    hizmeti_degisen.hizmet_turu = "Danışmanlık"
    kapsamdan_cikan.kapsam_durumu = "KAPSAM_DISI"
    adi_kalkan.hizmet_turu = "Listeden Kalkmış Ad"
    tarafsiz_tasinan.case_id, tarafsiz_tasinan.case_party_id = baska.id, None
    tasinan.case_id, tasinan.case_party_id = baska.id, ali_baska.id

    # Satırı OLMAYAN föyler.
    satirsiz = [
        _foy(db, case, ali, "S-7"),
        _foy(db, case, ali, "S-8", hizmet_turu="  Lexis   Rapor "),
        _foy(db, case, ali, "S-9", kapsam_durumu="KAPSAM_DISI"),
        _foy(db, case, None, "S-10"),
        _foy(db, case, karsi, "S-11"),
        _foy(db, case, ali, "S-12", hizmet_turu=None),
        _foy(db, case, ali, "S-13", hizmet_turu="Eski Ad"),
    ]
    foyler = satirli + satirsiz
    beklenen = {
        "S-1": (ch.FOY_DEGISMEDI, None),
        "S-2": (ch.FOY_GUNCELLENDI, None),
        "S-3": (ch.FOY_SILINDI, ch.SEBEP_KAPSAM_DISI),
        "S-4": (ch.FOY_ATLANDI, ch.SEBEP_LISTEDE_YOK),      # mevcut satır yerinde kalır
        "S-5": (ch.FOY_SILINDI, ch.SEBEP_TARAF_YOK),        # föy başka karta gitti
        "S-6": (ch.FOY_GUNCELLENDI, None),
        "S-7": (ch.FOY_EKLENDI, None),
        "S-8": (ch.FOY_EKLENDI, None),
        "S-9": (ch.FOY_ATLANDI, ch.SEBEP_KAPSAM_DISI),
        "S-10": (ch.FOY_ATLANDI, ch.SEBEP_TARAF_YOK),
        "S-11": (ch.FOY_ATLANDI, ch.SEBEP_MUVEKKIL_DEGIL),
        "S-12": (ch.FOY_ATLANDI, ch.SEBEP_HIZMET_BOS),
        "S-13": (ch.FOY_ATLANDI, ch.SEBEP_LISTEDE_YOK),
    }
    yazmasiz = (ch.FOY_DEGISMEDI, ch.FOY_ATLANDI)

    hazir = ch.foy_hazirligi(db, foyler)
    ortam.statements.clear()
    on_kararlar = {foy.sistem_no: ch.yazmasiz_sonuc(foy, hazir) for foy in foyler}
    assert ortam.statements == [], "ön karar sorgu koşmamalı"

    for foy in foyler:
        on = on_kararlar[foy.sistem_no]
        gercek = ch.foydan_yaz(db, foy)
        assert (gercek.durum, gercek.sebep) == beklenen[foy.sistem_no], foy.sistem_no
        if gercek.durum in yazmasiz:
            assert on is not None, foy.sistem_no
            assert (on.durum, on.sebep) == (gercek.durum, gercek.sebep), foy.sistem_no
            assert on.satir is gercek.satir, foy.sistem_no
        else:
            assert on is None, foy.sistem_no
    db.close()


def test_hazirlik_ad_cozumu_tekil_dogrulamayla_ayni(ortam):
    """`FoyHazirligi.ad_coz` = `dogrulanmis_hizmet_adi`nın sorgusuz eşi — liste doluyken
    de BOŞKEN de (boş listede doğrulama atlanır, kolon sınırı yine geçerli)."""
    db = ortam.maker()
    adaylar = ["Lexis Rapor", "  Lexis   Rapor ", "lexis rapor", "Eski Ad", "", "   ", None, "x" * 101]

    def tekil(ham):
        try:
            return ch.dogrulanmis_hizmet_adi(db, ham)
        except ch.GecersizHizmetTuru:
            return None

    dolu = ch.foy_hazirligi(db, [])
    assert dolu.adlar == {ad for _, ad in HIZMETLER}
    assert [dolu.ad_coz(a) for a in adaylar] == [tekil(a) for a in adaylar]
    assert dolu.ad_coz("  Lexis   Rapor ") == "Lexis Rapor" and dolu.ad_coz("lexis rapor") is None

    db.query(models.ServiceType).delete()
    db.commit()
    bos = ch.foy_hazirligi(db, [])
    assert bos.adlar is None
    assert [bos.ad_coz(a) for a in adaylar] == [tekil(a) for a in adaylar]
    assert bos.ad_coz("Eski Ad") == "Eski Ad" and bos.ad_coz("x" * 101) is None
    db.close()


# ─── kart birleştirme taşıması + toplu özet ──────────────────────────────────

def test_tarafi_tasi_elle_cakismasi_birlesir_foy_satiri_tasinir(ortam):
    db = ortam.maker()
    kalan = _dava(db)
    sonen = _dava(db)
    hedef = _taraf(db, kalan, "Ali Veli")
    kaynak = _taraf(db, sonen, "Ali Veli")
    ch.elle_kumesini_yaz(db, kalan, hedef.id, ["Lexis Rapor"], changed_by="a")
    ch.elle_kumesini_yaz(db, sonen, kaynak.id, ["Lexis Rapor", "Danışmanlık"], changed_by="a")
    foy = _foy(db, sonen, kaynak, "SSTMN-1", hizmet_turu="Vekaletli Takip")
    ch.foydan_yaz(db, foy)
    db.commit()

    sonuc = ch.tarafi_tasi(db, eski_party_id=kaynak.id, yeni_party_id=hedef.id, yeni_case_id=kalan.id)
    db.commit()

    assert sonuc == {"tasinan": 2, "birlesen": 1}
    assert _satirlar(db, sonen.id) == [] and _ozet(db, sonen.id) is None
    assert _satirlar(db, kalan.id) == [
        (hedef.id, "Danışmanlık", False), (hedef.id, "Lexis Rapor", False), (hedef.id, "Vekaletli Takip", True),
    ]
    assert _ozet(db, kalan.id) == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    db.close()


def test_ozetleri_yenile_yalniz_degiseni_yazar(ortam):
    db = ortam.maker()
    a, b = _dava(db), _dava(db, hizmet_turu="Eski Değer")
    ali = _taraf(db, a, "Ali Veli")
    db.add(models.CaseHizmeti(case_id=a.id, case_party_id=ali.id, hizmet_turu="Lexis Rapor"))
    db.commit()

    assert ch.ozetleri_yenile(db, [a.id, b.id, a.id, None]) == 2
    db.commit()
    assert _ozet(db, a.id) == "Lexis Rapor" and _ozet(db, b.id) is None
    assert ch.ozetleri_yenile(db, [a.id, b.id]) == 0
    db.close()


# ─── update_case: taraf silme ────────────────────────────────────────────────

def _taraf_dict(name, party_type="CLIENT", role="Davalı"):
    return {"name": name, "role": role, "party_type": party_type}


def test_update_case_cikarilan_muvekkilin_elle_satirlari_tarihceli_silinir(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")
    ch.elle_kumesini_yaz(db, case, ali.id, ["Lexis Rapor", "Danışmanlık"], changed_by="a")
    ch.elle_kumesini_yaz(db, case, ayse.id, ["Vekaletli Takip"], changed_by="a")
    db.commit()
    case_id, ali_id, ayse_id = case.id, ali.id, ayse.id
    db.close()

    sonuc = ortam.manager.update_case(case_id, {"parties": [_taraf_dict("Ayşe Kaya")]}, changed_by="Avukat A")

    assert sonuc is True
    db = ortam.maker()
    assert db.get(models.CaseParty, ali_id) is None
    assert _satirlar(db, case_id) == [(ayse_id, "Vekaletli Takip", False)]
    assert _ozet(db, case_id) == "Vekaletli Takip"
    assert _tarihce(db, case_id)[-1] == ("Ali Veli — Danışmanlık ; Lexis Rapor", "", "Avukat A", "panel")
    db.close()


def test_update_case_hizmetsiz_kartta_eski_ozete_dokunmaz(ortam):
    """Hizmet satırı hiç yazılmamış kart (geriye dönük doldurma öncesi): taraf silinse de
    aktarımın yazdığı eski `cases.hizmet_turu` değeri durur."""
    db = ortam.maker()
    case = _dava(db, hizmet_turu="Lexis Rapor")
    _taraf(db, case, "Ali Veli")
    _taraf(db, case, "Ayşe Kaya")
    db.commit()
    case_id = case.id
    db.close()

    assert ortam.manager.update_case(case_id, {"parties": [_taraf_dict("Ayşe Kaya")]}) is True

    db = ortam.maker()
    assert _ozet(db, case_id) == "Lexis Rapor"
    assert _tarihce(db, case_id) == []
    db.close()


def test_update_case_foyu_olan_taraf_cikarilamaz(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")
    foy = _foy(db, case, ali, "SSTMN-1")
    ch.foydan_yaz(db, foy)
    ch.elle_kumesini_yaz(db, case, ali.id, ["Danışmanlık"], changed_by="a")
    db.commit()
    case_id, ali_id, ayse_id = case.id, ali.id, ayse.id
    db.close()

    sonuc = ortam.manager.update_case(case_id, {"parties": [_taraf_dict("Ayşe Kaya")]}, changed_by="Avukat A")

    assert sonuc is False, "RESTRICT: föy kaynaklı kaydı olan müvekkil karttan düşürülemez"
    db = ortam.maker()
    assert db.get(models.CaseParty, ali_id) is not None and db.get(models.CaseParty, ayse_id) is not None
    assert _satirlar(db, case_id) == [(ali_id, "Danışmanlık", False), (ali_id, "Lexis Rapor", True)], (
        "işlem bütünüyle geri alınmalı — elle satır da yerinde"
    )
    assert _ozet(db, case_id) == "Danışmanlık ; Lexis Rapor"
    db.close()


# ─── get_case: hizmetler listesi ─────────────────────────────────────────────

def test_get_case_hizmetler_listesi_ve_sorgu_sayisi(ortam):
    db = ortam.maker()
    case = _dava(db)
    ali = _taraf(db, case, "Ali Veli")
    ayse = _taraf(db, case, "Ayşe Kaya")
    foy = _foy(db, case, ali, "SSTMN-9425", hizmet_turu="Lexis Rapor")
    ch.foydan_yaz(db, foy)
    ch.elle_kumesini_yaz(db, case, ayse.id, ["Vekaletli Takip", "Danışmanlık"], changed_by="a")
    bos = _dava(db)
    db.commit()
    case_id, bos_id, ali_id, ayse_id, foy_id = case.id, bos.id, ali.id, ayse.id, foy.id
    db.close()

    ortam.statements.clear()
    kart = ortam.manager.get_case(case_id)
    dolu_sorgu = len(ortam.statements)
    ortam.statements.clear()
    bos_kart = ortam.manager.get_case(bos_id)
    bos_sorgu = len(ortam.statements)

    assert kart["hizmet_turu"] == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    assert [{k: v for k, v in h.items() if k != "id"} for h in kart["hizmetler"]] == [
        {"case_party_id": ali_id, "muvekkil_adi": "Ali Veli", "hizmet_turu": "Lexis Rapor",
         "kaynak": "foy", "foy_id": foy_id, "sistem_no": "SSTMN-9425"},
        {"case_party_id": ayse_id, "muvekkil_adi": "Ayşe Kaya", "hizmet_turu": "Danışmanlık",
         "kaynak": "elle", "foy_id": None, "sistem_no": None},
        {"case_party_id": ayse_id, "muvekkil_adi": "Ayşe Kaya", "hizmet_turu": "Vekaletli Takip",
         "kaynak": "elle", "foy_id": None, "sistem_no": None},
    ]
    assert all(isinstance(h["id"], int) for h in kart["hizmetler"])
    assert bos_kart["hizmetler"] == [] and bos_kart["hizmet_turu"] is None
    assert dolu_sorgu == bos_sorgu, "hizmet satırları kart ifadesinde gelmeli (joinedload) — ek sorgu yok"

    from schemas import CaseRead
    assert "hizmetler" in CaseRead.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# 3. API
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def api(ortam):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import get_db
    from dependencies import get_current_user
    from routes import case_hizmetleri as route_mod

    def _client(user=USER):
        app = FastAPI()
        app.include_router(route_mod.router)
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user

        def _db_override():
            db = ortam.maker()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db_override
        return TestClient(app, raise_server_exceptions=False)

    def _kur(tenant_id=None, deleted=False):
        """Kart + iki müvekkil + karşı taraf + Ali'ye föy kaynaklı satır."""
        db = ortam.maker()
        case = _dava(db, tenant_id=tenant_id, deleted=deleted)
        ali = _taraf(db, case, "Ali Veli")
        ayse = _taraf(db, case, "Ayşe Kaya")
        karsi = _taraf(db, case, "Karşı Taraf", party_type="COUNTER", role="Davacı")
        foy = _foy(db, case, ali, f"SSTMN-{case.id}", hizmet_turu="Lexis Rapor")
        foy_satiri = ch.foydan_yaz(db, foy).satir
        db.commit()
        sonuc = SimpleNamespace(case=case.id, ali=ali.id, ayse=ayse.id, karsi=karsi.id,
                                foy_satiri=foy_satiri.id, sistem_no=foy.sistem_no)
        db.close()
        return sonuc

    return SimpleNamespace(client=_client, kur=_kur, maker=ortam.maker)


def test_api_get_liste_sekli(api):
    k = api.kur()
    r = api.client().get(f"/api/cases/{k.case}/hizmetler")

    assert r.status_code == 200
    assert r.json() == [{
        "id": k.foy_satiri, "case_party_id": k.ali, "muvekkil_adi": "Ali Veli", "hizmet_turu": "Lexis Rapor",
        "kaynak": "foy", "foy_id": r.json()[0]["foy_id"], "sistem_no": k.sistem_no,
    }]


def test_api_post_201_tekrar_200_ayni_satir(api):
    k = api.kur()
    c = api.client()
    govde = {"case_party_id": k.ayse, "hizmet_turu": "Danışmanlık"}

    ilk = c.post(f"/api/cases/{k.case}/hizmetler", json=govde)
    tekrar = c.post(f"/api/cases/{k.case}/hizmetler", json=govde)

    assert ilk.status_code == 201 and tekrar.status_code == 200
    assert tekrar.json() == ilk.json()
    assert {x: ilk.json()[x] for x in ("case_party_id", "muvekkil_adi", "hizmet_turu", "kaynak", "sistem_no")} == {
        "case_party_id": k.ayse, "muvekkil_adi": "Ayşe Kaya", "hizmet_turu": "Danışmanlık",
        "kaynak": "elle", "sistem_no": None,
    }
    db = api.maker()
    assert _satirlar(db, k.case) == [(k.ali, "Lexis Rapor", True), (k.ayse, "Danışmanlık", False)]
    assert _ozet(db, k.case) == "Danışmanlık ; Lexis Rapor"
    assert _tarihce(db, k.case) == [("", "Ayşe Kaya — Danışmanlık", "Avukat A", "panel")]
    db.close()

    # föyün zaten verdiği hizmet: yeni satır açılmaz, föy satırı 200 ile döner
    foyden = c.post(f"/api/cases/{k.case}/hizmetler", json={"case_party_id": k.ali, "hizmet_turu": "Lexis Rapor"})
    assert foyden.status_code == 200 and foyden.json()["id"] == k.foy_satiri


def test_api_post_422_gecersiz_hizmet_ve_taraf(api):
    k = api.kur()
    baska = api.kur()
    c = api.client()

    for govde in (
        {"case_party_id": k.ayse, "hizmet_turu": "Uydurma Hizmet"},
        {"case_party_id": k.ayse, "hizmet_turu": "   "},
        {"case_party_id": k.karsi, "hizmet_turu": "Danışmanlık"},        # müvekkil değil
        {"case_party_id": baska.ayse, "hizmet_turu": "Danışmanlık"},     # başka kartın tarafı
        {"hizmet_turu": "Danışmanlık"},                                  # şema: taraf zorunlu
    ):
        r = c.post(f"/api/cases/{k.case}/hizmetler", json=govde)
        assert r.status_code == 422, (govde, r.status_code, r.text)

    db = api.maker()
    assert _satirlar(db, k.case) == [(k.ali, "Lexis Rapor", True)]
    assert _tarihce(db, k.case) == []
    db.close()


def test_api_delete_204_404_ve_foy_satiri_409(api):
    k = api.kur()
    baska = api.kur()
    c = api.client()
    elle = c.post(f"/api/cases/{k.case}/hizmetler", json={"case_party_id": k.ayse, "hizmet_turu": "Danışmanlık"}).json()

    foy = c.delete(f"/api/cases/{k.case}/hizmetler/{k.foy_satiri}")
    assert foy.status_code == 409 and "föy" in foy.json()["detail"]
    assert c.delete(f"/api/cases/{baska.case}/hizmetler/{elle['id']}").status_code == 404, "başka kartın satırı"
    assert c.delete(f"/api/cases/{k.case}/hizmetler/424242").status_code == 404

    assert c.delete(f"/api/cases/{k.case}/hizmetler/{elle['id']}").status_code == 204
    assert c.delete(f"/api/cases/{k.case}/hizmetler/{elle['id']}").status_code == 404, "zaten silinmiş"

    db = api.maker()
    assert _satirlar(db, k.case) == [(k.ali, "Lexis Rapor", True)]
    assert _ozet(db, k.case) == "Lexis Rapor"
    assert _tarihce(db, k.case)[-1] == ("Ayşe Kaya — Danışmanlık", "", "Avukat A", "panel")
    db.close()


def test_api_put_kume_ekler_siler_ve_liste_doner(api):
    k = api.kur()
    c = api.client()
    yol = f"/api/cases/{k.case}/hizmetler/{k.ayse}"

    ilk = c.put(yol, json={"hizmet_turleri": ["Danışmanlık", "Vekaletli Takip"]})
    assert ilk.status_code == 200
    assert [(s["muvekkil_adi"], s["hizmet_turu"], s["kaynak"]) for s in ilk.json()] == [
        ("Ali Veli", "Lexis Rapor", "foy"),
        ("Ayşe Kaya", "Danışmanlık", "elle"), ("Ayşe Kaya", "Vekaletli Takip", "elle"),
    ]

    ikinci = c.put(yol, json={"hizmet_turleri": ["Vekaletli Takip", "Çeviri"]})
    assert [(s["muvekkil_adi"], s["hizmet_turu"]) for s in ikinci.json()] == [
        ("Ali Veli", "Lexis Rapor"), ("Ayşe Kaya", "Çeviri"), ("Ayşe Kaya", "Vekaletli Takip"),
    ]
    ayni = c.put(yol, json={"hizmet_turleri": ["Çeviri", "Vekaletli Takip"]})
    assert ayni.status_code == 200 and ayni.json() == ikinci.json()

    db = api.maker()
    assert _ozet(db, k.case) == "Çeviri ; Lexis Rapor ; Vekaletli Takip"
    assert len(_tarihce(db, k.case)) == 2, "aynı küme ikinci kez tarihçe üretmemeli"
    db.close()

    # föy kaynaklı müvekkilde boş küme: föy satırı kalır
    bos = c.put(f"/api/cases/{k.case}/hizmetler/{k.ali}", json={"hizmet_turleri": []})
    assert bos.status_code == 200 and ("Ali Veli", "Lexis Rapor", "foy") in [
        (s["muvekkil_adi"], s["hizmet_turu"], s["kaynak"]) for s in bos.json()
    ]


def test_api_put_422_hicbir_satir_degismez(api):
    k = api.kur()
    baska = api.kur()
    c = api.client()
    c.put(f"/api/cases/{k.case}/hizmetler/{k.ayse}", json={"hizmet_turleri": ["Danışmanlık"]})

    for yol, govde in (
        (f"/api/cases/{k.case}/hizmetler/{k.ayse}", {"hizmet_turleri": ["Çeviri", "Uydurma Hizmet"]}),
        (f"/api/cases/{k.case}/hizmetler/{k.karsi}", {"hizmet_turleri": ["Çeviri"]}),
        (f"/api/cases/{k.case}/hizmetler/{baska.ayse}", {"hizmet_turleri": ["Çeviri"]}),
        (f"/api/cases/{k.case}/hizmetler/{k.ayse}", {}),                 # şema: liste zorunlu
    ):
        r = c.put(yol, json=govde)
        assert r.status_code == 422, (yol, govde, r.status_code, r.text)

    db = api.maker()
    assert _satirlar(db, k.case) == [(k.ali, "Lexis Rapor", True), (k.ayse, "Danışmanlık", False)]
    assert len(_tarihce(db, k.case)) == 1
    db.close()


def test_api_girdi_tavani_asiminda_422_sorgu_kosmadan(api):
    """Sınırsız liste = ad başına doğrulama sorgusu (tek istekte yüz binlerce). Tavan aşımı
    şemada 422'dir: manager'a ulaşmaz, GEÇERLİ adın tekrarı da tavanı delemez."""
    from schemas import HIZMET_ADI_MAX_LEN, HIZMET_KUMESI_AZAMI

    k = api.kur()
    c = api.client()
    kume_yolu = f"/api/cases/{k.case}/hizmetler/{k.ayse}"
    uzun_ad = "x" * (HIZMET_ADI_MAX_LEN + 1)

    # Tavanın kendisi geçer (tekrarlar tek ada iner) — sınır bir fazlasında başlar.
    tam = c.put(kume_yolu, json={"hizmet_turleri": ["Danışmanlık"] * HIZMET_KUMESI_AZAMI})
    assert tam.status_code == 200, tam.text

    for yontem, yol, govde in (
        ("put", kume_yolu, {"hizmet_turleri": ["Danışmanlık"] * (HIZMET_KUMESI_AZAMI + 1)}),
        ("put", kume_yolu, {"hizmet_turleri": [uzun_ad]}),
        ("post", f"/api/cases/{k.case}/hizmetler", {"case_party_id": k.ayse, "hizmet_turu": uzun_ad}),
    ):
        r = getattr(c, yontem)(yol, json=govde)
        assert r.status_code == 422, (yontem, govde.keys(), r.status_code, r.text[:200])

    db = api.maker()
    assert _satirlar(db, k.case) == [(k.ali, "Lexis Rapor", True), (k.ayse, "Danışmanlık", False)]
    db.close()


def test_api_gorunmeyen_dava_dort_ucta_404(api):
    """Başka tenant'ın kartı ve soft-silinmiş kart → 404; NULL tenant (paylaşımlı havuz) ve
    kendi tenant'ı görünür."""
    kendi = api.kur(tenant_id=T1)
    silik = api.kur(deleted=True)
    c2 = api.client(user=USER_T2)

    for istemci, k in ((c2, kendi), (api.client(), silik)):
        assert istemci.get(f"/api/cases/{k.case}/hizmetler").status_code == 404
        assert istemci.post(
            f"/api/cases/{k.case}/hizmetler", json={"case_party_id": k.ayse, "hizmet_turu": "Danışmanlık"},
        ).status_code == 404
        assert istemci.put(
            f"/api/cases/{k.case}/hizmetler/{k.ayse}", json={"hizmet_turleri": ["Danışmanlık"]},
        ).status_code == 404
        assert istemci.delete(f"/api/cases/{k.case}/hizmetler/{k.foy_satiri}").status_code == 404
    assert api.client().get("/api/cases/424242/hizmetler").status_code == 404

    paylasimli = api.kur(tenant_id=None)
    assert c2.get(f"/api/cases/{paylasimli.case}/hizmetler").status_code == 200
    assert api.client().get(f"/api/cases/{kendi.case}/hizmetler").status_code == 200

    db = api.maker()
    assert _satirlar(db, kendi.case) == [(kendi.ali, "Lexis Rapor", True)], "404 dönen uç hiçbir şey yazmamalı"
    db.close()


def test_api_oturumsuz_401(api):
    k = api.kur()
    c = api.client(user=None)

    assert c.get(f"/api/cases/{k.case}/hizmetler").status_code == 401
    assert c.post(f"/api/cases/{k.case}/hizmetler",
                  json={"case_party_id": k.ayse, "hizmet_turu": "Danışmanlık"}).status_code == 401
    assert c.put(f"/api/cases/{k.case}/hizmetler/{k.ayse}", json={"hizmet_turleri": []}).status_code == 401
    assert c.delete(f"/api/cases/{k.case}/hizmetler/{k.foy_satiri}").status_code == 401


def _duz_yollar(routes):
    """FastAPI `include_router`ı sarmalar (`_IncludedRouter`) — düzleştir (G081 deseni)."""
    for r in routes:
        ic = getattr(r, "original_router", None)
        if ic is not None:
            yield from _duz_yollar(ic.routes)
            continue
        for method in getattr(r, "methods", []) or []:
            yield (r.path, method)


def test_router_uygulamaya_kayitli():
    from api import app

    yollar = set(_duz_yollar(app.routes))
    assert ("/api/cases/{case_id}/hizmetler", "GET") in yollar
    assert ("/api/cases/{case_id}/hizmetler", "POST") in yollar
    assert ("/api/cases/{case_id}/hizmetler/{case_party_id}", "PUT") in yollar
    assert ("/api/cases/{case_id}/hizmetler/{hizmet_id}", "DELETE") in yollar


# ═══════════════════════════════════════════════════════════════════════════
# 4. reference_lists — yeniden adlandırma / taşıma / silme
# ═══════════════════════════════════════════════════════════════════════════

def test_satir_bagi_kayitli_ve_bosaltilamaz():
    from managers.reference_lists import DEPENDENCIES, SATIR_BAGIMLILIKLARI, bagimliliklar

    satir = SATIR_BAGIMLILIKLARI["service_types"]
    assert [(d.model, d.column, d.label, d.clearable) for d in satir] == [
        (models.CaseHizmeti, "hizmet_turu", "dava hizmeti", False),
    ]
    assert bagimliliklar("service_types") == [*DEPENDENCIES["service_types"], *satir]
    assert bagimliliklar("cities") == DEPENDENCIES["cities"]


def _liste_kurgusu(ortam):
    """Kart 1: Ali'de elle Lexis Rapor + elle Danışmanlık, Ayşe'de föyden Lexis Rapor.
    Kart 2: yalnız Vekaletli Takip (etkilenmemeli)."""
    db = ortam.maker()
    k1, k2 = _dava(db), _dava(db)
    ali, ayse = _taraf(db, k1, "Ali Veli"), _taraf(db, k1, "Ayşe Kaya")
    veli = _taraf(db, k2, "Veli Can")
    ch.elle_kumesini_yaz(db, k1, ali.id, ["Lexis Rapor", "Danışmanlık"], changed_by="a")
    ch.foydan_yaz(db, _foy(db, k1, ayse, "SSTMN-1", hizmet_turu="Lexis Rapor"))
    ch.elle_kumesini_yaz(db, k2, veli.id, ["Vekaletli Takip"], changed_by="a")
    db.commit()
    sonuc = SimpleNamespace(k1=k1.id, k2=k2.id, ali=ali.id, ayse=ayse.id, veli=veli.id)
    db.close()
    return sonuc


def test_yeniden_adlandirma_satirlara_ve_ozete_yayilir(ortam):
    k = _liste_kurgusu(ortam)

    sonuc = ortam.lists.update_item("service_types", "LEXIS-RAPOR", {"name": "Lexis Raporu"})

    assert sonuc == {"updated": 2}, "elle + föy satırı (çok değerli özet kolon bağına takılmaz)"
    db = ortam.maker()
    assert _satirlar(db, k.k1) == [
        (k.ali, "Danışmanlık", False), (k.ali, "Lexis Raporu", False), (k.ayse, "Lexis Raporu", True),
    ]
    assert _ozet(db, k.k1) == "Danışmanlık ; Lexis Raporu"
    assert _satirlar(db, k.k2) == [(k.veli, "Vekaletli Takip", False)] and _ozet(db, k.k2) == "Vekaletli Takip"
    db.close()


def test_tasiyarak_silmede_cakisan_elle_satir_birlesir(ortam):
    """Kural: Lexis Rapor → Danışmanlık taşımasında Ali'nin iki elle satırı TEK satıra iner
    (kısmi UNIQUE çakışması birleştirilir); föy satırı çevrilir; özet yenilenir."""
    k = _liste_kurgusu(ortam)

    sonuc = ortam.lists.delete_item("service_types", "LEXIS-RAPOR", mode="reassign", target="DANISMANLIK")

    assert sonuc == {"affected": 2}, "1 föy satırı çevrildi + 1 elle satır birleşti"
    db = ortam.maker()
    assert _satirlar(db, k.k1) == [(k.ali, "Danışmanlık", False), (k.ayse, "Danışmanlık", True)]
    assert _ozet(db, k.k1) == "Danışmanlık"
    assert _satirlar(db, k.k2) == [(k.veli, "Vekaletli Takip", False)]
    assert db.query(models.ServiceType).filter(models.ServiceType.code == "LEXIS-RAPOR").first() is None
    db.close()


def test_kullanimdaki_hizmet_bosaltilarak_silinemez(ortam):
    from managers.reference_lists import ItemInUseError

    k = _liste_kurgusu(ortam)

    kullanim = ortam.lists.get_usage("service_types", "LEXIS-RAPOR")
    assert kullanim["clearable"] is False
    assert {"label": "dava hizmeti", "count": 2, "clearable": False} in kullanim["items"]

    for mod in ("clear", "block"):
        with pytest.raises(ItemInUseError):
            ortam.lists.delete_item("service_types", "LEXIS-RAPOR", mode=mod)

    db = ortam.maker()
    assert db.query(models.ServiceType).filter(models.ServiceType.code == "LEXIS-RAPOR").first() is not None
    assert (k.ayse, "Lexis Rapor", True) in _satirlar(db, k.k1)
    db.close()

    # Kullanılmayan değer doğrudan silinir
    assert ortam.lists.delete_item("service_types", "CEVIRI", mode="clear") == {"affected": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 5. dbtest — gerçek Postgres (scratch DB; yoksa SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_admin():
    """test_migration_path.admin_engine'in yereli (fixture import F811 üretir)."""
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")
    admin = create_engine(
        url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        admin.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G248 dbtest atlandı")
    yield admin
    admin.dispose()


def _ozet_kolon_tipi(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'cases' AND column_name = 'hizmet_turu'"
        )).scalar()


@pytest.mark.dbtest
def test_pg_sifirdan_kurulum_tablo_indexler_ve_idempotent(pg_admin):
    with _scratch_database(pg_admin, "g248_fresh") as engine:
        _run_init_db(engine)
        once = _live_indexes(engine)

        assert INDEX_ADLARI <= set(once)
        assert "(case_id)" in once["idx_case_hizmetleri_case"]
        assert "(case_party_id)" in once["idx_case_hizmetleri_party"]
        assert once["uq_case_hizmetleri_foy"].startswith("CREATE UNIQUE INDEX")
        assert "WHERE (foy_id IS NOT NULL)" in once["uq_case_hizmetleri_foy"]
        assert once["uq_case_hizmetleri_elle"].startswith("CREATE UNIQUE INDEX")
        assert "(case_id, case_party_id, hizmet_turu) WHERE (foy_id IS NULL)" in once["uq_case_hizmetleri_elle"]
        assert "ix_case_hizmetleri_id" not in once, "PK ikizi (G192)"
        assert _ozet_kolon_tipi(engine) == "text"

        _run_init_db(engine)
        assert _live_indexes(engine) == once, "ikinci init_db index'leri değiştirdi"
        assert _ozet_kolon_tipi(engine) == "text"


@pytest.mark.dbtest
def test_pg_mevcut_kurulum_tablo_opu_ve_kolon_genisletmesi(pg_admin):
    """create_all'ın koşmadığı yol: tablo yoksa ("table", ...) op'u kurar, index op'u index'leri
    ekler; `cases.hizmet_turu` VARCHAR(100) ise TEXT'e genişler ve veri korunur. Kısmi UNIQUE'ler
    ve RESTRICT gerçek Postgres'te çalışır."""
    with _scratch_database(pg_admin, "g248_tableop") as engine:
        _run_init_db(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE case_hizmetleri"))
            conn.execute(text("ALTER TABLE cases ALTER COLUMN hizmet_turu TYPE VARCHAR(100)"))
            conn.execute(text(
                "INSERT INTO cases (tracking_no, status, active, hizmet_turu) "
                "VALUES ('G248-PG-1', 'DERDEST', true, 'Lexis Rapor')"
            ))
        assert _ozet_kolon_tipi(engine) == "character varying"

        original = database.engine
        database.engine = engine
        try:
            database.check_and_migrate_tables()
        finally:
            database.engine = original

        assert INDEX_ADLARI <= set(_live_indexes(engine))
        assert _ozet_kolon_tipi(engine) == "text"

        with engine.begin() as conn:
            cid = conn.execute(text("SELECT id FROM cases WHERE tracking_no = 'G248-PG-1'")).scalar()
            assert conn.execute(text("SELECT hizmet_turu FROM cases WHERE id = :c"), {"c": cid}).scalar() == "Lexis Rapor"
            uzun = " ; ".join(ad for _, ad in HIZMETLER) * 4
            assert len(uzun) > 100
            conn.execute(text("UPDATE cases SET hizmet_turu = :o WHERE id = :c"), {"o": uzun, "c": cid})
            pid = conn.execute(text(
                "INSERT INTO case_parties (case_id, name, role, party_type) "
                "VALUES (:c, 'Ali Veli', 'Davalı', 'CLIENT') RETURNING id"
            ), {"c": cid}).scalar()
            f1, f2 = (
                conn.execute(text(
                    "INSERT INTO case_foys (sistem_no, case_id, case_party_id) VALUES (:s, :c, :p) RETURNING id"
                ), {"s": s, "c": cid, "p": pid}).scalar()
                for s in ("SSTMN-1", "SSTMN-2")
            )
            ekle = text(
                "INSERT INTO case_hizmetleri (case_id, case_party_id, hizmet_turu, foy_id) "
                "VALUES (:c, :p, 'Lexis Rapor', :f)"
            )
            conn.execute(ekle, {"c": cid, "p": pid, "f": None})
            conn.execute(ekle, {"c": cid, "p": pid, "f": f1})
            conn.execute(ekle, {"c": cid, "p": pid, "f": f2})   # iki föy aynı müvekkil+hizmet: serbest
            assert conn.execute(text("SELECT COUNT(created_at) FROM case_hizmetleri")).scalar() == 3

        for f, kisit in ((None, "uq_case_hizmetleri_elle"), (f1, "uq_case_hizmetleri_foy")):
            with pytest.raises(IntegrityError) as hata:
                with engine.begin() as conn:
                    conn.execute(ekle, {"c": cid, "p": pid, "f": f})
            assert kisit in str(hata.value)

        with pytest.raises(IntegrityError):     # RESTRICT: hizmet kaydı olan taraf silinemez
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM case_hizmetleri WHERE foy_id IS NOT NULL"))
                conn.execute(text("DELETE FROM case_foys"))
                conn.execute(text("DELETE FROM case_parties WHERE id = :p"), {"p": pid})
        with pytest.raises(IntegrityError):     # RESTRICT: hizmet satırı olan föy silinemez
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM case_foys WHERE id = :f"), {"f": f1})
