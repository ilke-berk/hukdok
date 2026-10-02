"""G257 — Hizmet listesi veri ekibinin paketinden + aktarım listeye DB'den bakar.

Kullanıcı kararı 02.10.2026: karttaki hizmet açılır listesi (`service_types`)
diğer değer havuzları gibi (G124) paketin "Hizmet Türü" sütunundan beslenir.
Bu dosya iki engelin kalktığını ölçer:

  1. `deger_havuzu_seed.HAVUZLAR` hizmet listesini taşır: yeni adı ekler, mevcut
     ada dokunmaz, kuru koşu varsayılan, idempotent; `--kaldir` hizmet SATIRINDA
     (`case_hizmetleri`) kullanılan adı silmez (`reference_lists.bagimliliklar`),
  2. aktarım hizmet adını KOD sabitine değil koşu başında DB listesine karşı
     tanır (`hukdok_aktarim.hizmet_eslemesini_yukle`; tablo boşsa seed sabiti):
     listeye giren yeni ad aktarımda tanınır, föye LİSTENİN yazımı gider.

Sıra insan adımıdır: ÖNCE `deger_havuzu_seed --apply`, SONRA aktarım. Seed
koşulmadan gelen yeni ad föyde ham kalır ve G249'un UYARI yoluna düşer.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; bütün
testler openpyxl ile SENTETİK mini paket üretir (test_g249 düzeni).
"""
import inspect
import os

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from database import Base
from managers import case_hizmetleri, seed_data
from scripts import deger_havuzu_seed as seed
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import CIKIS_TAMAM, AlanHatasi, aktarimi_kos
from test_migration_path import _run_init_db, _scratch_database
from tests.test_g249_hizmet_aktarim import (
    _foy,
    _index_sqlleri,
    _kart,
    _ozetler,
    _paket_yaz,
    _satir,
    _taraf,
)

SEED_ADLARI = {ad for _kod, ad in seed_data.SERVICE_TYPES}


# ═══════════════════════════════════════════════════════════════════════════
# Ortam — sqlite (test_g249 reçetesi: FK + ÇALIŞAN SAVEPOINT) + hizmet listesi
# ═══════════════════════════════════════════════════════════════════════════

def _hizmet_listesini_kur(db):
    for sira, (kod, ad) in enumerate(seed_data.SERVICE_TYPES):
        db.add(models.ServiceType(code=kod, name=ad, active=True, sequence=sira))


@pytest.fixture()
def bos_ortam():
    """`service_types` BOŞ kurulum (seed'i koşmamış ortam)."""
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
        for sql in _index_sqlleri("case_foys", "case_hizmetleri", "case_esas_numbers"):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture()
def ortam(bos_ortam):
    """Hizmet listesi seed sabitleriyle kurulu (9 ad) + iki kart (D-1, D-2)."""
    db = bos_ortam()
    try:
        _hizmet_listesini_kur(db)
        for i in (1, 2):
            _kart(db, f"HA.G257.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    return bos_ortam


def _liste(fabrika):
    """`service_types` satırları, liste sırasıyla: [(kod, ad, aktif, sıra)]."""
    db = fabrika()
    try:
        return [(r.code, r.name, r.active, r.sequence) for r in
                db.query(models.ServiceType).order_by(models.ServiceType.sequence, models.ServiceType.id)]
    finally:
        db.close()


def _liste_adlari(fabrika):
    return {ad for _kod, ad, _aktif, _sira in _liste(fabrika)}


def _foy_hizmetleri(fabrika):
    """{SistemNo: föyün hizmet değeri} — `case_foys.hizmet_turu`."""
    db = fabrika()
    try:
        return dict(db.query(models.CaseFoy.sistem_no, models.CaseFoy.hizmet_turu).all())
    finally:
        db.close()


def _satir_hizmetleri(fabrika):
    """{SistemNo: hizmet adı} — föy kaynaklı `case_hizmetleri` satırları."""
    db = fabrika()
    try:
        return dict(
            db.query(models.CaseFoy.sistem_no, models.CaseHizmeti.hizmet_turu)
            .join(models.CaseHizmeti, models.CaseHizmeti.foy_id == models.CaseFoy.id).all()
        )
    finally:
        db.close()


def _adi_degistir(fabrika, eski, yeni):
    """Panelden yeniden adlandırmanın LİSTE tarafı (satır/özet yayılımı G248'in işi)."""
    db = fabrika()
    try:
        assert db.query(models.ServiceType).filter_by(name=eski).update({"name": yeni}) == 1
        db.commit()
    finally:
        db.close()


def _kos(fabrika, tmp_path, satirlar, **kw):
    paket = _paket_yaz(tmp_path / "t.xlsx", satirlar)
    return aktarimi_kos(fabrika, girdi=paket, rapor_dizini=tmp_path / "rapor", **kw)


def _uyarilar(sonuc):
    return {r.sistem_no: r.sebep for r in sonuc.rapor_satirlari if r.tur == "UYARI"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kayıt kilitleri (DB yok)
# ═══════════════════════════════════════════════════════════════════════════

def test_havuzlar_hizmet_listesini_tasir():
    """Kabul 1: `service_types` havuzu paketin "Hizmet Türü" sütununa bağlı, TEK
    değerli; karar listesi değil (büro durumu elemesi ona uygulanmaz)."""
    havuz = seed.HAVUZ_HARITASI["service_types"]
    assert havuz == seed.Havuz("service_types", models.ServiceType, ("Hizmet Türü",), False)
    assert havuz in seed.HAVUZLAR and len(seed.HAVUZLAR) == 14
    assert "service_types" not in seed.KARAR_LISTELERI
    # Aktarımla AYNI sütun: seed'in beslediği liste ile aktarımın okuduğu başlık bir.
    assert hukdok_aktarim.SUTUN_ADAYLARI["hizmet_turu"] == havuz.basliklar


def test_varsayilan_esleme_seed_sabiti_ve_imza_degismedi():
    """Kabul 2: modül düzeyi `HIZMET_TURU_ESLEMESI` adı korunur (varsayılan = seed
    sabitleri); koşu dışında geçerli eşleme odur; `_hizmet_turu(deger, alan)` imzası aynı."""
    assert set(hukdok_aktarim.HIZMET_TURU_ESLEMESI.values()) == SEED_ADLARI
    assert hukdok_aktarim.hizmet_eslemesi() is hukdok_aktarim.HIZMET_TURU_ESLEMESI
    assert list(inspect.signature(hukdok_aktarim._hizmet_turu).parameters) == ["deger", "alan"]
    assert hukdok_aktarim._hizmet_turu("LEXIS RAPOR", "hizmet_turu") == "Lexis Rapor"
    with pytest.raises(AlanHatasi, match="kapalı listede"):
        hukdok_aktarim._hizmet_turu("Yeni Hizmet X", "hizmet_turu")


def test_panel_teslim_hattina_otomatik_seed_baglanmadi():
    """Kabul 7: `teslim_kutusu` havuz seed'ini ÇAĞIRMAZ (diğer havuzlarla aynı:
    insan adımı) — panelden uygulanan pakette yeni hizmet adı uyarıya düşer."""
    from services import teslim_kutusu

    kaynak = inspect.getsource(teslim_kutusu)
    assert "deger_havuzu_seed" not in kaynak and "havuzlari_kur" not in kaynak


# ═══════════════════════════════════════════════════════════════════════════
# 2. Eşleme DB'den — `hizmet_eslemesini_yukle`
# ═══════════════════════════════════════════════════════════════════════════

def test_esleme_bos_tabloda_seed_sabitine_duser(bos_ortam):
    db = bos_ortam()
    try:
        harita = hukdok_aktarim.hizmet_eslemesini_yukle(db)
    finally:
        db.close()
    assert harita == hukdok_aktarim.HIZMET_TURU_ESLEMESI
    assert harita is not hukdok_aktarim.HIZMET_TURU_ESLEMESI     # kopya: varsayılan kirlenmez


def test_esleme_db_listesinden_kurulur_pasif_dahil_ilk_yazim_kazanir(bos_ortam):
    """Liste doluysa eşleme YALNIZ listedir (seed'e bakılmaz): değer listenin
    yazımı, anahtar harf/aksan duyarsız; pasif ad da tanınır; yalnız yazımı
    farklı ikiz satırda liste sırasındaki ilk ad kazanır."""
    db = bos_ortam()
    try:
        db.add(models.ServiceType(code="A", name="Takip (Doktor Müvekkil)", active=True, sequence=0))
        db.add(models.ServiceType(code="B", name="Yeni Hizmet X", active=False, sequence=1))
        db.add(models.ServiceType(code="C", name="YENİ HİZMET X", active=True, sequence=2))
        db.commit()
        harita = hukdok_aktarim.hizmet_eslemesini_yukle(db)
    finally:
        db.close()
    assert harita == {
        "TAKIPDOKTORMUVEKKIL": "Takip (Doktor Müvekkil)",
        "YENIHIZMETX": "Yeni Hizmet X",
    }
    assert "LEXISRAPOR" not in harita                 # seed adı listede yoksa tanınmaz


def test_kosu_eslemesi_kosu_disina_sizmaz_hata_yolunda_da(ortam, tmp_path, monkeypatch):
    """Koşu eşlemesi koşuya özeldir: koşu bitince (hata yolunda da) varsayılana
    dönülür — aynı süreçteki sonraki koşu/test önceki DB'nin listesini görmez."""
    db = ortam()
    try:
        db.add(models.ServiceType(code="YENI_HIZMET_X", name="Yeni Hizmet X", active=True, sequence=9))
        db.commit()
    finally:
        db.close()
    satirlar = [_satir("H-1", "D-1", "Ak Sigorta A.Ş.", "yeni hizmet x")]

    sonuc = _kos(ortam, tmp_path, satirlar)

    assert sonuc.hizmet_eklenen == 1 and _foy_hizmetleri(ortam) == {"H-1": "Yeni Hizmet X"}
    assert hukdok_aktarim.hizmet_eslemesi() is hukdok_aktarim.HIZMET_TURU_ESLEMESI
    assert set(hukdok_aktarim.HIZMET_TURU_ESLEMESI.values()) == SEED_ADLARI
    with pytest.raises(AlanHatasi):
        hukdok_aktarim._hizmet_turu("Yeni Hizmet X", "hizmet_turu")

    def _patla(*_a, **_kw):
        # Koşunun ORTASINDA eşleme DB'den kurulmuş olmalı; sonra koşu düşer.
        assert hukdok_aktarim._hizmet_turu("yeni hizmet x", "hizmet_turu") == "Yeni Hizmet X"
        raise RuntimeError("koşu ortasında beklenmeyen hata")

    monkeypatch.setattr(hukdok_aktarim, "kapsam_isaretlerini_yaz", _patla)
    with pytest.raises(RuntimeError, match="koşu ortasında"):
        _kos(ortam, tmp_path, satirlar)
    assert hukdok_aktarim.hizmet_eslemesi() is hukdok_aktarim.HIZMET_TURU_ESLEMESI


# ═══════════════════════════════════════════════════════════════════════════
# 3. Uçtan uca — seed'siz aktarım → seed kuru koşu → --apply → aktarım
# ═══════════════════════════════════════════════════════════════════════════

def _uctan_uca(fabrika, tmp_path):
    """Kabul 3. `fabrika`: hizmet listesi 9 seed adıyla kurulu, D-1/D-2 kartları açık.

    Paket listede OLMAYAN "Yeni Hizmet X" adını iki föyde (biri küçük harfle)
    ve listedeki bir adı BÜYÜK yazımla taşır."""
    paket = _paket_yaz(tmp_path / "HUKDOK_TESLIM_g257.xlsx", [
        _satir("H-1", "D-1", "Ak Sigorta A.Ş.", "Yeni Hizmet X"),
        _satir("H-3", "D-1", "Dr. Veli Can", "yeni hizmet x"),
        _satir("H-2", "D-2", "Dr. Ali Veli", "LEXIS RAPOR"),
    ])
    rapor = tmp_path / "rapor"

    # (a) Seed koşulmadan aktarım: yeni ad föyde HAM kalır, satır yazılmaz, UYARI (G249).
    seedsiz = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=rapor)
    assert seedsiz.cikis_kodu == CIKIS_TAMAM and seedsiz.hatalar == []
    assert (seedsiz.hizmet_eklenen, seedsiz.hizmet_listede_yok) == (1, 2)
    uyarilar = _uyarilar(seedsiz)
    assert set(uyarilar) == {"H-1", "H-3"} and len(seedsiz.rapor_satirlari) == 2
    assert "hizmet türü listede yok" in uyarilar["H-1"] and "Yeni Hizmet X" in uyarilar["H-1"]
    assert _foy_hizmetleri(fabrika) == {
        "H-1": "Yeni Hizmet X", "H-3": "yeni hizmet x", "H-2": "Lexis Rapor"}
    assert _satir_hizmetleri(fabrika) == {"H-2": "Lexis Rapor"}
    assert _ozetler(fabrika) == {"D-1": None, "D-2": "Lexis Rapor"}

    # (b) Seed kuru koşu: "1 yeni", listeye YAZMAZ; mevcut ada (BÜYÜK yazım) dokunmaz.
    kuru = {s.liste_adi: s for s in seed.havuzlari_kur(fabrika, girdi=paket)}
    hizmet = kuru["service_types"]
    assert (hizmet.sutun, hizmet.mevcut, hizmet.yeni, hizmet.ornekler) == (
        "Hizmet Türü", 9, 1, ["Yeni Hizmet X"])
    assert sum(s.yeni for s in kuru.values()) == 1
    assert "kuru koşu, yazılmadı" in seed.ozet_metni(list(kuru.values()), apply=False)
    assert _liste_adlari(fabrika) == SEED_ADLARI

    # (c) --apply listeye ekler (sona, aktif, kodu addan); ikinci seed koşusu 0.
    yazan = {s.liste_adi: s.yeni for s in seed.havuzlari_kur(fabrika, girdi=paket, apply=True)}
    assert yazan["service_types"] == 1
    liste = _liste(fabrika)
    assert [(kod, ad) for kod, ad, _aktif, _sira in liste[:9]] == list(seed_data.SERVICE_TYPES)
    assert liste[9] == ("YENI_HIZMET_X", "Yeni Hizmet X", True, 9)
    assert len(liste) == 10
    tekrar = seed.havuzlari_kur(fabrika, girdi=paket, apply=True)
    assert sum(s.yeni for s in tekrar) == 0 and len(_liste(fabrika)) == 10

    # (d) Aktarım yeni adı TANIR: föyde kanonik ad, föy satırı yazılı, kart özeti doğru.
    seedli = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=rapor)
    assert seedli.cikis_kodu == CIKIS_TAMAM and seedli.rapor_satirlari == []
    assert (seedli.hizmet_eklenen, seedli.hizmet_listede_yok) == (2, 0)
    assert _foy_hizmetleri(fabrika) == {
        "H-1": "Yeni Hizmet X", "H-3": "Yeni Hizmet X", "H-2": "Lexis Rapor"}
    assert _satir_hizmetleri(fabrika) == {
        "H-1": "Yeni Hizmet X", "H-3": "Yeni Hizmet X", "H-2": "Lexis Rapor"}
    assert _ozetler(fabrika) == {"D-1": "Yeni Hizmet X", "D-2": "Lexis Rapor"}

    # (e) Aynı paketle bir koşu daha: hizmet satırı da föy de değişmez.
    ucuncu = aktarimi_kos(fabrika, girdi=paket, rapor_dizini=rapor)
    assert (ucuncu.hizmet_eklenen, ucuncu.hizmet_guncellenen, ucuncu.hizmet_silinen) == (0, 0, 0)
    assert ucuncu.hizmet_listede_yok == 0 and ucuncu.rapor_satirlari == []
    assert len(_satir_hizmetleri(fabrika)) == 3


def test_uctan_uca_yeni_hizmet_once_seed_sonra_aktarim(ortam, tmp_path):
    _uctan_uca(ortam, tmp_path)


def test_kuru_kosu_da_listeye_dbden_bakar(ortam, tmp_path):
    """Panelin "Kuru koş"u da `aktarimi_kos`tan geçer: listedeki yeni ad kuru
    koşuda tanınır (farkta hizmet satırı görünür, UYARI yok), hiçbir şey yazılmaz."""
    db = ortam()
    try:
        db.add(models.ServiceType(code="YENI_HIZMET_X", name="Yeni Hizmet X", active=True, sequence=9))
        db.commit()
    finally:
        db.close()

    sonuc = _kos(ortam, tmp_path, [_satir("H-1", "D-1", "Ak Sigorta A.Ş.", "YENI HIZMET X")], dry_run=True)

    assert sonuc.dry_run and not sonuc.yazildi
    assert (sonuc.hizmet_eklenen, sonuc.hizmet_listede_yok) == (1, 0) and sonuc.rapor_satirlari == []
    assert _foy_hizmetleri(ortam) == {} and _satir_hizmetleri(ortam) == {}


def test_bos_listede_davranis_eskisi_gibi_seed_adlari_taninir(bos_ortam, tmp_path):
    """Tablo BOŞ (seed'i koşmamış kurulum): eşleme seed sabitine düşer — seed adı
    kanonik yazımla föye ve satıra gider (hizmet kapısı da boş listede atlanır)."""
    db = bos_ortam()
    try:
        _kart(db, "HA.G257.1", "D-1")
        db.commit()
    finally:
        db.close()

    sonuc = _kos(bos_ortam, tmp_path, [_satir("H-1", "D-1", "Ak Sigorta A.Ş.", "TAKIP DOKTOR MUVEKKIL")])

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.hizmet_eklenen == 1
    assert _foy_hizmetleri(bos_ortam) == {"H-1": "Takip (doktor müvekkil)"}
    assert _satir_hizmetleri(bos_ortam) == {"H-1": "Takip (doktor müvekkil)"}


# ═══════════════════════════════════════════════════════════════════════════
# 4. Panelden yeniden adlandırma — yazım değişikliği eşlenir, kelime değişikliği eşlenmez
# ═══════════════════════════════════════════════════════════════════════════

def test_yalniz_yazimi_degisen_ad_listenin_yazimina_eslenir(ortam, tmp_path):
    """G256 notu: panel adı `tr_title`'dan geçirir ("Takip (Doktor Müvekkil)");
    paket eski yazımı ("Takip (doktor müvekkil)") gönderse de eşleme harf/aksan
    duyarsızdır → föye ve satıra LİSTENİN yazımı gider, uyarı yok. (Eski kodda
    föye seed yazımı giderdi ve satır kapısı adı birebir bulamayıp UYARI'ya düşerdi.)"""
    _adi_degistir(ortam, "Takip (doktor müvekkil)", "Takip (Doktor Müvekkil)")

    sonuc = _kos(ortam, tmp_path, [_satir("H-1", "D-1", "Dr. Ali Veli", "Takip (doktor müvekkil)")])

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.rapor_satirlari == []
    assert (sonuc.hizmet_eklenen, sonuc.hizmet_listede_yok) == (1, 0)
    assert _foy_hizmetleri(ortam) == {"H-1": "Takip (Doktor Müvekkil)"}
    assert _satir_hizmetleri(ortam) == {"H-1": "Takip (Doktor Müvekkil)"}
    assert _ozetler(ortam)["D-1"] == "Takip (Doktor Müvekkil)"


def test_kelimesi_degisen_ad_taninmaz_uyari_yoluna_duser(ortam, tmp_path):
    """Kabul 4 (BEKLENEN davranış, sabitlenir): DB'de "Lexis Rapor" → "Lexis
    Raporu", paket hâlâ "Lexis Rapor" gönderiyor → aktarım eski adı TANIMAZ;
    föyde ham kalır, satır yazılmaz, G249 UYARI yolu (HATA değil)."""
    _adi_degistir(ortam, "Lexis Rapor", "Lexis Raporu")

    sonuc = _kos(ortam, tmp_path, [_satir("H-1", "D-1", "Ak Sigorta A.Ş.", "Lexis Rapor")])

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.hatalar == []
    assert (sonuc.hizmet_eklenen, sonuc.hizmet_listede_yok) == (0, 1)
    uyarilar = _uyarilar(sonuc)
    assert set(uyarilar) == {"H-1"} and len(sonuc.rapor_satirlari) == 1
    assert "hizmet türü listede yok" in uyarilar["H-1"] and "'Lexis Rapor'" in uyarilar["H-1"]
    assert _foy_hizmetleri(ortam) == {"H-1": "Lexis Rapor"}
    assert _satir_hizmetleri(ortam) == {} and _ozetler(ortam)["D-1"] is None
    assert "Lexis Raporu" in _liste_adlari(ortam) and "Lexis Rapor" not in _liste_adlari(ortam)


# ═══════════════════════════════════════════════════════════════════════════
# 5. deger_havuzu_seed — hizmet havuzu + --kaldir satır bağı
# ═══════════════════════════════════════════════════════════════════════════

def test_seed_yeni_adi_ekler_mevcuda_dokunmaz_yer_tutucu_dusurur(ortam, tmp_path):
    """Kabul 1: `havuzu_isle` davranışı diğer havuzlarla aynı — sık geçen ad önce,
    mevcut ad (büyük/küçük harf duyarsız) atlanır, yer tutucu düşer, hiçbir satır
    silinmez/yeniden adlandırılmaz."""
    _adi_degistir(ortam, "Danışmanlık", "Danışmanlık Hizmeti")     # panel düzeltmesi korunur
    paket = _paket_yaz(tmp_path / "p.xlsx", [
        _satir("H-1", "D-1", hizmet="Lexis Rapor"),
        _satir("H-2", "D-1", hizmet="lexis rapor"),
        _satir("H-3", "D-1", hizmet="Bilirkişi Raporu"),
        _satir("H-4", "D-1", hizmet="Arabuluculuk"),
        _satir("H-5", "D-1", hizmet="Arabuluculuk"),
        _satir("H-6", "D-1", hizmet="-"),
        _satir("H-7", "D-1", hizmet=None),
    ])

    sonuc = {s.liste_adi: s for s in seed.havuzlari_kur(ortam, girdi=paket, apply=True)}

    assert (sonuc["service_types"].mevcut, sonuc["service_types"].yeni) == (9, 2)
    assert sonuc["service_types"].ornekler == ["Arabuluculuk", "Bilirkişi Raporu"]   # sıklık sırası
    liste = _liste(ortam)
    assert liste[9:] == [("ARABULUCULUK", "Arabuluculuk", True, 9),
                         ("BILIRKISI_RAPORU", "Bilirkişi Raporu", True, 10)]
    assert {ad for _k, ad, _a, _s in liste[:9]} == (SEED_ADLARI - {"Danışmanlık"}) | {"Danışmanlık Hizmeti"}
    assert sum(s.yeni for s in seed.havuzlari_kur(ortam, girdi=paket, apply=True)) == 0


@pytest.fixture()
def kullanilan_hizmetler(ortam):
    """D-1 kartında iki müvekkil: föy kaynaklı "Lexis Rapor" + elle "Danışmanlık".
    Kart özeti " ; " birleşiktir → kolon eşitliği iki adı da "kullanılmıyor" sayar;
    gerçek kullanım `case_hizmetleri` satır bağındadır."""
    db = ortam()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        sigorta = _taraf(db, kart, "Ak Sigorta A.Ş.")
        doktor = _taraf(db, kart, "Dr. Ali Veli")
        case_hizmetleri.foydan_yaz(db, _foy(db, kart, sigorta, "H-1", "Lexis Rapor"))
        case_hizmetleri.elle_ekle(db, kart, doktor.id, "Danışmanlık", changed_by="Avukat", source="panel")
        db.commit()
        assert kart.hizmet_turu == "Danışmanlık ; Lexis Rapor"
    finally:
        db.close()
    return ortam


def test_kaldir_hizmet_satirinda_kullanilan_adi_silmez_sayiyla_raporlar(kullanilan_hizmetler):
    """Kabul 1: `--kaldir` `service_types` için de çalışır; `case_hizmetleri`
    satırında kullanılan ad SİLİNMEZ ve kullanım sayısıyla raporlanır
    (`reference_lists.bagimliliklar` — yalnız `DEPENDENCIES` okunsaydı 0 sayılırdı)."""
    adlar = ["lexis rapor", "Danışmanlık", "Vekaletsiz Takip", "Yok Böyle"]

    kuru = seed.havuz_satirlarini_kaldir(kullanilan_hizmetler, liste_adi="service_types", adlar=adlar)

    lexis, danismanlik, vekaletsiz, yok = kuru
    assert (lexis.bulunan, lexis.kart_kullanimi, lexis.asama_kullanimi) == ("Lexis Rapor", 1, 0)
    assert (danismanlik.bulunan, danismanlik.kart_kullanimi) == ("Danışmanlık", 1)
    assert lexis.kullaniliyor and danismanlik.kullaniliyor
    assert vekaletsiz.bulunan == "Vekaletsiz Takip" and not vekaletsiz.kullaniliyor
    assert yok.bulunan is None
    assert not any(s.silindi for s in kuru)                       # kuru koşu varsayılan
    assert _liste_adlari(kullanilan_hizmetler) == SEED_ADLARI
    ozet = seed.kaldirma_ozeti(kuru, apply=False)
    assert "KULLANILIYOR — silinmedi" in ozet and "silinebilir (kuru koşu)" in ozet

    yazan = seed.havuz_satirlarini_kaldir(
        kullanilan_hizmetler, liste_adi="service_types", adlar=adlar, apply=True)

    assert [s.silindi for s in yazan] == [False, False, True, False]
    assert _liste_adlari(kullanilan_hizmetler) == SEED_ADLARI - {"Vekaletsiz Takip"}
    assert "silinen satır: 1 — YAZILDI" in seed.kaldirma_ozeti(yazan, apply=True)


def test_kaldir_tek_hizmetli_kartta_ozet_ve_satir_birlikte_sayilir(ortam):
    """Tek hizmetli kartta ad hem özet kolonunda hem satırda geçer: iki bağ toplanır."""
    db = ortam()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-2").one()
        case_hizmetleri.foydan_yaz(
            db, _foy(db, kart, _taraf(db, kart, "Dr. Ali Veli"), "H-9", "Vekaletli Takip"))
        db.commit()
        assert seed.satir_kullanimi(db, "service_types", "Vekaletli Takip") == (2, 0)
        assert seed.satir_kullanimi(db, "service_types", "Lexis Rapor") == (0, 0)
    finally:
        db.close()


def test_cli_kaldir_liste_secenegi_hizmet_listesini_kabul_eder(kullanilan_hizmetler, monkeypatch, capsys):
    import database

    monkeypatch.setattr(database, "SessionLocal", kullanilan_hizmetler)

    assert seed.main(["--liste", "service_types", "--kaldir", "Lexis Rapor"]) == 0

    cikti = capsys.readouterr().out
    assert "service_types" in cikti and "KULLANILIYOR — silinmedi" in cikti
    assert "kuru koşu, yazılmadı" in cikti
    assert _liste_adlari(kullanilan_hizmetler) == SEED_ADLARI


# ═══════════════════════════════════════════════════════════════════════════
# 6. dbtest — gerçek Postgres (scratch DB; yoksa SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_admin():
    """test_migration_path.admin_engine'in yereli (fixture import F811 üretir)."""
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")
    admin = create_engine(
        url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        admin.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G257 dbtest atlandı")
    yield admin
    admin.dispose()


@pytest.mark.dbtest
def test_pg_uctan_uca_yeni_hizmet_once_seed_sonra_aktarim(pg_admin, tmp_path):
    """Kabul 3, gerçek şemada: migrasyonlu scratch veritabanında aynı akış
    (seed'siz aktarım → kuru seed → --apply → aktarım tanır). Gerçek
    veritabanına dokunulmaz; scratch DB test sonunda düşürülür."""
    with _scratch_database(pg_admin, "g257") as engine:
        _run_init_db(engine)
        fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        db = fabrika()
        try:
            if db.query(models.ServiceType).count() == 0:
                _hizmet_listesini_kur(db)
            for i in (1, 2):
                _kart(db, f"HA.G257.{i}", f"D-{i}")
            db.commit()
        finally:
            db.close()
        assert _liste_adlari(fabrika) == SEED_ADLARI

        _uctan_uca(fabrika, tmp_path)
