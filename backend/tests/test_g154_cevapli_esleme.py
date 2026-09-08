"""G154 — Ekibin cevaplı xlsx'i → `--kart-esleme` haritası: cevap ayrıştırma
(3 desen + BAĞLAMAYIN), CSV sözleşmesi, `_kart_coz`da harita önceliği,
bilinmeyen kart HATA'sı, ön geçiş tutarlılığı ve ikinci koşu 0.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek cevap dosyası ve teslim paketi
REPOYA GİRMEZ; xlsx'ler openpyxl ile SENTETİK üretilir (test_g064
yardımcıları). Gerçek dosyayla ölçüm yalnız görev raporundadır.
"""
import csv
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import foy_map
from scripts import cevapli_kart_eslemesi as ce
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    CIKIS_GIRDI,
    CIKIS_SATIR_HATASI,
    CIKIS_TAMAM,
    AktarimHatasi,
    aktarimi_kos,
    kart_eslemesini_oku,
)
from tests.test_g064_aktarim_cekirdek import BASLIKLAR, _kart, _paket_yaz, _satir

BASLIKLAR_G154 = BASLIKLAR + ["Ana Tür", "Esas", "Müvekkil"]

CEVAP_BASLIKLARI = [
    "Grup", "Satır türü", "SistemNo / Kart No", "DosyaNo / Klasör No (Eski)", "Müvekkil",
    "HukuDok öneri kart", "CEVABINIZ (hangi kart / not)", "AÇIKLAMAMIZ (Veri Ekibi)",
]

AXA = "S3.AXA........2915.IDARE.00000"
ISIK = "S3.M_ISIK.....0001.IDARE.00000"
AXA_2 = "S3.AXA........2754.HUKUK.00000-2"
QUICK = "S4.QUICK......0060.IDARE.00000"
KULU = "S4.U_KULU.....0001.IDARE.00000"


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


def _cevap_xlsx(yol, gruplar, *, sayfa=ce.SAYFA, basliklar=None):
    """Sentetik CEVAPLI xlsx: gruplar = [(sistem_no, cevap, öneri, [(kart no, müvekkil), ...])]."""
    from openpyxl import Workbook

    kullanilan = list(basliklar if basliklar is not None else CEVAP_BASLIKLARI)
    wb = Workbook()
    ws = wb.active
    ws.title = sayfa
    ws.append(kullanilan)
    for grup_no, (sistem_no, cevap, oneri, kartlar) in enumerate(gruplar, start=1):
        foy = {"Grup": grup_no, "Satır türü": "FÖY (paket)", "SistemNo / Kart No": sistem_no,
               "DosyaNo / Klasör No (Eski)": "1.21184.00", "Müvekkil": "Axa Sigorta A.Ş.",
               "HukuDok öneri kart": oneri, "CEVABINIZ (hangi kart / not)": cevap}
        ws.append([foy.get(b) for b in kullanilan])
        for kart_no, muvekkil in kartlar:
            kart = {"Grup": grup_no, "Satır türü": "KART (HukuDok)", "SistemNo / Kart No": kart_no,
                    "DosyaNo / Klasör No (Eski)": "#1", "Müvekkil": muvekkil}
            ws.append([kart.get(b) for b in kullanilan])
    wb.save(yol)
    wb.close()
    return Path(yol)


def _kartlar(*adlar):
    return [ce.KartSatiri(tracking_no=tn, muvekkil_anahtarlari={
        hukdok_aktarim.normalize_party_key(a) for a in hukdok_aktarim._taraf_adlari(muv)
    }) for tn, muv in adlar]


def _muvekkil(db, case, ad):
    taraf = models.CaseParty(case_id=case.id, name=ad, role="Müvekkil", party_type="CLIENT")
    db.add(taraf)
    db.flush()
    return taraf


def _foy_karti(db_env, sistem_no):
    db = db_env()
    try:
        foy = foy_map.get_foy(db, sistem_no)
        return None if foy is None else foy.case_id
    finally:
        db.close()


def _csv_yaz(yol, satirlar, *, basliklar=("sistem_no", "tracking_no", "kaynak_not")):
    with open(yol, "w", newline="", encoding="utf-8-sig") as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(basliklar)
        yazici.writerows(satirlar)
    return Path(yol)


# ─── Birim: cevap ayrıştırma (kabul 1) ──────────────────────────────────────

@pytest.mark.parametrize("cevap, kartlar, durum, tracking_no", [
    (AXA, [(AXA, "Axa Sigorta A.ş."), (ISIK, "Mürüvvet Işık; Axa Sigorta A.ş.")], ce.DURUM_KART, AXA),
    (f"{AXA_2} (teyit)", [(AXA_2, "Axa Sigorta A.ş.")], ce.DURUM_KART, AXA_2),   # -2 eki + not
    ("MÜVEKKİL: Quick Sigorta A.Ş.",
     [(QUICK, "Quıck Sigorta A.ş"), (KULU, "Uğur Kulu; Tuğba Atcı; Quıck Sigorta A.ş")],
     ce.DURUM_MUVEKKIL, QUICK),                                     # id-1012: sigortanın KENDİ kartı
    ("Müvekkil : Ahmet Yılmaz",
     [("D1.A_YILMAZ...0001.HUKUK.00000", "Ahmet Yılmaz"), (AXA, "Axa Sigorta A.ş.; Ahmet Yılmaz")],
     ce.DURUM_MUVEKKIL, "D1.A_YILMAZ...0001.HUKUK.00000"),
    ("MÜVEKKİL: Ahmet Yılmaz", [(AXA, "Axa Sigorta A.ş."), (ISIK, "Mürüvvet Işık; Axa Sigorta A.ş.")],
     ce.DURUM_COZULEMEDI, ""),                                      # aday yok
    ("MÜVEKKİL: Axa Sigorta A.Ş.", [(AXA, "Axa Sigorta A.ş."), (AXA_2, "Axa Hayat Sigorta A.ş.")],
     ce.DURUM_COZULEMEDI, ""),                                      # iki aday
    ("BAĞLAMAYIN — önce bizde düzeltilecek", [(AXA, "Axa Sigorta A.ş.")], ce.DURUM_BAGLAMAYIN, ""),
    ("baglamayin", [], ce.DURUM_BAGLAMAYIN, ""),                    # aksansız / küçük harf
    (None, [(AXA, "Axa Sigorta A.ş.")], ce.DURUM_COZULEMEDI, ""),
    ("emin değiliz", [(AXA, "Axa Sigorta A.ş.")], ce.DURUM_COZULEMEDI, ""),
])
def test_cevabi_coz_uc_desen_ve_baglamayin(cevap, kartlar, durum, tracking_no):
    satir = ce.cevabi_coz("F-1", cevap, kartlar=_kartlar(*kartlar))
    assert (satir.durum, satir.tracking_no) == (durum, tracking_no)
    assert satir.sistem_no == "F-1" and satir.kaynak_not


def test_kaynak_not_oneriyle_karsilastirir(caplog):
    ayni = ce.cevabi_coz("F-1", AXA, oneri=AXA, kartlar=_kartlar((AXA, "Axa Sigorta A.ş.")))
    farkli = ce.cevabi_coz("F-2", ISIK, oneri=AXA, kartlar=_kartlar((AXA, "Axa"), (ISIK, "Işık")))
    yok = ce.cevabi_coz("F-3", AXA, oneri=None, kartlar=_kartlar((AXA, "Axa Sigorta A.ş.")))
    assert "öneriyle aynı" in ayni.kaynak_not
    assert f"öneri farklıydı: {AXA}" in farkli.kaynak_not
    assert "öneri yoktu" in yok.kaynak_not

    with caplog.at_level(logging.WARNING, logger="CevapliKartEslemesi"):
        disarida = ce.cevabi_coz("F-4", QUICK, oneri=AXA, kartlar=_kartlar((AXA, "Axa Sigorta A.ş.")))
    assert disarida.durum == ce.DURUM_KART and disarida.tracking_no == QUICK
    assert "grubun aday kartları dışında" in disarida.kaynak_not
    assert any("F-4" in r.getMessage() and "aday kartları arasında değil" in r.getMessage()
               for r in caplog.records)


def test_cevap_xlsx_okunur_csv_yazilir_baglamayin_atlanir(tmp_path):
    """Kabul 1: xlsx → satırlar → CSV; BAĞLAMAYIN CSV'ye girmez, özette görünür;
    üretilen CSV aktarımın okuyucusuyla birebir okunur (sözleşme iki uçta aynı)."""
    xlsx = _cevap_xlsx(tmp_path / "cevap.xlsx", [
        ("id-7356", AXA, AXA, [(AXA, "Axa Sigorta A.ş."), (ISIK, "Mürüvvet Işık; Axa Sigorta A.ş.")]),
        ("H-6589", "BAĞLAMAYIN — önce bizde düzeltilecek", "S3.AXA........2963.HUKUK.00000",
         [("S3.AXA........2963.HUKUK.00000", "Axa Sigorta A.ş."),
          ("S1.AK.........0619.HUKUK.00000", "Ak Sigorta A.ş.; Axa Sigorta A.ş.")]),
        ("id-1012", "MÜVEKKİL: Quick Sigorta A.Ş.", None,
         [(QUICK, "Quıck Sigorta A.ş"), (KULU, "Uğur Kulu; Tuğba Atcı; Quıck Sigorta A.ş")]),
        ("id-9999", "bilmiyoruz", AXA, [(AXA, "Axa Sigorta A.ş.")]),
    ])

    satirlar = ce.cevaplari_oku(xlsx)
    assert [(s.sistem_no, s.durum, s.tracking_no) for s in satirlar] == [
        ("id-7356", ce.DURUM_KART, AXA),
        ("H-6589", ce.DURUM_BAGLAMAYIN, ""),
        ("id-1012", ce.DURUM_MUVEKKIL, QUICK),
        ("id-9999", ce.DURUM_COZULEMEDI, ""),
    ]
    assert satirlar[0].grup == "1" and satirlar[2].grup == "3"

    yol = ce.csv_yaz(satirlar, tmp_path / "harita.csv")
    with open(yol, newline="", encoding="utf-8-sig") as dosya:
        kayitlar = list(csv.DictReader(dosya))
    assert [k["sistem_no"] for k in kayitlar] == ["id-7356", "id-1012", "id-9999"]   # H-6589 YOK
    assert kayitlar[2]["tracking_no"] == "" and "tanınmayan cevap" in kayitlar[2]["kaynak_not"]

    ozet = ce.ozet_metni(satirlar, yol)
    assert "kart no ile        : 1" in ozet and "müvekkil adıyla    : 1" in ozet
    assert "BAĞLAMAYIN (atlandı): 1" in ozet and "- H-6589: BAĞLAMAYIN" in ozet

    harita = kart_eslemesini_oku(yol)
    assert harita == {"id-7356": AXA, "id-1012": QUICK}                      # boş satır haritaya girmez


def test_cevap_xlsx_sayfa_ve_sutun_kilitleri(tmp_path):
    xlsx = _cevap_xlsx(tmp_path / "cevap.xlsx", [("F-1", AXA, AXA, [(AXA, "Axa")])], sayfa="OZET")
    with pytest.raises(AktarimHatasi, match="MUKERRER_ESLESME"):
        ce.cevaplari_oku(xlsx)

    eksik = _cevap_xlsx(tmp_path / "eksik.xlsx", [("F-1", AXA, AXA, [(AXA, "Axa")])],
                        basliklar=[b for b in CEVAP_BASLIKLARI if not b.startswith("CEVABINIZ")])
    with pytest.raises(AktarimHatasi, match="cevap"):
        ce.cevaplari_oku(eksik)

    with pytest.raises(AktarimHatasi, match="yok"):
        ce.cevaplari_oku(tmp_path / "yok.xlsx")


def test_cevapli_cli(tmp_path, capsys):
    xlsx = _cevap_xlsx(tmp_path / "cevap.xlsx", [("F-1", AXA, AXA, [(AXA, "Axa Sigorta A.ş.")])])
    cikti = tmp_path / "harita" / "kart_eslemesi.csv"
    assert ce.main(["--input", str(xlsx), "--output", str(cikti)]) == CIKIS_TAMAM
    assert kart_eslemesini_oku(cikti) == {"F-1": AXA}
    assert "föy satırı         : 1" in capsys.readouterr().out
    assert ce.main(["--input", str(tmp_path / "yok.xlsx"), "--output", str(cikti)]) == CIKIS_GIRDI


# ─── Birim: CSV okuyucu (aktarım tarafı) ────────────────────────────────────

def test_kart_eslemesini_oku_bos_ve_celisen_satirlar(tmp_path, caplog):
    yol = _csv_yaz(tmp_path / "h.csv", [
        ("F-1", AXA, "kart"),
        ("F-2", "", "MÜVEKKİL: X → çözülemedi"),
        ("F-1", AXA, "aynı karta tekrar — zararsız"),
        ("", QUICK, "SistemNo boş"),
    ])
    with caplog.at_level(logging.WARNING, logger="HukdokAktarim"):
        assert kart_eslemesini_oku(yol) == {"F-1": AXA}
    assert any("F-2" in r.getMessage() and "boş" in r.getMessage() for r in caplog.records)

    celisen = _csv_yaz(tmp_path / "c.csv", [("F-1", AXA, ""), ("F-1", ISIK, "")])
    with pytest.raises(AktarimHatasi, match="iki farklı karta"):
        kart_eslemesini_oku(celisen)

    basliksiz = _csv_yaz(tmp_path / "b.csv", [("F-1", AXA)], basliklar=("SistemNo", "Kart"))
    with pytest.raises(AktarimHatasi, match="başlıkları eksik"):
        kart_eslemesini_oku(basliksiz)

    with pytest.raises(AktarimHatasi, match="dosyası yok"):
        kart_eslemesini_oku(tmp_path / "yok.csv")


# ─── sqlite: harita önceliği (kabul 2) ──────────────────────────────────────

def _gercek_mukerrer(db_env, klasor="3.563.00", esas="2019/12"):
    """id-14272 deseni: aynı Dosya No, aynı esas/tür, İKİSİ DE {Ak} — hiçbir
    anahtar ayırmaz (G153 raporundaki 2 'gerçek mükerrer')."""
    db = db_env()
    try:
        a = _kart(db, "S1.AK.........0686.IDARE.00000", klasor, file_type="İdare", esas_no=esas)
        b = _kart(db, "S1.AK.........0687.IDARE.00000", klasor, file_type="İdare", esas_no=esas)
        _muvekkil(db, a, "Ak Sigorta A.ş.")
        _muvekkil(db, b, "Ak Sigorta A.ş.")
        tek = _kart(db, "S1.AK.........0001.HUKUK.00000", "3.1.00", file_type="Hukuk")
        db.commit()
        return a.id, b.id, tek.id
    finally:
        db.close()


def _paket(tmp_path, *satirlar):
    return _paket_yaz(tmp_path / "teslim.xlsx", list(satirlar), basliklar=BASLIKLAR_G154)


def _foy_satiri(sistem_no, dosya_no, **ek):
    return _satir(sistem_no, dosya_no, **{"Ana Tür": "İDARE", "Esas": "2019/12",
                                          "Müvekkil": "Ak Sigorta A.Ş.", **ek})


def test_harita_belirsiz_ikizi_verilen_karta_baglar(db_env, tmp_path, caplog):
    """Kabul 2: haritasız koşuda satır 'Belirsiz eşleşme' HATA'sı; haritayla
    ekibin dediği (İKİNCİ) karta bağlanır. Harita yalnız verilen SistemNo'yu
    etkiler: haritada olmayan satır köprüden her zamanki gibi geçer."""
    a_id, b_id, tek_id = _gercek_mukerrer(db_env)
    paket = _paket(tmp_path, _foy_satiri("id-14272", "3.563.00"),
                   _foy_satiri("id-1", "3.1.00", **{"Ana Tür": "HUKUK"}))

    haritasiz = aktarimi_kos(db_env, girdi=paket, dry_run=True, rapor_dizini=tmp_path / "r0")
    assert haritasiz.cikis_kodu == CIKIS_SATIR_HATASI
    assert [h.sistem_no for h in haritasiz.hatalar] == ["id-14272"]
    assert "Belirsiz eşleşme" in haritasiz.hatalar[0].sebep

    with caplog.at_level(logging.INFO, logger="HukdokAktarim"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r1",
                             kart_eslemesi={"id-14272": "S1.AK.........0687.IDARE.00000"})
    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert sonuc.foy_yeni == 2 and sonuc.islenen == 2
    assert _foy_karti(db_env, "id-14272") == b_id
    assert _foy_karti(db_env, "id-1") == tek_id
    assert any("id-14272 açık haritayla kart" in r.getMessage() for r in caplog.records)
    assert any("Açık kart haritası: 1 SistemNo" in r.getMessage() for r in caplog.records)


def test_bilinmeyen_ve_silinmis_kart_hata(db_env, tmp_path):
    """Kabul 2: haritadaki kart DB'de yoksa ya da silinmişse satır HATA (rapor),
    föy YAZILMAZ, köprüye DÜŞÜLMEZ (tahmin yasağı); öteki satırlar işlenir."""
    a_id, b_id, tek_id = _gercek_mukerrer(db_env)
    db = db_env()
    try:
        from datetime import datetime, timezone
        db.get(models.Case, tek_id).deleted_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    paket = _paket(tmp_path, _foy_satiri("id-14272", "3.563.00"),
                   _foy_satiri("id-14271", "3.563.00"),
                   _foy_satiri("id-1", "3.1.00", **{"Ana Tür": "HUKUK"}))

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r", kart_eslemesi={
        "id-14272": "S9.YOK........0001.IDARE.00000",
        "id-14271": "S1.AK.........0686.IDARE.00000",
        "id-1": "S1.AK.........0001.HUKUK.00000",              # silinmiş kart
    })
    assert sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    hatalar = {h.sistem_no: h.sebep for h in sonuc.hatalar}
    assert set(hatalar) == {"id-14272", "id-1"}
    assert "--kart-esleme" in hatalar["id-14272"] and "S9.YOK........0001.IDARE.00000" in hatalar["id-14272"]
    assert "silinmiş" in hatalar["id-1"]
    assert _foy_karti(db_env, "id-14272") is None and _foy_karti(db_env, "id-1") is None
    assert _foy_karti(db_env, "id-14271") == a_id and sonuc.islenen == 1


def test_harita_foy_kaydindan_once(db_env, tmp_path, caplog):
    """Harita föy kaydından da öncedir: yanlış karta bağlı föy ekibin kartına
    TAŞINIR (`foy_map._apply_update` WARNING'i), kart değiştirme tarihçesiyle."""
    a_id, b_id, _tek = _gercek_mukerrer(db_env)
    db = db_env()
    try:
        foy_map.upsert_foy(db, db.get(models.Case, a_id), sistem_no="id-14272", source="eski")
        db.commit()
    finally:
        db.close()
    paket = _paket(tmp_path, _foy_satiri("id-14272", "3.563.00"))

    with caplog.at_level(logging.WARNING, logger="foy_map"):
        sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r",
                             kart_eslemesi={"id-14272": "S1.AK.........0687.IDARE.00000"})
    assert not sonuc.hatalar and sonuc.foy_guncellenen == 1
    assert _foy_karti(db_env, "id-14272") == b_id
    assert any("kart değiştiriyor" in r.getMessage() for r in caplog.records)


def test_on_gecis_haritali_foyleri_uzlasiya_katar(db_env, tmp_path):
    """Ön geçiş ikizi de haritayı görür: aynı karta haritayla düşen iki föy bir
    kart alanında çelişiyorsa alan YAZILMAZ ve kardeş-föy raporuna düşer —
    ikiz haritayı görmeseydi satır satır yazımda son föy kazanırdı."""
    a_id, b_id, _tek = _gercek_mukerrer(db_env)
    paket = _paket(tmp_path,
                   _foy_satiri("id-14271", "3.563.00", **{"Arşiv Tarihi": "15.03.2021"}),
                   _foy_satiri("id-14272", "3.563.00", **{"Arşiv Tarihi": "16.03.2021"}))
    harita = {"id-14271": "S1.AK.........0686.IDARE.00000", "id-14272": "S1.AK.........0686.IDARE.00000"}

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r", kart_eslemesi=harita)
    assert not sonuc.hatalar and sonuc.foy_yeni == 2
    assert _foy_karti(db_env, "id-14271") == a_id and _foy_karti(db_env, "id-14272") == a_id
    kart_celiskileri = [c for c in sonuc.celiskiler if c.kume == "KART" and c.alan == "arsiv_tarihi"]
    assert len(kart_celiskileri) == 1 and kart_celiskileri[0].kume_anahtari == str(a_id)
    db = db_env()
    try:
        assert db.get(models.Case, a_id).arsiv_tarihi is None
        assert db.get(models.Case, b_id).arsiv_tarihi is None
    finally:
        db.close()


def test_celiski_kapisi_haritadan_once(db_env, tmp_path):
    """Karar: kök/müvekkil çelişkisi (G153, H-6589 deseni) haritadan ÖNCE —
    paketin kendi içinde çelişen satır, harita verilse de yazılmaz (ekip:
    "önce bizde düzeltilecek"); cevaplı script zaten BAĞLAMAYIN'ı CSV'ye almaz."""
    a_id, _b, _tek = _gercek_mukerrer(db_env, klasor="3.1400.00")
    paket = _paket(tmp_path, _foy_satiri("H-6589", "3.1400.00", **{"Müvekkil": "Axa Sigorta A.Ş."}))

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r",
                         kart_eslemesi={"H-6589": "S1.AK.........0686.IDARE.00000"})
    assert sonuc.kok_muvekkil_celiskisi == 1 and sonuc.cikis_kodu == CIKIS_SATIR_HATASI
    assert _foy_karti(db_env, "H-6589") is None


def test_ikinci_kosu_sifir(db_env, tmp_path):
    """Kabul 3'ün sentetik ikizi: aynı paket + aynı haritayla ikinci koşu 0
    (föy/alan/taraf/tarihçe)."""
    a_id, b_id, _tek = _gercek_mukerrer(db_env)
    paket = _paket(tmp_path,
                   _foy_satiri("id-14271", "3.563.00", **{"Arşiv Tarihi": "15.03.2021"}),
                   _foy_satiri("id-14272", "3.563.00", **{"Arşiv Tarihi": "16.03.2021"}))
    harita = {"id-14271": "S1.AK.........0686.IDARE.00000", "id-14272": "S1.AK.........0687.IDARE.00000"}

    ilk = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r1", kart_eslemesi=harita)
    assert not ilk.hatalar and ilk.foy_yeni == 2 and ilk.alan_degisikligi == 2

    def _tarihce():
        db = db_env()
        try:
            return db.query(models.CaseHistory).count()
        finally:
            db.close()

    once = _tarihce()
    ikinci = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "r2", kart_eslemesi=harita)
    assert not ikinci.hatalar
    assert (ikinci.foy_yeni, ikinci.foy_guncellenen, ikinci.alan_degisikligi,
            ikinci.taraf_eklenen, ikinci.foy_muvekkil_bagli) == (0, 2, 0, 0, 0)
    assert _tarihce() == once
    assert _foy_karti(db_env, "id-14271") == a_id and _foy_karti(db_env, "id-14272") == b_id


def test_cli_kart_esleme(db_env, tmp_path, monkeypatch, capsys):
    """`--kart-esleme <csv>` CLI'dan haritaya; yok/bozuk dosya koşuyu başlatmaz."""
    import database

    a_id, b_id, _tek = _gercek_mukerrer(db_env)
    monkeypatch.setattr(database, "SessionLocal", db_env)
    paket = _paket(tmp_path, _foy_satiri("id-14272", "3.563.00"))
    harita = _csv_yaz(tmp_path / "h.csv", [("id-14272", "S1.AK.........0687.IDARE.00000", "cevap")])

    kod = hukdok_aktarim.main([
        "--input", str(paket), "--kesim-tarihi", "30.07.2026", "--rapor-dizini", str(tmp_path / "r"),
        "--kart-esleme", str(harita),
    ])
    assert kod == CIKIS_TAMAM and _foy_karti(db_env, "id-14272") == b_id
    assert "yeni föy          : 1" in capsys.readouterr().out

    kod = hukdok_aktarim.main([
        "--input", str(paket), "--kesim-tarihi", "30.07.2026", "--kart-esleme", str(tmp_path / "yok.csv"),
    ])
    assert kod == CIKIS_GIRDI
