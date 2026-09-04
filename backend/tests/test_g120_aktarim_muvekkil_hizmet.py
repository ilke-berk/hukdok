"""G120 — Aktarım eşlemesi: Müvekkil Tipi + Hizmet Türü teslimden kartlara.

G119'un açtığı iki kapalı-liste alanı (`cases.muvekkil_tipi`, `cases.hizmet_turu`)
aktarım yazma yoluna G104 deseninin birebir kopyasıyla bağlanır. Sözleşme
(DB-2026-002, 04.09.2026):

* Başlıklar `Müvekkil Tipi` / `Hizmet Türü`; `_baslik_anahtari` toleransı
  aksan/büyük-küçük farkını yutar; başlık teslimde yoksa alan "bu teslimde yok"
  sayılır, davranış birebir eskisidir (None = boşalt DEĞİL).
* Değer eşlemesi AD bazlı, kanonik adların tek kaynağı G119 seed sabitleri
  (`seed_data.CLIENT_TYPES` / `SERVICE_TYPES`); tanınmayan değer YAZILMAZ ve
  satır raporuna düşer — satırın diğer alanları normal işlenir (`AlanHatasi`).
* ` ; ` ayraçlı çok değer İKİ alanda da TANIMSIZ → yazılmaz + rapor (hukumdeki_rol
  kuralı); KARMA benzeri normalizasyon YOK.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
testler openpyxl ile SENTETİK mini paket üretir (test_g104 düzeni).
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import foy_map, seed_data
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    CIKIS_SATIR_HATASI,
    CIKIS_TAMAM,
    AlanHatasi,
    aktarimi_kos,
    xlsx_oku,
)

# Sentetik paketin başlıkları — gerçek teslim paketiyle AYNI adlar, içerik
# uydurma. "Müvekkil" BİLEREK içeride: taraf sütunuyla `Müvekkil Tipi`
# sütununun başlık eşlemesi çapraz bağlanmamalı.
BASLIKLAR = ["SistemNo", "TKU", "Hasar No", "Dosya No", "Tıbbi Olay", "Müvekkil"]
G120_BASLIKLAR = BASLIKLAR + ["Müvekkil Tipi", "Hizmet Türü"]


def _paket_yaz(yol, satirlar, *, basliklar=None, sayfa="Föyler"):
    """Sentetik mini teslim paketi (.xlsx); satırlar sözlük listesidir."""
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
    temel = {"SistemNo": sistem_no, "Dosya No": dosya_no, "TKU": "TKU-120"}
    temel.update(extra)
    return temel


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — dönüştürücüler + sözleşme/kayıt kilitleri (DB yok)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ham,beklenen", [
    ("Sigorta", "Sigorta"),                            # bildirimin örnek satırı
    ("SİGORTA", "Sigorta"),                            # değer eşlemesi toleranslı
    ("doktor", "Doktor"),
    ("Diğer Sağlık Çalışanı", "Diğer Sağlık Çalışanı"),
    ("DIGER SAGLIK CALISANI", "Diğer Sağlık Çalışanı"),   # aksansız yazım
    ("Hasta ; Hasta", "Hasta"),                        # mükerrer yazım tek değerdir
    (None, None),
    ("", None),
    ("-", None),                                       # D5 ortak yer tutucu sözlüğü
    ("YOK", None),
])
def test_muvekkil_tipi_donusumu(ham, beklenen):
    assert hukdok_aktarim._muvekkil_tipi(ham, "muvekkil_tipi") == beklenen


@pytest.mark.parametrize("ham,beklenen", [
    ("Lexis Rapor", "Lexis Rapor"),                    # bildirimin örnek satırı
    ("LEXIS RAPOR", "Lexis Rapor"),
    ("Takip (doktor müvekkil)", "Takip (doktor müvekkil)"),
    ("TAKIP DOKTOR MUVEKKIL", "Takip (doktor müvekkil)"),  # parantez/aksan toleransı
    ("Vekalet Ücreti Alacağı", "Vekalet Ücreti Alacağı"),
    ("danismanlik", "Danışmanlık"),
    ("Lexis Rapor;Lexis Rapor", "Lexis Rapor"),        # mükerrer yazım tek değerdir
    (None, None),
    ("-", None),
])
def test_hizmet_turu_donusumu(ham, beklenen):
    assert hukdok_aktarim._hizmet_turu(ham, "hizmet_turu") == beklenen


@pytest.mark.parametrize("ham", [
    "Sigorta Şirketi",                     # kapalı listede yok (görev örneği)
    "Sigorta ; Sigorta Şirketi",           # kısmi tanıma = tahmin, yasak
    "Lexis Rapor",                         # HİZMET listesinin değeri TİP listesinde geçmez
])
def test_muvekkil_tipi_taninmayan_deger_alan_hatasi(ham):
    """Tahmin yasağı: kapalı listeye zorlanamayan hücre alanı düşürür (satırı değil)."""
    with pytest.raises(AlanHatasi, match="kapalı listede"):
        hukdok_aktarim._muvekkil_tipi(ham, "muvekkil_tipi")


@pytest.mark.parametrize("ham", [
    "Rapor",                               # kısaltma tahmin edilmez
    "Takip",                               # beş "Takip (...)" değerinden hangisi? tahmin yok
    "Sigorta",                             # TİP listesinin değeri HİZMET listesinde geçmez
])
def test_hizmet_turu_taninmayan_deger_alan_hatasi(ham):
    with pytest.raises(AlanHatasi, match="kapalı listede"):
        hukdok_aktarim._hizmet_turu(ham, "hizmet_turu")


def test_cok_deger_iki_alanda_da_tanimsiz():
    """SÖZLEŞME: iki alanda da çok değer tanımsızdır — KARMA benzeri
    normalizasyon YOK (hukumdeki_rol kuralı)."""
    with pytest.raises(AlanHatasi, match="çok değerli"):
        hukdok_aktarim._muvekkil_tipi("Sigorta ; Doktor", "muvekkil_tipi")
    with pytest.raises(AlanHatasi, match="çok değerli"):
        hukdok_aktarim._hizmet_turu("Lexis Rapor ; Vekaletli Takip", "hizmet_turu")


def test_sozlesme_kapali_liste_adlari_seed_sabitlerinden():
    """SÖZLEŞME kilidi: 5+9 kanonik ad birebir; kaynak G119 seed sabitleri
    (literal kopya DEĞİL — panel/liste değişirse eşleme kendiliğinden izler)."""
    assert set(hukdok_aktarim.MUVEKKIL_TIPI_ESLEMESI.values()) == {
        "Sigorta", "Doktor", "Kurum", "Hasta", "Diğer Sağlık Çalışanı",
    }
    assert set(hukdok_aktarim.HIZMET_TURU_ESLEMESI.values()) == {
        "Takip (doktor müvekkil)", "Lexis Rapor", "Vekaletsiz Takip",
        "Vekaletli Takip", "Vekalet Ücreti Alacağı", "Takip (hasta vekilliği)",
        "Takip (kurum vekilliği)", "Danışmanlık", "Takip (sağlık personeli)",
    }
    assert set(hukdok_aktarim.MUVEKKIL_TIPI_ESLEMESI.values()) == {
        ad for _kod, ad in seed_data.CLIENT_TYPES
    }
    assert set(hukdok_aktarim.HIZMET_TURU_ESLEMESI.values()) == {
        ad for _kod, ad in seed_data.SERVICE_TYPES
    }
    # Anahtar çakışması yok: 5 ve 9 ad, 5 ve 9 anahtara çözülür.
    assert len(hukdok_aktarim.MUVEKKIL_TIPI_ESLEMESI) == len(seed_data.CLIENT_TYPES)
    assert len(hukdok_aktarim.HIZMET_TURU_ESLEMESI) == len(seed_data.SERVICE_TYPES)


def test_kayit_kilitleri_sutun_adaylari_kart_alanlari_ve_docstring():
    """Eşleme kayıtları + sınıf kararı + kabul 6 (KART_ALANLARI + docstring)."""
    assert hukdok_aktarim.SUTUN_ADAYLARI["muvekkil_tipi"] == ("Müvekkil Tipi",)
    assert hukdok_aktarim.SUTUN_ADAYLARI["hizmet_turu"] == ("Hizmet Türü",)
    assert hukdok_aktarim.KART_ALANLARI["muvekkil_tipi"] == (
        "muvekkil_tipi", hukdok_aktarim._muvekkil_tipi)
    assert hukdok_aktarim.KART_ALANLARI["hizmet_turu"] == (
        "hizmet_turu", hukdok_aktarim._hizmet_turu)
    # Dolu hücre kuralı: METİN alanlarının varsayılan (üzerine yazma) sınıfı —
    # İÇERİK moduna GİRMEZLER (dönüşüm çıktısı zaten kanonik ad).
    assert not {"muvekkil_tipi", "hizmet_turu"} & hukdok_aktarim.ICERIK_KARSILASTIRMALI_ALANLAR
    # `service_type` (ofis dosya no hizmet bloğu) yazılmaya BAŞLANMADI — ayrı alan.
    assert "service_type" not in hukdok_aktarim.KART_ALANLARI
    # Kabul 6: modül docstring'inin "YAZILAN kart alanları" bölümü iki alanı sayar.
    doc = hukdok_aktarim.__doc__ or ""
    yazilan = doc.split("YAZILAN kart alanları", 1)[1].split("Bilinçli YAZILMAYANLAR", 1)[0]
    assert "muvekkil_tipi" in yazilan and "hizmet_turu" in yazilan


def test_baslik_toleransi_aksansiz_yazim_da_okunur(tmp_path):
    """`_baslik_anahtari` toleransı: BÜYÜK/aksansız/küçük yazımlar aynı sütuna çözülür."""
    paket = _paket_yaz(tmp_path / "t.xlsx", [
        {"SistemNo": "H-11636", "Dosya No": "D-1",
         "MUVEKKIL TIPI": "Sigorta", "hizmet türü": "Lexis Rapor"},
    ], basliklar=["SistemNo", "Dosya No", "MUVEKKIL TIPI", "hizmet türü"])

    satirlar, bulunanlar = xlsx_oku(paket)

    assert bulunanlar["muvekkil_tipi"] == "MUVEKKIL TIPI"
    assert bulunanlar["hizmet_turu"] == "hizmet türü"
    assert satirlar[0].degerler["muvekkil_tipi"] == "Sigorta"
    assert satirlar[0].degerler["hizmet_turu"] == "Lexis Rapor"


def test_eski_formatta_basliklar_yok_alan_okunmaz(tmp_path):
    """Toleransın öbür yüzü: başlık yoksa alan hiç okunmaz; taraf sütunu
    "Müvekkil" `muvekkil_tipi`ye ÇAPRAZ bağlanmaz."""
    paket = _paket_yaz(tmp_path / "t.xlsx",
                       [_satir("S-1", "D-1", **{"Müvekkil": "Ayşe Yılmaz"})])

    satirlar, bulunanlar = xlsx_oku(paket)

    assert "muvekkil_tipi" not in bulunanlar and "hizmet_turu" not in bulunanlar
    assert "muvekkil_tipi" not in satirlar[0].degerler
    assert satirlar[0].degerler["muvekkil"] == "Ayşe Yılmaz"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite (test_g064 fixture reçetesi: FK + ÇALIŞAN SAVEPOINT)
# ═══════════════════════════════════════════════════════════════════════════

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


def _kart(db, tracking, klasor, **extra):
    case = models.Case(tracking_no=tracking, status="DERDEST", klasor_no_2=klasor, **extra)
    db.add(case)
    db.flush()
    return case


@pytest.fixture()
def iki_kart(db_env):
    db = db_env()
    try:
        for i in (1, 2):
            _kart(db, f"HA.G120.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    return db_env


def _kartlar(fabrika):
    db = fabrika()
    try:
        return {c.klasor_no_2: (c.muvekkil_tipi, c.hizmet_turu)
                for c in db.query(models.Case).all()}
    finally:
        db.close()


def test_basliksiz_paket_iki_alani_ellemiyor(db_env, tmp_path):
    """Kabul 1: başlık teslimde yoksa alan atlanır — DOLU değer boşalmaz,
    tarihçeye satır düşmez, koşu yeşil (eski paketle davranış birebir eski)."""
    db = db_env()
    try:
        _kart(db, "HA.G120.1", "D-1",
              muvekkil_tipi="Sigorta", hizmet_turu="Lexis Rapor")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "eski.xlsx",
                       [_satir("S-1", "D-1", **{"Tıbbi Olay": "Enfeksiyon"})])

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.alan_degisikligi == 1                # yalnız serbest-metin tibbi_olay
    db = db_env()
    try:
        kart = db.query(models.Case).one()
        assert (kart.muvekkil_tipi, kart.hizmet_turu) == ("Sigorta", "Lexis Rapor")
        assert kart.tibbi_olay == "Enfeksiyon"
        alanlar = {h.field_name for h in db.query(models.CaseHistory).all()}
        assert not alanlar & {"muvekkil_tipi", "hizmet_turu"}
    finally:
        db.close()


def test_dry_run_iki_alan_farkta_gorunur_dbye_yazilmaz(iki_kart, tmp_path):
    """Kabul 2: kuru koşu iki alanı fark sayımında gösterir, hiçbir tabloya
    yazmaz (kart alanları + tarihçe + föy sıfır kalır)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-11636", "D-1", **{"Müvekkil Tipi": "Sigorta",
                                    "Hizmet Türü": "Lexis Rapor"}),
    ], basliklar=G120_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, dry_run=True,
                         rapor_dizini=tmp_path / "rapor")

    assert sonuc.dry_run and not sonuc.yazildi
    assert sonuc.alan_degisikligi == 2 and sonuc.kart_degisen == 1
    db = iki_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert (kart.muvekkil_tipi, kart.hizmet_turu) == (None, None)
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.CaseFoy).count() == 0
    finally:
        db.close()


def test_gecerli_deger_yazilir_taninmayan_rapora_duser(iki_kart, tmp_path):
    """Kabul 3: "Sigorta" / "Lexis Rapor" KANONİK yazımla yazılır; "Sigorta
    Şirketi" gibi listede olmayan değer yazılmaz, satır raporuna gerekçesiyle
    düşer — föyün DİĞER alanları normal işlenir (satır düşmez)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-11636", "D-1", **{"Müvekkil Tipi": "SİGORTA",
                                    "Hizmet Türü": "Lexis Rapor"}),
        _satir("S-2", "D-2", **{"Müvekkil Tipi": "Sigorta Şirketi",
                                "Hizmet Türü": "Vekaletli Takip",
                                "Tıbbi Olay": "Enfeksiyon"}),
    ], basliklar=G120_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI     # insan müdahalesi konusu
    assert sonuc.islenen == 2                         # satır DÜŞMEDİ
    assert len(sonuc.rapor_satirlari) == 1
    hata = sonuc.hatalar[0]
    assert hata.sistem_no == "S-2" and hata.tur == "HATA"
    assert "muvekkil_tipi yazılmadı" in hata.sebep and "Sigorta Şirketi" in hata.sebep

    db = iki_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        # tolere yazım kanonik ada çözüldü (bizim yazımımız)
        assert kartlar["D-1"].muvekkil_tipi == "Sigorta"
        assert kartlar["D-1"].hizmet_turu == "Lexis Rapor"
        # tanınmayan değer yazılmadı; satırın DİĞER alanları ve föyü İŞLENDİ
        assert kartlar["D-2"].muvekkil_tipi is None
        assert kartlar["D-2"].hizmet_turu == "Vekaletli Takip"
        assert kartlar["D-2"].tibbi_olay == "Enfeksiyon"
        assert foy_map.get_foy(db, "S-2") is not None
    finally:
        db.close()

    rapor = [y for y in sonuc.raporlar if "satir-raporu" in y.name]
    assert rapor and "Sigorta Şirketi" in rapor[0].read_text(encoding="utf-8-sig")


def test_cok_deger_yazilmaz_rapora_duser(iki_kart, tmp_path):
    """Kabul 4: ` ; ` ile çok değer iki alanda da yazılmaz + rapora düşer."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Müvekkil Tipi": "Sigorta ; Doktor"}),
        _satir("S-2", "D-2", **{"Hizmet Türü": "Lexis Rapor ; Vekaletli Takip"}),
    ], basliklar=G120_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    assert _kartlar(iki_kart) == {"D-1": (None, None), "D-2": (None, None)}
    sebepler = {h.sistem_no: h.sebep for h in sonuc.hatalar}
    assert set(sebepler) == {"S-1", "S-2"}
    assert "muvekkil_tipi yazılmadı" in sebepler["S-1"] and "çok değerli" in sebepler["S-1"]
    assert "hizmet_turu yazılmadı" in sebepler["S-2"] and "çok değerli" in sebepler["S-2"]


def test_ikinci_kosu_sifir_degisiklik_iki_alan_dahil(iki_kart, tmp_path):
    """Kabul 5: idempotency iki yeni alanı da kapsar — aynı girdiyle ikinci
    koşu 0 değişiklik, `case_history` şişmez."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-11636", "D-1", **{"Müvekkil Tipi": "Sigorta",
                                    "Hizmet Türü": "Lexis Rapor"}),
        _satir("S-2", "D-2", **{"Müvekkil Tipi": "doktor"}),
    ], basliklar=G120_BASLIKLAR)

    ilk = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM
    assert ilk.alan_degisikligi == 3 and ilk.kart_degisen == 2

    db = iki_kart()
    try:
        tarihce = db.query(models.CaseHistory).count()
        yazilan = {(h.field_name, h.old_value, h.new_value)
                   for h in db.query(models.CaseHistory)
                   if h.field_name in ("muvekkil_tipi", "hizmet_turu")}
        assert ("muvekkil_tipi", None, "Sigorta") in yazilan
        assert ("hizmet_turu", None, "Lexis Rapor") in yazilan
        assert ("muvekkil_tipi", None, "Doktor") in yazilan
    finally:
        db.close()

    ikinci = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0
    db = iki_kart()
    try:
        assert db.query(models.CaseHistory).count() == tarihce
    finally:
        db.close()
    assert _kartlar(iki_kart) == {"D-1": ("Sigorta", "Lexis Rapor"),
                                  "D-2": ("Doktor", None)}


def test_kardes_foyler_farkli_muvekkil_tipi_celiski_raporuna_duser(iki_kart, tmp_path):
    """Kardeş föy çelişkisi BEKLENEN durumdur (bildirim: "föy başına değişir"):
    aynı kartın iki föyü farklı müvekkil tipi anlatıyorsa mevcut ön-geçiş
    mekanizması alanı yazmaz, çelişki raporuna düşürür — özel istisna YOK."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Müvekkil Tipi": "Sigorta", "Hizmet Türü": "Lexis Rapor"}),
        _satir("S-2", "D-1", **{"Müvekkil Tipi": "Doktor", "Hizmet Türü": "Lexis Rapor"}),
    ], basliklar=G120_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    celiski = [c for c in sonuc.celiskiler if c.alan == "muvekkil_tipi"]
    assert len(celiski) == 1 and celiski[0].kume == "KART"
    assert "S-1=Sigorta" in celiski[0].degerler and "S-2=Doktor" in celiski[0].degerler
    assert not [c for c in sonuc.celiskiler if c.alan == "hizmet_turu"]   # uzlaşan alan çelişki değil
    assert _kartlar(iki_kart)["D-1"] == (None, "Lexis Rapor")   # çelişen yazılmadı, uzlaşan yazıldı


def test_dolu_hucre_metin_sinifiyla_uzerine_yazilir(iki_kart, tmp_path):
    """Sınıf kararı kilidi: iki alan METİN alanlarının VARSAYILAN sınıfında —
    içerik farkında teslim kazanır, tarihçeye eski→yeni düşer."""
    db = iki_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        kart.hizmet_turu = "Vekaletli Takip"
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Hizmet Türü": "Lexis Rapor"}),
    ], basliklar=G120_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.alan_degisikligi == 1
    db = iki_kart()
    try:
        assert db.query(models.Case).filter_by(
            klasor_no_2="D-1").one().hizmet_turu == "Lexis Rapor"
        kayit = db.query(models.CaseHistory).filter_by(field_name="hizmet_turu").one()
        assert (kayit.old_value, kayit.new_value) == ("Vekaletli Takip", "Lexis Rapor")
    finally:
        db.close()
