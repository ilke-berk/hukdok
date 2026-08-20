"""Aynı dava / mükerrer kart raporu — `scripts/mukerrer_kart_raporu.py`.

Script SALT OKUNURDUR: hiçbir tabloya yazmaz, hiçbir kartı birleştirmez. Testler
raporun karar verdirici üç kolonunu kilitler:

* `isim_blogu` — ofis numarasından müvekkil bloğu çıkarımı
* `hukum` — bu iki kart gerçekten mükerrer mi, yoksa AYRI durmaları mı doğru
  (hasar dosya numarası → sigortalı hekim → karşı taraf sırasıyla)
* geçişli gruplama — A-B ve B-C aynı davaysa grup {A, B, C} olmalı

"Aynı dava" hükmü scriptte tekrar edilmez; `services.case_relations_auto`tan
gelir (panelin AYNI_DAVA rozetiyle tek kaynak) — o taraf
`test_iliskili_dava_otomatik.py`de test edilir.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mukerrer_kart_raporu as rapor  # noqa: E402


def _taraf(name, party_type):
    return SimpleNamespace(name=name, party_type=party_type)


def _kart(tracking_no, *taraflar):
    return SimpleNamespace(tracking_no=tracking_no, parties=list(taraflar))


# ── isim bloğu ────────────────────────────────────────────────────────────────

def test_isim_blogu_ofis_numarasindan_cikiyor():
    assert rapor._isim_blogu("D1.B_GURER....0001.IDARE.00000") == "B_GURER..."
    assert rapor._isim_blogu("S3.AXA........2967.IDARE.00000") == "AXA......."


@pytest.mark.parametrize("bozuk", ["", "D1.KISA", None])
def test_kisa_veya_bos_ofis_numarasi_bos_blok_verir(bozuk):
    """Boş blok eşleşme üretmemeli: aksi hâlde bütün bozuk numaralı kartlar
    birbirinin mükerreri sayılırdı (rapor bu yüzden boş bloğu atlıyor)."""
    assert rapor._isim_blogu(bozuk) == ""


# ── hüküm: mükerrer mi, ayrı durması mı doğru ─────────────────────────────────

def _hekim_karti(ad, karsi="Songül Kaya"):
    return _kart("X", _taraf("Ak Sigorta A.Ş.", "CLIENT"), _taraf(karsi, "COUNTER"),
                 _taraf(ad, "THIRD"), _taraf("Bezmialem Vakıf Üniversitesi Hastanesi", "THIRD"))


def test_ayni_taraflar_mukerrer_adayidir():
    sol, sag = _hekim_karti("Murat Özcan Dr."), _hekim_karti("Murat Özcan Dr.")
    assert rapor._hukum(sol, sag, {"15902623"}, {"15902623"}) == "MUKERRER_ADAYI"


def test_farkli_hasar_dosyasi_her_seyin_onunde_gelir():
    """Canlı vaka TKU-80: İstanbul 9. İdare 2020/550 altında iki kart, hasar
    3745261180001 (dört hekim) ve 6528666170001 (Engin Can Dr.). Karşı taraf
    'Abdukadir' ↔ 'Abdulkadir' yazılmış — isme bakan bir hüküm yanılırdı."""
    sol = _hekim_karti("Anas Abdelrahim Saleh Dr.", karsi="Abdukadir Tunçel")
    sag = _hekim_karti("Engin Can Dr.", karsi="Abdulkadir Tunçel")
    assert rapor._hukum(sol, sag, {"3745261180001"}, {"6528666170001"}) \
        == "FARKLI_HASAR_DOSYASI"


def test_farkli_sigortali_hekim_mukerrer_degildir():
    """Aynı davada her sigortalı hekim için ayrı kart açılmışsa bu doğru kayıttır."""
    sol, sag = _hekim_karti("Nadir Yıldırım Dr."), _hekim_karti("Semra Külekçi Dr.")
    assert rapor._hukum(sol, sag, set(), set()) == "FARKLI_SIGORTALI"


def test_ortak_hastane_farkli_hekimi_gizlemiyor():
    """Hastane/bakanlık onlarca davanın ortak davalısıdır; kurum kesişimi
    'aynı hekim' sanılırsa iki ayrı hekim dosyası mükerrer ilan edilirdi."""
    sol = _kart("A", _taraf("Nadir Yıldırım Dr.", "THIRD"), _taraf("Sağlık Bakanlığı", "THIRD"),
                _taraf("Songül Kaya", "COUNTER"))
    sag = _kart("B", _taraf("Semra Külekçi Dr.", "THIRD"), _taraf("Sağlık Bakanlığı", "THIRD"),
                _taraf("Songül Kaya", "COUNTER"))
    assert rapor._hukum(sol, sag, set(), set()) == "FARKLI_SIGORTALI"


def test_farkli_karsi_taraf_esas_no_hatasina_isaret_eder():
    """Canlı vaka: Gaziantep 2. Tüketici 2017/1210 — aynı mahkeme + aynı esas,
    ama biri 'Çeliksoy' diğeri 'Oğul' davalı. Mükerrer değil, veri hatası."""
    sol = _kart("A", _taraf("Ahmet Çeliksoy", "COUNTER"), _taraf("Hamide Çeliksoy", "COUNTER"))
    sag = _kart("B", _taraf("Bekir Oğul", "COUNTER"))
    assert rapor._hukum(sol, sag, set(), set()) == "KARSI_TARAF_FARKLI"


def test_yazim_farki_ayni_tarafi_ayirmiyor():
    """normalize_party_key üzerinden: büyük-küçük ve aksan farkı sahte ayrım
    üretmemeli (canlı örnek: 'Birgül' ↔ 'BİRGÜL')."""
    sol, sag = _hekim_karti("Birgül Akkaya"), _hekim_karti("BİRGÜL AKKAYA")
    assert rapor._hukum(sol, sag, set(), set()) == "MUKERRER_ADAYI"


def test_bir_tarafta_hic_hekim_yoksa_hukum_verilmez():
    """Yalnız hastane/bakanlık kayıtlıysa karşılaştırma YAPILAMADI demektir;
    'mükerrer adayı' saymak ölçmediğimizi bulgu gibi göstermek olurdu."""
    sol = _hekim_karti("Gürcan Akgül Dr.")
    sag = _kart("B", _taraf("Sağlık Bakanlığı", "THIRD"), _taraf("Songül Kaya", "COUNTER"))
    assert rapor._hukum(sol, sag, set(), set()) == "SIGORTALI_KARSILASTIRILAMADI"


def test_hasar_numarasi_tek_tarafta_varsa_ayrac_calismaz():
    """Bir kartta hasar no yok: 'ayrık' demek için iki taraf da dolu olmalı."""
    sol, sag = _hekim_karti("Murat Özcan Dr."), _hekim_karti("Murat Özcan Dr.")
    assert rapor._hukum(sol, sag, {"15902623"}, set()) == "MUKERRER_ADAYI"


def test_muvekkil_karsi_taraf_sigortali_ayri_kolonlara_gidiyor():
    kart = _kart(
        "A",
        _taraf("Ak Sigorta A.Ş.", "CLIENT"),
        _taraf("Songül Kaya", "COUNTER"),
        _taraf("Murat Özcan Dr.", "THIRD"),
    )
    assert rapor._muvekkil(kart) == "Ak Sigorta A.Ş."
    assert rapor._karsi_taraf(kart) == "Songül Kaya"
    assert rapor._sigortali(kart) == "Murat Özcan Dr."


@pytest.mark.parametrize("kurum", [
    "Bezmialem Vakıf Üniversitesi Tıp Fakültesi Hastanesi", "Sağlık Bakanlığı",
    "Özel Medova Hastanesi", "Ege Üniversitesi", "Anadolu Anonim Türk Sigorta Şirketi",
    "Türkiye Kamu Hastaneleri Kurumu",
])
def test_kurumlar_kisi_sayilmiyor(kurum):
    assert rapor._kisi_adlari([kurum]) == []


@pytest.mark.parametrize("kisi", ["Murat Özcan Dr.", "Semra Külekçi", "Anas Abdelrahim Saleh Dr."])
def test_hekimler_kisi_sayiliyor(kisi):
    assert rapor._kisi_adlari([kisi]) == [kisi]


# ── geçişli gruplama ──────────────────────────────────────────────────────────

def test_gecisli_ciftler_tek_grupta_toplaniyor():
    """TKU-1230 deseni: üç kart üç çift üretir, grup TEK olmalı."""
    gruplar, _ = rapor.gruplari_kur([(803, 804, "TKU-1230"), (803, 805, "TKU-1230"),
                                     (804, 805, "TKU-1230")])
    assert [sorted(u) for u in gruplar.values()] == [[803, 804, 805]]


def test_zincir_halinde_gelen_ciftler_birlesiyor():
    """A-B önce, B-C sonra: ikinci çift iki ayrı grubu birleştirmeli."""
    gruplar, kanitlar = rapor.gruplari_kur(
        [(1, 2, "esas+mahkeme"), (3, 4, "TKU-9"), (2, 3, "TKU-9")]
    )
    assert [sorted(u) for u in gruplar.values()] == [[1, 2, 3, 4]]
    # Birleşen grupların kanıtları da taşınır, düşmez.
    (grup_id,) = gruplar.keys()
    assert kanitlar[grup_id] == {"esas+mahkeme", "TKU-9"}


def test_iliskisiz_ciftler_ayri_gruplarda_kaliyor():
    gruplar, _ = rapor.gruplari_kur([(1, 2, "TKU-1"), (3, 4, "TKU-2")])
    assert sorted(sorted(u) for u in gruplar.values()) == [[1, 2], [3, 4]]
