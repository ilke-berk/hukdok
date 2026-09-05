"""G126 — Kartsız föyler için kart açma (05.09.2026 kullanıcı kararı).

Aktarım kart açmaz; 04.09 paketinde 217 föy / 210 DosyaNo kartsızdı. Script
DosyaNo başına MİNİMAL kart açar (ofis no mevcut kuralla: kategori + isim
bloğu + blok başına max+1 + tür), taraf/avukat yazmaz (aktarımın işi), ikinci
koşuda 0 kart (DosyaNo artık kartlı). Sentetik paket (A.2).
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import case_manager
from scripts import hukdok_aktarim
from scripts import kartsiz_foy_kart_ac as kk

BASLIKLAR = ["SistemNo", "Dosya No", "Klasör No", "Müvekkil", "Müvekkil Tipi", "Ana Tür",
             "Durum", "Dava Konusu", "Yerel Mahkeme", "Esas", "Dava Tarihi"]


def _paket_yaz(yol, satirlar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(BASLIKLAR)
    for s in satirlar:
        ws.append([s.get(b) for b in BASLIKLAR])
    wb.save(yol)
    wb.close()
    return Path(yol)


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table
            for sql in op[2] if not sql.lstrip().upper().startswith(("UPDATE", "ALTER"))]


@pytest.fixture()
def db_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops("case_foys"):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


SATIRLAR = [
    # mevcut karta düşen föy (D-1) → kartsız DEĞİL
    {"SistemNo": "H-1", "Dosya No": "D-1", "Müvekkil": "Ali Var Dr.", "Müvekkil Tipi": "Doktor",
     "Ana Tür": "HUKUK", "Durum": "Aktif"},
    # aynı DosyaNo'da ARB + HUKUK → TEK kart, tür HUKUK, durum DERDEST
    {"SistemNo": "ARB-2", "Dosya No": "2005.001", "Müvekkil": "Hülya Artuç Dr", "Müvekkil Tipi": "Doktor",
     "Ana Tür": "ARABULUCULUK", "Durum": "Arşiv", "Dava Konusu": "Tazminat"},
    {"SistemNo": "H-3", "Dosya No": "2005.001", "Müvekkil": "Hülya Artuç Dr", "Müvekkil Tipi": "Doktor",
     "Ana Tür": "HUKUK", "Durum": "Aktif", "Yerel Mahkeme": "Bursa 3. Asliye Hukuk", "Esas": "2026/12",
     "Dava Tarihi": "2026-02-01"},
    # sigorta müvekkili → S4.QUICK
    {"SistemNo": "H-4", "Dosya No": "4.100.00", "Müvekkil": "Quick Sigorta A.Ş.", "Müvekkil Tipi": "Sigorta",
     "Ana Tür": "İDARE", "Durum": "Aktif"},
    # Dosya No boş → köprü yok, kart açılmaz
    {"SistemNo": "H-5", "Dosya No": None, "Müvekkil": "Boş Dosya", "Müvekkil Tipi": "Hasta",
     "Ana Tür": "HUKUK", "Durum": "Aktif"},
]


@pytest.fixture()
def ortam(db_env, monkeypatch):
    db = db_env()
    try:
        db.add(models.Case(tracking_no="D1.A_VAR......0001.HUKUK.00000", status="DERDEST", klasor_no_2="D-1"))
        # aynı isim bloğunda mevcut bir kart: sıra max+1 = 0004 olmalı
        db.add(models.Case(tracking_no="D1.H_ARTUC....0003.IDARE.00000", status="MAHZEN", klasor_no_2="Z-9"))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(case_manager, "SessionLocal", db_env)
    return db_env


def test_kuru_kosu_aday_uretir_kart_acmaz(ortam, tmp_path):
    paket = _paket_yaz(tmp_path / "p.xlsx", SATIRLAR)

    adaylar = kk.kartlari_ac(ortam, girdi=paket, rapor_dizini=tmp_path / "r")

    by = {a.dosya_no: a for a in adaylar}
    assert set(by) == {"2005.001", "4.100.00"}                       # D-1 kartlı, H-5 dosya no boş
    assert by["2005.001"].sistem_nolar == ["ARB-2", "H-3"]
    assert by["2005.001"].tracking_no == "D1.H_ARTUC....0004.HUKUK.00000"   # blok max 3 → 4, tür HUKUK
    assert by["2005.001"].status == "DERDEST" and by["2005.001"].esas_no == "2026/12"
    assert by["4.100.00"].tracking_no == "S4.QUICK......0001.IDARE.00000"
    db = ortam()
    try:
        assert db.query(models.Case).count() == 2                    # kuru koşu: açılmadı
    finally:
        db.close()
    assert list((tmp_path / "r").glob("acilan-kartlar_*.csv"))


def test_apply_kart_acar_aktarim_baglar_ikinci_kosu_sifir(ortam, tmp_path):
    paket = _paket_yaz(tmp_path / "p.xlsx", SATIRLAR)

    adaylar = kk.kartlari_ac(ortam, girdi=paket, apply=True)

    assert all(a.case_id for a in adaylar) and len(adaylar) == 2
    db = ortam()
    try:
        yeni = db.query(models.Case).filter_by(klasor_no_2="2005.001").one()
        assert yeni.tracking_no == "D1.H_ARTUC....0004.HUKUK.00000"
        assert yeni.esas_no == "2026/12" and yeni.court == "Bursa 3. Asliye Hukuk"
        assert yeni.parties == [] and yeni.lawyers == []             # taraf/avukat aktarımın işi
        assert "ARB-2" in (yeni.notes or "")
    finally:
        db.close()

    # aktarım: föyler yeni kartlara DosyaNo köprüsüyle bağlanır
    sonuc = hukdok_aktarim.aktarimi_kos(ortam, girdi=paket, rapor_dizini=tmp_path / "a")
    assert sonuc.foy_yeni == 4                                       # H-1, ARB-2, H-3, H-4 (H-5 dosya no boş)
    assert not any("Kart bulunamadı" in r.sebep for r in sonuc.rapor_satirlari)
    db = ortam()
    try:
        yeni = db.query(models.Case).filter_by(klasor_no_2="2005.001").one()
        assert {f.sistem_no for f in yeni.foys} == {"ARB-2", "H-3"}
        assert {p.name for p in yeni.parties} == {"Hülya Artuç Dr"}
    finally:
        db.close()

    # ikinci koşu: kartsız föy kalmadı
    ikinci = kk.kartlari_ac(ortam, girdi=paket, apply=True)
    assert ikinci == []


def test_muvekkil_bos_hata_kart_acilmaz(ortam, tmp_path):
    paket = _paket_yaz(tmp_path / "p.xlsx", [
        {"SistemNo": "H-9", "Dosya No": "9.9.00", "Müvekkil": None, "Ana Tür": "HUKUK", "Durum": "Aktif"},
    ])
    adaylar = kk.kartlari_ac(ortam, girdi=paket, apply=True)
    assert adaylar[0].hata and adaylar[0].case_id is None
