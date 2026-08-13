"""G055 — dava arama UNION + çok terimli INTERSECT-of-UNION (E8).

Eskiden 13-14 kollu tek bir OR/EXISTS ağacı vardı; planlayıcı o ağaçta hiçbir
trigram index seçemiyordu (ADR-018). `case_manager.get_cases` artık her kolonu
AYRI bir SELECT olarak UNION'lıyor (tek terim) ve terimler arası AND semantiğini
UNION'ların INTERSECT'iyle kuruyor (çok terimli). Bu dosya, yeniden yazımın
**riskli** kısımlarını kilitler — id kümesi/sıra eşdeğerliğinin kendisi
`test_g045_esas_tarihcesi.py`/`test_g051_kart_ve_arama_sorgulari.py` gibi
mevcut dosyalarda zaten dolaylı test ediliyordu (hepsi yeşil kaldı); burada
eksik olan **çok terimli AND** ve **UNION dedup** için hiç test yoktu (grep
doğrulandı, G055 raporu).
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base


@pytest.fixture()
def db_env(monkeypatch):
    from managers import case_manager

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    yield SimpleNamespace(sessions=maker, manager=case_manager)
    engine.dispose()


def _dava(db_env, tracking_no, **extra):
    created = db_env.manager.add_case({"tracking_no": tracking_no, **extra})
    assert created and "id" in created, created
    return created["id"]


def _parti_ekle(db_env, case_id, name, role="Davacı", party_type="CLIENT"):
    db = db_env.sessions()
    try:
        db.add(models.CaseParty(case_id=case_id, name=name, role=role, party_type=party_type))
        db.commit()
    finally:
        db.close()


def _tarihce_ekle(db_env, case_id, old_value, field_name="notes"):
    db = db_env.sessions()
    try:
        db.add(models.CaseHistory(case_id=case_id, field_name=field_name, old_value=old_value))
        db.commit()
    finally:
        db.close()


def test_cok_terimli_and_semantigi_yalniz_ikisini_de_karsilayani_buluyor(db_env):
    """"tazminat murat" — yalnız İKİSİNİ DE karşılayan dava dönmeli (INTERSECT).

    Terimler bilinçli ASCII: SQLite'ın yerleşik `lower()`'ı Türkçe diakritikleri
    (ö/ş/ç/ı/İ) büyük/küçük harf eşitlemez (Postgres ILIKE eşitler — G055
    raporundaki 20 canlı sorgu "özen" dahil zaten Postgres'te doğrulandı).
    Burada birim testin harness sınırı, ürün davranışı değil.
    """
    _dava(db_env, "T.0001.2026", subject="Tazminat davasi")  # yalnız tek terimi karşılar
    sadece_murat = _dava(db_env, "T.0002.2026", subject="Diger dava turu")
    _parti_ekle(db_env, sadece_murat, "Ahmet Murat")
    ikisi_de = _dava(db_env, "T.0003.2026", subject="Tazminat davasi")
    _parti_ekle(db_env, ikisi_de, "Mehmet Murat")

    items, total = db_env.manager.get_cases(q="tazminat murat")

    assert total == 1
    assert [i["id"] for i in items] == [ikisi_de]


def test_uc_terimli_intersect_zinciri(db_env):
    """`intersect(*term_id_queries)` iki terimle sınırlı kalmamalı."""
    tam_uyan = _dava(db_env, "T.0010.2026", subject="Tazminat davasi", court="Ankara icra mahkemesi")
    _parti_ekle(db_env, tam_uyan, "Ahmet Murat")
    _dava(db_env, "T.0011.2026", subject="Tazminat davasi", court="Ankara icra mahkemesi")  # yalnız iki terimi karşılar

    items, total = db_env.manager.get_cases(q="tazminat murat icra")

    assert total == 1
    assert [i["id"] for i in items] == [tam_uyan]


def test_ayni_terim_iki_ayri_kolonda_essesse_de_sonuc_tekil(db_env):
    """UNION DISTINCT'tir: bir dava iki koldan eşleşse bile listede BİR KEZ görünür."""
    case_id = _dava(db_env, "T.0020.2026", subject="Tazminat davasi")
    _parti_ekle(db_env, case_id, "Tazminat Sigorta AS")

    items, total = db_env.manager.get_cases(q="tazminat")

    assert total == 1
    assert [i["id"] for i in items] == [case_id]


def test_exact_modda_notes_kolu_aranmiyor(db_env):
    """Eski OR ağacında exact dalında `notes` hiç yoktu — davranış korunmalı."""
    case_id = _dava(db_env, "T.0030.2026", notes="notestoken2026")

    normal_items, normal_total = db_env.manager.get_cases(q="notestoken2026")
    exact_items, exact_total = db_env.manager.get_cases(q="notestoken2026", exact=True)

    assert normal_total == 1 and [i["id"] for i in normal_items] == [case_id]
    assert exact_total == 0 and exact_items == []


def test_exact_modda_history_kolu_aranmiyor(db_env):
    """Eski OR ağacında exact dalında `case_history.old_value` hiç yoktu."""
    case_id = _dava(db_env, "T.0031.2026")
    _tarihce_ekle(db_env, case_id, "eskidegertoken2026")

    normal_items, normal_total = db_env.manager.get_cases(q="eskidegertoken2026")
    exact_items, exact_total = db_env.manager.get_cases(q="eskidegertoken2026", exact=True)

    assert normal_total == 1 and [i["id"] for i in normal_items] == [case_id]
    assert exact_total == 0 and exact_items == []
