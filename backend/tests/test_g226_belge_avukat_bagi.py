"""G226 — belge hattı avukatı `lawyers.id` ile taşır (`case_documents.lawyer_id`).

Kilitlenenler:
1. Şema: `lawyer_id` FK `lawyers.id` ON DELETE RESTRICT; kolon op'u + AYRI koşulsuz index op'u.
2. Toleranslı çözüm (`document_pipeline.lawyer_id_for_text`): "TUGCE UNGOR" ↔ "Tuğçe Ungör Yanık".
3. Yazma / e-posta / müvekkil bilgilendirme yolları `lawyer_id` taşır; ad + e-posta `lawyers` satırından.
4. Ölü `avukat_kodu` artıkları kalktı (/confirm Form alanı, auto-enrich avukat dalı, şema alanı,
   prompt, `send_document_notification` parametresi).
5. Doldurma betiği `scripts/belge_avukat_bagi.py`: kuru koşu varsayılan, eski kod haritası,
   eşleşmeyen raporu, `avukat_kodu`'ya dokunmama, idempotentlik, envanter İHLAL'inde geri alma.

SQLite'ta `translate()` yoktur (avukat envanteri filtresi kullanır) — fixture Python ile tanımlar.
"""
import asyncio
import inspect
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers.config_manager import DynamicConfig


def _translate(deger, kaynak, hedef):
    if deger is None:
        return None
    return deger.translate(str.maketrans(kaynak, hedef))


@pytest.fixture()
def fabrika():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.create_function("translate", 3, _translate)
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    config = DynamicConfig.get_instance()
    onceki = config.get_lawyers()
    config.set_lawyers([])
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    config.set_lawyers(onceki)
    engine.dispose()


@pytest.fixture()
def avukatlar(fabrika):
    db = fabrika()
    tugce = models.Lawyer(code="TUGCEUNG", name="Tuğçe Ungör Yanık", email="tugce@ofis.test",
                          active=True, sequence=1)
    serap = models.Lawyer(code="SERAPTUR", name="Serap Turgal", email="serap@ofis.test",
                          active=True, sequence=2)
    baris = models.Lawyer(code="BBA", name="Barış Yücel", active=True, sequence=3)
    aysegul = models.Lawyer(code="AYSEGULH", name="Ayşe Gül Hanyaloğlu", active=True, sequence=4)
    eski = models.Lawyer(code="ESKIAVUK", name="Eski Avukat", active=False, sequence=5)
    db.add_all([tugce, serap, baris, aysegul, eski])
    db.commit()
    ids = {lw.code: lw.id for lw in (tugce, serap, baris, aysegul, eski)}
    db.close()
    return ids


# ── 1. şema ──────────────────────────────────────────────────────────────────

def test_lawyer_id_kolonu_fk_restrict():
    kolon = models.CaseDocument.__table__.c.lawyer_id
    assert kolon.nullable is True
    fk = list(kolon.foreign_keys)[0]
    assert fk.column.table.name == "lawyers" and fk.column.name == "id"
    assert fk.ondelete == "RESTRICT"
    # FK index'i modelde DEĞİL, koşulsuz migrasyon op'unda (G043 kuralı)
    assert not kolon.index
    # geçiş kolonu yerinde (G231 kaldırır)
    assert "avukat_kodu" in models.CaseDocument.__table__.c


def test_migrasyon_kolon_op_u_ve_ayri_index_op_u():
    kolon_oplari = [op for op in _MIGRATIONS
                    if op[0] == "columns" and op[1] == "case_documents" and "lawyer_id" in op[2]]
    assert len(kolon_oplari) == 1
    ddl = kolon_oplari[0][2]["lawyer_id"]
    assert isinstance(ddl, str), "kolon op'una index/kısıt SQL'i GÖMÜLMEZ (koşullu op tuzağı)"
    assert "REFERENCES lawyers(id) ON DELETE RESTRICT" in ddl
    index_sqlleri = [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == "case_documents"
                     for sql in op[2]]
    assert ("CREATE INDEX IF NOT EXISTS idx_case_documents_lawyer_id ON case_documents (lawyer_id)"
            in index_sqlleri)


def test_restrict_avukat_silinemez_belge_bagliyken(fabrika, avukatlar):
    from sqlalchemy.exc import IntegrityError

    db = fabrika()
    db.add(models.CaseDocument(original_filename="a.pdf", stored_filename="a.pdf",
                               lawyer_id=avukatlar["SERAPTUR"]))
    db.commit()
    with pytest.raises(IntegrityError):
        db.query(models.Lawyer).filter(models.Lawyer.id == avukatlar["SERAPTUR"]).delete()
        db.commit()
    db.rollback()
    db.close()


# ── 2. toleranslı çözüm ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ham, kod", [
    ("TUGCE UNGOR", "TUGCEUNG"),                       # liste yazımından farklı, aksansız, soyadsız
    ("Tuğçe Ungör Yanık", "TUGCEUNG"),
    ("Av. Tuğçe Üngör Yanık", "TUGCEUNG"),             # ünvan + Ü yazımı
    ("SERAP TURGAL", "SERAPTUR"),
    ("Tuğçe Ungör Yanık;Serap Turgal", "TUGCEUNG"),    # çoklu: ilk çözülen parça sorumlu
    ("Hanyaloğlu", "AYSEGULH"),                        # benzersiz soyad
    ("Eski Avukat", "ESKIAVUK"),                       # pasif avukat da çözülür
])
def test_toleransli_cozum(fabrika, avukatlar, ham, kod):
    from services import document_pipeline

    db = fabrika()
    try:
        assert document_pipeline.lawyer_id_for_text(db, ham) == avukatlar[kod]
    finally:
        db.close()


def test_kod_metni_artik_cozulmez(fabrika, avukatlar):
    """G228 (27.09, test taşıma izni): kod token eşlemesi kalktı — kart metnindeki çıplak kod
    ("BBA") avukata ÇÖZÜLMEZ. Eskiden `[BBA-BBA]` parametresi çözülmesini sabitliyordu.
    Eski belgelerin kodları `scripts/belge_avukat_bagi.py` ile `lawyers.code`'a birebir bağlanır."""
    from services import document_pipeline

    db = fabrika()
    try:
        assert document_pipeline.lawyer_id_for_text(db, "BBA") is None
    finally:
        db.close()


@pytest.mark.parametrize("ham", [None, "", "   ", "Atanmadı", "Tanımsız Kişi"])
def test_cozulemeyen_metin_none(fabrika, avukatlar, ham):
    from services import document_pipeline

    db = fabrika()
    try:
        assert document_pipeline.lawyer_id_for_text(db, ham) is None
    finally:
        db.close()


def test_validate_tenant_davanin_sorumlusunu_id_olarak_dondurur(fabrika, avukatlar, monkeypatch):
    import auth_helpers
    from services import document_pipeline

    db = fabrika()
    kart = models.Case(tracking_no="G226.1", status="DERDEST", responsible_lawyer_name="TUGCE UNGOR")
    db.add(kart)
    db.commit()
    kart_id = kart.id
    db.close()

    monkeypatch.setattr(document_pipeline, "SessionLocal", fabrika)
    monkeypatch.setattr(
        auth_helpers, "get_tenant_owned_case",
        lambda s, case_id, tid: s.query(models.Case).filter(models.Case.id == case_id).first(),
    )
    assert list(inspect.signature(document_pipeline.validate_tenant_and_resolve_lawyer).parameters) == [
        "linked_case_id", "user",
    ]
    assert document_pipeline.validate_tenant_and_resolve_lawyer(kart_id, {"tid": "t1"}) == avukatlar["TUGCEUNG"]


# ── 3. yazma + e-posta yolları lawyer_id taşır ───────────────────────────────

def test_save_case_document_lawyer_id_yazar_avukat_kodu_yazmaz(fabrika, avukatlar, monkeypatch):
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "SessionLocal", fabrika)
    doc_id = document_pipeline.save_case_document(
        case_id=None, original_filename="a.pdf", stored_filename="b.pdf",
        lawyer_id=avukatlar["SERAPTUR"],
    )
    db = fabrika()
    belge = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).one()
    assert belge.lawyer_id == avukatlar["SERAPTUR"]
    assert belge.avukat_kodu is None
    db.close()
    assert "avukat_kodu" not in inspect.signature(document_pipeline.save_case_document).parameters


def test_pipeline_imzalari_lawyer_id_tasir():
    from services import document_pipeline

    for fn in (document_pipeline.convert_pdfa_and_queue_uploads,
               document_pipeline._register_pending_conversion,
               document_pipeline.send_notification_email,
               document_pipeline.send_client_notice_email,
               document_pipeline.send_email_sync):
        params = inspect.signature(fn).parameters
        assert "lawyer_id" in params, fn.__name__
        assert "avukat_kodu" not in params, fn.__name__


def test_avukat_adi_ve_eposta_lawyers_satirindan(fabrika, avukatlar, monkeypatch):
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "SessionLocal", fabrika)
    assert document_pipeline.resolve_lawyer_name(avukatlar["TUGCEUNG"]) == "Tuğçe Ungör Yanık"
    assert document_pipeline.lawyer_contact(avukatlar["SERAPTUR"]) == {
        "name": "Serap Turgal", "email": "serap@ofis.test",
    }
    assert document_pipeline.resolve_lawyer_name(None) == ""
    assert document_pipeline.lawyer_contact(999999) == {}


def test_muvekkil_bilgilendirme_avukat_epostasi_lawyer_id_den(fabrika, avukatlar, monkeypatch):
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "SessionLocal", fabrika)
    gonderilen = []

    def fake_send(pdf_path, filename, lawyer_id, meta, to_list, cc_list, *a, **k):
        gonderilen.append({"lawyer_id": lawyer_id, "to": to_list})
        return {"success": True}

    monkeypatch.setattr(document_pipeline, "send_email_sync", fake_send)
    results: dict = {}
    asyncio.run(document_pipeline.send_client_notice_email(
        email_file_path="x.pdf", new_filename="x.pdf", lawyer_id=avukatlar["TUGCEUNG"],
        avukat_adi="", email_metadata={}, client_notice_message="metin",
        current_user_name="t", results=results, timings={},
    ))
    assert results["client_notice_success"] is True
    assert gonderilen == [{"lawyer_id": avukatlar["TUGCEUNG"], "to": ["Tuğçe Ungör Yanık <tugce@ofis.test>"]}]


def test_muvekkil_bilgilendirme_epostasiz_avukatta_gonderilmez(fabrika, avukatlar, monkeypatch):
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "SessionLocal", fabrika)
    monkeypatch.setattr(document_pipeline, "send_email_sync",
                        lambda *a, **k: pytest.fail("e-postasız avukata gönderim denenmemeli"))
    results: dict = {}
    asyncio.run(document_pipeline.send_client_notice_email(
        email_file_path="x.pdf", new_filename="x.pdf", lawyer_id=avukatlar["BBA"],
        avukat_adi="", email_metadata={}, client_notice_message="metin",
        current_user_name="t", results=results, timings={},
    ))
    assert results["client_notice_success"] is False


# ── 4. ölü avukat_kodu artıkları ─────────────────────────────────────────────

def test_confirm_formunda_avukat_kodu_yok():
    from routes import processing

    assert "avukat_kodu" not in inspect.signature(processing.confirm_process).parameters


def test_auto_enrich_avukat_dali_yok_ve_sorumluya_dokunmaz(fabrika, avukatlar, monkeypatch):
    from routes import processing

    assert list(inspect.signature(processing._auto_enrich_case_data).parameters) == [
        "case_id", "karsi_taraf", "uploaded_by",
    ]
    db = fabrika()
    kart = models.Case(tracking_no="G226.2", status="DERDEST", responsible_lawyer_name=None)
    db.add(kart)
    db.commit()
    kart_id = kart.id
    db.close()

    monkeypatch.setattr(processing, "SessionLocal", fabrika)
    assert processing._auto_enrich_case_data(kart_id, None, "t") == {}
    db = fabrika()
    kart = db.query(models.Case).filter(models.Case.id == kart_id).one()
    assert kart.responsible_lawyer_name is None
    assert db.query(models.CaseHistory).count() == 0
    db.close()


def test_analiz_ciktisinda_avukat_kodu_alani_yok():
    import analyzer
    from schemas_process import ProcessAnalysisOutput

    assert "avukat_kodu" not in ProcessAnalysisOutput.model_fields
    assert "avukat_kodu" not in analyzer.get_default_json()


def test_prompt_avukat_kodu_artigi_yok():
    import prompts

    metin = prompts.get_system_instruction(
        dynamic_lawyers=[{"code": "SERAPTUR", "name": "Serap Turgal"}],
        pre_extracted={"tarih": "2026-09-27", "avukat_kodu": "SERAPTUR"},
    )
    assert "Avukat: SERAPTUR" not in metin
    assert '"SERAPTUR"' not in metin
    assert "SERAP TURGAL" in metin        # avukat ayıklama notu korunur


def test_send_document_notification_avukat_kodu_parametresi_yok():
    import email_sender

    assert "avukat_kodu" not in inspect.signature(email_sender.send_document_notification).parameters


# ── 5. doldurma betiği ───────────────────────────────────────────────────────

@pytest.fixture()
def belgeler(fabrika, avukatlar):
    db = fabrika()
    kart = models.Case(tracking_no="G226.3", status="DERDEST", responsible_lawyer_name="Serap Turgal")
    db.add(kart)
    db.flush()
    kodlar = [("SERAPTUR", False), ("SERAPTUR", True), ("TUGCEUNG", False), ("TUY", False),
              ("BYU", False), ("AGH", False), ("BILINMEZ", False), (None, False), (" bba ", False)]
    for i, (kod, silinmis) in enumerate(kodlar):
        db.add(models.CaseDocument(
            case_id=kart.id, original_filename=f"b{i}.pdf", stored_filename=f"b{i}.pdf",
            avukat_kodu=kod, deleted_at=datetime.now(timezone.utc) if silinmis else None,
        ))
    # zaten bağlı belge: dokunulmaz
    db.add(models.CaseDocument(case_id=kart.id, original_filename="z.pdf", stored_filename="z.pdf",
                               avukat_kodu="SERAPTUR", lawyer_id=avukatlar["TUGCEUNG"]))
    db.commit()
    db.close()


def _baglar(fabrika):
    db = fabrika()
    try:
        return sorted((b.stored_filename, b.avukat_kodu, b.lawyer_id)
                      for b in db.query(models.CaseDocument).all())
    finally:
        db.close()


def test_betik_kuru_kosu_yazmaz(fabrika, belgeler):
    from scripts import belge_avukat_bagi as betik

    once = _baglar(fabrika)
    sonuc = betik.kos(fabrika)
    assert sonuc["durum"].startswith("KURU KOSU")
    assert sum(sonuc["baglanan"].values()) == 7
    assert _baglar(fabrika) == once


def test_betik_apply_baglar_eski_kodlari_cevirir_avukat_koduna_dokunmaz(fabrika, avukatlar, belgeler):
    from scripts import belge_avukat_bagi as betik

    sonuc = betik.kos(fabrika, apply=True)
    assert sonuc["durum"] == "UYGULANDI"
    assert sonuc["ihlal"] == []
    assert sonuc["eslesmeyen"] == {"BILINMEZ": 1}
    assert sonuc["zaten_bagli"] == 1
    assert sonuc["baglanan"] == {
        ("SERAPTUR", "SERAPTUR"): 2,           # silinmiş belge de bağlanır
        ("TUGCEUNG", "TUGCEUNG"): 1,
        ("TUY", "TUGCEUNG"): 1,
        ("BYU", "BBA"): 1,
        ("AGH", "AYSEGULH"): 1,
        (" bba ", "BBA"): 1,
    }
    baglar = {ad: (kod, lid) for ad, kod, lid in _baglar(fabrika)}
    assert baglar["b3.pdf"] == ("TUY", avukatlar["TUGCEUNG"])
    assert baglar["b4.pdf"] == ("BYU", avukatlar["BBA"])
    assert baglar["b5.pdf"] == ("AGH", avukatlar["AYSEGULH"])
    assert baglar["b6.pdf"] == ("BILINMEZ", None)        # eşleşmeyen bağsız kalır
    assert baglar["b7.pdf"] == (None, None)
    assert baglar["z.pdf"] == ("SERAPTUR", avukatlar["TUGCEUNG"])   # bağlı belgeye dokunulmaz
    assert baglar["b8.pdf"] == (" bba ", avukatlar["BBA"])          # avukat_kodu AYNEN kalır

    ikinci = betik.kos(fabrika, apply=True)
    assert ikinci["baglanan"] == {}                       # idempotent
    assert ikinci["eslesmeyen"] == {"BILINMEZ": 1}


def test_betik_envanter_ihlalinde_geri_alir(fabrika, belgeler, monkeypatch):
    from scripts import belge_avukat_bagi as betik

    once = _baglar(fabrika)
    madde = {"tur": "IHLAL", "avukat": "SERAPTUR", "alan": "belge", "once": 2, "sonra": 1,
             "aciklama": "belge düştü"}
    monkeypatch.setattr(betik.env, "karsilastir", lambda a, b: [madde])
    sonuc = betik.kos(fabrika, apply=True)
    assert sonuc["durum"].startswith("GERI ALINDI")
    assert sonuc["ihlal"] == [madde]
    assert _baglar(fabrika) == once
    assert "SERAPTUR" in betik.ozet_metni(sonuc)


def test_betik_gercek_envanter_denk_kalir(fabrika, belgeler):
    """Bağlama belge sayısını düşürmez: eski kodun belgesi doğru avukata GEÇER (artış BİLGİ)."""
    from scripts import belge_avukat_bagi as betik

    sonuc = betik.kos(fabrika, apply=True)
    assert sonuc["ihlal"] == []
    artan = {(m["avukat"], m["alan"]): (m["once"], m["sonra"]) for m in sonuc["fark"]}
    # TUY → Tuğçe (önce: TUGCEUNG kodlu 1 + bağlı 1), AGH → Ayşe Gül, BYU → Barış:
    # eski kodlar öncesinde hiçbir avukata sayılmıyordu
    assert artan[("TUGCEUNG", "belge")] == (2, 3)
    assert artan[("AYSEGULH", "belge")] == (0, 1)
    assert artan[("BBA", "belge")] == (1, 2)
    assert ("SERAPTUR", "belge") not in artan
    assert (None, "avukatli_belge") not in artan          # toplam aynen
