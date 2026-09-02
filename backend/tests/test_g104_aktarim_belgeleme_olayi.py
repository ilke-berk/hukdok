"""G104 — Aktarım eşlemesi: Olay Türü + Hükümdeki Rol teslimden kartlara.

G103'ün açtığı iki kapalı-liste alanı (`cases.olay_turu`, `cases.hukumdeki_rol`)
aktarım yazma yoluna bağlanır. Sözleşme (25.08 belgesi §5 + 31.08 teslim kuralı):

* Başlıklar (`Olay Türü` / `Hükümdeki Rol`) karşı tarafla yazılı olarak henüz
  SABİTLENMEDİ — eşleme toleranslıdır: başlık teslimde yoksa alan "bu teslimde
  yok" sayılır, davranış birebir eskisidir (None = boşalt DEĞİL).
* Değer eşlemesi AD bazlı, kapalı listeye karşı (adların tek doğruluk kaynağı
  G103 seed sabitleri); tanınmayan değer YAZILMAZ ve satır raporuna düşer —
  satırın diğer alanları normal işlenir (`AlanHatasi`, alan-düzeyi atlama).
* ` ; ` ayraçlı çok değerli hücre: olay türünde {Tıbbi Olay, Belgeleme Olayı}
  → "Tıbbi + Belgeleme"; hükümdeki rolde çok değer TANIMSIZ → yazılmaz + rapor.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
testler openpyxl ile SENTETİK mini paket üretir (test_g064 düzeni).
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
# uydurma. "Tıbbi Olay" BİLEREK içeride: serbest-metin `tibbi_olay` sütunuyla
# kapalı-liste `Olay Türü` sütununun başlık eşlemesi çapraz bağlanmamalı.
BASLIKLAR = ["SistemNo", "TKU", "Hasar No", "Dosya No", "Tıbbi Olay"]
G104_BASLIKLAR = BASLIKLAR + ["Olay Türü", "Hükümdeki Rol"]


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
    temel = {"SistemNo": sistem_no, "Dosya No": dosya_no, "TKU": "TKU-104"}
    temel.update(extra)
    return temel


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — dönüştürücüler + sözleşme/kayıt kilitleri (DB yok)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ham,beklenen", [
    ("Tıbbi Olay", "Tıbbi Olay"),
    ("TIBBİ OLAY", "Tıbbi Olay"),                     # değer eşlemesi de toleranslı
    ("belgeleme olayi", "Belgeleme Olayı"),           # aksansız yazım
    ("Tıbbi + Belgeleme", "Tıbbi + Belgeleme"),       # KARMA'nın kendisi de gelebilir
    ("Tıbbi+Belgeleme", "Tıbbi + Belgeleme"),
    ("Tıbbi Olay ; Belgeleme Olayı", "Tıbbi + Belgeleme"),   # 31.08 kuralı
    ("Belgeleme Olayı;Tıbbi Olay", "Tıbbi + Belgeleme"),     # sıra/boşluk önemsiz
    ("Tıbbi Olay ; Tıbbi Olay", "Tıbbi Olay"),        # mükerrer yazım tek değerdir
    (None, None),
    ("", None),
    ("-", None),                                      # D5 ortak yer tutucu sözlüğü
    ("YOK", None),
])
def test_olay_turu_donusumu(ham, beklenen):
    assert hukdok_aktarim._olay_turu(ham, "olay_turu") == beklenen


@pytest.mark.parametrize("ham", [
    "Aydınlatma",                          # kapalı listede yok (görev örneği)
    "Tıbbi Olay ; Aydınlatma",             # kısmi tanıma = tahmin, yasak
    "Tıbbi Olay ; Tıbbi + Belgeleme",      # tanımsız kombinasyon (yalnız {Tıbbi, Belgeleme})
    "Tek Gerekçe",                         # ROL listesinin değeri TÜR listesinde geçmez
])
def test_olay_turu_taninmayan_deger_alan_hatasi(ham):
    """Tahmin yasağı: kapalı listeye zorlanamayan hücre alanı düşürür (satırı değil)."""
    with pytest.raises(AlanHatasi):
        hukdok_aktarim._olay_turu(ham, "olay_turu")


@pytest.mark.parametrize("ham,beklenen", [
    ("Tek Gerekçe", "Tek Gerekçe"),
    ("YAN GEREKCE", "Yan Gerekçe"),
    ("yalniz saptama", "Yalnız Saptama"),
    ("Reddedilmiş İddia", "Reddedilmiş İddia"),
    ("Tek Gerekçe;TEK GEREKÇE", "Tek Gerekçe"),       # mükerrer yazım tek değerdir
    (None, None),
    ("-", None),
])
def test_hukumdeki_rol_donusumu(ham, beklenen):
    assert hukdok_aktarim._hukumdeki_rol(ham, "hukumdeki_rol") == beklenen


def test_hukumdeki_rol_cok_deger_tanimsiz():
    """SÖZLEŞME: rolde çok değer tanımsızdır — KARMA benzeri normalizasyon YOK."""
    with pytest.raises(AlanHatasi, match="çok değerli"):
        hukdok_aktarim._hukumdeki_rol("Tek Gerekçe ; Yan Gerekçe", "hukumdeki_rol")
    with pytest.raises(AlanHatasi, match="kapalı listede"):
        hukdok_aktarim._hukumdeki_rol("Davacı Vekili", "hukumdeki_rol")


def test_sozlesme_kapali_liste_adlari_seed_sabitlerinden():
    """SÖZLEŞME kilidi: 3+4 kanonik ad birebir; kaynak G103 seed sabitleri
    (literal kopya DEĞİL — panel/liste değişirse eşleme kendiliğinden izler)."""
    assert set(hukdok_aktarim.OLAY_TURU_ESLEMESI.values()) == {
        "Tıbbi Olay", "Belgeleme Olayı", "Tıbbi + Belgeleme",
    }
    assert set(hukdok_aktarim.HUKUMDEKI_ROL_ESLEMESI.values()) == {
        "Tek Gerekçe", "Yan Gerekçe", "Yalnız Saptama", "Reddedilmiş İddia",
    }
    assert hukdok_aktarim._OLAY_TURU_ADLARI == dict(seed_data.EVENT_TYPES)
    assert set(hukdok_aktarim.HUKUMDEKI_ROL_ESLEMESI.values()) == {
        ad for _kod, ad in seed_data.JUDGMENT_ROLES
    }


def test_kayit_kilitleri_sutun_adaylari_kart_alanlari_ve_docstring():
    """Eşleme kayıtları + sınıf kararı + kabul 6 (docstring'in YAZILAN bölümü)."""
    assert hukdok_aktarim.SUTUN_ADAYLARI["olay_turu"] == ("Olay Türü",)
    assert hukdok_aktarim.SUTUN_ADAYLARI["hukumdeki_rol"] == ("Hükümdeki Rol",)
    assert hukdok_aktarim.KART_ALANLARI["olay_turu"] == (
        "olay_turu", hukdok_aktarim._olay_turu)
    assert hukdok_aktarim.KART_ALANLARI["hukumdeki_rol"] == (
        "hukumdeki_rol", hukdok_aktarim._hukumdeki_rol)
    # Dolu hücre kuralı: METİN alanlarının varsayılan (üzerine yazma) sınıfı —
    # İÇERİK moduna GİRMEZLER (dönüşüm çıktısı zaten kanonik ad).
    assert not {"olay_turu", "hukumdeki_rol"} & hukdok_aktarim.ICERIK_KARSILASTIRMALI_ALANLAR
    # Kabul 6: modül docstring'inin "YAZILAN kart alanları" bölümü iki alanı sayar.
    assert "olay_turu" in (hukdok_aktarim.__doc__ or "")
    assert "hukumdeki_rol" in (hukdok_aktarim.__doc__ or "")
    # AlanHatasi bilinçli olarak SatirHatasi DEĞİL: satır düşürmez.
    assert not issubclass(AlanHatasi, hukdok_aktarim.SatirHatasi)


def test_baslik_toleransi_aksansiz_yazim_da_okunur(tmp_path):
    """Başlıklar yazılı sabitlenmedi — `_baslik_anahtari` toleransı iş başında:
    BÜYÜK/aksansız/küçük yazımlar aynı sütuna çözülür."""
    paket = _paket_yaz(tmp_path / "t.xlsx", [
        {"SistemNo": "S-1", "Dosya No": "D-1",
         "OLAY TURU": "Tıbbi Olay", "hükümdeki rol": "Tek Gerekçe"},
    ], basliklar=["SistemNo", "Dosya No", "OLAY TURU", "hükümdeki rol"])

    satirlar, bulunanlar = xlsx_oku(paket)

    assert bulunanlar["olay_turu"] == "OLAY TURU"
    assert bulunanlar["hukumdeki_rol"] == "hükümdeki rol"
    assert satirlar[0].degerler["olay_turu"] == "Tıbbi Olay"
    assert satirlar[0].degerler["hukumdeki_rol"] == "Tek Gerekçe"


def test_eski_formatta_basliklar_yok_alan_okunmaz(tmp_path):
    """Toleransın öbür yüzü: başlık yoksa alan hiç okunmaz; serbest-metin
    "Tıbbi Olay" sütunu `olay_turu`ya ÇAPRAZ bağlanmaz."""
    paket = _paket_yaz(tmp_path / "t.xlsx",
                       [_satir("S-1", "D-1", **{"Tıbbi Olay": "Enfeksiyon"})])

    satirlar, bulunanlar = xlsx_oku(paket)

    assert "olay_turu" not in bulunanlar and "hukumdeki_rol" not in bulunanlar
    assert "olay_turu" not in satirlar[0].degerler
    assert satirlar[0].degerler["tibbi_olay"] == "Enfeksiyon"


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
            _kart(db, f"HA.G104.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    return db_env


def _kartlar(fabrika):
    db = fabrika()
    try:
        return {c.klasor_no_2: (c.olay_turu, c.hukumdeki_rol)
                for c in db.query(models.Case).all()}
    finally:
        db.close()


def test_basliksiz_paket_iki_alani_ellemiyor(db_env, tmp_path):
    """Kabul 1: başlık teslimde yoksa alan atlanır — DOLU değer boşalmaz,
    tarihçeye satır düşmez, koşu yeşil (eski paketle davranış birebir eski)."""
    db = db_env()
    try:
        _kart(db, "HA.G104.1", "D-1",
              olay_turu="Tıbbi Olay", hukumdeki_rol="Tek Gerekçe")
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
        assert (kart.olay_turu, kart.hukumdeki_rol) == ("Tıbbi Olay", "Tek Gerekçe")
        assert kart.tibbi_olay == "Enfeksiyon"
        alanlar = {h.field_name for h in db.query(models.CaseHistory).all()}
        assert not alanlar & {"olay_turu", "hukumdeki_rol"}
    finally:
        db.close()


def test_dry_run_iki_alan_farkta_gorunur_dbye_yazilmaz(iki_kart, tmp_path):
    """Kabul 2: kuru koşu iki alanı fark sayımında gösterir, hiçbir tabloya
    yazmaz (kart alanları + tarihçe + föy sıfır kalır)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "Belgeleme Olayı",
                                "Hükümdeki Rol": "Yan Gerekçe"}),
    ], basliklar=G104_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, dry_run=True,
                         rapor_dizini=tmp_path / "rapor")

    assert sonuc.dry_run and not sonuc.yazildi
    assert sonuc.alan_degisikligi == 2 and sonuc.kart_degisen == 1
    db = iki_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert (kart.olay_turu, kart.hukumdeki_rol) == (None, None)
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.CaseFoy).count() == 0
    finally:
        db.close()


def test_gecerli_deger_yazilir_taninmayan_rapora_duser(iki_kart, tmp_path):
    """Kabul 3: geçerli değerler KANONİK yazımla yazılır; "Aydınlatma" gibi
    listede olmayan değer yazılmaz, satır raporuna gerekçesiyle düşer —
    föyün DİĞER alanları normal işlenir (satır düşmez)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "TIBBİ OLAY",
                                "Hükümdeki Rol": "Reddedilmiş İddia"}),
        _satir("S-2", "D-2", **{"Olay Türü": "Aydınlatma",
                                "Tıbbi Olay": "Enfeksiyon"}),
    ], basliklar=G104_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI     # insan müdahalesi konusu
    assert sonuc.islenen == 2                         # satır DÜŞMEDİ
    assert len(sonuc.rapor_satirlari) == 1
    hata = sonuc.hatalar[0]
    assert hata.sistem_no == "S-2" and hata.tur == "HATA"
    assert "olay_turu yazılmadı" in hata.sebep and "Aydınlatma" in hata.sebep

    db = iki_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        # tolere yazım kanonik ada çözüldü (bizim yazımımız)
        assert kartlar["D-1"].olay_turu == "Tıbbi Olay"
        assert kartlar["D-1"].hukumdeki_rol == "Reddedilmiş İddia"
        # tanınmayan değer yazılmadı; satırın diğer alanı ve föyü İŞLENDİ
        assert kartlar["D-2"].olay_turu is None
        assert kartlar["D-2"].tibbi_olay == "Enfeksiyon"
        assert foy_map.get_foy(db, "S-2") is not None
    finally:
        db.close()

    rapor = [y for y in sonuc.raporlar if "satir-raporu" in y.name]
    assert rapor and "Aydınlatma" in rapor[0].read_text(encoding="utf-8-sig")


def test_karma_normalize_edilir_cok_rol_yazilmaz(iki_kart, tmp_path):
    """Kabul 4: ` ; ` ile {Tıbbi Olay, Belgeleme Olayı} → "Tıbbi + Belgeleme";
    hükümdeki rolde çok değer yazılmaz + rapora düşer."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "Tıbbi Olay ; Belgeleme Olayı"}),
        _satir("S-2", "D-2", **{"Hükümdeki Rol": "Tek Gerekçe ; Yan Gerekçe"}),
    ], basliklar=G104_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    kartlar = _kartlar(iki_kart)
    assert kartlar["D-1"] == ("Tıbbi + Belgeleme", None)
    assert kartlar["D-2"] == (None, None)
    assert len(sonuc.hatalar) == 1
    assert sonuc.hatalar[0].sistem_no == "S-2"
    assert "hukumdeki_rol yazılmadı" in sonuc.hatalar[0].sebep
    assert "çok değerli" in sonuc.hatalar[0].sebep


def test_ikinci_kosu_sifir_degisiklik_iki_alan_dahil(iki_kart, tmp_path):
    """Kabul 5: idempotency iki yeni alanı da kapsar — aynı girdiyle ikinci
    koşu 0 değişiklik, `case_history` şişmez."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "Tıbbi Olay",
                                "Hükümdeki Rol": "Yalnız Saptama"}),
        _satir("S-2", "D-2", **{"Olay Türü": "Belgeleme Olayı;Tıbbi Olay"}),
    ], basliklar=G104_BASLIKLAR)

    ilk = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM
    assert ilk.alan_degisikligi == 3 and ilk.kart_degisen == 2

    db = iki_kart()
    try:
        tarihce = db.query(models.CaseHistory).count()
        yazilan = {(h.field_name, h.old_value, h.new_value)
                   for h in db.query(models.CaseHistory)
                   if h.field_name in ("olay_turu", "hukumdeki_rol")}
        assert ("olay_turu", None, "Tıbbi Olay") in yazilan
        assert ("hukumdeki_rol", None, "Yalnız Saptama") in yazilan
        assert ("olay_turu", None, "Tıbbi + Belgeleme") in yazilan
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
    assert _kartlar(iki_kart) == {"D-1": ("Tıbbi Olay", "Yalnız Saptama"),
                                  "D-2": ("Tıbbi + Belgeleme", None)}


def test_kardes_foyler_ayri_satirlarda_uzlasmazsa_karma_uydurulmaz(iki_kart, tmp_path):
    """KARMA yalnız TEK hücrenin ` ; ` birleşimidir. Aynı kartın iki föyü AYRI
    satırlarda farklı tür anlatıyorsa bu kardeş-föy çelişkisidir: alan
    yazılmaz, çelişki raporuna düşer (kur'a/tahmin yok)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "Tıbbi Olay"}),
        _satir("S-2", "D-1", **{"Olay Türü": "Belgeleme Olayı"}),
    ], basliklar=G104_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    celiski = [c for c in sonuc.celiskiler if c.alan == "olay_turu"]
    assert len(celiski) == 1 and celiski[0].kume == "KART"
    assert "S-1=Tıbbi Olay" in celiski[0].degerler
    assert _kartlar(iki_kart)["D-1"] == (None, None)   # KARMA uydurulmadı


def test_dolu_hucre_metin_sinifiyla_uzerine_yazilir(iki_kart, tmp_path):
    """Sınıf kararı kilidi: iki alan METİN alanlarının VARSAYILAN sınıfında —
    içerik farkında teslim kazanır, tarihçeye eski→yeni düşer (İÇERİK modu
    gereksiz: dönüşüm çıktısı zaten kanonik ad, yalnız-yazım farkı oluşamaz)."""
    db = iki_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        kart.olay_turu = "Tıbbi Olay"
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("S-1", "D-1", **{"Olay Türü": "Belgeleme Olayı"}),
    ], basliklar=G104_BASLIKLAR)

    sonuc = aktarimi_kos(iki_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.alan_degisikligi == 1
    db = iki_kart()
    try:
        assert db.query(models.Case).filter_by(
            klasor_no_2="D-1").one().olay_turu == "Belgeleme Olayı"
        kayit = db.query(models.CaseHistory).filter_by(field_name="olay_turu").one()
        assert (kayit.old_value, kayit.new_value) == ("Tıbbi Olay", "Belgeleme Olayı")
    finally:
        db.close()
