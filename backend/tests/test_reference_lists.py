"""tr_upper — referans listesi isim normalizasyonu birim testleri."""
from managers.reference_lists import tr_upper


def test_tr_upper_noktali_i():
    # str.upper() 'i'yi 'I' yapar; Türkçe'de 'İ' olmalı
    assert tr_upper("istinaf") == "İSTİNAF"
    assert tr_upper("hasta") == "HASTA"


def test_tr_upper_noktasiz_i():
    assert tr_upper("ılık") == "ILIK"
    assert tr_upper("kırşehir") == "KIRŞEHİR"


def test_tr_upper_diger_turkce_harfler():
    assert tr_upper("özel müvekkil") == "ÖZEL MÜVEKKİL"
    assert tr_upper("çağrı") == "ÇAĞRI"


def test_tr_upper_bosluk_normalizasyonu():
    assert tr_upper("  dr   özel  ") == "DR ÖZEL"


def test_tr_upper_zaten_buyuk():
    assert tr_upper("HASTANE ÖZEL MÜVEKKİL") == "HASTANE ÖZEL MÜVEKKİL"
