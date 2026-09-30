"""Ofis no sırası — sayaç semantiği (Faz 6.3'ün G239 taşıması, karar 023).

Bilinen bug (2026-07-16): COUNT tabanlı öneri, araya silinmiş kayıt girince
dolu numarayı yeniden önerip UniqueViolation/409 üretiyordu. Faz 6.3 bunu
numaraları AYRIŞTIRIP max+1 alan `routes.cases.max_tracking_sequence` ile
kapatmıştı. G239'da o fonksiyon ve onu çağıran `/api/cases/client-sequence` ucu
KALKTI: sıra artık numaradan okunmaz, `ofis_no_sayaclari` sayacından tahsis
edilir (`services/ofis_no.sira_tahsis_et`, müvekkil kodu başına). Aynı altı
senaryo yeni kaynağa karşı kilitlenir — "dolu numara yeniden önerilmez" iddiası
aynı, mekanizma sayaç.

İNSAN ONAYLI TEST TAŞIMA (G239): beklentiler "numara listesinden max" yerine
"sayaçtan sıra"ya çevrildi; test sayısı ve assert sayısı azalmadı.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from routes import cases as cases_route
from services import ofis_no

KOD = "DR.A.YILMAZ"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


def test_gapless_sequence(db):
    # İki tahsis → sıradaki 3 (eski: iki numaralı liste, max+1 == 3).
    assert [ofis_no.sira_tahsis_et(db, KOD), ofis_no.sira_tahsis_et(db, KOD)] == [1, 2]
    assert ofis_no.siradaki(db, KOD) == 3


def test_deleted_record_gap_does_not_collide(db):
    # 3 numaralı dava silinmiş olsa da sayaç GERİ GİTMEZ: dört tahsisten sonra
    # sıradaki 5'tir — silinen kartın numarası yeniden verilmez, dolu 4 önerilmez.
    for _ in range(4):
        sira = ofis_no.sira_tahsis_et(db, KOD)
    db.add(models.Case(tracking_no=f"{KOD}-0003-HUK", ofis_no_kodu=KOD, ofis_no_sira=3,
                       deleted_at=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    db.commit()
    assert sira == 4
    assert ofis_no.siradaki(db, KOD) == 5


def test_empty_list_starts_at_one(db):
    # Hiç tahsis yapılmamış kod 1'den başlar.
    assert ofis_no.siradaki(db, KOD) == 1


def test_malformed_numbers_ignored(db):
    # Sıra numaradan OKUNMAZ: DB'de eski formatlı 0007 numaralı kart dursa da
    # (eski fonksiyon bunu ayrıştırıp 7 derdi) sayaç yalnız kendi tahsislerini sayar.
    for no in ("ESKI-FORMAT-123", "HD.YILMAZAHME.0007.11000"):
        db.add(models.Case(tracking_no=no))
    db.commit()
    assert ofis_no.siradaki(db, KOD) == 1


def test_all_malformed_yields_zero(db):
    # Numara ayrıştıran saf fonksiyon kalktı; desene uymayan numaralar sayaç üretmez.
    for no in ("X", "2024/123"):
        db.add(models.Case(tracking_no=no))
    db.commit()
    assert not hasattr(cases_route, "max_tracking_sequence")
    assert db.query(models.OfisNoSayaci).count() == 0


def test_padding_underscore_name_block_matches_pattern(db):
    # Eski '_' pad'li isim bloğu (`HD.KAYA______.0012.10000`) artık bir sıra
    # kaynağı değil: sayaç müvekkil KODU başınadır, başka kodun sırasını etkilemez.
    db.add(models.Case(tracking_no="HD.KAYA______.0012.10000"))
    for _ in range(12):
        ofis_no.sira_tahsis_et(db, "DR.A.KAYA")
    db.commit()
    assert ofis_no.siradaki(db, "DR.A.KAYA") == 13
    assert ofis_no.siradaki(db, KOD) == 1
