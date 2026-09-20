"""KolayOfis raporundan dosya son durumu tazeleme (`scripts/kolayofis_son_durum.py`):
başlıksız sütun, yazım düzeltmesi, yer tutucu/boş hücre, föy→kart çözümü, çelişki,
panel listesi düzeltmesi, kuru koşu ve idempotentlik.

**TEST VERİSİ KURALI:** ekibin gerçek raporu repoya girmez; sayfa openpyxl ile SENTETİK
üretilir (17.09 çıktısının başlık düzeniyle: son durum sütunu BAŞLIKSIZ).
"""
import openpyxl
import pytest

import models
from scripts import kolayofis_son_durum as ko
from tests.test_g064_aktarim_cekirdek import _kart
from tests.test_g179_ekip_cevabi_1209 import _foy, db_env  # noqa: F401

# 17.09 çıktısının başlıkları; 16. sütun (son durum) BAŞLIKSIZ gelir.
BASLIKLAR = ["Dosya - Föy Bilgileri", "SistemNo", "DosyaNo", "Klasör No", "Tarafımız", "Müvekkil",
             "Karşı Taraf", "Yerel Mahkeme", "Esas", "Dava Tarihi", "Ana Tür", "Durum", "Dava Konusu",
             "Dava Türü Alt Kırılımı", "Buro Özel Türü", None, "Yerel Mahkeme Karar Durumu", "Dosya İlgilisi"]


def _rapor_yaz(yol, satirlar, *, basliklar=None):
    """satirlar: (SistemNo, son durum) — son durum None ise hücre boş bırakılır."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(basliklar if basliklar is not None else BASLIKLAR)
    for sistem_no, son_durum in satirlar:
        satir = [None] * len(BASLIKLAR)
        satir[1] = sistem_no
        satir[15] = son_durum
        ws.append(satir)
    wb.save(yol)
    return yol


@pytest.fixture()
def rapor(tmp_path):
    def yaz(satirlar, **kw):
        return _rapor_yaz(tmp_path / "rapor.xlsx", satirlar, **kw)
    return yaz


def _liste(db, *adlar):
    for i, ad in enumerate(adlar):
        db.add(models.FileStatus(code=ko._karar_kodu(ad).replace("_", "-"), name=ad, active=True, sequence=i))
    db.flush()


# ─── Rapor okuma ─────────────────────────────────────────────────────────────

def test_baslıksiz_sutun_komsulardan_bulunur(rapor):
    yol = rapor([("H-1", "Bilirkişide")])
    assert ko.raporu_oku(yol) == [("H-1", "Bilirkişide")]


def test_baslikli_sutun_da_okunur(rapor):
    basliklar = list(BASLIKLAR)
    basliklar[15] = "Son Durum"
    yol = rapor([("H-1", "Temyizde")], basliklar=basliklar)
    assert ko.raporu_oku(yol) == [("H-1", "Temyizde")]


def test_sutun_bulunamazsa_hata(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["SistemNo", "Müvekkil"])
    wb.save(tmp_path / "eksik.xlsx")
    with pytest.raises(ValueError, match="son durum sütunu"):
        ko.raporu_oku(tmp_path / "eksik.xlsx")


@pytest.mark.parametrize("ham, beklenen", [
    ("Delliller Toplanıyor", "Deliller Toplanıyor"),      # ekibin başlık listesindeki yazım hatası
    ("Bekletici Mesele/ceza-hukuk Dosyası", "Bekletici Mesele/Ceza-Hukuk Dosyası"),
    ("Islah ", "Islah"),                                  # sondaki boşluk
    ("  Bilirkişide  ", "Bilirkişide"),
    ("Lütfen Seçiniz", None),                             # yer tutucu → yazılmaz
    ("", None),
    (None, None),
])
def test_deger_normalizasyonu(ham, beklenen):
    assert ko._degeri_normalize(ham) == beklenen


def test_yazilmayan_satirlar_rapordan_dusurulur(rapor):
    yol = rapor([("H-1", "Delliller Toplanıyor"), ("H-2", "Lütfen Seçiniz"), ("H-3", None), (None, "Tanık")])
    assert ko.raporu_oku(yol) == [("H-1", "Deliller Toplanıyor")]


# ─── Son durum tazeleme ──────────────────────────────────────────────────────

def test_kart_tazelenir_ve_tarihce_dusuer(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "Temyizde")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    db.commit()
    kart_id = kart.id
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde")]), apply=True, kim="test")
    assert sonuc.sayim("son_durum", "YAPILDI") == 1

    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Temyizde"
    tarihce = db.query(models.CaseHistory).filter_by(field_name="dosya_son_durumu").one()
    assert (tarihce.old_value, tarihce.new_value) == ("Bilirkişide", "Temyizde")
    assert tarihce.changed_by == ko.DEGISTIREN and "H-1" in tarihce.source
    db.close()


def test_bos_kutu_dolar(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Ön İnceleme")
    kart = _kart(db, "T1", "1.1")
    _foy(db, kart, "H-1")
    db.commit()
    kart_id = kart.id
    db.close()

    ko.kos(db_env, rapor=rapor([("H-1", "Ön İnceleme")]), apply=True)
    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Ön İnceleme"
    db.close()


def test_yer_tutucu_dolu_kutuyu_bosaltmaz(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    db.commit()
    kart_id = kart.id
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Lütfen Seçiniz"), ("H-1", None)]), apply=True)
    assert sonuc.sayim("son_durum", "YAPILDI") == 0

    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Bilirkişide"
    assert db.query(models.CaseHistory).filter_by(field_name="dosya_son_durumu").count() == 0
    db.close()


def test_celiskili_kart_atlanir(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "Temyizde", "Kesin Lehe")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    _foy(db, kart, "H-2")
    db.commit()
    kart_id = kart.id
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde"), ("H-2", "Kesin Lehe")]), apply=True)
    assert sonuc.sayim("son_durum", "CELISKI") == 1
    assert sonuc.sayim("son_durum", "YAPILDI") == 0
    kalem = next(k for k in sonuc.kalemler if k.sonuc == "CELISKI")
    assert "H-1" in kalem.aciklama and "H-2" in kalem.aciklama

    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Bilirkişide"
    db.close()


def test_ayni_degeri_soyleyen_coklu_foy_celiski_degil(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Temyizde")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    _foy(db, kart, "H-2")
    db.commit()
    kart_id = kart.id
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde"), ("H-2", "Temyizde")]), apply=True)
    assert sonuc.sayim("son_durum", "CELISKI") == 0

    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Temyizde"
    db.close()


def test_bizde_olmayan_foy_ret(db_env, rapor):  # noqa: F811
    sonuc = ko.kos(db_env, rapor=rapor([("H-YOK", "Temyizde")]), apply=True)
    assert sonuc.sayim("son_durum", "RET") == 1


def test_silinmis_kartin_foyu_ret(db_env, rapor):  # noqa: F811
    from sqlalchemy import func

    db = db_env()
    _liste(db, "Temyizde")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    kart.deleted_at = func.now()
    db.commit()
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde")]), apply=True)
    assert sonuc.sayim("son_durum", "RET") == 1
    assert sonuc.sayim("son_durum", "YAPILDI") == 0


# ─── Panel listesi ve kart yazım birliği ─────────────────────────────────────

def test_liste_duzeltmesi(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "İstinafta")
    db.commit()
    db.close()

    ko.kos(db_env, rapor=rapor([]), apply=True)
    db = db_env()
    adlar = {s.name for s in db.query(models.FileStatus).all()}
    assert "İstinafda" in adlar and "İstinafta" not in adlar
    assert {"Kapalı", "Soruşturma"} <= adlar
    kodlar = [s.code for s in db.query(models.FileStatus).all()]
    assert len(kodlar) == len(set(kodlar))          # kod tekilliği korunur
    db.close()


def test_liste_dogru_yazim_varsa_eski_satir_silinmez(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "İstinafta", "İstinafda")
    db.commit()
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([]), apply=True)
    assert sonuc.sayim("liste", "ATLANDI") >= 1
    db = db_env()
    assert {"İstinafta", "İstinafda"} <= {s.name for s in db.query(models.FileStatus).all()}
    db.close()


def test_kart_yazim_birligi(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bekletici Mesele/Ceza-Hukuk Dosyası")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bekletici Mesele/ceza-hukuk Dosyası")
    db.commit()
    kart_id = kart.id
    db.close()

    ko.kos(db_env, rapor=rapor([]), apply=True)
    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Bekletici Mesele/Ceza-Hukuk Dosyası"
    assert db.query(models.CaseHistory).filter_by(field_name="dosya_son_durumu").count() == 1
    db.close()


# ─── Kuru koşu ve idempotentlik ──────────────────────────────────────────────

def test_kuru_kosu_yazmaz(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "Temyizde")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    db.commit()
    kart_id = kart.id
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde")]), apply=False)
    assert sonuc.sayim("son_durum", "YAPILDI") == 1      # rapor yine basılır

    db = db_env()
    assert db.get(models.Case, kart_id).dosya_son_durumu == "Bilirkişide"
    assert db.query(models.CaseHistory).count() == 0
    assert {s.name for s in db.query(models.FileStatus).all()} == {"Bilirkişide", "Temyizde"}
    db.close()


def test_ikinci_kosu_degisiklik_uretmez(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "İstinafta")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    db.commit()
    db.close()

    yol = rapor([("H-1", "Delliller Toplanıyor")])
    ko.kos(db_env, rapor=yol, apply=True)
    ikinci = ko.kos(db_env, rapor=yol, apply=True)
    assert ikinci.sayim("son_durum", "YAPILDI") == 0
    assert ikinci.sayim("liste", "YAPILDI") == 0
    assert ikinci.sayim("kart_yazim", "YAPILDI") == 0

    db = db_env()
    assert db.query(models.CaseHistory).filter_by(field_name="dosya_son_durumu").count() == 1
    db.close()


def test_ozet_metni_celiskiyi_gosterir(db_env, rapor):  # noqa: F811
    db = db_env()
    _liste(db, "Bilirkişide", "Temyizde", "Kesin Lehe")
    kart = _kart(db, "T1", "1.1", dosya_son_durumu="Bilirkişide")
    _foy(db, kart, "H-1")
    _foy(db, kart, "H-2")
    db.commit()
    db.close()

    sonuc = ko.kos(db_env, rapor=rapor([("H-1", "Temyizde"), ("H-2", "Kesin Lehe")]), apply=False)
    metin = ko.ozet_metni(sonuc, apply=False)
    assert "KURU KOŞU" in metin and "CELISKI" in metin
