"""G109 — SharePoint teslim gözcüsü (`list_folder_children` + `sharepoint_tara`),
gece turu (`gece_turu`, 04:00 TR) ve boot telafisi (`boot_catch_up`).

Plan: docs/plan/veri-teslim-otomasyonu-plani-2026-09-03.md §2 + §2.3.

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; paketler
test_g107'nin sentetik üreticisiyle (`_paket`) openpyxl'den üretilir.

Katmanlar:

1. **Graph listeleme** — test_faz3'ün sahte session/token fixture'ları: iki sayfa
   `nextLink` birleşir, yalnız dosyalar, 404 → boş liste + WARNING, 401 → token
   yenilenip tekrar. Ağa çıkılmaz (conftest sözleşmesi).
2. **Gözcü / gece turu / boot** — süreç içi sqlite (G107/G108 reçetesi) + Graph
   çağrıları (`list_folder_children`, `download_file_from_sharepoint`) modül
   düzeyinde sahte: teslim_kutusu bunları `_spu.<ad>` ile çağrı anında çözer,
   monkeypatch `sharepoint_uploader_graph` üzerinde yapılır.
3. **Zamanlayıcı kaydı** — test_g085'in AST yardımcısıyla `veri_teslim` job'ı
   `is_leader` bloğunda, 04:00 TR, misfire 3600; boot thread'i aynı blokta.
"""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import sharepoint.sharepoint_uploader_graph as spu
from database import Base
from services import app_settings
from services import teslim_kutusu as tk
from test_faz3_graph_retry import _FakeResponse, _FakeSession, _ListHandler
from test_g085_sure_tarayici import _api_agaci, _kw, _lider_blogundaki_joblar
from test_g107_teslim_kutusu import _defter, _iki_satir, _index_ops, _kart, _paket, _uc_satir

KEY = app_settings.VERI_TESLIM_OTOMASYONU_KEY
KLASOR = "03_VERI_TESLIM/gelen"
ONCEKI = "HUKDOK_TESLIM_ONCEKI.xlsx"
ADMIN = "yonetici@hanyaloglu-acar.av.tr"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Graph listeleme — list_folder_children
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def envsiz(monkeypatch):
    monkeypatch.setattr(spu, "_load_env", lambda: None)


# test_faz3_graph_retry'nin fixture ikizleri (fixture fonksiyonu import edilemez —
# ruff F401; sahte sınıflar oradan gelir, düzen burada kurulur).
@pytest.fixture()
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(spu, "_get_shared_session", lambda: session)
    return session


@pytest.fixture()
def fake_ids(monkeypatch):
    monkeypatch.setattr(
        spu, "_get_site_and_drive_id",
        lambda token, config_type="default": ("site-1", "drive-1"),
    )


@pytest.fixture()
def token_calls(monkeypatch):
    calls = []

    def fake_token(config_type="default", force_refresh=False):
        calls.append(force_refresh)
        return f"tok{len(calls)}"

    monkeypatch.setattr(spu, "get_graph_token", fake_token)
    return calls


@pytest.fixture()
def uploader_log_records():
    handler = _ListHandler()
    target = logging.getLogger("SharePointUploader")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _dosya(ad, item_id=None, etag="1"):
    return {"id": item_id or f"item-{ad}", "name": ad, "eTag": f'"{etag}"', "size": 10,
            "file": {"mimeType": "application/octet-stream"}, "lastModifiedDateTime": "2026-09-03T01:00:00Z"}


def _klasor(ad):
    return {"id": f"folder-{ad}", "name": ad, "folder": {"childCount": 0}}


class TestListFolderChildren:
    def test_iki_sayfa_nextlink_birlesir_yalniz_dosyalar(self, envsiz, fake_session, fake_ids, token_calls):
        """Kabul: sahte Graph yanıtıyla iki sayfa `nextLink` birleşiyor; klasör öğeleri elenir."""
        devam = "https://graph.microsoft.com/v1.0/drives/drive-1/items/x/children?$skiptoken=abc"
        fake_session.get_script = [
            _FakeResponse(200, {"value": [_dosya("HUKDOK_TESLIM_A.xlsx"), _klasor("eski")],
                                "@odata.nextLink": devam}),
            _FakeResponse(200, {"value": [_dosya("notlar.txt")]}),
        ]

        dosyalar = spu.list_folder_children(KLASOR)

        assert [d["name"] for d in dosyalar] == ["HUKDOK_TESLIM_A.xlsx", "notlar.txt"]
        assert len(fake_session.gets) == 2
        ilk, ikinci = fake_session.gets
        assert ilk["url"] == f"{spu.GRAPH}/drives/drive-1/root:/03_VERI_TESLIM/gelen:/children"
        assert ilk["params"] == {"$select": "id,name,size,eTag,file,lastModifiedDateTime", "$top": 200}
        assert ilk["headers"]["Authorization"] == "Bearer tok1"
        assert ikinci["url"] == devam and ikinci["params"] is None   # nextLink parametreleri kendi taşır
        assert token_calls == [False]

    def test_404_bos_liste_warning_error_yok(
        self, envsiz, fake_session, fake_ids, token_calls, uploader_log_records
    ):
        """Kabul: klasör yoksa boş liste + WARNING (gece job'ı ERROR basmasın)."""
        fake_session.get_script = [_FakeResponse(404, text="itemNotFound")]

        assert spu.list_folder_children(KLASOR) == []

        uyarilar = [r for r in uploader_log_records if r.levelno == logging.WARNING]
        assert uyarilar and KLASOR in uyarilar[0].getMessage()
        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]

    def test_401de_token_zorla_yenilenip_tekrar_denenir(self, envsiz, fake_session, fake_ids, token_calls):
        """Kabul: 401 → token yenilenip tekrar (mevcut `_with_fresh_token_on_401` deseni)."""
        fake_session.get_script = [
            _FakeResponse(401, text="token süresi doldu"),
            _FakeResponse(200, {"value": [_dosya("HUKDOK_TESLIM_A.xlsx")]}),
        ]

        dosyalar = spu.list_folder_children(KLASOR)

        assert [d["name"] for d in dosyalar] == ["HUKDOK_TESLIM_A.xlsx"]
        assert token_calls == [False, True]
        assert fake_session.gets[1]["headers"]["Authorization"] == "Bearer tok2"

    def test_diger_http_hatalari_yukselir_error_uretmez(
        self, envsiz, fake_session, fake_ids, token_calls, uploader_log_records
    ):
        fake_session.get_script = [_FakeResponse(403, text="yetki yok")]
        with pytest.raises(requests.HTTPError):
            spu.list_folder_children(KLASOR)
        assert not [r for r in uploader_log_records if r.levelno >= logging.ERROR]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Düzen — sqlite + sahte SharePoint
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """sqlite (FK + SAVEPOINT + defter/föy/bildirim index'leri) + spool + iki kart;
    `teslim_kutusu.SessionLocal` ve `app_settings.SessionLocal` bu fabrikaya bağlanır
    (gece_turu / boot_catch_up `db` almaz — kendi oturumunu buradan açar)."""
    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    monkeypatch.delenv("SHAREPOINT_FOLDER_TESLIM_NAME", raising=False)
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

    db = maker()
    try:
        for i in (1, 2):
            _kart(db, f"HA.G109.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()

    yield SimpleNamespace(db=maker, spool=tmp_path / "teslim_spool")
    engine.dispose()


@pytest.fixture()
def sahte_sp(monkeypatch):
    """`sharepoint_uploader_graph.list_folder_children` / `download_file_from_sharepoint`
    yerine bellek içi klasör; çağrılar kaydedilir."""
    sp = SimpleNamespace(dosyalar=[], icerikler={}, listelenen=[], indirilen=[],
                         liste_hatasi=None, indirme_hatalari=set())

    def _list(folder_name):
        sp.listelenen.append(folder_name)
        if sp.liste_hatasi is not None:
            raise sp.liste_hatasi
        return list(sp.dosyalar)

    def _download(folder_name, filename):
        sp.indirilen.append(filename)
        if filename in sp.indirme_hatalari:
            raise requests.ConnectionError(f"ağ koptu: {filename}")
        return sp.icerikler[filename], "application/octet-stream"

    def ekle(ad, icerik, *, item_id=None, etag="1"):
        sp.dosyalar.append(_dosya(ad, item_id=item_id, etag=etag))
        sp.icerikler[ad] = icerik

    monkeypatch.setattr(spu, "list_folder_children", _list)
    monkeypatch.setattr(spu, "download_file_from_sharepoint", _download)
    sp.ekle = ekle
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


def _teslimler(env):
    db = env.db()
    try:
        return db.query(models.AktarimTeslimi).order_by(models.AktarimTeslimi.id).all()
    finally:
        db.close()


def _defter_satiri(env, **alanlar):
    db = env.db()
    try:
        return _defter(db, **alanlar)
    finally:
        db.close()


def _foy_sayisi(env):
    db = env.db()
    try:
        return db.query(models.CaseFoy).count()
    finally:
        db.close()


def _bildirimler(env):
    db = env.db()
    try:
        return db.query(models.Notification).filter(models.Notification.type == tk.BILDIRIM_TURU).all()
    finally:
        db.close()


def _onceki_uygulandi(env):
    """Zincir/ilk-teslim kapısını açan `uygulandi` satır."""
    return _defter_satiri(env, dosya_adi=ONCEKI, sha256="b" * 64, durum=tk.DURUM_UYGULANDI)


def _esik_ici_paket(damga="a", onceki=ONCEKI):
    """Eşik içi + zincirli paket (önceki = defterde uygulandı olan)."""
    return _paket(_iki_satir(damga), ozet=f"{onceki} · 3 satır × 6 sütun")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Gözcü — sharepoint_tara
# ═══════════════════════════════════════════════════════════════════════════

def test_gelen_klasoru_env_ve_varsayilan(monkeypatch):
    monkeypatch.delenv("SHAREPOINT_FOLDER_TESLIM_NAME", raising=False)
    assert tk.teslim_gelen_klasoru() == "03_VERI_TESLIM/gelen"
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "/99_TEST/")
    assert tk.teslim_gelen_klasoru() == "99_TEST/gelen"


def test_item_anahtari_id_ve_etag_tirnaksiz():
    assert tk.sharepoint_item_anahtari({"id": "item-1", "eTag": '"{ABC},7"'}) == "item-1@{ABC},7"
    assert tk.sharepoint_item_anahtari({"id": "item-1"}) == "item-1@"


@pytest.mark.parametrize("ad,uyar", [
    ("HUKDOK_TESLIM_PAKETI_2026-09-10.xlsx", True),
    ("hukdok_teslim_a.XLSX", True),
    ("HUKDOK_TESLIM_.xlsx", True),
    ("notlar.txt", False),
    ("HUKDOK_TESLIM_A.xlsx.bak", False),
    ("ESKI_HUKDOK_TESLIM_A.xlsx", False),
])
def test_ad_kalibi_harf_duyarsiz(ad, uyar):
    assert bool(tk.TESLIM_AD_KALIBI.match(ad)) is uyar


def test_tara_anahtar_kapaliyken_listeleme_hic_cagrilmaz(env, sahte_sp):
    """Kabul: anahtar kapalıyken listeleme hiç çağrılmıyor."""
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _paket(_uc_satir()))
    assert tk.sharepoint_tara() == {"yeni": 0, "yinelenen": 0, "atlanan": 0}
    assert sahte_sp.listelenen == [] and sahte_sp.indirilen == []
    assert _teslimler(env) == []


def test_tara_uc_dosyali_klasor_yeni_atlanan_ucuz_eleme(env, sahte_sp):
    """Kabul: `HUKDOK_TESLIM_A.xlsx` + `notlar.txt` + daha önce alınmış `HUKDOK_TESLIM_B.xlsx`
    (aynı eTag) → yeni=1, atlanan=1; indirme YALNIZ A için."""
    _anahtar(env, True)
    b_anahtar = tk.sharepoint_item_anahtari(_dosya("HUKDOK_TESLIM_B.xlsx", item_id="item-b", etag="{B},2"))
    _defter_satiri(env, dosya_adi="HUKDOK_TESLIM_B.xlsx", sha256="c" * 64, kaynak="sharepoint",
                   sharepoint_item_id=b_anahtar, durum=tk.DURUM_UYGULANDI)
    a_icerik = _paket(_uc_satir())
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", a_icerik, item_id="item-a", etag="{A},1")
    sahte_sp.ekle("notlar.txt", b"not")
    sahte_sp.ekle("HUKDOK_TESLIM_B.xlsx", b"eski icerik", item_id="item-b", etag="{B},2")

    sayac = tk.sharepoint_tara()

    assert sayac == {"yeni": 1, "yinelenen": 1, "atlanan": 1}
    assert sahte_sp.listelenen == [KLASOR]
    assert sahte_sp.indirilen == ["HUKDOK_TESLIM_A.xlsx"]
    yeni = [t for t in _teslimler(env) if t.dosya_adi == "HUKDOK_TESLIM_A.xlsx"]
    assert len(yeni) == 1
    assert yeni[0].durum == "alindi" and yeni[0].kaynak == "sharepoint"
    assert yeni[0].sharepoint_item_id == "item-a@{A},1"
    assert Path(yeni[0].spool_path).read_bytes() == a_icerik
    # İkinci tarama: A artık defterde (aynı eTag) → indirme yok, yeni 0
    sahte_sp.indirilen.clear()
    assert tk.sharepoint_tara() == {"yeni": 0, "yinelenen": 2, "atlanan": 1}
    assert sahte_sp.indirilen == []


def test_tara_etag_degisti_ayni_icerik_indirilir_yinelenen(env, sahte_sp):
    """eTag değişti (dosya yerinde yeniden kaydedildi) → indirilir; sha256 aynıysa
    `yinelenen` satırı açılır, ilk satıra dokunulmaz."""
    _anahtar(env, True)
    icerik = _paket(_uc_satir())
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", icerik, item_id="item-a", etag="{A},1")
    assert tk.sharepoint_tara()["yeni"] == 1
    sahte_sp.dosyalar[0]["eTag"] = '"{A},2"'

    sayac = tk.sharepoint_tara()

    assert sayac == {"yeni": 0, "yinelenen": 1, "atlanan": 0}
    assert sahte_sp.indirilen == ["HUKDOK_TESLIM_A.xlsx"] * 2
    satirlar = _teslimler(env)
    assert [t.durum for t in satirlar] == ["alindi", "yinelenen"]
    assert [t.sharepoint_item_id for t in satirlar] == ["item-a@{A},1", "item-a@{A},2"]


def test_tara_klasor_adi_envden(env, sahte_sp, monkeypatch):
    _anahtar(env, True)
    monkeypatch.setenv("SHAREPOINT_FOLDER_TESLIM_NAME", "77_TESLIM")
    tk.sharepoint_tara()
    assert sahte_sp.listelenen == ["77_TESLIM/gelen"]


def test_tara_tek_dosya_hatasi_warning_tur_devam(env, sahte_sp, caplog):
    """Kabul (log sözleşmesi): dosya başına WARNING, tur devam eder, ERROR yok."""
    _anahtar(env, True)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _paket(_uc_satir("a")))
    sahte_sp.ekle("HUKDOK_TESLIM_B.xlsx", _paket(_uc_satir("b")))
    sahte_sp.indirme_hatalari.add("HUKDOK_TESLIM_A.xlsx")

    with caplog.at_level(logging.INFO):
        sayac = tk.sharepoint_tara()

    assert sayac == {"yeni": 1, "yinelenen": 0, "atlanan": 0}
    assert [t.dosya_adi for t in _teslimler(env)] == ["HUKDOK_TESLIM_B.xlsx"]
    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(uyarilar) == 1 and "HUKDOK_TESLIM_A.xlsx" in uyarilar[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_tara_listeleme_hatasi_yukselir(env, sahte_sp):
    """Listeleme hatası tur düzeyinde ele alınır (gece: TEK ERROR, boot: WARNING) — burada yükselir."""
    _anahtar(env, True)
    sahte_sp.liste_hatasi = requests.ConnectionError("Graph erişilemez")
    with pytest.raises(requests.ConnectionError):
        tk.sharepoint_tara()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Gece turu
# ═══════════════════════════════════════════════════════════════════════════

def test_gece_turu_esik_ici_teslim_uygulandi_gece_job(env, sahte_sp):
    """Kabul: defterde önceden `uygulandi` teslim + eşik içi yeni teslim →
    `uygulandi`, `uygulayan="gece-job"`, föy satırları yazıldı."""
    _anahtar(env, True)
    _onceki_uygulandi(env)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _esik_ici_paket("a"))

    ozet = tk.gece_turu()

    assert ozet["etkin"] is True and ozet["toparlanan"] == 0
    assert ozet["tara"] == {"yeni": 1, "yinelenen": 0, "atlanan": 0}
    (teslim,) = [t for t in _teslimler(env) if t.dosya_adi == "HUKDOK_TESLIM_A.xlsx"]
    assert teslim.durum == "uygulandi" and teslim.uygulayan == tk.GECE_UYGULAYAN == "gece-job"
    assert teslim.zincir_tamam is True and teslim.kapi_karari == "otomatik"
    assert ozet["durumlar"] == {teslim.id: "uygulandi"} and ozet["uygulanan"] == teslim.id
    assert _foy_sayisi(env) == 2


def test_gece_turu_iki_yeni_teslim_biri_uygulandi_digeri_inceleme(env, sahte_sp):
    """Kabul: iki yeni teslim → biri `uygulandi`, diğeri `inceleme_bekliyor`
    (tek-uygulama kuralı: ikincisi zincirli ve eşik içi olsa da insana bırakılır)."""
    _anahtar(env, True)
    _onceki_uygulandi(env)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _esik_ici_paket("a"))
    sahte_sp.ekle("HUKDOK_TESLIM_B.xlsx", _esik_ici_paket("b", onceki="HUKDOK_TESLIM_A.xlsx"))

    ozet = tk.gece_turu()

    a, b = [t for t in _teslimler(env) if t.dosya_adi != ONCEKI]
    assert (a.dosya_adi, a.durum, a.uygulayan) == ("HUKDOK_TESLIM_A.xlsx", "uygulandi", "gece-job")
    assert (b.dosya_adi, b.durum, b.uygulayan) == ("HUKDOK_TESLIM_B.xlsx", "inceleme_bekliyor", None)
    assert b.zincir_tamam is True                                   # A uygulandı → zincir tamam
    assert b.kapi_karari == "inceleme" and b.kapi_gerekcesi.startswith("tek_uygulama")
    assert f"#{a.id}" in b.kapi_gerekcesi
    assert [g["durum"] for g in b.durum_gecmisi] == ["alindi", "dogrulandi", "kuru_kosuldu", "inceleme_bekliyor"]
    assert ozet["durumlar"] == {a.id: "uygulandi", b.id: "inceleme_bekliyor"}
    assert ozet["uygulanan"] == a.id
    assert _foy_sayisi(env) == 2                                    # yalnız A yazdı
    bildirim = [n for n in _bildirimler(env) if n.dedupe_key.startswith(f"teslim:{b.id}:")]
    assert len(bildirim) == 1 and bildirim[0].severity == "warning"
    assert "tek_uygulama" in bildirim[0].body


def test_gece_turu_anahtar_kapali_hicbir_durum_degismez(env, sahte_sp):
    """Kabul: anahtar kapalı → hiçbir durum değişmiyor (toparlama dahil), listeleme yok."""
    _onceki_uygulandi(env)
    kesik = _defter_satiri(env, sha256="c" * 64, durum=tk.DURUM_UYGULANIYOR)
    db = env.db()
    try:
        bekleyen = tk.teslim_kaydet(icerik=_esik_ici_paket("a"), dosya_adi="HUKDOK_TESLIM_A.xlsx",
                                    kaynak="yukleme", db=db)
    finally:
        db.close()
    sahte_sp.ekle("HUKDOK_TESLIM_B.xlsx", _esik_ici_paket("b"))

    ozet = tk.gece_turu()

    assert ozet == {"etkin": False, "toparlanan": 0, "tara": None, "durumlar": {}, "uygulanan": None}
    assert sahte_sp.listelenen == []
    assert _teslim(env, kesik).durum == "uygulaniyor"
    assert _teslim(env, bekleyen).durum == "alindi"
    assert _foy_sayisi(env) == 0 and len(_teslimler(env)) == 3


def test_gece_turu_tarama_hatasi_tek_error_bekleyenler_yine_islenir(env, sahte_sp, caplog):
    """Kabul (log sözleşmesi): tur başına en fazla TEK ERROR; tarama düşse de dün
    indirilen bekleyen teslim işlenir."""
    _anahtar(env, True)
    _onceki_uygulandi(env)
    db = env.db()
    try:
        bekleyen = tk.teslim_kaydet(icerik=_esik_ici_paket("a"), dosya_adi="HUKDOK_TESLIM_A.xlsx",
                                    kaynak="sharepoint", sharepoint_item_id="item-a@1", db=db)
    finally:
        db.close()
    sahte_sp.liste_hatasi = requests.ConnectionError("Graph erişilemez")

    with caplog.at_level(logging.INFO):
        ozet = tk.gece_turu()

    assert ozet["tara"] is None
    assert _teslim(env, bekleyen).durum == "uygulandi"
    hatalar = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(hatalar) == 1 and "Graph erişilemez" in hatalar[0].getMessage()


def test_gece_turu_inceleme_bekleyen_ve_kesik_satirlar(env, sahte_sp):
    """`inceleme_bekliyor` satırına dokunulmaz (insan bekliyor); `uygulaniyor` toparlanır."""
    _anahtar(env, True)
    inceleme = _defter_satiri(env, sha256="d" * 64, durum=tk.DURUM_INCELEME, kapi_karari="inceleme",
                              kapi_gerekcesi="ilk_teslim (defterde uygulanmış teslim yok)",
                              durum_gecmisi=[{"durum": "inceleme_bekliyor", "at": "x", "not": None}])
    kesik = _defter_satiri(env, sha256="c" * 64, durum=tk.DURUM_UYGULANIYOR)

    ozet = tk.gece_turu()

    assert ozet["toparlanan"] == 1 and ozet["durumlar"] == {}
    assert _teslim(env, kesik).durum == "inceleme_bekliyor"
    beklemede = _teslim(env, inceleme)
    assert beklemede.durum == "inceleme_bekliyor" and len(beklemede.durum_gecmisi) == 1


def test_gece_turu_ilk_teslim_inceleme_uygulama_yok(env, sahte_sp):
    """Defter boşken gelen ilk teslim kapıda `inceleme_bekliyor` — gece de uygulamaz."""
    _anahtar(env, True)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _paket(_uc_satir()))

    ozet = tk.gece_turu()

    (teslim,) = _teslimler(env)
    assert teslim.durum == "inceleme_bekliyor" and "ilk_teslim" in teslim.kapi_gerekcesi
    assert ozet["uygulanan"] is None and _foy_sayisi(env) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Boot telafisi
# ═══════════════════════════════════════════════════════════════════════════

def test_boot_bekleyen_kuru_kosuldu_ya_gelir_asla_uygulandi_olmaz(env, sahte_sp):
    """Kabul: bekleyen teslim `kuru_kosuldu`ya geliyor (kapı otomatik dese bile),
    ASLA `uygulandi`ya geçmiyor; `uygulaniyor` toparlanır."""
    _anahtar(env, True)
    _onceki_uygulandi(env)
    kesik = _defter_satiri(env, sha256="c" * 64, durum=tk.DURUM_UYGULANIYOR)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _esik_ici_paket("a"))

    ozet = tk.boot_catch_up()

    assert ozet["etkin"] is True and ozet["toparlanan"] == 1
    assert ozet["tara"] == {"yeni": 1, "yinelenen": 0, "atlanan": 0}
    (teslim,) = [t for t in _teslimler(env) if t.dosya_adi == "HUKDOK_TESLIM_A.xlsx"]
    assert teslim.durum == "kuru_kosuldu" and teslim.kapi_karari == "otomatik"
    assert teslim.uygulayan is None
    assert ozet["durumlar"] == {teslim.id: "kuru_kosuldu"}
    assert _teslim(env, kesik).durum == "inceleme_bekliyor"
    assert _foy_sayisi(env) == 0
    assert "uygulandi" not in [t.durum for t in _teslimler(env) if t.dosya_adi != ONCEKI]


def test_boot_ilk_teslim_inceleme_bekliyor(env, sahte_sp):
    """Kabul: bekleyen teslim `inceleme_bekliyor`a geliyor (defter boş → ilk_teslim)."""
    _anahtar(env, True)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _paket(_uc_satir()))

    ozet = tk.boot_catch_up()

    (teslim,) = _teslimler(env)
    assert teslim.durum == "inceleme_bekliyor"
    assert ozet["durumlar"] == {teslim.id: "inceleme_bekliyor"}


def test_boot_kuru_kosulmus_satiri_yeniden_kosturmaz(env, sahte_sp):
    """`kuru_kosuldu` gece uygulanmayı bekliyor; her restart'ta yeniden kuru koşturulmaz."""
    _anahtar(env, True)
    hazir = _defter_satiri(env, sha256="d" * 64, durum=tk.DURUM_KURU_KOSULDU,
                           durum_gecmisi=[{"durum": "kuru_kosuldu", "at": "x", "not": None}])

    ozet = tk.boot_catch_up()

    assert ozet["durumlar"] == {}
    teslim = _teslim(env, hazir)
    assert teslim.durum == "kuru_kosuldu" and len(teslim.durum_gecmisi) == 1


def test_boot_istisna_tek_warning_ile_yutulur(env, sahte_sp, caplog):
    """Kabul: istisna WARNING ile yutuluyor (thread'den taşmaz), ERROR yok, None döner."""
    _anahtar(env, True)
    sahte_sp.liste_hatasi = RuntimeError("Graph token alınamadı")

    with caplog.at_level(logging.INFO):
        assert tk.boot_catch_up() is None

    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(uyarilar) == 1 and "Graph token alınamadı" in uyarilar[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_boot_anahtar_kapali_yalniz_toparlar(env, sahte_sp):
    """Anahtar kapalıyken de kesilmiş elle uygulama toparlanır; listeleme yok."""
    kesik = _defter_satiri(env, sha256="c" * 64, durum=tk.DURUM_UYGULANIYOR)
    sahte_sp.ekle("HUKDOK_TESLIM_A.xlsx", _paket(_uc_satir()))

    ozet = tk.boot_catch_up()

    assert ozet == {"etkin": False, "toparlanan": 1, "tara": None, "durumlar": {}}
    assert sahte_sp.listelenen == []
    assert _teslim(env, kesik).durum == "inceleme_bekliyor"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Zamanlayıcı kaydı (AST — test_g085 deseni)
# ═══════════════════════════════════════════════════════════════════════════

def test_veri_teslim_job_u_lider_blogunda_04_00_tr():
    """Kabul: `veri_teslim` job'ı `is_leader` bloğunda, 04:00 TR, misfire 3600, gece_turu."""
    job = _lider_blogundaki_joblar()["veri_teslim"]

    assert _kw(job, "replace_existing").value is True
    assert _kw(job, "misfire_grace_time").value == 3600
    trigger = job.args[1]
    assert isinstance(trigger, ast.Call) and trigger.func.id == "CronTrigger"
    assert _kw(trigger, "hour").value == 4 and _kw(trigger, "minute").value == 0
    tz = _kw(trigger, "timezone")
    assert isinstance(tz, ast.Call) and tz.args[0].value == "Europe/Istanbul"
    assert isinstance(job.args[0], ast.Name) and job.args[0].id == "gece_turu"


def test_mevcut_joblar_ve_saat_sirasi_korundu():
    joblar = _lider_blogundaki_joblar()
    saatler = {jid: (_kw(joblar[jid].args[1], "hour").value, _kw(joblar[jid].args[1], "minute").value)
               for jid in ("daily_activity_report", "conversion_retry", "veri_teslim", "deadline_scan")}
    assert saatler == {"daily_activity_report": (0, 0), "conversion_retry": (2, 30),
                       "veri_teslim": (4, 0), "deadline_scan": (6, 0)}


def test_boot_telafi_threadi_lider_blogunda():
    """`boot_catch_up` daemon thread'i `is_leader` bloğunun içinde başlatılır."""
    hedefler = []
    for node in ast.walk(_api_agaci()):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "is_leader"):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "Thread"):
                hedef = _kw(inner, "target")
                if isinstance(hedef, ast.Name):
                    hedefler.append(hedef.id)
                assert _kw(inner, "daemon").value is True
    assert "teslim_boot_catch_up" in hedefler and "boot_catch_up_scan" in hedefler
