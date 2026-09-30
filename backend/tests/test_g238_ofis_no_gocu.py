"""G238 — ofis no göçü (`scripts/ofis_no_gocu.py`): plan (DB'siz) + `--apply` (GERÇEK Postgres).

İki katman:

* **Plan** — `kart_planla` / `siralari_ver` saf fonksiyonlardır; karar 023 vakaları, kategori
  kaynağı zinciri ve sıra kuralı DB'siz sınanır.
* **Uygulama** — scratch veritabanında (`test_migration_path` altyapısı; gerçek `hukudok`
  DB'sine asla yazılmaz, DB yoksa SKIP): iki aşamalı numara yazımı, tarihçe, föy çevirisi,
  sayaç, envanter kapısı rollback'i, idempotency ve eski numarayla arama.
"""
import csv
import importlib
import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Uygulama modülleri env okur — önce env, sonra import (import sırası davranışın parçası).
os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

models = importlib.import_module("models")
mig = importlib.import_module("test_migration_path")
case_manager = importlib.import_module("managers.case_manager")
goc = importlib.import_module("scripts.ofis_no_gocu")
ofis_no = importlib.import_module("services.ofis_no")

admin_engine = mig.admin_engine

ESKI_S3 = "S3.AXA........0131.HUKUK.00000"
ESKI_D1 = "D1.M_OZTURK...0003.HUKUK.00000"
ESKI_S0 = "S0.KORU.......0001.IDARE.00000"
ESKI_X1 = "X1.ENTHONE....0015.CEZAA.00000"


# ─── Plan yardımcıları ───────────────────────────────────────────────────────

def _muvekkil(ad, kategori=None, pid=1, rol="Müvekkil"):
    return {"id": pid, "name": ad, "role": rol, "party_type": "CLIENT", "client_category": kategori}


def _taraf(ad, rol, pid=50, tip="THIRD"):
    return {"id": pid, "name": ad, "role": rol, "party_type": tip, "client_category": None}


def _foy(sigortali=None, tip=None, party_id=None, kapsam=None):
    return {
        "case_party_id": party_id, "muvekkil_tipi": tip, "kapsam_durumu": kapsam,
        "ham_veri": {"Sigortalı": sigortali} if sigortali else {},
    }


def _kart(cid=1, eski=ESKI_S3, taraflar=(), foyler=(), **kw):
    return goc.KartGirdisi(case_id=cid, tracking_no=eski, taraflar=list(taraflar), foyler=list(foyler), **kw)


def _numara(kart, ad_kategorileri=None):
    plan = goc.kart_planla(kart, None, ad_kategorileri)
    goc.siralari_ver([plan])
    return plan


# ─── Plan: karar 023 vakaları ────────────────────────────────────────────────

def test_sigortaci_ve_sigortali_foyden():
    plan = _numara(_kart(
        taraflar=[_muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi")], foyler=[_foy("Dr. Emre Altunç")],
    ))
    assert plan.yeni == "AXA-0001-DR.E.ALTUNC-HUK"
    assert (plan.kod, plan.sira, plan.kategori_kaynagi, plan.sigortali_kaynagi) == ("AXA", 1, "muvekkil_kaydi", "foy")


def test_sigortaci_sigortalisiz_bloksuz_numaralanir_ve_eksik_isaretlenir():
    plan = _numara(_kart(taraflar=[_muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi")]))
    assert plan.yeni == "AXA-0001-HUK"
    assert plan.sigortaci and plan.sigortali is None and plan.sigortali_kaynagi == "eksik"


@pytest.mark.parametrize("ad, beklenen", [
    ("Koru Sigorta A.Ş.", "KORU-0001-IDR"),
    ("HDI Sigorta A.Ş.", "HDI-0001-IDR"),
    ("Ergo Sigorta A.Ş.", "SG-0001-IDR"),
])
def test_s0_kartinda_sirket_addan_cozulur_bilinmeyen_sg(ad, beklenen):
    plan = _numara(_kart(eski=ESKI_S0, file_type="İdare", taraflar=[_muvekkil(ad)]))
    assert plan.yeni == beklenen
    assert plan.kategori_kaynagi == "eski_numara"


@pytest.mark.parametrize("ad, kategori, tur, beklenen", [
    ("Dr. Mehmet Öztürk", "Doktor", "Hukuk", "DR.M.OZTURK-0001-HUK"),
    ("Ayşe Koca", "Sağlık Çalışanı", "Hukuk", "SC.A.KOCA-0001-HUK"),
    ("Ali Kaya", "Hasta", "İdare", "HS.A.KAYA-0001-IDR"),
    ("Özel Safa Hastanesi", "Özel Hastane", "Hukuk", "OH.SAFA-0001-HUK"),
])
def test_kisi_ve_kurum_kategorileri(ad, kategori, tur, beklenen):
    plan = _numara(_kart(eski=ESKI_D1, file_type=tur, taraflar=[_muvekkil(ad, kategori)]))
    assert plan.yeni == beklenen
    assert not plan.sigortaci and plan.sigortali_kaynagi == ""


def test_x1_sirket_kr_kisi_br():
    sirket = _numara(_kart(eski=ESKI_X1, file_type="Ceza", taraflar=[_muvekkil("Enthone Kimya San. ve Tic. A.Ş.")]))
    kisi = _numara(_kart(eski=ESKI_X1, file_type="İcra", taraflar=[_muvekkil("Tarık Koç")]))
    assert sirket.yeni == "KR.ENTHONE-0001-CEZ"
    assert kisi.yeni == "BR.T.KOC-0001-ICR"
    assert sirket.kategori_kaynagi == kisi.kategori_kaynagi == "eski_numara"


def test_x1_kartinda_sigorta_adli_sirket_sigortaci_sayilmaz():
    plan = _numara(_kart(eski=ESKI_X1, taraflar=[_muvekkil("Kaynak Sigorta Aracılık Ltd. Şti.")]))
    assert plan.yeni == "KR.KAYNAK-0001-HUK"


def test_silinmis_kart_da_numara_alir():
    plan = _numara(_kart(silinmis=True, eski=ESKI_D1, taraflar=[_muvekkil("Dr. Mehmet Öztürk", "Doktor")]))
    assert plan.silinmis and plan.yeni == "DR.M.OZTURK-0001-HUK"


def test_cok_hekimli_sigortali_tek_kisi():
    plan = _numara(_kart(
        taraflar=[_muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi")],
        foyler=[_foy("Özel Safa Hastanesi; Dr. Ali Kaya; Dr. Veli Can")],
    ))
    assert plan.yeni == "AXA-0001-DR.A.KAYA-HUK"


def test_sigortaci_ile_doktor_birlikte_muvekkil_doktor_sigortali_bloguna():
    plan = _numara(_kart(taraflar=[
        _muvekkil("Dr. Emre Altunç", "Doktor", pid=1), _muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi", pid=2),
    ]))
    assert plan.yeni == "AXA-0001-DR.E.ALTUNC-HUK"
    assert plan.sigortali_kaynagi == "ortak_muvekkil"


def test_sigortali_kaynaklari_taraf_ve_diger_davali():
    taraf = _numara(_kart(taraflar=[
        _muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi"), _taraf("Dr. Selim Özay", "Sigortalı"),
    ]))
    davali = _numara(_kart(taraflar=[
        _muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi"), _taraf("Dr. Hakan Bağış", "Diğer Davalı"),
    ]))
    assert (taraf.yeni, taraf.sigortali_kaynagi) == ("AXA-0001-DR.S.OZAY-HUK", "taraf")
    assert (davali.yeni, davali.sigortali_kaynagi) == ("AXA-0001-DR.H.BAGIS-HUK", "diger_davali")


def test_muvekkilsiz_kart_numara_almaz():
    plan = _numara(_kart(taraflar=[_taraf("Karşı Taraf A.Ş.", "Karşı Taraf", tip="COUNTER")]))
    assert plan.durum == "MUVEKKILSIZ" and plan.yeni is None and plan.kod is None


# ─── Plan: kategori kaynağı zinciri ──────────────────────────────────────────

def test_zincir_1_muvekkil_kategorisi_eski_koddan_once_gelir():
    # Eski numara D1 (doktor) diyor; müvekkil kaydı Bireysel — kayıt kazanır.
    plan = _numara(_kart(eski=ESKI_D1, taraflar=[_muvekkil("Mehmet Öztürk", "Bireysel")]))
    assert (plan.yeni, plan.kategori_kaynagi) == ("BR.M.OZTURK-0001-HUK", "muvekkil_kaydi")


def test_zincir_1_bagsiz_tarafta_ayni_adli_muvekkil_kaydi():
    kart = _kart(eski=ESKI_D1, taraflar=[_muvekkil("Mehmet Öztürk")], foyler=[_foy(tip="Hasta", party_id=1)])
    plan = _numara(kart, {goc.ad_anahtari("Mehmet Öztürk"): "Bireysel"})
    assert (plan.yeni, plan.kategori_kaynagi) == ("BR.M.OZTURK-0001-HUK", "muvekkil_kaydi_ad")


def test_zincir_2_foy_muvekkil_tipi_eski_koddan_once_gelir():
    plan = _numara(_kart(eski=ESKI_D1, taraflar=[_muvekkil("Mehmet Öztürk")], foyler=[_foy(tip="Hasta", party_id=1)]))
    assert (plan.yeni, plan.kategori_kaynagi) == ("HS.M.OZTURK-0001-HUK", "foy")


def test_zincir_2_kapsam_disi_ve_baska_tarafin_foyu_sayilmaz():
    plan = _numara(_kart(eski=ESKI_D1, taraflar=[_muvekkil("Mehmet Öztürk")], foyler=[
        _foy(tip="Hasta", party_id=1, kapsam="SILINDI"), _foy(tip="Kurum", party_id=99),
    ]))
    assert (plan.yeni, plan.kategori_kaynagi) == ("DR.M.OZTURK-0001-HUK", "eski_numara")


@pytest.mark.parametrize("eski, ad, beklenen", [
    ("D1.M_OZTURK...0003.HUKUK.00000", "Mehmet Öztürk", "DR.M.OZTURK-0001-HUK"),
    ("D2.A_KOCA.....0001.HUKUK.00000", "Ayşe Koca", "SC.A.KOCA-0001-HUK"),
    ("H1.A_KAYA.....0001.HUKUK.00000", "Ali Kaya", "HS.A.KAYA-0001-HUK"),
    ("H2.SAFA.......0001.HUKUK.00000", "Özel Safa Hastanesi", "OH.SAFA-0001-HUK"),
    # S1-S7 tek şirket kodları: ad listede eşleşmese de sabit koda gider; S4 iki şirket → addan.
    ("S3.BILINMEYEN.0001.HUKUK.00000", "Bilinmeyen Şirket", "AXA-0001-HUK"),
    ("S5.BILINMEYEN.0001.HUKUK.00000", "Bilinmeyen Şirket", "EUREKO-0001-HUK"),
    ("S4.QUICK......0001.HUKUK.00000", "Quick Sigorta A.Ş.", "QUICK-0001-HUK"),
    ("S4.CORPUS.....0001.HUKUK.00000", "Corpus Sigorta A.Ş.", "CORPUS-0001-HUK"),
    ("S4.BILINMEYEN.0001.HUKUK.00000", "Bilinmeyen Şirket", "SG-0001-HUK"),
])
def test_zincir_3_eski_numaranin_ilk_blogu(eski, ad, beklenen):
    plan = _numara(_kart(eski=eski, taraflar=[_muvekkil(ad)]))
    assert (plan.yeni, plan.kategori_kaynagi) == (beklenen, "eski_numara")


def test_zincir_sonu_taninmayan_eski_kodda_ad_kurali():
    plan = _numara(_kart(eski="HK.TEST.0001", taraflar=[_muvekkil("Tarık Koç")]))
    assert (plan.yeni, plan.kategori_kaynagi) == ("BR.T.KOC-0001-HUK", "ad_kurali")


def test_kisi_eski_kodu_sirket_adina_yazilmaz():
    plan = _numara(_kart(eski=ESKI_D1, taraflar=[_muvekkil("Enthone Kimya A.Ş.")]))
    assert (plan.yeni, plan.kategori_kaynagi) == ("KR.ENTHONE-0001-HUK", "ad_kurali")


# ─── Plan: sıra ──────────────────────────────────────────────────────────────

def _doktor_karti(cid, acilis=None, olusturma=None):
    return _kart(cid=cid, eski=f"D1.M_OZTURK...{cid:04d}.HUKUK.00000", opening_date=acilis, created_at=olusturma,
                 taraflar=[_muvekkil("Dr. Mehmet Öztürk", "Doktor")])


def test_sira_opening_date_sonra_created_at_sonra_id():
    utc = timezone.utc
    kartlar = [
        _doktor_karti(1, olusturma=datetime(2020, 1, 1, tzinfo=utc)),                       # tarihsiz, eski kayıt
        _doktor_karti(2, acilis=date(2024, 5, 1), olusturma=datetime(2026, 1, 2, tzinfo=utc)),
        _doktor_karti(3, acilis=date(2021, 3, 1)),
        _doktor_karti(4, acilis=date(2024, 5, 1), olusturma=datetime(2026, 1, 1, tzinfo=utc)),
        _doktor_karti(5, olusturma=datetime(2019, 1, 1, tzinfo=utc)),                       # tarihsiz, daha eski
        _doktor_karti(7, acilis=date(2025, 1, 1), olusturma=datetime(2026, 2, 2, tzinfo=utc)),
        _doktor_karti(6, acilis=date(2025, 1, 1), olusturma=datetime(2026, 2, 2, tzinfo=utc)),
    ]
    planlar = [goc.kart_planla(k) for k in kartlar]
    tepe = goc.siralari_ver(planlar)
    assert {p.case_id: p.sira for p in planlar} == {3: 1, 4: 2, 2: 3, 6: 4, 7: 5, 5: 6, 1: 7}
    assert tepe == {"DR.M.OZTURK": 7}
    assert goc.plan_hatalari(planlar) == []


def test_sira_kod_basina_sayilir_ve_mevcut_sayactan_devam_eder():
    yeni = _kart(cid=9, eski="DR.M.OZTURK-0012-HUK", ofis_no_kodu="DR.M.OZTURK", ofis_no_sira=12,
                 taraflar=[_muvekkil("Dr. Mehmet Öztürk", "Doktor")])
    planlar = [goc.kart_planla(k) for k in (
        yeni, _doktor_karti(1, acilis=date(2020, 1, 1)),
        _kart(cid=2, taraflar=[_muvekkil("AXA Sigorta A.Ş.", "Sigorta Şirketi")]),
    )]
    tepe = goc.siralari_ver(planlar, {"AXA": 40, "DR.M.OZTURK": 3})
    assert planlar[0].durum == "ZATEN_YENI" and planlar[0].yeni == "DR.M.OZTURK-0012-HUK"
    assert planlar[1].yeni == "DR.M.OZTURK-0013-HUK"
    assert planlar[2].yeni == "AXA-0041-HUK"
    assert tepe == {"DR.M.OZTURK": 13, "AXA": 41}


def test_plan_kapisi_cakismayi_yakalar():
    a = goc.KartPlani(case_id=1, eski="E1", silinmis=False, durum="GOC", yeni="AXA-0001-HUK")
    b = goc.KartPlani(case_id=2, eski="AXA-0001-HUK", silinmis=False, durum="ZATEN_YENI", yeni="AXA-0001-HUK")
    c = goc.KartPlani(case_id=3, eski="E3", silinmis=False, durum="GOC", yeni="bozuk")
    hatalar = goc.plan_hatalari([a, b, c])
    assert len(hatalar) == 2 and "mükerrer" in hatalar[0] and "desen" in hatalar[1]


@pytest.mark.parametrize("numara, uyar", [
    ("DR.M.OZTURK-0003-HUK", True), ("KR.ENTHONE-0015-CEZ", True), ("AXA-3297-DR.E.ALTUNC-HUK", True),
    ("SG-0001-HUK", True), ("HS.MADONNA-10000-IDR", True), ("AXA-3297-OH.SAFA-HUK", True),
    (ESKI_S3, False), ("__GOC__12", False), ("AXA-297-HUK", False), ("AXA-0001-HUKUK", False), ("", False),
])
def test_yeni_format_deseni(numara, uyar):
    assert goc.yeni_formatta(numara) is uyar


# ─── Uygulama: gerçek Postgres ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg_engine(admin_engine):
    with mig._scratch_database(admin_engine, "g238") as engine:
        mig._run_init_db(engine)
        # Sigorta kodları migrasyonla değil açılış seed'iyle gelir — karar 023 tablosunu yaz.
        with sessionmaker(bind=engine)() as db:
            for kod, ad, anahtarlar in ofis_no.VARSAYILAN_SIGORTA_KODLARI:
                db.add(models.SigortaKisaKodu(kod=kod, ad=ad, eslesme_anahtarlari=list(anahtarlar), aktif=True))
            db.commit()
        yield engine


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE case_history, case_foys, case_parties, cases, clients, ofis_no_sayaclari "
            "RESTART IDENTITY CASCADE"
        ))
    Fabrika = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    return Fabrika


def _kart_ekle(Fabrika, eski, muvekkiller, *, tur="Hukuk", acilis=None, silinmis=False, sigortali=None,
               onceki=None, taraflar=()):
    """Kart + CLIENT tarafları (+ isteğe bağlı föy) yazar; `muvekkiller`: (ad, kategori|None)."""
    db = Fabrika()
    try:
        kart = models.Case(
            tracking_no=eski, file_type=tur, opening_date=acilis, status="DERDEST",
            deleted_at=datetime(2026, 9, 1, tzinfo=timezone.utc) if silinmis else None,
            active=not silinmis,
        )
        db.add(kart)
        db.flush()
        ilk_taraf = None
        for ad, kategori in muvekkiller:
            client_id = None
            if kategori:
                m = models.Client(name=ad, category=kategori, contact_type="Client", active=True)
                db.add(m)
                db.flush()
                client_id = m.id
            taraf = models.CaseParty(case_id=kart.id, name=ad, role="Müvekkil", party_type="CLIENT", client_id=client_id)
            db.add(taraf)
            db.flush()
            ilk_taraf = ilk_taraf or taraf
        for ad, rol in taraflar:
            db.add(models.CaseParty(case_id=kart.id, name=ad, role=rol, party_type="THIRD"))
        if sigortali or onceki:
            db.add(models.CaseFoy(
                sistem_no=f"SSTMN-{kart.id}", case_id=kart.id,
                case_party_id=ilk_taraf.id if ilk_taraf is not None else None,
                ham_veri={"Sigortalı": sigortali} if sigortali else None, onceki_tracking_no=onceki,
            ))
        db.commit()
        return kart.id
    finally:
        db.close()


def _satirlar(engine, sql, **p):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _numaralar(engine):
    return {r["id"]: r["tracking_no"] for r in _satirlar(engine, "SELECT id, tracking_no FROM cases")}


def _ornek_veri(Fabrika):
    """Altı kart: iki AXA (biri sigortalılı), doktor, silinmiş doktor, X1 şirket, birleşmiş kartın föyünü taşıyan."""
    return {
        "axa_yeni": _kart_ekle(Fabrika, "S3.AXA........0002.HUKUK.00000", [("AXA Sigorta A.Ş.", "Sigorta Şirketi")],
                               acilis=date(2024, 6, 1), sigortali="Dr. Emre Altunç"),
        "axa_eski": _kart_ekle(Fabrika, "S3.AXA........0001.IDARE.00000", [("AXA Sigorta A.Ş.", None)],
                               tur="İdare", acilis=date(2020, 1, 1)),
        "doktor": _kart_ekle(Fabrika, "D1.M_OZTURK...0001.HUKUK.00000", [("Dr. Mehmet Öztürk", None)],
                             acilis=date(2022, 1, 1), onceki="D1.M_OZTURK...0002.HUKUK.00000"),
        "silinmis": _kart_ekle(Fabrika, "D1.M_OZTURK...0002.HUKUK.00000", [("Dr. Mehmet Öztürk", None)],
                               acilis=date(2021, 1, 1), silinmis=True),
        "sirket": _kart_ekle(Fabrika, "X1.ENTHONE....0015.CEZAA.00000", [("Enthone Kimya San. ve Tic. A.Ş.", None)],
                             tur="Ceza"),
        "yabanci_foy": _kart_ekle(Fabrika, "X1.T_KOC......0009.ICRAA.00000", [("Tarık Koç", None)], tur="İcra",
                                  onceki="ESLEMEDE-OLMAYAN-NO"),
    }


pg_test = pytest.mark.dbtest


@pg_test
def test_kuru_kosu_db_ye_yazmaz_ve_raporlari_uretir(pg, pg_engine, tmp_path):
    ids = _ornek_veri(pg)
    once = _numaralar(pg_engine)

    sonuc = goc.kos(pg, rapor_dizini=tmp_path)

    assert not sonuc.uygulandi and sonuc.degisen == 6 and sonuc.plan_hatalari == []
    assert _numaralar(pg_engine) == once
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM case_history")[0]["n"] == 0
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM ofis_no_sayaclari")[0]["n"] == 0

    esleme, eksik, ozet = sonuc.raporlar
    with esleme.open(encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.DictReader(f))
    assert list(satirlar[0]) == ["case_id", "eski", "yeni", "silinmis", "kategori_kaynagi", "sigortali_kaynagi"]
    by_id = {int(s["case_id"]): s for s in satirlar}
    assert by_id[ids["axa_yeni"]]["yeni"] == "AXA-0002-DR.E.ALTUNC-HUK"
    assert by_id[ids["axa_yeni"]]["kategori_kaynagi"] == "muvekkil_kaydi"
    assert by_id[ids["axa_eski"]]["kategori_kaynagi"] == "muvekkil_kaydi_ad"   # bağsız taraf, aynı adlı kayıt
    assert by_id[ids["silinmis"]]["silinmis"] == "1"
    with eksik.open(encoding="utf-8-sig", newline="") as f:
        assert [int(s["case_id"]) for s in csv.DictReader(f)] == [ids["axa_eski"]]
    metin = ozet.read_text(encoding="utf-8")
    assert "KURU KOŞU" in metin and "AXA" in metin and "Müvekkilsiz kart: 0" in metin


@pg_test
def test_apply_numaralari_tarihceyi_foyu_ve_sayaci_yazar(pg, pg_engine):
    ids = _ornek_veri(pg)

    sonuc = goc.kos(pg, apply=True, kim="test")

    assert sonuc.uygulandi and sonuc.degisen == 6
    assert _numaralar(pg_engine) == {
        ids["axa_eski"]: "AXA-0001-IDR",                  # açılış 2020 → ilk sıra
        ids["axa_yeni"]: "AXA-0002-DR.E.ALTUNC-HUK",
        ids["silinmis"]: "DR.M.OZTURK-0001-HUK",          # silinmiş kart da sıraya girer (2021)
        ids["doktor"]: "DR.M.OZTURK-0002-HUK",
        ids["sirket"]: "KR.ENTHONE-0001-CEZ",
        ids["yabanci_foy"]: "BR.T.KOC-0001-ICR",
    }
    kod_sira = {r["id"]: (r["ofis_no_kodu"], r["ofis_no_sira"])
                for r in _satirlar(pg_engine, "SELECT id, ofis_no_kodu, ofis_no_sira FROM cases")}
    assert kod_sira[ids["axa_yeni"]] == ("AXA", 2) and kod_sira[ids["silinmis"]] == ("DR.M.OZTURK", 1)

    tarihce = _satirlar(pg_engine, "SELECT case_id, field_name, old_value, new_value, source, changed_by "
                                   "FROM case_history ORDER BY id")
    numara_satirlari = [t for t in tarihce if t["field_name"] == "tracking_no"]
    assert len(numara_satirlari) == 6
    assert all(t["source"] == "OFIS_NO_GOCU" and t["changed_by"] == "test" for t in tarihce)
    assert {"case_id": ids["axa_yeni"], "field_name": "tracking_no", "old_value": "S3.AXA........0002.HUKUK.00000",
            "new_value": "AXA-0002-DR.E.ALTUNC-HUK", "source": "OFIS_NO_GOCU", "changed_by": "test"} in tarihce

    # Föyde kalan eski numara eşlemeyle çevrilir; eşlemede olmayan değer olduğu gibi kalır (sayılır).
    foyler = {r["case_id"]: r["onceki_tracking_no"]
              for r in _satirlar(pg_engine, "SELECT case_id, onceki_tracking_no FROM case_foys")}
    assert foyler[ids["doktor"]] == "DR.M.OZTURK-0001-HUK"
    assert foyler[ids["yabanci_foy"]] == "ESLEMEDE-OLMAYAN-NO"
    assert (sonuc.foy_cevrilen, sonuc.foy_eslesmeyen) == (1, 1)

    sayaclar = {r["kod"]: r["son_sira"] for r in _satirlar(pg_engine, "SELECT kod, son_sira FROM ofis_no_sayaclari")}
    assert sayaclar == {"AXA": 2, "DR.M.OZTURK": 2, "KR.ENTHONE": 1, "BR.T.KOC": 1}


@pg_test
def test_apply_sonrasi_yeni_kayit_max_arti_bir_alir(pg, pg_engine):
    _ornek_veri(pg)
    goc.kos(pg, apply=True)

    db = pg()
    try:
        onizleme = ofis_no.onizle(db, [{"name": "AXA Sigorta A.Ş.", "category": "Sigorta Şirketi"}], "Hukuk",
                                  foys=[], parties=[])
        assert onizleme["numara"] == "AXA-0003-HUK"
        assert ofis_no.sira_tahsis_et(db, "AXA") == 3
        assert ofis_no.sira_tahsis_et(db, "DR.M.OZTURK") == 3
        db.commit()
    finally:
        db.close()


@pg_test
def test_apply_sonrasi_eski_numarayla_arama_karti_bulur(pg, pg_engine):
    ids = _ornek_veri(pg)
    goc.kos(pg, apply=True)

    bulunan, toplam = case_manager.get_cases(q="S3.AXA........0002.HUKUK.00000")
    assert [k["id"] for k in bulunan] == [ids["axa_yeni"]] and toplam == 1
    assert bulunan[0]["tracking_no"] == "AXA-0002-DR.E.ALTUNC-HUK"

    # Birleşmede sönen (silinmiş) kartın eski numarası föyü taşıyan YAŞAYAN kartı bulmaya devam eder.
    bulunan, _ = case_manager.get_cases(q="D1.M_OZTURK...0002.HUKUK.00000")
    assert [k["id"] for k in bulunan] == [ids["doktor"]]

    bulunan, _ = case_manager.get_cases(q="AXA-0002-DR.E.ALTUNC-HUK")
    assert [k["id"] for k in bulunan] == [ids["axa_yeni"]]


@pg_test
def test_envanter_kapisi_bozulunca_rollback(pg, pg_engine, monkeypatch):
    _ornek_veri(pg)
    once = _numaralar(pg_engine)
    gercek = goc.envanter
    cagri = {"n": 0}

    def bozuk_envanter(db):
        cagri["n"] += 1
        kart, silinmis, foy = gercek(db)
        # 1: plan, 2: uygulama öncesi, 3: kapı — sonuncuda bir föy "kaybolmuş" görünür.
        return (kart, silinmis, foy - 1) if cagri["n"] >= 3 else (kart, silinmis, foy)

    monkeypatch.setattr(goc, "envanter", bozuk_envanter)
    with pytest.raises(goc.GocDurdu, match="envanter"):
        goc.kos(pg, apply=True)

    assert cagri["n"] == 3
    assert _numaralar(pg_engine) == once
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM case_history")[0]["n"] == 0
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM ofis_no_sayaclari")[0]["n"] == 0
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM cases WHERE ofis_no_kodu IS NOT NULL")[0]["n"] == 0


@pg_test
def test_kapi_desen_disi_numarayi_ve_envanter_farkini_raporlar(pg, pg_engine):
    _kart_ekle(pg, ESKI_D1, [("Dr. Mehmet Öztürk", "Doktor")])
    db = pg()
    try:
        hatalar = goc.kapi_kontrolu(db, (2, 0, 0))
    finally:
        db.close()
    assert len(hatalar) == 2 and "envanter" in hatalar[0] and "desen dışı 1" in hatalar[1]


@pg_test
def test_muvekkilsiz_kart_atlanir_eski_numarasiyla_kalir(pg, pg_engine):
    """Kullanıcı kararı 30.09: müvekkilsiz kart göçü DURDURMAZ, eski numarasıyla kalır."""
    _ornek_veri(pg)
    _kart_ekle(pg, "S1.AK.........0007.HUKUK.00000", [])
    once = _numaralar(pg_engine)

    kuru = goc.kos(pg)
    assert len(kuru.durumdakiler("MUVEKKILSIZ")) == 1 and kuru.degisen == 6
    assert "S1.AK.........0007.HUKUK.00000" in goc.ozet_metni(kuru)
    assert _numaralar(pg_engine) == once

    sonuc = goc.kos(pg, apply=True)
    sonra = _numaralar(pg_engine)
    assert len(sonuc.durumdakiler("MUVEKKILSIZ")) == 1 and sonuc.degisen == 6
    kalan = [n for n in sonra.values() if not goc.yeni_formatta(n)]
    assert kalan == ["S1.AK.........0007.HUKUK.00000"]
    assert _satirlar(
        pg_engine, "SELECT count(*) AS n FROM case_history WHERE old_value = 'S1.AK.........0007.HUKUK.00000'"
    )[0]["n"] == 0
    # İkinci koşu da durmaz, atlanan kart yine atlanır.
    ikinci = goc.kos(pg, apply=True)
    assert ikinci.degisen == 0 and _numaralar(pg_engine) == sonra


@pg_test
def test_kapi_muaf_olmayan_desen_disi_numarayi_yakalar(pg):
    _ornek_veri(pg)
    db = pg()
    try:
        tum = goc.envanter(db)
        hatalar = goc.kapi_kontrolu(db, tum, frozenset())
        muaf = frozenset(str(n) for (n,) in db.execute(text("SELECT tracking_no FROM cases")))
        assert hatalar and "desen dışı" in hatalar[-1]
        assert goc.kapi_kontrolu(db, tum, muaf) == []
    finally:
        db.close()


@pg_test
def test_ikinci_kosu_sifir_degisiklik(pg, pg_engine):
    _ornek_veri(pg)
    goc.kos(pg, apply=True)
    once = _numaralar(pg_engine)
    tarihce = _satirlar(pg_engine, "SELECT count(*) AS n FROM case_history")[0]["n"]
    sayaclar = _satirlar(pg_engine, "SELECT kod, son_sira FROM ofis_no_sayaclari ORDER BY kod")

    ikinci = goc.kos(pg, apply=True)

    assert ikinci.degisen == 0 and len(ikinci.durumdakiler("ZATEN_YENI")) == 6
    assert (ikinci.foy_cevrilen, ikinci.sayaclar) == (0, {})
    assert _numaralar(pg_engine) == once
    assert _satirlar(pg_engine, "SELECT count(*) AS n FROM case_history")[0]["n"] == tarihce
    assert _satirlar(pg_engine, "SELECT kod, son_sira FROM ofis_no_sayaclari ORDER BY kod") == sayaclar


@pg_test
def test_goc_sonrasi_acilan_eski_formatli_kart_sayactan_devam_eder(pg, pg_engine):
    _ornek_veri(pg)
    goc.kos(pg, apply=True)
    yeni_id = _kart_ekle(pg, "S3.AXA........0003.HUKUK.00000", [("AXA Sigorta A.Ş.", None)], acilis=date(2019, 1, 1))

    sonuc = goc.kos(pg, apply=True)

    assert sonuc.degisen == 1
    # Açılış tarihi en eski olsa da verilmiş numaralar değişmez: sıra en yüksekten devam eder.
    assert _numaralar(pg_engine)[yeni_id] == "AXA-0003-HUK"
    assert _satirlar(pg_engine, "SELECT son_sira FROM ofis_no_sayaclari WHERE kod = 'AXA'")[0]["son_sira"] == 3
