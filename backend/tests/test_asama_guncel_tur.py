"""Aşama fotoğrafı güncel turu gösterir (veri ekibi 02.10 kontrolü, 1_KARAR_KUNYESI).

Kusur: fotoğraf aşamanın en yüksek `sira_no`lu satırından alınır, `sira_no` ise
paketin `AsamaNo` sırasıydı. Ekip belge okumasıyla bulduğu ESKİ turları sona
ekliyor (H-13205: A3 güncel istinaf 2024/3025, A6 eski istinaf 2018/2209) →
45 kartta kart eski turu gösterdi. Düzeltme:

  * paket satırları "Güncel?" (EVET sonda) → karar tarihi (grup tam tarihliyse)
    → AsamaNo ile sıralanır (`_asama_kronolojisi`);
  * önce birebir aynı satırlar tüketilir (eski tur güncel satırı ezmez);
  * aşamanın `sira_no`ları paket sırasına çekilir; paketin anlatmadığı mevcut
    satırlar başta kalır (silinmez); belgeli satırlı aşamaya dokunulmaz;
  * aynı paketle ikinci koşu 0.
"""
from datetime import date

import pytest

import models
from managers import stage_decisions
from scripts.hukdok_aktarim import HamSatir, _asama_kronolojisi, aktarimi_kos

# Fixture'lar G064/G150'den — tek kaynak (ruff F811 kullanım yerinde susturulur).
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    _asama_paketi_yaz,
    _satir,
    db_env,
    uc_kart,
)
from tests.test_g150_asama_kurali import _elle_satir, _kart, _satirlar, _tarihce, zemin  # noqa: F401


def _istinaf(no, esas, karar, tarih, guncel, durum="Kaldırma"):
    return {"SistemNo": "H-1", "AsamaNo": no, "Aşama": "İstinaf", "Mahkeme": "İzmir BAM 4. HD",
            "Esas No": esas, "Karar No": karar, "Karar Tarihi": tarih, "Karar Durumu": durum,
            "Güven": "KESİN", "Güncel?": guncel}


def _ham(no, tarih=None, guncel=None):
    return HamSatir(satir_no=no, degerler={"asama_no": no, "karar_tarihi": tarih, "guncel": guncel})


# ─── Sıralama anahtarı ───────────────────────────────────────────────────────

def test_kronoloji_guncel_sona_tarihsiz_grupta_asamano():
    """H-13205 istinaf: A3 EVET (2025), A6 HAYIR tarihsiz → A6, A3."""
    sirali = _asama_kronolojisi([_ham(3, "18.03.2025", "EVET"), _ham(6, None, "HAYIR")])
    assert [s.satir_no for s in sirali] == [6, 3]


def test_kronoloji_iki_evet_tarihle_ayrilir():
    """id-8649 temyiz: iki EVET; AsamaNo 4 olan 2018 tarihli → 2023 sona."""
    sirali = _asama_kronolojisi([_ham(3, "18.05.2023", "EVET"), _ham(4, "07.05.2018", "EVET")])
    assert [s.satir_no for s in sirali] == [4, 3]


def test_kronoloji_evet_tarihten_once_gelir():
    """H-13205 yerel: EVET olan 2018 asıl dava, HAYIR olan 2024 kaldırılan kararın SONRASINDA."""
    sirali = _asama_kronolojisi([_ham(2, "21.10.2024", "HAYIR"), _ham(5, "10.05.2018", "EVET")])
    assert [s.satir_no for s in sirali] == [2, 5]


def test_kronoloji_sutunsuz_eski_paket_asamano_sirasi():
    """"Güncel?" yok + tarihsiz satır var → AsamaNo sırası (eski davranış)."""
    sirali = _asama_kronolojisi([_ham(2, None), _ham(1, "01.01.2020")])
    assert [s.satir_no for s in sirali] == [1, 2]


# ─── Uçtan uca ───────────────────────────────────────────────────────────────

def test_617_deseni_eski_tur_sonra_gelince_fotograf_guncel_tur(zemin, tmp_path):  # noqa: F811
    """15.09 paketi güncel turu (2024/3025) yazmıştı; 01.10 paketi eski turu
    (2018/2209) AsamaNo 6 ile getirdi. Kart GÜNCEL turu göstermeli, güncel
    satır ezilmemeli (tarihçede güncelleme yok)."""
    ilk = _asama_paketi_yaz(tmp_path / "ilk.xlsx", [_satir("H-1", "D-1")],
                            [_istinaf(3, "2024/3025", "2025/590", "18.03.2025", "EVET")])
    aktarimi_kos(zemin, girdi=ilk, rapor_dizini=tmp_path / "r1")

    paket = _asama_paketi_yaz(tmp_path / "ikinci.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(3, "2024/3025", "2025/590", "18.03.2025", "EVET"),
        _istinaf(6, "2018/2209", "2020/1783", None, "HAYIR"),
    ])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r2")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen) == (1, 0)
    assert sonuc.asama_sira_duzeltilen == 1
    satirlar = _satirlar(zemin)
    assert satirlar[("ISTINAF", 1)].esas_no == "2018/2209"
    assert satirlar[("ISTINAF", 2)].esas_no == "2024/3025"
    kart = _kart(zemin)
    assert (kart.istinaf_esas_no, kart.istinaf_karar_no) == ("2024/3025", "2025/590")
    tarihce = _tarihce(zemin)
    assert [t[0] for t in tarihce] == ["case_stage_decisions.ISTINAF.sira"]
    assert tarihce[0][1:3] == ("2024/3025/2025/590 · 2018/2209/2020/1783",
                               "2018/2209/2020/1783 · 2024/3025/2025/590")

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r3")
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen,
            ikinci.asama_ikinci_tur, ikinci.asama_sira_duzeltilen) == (0, 0, 0, 0)


def test_mevcut_yanlis_sira_ayni_paketle_duzelir(zemin, tmp_path):  # noqa: F811
    """Prod'daki hâl: iki satır da var ama eski tur yüksek sira_no'da (#13247).
    Aynı paketin yeniden koşusu içerik yazmaz, yalnız sırayı çevirir."""
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2026/214",
                karar_no="2026/582", karar_tarihi=date(2026, 2, 3), karar_durumu="Kaldırma",
                damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2021/4915",
                karar_no="2021/4950", karar_tarihi=date(2021, 12, 24), karar_durumu="Başvuru Ret",
                damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    assert _kart(zemin).istinaf_esas_no == "2021/4915"          # kusurlu fotoğraf

    paket = _asama_paketi_yaz(tmp_path / "p.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(2, "2026/214", "2026/582", "03.02.2026", "EVET"),
        _istinaf(4, "2021/4915", "2021/4950", "24.12.2021", "HAYIR", durum="Başvuru Ret"),
    ])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen, sonuc.asama_ikinci_tur) == (0, 0, 0)
    assert sonuc.asama_sira_duzeltilen == 1
    satirlar = _satirlar(zemin)
    assert satirlar[("ISTINAF", 1)].esas_no == "2021/4915"
    assert satirlar[("ISTINAF", 2)].esas_no == "2026/214"
    assert _kart(zemin).istinaf_esas_no == "2026/214"


def test_paketin_anlatmadigi_satir_basta_kalir_silinmez(zemin, tmp_path):  # noqa: F811
    """#2152 deseni (prod hâli): 15.09'dan kalma karışık satır (#1) + 01.10'un
    üç turu AsamaNo sırasıyla (#2-#4). Paketin artık anlatmadığı #1 silinmez,
    başta kalır; üç tur kronolojiye dizilir, fotoğraf EVET olan Onama."""
    for esas, karar, tarih in (("2025/694", None, date(2017, 4, 20)),
                               ("2019/9237", "2023/4443", date(2023, 9, 13)),
                               ("2025/694", "2026/2361", date(2026, 4, 21)),
                               ("2015/921", "2017/1897", date(2017, 4, 20))):
        _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no=esas,
                    karar_no=karar, karar_tarihi=tarih, karar_durumu="Kaldırma",
                    damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    assert _kart(zemin).istinaf_esas_no == "2015/921"           # kusurlu fotoğraf
    paket = _asama_paketi_yaz(tmp_path / "p.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(2, "2019/9237", "2023/4443", "13.09.2023", "HAYIR"),
        _istinaf(4, "2025/694", "2026/2361", "21.04.2026", "EVET"),
        _istinaf(5, "2015/921", "2017/1897", "20.04.2017", "HAYIR"),
    ])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen, sonuc.asama_sira_duzeltilen) == (0, 0, 1)
    satirlar = _satirlar(zemin)
    assert [(satirlar[("ISTINAF", i)].esas_no, satirlar[("ISTINAF", i)].karar_no)
            for i in range(1, 5)] == [("2025/694", None), ("2015/921", "2017/1897"),
                                      ("2019/9237", "2023/4443"), ("2025/694", "2026/2361")]
    assert (_kart(zemin).istinaf_esas_no, _kart(zemin).istinaf_karar_no) == ("2025/694", "2026/2361")


def test_ayni_esasli_satir_hedeflenir_konumdaki_tur_ezilmez(zemin, tmp_path):  # noqa: F811
    """#13363 deseni: bizde güncel tur (2025/27) tek satır, açıklaması farklı →
    birebir değil. Paketin ilk (eski) turu 2017/2141 konum 1'deki 2025/27'yi
    EZMEMELİ: 2025/27 aynı esaslı satırı günceller, 2017/2141 eklenir."""
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2025/27",
                karar_no="2025/1114", karar_tarihi=date(2025, 5, 29), karar_durumu="Başvuru Ret",
                aciklama="eski not", damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    paket = _asama_paketi_yaz(tmp_path / "p.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(2, "2025/27", "2025/1114", "29.05.2025", "EVET", durum="Başvuru Ret"),
        _istinaf(4, "2017/2141", "2017/2242", "20.12.2017", "HAYIR"),
    ])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen, sonuc.asama_ikinci_tur) == (1, 1, 0)
    satirlar = _satirlar(zemin)
    assert [satirlar[("ISTINAF", i)].esas_no for i in (1, 2)] == ["2017/2141", "2025/27"]
    guncellenen = [t for t in _tarihce(zemin) if not t[0].endswith(".sira")]
    assert {t[0].rsplit(".", 1)[1] for t in guncellenen} == {"aciklama"}   # esas ezilmedi
    assert _kart(zemin).istinaf_esas_no == "2025/27"


def test_belgeli_satirli_asamada_sira_degismez(zemin, tmp_path):  # noqa: F811
    """Belgeli (BELGE) satır varsa sıra düzeltmesi yapılmaz (G150 muhafazakârlığı)."""
    _elle_satir(zemin, stage="ISTINAF", damga="BELGE", mahkeme="İzmir BAM 4. HD",
                esas_no="2026/214", karar_no="2026/582", karar_tarihi=date(2026, 2, 3),
                karar_durumu="Kaldırma")
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2021/4915",
                karar_no="2021/4950", karar_tarihi=date(2021, 12, 24), karar_durumu="Başvuru Ret")
    paket = _asama_paketi_yaz(tmp_path / "p.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(2, "2026/214", "2026/582", "03.02.2026", "EVET"),
        _istinaf(4, "2021/4915", "2021/4950", "24.12.2021", "HAYIR", durum="Başvuru Ret"),
    ])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "r")

    assert sonuc.asama_sira_duzeltilen == 0
    assert _satirlar(zemin)[("ISTINAF", 1)].esas_no == "2026/214"


# ─── Yönetici ────────────────────────────────────────────────────────────────

def test_reorder_eksik_id_reddeder_ve_ayni_sira_yazmaz(zemin):  # noqa: F811
    a = _elle_satir(zemin, stage="TEMYIZ", esas_no="2020/1")
    b = _elle_satir(zemin, stage="TEMYIZ", esas_no="2021/2")
    db = zemin()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        with pytest.raises(ValueError):
            stage_decisions.reorder_stage_decisions(db, kart, "TEMYIZ", [a])
        assert stage_decisions.reorder_stage_decisions(db, kart, "TEMYIZ", [a, b]) is False
        assert stage_decisions.reorder_stage_decisions(db, kart, "TEMYIZ", [b, a]) is True
        db.commit()
        assert kart.temyiz_esas_no == "2020/1"
    finally:
        db.close()


# ─── Yalnız aşama katmanı script'i ───────────────────────────────────────────

def test_asama_sirasi_duzelt_kart_alanina_yazmaz_kuru_kosu_geri_alir(zemin, tmp_path):  # noqa: F811
    """`scripts/asama_sirasi_duzelt`: kuru koşu hiçbir şey bırakmaz; `apply`
    yalnız aşama satırlarını yazar (kart alanı/föy tarihçesi yok), ikinci koşu 0."""
    from scripts import asama_sirasi_duzelt

    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2026/214",
                karar_no="2026/582", karar_tarihi=date(2026, 2, 3), karar_durumu="Kaldırma",
                damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İzmir BAM 4. HD", esas_no="2021/4915",
                karar_no="2021/4950", karar_tarihi=date(2021, 12, 24), karar_durumu="Başvuru Ret",
                damga="TURETILDI", source="HUKDOK_TESLIM_eski.xlsx")
    paket = _asama_paketi_yaz(tmp_path / "p.xlsx", [_satir("H-1", "D-1")], [
        _istinaf(2, "2026/214", "2026/582", "03.02.2026", "EVET"),
        _istinaf(4, "2021/4915", "2021/4950", "24.12.2021", "HAYIR", durum="Başvuru Ret"),
    ])
    db = zemin()
    try:
        db.add(models.CaseFoy(case_id=db.query(models.Case).filter_by(klasor_no_2="D-1").one().id,
                              sistem_no="H-1"))
        db.commit()
    finally:
        db.close()

    kuru = asama_sirasi_duzelt.kos(zemin, girdi=paket, apply=False)
    assert kuru.asama_sira_duzeltilen == 1
    assert _kart(zemin).istinaf_esas_no == "2021/4915"           # geri alındı

    sonuc = asama_sirasi_duzelt.kos(zemin, girdi=paket, apply=True)
    assert sonuc.asama_sira_duzeltilen == 1
    kart = _kart(zemin)
    assert kart.istinaf_esas_no == "2026/214"
    # Tek tarihçe satırı sıra kaydıdır — föy/kart alanı yazılmadı.
    assert [t[0] for t in _tarihce(zemin, onek="")] == ["case_stage_decisions.ISTINAF.sira"]

    ikinci = asama_sirasi_duzelt.kos(zemin, girdi=paket, apply=True)
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen, ikinci.asama_sira_duzeltilen) == (0, 0, 0)
