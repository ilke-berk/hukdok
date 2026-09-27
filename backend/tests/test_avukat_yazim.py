"""`scripts/avukat_yazim.py` — avukat adlarının yazım birliği + kart–avukat bağı (27.09 kararı):
liste 7 avukatı normal yazıma geçirir, 3 dış avukat eklenir, idari personel listeye girmez;
kart yazımı tarihçeli tek biçime iner, aynı kartta ikizlenen satır birleşir, bağ kurulur;
"A;B" birleşik değer ve silinmiş kart dokunulmaz; kuru koşu yazmaz; ikinci koşu 0.
"""
from datetime import datetime, timezone

import models
from scripts import avukat_yazim as ay
from tests import test_g179_ekip_cevabi_1209 as g179
from tests.test_g064_aktarim_cekirdek import _kart

db_env = g179.db_env          # nitelik ataması: pytest için aynı fixture, ruff F811 sanmaz


def _kur(fabrika):
    db = fabrika()
    try:
        tugce = models.Lawyer(code="TUGCEUNG", name="TUGCE UNGOR", gorev="AVUKAT", sequence=1)
        berna = models.Lawyer(code="BERNABUR", name="BERNA BURCU BASYURT", gorev="AVUKAT", sequence=2)
        diger = models.Lawyer(code="ZEYNEPAY", name="ZEYNEP AYAN", gorev="DIŞ AVUKAT", sequence=3)
        db.add_all([tugce, berna, diger])
        db.flush()
        k1 = _kart(db, "D1.K1........0001.HUKUK.00000", "", responsible_lawyer_name="TUGCE UNGOR",
                   uyap_lawyer_name="Av. Tuğçe Ungor Yanık")
        k2 = _kart(db, "D1.K2........0002.HUKUK.00000", "", responsible_lawyer_name="Tuğçe Üngör Yanık;Serap Turgal")
        silinmis = _kart(db, "D1.K3........0003.HUKUK.00000", "", responsible_lawyer_name="TUGCE UNGOR",
                         deleted_at=datetime.now(timezone.utc))
        db.add_all([
            # k1: aynı kişinin iki yazımı → birleşir (bağlı olan kalır)
            models.CaseLawyer(case_id=k1.id, name="Tuğçe Üngör Yanık"),
            models.CaseLawyer(case_id=k1.id, name="TUGCE UNGOR", lawyer_id=tugce.id),
            models.CaseLawyer(case_id=k1.id, name="Cigdem Tel"),          # idari: yazım düzelir, bağ yok
            models.CaseLawyer(case_id=k1.id, name="Selda ŞENER"),          # yeni dış avukat → bağlanır
            models.CaseLawyer(case_id=k2.id, name="Berna Burcu Başyurt"),  # liste adı düzelince bağlanır
            models.CaseLawyer(case_id=silinmis.id, name="TUGCE UNGOR"),
        ])
        db.commit()
        return {"k1": k1.id, "k2": k2.id, "silinmis": silinmis.id, "tugce": tugce.id, "berna": berna.id}
    finally:
        db.close()


def test_anahtar_turkce_katlar_ve_unvani_atar():
    assert ay.anahtar("Av. Tuğçe Ungor Yanık") == ay.anahtar("TUGCE UNGOR YANIK") == "TUGCE UNGOR YANIK"
    assert ay.anahtar("Selda ŞENER") == "SELDA SENER"
    assert ay.anahtar("  Barış   Yücel ") == "BARIS YUCEL"


def test_kuru_kosu_yazmaz(db_env):
    _kur(db_env)
    sonuc, _, _ = ay.kos(db_env, apply=False)
    assert sonuc.sayim("liste", "YAPILDI") == 2 and sonuc.sayim("ekle", "YAPILDI") == 3
    db = db_env()
    try:
        assert {av.name for av in db.query(models.Lawyer)} == {"TUGCE UNGOR", "BERNA BURCU BASYURT", "ZEYNEP AYAN"}
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.CaseLawyer).count() == 6
    finally:
        db.close()


def test_apply_yazim_bag_birlesme_ve_ikinci_kosu_sifir(db_env):
    ids = _kur(db_env)
    sonuc, sayac, kalan = ay.kos(db_env, apply=True, kim="ilke")
    assert sayac == {"birlesik_atlandi": 1, "birlesen_satir": 1}

    db = db_env()
    try:
        liste = {av.code: (av.name, av.gorev) for av in db.query(models.Lawyer)}
        assert liste["TUGCEUNG"] == ("Tuğçe Üngör Yanık", "AVUKAT")
        assert liste["BERNABUR"] == ("Berna Burcu Başyurt", "AVUKAT")
        assert liste["ZEYNEPAY"] == ("ZEYNEP AYAN", "DIŞ AVUKAT")          # tabloda olmayan dokunulmaz
        for ad, kod in ay.YENI_DIS_AVUKATLAR:
            assert liste[kod] == (ad, "DIŞ AVUKAT")
        assert not any(ay.anahtar(ad) == ay.anahtar(p) for ad, _ in liste.values() for p in ay.IDARI_PERSONEL)

        k1 = db.get(models.Case, ids["k1"])
        assert (k1.responsible_lawyer_name, k1.uyap_lawyer_name) == ("Tuğçe Üngör Yanık", "Tuğçe Üngör Yanık")
        assert db.get(models.Case, ids["k2"]).responsible_lawyer_name == "Tuğçe Üngör Yanık;Serap Turgal"
        assert db.get(models.Case, ids["silinmis"]).responsible_lawyer_name == "TUGCE UNGOR"

        satirlar = {(s.case_id, s.name): s.lawyer_id for s in db.query(models.CaseLawyer)}
        selda = db.query(models.Lawyer).filter_by(code="SELDASEN").one().id
        assert satirlar == {
            (ids["k1"], "Tuğçe Üngör Yanık"): ids["tugce"],   # ikiz birleşti, bağlı olan kaldı
            (ids["k1"], "Çiğdem Tel"): None,                  # idari personel: bağ yok
            (ids["k1"], "Selda Şener"): selda,
            (ids["k2"], "Berna Burcu Başyurt"): ids["berna"],
            (ids["silinmis"], "TUGCE UNGOR"): None,           # silinmiş kart kapsam dışı
        }
        assert kalan == {"Çiğdem Tel": 1, "TUGCE UNGOR": 1}

        tarihce = {(h.case_id, h.field_name, h.old_value, h.new_value, h.changed_by, h.source)
                   for h in db.query(models.CaseHistory)}
        assert (ids["k1"], "responsible_lawyer_name", "TUGCE UNGOR", "Tuğçe Üngör Yanık", "ilke", "avukat_yazim") in tarihce
        assert (ids["k1"], "uyap_lawyer_name", "Av. Tuğçe Ungor Yanık", "Tuğçe Üngör Yanık", "ilke", "avukat_yazim") in tarihce
        assert (ids["k1"], "avukat", "Cigdem Tel", "Çiğdem Tel", "ilke", "avukat_yazim") in tarihce
        assert not any(h[0] == ids["silinmis"] for h in tarihce)
    finally:
        db.close()

    ikinci, sayac2, _ = ay.kos(db_env, apply=True)
    assert not [k for k in ikinci.kalemler if k.sonuc == "YAPILDI"]
    assert sayac2["birlesen_satir"] == 0


def test_iki_aday_satir_ret(db_env):
    db = db_env()
    try:
        db.add_all([models.Lawyer(code="A1", name="SERAP TURGAL"), models.Lawyer(code="A2", name="Serap  TURGAL")])
        db.commit()
    finally:
        db.close()
    sonuc, _, _ = ay.kos(db_env, apply=True)
    serap = [k for k in sonuc.kalemler if k.adim == "liste" and "Serap" in k.hedef]
    assert [k.sonuc for k in serap] == ["RET"]
