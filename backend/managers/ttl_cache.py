import threading
import time
from typing import Any, Callable, Optional


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
