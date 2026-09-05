"""G127 — Mükerrer kart birleştirme (05.09.2026 kullanıcı kararı).

Eski aktarımın aynı dava için açtığı ikiz kartlar (aynı esas + mahkeme + müvekkil)
aktarımın "belirsiz eşleşme" kuralına takılıyor, föy hiçbir karta yazılmıyordu.
Script mükerrerin her şeyini kalan karta taşır ve mükerreri SOFT siler; belge
koruma şartı (belge sayısı ve belge-taraf bağı) birebir korunur; mükerrer
olmayan çift REDDEDİLİR.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import case_manager
from scripts import mukerrer_kart_birlestir as mb
from services import belge_envanteri


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table
            for sql in op[2] if not sql.lstrip().upper().startswith(("UPDATE", "ALTER"))]


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
    with engine.begin() as conn:
        for sql in _index_ops("case_foys"):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _kart(db, tno, klasor, *, esas="2019/82", court="Yalova 2. Asliye Hukuk Mahkemesi",
          muvekkil=("Ak Sigorta A.Ş.",), karsi=("Gökhan Gedik",), status="MAHZEN"):
    c = models.Case(tracking_no=tno, status=status, klasor_no_2=klasor, court=court, file_type="Hukuk")
    db.add(c)
    db.flush()
    case_manager.sync_current_esas(db, c, esas, court=court, source="test")
    for m in muvekkil:
        c.parties.append(models.CaseParty(name=m, role="Müvekkil", party_type="CLIENT"))
    for k in karsi:
        c.parties.append(models.CaseParty(name=k, role="Davalı", party_type="COUNTER"))
    db.flush()
    return c


@pytest.fixture()
def cift(db_env):
    """kalan #1 (föylü, avukatlı), mükerrer #2 (belgeli — belge müvekkil tarafına bağlı)."""
    db = db_env()
    try:
        kalan = _kart(db, "S1.AK.........0377.HUKUK.00000", "3.655.00;3.658.00")
        kalan.lawyers.append(models.CaseLawyer(name="Serap Turgal"))
        db.add(models.CaseFoy(sistem_no="H-100", case_id=kalan.id, tku_no="TKU-1"))
        mukerrer = _kart(db, "S1.AK.........0376.HUKUK.00000", "3.658.00",
                         muvekkil=("AK SİGORTA A.Ş.",), karsi=("Gökhan Gedik", "Ayşe Gedik"), status="DERDEST")
        mukerrer.lawyers.append(models.CaseLawyer(name="Serap Turgal"))
        mukerrer.lawyers.append(models.CaseLawyer(name="Berna Burcu Basyurt"))
        mukerrer.notes = "eski not"
        db.flush()
        muv_taraf = next(p for p in mukerrer.parties if p.party_type == "CLIENT")
        mukerrer.documents.append(models.CaseDocument(
            original_filename="dilekce.pdf", stored_filename="x.pdf", belge_turu_kodu="DILEKCE_______",
            case_party_id=muv_taraf.id, sharepoint_url="https://sp/x.pdf"))
        db.add(models.CaseStageDecision(case_id=mukerrer.id, stage="YEREL", sira_no=1, karar_no="2020/1",
                                        karar_tarihi=date(2020, 1, 1), dogrulama_durumu="BELIRSIZ"))
        db.commit()
        return db_env, kalan.id, mukerrer.id
    finally:
        db.close()


def test_on_kosul_mukerrer_olmayani_reddeder(db_env):
    db = db_env()
    try:
        a = _kart(db, "A.1", "1")
        b = _kart(db, "B.1", "2", muvekkil=("Ak Sigorta A.Ş.", "Deniz Çakır"))   # müvekkil ayrımı
        c = _kart(db, "C.1", "3", esas="2019/99")
        assert "müvekkil" in mb.on_kosul(a, b)
        assert "esas" in mb.on_kosul(a, c)
        assert mb.on_kosul(a, a) == "aynı kart"
        d = _kart(db, "D.1", "4")
        assert mb.on_kosul(a, d) is None
    finally:
        db.close()


def test_kuru_kosu_hicbir_sey_yazmaz(cift):
    fabrika, kalan_id, mukerrer_id = cift
    sonuc = mb.ciftleri_birlestir(fabrika, [(kalan_id, mukerrer_id)])
    assert sonuc[0].ret is None and sonuc[0].tasinan["belge"] == 1
    db = fabrika()
    try:
        assert db.get(models.Case, mukerrer_id).deleted_at is None
        assert db.query(models.CaseDocument).one().case_id == mukerrer_id
    finally:
        db.close()


def test_birlestirme_belgeyi_tarafiyla_tasir_tekillestirir_soft_siler(cift):
    fabrika, kalan_id, mukerrer_id = cift
    db = fabrika()
    once = belge_envanteri.snapshot(db)
    db.close()

    sonuc = mb.ciftleri_birlestir(fabrika, [(kalan_id, mukerrer_id)], apply=True, kim="test")

    assert sonuc[0].ret is None
    t = sonuc[0].tasinan
    assert t["belge"] == 1 and t["taraf_tasinan"] == 1 and t["taraf_tekil"] == 2   # Ayşe Gedik taşındı; AK + Gökhan tekil
    assert t["avukat"] == 1 and t["asama"] == 1
    db = fabrika()
    try:
        kalan = db.get(models.Case, kalan_id)
        muk = db.get(models.Case, mukerrer_id)
        assert muk.deleted_at is not None and muk.active is False and f"#{kalan_id}" in muk.delete_reason
        assert muk.deleted_by == "test"
        assert muk.tracking_no == "S1.AK.........0376.HUKUK.00000"            # ofis no mükerrerde kalır
        belge = db.query(models.CaseDocument).one()
        assert belge.case_id == kalan_id
        assert belge.case_party_id == next(p.id for p in kalan.parties if p.party_type == "CLIENT")  # SET NULL değil
        assert sorted(p.name for p in kalan.parties) == ["Ak Sigorta A.Ş.", "Ayşe Gedik", "Gökhan Gedik"]
        assert sorted(lw.name for lw in kalan.lawyers) == ["Berna Burcu Basyurt", "Serap Turgal"]
        assert db.query(models.CaseParty).filter_by(case_id=mukerrer_id).count() == 0
        assert kalan.klasor_no_2 == "3.655.00;3.658.00"
        assert kalan.status == "DERDEST"                                        # aktif dava mahzene düşmez
        assert "[Birleştirme" in kalan.notes and "eski not" in kalan.notes
        assert db.query(models.CaseStageDecision).filter_by(case_id=kalan_id, stage="YEREL").count() == 1
        assert db.query(models.CaseFoy).filter_by(case_id=kalan_id).count() == 1
        tarihce = db.query(models.CaseHistory).filter_by(case_id=kalan_id, field_name="mukerrer_birlestirme").one()
        assert tarihce.old_value == "S1.AK.........0376.HUKUK.00000"
    finally:
        db.close()
    # Belge koruma: belge SAYISI ve SharePoint bağı korunur; yalnız kart/taraf bağı
    # bilinçli değişir (birleştirmenin kendisi) — envanter farkı sadece o iki alanda.
    db = fabrika()
    try:
        sonra = belge_envanteri.snapshot(db)
        fark = belge_envanteri.diff(once, sonra)
        assert set(fark) <= {"bag_imzasi"}, fark          # sayımlar aynı; yalnız bağ imzası değişir
    finally:
        db.close()

    # ikinci çağrı: mükerrer zaten silinmiş → RET, hiçbir şey değişmez
    ikinci = mb.ciftleri_birlestir(fabrika, [(kalan_id, mukerrer_id)], apply=True)
    assert "silinmiş" in ikinci[0].ret


def test_birlestirme_sonrasi_dosya_no_koprusu_tek_karta_cozulur(cift):
    """Aktarımın 'belirsiz eşleşme'si biter: _dosya_no_haritasi silineni görmez."""
    from scripts.hukdok_aktarim import _dosya_no_haritasi

    fabrika, kalan_id, mukerrer_id = cift
    db = fabrika()
    try:
        assert len(_dosya_no_haritasi(db)["3.658.00"]) == 2
    finally:
        db.close()
    mb.ciftleri_birlestir(fabrika, [(kalan_id, mukerrer_id)], apply=True)
    db = fabrika()
    try:
        assert _dosya_no_haritasi(db)["3.658.00"] == [kalan_id]
    finally:
        db.close()
