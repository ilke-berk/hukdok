"""28.09 — Rapor raporunda çok değerli tıbbi alanlar (plan: tıbbi beşli seçilebilir liste).

Tıbbi Süreç · Tıbbi Olay · İddia Edilen Kusur · Hastada Oluşan Zarar · Uygulanan Yöntem hücrede
" ; " ayraçlı birden çok öğe taşır (G124, `services/multi_value.py`). Katalogda seçenekler havuz
tablosu (aktif) ∪ verideki öğeler, kart sayılı (`registry.coklu_deger_secenekleri`); motorda
`eq`/`ne`/`in` TAM öğe eşler (`motor._coklu_kosulu`) — "Cerrahi" "Cerrahi Uygulama"yı getirmez;
`contains` hücrede parça arar. Bağlı kaynaklarda (G166) aynı anlam: tekil bağ (föyler → dava.*)
düz kolon gibi, çoklu bağ (müvekkiller → dava.*) EXISTS atomu çok değerli koşulu alır.

Düzen `test_g166_rapor_bagli_kaynaklar.env` reçetesiyle aynı (sqlite StaticPool, gerçek `require_admin`).
"""
import datetime as dt
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from services.rapor import asistan, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
TIBBI = ("tibbi_surec", "tibbi_olay", "iddia_edilen_kusur", "hastada_olusan_zarar", "uygulanan_yontem")


def _veri_yukle(db):
    C = models.Case
    c1 = C(tracking_no="HA.CD.1", tenant_id=T1, status="DERDEST",
           tibbi_surec="Cerrahi Uygulama ; Doğum Yönetimi", tibbi_olay="Down Sendromu")
    c2 = C(tracking_no="HA.CD.2", tenant_id=None, status="DERDEST",
           tibbi_surec="Cerrahi", tibbi_olay="Omuz Distosisi ; down sendromu")      # küçük harf → aynı öğe
    c3 = C(tracking_no="HA.CD.3", tenant_id=T1, status="DERDEST", tibbi_surec=None, tibbi_olay="")
    c4 = C(tracking_no="HA.CD.4", tenant_id=T2, status="DERDEST", tibbi_surec="Cerrahi ; Yabancı Süreç")
    c5 = C(tracking_no="HA.CD.5", tenant_id=T1, status="DERDEST", tibbi_surec="Cerrahi ; Silinmiş Süreç",
           deleted_at=SILINDI, deleted_by=ADMIN)
    db.add_all([c1, c2, c3, c4, c5])
    db.flush()
    db.add_all([
        models.MedicalProcess(code="MP1", name="Cerrahi", active=True, sequence=1),
        models.MedicalProcess(code="MP2", name="Tanı Süreci", active=True, sequence=2),       # yalnız havuzda
        models.MedicalProcess(code="MP3", name="Pasif Süreç", active=False, sequence=3),      # pasif → yok
        models.MedicalEvent(code="ME1", name="Down Sendromu", active=True, sequence=1),
    ])
    a = models.Client(name="Dr. Ayse", tenant_id=T1)
    b = models.Client(name="Beta Hastanesi", tenant_id=T1)
    db.add_all([a, b])
    db.flush()
    P = models.CaseParty
    db.add_all([
        P(case_id=c1.id, client_id=a.id, name="Dr. Ayse", role="Davalı", party_type="CLIENT"),
        P(case_id=c2.id, client_id=b.id, name="Beta Hastanesi", role="Davalı", party_type="CLIENT"),
        P(case_id=c5.id, client_id=b.id, name="Beta Hastanesi", role="Davalı", party_type="CLIENT"),
    ])
    F = models.CaseFoy
    db.add_all([
        F(sistem_no="S1", case_id=c1.id, durum="DERDEST"),
        F(sistem_no="S2", case_id=c2.id, durum="DERDEST"),
        F(sistem_no="S3", case_id=c2.id, durum="DERDEST"),
    ])
    db.commit()


@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import reports as route_mod

    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    monkeypatch.delenv("RAPOR_MAX_SATIR", raising=False)
    route_mod.katalog_onbellegini_sifirla()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(route_mod, "SessionLocal", maker)
    db = maker()
    try:
        _veri_yukle(db)
    finally:
        db.close()

    def _client(tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": ADMIN, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(db=maker, client=_client, route=route_mod)
    route_mod.katalog_onbellegini_sifirla()
    engine.dispose()


def _kolonlar(client, kaynak):
    r = client.get(CATALOG)
    assert r.status_code == 200, r.text
    k = next(v for v in r.json()["veri_kaynaklari"] if v["anahtar"] == kaynak)
    return {c["anahtar"]: c for c in k["kolonlar"]}


def _takip_nolari(client, filtre, kaynak="davalar", kolon="tracking_no"):
    r = client.post(PREVIEW, json={"tanim": {"veri_kaynagi": kaynak, "kolonlar": [kolon], "filtreler": [filtre],
                                            "siralama": [{"alan": kolon, "yon": "asc"}]}})
    assert r.status_code == 200, r.text
    return [s[kolon] for s in r.json()["satirlar"]]


# ─── Katalog ────────────────────────────────────────────────────────────────

def test_tibbi_besli_katalogda_cok_degerli(env):
    davalar = _kolonlar(env.client(), "davalar")
    for anahtar in TIBBI:
        k = davalar[anahtar]
        assert k["coklu_deger"] is True and k["tip"] == "metin" and k["grup"] == "Tıbbi", anahtar
        assert "contains" in k["oplar"] and "in" in k["oplar"] and "eq" in k["oplar"]
    # tek değerli kolonlar işaretsiz
    assert davalar["subject"]["coklu_deger"] is False


def test_secenekler_havuz_ve_veri_ogeleri_sayili(env):
    """Havuz (aktif) ∪ verideki öğeler; sayı = öğeyi taşıyan kart (tenant + soft-delete kurallı);
    büyük/küçük harf farkı tek öğe (havuz yazımı); sıra sayı azalan, eşitlikte Türk alfabesi;
    öğe listesi varken kontrol çoklu seçim, `oneriler` yok."""
    davalar = _kolonlar(env.client(), "davalar")
    surec = davalar["tibbi_surec"]
    assert surec["secenekler"] == ["Cerrahi", "Cerrahi Uygulama", "Doğum Yönetimi", "Tanı Süreci"]
    assert surec["secenek_sayilari"] == {"Cerrahi": 1, "Cerrahi Uygulama": 1, "Doğum Yönetimi": 1, "Tanı Süreci": 0}
    assert surec["kontrol"] == "coklu_secim" and surec["secenek_kaynagi"] == "veri" and surec["oneriler"] is None
    olay = davalar["tibbi_olay"]
    assert olay["secenekler"] == ["Down Sendromu", "Omuz Distosisi"]
    assert olay["secenek_sayilari"] == {"Down Sendromu": 2, "Omuz Distosisi": 1}
    # hiç öğesi olmayan (boş havuz + boş veri) çok değerli kolon metin kutusunda kalır
    kusur = davalar["iddia_edilen_kusur"]
    assert kusur["secenekler"] is None and kusur["kontrol"] == "metin_icerir" and kusur["secenek_kaynagi"] is None
    # başka tenant'ın / silinmiş davanın öğesi yok
    assert "Yabancı Süreç" not in surec["secenekler"] and "Silinmiş Süreç" not in surec["secenekler"]
    assert "Pasif Süreç" not in surec["secenekler"]


def test_bagli_kaynaklarda_secenekler(env):
    """Tekil bağ (föyler → dava.*): föy satırı sayılır; çoklu bağ (müvekkiller → dava.*): hedefin DISTINCT
    hücrelerinden öğeler, sayı yok (None)."""
    client = env.client()
    foy = _kolonlar(client, "foyler")["dava.tibbi_surec"]
    assert foy["coklu_deger"] is True and foy["kontrol"] == "coklu_secim"
    assert foy["secenek_sayilari"] == {"Cerrahi": 2, "Cerrahi Uygulama": 1, "Doğum Yönetimi": 1, "Tanı Süreci": 0}
    muv = _kolonlar(client, "muvekkiller")["dava.tibbi_surec"]
    assert muv["coklu_deger"] is True and muv["kontrol"] == "coklu_secim" and muv["secenek_sayilari"] is None
    assert set(muv["secenekler"]) == {"Cerrahi", "Cerrahi Uygulama", "Doğum Yönetimi", "Tanı Süreci"}


# ─── Filtre anlamı ──────────────────────────────────────────────────────────

def test_eq_tam_oge_eslesir_parca_eslesmez(env):
    client = env.client()
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "eq", "deger": "Cerrahi"}) == ["HA.CD.2"]
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "eq", "deger": "Doğum Yönetimi"}) == ["HA.CD.1"]
    # büyük/küçük harf duyarsız, öğe hücrenin başında/ortasında/sonunda
    assert _takip_nolari(client, {"alan": "tibbi_olay", "op": "eq", "deger": "DOWN SENDROMU"}) == ["HA.CD.1", "HA.CD.2"]
    # contains parça arar (eski davranış korunur)
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "contains", "deger": "Cerrahi"}) == ["HA.CD.1", "HA.CD.2"]


def test_in_ne_ve_bos(env):
    client = env.client()
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "in", "deger": ["Cerrahi", "Doğum Yönetimi"]}) == \
        ["HA.CD.1", "HA.CD.2"]
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "in", "deger": ["Cerrahi", None]}) == \
        ["HA.CD.2", "HA.CD.3"]
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "in", "deger": [None]}) == ["HA.CD.3"]
    # ne: öğeyi taşımayan + boş hücre
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "ne", "deger": "Cerrahi"}) == ["HA.CD.1", "HA.CD.3"]
    assert _takip_nolari(client, {"alan": "tibbi_olay", "op": "is_null"}) == ["HA.CD.3"]


def test_joker_karakterler_kacisli(env):
    """`%`/`_` öğe içinde joker değildir (ILIKE kaçışı atomda)."""
    client = env.client()
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "eq", "deger": "Cerrah%"}) == []
    assert _takip_nolari(client, {"alan": "tibbi_surec", "op": "eq", "deger": "Cerrah_"}) == []


def test_bagli_kolonlarda_tam_oge(env):
    client = env.client()
    # tekil bağ: föyler → dava.tibbi_surec
    assert _takip_nolari(client, {"alan": "dava.tibbi_surec", "op": "eq", "deger": "Cerrahi"},
                         kaynak="foyler", kolon="sistem_no") == ["S2", "S3"]
    # çoklu bağ: müvekkiller → dava.* (EXISTS; silinmiş dava c5 sayılmaz)
    assert _takip_nolari(client, {"alan": "dava.tibbi_surec", "op": "eq", "deger": "Cerrahi"},
                         kaynak="muvekkiller", kolon="name") == ["Beta Hastanesi"]
    assert _takip_nolari(client, {"alan": "dava.tibbi_surec", "op": "in", "deger": ["Cerrahi Uygulama"]},
                         kaynak="muvekkiller", kolon="name") == ["Dr. Ayse"]


# ─── Asistan ────────────────────────────────────────────────────────────────

def test_asistan_cok_degerli_kolonu_sik_ogelerle_gorur(env):
    """Katalog metninde çok değerli şerhi + en sık öğeler (tam liste DEĞİL); prompt'a en fazla
    `COKLU_PROMPT_OGE_MAX` öğe girer."""
    katalog = env.route._katalogu_getir(T1)
    veri = asistan.veri_secenekleri_katalogdan(katalog)
    assert veri[("davalar", "tibbi_olay")] == ["Down Sendromu", "Omuz Distosisi"]
    satir = next(s for s in asistan.katalog_metni(veri).splitlines() if s.startswith("tibbi_olay · "))
    assert "ÇOK DEĞERLİ" in satir and "en sık 2 öğe (tam liste değil; burada yoksa contains): Down Sendromu|Omuz Distosisi" in satir

    uzun = {"veri_kaynaklari": [{"anahtar": "davalar", "kolonlar": [
        {"anahtar": "tibbi_olay", "secenek_kaynagi": "veri", "bag": None, "coklu_deger": True,
         "secenekler": [f"Öğe {i}" for i in range(500)]},
        {"anahtar": "court", "secenek_kaynagi": "veri", "bag": None, "secenekler": [f"M {i}" for i in range(50)]},
    ]}]}
    kesik = asistan.veri_secenekleri_katalogdan(uzun)
    assert len(kesik[("davalar", "tibbi_olay")]) == asistan.COKLU_PROMPT_OGE_MAX
    assert len(kesik[("davalar", "court")]) == 50                  # tek değerli liste kesilmez


# ─── Kayıt defteri denetimi ─────────────────────────────────────────────────

def test_denetim_cok_degerli_kurallari():
    K = registry.KAYNAKLAR["davalar"]
    kolon = K.kolonlar["tibbi_surec"]
    with pytest.raises(ValueError, match="çok değerli yalnız"):
        registry._kolonu_denetle(K, replace(K.kolonlar["opening_date"], coklu_deger=True))
    with pytest.raises(ValueError, match="havuz tablosu yok"):
        registry._kolonu_denetle(K, replace(kolon, secenek_tablosu=None))
