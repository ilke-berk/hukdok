"""G119 — Müvekkil Tipi + Hizmet Türü: iki kolon + iki kapalı liste (seed'li).

Kaynak: veri ekibinin Format Değişiklik Bildirimi DB-2026-002 (04.09.2026):
ilk teslim paketinden itibaren `Sheet` sayfasında föy düzeyinde iki yeni
sütun, 8.409 föyün tamamında dolu. Müvekkil Tipi = büronun bu föyde kimi
temsil ettiği (E-8 okuma yönü); Hizmet Türü = takip mi rapor mu ("Lexis
Rapor" 2.218 föy dava takibi değil). Bugüne kadar sessizce yok sayılıyordu.

İki liste G103 (`event_types`) deseninin birebir kopyasıdır (model +
LIST_REGISTRY + DEPENDENCIES + seed + config route + DynamicConfig setter'ı);
yazma yolu takip paneli, kapısı G066 davranış eşidir (case_manager'da
`_EVENT_LIST_COLUMNS`), liste filtresi (yalnız hizmet_turu) `file_type`
kalıbıdır. Tasarım kararı: mevcut `client_categories`/`bureau_types`
KULLANILMAZ ve DEĞİŞMEZ — bu dosya o kilidi de taşır.

Katmanlar (test_g103 düzeni):
1. DB'siz — model/migrasyon/şema/registry/whitelist kilitleri.
2. Sabit kilitleri — sözleşme değerleri (5+9, yazımlar birebir, kodlar ASCII).
3. sqlite (StaticPool) — seed idempotent + silme koruması + kart yazma kapısı +
   get_case/get_cases okuma-filtre yolları + route katmanı (400/403/200).
4. Gerçek Postgres (dbtest) — migrasyon yolu: iki kolon + iki tablo +
   ikinci koşu idempotent; DB yoksa SKIP (üç-ortam kuralı).
"""
import logging
import re

import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import models
from database import _MIGRATIONS
from managers import case_manager, seed_data
from managers.stage_decisions import InvalidDecisionStatusError
from schemas import CaseRead, CaseTrackingUpdate

# (registry anahtarı, model, bağlı cases kolonu, Türkçe başlık, seed sabiti, adet)
YENI_LISTELER = [
    ("client_types", models.ClientType, "muvekkil_tipi",
     "Müvekkil Tipleri", seed_data.CLIENT_TYPES, 5),
    ("service_types", models.ServiceType, "hizmet_turu",
     "Hizmet Türleri", seed_data.SERVICE_TYPES, 9),
]

# Sözleşme yazımları (G119/G120/G121 ORTAK bloğu) — BİREBİR, bildirimdeki sırayla.
RESMI_MUVEKKIL_TIPLERI = ["Sigorta", "Doktor", "Kurum", "Hasta", "Diğer Sağlık Çalışanı"]
RESMI_MUVEKKIL_TIPI_KODLARI = ["SIGORTA", "DOKTOR", "KURUM", "HASTA", "DIGER-SAGLIK-CALISANI"]
RESMI_HIZMET_TURLERI = [
    "Takip (doktor müvekkil)", "Lexis Rapor", "Vekaletsiz Takip", "Vekaletli Takip",
    "Vekalet Ücreti Alacağı", "Takip (hasta vekilliği)", "Takip (kurum vekilliği)",
    "Danışmanlık", "Takip (sağlık personeli)",
]
RESMI_HIZMET_TURU_KODLARI = [
    "TAKIP-DOKTOR-MUVEKKIL", "LEXIS-RAPOR", "VEKALETSIZ-TAKIP", "VEKALETLI-TAKIP",
    "VEKALET-UCRETI-ALACAGI", "TAKIP-HASTA-VEKILLIGI", "TAKIP-KURUM-VEKILLIGI",
    "DANISMANLIK", "TAKIP-SAGLIK-PERSONELI",
]

# (kolon, geçerli değer, liste dışı değer) — iki alan da AYRI test edilir.
IKI_ALAN = [
    ("muvekkil_tipi", "Doktor", "Avukat"),
    ("hizmet_turu", "Lexis Rapor", "Serbest Hizmet"),
]


def _route_dump(payload: dict) -> dict:
    """Route'un yaptığı dönüşümün birebir kopyası (G065/G066 deseni)."""
    return CaseTrackingUpdate.model_validate(payload).model_dump(exclude_unset=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema — model + migrasyon + Pydantic + registry + whitelist
# ═══════════════════════════════════════════════════════════════════════════

def test_iki_model_tanimli_kod_tekil_ve_zorunlu():
    for key, model, _, _, _, _ in YENI_LISTELER:
        assert model.__tablename__ == key
        code_col = model.code.property.columns[0]
        assert code_col.unique, f"{key}.code UNIQUE değil"
        assert not code_col.nullable, f"{key}.code NULL kabul ediyor"
        assert not model.name.property.columns[0].nullable, f"{key}.name NULL kabul ediyor"


def test_iki_kolon_modelde_null_ve_defaultsuz():
    """NULL = "bilinmiyor" — meşru durum, backfill YOK (sözleşme)."""
    for kolon in ("muvekkil_tipi", "hizmet_turu"):
        col = getattr(models.Case, kolon).property.columns[0]
        assert col.nullable, f"{kolon}: NULL kabul etmeli"
        assert col.default is None, f"{kolon}: DEFAULT 'bilinmiyor' ayrımını karartır"
        assert col.type.length == 100, kolon


def test_kolonlar_migrasyona_kayitli():
    """Mevcut kurulumda kolonlar ancak migrasyonla gelir (create_all alter
    etmez). Madde 38 deseni: yalnız ("columns", ...) op'u; tablolar modelde
    tanımlı olduğu için create_all yaratır."""
    kayitli = {}
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == "cases":
            for name, spec in op[2].items():
                kayitli[name] = spec if isinstance(spec, str) else spec[0]
    assert kayitli.get("muvekkil_tipi") == "VARCHAR(100)"
    assert kayitli.get("hizmet_turu") == "VARCHAR(100)"


def test_registry_deps_titles_kayitli():
    from managers.reference_lists import DEPENDENCIES, LIST_REGISTRY, LIST_TITLES

    for key, model, column, baslik, _, _ in YENI_LISTELER:
        assert key in LIST_REGISTRY, f"{key} LIST_REGISTRY'de yok"
        assert LIST_REGISTRY[key].model is model
        assert LIST_TITLES.get(key) == baslik, f"{key} için Türkçe başlık yanlış/yok"
        # Yeniden adlandırma bağlı kayıtlara yayılsın diye DEPENDENCIES şart
        deps = DEPENDENCIES[key]
        assert [(d.model, d.column, d.label) for d in deps] == [(models.Case, column, "dava")]


def test_mevcut_listeler_degismedi():
    """Tasarım kararı: client_categories / bureau_types KULLANILMAZ ve
    DEĞİŞMEZ — bağları eski varlık/kolonlarında kalır, yeni listeler onların
    yerine geçmez."""
    from managers.reference_lists import DEPENDENCIES, LIST_REGISTRY

    assert LIST_REGISTRY["client_categories"].model is models.ClientCategory
    assert LIST_REGISTRY["bureau_types"].model is models.BureauType
    assert [(d.model, d.column) for d in DEPENDENCIES["client_categories"]] == [(models.Client, "category")]
    assert [(d.model, d.column) for d in DEPENDENCIES["bureau_types"]] == [(models.Case, "bureau_type")]
    # Yeni kolonlar eski listelere BAĞLANMADI
    for key in ("client_categories", "bureau_types"):
        assert not any(d.column in ("muvekkil_tipi", "hizmet_turu") for d in DEPENDENCIES[key]), key


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
    """GET/POST/DELETE üçlüsü — event_types kalıbının birebir kopyası."""
    from routes import config as config_route

    paths = {route.path for route in config_route.router.routes}
    for key, _, _, _, _, _ in YENI_LISTELER:
        assert f"/api/config/{key}" in paths, f"{key} GET/POST ucu yok"
        assert f"/api/config/{key}/{{code}}" in paths, f"{key} DELETE ucu yok"


def test_schemalarda_iki_alan():
    for sema in (CaseRead, CaseTrackingUpdate):
        for alan in ("muvekkil_tipi", "hizmet_turu"):
            assert alan in sema.model_fields, f"{sema.__name__}.{alan}"
            assert sema.model_fields[alan].default is None


def test_takip_whitelistinde():
    """Yazma yolu takip paneli (kırmızı-yeşil kanıtı: eski TRACKING_FIELDS
    alanları içermiyordu, gönderilen değer sessizce süzülüyordu)."""
    for alan in ("muvekkil_tipi", "hizmet_turu"):
        assert alan in case_manager.TRACKING_FIELDS, alan


def test_kapali_liste_kapisina_bagli():
    """G066/G103 kapısı iki yeni kolonu da kendi listesine bağlıyor."""
    assert case_manager._EVENT_LIST_COLUMNS["muvekkil_tipi"] == (models.ClientType, "client_types")
    assert case_manager._EVENT_LIST_COLUMNS["hizmet_turu"] == (models.ServiceType, "service_types")


def test_alanlar_hicbir_baglamda_zorunlu_degil():
    """Kabul kriteri: required_fields DEĞİŞMEDİ — iki alan ne zorunlu listede
    ne eksik-bayrak girdisinde. `service_type` (ofis no hizmet bloğu) ise
    eskiden beri orada — yeni `hizmet_turu` onunla KARIŞTIRILMAZ."""
    from required_fields import MISSING_FLAG_INPUT_FIELDS, REQUIRED_CASE_FIELDS

    zorunlu = {f["field"] for f in REQUIRED_CASE_FIELDS}
    for alan in ("muvekkil_tipi", "hizmet_turu"):
        assert alan not in zorunlu, f"{alan} zorunlu YAPILMAMALIYDI"
        assert alan not in MISSING_FLAG_INPUT_FIELDS, alan


# ═══════════════════════════════════════════════════════════════════════════
# 2. Sözleşme sabitleri — sayılar, yazımlar, kodlar
# ═══════════════════════════════════════════════════════════════════════════

def test_seed_sabitleri_sozlesme_degerleri():
    for key, _, _, _, sabit, adet in YENI_LISTELER:
        assert len(sabit) == adet, f"{key}: {len(sabit)} != {adet}"
        kodlar = [code for code, _ in sabit]
        assert len(set(kodlar)) == len(kodlar), f"{key}: mükerrer kod var"
        for code in kodlar:
            assert re.fullmatch(r"[A-Z0-9-]+", code), f"{key}: ASCII dışı kod {code!r}"

    assert [ad for _, ad in seed_data.CLIENT_TYPES] == RESMI_MUVEKKIL_TIPLERI
    assert [code for code, _ in seed_data.CLIENT_TYPES] == RESMI_MUVEKKIL_TIPI_KODLARI
    assert [ad for _, ad in seed_data.SERVICE_TYPES] == RESMI_HIZMET_TURLERI
    assert [code for code, _ in seed_data.SERVICE_TYPES] == RESMI_HIZMET_TURU_KODLARI


def test_seed_yarissiz_ekleme_kullaniyor():
    """G058 deseni korunuyor: iki seed de `_seed_karar_listesi` (jenerik
    kapalı-liste seed'i) → `_ekle_yarissiz` (satır başına SAVEPOINT) yolundan."""
    co = seed_data.seed_all_lists.__code__.co_names
    for fn in ("_seed_client_types", "_seed_service_types"):
        assert fn in co, f"seed_all_lists {fn} çağırmıyor"
    for fn in (seed_data._seed_client_types, seed_data._seed_service_types):
        assert "_seed_karar_listesi" in fn.__code__.co_names


# ═══════════════════════════════════════════════════════════════════════════
# 3. sqlite — seed + silme koruması + kart yazma/okuma yolları + route
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def oturum_fabrikasi(monkeypatch):
    """Paylaşımlı in-memory sqlite; seed_data + reference_lists + case_manager
    aynı DB'yi görür (StaticPool şart — test_seed_data.py'deki gerekçe).
    DynamicConfig süreç-global singleton'dır: add/delete'in refresh_cache'i onu
    doldurur — iki liste testten önce ve sonra boşaltılır (test kirliliği)."""
    from managers import reference_lists
    from managers.config_manager import DynamicConfig

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(seed_data, "SessionLocal", Fabrika)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)

    config = DynamicConfig.get_instance()
    config.set_client_types([])
    config.set_service_types([])
    yield Fabrika
    config.set_client_types([])
    config.set_service_types([])
    engine.dispose()


@pytest.fixture()
def seedli_fabrika(oturum_fabrikasi):
    seed_data.seed_all_lists()
    return oturum_fabrikasi


def _say(Fabrika, model) -> int:
    db = Fabrika()
    try:
        return db.query(func.count(model.id)).scalar()
    finally:
        db.close()


def _dava_ekle(Fabrika, tracking_no="HA.X.9119.2026", **alanlar) -> int:
    db = Fabrika()
    try:
        case = models.Case(tracking_no=tracking_no, status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _oku(Fabrika, case_id: int, alan: str):
    db = Fabrika()
    try:
        return getattr(db.get(models.Case, case_id), alan)
    finally:
        db.close()


def test_seed_iki_tabloyu_sozlesme_adetleriyle_dolduruyor(seedli_fabrika):
    """Kabul kriteri: temiz DB'de 5+9 satır bildirimdeki sırayla."""
    for key, model, _, _, sabit, adet in YENI_LISTELER:
        assert _say(seedli_fabrika, model) == adet, key
        db = seedli_fabrika()
        try:
            satirlar = db.query(model).order_by(model.sequence).all()
            assert [(s.code, s.name) for s in satirlar] == list(sabit), key
            assert [s.sequence for s in satirlar] == list(range(adet)), key
            assert all(s.active for s in satirlar), key
        finally:
            db.close()


def test_ikinci_kosu_eklemiyor_ve_error_basmiyor(seedli_fabrika, caplog):
    """Kabul kriteri: ikinci açılışta 0 ekleme, 0 ERROR (log sözleşmesi)."""
    once = {key: _say(seedli_fabrika, model) for key, model, _, _, _, _ in YENI_LISTELER}
    with caplog.at_level(logging.ERROR):
        seed_data.seed_all_lists()
    sonra = {key: _say(seedli_fabrika, model) for key, model, _, _, _, _ in YENI_LISTELER}
    assert sonra == once
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_seed_mevcut_listelere_dokunmuyor(seedli_fabrika):
    """Kabul kriteri: client_categories / bureau_types DEĞİŞMEDİ — yeni seed
    değerleri o tablolara sızmaz."""
    db = seedli_fabrika()
    try:
        kategori_adlari = {r.name for r in db.query(models.ClientCategory).all()}
        buro_adlari = {r.name for r in db.query(models.BureauType).all()}
    finally:
        db.close()
    assert not (kategori_adlari & set(RESMI_HIZMET_TURLERI))
    assert not (buro_adlari & set(RESMI_HIZMET_TURLERI))
    assert "Diğer Sağlık Çalışanı" not in kategori_adlari


def test_get_items_sozlesme_sirasiyla_donuyor(seedli_fabrika):
    """GET ucunun veri katmanı değerleri sequence sırasıyla döner — dropdown
    sözleşme sırasını korur; biçim event_types ile aynı (code/name)."""
    from managers.reference_lists import get_items

    assert get_items("client_types") == [
        {"code": code, "name": name} for code, name in seed_data.CLIENT_TYPES
    ]
    assert get_items("service_types") == [
        {"code": code, "name": name} for code, name in seed_data.SERVICE_TYPES
    ]


def test_silme_korumasi_kullanimda_block(seedli_fabrika):
    """Listedeki değer bir davada kullanılıyorken mode=block silme
    ItemInUseError üretir (api.py 409'a çevirir); bağ get_usage'ın DepSpec
    (cases.hizmet_turu) yolundan gelir."""
    from managers.reference_lists import ItemInUseError, delete_item

    _dava_ekle(seedli_fabrika, hizmet_turu="Lexis Rapor")
    with pytest.raises(ItemInUseError) as exc:
        delete_item("service_types", "LEXIS-RAPOR", mode="block")
    assert exc.value.usage["total"] == 1
    assert exc.value.usage["items"][0]["label"] == "dava"

    db = seedli_fabrika()
    try:
        assert db.query(models.ServiceType).filter_by(code="LEXIS-RAPOR").count() == 1
    finally:
        db.close()


def test_yeniden_adlandirma_karta_yayiliyor(seedli_fabrika):
    """DEPENDENCIES'in ikinci işlevi: liste öğesi yeniden adlandırılınca
    kart kolonundaki denormalize ad da çevrilir (muvekkil_tipi yolu)."""
    from managers.reference_lists import rename_item

    cid = _dava_ekle(seedli_fabrika, muvekkil_tipi="Doktor")
    assert rename_item("client_types", "DOKTOR", "Hekim")
    assert _oku(seedli_fabrika, cid, "muvekkil_tipi") == "Hekim"


# ── Kart yazma yolu — update_case_tracking kapısı (G066/G103 davranış eşi) ──

@pytest.mark.parametrize("alan,gecerli,liste_disi", IKI_ALAN)
def test_listedeki_deger_yazilabiliyor(seedli_fabrika, alan, gecerli, liste_disi):
    cid = _dava_ekle(seedli_fabrika)
    assert case_manager.update_case_tracking(
        cid, _route_dump({alan: gecerli}), changed_by="g119-test"
    ) is True
    assert _oku(seedli_fabrika, cid, alan) == gecerli


@pytest.mark.parametrize("alan,gecerli,liste_disi", IKI_ALAN)
def test_liste_disi_deger_reddediliyor(seedli_fabrika, alan, gecerli, liste_disi):
    """Kırmızı-yeşil kanıtı: eski kodda alan whitelist'te olmadığından sessizce
    süzülürdü; kapı olmadan eklenseydi serbest metin yazılırdı."""
    cid = _dava_ekle(seedli_fabrika)
    with pytest.raises(InvalidDecisionStatusError):
        case_manager.update_case_tracking(
            cid, _route_dump({alan: liste_disi}), changed_by="g119-test"
        )
    assert _oku(seedli_fabrika, cid, alan) is None


@pytest.mark.parametrize("alan,gecerli,liste_disi", IKI_ALAN)
def test_null_gonderimi_alani_temizliyor(seedli_fabrika, alan, gecerli, liste_disi):
    """G065 sözleşmesi korunur: None GÖNDERİLEN alan silinir (exclude_unset)."""
    cid = _dava_ekle(seedli_fabrika, **{alan: gecerli})
    assert case_manager.update_case_tracking(
        cid, _route_dump({alan: None}), changed_by="g119-test"
    ) is True
    assert _oku(seedli_fabrika, cid, alan) is None


def test_bosluk_normalize_ediliyor(seedli_fabrika):
    """Normalizasyon G066 ile AYNI: baştaki/sondaki ve İÇTEKİ fazla boşluklar
    sadeleşir, sonra ada göre eşleşir."""
    cid = _dava_ekle(seedli_fabrika)
    assert case_manager.update_case_tracking(
        cid, _route_dump({"hizmet_turu": "  Takip   (doktor  müvekkil) "}), changed_by="g119-test"
    ) is True
    assert _oku(seedli_fabrika, cid, "hizmet_turu") == "Takip (doktor müvekkil)"


@pytest.mark.parametrize("alan,gecerli,liste_disi", IKI_ALAN)
def test_bos_listede_warningle_geciyor(oturum_fabrikasi, caplog, alan, gecerli, liste_disi):
    """Kabul kriteri: liste boşaltılınca yazım WARNING'le geçer (G066 karar
    noktası 3 eşliği — seed'i koşmamış kurulumda veri girişi kilitlenmez)."""
    liste_adi = case_manager._EVENT_LIST_COLUMNS[alan][1]
    cid = _dava_ekle(oturum_fabrikasi)
    with caplog.at_level("WARNING"):
        assert case_manager.update_case_tracking(
            cid, _route_dump({alan: gecerli}), changed_by="g119-test"
        ) is True
    assert _oku(oturum_fabrikasi, cid, alan) == gecerli
    assert any(liste_adi in r.message and "BOŞ" in r.message
               for r in caplog.records)


def test_ret_kismi_yazim_birakmiyor(seedli_fabrika):
    """Doğrulama YAZIMDAN ÖNCE toptan koşar: geçerli müvekkil tipi + liste dışı
    hizmet türü aynı gövdedeyse HİÇBİRİ yazılmaz (G066 sözleşmesi bozulmadı)."""
    cid = _dava_ekle(seedli_fabrika)
    with pytest.raises(InvalidDecisionStatusError):
        case_manager.update_case_tracking(
            cid,
            _route_dump({"muvekkil_tipi": "Sigorta", "hizmet_turu": "Bilinmeyen Hizmet"}),
            changed_by="g119-test",
        )
    assert _oku(seedli_fabrika, cid, "muvekkil_tipi") is None
    assert _oku(seedli_fabrika, cid, "hizmet_turu") is None


def test_g103_kapisi_hala_calisiyor(seedli_fabrika):
    """Korunum: aynı kapıya iki kolon eklenmesi olay_turu'nun reddini bozmadı."""
    cid = _dava_ekle(seedli_fabrika)
    with pytest.raises(InvalidDecisionStatusError):
        case_manager.update_case_tracking(
            cid, _route_dump({"olay_turu": "Serbest Metin Olay"}), changed_by="g119-test"
        )


# ── Okuma yolu + liste filtresi ──────────────────────────────────────────────

def test_get_case_ciktisinda_iki_alan(seedli_fabrika):
    cid = _dava_ekle(seedli_fabrika, muvekkil_tipi="Sigorta", hizmet_turu="Lexis Rapor",
                     service_type="00001")
    result = case_manager.get_case(cid)
    assert result["muvekkil_tipi"] == "Sigorta"
    assert result["hizmet_turu"] == "Lexis Rapor"
    # Mevcut `service_type` (ofis no hizmet bloğu) ayrı alan olarak korunur
    assert result["service_type"] == "00001"

    bos = case_manager.get_case(_dava_ekle(seedli_fabrika, tracking_no="HA.X.9120.2026"))
    assert bos["muvekkil_tipi"] is None
    assert bos["hizmet_turu"] is None


def test_get_cases_hizmet_turu_filtresi_tenantla_birlikte(seedli_fabrika):
    """Kabul kriteri: `get_cases(hizmet_turu="Lexis Rapor")` yalnız o değerli
    kartları döndürür; tenant deseni ("X OR NULL") bozulmaz; verilmeyince/"ALL"
    iken filtre yok; total (X-Total-Count'un kaynağı) sayfalamadan önce sayılır."""
    c1 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9201.2026", hizmet_turu="Lexis Rapor")
    c2 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9202.2026", hizmet_turu="Vekaletli Takip")
    c3 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9203.2026")            # NULL = bilinmiyor
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9204.2026",
               hizmet_turu="Lexis Rapor", tenant_id="baska-tenant")

    items, total = case_manager.get_cases(hizmet_turu="Lexis Rapor", tenant_id="tenant-1")
    assert [c["id"] for c in items] == [c1]
    assert total == 1

    items, total = case_manager.get_cases(tenant_id="tenant-1")
    assert {c["id"] for c in items} == {c1, c2, c3}
    assert total == 3

    items, total = case_manager.get_cases(hizmet_turu="ALL", tenant_id="tenant-1")
    assert total == 3


def test_get_cases_iki_filtre_birlikte(seedli_fabrika):
    """olay_turu + hizmet_turu filtreleri AND ile birleşir (bağımsız kalıplar
    birbirini ezmez)."""
    c1 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9211.2026",
                    hizmet_turu="Lexis Rapor", olay_turu="Tıbbi Olay")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9212.2026",
               hizmet_turu="Lexis Rapor", olay_turu="Belgeleme Olayı")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9213.2026",
               hizmet_turu="Vekaletli Takip", olay_turu="Tıbbi Olay")

    items, total = case_manager.get_cases(hizmet_turu="Lexis Rapor", olay_turu="Tıbbi Olay")
    assert [c["id"] for c in items] == [c1]
    assert total == 1


def test_get_cases_muvekkil_tipi_filtresi_yok():
    """Sözleşme: Müvekkil Tipi için liste filtresi BİLİNÇLİ yok."""
    import inspect

    assert "muvekkil_tipi" not in inspect.signature(case_manager.get_cases).parameters
    assert "hizmet_turu" in inspect.signature(case_manager.get_cases).parameters


# ── Route katmanı — 400 / 403 / 200 ──────────────────────────────────────────

@pytest.fixture()
def client(seedli_fabrika):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın
    # (test_faz5_status_codes deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter

    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_route_get_listeler_sirali_donuyor(client):
    """Kabul kriteri: GET client_types → 5 kayıt sıralı; service_types → 9.
    Cevap biçimi event_types ile aynı (code/name)."""
    resp = client.get("/api/config/client_types")
    assert resp.status_code == 200
    assert resp.json() == [{"code": c, "name": n} for c, n in seed_data.CLIENT_TYPES]

    resp = client.get("/api/config/service_types")
    assert resp.status_code == 200
    assert resp.json() == [{"code": c, "name": n} for c, n in seed_data.SERVICE_TYPES]
    assert len(resp.json()) == 9


def test_route_post_delete_admin_kapili(client, monkeypatch):
    """Kabul kriteri: POST/DELETE admin kapılı (event_types kalıbı) —
    ADMIN_EMAILS'te olmayan kullanıcı 403 alır, listeye dokunulmaz."""
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    assert client.post("/api/config/client_types",
                       json={"code": "X1", "name": "Deneme"}).status_code == 403
    assert client.post("/api/config/service_types",
                       json={"code": "X1", "name": "Deneme"}).status_code == 403
    assert client.delete("/api/config/service_types/LEXIS-RAPOR").status_code == 403
    assert client.delete("/api/config/client_types/DOKTOR").status_code == 403
    assert len(client.get("/api/config/service_types").json()) == 9  # silinmedi
    assert len(client.get("/api/config/client_types").json()) == 5


def test_route_post_delete_admin_ile_calisiyor(client, monkeypatch, seedli_fabrika):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    resp = client.post("/api/config/client_types", json={"code": "X1", "name": "Deneme"})
    assert resp.status_code == 200
    assert _say(seedli_fabrika, models.ClientType) == 6

    resp = client.delete("/api/config/client_types/X1")
    assert resp.status_code == 200
    assert _say(seedli_fabrika, models.ClientType) == 5

    resp = client.post("/api/config/service_types", json={"code": "X2", "name": "Deneme 2"})
    assert resp.status_code == 200
    assert _say(seedli_fabrika, models.ServiceType) == 10

    resp = client.delete("/api/config/service_types/X2")
    assert resp.status_code == 200
    assert _say(seedli_fabrika, models.ServiceType) == 9


def test_route_liste_disi_deger_400_donuyor(client, seedli_fabrika):
    """InvalidDecisionStatusError handler'ı (api.py) kapının hatasını 400'e
    çevirir; detay alan + liste + değeri söyler."""
    cid = _dava_ekle(seedli_fabrika)
    resp = client.patch(f"/api/cases/{cid}/tracking",
                        json={"muvekkil_tipi": "Avukat"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "muvekkil_tipi" in detail          # hangi alan
    assert "client_types" in detail           # hangi liste
    assert "Avukat" in detail                 # hangi değer
    assert _oku(seedli_fabrika, cid, "muvekkil_tipi") is None


def test_route_gecerli_deger_200_donuyor(client, seedli_fabrika):
    cid = _dava_ekle(seedli_fabrika)
    resp = client.patch(f"/api/cases/{cid}/tracking",
                        json={"muvekkil_tipi": "Hasta", "hizmet_turu": "Takip (hasta vekilliği)"})
    assert resp.status_code == 200
    assert _oku(seedli_fabrika, cid, "muvekkil_tipi") == "Hasta"
    assert _oku(seedli_fabrika, cid, "hizmet_turu") == "Takip (hasta vekilliği)"

    resp = client.get(f"/api/cases/{cid}")
    assert resp.status_code == 200
    assert resp.json()["muvekkil_tipi"] == "Hasta"
    assert resp.json()["hizmet_turu"] == "Takip (hasta vekilliği)"


def test_route_liste_ucu_hizmet_turu_filtresi(client, seedli_fabrika):
    """Query param liste isteğine bağlanıyor; X-Total-Count davranışı bozulmadı."""
    c1 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9301.2026", hizmet_turu="Lexis Rapor")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9302.2026", hizmet_turu="Vekaletli Takip")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9303.2026")

    resp = client.get("/api/cases", params={"hizmet_turu": "Lexis Rapor"})
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [c1]
    assert resp.headers["X-Total-Count"] == "1"

    resp = client.get("/api/cases")
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "3"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Gerçek Postgres — migrasyon yolu (üç-ortam kuralı: DB yoksa SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def admin_engine():
    """test_migration_path.admin_engine'in yereli: CREATE/DROP DATABASE için
    bakım bağlantısı; Postgres'e ulaşılamıyorsa SKIP (FAIL değil) — konteynersiz
    saf birim koşusu yeşil kalır (üç-ortam kuralı)."""
    import os

    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("MIGRATION_TEST_DATABASE_URL/DATABASE_URL postgresql:// değil")

    engine = create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__}) — migrasyon yolu testi atlandı")
    yield engine
    engine.dispose()


@pytest.mark.dbtest
def test_migrasyon_iki_kolon_iki_tablo_ve_idempotent(admin_engine):
    """Kabul kriteri: sıfırdan kurulumda iki kolon (migrasyon) + iki tablo
    (create_all, `to_regclass` ile ölçülür) oluşur; ikinci init_db koşusu
    şemayı DEĞİŞTİRMEZ (0 değişiklik). Scratch DB deseni test_migration_path'ten
    (gerçek veritabanına asla yazılmaz, teardown hata yolunda da düşürür)."""
    from test_migration_path import (
        _live_columns,
        _run_init_db,
        _schema_snapshot,
        _scratch_database,
    )

    with _scratch_database(admin_engine, "g119") as engine:
        _run_init_db(engine)

        columns = _live_columns(engine)
        assert "muvekkil_tipi" in columns["cases"]
        assert "hizmet_turu" in columns["cases"]
        with engine.connect() as conn:
            for tablo in ("client_types", "service_types"):
                assert conn.execute(
                    text("SELECT to_regclass(:t)"), {"t": tablo}
                ).scalar() == tablo, f"{tablo} tablosu oluşmadı"

        before = _schema_snapshot(engine)
        _run_init_db(engine)   # hata fırlatırsa test kırmızı
        assert _schema_snapshot(engine) == before, "ikinci koşu şemayı değiştirdi"
