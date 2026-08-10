"""Frontend hata beacon'ı (Faz 2-C): POST /api/client-error.

Tarayıcıda yakalanmayan hatalar (window 'error' + 'unhandledrejection',
bkz. frontend/src/lib/errorBeacon.ts) buraya POST edilir ve severity=ERROR
ile loglanır — GCP ERROR-oranı alarmı (log tabanlı metrik) bu satırları da
sayar; "ekran boş" şikayeti artık sunucudan görünür.

Tasarım sınırları:
- Auth YOK (bilinçli): auth altyapısı kırıkken de hata raporlanabilmeli.
  Karşılığında sıkı korumalar: IP başına hız limiti, küçük gövde tavanı,
  alan beyaz listesi + uzunluk kırpma (log şişirme/injection koruması).
- Content-Type kontrolü yok: sendBeacon düz string gönderir (text/plain) —
  application/json isteseydik CORS preflight gerekirdi; gövde ham okunur.
- Yanıt 204: sendBeacon yanıt gövdesini okuyamaz, içerik anlamsız.
"""
import json
import logging

from fastapi import APIRouter, Request, Response

from rate_limiting import _rate_limit_key, limiter

router = APIRouter()

logger = logging.getLogger("client_error")

# sendBeacon tipik gövdesi <2 KB; 16 KB her meşru raporu fazlasıyla kapsar.
MAX_BODY_BYTES = 16 * 1024

# Beyaz liste: alan adı → azami uzunluk. Listede olmayan her alan sessizce
# düşer (istemci sürüm kayması 422 üretmesin); değerler string'e çevrilip
# kırpılır. line/col ayrıca int'e zorlanır.
_STR_FIELDS = {"kind": 32, "message": 2000, "stack": 8000, "url": 1000}
_INT_FIELDS = ("line", "col")
_KIND_ALLOWED = frozenset({"error", "unhandledrejection"})


def _sanitize(data: dict) -> dict:
    report = {}
    for field, max_len in _STR_FIELDS.items():
        value = data.get(field)
        if value is not None:
            report[field] = str(value)[:max_len]
    for field in _INT_FIELDS:
        value = data.get(field)
        if value is not None:
            try:
                report[field] = int(value)
            except (TypeError, ValueError):
                pass
    if report.get("kind") not in _KIND_ALLOWED:
        report["kind"] = "unknown"
    return report


@router.post("/api/client-error", status_code=204)
@limiter.limit("10/minute")
async def report_client_error(request: Request):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        return Response(status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(status_code=413)

    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return Response(status_code=400)
    if not isinstance(data, dict):
        return Response(status_code=400)

    report = _sanitize(data)
    # Başlık satırı kısa tutulur (mesajın tamamı extra'da) — JSON formatter
    # extra alanları geçirir (logging_setup._STANDARD_ATTRS dışındakiler);
    # anahtarlar LogRecord'un rezerve adlarıyla çakışmasın diye client_ önekli.
    logger.error(
        f"CLIENT {report.get('kind', 'unknown')}: {report.get('message', '')[:200]}",
        extra={
            "event": "client_error",
            "client_kind": report.get("kind"),
            "client_message": report.get("message"),
            "client_stack": report.get("stack"),
            "client_url": report.get("url"),
            "client_line": report.get("line"),
            "client_col": report.get("col"),
            "client_ip": _rate_limit_key(request),
            "client_user_agent": (request.headers.get("user-agent") or "")[:300],
        },
    )
    return Response(status_code=204)
