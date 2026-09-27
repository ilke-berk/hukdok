"""G224 — avukat envanteri (`services/avukat_envanteri.py`) + betiği.

Kullanıcı şartı (27.09): avukat kimliği geçişinde hiçbir dava kaybolmamalı. Bu
testler ölçümün doğru sayıyı verdiğini ve karşılaştırmanın kaybı İHLAL, artışı
BİLGİ saydığını kilitler. Özellikle ÖNBELLEK TUZAĞI: filtre avukatı süreç-içi
`DynamicConfig`'ten çözer; betik sürecinde önbellek boştur ve filtre 0 sayar —
`olc` önbelleği DB'den doldurmazsa "0 → 0 denk" sahte yeşili doğar.

SQLite'ta `translate()` yoktur; avukat filtresinin SQL ön-elemesi onu kullanır.
Fixture Postgres'in `translate`'ini Python ile tanımlar (aynı semantik: eşit
uzunlukta kaynak/hedef, karakter başına eşleme).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from managers.config_manager import DynamicConfig
from scripts import avukat_envanteri as betik
from services import avukat_envanteri as env


def _translate(deger, kaynak, hedef):
    if deger is None:
        return None
    return deger.translate(str.maketrans(kaynak, hedef))


@pytest.fixture()
def fabrika():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.create_function("translate", 3, _translate)

    Base.metadata.create_all(engine)
    config = DynamicConfig.get_instance()
    onceki = config.get_lawyers()
    config.set_lawyers([])                     # betik süreci gibi: önbellek BOŞ
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    config.set_lawyers(onceki)
    engine.dispose()


@pytest.fixture()
def veri(fabrika):
    """İki avukat + bir pasif avukat; beş kart; case_lawyers ve belgeler.

    c1 sorumlu "SERAP TURGAL" · c2 sorumlu "Av. Tuğçe Ungör Yanık;Serap Turgal" ·
    c3 PASİF kart (Serap) · c4 yalnız bağsız case_lawyers "Serap Turgal" ·
    c5 bağlı case_lawyers (Tuğçe). Belgeler: SERAPTUR ×2 (+1 silinmiş), TUGCEUNG ×1.
    """
    db = fabrika()
    serap = models.Lawyer(code="SERAPTUR", name="Serap Turgal", active=True, sequence=1)
    tugce = models.Lawyer(code="TUGCEUNG", name="Tuğçe Ungör Yanık", active=True, sequence=2)
    eski = models.Lawyer(code="ESKIAVUK", name="Eski Avukat", active=False, sequence=3)
    db.add_all([serap, tugce, eski])
    db.flush()
    kartlar = {}
    for no, sorumlu, aktif in [
        ("c1", "SERAP TURGAL", True),
        ("c2", "Av. Tuğçe Ungör Yanık;Serap Turgal", True),
        ("c3", "Serap Turgal", False),
        ("c4", None, True),
        ("c5", None, True),
    ]:
        kart = models.Case(tracking_no=f"G224.{no}", status="DERDEST",
                           responsible_lawyer_name=sorumlu, active=aktif)
        db.add(kart)
        db.flush()
        kartlar[no] = kart.id
    db.add_all([
        models.CaseLawyer(case_id=kartlar["c4"], name="Serap Turgal"),
        models.CaseLawyer(case_id=kartlar["c5"], name="Tuğçe Ungör Yanık", lawyer_id=tugce.id),
        models.CaseLawyer(case_id=kartlar["c5"], name="Harici Vekil"),
    ])
    for i, (kod, silinmis) in enumerate([("SERAPTUR", False), ("SERAPTUR", False),
                                          ("SERAPTUR", True), ("TUGCEUNG", False), (None, False)]):
        db.add(models.CaseDocument(
            case_id=kartlar["c1"], original_filename=f"b{i}.pdf", stored_filename=f"b{i}.pdf",
            avukat_kodu=kod, deleted_at=datetime.now(timezone.utc) if silinmis else None,
        ))
    kimlikler = {"kartlar": kartlar, "serap_id": serap.id, "tugce_id": tugce.id}
    db.commit()
    db.close()
    return kimlikler


def _foto(fabrika):
    db = fabrika()
    try:
        return env.olc(db)
    finally:
        db.close()


# ── 1. fotoğraf alanları ─────────────────────────────────────────────────────

def test_fotograf_alanlari(fabrika, veri):
    foto = _foto(fabrika)
    assert foto["surum"] == 1 and foto["olculme_zamani"]
    assert set(foto["avukatlar"]) == {"SERAPTUR", "TUGCEUNG", "ESKIAVUK"}

    serap = foto["avukatlar"]["SERAPTUR"]
    assert serap == {
        "kimlik": None, "code": "SERAPTUR", "ad": "Serap Turgal", "aktif": True,
        "filtre_dava": 3,            # c1 + c2 + c4 (case_lawyers); c3 pasif kart sayılmaz
        "sorumlu_kart": 2,           # c1 + c2
        "case_lawyers": 1, "case_lawyers_bagli": 0,
        "belge": 2,                  # silinmiş belge sayılmaz
    }
    tugce = foto["avukatlar"]["TUGCEUNG"]
    assert (tugce["filtre_dava"], tugce["sorumlu_kart"], tugce["case_lawyers"],
            tugce["case_lawyers_bagli"], tugce["belge"]) == (2, 1, 1, 1, 1)
    assert foto["avukatlar"]["ESKIAVUK"]["aktif"] is False

    assert foto["toplamlar"] == {
        "avukat": 3,
        "aktif_dava": 4,
        "sorumlu_dolu_dava": 2,
        "case_lawyers_satir": 3,
        "case_lawyers_bagli": 1,
        "case_lawyers_bagsiz": 2,
        "avukatli_belge": 3,
        "bagsiz_case_lawyers_adlari": {"Harici Vekil": 1, "Serap Turgal": 1},
    }


# ── 2. önbellek tuzağı ───────────────────────────────────────────────────────

def test_filtre_sayisi_onbellek_doldurularak_olculur(fabrika, veri):
    """Önbellek BOŞKEN filtre kodu çözemez ve 0 bulur; `olc` ise gerçek sayıyı verir
    ve iş bitince önbelleği eski hâline döndürür."""
    from managers.case_manager import _lawyer_filter_case_ids

    config = DynamicConfig.get_instance()
    assert config.get_lawyers() == []
    db = fabrika()
    try:
        assert _lawyer_filter_case_ids(db, "SERAPTUR", None) == set()   # tuzağın kendisi
        foto = env.olc(db)
    finally:
        db.close()
    assert foto["avukatlar"]["SERAPTUR"]["filtre_dava"] == 3
    assert config.get_lawyers() == []                                   # geri kondu


def test_onbellek_uygulamanin_bicimiyle_yalniz_aktiflerle_dolar(fabrika, veri, monkeypatch):
    gorulen = []
    gercek = env._lawyer_filter_case_ids

    def _izle(db, secim, tenant_id):
        gorulen.append([lw["code"] for lw in DynamicConfig.get_instance().get_lawyers()])
        return gercek(db, secim, tenant_id)

    monkeypatch.setattr(env, "_lawyer_filter_case_ids", _izle)
    _foto(fabrika)
    assert gorulen and all(kodlar == ["SERAPTUR", "TUGCEUNG"] for kodlar in gorulen)


# ── 3. karşılaştırma: kayıp İHLAL ────────────────────────────────────────────

def test_ayni_durum_denk(fabrika, veri):
    assert env.karsilastir(_foto(fabrika), _foto(fabrika)) == []


def test_kart_silinince_ihlal(fabrika, veri):
    once = _foto(fabrika)
    db = fabrika()
    kart = db.get(models.Case, veri["kartlar"]["c1"])
    kart.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.close()

    ihlal = env.ihlaller(env.karsilastir(once, _foto(fabrika)))
    alanlar = {(m["avukat"], m["alan"]) for m in ihlal}
    assert ("SERAPTUR", "filtre_dava") in alanlar
    assert ("SERAPTUR", "sorumlu_kart") in alanlar
    assert (None, "aktif_dava") in alanlar


def test_case_lawyers_satiri_dusunce_ihlal(fabrika, veri):
    once = _foto(fabrika)
    db = fabrika()
    db.query(models.CaseLawyer).filter(models.CaseLawyer.name == "Serap Turgal").delete()
    db.commit()
    db.close()

    ihlal = env.ihlaller(env.karsilastir(once, _foto(fabrika)))
    alanlar = {(m["avukat"], m["alan"]): (m["once"], m["sonra"]) for m in ihlal}
    assert alanlar[("SERAPTUR", "case_lawyers")] == (1, 0)
    assert alanlar[("SERAPTUR", "filtre_dava")] == (3, 2)
    assert alanlar[(None, "case_lawyers_satir")] == (3, 2)


def test_bag_artisi_ihlal_degil(fabrika, veri):
    once = _foto(fabrika)
    db = fabrika()
    satir = db.query(models.CaseLawyer).filter(models.CaseLawyer.name == "Serap Turgal").one()
    satir.lawyer_id = veri["serap_id"]
    db.commit()
    db.close()

    fark = env.karsilastir(once, _foto(fabrika))
    assert env.ihlaller(fark) == []
    bilgi = {(m["avukat"], m["alan"]): (m["once"], m["sonra"]) for m in fark}
    assert bilgi[("SERAPTUR", "case_lawyers_bagli")] == (0, 1)
    assert bilgi[(None, "case_lawyers_bagli")] == (1, 2)
    assert bilgi[(None, "case_lawyers_bagsiz")] == (2, 1)      # bağsızın azalması BİLGİ
    assert ("SERAPTUR", "case_lawyers") not in bilgi            # satır sayısı aynı


def test_belge_dusunce_ihlal(fabrika, veri):
    once = _foto(fabrika)
    db = fabrika()
    belge = db.query(models.CaseDocument).filter(models.CaseDocument.avukat_kodu == "TUGCEUNG").one()
    belge.avukat_kodu = None
    db.commit()
    db.close()

    alanlar = {(m["avukat"], m["alan"]) for m in env.ihlaller(env.karsilastir(once, _foto(fabrika)))}
    assert alanlar == {("TUGCEUNG", "belge"), (None, "avukatli_belge")}


# ── 4. eşleşme: kimlik → kod → ad ────────────────────────────────────────────

def _kayit(**ek):
    temel = {"kimlik": None, "code": "SERAPTUR", "ad": "Serap Turgal", "aktif": True,
             "filtre_dava": 3, "sorumlu_kart": 2, "case_lawyers": 1, "case_lawyers_bagli": 0, "belge": 2}
    temel.update(ek)
    return temel


def test_ad_degisikliginde_kod_ayni_eslesme_korunur():
    once = {"avukatlar": {"SERAPTUR": _kayit()}, "toplamlar": {}}
    sonra = {"avukatlar": {"SERAPTUR": _kayit(ad="Serap Turgal Aksoy")}, "toplamlar": {}}
    fark = env.karsilastir(once, sonra)
    assert env.ihlaller(fark) == []
    assert [(m["tur"], m["alan"]) for m in fark] == [("BILGI", "ad")]


def test_kimlik_anahtarina_gecis_kodla_eslesir():
    """G225 sonrası anahtar kimlik olur; önceki fotoğrafın kod anahtarlı kaydı kodla bulunur."""
    once = {"avukatlar": {"SERAPTUR": _kayit()}, "toplamlar": {}}
    sonra = {"avukatlar": {"AVK-00001": _kayit(kimlik="AVK-00001")}, "toplamlar": {}}
    fark = env.karsilastir(once, sonra)
    assert env.ihlaller(fark) == []
    assert [(m["alan"], m["sonra"]) for m in fark] == [("kimlik", "AVK-00001")]


def test_kimlik_koddan_once_gelir_ve_ad_son_care():
    once = {"avukatlar": {
        "AVK-00001": _kayit(kimlik="AVK-00001", code="ESKI"),
        "X": _kayit(code="X", ad="Tuğçe Ungör Yanık"),
    }, "toplamlar": {}}
    sonra = {"avukatlar": {
        "AVK-00001": _kayit(kimlik="AVK-00001", code="YENI"),     # kod değişse de kimlik eşler
        "Y": _kayit(code="Y", ad="TUGCE UNGOR YANIK"),            # kod farklı → normalize ad
    }, "toplamlar": {}}
    fark = env.karsilastir(once, sonra)
    assert [(m["tur"], m["avukat"], m["alan"]) for m in fark] == [("BILGI", "X", "ad")]


def test_avukat_kaybolursa_ihlal_yeni_avukat_bilgi():
    once = {"avukatlar": {"SERAPTUR": _kayit()}, "toplamlar": {}}
    sonra = {"avukatlar": {"BASKA": _kayit(code="BASKA", ad="Başka Kişi")}, "toplamlar": {}}
    fark = env.karsilastir(once, sonra)
    assert [(m["tur"], m["avukat"], m["alan"]) for m in fark] == [
        ("IHLAL", "SERAPTUR", "avukat"), ("BILGI", "BASKA", "avukat"),
    ]


# ── 5. betik ─────────────────────────────────────────────────────────────────

def test_betik_kaydet_ve_karsilastir(fabrika, veri, tmp_path, capsys):
    yol = tmp_path / "once.json"
    assert betik.kos(fabrika, str(yol), None) == 0
    assert betik.oku(str(yol))["avukatlar"]["SERAPTUR"]["filtre_dava"] == 3

    assert betik.kos(fabrika, None, str(yol)) == 0            # değişiklik yok → 0
    assert "DENK" in capsys.readouterr().out

    db = fabrika()
    db.query(models.CaseLawyer).filter(models.CaseLawyer.name == "Serap Turgal").delete()
    db.commit()
    db.close()
    assert betik.kos(fabrika, None, str(yol)) == 1            # İHLAL → çıkış kodu ≠ 0
    assert "[IHLAL] SERAPTUR · case_lawyers" in capsys.readouterr().out


def test_betik_arguman_zorunlu():
    with pytest.raises(SystemExit) as exc:
        betik.main([])
    assert exc.value.code != 0
