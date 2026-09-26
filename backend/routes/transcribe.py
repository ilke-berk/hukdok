"""Sesli giriş transkripsiyonu (G216) — `POST /api/transcribe`.

Hukukbot + Rapor asistanı sohbet kutularına "kulak": tarayıcı kaydeder, burada
Gemini Türkçe metne döker, metin kutuya düşer, kullanıcı düzeltip gönderir
(frontend G217). Ses Hukukbot'a GİTMEZ; tek dış çağrı mevcut Gemini hattıdır.

Sözleşme SABİT (G217 buna göre paralel yazıldı):

* `multipart/form-data`, tek alan `ses` (dosya); oturum zorunlu → yoksa 401
* tür (parametresiz, `;codecs=opus` atılır): `audio/webm | audio/ogg | audio/mp4 |
  audio/mpeg | audio/wav`, aksi 415
* boyut > 2 MB → 413; boş dosya (ya da `ses` alanı yok) → 422
* başarı 200 `{"metin": str}` — strip'li, konuşma yoksa ""
* Gemini meşgul / başarısız / devre açık → 503 `SERVIS_YOK_MESAJI`

Gizlilik: ses YALNIZ bellekte işlenir — diske, DB'ye, loga yazılmaz. Starlette'in
multipart ayrıştırıcısı dosya parçasını `spool_max_size` (1 MB) üstünde geçici
diske taşır; bu yüzden ayrıştırıcı spool tavanı gövde tavanının üstünde bir alt
sınıfla kurulur ve gövde akışı tavanda kesilir (tavan aşımı diske değil 413'e
gider). Ne ses ne transkript loglanır; log satırı yalnız boyut, tür, süre (ms)
ve sonuç taşır.

Hız koruması: repoda KULLANICI başına sınırlayıcı deseni yok; `rate_limiting.limiter`
IP anahtarlıdır ve `default_limits` (RATE_LIMIT_DEFAULT) SlowAPIMiddleware ile bu
uca da uygulanır. Yeni altyapı kurulmadı (görev kuralı).
"""
import logging
import os
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

import gemini_client
import health
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SES_BYTES = 2 * 1024 * 1024
# multipart zarfı (sınır satırları + parça başlıkları) için pay: gövde tavanı
# = ses tavanı + zarf. Ses baytının kendisi ayrıca MAX_SES_BYTES'a karşı ölçülür.
_ZARF_PAYI = 64 * 1024
_MAX_GOVDE_BYTES = MAX_SES_BYTES + _ZARF_PAYI

KABUL_EDILEN_TURLER = frozenset(
    {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
)

SERVIS_YOK_MESAJI = "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin."


class _BellekMultiPartParser(MultiPartParser):
    """Dosya parçasını diske TAŞIMAYAN ayrıştırıcı: spool tavanı gövde tavanının
    üstünde → SpooledTemporaryFile hiç rollover etmez (bellekte kalır)."""

    spool_max_size = _MAX_GOVDE_BYTES * 2


class _GovdeCokBuyuk(Exception):
    pass


def _tur_normalize(content_type: str | None) -> str:
    """`audio/webm;codecs=opus` → `audio/webm` (parametreler atılır, küçük harf)."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def _model_adi() -> str:
    # Ana analiz modeliyle AYNI config (email_sender / date_extractor deseni).
    return os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")


async def _tavanli_akis(request: Request) -> AsyncGenerator[bytes, None]:
    toplam = 0
    async for parca in request.stream():
        toplam += len(parca)
        if toplam > _MAX_GOVDE_BYTES:
            raise _GovdeCokBuyuk()
        yield parca


async def _ses_dosyasini_oku(request: Request) -> UploadFile:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_GOVDE_BYTES:
        raise HTTPException(status_code=413, detail="Ses kaydı 2 MB sınırını aşıyor.")
    if _tur_normalize(request.headers.get("content-type")) != "multipart/form-data":
        raise HTTPException(status_code=422, detail="multipart/form-data bekleniyor.")
    parser = _BellekMultiPartParser(
        request.headers, _tavanli_akis(request), max_files=1, max_fields=0
    )
    try:
        form = await parser.parse()
    except _GovdeCokBuyuk:
        raise HTTPException(status_code=413, detail="Ses kaydı 2 MB sınırını aşıyor.") from None
    except MultiPartException:
        raise HTTPException(status_code=422, detail="Form verisi okunamadı.") from None
    ses = form.get("ses")
    if not isinstance(ses, UploadFile):
        raise HTTPException(status_code=422, detail="'ses' dosya alanı eksik.")
    return ses


@router.post("/api/transcribe")
async def transcribe(request: Request, user: dict = Depends(get_current_user)):
    ses = await _ses_dosyasini_oku(request)
    tur = _tur_normalize(ses.content_type)
    if tur not in KABUL_EDILEN_TURLER:
        raise HTTPException(status_code=415, detail="Desteklenmeyen ses türü.")

    veri = await ses.read()
    await ses.close()
    boyut = len(veri)
    if boyut > MAX_SES_BYTES:
        raise HTTPException(status_code=413, detail="Ses kaydı 2 MB sınırını aşıyor.")
    if boyut == 0:
        raise HTTPException(status_code=422, detail="Ses kaydı boş.")

    baslangic = time.monotonic()
    try:
        metin = await gemini_client.transcribe_audio(veri, tur, _model_adi())
    except Exception as e:
        sure_ms = int((time.monotonic() - baslangic) * 1000)
        health.record_gemini_error()
        # Nihai başarısızlık — TEK ERROR. İstisna METNİ bilinçli yazılmaz (içerik
        # sızmasın); yalnız tip + API kodu.
        kod = getattr(e, "code", None)
        logger.error(
            "Transkripsiyon başarısız: boyut=%d tur=%s sure_ms=%d sonuc=hata hata=%s kod=%s",
            boyut, tur, sure_ms, e.__class__.__name__, kod,
        )
        raise HTTPException(status_code=503, detail=SERVIS_YOK_MESAJI) from None

    sure_ms = int((time.monotonic() - baslangic) * 1000)
    logger.info(
        "Transkripsiyon: boyut=%d tur=%s sure_ms=%d sonuc=%s",
        boyut, tur, sure_ms, "ok" if metin else "bos",
    )
    return {"metin": metin}
