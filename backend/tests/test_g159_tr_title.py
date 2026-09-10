"""G159 — `tr_title` DB-008 yazım standardı + `sub_type` yazım farkında paket kazanır.

Plan 08.09 §5 (kullanıcı onayı 08.09): naif kelime-başı büyütme 4.521 kartta
"… Ve …", 3.209 taraf satırında "A.ş.", konuda "(tıbbi" üretiyordu. Ekibin
DB-008 kuralı: bağlaç küçük (ve, ile), kısaltma korunur (A.Ş. · Dr. · T.C.),
parantez/tire/bölü sonrası büyük, yabancı adda I/ı kuralı yok (QUICK → Quick).

Plan §1.3 M6: `sub_type` yazım farkında da paket yazar (biçim `tr_title`ın),
`court` içerik modunda kalır (mahkeme adı kimliği bizim, G067-G070).
"""
import pytest

import models
from managers.reference_lists import BAGLACLAR, KISALTMALAR, normalize_list_name, tr_title
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import DuzeltmeKaydi, HamSatir, aktarimi_kos
from tests import test_g064_aktarim_cekirdek as g064
from tests.test_g064_aktarim_cekirdek import BASLIKLAR, _paket_yaz, _satir

db_env = g064.db_env
uc_kart = g064.uc_kart


# ═══════════════════════════════════════════════════════════════════════════
# 1. tr_title — DB-008 tablosu
# ═══════════════════════════════════════════════════════════════════════════

TABLO = [
    # görev tablosu (G159 §4)
    ("KADIN HASTALIKLARI VE DOĞUM", "Kadın Hastalıkları ve Doğum"),
    ("AK SİGORTA A.Ş.", "Ak Sigorta A.Ş."),
    ("TAZMİNAT (TIBBİ HATA)", "Tazminat (Tıbbi Hata)"),
    ("DR ÖZEL", "Dr Özel"),
    ("QUICK SİGORTA", "Quick Sigorta"),
    ("YARGITAY 3. HD", "Yargıtay 3. HD"),
    ("T.C. SAĞLIK BAKANLIĞI", "T.C. Sağlık Bakanlığı"),
    ("ali VELİ", "Ali Veli"),
    # bağlaç: ilk kelime hariç küçük; "vb." nokta soyularak tanınır
    ("ÇOCUK SAĞLIĞI VE HASTALIKLARI", "Çocuk Sağlığı ve Hastalıkları"),
    ("HASTA İLE HEKİM", "Hasta ile Hekim"),
    ("ANNE VEYA BABA ADINA", "Anne veya Baba adına"),
    ("VE DİĞERLERİ", "Ve Diğerleri"),
    ("tıbbi cihaz vb.", "Tıbbi Cihaz vb."),
    # noktalı kısaltma ("X.Y." deseni) tamamı büyük; olağan kısa kelimeler değil
    ("ak sigorta a.ş.", "Ak Sigorta A.Ş."),
    ("K.H. ÖZEL HASTANESİ", "K.H. Özel Hastanesi"),
    ("ÖZEL SAĞLIK LTD. ŞTİ.", "Özel Sağlık Ltd. Şti."),
    ("AV. AHMET YILMAZ", "Av. Ahmet Yılmaz"),
    ("M. ALİ", "M. Ali"),
    # bilinen 2-3 harfli kısaltma kanonik yazımıyla; marka adı listede DEĞİL
    ("yargıtay 13. hd", "Yargıtay 13. HD"),
    ("İSTANBUL BAM 5. HD", "İstanbul BAM 5. HD"),
    ("TCK 85 (TAKSİRLE ÖLDÜRME)", "TCK 85 (Taksirle Öldürme)"),
    ("HDI SİGORTA A.Ş.", "HDI Sigorta A.Ş."),
    ("AXA SİGORTA A.Ş.", "Axa Sigorta A.Ş."),
    # kelime sınırı: boşluk + `(` `-` `/`
    ("RED/ESASTAN", "Red/Esastan"),
    ("DAVALI-DAVACI", "Davalı-Davacı"),
    ("KABUL/KISMEN", "Kabul/Kısmen"),
    # yabancı ad: I → i (Türkçede olmayan harf ya da I'nın ünlüye komşuluğu)
    ("Quıck Sigorta A.ş", "Quick Sigorta A.Ş"),
    ("ALLIANZ SİGORTA", "Allianz Sigorta"),
    # Türkçe I/ı kuralı yerinde
    ("IŞIK", "Işık"),
    ("KIRŞEHİR İDARE", "Kırşehir İdare"),
    ("istinaf", "İstinaf"),
    # boşluk normalizasyonu + harfsiz parçalar
    ("  dr   özel  ", "Dr Özel"),
    ("2023/1660", "2023/1660"),
    ("", ""),
]


@pytest.mark.parametrize("ham,beklenen", TABLO)
def test_tr_title_db008_tablosu(ham, beklenen):
    assert tr_title(ham) == beklenen


@pytest.mark.parametrize("ham,_beklenen", TABLO)
def test_tr_title_idempotent(ham, _beklenen):
    bir = tr_title(ham)
    assert tr_title(bir) == bir


@pytest.mark.parametrize("ham,beklenen", TABLO)
def test_normalize_list_name_ve_baslik_bicimli_ayni_fonksiyon(ham, beklenen):
    """Liste adı (`normalize_list_name`) ve kart uzmanlık alanı (`_baslik_bicimli`)
    AYNI yazımı taşır — istisna yok."""
    assert normalize_list_name(ham) == beklenen
    assert hukdok_aktarim._baslik_bicimli(ham, "sub_type") == (beklenen or None)


def test_baglac_ve_kisaltma_kumeleri_bilincli_kucuk():
    """Marka adı (AXA, QUICK) LİSTELENMEZ — kural noktalı desen + bilinen kısaltma."""
    assert {"ve", "ile", "veya", "adına", "vb"} <= BAGLACLAR
    assert {"HD", "İDD", "BİM", "BAM", "HDI", "TCK", "HMK"} <= KISALTMALAR
    assert not {"AXA", "QUICK", "AK"} & KISALTMALAR
    assert all(len(k) <= 3 for k in KISALTMALAR)


# ═══════════════════════════════════════════════════════════════════════════
# 2. sub_type paket kazanır, court içerik modunda
# ═══════════════════════════════════════════════════════════════════════════

def test_icerik_modu_yalniz_court_bosaltma_yasagi_sub_type_ile():
    assert hukdok_aktarim.ICERIK_KARSILASTIRMALI_ALANLAR == {"court"}
    assert hukdok_aktarim.BOSALTMA_YASAK_KART_ALANLARI == {"court", "sub_type"}
    assert hukdok_aktarim.BOSALTMA_YASAK_KART_ALANLARI <= hukdok_aktarim.BOSALTMA_DISI_ALANLAR


def test_sub_type_yazim_farkinda_paket_yazar_court_dokunmaz(uc_kart, tmp_path):
    """D-1: kartta eski `tr_title` biçimi ("… Ve …") + mahkeme adımız; paket aynı
    içeriği BÜYÜK HARF gönderiyor → `sub_type` DB-008 biçimine yazılır,
    `court` bizim yazımımızda kalır. İkinci koşu 0 değişiklik."""
    db = uc_kart()
    try:
        kart = {c.klasor_no_2: c for c in db.query(models.Case).all()}["D-1"]
        kart.court = "Bakırköy 3. Tüketici Mahkemesi"
        kart.sub_type = "Ortopedi Ve Travmatoloji"
        db.commit()
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Yerel Mahkeme": "BAKIRKÖY 3. TÜKETİCİ MAHKEMESİ",
                                    "Dava Türü Alt Kırılımı": "ORTOPEDİ VE TRAVMATOLOJİ"}),
    ], basliklar=BASLIKLAR + ["Yerel Mahkeme", "Dava Türü Alt Kırılımı"])

    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.alan_degisikligi == 1                       # yalnız sub_type

    db = uc_kart()
    try:
        kart = {c.klasor_no_2: c for c in db.query(models.Case).all()}["D-1"]
        assert kart.sub_type == "Ortopedi ve Travmatoloji"   # paket kazandı, DB-008 biçimi
        assert kart.court == "Bakırköy 3. Tüketici Mahkemesi"  # içerik modu: yazım bizim
        tarihce = db.query(models.CaseHistory).count()
    finally:
        db.close()

    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0
    db = uc_kart()
    try:
        assert db.query(models.CaseHistory).count() == tarihce
    finally:
        db.close()


def test_sub_type_bosaltma_talimati_yine_reddedilir():
    """`sub_type` içerik modundan çıktı ama `Düzeltme_Logu` "(boş)" talimatı yine
    uygulanmaz; sebep künye/içerik metniyle KARIŞMAZ."""
    satir = HamSatir(satir_no=2, degerler={"uzmanlik_alani": None, "yerel_mahkeme": None})
    duzeltmeler = {
        ("S-1", "sub_type"): DuzeltmeKaydi(satir_no=3, sistem_no="S-1", alan="sub_type",
                                           yeni=None, bosalt=True, gerekce=None, tarih=None),
        ("S-1", "court"): DuzeltmeKaydi(satir_no=4, sistem_no="S-1", alan="court",
                                        yeni=None, bosalt=True, gerekce=None, tarih=None),
    }
    uygulanabilir, reddedilen = hukdok_aktarim._bosaltma_talimatlari(satir, "S-1", duzeltmeler)
    assert uygulanabilir == []
    sebepler = dict(reddedilen)
    assert sebepler["sub_type"].startswith("boşaltılmadı — uzmanlık alanı boşaltılmaz")
    assert sebepler["court"].startswith("boşaltılmadı — içerik-karşılaştırmalı")
    assert "stage_decisions" not in sebepler["sub_type"]
