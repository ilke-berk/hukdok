"""G251 — Raporlama "Hizmetler" kaynağı (müvekkil × hizmet × dava) + davalarda çok değerli hizmet kolonu.

Kabul: muhasebe sorusu sohbet ekranından sorulabilsin — "X müvekkiline hangi davalarda hangi hizmet
verildi", "Lexis Rapor verilen müvekkiller". Kaynak satırı = bir hizmet kaydı (`case_hizmetleri`, G248);
kendi kolonları hizmet türü (kapalı liste), kaynak (`föy`/`elle`), müvekkil adı; `dava.*` tekil bağ
(föyler deseni), `muvekkil.*` çoklu bağ ama hizmetin KENDİ tarafına dar (`kart_eslesmesi`); tenant +
soft-delete dava üzerinden, föyü kapsam dışı işaretli satır görünmez. `davalar.hizmet_turu` artık
satırların " ; " birleşik özeti → çok değerli (eski eşitlik filtresi TAM ÖĞE eşler). Özet modu:
müvekkile ve hizmet türüne göre `sayi`. Asistan kataloğu kaynağı tanır, tanım `tanimi_dogrula`
yolundan geçer (K6).

Düzen `test_g166_rapor_bagli_kaynaklar.env` reçetesiyle aynı (sqlite StaticPool, gerçek `require_admin`).
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from managers import case_hizmetleri
from managers.seed_data import SERVICE_TYPES
from prompts import get_rapor_asistani_instruction
from schemas_rapor import KOLON_MAX, AsistanTanimi, RaporDogrulamaHatasi, RaporTanimi
from services.rapor import asistan, motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)

TAKIP = "Takip (doktor müvekkil)"
RAPOR = "Lexis Rapor"
DANISMANLIK = "Danışmanlık"


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

def _veri_yukle(db):
    C = models.Case
    c1 = C(tracking_no="HA.G251.1", tenant_id=T1, status="DERDEST", esas_no="2025/10", court="Bursa 1. Asliye Hukuk")
    c2 = C(tracking_no="HA.G251.2", tenant_id=None, status="DERDEST", esas_no="2025/20", court="Ankara 2. Asliye Hukuk")
    c3 = C(tracking_no="HA.G251.3", tenant_id=T2, status="DERDEST", esas_no="2025/30")
    c4 = C(tracking_no="HA.G251.4", tenant_id=T1, status="DERDEST", esas_no="2025/40", deleted_at=SILINDI,
           deleted_by=ADMIN)
    # Hizmet satırı HİÇ yazılmamış kart: aktarımın eski tek değeri durur (G248 sözleşmesi)
    c5 = C(tracking_no="HA.G251.5", tenant_id=T1, status="DERDEST", esas_no="2025/50", hizmet_turu=TAKIP)
    db.add_all([c1, c2, c3, c4, c5])
    db.flush()

    ayse = models.Client(name="Dr. Ayşe", tenant_id=T1, category="Doktor", phone="0212 111", il="İstanbul")
    beta = models.Client(name="Beta Hastanesi", tenant_id=None, category="Özel Hastane", phone="0312 222", il="Ankara")
    gamma = models.Client(name="Gamma Ltd", tenant_id=T1, category="Kurum", phone="999", deleted_at=SILINDI)
    db.add_all([ayse, beta, gamma])
    db.flush()

    P = models.CaseParty
    p_ayse1 = P(case_id=c1.id, client_id=ayse.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT")
    # client_id BOŞ → ad anahtarıyla karta bağlanır (`kart_eslesmesi`, büyük/küçük harf katlanır)
    p_beta1 = P(case_id=c1.id, name="BETA HASTANESI", role="Davalı", party_type="CLIENT")
    p_kartsiz = P(case_id=c1.id, name="Kartsız Kişi", role="Davalı", party_type="CLIENT")     # hiç kartı yok
    p_gamma = P(case_id=c1.id, client_id=gamma.id, name="Gamma Ltd", role="Davalı", party_type="CLIENT")  # kart silinmiş
    p_karsi = P(case_id=c1.id, name="Hasta H", role="Davacı", party_type="COUNTER")
    p_ayse2 = P(case_id=c2.id, client_id=ayse.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT")
    p_yabanci = P(case_id=c3.id, name="Yabancı Müvekkil", role="Davalı", party_type="CLIENT")
    p_silinmis = P(case_id=c4.id, client_id=ayse.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT")
    db.add_all([p_ayse1, p_beta1, p_kartsiz, p_gamma, p_karsi, p_ayse2, p_yabanci, p_silinmis])
    db.flush()

    F = models.CaseFoy
    f1 = F(sistem_no="SSTMN-1", case_id=c1.id, case_party_id=p_ayse1.id, hizmet_turu=TAKIP)
    f2 = F(sistem_no="SSTMN-2", case_id=c1.id, case_party_id=p_beta1.id, hizmet_turu=DANISMANLIK,
           kapsam_durumu="KAPSAM_DISI", kapsam_gerekcesi="malpraktis dışı")
    db.add_all([f1, f2])
    db.flush()

    H = models.CaseHizmeti
    db.add_all([
        H(case_id=c1.id, case_party_id=p_ayse1.id, hizmet_turu=TAKIP, foy_id=f1.id, source="HUKDOK_TESLIM_X"),
        H(case_id=c1.id, case_party_id=p_ayse1.id, hizmet_turu=RAPOR, source="panel", created_by="Av. Ali"),
        H(case_id=c1.id, case_party_id=p_beta1.id, hizmet_turu=RAPOR, source="panel"),
        # föyü kapsam dışı işaretli → rapora GİRMEZ (aktarım henüz satırı silmemiş olsa da)
        H(case_id=c1.id, case_party_id=p_beta1.id, hizmet_turu=DANISMANLIK, foy_id=f2.id, source="HUKDOK_TESLIM_X"),
        H(case_id=c1.id, case_party_id=p_kartsiz.id, hizmet_turu=TAKIP, source="panel"),
        H(case_id=c1.id, case_party_id=p_gamma.id, hizmet_turu=DANISMANLIK, source="panel"),
        H(case_id=c2.id, case_party_id=p_ayse2.id, hizmet_turu=RAPOR, source="panel"),
        H(case_id=c3.id, case_party_id=p_yabanci.id, hizmet_turu=TAKIP, source="panel"),        # başka tenant
        H(case_id=c4.id, case_party_id=p_silinmis.id, hizmet_turu=TAKIP, source="panel"),       # silinmiş dava
    ])
    db.flush()
    # Kart özeti GERÇEK yazıcıdan (`cases.hizmet_turu` = satırların DISTINCT adları, " ; " birleşik)
    for kart in (c1, c2):
        case_hizmetleri.ozeti_yenile(db, kart.id)
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


def _tanim(kolonlar, filtreler=(), siralama=(), kaynak="hizmetler", **ek):
    return {"veri_kaynagi": kaynak, "kolonlar": list(kolonlar), "filtreler": list(filtreler),
            "siralama": list(siralama), **ek}


def _onizle(client, tanim):
    r = client.post(PREVIEW, json={"tanim": tanim, "sayfa_boyu": 200})
    assert r.status_code == 200, r.text
    return r.json()


def _uclu(govde):
    """(müvekkil, hizmet, dava ofis no) üçlüleri — sıralı liste."""
    return sorted((s["muvekkil_adi"], s["hizmet_turu"], s["dava.tracking_no"]) for s in govde["satirlar"])


def _katalog(client, kaynak="hizmetler"):
    r = client.get(CATALOG)
    assert r.status_code == 200, r.text
    return next(k for k in r.json()["veri_kaynaklari"] if k["anahtar"] == kaynak)


def _kolonlar(kaynak):
    return {k["anahtar"]: k for k in kaynak["kolonlar"]}


UCLU_KOLONLAR = ("muvekkil_adi", "hizmet_turu", "dava.tracking_no")
T1_UCLULERI = [
    ("BETA HASTANESI", RAPOR, "HA.G251.1"),
    ("Dr. Ayşe", RAPOR, "HA.G251.1"),
    ("Dr. Ayşe", RAPOR, "HA.G251.2"),
    ("Dr. Ayşe", TAKIP, "HA.G251.1"),
    ("Gamma Ltd", DANISMANLIK, "HA.G251.1"),
    ("Kartsız Kişi", TAKIP, "HA.G251.1"),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kayıt defteri + katalog
# ═══════════════════════════════════════════════════════════════════════════

def test_kaynak_kayit_defterinde_ve_katalogda(env):
    """Kabul: `hizmetler` beşinci kaynak; kendi kolonları hizmet türü (kapalı liste), kaynak (`föy`/`elle`),
    müvekkil adı (düz → gruplanabilir); `dava.*` tekil, `muvekkil.*` çoklu bağ."""
    assert list(registry.KAYNAKLAR) == ["davalar", "muvekkiller", "belgeler", "foyler", "hizmetler"]
    assert "hizmetler" in registry.CEKIRDEK
    kaynak = _katalog(env.client())
    assert kaynak["etiket"] == "Hizmetler"
    assert kaynak["varsayilan_kolonlar"] == ["muvekkil_adi", "hizmet_turu", "dava.tracking_no", "dava.esas_no",
                                             "dava.court", "kaynak"]
    assert kaynak["iliskiler"] == [
        {"anahtar": "dava", "etiket": "Dava", "hedef": "davalar", "coklu": False},
        {"anahtar": "muvekkil", "etiket": "Müvekkil kartı", "hedef": "muvekkiller", "coklu": True},
    ]
    k = _kolonlar(kaynak)
    assert [a for a, c in k.items() if c["bag"] is None] == [
        "arama", "hizmet_turu", "kaynak", "muvekkil_adi", "sistem_no", "id", "case_id", "source", "created_by",
        "created_at",
    ]
    hizmet = k["hizmet_turu"]
    assert hizmet["tip"] == "liste" and hizmet["secenek_kaynagi"] == "sabit" and hizmet["gruplanabilir"] is True
    assert set(hizmet["secenekler"]) == {ad for _kod, ad in SERVICE_TYPES}
    # sayılar kaynağın kısıtlarıyla: kapsam dışı föyün "Danışmanlık" satırı sayılmaz (yalnız Gamma'nın elle satırı)
    assert hizmet["secenek_sayilari"][RAPOR] == 3 and hizmet["secenek_sayilari"][TAKIP] == 2
    assert hizmet["secenek_sayilari"][DANISMANLIK] == 1
    kay = k["kaynak"]
    assert kay["tip"] == "liste" and kay["secenekler"] == ["elle", "föy"]          # sayıya göre azalan
    assert kay["secenek_sayilari"] == {"elle": 5, "föy": 1} and kay["gruplanabilir"] is True
    muv = k["muvekkil_adi"]
    assert muv["tip"] == "metin" and muv["turetilmis"] is False and muv["gruplanabilir"] is True
    assert muv["oneriler"] == ["BETA HASTANESI", "Dr. Ayşe", "Gamma Ltd", "Kartsız Kişi"]
    # tekil dava bağı düz kolon gibi (sıralanır/gruplanır); müvekkil kartı bağı çoklu (türetilmiş, sıralanmaz)
    assert k["dava.tracking_no"]["siralanabilir"] is True and k["dava.tracking_no"]["bag"] == "dava"
    assert k["muvekkil.phone"]["turetilmis"] is True and k["muvekkil.phone"]["siralanabilir"] is False
    # kartın hizmet ÖZETİ bu kaynakta yok (satırın kendi kolonu var); müvekkil kartının dava sayısı da (haric)
    assert "dava.hizmet_turu" not in k and "muvekkil.dava_sayisi" not in k
    assert not (set(k) & registry.YASAK_KOLONLAR)


def test_hizli_filtreler_ve_kolon_seti(env):
    kaynak = _katalog(env.client())
    assert [(hf["alan"], hf["sunum"]) for hf in kaynak["hizli_filtreler"]] == [
        ("arama", "arama"), ("hizmet_turu", "varsayilan"), ("muvekkil_adi", "varsayilan"), ("kaynak", "varsayilan"),
    ]
    assert kaynak["kolon_setleri"] == [{"ad": "Temel", "kolonlar": kaynak["varsayilan_kolonlar"]}]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Satırlar: tenant + soft-delete + kapsam dışı föy
# ═══════════════════════════════════════════════════════════════════════════

def test_satir_bir_hizmet_kaydi_tenant_soft_delete_ve_kapsam(env):
    """Kabul: kısıtlar dava kaynağından (`_foy_kisitlari` deseni) — başka tenant'ın ve silinmiş davanın
    satırı yok, NULL tenant (paylaşımlı) var; föyü kapsam dışı işaretli satır görünmez."""
    govde = _onizle(env.client(), _tanim(UCLU_KOLONLAR))
    assert _uclu(govde) == T1_UCLULERI and govde["toplam"] == 6
    assert not any(s["hizmet_turu"] == DANISMANLIK and s["muvekkil_adi"] == "BETA HASTANESI" for s in govde["satirlar"])
    # başka tenant: kendi kaydı + paylaşımlı (NULL) dava
    assert _uclu(_onizle(env.client(tid=T2), _tanim(UCLU_KOLONLAR))) == [
        ("Dr. Ayşe", RAPOR, "HA.G251.2"), ("Yabancı Müvekkil", TAKIP, "HA.G251.3"),
    ]


def test_silinmis_davanin_satiri_id_ile_de_gelmez(env):
    db = env.db()
    try:
        c4 = db.query(models.Case).filter_by(tracking_no="HA.G251.4").one().id
        f2 = db.query(models.CaseFoy).filter_by(sistem_no="SSTMN-2").one().id
        kapsam_disi = db.query(models.CaseHizmeti).filter_by(foy_id=f2).one().id
    finally:
        db.close()
    client = env.client()
    assert _onizle(client, _tanim(("id",), [{"alan": "case_id", "op": "eq", "deger": c4}]))["toplam"] == 0
    assert _onizle(client, _tanim(("id",), [{"alan": "id", "op": "eq", "deger": kapsam_disi}]))["toplam"] == 0


def test_kapsam_isareti_kalkinca_satir_gorunur(env):
    """Kısıt föyün GÜNCEL işaretine bakar: işaret NULL'a çekilince (föy yeniden kapsamda) satır gelir."""
    db = env.db()
    try:
        db.query(models.CaseFoy).filter_by(sistem_no="SSTMN-2").update({"kapsam_durumu": None})
        db.commit()
    finally:
        db.close()
    govde = _onizle(env.client(), _tanim((*UCLU_KOLONLAR, "kaynak", "sistem_no")))
    assert govde["toplam"] == 7
    [satir] = [s for s in govde["satirlar"] if s["sistem_no"] == "SSTMN-2"]
    assert (satir["muvekkil_adi"], satir["hizmet_turu"], satir["kaynak"]) == ("BETA HASTANESI", DANISMANLIK, "föy")


def test_kaynak_kolonu_foy_elle(env):
    """`kaynak`: `foy_id` dolu → "föy" (+ föyün SistemNo'su), boş → "elle"; düz kolon gibi süzülür/sıralanır."""
    client = env.client()
    foy = _onizle(client, _tanim((*UCLU_KOLONLAR, "kaynak", "sistem_no"),
                                 [{"alan": "kaynak", "op": "eq", "deger": "föy"}]))
    assert foy["satirlar"] == [{"muvekkil_adi": "Dr. Ayşe", "hizmet_turu": TAKIP, "dava.tracking_no": "HA.G251.1",
                                "kaynak": "föy", "sistem_no": "SSTMN-1"}]
    elle = _onizle(client, _tanim((*UCLU_KOLONLAR, "kaynak", "sistem_no"),
                                  [{"alan": "kaynak", "op": "in", "deger": ["elle"]}]))
    assert elle["toplam"] == 5 and {s["kaynak"] for s in elle["satirlar"]} == {"elle"}
    assert {s["sistem_no"] for s in elle["satirlar"]} == {None}
    sirali = _onizle(client, _tanim(("kaynak",), siralama=[{"alan": "kaynak", "yon": "desc"}]))
    assert [s["kaynak"] for s in sirali["satirlar"]] == ["föy"] + ["elle"] * 5


# ═══════════════════════════════════════════════════════════════════════════
# 3. Müvekkil ve dava kolonları (bağlı kaynaklar)
# ═══════════════════════════════════════════════════════════════════════════

def test_muvekkil_karti_kolonlari_hizmetin_kendi_tarafindan(env):
    """Kabul: müvekkil kolonları `case_parties.client_id` → müvekkiller (id yoksa ad anahtarı), bağsız
    tarafta yalnız ad. Bağ hizmetin KENDİ tarafına dar: aynı kartta başka müvekkilin kartı karışmaz."""
    govde = _onizle(env.client(), _tanim(("muvekkil_adi", "hizmet_turu", "muvekkil.phone", "muvekkil.category",
                                          "muvekkil.name"),
                                         [{"alan": "dava.tracking_no", "op": "eq", "deger": "HA.G251.1"}]))
    satirlar = {(s["muvekkil_adi"], s["hizmet_turu"]): s for s in govde["satirlar"]}
    assert satirlar[("Dr. Ayşe", TAKIP)]["muvekkil.phone"] == "0212 111"          # client_id bağı
    assert satirlar[("Dr. Ayşe", RAPOR)]["muvekkil.category"] == "Doktor"
    beta = satirlar[("BETA HASTANESI", RAPOR)]                                     # ad anahtarı bağı
    assert (beta["muvekkil.phone"], beta["muvekkil.category"], beta["muvekkil.name"]) == \
        ("0312 222", "Özel Hastane", "Beta Hastanesi")
    kartsiz = satirlar[("Kartsız Kişi", TAKIP)]                                    # bağsız taraf: yalnız ad
    assert kartsiz["muvekkil.phone"] is None and kartsiz["muvekkil.name"] is None
    assert satirlar[("Gamma Ltd", DANISMANLIK)]["muvekkil.phone"] is None          # silinmiş kart sayılmaz


def test_muvekkil_karti_filtresi_satirin_tarafina_bakar(env):
    client = env.client()
    doktor = _onizle(client, _tanim(UCLU_KOLONLAR, [{"alan": "muvekkil.category", "op": "eq", "deger": "Doktor"}]))
    assert _uclu(doktor) == [("Dr. Ayşe", RAPOR, "HA.G251.1"), ("Dr. Ayşe", RAPOR, "HA.G251.2"),
                             ("Dr. Ayşe", TAKIP, "HA.G251.1")]
    ankara = _onizle(client, _tanim(UCLU_KOLONLAR, [{"alan": "muvekkil.il", "op": "eq", "deger": "Ankara"}]))
    assert _uclu(ankara) == [("BETA HASTANESI", RAPOR, "HA.G251.1")]
    kartsiz = _onizle(client, _tanim(UCLU_KOLONLAR, [{"alan": "muvekkil.name", "op": "is_null"}]))
    assert _uclu(kartsiz) == [("Gamma Ltd", DANISMANLIK, "HA.G251.1"), ("Kartsız Kişi", TAKIP, "HA.G251.1")]


def test_dava_kolonlari_tekil_bag_duz_kolon_gibi(env):
    govde = _onizle(env.client(), _tanim(("muvekkil_adi", "dava.tracking_no", "dava.esas_no", "dava.court",
                                          "dava.muvekkil_adlari"),
                                         [{"alan": "dava.court", "op": "contains", "deger": "Ankara"}],
                                         [{"alan": "dava.tracking_no", "yon": "desc"}]))
    assert govde["satirlar"] == [{"muvekkil_adi": "Dr. Ayşe", "dava.tracking_no": "HA.G251.2",
                                  "dava.esas_no": "2025/20", "dava.court": "Ankara 2. Asliye Hukuk",
                                  "dava.muvekkil_adlari": "Dr. Ayşe"}]


def test_muhasebe_sorulari(env):
    """Hedef: "X müvekkiline hangi davalarda hangi hizmet verildi" + "Lexis Rapor verilen müvekkiller"."""
    client = env.client()
    ayse = _onizle(client, _tanim(("muvekkil_adi", "hizmet_turu", "dava.tracking_no", "dava.esas_no"),
                                  [{"alan": "muvekkil_adi", "op": "contains", "deger": "ayşe"}],
                                  [{"alan": "dava.tracking_no", "yon": "asc"}, {"alan": "hizmet_turu", "yon": "asc"}]))
    assert [(s["dava.tracking_no"], s["dava.esas_no"], s["hizmet_turu"]) for s in ayse["satirlar"]] == [
        ("HA.G251.1", "2025/10", RAPOR), ("HA.G251.1", "2025/10", TAKIP), ("HA.G251.2", "2025/20", RAPOR),
    ]
    rapor = _onizle(client, _tanim(UCLU_KOLONLAR, [{"alan": "hizmet_turu", "op": "eq", "deger": RAPOR}]))
    assert {s["muvekkil_adi"] for s in rapor["satirlar"]} == {"Dr. Ayşe", "BETA HASTANESI"} and rapor["toplam"] == 3
    # tek arama kutusu: müvekkil adı / hizmet türü / ofis no / esas no / föy SistemNo
    for deger, beklenen in (("kartsız", 1), ("lexis", 3), ("G251.2", 1), ("2025/20", 1), ("SSTMN-1", 1)):
        govde = _onizle(client, _tanim(UCLU_KOLONLAR, [{"alan": "arama", "op": "contains", "deger": deger}]))
        assert govde["toplam"] == beklenen, deger


def test_tum_secilebilir_kolonlar_sorgulanir(env):
    """Bağlı kolon alt sorguları (dava.* türetilmişleri `case_parties`/`case_foys` üzerinde; hizmetler FROM'unda
    ikisi de var) korelasyon tuzağına düşmez: her seçilebilir kolon seçilir, her filtrelenebilir kolon süzülür."""
    kaynak = registry.KAYNAKLAR["hizmetler"]
    secilebilir = [a for a, k in kaynak.kolonlar.items() if k.secilebilir]
    client = env.client()
    for i in range(0, len(secilebilir), KOLON_MAX):
        govde = _onizle(client, _tanim(secilebilir[i:i + KOLON_MAX]))
        assert govde["toplam"] == 6, secilebilir[i:i + KOLON_MAX]
    for anahtar, kolon in kaynak.kolonlar.items():
        if kolon.filtrelenebilir and "is_null" in kolon.oplar:
            r = client.post(PREVIEW, json={"tanim": _tanim(("id",), [{"alan": anahtar, "op": "is_null"}])})
            assert r.status_code == 200, (anahtar, r.text)


def test_postgres_sorgusu_join_ve_kapsam_kisiti():
    """Derlenen SQL (Postgres lehçesi): dava INNER, taraf INNER, föy LEFT JOIN; kapsam + soft-delete WHERE'de."""
    tanim = RaporTanimi(veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi", "hizmet_turu", "kaynak", "muvekkil.phone"])
    sql = str(motor.sorgu_kur(tanim, T1).compile(dialect=postgresql.dialect()))
    assert "FROM case_hizmetleri JOIN cases ON case_hizmetleri.case_id = cases.id" in sql
    assert "JOIN case_parties ON case_hizmetleri.case_party_id = case_parties.id" in sql
    assert "LEFT OUTER JOIN case_foys ON case_hizmetleri.foy_id = case_foys.id" in sql
    assert "coalesce(case_foys.kapsam_durumu" in sql and "cases.deleted_at IS NULL" in sql
    assert "ORDER BY case_hizmetleri.id" in sql


# ═══════════════════════════════════════════════════════════════════════════
# 4. Özet modu
# ═══════════════════════════════════════════════════════════════════════════

def test_ozet_muvekkile_ve_hizmet_turune_gore_sayi(env):
    """Kabul: `hizmetler` kaynağında müvekkile ve hizmet türüne göre `sayi` gruplaması."""
    client = env.client()
    muvekkil = _onizle(client, _tanim(("muvekkil_adi",), gruplama=[{"alan": "muvekkil_adi"}],
                                      olcumler=[{"islem": "sayi"}]))
    assert [k["anahtar"] for k in muvekkil["kolonlar"]] == ["muvekkil_adi", "sayi"]
    assert muvekkil["satirlar"] == [                     # sayı azalan, eşitlikte müvekkil adı artan
        {"muvekkil_adi": "Dr. Ayşe", "sayi": 3},
        {"muvekkil_adi": "BETA HASTANESI", "sayi": 1},
        {"muvekkil_adi": "Gamma Ltd", "sayi": 1},
        {"muvekkil_adi": "Kartsız Kişi", "sayi": 1},
    ]
    hizmet = _onizle(client, _tanim(("hizmet_turu",), gruplama=[{"alan": "hizmet_turu"}],
                                    olcumler=[{"islem": "sayi"}]))
    assert {s["hizmet_turu"]: s["sayi"] for s in hizmet["satirlar"]} == {RAPOR: 3, TAKIP: 2, DANISMANLIK: 1}
    assert hizmet["satirlar"][0] == {"hizmet_turu": RAPOR, "sayi": 3} and hizmet["toplam"] == 3
    ikili = _onizle(client, _tanim(("muvekkil_adi",),
                                   [{"alan": "muvekkil_adi", "op": "contains", "deger": "Ayşe"}],
                                   [{"alan": "hizmet_turu", "yon": "asc"}],
                                   gruplama=[{"alan": "muvekkil_adi"}, {"alan": "hizmet_turu"}, {"alan": "kaynak"}],
                                   olcumler=[{"islem": "sayi"}, {"islem": "sayi", "alan": "dava.tracking_no"}]))
    assert ikili["satirlar"] == [
        {"muvekkil_adi": "Dr. Ayşe", "hizmet_turu": RAPOR, "kaynak": "elle", "sayi": 2, "sayi:dava.tracking_no": 2},
        {"muvekkil_adi": "Dr. Ayşe", "hizmet_turu": TAKIP, "kaynak": "föy", "sayi": 1, "sayi:dava.tracking_no": 1},
    ]


def test_ozet_muvekkil_karti_kolonu_gruplanamaz(env):
    """Çoklu bağ kolonu (birleşik metin) gruplanamaz — motorun mevcut kuralı; müvekkile göre gruplama
    düz `muvekkil_adi` iledir."""
    r = env.client().post(PREVIEW, json={"tanim": _tanim(("muvekkil_adi",), gruplama=[{"alan": "muvekkil.category"}],
                                                         olcumler=[{"islem": "sayi"}])})
    assert r.status_code == 422 and "gruplanamaz" in r.json()["detail"]["sebep"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Davalar: `hizmet_turu` çok değerli (özet " ; " birleşik)
# ═══════════════════════════════════════════════════════════════════════════

def _davalar(client, filtre):
    govde = _onizle(client, _tanim(("tracking_no",), [filtre], [{"alan": "tracking_no", "yon": "asc"}],
                                   kaynak="davalar"))
    return [s["tracking_no"] for s in govde["satirlar"]]


def test_davalar_hizmet_turu_cok_degerli_katalog(env):
    db = env.db()
    try:
        ozet = db.query(models.Case).filter_by(tracking_no="HA.G251.1").one().hizmet_turu
    finally:
        db.close()
    assert ozet == f"{DANISMANLIK} ; {RAPOR} ; {TAKIP}"              # G248 özeti: DISTINCT, alfabetik, " ; "
    kolon = _kolonlar(_katalog(env.client(), "davalar"))["hizmet_turu"]
    assert kolon["coklu_deger"] is True and kolon["tip"] == "metin" and kolon["kontrol"] == "coklu_secim"
    assert kolon["secenek_kaynagi"] == "veri" and "eq" in kolon["oplar"] and "contains" in kolon["oplar"]
    # öğe bazında kart sayısı: c1 üç öğe, c2 Lexis Rapor, c5 eski tek değer (silinmiş/yabancı kart yok)
    assert kolon["secenek_sayilari"] == {RAPOR: 2, TAKIP: 2, DANISMANLIK: 1}
    assert kolon["secenekler"] == [RAPOR, TAKIP, DANISMANLIK]
    assert registry.DAVALAR.kolonlar["hizmet_turu"].secenek_tablosu is models.ServiceType


def test_davalar_eski_esitlik_filtresi_tam_oge_esler(env):
    """Kabul: eski `hizmet_turu eq "Lexis Rapor"` filtresi birleşik özette TAM ÖĞE eşler — çok hizmetli
    kartı da getirir, parça eşleşmesi yapmaz; `in`/`ne`/boş anlamı çok değerli atomla."""
    client = env.client()
    assert _davalar(client, {"alan": "hizmet_turu", "op": "eq", "deger": RAPOR}) == ["HA.G251.1", "HA.G251.2"]
    assert _davalar(client, {"alan": "hizmet_turu", "op": "eq", "deger": TAKIP}) == ["HA.G251.1", "HA.G251.5"]
    assert _davalar(client, {"alan": "hizmet_turu", "op": "eq", "deger": "Takip"}) == []          # parça ≠ öğe
    assert _davalar(client, {"alan": "hizmet_turu", "op": "contains", "deger": "Takip"}) == ["HA.G251.1", "HA.G251.5"]
    assert _davalar(client, {"alan": "hizmet_turu", "op": "in", "deger": [DANISMANLIK, RAPOR]}) == \
        ["HA.G251.1", "HA.G251.2"]
    assert _davalar(client, {"alan": "hizmet_turu", "op": "ne", "deger": RAPOR}) == ["HA.G251.5"]
    # tekil bağ kopyası (föyler → dava.hizmet_turu) aynı anlamı taşır
    foy = _onizle(client, _tanim(("sistem_no",), [{"alan": "dava.hizmet_turu", "op": "eq", "deger": RAPOR}],
                                 [{"alan": "sistem_no", "yon": "asc"}], kaynak="foyler"))
    assert [s["sistem_no"] for s in foy["satirlar"]] == ["SSTMN-1", "SSTMN-2"]
    # föyün KENDİ hizmet türü tek değerli kapalı liste kalır
    assert registry.KAYNAKLAR["foyler"].kolonlar["hizmet_turu"].tip == "liste"
    assert registry.KAYNAKLAR["foyler"].kolonlar["hizmet_turu"].coklu_deger is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. Asistan: katalog kaynağı tanır, tanım tek doğrulama yolundan (K6)
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_katalogu_kaynagi_ve_ipucunu_tasir(env):
    metin = asistan.katalog_metni()
    blok = next(b for b in metin.split("\n\n") if b.startswith("## hizmetler — Hizmetler"))
    satirlar = blok.splitlines()
    assert satirlar[1] == "varsayılan kolonlar: muvekkil_adi, hizmet_turu, dava.tracking_no, dava.esas_no, dava.court, kaynak"
    assert satirlar[2] == asistan.KAYNAK_IPUCLARI["hizmetler"] and satirlar[2].startswith("ne zaman: ")
    assert "Lexis Rapor verilen müvekkiller" in satirlar[2] and "GRUPLANIR" in satirlar[2]
    assert "hizmet_turu · Hizmet Türü · liste · " + "|".join(ad for _kod, ad in SERVICE_TYPES) in blok
    assert "kaynak · Kaynak · liste · föy|elle" in blok
    assert "\nmuvekkil_adi · Müvekkil · metin" in blok
    assert "dava.<kolon> · Dava · BAĞLI: 'davalar' kaynağının kolonları" in blok and "tekil: filtre/sıralama" in blok
    assert "muvekkil.<kolon> · Müvekkil kartı · BAĞLI: 'muvekkiller' kaynağının kolonları" in blok
    # ipucu yalnız tanımlı kaynakta; anahtarlar kayıt defterinde
    assert set(asistan.KAYNAK_IPUCLARI) <= set(registry.KAYNAKLAR)
    assert sum(1 for s in metin.splitlines() if s.startswith("ne zaman: ")) == len(asistan.KAYNAK_IPUCLARI)
    assert "## hizmetler — Hizmetler" in get_rapor_asistani_instruction(metin, "2026-10-02")
    # davalar.hizmet_turu prompt'a çok değerli şerhi + rota kataloğundaki öğelerle girer
    veri = asistan.veri_secenekleri_katalogdan(env.route._katalogu_getir(T1))
    assert veri[("davalar", "hizmet_turu")] == [RAPOR, TAKIP, DANISMANLIK]
    dava_satiri = next(s for s in asistan.katalog_metni(veri).splitlines() if s.startswith("hizmet_turu · Hizmet Türü · metin"))
    assert "ÇOK DEĞERLİ" in dava_satiri and f"{RAPOR}|{TAKIP}|{DANISMANLIK}" in dava_satiri


def test_asistan_tanimi_ayni_dogrulama_yolundan(env):
    """K6: asistanın `hizmetler` tanımı `asistan.tanimi_dogrula` → `RaporTanimi` + `motor.tanimi_dogrula`
    yolundan geçer ve çalışır; katalog dışı kolon / gruplanamayan kolon aynı yolda reddedilir."""
    tanim = asistan.tanimi_dogrula(AsistanTanimi(
        veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi", "hizmet_turu", "dava.tracking_no"],
        filtreler=[{"alan": "hizmet_turu", "op": "eq", "deger": RAPOR}],
        siralama=[{"alan": "muvekkil_adi", "yon": "asc"}],
    ))
    assert isinstance(tanim, RaporTanimi) and tanim.veri_kaynagi == "hizmetler"
    assert _onizle(env.client(), tanim.model_dump())["toplam"] == 3
    ozet = asistan.tanimi_dogrula(AsistanTanimi(
        veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi"], gruplama=[{"alan": "muvekkil_adi"}],
        olcumler=[{"islem": "sayi"}], siralama=[{"alan": "sayi", "yon": "desc"}],
    ))
    assert ozet.ozet_modu and _onizle(env.client(), ozet.model_dump())["satirlar"][0] == {"muvekkil_adi": "Dr. Ayşe",
                                                                                         "sayi": 3}
    with pytest.raises(RaporDogrulamaHatasi) as ex:
        asistan.tanimi_dogrula(AsistanTanimi(veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi", "dava.hizmet_turu"]))
    assert ex.value.alan == "kolonlar[1]" and "katalogda olmayan kolon" in ex.value.sebep
    with pytest.raises(RaporDogrulamaHatasi, match="gruplanamaz"):
        asistan.tanimi_dogrula(AsistanTanimi(veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi"],
                                             gruplama=[{"alan": "muvekkil.name"}], olcumler=[{"islem": "sayi"}]))
    with pytest.raises(RaporDogrulamaHatasi):
        asistan.tanimi_dogrula(AsistanTanimi(veri_kaynagi="hizmetler", kolonlar=["muvekkil_adi"],
                                             filtreler=[{"alan": "kaynak", "op": "contains", "deger": "föy"}]))
