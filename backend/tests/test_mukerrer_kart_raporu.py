"""Aynı dava / mükerrer kart raporu — `scripts/mukerrer_kart_raporu.py`.

Script SALT OKUNURDUR: hiçbir tabloya yazmaz, hiçbir kartı birleştirmez. Testler
raporun karar verdirici üç kolonunu kilitler:

* `isim_blogu` — ofis numarasından müvekkil bloğu çıkarımı
* `karsi_taraf_ortak` — mükerrer kayıt mı, yoksa esas numarası yanlış girilmiş
  İKİ AYRI dava mı (canlı örnek: Gaziantep 2. Tüketici 2017/1210 kartlarından
  biri 'Çeliksoy', diğeri 'Oğul' davalı)
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


# ── karşı taraf ayracı ────────────────────────────────────────────────────────

def test_ayni_karsi_taraf_mukerrer_adayidir():
    sol = _kart("A", _taraf("Songül Kaya", "COUNTER"))
    sag = _kart("B", _taraf("Songül Kaya", "COUNTER"))
    assert rapor._karsi_taraf_ortak(sol, sag) == "EVET"


def test_farkli_karsi_taraf_esas_no_hatasina_isaret_eder():
    """Canlı vaka: aynı mahkeme + aynı esas, ama davalılar bambaşka."""
    sol = _kart("A", _taraf("Ahmet Çeliksoy", "COUNTER"), _taraf("Hamide Çeliksoy", "COUNTER"))
    sag = _kart("B", _taraf("Bekir Oğul", "COUNTER"))
    assert rapor._karsi_taraf_ortak(sol, sag) == "HAYIR"


def test_yazim_farki_ayni_tarafi_ayirmiyor():
    """Karşılaştırma normalize_party_key üzerinden: büyük-küçük ve aksan farkı
    sahte 'HAYIR' üretmemeli (canlı örnek: 'Birgül' ↔ 'BİRGÜL')."""
    sol = _kart("A", _taraf("Birgül Akkaya", "COUNTER"))
    sag = _kart("B", _taraf("BİRGÜL AKKAYA", "COUNTER"))
    assert rapor._karsi_taraf_ortak(sol, sag) == "EVET"


def test_taraf_bilgisi_eksikse_hukum_verilmez():
    sol = _kart("A", _taraf("Songül Kaya", "COUNTER"))
    sag = _kart("B", _taraf("Ak Sigorta A.Ş.", "CLIENT"))  # karşı taraf satırı yok
    assert rapor._karsi_taraf_ortak(sol, sag) == "BILINMIYOR"


def test_muvekkil_ve_karsi_taraf_ayri_kolonlara_gidiyor():
    kart = _kart(
        "A",
        _taraf("Ak Sigorta A.Ş.", "CLIENT"),
        _taraf("Songül Kaya", "COUNTER"),
        _taraf("Murat Özcan Dr.", "THIRD"),
    )
    assert rapor._muvekkil(kart) == "Ak Sigorta A.Ş."
    assert rapor._karsi_taraf(kart) == "Songül Kaya"


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
