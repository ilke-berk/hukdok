"""`managers/seed_data.py` — açılış tohumlaması ve worker yarışı (G058).

Kaynak: Deploy #10 (2026-08-13) prod açılışında tek ERROR gözlendi —

    Seed AppealingParties Error: (psycopg2.errors.UniqueViolation)
    duplicate key value violates unique constraint "ix_appealing_parties_code"
    DETAIL:  Key (code)=(DAVACI) already exists.

Backend uvicorn'u 2 worker ile kalkar ve HER İKİSİ de `seed_all_lists()` koşar.
Desen "var mı bak → yoksa ekle → commit" ve atomik değil. Veri doğruydu (kısıt
görevini yaptı) ama her açılışta ERROR basılıyordu; log sözleşmesi gereği ERROR
"nihai başarısızlık" demektir, iyi huylu bir yarış onu tüketmemeli.

Bu dosya yarışı GERÇEKTEN kurar (iki ayrı Session, araya girme sırası zorlanır)
ve üç şeyi kilitler: veri doğru, ERROR yok, iki koşuda satır sayısı değişmiyor.
"""
import logging

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import models
from managers import seed_data


@pytest.fixture
def oturum_fabrikasi(monkeypatch):
    """Paylaşımlı in-memory sqlite + `SessionLocal` yönlendirmesi.

    `StaticPool` şart: aynı bellek veritabanını birden çok bağlantı görsün ki
    yarış gerçekten kurulabilsin (her bağlantı ayrı DB açsaydı çakışma olmazdı).
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(seed_data, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _say(Fabrika, model) -> int:
    db = Fabrika()
    try:
        return db.query(func.count(model.id)).scalar()
    finally:
        db.close()


# ── Temel sözleşme ───────────────────────────────────────────────────────────

def test_seed_bos_veritabanini_dolduruyor(oturum_fabrikasi):
    seed_data.seed_all_lists()
    assert _say(oturum_fabrikasi, models.AppealingParty) == len(seed_data.APPEALING_PARTIES)
    assert _say(oturum_fabrikasi, models.FileType) > 0
    assert _say(oturum_fabrikasi, models.City) > 0


def test_ikinci_kosu_satir_sayisini_degistirmiyor(oturum_fabrikasi, caplog):
    """İdempotency: aynı seed iki kez koşunca hiçbir tablo büyümüyor."""
    seed_data.seed_all_lists()
    once = {
        m.__name__: _say(oturum_fabrikasi, m)
        for m in (models.AppealingParty, models.FileType, models.City,
                  models.PartyRole, models.FileStatus, models.Specialty)
    }
    with caplog.at_level(logging.ERROR):
        seed_data.seed_all_lists()
    sonra = {k: _say(oturum_fabrikasi, getattr(models, k)) for k in once}
    assert sonra == once
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_seed_mukerrer_uretmiyor(oturum_fabrikasi):
    seed_data.seed_all_lists()
    seed_data.seed_all_lists()
    db = oturum_fabrikasi()
    try:
        mukerrer = (
            db.query(models.AppealingParty.code)
            .group_by(models.AppealingParty.code)
            .having(func.count(models.AppealingParty.id) > 1)
            .all()
        )
    finally:
        db.close()
    assert mukerrer == []


# ── Yarış: iki worker aynı anda tohumluyor ───────────────────────────────────

def test_iki_worker_ayni_anda_tohumlarsa_ERROR_YOK(oturum_fabrikasi, caplog):
    """PROD'DA GÖZLENEN SENARYO.

    İki oturum da "tablo boş" görür, ikisi de eklemeye çalışır. Biri kazanır,
    diğeri kısıta çarpar. Beklenen: veri doğru, **hiç ERROR yok**.
    """
    A = oturum_fabrikasi()
    B = oturum_fabrikasi()
    try:
        # İkisi de aynı anda "yok" görüyor — araya girme burada zorlanıyor.
        assert A.query(models.AppealingParty).count() == 0
        assert B.query(models.AppealingParty).count() == 0

        for idx, (code, name) in enumerate(seed_data.APPEALING_PARTIES):
            seed_data._ekle_yarissiz(
                A, models.AppealingParty(code=code, name=name, active=True, sequence=idx)
            )
        A.commit()

        with caplog.at_level(logging.ERROR):
            eklenen = 0
            for idx, (code, name) in enumerate(seed_data.APPEALING_PARTIES):
                if seed_data._ekle_yarissiz(
                    B, models.AppealingParty(code=code, name=name, active=True, sequence=idx)
                ):
                    eklenen += 1
            B.commit()
    finally:
        A.close()
        B.close()

    assert eklenen == 0, "kaybeden worker hiçbir satır eklememeliydi"
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == [], \
        "iyi huylu yarış ERROR bastı — log sözleşmesi ihlali"
    assert _say(oturum_fabrikasi, models.AppealingParty) == len(seed_data.APPEALING_PARTIES)


def test_yaristaki_kayip_satir_DIGERLERINI_dusurmuyor(oturum_fabrikasi):
    """SAVEPOINT'in asıl gerekçesi: tek satırlık çakışma, aynı commit'teki
    diğer satırları geri almamalı.

    A yalnız ilk kodu yazar; B üçünü birden dener. B'nin ilki çakışır ama
    kalan ikisi YAZILMALI — toptan `rollback` deseni burada veri kaybederdi.
    """
    ilk_kod, ilk_ad = seed_data.APPEALING_PARTIES[0]
    A = oturum_fabrikasi()
    try:
        A.add(models.AppealingParty(code=ilk_kod, name=ilk_ad, active=True, sequence=0))
        A.commit()
    finally:
        A.close()

    B = oturum_fabrikasi()
    try:
        eklenen = 0
        for idx, (code, name) in enumerate(seed_data.APPEALING_PARTIES):
            if seed_data._ekle_yarissiz(
                B, models.AppealingParty(code=code, name=name, active=True, sequence=idx)
            ):
                eklenen += 1
        B.commit()
    finally:
        B.close()

    assert eklenen == len(seed_data.APPEALING_PARTIES) - 1
    assert _say(oturum_fabrikasi, models.AppealingParty) == len(seed_data.APPEALING_PARTIES)


def test_ekle_yarissiz_cakismada_False_dondurur(oturum_fabrikasi):
    db = oturum_fabrikasi()
    try:
        kod, ad = seed_data.APPEALING_PARTIES[0]
        assert seed_data._ekle_yarissiz(
            db, models.AppealingParty(code=kod, name=ad, active=True, sequence=0)
        ) is True
        db.commit()
        assert seed_data._ekle_yarissiz(
            db, models.AppealingParty(code=kod, name=ad, active=True, sequence=0)
        ) is False
        db.commit()
    finally:
        db.close()
    assert _say(oturum_fabrikasi, models.AppealingParty) == 1


def test_cakismadan_sonra_oturum_hala_kullanilabilir(oturum_fabrikasi):
    """SAVEPOINT geri alındıktan sonra oturum ölü olmamalı — toptan rollback
    deseninde `InFailedSqlTransaction`a düşerdi (CI'da G054 testlerinde
    gördüğümüz domino ile aynı sınıf)."""
    db = oturum_fabrikasi()
    try:
        kod, ad = seed_data.APPEALING_PARTIES[0]
        db.add(models.AppealingParty(code=kod, name=ad, active=True, sequence=0))
        db.commit()

        seed_data._ekle_yarissiz(
            db, models.AppealingParty(code=kod, name=ad, active=True, sequence=0)
        )
        # Aynı oturumda yeni ve ÇAKIŞMAYAN bir satır hâlâ yazılabilmeli
        baska_kod, baska_ad = seed_data.APPEALING_PARTIES[1]
        assert seed_data._ekle_yarissiz(
            db, models.AppealingParty(code=baska_kod, name=baska_ad, active=True, sequence=1)
        ) is True
        db.commit()
    finally:
        db.close()
    assert _say(oturum_fabrikasi, models.AppealingParty) == 2


# ── Yarış YALNIZ appealing_parties'te değil ──────────────────────────────────

@pytest.mark.parametrize("model", [
    models.FileType, models.City, models.FileStatus,
    models.Specialty, models.BureauType, models.ClientCategory,
])
def test_yaris_korumasi_tum_seedlerde_gecerli(oturum_fabrikasi, caplog, model):
    """Yarış dokuz seed fonksiyonunun HEPSİNDE vardı; yalnız `appealing_parties`
    görünür oldu çünkü Deploy #10'un getirdiği tek YENİ tablo oydu. Bu test
    "gözlenen tek satırı yamalamadık"ın kanıtı."""
    seed_data.seed_all_lists()
    beklenen = _say(oturum_fabrikasi, model)
    assert beklenen > 0, "seed hiç satır yazmadıysa test bir şey kanıtlamaz"

    with caplog.at_level(logging.ERROR):
        seed_data.seed_all_lists()

    assert _say(oturum_fabrikasi, model) == beklenen
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
