"""SharePoint veri teslim klasörü yolunun kaldırılması (17.09.2026, kullanıcı kararı).

Kalkan: G109 gözcüsü (`sharepoint_tara`, `list_folder_children`), 04:00 gece turu + boot
telafisi, G110 `cevap/` yüklemesi, G147 ayrı teslim kimliği (`TESLIM_SHAREPOINT_*`),
`/api/admin/aktarim/tara`, `veri_teslim_otomasyonu` anahtarı. Kalan: panelden yükleme →
kuru koşu → "Uygula" + CLI; açılışta yalnız `boot_toparla` (kesilmiş elle uygulama).

Bu dosya kaldırılanın GERİ GELMEDİĞİNİ ve kalanın çalıştığını kilitler; `test_g109` ve
`test_g147` silindi (gördükleri davranış yok).
"""
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import sharepoint.auth_graph as auth_graph
import sharepoint.sharepoint_uploader_graph as spu
from database import Base
from services import app_settings
from services import teslim_cevap
from services import teslim_kutusu as tk
from test_g085_sure_tarayici import _api_agaci, _kw, _lider_blogundaki_joblar
from test_g107_teslim_kutusu import _defter, _index_ops


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TESLIM_SPOOL_DIR", str(tmp_path / "teslim_spool"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

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
        for sql in _index_ops("aktarim_teslimleri"):
            conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(tk, "SessionLocal", maker)
    yield SimpleNamespace(db=maker)
    engine.dispose()


def _satir(env, **alanlar):
    db = env.db()
    try:
        return _defter(db, **alanlar)
    finally:
        db.close()


# ── Zamanlayıcı ve açılış ───────────────────────────────────────────────────

def test_gece_teslim_job_u_yok_diger_joblar_saatinde():
    joblar = _lider_blogundaki_joblar()
    assert "veri_teslim" not in joblar
    saatler = {jid: (_kw(joblar[jid].args[1], "hour").value, _kw(joblar[jid].args[1], "minute").value)
               for jid in ("daily_activity_report", "conversion_retry", "deadline_scan")}
    assert saatler == {"daily_activity_report": (0, 0), "conversion_retry": (2, 30), "deadline_scan": (6, 0)}


def test_lider_blogunda_yalniz_toparlama_threadi():
    hedefler = []
    for node in __import__("ast").walk(_api_agaci()):
        if type(node).__name__ == "Call" and getattr(node.func, "attr", None) == "Thread":
            hedef = _kw(node, "target")
            if hedef is not None and hasattr(hedef, "id"):
                hedefler.append(hedef.id)
    assert "teslim_boot_toparla" in hedefler
    assert "teslim_boot_catch_up" not in hedefler and "boot_catch_up_scan" in hedefler


def test_boot_toparla_kesilmis_uygulamayi_incelemeye_alir(env):
    kesik = _satir(env, sha256="c" * 64, durum=tk.DURUM_UYGULANIYOR)
    bekleyen = _satir(env, sha256="d" * 64, durum=tk.DURUM_ALINDI)

    assert tk.boot_toparla() == 1

    db = env.db()
    try:
        assert db.get(models.AktarimTeslimi, kesik).durum == tk.DURUM_INCELEME
        assert db.get(models.AktarimTeslimi, bekleyen).durum == tk.DURUM_ALINDI     # işlenmez
    finally:
        db.close()


def test_boot_toparla_istisnayi_tek_warning_ile_yutar(monkeypatch, caplog):
    def _patla(**_kw):
        raise RuntimeError("db yok")

    monkeypatch.setattr(tk, "acilis_toparla", _patla)
    with caplog.at_level(logging.INFO):
        assert tk.boot_toparla() is None
    assert [r.levelno for r in caplog.records if r.levelno >= logging.WARNING] == [logging.WARNING]


# ── Kaldırılan semboller geri gelmedi ────────────────────────────────────────

@pytest.mark.parametrize("modul, ad", [
    (tk, "sharepoint_tara"), (tk, "gece_turu"), (tk, "boot_catch_up"), (tk, "TESLIM_SP_CONFIG"),
    (tk, "teslim_gelen_klasoru"), (tk, "_cevap_dene"),
    (teslim_cevap, "cevap_yukle"), (teslim_cevap, "cevap_klasoru"), (teslim_cevap, "bekleyen_cevaplari_yukle"),
    (spu, "list_folder_children"), (auth_graph, "CONFIG_TESLIM"),
    (app_settings, "veri_teslim_otomasyonu_etkin"),
])
def test_kaldirilan_sembol_yok(modul, ad):
    assert not hasattr(modul, ad)


def test_tek_sharepoint_kimligi_bilinmeyen_config_valueerror():
    assert auth_graph.CONFIG_TYPES == ("default",)
    with pytest.raises(ValueError, match="teslim"):
        auth_graph._get_msal_app("teslim")


def test_anahtar_registryde_yok_tara_ucu_yok():
    assert "veri_teslim_otomasyonu" not in app_settings.SETTINGS_REGISTRY
    from routes.admin import router
    yollar = {getattr(r, "path", "") for r in router.routes}
    assert "/api/admin/aktarim/tara" not in yollar
    assert "/api/admin/aktarim/teslimler/{teslim_id}/uygula" in yollar


def test_uygulama_eslesme_dosyasini_rapor_dizinine_yazar(env, tmp_path, monkeypatch):
    """Eşleşme CSV'si SharePoint yüklemesiyle birlikte kaybolmasın — uygulama yolu üretir."""
    cagri = []

    def _uret(teslim_id, hedef, *, db=None):
        cagri.append((teslim_id, hedef.name))
        hedef.write_text("x", encoding="utf-8")
        return hedef

    monkeypatch.setattr(teslim_cevap, "eslesme_csv_uret", _uret)
    db = env.db()
    try:
        yol = tk._eslesme_dene(db, 7, rapor=tmp_path, dosya_adi="HUKDOK_TESLIM_X.xlsx")
    finally:
        db.close()
    assert cagri == [(7, "eslesme_HUKDOK_TESLIM_X.csv")] and yol.is_file()


def test_eslesme_hatasi_warning_durum_degismez(env, tmp_path, monkeypatch, caplog):
    def _patla(*_a, **_kw):
        raise ValueError("spool yok")

    monkeypatch.setattr(teslim_cevap, "eslesme_csv_uret", _patla)
    db = env.db()
    try:
        with caplog.at_level(logging.WARNING):
            assert tk._eslesme_dene(db, 7, rapor=tmp_path, dosya_adi="HUKDOK_TESLIM_X.xlsx") is None
    finally:
        db.close()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
