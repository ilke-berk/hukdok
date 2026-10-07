"""PDF araçları çekirdeği (G267, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §1 K3-K8, §3, §5).

HTTP bilmeyen, `deadline` (time.monotonic tabanlı, None = bütçesiz) alan saf fonksiyonlar:
birleştir, böl, sayfa düzenle, sıkıştır, karart, damga, not, pdf'e çevir, sayfa meta, önizleme.

Ortak kurallar:
- Hiçbir fonksiyon GİRDİ dosyasını değiştirmez; çıktı verilen dizine geçici ada yazılır ve
  sonda `os.replace` ile adlandırılır (yarım dosya kalmaz).
- Koordinatlar (karartma, not, damga) **görünür** sayfa düzlemindedir: sol-üst orijin, PDF
  puanı, döndürme uygulanmış (`page.rect`). PyMuPDF açıklama/metin yöntemleri döndürülmemiş
  düzlem ister → `page.derotation_matrix` ile çevrilir (07.10 konteyner deneyiyle doğrulandı:
  `rect * derotation_matrix` → açıklama, `rect * rotation_matrix` → görünür).
- Log sözleşmesi: çekirdek yalnız deneme düzeyi WARNING basar; nihai hata çağıranda (route).
- Hata sınıfları tek tabandan (`PdfArcHatasi`); route bunları 4xx/5xx'e çevirir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Sequence

import fitz

from pdf.format_converter import (
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    _clip_timeout,
    image_to_pdf,
    office_to_pdf,
)
from pdf.pdf_converter import _find_ghostscript, _gs_timeout, _udf_to_pdfa2b

try:
    from managers.log_manager import TechnicalLogger
except ImportError:  # pragma: no cover - yalnız modül tek başına import edilirse
    class TechnicalLogger:  # type: ignore[no-redef]
        @staticmethod
        def log(level, message, metadata=None):
            import logging

            logging.log(getattr(logging, level, logging.INFO), message)


# ── Hata sınıfları ───────────────────────────────────────────────────────────

class PdfArcHatasi(Exception):
    """PDF araçları çekirdeğinin ortak tabanı (açılamayan/şifreli PDF dahil)."""


class ParametreHatasi(PdfArcHatasi):
    """Çağıranın verdiği parametre geçersiz (route → 422)."""


class SayfaSinirAsildi(PdfArcHatasi):
    """Çıktı sayfa sayısı tavanı aşıyor (route → 413)."""


class AracYok(PdfArcHatasi):
    """Gerekli dış araç (Ghostscript, DejaVuSans) bulunamadı."""


class ZamanAsimi(PdfArcHatasi):
    """Zaman bütçesi doldu (route → 504); alt süreç öldürülmüştür."""


# ── Sabitler ─────────────────────────────────────────────────────────────────

DEJAVU_FONTFILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_FONTNAME = "DejaVuSans"
DAMGA_KONUMLARI = ("sag-ust", "sol-ust", "sag-alt", "sol-alt", "orta")
DAMGA_MAX_KARAKTER = 120
NOT_MAX_KARAKTER = 2000
DAMGA_KENAR_BOSLUGU = 36.0  # PDF puanı (yarım inç)
SIKISTIRMA_SEVIYELERI = {"ekran": "/screen", "ebook": "/ebook", "yazici": "/printer"}
ONIZLEME_GENISLIK_ARALIGI = (64, 1600)
GECERLI_DONDURMELER = {0, 90, 180, 270}


# ── Ortak yardımcılar ────────────────────────────────────────────────────────

def _sure_kontrol(deadline: Optional[float]) -> None:
    """Bütçe dolduysa ZamanAsimi — uzun döngülerin arasında çağrılır."""
    if deadline is not None and time.monotonic() >= deadline:
        raise ZamanAsimi("Zaman bütçesi doldu")


def _ac(pdf_path: str) -> fitz.Document:
    """PDF'i açar; açılamayan ya da şifreli dosya PdfArcHatasi."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:  # fitz FileDataError / RuntimeError / FileNotFoundError
        raise PdfArcHatasi(f"PDF açılamadı: {e}") from e
    if doc.needs_pass:
        doc.close()
        raise PdfArcHatasi("PDF şifreli, işlenemez")
    if not doc.is_pdf:
        doc.close()
        raise PdfArcHatasi("Dosya PDF değil")
    return doc


def _hedef_yolu(cikti_dizini: str, ad: str) -> str:
    """Çıktı dizininde çakışmayan nihai yol (`ad.pdf`, `ad-2.pdf`, ...)."""
    os.makedirs(cikti_dizini, exist_ok=True)
    govde, uzanti = os.path.splitext(ad)
    uzanti = uzanti or ".pdf"
    aday = os.path.join(cikti_dizini, govde + uzanti)
    sayac = 2
    while os.path.exists(aday):
        aday = os.path.join(cikti_dizini, f"{govde}-{sayac}{uzanti}")
        sayac += 1
    return aday


def _gecici_ad(hedef: str) -> str:
    return f"{hedef}.{uuid.uuid4().hex}.tmp"


def _kaydet(doc: fitz.Document, hedef: str) -> str:
    """Belgeyi geçici ada yazıp `os.replace` ile adlandırır; hata yolunda geçici dosya silinir."""
    gecici = _gecici_ad(hedef)
    try:
        doc.save(gecici, garbage=3, deflate=True)
        os.replace(gecici, hedef)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)
    return hedef


def _kopyala(kaynak: str, hedef: str) -> str:
    gecici = _gecici_ad(hedef)
    try:
        shutil.copyfile(kaynak, gecici)
        os.replace(gecici, hedef)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)
    return hedef


def _sayfa_no_dogrula(no: Any, sayfa_sayisi: int) -> int:
    if isinstance(no, bool) or not isinstance(no, int):
        raise ParametreHatasi(f"Sayfa numarası tam sayı olmalı: {no!r}")
    if no < 1 or no > sayfa_sayisi:
        raise ParametreHatasi(f"Sayfa numarası aralık dışı: {no} (1-{sayfa_sayisi})")
    return no


def _sayi(deger: Any, ad: str) -> float:
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        raise ParametreHatasi(f"{ad} sayı olmalı: {deger!r}")
    return float(deger)


def _renk(hex_renk: str) -> tuple[float, float, float]:
    """`#rrggbb` → (r, g, b) 0-1 aralığı."""
    if not isinstance(hex_renk, str) or len(hex_renk) != 7 or not hex_renk.startswith("#"):
        raise ParametreHatasi(f"Renk '#rrggbb' biçiminde olmalı: {hex_renk!r}")
    try:
        r, g, b = (int(hex_renk[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError as e:
        raise ParametreHatasi(f"Renk '#rrggbb' biçiminde olmalı: {hex_renk!r}") from e
    return r / 255.0, g / 255.0, b / 255.0


# ── Meta ve önizleme ─────────────────────────────────────────────────────────

def sayfa_meta(pdf_path: str) -> dict[str, Any]:
    """`{"sayfa", "boyut", "sayfalar": [{"no","genislik","yukseklik"}]}` — boyutlar görünür düzlem (`page.rect`)."""
    with _ac(pdf_path) as doc:
        sayfalar = [
            {
                "no": i + 1,
                "genislik": round(float(page.rect.width), 2),
                "yukseklik": round(float(page.rect.height), 2),
            }
            for i, page in enumerate(doc)
        ]
    return {"sayfa": len(sayfalar), "boyut": os.path.getsize(pdf_path), "sayfalar": sayfalar}


def onizleme_png(pdf_path: str, sayfa_no: int, genislik: int = 240) -> bytes:
    """Sayfanın PNG önizlemesi; `genislik` piksel (64-1600). Döndürme pixmap'te görünür."""
    if isinstance(genislik, bool) or not isinstance(genislik, int) or not (
        ONIZLEME_GENISLIK_ARALIGI[0] <= genislik <= ONIZLEME_GENISLIK_ARALIGI[1]
    ):
        raise ParametreHatasi(f"Önizleme genişliği {ONIZLEME_GENISLIK_ARALIGI} aralığında olmalı: {genislik!r}")
    with _ac(pdf_path) as doc:
        no = _sayfa_no_dogrula(sayfa_no, doc.page_count)
        page = doc[no - 1]
        olcek = genislik / float(page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(olcek, olcek), alpha=False)
        return pix.tobytes("png")


# ── İşlemler ─────────────────────────────────────────────────────────────────

def birlestir(
    girdiler: Sequence[str],
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    cikti_adi: str = "birlestirilmis.pdf",
    max_sayfa: Optional[int] = None,
) -> str:
    """Girdileri verilen sırayla tek PDF'e birleştirir. Toplam sayfa `max_sayfa`'yı aşarsa çıktı yazılmadan
    SayfaSinirAsildi."""
    if not girdiler:
        raise ParametreHatasi("Birleştirme için en az bir girdi gerekir")
    _sure_kontrol(deadline)
    kaynaklar = [_ac(p) for p in girdiler]
    try:
        toplam = sum(d.page_count for d in kaynaklar)
        if max_sayfa is not None and toplam > max_sayfa:
            raise SayfaSinirAsildi(f"Toplam sayfa {toplam} > tavan {max_sayfa}")
        hedef = _hedef_yolu(cikti_dizini, cikti_adi)
        with fitz.open() as cikti:
            for kaynak in kaynaklar:
                _sure_kontrol(deadline)
                cikti.insert_pdf(kaynak)
            return _kaydet(cikti, hedef)
    finally:
        for d in kaynaklar:
            d.close()


def _araliklari_dogrula(araliklar: Any, sayfa_sayisi: int) -> list[tuple[int, int]]:
    if not isinstance(araliklar, (list, tuple)) or not araliklar:
        raise ParametreHatasi("araliklar boş olmayan bir liste olmalı")
    sonuc: list[tuple[int, int]] = []
    for aralik in araliklar:
        if not isinstance(aralik, (list, tuple)) or len(aralik) != 2:
            raise ParametreHatasi(f"Aralık [başlangıç, bitiş] biçiminde olmalı: {aralik!r}")
        a = _sayfa_no_dogrula(aralik[0], sayfa_sayisi)
        b = _sayfa_no_dogrula(aralik[1], sayfa_sayisi)
        if a > b:
            raise ParametreHatasi(f"Aralık başlangıcı bitişten büyük: {aralik!r}")
        sonuc.append((a, b))
    sirali = sorted(sonuc)
    for (_, onceki_bitis), (sonraki_bas, _) in zip(sirali, sirali[1:], strict=False):
        if sonraki_bas <= onceki_bitis:
            raise ParametreHatasi("Aralıklar çakışıyor")
    return sonuc


def bol(
    pdf_path: str,
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    araliklar: Optional[Sequence[Sequence[int]]] = None,
    her_n: Optional[int] = None,
) -> list[str]:
    """PDF'i 1 tabanlı kapalı aralıklara YA DA her `her_n` sayfada bir parçaya böler.
    Çıktı adları `<ad>_<bas>-<bit>.pdf`."""
    if (araliklar is None) == (her_n is None):
        raise ParametreHatasi("araliklar ya da her_n'den tam biri verilmeli")
    _sure_kontrol(deadline)
    govde = Path(pdf_path).stem
    ciktilar: list[str] = []
    with _ac(pdf_path) as doc:
        n = doc.page_count
        if her_n is not None:
            if isinstance(her_n, bool) or not isinstance(her_n, int) or her_n < 1:
                raise ParametreHatasi(f"her_n pozitif tam sayı olmalı: {her_n!r}")
            parcalar = [(bas, min(bas + her_n - 1, n)) for bas in range(1, n + 1, her_n)]
        else:
            parcalar = _araliklari_dogrula(araliklar, n)
        try:
            for bas, bit in parcalar:
                _sure_kontrol(deadline)
                hedef = _hedef_yolu(cikti_dizini, f"{govde}_{bas}-{bit}.pdf")
                with fitz.open() as parca:
                    parca.insert_pdf(doc, from_page=bas - 1, to_page=bit - 1)
                    ciktilar.append(_kaydet(parca, hedef))
        except BaseException:
            for yol in ciktilar:
                if os.path.exists(yol):
                    os.remove(yol)
            raise
    return ciktilar


def sayfa_duzenle(
    pdf_path: str,
    sayfalar: Sequence[dict[str, Any]],
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    cikti_adi: Optional[str] = None,
) -> str:
    """Listedeki sıra yeni sıradır; listede olmayan sayfa silinir; `dondur` mevcut döndürmeye eklenir (mod 360)."""
    if not sayfalar:
        raise ParametreHatasi("En az bir sayfa kalmalı")
    _sure_kontrol(deadline)
    with _ac(pdf_path) as doc:
        n = doc.page_count
        secim: list[int] = []
        yeni_dondurmeler: list[int] = []
        for kayit in sayfalar:
            if not isinstance(kayit, dict) or "no" not in kayit:
                raise ParametreHatasi(f"Sayfa kaydı {{'no', 'dondur'?}} biçiminde olmalı: {kayit!r}")
            no = _sayfa_no_dogrula(kayit["no"], n)
            if no in [s + 1 for s in secim]:
                raise ParametreHatasi(f"Sayfa listede birden çok kez geçiyor: {no}")
            dondur = kayit.get("dondur", 0) or 0
            if isinstance(dondur, bool) or not isinstance(dondur, int) or dondur not in GECERLI_DONDURMELER:
                raise ParametreHatasi(f"dondur 0/90/180/270 olmalı: {dondur!r}")
            secim.append(no - 1)
            yeni_dondurmeler.append((doc[no - 1].rotation + dondur) % 360)
        hedef = _hedef_yolu(cikti_dizini, cikti_adi or f"{Path(pdf_path).stem}_duzenlenmis.pdf")
        doc.select(secim)
        for i, derece in enumerate(yeni_dondurmeler):
            doc[i].set_rotation(derece)
        return _kaydet(doc, hedef)


def sikistir(
    pdf_path: str,
    seviye: str,
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    cikti_adi: Optional[str] = None,
) -> tuple[str, int]:
    """Ghostscript `-dPDFSETTINGS` ile sıkıştırır. Döner: (çıktı yolu, küçülme bayt). Çıktı girdiden
    büyükse girdinin kopyası döner ve küçülme 0. Ghostscript yoksa AracYok; bütçe dolarsa ZamanAsimi."""
    if seviye not in SIKISTIRMA_SEVIYELERI:
        raise ParametreHatasi(f"seviye {sorted(SIKISTIRMA_SEVIYELERI)} içinden olmalı: {seviye!r}")
    _sure_kontrol(deadline)
    with _ac(pdf_path):
        pass  # yalnız doğrulama: açılamayan/şifreli PDF'i Ghostscript'e vermeden reddet
    gs = _find_ghostscript()
    if not gs:
        raise AracYok("Ghostscript bulunamadı")
    hedef = _hedef_yolu(cikti_dizini, cikti_adi or f"{Path(pdf_path).stem}_sikistirilmis.pdf")
    gecici = _gecici_ad(hedef)
    komut = [
        gs,
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-dNOOUTERSAVE",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={SIKISTIRMA_SEVIYELERI[seviye]}",
        f"-sOutputFile={gecici}",
        pdf_path,
    ]
    gs_timeout = _clip_timeout(_gs_timeout(), deadline)
    try:
        try:
            sonuc = subprocess.run(
                komut,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=gs_timeout,
            )
        except subprocess.TimeoutExpired:
            # subprocess.run zaman aşımında alt süreci öldürür; deneme düzeyi WARNING (log sözleşmesi)
            TechnicalLogger.log("WARNING", f"Ghostscript sıkıştırma timeout ({gs_timeout:.0f}s aşıldı)")
            raise ZamanAsimi(f"Sıkıştırma {gs_timeout:.0f} sn içinde bitmedi") from None
        if sonuc.returncode != 0 or not os.path.exists(gecici):
            hata = (sonuc.stderr or "Bilinmeyen hata")[:2048]
            TechnicalLogger.log("WARNING", f"Ghostscript sıkıştırma hatası: {hata}")
            raise PdfArcHatasi(f"Ghostscript sıkıştırma hatası: {hata}")
        girdi_boyut = os.path.getsize(pdf_path)
        cikti_boyut = os.path.getsize(gecici)
        if cikti_boyut >= girdi_boyut:
            os.remove(gecici)
            return _kopyala(pdf_path, hedef), 0
        os.replace(gecici, hedef)
        return hedef, girdi_boyut - cikti_boyut
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)


def _gorunur_rect(alan: dict[str, Any], page: fitz.Page) -> fitz.Rect:
    """Görünür düzlem alanını sayfaya kırpar ve açıklama düzlemine (döndürülmemiş) çevirir."""
    rect = fitz.Rect(
        _sayi(alan.get("x0"), "x0"), _sayi(alan.get("y0"), "y0"),
        _sayi(alan.get("x1"), "x1"), _sayi(alan.get("y1"), "y1"),
    ).normalize()
    kirpik = rect & page.rect
    if kirpik.is_empty:
        raise ParametreHatasi(f"Alan sayfa dışında ya da boş: {alan!r}")
    return kirpik * page.derotation_matrix


def karart(
    pdf_path: str,
    alanlar: Sequence[dict[str, Any]],
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    cikti_adi: Optional[str] = None,
) -> str:
    """Alanları gerçekten siler (`apply_redactions`: metin VE görüntü pikselleri). Koordinat görünür düzlem."""
    if not alanlar:
        raise ParametreHatasi("En az bir karartma alanı gerekir")
    _sure_kontrol(deadline)
    with _ac(pdf_path) as doc:
        n = doc.page_count
        sayfa_alanlari: dict[int, list[fitz.Rect]] = {}
        for alan in alanlar:
            if not isinstance(alan, dict):
                raise ParametreHatasi(f"Alan sözlük olmalı: {alan!r}")
            no = _sayfa_no_dogrula(alan.get("sayfa"), n)
            sayfa_alanlari.setdefault(no, []).append(_gorunur_rect(alan, doc[no - 1]))
        hedef = _hedef_yolu(cikti_dizini, cikti_adi or f"{Path(pdf_path).stem}_karartilmis.pdf")
        for no, rectler in sayfa_alanlari.items():
            _sure_kontrol(deadline)
            page = doc[no - 1]
            for rect in rectler:
                page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()  # varsayılan images=PDF_REDACT_IMAGE_PIXELS: görüntü pikselleri de silinir
        return _kaydet(doc, hedef)


def _damga_fontu() -> fitz.Font:
    if not os.path.exists(DEJAVU_FONTFILE):
        raise AracYok(f"Damga yazı tipi yok: {DEJAVU_FONTFILE}")
    return fitz.Font(fontfile=DEJAVU_FONTFILE)


def _damga_noktasi(konum: str, page: fitz.Page, metin_genisligi: float, punto: float) -> fitz.Point:
    """Görünür düzlemde ilk karakterin taban çizgisi noktası."""
    w, h = float(page.rect.width), float(page.rect.height)
    k = DAMGA_KENAR_BOSLUGU
    if konum == "sol-ust":
        return fitz.Point(k, k + punto)
    if konum == "sag-ust":
        return fitz.Point(w - k - metin_genisligi, k + punto)
    if konum == "sol-alt":
        return fitz.Point(k, h - k)
    if konum == "sag-alt":
        return fitz.Point(w - k - metin_genisligi, h - k)
    return fitz.Point((w - metin_genisligi) / 2, (h + punto) / 2)  # orta


def damga(
    pdf_path: str,
    metin: str,
    konum: str,
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    sayfalar: Any = "hepsi",
    punto: float = 12,
    renk: str = "#b00020",
    cikti_adi: Optional[str] = None,
) -> str:
    """Metin damgası (DejaVuSans gömülü, Türkçe glif). `konum` beş değerden biri; `sayfalar` "hepsi" ya da
    1 tabanlı liste; `punto` 4-144; `renk` `#rrggbb`. Metin ≤ 120 karakter."""
    if not isinstance(metin, str) or not metin.strip():
        raise ParametreHatasi("Damga metni boş olamaz")
    if len(metin) > DAMGA_MAX_KARAKTER:
        raise ParametreHatasi(f"Damga metni en çok {DAMGA_MAX_KARAKTER} karakter olabilir")
    if konum not in DAMGA_KONUMLARI:
        raise ParametreHatasi(f"konum {DAMGA_KONUMLARI} içinden olmalı: {konum!r}")
    punto_f = _sayi(punto, "punto")
    if not (4 <= punto_f <= 144):
        raise ParametreHatasi(f"punto 4-144 aralığında olmalı: {punto!r}")
    rgb = _renk(renk)
    _sure_kontrol(deadline)
    font = _damga_fontu()
    genislik = font.text_length(metin, fontsize=punto_f)
    with _ac(pdf_path) as doc:
        n = doc.page_count
        if sayfalar == "hepsi":
            hedef_sayfalar = list(range(1, n + 1))
        elif isinstance(sayfalar, (list, tuple)) and sayfalar:
            hedef_sayfalar = sorted({_sayfa_no_dogrula(s, n) for s in sayfalar})
        else:
            raise ParametreHatasi(f"sayfalar 'hepsi' ya da sayfa numarası listesi olmalı: {sayfalar!r}")
        hedef = _hedef_yolu(cikti_dizini, cikti_adi or f"{Path(pdf_path).stem}_damgali.pdf")
        for no in hedef_sayfalar:
            _sure_kontrol(deadline)
            page = doc[no - 1]
            nokta = _damga_noktasi(konum, page, genislik, punto_f) * page.derotation_matrix
            page.insert_text(
                nokta,
                metin,
                fontsize=punto_f,
                fontname=DEJAVU_FONTNAME,
                fontfile=DEJAVU_FONTFILE,
                color=rgb,
                rotate=page.rotation,  # görünür düzlemde dik dursun (deney: rotate=page.rotation)
            )
        return _kaydet(doc, hedef)


def not_ekle(
    pdf_path: str,
    sayfa: int,
    x: float,
    y: float,
    metin: str,
    cikti_dizini: str,
    deadline: Optional[float] = None,
    *,
    cikti_adi: Optional[str] = None,
) -> str:
    """Yapışkan not açıklaması (`add_text_annot`); (x, y) görünür düzlem; metin ≤ 2.000 karakter."""
    if not isinstance(metin, str) or not metin.strip():
        raise ParametreHatasi("Not metni boş olamaz")
    if len(metin) > NOT_MAX_KARAKTER:
        raise ParametreHatasi(f"Not metni en çok {NOT_MAX_KARAKTER} karakter olabilir")
    nokta = fitz.Point(_sayi(x, "x"), _sayi(y, "y"))
    _sure_kontrol(deadline)
    with _ac(pdf_path) as doc:
        no = _sayfa_no_dogrula(sayfa, doc.page_count)
        page = doc[no - 1]
        if not page.rect.contains(nokta):
            raise ParametreHatasi(f"Not noktası sayfa dışında: ({x}, {y})")
        hedef = _hedef_yolu(cikti_dizini, cikti_adi or f"{Path(pdf_path).stem}_notlu.pdf")
        page.add_text_annot(nokta * page.derotation_matrix, metin)
        return _kaydet(doc, hedef)


def pdf_ye_cevir(kaynak: str, cikti_dizini: str, deadline: Optional[float] = None) -> str:
    """`.pdf` → kopya; `.udf` → `_udf_to_pdfa2b`; resim/Office → `format_converter` (`ensure_pdf` ile aynı
    dağıtım, `deadline` iletilir; semafor dolu → `ConversionBusyError` çağırana sızar, route 503 yapar)."""
    uzanti = Path(kaynak).suffix.lower()
    _sure_kontrol(deadline)
    hedef = _hedef_yolu(cikti_dizini, f"{Path(kaynak).stem}.pdf")
    if uzanti == ".pdf":
        with _ac(kaynak):
            pass
        return _kopyala(kaynak, hedef)
    gecici = _gecici_ad(hedef)
    try:
        if uzanti == ".udf":
            _udf_to_pdfa2b(kaynak, gecici, deadline=deadline)
        elif uzanti in IMAGE_EXTENSIONS:
            image_to_pdf(kaynak, gecici, deadline=deadline)
        elif uzanti in OFFICE_EXTENSIONS:
            office_to_pdf(kaynak, gecici, deadline=deadline)
        else:
            raise ParametreHatasi(f"Desteklenmeyen uzantı: {uzanti or '(yok)'}")
        if not os.path.exists(gecici):
            raise PdfArcHatasi("Dönüştürücü çıktı üretmedi")
        os.replace(gecici, hedef)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)
    return hedef
