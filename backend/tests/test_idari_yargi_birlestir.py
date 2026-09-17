"""`scripts/idari_yargi_birlestir.py` — "İdari Yargı" dava türünün "İdare"ye birleşmesi
(ekibe söz 17.09): kartlar tarihçeli taşınır, ofis no DEĞİŞMEZ, kopya mahkeme türleri ve
tür satırı silinir, kuru koşu yazmaz, ikinci koşu 0. Kod tarafının bekçileri de burada:
seed ve `judicial_unit` artık "İdari Yargı" üretmez.
"""
from datetime import datetime, timezone

import models
from managers.seed_data import COURT_TYPES_SEED
from scripts import idari_yargi_birlestir as iy
from services.judicial_unit import PATTERNS
from services.rapor.registry import DAVA_TURLERI
from tests import test_g179_ekip_cevabi_1209 as g179
from tests.test_g064_aktarim_cekirdek import _kart

db_env = g179.db_env          # nitelik ataması: pytest için aynı fixture, ruff F811 sanmaz


def _kur(fabrika):
    db = fabrika()
    try:
        db.add_all([
            models.FileType(code="İdare", name="İdare", active=True, sequence=3),
            models.FileType(code="İdari Yargı", name="İdari Yargı", active=True, sequence=3),
            models.CourtType(code="İDA-İDARE-30", name="İDARE MAHKEMESİ", parent_code="İdare"),
            models.CourtType(code="İDA-İDARE-25", name="İDARE MAHKEMESİ", parent_code="İdari Yargı"),
            models.CourtType(code="İDA-OZEL-99", name="ÖZEL İDARİ BİRİM", parent_code="İdari Yargı"),
        ])
        aktif = _kart(db, "X1.B_DR.......0001.IDARI.00100", "", file_type="İdari Yargı")
        silinmis = _kart(db, "X1.E_DR.......0001.IDARI.00000", "", file_type="İdari Yargı",
                         deleted_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        eski_idare = _kart(db, "D1.G_TANYEL...0003.IDARI.00000", "", file_type="İdare")
        hukuk = _kart(db, "S0.KORU.......0001.HUKUK.00000", "", file_type="Hukuk")
        db.commit()
        return aktif.id, silinmis.id, eski_idare.id, hukuk.id
    finally:
        db.close()


def test_kuru_kosu_yazmaz(db_env):
    aktif, *_ = _kur(db_env)
    sonuc = iy.kos(db_env, apply=False)
    assert sonuc.sayim("kart", "YAPILDI") == 2
    db = db_env()
    try:
        assert db.get(models.Case, aktif).file_type == "İdari Yargı"
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.FileType).count() == 2
    finally:
        db.close()


def test_apply_birlestirir_ofis_no_degismez_ikinci_kosu_sifir(db_env):
    aktif, silinmis, eski_idare, hukuk = _kur(db_env)
    sonuc = iy.kos(db_env, apply=True, kim="ilke")
    assert (sonuc.sayim("kart", "YAPILDI"), sonuc.sayim("mahkeme", "YAPILDI"), sonuc.sayim("tur", "YAPILDI")) == (2, 2, 1)

    db = db_env()
    try:
        for cid, no in ((aktif, "X1.B_DR.......0001.IDARI.00100"), (silinmis, "X1.E_DR.......0001.IDARI.00000")):
            kart = db.get(models.Case, cid)
            assert kart.file_type == "İdare" and kart.tracking_no == no
        assert db.get(models.Case, eski_idare).tracking_no == "D1.G_TANYEL...0003.IDARI.00000"
        assert db.get(models.Case, hukuk).file_type == "Hukuk"

        tarihce = db.query(models.CaseHistory).order_by(models.CaseHistory.case_id).all()
        assert [(h.case_id, h.field_name, h.old_value, h.new_value) for h in tarihce] == [
            (aktif, "file_type", "İdari Yargı", "İdare"), (silinmis, "file_type", "İdari Yargı", "İdare")]
        assert "ilke" in tarihce[0].source

        mahkemeler = {(m.name, m.parent_code) for m in db.query(models.CourtType)}
        assert mahkemeler == {("İDARE MAHKEMESİ", "İdare"), ("ÖZEL İDARİ BİRİM", "İdare")}
        assert [t.name for t in db.query(models.FileType)] == ["İdare"]
    finally:
        db.close()

    ikinci = iy.kos(db_env, apply=True)
    assert ikinci.kalemler == []


def test_idare_satiri_yoksa_tur_silinmez(db_env):
    db = db_env()
    try:
        db.add(models.FileType(code="İdari Yargı", name="İdari Yargı", active=True, sequence=3))
        db.commit()
    finally:
        db.close()
    sonuc = iy.kos(db_env, apply=True)
    assert sonuc.sayim("tur", "RET") == 1
    db = db_env()
    try:
        assert db.query(models.FileType).count() == 1
    finally:
        db.close()


def test_kod_artik_idari_yargi_uretmez():
    """Seed her açılışta eksik satırı eklediği için birleşme kodda da kalıcı olmalı."""
    assert "İdari Yargı" not in COURT_TYPES_SEED
    assert {parent for _rx, _ad, parent in PATTERNS} <= set(COURT_TYPES_SEED)
    assert "İdari Yargı" not in DAVA_TURLERI
