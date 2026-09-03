"""G108 — Teslim admin uçları (`/api/admin/aktarim/*`) + admin bildirimi
(`teslim_kutusu.bildir`) + `veri_teslim_otomasyonu` anahtarı.

Sözleşme: gorevler/gorev/G108.md "SÖZLEŞME" tablosu (G111 paneli buna göre yazıldı).

**TEST VERİSİ KURALI (A.2 dersi):** gerçek teslim paketi REPOYA GİRMEZ; paketler
test_g107'nin sentetik üreticisiyle (`_paket`) openpyxl'den üretilir.

Düzen: süreç içi sqlite (StaticPool, G064/G107 reçetesi: FK + çalışan SAVEPOINT +
`case_foys` / `aktarim_teslimleri` / `notifications` migrasyon index'leri).
`routes.admin.SessionLocal` sqlite fabrikasına bağlanır; uçlar servis
fonksiyonlarına `db=` ile aynı oturumu verdiği için başka yama gerekmez.
Kimlik `get_current_user` override'ı + `ADMIN_EMAILS` env'i (gerçek
`require_admin` koşar — 403 testi sahte değildir).
"""
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from services import app_settings
from services import notifications as bildirimler
from services import teslim_kutusu as tk
from test_g107_teslim_kutusu import _iki_satir, _index_ops, _kart, _paket, _uc_satir

ADMIN_1 = "yonetici@hanyaloglu-acar.av.tr"
ADMIN_2 = "Ikinci.Yonetici@lexisbio.com"      # büyük harf: normalize edildiği görülsün
USER = "avukat@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"

BASE = "/api/admin/aktarim"
SETTINGS_URL = "/api/admin/settings"
KEY = "veri_teslim_otomasyonu"


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """sqlite + spool + iki kart + admin router TestClient fabrikası."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import admin as route_mod

    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    monkeypatch.setenv("ADMIN_EMAILS", f"{ADMIN_1}, {ADMIN_2}")
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
    monkeypatch.setattr(route_mod, "SessionLocal", maker)

    db = maker()
    try:
        for i in (1, 2):
            _kart(db, f"HA.G108.{i}", f"D-{i}")
        db.commit()
    finally:
        db.close()

    def _client(email=ADMIN_1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": T1}
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(db=maker, client=_client, route=route_mod, spool=tmp_path / "teslim_spool")
    engine.dispose()


def _yukle(client, icerik: bytes, ad: str = "HUKDOK_TESLIM_PAKETI_2026-09-10.xlsx"):
    return client.post(f"{BASE}/teslimler", files={"file": (ad, icerik, "application/octet-stream")})


def _teslim(env, tid):
    db = env.db()
    try:
        return db.get(models.AktarimTeslimi, tid)
    finally:
        db.close()


def _defter(env, **alanlar):
    """Doğrudan defter satırı (durum kontrolü testleri için)."""
    temel = dict(dosya_adi="HUKDOK_TESLIM_T.xlsx", sha256="0" * 64, kaynak="yukleme",
                 durum=tk.DURUM_UYGULANDI, durum_gecmisi=[])
    temel.update(alanlar)
    db = env.db()
    try:
        teslim = models.AktarimTeslimi(**temel)
        db.add(teslim)
        db.commit()
        return teslim.id
    finally:
        db.close()


def _bildirimler(env, tur=tk.BILDIRIM_TURU):
    db = env.db()
    try:
        return (
            db.query(models.Notification)
            .filter(models.Notification.type == tur)
            .order_by(models.Notification.id)
            .all()
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kapı: yedi uç require_admin ile kapılı
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("metot,yol,kwargs", [
    ("get", f"{BASE}/teslimler?limit=50", {}),
    ("get", f"{BASE}/teslimler/1", {}),
    ("post", f"{BASE}/teslimler", {"files": {"file": ("a.xlsx", b"x", "application/octet-stream")}}),
    ("post", f"{BASE}/teslimler/1/kuru-kos", {}),
    ("post", f"{BASE}/teslimler/1/uygula", {"json": {"onay": True}}),
    ("get", f"{BASE}/teslimler/1/raporlar", {}),
    ("get", f"{BASE}/teslimler/1/raporlar/kuru-kosu-ozeti.txt", {}),
    ("post", f"{BASE}/tara", {}),
])
def test_admin_olmayan_403(env, metot, yol, kwargs):
    """Kabul: yedi uç (rapor indirme dahil sekiz yol) admin olmayana 403."""
    client = env.client(email=USER)
    r = getattr(client, metot)(yol, **kwargs)
    assert r.status_code == 403
    assert _bildirimler(env) == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Yükleme
# ═══════════════════════════════════════════════════════════════════════════

def test_yukleme_ilk_teslim_inceleme_bekliyor(env):
    """Kabul: sentetik mini xlsx → 201; ilk teslim kapıda `inceleme_bekliyor`
    (`ilk_teslim`); spool + rapor dizini dolu; föy YAZILMADI (otomatik uygulama yok)."""
    client = env.client()
    r = _yukle(client, _paket(_uc_satir()))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["durum"] == "inceleme_bekliyor"
    teslim = _teslim(env, data["id"])
    assert teslim.kaynak == "yukleme" and teslim.dosya_adi == "HUKDOK_TESLIM_PAKETI_2026-09-10.xlsx"
    assert (teslim.okunan, teslim.islenen, teslim.atlanan) == (3, 2, 1)
    assert "ilk_teslim" in teslim.kapi_gerekcesi and teslim.uygulayan is None
    assert Path(teslim.spool_path).is_file() and Path(teslim.rapor_dizini).is_dir()
    db = env.db()
    try:
        assert db.query(models.CaseFoy).count() == 0
    finally:
        db.close()


def test_yukleme_zincirli_teslim_kuru_kosuldu_kalir(env):
    """Kapı `otomatik` dese bile yükleme yolu uygulamaz → `kuru_kosuldu`."""
    _defter(env, dosya_adi="HUKDOK_TESLIM_ONCEKI.xlsx", sha256="b" * 64, durum="uygulandi")
    r = _yukle(env.client(), _paket(_iki_satir(), ozet="HUKDOK_TESLIM_ONCEKI.xlsx · 2 satır"))
    assert r.status_code == 201
    assert r.json()["durum"] == "kuru_kosuldu"
    teslim = _teslim(env, r.json()["id"])
    assert teslim.kapi_karari == "otomatik" and teslim.zincir_tamam is True


def test_yukleme_xlsx_disi_400(env):
    client = env.client()
    r = client.post(f"{BASE}/teslimler", files={"file": ("notlar.txt", b"merhaba", "text/plain")})
    assert r.status_code == 400
    r = client.post(f"{BASE}/teslimler", files={"file": ("paket.xls", b"x", "application/octet-stream")})
    assert r.status_code == 400
    r = client.post(f"{BASE}/teslimler", files={"file": ("bos.xlsx", b"", "application/octet-stream")})
    assert r.status_code == 400
    db = env.db()
    try:
        assert db.query(models.AktarimTeslimi).count() == 0
    finally:
        db.close()


def test_yukleme_ayni_dosya_ikinci_kez_yinelenen(env):
    """Kabul: aynı dosya ikinci kez → 201 + `durum="yinelenen"`; ilk satıra dokunulmaz."""
    client = env.client()
    icerik = _paket(_uc_satir())
    ilk = _yukle(client, icerik).json()
    ikinci = _yukle(client, icerik, ad="HUKDOK_TESLIM_PAKETI_2026-09-10 (1).xlsx")
    assert ikinci.status_code == 201
    assert ikinci.json()["durum"] == "yinelenen" and ikinci.json()["id"] != ilk["id"]
    assert _teslim(env, ilk["id"]).durum == "inceleme_bekliyor"
    assert _teslim(env, ikinci.json()["id"]).spool_path is None


def test_yukleme_bozuk_dosya_reddedildi_201(env):
    """Yapı hatası HTTP hatası değildir: defter `reddedildi` der, uç 201 + durum döner."""
    r = _yukle(env.client(), b"bu bir xlsx degil")
    assert r.status_code == 201
    assert r.json()["durum"] == "reddedildi"
    assert "açılamadı" in _teslim(env, r.json()["id"]).hata_mesaji


def test_yukleme_boyut_siniri_413(env, monkeypatch):
    monkeypatch.setattr(env.route, "TESLIM_YUKLEME_SINIRI", 64)
    r = _yukle(env.client(), b"x" * 65)
    assert r.status_code == 413
    r = _yukle(env.client(), b"x" * 64)
    assert r.status_code == 201                                   # sınırın kendisi kabul


# ═══════════════════════════════════════════════════════════════════════════
# 3. Liste + tek teslim
# ═══════════════════════════════════════════════════════════════════════════

def test_liste_en_yeni_once_esikler_etkin(env):
    client = env.client()
    a = _yukle(client, _paket(_uc_satir("a"))).json()["id"]
    b = _yukle(client, _paket(_uc_satir("b"))).json()["id"]

    r = client.get(f"{BASE}/teslimler?limit=50")
    assert r.status_code == 200
    data = r.json()
    assert [t["id"] for t in data["teslimler"]] == [b, a]
    assert data["esikler"] == {"hata_orani": 0.02, "eslesmeyen_orani": 0.05, "alan_degisikligi": 10000}
    assert data["etkin"] is False                                 # anahtar varsayılan kapalı

    satir = data["teslimler"][0]
    beklenen = {
        "id", "dosya_adi", "sha256", "kaynak", "durum", "onceki_teslim_adi", "zincir_tamam",
        "okunan", "islenen", "atlanan", "hata_sayisi", "alan_degisikligi", "kart_degisen",
        "envanter_denk", "kapi_karari", "kapi_gerekcesi", "cevap_yuklendi", "uygulayan",
        "hata_mesaji", "created_at", "updated_at", "done_at",
    }
    assert set(satir) == beklenen                                  # liste dışı: durum_gecmisi, spool_path
    assert satir["durum"] == "inceleme_bekliyor" and satir["kapi_karari"] == "inceleme"
    assert isinstance(satir["created_at"], str) and "T" in satir["created_at"]   # ISO 8601

    assert len(client.get(f"{BASE}/teslimler?limit=1").json()["teslimler"]) == 1
    assert client.get(f"{BASE}/teslimler?limit=0").status_code == 422


def test_tek_teslim_gecmis_dahil_ve_404(env):
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    r = client.get(f"{BASE}/teslimler/{tid}")
    assert r.status_code == 200
    data = r.json()
    assert [g["durum"] for g in data["durum_gecmisi"]] == [
        "alindi", "dogrulandi", "kuru_kosuldu", "inceleme_bekliyor",
    ]
    assert data["spool_path"].endswith(".xlsx")
    assert client.get(f"{BASE}/teslimler/9999").status_code == 404


def test_esikler_envden_okunur(env, monkeypatch):
    monkeypatch.setenv("TESLIM_KAPI_ALAN_DEGISIKLIGI", "500")
    assert env.client().get(f"{BASE}/teslimler").json()["esikler"]["alan_degisikligi"] == 500


# ═══════════════════════════════════════════════════════════════════════════
# 4. kuru-kos
# ═══════════════════════════════════════════════════════════════════════════

def test_kuru_kos_inceleme_bekliyorda_yeniden_kosar(env):
    """`inceleme_bekliyor` işlenebilir: baştan doğrula+kuru koş+kapı; karar/gerekçe döner."""
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    r = client.post(f"{BASE}/teslimler/{tid}/kuru-kos")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {
        "id": tid, "durum": "inceleme_bekliyor", "kapi_karari": "inceleme",
        "kapi_gerekcesi": data["kapi_gerekcesi"],
    }
    assert "ilk_teslim" in data["kapi_gerekcesi"]
    gecmis = [g["durum"] for g in _teslim(env, tid).durum_gecmisi]
    assert gecmis.count("kuru_kosuldu") == 2                       # gerçekten yeniden koştu


def test_kuru_kos_uygulandi_satirinda_409(env):
    """Kabul: `uygulandi` satırında 409; `reddedildi`/`yinelenen`/`basarisiz` de nihai."""
    client = env.client()
    for durum in ("uygulandi", "reddedildi", "yinelenen", "basarisiz", "uygulaniyor"):
        tid = _defter(env, sha256=durum.ljust(64, "0"), durum=durum)
        r = client.post(f"{BASE}/teslimler/{tid}/kuru-kos")
        assert r.status_code == 409, durum
        assert _teslim(env, tid).durum == durum
    assert client.post(f"{BASE}/teslimler/9999/kuru-kos").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 5. uygula
# ═══════════════════════════════════════════════════════════════════════════

def test_uygula_onayla_uygulandi_uygulayan_admin(env):
    """Kabul: `{"onay": true}` → `uygulandi`, `uygulayan` = admin e-postası, föyler yazıldı."""
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    r = client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": tid, "durum": "uygulandi"}
    teslim = _teslim(env, tid)
    assert teslim.uygulayan == ADMIN_1 and teslim.done_at is not None
    db = env.db()
    try:
        assert db.query(models.CaseFoy).count() == 2
    finally:
        db.close()
    # nihai: ikinci uygulama 409
    assert client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True}).status_code == 409


def test_uygula_anahtardan_bagimsiz(env):
    """Elle "Uygula" otomasyon anahtarı KAPALIYKEN de çalışır (yönetici bilinçli tıklıyor)."""
    client = env.client()
    assert client.get(f"{BASE}/teslimler").json()["etkin"] is False
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    assert client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True}).json()["durum"] == "uygulandi"


def test_uygula_onay_yoksa_400(env):
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    assert client.post(f"{BASE}/teslimler/{tid}/uygula", json={}).status_code == 400
    assert client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": False}).status_code == 400
    assert _teslim(env, tid).durum == "inceleme_bekliyor"


def test_uygula_reddedildi_satirinda_409(env):
    client = env.client()
    for durum in ("reddedildi", "alindi", "dogrulandi", "yinelenen", "uygulaniyor"):
        tid = _defter(env, sha256=durum.ljust(64, "0"), durum=durum)
        assert client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True}).status_code == 409, durum
        assert _teslim(env, tid).durum == durum
    assert client.post(f"{BASE}/teslimler/9999/uygula", json={"onay": True}).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 6. Raporlar
# ═══════════════════════════════════════════════════════════════════════════

def test_raporlar_listelenir_ve_iner(env):
    """Kabul: listelenen ad iniyor (içerik birebir, text/csv ya da text/plain)."""
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    r = client.get(f"{BASE}/teslimler/{tid}/raporlar")
    assert r.status_code == 200
    dosyalar = r.json()["dosyalar"]
    adlar = [d["ad"] for d in dosyalar]
    assert "kuru-kosu-ozeti.txt" in adlar
    assert any(ad.startswith("satir-raporu_") and ad.endswith(".csv") for ad in adlar)
    assert all(d["boyut"] > 0 for d in dosyalar)
    assert adlar == sorted(adlar)

    rapor_dizini = Path(_teslim(env, tid).rapor_dizini)
    for ad in adlar:
        r = client.get(f"{BASE}/teslimler/{tid}/raporlar/{ad}")
        assert r.status_code == 200, ad
        assert r.content == (rapor_dizini / ad).read_bytes()
        beklenen_tur = "text/csv; charset=utf-8" if ad.endswith(".csv") else "text/plain; charset=utf-8"
        assert r.headers["content-type"] == beklenen_tur
        assert ad in r.headers["content-disposition"]


def test_rapor_yol_disina_cikis_400(env):
    """Kabul: `..%2F` gibi yol 400 (404 değil — açık ret).

    Çıplak `..` segmenti burada denenmez: HTTP istemcisi (httpx, tarayıcı) nokta
    segmentini sunucuya göndermeden kendisi çözer — sunucu onu hiç görmez."""
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    for kotu in ("..%2Fetc%2Fpasswd", "..%5C..%5Cx.txt", "%2Fetc%2Fpasswd", ".gizli.txt", "a%2Fb.csv", "..%2F"):
        r = client.get(f"{BASE}/teslimler/{tid}/raporlar/{kotu}")
        assert r.status_code == 400, kotu
    assert client.get(f"{BASE}/teslimler/{tid}/raporlar/olmayan.csv").status_code == 404
    assert client.get(f"{BASE}/teslimler/{tid}/raporlar/paket.xlsx").status_code == 404   # yalnız csv/txt
    assert client.get(f"{BASE}/teslimler/9999/raporlar/kuru-kosu-ozeti.txt").status_code == 404


def test_raporlar_klasor_yoksa_bos_liste(env):
    tid = _defter(env, durum="alindi")
    client = env.client()
    assert client.get(f"{BASE}/teslimler/{tid}/raporlar").json() == {"dosyalar": []}
    assert client.get(f"{BASE}/teslimler/{tid}/raporlar/kuru-kosu-ozeti.txt").status_code == 404
    assert client.get(f"{BASE}/teslimler/9999/raporlar").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 7. Anahtar + tara
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_settings_listesinde_varsayilan_kapali(env, monkeypatch):
    """Kabul: `GET /api/admin/settings` listesinde görünüyor, varsayılan False."""
    monkeypatch.setattr(app_settings, "SessionLocal", env.db)
    client = env.client()
    listed = {s["key"]: s for s in client.get(SETTINGS_URL).json()["settings"]}
    assert listed[KEY]["value"] is False and listed[KEY]["default"] is False
    assert listed[KEY]["label"] == "Veri teslim otomasyonu"
    assert app_settings.veri_teslim_otomasyonu_etkin() is False

    assert client.put(f"{SETTINGS_URL}/{KEY}", json={"value": True}).status_code == 200
    assert client.get(f"{BASE}/teslimler").json()["etkin"] is True
    assert app_settings.veri_teslim_otomasyonu_etkin() is True


def test_tara_kapaliyken_gozcu_cagrilmaz_acikken_tarar_ve_kuru_kosar(env, monkeypatch, caplog):
    """G116: anahtar kapalı → `sharepoint_tara` ÇAĞRILMAZ (sayaç 0) + eski `not`;
    açık → gözcü sayaçları (`not` YOK) + bu çağrıda `alindi`ya düşen teslim
    `teslimi_isle(otomatik_uygula=False)` ile kuru koşuya sokulur → `islenen`.
    Gözcü istisnası → 502 + detail, log'da ERROR yok; tek teslimin işleme
    istisnası tarama sonucunu düşürmez (`durum: "hata"`)."""
    monkeypatch.setattr(app_settings, "SessionLocal", env.db)
    tara_cagri = []
    isle_cagri = []

    def _sahte_tara(*, db=None):
        """Gözcü taklidi: deftere `alindi` bir satır düşürür (sha256 çağrı başına farklı — kısmi UNIQUE)."""
        tara_cagri.append(db)
        n = len(tara_cagri)
        teslim = models.AktarimTeslimi(
            dosya_adi=f"HUKDOK_TESLIM_SP_{n}.xlsx", sha256=str(n).ljust(64, "c"), kaynak="sharepoint",
            sharepoint_item_id=f"item-{n}:etag-{n}", durum=tk.DURUM_ALINDI, durum_gecmisi=[],
        )
        db.add(teslim)
        db.commit()
        return {"yeni": 1, "yinelenen": 0, "atlanan": 2}

    def _sahte_isle(teslim_id, *, otomatik_uygula, db=None):
        isle_cagri.append((teslim_id, otomatik_uygula))
        return "inceleme_bekliyor"

    monkeypatch.setattr(tk, "sharepoint_tara", _sahte_tara)
    monkeypatch.setattr(tk, "teslimi_isle", _sahte_isle)
    client = env.client()

    # 1. Anahtar kapalı: gözcü çağrılmadı, eski metin
    r = client.post(f"{BASE}/tara")
    assert r.status_code == 200
    assert r.json() == {"yeni": 0, "yinelenen": 0, "not": "Veri teslim otomasyonu kapalı — tarama yapılmadı"}
    assert tara_cagri == [] and isle_cagri == []

    # 2. Anahtar açık: gözcü sayaçları + yalnız yeni alınan teslim kuru koşuya girdi
    client.put(f"{SETTINGS_URL}/{KEY}", json={"value": True})
    r = client.post(f"{BASE}/tara")
    assert r.status_code == 200, r.text
    assert r.json() == {"yeni": 1, "yinelenen": 0, "atlanan": 2, "islenen": [{"id": 1, "durum": "inceleme_bekliyor"}]}
    assert len(tara_cagri) == 1 and isle_cagri == [(1, False)]     # otomatik_uygula=False (gündüz kuralı)

    # 3. Önceden `alindi` kalan satır (id 1) ikinci taramada YENİDEN işlenmez; yeni gelen (id 2) işlenir
    r = client.post(f"{BASE}/tara")
    assert r.json()["islenen"] == [{"id": 2, "durum": "inceleme_bekliyor"}]
    assert isle_cagri == [(1, False), (2, False)]

    # 4. Tek teslimin işleme istisnası: tarama sonucu düşmez, WARNING
    def _isle_patla(teslim_id, *, otomatik_uygula, db=None):
        raise RuntimeError("kuru koşu patladı")

    monkeypatch.setattr(tk, "teslimi_isle", _isle_patla)
    with caplog.at_level(logging.WARNING):
        r = client.post(f"{BASE}/tara")
    assert r.status_code == 200
    assert r.json()["islenen"] == [{"id": 3, "durum": "hata", "mesaj": "kuru koşu patladı"}]
    assert any("işlenemedi" in rec.getMessage() and rec.levelno == logging.WARNING for rec in caplog.records)
    assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR]

    # 5. Gözcü istisnası: 502 + detail, log'da ERROR yok
    def _tara_patla(*, db=None):
        raise RuntimeError("Graph 503 — klasör listelenemedi")

    monkeypatch.setattr(tk, "sharepoint_tara", _tara_patla)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        r = client.post(f"{BASE}/tara")
    assert r.status_code == 502
    assert r.json() == {"detail": "SharePoint taraması başarısız: Graph 503 — klasör listelenemedi"}
    assert any(rec.levelno == logging.WARNING and "taraması başarısız" in rec.getMessage() for rec in caplog.records)
    assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR]


# ═══════════════════════════════════════════════════════════════════════════
# 8. Bildirim
# ═══════════════════════════════════════════════════════════════════════════

def test_bildirim_inceleme_bekliyor_her_admine_bir_satir_dedupe(env):
    """Kabul: `inceleme_bekliyor` geçişinde her admin e-postasına bir satır;
    aynı geçiş ikinci kez (kuru-kos) bildirim ÜRETMİYOR."""
    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]
    satirlar = _bildirimler(env)
    assert sorted(s.recipient_email for s in satirlar) == sorted([ADMIN_1, ADMIN_2.lower()])
    for s in satirlar:
        assert s.type == "veri_teslim" and s.severity == "warning"
        assert s.title == "Veri teslimi inceleme bekliyor: HUKDOK_TESLIM_PAKETI_2026-09-10.xlsx"
        assert "ilk_teslim" in s.body
        assert s.dedupe_key == f"teslim:{tid}:inceleme_bekliyor:{s.recipient_email}"
        assert s.tenant_id is None                                 # ortak havuz

    assert client.post(f"{BASE}/teslimler/{tid}/kuru-kos").status_code == 200
    assert len(_bildirimler(env)) == 2                            # dedupe: satır ikilenmedi


def test_bildirim_uygulandi_info_reddedildi_warning(env):
    client = env.client()
    icerik = _paket(_uc_satir())        # aynı BAYTLAR yeniden yüklenir (openpyxl her üretimde zaman damgası yazar)
    tid = _yukle(client, icerik).json()["id"]
    client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True})
    satirlar = _bildirimler(env)
    uygulandi = [s for s in satirlar if s.title.startswith("Veri teslimi uygulandı")]
    assert len(uygulandi) == 2 and all(s.severity == "info" for s in uygulandi)
    assert all(f"uygulayan {ADMIN_1}" in s.body and "okunan 3" in s.body for s in uygulandi)
    assert {s.dedupe_key for s in uygulandi} == {
        f"teslim:{tid}:uygulandi:{ADMIN_1}", f"teslim:{tid}:uygulandi:{ADMIN_2.lower()}",
    }

    red = _yukle(client, _paket(_uc_satir("r"), veri_sayfasi="Föyler")).json()
    assert red["durum"] == "reddedildi"
    redler = [s for s in _bildirimler(env) if s.title.startswith("Veri teslimi reddedildi")]
    assert len(redler) == 2 and all(s.severity == "warning" and "'Sheet' sayfası yok" in s.body for s in redler)

    # yinelenen: bildirim YOK
    onceki = len(_bildirimler(env))
    assert _yukle(client, icerik).json()["durum"] == "yinelenen"
    assert len(_bildirimler(env)) == onceki


def test_bildirim_basarisiz_warning_tek_error(env, monkeypatch, caplog):
    from scripts import hukdok_aktarim

    client = env.client()
    tid = _yukle(client, _paket(_uc_satir())).json()["id"]

    def _patla(*_a, **_k):
        raise RuntimeError("bağlantı koptu")

    monkeypatch.setattr(hukdok_aktarim, "aktarimi_kos", _patla)
    with caplog.at_level(logging.WARNING):
        r = client.post(f"{BASE}/teslimler/{tid}/uygula", json={"onay": True})
    assert r.status_code == 200 and r.json()["durum"] == "basarisiz"
    basarisiz = [s for s in _bildirimler(env) if s.title.startswith("Veri teslimi başarısız")]
    assert len(basarisiz) == 2 and all("RuntimeError" in s.body and s.severity == "warning" for s in basarisiz)
    errors = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert len(errors) == 1                                       # log sözleşmesi korunuyor


def test_bildirim_patlayinca_akis_devam_eder_warning(env, monkeypatch, caplog):
    """Kabul: `create_notification` patlayınca akış devam ediyor (WARNING, ERROR yok)."""
    def _patla(*_a, **_k):
        raise RuntimeError("bildirim tablosu kilitli")

    monkeypatch.setattr(bildirimler, "create_notification", _patla)
    client = env.client()
    with caplog.at_level(logging.DEBUG):
        r = _yukle(client, _paket(_uc_satir()))
    assert r.status_code == 201 and r.json()["durum"] == "inceleme_bekliyor"
    assert _teslim(env, r.json()["id"]).durum == "inceleme_bekliyor"
    assert _bildirimler(env) == []
    uyarilar = [rec for rec in caplog.records if rec.levelno == logging.WARNING and "bildirim" in rec.getMessage()]
    assert len(uyarilar) == 2                                     # alıcı başına bir WARNING
    assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR]


def test_bildir_alici_yoksa_warning_bilinmeyen_olay_sessiz(env, monkeypatch, caplog):
    tid = _defter(env, durum="inceleme_bekliyor", kapi_gerekcesi="ilk_teslim (defterde uygulanmış teslim yok)")
    db = env.db()
    try:
        assert tk.bildir(tid, "kuru_kosuldu", db=db) == []         # bildirim üretmeyen geçiş
        assert tk.bildir(tid, "yinelenen", db=db) == []
        monkeypatch.setenv("ADMIN_EMAILS", "")
        with caplog.at_level(logging.WARNING):
            assert tk.bildir(tid, "inceleme_bekliyor", db=db) == []
        assert any("ADMIN_EMAILS" in rec.getMessage() for rec in caplog.records)
        assert tk.bildir(9999, "inceleme_bekliyor", db=db) == []   # olmayan teslim: yutulur
    finally:
        db.close()
    assert _bildirimler(env) == []


def test_bildir_oturumsuz_kendi_oturumunu_acar(env, monkeypatch):
    monkeypatch.setattr(tk, "SessionLocal", env.db)
    tid = _defter(env, durum="inceleme_bekliyor", kapi_gerekcesi="bos_teslim (okunan satır 0)")
    ids = tk.bildir(tid, "inceleme_bekliyor")
    assert len(ids) == 2
    assert tk.bildir(tid, "inceleme_bekliyor") == ids              # dedupe: aynı id'ler
    assert [s.body for s in _bildirimler(env)] == ["Kapı: bos_teslim (okunan satır 0)"] * 2


def test_dedupe_anahtari_alici_sonda_kucuk_harf():
    """G082 dersi: anahtar global tekil → alıcı sonda; e-posta normalize."""
    assert tk.bildirim_dedupe_key(7, "uygulandi", "Ad.Soyad@Buro.TR") == "teslim:7:uygulandi:ad.soyad@buro.tr"
    assert set(tk.BILDIRIM_OLAYLARI) == {"inceleme_bekliyor", "basarisiz", "reddedildi", "uygulandi"}
    assert tk.BILDIRIM_OLAYLARI["uygulandi"][1] == "info"
    assert all(tk.BILDIRIM_OLAYLARI[o][1] == "warning" for o in ("inceleme_bekliyor", "basarisiz", "reddedildi"))
