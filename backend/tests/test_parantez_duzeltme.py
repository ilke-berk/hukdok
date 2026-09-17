"""`scripts/parantez_duzeltme.py` — kapanmamış parantezli 5 hücre (ekibe söz 17.09):
taraf adı ve mahkeme tarihçeli düzelir, 12398'e gömülü eski esas esas tarihçesine (ONCEKI)
gider, güncel esas değişmez; beklenmeyen değere dokunulmaz; kuru koşu yazmaz; ikinci koşu 0.

Sabit tablolar prod id'leri taşır → testte monkeypatch ile bu DB'nin id'lerine çevrilir.
"""
from datetime import datetime, timezone

import models
from scripts import parantez_duzeltme as pd
from tests import test_g179_ekip_cevabi_1209 as g179
from tests.test_g064_aktarim_cekirdek import _kart

db_env = g179.db_env          # nitelik ataması: pytest için aynı fixture, ruff F811 sanmaz

ESKI_TARAF = "Fatma Serap Aydoğdu ( Kendi adına Asaleten"
ESKI_MAHKEME = "İstanbul Anadolu 1. Asliye Ticaret Mahkemesi( Eski--istanbul Anadolu 10. Atm)2013/720)"
YENI_MAHKEME = "İstanbul Anadolu 1. Asliye Ticaret Mahkemesi"


def _kur(fabrika, monkeypatch, *, taraf_adi=ESKI_TARAF):
    db = fabrika()
    try:
        kart = _kart(db, "S0.KORU.......1660.HUKUK.00000", "", court=ESKI_MAHKEME)
        db.add(models.CaseEsasNumber(case_id=kart.id, esas_no="2014/700", stage="YEREL", is_current=True))
        kart.esas_no = "2014/700"
        taraf = models.CaseParty(case_id=kart.id, name=taraf_adi, role="Karşı Taraf", party_type="COUNTER")
        temiz = models.CaseParty(case_id=kart.id, name="Medine Kiriş", role="Karşı Taraf", party_type="COUNTER")
        db.add_all([taraf, temiz])
        db.commit()
        kart_id, taraf_id = kart.id, taraf.id
    finally:
        db.close()
    monkeypatch.setattr(pd, "TARAF_DUZELTMELERI", ((kart_id, taraf_id, ESKI_TARAF, "Fatma Serap Aydoğdu"),))
    monkeypatch.setattr(pd, "MAHKEME_DUZELTMELERI", (
        (kart_id, ESKI_MAHKEME, YENI_MAHKEME, "2013/720", "İstanbul Anadolu 10. Asliye Ticaret Mahkemesi"),))
    return kart_id, taraf_id


def test_kuru_kosu_yazmaz_ama_olcer(db_env, monkeypatch):
    kart_id, taraf_id = _kur(db_env, monkeypatch)
    sonuc, kalan = pd.kos(db_env, apply=False)
    assert (sonuc.sayim("taraf", "YAPILDI"), sonuc.sayim("mahkeme", "YAPILDI")) == (1, 1)
    assert kalan == (0, 0)                      # transaction içinde düzeltme sonrası ölçüm
    db = db_env()
    try:
        assert db.get(models.CaseParty, taraf_id).name == ESKI_TARAF
        assert db.get(models.Case, kart_id).court == ESKI_MAHKEME
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.CaseEsasNumber).count() == 1
    finally:
        db.close()


def test_apply_duzeltir_esas_tarihcesi_ikinci_kosu_sifir(db_env, monkeypatch):
    kart_id, taraf_id = _kur(db_env, monkeypatch)
    sonuc, kalan = pd.kos(db_env, apply=True, kim="ilke")
    assert [k.sonuc for k in sonuc.kalemler] == ["YAPILDI", "YAPILDI"] and kalan == (0, 0)

    db = db_env()
    try:
        kart = db.get(models.Case, kart_id)
        assert kart.court == YENI_MAHKEME and kart.esas_no == "2014/700"
        assert db.get(models.CaseParty, taraf_id).name == "Fatma Serap Aydoğdu"
        esaslar = {(e.esas_no, e.stage, e.court, e.is_current) for e in db.query(models.CaseEsasNumber)}
        assert esaslar == {("2014/700", "YEREL", None, True),
                           ("2013/720", "ONCEKI", "İstanbul Anadolu 10. Asliye Ticaret Mahkemesi", False)}
        tarihce = {(h.field_name, h.old_value, h.new_value) for h in db.query(models.CaseHistory)}
        assert tarihce == {("taraf", f"{ESKI_TARAF} (Karşı Taraf)", "Fatma Serap Aydoğdu (Karşı Taraf)"),
                           ("court", ESKI_MAHKEME, YENI_MAHKEME)}
    finally:
        db.close()

    ikinci, _ = pd.kos(db_env, apply=True)
    assert [k.sonuc for k in ikinci.kalemler] == ["ATLANDI", "ATLANDI"]


def test_beklenmeyen_deger_ret(db_env, monkeypatch):
    _, taraf_id = _kur(db_env, monkeypatch, taraf_adi="Fatma Serap Aydoğdu (elle düzeltilmiş)")
    sonuc, kalan = pd.kos(db_env, apply=True)
    assert sonuc.sayim("taraf", "RET") == 1 and kalan == (0, 0)   # elle değer dengeli; mahkeme düzeldi
    db = db_env()
    try:
        assert db.get(models.CaseParty, taraf_id).name == "Fatma Serap Aydoğdu (elle düzeltilmiş)"
    finally:
        db.close()


def test_bekci_dengesiz_parantezi_sayar(db_env):
    db = db_env()
    try:
        kart = _kart(db, "A", "", court="X Mahkemesi (Eski")
        silinmis = _kart(db, "B", "", court="Y (", deleted_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        db.add_all([models.CaseParty(case_id=kart.id, name="Ad (Soyad", role="R", party_type="COUNTER"),
                    models.CaseParty(case_id=kart.id, name="Tam (Ad)", role="R", party_type="COUNTER"),
                    models.CaseParty(case_id=silinmis.id, name="Z (", role="R", party_type="COUNTER")])
        db.flush()
        assert pd.kalan_dengesiz(db) == (1, 1)
    finally:
        db.close()
