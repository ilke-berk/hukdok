"""Ekip cevabı 22.09 › A2 kart ayırma (`scripts/ekip_cevabi_2209.py`): föy çiftiyle kart
tanıma, ayırma + taraf temizliği, belge/föy bağlı tarafın korunması, kuru koşu, idempotency.

**TEST VERİSİ KURALI:** ham satırlar elde yazılmış sözlükler (ekibin başlıklarıyla).
"""
import models
from scripts import ekip_cevabi_2209 as ec
from tests.test_g064_aktarim_cekirdek import _kart
from tests.test_g180_birlesik_kart_ayir import _foy, _ham, db_env  # noqa: F401

AYIRMA = (("H-10589", "ARB-16909", "test kanıtı"),)


def _quick_karti(db_env, *, belge_bagli=False):  # noqa: F811
    """Ek-1 A2 #4370 deseni: Hukuk kartı altında Quick Sigorta davası + Dr. Cemal Ünlü arabuluculuğu."""
    db = db_env()
    try:
        k = _kart(db, "S4.QUICK......0032.HUKUK.00000", "2.011.00", file_type="Hukuk", esas_no="2020/269",
                  court="İstanbul 3. Tüketici Mahkemesi")
        quick = models.CaseParty(case_id=k.id, name="Quick Sigorta A.Ş.", role="Müdahil", party_type="CLIENT")
        cemal = models.CaseParty(case_id=k.id, name="Cemal Ünlü Dr", role="Aleyhine Başvurulan", party_type="CLIENT")
        atici = models.CaseParty(case_id=k.id, name="Mehmet Atıcı", role="Karşı Taraf", party_type="COUNTER")
        db.add_all([quick, cemal, atici, models.CaseParty(case_id=k.id, name="Özge Tanlı", role="Karşı Taraf",
                                                           party_type="COUNTER")])
        db.flush()
        db.add(models.CaseDocument(case_id=k.id, original_filename="d.pdf", stored_filename="d.pdf",
                                   case_party_id=cemal.id if belge_bagli else None))
        _foy(db, k, "H-10589", _ham("H-10589", "2.011.00", "HUKUK", "2020/269", "İstanbul 3. Tüketici Mahkemesi",
                                     muvekkil="Quick Sigorta A.Ş.", karsi="Özge Tanlı"))
        _foy(db, k, "ARB-16909", _ham("ARB-16909", "1990.001", "ARABULUCULUK", "2026/720",
                                       "Kayseri Arabuluculuk Bürosu", muvekkil="Cemal Ünlü Dr",
                                       karsi="Mehmet Atıcı;Ruziye Atıcı", tip="Doktor"))
        db.commit()
        return k.id
    finally:
        db.close()


def test_ayirma_ve_taraf_temizligi(db_env):  # noqa: F811
    kart_id = _quick_karti(db_env)
    db = db_env()
    sonuc = ec.Sonuc()
    ec.kartlari_ayir(db, AYIRMA, kim="test", sonuc=sonuc)
    db.commit()
    assert sonuc.sayim("ayirma", "YAPILDI") == 1

    kalan = db.get(models.Case, kart_id)
    foyler = {f.sistem_no: f for f in db.query(models.CaseFoy).all()}
    assert foyler["H-10589"].case_id == kart_id
    yeni = db.get(models.Case, foyler["ARB-16909"].case_id)
    assert yeni.id != kart_id and yeni.file_type == "Arabuluculuk"
    # Kalan kartta taşınan föye özgü taraflar silindi, ortak/kendi tarafları duruyor.
    kalan_adlar = {p.name for p in db.query(models.CaseParty).filter_by(case_id=kart_id)}
    assert kalan_adlar == {"Quick Sigorta A.Ş.", "Özge Tanlı"}
    yeni_adlar = {p.name for p in db.query(models.CaseParty).filter_by(case_id=yeni.id)}
    assert {"Cemal Ünlü Dr", "Mehmet Atıcı", "Ruziye Atıcı"} <= yeni_adlar
    assert sonuc.sayim("taraf", "YAPILDI") == 2
    # Belge kalan kartta; tarihçe iki alanda.
    assert db.query(models.CaseDocument).filter_by(case_id=kart_id).count() == 1
    alanlar = {h.field_name for h in db.query(models.CaseHistory).filter_by(case_id=kart_id)}
    assert {"kart_ayirma", "taraf"} <= alanlar
    assert all(h.changed_by == ec.DEGISTIREN
               for h in db.query(models.CaseHistory).filter_by(field_name="taraf", case_id=kart_id))
    assert db.query(models.CaseRelation).filter_by(source_case_id=kart_id, target_case_id=yeni.id,
                                                    relation_type="AYRISTIRILAN").count() == 1
    assert kalan.deleted_at is None
    db.close()


def test_belge_bagli_taraf_silinmez(db_env):  # noqa: F811
    kart_id = _quick_karti(db_env, belge_bagli=True)
    db = db_env()
    sonuc = ec.Sonuc()
    ec.kartlari_ayir(db, AYIRMA, kim="test", sonuc=sonuc)
    db.commit()
    kalan_adlar = {p.name for p in db.query(models.CaseParty).filter_by(case_id=kart_id)}
    assert "Cemal Ünlü Dr" in kalan_adlar and "Mehmet Atıcı" not in kalan_adlar
    atlanan = [k for k in sonuc.kalemler if k.adim == "taraf" and k.sonuc == "ATLANDI"]
    assert len(atlanan) == 1 and "1 belge" in atlanan[0].aciklama
    db.close()


def test_foy_cifti_ayni_kartta_degilse_ret(db_env):  # noqa: F811
    db = db_env()
    a = _kart(db, "A", "1.1", file_type="Hukuk")
    b = _kart(db, "B", "1.2", file_type="Hukuk")
    _foy(db, a, "H-10589", _ham("H-10589", "1.1", "HUKUK", "2020/269", "M"))
    _foy(db, b, "ARB-16909", _ham("ARB-16909", "1.2", "ARABULUCULUK", "2026/720", "K"))
    db.commit()
    sonuc = ec.Sonuc()
    ec.kartlari_ayir(db, AYIRMA + (("H-YOK", "ARB-16909", "x"),), kim="test", sonuc=sonuc)
    assert sonuc.sayim("ayirma", "RET") == 2
    assert "zaten ayrı kartlarda" in sonuc.kalemler[0].aciklama
    assert "föy bizde yok" in sonuc.kalemler[1].aciklama
    db.close()


def test_kuru_kosu_yazmaz_ve_ikinci_kosu_ret(db_env, monkeypatch):  # noqa: F811
    kart_id = _quick_karti(db_env)
    monkeypatch.setattr(ec, "AYIRMALAR", AYIRMA)

    ec.kos(db_env, apply=False)
    db = db_env()
    assert db.query(models.Case).count() == 1
    assert db.query(models.CaseParty).filter_by(case_id=kart_id).count() == 4
    assert db.query(models.CaseHistory).count() == 0
    db.close()

    birinci = ec.kos(db_env, apply=True, kim="test")
    assert birinci.sayim("ayirma", "YAPILDI") == 1
    ikinci = ec.kos(db_env, apply=True, kim="test")
    assert ikinci.sayim("ayirma", "RET") == 1 and ikinci.sayim("ayirma", "YAPILDI") == 0
    db = db_env()
    assert db.query(models.Case).count() == 2
    db.close()


def test_ozet_metni(db_env, monkeypatch):  # noqa: F811
    _quick_karti(db_env)
    monkeypatch.setattr(ec, "AYIRMALAR", AYIRMA)
    metin = ec.ozet_metni(ec.kos(db_env, apply=False), apply=False)
    assert "KURU KOŞU" in metin and "[ayirma]" in metin and "[taraf]" in metin
