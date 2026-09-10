"""G166 — Rapor kaynakları arası birleştirme: bağlı kaynak kolonları (`<iliski>.<kolon>`).

Kabul: "Nisan'dan sonra açılan davaların ofis no + müvekkil adı + müvekkil telefonu" TEK raporla
çıkar (`davalar` kaynağı, `muvekkil.phone`/`muvekkil.mobile_phone`). Bağlı kolonlar kayıt
defterinden TÜRETİLİR (elle liste yok), çoklu bağda değerler ' ; ' ile birleşik + EXISTS filtresi,
tekil bağda (belgeler/foyler → dava) düz kolon davranışı; tenant + soft-delete kuralları (K2)
bağ üzerinden de korunur; asistan katalog metni bağlı kolonları ilişki başına tek satırla gömer;
`kart_eslesmesi` ad anahtarı için ifade index'i migrasyonda (`_ad_anahtari` ile birebir).

Düzen `test_g137_rapor_katalog_genisleme.env` reçetesiyle aynı (sqlite StaticPool, gerçek
`require_admin`).
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
from database import Base
from prompts import get_rapor_asistani_instruction
from schemas_rapor import TIP_OPLARI, AsistanFiltre, AsistanTanimi, RaporDogrulamaHatasi, RaporTanimi
from services.rapor import asistan, motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

def _veri_yukle(db):
    c1 = models.Case(tracking_no="HA.G166.1", tenant_id=T1, status="DERDEST", subject="Mayis davasi",
                     court="Bursa 1. Asliye Hukuk", opening_date=dt.date(2026, 5, 1))
    c2 = models.Case(tracking_no="HA.G166.2", tenant_id=None, status="KARAR", subject="Mart davasi",
                     court="Ankara 2. Asliye Hukuk", opening_date=dt.date(2026, 3, 1))
    c3 = models.Case(tracking_no="HA.G166.3", tenant_id=T1, status="DERDEST", subject="Tarafsiz haziran",
                     court="Izmir 3. Asliye Hukuk", opening_date=dt.date(2026, 6, 1))
    c4 = models.Case(tracking_no="HA.G166.4", tenant_id=T2, status="DERDEST", subject="Baska tenant",
                     opening_date=dt.date(2026, 7, 1))
    c5 = models.Case(tracking_no="HA.G166.5", tenant_id=T1, status="DERDEST", subject="Silinmis dava",
                     opening_date=dt.date(2026, 7, 1), deleted_at=SILINDI, deleted_by=ADMIN)
    db.add_all([c1, c2, c3, c4, c5])
    db.flush()

    a = models.Client(name="Dr. Ayse", tenant_id=T1, category="Doktor", phone="0212 111", mobile_phone="0532 1",
                      il="Istanbul", vekaletname_tarihi=dt.date(2024, 1, 15), active=True)
    b = models.Client(name="Beta Hastanesi", tenant_id=None, category=None, phone=None, mobile_phone="0533 2",
                      il="Ankara", active=True)
    silinmis = models.Client(name="Kapanan Kart", tenant_id=T1, category="Kurum", phone="999", deleted_at=SILINDI)
    baska = models.Client(name="Yabanci Kart", tenant_id=T2, category="Kurum", phone="444")
    db.add_all([a, b, silinmis, baska])
    db.flush()

    P = models.CaseParty
    db.add_all([
        # c1: A (id bağı) + B (id bağı) + silinmiş kart (sayılmaz) + karşı taraf
        P(case_id=c1.id, client_id=a.id, name="Dr. Ayse", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, client_id=b.id, name="Beta Hastanesi", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, client_id=silinmis.id, name="Kapanan Kart", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, name="Hasta H", role="Davacı", party_type="COUNTER"),
        # c2: B — client_id BOŞ, ad anahtarıyla bağ (büyük/küçük harf farkı `_ad_anahtari` ile katlanır)
        P(case_id=c2.id, name="BETA HASTANESI", role="Davalı", party_type="CLIENT"),
        # c4 / c5: A — tenant / silinmiş dava (T1 raporuna girmez; müvekkiller→dava bağında da sayılmaz)
        P(case_id=c4.id, client_id=a.id, name="Dr. Ayse", role="Davalı", party_type="CLIENT"),
        P(case_id=c5.id, client_id=a.id, name="Dr. Ayse", role="Davalı", party_type="CLIENT"),
    ])
    F = models.CaseFoy
    db.add_all([
        F(sistem_no="S1", case_id=c1.id, tku_no="TKU-2", durum="MAHZEN"),
        F(sistem_no="S2", case_id=c1.id, tku_no="TKU-1", durum="DERDEST"),
        F(sistem_no="S3", case_id=c1.id, tku_no="TKU-1", durum="DERDEST"),      # tekrar eden TKU tekilleşir
        F(sistem_no="S4", case_id=c2.id, tku_no="TKU-9", durum="DERDEST"),
    ])
    D = models.CaseDocument
    db.add_all([
        D(case_id=c1.id, original_filename="dilekce.pdf", stored_filename="d1.pdf", belge_turu_adi="Dilekçe",
          link_mode="LINKED", uploaded_at=dt.datetime(2026, 5, 2, 10, 0)),
        D(case_id=c1.id, original_filename="silinmis.pdf", stored_filename="d2.pdf", belge_turu_adi="Silinmiş Tür",
          link_mode="LINKED", deleted_at=SILINDI, deleted_by=ADMIN),
        D(case_id=c2.id, original_filename="karar.pdf", stored_filename="d3.pdf", belge_turu_adi="Karar",
          link_mode="LINKED", uploaded_at=dt.datetime(2026, 3, 5, 9, 0)),
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

    yield SimpleNamespace(db=maker, client=_client, route=route_mod)
    route_mod.katalog_onbellegini_sifirla()
    engine.dispose()


def _tanim(kaynak="davalar", kolonlar=("tracking_no",), filtreler=(), siralama=()):
    return {"veri_kaynagi": kaynak, "kolonlar": list(kolonlar), "filtreler": list(filtreler),
            "siralama": list(siralama)}


def _onizle(client, tanim, **sayfa):
    return client.post(PREVIEW, json={"tanim": tanim, **sayfa})


def _satirlar(cevap, anahtar="tracking_no"):
    assert cevap.status_code == 200, cevap.text
    return {s[anahtar]: s for s in cevap.json()["satirlar"]}


def _takip(cevap):
    return set(_satirlar(cevap))


def _katalog(client):
    r = client.get(CATALOG)
    assert r.status_code == 200, r.text
    return {k["anahtar"]: k for k in r.json()["veri_kaynaklari"]}


def _kolonlar(kaynak):
    return {k["anahtar"]: k for k in kaynak["kolonlar"]}


def _422(r, alan_parcasi):
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert alan_parcasi in detail["alan"], detail
    return detail


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kayıt defteri: bağlı kolonlar türetilir, elle liste yok
# ═══════════════════════════════════════════════════════════════════════════

def test_iliskiler_ve_bagli_kolon_turetimi():
    """Kabul: davalar → muvekkil/foy/belge (çoklu), muvekkiller → dava (çoklu), belgeler/foyler → dava (tekil)
    + muvekkil (çoklu). Bağlı kolon = hedef kaynağın her seçilebilir kolonu (`haric` ve çoklu bağda
    türetilmişler dışında), anahtar `<iliski>.<kolon>`, etiket/grup `"<İlişki> · …"`, ikinci derece bağ YOK."""
    beklenen = {
        "davalar": [("muvekkil", "muvekkiller", True), ("foy", "foyler", True), ("belge", "belgeler", True)],
        "muvekkiller": [("dava", "davalar", True)],
        "belgeler": [("dava", "davalar", False), ("muvekkil", "muvekkiller", True)],
        "foyler": [("dava", "davalar", False), ("muvekkil", "muvekkiller", True)],
    }
    for anahtar, kaynak in registry.KAYNAKLAR.items():
        assert [(i.anahtar, i.hedef, i.coklu) for i in kaynak.iliskiler] == beklenen[anahtar]
        for iliski in kaynak.iliskiler:
            hedef = registry.CEKIRDEK[iliski.hedef]
            beklenen_kolonlar = [
                k for k in hedef.kolonlar.values()
                if k.secilebilir and k.anahtar not in iliski.haric and not (iliski.coklu and k.turetilmis)
            ]
            bagli = [k for k in kaynak.kolonlar.values() if k.bag == iliski.anahtar]
            assert [k.anahtar for k in bagli] == [f"{iliski.anahtar}.{k.anahtar}" for k in beklenen_kolonlar]
            for hk, bk in zip(beklenen_kolonlar, bagli, strict=True):
                assert bk.etiket == f"{iliski.etiket} · {hk.etiket}" and bk.grup == f"{iliski.etiket} · {hk.grup}"
                assert bk.tip == hk.tip and bk.grup in kaynak.gruplar
                assert "." not in hk.anahtar, "bağın bağı üretilmez"
                if iliski.coklu:
                    assert bk.turetilmis and bk.filtrelenebilir and not bk.siralanabilir
                    assert bk.oplar == TIP_OPLARI[hk.tip] and bk.filtre_ifadesi is not None
                    assert bk.onerili == (hk.onerili or hk.veriden_liste) and not bk.veriden_liste
                else:
                    # tekil: düz kolon düz kalır (sıralanabilir, veriden liste), türetilmiş türetilmiş kalır
                    assert (bk.turetilmis, bk.siralanabilir, bk.veriden_liste, bk.filtrelenebilir) == \
                        (hk.turetilmis, hk.siralanabilir, hk.veriden_liste, hk.filtrelenebilir)
    davalar = registry.DAVALAR.kolonlar
    assert "muvekkil.dava_sayisi" not in davalar and "muvekkil.arama" not in davalar
    assert "foy.case_id" not in davalar and "belge.dava_tracking_no" not in davalar
    assert "dava.muvekkil_adlari" not in registry.MUVEKKILLER.kolonlar      # çoklu bağda türetilmiş atlanır
    assert "dava.muvekkil_adlari" in registry.BELGELER.kolonlar             # tekil bağda kopyalanır
    assert davalar["muvekkil.phone"].etiket == "Müvekkil kartı · Telefon"
    assert davalar["muvekkil.phone"].grup == "Müvekkil kartı · İletişim"


def test_kayit_defteri_oz_denetimi_bag_kurallari(monkeypatch):
    """Kabul: bildirilmemiş bağ, noktalı düz anahtar, kümesiz çoklu bağ ve kolonsuz ilişki import anında ValueError."""
    from dataclasses import replace
    kaynak = registry.DAVALAR
    phone = kaynak.kolonlar["muvekkil.phone"]

    def _dene(yeni_kaynak, parca):
        monkeypatch.setitem(registry.KAYNAKLAR, "davalar", yeni_kaynak)
        with pytest.raises(ValueError, match=parca):
            registry._kendini_denetle()

    _dene(replace(kaynak, iliskiler=()), "bildirilmemiş")
    _dene(replace(kaynak, kolonlar={**kaynak.kolonlar, "x.y": replace(phone, anahtar="x.y", bag=None)}),
          "nokta yalnız")
    _dene(replace(kaynak, iliskiler=(*kaynak.iliskiler, replace(registry.MUVEKKIL_ILISKISI, anahtar="bos"))),
          "hiç kolonu yok")
    _dene(replace(kaynak, iliskiler=tuple(replace(i, kume=None) for i in kaynak.iliskiler)), "kume")


def test_katalog_bag_alanlari_ve_iliskiler(env):
    """Kabul: kaynak gövdesinde `iliskiler` [{anahtar, etiket, hedef, coklu}], kolonda `bag`; çoklu bağ
    kolonunda kontrol hedef tipinden, `oplar` dolu, `siralanabilir=false`; önerili hedef kolonun önerileri
    HEDEF kaynağın tenant + soft-delete kuralıyla (silinmiş / başka tenant kart yok); liste kolonun
    seçenekleri sabit çekirdek + DISTINCT (sayı yok)."""
    kaynaklar = _katalog(env.client())
    assert kaynaklar["davalar"]["iliskiler"] == [
        {"anahtar": "muvekkil", "etiket": "Müvekkil kartı", "hedef": "muvekkiller", "coklu": True},
        {"anahtar": "foy", "etiket": "Föy", "hedef": "foyler", "coklu": True},
        {"anahtar": "belge", "etiket": "Belge", "hedef": "belgeler", "coklu": True},
    ]
    assert kaynaklar["belgeler"]["iliskiler"][0] == {"anahtar": "dava", "etiket": "Dava", "hedef": "davalar",
                                                     "coklu": False}
    d = _kolonlar(kaynaklar["davalar"])
    assert d["tracking_no"]["bag"] is None and d["muvekkil.phone"]["bag"] == "muvekkil"
    tel = d["muvekkil.phone"]
    assert tel["kontrol"] == "metin_icerir" and tel["turetilmis"] and not tel["siralanabilir"]
    assert tel["oplar"] == ["eq", "ne", "contains", "in", "is_null", "not_null"] and tel["bos_sayisi"] is None
    assert d["muvekkil.vekaletname_tarihi"]["kontrol"] == "tarih_araligi"
    assert d["muvekkil.il"]["oneriler"] == ["Ankara", "Istanbul"]       # Yabanci Kart (T2) / Kapanan Kart yok
    kat = d["muvekkil.category"]
    assert kat["secenek_kaynagi"] == "sabit" and kat["secenek_sayilari"] is None
    assert "Doktor" in kat["secenekler"] and kat["kontrol"] == "coklu_secim"
    # tekil bağ: belgeler'de dava.court veriden liste + boş sayısı + sıralanabilir
    b = _kolonlar(kaynaklar["belgeler"])
    assert b["dava.court"]["bag"] == "dava" and b["dava.court"]["siralanabilir"] and not b["dava.court"]["turetilmis"]
    assert b["dava.court"]["secenek_kaynagi"] == "veri" and isinstance(b["dava.court"]["bos_sayisi"], int)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Kullanıcının örneği: davalar + müvekkil kartı kolonları
# ═══════════════════════════════════════════════════════════════════════════

def test_nisan_sonrasi_davalar_muvekkil_adi_ve_telefonu(env):
    """Kabul (görevin kaynağı): tek rapor — ofis no, müvekkil adları, telefon, cep; Nisan'dan sonra açılanlar.
    Çoklu bağ değerleri tekil + sıralı + ' ; ' ile; boş değer atlanır; silinmiş kart / başka tenant / silinmiş
    dava girmez; tarafsız dava boş hücreyle listede kalır (LEFT anlamı)."""
    r = _onizle(env.client(), _tanim(
        kolonlar=("tracking_no", "muvekkil_adlari", "muvekkil.name", "muvekkil.phone", "muvekkil.mobile_phone"),
        filtreler=[{"alan": "opening_date", "op": "gte", "deger": "2026-04-01"}],
        siralama=[{"alan": "opening_date", "yon": "asc"}],
    ))
    satirlar = _satirlar(r)
    assert list(satirlar) == ["HA.G166.1", "HA.G166.3"]
    c1 = satirlar["HA.G166.1"]
    assert c1["muvekkil.name"] == "Beta Hastanesi ; Dr. Ayse"
    assert c1["muvekkil.phone"] == "0212 111" and c1["muvekkil.mobile_phone"] == "0532 1 ; 0533 2"
    assert satirlar["HA.G166.3"]["muvekkil.phone"] is None and satirlar["HA.G166.3"]["muvekkil.name"] is None
    assert r.json()["kolonlar"][3] == {"anahtar": "muvekkil.phone", "etiket": "Müvekkil kartı · Telefon",
                                       "tip": "metin"}


def test_ad_anahtariyla_bagli_taraf_ve_tekillesme(env):
    """Kabul: `client_id` boş taraf ad anahtarıyla karta bağlanır (c2 → Beta); tekrar eden föy TKU'su tek
    yazılır; tarih/mantık değerleri metne çevrilip birleşir."""
    r = _onizle(env.client(), _tanim(kolonlar=("tracking_no", "muvekkil.mobile_phone", "foy.tku_no", "foy.durum",
                                                "muvekkil.vekaletname_tarihi", "muvekkil.active")))
    s = _satirlar(r)
    assert s["HA.G166.2"]["muvekkil.mobile_phone"] == "0533 2" and s["HA.G166.2"]["foy.tku_no"] == "TKU-9"
    assert s["HA.G166.1"]["foy.tku_no"] == "TKU-1 ; TKU-2" and s["HA.G166.1"]["foy.durum"] == "DERDEST ; MAHZEN"
    assert s["HA.G166.1"]["muvekkil.vekaletname_tarihi"] == "2024-01-15"
    assert s["HA.G166.1"]["muvekkil.active"] in ("1", "true")       # sqlite '1' / Postgres 'true' (metne cast)


def test_coklu_bag_filtreleri_exists_anlami(env):
    """Kabul: filtre = "koşula uyan HERHANGİ bir bağlı kayıt"; `is_null` = dolu değerli bağlı kayıt yok;
    `in` + null = is_null OR in; tarih op'ları hedef tipine göre; silinmiş kart / silinmiş belge sayılmaz."""
    c = env.client()

    def f(alan, op, deger=None):
        return [{"alan": alan, "op": op, **({} if deger is None else {"deger": deger})}]

    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.phone", "contains", "212")))) == {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.phone", "eq", "999")))) == set()      # silinmiş kart
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.phone", "is_null")))) == {"HA.G166.2", "HA.G166.3"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.phone", "not_null")))) == {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.mobile_phone", "not_null")))) == {"HA.G166.1", "HA.G166.2"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.category", "eq", "Doktor")))) == {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.category", "in", ["Doktor", None])))) == \
        {"HA.G166.1", "HA.G166.2", "HA.G166.3"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.category", "in", [None])))) == {"HA.G166.2", "HA.G166.3"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.vekaletname_tarihi", "gte", "2024-01-01")))) == {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.vekaletname_tarihi", "gte", "2024-02-01")))) == set()
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.active", "eq", True)))) == {"HA.G166.1", "HA.G166.2"}
    assert _takip(_onizle(c, _tanim(filtreler=f("foy.durum", "eq", "MAHZEN")))) == {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("belge.belge_turu_adi", "contains", "Silinmiş")))) == set()
    assert _takip(_onizle(c, _tanim(filtreler=f("belge.uploaded_at", "between", ["2026-05-01", "2026-05-31"])))) == \
        {"HA.G166.1"}
    assert _takip(_onizle(c, _tanim(filtreler=f("belge.uploaded_at", "eq", "2026-03-05")))) == {"HA.G166.2"}
    # iki bağ aynı tanımda AND
    assert _takip(_onizle(c, _tanim(filtreler=f("muvekkil.il", "eq", "Ankara") + f("foy.tku_no", "eq", "TKU-9")))) == \
        {"HA.G166.2"}


def test_muvekkilden_davalar_ve_belgeden_dava_tekil_bag(env):
    """Kabul: muvekkiller → dava.* (çoklu; silinmiş dava sayılmaz); belgeler → dava.* tekil (filtre + sıralama
    düz kolon gibi) + muvekkil.* çoklu (cases FROM'da olduğu için aynı bağ).
    Tenant kuralı ANA satırdan gelir (K2); bağlı kayıt tenant'a göre süzülmez — `dava_sayisi` /
    `muvekkil_kategorisi` ile aynı bilinçli davranış (paylaşımlı havuz: kayıtlar `tenant_id=NULL`)."""
    c = env.client()
    r = _onizle(c, _tanim("muvekkiller", ("name", "phone", "dava.tracking_no", "dava.opening_date"),
                          filtreler=[{"alan": "dava.opening_date", "op": "gte", "deger": "2026-04-01"}]))
    s = _satirlar(r, "name")
    assert set(s) == {"Dr. Ayse", "Beta Hastanesi"}
    assert s["Dr. Ayse"]["dava.tracking_no"] == "HA.G166.1 ; HA.G166.4"     # c5 (silinmiş) yok; c4 tenant süzülmez
    assert s["Beta Hastanesi"]["dava.tracking_no"] == "HA.G166.1 ; HA.G166.2"
    assert s["Beta Hastanesi"]["dava.opening_date"] == "2026-03-01 ; 2026-05-01"
    r = _onizle(c, _tanim("belgeler", ("original_filename", "dava.tracking_no", "dava.court", "muvekkil.phone"),
                          filtreler=[{"alan": "dava.opening_date", "op": "gte", "deger": "2026-01-01"},
                                     {"alan": "dava.court", "op": "contains", "deger": "Asliye"}],
                          siralama=[{"alan": "dava.opening_date", "yon": "desc"}]))
    satirlar = r.json()["satirlar"]
    assert [x["original_filename"] for x in satirlar] == ["dilekce.pdf", "karar.pdf"]
    assert satirlar[0]["dava.court"] == "Bursa 1. Asliye Hukuk" and satirlar[0]["muvekkil.phone"] == "0212 111"


def test_dogrulama_422_bagli_kolon_kurallari(env):
    """Kabul: çoklu bağ kolonu sıralanamaz; katalog dışı `muvekkil.dava_sayisi` / `muvekkil.notes` / ikinci
    derece anahtar 422; op alt kümesi hedef tipinden (liste kolonda contains yok)."""
    c = env.client()
    _422(_onizle(c, _tanim(siralama=[{"alan": "muvekkil.phone", "yon": "asc"}])), "siralama[0]")
    for anahtar in ("muvekkil.dava_sayisi", "muvekkil.notes", "muvekkil.tc_no", "muvekkil.dava.tracking_no", "foy.case_id"):
        _422(_onizle(c, _tanim(kolonlar=("tracking_no", anahtar))), "kolonlar[1]")
    _422(_onizle(c, _tanim(filtreler=[{"alan": "muvekkil.category", "op": "contains", "deger": "Dok"}])), "filtreler[0]")
    _422(_onizle(c, _tanim(filtreler=[{"alan": "belge.uploaded_at", "op": "gte", "deger": "dün"}])), "filtreler[0]")
    # tekil bağ: sıralama serbest
    assert _onizle(c, _tanim("foyler", ("sistem_no", "dava.court"),
                             siralama=[{"alan": "dava.court", "yon": "asc"}])).status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 3. Asistan: katalog metni + aynı doğrulama yolu + prompt kuralı
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_katalog_metni_iliski_satirlari():
    """Kabul: bağlı kolonlar tek tek gömülmez (prompt gürültüsü); ilişki başına bir satır (önek, hedef,
    hariç listesi, çoklu/tekil şerhi); prompt kuralı bağlı kolonu anlatır."""
    metin = asistan.katalog_metni()
    assert "\nmuvekkil.phone · " not in metin and "\ndava.tracking_no · " not in metin
    assert ("muvekkil.<kolon> · Müvekkil kartı · BAĞLI: 'muvekkiller' kaynağının kolonları 'muvekkil.' önekiyle "
            "(ör. muvekkil.name) · hariç: dava_sayisi · çoklu:") in metin
    assert "dava.<kolon> · Dava · BAĞLI: 'davalar' kaynağının kolonları 'dava.' önekiyle (ör. dava.tracking_no) · " \
           "tekil: filtre/sıralama düz kolon gibi" in metin
    assert "hariç: muvekkil_adlari, karsi_taraf_adlari, sigortali_adlari, muvekkil_kategorisi, foy_sayisi, belge_sayisi" in metin
    davalar_blogu = metin.split("## muvekkiller")[0]
    assert davalar_blogu.count("BAĞLI:") == 3
    talimat = get_rapor_asistani_instruction(metin, "2026-09-10")
    assert "BAĞLI KAYNAK KOLONLARI" in talimat and "muvekkil.phone" in talimat


def test_asistan_tanimi_bagli_kolonla_ayni_dogrulamadan_gecer():
    """Kabul (K6): asistanın ürettiği `muvekkil.phone` kolonu / tarih filtresi manuel yoldan geçer; sıralama
    çoklu bağda RaporDogrulamaHatasi."""
    t = AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no", "muvekkil_adlari", "muvekkil.phone"],
                      filtreler=[AsistanFiltre(alan="opening_date", op="gte", deger="2026-04-01"),
                                 AsistanFiltre(alan="muvekkil.vekaletname_tarihi", op="between",
                                               degerler=["2024-01-01", "2024-12-31"]),
                                 AsistanFiltre(alan="muvekkil.category", op="in", degerler=["Doktor", "(boş)"])])
    rt = asistan.tanimi_dogrula(t)
    assert isinstance(rt, RaporTanimi) and rt.kolonlar[-1] == "muvekkil.phone"
    assert rt.filtreler[1].deger == ["2024-01-01", "2024-12-31"] and rt.filtreler[2].deger == ["Doktor", None]
    with pytest.raises(RaporDogrulamaHatasi):
        asistan.tanimi_dogrula(AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                                             siralama=[{"alan": "muvekkil.phone", "yon": "asc"}]))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Migrasyon: ad anahtarı ifade index'i `_ad_anahtari` ile birebir
# ═══════════════════════════════════════════════════════════════════════════

def test_ad_anahtari_index_i_registry_ifadesiyle_birebir():
    """Kabul: iki index koşulsuz ("index", ...) op'unda, IF NOT EXISTS; DDL'deki ifade `_ad_anahtari`nin
    Postgres derlemesiyle aynı (planlayıcı ancak o zaman kullanır — ölçüm 21.9 s → 0.5 s)."""
    sqller = [sql for op in database._MIGRATIONS if op[0] == "index" for sql in op[2]]
    for tablo, ad, kolon in (("clients", "idx_clients_ad_anahtari", models.Client.name),
                             ("case_parties", "idx_case_parties_ad_anahtari", models.CaseParty.name)):
        eslesen = [s for s in sqller if f" {ad} " in s]
        assert len(eslesen) == 1 and "IF NOT EXISTS" in eslesen[0] and f"ON {tablo} " in eslesen[0]
        derlenen = str(registry._ad_anahtari(kolon).compile(dialect=postgresql.dialect(),
                                                            compile_kwargs={"literal_binds": True}))
        ifade = derlenen.replace(f"{tablo}.name", "name")
        assert f"(({ifade}))" in eslesen[0], (eslesen[0], ifade)


def test_tarih_kosulu_tek_kaynak_motor_ve_bagli_kolon():
    """Kabul: motorun tarih koşulu registry.tarih_kosulu'na delege eder (kopya yok); DateTime kolonda gün aralığı."""
    import inspect
    assert "registry.tarih_kosulu" in inspect.getsource(motor._tarih_kosulu)
    kosul = str(registry.tarih_kosulu(models.CaseDocument.uploaded_at, True, "eq", dt.date(2026, 5, 2)))
    assert ">=" in kosul and "<" in kosul
