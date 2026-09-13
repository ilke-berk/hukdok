"""Bildirim iyileştirmeleri (13.09.2026 prod ölçümü sonrası).

Ölçüm: prod'daki 240 bildirimin 240'ı okunmamıştı — alıcı olan sorumlu avukat
hesapları sisteme girmiyor, belgeyi yükleyen / duruşmayı giren ofis personeli
ise hiç bildirim almıyordu; `sure_yaklasti` hiç üretilmemişti (tebliğ tarihi
yalnız aktarım paketinden doluydu); gece dönüşüm retry'ı bildirim üretmiyordu.

Kilitlenen davranışlar:
  1. `email_recipients.notify_copy` bayrağı: işaretli + aktif + allowlist'te
     olan alıcılar kopya listesine girer; bayraksız/pasif/dış adres girmez,
  2. nihai alıcı = sorumlu avukat(lar) + kopyalar, tekil; `exclude` (belgeyi
     yükleyen) listeden düşer — sorumlu avukat da olsa,
  3. "belge işlendi": kopya alıcı yazılır, yükleyen YAZILMAZ; sorumlu
     çözülemezse WARNING yine düşer ama kopya alıcı bildirimi alır,
  4. gece taraması: süre/duruşma bildirimleri kopya alıcıya da yazılır
     (alıcı bazlı dedupe anahtarı satır ikilemez),
  5. yönetim listesi: `notify_copy` düzenlenebilir, "true"/"false" metni
     boolean'a çevrilir, False değeri None'a düşmez,
  6. migrasyonda `email_recipients.notify_copy` ("columns" op'u) tanımlı,
  7. karar belgesiyle girilen tebliğ tarihi aşama kararına yazılır: satır yoksa
     BELGE damgalı yeni satır, boş alan dolar, DOLU ALAN EZİLMEZ, tebligat
     (mazbata) türünde hiçbir şey yazılmaz; kart fotoğrafı tazelenir.

Testler süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar; dedupe ve
karar sırası UNIQUE kısıtları `database._MIGRATIONS`'taki gerçek DDL'den
kurulur (G081/G082/G062 deseni).
"""
import logging
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DOMAIN = "hanyaloglu-acar.av.tr"
MAIL_SERAP = f"turgal@{DOMAIN}"
MAIL_MERAL = f"meral@{DOMAIN}"
MAIL_TEL = f"tel@{DOMAIN}"


def _index_ddls(table: str) -> list[str]:
    import database

    return [
        ddl
        for op in database._MIGRATIONS
        if op[0] == "index" and op[1] == table
        for ddl in op[2]
        if not ddl.upper().startswith(("INSERT", "UPDATE"))
    ]


@pytest.fixture()
def env(monkeypatch):
    from database import Base
    import models  # noqa: F401
    from services import deadline_scanner as scanner
    from services import notification_targeting as targeting
    from services import notifications as svc

    monkeypatch.setenv("NOTIFICATION_DOMAINS", DOMAIN)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _index_ddls("notifications") + _index_ddls("case_stage_decisions"):
            conn.execute(text(ddl))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _run(fn):
        db = maker()
        try:
            return fn(db)
        finally:
            db.close()

    def _avukat(code, name, email, gorev="AVUKAT"):
        def op(db):
            db.add(models.Lawyer(code=code, name=name, email=email, gorev=gorev, active=True))
            db.commit()
        _run(op)

    def _alici(name, email, notify_copy=True, active=True, sequence=0):
        def op(db):
            db.add(models.EmailRecipient(
                name=name, email=email, notify_copy=notify_copy, active=active, sequence=sequence,
            ))
            db.commit()
        _run(op)

    def _dava(sorumlu="Av. Serap Turgal", **kw):
        def op(db):
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
            return int(row.id)
        return _run(op)

    def _belge(case_id, **kw):
        def op(db):
            row = models.CaseDocument(
                case_id=case_id,
                original_filename=kw.pop("original_filename", "karar.pdf"),
                stored_filename=kw.pop("stored_filename", "2024-1234_KARAR.pdf"),
                belge_turu_adi=kw.pop("belge_turu_adi", "Gerekçeli Karar"),
                sharepoint_url=kw.pop("sharepoint_url", "https://sp/arsiv/karar.pdf"),
                upload_status=kw.pop("upload_status", "uploaded"),
                **kw,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        return _run(op)

    def _durusma(case_id, hearing_date, **kw):
        def op(db):
            row = models.HearingDate(case_id=case_id, hearing_date=hearing_date, **kw)
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        return _run(op)

    def _bildirimler():
        return _run(lambda db: db.query(models.Notification).order_by(models.Notification.id).all())

    yield SimpleNamespace(
        models=models, scanner=scanner, targeting=targeting, svc=svc, sessions=maker, run=_run,
        avukat=_avukat, alici=_alici, dava=_dava, belge=_belge, durusma=_durusma,
        bildirimler=_bildirimler,
    )
    engine.dispose()


# ─── 1-2. kopya alıcı çözümü ─────────────────────────────────────────────────

def test_kopya_alicilar_yalniz_bayrakli_aktif_ve_allowlistte(env):
    env.alici("Nurten Meral", MAIL_MERAL, sequence=1)
    env.alici("Çiğdem Tel", "Tel@" + DOMAIN.upper(), sequence=0)          # büyük harf → normalize
    env.alici("Murat Arslan", f"arslan@{DOMAIN}", notify_copy=False)      # bayraksız
    env.alici("Pasif", f"pasif@{DOMAIN}", active=False)                   # pasif
    env.alici("Dış", "dis@gmail.com")                                     # allowlist dışı

    kopyalar = env.run(lambda db: env.targeting.copy_recipients(db))
    assert kopyalar == [MAIL_TEL, MAIL_MERAL]                              # sequence sırası


def test_nihai_alici_sorumlu_arti_kopya_yukleyen_haric(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava()

    def op(db):
        case = db.get(env.models.Case, case_id)
        return (
            env.targeting.resolve_notification_recipients(db, case),
            env.targeting.resolve_notification_recipients(db, case, exclude=MAIL_MERAL.upper()),
            env.targeting.resolve_notification_recipients(db, case, exclude=MAIL_SERAP),
        )
    hepsi, meralsiz, serapsiz = env.run(op)
    assert hepsi == ([MAIL_SERAP, MAIL_MERAL], [MAIL_SERAP])
    assert meralsiz == ([MAIL_SERAP], [MAIL_SERAP])
    # Sorumlu avukat belgeyi kendisi yüklediyse o da almaz — kural eyleme bağlı
    assert serapsiz == ([MAIL_MERAL], [MAIL_SERAP])


def test_sorumlu_cozulemezse_zapt_avukati_sonra_kopya(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava(sorumlu="Arşiv Dosya Yöneticisi")

    def op(db):
        case = db.get(env.models.Case, case_id)
        return (
            env.targeting.resolve_notification_recipients(db, case),
            env.targeting.resolve_notification_recipients(db, case, fallback="Av. Serap Turgal"),
        )
    kopya_yalniz, zapttan = env.run(op)
    assert kopya_yalniz == ([MAIL_MERAL], [])
    assert zapttan == ([MAIL_SERAP, MAIL_MERAL], [MAIL_SERAP])


# ─── 3. belge işlendi ────────────────────────────────────────────────────────

def _uret(env, doc_id):
    return env.run(lambda db: env.svc.notify_document_processed(doc_id, db=db))


def test_belge_islendi_kopya_alir_yukleyen_almaz(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.alici("Nurten Meral", MAIL_MERAL)
    env.alici("Çiğdem Tel", MAIL_TEL, sequence=1)
    case_id = env.dava()
    doc_id = env.belge(case_id, uploaded_by_email="Meral@" + DOMAIN)

    ids = _uret(env, doc_id)
    rows = env.bildirimler()
    assert len(ids) == 2 and [r.recipient_email for r in rows] == [MAIL_SERAP, MAIL_TEL]
    assert {r.dedupe_key for r in rows} == {
        f"doc-processed:{doc_id}:{MAIL_SERAP}", f"doc-processed:{doc_id}:{MAIL_TEL}",
    }
    # İkinci çağrı satır ikilemez
    assert _uret(env, doc_id) == ids and len(env.bildirimler()) == 2


def test_belge_islendi_sorumlu_cozulemese_de_kopyaya_gider_warning_kalir(env, caplog):
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava(sorumlu="Arşiv Dosya Yöneticisi")
    doc_id = env.belge(case_id, uploaded_by_email=MAIL_TEL)

    with caplog.at_level(logging.WARNING, logger="services.notifications"):
        ids = _uret(env, doc_id)
    rows = env.bildirimler()
    assert len(ids) == 1 and rows[0].recipient_email == MAIL_MERAL
    uyarilar = [r for r in caplog.records if r.levelno == logging.WARNING and "hedefsiz" in r.getMessage()]
    assert len(uyarilar) == 1 and "kopya=1" in uyarilar[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_belge_islendi_yukleyen_tek_aliciysa_bildirim_yok(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava()
    doc_id = env.belge(case_id, uploaded_by_email=MAIL_SERAP)
    assert _uret(env, doc_id) == [] and env.bildirimler() == []


# ─── 4. gece taraması ────────────────────────────────────────────────────────

def test_durusma_bildirimi_kopya_aliciya_da_yazilir_ve_ikilenmez(env):
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava()
    bugun = date(2026, 10, 5)
    hearing_id = env.durusma(case_id, bugun + timedelta(days=3))

    def tara(db):
        return env.scanner.scan_deadlines(bugun=bugun, db=db)
    s1 = env.run(tara)
    rows = env.bildirimler()
    assert s1["durusma_bildirim"] == 2 and s1["hedefsiz"] == 0
    assert {r.recipient_email for r in rows} == {MAIL_SERAP, MAIL_MERAL}
    assert {r.dedupe_key for r in rows} == {
        f"hearing:{hearing_id}:3:{MAIL_SERAP}", f"hearing:{hearing_id}:3:{MAIL_MERAL}",
    }
    env.run(tara)
    assert len(env.bildirimler()) == 2


def test_durusma_sorumlu_cozulemezse_kopya_alir_hedefsiz_sayilir(env, caplog):
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava(sorumlu="Arşiv Dosya Yöneticisi")
    bugun = date(2026, 10, 5)
    env.durusma(case_id, bugun + timedelta(days=1))

    with caplog.at_level(logging.WARNING, logger="services.deadline_scanner"):
        s = env.run(lambda db: env.scanner.scan_deadlines(bugun=bugun, db=db))
    assert s["durusma_bildirim"] == 1 and s["hedefsiz"] == 1
    assert env.bildirimler()[0].recipient_email == MAIL_MERAL
    assert [r for r in caplog.records if r.levelno == logging.WARNING and "hedefsiz" in r.getMessage()]


def test_kopya_yokken_davranis_eskisi_gibi(env):
    """Bayrak hiç açılmamışsa tarama G085 sözleşmesinin dışına çıkmaz."""
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    case_id = env.dava()
    bugun = date(2026, 10, 5)
    env.durusma(case_id, bugun + timedelta(days=3))
    s = env.run(lambda db: env.scanner.scan_deadlines(bugun=bugun, db=db))
    assert s["durusma_bildirim"] == 1
    assert [r.recipient_email for r in env.bildirimler()] == [MAIL_SERAP]


# ─── 5-6. yönetim listesi + migrasyon ────────────────────────────────────────

def test_liste_spec_notify_copy_duzenlenebilir_ve_serialize_edilir():
    from managers.reference_lists import LIST_REGISTRY, _as_bool

    spec = LIST_REGISTRY["emails"]
    assert "notify_copy" in spec.fields and "notify_copy" in spec.editable
    assert _as_bool("true") is True and _as_bool("True") is True and _as_bool("evet") is True
    assert _as_bool("false") is False and _as_bool("") is False and _as_bool(False) is False


def test_update_item_notify_copy_metnini_boolean_yazar(env, monkeypatch):
    from managers import reference_lists

    monkeypatch.setattr(reference_lists, "SessionLocal", env.sessions)
    monkeypatch.setattr(reference_lists, "refresh_cache", lambda *_: None)
    env.alici("Nurten Meral", MAIL_MERAL, notify_copy=False)

    assert reference_lists.update_item("emails", MAIL_MERAL, {"notify_copy": "true"}) == {"updated": 0}
    assert env.run(lambda db: db.query(env.models.EmailRecipient).one().notify_copy) is True
    # "false" → False (None'a DÜŞMEZ); ad dokunulmadan kalır
    assert reference_lists.update_item("emails", MAIL_MERAL, {"notify_copy": "false"}) == {"updated": 0}
    row = env.run(lambda db: db.query(env.models.EmailRecipient).one())
    assert row.notify_copy is False and row.name == "Nurten Meral"


def test_migrasyon_notify_copy_kolonunu_tanimlar():
    import database

    op = next(
        (o for o in database._MIGRATIONS if o[0] == "columns" and o[1] == "email_recipients"),
        None,
    )
    assert op is not None and "notify_copy" in op[2]
    assert "BOOLEAN" in op[2]["notify_copy"].upper()


# ─── 7. tebliğ tarihi → aşama kararı ─────────────────────────────────────────

@pytest.fixture()
def teblig(env, monkeypatch):
    from routes import processing

    monkeypatch.setattr(processing, "SessionLocal", env.sessions)
    return processing


@pytest.mark.parametrize(
    "kod, beklenen",
    [
        ("GEREKCELI-KRR_", "YEREL"), ("GEREKCELIKRR", "YEREL"), ("gerekceli-krr", "YEREL"),
        ("ISTINAF-KRR___", "ISTINAF"), ("YARGITAYKRR", "TEMYIZ"), ("KRR_DZLTM-KRR_", "KARAR_DUZELTME"),
        ("TEBLIGAT______", None), ("ARA-KRR_______", None), ("ISTINAF-BSVR__", None), ("", None), (None, None),
    ],
)
def test_karar_belgesi_turu_asamaya_eslenir_tebligat_eslenmez(teblig, kod, beklenen):
    assert teblig.decision_stage_for_doctype(kod) == beklenen


def _kararlar(env, case_id):
    return env.run(
        lambda db: db.query(env.models.CaseStageDecision)
        .filter(env.models.CaseStageDecision.case_id == case_id)
        .order_by(env.models.CaseStageDecision.sira_no).all()
    )


def test_teblig_satir_yoksa_belge_damgali_satir_acar_ve_tarihce_yazar(env, teblig):
    case_id = env.dava()
    sonuc = teblig._auto_stage_teblig(case_id, "GEREKCELIKRR", "2026-10-01", "Nurten Meral", "2026-10-02_X_GEREKCELI-KRR.pdf")
    assert sonuc == {"stage": "YEREL", "action": "eklendi", "teblig_tarihi": "2026-10-01"}
    rows = _kararlar(env, case_id)
    assert len(rows) == 1
    row = rows[0]
    assert (row.stage, row.sira_no, row.teblig_tarihi, row.dogrulama_durumu) == ("YEREL", 1, date(2026, 10, 1), "BELGE")
    assert row.source == "belge:2026-10-02_X_GEREKCELI-KRR.pdf"
    # Kart fotoğrafı tazelendi + imzalı tarihçe
    case = env.run(lambda db: db.get(env.models.Case, case_id))
    assert case.karar_teblig_tarihi == date(2026, 10, 1)
    hist = env.run(lambda db: db.query(env.models.CaseHistory).filter_by(case_id=case_id).all())
    assert len(hist) == 1 and (hist[0].field_name, hist[0].new_value, hist[0].source, hist[0].changed_by) == (
        "YEREL.teblig_tarihi", "2026-10-01", "auto-teblig", "Nurten Meral",
    )


def test_teblig_bos_alani_doldurur_dolu_alani_ezmez(env, teblig):
    case_id = env.dava()

    def op(db):
        db.add(env.models.CaseStageDecision(
            case_id=case_id, stage="ISTINAF", sira_no=1, karar_tarihi=date(2026, 9, 20),
            dogrulama_durumu="UYAP",
        ))
        db.commit()
    env.run(op)

    # UYAP damgalı satırın BOŞ tebliğ alanı belgeden dolar (ezme değil, doldurma)
    assert teblig._auto_stage_teblig(case_id, "ISTINAF-KRR___", "01.10.2026", "Çiğdem Tel", "istinaf.pdf")["action"] == "dolduruldu"
    rows = _kararlar(env, case_id)
    assert len(rows) == 1 and rows[0].teblig_tarihi == date(2026, 10, 1) and rows[0].karar_tarihi == date(2026, 9, 20)
    assert env.run(lambda db: db.get(env.models.Case, case_id)).istinaf_teblig_tarihi == date(2026, 10, 1)

    # Dolu alan: ikinci belge farklı tarih getirse de DOKUNULMAZ, tarihçe de yazılmaz
    assert teblig._auto_stage_teblig(case_id, "ISTINAF-KRR___", "2026-10-09", "Çiğdem Tel", "istinaf2.pdf") is None
    assert _kararlar(env, case_id)[0].teblig_tarihi == date(2026, 10, 1)
    assert env.run(lambda db: db.query(env.models.CaseHistory).filter_by(case_id=case_id).count()) == 1


def test_teblig_tebligat_turunde_ve_tarihsiz_cagrida_hicbir_sey_yazmaz(env, teblig):
    case_id = env.dava()
    assert teblig._auto_stage_teblig(case_id, "TEBLIGAT______", "2026-10-01", None, "mazbata.pdf") is None
    assert teblig._auto_stage_teblig(case_id, "GEREKCELIKRR", "", None, "karar.pdf") is None
    assert teblig._auto_stage_teblig(case_id, "GEREKCELIKRR", "bozuk tarih", None, "karar.pdf") is None
    assert teblig._auto_stage_teblig(None, "GEREKCELIKRR", "2026-10-01", None, "karar.pdf") is None
    assert _kararlar(env, case_id) == []


def test_teblig_yazimi_sonra_gece_taramasi_sure_uyarisi_uretir(env, teblig):
    """Uçtan uca: belgeden gelen tebliğ → 06:00 taraması T-15 uyarısı yazar."""
    env.avukat("STG", "Serap Turgal", MAIL_SERAP)
    env.alici("Nurten Meral", MAIL_MERAL)
    case_id = env.dava()
    # 01.10.2026 tebliğ → istinaf 2 hafta → son gün 15.10.2026 (G085 sabiti)
    teblig._auto_stage_teblig(case_id, "GEREKCELI-KRR_", "2026-10-01", "Nurten Meral", "karar.pdf")

    s = env.run(lambda db: env.scanner.scan_deadlines(bugun=date(2026, 10, 8), db=db))
    rows = env.bildirimler()
    assert s["sure_bildirim"] == 2
    assert {r.recipient_email for r in rows} == {MAIL_SERAP, MAIL_MERAL}
    assert all(r.type == "sure_yaklasti" and r.due_date == date(2026, 10, 15) for r in rows)
