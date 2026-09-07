"""Raporlama sorgu motoru — RaporTanimi → SQLAlchemy Core Select (G130).

Akış: `tanimi_dogrula` (registry'ye karşı anahtar/op/tip/değer denetimi, hata =
`RaporDogrulamaHatasi` → route 422) → `sorgu_kur` (Core `select`, ORM entity
DEĞİL; tenant + soft-delete `VeriKaynagi.kisitlar`ından, K2) → `onizle`
(sayfalı satırlar + toplam) ya da `satirlari_akit` (`yield_per` iteratörü —
G131 export'u bunu tüketir, bellek disiplini K3).

Güvenlik sınırı: istemciden gelen string'ler yalnız (a) registry sözlüğünde
ANAHTAR olarak aranır, (b) `contains` için `%`/`_`/`\\` kaçışlı ILIKE
parametresi olur, (c) `in` listesi bağlı parametre olur. Hiçbiri SQL metnine
girmez. Sıralama ve filtre ifadeleri daima `Kolon.ifade`'dir; filtrelenebilir
türetilmiş kolonda (G137) koşulu registry'nin `Kolon.filtre_ifadesi`si kurar
(EXISTS), atom koşulu (`_ifade_kosulu`) yine buradan alır. Op denetimi iki
katman: tip tablosu (`TIP_OPLARI`) + kolonun alt kümesi (`Kolon.oplar`).
G141: `in` listesindeki `null` öğesi "(boş)" demektir → `IN (...) OR IS NULL`
(yalnız `[null]` = `IS NULL`); `secilebilir=False` kolon (sanal `arama`)
kolon listesine ve sıralamaya giremez (422), yalnız filtre.

Serileştirme (plan §2.4): tarih/zaman ISO 8601 string, Decimal → float (JSON
number), bool olduğu gibi, NULL → null.
"""
from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from typing import Any, Iterator, Optional

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from schemas_rapor import (
    DEGERSIZ_OPLAR, ONIZLEME_SAYFA_BOYU_MAX, TIP_OPLARI, Filtre, KolonBasligi, RaporDogrulamaHatasi, RaporTanimi,
)
from services.rapor import registry
from services.rapor.registry import Kolon, VeriKaynagi

AKIS_PARCA = 500          # satirlari_akit yield_per boyu
_ILIKE_KACIS = "\\"


def limitler() -> dict[str, int]:
    """Katalogdaki `limitler` (plan §2.4). `RAPOR_MAX_SATIR` env'i G131 export tavanı;
    burada yalnız istemciye bildirilir (varsayılan plan §2.7: 50000)."""
    try:
        export_max = int(os.getenv("RAPOR_MAX_SATIR", "50000"))
    except ValueError:
        export_max = 50000
    return {"onizleme_sayfa_boyu_max": ONIZLEME_SAYFA_BOYU_MAX, "export_max_satir": export_max}


# ─── Doğrulama ───────────────────────────────────────────────────────────────

def _kaynak(tanim: RaporTanimi) -> VeriKaynagi:
    kaynak = registry.kaynak_bul(tanim.veri_kaynagi)
    if kaynak is None:
        raise RaporDogrulamaHatasi("veri_kaynagi", f"bilinmeyen veri kaynağı: {tanim.veri_kaynagi}")
    return kaynak


def _kolon(kaynak: VeriKaynagi, anahtar: str, alan: str) -> Kolon:
    kolon = kaynak.kolonlar.get(anahtar)
    if kolon is None:
        raise RaporDogrulamaHatasi(alan, f"katalogda olmayan kolon: {anahtar}")
    return kolon


def _tarih(deger: Any, alan: str) -> dt.date:
    if isinstance(deger, str):
        try:
            return dt.date.fromisoformat(deger)
        except ValueError:
            pass
    raise RaporDogrulamaHatasi(alan, "tarih değeri ISO biçiminde olmalı (YYYY-AA-GG)")


def _sayi(deger: Any, alan: str) -> Decimal:
    if isinstance(deger, bool) or not isinstance(deger, (int, float, str)):
        raise RaporDogrulamaHatasi(alan, "sayısal değer bekleniyor")
    try:
        return Decimal(str(deger))
    except ArithmeticError:
        raise RaporDogrulamaHatasi(alan, "sayısal değer bekleniyor") from None


def _metin(deger: Any, alan: str) -> str:
    if not isinstance(deger, str):
        raise RaporDogrulamaHatasi(alan, "metin değeri bekleniyor")
    return deger


def _cift(deger: Any, alan: str) -> tuple[Any, Any]:
    if not isinstance(deger, list) or len(deger) != 2:
        raise RaporDogrulamaHatasi(alan, "'between' iki öğeli liste ister [başlangıç, bitiş]")
    return deger[0], deger[1]


def _deger_cevir(kolon: Kolon, filtre: Filtre, alan: str) -> Any:
    """Op'a ve kolon tipine göre değeri denetler, Python tipine çevirir."""
    op, deger, tip = filtre.op, filtre.deger, kolon.tip
    if op in DEGERSIZ_OPLAR:
        return None
    if deger is None:
        raise RaporDogrulamaHatasi(alan, f"'{op}' için değer gerekli (null yalnız 'in' listesinde)")
    if tip in ("metin", "liste"):
        if op == "in":
            if not isinstance(deger, list) or not deger:
                raise RaporDogrulamaHatasi(alan, "'in' boş olmayan liste ister")
            # `null` öğesi "(boş)" (plan §5.2): tip denetimi atlanır, motor IS NULL'a çevirir
            return [None if d is None else _metin(d, alan) for d in deger]
        return _metin(deger, alan)
    if tip == "tarih":
        if op == "between":
            a, b = _cift(deger, alan)
            return (_tarih(a, alan), _tarih(b, alan))
        return _tarih(deger, alan)
    if tip in ("sayi", "para"):
        if op == "between":
            a, b = _cift(deger, alan)
            return (_sayi(a, alan), _sayi(b, alan))
        return _sayi(deger, alan)
    if tip == "mantik":
        if not isinstance(deger, bool):
            raise RaporDogrulamaHatasi(alan, "mantık değeri true/false olmalı")
        return deger
    raise RaporDogrulamaHatasi(alan, f"tanınmayan kolon tipi: {tip}")


def tanimi_dogrula(tanim: RaporTanimi) -> tuple[VeriKaynagi, list[tuple[Kolon, Filtre, Any]]]:
    """Registry'ye karşı tam doğrulama. Döner: (kaynak, [(kolon, filtre, çevrilmiş değer)]).
    Yapısal sınırlar (adet/tekrar) Pydantic'te; burada anahtar/op/tip/değer."""
    kaynak = _kaynak(tanim)
    for i, anahtar in enumerate(tanim.kolonlar):
        if not _kolon(kaynak, anahtar, f"kolonlar[{i}]").secilebilir:
            # Sanal `arama` (G141): yalnız filtre alanı, SELECT'e girmez
            raise RaporDogrulamaHatasi(f"kolonlar[{i}]", f"yalnız filtre alanı, kolon listesine giremez: {anahtar}")
    filtreler: list[tuple[Kolon, Filtre, Any]] = []
    for i, f in enumerate(tanim.filtreler):
        alan = f"filtreler[{i}]"
        kolon = _kolon(kaynak, f.alan, alan)
        if not kolon.filtrelenebilir:
            raise RaporDogrulamaHatasi(alan, f"kolon filtrelenemez: {f.alan}")
        if f.op not in TIP_OPLARI[kolon.tip]:
            raise RaporDogrulamaHatasi(alan, f"'{f.op}' operatörü '{kolon.tip}' tipinde izinli değil")
        if f.op not in kolon.oplar:
            # Türetilmiş kolonda tip tablosunun alt kümesi (`Kolon.izinli_oplar`, plan §4.2)
            raise RaporDogrulamaHatasi(
                alan, f"'{f.op}' operatörü '{f.alan}' kolonunda izinli değil (izinli: {', '.join(kolon.oplar)})",
            )
        filtreler.append((kolon, f, _deger_cevir(kolon, f, alan)))
    for i, s in enumerate(tanim.siralama):
        alan = f"siralama[{i}]"
        kolon = _kolon(kaynak, s.alan, alan)
        if not kolon.secilebilir:
            raise RaporDogrulamaHatasi(alan, f"yalnız filtre alanı, sıralamaya giremez: {s.alan}")
        if not kolon.siralanabilir:
            raise RaporDogrulamaHatasi(alan, f"kolon sıralanamaz: {s.alan}")
    return kaynak, filtreler


# ─── Sorgu kurma ─────────────────────────────────────────────────────────────

def _ilike_kacis(metin: str) -> str:
    return (
        metin.replace(_ILIKE_KACIS, _ILIKE_KACIS + _ILIKE_KACIS)
        .replace("%", _ILIKE_KACIS + "%")
        .replace("_", _ILIKE_KACIS + "_")
    )


def _gun_basi(gun: dt.date) -> dt.datetime:
    return dt.datetime.combine(gun, dt.time.min)


def _gun_sonrasi(gun: dt.date) -> dt.datetime:
    return _gun_basi(gun + dt.timedelta(days=1))


def _tarih_kosulu(kolon: Kolon, op: str, deger: Any):
    """Tarih kolonlarında karşılaştırma; DateTime kolonda (created_at gibi) gün
    aralığı: eq = [gün, gün+1), lte = < gün+1. Gün sınırı DB oturumunun saat
    dilimine göredir (sqlite bind'ı `date` değil `datetime` ister)."""
    ifade = kolon.ifade
    if kolon.zaman_damgali:
        if op == "eq":
            return and_(ifade >= _gun_basi(deger), ifade < _gun_sonrasi(deger))
        if op == "gte":
            return ifade >= _gun_basi(deger)
        if op == "lte":
            return ifade < _gun_sonrasi(deger)
        a, b = deger
        return and_(ifade >= _gun_basi(a), ifade < _gun_sonrasi(b))
    if op == "eq":
        return ifade == deger
    if op == "gte":
        return ifade >= deger
    if op == "lte":
        return ifade <= deger
    a, b = deger
    return and_(ifade >= a, ifade <= b)


def _bos(ifade: Any, metin: bool):
    """"Boş" koşulu: metin/liste kolonda `IS NULL OR TRIM(col) = ''` (G145 kataloğunun `bos_sayisi`
    ile AYNI anlam — rozet 120 derken filtre 95 bulmasın, 07.09 kararı); diğer tiplerde `IS NULL`."""
    if metin:
        return or_(ifade.is_(None), func.trim(ifade) == "")
    return ifade.is_(None)


def _ifade_kosulu(ifade: Any, op: str, deger: Any, metin: bool = False):
    """Tarih dışı atom koşul: verilen ifade üzerinde op. Türetilmiş kolonların
    EXISTS filtreleri (`Kolon.filtre_ifadesi`) de bunu alır — ILIKE kaçışı ve
    `ne`/`in` semantiği TEK yerde (kopya yok). `metin`: boşluk anlamı (`_bos`)."""
    if op == "is_null":
        return _bos(ifade, metin)
    if op == "not_null":
        return ~_bos(ifade, metin)
    if op == "eq":
        return ifade == deger
    if op == "ne":
        # NULL/boş satırlar "eşit değil"e dahil — kullanıcı beklentisi (boş da farklıdır)
        return or_(ifade != deger, _bos(ifade, metin))
    if op == "contains":
        return ifade.ilike(f"%{_ilike_kacis(deger)}%", escape=_ILIKE_KACIS)
    if op == "in":
        # `null` öğesi "Boş" (plan §5.2/§7): IN (dolu) OR boş; yalnız [null] = boş
        dolu = [d for d in deger if d is not None]
        if len(dolu) == len(deger):
            return ifade.in_(deger)
        if not dolu:
            return _bos(ifade, metin)
        return or_(ifade.in_(dolu), _bos(ifade, metin))
    if op == "gte":
        return ifade >= deger
    if op == "lte":
        return ifade <= deger
    if op == "between":
        a, b = deger
        return and_(ifade >= a, ifade <= b)
    raise ValueError(f"tanınmayan operatör: {op}")     # pragma: no cover — TIP_OPLARI eler


def _kosul(kolon: Kolon, filtre: Filtre, deger: Any):
    op = filtre.op
    if kolon.filtre_ifadesi is not None:
        # Türetilmiş + filtrelenebilir (plan §4.2): registry EXISTS'i kurar, atom koşulu buradan alır
        return kolon.filtre_ifadesi(op, deger, _ifade_kosulu)
    if kolon.tip == "tarih" and op not in DEGERSIZ_OPLAR:
        return _tarih_kosulu(kolon, op, deger)
    # Metin/liste kolonda "boş" = NULL ya da boş string (katalog `bos_sayisi` ile aynı anlam)
    return _ifade_kosulu(kolon.ifade, op, deger, metin=kolon.tip in ("metin", "liste"))


def sorgu_kur(tanim: RaporTanimi, tenant_id: str) -> Select:
    """Core `select`: seçili kolonlar `Kolon.ifade` etiketiyle, kaynak kısıtları
    (tenant + soft-delete) + filtreler + sıralama (+ birincil anahtar son kırıcı)."""
    kaynak, filtreler = tanimi_dogrula(tanim)
    secimler = [kaynak.kolonlar[a].ifade.label(a) for a in tanim.kolonlar]
    sorgu = select(*secimler).select_from(kaynak.from_clause)
    sorgu = sorgu.where(*kaynak.kisitlar(tenant_id))
    for kolon, filtre, deger in filtreler:
        sorgu = sorgu.where(_kosul(kolon, filtre, deger))
    siralama = []
    for s in tanim.siralama:
        ifade = kaynak.kolonlar[s.alan].ifade
        siralama.append(ifade.desc().nulls_last() if s.yon == "desc" else ifade.asc().nulls_first())
    if kaynak.birincil_anahtar is not None:
        siralama.append(kaynak.birincil_anahtar.asc())
    return sorgu.order_by(*siralama)


# ─── Çalıştırma ──────────────────────────────────────────────────────────────

def _serilestir(deger: Any) -> Any:
    if deger is None or isinstance(deger, (bool, int, float, str)):
        return deger
    if isinstance(deger, Decimal):
        return float(deger)
    if isinstance(deger, (dt.datetime, dt.date, dt.time)):
        return deger.isoformat()
    return str(deger)


def _satir(anahtarlar: list[str], satir) -> dict[str, Any]:
    return {a: _serilestir(v) for a, v in zip(anahtarlar, satir, strict=True)}


def kolon_basliklari(tanim: RaporTanimi) -> list[KolonBasligi]:
    kaynak = _kaynak(tanim)
    basliklar = []
    for i, a in enumerate(tanim.kolonlar):
        kolon = _kolon(kaynak, a, f"kolonlar[{i}]")
        basliklar.append(KolonBasligi(anahtar=a, etiket=kolon.etiket, tip=kolon.tip))
    return basliklar


def onizle(db: Session, tanim: RaporTanimi, tenant_id: str, sayfa: int = 1,
           sayfa_boyu: int = 50) -> tuple[list[KolonBasligi], list[dict[str, Any]], int]:
    """(kolonlar, satirlar, toplam). `sayfa` 1'den başlar; `sayfa_boyu` tavanı
    `ONIZLEME_SAYFA_BOYU_MAX` (route Pydantic'te keser, burada da kırpılır)."""
    sayfa = max(1, sayfa)
    sayfa_boyu = max(1, min(sayfa_boyu, ONIZLEME_SAYFA_BOYU_MAX))
    sorgu = sorgu_kur(tanim, tenant_id)
    toplam = db.execute(select(func.count()).select_from(sorgu.order_by(None).subquery())).scalar_one()
    satirlar = db.execute(sorgu.offset((sayfa - 1) * sayfa_boyu).limit(sayfa_boyu)).all()
    return kolon_basliklari(tanim), [_satir(tanim.kolonlar, s) for s in satirlar], int(toplam)


def satirlari_akit(db: Session, tanim: RaporTanimi, tenant_id: str,
                   parca: Optional[int] = None) -> Iterator[dict[str, Any]]:
    """Satır iteratörü (`yield_per`) — G131 export (xlsx write_only / csv) bunu tüketir;
    tüm sonuç belleğe alınmaz."""
    sorgu = sorgu_kur(tanim, tenant_id)
    sonuc = db.execute(sorgu.execution_options(yield_per=parca or AKIS_PARCA))
    for satir in sonuc:
        yield _satir(tanim.kolonlar, satir)
