"""G082 — "belge işlendi" bildiriminin ilk üreticisi.

Kilitlenen davranışlar:
  1. bildirim YALNIZ `sharepoint_url` commit edildikten sonra üretilir —
     başarısız yükleme yolunda ("failed") HİÇ bildirim yok,
  2. idempotency: aynı belge için ikinci çağrı (outbox retry / yeniden yükleme)
     satır İKİLEMEZ; anahtar `doc-processed:<doc_id>` önekini taşır,
  3. bildirim metni belgenin müvekkil-maili durumunu bilgi olarak taşır
     (True → "gönderildi", None → "gönderilmedi", False → "gönderilemedi"),
  4. alıcı çözülemezse bildirim üretilmez ve WARNING loglanır (nihai
     başarısızlık değil → ERROR YAZILMAZ),
  5. bildirim üretimi ana yükleme akışını BOZMAZ: servis patlasa bile satır
     'uploaded' kalır, belge URL'si yerinde durur, hukukbot hook'u açılır,
  6. mail YOLLARINA dokunulmaz: `email_sender` / `document_pipeline`
     bildirimden hiç çağrılmaz (bildirim maili KOPYALAMAZ, yalnız anlatır).

Üretici testleri süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar;
dedupe UNIQUE kısıtı `database._MIGRATIONS`'taki gerçek DDL'den kurulur
(G081 dosyasıyla aynı desen). Yükleme akışı testleri ise DB'ye/ağa inmez:
`upload_queue.SessionLocal` fake'lenir (Faz 3-A test sözleşmesi).
"""
import logging
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DOMAIN = "hanyaloglu-acar.av.tr"
MAIL_SERAP = f"serap.turgal@{DOMAIN}"
MAIL_TUGCE = f"tugce.ungor@{DOMAIN}"


def _notifications_index_ddls() -> list[str]:
    """Migrasyondaki `notifications` index op'unun DDL'leri (tek kaynak)."""
    import database

    return [
        ddl
        for op in database._MIGRATIONS
        if op[0] == "index" and op[1] == "notifications"
        for ddl in op[2]
    ]


@pytest.fixture()
def env(monkeypatch):
    """sqlite motoru + oturum fabrikası + veri kurucular."""
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    from services import notifications as svc

    monkeypatch.setenv("NOTIFICATION_DOMAINS", DOMAIN)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _notifications_index_ddls():
            conn.execute(text(ddl))

    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _avukat(code: str, name: str, email: str, gorev: str = "AVUKAT"):
        db = maker()
        try:
            row = models.Lawyer(code=code, name=name, email=email, gorev=gorev, active=True)
            db.add(row)
            db.commit()
        finally:
            db.close()

    def _dava(sorumlu: str, **kw):
        db = maker()
        try:
            row = models.Case(
                tracking_no=kw.pop("tracking_no", "2024/1234"),
                esas_no=kw.pop("esas_no", "2024/55"),
                court=kw.pop("court", "Ankara 1. Asliye Hukuk Mahkemesi"),
                responsible_lawyer_name=sorumlu,
                **kw,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        finally:
            db.close()

    def _belge(case_id, **kw):
        db = maker()
        try:
            row = models.CaseDocument(
                case_id=case_id,
                original_filename=kw.pop("original_filename", "tebligat.pdf"),
                stored_filename=kw.pop("stored_filename", "2024-1234_TEBLIGAT.pdf"),
                belge_turu_adi=kw.pop("belge_turu_adi", "Tebligat"),
                sharepoint_url=kw.pop("sharepoint_url", "https://sp/arsiv/tebligat.pdf"),
                upload_status=kw.pop("upload_status", "uploaded"),
                **kw,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        finally:
            db.close()

    def _bildirimler():
        db = maker()
        try:
            return (
                db.query(models.Notification)
                .order_by(models.Notification.id)
                .all()
            )
        finally:
            db.close()

    yield SimpleNamespace(
        models=models,
        service=svc,
        sessions=maker,
        db=maker,
        avukat=_avukat,
        dava=_dava,
        belge=_belge,
        bildirimler=_bildirimler,
    )
    engine.dispose()


def _uret(env, document_id):
    """notify_document_processed kısayolu — kendi oturumunu açar/kapatır."""
    db = env.db()
    try:
        return env.service.notify_document_processed(document_id, db=db)
    finally:
        db.close()


# ─── üretici: mutlu yol ──────────────────────────────────────────────────────

def test_bildirim_sorumlu_avukata_yazilir(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Av. Serap Turgal")
    doc_id = env.belge(case_id)

    ids = _uret(env, doc_id)

    rows = env.bildirimler()
    assert len(ids) == 1 and len(rows) == 1
    row = rows[0]
    assert row.recipient_email == MAIL_SERAP
    assert row.type == env.service.DOC_PROCESSED_TYPE == "belge_islendi"
    assert row.severity == "info"
    assert row.case_id == case_id and row.document_id == doc_id
    assert "Tebligat" in row.title
    assert "2024/1234" in (row.body or "")


def test_bildirim_metni_dava_kunyesini_ve_belge_adini_tasir(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal", tracking_no="2025/9", esas_no="2025/77")
    doc_id = env.belge(case_id, original_filename="karar.pdf", belge_turu_adi="Karar")

    _uret(env, doc_id)

    body = env.bildirimler()[0].body
    assert "2025/9" in body and "2025/77" in body
    assert "karar.pdf" in body


# ─── üretici: mail durumu metni (üç değerli) ─────────────────────────────────

@pytest.mark.parametrize(
    "email_sent, beklenen, olmayan",
    [
        (True, "gönderildi", "gönderilemedi"),
        (None, "gönderilmedi", "gönderilemedi"),
        (False, "gönderilemedi", "gönderilmedi"),
    ],
)
def test_mail_durumu_bildirim_metnine_yazilir(env, email_sent, beklenen, olmayan):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal")
    doc_id = env.belge(case_id, email_sent=email_sent)

    _uret(env, doc_id)

    body = env.bildirimler()[0].body
    assert "Müvekkil bilgilendirmesi" in body
    assert beklenen in body and olmayan not in body


def test_mail_durumu_metni_uc_degerlidir():
    from services import notifications as svc

    assert svc.mail_status_text(True).endswith("gönderildi.")
    assert svc.mail_status_text(None).endswith("gönderilmedi.")
    assert svc.mail_status_text(False).endswith("gönderilemedi.")


# ─── üretici: idempotency ────────────────────────────────────────────────────

def test_ikinci_cagri_ikinci_bildirim_uretmez(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal")
    doc_id = env.belge(case_id)

    ilk = _uret(env, doc_id)
    ikinci = _uret(env, doc_id)

    assert ilk == ikinci, "aynı belge aynı bildirimi göstermeli"
    assert len(env.bildirimler()) == 1


def test_dedupe_anahtari_doc_processed_onekini_tasir(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal")
    doc_id = env.belge(case_id)

    _uret(env, doc_id)

    row = env.bildirimler()[0]
    assert row.dedupe_key.startswith(f"doc-processed:{doc_id}")
    assert row.dedupe_key == env.service.document_processed_dedupe_key(doc_id, MAIL_SERAP)


def test_coklu_sorumlu_her_avukata_ayri_bildirim_ve_tekrarda_ikilemez(env):
    """`dedupe_key` GLOBAL tekil + satır TEK alıcı taşır → anahtar alıcıyla
    genişletilmiştir; iki sorumlu iki bildirim alır, ikinci çağrı ikilemez."""
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.avukat("TUY", "Tuğçe Üngör Yanık", MAIL_TUGCE)
    case_id = env.dava("Tuğçe Üngör Yanık;Serap Turgal")
    doc_id = env.belge(case_id)

    ilk = _uret(env, doc_id)
    assert len(ilk) == 2
    assert {r.recipient_email for r in env.bildirimler()} == {MAIL_SERAP, MAIL_TUGCE}

    ikinci = _uret(env, doc_id)
    assert ikinci == ilk
    assert len(env.bildirimler()) == 2


# ─── üretici: hedefsiz yollar (WARNING, ERROR YOK) ───────────────────────────

def _uyarilar(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _hatalar(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_alici_cozulemezse_bildirim_yok_ve_warning(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Arşiv Dosya Yöneticisi")
    doc_id = env.belge(case_id)

    assert _uret(env, doc_id) == []
    assert env.bildirimler() == []
    assert _uyarilar(caplog) and not _hatalar(caplog)


def test_allowlist_disi_avukata_bildirim_gitmez(env, caplog):
    """69 dış avukatın kişisel adresi yapısal kapıdan geçemez (G080)."""
    caplog.set_level(logging.DEBUG)
    env.avukat("DIS", "Ahmet Dışavukat", "ahmet.disavukat@gmail.com", gorev="DIŞ AVUKAT")
    case_id = env.dava("Ahmet Dışavukat")
    doc_id = env.belge(case_id)

    assert _uret(env, doc_id) == []
    assert env.bildirimler() == []
    assert _uyarilar(caplog) and not _hatalar(caplog)


def test_davasiz_belge_bildirim_uretmez(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    doc_id = env.belge(None)

    assert _uret(env, doc_id) == []
    assert env.bildirimler() == []
    assert _uyarilar(caplog) and not _hatalar(caplog)


def test_olmayan_belge_bildirim_uretmez(env, caplog):
    caplog.set_level(logging.DEBUG)

    assert _uret(env, 4242) == []
    assert env.bildirimler() == []
    assert _uyarilar(caplog) and not _hatalar(caplog)


def test_bos_document_id_sessizce_bos_doner(env, caplog):
    caplog.set_level(logging.DEBUG)

    assert _uret(env, 0) == []
    assert env.bildirimler() == []
    assert not _hatalar(caplog)


def test_kendi_oturumunu_acar_ve_kapatir(env, monkeypatch):
    """`db` verilmezse servis kendi oturumunu açar — yükleme akışının
    transaction'ından yapısal olarak ayrık kalsın diye."""
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal")
    doc_id = env.belge(case_id)

    acilan = []

    def _fabrika():
        db = env.sessions()
        acilan.append(db)
        return db

    monkeypatch.setattr(env.service, "SessionLocal", _fabrika)
    ids = env.service.notify_document_processed(doc_id)

    assert len(ids) == 1 and len(env.bildirimler()) == 1
    assert len(acilan) == 1


# ─── mail yolları: DOKUNULMAZ ────────────────────────────────────────────────

def test_bildirim_uretimi_mail_gondermez(env, monkeypatch):
    """Bildirim, mevcut mail akışının YANINA yazılan bağımsız bir kayıttır:
    `email_sender` / `document_pipeline` gönderim yolları çağrılmaz."""
    import email_sender
    from services import document_pipeline

    for modul, ad in (
        (email_sender, "send_document_email"),
        (email_sender, "send_document_notification"),
        (document_pipeline, "send_client_notice_email"),
    ):
        assert hasattr(modul, ad), f"{ad} kayboldu — mail yolu bekçisi geçersizleşti"
        monkeypatch.setattr(
            modul, ad,
            lambda *a, _ad=ad, **kw: pytest.fail(f"bildirim {_ad} çağırmamalı"),
        )

    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava("Serap Turgal")
    doc_id = env.belge(case_id)

    assert len(_uret(env, doc_id)) == 1


# ─── yükleme akışı entegrasyonu (upload_queue) ───────────────────────────────

class _FakeRow:
    def __init__(self, **kw):
        self.id = kw.get("id", 5)
        self.document_id = kw.get("document_id", 7)
        self.kind = kw.get("kind", "islenmis")
        self.spool_path = kw.get("spool_path")
        self.target_filename = kw.get("target_filename", "belge.pdf")
        self.target_folder = kw.get("target_folder", "02_YEDEK_ARSIV")
        self.status = kw.get("status", "pending")
        self.attempts = kw.get("attempts", 0)
        self.next_attempt_at = kw.get("next_attempt_at")
        self.last_error = kw.get("last_error")
        self.created_at = kw.get("created_at")
        self.done_at = kw.get("done_at")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return _FakeQuery(self.rows)

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


@pytest.fixture()
def akis(monkeypatch, tmp_path):
    """_attempt_upload için hazır sahne: spool'lu satır + fake session + kancalar."""
    from services import upload_queue, document_pipeline, export_publisher
    from services import notifications as svc

    upload_queue.stop_upload_worker()
    upload_queue._wake.clear()
    upload_queue._stop.clear()

    spool = tmp_path / "spool_kopya.pdf"
    spool.write_bytes(b"%PDF-1.4 spool")
    row = _FakeRow(spool_path=str(spool))
    monkeypatch.setattr(upload_queue, "SessionLocal", lambda: _FakeSession([row]))

    monkeypatch.setattr(
        document_pipeline, "_record_upload_result", lambda doc_id, url, db=None: url is not None
    )
    notified: list = []
    monkeypatch.setattr(
        export_publisher, "notify_hukukbot", lambda doc_id: notified.append(doc_id)
    )
    uretilen: list = []
    monkeypatch.setattr(
        svc, "notify_document_processed",
        lambda doc_id, db=None: uretilen.append(doc_id) or [1],
    )

    def _uploader(sonuc=None, hata=None):
        import sharepoint.sharepoint_uploader_graph as uploader

        def _fn(*a, **kw):
            if hata is not None:
                raise hata
            return sonuc

        monkeypatch.setattr(uploader, "upload_file_to_sharepoint", _fn)

    yield SimpleNamespace(
        queue=upload_queue,
        service=svc,
        row=row,
        spool=str(spool),
        notified=notified,
        uretilen=uretilen,
        uploader=_uploader,
    )
    upload_queue.stop_upload_worker()


def test_yukleme_basarili_olunca_bildirim_uretilir(akis):
    akis.uploader(sonuc={"webUrl": "https://sp/yeni.pdf"})

    akis.queue._attempt_upload(5)

    assert akis.row.status == "uploaded"
    assert akis.uretilen == [7]
    assert akis.notified == [7], "hukukbot hook'u yerinde kalmalı"


def test_yukleme_basarisizsa_bildirim_yok(akis):
    """Yükleme hatasında (retry yolu) HİÇ bildirim üretilmez."""
    akis.uploader(hata=RuntimeError("SharePoint 503"))

    akis.queue._attempt_upload(5)

    assert akis.row.status == "pending" and akis.row.last_error
    assert akis.uretilen == []
    assert akis.notified == []


def test_nihai_failed_yolunda_da_bildirim_yok(akis):
    akis.row.attempts = akis.queue.MAX_ATTEMPTS - 1
    akis.uploader(hata=RuntimeError("SharePoint 503"))

    akis.queue._attempt_upload(5)

    assert akis.row.status == "failed"
    assert akis.uretilen == []


def test_url_yazilmayan_satirda_bildirim_yok(akis, monkeypatch):
    """`_record_upload_result` False dönerse (ham satır / belgesiz) bildirim yok:
    kapı `sharepoint_url` yazımıdır, yükleme başarısı tek başına yetmez."""
    from services import document_pipeline

    akis.uploader(sonuc={"webUrl": "https://sp/yeni.pdf"})
    monkeypatch.setattr(
        document_pipeline, "_record_upload_result", lambda doc_id, url, db=None: False
    )

    akis.queue._attempt_upload(5)

    assert akis.row.status == "uploaded"
    assert akis.uretilen == []
    assert akis.notified == []


def test_bildirim_patlasa_bile_yukleme_yesil_kalir(akis, caplog, monkeypatch):
    """Servis istisna fırlatsa bile satır 'uploaded' kalır, hook açılır,
    log WARNING'de kalır (nihai başarısızlık değil → ERROR yok)."""
    caplog.set_level(logging.DEBUG)
    akis.uploader(sonuc={"webUrl": "https://sp/yeni.pdf"})

    def _patla(doc_id, db=None):
        raise RuntimeError("bildirim tablosu yok")

    monkeypatch.setattr(akis.service, "notify_document_processed", _patla)

    akis.queue._attempt_upload(5)

    assert akis.row.status == "uploaded"
    assert akis.row.last_error is None
    assert not os.path.exists(akis.spool), "başarı yolu bozulmamalı"
    assert akis.notified == [7], "bildirim arızası hukukbot hook'unu engellememeli"
    assert _uyarilar(caplog) and not _hatalar(caplog)


def test_upload_queue_bildirimi_hook_SONRASI_cagirir(akis, monkeypatch):
    """Sıra bilinçli: bildirim en sonda — arızası hiçbir adımı geri saramaz."""
    sira: list = []
    from services import export_publisher

    monkeypatch.setattr(
        export_publisher, "notify_hukukbot", lambda doc_id: sira.append("hukukbot")
    )
    monkeypatch.setattr(
        akis.service, "notify_document_processed",
        lambda doc_id, db=None: sira.append("bildirim"),
    )
    akis.uploader(sonuc={"webUrl": "https://sp/yeni.pdf"})

    akis.queue._attempt_upload(5)

    assert sira == ["hukukbot", "bildirim"]
