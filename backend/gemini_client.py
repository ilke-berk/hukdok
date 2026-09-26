"""Ortak Gemini client modülü (google-genai SDK).

Eski SDK'daki genai.configure(...) global durumunun yerini alır: tüm modüller
Client örneğini buradan alır (analyzer, email_sender, date_extractor).

Client anahtar değişmediği sürece bir kez kurulur; anahtar rotasyonunda
(env yeniden yüklenip farklı anahtar geldiğinde) yeni Client üretilir.
Client kurulumu ağ çağrısı yapmaz.

Faz 3-C: Gemini'ye giden çağrıların API-seviyesi politikası da burada yaşar —
retry sınıflandırması (kod bazlı, string eşleme yok) ve model-başına devre
kesici. SDK'nın kendi retry'ı (HttpOptions.retry_options) bilinçli KAPALI
bırakılır: verilmediğinde SDK "never retry" kullanır, retry politikasının tek
sahibi bizim katmandır (çifte-retry çarpanı olmaz).
"""
import logging
import threading
import time
from typing import Optional

import httpx  # google-genai'nin zorunlu transport bağımlılığı (requirements'a
# ayrıca yazılmadı — 3-B'deki urllib3/requests kararıyla aynı gerekçe)
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from config.settings import settings

# Hiçbir Gemini çağrısı sonsuza dek asılmamalı: SDK'da varsayılan timeout yok,
# takılı bir istek /process akışını süresiz bloke ediyordu. Milisaniye cinsinden.
# Faz 5-A: evi config/settings.py (env: GEMINI_HTTP_TIMEOUT_MS); alias korunur —
# 3-C bütçe aritmetiği (170 + 120 = 290 < 300) bekçi testiyle kilitli.
GEMINI_HTTP_TIMEOUT_MS = settings.gemini_http_timeout_ms

_client: Optional[genai.Client] = None
_client_key: Optional[str] = None
_lock = threading.Lock()


def get_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Paylaşılan google-genai Client'ını döndürür.

    api_key verilmezse vault üzerinden GEMINI_API_KEY okunur.
    Anahtar bulunamazsa None döner; çağıran taraf loglayıp akışı keser.
    """
    global _client, _client_key

    if api_key is None:
        import vault

        api_key = vault.get_secret("GEMINI_API_KEY")
    if not api_key:
        return None

    with _lock:
        if _client is None or _client_key != api_key:
            _client = genai.Client(
                api_key=api_key,
                http_options=genai_types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS),
            )
            _client_key = api_key
        return _client


# ============================================================================
# Retry sınıflandırması (Faz 3-C) — KOD bazlı, string eşleme yok
# ============================================================================
# SDK hiyerarşisi (google-genai 2.11.0, koddan doğrulandı): APIError.code her
# zaman int dolu; 4xx → ClientError, 5xx → ServerError (ikisi de APIError altı).
# httpx transport hataları (TimeoutException, ConnectError, RemoteProtocolError
# — hepsi TransportError altında) SDK'dan sarmalanmadan geçer.
RETRYABLE_API_CODES = frozenset({429, 500, 502, 503, 504})
# Devre kesiciyi yalnız doygunluk sinyalleri besler: 429 (kota/rate-limit) ve
# 503 (overloaded). 500/502/504 ve ağ hataları retry edilir ama kesici saymaz.
SATURATION_API_CODES = frozenset({429, 503})


def classify_transient(exc: BaseException) -> Optional[str]:
    """Hatanın geçici (retry'a değer) olup olmadığını KOD bazlı sınıflandırır.

    Dönüş: "429" (kota — uzun backoff), "server" (500/502/503/504 — kısa
    backoff), "transport" (httpx ağ/timeout — kısa backoff) ya da None (kalıcı).
    """
    if isinstance(exc, genai_errors.APIError) and exc.code in RETRYABLE_API_CODES:
        return "429" if exc.code == 429 else "server"
    if isinstance(exc, httpx.TransportError):
        return "transport"
    return None


# ============================================================================
# Devre kesici (Faz 3-C) — model-başına, art arda 429/503 → 60 sn açık
# ============================================================================
# Model-başına tutulur çünkü Gemini'de rate-limit/overload model bazlıdır:
# tek global kesici, intake modelinin (GEMINI_INTAKE_MODEL) fırtınasında ana
# analiz modelini de keserdi (yanlış pozitif) — tersi de geçerli.
#
# Bilinçli sınır: state süreç içidir (uvicorn şu an tek worker). Faz 3-E'de
# --workers 2'ye geçilince her worker kendi kesicisini işletir — koruma amaçlı
# sinyal için yeterli; health.py'nin süreç-içi sayaçlarıyla aynı gerekçe.
#
# Yarı-açık davranış: açık süre dolunca çağrılara yeniden izin verilir ama
# sayaç sıfırlanmaz — ilk 429/503 kesiciyi ANINDA yeniden açar; ancak başarılı
# bir çağrı sayacı sıfırlayıp kesiciyi tam kapatır.
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_OPEN_SECONDS = 60.0

_circuit_lock = threading.Lock()
# model -> {"consecutive": int, "open_until": float (monotonic)}
_circuit_state: dict = {}


class GeminiCircuitOpenError(Exception):
    """Devre kesici açıkken yapılan çağrının hızlı-fail hatası.

    Çağrı Gemini'ye hiç gitmemiştir; kullanıcıya "kısa süre sonra tekrar
    deneyin" mesajı düşer (analyzer._api_error_ozet bu tipi tanır).
    """

    def __init__(self, model: str, remaining_seconds: float):
        self.model = model
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Gemini devre kesici açık (model={model}, {remaining_seconds:.0f} sn kaldı)"
        )


def _monotonic() -> float:
    """time.monotonic dolaylaması — testler saati buradan kontrol eder."""
    return time.monotonic()


def circuit_open_remaining(model: str) -> float:
    """Kesici açıksa kalan saniyeyi, kapalıysa 0.0 döndürür."""
    with _circuit_lock:
        state = _circuit_state.get(model)
        if state is None:
            return 0.0
        return max(0.0, state["open_until"] - _monotonic())


def circuit_record_failure(model: str) -> bool:
    """Bir 429/503 gözlemini işler; kesici bu olayla AÇILDIYSA True döndürür.

    Çağıran yalnız SATURATION_API_CODES'taki hatalarda çağırmalı; eşiğe
    ulaşan her yeni hata açık pencereyi ileri taşır (kanıt biriktikçe uzar).
    Açılış olayı burada TEK noktadan WARNING loglanır (log sözleşmesi:
    nihai ERROR'ları çağıranların handler'ları üretir).
    """
    with _circuit_lock:
        state = _circuit_state.setdefault(model, {"consecutive": 0, "open_until": 0.0})
        state["consecutive"] += 1
        opened = False
        if state["consecutive"] >= CIRCUIT_FAILURE_THRESHOLD:
            opened = state["open_until"] <= _monotonic()
            state["open_until"] = _monotonic() + CIRCUIT_OPEN_SECONDS
    if opened:
        logging.getLogger(__name__).warning(
            f"⛔ Gemini devre kesici AÇILDI (model={model}, art arda "
            f"{CIRCUIT_FAILURE_THRESHOLD}+ doygunluk hatası, {CIRCUIT_OPEN_SECONDS:.0f} sn)"
        )
    return opened


def circuit_record_success(model: str) -> None:
    """Başarılı çağrı: sayaç sıfırlanır, kesici tam kapanır."""
    with _circuit_lock:
        state = _circuit_state.get(model)
        if state is not None:
            state["consecutive"] = 0
            state["open_until"] = 0.0


def reset_circuits_for_tests() -> None:
    with _circuit_lock:
        _circuit_state.clear()


# ============================================================================
# Sesli giriş transkripsiyonu (G216) — POST /api/transcribe'ın Gemini ayağı
# ============================================================================
# Kullanıcı kaydı bitirip bekler: analiz hattının 170 sn bütçesi burada anlamsız.
# Az deneme + kısa bütçe; bütçe "yeni bekleme/deneme BAŞLATMA" kapısıdır (3-C deseni),
# son deneme HTTP timeout'una (GEMINI_HTTP_TIMEOUT_MS) kadar sürebilir.
TRANSCRIBE_MAX_RETRIES = 2
TRANSCRIBE_RETRY_DEADLINE_SECONDS = 20.0

TRANSCRIBE_PROMPT = (
    "Türkçe konuşmayı birebir yazıya dök; hukuki terim, kurum ve kişi adlarını olduğu "
    "gibi yaz; noktalama ekle; yorum, özet, açıklama ekleme; yalnız metni döndür. "
    "Kayıtta konuşma yoksa boş yanıt döndür."
)


class GeminiUnavailableError(Exception):
    """Gemini istemcisi kurulamadı (anahtar yok) — çağrı yapılamaz."""


async def _transcribe_sleep(seconds: float) -> None:
    """asyncio.sleep dolaylaması — testler beklemeyi buradan sıfırlar."""
    import asyncio

    await asyncio.sleep(seconds)


async def transcribe_audio(audio: bytes, mime_type: str, model: str) -> str:
    """Ses baytlarını Gemini ile Türkçe metne döker; strip'li metni döndürür.

    Politika ortak katmanla aynıdır: `classify_transient` ile geçici hatalar
    jitter'lı backoff'la yeniden denenir (her deneme WARNING — İÇERİK loglanmaz),
    429/503 model-başına devre kesiciyi besler, kesici açıksa çağrı hiç yapılmadan
    `GeminiCircuitOpenError`. Nihai hata ÇAĞIRANA fırlatılır; tek ERROR'u ve
    health kaydını çağıran üretir (log sözleşmesi).

    Ses yalnız bellekte tutulur: `Part.from_bytes` inline veri gönderir (Files API'ye
    yükleme yok, diske yazma yok).
    """
    import random

    remaining_open = circuit_open_remaining(model)
    if remaining_open > 0:
        raise GeminiCircuitOpenError(model, remaining_open)

    client = get_client()
    if client is None:
        raise GeminiUnavailableError("GEMINI_API_KEY bulunamadı")

    log = logging.getLogger(__name__)
    contents = [
        TRANSCRIBE_PROMPT,
        genai_types.Part.from_bytes(data=audio, mime_type=mime_type),
    ]
    config = genai_types.GenerateContentConfig(temperature=0.0)
    deadline = _monotonic() + TRANSCRIBE_RETRY_DEADLINE_SECONDS
    attempt = 0
    while True:
        try:
            response = await client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:
            kind = classify_transient(e)
            if kind is None:
                raise
            api_code = e.code if isinstance(e, genai_errors.APIError) else None
            if api_code in SATURATION_API_CODES:
                circuit_record_failure(model)
            if attempt >= TRANSCRIBE_MAX_RETRIES:
                raise
            base = 5.0 if kind == "429" else 1.0
            wait_sec = min(base * (2 ** attempt) + random.uniform(0, base), 10.0)
            if _monotonic() + wait_sec > deadline:
                raise
            label = str(api_code) if api_code is not None else f"ağ/{e.__class__.__name__}"
            log.warning(
                f"⏳ Transkripsiyon: Gemini geçici hata ({label}) — {wait_sec:.1f}s sonra "
                f"tekrar denenecek (Deneme {attempt + 1}/{TRANSCRIBE_MAX_RETRIES})"
            )
            attempt += 1
            await _transcribe_sleep(wait_sec)
            continue
        circuit_record_success(model)
        return (response.text or "").strip()
