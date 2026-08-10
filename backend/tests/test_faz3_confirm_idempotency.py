"""Faz 3-D (plan 3.5) — /confirm idempotency + /commit 409 idempotent çözümleme.

DB/ağ yok: idempotency kaydı ve dava eşleşmesi süreç içi sqlite (StaticPool)
üzerinde koşar — modül SessionLocal'ları monkeypatch'lenir (konteynerde
doğrulandı: aware yazım naive-UTC okunur, eşitlik/karşılaştırma filtreleri
çalışır). Pipeline adımları test_case_intake_commit kalıbıyla sahtelenir;
accept_incoming_file GERÇEK çalışır (PROCESS_CACHE POP semantiği korunur).
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def sqlite_sessions():
    """Paylaşılan in-memory sqlite: Base.metadata'daki TÜM tablolar kurulur."""
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield maker
    engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
# 1) confirm_idempotency servisi — birim testleri
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def idem(sqlite_sessions, monkeypatch):
    from services import confirm_idempotency

    monkeypatch.setattr(confirm_idempotency, "SessionLocal", sqlite_sessions)
    return SimpleNamespace(svc=confirm_idempotency, sessions=sqlite_sessions)


def _get_row(sessions, pid):
    import models

    db = sessions()
    try:
        return db.query(models.ConfirmReceipt).filter(
            models.ConfirmReceipt.process_id == pid
        ).first()
    finally:
        db.close()


def test_begin_ilk_cagri_proceed_ve_satir_acar(idem):
    verdict, replay = idem.svc.begin("pid-1", "user@x.com")
    assert (verdict, replay) == ("proceed", None)
    row = _get_row(idem.sessions, "pid-1")
    assert row is not None and row.status == "in_progress"
    assert row.owner == "user@x.com"


def test_begin_canli_in_progress_409_verdikti(idem):
    idem.svc.begin("pid-2", "user@x.com")
    verdict, replay = idem.svc.begin("pid-2", "user@x.com")
    assert (verdict, replay) == ("in_progress", None)


def test_complete_sonrasi_replay_ayni_yaniti_doner(idem):
    idem.svc.begin("pid-3", "user@x.com")
    payload = {"status": "completed", "results": {"case_document_id": 7}, "timings": {}}
    idem.svc.complete("pid-3", payload)
    verdict, replay = idem.svc.begin("pid-3", "user@x.com")
    assert verdict == "replay"
    assert replay == payload


def test_release_sonrasi_retry_serbest(idem):
    idem.svc.begin("pid-4", "user@x.com")
    idem.svc.release("pid-4")
    verdict, _ = idem.svc.begin("pid-4", "user@x.com")
    assert verdict == "proceed"


def test_owner_uyusmazligi_yanit_sizdirmaz(idem):
    idem.svc.begin("pid-5", "asil@x.com")
    idem.svc.complete("pid-5", {"status": "completed", "results": {}, "timings": {}})
    verdict, replay = idem.svc.begin("pid-5", "baskasi@x.com")
    assert (verdict, replay) == ("in_progress", None)


def test_bayat_in_progress_devralinir(idem):
    import models

    idem.svc.begin("pid-6", "user@x.com")
    stale = datetime.now(timezone.utc) - timedelta(
        seconds=idem.svc.STALE_IN_PROGRESS_SECONDS + 60
    )
    db = idem.sessions()
    db.query(models.ConfirmReceipt).filter(
        models.ConfirmReceipt.process_id == "pid-6"
    ).update({"created_at": stale, "updated_at": stale}, synchronize_session=False)
    db.commit()
    db.close()

    verdict, _ = idem.svc.begin("pid-6", "user@x.com")
    assert verdict == "proceed"
    # Devralınan satır tazelendi: ikinci eşzamanlı deneme artık 409 yer
    verdict2, _ = idem.svc.begin("pid-6", "user@x.com")
    assert verdict2 == "in_progress"


def test_eski_kayitlar_firsatci_temizlikle_duser(idem):
    import models

    idem.svc.begin("pid-eski", "user@x.com")
    idem.svc.complete("pid-eski", {"status": "completed", "results": {}, "timings": {}})
    old = datetime.now(timezone.utc) - timedelta(days=idem.svc.RETENTION_DAYS + 1)
    db = idem.sessions()
    db.query(models.ConfirmReceipt).update(
        {"created_at": old}, synchronize_session=False
    )
    db.commit()
    db.close()

    idem.svc.begin("pid-yeni", "user@x.com")
    assert _get_row(idem.sessions, "pid-eski") is None
    assert _get_row(idem.sessions, "pid-yeni") is not None


def test_db_arizasinda_bypass_kapiyi_atlar(idem, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(idem.svc, "SessionLocal", boom)
    verdict, replay = idem.svc.begin("pid-7", "user@x.com")
    assert (verdict, replay) == ("bypass", None)
    # complete/release de fırlatmaz (best-effort)
    idem.svc.complete("pid-7", {"a": 1})
    idem.svc.release("pid-7")


# ═════════════════════════════════════════════════════════════════════════════
# 2) /confirm route kablolaması — replay / 409 / release davranışı
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def confirm_env(sqlite_sessions, monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import processing
    from routes.processing import PROCESS_CACHE
    from services import confirm_idempotency, document_pipeline

    monkeypatch.setattr(confirm_idempotency, "SessionLocal", sqlite_sessions)

    calls = {"convert": [], "email": [], "cleanup": []}

    def fake_convert(**kwargs):
        calls["convert"].append(kwargs)
        pdfa = tmp_path / f"pdfa_{len(calls['convert'])}.pdf"
        pdfa.write_bytes(b"%PDF pdfa")
        doc_id = 900 + len(calls["convert"])
        kwargs["results"]["case_document_id"] = doc_id  # gerçek davranışın aynası
        return (str(pdfa), doc_id)

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", fake_convert)

    async def fake_send_email(**kwargs):
        calls["email"].append(kwargs)
        kwargs["results"]["email"] = "Gönderildi"

    monkeypatch.setattr(document_pipeline, "send_notification_email", fake_send_email)
    monkeypatch.setattr(
        document_pipeline, "schedule_cleanup",
        lambda *a, **k: calls["cleanup"].append((a, k)),
    )

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {
            "path": str(p), "original_path": None, "original_ext": ".pdf",
            "owner": "test@example.com",
        })
        return p

    app = FastAPI()
    app.include_router(processing.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    client = TestClient(app, raise_server_exceptions=False)
    return SimpleNamespace(
        client=client, calls=calls, put_cache=put_cache,
        cache=PROCESS_CACHE, sessions=sqlite_sessions, svc=confirm_idempotency,
    )


def _confirm_form(pid=None, **extra):
    form = {
        "new_filename": "2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf",
        "send_email": "false",
        "is_test_mode": "true",
    }
    if pid:
        form["process_id"] = pid
    form.update(extra)
    return form


def test_confirm_basari_sonrasi_retry_pipeline_kosmaz_replay_doner(confirm_env):
    confirm_env.put_cache("pid-c1")
    r1 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c1"))
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["results"]["case_document_id"] == 901
    assert len(confirm_env.calls["convert"]) == 1

    # 504 senaryosu: kullanıcı aynı process_id ile tekrar basar (cache POP'lu,
    # dosya fallback'i de yok) — kapı pipeline'a hiç inmeden saklanan yanıtı verir.
    r2 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c1"))
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["results"]["idempotent_replay"] is True
    assert body2["results"]["case_document_id"] == 901
    assert len(confirm_env.calls["convert"]) == 1  # pipeline TEKRAR KOŞMADI
    assert len(confirm_env.calls["email"]) == 0    # mükerrer e-posta yok


def test_confirm_suren_islem_409_dondurur_ve_belge_tuketmez(confirm_env):
    import models

    db = confirm_env.sessions()
    db.add(models.ConfirmReceipt(
        process_id="pid-c2", owner="test@example.com", status="in_progress",
    ))
    db.commit()
    db.close()

    confirm_env.put_cache("pid-c2")
    r = confirm_env.client.post("/confirm", data=_confirm_form("pid-c2"))
    assert r.status_code == 409
    assert "TEKRAR GÖNDERMEYİN" in r.json()["detail"]
    assert confirm_env.calls["convert"] == []
    # Kapı ilk yan etkiden önce: cache girdisi POP edilmedi, ilk istek kullanacak
    assert confirm_env.cache.touch("pid-c2") is True


def test_confirm_belge_yaratilmadan_dusen_istek_kaydi_birakir(confirm_env, monkeypatch):
    from fastapi import HTTPException

    from services import document_pipeline

    calls = confirm_env.calls

    def convert_ilk_seferde_patlar(**kwargs):
        calls["convert"].append(kwargs)
        if len(calls["convert"]) == 1:
            # Belge YARATILMADAN düşer (results'a case_document_id yazılmadı)
            raise HTTPException(status_code=500, detail="PDF/A dönüşümü başarısız (test)")
        kwargs["results"]["case_document_id"] = 999
        return (None, 999)

    monkeypatch.setattr(
        document_pipeline, "convert_pdfa_and_queue_uploads", convert_ilk_seferde_patlar
    )
    confirm_env.put_cache("pid-c3")
    r1 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c3"))
    assert r1.status_code == 500
    assert _get_row(confirm_env.sessions, "pid-c3") is None  # release edildi

    # Retry serbest: dönüşüm düzelince aynı process_id ile kayıt tamamlanır
    confirm_env.put_cache("pid-c3")
    r2 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c3"))
    assert r2.status_code == 200
    row = _get_row(confirm_env.sessions, "pid-c3")
    assert row is not None and row.status == "completed"


def test_confirm_belge_yaratildiktan_sonra_dusen_istek_kilidi_tutar(confirm_env, monkeypatch):
    from services import document_pipeline

    async def email_patlar(**kwargs):
        raise RuntimeError("SMTP down (test)")

    monkeypatch.setattr(document_pipeline, "send_notification_email", email_patlar)
    confirm_env.put_cache("pid-c4")
    r1 = confirm_env.client.post(
        "/confirm",
        data=_confirm_form("pid-c4", send_email="true", custom_to_json='["a@b.c"]'),
    )
    assert r1.status_code == 500
    # Belge yaratılmıştı (convert koştu) → kayıt in_progress KALIR: yeniden
    # koşmak belgeyi mükerrer yaratırdı; retry 409 alır.
    row = _get_row(confirm_env.sessions, "pid-c4")
    assert row is not None and row.status == "in_progress"
    r2 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c4"))
    assert r2.status_code == 409
    assert len(confirm_env.calls["convert"]) == 1


def test_confirm_process_id_yoksa_kapi_devrede_degil(confirm_env, tmp_path):
    import models

    p = tmp_path / "dosya.pdf"
    p.write_bytes(b"%PDF-1.4 fake\n%%EOF")
    with open(p, "rb") as f:
        r = confirm_env.client.post(
            "/confirm",
            data=_confirm_form(None),
            files={"file": ("dosya.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200
    db = confirm_env.sessions()
    try:
        assert db.query(models.ConfirmReceipt).count() == 0
    finally:
        db.close()


def test_confirm_db_arizasinda_korumasiz_calisir(confirm_env, monkeypatch):
    from services import confirm_idempotency

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(confirm_idempotency, "SessionLocal", boom)
    confirm_env.put_cache("pid-c5")
    r1 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c5"))
    assert r1.status_code == 200
    # Kapı yok = bugünkü davranış: retry pipeline'ı yeniden koşar (bilinçli
    # fallback — kapı arızası /confirm'i durdurmamalı)
    confirm_env.put_cache("pid-c5")
    r2 = confirm_env.client.post("/confirm", data=_confirm_form("pid-c5"))
    assert r2.status_code == 200
    assert len(confirm_env.calls["convert"]) == 2


# ═════════════════════════════════════════════════════════════════════════════
# 3) find_idempotent_commit_match — birim testleri (sqlite)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def match_db(sqlite_sessions, monkeypatch):
    from managers import case_manager

    monkeypatch.setattr(case_manager, "SessionLocal", sqlite_sessions)
    return SimpleNamespace(cm=case_manager, sessions=sqlite_sessions)


def _seed_case(sessions, tracking_no="2026/0456", esas_no="2024/1",
               court="ANKARA 3. ASLİYE HUKUK MAHKEMESİ", parties=None, **extra):
    import models

    db = sessions()
    try:
        case = models.Case(
            tracking_no=tracking_no, esas_no=esas_no, court=court,
            status="DERDEST", **extra,
        )
        db.add(case)
        db.flush()
        for name, ptype in (parties or [("Ahmet YILMAZ", "CLIENT")]):
            db.add(models.CaseParty(
                case_id=case.id, name=name, role="DAVACI", party_type=ptype,
            ))
        db.commit()
        return case.id
    finally:
        db.close()


def _req_data(**overrides):
    data = {
        "tracking_no": "2026/0456",
        "esas_no": "2024/1",
        "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
        "parties": [{"name": "Ahmet YILMAZ", "party_type": "CLIENT", "role": "DAVACI"}],
    }
    data.update(overrides)
    return data


def test_match_ayni_taslak_yeni_dava_eslesir(match_db):
    case_id = _seed_case(match_db.sessions)
    m = match_db.cm.find_idempotent_commit_match(_req_data())
    assert m is not None
    assert m["id"] == case_id
    assert m["reused"] is True
    assert m["tracking_no"] == "2026/0456"
    assert m["status"] == "DERDEST"


def test_match_taraf_adi_normalize_ile_eslesir(match_db):
    # Büyük/küçük ve boşluk farkları tolere edilir (normalize_party_key)
    _seed_case(match_db.sessions, parties=[("AHMET  YILMAZ", "CLIENT")])
    m = match_db.cm.find_idempotent_commit_match(_req_data())
    assert m is not None


def test_match_eski_dava_eslesmez_gercek_cakisma(match_db):
    import models

    _seed_case(match_db.sessions)
    old = datetime.now(timezone.utc) - timedelta(
        hours=match_db.cm.IDEMPOTENT_MATCH_WINDOW_HOURS + 1
    )
    db = match_db.sessions()
    db.query(models.Case).update({"created_at": old}, synchronize_session=False)
    db.commit()
    db.close()
    assert match_db.cm.find_idempotent_commit_match(_req_data()) is None


def test_match_farkli_taraf_kumesi_eslesmez(match_db):
    _seed_case(match_db.sessions, parties=[("Mehmet KAYA", "CLIENT")])
    assert match_db.cm.find_idempotent_commit_match(_req_data()) is None


def test_match_farkli_esas_no_eslesmez(match_db):
    _seed_case(match_db.sessions, esas_no="2024/99")
    assert match_db.cm.find_idempotent_commit_match(_req_data()) is None


def test_match_soft_delete_edilmis_dava_eslesmez(match_db):
    _seed_case(match_db.sessions, deleted_at=datetime.now(timezone.utc))
    assert match_db.cm.find_idempotent_commit_match(_req_data()) is None


def test_match_tarafsiz_istek_eslesmez(match_db):
    _seed_case(match_db.sessions)
    assert match_db.cm.find_idempotent_commit_match(_req_data(parties=[])) is None


def test_match_baska_tenant_damgali_dava_eslesmez(match_db):
    _seed_case(match_db.sessions, tenant_id="tenant-baska")
    assert match_db.cm.find_idempotent_commit_match(_req_data(), tenant_id="tenant-1") is None
    # Damgasız (ortak havuz NULL) dava aynı tenant sorusuna eşleşir
    _seed_case(match_db.sessions, tracking_no="2026/0457")
    m = match_db.cm.find_idempotent_commit_match(
        _req_data(tracking_no="2026/0457"), tenant_id="tenant-1"
    )
    assert m is not None


def test_get_case_document_filenames_soft_delete_haric(match_db):
    import models

    case_id = _seed_case(match_db.sessions)
    db = match_db.sessions()
    db.add(models.CaseDocument(
        case_id=case_id, original_filename="a.pdf", stored_filename="ARSIV-A.pdf",
    ))
    db.add(models.CaseDocument(
        case_id=case_id, original_filename="b.pdf", stored_filename="ARSIV-B.pdf",
        deleted_at=datetime.now(timezone.utc),
    ))
    db.commit()
    db.close()
    mapping = match_db.cm.get_case_document_filenames(case_id)
    assert "ARSIV-A.pdf" in mapping
    assert "ARSIV-B.pdf" not in mapping


# ═════════════════════════════════════════════════════════════════════════════
# 4) /commit 409 çözümleme — route kablolaması
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def commit_env(monkeypatch, tmp_path):
    """test_case_intake_commit'in env kalıbının 3-D odaklı kopyası."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from managers import case_manager
    from routes import case_intake
    from routes.processing import PROCESS_CACHE
    from services import document_pipeline

    calls = {"add_case": [], "convert": [], "match": [], "doc_lookup": []}

    def fake_add_case_duplicate(data):
        calls["add_case"].append(data)
        return {"error": "duplicate_tracking_no"}

    monkeypatch.setattr(case_manager, "add_case", fake_add_case_duplicate)
    monkeypatch.setattr(
        document_pipeline, "validate_tenant_and_resolve_lawyer",
        lambda case_id, user, avukat_kodu: "AVK1",
    )

    doc_ids = iter(range(41, 99))

    def fake_convert(**kwargs):
        calls["convert"].append(kwargs)
        pdfa = tmp_path / f"pdfa_{len(calls['convert'])}.pdf"
        pdfa.write_bytes(b"%PDF pdfa")
        return (str(pdfa), next(doc_ids))

    monkeypatch.setattr(document_pipeline, "convert_pdfa_and_queue_uploads", fake_convert)
    monkeypatch.setattr(document_pipeline, "schedule_cleanup", lambda *a, **k: None)

    def put_cache(pid):
        p = tmp_path / f"{pid}.pdf"
        p.write_bytes(b"%PDF fake")
        PROCESS_CACHE.set(pid, {
            "path": str(p), "original_path": None, "original_ext": ".pdf",
            "owner": "test@example.com",
        })
        return p

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    return SimpleNamespace(
        client=TestClient(app), calls=calls, put_cache=put_cache,
        cache=PROCESS_CACHE, cm=case_manager,
    )


def _commit_payload(**overrides):
    payload = {
        "case": {
            "tracking_no": "2026/0456",
            "esas_no": "2024/1",
            "status": "KARAR",
            "court": "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
            "responsible_lawyer_name": "Av. Deniz",
            "parties": [
                {"name": "Ahmet YILMAZ", "role": "DAVACI",
                 "party_type": "CLIENT", "client_id": 12},
            ],
        },
        "documents": [],
        "policies": [],
        "options": {"send_email": False},
    }
    payload.update(overrides)
    return payload


def _commit_doc(pid, filename="2024-01-15_AHMET-YILMAZ_TENSIP-ZPT____.pdf"):
    return {"process_id": pid, "new_filename": filename,
            "belge_turu_kodu": "TENSIP-ZPT____", "esas_no": "2024/1"}


def test_commit_409_eslesme_varsa_mevcut_dava_idempotent_doner(commit_env, monkeypatch):
    def fake_match(data, tenant_id=None):
        commit_env.calls["match"].append((data.get("tracking_no"), tenant_id))
        return {
            "id": 777, "tracking_no": data.get("tracking_no"),
            "esas_no": data.get("esas_no"), "court": data.get("court") or "",
            "status": "DERDEST", "responsible_lawyer_name": "Av. Deniz",
            "reused": True,
        }

    monkeypatch.setattr(commit_env.cm, "find_idempotent_commit_match", fake_match)
    monkeypatch.setattr(commit_env.cm, "get_case_document_filenames", lambda cid: {})

    r = commit_env.client.post("/api/case-intake/commit", json=_commit_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["id"] == 777
    assert body["case"]["idempotent_reuse"] is True
    assert body["case"]["tracking_no"] == "2026/0456"
    assert commit_env.calls["match"] == [("2026/0456", "tenant-1")]


def test_commit_409_eslesme_yoksa_ayni_409_devam_eder(commit_env, monkeypatch):
    monkeypatch.setattr(
        commit_env.cm, "find_idempotent_commit_match", lambda data, tenant_id=None: None
    )
    commit_env.put_cache("pid-dup2")
    r = commit_env.client.post(
        "/api/case-intake/commit",
        json=_commit_payload(documents=[_commit_doc("pid-dup2")]),
    )
    assert r.status_code == 409
    assert "2026/0456" in r.json()["detail"]
    # 409'da hiçbir belge tüketilmedi (mevcut garanti korunuyor)
    assert commit_env.cache.touch("pid-dup2") is True
    assert commit_env.calls["convert"] == []


def test_commit_409_reuse_arsivli_belge_tekrar_arsivlenmez(commit_env, monkeypatch):
    monkeypatch.setattr(
        commit_env.cm, "find_idempotent_commit_match",
        lambda data, tenant_id=None: {
            "id": 777, "tracking_no": "2026/0456", "esas_no": "2024/1",
            "court": "", "status": "DERDEST", "responsible_lawyer_name": "",
            "reused": True,
        },
    )

    def fake_lookup(case_id):
        commit_env.calls["doc_lookup"].append(case_id)
        # sanitize_filename padding'i teke indirir — davadaki kayıtlı ad böyle
        return {"2024-01-15_AHMET-YILMAZ_TENSIP-ZPT_.pdf": 555}

    monkeypatch.setattr(commit_env.cm, "get_case_document_filenames", fake_lookup)

    commit_env.put_cache("pid-yeni")
    r = commit_env.client.post(
        "/api/case-intake/commit",
        json=_commit_payload(documents=[
            _commit_doc("pid-eski"),  # davada zaten var → yeniden arşivlenmez
            _commit_doc("pid-yeni", filename="2024-02-01_AHMET-YILMAZ_TEBLIGAT______.pdf"),
        ]),
    )
    assert r.status_code == 200
    body = r.json()
    assert commit_env.calls["doc_lookup"] == [777]
    # Yanıt istek sırasını korur: ilk belge mevcut id'siyle, ikincisi arşivlendi
    docs = body["documents"]
    assert [d["process_id"] for d in docs] == ["pid-eski", "pid-yeni"]
    assert docs[0] == {"process_id": "pid-eski", "status": "queued",
                       "document_id": 555, "error_ozet": None}
    assert docs[1]["status"] == "queued"
    assert docs[1]["document_id"] == 41
    # Yalnız yeni belge için pipeline koştu; eski belgenin cache'i tüketilmedi
    assert len(commit_env.calls["convert"]) == 1
    assert commit_env.calls["convert"][0]["linked_case_id"] == 777


def test_commit_normal_kayitta_reuse_bayragi_false(commit_env, monkeypatch):
    def fake_add_case_ok(data):
        return {"id": 123, "tracking_no": data.get("tracking_no"),
                "esas_no": data.get("esas_no"), "court": data.get("court") or "",
                "status": "DERDEST", "responsible_lawyer_name": ""}

    monkeypatch.setattr(commit_env.cm, "add_case", fake_add_case_ok)
    r = commit_env.client.post("/api/case-intake/commit", json=_commit_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["idempotent_reuse"] is False
    assert body["case"]["status"] == "DERDEST"
