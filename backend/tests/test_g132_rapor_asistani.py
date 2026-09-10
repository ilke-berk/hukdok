"""G132 — Rapor asistanı: Gemini JSON şemalı `/api/reports/chat` NDJSON akışı,
sunucu tarafı tanım doğrulaması (K6), `rapor_asistani` anahtarı (K8),
`GEMINI_RAPOR_MODEL` (K9).

Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.4 (`/chat`), §2.6 (akış), §2.7 (env).

Düzen: Gemini SAHTE — `analyzer._gemini_call_with_retry` monkeypatch'lenir (asistan
yalnız bu yoldan çağırır; sahte çağrıyı kaydeder, hazır cevap döner ya da istisna
atar). Anahtar gerçek `app_settings` + süreç içi sqlite; kimlik `get_current_user`
override'ı + `ADMIN_EMAILS` (GERÇEK `require_admin`). Ağ/DB yok.
"""
import inspect
import json
import logging
import os
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import analyzer  # noqa: E402
import gemini_client  # noqa: E402
from config.settings import Settings, settings  # noqa: E402
from schemas_rapor import (  # noqa: E402
    AsistanTanimi, RaporAsistanCevabi, RaporDogrulamaHatasi, RaporTanimi, SohbetMesaji,
)
from services import app_settings  # noqa: E402
from services.rapor import asistan, registry  # noqa: E402

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
USER = "avukat@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
CHAT = "/api/reports/chat"
SETTINGS_URL = "/api/admin/settings"
KEY = "rapor_asistani"

GECERLI_TANIM = {
    "veri_kaynagi": "davalar",
    "kolonlar": ["tracking_no", "responsible_lawyer_name", "opening_date"],
    "filtreler": [
        {"alan": "opening_date", "op": "between", "degerler": ["2025-01-01", "2025-12-31"]},
        {"alan": "karar_tarihi", "op": "is_null"},
        {"alan": "status", "op": "eq", "deger": "DERDEST"},
    ],
    "siralama": [{"alan": "opening_date", "yon": "desc"}],
}


def _cevap(tanim=GECERLI_TANIM, cevap="2025'te açılan, kararı olmayan derdest davalar hazırlandı.", eylem="indir_xlsx"):
    return {"cevap": cevap, "tanim": tanim, "eylem": eylem}


def _yanit(metin, finish="STOP"):
    return SimpleNamespace(text=metin, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))])


def _mesajlar(*icerikler):
    roller = ["user", "assistant"]
    n = len(icerikler)
    # son mesaj kullanıcının olacak şekilde dönüşümlü rol
    return [{"rol": roller[(n - 1 - i) % 2], "icerik": m} for i, m in enumerate(icerikler)]


def _olaylar(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(satir) for satir in r.text.splitlines() if satir.strip()]


@pytest.fixture()
def sahte_gemini(monkeypatch):
    """`analyzer._gemini_call_with_retry` yerine kayıt tutan sahte; `sonuc` bir
    yanıt nesnesi ya da fırlatılacak istisnadır."""
    kayit = SimpleNamespace(cagrilar=[], sonuc=_yanit(json.dumps(_cevap(), ensure_ascii=False)))

    async def _sahte(gen_config, payload, max_retries=5, stats=None, model=None):
        kayit.cagrilar.append({"config": gen_config, "payload": payload, "stats": stats, "model": model})
        if isinstance(kayit.sonuc, BaseException):
            raise kayit.sonuc
        return kayit.sonuc

    monkeypatch.setattr(analyzer, "_gemini_call_with_retry", _sahte)
    return kayit


@pytest.fixture()
def env(monkeypatch, sahte_gemini):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import admin as admin_mod
    from routes import reports as route_mod

    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(app_settings, "SessionLocal", maker)
    monkeypatch.setattr(route_mod, "SessionLocal", maker)

    def _client(email=ADMIN, tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.include_router(admin_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    def _ac(deger=True):
        app_settings.set_setting_bool(KEY, deger, updated_by=ADMIN)

    yield SimpleNamespace(client=_client, ac=_ac, gemini=sahte_gemini, db=maker)
    engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Anahtar (K8) + yetki + gövde sınırları
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_varsayilan_kapali_ve_admin_settingste_listelenir(env):
    assert app_settings.SETTINGS_REGISTRY[KEY]["default"] is False
    assert app_settings.rapor_asistani_etkin() is False
    listed = {s["key"]: s for s in env.client().get(SETTINGS_URL).json()["settings"]}
    assert listed[KEY]["value"] is False and listed[KEY]["default"] is False
    assert listed[KEY]["label"] == "Rapor asistanı (AI)"
    assert "Gemini" in listed[KEY]["description"] and "devam eder" in listed[KEY]["description"]


def test_anahtar_kapaliyken_409_akis_acilmaz(env):
    r = env.client().post(CHAT, json={"mesajlar": _mesajlar("derdest davalar")})
    assert r.status_code == 409
    assert r.json()["detail"] == "rapor_asistani kapalı"
    assert env.gemini.cagrilar == []
    # kapı gövdeden ÖNCE: bozuk gövde de 409 alır (özellik kapalıyken hiçbir şey ayrıştırılmaz)
    assert env.client().post(CHAT, json={"mesajlar": []}).status_code == 409


def test_anahtar_acilinca_calisir_ve_panelden_kapatilinca_yine_409(env):
    client = env.client()
    assert client.put(f"{SETTINGS_URL}/{KEY}", json={"value": True}).status_code == 200
    olaylar = _olaylar(client.post(CHAT, json={"mesajlar": _mesajlar("derdest davalar")}))
    assert olaylar[-1]["status"] == "complete"
    assert client.put(f"{SETTINGS_URL}/{KEY}", json={"value": False}).status_code == 200
    assert client.post(CHAT, json={"mesajlar": _mesajlar("derdest davalar")}).status_code == 409


def test_yonetici_degil_403(env):
    env.ac()
    r = env.client(email=USER).post(CHAT, json={"mesajlar": _mesajlar("derdest davalar")})
    assert r.status_code == 403
    assert env.gemini.cagrilar == []


@pytest.mark.parametrize("govde, alan", [
    ({"mesajlar": [{"rol": "user", "icerik": "m"}] * 21}, "mesajlar"),
    ({"mesajlar": [{"rol": "user", "icerik": "x" * 4001}]}, "mesajlar.0.icerik"),
    ({"mesajlar": []}, "mesajlar"),
    ({"mesajlar": [{"rol": "user", "icerik": ""}]}, "mesajlar.0.icerik"),
    ({"mesajlar": [{"rol": "assistant", "icerik": "son mesaj asistan"}]}, "mesajlar"),
    ({"mesajlar": [{"rol": "system", "icerik": "rol yok"}]}, "mesajlar.0.rol"),
    ({"mesajlar": _mesajlar("m"), "mevcut_tanim": {"veri_kaynagi": "davalar", "kolonlar": []}},
     "mevcut_tanim.kolonlar"),
    ({"mesajlar": _mesajlar("m"), "fazla": 1}, "fazla"),
])
def test_govde_sinirlari_422(env, govde, alan):
    env.ac()
    r = env.client().post(CHAT, json=govde)
    assert r.status_code == 422, r.text
    detay = r.json()["detail"]
    assert set(detay) == {"alan", "sebep"} and detay["alan"] == alan
    assert env.gemini.cagrilar == []


def test_tam_20_mesaj_ve_4000_karakter_gecer(env):
    env.ac()
    mesajlar = _mesajlar(*["x" * 4000] * 20)
    olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": mesajlar}))
    assert olaylar[-1]["status"] == "complete"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Akış sözleşmesi (plan §2.6)
# ═══════════════════════════════════════════════════════════════════════════

def test_gecerli_tanim_info_sonra_complete(env, caplog):
    env.ac()
    with caplog.at_level(logging.WARNING):
        olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar(
            "2025'te açılan, karar tarihi boş derdest davaları avukat adıyla listele, Excel ver")}))
    assert [o["status"] for o in olaylar] == ["info", "complete"]
    assert olaylar[0] == {"status": "info", "message": "Rapor tanımı hazırlanıyor"}
    son = olaylar[-1]
    assert set(son) == {"status", "cevap", "tanim", "eylem"}
    assert son["cevap"].startswith("2025'te açılan") and son["eylem"] == "indir_xlsx"
    # tanım sunucuda RaporTanimi'ye çevrilmiş: between listesi, is_null değersiz, eq metin
    assert son["tanim"]["veri_kaynagi"] == "davalar"
    assert son["tanim"]["kolonlar"] == ["tracking_no", "responsible_lawyer_name", "opening_date"]
    assert son["tanim"]["filtreler"] == [
        {"alan": "opening_date", "op": "between", "deger": ["2025-01-01", "2025-12-31"]},
        {"alan": "karar_tarihi", "op": "is_null", "deger": None},
        {"alan": "status", "op": "eq", "deger": "DERDEST"},
    ]
    assert son["tanim"]["siralama"] == [{"alan": "opening_date", "yon": "desc"}]
    RaporTanimi.model_validate(son["tanim"])   # istemcinin /export'a aynen gönderebileceği gövde
    assert "process_id" not in son
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_katalog_disi_kolon_warning_tanim_null_yine_complete(env, caplog):
    """Kabul: geçersiz tanım hiçbir zaman istemciye `tanim` olarak gitmez."""
    env.ac()
    bozuk = dict(GECERLI_TANIM, kolonlar=["tracking_no", "notes"])   # notes katalog DIŞI (PII)
    env.gemini.sonuc = _yanit(json.dumps(_cevap(tanim=bozuk), ensure_ascii=False))
    with caplog.at_level(logging.WARNING):
        olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("notlarla listele")}))
    assert [o["status"] for o in olaylar] == ["info", "warning", "complete"]
    assert "kolonlar[1]" in olaylar[1]["message"] and "notes" in olaylar[1]["message"]
    son = olaylar[-1]
    assert son["tanim"] is None and son["eylem"] is None
    assert son["cevap"].startswith("2025'te açılan")   # asistan metni korunur
    assert [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.parametrize("tanim, alan", [
    (dict(GECERLI_TANIM, veri_kaynagi="sql"), "veri_kaynagi"),
    (dict(GECERLI_TANIM, filtreler=[{"alan": "status", "op": "contains", "deger": "x"}]), "filtreler[0]"),
    (dict(GECERLI_TANIM, filtreler=[{"alan": "muvekkil_adlari", "op": "eq", "deger": "x"}]), "filtreler[0]"),
    (dict(GECERLI_TANIM, filtreler=[{"alan": "opening_date", "op": "gte", "deger": "dün"}]), "filtreler[0]"),
    (dict(GECERLI_TANIM, siralama=[{"alan": "foy_sayisi", "yon": "asc"}]), "siralama[0]"),
    (dict(GECERLI_TANIM, kolonlar=["tracking_no", "tracking_no"]), "kolonlar"),
    (dict(GECERLI_TANIM, kolonlar=[]), "kolonlar"),
    (dict(GECERLI_TANIM, filtreler=[{"alan": "tenant_id", "op": "eq", "deger": "x"}]), "filtreler[0]"),
], ids=["kaynak", "op-tip", "turetilmis-filtre", "tarih-bicimi", "turetilmis-sira", "tekrar", "bos", "tenant"])
def test_registry_ve_pydantic_dogrulamasi_ayni_yol(env, tanim, alan):
    """Manuel tanımla aynı iki katman: Pydantic sınırlar + motor registry denetimi."""
    env.ac()
    env.gemini.sonuc = _yanit(json.dumps(_cevap(tanim=tanim), ensure_ascii=False))
    olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")}))
    assert [o["status"] for o in olaylar] == ["info", "warning", "complete"]
    assert alan in olaylar[1]["message"]
    assert olaylar[-1]["tanim"] is None


def test_asistan_soru_sorarsa_tanim_null_warning_yok(env):
    env.ac()
    env.gemini.sonuc = _yanit(json.dumps(_cevap(tanim=None, cevap="Hangi yıl?", eylem=None), ensure_ascii=False))
    olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("davaları listele")}))
    assert [o["status"] for o in olaylar] == ["info", "complete"]
    assert olaylar[-1] == {"status": "complete", "cevap": "Hangi yıl?", "tanim": None, "eylem": None}


def test_tanim_null_ile_gelen_eylem_sunucuda_dusurulur(env, caplog):
    """Gerçek Gemini duman testi bulgusu (07.09): model kuralı ihlal edip tanim=null +
    eylem=onizle döndürdü. Sözleşme 'tanım yoksa eylem yok' — sunucu keser, WARNING
    loglar (ERROR değil; nihai başarısızlık yok), akış yine complete ile biter."""
    env.ac()
    env.gemini.sonuc = _yanit(json.dumps(_cevap(tanim=None, cevap="Liste aşağıda.", eylem="onizle"), ensure_ascii=False))
    with caplog.at_level(logging.WARNING):
        olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("davaları listele")}))
    assert [o["status"] for o in olaylar] == ["info", "complete"]
    assert olaylar[-1]["tanim"] is None and olaylar[-1]["eylem"] is None
    assert any("eylem dusuruldu" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def _failed_sozlesmesi(olaylar, kod):
    assert [o for o in olaylar if o["status"] == "complete"] == []
    son = olaylar[-1]
    assert set(son) == {"status", "error_ozet", "error_kod"}
    assert son["status"] == "failed" and son["error_kod"] == kod
    assert son["error_ozet"].strip() and "Kod:" in son["error_ozet"]
    return son


def _api_hata(code):
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, {"error": {"message": "hata", "status": "X"}})


@pytest.mark.parametrize("istisna, kod", [
    (_api_hata(429), "gemini_saturated"),
    (gemini_client.GeminiCircuitOpenError("models/test-flash", 42.0), "gemini_saturated"),
    (_api_hata(503), "gemini_saturated"),
    (_api_hata(403), "analysis_error"),
    (RuntimeError("bilinmez"), "analysis_error"),
], ids=["429", "devre-kesici", "503", "403", "bilinmez"])
def test_gemini_hatasi_failed_tek_error(env, caplog, istisna, kod):
    env.ac()
    env.gemini.sonuc = istisna
    with caplog.at_level(logging.WARNING):
        olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")}))
    assert [o["status"] for o in olaylar] == ["info", "failed"]
    _failed_sozlesmesi(olaylar, kod)
    hatalar = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(hatalar) == 1 and kod in hatalar[0].getMessage()


def test_devre_kesici_ozeti_kullaniciya_1_dakika_der(env):
    env.ac()
    env.gemini.sonuc = gemini_client.GeminiCircuitOpenError("models/test-flash", 42.0)
    son = _failed_sozlesmesi(_olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")})),
                             "gemini_saturated")
    assert "1 dakika" in son["error_ozet"]


@pytest.mark.parametrize("yanit, kod", [
    (_yanit("kesik {", finish="MAX_TOKENS"), "gemini_truncated"),
    (_yanit(None, finish="SAFETY"), "gemini_blocked"),
    (_yanit("bu json değil"), "schema_invalid"),
    (_yanit(json.dumps({"tanim": None})), "schema_invalid"),        # cevap zorunlu
    (_yanit(json.dumps({"cevap": "x", "eylem": "yazdir"})), "schema_invalid"),
    (_yanit(None, finish="STOP"), "analysis_error"),                 # boş yanıt, neden yok
], ids=["max-tokens", "safety", "json-degil", "cevap-yok", "eylem-disi", "bos"])
def test_yanit_hatalari_etiketi(env, caplog, yanit, kod):
    env.ac()
    env.gemini.sonuc = yanit
    with caplog.at_level(logging.WARNING):
        olaylar = _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")}))
    _failed_sozlesmesi(olaylar, kod)
    assert sum(1 for r in caplog.records if r.levelno >= logging.ERROR) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. Gemini isteği: prompt, mevcut_tanim, contents, model (K9)
# ═══════════════════════════════════════════════════════════════════════════

def test_gemini_cagrisi_json_semali_ve_retry_uzerinden(env, monkeypatch):
    env.ac()
    monkeypatch.setattr(settings, "gemini_rapor_model", "models/rapor-test")
    _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")}))
    assert len(env.gemini.cagrilar) == 1
    c = env.gemini.cagrilar[0]
    assert c["model"] == "models/rapor-test"
    assert c["stats"] == {"retry_count": 0, "retry_wait_ms": 0}
    assert c["config"].response_mime_type == "application/json"
    assert c["config"].response_schema is RaporAsistanCevabi


def test_mevcut_tanim_prompta_girer(env):
    env.ac()
    mevcut = {"veri_kaynagi": "muvekkiller", "kolonlar": ["name", "il"],
              "filtreler": [{"alan": "il", "op": "eq", "deger": "Ankara"}], "siralama": []}
    _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("telefonu da ekle"), "mevcut_tanim": mevcut}))
    talimat = env.gemini.cagrilar[0]["config"].system_instruction
    assert "MEVCUT TANIM" in talimat
    assert json.dumps(mevcut, ensure_ascii=False) in talimat
    # mevcut tanım yoksa bölüm de yok
    _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("telefonu da ekle")}))
    assert "MEVCUT TANIM" not in env.gemini.cagrilar[1]["config"].system_instruction


def test_prompt_katalogu_registryden_gomer(env):
    env.ac()
    _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar("liste")}))
    talimat = env.gemini.cagrilar[0]["config"].system_instruction
    for kaynak in registry.KAYNAKLAR.values():
        assert f"## {kaynak.anahtar} — {kaynak.etiket}" in talimat
        for kolon in kaynak.kolonlar.values():
            if kolon.bag is None:      # G166: bağlı kolonlar ilişki başına tek satırla girer (test_g166)
                assert f"\n{kolon.anahtar} · {kolon.etiket} · {kolon.tip}" in talimat
    assert "status · Durum · liste · DANIŞ|DERDEST|" in talimat
    assert "muvekkil_adlari · Müvekkiller · metin · türetilmiş" in talimat
    # kurallar + bugün
    for parca in ("YALNIZ katalogdaki", "tanim=null", "indir_xlsx", "Bugünün tarihi", "is_null"):
        assert parca in talimat
    assert "notes" not in talimat and "tenant_id" not in talimat and "tc_no" not in talimat


def test_katalog_metni_tum_kolonlari_icerir_elle_liste_yok():
    metin = asistan.katalog_metni()
    for kaynak in registry.KAYNAKLAR.values():
        assert f"varsayılan kolonlar: {', '.join(kaynak.varsayilan_kolonlar)}" in metin
        for kolon in kaynak.kolonlar.values():
            if kolon.bag is None:      # G166: bağlı kolonlar ilişki satırıyla (test_g166)
                assert f"\n{kolon.anahtar} · " in metin
    kaynak = inspect.getsource(asistan)
    assert "registry.KAYNAKLAR" in kaynak and "secenekleri_getir" in kaynak


def test_contents_rol_eslemesi_ve_son_20(env):
    env.ac()
    icerikler = [f"m{i}" for i in range(20)]           # 20 mesaj (sınır), dönüşümlü rol
    _olaylar(env.client().post(CHAT, json={"mesajlar": _mesajlar(*icerikler)}))
    payload = env.gemini.cagrilar[0]["payload"]
    # baştaki asistan mesajı atılır (Gemini kullanıcıyla başlar) → 19 içerik, ilk ve son user
    assert [c.role for c in payload][:3] == ["user", "model", "user"]
    assert payload[0].role == "user" and payload[-1].role == "user"
    assert payload[-1].parts[0].text == "m19" and len(payload) == 19


def test_icerikleri_kur_son_20_ve_bas_asistan_atilir():
    mesajlar = [SohbetMesaji(rol="user", icerik=f"u{i}") for i in range(25)]
    icerikler = asistan.icerikleri_kur(mesajlar)
    assert len(icerikler) == 20 and icerikler[0].parts[0].text == "u5"
    karisik = [SohbetMesaji(rol="assistant", icerik="hoş geldiniz"), SohbetMesaji(rol="user", icerik="liste"),
               SohbetMesaji(rol="assistant", icerik="hangi yıl?"), SohbetMesaji(rol="user", icerik="2025")]
    icerikler = asistan.icerikleri_kur(karisik)
    assert [(c.role, c.parts[0].text) for c in icerikler] == [("user", "liste"), ("model", "hangi yıl?"), ("user", "2025")]


def test_get_rapor_model_env_ve_fallback(monkeypatch):
    monkeypatch.setattr(settings, "gemini_rapor_model", "models/rapor-x")
    assert asistan.get_rapor_model() == "models/rapor-x"
    monkeypatch.setattr(settings, "gemini_rapor_model", "  ")
    monkeypatch.setenv("GEMINI_INTAKE_MODEL", "models/intake-y")
    assert asistan.get_rapor_model() == "models/intake-y"
    monkeypatch.delenv("GEMINI_INTAKE_MODEL", raising=False)
    from case_intake_analyzer import DEFAULT_INTAKE_MODEL
    assert asistan.get_rapor_model() == DEFAULT_INTAKE_MODEL


def test_settings_gemini_rapor_model(monkeypatch):
    monkeypatch.delenv("GEMINI_RAPOR_MODEL", raising=False)
    assert Settings().gemini_rapor_model == ""
    monkeypatch.setenv("GEMINI_RAPOR_MODEL", "models/gemini-3.6-flash")
    assert Settings().gemini_rapor_model == "models/gemini-3.6-flash"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Tip çevirisi (Gemini metin değerleri → RaporTanimi)
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_tanimi_cevirisi_tiplere_gore():
    t = AsistanTanimi(
        veri_kaynagi="davalar", kolonlar=["tracking_no"],
        filtreler=[
            {"alan": "active", "op": "eq", "deger": "true"},
            {"alan": "maddi_tazminat", "op": "gte", "deger": "150000"},
            {"alan": "dava_degeri", "op": "between", "degerler": ["1000.50", "2 000"]},
            {"alan": "foy_sayisi", "op": "eq", "deger": "3"},
            {"alan": "status", "op": "in", "degerler": ["DERDEST", "KARAR"]},
            {"alan": "status", "op": "in", "deger": "DERDEST"},           # tek değer 'in' → liste
            {"alan": "opening_date", "op": "gte", "deger": " 2025-01-01 "},
            {"alan": "karar_tarihi", "op": "not_null", "deger": "gereksiz"},
            {"alan": "subject", "op": "contains", "deger": "malpraktis"},
            {"alan": "olmayan", "op": "eq", "deger": "5"},
        ],
    )
    govde = asistan.asistan_tanimini_cevir(t)
    assert [f.get("deger") for f in govde["filtreler"]] == [
        True, 150000, [1000.5, 2000], 3, ["DERDEST", "KARAR"], ["DERDEST"], "2025-01-01", None, "malpraktis", "5",
    ]
    assert "deger" not in govde["filtreler"][7]        # değersiz op: anahtar hiç yok


def test_bozuk_sayi_metin_kalir_ve_motor_reddeder():
    t = AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                      filtreler=[{"alan": "maddi_tazminat", "op": "gte", "deger": "yüz bin"}])
    assert asistan.asistan_tanimini_cevir(t)["filtreler"][0]["deger"] == "yüz bin"
    with pytest.raises(RaporDogrulamaHatasi) as e:
        asistan.tanimi_dogrula(t)
    assert e.value.alan == "filtreler[0]" and "sayısal" in e.value.sebep
    t2 = AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                       filtreler=[{"alan": "active", "op": "eq", "deger": "belki"}])
    with pytest.raises(RaporDogrulamaHatasi):
        asistan.tanimi_dogrula(t2)
    # sonlu olmayan sayı metin kalır (int() OverflowError'a düşmez); kabul/ret motorun kararı
    t3 = AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                       filtreler=[{"alan": "maddi_tazminat", "op": "gte", "deger": "Infinity"}])
    assert asistan.asistan_tanimini_cevir(t3)["filtreler"][0]["deger"] == "Infinity"


def test_tanimi_dogrula_gecerli_rapor_tanimi_doner():
    t = AsistanTanimi.model_validate(GECERLI_TANIM)
    rt = asistan.tanimi_dogrula(t)
    assert isinstance(rt, RaporTanimi) and rt.filtreler[0].deger == ["2025-01-01", "2025-12-31"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Kod incelemesi bekçileri (kabul: DB yok, client.aio yok, Gemini şeması)
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_db_ve_gemini_clienta_dokunmaz():
    kaynak = inspect.getsource(asistan)
    assert "SessionLocal" not in kaynak
    assert "from database" not in kaynak and "import database" not in kaynak
    assert "client.aio" not in kaynak and "get_client" not in kaynak and "generate_content(" not in kaynak
    assert "_gemini_call_with_retry(" in kaynak and "_ensure_response_text(" in kaynak and "_failed_event(" in kaynak
    # tembel import: routes.reports GEMINI_MODEL_NAME olmadan yüklenebilmeli (CI)
    assert not any(satir.startswith("import analyzer") for satir in kaynak.splitlines())


def _sema_yuru(s, bulgular):
    if "additional_properties" in s:
        bulgular.append("additional_properties")
    for ad, alt in (s.get("properties") or {}).items():
        if not (alt.get("type") or alt.get("any_of")):
            bulgular.append(f"tipsiz:{ad}")
        _sema_yuru(alt, bulgular)
    if s.get("items"):
        _sema_yuru(s["items"], bulgular)
    return bulgular


def test_gemini_semasi_developer_api_uyumlu():
    """`RaporTanimi` (extra=forbid, deger: Any) Gemini şemasına GİREMEZ: SDK
    dönüşümü `additionalProperties` ve tipsiz alan üretir (Developer API
    desteklemez). Asistan şeması bu ikisinden arınık olmalı."""
    from google.genai import _transformers as t

    sahte_client = SimpleNamespace(vertexai=False)
    sema = t.t_schema(sahte_client, RaporAsistanCevabi).model_dump(exclude_none=True)
    assert _sema_yuru(sema, []) == []
    assert set(sema["properties"]) == {"cevap", "tanim", "eylem"}
    assert sema["properties"]["eylem"]["enum"] == ["onizle", "indir_xlsx", "indir_csv"]
    filtre = sema["properties"]["tanim"]["properties"]["filtreler"]["items"]["properties"]
    assert set(filtre) == {"alan", "op", "deger", "degerler"}
    assert filtre["deger"]["type"] == "STRING" and filtre["degerler"]["type"] == "ARRAY"

    # Karşı kanıt: RaporTanimi tabanlı şema aynı dönüştürücüde iki kusuru da taşır
    kusurlu = t.t_schema(sahte_client, RaporTanimi).model_dump(exclude_none=True)
    bulgular = _sema_yuru(kusurlu, [])
    assert "additional_properties" in bulgular and "tipsiz:deger" in bulgular


def test_env_example_ve_registry_anahtari():
    assert app_settings.RAPOR_ASISTANI_KEY == KEY
    assert KEY in app_settings.SETTINGS_REGISTRY
    assert hasattr(settings, "gemini_rapor_model")
