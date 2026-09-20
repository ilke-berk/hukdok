"""Ek-6 › 03 — korunan alanların kaynağını sınıflayan salt okunur rapor
(`scripts/korunan_alan_kaynaklari.py`): imza → sınıf, belge bağlantısı, esas tarihçesi.

**TEST VERİSİ KURALI:** ekin kendisi repoya girmez; sayfa openpyxl ile SENTETİK üretilir.
"""
import csv

import openpyxl
import pytest

import models
from scripts import korunan_alan_kaynaklari as kk
from tests.test_g064_aktarim_cekirdek import _kart
from tests.test_g179_ekip_cevabi_1209 import db_env  # noqa: F401


def _ek6_yaz(yol, satirlar):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = kk.EK6_KORUNAN_SAYFASI
    ws.append(["Föy", "Dosya No", "Kart", "Alan", "Sizin koruduğunuz değer", "Paketimizdeki değer",
               "Bizim kaydımızda bugün", "Aşama zincirimizde var mı", "Sorumuz"])
    for foy, dosya, kart, alan, korunan, paket in satirlar:
        ws.append([foy, dosya, kart, alan, korunan, paket, paket, "hayır", "soru"])
    wb.save(yol)
    return yol


@pytest.mark.parametrize("imza, sinif, belge", [
    ("belge:karar.pdf", "BELGE", "karar.pdf"),
    ("intake-enrich: dilekce.pdf +2", "BELGE", "dilekce.pdf +2"),
    ("auto-enrich", "BELGEDEN_TURETME", ""),
    ("auto-stage: KARAR", "BELGEDEN_TURETME", ""),
    ("update_case", "PANELDEN_ELLE", ""),
    ("panel", "PANELDEN_ELLE", ""),          # case_manager.PANEL_SOURCE (08.09'dan beri)
    ("HUKDOK_TESLIM_paket.xlsx", "PAKET", ""),
    (None, "KAYNAK_YOK", ""),
    ("", "KAYNAK_YOK", ""),
    ("ekip cevabı 12.09", "DIGER", ""),
])
def test_imza_siniflamasi(imza, sinif, belge):
    assert kk._sinifla(imza) == (sinif, belge)


def test_korunan_degeri_yazan_satir_secilir(db_env, tmp_path):  # noqa: F811
    """Alanda birden çok tarihçe satırı varsa korunan değeri YAZAN satır raporlanır."""
    db = db_env()
    try:
        kart = _kart(db, "S1.AK.0001.HUKUK.00000", "9.395.00", file_type="Hukuk", esas_no="2024/571")
        db.add(models.CaseEsasNumber(case_id=kart.id, esas_no="2016/753", stage="ONCEKI",
                                     is_current=False, source="HUKDOK_TESLIM_04-09.xlsx"))
        db.add(models.CaseEsasNumber(case_id=kart.id, esas_no="2024/571", stage="YEREL",
                                     is_current=True, source="belge:karar.pdf"))
        db.add(models.CaseDocument(case_id=kart.id, original_filename="karar.pdf",
                                   stored_filename="k.pdf", sharepoint_url="https://sp/karar.pdf"))
        db.add(models.CaseHistory(case_id=kart.id, field_name="esas_no", old_value="2015/1",
                                  new_value="2016/753", changed_by="aktarim",
                                  source="HUKDOK_TESLIM_04-09.xlsx"))
        db.add(models.CaseHistory(case_id=kart.id, field_name="esas_no", old_value="2016/753",
                                  new_value="2024/571", changed_by="sistem", source="belge:karar.pdf"))
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    ek6 = _ek6_yaz(tmp_path / "ek6.xlsx", [("H-4530", "9.395.00", kart_id, "Esas", "2024/571", "2016/753")])

    kalemler = kk.kos(db_env, ek6=ek6)

    assert len(kalemler) == 1
    kalem = kalemler[0]
    assert kalem.kolon == "esas_no" and kalem.kaynak_sinifi == "BELGE"
    assert kalem.belge == "karar.pdf" and kalem.sharepoint_url == "https://sp/karar.pdf"
    assert kalem.bugunku_deger == "2024/571" and kalem.degistiren == "sistem"
    assert "2016/753 (ONCEKI, kaynak=HUKDOK_TESLIM_04-09.xlsx)" in kalem.esas_tarihcesi
    assert "2024/571 (YEREL·güncel" in kalem.esas_tarihcesi


def test_mahkeme_tarihcesiz_ve_bilinmeyen_alan(db_env, tmp_path):  # noqa: F811
    db = db_env()
    try:
        kart = _kart(db, "S1.AK.0002.HUKUK.00000", "1.1", file_type="Hukuk",
                     court="Bakırköy 5. Tüketici Mahkemesi")
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    ek6 = _ek6_yaz(tmp_path / "ek6.xlsx", [
        ("H-15497", "6.5111.00", kart_id, "Yerel Mahkeme", "Bakırköy 5. Tüketici Mahkemesi",
         "Bakırköy 13. Tüketici Mahkemesi"),
        ("H-9", "1.1", kart_id, "Dosya Son Durumu", "Derdest", "İstinafda"),
        ("H-8", "1.1", 999999, "Esas", "2026/1", "2020/1"),
    ])

    kalemler = kk.kos(db_env, ek6=ek6)

    assert [k.kaynak_sinifi for k in kalemler] == ["TARIHCE_YOK", "ALAN_TANINMADI", "KART_YOK"]
    assert kalemler[0].bugunku_deger == "Bakırköy 5. Tüketici Mahkemesi"

    yol = tmp_path / "rapor" / "kaynak.csv"
    kk.csv_yaz(kalemler, yol)
    with yol.open(encoding="utf-8-sig") as f:
        satirlar = list(csv.reader(f, delimiter=";"))
    assert satirlar[0] == list(kk.BASLIKLAR) and len(satirlar) == 4
    assert kk.ozet_metni(kalemler).count("TARIHCE_YOK") == 2      # sayım + kalem satırı
