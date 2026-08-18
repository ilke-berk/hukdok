"""G060 — Karar sonucu resmi listeleri: 4 kapalı havuz + `cases.yerel_karar_durumu`.

Kaynak: KARAR_ASAMALARI_TASARIM_PAKETI_2026-08-17 "kapalı havuzlar" değişmezi +
DEGER_HAVUZLARI (2026-08-10 teslim paketi: Yerel 28 · İstinaf 3 · Temyiz 3 · KD 2).
Dört liste `appealing_parties` deseninin (G044) kopyasıdır: model + LIST_REGISTRY
+ DEPENDENCIES + seed + config route + DynamicConfig setter'ı.

Katmanlar (test_g044_faz_f_semasi.py düzeni):
1. DB'siz — model/migrasyon/şema/registry kilitleri.
2. Sabit kilitleri — resmi havuz sayıları, BİREBİR yazımlar, kod üretim kuralı.
3. sqlite (StaticPool) — seed idempotent + yazımların normalize edilmeden
   yazılması + silme koruması (mode=block → ItemInUseError, get_usage DepSpec bağı).

Gerçek DB'ye bağlanan test YOK: hepsi kendi in-memory sqlite şemasını kurar —
üç ortam (lokal konteyner / deploy kapısı / CI çıplak postgres) aynı davranır
(Deploy #10 dersi, KUYRUK.md "kapı merdiveninin kör noktası").
"""
import logging
import re

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS
from managers import seed_data

# (registry anahtarı, model, bağlı cases kolonu, Türkçe başlık, seed sabiti, adet)
YENI_LISTELER = [
    ("local_decisions", models.LocalDecision, "yerel_karar_durumu",
     "Yerel Karar Durumları", seed_data.LOCAL_DECISIONS, 28),
    ("appeal_decisions", models.AppealDecision, "istinaf_karar_durumu",
     "İstinaf Karar Durumları", seed_data.APPEAL_DECISIONS, 3),
    ("cassation_decisions", models.CassationDecision, "temyiz_karar_durumu",
     "Temyiz Onama Durumları", seed_data.CASSATION_DECISIONS, 3),
    ("revision_decisions", models.RevisionDecision, "karar_duzeltme_durumu",
     "Karar Düzeltme Durumları", seed_data.REVISION_DECISIONS, 2),
]

# Resmi havuz yazımları — görev dosyası/DEGER_HAVUZLARI ile BİREBİR.
RESMI_YEREL = [
    "Açılmamış Sayılması (HMK 150. Md)", "Adli Para Cezası", "Anlaşma",
    "Anlaşmama", "Beraat", "Birleştirme", "Derdest", "Düşme Kararı",
    "Hapis Cezası", "Hapis Cezasının Paraya Çevrilmesi",
    "Hükmün Açıklanmasının Geri Bırakılması (HAGB)", "İflas", "Kabul",
    "Kabul/Kısmen", "Kapalı", "Karar Verilmesine Yer Olmadığına (HMK 331 Md.)",
    "Kovuşturmaya Yer Olmadığına (KYOK)", "Red/Arabuluculuk Ön Şart",
    "Red/Dilekçenin Reddi", "Red/Esastan", "Red/Feragat", "Red/Görev",
    "Red/Husumet", "Red/İdari Merciye Tevdi", "Red/MSK Kararı Gereği",
    "Red/Yargı Yolu", "Red/Yetkisizlik", "Red/Zamanaşımı",
]
RESMI_ISTINAF = ["Kaldırma", "Kaldırma/Yeniden Hüküm", "Başvuru Ret"]
RESMI_TEMYIZ = ["Bozma", "Onama", "Düzelterek Onama"]
RESMI_KARAR_DUZELTME = ["Karar Düzeltme Kabul", "Karar Düzeltme Ret"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema — model + migrasyon + Pydantic + registry
# ═══════════════════════════════════════════════════════════════════════════

def test_dort_model_tanimli_kod_tekil_ve_zorunlu():
    for key, model, _, _, _, _ in YENI_LISTELER:
        code_col = model.code.property.columns[0]
        assert code_col.unique, f"{key}.code UNIQUE değil"
        assert not code_col.nullable, f"{key}.code NULL kabul ediyor"
        assert not model.name.property.columns[0].nullable, f"{key}.name NULL kabul ediyor"


def test_yerel_karar_durumu_modelde_null_ve_defaultsuz():
    col = models.Case.yerel_karar_durumu.property.columns[0]
    assert col.nullable, "aktarım kısmi partide patlar (G044 gerekçesi)"
    assert col.default is None, "DEFAULT 'girilmedi' ile '' ayrımını karartır"
    assert col.type.length == 100  # kardeş kolonlarla (istinaf/temyiz/KD) aynı


def test_yerel_karar_durumu_migrasyona_kayitli():
    """Mevcut kurulumda kolon ancak migrasyonla gelir (create_all alter etmez).
    G041 kuralı gereği kısıt/index gerekmedi → yalnız ("columns", ...) op'u."""
    kayitli = {}
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == "cases":
            for name, spec in op[2].items():
                kayitli[name] = spec if isinstance(spec, str) else spec[0]
    assert kayitli.get("yerel_karar_durumu") == "VARCHAR(100)"


def test_karar_turu_ve_karar_lehine_davranisi_degismedi():
    """Kaba 6'lık `karar_turu` + `karar_lehine` bu görevin kapsamı DIŞINDA:
    tanımları aynen duruyor ve yeni listelerin hiçbirine BAĞLANMADI."""
    from managers.reference_lists import DEPENDENCIES

    turu = models.Case.karar_turu.property.columns[0]
    lehine = models.Case.karar_lehine.property.columns[0]
    assert turu.type.length == 50 and turu.nullable
    assert lehine.type.length == 20 and lehine.nullable

    yeni_bagli = {
        dep.column
        for key, _, _, _, _, _ in YENI_LISTELER
        for dep in DEPENDENCIES[key]
    }
    assert "karar_turu" not in yeni_bagli
    assert "karar_lehine" not in yeni_bagli


def test_registry_deps_titles_kayitli():
    from managers.reference_lists import DEPENDENCIES, LIST_REGISTRY, LIST_TITLES

    for key, model, column, baslik, _, _ in YENI_LISTELER:
        assert key in LIST_REGISTRY, f"{key} LIST_REGISTRY'de yok"
        assert LIST_REGISTRY[key].model is model
        assert LIST_TITLES.get(key) == baslik, f"{key} için Türkçe başlık yanlış/yok"
        # Yeniden adlandırma bağlı kayıtlara yayılsın diye DEPENDENCIES şart
        deps = DEPENDENCIES[key]
        assert [(d.model, d.column) for d in deps] == [(models.Case, column)]


def test_dynamicconfig_getter_setterlari_var():
    """`refresh_cache` setter'ı getattr ile çağırır — yoksa güncelleme patlar."""
    from managers.config_manager import DynamicConfig
    from managers.reference_lists import LIST_REGISTRY

    for key, _, _, _, _, _ in YENI_LISTELER:
        spec = LIST_REGISTRY[key]
        assert hasattr(DynamicConfig, spec.setter), f"{key}: {spec.setter} yok"
        getter = spec.setter.replace("set_", "get_", 1)
        assert hasattr(DynamicConfig, getter), f"{key}: {getter} yok"


def test_endpointler_kayitli():
    """GET/POST/DELETE üçlüsü — appealing_parties'in kayıt yoluyla aynı yol
    (router'a modül seviyesinde dekoratörle)."""
    from routes import config as config_route

    paths = {route.path for route in config_route.router.routes}
    for key, _, _, _, _, _ in YENI_LISTELER:
        assert f"/api/config/{key}" in paths, f"{key} GET/POST ucu yok"
        assert f"/api/config/{key}/{{code}}" in paths, f"{key} DELETE ucu yok"


def test_schemalarda_yerel_karar_durumu():
    from schemas import CaseRead, CaseTrackingUpdate

    for sema in (CaseRead, CaseTrackingUpdate):
        assert "yerel_karar_durumu" in sema.model_fields, sema.__name__
        assert sema.model_fields["yerel_karar_durumu"].default is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Resmi havuz sabitleri — sayılar, yazımlar, kod kuralı
# ═══════════════════════════════════════════════════════════════════════════

def test_resmi_havuz_sayilari_ve_kod_tekilligi():
    for key, _, _, _, sabit, adet in YENI_LISTELER:
        assert len(sabit) == adet, f"{key}: {len(sabit)} != {adet}"
        kodlar = [code for code, _ in sabit]
        assert len(set(kodlar)) == len(kodlar), f"{key}: mükerrer kod var"


def test_resmi_yazimlar_birebir():
    assert [ad for _, ad in seed_data.LOCAL_DECISIONS] == RESMI_YEREL
    assert [ad for _, ad in seed_data.APPEAL_DECISIONS] == RESMI_ISTINAF
    assert [ad for _, ad in seed_data.CASSATION_DECISIONS] == RESMI_TEMYIZ
    assert [ad for _, ad in seed_data.REVISION_DECISIONS] == RESMI_KARAR_DUZELTME


def test_kod_uretim_kurali():
    """Görev tanımındaki kural: tr_upper → Türkçe sadeleştir → [^A-Z0-9]+ → `_`."""
    assert seed_data._karar_kodu(
        "Hükmün Açıklanmasının Geri Bırakılması (HAGB)"
    ) == "HUKMUN_ACIKLANMASININ_GERI_BIRAKILMASI_HAGB"
    assert seed_data._karar_kodu("Red/İdari Merciye Tevdi") == "RED_IDARI_MERCIYE_TEVDI"
    assert seed_data._karar_kodu("İflas") == "IFLAS"
    assert seed_data._karar_kodu(
        "Karar Verilmesine Yer Olmadığına (HMK 331 Md.)"
    ) == "KARAR_VERILMESINE_YER_OLMADIGINA_HMK_331_MD"

    for key, _, _, _, sabit, _ in YENI_LISTELER:
        for code, _ in sabit:
            assert re.fullmatch(r"[A-Z0-9_]+", code), f"{key}: ASCII dışı kod {code!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. sqlite — seed idempotentliği + yazım koruması + silme koruması
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def oturum_fabrikasi(monkeypatch):
    """Paylaşımlı in-memory sqlite; seed_data VE reference_lists aynı DB'yi görür
    (StaticPool şart — test_seed_data.py'deki gerekçe)."""
    from managers import reference_lists

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(seed_data, "SessionLocal", Fabrika)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _say(Fabrika, model) -> int:
    db = Fabrika()
    try:
        return db.query(func.count(model.id)).scalar()
    finally:
        db.close()


def test_seed_dort_tabloyu_resmi_adetlerle_dolduruyor(oturum_fabrikasi):
    seed_data.seed_all_lists()
    for key, model, _, _, _, adet in YENI_LISTELER:
        assert _say(oturum_fabrikasi, model) == adet, key


def test_seed_yazimlari_normalize_etmeden_yaziyor(oturum_fabrikasi):
    """normalize_list_name (tr_title) devrede olsaydı "Red/Esastan" →
    "Red/esastan" olurdu — seed'in add_item yerine doğrudan model satırı
    yazmasının (görev notu) kanıtı."""
    seed_data.seed_all_lists()
    db = oturum_fabrikasi()
    try:
        adlar = {ad for (ad,) in db.query(models.LocalDecision.name).all()}
    finally:
        db.close()
    assert adlar == set(RESMI_YEREL)
    assert "Red/Esastan" in adlar
    assert "Red/esastan" not in adlar


def test_ikinci_kosu_eklemiyor_ve_error_basmiyor(oturum_fabrikasi, caplog):
    """Kabul kriteri: ikinci koşuda 0 ekleme, 0 ERROR (idempotentlik)."""
    seed_data.seed_all_lists()
    once = {key: _say(oturum_fabrikasi, model) for key, model, _, _, _, _ in YENI_LISTELER}
    with caplog.at_level(logging.ERROR):
        seed_data.seed_all_lists()
    sonra = {key: _say(oturum_fabrikasi, model) for key, model, _, _, _, _ in YENI_LISTELER}
    assert sonra == once
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_seed_yarissiz_ekleme_kullaniyor():
    """G058 deseni korunuyor: dört seed de `_seed_karar_listesi` →
    `_ekle_yarissiz` (satır başına SAVEPOINT) yolundan geçer."""
    co = seed_data.seed_all_lists.__code__.co_names
    for fn in ("_seed_local_decisions", "_seed_appeal_decisions",
               "_seed_cassation_decisions", "_seed_revision_decisions"):
        assert fn in co, f"seed_all_lists {fn} çağırmıyor"
    assert "_ekle_yarissiz" in seed_data._seed_karar_listesi.__code__.co_names


def test_get_items_resmi_sirayla_donuyor(oturum_fabrikasi):
    """GET ucunun veri katmanı (get_items) değerleri sequence sırasıyla döner —
    dropdown resmi havuz sırasını korur (G061'in okuyacağı yol)."""
    from managers.reference_lists import get_items

    seed_data.seed_all_lists()
    assert [v["name"] for v in get_items("local_decisions")] == RESMI_YEREL
    assert get_items("appeal_decisions") == [
        {"code": code, "name": name} for code, name in seed_data.APPEAL_DECISIONS
    ]


def test_silme_korumasi_kullanimda_block(oturum_fabrikasi):
    """Kabul kriteri: listedeki değer bir davada kullanılıyorken mode=block
    silme ItemInUseError üretir (api.py handler'ı bunu 409'a çevirir); bağ
    get_usage'ın DepSpec (cases.yerel_karar_durumu) yolundan gelir."""
    from managers.reference_lists import ItemInUseError, delete_item

    seed_data.seed_all_lists()
    db = oturum_fabrikasi()
    try:
        db.add(models.Case(tracking_no="HA.X.9001.2026", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0,
                           yerel_karar_durumu="Beraat"))
        db.commit()
    finally:
        db.close()

    with pytest.raises(ItemInUseError) as exc:
        delete_item("local_decisions", "BERAAT", mode="block")
    assert exc.value.usage["total"] == 1
    assert exc.value.usage["items"][0]["label"] == "dava"

    # Öğe silinmedi, davadaki değer el değmeden duruyor
    db = oturum_fabrikasi()
    try:
        assert db.query(models.LocalDecision).filter_by(code="BERAAT").count() == 1
        assert db.query(models.Case).filter_by(yerel_karar_durumu="Beraat").count() == 1
    finally:
        db.close()
