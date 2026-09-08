"""G158 — çoklu avukatlı kart "eksik sorumlu avukat" sayılmaz (M5, plan 08.09 §1.3).

Aktarım çoklu isimli föyde `responsible_lawyer_name` kutusunu BİLEREK boş
bırakır ve isimleri `case_lawyers`a yazar (`hukdok_aktarim.py::_tek_avukat`).
Ekip kararı: bu kartlar 12 avukata "atanmış" değil, sorumlusu ayrıştırılamamış
eski dosyadır — "silmeyin, boşaltmayın, atanmadı saymayın". Kural:

    kutu boş VE case_lawyers satırı >= COKLU_AVUKAT_ESIGI (2)  →  eksik DEĞİL
    kutu boş VE satır 0 ya da 1                                →  eksik (değişmedi)

Dört iddia kilitlenir:

1. Python kuralı 0 / 1 / 2 / 3 satırda doğru söyler; kapı yalnız kendi alanını
   açar; kural VERİ olarak yazılıdır (`skip_when_lawyers_at_least`, JSON'a gider).
2. SQL ikizi aynı kapıyı çevirir (string düzeyi + gerçek Postgres'te aynı sonuç).
3. Yazma yolu bayatlamaz: aktarımın yaptığı gibi `case_lawyers` doğrudan yazılıp
   `refresh_missing_required` çağrılınca bayrak yeni kurala göre hesaplanır;
   `get_case`/`get_cases` canlı listesi de aynı şeyi söyler.
4. Kural değişikliği backfill'i (`backfill_missing_required_flags`) kuru koşuda
   yazmaz, `apply` ile yazar, ikinci koşuda 0 döner (idempotent).

sqlite bölümü G046 desenini (StaticPool + SessionLocal yönlendirmesi) kullanır;
Postgres bölümü `dbtest` işaretlidir ve TEK bir işlem içinde koşup ROLLBACK
eder — gerçek veritabanına kalıcı hiçbir satır yazmaz.
"""
import json
import os
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from required_fields import (
    COKLU_AVUKAT_ESIGI,
    MISSING_BUCKET_AKTARIM,
    MISSING_BUCKET_MANUAL,
    REQUIRED_CASE_FIELDS,
    _sql_lawyer_count,
    _sql_norm,
    compute_missing_bucket,
    compute_missing_fields,
    is_field_required,
    missing_bucket_sql,
    missing_required_sql,
)

KOLON = "missing_required_bucket"
ALAN = "responsible_lawyer_name"


def _tam_kayit(**overrides) -> dict:
    """Hiçbir zorunlu alanı eksik olmayan dava verisi (G046 ile aynı)."""
    data = {
        "esas_no": "2024/145",
        "court": "Ankara 5. Asliye Hukuk Mahkemesi",
        "file_type": "Hukuk",
        "judicial_unit": "Asliye Hukuk",
        "sub_type": "Tıbbi Malpraktis",
        "opening_date": "2024-01-15",
        "subject": "Tazminat",
        "responsible_lawyer_name": "Av. Deneme Kişi",
        "uyap_lawyer_name": "Av. Deneme Kişi",
        "service_type": "DAVA",
        "acceptance_date": "2024-01-10",
        "bureau_type": "LEXİS",
        "atama_tarihi": "2024-01-12",
    }
    data.update(overrides)
    return data


def _avukatlar(n: int) -> list:
    return [{"name": f"Av. Kişi {i}", "lawyer_id": None} for i in range(n)]


def _eksik_alanlar(case_data, lawyers=None) -> list:
    return [e["field"] for e in compute_missing_fields(case_data, [], lawyers)]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Python kuralı
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("n, eksik_mi", [(0, True), (1, True), (2, False), (3, False)])
def test_bos_kutu_avukat_satiri_sayisina_gore(n, eksik_mi):
    """Kabul kriteri: 0/1 satırda eksik, >= 2 satırda değil."""
    eksik = _eksik_alanlar(_tam_kayit(responsible_lawyer_name=None), _avukatlar(n))
    assert (ALAN in eksik) is eksik_mi, f"{n} avukat satırı: {eksik}"


def test_esik_iki_ve_kural_veri_olarak_yazili():
    """Kural KOD değil VERİ: liste JSON olarak frontend'e gider (G046 ilkesi)."""
    assert COKLU_AVUKAT_ESIGI == 2
    tanim = next(f for f in REQUIRED_CASE_FIELDS if f["field"] == ALAN)
    assert tanim["skip_when_lawyers_at_least"] == COKLU_AVUKAT_ESIGI
    assert json.loads(json.dumps(REQUIRED_CASE_FIELDS)) == REQUIRED_CASE_FIELDS
    # Kapı yalnız bu alanda — başka bir alana sızması sessiz olmamalı
    assert [f["field"] for f in REQUIRED_CASE_FIELDS if f.get("skip_when_lawyers_at_least")] == [ALAN]


def test_lawyers_verilmezse_case_data_icinden_okunuyor():
    """get_case/get_cases sözlükleri `lawyers` anahtarını taşır; ikinci parametre şart değil."""
    data = _tam_kayit(responsible_lawyer_name=None, lawyers=_avukatlar(2))
    assert ALAN not in [e["field"] for e in compute_missing_fields(data)]

    data["lawyers"] = _avukatlar(1)
    assert ALAN in [e["field"] for e in compute_missing_fields(data)]


def test_yalnizca_bosluk_kutu_da_bos_sayiliyor():
    eksik = _eksik_alanlar(_tam_kayit(responsible_lawyer_name="   "), _avukatlar(2))
    assert ALAN not in eksik
    assert ALAN in _eksik_alanlar(_tam_kayit(responsible_lawyer_name="   "), _avukatlar(1))


def test_kapi_yalnizca_kendi_alanini_aciyor():
    """İki avukat satırı `court`u zorunlu olmaktan çıkarmaz."""
    eksik = _eksik_alanlar(_tam_kayit(responsible_lawyer_name=None, court=None), _avukatlar(2))
    assert eksik == ["court"]


def test_dolu_kutu_coklu_avukatta_eksik_yok():
    assert _eksik_alanlar(_tam_kayit(), _avukatlar(2)) == []


def test_avukat_satirlari_nesne_de_olabilir():
    """refresh_missing_required Row nesneleri geçirir — yalnız SAYILIR."""
    satirlar = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert ALAN not in _eksik_alanlar(_tam_kayit(responsible_lawyer_name=None), satirlar)


def test_is_field_required_varsayilan_sayim_sifir():
    """`lawyer_count` verilmezse kapı KAPALI kalır — eski çağrılar davranış değiştirmez."""
    tanim = next(f for f in REQUIRED_CASE_FIELDS if f["field"] == ALAN)
    assert is_field_required(tanim, {}) is True
    assert is_field_required(tanim, {}, lawyer_count=1) is True
    assert is_field_required(tanim, {}, lawyer_count=2) is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. SQL ikizi — string düzeyi
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("table", ["cases", "v"])
def test_sql_ikizi_avukat_kapisini_sorumlu_avukat_kosuluna_bagliyor(table):
    sql = missing_required_sql(table)
    beklenen = (
        f"({_sql_lawyer_count(table)} < {COKLU_AVUKAT_ESIGI} AND "
        f"{_sql_norm(table + '.' + ALAN)} = '')"
    )
    assert beklenen in sql
    assert f"l.case_id = {table}.id" in sql


def test_sql_ikizi_avukat_kapisi_tek_alanda():
    """Kapı başka bir alanın koşuluna sızmamalı (Python tarafıyla bire bir)."""
    assert missing_required_sql().count("case_lawyers") == 1
    assert missing_bucket_sql().count("case_lawyers") == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. Yazma yolu — sqlite (aktarımın yaptığı gibi case_lawyers doğrudan yazılır)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env(monkeypatch):
    from database import Base
    from managers import case_manager

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    yield SimpleNamespace(sessions=maker, manager=case_manager, engine=engine)
    engine.dispose()


def _kova(db_env, case_id):
    db = db_env.sessions()
    try:
        return getattr(db.get(models.Case, case_id), KOLON)
    finally:
        db.close()


def _dava(db_env, tracking_no="HA.X.0001.2026", **overrides):
    data = _tam_kayit(**overrides)
    data["tracking_no"] = tracking_no
    data["parties"] = []
    created = db_env.manager.add_case(data)
    assert created and "id" in created, created
    return created["id"]


def _aktarim_gibi_avukat_yaz(db_env, case_id, n, source=None):
    """Aktarımın yolu: `case_lawyers`a doğrudan satır + (varsa) imza + refresh.

    Satırlar commit'ten ÖNCE, aynı oturumda tazeleme çağrılır — `db.flush()`
    iddiası ("bekleyen satırı görür") böyle sınanır.
    """
    db = db_env.sessions()
    try:
        case = db.get(models.Case, case_id)
        for lw in _avukatlar(n):
            db.add(models.CaseLawyer(case_id=case_id, name=lw["name"], lawyer_id=None))
        if source:
            db.add(models.CaseHistory(
                case_id=case_id, field_name="avukat", old_value=None, new_value="x",
                changed_by="aktarim", source=source,
            ))
        kova = db_env.manager.refresh_missing_required(db, case)
        db.commit()
        return kova
    finally:
        db.close()


@pytest.mark.parametrize("n, beklenen", [(0, MISSING_BUCKET_MANUAL), (1, MISSING_BUCKET_MANUAL), (2, None)])
def test_refresh_avukat_satirlarini_sayarak_kovayi_yaziyor(db_env, n, beklenen):
    case_id = _dava(db_env, responsible_lawyer_name=None)
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL

    assert _aktarim_gibi_avukat_yaz(db_env, case_id, n) == beklenen
    assert _kova(db_env, case_id) == beklenen


def test_aktarim_imzali_coklu_avukatli_kart_kovadan_cikiyor(db_env):
    """Hedefin kendisi: AKTARIM kovasındaki çoklu avukatlı kart gürültü olmaktan çıkar."""
    case_id = _dava(db_env, responsible_lawyer_name=None)
    _aktarim_gibi_avukat_yaz(db_env, case_id, 0, source="HUKDOK_TESLIM_2026-09-04")
    assert _kova(db_env, case_id) == MISSING_BUCKET_AKTARIM

    _aktarim_gibi_avukat_yaz(db_env, case_id, 2)

    assert _kova(db_env, case_id) is None


def test_coklu_avukat_baska_eksigi_gizlemiyor(db_env):
    """Kutu boş + 2 avukat AMA uyap boş → kart hâlâ (aktarım) kovasında."""
    case_id = _dava(db_env, responsible_lawyer_name=None, uyap_lawyer_name=None)
    _aktarim_gibi_avukat_yaz(db_env, case_id, 2, source="HUKDOK_TESLIM_2026-09-04")
    assert _kova(db_env, case_id) == MISSING_BUCKET_AKTARIM


def test_canli_liste_get_case_ve_get_cases_ayni_kurali_soyluyor(db_env):
    """Kart ve liste uyarısı (canlı hesap) bayrakla aynı şeyi demeli."""
    iki = _dava(db_env, tracking_no="HA.X.0001.2026", responsible_lawyer_name=None)
    bir = _dava(db_env, tracking_no="HA.X.0002.2026", responsible_lawyer_name=None)
    _aktarim_gibi_avukat_yaz(db_env, iki, 2)
    _aktarim_gibi_avukat_yaz(db_env, bir, 1)

    kart_iki = db_env.manager.get_case(iki)
    kart_bir = db_env.manager.get_case(bir)
    assert [e["field"] for e in kart_iki["missing_required_fields"]] == []
    assert [e["field"] for e in kart_bir["missing_required_fields"]] == [ALAN]

    items, _ = db_env.manager.get_cases()
    liste = {i["id"]: [e["field"] for e in i["missing_required_fields"]] for i in items}
    assert liste == {iki: [], bir: [ALAN]}


# ═══════════════════════════════════════════════════════════════════════════
# 4. Gerçek Postgres — SQL ikizi + backfill (tek işlem, ROLLBACK)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def pg_tx():
    """Gerçek Postgres'te ROLLBACK'lenen tek işlem; ulaşılamıyorsa SKIP.

    Oturum dış bir transaction'a bağlıdır: fonksiyonlar `commit` çağırmaz
    (`db` dışarıdan verilince çağıranın işi), fixture sonunda her şey geri alınır.
    """
    url = os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL postgresql:// değil")

    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    try:
        conn = engine.connect()
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__})")
    # İşlem ÖNCE açılır: ilk execute autobegin yapar, sonradan begin() reddedilir.
    trans = conn.begin()
    var = conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'cases' AND column_name = :k"
    ), {"k": KOLON}).first()
    if not var:
        trans.rollback()
        conn.close()
        engine.dispose()
        pytest.skip(f"cases.{KOLON} kolonu yok — migrasyon henüz koşmamış")

    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
        engine.dispose()


def _pg_kart(session, n_avukat: int, kova_on_deger=MISSING_BUCKET_MANUAL) -> models.Case:
    """Kutusu boş, diğer alanları tam bir kart + n avukat satırı (flush, commit YOK)."""
    data = _tam_kayit(responsible_lawyer_name=None)
    for k in ("opening_date", "acceptance_date", "atama_tarihi"):
        data[k] = date.fromisoformat(data[k])
    case = models.Case(tracking_no=f"G158.{uuid.uuid4().hex[:12]}", **data)
    setattr(case, KOLON, kova_on_deger)
    session.add(case)
    session.flush()
    for lw in _avukatlar(n_avukat):
        session.add(models.CaseLawyer(case_id=case.id, name=lw["name"], lawyer_id=None))
    session.flush()
    return case


def _pg_sql_kova(session, case_id):
    return session.execute(text(
        f"SELECT {missing_bucket_sql('cases')} FROM cases WHERE id = :id"
    ), {"id": case_id}).scalar()


@pytest.mark.parametrize("n, beklenen", [(0, MISSING_BUCKET_MANUAL), (1, MISSING_BUCKET_MANUAL), (2, None)])
@pytest.mark.dbtest
def test_sql_ikizi_postgreste_avukat_satirlarini_sayiyor(pg_tx, n, beklenen):
    """Kabul kriteri: Python + SQL aynı sonucu verir (0 / 1 / 2 satır)."""
    from managers.case_manager import _case_snapshot, refresh_missing_required

    case = _pg_kart(pg_tx, n)

    assert _pg_sql_kova(pg_tx, case.id) == beklenen
    # Python kuralı aynı satırda aynı şeyi söylemeli (ikizlik iddiasının kendisi)
    lawyers = pg_tx.query(models.CaseLawyer.id).filter(models.CaseLawyer.case_id == case.id).all()
    assert compute_missing_bucket(
        compute_missing_fields(_case_snapshot(case), [], lawyers), False
    ) == beklenen
    # ve tek yazma yolu da
    assert refresh_missing_required(pg_tx, case) == beklenen


@pytest.mark.dbtest
def test_backfill_kuru_kosu_yazmiyor_apply_yaziyor_ikinci_kosu_sifir(pg_tx):
    """Kabul kriteri: backfill sayısı raporlanır, ikinci koşu 0 (idempotent)."""
    from managers.case_manager import backfill_missing_required_flags

    bayat = _pg_kart(pg_tx, 2, kova_on_deger=MISSING_BUCKET_MANUAL)   # kural: None olmalı

    kuru = backfill_missing_required_flags(db=pg_tx, apply=False)
    assert kuru["degisecek"] >= 1 and kuru["uygulanan"] == 0
    pg_tx.refresh(bayat)
    assert getattr(bayat, KOLON) == MISSING_BUCKET_MANUAL, "kuru koşu yazdı"

    uygulama = backfill_missing_required_flags(db=pg_tx, apply=True)
    assert uygulama["uygulanan"] == uygulama["degisecek"] >= 1
    pg_tx.refresh(bayat)
    assert getattr(bayat, KOLON) is None

    ikinci = backfill_missing_required_flags(db=pg_tx, apply=True)
    assert ikinci["degisecek"] == 0 and ikinci["uygulanan"] == 0
    assert ikinci["toplam"] == uygulama["toplam"]
