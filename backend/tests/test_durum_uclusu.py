"""Dava durumu üçlüsü (kullanıcı kararı 12.09.2026): `cases.status` yalnız
DERDEST | DANIŞ | MAHZEN. Temyizdeki dava da derdesttir — yargı aşaması
`cases.case_stage`'in işidir.

Katmanlar:
1. `constants.normalize_case_status` — üçlü olduğu gibi, eski değer üçlü +
   aşama, tanınmayan metin dokunulmadan döner.
2. Belge işleme "auto-status" artık AŞAMA yazar (`case_stage`, source
   `auto-stage`); status'a dokunmaz. Eski kod status'a TEMYIZ/KARAR yazıyordu.
3. Panel yolları (`update_case`, `update_case_tracking`) eski değeri üçlüye
   çevirir, boş aşamaya taşır; tarihçeye üçlü değer düşer.
4. `get_case_stats.appeal` aşamadan sayılır; kapalı = MAHZEN (+ eski KAPALI).
5. Rapor kataloğu `DAVA_DURUMLARI` üçlü; migrasyon 50 üç SQL ile veriyi çeker.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from constants import CASE_STATUSES, LEGACY_CASE_STATUS, normalize_case_status
from managers import case_manager


@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _dava(Fabrika, **alanlar) -> int:
    db = Fabrika()
    try:
        alanlar.setdefault("status", "DERDEST")
        case = models.Case(tracking_no=alanlar.pop("tracking_no", "HA.DURUM.1"),
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _kart(Fabrika, cid):
    db = Fabrika()
    try:
        return db.get(models.Case, cid)
    finally:
        db.close()


def _tarihce(Fabrika, cid):
    db = Fabrika()
    try:
        return [(h.field_name, h.old_value, h.new_value, h.source)
                for h in db.query(models.CaseHistory).filter(models.CaseHistory.case_id == cid)
                .order_by(models.CaseHistory.id).all()]
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. normalize_case_status
# ═══════════════════════════════════════════════════════════════════════════

def test_ucLu_sabit_ve_eski_harita_tutarli():
    assert CASE_STATUSES == ("DERDEST", "DANIŞ", "MAHZEN")
    for eski, (yeni, asama) in LEGACY_CASE_STATUS.items():
        assert yeni in CASE_STATUSES and asama == eski
    assert LEGACY_CASE_STATUS["KAPALI"] == ("MAHZEN", "KAPALI")
    assert LEGACY_CASE_STATUS["TEMYIZ"] == ("DERDEST", "TEMYIZ")


@pytest.mark.parametrize("ham,beklenen", [
    ("DERDEST", ("DERDEST", None)),
    ("derdest", ("DERDEST", None)),
    ("DANIŞ", ("DANIŞ", None)),
    ("danış", ("DANIŞ", None)),
    ("DANIS", ("DANIŞ", None)),                 # ASCII yazım
    ("Mahzen", ("MAHZEN", None)),
    ("TEMYIZ", ("DERDEST", "TEMYIZ")),          # temyizdeki dava derdesttir
    ("İstinaf", ("DERDEST", "ISTINAF")),
    ("KARAR", ("DERDEST", "KARAR")),
    ("KAPALI", ("MAHZEN", "KAPALI")),           # kapalı = arşiv
    ("Aktif", ("DERDEST", None)),               # teslim yazımı
    ("Arşiv", ("MAHZEN", None)),
    ("", (None, None)),
    (None, (None, None)),
    ("Bilinmeyen Durum", ("Bilinmeyen Durum", None)),   # dokunulmaz — tahmin yok
])
def test_normalize_case_status(ham, beklenen):
    assert normalize_case_status(ham) == beklenen


# ═══════════════════════════════════════════════════════════════════════════
# 2. Belge işleme: durum değil AŞAMA
# ═══════════════════════════════════════════════════════════════════════════

def test_auto_update_asama_yazar_status_a_dokunmaz(fabrika, monkeypatch):
    """Eski kod TEMYIZ belgesinde status'u TEMYIZ yapardı — kırmızı. Şimdi
    case_stage TEMYIZ olur, status DERDEST kalır, tarihçe `case_stage`/`auto-stage`."""
    from routes import processing

    monkeypatch.setattr(processing, "SessionLocal", fabrika)
    cid = _dava(fabrika)
    assert processing._auto_update_case_status(cid, "TEMYIZ_DILEKCESI__", "avukat") is True
    kart = _kart(fabrika, cid)
    assert kart.status == "DERDEST"
    assert kart.case_stage == "TEMYIZ"
    assert _tarihce(fabrika, cid) == [("case_stage", None, "TEMYIZ", "auto-stage")]
    # aynı aşama ikinci kez → değişiklik yok
    assert processing._auto_update_case_status(cid, "TEMYIZ_DILEKCESI__", "avukat") is False
    assert len(_tarihce(fabrika, cid)) == 1


def test_auto_update_feragat_kapali_asamasi_status_derdest_kalir(fabrika, monkeypatch):
    from routes import processing

    monkeypatch.setattr(processing, "SessionLocal", fabrika)
    cid = _dava(fabrika)
    assert processing._auto_update_case_status(cid, "FERAGAT", "avukat") is True
    kart = _kart(fabrika, cid)
    assert (kart.status, kart.case_stage) == ("DERDEST", "KAPALI")
    assert processing.DOCTYPE_TO_STAGE_MAP["ISLAH"] == "DERDEST"
    assert not hasattr(processing, "DOCTYPE_TO_STATUS_MAP")


def test_auto_update_bilinmeyen_tur_dokunmaz(fabrika, monkeypatch):
    from routes import processing

    monkeypatch.setattr(processing, "SessionLocal", fabrika)
    cid = _dava(fabrika)
    assert processing._auto_update_case_status(cid, "DILEKCE_______", "avukat") is False
    assert _tarihce(fabrika, cid) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Panel yolları üçlü dışına yazamaz
# ═══════════════════════════════════════════════════════════════════════════

def test_update_case_eski_degeri_ucluye_cevirir_asamayi_korur(fabrika):
    cid = _dava(fabrika)
    assert case_manager.update_case(cid, {"status": "TEMYIZ"}, changed_by="avukat") is True
    kart = _kart(fabrika, cid)
    assert (kart.status, kart.case_stage) == ("DERDEST", "TEMYIZ")
    assert _tarihce(fabrika, cid) == []            # DERDEST → DERDEST: değişiklik yok
    assert case_manager.update_case(cid, {"status": "KAPALI"}, changed_by="avukat") is True
    kart = _kart(fabrika, cid)
    assert (kart.status, kart.case_stage) == ("MAHZEN", "TEMYIZ")     # dolu aşamaya dokunmaz
    assert _tarihce(fabrika, cid) == [("status", "DERDEST", "MAHZEN", "panel")]


def test_update_case_uclu_degeri_oldugu_gibi_yazar(fabrika):
    cid = _dava(fabrika)
    assert case_manager.update_case(cid, {"status": "danış"}, changed_by="avukat") is True
    assert _kart(fabrika, cid).status == "DANIŞ"
    assert _tarihce(fabrika, cid) == [("status", "DERDEST", "DANIŞ", "panel")]


def test_update_case_tracking_eski_degeri_ucluye_cevirir(fabrika):
    cid = _dava(fabrika)
    assert case_manager.update_case_tracking(cid, {"status": "ISTINAF"}, changed_by="avukat") is True
    kart = _kart(fabrika, cid)
    assert (kart.status, kart.case_stage) == ("DERDEST", "ISTINAF")
    # panel aynı istekte aşamayı da veriyorsa onunki kazanır
    assert case_manager.update_case_tracking(
        cid, {"status": "KAPALI", "case_stage": "KESINLESME"}, changed_by="avukat",
    ) is True
    kart = _kart(fabrika, cid)
    assert (kart.status, kart.case_stage) == ("MAHZEN", "KESINLESME")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sayaçlar ve katalog
# ═══════════════════════════════════════════════════════════════════════════

def test_get_case_stats_appeal_asamadan_kapali_mahzen(fabrika):
    _dava(fabrika, tracking_no="HA.D.1", status="DERDEST", case_stage="TEMYIZ")
    _dava(fabrika, tracking_no="HA.D.2", status="DERDEST", case_stage="ISTINAF")
    _dava(fabrika, tracking_no="HA.D.3", status="DERDEST")
    _dava(fabrika, tracking_no="HA.D.4", status="MAHZEN", case_stage="KAPALI")
    _dava(fabrika, tracking_no="HA.D.5", status="DANIŞ")
    stats = case_manager.get_case_stats()
    assert stats["total"] == 5
    assert (stats["active"], stats["closed"], stats["appeal"], stats["danis_active"]) == (3, 1, 2, 1)
    assert stats["statuses"] == {"DERDEST": 3, "MAHZEN": 1, "DANIŞ": 1}


def test_rapor_katalogu_uclu():
    from services.rapor.registry import DAVA_DURUMLARI

    assert DAVA_DURUMLARI == ("DANIŞ", "DERDEST", "MAHZEN")


def test_migrasyon_50_uc_sql_idempotent_kosulsuz():
    """Veri düzeltmesi koşulsuz ("index") op'unda: tarihçe → aşama → status; her
    biri aynı WHERE listesiyle sınırlı (ikinci koşu 0 satır). KAPALI → MAHZEN."""
    from database import _MIGRATIONS

    op = next(op for op in _MIGRATIONS if op[0] == "index" and op[1] == "cases"
              and any("migrasyon_50_durum_uclusu" in s for s in op[2]))
    sqller = op[2]
    assert len(sqller) == 3
    assert sqller[0].startswith("INSERT INTO case_history")
    assert "UPDATE cases SET case_stage = status" in sqller[1] and "case_stage IS NULL" in sqller[1]
    assert sqller[2].startswith("UPDATE cases SET status")
    for s in sqller:
        assert "WHERE status IN ('KARAR', 'ISTINAF', 'TEMYIZ', 'KARAR_DUZELTME', 'KESINLESME', 'INFAZ', 'KAPALI')" in s
        assert "CASE WHEN status = 'KAPALI' THEN 'MAHZEN' ELSE 'DERDEST' END" in s or "case_stage" in s
    assert all(d in sqller[0] for d in LEGACY_CASE_STATUS)
