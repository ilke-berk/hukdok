"""G153 — Dosya No kökü → müvekkil kimliği: eşleştirme adımı, kök/müvekkil
çelişkisi (H-6589), föy ↔ müvekkil bağı (`case_foys.case_party_id`) ve
"müvekkil değişti" raporu.

Ekip (06.09 §2): müvekkil kimliği `DosyaNo`nun ilk noktaya kadarki kökünde
kodlu (1 Axa · 2 Quick · 3 Ak · … · 13 hizmetsiz · ≥500 hekim/kurum). Eşleştirici
belirsiz eşleşmede kökü esas/tür'den SONRA, müvekkil adından ÖNCE dener; kök ile
`Müvekkil` hücresi çelişirse (kök 3 = Ak, hücre Axa) satır YAZILMAZ. Föy artık
`Müvekkil` hücresinin ilk parçasına uyan CLIENT satırına bağlanır; bağ başka
tarafa geçerse eski satır silinmez, rapor `MUVEKKIL_DEGISTI` ile "elle düzeltme
listesi"ne düşer.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
paketler openpyxl ile SENTETİK üretilir (test_g064 yardımcıları). Gerçek
paketle ölçüm yalnız görev raporundadır.
"""
import logging

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import foy_map
from party_check import normalize_party_key
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    CIKIS_SATIR_HATASI,
    CIKIS_TAMAM,
    DOSYANO_KOK_MUVEKKILI,
    MUVEKKIL_DEGISTI_TURU,
    HamSatir,
    aktarimi_kos,
    ozet_metni,
)
from tests.test_g064_aktarim_cekirdek import BASLIKLAR, _kart, _paket_yaz, _satir

BASLIKLAR_G153 = BASLIKLAR + ["Ana Tür", "Esas", "Müvekkil"]


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


@pytest.fixture()
def db_env():
    """In-memory sqlite + `case_foys` migrasyon index'leri + FK + çalışan
    SAVEPOINT (pysqlite BEGIN reçetesi — gerekçe test_g064'teki ikizinde)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_connection, _record):
        dbapi_connection.isolation_level = None      # pysqlite BEGIN yaymasın
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


def _muvekkil(db, case, ad, *, client_id=None):
    taraf = models.CaseParty(case_id=case.id, name=ad, role="Müvekkil",
                             party_type="CLIENT", client_id=client_id)
    db.add(taraf)
    db.flush()
    return taraf


def _cozum_loglari(caplog):
    return [r.getMessage() for r in caplog.records
            if "ikinci anahtarla çözüldü" in r.getMessage()]


def _satir_ham(**degerler):
    return HamSatir(satir_no=2, degerler=degerler)


# ─── Birim: kök çıkarımı ve harita ───────────────────────────────────────────

@pytest.mark.parametrize("ham, beklenen", [
    ("3.1400.00", "3"),                      # tek haneli sigorta kökü
    ("1706.001.00", "1706"),                 # dört haneli hekim kökü — sabit hane YOK
    ("8000.12.00", "8000"),                  # Nippon
    (" 2 . 054.00", "2"),                    # boşluk toleransı
    ("624.001.00;3.137.00", "624"),          # çok değerli hücre → İLK numaranın kökü
    ("03.5.00", "3"),                        # baştaki sıfır düşer
    ("S3.AXA.2915", "S3"),                   # rakam dışı kök olduğu gibi (haritada yok)
    (None, None),
    ("   ", None),
])
def test_dosya_no_koku_bes_bicim(ham, beklenen):
    assert hukdok_aktarim._dosya_no_koku(ham) == beklenen


@pytest.mark.parametrize("ham, beklenen", [
    ("3.1400.00", ("3", "Ak Sigorta A.Ş.")),
    ("2.054.00", ("2", "Quick Sigorta A.Ş.")),
    ("9.541.00", ("9", "Anadolu Anonim Türk Sigorta Şirketi")),
    ("8000.12.00", ("8000", "Türk Nippon Sigorta A.Ş.")),
    ("13.7.00", None),                       # hizmet verilmemiş — kural atlanır
    ("1519.001.00", None),                   # ≥500 hekim/kurum — ad gerekir
    ("4.1.00", None),                        # ekibin listesinde olmayan kök
    ("", None),
])
def test_kok_muvekkili_yalniz_sigorta_kokleri(ham, beklenen):
    assert hukdok_aktarim._kok_muvekkili(ham) == beklenen


def test_kok_haritasi_ekibin_listesi():
    """06.09 §2 listesi birebir; her kökün adı bir SİGORTA adı (marka çıkarılabilir)."""
    assert set(DOSYANO_KOK_MUVEKKILI) == {"1", "2", "3", "5", "6", "7", "8", "9", "8000"}
    assert "13" not in DOSYANO_KOK_MUVEKKILI
    for kok, ad in DOSYANO_KOK_MUVEKKILI.items():
        marka = hukdok_aktarim._sigorta_markasi(normalize_party_key(ad))
        assert marka, (kok, ad)


@pytest.mark.parametrize("adlar, kok, beklenen", [
    (["Quıck Sigorta A.ş"], "2", True),               # noktasız ı + eksik nokta (578 satırlık yazım)
    (["Quick Sigorta A.Ş."], "2", True),
    (["S.s. Koru Sigorta Kooperatifi"], "5", True),   # kooperatif yazımı
    (["Türk Nippon Sigorta Aş"], "8000", True),
    (["Axa Hayat Sigorta A.ş."], "1", True),          # aynı marka, başka şirket eki
    (["Axa Sigorta A.ş.", "Axa Hayat Sigorta A.ş."], "1", True),
    (["Anadolu Anonim Türk Sigorta Şirketi"], "9", True),
    (["Ergo Sigorta A.ş."], "8", False),              # başka sigorta
    (["Ahmet Yılmaz"], "3", False),                   # sigorta değil
    (["Ak Sigorta A.ş."], "1", False),                # Ak ≠ Axa
    (["Mürüvvet Işık", "Axa Sigorta A.ş."], "1", False),   # ikiz HEKİM kartı: sigorta ortak müvekkil
    (["Ak Sigorta A.ş.", "Axa Sigorta A.ş."], "1", False),  # iki sigortalı kart (S1.AK…0262) Axa'nın değil
    ([], "1", False),                                 # CLIENT yok
])
def test_kokun_karti_mi_yalniz_sigorta_muvekkilli_kart(adlar, kok, beklenen):
    assert hukdok_aktarim._kokun_karti_mi({normalize_party_key(a) for a in adlar}, kok) is beklenen


@pytest.mark.parametrize("dosya_no, muvekkil, celiski", [
    ("3.1400.00", "Axa Sigorta A.Ş.", True),          # H-6589 deseni: kök Ak, hücre Axa
    ("2.054.00", "Corpus Sigorta Anonim Şirketi", True),
    ("9.541.00", "Axa Sigorta A.ş.; Ahmet Yılmaz", True),   # ilk parça sayılır
    ("3.1400.00", "Ak Sigorta A.Ş.", False),          # uyumlu
    ("2.054.00", "Quıck Sigorta A.ş", False),         # aynı marka, başka yazım
    ("1.5.00", "Axa Hayat Sigorta A.ş.", False),
    ("9.541.00", "Ahmet Yılmaz", False),              # hekim adı — çelişki DEĞİL (15 föy sınıfı)
    ("9.541.00", None, False),                        # boş hücre
    ("1519.001.00", "Axa Sigorta A.Ş.", False),       # kök ≥500: kural yok
    ("13.7.00", "Axa Sigorta A.Ş.", False),           # hizmetsiz kök: kural yok
])
def test_kok_muvekkil_celiskisi(dosya_no, muvekkil, celiski):
    sebep = hukdok_aktarim._kok_muvekkil_celiskisi(_satir_ham(dosya_no=dosya_no, muvekkil=muvekkil))
    if celiski:
        assert sebep is not None and sebep.startswith("kök/müvekkil çelişkisi")
        assert dosya_no.split(".")[0] in sebep
    else:
        assert sebep is None


# ─── sqlite: eleme sırası ────────────────────────────────────────────────────

def _ikiz(db_env, *, klasor, a_muvekkil, b_muvekkil, esas="2023/449", tur="Hukuk",
          a_tur=None, b_tur=None):
    """Aynı Dosya No, aynı esas, (varsayılan) aynı tür — müvekkilleri farklı iki kart."""
    db = db_env()
    try:
        a = _kart(db, "HA.G153.A", klasor, file_type=a_tur or tur, esas_no=esas)
        b = _kart(db, "HA.G153.B", klasor, file_type=b_tur or tur, esas_no=esas)
        _muvekkil(db, a, a_muvekkil)
        _muvekkil(db, b, b_muvekkil)
        db.commit()
        return a.id, b.id
    finally:
        db.close()


def _foy_karti(db_env, sistem_no):
    db = db_env()
    try:
        foy = foy_map.get_foy(db, sistem_no)
        return None if foy is None else foy.case_id
    finally:
        db.close()


def test_kok_adimi_tek_adaya_iner_id1012_deseni(db_env, tmp_path, caplog):
    """Kabul 2: id-1012 (Dosya No `2.054.00`, kök 2 = Quick) iki kartla eşleşiyor,
    esas/tür aynı; CLIENT'ı Quick olan kart tek → kök adımı seçer. `Müvekkil`
    hücresi hiçbir karta uymuyor (hekim adı) — G118 adımı tek başına çözemezdi."""
    a_id, _b_id = _ikiz(db_env, klasor="2.054.00",
                        a_muvekkil="Quıck Sigorta A.ş", b_muvekkil="Ak Sigorta A.ş.")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-1012", "2.054.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                         "Müvekkil": "Dr. Mehmet Kaya"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert _foy_karti(db_env, "id-1012") == a_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+kök," in m and "kök=2=" in m for m in loglar)


def test_kok_adimi_muvekkil_adindan_once(db_env, tmp_path, caplog):
    """Kabul 1 (sıra): kök Quick'i, `Müvekkil` hücresi öteki kartın müvekkilini
    gösteriyor → kök kazanır (deterministik kimlik), ad adımına gelinmez."""
    a_id, _b_id = _ikiz(db_env, klasor="2.077.00",
                        a_muvekkil="Quick Sigorta A.Ş.", b_muvekkil="Ahmet Yılmaz")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-SIRA", "2.077.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                        "Müvekkil": "Ahmet Yılmaz"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    assert _foy_karti(db_env, "F-SIRA") == a_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+kök," in m for m in loglar)


def test_gercek_ikiz_deseni_sigorta_karti_ve_hekim_karti(db_env, tmp_path, caplog):
    """04.09 paketinin gerçek ikizi (id-7356): `S3.AXA…` {Axa} ile `S3.M_ISIK…`
    {Mürüvvet Işık, Axa} aynı esas/tür/Dosya No. Kök 1 satırı sigortanın
    kartına (kök adımı); hekim köklü (1361 ≥ 500) satır ad adımıyla hekimin
    kartına — her ikisi de föy↔müvekkil bağını kendi CLIENT satırına kurar."""
    db = db_env()
    try:
        axa = _kart(db, "S3.AXA........2915.IDARE.00000", "1.21184.00", file_type="İdare", esas_no="2019/963")
        hekim = _kart(db, "S3.M_ISIK.....0001.IDARE.00000", "1361.001.00;1.21184.00",
                      file_type="İdare", esas_no="2019/963")
        axa_taraf = _muvekkil(db, axa, "Axa Sigorta A.ş.")
        hekim_taraf = _muvekkil(db, hekim, "Mürüvvet Işık")
        _muvekkil(db, hekim, "Axa Sigorta A.ş.")
        db.commit()
        axa_id, hekim_id, axa_taraf_id, hekim_taraf_id = axa.id, hekim.id, axa_taraf.id, hekim_taraf.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-7356", "1.21184.00", **{"Ana Tür": "İDARE", "Esas": "2019/963",
                                           "Müvekkil": "Axa Sigorta A.Ş."}),
        _satir("id-7357", "1361.001.00;1.21184.00", **{"Ana Tür": "İDARE", "Esas": "2019/963",
                                                       "Müvekkil": "Mürüvvet Işık"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert sonuc.foy_muvekkil_bagli == 2 and sonuc.taraf_eklenen == 0
    assert _foy(db_env, "id-7356") == (axa_id, axa_taraf_id)
    assert _foy(db_env, "id-7357") == (hekim_id, hekim_taraf_id)
    loglar = _cozum_loglari(caplog)
    assert any("id-7356" in m and "kriter=esas+tür+kök," in m for m in loglar)
    assert any("id-7357" in m and "kriter=esas+tür+müvekkil," in m for m in loglar)
    assert not any("id-7357" in m and "kök" in m for m in loglar)


def test_tur_adimi_kokten_once(db_env, tmp_path, caplog):
    """Kabul 1 (sıra): tür tek adaya iniyor ve kökle ÇELİŞİYOR → mevcut 3. adım
    kazanır; kök adımına gelinmez (esas/tür'den SONRA)."""
    db = db_env()
    try:
        hukuk = _kart(db, "HA.G153.H", "2.090.00", file_type="Hukuk")
        arabu = _kart(db, "HA.G153.R", "2.090.00", file_type="Arabuluculuk")
        _muvekkil(db, hukuk, "Ak Sigorta A.Ş.")
        _muvekkil(db, arabu, "Quick Sigorta A.Ş.")
        db.commit()
        hukuk_id = hukuk.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-TUR", "2.090.00", **{"Ana Tür": "HUKUK"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    assert _foy_karti(db_env, "F-TUR") == hukuk_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=tür," in m for m in loglar)


def test_kok_ayirmayinca_muvekkil_adi_devam_eder(db_env, tmp_path, caplog):
    """İki kart da kökün sigortasını taşıyor (gerçek iki-müvekkilli ikiz) → kök
    tek adaya inmez, G118 ad adımı devreye girer ve seçer."""
    db = db_env()
    try:
        a = _kart(db, "HA.G153.A", "1.21184.00", file_type="Hukuk", esas_no="2023/1")
        b = _kart(db, "HA.G153.B", "1.21184.00", file_type="Hukuk", esas_no="2023/1")
        for kart in (a, b):
            _muvekkil(db, kart, "Axa Sigorta A.Ş.")
        _muvekkil(db, a, "Ahmet Yılmaz")
        _muvekkil(db, b, "Zeynep Demir")
        db.commit()
        b_id = b.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-AD", "1.21184.00", **{"Ana Tür": "HUKUK", "Esas": "2023/1",
                                        "Müvekkil": "Demir Zeynep"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    assert _foy_karti(db_env, "F-AD") == b_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+müvekkil," in m for m in loglar)


def test_hekim_koku_atlanir_sebep_metninde_kok_yok(db_env, tmp_path):
    """Kök ≥500 (hekim/kurum): adım atlanır; ad da ayırmıyorsa satır eski
    metinle rapora düşer ("kök" sözcüğü geçmez — adım hiç denenmedi)."""
    _ikiz(db_env, klasor="1519.001.00",
          a_muvekkil="Quick Sigorta A.Ş.", b_muvekkil="Ak Sigorta A.Ş.")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-HEKIM", "1519.001.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI and len(sonuc.hatalar) == 1
    assert sonuc.hatalar[0].sebep.endswith("— esas/tür de ayırmadı")
    assert "kök" not in sonuc.hatalar[0].sebep
    assert _foy_karti(db_env, "F-HEKIM") is None


def test_kok_de_ayirmayinca_sebep_metni_koku_soyler(db_env, tmp_path):
    """Sigorta köklü satırda hiçbir kart kökün sigortasını taşımıyor ve ad da
    yok → None; sebep metni kök adımının da denendiğini söyler."""
    _ikiz(db_env, klasor="3.649.00", a_muvekkil="Ahmet Yılmaz", b_muvekkil="Zeynep Demir")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-KOK", "3.649.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert len(sonuc.hatalar) == 1
    assert sonuc.hatalar[0].sebep.endswith("— esas/tür/kök de ayırmadı")


# ─── sqlite: kök/müvekkil çelişkisi (H-6589) ─────────────────────────────────

def test_h6589_deseni_yazilmaz_ve_rapora_duser(db_env, tmp_path):
    """Kabul 2: kök 3 = Ak, hücre Axa → satır hiçbir karta yazılmaz (kart tek
    ve eşleşiyor olsa bile), rapor HATA "kök/müvekkil çelişkisi", sayaç 1."""
    db = db_env()
    try:
        kart = _kart(db, "HA.G153.C", "3.1400.00", file_type="Hukuk")
        _muvekkil(db, kart, "Ak Sigorta A.Ş.")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-6589", "3.1400.00", **{"Ana Tür": "HUKUK", "Müvekkil": "Axa Sigorta A.Ş.",
                                         "Hasar No": "HSR-6589"}),
        _satir("H-OK", "3.1400.00", **{"Ana Tür": "HUKUK", "Müvekkil": "Ak Sigorta A.Ş."}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    assert sonuc.kok_muvekkil_celiskisi == 1 and len(sonuc.hatalar) == 1
    hata = sonuc.hatalar[0]
    assert hata.sistem_no == "H-6589" and hata.tur == "HATA"
    assert hata.sebep.startswith("kök/müvekkil çelişkisi") and "Ak Sigorta" in hata.sebep
    assert "Axa Sigorta" in hata.sebep
    assert _foy_karti(db_env, "H-6589") is None            # yazılmadı
    assert _foy_karti(db_env, "H-OK") is not None          # kardeşi yazıldı
    db = db_env()
    try:
        # çelişen satırın Axa'sı karta taraf olarak da EKLENMEDİ
        assert db.query(models.CaseParty).filter(
            models.CaseParty.name.like("%Axa%")).count() == 0
    finally:
        db.close()
    assert "1 kök/müvekkil çelişkisi (yazılmadı)" in ozet_metni(sonuc)


def test_celiskili_satir_mevcut_foyu_de_guncellemez(db_env, tmp_path):
    """Föy zaten bizde olsa bile çelişkili satır ona DOKUNMAZ (hasar no aynı kalır)."""
    db = db_env()
    try:
        kart = _kart(db, "HA.G153.C", "3.1400.00", file_type="Hukuk")
        _muvekkil(db, kart, "Ak Sigorta A.Ş.")
        foy_map.upsert_foy(db, kart, sistem_no="H-6589", hasar_no="HSR-ESKI")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-6589", "3.1400.00", **{"Müvekkil": "Axa Sigorta A.Ş.", "Hasar No": "HSR-YENI"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.kok_muvekkil_celiskisi == 1 and sonuc.foy_guncellenen == 0
    db = db_env()
    try:
        assert foy_map.get_foy(db, "H-6589").hasar_no == "HSR-ESKI"
    finally:
        db.close()


def test_on_gecis_celiskili_satiri_uzlasiya_katmaz(db_env):
    """`_kart_id_tahmini` (ön geçiş ikizi) çelişkili satırda None döner —
    yazılmayacak satır kardeş föy uzlaşısını şekillendirmemeli."""
    db = db_env()
    try:
        kart = _kart(db, "HA.G153.C", "3.1400.00", file_type="Hukuk")
        db.commit()
        harita = {"3.1400.00": [kart.id]}
        celiskili = _satir_ham(sistem_no="H-6589", dosya_no="3.1400.00", muvekkil="Axa Sigorta A.Ş.")
        uyumlu = _satir_ham(sistem_no="H-OK", dosya_no="3.1400.00", muvekkil="Ak Sigorta A.Ş.")
        assert hukdok_aktarim._kart_id_tahmini(db, celiskili, {"H-6589": kart.id}, harita, "H-6589") is None
        assert hukdok_aktarim._kart_id_tahmini(db, uyumlu, {}, harita, "H-OK") == kart.id
    finally:
        db.close()


# ─── sqlite: föy ↔ müvekkil bağı ─────────────────────────────────────────────

def _tek_kart(db_env, *muvekkiller, klasor="9.541.00"):
    db = db_env()
    try:
        kart = _kart(db, "HA.G153.T", klasor, file_type="Hukuk")
        taraflar = [_muvekkil(db, kart, ad) for ad in muvekkiller]
        db.commit()
        return kart.id, [t.id for t in taraflar]
    finally:
        db.close()


def _foy(db_env, sistem_no):
    db = db_env()
    try:
        foy = foy_map.get_foy(db, sistem_no)
        return (foy.case_id, foy.case_party_id) if foy is not None else None
    finally:
        db.close()


def test_foy_muvekkile_baglanir_ilk_parca_anahtar_esitligi(db_env, tmp_path):
    """Kabul 3: hücrenin İLK parçası (kelime sırası/şirket eki farklı) kartın
    CLIENT satırına düşer → `case_party_id` o satır; sayaç `foy_muvekkil_bagli`."""
    kart_id, (ahmet_id, _anadolu_id) = _tek_kart(
        db_env, "Ahmet Yılmaz", "Anadolu Anonim Türk Sigorta Şirketi")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-BAG", "9.541.00", **{"Müvekkil": "Yılmaz Ahmet; Anadolu Sigorta"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.foy_muvekkil_bagli == 1 and sonuc.foy_muvekkil_degisen == 0
    assert _foy(db_env, "F-BAG") == (kart_id, ahmet_id)
    assert "1 bağlandı" in ozet_metni(sonuc)
    db = db_env()
    try:
        kayit = db.query(models.CaseHistory).filter(
            models.CaseHistory.field_name == "case_foys.case_party_id").one()
        assert (kayit.old_value, kayit.new_value) == (None, "Ahmet Yılmaz")
        assert kayit.source == sonuc.kaynak_imzasi
    finally:
        db.close()


def test_kartta_olmayan_muvekkil_once_eklenir_sonra_baglanir(db_env, tmp_path):
    """Hücredeki ad kartta yoksa `_taraflari_yaz` ekler (yalnız-ekleme), bağ o
    yeni CLIENT satırına kurulur — sıra taraf yazımından SONRA."""
    kart_id, _ = _tek_kart(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-YENI", "9.541.00", **{"Müvekkil": "Zeynep Demir"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.taraf_eklenen == 1 and sonuc.foy_muvekkil_bagli == 1
    db = db_env()
    try:
        taraf = db.query(models.CaseParty).filter(models.CaseParty.name == "Zeynep Demir").one()
        assert taraf.party_type == "CLIENT" and taraf.case_id == kart_id
        assert foy_map.get_foy(db, "F-YENI").case_party_id == taraf.id
    finally:
        db.close()


def test_muvekkil_hucresi_bossa_bag_null(db_env, tmp_path):
    """Eşleşme yoksa NULL (bugünkü hâl) — sayaç 0."""
    kart_id, _ = _tek_kart(db_env, "Ahmet Yılmaz")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-BOS", "9.541.00"),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.foy_muvekkil_bagli == 0
    assert _foy(db_env, "F-BOS") == (kart_id, None)


def test_muvekkil_degisti_raporu_eski_taraf_satiri_korunur(db_env, tmp_path):
    """Kabul 3: ilk pakette Ahmet'e bağlı föy, ikinci pakette hücre Zeynep →
    bağ güncellenir, satır raporu `MUVEKKIL_DEGISTI` "eski → yeni", eski CLIENT
    satırı SİLİNMEZ ve rolü değişmez; HATA değil (çıkış 0)."""
    kart_id, (ahmet_id,) = _tek_kart(db_env, "Ahmet Yılmaz")
    ilk_paket = _paket_yaz(tmp_path / "ilk.xlsx", [
        _satir("F-DEG", "9.541.00", **{"Müvekkil": "Ahmet Yılmaz"}),
    ], basliklar=BASLIKLAR_G153)
    ilk = aktarimi_kos(db_env, girdi=ilk_paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.foy_muvekkil_bagli == 1 and _foy(db_env, "F-DEG") == (kart_id, ahmet_id)

    ikinci_paket = _paket_yaz(tmp_path / "ikinci.xlsx", [
        _satir("F-DEG", "9.541.00", **{"Müvekkil": "Zeynep Demir"}),
    ], basliklar=BASLIKLAR_G153)
    ikinci = aktarimi_kos(db_env, girdi=ikinci_paket, rapor_dizini=tmp_path / "rapor")

    assert ikinci.cikis_kodu == CIKIS_TAMAM and not ikinci.hatalar
    assert ikinci.foy_muvekkil_degisen == 1 and ikinci.foy_muvekkil_bagli == 0
    rapor = [r for r in ikinci.rapor_satirlari if r.tur == MUVEKKIL_DEGISTI_TURU]
    assert len(rapor) == 1 and rapor[0].sistem_no == "F-DEG"
    assert rapor[0].sebep == "müvekkil değişti: Ahmet Yılmaz → Zeynep Demir"
    assert "1 müvekkil değişti (rapor)" in ozet_metni(ikinci)
    db = db_env()
    try:
        eski = db.get(models.CaseParty, ahmet_id)
        assert eski is not None and eski.party_type == "CLIENT" and eski.role == "Müvekkil"
        yeni = db.query(models.CaseParty).filter(models.CaseParty.name == "Zeynep Demir").one()
        assert foy_map.get_foy(db, "F-DEG").case_party_id == yeni.id
        assert db.query(models.CaseParty).filter(models.CaseParty.case_id == kart_id).count() == 2
        kayit = db.query(models.CaseHistory).filter(
            models.CaseHistory.field_name == "case_foys.case_party_id",
            models.CaseHistory.old_value == "Ahmet Yılmaz").one()
        assert kayit.new_value == "Zeynep Demir"
    finally:
        db.close()


def test_ikinci_kosu_sifir(db_env, tmp_path):
    """Kabul: aynı girdiyle ikinci koşu — bağ sayaçları 0, tarihçe ve taraf
    tablosu büyümez, kök adımıyla seçilen kart sabit."""
    a_id, _b_id = _ikiz(db_env, klasor="2.054.00",
                        a_muvekkil="Quıck Sigorta A.ş", b_muvekkil="Ak Sigorta A.ş.")
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-1012", "2.054.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                         "Müvekkil": "Quick Sigorta A.Ş.", "Hasar No": "H-1"}),
        _satir("id-1013", "2.054.00", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                         "Müvekkil": "Dr. Mehmet Kaya", "Hasar No": "H-2"}),
    ], basliklar=BASLIKLAR_G153)

    ilk = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM and (ilk.foy_yeni, ilk.foy_guncellenen) == (2, 0)
    assert ilk.foy_muvekkil_bagli == 2 and ilk.taraf_eklenen == 1     # Mehmet Kaya eklendi

    def _fotograf():
        db = db_env()
        try:
            return (
                {f.sistem_no: (f.case_id, f.case_party_id) for f in db.query(models.CaseFoy)},
                db.query(models.CaseParty).count(),
                db.query(models.CaseHistory).count(),
            )
        finally:
            db.close()

    sonrasi = _fotograf()
    assert {s: c for s, (c, _p) in sonrasi[0].items()} == {"id-1012": a_id, "id-1013": a_id}
    assert all(p is not None for _c, p in sonrasi[0].values())

    ikinci = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert (ikinci.foy_yeni, ikinci.foy_guncellenen) == (0, 2)
    assert (ikinci.foy_muvekkil_bagli, ikinci.foy_muvekkil_degisen, ikinci.taraf_eklenen) == (0, 0, 0)
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0
    assert _fotograf() == sonrasi
