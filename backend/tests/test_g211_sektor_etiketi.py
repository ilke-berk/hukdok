"""G211 — Müvekkil `sektor` kolonunun ekrandaki adı "Çalıştığı Kurum" (26.09 kullanıcı kararı:
yalnız etiket). Anahtar `sektor` KALIR: kayıtlı rapor şablonları kolonları anahtarla tutar
(`RaporTanimi.kolonlar` anahtar listesi), etiket değişikliği onları bozmaz.
"""
from services.rapor import registry


def test_muvekkil_sektor_etiketi_calistigi_kurum():
    kolon = registry.KAYNAKLAR["muvekkiller"].kolonlar["sektor"]
    assert kolon.anahtar == "sektor"
    assert kolon.etiket == "Çalıştığı Kurum"


def test_sektor_anahtari_kaynakta_duruyor_eski_etiket_yok():
    kolonlar = registry.KAYNAKLAR["muvekkiller"].kolonlar
    assert "sektor" in kolonlar
    assert all(k.etiket != "Sektör" for k in kolonlar.values())


def test_bagli_kaynaklarda_da_yeni_etiket():
    """`muvekkil.sektor` gibi türetilmiş bağlı kolonlar hedef etiketi taşır; eski ad hiçbir
    kaynakta görünmez."""
    for kaynak in registry.KAYNAKLAR.values():
        for anahtar, kolon in kaynak.kolonlar.items():
            if anahtar.split(".")[-1] == "sektor":
                assert "Sektör" not in kolon.etiket, (kaynak, anahtar)
                assert "Çalıştığı Kurum" in kolon.etiket, (kaynak, anahtar)
