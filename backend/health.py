"""Süreç içi sağlık sinyalleri — derin /healthz'in veri kaynağı (Faz 2-A).

Modüller olay anında ucuz birer damga bırakır (record_*), /healthz bunları
okur. Buradaki hiçbir fonksiyon ağ/DB çağrısı yapmaz; tek canlı kontrol olan
DB SELECT 1, api.py'deki endpoint'te TTL cache arkasında koşar.

Bilinçli sınır: sayaçlar süreç içidir. uvicorn --workers N geçişinde (Faz 3-E)
her worker kendi penceresini raporlar — görünürlük sinyali için yeterli;
merkezileştirme gerekirse o fazda ele alınır.

Import zinciri stdlib ile sınırlı tutuldu: auth_graph (konteyner script'leri
dahil her yerden import edilir) bu modülü çeker; database gibi env isteyen
modüllere bağlanmak scriptleri kırardı.
"""
import threading
import time
from collections import deque
from typing import Optional

# "Son Gemini hata sayısı" bu pencerede sayılır (plan Faz 2.1)
GEMINI_ERROR_WINDOW_SECONDS = 3600.0
# Pencereden bağımsız bellek tavanı: hata fırtınasında deque büyümesin
_MAX_EVENTS = 500

_lock = threading.Lock()
_graph_token_ok_at: Optional[float] = None
_graph_token_fail_at: Optional[float] = None
_gemini_error_times: deque = deque(maxlen=_MAX_EVENTS)


def record_graph_token_ok() -> None:
    """auth_graph başarılı token aldığında damgalar (cache'ten dönüş dahil)."""
    global _graph_token_ok_at
    with _lock:
        _graph_token_ok_at = time.time()


def record_graph_token_fail() -> None:
    """auth_graph retry sonrası da token alamadıysa damgalar."""
    global _graph_token_fail_at
    with _lock:
        _graph_token_fail_at = time.time()


def record_gemini_error() -> None:
    """Nihai Gemini başarısızlığında çağrılır — geçici 429/503 retry'ları
    sayılmaz (onlar akışı bozmadan atlatılıyor), yalnız kullanıcıya/akışa
    yansıyan son durum hataları sayılır."""
    with _lock:
        _gemini_error_times.append(time.time())


def reset_for_tests() -> None:
    global _graph_token_ok_at, _graph_token_fail_at
    with _lock:
        _graph_token_ok_at = None
        _graph_token_fail_at = None
        _gemini_error_times.clear()


def _age(now: float, at: Optional[float]) -> Optional[int]:
    return int(now - at) if at is not None else None


def signals_snapshot(now: Optional[float] = None) -> dict:
    """Kilit altında okunan özet; /healthz 'checks' alanına girer."""
    if now is None:
        now = time.time()
    with _lock:
        return {
            "graph_token_age_seconds": _age(now, _graph_token_ok_at),
            "graph_token_last_fail_age_seconds": _age(now, _graph_token_fail_at),
            "gemini_errors_last_hour": sum(
                1 for t in _gemini_error_times if now - t <= GEMINI_ERROR_WINDOW_SECONDS
            ),
        }


def evaluate(db_ok: bool, version: str, now: Optional[float] = None) -> "tuple[dict, int]":
    """(payload, http_status) üretir — saf ve deterministik, testler doğrudan çağırır.

    Durum kuralları:
    - DB fail → "unhealthy" + 503: docker healthcheck, deploy kapısı ve GCP
      uptime check'in alarm koşulu. Çekirdek bağımlılık olmadan servis yok.
    - DB ok ama son 1 saatte Gemini hatası var YA DA son Graph token denemesi
      başarısızlıkla bittiyse → "degraded" + 200: görünürlük amaçlı, restart
      veya uptime alarmı tetiklemez (log tabanlı alarmlar Faz 2-C'nin işi).
    - Aksi halde "ok" + 200.

    "version" kök seviyede kalmalı: deploy.sh sağlık kapısı bu alanı beklenen
    git SHA ile karşılaştırıyor (Faz 1-C).
    """
    signals = signals_snapshot(now=now)
    with _lock:
        # Sıralama ham timestamp'lerle: snapshot'taki yaşlar int'e kesilir,
        # aynı saniye içindeki ok→fail sırası orada ayırt edilemez.
        graph_ok_at, graph_fail_at = _graph_token_ok_at, _graph_token_fail_at

    if not db_ok:
        status, code = "unhealthy", 503
    else:
        last_graph_attempt_failed = graph_fail_at is not None and (
            graph_ok_at is None or graph_fail_at > graph_ok_at
        )
        degraded = signals["gemini_errors_last_hour"] > 0 or last_graph_attempt_failed
        status, code = ("degraded", 200) if degraded else ("ok", 200)

    payload = {
        "status": status,
        "version": version,
        "checks": {"db": "ok" if db_ok else "fail", **signals},
    }
    return payload, code
