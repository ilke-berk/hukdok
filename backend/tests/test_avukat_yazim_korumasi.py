"""27.09 avukat yazım koruması (kullanıcı kararı: "ileride kaydedilirken hatayı engellemeliyiz").

Kilitlenen davranışlar:
  1. `kanonik_avukat_metni`: bilinen kişi listedeki yazıma iner (tek/çoklu, "Av." önekli,
     soyadı eksik), aynı kişi bir kez kalır, listede olmayan vekil aynen kalır, ayraç içeren
     liste kaydı ("Hanyaloğlu & Acar") bölünmez.
  2. `listede_olmayan_yeni_adlar` / `avukat_adlarini_dogrula`: YENİ bilinmeyen ad yakalanır,
     değişmeden geri gelen eski değer engellenmez.
  3. Uçlar: dava ekle/güncelle listede olmayan YENİ adla 422 (api.py handler), ERROR yok.
  4. Yönetim listesi: aynı kişi farklı yazımla ikinci kez eklenemez (`ad_kimligi`).
  5. Aktarım: liste yazımı kart yazımını ezer (liste doğru yazımın tek kaynağı).
"""
import types

import pytest

import models
from managers import case_manager, lawyer_resolver
from managers.lawyer_resolver import AvukatListedeYok, kanonik_avukat_metni, listede_olmayan_yeni_adlar
from managers.reference_lists import ad_kimligi
from tests import test_g179_ekip_cevabi_1209 as g179
from tests.test_g064_aktarim_cekirdek import _kart

db_env = g179.db_env          # nitelik ataması: pytest için aynı fixture, ruff F811 sanmaz

LISTE = [
    {"code": "TUGCEUNG", "name": "Tuğçe Ungör Yanık"},
    {"code": "SERAPTUR", "name": "Serap Turgal"},
    {"code": "AYSEGULH", "name": "Ayşe Gül Hanyaloğlu"},
    {"code": "H&A", "name": "Hanyaloğlu & Acar"},
]


class _Config:
    def get_lawyers(self):
        return LISTE


@pytest.fixture
def liste(monkeypatch):
    monkeypatch.setattr(lawyer_resolver, "DynamicConfig", types.SimpleNamespace(get_instance=lambda: _Config()))


# ── 1. kanonik yazım ────────────────────────────────────────────────────────

@pytest.mark.parametrize("girdi, beklenen", [
    ("TUGCE UNGOR", "Tuğçe Ungör Yanık"),
    ("Tuğçe Üngör Yanık", "Tuğçe Ungör Yanık"),
    ("Av. Tuğçe Ungor Yanık", "Tuğçe Ungör Yanık"),
    ("  SERAP   TURGAL ", "Serap Turgal"),
    ("TUĞÇE ÜNGÖR;HAYRETTİN ÇİL; SERAP TURGAL; TUGCE UNGOR YANIK",
     "Tuğçe Ungör Yanık;HAYRETTİN ÇİL;Serap Turgal"),
    ("Hanyaloğlu & Acar", "Hanyaloğlu & Acar"),          # ayraçlı liste kaydı bölünmez
    ("Mahmut Bilinmez", "Mahmut Bilinmez"),              # listede yok → aynen
    ("", ""),
    (None, None),
])
def test_kanonik_avukat_metni(liste, girdi, beklenen):
    assert kanonik_avukat_metni(girdi) == beklenen


# ── 2. yeni bilinmeyen ad ───────────────────────────────────────────────────

def test_listede_olmayan_yeni_adlar(liste):
    assert listede_olmayan_yeni_adlar("Mahmut Bilinmez") == ["Mahmut Bilinmez"]
    assert listede_olmayan_yeni_adlar("TUGCE UNGOR") == []                              # listede (farklı yazım)
    assert listede_olmayan_yeni_adlar("Hanyaloğlu & Acar") == []
    assert listede_olmayan_yeni_adlar("Arşiv Dosya Yöneticisi", "Arşiv Dosya Yöneticisi") == []   # değişmedi
    assert listede_olmayan_yeni_adlar("Serap Turgal;Murat Arslan", "Murat Arslan") == []          # eski parça
    assert listede_olmayan_yeni_adlar(None) == [] and listede_olmayan_yeni_adlar("  ") == []


def test_avukat_adlarini_dogrula(liste):
    case_manager.avukat_adlarini_dogrula({"responsible_lawyer_name": "TUGCE UNGOR",
                                          "lawyers": [{"name": "Serap Turgal"}]})
    with pytest.raises(AvukatListedeYok) as exc:
        case_manager.avukat_adlarini_dogrula({"uyap_lawyer_name": "Yeni Kişi"})
    assert "Yeni Kişi" in str(exc.value) and "Avukatlar" in str(exc.value)
    # kartta zaten duran değer (sorumlu ya da avukat listesi) engellenmez
    case_manager.avukat_adlarini_dogrula(
        {"responsible_lawyer_name": "Arşiv Dosya Yöneticisi", "lawyers": [{"name": "Murat Arslan"}]},
        {"responsible_lawyer_name": "Arşiv Dosya Yöneticisi", "lawyers": ["Murat Arslan"]},
    )


# ── 3. uçlar ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    from starlette.testclient import TestClient

    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter

    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def _payload(**ek):
    return {"tracking_no": "2026/0001", "esas_no": "2026/1", "parties": [], "lawyers": [], **ek}


def test_dava_ekle_listede_olmayan_adla_422(client, db_env, monkeypatch, caplog):
    """Doğrulama yazımın yapıldığı OTURUMUN avukat listesine bakar (CI'da çıplak DB — bu test
    kendi listesini kurar; config önbelleğine dayanmaz)."""
    db = db_env()
    try:
        db.add(models.Lawyer(code="TUGCEUNG", name="Tuğçe Ungör Yanık"))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(case_manager, "SessionLocal", db_env)
    resp = client.post("/api/cases", json=_payload(responsible_lawyer_name="Mahmut Bilinmez"))
    assert resp.status_code == 422
    assert "Mahmut Bilinmez" in resp.json()["detail"]
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []
    db = db_env()
    try:
        assert db.query(models.Case).count() == 0                      # kart açılmadı
    finally:
        db.close()


def test_bos_listede_dogrulama_atlanir(db_env):
    """Liste hiç yüklenmemişse (yeni kurulum) kayıt engellenmez."""
    db = db_env()
    try:
        case_manager.avukat_adlarini_dogrula({"responsible_lawyer_name": "Herhangi Biri"}, db=db)
    finally:
        db.close()


def test_dava_guncelle_avukat_hatasi_422(client, monkeypatch):
    from routes import cases

    def _red(*a, **kw):
        raise AvukatListedeYok(["Yeni Kişi"])

    monkeypatch.setattr(cases, "update_case", _red)
    resp = client.put("/api/cases/1", json=_payload())
    assert resp.status_code == 422
    assert "Yeni Kişi" in resp.json()["detail"]


# ── 4. yönetim listesi ──────────────────────────────────────────────────────

def test_ad_kimligi_ayni_kisiyi_tanir():
    assert ad_kimligi("lawyers", "Av. Tuğçe Ungör Yanık") == ad_kimligi("lawyers", "TUGCE  UNGOR YANIK")
    assert ad_kimligi("lawyers", "Serap Turgal") != ad_kimligi("lawyers", "Serap Turgut")
    # diğer listelerde eski davranış (yalnız Türkçe büyük harf)
    assert ad_kimligi("statuses", "Çözüldü") != ad_kimligi("statuses", "Cozuldu")


# ── 5. aktarım: liste yazımı kazanır ────────────────────────────────────────

def test_aktarim_haritasi_liste_yazimini_one_alir(db_env):
    from scripts.hukdok_aktarim import _baslik_anahtari, avukat_haritasi_kur

    db = db_env()
    try:
        db.add(models.Lawyer(code="TUGCEUNG", name="Tuğçe Ungör Yanık"))
        db.add(models.Lawyer(code="ESKI", name="DUGCEM AYDIYE BALIKCI"))      # düzeltilmemiş BÜYÜK kayıt
        _kart(db, "D1.K1........0001.HUKUK.00000", "", responsible_lawyer_name="Tuğçe Üngör Yanık")
        _kart(db, "D1.K2........0002.HUKUK.00000", "", responsible_lawyer_name="Murat Arslan")
        db.commit()
        harita = avukat_haritasi_kur(db)
    finally:
        db.close()
    assert harita[_baslik_anahtari("Tugce Ungor Yanık")] == "Tuğçe Ungör Yanık"     # liste kazandı
    assert harita[_baslik_anahtari("Murat Arslan")] == "Murat Arslan"               # listede yok → kart
    assert _baslik_anahtari("DUGCEM AYDIYE BALIKCI") in harita                       # BÜYÜK kayıt: eski davranış
