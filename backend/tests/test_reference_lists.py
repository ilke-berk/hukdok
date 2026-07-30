"""Referans listesi birim testleri: isim normalizasyonu + bağımlılık haritası tutarlılığı."""
from managers.reference_lists import (
    DEPENDENCIES, LIST_REGISTRY, _name_variants, resolve_list_type, tr_title, tr_upper,
)


# tr_upper yalnızca harf duyarsız karşılaştırma için kullanılır
def test_tr_upper_noktali_i():
    assert tr_upper("istinaf") == "İSTİNAF"
    assert tr_upper("hasta") == "HASTA"


def test_tr_upper_noktasiz_i():
    assert tr_upper("ılık") == "ILIK"
    assert tr_upper("kırşehir") == "KIRŞEHİR"


def test_tr_upper_bosluk_normalizasyonu():
    assert tr_upper("  dr   özel  ") == "DR ÖZEL"


# tr_title saklama formatı: her kelimenin ilk harfi büyük, kalanı küçük
def test_tr_title_temel():
    assert tr_title("hastane özel müvekkil") == "Hastane Özel Müvekkil"
    assert tr_title("HASTANE ÖZEL MÜVEKKİL") == "Hastane Özel Müvekkil"


def test_tr_title_noktali_i():
    # kelime başındaki 'i' → 'İ', kelime içindeki 'İ' → 'i'
    assert tr_title("istinaf") == "İstinaf"
    assert tr_title("BİLİRKİŞİDE") == "Bilirkişide"


def test_tr_title_noktasiz_i():
    assert tr_title("ılık") == "Ilık"
    assert tr_title("KIRŞEHİR") == "Kırşehir"


def test_tr_title_diger_turkce_harfler():
    assert tr_title("çağrı özel") == "Çağrı Özel"
    assert tr_title("ÜROLOJİ") == "Üroloji"


def test_tr_title_bosluk_normalizasyonu():
    assert tr_title("  dr   özel  ") == "Dr Özel"


# _name_variants: eski kayıtlar aynı değeri BÜYÜK HARFLE saklamış olabiliyor
def test_name_variants_buyuk_kucuk_kapsar():
    variants = _name_variants("Doktor")
    assert "DOKTOR" in variants and "doktor" in variants and "Doktor" in variants


def test_name_variants_turkce_harf():
    # "İstanbul" için ASCII upper() 'İSTANBUL' üretemez; tr_upper şart
    assert "İSTANBUL" in _name_variants("İstanbul")


def test_resolve_list_type():
    assert resolve_list_type("email_recipients") == "emails"   # takma ad
    assert resolve_list_type("statuses") == "statuses"
    assert resolve_list_type("olmayan_liste") is None


# ─── Bağımlılık haritası tutarlılığı ─────────────────────────────────────────
# Yeni bir liste eklenip DEPENDENCIES'e yazılmazsa yeniden adlandırma sessizce
# bağlı kayıtları güncellemez — bu testler o sessiz kopmayı yakalar.

def test_her_liste_icin_bagimlilik_tanimli():
    assert set(DEPENDENCIES) == set(LIST_REGISTRY)


def test_bagimli_kolonlar_modelde_var():
    for list_type, deps in DEPENDENCIES.items():
        for dep in deps:
            assert hasattr(dep.model, dep.column), f"{list_type}: {dep.model.__name__}.{dep.column} yok"
            if dep.code_column:
                assert hasattr(dep.model, dep.code_column), f"{list_type}: {dep.code_column} yok"


def test_duzenlenebilir_alanlar_modelde_var():
    for list_type, spec in LIST_REGISTRY.items():
        for field in spec.editable:
            assert hasattr(spec.model, field), f"{list_type}: {field} kolonu yok"


def test_not_null_kolonlar_bosaltilabilir_isaretlenmemis():
    # clearable=True olan bir NOT NULL kolonu silmede IntegrityError'a düşerdi
    for list_type, deps in DEPENDENCIES.items():
        for dep in deps:
            column = getattr(dep.model, dep.column).property.columns[0]
            if not column.nullable:
                assert not dep.clearable, f"{list_type}: {dep.column} NOT NULL ama clearable=True"
