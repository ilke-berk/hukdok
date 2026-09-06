"""Rapor koşu logu — `report_runs` yazma yolu + çıktı saklama/temizlik (G131, K4).

Tek yazma yolu: `kosu_baslat` (satır açılır, COMMIT → id dosya adının parçası
olur) → üretim → `kosu_bitir` (dosya bilgisi ya da `hata`; hata durumunda da
satır KALIR). Önizleme buradan geçmez (loglanmaz).

Çıktı dizini: `settings.rapor_cikti_dizini` (env `RAPOR_CIKTI_DIZINI`), boşsa
`<backend>/data/rapor_ciktilari` (konteynerde `/app/data` = backend-data
volume'u — `teslim_kutusu.get_teslim_spool_dir` ikizi).

Temizlik (`temizle`): `baslangic`i `settings.rapor_cikti_saklama_gun`den eski
ve `dosya_yolu` dolu satırların dosyası silinir, `dosya_yolu=NULL` yazılır;
satır (log) kalır, indirme 410 döner. Her export sonunda `temizle_sessiz` ile
best-effort çağrılır — istisna yutulur, WARNING (log sözleşmesi: deneme düzeyi).
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from config.settings import settings

logger = logging.getLogger(__name__)

IZINLI_UZANTILAR = (".xlsx", ".csv")
HATA_MAX = 500


def cikti_dizini() -> Path:
    """Saklama dizini (yaratılır)."""
    override = (settings.rapor_cikti_dizini or "").strip()
    if override:
        dizin = Path(override)
    else:
        dizin = Path(__file__).resolve().parent.parent.parent / "data" / "rapor_ciktilari"
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


def cikti_yolu(run_id: int, dosya_adi: str) -> Path:
    """`<dizin>/<run_id>-<slug>.<ext>` — ad bileşeni yalnız güvenli karakterlerden."""
    kok = Path(dosya_adi).name
    govde, nokta, uzanti = kok.rpartition(".")
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (govde or kok)).strip("-") or "rapor"
    uzanti = ("." + uzanti.lower()) if nokta else ""
    return cikti_dizini() / f"{run_id}-{slug}{uzanti}"


def yol_guvenli_mi(yol: Optional[str]) -> bool:
    """Saklanan yolun çıktı dizini ALTINDA ve izinli uzantıda olduğunu doğrular
    (`routes/admin.py::api_teslim_rapor_indir` deseni — path traversal savunması)."""
    if not yol:
        return False
    dosya = Path(yol)
    if dosya.suffix.lower() not in IZINLI_UZANTILAR:
        return False
    try:
        kok = cikti_dizini().resolve()
        return kok in dosya.resolve().parents
    except OSError:
        return False


def dosya_mevcut(run: models.ReportRun) -> bool:
    """`dosya_yolu` dolu, dizin altında ve diskte var."""
    yol: Optional[str] = run.dosya_yolu
    return bool(yol) and yol_guvenli_mi(yol) and Path(str(yol)).is_file()


# ─── Yazma yolu ──────────────────────────────────────────────────────────────

def kosu_baslat(db: Session, *, tanim: dict[str, Any], format: str, kaynak: str, veri_kaynagi: str,
                kolon_sayisi: int, satir_sayisi: int, kullanici: str, tenant_id: Optional[str],
                dosya_adi: str, sablon_id: Optional[int] = None) -> models.ReportRun:
    """Koşu satırını açar ve COMMIT eder (id dosya adına girer). Satır sayısı
    COUNT ile önceden ölçülmüştür (tavan aşımı buraya gelmez)."""
    run = models.ReportRun(
        sablon_id=sablon_id, tanim=tanim, format=format, kaynak=kaynak, veri_kaynagi=veri_kaynagi,
        kolon_sayisi=kolon_sayisi, satir_sayisi=satir_sayisi, kullanici=kullanici, tenant_id=tenant_id,
        baslangic=dt.datetime.now(dt.timezone.utc), dosya_adi=dosya_adi,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def kosu_bitir(db: Session, run: models.ReportRun, *, dosya_yolu: Optional[str] = None,
               dosya_boyutu: Optional[int] = None, sha256: Optional[str] = None,
               satir_sayisi: Optional[int] = None, sure_ms: Optional[int] = None,
               hata: Optional[str] = None) -> models.ReportRun:
    """Dosya bilgisini ya da hatayı yazar; hata yolunda satır SİLİNMEZ."""
    run.dosya_yolu = dosya_yolu
    run.dosya_boyutu = dosya_boyutu
    run.sha256 = sha256
    if satir_sayisi is not None:
        run.satir_sayisi = satir_sayisi
    run.sure_ms = sure_ms
    run.hata = (hata or "")[:HATA_MAX] or None
    db.commit()
    db.refresh(run)
    return run


# ─── Temizlik ────────────────────────────────────────────────────────────────

def temizle(db: Session, simdi: Optional[dt.datetime] = None, saklama_gun: Optional[int] = None) -> int:
    """Saklama süresi dolan çıktı dosyalarını siler, `dosya_yolu=NULL` yazar.
    Döner: temizlenen satır sayısı. Diskte olmayan dosya da NULL'lanır (kayıt
    tutarlılığı); silme hatası satırı atlar (WARNING)."""
    simdi = simdi or dt.datetime.now(dt.timezone.utc)
    gun = settings.rapor_cikti_saklama_gun if saklama_gun is None else saklama_gun
    esik = simdi - dt.timedelta(days=max(0, int(gun)))
    adaylar = (
        db.query(models.ReportRun)
        .filter(models.ReportRun.dosya_yolu.isnot(None), models.ReportRun.baslangic < esik)
        .all()
    )
    temizlenen = 0
    for run in adaylar:
        yol_metni: Optional[str] = run.dosya_yolu
        yol = Path(str(yol_metni))
        try:
            if yol_guvenli_mi(yol_metni) and yol.is_file():
                yol.unlink()
        except OSError as exc:
            logger.warning("Rapor ciktisi silinemedi run=%s yol=%s: %s", run.id, yol, exc)
            continue
        run.dosya_yolu = None
        temizlenen += 1
    if temizlenen:
        db.commit()
    return temizlenen


def temizle_sessiz(db: Session) -> int:
    """Best-effort temizlik (export sonunda): istisna yutulur, WARNING loglanır."""
    try:
        return temizle(db)
    except Exception as exc:  # bilinçli geniş yakalama: temizlik export'u düşürmez
        logger.warning("Rapor cikti temizligi atlandi: %s", exc)
        try:
            db.rollback()
        except Exception:  # pragma: no cover — rollback da patlarsa yutulur
            pass
        return 0


__all__ = [
    "HATA_MAX", "IZINLI_UZANTILAR", "cikti_dizini", "cikti_yolu", "dosya_mevcut", "kosu_baslat", "kosu_bitir",
    "temizle", "temizle_sessiz", "yol_guvenli_mi",
]
