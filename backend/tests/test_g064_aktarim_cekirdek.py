"""G064 — HUKDOK aktarımının çekirdek yazma yolu: idempotent iskelet + kuru
koşu + belge envanter denkliği.

İşletim modeli (FAZ F gereksinim belgesi §0): aktarım bir OLAY DEĞİL, TEKRAR
EDEN bir süreçtir — teslim partiler hâlinde gelecek, dört düzeltme listesi
yolda. "Aynı girdiyle iki kez koşulduğunda kayıt sayısı değişmez" bu yüzden
kabul kriterinin kendisidir.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ. Bütün
testler openpyxl ile SENTETİK mini paket üretir (uydurma satırlar, aynı sütun
başlıkları); gerçek paket yalnız çalışma zamanında `--input` ile okunur.

Katmanlar (test_g063 düzeni):

1. **Birim** — normalizasyon (D5 yer tutucu tarih, TR sayı), sütun eşleme,
   çelişki bulucu, kapsam kilitleri. DB yok.
2. **sqlite (StaticPool)** — uçtan uca koşu: idempotentlik, SAVEPOINT
   izolasyonu, kuru koşu, belge envanteri kapısı, UPDATE-in-place. Fixture
   migrasyonun index SQL'lerini OLDUĞU GİBİ uygular ve `PRAGMA
   foreign_keys=ON` ile FK aksiyonlarını açar (G049 dersi).
3. **dbtest (gerçek Postgres)** — 3-ortam kuralı: DATABASE_URL yoksa/şema
   göçmemişse (to_regclass) SKIP, FAIL değil. Yazımlar dış transaction'la
   TAMAMEN geri alınır.
"""
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from database import _MIGRATIONS, Base
from managers import foy_map
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    CIKIS_ENVANTER,
    CIKIS_SATIR_HATASI,
    CIKIS_TAMAM,
    AktarimHatasi,
    SatirHatasi,
    aktarimi_kos,
    celiskileri_bul,
    ozet_metni,
    xlsx_oku,
)
from services import belge_envanteri

# Sentetik paketin başlıkları — gerçek teslim paketiyle AYNI adlar, içerik
# tamamen uydurma.
BASLIKLAR = [
    "SistemNo", "TKU", "Hasar No", "Dosya No",
    "Arşiv Tarihi", "Islah Tutarı", "Tıbbi Olay", "Karar No", "Karar Tarihi",
]


def _paket_yaz(yol, satirlar, *, basliklar=None, sayfa="Föyler"):
    """Sentetik mini teslim paketi (.xlsx) üretir; satırlar sözlük listesidir."""
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
    """Tek föy satırı — varsayılanlar hep aynı ki testler farkı yazsın."""
    temel = {"SistemNo": sistem_no, "Dosya No": dosya_no, "TKU": "TKU-100"}
    temel.update(extra)
    return temel


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — normalizasyon, okuma, çelişki, kapsam kilitleri
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ham,beklenen", [
    ("SistemNo", "SISTEMNO"),
    ("Sistem No", "SISTEMNO"),
    ("  sistem  no ", "SISTEMNO"),
    ("Arşiv Tarihi", "ARSIVTARIHI"),
    ("ARSIV TARIHI", "ARSIVTARIHI"),
    ("Islah Tutarı", "ISLAHTUTARI"),
    ("İslah Tutarı", "ISLAHTUTARI"),
])
def test_baslik_anahtari_aksan_ve_bosluk_duyarsiz(ham, beklenen):
    """Teslim paketleri arasında yazım farkı var ("Islah"/"İslah"); başlık
    eşlemesi buna dayanmalı, yoksa sütun sessizce OKUNMAZ ve alan boş kalırdı."""
    assert hukdok_aktarim._baslik_anahtari(ham) == beklenen


@pytest.mark.parametrize("ham", ["01.01.1900", "1900-01-01", "-", "?", "yok", "BELİRSİZ"])
def test_yer_tutucu_tarihler_null_olur(ham):
    """D5: yer tutucu tarihler NULL (217 + 40 satır ölçüldü)."""
    assert hukdok_aktarim._tarih(ham, "arsiv_tarihi") is None


def test_gelecek_tarih_null_olur():
    """D5'in üçüncü sınıfı: gelecek tarihler (01.01.2030 ×3, 01.01.2027)."""
    gelecek = date.today() + timedelta(days=800)
    assert hukdok_aktarim._tarih(gelecek, "arsiv_tarihi") is None


@pytest.mark.parametrize("ham,beklenen", [
    ("15.03.2021", date(2021, 3, 15)),
    ("2021-03-15", date(2021, 3, 15)),
    ("15/03/2021", date(2021, 3, 15)),
    (datetime(2021, 3, 15, 10, 30), date(2021, 3, 15)),
    (date(2021, 3, 15), date(2021, 3, 15)),
    ("2021-03-15 00:00:00", date(2021, 3, 15)),   # METİN hücre + saat eki
    ("2021-03-15T10:30:00", date(2021, 3, 15)),
])
def test_gercek_tarihler_cozulur(ham, beklenen):
    assert hukdok_aktarim._tarih(ham, "arsiv_tarihi") == beklenen


def test_cozulemeyen_tarih_satiri_dusurur():
    """Bilinmeyen kusuru sessizce NULL'lamak onu karşı tarafın düzeltme
    listesinden gizlerdi — yer tutucular BİLİNEN sınıftır, bu değil."""
    with pytest.raises(SatirHatasi, match="çözümlenemedi"):
        hukdok_aktarim._tarih("31.02.2020", "arsiv_tarihi")


@pytest.mark.parametrize("ham,beklenen", [
    ("12.345,67", Decimal("12345.67")),
    ("1.500", Decimal("1500")),
    ("1500,50", Decimal("1500.50")),
    ("1500.50", Decimal("1500.50")),
    ("12.345,67 TL", Decimal("12345.67")),
    (1500, Decimal("1500")),
    (1500.5, Decimal("1500.5")),
])
def test_tr_bicimli_sayi_cozulur(ham, beklenen):
    """"12.345,67" (nokta binlik) ile "12345.67" aynı pakette yaşıyor."""
    assert hukdok_aktarim._sayi(ham, "islah_tutari") == beklenen


@pytest.mark.parametrize("ham", ["abc", "-500", True])
def test_gecersiz_sayi_satiri_dusurur(ham):
    with pytest.raises(SatirHatasi):
        hukdok_aktarim._sayi(ham, "islah_tutari")


def test_bos_deger_none_dondurur_bosaltma_yok():
    """`None` "bu teslimde yok" demektir, "boşalt" değil (foy_map sözleşmesi)."""
    assert hukdok_aktarim._metin("   ") is None
    assert hukdok_aktarim._tarih("", "arsiv_tarihi") is None
    assert hukdok_aktarim._sayi("", "islah_tutari") is None


def test_xlsx_okuma_basliklari_ve_satirlari_cozer(tmp_path):
    paket = _paket_yaz(tmp_path / "t.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021"}),
        {},                                               # tamamen boş satır: atlanır
        _satir("SSTMN-2", "D-2"),
    ])
    satirlar, basliklar = xlsx_oku(paket)

    assert [s.degerler["sistem_no"] for s in satirlar] == ["SSTMN-1", "SSTMN-2"]
    assert [s.satir_no for s in satirlar] == [2, 4]       # xlsx satır numarası korunur
    assert basliklar["sistem_no"] == "SistemNo"
    assert basliklar["arsiv_tarihi"] == "Arşiv Tarihi"


def test_xlsx_limit_ve_sayfa_secimi(tmp_path):
    paket = _paket_yaz(tmp_path / "t.xlsx",
                       [_satir(f"SSTMN-{i}", f"D-{i}") for i in range(1, 6)],
                       sayfa="Teslim")
    assert len(xlsx_oku(paket, limit=2)[0]) == 2
    assert len(xlsx_oku(paket, sheet="Teslim")[0]) == 5
    with pytest.raises(AktarimHatasi, match="Sayfa yok"):
        xlsx_oku(paket, sheet="Olmayan")


def test_sistem_no_sutunu_yoksa_kosu_hic_baslamaz(tmp_path):
    """Kimlik sütunu yoksa dosya bu script için okunamaz: yarım aktarım yerine
    gürültülü ret (foy_map'in `sistem_no` kırpmama kararıyla aynı akıl)."""
    paket = _paket_yaz(tmp_path / "t.xlsx", [{"Dosya No": "D-1"}],
                       basliklar=["Dosya No", "TKU"])
    with pytest.raises(AktarimHatasi, match="Zorunlu sütun"):
        xlsx_oku(paket)


def test_celiski_bulucu_kardes_foylerde_kunye_uyusmazligini_yakalar():
    """Tasarım paketi kanıtı: id-7189 K.2018/143 vs id-7190 K.2016/768 —
    aynı kartın iki föyü, farklı karar künyesi; kartta künye TEK SLOT."""
    celiskiler = celiskileri_bul([
        {"sistem_no": "id-7189", "case_id": 5, "tku_no": "TKU-784",
         "karar_no": "2018/143", "karar_tarihi": "2018-05-02"},
        {"sistem_no": "id-7190", "case_id": 5, "tku_no": "TKU-784",
         "karar_no": "2016/768", "karar_tarihi": "2018-05-02"},
    ])
    assert len(celiskiler) == 1
    assert celiskiler[0].kume == "KART" and celiskiler[0].kume_anahtari == "5"
    assert celiskiler[0].alan == "karar_no"
    assert "id-7189=2018/143" in celiskiler[0].degerler
    assert "id-7190=2016/768" in celiskiler[0].degerler


def test_celiski_bulucu_uyusan_foylerde_susar():
    assert celiskileri_bul([
        {"sistem_no": "id-1", "case_id": 5, "karar_no": "2018/143"},
        {"sistem_no": "id-2", "case_id": 5, "karar_no": "2018/143"},
        {"sistem_no": "id-3", "case_id": 5, "karar_no": None},      # boş çelişki değil
    ]) == []


def test_celiski_bulucu_kartsiz_satirlari_tku_ile_gruplar():
    """Eşleşmemiş satırların çelişkisi de karşı tarafa borçlu olduğumuz bulgu."""
    celiskiler = celiskileri_bul([
        {"sistem_no": "id-1", "case_id": None, "tku_no": "TKU-9", "karar_no": "A"},
        {"sistem_no": "id-2", "case_id": None, "tku_no": "TKU-9", "karar_no": "B"},
    ])
    assert [(c.kume, c.kume_anahtari) for c in celiskiler] == [("TKU", "TKU-9")]


def test_kapsam_kilidi_import_excel_cases_kullanilmiyor():
    """Görevin "dokunma" kalemi mekanik kilit: eski toplu-yazma scripti
    (idempotent değil, hata yolunda sessiz veri kaybı, `-2` mükerrer üretimi)
    ne çağrılır ne örnek alınır."""
    kaynak = Path(hukdok_aktarim.__file__).read_text(encoding="utf-8")
    assert "import_excel_cases" in kaynak, "kaynak dosyası okunamadı mı?"
    # Tek geçiş docstring'deki YASAK şerhidir; import/çağrı yok.
    assert kaynak.count("import_excel_cases") == 1
    assert "from scripts.import_excel_cases" not in kaynak
    assert "import import_excel_cases" not in kaynak


def test_kapsam_kilidi_ikinci_yazici_dogurmadi():
    """`cases.sistem_no`/`cases.tku_no` (nihai tekilleştirme: tam eşleme turu)
    ve karar künyesi (tek yazma yolu G062'nin aşama fotoğrafı) BU SCRIPTTEN
    yazılmaz; künye yalnız çelişki raporu için OKUNUR."""
    kaynak = Path(hukdok_aktarim.__file__).read_text(encoding="utf-8")
    for yasak in ("case.sistem_no", "case.tku_no", "case.karar_no", "case.karar_tarihi"):
        assert f"{yasak} =" not in kaynak, f"{yasak} kolonuna yazılıyor"
    yazilanlar = set(hukdok_aktarim.KART_ALANLARI) | set(hukdok_aktarim.KART_TURETILEN)
    # Künye + aşama kolonları hiçbir tura girmez: tek yazma yolu stage_decisions.
    assert not yazilanlar & {
        "karar_no", "karar_tarihi", "yerel_karar_durumu", "karar_teblig_tarihi",
        "istinaf_mahkemesi", "istinaf_esas_no", "istinaf_karar_no",
        "temyiz_mahkemesi", "temyiz_esas_no", "temyiz_karar_no",
        "karar_duzeltme_durumu", "sistem_no", "tku_no",
    }
    # Bilinçli yazılmayan: hizmet türünün 5 haneli bitmask semantiği kararlaşmadı.
    assert not yazilanlar & {"service_type"}
    # `court`/`sub_type` yazılır AMA yalnız içerik farkında (yazım bizim).
    assert hukdok_aktarim.ICERIK_KARSILASTIRMALI_ALANLAR == {"court", "sub_type"}
    # Toptan taraf silme belge-taraf bağını SESSİZCE koparırdı (SET NULL tuzağı)
    assert "delete(models.CaseParty" not in kaynak
    assert "CaseParty).delete" not in kaynak


def test_ozet_metni_envanter_durumunu_da_basar():
    sonuc = hukdok_aktarim.AktarimSonucu(okunan=3, islenen=3, kaynak_imzasi="X")
    metin = ozet_metni(sonuc)
    assert "okunan satır      : 3" in metin
    assert "belge envanteri DENK" in metin


# ═══════════════════════════════════════════════════════════════════════════
# 2. Belge envanteri (birim)
# ═══════════════════════════════════════════════════════════════════════════

def _envanter(**alanlar):
    temel = {"toplam": 2, "karta_bagli": 2, "tarafa_bagli": 1, "arsivli": 1,
             "silinmis": 0, "bag_imzasi": "abc"}
    temel.update(alanlar)
    return belge_envanteri.BelgeEnvanteri(**temel)


def test_envanter_diff_bos_sozluk_denklik_demektir():
    assert belge_envanteri.diff(_envanter(), _envanter()) == {}
    assert belge_envanteri.denk(_envanter(), _envanter())


def test_envanter_diff_degisen_alani_gosterir():
    fark = belge_envanteri.diff(_envanter(), _envanter(tarafa_bagli=0, bag_imzasi="xyz"))
    assert fark["tarafa_bagli"] == (1, 0)
    assert "bag_imzasi" in fark
    metin = belge_envanteri.bicimle(fark)
    assert "DENK DEĞİL" in metin and "tarafa_bagli: 1 → 0 (-1)" in metin


# ═══════════════════════════════════════════════════════════════════════════
# 3. Davranış — sqlite (kısıt + FK aksiyonları migrasyondan uygulanır, G049)
# ═══════════════════════════════════════════════════════════════════════════

def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


@pytest.fixture()
def db_env():
    """Paylaşılan in-memory sqlite + `case_foys` migrasyon index'leri + FK +
    ÇALIŞAN SAVEPOINT.

    Üçüncüsü bu görevin can damarı: pysqlite sürücüsü BEGIN'i kendi
    zamanlamasıyla yayar ve DML olmayan bir ifadeden (SAVEPOINT) hemen önce
    bekleyen transaction'ı ÖRTÜK COMMIT eder — savepoint'ler sahte çalışır,
    `rollback()` hiçbir şeyi geri almaz ve kuru koşu sessizce YAZARDI.
    SQLAlchemy'nin belgelediği reçete (isolation_level=None + elle BEGIN) bunu
    kapatır. Sürücü tuhaflığıdır: Postgres'te (prod) savepoint zaten doğru
    çalışır — bkz. dbtest bölümü, aynı akış gerçek şemada da ölçülür.
    """
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


def _sayimlar(fabrika):
    """Bütün ilgili tabloların satır sayıları — kuru koşunun kanıtı."""
    db = fabrika()
    try:
        return {
            model.__name__: db.query(model).count()
            for model in (models.Case, models.CaseFoy, models.CaseHistory,
                          models.CaseParty, models.CaseDocument)
        }
    finally:
        db.close()


def _kart_fotografi(fabrika):
    """Kartların ölçülen alanları — "cases diff'i" kabul kriterinin ölçümü."""
    db = fabrika()
    try:
        return {
            c.id: (c.arsiv_tarihi, c.islah_tutari, c.tibbi_olay, c.karar_no,
                   c.missing_required_bucket, c.klasor_no_2)
            for c in db.query(models.Case).all()
        }
    finally:
        db.close()


@pytest.fixture()
def uc_kart(db_env):
    """Üç kart (D-1/D-2/D-3) — teslim paketinin eşleşeceği zemin."""
    db = db_env()
    try:
        for i in (1, 2, 3):
            _kart(db, f"HA.G064.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    return db_env


def test_ilk_kosu_yazar_ikinci_kosu_hicbir_sey_degistirmez(uc_kart, tmp_path):
    """Kabul kriteri: aynı girdiyle ikinci koşu 0 değişiklik — case_foys satır
    sayısı, cases diff'i ve case_history büyümesi ÜÇÜ DE ölçülür."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021",
                                    "Islah Tutarı": "12.345,67", "Hasar No": "H-1"}),
        _satir("SSTMN-2", "D-2", **{"Tıbbi Olay": "Ameliyat  sonrası   enfeksiyon"}),
        _satir("SSTMN-3", "D-3"),
        _satir("SSTMN-9", "D-YOK"),                      # köprüde karşılığı yok
    ])

    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM                 # atlanan satır kırmızı DEĞİL
    assert (ilk.foy_yeni, ilk.foy_guncellenen, ilk.atlanan) == (3, 0, 1)
    assert ilk.yazildi and not ilk.envanter_farki

    sayim_sonrasi = _sayimlar(uc_kart)
    fotograf_sonrasi = _kart_fotografi(uc_kart)
    assert sayim_sonrasi["CaseFoy"] == 3

    # Yazılan değerler gerçekten kartta (normalize edilmiş hâlleriyle)
    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].arsiv_tarihi == date(2021, 3, 15)
        assert kartlar["D-1"].islah_tutari == Decimal("12345.67")
        assert kartlar["D-2"].tibbi_olay == "Ameliyat sonrası enfeksiyon"
        assert foy_map.get_foy(db, "SSTMN-1").hasar_no == "H-1"
        assert foy_map.get_foy(db, "SSTMN-9") is None     # eşleşmeyen satır YAZILMADI
    finally:
        db.close()

    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert (ikinci.foy_yeni, ikinci.foy_guncellenen) == (0, 3)
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0
    assert _sayimlar(uc_kart) == sayim_sonrasi            # case_foys + case_history sabit
    assert _kart_fotografi(uc_kart) == fotograf_sonrasi   # cases diff'i boş


def test_bozuk_satir_izole_kalan_satirlar_islenir(uc_kart, tmp_path):
    """Kabul kriteri: ortadaki satır bilinçli bozuk → o satır rapora düşer,
    kalanlar İŞLENİR. SAVEPOINT'in kanıtı: bozuk satırın föyü de yazılmamıştır
    (föy upsert'i alan doğrulamasından ÖNCE gelir)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1"),
        _satir("SSTMN-2", "D-2", **{"Arşiv Tarihi": "31.02.2020"}),   # geçersiz tarih
        _satir("SSTMN-3", "D-3"),
    ])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    assert sonuc.islenen == 2 and sonuc.foy_yeni == 2
    assert [(h.satir_no, h.sistem_no) for h in sonuc.hatalar] == [(3, "SSTMN-2")]
    assert "çözümlenemedi" in sonuc.hatalar[0].sebep

    db = uc_kart()
    try:
        assert {f.sistem_no for f in db.query(models.CaseFoy).all()} == {"SSTMN-1", "SSTMN-3"}
        # Yarım yazım kalmadı: bozuk satırın kartına tarihçe de düşmedi
        bozuk_kart = db.query(models.Case).filter_by(klasor_no_2="D-2").one()
        assert db.query(models.CaseHistory).filter_by(case_id=bozuk_kart.id).count() == 0
        assert bozuk_kart.arsiv_tarihi is None
    finally:
        db.close()

    rapor = [y for y in sonuc.raporlar if "satir-raporu" in y.name]
    assert rapor and "SSTMN-2" in rapor[0].read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("ham,beklenen", [
    ("624.001.00;3.137.00", ["624.001.00", "3.137.00"]),
    ("1077.001.00;1078.001.00;1.20816.00", ["1077.001.00", "1078.001.00", "1.20816.00"]),
    (" 9.070.00 ", ["9.070.00"]),
    ("A-1;a-1", ["A-1"]),                       # aynı parça iki kez sayılmaz
    (None, []),
])
def test_cok_degerli_dosya_no_parcalanir(ham, beklenen):
    """`klasor_no_2` ';' ile birleşik tutulur; lokal prod kopyasında 14.317
    dolu kaydın 1.267'si çok değerli — ve bunlar tam da BİRLEŞİK kartlar."""
    assert hukdok_aktarim._dosya_no_parcalari(ham) == beklenen


def test_birlesik_kart_parcalanmis_dosya_no_ile_eslesir(db_env, tmp_path):
    """Birleşik kart (2+ föy) çekirdek vaka: teslim tek numara yazar, kartta o
    numara ';' ile birleşik durur. Tam-değer eşleşmesi bu kartı ıskalardı."""
    db = db_env()
    try:
        _kart(db, "HA.G064.BIRLESIK", "624.001.00;3.137.00")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "3.137.00"),                   # ikinci parça
        _satir("SSTMN-2", "624.001.00"),                 # ilk parça — AYNI kart
    ])

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.foy_yeni == 2
    db = db_env()
    try:
        kart = db.query(models.Case).one()
        assert len(foy_map.get_case_foys(db, kart.id)) == 2   # iki föy TEK kartta
    finally:
        db.close()


def test_belirsiz_eslesme_yanlis_karta_yazmaz(db_env, tmp_path):
    """112 mükerrer `klasor_no_2` grubu var (14.317 dolu / 14.204 distinct);
    çok eşleşen satır yanlış karta yazmaktansa rapora düşer."""
    db = db_env()
    try:
        _kart(db, "HA.G064.A", "D-AYNI")
        _kart(db, "HA.G064.B", "D-AYNI")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [_satir("SSTMN-1", "D-AYNI")])

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    assert "Belirsiz eşleşme" in sonuc.hatalar[0].sebep
    assert _sayimlar(db_env)["CaseFoy"] == 0


def test_ikinci_anahtar_esas_ve_tur_ile_belirsizligi_cozer(db_env, tmp_path):
    """Belirsizliğin tipik hâli ikiz kartlarımız: aynı klasör no hem dava hem
    arabuluculuk kartında. Föyün Ana Tür + Esas'ı hangisi olduğunu söyler
    (257 belirsiz satırın 223'ü bu iki kriterle çözülüyor, ölçüldü)."""
    db = db_env()
    try:
        _kart(db, "HA.G064.H", "D-IKIZ", file_type="Hukuk", esas_no="2023/449")
        _kart(db, "HA.G064.A", "D-IKIZ", file_type="Arabuluculuk", esas_no="2023/166")
        _kart(db, "HA.G064.X", "D-KOR", file_type="Hukuk")
        _kart(db, "HA.G064.Y", "D-KOR", file_type="Hukuk")
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("H-1", "D-IKIZ", **{"Ana Tür": "HUKUK", "Esas": "2023/449"}),
        _satir("ARB-1", "D-IKIZ", **{"Ana Tür": "ARABULUCULUK", "Esas": "2023/166"}),
        _satir("H-9", "D-KOR", **{"Ana Tür": "HUKUK"}),      # ikisi de aynı: ayrılmaz
    ], basliklar=BASLIKLAR + ["Ana Tür", "Esas"])

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = db_env()
    try:
        kartlar = {c.tracking_no: c for c in db.query(models.Case).all()}
        assert foy_map.get_foy(db, "H-1").case_id == kartlar["HA.G064.H"].id
        assert foy_map.get_foy(db, "ARB-1").case_id == kartlar["HA.G064.A"].id
        assert foy_map.get_foy(db, "H-9") is None            # ayrılamayan YAZILMADI
    finally:
        db.close()
    assert len(sonuc.hatalar) == 1 and "esas/tür de ayırmadı" in sonuc.hatalar[0].sebep


def test_dry_run_hicbir_tabloya_yazmaz(uc_kart, tmp_path):
    """Kabul kriteri: `--dry-run` hiçbir tabloya yazmaz — öncesi/sonrası TÜM
    sayımlar ve kart alanları eşit; ürünü rapordur."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021"}),
        _satir("SSTMN-2", "D-2"),
        _satir("SSTMN-9", "D-YOK"),
    ])
    once_sayim, once_fotograf = _sayimlar(uc_kart), _kart_fotografi(uc_kart)

    sonuc = aktarimi_kos(uc_kart, girdi=paket, dry_run=True, rapor_dizini=tmp_path / "rapor")

    assert sonuc.dry_run and not sonuc.yazildi
    assert sonuc.foy_yeni == 2                 # yazılacak OLAN sayılır (kuru koşunun bilgisi)
    assert _sayimlar(uc_kart) == once_sayim
    assert _kart_fotografi(uc_kart) == once_fotograf
    assert sonuc.raporlar and sonuc.raporlar[0].exists()


@pytest.fixture()
def belgeli_kart(db_env):
    """Kart + taraf + o tarafa bağlı işlenmiş belge (koruma şartının zemini)."""
    db = db_env()
    try:
        case = _kart(db, "HA.G064.B1", "D-1")
        taraf = models.CaseParty(case_id=case.id, name="Ali V.", role="Davacı",
                                 party_type="CLIENT")
        db.add(taraf)
        db.flush()
        db.add(models.CaseDocument(
            case_id=case.id, case_party_id=taraf.id,
            original_filename="tensip.pdf", stored_filename="TENSIP.pdf",
            sharepoint_url="https://sp/tensip.pdf", link_mode="LINKED",
        ))
        db.commit()
        return db_env, case.id, taraf.id
    finally:
        db.close()


def test_normal_kosuda_belge_envanteri_denk_kalir(belgeli_kart, tmp_path):
    """Kabul kriteri: belgeli kart senaryosunda koşu sonrası envanter BİREBİR
    denk; belge-taraf bağı kımıldamaz."""
    fabrika, case_id, taraf_id = belgeli_kart
    paket = _paket_yaz(tmp_path / "teslim.xlsx",
                       [_satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021"})])

    sonuc = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.envanter_farki == {}
    assert sonuc.envanter_once == sonuc.envanter_sonra
    db = fabrika()
    try:
        belge = db.query(models.CaseDocument).one()
        assert (belge.case_id, belge.case_party_id) == (case_id, taraf_id)
        assert db.query(models.CaseParty).count() == 1      # taraf silinmedi
    finally:
        db.close()


def test_belge_bagi_koparsa_kosu_geri_alinir_ve_nonzero_doner(belgeli_kart, tmp_path,
                                                              monkeypatch):
    """Kabul kriteri: script bilerek bozulursa NONZERO + fark raporu.

    Bozulma `case_party_id`'nin SET NULL ile kopması olarak taklit edilir
    (models.py:770 tuzağının tam sınıfı). Kapı commit'ten ÖNCE ölçtüğü için
    koşu geri alınır: belge bağı YERİNDE kalır, föy de yazılmaz."""
    fabrika, case_id, taraf_id = belgeli_kart
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [_satir("SSTMN-1", "D-1")])
    gercek = hukdok_aktarim._kart_alanlarini_yaz

    def _bagi_kopar(db, case, satir, source, **kwargs):
        db.query(models.CaseDocument).filter(
            models.CaseDocument.case_id == case.id
        ).update({"case_party_id": None}, synchronize_session=False)
        return gercek(db, case, satir, source, **kwargs)

    monkeypatch.setattr(hukdok_aktarim, "_kart_alanlarini_yaz", _bagi_kopar)

    sonuc = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_ENVANTER
    assert sonuc.envanter_farki["tarafa_bagli"] == (1, 0)
    assert "bag_imzasi" in sonuc.envanter_farki
    assert not sonuc.yazildi
    db = fabrika()
    try:
        assert db.query(models.CaseDocument).one().case_party_id == taraf_id
        assert db.query(models.CaseFoy).count() == 0        # koşu tamamen geri alındı
    finally:
        db.close()


def test_mevcut_kart_update_in_place_kimlikler_sabit(belgeli_kart, tmp_path):
    """Kabul kriteri: kart id'si değişmiyor, `case_parties` satırları
    silinmiyor (DELETE+INSERT yasak)."""
    fabrika, case_id, taraf_id = belgeli_kart
    paket = _paket_yaz(tmp_path / "teslim.xlsx",
                       [_satir("SSTMN-1", "D-1", **{"Tıbbi Olay": "Enfeksiyon"})])

    aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = fabrika()
    try:
        kart = db.query(models.Case).one()
        assert kart.id == case_id and kart.tibbi_olay == "Enfeksiyon"
        assert [p.id for p in db.query(models.CaseParty).all()] == [taraf_id]
        assert foy_map.get_foy(db, "SSTMN-1").case_id == case_id
    finally:
        db.close()


def test_aktarim_imzasi_ve_eksik_alan_kovasi(uc_kart, tmp_path):
    """D8/K1: aktarım kaynaklı kayıt eksik-alan filtresinde AYRI kovada durur.
    İmza `case_history.source`ta yaşar (ikinci bayrak tutulmaz) — alanı hiç
    değişmeyen kart da föy eşlemesiyle imzalanır, yoksa "elle açılmış" kovada
    görünürdü."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [_satir("SSTMN-3", "D-3")])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.kaynak_imzasi.startswith("HUKDOK_TESLIM")
    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-3").one()
        kayit = db.query(models.CaseHistory).filter_by(case_id=kart.id).one()
        assert kayit.field_name == "case_foys.sistem_no"
        assert kayit.new_value == "SSTMN-3"
        assert kayit.source == sonuc.kaynak_imzasi
        assert kayit.changed_by == "hukdok_aktarim"
        assert kart.missing_required_bucket == "AKTARIM"
    finally:
        db.close()


def test_alan_degisikligi_tarihceye_eski_yeni_ile_dusuyor(uc_kart, tmp_path):
    """Provenance imzası alan bazında da izlenebilir olmalı: hangi teslim
    hangi değeri değiştirdi?"""
    ilk = _paket_yaz(tmp_path / "ilk.xlsx",
                     [_satir("SSTMN-1", "D-1", **{"Tıbbi Olay": "Enfeksiyon"})])
    aktarimi_kos(uc_kart, girdi=ilk, rapor_dizini=tmp_path / "rapor")

    duzeltme = _paket_yaz(tmp_path / "duzeltme.xlsx",
                          [_satir("SSTMN-1", "D-1", **{"Tıbbi Olay": "Kanama"})])
    sonuc = aktarimi_kos(uc_kart, girdi=duzeltme, rapor_dizini=tmp_path / "rapor")

    assert sonuc.alan_degisikligi == 1 and sonuc.kart_degisen == 1
    db = uc_kart()
    try:
        kayitlar = (
            db.query(models.CaseHistory)
            .filter_by(field_name="tibbi_olay")
            .order_by(models.CaseHistory.id)
            .all()
        )
        # İlk teslim boş alanı doldurdu, düzeltme listesi değiştirdi: iki satır
        assert [(k.old_value, k.new_value) for k in kayitlar] == [
            (None, "Enfeksiyon"), ("Enfeksiyon", "Kanama"),
        ]
        kayit = kayitlar[-1]
        assert kayit.source.endswith("duzeltme.xlsx")
        assert db.query(models.Case).filter_by(klasor_no_2="D-1").one().tibbi_olay == "Kanama"
    finally:
        db.close()


def test_verilmeyen_alan_korunur_bosaltilmaz(uc_kart, tmp_path):
    """Partili teslimde eksik sütun mevcut değeri SİLMEZ (foy_map sözleşmesi)."""
    ilk = _paket_yaz(tmp_path / "ilk.xlsx",
                     [_satir("SSTMN-1", "D-1", **{"Tıbbi Olay": "Enfeksiyon",
                                                  "Arşiv Tarihi": "15.03.2021"})])
    aktarimi_kos(uc_kart, girdi=ilk, rapor_dizini=tmp_path / "rapor")

    eksik = _paket_yaz(tmp_path / "eksik.xlsx", [_satir("SSTMN-1", "D-1")])
    sonuc = aktarimi_kos(uc_kart, girdi=eksik, rapor_dizini=tmp_path / "rapor")

    assert sonuc.alan_degisikligi == 0
    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert kart.tibbi_olay == "Enfeksiyon" and kart.arsiv_tarihi == date(2021, 3, 15)
    finally:
        db.close()


def test_yer_tutucu_tarih_satiri_dusurmez_alani_bos_birakir(uc_kart, tmp_path):
    paket = _paket_yaz(tmp_path / "teslim.xlsx",
                       [_satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "01.01.1900",
                                                    "Tıbbi Olay": "Enfeksiyon"})])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.islenen == 1
    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert kart.arsiv_tarihi is None and kart.tibbi_olay == "Enfeksiyon"
    finally:
        db.close()


def test_kardes_foy_celiskisi_raporlaniyor_kunye_yazilmiyor(uc_kart, tmp_path):
    """Kabul kriteri: sentetik çelişen iki kardeş föy → rapor satırı üretiliyor.
    Künye kartın TEK SLOT'una YAZILMAZ (tek yazma yolu G062'nin fotoğrafı)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-7189", "D-1", **{"Karar No": "2018/143", "TKU": "TKU-784"}),
        _satir("id-7190", "D-1", **{"Karar No": "2016/768", "TKU": "TKU-784"}),
    ])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert len(sonuc.celiskiler) == 1 and sonuc.celiskiler[0].alan == "karar_no"
    rapor = [y for y in sonuc.raporlar if "kardes-foy" in y.name]
    icerik = rapor[0].read_text(encoding="utf-8-sig")
    assert "id-7189=2018/143" in icerik and "id-7190=2016/768" in icerik
    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert kart.karar_no is None                     # ikinci yazıcı doğmadı
        assert len(foy_map.get_case_foys(db, kart.id)) == 2   # iki föy TEK kartta
    finally:
        db.close()


def test_yazilan_alanlarin_hepsi_gercek_kart_kolonu():
    """Eşleme sözlüğündeki her anahtar `Case` modelinde VAR olmalı.

    Bekçi sebebi: DB'de modelde KARŞILIĞI OLMAYAN kolonlar da var (`last_status`
    eski kalıntı). Sözlüğe öylesi bir ad yazılırsa hata koşu ortasında
    `AttributeError` olarak patlar — burada saniyesinde yakalanır.
    """
    kolonlar = {c.name for c in models.Case.__table__.columns}
    yazilanlar = set(hukdok_aktarim.KART_ALANLARI) | set(hukdok_aktarim.KART_TURETILEN)
    assert yazilanlar <= kolonlar, f"modelde yok: {sorted(yazilanlar - kolonlar)}"
    # Kaynak sütun anahtarları da okunabilir olmalı (SUTUN_ADAYLARI'nda tanımlı)
    kaynaklar = {kaynak for kaynak, _ in hukdok_aktarim.KART_ALANLARI.values()}
    assert kaynaklar <= set(hukdok_aktarim.SUTUN_ADAYLARI)


def test_tam_esleme_kart_alanlarini_yaziyor(uc_kart, tmp_path):
    """Tam eşleme turu: sınıflandırma + tarih + para + tıbbi alanlar kartta."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{
            "Ana Tür": "İDARE", "Durum": "Arşiv", "Dava Konusu": "Tazminat (Tıbbi Kötü Uygulama)",
            "Dava Tarihi": "03.01.2023", "Dava Değeri TL": "250.000,00",
            "Manevi Dava Değeri TL": "100.000,00", "Son Durum": "Kesin Lehe",
            "Hukuk No": "460592", "Hasar No": "3509162150001",
            "İddia Edilen Kusur": "Tanı Hatası", "Uygulanan Yöntem": "Sezaryen",
            "İstinaf Mahkemesi Başvuran Taraf": "DAVALI-DAVACI",
        }),
    ], basliklar=BASLIKLAR + ["Ana Tür", "Durum", "Dava Konusu", "Dava Tarihi",
                              "Dava Değeri TL", "Manevi Dava Değeri TL", "Son Durum",
                              "Hukuk No", "İddia Edilen Kusur", "Uygulanan Yöntem",
                              "İstinaf Mahkemesi Başvuran Taraf"])

    aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert kart.file_type == "İdare" and kart.status == "MAHZEN"
        assert kart.subject == "Tazminat (Tıbbi Kötü Uygulama)"
        assert kart.opening_date == date(2023, 1, 3)
        assert kart.manevi_tazminat == Decimal("100000")
        assert kart.maddi_tazminat == Decimal("150000")     # D4: 250.000 − 100.000
        assert kart.dosya_son_durumu == "Kesin Lehe"
        assert (kart.hukuk_no, kart.hasar_dosya_no) == ("460592", "3509162150001")
        assert kart.iddia_edilen_kusur == "Tanı Hatası"
        assert kart.istinaf_basvuran_taraf == "Her İki Taraf"   # birleşik yazım
    finally:
        db.close()


def test_d4_manevi_dava_degerini_asarsa_maddi_yazilmaz(uc_kart, tmp_path):
    """D4: manevi > dava değeri olan 98 satırda maddi UYDURULMAZ, NULL kalır."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Dava Değeri TL": "50000", "Manevi Dava Değeri TL": "80000"}),
        _satir("SSTMN-2", "D-2", **{"Dava Değeri TL": "80000", "Manevi Dava Değeri TL": "80000"}),
    ], basliklar=BASLIKLAR + ["Dava Değeri TL", "Manevi Dava Değeri TL"])

    aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].maddi_tazminat == Decimal("0")  # dokunulmadı (model default)
        yazilan = {h.field_name for h in db.query(models.CaseHistory).all()}
        assert "maddi_tazminat" not in yazilan or kartlar["D-2"].maddi_tazminat == Decimal("0")
        assert kartlar["D-2"].maddi_tazminat == Decimal("0")  # 0 DOĞRU (NULL ≠ 0)
    finally:
        db.close()


def test_kapali_liste_taninmayan_degeri_yazmaz(uc_kart, tmp_path):
    """Teslimde 17 yazım var, bizim liste üç değerli — eşlemesi olmayan BOŞ kalır."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"İstinaf Mahkemesi Başvuran Taraf": "SANIK MÜDAFİ"}),
        _satir("SSTMN-2", "D-2", **{"Ana Tür": "BİLİNMEYEN TÜR"}),
    ], basliklar=BASLIKLAR + ["İstinaf Mahkemesi Başvuran Taraf", "Ana Tür"])

    aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].istinaf_basvuran_taraf is None
        assert kartlar["D-2"].file_type is None               # uydurma tür yazılmadı
    finally:
        db.close()


def test_icerik_farkinda_yazilir_yazim_farkinda_yazilmaz(uc_kart, tmp_path):
    """`court`/`sub_type`: içerik teslimin, yazım bizim.

    Ölçüm (2026-08-19): `court`ta 562 farkın 480'i yalnız BÜYÜK HARF/noktalama,
    82'si gerçekten başka mahkeme; `sub_type`ta 7.390 farkın 7.039'u yazım.
    Yazımı da üstüne yazmak G067-G070'te düzeltilen mahkeme adı kimliğini ve
    referans listelerinin `tr_title` formatını geriletirdi.
    """
    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        kartlar["D-1"].court = "Bakırköy 3. Tüketici Mahkemesi"
        kartlar["D-1"].sub_type = "Ortopedi Ve Travmatoloji"
        kartlar["D-3"].court = "İzmir 4. İdare Mahkemesi"
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        # yalnız yazım farkı → dokunulmaz
        _satir("SSTMN-1", "D-1", **{"Yerel Mahkeme": "BAKIRKÖY 3. TÜKETİCİ MAHKEMESİ",
                                    "Dava Türü Alt Kırılımı": "ORTOPEDİ VE TRAVMATOLOJİ"}),
        # kart boştu → dolar (BÜYÜK HARF gelen uzmanlık `tr_title`e çevrilir)
        _satir("SSTMN-2", "D-2", **{"Yerel Mahkeme": "ANKARA 9. TÜKETİCİ MAHKEMESİ",
                                    "Dava Türü Alt Kırılımı": "ÇOCUK SAĞLIĞI VE HASTALIKLARI"}),
        # GERÇEK içerik farkı → teslim kazanır
        _satir("SSTMN-3", "D-3", **{"Yerel Mahkeme": "İzmir 15. Asliye Hukuk Mahkemesi"}),
    ], basliklar=BASLIKLAR + ["Yerel Mahkeme", "Dava Türü Alt Kırılımı"])

    aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].court == "Bakırköy 3. Tüketici Mahkemesi"   # yazım: korundu
        assert kartlar["D-1"].sub_type == "Ortopedi Ve Travmatoloji"      # yazım: korundu
        assert kartlar["D-2"].court == "ANKARA 9. TÜKETİCİ MAHKEMESİ"     # boştu, doldu
        assert kartlar["D-2"].sub_type == "Çocuk Sağlığı Ve Hastalıkları"  # tr_title
        assert kartlar["D-3"].court == "İzmir 15. Asliye Hukuk Mahkemesi"  # içerik: değişti
    finally:
        db.close()


def test_esas_kolonu_tarihce_yolundan_yazilir(uc_kart, tmp_path):
    """`esas_no` TÜRETİLMİŞ (G045): setattr değil `sync_current_esas`."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Esas": "2023/1660", "Yerel Mahkeme": "Şanlıurfa 1. Tüketici Mahkemesi"}),
    ], basliklar=BASLIKLAR + ["Esas", "Yerel Mahkeme"])

    aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        assert kart.esas_no == "2023/1660"
        satirlar = db.query(models.CaseEsasNumber).filter_by(case_id=kart.id).all()
        assert len(satirlar) == 1 and satirlar[0].is_current
        assert satirlar[0].court == "Şanlıurfa 1. Tüketici Mahkemesi"
    finally:
        db.close()


def test_taraflar_yalniz_eklenir_mevcut_satira_dokunulmaz(belgeli_kart, tmp_path):
    """Belge koruma şartı: mevcut taraf satırı GÜNCELLENMEZ/SİLİNMEZ, yalnız
    eksik ad eklenir. `case_documents.case_party_id` SET NULL olduğu için
    toptan yeniden yazma belge-taraf bağını sessizce koparırdı."""
    fabrika, case_id, taraf_id = belgeli_kart
    db = fabrika()
    try:
        mevcut = db.get(models.CaseParty, taraf_id)
        mevcut_ad, mevcut_rol = mevcut.name, mevcut.role
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{
            "Müvekkil": mevcut_ad,                       # zaten var → eklenmez
            "Karşı Taraf": "Turgut Keser; Ramazan Keser",  # ikisi de yeni
            "Sigortalı": "AK SİGORTA A.Ş.",
            "Taraf Sıfatı": "Feri Müdahil",
        }),
    ], basliklar=BASLIKLAR + ["Müvekkil", "Karşı Taraf", "Sigortalı", "Taraf Sıfatı"])

    ilk = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.taraf_eklenen == 3 and not ilk.envanter_farki

    db = fabrika()
    try:
        korunan = db.get(models.CaseParty, taraf_id)
        assert (korunan.name, korunan.role) == (mevcut_ad, mevcut_rol)   # DOKUNULMADI
        yeni = {p.name: (p.party_type, p.role)
                for p in db.query(models.CaseParty).filter(models.CaseParty.id != taraf_id)}
        assert yeni["Turgut Keser"] == ("COUNTER", "Karşı Taraf")
        assert yeni["AK SİGORTA A.Ş."] == ("THIRD", "Sigortalı")      # D1
        assert db.query(models.CaseDocument).one().case_party_id == taraf_id
    finally:
        db.close()

    ikinci = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.taraf_eklenen == 0                    # idempotent


def test_avukat_listesi_case_lawyers_satirlarina_acilir(uc_kart, tmp_path):
    """Teslimde "Sorumlu Avukatlar" bir LİSTE; bizde tek kutu + `case_lawyers`.

    Tek isimli föy kartın `responsible_lawyer_name`ini de yazar; çoklu föy
    YAZMAZ (hangisi sorumlu belli değil) ama isimlerin hepsi satır olur.
    Yazım teslimin aksansız hâli değil BİZİM kayıtlı yazımımızdır.
    """
    db = uc_kart()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-3").one()
        kart.responsible_lawyer_name = "Tuğçe Üngör Yanık"     # doğru yazım kaynağı
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Sorumlu Avukatlar": "Tugce Ungor Yanık,"}),
        _satir("SSTMN-2", "D-2", **{"Sorumlu Avukatlar": "Ayse Acar Yucel, Barıs Yucel,"}),
    ], basliklar=BASLIKLAR + ["Sorumlu Avukatlar"])

    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.avukat_eklenen == 3                     # 1 + 2 isim

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        # tek isim → kart alanı da yazıldı, BİZİM yazımımızla
        assert kartlar["D-1"].responsible_lawyer_name == "Tuğçe Üngör Yanık"
        # çoklu isim → kart alanı yazılmadı, satırlar açıldı
        assert kartlar["D-2"].responsible_lawyer_name is None
        adlar = {r.name for r in db.query(models.CaseLawyer).filter_by(case_id=kartlar["D-2"].id)}
        assert adlar == {"Ayse Acar Yucel", "Barıs Yucel"}
    finally:
        db.close()

    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.avukat_eklenen == 0 and ikinci.alan_degisikligi == 0
    db = uc_kart()
    try:
        assert db.query(models.CaseLawyer).count() == 3    # satır İKİLENMEDİ
    finally:
        db.close()


def test_kardes_foyler_kart_alaninda_uzlasmazsa_alan_yazilmaz(uc_kart, tmp_path):
    """19.08 provasının bulgusu: kart alanı TEK SLOT, föy ise kart başına çok.

    Satır satır yazınca kartta "en son işlenen föy" kalıyor ve ikinci koşuda
    başka föy kazanıp alan SALINIYORDU (gerçek koşuda kart#195: 12 föyün
    ikisi farklı Arşiv Tarihi taşıyor → 2. ve 3. koşu her seferinde 6
    değişiklik). Uzlaşmayan alan artık YAZILMAZ, rapora düşer.
    """
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-9899", "D-1", **{"Arşiv Tarihi": "12.07.2023", "Hasar No": "H-A"}),
        _satir("id-9902", "D-1", **{"Arşiv Tarihi": "07.06.2017", "Hasar No": "H-B"}),
        _satir("id-9908", "D-1", **{"Arşiv Tarihi": "12.07.2023"}),
        _satir("SSTMN-2", "D-2", **{"Arşiv Tarihi": "15.03.2021"}),   # uzlaşan kart
    ])

    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    celiski = [c for c in ilk.celiskiler if c.alan == "arsiv_tarihi"]
    assert len(celiski) == 1 and celiski[0].kume == "KART"
    assert "id-9902=2017-06-07" in celiski[0].degerler

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].arsiv_tarihi is None          # kur'a çekilmedi
        assert kartlar["D-2"].arsiv_tarihi == date(2021, 3, 15)   # uzlaşan yazıldı
        # Föyler yine de asıldı: çelişki kartı yazmayı engeller, kimliği DEĞİL.
        assert len(foy_map.get_case_foys(db, kartlar["D-1"].id)) == 3
        assert foy_map.get_foy(db, "id-9902").hasar_no == "H-B"
    finally:
        db.close()

    fotograf = _kart_fotografi(uc_kart)
    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0
    assert _kart_fotografi(uc_kart) == fotograf             # salınım bitti


def test_kart_degisen_ayni_kartin_iki_foyunu_tek_kart_sayar(uc_kart, tmp_path):
    """Özet satırındaki "N kart" KART sayar, satır değil (provada 52 kart
    "58 kart" diye raporlanmıştı)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Islah Tutarı": "1.000,00"}),
        _satir("SSTMN-2", "D-1", **{"Tıbbi Olay": "Enfeksiyon"}),
    ])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.alan_degisikligi == 2      # iki ayrı alan yazıldı
    assert sonuc.kart_degisen == 1          # ama TEK kartta


def test_klasor_no_basligi_tku_grup_anahtari_olarak_okunur(tmp_path):
    """Teslim paketinde TKU'nun başlığı "Klasör No"dur; aday listesi bunu
    tanımazsa föyler tku_no'suz doğar (19.08 provasında 90/90 boştu)."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        {"SistemNo": "SSTMN-1", "Klasör No": "TKU-784", "DosyaNo": "D-1"},
    ], basliklar=["SistemNo", "Klasör No", "DosyaNo"])

    satirlar, bulunanlar = xlsx_oku(paket)

    assert bulunanlar["tku_no"] == "Klasör No"
    assert satirlar[0].degerler["tku_no"] == "TKU-784"
    assert bulunanlar["dosya_no"] == "DosyaNo"      # KLASORNO ≠ KLASORNO2


def test_ayni_paketteki_mukerrer_sistem_no_satir_ikilemiyor(uc_kart, tmp_path):
    """Aynı dosyada iki kez geçen SistemNo: ikinci satır föyü günceller."""
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Hasar No": "H-1"}),
        _satir("SSTMN-1", "D-1", **{"Hasar No": "H-2"}),
    ])

    sonuc = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert (sonuc.foy_yeni, sonuc.foy_guncellenen) == (1, 1)
    db = uc_kart()
    try:
        assert db.query(models.CaseFoy).count() == 1
        assert foy_map.get_foy(db, "SSTMN-1").hasar_no == "H-2"
    finally:
        db.close()


def test_envanter_snapshot_kart_kapsamiyla_daraltilabiliyor(belgeli_kart):
    """`case_ids` filtresi: eş zamanlı yükleme gürültüsünü kapsam dışında
    bırakmak isteyen çağıranlar için (script tam tabloyu ölçer)."""
    fabrika, case_id, _taraf_id = belgeli_kart
    db = fabrika()
    try:
        tam = belge_envanteri.snapshot(db)
        kapsamli = belge_envanteri.snapshot(db, case_ids=[case_id])
        bos = belge_envanteri.snapshot(db, case_ids=[])
        assert tam == kapsamli                 # tek kart var: aynı görüntü
        assert bos.toplam == 0 and bos.bag_imzasi != tam.bag_imzasi
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. dbtest — gerçek Postgres (3-ortam kuralı: to_regclass + SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg():
    """Gerçek Postgres bağlantısı; DB yoksa YA DA şema göçmemişse modül SKIP.

    Çıplak CI Postgres'i bağlantı verir ama tablo sunmaz — to_regclass kontrolü
    o ortamı FAIL yerine SKIP yapar. Testler yazdıklarını dış transaction'la
    geri alır; gerçek veritabanına kalıcı satır bırakılmaz.
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
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G064 dbtest atlandı")

    try:
        eksik = [
            t for t in ("cases", "case_parties", "case_documents", "case_history", "case_foys")
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar() is None
        ]
    except Exception as exc:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema sorgulanamadı ({type(exc).__name__})")
    if eksik:
        conn.close()
        engine.dispose()
        pytest.skip(f"Şema göçmemiş — eksik tablo: {', '.join(eksik)} (migrasyon koşmamış)")

    conn.rollback()
    try:
        yield conn
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.dbtest
def test_gercek_postgreste_kosu_idempotent_ve_envanter_denk(pg, tmp_path):
    """Uçtan uca gerçek şemada: ilk koşu yazar, ikinci koşu 0 değişiklik,
    belge envanteri iki koşuda da denk. Yazılanlar dış transaction'la geri
    alınır (gerçek DB'ye iz bırakılmaz)."""
    damga = uuid.uuid4().hex[:10]
    tracking = f"HA.G064.{os.getpid()}.{damga}"
    klasor = f"G064-{damga}"
    sistem_no = f"G064-{damga}"
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir(sistem_no, klasor, **{"Arşiv Tarihi": "15.03.2021",
                                     "Islah Tutarı": "12.345,67"}),
    ])

    trans = pg.begin()
    try:
        kurulum = Session(bind=pg)
        try:
            kurulum.add(models.Case(tracking_no=tracking, status="DERDEST",
                                    klasor_no_2=klasor))
            kurulum.commit()
        finally:
            kurulum.close()

        ilk = aktarimi_kos(lambda: Session(bind=pg), girdi=paket,
                           rapor_dizini=tmp_path / "rapor")
        assert ilk.cikis_kodu == CIKIS_TAMAM
        assert (ilk.foy_yeni, ilk.alan_degisikligi) == (1, 2)
        assert ilk.envanter_farki == {}

        ikinci = aktarimi_kos(lambda: Session(bind=pg), girdi=paket,
                              rapor_dizini=tmp_path / "rapor")
        assert (ikinci.foy_yeni, ikinci.foy_guncellenen) == (0, 1)
        assert ikinci.alan_degisikligi == 0 and ikinci.envanter_farki == {}

        kontrol = Session(bind=pg)
        try:
            foyler = kontrol.query(models.CaseFoy).filter_by(sistem_no=sistem_no).all()
            assert len(foyler) == 1                       # satır İKİLENMEDİ
            kart = kontrol.get(models.Case, foyler[0].case_id)
            assert kart.tracking_no == tracking
            assert kart.arsiv_tarihi == date(2021, 3, 15)
            assert kart.islah_tutari == Decimal("12345.67")
            assert kontrol.query(models.CaseHistory).filter_by(case_id=kart.id).count() == 3
        finally:
            kontrol.close()
    finally:
        trans.rollback()

    kalan = pg.execute(
        text("SELECT count(*) FROM case_foys WHERE sistem_no = :s"), {"s": sistem_no}
    ).scalar()
    pg.rollback()
    assert kalan == 0


@pytest.mark.dbtest
def test_gercek_postgreste_statement_timeout_yukseliyor(pg):
    """§8 madde 6: engine 30 sn ile bağlanır, toplu yazma bunu meşru aşar."""
    trans = pg.begin()
    session = Session(bind=pg)
    try:
        assert hukdok_aktarim._statement_timeout_yukselt(session, 600_000) is True
        assert session.execute(text("SHOW statement_timeout")).scalar() == "10min"
    finally:
        session.close()
        trans.rollback()
