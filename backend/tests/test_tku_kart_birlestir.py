"""TKU kart birleştirmesi (11.09.2026 kullanıcı kararı).

Aynı davanın müvekkil başına açılmış kartları (aynı TKU + aynı esas + aynı
mahkeme) tek karta toplanır: föyler değişmez, kalan kartta bütün müvekkiller,
sönen kartın ofis numarası föyde `onceki_tracking_no` olarak kalır ve aramada
bulunur. Farklı esas/mahkeme/tür = farklı dava → birleştirilmez (ilişki kalır).
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
from scripts import tku_kart_birlestir as tb


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


def _kart(db, tno, *, esas="2014/394", court="Tarsus 3. Asliye Hukuk Mahkemesi", file_type="Hukuk",
          muvekkil=("Axa Sigorta A.Ş.",), karsi=("Sevgi Atilla",), foy=(), belge=0):
    c = models.Case(tracking_no=tno, status="MAHZEN", court=court, file_type=file_type)
    db.add(c)
    db.flush()
    case_manager.sync_current_esas(db, c, esas, court=court, source="test")
    for m in muvekkil:
        c.parties.append(models.CaseParty(name=m, role="Müvekkil", party_type="CLIENT"))
    for k in karsi:
        c.parties.append(models.CaseParty(name=k, role="Karşı Taraf", party_type="COUNTER"))
    db.flush()
    muv = next(p for p in c.parties if p.party_type == "CLIENT")
    for sistem_no, tku in foy:
        db.add(models.CaseFoy(sistem_no=sistem_no, case_id=c.id, tku_no=tku, case_party_id=muv.id))
    for i in range(belge):
        c.documents.append(models.CaseDocument(
            original_filename=f"b{i}.pdf", stored_filename=f"{tno}-{i}.pdf", belge_turu_kodu="DILEKCE_______",
            case_party_id=muv.id, sharepoint_url=f"https://sp/{tno}/{i}.pdf"))
    db.flush()
    return c


@pytest.fixture()
def tarsus(db_env):
    """TKU-1014: Axa kartı (1 belge) + Dr. Şimşek kartı (föylü) — aynı esas + mahkeme, farklı müvekkil.
    Artı: aynı TKU'lu ama farklı esaslı (ilişkili dava) üçüncü kart — gruba GİRMEZ."""
    db = db_env()
    try:
        axa = _kart(db, "S3.AXA........0782.HUKUK.00000", foy=[("H-1", "TKU-1014")], belge=1)
        dr = _kart(db, "D1.H_SIMSEK...0001.HUKUK.00000", muvekkil=("Hüseyin Şimşek",),
                   foy=[("H-2", "TKU-1014")])
        db.add(models.CaseStageDecision(case_id=dr.id, stage="YEREL", sira_no=1, karar_no="2020/1",
                                        karar_tarihi=date(2020, 1, 1), dogrulama_durumu="BELIRSIZ"))
        iliskili = _kart(db, "S3.AXA........0783.IDARE.00000", esas="2019/12", court="Mersin 1. İdare Mahkemesi",
                         file_type="İdare", foy=[("H-3", "TKU-1014")])
        db.commit()
        return db_env, axa.id, dr.id, iliskili.id
    finally:
        db.close()


def test_gruplari_bul_ayni_esas_birden_cok_kart(tarsus):
    fabrika, axa_id, dr_id, iliskili_id = tarsus
    db = fabrika()
    try:
        gruplar = tb.gruplari_bul(db)
        assert len(gruplar) == 1
        g = gruplar[0]
        assert (g.tku_no, g.esas_no) == ("TKU-1014", "2014/394")
        assert g.kart_idler == sorted([axa_id, dr_id])          # ilişkili dava (2019/12) dışarıda
        assert tb.gruplari_bul(db, tku=["TKU-9999"]) == []
    finally:
        db.close()


def test_kalan_sec_belge_foy_id_sirasi(db_env):
    db = db_env()
    try:
        a = _kart(db, "A", foy=[("F-1", "T")])                               # 0 belge, 1 föy, en eski
        b = _kart(db, "B", muvekkil=("X",), foy=[("F-2", "T")], belge=1)     # 1 belge
        c = _kart(db, "C", muvekkil=("Y",), foy=[("F-3", "T"), ("F-4", "T")])  # 0 belge, 2 föy
        assert tb.kalan_sec(db, [a, b, c]).id == b.id      # belge kazanır
        assert tb.kalan_sec(db, [a, c]).id == c.id         # föy sayısı
        d = _kart(db, "D", muvekkil=("Z",), foy=[("F-5", "T")])
        assert tb.kalan_sec(db, [d, a]).id == a.id         # en eski
    finally:
        db.close()


def test_kuru_kosu_hicbir_sey_yazmaz_ama_plan_verir(tarsus):
    fabrika, axa_id, dr_id, _ = tarsus
    gruplar = tb.gruplari_birlestir(fabrika)
    assert gruplar[0].kalan_id == axa_id                    # belgeli kart kalır
    s = gruplar[0].sonuclar[0]
    assert s.ret is None and s.mukerrer_id == dr_id and s.tasinan["foy"] == 1
    db = fabrika()
    try:
        assert db.get(models.Case, dr_id).deleted_at is None
        assert db.query(models.CaseFoy).filter_by(sistem_no="H-2").one().case_id == dr_id
    finally:
        db.close()


def test_apply_muvekkil_ayrimi_tek_kartta_toplanir_foy_eski_ofis_noyu_tasir(tarsus):
    fabrika, axa_id, dr_id, iliskili_id = tarsus
    gruplar = tb.gruplari_birlestir(fabrika, apply=True, kim="test")
    s = gruplar[0].sonuclar[0]
    assert s.ret is None and s.tasinan["taraf_tasinan"] == 1 and s.tasinan["asama"] == 1
    db = fabrika()
    try:
        kalan = db.get(models.Case, axa_id)
        sonen = db.get(models.Case, dr_id)
        assert sorted(p.name for p in kalan.parties if p.party_type == "CLIENT") == ["Axa Sigorta A.Ş.", "Hüseyin Şimşek"]
        assert [p.name for p in kalan.parties if p.party_type == "COUNTER"] == ["Sevgi Atilla"]   # tekil
        foyler = {f.sistem_no: f for f in db.query(models.CaseFoy).filter_by(case_id=axa_id)}
        assert set(foyler) == {"H-1", "H-2"}
        assert foyler["H-2"].onceki_tracking_no == "D1.H_SIMSEK...0001.HUKUK.00000"
        assert foyler["H-1"].onceki_tracking_no is None                     # hep bu karttaydı
        assert foyler["H-2"].case_party_id == next(p.id for p in kalan.parties if p.name == "Hüseyin Şimşek")
        assert sonen.deleted_at is not None and sonen.active is False
        assert sonen.delete_reason.startswith("TKU kart birleştirmesi:") and f"#{axa_id}" in sonen.delete_reason
        assert sonen.tracking_no == "D1.H_SIMSEK...0001.HUKUK.00000"       # ofis no sönen kartta da kalır
        tarihce = db.query(models.CaseHistory).filter_by(case_id=axa_id, field_name="tku_birlestirme").one()
        assert tarihce.old_value == "D1.H_SIMSEK...0001.HUKUK.00000"
        assert db.get(models.Case, iliskili_id).deleted_at is None          # ilişkili davaya dokunulmadı
        assert db.query(models.CaseDocument).count() == 1                    # belge envanteri
        # Eski ofis numarasıyla arama birleşik kartı bulur (föy kolu); sönen kart da
        # kendi tracking_no'suyla eşleşir ama get_cases soft-delete filtresiyle eler.
        ids = {r[0] for r in db.execute(case_manager._search_term_ids("D1.H_SIMSEK...0001.HUKUK.00000", True))}
        assert axa_id in ids
        # İkinci koşu: grup kalmadı
        assert tb.gruplari_bul(db) == []
    finally:
        db.close()


def test_mahkeme_veya_tur_farkli_kart_reddedilir(db_env):
    db = db_env()
    try:
        a = _kart(db, "A", foy=[("F-1", "TKU-5")])
        b = _kart(db, "B", muvekkil=("X",), court="Adana 1. Asliye Hukuk Mahkemesi", foy=[("F-2", "TKU-5")])
        c = _kart(db, "C", muvekkil=("Y",), file_type="İdare", foy=[("F-3", "TKU-5")])
        db.commit()
        a_id, b_id, c_id = a.id, b.id, c.id
    finally:
        db.close()
    gruplar = tb.gruplari_birlestir(db_env, apply=True)
    assert len(gruplar) == 1 and gruplar[0].kalan_id == a_id
    retler = {s.mukerrer_id: s.ret for s in gruplar[0].sonuclar}
    assert "mahkeme farklı" in retler[b_id]
    assert "dosya türü farklı" in retler[c_id]
    db = db_env()
    try:
        assert db.query(models.Case).filter(models.Case.deleted_at.isnot(None)).count() == 0
    finally:
        db.close()


def test_uc_kartli_grup_ve_zincir_esleme(db_env):
    """Aynı esasta üç kart tek karta iner; ikinci TKU'da aynı kart geçince yeniden eşlenir."""
    db = db_env()
    try:
        a = _kart(db, "A", muvekkil=("Ak Sigorta A.Ş.",), foy=[("F-1", "TKU-1"), ("F-4", "TKU-2")])
        b = _kart(db, "B", muvekkil=("Deniz Çakır",), foy=[("F-2", "TKU-1")])
        c = _kart(db, "C", muvekkil=("Ali Veli",), foy=[("F-3", "TKU-1")])
        d = _kart(db, "D", muvekkil=("Ayşe Yılmaz",), foy=[("F-5", "TKU-2")])
        db.commit()
        ids = (a.id, b.id, c.id, d.id)
    finally:
        db.close()
    gruplar = tb.gruplari_birlestir(db_env, apply=True)
    assert [(g.tku_no, g.kalan_id) for g in gruplar] == [("TKU-1", ids[0]), ("TKU-2", ids[0])]
    assert all(s.ret is None for g in gruplar for s in g.sonuclar)
    db = db_env()
    try:
        kalan = db.get(models.Case, ids[0])
        assert sorted(p.name for p in kalan.parties if p.party_type == "CLIENT") == [
            "Ak Sigorta A.Ş.", "Ali Veli", "Ayşe Yılmaz", "Deniz Çakır"]
        assert db.query(models.CaseFoy).filter_by(case_id=ids[0]).count() == 5
        assert db.query(models.Case).filter(models.Case.deleted_at.isnot(None)).count() == 3
    finally:
        db.close()


def test_yer_tutucu_esas_gruba_girmez_bosluk_farki_yutulur(db_env):
    """'2021/' ve '2014/???' kimlik değildir; '2020 / 1777' = '2020/1777'."""
    db = db_env()
    try:
        _kart(db, "A", esas="2021/", foy=[("F-1", "TKU-7")])
        _kart(db, "B", muvekkil=("X",), esas="2021/", foy=[("F-2", "TKU-7")])
        _kart(db, "C", muvekkil=("Y",), esas="2014/???", foy=[("F-3", "TKU-7")])
        d = _kart(db, "D", muvekkil=("Z",), esas="2020 / 1777", foy=[("F-4", "TKU-8")])
        e = _kart(db, "E", muvekkil=("W",), esas="2020/1777", foy=[("F-5", "TKU-8")])
        db.flush()
        gruplar = tb.gruplari_bul(db)
        assert [(g.tku_no, g.esas_no, g.kart_idler) for g in gruplar] == [("TKU-8", "2020/1777", [d.id, e.id])]
    finally:
        db.close()


@pytest.mark.parametrize("a, b, uyumlu", [
    ("Kocaeli 2. İdare Mahkemesi", "Kocaeli 2. İdare Mahkemeleri", True),           # Mahkemesi/Mahkemeleri
    ("Didim 1. Asliye Hukuk Mahkemesi", "Didim 1. Asliye Hukuk Mahkemesi (tüketici Mahkemesi Sıfatıyla)", True),
    ("Şanlıurfa 1. İdare Mahkemesi", "Şanlıurfa İdare Mahkemesi", True),           # tek mahkemeli yer, "1." yok
    ("ANKARA 5. TÜKETİCİ MAHKEMESİ", "Ankara 5. Tüketici Mahkemesi", True),        # büyük/küçük harf
    ("", "Ankara 5. Tüketici Mahkemesi", True),                                     # biri boş
    ("Ankara 5. İdare Mahkemesi", "Ankara 15. İdare Mahkemesi", False),            # sıra farklı
    ("Antalya 1. İdare Mahkemesi", "Antalya 2. İdare Mahkemesi", False),
    ("İstanbul 4. Tüketici Mahkemesi", "Ankara 5. Tüketici Mahkemesi", False),     # yer farklı
    ("Antalya 5. İdare Mahkemesi", "Antalya 5. Sulh Hukuk Mahkemesi", False),      # tür farklı
])
def test_mahkeme_uyumu_yazim_farki_yutar_kimlik_farki_yutmaz(a, b, uyumlu):
    assert (tb.mahkeme_uyumu(a, b) is None) is uyumlu
    assert (tb.mahkeme_uyumu(b, a) is None) is uyumlu                              # simetrik


def test_mahkeme_yazim_farki_birlesir(db_env):
    db = db_env()
    try:
        a = _kart(db, "A", court="Kocaeli 2. İdare Mahkemesi", file_type="İdare", foy=[("F-1", "TKU-9")])
        b = _kart(db, "B", muvekkil=("X",), court="Kocaeli 2. İdare Mahkemeleri", file_type="İdare",
                  foy=[("F-2", "TKU-9")])
        db.commit()
        a_id, b_id = a.id, b.id
    finally:
        db.close()
    gruplar = tb.gruplari_birlestir(db_env, apply=True)
    assert gruplar[0].sonuclar[0].ret is None and gruplar[0].kalan_id == a_id
    db = db_env()
    try:
        assert db.get(models.Case, b_id).deleted_at is not None
    finally:
        db.close()


def test_mukerrer_scripti_varsayilanda_muvekkil_ayrimini_hala_reddeder(db_env):
    db = db_env()
    try:
        a = _kart(db, "A")
        b = _kart(db, "B", muvekkil=("X",))
        assert "müvekkil" in mb.on_kosul(a, b)
        assert mb.on_kosul(a, b, muvekkil_ayrimi=True) is None
    finally:
        db.close()


def test_ozet_ve_rapor(tarsus, tmp_path):
    gruplar = tb.gruplari_birlestir(tarsus[0])
    metin = tb.ozet_metni(gruplar, apply=False)
    assert "KURU KOŞU" in metin and "sönen kart          : 1" in metin
    yol = tmp_path / "tku.csv"
    tb.rapor_yaz(gruplar, str(yol), apply=False)
    satirlar = yol.read_text(encoding="utf-8-sig").splitlines()
    assert satirlar[0].startswith("tku_no;esas_no;kalan_id")
    assert ";PLAN;" in satirlar[1] and "Hüseyin Şimşek" in satirlar[1]
