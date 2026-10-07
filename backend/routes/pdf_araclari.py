"""PDF araçları uçları (G268 + G269, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §3 ve §6.3 son satır).

`POST /api/pdf-araclari/yukle` · `POST /api/pdf-araclari/islem` · `GET /api/pdf-araclari/onizleme/{id}/{sayfa}` ·
`POST /api/pdf-araclari/karta-bagla` · `POST /api/pdf-araclari/karttan-al`.
İndirme mevcut `GET /api/download/{id}` ucundan (routes/processing) — değişmedi.

**Karta bağla (G269, K4/K5/K17):** çalışma dosyası tek adımda kartın belgesi olur. `durum=KESIN` → MEVCUT hat
(`document_pipeline.convert_pdfa_and_queue_uploads`: PDF/A + ham/işlenmiş arşiv kuyruğu + URL commit'inde bildirim
ve Hukukbot allowlist'i — yeni kural yok; `/process` analizi ve e-posta YOK). `durum=TASLAK` → PDF/A YOK,
`save_case_document(durum="TASLAK")` + tek `islenmis` kuyruğu `03_TASLAKLAR/<ofis_no>/`; G282 filtreleri taslağı
Hukukbot'tan ve bildirimden eler. Idempotent: `istek_kimligi` (UUID) `ConfirmReceipt` deseniyle
(`services/confirm_idempotency`, anahtar `pdf_araclari:<uuid>`, şema değişmedi) — tekrar `{"document_id": aynı,
"reused": true}`. Kilitli kart (`KayitMesgulError`) 409, dönüşüm kuyruğu dolu 503, ikisi de kaydı bırakır.

**Karttan al:** kartın arşivdeki belgesi (`sharepoint_url` dolu) `documents.py` indirme yardımcısıyla
(`sharepoint_uploader_graph.download_file_from_sharepoint`) çekilir → `pdf_ye_cevir` (arşivde Office/UDF de olabilir)
→ çalışma dosyası (`Dosya`). Taslak belge `03_TASLAKLAR/<ofis_no>/`den, kesin belge işlenmiş arşivden okunur.

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
import re
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from auth_helpers import get_tenant_owned_case, get_tenant_owned_document
from config.settings import settings
from constants import normalize_belge_durumu, normalize_belge_yonu
from database import SessionLocal
from db_errors import KAYIT_MESGUL_DETAIL, KayitMesgulError
from dependencies import get_current_tenant, get_current_user
from file_utils import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    _normalize_doctype_code,
    safe_remove,
    sanitize_filename,
    validate_file_type,
)
from managers.config_manager import DynamicConfig
from managers.log_manager import TechnicalLogger
import models
from pdf import pdf_araclari as cekirdek
from pdf.format_converter import ConversionBusyError, acquire_conversion_slot
from rate_limiting import limiter
from routes.processing import DOWNLOAD_CACHE, _cache_dir, _cleanup_process_cache, _owner_id
from services import confirm_idempotency, document_pipeline, upload_queue

router = APIRouter(prefix="/api/pdf-araclari")
logger = logging.getLogger(__name__)

KAYNAK = "pdf_araclari"
HIZ_SINIRI = "30/minute"
# G269: belge kaynağı kolonu (constants.BELGE_KAYNAKLARI) — cache `kaynak`ından (küçük harf) AYRI.
BELGE_KAYNAGI = "PDF_ARACLARI"
# G269: idempotency anahtarı öneki — `ConfirmReceipt.process_id` (String(64)) /confirm'ün UUID'leriyle
# aynı tabloda yaşar; önek iki uzayı ayırır (13 + 36 = 49 karakter).
IDEMPOTENCY_ONEKI = "pdf_araclari:"
KART_BULUNAMADI = "Belirtilen dava bulunamadı."
BELGE_BULUNAMADI = "Belge bulunamadı."
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


class KartaBaglaIstegi(_StrictModel):
    """§3 + §6.3: `yon`/`durum` `constants.normalize_belge_*`'dan geçer (küçük harf kabul, bilinmeyen 422)."""

    id: str = Field(min_length=1, max_length=64)
    case_id: int = Field(ge=1)
    belge_turu_kodu: str = Field(min_length=1, max_length=64)
    dosya_adi: str = Field(min_length=1, max_length=255)
    case_party_id: Optional[int] = Field(default=None, ge=1)
    istek_kimligi: uuid.UUID
    yon: str = "GELEN"
    durum: str = "KESIN"

    @field_validator("yon")
    @classmethod
    def _yon(cls, v: str) -> str:
        return normalize_belge_yonu(v)

    @field_validator("durum")
    @classmethod
    def _durum(cls, v: str) -> str:
        return normalize_belge_durumu(v)


class KarttanAlIstegi(_StrictModel):
    document_id: int = Field(ge=1)


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


# ── G269: karta bağla / karttan al ───────────────────────────────────────────

def _belge_turleri() -> list[dict]:
    """Belge türü listesi: süreç-içi DynamicConfig (açılışta DB'den ısıtılır), boşsa DB'den okunur."""
    turler = DynamicConfig.get_instance().get_doctypes()
    if not turler:
        from managers.reference_lists import get_doctypes

        turler = get_doctypes()
    return turler or []


def _belge_turu_coz(kod: str) -> tuple[str, Optional[str]]:
    """İstekteki kodu listedeki KANONİK koda (DB'deki `_` pad'li yazım) ve adına çözer; yoksa 422.

    Karşılaştırma `_normalize_doctype_code` ile (padding tuzağı: `DAVA-DLK` == `DAVA-DLK______`)."""
    hedef = _normalize_doctype_code(kod)
    if hedef:
        for tur in _belge_turleri():
            ham = tur.get("kod") or tur.get("code") or tur.get("value")
            if ham and _normalize_doctype_code(str(ham)) == hedef:
                return str(ham), tur.get("aciklama") or tur.get("label") or tur.get("name") or None
    raise _hata(422, f"Belge türü kodu tanınmadı: {kod}", "belge_turu", ValueError(kod))


def _kart_dosya_adi(ad: str) -> str:
    """Kart belgesinin adı: `sanitize_filename` + `.pdf` zorunlu; sonuç boşsa 422 (varsayılan ad UYDURULMAZ)."""
    ham = os.path.basename((ad or "").strip().replace("\\", "/"))
    govde = ham
    for uzanti in sorted(ALLOWED_EXTENSIONS, key=len, reverse=True):  # ".pdf" gibi uzantı-yalnız ad da yakalanır
        if ham.lower().endswith(uzanti):
            govde = ham[: -len(uzanti)]
            break
    govde = govde.strip(" .")
    if not govde.strip("_-"):
        raise _hata(422, "Dosya adı boş ya da geçersiz.", "dosya_adi", ValueError(ad))
    try:
        temiz = sanitize_filename(f"{govde}.pdf")
    except HTTPException as e:
        raise _hata(422, f"Dosya adı geçersiz: {e.detail}", "dosya_adi", e) from None
    if not temiz or not Path(temiz).stem.strip(" ._-") or not temiz.lower().endswith(".pdf"):
        raise _hata(422, "Dosya adı boş ya da geçersiz.", "dosya_adi", ValueError(ad))
    return temiz


def _klasor_adi(ofis_no: str) -> str:
    """SharePoint alt klasör adı: ofis no'daki yol ayraçları ve yasak karakterler `-` olur (ayrıştırma YOK, karar 023)."""
    return re.sub(r'[\\/:*?"<>|#%]', "-", (ofis_no or "").strip()).strip(" .") or "KARTSIZ"


def _kart_bul(case_id: int, tenant_id: str) -> SimpleNamespace:
    """Kart `tenant_id == X OR IS NULL` + soft-delete süzgeciyle; yoksa 404. Oturum kapanmadan kopya alınır."""
    db = SessionLocal()
    try:
        kart = get_tenant_owned_case(db, case_id, tenant_id)
        if kart is None:
            raise HTTPException(status_code=404, detail=KART_BULUNAMADI)
        return SimpleNamespace(id=kart.id, tracking_no=kart.tracking_no, esas_no=kart.esas_no)
    finally:
        db.close()


def _taraf_dogrula(case_party_id: Optional[int], case_id: int) -> None:
    """`case_party_id` verilmişse o kartın tarafı olmalı; değilse 422."""
    if case_party_id is None:
        return
    db = SessionLocal()
    try:
        taraf = (
            db.query(models.CaseParty.id)
            .filter(models.CaseParty.id == case_party_id, models.CaseParty.case_id == case_id)
            .first()
        )
    finally:
        db.close()
    if taraf is None:
        raise _hata(422, "Taraf bu davanın tarafı değil.", "taraf", ValueError(case_party_id))


def _kullanici_adi(user: dict) -> str:
    return user.get("name") or user.get("preferred_username") or "Bilinmeyen"


def _kullanici_eposta(user: dict) -> Optional[str]:
    return user.get("preferred_username") or user.get("upn") or user.get("email") or None


def _karta_bagla_kos(
    background_tasks: BackgroundTasks,
    kayit: dict[str, Any],
    kart: SimpleNamespace,
    tur_kodu: str,
    tur_adi: Optional[str],
    dosya_adi: str,
    case_party_id: Optional[int],
    yon: str,
    durum: str,
    user: dict,
    results: dict[str, Any],
) -> int:
    """Threadpool'da: KESIN → mevcut PDF/A hattı; TASLAK → PDF/A'sız kayıt + tek taslak yüklemesi.

    Çalışma dosyası SİLİNMEZ (cache TTL'i siler; kullanıcı zincire devam edebilir) — bu yüzden
    `schedule_cleanup` çağrılmaz; yalnız PDF/A geçici dosyası kuyruğa kopyalandıktan sonra temizlenir.
    Belge yaratıldıysa `results["case_document_id"]` dolar (idempotency release kararı buna bakar).
    """
    kaynak_yol = kayit["path"]
    orijinal_ad = kayit.get("filename") or dosya_adi
    if durum == "KESIN":
        ham_folder = os.getenv("SHAREPOINT_FOLDER_HAM_NAME", "01_HAM_ARSIV")
        islenmis_folder = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")
        ham_filename = f"{datetime.now().strftime('%Y-%m-%d')}_{dosya_adi}"
        timings: dict[str, Any] = {}
        pdfa_temp_file, doc_id = document_pipeline.convert_pdfa_and_queue_uploads(
            background_tasks=background_tasks,
            source_path=kaynak_yol,
            ham_filename=ham_filename,
            ham_folder=ham_folder,
            islenmis_folder=islenmis_folder,
            new_filename=dosya_adi,
            original_filename=orijinal_ad,
            belge_turu_kodu=tur_kodu,
            muvekkiller=[],
            muvekkil_adi=None,
            ai_ozet=None,
            linked_case_id=kart.id,
            case_party_id=case_party_id,
            lawyer_id=None,
            esas_no=kart.esas_no,
            is_test_mode=False,
            user=user,
            current_user_name=_kullanici_adi(user),
            results=results,
            timings=timings,
            ham_source_path=kaynak_yol,
            yon=yon,
            kaynak=BELGE_KAYNAGI,
            durum="KESIN",
            conversion_budget_seconds=settings.pdf_araclari_butce_saniye,
        )
        if pdfa_temp_file and pdfa_temp_file != kaynak_yol:
            # Kuyruk payload'ı spool'a kopyalandı (fallback görevi varsa sırada ondan ÖNCE koşar).
            background_tasks.add_task(safe_remove, pdfa_temp_file)
    else:
        from services.archive_names import unique_islenmis_name

        # Kayıt adı DB'de benzersiz (mevcut hat ile aynı kural): aynı adlı ikinci taslak
        # SharePoint'te öncekini EZMEZ (küçük dosya yüklemesi sormadan değiştirir).
        dosya_adi = unique_islenmis_name(dosya_adi)
        doc_id = document_pipeline.save_case_document(
            case_id=kart.id,
            original_filename=orijinal_ad,
            stored_filename=dosya_adi,
            belge_turu_kodu=tur_kodu,
            belge_turu_adi=tur_adi,
            case_party_id=case_party_id,
            lawyer_id=None,
            esas_no=kart.esas_no,
            is_test_mode=False,
            uploaded_by=_kullanici_adi(user),
            uploaded_by_email=_kullanici_eposta(user),
            yon=yon,
            kaynak=BELGE_KAYNAGI,
            durum="TASLAK",
        )
        if doc_id is not None:
            results["case_document_id"] = doc_id
            hedef = f"{settings.sharepoint_folder_taslak_name}/{_klasor_adi(kart.tracking_no)}"
            # Tek kuyruk: taslak ham arşive GİRMEZ (K12); URL commit'i `upload_queue` yolundan
            # geçer, G282 kapıları (export + bildirim) TASLAK'ı eler.
            if upload_queue.enqueue_upload("islenmis", kaynak_yol, dosya_adi, hedef, document_id=doc_id) is None:
                background_tasks.add_task(document_pipeline.async_islenmis_upload, kaynak_yol, dosya_adi, hedef, doc_id)
    if doc_id is None:
        raise _hata(500, "Belge kaydı açılamadı.", "belge_kaydi", RuntimeError("save_case_document None"))
    return int(doc_id)


@router.post("/karta-bagla")
@limiter.limit(HIZ_SINIRI)
async def karta_bagla(
    request: Request,
    istek: KartaBaglaIstegi,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Çalışma dosyasını kartın belgesi yapar; yanıt `{"document_id", "reused"}` (§3 / §6.3, K17).

    Sıra: idempotency kapısı (ilk yan etkiden ÖNCE; replay'de cache süresi dolmuş olsa da aynı belge döner)
    → sahiplik 404 → kart 404 → tür 422 → ad 422 → taraf 422 → kayıt. Belge yaratılmadan düşen her yol kaydı
    bırakır (retry serbest); belge yaratıldıysa kayıt kalır (mükerrer belge yolu kapalı, bayat eşiği 30 dk).
    """
    anahtar = f"{IDEMPOTENCY_ONEKI}{istek.istek_kimligi}"
    verdict, replay = confirm_idempotency.begin(anahtar, _owner_id(user))
    if verdict == "replay" and replay is not None:
        TechnicalLogger.log("INFO", f"karta-bagla idempotent replay: {anahtar}")
        return {"document_id": replay.get("document_id"), "reused": True}
    if verdict == "in_progress":
        raise HTTPException(
            status_code=409,
            detail="Bu belgenin karta bağlanması sunucuda halen sürüyor. Lütfen bekleyin ve TEKRAR GÖNDERMEYİN.",
        )
    idem_active = verdict == "proceed"
    results: dict[str, Any] = {}
    try:
        try:
            kayit = _sahipli_kayit(istek.id, user)
            kart = _kart_bul(istek.case_id, tenant_id)
            tur_kodu, tur_adi = _belge_turu_coz(istek.belge_turu_kodu)
            dosya_adi = _kart_dosya_adi(istek.dosya_adi)
            _taraf_dogrula(istek.case_party_id, kart.id)
            doc_id = await run_in_threadpool(
                _karta_bagla_kos, background_tasks, kayit, kart, tur_kodu, tur_adi, dosya_adi,
                istek.case_party_id, istek.yon, istek.durum, user, results,
            )
        except KayitMesgulError as e:
            # Kart toplu bir işlemin kilidinde — geçici; WARNING pipeline'da atıldı, burada ERROR yok.
            raise HTTPException(status_code=409, detail=KAYIT_MESGUL_DETAIL) from e
        except ConversionBusyError as e:
            raise _hata(503, document_pipeline.CONVERSION_BUSY_DETAIL, "sistem_mesgul", e) from None
    except BaseException:
        if idem_active and not results.get("case_document_id"):
            confirm_idempotency.release(anahtar)
        raise
    payload = {"document_id": doc_id, "reused": False}
    if idem_active:
        confirm_idempotency.complete(anahtar, payload)
    return payload


def _sharepoint_indir(klasor: str, dosya_adi: str) -> tuple[bytes, str]:
    """`routes/documents.py` indirme ucunun kullandığı yardımcı (testte sahte)."""
    from sharepoint.sharepoint_uploader_graph import download_file_from_sharepoint

    return download_file_from_sharepoint(klasor, dosya_adi)


@router.post("/karttan-al")
@limiter.limit(HIZ_SINIRI)
async def karttan_al(
    request: Request,
    istek: KarttanAlIstegi,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Kartın arşivdeki belgesini çalışma dosyası yapar; yanıt `Dosya`. 404 belge/URL yok, 502 SharePoint, 413 boyut."""
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, istek.document_id, tenant_id, user)
        if doc is None or not doc.sharepoint_url or not doc.stored_filename:
            raise HTTPException(status_code=404, detail=BELGE_BULUNAMADI)
        stored_filename = str(doc.stored_filename)
        gorunen_ad = str(doc.original_filename or doc.stored_filename)
        taslak_mi = getattr(doc, "durum", "KESIN") == "TASLAK"
        ofis_no = doc.case.tracking_no if doc.case is not None else None
    finally:
        db.close()
    if taslak_mi and ofis_no:
        klasor = f"{settings.sharepoint_folder_taslak_name}/{_klasor_adi(ofis_no)}"
    else:
        klasor = os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")

    try:
        icerik, _mime = await run_in_threadpool(_sharepoint_indir, klasor, stored_filename)
    except Exception as e:
        raise _hata(502, "Belge SharePoint'ten alınamadı.", "sharepoint", e) from None
    if not icerik:
        raise _hata(502, "Belge SharePoint'ten boş geldi.", "sharepoint", ValueError(stored_filename))
    if len(icerik) > MAX_UPLOAD_BYTES:
        raise _hata(413, f"Belge çok büyük. Maksimum {MAX_UPLOAD_MB}MB.", "boyut", ValueError(len(icerik)))

    suffix = Path(stored_filename).suffix.lower() or ".pdf"
    ham_dizin = tempfile.mkdtemp(prefix="pdf_araclari_kart_")
    file_id = str(uuid.uuid4())
    ham_yol = os.path.join(ham_dizin, f"{file_id}{suffix}")
    try:
        with open(ham_yol, "wb") as f:
            f.write(icerik)

        def _calis() -> dict[str, Any]:
            _cleanup_process_cache()
            deadline = _deadline()
            acquire_conversion_slot(_pdf_arac_semaphore, deadline, "PDF aracı karttan al")
            try:
                yol = cekirdek.pdf_ye_cevir(ham_yol, str(_pdf_araclari_dir()), deadline)
            finally:
                _pdf_arac_semaphore.release()
            return _dosya_yaniti(file_id, yol, _pdf_adi(gorunen_ad, "belge.pdf"), owner=_owner_id(user))

        try:
            return await run_in_threadpool(_calis)
        except HTTPException:
            raise
        except (cekirdek.PdfArcHatasi, ConversionBusyError) as e:
            raise _cekirdek_hatasini_cevir(e) from None
        except Exception as e:
            raise _hata(422, "Arşiv belgesi PDF'e çevrilemedi.", "donusum_basarisiz", e) from None
    finally:
        shutil.rmtree(ham_dizin, ignore_errors=True)


# Bekçi (K10): uç yolları nginx `location /api` altında kalmalı — test_pdf_araclari_uclari doğrular.
assert all(str(getattr(r, "path", "")).startswith("/api/") for r in router.routes), "PDF araçları uçları /api/ altında olmalı"
