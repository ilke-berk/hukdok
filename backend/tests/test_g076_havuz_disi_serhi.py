"""G076 — "havuz dışı durum: None": karar durumu BOŞ satıra yanlış şerh.

`_asama_satirlarini_yaz` iki deneme yapıyor: önce kaynağın karar durumu,
kapalı havuz (G060) reddederse durumsuz + "havuz dışı durum: X" şerhi. Ama
fallback'i `deneme is None` ile ayırt ediyordu — oysa kaynak durumu ZATEN
boşsa ilk deneme de `None`dur ve o okuma açıklamaya Python'ın `None`'unu
basıyordu.

Kusurun boyu ölçüldü (2026-08-19 tam koşusu, lokal DB): **833 satırda
`aciklama = "havuz dışı durum: None"`** — YEREL 297, TEMYİZ 273, İSTİNAF 224,
K.Düzeltme 47. Gerçek havuz dışı değer taşıyan satır yalnız 8 taneydi
("havuz dışı durum: Lexis Rapor Gönderildi"). G074'ten sonra bu metin
kullanıcıya aşama tarihçesinde AYNEN görünüyordu.

Fixture'lar G064'ten gelir (pysqlite SAVEPOINT reçetesi tek kaynakta durmalı).
"""
import pytest
from pathlib import Path

import models
from scripts.hukdok_aktarim import CIKIS_TAMAM, aktarimi_kos

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN; ruff fixture parametresini
# yeniden tanımlama sanar (F811), kullanım yerinde susturulur.
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    BASLIKLAR,
    _satir,
    db_env,
    uc_kart,
)

SERH = "havuz dışı durum"


def _asama_paketi(yol, foy_satirlari, asama_satirlari):
    """Sheet + Karar_Asamalari; aşama sayfasında Açıklama sütunu da var."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Föyler"
    ws.append(BASLIKLAR)
    for satir in foy_satirlari:
        ws.append([satir.get(b) for b in BASLIKLAR])
    ah = ["SistemNo", "AsamaNo", "Aşama", "Mahkeme", "Esas No", "Karar No",
          "Karar Tarihi", "Karar Durumu", "Tebliğ Tarihi", "Güven", "Açıklama"]
    wa = wb.create_sheet("Karar_Asamalari")
    wa.append(ah)
    for satir in asama_satirlari:
        wa.append([satir.get(b) for b in ah])
    wb.save(yol)
    wb.close()
    return Path(yol)


@pytest.fixture()
def havuzlu_kartlar(uc_kart):  # noqa: F811
    """G060 kapalı havuzları seed'li zemin — tarihçe yolu boş listede hiçbir
    değeri geçirmez, o yüzden gerçek liste şart."""
    db = uc_kart()
    try:
        db.add(models.LocalDecision(code="RED-ESAS", name="Red/Esastan"))
        db.commit()
    finally:
        db.close()
    return uc_kart


def _satirlar(fabrika):
    """(stage, sira_no) → satır. TEK kartlı testler için; çok kartlıda
    `_aciklamalar` kullanılır (anahtar çakışır)."""
    db = fabrika()
    try:
        return {
            (d.stage, d.sira_no): d
            for d in db.query(models.CaseStageDecision).all()
        }
    finally:
        db.close()


def _aciklamalar(fabrika):
    db = fabrika()
    try:
        return sorted(
            (d.aciklama or "") for d in db.query(models.CaseStageDecision).all()
        )
    finally:
        db.close()


def test_karar_durumu_bos_satira_serh_yazilmaz(havuzlu_kartlar, tmp_path):
    """Kusurun kendisi: durum boşken şerh HİÇ doğmamalı (eski kod
    "havuz dışı durum: None" yazıyordu — bu test eski kodda KIRMIZI)."""
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Esas No": "2023/1", "Güven": "KESİN"}],           # Karar Durumu YOK
    )

    sonuc = aktarimi_kos(havuzlu_kartlar, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.asama_eklenen == 1
    # Havuz dışı bir DEĞER yok — sayaç da artmamalı
    assert sonuc.havuz_disi_durum == 0

    satir = _satirlar(havuzlu_kartlar)[("YEREL", 1)]
    assert satir.karar_durumu is None
    assert satir.aciklama is None, f"boş duruma şerh yazıldı: {satir.aciklama!r}"


def test_bos_durumda_kaynagin_aciklamasi_aynen_korunur(havuzlu_kartlar, tmp_path):
    """Şerh eklenmediği gibi kaynağın kendi açıklaması da kirletilmez."""
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Açıklama": "dosya işlemde", "Güven": "KESİN"}],
    )

    aktarimi_kos(havuzlu_kartlar, girdi=paket, rapor_dizini=tmp_path / "rapor")

    satir = _satirlar(havuzlu_kartlar)[("YEREL", 1)]
    assert satir.aciklama == "dosya işlemde"
    assert SERH not in satir.aciklama


def test_gercek_havuz_disi_deger_hala_serhleniyor(havuzlu_kartlar, tmp_path):
    """Gerileme nöbetçisi: düzeltme, GERÇEK havuz dışı değerin kaydını
    kaybetmemeli — 8 satır bu şerh sayesinde okunabiliyor."""
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Karar Durumu": "Lexis Rapor Gönderildi", "Güven": "KESİN"}],
    )

    sonuc = aktarimi_kos(havuzlu_kartlar, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.havuz_disi_durum == 1
    satir = _satirlar(havuzlu_kartlar)[("YEREL", 1)]
    assert satir.karar_durumu is None                     # havuz kabul etmedi
    assert satir.aciklama == "havuz dışı durum: Lexis Rapor Gönderildi"
    assert "None" not in satir.aciklama


def test_havuz_disi_serhi_kaynagin_aciklamasiyla_birlesir(havuzlu_kartlar, tmp_path):
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Karar Durumu": "Uydurma Sonuç", "Açıklama": "dosya işlemde", "Güven": "KESİN"}],
    )

    aktarimi_kos(havuzlu_kartlar, girdi=paket, rapor_dizini=tmp_path / "rapor")

    satir = _satirlar(havuzlu_kartlar)[("YEREL", 1)]
    assert satir.aciklama == "dosya işlemde · havuz dışı durum: Uydurma Sonuç"


def test_karisik_pakette_hicbir_satirda_none_serhi_yok(havuzlu_kartlar, tmp_path):
    """Uçtan uca: havuzdaki değer + havuz dışı değer + boş durum bir arada.
    Kabul kriteri — koşunun ÇIKTISINDA "None" şerhi hiç geçmiyor."""
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-2"), _satir("H-3", "D-3")],
        [
            {"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
             "Karar Durumu": "Red/Esastan", "Güven": "KESİN"},
            {"SistemNo": "H-2", "AsamaNo": 1, "Aşama": "Yerel",
             "Karar Durumu": "Lexis Rapor Gönderildi", "Güven": "KESİN"},
            {"SistemNo": "H-3", "AsamaNo": 1, "Aşama": "Yerel", "Güven": "BELİRSİZ"},
        ],
    )

    sonuc = aktarimi_kos(havuzlu_kartlar, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.asama_eklenen == 3 and sonuc.havuz_disi_durum == 1
    aciklamalar = _aciklamalar(havuzlu_kartlar)
    assert f"{SERH}: None" not in " | ".join(aciklamalar)
    assert aciklamalar == ["", "", "havuz dışı durum: Lexis Rapor Gönderildi"]
