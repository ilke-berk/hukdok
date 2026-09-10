"""G156 — Delta paket + zincir başlangıcı (plan 08.09 §1.1 K4 + K6).

Sözleşme: gorevler/gorev/G156.md. Üç kural kilitlenir:

1. `DEGISIKLIK_OZETI` "Teslim türü: tam | delta" satırı → `yapi["teslim_turu"]`
   (defter kolonu yok; satır yoksa `tam`).
2. Kapı: delta teslimde `kaybolan_basliklar` **bilgi** (yapı farkı bloğunda yine
   listelenir, `ozet.txt`'ye yazılır), tam teslimde ihlal; `yeni_basliklar` ve
   `kaybolan_sayfalar` iki türde de ihlal. Envanter/zincir/eşik kuralları aynen.
3. Zincir başlangıcı: "Önceki teslim" yer tutucu (`—`, `İLK`) + defterde hiç
   `uygulandi` teslim yok → `zincir_tamam=True`; uygulanmış teslim varken yer tutucu →
   `zincir_tamam=False` (`zincir_eksik`).

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; paketler
test_g107'nin sentetik üreticisiyle (`_paket`) openpyxl'den üretilir.
"""
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from services import teslim_kutusu as tk
from test_g107_teslim_kutusu import BASLIKLAR, _defter, _iki_satir, _index_ops, _kart, _paket, _uc_satir
from test_g115_yapi_farki import ONCEKI, ONCEKI_YAPI, TESLIM, _yapi

ADMIN = "yonetici@hanyaloglu-acar.av.tr"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — özet satırı ayrıştırıcı, sabitler, ihlal kategorileri
# ═══════════════════════════════════════════════════════════════════════════

def _ozet_ws(satirlar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for satir in satirlar:
        ws.append(list(satir))
    return ws


@pytest.mark.parametrize("satirlar,beklenen", [
    ([["Teslim türü", "delta"]], "delta"),
    ([["Teslim Türü:", "DELTA"]], "delta"),
    ([["Teslim türü: delta (yalnız değişen föyler)"]], "delta"),
    ([["TESLIM TURU", "Delta"]], "delta"),
    ([["Teslim türü", "tam"]], "tam"),
    ([["Teslim türü", "TAM"]], "tam"),
    ([["Teslim türü", "—"]], "tam"),
    ([["Teslim türü", None]], "tam"),
    ([["Önceki teslim", "—"]], "tam"),                              # satır hiç yok
    ([["Alan", "Değer"], ["Bu teslim", "X.xlsx"], ["Teslim türü", "delta"]], "delta"),
])
def test_teslim_turu_ayristirma(satirlar, beklenen):
    """"Teslim türü" etiketi aksan/boşluk/iki nokta duyarsız; değer `_anahtar` ile
    karşılaştırılır; satır yok / boş / yer tutucu → `tam`."""
    assert tk.teslim_turu_oku(_ozet_ws(satirlar)) == beklenen


def test_teslim_turu_taninmayan_deger_warning_ve_tam(caplog):
    """Tanınmayan değer sessizce delta SAYILMAZ: WARNING + `tam` (tam kuralları daha sıkı)."""
    with caplog.at_level(logging.WARNING, logger="services.teslim_kutusu"):
        assert tk.teslim_turu_oku(_ozet_ws([["Teslim türü", "kısmi"]])) == "tam"
    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(uyarilar) == 1 and "Teslim türü" in uyarilar[0].getMessage() and "kısmi" in uyarilar[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_sabitler_ve_defter_satiri_turu():
    assert tk.TESLIM_TURLERI == ("tam", "delta")
    assert tk.TESLIM_TURU_TAM == "tam" and tk.TESLIM_TURU_DELTA == "delta"
    assert tk._bos_yapi()["teslim_turu"] == "tam"
    # Defter satırından okuma: yapı yok / eski kayıt / bozuk değer → tam; delta → delta.
    assert tk.teslim_turu(models.AktarimTeslimi(yapi=None)) == "tam"
    assert tk.teslim_turu(models.AktarimTeslimi(yapi=_yapi())) == "tam"
    assert tk.teslim_turu(models.AktarimTeslimi(yapi=_yapi(teslim_turu="saçma"))) == "tam"
    assert tk.teslim_turu(models.AktarimTeslimi(yapi=_yapi(teslim_turu="delta"))) == "delta"
    # "teslim_turu" bir defter kolonu DEĞİLDİR — yapı JSON'unda yaşar.
    assert "teslim_turu" not in {c.name for c in models.AktarimTeslimi.__table__.columns}


def test_ihlal_kategorileri_turlere_gore():
    """Tam: yeni + kaybolan başlık + kaybolan sayfa; delta: kaybolan başlık ÇIKAR, diğer ikisi kalır."""
    assert tk._ihlal_kategorileri("tam") == ("yeni_basliklar", "kaybolan_basliklar", "kaybolan_sayfalar")
    assert tk._ihlal_kategorileri("delta") == ("yeni_basliklar", "kaybolan_sayfalar")
    fark = tk.yapi_farki(_yapi(), _yapi(basliklar=[b for b in BASLIKLAR if b != "Hasar No"]))
    assert fark["kaybolan_basliklar"] == ["Hasar No"]
    assert tk._ihlal_var(fark, "tam") is True and tk._ihlal_var(fark, "delta") is False
    assert tk._fark_gerekcesi(fark, "tam") == "yapi_degisti (kaybolan: Hasar No)"
    # Varsayılan (tür verilmeden) = tam — G115 çağrı sözleşmesi bozulmadı.
    assert tk._ihlal_var(fark) is True and tk._fark_gerekcesi(fark) == "yapi_degisti (kaybolan: Hasar No)"
    # Bilgi kalemleri türden bağımsız: kaybolan başlık yapı farkı bloğunda YİNE listelenir.
    assert ("kaybolan başlık", "Hasar No") in tk.fark_kalemleri(fark)


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite — doğrulama / kapı / zincir başlangıcı uçtan uca
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """sqlite (FK + çalışan SAVEPOINT + defter/bildirim index'leri) + spool + iki kart + ADMIN_EMAILS
    (test_g115 fixture reçetesi)."""
    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    for ad in ("TESLIM_KAPI_HATA_ORANI", "TESLIM_KAPI_ESLESMEYEN_ORANI", "TESLIM_KAPI_ALAN_DEGISIKLIGI"):
        monkeypatch.delenv(ad, raising=False)

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
        for tablo in ("case_foys", "aktarim_teslimleri", "notifications"):
            for sql in _index_ops(tablo):
                conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(tk, "SessionLocal", maker)

    db = maker()
    try:
        for i in (1, 2):
            _kart(db, f"HA.G156.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    yield SimpleNamespace(db=maker)
    engine.dispose()


def _onceki_uygulandi(db, yapi=ONCEKI_YAPI):
    return _defter(db, dosya_adi=ONCEKI, sha256="b" * 64, durum=tk.DURUM_UYGULANDI, yapi=yapi)


def _ozet_satirlari(*, onceki, tur):
    """Sentetik `DEGISIKLIK_OZETI`: "Bu teslim", "Önceki teslim", "Teslim türü" satırları."""
    satirlar = [["Alan", "Değer"], ["Bu teslim", f"{TESLIM} · 2 satır × 5 sütun"]]
    if onceki is not None:
        satirlar.append(["Önceki teslim", onceki])
    if tur is not None:
        satirlar.append(["Teslim türü", tur])
    return satirlar


def _eksik_sutunlu_paket(*, tur, onceki=f"{ONCEKI} · 2 satır"):
    """Önceki uygulanmış teslime göre "Hasar No" sütunu OLMAYAN paket (eşik içi iki satır)."""
    basliklar = [b for b in BASLIKLAR if b != "Hasar No"]
    return _paket(_iki_satir(), basliklar=basliklar, ozet_satirlari=_ozet_satirlari(onceki=onceki, tur=tur))


def _ozet_dosyasi(db, tid) -> str:
    from pathlib import Path

    rapor = Path(db.get(models.AktarimTeslimi, tid).rapor_dizini)
    return (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8")


def test_delta_paket_eksik_sutun_kapida_bilgi_otomatik(env, caplog):
    """Kabul: delta teslimde önceki uygulanmış teslime göre KAYBOLAN sütun → kapı `otomatik`
    (öteki eşikler içinde), gerekçe yok; fark yine `yapi_farki`da ve `ozet.txt` "yapı farkı"
    satırında (bilgi); `yapi["teslim_turu"] == "delta"`; bildirim yok; ERROR yok."""
    db = env.db()
    try:
        _onceki_uygulandi(db)
        tid = tk.teslim_kaydet(icerik=_eksik_sutunlu_paket(tur="delta"), dosya_adi=TESLIM,
                               kaynak="yukleme", db=db)
        with caplog.at_level(logging.INFO, logger="services.teslim_kutusu"):
            assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "kuru_kosuldu"

        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.yapi["teslim_turu"] == "delta"
        assert teslim.zincir_tamam is True
        assert teslim.kapi_karari == "otomatik" and teslim.kapi_gerekcesi is None
        assert teslim.yapi_farki["kaybolan_basliklar"] == ["Hasar No"]           # bilgi olarak duruyor
        assert teslim.durum_gecmisi[1]["not"].startswith("yapı tamam; teslim türü delta;")

        satirlar = _ozet_dosyasi(db, tid).rstrip().splitlines()
        assert "  yapı farkı        : kaybolan başlık: Hasar No" in satirlar
        assert satirlar[-1] == "  kapı kararı       : otomatik"
        assert db.query(models.Notification).filter(models.Notification.type == tk.BILDIRIM_TURU).count() == 0
        assert [r for r in caplog.records if r.levelno == logging.INFO and "delta teslim" in r.getMessage()]
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    finally:
        db.close()


@pytest.mark.parametrize("tur", [None, "tam"])
def test_tam_paket_eksik_sutun_kapida_ihlal(env, tur):
    """Kabul: aynı paket "Teslim türü" satırı YOKKEN ya da `tam` iken → `inceleme_bekliyor`,
    gerekçe `yapi_degisti (kaybolan: Hasar No)` (G115 davranışı korunur)."""
    db = env.db()
    try:
        _onceki_uygulandi(db)
        tid = tk.teslim_kaydet(icerik=_eksik_sutunlu_paket(tur=tur), dosya_adi=TESLIM,
                               kaynak="yukleme", db=db)
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "inceleme_bekliyor"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.yapi["teslim_turu"] == "tam"
        assert teslim.kapi_karari == "inceleme"
        assert teslim.kapi_gerekcesi == "yapi_degisti (kaybolan: Hasar No)"
    finally:
        db.close()


def test_delta_yeni_baslik_ve_kaybolan_sayfa_yine_ihlal(env):
    """Delta'da `yeni_basliklar` ve `kaybolan_sayfalar` kuralı DEĞİŞMEZ; gerekçede kaybolan
    başlık geçmez (bilgi), yeni başlık + kaybolan sayfa geçer."""
    db = env.db()
    try:
        _onceki_uygulandi(db, yapi=_yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]))
        fark = tk.yapi_farki(
            _yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]),
            _yapi(basliklar=[b for b in BASLIKLAR if b != "Hasar No"] + ["Yeni Sütun"]),
        )
        assert fark["kaybolan_basliklar"] == ["Hasar No"] and fark["yeni_basliklar"] == ["Yeni Sütun"]
        tid = _defter(db, yapi={**_yapi(teslim_turu="delta"), "fark": fark})
        assert tk.kapi_degerlendir(tid, db=db) == "inceleme"
        gerekce = db.get(models.AktarimTeslimi, tid).kapi_gerekcesi
        assert gerekce == "yapi_degisti (yeni: Yeni Sütun; kaybolan sayfa: Karar_Asamalari)"

        # Yalnız kaybolan sayfa, delta → yine ihlal.
        fark2 = tk.yapi_farki(_yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]), _yapi())
        tid2 = _defter(db, sha256="c" * 64, yapi={**_yapi(teslim_turu="delta"), "fark": fark2})
        assert tk.kapi_degerlendir(tid2, db=db) == "inceleme"
        assert db.get(models.AktarimTeslimi, tid2).kapi_gerekcesi == "yapi_degisti (kaybolan sayfa: Karar_Asamalari)"
    finally:
        db.close()


def test_delta_envanter_ve_zincir_kurali_aynen(env):
    """Delta teslim envanter denkliği ve zincir kuralından MUAF DEĞİLDİR."""
    db = env.db()
    try:
        _onceki_uygulandi(db)
        fark = tk.yapi_farki(_yapi(), _yapi(basliklar=[b for b in BASLIKLAR if b != "Hasar No"]))
        tid = _defter(db, envanter_denk=False, zincir_tamam=False,
                      yapi={**_yapi(teslim_turu="delta"), "fark": fark})
        assert tk.kapi_degerlendir(tid, db=db) == "inceleme"
        gerekce = db.get(models.AktarimTeslimi, tid).kapi_gerekcesi
        assert "envanter_denk_degil" in gerekce and "zincir_eksik" in gerekce
        assert "yapi_degisti" not in gerekce and gerekce.count(";") == 1
    finally:
        db.close()


@pytest.mark.parametrize("yer_tutucu", ["—", "İLK", "-", "yok"])
def test_zincir_baslangici_yer_tutucu_bos_defter_zincir_tamam(env, yer_tutucu):
    """Kabul: "Önceki teslim" yer tutucu + defterde hiç `uygulandi` teslim yok →
    `zincir_tamam=True`; kapı yalnız `ilk_teslim` der (zincir_eksik YOK)."""
    db = env.db()
    try:
        _defter(db, dosya_adi="HUKDOK_TESLIM_ESKI.xlsx", sha256="d" * 64, durum=tk.DURUM_INCELEME)
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir(), ozet=yer_tutucu), dosya_adi=TESLIM,
                               kaynak="yukleme", db=db)
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "inceleme_bekliyor"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.onceki_teslim_adi is None and teslim.zincir_tamam is True
        assert "zincir başlangıcı" in teslim.durum_gecmisi[1]["not"]
        assert teslim.kapi_gerekcesi == "ilk_teslim (defterde uygulanmış teslim yok)"
    finally:
        db.close()


def test_zincir_yer_tutucu_dolu_defter_zincir_eksik(env):
    """Kabul: defterde uygulanmış teslim VARKEN yer tutucu → `zincir_tamam=False` + `zincir_eksik`."""
    db = env.db()
    try:
        _onceki_uygulandi(db)
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir(), ozet="—"), dosya_adi=TESLIM,
                               kaynak="yukleme", db=db)
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "inceleme_bekliyor"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.onceki_teslim_adi is None and teslim.zincir_tamam is False
        assert "defterde uygulanmış teslim var" in teslim.durum_gecmisi[1]["not"]
        assert teslim.kapi_gerekcesi.startswith("zincir_eksik (")
    finally:
        db.close()


def test_zincir_adli_onceki_kurali_degismedi(env):
    """Ad verilmişse eski kural: uygulanmışsa True, değilse False — defter boş olsa bile
    yanlış ad zincir başlangıcı sayılmaz."""
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir(), ozet="HUKDOK_TESLIM_HAYALI.xlsx"),
                               dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid, db=db) == "dogrulandi"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.onceki_teslim_adi == "HUKDOK_TESLIM_HAYALI.xlsx" and teslim.zincir_tamam is False

        _onceki_uygulandi(db)
        tid2 = tk.teslim_kaydet(icerik=_paket(_uc_satir("k"), ozet=f"{ONCEKI} · 3 satır"),
                                dosya_adi="HUKDOK_TESLIM_K.xlsx", kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid2, db=db) == "dogrulandi"
        assert db.get(models.AktarimTeslimi, tid2).zincir_tamam is True
    finally:
        db.close()


def test_ozet_sayfasi_yoksa_zincir_null_ve_tur_tam(env):
    """`DEGISIKLIK_OZETI` yok → zincir NULL (değişmedi) ve tür `tam`."""
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir()), dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid, db=db) == "dogrulandi"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.zincir_tamam is None and teslim.yapi["teslim_turu"] == "tam"
    finally:
        db.close()
