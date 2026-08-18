"""G065 — `yerel_karar_durumu` okuma/yazma yolu: get_case serialize + takip whitelist.

G060 kolonu + kapalı listeyi açtı (models.py `Case.yerel_karar_durumu`, schemas.py
`CaseRead`/`CaseTrackingUpdate`), G061 dropdown'ı bağladı; ama alanın backend yolu
kopuktu (G060/G061 raporlarının ortak bulgusu): dava serialize sözlüğü
(`get_case`) alanı DÖNMÜYOR, takip whitelist'i (`TRACKING_FIELDS` "Yerel Karar"
bloğu) alanı YAZMIYORDU — dropdown dolu ama değer GET'te yok, PATCH'te sessizce
yoksayılıyordu. Bu dosya iki bağı kilitler:

1. Serialize: `get_case` çıktısı `yerel_karar_durumu`nu döner (değerli kayıtta
   değer, boş kayıtta anahtar + None — istinaf paritesinde).
2. Whitelist: route dump'ı → `tracking_changes` → `update_case_tracking` zinciri
   alanı yazar; None göndermek siler (exclude_unset sözleşmesi, Faz 1).
3. Korunum: whitelist dışı alanın sessiz yoksayması ve kardeş karar alanlarının
   (istinaf/temyiz/karar düzeltme) davranışı değişmedi.

Gerçek DB'ye bağlanan test YOK: in-memory sqlite + StaticPool (G060 deseni) —
üç ortam (lokal konteyner / deploy kapısı / CI çıplak postgres) aynı davranır.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from managers import case_manager
from managers.case_manager import TRACKING_FIELDS, tracking_changes
from schemas import CaseTrackingUpdate


def _route_dump(payload: dict) -> dict:
    """Route'un yaptığı dönüşümün birebir kopyası (test_case_tracking_update deseni):
    PATCH gövdesi şemadan geçer, exclude_unset yalnız gönderilen alanları bırakır."""
    return CaseTrackingUpdate.model_validate(payload).model_dump(exclude_unset=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — whitelist üyeliği + saf tracking_changes
# ═══════════════════════════════════════════════════════════════════════════

def test_yerel_karar_durumu_whitelistte():
    """Kırmızı-yeşil kanıtı (yazma bacağı): eski TRACKING_FIELDS alanı içermiyordu."""
    assert "yerel_karar_durumu" in TRACKING_FIELDS


def test_kardes_karar_alanlari_whitelistte_kaldi():
    """Kabul kriteri (korunum): istinaf/temyiz/KD karar alanları whitelist'te
    aynen duruyor — bu görev yalnız 'Yerel Karar' bloğuna EKLER, başkasını oynamaz."""
    for alan in ("karar_turu", "karar_lehine", "istinaf_karar_durumu",
                 "temyiz_karar_durumu", "karar_duzeltme_durumu"):
        assert alan in TRACKING_FIELDS, alan


def test_tracking_changes_yerel_karari_yaziyor():
    assert tracking_changes(_route_dump({"yerel_karar_durumu": "Beraat"})) == [
        ("yerel_karar_durumu", "Beraat")
    ]


def test_tracking_changes_null_gonderim_siler():
    """exclude_unset sözleşmesi: None GÖNDERİLEN alan dict'e girer → alan silinir."""
    assert tracking_changes(_route_dump({"yerel_karar_durumu": None})) == [
        ("yerel_karar_durumu", None)
    ]


def test_whitelist_disi_alan_yoksaymasi_degismedi():
    """Mevcut davranış korunur: TRACKING_FIELDS dışı anahtar sessizce süzülür
    (route katmanında ayrıca CaseTrackingUpdate şeması var; burada manager'a ham
    dict gelme senaryosu kilitlenir — test_case_tracking_update ile aynı sözleşme)."""
    assert tracking_changes({"tracking_no": "HACK", "yerel_karar_durumu": "Kabul"}) == [
        ("yerel_karar_durumu", "Kabul")
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite — serialize dönüşü + uçtan uca yazma
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def oturum_fabrikasi(monkeypatch):
    """In-memory sqlite; case_manager'ın modül-global SessionLocal'ı değiştirilir
    (get_case ve update_case_tracking aynı bağlamı görür). StaticPool şart —
    bağlantı başına ayrı :memory: DB açılmasın (test_g060 gerekçesi)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _dava_ekle(Fabrika, **alanlar) -> int:
    """Serialize'ın guard'sız float() çevirdiği tutarlar 0 verilir (G060 deseni)."""
    db = Fabrika()
    try:
        case = models.Case(tracking_no="HA.X.9002.2026", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def test_get_case_yerel_karar_durumunu_donuyor(oturum_fabrikasi):
    """Kırmızı-yeşil kanıtı (okuma bacağı): eski serialize sözlüğünde anahtar
    YOKTU — bu test eski kodda KeyError ile kırmızıdır."""
    cid = _dava_ekle(oturum_fabrikasi, yerel_karar_durumu="Beraat")
    kart = case_manager.get_case(cid)
    assert kart is not None
    assert kart["yerel_karar_durumu"] == "Beraat"


def test_get_case_bos_kayitta_anahtar_var_deger_none(oturum_fabrikasi):
    """İstinaf paritesi: değer girilmemişse anahtar yine döner, değer None —
    route ham dict'i döndürür (response_model yok), anahtar yoksa frontend'in
    kontrollü input'u undefined'a düşerdi."""
    cid = _dava_ekle(oturum_fabrikasi)
    kart = case_manager.get_case(cid)
    assert kart is not None
    assert "yerel_karar_durumu" in kart
    assert kart["yerel_karar_durumu"] is None
    assert kart["istinaf_karar_durumu"] is None  # kardeş desenle aynı


def test_update_case_tracking_yazip_get_case_okuyor(oturum_fabrikasi):
    """Uçtan uca: PATCH gövdesi (route dump'ı) → update_case_tracking → DB →
    get_case. Eski kodda update True döner ama whitelist süzdüğü için alan
    YAZILMAZDI — kırmızı. Değer resmi havuz yazımından (DEGER_HAVUZLARI)."""
    cid = _dava_ekle(oturum_fabrikasi)
    ok = case_manager.update_case_tracking(
        cid, _route_dump({"yerel_karar_durumu": "Red/Esastan"}), changed_by="g065-test"
    )
    assert ok is True
    kart = case_manager.get_case(cid)
    assert kart["yerel_karar_durumu"] == "Red/Esastan"


def test_update_case_tracking_null_ile_siler(oturum_fabrikasi):
    cid = _dava_ekle(oturum_fabrikasi, yerel_karar_durumu="Beraat")
    ok = case_manager.update_case_tracking(
        cid, _route_dump({"yerel_karar_durumu": None}), changed_by="g065-test"
    )
    assert ok is True
    db = oturum_fabrikasi()
    try:
        assert db.get(models.Case, cid).yerel_karar_durumu is None
    finally:
        db.close()


def test_update_whitelist_disi_yazmiyor_kardesler_calisiyor(oturum_fabrikasi):
    """Korunum, DB'ye kadar: (1) whitelist dışı `tracking_no` manager'a ham
    dict'le gelse de YAZILMAZ; (2) kardeş istinaf alanı eskisi gibi yazılır —
    yeni alan eklemek mevcut akışı bozmadı."""
    cid = _dava_ekle(oturum_fabrikasi)
    ok = case_manager.update_case_tracking(
        cid,
        {"tracking_no": "HACK", "istinaf_karar_durumu": "Başvuru Ret",
         "yerel_karar_durumu": "Kabul"},
        changed_by="g065-test",
    )
    assert ok is True
    db = oturum_fabrikasi()
    try:
        case = db.get(models.Case, cid)
        assert case.tracking_no == "HA.X.9002.2026"     # whitelist dışı — dokunulmadı
        assert case.istinaf_karar_durumu == "Başvuru Ret"
        assert case.yerel_karar_durumu == "Kabul"
    finally:
        db.close()
