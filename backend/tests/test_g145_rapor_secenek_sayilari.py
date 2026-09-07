"""G145 — Rapor kataloğu: `secenek_sayilari` + sıklık sırası (sabit listeler dahil, sıfırlılar sonda),
`bos_sayisi` (kaynak başına TEK sorgu), türetilmişte `null`, önbellek, asistan metni değişmez (plan §7.2).

Düzen `test_g141_rapor_veriden_liste.env` reçetesi (sqlite StaticPool, gerçek `require_admin`); veri bu
görevin senaryolarına göre: Durum DERDEST 2 / KARAR 1 (biri legacy NULL tenant), silinmiş DERDEST ve başka
tenant DERDEST sayılmaz; boş konu ("" ve yalnız boşluk), NULL mahkeme/tarih/tutar/mantık; müvekkil türleri;
sorgu sayacı motorun `before_cursor_execute` olayıyla (kaynak başına tek FILTER + tek UNION ALL).
"""
import datetime as dt
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from services.rapor import asistan, registry
from services.rapor.registry import DAVA_DURUMLARI

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
    c1 = models.Case(tracking_no="HA.G145.1", tenant_id=T1, status="DERDEST", subject="Kalp ameliyatı",
                     court="Ankara 1. Asliye Hukuk", opening_date=dt.date(2025, 3, 1), dava_degeri=100,
                     active=True, file_type="Hukuk")
    c2 = models.Case(tracking_no="HA.G145.2", tenant_id=T1, status="DERDEST", subject="", court=None,
                     opening_date=None, dava_degeri=None, file_type="Hukuk")
    c3 = models.Case(tracking_no="HA.G145.3", tenant_id=None, status="KARAR", subject="   ",
                     court="Bursa 2. Asliye Hukuk", opening_date=None, dava_degeri=None, active=False,
                     file_type="Panelden Tür")
    c_silinmis = models.Case(tracking_no="HA.G145.4", tenant_id=T1, status="DERDEST", subject="Silinmiş",
                             court="Silinmiş Mahkeme", deleted_at=SILINDI, deleted_by=ADMIN)
    c_yabanci = models.Case(tracking_no="HA.G145.5", tenant_id=T2, status="DERDEST", subject="Yabancı",
                            court="Yabancı Mahkeme")
    db.add_all([c1, c2, c3, c_silinmis, c_yabanci])
    db.flush()
    # `active` Column default=True: ORM'de açık `None` bile varsayılana düşer → NULL'u UPDATE ile yaz
    db.execute(update(models.Case).where(models.Case.id == c2.id).values(active=None))
    M = models.Client
    m1 = M(name="Dr. Bir", tenant_id=T1, client_type="Individual", category="Doktor", il="Ankara",
           email="bir@ornek.tr", birth_year=1970)
    m2 = M(name="Dr. İki", tenant_id=T1, client_type="Individual", category="Doktor", il="Ankara", email="",
           birth_year=None)
    m3 = M(name="Hastane", tenant_id=None, client_type="Corporate", category="Özel Hastane", il="İzmir",
           email=None, birth_year=None)
    m_silinmis = M(name="Silinmiş", tenant_id=T1, client_type="Corporate", category="Kurum", deleted_at=SILINDI)
    m_yabanci = M(name="Yabancı", tenant_id=T2, client_type="Corporate", category="Kurum")
    db.add_all([m1, m2, m3, m_silinmis, m_yabanci])
    db.flush()
    P = models.CaseParty
    db.add_all([
        P(case_id=c1.id, client_id=m1.id, name="Dr. Bir", role="Davalı", party_type="CLIENT"),
        P(case_id=c3.id, client_id=m3.id, name="Hastane", role="Davalı", party_type="CLIENT"),
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

    sorgular: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _kaydet(conn, cursor, statement, parameters, context, executemany):
        sorgular.append(statement)

    def _client(email=ADMIN, tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(db=maker, client=_client, route=route_mod, sorgular=sorgular)
    route_mod.katalog_onbellegini_sifirla()
    engine.dispose()


def _katalog(client):
    r = client.get(CATALOG)
    assert r.status_code == 200, r.text
    return {k["anahtar"]: k for k in r.json()["veri_kaynaklari"]}


def _kolonlar(kaynak):
    return {k["anahtar"]: k for k in kaynak["kolonlar"]}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Sabit listede sayı + sıra + sıfırlılar sonda; tenant / silinmiş kayıt sayılmaz
# ═══════════════════════════════════════════════════════════════════════════

def test_sabit_liste_sayi_sira_sifirlilar_sonda(env):
    """Kabul: Durum DERDEST 2 / KARAR 1 (legacy NULL tenant dahil), silinmiş ve başka tenant sayılmaz;
    sıra sayıya göre azalan, sıfırlı sabit değerler listede KALIR ve kendi sırasıyla sonda;
    `secenek_sayilari` anahtar kümesi = `secenekler`, `secenek_kaynagi` sabit kalır."""
    durum = _kolonlar(_katalog(env.client())["davalar"])["status"]
    sifirlilar = [d for d in DAVA_DURUMLARI if d not in ("DERDEST", "KARAR")]
    assert durum["secenekler"] == ["DERDEST", "KARAR", *sifirlilar]
    assert durum["secenek_sayilari"] == {"DERDEST": 2, "KARAR": 1, **{d: 0 for d in sifirlilar}}
    assert list(durum["secenek_sayilari"]) == durum["secenekler"]
    assert durum["secenek_kaynagi"] == "sabit" and durum["kontrol"] == "coklu_secim"
    # başka tenant: kendi DERDEST'i + legacy KARAR → 1'er, sabit sıra (DERDEST önce) korunur
    durum2 = _kolonlar(_katalog(env.client(tid=T2))["davalar"])["status"]
    assert durum2["secenekler"][:2] == ["DERDEST", "KARAR"]
    assert durum2["secenek_sayilari"]["DERDEST"] == 1 and durum2["secenek_sayilari"]["KARAR"] == 1


def test_sabit_liste_veride_gorulen_deger_ve_tablo_katmani_tenant_kuralli(env):
    """Veride görülen ek değer ("Panelden Tür", legacy) sabit çekirdek sonrası sayısıyla girer; silinmiş
    davanın değeri tenant/soft-delete kuralı gereği HİÇ girmez (G130 DISTINCT katmanının K2'li ikizi);
    referans tablosundaki aktif ad sıfır sayıyla listede, pasif ad yok."""
    db = env.db()
    try:
        db.add_all([
            models.FileType(code="TABLO", name="Tablodan Tür", active=True, sequence=1),
            models.FileType(code="PASIF", name="Pasif Tür", active=False, sequence=2),
            models.Case(tracking_no="HA.G145.6", tenant_id=T1, status="DERDEST", file_type="Silinmiş Tür",
                        deleted_at=SILINDI, deleted_by=ADMIN),
        ])
        db.commit()
    finally:
        db.close()
    ft = _kolonlar(_katalog(env.client())["davalar"])["file_type"]
    assert ft["secenekler"][:2] == ["Hukuk", "Panelden Tür"]
    assert ft["secenek_sayilari"]["Hukuk"] == 2 and ft["secenek_sayilari"]["Panelden Tür"] == 1
    assert "Tablodan Tür" in ft["secenekler"] and ft["secenek_sayilari"]["Tablodan Tür"] == 0
    assert "Pasif Tür" not in ft["secenekler"] and "Silinmiş Tür" not in ft["secenekler"]
    assert ft["secenekler"].index("Tablodan Tür") > ft["secenekler"].index("Danışmanlık")   # sabit → tablo sırası


def test_muvekkil_client_type_sayilari_ve_etiketler_degismedi(env):
    ct = _kolonlar(_katalog(env.client())["muvekkiller"])["client_type"]
    assert ct["secenekler"] == ["Individual", "Corporate"]
    assert ct["secenek_sayilari"] == {"Individual": 2, "Corporate": 1}         # silinmiş + yabancı sayılmaz
    assert ct["secenek_etiketleri"]["Individual"] == "Gerçek kişi"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Veriden listede sayı = G141 sayısı; türetilmiş listede null
# ═══════════════════════════════════════════════════════════════════════════

def test_veriden_liste_sayilari_g141_sorgusundan(env):
    kaynaklar = _katalog(env.client())
    court = _kolonlar(kaynaklar["davalar"])["court"]
    assert court["secenek_kaynagi"] == "veri"
    assert court["secenekler"] == ["Ankara 1. Asliye Hukuk", "Bursa 2. Asliye Hukuk"]
    assert court["secenek_sayilari"] == {"Ankara 1. Asliye Hukuk": 1, "Bursa 2. Asliye Hukuk": 1}
    il = _kolonlar(kaynaklar["muvekkiller"])["il"]
    assert il["secenekler"] == ["Ankara", "İzmir"] and il["secenek_sayilari"] == {"Ankara": 2, "İzmir": 1}
    db = env.db()
    try:
        D = registry.DAVALAR
        ciftler = registry.veriden_secenekleri_getir(D, D.kolonlar["court"], db, T1, sayili=True)
        assert ciftler == [("Ankara 1. Asliye Hukuk", 1), ("Bursa 2. Asliye Hukuk", 1)]
        assert registry.veriden_secenekleri_getir(D, D.kolonlar["court"], db, T1) == [d for d, _n in ciftler]
        assert registry.veriden_secenekleri_getir(D, D.kolonlar["subject"], db, T1, sayili=True) is None
    finally:
        db.close()


def test_turetilmis_liste_kolonda_sayi_null_sira_sabit(env):
    kategori = _kolonlar(_katalog(env.client())["davalar"])["muvekkil_kategorisi"]
    assert kategori["secenek_sayilari"] is None and kategori["bos_sayisi"] is None
    assert kategori["secenekler"][:2] == ["Doktor", "Sağlık Çalışanı"] and "Özel Hastane" in kategori["secenekler"]


def test_secenek_sayilari_yalniz_secenekli_kolonlarda(env):
    for anahtar, kaynak in _katalog(env.client()).items():
        for k in kaynak["kolonlar"]:
            if k["secenekler"] is None:
                assert k["secenek_sayilari"] is None, (anahtar, k["anahtar"])
            elif k["turetilmis"]:
                assert k["secenek_sayilari"] is None, (anahtar, k["anahtar"])
            else:
                assert list(k["secenek_sayilari"]) == k["secenekler"], (anahtar, k["anahtar"])
                sayilar = list(k["secenek_sayilari"].values())
                assert sayilar == sorted(sayilar, reverse=True), (anahtar, k["anahtar"])
                assert all(isinstance(n, int) and n >= 0 for n in sayilar)


def test_secenekleri_sayili_getir_db_yok_ve_liste_disi():
    D = registry.DAVALAR
    assert registry.secenekleri_sayili_getir(D, D.kolonlar["status"], None, T1) == (list(DAVA_DURUMLARI), None)
    assert registry.secenekleri_sayili_getir(D, D.kolonlar["subject"], None, T1) == ([], None)
    assert registry.liste_sayilari(D, None, T1) == {}


# ═══════════════════════════════════════════════════════════════════════════
# 3. bos_sayisi: metin boş string dahil, tarih/sayı/mantık NULL, türetilmişte null, tek sorgu
# ═══════════════════════════════════════════════════════════════════════════

def test_bos_sayisi_tiplere_gore(env):
    kaynaklar = _katalog(env.client())
    davalar = _kolonlar(kaynaklar["davalar"])
    assert davalar["subject"]["bos_sayisi"] == 2            # "" + yalnız boşluk (TRIM), silinmiş/yabancı sayılmaz
    assert davalar["court"]["bos_sayisi"] == 1              # NULL
    assert davalar["status"]["bos_sayisi"] == 0             # liste kolon da sayılır
    assert davalar["opening_date"]["bos_sayisi"] == 2       # tarih NULL
    assert davalar["dava_degeri"]["bos_sayisi"] == 2        # para NULL
    assert davalar["active"]["bos_sayisi"] == 1             # mantık NULL (False boş DEĞİL)
    assert davalar["id"]["bos_sayisi"] == 0
    for turetilmis in ("muvekkil_adlari", "muvekkil_kategorisi", "foy_sayisi", "belge_sayisi", "arama"):
        assert davalar[turetilmis]["bos_sayisi"] is None, turetilmis
    muv = _kolonlar(kaynaklar["muvekkiller"])
    assert muv["email"]["bos_sayisi"] == 2 and muv["birth_year"]["bos_sayisi"] == 2
    assert muv["dava_sayisi"]["bos_sayisi"] is None         # türetilmiş sayı (hızlı filtre) → null
    # başka tenant: kendi kaydı + legacy
    davalar2 = _kolonlar(_katalog(env.client(tid=T2))["davalar"])
    assert davalar2["subject"]["bos_sayisi"] == 1 and davalar2["court"]["bos_sayisi"] == 0


def test_bos_sayisi_yalniz_filtrelenebilir_is_null_izinli_duz_kolonlarda(env):
    for anahtar, kaynak in _katalog(env.client()).items():
        for k in kaynak["kolonlar"]:
            kolon = registry.KAYNAKLAR[anahtar].kolonlar[k["anahtar"]]
            beklenen_var = kolon.filtrelenebilir and not kolon.turetilmis and "is_null" in kolon.oplar
            assert (k["bos_sayisi"] is not None) == beklenen_var, (anahtar, k["anahtar"])
            if beklenen_var:
                assert isinstance(k["bos_sayisi"], int) and k["bos_sayisi"] >= 0


def test_bos_sayilari_ve_liste_sayilari_kaynak_basina_tek_sorgu(env):
    """Kabul: katalog kurulumunda kaynak başına TEK `COUNT(*) FILTER` sorgusu ve TEK `UNION ALL` GROUP BY
    sorgusu (4 kaynak → 4 + 4); ikinci çağrı önbellekten — hiç sorgu koşmaz."""
    client = env.client()
    env.sorgular.clear()
    client.get(CATALOG)
    filtreli = [s for s in env.sorgular if "FILTER (WHERE" in s]
    birlesik = [s for s in env.sorgular if "UNION ALL" in s]
    assert len(filtreli) == len(registry.KAYNAKLAR) == len(birlesik)
    for s in filtreli:
        assert s.count("FILTER (WHERE") >= 5 and "trim(" in s.lower()
    # davalar (en çok liste kolonlu kaynak): her düz liste kolonu tek UNION ALL'da; GROUP BY sayısı = kolon sayısı
    davalar_birlesik = max(birlesik, key=lambda s: s.count("GROUP BY"))
    assert davalar_birlesik.count("GROUP BY") == len(registry._duz_liste_kolonlari(registry.DAVALAR)) == 18
    env.sorgular.clear()
    client.get(CATALOG)
    assert env.sorgular == []


def test_bos_sayilari_fonksiyonu_dogrudan(env):
    db = env.db()
    try:
        bos = registry.bos_sayilari(registry.DAVALAR, db, T1)
        assert bos["subject"] == 2 and bos["court"] == 1 and bos["opening_date"] == 2
        assert "foy_sayisi" not in bos and "muvekkil_adlari" not in bos and "arama" not in bos
        assert registry.bos_sayilari(registry.DAVALAR, None, T1) == {}
        # satırsız kaynak → 0 (NULL değil)
        assert all(n == 0 for n in registry.bos_sayilari(registry.BELGELER, db, T1).values())
    finally:
        db.close()


def test_duz_liste_kolon_metin_disi_db_tipi_reddedilir():
    D = registry.DAVALAR
    with pytest.raises(ValueError, match="UNION ALL"):
        registry._kolonu_denetle(D, replace(D.kolonlar["status"], ifade=models.Case.id))
    registry._kolonu_denetle(D, D.kolonlar["status"])


# ═══════════════════════════════════════════════════════════════════════════
# 4. Asistan metni sayı gömmez; /preview gövdesi değişmedi
# ═══════════════════════════════════════════════════════════════════════════

def test_asistan_katalog_metni_sayi_gommez(env):
    metin = asistan.katalog_metni()
    assert f"\nstatus · Durum · liste · {'|'.join(DAVA_DURUMLARI)}\n" in metin
    for yasak in ("secenek_sayilari", "bos_sayisi"):
        assert yasak not in metin
    assert not re.search(r"\(\d+\)", metin)
    # DB'de veri varken de aynı metin (DB yok, K6): uzunluk değişmez
    env.client().get(CATALOG)
    assert asistan.katalog_metni() == metin


def test_onizleme_govdesi_degismedi(env):
    r = env.client().post(PREVIEW, json={"tanim": {"veri_kaynagi": "davalar", "kolonlar": ["tracking_no", "status"],
                                                   "filtreler": [{"alan": "status", "op": "eq", "deger": "KARAR"}],
                                                   "siralama": []}})
    assert r.status_code == 200, r.text
    govde = r.json()
    assert set(govde) == {"kolonlar", "satirlar", "toplam", "sayfa", "sayfa_boyu"}
    assert govde["toplam"] == 1 and govde["satirlar"][0]["tracking_no"] == "HA.G145.3"
    assert set(govde["kolonlar"][0]) == {"anahtar", "etiket", "tip"}


def _filtrele(client, alan, op, deger=None, kaynak="davalar"):
    f = {"alan": alan, "op": op}
    if deger is not None or op == "in":
        f["deger"] = deger
    r = client.post(PREVIEW, json={"tanim": {"veri_kaynagi": kaynak, "kolonlar": ["tracking_no"],
                                             "filtreler": [f], "siralama": []}})
    assert r.status_code == 200, r.text
    return {s["tracking_no"] for s in r.json()["satirlar"]}, r.json()["toplam"]


def test_bos_filtresi_rozetle_ayni_anlam(env):
    """07.09 kararı (G145 karar bekleyeni): katalog `bos_sayisi` metin kolonda boş string'i de sayar;
    filtre `is_null` de aynı satırları bulmalı — rozet 2 derken filtre 1 bulmasın. `not_null` tersi,
    `in [.., null]` boş string'i de kapsar; tarih/sayı kolonlarında yalnız NULL (davranış aynı)."""
    client = env.client()
    davalar = _kolonlar(_katalog(client)["davalar"])
    bos, toplam = _filtrele(client, "subject", "is_null")
    assert toplam == davalar["subject"]["bos_sayisi"] == 2 and bos == {"HA.G145.2", "HA.G145.3"}
    dolu, _ = _filtrele(client, "subject", "not_null")
    assert "HA.G145.1" in dolu and not (dolu & bos)
    # in içinde null: "Kalp ameliyatı" VEYA boş (boş string dahil)
    kume, _ = _filtrele(client, "subject", "in", ["Kalp ameliyatı", None])
    assert kume == {"HA.G145.1", "HA.G145.2", "HA.G145.3"}
    # yalnız [null] = boş; `ne` boşları da kapsar
    assert _filtrele(client, "subject", "in", [None])[0] == bos
    assert _filtrele(client, "subject", "ne", "Kalp ameliyatı")[0] == bos
    # tarih kolonunda anlam değişmedi: yalnız NULL
    tarih_bos, tarih_toplam = _filtrele(client, "opening_date", "is_null")
    assert tarih_toplam == davalar["opening_date"]["bos_sayisi"] == 2
