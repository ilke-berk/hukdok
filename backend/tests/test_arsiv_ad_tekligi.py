"""Arşiv adı tekliği testleri (2026-09-01 override arızası).

Arıza: frontend'in ürettiği `TARİH_TÜR_ESAS_KarşıTaraf.pdf` adı teklik
taşımıyordu; aynı ada düşen ikinci belge SharePoint'te birincinin dosyasını
değiştiriyordu (conflictBehavior=replace). services/archive_names.py hedef
adları kuyruğa girmeden benzersizleştirir; bu dosya o katmanı ve
document_pipeline entegrasyonunu doğrular.

conftest sözleşmesi: gerçek DB yok — SessionLocal fake'lenir. Modül SQL
filtrelerini yalnız ÖNFİLTRE sayar, kesin karar Python karşılaştırmasındadır;
fake query bu yüzden filtreleri yok sayıp tüm satırları döndürür.
"""
import logging

import pytest

import models
from services import archive_names


# ─── ortak fake'ler ──────────────────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDoc:
    def __init__(self, id, stored_filename):
        self.id = id
        self.stored_filename = stored_filename


class _FakeSession:
    """query(*ents) çağrısını ilk entity'nin tablosuna göre yönlendirir.

    doc_rows:    (id, stored_filename) — kolon sorguları
    outbox_rows: islenmis yolu (document_id, kind, target_filename);
                 ham yolu (kind, target_filename) — test hangi yolu
                 çalıştırıyorsa o şekli verir
    doc_obj:     resolve_stored_name_race'in rename için çektiği tam nesne
    """

    def __init__(self, doc_rows=None, outbox_rows=None, doc_obj=None):
        self.doc_rows = doc_rows or []
        self.outbox_rows = outbox_rows or []
        self.doc_obj = doc_obj
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, *ents):
        first = ents[0]
        cls = getattr(first, "class_", first)
        if cls is models.CaseDocument:
            if first is models.CaseDocument:  # tam nesne sorgusu (rename yolu)
                return _FakeQuery([self.doc_obj] if self.doc_obj else [])
            return _FakeQuery(self.doc_rows)
        return _FakeQuery(self.outbox_rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def name_log_records():
    """caplog BİLİNÇLİ değil (test_faz2_alerting gerekçesi): dictConfig pytest
    capture handler'ını söker; adlandırılmış logger'a takılan handler kalır."""
    handler = _ListHandler()
    target = logging.getLogger("services.archive_names")
    target.addHandler(handler)
    yield handler.records
    target.removeHandler(handler)


def _use(monkeypatch, session):
    monkeypatch.setattr(archive_names, "SessionLocal", lambda: session)
    return session


# ═════════════════════════════════════════════════════════════════════════════
# 1) unique_islenmis_name
# ═════════════════════════════════════════════════════════════════════════════


def test_cakisma_yoksa_ad_aynen_doner(monkeypatch):
    s = _use(monkeypatch, _FakeSession())
    ad = "2026-08-31_ARAKRR_26-754_S.Bakanligi.pdf"
    assert archive_names.unique_islenmis_name(ad) == ad
    assert s.closed


def test_cakismada_2_soneki_uretilir(monkeypatch):
    _use(monkeypatch, _FakeSession(doc_rows=[(10, "2026-08-31_ARAKRR_26-754_S.Bakanligi.pdf")]))
    assert (
        archive_names.unique_islenmis_name("2026-08-31_ARAKRR_26-754_S.Bakanligi.pdf")
        == "2026-08-31_ARAKRR_26-754_S.Bakanligi_2.pdf"
    )


def test_sonek_zinciri_ilk_bos_numaraya_ilerler(monkeypatch):
    _use(monkeypatch, _FakeSession(doc_rows=[(1, "X.pdf"), (2, "X_2.pdf")]))
    assert archive_names.unique_islenmis_name("X.pdf") == "X_3.pdf"


def test_teklik_stem_duzeyindedir_uzanti_farki_korumaz(monkeypatch):
    """conversion_pending belgesi X.udf saklar, gece job'ı X.pdf'e döner —
    X.pdf'i serbest saymak gece dönüşümünde yine ezmeye yol açardı."""
    _use(monkeypatch, _FakeSession(doc_rows=[(1, "X.udf")]))
    assert archive_names.unique_islenmis_name("X.pdf") == "X_2.pdf"


def test_outbox_islenmis_satiri_da_ad_uzayini_isgal_eder(monkeypatch):
    _use(monkeypatch, _FakeSession(outbox_rows=[(None, "islenmis", "X.pdf")]))
    assert archive_names.unique_islenmis_name("X.pdf") == "X_2.pdf"


def test_exclude_doc_id_kendi_satirlarini_saymaz(monkeypatch):
    """Gece dönüşüm job'ı kendi belgesinin .udf kaydını/outbox izini çakışma
    saymamalı — aynı ada yeniden yüklemek kendi dosyası için idempotent."""
    _use(
        monkeypatch,
        _FakeSession(doc_rows=[(5, "X.udf")], outbox_rows=[(5, "islenmis", "X.udf")]),
    )
    assert archive_names.unique_islenmis_name("X.pdf", exclude_doc_id=5) == "X.pdf"


def test_baska_belgenin_stemi_exclude_ile_serbest_kalmaz(monkeypatch):
    """Fix öncesi açılmış mükerrer kayıt senaryosu: gece job'ı kendi .udf'ini
    (5) dışlar ama stem'i işgal eden BAŞKA belgeyi (6) çakışma saymalıdır."""
    _use(
        monkeypatch,
        _FakeSession(doc_rows=[(5, "X.udf"), (6, "X.pdf")]),
    )
    assert archive_names.unique_islenmis_name("X.pdf", exclude_doc_id=5) == "X_2.pdf"


def test_benzer_on_ekli_farkli_stem_cakisma_sayilmaz(monkeypatch):
    """Önfiltre LIKE kaba olabilir; kesin karar Python stem eşitliğindedir."""
    _use(monkeypatch, _FakeSession(doc_rows=[(1, "X_EK.pdf"), (2, "X.notlar.pdf")]))
    # "X_EK" ≠ "X"; "X.notlar.pdf"in stem'i "X.notlar" ≠ "X" → aday serbest
    assert archive_names.unique_islenmis_name("X.pdf") == "X.pdf"


def test_sonek_uzayi_dolunca_rastgele_sonek(monkeypatch):
    monkeypatch.setattr(archive_names, "_MAX_SUFFIX", 3)
    _use(monkeypatch, _FakeSession(doc_rows=[(1, "X.pdf"), (2, "X_2.pdf"), (3, "X_3.pdf")]))
    sonuc = archive_names.unique_islenmis_name("X.pdf")
    assert sonuc.startswith("X_") and sonuc.endswith(".pdf")
    hex_kismi = sonuc[len("X_"):-len(".pdf")]
    assert len(hex_kismi) == 8 and all(c in "0123456789abcdef" for c in hex_kismi)


# ═════════════════════════════════════════════════════════════════════════════
# 2) unique_ham_name
# ═════════════════════════════════════════════════════════════════════════════


def test_ham_cakismasinda_sonek(monkeypatch):
    _use(monkeypatch, _FakeSession(outbox_rows=[("ham", "2026-09-01_ustyazi_(1).pdf")]))
    assert (
        archive_names.unique_ham_name("2026-09-01_ustyazi_(1).pdf")
        == "2026-09-01_ustyazi_(1)_2.pdf"
    )


def test_ham_cakisma_yoksa_aynen(monkeypatch):
    _use(monkeypatch, _FakeSession(outbox_rows=[]))
    assert archive_names.unique_ham_name("2026-09-01_a.pdf") == "2026-09-01_a.pdf"


def test_ham_tekligi_islenmis_satirlarindan_etkilenmez(monkeypatch):
    """Ham ve işlenmiş farklı klasörlerdedir — kind='islenmis' satırı ham ad
    uzayını işgal etmez (fake filtreleri yok sayar, Python kind'ı denetler)."""
    _use(monkeypatch, _FakeSession(outbox_rows=[("islenmis", "A.pdf")]))
    assert archive_names.unique_ham_name("A.pdf") == "A.pdf"


# ═════════════════════════════════════════════════════════════════════════════
# 3) resolve_stored_name_race
# ═════════════════════════════════════════════════════════════════════════════


def test_yaris_yoksa_ad_kalir(monkeypatch):
    s = _use(monkeypatch, _FakeSession(doc_rows=[(7, "X.pdf")]))
    assert archive_names.resolve_stored_name_race(7, "X.pdf") == "X.pdf"
    assert s.commits == 0


def test_kucuk_id_ad_sahibi_kalir(monkeypatch):
    s = _use(monkeypatch, _FakeSession(doc_rows=[(7, "X.pdf"), (9, "X.pdf")]))
    assert archive_names.resolve_stored_name_race(7, "X.pdf") == "X.pdf"
    assert s.commits == 0


def test_buyuk_id_deterministik_yeniden_adlanir(monkeypatch, name_log_records):
    doc = _FakeDoc(9, "X.pdf")
    s = _use(monkeypatch, _FakeSession(doc_rows=[(7, "X.pdf"), (9, "X.pdf")], doc_obj=doc))
    assert archive_names.resolve_stored_name_race(9, "X.pdf") == "X_9.pdf"
    assert doc.stored_filename == "X_9.pdf"
    assert s.commits == 1
    # Log sözleşmesi: yarış nihai arıza değildir → WARNING, ERROR değil
    assert any(r.levelno == logging.WARNING for r in name_log_records)
    assert not any(r.levelno >= logging.ERROR for r in name_log_records)


def test_uc_yonlu_yariste_sonekler_id_ile_ayrisir(monkeypatch):
    """Kaybedenler `_<doc_id>` aldığı için ikinci tur çakışma imkânsızdır."""
    doc9 = _FakeDoc(9, "X.pdf")
    _use(monkeypatch, _FakeSession(doc_rows=[(7, "X.pdf"), (9, "X.pdf"), (11, "X.pdf")], doc_obj=doc9))
    assert archive_names.resolve_stored_name_race(9, "X.pdf") == "X_9.pdf"
    doc11 = _FakeDoc(11, "X.pdf")
    _use(monkeypatch, _FakeSession(doc_rows=[(7, "X.pdf"), (9, "X_9.pdf"), (11, "X.pdf")], doc_obj=doc11))
    assert archive_names.resolve_stored_name_race(11, "X.pdf") == "X_11.pdf"


def test_doc_id_yoksa_db_ye_hic_dokunulmaz(monkeypatch):
    def boom():
        raise AssertionError("SessionLocal çağrılmamalıydı")

    monkeypatch.setattr(archive_names, "SessionLocal", boom)
    assert archive_names.resolve_stored_name_race(None, "X.pdf") == "X.pdf"


# ═════════════════════════════════════════════════════════════════════════════
# 4) Hata semantiği: adlandırma katmanı arşivlemeyi düşüremez
# ═════════════════════════════════════════════════════════════════════════════


def test_db_arizasinda_aday_aynen_doner_ve_error_uretilmez(monkeypatch, name_log_records):
    def boom():
        raise RuntimeError("db yok")

    monkeypatch.setattr(archive_names, "SessionLocal", boom)
    assert archive_names.unique_islenmis_name("X.pdf") == "X.pdf"
    assert archive_names.unique_ham_name("h.pdf") == "h.pdf"
    assert archive_names.resolve_stored_name_race(5, "X.pdf") == "X.pdf"
    assert any(r.levelno == logging.WARNING for r in name_log_records)
    assert not any(r.levelno >= logging.ERROR for r in name_log_records)


# ═════════════════════════════════════════════════════════════════════════════
# 5) document_pipeline entegrasyonu: kuyruk hedefi benzersizleştirilmiş addır
# ═════════════════════════════════════════════════════════════════════════════


class _FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def test_convert_basari_yolu_benzersiz_adla_kuyruklar(monkeypatch, tmp_path):
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    src = tmp_path / "analiz.pdf"
    src.write_bytes(b"%PDF-1.4 analiz")
    pdfa = tmp_path / "cikti.pdf"
    pdfa.write_bytes(b"%PDF-1.4 pdfa")
    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", lambda p, **kw: str(pdfa))
    monkeypatch.setattr(document_pipeline, "save_case_document", lambda **kw: 42)

    enqueued = []

    def fake_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        enqueued.append((kind, target_filename, document_id))
        return len(enqueued)

    monkeypatch.setattr(upload_queue, "enqueue_upload", fake_enqueue)
    # "yeni.pdf" alınmış → _2 beklenir; ham tarafı boş → aynen kalır
    _use(monkeypatch, _FakeSession(doc_rows=[(10, "yeni.pdf")]))

    results, timings = {}, {}
    pdfa_out, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=_FakeBackgroundTasks(),
        source_path=str(src),
        ham_filename="2026-09-01_orijinal.pdf",
        ham_folder="01_HAM_ARSIV",
        islenmis_folder="02_YEDEK_ARSIV",
        new_filename="yeni.pdf",
        original_filename="orijinal.pdf",
        belge_turu_kodu=None,
        muvekkiller=[],
        muvekkil_adi=None,
        ai_ozet=None,
        linked_case_id=None,
        case_party_id=None,
        avukat_kodu=None,
        esas_no=None,
        is_test_mode=False,
        user={},
        current_user_name="test",
        results=results,
        timings=timings,
        ham_source_path=None,
    )

    assert (pdfa_out, doc_id) == (str(pdfa), 42)
    assert results["stored_filename"] == "yeni_2.pdf"
    assert enqueued == [
        ("ham", "2026-09-01_orijinal.pdf", 42),
        ("islenmis", "yeni_2.pdf", 42),
    ]


def test_pending_yolunda_da_ad_benzersizlestirilir(monkeypatch, tmp_path):
    """Dönüşüm düşerse belge KENDİ uzantısıyla saklanır — pending adı da
    benzersizleştirilmiş stem'i taşımalı (X.udf ↔ X.pdf ayrımı yeterli değil)."""
    from services import document_pipeline, upload_queue
    import pdf.pdf_converter as pdf_converter

    monkeypatch.setenv("CONVERSION_SPOOL_DIR", str(tmp_path / "conv_spool"))
    src = tmp_path / "analiz.pdf"
    src.write_bytes(b"%PDF-1.4 analiz")
    orijinal = tmp_path / "orijinal.udf"
    orijinal.write_bytes(b"PK\x03\x04 orijinal")

    def boom(path, **kw):
        raise ValueError("dönüşüm patladı")

    monkeypatch.setattr(pdf_converter, "convert_to_pdfa2b", boom)

    saved = []

    def fake_save(**kw):
        saved.append(kw)
        return 7

    monkeypatch.setattr(document_pipeline, "save_case_document", fake_save)
    enqueued = []

    def fake_enqueue(kind, source_path, target_filename, target_folder, document_id=None):
        enqueued.append((kind, target_filename))
        return len(enqueued)

    monkeypatch.setattr(upload_queue, "enqueue_upload", fake_enqueue)
    # Var olan "yeni.udf" kaydı stem'i işgal ediyor → aday "yeni.pdf" → "yeni_2"
    _use(monkeypatch, _FakeSession(doc_rows=[(3, "yeni.udf")]))

    results, timings = {}, {}
    pdfa_out, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
        background_tasks=_FakeBackgroundTasks(),
        source_path=str(src),
        ham_filename="2026-09-01_orijinal.udf",
        ham_folder="01_HAM_ARSIV",
        islenmis_folder="02_YEDEK_ARSIV",
        new_filename="yeni.pdf",
        original_filename="orijinal.udf",
        belge_turu_kodu=None,
        muvekkiller=[],
        muvekkil_adi=None,
        ai_ozet=None,
        linked_case_id=None,
        case_party_id=None,
        avukat_kodu=None,
        esas_no=None,
        is_test_mode=False,
        user={},
        current_user_name="test",
        results=results,
        timings=timings,
        ham_source_path=str(orijinal),
    )

    assert (pdfa_out, doc_id) == (None, 7)
    assert saved[0]["stored_filename"] == "yeni_2.udf"
    assert results["stored_filename"] == "yeni_2.udf"
    assert results["archived_filename"] == "yeni_2.udf"
    assert ("islenmis", "yeni_2.udf") in enqueued
