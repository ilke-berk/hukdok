"""G071 — dolgu kelime toleransı + merci türü önceliği.

İki ayrı boşluk, aynı aile:

1. **Dolgu kelime.** `court_name._yer_bul` yer ile tür çapası arasında HARF
   görünce vazgeçiyordu; sözlükte olan yer bile düşüyordu
   (`Şişli **Nöbetçi** Sulh Hukuk`, `Bakırköy **Cumhuriyet** Başsavcılığı`).
   Çözüm KAPALI liste (`court_name.DOLGU_KELIMELER`) — "arada N kelimeye izin
   ver" biçimindeki genel tolerans G067/G070'in karşı-örneklerini geri getirirdi.
   Bu dosya hem listenin işlediğini hem de liste DIŞI dolgunun hâlâ KISMİ
   bıraktığını kilitler.

2. **Tür önceliği.** `judicial_unit.PATTERNS` sırasında çıplak `\\bTUKETICI\\b`
   sıfatı `\\bHAKEM HEYETI\\b` kalıbından önce geliyordu; hakem heyeti mahkeme
   sayılıyordu (`İzmir İl Tüketici Hakem Heyeti → TÜKETİCİ MAHKEMESİ`).
   `court_name` tarafında ayrıca çapa ile kurum soneki arasına giren kelimeler
   (`TÜKETİCİ **HAKEM** HEYETİ`) yüzeye katılmıyordu.

Ölçüm (2026-08-22, lokal prod kopyası, 2.183 tekil `cases.court`):
KISMİ **113 → 49** tekil (2.459 → 2.302 kayıt); 64 tekil değer (157 kayıt)
KISMİ→TAM'a döndü ve TEK BİR değer gerilemedi. Ayrıntı görev raporunda.
"""
import pytest

import extractors.court_extractor as ce
from services.court_name import (
    DOLGU_KELIMELER,
    GUVEN_KISMI,
    GUVEN_TAM,
    parse_court_name,
)
from services.judicial_unit import PATTERNS, derive_judicial_unit

# Saf modül: il listesi ÇAĞIRANDAN gelir; fallback deterministiktir.
_ILLER = tuple(ce._FALLBACK_ILLER)


def _coz(metin: str):
    cn = parse_court_name(metin, yerler=_ILLER)
    assert cn is not None, metin
    return cn


# ---------------------------------------------------------------------------
# 1. Görev tanımındaki ölçüm tablosu — dolgu kelime artık yeri düşürmüyor
# ---------------------------------------------------------------------------
class TestDolguKelimeYeriDusurmuyor:
    """G071 hedef tablosu: dördü de ÖNCEDEN KISMİ + yer=None dönüyordu."""

    @pytest.mark.parametrize(
        "metin, yer, kanonik",
        [
            ("Şişli 1. Sulh Hukuk Mahkemesi", "ŞİŞLİ", "SULH HUKUK MAHKEMESİ"),
            ("Şişli Nöbetçi Sulh Hukuk Mahkemesi", "ŞİŞLİ", "SULH HUKUK MAHKEMESİ"),
            ("Eyüp Nöbetçi Asliye Hukuk Mahkemesi", "EYÜP", "ASLİYE HUKUK MAHKEMESİ"),
            ("Bakırköy Cumhuriyet Başsavcılığı", "BAKIRKÖY", "CUMHURİYET BAŞSAVCILIĞI"),
        ],
    )
    def test_hedef_tablosu(self, metin, yer, kanonik):
        cn = _coz(metin)
        assert (cn.guven, cn.yer, cn.tur_kanonik) == (GUVEN_TAM, yer, kanonik)

    def test_ust_uste_dolgu_kelimeler(self):
        """`Nöbetçi Cumhuriyet` — iki dolgu arka arkaya; yer yine okunuyor."""
        cn = _coz("Tokat Nöbetçi Cumhuriyet Başsavcılığı")
        assert (cn.guven, cn.yer) == (GUVEN_TAM, "TOKAT")

    def test_bilesik_yer_dolgudan_sonra_kisalmiyor(self):
        """Bileşik yargı yeri dolgu kelimeyle de tam adıyla okunur."""
        cn = _coz("İstanbul Anadolu Nöbetçi Cumhuriyet Başsavcılığı")
        assert (cn.guven, cn.yer) == (GUVEN_TAM, "İSTANBUL ANADOLU")

    def test_savcilik_kisa_yazimi(self):
        """`Cumhuriyet Savcılığı` (Baş- yok) de aynı yoldan geçer."""
        cn = _coz("İstanbul Cumhuriyet Savcılığı")
        assert (cn.guven, cn.yer, cn.tur_kanonik) == (
            GUVEN_TAM, "İSTANBUL", "CUMHURİYET BAŞSAVCILIĞI"
        )

    def test_nobetci_dilekce_yazimi(self):
        """Canlı belge akışının en sık kalıbı (tebligat/tensip): `… Sayın Hakimliğine`."""
        cn = _coz("İstanbul Nöbetçi Asliye Hukuk Mahkemesi Sayın Hakimliğine")
        assert (cn.guven, cn.yer, cn.tur_kanonik) == (
            GUVEN_TAM, "İSTANBUL", "ASLİYE HUKUK MAHKEMESİ"
        )


# ---------------------------------------------------------------------------
# 2. Kimlik kararı: NÖBETÇİ kimliğe GİRMEZ ama iki kart aynı kimliğe düşmez
# ---------------------------------------------------------------------------
class TestNobetciKimlik:
    """Nöbetçi mahkeme, o mahkemenin KENDİSİdir — ayrı bir yargı yeri değil.

    Karar (G071 karar noktası 2): `NÖBETÇİ` yer/tür/sıra alanlarına GİRMEZ,
    ham yüzeyde KORUNUR. Sıra numaralı kartla çakışma bu yüzden olmaz.
    """

    def test_nobetci_tur_yuzeyine_sizmiyor(self):
        cn = _coz("Şişli Nöbetçi Sulh Hukuk Mahkemesi")
        assert cn.tur_yuzey == "SULH HUKUK MAHKEMESİ"
        assert cn.sira is None

    def test_nobetci_ham_yuzeyde_korunuyor(self):
        cn = _coz("Şişli Nöbetçi Sulh Hukuk Mahkemesi")
        assert cn.ham == "ŞİŞLİ NÖBETÇİ SULH HUKUK MAHKEMESİ"

    def test_nobetci_sirali_mahkemeyle_ayni_kimlige_dusmuyor(self):
        nobetci = _coz("Şişli Nöbetçi Sulh Hukuk Mahkemesi")
        birinci = _coz("Şişli 1. Sulh Hukuk Mahkemesi")
        assert nobetci.sira != birinci.sira
        assert nobetci.ham != birinci.ham
        assert nobetci.duz_ad() != birinci.duz_ad()


# ---------------------------------------------------------------------------
# 3. Liste DIŞI dolgu yanlış yer ÜRETMİYOR (kapalı liste kararının kapısı)
# ---------------------------------------------------------------------------
class TestListeDisiDolguKismiKaliyor:
    """Genel tolerans yerine kapalı liste seçildi; bu, o kararın mekanik kapısı."""

    @pytest.mark.parametrize(
        "metin",
        [
            "Şişli Acil Sulh Hukuk Mahkemesi",
            "Şişli Cumhuriyet Mahallesi Sulh Hukuk Mahkemesi",
            "Bakırköy Eski Asliye Ticaret Mahkemesi",
        ],
    )
    def test_taninmayan_dolgu_yer_uretmiyor(self, metin):
        cn = _coz(metin)
        assert cn.yer is None
        assert cn.guven == GUVEN_KISMI

    def test_askeri_yuksek_bilincle_disarida(self):
        """AYİM bir idare mahkemesi DEĞİL; dolgu sayılsa YANLIŞ kimlik üretirdi.

        `Ankara 3. Askeri Yüksek İdare Mahkemesi` → yer=ANKARA + İDARE MAHKEMESİ
        okunsaydı, ayrı bir yüksek mahkeme Ankara'nın idare mahkemesi olurdu.
        KISMİ kalması bilinçli bir karardır (bkz. `DOLGU_KELIMELER` yorumu).
        """
        cn = _coz("Ankara 3. Askeri Yüksek İdare Mahkemesi")
        assert cn.yer is None
        assert cn.guven == GUVEN_KISMI
        assert not {"ASKERİ", "YÜKSEK"} & set(DOLGU_KELIMELER)


# ---------------------------------------------------------------------------
# 4. G067 + G070 karşı-örnekleri: dolgu toleransı SIZINTI açmadı
# ---------------------------------------------------------------------------
class TestKarsiOrneklerYesilKaliyor:
    """Kelime sınırı, dolgu kelime araya girdiğinde de geçerli."""

    @pytest.mark.parametrize(
        "metin, beklenen",
        [
            ("Tatvan 2. Asliye Hukuk Mahkemesi", "TATVAN"),
            ("Tatvan Nöbetçi Asliye Hukuk Mahkemesi", "TATVAN"),
            ("Gelibolu Nöbetçi Sulh Hukuk Mahkemesi", "GELİBOLU"),
            ("Safranbolu Cumhuriyet Başsavcılığı", "SAFRANBOLU"),
            ("İnebolu Nöbetçi Asliye Hukuk Mahkemesi", "İNEBOLU"),
        ],
    )
    def test_uzun_ad_kisa_ada_dusmuyor(self, metin, beklenen):
        assert _coz(metin).yer == beklenen

    @pytest.mark.parametrize(
        "metin",
        [
            "Bağrı 1. Asliye Hukuk Mahkemesi",
            "Bağrı Nöbetçi Asliye Hukuk Mahkemesi",
            "Bayatlı Nöbetçi Sulh Hukuk Mahkemesi",
            "Fatihler Cumhuriyet Başsavcılığı",
            "Kemerburgaz Nöbetçi Asliye Hukuk Mahkemesi",
        ],
    )
    def test_yer_olmayan_onek_yer_uretmiyor(self, metin):
        assert _coz(metin).yer is None


# ---------------------------------------------------------------------------
# 5. Hakem heyeti mahkeme DEĞİL — tür önceliği
# ---------------------------------------------------------------------------
class TestHakemHeyetiMahkemeDegil:
    """`\\bHAKEM HEYETI\\b` artık çıplak `\\bTUKETICI\\b` sıfatından ÖNCE."""

    @pytest.mark.parametrize(
        "metin",
        [
            "İzmir İl Tüketici Hakem Heyeti",
            "Kadıköy İlçe Tüketici Hakem Heyeti",
            "Fatih Tüketici Hakem Heyeti",
            "Tüketici Sorunları Hakem Heyeti",
        ],
    )
    def test_derive_hakem_heyeti(self, metin):
        assert derive_judicial_unit(metin) == "TÜKETİCİ HAKEM HEYETİ"

    def test_parse_hakem_heyeti_yer_ve_tur(self):
        cn = _coz("İzmir İl Tüketici Hakem Heyeti")
        assert (cn.guven, cn.yer, cn.tur_kanonik) == (
            GUVEN_TAM, "İZMİR", "TÜKETİCİ HAKEM HEYETİ"
        )
        assert cn.tur_yuzey == "TÜKETİCİ HAKEM HEYETİ"

    def test_tahkim_hakem_heyetinden_once_kaliyor(self):
        """Sigorta tahkimi bir TÜKETİCİ hakem heyeti değildir — sıra korundu."""
        assert derive_judicial_unit("Sigorta Tahkim Komisyonu Hakem Heyeti") == "TAHKİM HEYETİ"
        kalip_sirasi = [rx for rx, _ad, _p in PATTERNS]
        assert kalip_sirasi.index(r"\bTAHKIM\b") < kalip_sirasi.index(r"\bHAKEM HEYETI\b")
        assert kalip_sirasi.index(r"\bHAKEM HEYETI\b") < kalip_sirasi.index(r"\bTUKETICI\b")

    @pytest.mark.parametrize(
        "metin",
        [
            "İstanbul 5. Tüketici Mahkemesi",
            "Ankara 3. Tüketici Mahkemesi",
            "Bakırköy 9. Tüketici Mahkemesi",
            "Kayseri 3. Tüketici Mahkemesi",
        ],
    )
    def test_tuketici_mahkemesi_vakalari_bozulmadi(self, metin):
        assert derive_judicial_unit(metin) == "TÜKETİCİ MAHKEMESİ"
        assert _coz(metin).tur_kanonik == "TÜKETİCİ MAHKEMESİ"

    def test_tuketici_mahkemesi_sifatiyla_bozulmadi(self):
        """G070 raporundaki tek kayıtlık uç örnek: sıfat hâlâ TÜKETİCİ'ye gidiyor."""
        assert derive_judicial_unit(
            "Yenice Asliye Hukuk Mahkemesi (Tüketici Mahkemesi Sıfatıyla)"
        ) == "TÜKETİCİ MAHKEMESİ"


# ---------------------------------------------------------------------------
# 6. Ara kelimeli sonek genişlemesi YALNIZ türü değiştiriyorsa uygulanır
# ---------------------------------------------------------------------------
class TestAraKelimeliSonekDar:
    """Genişleme, mevcut tür yüzeylerini sessizce büyütmemeli."""

    def test_turu_degistirmeyen_ek_yuzeye_katilmiyor(self):
        cn = _coz("İstanbul 3. İcra Dosya Müdürlüğü")
        assert cn.tur_kanonik == "İCRA DAİRESİ"
        assert cn.tur_yuzey == "İCRA"
        assert cn.ham == "İSTANBUL 3. İCRA"

    def test_hemen_sagdaki_sonek_onceligini_koruyor(self):
        cn = _coz("Kadıköy 3. İcra Müdürlüğü")
        assert cn.tur_yuzey == "İCRA MÜDÜRLÜĞÜ"
        assert cn.tur_kanonik == "İCRA DAİRESİ"

    def test_mahkeme_kalemi_yuzeye_yapismiyor(self):
        cn = _coz("Bakırköy 1. Asliye Hukuk Mahkemesi Kalem Müdürlüğü")
        assert cn.ham == "BAKIRKÖY 1. ASLİYE HUKUK MAHKEMESİ"
        assert cn.tur_kanonik == "ASLİYE HUKUK MAHKEMESİ"


# ---------------------------------------------------------------------------
# 7. Dolgu listesinin hijyeni — liste büyürse bu kapı konuşur
# ---------------------------------------------------------------------------
class TestDolguListesiHijyeni:
    def test_tekrar_yok_ve_kanonik_yazim(self):
        assert len(set(DOLGU_KELIMELER)) == len(DOLGU_KELIMELER)
        for k in DOLGU_KELIMELER:
            assert k == k.strip() and "  " not in k
            assert len(k) >= 2

    def test_dolgu_kelimesi_yargi_yeri_degil(self):
        """Bir yargı yeri adı dolgu listesine girerse o yer artık okunamaz."""
        from services.court_name import BILESIK_YARGI_YERLERI, YARGI_YERLERI

        yerler = set(YARGI_YERLERI) | set(BILESIK_YARGI_YERLERI) | set(_ILLER)
        assert not yerler & set(DOLGU_KELIMELER)
