"""G152 — `status` kesim-sonrası koruma: kullanıcı imzalı `case_history` varsa
paket `status`u yazmaz; `DEGISIKLIK_OZETI` "Veri kesim tarihi"; elle yol imzası.

Kullanıcı kararı 08.09 (plan §1.5 P2): "paket kazanır"ın TEK istisnası. Ekibin
veri kesimi 30.07.2026; o tarihten sonra bizde MAHZEN'e alınan kartı paket
`AKTIF → DERDEST` ile geri açıyordu. Ekip de "Durum'da HukuDok'un güncel
kaydı esas" diyor.

Katmanlar:
1. Kesim tarihi kaynağı — özet sayfası ayrıştırıcı (`kesim_tarihi_oku`), üç
   kaynaklı arayıcı (`kesim_tarihi_bul`: sayfa → paket adı + WARNING → yok),
   CLI çözümü (`_cli_kesim_tarihi`).
2. Koruma kuralı (sqlite, G064 fixture'ları) — kesim sonrası kullanıcı kaydı
   → korunur + rapor + sayaç; kesim öncesi / aktarım imzalı / kural kapalı →
   paket yazar; yalnız `status`; ikinci koşu; teslim hattı parametreyi geçer.
3. Elle yol imzası — `update_case` ve `update_case_tracking` (`status`)
   tarihçesi `changed_by` + `source="panel"`; uçtan uca panel → paket.

Fixture'lar G064'ten (pysqlite SAVEPOINT reçetesi tek kaynakta). Gerçek paket
repoya GİRMEZ (A.2) — sentetik paket.
"""
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from managers import case_manager
from required_fields import AKTARIM_SOURCE_PREFIX
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    CIKIS_TAMAM,
    STATUS_KORUNDU_TURU,
    AktarimHatasi,
    AktarimSonucu,
    aktarimi_kos,
    ozet_metni,
)
from services import teslim_kutusu as tk

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN (pysqlite SAVEPOINT reçetesi).
# Modül niteliği olarak takılır: `from ... import db_env` + parametre adı ruff'ta
# F811 (yeniden tanım) sanılır; nitelik ataması pytest için aynı fixture'dır
# ve susturma gerektirmez.
from tests import test_g064_aktarim_cekirdek as g064
from tests.test_g064_aktarim_cekirdek import BASLIKLAR, _paket_yaz, _satir
from tests.test_g107_teslim_kutusu import _paket as _teslim_paketi

db_env = g064.db_env
uc_kart = g064.uc_kart

KESIM = date(2026, 7, 30)
BASLIKLAR_DURUMLU = BASLIKLAR + ["Durum"]
AKTARIM_IMZASI = f"{AKTARIM_SOURCE_PREFIX}_HUKDOK_TESLIM_ESKI.xlsx"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kesim tarihi kaynağı
# ═══════════════════════════════════════════════════════════════════════════

def _ozet_ws(satirlar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for satir in satirlar:
        ws.append(satir)
    return ws


@pytest.mark.parametrize("satirlar,beklenen", [
    ([["Veri kesim tarihi", "30.07.2026"]], KESIM),
    ([["Veri Kesim Tarihi: 2026-07-30"]], KESIM),
    ([["VERİ KESİM TARİHİ", None, "30.07.2026"]], KESIM),           # sonraki dolu hücre
    ([["Veri kesim tarihi", datetime(2026, 7, 30, 0, 0)]], KESIM),   # tarih hücresi
    ([["Bu teslim", "X.xlsx"], ["Önceki teslim", "Y.xlsx"], ["Veri kesim tarihi", "30.07.2026"]], KESIM),
    ([["Veri kesim tarihi", "—"]], None),
    ([["Veri kesim tarihi", None]], None),
    ([["Önceki teslim", "Y.xlsx"]], None),
])
def test_kesim_tarihi_oku_ayristirma(satirlar, beklenen):
    """Etiket aksan/boşluk/iki nokta duyarsız; değer aynı hücrede ya da sonraki
    dolu hücrede; tarih hücresi de olur; yer tutucu / yok → None."""
    assert tk.kesim_tarihi_oku(_ozet_ws(satirlar)) == beklenen


def test_kesim_tarihi_oku_cozumlenemeyen_none_ve_warning(caplog):
    """Bozuk tarih paketi reddetmez: None (kural kapanır) + WARNING — sessiz düşüş yok."""
    with caplog.at_level(logging.WARNING, logger="services.teslim_kutusu"):
        assert tk.kesim_tarihi_oku(_ozet_ws([["Veri kesim tarihi", "31.02.2026"]])) is None
    assert any("Veri kesim tarihi" in r.getMessage() for r in caplog.records)


def test_onceki_teslim_adi_oku_davranisi_degismedi():
    """Ortak ayrıştırıcıya geçiş (`_ozet_etiket_degeri`) G107 sözleşmesini korur."""
    assert tk.onceki_teslim_adi_oku(_ozet_ws(
        [["Önceki teslim", "HUKDOK_TESLIM_A.xlsx · 8.409 satır × 68 sütun"]]
    )) == "HUKDOK_TESLIM_A.xlsx"
    assert tk.onceki_teslim_adi_oku(_ozet_ws([["Önceki teslim", "—"]])) is None
    assert tk.onceki_teslim_adi_oku(_ozet_ws([["Veri kesim tarihi", "30.07.2026"]])) is None


def _paket_dosyasi(tmp_path, ad, *, ozet_satirlari=None) -> Path:
    yol = tmp_path / ad
    yol.write_bytes(_teslim_paketi([_satir("SSTMN-1", "D-1")], ozet_satirlari=ozet_satirlari))
    return yol


def test_kesim_tarihi_bul_once_ozet_sayfasi(tmp_path, caplog):
    """1. kaynak: sayfa satırı — paket adındaki (farklı) tarihi ezer, WARNING yok."""
    yol = _paket_dosyasi(tmp_path, "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx",
                         ozet_satirlari=[["Önceki teslim", "—"], ["Veri kesim tarihi", "30.07.2026"]])
    with caplog.at_level(logging.INFO, logger="services.teslim_kutusu"):
        assert tk.kesim_tarihi_bul(yol, yol.name) == KESIM
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_kesim_tarihi_bul_sonra_paket_adi_warning(tmp_path, caplog):
    """2. kaynak: sayfa yok (ya da satır yok) → paket adındaki ISO tarih + WARNING."""
    sayfasiz = _paket_dosyasi(tmp_path, "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx")
    with caplog.at_level(logging.WARNING, logger="services.teslim_kutusu"):
        assert tk.kesim_tarihi_bul(sayfasiz, sayfasiz.name) == date(2026, 9, 4)
    assert any("paket adındaki tarih" in r.getMessage() for r in caplog.records)

    satirsiz = _paket_dosyasi(tmp_path, "HUKDOK_TESLIM_2026-08-15.xlsx",
                              ozet_satirlari=[["Önceki teslim", "X.xlsx"]])
    assert tk.kesim_tarihi_bul(satirsiz, satirsiz.name) == date(2026, 8, 15)


def test_kesim_tarihi_bul_hicbiri_yoksa_none(tmp_path):
    """3. durum: kaynak yok → None (WARNING'i `aktarimi_kos` basar — aşağıda)."""
    yol = _paket_dosyasi(tmp_path, "teslim.xlsx")
    assert tk.kesim_tarihi_bul(yol, yol.name) is None
    assert tk.kesim_tarihi_bul(yol, "HUKDOK_TESLIM_20260904.xlsx") is None      # ISO değil


def test_cli_kesim_tarihi_cozumu(tmp_path):
    """`--kesim-tarihi` açık değer iki biçimde; bozuk değer AktarimHatasi;
    verilmezse teslim hattıyla AYNI arayıcı."""
    yol = _paket_dosyasi(tmp_path, "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx",
                         ozet_satirlari=[["Veri kesim tarihi", "30.07.2026"]])
    assert hukdok_aktarim._cli_kesim_tarihi("30.07.2026", yol) == KESIM
    assert hukdok_aktarim._cli_kesim_tarihi("2026-07-30", yol) == KESIM
    assert hukdok_aktarim._cli_kesim_tarihi(None, yol) == KESIM
    with pytest.raises(AktarimHatasi, match="kesim-tarihi"):
        hukdok_aktarim._cli_kesim_tarihi("31.02.2026", yol)
    with pytest.raises(AktarimHatasi, match="kesim-tarihi"):
        hukdok_aktarim._cli_kesim_tarihi("yok", yol)                # yer tutucu → None → hata


# ═══════════════════════════════════════════════════════════════════════════
# 2. Koruma kuralı — sqlite
# ═══════════════════════════════════════════════════════════════════════════

def _kart_id(fabrika, klasor) -> int:
    db = fabrika()
    try:
        return db.query(models.Case.id).filter(models.Case.klasor_no_2 == klasor).scalar()
    finally:
        db.close()


def _durum_gecmisi(fabrika, klasor, *, yeni="MAHZEN", changed_at, source=None, changed_by=None):
    """Kartı `yeni` duruma alır ve tarihçeye verilen imzayla satır düşer."""
    db = fabrika()
    try:
        case = db.query(models.Case).filter(models.Case.klasor_no_2 == klasor).one()
        db.add(models.CaseHistory(
            case_id=case.id, field_name="status", old_value=case.status, new_value=yeni,
            changed_at=changed_at, changed_by=changed_by, source=source,
        ))
        case.status = yeni
        db.commit()
    finally:
        db.close()


def _kart(fabrika, klasor):
    db = fabrika()
    try:
        return db.query(models.Case).filter(models.Case.klasor_no_2 == klasor).one()
    finally:
        db.close()


def _status_tarihcesi(fabrika, klasor):
    db = fabrika()
    try:
        return (
            db.query(models.CaseHistory)
            .join(models.Case, models.Case.id == models.CaseHistory.case_id)
            .filter(models.Case.klasor_no_2 == klasor, models.CaseHistory.field_name == "status")
            .count()
        )
    finally:
        db.close()


def _aktif_paket(tmp_path, **ek):
    return _paket_yaz(tmp_path / "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Durum": "Aktif", "Tıbbi Olay": "Enfeksiyon", **ek}),
        _satir("SSTMN-2", "D-2", **{"Durum": "Aktif"}),
    ], basliklar=BASLIKLAR_DURUMLU)


def test_kesim_sonrasi_kullanici_kaydi_korunur_rapor_ve_sayac(uc_kart, tmp_path):
    """ÇEKİRDEK: 05.08'de kullanıcı MAHZEN'e almış (imzasız — dünkü elle yol);
    paket `Aktif` diyor → status MAHZEN kalır, öteki alan yazılır, rapor
    satırı KORUNDU (HATA değil: çıkış kodu 0), sayaç 1, tarihçe büyümez.
    Eski kodda status DERDEST'e dönerdi — kırmızı."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 5, 10, 0))
    paket = _aktif_paket(tmp_path)

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor", kesim_tarihi=KESIM)

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.yazildi
    assert sonuc.korunan_alan == 1 and sonuc.kesim_tarihi == KESIM
    kart = _kart(uc_kart, "D-1")
    assert kart.status == "MAHZEN"                       # paket yazmadı
    assert kart.tibbi_olay == "Enfeksiyon"               # kural yalnız status
    assert _kart(uc_kart, "D-2").status == "DERDEST"     # zaten DERDEST, değişiklik yok
    korunan = [r for r in sonuc.rapor_satirlari if r.tur == STATUS_KORUNDU_TURU]
    assert [(r.sistem_no, r.sebep) for r in korunan] == [("SSTMN-1", "status korundu (kullanıcı 05.08.2026)")]
    assert sonuc.hatalar == []
    assert _status_tarihcesi(uc_kart, "D-1") == 1        # aktarım status satırı düşmedi
    assert "alan korunan      : 1 (kesim 30.07.2026 sonrası kullanıcı değişikliği)" in ozet_metni(sonuc)


def test_kesim_gunu_de_korunur(uc_kart, tmp_path):
    """Eşik kesim GÜNÜNÜN başı: 30.07 öğlen yapılan değişiklik de korunur."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 7, 30, 12, 0), source="panel")
    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 1
    assert _kart(uc_kart, "D-1").status == "MAHZEN"


def test_kesim_oncesi_kayit_paket_yazar(uc_kart, tmp_path):
    """Kullanıcı 01.07'de MAHZEN'e almış, ekibin kesimi 30.07 → ekip bunu gördü;
    paket kazanır (DERDEST), sayaç 0, tarihçeye aktarım satırı düşer."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 7, 1, 9, 0), source="panel", changed_by="avukat")
    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 0
    assert _kart(uc_kart, "D-1").status == "DERDEST"
    assert _status_tarihcesi(uc_kart, "D-1") == 2
    assert not [r for r in sonuc.rapor_satirlari if r.tur == STATUS_KORUNDU_TURU]


def test_aktarim_imzali_kayit_paket_yazar(uc_kart, tmp_path):
    """Kesim sonrası kayıt AKTARIM imzalıysa (önceki paket yazmış) kullanıcı
    kararı değildir → paket yazar."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 20, 9, 0),
                   source=AKTARIM_IMZASI, changed_by=hukdok_aktarim.DEGISTIREN)
    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 0
    assert _kart(uc_kart, "D-1").status == "DERDEST"


def test_aktarim_imzasi_like_jokerine_kanmaz(uc_kart, tmp_path):
    """`autoescape` kanıtı: 'HUKDOKxTESLIM...' imzası aktarım DEĞİLDİR ('_' ham
    LIKE'ta joker olurdu) → kullanıcı kaydı sayılır, korunur."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 20, 9, 0),
                   source="HUKDOKxTESLIM_sahte.xlsx")
    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 1
    assert _kart(uc_kart, "D-1").status == "MAHZEN"


def test_kesim_tarihi_yoksa_kural_kapali_warning(uc_kart, tmp_path, caplog):
    """Kaynak yok → kural kapalı (paket yazar) + TEK WARNING; özet satırı bunu söyler."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 5, 10, 0))
    with caplog.at_level(logging.WARNING, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor")
    uyarilar = [r for r in caplog.records if "kesim tarihi yok" in r.getMessage()]
    assert len(uyarilar) == 1 and uyarilar[0].levelno == logging.WARNING
    assert sonuc.korunan_alan == 0 and sonuc.kesim_tarihi is None
    assert _kart(uc_kart, "D-1").status == "DERDEST"
    assert "alan korunan      : kural kapalı (veri kesim tarihi yok)" in ozet_metni(sonuc)


def test_paket_ayni_degeri_diyorsa_koruma_sayilmaz(uc_kart, tmp_path):
    """Kullanıcı MAHZEN demiş, paket de `Arşiv` (MAHZEN) diyor → fark yok, sayaç 0."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 5, 10, 0))
    paket = _paket_yaz(tmp_path / "t.xlsx", [_satir("SSTMN-1", "D-1", **{"Durum": "Arşiv"})],
                       basliklar=BASLIKLAR_DURUMLU)
    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor", kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 0 and sonuc.alan_degisikligi == 0
    assert _kart(uc_kart, "D-1").status == "MAHZEN"


def test_ikinci_kosu_yine_korur_tarihce_buyumez(uc_kart, tmp_path):
    """İdempotentlik: ikinci koşu status'a yine dokunmaz, yine raporlar (sessizce
    yutulmaz), `case_history` büyümez."""
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 5, 10, 0))
    paket = _aktif_paket(tmp_path)
    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor", kesim_tarihi=KESIM)
    tarihce = _status_tarihcesi(uc_kart, "D-1")
    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor", kesim_tarihi=KESIM)
    assert (ilk.korunan_alan, ikinci.korunan_alan) == (1, 1)
    assert ikinci.alan_degisikligi == 0
    assert _status_tarihcesi(uc_kart, "D-1") == tarihce == 1
    assert _kart(uc_kart, "D-1").status == "MAHZEN"


def test_kuru_kosu_da_raporlar_yazmaz(uc_kart, tmp_path):
    _durum_gecmisi(uc_kart, "D-1", changed_at=datetime(2026, 8, 5, 10, 0))
    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         dry_run=True, kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 1 and not sonuc.yazildi
    assert _kart(uc_kart, "D-1").status == "MAHZEN" and _kart(uc_kart, "D-1").tibbi_olay is None


def test_teslim_hatti_kesim_tarihini_gecer(db_env, tmp_path, monkeypatch):
    """`_aktarimi_calistir` paketten bulduğu kesim tarihini `aktarimi_kos`a geçer
    (defter kolonu YOK — değer koşuya parametredir)."""
    yol = _paket_dosyasi(tmp_path, "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx",
                         ozet_satirlari=[["Veri kesim tarihi", "30.07.2026"]])
    gorulen = {}

    def sahte_kos(fabrika, **kw):
        gorulen.update(kw)
        return AktarimSonucu(kaynak_imzasi=kw.get("source", ""), kesim_tarihi=kw.get("kesim_tarihi"))

    monkeypatch.setattr(hukdok_aktarim, "aktarimi_kos", sahte_kos)
    db = db_env()
    try:
        sonuc = tk._aktarimi_calistir(db, yol=yol, dosya_adi=yol.name, rapor=tmp_path / "rapor", dry_run=True)
    finally:
        db.close()
    assert gorulen["kesim_tarihi"] == KESIM and sonuc.kesim_tarihi == KESIM
    assert gorulen["dry_run"] is True


def test_sonuc_sozlesmesi_ve_ozet_satiri():
    """`AktarimSonucu` yeni alanlar + `KORUNDU` türü hata sayılmaz."""
    sonuc = AktarimSonucu(kaynak_imzasi="x")
    assert (sonuc.korunan_alan, sonuc.kesim_tarihi) == (0, None)
    sonuc.rapor_satirlari.append(hukdok_aktarim.RaporSatiri(1, "S", "D", STATUS_KORUNDU_TURU, "status korundu"))
    assert sonuc.hatalar == [] and sonuc.cikis_kodu == CIKIS_TAMAM
    assert "alan korunan      : kural kapalı" in ozet_metni(sonuc)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Elle yol imzası — update_case / update_case_tracking
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def fabrika(monkeypatch):
    """In-memory sqlite; `case_manager.SessionLocal` bağlanır (G073 deseni)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _dava(Fabrika, **alanlar) -> int:
    db = Fabrika()
    try:
        case = models.Case(tracking_no="HA.G152.1", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _tarihce(Fabrika, case_id):
    db = Fabrika()
    try:
        return [
            (h.field_name, h.old_value, h.new_value, h.changed_by, h.source)
            for h in db.query(models.CaseHistory).filter(models.CaseHistory.case_id == case_id)
            .order_by(models.CaseHistory.id).all()
        ]
    finally:
        db.close()


def test_update_case_tarihcesi_kullanici_ve_panel_imzali(fabrika):
    """Eski kodda `changed_by`/`source` NULL'dı — kırmızı."""
    cid = _dava(fabrika)
    assert case_manager.update_case(cid, {"status": "MAHZEN"}, changed_by="ilke@lexis") is True
    assert _tarihce(fabrika, cid) == [("status", "DERDEST", "MAHZEN", "ilke@lexis", "panel")]
    assert case_manager.PANEL_SOURCE == "panel"
    assert not case_manager.PANEL_SOURCE.startswith(AKTARIM_SOURCE_PREFIX)


def test_update_case_kullanici_verilmezse_imza_yine_dolu(fabrika):
    """Route bugün kullanıcıyı geçirmiyor (routes/** kapsam dışı): `changed_by`
    yine NULL kalmaz, `source` panel — koruma kuralı ayrımı `source`tan."""
    cid = _dava(fabrika, court="X Mahkemesi")
    assert case_manager.update_case(cid, {"status": "MAHZEN", "court": "Y Mahkemesi"}) is True
    satirlar = _tarihce(fabrika, cid)
    assert [(s[0], s[3], s[4]) for s in satirlar] == [("court", "panel", "panel"), ("status", "panel", "panel")]


def test_update_case_tracking_status_tarihcesi_imzali(fabrika):
    """Takip paneli `status` değiştirirse aynı imza; değişmeyen status satır üretmez."""
    cid = _dava(fabrika)
    assert case_manager.update_case_tracking(cid, {"status": "MAHZEN"}, changed_by="avukat") is True
    assert _tarihce(fabrika, cid) == [("status", "DERDEST", "MAHZEN", "avukat", "panel")]
    assert case_manager.update_case_tracking(cid, {"status": "MAHZEN"}, changed_by="avukat") is True
    assert len(_tarihce(fabrika, cid)) == 1


def test_update_case_tracking_oteki_alanlar_tarihcesiz(fabrika):
    """G073 kilidi korunur: status dışı takip alanı `case_history` yazmaz."""
    cid = _dava(fabrika)
    assert case_manager.update_case_tracking(
        cid, {"arsiv_tarihi": date(2026, 1, 2), "arabuluculuk_no": "ARB-1"}, changed_by="avukat",
    ) is True
    assert _tarihce(fabrika, cid) == []


def test_uctan_uca_panel_degisikligi_paketle_ezilmez(uc_kart, tmp_path, monkeypatch):
    """Panel (update_case) bugün MAHZEN'e alır → dünkü kesimli paket `Aktif` der
    → korunur. Tarihçe `func.now()` ile düşer: gerçek zaman damgası eşiği geçer."""
    monkeypatch.setattr(case_manager, "SessionLocal", uc_kart)
    cid = _kart_id(uc_kart, "D-1")
    assert case_manager.update_case(cid, {"status": "MAHZEN"}, changed_by="ilke@lexis") is True

    sonuc = aktarimi_kos(uc_kart, girdi=_aktif_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=date.today() - timedelta(days=1))
    assert sonuc.korunan_alan == 1
    assert _kart(uc_kart, "D-1").status == "MAHZEN"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Koruma HER alana genellendi (12.09.2026) — esas_no / court / boşaltma / boş doldurma
# ═══════════════════════════════════════════════════════════════════════════
# Kullanıcı kararı 12.09: prod'da 30.07'den sonra elle yapılan 47 düzeltme
# (status 20, esas_no 18, court 10) DOĞRU kabul edilir; paket bu alanları
# üzerine yazmaz, yalnız bizde boş olanı doldurur. Eski kural yalnız `status`u
# koruyordu — 28 esas/mahkeme düzeltmesi geri alınırdı (kırmızı).

BASLIKLAR_ESASLI = BASLIKLAR + ["Durum", "Esas", "Yerel Mahkeme"]


def _alan_gecmisi(fabrika, klasor, alan, yeni, *, changed_at, source="panel", changed_by="avukat"):
    """Kartın `alan`ını `yeni` yapar ve tarihçeye kullanıcı imzalı satır düşer."""
    db = fabrika()
    try:
        case = db.query(models.Case).filter(models.Case.klasor_no_2 == klasor).one()
        db.add(models.CaseHistory(
            case_id=case.id, field_name=alan, old_value=getattr(case, alan), new_value=yeni,
            changed_at=changed_at, changed_by=changed_by, source=source,
        ))
        setattr(case, alan, yeni)
        db.commit()
    finally:
        db.close()


def _esasli_paket(tmp_path, **ek):
    return _paket_yaz(tmp_path / "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Durum": "Aktif", "Esas": "2016/1191",
                                    "Yerel Mahkeme": "Eskişehir Tüketici Mahkemesi",
                                    "Tıbbi Olay": "Enfeksiyon", **ek}),
        _satir("SSTMN-2", "D-2", **{"Durum": "Aktif", "Esas": "2024/571",
                                    "Yerel Mahkeme": "Adana 4. Tüketici Mahkemesi"}),
    ], basliklar=BASLIKLAR_ESASLI)


def test_esas_ve_mahkeme_kullanici_duzeltmesi_korunur(uc_kart, tmp_path):
    """Prod örneği (kart 1511/1883): avukat 19.08'de esası 2026/1'e, 11.08'de
    mahkemeyi değiştirmiş; paket eski defter değerini taşıyor → ikisi de KORUNUR,
    öteki alan (Tıbbi Olay) yazılır, rapor iki KORUNDU satırı, çıkış kodu 0.
    Korunan mahkeme esas tarihçesine de sızmaz. Eski kodda ikisi de geri dönerdi."""
    _alan_gecmisi(uc_kart, "D-1", "esas_no", "2026/1", changed_at=datetime(2026, 8, 19, 11, 22))
    _alan_gecmisi(uc_kart, "D-1", "court", "İstanbul 26. Asliye Ticaret Mahkemesi",
                  changed_at=datetime(2026, 8, 11, 9, 45), source=None, changed_by=None)

    sonuc = aktarimi_kos(uc_kart, girdi=_esasli_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.yazildi and sonuc.hatalar == []
    assert sonuc.korunan_alan == 2
    kart = _kart(uc_kart, "D-1")
    assert kart.esas_no == "2026/1"
    assert kart.court == "İstanbul 26. Asliye Ticaret Mahkemesi"
    assert kart.tibbi_olay == "Enfeksiyon"                       # koruma alan bazlı, kart bazlı değil
    kart2 = _kart(uc_kart, "D-2")
    assert (kart2.esas_no, kart2.court) == ("2024/571", "Adana 4. Tüketici Mahkemesi")   # kaydı yok → paket yazar
    korunan = sorted((r.sistem_no, r.sebep) for r in sonuc.rapor_satirlari if r.tur == STATUS_KORUNDU_TURU)
    assert korunan == [("SSTMN-1", "court korundu (kullanıcı 11.08.2026)"),
                       ("SSTMN-1", "esas_no korundu (kullanıcı 19.08.2026)")]
    assert "alan korunan      : 2 (kesim 30.07.2026 sonrası kullanıcı değişikliği)" in ozet_metni(sonuc)
    db = uc_kart()
    try:
        guncel = (db.query(models.CaseEsasNumber)
                  .filter(models.CaseEsasNumber.case_id == kart.id, models.CaseEsasNumber.is_current.is_(True))
                  .all())
        assert all(e.court != "Eskişehir Tüketici Mahkemesi" for e in guncel)   # paket mahkemesi sızmadı
    finally:
        db.close()


def test_kesim_oncesi_esas_duzeltmesi_paket_yazar(uc_kart, tmp_path):
    """Esas 01.07'de değişmiş, kesim 30.07 → ekip gördü, paket kazanır; sayaç 0."""
    _alan_gecmisi(uc_kart, "D-1", "esas_no", "2026/1", changed_at=datetime(2026, 7, 1, 9, 0))
    sonuc = aktarimi_kos(uc_kart, girdi=_esasli_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 0
    assert _kart(uc_kart, "D-1").esas_no == "2016/1191"


def test_bizde_bos_alan_kullanici_kaydina_ragmen_dolar(uc_kart, tmp_path):
    """"Boş bilgi varsa doldurulsun": kullanıcı kesimden sonra mahkemeyi BOŞALTMIŞ
    (tarihçe var, alan boş) → paket doldurur, koruma sayılmaz."""
    _alan_gecmisi(uc_kart, "D-1", "court", None, changed_at=datetime(2026, 8, 11, 9, 45))
    assert _kart(uc_kart, "D-1").court is None
    sonuc = aktarimi_kos(uc_kart, girdi=_esasli_paket(tmp_path), rapor_dizini=tmp_path / "rapor",
                         kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 0
    assert _kart(uc_kart, "D-1").court == "Eskişehir Tüketici Mahkemesi"


def test_bosaltma_talimati_kullanici_dolusunu_bosaltamaz(uc_kart, tmp_path):
    """`Düzeltme_Logu` `(boş)` diyor ama kullanıcı kesimden sonra Tıbbi Olay'ı
    doldurmuş → boşaltılmaz, KORUNDU raporu; kesim öncesi dolduysa boşaltılır."""
    from tests.test_g112_duzeltme_logu import _log
    from tests.test_g112_duzeltme_logu import _paket_yaz as _loglu_paket

    _alan_gecmisi(uc_kart, "D-1", "tibbi_olay", "Kanama", changed_at=datetime(2026, 8, 5, 10, 0))
    _alan_gecmisi(uc_kart, "D-2", "tibbi_olay", "Kanama", changed_at=datetime(2026, 7, 1, 10, 0))
    paket = _loglu_paket(tmp_path / "t.xlsx", [_satir("SSTMN-1", "D-1"), _satir("SSTMN-2", "D-2")], log=[
        _log("SSTMN-1", "Tıbbi Olay", "(boş)", gerekce="yanlış föy"),
        _log("SSTMN-2", "Tıbbi Olay", "(boş)", gerekce="yanlış föy"),
    ])
    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor", kesim_tarihi=KESIM)
    assert sonuc.korunan_alan == 1
    assert _kart(uc_kart, "D-1").tibbi_olay == "Kanama"          # kullanıcı dolusu korundu
    assert _kart(uc_kart, "D-2").tibbi_olay is None              # kesim öncesi → talimat uygulandı
    assert [r.sebep for r in sonuc.rapor_satirlari if r.tur == STATUS_KORUNDU_TURU] == [
        "tibbi_olay korundu (kullanıcı 05.08.2026)"]
