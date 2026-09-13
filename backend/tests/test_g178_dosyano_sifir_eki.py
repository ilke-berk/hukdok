"""G178 — DosyaNo `.00` eki, klasör listesinin ilk parçası anahtarı, eski unvan
istisnası (ekibin 12.09 cevabı §1/§3/§8).

Ekip: MİCRO DosyaNo'su sondaki ".00" ekiyle gelir ("2.500.00"), eski kartlarımız
eksiz ("2.500"); ek normalize edilmediği için 37 föy "kartsız" sayılıp 05.09'da
ikinci kart açıldı. Belirsiz eşleşmede ekibin kuralı: klasör listesi föyün
DosyaNo'suyla BAŞLAYAN kart (18 satırın 8 belirsizini çözdü). Corpus (kök 2,
Quick'in eski unvanı) ve Ergo (kök 8, HDI devri) müvekkil hücresi BİLEREK
eski ad — kök/müvekkil çelişkisi DEĞİL.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek paket repoya girmez; paketler
openpyxl ile SENTETİK üretilir (test_g064 yardımcıları).
"""
import logging

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from party_check import normalize_party_key
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import CIKIS_SATIR_HATASI, CIKIS_TAMAM, aktarimi_kos
from tests.test_g064_aktarim_cekirdek import _kart, _paket_yaz, _satir
from tests.test_g153_dosyano_koku import (
    BASLIKLAR_G153,
    _cozum_loglari,
    _foy_karti,
    _muvekkil,
    _satir_ham,
)


@pytest.fixture()
def db_env():
    """test_g153'teki fixture'ın ikizi (import edilince ruff F811 — parametre adı
    gölgeler): in-memory sqlite + `case_foys` migrasyon index'leri + FK + SAVEPOINT."""
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
        for op in _MIGRATIONS:
            if op[0] == "index" and op[1] == "case_foys":
                for sql in op[2]:
                    conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


# ─── Birim: eşleşme anahtarı ─────────────────────────────────────────────────

@pytest.mark.parametrize("ham, beklenen", [
    ("2.500.00", "2.500"),            # ekibin çekirdek vakası: ek atılır
    ("2.500", "2.500"),               # eksiz kart değeri olduğu gibi
    ("6.5110.00", "6.5110"),          # H-15496 (kart 4356 ↔ 13565)
    ("3.1400.00", "3.1400"),
    ("1706.001.00", "1706.001"),
    ("2.531.01", "2.531.01"),         # .01 AYRI dosya — dokunulmaz
    ("1.00", "1.00"),                 # kalan parça noktasız → dokunulmaz
    (" 9.070.00 ", "9.070"),          # boşluk toleransı korunur
    ("a-1", "A-1"),                   # harf duyarsızlık korunur
    ("", ""),
    (None, ""),
])
def test_eslesme_anahtari_sondaki_sifir_ekini_atar(ham, beklenen):
    assert hukdok_aktarim._eslesme_anahtari(ham) == beklenen


def test_parcalar_ekli_ve_eksiz_ayni_parcaya_iner():
    """"2.500;2.500.00" tek anahtar — mükerrer parça sayılmaz."""
    assert hukdok_aktarim._dosya_no_parcalari("2.500;2.500.00") == ["2.500"]
    assert hukdok_aktarim._dosya_no_parcalari("9.1662;6.5110.00") == ["9.1662", "6.5110"]


def test_kok_cikarimi_ham_degerden_degismez():
    """Kök çıkarımı anahtardan bağımsız: ".00" atılsa da kök aynı."""
    assert hukdok_aktarim._dosya_no_koku("2.500.00") == hukdok_aktarim._dosya_no_koku("2.500") == "2"


# ─── Birim: eski unvan istisnası ─────────────────────────────────────────────

@pytest.mark.parametrize("dosya_no, muvekkil, celiski", [
    ("2.554.00", "Corpus Sigorta Anonim Şirketi", False),   # H-5441: kök Quick, hücre Corpus
    ("2.557.00", "Corpus Sigorta A.Ş.", False),             # yazım farkı — aynı marka
    ("8.019.00", "Ergo Sigorta A.Ş.", False),               # H-1592: kök HDI, hücre Ergo
    ("2.554.00", "Quick Sigorta A.Ş.", False),              # kökün kendi adı: zaten çelişki değil
    ("2.554.00", "Axa Sigorta A.Ş.", True),                 # başka sigorta: çelişki sürer
    ("3.1400.00", "Corpus Sigorta Anonim Şirketi", True),   # eski unvan yalnız KENDİ kökünde
    ("1.20563.00", "Ergo Sigorta A.Ş.", True),
])
def test_eski_unvan_kok_muvekkil_celiskisi_degil(dosya_no, muvekkil, celiski):
    sebep = hukdok_aktarim._kok_muvekkil_celiskisi(_satir_ham(dosya_no=dosya_no, muvekkil=muvekkil))
    assert (sebep is not None) is celiski


@pytest.mark.parametrize("adlar, kok, beklenen", [
    (["Corpus Sigorta Anonim Şirketi"], "2", True),          # Corpus kartı = Quick'in kartı
    (["Ergo Sigorta A.Ş."], "8", True),
    (["Corpus Sigorta Anonim Şirketi"], "3", False),         # başka kökte değil
    (["Corpus Sigorta Anonim Şirketi", "Ahmet Yılmaz"], "2", False),   # hekim ortak → sigortanın kartı değil
])
def test_kokun_karti_mi_eski_unvani_kokun_sayar(adlar, kok, beklenen):
    assert hukdok_aktarim._kokun_karti_mi({normalize_party_key(a) for a in adlar}, kok) is beklenen


def test_eski_unvan_haritasi_ekibin_listesi():
    """12.09 §1: Corpus → Quick (kök 2), Ergo → HDI (kök 8); her ad marka çıkarır."""
    assert set(hukdok_aktarim.DOSYANO_KOK_ESKI_UNVANLARI) == {"2", "8"}
    for kok, adlar in hukdok_aktarim.DOSYANO_KOK_ESKI_UNVANLARI.items():
        assert kok in hukdok_aktarim.DOSYANO_KOK_MUVEKKILI
        for ad in adlar:
            assert hukdok_aktarim._sigorta_markasi(normalize_party_key(ad)), (kok, ad)


# ─── sqlite: uçtan uca ───────────────────────────────────────────────────────

def test_eksiz_kart_ekli_dosya_no_ile_eslesir(db_env, tmp_path):
    """Çekirdek vaka (Ek-3 › 01, 37 föy): kart `2.500` (30.07 dışa aktarımı,
    föysüz), paket `2.500.00` → föy o karta bağlanır, yeni kart AÇILMAZ."""
    db = db_env()
    try:
        kart = _kart(db, "S4.QUICK......0469.HUKUK.00000", "2.500", file_type="Hukuk", esas_no="2025/393")
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-16708", "2.500.00", **{"Ana Tür": "HUKUK", "Esas": "2025/393"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert _foy_karti(db_env, "H-16708") == kart_id
    db = db_env()
    try:
        assert db.query(models.Case).count() == 1
    finally:
        db.close()


def test_ilk_parca_anahtari_h11235_deseni(db_env, tmp_path, caplog):
    """18 satırın "tek aday çıkmadı" dediğimiz H-11235'i: iki kart aynı esas/tür,
    müvekkil (Aysel Koca Hem.) İKİSİNDE de var, kök 1327 ≥ 500 (adım yok).
    Ekibin kuralı: klasör listesi 1327.001.00 ile BAŞLAYAN kart (794) seçilir."""
    db = db_env()
    try:
        tekli = _kart(db, "X1.A_HEM......0001.HUKUK.00000", "1327.001.00;1393.001.00;1395.001.00",
                      file_type="Hukuk", esas_no="2020/193")
        coklu = _kart(db, "X1.M_HEM......0001.HUKUK.00000", "1326.001.00;907.003.00;1327.001.00",
                      file_type="Hukuk", esas_no="2020/193")
        _muvekkil(db, tekli, "Aysel Koca Hem.")
        _muvekkil(db, coklu, "Aysel Koca Hem.")
        _muvekkil(db, coklu, "Meral Veysal Hem.")
        db.commit()
        tekli_id = tekli.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-11235", "1327.001.00", **{"Ana Tür": "HUKUK", "Esas": "2020/193",
                                            "Müvekkil": "Aysel Koca Hem."}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert _foy_karti(db_env, "H-11235") == tekli_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+ilk parça," in m and "ilk parça='1327.001'" in m for m in loglar)


def test_ilk_parca_muvekkil_adindan_sonra(db_env, tmp_path, caplog):
    """Sıra: müvekkil adı tek adaya iniyorsa ilk parça adımına GELİNMEZ —
    liste sırası yalnız esas/tür/kök/ad sustuğunda konuşur."""
    db = db_env()
    try:
        a = _kart(db, "HA.G178.A", "D-1;D-2", file_type="Hukuk", esas_no="2023/1")
        b = _kart(db, "HA.G178.B", "D-2;D-1", file_type="Hukuk", esas_no="2023/1")
        _muvekkil(db, a, "Ahmet Yılmaz")
        _muvekkil(db, b, "Mehmet Kaya")
        db.commit()
        b_id = b.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-SIRA", "D-1", **{"Ana Tür": "HUKUK", "Esas": "2023/1", "Müvekkil": "Mehmet Kaya"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    assert _foy_karti(db_env, "F-SIRA") == b_id            # ad kazandı, liste sırası (A) değil
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+müvekkil," in m for m in loglar)


def test_gercek_mukerrer_hala_belirsiz_sebep_ilk_parca_icerir(db_env, tmp_path):
    """id-14272 deseni: iki kart da aynı tek parçayla başlıyor, aynı müvekkil →
    hiçbir adım ayırmaz; sebep metni denenen "ilk parça" anahtarını da sayar."""
    db = db_env()
    try:
        a = _kart(db, "S1.AK.........0686.IDARE.00000", "3.563.00", file_type="İdare", esas_no="2019/12")
        b = _kart(db, "S1.AK.........0687.IDARE.00000", "3.563.00", file_type="İdare", esas_no="2019/12")
        _muvekkil(db, a, "Ak Sigorta A.ş.")
        _muvekkil(db, b, "Ak Sigorta A.ş.")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-14272", "3.563.00", **{"Ana Tür": "İDARE", "Esas": "2019/12",
                                          "Müvekkil": "Ak Sigorta A.Ş."}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, dry_run=True, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI and len(sonuc.hatalar) == 1
    sebep = sonuc.hatalar[0].sebep
    assert "Dosya No '3.563.00'" in sebep                  # ekibin gördüğü ham değer
    assert sebep.endswith("— esas/tür/kök/müvekkil/ilk parça de ayırmadı")


def test_corpus_satiri_yazilir_ve_kok_adimi_corpus_kartini_secer(db_env, tmp_path, caplog):
    """H-5441 deseni uçtan uca: kök 2 (Quick), hücre Corpus → satır artık
    DÜŞMEZ; ikiz kartlardan CLIENT'ı Corpus olan, kök adımında Quick'in kartı
    sayılır ve seçilir."""
    db = db_env()
    try:
        corpus = _kart(db, "S4.CORPUS.....0004.HUKUK.00000", "2.554.00", file_type="Hukuk", esas_no="2015/1367")
        ak = _kart(db, "S1.AK.........0999.HUKUK.00000", "2.554.00", file_type="Hukuk", esas_no="2015/1367")
        _muvekkil(db, corpus, "Corpus Sigorta Anonim Şirketi")
        _muvekkil(db, ak, "Ak Sigorta A.Ş.")
        db.commit()
        corpus_id = corpus.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-5441", "2.554.00", **{"Ana Tür": "HUKUK", "Esas": "2015/1367",
                                        "Müvekkil": "Corpus Sigorta Anonim Şirketi"}),
    ], basliklar=BASLIKLAR_G153)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert sonuc.kok_muvekkil_celiskisi == 0
    assert _foy_karti(db_env, "H-5441") == corpus_id
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=esas+tür+kök," in m and "kök=2=" in m for m in loglar)


def test_baska_kokte_corpus_hala_celiski(db_env, tmp_path):
    """İstisna yalnız kendi kökünde: kök 3 (Ak) + hücre Corpus → satır yine düşer."""
    db = db_env()
    try:
        _kart(db, "S1.AK.........0500.HUKUK.00000", "3.900.00", file_type="Hukuk", esas_no="2020/1")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-X", "3.900.00", **{"Ana Tür": "HUKUK", "Esas": "2020/1",
                                     "Müvekkil": "Corpus Sigorta Anonim Şirketi"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.kok_muvekkil_celiskisi == 1
    assert _foy_karti(db_env, "H-X") is None
