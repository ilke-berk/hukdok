"""G123 — Teslim paketinin 54 sütununun TAMAMI bizde (05.09.2026).

04.09 paketinin 54 sütununu tek tek koda karşı saydık: üçü hiç yoktu
(Dosya - Föy Bilgileri, Para Birimi TL, MüvekkilNo), biri ham hâliyle
saklanmıyordu (Dava Değeri TL), biri kolonu olduğu hâlde beslenmiyordu
(İstinaf Mahkeme Başvuru Tar.), ikisi aşama tablosunda durup karta
yansımıyordu (Yerel Mahkeme Tebliğ Tarihi / Kararı Açıklaması), "Eski Dosya
No" Sheet'ten okunmuyordu; föy düzeyinde gelen Müvekkil Tipi / Hizmet Türü /
Durum ise kart tek slotunda kardeş föy çelişkisiyle kayboluyordu (973 kart).
Bu dosya o boşlukların kapandığını kilitler.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
testler openpyxl ile SENTETİK mini paket üretir (test_g120 düzeni).
"""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import case_manager, foy_map, stage_decisions
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import HamSatir, aktarimi_kos, xlsx_oku
from services import teslim_kutusu

BASLIKLAR = [
    "Dosya - Föy Bilgileri", "SistemNo", "Dosya No", "Klasör No", "Durum",
    "Dava Değeri TL", "Manevi Dava Değeri TL", "Para Birimi TL", "MüvekkilNo",
    "Müvekkil Tipi", "Hizmet Türü", "Eski Dosya No", "İstinaf Mahkeme Başvuru Tar.",
]


def _paket_yaz(yol, satirlar, *, basliklar=None, sayfa="Sheet"):
    from openpyxl import Workbook

    kullanilan = list(basliklar if basliklar is not None else BASLIKLAR)
    wb = Workbook()
    ws = wb.active
    ws.title = sayfa
    ws.append(kullanilan)
    for satir in satirlar:
        ws.append([satir.get(baslik) for baslik in kullanilan])
    wb.save(yol)
    wb.close()
    return Path(yol)


def _satir(sistem_no, dosya_no, **extra):
    temel = {"SistemNo": sistem_no, "Dosya No": dosya_no, "Klasör No": "TKU-123"}
    temel.update(extra)
    return temel


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — kayıt kilitleri (DB yok)
# ═══════════════════════════════════════════════════════════════════════════

def test_bes_yeni_baslik_taniniyor():
    """Bilgilendirme belgesinin "okunmayan sütunlar" tablosundan çıkan beşi."""
    taninan, taninmayan = teslim_kutusu.basliklari_tani([
        "SistemNo", "Dosya No", "Dosya - Föy Bilgileri", "Para Birimi TL",
        "MüvekkilNo", "Eski Dosya No", "İstinaf Mahkeme Başvuru Tar.",
    ])
    assert {"mko_id", "para_birimi", "muvekkil_no", "eski_dosya_no",
            "istinaf_basvuru_tarihi"} <= set(taninan)
    assert taninmayan == []


def test_kart_alanlari_ve_foy_alanlari_kaydi():
    assert hukdok_aktarim.KART_ALANLARI["dava_degeri"] == ("dava_degeri", hukdok_aktarim._sayi)
    assert hukdok_aktarim.KART_ALANLARI["para_birimi"] == ("para_birimi", hukdok_aktarim._metin_alan)
    assert hukdok_aktarim.KART_ALANLARI["istinaf_basvuru_tarihi"] == (
        "istinaf_basvuru_tarihi", hukdok_aktarim._tarih)
    # Maddi türetmesi (D4) sürüyor: ham dava değeri saklanınca türetme kalkmadı.
    assert "maddi_tazminat" in hukdok_aktarim.KART_TURETILEN
    # Föy düzeyi alanlar foy_map'in güncellenebilir kümesinde ve modelde.
    for alan in ("mko_id", "muvekkil_no", "muvekkil_tipi", "hizmet_turu", "durum"):
        assert alan in foy_map._UPDATABLE
        assert alan in models.CaseFoy.__table__.columns
    for alan in ("dava_degeri", "para_birimi"):
        assert alan in models.Case.__table__.columns


def test_migrasyon_kolonlari_modelle_ayni():
    """Madde 43: kolon op'ları modeldeki adlarla birebir (sıfırdan kurulumda
    create_all, mevcut kurulumda ALTER — iki yol aynı şemaya çıkmalı)."""
    cases_ops = [op[2] for op in _MIGRATIONS if op[0] == "columns" and op[1] == "cases"]
    foy_ops = [op[2] for op in _MIGRATIONS if op[0] == "columns" and op[1] == "case_foys"]
    assert any({"dava_degeri", "para_birimi"} <= set(op) for op in cases_ops)
    assert any({"mko_id", "muvekkil_no", "muvekkil_tipi", "hizmet_turu", "durum"} <= set(op)
               for op in foy_ops)


def test_yerel_fotografi_teblig_ve_aciklamayi_tasiyor():
    assert stage_decisions._PHOTO_COLUMNS["YEREL"]["teblig_tarihi"] == "karar_teblig_tarihi"
    assert stage_decisions._PHOTO_COLUMNS["YEREL"]["aciklama"] == "karar_aciklama"


def test_fotograf_geri_doldurma_yalniz_bos_kolonu_doldurur():
    """Madde 43'ün UPDATE'leri `IS NULL` kapılı: elle girilmiş tebliğ/açıklama
    ezilmez, ikinci koşu 0 satır günceller (idempotent)."""
    sqls = [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == "cases"
            for sql in op[2] if sql.lstrip().upper().startswith("UPDATE")]
    assert len(sqls) == 2
    for sql in sqls:
        assert "IS NULL" in sql and "stage = 'YEREL'" in sql and "MAX(sira_no)" in sql


def test_foy_degerleri_kayipsiz():
    """Tanınan değer kanonik adla, tanınmayan/çok değerli hücre HAM yazımıyla,
    durum kart havuzuna eşlenmiş; boş hücre None (korunur)."""
    satir = HamSatir(satir_no=2, degerler={
        "mko_id": 9425, "muvekkil_no": "1137",
        "muvekkil_tipi": "SİGORTA", "hizmet_turu": "Lexis Rapor ; Vekaletli Takip",
        "durum": "Arşiv",
    })
    assert hukdok_aktarim.foy_degerleri(satir) == {
        "mko_id": "9425", "muvekkil_no": "1137",
        "muvekkil_tipi": "Sigorta",                        # kanonik ad
        "hizmet_turu": "Lexis Rapor ; Vekaletli Takip",    # çok değer: ham kalır, kayıp yok
        "durum": "MAHZEN",
    }
    bos = HamSatir(satir_no=3, degerler={"durum": "Kapalı"})
    assert hukdok_aktarim.foy_degerleri(bos) == {
        "mko_id": None, "muvekkil_no": None, "muvekkil_tipi": None,
        "hizmet_turu": None, "durum": "Kapalı",            # eşlenemeyen yazım ham
    }


def test_arama_foy_kimliklerini_kapsiyor():
    """TKU/SistemNo aktarımla `case_foys`a yazılıyor; arama yalnız boş legacy
    kolonlara bakıyordu — iki `case_foys` kolu eklendi."""
    sql = " ".join(str(s.compile(compile_kwargs={"literal_binds": True}))
                   for s in case_manager._term_case_id_selects("TKU-784", False))
    assert "case_foys.tku_no" in sql and "case_foys.sistem_no" in sql


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite (test_g064 fixture reçetesi)
# ═══════════════════════════════════════════════════════════════════════════

def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table
            for sql in op[2] if not sql.lstrip().upper().startswith("UPDATE")]


@pytest.fixture()
def db_env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops("case_foys"):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture()
def kart(db_env):
    db = db_env()
    try:
        case = models.Case(tracking_no="HA.G123.1", status="DERDEST", klasor_no_2="D-1",
                           esas_no="2024/10")
        db.add(case)
        db.flush()
        case_manager.sync_current_esas(db, case, "2024/10", source="test")
        db.commit()
    finally:
        db.close()
    return db_env


def _tam_satir(**extra):
    return _satir("H-1", "D-1", **{
        "Dosya - Föy Bilgileri": 9425, "Durum": "Arşiv",
        "Dava Değeri TL": 250000, "Manevi Dava Değeri TL": 50000,
        "Para Birimi TL": "TL", "MüvekkilNo": "1137",
        "Müvekkil Tipi": "Doktor", "Hizmet Türü": "Lexis Rapor",
        "Eski Dosya No": "2021/588",
        "İstinaf Mahkeme Başvuru Tar.": datetime(2025, 11, 24),
        **extra,
    })


def test_kart_alanlari_foy_alanlari_ve_eski_esas_yazilir(kart, tmp_path):
    paket = _paket_yaz(tmp_path / "t.xlsx", [_tam_satir()])

    sonuc = aktarimi_kos(kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == 0
    assert sonuc.onceki_esas_eklenen == 1
    db = kart()
    try:
        c = db.query(models.Case).one()
        assert c.dava_degeri == Decimal("250000")
        assert c.maddi_tazminat == Decimal("200000")       # D4 türetmesi sürüyor
        assert c.para_birimi == "TL"
        assert c.istinaf_basvuru_tarihi == date(2025, 11, 24)
        assert c.status == "MAHZEN" and c.muvekkil_tipi == "Doktor"
        assert c.esas_no == "2024/10"                      # güncel işaret DEĞİŞMEDİ
        esaslar = {(e.esas_no, e.stage, e.is_current) for e in c.esas_numbers}
        assert ("2021/588", "ONCEKI", False) in esaslar
        foy = db.query(models.CaseFoy).one()
        assert (foy.mko_id, foy.muvekkil_no) == ("9425", "1137")
        assert (foy.muvekkil_tipi, foy.hizmet_turu, foy.durum) == ("Doktor", "Lexis Rapor", "MAHZEN")
    finally:
        db.close()


def test_ikinci_kosu_sifir_degisiklik(kart, tmp_path):
    paket = _paket_yaz(tmp_path / "t.xlsx", [_tam_satir()])
    aktarimi_kos(kart, girdi=paket, rapor_dizini=tmp_path / "r1")

    ikinci = aktarimi_kos(kart, girdi=paket, rapor_dizini=tmp_path / "r2")

    assert ikinci.alan_degisikligi == 0
    assert ikinci.onceki_esas_eklenen == 0
    db = kart()
    try:
        assert db.query(models.CaseEsasNumber).filter_by(stage="ONCEKI").count() == 1
    finally:
        db.close()


def test_kardes_foy_celiskisinde_foy_degeri_kaybolmaz(kart, tmp_path):
    """Kartın iki föyü farklı hizmet türü söylüyor: kart alanı YAZILMAZ (D9),
    ama her föy kendi değerini taşır — 973 kartın kaybı bu satırla kapanır."""
    paket = _paket_yaz(tmp_path / "t.xlsx", [
        _satir("H-1", "D-1", **{"Hizmet Türü": "Lexis Rapor", "Durum": "Aktif",
                                "Müvekkil Tipi": "Doktor"}),
        _satir("H-2", "D-1", **{"Hizmet Türü": "Vekaletli Takip", "Durum": "Arşiv",
                                "Müvekkil Tipi": "Doktor"}),
    ])

    sonuc = aktarimi_kos(kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert {c.alan for c in sonuc.celiskiler} >= {"hizmet_turu", "status"}
    db = kart()
    try:
        c = db.query(models.Case).one()
        assert c.hizmet_turu is None and c.status == "DERDEST"   # kart: çelişki, yazılmadı
        assert c.muvekkil_tipi == "Doktor"                        # uzlaşan alan yazıldı
        foyler = {f.sistem_no: (f.hizmet_turu, f.durum) for f in db.query(models.CaseFoy)}
        assert foyler == {"H-1": ("Lexis Rapor", "DERDEST"),
                          "H-2": ("Vekaletli Takip", "MAHZEN")}
    finally:
        db.close()


def test_eksik_baslik_foy_alanini_ellemiyor(kart, tmp_path):
    """Partili teslim: başlık yoksa föydeki dolu değer korunur (None = yok)."""
    tam = _paket_yaz(tmp_path / "tam.xlsx", [_tam_satir()])
    aktarimi_kos(kart, girdi=tam, rapor_dizini=tmp_path / "r1")
    dar = _paket_yaz(tmp_path / "dar.xlsx", [_satir("H-1", "D-1")],
                     basliklar=["SistemNo", "Dosya No", "Klasör No"])

    aktarimi_kos(kart, girdi=dar, rapor_dizini=tmp_path / "r2")

    db = kart()
    try:
        foy = db.query(models.CaseFoy).one()
        assert (foy.mko_id, foy.hizmet_turu, foy.durum) == ("9425", "Lexis Rapor", "MAHZEN")
        c = db.query(models.Case).one()
        assert c.dava_degeri == Decimal("250000") and c.para_birimi == "TL"
    finally:
        db.close()


def test_get_case_yeni_alanlari_donduruyor(kart, tmp_path, monkeypatch):
    paket = _paket_yaz(tmp_path / "t.xlsx", [_tam_satir()])
    aktarimi_kos(kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    monkeypatch.setattr(case_manager, "SessionLocal", kart)

    veri = case_manager.get_case(1)

    assert veri["dava_degeri"] == 250000.0 and veri["para_birimi"] == "TL"
    assert veri["istinaf_basvuru_tarihi"] == "2025-11-24"
    foy = veri["foyler"][0]
    assert foy["mko_id"] == "9425" and foy["muvekkil_no"] == "1137"
    assert (foy["muvekkil_tipi"], foy["hizmet_turu"], foy["durum"]) == ("Doktor", "Lexis Rapor", "MAHZEN")
    assert [e["esas_no"] for e in veri["esas_numbers"]] == ["2024/10", "2021/588"]


def test_xlsx_oku_mko_id_ve_para_birimi(tmp_path):
    paket = _paket_yaz(tmp_path / "t.xlsx", [_tam_satir()])
    satirlar, bulunanlar = xlsx_oku(paket)
    assert bulunanlar["mko_id"] == "Dosya - Föy Bilgileri"
    assert bulunanlar["para_birimi"] == "Para Birimi TL"
    assert bulunanlar["eski_dosya_no"] == "Eski Dosya No"
    assert satirlar[0].degerler["mko_id"] == 9425
