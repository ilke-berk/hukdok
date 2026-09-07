"""G137 — Rapor kataloğu genişlemesi (plan §4.2): kolonda `grup`/`kontrol`/`oneriler`,
kaynakta `hizli_filtreler`/`kolon_setleri`; taraf bağlantılı dört dava filtresi
(EXISTS `case_parties` → `clients`, tenant + soft-delete kurallı); türetilmişte
op alt kümesi; katalog 60 sn önbelleği (`routes/reports._katalogu_getir`);
asistan katalog metni yeni alanları gömmez.

Düzen `test_g130_rapor_temeli.env` reçetesiyle aynı (sqlite StaticPool, gerçek
`require_admin`), veri bu görevin senaryolarına göre: aynı adı taşıyan CLIENT ve
COUNTER taraf, Sigortalı rolü, silinmiş müvekkil kartı, başka tenant / silinmiş dava.
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from schemas_rapor import TIP_OPLARI, RaporDogrulamaHatasi, RaporTanimi
from services.rapor import asistan, motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
CATALOG = "/api/reports/catalog"
PREVIEW = "/api/reports/preview"
SILINDI = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)

# G141: her kaynağa sanal `arama` kolonunun grubu "Arama" eklendi (plan §5.2).
GRUPLAR = {
    "davalar": ("Arama", "Kimlik", "Taraflar", "Mahkeme ve konu", "Tarihler", "Tutarlar", "Karar ve aşama", "Tıbbi",
                "Aktarım", "Sistem"),
    "muvekkiller": ("Arama", "Kimlik", "İletişim", "Vekalet", "Sınıflandırma", "Sistem"),
    "belgeler": ("Arama", "Belge", "Dava", "Yükleme", "Sistem"),
    "foyler": ("Arama", "Kimlik", "Sınıflandırma", "Kapsam", "Sistem"),
}
KONTROL = {"tarih": "tarih_araligi", "liste": "coklu_secim", "metin": "metin_icerir", "sayi": "sayi_araligi",
           "para": "sayi_araligi", "mantik": "mantik"}
# G141 (plan §5.2): işaretli metin kolonlar bu küçük veride eşik ALTINDA kalır → `secenekler` (veriden,
# sıklık sıralı) + `kontrol=coklu_secim`, `oneriler=None`; öneri katmanı yalnız işaretsiz önerili kolonlarda.
VERIDEN = {
    "davalar": {"responsible_lawyer_name", "uyap_lawyer_name", "court", "judicial_unit", "sub_type"},
    "muvekkiller": {"il", "specialty"},
    "belgeler": {"uploaded_by", "belge_turu_adi"},
    "foyler": set(),
}
ONERILI = {
    "davalar": {"muvekkil_adlari", "karsi_taraf_adlari", "sigortali_adlari"},
    "muvekkiller": {"sektor", "noterlik"},
    "belgeler": set(),
    "foyler": set(),
}


# ═══════════════════════════════════════════════════════════════════════════
# Düzen
# ═══════════════════════════════════════════════════════════════════════════

def _veri_yukle(db):
    c1 = models.Case(tracking_no="HA.G137.1", tenant_id=T1, status="DERDEST", subject="Anadolu davali",
                     court="Bursa 1. Asliye Hukuk", responsible_lawyer_name="Av. Ali", opening_date=dt.date(2025, 3, 1))
    c2 = models.Case(tracking_no="HA.G137.2", tenant_id=None, status="KARAR", subject="Anadolu karsi taraf",
                     court="Ankara 2. Asliye Hukuk", responsible_lawyer_name="Av. Veli")
    c3 = models.Case(tracking_no="HA.G137.3", tenant_id=T1, status="DERDEST", subject="Silinmis kartli muvekkil",
                     court="", responsible_lawyer_name=None)
    c4 = models.Case(tracking_no="HA.G137.4", tenant_id=T2, status="DERDEST", subject="Baska tenant",
                     court="Izmir 3. Asliye Hukuk", responsible_lawyer_name="Av. Yabanci")
    c5 = models.Case(tracking_no="HA.G137.5", tenant_id=T1, status="DERDEST", subject="Silinmis dava",
                     court="Silinmis Mahkeme", responsible_lawyer_name="Av. Silinmis", deleted_at=SILINDI,
                     deleted_by=ADMIN)
    c6 = models.Case(tracking_no="HA.G137.6", tenant_id=T1, status="DANIŞ", subject="Tarafsiz")
    db.add_all([c1, c2, c3, c4, c5, c6])
    db.flush()

    m_anadolu = models.Client(name="Anadolu Hastanesi", tenant_id=T1, category="Özel Hastane")
    m_dr = models.Client(name="Dr. Ayşe", tenant_id=None, category="Doktor")
    m_silinmis = models.Client(name="Kapanan Hastane", tenant_id=T1, category="Özel Hastane", deleted_at=SILINDI)
    m_kategorisiz = models.Client(name="Kategorisiz Cari", tenant_id=T1, category=None)
    m_baska = models.Client(name="Baska Tenant Cari", tenant_id=T2, category="Kurum")
    db.add_all([m_anadolu, m_dr, m_silinmis, m_kategorisiz, m_baska])
    db.flush()

    P = models.CaseParty
    db.add_all([
        # c1: müvekkil Anadolu Hastanesi (Özel Hastane) + Dr. Ayşe; karşı taraf Hasta B; sigortalı (THIRD)
        P(case_id=c1.id, client_id=m_anadolu.id, name="Anadolu Hastanesi", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, client_id=m_dr.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
        P(case_id=c1.id, name="Hasta B", role="Davacı", party_type="COUNTER"),
        P(case_id=c1.id, name="Sigortalı Klinik", role="Sigortalı", party_type="THIRD"),
        # c2: müvekkil Dr. Ayşe; KARŞI taraf adı "Anadolu Sigorta" — müvekkil filtresi bunu BULMAMALI
        P(case_id=c2.id, client_id=m_dr.id, name="Dr. Ayşe", role="Davalı", party_type="CLIENT"),
        P(case_id=c2.id, name="Anadolu Sigorta", role="Davacı", party_type="COUNTER"),
        # c3: müvekkil kartı SİLİNMİŞ (Özel Hastane) + kategorisiz canlı kart
        P(case_id=c3.id, client_id=m_silinmis.id, name="Kapanan Hastane", role="Davalı", party_type="CLIENT"),
        P(case_id=c3.id, client_id=m_kategorisiz.id, name="Kategorisiz Cari", role="Davalı", party_type="CLIENT"),
        # c4: başka tenant — adı Anadolu geçen müvekkil ve Sigortalı rolü (T1'e sızmamalı)
        P(case_id=c4.id, client_id=m_baska.id, name="Anadolu Yabanci", role="Davalı", party_type="CLIENT"),
        P(case_id=c4.id, name="Yabanci Sigortali", role="Sigortalı", party_type="THIRD"),
        # c5: silinmiş dava — taraf adı önerilere GİRMEMELİ
        P(case_id=c5.id, client_id=m_anadolu.id, name="Silinmis Dava Muvekkili", role="Davalı", party_type="CLIENT"),
        # Sigortalı rolü CLIENT tarafta da olabilir (her party_type); kartsız taraf
        P(case_id=c2.id, name="Sigortalı Doktor Ltd", role="Sigortalı", party_type="CLIENT"),
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


def _takip(cevap):
    assert cevap.status_code == 200, cevap.text
    return {s["tracking_no"] for s in cevap.json()["satirlar"]}


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
# 1. Katalog şekli: grup / kontrol / oneriler / hizli_filtreler / kolon_setleri
# ═══════════════════════════════════════════════════════════════════════════

def test_katalog_yeni_alanlarin_sekli(env):
    """Kabul: her kolonda `grup` + `kontrol` + `oneriler`/`oneri_kesik`; her kaynakta
    `hizli_filtreler` (+ G141 `sunum`/`etiket`) + `kolon_setleri` (plan §4.2 şekli).
    G141: veriden liste kolonlar eşik altında `secenekler` taşır, `oneriler` yalnız işaretsiz önerililerde."""
    kaynaklar = _katalog(env.client())
    assert set(kaynaklar) == set(GRUPLAR)
    for anahtar, kaynak in kaynaklar.items():
        assert isinstance(kaynak["hizli_filtreler"], list) and kaynak["hizli_filtreler"]
        assert isinstance(kaynak["kolon_setleri"], list) and kaynak["kolon_setleri"]
        for hf in kaynak["hizli_filtreler"]:
            assert set(hf) == {"alan", "alternatifler", "sunum", "etiket"} and isinstance(hf["alternatifler"], list)
        for ks in kaynak["kolon_setleri"]:
            assert set(ks) == {"ad", "kolonlar"} and ks["ad"] and ks["kolonlar"]
        for k in kaynak["kolonlar"]:
            assert k["grup"], f"{anahtar}.{k['anahtar']} grupsuz"
            assert k["grup"] in GRUPLAR[anahtar], f"{anahtar}.{k['anahtar']} grup kapalı küme dışı: {k['grup']}"
            assert isinstance(k["oneri_kesik"], bool)
            if k["anahtar"] in ONERILI[anahtar]:
                assert isinstance(k["oneriler"], list)
            else:
                assert k["oneriler"] is None
            if k["anahtar"] in VERIDEN[anahtar]:
                assert isinstance(k["secenekler"], list) and k["secenek_kaynagi"] == "veri", (anahtar, k["anahtar"])


def test_katalog_grup_kumesi_kaynaga_gore_kapali_ve_dolu(env):
    """Her kaynakta plan §4.2 gruplarının HEPSİ en az bir kolonla kullanılır (boş grup yok)."""
    kaynaklar = _katalog(env.client())
    for anahtar, gruplar in GRUPLAR.items():
        kullanilan = {k["grup"] for k in kaynaklar[anahtar]["kolonlar"]}
        assert kullanilan == set(gruplar), (anahtar, kullanilan ^ set(gruplar))
    davalar = _kolonlar(kaynaklar["davalar"])
    assert davalar["muvekkil_adlari"]["grup"] == "Taraflar" and davalar["sigortali_adlari"]["grup"] == "Taraflar"
    assert davalar["maddi_tazminat"]["grup"] == "Tutarlar" and davalar["karar_tarihi"]["grup"] == "Karar ve aşama"
    assert davalar["tibbi_olay"]["grup"] == "Tıbbi" and davalar["tku_no"]["grup"] == "Aktarım"


def test_katalog_kontrol_tip_eslemesi(env):
    """`kontrol` tipten türetilir; filtrelenemeyen kolonda null. G141: veriden liste kolon eşik altında
    (`secenek_kaynagi="veri"`) tip metin kalsa da `coklu_secim`."""
    kaynaklar = _katalog(env.client())
    for kaynak in kaynaklar.values():
        for k in kaynak["kolonlar"]:
            if not k["filtrelenebilir"]:
                assert k["kontrol"] is None, (kaynak["anahtar"], k["anahtar"])
            elif k["secenek_kaynagi"] == "veri":
                assert k["tip"] == "metin" and k["kontrol"] == "coklu_secim", (kaynak["anahtar"], k["anahtar"])
            else:
                assert k["kontrol"] == KONTROL[k["tip"]], (kaynak["anahtar"], k["anahtar"])
    davalar = _kolonlar(kaynaklar["davalar"])
    assert davalar["opening_date"]["kontrol"] == "tarih_araligi"
    assert davalar["status"]["kontrol"] == "coklu_secim"
    assert davalar["court"]["kontrol"] == "coklu_secim" and davalar["court"]["tip"] == "metin"
    assert davalar["muvekkil_adlari"]["kontrol"] == "metin_icerir"
    assert davalar["muvekkil_kategorisi"]["kontrol"] == "coklu_secim"
    assert davalar["maddi_tazminat"]["kontrol"] == "sayi_araligi"
    assert davalar["active"]["kontrol"] == "mantik"
    # Kolon başına izinli op listesi (G138 combobox kararı: `eq` yoksa seçim `contains` gönderir)
    assert davalar["muvekkil_adlari"]["oplar"] == ["contains", "is_null", "not_null"]
    assert "eq" in davalar["responsible_lawyer_name"]["oplar"]
    assert davalar["muvekkil_kategorisi"]["oplar"] == ["eq", "in", "is_null"]
    for kaynak in kaynaklar.values():
        for k in kaynak["kolonlar"]:
            assert (k["oplar"] == []) == (not k["filtrelenebilir"]), (kaynak["anahtar"], k["anahtar"])
    assert davalar["foy_sayisi"]["kontrol"] is None and davalar["belge_sayisi"]["kontrol"] is None
    assert _kolonlar(kaynaklar["belgeler"])["dava_subject"]["kontrol"] is None


def test_katalog_hizli_filtreler_plan_listesi(env):
    """Plan §4.2 hızlı filtre listeleri, sıralı; her anahtar katalogda ve filtrelenebilir;
    alternatifler yalnız tarih kontrolünde."""
    kaynaklar = _katalog(env.client())
    # G141 (plan §5.2): her listede `arama` başa; Müvekkiller şeridi yeniden kuruldu (test_g141 sunumları doğrular)
    beklenen = {
        "davalar": ["arama", "opening_date", "status", "responsible_lawyer_name", "court", "muvekkil_adlari",
                    "muvekkil_kategorisi", "hizmet_turu", "maddi_tazminat"],
        "muvekkiller": ["arama", "category", "il", "specialty", "dava_sayisi", "email", "mobile_phone"],
        "belgeler": ["arama", "uploaded_at", "belge_turu_adi", "uploaded_by", "link_mode"],
        "foyler": ["arama", "durum", "hizmet_turu", "muvekkil_tipi", "kapsam_durumu"],
    }
    for anahtar, liste in beklenen.items():
        kaynak = kaynaklar[anahtar]
        kolonlar = _kolonlar(kaynak)
        assert [hf["alan"] for hf in kaynak["hizli_filtreler"]] == liste
        for hf in kaynak["hizli_filtreler"]:
            for alan in (hf["alan"], *hf["alternatifler"]):
                assert kolonlar[alan]["filtrelenebilir"], (anahtar, alan)
            if hf["alternatifler"]:
                assert kolonlar[hf["alan"]]["kontrol"] == "tarih_araligi"
    acilis = kaynaklar["davalar"]["hizli_filtreler"][1]
    assert acilis == {"alan": "opening_date", "alternatifler": ["karar_tarihi", "kesinlesme_tarihi", "created_at"],
                      "sunum": "varsayilan", "etiket": None}


def test_katalog_kolon_setleri_plan_listesi(env):
    """Plan §4.2 kolon setleri; "Temel" = varsayılan; setlerdeki kolonlar katalogda."""
    kaynaklar = _katalog(env.client())
    for kaynak in kaynaklar.values():
        kolonlar = _kolonlar(kaynak)
        setler = {ks["ad"]: ks["kolonlar"] for ks in kaynak["kolon_setleri"]}
        assert setler["Temel"] == kaynak["varsayilan_kolonlar"]
        for ad, liste in setler.items():
            assert set(liste) <= set(kolonlar), (kaynak["anahtar"], ad)
    dava_setleri = {ks["ad"]: ks["kolonlar"] for ks in kaynaklar["davalar"]["kolon_setleri"]}
    assert list(dava_setleri) == ["Temel", "Karar takibi", "Tazminat", "Taraflar"]
    assert dava_setleri["Karar takibi"] == ["tracking_no", "esas_no", "court", "status", "case_stage", "karar_tarihi",
                                            "karar_turu", "karar_lehine", "kesinlesme_tarihi"]
    assert dava_setleri["Tazminat"] == ["tracking_no", "muvekkil_adlari", "court", "maddi_tazminat", "manevi_tazminat",
                                        "hukmedilen_toplam", "dava_degeri", "para_birimi"]
    assert dava_setleri["Taraflar"] == ["tracking_no", "muvekkil_adlari", "karsi_taraf_adlari", "sigortali_adlari",
                                        "muvekkil_kategorisi", "responsible_lawyer_name"]
    muv = {ks["ad"]: ks["kolonlar"] for ks in kaynaklar["muvekkiller"]["kolon_setleri"]}
    assert list(muv) == ["Temel", "İletişim", "Vekalet"]
    assert muv["İletişim"] == ["name", "category", "phone", "mobile_phone", "email", "address", "il"]
    assert muv["Vekalet"] == ["name", "vekalet_no", "buro_vekalet_no", "vekaletname_tarihi", "gecerlilik_tarihi",
                              "noterlik"]


def test_katalog_yeni_taraf_kolonlari(env):
    """`sigortali_adlari` (metin) ve `muvekkil_kategorisi` (liste, seçenek = seed ∪ clients.category DISTINCT)
    katalogda; dördü de filtrelenebilir, sıralanamaz, türetilmiş."""
    davalar = _kolonlar(_katalog(env.client())["davalar"])
    for anahtar in ("muvekkil_adlari", "karsi_taraf_adlari", "sigortali_adlari", "muvekkil_kategorisi"):
        k = davalar[anahtar]
        assert k["turetilmis"] and k["filtrelenebilir"] and not k["siralanabilir"], anahtar
    assert davalar["sigortali_adlari"]["tip"] == "metin" and davalar["sigortali_adlari"]["etiket"] == "Sigortalılar"
    kategori = davalar["muvekkil_kategorisi"]
    assert kategori["tip"] == "liste" and kategori["etiket"] == "Müvekkil Kategorisi"
    assert kategori["secenekler"][:2] == ["Doktor", "Sağlık Çalışanı"]
    assert "Özel Hastane" in kategori["secenekler"] and "Kurum" in kategori["secenekler"]
    assert kategori["oneriler"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Öneriler: DISTINCT, boş hariç, tenant + soft-delete, 300 kesme
# ═══════════════════════════════════════════════════════════════════════════

def test_oneriler_onerili_kolonlar_ve_kurallar(env):
    """Kabul: öneriler yalnız `onerili` metin kolonlarda; DISTINCT; boş/NULL hariç; silinmiş dava ve
    başka tenant hariç; NULL tenant (legacy) dahil. G141: avukat/mahkeme artık veriden seçenek
    (aynı kurallar; sıklık eşitliğinde ad sırası)."""
    kaynaklar = _katalog(env.client())
    for anahtar, onerili in ONERILI.items():
        kolonlar = _kolonlar(kaynaklar[anahtar])
        assert {a for a, k in kolonlar.items() if k["oneriler"] is not None} == onerili, anahtar
        assert {a for a, k in kolonlar.items() if k["secenek_kaynagi"] == "veri"} == VERIDEN[anahtar], anahtar
    davalar = _kolonlar(kaynaklar["davalar"])
    assert davalar["responsible_lawyer_name"]["secenekler"] == ["Av. Ali", "Av. Veli"]
    assert davalar["court"]["secenekler"] == ["Ankara 2. Asliye Hukuk", "Bursa 1. Asliye Hukuk"]
    assert davalar["responsible_lawyer_name"]["oneriler"] is None
    assert davalar["responsible_lawyer_name"]["oneri_kesik"] is False
    # Taraf adı önerileri: ilgili party_type/role, silinmiş dava (c5) ve başka tenant (c4) dışarıda
    assert davalar["muvekkil_adlari"]["oneriler"] == ["Anadolu Hastanesi", "Dr. Ayşe", "Kapanan Hastane",
                                                      "Kategorisiz Cari", "Sigortalı Doktor Ltd"]
    assert davalar["karsi_taraf_adlari"]["oneriler"] == ["Anadolu Sigorta", "Hasta B"]
    assert davalar["sigortali_adlari"]["oneriler"] == ["Sigortalı Doktor Ltd", "Sigortalı Klinik"]


def test_oneriler_tenant_kurali(env):
    """Başka tenant'ın yöneticisi kendi + legacy NULL kayıtların önerilerini görür."""
    davalar = _kolonlar(_katalog(env.client(tid=T2))["davalar"])
    assert davalar["responsible_lawyer_name"]["secenekler"] == ["Av. Veli", "Av. Yabanci"]
    assert davalar["muvekkil_adlari"]["oneriler"] == ["Anadolu Yabanci", "Dr. Ayşe", "Sigortalı Doktor Ltd"]
    assert davalar["sigortali_adlari"]["oneriler"] == ["Sigortalı Doktor Ltd", "Yabanci Sigortali"]


def test_oneriler_muvekkil_ve_belge_kaynaklari_soft_delete(env):
    db = env.db()
    try:
        db.add_all([
            models.Client(name="Izmirli", tenant_id=T1, il="İzmir", sektor="Sağlık"),
            models.Client(name="Bursali", tenant_id=None, il="Bursa", sektor=""),
            models.Client(name="Silinmis Izmirli", tenant_id=T1, il="Silinmis Il", deleted_at=SILINDI),
        ])
        c1 = db.query(models.Case).filter_by(tracking_no="HA.G137.1").one()
        c5 = db.query(models.Case).filter_by(tracking_no="HA.G137.5").one()
        db.add_all([
            models.CaseDocument(case_id=c1.id, original_filename="a.pdf", stored_filename="a", uploaded_by="Ayşe",
                                belge_turu_adi="Dilekçe"),
            models.CaseDocument(case_id=c1.id, original_filename="b.pdf", stored_filename="b", uploaded_by="Ayşe",
                                belge_turu_adi="Silinmis Belge Turu", deleted_at=SILINDI),
            models.CaseDocument(case_id=c5.id, original_filename="c.pdf", stored_filename="c", uploaded_by="Silinmis Dava",
                                belge_turu_adi="Tebligat"),
        ])
        db.commit()
    finally:
        db.close()
    kaynaklar = _katalog(env.client())
    muv = _kolonlar(kaynaklar["muvekkiller"])
    assert muv["il"]["secenekler"] == ["Bursa", "İzmir"]      # G141 veriden seçenek; silinmiş kart dışarıda
    assert muv["sektor"]["oneriler"] == ["Sağlık"]          # boş string hariç
    belge = _kolonlar(kaynaklar["belgeler"])
    assert belge["uploaded_by"]["secenekler"] == ["Ayşe"]     # silinmiş dava dışarıda
    assert belge["belge_turu_adi"]["secenekler"] == ["Dilekçe"]   # silinmiş belge dışarıda


def test_oneriler_300_kesme_ve_bayrak(env):
    db = env.db()
    try:
        db.add_all([models.Case(tracking_no=f"HA.K.{i:04d}", tenant_id=T1, status="DERDEST",
                                judicial_unit=f"Birim {i:04d}") for i in range(registry.ONERI_MAX + 5)])
        # tekrar eden değer DISTINCT'e girmez
        db.add(models.Case(tracking_no="HA.K.tekrar", tenant_id=T1, status="DERDEST", judicial_unit="Birim 0000"))
        db.commit()
    finally:
        db.close()
    davalar = _kolonlar(_katalog(env.client())["davalar"])
    birim = davalar["judicial_unit"]
    assert len(birim["oneriler"]) == registry.ONERI_MAX and birim["oneri_kesik"] is True
    assert birim["oneriler"][0] == "Birim 0000" and len(set(birim["oneriler"])) == registry.ONERI_MAX
    assert davalar["court"]["oneri_kesik"] is False


def test_onerileri_getir_db_yokken_bos(env):
    kolon = registry.DAVALAR.kolonlar["court"]
    assert registry.onerileri_getir(registry.DAVALAR, kolon, None, T1) == ([], False)
    assert registry.onerileri_getir(registry.DAVALAR, registry.DAVALAR.kolonlar["subject"], None, T1) == (None, False)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Taraf bağlantılı filtreler (EXISTS)
# ═══════════════════════════════════════════════════════════════════════════

def test_muvekkil_adi_contains_yalniz_client_tarafi(env):
    """Kabul: `muvekkil_adlari contains "Anadolu"` yalnız CLIENT tarafında bu adı taşıyan davaları döner —
    karşı tarafı "Anadolu Sigorta" olan c2 GELMEZ; başka tenant (c4) ve silinmiş dava (c5) gelmez."""
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": "anadolu"}]))
    assert _takip(r) == {"HA.G137.1"}
    r = _onizle(env.client(), _tanim(filtreler=[{"alan": "karsi_taraf_adlari", "op": "contains", "deger": "Anadolu"}]))
    assert _takip(r) == {"HA.G137.2"}
    # aynı ad başka tenant'ta: o tenant görür, T1 görmez
    r = _onizle(env.client(tid=T2), _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": "Anadolu"}]))
    assert _takip(r) == {"HA.G137.4"}


def test_taraf_filtresi_is_null_not_null(env):
    client = env.client()
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "is_null"}]))
    assert _takip(r) == {"HA.G137.6"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "karsi_taraf_adlari", "op": "not_null"}]))
    assert _takip(r) == {"HA.G137.1", "HA.G137.2"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "karsi_taraf_adlari", "op": "is_null"}]))
    assert _takip(r) == {"HA.G137.3", "HA.G137.6"}


def test_sigortali_adlari_role_bazli(env):
    """`sigortali_adlari` `role='Sigortalı'` — party_type'tan bağımsız (THIRD ve CLIENT)."""
    client = env.client()
    r = _onizle(client, _tanim(kolonlar=("tracking_no", "sigortali_adlari"),
                               filtreler=[{"alan": "sigortali_adlari", "op": "not_null"}],
                               siralama=[{"alan": "tracking_no", "yon": "asc"}]))
    assert r.status_code == 200, r.text
    satirlar = r.json()["satirlar"]
    assert [s["tracking_no"] for s in satirlar] == ["HA.G137.1", "HA.G137.2"]
    assert satirlar[0]["sigortali_adlari"] == "Sigortalı Klinik" and satirlar[1]["sigortali_adlari"] == "Sigortalı Doktor Ltd"
    r = _onizle(client, _tanim(filtreler=[{"alan": "sigortali_adlari", "op": "contains", "deger": "klinik"}]))
    assert _takip(r) == {"HA.G137.1"}
    # Sigortalı Klinik THIRD taraftır: müvekkil/karşı taraf filtresi onu bulmaz
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": "Klinik"}]))
    assert _takip(r) == set()


def test_muvekkil_kategorisi_silinmis_karti_saymaz(env):
    """Kabul: `muvekkil_kategorisi in ["Özel Hastane"]` müvekkil kartı silinmiş tarafı (c3) saymaz;
    tenant kuralı cases üzerinden (c4 T1'de görünmez)."""
    client = env.client()
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_kategorisi", "op": "in", "deger": ["Özel Hastane"]}]))
    assert _takip(r) == {"HA.G137.1"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_kategorisi", "op": "eq", "deger": "Doktor"}]))
    assert _takip(r) == {"HA.G137.1", "HA.G137.2"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_kategorisi", "op": "in", "deger": ["Kurum"]}]))
    assert _takip(r) == set()
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_kategorisi", "op": "is_null"}]))
    assert _takip(r) == {"HA.G137.3", "HA.G137.6"}       # c3: silinmiş kart + kategorisiz kart → kategorisiz sayılır
    # seçim ifadesi: CLIENT tarafların canlı kart kategorileri
    r = _onizle(client, _tanim(kolonlar=("tracking_no", "muvekkil_kategorisi"),
                               siralama=[{"alan": "tracking_no", "yon": "asc"}]))
    kategoriler = {s["tracking_no"]: s["muvekkil_kategorisi"] for s in r.json()["satirlar"]}
    assert set(kategoriler["HA.G137.1"].split(registry.AYRAC)) == {"Özel Hastane", "Doktor"}
    assert kategoriler["HA.G137.2"] == "Doktor" and kategoriler["HA.G137.3"] is None


def test_taraf_contains_ilike_kacisi_motor_yardimcisiyla(env):
    """`%`/`_` kaçışı motorun atom koşulundan gelir: joker istemciden geçmez."""
    db = env.db()
    try:
        c1 = db.query(models.Case).filter_by(tracking_no="HA.G137.1").one()
        db.add(models.CaseParty(case_id=c1.id, name="Yüzde %100 A.Ş.", role="Davalı", party_type="CLIENT"))
        db.commit()
    finally:
        db.close()
    client = env.client()
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": "%100"}]))
    assert _takip(r) == {"HA.G137.1"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": "a%"}]))
    assert _takip(r) == set()
    zehir = "x' OR 1=1 --"
    tanim = RaporTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                        filtreler=[{"alan": "muvekkil_adlari", "op": "contains", "deger": zehir},
                                   {"alan": "muvekkil_kategorisi", "op": "in", "deger": [zehir]}])
    derlenmis = motor.sorgu_kur(tanim, T1).compile()
    assert zehir not in str(derlenmis)
    assert "EXISTS" in str(derlenmis).upper()


def test_kart_baglari_client_id_yoksa_ad_anahtariyla_kurulur(env):
    """Kullanıcı bulgusu (07.09): canlı veride 16.192 CLIENT taraf satırından 9'unda `client_id` dolu,
    bağ fiilen isimle; yalnız id ile bağ "Dava Sayısı"nı herkes için 0 gösteriyordu. Kural
    (`registry.kart_eslesmesi`): id doluysa YALNIZ id; boşsa ad anahtarı (upper + trim + İ→I)."""
    with env.db() as db:
        m_dr = db.query(models.Client).filter_by(name="Dr. Ayşe").one()
        m_yeni = models.Client(name="İbrahim Yılmaz", tenant_id=T1, category="Doktor")
        db.add(m_yeni)
        db.flush()
        c1 = db.query(models.Case).filter_by(tracking_no="HA.G137.1").one()
        c6 = db.query(models.Case).filter_by(tracking_no="HA.G137.6").one()
        db.add_all([
            # client_id YOK, ad farklı yazımla eşleşir (küçük/büyük + İ/I + boşluk) → sayılır
            models.CaseParty(case_id=c6.id, name=" ibrahim yilmaz".replace("i", "İ", 1), role="Davalı",
                             party_type="CLIENT"),
            # client_id BAŞKA karta bağlı ama adı aynı → isimle SAYILMAZ (id öncelikli)
            models.CaseParty(case_id=c1.id, client_id=m_dr.id, name="İbrahim Yılmaz", role="Davalı",
                             party_type="CLIENT"),
            # aynı ad ama KARŞI taraf → sayılmaz
            models.CaseParty(case_id=c1.id, name="İbrahim Yılmaz", role="Davacı", party_type="COUNTER"),
        ])
        db.commit()
    env.route.katalog_onbellegini_sifirla()
    client = env.client()
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name", "dava_sayisi"),
                               filtreler=[{"alan": "name", "op": "eq", "deger": "İbrahim Yılmaz"}]))
    assert r.status_code == 200, r.text
    assert r.json()["satirlar"] == [{"name": "İbrahim Yılmaz", "dava_sayisi": 1}]
    # Dava kaynağı: c6'nın müvekkil kategorisi artık isimle bağlanan karttan gelir
    r = _onizle(client, _tanim(kolonlar=("tracking_no", "muvekkil_kategorisi"),
                               filtreler=[{"alan": "tracking_no", "op": "eq", "deger": "HA.G137.6"}]))
    assert r.json()["satirlar"] == [{"tracking_no": "HA.G137.6", "muvekkil_kategorisi": "Doktor"}]
    r = _onizle(client, _tanim(filtreler=[{"alan": "muvekkil_kategorisi", "op": "eq", "deger": "Doktor"}]))
    assert {s["tracking_no"] for s in r.json()["satirlar"]} == {"HA.G137.1", "HA.G137.2", "HA.G137.6"}


def test_dava_sayisi_hizli_filtresi_karsilastirilir(env):
    """Müvekkiller hızlı filtresi `dava_sayisi` (plan §4.2): COUNT alt sorgusu doğrudan süzülür."""
    client = env.client()
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name",),
                               filtreler=[{"alan": "dava_sayisi", "op": "gte", "deger": 2}]))
    assert {s["name"] for s in r.json()["satirlar"]} == {"Dr. Ayşe"}            # c1 + c2; Anadolu: c1 (c5 silinmiş)
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name",),
                               filtreler=[{"alan": "dava_sayisi", "op": "lte", "deger": 1}]))
    assert {s["name"] for s in r.json()["satirlar"]} == {"Anadolu Hastanesi", "Kategorisiz Cari"}
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name",),
                               filtreler=[{"alan": "dava_sayisi", "op": "eq", "deger": 0}]))
    assert {s["name"] for s in r.json()["satirlar"]} == set()
    # COUNT hiç NULL değil: §4.3 "boş olanlar" anahtarı 422 yemez, boş küme döner
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name",),
                               filtreler=[{"alan": "dava_sayisi", "op": "is_null"}]))
    assert r.status_code == 200 and r.json()["toplam"] == 0
    r = _onizle(client, _tanim(kaynak="muvekkiller", kolonlar=("name",),
                               filtreler=[{"alan": "dava_sayisi", "op": "not_null"}]))
    assert r.json()["toplam"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# 4. Türetilmişte op alt kümesi + sıralama 422
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("filtre", [
    {"alan": "muvekkil_adlari", "op": "eq", "deger": "Dr. Ayşe"},         # metinde eq tip tablosunda var, alt kümede yok
    {"alan": "muvekkil_adlari", "op": "ne", "deger": "x"},
    {"alan": "muvekkil_adlari", "op": "in", "deger": ["x"]},
    {"alan": "sigortali_adlari", "op": "gte", "deger": "x"},              # tip tablosunda da yok
    {"alan": "muvekkil_kategorisi", "op": "ne", "deger": "Doktor"},
    {"alan": "muvekkil_kategorisi", "op": "not_null"},
    {"alan": "muvekkil_kategorisi", "op": "contains", "deger": "Dok"},
])
def test_422_turetilmis_izinsiz_op(env, filtre):
    d = _422(_onizle(env.client(), _tanim(filtreler=[filtre])), "filtreler[0]")
    assert "izinli değil" in d["sebep"] and filtre["op"] in d["sebep"]


@pytest.mark.parametrize("alan", ["muvekkil_adlari", "sigortali_adlari", "muvekkil_kategorisi"])
def test_422_turetilmis_siralama(env, alan):
    d = _422(_onizle(env.client(), _tanim(siralama=[{"alan": alan, "yon": "asc"}])), "siralama[0]")
    assert "sıralanamaz" in d["sebep"]


def test_izinli_oplar_tip_tablosunun_alt_kumesi():
    """Kayıt defteri denetimi: `izinli_oplar` ⊆ `TIP_OPLARI[tip]`; filtrelenebilir türetilmiş → `filtre_ifadesi`."""
    for kaynak in registry.KAYNAKLAR.values():
        for kolon in kaynak.kolonlar.values():
            assert set(kolon.oplar) <= set(TIP_OPLARI[kolon.tip])
            if kolon.turetilmis and kolon.filtrelenebilir:
                assert kolon.filtre_ifadesi is not None
            if not kolon.turetilmis:
                assert kolon.filtre_ifadesi is None and kolon.oplar == TIP_OPLARI[kolon.tip]
    assert registry.DAVALAR.kolonlar["muvekkil_adlari"].oplar == ("contains", "is_null", "not_null")
    assert registry.DAVALAR.kolonlar["muvekkil_kategorisi"].oplar == ("eq", "in", "is_null")
    with pytest.raises(RaporDogrulamaHatasi) as ex:
        motor.tanimi_dogrula(RaporTanimi(veri_kaynagi="davalar", kolonlar=["id"],
                                         filtreler=[{"alan": "muvekkil_adlari", "op": "eq", "deger": "x"}]))
    assert ex.value.alan == "filtreler[0]"


def test_registry_denetimi_hatali_tanimi_reddeder():
    """`_kolonu_denetle`: grup dışı, filtre ifadesiz filtrelenebilir türetilmiş, alt küme dışı op, önerili liste."""
    from dataclasses import replace

    K = registry.DAVALAR
    kolon = K.kolonlar["subject"]
    with pytest.raises(ValueError, match="grup"):
        registry._kolonu_denetle(K, replace(kolon, grup="Yok"))
    with pytest.raises(ValueError, match="filtre_ifadesi yok"):
        registry._kolonu_denetle(K, replace(K.kolonlar["foy_sayisi"], filtrelenebilir=True))
    with pytest.raises(ValueError, match="izinli_oplar"):
        registry._kolonu_denetle(K, replace(kolon, izinli_oplar=("gte",)))
    with pytest.raises(ValueError, match="öneri yalnız metin"):
        registry._kolonu_denetle(K, replace(K.kolonlar["status"], onerili=True))
    with pytest.raises(ValueError, match="yalnız türetilmiş"):
        registry._kolonu_denetle(K, replace(kolon, filtre_ifadesi=lambda op, d, atom: None))


# ═══════════════════════════════════════════════════════════════════════════
# 5. Önbellek — 60 sn, tenant anahtarlı
# ═══════════════════════════════════════════════════════════════════════════

def test_katalog_onbellegi_60_sn(env, monkeypatch):
    """Kabul: 60 sn içinde ikinci çağrı `registry.katalog`ı (DISTINCT sorgularını) koşturmaz; 60 sn
    sonra yeniler; tenant anahtarlı."""
    saat = [1000.0]
    monkeypatch.setattr(env.route, "_saat", lambda: saat[0])
    sayac = {"n": 0}
    gercek = registry.katalog

    def sayan(db, limitler, tenant_id):
        sayac["n"] += 1
        return gercek(db, limitler, tenant_id)

    monkeypatch.setattr(env.route.registry, "katalog", sayan)
    client = env.client()
    ilk = client.get(CATALOG).json()
    assert sayac["n"] == 1
    saat[0] += 59.9
    assert client.get(CATALOG).json() == ilk and sayac["n"] == 1
    # başka tenant ayrı anahtar
    env.client(tid=T2).get(CATALOG)
    assert sayac["n"] == 2
    saat[0] += 0.2                     # ilk kayıt 60.1 sn yaşında
    client.get(CATALOG)
    assert sayac["n"] == 3
    env.route.katalog_onbellegini_sifirla()
    client.get(CATALOG)
    assert sayac["n"] == 4


def test_katalog_onbellegi_veri_degisimini_60_sn_gizler(env, monkeypatch):
    """Önbellek davranışının gözlemlenebilir sonucu: yeni DISTINCT değeri süre dolana dek görünmez."""
    saat = [5000.0]
    monkeypatch.setattr(env.route, "_saat", lambda: saat[0])
    client = env.client()
    assert _kolonlar(_katalog(client)["davalar"])["responsible_lawyer_name"]["secenekler"] == ["Av. Ali", "Av. Veli"]
    db = env.db()
    try:
        db.add(models.Case(tracking_no="HA.G137.yeni", tenant_id=T1, status="DERDEST", responsible_lawyer_name="Av. Yeni"))
        db.commit()
    finally:
        db.close()
    assert "Av. Yeni" not in _kolonlar(_katalog(client)["davalar"])["responsible_lawyer_name"]["secenekler"]
    saat[0] += 60.0
    assert "Av. Yeni" in _kolonlar(_katalog(client)["davalar"])["responsible_lawyer_name"]["secenekler"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Asistan katalog metni
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_katalog_metni_yeni_alanlari_gommez(env):
    """Kabul: `katalog_metni` öneri/hızlı filtre/grup/kontrol alanlarını içermez; yeni dört kolon girer;
    metin uzunluğu önerilerle şişmez (300+ DISTINCT değer varken de aynı)."""
    metin = asistan.katalog_metni()
    # grup adlarından yalnız hiçbir kolon etiketiyle çakışmayanlar ("Karşı Taraflar" etikettir)
    for yasak in ("hizli_filtreler", "kolon_setleri", "oneriler", "oneri_kesik", "tarih_araligi", "coklu_secim",
                  "metin_icerir", "sayi_araligi", "Mahkeme ve konu", "Karar ve aşama", "Sınıflandırma"):
        assert yasak not in metin, yasak
    for anahtar in ("muvekkil_adlari", "karsi_taraf_adlari", "sigortali_adlari", "muvekkil_kategorisi"):
        assert f"\n{anahtar} · " in metin
    assert "muvekkil_adlari · Müvekkiller · metin · türetilmiş (filtre yalnız: contains|is_null|not_null; sıralama yok)" in metin
    assert "muvekkil_kategorisi · Müvekkil Kategorisi · liste · Doktor|" in metin
    assert "foy_sayisi · Föy Sayısı · sayi · türetilmiş (filtre/sıralama yok)" in metin
    db = env.db()
    try:
        db.add_all([models.Case(tracking_no=f"HA.M.{i:04d}", tenant_id=T1, status="DERDEST",
                                court=f"Mahkeme {i:04d}") for i in range(registry.ONERI_MAX + 5)])
        db.commit()
    finally:
        db.close()
    assert asistan.katalog_metni() == metin
    assert "Mahkeme 0000" not in metin
