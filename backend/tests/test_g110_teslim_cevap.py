"""G110 — Cevap paketi: `services/teslim_cevap.py` (eşleşme CSV + SharePoint'e geri
yükleme) ve `teslim_kutusu`'ndaki bağlantı noktaları (`ozet.txt`, `teslim_uygula`
tek deneme, `gece_turu` yeniden deneme).

Plan: docs/plan/veri-teslim-otomasyonu-plani-2026-09-03.md §2.4.

**TEST VERİSİ KURALI (A.2 dersi):** paketler openpyxl ile SENTETİK üretilir
(test_g107 üreticisi). `upload_file_to_sharepoint` HER testte sahtelenir; cevap
klasörü env'i (`SHAREPOINT_FOLDER_TESLIM_NAME`) ve otomasyon anahtarı fixture'da
AÇIKÇA kurulur — ikisi de yükleme kapısıdır (teslim_cevap modül şerhi).
"""
import csv
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import sharepoint.sharepoint_uploader_graph as spu
from database import Base
from scripts import hukdok_aktarim
from services import app_settings
from services import teslim_cevap as tc
from services import teslim_kutusu as tk
from test_g107_teslim_kutusu import _defter, _iki_satir, _index_ops, _kart, _paket, _satir

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
KEY = app_settings.VERI_TESLIM_OTOMASYONU_KEY
ONCEKI = "HUKDOK_TESLIM_ONCEKI.xlsx"
TESLIM = "HUKDOK_TESLIM_X.xlsx"
KLASOR = "03_VERI_TESLIM/cevap/HUKDOK_TESLIM_X"


def _dort_satir():
    """3 eşleşen (D-1, D-2, D-3) + 1 eşleşmeyen (D-YOK) — kabul senaryosu."""
    return [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021"}),
        _satir("SSTMN-2", "D-2", TKU="TKU-200"),
        _satir("SSTMN-3", "D-3"),
        _satir("SSTMN-9", "D-YOK"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Fixture'lar
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """sqlite (FK + SAVEPOINT + defter/föy/bildirim index'leri) + spool + üç kart;
    `teslim_kutusu`/`app_settings.SessionLocal` bu fabrikaya; cevap klasörü env'i kurulu."""
    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "03_VERI_TESLIM")
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
    monkeypatch.setattr(app_settings, "SessionLocal", maker)
    # Gece turunun gözcüsü: boş klasör (bu dosya yüklemeyi test eder, indirmeyi değil)
    monkeypatch.setattr(spu, "list_folder_children", lambda folder_name: [])

    db = maker()
    try:
        for i in (1, 2, 3):
            _kart(db, f"HA.G110.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()

    yield SimpleNamespace(db=maker, spool=tmp_path / "teslim_spool")
    engine.dispose()


@pytest.fixture()
def sahte_upload(monkeypatch):
    """`upload_file_to_sharepoint` yerine kayıt tutan sahte; `patlayan` kümesindeki
    hedef adlar RuntimeError fırlatır."""
    sp = SimpleNamespace(cagrilar=[], patlayan=set())

    def _upload(filepath, target_filename, target_folder_name, content_type="application/pdf", **kw):
        sp.cagrilar.append((Path(filepath).name, target_filename, target_folder_name, content_type))
        if target_filename in sp.patlayan:
            raise RuntimeError(f"Graph 503: {target_filename}")
        return {"id": f"item-{len(sp.cagrilar)}", "name": target_filename}

    monkeypatch.setattr(spu, "upload_file_to_sharepoint", _upload)
    return sp


def _anahtar(env, deger: bool) -> None:
    db = env.db()
    try:
        app_settings.set_setting_bool(KEY, deger, updated_by="test", db=db)
    finally:
        db.close()


def _teslim(env, tid):
    db = env.db()
    try:
        return db.get(models.AktarimTeslimi, tid)
    finally:
        db.close()


def _onceki_uygulandi(env):
    db = env.db()
    try:
        return _defter(db, dosya_adi=ONCEKI, sha256="b" * 64, durum=tk.DURUM_UYGULANDI, cevap_yuklendi=True)
    finally:
        db.close()


def _uygulanmis_teslim(env, satirlar=None, dosya_adi=TESLIM):
    """Paketi kaydet → işle → (kapı incelemeye düşerse) elle uygula; teslim id'sini döner."""
    _onceki_uygulandi(env)
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(satirlar or _dort_satir()), dosya_adi=dosya_adi,
                               kaynak="yukleme", db=db)
        durum = tk.teslimi_isle(tid, otomatik_uygula=False, db=db)
        assert durum in (tk.DURUM_KURU_KOSULDU, tk.DURUM_INCELEME), durum
        assert tk.teslim_uygula(tid, uygulayan="admin@buro.test", db=db) == tk.DURUM_UYGULANDI
    finally:
        db.close()
    return tid


def _csv_satirlari(yol: Path):
    ham = yol.read_bytes()
    assert ham.startswith(b"\xef\xbb\xbf")                      # UTF-8 BOM (byte düzeyinde)
    assert ham.split(b"\r\n", 1)[0] == b"\xef\xbb\xbf" + ";".join(tc.ESLESME_BASLIKLARI).encode()   # `;` ayraç
    with open(yol, "r", newline="", encoding="utf-8-sig") as dosya:
        return [satir for satir in csv.reader(dosya, delimiter=";") if satir]


def _cevap_uyarilari(caplog):
    """Yalnız teslim katmanının (kutusu + cevap) WARNING+ kayıtları — aktarımın satır
    düzeyi WARNING'leri (ATLANDI/HATA) bu testlerin konusu değil."""
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.name.startswith("services.teslim_")]


def _deneme_notlari(teslim):
    return [g["not"] for g in teslim.durum_gecmisi if str(g.get("not") or "").startswith(tc.DENEME_NOTU_ONEKI)]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — klasör adı, CSV biçimi
# ═══════════════════════════════════════════════════════════════════════════

def test_cevap_klasoru_env_zorunlu(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "/03_VERI_TESLIM/")
    assert tc.cevap_klasoru("HUKDOK_TESLIM_X.xlsx") == KLASOR
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "  ")
    assert tc.cevap_klasoru("HUKDOK_TESLIM_X.xlsx") is None
    monkeypatch.delenv("SHAREPOINT_FOLDER_TESLIM_NAME", raising=False)
    assert tc.cevap_klasoru("HUKDOK_TESLIM_X.xlsx") is None
    assert tc.teslim_adi_uzantisiz("HUKDOK_TESLIM_2026-09-10.XLSX") == "HUKDOK_TESLIM_2026-09-10"


def test_csv_bicimi_hukdok_aktarim_csv_yaz_ile_bayt_bayt_ayni(tmp_path):
    """`_csv_yaz` deseni kopyalandı (private) — çıktı hukdok_aktarim'inkiyle bayt düzeyinde eş."""
    satirlar = [("SSTMN-1", "D-1", 7, "HA.1", "D-1", "TKU-1", "", "ESLESTI", ""),
                ("SSTMN-9", "D-YOK", "", "", "", "", "", "ESLESMEDI", "Kart bulunamadı; 'x'")]
    a = tc._csv_yaz(tmp_path / "a.csv", tc.ESLESME_BASLIKLARI, satirlar)
    b = hukdok_aktarim._csv_yaz(tmp_path / "b.csv", tc.ESLESME_BASLIKLARI, satirlar)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes().startswith(b"\xef\xbb\xbf" + ";".join(tc.ESLESME_BASLIKLARI).encode())


def test_eslesme_basliklari_sozlesme():
    assert tc.ESLESME_BASLIKLARI == (
        "sistem_no", "dosya_no", "case_id", "tracking_no", "klasor_no_2",
        "tku_no", "case_party_id", "durum", "sebep",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Eşleşme CSV — sqlite uçtan uca
# ═══════════════════════════════════════════════════════════════════════════

def test_eslesme_csv_uctan_uca_3_eslesen_1_eslesmeyen(env, sahte_upload):
    """Kabul: 3 eşleşen + 1 eşleşmeyen paket uygulandıktan sonra dosyada 4 satır;
    eşleşmeyenin `case_id` boş, `sebep` dolu; BOM + `;` byte düzeyinde."""
    _anahtar(env, True)
    tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    yol = Path(teslim.rapor_dizini) / "eslesme_HUKDOK_TESLIM_X.csv"
    assert yol.is_file()

    satirlar = _csv_satirlari(yol)
    assert satirlar[0] == list(tc.ESLESME_BASLIKLARI)
    veri = satirlar[1:]
    assert len(veri) == 4

    db = env.db()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        foyler = {f.sistem_no: f for f in db.query(models.CaseFoy).all()}
    finally:
        db.close()
    assert set(foyler) == {"SSTMN-1", "SSTMN-2", "SSTMN-3"}

    for sira, (sistem_no, klasor) in enumerate([("SSTMN-1", "D-1"), ("SSTMN-2", "D-2"), ("SSTMN-3", "D-3")]):
        satir = veri[sira]
        assert satir[0] == sistem_no and satir[1] == klasor
        assert satir[2] == str(kartlar[klasor].id) and satir[2] == str(foyler[sistem_no].case_id)
        assert satir[3] == kartlar[klasor].tracking_no and satir[4] == klasor
        assert satir[5] == foyler[sistem_no].tku_no and satir[6] == ""     # case_party_id yok
        assert satir[7] == "ESLESTI" and satir[8] == ""
    assert veri[1][5] == "TKU-200"                                       # tku_no DB'den (föy)

    eslesmeyen = veri[3]
    assert eslesmeyen[0] == "SSTMN-9" and eslesmeyen[1] == "D-YOK"
    assert eslesmeyen[2] == "" and eslesmeyen[3] == "" and eslesmeyen[4] == "" and eslesmeyen[6] == ""
    assert eslesmeyen[7] == "ESLESMEDI"
    assert "Kart bulunamadı" in eslesmeyen[8] and "D-YOK" in eslesmeyen[8]


def test_eslesme_csv_ayni_sistem_no_iki_satir_ve_hata_sebebi(env):
    """Sebep SATIR numarasıyla eşlenir: aynı SistemNo iki kez → iki CSV satırı; ilk satır
    HATA ile düştü ama föy ikinci satırdan yazıldı → ESLESTI + sebep dolu; ikinci temiz."""
    satirlar = [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "31.02.2021"}),   # çözümlenemeyen tarih → satır HATA
        _satir("SSTMN-1", "D-1"),
        _satir("SSTMN-7", ""),                                        # Dosya No boş → satır HATA, föy yok
    ]
    tid = _uygulanmis_teslim(env, satirlar)          # anahtar kapalı: yükleme yok, CSV elle
    teslim = _teslim(env, tid)
    hedef = tc.eslesme_csv_uret(tid, Path(teslim.rapor_dizini) / "eslesme_test.csv")
    veri = _csv_satirlari(hedef)[1:]
    assert [v[0] for v in veri] == ["SSTMN-1", "SSTMN-1", "SSTMN-7"]
    assert veri[0][7] == "ESLESTI" and veri[0][2] != "" and "arsiv_tarihi çözümlenemedi" in veri[0][8]
    assert veri[1][7] == "ESLESTI" and veri[1][2] == veri[0][2] and veri[1][8] == ""
    assert veri[2][7] == "ESLESMEDI" and veri[2][2] == "" and "Dosya No boş" in veri[2][8]


def test_eslesme_csv_spool_dosyasi_yoksa_value_error(env):
    tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    Path(teslim.spool_path).unlink()
    with pytest.raises(ValueError, match="spool'da yok"):
        tc.eslesme_csv_uret(tid, Path(teslim.rapor_dizini) / "x.csv")


# ═══════════════════════════════════════════════════════════════════════════
# 3. ozet.txt — kuru koşu ve uygulama
# ═══════════════════════════════════════════════════════════════════════════

def test_ozet_txt_kuru_kosu_ve_uygulama_sonrasi_kapi_karariyla(env):
    """Kabul: `ozet.txt` kuru koşu ve uygulama sonrası spool'da; "yazıldı mı" satırı + kapı kararı."""
    _onceki_uygulandi(env)
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_dort_satir()), dosya_adi=TESLIM, kaynak="yukleme", db=db)
        assert tk.teslim_dogrula(tid, db=db) == "dogrulandi"
        assert tk.teslim_kuru_kos(tid, db=db) == "kuru_kosuldu"
        rapor = Path(db.get(models.AktarimTeslimi, tid).rapor_dizini)
        ozet = (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8")
        assert "yazıldı mı        : HAYIR (kuru koşu)" in ozet
        assert ozet.rstrip().splitlines()[-1] == "  kapı kararı       : henüz değerlendirilmedi"

        assert tk.kapi_degerlendir(tid, db=db) == "inceleme"            # eşleşmeyen 1/4 > 0.05
        ozet = (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8")
        son = ozet.rstrip().splitlines()[-1]
        assert son.startswith("  kapı kararı       : inceleme — eslesmeyen_orani")
        assert ozet.count("kapı kararı") == 1                            # satır tazelendi, ikilenmedi
        assert "HAYIR (kuru koşu)" in ozet

        assert tk.teslim_uygula(tid, uygulayan="admin@buro.test", db=db) == "uygulandi"
        ozet = (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8")
        assert "yazıldı mı        : EVET" in ozet
        assert ozet.rstrip().splitlines()[-1].startswith("  kapı kararı       : inceleme — eslesmeyen_orani")
        assert (rapor / "kuru-kosu-ozeti.txt").exists() and (rapor / "uygulama-ozeti.txt").exists()
    finally:
        db.close()


def test_ozet_txt_otomatik_kapi_gerekcesiz(env):
    _onceki_uygulandi(env)
    db = env.db()
    try:
        tid = tk.teslim_kaydet(
            icerik=_paket(_iki_satir("a"), ozet=f"{ONCEKI} · 2 satır"), dosya_adi=TESLIM, kaynak="yukleme", db=db,
        )
        assert tk.teslimi_isle(tid, otomatik_uygula=False, db=db) == "kuru_kosuldu"
        rapor = Path(db.get(models.AktarimTeslimi, tid).rapor_dizini)
        assert (rapor / tk.OZET_DOSYASI).read_text(encoding="utf-8").rstrip().splitlines()[-1] == \
            "  kapı kararı       : otomatik"
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. cevap_yukle — yükleme, kısmi başarısızlık, yeniden deneme
# ═══════════════════════════════════════════════════════════════════════════

def test_cevap_yukle_her_dosya_bir_kez_hedef_klasor_cevap_yuklendi_true(env, sahte_upload):
    """Kabul: sahte upload her dosya için bir kez, hedef klasör
    `03_VERI_TESLIM/cevap/HUKDOK_TESLIM_X`; `ozet.txt` → `ozet_<teslim>.txt`."""
    _anahtar(env, True)
    tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert teslim.durum == "uygulandi" and teslim.cevap_yuklendi is True

    rapor = Path(teslim.rapor_dizini)
    yerel = sorted(p.name for p in rapor.iterdir() if p.suffix in (".csv", ".txt"))
    assert "eslesme_HUKDOK_TESLIM_X.csv" in yerel and tk.OZET_DOSYASI in yerel
    assert any(ad.startswith("satir-raporu_") for ad in yerel)

    hedef_adlar = [c[1] for c in sahte_upload.cagrilar]
    assert len(hedef_adlar) == len(set(hedef_adlar)) == len(yerel)     # her dosya tam bir kez
    beklenen = {("ozet_HUKDOK_TESLIM_X.txt" if ad == tk.OZET_DOSYASI else ad) for ad in yerel}
    assert set(hedef_adlar) == beklenen
    assert {c[2] for c in sahte_upload.cagrilar} == {KLASOR}
    assert {c[3] for c in sahte_upload.cagrilar if c[1].endswith(".csv")} == {"text/csv"}
    assert {c[3] for c in sahte_upload.cagrilar if c[1].endswith(".txt")} == {"text/plain"}
    assert [c[0] for c in sahte_upload.cagrilar if c[1] == "ozet_HUKDOK_TESLIM_X.txt"] == [tk.OZET_DOSYASI]

    notlar = _deneme_notlari(teslim)
    assert len(notlar) == 1 and notlar[0].startswith("cevap yükleme denemesi #1: ") and "hatalar" not in notlar[0]
    assert f"{len(yerel)}/{len(yerel)} dosya → {KLASOR}" in notlar[0]
    assert teslim.durum_gecmisi[-1]["durum"] == "uygulandi"            # durum değişmedi


def test_cevap_yukle_bir_dosya_patlarsa_false_uygulandi_kalir_warning_ertesi_gece_true(env, sahte_upload, caplog):
    """Kabul: bir dosya patlarsa `cevap_yuklendi=False`, durum `uygulandi`, WARNING (ERROR yok);
    ertesi `gece_turu` yeniden dener ve başarıda True olur."""
    _anahtar(env, True)
    sahte_upload.patlayan = {"eslesme_HUKDOK_TESLIM_X.csv"}
    with caplog.at_level(logging.INFO):
        tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert teslim.durum == "uygulandi" and teslim.cevap_yuklendi is False and teslim.done_at is not None
    notlar = _deneme_notlari(teslim)
    assert len(notlar) == 1 and notlar[0].startswith("cevap yükleme denemesi #1: ")
    assert "hatalar: eslesme_HUKDOK_TESLIM_X.csv: RuntimeError: Graph 503" in notlar[0]
    uyarilar = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("cevap dosyası yüklenemedi" in m and "eslesme_HUKDOK_TESLIM_X.csv" in m for m in uyarilar)
    assert any("eksik yüklendi" in m for m in uyarilar)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    ilk_tur = len(sahte_upload.cagrilar)

    # Ertesi gece: engel kalktı → yeniden dener, hepsi gider
    sahte_upload.patlayan = set()
    ozet = tk.gece_turu()
    assert ozet["uygulanan"] is None and ozet["durumlar"] == {}
    teslim = _teslim(env, tid)
    assert teslim.cevap_yuklendi is True and teslim.durum == "uygulandi"
    notlar = _deneme_notlari(teslim)
    assert len(notlar) == 2 and notlar[1].startswith("cevap yükleme denemesi #2: ") and "hatalar" not in notlar[1]
    assert len(sahte_upload.cagrilar) == 2 * ilk_tur                     # ikinci turda tüm dosyalar yeniden

    # Üçüncü gece: yüklü teslime dokunulmaz
    tk.gece_turu()
    assert len(sahte_upload.cagrilar) == 2 * ilk_tur
    assert len(_deneme_notlari(_teslim(env, tid))) == 2


def test_cevap_yukle_zaten_yuklu_true_yeniden_yuklemez(env, sahte_upload):
    _anahtar(env, True)
    tid = _uygulanmis_teslim(env)
    sayi = len(sahte_upload.cagrilar)
    assert tc.cevap_yukle(tid) is True
    assert len(sahte_upload.cagrilar) == sayi


def test_cevap_yukle_yalniz_uygulandi_durumundan(env, sahte_upload):
    _onceki_uygulandi(env)
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_dort_satir()), dosya_adi=TESLIM, kaynak="yukleme", db=db)
        tk.teslimi_isle(tid, otomatik_uygula=False, db=db)
    finally:
        db.close()
    with pytest.raises(ValueError, match="cevap yükleme"):
        tc.cevap_yukle(tid)
    with pytest.raises(ValueError, match="Teslim yok"):
        tc.cevap_yukle(9999)
    assert sahte_upload.cagrilar == []


def test_cevap_yukle_anahtar_kapaliyken_atlanir_defter_degismez(env, sahte_upload, caplog):
    """Anahtar kapalı: elle uygulama çalışır, cevap SPOOL'da kalır, yükleme denenmez, not düşmez."""
    with caplog.at_level(logging.INFO):
        tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert teslim.durum == "uygulandi" and teslim.cevap_yuklendi is False
    assert sahte_upload.cagrilar == [] and _deneme_notlari(teslim) == []
    assert (Path(teslim.rapor_dizini) / tk.OZET_DOSYASI).is_file()
    assert any("veri_teslim_otomasyonu kapalı" in r.getMessage() for r in caplog.records if r.levelno == logging.INFO)
    assert _cevap_uyarilari(caplog) == []                              # aktarımın satır WARNING'i ayrı

    # Anahtar açılınca ertesi gece turu yükler
    _anahtar(env, True)
    tk.gece_turu()
    assert _teslim(env, tid).cevap_yuklendi is True and len(sahte_upload.cagrilar) > 0


def test_cevap_yukle_klasor_envi_yoksa_atlanir(env, sahte_upload, monkeypatch, caplog):
    """Yazma hedefi env'den AÇIKÇA gelir: tanımsızsa INFO + False, deneme sayılmaz."""
    _anahtar(env, True)
    monkeypatch.delenv("SHAREPOINT_FOLDER_TESLIM_NAME")
    with caplog.at_level(logging.INFO):
        tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert teslim.cevap_yuklendi is False and sahte_upload.cagrilar == [] and _deneme_notlari(teslim) == []
    assert any("SHAREPOINT_FOLDER_TESLIM_NAME tanımsız" in r.getMessage() for r in caplog.records)
    assert _cevap_uyarilari(caplog) == []                              # aktarımın satır WARNING'i ayrı
    assert tc.cevap_yukle(tid) is False

    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "03_VERI_TESLIM")
    assert tc.cevap_yukle(tid) is True
    assert {c[2] for c in sahte_upload.cagrilar} == {KLASOR}


def test_cevap_yukle_eslesme_uretilemezse_false_warning_deneme_sayilir(env, sahte_upload, caplog):
    tid = _uygulanmis_teslim(env)                    # anahtar kapalı: henüz deneme yok
    _anahtar(env, True)
    Path(_teslim(env, tid).spool_path).unlink()      # spool dosyası gitti → xlsx okunamaz
    with caplog.at_level(logging.INFO):
        assert tc.cevap_yukle(tid) is False
    teslim = _teslim(env, tid)
    assert teslim.durum == "uygulandi" and teslim.cevap_yuklendi is False
    notlar = _deneme_notlari(teslim)
    assert len(notlar) == 1 and "eşleşme dosyası üretilemedi" in notlar[0]
    assert sahte_upload.cagrilar == []
    assert any("eşleşme dosyası üretilemedi" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_cevap_yukle_rapor_dizini_yoksa_false_warning(env, sahte_upload, caplog):
    _anahtar(env, True)
    db = env.db()
    try:
        tid = _defter(db, dosya_adi=TESLIM, sha256="e" * 64, durum=tk.DURUM_UYGULANDI, rapor_dizini=None)
    finally:
        db.close()
    with caplog.at_level(logging.INFO):
        assert tc.cevap_yukle(tid) is False
    teslim = _teslim(env, tid)
    assert teslim.cevap_yuklendi is False and "rapor dizini yok" in _deneme_notlari(teslim)[0]
    assert any("rapor dizini yok" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_cevap_dene_istisnayi_warning_ile_yutar_durum_uygulandi(env, monkeypatch, caplog):
    """`teslim_uygula` başarı yolunda cevap katmanının beklenmedik istisnası uygulamayı bozmaz."""
    _anahtar(env, True)

    def _patla(teslim_id, *, db=None):
        raise RuntimeError("cevap katmanı çöktü")

    monkeypatch.setattr(tc, "cevap_yukle", _patla)
    with caplog.at_level(logging.INFO):
        tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert teslim.durum == "uygulandi" and teslim.cevap_yuklendi is False
    assert any("cevap yüklemesi yapılamadı" in r.getMessage() and "cevap katmanı çöktü" in r.getMessage()
               for r in caplog.records if r.levelno == logging.WARNING)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Gece turu bağlantısı
# ═══════════════════════════════════════════════════════════════════════════

def test_gece_turu_uygulanan_teslim_ayni_gece_ikinci_kez_denenmez(env, sahte_upload, monkeypatch):
    """Turda uygulanan teslim `teslim_uygula` içinde bir kez denendi; tur sonu yeniden
    denemez (retry ertesi geceye kalır). Ertesi gece 2. deneme."""
    _anahtar(env, True)
    _onceki_uygulandi(env)
    db = env.db()
    try:
        tid = tk.teslim_kaydet(icerik=_paket(_iki_satir("a"), ozet=f"{ONCEKI} · 2 satır"),
                               dosya_adi=TESLIM, kaynak="yukleme", db=db)
    finally:
        db.close()
    sahte_upload.patlayan = {"ozet_HUKDOK_TESLIM_X.txt"}

    ozet = tk.gece_turu()
    assert ozet["uygulanan"] == tid and ozet["durumlar"] == {tid: "uygulandi"}
    teslim = _teslim(env, tid)
    assert teslim.uygulayan == "gece-job" and teslim.cevap_yuklendi is False
    assert len(_deneme_notlari(teslim)) == 1
    ilk = len(sahte_upload.cagrilar)

    sahte_upload.patlayan = set()
    tk.gece_turu()
    teslim = _teslim(env, tid)
    assert teslim.cevap_yuklendi is True and len(_deneme_notlari(teslim)) == 2
    assert len(sahte_upload.cagrilar) == 2 * ilk


def test_gece_turu_bekleyen_cevaplar_id_sirasiyla_tek_hata_turu_durdurmaz(env, sahte_upload, monkeypatch):
    """Birden çok bekleyen: hepsi denenir, birinin istisnası diğerini engellemez; `ozet` şekli değişmez."""
    _anahtar(env, True)
    t1 = _uygulanmis_teslim(env, dosya_adi="HUKDOK_TESLIM_1.xlsx")   # anahtar açık ama...
    # ...ilk denemeyi başarısız kılmak için sonradan cevap_yuklendi'yi düşür
    db = env.db()
    try:
        for tid in (t1,):
            db.get(models.AktarimTeslimi, tid).cevap_yuklendi = False
        t2 = _defter(db, dosya_adi="HUKDOK_TESLIM_2.xlsx", sha256="f" * 64, durum=tk.DURUM_UYGULANDI,
                     rapor_dizini=None)
        db.commit()
    finally:
        db.close()
    sahte_upload.cagrilar.clear()

    orijinal = tc.cevap_yukle
    sira = []

    def _izle(teslim_id, *, db=None):
        sira.append(teslim_id)
        if teslim_id == t2:
            raise RuntimeError("beklenmedik")
        return orijinal(teslim_id, db=db)

    monkeypatch.setattr(tc, "cevap_yukle", _izle)
    ozet = tk.gece_turu()
    assert set(ozet) == {"etkin", "toparlanan", "tara", "durumlar", "uygulanan"}
    assert sira == [t1, t2]
    assert _teslim(env, t1).cevap_yuklendi is True and _teslim(env, t2).cevap_yuklendi is False
    assert {c[2] for c in sahte_upload.cagrilar} == {"03_VERI_TESLIM/cevap/HUKDOK_TESLIM_1"}


def test_cevap_bekleyen_idler_haric(env):
    db = env.db()
    try:
        a = _defter(db, dosya_adi="A.xlsx", sha256="1" * 64, durum=tk.DURUM_UYGULANDI)
        b = _defter(db, dosya_adi="B.xlsx", sha256="2" * 64, durum=tk.DURUM_UYGULANDI, cevap_yuklendi=True)
        c = _defter(db, dosya_adi="C.xlsx", sha256="3" * 64, durum=tk.DURUM_UYGULANDI)
        _defter(db, dosya_adi="D.xlsx", sha256="4" * 64, durum=tk.DURUM_INCELEME)
        assert tc.cevap_bekleyen_idler(db) == [a, c]
        assert tc.cevap_bekleyen_idler(db, haric=a) == [c]
        assert b not in tc.cevap_bekleyen_idler(db)
    finally:
        db.close()
