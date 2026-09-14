"""G196 — Dava durumu yazma yollarında üçlü kapısı: üçlü dışı değer 400, veritabanına gitmez.

G195 `cases.status` üzerine `CHECK (status IN CASE_STATUSES) NOT VALID` koydu; yazma
yolları buna hazır değildi. Üçlü dışı serbest metin (`"Arşivde"`):

* `add_case` — status'u normalize etmeden yazıyordu → `CheckViolation` → `Add Case Error`
  ERROR + `None` → `POST /api/cases` 500,
* `update_case` — `normalize_case_status` tanımadığı metni olduğu gibi döndürür →
  commit'te `CheckViolation` → `Update Case Error` ERROR + `False` → `PUT` 500,
* `update_case_tracking` — aynı desen → ERROR + `False` → takip ucu yanıltıcı 404.

Kapı artık veritabanından ÖNCE (`constants.validated_case_status`): eski değer (TEMYIZ,
KAPALI, ...) üçlüye çevrilir, aşama taşınır (karar 020); üçlü dışı `InvalidCaseStatusError`
yükselir → `api.py` 400. Hiçbir alan yazılmaz, ERROR basılmaz (istemci hatası nihai sistem
başarısızlığı değildir — log sözleşmesi).

Katmanlar:
1. DB'siz — kapı yardımcısı; `normalize_case_status` sözleşmesi DEĞİŞMEDİ.
2. sqlite (StaticPool, CHECK yok) — üç yönetici fonksiyonu: kısıt olmasa bile serbest metin
   yazılmaz (kapı uygulamada), kısmi yazım/tarihçe yok; eski değer üçlü + aşama.
3. dbtest (scratch Postgres, G195 kısıtı yerinde; `test_migration_path` altyapısı, gerçek
   `hukudok` DB'sine asla yazılmaz, DB yoksa SKIP) — üç HTTP yolu 400; engine `handle_error`
   dinleyicisi `CheckViolation`'a HİÇ ulaşılmadığını, caplog ERROR yokluğunu doğrular (iki
   kanıt aracı da bir kontrol testiyle boş geçmediği gösterilir).
"""
import logging
from types import SimpleNamespace

import pytest
from psycopg2 import errors as pg_errors
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import test_migration_path as mig
from constants import CASE_STATUSES, normalize_case_status
from managers import case_manager

# Scratch DB fixture'ı `test_migration_path`'ten yeniden kullanılır (test_g195 deseni).
admin_engine = mig.admin_engine

SERBEST = "Arşivde"


def _errorlar(caplog):
    return [kayit.getMessage() for kayit in caplog.records if kayit.levelno >= logging.ERROR]


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — kapı yardımcısı
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ham,beklenen", [
    ("DERDEST", ("DERDEST", None)),
    ("danış", ("DANIŞ", None)),
    ("DANIS", ("DANIŞ", None)),
    ("Mahzen", ("MAHZEN", None)),
    ("TEMYIZ", ("DERDEST", "TEMYIZ")),          # eski değer: üçlü + korunacak aşama
    ("KAPALI", ("MAHZEN", "KAPALI")),
    ("Arşiv", ("MAHZEN", None)),                # teslim yazımı
    ("", (None, None)),                         # boş: çağıran kendi varsayılanını uygular
    ("   ", (None, None)),
    (None, (None, None)),
])
def test_kapi_ucluyu_ve_eski_degeri_normalize_eder(ham, beklenen):
    from constants import validated_case_status

    assert validated_case_status(ham) == beklenen


@pytest.mark.parametrize("ham", [SERBEST, "Bilinmeyen Durum", "TEMYİZDE", " 0 "])
def test_kapi_uclu_disini_reddeder_normalize_sozlesmesi_degismez(ham):
    from constants import InvalidCaseStatusError, validated_case_status

    with pytest.raises(InvalidCaseStatusError) as exc:
        validated_case_status(ham)
    # ValueError alt sınıfı (stage_decisions.InvalidDecisionStatusError deseni)
    assert isinstance(exc.value, ValueError)
    mesaj = str(exc.value)
    assert repr(ham.strip()) in mesaj
    assert all(durum in mesaj for durum in CASE_STATUSES)
    # normalize_case_status kendi sözleşmesini korur: tanımadığını olduğu gibi döndürür
    assert normalize_case_status(ham) == (ham.strip(), None)


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite — yönetici fonksiyonları (CHECK kısıtı YOK: kapı uygulamada olmalı)
# ═══════════════════════════════════════════════════════════════════════════

_IZLENEN = ("tracking_no", "status", "case_stage", "court", "subject", "esas_no", "karar_no", "updated_at")


@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _yeni_dava(**alanlar) -> dict:
    data = {
        "tracking_no": "HA.G196.0001.2026", "court": "Ankara 1. Asliye Hukuk Mahkemesi",
        "subject": "Tazminat", "esas_no": "2026/1", "parties": [], "lawyers": [],
    }
    data.update(alanlar)
    return data


def _mevcut_dava(Fabrika) -> int:
    db = Fabrika()
    try:
        case = models.Case(
            tracking_no="HA.G196.0002.2026", status="DERDEST", court="X Mahkemesi",
            subject="Eski konu", maddi_tazminat=0, manevi_tazminat=0,
        )
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _kart_sayisi(Fabrika) -> int:
    db = Fabrika()
    try:
        return db.query(models.Case).count()
    finally:
        db.close()


def _fotograf(Fabrika, cid) -> dict:
    db = Fabrika()
    try:
        kart = db.get(models.Case, cid)
        return {alan: getattr(kart, alan) for alan in _IZLENEN}
    finally:
        db.close()


def _yan_kayitlar(Fabrika, cid) -> tuple:
    """(case_history, case_stage_logs) satır sayıları."""
    db = Fabrika()
    try:
        return (
            db.query(models.CaseHistory).filter(models.CaseHistory.case_id == cid).count(),
            db.query(models.CaseStageLog).filter(models.CaseStageLog.case_id == cid).count(),
        )
    finally:
        db.close()


def test_add_case_uclu_disi_deger_kart_acmaz_error_basmaz(fabrika, caplog):
    from constants import InvalidCaseStatusError

    with caplog.at_level(logging.WARNING):
        with pytest.raises(InvalidCaseStatusError):
            case_manager.add_case(_yeni_dava(status=SERBEST))
    assert _kart_sayisi(fabrika) == 0
    assert _errorlar(caplog) == []


@pytest.mark.parametrize("gelen,beklenen", [
    ({"status": "TEMYIZ"}, ("DERDEST", "TEMYIZ")),      # aşama boş → eski değer oraya
    ({"status": "KAPALI"}, ("MAHZEN", "KAPALI")),
    ({"status": "danış"}, ("DANIŞ", None)),
    ({"status": "TEMYIZ", "case_stage": "ISTINAF"}, ("DERDEST", "ISTINAF")),   # istek aşaması kazanır
    ({}, ("DERDEST", None)),                            # status verilmezse DERDEST (mevcut)
    ({"status": None}, ("DERDEST", None)),
    ({"status": ""}, ("DERDEST", None)),
])
def test_add_case_eski_degeri_ucluye_ceker_asamayi_tasir(fabrika, gelen, beklenen):
    sonuc = case_manager.add_case(_yeni_dava(**gelen))
    assert sonuc and "id" in sonuc, sonuc
    assert sonuc["status"] == beklenen[0]
    kart = _fotograf(fabrika, sonuc["id"])
    assert (kart["status"], kart["case_stage"]) == beklenen


def test_update_case_uclu_disi_deger_hicbir_alani_yazmaz(fabrika, caplog):
    from constants import InvalidCaseStatusError

    cid = _mevcut_dava(fabrika)
    once = _fotograf(fabrika, cid)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(InvalidCaseStatusError):
            case_manager.update_case(cid, {
                "status": SERBEST, "court": "Y Mahkemesi", "subject": "Yeni konu", "esas_no": "2026/9",
            }, changed_by="avukat")
    assert _fotograf(fabrika, cid) == once
    assert _yan_kayitlar(fabrika, cid) == (0, 0)
    assert _errorlar(caplog) == []


def test_update_case_olmayan_dava_once_404_anlamini_korur(fabrika):
    assert case_manager.update_case(999, {"status": SERBEST}) is None


def test_update_case_tracking_uclu_disi_deger_hicbir_alani_yazmaz(fabrika, caplog):
    from constants import InvalidCaseStatusError

    cid = _mevcut_dava(fabrika)
    once = _fotograf(fabrika, cid)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(InvalidCaseStatusError):
            # case_stage/karar_no status'tan ÖNCE/SONRA işlenen alanlar: kısmi yazım olmamalı
            case_manager.update_case_tracking(
                cid, {"case_stage": "KARAR", "karar_no": "2026/7", "status": SERBEST}, changed_by="avukat",
            )
    assert _fotograf(fabrika, cid) == once
    assert _yan_kayitlar(fabrika, cid) == (0, 0)
    assert _errorlar(caplog) == []


def test_update_case_tracking_none_alani_temizler_mevcut_davranis(fabrika):
    cid = _mevcut_dava(fabrika)
    assert case_manager.update_case_tracking(cid, {"status": None}, changed_by="avukat") is True
    assert _fotograf(fabrika, cid)["status"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. dbtest — scratch Postgres, G195 kısıtı yerinde, HTTP yolları
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_engine(admin_engine):
    with mig._scratch_database(admin_engine, "g196") as engine:
        mig._run_init_db(engine)
        yield engine


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın (test_g103 deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter

    hatalar: list = []

    def _kaydet(ctx):
        hatalar.append(ctx.original_exception)

    event.listen(pg_engine, "handle_error", _kaydet)
    Fabrika = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield SimpleNamespace(client=TestClient(app), engine=pg_engine, hatalar=hatalar)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()
        event.remove(pg_engine, "handle_error", _kaydet)


def _pg_satir(pg, tracking_no):
    with pg.engine.connect() as conn:
        satir = conn.execute(text(
            "SELECT id, status, case_stage, court, subject, esas_no, karar_no, updated_at "
            "FROM cases WHERE tracking_no = :t"
        ), {"t": tracking_no}).mappings().first()
    return dict(satir) if satir is not None else None


def _pg_yan_kayitlar(pg, cid) -> tuple:
    """(case_history, case_stage_logs, case_esas_numbers) satır sayıları."""
    with pg.engine.connect() as conn:
        return tuple(
            conn.execute(text(f"SELECT count(*) FROM {tablo} WHERE case_id = :id"), {"id": cid}).scalar()
            for tablo in ("case_history", "case_stage_logs", "case_esas_numbers")
        )


def _pg_dava_ac(pg, tracking_no) -> int:
    r = pg.client.post("/api/cases", json={
        "tracking_no": tracking_no, "court": "X Mahkemesi", "subject": "Eski konu", "esas_no": "2026/1",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.dbtest
def test_pg_kanit_araclari_bos_gecmez(pg, caplog):
    """Kontrol: kısıt yerinde ve dinleyici/log yakalama gerçekten çalışıyor — yoksa
    aşağıdaki "CheckViolation yok" ve "ERROR yok" iddiaları boşa geçerdi."""
    with pytest.raises(IntegrityError):
        with pg.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO cases (tracking_no, status) VALUES ('G196/KONTROL', :s)"), {"s": SERBEST},
            )
    assert len(pg.hatalar) == 1 and isinstance(pg.hatalar[0], pg_errors.CheckViolation), pg.hatalar

    with caplog.at_level(logging.WARNING):
        logging.getLogger("AdminManager").error("kontrol")   # case_manager'ın logger'ı
    assert _errorlar(caplog) == ["kontrol"]


@pytest.mark.dbtest
def test_pg_post_uclu_disi_400_kart_yok_check_yok_error_yok(pg, caplog):
    with caplog.at_level(logging.WARNING):
        r = pg.client.post("/api/cases", json={"tracking_no": "G196/POST", "status": SERBEST, "court": "X"})
    assert r.status_code == 400, r.text
    detay = r.json()["detail"]
    assert SERBEST in detay and all(durum in detay for durum in CASE_STATUSES), detay
    assert _pg_satir(pg, "G196/POST") is None
    assert pg.hatalar == []
    assert _errorlar(caplog) == []


@pytest.mark.dbtest
def test_pg_post_eski_deger_derdest_asama_ve_varsayilan(pg):
    r = pg.client.post("/api/cases", json={"tracking_no": "G196/TEMYIZ", "status": "TEMYIZ"})
    assert r.status_code == 200, r.text
    satir = _pg_satir(pg, "G196/TEMYIZ")
    assert (satir["status"], satir["case_stage"]) == ("DERDEST", "TEMYIZ")

    r = pg.client.post("/api/cases", json={"tracking_no": "G196/VARSAYILAN"})
    assert r.status_code == 200, r.text
    satir = _pg_satir(pg, "G196/VARSAYILAN")
    assert (satir["status"], satir["case_stage"]) == ("DERDEST", None)
    assert pg.hatalar == []


@pytest.mark.dbtest
def test_pg_put_uclu_disi_400_hicbir_alan_degismez(pg, caplog):
    cid = _pg_dava_ac(pg, "G196/PUT")
    once = _pg_satir(pg, "G196/PUT")
    yan_once = _pg_yan_kayitlar(pg, cid)

    with caplog.at_level(logging.WARNING):
        r = pg.client.put(f"/api/cases/{cid}", json={
            "tracking_no": "G196/PUT", "status": SERBEST,
            "court": "Y Mahkemesi", "subject": "Yeni konu", "esas_no": "2026/9",
        })
    assert r.status_code == 400, r.text
    assert SERBEST in r.json()["detail"]
    assert _pg_satir(pg, "G196/PUT") == once
    assert _pg_yan_kayitlar(pg, cid) == yan_once
    assert pg.hatalar == []
    assert _errorlar(caplog) == []

    # Eski değer: mevcut davranış (DERDEST + boş aşamaya taşınır)
    r = pg.client.put(f"/api/cases/{cid}", json={
        "tracking_no": "G196/PUT", "status": "TEMYIZ",
        "court": "X Mahkemesi", "subject": "Eski konu", "esas_no": "2026/1",
    })
    assert r.status_code == 200, r.text
    satir = _pg_satir(pg, "G196/PUT")
    assert (satir["status"], satir["case_stage"]) == ("DERDEST", "TEMYIZ")
    assert pg.hatalar == []


@pytest.mark.dbtest
def test_pg_takip_yolu_uclu_disi_kapida_durur_check_yok_error_yok(pg, caplog):
    """`update_case_tracking` gerçek Postgres'te: kapı yazımdan ÖNCE yükselir.

    Yönetici düzeyinde sınanır, HTTP düzeyinde DEĞİL: `schemas.CaseTrackingUpdate`
    `status` alanı taşımaz → `PATCH /api/cases/{id}/tracking` gövdedeki `status`'u
    pydantic'te sessizce düşürür ve yöneticiye hiç ulaştırmaz (G196 raporu). Kapı,
    fonksiyonun `TRACKING_FIELDS` sözleşmesindeki `status` yolunu korur; route'a 400
    olarak çıkışı `api.py` handler'ı + aşağıdaki PUT/POST HTTP testleriyle aynıdır.
    """
    from constants import InvalidCaseStatusError

    cid = _pg_dava_ac(pg, "G196/TAKIP")
    once = _pg_satir(pg, "G196/TAKIP")
    yan_once = _pg_yan_kayitlar(pg, cid)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(InvalidCaseStatusError):
            case_manager.update_case_tracking(
                cid, {"case_stage": "KARAR", "karar_no": "2026/7", "status": SERBEST}, changed_by="avukat",
            )
    assert _pg_satir(pg, "G196/TAKIP") == once
    assert _pg_yan_kayitlar(pg, cid) == yan_once
    assert pg.hatalar == []
    assert _errorlar(caplog) == []

    # Eski değer: mevcut davranış (üçlü + boş aşamaya taşınır), tarihçe satırı düşer
    assert case_manager.update_case_tracking(cid, {"status": "KAPALI"}, changed_by="avukat") is True
    satir = _pg_satir(pg, "G196/TAKIP")
    assert (satir["status"], satir["case_stage"]) == ("MAHZEN", "KAPALI")
    assert pg.hatalar == []
