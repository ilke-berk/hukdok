"""G044 — FAZ F şeması: 10 yeni `cases` kolonu + iki kapalı liste + Uzmanlık Alanı.

Kaynak: docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md §1.
Şartname kalemi "11 yeni kolon" diye sayar; on birincisi kolon DEĞİL
`case_esas_numbers` TABLOSUDUR (§1.3) ve G045'in işidir — burada 10 kolon var.

Üç katman:

1. **DB'siz** — model kolonları, migrasyon kaydı, Pydantic şeması, referans
   listesi kaydı. Aktarım "olmayan kolona yazamaz"; kilitlenen şey şemanın
   kendisidir.
2. **sqlite (StaticPool)** — `get_case` okuma yolu: alanlar NULL kabul ediyor mu
   ve dolu değer karta dönüyor mu? Sahte bir session bu soruyu yanıtlayamaz
   (desen `test_tenant_softdelete_semantics.py` ile aynı).
3. **Adlandırma kilidi** — `Dava Türü Alt Kırılımı` → `Uzmanlık Alanı` bir ETİKET
   kararıdır; `cases.sub_type` kolon adı bilinçli KORUNDU. Test kararın iki
   yönünü de tutar ki sonraki bir oturum "rename yapılmamış" diye kolonu
   değiştirmesin.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import Date, Numeric, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS

# Şartname §1.1'in kolon kalemleri (esas tarihçesi HARİÇ — o G045'in tablosu)
FAZ_F_KOLONLARI = [
    "islah_tutari",
    "arsiv_tarihi",
    "istinaf_basvuran_taraf",
    "arabuluculuk_no",
    "arabuluculuk_karar_tarihi",
    "tibbi_surec",
    "tibbi_olay",
    "iddia_edilen_kusur",
    "hastada_olusan_zarar",
    "uygulanan_yontem",
]

# Şartname §1.2: "zaten var, tekrar ekleme" kümesi. Yanlışlıkla ikinci kez
# eklenirse migrasyon patlamaz ama şema iki kaynaklı hâle gelir.
ZATEN_VAR = [
    "karar_duzeltme_esas_no", "karar_duzeltme_karar_no", "karar_duzeltme_tarihi",
    "karar_duzeltme_teblig_tarihi", "karar_duzeltme_aciklama",
    "temyiz_basvuru_tarihi", "temyiz_karar_no", "temyiz_teblig_tarihi",
    "temyiz_eden_durumu", "temyiz_karar_aciklama",
    "istinaf_teblig_tarihi", "kesinlesme_tarihi", "infaz_tarihi", "yeni_esas_no",
]


def _case_column_ops():
    """`("columns", "cases", {...})` op'larındaki kolon → DDL eşlemesi."""
    ops = {}
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == "cases":
            for name, spec in op[2].items():
                ops[name] = spec if isinstance(spec, str) else spec[0]
    return ops


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema — model + migrasyon + Pydantic
# ═══════════════════════════════════════════════════════════════════════════

def test_on_kolon_modelde_tanimli():
    for column in FAZ_F_KOLONLARI:
        assert hasattr(models.Case, column), f"models.Case.{column} yok"


def test_on_kolon_null_kabul_ediyor():
    """Aktarım partiler hâlinde gelecek — "henüz gelmedi" geçerli bir durumdur."""
    for column in FAZ_F_KOLONLARI:
        col = getattr(models.Case, column).property.columns[0]
        assert col.nullable, f"cases.{column} NOT NULL — aktarım kısmi partide patlar"
        assert col.default is None, f"cases.{column} DEFAULT taşıyor — NULL/0 ayrımı kaybolur"


def test_on_kolon_migrasyona_kayitli():
    """Mevcut kurulumlarda kolonlar ancak migrasyonla gelir (create_all alter etmez)."""
    kayitli = _case_column_ops()
    eksik = [c for c in FAZ_F_KOLONLARI if c not in kayitli]
    assert eksik == [], "migrasyona yazılmayan kolonlar: " + ", ".join(eksik)


def test_migrasyon_ddl_tipleri_modelle_uyumlu():
    kayitli = _case_column_ops()
    assert kayitli["islah_tutari"] == "NUMERIC(20,2)"
    assert kayitli["arsiv_tarihi"] == "DATE"
    assert kayitli["arabuluculuk_karar_tarihi"] == "DATE"
    for column in ("istinaf_basvuran_taraf", "arabuluculuk_no", "tibbi_surec",
                   "tibbi_olay", "iddia_edilen_kusur", "hastada_olusan_zarar",
                   "uygulanan_yontem"):
        assert kayitli[column].startswith("VARCHAR("), f"{column}: {kayitli[column]}"

    # Model tarafı: tutar NUMERIC, tarihler DATE
    assert isinstance(models.Case.islah_tutari.property.columns[0].type, Numeric)
    for column in ("arsiv_tarihi", "arabuluculuk_karar_tarihi"):
        assert isinstance(getattr(models.Case, column).property.columns[0].type, Date)


def test_zaten_var_olan_alanlar_mukerrer_eklenmedi():
    """§1.2 kümesi modelde duruyor ve yeni op'a İKİNCİ kez yazılmadı."""
    kayitli = _case_column_ops()
    for column in ZATEN_VAR:
        assert hasattr(models.Case, column), f"models.Case.{column} kaybolmuş"
    # Aynı kolonun iki ayrı "columns" op'unda görünmesi tespit edilemezdi (dict
    # birleşiyor) — bu yüzden op BAŞINA sayılır.
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == "cases":
            cakisan = set(op[2]) & set(FAZ_F_KOLONLARI)
            if cakisan:
                assert cakisan == set(FAZ_F_KOLONLARI), (
                    "FAZ F kolonları birden çok op'a dağılmış: " + ", ".join(sorted(cakisan))
                )
    assert "islah_tutari" in kayitli


def test_case_read_semasi_alanlari_opsiyonel():
    from schemas import CaseRead

    case = CaseRead(id=1, tracking_no="HA.X.0001.2026", status="DERDEST",
                    created_at="2026-08-12T00:00:00")
    for column in FAZ_F_KOLONLARI:
        assert column in CaseRead.model_fields, f"CaseRead.{column} yok"
        assert getattr(case, column) is None, f"CaseRead.{column} varsayılanı None değil"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Okuma yolu — sqlite üzerinde gerçek get_case
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env(monkeypatch):
    """Paylaşılan in-memory sqlite + case_manager.SessionLocal yönlendirmesi."""
    from database import Base
    from managers import case_manager

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    yield SimpleNamespace(sessions=maker, manager=case_manager)
    engine.dispose()


def _yeni_dava(db_env, **fields):
    db = db_env.sessions()
    try:
        case = models.Case(
            tracking_no=fields.pop("tracking_no", "HA.X.0001.2026"),
            status="DERDEST",
            maddi_tazminat=0,
            manevi_tazminat=0,
            **fields,
        )
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def test_bos_alanlar_okuma_yolunda_none_donuyor(db_env):
    case_id = _yeni_dava(db_env)
    result = db_env.manager.get_case(case_id)

    assert result is not None
    for column in FAZ_F_KOLONLARI:
        assert column in result, f"get_case çıktısında {column} yok"
        assert result[column] is None, f"{column} boşken None dönmedi: {result[column]!r}"


def test_dolu_alanlar_okuma_yolundan_donuyor(db_env):
    from datetime import date
    from decimal import Decimal

    case_id = _yeni_dava(
        db_env,
        tracking_no="HA.X.0002.2026",
        islah_tutari=Decimal("15000.50"),
        arsiv_tarihi=date(2024, 3, 14),
        istinaf_basvuran_taraf="Her İki Taraf",
        arabuluculuk_no="2023/1234",
        arabuluculuk_karar_tarihi=date(2023, 11, 2),
        tibbi_surec="Doğum",
        tibbi_olay="Omuz Distosisi",
        iddia_edilen_kusur="Tedavi Hatası",
        hastada_olusan_zarar="Kalıcı Maluliyet",
        uygulanan_yontem="Sezaryen",
    )
    result = db_env.manager.get_case(case_id)

    # Tutar JSON'a float olarak çıkar (hukmedilen_* ile aynı sözleşme)
    assert result["islah_tutari"] == 15000.50
    assert isinstance(result["islah_tutari"], float)
    # Tarihler ISO metin (dava kartındaki diğer tarihlerle aynı biçim)
    assert result["arsiv_tarihi"] == "2024-03-14"
    assert result["arabuluculuk_karar_tarihi"] == "2023-11-02"
    assert result["istinaf_basvuran_taraf"] == "Her İki Taraf"
    assert result["arabuluculuk_no"] == "2023/1234"
    assert result["tibbi_surec"] == "Doğum"
    assert result["tibbi_olay"] == "Omuz Distosisi"
    assert result["iddia_edilen_kusur"] == "Tedavi Hatası"
    assert result["hastada_olusan_zarar"] == "Kalıcı Maluliyet"
    assert result["uygulanan_yontem"] == "Sezaryen"


def test_islah_tutari_sifir_none_ile_karismiyor(db_env):
    """0 ile "girilmedi" ayrı: `if item.x` kısaltması 0'ı NULL'a çevirirdi."""
    from decimal import Decimal

    case_id = _yeni_dava(db_env, tracking_no="HA.X.0003.2026", islah_tutari=Decimal("0"))
    assert db_env.manager.get_case(case_id)["islah_tutari"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 3. İki KAPALI liste — mevcut referans listesi mekanizmasıyla
# ═══════════════════════════════════════════════════════════════════════════

def test_kapali_listeler_registry_de_kayitli():
    from managers.reference_lists import DEPENDENCIES, LIST_REGISTRY, LIST_TITLES

    for key, model, column in (
        ("alleged_faults", models.AllegedFault, "iddia_edilen_kusur"),
        ("appealing_parties", models.AppealingParty, "istinaf_basvuran_taraf"),
    ):
        assert key in LIST_REGISTRY, f"{key} LIST_REGISTRY'de yok"
        assert LIST_REGISTRY[key].model is model
        assert key in LIST_TITLES, f"{key} için Türkçe başlık yok (Excel dışa aktarımı)"
        # Yeniden adlandırma bağlı kayıtlara yayılsın diye DEPENDENCIES şart
        deps = DEPENDENCIES[key]
        assert [(d.model, d.column) for d in deps] == [(models.Case, column)]


def test_her_listenin_dynamicconfig_setteri_var():
    """`refresh_cache` setter'ı getattr ile çağırır — yoksa liste güncellemesi patlar."""
    from managers.config_manager import DynamicConfig
    from managers.reference_lists import LIST_REGISTRY

    eksik = [k for k, spec in LIST_REGISTRY.items() if not hasattr(DynamicConfig, spec.setter)]
    assert eksik == [], "DynamicConfig setter'ı olmayan listeler: " + ", ".join(eksik)


def test_istinaf_basvuran_taraf_uc_degerle_seedleniyor():
    """Şartname §1.1 (S5): Davacı / Davalı / Her İki Taraf — kapalı küme."""
    from managers.seed_data import APPEALING_PARTIES, seed_all_lists

    assert [name for _, name in APPEALING_PARTIES] == ["Davacı", "Davalı", "Her İki Taraf"]
    assert len({code for code, _ in APPEALING_PARTIES}) == 3
    assert "_seed_appealing_parties" in seed_all_lists.__code__.co_names


def test_iddia_edilen_kusur_uydurma_degerle_doldurulmadi():
    """7 değerin KENDİSİ teslim paketinde yok → liste boş doğar (bilinçli).

    Uydurulmuş kusur adları aktarımda gerçek değerlerle çakışırdı; boş liste
    görünür bir eksiktir, uydurma veri görünmez bir hatadır.
    """
    import managers.seed_data as seed_data

    assert not hasattr(seed_data, "ALLEGED_FAULTS")
    assert "AllegedFault" not in seed_data.seed_all_lists.__code__.co_names


def test_kapali_liste_endpointleri_kayitli():
    """Arayüz değerleri backend'den okur; frontend'de sabit liste tutulmaz (G048)."""
    from routes import config as config_route

    paths = {route.path for route in config_route.router.routes}
    assert "/api/config/alleged_faults" in paths
    assert "/api/config/appealing_parties" in paths


# ═══════════════════════════════════════════════════════════════════════════
# 4. `Dava Türü Alt Kırılımı` → `Uzmanlık Alanı` (şartname §1.4)
# ═══════════════════════════════════════════════════════════════════════════

def test_uzmanlik_alani_etiket_degisimi_kolon_adi_degil():
    """Karar: ETİKET değişti, kolon adı (`sub_type`) korundu.

    Gerekçe koddan: `sub_type`in değeri `specialties` referans listesinden gelir
    (DEPENDENCIES) — yani alan zaten "uzmanlık alanı"dır, değişen Türkçe addır.
    Kolonu yeniden adlandırmak modelden migrasyona, şemadan arayüze ve dış Excel
    alışverişine kadar her katmanı kırardı ve hiçbir belirsizliği çözmezdi.
    """
    from required_fields import REQUIRED_CASE_FIELDS

    assert hasattr(models.Case, "sub_type"), "kolon yeniden adlandırılmış — G044 kararı bu değildi"
    assert not hasattr(models.Case, "uzmanlik_alani")

    etiketler = {f["field"]: f["label"] for f in REQUIRED_CASE_FIELDS}
    assert etiketler["sub_type"] == "Uzmanlık Alanı"


def test_uzmanlik_alani_kullanim_etiketi_guncel():
    """Silme/yeniden adlandırma diyaloğundaki "N dava kullanıyor" metni."""
    from managers.reference_lists import DEPENDENCIES

    labels = [d.label for d in DEPENDENCIES["specialties"] if d.column == "sub_type"]
    assert labels == ["dava (uzmanlık alanı)"]
