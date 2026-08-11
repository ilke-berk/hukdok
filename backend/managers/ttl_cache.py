"""Süreli önbellek iki biçimde: süreç-içi `TTLCache` ve disk destekli `DiskTTLCache`.

`TTLCache` RLock korumalı bellek sözlüğüdür (tek süreç). `DiskTTLCache` girdiyi dosyaya
yazar; TTL saati dosya mtime'ıdır, `pop()` claim dosyasıyla atomiktir ve
`cleanup_stale()` sahipsiz payload'ı 2×TTL'de süpürür — böylece uvicorn'un iki
worker'ı `/process`→`/confirm` çaprazında aynı girdiyi paylaşır, girdi restart'ı atlatır.
Tek tüketici `routes/processing.py` (PROCESS_CACHE, DOWNLOAD_CACHE). Dış bağımlılık yok.
"""
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory cache with explicit TTL cleanup.

    All operations are guarded by an RLock so async event-loop callers and
    threadpool background tasks (BackgroundTasks, run_in_executor) can
    share state without races. Single-process only — not shared across
    uvicorn workers.
    """

    def __init__(self, ttl_seconds: int):
        self._store: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds

    def set(self, key: str, value: dict) -> None:
        entry = dict(value)
        entry["_ts"] = time.time()
        with self._lock:
            self._store[key] = entry

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(key)
            return dict(entry) if entry else None

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                return default
            return entry

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def touch(self, key: str) -> bool:
        """Reset the entry's TTL clock without changing its value.

        Returns False if the key is absent (already expired/evicted) —
        callers surface this so the user can re-upload the document.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            entry["_ts"] = time.time()
            return True

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def cleanup_stale(self, on_evict: Optional[Callable[[str, dict], None]] = None) -> int:
        cutoff = time.time() - self._ttl
        with self._lock:
            stale = [k for k, v in self._store.items() if v.get("_ts", 0) < cutoff]
            evicted = [(k, self._store.pop(k)) for k in stale]
        if on_evict:
            for k, v in evicted:
                try:
                    on_evict(k, v)
                except Exception:
                    pass
        return len(evicted)


class DiskTTLCache:
    """Disk destekli TTL cache — süreçler ARASI paylaşım + restart kalıcılığı (Faz 3-E, plan 3.7).

    TTLCache ile aynı arayüzü sunar; PROCESS_CACHE/DOWNLOAD_CACHE bunun
    üzerinden uvicorn --workers N'de worker'lar arasında ve restart'lar
    boyunca tutarlı kalır. Tasarım kararları:

    * BELLEKTE STATE YOK ("diskten lazy okuma" kararı): her girdi
      <dir>/<key>.json meta dosyasıdır, her işlem diski okur. İşlem hacmi
      kullanıcı-eylemi mertebesinde (dakikada onlarca) ve meta dosyaları
      birkaç yüz bayt — süreç içi indeks + sidecar senkronunun bayatlama
      problemleri (worker A evict etti, worker B hâlâ biliyor) hiç doğmaz.
    * TTL SAATİ = DOSYA MTIME'I: touch() = os.utime — içerik yeniden
      yazılmaz, damga restart'ta da kalıcıdır. TTLCache gibi süre dolumu
      YALNIZ cleanup_stale'de işlenir (get "süresi geçmiş ama henüz
      süpürülmemiş" girdiyi yine döndürür — davranış birebir korunur).
    * pop() SÜREÇLER ARASI ATOMİK: meta dosyası önce rastgele adlı bir
      claim dosyasına os.replace/rename ile taşınır — yarışan iki pop'tan
      yalnız biri kazanır, kaybeden default alır. /confirm'in çifte tüketimi
      esasen confirm_receipts kapısıyla engellidir; bu atomiklik kapının
      bypass (DB arızası) moduna düştüğü anların emniyet kemeridir.
    * adopt_file_fields: set() bu alanlardaki dosyaları cache dizinine
      TAŞIR (shutil.move) — sistem temp'inde doğan payload'lar (analiz
      PDF'i, dönüştürülmüş orijinal) backend-data volume'üne geçer; restart
      ve worker sınırını payload da atlatır. Taşıma başarısızsa özgün yol
      korunur: aynı konteynerdeki worker'lar /tmp'yi zaten paylaştığından
      davranış bugünden kötü olmaz, yalnız restart kalıcılığı kaybedilir.

    Süreç içi kilit yok (bilinçli): her işlem tekil bir atomik FS çağrısına
    (os.replace / utime / unlink) dayanır; anahtarlarımız istek başına tekil
    UUID'lerdir, aynı anahtara eşzamanlı set pratikte yoktur.
    """

    # Bozuk/yarım kalan artıkların süpürme eşiği çarpanı: canlı bir pop'un
    # claim dosyası milisaniyeler yaşar; TTL'den eski claim = pop ortasında
    # ölen süreç. Meta'sız payload (adopt sonrası meta yazılamadı) 2×TTL'de
    # süpürülür — yaşayan hiçbir girdiyle yarışmaz.
    _ORPHAN_TTL_FACTOR = 2

    def __init__(self, base_dir: Path, ttl_seconds: int,
                 adopt_file_fields: tuple = ()) -> None:
        self._dir = Path(base_dir)
        self._ttl = ttl_seconds
        self._adopt_fields = tuple(adopt_file_fields)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── yol yardımcıları ────────────────────────────────────────────────────

    @staticmethod
    def _safe_key(key: str) -> str:
        """Anahtar dosya adına iner — path traversal'a kapalı."""
        return re.sub(r"[^A-Za-z0-9._-]", "_", str(key))

    def _meta_path(self, key: str) -> Path:
        return self._dir / f"{self._safe_key(key)}.json"

    @staticmethod
    def _key_from_meta(meta: Path) -> str:
        return meta.name[: -len(".json")]

    # ── payload sahiplenme (set) ────────────────────────────────────────────

    def _adopt_files(self, key: str, entry: dict) -> None:
        for field in self._adopt_fields:
            src = entry.get(field)
            if not src or not os.path.isfile(src):
                continue
            src_path = Path(src)
            if src_path.parent == self._dir:
                continue  # zaten cache dizininde (ör. re-set)
            suffix = src_path.suffix.lower()
            dest = self._dir / f"{self._safe_key(key)}.{field}-{uuid.uuid4().hex[:8]}{suffix}"
            try:
                shutil.move(str(src_path), str(dest))
                entry[field] = str(dest)
            except OSError as e:
                # Taşınamadı → özgün yol korunur (docstring: bugünden kötü değil)
                logger.warning(
                    f"DiskTTLCache payload taşınamadı ({key}.{field}): {e} — özgün yol korunuyor"
                )

    # ── temel işlemler ──────────────────────────────────────────────────────

    def set(self, key: str, value: dict) -> None:
        entry = dict(value)
        self._adopt_files(key, entry)
        meta = self._meta_path(key)
        tmp = meta.with_name(f"{meta.name}.tmp-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, meta)  # atomik: yarım meta asla görünmez
        except OSError as e:
            logger.warning(f"DiskTTLCache set yazılamadı ({key}): {e}")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def get(self, key: str) -> Optional[dict]:
        try:
            raw = self._meta_path(key).read_text(encoding="utf-8")
            entry = json.loads(raw)
            return entry if isinstance(entry, dict) else None
        except (OSError, ValueError):
            # Yok / okunamadı / bozuk → miss; bozuk dosyayı cleanup süpürür
            return None

    def _claim_and_read(self, meta: Path) -> Optional[dict]:
        """Meta dosyasını atomik olarak sahiplenip içeriğini döndürür.

        Kaybeden yarışçı (dosya çoktan taşınmış) None alır. Sahiplenilen ama
        çözümlenemeyen dosya silinir ve None döner (payload'ları orphan
        süpürmesi toplar).

        Claim adı OLUŞTURULMA zamanını taşır (".claim-<epoch>-<rasgele>"):
        rename mtime'ı MİRAS bırakır — süresi dolmuş bir girdinin canlı
        eviction claim'i eski mtime'la "bayat claim" gibi görünür ve eşzamanlı
        ikinci süpürücü aynı girdiyi İKİNCİ kez evict ederdi (testte yakalanan
        yarış). Zaman adın içinde atomik gittiğinden pencere hiç doğmaz.
        """
        claim = meta.with_name(
            f"{meta.name[:-len('.json')]}.claim-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        )
        try:
            os.replace(meta, claim)
        except OSError:
            return None
        try:
            entry = json.loads(claim.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entry = None
        try:
            claim.unlink()
        except OSError:
            pass
        return entry if isinstance(entry, dict) else None

    def pop(self, key: str, default: Any = None) -> Any:
        entry = self._claim_and_read(self._meta_path(key))
        return entry if entry is not None else default

    def delete(self, key: str) -> bool:
        """Yalnız meta girdisini düşürür (TTLCache.delete ile aynı sözleşme:
        payload dosyalarının yaşam döngüsü çağıranındır)."""
        try:
            self._meta_path(key).unlink()
            return True
        except OSError:
            return False

    def touch(self, key: str) -> bool:
        try:
            os.utime(self._meta_path(key))
            return True
        except OSError:
            return False

    def __contains__(self, key: str) -> bool:
        return self._meta_path(key).exists()

    # ── süpürme ─────────────────────────────────────────────────────────────

    def cleanup_stale(self, on_evict: Optional[Callable[[str, dict], None]] = None) -> int:
        """TTL'i dolan girdileri (ve yarım kalmış artıkları) süpürür.

        Süreçler arası güvenli: eviction claim-atomiktir, iki worker aynı
        girdiyi aynı anda süpüremez. Boot'ta da çağrılır (api.py lifespan) —
        "TTL indeksini yeniden kur" adımı budur: indeks diskin kendisi
        olduğundan kurulacak şey yalnız bayatların temizliğidir.
        """
        now = time.time()
        cutoff = now - self._ttl
        orphan_cutoff = now - self._ttl * self._ORPHAN_TTL_FACTOR
        evicted = 0

        for meta in sorted(self._dir.glob("*.json")):
            try:
                if meta.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue  # yarıştaki başka worker aldı
            entry = self._claim_and_read(meta)
            if entry is None:
                continue
            evicted += 1
            if on_evict:
                try:
                    on_evict(self._key_from_meta(meta), entry)
                except Exception:
                    pass

        # Pop/evict ortasında ölen sürecin claim dosyaları: içerik
        # okunabiliyorsa eviction gibi işlenir (payload'lar on_evict'le
        # silinir), sonra düşer. Yaş, addaki claim zamanından okunur
        # (_claim_and_read docstring'i); ad çözülemezse mtime'a düşülür.
        for claim in sorted(self._dir.glob("*.claim-*")):
            try:
                claim_ts: float
                try:
                    claim_ts = float(claim.name.rsplit(".claim-", 1)[1].split("-")[0])
                except (IndexError, ValueError):
                    claim_ts = claim.stat().st_mtime
                if claim_ts >= cutoff:
                    continue
                entry = json.loads(claim.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                entry = None
            if isinstance(entry, dict) and on_evict:
                try:
                    on_evict(claim.name.split(".claim-")[0], entry)
                except Exception:
                    pass
            try:
                claim.unlink()
            except OSError:
                pass

        # Meta'sız kalan payload'lar (set yazamadı / bozuk meta silindi) ve
        # yarım .tmp- dosyaları: *.json ve *.claim-* dışındaki her dosya
        # 2×TTL'den eskiyse süpürülür.
        for stray in sorted(self._dir.iterdir()):
            name = stray.name
            if name.endswith(".json") or ".claim-" in name:
                continue
            try:
                if not stray.is_file() or stray.stat().st_mtime >= orphan_cutoff:
                    continue
                stray.unlink()
                logger.info(f"DiskTTLCache orphan payload süpürüldü: {name}")
            except OSError:
                continue

        return evicted
