"""G067 — mahkeme adı yapısal kimlik kapısı (services/court_name.py).

Görev dosyasındaki ölçülmüş kusurların regresyon kilidi + kendi kart verimizden
çıkan karşı-örnekler. Mevcut `test_court_extractor.py` geri uyum kanıtıdır ve
DEĞİŞTİRİLMEZ; yeni vakalar buraya yazılır.
"""
import inspect
from pathlib import Path

import pytest

import extractors.court_extractor as ce
import services.court_name as cn
import services.judicial_unit as ju
from extractors.court_extractor import find_court_identity, find_court_name
from services.court_name import GUVEN_KISMI, GUVEN_TAM, GUVEN_YOK, parse_court_name


@pytest.fixture(autouse=True)
def _fallback_listeleri(monkeypatch):
    """DynamicConfig devre dışı → fallback il listesi kullanılsın (deterministik)."""
    import managers.config_manager as cm

    class _Boom:
        def __init__(self):
            raise RuntimeError("test: DynamicConfig devre dışı")

    monkeypatch.setattr(cm, "DynamicConfig", _Boom)
    monkeypatch.setattr(ce, "_pattern_cache", None)
    monkeypatch.setattr(ce, "_pattern_cache_key", None)


# Doğrudan `parse_court_name` çağrılarında il listesi ÇAĞIRANDAN gelir (saf modül).
_ILLER = tuple(ce._FALLBACK_ILLER)


def _basliktan(*satirlar: str) -> str:
    """Belge başlığı üretir (find_court_name 20 karakterden kısa metni okumaz)."""
    return "T.C.\n" + "\n".join(satirlar) + "\nESAS NO: 2024/1\nDAVACI: A. B."


# ── Görev dosyasındaki 6 ölçüm satırı ────────────────────────────────────────

class TestOlculmusKusurlar:
    def test_bagri_agriya_donusmuyor(self):
        # Kök neden: il alternasyonunda kelime sınırı yoktu → "BAĞRI" içinde "AĞRI"
        metin = _basliktan("BAĞRI", "1. ASLİYE HUKUK MAHKEMESİ")
        kimlik = find_court_identity(metin)
        assert kimlik is not None
        assert kimlik.yer is None
        assert "AĞRI" not in find_court_name(metin)
        assert find_court_name(metin) == "1. ASLİYE HUKUK MAHKEMESİ"

    def test_adliye_yeri_manavgat_taniniyor(self):
        metin = _basliktan("MANAVGAT", "1. ASLİYE HUKUK MAHKEMESİ")
        assert find_court_name(metin) == "MANAVGAT 1. ASLİYE HUKUK MAHKEMESİ"
        assert find_court_identity(metin).yer == "MANAVGAT"

    def test_bilesik_yargi_yeri_istanbul_anadolu(self):
        metin = _basliktan("İSTANBUL ANADOLU", "6. TÜKETİCİ MAHKEMESİ")
        kimlik = find_court_identity(metin)
        assert kimlik.yer == "İSTANBUL ANADOLU"
        assert find_court_name(metin) == "İSTANBUL ANADOLU 6. TÜKETİCİ MAHKEMESİ"

    def test_yargitay_tek_satirda_daireyi_koruyor(self):
        # Eski dal daire için satır sonu şart koşuyordu → "YARGITAY" (daire kayıp)
        metin = _basliktan("YARGITAY 11. HUKUK DAİRESİ")
        kimlik = find_court_identity(metin)
        assert kimlik.daire_no == 11
        assert find_court_name(metin) == "YARGITAY 11. HUKUK DAİRESİ"

    def test_yargitay_satir_sonuyla_da_calisiyor(self):
        metin = _basliktan("YARGITAY", "11. HUKUK DAİRESİ")
        assert find_court_name(metin) == "YARGITAY 11. HUKUK DAİRESİ"
        assert find_court_identity(metin).daire_no == 11

    def test_bam_dairesi_bozulmadan_geciyor(self):
        metin = _basliktan("İSTANBUL", "BÖLGE ADLİYE MAHKEMESİ", "43. HUKUK DAİRESİ")
        kimlik = find_court_identity(metin)
        assert find_court_name(metin) == "İSTANBUL BÖLGE ADLİYE MAHKEMESİ 43. HUKUK DAİRESİ"
        assert (kimlik.yer, kimlik.daire_no) == ("İSTANBUL", 43)


# ── Kendi kart verimizden gelen karşı-örnekler ───────────────────────────────

class TestKendiVerimiz:
    @pytest.mark.parametrize(
        "yer, sizan_il, tur",
        [
            ("TATVAN", "VAN", "2. ASLİYE HUKUK MAHKEMESİ"),
            ("GELİBOLU", "BOLU", "1. ASLİYE HUKUK MAHKEMESİ"),
            ("SAFRANBOLU", "BOLU", "1. SULH HUKUK MAHKEMESİ"),
            ("İNEBOLU", "BOLU", "1. ASLİYE CEZA MAHKEMESİ"),
        ],
    )
    def test_kelime_icindeki_il_sizmiyor(self, yer, sizan_il, tur):
        metin = _basliktan(yer, tur)
        kimlik = find_court_identity(metin)
        assert kimlik.yer == yer
        assert kimlik.yer != sizan_il
        assert find_court_name(metin) == f"{yer} {tur}"

    @pytest.mark.parametrize(
        "yer, tur",
        [
            ("ŞİŞLİ", "3. ASLİYE HUKUK MAHKEMESİ"),
            ("BAKIRKÖY", "7. AİLE MAHKEMESİ"),
            ("BEYOĞLU", "1. SULH HUKUK MAHKEMESİ"),
            ("GEBZE", "2. İŞ MAHKEMESİ"),
            ("KARTAL", "4. ASLİYE TİCARET MAHKEMESİ"),
        ],
    )
    def test_adliye_yerleri_artik_taniniyor(self, yer, tur):
        kimlik = find_court_identity(_basliktan(yer, tur))
        assert kimlik.yer == yer
        assert kimlik.guven == GUVEN_TAM

    def test_slashli_kart_degeri(self):
        # Kartlardaki tipik yazım: "T.C. / TATVAN / 2. ASLİYE HUKUK MAHKEMESİ"
        kimlik = parse_court_name("T.C. / TATVAN / 2. ASLİYE HUKUK MAHKEMESİ")
        assert (kimlik.yer, kimlik.sira) == ("TATVAN", 2)


# ── Daire okuması: basamak düşmesi ölçülebilir olmalı ────────────────────────

class TestDaireOkumasi:
    @pytest.mark.parametrize("no", [11, 21, 43])
    def test_iki_basamak_korunuyor(self, no):
        kimlik = parse_court_name(f"YARGITAY {no}. HUKUK DAİRESİ")
        assert kimlik.daire_no == no
        assert kimlik.duz_ad() == f"YARGITAY {no}. HUKUK DAİRESİ"

    @pytest.mark.parametrize(
        "yazim",
        ["11. HUKUK DAİRESİ", "11. HD", "ONBİRİNCİ HUKUK DAİRESİ", "ON BİRİNCİ HUKUK DAİRESİ"],
    )
    def test_ayni_daire_kimligi(self, yazim):
        kimlik = parse_court_name(f"YARGITAY {yazim}")
        assert (kimlik.daire_no, kimlik.daire_adi) == (11, "HUKUK DAİRESİ")

    def test_ceza_dairesi_kisaltmasi(self):
        kimlik = parse_court_name("YARGITAY 8. CD")
        assert (kimlik.daire_no, kimlik.daire_adi) == (8, "CEZA DAİRESİ")

    def test_sozel_daire_yuzeyi_korunuyor(self):
        kimlik = parse_court_name("ANKARA BÖLGE İDARE MAHKEMESİ ÜÇÜNCÜ İDARİ DAVA DAİRESİ")
        assert kimlik.daire_no == 3
        assert kimlik.daire_yuzey == "ÜÇÜNCÜ İDARİ DAVA DAİRESİ"


# ── Tahmin yasağı: tanınmayan yer başka bir yere DÖNÜŞMEZ ────────────────────

class TestTaninmayanYer:
    @pytest.mark.parametrize("uydurma", ["ZIRZOP", "FOOBARKÖY", "KIZILTEPEDEN", "BAĞRI"])
    def test_sozluk_disi_yer_bos_kalir(self, uydurma):
        metin = _basliktan(uydurma, "3. ASLİYE HUKUK MAHKEMESİ")
        kimlik = find_court_identity(metin)
        assert kimlik.yer is None
        assert kimlik.guven == GUVEN_KISMI
        assert find_court_name(metin) == "3. ASLİYE HUKUK MAHKEMESİ"

    def test_uzaktaki_il_mahkemeye_yapistirilmaz(self):
        # Yer ile mahkeme arasında harf varsa yer DOĞRULANMAMIŞ sayılır
        kimlik = parse_court_name("ANKARA CADDESİ NO 5 TAPU MÜDÜRLÜĞÜ YANI 3. ASLİYE HUKUK MAHKEMESİ")
        assert kimlik.yer is None


# ── Güven damgası (G068 bu sözleşmeye bağlanacak) ────────────────────────────

class TestGuvenDamgasi:
    def test_tam_yer_ve_tur_dogrulandi(self):
        assert parse_court_name("ANKARA 5. ASLİYE HUKUK MAHKEMESİ", yerler=_ILLER).guven == GUVEN_TAM

    def test_kismi_tur_dogrulandi_yer_taninmadi(self):
        assert parse_court_name("ZIRZOP 5. ASLİYE HUKUK MAHKEMESİ").guven == GUVEN_KISMI

    def test_kismi_ust_mahkeme_yer_gerektirmez(self):
        kimlik = parse_court_name("YARGITAY 9. HUKUK DAİRESİ")
        assert kimlik.guven == GUVEN_KISMI
        assert kimlik.yer is None

    def test_yok_tur_bile_taninmadi(self):
        kimlik = parse_court_name("ANKARA 7. TESCİL MAHKEMESİ")
        assert kimlik.guven == GUVEN_YOK
        assert kimlik.tur_kanonik is None

    def test_mahkeme_olmayan_kurum_uretilmez(self):
        # Son çare yolu bilinçli olarak yalnız yargısal sonekleri tanır
        assert find_court_name(_basliktan("ANKARA", "TAPU MÜDÜRLÜĞÜ")) is None

    def test_dairesiz_bam_yuzeyi_korunur(self):
        # Kanonik karşılığı yok (judicial_unit BAM için HUKUK/CEZA arar) ama
        # yüzey uydurma DEĞİL; geri uyum için string olarak korunur.
        metin = _basliktan("İSTANBUL", "BÖLGE ADLİYE MAHKEMESİ")
        assert find_court_name(metin) == "İSTANBUL BÖLGE ADLİYE MAHKEMESİ"
        assert find_court_identity(metin).guven == GUVEN_YOK

    def test_hicbir_iz_yoksa_none(self):
        assert parse_court_name("Taraflar arasındaki sözleşme uyarınca ödeme yapılmıştır.") is None


# ── Liste kaynağı: DB yolu ve fallback yolu ─────────────────────────────────

class TestListeKaynagi:
    def test_fallback_yolu_ili_taniyor(self):
        # autouse fixture DynamicConfig'i patlatıyor → _FALLBACK_ILLER devrede
        assert find_court_identity(_basliktan("İZMİR", "2. VERGİ MAHKEMESİ")).yer == "İZMİR"

    def test_fallback_yolunda_db_ozel_ili_yok(self):
        assert find_court_identity(_basliktan("HAYALİYE", "2. VERGİ MAHKEMESİ")).yer is None

    def test_db_yolu_config_ilini_taniyor(self, monkeypatch):
        import managers.config_manager as cm

        class _SahteConfig:
            def get_court_types(self):
                return [{"name": "ASLİYE HUKUK MAHKEMESİ"}, {"name": "VERGİ MAHKEMESİ"}]

            def get_cities(self):
                return [{"name": "Hayaliye"}, {"name": "İstanbul"}]

        monkeypatch.setattr(cm, "DynamicConfig", _SahteConfig)
        monkeypatch.setattr(ce, "_pattern_cache", None)
        monkeypatch.setattr(ce, "_pattern_cache_key", None)

        assert find_court_identity(_basliktan("HAYALİYE", "2. VERGİ MAHKEMESİ")).yer == "HAYALİYE"

    def test_yer_listesi_cagirandan_gelir(self):
        # Saf modül: liste okuması yok, argümanla gelir (judicial_unit deseni)
        assert parse_court_name("HAYALİYE 2. VERGİ MAHKEMESİ").yer is None
        assert parse_court_name("HAYALİYE 2. VERGİ MAHKEMESİ", yerler=("Hayaliye",)).yer == "HAYALİYE"


# ── Kanonik tür tek kaynak: judicial_unit ───────────────────────────────────

class TestTurKanonikTekKaynak:
    def test_kalip_tablosu_ayni_nesne(self):
        assert cn.PATTERNS is ju.PATTERNS

    def test_ikinci_kopya_yok(self):
        """Modülde kanonik tür adlarının ikinci bir listesi/dizisi bulunmamalı.

        Tek istisna "DANIŞTAY": o bir mahkeme TÜRÜ değil, yer gerektirmeyen üst
        mahkeme kimliğidir (UST_MAHKEMELER) ve judicial_unit'te de aynı adla geçer.
        """
        kanonik = {ad for _rx, ad, _parent in ju.PATTERNS}
        modul_stringleri: set[str] = set()
        for isim, deger in vars(cn).items():
            if isim.startswith("__"):
                continue
            if isinstance(deger, (list, tuple, set, frozenset)):
                modul_stringleri |= {x for x in deger if isinstance(x, str)}
            elif isinstance(deger, dict):
                modul_stringleri |= {k for k in deger if isinstance(k, str)}
                modul_stringleri |= {v for v in deger.values() if isinstance(v, str)}
        assert kanonik & modul_stringleri <= {"DANIŞTAY"}

    @pytest.mark.parametrize(
        "ad, beklenen",
        [
            ("ANKARA 5. ASLİYE HUKUK MAHKEMESİ", "ASLİYE HUKUK MAHKEMESİ"),
            ("BURSA 4. SULH CEZA HÂKİMLİĞİ", "SULH CEZA HAKİMLİĞİ"),
            ("İSTANBUL BÖLGE ADLİYE MAHKEMESİ 43. HD", "BÖLGE ADLİYE MAH. HUKUK DAİRESİ"),
            ("ANKARA 5. İCRA DAİRESİ", "İCRA DAİRESİ"),
            ("İSTANBUL ANADOLU 6. TÜKETİCİ MAHKEMESİ", "TÜKETİCİ MAHKEMESİ"),
        ],
    )
    def test_kanonik_deger_judicial_unitten(self, ad, beklenen):
        assert parse_court_name(ad).tur_kanonik == beklenen


# ── Geri uyum: find_court_name sözleşmesi + analyzer'a dokunulmadı ──────────

class TestGeriUyum:
    def test_imza_ve_donus_tipi_degismedi(self):
        imza = inspect.signature(find_court_name)
        assert str(imza) == "(text: str) -> str | None"
        assert isinstance(find_court_name(_basliktan("ANKARA", "5. ASLİYE HUKUK MAHKEMESİ")), str)

    def test_kisa_metin_ve_bos_metin_none(self):
        assert find_court_name("kısa") is None
        assert find_court_name("") is None

    def test_analyzer_cagrisi_degismedi(self):
        kaynak = Path(__file__).resolve().parents[1] / "analyzer.py"
        metin = kaynak.read_text(encoding="utf-8")
        assert "from extractors.court_extractor import find_court_name" in metin
        assert 'pre_extracted["court"] = find_court_name(extracted_text)' in metin
