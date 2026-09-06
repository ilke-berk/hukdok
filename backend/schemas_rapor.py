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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# ─── Sınırlar (plan §2.1) ────────────────────────────────────────────────────
KOLON_MAX = 60
FILTRE_MAX = 20
IN_DEGER_MAX = 200
SIRALAMA_MAX = 3
ONIZLEME_SAYFA_BOYU_MAX = 200

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
    deger: Any = None

    @field_validator("deger")
    @classmethod
    def _in_sinirini_denetle(cls, v: Any, info):
        # `in` listesi tavanı: tip bilinmeden de yapısal olarak kesilir
        if isinstance(v, list) and len(v) > IN_DEGER_MAX:
            raise ValueError(f"'in' değeri en fazla {IN_DEGER_MAX} öğe alır")
        return v


class Siralama(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alan: str = Field(min_length=1, max_length=100)
    yon: Literal["asc", "desc"] = "asc"


class RaporTanimi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    veri_kaynagi: str = Field(min_length=1, max_length=50)
    kolonlar: list[str] = Field(min_length=1, max_length=KOLON_MAX)
    filtreler: list[Filtre] = Field(default_factory=list, max_length=FILTRE_MAX)
    siralama: list[Siralama] = Field(default_factory=list, max_length=SIRALAMA_MAX)

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
    "DEGERSIZ_OPLAR", "ExportFormati", "ExportIstegi", "ExportKaynagi", "FILTRE_MAX", "IN_DEGER_MAX",
    "KOLON_MAX", "KolonBasligi", "KolonTipi", "KosuListesi", "ONIZLEME_SAYFA_BOYU_MAX", "Op", "OnizlemeCevabi",
    "OnizlemeIstegi", "Filtre", "RaporDogrulamaHatasi", "RaporKosusu", "RaporSablonu", "RaporTanimi",
    "SIRALAMA_MAX", "SablonIstegi", "Siralama", "TIP_OPLARI", "pydantic_hatasini_cevir",
]
