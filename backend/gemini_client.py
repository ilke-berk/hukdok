"""Ortak Gemini client modülü (google-genai SDK).

Eski SDK'daki genai.configure(...) global durumunun yerini alır: tüm modüller
Client örneğini buradan alır (analyzer, email_sender, date_extractor).

Client anahtar değişmediği sürece bir kez kurulur; anahtar rotasyonunda
(env yeniden yüklenip farklı anahtar geldiğinde) yeni Client üretilir.
Client kurulumu ağ çağrısı yapmaz.
"""
import threading
from typing import Optional

from google import genai
from google.genai import types as genai_types

# Hiçbir Gemini çağrısı sonsuza dek asılmamalı: SDK'da varsayılan timeout yok,
# takılı bir istek /process akışını süresiz bloke ediyordu. Milisaniye cinsinden.
GEMINI_HTTP_TIMEOUT_MS = 120_000

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
