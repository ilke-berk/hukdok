"""court_extractor testleri — regex denetim raporu Faz 2.2.

DynamicConfig stub'lanır (DB'ye bağımlılık yok) → _FALLBACK_* listeleri
deterministik olarak kullanılır. Kritik regresyon korumaları:
- turkish_upper düzeltmesi: karışık harfli metin ("Mahkemesi") eşleşmeli;
  str.upper() "MAHKEMESI" (İ'siz) üretip kalıpları kaçırıyordu.
- Body katmanı büyük harfli kalıplarla çalışmalı (IGNORECASE İ'yi eşleyemez).
"""
import pytest

import extractors.court_extractor as ce
from extractors.court_extractor import find_court_name


@pytest.fixture(autouse=True)
def _force_fallback_lists(monkeypatch):
    """DB config'i devre dışı bırak → fallback il/mahkeme listeleri kullanılsın."""
    import managers.config_manager as cm

    class _Boom:
        def __init__(self):
            raise RuntimeError("test: DynamicConfig devre dışı")

    monkeypatch.setattr(cm, "DynamicConfig", _Boom)
    # Önceki testlerden kalan derlenmiş pattern cache'ini sıfırla
    monkeypatch.setattr(ce, "_pattern_cache", None)
    monkeypatch.setattr(ce, "_pattern_cache_key", None)


# Body testleri için: mahkeme adını ilk 20 satırın (header katmanı) dışına iter
_PAD = "\n".join(f"dolgu satırı {i}" for i in range(25))


# ── Katman 1: Header ─────────────────────────────────────────────────────────

class TestHeader:
    def test_il_sira_tur(self):
        text = "T.C.\nANKARA\n5. ASLİYE HUKUK MAHKEMESİ\nESAS NO: 2023/145"
        assert find_court_name(text) == "ANKARA 5. ASLİYE HUKUK MAHKEMESİ"

    def test_mixed_case_header(self):
        # turkish_upper regresyonu: "Mahkemesi".upper() = "MAHKEMESI" eşleşmiyordu
        text = "T.C.\nİstanbul\n3. Asliye Ticaret Mahkemesi\nDosya No: 2024/7"
        assert find_court_name(text) == "İSTANBUL 3. ASLİYE TİCARET MAHKEMESİ"

    def test_yargitay_with_daire(self):
        text = "T.C.\nYARGITAY\n9. HUKUK DAİRESİ\nE. 2023/145 K. 2023/456"
        assert find_court_name(text) == "YARGITAY 9. HUKUK DAİRESİ"

    def test_danistay_plain(self):
        text = "T.C.\nDANIŞTAY\nBaşkanlığına sunulmak üzere"
        assert find_court_name(text) == "DANIŞTAY"

    def test_bam_with_daire(self):
        text = "T.C.\nİSTANBUL\nBÖLGE ADLİYE MAHKEMESİ\n12. HUKUK DAİRESİ"
        assert find_court_name(text) == "İSTANBUL BÖLGE ADLİYE MAHKEMESİ 12. HUKUK DAİRESİ"

    def test_bim_with_sozel_daire(self):
        # Sözel sıra sayılı daire ("ÜÇÜNCÜ")
        text = "T.C.\nANKARA\nBÖLGE İDARE MAHKEMESİ\nÜÇÜNCÜ İDARİ DAVA DAİRESİ"
        assert find_court_name(text) == "ANKARA BÖLGE İDARE MAHKEMESİ ÜÇÜNCÜ İDARİ DAVA DAİRESİ"

    def test_idare_mahkemesi(self):
        text = "T.C.\nANKARA\n10. İDARE MAHKEMESİ\n2024/123 E."
        assert find_court_name(text) == "ANKARA 10. İDARE MAHKEMESİ"

    def test_vergi_mahkemesi(self):
        text = "T.C.\nİZMİR\n2. VERGİ MAHKEMESİ\nDavacı: ..."
        assert find_court_name(text) == "İZMİR 2. VERGİ MAHKEMESİ"

    def test_sulh_ceza_hakimligi(self):
        text = "T.C.\nBURSA\n4. SULH CEZA HÂKİMLİĞİ\nSorgu No: 2024/1"
        assert find_court_name(text) == "BURSA 4. SULH CEZA HÂKİMLİĞİ"


# ── Katman 2: Body ───────────────────────────────────────────────────────────

class TestBody:
    def test_hukum_veren(self):
        text = _PAD + "\nHüküm veren İzmir 2. Asliye Hukuk Mahkemesi ilamının incelenmesinde"
        assert find_court_name(text) == "İZMİR 2. ASLİYE HUKUK MAHKEMESİ"

    def test_karar_veren(self):
        text = _PAD + "\nKarar veren Ankara 5. İş Mahkemesi dosyasında"
        assert find_court_name(text) == "ANKARA 5. İŞ MAHKEMESİ"

    def test_tarafindan(self):
        text = _PAD + "\nİşbu karar Konya 1. Aile Mahkemesi tarafından verilmiştir."
        assert find_court_name(text) == "KONYA 1. AİLE MAHKEMESİ"

    def test_mixed_case_body(self):
        # turkish_upper + büyük harfli kalıp regresyonu (body hiç çalışmıyordu)
        text = _PAD + "\nhüküm veren adana 3. ağır ceza mahkemesi kararı uyarınca"
        assert find_court_name(text) == "ADANA 3. AĞIR CEZA MAHKEMESİ"


# ── Genel davranış ───────────────────────────────────────────────────────────

class TestGeneral:
    def test_short_text_returns_none(self):
        assert find_court_name("kısa") is None

    def test_empty_returns_none(self):
        assert find_court_name("") is None

    def test_no_court_returns_none(self):
        text = "Taraflar arasındaki sözleşme uyarınca ödeme yapılmıştır.\nSaygılarımla."
        assert find_court_name(text) is None

    def test_header_wins_over_body(self):
        # Header'daki mahkeme, body'deki farklı mahkemeden önce gelir
        text = (
            "T.C.\nANKARA\n5. ASLİYE HUKUK MAHKEMESİ\n"
            + _PAD
            + "\nHüküm veren İzmir 2. Asliye Hukuk Mahkemesi kararı bozulmuştur."
        )
        assert find_court_name(text) == "ANKARA 5. ASLİYE HUKUK MAHKEMESİ"
