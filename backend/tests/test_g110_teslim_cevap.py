"""G110 — Cevap dosyaları: `services/teslim_cevap.py` (eşleşme CSV) ve `teslim_kutusu`'ndaki
bağlantı noktaları (`ozet.txt`, uygulama sonrası eşleşme dosyası). SharePoint `cevap/`
yüklemesi, gece turu yeniden denemesi ve G194 yükleme döngüsü 17.09.2026'da teslim klasörü
yoluyla birlikte kalktı (`test_teslim_klasoru_kaldirildi.py`).

Plan: docs/plan/veri-teslim-otomasyonu-plani-2026-09-03.md §2.4.

**TEST VERİSİ KURALI (A.2 dersi):** paketler openpyxl ile SENTETİK üretilir
(test_g107 üreticisi). `upload_file_to_sharepoint` sahtelenir — çağrılmadığı kanıtlanır.
"""
import csv
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
from services import teslim_cevap as tc
from services import teslim_kutusu as tk
from test_g107_teslim_kutusu import _defter, _iki_satir, _index_ops, _kart, _paket, _satir

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
ONCEKI = "HUKDOK_TESLIM_ONCEKI.xlsx"
TESLIM = "HUKDOK_TESLIM_X.xlsx"


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
    `teslim_kutusu.SessionLocal` bu fabrikaya."""
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


# ═══════════════════════════════════════════════════════════════════════════
# 1. Birim — CSV biçimi
# ═══════════════════════════════════════════════════════════════════════════

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
    tid = _uygulanmis_teslim(env, satirlar)
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
# 4. Uygulama yan ürünü — eşleşme dosyası kendiliğinden, SharePoint'e yükleme YOK
# ═══════════════════════════════════════════════════════════════════════════

def test_uygulama_eslesme_dosyasini_uretir_sharepointe_yuklemez(env, sahte_upload):
    """17.09: cevap klasörü yolu kalktı — uygulama eşleşme CSV'sini rapor dizinine yazar,
    `upload_file_to_sharepoint` HİÇ çağrılmaz, `cevap_yuklendi` yazılmaz."""
    tid = _uygulanmis_teslim(env)
    teslim = _teslim(env, tid)
    assert (Path(teslim.rapor_dizini) / "eslesme_HUKDOK_TESLIM_X.csv").is_file()
    assert sahte_upload.cagrilar == [] and teslim.cevap_yuklendi is False
