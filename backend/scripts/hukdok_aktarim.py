#!/usr/bin/env python3
"""HUKDOK aktarımının ÇEKİRDEK yazma yolu (G064) — iskelet + kuru koşu.

Tam 68 sütunluk eşleme BU TURUN İŞİ DEĞİL (final export + CEVAP xlsx geldikten
sonra ayrı plan turu). Burada iskelet kurulur ve KANITLANIR: SistemNo anahtarlı
idempotent upsert, satır bazlı hata izolasyonu, kuru koşu, belge envanter
denkliği, kardeş-föy çelişki raporu.

    docker compose exec -T backend python scripts/hukdok_aktarim.py \\
        --input /app/data/teslim.xlsx --dry-run
    docker compose exec -T backend python scripts/hukdok_aktarim.py \\
        --input /app/data/teslim.xlsx --limit 50

İşletim modeli (FAZ F gereksinim belgesi §0): aktarım bir OLAY DEĞİL, TEKRAR
EDEN bir süreçtir — göz hastalıkları dilimi partiler hâlinde gelecek, ayrıca
dört düzeltme listesi yolda. "Aynı girdiyle iki kez koşulduğunda kayıt sayısı
değişmez" bu yüzden süs değil, işletim modelinin kendisi.

Pazarlıksız kurallar
--------------------
* **SistemNo idempotency anahtarıdır** (`case_foys`, G063). İkinci koşu satır
  ikilemez; değişmeyen alan için `case_history` satırı DA yazılmaz — yoksa
  "değişiklik yok" koşusu tarihçeyi şişirir ve idempotentlik ölçülemez hâle
  gelirdi.
* **Mevcut kartta YALNIZ UPDATE.** Kart DELETE+INSERT yasak; `case_parties`
  satırları toptan silinip yeniden yazılmaz. Sebep şemada: `case_documents.
  case_party_id` FK'sı `ondelete=SET NULL` (models.py:770) — toptan taraf
  silme belge-taraf bağını HATA VERMEDEN koparır. Koşu öncesi/sonrası belge
  envanteri (`services/belge_envanteri.py`) DENK çıkmak zorundadır; denk
  değilse koşu KENDİNİ GERİ ALIR (kapı commit'ten ÖNCE ölçer — hasar kalıcı
  olmadan durdurulur) ve NONZERO çıkar.
* **Satır hatası SAVEPOINT ile izole** (temizlik planı §8: `rollback` değil).
  Hatalı satır kısmen yazılmış olabilir (föy INSERT'i alan doğrulamasından
  ÖNCE gelir); savepoint o kısmı da geri alır. Parti DÜŞMEZ, satır rapora
  düşer. Yarım föy yazıp devam etmek, düzeltme listesiyle zaten geri gelecek
  bir satır için sessiz veri bozulması olurdu.
* **`None` = "bu teslimde yok", "boşalt" DEĞİL** (foy_map ile aynı sözleşme):
  partili teslimde eksik sütun mevcut değeri silmez. Alan boşaltma bu turda
  YOK — açık bir düzeltme yolu gerektirir.
* **Kart YARATILMAZ.** Bu ağırlıkla bir UPDATE dalgasıdır (eşleştirme köprüsü
  DosyaNo↔`klasor_no_2` %97,4); eşleşmeyen satır rapora düşer. Kart açmak
  ofis dosya numarasını SharePoint sayacından ATOMİK tahsis etmeyi gerektirir
  (CLAUDE.md belge akışı) — çevrimdışı bir aktarım scriptinin işi değildir.
* **İlerleme imleci YOK, gerekmiyor**: işlenmiş SistemNo'lar `case_foys`'ta
  yaşar; yarım kalan koşuyu tekrar başlatmak bedava (idempotentlik).
* `statement_timeout` koşu süresince açıkça yükseltilir (§8 madde 6): engine
  30 sn ile bağlanır, toplu yazma bunu meşru aşar.

Bu turda YAZILAN kart alanları (DAR küme — iskeleti kanıtlamaya yeter)
---------------------------------------------------------------------
`arsiv_tarihi` (tarih/D5 yer tutucu kuralı) · `islah_tutari` (TR biçimli sayı)
· `tibbi_olay` (serbest metin/kırpma). Üçü de FARKLI bir dönüşüm sınıfını
kanıtlar; dördüncüsü aynı sınıfların kopyası olurdu. Karar künyesi
(`karar_no`/`karar_tarihi`) BİLİNÇLİ YAZILMAZ — o kolonların tek yazma yolu
`managers/stage_decisions.py`ın aşama fotoğrafıdır (G062); buradan yazmak
ikinci bir yazıcı doğururdu. Künye yalnız OKUNUR ve kardeş-föy çelişki
raporunu üretir. `cases.sistem_no`/`cases.tku_no` da yazılmaz (nihai
tekilleştirme tam eşleme turunun işi).

`scripts/import_excel_cases.py` KULLANILMAZ ve çağrılmaz (temizlik planı §8:
idempotent değil, hata yolunda sessiz veri kaybı, `-2` mükerrer üretimi).
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# E402 (import'tan önce sys.path kurulumu) scripts/* için pyproject'te bilinçli
# olarak kapalıdır — script tek başına da koşabilmeli.
import models
from managers import case_manager, foy_map
from managers.reference_lists import tr_upper
from required_fields import AKTARIM_SOURCE_PREFIX
from services import belge_envanteri

logger = logging.getLogger("HukdokAktarim")

# ─── Çıkış kodları ───────────────────────────────────────────────────────────
# En ağırı kazanır. 2 belge koruma şartının ihlalidir: koşu geri alınmıştır.
CIKIS_TAMAM = 0
CIKIS_SATIR_HATASI = 1
CIKIS_ENVANTER = 2
CIKIS_GIRDI = 3

# Engine 30 sn statement_timeout ile bağlanır (database.py); toplu yazma bunu
# meşru aşar. Koşu süresince açıkça yükseltilir (§8 madde 6).
VARSAYILAN_TIMEOUT_MS = 600_000

DEGISTIREN = "hukdok_aktarim"

# ─── Kaynak sütunlar ─────────────────────────────────────────────────────────
# Aday adlar; ilk eşleşen kullanılır. Başlık karşılaştırması aksan ve boşluk
# duyarsızdır (_baslik_anahtari) — teslim paketleri arasında "Islah Tutarı" /
# "İslah Tutarı" gibi yazım farkları görülüyor. TAM 68 sütunluk eşleme bu turun
# işi DEĞİLDİR; buradaki küme yalnız çekirdeği besler.
SUTUN_ADAYLARI: Dict[str, Tuple[str, ...]] = {
    "sistem_no":    ("SistemNo", "Sistem No"),
    "tku_no":       ("TKU", "TKU No", "TKU No."),
    "hasar_no":     ("Hasar No", "Hasar Numarası"),
    "dosya_no":     ("Dosya No", "DosyaNo", "Klasör No.2"),
    "arsiv_tarihi": ("Arşiv Tarihi",),
    "islah_tutari": ("Islah Tutarı", "İslah Tutarı"),
    "tibbi_olay":   ("Tıbbi Olay",),
    "karar_no":     ("Karar No",),
    "karar_tarihi": ("Karar Tarihi",),
}

# Satırın kimliği: bu sütun yoksa dosya bu script için okunamaz.
ZORUNLU_SUTUNLAR = ("sistem_no",)

# Kardeş föylerde uyuşmazlığı raporlanan künye alanları (yazılmaz, okunur).
KUNYE_ALANLARI = ("karar_no", "karar_tarihi")

# D5 — yer tutucu değerler NULL'a çevrilir (metin biçimli tarihler dahil);
# tarih ve sayı yollarının ORTAK sözlüğü, "-" bir alanda yer tutucuysa
# diğerinde de yer tutucudur.
YER_TUTUCULAR = frozenset({"-", "--", "—", "?", "YOK", "BELİRSİZ", "BOŞ", "N/A", "NA"})
YER_TUTUCU_YIL = 1900

_TARIH_BICIMLERI = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")

# Çok değerli dosya numarası ayracı (`klasor_no_2`: "624.001.00;3.137.00").
# Numaraların KENDİSİ nokta içerir — ayraç olarak yalnız ';' ve satır sonu
# kabul edilir; virgül/nokta eklemek numaraları ortadan bölerdi.
_AYRAC = re.compile(r"[;\r\n]+")

# Kart alanlarının kolon sınırları modelden okunur, elle tekrarlanmaz
# (foy_map._LIMITS gerekçesi: şema büyürse kod kendiliğinden uyar).
_KART_LIMITLERI: Dict[str, int] = {}
for _kolon in models.Case.__table__.columns:
    _uzunluk = getattr(_kolon.type, "length", None)
    if _uzunluk:
        _KART_LIMITLERI[_kolon.name] = _uzunluk


class AktarimHatasi(Exception):
    """Koşunun tamamını durduran girdi hatası (dosya/sayfa/başlık)."""


class SatirHatasi(Exception):
    """TEK satırı düşüren VERİ hatası — parti devam eder, satır rapora düşer.

    İnsan müdahalesi gerektirir (düzeltme listesi konusu); koşuyu NONZERO
    yapar.
    """


class SatirAtlandi(SatirHatasi):
    """Satır BEKLENEN sebeple işlenmedi (kart yok) — koşuyu kırmızıya çekmez.

    Eşleştirme köprüsü %97,4; kalan satırların kartı henüz yok ve bu turda
    kart YARATILMIYOR. Beklenen bir sonucu "hata" saymak, gerçek hataları
    gürültüde boğardı — ama satır yine de rapora düşer.
    """


@dataclass
class HamSatir:
    satir_no: int                      # xlsx'teki 1 tabanlı satır numarası
    degerler: Dict[str, Any]


@dataclass
class RaporSatiri:
    satir_no: int
    sistem_no: str
    dosya_no: str
    tur: str                           # HATA | ATLANDI
    sebep: str


@dataclass
class Celiski:
    kume: str                          # KART | TKU
    kume_anahtari: str
    alan: str
    degerler: str                      # "SSTMN-1=2018/143 | SSTMN-2=2016/768"


@dataclass
class AktarimSonucu:
    okunan: int = 0
    islenen: int = 0
    foy_yeni: int = 0
    foy_guncellenen: int = 0
    alan_degisikligi: int = 0
    kart_degisen: int = 0
    atlanan: int = 0
    dry_run: bool = False
    yazildi: bool = False              # commit edildi mi?
    kaynak_imzasi: str = ""
    rapor_satirlari: List[RaporSatiri] = field(default_factory=list)
    celiskiler: List[Celiski] = field(default_factory=list)
    envanter_once: Optional[belge_envanteri.BelgeEnvanteri] = None
    envanter_sonra: Optional[belge_envanteri.BelgeEnvanteri] = None
    envanter_farki: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    raporlar: List[Path] = field(default_factory=list)

    @property
    def hatalar(self) -> List[RaporSatiri]:
        return [r for r in self.rapor_satirlari if r.tur == "HATA"]

    @property
    def cikis_kodu(self) -> int:
        if self.envanter_farki:
            return CIKIS_ENVANTER
        return CIKIS_SATIR_HATASI if self.hatalar else CIKIS_TAMAM


# ═══════════════════════════════════════════════════════════════════════════
# Normalizasyon
# ═══════════════════════════════════════════════════════════════════════════

def _baslik_anahtari(deger: Any) -> str:
    """Başlık karşılaştırma anahtarı: TR büyük harf + aksan sadeleştirme +
    yalnız harf/rakam. "Arşiv Tarihi" ile "ARSIV TARIHI" aynı sütundur."""
    buyuk = tr_upper(str(deger or ""))
    ayrik = unicodedata.normalize("NFD", buyuk)
    sade = "".join(ch for ch in ayrik if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]", "", sade)


def _metin(deger: Any) -> Optional[str]:
    """Boşluk-normalize metin; boş hücre None ("bu teslimde yok")."""
    if deger is None:
        return None
    if isinstance(deger, (datetime, date)):
        return deger.isoformat()
    metin = " ".join(str(deger).split())
    return metin or None


def _kirp(deger: Optional[str], kolon: str) -> Optional[str]:
    """Kimlik OLMAYAN metni kolon sınırına kırpar (deneme-düzeyi → WARNING)."""
    if deger is None:
        return None
    sinir = _KART_LIMITLERI.get(kolon)
    if sinir and len(deger) > sinir:
        logger.warning(f"cases.{kolon} kolon sınırına kırpıldı (>{sinir}): {deger[:60]!r}…")
        return deger[:sinir]
    return deger


def _tarih(deger: Any, alan: str) -> Optional[date]:
    """D5 — yer tutucu tarihler NULL; çözümlenemeyen tarih SATIRI DÜŞÜRÜR.

    Yer tutucular (01.01.1900, metin biçimliler, gelecek tarihler) bilinen ve
    ölçülmüş sınıflardır; sessizce NULL'lanırlar. Çözümlenemeyen bir tarih ise
    bilinmeyen bir kusurdur: sessizce NULL'lamak onu karşı tarafın düzeltme
    listesinden gizlerdi.
    """
    if deger is None:
        return None
    if isinstance(deger, datetime):
        deger = deger.date()
    if isinstance(deger, date):
        return _tarih_suz(deger, alan)

    ham = " ".join(str(deger).split())
    if not ham:
        return None
    if tr_upper(ham) in YER_TUTUCULAR:
        logger.warning(f"{alan}: yer tutucu tarih NULL'landı ({ham!r})")
        return None
    for bicim in _TARIH_BICIMLERI:
        try:
            return _tarih_suz(datetime.strptime(ham, bicim).date(), alan)
        except ValueError:
            continue
    raise SatirHatasi(f"{alan} çözümlenemedi: {ham!r}")


def _tarih_suz(deger: date, alan: str) -> Optional[date]:
    """D5'in tarih-nesnesi tarafı: 1900 ve öncesi + gelecek tarih = yer tutucu."""
    if deger.year <= YER_TUTUCU_YIL:
        logger.warning(f"{alan}: yer tutucu tarih NULL'landı ({deger.isoformat()})")
        return None
    if deger > date.today():
        logger.warning(f"{alan}: gelecek tarih NULL'landı ({deger.isoformat()})")
        return None
    return deger


def _sayi(deger: Any, alan: str) -> Optional[Decimal]:
    """TR biçimli parasal değer → Decimal. Çözümlenemeyen SATIRI DÜŞÜRÜR.

    "12.345,67" (nokta binlik, virgül ondalık) ile "12345.67" birlikte
    yaşıyor; ayrım virgülün varlığıyla ve binlik kalıbıyla yapılır.
    """
    if deger is None:
        return None
    if isinstance(deger, bool):                       # openpyxl TRUE/FALSE hücresi
        raise SatirHatasi(f"{alan} sayı değil: {deger!r}")
    if isinstance(deger, (int, float, Decimal)):
        return _sayi_suz(Decimal(str(deger)), alan)

    ham = " ".join(str(deger).split())
    if not ham:
        return None
    temiz = ham.replace("₺", "").replace("TL", "").replace(" ", "").strip()
    if not temiz or tr_upper(temiz) in YER_TUTUCULAR:
        return None
    if "," in temiz:
        temiz = temiz.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", temiz):    # 12.345 → binlik ayracı
        temiz = temiz.replace(".", "")
    try:
        return _sayi_suz(Decimal(temiz), alan)
    except InvalidOperation:
        raise SatirHatasi(f"{alan} çözümlenemedi: {ham!r}") from None


def _sayi_suz(deger: Decimal, alan: str) -> Decimal:
    if deger < 0:
        raise SatirHatasi(f"{alan} negatif olamaz: {deger}")
    return deger


def _tarih_yumusak(deger: Any, alan: str) -> str:
    """Çelişki raporu için tarih anahtarı — ÇÖZÜLEMEZSE ham metin.

    Rapor "iki kardeş föy aynı şeyi mi söylüyor?" sorusunu sorar; çözümlenemeyen
    bir künye tarihi de karşılaştırılabilir bir cevaptır (ve satırı düşürmez —
    künye alanları YAZILMIYOR).
    """
    try:
        cozulen = _tarih(deger, alan)
    except SatirHatasi:
        return _metin(deger) or ""
    return cozulen.isoformat() if cozulen else ""


# Kart alanı → (kaynak sütun anahtarı, dönüştürücü)
KART_ALANLARI: Dict[str, Tuple[str, Callable[[Any, str], Any]]] = {
    "arsiv_tarihi": ("arsiv_tarihi", _tarih),
    "islah_tutari": ("islah_tutari", _sayi),
    "tibbi_olay":   ("tibbi_olay", lambda d, alan: _kirp(_metin(d), alan)),
}


# ═══════════════════════════════════════════════════════════════════════════
# Girdi okuma
# ═══════════════════════════════════════════════════════════════════════════

def xlsx_oku(yol: Path, *, sheet: Optional[str] = None,
             limit: Optional[int] = None) -> Tuple[List[HamSatir], Dict[str, str]]:
    """Teslim paketini okur → (satırlar, {alan: bulunan başlık}).

    Gerçek teslim paketi REPOYA GİRMEZ (A.2 dersi: gerçek müvekkil verisi
    OneDrive/repo dışında kalır) — dosya yalnız çalışma zamanında `--input`
    ile okunur; testler openpyxl ile SENTETİK mini paket üretir.
    """
    import openpyxl

    if not yol.exists():
        raise AktarimHatasi(f"Girdi dosyası yok: {yol}")

    wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
    try:
        if sheet is not None and sheet not in wb.sheetnames:
            raise AktarimHatasi(f"Sayfa yok: {sheet!r} (mevcut: {', '.join(wb.sheetnames)})")
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        satir_akisi = ws.iter_rows(values_only=True)
        baslik_satiri = next(satir_akisi, None)
        if baslik_satiri is None:
            raise AktarimHatasi(f"Girdi boş: {yol}")

        indeksler, bulunanlar = _sutun_indeksleri(baslik_satiri)
        eksik = [a for a in ZORUNLU_SUTUNLAR if a not in indeksler]
        if eksik:
            raise AktarimHatasi(
                f"Zorunlu sütun(lar) bulunamadı: {', '.join(eksik)} — "
                f"okunan başlıklar: {', '.join(str(b) for b in baslik_satiri if b)}"
            )

        satirlar: List[HamSatir] = []
        for sira, ham in enumerate(satir_akisi, start=2):
            if limit is not None and len(satirlar) >= limit:
                break                         # sınır ÖNCE bakılır: --limit 0 = hiç satır
            if ham is None or all(_metin(h) is None for h in ham):
                continue                      # tamamen boş satır: sessizce atla
            satirlar.append(HamSatir(
                satir_no=sira,
                degerler={
                    alan: (ham[i] if i < len(ham) else None)
                    for alan, i in indeksler.items()
                },
            ))
        return satirlar, bulunanlar
    finally:
        wb.close()


def _sutun_indeksleri(baslik_satiri: Sequence[Any]) -> Tuple[Dict[str, int], Dict[str, str]]:
    """{alan: sütun indeksi} + {alan: dosyada bulunan başlık}."""
    dosyadaki = {}
    for i, ham in enumerate(baslik_satiri):
        anahtar = _baslik_anahtari(ham)
        if anahtar and anahtar not in dosyadaki:
            dosyadaki[anahtar] = (i, str(ham).strip())

    indeksler: Dict[str, int] = {}
    bulunanlar: Dict[str, str] = {}
    for alan, adaylar in SUTUN_ADAYLARI.items():
        for aday in adaylar:
            eslesme = dosyadaki.get(_baslik_anahtari(aday))
            if eslesme:
                indeksler[alan], bulunanlar[alan] = eslesme[0], eslesme[1]
                break
    return indeksler, bulunanlar


# ═══════════════════════════════════════════════════════════════════════════
# Kart eşleştirme
# ═══════════════════════════════════════════════════════════════════════════

def _dosya_no_haritasi(db) -> Dict[str, List[int]]:
    """{normalize dosya no parçası: [kart id]} — köprü TEK sorguda okunur.

    Satır başına SELECT yapmak 8.409 satırda tam tarama demekti (`klasor_no_2`
    trigram index'i G042'de düştü). Mükerrer anahtar OLAĞANDIR (14.317 dolu /
    14.204 distinct → 112 grup); liste hâlinde tutulur, çok eşleşen satır
    "belirsiz eşleşme" ile rapora düşer — yanlış karta yazmaktansa.
    """
    harita: Dict[str, List[int]] = {}
    sorgu = (
        db.query(models.Case.id, models.Case.klasor_no_2)
        .filter(models.Case.klasor_no_2.isnot(None), models.Case.deleted_at.is_(None))
        .order_by(models.Case.id)
    )
    for case_id, klasor in sorgu.yield_per(1000):
        for parca in _dosya_no_parcalari(klasor):
            harita.setdefault(parca, []).append(case_id)
    return harita


def _dosya_no_parcalari(deger: Any) -> List[str]:
    """Çok değerli dosya numarasını parçalara ayırır (mükerrersiz, sıralı).

    `klasor_no_2` ÇOK DEĞERLİDİR: eski dosya numaraları ';' ile birleşik
    tutulur ("624.001.00;3.137.00"). Lokal prod kopyasında ölçüm (2026-08-19):
    14.317 dolu kaydın **1.267'si** çok değerli — ve bunlar tam da birleşik
    kartlar, yani bu görevin çekirdek vakası (1.211 kart 2+ föyü birleşik
    taşıyor). Tam-değer eşleşmesi o kartların hepsini ISKALARDI. Aynı ayrıştırma
    teslim tarafına da uygulanır (simetri): paket de birleşik yazabilir.
    """
    parcalar: List[str] = []
    for ham in _AYRAC.split(_metin(deger) or ""):
        anahtar = _eslesme_anahtari(ham)
        if anahtar and anahtar not in parcalar:
            parcalar.append(anahtar)
    return parcalar


def _eslesme_anahtari(deger: Any) -> str:
    """Dosya No ↔ klasor_no_2 karşılaştırma anahtarı (boşluk + harf duyarsız)."""
    return tr_upper(_metin(deger) or "")


# ═══════════════════════════════════════════════════════════════════════════
# Satır işleme
# ═══════════════════════════════════════════════════════════════════════════

def _kart_coz(db, satir: HamSatir, foy_haritasi: Dict[str, int],
              dosya_haritasi: Dict[str, List[int]], sistem_no: str) -> models.Case:
    """Satırın kartını bulur. Bulunamazsa SatirHatasi — kart YARATILMAZ."""
    case_id = foy_haritasi.get(sistem_no)
    if case_id is None:
        parcalar = _dosya_no_parcalari(satir.degerler.get("dosya_no"))
        if not parcalar:
            raise SatirHatasi("Dosya No boş ve föy kaydı yok — kart eşleştirilemedi")
        gosterim = "/".join(parcalar)
        adaylar: List[int] = []
        for parca in parcalar:
            for aday in dosya_haritasi.get(parca) or []:
                if aday not in adaylar:
                    adaylar.append(aday)
        if not adaylar:
            raise SatirAtlandi(
                f"Kart bulunamadı (Dosya No {gosterim!r} klasor_no_2 ile eşleşmiyor)"
            )
        if len(adaylar) > 1:
            raise SatirHatasi(
                f"Belirsiz eşleşme: Dosya No {gosterim!r} {len(adaylar)} kartla eşleşiyor "
                f"({', '.join(str(a) for a in adaylar[:5])})"
            )
        case_id = adaylar[0]

    case = db.get(models.Case, case_id)
    if case is None or case.deleted_at is not None:
        raise SatirHatasi(f"Kart {case_id} yok ya da silinmiş")
    return case


def _kart_alanlarini_yaz(db, case: models.Case, satir: HamSatir,
                         source: str) -> List[str]:
    """DAR alan kümesini kartın ÜZERİNE yazar (UPDATE-in-place); değişenleri döner.

    Değişmeyen alan için ne UPDATE ne `case_history` satırı üretilir — ikinci
    koşunun "0 değişiklik" kabul kriteri buna dayanır. `None` gelen alan
    KORUNUR (partili teslimde eksik sütun mevcut değeri silmez).
    """
    degisenler: List[str] = []
    for alan, (kaynak, donustur) in KART_ALANLARI.items():
        yeni = donustur(satir.degerler.get(kaynak), alan)
        if yeni is None:
            continue
        eski = getattr(case, alan)
        if eski == yeni:
            continue
        setattr(case, alan, yeni)
        db.add(models.CaseHistory(
            case_id=case.id, field_name=alan,
            old_value=_gecmis_metni(eski), new_value=_gecmis_metni(yeni),
            changed_by=DEGISTIREN, source=source,
        ))
        degisenler.append(alan)
    return degisenler


def _gecmis_metni(deger: Any) -> Optional[str]:
    if deger is None:
        return None
    if isinstance(deger, (date, datetime)):
        return deger.isoformat()
    return str(deger)


def _satiri_isle(db, satir: HamSatir, *, foy_haritasi: Dict[str, int],
                 dosya_haritasi: Dict[str, List[int]], source: str,
                 foy_source: str, sonuc: AktarimSonucu) -> int:
    """TEK satırın işi (kart id'sini döner) — çağıran SAVEPOINT içinde çağırır.

    SIRA ÖNEMLİ: föy upsert'i alan doğrulamasından ÖNCE gelir; bozuk bir alan
    savepoint'i geri alırken föyü de geri alır. Yarım föy (kimlik yazılmış,
    veri yazılmamış) bırakmak, düzeltme listesiyle zaten geri gelecek bir satır
    için sessiz bozulma olurdu.
    """
    sistem_no = _metin(satir.degerler.get("sistem_no"))
    if not sistem_no:
        raise SatirHatasi("SistemNo boş (föyün kimliği)")

    case = _kart_coz(db, satir, foy_haritasi, dosya_haritasi, sistem_no)
    yeni_foy = foy_map.get_foy(db, sistem_no) is None

    foy_map.upsert_foy(
        db, case,
        sistem_no=sistem_no,
        tku_no=_metin(satir.degerler.get("tku_no")),
        hasar_no=_metin(satir.degerler.get("hasar_no")),
        source=foy_source,
    )

    degisenler = _kart_alanlarini_yaz(db, case, satir, source)

    if yeni_foy:
        # Föyün kartla EŞLENMESİ de bir değişikliktir; provenance imzası
        # (D8/K1) yalnız alan değişikliğine bağlı kalırsa, hiçbir alanı
        # değişmeyen aktarım kartı "elle açılmış" kovada görünürdü.
        db.add(models.CaseHistory(
            case_id=case.id, field_name="case_foys.sistem_no",
            old_value=None, new_value=sistem_no,
            changed_by=DEGISTIREN, source=source,
        ))
        sonuc.foy_yeni += 1
    else:
        sonuc.foy_guncellenen += 1

    if degisenler or yeni_foy:
        # Türetilmiş eksik-alan kovasını TEK yazma yolundan tazele (D8):
        # aktarım imzası yeni düştüyse kayıt AKTARIM kovasına geçmeli.
        case_manager.refresh_missing_required(db, case)
    if degisenler:
        sonuc.alan_degisikligi += len(degisenler)
        sonuc.kart_degisen += 1

    sonuc.islenen += 1
    return cast(int, case.id)


# ═══════════════════════════════════════════════════════════════════════════
# Kardeş föy çelişki raporu
# ═══════════════════════════════════════════════════════════════════════════

def celiskileri_bul(kayitlar: Sequence[Dict[str, Any]]) -> List[Celiski]:
    """Aynı kart (yoksa aynı TKU) altındaki föylerde künye uyuşmazlıkları.

    Tasarım paketinin VAKALAR kanıtı: id-7189 K.2018/143 ile id-7190
    K.2016/768 aynı olayın iki föyü ama karar künyeleri farklı — kartta künye
    TEK SLOT olduğu için biri diğerini ezerdi. Bu satırlar
    `dogrulama_durumu = BELIRSIZ` ile işaretlenmeye ADAYDIR; işaretleme bu
    turda YOK, rapor üretimi yeterli (görev tanımı).

    Kart çözülemeyen satırlar TKU ile gruplanır: eşleşmemiş satırların
    çelişkisi de karşı tarafa borçlu olduğumuz bir bulgudur.
    """
    gruplar: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for kayit in kayitlar:
        if kayit.get("case_id"):
            anahtar = ("KART", str(kayit["case_id"]))
        elif kayit.get("tku_no"):
            anahtar = ("TKU", str(kayit["tku_no"]))
        else:
            continue
        gruplar.setdefault(anahtar, []).append(kayit)

    celiskiler: List[Celiski] = []
    for (kume, kume_anahtari), uyeler in sorted(gruplar.items()):
        if len(uyeler) < 2:
            continue
        for alan in KUNYE_ALANLARI:
            dolu = [(u["sistem_no"], u.get(alan) or "") for u in uyeler if u.get(alan)]
            if len({d for _, d in dolu}) > 1:
                celiskiler.append(Celiski(
                    kume=kume, kume_anahtari=kume_anahtari, alan=alan,
                    degerler=" | ".join(f"{s}={d}" for s, d in sorted(dolu)),
                ))
    return celiskiler


# ═══════════════════════════════════════════════════════════════════════════
# Koşu
# ═══════════════════════════════════════════════════════════════════════════

def _statement_timeout_yukselt(db, ms: int) -> bool:
    """Koşu süresince statement_timeout'u yükseltir (yalnız Postgres).

    `SET` bind parametresi almaz; `set_config` alır (üçüncü argüman is_local
    = false: oturum boyu). sqlite birim koşusunda sessizce atlanır.
    """
    if ms <= 0 or db.get_bind().dialect.name != "postgresql":
        return False
    db.execute(text("SELECT set_config('statement_timeout', :ms, false)"), {"ms": str(ms)})
    logger.info(f"statement_timeout koşu için {ms} ms'e yükseltildi")
    return True


def aktarimi_kos(session_factory, *, girdi: Path, sheet: Optional[str] = None,
                 limit: Optional[int] = None, dry_run: bool = False,
                 source: Optional[str] = None, rapor_dizini: Optional[Path] = None,
                 statement_timeout_ms: int = VARSAYILAN_TIMEOUT_MS) -> AktarimSonucu:
    """Çekirdek akış: oku → normalize → föy upsert → kart alanları → raporlar.

    TEK transaction, TEK commit: belge envanteri kapısı commit'ten ÖNCE ölçer,
    parti başına commit o kapıyı bölerdi. Kapı kırmızıysa (ya da `dry_run`)
    koşu tamamen geri alınır ve NONZERO döner.
    """
    girdi = Path(girdi)
    satirlar, bulunan_basliklar = xlsx_oku(girdi, sheet=sheet, limit=limit)
    kaynak_imzasi = source or f"{AKTARIM_SOURCE_PREFIX}_{girdi.name}"
    foy_source = kaynak_imzasi[:100]
    if len(kaynak_imzasi) > 100:
        logger.warning(
            f"Föy kaynağı 100 karaktere kırpıldı: {kaynak_imzasi!r} → {foy_source!r}"
        )

    sonuc = AktarimSonucu(okunan=len(satirlar), dry_run=dry_run,
                          kaynak_imzasi=kaynak_imzasi)
    logger.info(
        f"Aktarım başlıyor: {girdi.name} · {len(satirlar)} satır · "
        f"{'KURU KOŞU' if dry_run else 'YAZMA'} · bulunan sütunlar: "
        f"{', '.join(sorted(bulunan_basliklar))}"
    )

    db = session_factory()
    try:
        _statement_timeout_yukselt(db, statement_timeout_ms)
        sonuc.envanter_once = belge_envanteri.snapshot(db)

        foy_haritasi = foy_map.map_sistem_no_to_case(
            db, [_metin(s.degerler.get("sistem_no")) for s in satirlar]
        )
        dosya_haritasi = _dosya_no_haritasi(db)
        kunye_kayitlari: List[Dict[str, Any]] = []

        for satir in satirlar:
            sistem_no = _metin(satir.degerler.get("sistem_no")) or ""
            try:
                with db.begin_nested():
                    case_id = _satiri_isle(
                        db, satir,
                        foy_haritasi=foy_haritasi, dosya_haritasi=dosya_haritasi,
                        source=kaynak_imzasi, foy_source=foy_source, sonuc=sonuc,
                    )
            except SatirHatasi as exc:
                # Savepoint geri alındı; bellekteki (flush edilmemiş) hâl bayat.
                db.expire_all()
                tur = "ATLANDI" if isinstance(exc, SatirAtlandi) else "HATA"
                if tur == "ATLANDI":
                    sonuc.atlanan += 1
                sonuc.rapor_satirlari.append(RaporSatiri(
                    satir_no=satir.satir_no, sistem_no=sistem_no,
                    dosya_no=_metin(satir.degerler.get("dosya_no")) or "",
                    tur=tur, sebep=str(exc),
                ))
                logger.warning(f"Satır {satir.satir_no} ({sistem_no}) {tur}: {exc}")
            except SQLAlchemyError as exc:
                db.expire_all()
                sonuc.rapor_satirlari.append(RaporSatiri(
                    satir_no=satir.satir_no, sistem_no=sistem_no,
                    dosya_no=_metin(satir.degerler.get("dosya_no")) or "",
                    tur="HATA", sebep=f"{type(exc).__name__}: {exc}",
                ))
                logger.warning(f"Satır {satir.satir_no} ({sistem_no}) DB hatası: {exc}")
            else:
                # Aynı dosyada ikinci kez geçen SistemNo doğrudan bu karta
                # düşsün (Dosya No köprüsüne ikinci kez gitmeye gerek yok).
                foy_haritasi[sistem_no] = case_id
                kunye_kayitlari.append({
                    "sistem_no": sistem_no,
                    "case_id": case_id,
                    "tku_no": _metin(satir.degerler.get("tku_no")),
                    "karar_no": _metin(satir.degerler.get("karar_no")),
                    "karar_tarihi": _tarih_yumusak(
                        satir.degerler.get("karar_tarihi"), "karar_tarihi"),
                })

        sonuc.celiskiler = celiskileri_bul(kunye_kayitlari)

        db.flush()
        sonuc.envanter_sonra = belge_envanteri.snapshot(db)
        sonuc.envanter_farki = belge_envanteri.diff(sonuc.envanter_once, sonuc.envanter_sonra)

        if sonuc.envanter_farki:
            # Belge koruma şartı: hasar KALICI OLMADAN durdurulur.
            logger.error(
                "Aktarım GERİ ALINDI — " + belge_envanteri.bicimle(sonuc.envanter_farki)
            )
            db.rollback()
        elif dry_run:
            db.rollback()
            logger.info("KURU KOŞU: hiçbir tabloya yazılmadı (geri alındı)")
        else:
            db.commit()
            sonuc.yazildi = True
    finally:
        db.close()

    sonuc.raporlar = _raporlari_yaz(sonuc, girdi=girdi, rapor_dizini=rapor_dizini)
    return sonuc


# ═══════════════════════════════════════════════════════════════════════════
# Raporlar
# ═══════════════════════════════════════════════════════════════════════════

def _raporlari_yaz(sonuc: AktarimSonucu, *, girdi: Path,
                   rapor_dizini: Optional[Path]) -> List[Path]:
    """Satır raporu + kardeş föy çelişki raporu (CSV; UTF-8 BOM, ';' ayraç).

    Kuru koşuda DA yazılır — kuru koşunun ürünü zaten rapordur. CSV seçildi:
    xlsx'in biçimlendirmesine ihtiyaç yok, ';' + BOM ile Türkçe Excel'de
    doğrudan açılıyor ve dosya diff'lenebilir kalıyor.
    """
    if not sonuc.rapor_satirlari and not sonuc.celiskiler:
        return []
    dizin = Path(rapor_dizini) if rapor_dizini else girdi.parent / "aktarim-raporlari"
    dizin.mkdir(parents=True, exist_ok=True)
    damga = datetime.now().strftime("%Y%m%d-%H%M%S")

    yazilan: List[Path] = []
    if sonuc.rapor_satirlari:
        yazilan.append(_csv_yaz(
            dizin / f"satir-raporu_{damga}.csv",
            ("satir_no", "sistem_no", "dosya_no", "tur", "sebep"),
            [(r.satir_no, r.sistem_no, r.dosya_no, r.tur, r.sebep)
             for r in sonuc.rapor_satirlari],
        ))
    if sonuc.celiskiler:
        yazilan.append(_csv_yaz(
            dizin / f"kardes-foy-celiskileri_{damga}.csv",
            ("kume", "kume_anahtari", "alan", "degerler"),
            [(c.kume, c.kume_anahtari, c.alan, c.degerler) for c in sonuc.celiskiler],
        ))
    return yazilan


def _csv_yaz(yol: Path, basliklar: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> Path:
    with open(yol, "w", newline="", encoding="utf-8-sig") as dosya:
        yazici = csv.writer(dosya, delimiter=";")
        yazici.writerow(basliklar)
        yazici.writerows(satirlar)
    return yol


def ozet_metni(sonuc: AktarimSonucu) -> str:
    """Koşunun tek ekranlık özeti (stdout + log)."""
    satirlar = [
        "=" * 78,
        f"HUKDOK aktarımı — {sonuc.kaynak_imzasi}",
        "=" * 78,
        f"  okunan satır      : {sonuc.okunan}",
        f"  işlenen satır     : {sonuc.islenen}",
        f"  yeni föy          : {sonuc.foy_yeni}",
        f"  güncellenen föy   : {sonuc.foy_guncellenen}",
        f"  alan değişikliği  : {sonuc.alan_degisikligi} ({sonuc.kart_degisen} kart)",
        f"  atlanan (kart yok): {sonuc.atlanan}",
        f"  satır hatası      : {len(sonuc.hatalar)}",
        f"  kardeş çelişkisi  : {len(sonuc.celiskiler)}",
        f"  yazıldı mı        : {'HAYIR (kuru koşu)' if sonuc.dry_run else ('EVET' if sonuc.yazildi else 'HAYIR')}",
        "  " + belge_envanteri.bicimle(sonuc.envanter_farki).replace("\n", "\n  "),
    ]
    for yol in sonuc.raporlar:
        satirlar.append(f"  rapor             : {yol}")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="HUKDOK teslim paketini kartlara aktarır (çekirdek yazma yolu, G064)",
    )
    parser.add_argument("--input", required=True, help="teslim paketi (.xlsx)")
    parser.add_argument("--sheet", default=None, help="sayfa adı (varsayılan: ilk sayfa)")
    parser.add_argument("--limit", type=int, default=None, help="ilk N veri satırı")
    parser.add_argument("--dry-run", action="store_true",
                        help="hiçbir tabloya yazma; yalnız rapor üret")
    parser.add_argument("--source", default=None,
                        help=f"provenance imzası (varsayılan: {AKTARIM_SOURCE_PREFIX}_<dosya adı>)")
    parser.add_argument("--rapor-dizini", default=None,
                        help="rapor CSV'lerinin yazılacağı dizin")
    parser.add_argument("--statement-timeout-ms", type=int, default=VARSAYILAN_TIMEOUT_MS,
                        help="koşu süresince statement_timeout (0 = dokunma)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Loglama TEK noktadan yapılandırılır (Faz 2-B): dağınık basicConfig yasak,
    # bekçisi tests/test_faz2_logging.py::test_no_basicconfig_left_in_backend.
    from logging_setup import configure_logging

    configure_logging()

    import database

    try:
        sonuc = aktarimi_kos(
            database.SessionLocal,
            girdi=Path(args.input),
            sheet=args.sheet,
            limit=args.limit,
            dry_run=args.dry_run,
            source=args.source,
            rapor_dizini=Path(args.rapor_dizini) if args.rapor_dizini else None,
            statement_timeout_ms=args.statement_timeout_ms,
        )
    except AktarimHatasi as exc:
        logger.error(f"Aktarım başlamadı: {exc}")
        return CIKIS_GIRDI

    print(ozet_metni(sonuc))
    return sonuc.cikis_kodu


if __name__ == "__main__":
    sys.exit(main())
