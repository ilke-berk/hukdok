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
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Select, and_, func, null, or_, select
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


def _arama(*ifadeler: Any, ek_filtreler: tuple[FiltreIfadesi, ...] = ()) -> Kolon:
    """Kaynağın sanal arama kolonu (plan §5.2): yalnız filtre (`secilebilir=False`), yalnız `contains`,
    seçim ifadesi yok (`NULL` — motor bu kolonu hiçbir zaman SELECT'e almaz, `tanimi_dogrula` 422 verir)."""
    return replace(
        _turetilmis(ARAMA_KOLONU, "Ara", "metin", null(), filtrelenebilir=True, secilebilir=False,
                    filtre_ifadesi=_arama_filtresi(ifadeler, ek_filtreler), izinli_oplar=("contains",)),
        grup=ARAMA_GRUBU,
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
    _arama(_M.name, _M.cari_kod, _M.email, _M.phone, _M.mobile_phone),
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
    _arama(_D.original_filename, models.Case.tracking_no, _D.ai_summary),
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
    _arama(_F.sistem_no, _F.tku_no, _F.hasar_no, models.Case.tracking_no),
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
        for kolon in kaynak.kolonlar.values():
            _kolonu_denetle(kaynak, kolon)
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


def veriden_secenekleri_getir(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session],
                              tenant_id: str) -> Optional[list[str]]:
    """`veriden_liste` metin kolonun seçenekleri (plan §5.2): kaynağın tenant + soft-delete kısıtı,
    boş hariç, `GROUP BY` + `COUNT` ile SIKLIĞA göre azalan (eşitlikte ad); DISTINCT sayısı
    `settings.rapor_secenek_esigi`ni aşarsa `None` (→ katalog `metin_icerir` + G137 önerileri).
    İşaretsiz kolonda ya da `db` yoksa `None`. Sorgu `LIMIT eşik+1` ile kesilir — eşik aşımı
    tüm DISTINCT'i çekmeden anlaşılır."""
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
    return [str(deger) for deger, _sayi in satirlar]


def _kolon_katalogu(kaynak: VeriKaynagi, kolon: Kolon, db: Optional[Session], tenant_id: str) -> dict[str, Any]:
    # Seçenek kaynağı (plan §5.2): sabit `liste` → "sabit"; veriden liste eşik altı → "veri";
    # aksi hâlde yok. Veriden liste eşik altında öneri katmanı KOŞMAZ (ikisi birbirinin yerine).
    secenekler: Optional[list[str]] = None
    secenek_kaynagi: Optional[str] = None
    kontrol = kolon.kontrol
    if kolon.tip == "liste":
        secenekler, secenek_kaynagi = secenekleri_getir(kolon, db), "sabit"
    else:
        secenekler = veriden_secenekleri_getir(kaynak, kolon, db, tenant_id)
        if secenekler is not None:
            secenek_kaynagi, kontrol = "veri", KONTROLLER["liste"]
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
        # Kolon başına izinli op'lar (taraf kolonlarında tip tablosunun alt kümesi, ör. `eq` yok):
        # frontend combobox seçiminde `eq` mi `contains` mi göndereceğini buradan bilir (plan §4.3).
        "oplar": list(kolon.oplar) if kolon.filtrelenebilir else [],
        "secenekler": secenekler,
        "secenek_kaynagi": secenek_kaynagi,
        "secenek_etiketleri": dict(kolon.secenek_etiketleri) if kolon.secenek_etiketleri is not None else None,
        "oneriler": oneriler,
        "oneri_kesik": kesik,
    }


def katalog(db: Optional[Session], limitler: dict[str, int], tenant_id: str) -> dict[str, Any]:
    """`GET /api/reports/catalog` gövdesi (plan §2.4 + §4.2 + §5.2). Öneriler ve veriden
    seçenekler tenant kurallı olduğundan gövde tenant'a özeldir — route süreç içi 60 sn
    önbellekler (GROUP BY sorguları da önbelleğin içinde)."""
    return {
        "veri_kaynaklari": [
            {
                "anahtar": kaynak.anahtar,
                "etiket": kaynak.etiket,
                "aciklama": kaynak.aciklama,
                "varsayilan_kolonlar": list(kaynak.varsayilan_kolonlar),
                "kolonlar": [_kolon_katalogu(kaynak, kolon, db, tenant_id) for kolon in kaynak.kolonlar.values()],
                "hizli_filtreler": [
                    {"alan": hf.alan, "alternatifler": list(hf.alternatifler), "sunum": hf.sunum,
                     "etiket": hf.etiket}
                    for hf in kaynak.hizli_filtreler
                ],
                "kolon_setleri": [{"ad": ks.ad, "kolonlar": list(ks.kolonlar)} for ks in kaynak.kolon_setleri],
            }
            for kaynak in KAYNAKLAR.values()
        ],
        "limitler": dict(limitler),
    }
