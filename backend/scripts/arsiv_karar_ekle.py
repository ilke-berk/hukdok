#!/usr/bin/env python3
"""Büro karar arşivini kartların altına ARŞİV BELGESİ olarak ekler (05.10.2026).

Kullanıcı kararı (05.10.2026): "ilk aşamada eşleşenler üzerinden gidelim" — karar
PDF'lerinin föy eşleşmesi depo DIŞINDA hesaplanır (karar → teslim paketindeki föy;
`docs/plan/karar-belgeleri-calisma-plani-2026-10-05.md` §5.3) ve bu script'e bir liste
(CSV) olarak verilir. Script yalnız HUKDOK tarafını yapar: föy → kart, kart → aşama
kararı, belge kaydı.

Girdi CSV'si (UTF-8, başlıklı; kişi adı taşımaz):
    dosya           arşivdeki dosya adı (`tarih__mahkeme__esas__uzmanlık__sonuç__kimlik.pdf`)
    sha256          dosyanın parmak izi
    foyler          föy sistem numaraları, `;` ile (hepsi AYNI karta gitmeli)
    belge_tarihi    karar tarihi (YYYY-AA-GG; boş olabilir)
    mahkeme_etiketi dosya adındaki mahkeme (`ISTANBUL_BAM_14_HD`; belge türü buradan)
    esas_no         dosya adındaki esas (`2019/1186`; boş olabilir)
    asama_mahkeme / asama_esas / asama_tarih
                    pakette tutan aşama satırının künyesi (boş olabilir)
    aciklama        (isteğe bağlı sütun) belge özetine eklenir — eşleşme künyeyle değil karar
                    metniyle kurulduysa kartta görünsün diye

Ne yapar:
* **Kart:** `foyler` → `case_foys.sistem_no` → kart. Föy yoksa, kart silinmişse ya da
  föyler birden çok karta gidiyorsa belge EKLENMEZ (kart seçilmez, rapora düşer).
* **Aşama bağı** (`case_documents.asama_karari_id`): kartın `case_stage_decisions`
  satırlarında önce paketin aşama künyesi, sonra dosya adının künyesi aranır —
  esas no + karar tarihi, yoksa yalnız esas no, yoksa karar tarihi + mahkeme. TEK satır
  tutuyorsa bağlanır; tutmuyorsa ya da birden çok satır tutuyorsa bağ BOŞ kalır
  (tahmin edilmez), belge yine karta girer.
* **Belge türü:** mahkeme etiketinden — Danıştay / Yargıtay / BAM-BİM (istinaf) / AYM,
  diğerleri gerekçeli karar.
* **Mükerrer:** aynı kartta aynı parmak izi varsa atlanır (kısmi unique index
  `uq_case_docs_kart_sha`, migrasyon 60) — script yeniden koşulabilir.

Ne YAPMAZ (bilinçli):
* Analiz / onay hattından (`/process` → `/confirm`) geçmez; SharePoint'e yüklemez →
  `sharepoint_url` boş kalır, belge kartta listelenir ama karttan AÇILAMAZ (arşive
  yükleme ayrı adım, kullanıcı kararı).
* `notify_hukukbot` çağırmaz (`sharepoint_url` boş kayıt export'a da girmez) ve
  `belge_islendi` bildirimi üretmez.
* `uploaded_at` = KARAR TARİHİ yazılır (yükleme anı değil): 3.000+ belge "son
  belgeler" listesini ve günlük aktivite raporunu doldurmasın, kartta kendi tarihinde
  dursun. Aktarımın izi `uploaded_by = "ARSIV_AKTARIM"` + `--kim`.

200 belgede bir commit (02.10 kilit dersi: tek uzun transaction yok). Yine de prod'da
`--apply` mesai DIŞINDA; kuru koşu prod'da değil, prod dump'ının kopyasında.

    docker compose exec -T backend python scripts/arsiv_karar_ekle.py --liste /tmp/liste.csv
    docker compose exec -T backend python scripts/arsiv_karar_ekle.py --liste /tmp/liste.csv --apply --kim "ilke"

**İkinci adım — arşive yükleme (`--yukle`, kullanıcı kararı 05.10):** eklenmiş arşiv
belgelerinin PDF'ini SharePoint arşivine (`SHAREPOINT_FOLDER_ISLENMIS_NAME`) yükler ve
`sharepoint_url`'i yazar; belge o andan itibaren karttan açılır. Arşive YAZAR (lokal
kurulum da gerçek arşive bağlıdır) — ayrıntı ve korumalar `yukle` docstring'inde.

    docker compose exec -T backend python scripts/arsiv_karar_ekle.py --yukle --pdf-dizini /tmp/kararlar
    docker compose exec -T backend python scripts/arsiv_karar_ekle.py --yukle --pdf-dizini /tmp/kararlar --apply
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modülleri için

import models

logger = logging.getLogger("arsiv_karar_ekle")

KAYNAK = "ARSIV_AKTARIM"
VARSAYILAN_CIKTI = "/tmp/arsiv_karar_ekle"
PARTI = 200

# sonuç etiketleri
EKLENDI, ZATEN_VAR, FOY_YOK, KART_SILINMIS, COK_KART, GIRDI_HATALI = (
    "EKLENDI", "ZATEN_VAR", "FOY_YOK", "KART_SILINMIS", "COK_KART", "GIRDI_HATALI")

# (kod, ad) — DB'de bugün kullanılan pad'siz yazım (CLAUDE.md "Doctype `_` padding")
TUR_GEREKCELI = ("GEREKCELIKRR", "Gerekçeli Karar")
TUR_ISTINAF = ("ISTINAFKRR", "İstinaf Kararı")
TUR_YARGITAY = ("YARGITAYKRR", "Yargıtay Kararı")
TUR_DANISTAY = ("DANISTAYKRR", "Danıştay Kararı")
TUR_AYM = ("AYMKRR", "Anayasa Mahkemesi Kararı")

_ESAS = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*/\s*(\d{1,7})(?!\d)")
_KATLA = str.maketrans("İıiŞşĞğÜüÖöÇçÂâÎîÛû", "IIISSGGUUOOCCAAIIUU")


def belge_turu(mahkeme_etiketi: Optional[str]) -> Tuple[str, str]:
    """Dosya adındaki mahkeme etiketi → (belge türü kodu, adı)."""
    k = (mahkeme_etiketi or "").upper()
    if k.startswith("DANISTAY"):
        return TUR_DANISTAY
    if k.startswith("YARGITAY"):
        return TUR_YARGITAY
    if "ANAYASA" in k or k.startswith("AYM"):
        return TUR_AYM
    if re.search(r"(^|_)(BAM|BIM)(_|$)", k):
        return TUR_ISTINAF
    return TUR_GEREKCELI


def esas_kumesi(s: Optional[str]) -> Set[str]:
    """'2022/091 E.; 2023/5' → {'2022/91', '2023/5'}; sırası yazılmamış esas atılır."""
    return {f"{yil}/{int(sira)}" for yil, sira in _ESAS.findall(s or "")}


def mahkeme_anahtari(s: Optional[str]) -> str:
    """Yazım farkını (boşluk, nokta, büyük/küçük, Türkçe harf) atan karşılaştırma anahtarı."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").translate(_KATLA).upper())


def tarih_coz(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def asama_bul(asamalar: Sequence[Any], esas: Optional[str], tarih: Optional[date],
              mahkeme: Optional[str]) -> Optional[Any]:
    """Künye → kartın TEK aşama kararı; tutmuyorsa ya da birden çok satır tutuyorsa None.

    Kademeler: esas + tarih → yalnız esas → tarih + mahkeme. Bir kademede birden çok satır
    varsa mahkeme adıyla daraltılır; yine birden çoksa bağ KURULMAZ (tahmin yok).
    """
    aranan = esas_kumesi(esas)
    m = mahkeme_anahtari(mahkeme)

    def tek(adaylar: List[Any]) -> Optional[Any]:
        if len(adaylar) > 1 and m:
            adaylar = [a for a in adaylar if mahkeme_anahtari(a.mahkeme) == m]
        return adaylar[0] if len(adaylar) == 1 else None

    esasli = [a for a in asamalar if aranan and esas_kumesi(a.esas_no) & aranan]
    if tarih:
        ikisi = [a for a in esasli if a.karar_tarihi == tarih]
        if ikisi:
            return tek(ikisi)
    if esasli:
        return tek(esasli)
    if tarih and m:
        return tek([a for a in asamalar if a.karar_tarihi == tarih and mahkeme_anahtari(a.mahkeme) == m])
    return None


@dataclass
class Satir:
    dosya: str
    sonuc: str
    kart_id: Optional[int] = None
    asama_karari_id: Optional[int] = None
    belge_turu_kodu: str = ""
    aciklama: str = ""


@dataclass
class KosuSonucu:
    satirlar: List[Satir] = field(default_factory=list)
    yazildi: bool = False

    def say(self) -> Counter:
        return Counter(s.sonuc for s in self.satirlar)

    @property
    def asamali(self) -> int:
        return sum(1 for s in self.satirlar if s.sonuc == EKLENDI and s.asama_karari_id)

    @property
    def kart_sayisi(self) -> int:
        return len({s.kart_id for s in self.satirlar if s.sonuc == EKLENDI})


def _kart_bul(db, foyler: Sequence[str]) -> Tuple[str, Optional[models.Case]]:
    satirlar = (db.query(models.CaseFoy.case_id).filter(models.CaseFoy.sistem_no.in_(list(foyler)))
                .distinct().all()) if foyler else []
    idler = sorted({r[0] for r in satirlar})
    if not idler:
        return FOY_YOK, None
    if len(idler) > 1:
        return COK_KART, None
    kart = db.get(models.Case, idler[0])
    if kart is None or kart.deleted_at is not None:
        return KART_SILINMIS, None
    return "", kart


def kos(fabrika: Callable[[], Any], liste: Iterable[Dict[str, str]], *, apply: bool = False,
        kim: Optional[str] = None, cikti_dizini: Optional[Path] = None) -> KosuSonucu:
    """Listeyi işler; `apply` ise 200 belgede bir commit, değilse sonda rollback.

    Kuru koşu da kayıtları oturumda AÇAR ve geri alır — rapor, apply'ın yapacağının
    birebir ön izlemesidir (unique kısıt dahil).
    """
    if apply and not kim:
        raise ValueError("--apply için --kim zorunlu")
    sonuc = KosuSonucu()
    db = fabrika()
    bekleyen = 0
    try:
        for g in liste:
            dosya = (g.get("dosya") or "").strip()
            sha = (g.get("sha256") or "").strip().lower()
            foyler = [f.strip() for f in (g.get("foyler") or "").split(";") if f.strip()]
            if not dosya or not re.fullmatch(r"[0-9a-f]{64}", sha):
                sonuc.satirlar.append(Satir(dosya, GIRDI_HATALI, aciklama="dosya adı ya da sha256 eksik / bozuk"))
                continue
            durum, kart = _kart_bul(db, foyler)
            if kart is None:
                sonuc.satirlar.append(Satir(dosya, durum, aciklama=";".join(foyler)))
                continue
            var = (db.query(models.CaseDocument.id)
                   .filter(models.CaseDocument.case_id == kart.id,
                           models.CaseDocument.dosya_sha256 == sha,
                           models.CaseDocument.deleted_at.is_(None)).first())
            if var:
                sonuc.satirlar.append(Satir(dosya, ZATEN_VAR, kart.id, aciklama=f"belge #{var[0]}"))
                continue
            tarih = tarih_coz(g.get("belge_tarihi"))
            asamalar = (db.query(models.CaseStageDecision)
                        .filter(models.CaseStageDecision.case_id == kart.id).all())
            asama = None
            if g.get("asama_esas") or g.get("asama_tarih"):
                asama = asama_bul(asamalar, g.get("asama_esas"), tarih_coz(g.get("asama_tarih")), g.get("asama_mahkeme"))
            if asama is None:
                asama = asama_bul(asamalar, g.get("esas_no"), tarih, None)
            kod, ad = belge_turu(g.get("mahkeme_etiketi"))
            db.add(models.CaseDocument(
                case_id=kart.id, original_filename=dosya, stored_filename=dosya,
                belge_turu_kodu=kod, belge_turu_adi=ad,
                ai_summary=" ".join(p for p in ("Büro karar arşivinden aktarıldı.", (g.get("aciklama") or "").strip()) if p),
                esas_no=(g.get("esas_no") or "").strip() or None,
                link_mode="LINKED", uploaded_by=f"{KAYNAK}:{kim}" if kim else KAYNAK,
                uploaded_at=(datetime(tarih.year, tarih.month, tarih.day, 9, tzinfo=timezone.utc)
                             if tarih else datetime.now(timezone.utc)),
                upload_status="pending", dosya_sha256=sha,
                asama_karari_id=asama.id if asama is not None else None,
            ))
            db.flush()
            sonuc.satirlar.append(Satir(dosya, EKLENDI, kart.id, asama.id if asama is not None else None, kod))
            bekleyen += 1
            if apply and bekleyen >= PARTI:
                db.commit()
                bekleyen = 0
        if apply:
            db.commit()
            sonuc.yazildi = True
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if cikti_dizini is not None:
        cikti_dizini.mkdir(parents=True, exist_ok=True)
        with open(cikti_dizini / "arsiv_karar_ekle_rapor.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["dosya", "sonuc", "kart_id", "asama_karari_id", "belge_turu_kodu", "aciklama"])
            for s in sonuc.satirlar:
                w.writerow([s.dosya, s.sonuc, s.kart_id or "", s.asama_karari_id or "", s.belge_turu_kodu, s.aciklama])
    return sonuc


# ─── Arşive yükleme (--yukle) ────────────────────────────────────────────────

YUKLENECEK, YUKLENDI, ARSIVDE_VARDI, AD_CAKISMASI, DOSYA_YOK, SHA_FARKLI, YUKLEME_HATASI = (
    "YUKLENECEK", "YUKLENDI", "ARSIVDE_VARDI", "AD_CAKISMASI", "DOSYA_YOK", "SHA_FARKLI", "YUKLEME_HATASI")
ARDISIK_HATA_SINIRI = 15


def arsiv_klasoru() -> str:
    return os.getenv("SHAREPOINT_FOLDER_ISLENMIS_NAME", "02_YEDEK_ARSIV")


def _dosya_sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as fh:
        for parca in iter(lambda: fh.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


@dataclass
class YuklemeSatiri:
    dosya: str
    sonuc: str
    belge_sayisi: int = 0
    aciklama: str = ""


@dataclass
class YuklemeSonucu:
    satirlar: List[YuklemeSatiri] = field(default_factory=list)
    yazildi: bool = False
    durduruldu: bool = False

    def say(self) -> Counter:
        return Counter(s.sonuc for s in self.satirlar)


def yukle(fabrika: Callable[[], Any], pdf_dizini: Path, *, apply: bool = False,
          mevcut: Optional[Callable[[str, str], Optional[Dict[str, Any]]]] = None,
          yukleyici: Optional[Callable[[str, str, str], Dict[str, Any]]] = None,
          is_parcacigi: int = 4, limit: Optional[int] = None,
          cikti_dizini: Optional[Path] = None) -> YuklemeSonucu:
    """Arşiv belgelerinin PDF'ini SharePoint arşivine yükler ve `sharepoint_url`'i yazar.

    Kapsam: bu script'in eklediği (`uploaded_by` `ARSIV_AKTARIM…`), URL'i boş, silinmemiş
    kayıtlar. Aynı dosya birden çok kartta kayıtlıysa BİR KEZ yüklenir. Dosya başına:

    1. yerel dosya var mı, parmak izi kayıttakiyle aynı mı (değilse yüklenmez);
    2. **arşivde aynı adda dosya var mı** — küçük dosya yüklemesi sormadan ezdiği için
       ÖNCE bakılır: boyutu aynıysa bizim önceki koşumuzdur (URL'i alınır, yeniden
       yüklenmez); boyutu farklıysa `AD_CAKISMASI`, dosyaya DOKUNULMAZ;
    3. yoksa yüklenir; URL kayda dosya başına commit'le yazılır (yarıda kesilen koşu
       kaldığı yerden sürer).

    Kuru koşu 1. ve 2. adımı koşar (arşive yalnız okuma), hiçbir şey yüklemez / yazmaz.
    `upload_queue` kullanılmaz: o yol `belge_islendi` bildirimi ve Hukukbot aktarımı
    üretir; burada ikisi de bilerek yok. Art arda 15 hata koşuyu durdurur.
    """
    if mevcut is None or yukleyici is None:
        from sharepoint.sharepoint_uploader_graph import get_file_meta_from_sharepoint, upload_file_to_sharepoint
        mevcut = mevcut or get_file_meta_from_sharepoint
        yukleyici = yukleyici or (lambda yol, ad, klasor: upload_file_to_sharepoint(yol, ad, klasor))
    klasor = arsiv_klasoru()
    sonuc = YuklemeSonucu()
    db = fabrika()
    try:
        kayitlar = (db.query(models.CaseDocument.id, models.CaseDocument.stored_filename, models.CaseDocument.dosya_sha256)
                    .filter(models.CaseDocument.uploaded_by.like(f"{KAYNAK}%"),
                            models.CaseDocument.sharepoint_url.is_(None),
                            models.CaseDocument.deleted_at.is_(None),
                            models.CaseDocument.dosya_sha256.isnot(None))
                    .order_by(models.CaseDocument.id).all())
    finally:
        db.close()      # ağ aşaması dakikalar sürer: açık transaction bırakılmaz (idle-in-transaction zaman aşımı)
    dosyalar: Dict[str, Tuple[str, List[int]]] = {}
    for belge_id, ad, sha in kayitlar:
        dosyalar.setdefault(ad, (sha, []))[1].append(belge_id)
    adlar = list(dosyalar)[:limit] if limit else list(dosyalar)

    def isle(ad: str) -> Tuple[str, str, Optional[str], str]:
        yol = pdf_dizini / ad
        if not yol.is_file():
            return ad, DOSYA_YOK, None, ""
        if _dosya_sha256(yol) != dosyalar[ad][0]:
            return ad, SHA_FARKLI, None, "yerel dosya kayıttaki parmak iziyle aynı değil"
        try:
            var = mevcut(klasor, ad)
            if var is not None:
                if int(var.get("size") or -1) == yol.stat().st_size:
                    return ad, ARSIVDE_VARDI, var.get("webUrl"), ""
                return ad, AD_CAKISMASI, None, f"arşivde aynı adda {var.get('size')} baytlık başka dosya var"
            if not apply:
                return ad, YUKLENECEK, None, ""
            url = (yukleyici(str(yol), ad, klasor) or {}).get("webUrl")
            if not url:
                return ad, YUKLEME_HATASI, None, "yanıtta webUrl yok"
            return ad, YUKLENDI, url, ""
        except Exception as e:      # tek dosyanın hatası koşuyu düşürmez; art arda hata durdurur
            return ad, YUKLEME_HATASI, None, f"{type(e).__name__}: {e}"[:300]

    ardisik = 0
    with ThreadPoolExecutor(max_workers=max(1, is_parcacigi)) as havuz:
        isler = [havuz.submit(isle, ad) for ad in adlar]
        for i, gelecek in enumerate(isler, 1):
            ad, durum, url, aciklama = gelecek.result()
            idler = dosyalar[ad][1]
            sonuc.satirlar.append(YuklemeSatiri(ad, durum, len(idler), aciklama))
            if apply and url and durum in (YUKLENDI, ARSIVDE_VARDI):
                yaz = fabrika()
                try:
                    (yaz.query(models.CaseDocument).filter(models.CaseDocument.id.in_(idler))
                     .update({"sharepoint_url": url, "upload_status": "uploaded"}, synchronize_session=False))
                    yaz.commit()
                finally:
                    yaz.close()
            ardisik = ardisik + 1 if durum == YUKLEME_HATASI else 0
            if ardisik >= ARDISIK_HATA_SINIRI:
                sonuc.durduruldu = True
                for kalan in isler[i:]:
                    kalan.cancel()
                logger.warning(f"Arşive yükleme DURDURULDU: art arda {ardisik} hata (son: {aciklama})")
                break
            if i % 250 == 0:
                logger.info(f"arşive yükleme: {i}/{len(adlar)} dosya — {dict(sonuc.say())}")
    sonuc.yazildi = apply
    if cikti_dizini is not None:
        cikti_dizini.mkdir(parents=True, exist_ok=True)
        with open(cikti_dizini / "arsiv_karar_yukle_rapor.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["dosya", "sonuc", "belge_sayisi", "aciklama"])
            for s in sonuc.satirlar:
                w.writerow([s.dosya, s.sonuc, s.belge_sayisi, s.aciklama])
    return sonuc


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Büro karar arşivini kartlara arşiv belgesi olarak ekler (05.10.2026)")
    parser.add_argument("--liste", help="Eşleştirme listesi (CSV) — belge kaydı açar")
    parser.add_argument("--yukle", action="store_true", help="Eklenmiş arşiv belgelerinin PDF'ini SharePoint arşivine yükle")
    parser.add_argument("--pdf-dizini", help="PDF'lerin bulunduğu dizin (--yukle ile zorunlu)")
    parser.add_argument("--limit", type=int, help="--yukle: en çok bu kadar dosya")
    parser.add_argument("--apply", action="store_true", help="Yaz / yükle (varsayılan kuru koşu)")
    parser.add_argument("--kim", help="Aktarımı yapan (--liste --apply ile zorunlu)")
    parser.add_argument("--cikti-dizini", default=VARSAYILAN_CIKTI, help=f"Rapor dizini (varsayılan {VARSAYILAN_CIKTI})")
    args = parser.parse_args(argv)
    if args.yukle == bool(args.liste):
        parser.error("--liste ya da --yukle (yalnız biri) verilmeli")
    if args.yukle and not args.pdf_dizini:
        parser.error("--yukle için --pdf-dizini zorunlu")
    if args.liste and args.apply and not args.kim:
        parser.error("--apply için --kim zorunlu")

    from database import SessionLocal
    from logging_setup import configure_logging   # Faz 2-B bekçisi: basicConfig YOK

    configure_logging()

    if args.yukle:
        ys = yukle(SessionLocal, Path(args.pdf_dizini), apply=args.apply, limit=args.limit,
                   cikti_dizini=Path(args.cikti_dizini))
        print(f"{'YÜKLENDİ' if ys.yazildi else 'KURU KOŞU (yüklenmedi)'} — {len(ys.satirlar)} dosya, klasör {arsiv_klasoru()}"
              + (" — DURDURULDU (art arda hata)" if ys.durduruldu else ""))
        for etiket, adet in sorted(ys.say().items()):
            print(f"  {etiket:15s} {adet}")
        print(f"  rapor: {Path(args.cikti_dizini) / 'arsiv_karar_yukle_rapor.csv'}")
        return 1 if ys.durduruldu else 0

    with open(args.liste, encoding="utf-8-sig", newline="") as fh:
        liste = list(csv.DictReader(fh))
    sonuc = kos(SessionLocal, liste, apply=args.apply, kim=args.kim, cikti_dizini=Path(args.cikti_dizini))
    say = sonuc.say()
    print(f"{'UYGULANDI' if sonuc.yazildi else 'KURU KOŞU (yazılmadı)'} — liste: {len(liste)} satır")
    for etiket in (EKLENDI, ZATEN_VAR, FOY_YOK, KART_SILINMIS, COK_KART, GIRDI_HATALI):
        print(f"  {etiket:14s} {say.get(etiket, 0)}")
    print(f"  eklenenlerin {sonuc.asamali} tanesi aşama kararına bağlı; {sonuc.kart_sayisi} kart")
    print(f"  rapor: {Path(args.cikti_dizini) / 'arsiv_karar_ekle_rapor.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
