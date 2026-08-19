"""G069 — üst mahkeme boşluğu: Yargıtay daireleri Bölge Adliye'ye yazılıyordu.

Ölçüm (2026-08-19, değişiklikten ÖNCE, konteynerde `derive_judicial_unit`):

    Yargıtay 11. Hukuk Dairesi   → BÖLGE ADLİYE MAH. HUKUK DAİRESİ   (yanlış)
    Yargıtay 9. Ceza Dairesi     → BÖLGE ADLİYE MAH. CEZA DAİRESİ    (yanlış)
    Yargıtay Hukuk Genel Kurulu  → None                              (eksik)
    Danıştay 10. Dairesi         → DANIŞTAY                          (doğru)
    İstanbul BAM 43. Hukuk Dai.  → BÖLGE ADLİYE MAH. HUKUK DAİRESİ   (doğru)

Bugün latent (Yargıtay taşıyan 0 kart), FAZ F temyiz/istinaf aşamalarını kartlara
yazmaya başladığında her temyiz kararı istinaf mercii olarak sınıflanırdı.

Kanonik ad kararı (G069): tek "YARGITAY" değil, Bölge Adliye ile SİMETRİK bir çift —
`YARGITAY HUKUK DAİRESİ` / `YARGITAY CEZA DAİRESİ`. Gerekçe: judicial_unit bir yargı
BİRİMİ (court_types) alanıdır ve her değer TEK `parent_code` taşır; Yargıtay hem hukuk
hem ceza dairesi barındırdığı için tek değer parent'ı keyfî seçmeye zorlardı. Danıştay'ın
tek değer olması bir adlandırma geleneği değil, tümüyle İdari Yargı'da olmasının sonucudur.
"""
import pytest

from managers.seed_data import COURT_TYPES_SEED
from services.court_name import parse_court_name
from services.judicial_unit import PATTERNS, derive_judicial_unit, normalize_court

YARGITAY_HUKUK = "YARGITAY HUKUK DAİRESİ"
YARGITAY_CEZA = "YARGITAY CEZA DAİRESİ"
BAM_HUKUK = "BÖLGE ADLİYE MAH. HUKUK DAİRESİ"
BAM_CEZA = "BÖLGE ADLİYE MAH. CEZA DAİRESİ"


# ── Görev dosyasındaki 5 ölçüm satırı ────────────────────────────────────────

class TestOlculmusKusurlar:
    @pytest.mark.parametrize(
        "court, beklenen",
        [
            ("Yargıtay 11. Hukuk Dairesi", YARGITAY_HUKUK),
            ("Yargıtay 9. Ceza Dairesi", YARGITAY_CEZA),
            ("Yargıtay Hukuk Genel Kurulu", YARGITAY_HUKUK),
            ("Danıştay 10. Dairesi", "DANIŞTAY"),
            ("İstanbul BAM 43. Hukuk Dairesi", BAM_HUKUK),
        ],
    )
    def test_olcum_satiri(self, court, beklenen):
        assert derive_judicial_unit(court) == beklenen

    @pytest.mark.parametrize(
        "court",
        [
            "Yargıtay 11. Hukuk Dairesi",
            "Yargıtay 9. Ceza Dairesi",
            "Yargıtay Hukuk Genel Kurulu",
            "Yargıtay Ceza Genel Kurulu",
            "YARGITAY 8. CD",
            "Yargıtay 4. HD",
        ],
    )
    def test_temyiz_mercii_istinafa_yazilmaz(self, court):
        """Asıl kusur: temyiz (Yargıtay) → istinaf (Bölge Adliye) sızması."""
        birim = derive_judicial_unit(court)
        assert birim is not None
        assert "BÖLGE ADLİYE" not in birim
        assert birim.startswith("YARGITAY ")

    @pytest.mark.parametrize(
        "court, beklenen",
        [
            ("Yargıtay Ceza Genel Kurulu", YARGITAY_CEZA),
            ("Yargıtay Büyük Genel Kurulu (Hukuk)", YARGITAY_HUKUK),
            ("YARGITAY 8. CD", YARGITAY_CEZA),
            ("Yargıtay 4. HD", YARGITAY_HUKUK),
        ],
    )
    def test_genel_kurul_ve_kisaltma(self, court, beklenen):
        """Genel kurullar kendi tarafındaki (hukuk/ceza) Yargıtay birimine düşer."""
        assert derive_judicial_unit(court) == beklenen

    def test_hukuk_ceza_isareti_yoksa_uydurulmaz(self):
        """Tahmin yasağı: taraf belli değilse parent seçilemez → değer ÜRETİLMEZ."""
        assert derive_judicial_unit("Yargıtay Başkanlığı") is None
        assert derive_judicial_unit("Yargıtay İçtihadı Birleştirme Genel Kurulu") is None


# ── Regresyon: istinaf / BAM / Bölge Adliye vakaları BOZULMADI ───────────────

class TestIstinafRegresyonu:
    @pytest.mark.parametrize(
        "court, beklenen",
        [
            ("İstanbul BAM 43. Hukuk Dairesi", BAM_HUKUK),
            ("İstanbul Bölge Adliye Mahkemesi 2. Ceza Dairesi", BAM_CEZA),
            ("Ankara Bölge Adliye Mahkemesi 24. Hukuk Dairesi", BAM_HUKUK),
            ("İstinaf 3. Hukuk Dairesi", BAM_HUKUK),
            ("İzmir BAM 5. Ceza Dairesi", BAM_CEZA),
            ("2. Hukuk Dairesi", BAM_HUKUK),
            ("Ankara 5. Asliye Hukuk Mahkemesi", "ASLİYE HUKUK MAHKEMESİ"),
            ("Bursa 4. Sulh Ceza Hâkimliği", "SULH CEZA HAKİMLİĞİ"),
            ("Ankara 5. İcra Dairesi", "İCRA DAİRESİ"),
            ("Danıştay 10. Dairesi", "DANIŞTAY"),
        ],
    )
    def test_mevcut_vaka_degismedi(self, court, beklenen):
        assert derive_judicial_unit(court) == beklenen

    def test_yargitay_atfi_ilk_derece_turunu_bozmaz(self):
        """Karar metninde geçen Yargıtay atfı mahkemenin KENDİ türünü ezmemeli."""
        assert derive_judicial_unit(
            "Ankara 5. Asliye Hukuk Mahkemesi (Yargıtay bozması sonrası)"
        ) == "ASLİYE HUKUK MAHKEMESİ"


# ── Kalıp sırası: özgül (Yargıtay) → genel (…DAİRESİ) ───────────────────────

class TestKalipSirasi:
    def test_yargitay_genel_daire_alternatifinden_once(self):
        adlar = [ad for _rx, ad, _parent in PATTERNS]
        for yargitay, bam in ((YARGITAY_HUKUK, BAM_HUKUK), (YARGITAY_CEZA, BAM_CEZA)):
            assert adlar.index(yargitay) < adlar.index(bam)


# ── İki katman çelişmiyor: court_name kanonik çıktısı (G067 kapısı) ─────────

class TestKatmanlarUyumlu:
    @pytest.mark.parametrize(
        "ad", ["YARGITAY 11. HUKUK DAİRESİ", "YARGITAY 9. CEZA DAİRESİ", "YARGITAY 8. CD"]
    )
    def test_court_name_yargitayi_bam_saymaz(self, ad):
        kimlik = parse_court_name(ad)
        assert kimlik is not None
        # court_name üst mahkemeyi KURUM kimliği olarak okur (UST_MAHKEMELER dalı)
        assert kimlik.tur_kanonik == "YARGITAY"
        assert derive_judicial_unit(ad).startswith("YARGITAY ")

    def test_bam_dairesi_her_iki_katmanda_bam(self):
        ad = "İSTANBUL BÖLGE ADLİYE MAHKEMESİ 43. HUKUK DAİRESİ"
        assert parse_court_name(ad).tur_kanonik == BAM_HUKUK
        assert derive_judicial_unit(ad) == BAM_HUKUK

    def test_bam_kisaltmasi_kanonik_disi_kaliyor(self):
        """Mevcut davranış (G069 KAPSAMI DIŞI): derive_judicial_unit BAM'da HD/CD
        kısaltmasını açmaz — "BÖLGE ADLİYE" tek başına hukuk/ceza tarafını söylemez.
        court_name kısaltmayı ÖNCE açtığı için oradan kanonik değer gelir."""
        ad = "İSTANBUL BÖLGE ADLİYE MAHKEMESİ 43. HD"
        assert parse_court_name(ad).tur_kanonik == BAM_HUKUK
        assert derive_judicial_unit(ad) is None


# ── court_types sözlüğü: üretilen HER kanonik değerin karşılığı olmalı ──────

class TestSozlukKapsami:
    def test_her_kanonik_deger_seedde_var(self):
        seedde = {
            normalize_court(ad) for adlar in COURT_TYPES_SEED.values() for ad in adlar
        }
        eksik = sorted(
            {ad for _rx, ad, _parent in PATTERNS if normalize_court(ad) not in seedde}
        )
        assert eksik == []

    @pytest.mark.parametrize(
        "ad, parent", [(YARGITAY_HUKUK, "Hukuk"), (YARGITAY_CEZA, "Ceza")]
    )
    def test_yeni_deger_dogru_parent_altinda(self, ad, parent):
        assert ad in COURT_TYPES_SEED[parent]
        parent_by_name = {n: p for _rx, n, p in PATTERNS}
        assert parent_by_name[ad] == parent

    def test_ilk_derece_girdisi_ayri_kaldi(self):
        """Yargıtay'ın ilk derece sıfatı ayrı bir birimdir; yeni değer onu EZMEZ."""
        assert "YARGITAY CEZA DAİRESİ (İLK DERECE)" in COURT_TYPES_SEED["Ceza"]
        assert YARGITAY_CEZA in COURT_TYPES_SEED["Ceza"]
