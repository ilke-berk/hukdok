"""G072 — Aşama/karar tarihçesinin OKUMA yolu: `GET /api/cases/{id}/stage-decisions`.

`case_stage_decisions` G062'de açıldı ve 2026-08-19 HUKDOK aktarımıyla doldu
(lokal ölçüm: 4.971 satır — YEREL 3.098, İSTİNAF 1.236, TEMYİZ 574, K.Düzeltme
63) ama tablonun NE ROUTE'U NE EKRANI vardı: takip paneli yalnız `cases`
üzerindeki tek-slot FOTOĞRAFI gösteriyordu, aynı aşamanın önceki kararı
(kanıt vakası id-2271: Danıştay 2023 Bozma + 2026 Onama) hiç görünmüyordu.

Bu görev SALT OKUMA'dır: yazma yolu (`add_stage_decision`,
`delete_stage_decision`, `_resync_stage_photo`) ve `case_stage_decisions`
şeması değişmedi — son bölüm bunu mekanik olarak kapatır.

Katmanlar (test_g062 düzeni):

1. **Sözleşme** — şema + route kaydı (response_model bağlı mı).
2. **sqlite (StaticPool)** — davranış: route fonksiyonu DOĞRUDAN çağrılır,
   `routes.cases.SessionLocal` fixture'ın session maker'ına yönlendirilir
   (test_g016 deseni; TestClient + MSAL yığını gerekmez).
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import seed_data
from managers.stage_decisions import DECISION_STAGES, add_stage_decision

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"

_KARAR_LISTELERI = (
    (models.LocalDecision, seed_data.LOCAL_DECISIONS),
    (models.AppealDecision, seed_data.APPEAL_DECISIONS),
    (models.CassationDecision, seed_data.CASSATION_DECISIONS),
    (models.RevisionDecision, seed_data.REVISION_DECISIONS),
)


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Sözleşme — şema + route kaydı
# ═══════════════════════════════════════════════════════════════════════════

def test_yanit_semasi_iki_listeyi_ayri_tutuyor():
    """Karar künyesi ile NUMARANIN tarihçesi tek listede birleşmez (karar noktası 2)."""
    from schemas import CaseStageDecisionsResponse

    bos = CaseStageDecisionsResponse(case_id=7)
    assert bos.decisions == [] and bos.onceki_esaslar == []
    alanlar = set(CaseStageDecisionsResponse.model_fields)
    assert alanlar == {"case_id", "decisions", "onceki_esaslar"}


def test_esas_numarasi_semasi_asama_etiketini_tasiyor():
    """Arayüz "hangi aşamanın numarasıydı" diyebilsin diye `stage` şemada."""
    from schemas import CaseEsasNumberRead

    satir = CaseEsasNumberRead(id=1, case_id=2, esas_no="2017/325", stage="ONCEKI")
    assert satir.is_current is False
    assert CaseEsasNumberRead.model_config.get("from_attributes") is True


def test_route_kayitli_ve_response_model_bagli():
    from schemas import CaseStageDecisionsResponse
    from routes import cases as cases_route

    rota = [
        r for r in cases_route.router.routes
        if getattr(r, "path", None) == "/api/cases/{case_id}/stage-decisions"
    ]
    assert len(rota) == 1, "stage-decisions route'u kayıtlı değil"
    assert set(rota[0].methods) == {"GET"}
    assert rota[0].response_model is CaseStageDecisionsResponse


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env(monkeypatch):
    """sqlite + migrasyon index'leri + G060 seed'leri; route SessionLocal'ı bağlanır."""
    from routes import cases as cases_route

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops("case_stage_decisions"):
            conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = maker()
    try:
        for model, degerler in _KARAR_LISTELERI:
            for idx, (code, name) in enumerate(degerler):
                db.add(model(code=code, name=name, active=True, sequence=idx))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(cases_route, "SessionLocal", maker)
    yield maker
    engine.dispose()


def _dava(db, tracking_no="HA.X.0001.2026", tenant_id=T1, **extra):
    case = models.Case(
        tracking_no=tracking_no, status="DERDEST",
        maddi_tazminat=0, manevi_tazminat=0, tenant_id=tenant_id, **extra,
    )
    db.add(case)
    db.flush()
    return case


def _oku(case_id, tenant_id=T1):
    from routes.cases import api_get_case_stage_decisions

    return api_get_case_stage_decisions(case_id=case_id, tenant_id=tenant_id)


# ─── Satırlar görünüyor mu ───────────────────────────────────────────────────

def test_asama_satirlari_kronolojik_ve_sira_no_ile_donuyor(db_env):
    """Kabul kriteri: satırlar `sira_no` sırasıyla; aşamalar arası sıra
    alfabetik DEĞİL kronolojik (alfabetikte istinaf → k.düzeltme → temyiz →
    yerel çıkardı, yani zaman çizgisi tersine dönerdi)."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma")
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama")
        add_stage_decision(db, case, stage="KARAR_DUZELTME", karar_durumu="Karar Düzeltme Ret")
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        add_stage_decision(db, case, stage="ISTINAF", karar_durumu="Başvuru Ret")
        db.commit()
        case_id = case.id
    finally:
        db.close()

    yanit = _oku(case_id)
    assert [(d.stage, d.sira_no) for d in yanit.decisions] == [
        ("YEREL", 1), ("ISTINAF", 1), ("TEMYIZ", 1), ("TEMYIZ", 2), ("KARAR_DUZELTME", 1),
    ]
    assert yanit.case_id == case_id


def test_id_2271_ayni_asamanin_iki_karari_da_yanitta(db_env):
    """Görevin varlık sebebi: fotoğraf yalnız Onama'yı gösteriyordu, Bozma
    tabloda saklı kalıyordu. Okuma yolu ikisini de veriyor."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(
            db, case, stage="TEMYIZ", mahkeme="Danıştay 8. Daire", esas_no="2023/10",
            karar_no="2023/55", karar_durumu="Bozma", dogrulama_durumu="BELGE",
            source="g072-test",
        )
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama", dogrulama_durumu="UYAP")
        db.commit()
        case_id = case.id
        fotograf = case.temyiz_karar_durumu
    finally:
        db.close()

    yanit = _oku(case_id)
    assert [d.karar_durumu for d in yanit.decisions] == ["Bozma", "Onama"]
    assert fotograf == "Onama", "tek-slot fotoğraf hâlâ son kararı gösteriyor olmalı"

    bozma = yanit.decisions[0]
    assert (bozma.mahkeme, bozma.esas_no, bozma.karar_no) == ("Danıştay 8. Daire", "2023/10", "2023/55")
    assert (bozma.dogrulama_durumu, bozma.source) == ("BELGE", "g072-test")


def test_satirda_kabul_kriterinin_saydigi_tum_alanlar_var(db_env):
    from datetime import date

    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(
            db, case, stage="ISTINAF", mahkeme="İstanbul BAM 9. HD", esas_no="2025/1",
            karar_no="2025/2", karar_tarihi=date(2025, 3, 4), karar_durumu="Başvuru Ret",
            teblig_tarihi=date(2025, 4, 1), basvuran_taraf="Davalı",
            aciklama="süresinde başvuru", dogrulama_durumu="UYAP", source="HUKDOK_TESLIM_2026-08-10",
        )
        db.commit()
        case_id = case.id
    finally:
        db.close()

    satir = _oku(case_id).decisions[0]
    assert satir.mahkeme == "İstanbul BAM 9. HD"
    assert (satir.esas_no, satir.karar_no) == ("2025/1", "2025/2")
    assert (satir.karar_tarihi, satir.teblig_tarihi) == (date(2025, 3, 4), date(2025, 4, 1))
    assert satir.karar_durumu == "Başvuru Ret"
    assert satir.basvuran_taraf == "Davalı"
    assert satir.aciklama == "süresinde başvuru"
    assert satir.dogrulama_durumu == "UYAP"
    assert satir.source == "HUKDOK_TESLIM_2026-08-10"
    assert satir.created_at is not None


def test_tanimsiz_asama_etiketi_satiri_yutmuyor(db_env):
    """Ham INSERT ya da ileride eklenen bir aşama okuma yolunda KAYBOLMAZ —
    sıralama `else_` ile sona düşürür, filtre uygulanmaz."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.add(models.CaseStageDecision(case_id=case.id, stage="YENI_ASAMA", sira_no=1))
        db.commit()
        case_id = case.id
    finally:
        db.close()

    assert [d.stage for d in _oku(case_id).decisions] == ["YEREL", "YENI_ASAMA"]


def test_tarihcesi_olmayan_dava_bos_listeyle_200(db_env):
    """Kabul kriteri: veri yokluğu hata değildir."""
    db = db_env()
    try:
        case = _dava(db)
        db.commit()
        case_id = case.id
    finally:
        db.close()

    yanit = _oku(case_id)
    assert yanit.decisions == [] and yanit.onceki_esaslar == []


# ─── Önceki esaslar ayrı alanda ──────────────────────────────────────────────

def test_onceki_esaslar_ayri_alanda_guncel_satir_girmiyor(db_env):
    """Kabul kriteri: `is_current` satırı bu listeye GİRMEZ — o zaten
    `cases.esas_no`nun kendisi (türetilmiş kopyası)."""
    db = db_env()
    try:
        case = _dava(db)
        db.add_all([
            models.CaseEsasNumber(case_id=case.id, esas_no="2017/325", stage="ONCEKI",
                                  court="Ankara 3. Asliye Hukuk", is_current=False,
                                  source="HUKDOK_TESLIM_2026-08-10"),
            models.CaseEsasNumber(case_id=case.id, esas_no="2024/145", stage="YEREL",
                                  is_current=True, source="add_case"),
        ])
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.commit()
        case_id = case.id
    finally:
        db.close()

    yanit = _oku(case_id)
    assert [(e.esas_no, e.stage) for e in yanit.onceki_esaslar] == [("2017/325", "ONCEKI")]
    assert yanit.onceki_esaslar[0].court == "Ankara 3. Asliye Hukuk"
    assert yanit.onceki_esaslar[0].is_current is False
    # Karar satırlarıyla KARIŞMADI: esas tarihçesi decisions'a sızmıyor
    assert [d.stage for d in yanit.decisions] == ["YEREL"]


def test_onceki_esaslar_sadece_bu_davanin(db_env):
    db = db_env()
    try:
        a = _dava(db, tracking_no="HA.X.0001.2026")
        b = _dava(db, tracking_no="HA.X.0002.2026")
        db.add_all([
            models.CaseEsasNumber(case_id=a.id, esas_no="2017/1", stage="ONCEKI", is_current=False),
            models.CaseEsasNumber(case_id=b.id, esas_no="2018/2", stage="ONCEKI", is_current=False),
        ])
        add_stage_decision(db, b, stage="YEREL", karar_durumu="Kabul")
        db.commit()
        a_id = a.id
    finally:
        db.close()

    yanit = _oku(a_id)
    assert [e.esas_no for e in yanit.onceki_esaslar] == ["2017/1"]
    assert yanit.decisions == []


# ─── Tenant kapısı + 404 (G016 dersi) ────────────────────────────────────────

def _durum(case_id, tenant_id):
    with pytest.raises(HTTPException) as hata:
        _oku(case_id, tenant_id=tenant_id)
    return hata.value.status_code


def test_baska_tenantin_davasi_404_ve_satir_sizmiyor(db_env):
    db = db_env()
    try:
        case = _dava(db, tenant_id=T2)
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.commit()
        case_id = case.id
    finally:
        db.close()

    assert _durum(case_id, T1) == 404
    assert len(_oku(case_id, tenant_id=T2).decisions) == 1


def test_paylasimli_havuz_kaydi_iki_tenanta_da_aciktir(db_env):
    """tenant_id=NULL = paylaşımlı legacy (auth_helpers sözleşmesi); 8.156 föylük
    aktarım tam olarak bu kovaya yazdı."""
    db = db_env()
    try:
        case = _dava(db, tenant_id=None)
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.commit()
        case_id = case.id
    finally:
        db.close()

    assert len(_oku(case_id, tenant_id=T1).decisions) == 1
    assert len(_oku(case_id, tenant_id=T2).decisions) == 1


def test_silinmis_ve_olmayan_dava_404(db_env):
    from datetime import datetime

    db = db_env()
    try:
        case = _dava(db, deleted_at=datetime(2026, 8, 1, 10, 0))
        add_stage_decision(db, case, stage="YEREL", karar_durumu="Kabul")
        db.commit()
        silinmis_id = case.id
    finally:
        db.close()

    assert _durum(silinmis_id, T1) == 404
    assert _durum(999_999, T1) == 404


# ─── Salt okuma güvencesi ────────────────────────────────────────────────────

def test_okuma_hicbir_seyi_degistirmiyor(db_env):
    """Kabul kriteri: bu görev SALT OKUMA — çağrı satır sayısını da tek-slot
    fotoğrafı da değiştirmez (fotoğraf senkronu okuma yolunda ÇALIŞMAZ)."""
    db = db_env()
    try:
        case = _dava(db)
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma")
        add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Onama")
        db.commit()
        case_id = case.id
        onceki = (case.temyiz_karar_durumu, case.temyiz_karar_no, case.temyiz_karar_tarihi)
    finally:
        db.close()

    _oku(case_id)
    _oku(case_id)

    db = db_env()
    try:
        case = db.get(models.Case, case_id)
        assert (case.temyiz_karar_durumu, case.temyiz_karar_no, case.temyiz_karar_tarihi) == onceki
        assert db.query(models.CaseStageDecision).count() == 2
    finally:
        db.close()


def test_yazma_yolu_route_katmanindan_cagrilmiyor():
    """Route yalnız okuma fonksiyonunu import eder; yazma/silme yolu ve
    fotoğraf senkronu bu dosyada GEÇMEZ (görev dosyasının "dokunma" listesi)."""
    from pathlib import Path

    import routes.cases as cases_route

    kaynak = Path(cases_route.__file__).read_text(encoding="utf-8")
    for yasak in ("add_stage_decision", "delete_stage_decision", "_resync_stage_photo"):
        assert yasak not in kaynak, f"route katmanı yazma yolunu çağırıyor: {yasak}"
    assert "get_stage_decisions" in kaynak


def test_asama_siralamasi_decision_stages_ten_turetiliyor():
    """İkinci bir sıra listesi yok: rank `DECISION_STAGES`in kendisidir —
    yeni bir aşama eklendiği anda okuma sırası da onu kapsar."""
    from managers.stage_decisions import _STAGE_RANK

    assert DECISION_STAGES == ("YEREL", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME")
    assert _STAGE_RANK == {stage: i for i, stage in enumerate(DECISION_STAGES)}
