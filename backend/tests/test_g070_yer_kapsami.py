"""G070 — yargı yeri sözlüğünün KAPSAMI ölçülebilir eşikle kilitli.

G067 sözlüğü açtı, kapsamı gözle bıraktı. Bu dosya kapsamı SAYIYA bağlar:
`KART_VERISINDEN_YERLER`, 2026-08-19'da lokal prod kopyasındaki 2.163 tekil
`cases.court` değerinin ayrıştırıcı tarafından TAM okunan yer adlarıdır (232 ad).
Repoya kart/dava verisi GİRMEZ — yalnız YER ADLARI (kişisel veri değil).

Eşik neden %95 ve neden bir eşik: sözlüğün bilinçli olarak eksik kalma hakkı var
(modül docstring'i: eksik yer `None` üretir, yanlış yer üretmez) ve yanlış çıktığı
anlaşılan bir adın çıkarılması testi kırmızıya döndürmemeli. Ama sözlüğün ya da
kelime sınırı makinesinin toptan bozulması (blokların boşalması, sınırın gevşemesi,
alternasyonun sırasının kayması) eşiği anında altına düşürür. Ölçülen değer bugün
%100'dür; eşik 11 adlık bilinçli-değişiklik payı bırakır.
"""
import pytest

import extractors.court_extractor as ce
import services.court_name as cn
from services.court_name import GUVEN_TAM, parse_court_name

# Doğrudan `parse_court_name` çağrılarında il listesi ÇAĞIRANDAN gelir (saf modül);
# fallback il listesi deterministiktir (DynamicConfig'e bağlı değil).
_ILLER = tuple(ce._FALLBACK_ILLER)

#: Kapsam eşiği — temsilî yer adı kümesinin en az bu oranı TAM okunmalı.
ESIK = 0.95

# --------------------------------------------------------------------------
# G070'te sözlüğe GİREN adlar (kendi kart verimizde ölçüldü, 56 tekil değer)
# --------------------------------------------------------------------------
G070_EKLENEN_YERLER: tuple[str, ...] = (
    "SARIYER", "FATİH", "BEŞİKTAŞ", "BAĞCILAR", "ZEYTİNBURNU", "ÜMRANİYE",
    "GÖLCÜK", "KOCAALİ", "KARABURUN", "KEMER", "BUCAK", "ÇEKEREK", "BAYAT",
    "ALTINTAŞ", "ÇAYKARA", "ESPİYE", "HINIS", "KARAYAZI", "LİCE", "NURDAĞI",
    "ANDIRIN", "İMAMOĞLU",
)

# --------------------------------------------------------------------------
# Temsilî küme: kart verimizde GEÇEN ve ayrıştırıcının yer olarak okuduğu adlar
# (2026-08-19 ölçümü, 232 ad — 81 il + adliye/bileşik yargı yerleri)
# --------------------------------------------------------------------------
KART_VERISINDEN_YERLER: tuple[str, ...] = (
    "ADANA", "ADIYAMAN", "AFYONKARAHİSAR", "AKHİSAR", "AKSARAY",
    "AKYAZI", "AKÇAABAT", "AKÇAKOCA", "AKŞEHİR", "ALANYA",
    "ALAPLI", "ALAŞEHİR", "ALTINTAŞ", "ANAMUR", "ANDIRIN",
    "ANKARA", "ANKARA BATI", "ANTALYA", "ARDAHAN", "AYDIN",
    "AYVACIK", "AYVALIK", "AĞRI", "BAFRA", "BAKIRKÖY",
    "BALIKESİR", "BANDIRMA", "BARTIN", "BATMAN", "BAYAT",
    "BAĞCILAR", "BERGAMA", "BEYKOZ", "BEYOĞLU", "BEŞİKTAŞ",
    "BODRUM", "BOLU", "BOZOVA", "BUCAK", "BURDUR",
    "BURHANİYE", "BURSA", "BÜYÜKÇEKMECE", "BİGA", "BİLECİK",
    "BİNGÖL", "BİRECİK", "BİSMİL", "CEYHAN", "CİZRE",
    "DATÇA", "DENİZLİ", "DERİK", "DÖRTYOL", "DÜZCE",
    "DİDİM", "DİKİLİ", "DİYARBAKIR", "EDREMİT", "EDİRNE",
    "ELAZIĞ", "ELBİSTAN", "ERBAA", "ERCİŞ", "ERDEMLİ",
    "EREĞLİ", "ERGANİ", "ERZURUM", "ERZİN", "ERZİNCAN",
    "ESKİŞEHİR", "ESPİYE", "EYÜP", "FATSA", "FATİH",
    "FETHİYE", "GAZİANTEP", "GAZİOSMANPAŞA", "GEBZE", "GEDİZ",
    "GELİBOLU", "GEMLİK", "GERMENCİK", "GÖLCÜK", "GÖNEN",
    "GÜMÜŞHANE", "GİRESUN", "HAKKARİ", "HALFETİ", "HATAY",
    "HENDEK", "HINIS", "ISPARTA", "IĞDIR", "KADIKÖY",
    "KADİRLİ", "KAHRAMANMARAŞ", "KAHTA", "KAMAN", "KARABURUN",
    "KARABÜK", "KARAMAN", "KARAPINAR", "KARASU", "KARAYAZI",
    "KARTAL", "KARŞIYAKA", "KASTAMONU", "KAYSERİ", "KAŞ",
    "KEMER", "KEŞAN", "KIRIKHAN", "KIRIKKALE", "KIRKLARELİ",
    "KIRŞEHİR", "KIZILCAHAMAM", "KIZILTEPE", "KOCAALİ", "KOCAELİ",
    "KONYA", "KOZAN", "KULU", "KURTALAN", "KUŞADASI",
    "KÖRFEZ", "KÜTAHYA", "KÜÇÜKÇEKMECE", "KİLİS", "LÜLEBURGAZ",
    "LİCE", "MALATYA", "MANAVGAT", "MANİSA", "MARDİN",
    "MARMARİS", "MENEMEN", "MERSİN", "MUDANYA", "MUT",
    "MUĞLA", "MUŞ", "MİDYAT", "MİLAS", "NEVŞEHİR",
    "NURDAĞI", "NİZİP", "NİĞDE", "OLTU", "ORDU",
    "ORHANGAZİ", "OSMANİYE", "PAZARCIK", "PENDİK", "POLATLI",
    "REYHANLI", "RİZE", "SAFRANBOLU", "SAKARYA", "SALİHLİ",
    "SAMANDAĞ", "SAMSUN", "SANDIKLI", "SARIGÖL", "SARIYER",
    "SEFERİHİSAR", "SENİRKENT", "SERİK", "SOMA", "SULTANBEYLİ",
    "SULUOVA", "SUNGURLU", "SÖKE", "SÖĞÜT", "SİLİFKE",
    "SİLİVRİ", "SİNCAN", "SİNOP", "SİVAS", "SİVEREK",
    "SİİRT", "TARSUS", "TATVAN", "TAVAS", "TAVŞANLI",
    "TEKİRDAĞ", "TOKAT", "TRABZON", "TURGUTLU", "TURHAL",
    "TUZLA", "TİRE", "UŞAK", "VAN", "VEZİRKÖPRÜ",
    "YALOVA", "YALVAÇ", "YATAĞAN", "YOZGAT", "YÜKSEKOVA",
    "ZARA", "ZEYTİNBURNU", "ZONGULDAK", "ZİLE", "ÇANAKKALE",
    "ÇARŞAMBA", "ÇATALCA", "ÇAYCUMA", "ÇAYELİ", "ÇAYKARA",
    "ÇEKEREK", "ÇERKEZKÖY", "ÇEŞME", "ÇORLU", "ÇORUM",
    "ÇUMRA", "ÇİVRİL", "ÖDEMİŞ", "ÜMRANİYE", "ÜNYE",
    "ÜSKÜDAR", "İMAMOĞLU", "İNEBOLU", "İNEGÖL", "İSKENDERUN",
    "İSLAHİYE", "İSTANBUL", "İSTANBUL ANADOLU", "İZMİR", "ŞANLIURFA",
    "ŞİLE", "ŞİŞLİ",
)


def _tam_okunuyor(yer: str) -> bool:
    """Yer adı sentetik bir mahkeme adının içinde TAM güvenle okunuyor mu."""
    kimlik = parse_court_name(f"{yer} 1. ASLİYE HUKUK MAHKEMESİ", yerler=_ILLER)
    return kimlik is not None and kimlik.guven == GUVEN_TAM and kimlik.yer == yer


class TestKapsamEsigi:
    def test_temsili_kume_esigin_uzerinde(self):
        okunmayan = [y for y in KART_VERISINDEN_YERLER if not _tam_okunuyor(y)]
        oran = 1 - len(okunmayan) / len(KART_VERISINDEN_YERLER)
        assert oran >= ESIK, (
            f"Yargı yeri kapsamı {oran:.3f} < {ESIK}; okunamayan adlar: {okunmayan}"
        )

    def test_temsili_kume_bugun_tam(self):
        # Ölçülen değer bugün %100 — eşik payı bilinçli değişiklik içindir,
        # sessiz gerilemeyi örtmek için değil.
        assert [y for y in KART_VERISINDEN_YERLER if not _tam_okunuyor(y)] == []

    def test_g070_eklenen_yerlerin_hepsi_taniniyor(self):
        # Bu testin ESKİ sözlükte kırmızı olması gerekir (22 ad G070'te girdi).
        assert [y for y in G070_EKLENEN_YERLER if not _tam_okunuyor(y)] == []

    @pytest.mark.parametrize(
        "metin,beklenen",
        [
            ("SARIYER SULH HUKUK MAHKEMESİ", "SARIYER"),
            ("FATİH 3. İCRA MÜDÜRLÜĞÜ", "FATİH"),
            ("HINIS ASLİYE HUKUK MAHKEMESİ", "HINIS"),
            ("ANDIRIN ASLİYE HUKUK MAHKEMESİ", "ANDIRIN"),
            ("BAĞCILAR 2. AİLE MAHKEMESİ", "BAĞCILAR"),
            ("GÖLCÜK 1. İCRA MÜDÜRLÜĞÜ", "GÖLCÜK"),
            ("ANTALYA KEMER ADLİYESİ ARABULUCULUK BÜROSU", "KEMER"),
        ],
    )
    def test_kart_verisindeki_ham_yazimlar(self, metin, beklenen):
        # Kendi kart verimizden ALINAN yazımlar (yalnız yer + mahkeme türü).
        kimlik = parse_court_name(metin, yerler=_ILLER)
        assert kimlik is not None
        assert kimlik.yer == beklenen
        assert kimlik.guven == GUVEN_TAM


class TestSozlukHijyeni:
    """Sözlüğe 'yer olmayan' bir şey girmesin — mekanik kapı."""

    def test_tekrar_yok(self):
        tum = cn.YARGI_YERLERI + cn.BILESIK_YARGI_YERLERI
        tekrar = sorted({ad for ad in tum if tum.count(ad) > 1})
        assert tekrar == []

    def test_kanonik_yazim(self):
        for ad in cn.YARGI_YERLERI + cn.BILESIK_YARGI_YERLERI:
            assert ad == ad.strip(), ad
            assert "  " not in ad, ad
            assert len(ad) >= 3, ad
            assert not any(ch.isdigit() or ch == "." for ch in ad), ad

    def test_kurum_kelimesi_sozluge_girmemis(self):
        # KISMI kalan değerlerin bir kısmı yer değil TÜR/dolgu eksiğidir
        # (savcılık, icra müdürlüğü, arabuluculuk bürosu, nöbetçi...). Bunlar
        # sözlüğe ÇÖZÜM diye yazılamaz: yer değiller.
        yasak = (
            "CUMHURİYET", "NÖBETÇİ", "BAŞSAVCILIĞI", "SAVCILIĞI", "MÜDÜRLÜĞÜ",
            "ARABULUCULUK", "BÜROSU", "ADLİYESİ", "MAHKEMESİ", "HEYETİ",
            "NOTERLİĞİ", "TAHKİM", "SİGORTA",
        )
        for ad in cn.YARGI_YERLERI + cn.BILESIK_YARGI_YERLERI:
            for kelime in yasak:
                assert kelime not in ad.split(), f"{ad} içinde kurum kelimesi: {kelime}"

    def test_kisaltma_ve_yazim_bozulmasi_girmemis(self):
        # Aynı yargı yerine İKİNCİ kimlik açacak yazımlar bilinçle dışarıda
        # (bkz. modüldeki bakım kuralı). Varyant→kanonik eşlemesi ayrı görev.
        for bozuk in ("İSTANBUL AND", "EREĞLİ KDZ", "BAKİRKÖY", "DİYARBAKİR",
                      "ŞANLİURFA", "KADİKÖY", "AFYON"):
            assert bozuk not in cn.YARGI_YERLERI
            assert bozuk not in cn.BILESIK_YARGI_YERLERI


class TestKarsiOrneklerYesilKaliyor:
    """G067 sızıntı kilitleri sözlük büyüdükten SONRA da geçerli."""

    @pytest.mark.parametrize(
        "metin,sizmamasi_gereken",
        [
            ("TATVAN 2. ASLİYE HUKUK MAHKEMESİ", "VAN"),
            ("GELİBOLU 1. ASLİYE HUKUK MAHKEMESİ", "BOLU"),
            ("SAFRANBOLU 1. ASLİYE HUKUK MAHKEMESİ", "BOLU"),
            ("İNEBOLU 1. ASLİYE HUKUK MAHKEMESİ", "BOLU"),
            ("BAĞRI 1. ASLİYE HUKUK MAHKEMESİ", "AĞRI"),
        ],
    )
    def test_uzun_ad_kisa_ile_karismiyor(self, metin, sizmamasi_gereken):
        kimlik = parse_court_name(metin, yerler=_ILLER)
        assert kimlik is not None
        assert kimlik.yer != sizmamasi_gereken

    @pytest.mark.parametrize(
        "metin",
        [
            "BAYATLI 1. ASLİYE HUKUK MAHKEMESİ",     # BAYAT
            "BELİCE 1. ASLİYE HUKUK MAHKEMESİ",      # LİCE
            "KEMERBURGAZ 1. ASLİYE HUKUK MAHKEMESİ",  # KEMER
            "FATİHLER 1. ASLİYE HUKUK MAHKEMESİ",    # FATİH
            "BUCAKLI 1. ASLİYE HUKUK MAHKEMESİ",     # BUCAK
        ],
    )
    def test_yeni_adlar_kelime_icinde_eslesmiyor(self, metin):
        # G070'te giren kısa adlar sözlüğü büyüttü; kelime sınırı korunuyor mu.
        kimlik = parse_court_name(metin, yerler=_ILLER)
        assert kimlik is not None
        assert kimlik.yer is None

    def test_kocaali_kocaeliyi_gasp_etmiyor(self):
        # Bir harf farkla ayrılan iki ayrı yargı yeri (Sakarya/Kocaali · Kocaeli).
        assert parse_court_name("KOCAELİ 1. ASLİYE HUKUK MAHKEMESİ", yerler=_ILLER).yer == "KOCAELİ"
        assert parse_court_name("KOCAALİ 8. İCRA MÜDÜRLÜĞÜ", yerler=_ILLER).yer == "KOCAALİ"

    def test_bilesik_ad_kisa_adi_yeniyor(self):
        # "İSTANBUL ANADOLU" sözlük büyüdükten sonra da "İSTANBUL"a düşmüyor.
        kimlik = parse_court_name("İSTANBUL ANADOLU 6. TÜKETİCİ MAHKEMESİ", yerler=_ILLER)
        assert kimlik.yer == "İSTANBUL ANADOLU"
