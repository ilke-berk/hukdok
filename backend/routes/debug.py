"""Bellek teşhis endpoint'i (yalnız admin).

2026-07-29 OOM incelemesi için eklendi. RSS ile Python heap'i (tracemalloc)
arasındaki büyük fark C-tarafı/malloc-arena büyümesini, buffer ve nesne
sayaçları Python tarafı birikimi gösterir.

tracemalloc maliyetli olduğu için varsayılan kapalıdır; iki ölçüm arasında
`?trace=start` ile açılıp `?trace=stop` ile kapatılır.
"""

import gc
import logging
import tracemalloc
from typing import Optional

from fastapi import APIRouter, Depends

from managers.log_manager import TechnicalLogger
from routes.config import require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

_PROC_FIELDS = ("VmRSS", "VmHWM", "VmSwap")


def _proc_status_kb() -> dict:
    values = {}
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                field = line.split(":", 1)[0]
                if field in _PROC_FIELDS:
                    values[field.lower() + "_kb"] = int(line.split()[1])
    except OSError:
        pass
    return values


def _cgroup_memory_kb() -> dict:
    values = {}
    try:
        with open("/sys/fs/cgroup/memory.stat", encoding="ascii") as f:
            for line in f:
                key, _, raw = line.partition(" ")
                if key in ("anon", "file"):
                    values[key + "_kb"] = int(raw) // 1024
    except OSError:
        pass
    return values


def _object_counts() -> dict:
    tracked = {}
    try:
        import fitz

        tracked["fitz.Document"] = fitz.Document
    except ImportError:
        pass
    try:
        from PIL import Image as PILImage

        tracked["PIL.Image"] = PILImage.Image
    except ImportError:
        pass

    counts = {name: 0 for name in tracked}
    for obj in gc.get_objects():
        for name, cls in tracked.items():
            if isinstance(obj, cls):
                counts[name] += 1
    counts["gc_garbage"] = len(gc.garbage)
    return counts


def _buffer_stats() -> dict:
    with TechnicalLogger._lock:
        entries = list(TechnicalLogger._buffer)
    approx_bytes = sum(len(e.get("message", "")) + len(str(e.get("details", ""))) for e in entries)
    return {
        "entries": len(entries),
        "max_entries": TechnicalLogger._MAX_BUFFER_ENTRIES,
        "approx_kb": approx_bytes // 1024,
    }


def _tracemalloc_report(top: int) -> Optional[dict]:
    if not tracemalloc.is_tracing():
        return None
    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")[:top]
    return {
        "current_kb": current // 1024,
        "peak_kb": peak // 1024,
        "top": [
            {
                "location": str(stat.traceback[0]) if stat.traceback else "?",
                "size_kb": stat.size // 1024,
                "count": stat.count,
            }
            for stat in stats
        ],
    }


@router.get("/api/admin/debug/memory")
async def api_debug_memory(
    trace: Optional[str] = None,
    top: int = 15,
    user: dict = Depends(require_admin),
):
    """Süreç/cgroup belleği, TechnicalLogger buffer'ı, nesne sayaçları ve
    (açıksa) tracemalloc özeti. `trace=start|stop` ile Python-heap izleme."""
    if trace == "start" and not tracemalloc.is_tracing():
        tracemalloc.start(10)
        logger.info("Debug: tracemalloc başlatıldı")

    result = {
        "process": _proc_status_kb(),
        "cgroup": _cgroup_memory_kb(),
        "technical_log_buffer": _buffer_stats(),
        "objects": _object_counts(),
        "tracemalloc": _tracemalloc_report(top),
    }

    try:
        import anyio.to_thread

        limiter = anyio.to_thread.current_default_thread_limiter()
        stats = limiter.statistics()
        result["threadpool"] = {
            "borrowed_tokens": limiter.borrowed_tokens,
            "total_tokens": limiter.total_tokens,
            "tasks_waiting": stats.tasks_waiting,
        }
    except Exception:
        result["threadpool"] = None

    if trace == "stop" and tracemalloc.is_tracing():
        tracemalloc.stop()
        logger.info("Debug: tracemalloc durduruldu")
        result["tracemalloc_stopped"] = True

    return result
