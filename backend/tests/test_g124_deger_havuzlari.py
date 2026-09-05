"""G124 — Değer havuzları: para birimi, tıbbi beşli çok değerli listeler, mahkeme
ve idare önerileri, taraf rolüne üç değer (05.09.2026 kullanıcı kararı).

Ölçüm (04.09 paketi): tıbbi beşli " ; " ile 9 parçaya kadar çok değerli, 200/300
sınırı 18 hücreyi kırpıyordu; İddia Edilen Kusur 9, Tıbbi Süreç 97, Tıbbi Olay
667, Hastada Oluşan Zarar 258, Uygulanan Yöntem 260 atomik değer; Temyiz
Mahkemesi 41, İstinaf Mahkemesi 221, Davalı İdare 10; Taraf Sıfatı'nda üç rol
listede yoktu. Kararlar: sınır kalkar, listeler PAKETTEN kurulur (yazımlar
olduğu gibi — "hatalısını geçirelim"), çok değerli alan parça parça doğrulanır.

**TEST VERİSİ KURALI (A.2):** gerçek paket repoya GİRMEZ; sentetik paket.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import case_manager, seed_data
from managers.reference_lists import DEPENDENCIES, LIST_REGISTRY, LIST_TITLES
from managers.stage_decisions import InvalidDecisionStatusError
from schemas import CaseTrackingUpdate
from scripts import deger_havuzu_seed as seed
from services.multi_value import SEPARATOR, join_values, split_values

YENI_LISTELER = {
    "currencies": models.Currency,
    "medical_processes": models.MedicalProcess,
    "medical_events": models.MedicalEvent,
    "patient_harms": models.PatientHarm,
    "applied_methods": models.AppliedMethod,
    "cassation_courts": models.CassationCourt,
    "appeal_courts": models.AppealCourt,
    "defendant_administrations": models.DefendantAdministration,
}
TIBBI_BESLI = ("tibbi_surec", "tibbi_olay", "iddia_edilen_kusur", "hastada_olusan_zarar", "uygulanan_yontem")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Sözleşme kilitleri (DB yok)
# ═══════════════════════════════════════════════════════════════════════════

def test_split_join_sozlesmesi():
    assert split_values("Komplikasyon Yönetimi ; Takip Eksikliği;;takip eksikliği ") == [
        "Komplikasyon Yönetimi", "Takip Eksikliği"]
    assert split_values("Kaynamama / Yanlış Kaynama, Gecikmiş") == ["Kaynamama / Yanlış Kaynama, Gecikmiş"]
    assert split_values(None) == [] and split_values(" ; ") == []
    assert join_values(["A", " B ", ""]) == f"A{SEPARATOR}B"
    assert join_values([]) is None


def test_sekiz_liste_registry_deps_titles_ve_dynamicconfig():
    from managers.config_manager import DynamicConfig

    for key, model in YENI_LISTELER.items():
        assert LIST_REGISTRY[key].model is model and model.__tablename__ == key
        assert key in DEPENDENCIES and key in LIST_TITLES
        assert hasattr(DynamicConfig, LIST_REGISTRY[key].setter), key
        assert hasattr(DynamicConfig, f"get_{key}"), key
        code_col = model.code.property.columns[0]
        assert code_col.unique and not code_col.nullable
    # Bağlar: para birimi + iki mahkeme + tıbbi dördü kart kolonuna, davalı idare bağsız.
    assert [(d.model, d.column) for d in DEPENDENCIES["currencies"]] == [(models.Case, "para_birimi")]
    assert [(d.model, d.column) for d in DEPENDENCIES["cassation_courts"]] == [(models.Case, "temyiz_mahkemesi")]
    assert [(d.model, d.column) for d in DEPENDENCIES["appeal_courts"]] == [(models.Case, "istinaf_mahkemesi")]
    assert [(d.model, d.column) for d in DEPENDENCIES["medical_events"]] == [(models.Case, "tibbi_olay")]
    assert DEPENDENCIES["defendant_administrations"] == []


def test_para_birimi_seed_sabiti_tl_varsayilan():
    assert seed_data.CURRENCIES[0] == ("TL", "TL")
    assert {c for c, _ in seed_data.CURRENCIES} == {"TL", "USD", "EUR"}
    assert seed_data.VARSAYILAN_PARA_BIRIMI == "TL"


def test_tibbi_besli_kolon_siniri_kalkti_ve_migrasyon_var():
    for kolon in TIBBI_BESLI:
        assert getattr(models.Case, kolon).property.columns[0].type.length is None, kolon
    alters = [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == "cases"
              for sql in op[2] if sql.startswith("ALTER TABLE cases ALTER COLUMN")]
    assert {sql.split()[5] for sql in alters} == set(TIBBI_BESLI)
    assert all(sql.endswith("TYPE VARCHAR") for sql in alters)


def test_takip_whitelist_ve_sema_yeni_alanlari_kapsiyor():
    for alan in TIBBI_BESLI + ("dava_degeri", "para_birimi"):
        assert alan in case_manager.TRACKING_FIELDS, alan
        assert alan in CaseTrackingUpdate.model_fields, alan
    assert case_manager._EVENT_LIST_COLUMNS["para_birimi"] == (models.Currency, "currencies")
    assert set(case_manager._MULTI_LIST_COLUMNS) == set(TIBBI_BESLI)
    assert case_manager._MULTI_LIST_COLUMNS["iddia_edilen_kusur"] == (models.AllegedFault, "alleged_faults")


def test_config_route_lari_kayitli():
    from routes.config import router

    yollar = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    for key in YENI_LISTELER:
        assert (f"/api/config/{key}", ("GET",)) in yollar, key
        assert (f"/api/config/{key}", ("POST",)) in yollar, key
        assert (f"/api/config/{key}/{{code}}", ("DELETE",)) in yollar, key


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite davranışı — çok değerli doğrulama + havuz seed'i
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _liste_doldur(db, model, adlar):
    for i, ad in enumerate(adlar):
        db.add(model(code=f"K{i}", name=ad, active=True, sequence=i))
    db.flush()


def test_cok_degerli_dogrulama_parca_parca(db_env):
    db = db_env()
    try:
        _liste_doldur(db, models.AllegedFault, ["Uygulama Hatası", "Takip Eksikliği"])
        # tanınan parçalar KANONİK yazımla birleşir (büyük/küçük harf yutulur)
        assert case_manager.validated_multi_list_value(
            db, "iddia_edilen_kusur", "uygulama hatası; Takip Eksikliği ;") == \
            f"Uygulama Hatası{SEPARATOR}Takip Eksikliği"
        # boş → None (alan temizlenir)
        assert case_manager.validated_multi_list_value(db, "iddia_edilen_kusur", " ; ") is None
        # tanınmayan parça → 400 sınıfı hata (tahmin yasağı)
        with pytest.raises(InvalidDecisionStatusError, match="Aydınlatma"):
            case_manager.validated_multi_list_value(db, "iddia_edilen_kusur", "Uygulama Hatası ; Aydınlatma")
        # liste BOŞSA doğrulama atlanır, metin normalize edilerek geçer
        assert case_manager.validated_multi_list_value(db, "tibbi_olay", "Down Sendromu;;Omuz Distosisi") == \
            f"Down Sendromu{SEPARATOR}Omuz Distosisi"
        # çok değerli olmayan kolon dokunulmadan geçer
        assert case_manager.validated_multi_list_value(db, "karar_no", "2024/1") == "2024/1"
    finally:
        db.close()


def test_para_birimi_kapali_liste_kapisi(db_env):
    db = db_env()
    try:
        _liste_doldur(db, models.Currency, ["TL", "USD", "EUR"])
        assert case_manager.validated_event_list_value(db, "para_birimi", "USD") == "USD"
        with pytest.raises(InvalidDecisionStatusError):
            case_manager.validated_event_list_value(db, "para_birimi", "GBP")
    finally:
        db.close()


def _paket_yaz(yol, satirlar, basliklar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(basliklar)
    for satir in satirlar:
        ws.append([satir.get(b) for b in basliklar])
    wb.save(yol)
    wb.close()
    return Path(yol)


BASLIKLAR = ["SistemNo", "Tıbbi Olay", "İddia Edilen Kusur", "Temyiz Mahkemesi",
             "İstinaf Karar Durumu", "Davalı İdare", "Para Birimi TL"]


def test_havuz_seedi_paketten_kurar_yazimi_korur_idempotent(db_env, tmp_path):
    paket = _paket_yaz(tmp_path / "p.xlsx", [
        {"SistemNo": "H-1", "Tıbbi Olay": "Down Sendromu ; Omuz Distosisi",
         "İddia Edilen Kusur": "Uygulama Hatası ; Yeni Kusur", "Temyiz Mahkemesi": "YARGITAY .....HD",
         "İstinaf Karar Durumu": "Karar Aaleyhe", "Davalı İdare": "SAĞLIK BAKANLIĞI", "Para Birimi TL": "TL"},
        {"SistemNo": "H-2", "Tıbbi Olay": "Omuz Distosisi", "İddia Edilen Kusur": "-",
         "İstinaf Karar Durumu": "Karar-Aleyhe", "Davalı İdare": "SAĞLIK BAKANLIĞI ; VAN VALİLİĞİ",
         "Para Birimi TL": "TL"},
    ], BASLIKLAR)
    db = db_env()
    try:
        _liste_doldur(db, models.AllegedFault, ["Uygulama Hatası"])
        db.commit()
    finally:
        db.close()

    kuru = seed.havuzlari_kur(db_env, girdi=paket)                     # kuru koşu
    db = db_env()
    try:
        assert db.query(models.MedicalEvent).count() == 0              # yazılmadı
    finally:
        db.close()
    yeni = {s.liste_adi: s.yeni for s in kuru}
    assert yeni["medical_events"] == 2 and yeni["alleged_faults"] == 1   # "-" yer tutucu düştü
    assert yeni["cassation_courts"] == 1 and yeni["defendant_administrations"] == 2
    assert yeni["appeal_decisions"] == 2                                # bozuk yazımlar GEÇER
    assert yeni["currencies"] == 0 or yeni["currencies"] == 1           # TL seed'lenmemişse eklenir
    assert next(s for s in kuru if s.liste_adi == "medical_processes").sutun is None   # pakette yok

    seed.havuzlari_kur(db_env, girdi=paket, apply=True)
    ikinci = seed.havuzlari_kur(db_env, girdi=paket, apply=True)
    assert sum(s.yeni for s in ikinci) == 0                             # idempotent

    db = db_env()
    try:
        olaylar = {r.name: r.sequence for r in db.query(models.MedicalEvent)}
        assert olaylar == {"Omuz Distosisi": 0, "Down Sendromu": 1}   # sıklık sırası
        assert {r.name for r in db.query(models.AllegedFault)} == {"Uygulama Hatası", "Yeni Kusur"}
        assert [r.name for r in db.query(models.CassationCourt)] == ["YARGITAY .....HD"]  # yazım korunur
        kodlar = {r.name: r.code for r in db.query(models.AppealDecision)}
        assert kodlar["Karar Aaleyhe"] != kodlar["Karar-Aleyhe"]        # kod çakışması sonekle çözülür
        assert {r.name for r in db.query(models.DefendantAdministration)} == {"SAĞLIK BAKANLIĞI", "VAN VALİLİĞİ"}
    finally:
        db.close()


def test_taraf_rolu_seed_ucu_iceriyor():
    import inspect

    kaynak = inspect.getsource(seed_data._seed_party_roles)
    for rol in ("Aleyhine Başvurulan", "Alacaklı", "Katılan"):
        assert f'"{rol}"' in kaynak, rol
