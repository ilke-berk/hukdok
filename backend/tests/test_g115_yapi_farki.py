"""G115 — Teslim yapı farkı: `aktarim_teslimleri.yapi` + `teslim_kutusu.yapi_farki` +
kapı kuralı `yapi_degisti` + bildirim gövdesi bloğu + `ozet.txt` "yapı farkı" satırları.

Sözleşme: gorevler/gorev/G115.md. Bilgilendirme belgesi (§5) veri ekibinden sütun/sayfa
değişikliğini önceden bildirmesini istiyor; bu dosya sistemin bunu KENDİSİNİN yakaladığını
kilitler: tanınmayan başlık sessizce atlanmaz, kaybolan başlık/sayfa "yok" sayılmaz.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; paketler
test_g107'nin sentetik üreticisiyle (`_paket`) openpyxl'den üretilir.

Katmanlar:

1. **Birim** — migrasyon op'u, `yapi_farki` (altı parametrik durum), `basliklari_tani`,
   kısaltma, serializer.
2. **sqlite (StaticPool)** — doğrulama `yapi`yi doldurur (red yolunda da), kapı,
   bildirim gövdesi + dedupe, `ozet.txt`, log sözleşmesi.
3. **dbtest (gerçek Postgres, scratch DB)** — kolon sıfırdan `create_all`'dan, mevcut
   kurulumda `ALTER TABLE ADD COLUMN`'dan geliyor; ikinci koşu idempotent (3-ortam kuralı).
"""
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from database import _MIGRATIONS, Base
from schemas import AktarimTeslimiOut, AktarimTeslimiOzetOut
from scripts import hukdok_aktarim
from services import teslim_kutusu as tk
from test_g107_teslim_kutusu import BASLIKLAR, _defter, _iki_satir, _index_ops, _kart, _paket, _uc_satir
from test_migration_path import _live_columns, _run_init_db, _scratch_database

ONCEKI = "HUKDOK_TESLIM_ONCEKI.xlsx"
TESLIM = "HUKDOK_TESLIM_YENI.xlsx"
ADMIN = "yonetici@hanyaloglu-acar.av.tr"

#: Önceki uygulanmış teslimin yapısı — bugünkü sentetik paketle AYNI başlık/sayfa kümesi.
ONCEKI_YAPI = {
    "sayfalar": ["Sheet", "DEGISIKLIK_OZETI"],
    "basliklar": list(BASLIKLAR),
    "taninan": ["sistem_no", "tku_no", "hasar_no", "dosya_no", "arsiv_tarihi", "tibbi_olay"],
    "taninmayan": [],
}


def _yapi(**degisiklik) -> dict:
    return {**ONCEKI_YAPI, **degisiklik}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim
# ═══════════════════════════════════════════════════════════════════════════

def test_migrasyon_yapi_kolonu_columns_opunda_indexsiz():
    """Kabul: `yapi` kolonu ("columns", "aktarim_teslimleri", …) op'unda, JSON; index yok."""
    oplar = [op for op in _MIGRATIONS if op[0] == "columns" and op[1] == "aktarim_teslimleri"]
    assert len(oplar) == 1 and set(oplar[0][2]) == {"yapi"}
    assert oplar[0][2]["yapi"] == "JSON"
    assert not any("yapi" in sql for sql in _index_ops("aktarim_teslimleri"))
    assert "yapi" in {c.name for c in models.AktarimTeslimi.__table__.columns}
    assert models.AktarimTeslimi.__table__.columns["yapi"].nullable is True


@pytest.mark.parametrize("onceki,simdiki,beklenen", [
    # (a) önceki yok → yalnız taninmayan_basliklar
    (None, _yapi(basliklar=BASLIKLAR + ["Ekstra"], taninmayan=["Ekstra"]),
     {"yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": [], "kaybolan_sayfalar": [],
      "taninmayan_basliklar": ["Ekstra"]}),
    # (b) aynı başlık aksan/boşluk/harf farkıyla → fark YOK
    (_yapi(), _yapi(basliklar=["SISTEMNO", "tku", "HASAR  NO", "Dosya no", "ARSIV TARIHI", "Tibbi olay"]),
     {"yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": [], "kaybolan_sayfalar": [],
      "taninmayan_basliklar": []}),
    # (c) yeni sütun → yeni_basliklar (ham yazım)
    (_yapi(), _yapi(basliklar=BASLIKLAR + ["Yeni Sütun"], taninmayan=["Yeni Sütun"]),
     {"yeni_basliklar": ["Yeni Sütun"], "kaybolan_basliklar": [], "yeni_sayfalar": [],
      "kaybolan_sayfalar": [], "taninmayan_basliklar": ["Yeni Sütun"]}),
    # (d) kaybolan sütun → kaybolan_basliklar (ÖNCEKİ paketin ham yazımıyla)
    (_yapi(), _yapi(basliklar=[b for b in BASLIKLAR if b != "Tıbbi Olay"]),
     {"yeni_basliklar": [], "kaybolan_basliklar": ["Tıbbi Olay"], "yeni_sayfalar": [],
      "kaybolan_sayfalar": [], "taninmayan_basliklar": []}),
    # (e) Karar_Asamalari kaybolmuş → kaybolan_sayfalar; yeni izlenen sayfa → yeni_sayfalar
    (_yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]),
     _yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Düzeltme_Logu"]),
     {"yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": ["Düzeltme_Logu"],
      "kaybolan_sayfalar": ["Karar_Asamalari"], "taninmayan_basliklar": []}),
    # (f) SUTUN_SOZLUGU (okunmayan sayfa) kaybolmuş / gelmiş → fark YOK
    (_yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "SUTUN_SOZLUGU"]),
     _yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "NOTLAR"]),
     {"yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": [], "kaybolan_sayfalar": [],
      "taninmayan_basliklar": []}),
])
def test_yapi_farki_parametrik(onceki, simdiki, beklenen):
    assert tk.yapi_farki(onceki, simdiki) == beklenen


def test_yapi_farki_sayfa_adi_aksan_ve_alt_cizgi_duyarsiz():
    """"Silinen_Föyler" ≡ "SILINEN FOYLER" (hukdok_aktarim kapsam sayfaları da böyle bulur)."""
    fark = tk.yapi_farki(
        _yapi(sayfalar=["Sheet", "Silinen_Föyler", "Kapsam_Dışı"]),
        _yapi(sayfalar=["Sheet", "SILINEN FOYLER", "KAPSAM DISI"]),
    )
    assert fark["yeni_sayfalar"] == [] and fark["kaybolan_sayfalar"] == []
    assert set(tk.IZLENEN_SAYFALAR) == {
        "Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari", "Düzeltme_Logu",
        "DEGER_HAVUZLARI", "Silinen_Föyler", "Kapsam_Dışı",
    }


def test_basliklari_tani_sutun_adaylari_uzerinden():
    """Tanıma `hukdok_aktarim.SUTUN_ADAYLARI` × `_baslik_anahtari`: "Klasör No" TKU'dur,
    "Klasör No.2" dosya no; bilinmeyen ham başlık `taninmayan`a girer."""
    taninan, taninmayan = tk.basliklari_tani(
        ["SistemNo", "Klasör No", "Klasör No.2", "ARSIV TARIHI", "Bilinmeyen Sütun", "", "SistemNo"]
    )
    assert taninan == ["sistem_no", "tku_no", "dosya_no", "arsiv_tarihi"]
    assert taninmayan == ["Bilinmeyen Sütun"]
    assert all(alan in hukdok_aktarim.SUTUN_ADAYLARI for alan in taninan)


def test_fark_kalemleri_kategori_basina_20_sinir_ve_taninmayan_disarida():
    cok = [f"S{i}" for i in range(25)]
    fark = {"yeni_basliklar": cok, "kaybolan_basliklar": ["K"], "yeni_sayfalar": ["Y"],
            "kaybolan_sayfalar": ["KS"], "taninmayan_basliklar": cok}
    kalemler = tk.fark_kalemleri(fark)
    yeni = [ad for etiket, ad in kalemler if etiket == "yeni başlık"]
    assert len(yeni) == 21 and yeni[-1] == "… (+5)" and yeni[:20] == cok[:20]
    assert ("kaybolan başlık", "K") in kalemler and ("kaybolan sayfa", "KS") in kalemler
    assert ("yeni sayfa", "Y") in kalemler
    assert not any("tanınmayan" in etiket for etiket, _ in kalemler)
    assert tk.fark_kalemleri(None) == [] and tk.fark_kalemleri({"taninmayan_basliklar": cok}) == []
    assert tk.KAPI_YAPI_DEGISTI == "yapi_degisti" and "yapi_degisti" in tk.KAPI_KURALLARI


def test_serializer_yapi_farki_model_propertysinden_yapi_liste_disi():
    """`AktarimTeslimiOzetOut`/`AktarimTeslimiOut.yapi_farki` = `yapi["fark"]`; `yapi` serileşmez."""
    fark = tk.yapi_farki(_yapi(), _yapi(basliklar=BASLIKLAR + ["Ek"], taninmayan=["Ek"]))
    teslim = models.AktarimTeslimi(id=7, dosya_adi="x.xlsx", sha256="0" * 64, kaynak="yukleme",
                                   durum="kuru_kosuldu", yapi={**_yapi(), "fark": fark})
    assert teslim.yapi_farki == fark
    for sema in (AktarimTeslimiOzetOut, AktarimTeslimiOut):
        cikti = sema.model_validate(teslim).model_dump()
        assert cikti["yapi_farki"] == fark and "yapi" not in cikti
    assert models.AktarimTeslimi(yapi=None).yapi_farki is None
    assert models.AktarimTeslimi(yapi=_yapi()).yapi_farki is None           # fark henüz yok


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite — doğrulama / kapı / bildirim / özet
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """sqlite (FK + çalışan SAVEPOINT + defter/bildirim index'leri) + spool + iki kart + ADMIN_EMAILS."""
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
            _kart(db, f"HA.G115.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()
    yield SimpleNamespace(db=maker)
    engine.dispose()


def _onceki_uygulandi(db, yapi=ONCEKI_YAPI):
    return _defter(db, dosya_adi=ONCEKI, sha256="b" * 64, durum=tk.DURUM_UYGULANDI, yapi=yapi)


def _bildirimler(db):
    return (
        db.query(models.Notification)
        .filter(models.Notification.type == tk.BILDIRIM_TURU)
        .order_by(models.Notification.id)
        .all()
    )


def _ozet(db, tid) -> str:
    rapor = Path(db.get(models.AktarimTeslimi, tid).rapor_dizini)
    return (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8")


def test_dogrula_yapiyi_doldurur_sayfalar_basliklar_taninan_taninmayan(env):
    """Kabul: sentetik pakette `yapi` = sayfalar + ham başlıklar + tanınan alan adları +
    tanınmayan ham başlıklar; önceki teslim yok → fark yalnız tanınmayan; log WARNING/ERROR yok."""
    db = env.db()
    try:
        icerik = _paket(_uc_satir(), basliklar=BASLIKLAR + ["Yeni Sütun"], ozet="—")
        tid = tk.teslim_kaydet(icerik=icerik, dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid, db=db) == "dogrulandi"
        yapi = db.get(models.AktarimTeslimi, tid).yapi
        assert yapi["sayfalar"] == ["Sheet", "DEGISIKLIK_OZETI"]
        assert yapi["basliklar"] == BASLIKLAR + ["Yeni Sütun"]
        assert yapi["taninan"] == ["sistem_no", "tku_no", "hasar_no", "dosya_no", "arsiv_tarihi", "tibbi_olay"]
        assert yapi["taninmayan"] == ["Yeni Sütun"]
        assert yapi["fark"] == {
            "yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": [],
            "kaybolan_sayfalar": [], "taninmayan_basliklar": ["Yeni Sütun"],
        }
    finally:
        db.close()


@pytest.mark.parametrize("paket_args,beklenen_basliklar", [
    ({"veri_sayfasi": "Veri"}, []),                                        # 'Sheet' yok
    ({"basliklar": ["SistemNo", "TKU"]}, ["SistemNo", "TKU"]),              # zorunlu 'Dosya No' yok
])
def test_dogrula_reddedildi_yolunda_da_sayfalar_dolu(env, paket_args, beklenen_basliklar):
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_uc_satir(), **paket_args), dosya_adi=TESLIM,
                               kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid, db=db) == "reddedildi"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.yapi["sayfalar"] == [paket_args.get("veri_sayfasi", "Sheet")]
        assert teslim.yapi["basliklar"] == beklenen_basliklar
        assert "fark" not in teslim.yapi and teslim.yapi_farki is None
    finally:
        db.close()


def test_yeni_baslik_kapi_inceleme_gerekce_bildirim_ozet_log(env, caplog):
    """Kabul (kapı + bildirim + özet + log): önceki uygulandı teslime göre YENİ başlık →
    `inceleme_bekliyor`, gerekçede `yapi_degisti` + başlık adı; bildirim gövdesinde
    "Yapı farkı:" bloğu; `ozet.txt`'de "yapı farkı" satırı ve kapı satırı SON;
    fark tek WARNING, ERROR yok; dedupe anahtarı değişmedi."""
    db = env.db()
    try:
        _onceki_uygulandi(db)
        icerik = _paket(_iki_satir(), basliklar=BASLIKLAR + ["Yeni Sütun"], ozet=f"{ONCEKI} · 2 satır")
        tid = tk.teslim_kaydet(icerik=icerik, dosya_adi=TESLIM, kaynak="yukleme", db=db)
        with caplog.at_level(logging.WARNING, logger="services.teslim_kutusu"):
            assert tk.teslimi_isle(tid, otomatik_uygula=True, db=db) == "inceleme_bekliyor"

        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.kapi_karari == "inceleme"
        assert teslim.kapi_gerekcesi == "yapi_degisti (yeni: Yeni Sütun)"      # tek ihlal: sayaçlar eşik içi
        assert teslim.yapi_farki["yeni_basliklar"] == ["Yeni Sütun"]
        assert teslim.yapi_farki["taninmayan_basliklar"] == ["Yeni Sütun"]
        assert teslim.uygulayan is None                                           # otomatik uygulanmadı

        bildirimler = _bildirimler(db)
        assert len(bildirimler) == 1
        assert bildirimler[0].body == "Kapı: yapi_degisti (yeni: Yeni Sütun)\nYapı farkı:\n  yeni başlık: Yeni Sütun"
        assert bildirimler[0].dedupe_key == tk.bildirim_dedupe_key(tid, "inceleme_bekliyor", ADMIN)
        assert tk.bildir(tid, "inceleme_bekliyor", db=db) == [bildirimler[0].id]  # ikinci kez üretmez
        assert len(_bildirimler(db)) == 1

        ozet = _ozet(db, tid)
        satirlar = ozet.rstrip().splitlines()
        assert "  yapı farkı        : yeni başlık: Yeni Sütun" in satirlar
        assert satirlar[-1] == "  kapı kararı       : inceleme — yapi_degisti (yeni: Yeni Sütun)"
        assert ozet.count("yapı farkı") == 1 and ozet.count("kapı kararı") == 1

        uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING and "yapı farkı" in r.getMessage()]
        assert len(uyarilar) == 1 and "yeni başlık: Yeni Sütun" in uyarilar[0].getMessage()
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    finally:
        db.close()


def test_yalniz_taninmayan_onceki_teslimde_de_vardi_kapi_etkilenmez(env):
    """Kabul: önceki `uygulandi` teslimde de bulunan tanınmayan başlık + eşik içi sayaçlar +
    aynı yapı → `otomatik`; bildirim yok; `ozet.txt` "yapı farkı: yok"."""
    db = env.db()
    try:
        _onceki_uygulandi(db, yapi=_yapi(basliklar=BASLIKLAR + ["Okunmayan"], taninmayan=["Okunmayan"]))
        icerik = _paket(_iki_satir(), basliklar=BASLIKLAR + ["OKUNMAYAN"], ozet=f"{ONCEKI} · 2 satır")
        tid = tk.teslim_kaydet(icerik=icerik, dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "kuru_kosuldu"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.kapi_karari == "otomatik" and teslim.kapi_gerekcesi is None
        assert teslim.yapi_farki == {
            "yeni_basliklar": [], "kaybolan_basliklar": [], "yeni_sayfalar": [],
            "kaybolan_sayfalar": [], "taninmayan_basliklar": ["OKUNMAYAN"],
        }
        assert _bildirimler(db) == []
        satirlar = _ozet(db, tid).rstrip().splitlines()
        assert "  yapı farkı        : yok" in satirlar
        assert satirlar[-1] == "  kapı kararı       : otomatik"
    finally:
        db.close()


def test_kaybolan_baslik_ve_sayfa_gerekcede_yeni_sayfa_bilgi(env):
    """Kaybolan başlık/sayfa ihlal (gerekçede adıyla); yalnız yeni sayfa → otomatik, bildirim yok."""
    db = env.db()
    try:
        _onceki_uygulandi(db, yapi=_yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]))
        tid = _defter(db, yapi={**_yapi(), "fark": tk.yapi_farki(
            _yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Karar_Asamalari"]),
            _yapi(basliklar=[b for b in BASLIKLAR if b != "Hasar No"]),
        )})
        assert tk.kapi_degerlendir(tid, db=db) == "inceleme"
        gerekce = db.get(models.AktarimTeslimi, tid).kapi_gerekcesi
        assert gerekce == "yapi_degisti (kaybolan: Hasar No; kaybolan sayfa: Karar_Asamalari)"

        tid2 = _defter(db, sha256="c" * 64, yapi={**_yapi(), "fark": tk.yapi_farki(
            _yapi(), _yapi(sayfalar=["Sheet", "DEGISIKLIK_OZETI", "Düzeltme_Logu"]),
        )})
        assert tk.kapi_degerlendir(tid2, db=db) == "otomatik"
        assert db.get(models.AktarimTeslimi, tid2).kapi_gerekcesi is None
        assert _bildirimler(db) == []
    finally:
        db.close()


def test_onceki_yapi_en_son_uygulandi_teslimden_null_yapi_bilinmiyor(env):
    """"Önceki" = en son `uygulandi` teslim; onun `yapi`si NULL ise (eski kayıt) fark yalnız tanınmayan."""
    db = env.db()
    try:
        _defter(db, dosya_adi="HUKDOK_TESLIM_ESKI.xlsx", sha256="a" * 64, durum=tk.DURUM_UYGULANDI,
                yapi=_yapi(basliklar=BASLIKLAR + ["Kalkan"]))
        _defter(db, dosya_adi=ONCEKI, sha256="b" * 64, durum=tk.DURUM_UYGULANDI, yapi=None)
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir(), ozet=f"{ONCEKI} · 2 satır"),
                               dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "kuru_kosuldu"
        teslim = db.get(models.AktarimTeslimi, tid)
        assert teslim.kapi_karari == "otomatik"
        assert teslim.yapi_farki["kaybolan_basliklar"] == []                 # ESKİ teslimle kıyaslanmadı
        assert tk._onceki_yapi(db, haric=tid) is None
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. dbtest — gerçek Postgres (scratch DB; 3-ortam kuralı: DB yoksa SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def fresh_db():
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
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — G115 dbtest atlandı")
    try:
        with _scratch_database(admin, "g115") as engine:
            _run_init_db(engine)
            yield engine
    finally:
        admin.dispose()


@pytest.mark.dbtest
def test_pg_yapi_kolonu_sifirdan_ve_mevcut_kurulumda_gelir_ikinci_kosu_idempotent(fresh_db):
    """Kabul: sıfırdan kurulumda kolon `create_all`'dan; kolon düşürülmüş (eski) kurulumda
    `("columns", …)` op'u ALTER ile ekler; ikinci `init_db` şemayı değiştirmez."""
    assert "yapi" in _live_columns(fresh_db)["aktarim_teslimleri"]
    once = _live_columns(fresh_db)
    _run_init_db(fresh_db)                                           # ikinci koşu
    assert _live_columns(fresh_db) == once

    with fresh_db.begin() as conn:
        conn.execute(text("ALTER TABLE aktarim_teslimleri DROP COLUMN yapi"))
    assert "yapi" not in _live_columns(fresh_db)["aktarim_teslimleri"]
    _run_init_db(fresh_db)                                           # eski kurulum yolu: ALTER TABLE ADD
    assert _live_columns(fresh_db) == once
    with fresh_db.connect() as conn:
        tip = conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'aktarim_teslimleri' AND column_name = 'yapi'"
        )).scalar()
    assert tip == "json"
