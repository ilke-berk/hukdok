"""Dava CRUD ve takip işlemleri.

Avukat adı çözümleme mantığı managers/lawyer_resolver.py'de,
referans listeleri managers/reference_lists.py'dedir.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import exists, func, intersect, literal, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from database import SessionLocal, SQL_FOLD_FROM, SQL_FOLD_TO
from db_errors import KayitMesgulError, is_lock_timeout, is_unique_violation
import models
from constants import InvalidCaseStatusError, validated_case_status
from party_check import normalize_party_key, normalize_tc, taraf_listesini_tekillestir
from required_fields import (
    AKTARIM_SOURCE_PREFIX,
    MISSING_BUCKETS,
    MISSING_FLAG_INPUT_FIELDS,
    compute_missing_bucket,
    compute_missing_fields,
    missing_bucket_sql,
)
from managers.lawyer_resolver import (
    _norm_name, _split_persons, _resolve_lawyer_aliases, _value_matches,
    AvukatListedeYok, canonicalize_lawyers, kanonik_avukat_metni, listede_olmayan_yeni_adlar,
)

# G066: karar durumu kapalı havuz kapısı tarihçe modülünde yaşar (ikinci
# uygulama çıkarılmadı). Import yönü tek yönlüdür — `stage_decisions` yalnız
# `models`/`db_errors` import eder, `case_manager`ı ÇAĞIRMAZ: döngü yok,
# "sonra import" hilesine gerek kalmadı.
from managers import case_hizmetleri, stage_decisions
from services import ofis_no
from services.multi_value import SEPARATOR, split_values

logger = logging.getLogger("AdminManager")

# Faz 5-B (plan 5.3): tracking_no çakışması SQLSTATE 23505 + ihlal edilen
# indeksin ADIYLA tespit edilir (eski `"tracking_no" in str(e)` metin eşlemesi
# kalktı). Ad, models.Case.tracking_no'nun `unique=True, index=True`
# tanımından SQLAlchemy'nin ürettiği indekstir — `cases` tablosunda
# `uq_cases_sistem_no` da UNIQUE olduğu için ad eşlemesi ŞART: sistem_no
# çakışmasına "ofis numarası zaten kayıtlı" demek kullanıcıyı boşuna sıra
# numarası artırmaya iterdi.
TRACKING_NO_UNIQUE_INDEX = "ix_cases_tracking_no"

# G236: kayıt isteği kimliğinin kısmi UNIQUE index'i (migrasyon 57) — eşzamanlı iki
# aynı-kimlikli istekte kaybedeni bu yakalar.
ISTEK_KIMLIGI_UNIQUE_INDEX = "uq_cases_istek_kimligi"

# G236: `add_case` veri sözlüğündeki bayrak — doluysa numarayı SUNUCU verir
# (`services/ofis_no`, karar 023) ve istemcinin `tracking_no`'su yok sayılır. Bayrağı
# yalnız kullanıcı route'ları (POST /api/cases, intake commit) koyar; `add_case`'i
# doğrudan çağıran aktarım/script yolları (kendi numarasını getirir) eski yolda kalır.
SUNUCU_NUMARASI_BAYRAGI = "ofis_no_sunucudan"


# G250: `add_case` veri sözlüğünde kaydı açan kullanıcının adı (opsiyonel) — hizmet
# satırlarının tarihçe imzası. Route koymazsa imza `PANEL_SOURCE` olur.
KAYDEDEN_ANAHTARI = "kaydeden"


class OfisNoVerilemez(ValueError):
    """Kart için ofis numarası üretilemiyor (müvekkil yok / adı boş) — istemci hatası (→ 422)."""


class HizmetKaydiGecersiz(OfisNoVerilemez):
    """Kart açılamıyor: müvekkilin hizmeti yok ya da hizmet adı kapalı listede değil (G250 → 422).

    `OfisNoVerilemez`'den BİLEREK türer: kart açan iki kullanıcı route'u (POST /api/cases,
    intake commit) o tipi zaten `422 + detail=str(e)`'ye çeviriyor — "kart açılamaz, isteği
    düzelt" sınıfı tek kapıdan geçer, route'lara ikinci bir `except` gerekmez. Ayırt etmek
    isteyen çağıran bu alt tipi yakalar.
    """


def _parse_date_field(value, field_name: str):
    """'YYYY-MM-DD' formatındaki alanı date'e çevirir; geçersizse loglayıp None döner."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Geçersiz tarih değeri atlandı: {field_name}={value!r}")
        return None


# ─── ESAS NUMARASI TARİHÇESİ (FAZ F şartnamesi §1.3, G045) ───────────────────
#
# `cases.esas_no` TÜRETİLMİŞ bir değerdir: `case_esas_numbers` tablosundaki
# `is_current = True` satırının kopyası. Kolona DOĞRUDAN atama yapılmaz — tek
# yazma yolu `sync_current_esas`'tır; ikinci bir yazıcı ikinci bir doğruluk
# kaynağı demektir. Şema tarafındaki karşılığı `uq_case_esas_current` kısmi
# unique index'idir (database.py madde 32): kural yorumla değil kısıtla tutulur.
ESAS_STAGE_YEREL = "YEREL"
ESAS_STAGE_ONCEKI = "ONCEKI"
ESAS_STAGES = (ESAS_STAGE_YEREL, "ISTINAF", "TEMYIZ", "KARAR_DUZELTME", ESAS_STAGE_ONCEKI)

# Serbest metinden esas numarası: yıl 19xx/20xx, ardından sıra numarası.
# `(?<!\d)` / `(?!\d)` sınırları uzun rakam dizilerinin ortasından eşleşmeyi
# engeller. Ayırıcı SERBEST bırakıldı (" - ", ",", ";", "/" hepsi geçer):
# teslim paketinde tek ayırıcı gözlendi ("2017/325 - 2024/145") ama karşı taraf
# dört düzeltme listesi daha gönderecek — ayırıcıyı sabitlemek, biçim
# değişince satırı sessizce yutardı.
_ESAS_NO_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*/\s*(\d{1,6})(?!\d)")

# Kolon sınırları modelden okunur, elle tekrarlanmaz: şema büyürse kod
# kendiliğinden uyar (aksi hâlde sessizce yanlış yerde kırpar).
_ESAS_NO_MAX = models.CaseEsasNumber.esas_no.property.columns[0].type.length
_ESAS_COURT_MAX = models.CaseEsasNumber.court.property.columns[0].type.length
_ESAS_SOURCE_MAX = models.CaseEsasNumber.source.property.columns[0].type.length


def parse_esas_history(raw) -> list:
    """Serbest metinden esas numarası listesi (saf; sıra korunur, tekilleşir).

    Şartname §1.3'ün "çok değerli girdi" örneği: `"2017/325 - 2024/145"` iki
    ayrı ÖNCEKİ esas numarasıdır, tek bir metin değeri değil.

    Bilinçli sınır: numaranın kendisi normalize edilir (iç boşluk atılır) ama
    rakamlar OLDUĞU GİBİ korunur — sıfır dolgusu ("2024/0123") anlamlı bir
    fark olabilir; toleranslı karşılaştırmayı `case_matcher._esas_no_similarity`
    yapar, saklama biçimini bozmak veriyi kaybetmektir.

    VERİ DOLUMU BU GÖREVDE YOK — kural burada, uygulaması FAZ F'nin aktarım
    scriptinin işi (görev dosyası kabul kriteri).
    """
    seen: list = []
    for year, seq in _ESAS_NO_RE.findall(str(raw or "")):
        value = f"{year}/{seq}"
        if value not in seen:
            seen.append(value)
    return seen


def add_historical_esas(db, case, esas_no, *, stage: str = ESAS_STAGE_ONCEKI,
                        court=None, source=None):
    """GEÇMİŞ bir esas numarasını tarihçeye ekler — `is_current`'a DOKUNMAZ.

    `sync_current_esas`ın kardeşi ama tersi yönde: o "bugünkü numara budur"
    der, bu "bu numara da bu davaya aitti" der. Ayrı fonksiyon olmasının
    sebebi güncel işaretin tek yerden yönetilmesi: aktarımın getirdiği eski
    numara (teslimin "Eski Dosya No" sütunu + `Karar_Asamalari`nın "Önceki"
    satırları) kartın güncel esasını EZMEMELİ.

    Aynı (esas_no, stage) satırı varsa hiçbir şey yapılmaz ve **None döner** —
    dönüş değeri "yeni satır açıldı mı" sorusunun cevabıdır; aktarımın
    "ikinci koşu 0 değişiklik" ölçümü buna dayanır (şartname §0).
    """
    value = " ".join(str(esas_no or "").split())
    if not value or len(value) > _ESAS_NO_MAX:
        return None
    if case.id is None:
        db.flush()
    mevcut = db.query(models.CaseEsasNumber).filter(
        models.CaseEsasNumber.case_id == case.id,
        models.CaseEsasNumber.esas_no == value,
        models.CaseEsasNumber.stage == stage,
    ).first()
    if mevcut is not None:
        return None                      # zaten var: yeni satır AÇILMADI
    row = models.CaseEsasNumber(
        case_id=case.id, esas_no=value, stage=stage, court=court,
        is_current=False, source=source,
    )
    db.add(row)
    db.flush()
    return row


def sync_current_esas(db, case, esas_no, court=None, source=None,
                      stage: str = ESAS_STAGE_YEREL):
    """`cases.esas_no`ya yazan TEK yol; tarihçeyi `is_current` ile senkron tutar.

    Davranış:
      * Değer boşsa kolon temizlenir ve güncel işaret kalkar — tarihçe satırları
        SİLİNMEZ: geçmiş numaralar kayıt değeridir, eski esasla arama yapılıyor.
      * Değer varsa (esas_no, stage) satırı yoksa açılır, varsa yeniden güncel
        işaretlenir; diğer satırların `is_current`'ı düşer. Böylece dava başına
        en fazla bir güncel satır kalır (`uq_case_esas_current`).
      * Aynı numara ikinci kez yazılırsa yeni satır AÇILMAZ (`uq_case_esas`) —
        aktarım tekrar tekrar koşacağı için idempotency pazarlıksız (§0).

    `court`/`source` yalnız satır ilk doğduğunda yazılır; sonradan gelen bir
    mahkeme değeri yalnız boş alanı doldurur — provenance üzerine yazmak
    "bu numara hangi mahkemedeydi" bilgisini kaybettirirdi.
    """
    if stage not in ESAS_STAGES:
        raise ValueError(f"Bilinmeyen esas aşaması: {stage!r}")

    value = " ".join(str(esas_no or "").split()) or None
    case.esas_no = value

    # `cases.esas_no` sınırsız TEXT, tarihçe kolonu VARCHAR(50) (şartname §1.3).
    # Sığmayan bir değer (elle girilmiş çöp) bugüne kadar SORUNSUZ kaydediliyordu;
    # tarihçe uğruna kaydı 500'e çevirmek kabul edilemez. Satır atlanır ama eski
    # `is_current` işareti YİNE DE düşer — yoksa kolon yeni değeri, tarihçe eski
    # değeri "güncel" gösterir ve tam da kaçınılan ikinci kaynak doğardı.
    # Log sözleşmesi: deneme-düzeyi durum WARNING, ERROR değil.
    row_value = value
    if value is not None and len(value) > _ESAS_NO_MAX:
        logger.warning(
            f"Esas no tarihçeye yazılamadı (>{_ESAS_NO_MAX} karakter): {value[:60]!r}"
        )
        row_value = None

    if case.id is None:
        db.flush()          # FK için dava id'si şart

    target = None
    demoted = False
    rows = db.query(models.CaseEsasNumber).filter(
        models.CaseEsasNumber.case_id == case.id
    ).all()
    for row in rows:
        if row_value and row.esas_no == row_value and row.stage == stage:
            target = row
        elif row.is_current:
            row.is_current = False
            demoted = True

    # ÖNCE BOŞALT, SONRA İŞARETLE (G049 — G045 denetim bulgusu).
    # `uq_case_esas_current` kısmi unique index'i ertelenebilir DEĞİLDİR: ihlal
    # flush'ın SONUNDA değil, ihlal eden ifadenin kendisinde patlar. SQLAlchemy
    # aynı flush'taki UPDATE'leri PK sırasına göre yayar; tarihçede ZATEN VAR
    # OLAN daha eski bir numaraya geri dönüşte hedefin id'si küçük olduğu için
    # önce ona True yazılır → o an iki güncel satır olur → UniqueViolation
    # (gerçek kullanıcı yolu: yazım hatası düzeltme, görevsizlik sonrası dönüş).
    # Bu yüzden düşürme AYRI ve ÖNCE gelen bir flush'ta yazılır; aradaki anda
    # dava "güncel satırsız" kalır, ki kısıt bunu serbest bırakır.
    # Toplu tek UPDATE alternatifi (`query(...).update({is_current: False})`)
    # de kısıtı sağlardı ama hedefi de gereksizce düşürüp geri kaldırırdı ve
    # ORM kimlik haritasını `synchronize_session` ile elle senkronlamayı
    # gerektirirdi — akış aynı, riski fazla.
    if demoted:
        db.flush()

    if row_value is None:
        return None
    if target is None:
        target = models.CaseEsasNumber(
            case_id=case.id, esas_no=row_value, stage=stage,
            # Denormalize kopyalar kolon sınırlarına kırpılır: taşan bir mahkeme
            # adı yüzünden kaydın tamamını kaybetmek orantısız olurdu.
            court=(str(court)[:_ESAS_COURT_MAX] if court else None),
            source=(str(source)[:_ESAS_SOURCE_MAX] if source else None),
        )
        db.add(target)
    elif court and not target.court:
        target.court = str(court)[:_ESAS_COURT_MAX]
    target.is_current = True
    return target


def _esas_row_dict(row) -> dict:
    """Tarihçe satırının API gösterimi (kart ve arama aynı sözleşmeyi kullanır)."""
    return {
        "esas_no": row.esas_no,
        "stage": row.stage,
        "court": row.court,
        "is_current": bool(row.is_current),
        "source": row.source,
    }


def _foy_row_dict(row) -> dict:
    """Föy satırının (`case_foys`, G063) kart gösterimi + kapsam işareti (G113).

    `kapsam_durumu` NULL = kapsamda; `SILINDI` | `KAPSAM_DISI` işaretli föy
    silinmemiştir, yalnız veri ekibince kapsamdan çıkarılmıştır (gerekçe +
    tarih yanında). Frontend rozeti sonraki turun işi; sözleşme burada.
    """
    return {
        "id": row.id,
        "sistem_no": row.sistem_no,
        "tku_no": row.tku_no,
        "hasar_no": row.hasar_no,
        # G123 föy düzeyi teslim alanları
        "mko_id": row.mko_id,
        "muvekkil_no": row.muvekkil_no,
        "muvekkil_tipi": row.muvekkil_tipi,
        "hizmet_turu": row.hizmet_turu,
        "durum": row.durum,
        # G125 ham satır (orijinal başlık → değer); NULL = ham satırsız eski kayıt
        "ham_veri": row.ham_veri,
        # TKU kart birleştirmesinde sönen kartın ofis numarası (NULL = taşınmadı)
        "onceki_tracking_no": row.onceki_tracking_no,
        "source": row.source,
        "case_party_id": row.case_party_id,
        "kapsam_durumu": row.kapsam_durumu,
        "kapsam_gerekcesi": row.kapsam_gerekcesi,
        "kapsam_tarihi": row.kapsam_tarihi.isoformat() if row.kapsam_tarihi else None,
    }


def _apply_tenant_filter(query, tenant_id: Optional[str]):
    """Sorguya tenant izolasyon + soft-delete filtresi uygular.
    tenant_id'si NULL olan kayıtlar (eski/migrasyon öncesi) her tenant'a görünür.
    Soft-delete edilmiş davalar (deleted_at dolu) hiçbir case_manager yoluna
    dönmez — case_manager tamamen kullanıcı-yüzüdür; silinenleri yalnız
    routes/admin.py doğrudan sorgular.
    """
    query = query.filter(models.Case.deleted_at.is_(None))
    if tenant_id:
        from sqlalchemy import or_
        return query.filter(
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        )
    return query


def _sql_folded(column):
    """Kolonun ASCII'ye katlanmış küçük harf SQL ifadesi (_norm_name'in SQL ikizi).

    Katlama haritası database.SQL_FOLD_* sabitlerinden gelir — orada da
    `idx_cases_resp_lawyer_fold_trgm` fonksiyonel index'ini üretir. İki taraf aynı
    ifadeyi üretmezse index bu sorguya HİÇ uygulanmaz (hata vermez, sessizce
    yavaşlar); bu yüzden harita tek kaynaktan gelir.
    """
    from sqlalchemy import func
    return func.lower(
        func.translate(func.coalesce(column, ""), SQL_FOLD_FROM, SQL_FOLD_TO)
    )


def _lawyer_prefilter(column, tokens):
    """Ad kolonu için SUPERSET ön-eleme koşulu: token'lardan en az biri geçiyor mu?

    `_value_matches`in iki kuralı da (≥2 ortak token / benzersiz soyad; G228'de
    kod kuralı kalktı) eşleşebilmek için değerin normalize halinde `tokens`
    kümesinden en az bir öğe bulunmasını GEREKTİRİR — biri en az bir çekirdek
    token, diğeri soyadın kendisi. Dolayısıyla bu koşul Python
    doğrulamasının sonucunu asla eleyemez; yalnız aday sayısını kırpar. Kesin
    kararı yine `_value_matches` verir, sonuç kümesi bit-bit aynı kalır.

    Ünvan atma (`_TITLE_TOKENS`) SQL tarafında YAPILMAZ; gerekmiyor da: ünvan
    atmak yalnız token siler, kalan token'ların karakter dizisini bozmaz →
    '%token%' araması ünvanlı ham metinde de bulur (yön: SQL ⊇ Python).
    """
    from sqlalchemy import or_
    folded = _sql_folded(column)
    return or_(*[folded.like(f"%{t}%") for t in sorted(tokens)])


_KIMLIK_BICIMI = re.compile(models.AVUKAT_KIMLIK_REGEX, re.IGNORECASE)


def _kimligi_ada_cevir(db, selected: str) -> str:
    """Kimlik biçimli seçim önbellekte (aktif avukatlar) yoksa DB'deki kaydın ADINI döner.

    Aktif avukat kimliği `_resolve_lawyer_aliases` içinde önbellekten çözülür — DB'ye
    gidilmez. Pasif avukat menüde yoktur; kimliği yine de adına iner ki kartları ad
    eşlemesiyle bulunsun (G225 "pasif avukatın kartları filtrede kalır" davranışı).
    Kimlik biçimi dışındaki seçim ve bilinmeyen kimlik AYNEN döner."""
    secim = (selected or "").strip()
    if not _KIMLIK_BICIMI.match(secim) or _resolve_lawyer_aliases(secim) is not None:
        return selected
    kayit = db.query(models.Lawyer.name).filter(models.Lawyer.kimlik == secim.upper()).first()
    return kayit[0] if kayit and kayit[0] else selected


def _lawyer_filter_case_ids(db, selected: str, tenant_id: Optional[str]):
    """Seçilen avukatla eşleşen dava ID kümesini döndürür (toleranslı).
    responsible_lawyer_name + case_lawyers ilişkisinin ikisini de tarar.

    FAZ E/E7: eşleştirme mantığı Python'da kalır (ünvan/diakritik/çoklu-avukat
    kuralları SQL'e sadakatle çevrilemez), ama ADAYLAR artık SQL'de daralır —
    eskiden her filtrede `cases` tablosunun tamamı (14.345 satır) Python'a
    çekiliyordu. Ölçüm: 159 avukat seçimi, ortalama 47,4 ms → 3,0 ms (~16×);
    159/159'unda eski ve yeni id kümeleri birebir aynı.

    G228 — filtre girdisi `?lawyer=<kimlik>` (`AVK-00001`); eski kod/ad değeri 1 sürüm
    GERİYE UYUMLU (G231'de kalkar). GÜVENCE: filtre ASLA yalnız kimliğe bakmaz — kimlik
    yalnız avukat KAYDINI bulur, eşleşme aşağıdaki toleranslı AD kurallarıyla koşar;
    yalnız adla yazılmış kartlar (sorumlu avukat metni) sonuçta kalır. Menüde olmayan
    (pasif) avukatın kimliği DB'den adına çevrilir ve ad yoluna düşer.
    """
    selected = _kimligi_ada_cevir(db, selected)
    aliases = _resolve_lawyer_aliases(selected)
    matched: set = set()

    if aliases is None:
        # Config'te çözülemedi → normalize edilmiş "contains" ile geriye dönük güvenli arama
        sel_norm = _norm_name(selected)
        if not sel_norm:
            return matched
        tokens = set(sel_norm.split())

        def _case_matches(value):
            return any(sel_norm in _norm_name(p) for p in _split_persons(value))

        def _lawyer_matches(value):
            return sel_norm in _norm_name(value)
    else:
        # code_norm G228'den beri daima "" (kod eşleşme token'ı değil) — ön-elemeye girmez.
        core_tokens, code_norm, surname, surname_unique = aliases
        tokens = {t for t in core_tokens if t}

        def _case_matches(value):
            return _value_matches(value, core_tokens, code_norm, surname, surname_unique)

        _lawyer_matches = _case_matches

    if not tokens:
        # Çekirdek token yok → ad kurallarının hiçbiri eşleşemez.
        return matched

    q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(models.Case.active.is_(True))
    q = _apply_tenant_filter(q, tenant_id)
    q = q.filter(_lawyer_prefilter(models.Case.responsible_lawyer_name, tokens))
    for cid, rn in q.all():
        if _case_matches(rn):
            matched.add(cid)
    # BİLİNÇLİ: case_lawyers tarafında tenant/active filtresi YOK (eski davranış
    # aynen korunur) — fazladan id çağıranın `Case.id.in_()` süzgecinde düşer.
    lq = db.query(models.CaseLawyer.case_id, models.CaseLawyer.name).filter(
        _lawyer_prefilter(models.CaseLawyer.name, tokens)
    )
    for cid, nm in lq.all():
        if _lawyer_matches(nm):
            matched.add(cid)
    return matched


def get_case(case_id: int, tenant_id: str = None):
    # E1 (G051) — İLİŞKİLER BİLEREK LAZY: burada `selectinload` YOKTUR ve
    # eklenmemelidir. Liste yolunda (`get_cases`) selectinload N satırın ilişki
    # sorgusunu 1'e indirir; KART TEK satırdır, orada selectinload bir sorguyu
    # bir sorguya indirir — kazanç yok, kurulum maliyeti var.
    # Ölçüm (lokal prod kopyası, 14.345 aktif dava, 14 kart × 10 tekrar,
    # 2026-08-12): lazy 6 sorgu / 2,90 ms · selectinload×5 6 sorgu / 3,70 ms ·
    # + zincirli `documents.case_party` 6-7 sorgu / 3,88 ms. Yani "kart N+1"
    # teşhisi tutmuyor; üç varyantın sorgu sayısı aynı, eager olan YAVAŞ.
    # `d.case_party` da belge başına sorgu AÇMAZ: taraf aynı davanın tarafıdır
    # ve sözlük `parties`i `documents`ten önce materyalize eder — PK identity
    # map'ten gelir. Bu iddiayı tests/test_g051_kart_ve_arama_sorgulari.py
    # belge sayısını artırarak kilitler.
    #
    # `foys` (G113) TEK İSTİSNA ve selectinload DEĞİL, `joinedload`: föyler
    # kart satırına LEFT JOIN'le AYNI ifadede gelir — ek sorgu açılmaz, kartın
    # sorgu sayısı 6'da kalır (G051 kilidi). Kart başına föy sayısı küçüktür
    # (ölçüm 10.08: en kalabalık kart 12 föy), satır çoğalması önemsiz; ayrı
    # bir round-trip ise her kart açılışına eklenirdi.
    #
    # `hizmetler` (G248) AYNI gerekçeyle joinedload: hizmet satırları da kart
    # ifadesinde gelir, sorgu sayısı 6'da kalır. Satır başına müvekkil adı ve
    # föy SistemNo'su ek sorgu açmaz — ikisi de bu kartın zaten yüklenen
    # `parties` / `foys` koleksiyonlarından okunur.
    try:
        db = SessionLocal()
        query = (
            db.query(models.Case)
            .options(joinedload(models.Case.foys), joinedload(models.Case.hizmetler))
            .filter(models.Case.id == case_id)
        )
        query = _apply_tenant_filter(query, tenant_id)
        item = query.first()
        if not item:
            return None

        # Build response with parties and history
        result = {
            "id": item.id,
            "tracking_no": item.tracking_no,
            "esas_no": item.esas_no,
            # Esas numarası TARİHÇESİ (G045): güncel satır önce, sonra yazılma
            # sırası. `esas_no` bu listedeki is_current satırının kopyasıdır —
            # kart iki değeri de gösterir ki "hangi numara ne zamandı" görünsün.
            "esas_numbers": [
                _esas_row_dict(e)
                for e in sorted(item.esas_numbers, key=lambda e: (not e.is_current, e.id))
            ],
            "status": item.status,
            "file_type": item.file_type,
            "sub_type": item.sub_type,
            "subject": item.subject,
            "court": item.court,
            "opening_date": item.opening_date.isoformat() if item.opening_date else None,
            "responsible_lawyer_name": item.responsible_lawyer_name,
            "uyap_lawyer_name": item.uyap_lawyer_name,
            "maddi_tazminat": float(item.maddi_tazminat),
            "manevi_tazminat": float(item.manevi_tazminat),
            # Dava değeri HAM hâli + para birimi (G123): maddi bundan türetilir,
            # NULL = bilinmiyor (float(None) patlar, is not None şart).
            "dava_degeri": float(item.dava_degeri) if item.dava_degeri is not None else None,
            "para_birimi": item.para_birimi,
            "acceptance_date": item.acceptance_date.isoformat() if item.acceptance_date else None,
            "bureau_type": item.bureau_type,
            "sub_type_extra": item.sub_type_extra,
            "judicial_unit": item.judicial_unit,
            "atama_tarihi": item.atama_tarihi.isoformat() if item.atama_tarihi else None,
            "hasar_dosya_no": item.hasar_dosya_no,
            "hukuk_no": item.hukuk_no,
            "klasor_no_2": item.klasor_no_2,
            "tku_no": item.tku_no,
            "sistem_no": item.sistem_no,
            "notes": item.notes,
            # Eşzamanlılık imzası: zenginleştirme apply'ı bu değeri
            # expected_updated_at olarak geri gönderir (bayat ekran → 409).
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "parties": [{"id": p.id, "name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender, "tc_no": p.tc_no} for p in item.parties],
            "lawyers": [{"name": lw.name, "lawyer_id": lw.lawyer_id} for lw in item.lawyers],
            "history": [{"field": h.field_name, "old": h.old_value, "new": h.new_value, "date": h.changed_at.isoformat(), "changed_by": h.changed_by, "source": h.source} for h in sorted(item.history, key=lambda x: x.changed_at, reverse=True)],
            # Soft-delete: silinen belgeler dava kartında görünmez (ilişki ham
            # geldiği için filtre burada — routes/documents.py listeleriyle tutarlı)
            "documents": [{"id": d.id, "original_filename": d.original_filename, "stored_filename": d.stored_filename, "sharepoint_url": d.sharepoint_url, "belge_turu_kodu": d.belge_turu_kodu, "belge_turu_adi": d.belge_turu_adi, "ai_summary": d.ai_summary, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None, "case_party_id": d.case_party_id, "case_party_name": d.case_party.name if d.case_party else None} for d in item.documents if d.deleted_at is None],
            # Kartın föyleri (G063) + kapsam işareti (G113); joinedload ile
            # yukarıdaki sorguda geldi, burada ek sorgu açılmaz. Sıra: sistem_no
            # (foy_map.get_case_foys ile aynı sözleşme).
            "foyler": [_foy_row_dict(f) for f in sorted(item.foys, key=lambda f: f.sistem_no)],
            # Takip alanları
            "case_stage": item.case_stage,
            "dosya_son_durumu": item.dosya_son_durumu,
            "karar_tarihi": item.karar_tarihi.isoformat() if item.karar_tarihi else None,
            "karar_turu": item.karar_turu,
            "karar_lehine": item.karar_lehine,
            # Yerel kararın RESMİ sonucu — kapalı liste (local_decisions, G060);
            # okuma yolu bu satır (G065). Kaba `karar_turu`ndan AYRI alandır.
            "yerel_karar_durumu": item.yerel_karar_durumu,
            "karar_no": item.karar_no,
            "karar_teblig_tarihi": item.karar_teblig_tarihi.isoformat() if item.karar_teblig_tarihi else None,
            "karar_aciklama": item.karar_aciklama,
            # NULL = girilmedi (0'dan farklı) — float(None) patlar, is not None şart
            "hukmedilen_maddi": float(item.hukmedilen_maddi) if item.hukmedilen_maddi is not None else None,
            "hukmedilen_manevi": float(item.hukmedilen_manevi) if item.hukmedilen_manevi is not None else None,
            "hukmedilen_toplam": float(item.hukmedilen_toplam) if item.hukmedilen_toplam is not None else None,
            "istinaf_basvuru_tarihi": item.istinaf_basvuru_tarihi.isoformat() if item.istinaf_basvuru_tarihi else None,
            "istinaf_karar_durumu": item.istinaf_karar_durumu,
            "istinaf_karar_tarihi": item.istinaf_karar_tarihi.isoformat() if item.istinaf_karar_tarihi else None,
            "istinaf_mahkemesi": item.istinaf_mahkemesi,
            "istinaf_esas_no": item.istinaf_esas_no,
            "istinaf_karar_no": item.istinaf_karar_no,
            "istinaf_karar_aciklama": item.istinaf_karar_aciklama,
            "istinaf_teblig_tarihi": item.istinaf_teblig_tarihi.isoformat() if item.istinaf_teblig_tarihi else None,
            "temyiz_basvuru_tarihi": item.temyiz_basvuru_tarihi.isoformat() if item.temyiz_basvuru_tarihi else None,
            "temyiz_karar_durumu": item.temyiz_karar_durumu,
            "temyiz_karar_tarihi": item.temyiz_karar_tarihi.isoformat() if item.temyiz_karar_tarihi else None,
            "temyiz_mahkemesi": item.temyiz_mahkemesi,
            "temyiz_esas_no": item.temyiz_esas_no,
            "temyiz_karar_no": item.temyiz_karar_no,
            "temyiz_eden_durumu": item.temyiz_eden_durumu,
            "temyiz_karar_aciklama": item.temyiz_karar_aciklama,
            "temyiz_teblig_tarihi": item.temyiz_teblig_tarihi.isoformat() if item.temyiz_teblig_tarihi else None,
            "karar_duzeltme_durumu": item.karar_duzeltme_durumu,
            "karar_duzeltme_esas_no": item.karar_duzeltme_esas_no,
            "karar_duzeltme_karar_no": item.karar_duzeltme_karar_no,
            "karar_duzeltme_tarihi": item.karar_duzeltme_tarihi.isoformat() if item.karar_duzeltme_tarihi else None,
            "karar_duzeltme_teblig_tarihi": item.karar_duzeltme_teblig_tarihi.isoformat() if item.karar_duzeltme_teblig_tarihi else None,
            "karar_duzeltme_aciklama": item.karar_duzeltme_aciklama,
            "yeni_esas_no": item.yeni_esas_no,
            "kesinlesme_tarihi": item.kesinlesme_tarihi.isoformat() if item.kesinlesme_tarihi else None,
            "infaz_tarihi": item.infaz_tarihi.isoformat() if item.infaz_tarihi else None,
            # FAZ F alanları (G044) — yazma yolu FAZ F'nin işi, okuma burada.
            # NULL = "aktarım henüz gelmedi"; float(None) patlar, is not None şart.
            "islah_tutari": float(item.islah_tutari) if item.islah_tutari is not None else None,
            "arsiv_tarihi": item.arsiv_tarihi.isoformat() if item.arsiv_tarihi else None,
            "istinaf_basvuran_taraf": item.istinaf_basvuran_taraf,
            "arabuluculuk_no": item.arabuluculuk_no,
            "arabuluculuk_karar_tarihi": item.arabuluculuk_karar_tarihi.isoformat() if item.arabuluculuk_karar_tarihi else None,
            "tibbi_surec": item.tibbi_surec,
            "tibbi_olay": item.tibbi_olay,
            "iddia_edilen_kusur": item.iddia_edilen_kusur,
            "hastada_olusan_zarar": item.hastada_olusan_zarar,
            "uygulanan_yontem": item.uygulanan_yontem,
            # Belgeleme olayı alanları (G103) — kapalı listeler (event_types /
            # judgment_roles); NULL = "karar okunmadı", meşru durum.
            "olay_turu": item.olay_turu,
            "hukumdeki_rol": item.hukumdeki_rol,
            # Müvekkil Tipi / Hizmet Türü (G119) — kapalı listeler (client_types /
            # service_types); NULL = "bilinmiyor". `service_type` (ofis no bloğu,
            # hemen aşağıda) ile İLGİSİZ.
            "muvekkil_tipi": item.muvekkil_tipi,
            # G248: `hizmet_turu` artık TÜRETİLMİŞ özettir (" ; " birleşik) — kaynağı
            # hemen aşağıdaki `hizmetler` satırları (`case_hizmetleri`).
            "hizmet_turu": item.hizmet_turu,
        }
        # Hizmet kayıtları (G248): kart × müvekkil × hizmet. Müvekkil adı ve föy
        # SistemNo'su yukarıda yüklenen koleksiyonlardan — ek sorgu yok.
        taraf_adlari = {p.id: p.name for p in item.parties}
        foy_nolari = {f.id: f.sistem_no for f in item.foys}
        result["hizmetler"] = case_hizmetleri.satirlari_sirala(
            case_hizmetleri.satir_dict(h, taraf_adlari, foy_nolari) for h in item.hizmetler
        )
        result["service_type"] = item.service_type
        result["missing_required_fields"] = compute_missing_fields(result, result["parties"])
        return result
    except Exception as e:
        logger.error(f"Get Case Error: {e}")
        return None
    finally:
        db.close()


_TEMYIZ_ASAMALARI = ("TEMYIZ", "KARAR_DUZELTME")
_ISTINAF_ASAMALARI = ("ISTINAF",)
#: Temyiz mercii dosya türünden: İdare → Danıştay, kalanı (Hukuk/Ceza/boş) → Yargıtay.
#: Karar satırındaki `mahkeme` adı ~%20 boş; dosya türü her kartta dolu.
_DANISTAY_DOSYA_TURU = "İdare"
#: Liste durum filtresinin sanal değerleri (26.09.2026): DURUM değil, derdest
#: dosyanın ulaştığı EN İLERİ kanun yolu — avukat paneli sayacıyla aynı tanım.
#: TEMYIZ = temyiz ∪ karar düzeltme; TEMYIZ_YARGITAY + TEMYIZ_DANISTAY = TEMYIZ.
DERDEST_ASAMA_FILTRELERI = ("ISTINAF", "TEMYIZ", "TEMYIZ_YARGITAY", "TEMYIZ_DANISTAY")


def _asamada(asamalar):
    """Kart bu aşamalardan birine ulaşmış mı: aşama kararı tarihçesi ya da `case_stage`."""
    from sqlalchemy import exists, func, or_

    karar_var = exists().where(
        models.CaseStageDecision.case_id == models.Case.id,
        models.CaseStageDecision.stage.in_(asamalar),
    )
    # coalesce: NULL aşamada `NOT (... OR NULL)` NULL olur, kart düşerdi
    return or_(karar_var, func.coalesce(models.Case.case_stage, "").in_(asamalar))


def derdest_asama_kosullari(asama: str) -> tuple:
    """Derdest + en ileri kanun yolu `asama` (DERDEST_ASAMA_FILTRELERI) koşulları.
    Bir dosya yalnız bir kutuya düşer: temyiz (karar düzeltme dahil) istinafı ezer;
    temyiz, dosya türüne göre Yargıtay / Danıştay diye ayrık bölünür."""
    from sqlalchemy import func

    derdest = models.Case.status == "DERDEST"
    temyiz = _asamada(_TEMYIZ_ASAMALARI)
    danistay = func.coalesce(models.Case.file_type, "") == _DANISTAY_DOSYA_TURU
    if asama == "TEMYIZ":
        return (derdest, temyiz)
    if asama == "TEMYIZ_YARGITAY":
        return (derdest, temyiz, ~danistay)
    if asama == "TEMYIZ_DANISTAY":
        return (derdest, temyiz, danistay)
    if asama == "ISTINAF":
        return (derdest, ~temyiz, _asamada(_ISTINAF_ASAMALARI))
    raise ValueError(f"tanınmayan aşama filtresi: {asama!r}")


#: Rapor kolonu `davalar.kanun_yolu` değerleri — panel kutularıyla aynı tanım (`kanun_yolu_ifadesi`).
KANUN_YOLU_YEREL = "Yerel"
KANUN_YOLU_ISTINAF = "İstinaf"
KANUN_YOLU_YARGITAY = "Temyiz – Yargıtay"
KANUN_YOLU_DANISTAY = "Temyiz – Danıştay"
KANUN_YOLLARI = (KANUN_YOLU_YEREL, KANUN_YOLU_ISTINAF, KANUN_YOLU_YARGITAY, KANUN_YOLU_DANISTAY)


def kanun_yolu_ifadesi():
    """Kartın ulaştığı EN İLERİ kanun yolu (SQL CASE) — `derdest_asama_kosullari` ile aynı kural, durumdan
    bağımsız: temyiz (karar düzeltme dahil) istinafı ezer, temyiz dosya türüne göre Yargıtay/Danıştay;
    aşama kararı da `case_stage` de yoksa "Yerel". Rapor `Durum = DERDEST` ile panel sayısını verir."""
    from sqlalchemy import case, func

    danistay = func.coalesce(models.Case.file_type, "") == _DANISTAY_DOSYA_TURU
    return case(
        (_asamada(_TEMYIZ_ASAMALARI), case((danistay, KANUN_YOLU_DANISTAY), else_=KANUN_YOLU_YARGITAY)),
        (_asamada(_ISTINAF_ASAMALARI), KANUN_YOLU_ISTINAF),
        else_=KANUN_YOLU_YEREL,
    )


def _derdest_en_ileri_asama(db, tenant_id) -> dict:
    """Derdest (aktif) dosyaları en ileri kanun yoluna göre sayar:
    {"ISTINAF": n, "TEMYIZ": t, "TEMYIZ_YARGITAY": y, "TEMYIZ_DANISTAY": d}; t = y + d.
    Bir dosya aynı düzeyde yalnız bir kutuya düşer."""
    from sqlalchemy import func

    def _say(asama):
        q = db.query(func.count(models.Case.id)).filter(
            models.Case.active.is_(True), *derdest_asama_kosullari(asama),
        )
        return _apply_tenant_filter(q, tenant_id).scalar() or 0

    return {asama: _say(asama) for asama in DERDEST_ASAMA_FILTRELERI}


def get_case_stats(tenant_id: str = None):
    from sqlalchemy import func
    try:
        db = SessionLocal()
        stats: dict = {"total": 0, "active": 0, "closed": 0, "appeal": 0, "danis_active": 0, "statuses": {}}
        base_query = db.query(models.Case.status, func.count(models.Case.id)).filter(models.Case.active.is_(True))
        base_query = _apply_tenant_filter(base_query, tenant_id)
        counts = base_query.group_by(models.Case.status).all()

        for status, count in counts:
            stats["total"] += count
            stats["statuses"][status] = count

            s = (status or "").upper()
            if s == "DERDEST":
                stats["active"] += count
            elif s in ("KAPALI", "MAHZEN"):      # KAPALI: migrasyon 50 öncesi eski değer
                stats["closed"] += count

        for status, count in stats["statuses"].items():
            if (status or "").upper().startswith("DANI"):
                stats["danis_active"] += count

        # Üçlü kural (12.09.2026): temyiz/istinaf DURUM değil AŞAMA — `appeal`
        # sayacı `case_stage`'ten okunur (panel geriye dönük anahtarı korur).
        appeal_query = db.query(func.count(models.Case.id)).filter(
            models.Case.active.is_(True),
            models.Case.case_stage.in_(("ISTINAF", "TEMYIZ")),
        )
        stats["appeal"] = _apply_tenant_filter(appeal_query, tenant_id).scalar() or 0

        # Avukat paneli kutuları (26.09.2026 kullanıcı kararı): derdest dosyaların
        # ulaştığı EN İLERİ kanun yolu. `case_stage` kolonu çoğu kartta boş —
        # kaynak aşama kararları tarihçesi (`case_stage_decisions`); kolon da dolu
        # ise ona da bakılır. Temyiz (karar düzeltme dahil) istinafı ezer.
        stats["derdest_stages"] = _derdest_en_ileri_asama(db, tenant_id)

        return stats
    except Exception as e:
        logger.error(f"Get Case Stats Error: {e}")
        return {"total": 0, "active": 0, "closed": 0, "appeal": 0, "danis_active": 0, "statuses": {},
                "derdest_stages": dict.fromkeys(DERDEST_ASAMA_FILTRELERI, 0)}
    finally:
        db.close()


# ─── EKSİK ZORUNLU ALAN BAYRAĞI (FAZ E 6 + FAZ F D2/D8, G046) ────────────────
#
# `cases.missing_required_bucket` TÜRETİLMİŞ kolondur ve tek yazma yolu
# aşağıdaki `refresh_missing_required`tır (esas_no'da `sync_current_esas` ile
# aynı desen). Kural `required_fields`te yaşar; burada yalnız kaydın anlık
# görüntüsü toplanır.
#
# NEDEN DENORMALİZE (E6): filtre eskiden satır başına iki korele EXISTS + 13
# kolonun trim kontrolüyle hesaplanıyordu. Lokal prod kopyasında ölçüm
# (14.345 aktif dava, 2026-08-12): count 36,1 ms → 5,1 ms, ilk sayfa (50 satır)
# 4,6 ms → 1,9 ms. Lokal kopya prod'u TEMSİL ETMEZ (yazma trafiği sıfır,
# önbellek sıcak) — mertebe değişimi anlamlıdır, mutlak sayılar değil.
#
# BAYAT BAYRAK RİSKİ gerçektir; üç savunma var:
#   1. üç yazma yolunun (add/update/enrich) üçü de bu fonksiyondan geçer,
#   2. `TRACKING_FIELDS` ile zorunlu alanların kesişmesi testle boş tutulur —
#      takip formu zorunlu alan yazmaya başlarsa test söyler,
#   3. `audit_missing_required_flags` bayrağı SQL ikiziyle karşılaştırır.


def _case_snapshot(case) -> dict:
    """Kaydın bayrak için okunan alanları (zorunlular + kapı alanları)."""
    return {name: getattr(case, name, None) for name in MISSING_FLAG_INPUT_FIELDS}


def _is_aktarim_kaydi(db, case_id: int) -> bool:
    """Kayıt HUKDOK teslim aktarımından mı doğdu? (D8 — provenance tek kaynak)

    İmza `case_history.source`ta yaşar; denormalize İKİNCİ bir bayrak
    tutulmaz. `startswith(..., autoescape=True)` şart: ham LIKE'ta '_' joker
    olur ve 'HUKDOKxTESLIM...' de eşleşirdi.
    """
    return db.query(models.CaseHistory.id).filter(
        models.CaseHistory.case_id == case_id,
        models.CaseHistory.source.startswith(AKTARIM_SOURCE_PREFIX, autoescape=True),
    ).first() is not None


def refresh_missing_required(db, case) -> Optional[str]:
    """Eksik alan bayrağını yeniden hesaplar ve kayda yazar; kovayı döndürür.

    `db.flush()` ile başlar: taraf ekleme/silme ve alan atamaları henüz
    bekliyorsa aşağıdaki sorgu onları GÖREMEZ ve bayrak bir tur bayat kalırdı.
    Taraflar ilişki üzerinden değil sorguyla okunur — `add_case` satırları
    `case_id` ile ekler, `case.parties` koleksiyonu o anda boş görünür.
    Avukat satırları da aynı sebeple sorguyla sayılır (M5 kapısı, G158):
    aktarım `case_lawyers`i doğrudan yazıp bu fonksiyonu çağırır.
    """
    db.flush()
    parties = db.query(models.CaseParty.party_type, models.CaseParty.tc_no).filter(
        models.CaseParty.case_id == case.id
    ).all()
    lawyers = db.query(models.CaseLawyer.id).filter(
        models.CaseLawyer.case_id == case.id
    ).all()
    missing = compute_missing_fields(_case_snapshot(case), parties, lawyers)
    is_aktarim = bool(missing) and _is_aktarim_kaydi(db, case.id)
    case.missing_required_bucket = compute_missing_bucket(missing, is_aktarim)
    return case.missing_required_bucket


def audit_missing_required_flags(db=None, limit: int = 20) -> dict:
    """Bayrak ile SQL ikizinin sapmasını ölçer (bayatlama nöbetçisi, Postgres).

    Denormalize bir kolonun tek gerçek riski sessizce bayatlamasıdır; bu
    fonksiyon soruyu ölçülebilir kılar: {"toplam", "sapan", "ornekler"}.
    Salt okunurdur — düzeltme YAPMAZ (bayat satırı sessizce onarmak, bayatlığın
    NEDENİNİ gizlerdi; onarım kaydın kendi yazma yolundan geçmeli).
    """
    from sqlalchemy import text

    own = db is None
    db = db or SessionLocal()
    try:
        toplam = db.execute(text("SELECT count(*) FROM cases")).scalar() or 0
        rows = db.execute(text(
            "SELECT id, missing_required_bucket AS bayrak, "
            f"{missing_bucket_sql('cases')} AS beklenen FROM cases "
            f"WHERE missing_required_bucket IS DISTINCT FROM {missing_bucket_sql('cases')} "
            f"ORDER BY id LIMIT {int(limit)}"
        )).all()
        sapan = db.execute(text(
            "SELECT count(*) FROM cases WHERE missing_required_bucket "
            f"IS DISTINCT FROM {missing_bucket_sql('cases')}"
        )).scalar() or 0
        return {
            "toplam": toplam,
            "sapan": sapan,
            "ornekler": [{"id": r.id, "bayrak": r.bayrak, "beklenen": r.beklenen} for r in rows],
        }
    finally:
        if own:
            db.close()


def backfill_missing_required_flags(db=None, apply: bool = False) -> dict:
    """KURAL DEĞİŞİKLİĞİ sonrası bayrağı toplu tazeler (Postgres, G158).

    `audit_missing_required_flags` bayat bayrağı bilerek onarmaz: bayatlık bir
    yazma yolunun kaçtığını gösterir ve o yol düzeltilmelidir. Burası farklı
    bir durum içindir — kural (`required_fields`) değişti, satırlar doğru
    yollardan yazılmıştı ama kuralın yeni hâline göre yeniden hesaplanmalı.
    Tek kaynak korunur: yazılan ifade migrasyon 33'ün backfill'iyle AYNI
    `missing_bucket_sql`dir, ikinci bir kural listesi yoktur.

    Varsayılan KURU KOŞU: yalnız sayar. `apply=True` yazar; oturum dışarıdan
    verildiyse commit ÇAĞIRANIN işidir (test rollback'i için), kendi oturumunu
    açtıysa commit eder. Dönen: {"toplam", "degisecek", "uygulanan"}; ikinci
    koşuda `degisecek` 0'dır (idempotent — WHERE IS DISTINCT FROM).
    """
    from sqlalchemy import text

    own = db is None
    db = db or SessionLocal()
    try:
        hedef = missing_bucket_sql("cases")
        toplam = db.execute(text("SELECT count(*) FROM cases")).scalar() or 0
        degisecek = db.execute(text(
            f"SELECT count(*) FROM cases WHERE missing_required_bucket IS DISTINCT FROM {hedef}"
        )).scalar() or 0
        uygulanan = 0
        if apply and degisecek:
            sonuc = db.execute(text(
                f"UPDATE cases SET missing_required_bucket = {hedef} "
                f"WHERE missing_required_bucket IS DISTINCT FROM {hedef}"
            ))
            uygulanan = sonuc.rowcount or 0
            if own:
                db.commit()
        return {"toplam": toplam, "degisecek": degisecek, "uygulanan": uygulanan}
    finally:
        if own:
            db.close()


def _attach_esas_matches(db, cases_list: list, q, exact: bool, min_len: int) -> None:
    """Aramayı eşleştiren TARİHÇE satırlarını sonuç satırlarına iliştirir (G045).

    "2021/588 ile arayınca dosya çıksın" tek başına yetmez: kullanıcı listede
    o numarayı GÖREMEZ, çünkü `esas_no` kolonu artık başka bir numaradır ve
    sonuç "neden çıktı bu?" diye okunur. Bu yüzden eşleşen satırın AŞAMASI da
    taşınır (`stage`), kart açmaya gerek kalmaz.

    Tek ek sorgu, yalnız arama varken: N+1 olmasın diye sayfadaki id'ler toplu
    sorulur. Eşleşme yoksa alan boş liste kalır (istemci sözleşmesi sabit).
    """
    for row in cases_list:
        row["esas_matches"] = []
    if not cases_list or not q or len(q) < min_len:
        return

    from sqlalchemy import or_
    terms = [t for t in q.strip().split() if exact or len(t) >= 2]
    if not terms:
        return
    patterns = [t if exact else f"%{t}%" for t in terms]

    rows = (
        db.query(models.CaseEsasNumber)
        .filter(
            models.CaseEsasNumber.case_id.in_([row["id"] for row in cases_list]),
            or_(*[models.CaseEsasNumber.esas_no.ilike(p) for p in patterns]),
        )
        .order_by(models.CaseEsasNumber.id)
        .all()
    )
    by_case: dict = {}
    for row in rows:
        by_case.setdefault(row.case_id, []).append(_esas_row_dict(row))
    for row in cases_list:
        row["esas_matches"] = by_case.get(row["id"], [])


def _term_case_id_selects(term: str, exact: bool) -> list:
    """Tek bir arama teriminin eşleşebileceği kolon/ilişkilerin AYRI SELECT'leri (E8, G055).

    Eskiden bunlar tek bir OR/EXISTS ağacında birleşiyordu ve planlayıcı o ağaçta
    trigram index seçemiyordu (ADR-018). Her kol bağımsız SELECT olunca Postgres
    her birini kendi başına optimize edip çağıran tarafta UNION'lar — index
    geri gelmese bile ölçülen kazanç büyük (bkz. G055 raporu).
    Exact modda `notes` ve `case_history.old_value` YOK — eski OR ağacındaki
    davranışın aynısı, normal moddaki 15 koldan ikisi eksik kalır.

    `cases.tku_no` / `cases.sistem_no` kolları G190'da ÇIKARILDI: iki kolonun
    kodda yazıcısı yok (aktarım G123'ten beri föy tablosuna yazar; yazmama
    `test_g063_case_foys`/`test_g064_aktarim_cekirdek` ile kilitli), lokal restore
    kopyasında 14.578 kartta 0 dolu. Her aramada iki boş seq scan'di (1.440 sayfa
    ×2); TKU/SistemNo aramasını aşağıdaki `case_foys` kolları karşılar.
    """
    pattern = term if exact else f"%{term}%"
    contains = f"%{term}%"
    selects = [
        select(models.Case.id).where(models.Case.esas_no.ilike(pattern)),
        # Eski/aşama esasları (G045): görevsizlik-bozma sonrası numara değişse de
        # dosya eski numarasıyla bulunur.
        select(models.Case.id)
        .join(models.CaseEsasNumber, models.CaseEsasNumber.case_id == models.Case.id)
        .where(models.CaseEsasNumber.esas_no.ilike(pattern)),
        select(models.Case.id).where(models.Case.tracking_no.ilike(pattern)),
        select(models.Case.id).where(models.Case.klasor_no_2.ilike(pattern)),  # Eski sistem no
        # Föy kimlikleri (G123): aktarım TKU/SistemNo'yu `case_foys`a yazar
        # (TKU-784, SSTMN-9425); `cases` üzerindeki legacy ikizleri boştur (G190).
        select(models.Case.id)
        .join(models.CaseFoy, models.CaseFoy.case_id == models.Case.id)
        .where(models.CaseFoy.tku_no.ilike(pattern)),
        select(models.Case.id)
        .join(models.CaseFoy, models.CaseFoy.case_id == models.Case.id)
        .where(models.CaseFoy.sistem_no.ilike(pattern)),
        # TKU kart birleştirmesinde sönen kartın ofis numarası föyde kalır
        # (11.09.2026); avukat eski numarayla aradığında birleşik kart çıkar.
        select(models.Case.id)
        .join(models.CaseFoy, models.CaseFoy.case_id == models.Case.id)
        .where(models.CaseFoy.onceki_tracking_no.ilike(pattern)),
        select(models.Case.id).where(models.Case.court.ilike(contains)),
        select(models.Case.id).where(models.Case.subject.ilike(contains)),
        select(models.Case.id).where(models.Case.responsible_lawyer_name.ilike(contains)),
        select(models.Case.id).where(models.Case.uyap_lawyer_name.ilike(contains)),
        select(models.Case.id)
        .join(models.CaseParty, models.CaseParty.case_id == models.Case.id)
        .where(models.CaseParty.name.ilike(contains)),
        select(models.Case.id)
        .join(models.CaseLawyer, models.CaseLawyer.case_id == models.Case.id)
        .where(models.CaseLawyer.name.ilike(contains)),
    ]
    if not exact:
        selects.append(select(models.Case.id).where(models.Case.notes.ilike(pattern)))
        selects.append(
            select(models.Case.id)
            .join(models.CaseHistory, models.CaseHistory.case_id == models.Case.id)
            .where(models.CaseHistory.old_value.ilike(pattern))
        )
    return selects


def _search_term_ids(term: str, exact: bool):
    """Bir terimin eşleştiği TÜM dava id'lerinin UNION'u (tek terim = tek OR grubu).

    UNION'u ADLANDIRILMIŞ bir subquery'ye sarıp tek kolonlu düz bir `select()`
    döndürür — çok terimli aramada bunların `intersect()`'i alınacak
    (`INTERSECT`-of-`UNION`, E8) ve iç içe `CompoundSelect`'in doğrudan
    `.in_()`'e verilmesi SQLAlchemy 2.x'te `_scalar_type()` üzerinde
    `NotImplementedError` fırlatıyor — düz `select()` bu sorunu taşımıyor.
    """
    term_subq = union(*_term_case_id_selects(term, exact)).subquery()
    return select(term_subq.c.id)


def _load_cases_in_order(db, ids: list) -> list:
    """Verilen id'lerin dava satırlarını AYNI sırayla yükler (D4, G190).

    Sıralama ve süzme id listesini üreten sorguda yapıldı; burada yalnız en çok
    `limit` kadar birincil anahtar okunur (parties/lawyers selectinload ile).
    İki sorgu arasında silinen satır sessizce atlanır — liste tekrar üretmez.
    """
    if not ids:
        return []
    rows = (
        db.query(models.Case)
        .options(selectinload(models.Case.parties), selectinload(models.Case.lawyers))
        .filter(models.Case.id.in_(ids))
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[case_id] for case_id in ids if case_id in by_id]


def _coklu_oge_kosulu(kolon, oge: str):
    """Çok değerli hücrede `oge` TAM öğe mi: `' ; ' || hücre || ' ; '` ILIKE `'% ; oge ; %'`.

    Rapor motorunun `_oge_kosulu`'yla aynı anlam (büyük/küçük harf duyarsız, `%`/`_`
    kaçışlı) — "Cerrahi" süzgeci "Cerrahi Uygulama" hücresini YAKALAMAZ.
    """
    kacisli = oge.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return (literal(SEPARATOR) + kolon + literal(SEPARATOR)).ilike(
        f"%{SEPARATOR}{kacisli}{SEPARATOR}%", escape="\\",
    )


def _hizmet_kosulu(hizmet_turu: str):
    """Kartın bu adla KAPSAMDAKİ bir hizmet satırı var mı (`EXISTS case_hizmetleri`, G250).

    Eski filtre `cases.hizmet_turu == X` eşitliğiydi; kolon artık çok değerli TÜRETİLMİŞ
    özet ("A ; B") olduğu için çok hizmetli kartı hiçbir filtrede bulamıyordu. Kaynak
    satırlara bakılır: çok hizmetli kart HER hizmetinin filtresinde çıkar.

    Kapsam: föy kaynaklı satırın föyü kapsam dışıysa (`kapsam_durumu` dolu) satır
    sayılmaz. Aktarım o satırı zaten siler (`case_hizmetleri.foydan_yaz`); koşul, işaret
    ile silme arasında kalmış bir satırın listeyi kirletmesine karşı ikinci kilittir.
    Elle satırın (`foy_id` NULL) föyü yoktur — her zaman kapsamdadır.
    """
    kapsam_disi_foy = exists().where(
        models.CaseFoy.id == models.CaseHizmeti.foy_id,
        func.coalesce(models.CaseFoy.kapsam_durumu, "") != "",
    )
    return exists().where(
        models.CaseHizmeti.case_id == models.Case.id,
        models.CaseHizmeti.hizmet_turu == hizmet_turu,
        ~kapsam_disi_foy,
    )


# Tıbbi Olay seçeneklerini daraltan üst alanlar (02.10). Ekip "Süreç Grubu" sütununu
# gönderince buraya eklenir; uç ve ekran değişmeden o alana göre daraltır.
_OLAY_DARALTAN_ALANLAR = {"tibbi_surec": models.Case.tibbi_surec}


def tibbi_olay_secenekleri(tenant_id: str = None, **ust_filtreler) -> List[Dict[str, Any]]:
    """Dava listesi Tıbbi Olay filtresinin seçenekleri: VERİDE geçen öğeler + dava sayısı.

    Havuz (`medical_events`) değil kartlar okunur — seçenek sıfır sonuç vermez. Üst filtre
    (`tibbi_surec="Doğum Yönetimi"`) verilirse yalnız o süreçle birlikte kodlanmış olaylar
    sayılır (`_coklu_oge_kosulu`, liste filtresiyle aynı tam öğe anlamı). Çok değerli hücre
    öğelere bölünür, dava öğe başına bir kez sayılır; büyük/küçük harf farkı tek seçenektir
    (filtre ILIKE), görünen yazım en sık olanıdır. Sıra: sayı azalan, sonra ad.
    """
    db = SessionLocal()
    try:
        query = db.query(models.Case.tibbi_olay).filter(
            models.Case.active.is_(True),
            models.Case.tibbi_olay.isnot(None), models.Case.tibbi_olay != "",
        )
        query = _apply_tenant_filter(query, tenant_id)
        for alan, deger in ust_filtreler.items():
            kolon = _OLAY_DARALTAN_ALANLAR.get(alan)
            if kolon is not None and deger and deger != "ALL":
                query = query.filter(_coklu_oge_kosulu(kolon, deger))

        sayilar: Dict[str, int] = {}
        yazimlar: Dict[str, Dict[str, int]] = {}
        for (hucre,) in query:
            for oge in split_values(hucre):
                anahtar = oge.casefold()
                sayilar[anahtar] = sayilar.get(anahtar, 0) + 1
                yazim = yazimlar.setdefault(anahtar, {})
                yazim[oge] = yazim.get(oge, 0) + 1
        satirlar = [
            (max(yazimlar[k].items(), key=lambda kv: kv[1])[0], n) for k, n in sayilar.items()
        ]
        satirlar.sort(key=lambda s: (-s[1], s[0].casefold()))
        return [{"name": ad, "count": n} for ad, n in satirlar]
    finally:
        db.close()


def get_cases(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
    lawyer: str = None,
    q: str = None,
    exact: bool = False,
    tenant_id: str = None,
    file_type: str = None,
    urgent_days: int = None,
    missing_required: bool = False,
    missing_bucket: str = None,
    olay_turu: str = None,
    hizmet_turu: str = None,
    tibbi_surec: str = None,
    tibbi_olay: str = None,
    with_total: bool = True,
) -> "tuple[list[dict], int]":
    """Filtrelenmiş dava listesini ve OFFSET/LIMIT öncesi toplam sayıyı döndürür.

    `with_total=False` (E3, G051): toplam SAYILMAZ ve ikinci öğe `-1` döner.
    `-1` bilinçlidir — `len(items)` döndürmek "gerçek toplam" gibi okunur ve
    çağıranın sayfalamasını sessizce bozar (bkz. `tests/test_cases_pagination.py`);
    `-1` toplamı kullanmaya kalkanı ilk bakışta ele verir. Bu yüzden yalnız
    toplamı zaten atan tek çağrı yeri olan `search_cases` bu bayrağı verir;
    liste yolu (`routes/cases.py` → `X-Total-Count`) ASLA vermez.

    `missing_bucket` (D8): eksik filtresi açıkken kovayı daraltır —
    "MANUAL" elle açılmış kayıtlar, "AKTARIM" HUKDOK teslim aktarımından gelenler
    (required_fields.MISSING_BUCKETS). Verilmezse İKİ KOVA DA döner: bugünkü
    davranış korunur ve borç gizlenmez — kova seçimi panelin işidir ve frontend
    bu görevin kapsamı DIŞINDADIR (ayrı iş). Tanınmayan değer sessizce sonucu
    saptırmasın diye yok sayılır ve WARNING'lenir.

    `olay_turu` (G103): belgeleme olayı filtresi — `file_type` kalıbıyla
    eşitlik (değer listenin ADIDIR, ör. "Belgeleme Olayı"; "ALL" = filtre yok).

    `hizmet_turu` (G119, G250): hizmet türü filtresi — değer listenin ADIDIR
    (ör. "Lexis Rapor"). Eşitlik DEĞİL: kartın o adla kapsamdaki bir hizmet satırı
    (`case_hizmetleri`) varsa eşleşir (`_hizmet_kosulu`); `cases.hizmet_turu` özeti
    okunmaz. Müvekkil Tipi için filtre BİLİNÇLİ yok (sözleşme).

    `tibbi_surec` / `tibbi_olay` (02.10): klinik tasnif filtreleri — kolonlar ÇOK
    DEĞERLİDİR (`multi_value.SEPARATOR`), değer havuz öğesinin ADIDIR ve hücrede TAM
    ÖĞE olarak aranır (`_coklu_oge_kosulu`, rapor motorunun `eq` anlamıyla aynı).
    """
    try:
        db = SessionLocal()
        # İlişki yükleyicileri (selectinload) YALNIZ satır yüklenirken eklenir:
        # D4 yolundaki `with_entities(Case.id)` id sorgusu Case varlığı taşımaz.
        query = db.query(models.Case).filter(models.Case.active.is_(True))
        query = _apply_tenant_filter(query, tenant_id)

        if status in DERDEST_ASAMA_FILTRELERI:
            # Sanal durum (26.09): derdest + en ileri kanun yolu (avukat paneli sayacıyla aynı)
            query = query.filter(*derdest_asama_kosullari(status))
        elif status and status != "ALL":
            query = query.filter(models.Case.status == status)

        if file_type and file_type != "ALL":
            query = query.filter(models.Case.file_type == file_type)

        # Belgeleme olayı filtresi (G103) — file_type kalıbıyla eşitlik
        if olay_turu and olay_turu != "ALL":
            query = query.filter(models.Case.olay_turu == olay_turu)

        # Hizmet türü filtresi (G119; G250'den beri eşitlik DEĞİL): kartın o adla kapsamdaki
        # bir hizmet satırı var mı — çok hizmetli kart her hizmetinin filtresinde bulunur.
        if hizmet_turu and hizmet_turu != "ALL":
            query = query.filter(_hizmet_kosulu(hizmet_turu))

        # Klinik tasnif filtreleri (02.10) — çok değerli hücrede tam öğe eşleşmesi
        if tibbi_surec and tibbi_surec != "ALL":
            query = query.filter(_coklu_oge_kosulu(models.Case.tibbi_surec, tibbi_surec))
        if tibbi_olay and tibbi_olay != "ALL":
            query = query.filter(_coklu_oge_kosulu(models.Case.tibbi_olay, tibbi_olay))

        if missing_required:
            # E6: sıcak yolda tek kolon okunur; kural + hesap yazma yolunda
            # (refresh_missing_required). NULL = eksik yok.
            query = query.filter(models.Case.missing_required_bucket.isnot(None))
            if missing_bucket:
                if missing_bucket in MISSING_BUCKETS:
                    query = query.filter(models.Case.missing_required_bucket == missing_bucket)
                else:
                    logger.warning(f"Bilinmeyen eksik-alan kovası yok sayıldı: {missing_bucket!r}")

        if urgent_days is not None:
            # Önümüzdeki N gün içinde duruşması olan davalar (bugün dahil)
            today = date.today()
            upcoming = db.query(models.HearingDate.case_id).filter(
                models.HearingDate.hearing_date >= today,
                models.HearingDate.hearing_date <= today + timedelta(days=urgent_days),
            )
            query = query.filter(models.Case.id.in_(upcoming))

        if lawyer and lawyer != "ALL":
            # Toleranslı eşleştirme: ünvan/diakritik/format farklarını ve çoklu avukatı çözer.
            matched_ids = _lawyer_filter_case_ids(db, lawyer, tenant_id)
            # Eşleşme yoksa garanti boş küme (-1) ile sonucu boşalt
            query = query.filter(models.Case.id.in_(matched_ids if matched_ids else [-1]))

        min_len = 1 if exact else 2
        search_filtered = False
        if q and len(q) >= min_len:
            terms = q.strip().split()
            term_id_queries = []
            for term in terms:
                if not exact and len(term) < 2:
                    continue
                term_id_queries.append(_search_term_ids(term, exact))

            # Çok terimli arama AND semantiği: her terim AYRI eşleşmeli
            # (INTERSECT-of-UNION, E8). Tek terimde intersect hiç koşmaz.
            if term_id_queries:
                combined_ids = (
                    term_id_queries[0] if len(term_id_queries) == 1
                    else intersect(*term_id_queries)
                )
                query = query.filter(models.Case.id.in_(combined_ids))
                search_filtered = True

        # Relevance sıralaması: sorgu varsa exact > prefix > partial > diğer.
        # id tiebreaker: updated_at unique değil — eşitlikte sayfalar arası
        # satır tekrarı/atlamasını önler.
        order_by: tuple = (models.Case.updated_at.desc(), models.Case.id.desc())
        if q and len(q.strip()) >= min_len:
            from sqlalchemy import case as sa_case
            raw = q.strip()
            relevance = sa_case(
                (models.Case.esas_no.ilike(raw), 1),
                (models.Case.tracking_no.ilike(raw), 1),
                (models.Case.klasor_no_2.ilike(raw), 1),
                (models.Case.esas_no.ilike(f"{raw}%"), 2),
                (models.Case.tracking_no.ilike(f"{raw}%"), 2),
                (models.Case.klasor_no_2.ilike(f"{raw}%"), 2),
                else_=3,
            )
            order_by = (relevance, *order_by)

        if search_filtered and with_total:
            # D4 (G190): arama + toplam. Eskiden `count()` ve sayfa sorgusu aynı
            # UNION/INTERSECT ağacını İKİ kez koşuyordu. Artık süzülmüş ve
            # SIRALANMIŞ id listesi TEK sorguda gelir (arama sonucu en çok ~14 k
            # int): toplam = listenin uzunluğu, sayfa = listenin dilimi. Aynı
            # listeden dilimlendiği için sayfalar arası tekrar/atlama olamaz.
            ordered_ids = [row[0] for row in query.with_entities(models.Case.id).order_by(*order_by).all()]
            total = len(ordered_ids)
            items = _load_cases_in_order(db, ordered_ids[offset:offset + limit])
        else:
            # Toplam sayı — sayfalama (offset/limit) uygulanmadan önce.
            # İstenmezse COUNT hiç koşmaz: aramada bu, her tuş vuruşunda ikinci
            # bir tam taramayı ortadan kaldırır (E3) ve UNION ağacı yalnız sayfa
            # sorgusunda, bir kez koşar. Aramasız liste yolunda UNION yoktur.
            total = query.count() if with_total else -1
            items = (
                query.options(selectinload(models.Case.parties), selectinload(models.Case.lawyers))
                .order_by(*order_by).offset(offset).limit(limit).all()
            )

        cases_list = []
        for item in items:
            result = {
                "id": item.id,
                "tracking_no": item.tracking_no,
                "esas_no": item.esas_no,
                "status": item.status,
                "file_type": item.file_type,
                "sub_type": item.sub_type,
                "subject": item.subject,
                "court": item.court,
                "opening_date": item.opening_date.isoformat() if item.opening_date else None,
                "responsible_lawyer_name": item.responsible_lawyer_name,
                "uyap_lawyer_name": item.uyap_lawyer_name,
                "maddi_tazminat": float(item.maddi_tazminat) if item.maddi_tazminat else 0,
                "manevi_tazminat": float(item.manevi_tazminat) if item.manevi_tazminat else 0,
                "acceptance_date": item.acceptance_date.isoformat() if item.acceptance_date else None,
                "bureau_type": item.bureau_type,
                "sub_type_extra": item.sub_type_extra,
                "judicial_unit": item.judicial_unit,
                "service_type": item.service_type,
                "atama_tarihi": item.atama_tarihi.isoformat() if item.atama_tarihi else None,
                "hasar_dosya_no": item.hasar_dosya_no,
                "hukuk_no": item.hukuk_no,
                "klasor_no_2": item.klasor_no_2,
                "notes": item.notes,
                "dosya_son_durumu": getattr(item, "dosya_son_durumu", None),
                "parties": [{"id": p.id, "name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender, "tc_no": p.tc_no} for p in item.parties],
                "lawyers": [{"name": lw.name, "lawyer_id": lw.lawyer_id} for lw in item.lawyers],
                "created_at": item.created_at.isoformat() if hasattr(item, 'created_at') and item.created_at else None,
                "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else None,
            }
            result["missing_required_fields"] = compute_missing_fields(result, result["parties"])
            cases_list.append(result)
        _attach_esas_matches(db, cases_list, q, exact, min_len)
        return cases_list, total
    except Exception as e:
        logger.error(f"Get Cases Advanced Error: {e}")
        return [], 0
    finally:
        db.close()


def diff_case_parties(existing: list, incoming: list):
    """Taraf listesi diff'i: (updates, inserts, delete_ids) döndürür.

    updates: [(existing_id, incoming_dict)], inserts: [incoming_dict],
    delete_ids: [existing_id]. Eşleşme önce normalize TC (kesin kimlik),
    sonra `normalize_party_key` (kurumsal ünvan eşitlemeli, kelime sırası
    bağımsız isim anahtarı) ile yapılır; her mevcut satır en fazla bir gelen
    tarafla eşleşir. Eşleşen satır UPDATE edildiği için id'si sabit kalır —
    case_documents.case_party_id bağları (FK SET NULL) öksüzleşmez.
    İsim eşleşip TC farklıysa TC düzeltmesi sayılır (satır korunur).
    """
    unmatched = {p["id"] for p in existing}
    by_tc: dict[str, list[int]] = {}
    by_name: dict[str, list[int]] = {}
    for p in existing:
        tc = normalize_tc(p.get("tc_no"))
        if tc:
            by_tc.setdefault(tc, []).append(p["id"])
        key = normalize_party_key(p.get("name") or "")
        if key:
            by_name.setdefault(key, []).append(p["id"])

    updates, inserts = [], []
    for inc in incoming:
        pid = None
        tc = normalize_tc(inc.get("tc_no"))
        if tc:
            pid = next((i for i in by_tc.get(tc, []) if i in unmatched), None)
        if pid is None:
            key = normalize_party_key(inc.get("name") or "")
            if key:
                pid = next((i for i in by_name.get(key, []) if i in unmatched), None)
        if pid is None:
            inserts.append(inc)
        else:
            unmatched.discard(pid)
            updates.append((pid, inc))
    return updates, inserts, sorted(unmatched)


def _resolve_party_client_id(db, p: dict):
    """CLIENT tarafı için cari çözümü: verilmiş client_id aynen; yoksa ada göre
    mevcut cari, o da yoksa yeni cari (Otomatik Müşteri Oluşturma Yükseltmesi)."""
    client_id = p.get("client_id")
    name = p.get("name")
    if p.get("party_type") == "CLIENT" and name and not client_id:
        existing_client = db.query(models.Client).filter(
            models.Client.name.ilike(name.strip()),
            models.Client.deleted_at.is_(None),  # silinmiş cariye oto-bağlanma
        ).first()
        if existing_client:
            client_id = existing_client.id
        else:
            new_client = models.Client(
                name=name.strip(),
                contact_type="Client",
                client_type="Individual",
                active=True
            )
            db.add(new_client)
            db.flush()
            client_id = new_client.id
    return client_id


#: Elle (panel) yolunun `case_history.source` imzası (G152). Aktarım imzası
#: `AKTARIM_SOURCE_PREFIX` ile başlar; bu başlamaz — `status` kesim-sonrası
#: koruma kuralı ayrımı buradan yapar (`hukdok_aktarim.kesim_sonrasi_kullanici_kaydi`).
PANEL_SOURCE = "panel"



def avukat_adlarini_dogrula(yeni: dict, onceki: Optional[dict] = None, db=None) -> None:
    """27.09 yazım koruması (kullanıcı kararı): kullanıcı yazma yoluna listede karşılığı olmayan
    YENİ avukat adı gelirse `AvukatListedeYok` (api.py → 422). Kartta zaten duran, değişmeden
    geri gelen eski değer ("Arşiv Dosya Yöneticisi", idari personel) engellenmez."""
    onceki = onceki or {}
    # Liste, yazımın yapıldığı AYNI oturumdan okunur (config önbelleği başka DB'yi gösterebilir).
    liste = ([{"code": av.code, "name": av.name} for av in db.query(models.Lawyer).all()]
             if db is not None else None)
    eksik: list = []
    for alan in ("responsible_lawyer_name", "uyap_lawyer_name"):
        eksik += listede_olmayan_yeni_adlar(yeni.get(alan), onceki.get(alan), liste)
    onceki_liste = ";".join([*(onceki.get("lawyers") or []), onceki.get("responsible_lawyer_name") or ""])
    for lw in yeni.get("lawyers") or []:
        eksik += listede_olmayan_yeni_adlar((lw or {}).get("name"), onceki_liste, liste)
    if eksik:
        raise AvukatListedeYok(dict.fromkeys(eksik))


def update_case(case_id: int, data: dict, tenant_id: str = None, *,
                changed_by: Optional[str] = None):
    """Dava alanlarını günceller.

    Dönüş (Faz 5-B, plan 5.3 — reference_lists.update_item ile AYNI ayrım):
      True  — başarı
      None  — dava yok / bu tenant'a görünmüyor → route 404 döner
      False — güncelleme sırasında hata → route 500 döner
    Ayrımdan önce ikisi de False'tu; "olmayan davayı güncelle" 500 oluyordu.

    Tarihçe imzası (G152): izlenen alan değişince `case_history` satırı
    `changed_by=<kullanıcı>` (route vermezse `PANEL_SOURCE`) ve
    `source=PANEL_SOURCE` ile yazılır — dün ikisi de NULL'dı, aktarım
    kaydından ayırt edilemiyordu.
    """
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return None

        # 27.09 yazım koruması — HİÇBİR alan yazılmadan (listede olmayan YENİ avukat adı → 422)
        avukat_adlarini_dogrula(data, {
            "responsible_lawyer_name": case.responsible_lawyer_name,
            "uyap_lawyer_name": case.uyap_lawyer_name,
            "lawyers": [lw.name for lw in case.lawyers],
        }, db=db)

        # Fields to track for history
        tracked_fields = ["esas_no", "court", "status"]

        # Üçlü kural (12.09.2026): status yalnız DERDEST | DANIŞ | MAHZEN; eski
        # değer (TEMYIZ, KAPALI, ...) üçlüye çevrilir, aşama boşsa oraya taşınır.
        # Üçlü dışı değer (G196) HİÇBİR alan yazılmadan InvalidCaseStatusError →
        # route 400 (G195 CHECK kısıtına ulaşıp 500 + ERROR üretmez).
        if data.get("status") is not None:
            data = dict(data)
            normalized, stage = validated_case_status(data["status"])
            data["status"] = normalized
            if stage and not case.case_stage:
                case.case_stage = stage

        # 1. Update Case and Record History
        for field in tracked_fields:
            new_val = data.get(field)
            old_val = getattr(case, field)
            if new_val is not None and str(new_val) != str(old_val):
                # Add to history
                history_entry = models.CaseHistory(
                    case_id=case_id,
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else "",
                    new_value=str(new_val),
                    changed_by=changed_by or PANEL_SOURCE,
                    source=PANEL_SOURCE,
                )
                db.add(history_entry)
                if field == "esas_no":
                    # Türetilmiş alan: kolon + tarihçe tek yoldan (G045).
                    # court bu turda da değişebilir; henüz yazılmamış olabileceği
                    # için gelen değer önceliklidir.
                    sync_current_esas(
                        db, case, new_val,
                        court=data.get("court") or case.court, source="update_case",
                    )
                else:
                    setattr(case, field, new_val)

        # Update non-tracked main fields
        case.file_type = data.get("file_type", case.file_type)
        case.sub_type = data.get("sub_type", case.sub_type)
        # Faz 6.4 kararı (2026-08-01): service_type kalıcı VE düzenlenebilir —
        # NewCase edit formu zaten gönderiyordu, burada yok sayılıyordu.
        # G250: ESKİ 5'li maske — yalnız geriye uyum için okunup saklanır; hiçbir şeyi
        # beslemez (ofis no, zorunlu alan, hizmet kaydı) ve sunucu yeni kod üretmez.
        # Taraflardaki `hizmet_turleri` burada YOK SAYILIR: mevcut kartın hizmetleri
        # `PUT /api/cases/{id}/hizmetler/{case_party_id}` ucundan yazılır.
        case.service_type = data.get("service_type", case.service_type)
        case.subject = data.get("subject", case.subject)
        case.responsible_lawyer_name = data.get("responsible_lawyer_name", case.responsible_lawyer_name)
        # 27.09 yazım koruması: UYAP avukatı da listedeki yazıma iner (sorumlu avukat aşağıda
        # canonicalize_lawyers'tan geçer).
        case.uyap_lawyer_name = kanonik_avukat_metni(data.get("uyap_lawyer_name", case.uyap_lawyer_name))
        case.maddi_tazminat = data.get("maddi_tazminat", case.maddi_tazminat)
        case.manevi_tazminat = data.get("manevi_tazminat", case.manevi_tazminat)
        case.bureau_type = data.get("bureau_type", case.bureau_type)
        case.sub_type_extra = data.get("sub_type_extra", case.sub_type_extra)
        case.judicial_unit = data.get("judicial_unit", case.judicial_unit)
        case.hasar_dosya_no = data.get("hasar_dosya_no", case.hasar_dosya_no)
        case.hukuk_no = data.get("hukuk_no", case.hukuk_no)
        case.klasor_no_2 = data.get("klasor_no_2", case.klasor_no_2)
        case.notes = data.get("notes", case.notes)

        if data.get("opening_date"):
            parsed = _parse_date_field(data["opening_date"], "opening_date")
            if parsed:
                case.opening_date = parsed

        if data.get("acceptance_date"):
            parsed = _parse_date_field(data["acceptance_date"], "acceptance_date")
            if parsed:
                case.acceptance_date = parsed

        if data.get("atama_tarihi"):
            parsed = _parse_date_field(data["atama_tarihi"], "atama_tarihi")
            if parsed:
                case.atama_tarihi = parsed

        # 2. Sync Parties — diff bazlı: eşleşen satır UPDATE (id sabit,
        # belge-taraf bağı korunur), yeni satır INSERT, kalkan satır DELETE.
        existing_parties = db.query(models.CaseParty).filter(
            models.CaseParty.case_id == case_id
        ).all()
        updates, inserts, delete_ids = diff_case_parties(
            [{"id": ep.id, "name": ep.name, "tc_no": ep.tc_no} for ep in existing_parties],
            data.get("parties", []),
        )

        rows_by_id = {ep.id: ep for ep in existing_parties}
        for pid, p in updates:
            row = rows_by_id[pid]
            row.client_id = _resolve_party_client_id(db, p)
            row.name = p.get("name")
            row.role = p.get("role")
            row.party_type = p.get("party_type")
            row.birth_year = p.get("birth_year")
            row.gender = p.get("gender")
            row.tc_no = (p.get("tc_no") or "").strip() or None
        for p in inserts:
            db.add(models.CaseParty(
                case_id=case_id,
                client_id=_resolve_party_client_id(db, p),
                name=p.get("name"),
                role=p.get("role"),
                party_type=p.get("party_type"),
                birth_year=p.get("birth_year"),
                gender=p.get("gender"),
                tc_no=(p.get("tc_no") or "").strip() or None
            ))
        if delete_ids:
            # G248: karttan düşen müvekkilin ELLE hizmet satırları taraf silinmeden
            # ÖNCE tarihçeli silinir (case_hizmetleri.case_party_id RESTRICT) ve kart
            # özeti yenilenir. Föy kaynaklı satırı olan taraf silinemez — aşağıdaki
            # DELETE `case_foys`/`case_hizmetleri` RESTRICT'ine takılır (davranış
            # değişmedi: işlem geri alınır, route 500 döner).
            case_hizmetleri.taraflarin_elle_satirlarini_sil(
                db, case, delete_ids,
                changed_by=changed_by or PANEL_SOURCE, source=PANEL_SOURCE,
            )
            db.query(models.CaseParty).filter(
                models.CaseParty.id.in_(delete_ids)
            ).delete(synchronize_session=False)

        # 3. Sync Lawyers — Track B: canonical ad + lawyer_id FK üret
        db.query(models.CaseLawyer).filter(models.CaseLawyer.case_id == case_id).delete()
        rows, canonical, unresolved = canonicalize_lawyers(
            db, data.get("lawyers", []), data.get("responsible_lawyer_name")
        )
        for r in rows:
            db.add(models.CaseLawyer(case_id=case_id, lawyer_id=r["lawyer_id"], name=r["name"]))
        if canonical:
            case.responsible_lawyer_name = canonical
        if unresolved:
            logger.warning(f"Case {case_id}: çözülemeyen avukat(lar): {unresolved}")

        # Eksik alan bayrağı: alanlar VE taraflar yazıldıktan sonra (G046)
        refresh_missing_required(db, case)

        case.updated_at = datetime.now()
        db.commit()
        return True
    except (InvalidCaseStatusError, AvukatListedeYok):
        # İstemci hatası (G196; 27.09 avukat yazım koruması) — nihai başarısızlık DEĞİL:
        # ERROR basılmaz, False'a yutulmaz; api.py 400/422'ye çevirir. Kapılar ilk
        # yazımdan önce koştuğu için rollback yalnız oturumu temiz kapatır.
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Update Case Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()


# Zenginleştirme modunun (Faz 7) güncelleyebildiği dava kartı alanları.
# status/tracking_no/service_type bilinçli dışarıda: durum takip panelinin,
# ofis no + hizmet maskesi açılış sihirbazının işi.
ENRICH_FIELDS = [
    "esas_no", "court", "file_type", "sub_type", "sub_type_extra", "subject",
    "opening_date", "judicial_unit", "maddi_tazminat", "manevi_tazminat",
    "hasar_dosya_no", "hukuk_no", "klasor_no_2", "acceptance_date",
    "atama_tarihi", "bureau_type", "responsible_lawyer_name",
    "uyap_lawyer_name", "notes",
]
_ENRICH_DATE_FIELDS = {"opening_date", "acceptance_date", "atama_tarihi"}
_ENRICH_MONEY_FIELDS = {"maddi_tazminat", "manevi_tazminat"}


def enrich_changes(current: dict, fields: dict) -> list:
    """exclude_unset fields dict'inden uygulanacak (alan, eski, yeni) üçlüleri (saf).

    Sözleşme (İş Kalemi 3.4 deseni): fields yalnız istemcinin GÖNDERDİĞİ
    anahtarları içerir — gönderilmeyen alan dokunulmaz, None gönderilen SİLİNİR.
    Değeri değişmeyen alan listeye girmez (no-op CaseHistory kirletmez).
    Tarih alanları date'e çevrilir; çevrilemeyen tarih yok sayılır.
    """
    changes = []
    for field in ENRICH_FIELDS:
        if field not in fields:
            continue
        new_val = fields[field]
        old_val = current.get(field)
        if field in _ENRICH_DATE_FIELDS and new_val is not None:
            new_val = _parse_date_field(new_val, field)
            if new_val is None:
                continue
        if field in _ENRICH_MONEY_FIELDS:
            try:
                unchanged = float(new_val or 0) == float(old_val or 0)
            except (TypeError, ValueError):
                unchanged = False
        else:
            unchanged = str(old_val or "") == str(new_val or "")
        if unchanged:
            continue
        changes.append((field, old_val, new_val))
    return changes


def is_stale_case(case_updated_at, expected_updated_at) -> bool:
    """Optimistic imza kontrolü (saf): verilen imza davanın updated_at'iyle
    eşleşmiyor mu? İmza verilmemişse kontrol atlanır (geriye uyum — eski
    istemci davranışı değişmez). İki taraf da ISO normalize edilir; ayrıştırılamayan
    imza bayat sayılır (yanlış pozitif 409 zararsız — kullanıcı güncel değerleri görür).
    """
    if not expected_updated_at:
        return False

    def norm(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        try:
            return datetime.fromisoformat(str(value).strip()).isoformat()
        except ValueError:
            return str(value).strip()

    return norm(case_updated_at) != norm(expected_updated_at)


def enrich_case(case_id: int, fields: dict, new_parties: list,
                changed_by: str, source: str, tenant_id: str = None,
                expected_updated_at: str = None):
    """Zenginleştirme modu (Faz 7): mevcut davaya kısmi güncelleme.

    update_case'ten farkları: alan beyaz listesi ENRICH_FIELDS + exclude_unset
    semantiği (enrich_changes), taraflarda YALNIZ EKLEME (mevcut satır
    güncellenmez/silinmez — case_party_id bağları garanti korunur; zaten
    kayıtlı taraf normalize ad/TC eşleşmesiyle atlanır), her değişikliğe
    changed_by + source imzalı CaseHistory kaydı.

    expected_updated_at dolu gelirse davanın güncel updated_at'iyle
    karşılaştırılır — eşleşmezse HİÇBİR alan yazılmadan {"error": "stale_case"}
    döner (route 409'a çevirir; belge arşivi apply'da bu adımdan SONRA koştuğu
    için 409'da belge de tüketilmez — retry güvenli).

    Döner: None (dava yok/tenant dışı) | {"error": ...} |
    {"tracking_no", "updated_fields": [{field, old, new}], "added_parties": [ad]}.
    """
    db = SessionLocal()
    try:
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return None

        if is_stale_case(case.updated_at, expected_updated_at):
            return {"error": "stale_case"}

        # 27.09 yazım koruması: avukat alanları listedeki yazıma iner (aynı kişinin
        # farklı yazımı "değişiklik" sayılmaz, tarihçe gürültüsü üretmez).
        fields = dict(fields)
        for alan in ("responsible_lawyer_name", "uyap_lawyer_name"):
            if fields.get(alan):
                fields[alan] = kanonik_avukat_metni(fields[alan])

        current = {f: getattr(case, f) for f in ENRICH_FIELDS}
        updated = []
        for field, old_val, new_val in enrich_changes(current, fields):
            if field == "esas_no":
                # Türetilmiş alan: kolon + tarihçe tek yoldan (G045). Belgeden
                # gelen zenginleştirme bu yolla da tarihçeye düşer — dosyanın
                # esası tensiple/bozmayla değiştiğinde eskisi kayıtta kalır.
                sync_current_esas(
                    db, case, new_val,
                    court=fields.get("court") or case.court, source=source,
                )
            else:
                setattr(case, field, new_val)
            db.add(models.CaseHistory(
                case_id=case_id,
                field_name=field,
                old_value=str(old_val) if old_val is not None else "",
                new_value=str(new_val) if new_val is not None else "",
                changed_by=changed_by,
                source=source,
            ))
            updated.append({
                "field": field,
                "old": str(old_val) if old_val is not None else None,
                "new": str(new_val) if new_val is not None else None,
            })

        added = []
        existing_rows = [
            {"id": p.id, "name": p.name, "tc_no": p.tc_no} for p in case.parties
        ]
        # 03.10: "A; B" adı kişi başına bölünür, gelen listede aynı kişi bir kez sayılır.
        for p in taraf_listesini_tekillestir(new_parties):
            _, inserts, _ = diff_case_parties(existing_rows, [p])
            if not inserts:
                continue  # zaten kayıtlı taraf — yalnız-EKLEME idempotent kalır
            db.add(models.CaseParty(
                case_id=case_id,
                client_id=_resolve_party_client_id(db, p),
                name=p.get("name"),
                role=p.get("role"),
                party_type=p.get("party_type"),
                birth_year=p.get("birth_year"),
                gender=p.get("gender"),
                tc_no=(p.get("tc_no") or "").strip() or None,
            ))
            db.add(models.CaseHistory(
                case_id=case_id,
                field_name="taraf",
                old_value="",
                new_value=f"{p.get('name')} ({p.get('role') or p.get('party_type')})",
                changed_by=changed_by,
                source=source,
            ))
            existing_rows.append({"id": 0, "name": p.get("name"), "tc_no": p.get("tc_no")})
            added.append(p.get("name"))

        if updated or added:
            # Eksik alan bayrağı: yalnız gerçekten bir şey değiştiyse (G046).
            # Kayıt dokunulmadıysa bayrağı da yeniden yazmak, boş bir UPDATE
            # üretip enrich'in "hiçbir şey değişmedi" sözleşmesini bozardı.
            refresh_missing_required(db, case)
            case.updated_at = datetime.now()
        db.commit()
        return {
            "tracking_no": case.tracking_no,
            "updated_fields": updated,
            "added_parties": added,
        }
    except Exception as e:
        logger.error(f"Enrich Case Error: {e}")
        db.rollback()
        return {"error": "enrich_failed"}
    finally:
        db.close()


def find_duplicate_cases(esas_no: str, court: str = None, tenant_id: str = None):
    """Aynı esas no'lu aktif davaları bulur (mükerrer açılış uyarısı için).

    Esas no karşılaştırması normalize + sıfır dolgu toleranslıdır
    ("2024/123" == "2024 / 0123"); mahkeme benzerliği bilgi amaçlı
    `court_match` bayrağı olarak döner — aynı esas no farklı mahkemede
    meşru olabilir, karar kullanıcının.

    G014: istisna YUTULMAZ. Eski hâl DB hatasında `logger.error` + boş liste
    döndürüyordu; boş liste "mükerrer yok" anlamına geldiği için arıza anında
    mükerrer dava kapısı sessizce açılıyor, aynı esas no ikinci kez
    kaydedilebiliyordu. Hata çağırana ulaşır; nihai ERROR'u ve HTTP
    sözleşmesini route yazar (log sözleşmesi: TEK ERROR).
    """
    from case_matcher import _court_similarity, _esas_no_similarity

    if not esas_no or not str(esas_no).strip():
        return []
    db = SessionLocal()
    try:
        q = db.query(models.Case).filter(
            models.Case.active.is_(True), models.Case.esas_no.isnot(None)
        )
        q = _apply_tenant_filter(q, tenant_id)
        matches = []
        for c in q.all():
            if _esas_no_similarity(esas_no, c.esas_no) >= 50:
                court_score, _reason = _court_similarity(court or "", c.court or "")
                matches.append({
                    "id": c.id,
                    "tracking_no": c.tracking_no,
                    "esas_no": c.esas_no,
                    "court": c.court,
                    "status": c.status,
                    "court_match": court_score >= 25,
                })
        # Aynı mahkemedekiler önce — kullanıcı için en olası mükerrerler
        matches.sort(key=lambda m: not m["court_match"])
        return matches[:10]
    finally:
        db.close()


def search_cases(query: str, exact: bool = False, active_only: bool = False, tenant_id: str = None):
    status = "DERDEST" if active_only else None
    # Dropdown en fazla 8 sonuç gösteriyor; relevance sıralı ilk 25 fazlasıyla yeterli.
    # 500 kayıt çekip parties+lawyers ile serialize etmek her tuş vuruşunda boşa yüktü.
    # `with_total=False` (E3): dropdown toplam sayı GÖSTERMEZ — sayılsaydı her
    # tuş vuruşunda ikinci bir tam tarama olurdu. Toplamı kullanan TEK yer liste
    # yolu; orası bayrağı vermez (X-Total-Count sözleşmesi korunur).
    items, _total = get_cases(
        q=query, limit=25, exact=exact, status=status, tenant_id=tenant_id, with_total=False
    )
    return items


def _mevcut_muvekkili_bul(db, name: Optional[str], tc_no: Optional[str] = None):
    """Taraf adına/TC'sine karşılık gelen (silinmemiş) müvekkil kaydı — yoksa None.

    TC verilmişse önce TC ile eşlenir (aynı isimli iki cari belirsizliğini çözer).
    `add_case`'in otomatik müvekkil bağlama kuralı; ofis no üretimi de kategoriyi
    buradan okur (ikisi aynı kaydı görsün diye tek yardımcı).
    """
    tc = (tc_no or "").strip()
    if tc:
        bulunan = db.query(models.Client).filter(
            models.Client.tc_no == tc,
            models.Client.deleted_at.is_(None),  # silinmiş cariye oto-bağlanma
        ).first()
        if bulunan:
            return bulunan
    if not (name or "").strip():
        return None
    return db.query(models.Client).filter(
        models.Client.name.ilike((name or "").strip()),
        models.Client.deleted_at.is_(None),
    ).first()


def ofis_no_muvekkilleri(db, parties) -> List[Dict[str, Any]]:
    """İstekteki CLIENT taraflardan ofis no üreticisinin müvekkil listesi (`name`, `category`).

    Kategori müvekkil kaydından gelir: `client_id` verilmişse o kayıt, yoksa `add_case`'in
    bağlayacağı mevcut kayıt (`_mevcut_muvekkili_bul`); kayıt yoksa (yeni müvekkil / danışma)
    kategori boş kalır → üretici addan KR/BR ayırır (karar 023 §2).
    """
    muvekkiller: List[Dict[str, Any]] = []
    for p in parties or []:
        if p.get("party_type") != "CLIENT":
            continue
        client = None
        if p.get("client_id"):
            client = db.get(models.Client, p.get("client_id"))
        ad = (p.get("name") or "").strip()
        if client is None and ad:
            client = _mevcut_muvekkili_bul(db, ad, p.get("tc_no"))
        ad = ad or str(getattr(client, "name", None) or "").strip()
        if ad:
            muvekkiller.append({"name": ad, "category": getattr(client, "category", None)})
    return muvekkiller


def _ofis_no_parcalari(db, data: dict) -> Tuple[str, Optional[str], str]:
    """(müvekkil kodu, sigortalı bloğu | None, tür kodu) — sırasız; sayacı ÇAĞIRAN tahsis eder.

    Müvekkil yoksa ya da adından blok üretilemiyorsa `OfisNoVerilemez` (→ 422): yer tutucu
    numara üretilmez (karar 023).
    """
    parties = data.get("parties") or []
    muvekkiller = ofis_no_muvekkilleri(db, parties)
    if not muvekkiller:
        raise OfisNoVerilemez("Müvekkil olmadan ofis numarası verilemez — en az bir müvekkil ekleyin.")
    try:
        kl = ofis_no.kod_listelerini_yukle(db)
        kod, secilen = ofis_no.musteri_kodu(muvekkiller, kl)
        sigortali = None
        if ofis_no.sigortaci_mi(secilen.get("name"), secilen.get("category")):
            sigortali = ofis_no.sigortali_sec(
                None, foys=[], parties=parties, muvekkiller=muvekkiller, kod_listeleri=kl
            )
        return kod, sigortali, ofis_no.tur_kodu(data.get("file_type"))
    except ValueError as e:
        raise OfisNoVerilemez(f"Ofis numarası verilemedi: {e}") from e


def _taraf_hizmetlerini_dogrula(db, parties, *, zorunlu: bool) -> Dict[int, List[str]]:
    """Kart açılırken tarafların `hizmet_turleri`'ni doğrular (G250) — HİÇBİR şey yazmadan.

    Dönüş `{parties içindeki sıra: [kanonik hizmet adı, ...]}` (yalnız hizmeti olan
    müvekkiller). Kurallar:

    * Her ad `service_types` kapalı listesine karşı doğrulanır (kapı
      `case_hizmetleri.dogrulanmis_hizmet_adi` — hizmet satırıyla ORTAK); listede olmayan
      ad `HizmetKaydiGecersiz`.
    * Hizmet yalnız MÜVEKKİL tarafına yazılır; başka tarafta gelirse `HizmetKaydiGecersiz`
      (kullanıcı yolunda şema bunu zaten 422'ler — burası doğrudan çağıranın kilidi).
    * `zorunlu` (kullanıcı yolları — `SUNUCU_NUMARASI_BAYRAGI`): hizmeti olmayan her
      müvekkil adıyla sayılır → `HizmetKaydiGecersiz`. Script/aktarım yolunda zorunlu değil.
    * `service_types` listesi BOŞSA zorunluluk atlanır (WARNING): seçilecek hizmet yoktur,
      kuralı dayatmak seed'i koşmamış kurulumda kart açmayı kilitlerdi — avukat yazım
      koruması ve `validated_event_list_value` ile aynı "boş listede kapı açık" kuralı.
    """
    sonuc: Dict[int, List[str]] = {}
    hizmetsiz: List[str] = []
    for sira, p in enumerate(parties or []):
        ad = " ".join(str(p.get("name") or "").split()) or "(adsız taraf)"
        hamlar = p.get("hizmet_turleri") or []
        if p.get("party_type") != case_hizmetleri.MUVEKKIL_TARAF_TURU:
            if hamlar:
                raise HizmetKaydiGecersiz(
                    f'Hizmet türü yalnız müvekkil tarafına yazılır: "{ad}" müvekkil değil.'
                )
            continue
        adlar: List[str] = []
        for ham in hamlar:
            try:
                kanonik = case_hizmetleri.dogrulanmis_hizmet_adi(db, ham)
            except case_hizmetleri.GecersizHizmetTuru as exc:
                raise HizmetKaydiGecersiz(f'Müvekkil "{ad}": {exc}') from exc
            if kanonik not in adlar:
                adlar.append(kanonik)
        if adlar:
            sonuc[sira] = adlar
        else:
            hizmetsiz.append(ad)

    if zorunlu and hizmetsiz:
        if db.query(models.ServiceType.id).first() is None:
            logger.warning(
                "service_types listesi BOŞ — müvekkil başına hizmet zorunluluğu atlandı "
                "(seed koşmamış olabilir)"
            )
        else:
            sayilan = ", ".join(f'"{a}"' for a in hizmetsiz)
            raise HizmetKaydiGecersiz(
                f"Hizmet türü seçilmemiş müvekkil var: {sayilan}. "
                "Her müvekkil için en az bir hizmet türü seçin."
            )
    return sonuc


def add_case(data: dict, tenant_id: str = None):
    # Zorunlu alan eksikliği kaydı ENGELLEMEZ (kullanıcı kararı 2026-07-31 rev.2):
    # dosya DERDEST olarak açılır, eksikler get_case/get_cases'teki
    # missing_required_fields ile panelde uyarı olarak görünür ve filtrelenir.
    # TEK istisna hizmet kaydıdır (G250, 01.10.2026 kararı): kullanıcı yolunda hizmeti
    # olmayan müvekkille kart AÇILMAZ (`_taraf_hizmetlerini_dogrula` → 422). Bu bir
    # "eksik alan" değil oluşturma kapısıdır — `required_fields`'e girmez, mevcut
    # kartları eksik saymaz.
    #
    # Üçlü kapısı (G196) oturum açılmadan ÖNCE: eski değer (TEMYIZ, KAPALI, ...)
    # üçlüye çevrilir ve aşama taşınır (karar 020 — update_case ile aynı kural);
    # üçlü dışı değer InvalidCaseStatusError → route 400, kart açılmaz, ERROR yok.
    # Boş/None → DERDEST (varsayılan).
    status, legacy_stage = validated_case_status(data.get("status"))
    status = status or "DERDEST"
    sunucu_numarasi = bool(data.get(SUNUCU_NUMARASI_BAYRAGI))
    istek_kimligi = str(data["istek_kimligi"]) if data.get("istek_kimligi") else None
    # Taraf tekilliği (03.10): kart AÇILIRKEN aynı kişi tek satırdır. "A; B" adı kişi
    # başına bölünür, aynı kişi iki türde geldiyse öncelikli tür kalır (müvekkil > karşı
    # taraf > 3. şahıs). Hizmet kapısı ve ofis no bu temiz listeyi okur — sıra numaraları
    # (`taraf_hizmetleri`) onunla tutarlıdır. Çağıranın sözlüğü DEĞİŞTİRİLMEZ (kopya).
    if data.get("parties"):
        data = {**data, "parties": taraf_listesini_tekillestir(data["parties"])}
    try:
        db = SessionLocal()
        # 27.09 yazım koruması: listede olmayan avukat adıyla kart açılmaz (AvukatListedeYok → 422).
        avukat_adlarini_dogrula(data, db=db)

        # G250 hizmet kapısı — İLK yazımdan (ve sıra tahsisinden) ÖNCE: kullanıcı yolunda
        # (bayraklı istek) her müvekkilin en az bir hizmeti olmalı, adlar kapalı listeden
        # (HizmetKaydiGecersiz → 422). Script/aktarım yolunda zorunlu değil; verilen adlar
        # yine doğrulanır. Müvekkilsiz istek buradan geçer, aşağıda OfisNoVerilemez alır.
        taraf_hizmetleri = _taraf_hizmetlerini_dogrula(
            db, data.get("parties"), zorunlu=sunucu_numarasi
        )

        # Handle opening date — çoklu format desteği
        opening_date = None
        date_str = data.get("opening_date")
        if date_str:
            date_str = str(date_str).strip()
            # Deneyeceğimiz tüm formatlar (öncelik sırasına göre)
            DATE_FORMATS = [
                "%Y-%m-%d",   # 2024-12-08  (HTML input type=date)
                "%d.%m.%Y",   # 08.12.2024  (Türkçe standart)
                "%d/%m/%Y",   # 08/12/2024
                "%d%m%Y",     # 08122024    (8 haneli bitişik)
                "%Y%m%d",     # 20241208    (8 haneli ISO bitişik)
                "%d%m%y",     # 081224      (6 haneli, günlük belge)
                "%y%m%d",     # 241208      (6 haneli, YYMMDD)
            ]
            for fmt in DATE_FORMATS:
                try:
                    opening_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not opening_date:
                logger.warning(f"Tarih parse edilemedi, atlanıyor: '{date_str}'")

        # 0. Ofis numarası (G236): bayraklı istekte numarayı sunucu kurar ve sırayı BU
        # transaction'da tahsis eder (rollback = sıra da geri döner; mükerrer yok, boşluk
        # kabul). İstemcinin `tracking_no`'su okunmaz. Avukat/durum doğrulamalarından SONRA
        # koşar — müvekkilsiz istek onların 422/400'ünü gölgelemez.
        tracking_no = data.get("tracking_no")
        ofis_no_kodu = ofis_no_sira = None
        if sunucu_numarasi:
            ofis_no_kodu, sigortali, tur = _ofis_no_parcalari(db, data)
            ofis_no_sira = ofis_no.sira_tahsis_et(db, ofis_no_kodu)
            tracking_no = ofis_no.numara_kur(ofis_no_kodu, ofis_no_sira, sigortali, tur)

        # 1. Create Case
        # esas_no BİLİNÇLİ olarak burada verilmez — türetilmiş değerdir ve
        # yalnız sync_current_esas yazar (flush'tan sonra, G045).
        new_case = models.Case(
            tracking_no=tracking_no,
            ofis_no_kodu=ofis_no_kodu,
            ofis_no_sira=ofis_no_sira,
            istek_kimligi=istek_kimligi,
            status=status,
            # Eski değerin aşaması yalnız istek aşama vermediyse (update_case_tracking eşi)
            case_stage=data.get("case_stage") or legacy_stage,
            service_type=data.get("service_type"),
            file_type=data.get("file_type"),
            sub_type=data.get("sub_type"),
            subject=data.get("subject"),
            court=data.get("court"),
            opening_date=opening_date,
            responsible_lawyer_name=data.get("responsible_lawyer_name"),
            uyap_lawyer_name=kanonik_avukat_metni(data.get("uyap_lawyer_name")),
            maddi_tazminat=data.get("maddi_tazminat", 0),
            manevi_tazminat=data.get("manevi_tazminat", 0),
            bureau_type=data.get("bureau_type"),
            sub_type_extra=data.get("sub_type_extra"),
            judicial_unit=data.get("judicial_unit"),
            hasar_dosya_no=data.get("hasar_dosya_no"),
            hukuk_no=data.get("hukuk_no"),
            klasor_no_2=data.get("klasor_no_2"),
            notes=data.get("notes"),
        )

        # Handle acceptance_date
        acceptance_date_str = data.get("acceptance_date")
        if acceptance_date_str:
            new_case.acceptance_date = _parse_date_field(acceptance_date_str, "acceptance_date")

        # Handle atama_tarihi
        atama_tarihi_str = data.get("atama_tarihi")
        if atama_tarihi_str:
            new_case.atama_tarihi = _parse_date_field(atama_tarihi_str, "atama_tarihi")

        db.add(new_case)
        db.flush()  # Get the case ID

        # 1b. Esas no + tarihçenin ilk satırı (G045) — tek yazma yolu
        sync_current_esas(
            db, new_case, data.get("esas_no"),
            court=data.get("court"), source="add_case",
        )

        # 2. Add Parties
        # Danışma (DANIŞ): ortada henüz dava yok; listede olmayan müvekkil için
        # KALICI yeni müvekkil kaydı OLUŞTURMA. Tam eşleşme varsa mevcut müvekkile
        # bağla, yoksa adı yalnızca CaseParty üzerinde sakla (client_id=None).
        is_consult = (status == "DANIŞ")
        parties = data.get("parties", [])
        hizmetli_taraflar: List[Tuple[Any, List[str]]] = []
        for sira, p in enumerate(parties):
            client_id = p.get("client_id")
            party_type = p.get("party_type")
            name = p.get("name")

            # Otomatik Müşteri Oluşturma Yükseltmesi
            if party_type == "CLIENT" and name and not client_id:
                existing_client = _mevcut_muvekkili_bul(db, name, p.get("tc_no"))
                if existing_client:
                    client_id = existing_client.id
                elif not is_consult:
                    new_client = models.Client(
                        name=name.strip(),
                        contact_type="Client",
                        client_type="Individual",
                        active=True
                    )
                    db.add(new_client)
                    db.flush()
                    client_id = new_client.id

            party = models.CaseParty(
                case_id=new_case.id,
                client_id=client_id,
                name=name,
                role=p.get("role"),
                party_type=party_type,
                birth_year=p.get("birth_year"),
                gender=p.get("gender"),
                tc_no=(p.get("tc_no") or "").strip() or None
            )
            db.add(party)
            if sira in taraf_hizmetleri:
                hizmetli_taraflar.append((party, taraf_hizmetleri[sira]))

        # 2b. Hizmet kayıtları (G250): müvekkil başına hizmet kümesi, kartla AYNI
        # transaction'da ve hizmetin TEK yazma yolundan (`case_hizmetleri`, G248) — her
        # müvekkil kendi kümesini taşır (muhasebe ayrımı), kart özeti (`cases.hizmet_turu`)
        # orada yenilenir. Taraf id'leri için önce flush.
        if hizmetli_taraflar:
            db.flush()
            kaydeden = data.get(KAYDEDEN_ANAHTARI) or PANEL_SOURCE
            for party, adlar in hizmetli_taraflar:
                case_hizmetleri.elle_kumesini_yaz(
                    db, new_case, party.id, adlar,
                    changed_by=kaydeden, source=PANEL_SOURCE,
                )

        # 3. Add Lawyers — Track B: canonical ad + lawyer_id FK üret
        rows, canonical, unresolved = canonicalize_lawyers(
            db, data.get("lawyers", []), data.get("responsible_lawyer_name")
        )
        for r in rows:
            db.add(models.CaseLawyer(case_id=new_case.id, lawyer_id=r["lawyer_id"], name=r["name"]))
        if canonical:
            new_case.responsible_lawyer_name = canonical
        if unresolved:
            logger.warning(f"Yeni dava ({new_case.tracking_no}): çözülemeyen avukat(lar): {unresolved}")

        # Eksik alan bayrağı: taraflar eklendikten SONRA (karşı taraf TC kuralı
        # onları okur). Kolonun DEFAULT'u 'MANUAL' — burası onu düzelten yerdir.
        refresh_missing_required(db, new_case)

        db.commit()
        # Return the new case object (for frontend linking)
        return {
            "id": new_case.id,
            "tracking_no": new_case.tracking_no,
            "esas_no": new_case.esas_no,
            "court": new_case.court or "",
            "status": new_case.status,
            "responsible_lawyer_name": new_case.responsible_lawyer_name or "",
        }
    except IntegrityError as e:
        db.rollback()
        if is_unique_violation(e, ISTEK_KIMLIGI_UNIQUE_INDEX):
            # G236: aynı kimlikli istek bu kartı ZATEN açtı (eşzamanlı çift istek ya da
            # görünmeyen/silinmiş kart). Nihai değil — route kazananın kartını döndürür;
            # sıra tahsisi rollback'le geri döndü. Log sözleşmesi: WARNING.
            logger.warning(f"Add Case: istek kimliği zaten kayıtlı — {istek_kimligi}")
            return {"error": "duplicate_istek_kimligi"}
        if is_unique_violation(e, TRACKING_NO_UNIQUE_INDEX) and not sunucu_numarasi:
            # Yalnız numarasını KENDİ getiren doğrudan çağrılar (aktarım/script): çakışmayı
            # çağıran yorumlar. Sunucunun verdiği numarada çakışma sayaç tutarsızlığıdır —
            # aşağıdaki nihai ERROR'a düşer (route 500), sessizce 409'a çevrilmez.
            logger.warning(f"Add Case: tracking_no çakışması — {data.get('tracking_no')}")
            return {"error": "duplicate_tracking_no"}
        logger.error(f"Add Case Error: {e}")
        return None
    except (AvukatListedeYok, OfisNoVerilemez):
        # İstemci hatası (27.09 yazım koruması / G236 müvekkilsiz kayıt / G250 hizmet
        # kapısı — HizmetKaydiGecersiz bir OfisNoVerilemez'dir): ERROR yok, yutulmaz —
        # 422 (AvukatListedeYok api.py'de, OfisNoVerilemez route'ta).
        db.rollback()
        raise
    except case_hizmetleri.HizmetHatasi as e:
        # Hizmet yazımının kendi istemci hatası (ön doğrulamadan geçip buraya düşmesi
        # beklenmez) — aşağıdaki genel `except`'e yutulup 500'e dönmesin: aynı 422 sınıfı.
        db.rollback()
        raise HizmetKaydiGecersiz(str(e)) from e
    except Exception as e:
        logger.error(f"Add Case Error: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def istek_kimligi_karti(istek_kimligi, tenant_id: Optional[str] = None) -> Optional[dict]:
    """Bu kayıt isteği kimliğiyle DAHA ÖNCE açılmış kart (G236) — yoksa None.

    Tekrar eden istek koruması (`/confirm`'deki `process_id` deseni): yanıtı kaybolan
    kayıt, çift tıklama ya da taslaktan devam aynı kimlikle gelir → yeni kart açılmaz,
    sayaç artmaz, ilk kart `add_case` dönüş şekli + `"reused": True` ile döner.

    Eşleşme anahtarı YALNIZ kimliktir. Numara artık sunucudan geldiği için Faz 3-D'nin
    `find_idempotent_commit_match` ölçütleri (numara + esas/mahkeme + taraf kümesi + 24
    saat penceresi) kalktı: kimlik isteğe özgü UUID'dir, tahmin ölçütüne ve zaman
    penceresine ihtiyaç yok.

    Kart DÖNDÜRÜLMEZ (None): kimlik boş, kart soft-delete edilmiş ya da başka tenant'a
    damgalı. O durumda kimlik yine de doludur → `add_case` unique index'e çarpar
    (`duplicate_istek_kimligi`) ve route 409 verir: başkasının kartı sızmaz, ikinci kart
    da açılmaz. Sorgu hatası YUTULMAZ (çağıran 500 görür) — "bakılamadı"yı "yok" saymak
    ön bakışı sessizce devre dışı bırakırdı.
    """
    if not istek_kimligi:
        return None
    db = SessionLocal()
    try:
        case = (
            db.query(models.Case)
            .filter(
                models.Case.istek_kimligi == str(istek_kimligi),
                models.Case.deleted_at.is_(None),
            )
            .first()
        )
        if case is None:
            return None
        if tenant_id and case.tenant_id and case.tenant_id != tenant_id:
            return None

        return {
            "id": case.id,
            "tracking_no": case.tracking_no,
            "esas_no": case.esas_no,
            "court": case.court or "",
            "status": case.status,
            "responsible_lawyer_name": case.responsible_lawyer_name or "",
            "reused": True,
        }
    finally:
        db.close()


def get_case_document_filenames(case_id: int) -> dict:
    """Davanın (soft-delete edilmemiş) belgelerinin stored_filename → id eşlemesi.

    Faz 3-D idempotent commit çözümlemesi için: retry'ın belgelerinden davada
    zaten kayıtlı olanlar yeniden arşivlenmeden raporlanır. Aynı ada birden çok
    belge varsa ilk (en eski) id döner — yalnız raporlama, kozmetik.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(models.CaseDocument.stored_filename, models.CaseDocument.id)
            .filter(
                models.CaseDocument.case_id == case_id,
                models.CaseDocument.deleted_at.is_(None),
            )
            .order_by(models.CaseDocument.id)
            .all()
        )
        out: dict = {}
        for name, doc_id in rows:
            if name:
                out.setdefault(name, doc_id)
        return out
    except Exception as e:
        logger.warning(f"Belge adı eşlemesi alınamadı (case={case_id}): {e}")
        return {}
    finally:
        db.close()


# Takip panelinin güncelleyebildiği alanlar (case_stage dahil).
#
# Yerleşim kuralı (G073): bu liste dosyanın ZAMAN ÇİZGİSİDİR — arabuluculuktan
# (dava öncesi) arşive (kapanış) kadar "dosya nerede" bilgisi buradan yazılır.
# Kartta kalanlar ise statik künye (kim, hangi mahkeme, hangi klasör). Aynı alan
# İKİ ekrandan YAZILMAZ; kart grupları salt okunurdur
# (`frontend/src/lib/caseCardFields.ts` başlığı), G074 okuma kopyalarını da
# kaldırır.
TRACKING_FIELDS = [
    "case_stage",
    "dosya_son_durumu",
    # Dosya durumu
    "status",
    # Arabuluculuk — davanın ÖN AŞAMASI (teslimde 435 föy `Ana Tür =
    # ARABULUCULUK`; 148 kartta dava ile aynı kartta birleşti). Kart alanı
    # olarak durunca zaman çizgisinin ilk adımı başka ekranda kalıyordu (G073).
    # NOT (G076): numara SÜTUNU teslimde 8.409 satırın 1'inde dolu — alanın
    # bugünkü tek gerçekçi dolum yolu buradan, elle giriştir.
    "arabuluculuk_no", "arabuluculuk_karar_tarihi",
    # Yerel Karar
    "karar_tarihi", "karar_turu", "karar_lehine", "yerel_karar_durumu",
    "karar_no", "karar_teblig_tarihi", "karar_aciklama",
    "hukmedilen_maddi", "hukmedilen_manevi", "hukmedilen_toplam",
    # İstinaf
    "istinaf_basvuru_tarihi", "istinaf_karar_durumu", "istinaf_karar_tarihi",
    "istinaf_mahkemesi", "istinaf_esas_no", "istinaf_karar_no",
    "istinaf_karar_aciklama", "istinaf_teblig_tarihi",
    # Temyiz
    "temyiz_basvuru_tarihi", "temyiz_karar_durumu", "temyiz_karar_tarihi",
    "temyiz_mahkemesi", "temyiz_esas_no", "temyiz_karar_no",
    "temyiz_eden_durumu", "temyiz_karar_aciklama", "temyiz_teblig_tarihi",
    # Karar Düzeltme
    "karar_duzeltme_durumu", "karar_duzeltme_esas_no", "karar_duzeltme_karar_no",
    "karar_duzeltme_tarihi", "karar_duzeltme_teblig_tarihi",
    "karar_duzeltme_aciklama", "yeni_esas_no",
    # Kesinleşme / İnfaz — ve dosyanın KAPANIŞ olayı: arşiv, KESINLESME/KAPALI
    # aşamalarının devamıdır; kartta durunca yaşam çizgisi ikiye bölünüyordu (G073).
    "kesinlesme_tarihi", "infaz_tarihi", "arsiv_tarihi",
    # Belgeleme olayı alanları (G103) — kapalı listeler (event_types /
    # judgment_roles); yazımdan önce `_EVENT_LIST_COLUMNS` kapısından geçerler
    # (G066 davranış eşi). Hükümdeki rol karar bağlamlı olduğu için yazma yolu
    # takip paneli seçildi; hiçbir bağlamda zorunlu değiller.
    "olay_turu", "hukumdeki_rol",
    # Müvekkil Tipi (G119) — kapalı liste (client_types), aynı kapıdan geçer; hiçbir
    # bağlamda zorunlu değil. `hizmet_turu` G250'de bu listeden ÇIKTI: kart alanı
    # `case_hizmetleri`'nden TÜRETİLEN özettir (tek yazıcı `case_hizmetleri.ozeti_yenile`),
    # takip ucundan yazılamaz — gönderilirse YOK SAYILIR (şemada da yok; hata dönmez ki
    # formun tamamını geri gönderen eski istemcinin öteki alanları kaydolsun).
    "muvekkil_tipi",
    # G124 — dava değeri + para birimi (currencies kapısı) ve tıbbi beşli
    # (çok değerli; parça parça kendi listelerine karşı, `_MULTI_LIST_COLUMNS`).
    # Tıbbi beşlinin öteki yazıcısı aktarımdır (metin, doğrulamasız); panel
    # yazımı liste kapısından geçer.
    "dava_degeri", "para_birimi",
    "tibbi_surec", "tibbi_olay", "iddia_edilen_kusur", "hastada_olusan_zarar",
    "uygulanan_yontem",
]


def tracking_changes(data: dict) -> list:
    """exclude_unset dict'inden uygulanacak (alan, değer) çiftleri (saf).

    Sözleşme (Faz 1): data yalnız istemcinin GÖNDERDİĞİ alanları içerir
    (route model_dump(exclude_unset=True) ile üretir). Gönderilmeyen alan
    listeye girmez → dokunulmaz; None gönderilen girer → alan silinir.
    """
    return [(f, data[f]) for f in TRACKING_FIELDS if f in data]


# Belgeleme olayı alanlarının kapalı listeleri (G103) — kolon → (model, liste
# adı). G066 kapısının (stage_decisions.DECISION_STATUS_COLUMNS) ikizidir ama
# kaynak G060 karar havuzları değil event_types/judgment_roles olduğu için
# `_PHOTO_COLUMNS`tan türetilemez; harita burada yaşar çünkü bu alanların tek
# yazma yolu takip panelidir (tarihçe/fotoğraf yolu bu kolonlara yazmaz).
_EVENT_LIST_COLUMNS: Dict[str, Tuple[Any, str]] = {   # değer: (liste modeli, liste adı)
    "olay_turu": (models.EventType, "event_types"),
    "hukumdeki_rol": (models.JudgmentRole, "judgment_roles"),
    # Müvekkil Tipi / Hizmet Türü (G119, DB-2026-002) — aynı kapı, aynı davranış.
    # `hizmet_turu` G250'den beri takip ucundan YAZILMAZ (TRACKING_FIELDS'te yok); satır
    # burada kalır çünkü hizmet SATIRININ adı aynı kapıdan doğrulanır
    # (`case_hizmetleri.dogrulanmis_hizmet_adi` → `validated_event_list_value`).
    "muvekkil_tipi": (models.ClientType, "client_types"),
    "hizmet_turu": (models.ServiceType, "service_types"),
    # Para birimi (G124) — aynı kapı (tek değer, kapalı liste currencies).
    "para_birimi": (models.Currency, "currencies"),
}

# G124 — ÇOK DEĞERLİ kapalı liste kolonları: hücre " ; " ile birleşik metin,
# her parça kendi listesine karşı doğrulanır (davranış `validated_event_list_value`
# ile aynı: boş → None, liste BOŞSA atlanır, tanınmayan parça 400). Parçalar
# normalize edilip (boşluk/mükerrer) listedeki KANONİK yazımla yeniden
# birleştirilir — aktarımın yazdığı ham metinle aynı ayraç (services.multi_value).
_MULTI_LIST_COLUMNS: Dict[str, Tuple[Any, str]] = {
    "tibbi_surec": (models.MedicalProcess, "medical_processes"),
    "tibbi_olay": (models.MedicalEvent, "medical_events"),
    "iddia_edilen_kusur": (models.AllegedFault, "alleged_faults"),
    "hastada_olusan_zarar": (models.PatientHarm, "patient_harms"),
    "uygulanan_yontem": (models.AppliedMethod, "applied_methods"),
}


def validated_multi_list_value(db, column: str, value):
    """`cases.<column>` çok değerli kapalı liste alanıysa parça parça doğrular."""
    from services.multi_value import join_values, split_values

    entry = _MULTI_LIST_COLUMNS.get(column)
    if entry is None:
        return value
    model, liste_adi = entry
    parcalar = split_values(value)
    if not parcalar:
        return None
    if db.query(model.id).first() is None:
        logger.warning(
            f"{liste_adi} listesi BOŞ — {column} kapalı liste doğrulaması "
            f"atlandı (havuz seed'i koşmamış olabilir)"
        )
        return join_values(parcalar)
    kanonik: List[str] = []
    for parca in parcalar:
        satir = db.query(model.name).filter(func.lower(model.name) == parca.lower()).first()
        if satir is None:
            raise stage_decisions.InvalidDecisionStatusError(
                f"{column}: '{parca}' {liste_adi} listesinde yok"
            )
        kanonik.append(satir[0])
    return join_values(kanonik)


def validated_event_list_value(db, column: str, value):
    """`cases.<column>` belgeleme olayı alanıysa kapalı listesine karşı doğrular.

    Davranış G066 (`stage_decisions.validated_status_for_column`) ile BİLİNÇLİ
    eş — aynı kolon ailesine iki farklı kural koymamak için:
      * belgeleme olayı alanı OLMAYAN kolon dokunulmadan döner,
      * None/boş → None (alan temizlenir),
      * liste BOŞSA doğrulama atlanır (WARNING, log sözleşmesi) — seed'i
        koşmamış kurulumda veri girişi kilitlenmesin,
      * listede olmayan değer `InvalidDecisionStatusError` (api.py 400'e
        çevirir; yeni exception tipi + handler açmamak için aynı tip),
      * `active` filtresi YOK (G066 karar noktasıyla simetri: dropdown'dan
        kaldırılmış değer mevcut kayıttan geri yazılabilmeli).
    """
    entry = _EVENT_LIST_COLUMNS.get(column)
    if entry is None:
        return value
    model, liste_adi = entry
    if value is None or not str(value).strip():
        return None
    ad = " ".join(str(value).split())
    if db.query(model.id).first() is None:
        logger.warning(
            f"{liste_adi} listesi BOŞ — {column} kapalı liste doğrulaması "
            f"atlandı (seed koşmamış olabilir)"
        )
        return ad
    if db.query(model.id).filter(model.name == ad).first() is None:
        raise stage_decisions.InvalidDecisionStatusError(
            f"{column} için geçersiz değer: {ad!r} — değer {liste_adi} "
            f"kapalı listesinde yok (G103)"
        )
    return ad


def _validated_tracking_value(db, field: str, value):
    """Takip yazma yolunun iki kapısı sırayla: G066 karar havuzları (aşama
    karar durumu kolonları) + G103 belgeleme olayı listeleri. Kümeler ayrık —
    bir alan en fazla bir kapıya takılır, diğerinden dokunulmadan geçer."""
    return validated_multi_list_value(
        db, field,
        validated_event_list_value(
            db, field, stage_decisions.validated_status_for_column(db, field, value)
        ),
    )


def update_case_tracking(case_id: int, data: dict, changed_by: str, source: str = "MANUAL", tenant_id: str = None) -> bool:
    """Dava takip bilgilerini günceller ve aşama değişmişse CaseStageLog kaydı ekler.

    data yalnız güncellenecek alanları içermeli (exclude_unset); None değer
    alanı temizler.

    Dört karar durumu alanı (yerel/istinaf/temyiz/karar düzeltme) G060 kapalı
    havuzlarına karşı doğrulanır (G066): kapalılık artık yalnız arayüzde değil
    — API'yi doğrudan çağıran da liste dışı değer yazamaz. İki belgeleme olayı
    alanı (olay_turu/hukumdeki_rol) aynı davranışla kendi listelerine karşı
    doğrulanır (G103, `_EVENT_LIST_COLUMNS`). Doğrulama YAZIMDAN ÖNCE toptan
    koşar: bir alan reddedilirse HİÇBİRİ yazılmaz, hata
    `InvalidDecisionStatusError` olarak yükselir (api.py 400'e çevirir) — bu
    fonksiyonun `False` dönüşü "dava bulunamadı/yazılamadı" anlamını korur.
    Kart başka bir transaction'ın kilidindeyse (toplu aktarım, lock_timeout)
    `KayitMesgulError` yükselir (api.py 409) — 404'e dönüşüp "dava bulunamadı"
    demesin (02.10.2026 olayı).

    `case_history` YALNIZ `status` için yazılır (G152 — kesim-sonrası koruma
    kuralı bu tarihçeyi okur; imza `changed_by` + `source=PANEL_SOURCE`).
    Öteki takip alanları bugün de tarihçesizdir (G073 kilidi), değişmedi.
    """
    db = SessionLocal()
    try:
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return False

        old_stage = case.case_stage
        new_stage = data.get("case_stage")
        note = data.pop("note", None)

        # Kapalı liste kapıları (G066 karar havuzları + G103 belgeleme olayı
        # listeleri) ÖNCE, yazım SONRA: kısmi uygulama olmasın.
        degisiklikler = [
            (field, _validated_tracking_value(db, field, value))
            for field, value in tracking_changes(data)
        ]
        # Üçlü kural (12.09.2026): takip paneli de üçlü dışına yazamaz. Kapı (G196)
        # da yazımdan ÖNCE toptan: üçlü dışı değer InvalidCaseStatusError → hiçbir
        # alan (listede status'tan önce gelen case_stage dahil) yazılmaz.
        status_stage = None
        kapili = []
        for field, value in degisiklikler:
            if field == "status":
                value, status_stage = validated_case_status(value)
            kapili.append((field, value))
        for field, value in kapili:
            if field == "status":
                if status_stage and not case.case_stage and not data.get("case_stage"):
                    case.case_stage = status_stage
            if field == "status" and value != case.status:
                db.add(models.CaseHistory(
                    case_id=case_id, field_name="status",
                    old_value=str(case.status) if case.status is not None else "",
                    new_value=str(value) if value is not None else None,
                    changed_by=changed_by or PANEL_SOURCE, source=PANEL_SOURCE,
                ))
            setattr(case, field, value)

        if new_stage and new_stage != old_stage:
            log = models.CaseStageLog(
                case_id=case_id,
                stage=new_stage,
                changed_by=changed_by,
                source=source,
                note=note,
            )
            db.add(log)

        db.commit()
        return True
    except (stage_decisions.InvalidDecisionStatusError, InvalidCaseStatusError):
        # İstemci hatası — nihai başarısızlık DEĞİL: ERROR basılmaz (log
        # sözleşmesi) ve False'a yutulmaz; route katmanına 400 olarak çıkar.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        if is_lock_timeout(e):
            # Kart toplu bir işlemin kilidinde — geçici, 409 (KayitMesgulError).
            logger.warning(f"update_case_tracking: dava {case_id} kilitli (lock_timeout)")
            raise KayitMesgulError() from e
        logger.error(f"update_case_tracking error: {e}")
        return False
    finally:
        db.close()


def get_case_stage_log(case_id: int, tenant_id: str = None) -> list:
    """Davanın aşama tarihçesini döner. tenant_id verilirse, dava o tenant'a (veya legacy NULL'a) ait değilse boş liste döner."""
    db = SessionLocal()
    try:
        # Önce davanın bu tenant tarafından görülebildiğini doğrula
        case_q = db.query(models.Case).filter(models.Case.id == case_id)
        case_q = _apply_tenant_filter(case_q, tenant_id)
        if not case_q.first():
            return []

        logs = (
            db.query(models.CaseStageLog)
            .filter(models.CaseStageLog.case_id == case_id)
            .order_by(models.CaseStageLog.changed_at.asc())
            .all()
        )
        return logs
    except Exception as e:
        logger.error(f"get_case_stage_log error: {e}")
        return []
    finally:
        db.close()
