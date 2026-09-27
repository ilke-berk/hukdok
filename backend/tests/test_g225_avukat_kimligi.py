"""G225 — kurumsal avukat kimliği `AVK-00001` + avukat silinmez (yalnız pasif) + FK RESTRICT.

Kullanıcı kararı 27.09: avukat kimliği KURUMSAL — sistem üretir, bir kez verilir, değişmez,
yeniden kullanılmaz. Avukat kaydı ASLA silinmez: bugüne dek `delete_item` kaydı `db.delete`
ile siliyor, "clear" modu kartlardaki avukat alanını boşaltıyor, `case_lawyers.lawyer_id`
ON DELETE SET NULL bağı koparıyordu — üçü de dava kaybı yolu.

Katmanlar:
1. DB'siz — biçim, model, migrasyon op'ları (koşullu op tuzağı: kısıtlar KOŞULSUZ op'ta).
2. SQLite (StaticPool, `PRAGMA foreign_keys=ON`) — üretim, yeniden deneme, değişmezlik,
   pasife alma / reddedilen modlar / taşıma, route kodları, pasif avukatın filtre davranışı,
   betik yolu. Diğer listelerin silme davranışı DEĞİŞMEDİ.
3. `dbtest` — scratch Postgres (`test_migration_path` altyapısı; gerçek DB'ye yazılmaz, DB
   yoksa SKIP): NOT NULL + UNIQUE + CHECK + RESTRICT gerçek kısıt olarak; eski kurulum
   taklidinde deterministik doldurma, FK SET NULL → RESTRICT dönüşümü ve idempotentlik.
"""
import pytest
from fastapi import FastAPI
from psycopg2 import errors as pg_errors
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import database
import models
import test_migration_path as mig
from managers import reference_lists
from managers.config_manager import DynamicConfig

admin_engine = mig.admin_engine


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz
# ═══════════════════════════════════════════════════════════════════════════

def test_kimlik_bicimi_ve_numarasi():
    assert models.avukat_kimligi(1) == "AVK-00001"
    assert models.avukat_kimligi(99999) == "AVK-99999"
    for gecersiz in (0, -1, 100000):
        with pytest.raises(ValueError):
            models.avukat_kimligi(gecersiz)
    assert models.avukat_kimlik_numarasi("AVK-00012") == 12
    for bicim_disi in (None, "", "AVK-12", "AVK-000012", "XYZ-00001", "avk-00001"):
        assert models.avukat_kimlik_numarasi(bicim_disi) == 0
    assert models.AVUKAT_KIMLIK_REGEX == "^AVK-[0-9]{5}$"


def test_model_kimlik_kolonu_unique_index_ve_fk_restrict():
    kolon = models.Lawyer.__table__.c.kimlik
    assert kolon.type.length == 9
    index = {ix.name: ix for ix in models.Lawyer.__table__.indexes}["ix_lawyers_kimlik"]
    assert index.unique and [c.name for c in index.columns] == ["kimlik"]

    fk = list(models.CaseLawyer.__table__.c.lawyer_id.foreign_keys)[0]
    assert fk.column.table.name == "lawyers"
    assert fk.ondelete == "RESTRICT"


def _op_sirasi(kosul):
    return [i for i, op in enumerate(database._MIGRATIONS) if kosul(op)]


def test_migrasyon_kolon_kosullu_kisitlar_kosulsuz_opta():
    kolon_op = _op_sirasi(lambda op: op[0] == "columns" and op[1] == "lawyers" and "kimlik" in op[2])
    assert len(kolon_op) == 1
    assert database._MIGRATIONS[kolon_op[0]][2]["kimlik"] == "VARCHAR(9)"

    kisit_op = _op_sirasi(lambda op: op[0] == "index" and op[1] == "lawyers"
                          and any("ix_lawyers_kimlik" in sql for sql in op[2]))
    assert len(kisit_op) == 1 and kolon_op[0] < kisit_op[0]
    sqls = database._MIGRATIONS[kisit_op[0]][2]
    doldurma, unique, not_null, check = sqls
    # doldurma: yalnız boşlar, deterministik sıra, mevcut en büyüğün üstünden
    assert doldurma.startswith("UPDATE lawyers")
    assert "WHERE kimlik IS NULL" in doldurma
    assert "ORDER BY sequence, id" in doldurma
    assert "max(substring(kimlik from 5)::int)" in doldurma
    # UNIQUE ayrı, koşulsuz, modeldeki index ile AYNI ad
    assert unique == "CREATE UNIQUE INDEX IF NOT EXISTS ix_lawyers_kimlik ON lawyers (kimlik)"
    assert not_null == "ALTER TABLE lawyers ALTER COLUMN kimlik SET NOT NULL"
    assert "ck_lawyers_kimlik_bicim" in check and "pg_constraint" in check
    assert f"CHECK (kimlik ~ '{models.AVUKAT_KIMLIK_REGEX}')" in check

    fk_op = _op_sirasi(lambda op: op[0] == "index" and op[1] == "case_lawyers"
                       and any("ON DELETE RESTRICT" in sql for sql in op[2]))
    assert len(fk_op) == 1
    fk_sql = database._MIGRATIONS[fk_op[0]][2][0]
    assert "confdeltype <> 'r'" in fk_sql and "DROP CONSTRAINT" in fk_sql
    assert "REFERENCES lawyers (id) ON DELETE RESTRICT" in fk_sql


def test_avukat_silme_modlari_sabiti():
    assert reference_lists.AVUKAT_SILME_MODLARI == ("block", "reassign")


# ═══════════════════════════════════════════════════════════════════════════
# 2. SQLite
# ═══════════════════════════════════════════════════════════════════════════

def _translate(deger, kaynak, hedef):
    if deger is None:
        return None
    return deger.translate(str.maketrans(kaynak, hedef))


@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.create_function("translate", 3, _translate)
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    config = DynamicConfig.get_instance()
    onceki = config.get_lawyers()
    yield Fabrika
    config.set_lawyers(onceki)
    engine.dispose()


@pytest.fixture()
def veri(fabrika):
    """Serap (AVK-00001, iki kartta: biri sorumlu + bağlı case_lawyers) · Tuğçe (AVK-00002)."""
    db = fabrika()
    serap = models.Lawyer(kimlik="AVK-00001", code="SERAPTUR", name="Serap Turgal", active=True, sequence=1)
    tugce = models.Lawyer(kimlik="AVK-00002", code="TUGCEUNG", name="Tuğçe Ungör Yanık", active=True, sequence=2)
    db.add_all([serap, tugce])
    db.flush()
    k1 = models.Case(tracking_no="G225.1", status="DERDEST", responsible_lawyer_name="Serap Turgal")
    k2 = models.Case(tracking_no="G225.2", status="DERDEST", responsible_lawyer_name="SERAP TURGAL")
    db.add_all([k1, k2])
    db.flush()
    db.add_all([
        models.CaseLawyer(case_id=k1.id, name="Serap Turgal", lawyer_id=serap.id),
        models.CaseLawyer(case_id=k2.id, name="Tuğçe Ungör Yanık", lawyer_id=tugce.id),
    ])
    db.commit()
    kimlikler = {"k1": k1.id, "k2": k2.id, "serap": serap.id, "tugce": tugce.id}
    db.close()
    return kimlikler


def _avukat(fabrika, code):
    db = fabrika()
    try:
        av = db.query(models.Lawyer).filter_by(code=code).one_or_none()
        return None if av is None else {"kimlik": av.kimlik, "active": av.active, "name": av.name, "id": av.id}
    finally:
        db.close()


def _kart_ozeti(fabrika):
    db = fabrika()
    try:
        kartlar = {c.tracking_no: c.responsible_lawyer_name for c in db.query(models.Case)}
        baglar = sorted((cl.case_id, cl.name, cl.lawyer_id) for cl in db.query(models.CaseLawyer))
        return kartlar, baglar
    finally:
        db.close()


# ── üretim ───────────────────────────────────────────────────────────────────

def test_yeni_avukat_sunucudan_sirali_kimlik_alir(fabrika):
    assert reference_lists.add_lawyer("AAA", "Ali Veli") is True
    assert reference_lists.add_lawyer("BBB", "Ayşe Fatma") is True
    assert _avukat(fabrika, "AAA")["kimlik"] == "AVK-00001"
    assert _avukat(fabrika, "BBB")["kimlik"] == "AVK-00002"


def test_numara_en_buyuk_ustunden_verilir_bosluk_ve_pasif_tekrar_kullanilmaz(fabrika):
    db = fabrika()
    db.add_all([
        models.Lawyer(kimlik="AVK-00002", code="IKI", name="İki Avukat", active=True),
        models.Lawyer(kimlik="AVK-00007", code="YEDI", name="Yedi Avukat", active=False),  # pasif, en büyük
    ])
    db.commit()
    db.close()
    assert reference_lists.add_lawyer("YENI", "Yeni Avukat") is True
    assert _avukat(fabrika, "YENI")["kimlik"] == "AVK-00008"      # 1/3-6 boşlukları doldurulmaz


def test_istemciden_gelen_kimlik_yok_sayilir(fabrika):
    assert reference_lists.add_item("lawyers", code="AAA", name="Ali Veli", kimlik="AVK-99999") is True
    assert _avukat(fabrika, "AAA")["kimlik"] == "AVK-00001"


def test_kimlik_cakismasinda_yeniden_dener(fabrika, monkeypatch):
    """İki süreç aynı "en büyük + 1"i hesapladı: unique index ikinciyi reddeder, yeniden okunur."""
    db = fabrika()
    db.add(models.Lawyer(kimlik="AVK-00001", code="ILK", name="İlk Avukat", active=True))
    db.commit()
    db.close()

    gercek = models.sonraki_avukat_kimligi
    cagrilar = []

    def yarisan(oturum):
        cagrilar.append(1)
        return "AVK-00001" if len(cagrilar) == 1 else gercek(oturum)   # ilk hesap bayat

    monkeypatch.setattr(models, "sonraki_avukat_kimligi", yarisan)
    assert reference_lists.add_lawyer("IKINCI", "İkinci Avukat") is True
    assert len(cagrilar) == 2
    assert _avukat(fabrika, "IKINCI")["kimlik"] == "AVK-00002"


def test_kod_cakismasi_yeniden_denenmez():
    """Yalnız KİMLİK çakışması yeniden denenir; başka unique ihlali çağırana gider."""
    ie = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: lawyers.code"))
    assert reference_lists._kimlik_cakismasi(ie) is False
    ie_kimlik = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: lawyers.kimlik"))
    assert reference_lists._kimlik_cakismasi(ie_kimlik) is True

    class _PgHata(Exception):
        pgcode = "23505"

        def __init__(self, kisit):
            super().__init__("duplicate key value violates unique constraint")
            self.diag = type("Diag", (), {"constraint_name": kisit})()

    assert reference_lists._kimlik_cakismasi(IntegrityError("INSERT", {}, _PgHata("ix_lawyers_kimlik"))) is True
    assert reference_lists._kimlik_cakismasi(IntegrityError("INSERT", {}, _PgHata("ix_lawyers_code"))) is False


# ── değişmezlik ──────────────────────────────────────────────────────────────

def test_guncelleme_yollari_kimligi_degistirmez(fabrika, veri):
    sonuc = reference_lists.update_item("lawyers", "SERAPTUR", {"kimlik": "AVK-00099", "email": "s@x.tr"})
    assert sonuc == {"updated": 0}
    assert _avukat(fabrika, "SERAPTUR")["kimlik"] == "AVK-00001"
    assert "kimlik" not in reference_lists.LIST_REGISTRY["lawyers"].editable

    # ORM/betik yolu da kapalı: verilmiş kimlik değiştirilemez, boşaltılamaz
    for yeni in ("AVK-00099", None):
        db = fabrika()
        try:
            db.query(models.Lawyer).filter_by(code="SERAPTUR").one().kimlik = yeni
            with pytest.raises(ValueError, match="kimliği değiştirilemez"):
                db.flush()
        finally:
            db.rollback()
            db.close()
    assert _avukat(fabrika, "SERAPTUR")["kimlik"] == "AVK-00001"


# ── silme = pasif ────────────────────────────────────────────────────────────

def test_block_kullanimdaki_avukati_silmez_pasife_alir(fabrika, veri):
    once = _kart_ozeti(fabrika)
    assert reference_lists.delete_item("lawyers", "SERAPTUR") == {"affected": 0}
    serap = _avukat(fabrika, "SERAPTUR")
    assert serap is not None and serap["active"] is False and serap["kimlik"] == "AVK-00001"
    assert _kart_ozeti(fabrika) == once                       # kart adı + bağ aynen
    assert [lw["code"] for lw in reference_lists.get_lawyers()] == ["TUGCEUNG"]
    assert [lw["code"] for lw in DynamicConfig.get_instance().get_lawyers()] == ["TUGCEUNG"]

    # tekrar "silmek" idempotent
    assert reference_lists.delete_item("lawyers", "SERAPTUR") == {"affected": 0}
    assert _avukat(fabrika, "SERAPTUR")["active"] is False


@pytest.mark.parametrize("mod", ["clear", "keep"])
def test_clear_ve_keep_avukat_icin_reddedilir(fabrika, veri, mod):
    once = _kart_ozeti(fabrika)
    with pytest.raises(reference_lists.LawyerDeleteRejected, match="silinmez"):
        reference_lists.delete_item("lawyers", "SERAPTUR", mode=mod)
    assert _avukat(fabrika, "SERAPTUR")["active"] is True
    assert _kart_ozeti(fabrika) == once


def test_reassign_kartlari_tasir_kaynak_pasif_kalir(fabrika, veri):
    sonuc = reference_lists.delete_item("lawyers", "SERAPTUR", mode="reassign", target="TUGCEUNG")
    assert sonuc and sonuc["affected"] >= 2
    serap = _avukat(fabrika, "SERAPTUR")
    assert serap is not None and serap["active"] is False and serap["kimlik"] == "AVK-00001"
    kartlar, baglar = _kart_ozeti(fabrika)
    assert kartlar == {"G225.1": "Tuğçe Ungör Yanık", "G225.2": "Tuğçe Ungör Yanık"}
    assert baglar == sorted([(veri["k1"], "Tuğçe Ungör Yanık", veri["tugce"]),
                             (veri["k2"], "Tuğçe Ungör Yanık", veri["tugce"])])


def test_reassign_pasif_ya_da_ayni_hedefe_reddedilir(fabrika, veri):
    reference_lists.delete_item("lawyers", "TUGCEUNG")               # Tuğçe pasif
    with pytest.raises(reference_lists.LawyerDeleteRejected, match="pasif"):
        reference_lists.delete_item("lawyers", "SERAPTUR", mode="reassign", target="TUGCEUNG")
    with pytest.raises(reference_lists.LawyerDeleteRejected):
        reference_lists.delete_item("lawyers", "SERAPTUR", mode="reassign", target="SERAPTUR")
    assert _avukat(fabrika, "SERAPTUR")["active"] is True


def test_pasif_avukat_yeniden_eklenince_ayni_kimlikle_acilir(fabrika, veri):
    reference_lists.delete_item("lawyers", "SERAPTUR")
    assert reference_lists.add_lawyer("SERAP2", "SERAP TURGAL") is True
    db = fabrika()
    try:
        assert db.query(models.Lawyer).count() == 2                   # ikinci kayıt doğmadı
    finally:
        db.close()
    serap = _avukat(fabrika, "SERAPTUR")
    assert serap["active"] is True and serap["kimlik"] == "AVK-00001"
    assert _avukat(fabrika, "SERAP2") is None
    # etkin kişi için mükerrer koruması aynen
    with pytest.raises(reference_lists.DuplicateItemError):
        reference_lists.add_lawyer("SERAP3", "Serap Turgal")


def test_bagli_avukat_ham_sqlle_silinemez_restrict(fabrika, veri):
    db = fabrika()
    try:
        with pytest.raises(IntegrityError):
            db.execute(text("DELETE FROM lawyers WHERE code = 'SERAPTUR'"))
            db.commit()
        db.rollback()
        assert db.query(models.CaseLawyer).filter_by(lawyer_id=veri["serap"]).count() == 1
    finally:
        db.close()


def test_diger_listelerin_silme_davranisi_degismedi(fabrika):
    assert reference_lists.add_status("GELEN", "Gelen Belge") is True
    assert reference_lists.delete_item("statuses", "GELEN") == {"affected": 0}
    db = fabrika()
    try:
        assert db.query(models.Status).filter_by(code="GELEN").count() == 0   # gerçekten silindi
    finally:
        db.close()

    # "clear" diğer listelerde çalışmaya devam eder
    assert reference_lists.add_case_subject("TAZ", "Tazminat") is True
    db = fabrika()
    db.add(models.Case(tracking_no="G225.X", status="DERDEST", subject="Tazminat"))
    db.commit()
    db.close()
    assert reference_lists.delete_item("case_subjects", "TAZ", mode="clear") == {"affected": 1}
    db = fabrika()
    try:
        assert db.query(models.Case).filter_by(tracking_no="G225.X").one().subject is None
        assert db.query(models.CaseSubject).count() == 0
    finally:
        db.close()


# ── pasif avukat ve dava listesi filtresi ─────────────────────────────────────

def test_pasif_avukat_menude_yok_ama_kartlari_filtrede_bulunur(fabrika, veri):
    """Mevcut davranış korunur: menü (`get_lawyers`) yalnız aktifleri verir → pasif avukat
    listeden SEÇİLEMEZ; adıyla gelen filtre (eski yer imi / URL) toleranslı ad eşlemesine
    düşer ve kartları yine bulur."""
    from managers import case_manager

    reference_lists.refresh_cache("lawyers")
    db = fabrika()
    try:
        once = case_manager._lawyer_filter_case_ids(db, "Serap Turgal", None)
    finally:
        db.close()
    assert once == {veri["k1"], veri["k2"]}

    reference_lists.delete_item("lawyers", "SERAPTUR")
    assert "Serap Turgal" not in [lw["name"] for lw in reference_lists.get_lawyers()]
    db = fabrika()
    try:
        assert case_manager._lawyer_filter_case_ids(db, "Serap Turgal", None) == once
    finally:
        db.close()


# ── route katmanı ────────────────────────────────────────────────────────────

@pytest.fixture()
def istemci(fabrika):
    from dependencies import get_current_user
    from routes import config as config_routes

    app = FastAPI()
    app.include_router(config_routes.router)
    kullanici = {"preferred_username": "admin@example.com"}
    app.dependency_overrides[get_current_user] = lambda: kullanici
    app.dependency_overrides[config_routes.require_admin] = lambda: kullanici
    return TestClient(app)


def test_route_ozel_delete_ucu_pasife_alir(istemci, fabrika, veri):
    yanit = istemci.delete("/api/config/lawyers/SERAPTUR")
    assert yanit.status_code == 200
    assert _avukat(fabrika, "SERAPTUR")["active"] is False
    assert istemci.delete("/api/config/lawyers/YOKKOD").status_code == 404


@pytest.mark.parametrize("mod", ["clear", "keep"])
def test_route_genel_delete_clear_keep_422(istemci, fabrika, veri, mod):
    yanit = istemci.post("/api/config/delete", json={"type": "lawyers", "code": "SERAPTUR", "mode": mod})
    assert yanit.status_code == 422
    assert "silinmez" in yanit.json()["detail"]
    assert _avukat(fabrika, "SERAPTUR")["active"] is True


def test_route_genel_delete_block_ve_reassign(istemci, fabrika, veri):
    yanit = istemci.post("/api/config/delete", json={"type": "lawyers", "code": "TUGCEUNG", "mode": "block"})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "TUGCEUNG")["active"] is False
    yanit = istemci.post("/api/config/delete", json={"type": "lawyers", "code": "SERAPTUR",
                                                    "mode": "reassign", "target_code": "TUGCEUNG"})
    assert yanit.status_code == 422                                  # pasif hedef


def test_route_put_ve_update_kimligi_yok_sayar(istemci, fabrika, veri):
    yanit = istemci.put("/api/config/lawyers/SERAPTUR", json={"email": "s@x.tr", "kimlik": "AVK-00099"})
    assert yanit.status_code == 200
    yanit = istemci.post("/api/config/update", json={"type": "lawyers", "code": "SERAPTUR",
                                                    "fields": {"kimlik": "AVK-00099", "phone": "1"}})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "SERAPTUR")["kimlik"] == "AVK-00001"


def test_route_post_yeni_avukata_kimlik_verir(istemci, fabrika, veri):
    yanit = istemci.post("/api/config/lawyers", json={"code": "YENI", "name": "Yeni Avukat"})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "YENI")["kimlik"] == "AVK-00003"


# ── betik yolu ───────────────────────────────────────────────────────────────

def test_avukat_yazim_yeni_dis_avukatlara_sirali_kimlik_verir(fabrika, veri):
    """Aynı flush'ta üç yeni kayıt: oturumdaki yeni kayıtlar sayıldığı için numara ikilenmez."""
    from scripts import avukat_yazim
    from scripts.ekip_cevabi_1209 import Sonuc

    db = fabrika()
    try:
        avukat_yazim.dis_avukatlari_ekle(db, sonuc=Sonuc())
        db.commit()
        kimlikler = {av.code: av.kimlik for av in db.query(models.Lawyer)}
    finally:
        db.close()
    assert kimlikler == {
        "SERAPTUR": "AVK-00001", "TUGCEUNG": "AVK-00002",
        "SELDASEN": "AVK-00003", "REYHANDU": "AVK-00004", "ASUBARIS": "AVK-00005",
    }


def test_sonraki_kimlik_oturumdaki_yeni_kayitlari_sayar(fabrika):
    db = fabrika()
    try:
        db.add(models.Lawyer(kimlik=models.sonraki_avukat_kimligi(db), code="A", name="A"))
        db.add(models.Lawyer(kimlik=models.sonraki_avukat_kimligi(db), code="B", name="B"))
        db.commit()
        assert sorted(av.kimlik for av in db.query(models.Lawyer)) == ["AVK-00001", "AVK-00002"]
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. dbtest — scratch Postgres
# ═══════════════════════════════════════════════════════════════════════════

def _pg_hata(exc_info, tip):
    assert isinstance(exc_info.value.orig, tip), type(exc_info.value.orig)


def _fk_eylemi(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT c.conname, c.confdeltype FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
            "WHERE c.conrelid = to_regclass('case_lawyers') AND c.contype = 'f' AND a.attname = 'lawyer_id'"
        )).all()


@pytest.mark.dbtest
def test_sifirdan_kurulumda_kisitlar_gercek(admin_engine):
    with mig._scratch_database(admin_engine, "g225yeni") as engine:
        mig._run_init_db(engine)
        with engine.connect() as conn:
            nullable = conn.execute(text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'lawyers' AND column_name = 'kimlik'")).scalar()
            index_tanimi = conn.execute(text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_lawyers_kimlik'")).scalar()
            check = conn.execute(text(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_lawyers_kimlik_bicim'")).scalar()
        assert nullable == "NO"
        assert index_tanimi and "UNIQUE" in index_tanimi
        assert check == 1
        assert [eylem for _, eylem in _fk_eylemi(engine)] == ["r"]

        with engine.begin() as conn:
            conn.execute(text("INSERT INTO lawyers (kimlik, code, name, active) VALUES ('AVK-00001', 'A', 'A', true)"))
            av_id = conn.execute(text("SELECT id FROM lawyers WHERE code = 'A'")).scalar()
            conn.execute(text("INSERT INTO cases (tracking_no, status) VALUES ('G225/1', 'DERDEST')"))
            kart = conn.execute(text("SELECT id FROM cases WHERE tracking_no = 'G225/1'")).scalar()
            conn.execute(text("INSERT INTO case_lawyers (case_id, lawyer_id, name) VALUES (:k, :a, 'A')"),
                         {"k": kart, "a": av_id})

        for sql, tip in [
            ("INSERT INTO lawyers (kimlik, code, name) VALUES ('AVK-1', 'B', 'B')", pg_errors.CheckViolation),
            ("INSERT INTO lawyers (kimlik, code, name) VALUES ('AVK-00001', 'C', 'C')", pg_errors.UniqueViolation),
            ("INSERT INTO lawyers (code, name) VALUES ('D', 'D')", pg_errors.NotNullViolation),
            ("DELETE FROM lawyers WHERE code = 'A'", pg_errors.ForeignKeyViolation),
        ]:
            with pytest.raises(IntegrityError) as exc:
                with engine.begin() as conn:
                    conn.execute(text(sql))
            _pg_hata(exc, tip)

        onceki = _fk_eylemi(engine)
        mig._run_init_db(engine)                                    # idempotent
        assert _fk_eylemi(engine) == onceki


@pytest.mark.dbtest
def test_eski_kurulumda_doldurma_deterministik_fk_restricte_doner(admin_engine):
    """Eski kurulum taklidi: kimlik kolonu YOK, FK SET NULL; init_db kolonu ekler, boşları
    `sequence, id` sırasıyla mevcut en büyüğün üstünden doldurur, FK'yı RESTRICT yapar."""
    with mig._scratch_database(admin_engine, "g225eski") as engine:
        mig._run_init_db(engine)
        mevcut_fk = [ad for ad, _ in _fk_eylemi(engine)]
        with engine.begin() as conn:
            for ad in mevcut_fk:
                conn.execute(text(f"ALTER TABLE case_lawyers DROP CONSTRAINT {ad}"))
            conn.execute(text(
                "ALTER TABLE case_lawyers ADD CONSTRAINT case_lawyers_lawyer_id_fkey "
                "FOREIGN KEY (lawyer_id) REFERENCES lawyers (id) ON DELETE SET NULL"))
            conn.execute(text("ALTER TABLE lawyers DROP COLUMN kimlik"))   # index + CHECK de düşer
            conn.execute(text(
                "INSERT INTO lawyers (code, name, sequence) VALUES "
                "('C3', 'C', 3), ('A1', 'A', 1), ('B1', 'B', 1), ('D0', 'D', 0)"))
        assert [e for _, e in _fk_eylemi(engine)] == ["n"]

        mig._run_init_db(engine)
        with engine.connect() as conn:
            kimlikler = dict(conn.execute(text("SELECT code, kimlik FROM lawyers")).all())
        # sequence 0 → D0; sequence 1'de id sırası A1 < B1; sonra C3
        assert kimlikler == {"D0": "AVK-00001", "A1": "AVK-00002", "B1": "AVK-00003", "C3": "AVK-00004"}
        assert [e for _, e in _fk_eylemi(engine)] == ["r"]

        # Koşullu op tuzağı: kolon VAR, unique index YOK (create_all'lı kurulum gibi) →
        # koşulsuz op index'i yine kurar; kimliği olmayan yeni satır en büyüğün üstünden dolar.
        with engine.begin() as conn:
            conn.execute(text("DROP INDEX ix_lawyers_kimlik"))
            conn.execute(text("ALTER TABLE lawyers ALTER COLUMN kimlik DROP NOT NULL"))
            conn.execute(text("INSERT INTO lawyers (code, name, sequence) VALUES ('E0', 'E', 0)"))
        mig._run_init_db(engine)
        with engine.connect() as conn:
            assert conn.execute(text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_lawyers_kimlik'")).scalar()
            kimlikler2 = dict(conn.execute(text("SELECT code, kimlik FROM lawyers")).all())
        assert kimlikler2 == {**kimlikler, "E0": "AVK-00005"}

        mig._run_init_db(engine)                                    # ikinci koşu hiçbir şeyi oynatmaz
        with engine.connect() as conn:
            assert dict(conn.execute(text("SELECT code, kimlik FROM lawyers")).all()) == kimlikler2
        assert [e for _, e in _fk_eylemi(engine)] == ["r"]
