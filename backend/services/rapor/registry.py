"""Raporlama kayıt defteri — hangi veri kaynağı, hangi kolon, hangi tip (G130, G137).

**Beyaz liste ilkesi (plan K1):** istemciden (ve asistandan, K6) gelen hiçbir
string SQL'e ham girmez. Motor yalnız buradaki `Kolon.ifade` SQLAlchemy
ifadelerini (ve türetilmiş kolonda `Kolon.filtre_ifadesi`nin ürettiği EXISTS
koşulunu) kullanır; istemcinin gönderdiği anahtar bu sözlükte yoksa 422.
`SETTINGS_REGISTRY` / `LIST_REGISTRY` deseninin (services/app_settings.py,
managers/reference_lists.py) rapor ikizi.

Dört veri kaynağı (plan §2.3): `davalar` (cases), `muvekkiller` (clients),
`belgeler` (case_documents JOIN cases), `foyler` (case_foys JOIN cases).
Tenant + soft-delete kuralı `VeriKaynagi.kisitlar(tenant_id)` ile TEK yerden
gelir (K2, `case_manager._apply_tenant_filter` ile aynı kural):
`tenant_filter_clause` + `deleted_at IS NULL`; `belgeler`/`foyler` bunu `cases`
JOIN'iyle (INNER — davasız/silinmiş davalı satır rapora girmez), `muvekkiller`
`Client` üzerinden alır.

Kataloga GİRMEYENLER (plan §2.3): `tenant_id`, `deleted_*`, `notes` (serbest
metin, PII), `ham_veri` (föy ham satırı); ayrıca `clients.tc_no` / `source_ids`
ve belge `email_error` / `conversion_spool_path` (teknik/PII, rapor değeri yok).

Kolon tipi kolonun SQLAlchemy tipinden türetilir (`_tip_bul`); kapalı listeli
alanlar `liste` tipine `secenekler` ile ZORLANIR — seçeneksiz `liste` kolon YOK
(`test_g130_rapor_temeli` bunu mekanik doğrular). Seçenek kaynağı üç katman:
sabit çekirdek (seed sabitleri / kod sözlükleri) + referans tablosu adları
(`secenek_tablosu`, aktif satırlar) + kolondaki DISTINCT değerler; hepsi
`secenekleri_getir(kolon, db)` ile birleşir (sıra korunur, tekrar yok).
Türetilmiş metin birleştirmeleri `func.aggregate_strings(..., " ; ")` —
Postgres'te string_agg, sqlite'ta group_concat (testler sqlite koşar).

**G137 (plan §4.2) — kullanılabilirlik katmanı:** her kolonun `grup`u (kaynağa
göre KAPALI küme, `VeriKaynagi.gruplar`), tipten türetilen `kontrol`
(`KONTROLLER`), `onerili` metin kolonlarda DISTINCT öneri listesi
(`onerileri_getir`: tenant + soft-delete kurallı, boş hariç, ≤`ONERI_MAX`,
aşarsa `oneri_kesik`); kaynağa `hizli_filtreler` + `kolon_setleri`.
Türetilmiş kolon kuralı gevşedi: `filtrelenebilir` artık KOLON BAZINDA —
filtrelenebilir türetilmiş kolon `filtre_ifadesi` (EXISTS üreten fonksiyon)
taşımak ZORUNDA ve `izinli_oplar` ile tip tablosunun alt kümesine daralır;
`siralanabilir=False` kalır. Taraf bağlantılı dört dava kolonu
(`muvekkil_adlari`, `karsi_taraf_adlari`, `sigortali_adlari`,
`muvekkil_kategorisi`) `case_parties` (→ `clients`) EXISTS'iyle süzülür;
silinmiş müvekkil kartı sayılmaz, tenant kuralı `cases` üzerinden gelir.

**G141 (plan §5) — kontrol türü kolon TİPİNDEN değil VERİDEN:** "birden fazla şehir
seçilemiyor" sınıfı sorunun kökü `kontrol`ün tipten türemesiydi. `veriden_liste`
işaretli metin kolonda (`il`, `court`, `responsible_lawyer_name`…) tenant +
soft-delete kurallı DISTINCT değer sayısı `settings.rapor_secenek_esigi`
(env `RAPOR_SECENEK_ESIGI`, varsayılan 100) eşiğini aşmıyorsa katalog
`kontrol="coklu_secim"` + `secenekler` (SIKLIĞA göre azalan, sonra ad) +
`secenek_kaynagi="veri"` verir; aşıyorsa G137 davranışı (`metin_icerir` +
`oneriler`). `tip` metin KALIR (op tablosu değişmez). Sabit `liste` kolonda
`secenek_kaynagi="sabit"`; `secenek_etiketleri` ham kod saklanan alanda gösterim
haritasıdır (`client_type`), filtre değeri ham gider. Her kaynağın sanal `arama`
kolonu (`secilebilir=False`, yalnız `contains`) birden çok kolonda OR'lu ILIKE
arar; kolon listesine/sıralamaya giremez, kolon setlerinde yok. `HizliFiltre.sunum`
(`SUNUMLAR`) + `etiket` frontend şeridinin (plan §5.3) sunum ipucudur;
`_kendini_denetle` sunum-kolon uyumunu import anında zorlar.

**G145 (plan §7.2) — seçenek sayıları + boş sayısı:** `secenekler` dolu her kolonda
`secenek_sayilari` (`{deger: n}`) ve sıra SAYIYA göre azalan (eşitlikte sabit listenin
kendi sırası / veriden: ad; sıfırlılar listede KALIR, sonda). Sabit `liste` kolonda
sayı kaynağın `kisitlar(tenant_id)` ile kaynak başına TEK `GROUP BY` (UNION ALL)
sorgusundan gelir (`liste_sayilari` → `secenekleri_sayili_getir`) — bu G130'un DISTINCT katmanının da yerine geçer,
yani panelden eklenmemiş "veride görülen" değerler artık tenant + soft-delete
kurallıdır (veriden liste ve önerilerle aynı kural, K2). Türetilmiş `liste` kolonda
(`muvekkil_kategorisi`: EXISTS başına GROUP BY pahalı) sayı hesaplanmaz → `null`,
sıra değişmez. `bos_sayisi` filtrelenebilir + `is_null` izinli + türetilmiş OLMAYAN
her kolonda: kaynak başına TEK `SUM(CASE …)` sorgusu (`bos_sayilari`); metin/liste
kolonda `IS NULL OR TRIM(col) = ''` — motorun `is_null`/`not_null`/`in [null]` filtreleri de
metin/liste kolonda AYNI koşulu kullanır (`motor._bos`, 07.09 kararı): rozetle sonuç eşit.
Asistan katalog metnine sayılar girmez (`secenekleri_getir(db=None)` yolu aynı).

**G166 — bağlı kaynak kolonları (kaynaklar arası birleştirme):** "Nisan'dan sonra açılan
davaların ofis no + müvekkil adı + müvekkil telefonu" gibi istekler tek kaynakta
karşılanamıyordu (telefon `muvekkiller`de, açılış tarihi `davalar`da). Çözüm K1'i
bozmadan: her kaynak `iliskiler` ile bağlı kaynaklar bildirir (`Iliski`), bağlı kaynağın
kolonları ana kataloğa `<iliski>.<kolon>` anahtarı (`muvekkil.phone`), `"<İlişki> · <Etiket>"`
etiketi ve `"<İlişki> · <Grup>"` grubuyla TÜRETİLİR (`_bagli_kolonlar`) — elle kolon
listesi yok, hedef kaynağa eklenen kolon bağlı tarafta kendiliğinden görünür.
İki bağ biçimi: **çoklu** (`coklu=True`, `kume` correlated satır kümesi — davalar→müvekkil
kartı `case_parties`/`kart_eslesmesi`, davalar→föy, davalar→belge, müvekkiller→dava):
seçim değerleri `GROUP BY` ile tekilleştirilip `AYRAC` ile birleşir (tarih/sayı metne cast),
filtre EXISTS ("herhangi bir bağlı kaydın kolonu"; `is_null` = dolu değerli bağlı kayıt yok),
sıralama yok; **tekil** (`coklu=False`, hedef tablo zaten `from_clause` JOIN'inde — belgeler/
föyler→dava): kolon aynen kopyalanır, filtre/sıralama/boş sayısı/veriden liste düz kolon gibi
çalışır. Bağlı kolonun `bag` alanı ilişki anahtarını taşır; asistan katalog metni bağlı
kolonları tek tek değil ilişki başına bir satırla gömer (`asistan.katalog_metni`).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Mapping, Optional, overload

import datetime as dt

from sqlalchemy import (
    Boolean, Date, DateTime, Integer, Numeric, Select, String, and_, cast, func, literal, null, or_, select,
    union_all,
)
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

import models
from auth_helpers import tenant_filter_clause
from config.settings import settings
from managers.seed_data import (
    APPEAL_DECISIONS, APPEALING_PARTIES, CASSATION_DECISIONS, CLIENT_TYPES, CURRENCIES, EVENT_TYPES,
    JUDGMENT_ROLES, LOCAL_DECISIONS, REVISION_DECISIONS, SERVICE_TYPES,
)
from required_fields import MISSING_BUCKETS
from schemas_rapor import TIP_OPLARI

AYRAC = " ; "
ONERI_MAX = 300           # plan §4.2: öneri listesi tavanı; aşarsa ilk 300 + `oneri_kesik`

# Tip → filtre kontrolü (plan §4.2; filtrelenemeyen kolonda `kontrol=null`).
KONTROLLER: dict[str, str] = {
    "tarih": "tarih_araligi",
    "liste": "coklu_secim",
    "metin": "metin_icerir",
    "sayi": "sayi_araligi",
    "para": "sayi_araligi",
    "mantik": "mantik",
}

# Hızlı filtre sunumları (plan §5.2/§5.3): `arama` yalnız `arama` kolonunda, `cipler` yalnız
# seçenekli kolonda (liste ya da veriden liste), `var_yok` yalnız sayı/para, `bos_anahtari`
# `is_null` alan her kolonda; `varsayilan` kontrol türüne göre (G137 davranışı).
SUNUMLAR = ("varsayilan", "arama", "cipler", "var_yok", "bos_anahtari")
ARAMA_KOLONU = "arama"
ARAMA_GRUBU = "Arama"

# ─── Tipler ──────────────────────────────────────────────────────────────────

# Motorun türetilmiş filtreye verdiği atom koşul üreticisi: (ifade, op, değer) → koşul.
# ILIKE kaçışı ve `ne`/`in` semantiği motorda TEK yerde kalır (kopya yok).
AtomKosul = Callable[[Any, str, Any], Any]
FiltreIfadesi = Callable[[str, Any, AtomKosul], Any]


@dataclass(frozen=True)
class Kolon:
    anahtar: str
    etiket: str
    tip: str                      # metin | liste | tarih | sayi | para | mantik
    ifade: Any                    # SQLAlchemy ColumnElement (kolon ya da scalar alt sorgu)
    grup: str = ""                # plan §4.2 kümesi; `_grup(...)` doldurur, denetim boş bırakmaz
    filtrelenebilir: bool = True
    siralanabilir: bool = True
    turetilmis: bool = False
    secenekler: tuple[str, ...] = ()          # sabit çekirdek (liste tipinde zorunlu)
    # Referans listesi ORM modeli (`name`/`active`/`sequence`/`id` kolonlu); eski stil
    # Column() modelleri mypy'de öznitelik taşımadığı için `Any`.
    secenek_tablosu: Any = None
    # Seçeneklerin DISTINCT katmanı için kolon (türetilmiş liste kolonda; None → `ifade`).
    secenek_ifadesi: Any = None
    zaman_damgali: bool = False               # tarih tipinde DateTime kolon (gün aralığı karşılaştırması)
    onerili: bool = False                     # metin kolonda DISTINCT öneri listesi (plan §4.2)
    # Türetilmiş kolonda filtre koşulu üreticisi (EXISTS); None ise motor `ifade`yi kullanır.
    filtre_ifadesi: Optional[FiltreIfadesi] = None
    # Tip tablosunun (`TIP_OPLARI[tip]`) alt kümesi; None → tablo aynen.
    izinli_oplar: Optional[tuple[str, ...]] = None
    # Türetilmiş önerili kolonda öneri sorgusu: tenant_id → DISTINCT string Select (sıralı).
    oneri_sorgusu: Optional[Callable[[str], Select]] = None
    # G141: metin kolonda veriden kapalı liste (eşik altı → coklu_secim; `onerili` ZORUNLU — eşik
    # üstü G137 önerilerine düşer). Denetim: yalnız düz metin kolonda.
    veriden_liste: bool = False
    # Ham kod saklanan alanda gösterim etiketleri {deger: etiket}; filtre değeri HAM gider.
    secenek_etiketleri: Optional[Mapping[str, str]] = None
    # False → yalnız filtre alanı (sanal `arama`): kolon listesine/sıralamaya giremez.
    secilebilir: bool = True
    # Kullanıcıya yönelik kısa açıklama (arama kutusu yer tutucusu: hangi alanlarda arar).
    # Katalogda `aciklama`; G142 frontend isteğe bağlı okur (plan §5.2 şerhi 07.09).
    aciklama: Optional[str] = None
    # G166: bağlı kaynak kolonu — ilişki anahtarı (`muvekkil.phone` → "muvekkil"); düz kolonda None.
    bag: Optional[str] = None

    @property
    def oplar(self) -> tuple[str, ...]:
        return self.izinli_oplar if self.izinli_oplar is not None else TIP_OPLARI[self.tip]

    @property
    def kontrol(self) -> Optional[str]:
        """Tipten türeyen kontrol (G137). `veriden_liste` kolonda nihai kontrol veriye bağlıdır —
        `_kolon_katalogu` eşik sonucuna göre `coklu_secim`e çevirir."""
        return KONTROLLER[self.tip] if self.filtrelenebilir else None


@dataclass(frozen=True)
class HizliFiltre:
    alan: str
    alternatifler: tuple[str, ...] = ()       # yalnız tarih aralığı kontrolünde alan değiştirici
    sunum: str = "varsayilan"                 # `SUNUMLAR` (plan §5.2)
    etiket: Optional[str] = None              # anahtar metni ("Davası var", "E-postası yok")


@dataclass(frozen=True)
class KolonSeti:
    ad: str
    kolonlar: tuple[str, ...]


@dataclass(frozen=True)
class Iliski:
    """Bağlı kaynak (G166). `coklu=True`: `kume()` ana kaynağa correlated, hedef tablodan (JOIN'li)
    `select(literal(1))` — bağ koşulları + hedefin soft-delete kuralı içinde; seçim/filtre bunun
    üzerine kurulur. `coklu=False`: hedef tablo ana kaynağın `from_clause`unda zaten var (INNER JOIN),
    kolonlar aynen kopyalanır. `hedef_from`/`hedef_kisitlar` yalnız öneri sorgusu için (çoklu bağda
    önerili metin kolonun DISTINCT değerleri hedef kaynağın tenant + soft-delete kuralıyla)."""
    anahtar: str                              # anahtar öneki: "muvekkil" → "muvekkil.phone"
    etiket: str                               # "Müvekkil kartı" → etiket "Müvekkil kartı · Telefon"
    hedef: str                                # hedef kaynak anahtarı ("muvekkiller")
    coklu: bool
    kume: Optional[Callable[[], Select]] = None
    hedef_from: Any = None
    hedef_kisitlar: Optional[Callable[[str], list[ColumnElement]]] = None
    haric: frozenset[str] = frozenset()       # hedef kolonlarından alınmayanlar (anahtar)


@dataclass(frozen=True)
class VeriKaynagi:
    anahtar: str
    etiket: str
    aciklama: str
    from_clause: Any                          # Table ya da Join
    kisitlar: Callable[[str], list[ColumnElement]]
    kolonlar: dict[str, Kolon]
    varsayilan_kolonlar: tuple[str, ...]
    gruplar: tuple[str, ...]                  # kapalı grup kümesi (plan §4.2), sıralı
    hizli_filtreler: tuple[HizliFiltre, ...] = ()
    kolon_setleri: tuple[KolonSeti, ...] = ()
    birincil_anahtar: Any = field(default=None)   # deterministik sıralama için son kırıcı
    iliskiler: tuple[Iliski, ...] = ()        # G166 bağlı kaynaklar (kolonları `kolonlar`a türetilmiş)


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tip_bul(kolon) -> tuple[str, bool]:
    """SQLAlchemy kolon tipinden rapor tipi; ikinci değer DateTime mi."""
    t = kolon.type
    if isinstance(t, Boolean):
        return "mantik", False
    if isinstance(t, DateTime):
        return "tarih", True
    if isinstance(t, Date):
        return "tarih", False
    if isinstance(t, Numeric):
        return "para", False
    if isinstance(t, Integer):
        return "sayi", False
    return "metin", False


def _adlar(cift_listesi) -> tuple[str, ...]:
    """Seed sabiti `[(kod, ad), ...]` → adlar (denormalize ad saklanan alanlar için)."""
    return tuple(ad for _kod, ad in cift_listesi)


def _kolon(model, anahtar: str, etiket: str, *, liste: tuple[str, ...] | None = None,
           secenek_tablosu: Any = None, tip: Optional[str] = None, onerili: bool = False,
           veriden_liste: bool = False, secenek_etiketleri: Optional[Mapping[str, str]] = None) -> Kolon:
    """Düz tablo kolonu → Kolon. `liste` verilirse tip `liste` ve seçenekler dolu.
    `veriden_liste` (G141) metin kolonu eşik altında çoklu seçime çevirir; öneri katmanı
    eşik üstü yedeği olduğundan `onerili` otomatik açılır."""
    col = getattr(model, anahtar)
    bulunan, zaman = _tip_bul(col)
    if liste is not None or secenek_tablosu is not None:
        return Kolon(anahtar, etiket, "liste", col, secenekler=tuple(liste or ()),
                     secenek_tablosu=secenek_tablosu, secenek_etiketleri=secenek_etiketleri)
    return Kolon(anahtar, etiket, tip or bulunan, col, zaman_damgali=zaman, onerili=onerili or veriden_liste,
                 veriden_liste=veriden_liste, secenek_etiketleri=secenek_etiketleri)


def _turetilmis(anahtar: str, etiket: str, tip: str, ifade, *, filtrelenebilir: bool = False,
                filtre_ifadesi: Optional[FiltreIfadesi] = None, izinli_oplar: Optional[tuple[str, ...]] = None,
                onerili: bool = False, oneri_sorgusu: Optional[Callable[[str], Select]] = None,
                liste: tuple[str, ...] | None = None, secenek_tablosu: Any = None,
                secenek_ifadesi: Any = None, secilebilir: bool = True) -> Kolon:
    """Türetilmiş kolon: sıralanamaz; filtre yalnız `filtre_ifadesi` ile (plan §4.2)."""
    return Kolon(
        anahtar, etiket, tip, ifade, filtrelenebilir=filtrelenebilir, siralanabilir=False, turetilmis=True,
        secenekler=tuple(liste or ()), secenek_tablosu=secenek_tablosu, secenek_ifadesi=secenek_ifadesi,
        onerili=onerili, filtre_ifadesi=filtre_ifadesi, izinli_oplar=izinli_oplar, oneri_sorgusu=oneri_sorgusu,
        secilebilir=secilebilir,
    )


def _arama_filtresi(ifadeler: tuple[Any, ...], ek_filtreler: tuple[FiltreIfadesi, ...] = ()) -> FiltreIfadesi:
    """Sanal `arama` kolonunun koşulu: verilen kolonların HERHANGİ birinde `contains` (OR'lu ILIKE;
    kaçış motorun atom koşulundan) + isteğe bağlı EXISTS filtreleri (taraf adları)."""
    def filtre(op: str, deger: Any, atom: AtomKosul):
        return or_(*(atom(ifade, op, deger) for ifade in ifadeler), *(f(op, deger, atom) for f in ek_filtreler))
    return filtre


def _arama(*ifadeler: Any, aciklama: str, ek_filtreler: tuple[FiltreIfadesi, ...] = ()) -> Kolon:
    """Kaynağın sanal arama kolonu (plan §5.2): yalnız filtre (`secilebilir=False`), yalnız `contains`,
    seçim ifadesi yok (`NULL` — motor bu kolonu hiçbir zaman SELECT'e almaz, `tanimi_dogrula` 422 verir).
    `aciklama` arama kutusunun yer tutucusudur (hangi alanlarda aradığını söyler)."""
    return replace(
        _turetilmis(ARAMA_KOLONU, "Ara", "metin", null(), filtrelenebilir=True, secilebilir=False,
                    filtre_ifadesi=_arama_filtresi(ifadeler, ek_filtreler), izinli_oplar=("contains",)),
        grup=ARAMA_GRUBU, aciklama=aciklama,
    )


def _grup(grup: str, *kolonlar: Kolon) -> list[Kolon]:
    """Kolon demetine grup etiketi basar (plan §4.2 kümeleri)."""
    return [replace(k, grup=grup) for k in kolonlar]


def _sozluk(kolonlar: list[Kolon]) -> dict[str, Kolon]:
    sozluk: dict[str, Kolon] = {}
    for k in kolonlar:
        if k.anahtar in sozluk:
            raise ValueError(f"kayıt defterinde kolon tekrarı: {k.anahtar}")
        sozluk[k.anahtar] = k
    return sozluk


# ─── Tarih koşulu (motor + bağlı kolon filtresi ortak) ───────────────────────

def _gun_basi(gun: dt.date) -> dt.datetime:
    return dt.datetime.combine(gun, dt.time.min)


def _gun_sonrasi(gun: dt.date) -> dt.datetime:
    return _gun_basi(gun + dt.timedelta(days=1))


def tarih_kosulu(ifade: Any, zaman_damgali: bool, op: str, deger: Any):
    """Tarih kolonlarında karşılaştırma (G130 motorundan taşındı, G166 bağlı kolon EXISTS'i de
    kullanır); DateTime kolonda (`created_at` gibi) gün aralığı: eq = [gün, gün+1), lte = < gün+1.
    Gün sınırı DB oturumunun saat dilimine göredir (sqlite bind'ı `date` değil `datetime` ister).
    `op` ∈ eq | gte | lte | between (değersiz op'lar çağıranda elenir)."""
    if zaman_damgali:
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


def _bos_kosulu(kolon: Kolon):
    """Boş kayıt koşulu: metin/liste kolonda `IS NULL OR TRIM(col) = ''`, diğer tiplerde `IS NULL`."""
    if kolon.tip in ("metin", "liste"):
        return or_(kolon.ifade.is_(None), func.trim(kolon.ifade) == "")
    return kolon.ifade.is_(None)


# ─── G166: bağlı kaynak kolonları ────────────────────────────────────────────

def bag_anahtari(iliski: Iliski, kolon_anahtari: str) -> str:
    return f"{iliski.anahtar}.{kolon_anahtari}"


def _bagli_secim(iliski: Iliski, k: Kolon):
    """Çoklu bağda seçim ifadesi: bağlı kayıtların kolon değerleri tekil (`GROUP BY`) ve sıralı,
    `AYRAC` ile birleşik (scalar alt sorgu). Tarih/sayı/mantık metne cast edilir (Postgres
    `string_agg` metin ister; ISO tarih metni sıralamada da kronolojik). sqlite `group_concat`
    DISTINCT + ayraç birlikte almadığından tekilleştirme iç alt sorguda (iki motor aynı SQL)."""
    assert iliski.kume is not None
    deger = k.ifade if k.tip in ("metin", "liste") else cast(k.ifade, String)
    ic = (
        iliski.kume().with_only_columns(deger.label("v"))
        .where(~_bos_kosulu(k))
        .group_by(deger)
        .order_by(deger)
        .subquery()
    )
    return select(func.aggregate_strings(ic.c.v, AYRAC)).select_from(ic).scalar_subquery()


def _bagli_filtre(iliski: Iliski, k: Kolon) -> FiltreIfadesi:
    """Çoklu bağda EXISTS filtresi: `op` = "koşula uyan HERHANGİ bir bağlı kaydın kolonu";
    `is_null` = dolu değerli bağlı kayıt yok, `not_null` = var; `in` listesindeki `null` ("(boş)")
    `is_null` ile OR'lanır (`muvekkil_kategorisi` ile aynı anlam); tarih kolonunda `tarih_kosulu`
    (DateTime gün aralığı), diğerlerinde motorun atom koşulu."""
    def filtre(op: str, deger: Any, atom: AtomKosul):
        assert iliski.kume is not None
        kume = iliski.kume()
        dolu = kume.where(~_bos_kosulu(k))
        if op == "is_null":
            return ~dolu.exists()
        if op == "not_null":
            return dolu.exists()
        if op == "in" and any(d is None for d in deger):
            dolular = [d for d in deger if d is not None]
            if not dolular:
                return ~dolu.exists()
            return or_(~dolu.exists(), kume.where(atom(k.ifade, op, dolular)).exists())
        if k.tip == "tarih":
            return kume.where(tarih_kosulu(k.ifade, k.zaman_damgali, op, deger)).exists()
        return kume.where(atom(k.ifade, op, deger)).exists()
    return filtre


def _hedef_onerileri(iliski: Iliski, k: Kolon) -> Callable[[str], Select]:
    """Çoklu bağda önerili metin kolonun DISTINCT değerleri: HEDEF kaynağın tenant + soft-delete
    kuralıyla (bağ üzerinden değil — öneri listesi "hangi değerler var" sorusudur)."""
    assert iliski.hedef_from is not None and iliski.hedef_kisitlar is not None

    def sorgu(tenant_id: str) -> Select:
        assert iliski.hedef_kisitlar is not None
        return (
            select(k.ifade).distinct()
            .select_from(iliski.hedef_from)
            .where(and_(*iliski.hedef_kisitlar(tenant_id), k.ifade.isnot(None), k.ifade != ""))
            .order_by(k.ifade)
        )
    return sorgu


def _bagli_kolon(iliski: Iliski, k: Kolon) -> Kolon:
    anahtar = bag_anahtari(iliski, k.anahtar)
    etiket = f"{iliski.etiket} · {k.etiket}"
    grup = f"{iliski.etiket} · {k.grup}"
    if not iliski.coklu:
        # Tekil bağ: hedef tablo FROM'da; düz kolon düz kalır (filtre/sıralama/boş sayısı/veriden liste),
        # hedefin türetilmiş kolonları da (correlate hedef tabloya) aynen çalışır.
        return replace(k, anahtar=anahtar, etiket=etiket, grup=grup, bag=iliski.anahtar)
    onerili = k.onerili or k.veriden_liste
    return Kolon(
        anahtar, etiket, k.tip, _bagli_secim(iliski, k), grup=grup, filtrelenebilir=True, siralanabilir=False,
        turetilmis=True, secenekler=k.secenekler, secenek_tablosu=k.secenek_tablosu,
        secenek_ifadesi=k.ifade if k.tip == "liste" else None, zaman_damgali=k.zaman_damgali,
        onerili=onerili, filtre_ifadesi=_bagli_filtre(iliski, k),
        oneri_sorgusu=_hedef_onerileri(iliski, k) if onerili else None,
        secenek_etiketleri=k.secenek_etiketleri, bag=iliski.anahtar,
    )


def _bagli_kolonlar(iliski: Iliski, hedef_kolonlar: list[Kolon]) -> list[Kolon]:
    """Hedef kaynağın kolonlarından bağlı kolonlar: sanal `arama` ve `haric` daima atlanır; çoklu
    bağda hedefin türetilmiş kolonları da atlanır (iç içe birleştirme/EXISTS tanımsız)."""
    return [
        _bagli_kolon(iliski, k) for k in hedef_kolonlar
        if k.secilebilir and k.anahtar not in iliski.haric and not (iliski.coklu and k.turetilmis)
    ]


def _bag_gruplari(iliskiler: tuple[Iliski, ...], hedef_gruplari: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Bağlı kolon grupları `"<İlişki> · <Grup>"` — hedefin `Arama` grubu hariç, hedef sırasıyla."""
    return tuple(
        f"{i.etiket} · {g}" for i in iliskiler for g in hedef_gruplari[i.hedef] if g != ARAMA_GRUBU
    )


# ─── Kapalı liste çekirdekleri ───────────────────────────────────────────────
# cases.status: model şerhi (DERDEST | DANIŞ | MAHZEN) + CaseList.STATUS_ORDER.
DAVA_DURUMLARI = ("DANIŞ", "DERDEST", "KARAR", "ISTINAF", "TEMYIZ", "KAPALI", "MAHZEN")
# cases.case_stage: models.py şerhi + frontend trackingDraft.STAGES anahtarları.
DAVA_ASAMALARI = ("DERDEST", "KARAR", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME", "KESINLESME", "INFAZ", "KAPALI")
KARAR_TURLERI = ("KABUL", "RED", "KISMI_KABUL", "FERAGAT", "UZLASMA", "DUSME")   # trackingDraft.STAGE_FIELDS
KARAR_LEHINE = ("LEHINE", "ALEYHINE", "KISMI")
# file_types seed'i fonksiyon-yerel (seed_data._seed_file_types); çekirdek burada,
# tablo + DISTINCT katmanı panelden eklenenleri getirir.
DAVA_TURLERI = ("Ceza", "Hukuk", "İcra", "İdare", "İdari Yargı", "Arabuluculuk", "Savcılık", "Tahkim", "Vergi",
                "Danışmanlık")
BELGE_LINK_MODLARI = ("LINKED", "TEST", "UNLINKED")
BELGE_UPLOAD_DURUMLARI = ("pending", "uploaded", "failed")
BELGE_DONUSUM_DURUMLARI = ("pending", "failed")
FOY_DURUMLARI = ("DERDEST", "MAHZEN")
FOY_KAPSAM_DURUMLARI = ("SILINDI", "KAPSAM_DISI")
MUVEKKIL_ILETISIM_TURLERI = ("Client", "Other")
MUVEKKIL_TIPLERI_CARI = ("Individual", "Corporate")
# client_categories seed çekirdeği (NewClient.tsx / seed_data); tablo + DISTINCT katmanı panelden eklenenleri getirir.
MUVEKKIL_KATEGORILERI = ("Doktor", "Sağlık Çalışanı", "Hasta", "Kurum", "Özel Hastane", "Bireysel", "Sigorta Şirketi",
                         "Diğer")
CINSIYETLER = ("Erkek", "Kadın")                       # NewClient.tsx seçenekleri ("Belirtilmemiş" = NULL)
# file_statuses seed'i fonksiyon-yerel 38 ad (seed_data._seed_file_statuses); çekirdek
# sık kullanılanlar, kalanı tablo + DISTINCT katmanından gelir.
DOSYA_SON_DURUMLARI = ("Bilirkişide", "İstinafta", "Temyizde", "Karar Düzeltmede", "Kesin Lehe", "Kesin Aleyhe")
SIGORTALI_ROLU = "Sigortalı"                           # case_parties.role (her party_type)

# Taraf bağlantılı metin kolonların op alt kümesi (plan §4.2 tablosu)
TARAF_METIN_OPLARI = ("contains", "is_null", "not_null")
TARAF_KATEGORI_OPLARI = ("eq", "in", "is_null")


# ─── davalar ─────────────────────────────────────────────────────────────────

def _dava_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.Case.deleted_at.is_(None), tenant_filter_clause(models.Case, tenant_id)]


TarafKosulu = Callable[[Any], Any]     # (CaseParty) → koşul (party_type / role)


def _party_type(tur: str) -> TarafKosulu:
    return lambda P: P.party_type == tur


def _role(rol: str) -> TarafKosulu:
    return lambda P: P.role == rol


def _taraf_adlari(kosul: TarafKosulu):
    """Seçim ifadesi: koşula uyan tarafların adları `AYRAC` ile birleşik (scalar alt sorgu)."""
    P = models.CaseParty
    return (
        select(func.aggregate_strings(P.name, AYRAC))
        .where(and_(P.case_id == models.Case.id, kosul(P)))
        .correlate(models.Case)
        .scalar_subquery()
    )


def _taraf_filtresi(kosul: TarafKosulu) -> FiltreIfadesi:
    """EXISTS filtresi: `contains` = "koşula uyan HERHANGİ bir tarafın adı içerir"
    (birleşik metin üzerinde değil); `is_null` = böyle taraf yok, `not_null` = var.
    ILIKE kaçışı motorun atom koşulundan gelir (kopya yok)."""
    def filtre(op: str, deger: Any, atom: AtomKosul):
        P = models.CaseParty
        varlik = select(P.id).where(and_(P.case_id == models.Case.id, kosul(P))).correlate(models.Case)
        if op == "is_null":
            return ~varlik.exists()
        if op == "not_null":
            return varlik.exists()
        return varlik.where(atom(P.name, op, deger)).exists()
    return filtre


def _taraf_adi_onerileri(kosul: TarafKosulu) -> Callable[[str], Select]:
    """Öneri sorgusu: koşula uyan tarafların DISTINCT adları; dava tenant + soft-delete kurallı."""
    def sorgu(tenant_id: str) -> Select:
        P = models.CaseParty
        return (
            select(P.name).distinct()
            .select_from(P.__table__.join(models.Case.__table__, P.case_id == models.Case.id))
            .where(and_(*_dava_kisitlari(tenant_id), kosul(P), P.name.isnot(None), P.name != ""))
            .order_by(P.name)
        )
    return sorgu


def _ad_anahtari(ifade):
    """Taraf adı ↔ müvekkil kartı adı karşılaştırma anahtarı (SQL tarafı): büyük harf + 'İ'→'I'
    katlaması. `upper`/`replace` hem Postgres hem sqlite'ta var; en_US upper 'İ'yi korur, Türkçe
    yazımda 'İBRAHİM' ile 'IBRAHIM' eşleşsin diye katlanır. `party_check.normalize_person_name`
    kadar kapsamlı değil (unvan/diakritik yok) — bilinçli: SQL'de koşmalı, ölçüm 07.09 lokal:
    1.998 karttan 965'i isimle eşleşiyor, `client_id` ile yalnız 9 taraf satırı bağlı."""
    # 'ı' da katlanır: Postgres upper('ı')='I' zaten, sqlite (testler) ASCII dışını büyütmez.
    return func.replace(func.replace(func.upper(func.trim(ifade)), "İ", "I"), "ı", "I")


def kart_eslesmesi(P, M):
    """Taraf satırı ↔ müvekkil kartı bağı: `client_id` doluysa YALNIZ o (isim bakılmaz);
    boşsa ad anahtarı eşitliği. Veri gerçeği (07.09): 16.192 CLIENT taraf satırından 9'unda
    `client_id` dolu — yalnız id ile bağ, "Dava Sayısı"nı herkes için 0 gösteriyordu
    (kullanıcı bulgusu). `routes/clients.py` case-summary hâlâ yalnız id ile (kapsam dışı, NOT)."""
    return or_(
        P.client_id == M.id,
        and_(P.client_id.is_(None), _ad_anahtari(P.name) == _ad_anahtari(M.name)),
    )


def _muvekkil_kategorileri():
    """Seçim ifadesi: CLIENT tarafların (silinmemiş) müvekkil kartı kategorileri birleşik."""
    P, M = models.CaseParty, models.Client
    return (
        select(func.aggregate_strings(M.category, AYRAC))
        .select_from(P.__table__.join(M.__table__, kart_eslesmesi(P, M)))
        .where(and_(P.case_id == models.Case.id, P.party_type == "CLIENT", M.deleted_at.is_(None),
                    M.category.isnot(None)))
        .correlate(models.Case)
        .scalar_subquery()
    )


def _muvekkil_kategorisi_filtresi(op: str, deger: Any, atom: AtomKosul):
    """EXISTS `case_parties JOIN clients`: silinmiş müvekkil kartı sayılmaz (`clients.deleted_at IS NULL`);
    tenant kuralı `cases` üzerinden (K2). `is_null` = kategorili canlı müvekkil kartı olan CLIENT taraf yok.
    `in` listesindeki `null` (G141, "(boş)") aynı anlamdadır: "kategorili taraf yok" VEYA EXISTS(in dolu)
    — kartın kategorisi NULL olan bir taraf aramak DEĞİL (satır düzeyi `IS NULL` burada yanıltırdı)."""
    P, M = models.CaseParty, models.Client
    varlik = (
        select(P.id)
        .select_from(P.__table__.join(M.__table__, kart_eslesmesi(P, M)))
        .where(and_(P.case_id == models.Case.id, P.party_type == "CLIENT", M.deleted_at.is_(None)))
        .correlate(models.Case)
    )
    kategorisiz = ~varlik.where(M.category.isnot(None)).exists()
    if op == "is_null":
        return kategorisiz
    if op == "in" and any(d is None for d in deger):
        dolu = [d for d in deger if d is not None]
        if not dolu:
            return kategorisiz
        return or_(kategorisiz, varlik.where(atom(M.category, op, dolu)).exists())
    return varlik.where(atom(M.category, op, deger)).exists()


def _foy_sayisi():
    F = models.CaseFoy
    return select(func.count(F.id)).where(F.case_id == models.Case.id).correlate(models.Case).scalar_subquery()


def _belge_sayisi():
    D = models.CaseDocument
    return (
        select(func.count(D.id))
        .where(and_(D.case_id == models.Case.id, D.deleted_at.is_(None)))
        .correlate(models.Case)
        .scalar_subquery()
    )


def _skaler_filtre(ifade) -> FiltreIfadesi:
    """Türetilmiş SAYI kolonu (COUNT alt sorgusu) doğrudan karşılaştırılır — atom koşul aynı."""
    return lambda op, deger, atom: atom(ifade, op, deger)


_C = models.Case
_DAVA_GRUPLARI = (ARAMA_GRUBU, "Kimlik", "Taraflar", "Mahkeme ve konu", "Tarihler", "Tutarlar", "Karar ve aşama",
                  "Tıbbi", "Aktarım", "Sistem")
_DAVA_KOLONLARI: list[Kolon] = [
    # Plan §5.2: tek arama kutusu — ofis no / esas no / konu / mahkeme + müvekkil ve karşı taraf adları (EXISTS)
    _arama(_C.tracking_no, _C.esas_no, _C.subject, _C.court,
           aciklama="Ofis dosya no, esas no, konu, mahkeme veya taraf adı…",
           ek_filtreler=(_taraf_filtresi(_party_type("CLIENT")), _taraf_filtresi(_party_type("COUNTER")))),
    *_grup(
        "Kimlik",
        _kolon(_C, "tracking_no", "Ofis Dosya No"),
        _kolon(_C, "esas_no", "Esas No"),
        _kolon(_C, "status", "Durum", liste=DAVA_DURUMLARI),
        _kolon(_C, "file_type", "Dava Türü", liste=DAVA_TURLERI, secenek_tablosu=models.FileType),
        _kolon(_C, "sub_type", "Uzmanlık Alanı", veriden_liste=True),
        _kolon(_C, "sub_type_extra", "Ek Alt Kırılım"),
        _kolon(_C, "service_type", "Hizmet Tipi"),
        _kolon(_C, "bureau_type", "Büro Özel Türü", secenek_tablosu=models.BureauType,
               liste=("ALEYHE", "DR ÖZEL", "HASTANE ÖZEL MÜVEKKİL", "LEXİS", "RÜCU", "VEKALETLİ TAKİP",
                      "VEKALETSİZ TAKİP", "ÖZEL")),
        # Olay / müvekkil / hizmet (kapalı listeler, ad denormalize)
        _kolon(_C, "olay_turu", "Olay Türü", liste=_adlar(EVENT_TYPES), secenek_tablosu=models.EventType),
        _kolon(_C, "hukumdeki_rol", "Hükümdeki Rol", liste=_adlar(JUDGMENT_ROLES), secenek_tablosu=models.JudgmentRole),
        _kolon(_C, "muvekkil_tipi", "Müvekkil Tipi", liste=_adlar(CLIENT_TYPES), secenek_tablosu=models.ClientType),
        _kolon(_C, "hizmet_turu", "Hizmet Türü", liste=_adlar(SERVICE_TYPES), secenek_tablosu=models.ServiceType),
        _kolon(_C, "responsible_lawyer_name", "Sorumlu Avukat", veriden_liste=True),
        _kolon(_C, "uyap_lawyer_name", "UYAP Avukatı", veriden_liste=True),
    ),
    *_grup(
        "Taraflar",
        # Türetilmiş + filtrelenebilir (plan §4.2): EXISTS `case_parties`; sıralanamaz.
        _turetilmis("muvekkil_adlari", "Müvekkiller", "metin", _taraf_adlari(_party_type("CLIENT")),
                    filtrelenebilir=True, filtre_ifadesi=_taraf_filtresi(_party_type("CLIENT")),
                    izinli_oplar=TARAF_METIN_OPLARI, onerili=True,
                    oneri_sorgusu=_taraf_adi_onerileri(_party_type("CLIENT"))),
        _turetilmis("karsi_taraf_adlari", "Karşı Taraflar", "metin", _taraf_adlari(_party_type("COUNTER")),
                    filtrelenebilir=True, filtre_ifadesi=_taraf_filtresi(_party_type("COUNTER")),
                    izinli_oplar=TARAF_METIN_OPLARI, onerili=True,
                    oneri_sorgusu=_taraf_adi_onerileri(_party_type("COUNTER"))),
        _turetilmis("sigortali_adlari", "Sigortalılar", "metin", _taraf_adlari(_role(SIGORTALI_ROLU)),
                    filtrelenebilir=True, filtre_ifadesi=_taraf_filtresi(_role(SIGORTALI_ROLU)),
                    izinli_oplar=TARAF_METIN_OPLARI, onerili=True,
                    oneri_sorgusu=_taraf_adi_onerileri(_role(SIGORTALI_ROLU))),
        _turetilmis("muvekkil_kategorisi", "Müvekkil Kategorisi", "liste", _muvekkil_kategorileri(),
                    filtrelenebilir=True, filtre_ifadesi=_muvekkil_kategorisi_filtresi,
                    izinli_oplar=TARAF_KATEGORI_OPLARI, liste=MUVEKKIL_KATEGORILERI,
                    secenek_tablosu=models.ClientCategory, secenek_ifadesi=models.Client.category),
    ),
    *_grup(
        "Mahkeme ve konu",
        _kolon(_C, "court", "Mahkeme", veriden_liste=True),
        _kolon(_C, "judicial_unit", "Yargı Birimi", veriden_liste=True),
        _kolon(_C, "subject", "Dava Konusu"),
    ),
    *_grup(
        "Tarihler",
        _kolon(_C, "opening_date", "Açılış Tarihi"),
        _kolon(_C, "acceptance_date", "İş Kabul Tarihi"),
        _kolon(_C, "atama_tarihi", "Atama Tarihi"),
        _kolon(_C, "kesinlesme_tarihi", "Kesinleşme Tarihi"),
        _kolon(_C, "infaz_tarihi", "İnfaz Tarihi"),
        _kolon(_C, "arsiv_tarihi", "Arşiv Tarihi"),
    ),
    *_grup(
        "Tutarlar",
        _kolon(_C, "maddi_tazminat", "Maddi Tazminat"),
        _kolon(_C, "manevi_tazminat", "Manevi Tazminat"),
        _kolon(_C, "islah_tutari", "Islah Tutarı"),
        _kolon(_C, "dava_degeri", "Dava Değeri"),
        _kolon(_C, "para_birimi", "Para Birimi", liste=_adlar(CURRENCIES), secenek_tablosu=models.Currency),
        _kolon(_C, "hukmedilen_maddi", "Hükmedilen Maddi"),
        _kolon(_C, "hukmedilen_manevi", "Hükmedilen Manevi"),
        _kolon(_C, "hukmedilen_toplam", "Hükmedilen Toplam"),
    ),
    *_grup(
        "Karar ve aşama",
        _kolon(_C, "case_stage", "Aşama", liste=DAVA_ASAMALARI),
        _kolon(_C, "dosya_son_durumu", "Dosya Son Durumu", secenek_tablosu=models.FileStatus,
               liste=DOSYA_SON_DURUMLARI),
        # Yerel karar
        _kolon(_C, "karar_tarihi", "Karar Tarihi"),
        _kolon(_C, "karar_turu", "Karar Türü", liste=KARAR_TURLERI),
        _kolon(_C, "karar_lehine", "Karar Lehine", liste=KARAR_LEHINE),
        _kolon(_C, "yerel_karar_durumu", "Karar Durumu", secenek_tablosu=models.LocalDecision,
               liste=_adlar(LOCAL_DECISIONS)),
        _kolon(_C, "karar_no", "Karar No"),
        _kolon(_C, "karar_teblig_tarihi", "Karar Tebliğ Tarihi"),
        _kolon(_C, "karar_aciklama", "Karar Açıklaması"),
        # İstinaf
        _kolon(_C, "istinaf_basvuru_tarihi", "İstinaf Başvuru Tarihi"),
        _kolon(_C, "istinaf_basvuran_taraf", "İstinaf Başvuran Taraf", liste=_adlar(APPEALING_PARTIES),
               secenek_tablosu=models.AppealingParty),
        _kolon(_C, "istinaf_karar_durumu", "İstinaf Karar Durumu", secenek_tablosu=models.AppealDecision,
               liste=_adlar(APPEAL_DECISIONS)),
        _kolon(_C, "istinaf_karar_tarihi", "İstinaf Karar Tarihi"),
        _kolon(_C, "istinaf_mahkemesi", "İstinaf Mahkemesi"),
        _kolon(_C, "istinaf_esas_no", "İstinaf Esas No"),
        _kolon(_C, "istinaf_karar_no", "İstinaf Karar No"),
        _kolon(_C, "istinaf_karar_aciklama", "İstinaf Açıklaması"),
        _kolon(_C, "istinaf_teblig_tarihi", "İstinaf Tebliğ Tarihi"),
        # Temyiz
        _kolon(_C, "temyiz_basvuru_tarihi", "Temyiz Başvuru Tarihi"),
        _kolon(_C, "temyiz_karar_durumu", "Temyiz Karar Durumu", secenek_tablosu=models.CassationDecision,
               liste=_adlar(CASSATION_DECISIONS)),
        _kolon(_C, "temyiz_karar_tarihi", "Temyiz Karar Tarihi"),
        _kolon(_C, "temyiz_mahkemesi", "Temyiz Mahkemesi"),
        _kolon(_C, "temyiz_esas_no", "Temyiz Esas No"),
        _kolon(_C, "temyiz_karar_no", "Temyiz Karar No"),
        _kolon(_C, "temyiz_eden_durumu", "Temyiz Eden"),
        _kolon(_C, "temyiz_karar_aciklama", "Temyiz Açıklaması"),
        _kolon(_C, "temyiz_teblig_tarihi", "Temyiz Tebliğ Tarihi"),
        # Karar düzeltme
        _kolon(_C, "karar_duzeltme_durumu", "Karar Düzeltme Durumu", secenek_tablosu=models.RevisionDecision,
               liste=_adlar(REVISION_DECISIONS)),
        _kolon(_C, "karar_duzeltme_esas_no", "Karar Düzeltme Esas No"),
        _kolon(_C, "karar_duzeltme_karar_no", "Karar Düzeltme Karar No"),
        _kolon(_C, "karar_duzeltme_tarihi", "Karar Düzeltme Tarihi"),
        _kolon(_C, "karar_duzeltme_teblig_tarihi", "Karar Düzeltme Tebliğ Tarihi"),
        _kolon(_C, "karar_duzeltme_aciklama", "Karar Düzeltme Açıklaması"),
        _kolon(_C, "yeni_esas_no", "Yeni Esas No"),
        # Arabuluculuk
        _kolon(_C, "arabuluculuk_no", "Arabuluculuk No"),
        _kolon(_C, "arabuluculuk_karar_tarihi", "Arabuluculuk Karar Tarihi"),
    ),
    *_grup(
        "Tıbbi",
        # Tıbbi beşli: ÇOK DEĞERLİ metin (" ; " ayraçlı, G124) → liste DEĞİL, `contains` ile aranır.
        _kolon(_C, "tibbi_surec", "Tıbbi Süreç"),
        _kolon(_C, "tibbi_olay", "Tıbbi Olay"),
        _kolon(_C, "iddia_edilen_kusur", "İddia Edilen Kusur"),
        _kolon(_C, "hastada_olusan_zarar", "Hastada Oluşan Zarar"),
        _kolon(_C, "uygulanan_yontem", "Uygulanan Yöntem"),
    ),
    *_grup(
        "Aktarım",
        _kolon(_C, "klasor_no_2", "Eski Sistem No"),
        _kolon(_C, "hasar_dosya_no", "Hasar Dosya No"),
        _kolon(_C, "hukuk_no", "Hukuk No"),
        _kolon(_C, "tku_no", "TKU No"),
        _kolon(_C, "sistem_no", "Sistem No"),
        _kolon(_C, "missing_required_bucket", "Eksik Zorunlu Alan Kovası", liste=tuple(MISSING_BUCKETS)),
        _turetilmis("foy_sayisi", "Föy Sayısı", "sayi", _foy_sayisi()),
    ),
    *_grup(
        "Sistem",
        _kolon(_C, "id", "ID"),
        _kolon(_C, "active", "Aktif"),
        _turetilmis("belge_sayisi", "Belge Sayısı", "sayi", _belge_sayisi()),
        _kolon(_C, "created_at", "Oluşturulma"),
        _kolon(_C, "updated_at", "Güncellenme"),
    ),
]

_DAVA_VARSAYILAN = ("tracking_no", "esas_no", "muvekkil_adlari", "court", "subject", "status",
                    "responsible_lawyer_name", "opening_date")

DAVALAR = VeriKaynagi(
    anahtar="davalar",
    etiket="Davalar",
    aciklama="Dava kartları (silinmişler hariç); müvekkil/karşı taraf adları ve föy/belge sayıları türetilmiş.",
    from_clause=models.Case.__table__,
    kisitlar=_dava_kisitlari,
    kolonlar=_sozluk(_DAVA_KOLONLARI),
    varsayilan_kolonlar=_DAVA_VARSAYILAN,
    gruplar=_DAVA_GRUPLARI,
    # Plan §4.2 hızlı filtre listesi (sıralı); tarih alanının alternatifleri alan değiştirici.
    # Plan §5.2: `arama` başa (Davalar listesi başka değişmez).
    hizli_filtreler=(
        HizliFiltre(ARAMA_KOLONU, sunum="arama"),
        HizliFiltre("opening_date", ("karar_tarihi", "kesinlesme_tarihi", "created_at")),
        HizliFiltre("status"),
        HizliFiltre("responsible_lawyer_name"),
        HizliFiltre("court"),
        HizliFiltre("muvekkil_adlari"),
        HizliFiltre("muvekkil_kategorisi"),
        HizliFiltre("hizmet_turu"),
        HizliFiltre("maddi_tazminat"),
    ),
    kolon_setleri=(
        KolonSeti("Temel", _DAVA_VARSAYILAN),
        KolonSeti("Karar takibi", ("tracking_no", "esas_no", "court", "status", "case_stage", "karar_tarihi",
                                   "karar_turu", "karar_lehine", "kesinlesme_tarihi")),
        KolonSeti("Tazminat", ("tracking_no", "muvekkil_adlari", "court", "maddi_tazminat", "manevi_tazminat",
                               "hukmedilen_toplam", "dava_degeri", "para_birimi")),
        KolonSeti("Taraflar", ("tracking_no", "muvekkil_adlari", "karsi_taraf_adlari", "sigortali_adlari",
                               "muvekkil_kategorisi", "responsible_lawyer_name")),
    ),
    birincil_anahtar=models.Case.id,
)

# ─── muvekkiller ─────────────────────────────────────────────────────────────

def _muvekkil_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.Client.deleted_at.is_(None), tenant_filter_clause(models.Client, tenant_id)]


def _dava_sayisi():
    """Müvekkil kartının (silinmemiş) dava sayısı; bağ `kart_eslesmesi` (id ya da ad anahtarı),
    yalnız CLIENT taraf satırları (karşı taraf/üçüncü kişi olarak geçtiği davalar sayılmaz)."""
    P = models.CaseParty
    return (
        select(func.count(func.distinct(P.case_id)))
        .select_from(P.__table__.join(models.Case.__table__, P.case_id == models.Case.id))
        .where(and_(kart_eslesmesi(P, models.Client), P.party_type == "CLIENT",
                    models.Case.deleted_at.is_(None)))
        .correlate(models.Client)
        .scalar_subquery()
    )


_M = models.Client
_MUVEKKIL_GRUPLARI = (ARAMA_GRUBU, "Kimlik", "İletişim", "Vekalet", "Sınıflandırma", "Sistem")
_DAVA_SAYISI = _dava_sayisi()
# clients.client_type ham İngilizce kod saklar (Individual 1.898 / Corporate 99 / "Gerçek Kişi" 1 — 07.09
# ölçümü); gösterim etiketli, filtre değeri HAM (plan §5.2).
MUVEKKIL_TIPI_ETIKETLERI: Mapping[str, str] = {
    "Individual": "Gerçek kişi",
    "Corporate": "Tüzel kişi",
    "Gerçek Kişi": "Gerçek kişi (eski yazım)",
}
_MUVEKKIL_KOLONLARI: list[Kolon] = [
    # Plan §5.1/5.2: tek arama kutusu — ad · cari kod · e-posta · telefon · cep
    _arama(_M.name, _M.cari_kod, _M.email, _M.phone, _M.mobile_phone,
           aciklama="Ad, cari kod, e-posta veya telefon…"),
    *_grup(
        "Kimlik",
        _kolon(_M, "name", "Müvekkil Adı"),
        _kolon(_M, "cari_kod", "Cari Kod"),
        _kolon(_M, "birth_year", "Doğum Yılı"),
        _kolon(_M, "gender", "Cinsiyet", liste=CINSIYETLER),
    ),
    *_grup(
        "İletişim",
        _kolon(_M, "email", "E-posta"),
        _kolon(_M, "phone", "Telefon"),
        _kolon(_M, "mobile_phone", "Cep Telefonu"),
        _kolon(_M, "address", "Adres"),
        _kolon(_M, "il", "İl", veriden_liste=True),
    ),
    *_grup(
        "Vekalet",
        _kolon(_M, "yevmiye_no", "Yevmiye No"),
        _kolon(_M, "noterlik", "Noterlik", onerili=True),
        _kolon(_M, "vekaletname_tarihi", "Vekaletname Tarihi"),
        _kolon(_M, "vekil_avukatlar", "Vekil Avukatlar"),
        _kolon(_M, "gecerlilik_tarihi", "Geçerlilik Tarihi"),
        _kolon(_M, "vekalet_no", "Vekalet No"),
        _kolon(_M, "buro_vekalet_no", "Büro Vekalet No"),
    ),
    *_grup(
        "Sınıflandırma",
        _kolon(_M, "contact_type", "Kayıt Türü", liste=MUVEKKIL_ILETISIM_TURLERI),
        _kolon(_M, "client_type", "Müvekkil Türü", liste=MUVEKKIL_TIPLERI_CARI,
               secenek_etiketleri=MUVEKKIL_TIPI_ETIKETLERI),
        _kolon(_M, "category", "Kategori", secenek_tablosu=models.ClientCategory, liste=MUVEKKIL_KATEGORILERI),
        _kolon(_M, "specialty", "Uzmanlık", veriden_liste=True),
        # Sektör 597 farklı yazım (07.09 ölçümü) — gerçek serbest metin, yalnız öneri (G137)
        _kolon(_M, "sektor", "Sektör", onerili=True),
    ),
    *_grup(
        "Sistem",
        _kolon(_M, "id", "ID"),
        _kolon(_M, "active", "Aktif"),
        # Hızlı filtre (plan §4.2) → COUNT alt sorgusu doğrudan karşılaştırılır; sıralanamaz. Op tablosu
        # `sayi` ile aynı: COUNT hiç NULL olmadığından `is_null` boş küme döner ama §4.3 "boş olanlar"
        # anahtarı 422 yemez.
        _turetilmis("dava_sayisi", "Dava Sayısı", "sayi", _DAVA_SAYISI, filtrelenebilir=True,
                    filtre_ifadesi=_skaler_filtre(_DAVA_SAYISI)),
        _kolon(_M, "updated_at", "Güncellenme"),
    ),
]

_MUVEKKIL_VARSAYILAN = ("name", "cari_kod", "category", "il", "phone", "email", "dava_sayisi")

MUVEKKILLER = VeriKaynagi(
    anahtar="muvekkiller",
    etiket="Müvekkiller",
    aciklama="Cari kartlar (silinmişler hariç); dava sayısı silinmemiş davalardan türetilir.",
    from_clause=models.Client.__table__,
    kisitlar=_muvekkil_kisitlari,
    kolonlar=_sozluk(_MUVEKKIL_KOLONLARI),
    varsayilan_kolonlar=_MUVEKKIL_VARSAYILAN,
    gruplar=_MUVEKKIL_GRUPLARI,
    # Plan §5.2 müvekkil şeridi (sıralı): arama kutusu · kategori çipleri · il · uzmanlık · "Davası var"
    # anahtarı · "E-postası yok" · "Cep telefonu yok". Müvekkil Türü / Kayıt Türü / vekalet alanları
    # şeritte YOK ("+ Başka alan"dan ulaşılır, §5.1 madde 7).
    hizli_filtreler=(
        HizliFiltre(ARAMA_KOLONU, sunum="arama"),
        HizliFiltre("category", sunum="cipler"),
        HizliFiltre("il"),
        HizliFiltre("specialty"),
        HizliFiltre("dava_sayisi", sunum="var_yok", etiket="Davası var"),
        HizliFiltre("email", sunum="bos_anahtari", etiket="E-postası yok"),
        HizliFiltre("mobile_phone", sunum="bos_anahtari", etiket="Cep telefonu yok"),
    ),
    kolon_setleri=(
        KolonSeti("Temel", _MUVEKKIL_VARSAYILAN),
        KolonSeti("İletişim", ("name", "category", "phone", "mobile_phone", "email", "address", "il")),
        KolonSeti("Vekalet", ("name", "vekalet_no", "buro_vekalet_no", "vekaletname_tarihi", "gecerlilik_tarihi",
                              "noterlik")),
    ),
    birincil_anahtar=models.Client.id,
)


# ─── belgeler ────────────────────────────────────────────────────────────────

def _belge_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.CaseDocument.deleted_at.is_(None), *_dava_kisitlari(tenant_id)]


_D = models.CaseDocument
_BELGE_GRUPLARI = (ARAMA_GRUBU, "Belge", "Dava", "Yükleme", "Sistem")
_BELGE_KOLONLARI: list[Kolon] = [
    # Plan §5.2: dosya adı · dava ofis no · özet
    _arama(_D.original_filename, models.Case.tracking_no, _D.ai_summary,
           aciklama="Dosya adı, ofis dosya no veya özet…"),
    *_grup(
        "Belge",
        _kolon(_D, "original_filename", "Orijinal Dosya Adı"),
        _kolon(_D, "stored_filename", "Arşiv Dosya Adı"),
        _kolon(_D, "belge_turu_kodu", "Belge Türü Kodu"),
        _kolon(_D, "belge_turu_adi", "Belge Türü", veriden_liste=True),
        _kolon(_D, "muvekkil_adi", "Müvekkil"),
        _kolon(_D, "avukat_kodu", "Avukat Kodu"),
        _kolon(_D, "esas_no", "Esas No"),
        _kolon(_D, "ai_summary", "Özet"),
        _kolon(_D, "sharepoint_url", "SharePoint Bağlantısı"),
    ),
    *_grup(
        "Dava",
        _kolon(_D, "case_id", "Dava ID"),
        _turetilmis("dava_tracking_no", "Dava Ofis No", "metin", models.Case.tracking_no),
        _turetilmis("dava_subject", "Dava Konusu", "metin", models.Case.subject),
    ),
    *_grup(
        "Yükleme",
        _kolon(_D, "link_mode", "Bağlantı Modu", liste=BELGE_LINK_MODLARI),
        _kolon(_D, "upload_status", "Yükleme Durumu", liste=BELGE_UPLOAD_DURUMLARI),
        _kolon(_D, "conversion_status", "Dönüşüm Durumu", liste=BELGE_DONUSUM_DURUMLARI),
        _kolon(_D, "email_sent", "E-posta Gönderildi"),
        _kolon(_D, "uploaded_by", "Yükleyen", veriden_liste=True),
        _kolon(_D, "uploaded_by_email", "Yükleyen E-posta"),
        _kolon(_D, "uploaded_at", "Yükleme Tarihi"),
    ),
    *_grup(
        "Sistem",
        _kolon(_D, "id", "ID"),
    ),
]

_BELGE_VARSAYILAN = ("dava_tracking_no", "belge_turu_adi", "original_filename", "muvekkil_adi", "uploaded_by",
                     "uploaded_at")

BELGELER = VeriKaynagi(
    anahtar="belgeler",
    etiket="Belgeler",
    aciklama="Davaya bağlı belgeler (silinmiş belge ve silinmiş dava hariç).",
    from_clause=models.CaseDocument.__table__.join(
        models.Case.__table__, models.CaseDocument.case_id == models.Case.id
    ),
    kisitlar=_belge_kisitlari,
    kolonlar=_sozluk(_BELGE_KOLONLARI),
    varsayilan_kolonlar=_BELGE_VARSAYILAN,
    gruplar=_BELGE_GRUPLARI,
    hizli_filtreler=(
        HizliFiltre(ARAMA_KOLONU, sunum="arama"),
        HizliFiltre("uploaded_at"),
        HizliFiltre("belge_turu_adi"),
        HizliFiltre("uploaded_by"),
        HizliFiltre("link_mode"),
    ),
    kolon_setleri=(KolonSeti("Temel", _BELGE_VARSAYILAN),),
    birincil_anahtar=models.CaseDocument.id,
)


# ─── foyler ──────────────────────────────────────────────────────────────────

def _foy_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return list(_dava_kisitlari(tenant_id))


_F = models.CaseFoy
_FOY_GRUPLARI = (ARAMA_GRUBU, "Kimlik", "Sınıflandırma", "Kapsam", "Sistem")
_FOY_KOLONLARI: list[Kolon] = [
    # Plan §5.2: sistem no · TKU · hasar no · dava ofis no
    _arama(_F.sistem_no, _F.tku_no, _F.hasar_no, models.Case.tracking_no,
           aciklama="SistemNo, TKU, hasar no veya ofis dosya no…"),
    *_grup(
        "Kimlik",
        _kolon(_F, "sistem_no", "SistemNo"),
        _kolon(_F, "tku_no", "TKU"),
        _kolon(_F, "hasar_no", "Hasar No"),
        _kolon(_F, "mko_id", "MKO Föy"),
        _kolon(_F, "muvekkil_no", "Müvekkil No"),
        _kolon(_F, "case_id", "Dava ID"),
        _turetilmis("dava_tracking_no", "Dava Ofis No", "metin", models.Case.tracking_no),
        _turetilmis("dava_subject", "Dava Konusu", "metin", models.Case.subject),
    ),
    *_grup(
        "Sınıflandırma",
        _kolon(_F, "muvekkil_tipi", "Müvekkil Tipi", liste=_adlar(CLIENT_TYPES), secenek_tablosu=models.ClientType),
        _kolon(_F, "hizmet_turu", "Hizmet Türü", liste=_adlar(SERVICE_TYPES), secenek_tablosu=models.ServiceType),
        _kolon(_F, "durum", "Durum", liste=FOY_DURUMLARI),
    ),
    *_grup(
        "Kapsam",
        _kolon(_F, "kapsam_durumu", "Kapsam Durumu", liste=FOY_KAPSAM_DURUMLARI),
        _kolon(_F, "kapsam_gerekcesi", "Kapsam Gerekçesi"),
        _kolon(_F, "kapsam_tarihi", "Kapsam Tarihi"),
    ),
    *_grup(
        "Sistem",
        _kolon(_F, "id", "ID"),
        _kolon(_F, "source", "Kaynak Teslim"),
        _kolon(_F, "created_at", "Oluşturulma"),
        _kolon(_F, "updated_at", "Güncellenme"),
    ),
]

_FOY_VARSAYILAN = ("sistem_no", "tku_no", "dava_tracking_no", "muvekkil_tipi", "hizmet_turu", "durum")

FOYLER = VeriKaynagi(
    anahtar="foyler",
    etiket="Föyler",
    aciklama="Teslim föyleri (SistemNo) kart bağıyla; silinmiş davanın föyleri hariç, ham satır katalog dışı.",
    from_clause=models.CaseFoy.__table__.join(models.Case.__table__, models.CaseFoy.case_id == models.Case.id),
    kisitlar=_foy_kisitlari,
    kolonlar=_sozluk(_FOY_KOLONLARI),
    varsayilan_kolonlar=_FOY_VARSAYILAN,
    gruplar=_FOY_GRUPLARI,
    hizli_filtreler=(
        HizliFiltre(ARAMA_KOLONU, sunum="arama"),
        HizliFiltre("durum"),
        HizliFiltre("hizmet_turu"),
        HizliFiltre("muvekkil_tipi"),
        HizliFiltre("kapsam_durumu"),
    ),
    kolon_setleri=(KolonSeti("Temel", _FOY_VARSAYILAN),),
    birincil_anahtar=models.CaseFoy.id,
)


# ─── G166: bağlı kaynaklar ───────────────────────────────────────────────────
# Kaynaklar arası birleştirme: her kaynak bağlı kaynaklarını bildirir, kolonları `<iliski>.<kolon>`
# anahtarıyla türetilir. Çekirdek (bağsız) kaynaklar önce yakalanır — bağlı kolonlar HEP çekirdekten
# üretilir (bağın bağı yok: `muvekkil.dava.x` gibi ikinci derece anahtar üretilmez).

def _muvekkil_kumesi() -> Select:
    """Davanın CLIENT taraflarının (canlı) müvekkil kartları — `muvekkil_kategorisi` ile aynı bağ
    (`kart_eslesmesi`: `client_id` ya da ad anahtarı). `cases` FROM'da olan her kaynakta çalışır."""
    P, M = models.CaseParty, models.Client
    return (
        select(literal(1))
        .select_from(P.__table__.join(M.__table__, kart_eslesmesi(P, M)))
        .where(and_(P.case_id == models.Case.id, P.party_type == "CLIENT", M.deleted_at.is_(None)))
        .correlate(models.Case)
    )


def _foy_kumesi() -> Select:
    F = models.CaseFoy
    return select(literal(1)).select_from(F.__table__).where(F.case_id == models.Case.id).correlate(models.Case)


def _belge_kumesi() -> Select:
    D = models.CaseDocument
    return (
        select(literal(1)).select_from(D.__table__)
        .where(and_(D.case_id == models.Case.id, D.deleted_at.is_(None)))
        .correlate(models.Case)
    )


def _muvekkilin_davalari_kumesi() -> Select:
    """Müvekkil kartının CLIENT tarafı olduğu silinmemiş davalar (`dava_sayisi` ile aynı bağ)."""
    P = models.CaseParty
    return (
        select(literal(1))
        .select_from(P.__table__.join(models.Case.__table__, P.case_id == models.Case.id))
        .where(and_(kart_eslesmesi(P, models.Client), P.party_type == "CLIENT", models.Case.deleted_at.is_(None)))
        .correlate(models.Client)
    )


_JOIN_KOLONLARI = frozenset({"case_id", "dava_tracking_no", "dava_subject"})     # hedefte zaten dava bağı
MUVEKKIL_ILISKISI = Iliski("muvekkil", "Müvekkil kartı", "muvekkiller", coklu=True, kume=_muvekkil_kumesi,
                           hedef_from=models.Client.__table__, hedef_kisitlar=_muvekkil_kisitlari,
                           haric=frozenset({"dava_sayisi"}))
FOY_ILISKISI = Iliski("foy", "Föy", "foyler", coklu=True, kume=_foy_kumesi, hedef_from=FOYLER.from_clause,
                      hedef_kisitlar=_foy_kisitlari, haric=_JOIN_KOLONLARI)
BELGE_ILISKISI = Iliski("belge", "Belge", "belgeler", coklu=True, kume=_belge_kumesi,
                        hedef_from=BELGELER.from_clause, hedef_kisitlar=_belge_kisitlari, haric=_JOIN_KOLONLARI)
DAVA_ILISKISI_COKLU = Iliski("dava", "Dava", "davalar", coklu=True, kume=_muvekkilin_davalari_kumesi,
                             hedef_from=models.Case.__table__, hedef_kisitlar=_dava_kisitlari)
DAVA_ILISKISI_TEKIL = Iliski("dava", "Dava", "davalar", coklu=False)     # belgeler/foyler: cases zaten JOIN'de

CEKIRDEK: dict[str, VeriKaynagi] = {k.anahtar: k for k in (DAVALAR, MUVEKKILLER, BELGELER, FOYLER)}


def _bagla(kaynak: VeriKaynagi, *iliskiler: Iliski) -> VeriKaynagi:
    kolonlar = list(kaynak.kolonlar.values())
    for iliski in iliskiler:
        kolonlar.extend(_bagli_kolonlar(iliski, list(CEKIRDEK[iliski.hedef].kolonlar.values())))
    gruplar = kaynak.gruplar + _bag_gruplari(iliskiler, {a: k.gruplar for a, k in CEKIRDEK.items()})
    return replace(kaynak, kolonlar=_sozluk(kolonlar), gruplar=gruplar, iliskiler=tuple(iliskiler))


DAVALAR = _bagla(DAVALAR, MUVEKKIL_ILISKISI, FOY_ILISKISI, BELGE_ILISKISI)
MUVEKKILLER = _bagla(MUVEKKILLER, DAVA_ILISKISI_COKLU)
BELGELER = _bagla(BELGELER, DAVA_ILISKISI_TEKIL, MUVEKKIL_ILISKISI)
FOYLER = _bagla(FOYLER, DAVA_ILISKISI_TEKIL, MUVEKKIL_ILISKISI)


# ─── Kayıt defteri ───────────────────────────────────────────────────────────

KAYNAKLAR: dict[str, VeriKaynagi] = {
    k.anahtar: k for k in (DAVALAR, MUVEKKILLER, BELGELER, FOYLER)
}

# Kataloga girmesi YASAK kolon adları — kayıt defteri kendi kendini denetler.
YASAK_KOLONLAR = frozenset({"tenant_id", "deleted_at", "deleted_by", "delete_reason", "notes", "ham_veri", "tc_no"})


def _kolonu_denetle(kaynak: VeriKaynagi, kolon: Kolon) -> None:
    ad = f"{kaynak.anahtar}.{kolon.anahtar}"
    if kolon.anahtar in YASAK_KOLONLAR:
        raise ValueError(f"{ad} kataloga giremez")
    if kolon.tip == "liste" and not kolon.secenekler and kolon.secenek_tablosu is None:
        raise ValueError(f"{ad}: seçeneksiz liste kolon")
    if kolon.tip == "liste" and not kolon.turetilmis and _tip_bul(kolon.ifade)[0] != "metin":
        # G145: `liste_sayilari` UNION ALL'ı düz liste kolonlarını tek `deger` sütununda birleştirir
        raise ValueError(f"{ad}: düz liste kolonun DB tipi metin olmalı (UNION ALL tip uyumu)")
    if not kolon.grup or kolon.grup not in kaynak.gruplar:
        raise ValueError(f"{ad}: grup kaynağın kapalı kümesinde değil: {kolon.grup!r}")
    if kolon.turetilmis:
        if kolon.siralanabilir:
            raise ValueError(f"{ad}: türetilmiş kolon sıralanamaz")
        if kolon.filtrelenebilir and kolon.filtre_ifadesi is None:
            raise ValueError(f"{ad}: filtrelenebilir türetilmiş kolonun filtre_ifadesi yok")
    elif kolon.filtre_ifadesi is not None:
        raise ValueError(f"{ad}: filtre_ifadesi yalnız türetilmiş kolonda")
    if kolon.izinli_oplar is not None:
        if not kolon.izinli_oplar or not set(kolon.izinli_oplar) <= set(TIP_OPLARI[kolon.tip]):
            raise ValueError(f"{ad}: izinli_oplar tip tablosunun boş olmayan alt kümesi olmalı")
    if kolon.onerili:
        if kolon.tip != "metin":
            raise ValueError(f"{ad}: öneri yalnız metin kolonda")
        if kolon.turetilmis and kolon.oneri_sorgusu is None:
            raise ValueError(f"{ad}: önerili türetilmiş kolonun oneri_sorgusu yok")
    if kolon.veriden_liste:
        # Eşik üstü yedeği G137 önerileri: `onerili` şart; türetilmişte GROUP BY ifadesi tanımsız
        if kolon.tip != "metin" or kolon.turetilmis or not kolon.onerili:
            raise ValueError(f"{ad}: veriden liste yalnız düz, önerili metin kolonda")
    if kolon.secenek_etiketleri is not None and kolon.tip != "liste" and not kolon.veriden_liste:
        raise ValueError(f"{ad}: seçenek etiketleri yalnız seçenekli kolonda")
    if not kolon.secilebilir:
        if not (kolon.turetilmis and kolon.filtrelenebilir) or kolon.siralanabilir:
            raise ValueError(f"{ad}: seçilemeyen kolon yalnız filtrelenebilir türetilmiş olabilir")
        if kolon.grup != ARAMA_GRUBU:
            raise ValueError(f"{ad}: seçilemeyen kolon '{ARAMA_GRUBU}' grubunda olmalı")
    elif kolon.grup == ARAMA_GRUBU:
        raise ValueError(f"{ad}: '{ARAMA_GRUBU}' grubu yalnız seçilemeyen kolon içindir")


def _hizli_filtreyi_denetle(kaynak: VeriKaynagi, hf: HizliFiltre) -> None:
    """Sunum ↔ kolon uyumu (plan §5.2): `arama` yalnız `arama` kolonunda; `cipler` yalnız seçenekli
    kolonda; `var_yok` yalnız sayı/para; `bos_anahtari` `is_null` alan kolonda; `etiket` yalnız anahtar
    sunumlarında anlamlı (var_yok / bos_anahtari)."""
    ad = f"{kaynak.anahtar}: hızlı filtre {hf.alan}"
    kolon = kaynak.kolonlar[hf.alan]
    if hf.sunum not in SUNUMLAR:
        raise ValueError(f"{ad}: tanınmayan sunum {hf.sunum!r}")
    if (hf.sunum == "arama") != (hf.alan == ARAMA_KOLONU):
        raise ValueError(f"{ad}: 'arama' sunumu yalnız ve ancak '{ARAMA_KOLONU}' kolonunda")
    if hf.sunum == "cipler" and kolon.tip != "liste" and not kolon.veriden_liste:
        raise ValueError(f"{ad}: 'cipler' sunumu yalnız seçenekli kolonda")
    if hf.sunum == "var_yok" and kolon.tip not in ("sayi", "para"):
        raise ValueError(f"{ad}: 'var_yok' sunumu yalnız sayı/para kolonda")
    if hf.sunum == "bos_anahtari" and "is_null" not in kolon.oplar:
        raise ValueError(f"{ad}: 'bos_anahtari' sunumu is_null izinli kolon ister")
    if hf.etiket is not None and hf.sunum not in ("var_yok", "bos_anahtari"):
        raise ValueError(f"{ad}: etiket yalnız anahtar sunumlarında (var_yok / bos_anahtari)")
    if hf.alternatifler and (kolon.tip != "tarih" or hf.sunum != "varsayilan"):
        raise ValueError(f"{ad}: alternatifler yalnız tarih hızlı filtresinde (varsayılan sunum)")


def _kendini_denetle() -> None:
    for kaynak in KAYNAKLAR.values():
        if len(set(kaynak.gruplar)) != len(kaynak.gruplar) or not kaynak.gruplar:
            raise ValueError(f"{kaynak.anahtar}: grup kümesi boş ya da tekrarlı")
        iliskiler = {i.anahtar: i for i in kaynak.iliskiler}
        if len(iliskiler) != len(kaynak.iliskiler):
            raise ValueError(f"{kaynak.anahtar}: ilişki anahtarı tekrarlı")
        for iliski in kaynak.iliskiler:
            # G166: ilişki anahtarı düz bir kolon adıyla çakışmaz; hedef katalogda; çoklu bağ kümeli
            if iliski.hedef not in CEKIRDEK or iliski.hedef == kaynak.anahtar:
                raise ValueError(f"{kaynak.anahtar}: ilişki hedefi geçersiz: {iliski.hedef}")
            if iliski.coklu != (iliski.kume is not None):
                raise ValueError(f"{kaynak.anahtar}.{iliski.anahtar}: çoklu bağ `kume` ister, tekil bağ istemez")
            if not any(k.bag == iliski.anahtar for k in kaynak.kolonlar.values()):
                raise ValueError(f"{kaynak.anahtar}.{iliski.anahtar}: ilişkinin hiç kolonu yok")
        for kolon in kaynak.kolonlar.values():
            _kolonu_denetle(kaynak, kolon)
            if kolon.bag is not None:
                if kolon.bag not in iliskiler or not kolon.anahtar.startswith(kolon.bag + "."):
                    raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar}: bağ ilişkisi bildirilmemiş: {kolon.bag}")
                if iliskiler[kolon.bag].coklu and not (kolon.turetilmis and kolon.filtrelenebilir):
                    raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar}: çoklu bağ kolonu türetilmiş+filtrelenebilir olmalı")
            elif "." in kolon.anahtar:
                raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar}: nokta yalnız bağlı kolon anahtarında")
        for anahtar in kaynak.varsayilan_kolonlar:
            if anahtar not in kaynak.kolonlar:
                raise ValueError(f"{kaynak.anahtar}: varsayılan kolon katalogda yok: {anahtar}")
            if not kaynak.kolonlar[anahtar].secilebilir:
                raise ValueError(f"{kaynak.anahtar}: varsayılan kolon seçilemez: {anahtar}")
        gorulen: set[str] = set()
        for hf in kaynak.hizli_filtreler:
            for anahtar in (hf.alan, *hf.alternatifler):
                kolon = kaynak.kolonlar.get(anahtar)
                if kolon is None or not kolon.filtrelenebilir:
                    raise ValueError(f"{kaynak.anahtar}: hızlı filtre katalogda yok ya da filtrelenemez: {anahtar}")
            _hizli_filtreyi_denetle(kaynak, hf)
            if hf.alan in gorulen:
                raise ValueError(f"{kaynak.anahtar}: hızlı filtre tekrarı: {hf.alan}")
            gorulen.add(hf.alan)
        adlar: set[str] = set()
        for ks in kaynak.kolon_setleri:
            if not ks.ad or ks.ad in adlar or not ks.kolonlar:
                raise ValueError(f"{kaynak.anahtar}: kolon seti adı boş/tekrarlı ya da set boş: {ks.ad!r}")
            adlar.add(ks.ad)
            for anahtar in ks.kolonlar:
                if anahtar not in kaynak.kolonlar:
                    raise ValueError(f"{kaynak.anahtar}: kolon seti '{ks.ad}' katalogda olmayan kolon: {anahtar}")
                if not kaynak.kolonlar[anahtar].secilebilir:
                    raise ValueError(f"{kaynak.anahtar}: kolon seti '{ks.ad}' seçilemeyen kolon içeriyor: {anahtar}")


_kendini_denetle()


def kaynak_bul(anahtar: str) -> Optional[VeriKaynagi]:
    return KAYNAKLAR.get(anahtar)


def secenekleri_getir(kolon: Kolon, db: Optional[Session]) -> list[str]:
    """`liste` kolonun seçenekleri: sabit çekirdek + referans tablosu (aktif) +
    kolondaki DISTINCT değerler; sıra korunur, tekrar yok, boş/None atlanır.
    `db` yoksa yalnız sabit çekirdek döner (asistan prompt'u için yeterli).
    Türetilmiş liste kolonda DISTINCT katmanı `secenek_ifadesi` kolonundan gelir
    (`muvekkil_kategorisi` → `clients.category`); yoksa katman atlanır."""
    if kolon.tip != "liste":
        return []
    gorulen: dict[str, None] = dict.fromkeys(kolon.secenekler)
    if db is not None:
        if kolon.secenek_tablosu is not None:
            T = kolon.secenek_tablosu
            satirlar = db.execute(
                select(T.name).where(T.active.is_(True)).order_by(T.sequence, T.id)
            ).scalars()
            for ad in satirlar:
                if ad:
                    gorulen.setdefault(str(ad))
        ifade = kolon.secenek_ifadesi if kolon.secenek_ifadesi is not None else (
            None if kolon.turetilmis else kolon.ifade
        )
        if ifade is not None:
            mevcut = db.execute(
                select(func.distinct(ifade)).where(ifade.isnot(None)).order_by(ifade)
            ).scalars()
            for deger in mevcut:
                if deger not in (None, ""):
                    gorulen.setdefault(str(deger))
    return list(gorulen)


def _sayiya_gore_sirala(secenekler: list[str], sayilar: Mapping[str, int]) -> list[str]:
    """Plan §7.2 sırası: sayıya göre azalan; eşitlikte verilen sıra (kararlı sıralama —
    sabit çekirdek → tablo → veriden ad sırası) korunur; sıfırlılar doğal olarak sonda."""
    return sorted(secenekler, key=lambda d: -sayilar.get(d, 0))


def _duz_liste_kolonlari(kaynak: VeriKaynagi) -> list[Kolon]:
    """Sayısı hesaplanan liste kolonları: düz (türetilmiş olmayan) `liste` tipi."""
    return [k for k in kaynak.kolonlar.values() if k.tip == "liste" and not k.turetilmis]


def liste_sayilari(kaynak: VeriKaynagi, db: Optional[Session], tenant_id: str,
                   kolonlar: Optional[list[Kolon]] = None) -> dict[str, dict[str, int]]:
    """Kaynağın düz `liste` kolonlarında veride görülen değerlerin sayıları
    `{kolon_anahtari: {deger: n}}` — kaynak başına TEK sorgu (G145 ölçümü 07.09, lokal 14.5k dava:
    18 ayrı GROUP BY 95 ms → UNION ALL tek sorgu 42 ms; GROUPING SETS 23 ms ama Postgres'e özel,
    testler sqlite koşar → dialect-bağımsız UNION ALL seçildi). Her parça kaynağın
    `kisitlar(tenant_id)` ile `GROUP BY kolon` (tenant + soft-delete, K2), NULL/"" hariç; UNION ALL
    tip uyumu için düz liste kolonun DB tipi metin olmalı (`_kolonu_denetle` zorlar). İç sözlük
    değere göre alfabetik (Python sırası — sqlite/Postgres collation farkı katalog sırasına sızmaz).
    `db` yoksa ya da kolon yoksa `{}`."""
    if db is None:
        return {}
    if kolonlar is None:
        kolonlar = _duz_liste_kolonlari(kaynak)
    if not kolonlar:
        return {}
    parcalar = [
        select(literal(k.anahtar).label("kolon"), k.ifade.label("deger"), func.count().label("n"))
        .select_from(kaynak.from_clause)
        .where(and_(*kaynak.kisitlar(tenant_id), k.ifade.isnot(None), k.ifade != ""))
        .group_by(k.ifade)
        for k in kolonlar
    ]
    sorgu = union_all(*parcalar) if len(parcalar) > 1 else parcalar[0]
    sonuc: dict[str, dict[str, int]] = {k.anahtar: {} for k in kolonlar}
    for kolon_adi, deger, sayi in db.execute(sorgu).all():
        sonuc[str(kolon_adi)][str(deger)] = int(sayi)
    return {ad: dict(sorted(sayilar.items())) for ad, sayilar in sonuc.items()}


def secenekleri_sayili_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str,
                             veri_sayilari: Optional[Mapping[str, int]] = None,
                             ) -> tuple[list[str], Optional[dict[str, int]]]:
    """`liste` kolonun seçenekleri + kayıt sayıları (G145). Düz kolonda sabit çekirdek + referans
    tablosu (aktif) + veride görülen değerler (`veri_sayilari`; verilmezse `liste_sayilari` bu kolon
    için koşar) — DISTINCT katmanının tenant kurallı ikizi; eşleşmeyen sabit değer `0`; sıra
    `_sayiya_gore_sirala`. Türetilmiş liste kolonda (`secenek_ifadesi`) sayı hesaplanmaz →
    (`secenekleri_getir` sırası, `None`). `db` yoksa (sabit çekirdek, `None`)."""
    if kolon.tip != "liste":
        return [], None
    if db is None or kolon.turetilmis:
        return secenekleri_getir(kolon, db), None
    gorulen: dict[str, None] = dict.fromkeys(kolon.secenekler)
    if kolon.secenek_tablosu is not None:
        T = kolon.secenek_tablosu
        for ad in db.execute(select(T.name).where(T.active.is_(True)).order_by(T.sequence, T.id)).scalars():
            if ad:
                gorulen.setdefault(str(ad))
    if veri_sayilari is None:
        veri_sayilari = liste_sayilari(kaynak, db, tenant_id, [kolon]).get(kolon.anahtar, {})
    for deger in veri_sayilari:
        gorulen.setdefault(deger)
    secenekler = _sayiya_gore_sirala(list(gorulen), veri_sayilari)
    return secenekler, {d: veri_sayilari.get(d, 0) for d in secenekler}


def bos_sayilari(kaynak: VeriKaynagi, db: Optional[Session], tenant_id: str) -> dict[str, int]:
    """Kaynağın boş kayıt sayıları `{kolon_anahtari: n}` — TEK sorgu (plan §7.2): filtrelenebilir,
    `is_null` izinli, türetilmiş OLMAYAN her kolon için `COUNT(*) FILTER (WHERE <boş>)` (Postgres ve
    sqlite ≥3.30 — konteyner 3.46; ölçüm 07.09: `SUM(CASE)` 44 ms → FILTER 34 ms, davalar);
    boş koşulu `_bos_kosulu`. Kaynağın `kisitlar(tenant_id)` uygulanır (tenant + soft-delete, K2).
    Satır yoksa `0`. `db` yoksa `{}`."""
    if db is None:
        return {}
    kolonlar = [k for k in kaynak.kolonlar.values()
                if k.filtrelenebilir and not k.turetilmis and "is_null" in k.oplar]
    if not kolonlar:
        return {}
    sorgu = (
        select(*(func.count().filter(_bos_kosulu(k)).label(k.anahtar) for k in kolonlar))
        .select_from(kaynak.from_clause)
        .where(and_(*kaynak.kisitlar(tenant_id)))
    )
    satir = db.execute(sorgu).one()
    return {k.anahtar: int(satir._mapping[k.anahtar]) for k in kolonlar}


def _oneri_sorgusu(kaynak: VeriKaynagi, kolon: Kolon, tenant_id: str) -> Select:
    if kolon.oneri_sorgusu is not None:
        return kolon.oneri_sorgusu(tenant_id)
    ifade = kolon.ifade
    return (
        select(ifade).distinct()
        .select_from(kaynak.from_clause)
        .where(and_(*kaynak.kisitlar(tenant_id), ifade.isnot(None), ifade != ""))
        .order_by(ifade)
    )


def onerileri_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session],
                    tenant_id: str) -> tuple[Optional[list[str]], bool]:
    """`onerili` metin kolonun DISTINCT değerleri (plan §4.2): kaynağın tenant +
    soft-delete kısıtı, boş hariç, DB sırasıyla, en fazla `ONERI_MAX`; aşarsa ilk
    `ONERI_MAX` + `(liste, True)`. Önerisiz kolonda `(None, False)`; `db` yoksa `([], False)`."""
    if not kolon.onerili:
        return None, False
    if db is None:
        return [], False
    satirlar = db.execute(_oneri_sorgusu(kaynak, kolon, tenant_id).limit(ONERI_MAX + 1)).scalars().all()
    degerler = [str(d) for d in satirlar if d not in (None, "")]
    return degerler[:ONERI_MAX], len(degerler) > ONERI_MAX


@overload
def veriden_secenekleri_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str,
                              *, sayili: Literal[False] = False) -> Optional[list[str]]: ...


@overload
def veriden_secenekleri_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str,
                              *, sayili: Literal[True]) -> Optional[list[tuple[str, int]]]: ...


def veriden_secenekleri_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str,
                              *, sayili: bool = False) -> Optional[list[str]] | Optional[list[tuple[str, int]]]:
    """`veriden_liste` metin kolonun seçenekleri (plan §5.2): kaynağın tenant + soft-delete kısıtı,
    boş hariç, `GROUP BY` + `COUNT` ile SIKLIĞA göre azalan (eşitlikte ad); DISTINCT sayısı
    `settings.rapor_secenek_esigi`ni aşarsa `None` (→ katalog `metin_icerir` + G137 önerileri).
    İşaretsiz kolonda ya da `db` yoksa `None`. Sorgu `LIMIT eşik+1` ile kesilir — eşik aşımı
    tüm DISTINCT'i çekmeden anlaşılır. `sayili=True` (G145) aynı sorgunun `(deger, sayi)`
    çiftlerini verir — katalog `secenek_sayilari`ni EK sorgu olmadan buradan alır."""
    if not kolon.veriden_liste or db is None:
        return None
    esik = max(0, int(settings.rapor_secenek_esigi))
    ifade = kolon.ifade
    sorgu = (
        select(ifade, func.count())
        .select_from(kaynak.from_clause)
        .where(and_(*kaynak.kisitlar(tenant_id), ifade.isnot(None), ifade != ""))
        .group_by(ifade)
        .order_by(func.count().desc(), ifade)
        .limit(esik + 1)
    )
    satirlar = db.execute(sorgu).all()
    if len(satirlar) > esik:
        return None
    if sayili:
        return [(str(deger), int(sayi)) for deger, sayi in satirlar]
    return [str(deger) for deger, _sayi in satirlar]


def _kolon_katalogu(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str,
                    bos_sayilari_kaynak: Optional[Mapping[str, int]] = None,
                    liste_sayilari_kaynak: Optional[Mapping[str, Mapping[str, int]]] = None) -> dict[str, Any]:
    # Seçenek kaynağı (plan §5.2): sabit `liste` → "sabit"; veriden liste eşik altı → "veri";
    # aksi hâlde yok. Veriden liste eşik altında öneri katmanı KOŞMAZ (ikisi birbirinin yerine).
    # G145: `secenek_sayilari` sabit listede kaynağın tek GROUP BY sorgusundan, veriden listede
    # G141 sorgusunun sayısı, türetilmiş listede `None`; `bos_sayisi` kaynağın tek sorgusundan
    # (`_kaynak_katalogu` ikisini bir kez hesaplayıp dağıtır; verilmezse kolon başına koşar).
    secenekler: Optional[list[str]] = None
    secenek_sayilari: Optional[dict[str, int]] = None
    secenek_kaynagi: Optional[str] = None
    kontrol = kolon.kontrol
    if kolon.tip == "liste":
        veri_sayilari = liste_sayilari_kaynak.get(kolon.anahtar, {}) if liste_sayilari_kaynak is not None else None
        secenekler, secenek_sayilari = secenekleri_sayili_getir(kaynak, kolon, db, tenant_id, veri_sayilari)
        secenek_kaynagi = "sabit"
    else:
        ciftler = veriden_secenekleri_getir(kaynak, kolon, db, tenant_id, sayili=True)
        if ciftler is not None:
            secenekler, secenek_sayilari = [d for d, _n in ciftler], dict(ciftler)
            secenek_kaynagi, kontrol = "veri", KONTROLLER["liste"]
    if bos_sayilari_kaynak is None:
        bos_sayilari_kaynak = bos_sayilari(kaynak, db, tenant_id)
    bos_sayisi = bos_sayilari_kaynak.get(kolon.anahtar) if db is not None else None
    if secenekler is None:
        oneriler, kesik = onerileri_getir(kaynak, kolon, db, tenant_id)
    else:
        oneriler, kesik = None, False
    return {
        "anahtar": kolon.anahtar,
        "etiket": kolon.etiket,
        "tip": kolon.tip,
        "grup": kolon.grup,
        "kontrol": kontrol,
        "filtrelenebilir": kolon.filtrelenebilir,
        "siralanabilir": kolon.siralanabilir,
        "turetilmis": kolon.turetilmis,
        "secilebilir": kolon.secilebilir,
        "aciklama": kolon.aciklama,
        # G166: bağlı kaynak kolonu (ilişki anahtarı); düz kolonda null
        "bag": kolon.bag,
        # Kolon başına izinli op'lar (taraf kolonlarında tip tablosunun alt kümesi, ör. `eq` yok):
        # frontend combobox seçiminde `eq` mi `contains` mi göndereceğini buradan bilir (plan §4.3).
        "oplar": list(kolon.oplar) if kolon.filtrelenebilir else [],
        "secenekler": secenekler,
        "secenek_sayilari": secenek_sayilari,
        "secenek_kaynagi": secenek_kaynagi,
        "secenek_etiketleri": dict(kolon.secenek_etiketleri) if kolon.secenek_etiketleri is not None else None,
        "oneriler": oneriler,
        "oneri_kesik": kesik,
        "bos_sayisi": bos_sayisi,
    }


def _kaynak_katalogu(kaynak: VeriKaynagi, db: Optional[Session], tenant_id: str) -> list[dict[str, Any]]:
    """Kaynağın kolon kataloğu; boş sayıları ve liste sayıları kaynak başına BİR kez (ikişer sorgu)
    hesaplanır ve kolonlara dağıtılır (G145)."""
    bos = bos_sayilari(kaynak, db, tenant_id)
    liste = liste_sayilari(kaynak, db, tenant_id)
    return [_kolon_katalogu(kaynak, kolon, db, tenant_id, bos, liste) for kolon in kaynak.kolonlar.values()]


def katalog(db: Optional[Session], limitler: dict[str, int], tenant_id: str) -> dict[str, Any]:
    """`GET /api/reports/catalog` gövdesi (plan §2.4 + §4.2 + §5.2 + §7.2). Öneriler, veriden
    seçenekler, seçenek/boş sayıları tenant kurallı olduğundan gövde tenant'a özeldir — route
    süreç içi 60 sn önbellekler (GROUP BY ve SUM(CASE) sorguları da önbelleğin içinde)."""
    return {
        "veri_kaynaklari": [
            {
                "anahtar": kaynak.anahtar,
                "etiket": kaynak.etiket,
                "aciklama": kaynak.aciklama,
                "varsayilan_kolonlar": list(kaynak.varsayilan_kolonlar),
                "kolonlar": _kaynak_katalogu(kaynak, db, tenant_id),
                "hizli_filtreler": [
                    {"alan": hf.alan, "alternatifler": list(hf.alternatifler), "sunum": hf.sunum,
                     "etiket": hf.etiket}
                    for hf in kaynak.hizli_filtreler
                ],
                "kolon_setleri": [{"ad": ks.ad, "kolonlar": list(ks.kolonlar)} for ks in kaynak.kolon_setleri],
                # G166: bağlı kaynaklar — kolonları `kolonlar` içinde `<anahtar>.<kolon>` olarak
                "iliskiler": [
                    {"anahtar": i.anahtar, "etiket": i.etiket, "hedef": i.hedef, "coklu": i.coklu}
                    for i in kaynak.iliskiler
                ],
            }
            for kaynak in KAYNAKLAR.values()
        ],
        "limitler": dict(limitler),
    }
