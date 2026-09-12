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

from sqlalchemy import Date, Select, String, and_, cast, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import FunctionElement

from schemas_rapor import (
    DEGERSIZ_OPLAR, GRUPLAMA_MAX, OLCUM_MAX, OLCUM_TIPLERI, ONIZLEME_SAYFA_BOYU_MAX, SAAT_DILIMI, TIP_OPLARI, Filtre,
    KolonBasligi, Olcum, RaporDogrulamaHatasi, RaporTanimi,
)
from services.rapor import registry
from services.rapor.registry import Kolon, VeriKaynagi

AKIS_PARCA = 500          # satirlari_akit yield_per boyu
_ILIKE_KACIS = "\\"


def limitler() -> dict[str, int]:
    """Katalogdaki `limitler` (plan §2.4). `RAPOR_MAX_SATIR` env'i G131 export tavanı;
    burada yalnız istemciye bildirilir (varsayılan plan §2.7: 50000). 12.09: özet modu tavanları."""
    try:
        export_max = int(os.getenv("RAPOR_MAX_SATIR", "50000"))
    except ValueError:
        export_max = 50000
    return {
        "onizleme_sayfa_boyu_max": ONIZLEME_SAYFA_BOYU_MAX, "export_max_satir": export_max,
        "gruplama_max": GRUPLAMA_MAX, "olcum_max": OLCUM_MAX,
    }


# ─── Özet modu (12.09): gruplama + ölçüm ifadeleri ───────────────────────────

class tr_gun(FunctionElement):     # noqa: N801 — SQL işlevi adı
    """Zaman damgası → TÜRKİYE günü (DATE). Postgres: `(col AT TIME ZONE 'Europe/Istanbul')::date`
    (`timestamptz` UTC tutulur, gün sınırı TR gece yarısı — `SAAT_DILIMI` ile aynı karar); sqlite (test):
    `date(col)` (naive). Gün/ay/yıl kırılımı bunun üstüne kurulur."""
    type = Date()
    inherit_cache = True


@compiles(tr_gun)
def _tr_gun_varsayilan(element: tr_gun, compiler: Any, **kw: Any) -> str:
    return "date(%s)" % compiler.process(element.clauses, **kw)


@compiles(tr_gun, "postgresql")
def _tr_gun_postgres(element: tr_gun, compiler: Any, **kw: Any) -> str:
    return "(%s AT TIME ZONE '%s')::date" % (compiler.process(element.clauses, **kw), SAAT_DILIMI.key)


KIRILIM_ETIKETLERI = {"gun": "gün", "ay": "ay", "yil": "yıl"}
OLCUM_ETIKETLERI = {"sayi": "{} sayısı", "toplam": "Toplam {}", "ortalama": "Ortalama {}", "min": "En küçük {}",
                    "max": "En büyük {}"}
KAYIT_SAYISI_ETIKETI = "Kayıt sayısı"


def _grup_ifadesi(kolon: Kolon, kirilim: Optional[str]) -> tuple[Any, str]:
    """(ifade, çıktı tipi). Tarih kolonunda kırılım: gün = Türkiye günü (DATE), ay = 'YYYY-AA', yıl = 'YYYY'
    (ISO metnin ön eki — Postgres `cast(date AS VARCHAR)` ve sqlite'ın tarih metni aynı biçimde). Diğer tiplerde
    kolonun kendisi."""
    if kolon.tip != "tarih":
        return kolon.ifade, kolon.tip
    gun = tr_gun(kolon.ifade) if kolon.zaman_damgali else kolon.ifade
    if kirilim in (None, "gun"):
        return gun, "tarih"
    uzunluk = 7 if kirilim == "ay" else 4
    return func.substr(cast(gun, String), 1, uzunluk), "metin"


def _olcum_ifadesi(olcum: Olcum, kolon: Optional[Kolon]) -> tuple[Any, str, str]:
    """(ifade, etiket, çıktı tipi). `sayi` alansız = COUNT(*), alanlı = dolu değer sayısı; toplam/ortalama
    para→para, sayi→sayi; min/max kolonun tipi."""
    if kolon is None:
        return func.count(), KAYIT_SAYISI_ETIKETI, "sayi"
    etiket = OLCUM_ETIKETLERI[olcum.islem].format(kolon.etiket)
    if olcum.islem == "sayi":
        return func.count(kolon.ifade), etiket, "sayi"
    if olcum.islem == "toplam":
        return func.sum(kolon.ifade), etiket, kolon.tip
    if olcum.islem == "ortalama":
        return func.avg(kolon.ifade), etiket, kolon.tip
    if olcum.islem == "min":
        return func.min(kolon.ifade), etiket, kolon.tip
    return func.max(kolon.ifade), etiket, kolon.tip


def _grup_etiketi(kolon: Kolon, kirilim: Optional[str]) -> str:
    if kolon.tip == "tarih" and kirilim in ("ay", "yil"):
        return f"{kolon.etiket} ({KIRILIM_ETIKETLERI[kirilim]})"
    return kolon.etiket


def ozet_kolonlari(kaynak: VeriKaynagi, tanim: RaporTanimi) -> list[tuple[str, str, str, Any]]:
    """Özet modunun çıktı kolonları: önce gruplama alanları (anahtar = alan), sonra ölçümler
    (anahtar = `olcum_anahtari`). Her öğe (anahtar, etiket, tip, ifade). Doğrulama `tanimi_dogrula`da."""
    kolonlar: list[tuple[str, str, str, Any]] = []
    for g in tanim.gruplama:
        kolon = kaynak.kolonlar[g.alan]
        ifade, tip = _grup_ifadesi(kolon, g.kirilim)
        kolonlar.append((g.alan, _grup_etiketi(kolon, g.kirilim), tip, ifade))
    for o in tanim.olcumler:
        ifade, etiket, tip = _olcum_ifadesi(o, kaynak.kolonlar[o.alan] if o.alan else None)
        kolonlar.append((o.anahtar, etiket, tip, ifade))
    return kolonlar


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
    _ozeti_dogrula(kaynak, tanim)
    if tanim.ozet_modu:
        # Özet modunda sıralama yalnız gruplama alanı ya da ölçüm anahtarıyla (çıktı kolonları bunlardır)
        izinli = {g.alan for g in tanim.gruplama} | {o.anahtar for o in tanim.olcumler}
        for i, s in enumerate(tanim.siralama):
            if s.alan not in izinli:
                raise RaporDogrulamaHatasi(
                    f"siralama[{i}]", f"özet modunda sıralama yalnız gruplama alanı ya da ölçüm anahtarıyla: {s.alan}",
                )
        return kaynak, filtreler
    for i, s in enumerate(tanim.siralama):
        alan = f"siralama[{i}]"
        kolon = _kolon(kaynak, s.alan, alan)
        if not kolon.secilebilir:
            raise RaporDogrulamaHatasi(alan, f"yalnız filtre alanı, sıralamaya giremez: {s.alan}")
        if not kolon.siralanabilir:
            raise RaporDogrulamaHatasi(alan, f"kolon sıralanamaz: {s.alan}")
    return kaynak, filtreler


def _ozeti_dogrula(kaynak: VeriKaynagi, tanim: RaporTanimi) -> None:
    """Gruplama: seçilebilir + sıralanabilir (düz) kolon, kırılım yalnız tarih kolonunda. Ölçüm: alanlı ise
    kolon seçilebilir ve tipi `OLCUM_TIPLERI[islem]` içinde (toplam/ortalama sayı-para, min/max +tarih)."""
    for i, g in enumerate(tanim.gruplama):
        alan = f"gruplama[{i}]"
        kolon = _kolon(kaynak, g.alan, alan)
        if not (kolon.secilebilir and kolon.siralanabilir):
            raise RaporDogrulamaHatasi(alan, f"kolon gruplanamaz (türetilmiş/çoklu bağ): {g.alan}")
        if g.kirilim is not None and kolon.tip != "tarih":
            raise RaporDogrulamaHatasi(alan, f"kırılım yalnız tarih kolonunda: {g.alan}")
    for i, o in enumerate(tanim.olcumler):
        alan = f"olcumler[{i}]"
        if o.alan is None:
            continue
        kolon = _kolon(kaynak, o.alan, alan)
        if not kolon.secilebilir:
            raise RaporDogrulamaHatasi(alan, f"yalnız filtre alanı, ölçüme giremez: {o.alan}")
        if kolon.tip not in OLCUM_TIPLERI[o.islem]:
            raise RaporDogrulamaHatasi(
                alan, f"'{o.islem}' ölçümü '{kolon.tip}' tipinde yapılamaz (izinli: {', '.join(OLCUM_TIPLERI[o.islem])})",
            )


# ─── Sorgu kurma ─────────────────────────────────────────────────────────────

def _ilike_kacis(metin: str) -> str:
    return (
        metin.replace(_ILIKE_KACIS, _ILIKE_KACIS + _ILIKE_KACIS)
        .replace("%", _ILIKE_KACIS + "%")
        .replace("_", _ILIKE_KACIS + "_")
    )


def _tarih_kosulu(kolon: Kolon, op: str, deger: Any):
    """Tarih kolonlarında karşılaştırma — gövde `registry.tarih_kosulu`da (G166: bağlı kolon
    EXISTS'i de aynı kuralı kullanır; DateTime kolonda gün aralığı)."""
    return registry.tarih_kosulu(kolon.ifade, kolon.zaman_damgali, op, deger)


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
    (tenant + soft-delete) + filtreler + sıralama (+ birincil anahtar son kırıcı).
    Özet modunda (12.09): gruplama ifadeleri + ölçüm toplamları, `GROUP BY` gruplama ifadeleri; filtreler
    yine WHERE'de (gruplamadan ÖNCE). Sıralama verilmemişse ilk ölçüm azalan ("X başına kaç" doğal sırası),
    gruplama alanları artan kırıcı."""
    kaynak, filtreler = tanimi_dogrula(tanim)
    if tanim.ozet_modu:
        return _ozet_sorgusu(kaynak, tanim, tenant_id, filtreler)
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


def _ozet_sorgusu(kaynak: VeriKaynagi, tanim: RaporTanimi, tenant_id: str,
                  filtreler: list[tuple[Kolon, Filtre, Any]]) -> Select:
    kolonlar = ozet_kolonlari(kaynak, tanim)
    ifadeler = {anahtar: ifade for anahtar, _e, _t, ifade in kolonlar}
    sorgu = select(*(ifade.label(anahtar) for anahtar, _e, _t, ifade in kolonlar)).select_from(kaynak.from_clause)
    sorgu = sorgu.where(*kaynak.kisitlar(tenant_id))
    for kolon, filtre, deger in filtreler:
        sorgu = sorgu.where(_kosul(kolon, filtre, deger))
    grup_ifadeleri = [ifadeler[g.alan] for g in tanim.gruplama]
    if grup_ifadeleri:
        sorgu = sorgu.group_by(*grup_ifadeleri)
    siralama = []
    for s in tanim.siralama:
        ifade = ifadeler[s.alan]
        siralama.append(ifade.desc().nulls_last() if s.yon == "desc" else ifade.asc().nulls_first())
    if not siralama and tanim.gruplama:
        siralama.append(ifadeler[tanim.olcumler[0].anahtar].desc().nulls_last())
    siralama.extend(ifade.asc().nulls_first() for ifade in grup_ifadeleri)
    return sorgu.order_by(*siralama)


# ─── Çalıştırma ──────────────────────────────────────────────────────────────

def _serilestir(deger: Any) -> Any:
    if deger is None or isinstance(deger, (bool, int, float, str)):
        return deger
    if isinstance(deger, Decimal):
        return float(deger)
    if isinstance(deger, dt.datetime) and deger.tzinfo is not None:
        # Postgres `timestamptz` UTC gelir; ekran/CSV/Excel Türkiye saatini görsün (12.09: gece
        # 22:15 UTC satırı bir önceki güne düşüyordu). ISO çıktı `+03:00` ofsetini taşır.
        return deger.astimezone(SAAT_DILIMI).isoformat()
    if isinstance(deger, (dt.datetime, dt.date, dt.time)):
        return deger.isoformat()
    return str(deger)


def _satir(anahtarlar: list[str], satir) -> dict[str, Any]:
    return {a: _serilestir(v) for a, v in zip(anahtarlar, satir, strict=True)}


def kolon_basliklari(tanim: RaporTanimi) -> list[KolonBasligi]:
    """Çıktı kolonları: liste görünümünde `kolonlar`, özet modunda gruplama alanları + ölçümler
    (`ozet_kolonlari`; özet doğrulaması burada da koşar — export rotası önce bunu çağırır)."""
    kaynak = _kaynak(tanim)
    if tanim.ozet_modu:
        _ozeti_dogrula(kaynak, tanim)
        return [KolonBasligi(anahtar=a, etiket=e, tip=t) for a, e, t, _i in ozet_kolonlari(kaynak, tanim)]
    basliklar = []
    for i, a in enumerate(tanim.kolonlar):
        kolon = _kolon(kaynak, a, f"kolonlar[{i}]")
        basliklar.append(KolonBasligi(anahtar=a, etiket=kolon.etiket, tip=kolon.tip))
    return basliklar


def cikti_anahtarlari(tanim: RaporTanimi) -> list[str]:
    """Satır sözlüğünün anahtarları — `sorgu_kur` etiketleriyle birebir."""
    if tanim.ozet_modu:
        return [g.alan for g in tanim.gruplama] + [o.anahtar for o in tanim.olcumler]
    return list(tanim.kolonlar)


def onizle(db: Session, tanim: RaporTanimi, tenant_id: str, sayfa: int = 1,
           sayfa_boyu: int = 50) -> tuple[list[KolonBasligi], list[dict[str, Any]], int]:
    """(kolonlar, satirlar, toplam). `sayfa` 1'den başlar; `sayfa_boyu` tavanı
    `ONIZLEME_SAYFA_BOYU_MAX` (route Pydantic'te keser, burada da kırpılır). Özet modunda `toplam` = grup sayısı."""
    sayfa = max(1, sayfa)
    sayfa_boyu = max(1, min(sayfa_boyu, ONIZLEME_SAYFA_BOYU_MAX))
    sorgu = sorgu_kur(tanim, tenant_id)
    anahtarlar = cikti_anahtarlari(tanim)
    toplam = db.execute(select(func.count()).select_from(sorgu.order_by(None).subquery())).scalar_one()
    satirlar = db.execute(sorgu.offset((sayfa - 1) * sayfa_boyu).limit(sayfa_boyu)).all()
    return kolon_basliklari(tanim), [_satir(anahtarlar, s) for s in satirlar], int(toplam)


def satirlari_akit(db: Session, tanim: RaporTanimi, tenant_id: str,
                   parca: Optional[int] = None) -> Iterator[dict[str, Any]]:
    """Satır iteratörü (`yield_per`) — G131 export (xlsx write_only / csv) bunu tüketir;
    tüm sonuç belleğe alınmaz."""
    sorgu = sorgu_kur(tanim, tenant_id)
    anahtarlar = cikti_anahtarlari(tanim)
    sonuc = db.execute(sorgu.execution_options(yield_per=parca or AKIS_PARCA))
    for satir in sonuc:
        yield _satir(anahtarlar, satir)
