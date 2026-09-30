"""G239 — eski ofis no formatını ayrıştıran kodun karar 023'e uyarlanması.

Kilitlenen iddialar (görev kabul kriterleri):

* üretim kodunda numarayı KONUMLA ayrıştıran ifade kalmadı (kaynak taraması);
* `cevapli_kart_eslemesi` eski VE yeni formatlı cevabı tanır, eski numara göç
  eşlemesiyle (göç raporu CSV'si ya da `case_history` izi) kartın bugünkü numarasına çözülür;
* mükerrer kart raporu göç ÖNCESİ ve SONRASI aynı çiftleri/grupları bulur — ölçü
  numaranın isim bloğu değil `cases.ofis_no_kodu`;
* `kartsiz_foy_kart_ac` yeni formatta ve SAYAÇTAN numara verir (sigortalı bloğu dahil);
* kart ayırmada "kartta kalan grup" `ofis_no_kodu` ile seçilir;
* `/api/cases/client-sequence` 404; eski üretici scriptler çalıştırılınca hata ile çıkar.

Sentetik veri (A.2): sqlite + elde yazılmış satırlar; gerçek paket/cevap dosyası yok.
"""
import csv
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
from database import Base
from managers import case_manager
from scripts import birlesik_kart_ayir as bka
from scripts import cevapli_kart_eslemesi as ce
from scripts import kartsiz_foy_kart_ac as kk
from scripts import mukerrer_kart_raporu as rapor
from scripts import ofis_no_gocu
from services import ofis_no

BACKEND = Path(__file__).resolve().parents[1]

ESKI_AXA = "S3.AXA........2915.IDARE.00000"
ESKI_AXA_EKLI = "S3.AXA........2754.HUKUK.00000-2"
YENI_AXA = "AXA-2915-DR.E.ALTUNC-IDR"
YENI_DOKTOR = "DR.M.OZTURK-0003-HUK"


@pytest.fixture()
def db_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = fabrika()
    try:
        for kod, ad, anahtarlar in ofis_no.VARSAYILAN_SIGORTA_KODLARI:
            db.add(models.SigortaKisaKodu(kod=kod, ad=ad, eslesme_anahtarlari=list(anahtarlar), aktif=True))
        db.commit()
    finally:
        db.close()
    yield fabrika
    engine.dispose()


# ─── Kaynak taraması (kabul 1) ───────────────────────────────────────────────

def test_uretim_kodunda_numarayi_konumla_ayristiran_ifade_kalmadi():
    """Kabul kriterindeki `rg` deseninin birebir karşılığı (tests/ hariç tüm backend)."""
    desen = re.compile(r"substr\(.*tracking_no|tracking_no\[3:13\]|split\(\"\.\"\)\[1\]")
    bulunan = []
    for yol in sorted(BACKEND.rglob("*.py")):
        goreli = yol.relative_to(BACKEND)
        if goreli.parts[0] in ("tests", "__pycache__", "data", "calibration"):
            continue
        for no, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), start=1):
            if desen.search(satir):
                bulunan.append(f"{goreli.as_posix()}:{no}")
    assert bulunan == []


def test_eski_sira_fonksiyonlari_ve_isim_blogu_yardimcilari_kalkti():
    from routes import cases as cases_route

    assert not hasattr(cases_route, "max_tracking_sequence")
    assert not hasattr(cases_route, "get_client_case_sequence")
    assert not hasattr(rapor, "_isim_blogu")
    assert not hasattr(kk, "isim_blogu") and not hasattr(kk, "rt")


# ─── client-sequence ucu (kabul 5) ───────────────────────────────────────────

def test_client_sequence_ucu_404_ve_semada_yok():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from routes import cases as cases_route

    app = FastAPI()
    app.include_router(cases_route.router)
    app.dependency_overrides[get_current_user] = lambda: {"name": "T", "preferred_username": "t@x", "tid": "t1"}
    app.dependency_overrides[get_current_tenant] = lambda: "t1"
    client = TestClient(app, raise_server_exceptions=False)

    for params in ({"client_name": "Ahmet Yılmaz"}, {"client_name": "x", "name_block": "ABCDEFGHIJ"}, {}):
        r = client.get("/api/cases/client-sequence", params=params)
        assert r.status_code == 404, r.text          # 422 değil: yol {case_id} kalıbına düşmüyor
        assert "sequence" not in r.json()
    assert "/api/cases/client-sequence" not in client.get("/openapi.json").json()["paths"]


# ─── Index düşürme (kabul 6) ─────────────────────────────────────────────────

def test_isim_blogu_indexi_dusurulur_yaratilmaz_idempotent():
    ad = "idx_cases_tracking_name_block"
    ifadeler = [sql for op in database._MIGRATIONS if op[0] == "index" for sql in op[2] if ad in sql]
    assert ifadeler == [f"DROP INDEX IF EXISTS {ad}"]            # tek ifade, IF EXISTS → ikinci açılışta da geçer
    assert ad in database._DUSURULECEK_INDEXLER["cases"]
    assert all(ad not in str(tanim) for tanim in database._TRGM_INDEXES)


# ─── Cevaplı eşleme: iki format + eski → yeni (kabul 2) ──────────────────────

@pytest.mark.parametrize("cevap, beklenen", [
    (YENI_AXA, YENI_AXA),                                          # sigortacı + sigortalı
    (f"{YENI_DOKTOR} (teyit edildi)", YENI_DOKTOR),                # kişi müvekkil + not
    ("kart: KR.ENTHONE-0015-CEZ.", "KR.ENTHONE-0015-CEZ"),         # kurum, sonda nokta
    ("SG-0001-HUK", "SG-0001-HUK"),                                # listede olmayan sigortacı
    ("HS.MADONNA-12345-ARB", "HS.MADONNA-12345-ARB"),              # 9999'dan sonra uzayan sıra
    (ESKI_AXA, ESKI_AXA),                                          # eski biçim hâlâ tanınır
    (f"{ESKI_AXA_EKLI} (teyit)", ESKI_AXA_EKLI),
])
def test_cevap_eski_ve_yeni_formati_tanir(cevap, beklenen):
    satir = ce.cevabi_coz("F-1", cevap)
    assert (satir.durum, satir.tracking_no) == (ce.DURUM_KART, beklenen)
    assert ofis_no_gocu.yeni_formatta(beklenen) is not ce.eski_formatta(beklenen)


@pytest.mark.parametrize("metin", ["2024-0123-HUK", "emin değiliz - 2024", "ABC-12-HUK", "dr.m.ozturk-0003-huk"])
def test_numara_olmayan_metin_kart_no_sayilmaz(metin):
    assert ce.cevabi_coz("F-1", metin).durum == ce.DURUM_COZULEMEDI


def test_eski_numara_goc_eslemesiyle_yeni_karta_cozulur(caplog):
    goc = {ESKI_AXA: YENI_AXA, "S3.M_ISIK.....0001.IDARE.00000": "AXA-0001-DR.M.ISIK-IDR"}
    kartlar = [ce.KartSatiri(ESKI_AXA), ce.KartSatiri("S3.M_ISIK.....0001.IDARE.00000")]

    satir = ce.cevabi_coz("F-1", f"{ESKI_AXA} — eski listeden", oneri=ESKI_AXA, kartlar=kartlar, goc_eslemesi=goc)
    assert (satir.durum, satir.tracking_no) == (ce.DURUM_KART, YENI_AXA)
    assert f"eski numara {ESKI_AXA}" in satir.kaynak_not and "öneriyle aynı" in satir.kaynak_not
    assert "aday kartları dışında" not in satir.kaynak_not       # adaylar da çevrildi

    # yeni numarayla gelen cevap eşlemeye hiç bakmaz
    yeni = ce.cevabi_coz("F-2", YENI_AXA, oneri=ESKI_AXA, kartlar=kartlar, goc_eslemesi=goc)
    assert yeni.tracking_no == YENI_AXA and "öneriyle aynı" in yeni.kaynak_not
    assert "eski numara" not in yeni.kaynak_not

    # eşleme verilmemişse (göç öncesi) eski numara olduğu gibi kalır — eski davranış
    assert ce.cevabi_coz("F-3", ESKI_AXA).tracking_no == ESKI_AXA

    # eşlemede olmayan eski numara: tahmin YOK, olduğu gibi + uyarı
    with caplog.at_level(logging.WARNING, logger="CevapliKartEslemesi"):
        yok = ce.cevabi_coz("F-4", ESKI_AXA_EKLI, goc_eslemesi=goc)
    assert yok.tracking_no == ESKI_AXA_EKLI and "göç eşlemesinde yok" in yok.kaynak_not
    assert any("F-4" in r.getMessage() and "göç eşlemesinde yok" in r.getMessage() for r in caplog.records)


def test_muvekkil_cevabinda_secilen_eski_kart_da_cevrilir():
    from party_check import normalize_party_key

    kartlar = [ce.KartSatiri(ESKI_AXA, {normalize_party_key("Axa Sigorta A.Ş.")})]
    satir = ce.cevabi_coz("F-1", "MÜVEKKİL: Axa Sigorta A.Ş.", kartlar=kartlar, goc_eslemesi={ESKI_AXA: YENI_AXA})
    assert (satir.durum, satir.tracking_no) == (ce.DURUM_MUVEKKIL, YENI_AXA)


def test_goc_eslemesi_csv_ve_db_kaynaklari(db_env, tmp_path):
    # (a) göç raporu CSV'si — `ofis_no_gocu.raporlari_yaz` başlıkları
    yol = tmp_path / "ofis_no_esleme_x.csv"
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "eski", "yeni", "silinmis", "kategori_kaynagi", "sigortali_kaynagi"])
        w.writerow([1, ESKI_AXA, YENI_AXA, 0, "muvekkil_kaydi", "foy"])
    assert ce.goc_eslemesini_oku(yol) == {ESKI_AXA: YENI_AXA}
    with pytest.raises(ce.ha.AktarimHatasi, match="yok"):
        ce.goc_eslemesini_oku(tmp_path / "yok.csv")
    bozuk = tmp_path / "bozuk.csv"
    bozuk.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ce.ha.AktarimHatasi, match="eski, yeni"):
        ce.goc_eslemesini_oku(bozuk)

    # (b) DB izi: göçün `case_history` satırı → kartın BUGÜNKÜ numarası
    db = db_env()
    try:
        kart = models.Case(tracking_no=YENI_AXA, ofis_no_kodu="AXA", ofis_no_sira=2915)
        baska = models.Case(tracking_no=YENI_DOKTOR, ofis_no_kodu="DR.M.OZTURK", ofis_no_sira=3)
        db.add_all([kart, baska])
        db.flush()
        db.add(models.CaseHistory(case_id=kart.id, field_name="tracking_no", old_value=ESKI_AXA,
                                  new_value="AXA-2915-IDR", changed_by="ofis_no_gocu", source=ce.GOC_KAYNAGI))
        # göç dışı numara değişikliği eşlemeye GİRMEZ
        db.add(models.CaseHistory(case_id=baska.id, field_name="tracking_no", old_value="ELLE-1",
                                  new_value=YENI_DOKTOR, changed_by="panel", source=None))
        db.commit()
    finally:
        db.close()
    assert ce.GOC_KAYNAGI == ofis_no_gocu.KAYNAK
    assert ce.goc_eslemesi_db(db_env) == {ESKI_AXA: YENI_AXA}     # new_value değil, güncel numara


def _cevap_xlsx(yol, gruplar):
    from openpyxl import Workbook

    basliklar = ["Grup", "Satır türü", "SistemNo / Kart No", "Müvekkil", "HukuDok öneri kart",
                 "CEVABINIZ (hangi kart / not)"]
    wb = Workbook()
    ws = wb.active
    ws.title = ce.SAYFA
    ws.append(basliklar)
    for no, (sistem_no, cevap, oneri, kartlar) in enumerate(gruplar, start=1):
        ws.append([no, "FÖY (paket)", sistem_no, "Axa Sigorta A.Ş.", oneri, cevap])
        for kart_no, muvekkil in kartlar:
            ws.append([no, "KART (HukuDok)", kart_no, muvekkil, None, None])
    wb.save(yol)
    wb.close()
    return Path(yol)


def test_cli_goc_esleme_ile_csv_yeni_numarayi_tasir(tmp_path, capsys):
    xlsx = _cevap_xlsx(tmp_path / "cevap.xlsx", [
        ("id-1", ESKI_AXA, ESKI_AXA, [(ESKI_AXA, "Axa Sigorta A.ş.")]),          # eski numarayla cevap
        ("id-2", YENI_DOKTOR, None, [(YENI_DOKTOR, "Mehmet Öztürk Dr.")]),       # yeni numarayla cevap
    ])
    goc = tmp_path / "goc.csv"
    goc.write_text(f"case_id,eski,yeni\n1,{ESKI_AXA},{YENI_AXA}\n", encoding="utf-8")
    cikti = tmp_path / "harita.csv"

    assert ce.main(["--input", str(xlsx), "--output", str(cikti), "--goc-esleme", str(goc)]) == ce.ha.CIKIS_TAMAM
    assert ce.ha.kart_eslemesini_oku(cikti) == {"id-1": YENI_AXA, "id-2": YENI_DOKTOR}
    assert "kart no ile        : 2" in capsys.readouterr().out
    # eşlemesiz koşu eski numarayı olduğu gibi bırakır (göç öncesi kullanım)
    assert ce.main(["--input", str(xlsx), "--output", str(cikti)]) == ce.ha.CIKIS_TAMAM
    assert ce.ha.kart_eslemesini_oku(cikti) == {"id-1": ESKI_AXA, "id-2": YENI_DOKTOR}


# ─── Mükerrer kart raporu: göç öncesi = göç sonrası (kabul 3) ────────────────

MAHKEME = "Ankara 2. Asliye Hukuk Mahkemesi"
# (etiket, esas, müvekkil adı, müvekkil kategorisi, sigortalı hekim, eski numara, yeni numara, kod)
KARTLAR = [
    ("g1", "2024/10", "Betül Gürer Dr.", "Doktor", None,
     "D1.B_GURER....0001.HUKUK.00000", "DR.B.GURER-0001-HUK", "DR.B.GURER"),
    ("g2", "2024/10", "Betül Gürer Dr.", "Doktor", None,
     "D1.B_GURER....0002.HUKUK.00000", "DR.B.GURER-0002-HUK", "DR.B.GURER"),
    # aynı dava, FARKLI müvekkil → grup var, şüphe yok
    ("f1", "2024/20", "Betül Gürer Dr.", "Doktor", None,
     "D1.B_GURER....0003.HUKUK.00000", "DR.B.GURER-0003-HUK", "DR.B.GURER"),
    ("f2", "2024/20", "Axa Sigorta A.Ş.", "Sigorta Şirketi", "Emre Altunç Dr.",
     "S3.AXA........0001.HUKUK.00000", "AXA-0001-DR.E.ALTUNC-HUK", "AXA"),
    # aynı dava, aynı sigortacı, FARKLI sigortalı → şüphe listesinde, hüküm FARKLI_SIGORTALI
    ("s1", "2024/30", "Axa Sigorta A.Ş.", "Sigorta Şirketi", "Nadir Yıldırım Dr.",
     "S3.AXA........0002.HUKUK.00000", "AXA-0002-DR.N.YILDIRIM-HUK", "AXA"),
    ("s2", "2024/30", "Axa Sigorta A.Ş.", "Sigorta Şirketi", "Semra Külekçi Dr.",
     "S3.AXA........0003.HUKUK.00000", "AXA-0003-DR.S.KULEKCI-HUK", "AXA"),
    # başka dava: hiçbir gruba girmez
    ("y1", "2024/40", "Betül Gürer Dr.", "Doktor", None,
     "D1.B_GURER....0004.HUKUK.00000", "DR.B.GURER-0004-HUK", "DR.B.GURER"),
]


def _rapor_kumeleri(fabrika, dizin):
    ozet = rapor.raporu_uret(fabrika, dizin)
    supheli_yol, envanter_yol = ozet["raporlar"]
    with open(supheli_yol, newline="", encoding="utf-8-sig") as f:
        supheli = {(int(s["kart_a"]), int(s["kart_b"]), s["hukum"]) for s in csv.DictReader(f, delimiter=";")}
    gruplar = {}
    with open(envanter_yol, newline="", encoding="utf-8-sig") as f:
        for s in csv.DictReader(f, delimiter=";"):
            gruplar.setdefault((s["grup"], s["tek_muvekkil"]), set()).add(int(s["kart_id"]))
    return supheli, {(frozenset(u), tek) for (_g, tek), u in gruplar.items()}


def test_mukerrer_raporu_goc_oncesi_ve_sonrasi_ayni_gruplari_bulur(db_env, tmp_path):
    db = db_env()
    try:
        musteriler = {}
        idler = {}
        for etiket, esas, muvekkil, kategori, sigortali, eski, _yeni, _kod in KARTLAR:
            if muvekkil not in musteriler:
                musteriler[muvekkil] = models.Client(name=muvekkil, category=kategori)
                db.add(musteriler[muvekkil])
                db.flush()
            kart = models.Case(tracking_no=eski, status="DERDEST", file_type="Hukuk", court=MAHKEME, esas_no=esas)
            db.add(kart)
            db.flush()
            db.add(models.CaseParty(case_id=kart.id, name=muvekkil, role="Müvekkil", party_type="CLIENT",
                                    client_id=musteriler[muvekkil].id))
            db.add(models.CaseParty(case_id=kart.id, name="Songül Kaya", role="Davacı", party_type="COUNTER"))
            if sigortali:
                db.add(models.CaseParty(case_id=kart.id, name=sigortali, role="Sigortalı", party_type="THIRD"))
            idler[etiket] = kart.id
        db.commit()
    finally:
        db.close()

    once = _rapor_kumeleri(db_env, tmp_path / "once")

    # Göç: numaralar yeni formata, kod kolonu dolar (scripts/ofis_no_gocu.uygula'nın yazdıkları).
    db = db_env()
    try:
        for etiket, _esas, _m, _k, _s, _eski, yeni, kod in KARTLAR:
            db.query(models.Case).filter(models.Case.id == idler[etiket]).update(
                {"tracking_no": yeni, "ofis_no_kodu": kod, "ofis_no_sira": int(yeni.split("-")[1])})
        db.commit()
    finally:
        db.close()

    sonra = _rapor_kumeleri(db_env, tmp_path / "sonra")

    assert once == sonra
    supheli, gruplar = sonra
    assert supheli == {
        (idler["g1"], idler["g2"], "SIGORTALI_KARSILASTIRILAMADI"),
        (idler["s1"], idler["s2"], "FARKLI_SIGORTALI"),          # sigortalı koda katılmaz, hükümde ayrılır
    }
    assert gruplar == {
        (frozenset({idler["g1"], idler["g2"]}), "EVET"),
        (frozenset({idler["f1"], idler["f2"]}), "HAYIR"),
        (frozenset({idler["s1"], idler["s2"]}), "EVET"),
    }


def test_kart_kodu_kolondan_kolon_bossa_muvekkilden():
    from types import SimpleNamespace as NS

    kolonlu = NS(ofis_no_kodu="AXA", tracking_no="HERHANGI", parties=[])
    assert kk.kart_kodu(kolonlu) == "AXA"
    doktor = NS(ofis_no_kodu=None, tracking_no="D1.X_YANLIS...0001.HUKUK.00000", parties=[
        NS(name="Betül Gürer Dr.", party_type="CLIENT", client=NS(category="Doktor")),
        NS(name="Songül Kaya", party_type="COUNTER", client=None),
    ])
    assert kk.kart_kodu(doktor) == "DR.B.GURER"                  # numaradaki blok (X_YANLIS) okunmaz
    assert kk.kart_kodu(NS(ofis_no_kodu="  ", tracking_no="D1.B_GURER....0001.HUKUK.00000", parties=[])) == ""


# ─── Kartsız föy: yeni format + sayaç (kabul 4) ──────────────────────────────

BASLIKLAR = ["SistemNo", "Dosya No", "Müvekkil", "Müvekkil Tipi", "Ana Tür", "Durum", "Sigortalı"]


def _paket(yol, satirlar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(BASLIKLAR)
    for s in satirlar:
        ws.append([s.get(b) for b in BASLIKLAR])
    wb.save(yol)
    wb.close()
    return Path(yol)


def test_kartsiz_foy_yeni_formatta_ve_sayactan_numara_verir(db_env, tmp_path, monkeypatch):
    monkeypatch.setattr(case_manager, "SessionLocal", db_env)
    db = db_env()
    try:
        # DB'de ESKİ formatlı 0007 numaralı kart var: sıra ondan OKUNMAZ, sayaçtan gelir (2 → 3).
        db.add(models.Case(tracking_no="S3.AXA........0007.HUKUK.00000", status="MAHZEN", klasor_no_2="Z-1"))
        for _ in range(2):
            ofis_no.sira_tahsis_et(db, "AXA")
        db.commit()
    finally:
        db.close()
    paket = _paket(tmp_path / "p.xlsx", [
        {"SistemNo": "H-1", "Dosya No": "1.100.00", "Müvekkil": "Axa Sigorta A.Ş.", "Müvekkil Tipi": "Sigorta",
         "Ana Tür": "HUKUK", "Durum": "Aktif", "Sigortalı": "Dr. Emre Altunç"},
        {"SistemNo": "H-2", "Dosya No": "1.200.00", "Müvekkil": "Axa Sigorta A.Ş.", "Müvekkil Tipi": "Sigorta",
         "Ana Tür": "CEZA", "Durum": "Arşiv"},                                  # sigortalı yok → blok yazılmaz
        {"SistemNo": "H-3", "Dosya No": "2.300.00", "Müvekkil": "Ayşe Demir", "Müvekkil Tipi": "Diğer Sağlık Çalışanı",
         "Ana Tür": "HUKUK", "Durum": "Aktif"},
        {"SistemNo": "H-4", "Dosya No": "3.400.00", "Müvekkil": "Enthone Kimya San. ve Tic. A.Ş.",
         "Müvekkil Tipi": "Kurum", "Ana Tür": "İDARE", "Durum": "Aktif"},
    ])

    kuru = kk.kartlari_ac(db_env, girdi=paket)
    beklenen = {
        "1.100.00": "AXA-0003-DR.E.ALTUNC-HUK",
        "1.200.00": "AXA-0004-CEZ",
        "2.300.00": "SC.A.DEMIR-0001-HUK",
        "3.400.00": "KR.ENTHONE-0001-IDR",
    }
    assert {a.dosya_no: a.tracking_no for a in kuru} == beklenen
    assert all(ofis_no_gocu.yeni_formatta(a.tracking_no) and not a.hata for a in kuru)
    db = db_env()
    try:
        assert ofis_no.siradaki(db, "AXA") == 3 and db.query(models.Case).count() == 1   # kuru koşu: sayaç yanmadı
    finally:
        db.close()

    acilan = kk.kartlari_ac(db_env, girdi=paket, apply=True)
    assert {a.dosya_no: a.tracking_no for a in acilan} == beklenen and all(a.case_id for a in acilan)
    db = db_env()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="1.100.00").one()
        assert (kart.tracking_no, kart.ofis_no_kodu, kart.ofis_no_sira) == ("AXA-0003-DR.E.ALTUNC-HUK", "AXA", 3)
        assert ofis_no.siradaki(db, "AXA") == 5 and ofis_no.siradaki(db, "SC.A.DEMIR") == 2
        assert kk.kart_kodu(kart) == "AXA"
    finally:
        db.close()


# ─── Kart ayırma: kartta kalan grup kod kolonuyla (kapsam 1) ─────────────────

def _ham(sistem_no, dosya_no, tur, esas, muvekkil):
    return {"SistemNo": sistem_no, "DosyaNo": dosya_no, "Müvekkil": muvekkil, "Müvekkil Tipi": "Doktor",
            "Karşı Taraf": "Ayşe Yılmaz", "Yerel Mahkeme": "Ankara Arabuluculuk Bürosu", "Esas": esas,
            "Dava Tarihi": "2026-03-01", "Ana Tür": tur, "Durum": "Aktif", "Dava Konusu": "Tazminat"}


def _iki_muvekkilli(db_env, *, tracking, kod, muvekkil=None):
    db = db_env()
    try:
        k = models.Case(tracking_no=tracking, status="DERDEST", klasor_no_2="1110.003;1993.001",
                        file_type="Arabuluculuk", esas_no="2026/720", court="Ankara Arabuluculuk Bürosu",
                        ofis_no_kodu=kod)
        db.add(k)
        db.flush()
        if muvekkil:
            db.add(models.CaseParty(case_id=k.id, name=muvekkil, role="Müvekkil", party_type="CLIENT"))
        db.add(models.CaseFoy(sistem_no="ARB-1", case_id=k.id,
                              ham_veri=_ham("ARB-1", "1110.003", "ARABULUCULUK", "2026/720", "Deniz Esinler Dr.")))
        db.add(models.CaseFoy(sistem_no="ARB-2", case_id=k.id,
                              ham_veri=_ham("ARB-2", "1993.001", "ARABULUCULUK", "2026/720", "Aylin Ayrim Dr")))
        db.commit()
        return k.id
    finally:
        db.close()


@pytest.mark.parametrize("tracking, kod, muvekkil", [
    ("DR.A.AYRIM-0002-ARB", "DR.A.AYRIM", None),                       # göç sonrası: kod kolonu
    # Kolon numarayla ÇELİŞSE bile kolon kazanır — numara ayrıştırılmıyor (eski kod D_ESINLER derdi).
    ("D1.D_ESINLER..0002.ARABU.00000", "DR.A.AYRIM", None),
    ("D1.D_ESINLER..0002.ARABU.00000", None, "Aylin Ayrim Dr"),        # göç öncesi: kolon boş → müvekkil tarafı
])
def test_kart_ayirmada_kalan_grup_kod_kolonuyla_secilir(db_env, tracking, kod, muvekkil):
    """"En büyük grup" kuralı Deniz'i seçerdi (eşit boyda, anahtarı büyük olan) —
    Aylin'in kartta kalması yalnız kod/müvekkil eşleşmesiyle mümkün."""
    kart_id = _iki_muvekkilli(db_env, tracking=tracking, kod=kod, muvekkil=muvekkil)
    sonuc = bka.kos(db_env, kart_idler=[kart_id], apply=True, kim="test", muvekkil_ayrimi=True)
    assert sonuc.sayim("YAPILDI") == 1 and sonuc.yeni_kart_sayisi == 1
    db = db_env()
    try:
        assert {f.sistem_no for f in db.query(models.CaseFoy).filter_by(case_id=kart_id)} == {"ARB-2"}
        yeni_id, yeni_no, sistem_nolar = sonuc.kalemler[0].yeni_kartlar[0]
        yeni = db.get(models.Case, yeni_id)
        assert sistem_nolar == ["ARB-1"] and yeni_no == "DR.D.ESINLER-0001-ARB"
        assert (yeni.ofis_no_kodu, yeni.ofis_no_sira) == ("DR.D.ESINLER", 1)
    finally:
        db.close()


# ─── Emekli üreticiler ───────────────────────────────────────────────────────

@pytest.mark.parametrize("script", ["retag_tracking_nos.py", "import_excel_cases.py"])
def test_eski_ureticiler_emekli_calistirilinca_hata_ile_cikar(script):
    yol = BACKEND / "scripts" / script
    kaynak = yol.read_text(encoding="utf-8")
    assert kaynak.lstrip().startswith('"""\nEMEKLİ — ÇALIŞTIRMA')
    # Çıkış DB/.env/Excel'e dokunan import'lardan ÖNCE: yan etkisiz ret.
    assert kaynak.index("sys.exit(EMEKLI_MESAJI)") < kaynak.index("load_dotenv")

    sonuc = subprocess.run([sys.executable, str(yol), "--dry-run"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(BACKEND), timeout=60)
    assert sonuc.returncode != 0
    assert "EMEKL" in sonuc.stderr and "karar 023" in sonuc.stderr
