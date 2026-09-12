"""Raporlama modülü — istemciden gelen rapor tanımının Pydantic sözleşmesi (G130).

Sözleşme kaynağı: `docs/plan/raporlama-plani-2026-09-06.md` §2.1-2.2 (DONDURULDU;
G133 frontend'i buna göre yazılır). Burada yalnız YAPISAL doğrulama vardır:
sınırlar (kolon ≤60, filtre ≤20, `in` ≤200, sıralama ≤3), tekrarsızlık, op
sözlüğü. Anahtarın kayıt defterinde olup olmadığı ve op'un kolon TİPİNE uyup
uymadığı `services/rapor/motor.tanimi_dogrula` işidir (registry oradan okunur);
ikisi de aynı `RaporDogrulamaHatasi` ile 422'ye `{"alan", "sebep"}` taşır.

K6 (plan §1): asistanın ürettiği tanım da bu şemadan ve aynı motor doğrulamasından
geçer — tek doğrulama yolu.
"""
import datetime as dt
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_serializer

# ─── Sınırlar (plan §2.1) ────────────────────────────────────────────────────
KOLON_MAX = 60
FILTRE_MAX = 20
IN_DEGER_MAX = 200
SIRALAMA_MAX = 3
ONIZLEME_SAYFA_BOYU_MAX = 200

# ─── Sözleşmenin saat dilimi (12.09) ─────────────────────────────────────────
# Tanımdaki tarih değerleri ve çıktıdaki zaman damgaları TÜRKİYE günü/saatidir: filtre bind'ları
# bu dilimle kurulur (`registry.tarih_kosulu`), Postgres `timestamptz` değerleri bu dilime çevrilerek
# serileştirilir (`motor._serilestir`) ve Excel'e yazılır (`cikti._tarihe_cevir`). DB oturumu UTC'dir.
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")

# ─── Tip ↔ izinli op tablosu (plan §2.2) — TEK sabit, motor da buradan okur ──
Op = Literal["eq", "ne", "contains", "in", "gte", "lte", "between", "is_null", "not_null"]
KolonTipi = Literal["metin", "liste", "tarih", "sayi", "para", "mantik"]

TIP_OPLARI: dict[str, tuple[str, ...]] = {
    "metin": ("eq", "ne", "contains", "in", "is_null", "not_null"),
    "liste": ("eq", "ne", "in", "is_null", "not_null"),
    "tarih": ("eq", "gte", "lte", "between", "is_null", "not_null"),
    "sayi": ("eq", "gte", "lte", "between", "is_null", "not_null"),
    "para": ("eq", "gte", "lte", "between", "is_null", "not_null"),
    "mantik": ("eq", "is_null"),
}
DEGERSIZ_OPLAR: tuple[str, ...] = ("is_null", "not_null")


class RaporDogrulamaHatasi(ValueError):
    """Tanım doğrulanamadı → route 422 `{"alan": ..., "sebep": ...}` döner."""

    def __init__(self, alan: str, sebep: str):
        super().__init__(f"{alan}: {sebep}")
        self.alan = alan
        self.sebep = sebep

    def detay(self) -> dict[str, str]:
        return {"alan": self.alan, "sebep": self.sebep}


class Filtre(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alan: str = Field(min_length=1, max_length=100)
    op: Op
    # `in` listesinde `null` öğesi "(boş)" demektir (plan §5.2, G141): motor
    # `IN (...) OR IS NULL` kurar; tek başına `[null]` = `is_null`. Başka op'un
    # listesinde (`between`) `null` yapısal olarak reddedilir.
    deger: Any = None

    @field_validator("deger")
    @classmethod
    def _in_sinirini_denetle(cls, v: Any, info):
        # `in` listesi tavanı: tip bilinmeden de yapısal olarak kesilir
        if isinstance(v, list):
            if len(v) > IN_DEGER_MAX:
                raise ValueError(f"'in' değeri en fazla {IN_DEGER_MAX} öğe alır")
            if info.data.get("op") != "in" and any(d is None for d in v):
                raise ValueError("null yalnız 'in' listesinde")
        return v


class Siralama(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alan: str = Field(min_length=1, max_length=100)
    yon: Literal["asc", "desc"] = "asc"


# ─── Özet modu (12.09: gruplama + ölçüm) ─────────────────────────────────────
# "Avukat başına kaç dava", "aylara göre açılış sayısı", "müvekkil başına toplam tazminat": tanım
# `olcumler` taşıyorsa ÖZET MODUDUR — satırlar `gruplama` alanlarına göre gruplanır, her grup için
# ölçümler hesaplanır (`gruplama` boşsa tek toplam satırı). `kolonlar` özet modunda KULLANILMAZ ama
# şemada zorunlu kalır (liste görünümüne dönünce aynı kolonlar geri gelir). Gruplama yalnız düz
# (sıralanabilir) kolonlarda; tarih kolonunda `kirilim` gün/ay/yıl (Türkiye günü, `SAAT_DILIMI`).
# Sıralama özet modunda gruplama alanı ya da ölçüm anahtarı (`olcum_anahtari`) ile yapılır.
GRUPLAMA_MAX = 3
OLCUM_MAX = 5
TarihKirilimi = Literal["gun", "ay", "yil"]
OlcumIslemi = Literal["sayi", "toplam", "ortalama", "min", "max"]
# Ölçüm işlemi → izinli kolon tipleri (`sayi` alan almadan da olur = COUNT(*); alanla = dolu değer sayısı)
OLCUM_TIPLERI: dict[str, tuple[str, ...]] = {
    "sayi": ("metin", "liste", "tarih", "sayi", "para", "mantik"),
    "toplam": ("sayi", "para"),
    "ortalama": ("sayi", "para"),
    "min": ("sayi", "para", "tarih"),
    "max": ("sayi", "para", "tarih"),
}


def olcum_anahtari(islem: str, alan: Optional[str]) -> str:
    """Ölçüm kolonunun cevap/sıralama anahtarı: `sayi` (alan yok) ya da `toplam:maddi_tazminat`."""
    return f"{islem}:{alan}" if alan else islem


class Gruplama(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alan: str = Field(min_length=1, max_length=100)
    kirilim: Optional[TarihKirilimi] = None     # yalnız tarih kolonunda; None = tarih kolonunda "gun"


class Olcum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    islem: OlcumIslemi
    alan: Optional[str] = Field(default=None, max_length=100)

    @property
    def anahtar(self) -> str:
        return olcum_anahtari(self.islem, self.alan)


class RaporTanimi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    veri_kaynagi: str = Field(min_length=1, max_length=50)
    kolonlar: list[str] = Field(min_length=1, max_length=KOLON_MAX)
    filtreler: list[Filtre] = Field(default_factory=list, max_length=FILTRE_MAX)
    siralama: list[Siralama] = Field(default_factory=list, max_length=SIRALAMA_MAX)
    gruplama: list[Gruplama] = Field(default_factory=list, max_length=GRUPLAMA_MAX)
    olcumler: list[Olcum] = Field(default_factory=list, max_length=OLCUM_MAX)

    @property
    def ozet_modu(self) -> bool:
        return bool(self.olcumler)

    @model_serializer(mode="wrap")
    def _bos_ozet_alanlarini_at(self, handler: Any) -> Any:
        """Boş `gruplama`/`olcumler` serileştirmeye GİRMEZ: liste görünümündeki tanımın JSON'u (koşu
        logu, şablon, asistan `mevcut_tanim`, `complete.tanim`) 12.09 öncesiyle birebir kalır — istemci
        ve eski kayıtlar için sözleşme değişmez; özet modunda iki alan görünür."""
        veri = handler(self)
        if isinstance(veri, dict):
            for alan in ("gruplama", "olcumler"):
                if not veri.get(alan):
                    veri.pop(alan, None)
        return veri

    @field_validator("kolonlar")
    @classmethod
    def _tekrarsiz(cls, v: list[str]) -> list[str]:
        gorulen: set[str] = set()
        for anahtar in v:
            if not anahtar:
                raise ValueError("boş kolon anahtarı")
            if anahtar in gorulen:
                raise ValueError(f"kolon tekrar ediyor: {anahtar}")
            gorulen.add(anahtar)
        return v

    @field_validator("gruplama")
    @classmethod
    def _gruplama_tekrarsiz(cls, v: list[Gruplama]) -> list[Gruplama]:
        gorulen: set[str] = set()
        for g in v:
            if g.alan in gorulen:
                raise ValueError(f"gruplama alanı tekrar ediyor: {g.alan}")
            gorulen.add(g.alan)
        return v

    @field_validator("olcumler")
    @classmethod
    def _olcumler_tekrarsiz(cls, v: list[Olcum], info) -> list[Olcum]:
        gorulen: set[str] = set()
        for o in v:
            if o.islem != "sayi" and not o.alan:
                raise ValueError(f"'{o.islem}' ölçümü alan ister")
            if o.anahtar in gorulen:
                raise ValueError(f"ölçüm tekrar ediyor: {o.anahtar}")
            gorulen.add(o.anahtar)
        if not v and info.data.get("gruplama"):
            raise ValueError("gruplama en az bir ölçüm ister (örn. kayıt sayısı)")
        return v


class OnizlemeIstegi(BaseModel):
    """`POST /api/reports/preview` gövdesi (plan §2.4)."""
    model_config = ConfigDict(extra="forbid")

    tanim: RaporTanimi
    sayfa: int = Field(default=1, ge=1)
    sayfa_boyu: int = Field(default=50, ge=1, le=ONIZLEME_SAYFA_BOYU_MAX)


class KolonBasligi(BaseModel):
    anahtar: str
    etiket: str
    tip: str


class OnizlemeCevabi(BaseModel):
    kolonlar: list[KolonBasligi]
    satirlar: list[dict[str, Any]]
    toplam: int
    sayfa: int
    sayfa_boyu: int


# ─── G131: şablon / export / koşu şemaları (plan §2.4) ───────────────────────

ExportFormati = Literal["xlsx", "csv"]
ExportKaynagi = Literal["manuel", "asistan"]


class SablonIstegi(BaseModel):
    """`POST/PUT /api/reports/templates` gövdesi — tam gövde (kısmi değil)."""
    model_config = ConfigDict(extra="forbid")

    ad: str = Field(min_length=1, max_length=120)
    aciklama: Optional[str] = Field(default=None, max_length=500)
    tanim: RaporTanimi
    paylasimli: bool = False


class RaporSablonu(BaseModel):
    """Şablon cevabı (`RaporSablonu`, plan §2.4) — ORM satırından `model_validate`."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ad: str
    aciklama: Optional[str]
    tanim: RaporTanimi
    olusturan: str
    paylasimli: bool
    created_at: Optional[dt.datetime]
    updated_at: Optional[dt.datetime]


class ExportIstegi(BaseModel):
    """`POST /api/reports/export` gövdesi."""
    model_config = ConfigDict(extra="forbid")

    tanim: RaporTanimi
    format: ExportFormati = "xlsx"
    sablon_id: Optional[int] = None
    kaynak: ExportKaynagi = "manuel"


class RaporKosusu(BaseModel):
    """Koşu/indirme log satırı (`RaporKosusu`, plan §2.4). `dosya_mevcut` =
    `dosya_yolu` dolu VE dosya diskte (route hesaplar)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    sablon_id: Optional[int]
    sablon_adi: Optional[str]
    format: str
    kaynak: str
    veri_kaynagi: str
    kolon_sayisi: int
    satir_sayisi: int
    kullanici: str
    baslangic: Optional[dt.datetime]
    sure_ms: Optional[int]
    dosya_adi: str
    dosya_boyutu: Optional[int]
    sha256: Optional[str]
    dosya_mevcut: bool
    hata: Optional[str] = None
    tanim: dict[str, Any]


class KosuListesi(BaseModel):
    toplam: int
    kosular: list[RaporKosusu]


# ─── G132: rapor asistanı (plan §2.6, K6-K7) ─────────────────────────────────
#
# İki ayrı şema ailesi vardır ve bu BİLİNÇLİDİR:
#
# * `SohbetIstegi` — istemciden gelen `/chat` gövdesi (sınırlar: mesaj ≤20,
#   içerik ≤4000; `extra="forbid"`). `mevcut_tanim` gerçek `RaporTanimi`dir.
# * `RaporAsistanCevabi` + `AsistanTanimi` + `AsistanFiltre` — Gemini'ye
#   `response_schema` olarak verilen aile. `RaporTanimi` BURADA KULLANILAMAZ:
#   (a) `extra="forbid"` → `additionalProperties:false` üretir; google-genai
#   2.11.0 Developer API modunda `additionalProperties`'i desteklemez
#   (`_raise_for_unsupported_mldev_properties` truthy değeri reddeder, `false`
#   süzülmeden API'ye gider — kabulü SDK garantisi dışında); (b) `Filtre.deger:
#   Any` tipsiz özellik üretir. Bu yüzden asistan filtresi değeri METİN taşır
#   (`deger`) ya da metin listesi (`degerler`, `in`/`between`); sunucu
#   (`services/rapor/asistan.tanimi_dogrula`) kolon tipine göre çevirir ve
#   sonucu AYNI `RaporTanimi` + `motor.tanimi_dogrula` yolundan geçirir (K6).
#   Geçmeyen tanım istemciye hiçbir zaman `tanim` olarak gitmez.

SOHBET_MESAJ_MAX = 20
SOHBET_ICERIK_MAX = 4000

SohbetRolu = Literal["user", "assistant"]
AsistanEylemi = Literal["onizle", "indir_xlsx", "indir_csv"]


class SohbetMesaji(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: SohbetRolu
    icerik: str = Field(min_length=1, max_length=SOHBET_ICERIK_MAX)


class SohbetIstegi(BaseModel):
    """`POST /api/reports/chat` gövdesi (plan §2.4). Son mesaj kullanıcıya ait
    olmalı — Gemini `contents` dizisi kullanıcı sırasıyla biter."""
    model_config = ConfigDict(extra="forbid")

    mesajlar: list[SohbetMesaji] = Field(min_length=1, max_length=SOHBET_MESAJ_MAX)
    mevcut_tanim: Optional[RaporTanimi] = None

    @field_validator("mesajlar")
    @classmethod
    def _son_mesaj_kullanicinin(cls, v: list[SohbetMesaji]) -> list[SohbetMesaji]:
        if v and v[-1].rol != "user":
            raise ValueError("son mesaj kullanıcıya ait olmalı (rol=user)")
        return v


class AsistanFiltre(BaseModel):
    """Gemini'nin ürettiği filtre: değer METİN (tek) ya da metin listesi
    (`in`/`between`); tip çevirisi sunucuda (yukarıdaki şerh). `in` listesinde
    `"(boş)"` sabiti sunucuda `null`'a çevrilir (`asistan.BOS_SABITLERI`, G141)."""

    alan: str
    op: Op
    deger: Optional[str] = None
    degerler: Optional[list[str]] = None


class AsistanSiralama(BaseModel):
    alan: str
    yon: Literal["asc", "desc"] = "asc"


class AsistanGruplama(BaseModel):
    alan: str
    kirilim: Optional[str] = None      # gun | ay | yil (tarih kolonunda); sunucu doğrular


class AsistanOlcum(BaseModel):
    islem: str                          # sayi | toplam | ortalama | min | max; sunucu doğrular
    alan: Optional[str] = None


class AsistanTanimi(BaseModel):
    veri_kaynagi: str
    kolonlar: list[str]
    filtreler: list[AsistanFiltre] = Field(default_factory=list)
    siralama: list[AsistanSiralama] = Field(default_factory=list)
    # 12.09 özet modu: "avukat başına kaç dava" → gruplama + olcumler (kolonlar yine dolu gelir, kullanılmaz)
    gruplama: list[AsistanGruplama] = Field(default_factory=list)
    olcumler: list[AsistanOlcum] = Field(default_factory=list)


class RaporAsistanCevabi(BaseModel):
    """Gemini `response_schema` (plan §2.6): kısa Türkçe `cevap`, isteğe bağlı
    `tanim` (belirsizlikte null + soru), isteğe bağlı `eylem` (K7)."""

    cevap: str
    tanim: Optional[AsistanTanimi] = None
    eylem: Optional[AsistanEylemi] = None


class SohbetTamamlandi(BaseModel):
    """`complete` olayının gövdesi (plan §2.6) — route'un ürettiği son olay."""

    status: Literal["complete"] = "complete"
    cevap: str
    tanim: Optional[RaporTanimi] = None
    eylem: Optional[AsistanEylemi] = None


def pydantic_hatasini_cevir(hata: ValidationError) -> RaporDogrulamaHatasi:
    """Pydantic'in ilk hatasını sözleşmedeki `{"alan","sebep"}` biçimine indirger.

    FastAPI'nin varsayılan 422 gövdesi `[{loc,msg,type}]` listesidir; sözleşme
    (§2.1) tek alan + tek sebep ister ve G133 bunu okur. Route gövdeyi kendi
    doğrular ve bu dönüştürücüyü kullanır.
    """
    ilk = hata.errors()[0] if hata.errors() else {}
    loc = ".".join(str(p) for p in ilk.get("loc", ()) if p != "body") or "tanim"
    mesaj = str(ilk.get("msg", "geçersiz gövde"))
    if mesaj.startswith("Value error, "):
        mesaj = mesaj[len("Value error, "):]
    return RaporDogrulamaHatasi(loc, mesaj)


__all__ = [
    "AsistanEylemi", "AsistanFiltre", "AsistanSiralama", "AsistanTanimi", "DEGERSIZ_OPLAR", "ExportFormati",
    "ExportIstegi", "ExportKaynagi", "FILTRE_MAX", "IN_DEGER_MAX", "KOLON_MAX", "KolonBasligi", "KolonTipi",
    "KosuListesi", "ONIZLEME_SAYFA_BOYU_MAX", "Op", "OnizlemeCevabi", "OnizlemeIstegi", "Filtre",
    "RaporAsistanCevabi", "RaporDogrulamaHatasi", "RaporKosusu", "RaporSablonu", "RaporTanimi", "SIRALAMA_MAX",
    "SOHBET_ICERIK_MAX", "SOHBET_MESAJ_MAX", "SablonIstegi", "Siralama", "SohbetIstegi", "SohbetMesaji",
    "SohbetRolu", "SohbetTamamlandi", "TIP_OPLARI", "pydantic_hatasini_cevir",
]
