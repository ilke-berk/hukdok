"""G130 — Raporlama temeli: kayıt defteri (`services/rapor/registry.py`), rapor
tanımı şeması (`schemas_rapor.py`), sorgu motoru (`services/rapor/motor.py`),
`GET /api/reports/catalog` + `POST /api/reports/preview` (`routes/reports.py`).

Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.1-2.4 (G133 frontend'i buna
göre yazılır).

Düzen (G108 `env` reçetesi): süreç içi sqlite (StaticPool), `routes.reports.SessionLocal`
sqlite fabrikasına bağlanır; kimlik `get_current_user` override'ı + `ADMIN_EMAILS`
env'i (GERÇEK `require_admin` koşar — 403 testi sahte değildir). Veri: iki tenant +
legacy NULL + soft-silinmiş kart; taraflar, müvekkiller, belgeler, föyler.
"""
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from schemas_rapor import KOLON_MAX, ONIZLEME_SAYFA_BOYU_MAX, TIP_OPLARI, RaporDogrulamaHatasi, RaporTanimi
from services.rapor import motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
USER = "avukat@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"

CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
KAYNAKLAR = ("davalar", "muvekkiller", "belgeler", "foyler")
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

def _veri_yukle(db):
    c1 = models.Case(tracking_no="HA.G130.1", tenant_id=T1, status="DERDEST", subject="Malpraktis %100 kusur",
                     court="Bursa 1. Asliye Hukuk", opening_date=dt.date(2025, 3, 1), active=True,
                     maddi_tazminat=Decimal("1000.50"), responsible_lawyer_name="Av. Ali",
                     created_at=dt.datetime(2026, 1, 5, 10, 0))
    c2 = models.Case(tracking_no="HA.G130.2", tenant_id=None, status="KARAR", subject="Dava_konusu alt cizgi",
                     court="Ankara 2. Asliye Hukuk", opening_date=dt.date(2024, 6, 15), active=False,
                     maddi_tazminat=Decimal("250"), karar_tarihi=dt.date(2025, 1, 10),
                     responsible_lawyer_name="Av. Veli", created_at=dt.datetime(2026, 1, 6, 9, 0))
    c3 = models.Case(tracking_no="HA.G130.3", tenant_id=T2, status="DERDEST", subject="Baska tenant",
                     opening_date=dt.date(2025, 5, 5), created_at=dt.datetime(2026, 1, 5, 11, 0))
    c4 = models.Case(tracking_no="HA.G130.4", tenant_id=T1, status="DERDEST", subject="Silinmis kart",
                     deleted_at=SILINDI, deleted_by=ADMIN, created_at=dt.datetime(2026, 1, 5, 12, 0))
    db.add_all([c1, c2, c3, c4])
    db.flush()

    m1 = models.Client(name="Dr. Ayşe", tenant_id=T1, cari_kod="000001", category="Doktor")
    m2 = models.Client(name="Hastane A", tenant_id=None, cari_kod="000002", category="Kurum")
    m3 = models.Client(name="Baska Tenant Cari", tenant_id=T2, cari_kod="000003")
    m4 = models.Client(name="Silinmis Cari", tenant_id=T1, cari_kod="000004", deleted_at=SILINDI)
    db.add_all([m1, m2, m3, m4])
    db.flush()

    db.add_all([
        models.CaseParty(case_id=c1.id, client_id=m1.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
        models.CaseParty(case_id=c1.id, client_id=m2.id, name="Hastane A", role="Davalı", party_type="CLIENT"),
        models.CaseParty(case_id=c1.id, name="Hasta B", role="Davacı", party_type="COUNTER"),
        models.CaseParty(case_id=c2.id, client_id=m1.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
        models.CaseParty(case_id=c3.id, client_id=m1.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
        models.CaseParty(case_id=c4.id, client_id=m1.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
    ])

    def _belge(case_id, ad, **extra):
        extra.setdefault("link_mode", "LINKED")
        return models.CaseDocument(case_id=case_id, original_filename=ad, stored_filename=f"S_{ad}",
                                   belge_turu_adi="Dava Dilekçesi", **extra)

    db.add_all([
        _belge(c1.id, "d1.pdf", uploaded_at=dt.datetime(2026, 2, 1, 8, 0)),
        _belge(c1.id, "d2_silinmis.pdf", deleted_at=SILINDI),
        _belge(c3.id, "d3_baska_tenant.pdf"),
        _belge(c4.id, "d4_silinmis_kart.pdf"),
        _belge(None, "d5_davasiz.pdf", link_mode="UNLINKED"),
    ])
    db.add_all([
        models.CaseFoy(sistem_no="SSTMN-1", case_id=c1.id, tku_no="TKU-1", durum="DERDEST", muvekkil_tipi="Doktor"),
        models.CaseFoy(sistem_no="SSTMN-2", case_id=c1.id, tku_no="TKU-1", durum="MAHZEN", muvekkil_tipi="Sigorta"),
        models.CaseFoy(sistem_no="SSTMN-3", case_id=c3.id, tku_no="TKU-9"),
        models.CaseFoy(sistem_no="SSTMN-4", case_id=c4.id, tku_no="TKU-4"),
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

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(route_mod, "SessionLocal", maker)

    db = maker()
    try:
        _veri_yukle(db)
    finally:
        db.close()

    def _client(email=ADMIN, tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(db=maker, client=_client)
    engine.dispose()


def _tanim(kaynak="davalar", kolonlar=("tracking_no",), filtreler=(), siralama=()):
    return {"veri_kaynagi": kaynak, "kolonlar": list(kolonlar), "filtreler": list(filtreler),
            "siralama": list(siralama)}


def _onizle(client, tanim, **sayfa):
    return client.post(PREVIEW, json={"tanim": tanim, **sayfa})


def _degerler(cevap, anahtar):
    return [s[anahtar] for s in cevap.json()["satirlar"]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Katalog
# ═══════════════════════════════════════════════════════════════════════════

def test_katalog_sekli(env):
    """Kabul: plan §2.4 şekli (+ §4.2 alanları, G137); 4 kaynak sırayla;
    `limitler.onizleme_sayfa_boyu_max == 200`; her liste kolonun seçenekleri dolu;
    türetilmiş kolonlar sıralanamaz (filtre G137'den beri kolon bazında — test_g137)."""
    r = env.client().get(CATALOG)
    assert r.status_code == 200, r.text
    govde = r.json()
    assert set(govde) == {"veri_kaynaklari", "limitler"}
    assert govde["limitler"] == {"onizleme_sayfa_boyu_max": 200, "export_max_satir": 50000}
    assert [k["anahtar"] for k in govde["veri_kaynaklari"]] == list(KAYNAKLAR)

    turetilmis_sayisi = liste_sayisi = 0
    for kaynak in govde["veri_kaynaklari"]:
        assert set(kaynak) == {"anahtar", "etiket", "aciklama", "varsayilan_kolonlar", "kolonlar",
                               "hizli_filtreler", "kolon_setleri"}
        anahtarlar = [k["anahtar"] for k in kaynak["kolonlar"]]
        assert len(anahtarlar) == len(set(anahtarlar))
        assert "id" in anahtarlar
        assert set(kaynak["varsayilan_kolonlar"]) <= set(anahtarlar)
        assert kaynak["varsayilan_kolonlar"]
        for k in kaynak["kolonlar"]:
            # G141 (plan §5.2): + secilebilir / secenek_kaynagi / secenek_etiketleri
            assert set(k) == {"anahtar", "etiket", "tip", "grup", "kontrol", "filtrelenebilir", "siralanabilir",
                              "turetilmis", "secilebilir", "oplar", "secenekler", "secenek_kaynagi",
                              "secenek_etiketleri", "oneriler", "oneri_kesik"}
            assert k["tip"] in TIP_OPLARI
            assert k["etiket"]
            if k["tip"] == "liste":
                liste_sayisi += 1
                assert k["secenekler"], f"{kaynak['anahtar']}.{k['anahtar']} seçeneksiz liste"
                assert k["secenek_kaynagi"] == "sabit"
            elif k["secenek_kaynagi"] == "veri":
                assert isinstance(k["secenekler"], list)     # veriden liste, eşik altı (G141)
            else:
                assert k["secenekler"] is None and k["secenek_kaynagi"] is None
            if k["turetilmis"]:
                turetilmis_sayisi += 1
                assert k["siralanabilir"] is False
    assert turetilmis_sayisi >= 4 + 1 + 2 + 2
    assert liste_sayisi >= 10


def test_katalog_yasak_kolonlar_ve_asgari_kume(env):
    """Plan §2.3: `tenant_id`, `deleted_*`, `notes`, `ham_veri` katalogda YOK; davalar
    asgari kolon kümesi + 4 türetilmiş; belgeler/foyler dava kolonları; muvekkiller dava_sayisi."""
    govde = env.client().get(CATALOG).json()
    kaynaklar = {k["anahtar"]: {c["anahtar"] for c in k["kolonlar"]} for k in govde["veri_kaynaklari"]}
    for anahtarlar in kaynaklar.values():
        assert not (anahtarlar & registry.YASAK_KOLONLAR)
    asgari = {
        "id", "tracking_no", "esas_no", "status", "file_type", "sub_type", "service_type", "subject", "court",
        "judicial_unit", "opening_date", "acceptance_date", "responsible_lawyer_name", "uyap_lawyer_name",
        "bureau_type", "klasor_no_2", "hasar_dosya_no", "tku_no", "sistem_no", "case_stage", "dosya_son_durumu",
        "karar_tarihi", "karar_turu", "karar_lehine", "karar_no", "kesinlesme_tarihi", "maddi_tazminat",
        "manevi_tazminat", "hukmedilen_toplam", "dava_degeri", "para_birimi", "olay_turu", "hukumdeki_rol",
        "muvekkil_tipi", "hizmet_turu", "tibbi_surec", "tibbi_olay", "iddia_edilen_kusur", "active",
        "missing_required_bucket", "created_at", "updated_at",
        "muvekkil_adlari", "karsi_taraf_adlari", "foy_sayisi", "belge_sayisi",
    }
    assert asgari <= kaynaklar["davalar"]
    assert {"dava_tracking_no", "dava_subject"} <= kaynaklar["belgeler"]
    assert {"dava_tracking_no", "dava_subject"} <= kaynaklar["foyler"]
    assert "ham_veri" not in kaynaklar["foyler"]
    assert "dava_sayisi" in kaynaklar["muvekkiller"]


def test_katalog_secenekler_tablo_ve_distinct_katmani(env):
    """Seçenekler = sabit çekirdek + referans tablosu (aktif) + kolondaki DISTINCT değerler."""
    db = env.db()
    try:
        db.add(models.EventType(code="TEST-OLAY", name="Panelden Eklenen", active=True, sequence=9))
        db.add(models.EventType(code="PASIF", name="Pasif Olay", active=False, sequence=10))
        c = db.query(models.Case).filter_by(tracking_no="HA.G130.1").one()
        c.status = "OZEL_DURUM"
        db.commit()
    finally:
        db.close()
    govde = env.client().get(CATALOG).json()
    davalar = {k["anahtar"]: k for k in govde["veri_kaynaklari"][0]["kolonlar"]}
    olay = davalar["olay_turu"]["secenekler"]
    assert olay[:3] == ["Tıbbi Olay", "Belgeleme Olayı", "Tıbbi + Belgeleme"]
    assert "Panelden Eklenen" in olay and "Pasif Olay" not in olay
    durum = davalar["status"]["secenekler"]
    assert durum[:2] == ["DANIŞ", "DERDEST"] and "OZEL_DURUM" in durum
    assert len(durum) == len(set(durum))


def test_katalog_export_limiti_envden(env, monkeypatch):
    monkeypatch.setenv("RAPOR_MAX_SATIR", "1234")
    assert env.client().get(CATALOG).json()["limitler"]["export_max_satir"] == 1234


# ═══════════════════════════════════════════════════════════════════════════
# 2. Kapı: gerçek require_admin
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("metot,yol,kwargs", [
    ("get", CATALOG, {}),
    ("post", PREVIEW, {"json": {"tanim": _tanim()}}),
])
def test_admin_olmayan_403(env, metot, yol, kwargs):
    r = getattr(env.client(email=USER), metot)(yol, **kwargs)
    assert r.status_code == 403
    assert r.json()["detail"] == "Yönetici yetkisi gerekli"


def test_tenantsiz_token_403(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dependencies import get_current_user
    from routes import reports as route_mod

    app = FastAPI()
    app.include_router(route_mod.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": ADMIN}
    assert TestClient(app).get(CATALOG).status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 3. 422 — doğrulama, detail {"alan","sebep"}
# ═══════════════════════════════════════════════════════════════════════════

def _422(r, alan_parcasi: str):
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert set(detail) == {"alan", "sebep"}, detail
    assert alan_parcasi in detail["alan"], detail
    assert detail["sebep"]
    return detail


def test_422_bilinmeyen_kaynak(env):
    _422(_onizle(env.client(), _tanim(kaynak="users")), "veri_kaynagi")


def test_422_bilinmeyen_kolon(env):
    d = _422(_onizle(env.client(), _tanim(kolonlar=("tracking_no", "password"))), "kolonlar[1]")
    assert "password" in d["sebep"]


def test_422_izinsiz_op(env):
    """`contains` tarih tipinde izinli değil (plan §2.2)."""
    f = {"alan": "opening_date", "op": "contains", "deger": "2025"}
    d = _422(_onizle(env.client(), _tanim(filtreler=[f])), "filtreler[0]")
    assert "contains" in d["sebep"] and "tarih" in d["sebep"]


def test_422_tanimsiz_op(env):
    f = {"alan": "subject", "op": "regex", "deger": "x"}
    _422(_onizle(env.client(), _tanim(filtreler=[f])), "filtreler")


@pytest.mark.parametrize("filtre", [
    {"alan": "opening_date", "op": "eq", "deger": "01.03.2025"},        # ISO değil
    {"alan": "opening_date", "op": "between", "deger": ["2025-01-01"]},  # tek öğe
    {"alan": "maddi_tazminat", "op": "gte", "deger": "çok"},            # sayı değil
    {"alan": "maddi_tazminat", "op": "eq", "deger": True},              # bool sayı değildir
    {"alan": "active", "op": "eq", "deger": "true"},                    # bool değil
    {"alan": "subject", "op": "in", "deger": "tek"},                    # liste değil
    {"alan": "subject", "op": "in", "deger": []},                       # boş liste
    {"alan": "subject", "op": "eq", "deger": 5},                        # metin değil
    {"alan": "subject", "op": "eq"},                                    # değer yok
])
def test_422_yanlis_deger_bicimi(env, filtre):
    _422(_onizle(env.client(), _tanim(filtreler=[filtre])), "filtreler[0]")


def test_422_kolon_tavani_ve_tekrar(env):
    kolonlar = [f"k{i}" for i in range(KOLON_MAX + 1)]
    _422(_onizle(env.client(), _tanim(kolonlar=kolonlar)), "kolonlar")
    _422(_onizle(env.client(), _tanim(kolonlar=("tracking_no", "tracking_no"))), "kolonlar")
    _422(_onizle(env.client(), _tanim(kolonlar=())), "kolonlar")


def test_422_filtre_siralama_in_tavanlari(env):
    filtreler = [{"alan": "subject", "op": "not_null"}] * 21
    _422(_onizle(env.client(), _tanim(filtreler=filtreler)), "filtreler")
    siralama = [{"alan": "subject", "yon": "asc"}] * 4
    _422(_onizle(env.client(), _tanim(siralama=siralama)), "siralama")
    buyuk_in = [{"alan": "subject", "op": "in", "deger": [str(i) for i in range(201)]}]
    _422(_onizle(env.client(), _tanim(filtreler=buyuk_in)), "filtreler")


def test_422_turetilmis_filtrelenemez_siralanamaz(env):
    """`filtre_ifadesi` taşımayan türetilmiş kolon (foy_sayisi) filtrelenemez; türetilmiş
    hiçbir kolon sıralanamaz. (Taraf kolonları G137 ile filtrelenebilir oldu — test_g137.)"""
    f = {"alan": "foy_sayisi", "op": "gte", "deger": 1}
    d = _422(_onizle(env.client(), _tanim(filtreler=[f])), "filtreler[0]")
    assert "filtrelenemez" in d["sebep"]
    s = {"alan": "foy_sayisi", "yon": "desc"}
    d = _422(_onizle(env.client(), _tanim(siralama=[s])), "siralama[0]")
    assert "sıralanamaz" in d["sebep"]


def test_422_sayfa_boyu_tavani_ve_bilinmeyen_alan(env):
    _422(_onizle(env.client(), _tanim(), sayfa_boyu=ONIZLEME_SAYFA_BOYU_MAX + 1), "sayfa_boyu")
    _422(_onizle(env.client(), _tanim(), sayfa=0), "sayfa")
    r = env.client().post(PREVIEW, json={"tanim": {**_tanim(), "sql": "DROP TABLE cases"}})
    _422(r, "tanim")
    _422(env.client().post(PREVIEW, json={}), "tanim")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Filtreler — her op tipi için en az bir
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("filtre,beklenen", [
    ({"alan": "status", "op": "eq", "deger": "DERDEST"}, {"HA.G130.1"}),
    ({"alan": "status", "op": "ne", "deger": "DERDEST"}, {"HA.G130.2"}),
    ({"alan": "status", "op": "in", "deger": ["DERDEST", "KARAR"]}, {"HA.G130.1", "HA.G130.2"}),
    ({"alan": "subject", "op": "contains", "deger": "malpraktis"}, {"HA.G130.1"}),        # ILIKE
    ({"alan": "responsible_lawyer_name", "op": "eq", "deger": "Av. Veli"}, {"HA.G130.2"}),
    ({"alan": "karar_tarihi", "op": "is_null"}, {"HA.G130.1"}),
    ({"alan": "karar_tarihi", "op": "not_null"}, {"HA.G130.2"}),
    ({"alan": "opening_date", "op": "eq", "deger": "2025-03-01"}, {"HA.G130.1"}),
    ({"alan": "opening_date", "op": "gte", "deger": "2025-01-01"}, {"HA.G130.1"}),
    ({"alan": "opening_date", "op": "lte", "deger": "2024-12-31"}, {"HA.G130.2"}),
    ({"alan": "opening_date", "op": "between", "deger": ["2024-01-01", "2024-12-31"]}, {"HA.G130.2"}),
    ({"alan": "maddi_tazminat", "op": "gte", "deger": 1000}, {"HA.G130.1"}),
    ({"alan": "maddi_tazminat", "op": "lte", "deger": 250}, {"HA.G130.2"}),
    ({"alan": "maddi_tazminat", "op": "eq", "deger": 1000.5}, {"HA.G130.1"}),
    ({"alan": "maddi_tazminat", "op": "between", "deger": [0, 500]}, {"HA.G130.2"}),
    ({"alan": "id", "op": "gte", "deger": 1}, {"HA.G130.1", "HA.G130.2"}),
    ({"alan": "active", "op": "eq", "deger": True}, {"HA.G130.1"}),
    ({"alan": "active", "op": "eq", "deger": False}, {"HA.G130.2"}),
    ({"alan": "created_at", "op": "eq", "deger": "2026-01-05"}, {"HA.G130.1"}),        # DateTime gün aralığı
    ({"alan": "created_at", "op": "between", "deger": ["2026-01-06", "2026-01-07"]}, {"HA.G130.2"}),
    ({"alan": "created_at", "op": "lte", "deger": "2026-01-05"}, {"HA.G130.1"}),
])
def test_filtre_oplari(env, filtre, beklenen):
    r = _onizle(env.client(), _tanim(filtreler=[filtre]))
    assert r.status_code == 200, r.text
    assert set(_degerler(r, "tracking_no")) == beklenen


def test_ne_null_satiri_dahil_eder(env):
    """`ne`: alanı NULL olan satır da "eşit değil" sayılır (boş ≠ değer)."""
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "karar_tarihi", "op": "not_null"},
                                                {"alan": "court", "op": "ne", "deger": "Yok"}]))
    assert set(_degerler(r, "tracking_no")) == {"HA.G130.2"}
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "esas_no", "op": "ne", "deger": "2020/1"}]))
    assert set(_degerler(r, "tracking_no")) == {"HA.G130.1", "HA.G130.2"}


def test_coklu_filtre_and(env):
    filtreler = [{"alan": "status", "op": "in", "deger": ["DERDEST", "KARAR"]},
                 {"alan": "opening_date", "op": "gte", "deger": "2025-01-01"}]
    r = _onizle(env.client(), _tanim(filtreler=filtreler))
    assert _degerler(r, "tracking_no") == ["HA.G130.1"]


@pytest.mark.parametrize("deger,beklenen", [
    ("%100", {"HA.G130.1"}),          # yüzde literal — kaçışsız her satırı eşlerdi
    ("_konusu", {"HA.G130.2"}),       # alt çizgi literal
    ("a%", set()),                    # literal "a%" hiçbir konuda yok
    ("\\", set()),                    # ters bölü literal
    ("kusur", {"HA.G130.1"}),
])
def test_contains_kacisi(env, deger, beklenen):
    """Kabul: `contains` `%`/`_`/`\\` kaçışlı — istemci joker gönderemez."""
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "subject", "op": "contains", "deger": deger}]))
    assert r.status_code == 200, r.text
    assert set(_degerler(r, "tracking_no")) == beklenen


def test_istemci_stringi_sql_metnine_girmez():
    """Kabul (kod incelemesi ikizi): filtre değeri derlenmiş SQL METNİNDE değil, bağlı parametrede."""
    zehir = "x' OR 1=1 --"
    tanim = RaporTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                        filtreler=[{"alan": "subject", "op": "contains", "deger": zehir},
                                   {"alan": "status", "op": "in", "deger": [zehir]}])
    derlenmis = motor.sorgu_kur(tanim, T1).compile()
    assert zehir not in str(derlenmis)
    assert any(zehir in str(v) for v in derlenmis.params.values())


# ═══════════════════════════════════════════════════════════════════════════
# 5. Tenant + soft-delete — dört kaynak
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kaynak,kolon,beklenen", [
    ("davalar", "tracking_no", {"HA.G130.1", "HA.G130.2"}),
    ("muvekkiller", "name", {"Dr. Ayşe", "Hastane A"}),
    ("belgeler", "original_filename", {"d1.pdf"}),
    ("foyler", "sistem_no", {"SSTMN-1", "SSTMN-2"}),
])
def test_tenant_ve_soft_delete(env, kaynak, kolon, beklenen):
    """Kabul: başka tenant'ın kaydı ve `deleted_at` dolu kayıt listelenmez; NULL tenant listelenir."""
    r = _onizle(env.client(), _tanim(kaynak=kaynak, kolonlar=(kolon,)))
    assert r.status_code == 200, r.text
    assert set(_degerler(r, kolon)) == beklenen
    assert r.json()["toplam"] == len(beklenen)


def test_baska_tenant_kendi_kaydini_gorur(env):
    r = _onizle(env.client(tid=T2), _tanim())
    assert set(_degerler(r, "tracking_no")) == {"HA.G130.2", "HA.G130.3"}


def test_silinmis_kartin_foy_ve_belgesi_id_ile_de_gelmez(env):
    """Filtreyle silinmiş/başka tenant kartın id'si istense de kısıt kalkmaz."""
    db = env.db()
    try:
        c4 = db.query(models.Case).filter_by(tracking_no="HA.G130.4").one().id
    finally:
        db.close()
    for kaynak in ("belgeler", "foyler"):
        r = _onizle(env.client(), _tanim(kaynak=kaynak, kolonlar=("id",),
                                         filtreler=[{"alan": "case_id", "op": "eq", "deger": c4}]))
        assert r.json()["toplam"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. Türetilmiş kolonlar
# ═══════════════════════════════════════════════════════════════════════════

def test_turetilmis_kolonlar(env):
    kolonlar = ("tracking_no", "muvekkil_adlari", "karsi_taraf_adlari", "foy_sayisi", "belge_sayisi")
    r = _onizle(env.client(), _tanim(kolonlar=kolonlar, siralama=[{"alan": "tracking_no", "yon": "asc"}]))
    assert r.status_code == 200, r.text
    s1, s2 = r.json()["satirlar"]
    assert set(s1["muvekkil_adlari"].split(registry.AYRAC)) == {"Dr. Ayşe", "Hastane A"}
    assert s1["karsi_taraf_adlari"] == "Hasta B"
    assert s1["foy_sayisi"] == 2 and s1["belge_sayisi"] == 1          # silinmiş belge sayılmaz
    assert s2["muvekkil_adlari"] == "Dr. Ayşe" and s2["karsi_taraf_adlari"] is None
    assert s2["foy_sayisi"] == 0 and s2["belge_sayisi"] == 0


def test_muvekkil_dava_sayisi_silinmis_kart_haric(env):
    r = _onizle(env.client(), _tanim(kaynak="muvekkiller", kolonlar=("name", "dava_sayisi")))
    sayilar = {s["name"]: s["dava_sayisi"] for s in r.json()["satirlar"]}
    assert sayilar == {"Dr. Ayşe": 3, "Hastane A": 1}                   # c1, c2, c3 (c4 silinmiş)


def test_belge_ve_foy_dava_kolonlari(env):
    r = _onizle(env.client(), _tanim(kaynak="belgeler", kolonlar=("original_filename", "dava_tracking_no",
                                                                    "dava_subject", "uploaded_at")))
    [s] = r.json()["satirlar"]
    assert s["dava_tracking_no"] == "HA.G130.1" and s["dava_subject"] == "Malpraktis %100 kusur"
    assert s["uploaded_at"].startswith("2026-02-01T08:00:00")
    r = _onizle(env.client(), _tanim(kaynak="foyler", kolonlar=("sistem_no", "dava_tracking_no", "durum"),
                                     filtreler=[{"alan": "durum", "op": "eq", "deger": "MAHZEN"}]))
    assert r.json()["satirlar"] == [{"sistem_no": "SSTMN-2", "dava_tracking_no": "HA.G130.1", "durum": "MAHZEN"}]


# ═══════════════════════════════════════════════════════════════════════════
# 7. Sayfalama, sıralama, serileştirme, akış
# ═══════════════════════════════════════════════════════════════════════════

def test_sayfalama_ve_toplam(env):
    client = env.client()
    siralama = [{"alan": "opening_date", "yon": "desc"}]
    r1 = _onizle(client, _tanim(siralama=siralama), sayfa=1, sayfa_boyu=1)
    r2 = _onizle(client, _tanim(siralama=siralama), sayfa=2, sayfa_boyu=1)
    r3 = _onizle(client, _tanim(siralama=siralama), sayfa=3, sayfa_boyu=1)
    for r in (r1, r2, r3):
        assert r.status_code == 200 and r.json()["toplam"] == 2 and r.json()["sayfa_boyu"] == 1
    assert _degerler(r1, "tracking_no") == ["HA.G130.1"] and r1.json()["sayfa"] == 1
    assert _degerler(r2, "tracking_no") == ["HA.G130.2"] and r2.json()["sayfa"] == 2
    assert _degerler(r3, "tracking_no") == []
    varsayilan = _onizle(client, _tanim())
    assert varsayilan.json()["sayfa"] == 1 and varsayilan.json()["sayfa_boyu"] == 50


def test_siralama_yonu_ve_null_sonda(env):
    client = env.client()
    asc = _onizle(client, _tanim(siralama=[{"alan": "opening_date", "yon": "asc"}]))
    assert _degerler(asc, "tracking_no") == ["HA.G130.2", "HA.G130.1"]
    desc = _onizle(client, _tanim(siralama=[{"alan": "karar_tarihi", "yon": "desc"}]))
    assert _degerler(desc, "tracking_no") == ["HA.G130.2", "HA.G130.1"]   # NULL sonda


def test_cevap_sekli_ve_serilestirme(env):
    """Plan §2.4: `kolonlar` [{anahtar,etiket,tip}], tarih ISO, para JSON number, null boş."""
    kolonlar = ("tracking_no", "opening_date", "maddi_tazminat", "active", "karar_tarihi", "esas_no", "created_at")
    r = _onizle(env.client(), _tanim(kolonlar=kolonlar, siralama=[{"alan": "tracking_no", "yon": "asc"}]))
    govde = r.json()
    assert set(govde) == {"kolonlar", "satirlar", "toplam", "sayfa", "sayfa_boyu"}
    assert govde["kolonlar"][:3] == [
        {"anahtar": "tracking_no", "etiket": "Ofis Dosya No", "tip": "metin"},
        {"anahtar": "opening_date", "etiket": "Açılış Tarihi", "tip": "tarih"},
        {"anahtar": "maddi_tazminat", "etiket": "Maddi Tazminat", "tip": "para"},
    ]
    s1 = govde["satirlar"][0]
    assert s1 == {"tracking_no": "HA.G130.1", "opening_date": "2025-03-01", "maddi_tazminat": 1000.5,
                  "active": True, "karar_tarihi": None, "esas_no": None, "created_at": "2026-01-05T10:00:00"}
    assert isinstance(s1["maddi_tazminat"], float)


def test_satirlari_akit_iteratoru(env):
    """G131 export'un tüketeceği akış: sözlük iteratörü, kısıtlar ve sıralama aynı."""
    tanim = RaporTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no", "muvekkil_adlari"],
                        siralama=[{"alan": "tracking_no", "yon": "desc"}])
    db = env.db()
    try:
        satirlar = list(motor.satirlari_akit(db, tanim, T1, parca=1))
    finally:
        db.close()
    assert [s["tracking_no"] for s in satirlar] == ["HA.G130.2", "HA.G130.1"]
    assert satirlar[1]["muvekkil_adlari"] in ("Dr. Ayşe ; Hastane A", "Hastane A ; Dr. Ayşe")


def test_motor_dogrulama_hatasi_sinifi():
    with pytest.raises(RaporDogrulamaHatasi) as ex:
        motor.tanimi_dogrula(RaporTanimi(veri_kaynagi="davalar", kolonlar=["yok"]))
    assert ex.value.detay() == {"alan": "kolonlar[0]", "sebep": "katalogda olmayan kolon: yok"}


def test_registry_kendini_denetler():
    """Kayıt defteri yüklenirken yasak kolon / seçeneksiz liste / filtre ifadesiz filtrelenebilir
    türetilmiş reddedilir (G137: türetilmiş filtre kolon bazında)."""
    for kaynak in registry.KAYNAKLAR.values():
        for kolon in kaynak.kolonlar.values():
            if kolon.tip == "liste":
                assert kolon.secenekler or kolon.secenek_tablosu is not None
                assert registry.secenekleri_getir(kolon, None) == list(kolon.secenekler)
            assert kolon.tip in TIP_OPLARI
    assert registry.kaynak_bul("yok") is None
    assert set(registry.KAYNAKLAR) == set(KAYNAKLAR)
