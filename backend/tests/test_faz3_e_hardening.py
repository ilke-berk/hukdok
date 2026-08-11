"""Faz 3-E testleri: DB timeout/rollback [3.6] + cache disk kalıcılığı [3.7]
+ uvicorn --workers 2 önkoşulları.

Kapsam:
- database.py: pool/connect/statement timeout sabitleri, _build_connect_args
  (0 = statement_timeout yok — migrate muafiyeti), get_db'nin istisna yolunda
  rollback'i; migrate.py'nin import'ta DB_STATEMENT_TIMEOUT_MS=0 set etmesi
- rollback taraması: pipeline commit handler'ları commit patlarsa rollback
  çağırır ve mevcut sözleşmelerini (None/False/sessiz WARNING) korur
- DiskTTLCache: TTLCache arayüz eşdeğerliği, süreçler-arası paylaşım (iki
  instance = iki worker simülasyonu), atomik pop yarışı, adopt (payload'ın
  cache dizinine taşınması), mtime-TTL + touch, claim/orphan süpürmeleri,
  bozuk meta dayanıklılığı
- singleton_lock: lider kilidi tekliği + bırakınca devralma
- bekçiler: api.py lifespan'inde init_db YOK, süreç-tekil işler is_leader
  kapısında, boot süpürmesi var; entrypoint --workers; PROCESS_CACHE/
  DOWNLOAD_CACHE disk destekli ve doğru parametreli

DB'ye/ağa inilmez (conftest sözleşmesi).
"""
import ast
import json
import os
import threading
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ─── ortak fake'ler (test_faz3_upload_outbox kalıbı) ─────────────────────────

class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def update(self, *args, **kwargs):
        return len(self._rows)

    def delete(self, *args, **kwargs):
        return len(self._rows)


class _FakeSession:
    def __init__(self, rows=(), commit_error=None):
        self.rows = list(rows)
        self.commit_error = commit_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _FakeQuery(self.rows)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def refresh(self, row):
        if getattr(row, "id", None) is None:
            row.id = 42


# ─── [3.6] engine yapılandırması ─────────────────────────────────────────────

def test_db_timeout_constants():
    import database

    assert database.DB_POOL_TIMEOUT_SECONDS == 10
    assert database.DB_CONNECT_TIMEOUT_SECONDS == 5
    # Değerin kendisi migrate importuna göre süreçte değişebilir (env'den
    # okunur); varsayılanın 30 sn olduğu kaynaktan doğrulanır.
    assert isinstance(database.DB_STATEMENT_TIMEOUT_MS, int)
    src = (BACKEND_DIR / "database.py").read_text(encoding="utf-8")
    assert 'os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000")' in src


def test_build_connect_args_with_statement_timeout():
    from database import _build_connect_args

    args = _build_connect_args(30000)
    assert args["connect_timeout"] == 5
    assert args["options"] == "-c statement_timeout=30000"


def test_build_connect_args_zero_disables_statement_timeout():
    """migrate.py muafiyeti: 0 → statement_timeout seçeneği HİÇ gönderilmez."""
    from database import _build_connect_args

    args = _build_connect_args(0)
    assert args == {"connect_timeout": 5}


def test_engine_created_with_timeouts():
    """Bekçi: create_engine çağrısı sabitleri ve connect_args'ı kullanmalı."""
    src = (BACKEND_DIR / "database.py").read_text(encoding="utf-8")
    assert "pool_timeout=DB_POOL_TIMEOUT_SECONDS" in src
    assert "connect_args=_build_connect_args(DB_STATEMENT_TIMEOUT_MS)" in src


def test_migrate_sets_statement_timeout_exemption():
    """migrate.py import'ta env'i 0'lar — create_all + backfill'ler sınırsız."""
    import importlib

    import migrate

    importlib.reload(migrate)  # önceki testlerin import'una bağımlı kalma
    assert os.environ.get("DB_STATEMENT_TIMEOUT_MS") == "0"


def test_get_db_rolls_back_on_exception(monkeypatch):
    import database

    session = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    gen = database.get_db()
    assert next(gen) is session
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("handler patladı"))
    assert session.rollbacks == 1
    assert session.closed


def test_get_db_no_rollback_on_clean_exit(monkeypatch):
    import database

    session = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    gen = database.get_db()
    next(gen)
    gen.close()
    assert session.rollbacks == 0
    assert session.closed


# ─── [3.6] rollback taraması ─────────────────────────────────────────────────

def test_save_case_document_rolls_back_and_returns_none(monkeypatch):
    from services import document_pipeline

    session = _FakeSession(commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: session)

    doc_id = document_pipeline.save_case_document(
        case_id=None, original_filename="a.pdf", stored_filename="b.pdf"
    )
    assert doc_id is None
    assert session.rollbacks == 1
    assert session.closed


def test_auto_update_case_status_rolls_back(monkeypatch):
    import routes.processing as processing

    class _Case:
        status = "DERDEST"

    session = _FakeSession(rows=[_Case()], commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(processing, "SessionLocal", lambda: session)

    assert processing._auto_update_case_status(5, "KARAR", "test") is False
    assert session.rollbacks == 1


def test_auto_enrich_case_data_rolls_back(monkeypatch):
    import routes.processing as processing

    class _Case:
        responsible_lawyer_name = "Mevcut Avukat"
        parties = []

    session = _FakeSession(rows=[_Case()], commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(processing, "SessionLocal", lambda: session)

    result = processing._auto_enrich_case_data(5, karsi_taraf="Karşı A.Ş.")
    assert result == {}
    assert session.rollbacks == 1


def test_save_hearing_date_rolls_back(monkeypatch):
    from services import document_pipeline
    import constants

    session = _FakeSession(rows=[], commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(document_pipeline, "SessionLocal", lambda: session)
    monkeypatch.setattr(constants, "is_hearing_doctype", lambda kod: True)

    results = {}
    document_pipeline.save_hearing_date(
        linked_case_id=5,
        belge_turu_kodu="DUR",
        sonraki_durusma_tarihi="2026-09-10",
        sonraki_durusma_saati="10:00",
        avukat_adi="Av",
        new_filename="x.pdf",
        current_user_name="t",
        results=results,
    )
    assert results["hearing_date_saved"] is None
    assert session.rollbacks == 1


def test_enqueue_upload_rolls_back_on_commit_error(monkeypatch, tmp_path):
    from services import upload_queue

    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(upload_queue, "get_spool_dir", lambda: tmp_path / "spool_test")
    (tmp_path / "spool_test").mkdir()

    session = _FakeSession(commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(upload_queue, "SessionLocal", lambda: session)

    outbox_id = upload_queue.enqueue_upload("ham", str(src), "hedef.pdf", "01_HAM")
    assert outbox_id is None  # fallback sözleşmesi korunur
    assert session.rollbacks == 1
    # yarım spool kopyası temizlendi
    assert list((tmp_path / "spool_test").iterdir()) == []


def test_attempt_upload_counter_commit_failure_rolls_back_and_skips_upload(
    monkeypatch, tmp_path
):
    from services import upload_queue

    spool = tmp_path / "s.pdf"
    spool.write_bytes(b"%PDF-1.4")

    class _Row:
        id = 1
        document_id = None
        kind = "ham"
        spool_path = str(spool)
        target_filename = "t.pdf"
        target_folder = "01_HAM"
        status = "pending"
        attempts = 0

    session = _FakeSession(rows=[_Row()], commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(upload_queue, "SessionLocal", lambda: session)

    uploads = []
    import sharepoint.sharepoint_uploader_graph as uploader
    monkeypatch.setattr(
        uploader, "upload_file_to_sharepoint",
        lambda *a, **k: uploads.append(1),
    )

    with pytest.raises(RuntimeError):
        upload_queue._attempt_upload(1)
    assert session.rollbacks == 1
    assert uploads == []  # sayaç commit'i düşünce upload'a GEÇİLMEZ


def test_confirm_idempotency_complete_rolls_back_without_raising(monkeypatch):
    from services import confirm_idempotency

    session = _FakeSession(commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(confirm_idempotency, "SessionLocal", lambda: session)

    confirm_idempotency.complete("pid-x", {"status": "completed"})  # raise etmemeli
    assert session.rollbacks == 1


def test_confirm_idempotency_release_rolls_back_without_raising(monkeypatch):
    from services import confirm_idempotency

    session = _FakeSession(commit_error=RuntimeError("commit down"))
    monkeypatch.setattr(confirm_idempotency, "SessionLocal", lambda: session)

    confirm_idempotency.release("pid-x")  # raise etmemeli
    assert session.rollbacks == 1


# ─── [3.7] DiskTTLCache ──────────────────────────────────────────────────────

def _cache(tmp_path, ttl=1800, adopt=()):
    from managers.ttl_cache import DiskTTLCache

    return DiskTTLCache(tmp_path / "cache", ttl_seconds=ttl, adopt_file_fields=adopt)


def test_disk_cache_set_get_roundtrip(tmp_path):
    c = _cache(tmp_path)
    c.set("pid-1", {"path": "/tmp/a.pdf", "original_path": None,
                    "original_ext": ".pdf", "owner": "u@example.com"})
    entry = c.get("pid-1")
    assert entry == {"path": "/tmp/a.pdf", "original_path": None,
                     "original_ext": ".pdf", "owner": "u@example.com"}
    assert c.get("pid-yok") is None
    assert "pid-1" in c
    assert "pid-yok" not in c


def test_disk_cache_pop_consumes(tmp_path):
    c = _cache(tmp_path)
    c.set("pid-1", {"path": "/tmp/a.pdf", "owner": "u"})
    assert c.pop("pid-1")["path"] == "/tmp/a.pdf"
    assert c.pop("pid-1", "yok") == "yok"
    assert c.get("pid-1") is None


def test_disk_cache_delete(tmp_path):
    c = _cache(tmp_path)
    c.set("pid-1", {"path": "/tmp/a.pdf"})
    assert c.delete("pid-1") is True
    assert c.delete("pid-1") is False


def test_disk_cache_shared_between_instances(tmp_path):
    """İki instance = iki uvicorn worker'ı: /process worker A'ya, /confirm
    worker B'ye düşer; girdi diskte olduğundan B görür ve tüketir."""
    a = _cache(tmp_path)
    b = _cache(tmp_path)
    a.set("pid-cross", {"path": "/tmp/x.pdf", "owner": "u@example.com"})
    assert b.get("pid-cross") is not None
    entry = b.pop("pid-cross")
    assert entry["owner"] == "u@example.com"
    assert a.get("pid-cross") is None  # tüketim iki tarafta da görünür


def test_disk_cache_survives_new_instance_like_restart(tmp_path):
    """Restart simülasyonu: yeni instance (yeni süreç) taze girdiyi bulur;
    TTL saati mtime olduğundan süre bilgisi de restart'ı atlatır."""
    _cache(tmp_path).set("pid-r", {"path": "/tmp/x.pdf", "owner": "u"})
    fresh = _cache(tmp_path)
    assert fresh.get("pid-r") is not None
    assert fresh.cleanup_stale() == 0  # taze girdi süpürülmez


def test_disk_cache_atomic_pop_single_winner(tmp_path):
    """Yarışan iki pop'tan (iki worker) TAM olarak biri girdiyi alır."""
    a = _cache(tmp_path)
    b = _cache(tmp_path)
    a.set("pid-race", {"path": "/tmp/x.pdf"})

    barrier = threading.Barrier(2)
    results = []

    def racer(cache):
        barrier.wait()
        results.append(cache.pop("pid-race"))

    t1 = threading.Thread(target=racer, args=(a,))
    t2 = threading.Thread(target=racer, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert winners[0]["path"] == "/tmp/x.pdf"


def test_disk_cache_touch_refreshes_ttl(tmp_path):
    c = _cache(tmp_path, ttl=1800)
    c.set("pid-t", {"path": "/tmp/x.pdf"})
    meta = c._meta_path("pid-t")
    old = time.time() - 3600
    os.utime(meta, (old, old))  # süresi geçmiş gibi damgala

    assert c.touch("pid-t") is True  # TTL tazelendi
    assert c.cleanup_stale() == 0
    assert c.get("pid-t") is not None
    assert c.touch("pid-yok") is False


def test_disk_cache_cleanup_evicts_stale_with_callback(tmp_path):
    c = _cache(tmp_path, ttl=1800)
    c.set("pid-old", {"path": "/tmp/x.pdf", "original_path": "/tmp/y.udf"})
    c.set("pid-new", {"path": "/tmp/z.pdf"})
    meta = c._meta_path("pid-old")
    old = time.time() - 3600
    os.utime(meta, (old, old))

    evicted = []
    assert c.cleanup_stale(on_evict=lambda k, v: evicted.append((k, v))) == 1
    assert evicted[0][0] == "pid-old"
    assert evicted[0][1]["original_path"] == "/tmp/y.udf"
    assert c.get("pid-old") is None
    assert c.get("pid-new") is not None


def test_disk_cache_concurrent_cleanup_evicts_once(tmp_path):
    """İki worker aynı anda süpürürse girdi TEK kez evict edilir (claim)."""
    a = _cache(tmp_path, ttl=1800)
    b = _cache(tmp_path, ttl=1800)
    a.set("pid-old", {"path": "/tmp/x.pdf"})
    old = time.time() - 3600
    os.utime(a._meta_path("pid-old"), (old, old))

    evictions = []
    barrier = threading.Barrier(2)

    def sweeper(cache):
        barrier.wait()
        cache.cleanup_stale(on_evict=lambda k, v: evictions.append(k))

    t1 = threading.Thread(target=sweeper, args=(a,))
    t2 = threading.Thread(target=sweeper, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert evictions == ["pid-old"]


def test_disk_cache_adopts_payload_files(tmp_path):
    """set() payload dosyalarını cache dizinine taşır (uzantı korunur);
    kaynak yol boşalır — /tmp'de doğan dosya volume'e geçmiş olur."""
    src_dir = tmp_path / "sistem_temp"
    src_dir.mkdir()
    pdf = src_dir / "analiz.pdf"
    udf = src_dir / "orijinal.udf"
    pdf.write_bytes(b"%PDF-1.4")
    udf.write_bytes(b"PK\x03\x04")

    c = _cache(tmp_path, adopt=("path", "original_path"))
    c.set("pid-a", {"path": str(pdf), "original_path": str(udf),
                    "original_ext": ".udf", "owner": "u"})

    entry = c.get("pid-a")
    assert not pdf.exists() and not udf.exists()  # taşındı
    for field, suffix in (("path", ".pdf"), ("original_path", ".udf")):
        new_path = Path(entry[field])
        assert new_path.parent == c._dir
        assert new_path.suffix == suffix
        assert new_path.exists()
    assert entry["owner"] == "u"  # diğer alanlar aynen taşınır


def test_disk_cache_adopt_missing_file_keeps_value(tmp_path):
    c = _cache(tmp_path, adopt=("path", "original_path"))
    c.set("pid-b", {"path": "/tmp/hic-yok.pdf", "original_path": None})
    entry = c.get("pid-b")
    assert entry["path"] == "/tmp/hic-yok.pdf"
    assert entry["original_path"] is None


def test_disk_cache_eviction_deletes_adopted_payloads(tmp_path):
    """Uçtan uca: adopt edilen payload'lar routes'un evict callback'iyle
    (safe_remove path + original_path) diskten silinir."""
    from file_utils import safe_remove

    src = tmp_path / "kaynak.pdf"
    src.write_bytes(b"%PDF-1.4")
    c = _cache(tmp_path, ttl=1800, adopt=("path", "original_path"))
    c.set("pid-e", {"path": str(src), "original_path": None})
    stored = Path(c.get("pid-e")["path"])
    assert stored.exists()

    old = time.time() - 3600
    os.utime(c._meta_path("pid-e"), (old, old))

    def _evict(k, entry):
        safe_remove(entry.get("path"))
        if entry.get("original_path"):
            safe_remove(entry.get("original_path"))

    assert c.cleanup_stale(on_evict=_evict) == 1
    assert not stored.exists()


def test_disk_cache_corrupt_meta_is_miss_and_swept(tmp_path):
    c = _cache(tmp_path, ttl=1800)
    bad = c._dir / "pid-bozuk.json"
    bad.write_text("{yarim json", encoding="utf-8")
    assert c.get("pid-bozuk") is None

    old = time.time() - 3600
    os.utime(bad, (old, old))
    evicted = []
    assert c.cleanup_stale(on_evict=lambda k, v: evicted.append(k)) == 0
    assert evicted == []
    assert not bad.exists()  # bozuk dosya sessizce düşürüldü


def test_disk_cache_stale_claim_swept_with_payload_cleanup(tmp_path):
    """Pop ortasında ölen sürecin claim dosyası: içerik okunabiliyorsa
    payload'lar on_evict'le silinir, claim düşer."""
    c = _cache(tmp_path, ttl=1800)
    payload = c._dir / "pid-c.path-abc.pdf"
    payload.write_bytes(b"%PDF-1.4")
    claim = c._dir / "pid-c.claim-dead1234"
    claim.write_text(json.dumps({"path": str(payload)}), encoding="utf-8")
    old = time.time() - 3600
    os.utime(claim, (old, old))
    os.utime(payload, (old, old))

    from file_utils import safe_remove
    c.cleanup_stale(on_evict=lambda k, v: safe_remove(v.get("path")))
    assert not claim.exists()
    assert not payload.exists()


def test_disk_cache_orphan_payload_swept_after_double_ttl(tmp_path):
    c = _cache(tmp_path, ttl=1800)
    orphan = c._dir / "pid-o.path-xyz.pdf"
    orphan.write_bytes(b"%PDF-1.4")

    old = time.time() - 1800 - 10
    os.utime(orphan, (old, old))
    c.cleanup_stale()
    assert orphan.exists()  # 1×TTL yetmez — yaşayan girdinin payload'ı olabilir

    older = time.time() - 3600 - 10
    os.utime(orphan, (older, older))
    c.cleanup_stale()
    assert not orphan.exists()


def test_disk_cache_key_is_sanitized(tmp_path):
    c = _cache(tmp_path)
    c.set("../kacak/anahtar", {"path": "/tmp/x.pdf"})
    assert (tmp_path / "kacak").exists() is False  # dizin dışına yazılmadı
    assert c.get("../kacak/anahtar") is not None  # aynı anahtarla erişilebilir
    files = list(c._dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].parent == c._dir  # meta cache dizininin İÇİNDE


# ─── süreç-tekil lider kilidi ────────────────────────────────────────────────

def test_singleton_lock_single_winner(tmp_path):
    from services.singleton_lock import _try_lock_file

    lock_path = tmp_path / "leader.lock"
    h1 = _try_lock_file(lock_path)
    assert h1 is not None
    h2 = _try_lock_file(lock_path)
    assert h2 is None  # ikinci taliP kilidi alamaz

    h1.close()  # süreç ölümü simülasyonu: kilit bırakılır
    h3 = _try_lock_file(lock_path)
    assert h3 is not None  # devralma
    h3.close()


def test_try_acquire_leader_idempotent(tmp_path, monkeypatch):
    import tempfile as _tempfile

    from services import singleton_lock

    monkeypatch.setattr(_tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(singleton_lock, "_handle", None)

    assert singleton_lock.try_acquire_leader() is True
    assert singleton_lock.try_acquire_leader() is True  # idempotent
    handle = singleton_lock._handle
    assert handle is not None
    handle.close()
    monkeypatch.setattr(singleton_lock, "_handle", None)


# ─── bekçiler: lifespan / entrypoint / cache kuruluşu ────────────────────────

def _lifespan_ast():
    src = (BACKEND_DIR / "api.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            return src, node
    raise AssertionError("api.py'de lifespan bulunamadı")


def test_lifespan_has_no_init_db():
    """3-E: migrasyonun tek sahibi entrypoint'teki migrate.py — lifespan'de
    init_db kalırsa her worker DDL koşar (yarış) ve statement_timeout'lu
    app engine'inde uzun backfill'ler kesilir. (AST bazlı: yorum satırındaki
    anma değil, gerçek çağrı/import aranır.)"""
    src, _ = _lifespan_ast()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            assert name != "init_db", "api.py init_db çağırmamalı (migrate.py'nin işi)"
        if isinstance(node, ast.ImportFrom):
            assert "init_db" not in [a.name for a in node.names], (
                "api.py init_db import etmemeli"
            )


def _count_in_leader_gates(fn_node, needle: str) -> tuple:
    total = ast.dump(fn_node).count(needle)
    gated = 0
    for node in ast.walk(fn_node):
        if isinstance(node, ast.If) and "is_leader" in ast.dump(node.test):
            gated += ast.dump(node).count(needle)
    return total, gated

def test_singleton_background_jobs_are_leader_gated():
    """Süreç-tekil işler (outbox worker, APScheduler, catch-up, gece dönüşüm
    retry'ı) yalnız is_leader kapısının içinde başlatılabilir — kapı kalkarsa
    worker sayısı kadar kopya koşar (aynı satır N kez yüklenir, N kopya rapor,
    aynı belge N kez dönüştürülür)."""
    _, lifespan = _lifespan_ast()
    for needle in (
        "start_upload_worker",
        "BackgroundScheduler",
        "catch_up_missed_reports",
        "retry_pending_conversions",  # Faz 3-F gece job'ı (scheduler'a job olarak)
    ):
        total, gated = _count_in_leader_gates(lifespan, needle)
        assert total > 0, f"lifespan'de {needle} yok"
        assert total == gated, f"{needle} is_leader kapısı DIŞINDA çağrılıyor"


def test_refresh_thread_is_per_worker():
    """Bilinçli karar: refresh thread'i worker-BAŞINA (DynamicConfig/matcher
    süreç içi) — lider kapısına alınırsa diğer worker'lar boş listeyle kalır."""
    _, lifespan = _lifespan_ast()
    total, gated = _count_in_leader_gates(lifespan, "refresh_lists_background")
    assert total > 0
    assert gated == 0, "refresh thread'i is_leader kapısına alınmamalı"


def test_lifespan_runs_boot_cache_cleanup():
    src, lifespan = _lifespan_ast()
    assert "_cleanup_process_cache" in ast.dump(lifespan), (
        "boot'ta disk cache TTL süpürmesi çağrılmalı (3.7: 'TTL indeksini yeniden kur')"
    )


def test_entrypoint_starts_two_workers_with_env_override():
    src = (BACKEND_DIR / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "--workers ${UVICORN_WORKERS:-2}" in src, (
        "uvicorn --workers env'den (varsayılan 2) gelmeli — UVICORN_WORKERS=1 "
        "imajsız geri dönüş yoludur"
    )


def test_process_and_download_caches_are_disk_backed():
    from managers.ttl_cache import DiskTTLCache
    from routes.processing import DOWNLOAD_CACHE, PROCESS_CACHE

    assert isinstance(PROCESS_CACHE, DiskTTLCache)
    assert isinstance(DOWNLOAD_CACHE, DiskTTLCache)
    assert PROCESS_CACHE._ttl == 1800
    assert DOWNLOAD_CACHE._ttl == 3600
    # payload sahiplenme yalnız PROCESS_CACHE'te: download payload'ı 30 sn
    # sonra silinen temp dosyadır, taşımak anlamsız (karar notu processing.py'de)
    assert PROCESS_CACHE._adopt_fields == ("path", "original_path")
    assert DOWNLOAD_CACHE._adopt_fields == ()


def test_json_log_lines_carry_pid():
    """2 worker'da log satırının kaynağı (worker-başına state teşhisi) pid'den
    okunur — JsonFormatter alanı düşürmemeli."""
    import logging

    from logging_setup import JsonFormatter

    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "mesaj", (), None)
    line = json.loads(JsonFormatter().format(rec))
    assert line["pid"] == os.getpid()
