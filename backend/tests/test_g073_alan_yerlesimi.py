"""G073 — Takip/kart alan yerleşimi: arabuluculuk + arşiv tarihi takip yoluna.

Ayrım şuydu: **karar künyesi → takip paneli**, **statik künye → kart**. Fikir
doğru, uygulamada üç sapma vardı (2026-08-19 incelemesi):

* `arabuluculuk_no` / `arabuluculuk_karar_tarihi` — davanın ÖN AŞAMASI (435 föy;
  148 kartta dava ile aynı kartta birleşti) kart alanı olarak duruyordu,
* `arsiv_tarihi` — dosyanın KAPANIŞ olayı, `KESINLESME`/`KAPALI` aşamalarının
  devamı, yine kartta,
* `dosya_son_durumu` — İKİ ekranda (panel yazıyor, kart 2026-08-19'da okuma
  amaçlı bastı). Backend'de zaten `TRACKING_FIELDS`te; kart kopyasını G074
  kaldırır (frontend işi).

Bu görev **hangi alanın hangi yazma yolundan geçtiğini** düzeltir; `cases`
şeması ve aktarımın kart eşlemesi DEĞİŞMEZ. Testlerin ağırlık merkezi bu
yüzden "ikinci yazıcı doğdu mu?" sorusudur — bu projede tekrar eden hata sınıfı
(en son `istinaf_basvuran_taraf`, 2026-08-19'da kapatıldı).

Katmanlar:

1. **Sözleşme** — `TRACKING_FIELDS` × şema × zorunlu alan kesişimi.
2. **sqlite** — `update_case_tracking` üç alanı gerçekten yazıyor; `case_history`
   ve `CaseStageLog` davranışı değişmedi.
3. **Aktarım** — sentetik paketle: aynı üç alan aktarımdan da yazılıyor ve
   İKİNCİ KOŞU hâlâ 0 değişiklik (idempotency regresyonu yok).
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from managers import case_manager, stage_decisions
from managers.case_manager import TRACKING_FIELDS, tracking_changes
from required_fields import REQUIRED_CASE_FIELDS
from schemas import CaseTrackingUpdate

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN gelir: `db_env`, pysqlite'ın
# örtük-commit tuhaflığını kapatan (isolation_level=None + elle BEGIN) reçeteyi
# taşıyor — ikinci bir kopya sessizce sahte SAVEPOINT'lerle koşardı (G064).
# Fixture'ı import edip parametre olarak istemek pytest'in standart deseni ama
# ruff bunu yeniden tanımlama sanar (F811) — kullanım yerinde susturulur.
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    _paket_yaz,
    _satir,
    db_env,
    uc_kart,
)
from scripts.hukdok_aktarim import CIKIS_TAMAM, aktarimi_kos

TASINAN_ALANLAR = ("arabuluculuk_no", "arabuluculuk_karar_tarihi", "arsiv_tarihi")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Sözleşme
# ═══════════════════════════════════════════════════════════════════════════

def test_uc_alan_takip_yazma_yolunda():
    """Kabul kriteri (kırmızı-yeşil kanıtı: eski listede üçü de YOKTU)."""
    for alan in TASINAN_ALANLAR:
        assert alan in TRACKING_FIELDS, alan
        assert alan in CaseTrackingUpdate.model_fields, f"{alan} şemada yok, route'tan geçemez"


def test_dosya_son_durumu_takipte_kaliyor():
    """Karar noktası 3: tekilleşme TAKİP yönünde — panel onu zaten YAZIYOR,
    kart yalnız okuyordu. Okuma kopyasını G074 (frontend) kaldırır."""
    assert "dosya_son_durumu" in TRACKING_FIELDS
    assert "dosya_son_durumu" in CaseTrackingUpdate.model_fields


def test_arabuluculuk_asama_kumesini_buyutmedi():
    """Karar noktası 1: (a) seçildi — `TRACKING_FIELDS`. (b) arabuluculuğu bir
    `case_stage_decisions` aşaması yapmak `DECISION_STAGES` kapalı kümesini ve
    dört G060 havuzunu büyütürdü; ayrı bir ADR hak eder, bu görevde kapsam dışı."""
    assert stage_decisions.DECISION_STAGES == ("YEREL", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME")
    assert "ARABULUCULUK" not in stage_decisions.DECISION_STAGES
    assert set(stage_decisions.STAGE_DECISION_LISTS) == set(stage_decisions.DECISION_STAGES)


def _fotograf_hedefleri():
    return {
        kolon for eslesme in stage_decisions._PHOTO_COLUMNS.values() for kolon in eslesme.values()
    }


def test_uc_alan_asama_fotografinin_hedefi_degil():
    """"İkinci yazıcı doğdu mu?" sınavı: üç alanın hiçbiri `_PHOTO_COLUMNS`
    hedefi DEĞİL, yani takip paneli bu üç kolonun tek etkileşimli yazıcısı."""
    assert not _fotograf_hedefleri() & set(TASINAN_ALANLAR)


def test_takip_fotograf_ortusmesi_karar_kunyesiyle_sinirli_kaldi():
    """Takip paneli ile aşama fotoğrafı ZATEN aynı karar künyesi kolonlarına
    yazıyor (G062 bilinçli bıraktı, birleşik yol G065'in işi; G066 ikisini aynı
    kapalı havuz kapısına bağladı). Bu görev o kümeyi BÜYÜTMEDİ — kesişim hâlâ
    yalnız karar künyesi; üç yeni alanın hiçbiri kesişime girmiyor."""
    kesisim = _fotograf_hedefleri() & set(TRACKING_FIELDS)
    assert kesisim == {
        "karar_no", "karar_tarihi", "yerel_karar_durumu",
        "istinaf_mahkemesi", "istinaf_esas_no", "istinaf_karar_no",
        "istinaf_karar_tarihi", "istinaf_karar_durumu", "istinaf_teblig_tarihi",
        "istinaf_karar_aciklama",
        "temyiz_mahkemesi", "temyiz_esas_no", "temyiz_karar_no",
        "temyiz_karar_tarihi", "temyiz_karar_durumu", "temyiz_teblig_tarihi",
        "temyiz_eden_durumu", "temyiz_karar_aciklama",
        "karar_duzeltme_esas_no", "karar_duzeltme_karar_no", "karar_duzeltme_tarihi",
        "karar_duzeltme_durumu", "karar_duzeltme_teblig_tarihi", "karar_duzeltme_aciklama",
    }
    assert not kesisim & set(TASINAN_ALANLAR)
    # 19.08'de kapatılan kusurun nöbetçisi: `istinaf_basvuran_taraf` fotoğraf
    # hedefidir ve takip listesine GİRMEMİŞTİR.
    assert "istinaf_basvuran_taraf" in _fotograf_hedefleri()
    assert "istinaf_basvuran_taraf" not in TRACKING_FIELDS


def test_zorunlu_alan_kesisimi_bos_kaldi():
    """Bayat bayrak savunması (G046 2. maddesi): takip formu zorunlu alan
    yazmaya başlarsa `missing_required_bucket` bayat kalırdı."""
    kesisim = set(TRACKING_FIELDS) & {f["field"] for f in REQUIRED_CASE_FIELDS}
    assert kesisim == set()


def test_tracking_changes_uc_alani_tasiyor():
    veri = CaseTrackingUpdate(
        arabuluculuk_no="ARB-2024/17",
        arabuluculuk_karar_tarihi=date(2024, 5, 6),
        arsiv_tarihi=date(2026, 1, 2),
    ).model_dump(exclude_unset=True)
    assert dict(tracking_changes(veri)) == {
        "arabuluculuk_no": "ARB-2024/17",
        "arabuluculuk_karar_tarihi": date(2024, 5, 6),
        "arsiv_tarihi": date(2026, 1, 2),
    }


def test_gonderilmeyen_alan_dokunulmuyor():
    """exclude_unset sözleşmesi üç yeni alan için de geçerli."""
    veri = CaseTrackingUpdate(arsiv_tarihi=date(2026, 1, 2)).model_dump(exclude_unset=True)
    assert [alan for alan, _ in tracking_changes(veri)] == ["arsiv_tarihi"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — update_case_tracking (sqlite)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def fabrika(monkeypatch):
    """In-memory sqlite; `case_manager.SessionLocal` bağlanır (G066 deseni)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _dava(Fabrika, **alanlar) -> int:
    db = Fabrika()
    try:
        case = models.Case(tracking_no="HA.G073.1", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _kart(Fabrika, case_id):
    db = Fabrika()
    try:
        return db.get(models.Case, case_id)
    finally:
        db.close()


def test_panel_uc_alani_yaziyor(fabrika):
    case_id = _dava(fabrika)

    assert case_manager.update_case_tracking(case_id, {
        "arabuluculuk_no": "ARB-2024/17",
        "arabuluculuk_karar_tarihi": date(2024, 5, 6),
        "arsiv_tarihi": date(2026, 1, 2),
    }, changed_by="test") is True

    kart = _kart(fabrika, case_id)
    assert kart.arabuluculuk_no == "ARB-2024/17"
    assert kart.arabuluculuk_karar_tarihi == date(2024, 5, 6)
    assert kart.arsiv_tarihi == date(2026, 1, 2)


def test_none_gonderilen_alan_temizlenir(fabrika):
    """Faz 1 sözleşmesi: gönderilmeyen alan dokunulmaz, None SİLER."""
    case_id = _dava(fabrika, arsiv_tarihi=date(2026, 1, 2), arabuluculuk_no="ARB-1")

    assert case_manager.update_case_tracking(
        case_id, {"arsiv_tarihi": None}, changed_by="test") is True

    kart = _kart(fabrika, case_id)
    assert kart.arsiv_tarihi is None
    assert kart.arabuluculuk_no == "ARB-1", "gönderilmeyen alan silinmiş"


def test_case_history_davranisi_degismedi(fabrika):
    """Kabul kriteri: `update_case_tracking` bugün `case_history` YAZMIYOR
    (G065'in işi) — bu görev onu ÇÖZMEZ, sadece bozmadığını gösterir.
    Aşama değişmediği için `CaseStageLog` da doğmaz."""
    case_id = _dava(fabrika)

    case_manager.update_case_tracking(case_id, {
        "arabuluculuk_no": "ARB-2024/17", "arsiv_tarihi": date(2026, 1, 2),
    }, changed_by="test")

    db = fabrika()
    try:
        assert db.query(models.CaseHistory).count() == 0
        assert db.query(models.CaseStageLog).count() == 0
    finally:
        db.close()


def test_asama_degisince_stage_log_hala_dusuyor(fabrika):
    """Nöbetçi: üç alanın eklenmesi mevcut `CaseStageLog` yolunu bozmadı."""
    case_id = _dava(fabrika, case_stage="YEREL")

    case_manager.update_case_tracking(case_id, {
        "case_stage": "KAPALI", "arsiv_tarihi": date(2026, 1, 2),
    }, changed_by="test")

    db = fabrika()
    try:
        loglar = db.query(models.CaseStageLog).all()
        assert [log.stage for log in loglar] == ["KAPALI"]
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Aktarım — üç alan yazılmaya devam ediyor, ikinci koşu 0 değişiklik
# ═══════════════════════════════════════════════════════════════════════════

AKTARIM_BASLIKLARI = [
    "SistemNo", "TKU", "Dosya No",
    "Arşiv Tarihi", "Arabuluculuk Numarası", "Arabuluculuk Karar Tarihi",
]


def test_aktarim_uc_alani_yazmaya_devam_ediyor_ve_idempotent(uc_kart, tmp_path):  # noqa: F811
    """Kabul kriteri: aktarım bu üç kolona yazmaya DEVAM eder (kolonlar yerinde
    kaldı) ve aynı girdiyle ikinci koşu hâlâ 0 değişiklik üretir.

    Bu İKİ YAZICI değildir: `_PHOTO_COLUMNS` gibi bir senkron yok — aktarım
    toplu bir veri yükleyicisidir, panel ise tekil düzeltme yolu; ikisi de aynı
    kolona yazar ama biri diğerinin yazdığını TÜRETMEZ.
    """
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("SSTMN-1", "D-1", **{"Arşiv Tarihi": "15.03.2021",
                                    "Arabuluculuk Numarası": "ARB-2020/9",
                                    "Arabuluculuk Karar Tarihi": "01.02.2020"}),
        _satir("SSTMN-2", "D-2", **{"Arabuluculuk Numarası": "ARB-2021/4"}),
    ], basliklar=AKTARIM_BASLIKLARI)

    ilk = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM and ilk.yazildi

    db = uc_kart()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        assert kartlar["D-1"].arsiv_tarihi == date(2021, 3, 15)
        assert kartlar["D-1"].arabuluculuk_no == "ARB-2020/9"
        assert kartlar["D-1"].arabuluculuk_karar_tarihi == date(2020, 2, 1)
        assert kartlar["D-2"].arabuluculuk_no == "ARB-2021/4"
        fotograf = {
            c.id: (c.arsiv_tarihi, c.arabuluculuk_no, c.arabuluculuk_karar_tarihi)
            for c in kartlar.values()
        }
    finally:
        db.close()

    ikinci = aktarimi_kos(uc_kart, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert ikinci.alan_degisikligi == 0 and ikinci.kart_degisen == 0

    db = uc_kart()
    try:
        assert {
            c.id: (c.arsiv_tarihi, c.arabuluculuk_no, c.arabuluculuk_karar_tarihi)
            for c in db.query(models.Case).all()
        } == fotograf
    finally:
        db.close()


def test_aktarim_kart_eslemesi_bu_turda_degismedi():
    """Görev dosyasının "dokunma" kalemi: `KART_ALANLARI` bu üç kolona yazmaya
    devam eder — alan takip yoluna geçti diye aktarımdan ÇIKARILMADI."""
    from scripts import hukdok_aktarim

    yazilanlar = set(hukdok_aktarim.KART_ALANLARI) | set(hukdok_aktarim.KART_TURETILEN)
    assert set(TASINAN_ALANLAR) <= yazilanlar
