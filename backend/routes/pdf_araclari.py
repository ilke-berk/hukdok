"""PDF araçları uçları (G268, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §3 ilk üç uç).

`POST /api/pdf-araclari/yukle` · `POST /api/pdf-araclari/islem` · `GET /api/pdf-araclari/onizleme/{id}/{sayfa}`.
İndirme mevcut `GET /api/download/{id}` ucundan (routes/processing) — değişmedi.

Çalışma dosyası = `DOWNLOAD_CACHE` kaydı (K2): `{"path","filename","owner","kaynak":"pdf_araclari","sayfa","sayfalar"}`;
dosya `PDF_ARACLARI_DIR` (varsayılan `<backend>/data/pdf_araclari`, konteynerde backend-data volume'ü) altında
`<uuid>.pdf`. TTL dolunca `processing._download_evict` payload'ı da siler (yalnız bu kaynak). Sahiplik: başkasının id'si
her uçta 404 (varlık maskelenir). Ağır iş `pdf.pdf_araclari` çekirdeğinde, `run_in_threadpool` + `_pdf_arac_semaphore`
(2; dolu → 503) + `deadline` (K8 bütçesi; dolunca 504). nginx'e dokunulmaz (K10): her yol `/api/` altında.

Hata eşlemesi: `ParametreHatasi`/`PdfArcHatasi` → 422, `SayfaSinirAsildi` → 413, `AracYok` → 503, `ZamanAsimi` → 504,
`ConversionBusyError` → 503. Log sözleşmesi: 4xx WARNING, 5xx TEK ERROR (`error_kod`).
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from config.settings import settings
from dependencies import get_current_user
from file_utils import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, sanitize_filename, validate_file_type
from managers.log_manager import TechnicalLogger
from pdf import pdf_araclari as cekirdek
from pdf.format_converter import ConversionBusyError, acquire_conversion_slot
from rate_limiting import limiter
from routes.processing import DOWNLOAD_CACHE, _cache_dir, _cleanup_process_cache, _owner_id

router = APIRouter(prefix="/api/pdf-araclari")
logger = logging.getLogger(__name__)

KAYNAK = "pdf_araclari"
HIZ_SINIRI = "30/minute"
# İşlem semaforu (K8): aynı anda en çok 2 PDF işlemi; bekleme `conversion_acquire_timeout_seconds` ile tavanlı.
_pdf_arac_semaphore = threading.Semaphore(2)

ISLEMLER = ("birlestir", "bol", "sayfa_duzenle", "sikistir", "karart", "damga", "not", "donustur")
BULUNAMADI = "Dosya bulunamadı veya süresi doldu."


def _pdf_araclari_dir() -> Path:
    """Çağrı anında çözülür (test env'i monkeypatch'leyebilsin); volume altı."""
    d = _cache_dir("PDF_ARACLARI_DIR", "pdf_araclari")
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Pydantic modelleri (işlem başına ayrı, extra="forbid") ───────────────────

class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BirlestirParametreleri(_StrictModel):
    pass


class DonusturParametreleri(_StrictModel):
    pass


class BolParametreleri(_StrictModel):
    araliklar: Optional[list[list[int]]] = None
    her_n: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _tam_biri(self) -> "BolParametreleri":
        if (self.araliklar is None) == (self.her_n is None):
            raise ValueError("araliklar ya da her_n'den tam biri verilmeli")
        if self.araliklar is not None and (not self.araliklar or any(len(a) != 2 for a in self.araliklar)):
            raise ValueError("araliklar [[bas, bit], ...] biçiminde, boş olmayan liste olmalı")
        return self


class SayfaKaydi(_StrictModel):
    no: int = Field(ge=1)
    dondur: Literal[0, 90, 180, 270] = 0


class SayfaDuzenleParametreleri(_StrictModel):
    sayfalar: list[SayfaKaydi] = Field(min_length=1)


class SikistirParametreleri(_StrictModel):
    seviye: Literal["ekran", "ebook", "yazici"]


class KarartmaAlani(_StrictModel):
    sayfa: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float


class KarartParametreleri(_StrictModel):
    alanlar: list[KarartmaAlani] = Field(min_length=1)


class DamgaParametreleri(_StrictModel):
    metin: str = Field(min_length=1, max_length=cekirdek.DAMGA_MAX_KARAKTER)
    konum: Literal["sag-ust", "sol-ust", "sag-alt", "sol-alt", "orta"]
    sayfalar: Union[Literal["hepsi"], list[int]] = "hepsi"
    punto: float = Field(default=12, ge=4, le=144)
    renk: str = Field(default="#b00020", pattern=r"^#[0-9a-fA-F]{6}$")


class NotParametreleri(_StrictModel):
    sayfa: int = Field(ge=1)
    x: float
    y: float
    metin: str = Field(min_length=1, max_length=cekirdek.NOT_MAX_KARAKTER)


PARAMETRE_MODELLERI: dict[str, type[_StrictModel]] = {
    "birlestir": BirlestirParametreleri,
    "bol": BolParametreleri,
    "sayfa_duzenle": SayfaDuzenleParametreleri,
    "sikistir": SikistirParametreleri,
    "karart": KarartParametreleri,
    "damga": DamgaParametreleri,
    "not": NotParametreleri,
    "donustur": DonusturParametreleri,
}


class IslemIstegi(_StrictModel):
    islem: Literal["birlestir", "bol", "sayfa_duzenle", "sikistir", "karart", "damga", "not", "donustur"]
    girdiler: list[str] = Field(min_length=1)
    parametreler: dict[str, Any] = Field(default_factory=dict)
    cikti_adi: Optional[str] = Field(default=None, max_length=200)


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _dosya_yaniti(file_id: str, path: str, ad: str, **ek: Any) -> dict[str, Any]:
    """Cache kaydını yazar ve §3 `Dosya` nesnesini döndürür (meta çekirdekten)."""
    meta = cekirdek.sayfa_meta(path)
    kayit = {"path": path, "filename": ad, "owner": ek.pop("owner"), "kaynak": KAYNAK,
             "sayfa": meta["sayfa"], "sayfalar": meta["sayfalar"]}
    DOWNLOAD_CACHE.set(file_id, kayit)
    yanit = {"id": file_id, "ad": ad, "sayfa": meta["sayfa"], "boyut": meta["boyut"], "sayfalar": meta["sayfalar"]}
    yanit.update(ek)
    return yanit


def _sahipli_kayit(file_id: str, user: dict) -> dict[str, Any]:
    """Sahibine ait PDF aracı kaydı; aksi her durumda 404 (varlık maskelenir)."""
    kayit = DOWNLOAD_CACHE.get(file_id)
    if not kayit or kayit.get("kaynak") != KAYNAK:
        raise HTTPException(status_code=404, detail=BULUNAMADI)
    sahip = (kayit.get("owner") or "").strip().lower()
    istekci = _owner_id(user)
    if not istekci or not sahip or istekci != sahip:
        TechnicalLogger.log("WARNING", f"PDF araçları sahiplik uyuşmazlığı: {file_id}")
        raise HTTPException(status_code=404, detail=BULUNAMADI)
    if not os.path.exists(kayit.get("path") or ""):
        DOWNLOAD_CACHE.delete(file_id)
        raise HTTPException(status_code=404, detail="Dosya diskte bulunamadı.")
    return kayit


def _pdf_adi(ad: Optional[str], varsayilan: str) -> str:
    """Kullanıcıya görünen ad: sanitize + `.pdf` uzantısı garantili."""
    temiz = sanitize_filename(ad) if ad else ""
    if not temiz or temiz in (".pdf",):
        temiz = varsayilan
    if not temiz.lower().endswith(".pdf"):
        temiz = f"{Path(temiz).stem or 'belge'}.pdf"
    return temiz


def _hata(status: int, detail: str, error_kod: str, exc: Exception) -> HTTPException:
    """Log sözleşmesi: 4xx WARNING, 5xx TEK ERROR."""
    if status >= 500:
        logger.error(f"PDF araçları hatası [{error_kod}]: {exc}")
    else:
        logger.warning(f"PDF araçları reddi [{error_kod}]: {exc}")
    return HTTPException(status_code=status, detail={"mesaj": detail, "error_kod": error_kod})


def _cekirdek_hatasini_cevir(exc: Exception) -> HTTPException:
    if isinstance(exc, cekirdek.ParametreHatasi):
        return _hata(422, str(exc), "parametre_hatasi", exc)
    if isinstance(exc, cekirdek.SayfaSinirAsildi):
        return _hata(413, f"Çıktı sayfa tavanını aşıyor ({settings.pdf_araclari_max_sayfa}).", "sayfa_siniri", exc)
    if isinstance(exc, cekirdek.ZamanAsimi):
        return _hata(504, "İşlem zaman bütçesinde bitmedi; daha küçük parçalarla deneyin.", "zaman_asimi", exc)
    if isinstance(exc, cekirdek.AracYok):
        return _hata(503, "İşlem için gerekli araç sunucuda yok.", "arac_yok", exc)
    if isinstance(exc, ConversionBusyError):
        return _hata(503, "Sistem meşgul; birkaç dakika sonra tekrar deneyin.", "sistem_mesgul", exc)
    if isinstance(exc, cekirdek.PdfArcHatasi):
        return _hata(422, str(exc), "pdf_hatasi", exc)
    return _hata(500, "PDF işlemi başarısız.", "islem_hatasi", exc)


def _deadline() -> float:
    return time.monotonic() + settings.pdf_araclari_butce_saniye


# ── Uçlar ────────────────────────────────────────────────────────────────────

@router.post("/yukle")
@limiter.limit(HIZ_SINIRI)
async def yukle(request: Request, file: UploadFile, user: dict = Depends(get_current_user)):
    """Tek dosya yükler, PDF'e çevirir (K3), çalışma dosyası olarak cache'e yazar; yanıt `Dosya`."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _hata(415, f"İzin verilmeyen dosya uzantısı: {suffix or '(yok)'}", "uzanti", ValueError(suffix))
    ham_dizin = tempfile.mkdtemp(prefix="pdf_araclari_")
    file_id = str(uuid.uuid4())
    ham_yol = os.path.join(ham_dizin, f"{file_id}{suffix}")
    try:
        toplam = 0
        with open(ham_yol, "wb") as f:
            while chunk := await file.read(65536):
                toplam += len(chunk)
                if toplam > MAX_UPLOAD_BYTES:
                    raise _hata(413, f"Dosya çok büyük. Maksimum {MAX_UPLOAD_MB}MB.", "boyut", ValueError(toplam))
                f.write(chunk)
        if toplam == 0:
            raise _hata(422, "Dosya boş.", "bos_dosya", ValueError(0))
        try:
            validate_file_type(ham_yol)
        except HTTPException as e:
            raise _hata(415, str(e.detail), "dosya_turu", e) from None

        def _calis() -> dict[str, Any]:
            _cleanup_process_cache()
            deadline = _deadline()
            acquire_conversion_slot(_pdf_arac_semaphore, deadline, "PDF aracı yükleme")
            try:
                yol = cekirdek.pdf_ye_cevir(ham_yol, str(_pdf_araclari_dir()), deadline)
            finally:
                _pdf_arac_semaphore.release()
            ad = _pdf_adi(file.filename, "belge.pdf")
            return _dosya_yaniti(file_id, yol, ad, owner=_owner_id(user))

        try:
            return await run_in_threadpool(_calis)
        except HTTPException:
            raise
        except (cekirdek.PdfArcHatasi, ConversionBusyError) as e:
            raise _cekirdek_hatasini_cevir(e) from None
        except Exception as e:
            raise _hata(422, "Dosya PDF'e çevrilemedi.", "donusum_basarisiz", e) from None
    finally:
        shutil.rmtree(ham_dizin, ignore_errors=True)


def _islemi_kos(istek: IslemIstegi, parametreler: _StrictModel, girdiler: list[dict[str, Any]], owner: str) -> list[dict[str, Any]]:
    """Threadpool'da: semafor + deadline altında çekirdeği çağırır, çıktıları cache'e yazar."""
    _cleanup_process_cache()
    deadline = _deadline()
    cikti_dizini = str(_pdf_araclari_dir())
    yollar = [g["path"] for g in girdiler]
    ilk_ad = Path(girdiler[0]["filename"]).stem
    p = parametreler.model_dump()
    acquire_conversion_slot(_pdf_arac_semaphore, deadline, "PDF aracı işlemi")
    try:
        ciktilar: list[tuple[str, str, dict[str, Any]]] = []  # (yol, görünen ad, ek alanlar)
        if istek.islem == "birlestir":
            yol = cekirdek.birlestir(yollar, cikti_dizini, deadline, cikti_adi=f"{uuid.uuid4()}.pdf",
                                     max_sayfa=settings.pdf_araclari_max_sayfa)
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, "birlestirilmis.pdf"), {}))
        elif istek.islem == "bol":
            parcalar = cekirdek.bol(yollar[0], cikti_dizini, deadline, araliklar=p["araliklar"], her_n=p["her_n"])
            govde = Path(yollar[0]).stem
            gorunen_govde = Path(_pdf_adi(istek.cikti_adi, f"{ilk_ad}.pdf")).stem
            for yol in parcalar:
                ek = Path(yol).stem[len(govde):]  # "_1-3"
                ciktilar.append((yol, f"{gorunen_govde}{ek}.pdf", {}))
        elif istek.islem == "sayfa_duzenle":
            yol = cekirdek.sayfa_duzenle(yollar[0], p["sayfalar"], cikti_dizini, deadline, cikti_adi=f"{uuid.uuid4()}.pdf")
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, f"{ilk_ad}_duzenlenmis.pdf"), {}))
        elif istek.islem == "sikistir":
            yol, kucultme = cekirdek.sikistir(yollar[0], p["seviye"], cikti_dizini, deadline, cikti_adi=f"{uuid.uuid4()}.pdf")
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, f"{ilk_ad}_sikistirilmis.pdf"), {"kucultme": kucultme}))
        elif istek.islem == "karart":
            yol = cekirdek.karart(yollar[0], p["alanlar"], cikti_dizini, deadline, cikti_adi=f"{uuid.uuid4()}.pdf")
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, f"{ilk_ad}_karartilmis.pdf"), {}))
        elif istek.islem == "damga":
            yol = cekirdek.damga(yollar[0], p["metin"], p["konum"], cikti_dizini, deadline, sayfalar=p["sayfalar"],
                                 punto=p["punto"], renk=p["renk"], cikti_adi=f"{uuid.uuid4()}.pdf")
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, f"{ilk_ad}_damgali.pdf"), {}))
        elif istek.islem == "not":
            yol = cekirdek.not_ekle(yollar[0], p["sayfa"], p["x"], p["y"], p["metin"], cikti_dizini, deadline,
                                    cikti_adi=f"{uuid.uuid4()}.pdf")
            ciktilar.append((yol, _pdf_adi(istek.cikti_adi, f"{ilk_ad}_notlu.pdf"), {}))
        else:  # donustur: girdi zaten PDF (K3) → kopya; sözleşme bütünlüğü için
            kopya_girdi = os.path.join(cikti_dizini, f"{uuid.uuid4()}.pdf")
            yol = cekirdek.pdf_ye_cevir(yollar[0], cikti_dizini, deadline)
            os.replace(yol, kopya_girdi)
            ciktilar.append((kopya_girdi, _pdf_adi(istek.cikti_adi, f"{ilk_ad}.pdf"), {}))
    finally:
        _pdf_arac_semaphore.release()
    return [_dosya_yaniti(str(uuid.uuid4()), yol, ad, owner=owner, **ek) for yol, ad, ek in ciktilar]


@router.post("/islem")
@limiter.limit(HIZ_SINIRI)
async def islem(request: Request, istek: IslemIstegi, user: dict = Depends(get_current_user)):
    """Çalışma dosyaları üstünde tek işlem; çıktılar yeni id'lerle cache'e. Yanıt `{"ciktilar": [Dosya]}`."""
    if len(istek.girdiler) > settings.pdf_araclari_max_girdi:
        raise _hata(422, f"İşlem başına en çok {settings.pdf_araclari_max_girdi} girdi.", "girdi_siniri",
                    ValueError(len(istek.girdiler)))
    if istek.islem != "birlestir" and len(istek.girdiler) != 1:
        raise _hata(422, f"'{istek.islem}' tek girdi alır.", "girdi_sayisi", ValueError(len(istek.girdiler)))
    try:
        parametreler = PARAMETRE_MODELLERI[istek.islem].model_validate(istek.parametreler)
    except ValidationError as e:
        raise _hata(422, f"Parametre hatası: {e.errors()[0].get('msg', '')}", "parametre_hatasi", e) from None
    girdiler = [_sahipli_kayit(gid, user) for gid in istek.girdiler]
    try:
        ciktilar = await run_in_threadpool(_islemi_kos, istek, parametreler, girdiler, _owner_id(user))
    except HTTPException:
        raise
    except Exception as e:
        raise _cekirdek_hatasini_cevir(e) from None
    return {"ciktilar": ciktilar}


@router.get("/onizleme/{file_id}/{sayfa}")
async def onizleme(file_id: str, sayfa: int, genislik: int = 240, user: dict = Depends(get_current_user)):
    """Sayfa PNG'si; `genislik` 64-1600 (aksi 422), sayfa aşımı 404; tarayıcı önbelleği özel 1 saat."""
    if not (cekirdek.ONIZLEME_GENISLIK_ARALIGI[0] <= genislik <= cekirdek.ONIZLEME_GENISLIK_ARALIGI[1]):
        raise _hata(422, "Önizleme genişliği 64-1600 piksel olmalı.", "parametre_hatasi", ValueError(genislik))
    kayit = _sahipli_kayit(file_id, user)
    if sayfa < 1 or sayfa > int(kayit.get("sayfa") or 0):
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı.")
    try:
        png = await run_in_threadpool(cekirdek.onizleme_png, kayit["path"], sayfa, genislik)
    except cekirdek.ParametreHatasi:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı.") from None
    except Exception as e:
        raise _cekirdek_hatasini_cevir(e) from None
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


# Bekçi (K10): uç yolları nginx `location /api` altında kalmalı — test_pdf_araclari_uclari doğrular.
assert all(str(getattr(r, "path", "")).startswith("/api/") for r in router.routes), "PDF araçları uçları /api/ altında olmalı"
