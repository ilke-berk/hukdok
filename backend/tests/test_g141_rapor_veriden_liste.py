"""G141 — Rapor kataloğu: veriden kapalı liste (eşik + sıklık sırası), `secenek_etiketleri`,
`in` listesinde `null` ("(boş)"), sanal `arama` kolonu + `secilebilir`, `HizliFiltre.sunum/etiket`,
müvekkil hızlı filtre şeridi, asistan "(boş)" çevirisi (plan §5, sözleşme §5.2 DONDU).

Düzen `test_g137_rapor_katalog_genisleme.env` reçetesi (sqlite StaticPool, gerçek `require_admin`);
veri bu görevin senaryolarına göre: il sıklıkları (Ankara 3 / İstanbul 2 / İzmir 1), il NULL ve "" kart,
silinmiş kart, başka tenant kart; davalarda mahkeme NULL kart ve taraf adları; belge/föy arama kolonları.
"""
import datetime as dt
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from config.settings import Settings, settings
from database import Base
from prompts import get_rapor_asistani_instruction
from schemas_rapor import AsistanTanimi, Filtre, RaporDogrulamaHatasi, RaporTanimi
from services.rapor import asistan, motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)

MUVEKKIL_SERIDI = [
    ("arama", "arama", None),
    ("category", "cipler", None),
    ("il", "varsayilan", None),
    ("specialty", "varsayilan", None),
    ("dava_sayisi", "var_yok", "Davası var"),
    ("email", "bos_anahtari", "E-postası yok"),
    ("mobile_phone", "bos_anahtari", "Cep telefonu yok"),
]
ARAMA_KOLONLARI = {
    "davalar": ("tracking_no", "esas_no", "subject", "court", "muvekkil_adlari", "karsi_taraf_adlari"),
    "muvekkiller": ("name", "cari_kod", "email", "phone", "mobile_phone"),
    "belgeler": ("original_filename", "dava_tracking_no", "ai_summary"),
    "foyler": ("sistem_no", "tku_no", "hasar_no", "dava_tracking_no"),
}


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

def _veri_yukle(db):
    M = models.Client
    db.add_all([
        M(name="Ankaralı Bir", tenant_id=T1, il="Ankara", cari_kod="CK-001", email="bir@ornek.tr",
          phone="0312 111", mobile_phone="0532 111", category="Doktor", specialty="Kardiyoloji",
          client_type="Individual"),
        M(name="Ankaralı İki", tenant_id=None, il="Ankara", cari_kod="CK-002", email=None, phone=None,
          mobile_phone="0532 222", category="Hasta", client_type="Corporate"),
        M(name="Ankaralı Üç", tenant_id=T1, il="Ankara", cari_kod="CK-003", email="uc@ornek.tr",
          mobile_phone=None, category="Doktor", specialty="Kardiyoloji", client_type="Individual"),
        M(name="İstanbullu Bir", tenant_id=T1, il="İstanbul", cari_kod="CK-004", email="dort@ornek.tr",
          phone="0212 444", category="Kurum", client_type="Corporate"),
        M(name="İstanbullu İki", tenant_id=T1, il="İstanbul", cari_kod="CK-005", specialty="Ortopedi",
          client_type="Gerçek Kişi"),
        M(name="İzmirli", tenant_id=T1, il="İzmir", cari_kod="CK-006", email="alti@ornek.tr"),
        M(name="İlsiz Kart", tenant_id=T1, il=None, cari_kod="CK-007"),
        M(name="Boş İlli Kart", tenant_id=T1, il="", cari_kod="CK-008"),
        M(name="Silinmiş Kart", tenant_id=T1, il="Silinmiş İl", cari_kod="CK-009", deleted_at=SILINDI),
        M(name="Yabancı Kart", tenant_id=T2, il="Yabancı İl", cari_kod="CK-010", email="yab@ornek.tr"),
    ])
    c1 = models.Case(tracking_no="HA.G141.1", tenant_id=T1, status="DERDEST", subject="Kalp ameliyatı kusuru",
                     court="Ankara 1. Asliye Hukuk", esas_no="2025/100")
    c2 = models.Case(tracking_no="HA.G141.2", tenant_id=T1, status="DERDEST", subject="Ortopedi",
                     court="Bursa 2. Asliye Hukuk", esas_no="2025/200")
    c3 = models.Case(tracking_no="HA.G141.3", tenant_id=None, status="KARAR", subject="Mahkemesiz kart",
                     court=None)
    c4 = models.Case(tracking_no="HA.G141.4", tenant_id=T1, status="DERDEST", subject="Tarafsız", court="")
    c5 = models.Case(tracking_no="HA.G141.5", tenant_id=T2, status="DERDEST", subject="Yabancı Kalp", court="Yabancı")
    c6 = models.Case(tracking_no="HA.G141.6", tenant_id=T1, status="DERDEST", subject="Silinmiş Kalp",
                     court="Ankara 1. Asliye Hukuk", deleted_at=SILINDI, deleted_by=ADMIN)
    db.add_all([c1, c2, c3, c4, c5, c6])
    db.flush()
    P = models.CaseParty
    db.add_all([
        P(case_id=c1.id, name="Ankaralı Bir", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, name="Hasta Şikayetçi", role="Davacı", party_type="COUNTER"),
        P(case_id=c2.id, name="İstanbullu Bir", role="Davalı", party_type="CLIENT"),
        P(case_id=c2.id, name="Ankaralı Üç", role="Davacı", party_type="COUNTER"),   # karşı taraf, kategori sayılmaz
        P(case_id=c3.id, name="İlsiz Kart", role="Davalı", party_type="CLIENT"),      # kategorisiz kart
    ])
    db.add_all([
        models.CaseDocument(case_id=c1.id, original_filename="bilirkisi_raporu.pdf", stored_filename="s1",
                            ai_summary="Kusur oranı yüzde elli"),
        models.CaseDocument(case_id=c2.id, original_filename="dilekce.pdf", stored_filename="s2", ai_summary=None),
        models.CaseFoy(sistem_no="SSTMN-41", case_id=c1.id, tku_no="TKU-41", hasar_no="HSR-41"),
        models.CaseFoy(sistem_no="SSTMN-42", case_id=c2.id, tku_no="TKU-42", hasar_no=None),
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

    def _client(email=ADMIN, tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    def _esik(deger):
        monkeypatch.setattr(settings, "rapor_secenek_esigi", deger)
        route_mod.katalog_onbellegini_sifirla()

    yield SimpleNamespace(db=maker, client=_client, route=route_mod, esik=_esik)
    route_mod.katalog_onbellegini_sifirla()
    engine.dispose()


def _tanim(kaynak="muvekkiller", kolonlar=("name",), filtreler=(), siralama=()):
    return {"veri_kaynagi": kaynak, "kolonlar": list(kolonlar), "filtreler": list(filtreler),
            "siralama": list(siralama)}


def _onizle(client, tanim, **sayfa):
    return client.post(PREVIEW, json={"tanim": tanim, **sayfa})


def _adlar(cevap, anahtar="name"):
    assert cevap.status_code == 200, cevap.text
    return {s[anahtar] for s in cevap.json()["satirlar"]}


def _katalog(client):
    r = client.get(CATALOG)
    assert r.status_code == 200, r.text
    return {k["anahtar"]: k for k in r.json()["veri_kaynaklari"]}


def _kolonlar(kaynak):
    return {k["anahtar"]: k for k in kaynak["kolonlar"]}


def _422(r, alan_parcasi):
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert set(detail) == {"alan", "sebep"}, detail
    assert alan_parcasi in detail["alan"], detail
    return detail


# ═══════════════════════════════════════════════════════════════════════════
# 1. Veriden kapalı liste: eşik altı çoklu seçim (sıklık sırası, tenant/soft-delete), eşik üstü içerir
# ═══════════════════════════════════════════════════════════════════════════

def test_il_veriden_coklu_secim_siklik_sirasi(env):
    """Kabul: `il` katalogda `kontrol="coklu_secim"`, `secenekler` sıklığa göre azalan (Ankara 3 /
    İstanbul 2 / İzmir 1), NULL ve "" hariç, silinmiş kart ve başka tenant hariç, legacy NULL tenant dahil;
    `secenek_kaynagi="veri"`, `tip` metin KALIR, öneri katmanı koşmaz."""
    il = _kolonlar(_katalog(env.client())["muvekkiller"])["il"]
    assert il["tip"] == "metin" and il["kontrol"] == "coklu_secim"
    assert il["secenekler"] == ["Ankara", "İstanbul", "İzmir"]
    assert il["secenek_kaynagi"] == "veri" and il["oneriler"] is None and il["oneri_kesik"] is False
    assert il["oplar"] == ["eq", "ne", "contains", "in", "is_null", "not_null"]    # op tablosu değişmedi
    # başka tenant: kendi + legacy
    il2 = _kolonlar(_katalog(env.client(tid=T2))["muvekkiller"])["il"]
    assert il2["secenekler"] == ["Ankara", "Yabancı İl"]                            # Ankaralı İki (NULL tenant)


def test_siklik_esitliginde_ad_sirasi_ve_dava_kaynagi(env):
    """Eşit sıklıkta ad sırası; davalar `court`: NULL/"" hariç, silinmiş dava (c6) sayılmaz →
    Ankara 1 (c1) ve Bursa 1 (c2) eşit → ad sırası."""
    court = _kolonlar(_katalog(env.client())["davalar"])["court"]
    assert court["secenekler"] == ["Ankara 1. Asliye Hukuk", "Bursa 2. Asliye Hukuk"]
    assert court["kontrol"] == "coklu_secim" and court["secenek_kaynagi"] == "veri"


def test_esik_ustu_metin_icerir_ve_oneriler(env):
    """Kabul (iki yön): eşik 2 → `il` 3 DISTINCT eşiği aşar → `metin_icerir` + G137 önerileri (ad sırası),
    `secenekler=None`, `secenek_kaynagi=None`; eşik 3 → tam sınır → yine `coklu_secim` (≤ eşik)."""
    env.esik(2)
    il = _kolonlar(_katalog(env.client())["muvekkiller"])["il"]
    assert il["kontrol"] == "metin_icerir" and il["secenekler"] is None and il["secenek_kaynagi"] is None
    assert il["oneriler"] == ["Ankara", "İstanbul", "İzmir"] and il["oneri_kesik"] is False
    env.esik(3)
    il = _kolonlar(_katalog(env.client())["muvekkiller"])["il"]
    assert il["kontrol"] == "coklu_secim" and il["secenekler"] == ["Ankara", "İstanbul", "İzmir"]
    # eşik 0: hiçbir veriden liste açılmaz — tüm işaretli kolonlar öneriye düşer
    env.esik(0)
    kolonlar = _kolonlar(_katalog(env.client())["muvekkiller"])
    assert kolonlar["il"]["kontrol"] == "metin_icerir" and kolonlar["specialty"]["kontrol"] == "metin_icerir"


def test_veriden_liste_isaretleri_plan_listesi(env):
    """Plan §5.2 işaret listesi: Müvekkiller il/specialty, Davalar court/judicial_unit/responsible_lawyer_name/
    uyap_lawyer_name/sub_type, Belgeler uploaded_by/belge_turu_adi; sabit listeler `secenek_kaynagi="sabit"`
    (karar_turu/case_stage/dosya_son_durumu/muvekkil_tipi zaten liste — coklu_secim)."""
    beklenen = {
        "davalar": {"court", "judicial_unit", "responsible_lawyer_name", "uyap_lawyer_name", "sub_type"},
        "muvekkiller": {"il", "specialty"},
        "belgeler": {"uploaded_by", "belge_turu_adi"},
        "foyler": set(),
    }
    for anahtar, kaynak in registry.KAYNAKLAR.items():
        assert {a for a, k in kaynak.kolonlar.items() if k.veriden_liste} == beklenen[anahtar], anahtar
        for k in kaynak.kolonlar.values():
            if k.veriden_liste:
                assert k.tip == "metin" and k.onerili and not k.turetilmis
    kaynaklar = _katalog(env.client())
    davalar = _kolonlar(kaynaklar["davalar"])
    for anahtar in ("karar_turu", "case_stage", "dosya_son_durumu", "status"):
        assert davalar[anahtar]["secenek_kaynagi"] == "sabit" and davalar[anahtar]["kontrol"] == "coklu_secim"
    assert _kolonlar(kaynaklar["foyler"])["muvekkil_tipi"]["secenek_kaynagi"] == "sabit"
    # işaretsiz metin: seçenek yok, kaynak yok
    assert davalar["subject"]["secenekler"] is None and davalar["subject"]["secenek_kaynagi"] is None


def test_veriden_secenekleri_getir_db_yokken_ve_isaretsiz_kolonda_none(env):
    M = registry.MUVEKKILLER
    assert registry.veriden_secenekleri_getir(M, M.kolonlar["il"], None, T1) is None
    with env.db() as db:
        assert registry.veriden_secenekleri_getir(M, M.kolonlar["name"], db, T1) is None
        assert registry.veriden_secenekleri_getir(M, M.kolonlar["il"], db, T1) == ["Ankara", "İstanbul", "İzmir"]


def test_rapor_secenek_esigi_env(monkeypatch):
    """`RAPOR_SECENEK_ESIGI` env → `settings.rapor_secenek_esigi`; varsayılan 100; bozuk değer varsayılana düşer."""
    monkeypatch.delenv("RAPOR_SECENEK_ESIGI", raising=False)
    assert Settings().rapor_secenek_esigi == 100
    monkeypatch.setenv("RAPOR_SECENEK_ESIGI", "7")
    assert Settings().rapor_secenek_esigi == 7
    monkeypatch.setenv("RAPOR_SECENEK_ESIGI", "çok")
    assert Settings().rapor_secenek_esigi == 100


# ═══════════════════════════════════════════════════════════════════════════
# 2. Seçenek etiketleri
# ═══════════════════════════════════════════════════════════════════════════

def test_client_type_secenek_etiketleri_ve_ham_filtre(env):
    """Kabul: `client_type` üç etiket (Individual/Corporate/Gerçek Kişi), `secenek_kaynagi="sabit"`,
    seçeneklerde DISTINCT "Gerçek Kişi" de var; filtre HAM kodla çalışır; başka kolonda etiket yok."""
    kaynaklar = _katalog(env.client())
    muv = _kolonlar(kaynaklar["muvekkiller"])
    ct = muv["client_type"]
    assert ct["secenek_etiketleri"] == {"Individual": "Gerçek kişi", "Corporate": "Tüzel kişi",
                                        "Gerçek Kişi": "Gerçek kişi (eski yazım)"}
    assert ct["secenek_kaynagi"] == "sabit" and ct["kontrol"] == "coklu_secim"
    assert ct["secenekler"][:2] == ["Individual", "Corporate"] and "Gerçek Kişi" in ct["secenekler"]
    assert set(ct["secenek_etiketleri"]) <= set(ct["secenekler"])
    for anahtar, kaynak in kaynaklar.items():
        for k in kaynak["kolonlar"]:
            if not (anahtar == "muvekkiller" and k["anahtar"] == "client_type"):
                assert k["secenek_etiketleri"] is None, (anahtar, k["anahtar"])
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "client_type", "op": "eq", "deger": "Corporate"}]))
    assert _adlar(r) == {"Ankaralı İki", "İstanbullu Bir"}
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "client_type", "op": "in", "deger": ["Gerçek Kişi"]}]))
    assert _adlar(r) == {"İstanbullu İki"}
    # etiketle filtre → eşleşme yok (etiket yalnız gösterim)
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "client_type", "op": "eq", "deger": "Tüzel kişi"}]))
    assert _adlar(r) == set()


# ═══════════════════════════════════════════════════════════════════════════
# 3. `in` listesinde null
# ═══════════════════════════════════════════════════════════════════════════

def test_in_null_il_ankara_veya_bos(env):
    """Kabul: `{"alan":"il","op":"in","deger":["Ankara",null]}` Ankara VEYA il NULL kartları döner
    ("" NULL değildir, gelmez); yalnız `[null]` = is_null; null'suz liste eski davranış."""
    client = env.client()
    r = _onizle(client, _tanim(filtreler=[{"alan": "il", "op": "in", "deger": ["Ankara", None]}]))
    assert _adlar(r) == {"Ankaralı Bir", "Ankaralı İki", "Ankaralı Üç", "İlsiz Kart"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "il", "op": "in", "deger": [None]}]))
    assert _adlar(r) == {"İlsiz Kart"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "il", "op": "in", "deger": ["İzmir", "İstanbul"]}]))
    assert _adlar(r) == {"İzmirli", "İstanbullu Bir", "İstanbullu İki"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "il", "op": "is_null"}]))
    assert _adlar(r) == {"İlsiz Kart"}


def test_in_null_davalar_court_ve_turetilmis_muvekkil_kategorisi(env):
    """Davalar `court in [Ankara 1, null]`: c1 + c3 (NULL), c4 ("" değil). Türetilmiş `muvekkil_kategorisi
    in ["Doktor", null]`: Doktor kartlı taraf (c1) VEYA kategorili taraf yok (c3 kategorisiz kart, c4 tarafsız,
    c2 Kurum → gelmez); yalnız `[null]` = is_null."""
    client = env.client()
    r = _onizle(client, _tanim("davalar", ("tracking_no",),
                               [{"alan": "court", "op": "in", "deger": ["Ankara 1. Asliye Hukuk", None]}]))
    assert _adlar(r, "tracking_no") == {"HA.G141.1", "HA.G141.3"}
    r = _onizle(client, _tanim("davalar", ("tracking_no",),
                               [{"alan": "muvekkil_kategorisi", "op": "in", "deger": ["Doktor", None]}]))
    assert _adlar(r, "tracking_no") == {"HA.G141.1", "HA.G141.3", "HA.G141.4"}
    r = _onizle(client, _tanim("davalar", ("tracking_no",),
                               [{"alan": "muvekkil_kategorisi", "op": "in", "deger": [None]}]))
    assert _adlar(r, "tracking_no") == {"HA.G141.3", "HA.G141.4"}
    r = _onizle(client, _tanim("davalar", ("tracking_no",),
                               [{"alan": "muvekkil_kategorisi", "op": "in", "deger": ["Doktor", "Kurum"]}]))
    assert _adlar(r, "tracking_no") == {"HA.G141.1", "HA.G141.2"}


@pytest.mark.parametrize("filtre,alan_parcasi", [
    ({"alan": "il", "op": "eq", "deger": None}, "filtreler[0]"),                        # değer gerekli
    ({"alan": "il", "op": "contains", "deger": None}, "filtreler[0]"),
    ({"alan": "il", "op": "eq", "deger": [None]}, "filtreler"),                          # Pydantic: null yalnız in
    ({"alan": "vekaletname_tarihi", "op": "between", "deger": [None, "2025-01-01"]}, "filtreler"),
    ({"alan": "dava_sayisi", "op": "gte", "deger": None}, "filtreler[0]"),
], ids=["eq-null", "contains-null", "eq-liste-null", "between-null", "gte-null"])
def test_422_null_baska_opta(env, filtre, alan_parcasi):
    d = _422(_onizle(env.client(), _tanim(filtreler=[filtre])), alan_parcasi)
    assert "null yalnız 'in' listesinde" in d["sebep"], d


def test_filtre_semasi_in_null_kabul_baska_op_ret():
    assert Filtre(alan="il", op="in", deger=["Ankara", None]).deger == ["Ankara", None]
    with pytest.raises(ValueError, match="null yalnız 'in' listesinde"):
        Filtre(alan="opening_date", op="between", deger=[None, "2025-01-01"])
    # motor: null öğesi tip denetimini atlar, IN OR IS NULL derlenir
    tanim = RaporTanimi(veri_kaynagi="muvekkiller", kolonlar=["name"],
                        filtreler=[{"alan": "il", "op": "in", "deger": ["Ankara", None]}])
    sql = str(motor.sorgu_kur(tanim, T1).compile()).upper()
    assert " IN (" in sql and "IS NULL" in sql
    sadece = RaporTanimi(veri_kaynagi="muvekkiller", kolonlar=["name"],
                         filtreler=[{"alan": "il", "op": "in", "deger": [None]}])
    sql = str(motor.sorgu_kur(sadece, T1).compile()).upper()
    assert "IS NULL" in sql and "IL IN (" not in sql


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sanal `arama` kolonu
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("deger,beklenen", [
    ("ankaralı bir", {"Ankaralı Bir"}),           # name, büyük/küçük duyarsız
    ("CK-004", {"İstanbullu Bir"}),               # cari_kod
    ("uc@ornek", {"Ankaralı Üç"}),                # email
    ("0212", {"İstanbullu Bir"}),                 # phone
    ("0532 222", {"Ankaralı İki"}),               # mobile_phone
    ("ornek.tr", {"Ankaralı Bir", "Ankaralı Üç", "İstanbullu Bir", "İzmirli"}),   # silinmiş/yabancı yok
    ("Yabancı", set()),                            # başka tenant
    ("Silinmiş", set()),                           # soft-delete
    ("%", set()),                                  # joker kaçışlı — literal '%' hiçbir alanda yok
])
def test_arama_muvekkil_bes_kolonda_contains(env, deger, beklenen):
    """Kabul: `arama contains` beş müvekkil kolonunun HERHANGİ birinde bulur; tenant + soft-delete kurallı;
    ILIKE kaçışı motorun atom koşulundan."""
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "arama", "op": "contains", "deger": deger}]))
    assert _adlar(r) == beklenen


def test_arama_davalar_taraf_exists_belgeler_foyler(env):
    client = env.client()

    def dava(deger):
        return _adlar(_onizle(client, _tanim("davalar", ("tracking_no",),
                                             [{"alan": "arama", "op": "contains", "deger": deger}])), "tracking_no")

    assert dava("G141.2") == {"HA.G141.2"}                          # tracking_no
    assert dava("2025/100") == {"HA.G141.1"}                        # esas_no
    assert dava("kalp") == {"HA.G141.1"}                            # subject; yabancı (c5) ve silinmiş (c6) yok
    assert dava("Bursa") == {"HA.G141.2"}                           # court
    assert dava("Ankaralı Bir") == {"HA.G141.1"}                    # müvekkil adı (EXISTS CLIENT)
    assert dava("Şikayetçi") == {"HA.G141.1"}                       # karşı taraf adı (EXISTS COUNTER)
    assert dava("Ankaralı Üç") == {"HA.G141.2"}                     # karşı taraf olarak geçer
    belge = _onizle(client, _tanim("belgeler", ("original_filename",),
                                   [{"alan": "arama", "op": "contains", "deger": "yüzde"}]))
    assert _adlar(belge, "original_filename") == {"bilirkisi_raporu.pdf"}         # ai_summary
    belge = _onizle(client, _tanim("belgeler", ("original_filename",),
                                   [{"alan": "arama", "op": "contains", "deger": "G141.2"}]))
    assert _adlar(belge, "original_filename") == {"dilekce.pdf"}                  # dava ofis no
    foy = _onizle(client, _tanim("foyler", ("sistem_no",), [{"alan": "arama", "op": "contains", "deger": "HSR-41"}]))
    assert _adlar(foy, "sistem_no") == {"SSTMN-41"}                                # hasar_no
    foy = _onizle(client, _tanim("foyler", ("sistem_no",), [{"alan": "arama", "op": "contains", "deger": "G141.2"}]))
    assert _adlar(foy, "sistem_no") == {"SSTMN-42"}                                # dava ofis no


def test_arama_kolon_listesinde_ve_siralamada_422_yalniz_contains(env):
    client = env.client()
    d = _422(_onizle(client, _tanim(kolonlar=("name", "arama"))), "kolonlar[1]")
    assert "yalnız filtre" in d["sebep"]
    d = _422(_onizle(client, _tanim(siralama=[{"alan": "arama", "yon": "asc"}])), "siralama[0]")
    assert "yalnız filtre" in d["sebep"]
    d = _422(_onizle(client, _tanim(filtreler=[{"alan": "arama", "op": "eq", "deger": "x"}])), "filtreler[0]")
    assert "izinli değil" in d["sebep"]
    d = _422(_onizle(client, _tanim(filtreler=[{"alan": "arama", "op": "is_null"}])), "filtreler[0]")
    assert "izinli değil" in d["sebep"]
    with pytest.raises(RaporDogrulamaHatasi) as ex:
        motor.tanimi_dogrula(RaporTanimi(veri_kaynagi="davalar", kolonlar=["arama"]))
    assert ex.value.alan == "kolonlar[0]"


def test_arama_katalogda_secilebilir_false_setlerde_ve_varsayilanda_yok(env):
    """Kabul: her kaynakta `arama` katalogda `secilebilir=false`, grup "Arama", filtrelenebilir, sıralanamaz,
    türetilmiş, `oplar=["contains"]`; kolon setlerinde ve varsayılan kolonlarda YOK; diğer kolonlar seçilebilir."""
    kaynaklar = _katalog(env.client())
    for anahtar, kaynak in kaynaklar.items():
        kolonlar = _kolonlar(kaynak)
        a = kolonlar["arama"]
        assert a["secilebilir"] is False and a["grup"] == "Arama" and a["etiket"] == "Ara" and a["tip"] == "metin"
        assert a["filtrelenebilir"] and not a["siralanabilir"] and a["turetilmis"]
        assert a["oplar"] == ["contains"] and a["kontrol"] == "metin_icerir"
        assert a["secenekler"] is None and a["oneriler"] is None
        assert "arama" not in kaynak["varsayilan_kolonlar"]
        for ks in kaynak["kolon_setleri"]:
            assert "arama" not in ks["kolonlar"], (anahtar, ks["ad"])
        assert [k["anahtar"] for k in kaynak["kolonlar"] if not k["secilebilir"]] == ["arama"]
        assert kaynak["kolonlar"][0]["anahtar"] == "arama"
    # kayıt defteri: arama kolonu plan §5.2 kolon listelerini tarar (kaynak kodu şahit)
    for anahtar, ifadeler in ARAMA_KOLONLARI.items():
        assert registry.KAYNAKLAR[anahtar].kolonlar["arama"].filtre_ifadesi is not None
        assert ifadeler   # plan listesi boş değil; davranış test_arama_* ile doğrulandı


# ═══════════════════════════════════════════════════════════════════════════
# 5. Hızlı filtre sunumu + denetim
# ═══════════════════════════════════════════════════════════════════════════

def test_muvekkil_hizli_filtreleri_plan_sirasi_ve_sunum(env):
    """Kabul: Müvekkiller `hizli_filtreler` plan §5.2 sırası ve `sunum`/`etiket` değerleriyle birebir;
    Davalar/Belgeler/Föyler başında `arama(arama)`, kalanı `varsayilan` etiketsiz."""
    kaynaklar = _katalog(env.client())
    muv = kaynaklar["muvekkiller"]["hizli_filtreler"]
    assert [(hf["alan"], hf["sunum"], hf["etiket"]) for hf in muv] == MUVEKKIL_SERIDI
    assert all(hf["alternatifler"] == [] for hf in muv)
    for anahtar in ("davalar", "belgeler", "foyler"):
        hfs = kaynaklar[anahtar]["hizli_filtreler"]
        assert hfs[0] == {"alan": "arama", "alternatifler": [], "sunum": "arama", "etiket": None}
        assert all(hf["sunum"] == "varsayilan" and hf["etiket"] is None for hf in hfs[1:]), anahtar
    # şeritten çıkanlar (plan §5.1 madde 7): "+ Başka alan"dan ulaşılır, katalogda filtrelenebilir kalır
    kolonlar = _kolonlar(kaynaklar["muvekkiller"])
    for anahtar in ("client_type", "contact_type", "vekalet_no"):
        assert anahtar not in {hf["alan"] for hf in muv} and kolonlar[anahtar]["filtrelenebilir"]


@pytest.mark.parametrize("hf,eslesme", [
    (registry.HizliFiltre("il", sunum="arama"), "'arama' sunumu"),
    (registry.HizliFiltre("arama"), "'arama' sunumu"),                       # arama kolonu başka sunumla
    (registry.HizliFiltre("name", sunum="cipler"), "'cipler' sunumu"),
    (registry.HizliFiltre("il", sunum="var_yok"), "'var_yok' sunumu"),
    (registry.HizliFiltre("il", etiket="İl"), "etiket yalnız"),
    (registry.HizliFiltre("il", sunum="yok"), "tanınmayan sunum"),
    (registry.HizliFiltre("il", alternatifler=("name",)), "alternatifler yalnız tarih"),
], ids=["arama-il", "arama-varsayilan", "cipler-metin", "var_yok-metin", "etiket-varsayilan",
        "sunum-bilinmez", "alternatif-metin"])
def test_hizli_filtre_denetimi_hatali_sunumu_reddeder(hf, eslesme):
    with pytest.raises(ValueError, match=eslesme):
        registry._hizli_filtreyi_denetle(registry.MUVEKKILLER, hf)


def test_hizli_filtre_bos_anahtari_is_null_izinsiz_kolonda_reddedilir():
    """`bos_anahtari` `is_null` alan kolon ister: op alt kümesi `is_null`suz kolonda (sentetik) ValueError."""
    M = registry.MUVEKKILLER
    daraltilmis = replace(M, kolonlar={**M.kolonlar, "il": replace(M.kolonlar["il"], izinli_oplar=("eq", "in"))})
    with pytest.raises(ValueError, match="'bos_anahtari' sunumu"):
        registry._hizli_filtreyi_denetle(daraltilmis, registry.HizliFiltre("il", sunum="bos_anahtari"))
    registry._hizli_filtreyi_denetle(M, registry.HizliFiltre("il", sunum="bos_anahtari"))


def test_hizli_filtre_denetimi_gecerli_sunumlar():
    M = registry.MUVEKKILLER
    for hf in (registry.HizliFiltre("il", sunum="cipler"), registry.HizliFiltre("category", sunum="cipler"),
               registry.HizliFiltre("dava_sayisi", sunum="var_yok", etiket="Davası var"),
               registry.HizliFiltre("il", sunum="bos_anahtari", etiket="İli yok"),
               registry.HizliFiltre("vekaletname_tarihi", alternatifler=("gecerlilik_tarihi",))):
        registry._hizli_filtreyi_denetle(M, hf)
    assert registry.SUNUMLAR == ("varsayilan", "arama", "cipler", "var_yok", "bos_anahtari")


def test_kolon_denetimi_g141_kurallari():
    """`_kolonu_denetle`: veriden liste yalnız düz önerili metin; etiket yalnız seçenekli kolonda; seçilemeyen
    kolon türetilmiş+filtrelenebilir ve 'Arama' grubunda; 'Arama' grubu yalnız seçilemeyen kolon için."""
    M = registry.MUVEKKILLER
    with pytest.raises(ValueError, match="veriden liste"):
        registry._kolonu_denetle(M, replace(M.kolonlar["category"], veriden_liste=True))
    with pytest.raises(ValueError, match="veriden liste"):
        registry._kolonu_denetle(M, replace(M.kolonlar["il"], onerili=False))
    with pytest.raises(ValueError, match="etiketleri yalnız"):
        registry._kolonu_denetle(M, replace(M.kolonlar["name"], secenek_etiketleri={"a": "b"}))
    with pytest.raises(ValueError, match="seçilemeyen kolon"):
        registry._kolonu_denetle(M, replace(M.kolonlar["name"], secilebilir=False))
    with pytest.raises(ValueError, match="grubunda olmalı"):
        registry._kolonu_denetle(M, replace(M.kolonlar["arama"], grup="Kimlik"))
    with pytest.raises(ValueError, match="yalnız seçilemeyen"):
        registry._kolonu_denetle(M, replace(M.kolonlar["name"], grup="Arama"))
    registry._kolonu_denetle(M, M.kolonlar["arama"])
    registry._kolonu_denetle(M, replace(M.kolonlar["il"], secenek_etiketleri={"Ankara": "Başkent"}))


# ═══════════════════════════════════════════════════════════════════════════
# 6. Asistan: "(boş)" çevirisi + katalog metni şerhi + uzunluk
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_bos_sabiti_in_listesinde_null_olur():
    """Kabul: `degerler:["Ankara","(boş)"]` → `in ["Ankara", null]`; "(bos)" ve boşluklu/büyük yazım da;
    `between`de çevrilmez → doğrulama "null yalnız 'in' listesinde" ile reddeder; tam yol `RaporTanimi` verir."""
    t = AsistanTanimi(veri_kaynagi="muvekkiller", kolonlar=["name", "il"], filtreler=[
        {"alan": "il", "op": "in", "degerler": ["Ankara", "(boş)"]},
        {"alan": "il", "op": "in", "degerler": [" (BOS) ", "İzmir", "(boş)"]},
        {"alan": "il", "op": "eq", "deger": "(boş)"},                      # tek değerde çevrilmez (metin)
    ])
    govde = asistan.asistan_tanimini_cevir(t)
    assert [f["deger"] for f in govde["filtreler"]] == [["Ankara", None], [None, "İzmir", None], "(boş)"]
    rt = asistan.tanimi_dogrula(t)
    assert isinstance(rt, RaporTanimi) and rt.filtreler[0].deger == ["Ankara", None]
    t2 = AsistanTanimi(veri_kaynagi="muvekkiller", kolonlar=["name"], filtreler=[
        {"alan": "vekaletname_tarihi", "op": "between", "degerler": ["(boş)", "2025-01-01"]},
    ])
    assert asistan.asistan_tanimini_cevir(t2)["filtreler"][0]["deger"] == ["(boş)", "2025-01-01"]
    with pytest.raises(RaporDogrulamaHatasi) as ex:
        asistan.tanimi_dogrula(t2)
    assert "ISO" in ex.value.sebep                                          # motor tarih denetimi (null yok)
    assert asistan.BOS_SABITLERI == frozenset({"(boş)", "(bos)"})


def test_katalog_metni_arama_serhi_ve_uzunluk_sismez(env):
    """Kabul: `katalog_metni` her kaynakta `arama`yı "yalnız filtre" şerhiyle içerir; veriden seçenek listeleri
    ve etiketler gömülmez (DB yok); toplam uzunluk `arama` satırları çıkarılmış hâlinin (G137 sonrası)
    +%20'sini aşmaz; prompt "(boş)" kuralını tek satırda taşır."""
    metin = asistan.katalog_metni()
    satirlar = metin.splitlines()
    arama_satirlari = [s for s in satirlar if s.startswith("arama · ")]
    assert len(arama_satirlari) == len(registry.KAYNAKLAR)
    for s in arama_satirlari:
        assert s.startswith("arama · Ara · metin · yalnız filtre") and "contains" in s
    for yasak in ("Ankara", "İstanbul", "Gerçek kişi", "secenek_etiketleri", "secilebilir", "secenek_kaynagi",
                  "sunum", "var_yok", "bos_anahtari"):
        assert yasak not in metin, yasak
    g137_hali = "\n".join(s for s in satirlar if not s.startswith("arama · "))
    assert len(metin) <= len(g137_hali) * 1.2
    talimat = get_rapor_asistani_instruction(metin, "2026-09-07")
    bos_kurali = [s for s in talimat.splitlines() if "(boş)" in s]
    assert len(bos_kurali) == 1 and "in" in bos_kurali[0]


# ═══════════════════════════════════════════════════════════════════════════
# 7. Sözleşme bekçileri: /preview gövdesi aynı, önbellek eşik sorgularını kapsar
# ═══════════════════════════════════════════════════════════════════════════

def test_onizleme_govdesi_degismedi_ve_onbellek_grup_sorgularini_kapsar(env, monkeypatch):
    client = env.client()
    r = _onizle(client, _tanim(kolonlar=("name", "il"), siralama=[{"alan": "name", "yon": "asc"}]), sayfa_boyu=2)
    govde = r.json()
    assert set(govde) == {"kolonlar", "satirlar", "toplam", "sayfa", "sayfa_boyu"}
    assert govde["kolonlar"] == [{"anahtar": "name", "etiket": "Müvekkil Adı", "tip": "metin"},
                                 {"anahtar": "il", "etiket": "İl", "tip": "metin"}]
    assert govde["toplam"] == 8 and len(govde["satirlar"]) == 2
    sayac = {"n": 0}
    gercek = registry.veriden_secenekleri_getir

    def sayan(*a, **k):
        sayac["n"] += 1
        return gercek(*a, **k)

    monkeypatch.setattr(registry, "veriden_secenekleri_getir", sayan)
    env.route.katalog_onbellegini_sifirla()
    client.get(CATALOG)
    ilk = sayac["n"]
    assert ilk == sum(1 for k in registry.KAYNAKLAR.values() for c in k.kolonlar.values() if c.tip != "liste")
    client.get(CATALOG)
    assert sayac["n"] == ilk                                     # 60 sn önbellek: GROUP BY sorguları tekrar koşmaz
