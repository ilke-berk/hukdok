"""Ekip iletileri 26.09 + 01.10 (`scripts/ekip_cevabi_2609.py`): aynı davanın kartını
birleştirme, föy taşıma + föysüz kartı kapatma, yabancı künye silme (BELGE korur), paketin
boş gönderdiği mahkeme, sigortalı adı, dava konusu kısaltması (kullanıcı kaydı KORUNDU),
kuru koşu ve ikinci koşu 0.

**TEST VERİSİ KURALI:** ham satırlar elde yazılmış sözlükler (ekibin başlıklarıyla); gerçek
paket repoya GİRMEZ.
"""
import models
from managers import stage_decisions
from scripts import ekip_cevabi_2609 as ec
from tests.test_g064_aktarim_cekirdek import _kart
from tests.test_g180_birlesik_kart_ayir import _foy, _ham, db_env  # noqa: F401

IDARE5 = "İstanbul 5. İdare Mahkemesi"
IDARE13 = "İstanbul 13. İdare Mahkemesi"
BEYKOZ = "Beykoz 1. Asliye Hukuk Mahkemesi"
UZUN = "Tazminat (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)"
KISA = "Tazminat (Tıbbi Kötü Uygulama)"


def _sayim(db, model, **filtre):
    return db.query(model).filter_by(**filtre).count()


def _veri(db_env, *, belge_damgasi=False, kullanici_konu=False):  # noqa: F811
    """Altı adımın hepsini tetikleyen küçük dünya; id'leri döner."""
    db = db_env()
    try:
        # 1) #665 ↔ #13363: aynı esas + mahkeme, müvekkiller farklı (müvekkil başına kart).
        kalan = _kart(db, "AK-1057-DR.R.KARAKUS-IDR", "3.1328.00", file_type="İdare", esas_no="2021/1921",
                      court=IDARE5, subject=UZUN)
        sonen = _kart(db, "AXA-2748-DR.E.COGENDEZ-IDR", "1.20675.00", file_type="İdare", esas_no="2021/1921",
                      court=IDARE5, subject=UZUN)
        db.add_all([models.CaseParty(case_id=kalan.id, name="Ak Sigorta A.Ş.", role="Müvekkil", party_type="CLIENT"),
                    models.CaseParty(case_id=sonen.id, name="Axa Sigorta A.Ş.", role="Müvekkil", party_type="CLIENT"),
                    models.CaseParty(case_id=sonen.id, name="Ali İsmail Kurşun", role="Karşı Taraf", party_type="COUNTER")])
        _foy(db, kalan, "id-842", _ham("id-842", "3.1328.00", "IDARE", "2021/1921", IDARE5, muvekkil="Ak Sigorta A.Ş."))
        _foy(db, sonen, "id-841", _ham("id-841", "1.20675.00", "IDARE", "2021/1921", IDARE5, muvekkil="Axa Sigorta A.Ş."))
        # 2) id-5126: eski kart #3146 (föysüz kalacak) → #13360.
        eski = _kart(db, "AK-0866-DR.M.AYGUN-IDR", "3.1259.00", file_type="İdare", esas_no="2021/1880", court=IDARE13)
        hedef = _kart(db, "ANADOLU-0902-DR.K.ISCEN-IDR", "9.1220.00", file_type="İdare", esas_no="2021/1880",
                      court=IDARE13)
        db.add(models.CaseParty(case_id=eski.id, name="Ak Sigorta A.Ş.", role="Müvekkil", party_type="CLIENT"))
        _foy(db, eski, "id-5126", _ham("id-5126", "3.1259.00", "IDARE", "2021/1880", IDARE13, muvekkil="Ak Sigorta A.Ş."))
        _foy(db, hedef, "id-8855", _ham("id-8855", "9.1220.00", "IDARE", "2021/1880", IDARE13,
                                        muvekkil="Anadolu Anonim Türk Sigorta Şirketi"))
        # 3) #29: Beykoz davasında Yozgat davasının temyiz + karar düzeltme satırları.
        beykoz = _kart(db, "DR.A.ERTURK-0001-HUK", "1.11.00", file_type="Hukuk", esas_no="2013/376", court=BEYKOZ)
        _foy(db, beykoz, "H-5614", _ham("H-5614", "1.11.00", "HUKUK", "2013/376", BEYKOZ))
        stage_decisions.add_stage_decision(db, beykoz, stage="YEREL", mahkeme=BEYKOZ, esas_no="2013/376",
                                           dogrulama_durumu="BELIRSIZ", source="HUKDOK_TESLIM_x")
        stage_decisions.add_stage_decision(db, beykoz, stage="TEMYIZ", mahkeme="Danıştay 15. Daire",
                                           esas_no="2016/1086",
                                           dogrulama_durumu="BELGE" if belge_damgasi else "BELIRSIZ",
                                           source="HUKDOK_TESLIM_x")
        stage_decisions.add_stage_decision(db, beykoz, stage="KARAR_DUZELTME", dogrulama_durumu="TURETILDI",
                                           source="HUKDOK_TESLIM_x")
        # 4) #2909: mahkeme boş, YEREL aşama satırının mahkemesi de boş.
        antalya = _kart(db, "AXA-0001-DR.O.COSKUNFIRAT-HUK", "2.1.00", file_type="Hukuk", esas_no="2025/252", court=None)
        _foy(db, antalya, "H-4922", _ham("H-4922", "2.1.00", "HUKUK", "2025/252", ""))
        stage_decisions.add_stage_decision(db, antalya, stage="YEREL", esas_no="2025/252", karar_no="2025/432",
                                           dogrulama_durumu="BELIRSIZ", source="HUKDOK_TESLIM_x")
        # 5) sigortalı: H-6677 yanlış ad, H-10298 sigortalı yok.
        mersin = _kart(db, "QUICK-0001-HUK", "2.2.00", file_type="Hukuk", esas_no="2021/171",
                       court="Mersin 1. Tüketici Mahkemesi")
        _foy(db, mersin, "H-6677", _ham("H-6677", "2.2.00", "HUKUK", "2021/171", "Mersin 1. Tüketici Mahkemesi"))
        db.add_all([models.CaseParty(case_id=mersin.id, name="DR.YUNUS ARAZ", role="Sigortalı", party_type="THIRD"),
                    models.CaseParty(case_id=mersin.id, name="Yusuf Araz Dr.", role="Diğer Davalı", party_type="THIRD")])
        sivas = _kart(db, "AK-0002-HUK", "2.3.00", file_type="Hukuk", esas_no="2017/430",
                      court="Sivas 3. Asliye Hukuk Mahkemesi")
        _foy(db, sivas, "H-10298", _ham("H-10298", "2.3.00", "HUKUK", "2017/430", "Sivas 3. Asliye Hukuk Mahkemesi"))
        db.add(models.CaseParty(case_id=sivas.id, name="Mustafa Kavurmaci Dr.", role="Diğer Davalı", party_type="THIRD"))
        # 6) dava konusu: kısa ad listede; bir kartta kullanıcı imzalı tarihçe.
        db.add_all([models.CaseSubject(code="TAZMINAT-TKU", name=KISA, active=True, sequence=0),
                    models.CaseSubject(code="RUCUEN-TKU", name="Rücuen Alacak (Tıbbi Kötü Uygulama)", active=True,
                                       sequence=1)])
        korunan = _kart(db, "DR.K.KORUNAN-0001-HUK", "2.4.00", file_type="Hukuk", esas_no="2020/1", court=BEYKOZ,
                        subject=UZUN)
        if kullanici_konu:
            db.add(models.CaseHistory(case_id=korunan.id, field_name="subject", old_value="Alacak", new_value=UZUN,
                                      changed_by="ilke", source=None))
        db.commit()
        return {"kalan": kalan.id, "sonen": sonen.id, "eski": eski.id, "hedef": hedef.id, "beykoz": beykoz.id,
                "antalya": antalya.id, "mersin": mersin.id, "sivas": sivas.id, "korunan": korunan.id}
    finally:
        db.close()


def test_kuru_kosu_hic_yazmaz(db_env):  # noqa: F811
    ids = _veri(db_env)
    sonuc = ec.kos(db_env, apply=False, kim="test")
    assert sonuc.sayim("cift", "YAPILDI") == 1 and sonuc.sayim("tasima", "YAPILDI") == 1
    db = db_env()
    assert db.get(models.Case, ids["sonen"]).deleted_at is None
    assert db.query(models.CaseFoy).filter_by(sistem_no="id-5126").one().case_id == ids["eski"]
    assert _sayim(db, models.CaseStageDecision, case_id=ids["beykoz"]) == 3
    assert db.get(models.Case, ids["antalya"]).court is None
    assert db.get(models.Case, ids["kalan"]).subject == UZUN
    db.close()


def test_alti_adim_uygulanir_ve_ikinci_kosu_sifir(db_env):  # noqa: F811
    ids = _veri(db_env)
    sonuc = ec.kos(db_env, apply=True, kim="test")
    assert sonuc.sayim("cift", "YAPILDI") == 1
    assert sonuc.sayim("tasima", "YAPILDI") == 1 and sonuc.sayim("kapatma", "YAPILDI") == 1
    assert sonuc.sayim("asama", "YAPILDI") == 2
    assert sonuc.sayim("mahkeme", "YAPILDI") == 2          # kart + YEREL aşama satırı
    assert sonuc.sayim("sigortali", "YAPILDI") == 2
    assert sonuc.sayim("konu", "YAPILDI") == 2             # kalan + korunan (sönen kart birleşmede kapandı)
    assert not [k for k in sonuc.kalemler if k.sonuc == "RET"]

    db = db_env()
    # 1) sönen kart kapandı, föyü kalanda, eski esas tarihçede değil ama föy taşındı
    assert db.get(models.Case, ids["sonen"]).deleted_at is not None
    assert db.query(models.CaseFoy).filter_by(sistem_no="id-841").one().case_id == ids["kalan"]
    # 2) id-5126 hedefte, eski kart kapalı
    assert db.query(models.CaseFoy).filter_by(sistem_no="id-5126").one().case_id == ids["hedef"]
    eski = db.get(models.Case, ids["eski"])
    assert eski.deleted_at is not None and eski.active is False and "föysüz" in eski.delete_reason
    # 3) Beykoz'da yalnız YEREL kaldı; kart fotoğrafı temiz
    kalanlar = db.query(models.CaseStageDecision).filter_by(case_id=ids["beykoz"]).all()
    assert [s.stage for s in kalanlar] == ["YEREL"]
    beykoz = db.get(models.Case, ids["beykoz"])
    assert beykoz.temyiz_karar_no is None
    # 4) mahkeme kartta ve aşama satırında
    antalya = db.get(models.Case, ids["antalya"])
    assert antalya.court == "Antalya 2. Tüketici Mahkemesi"
    yerel = stage_decisions.latest_stage_decision(db, antalya.id, "YEREL")
    assert yerel.mahkeme == "Antalya 2. Tüketici Mahkemesi"
    # 02.10 kusuru: yalnız mahkeme verilince update içeriğin geri kalanını boşaltıyordu.
    assert (yerel.esas_no, yerel.karar_no, yerel.dogrulama_durumu) == ("2025/252", "2025/432", "BELIRSIZ")
    # 5) sigortalı
    adlar = {p.name for p in db.query(models.CaseParty).filter_by(case_id=ids["mersin"], role="Sigortalı")}
    assert adlar == {"Yusuf Araz Dr."}
    assert _sayim(db, models.CaseParty, case_id=ids["sivas"], role="Sigortalı", name="Mustafa Kavurmacı Dr.") == 1
    # 6) dava konusu
    assert db.get(models.Case, ids["kalan"]).subject == KISA
    assert db.get(models.Case, ids["korunan"]).subject == KISA
    assert _sayim(db, models.CaseHistory, field_name="subject", changed_by=ec.DEGISTIREN) == 2
    db.close()

    ikinci = ec.kos(db_env, apply=True, kim="test")
    assert not [k for k in ikinci.kalemler if k.sonuc in ("YAPILDI", "RET")], \
        [(k.adim, k.hedef, k.sonuc, k.aciklama) for k in ikinci.kalemler if k.sonuc in ("YAPILDI", "RET")]


def test_belge_damgali_kunye_silinmez(db_env):  # noqa: F811
    ids = _veri(db_env, belge_damgasi=True)
    sonuc = ec.kos(db_env, apply=True, kim="test")
    assert sonuc.sayim("asama", "RET") == 1 and sonuc.sayim("asama", "YAPILDI") == 1
    db = db_env()
    assert sorted(s.stage for s in db.query(models.CaseStageDecision).filter_by(case_id=ids["beykoz"])) == \
        ["TEMYIZ", "YEREL"]
    db.close()


def test_kullanici_imzali_dava_konusu_korunur(db_env):  # noqa: F811
    ids = _veri(db_env, kullanici_konu=True)
    sonuc = ec.kos(db_env, apply=True, kim="test")
    assert sonuc.sayim("konu", "KORUNDU") == 1
    db = db_env()
    assert db.get(models.Case, ids["korunan"]).subject == UZUN
    db.close()


def test_kisa_ad_listede_yoksa_ret(db_env):  # noqa: F811
    _veri(db_env)
    db = db_env()
    db.query(models.CaseSubject).delete()
    db.commit()
    db.close()
    sonuc = ec.kos(db_env, apply=True, kim="test")
    assert sonuc.sayim("konu", "RET") == 2 and sonuc.sayim("konu", "YAPILDI") == 0


def test_mahkeme_farkliysa_ret(db_env):  # noqa: F811
    ids = _veri(db_env)
    db = db_env()
    db.get(models.Case, ids["antalya"]).court = "Antalya 1. Tüketici Mahkemesi"
    db.commit()
    db.close()
    sonuc = ec.kos(db_env, apply=True, kim="test")
    assert sonuc.sayim("mahkeme", "RET") == 1
