"""G084 — kanuni süre motoru testleri.

Her beklenti KANUN MADDESİNE referanslıdır: HMK m. 92 (süre hesabı), m. 93 (son günün
tatile rastlaması), m. 102/104 (adli tatil), m. 127 (cevap dilekçesi), m. 345 (istinaf),
m. 361 (temyiz). Testler sınır günlerini kapsar: adli tatilin ilk/son günü, 1 Eylül,
hafta sonuna denk gelen son gün, adli tatil + hafta sonu birleşimi ve takvimi
doğrulanmamış yıl.
"""

import ast
import logging
from datetime import date
from pathlib import Path

import pytest

from services.legal_deadlines import (
    CEVAP_DILEKCESI,
    ISTINAF_BASVURU,
    KURALLAR,
    TEMYIZ_BASVURU,
    Deadline,
    adli_tatil_icinde,
    deadline_for,
    deadline_for_kural,
    resmi_tatiller,
)

MODUL_YOLU = Path(__file__).resolve().parents[1] / "services" / "legal_deadlines.py"


# ---------------------------------------------------------------------------
# Saflık — modül DB'ye/ağa/config'e dokunmaz
# ---------------------------------------------------------------------------


def test_modul_models_import_etmez():
    """Saflık kilidi: kaynak dosyada models/DB/ağ import'u BULUNMAZ (G084 kabul kriteri)."""
    agac = ast.parse(MODUL_YOLU.read_text(encoding="utf-8"))
    yasak_kokler = {
        "models", "database", "sqlalchemy", "config", "requests",
        "httpx", "fastapi", "api", "managers",
    }
    bulunanlar = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for isim in dugum.names:
                bulunanlar.add(isim.name.split(".")[0])
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.module:
                bulunanlar.add(dugum.module.split(".")[0])
    assert not (bulunanlar & yasak_kokler), f"saf modül yasak import aldı: {bulunanlar & yasak_kokler}"


# ---------------------------------------------------------------------------
# Kural seti — her kural madde numarasıyla şerhli
# ---------------------------------------------------------------------------


def test_kural_seti_madde_numarasi_tasir():
    dayanaklar = {kural.ad: kural.dayanak for kural in KURALLAR}
    assert "345" in dayanaklar["İstinaf başvuru süresi"]
    assert "361" in dayanaklar["Temyiz başvuru süresi"]
    assert "127" in dayanaklar["Cevap dilekçesi süresi"]
    assert all(kural.hafta == 2 and kural.gun == 14 for kural in KURALLAR)


def test_yerel_karar_tebligi_istinaf_suresini_baslatir():
    """HMK m. 345/1: iki hafta, ilamın tebliğinden. 2026-03-02 Pzt → 2026-03-16 Pzt."""
    sonuc = deadline_for("YEREL", date(2026, 3, 2))
    assert isinstance(sonuc, Deadline)
    assert sonuc.son_gun == date(2026, 3, 16)
    assert sonuc.ham_son_gun == date(2026, 3, 16)
    assert sonuc.kural_adi == ISTINAF_BASVURU.ad
    assert "345" in sonuc.dayanak
    assert sonuc.kaydirmalar == ()
    assert sonuc.takvim_dogrulandi is True
    assert sonuc.teblig_tarihi == date(2026, 3, 2)


def test_istinaf_karar_tebligi_temyiz_suresini_baslatir():
    """HMK m. 361/1: iki hafta."""
    sonuc = deadline_for("ISTINAF", date(2026, 3, 2))
    assert sonuc is not None
    assert sonuc.kural_adi == TEMYIZ_BASVURU.ad
    assert "361" in sonuc.dayanak
    assert sonuc.son_gun == date(2026, 3, 16)


def test_cevap_dilekcesi_suresi():
    """HMK m. 127/1: dava dilekçesinin tebliğinden itibaren iki hafta."""
    asamayla = deadline_for("DAVA_DILEKCESI", date(2026, 3, 2))
    dogrudan = deadline_for_kural(CEVAP_DILEKCESI, date(2026, 3, 2))
    assert asamayla == dogrudan
    assert dogrudan is not None
    assert dogrudan.son_gun == date(2026, 3, 16)
    assert "127" in dogrudan.dayanak


def test_asama_etiketi_turkce_buyuk_harfle_de_taninir():
    assert deadline_for("İstinaf", date(2026, 3, 2)) == deadline_for("ISTINAF", date(2026, 3, 2))
    assert deadline_for(" yerel ", date(2026, 3, 2)) == deadline_for("YEREL", date(2026, 3, 2))


# ---------------------------------------------------------------------------
# Boş veri / süresi olmayan aşama → None
# ---------------------------------------------------------------------------


def test_teblig_tarihi_yoksa_sure_uydurulmaz():
    assert deadline_for("YEREL", None) is None
    assert deadline_for_kural(CEVAP_DILEKCESI, None) is None


@pytest.mark.parametrize("stage", ["TEMYIZ", "KARAR_DUZELTME", "BILINMEYEN", "", None])
def test_kanuni_suresi_olmayan_asama_none_doner(stage):
    """Temyiz/karar düzeltme tebliğinden bu motorda süre TÜRETİLMEZ."""
    assert deadline_for(stage, date(2026, 3, 2)) is None


# ---------------------------------------------------------------------------
# HMK m. 93 — son günün tatile/hafta sonuna rastlaması
# ---------------------------------------------------------------------------


def test_son_gun_resmi_tatile_rastlarsa_ilk_is_gunune_kayar():
    """2026-10-29 Cumhuriyet Bayramı (Per) → ilk iş günü 2026-10-30 (Cum)."""
    sonuc = deadline_for("YEREL", date(2026, 10, 15))
    assert sonuc is not None
    assert sonuc.ham_son_gun == date(2026, 10, 29)
    assert sonuc.son_gun == date(2026, 10, 30)
    assert len(sonuc.kaydirmalar) == 1
    assert "Cumhuriyet Bayramı" in sonuc.kaydirmalar[0]
    assert "93" in sonuc.kaydirmalar[0]


def test_dini_bayram_ve_hafta_sonu_ust_uste_kayar():
    """2026-03-20 Cum = Ramazan Bayramı 1. gün; 21-22 bayram + hafta sonu → 23 Mart Pzt."""
    sonuc = deadline_for("YEREL", date(2026, 3, 6))
    assert sonuc is not None
    assert sonuc.ham_son_gun == date(2026, 3, 20)
    assert sonuc.son_gun == date(2026, 3, 23)
    assert len(sonuc.kaydirmalar) == 3
    assert "Ramazan Bayramı" in sonuc.kaydirmalar[0]


# ---------------------------------------------------------------------------
# HMK m. 102 / 104 — adli tatil
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gun, beklenen",
    [
        (date(2027, 7, 19), False),  # tatilin bir gün öncesi
        (date(2027, 7, 20), True),   # tatilin İLK günü
        (date(2027, 8, 31), True),   # tatilin SON günü
        (date(2027, 9, 1), False),   # yeni adli yıl
    ],
)
def test_adli_tatil_sinirlari(gun, beklenen):
    assert adli_tatil_icinde(gun) is beklenen


def test_tatilin_ilk_gunune_denk_gelen_sure_uzar():
    """HMK m. 104: 2027-07-20 (tatilin ilk günü) → 2027-09-07 (Sal)."""
    sonuc = deadline_for("YEREL", date(2027, 7, 6))
    assert sonuc is not None
    assert sonuc.ham_son_gun == date(2027, 7, 20)
    assert sonuc.son_gun == date(2027, 9, 7)
    assert "adli tatil" in sonuc.kaydirmalar[0]
    assert "104" in sonuc.kaydirmalar[0]


def test_tatilin_son_gunune_denk_gelen_sure_uzar():
    """2027-08-31 (tatilin son günü) → 2027-09-07."""
    sonuc = deadline_for("YEREL", date(2027, 8, 17))
    assert sonuc is not None
    assert sonuc.ham_son_gun == date(2027, 8, 31)
    assert sonuc.son_gun == date(2027, 9, 7)


def test_tatilin_bir_gun_oncesi_uzamaz():
    """2027-07-19 Pzt — tatil başlamadı, kaydırma yok."""
    sonuc = deadline_for("YEREL", date(2027, 7, 5))
    assert sonuc is not None
    assert sonuc.son_gun == date(2027, 7, 19)
    assert sonuc.kaydirmalar == ()


def test_bir_eylul_uzamaz():
    """2027-09-01 Çar — adli tatil bitti, süre olduğu gibi kalır."""
    sonuc = deadline_for("YEREL", date(2027, 8, 18))
    assert sonuc is not None
    assert sonuc.son_gun == date(2027, 9, 1)
    assert sonuc.kaydirmalar == ()


def test_adli_tatil_ve_hafta_sonu_birlesimi():
    """2025-08-15 tatilde → 2025-09-07 Pazar → HMK m. 93 ile 2025-09-08 Pzt."""
    sonuc = deadline_for("YEREL", date(2025, 8, 1))
    assert sonuc is not None
    assert sonuc.ham_son_gun == date(2025, 8, 15)
    assert sonuc.son_gun == date(2025, 9, 8)
    assert len(sonuc.kaydirmalar) == 2
    assert "adli tatil" in sonuc.kaydirmalar[0]
    assert "hafta sonu (Pazar)" in sonuc.kaydirmalar[1]


def test_adli_tatile_tabi_olmayan_is_uzamaz():
    """HMK m. 103 istisnası: çağıran bilerek kapatırsa 104 uzaması işlemez."""
    sonuc = deadline_for("YEREL", date(2025, 8, 1), adli_tatile_tabi=False)
    assert sonuc is not None
    assert sonuc.son_gun == date(2025, 8, 15)
    assert sonuc.kaydirmalar == ()


# ---------------------------------------------------------------------------
# Takvimi doğrulanmamış yıl — tahmin yasağı
# ---------------------------------------------------------------------------


def test_takvimsiz_yil_kaydirmasiz_ve_isaretli_doner(caplog):
    """2030 takvimi YOK: 2030-09-07 Cumartesi olsa bile kaydırılmaz, WARNING loglanır."""
    with caplog.at_level(logging.WARNING, logger="services.legal_deadlines"):
        sonuc = deadline_for("YEREL", date(2030, 8, 1))
    assert sonuc is not None
    # Adli tatil uzaması HMK m. 102'ye bağlıdır, takvim tablosuna DEĞİL → uygulanır.
    assert sonuc.ham_son_gun == date(2030, 8, 15)
    assert sonuc.son_gun == date(2030, 9, 7)
    assert sonuc.takvim_dogrulandi is False
    assert not any("hafta sonu" in k for k in sonuc.kaydirmalar)
    assert any("takvim" in kayit.message.lower() for kayit in caplog.records)


def test_takvimsiz_yil_resmi_tatil_listesi_bos():
    assert resmi_tatiller(2030) == {}


def test_takvimli_yilin_tatilleri():
    tatiller = resmi_tatiller(2026)
    assert tatiller[date(2026, 4, 23)] == "Ulusal Egemenlik ve Çocuk Bayramı"
    assert tatiller[date(2026, 10, 29)] == "Cumhuriyet Bayramı"
    assert "Ramazan Bayramı" in tatiller[date(2026, 3, 20)]
    assert "Kurban Bayramı" in tatiller[date(2026, 5, 30)]
    # Arefe yarım gündür, TATİL SAYILMAZ (modül şerhi).
    assert date(2026, 5, 26) not in tatiller
