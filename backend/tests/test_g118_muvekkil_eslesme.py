"""G118 — Belirsiz eşleşmede üçüncü anahtar: satırın `Müvekkil` adı ↔ kartın
CLIENT tarafları.

03.09 lokal uçtan uca testinde 18.08 paketinin 36 hatasının 33'ü "belirsiz
eşleşme"ydi: aynı Dosya No bizde iki (bazen üç) kartla eşleşiyor, esas + Ana
Tür ikisinde de aynı — tipik hâl aynı davanın iki müvekkilli kartı. Satırın
`Müvekkil` sütunu hangi kartın kastedildiğini söylüyor; eşleştirici artık ona
da bakıyor (`_ikinci_anahtarla_coz`, adım 4-7). Tahmin yasağı korunur: ad da
ayırmıyorsa satır yine rapora düşer.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
paketler openpyxl ile SENTETİK üretilir (test_g064 yardımcıları). Gerçek
paketle ölçüm yalnız görev raporundadır.
"""
import logging
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import foy_map
from party_check import normalize_party_key
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import CIKIS_SATIR_HATASI, CIKIS_TAMAM, HamSatir, aktarimi_kos
from tests.test_g064_aktarim_cekirdek import BASLIKLAR, _kart, _paket_yaz, _satir

BASLIKLAR_G118 = BASLIKLAR + ["Ana Tür", "Esas", "Müvekkil"]


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
    db.add(models.CaseParty(case_id=case.id, name=ad, role="Müvekkil",
                            party_type="CLIENT", client_id=client_id))


def _cozum_loglari(caplog):
    return [r.getMessage() for r in caplog.records
            if "ikinci anahtarla çözüldü" in r.getMessage()]


# ─── Birim: anahtar sözleşmesi ───────────────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    ("Acıbadem Sağlık A.Ş.", "Acıbadem Sağlık Anonim Şirketi"),   # şirket eki
    ("Ahmet Yılmaz", "Yılmaz Ahmet"),                                # kelime sırası
    ("MEHMET  KAYA", "Mehmet Kaya"),                                 # boşluk/büyük-küçük
])
def test_normalize_party_key_esitleyen_farklar(a, b):
    assert normalize_party_key(a) == normalize_party_key(b)


def test_normalize_party_key_bir_harf_farki_eslesmez():
    """Tam anahtar eşitliği: bulanık/kısmi eşleşme YOK — Ahmet ≠ Ahmed."""
    assert normalize_party_key("Ahmet Yılmaz") != normalize_party_key("Ahmed Yılmaz")


def test_satir_muvekkil_anahtarlari_coklu_ad_ve_bos():
    satir = HamSatir(satir_no=2, degerler={"muvekkil": "Ahmet Yılmaz; Acıbadem A.Ş."})
    assert hukdok_aktarim._satir_muvekkil_anahtarlari(satir) == {
        normalize_party_key("Ahmet Yılmaz"), normalize_party_key("Acıbadem A.Ş."),
    }
    assert hukdok_aktarim._satir_muvekkil_anahtarlari(HamSatir(satir_no=3, degerler={})) == set()
    assert hukdok_aktarim._satir_muvekkil_anahtarlari(
        HamSatir(satir_no=4, degerler={"muvekkil": "  "})) == set()


def test_kart_muvekkil_anahtarlari_yalniz_client_ve_bagli_musteri(db_env):
    """Kümeye CLIENT taraflar + bağlı `clients.name` girer; COUNTER/THIRD ve
    silinmiş müvekkil kaydı GİRMEZ."""
    db = db_env()
    try:
        kart = _kart(db, "HA.G118.K", "D-K")
        canli = models.Client(name="Kaya Hastanesi Anonim Şirketi")
        silinmis = models.Client(name="Eski Müvekkil Ltd. Şti.", deleted_at=datetime.now())
        db.add_all([canli, silinmis])
        db.flush()
        _muvekkil(db, kart, "Ahmet Yılmaz", client_id=canli.id)
        _muvekkil(db, kart, "Zeynep Demir", client_id=silinmis.id)
        db.add(models.CaseParty(case_id=kart.id, name="Karşı Kişi", role="Karşı Taraf",
                                party_type="COUNTER"))
        db.add(models.CaseParty(case_id=kart.id, name="AK Sigorta A.Ş.", role="Sigortalı",
                                party_type="THIRD"))
        db.commit()
        assert hukdok_aktarim._kart_muvekkil_anahtarlari(db, kart.id) == {
            normalize_party_key("Ahmet Yılmaz"),
            normalize_party_key("Kaya Hastanesi A.Ş."),        # bağlı müvekkil, eki eşitlenmiş
            normalize_party_key("Zeynep Demir"),               # taraf satırı kalır
        }
    finally:
        db.close()


# ─── sqlite: uçtan uca eleme sırası ──────────────────────────────────────────

def _iki_muvekkilli_ikiz(db_env, *, esas="2023/449", tur="Hukuk"):
    """Aynı Dosya No, aynı esas, aynı tür, FARKLI müvekkil — 03.09'un tipik hâli."""
    db = db_env()
    try:
        a = _kart(db, "HA.G118.A", "D-CIFT", file_type=tur, esas_no=esas)
        b = _kart(db, "HA.G118.B", "D-CIFT", file_type=tur, esas_no=esas)
        _muvekkil(db, a, "Ahmet Yılmaz")
        _muvekkil(db, b, "Acıbadem Sağlık Anonim Şirketi")
        db.commit()
        return a.id, b.id
    finally:
        db.close()


def test_dorduncu_adim_esas_tur_muvekkil_ile_secer(db_env, tmp_path, caplog):
    """Kabul 1: esas ve tür iki kartta da aynı; satırın Müvekkil'i birine
    uyuyor → o kart (4. adım), log kriteri esas+tür+müvekkil."""
    a_id, b_id = _iki_muvekkilli_ikiz(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-A", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                   "Müvekkil": "Yılmaz Ahmet"}),                 # kelime sırası
        _satir("F-B", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                   "Müvekkil": "ACIBADEM SAĞLIK A.Ş."}),        # şirket eki
    ], basliklar=BASLIKLAR_G118)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    db = db_env()
    try:
        assert foy_map.get_foy(db, "F-A").case_id == a_id
        assert foy_map.get_foy(db, "F-B").case_id == b_id
    finally:
        db.close()
    loglar = _cozum_loglari(caplog)
    assert len(loglar) >= 2 and all("kriter=esas+tür+müvekkil" in m for m in loglar)


def test_ayni_muvekkilli_ikizler_none_ve_rapor_sebebi(db_env, tmp_path):
    """Kabul 2: iki kart aynı müvekkil anahtarını taşıyor (gerçek mükerrer) →
    tahmin YOK, satır "müvekkil de ayırmadı" ile rapora düşer."""
    db = db_env()
    try:
        a = _kart(db, "HA.G118.A", "D-AYNI", file_type="Hukuk", esas_no="2023/1")
        b = _kart(db, "HA.G118.B", "D-AYNI", file_type="Hukuk", esas_no="2023/1")
        _muvekkil(db, a, "Ahmet Yılmaz")
        _muvekkil(db, b, "Yılmaz Ahmet")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-X", "D-AYNI", **{"Ana Tür": "HUKUK", "Esas": "2023/1",
                                   "Müvekkil": "Ahmet Yılmaz"}),
    ], basliklar=BASLIKLAR_G118)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI and len(sonuc.hatalar) == 1
    assert "Belirsiz eşleşme" in sonuc.hatalar[0].sebep
    assert "esas/tür/müvekkil de ayırmadı" in sonuc.hatalar[0].sebep
    db = db_env()
    try:
        assert foy_map.get_foy(db, "F-X") is None
    finally:
        db.close()


def test_muvekkil_eslesmeyince_sebep_yine_muvekkil_de_ayirmadi(db_env, tmp_path):
    """Müvekkil dolu ama hiçbir adaya uymuyor → davranış eskiyle aynı (None),
    sebep metni üçüncü anahtarın da denendiğini söyler."""
    _iki_muvekkilli_ikiz(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-Y", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                   "Müvekkil": "Ahmed Yılmaz"}),               # bir harf farkı
    ], basliklar=BASLIKLAR_G118)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert len(sonuc.hatalar) == 1
    assert "esas/tür/müvekkil de ayırmadı" in sonuc.hatalar[0].sebep


def test_ucuncu_adim_tur_muvekkille_celisse_de_kazanir(db_env, tmp_path, caplog):
    """Kabul 3 (sıra testi): müvekkil eşleşen kart tür ile ÇELİŞİYOR ve tür tek
    adaya iniyor → mevcut 3. adım kazanır, müvekkil adımlarına gelinmez."""
    db = db_env()
    try:
        hukuk = _kart(db, "HA.G118.H", "D-SIRA", file_type="Hukuk")
        arabu = _kart(db, "HA.G118.R", "D-SIRA", file_type="Arabuluculuk")
        _muvekkil(db, hukuk, "Zeynep Demir")
        _muvekkil(db, arabu, "Ahmet Yılmaz")
        db.commit()
        hukuk_id = hukuk.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-S", "D-SIRA", **{"Ana Tür": "HUKUK", "Müvekkil": "Ahmet Yılmaz"}),
    ], basliklar=BASLIKLAR_G118)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    db = db_env()
    try:
        assert foy_map.get_foy(db, "F-S").case_id == hukuk_id     # tür kazandı
    finally:
        db.close()
    # Ön geçiş (`_kart_id_tahmini`) + asıl döngü aynı satırı iki kez çözer;
    # önemli olan her çözümün AYNI kriterle gelmesi.
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=tür," in m for m in loglar)


def test_yedinci_adim_yalniz_muvekkil_esas_ve_tur_susunca(db_env, tmp_path, caplog):
    """Esas ve tür hiçbir şey söylemiyorsa (satırda yok) 7. adım devreye girer."""
    a_id, _b_id = _iki_muvekkilli_ikiz(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-M", "D-CIFT", **{"Müvekkil": "Ahmet Yılmaz"}),
    ], basliklar=BASLIKLAR_G118)

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert not sonuc.hatalar
    db = db_env()
    try:
        assert foy_map.get_foy(db, "F-M").case_id == a_id
    finally:
        db.close()
    loglar = _cozum_loglari(caplog)
    assert loglar and all("kriter=müvekkil," in m for m in loglar)


def test_muvekkil_sutunu_yoksa_davranis_birebir_eski(db_env, tmp_path):
    """Kabul 4: `Müvekkil` sütunu paketten büsbütün eksik → None + eski sebep
    metni ("esas/tür de ayırmadı"), "müvekkil" sözcüğü geçmez."""
    _iki_muvekkilli_ikiz(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-E", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449"}),
    ], basliklar=BASLIKLAR + ["Ana Tür", "Esas"])

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI and len(sonuc.hatalar) == 1
    assert sonuc.hatalar[0].sebep.endswith("— esas/tür de ayırmadı")
    assert "müvekkil" not in sonuc.hatalar[0].sebep


def test_idempotency_muvekkille_secilen_kartlar_ikinci_kosuda_sifir_degisiklik(db_env, tmp_path):
    """Kabul 6: aynı girdiyle ikinci koşu 0 değişiklik — üçüncü anahtarla
    seçilen kartlar dahil (föy sabit kalır, alan/taraf değişmez)."""
    a_id, b_id = _iki_muvekkilli_ikiz(db_env)
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("F-A", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                   "Müvekkil": "Ahmet Yılmaz", "Hasar No": "H-A"}),
        _satir("F-B", "D-CIFT", **{"Ana Tür": "HUKUK", "Esas": "2023/449",
                                   "Müvekkil": "Acıbadem Sağlık A.Ş.", "Hasar No": "H-B"}),
    ], basliklar=BASLIKLAR_G118)

    ilk = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM and (ilk.foy_yeni, ilk.foy_guncellenen) == (2, 0)
    assert ilk.taraf_eklenen == 0                        # müvekkil zaten kartta

    def _fotograf():
        db = db_env()
        try:
            return (
                {f.sistem_no: f.case_id for f in db.query(models.CaseFoy)},
                db.query(models.CaseParty).count(),
                db.query(models.CaseHistory).count(),
            )
        finally:
            db.close()

    sonrasi = _fotograf()
    assert sonrasi[0] == {"F-A": a_id, "F-B": b_id}

    ikinci = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert (ikinci.foy_yeni, ikinci.foy_guncellenen) == (0, 2)
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0 and ikinci.taraf_eklenen == 0
    assert _fotograf() == sonrasi
