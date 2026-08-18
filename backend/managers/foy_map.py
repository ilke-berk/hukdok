"""Föy eşleme tablosunun (`case_foys`) TEK yazma yolu (G063).

Kullanıcı kararı (18.08): **dava TEK kart kalır, müvekkiller kartın altında;
kart föy bazında BÖLÜNMEZ.** Karşı tarafın teslimleri ise sonsuza dek SistemNo
anahtarlıdır ve bir kartta birden çok SistemNo yaşar (ön analiz: 1.211 mevcut
kart 2+ föyü birleşik taşıyor; TKU'da 1.537 çok üyeli grup / 4.030 satır).
`cases.sistem_no` tek kolonu bunu taşıyamaz — bu modül kartın kimliğini bölmeden
föyleri kartın altına asar.

Desen `managers/stage_decisions.py`ın (G062) ve `case_manager.sync_current_esas`ın
(G045) kardeşidir; o modüllerin davranışı DEĞİŞMEZ — burası `cases.sistem_no`,
`cases.tku_no` ve `case_documents` satırlarına ASLA yazmaz (G063 "dokunma"
listesi; nihai tekilleştirme FAZ F aktarım turunun işi).

Kurallar:

* **`sistem_no` idempotency anahtarıdır.** Teslim partiler hâlinde ve düzeltme
  listeleriyle tekrar tekrar gelecek: aynı föyün ikinci yazımı satır İKİLEMEZ,
  günceller (`uq_case_foys_sistem_no` kısıtı + `upsert_foy`). Anahtar KIRPILMAZ,
  sınırı aşarsa REDDEDİLİR — kırpma iki farklı föyü tek satıra çökertebilirdi,
  yani tablonun var oluş sebebini yok ederdi. Kimlik olmayan alanlar
  (`tku_no`/`hasar_no`/`source`) stage_decisions deseniyle WARNING'li kırpılır.
* **Verilmeyen alan KORUNUR.** `None` "boşalt" DEĞİL "bu teslimde yok"
  demektir: partili teslimde eksik sütun mevcut değeri silmemeli. Tek istisna
  aşağıdaki kart değişimidir.
* **Föyün tarafı kendi kartının tarafıdır.** `case_party_id` verilirse AYNI
  kartın bir tarafını göstermek zorundadır; föy başka karta taşınırsa ve yeni
  taraf verilmemişse eski bağ DÜŞÜRÜLÜR (eski kartın tarafını yeni kartın föyünde
  tutmak sessiz veri çöpü olurdu). İkisi de WARNING'ler.
* Fonksiyonlar COMMIT ETMEZ (flush eder) — işlem sınırı çağıranındır
  (`sync_current_esas`/`add_stage_decision` ile aynı sözleşme).
"""
import logging
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from db_errors import is_unique_violation

logger = logging.getLogger("CaseManager")

# Toplu sorgunun IN listesi parça boyu. Aktarım tek turda binlerce SistemNo
# soracak (10.08 teslim paketi: 8.409 föy); tek dev IN listesi hem sürücünün
# parametre sınırını hem planlayıcıyı zorlar.
_CHUNK = 1000

# Kolon sınırları modelden okunur, elle tekrarlanmaz (stage_decisions._LIMITS
# gerekçesi: şema büyürse kod kendiliğinden uyar).
_LIMITS: Dict[str, int] = {}
for _column in models.CaseFoy.__table__.columns:
    _limit = getattr(_column.type, "length", None)
    if _limit:
        _LIMITS[_column.name] = _limit

# Upsert'in güncelleyebildiği alanlar (kimlik `sistem_no` ile bağ `case_id`
# hariç — ikisi de ayrı ele alınır).
_UPDATABLE = ("case_party_id", "tku_no", "hasar_no", "source")


def _clamped(value: Optional[str], column: str) -> Optional[str]:
    """Kimlik OLMAYAN kısa metni boşluk-normalize edip kolon sınırına kırpar.

    Taşan bir hasar numarası yüzünden föyün tamamını düşürmek orantısız olurdu
    (stage_decisions._clamped gerekçesi); kırpma sessiz de değildir —
    deneme-düzeyi durum WARNING'dir (log sözleşmesi).
    """
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    limit = _LIMITS.get(column)
    if limit and len(text) > limit:
        logger.warning(
            f"case_foys.{column} kolon sınırına kırpıldı (>{limit}): {text[:60]!r}…"
        )
        text = text[:limit]
    return text


def _validated_sistem_no(value: Optional[str]) -> str:
    """Föyün KİMLİĞİ: normalize edilir ama ASLA kırpılmaz.

    Kırpılsaydı sınırı aşan iki farklı SistemNo aynı anahtara düşer ve unique
    kısıt bunları TEK föy sayardı — tablonun taşımak için var olduğu ayrımı
    tam da o noktada kaybederdik. Sessiz veri kaybı yerine gürültülü ret.
    """
    if value is None:
        raise ValueError("sistem_no zorunlu (föyün kimliği)")
    anahtar = " ".join(str(value).split())
    if not anahtar:
        raise ValueError("sistem_no boş olamaz (föyün kimliği)")
    limit = _LIMITS["sistem_no"]
    if len(anahtar) > limit:
        raise ValueError(
            f"sistem_no kolon sınırını aşıyor (>{limit}, kırpılmaz): {anahtar[:60]!r}"
        )
    return anahtar


def _validated_party(db: Session, case_id: int, case_party_id: Optional[int]) -> Optional[int]:
    """`case_party_id` AYNI kartın tarafı olmalı; değilse yazım reddedilir.

    Çapraz kart bağı veri çöpü olurdu (`add_stage_decision`ın `kaynak_id`
    doğrulamasıyla aynı gerekçe): föy kartın altında yaşar, tarafı da o kartın
    tarafıdır.
    """
    if case_party_id is None:
        return None
    party = db.get(models.CaseParty, case_party_id)
    if party is None or party.case_id != case_id:
        raise ValueError(
            f"case_party_id={case_party_id} bu kartın tarafı değil (dava {case_id})"
        )
    return case_party_id


def _is_duplicate_violation(exc: IntegrityError) -> bool:
    """UNIQUE ihlali mi? PG'de SQLSTATE 23505 ile; SQLSTATE taşımayan diyalekt
    (sqlite birim koşusu) için ayırt edilemez → çakışma VARSAYILIR ve çağıran
    satırı okumayı dener; okuyamazsa özgün hata yeniden yükselir. SQLSTATE VARSA
    ama 23505 DEĞİLSE (örn. FK 23503) çakışma SAYILMAZ — yanlış sınıflandırma
    gerçek hatayı sessizce yutardı (stage_decisions'taki akıl yürütme)."""
    if is_unique_violation(exc):
        return True
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code is None


def _insert_foy(db: Session, values: Dict[str, Any]) -> models.CaseFoy:
    """Satırı SAVEPOINT içinde yazar; çakışmada oturum kullanılabilir kalır."""
    row = models.CaseFoy(**values)
    with db.begin_nested():
        db.add(row)
        db.flush()
    return row


def _apply_update(
    db: Session, row: models.CaseFoy, case_id: int, degerler: Dict[str, Any]
) -> models.CaseFoy:
    """Mevcut föyü tazeler (ON CONFLICT DO UPDATE'in alan karşılığı).

    `None` gelen alan KORUNUR — partili teslimde eksik sütun mevcut değeri
    silmemeli. Kart değişimi meşrudur (düzeltme listesi föyü doğru karta
    taşıyabilir) ama sessiz değildir; taşınan föyün eski taraf bağı da düşer.
    """
    if row.case_id != case_id:
        logger.warning(
            f"Föy {row.sistem_no} kart değiştiriyor: dava {row.case_id} → {case_id} "
            f"(kaynak: {degerler.get('source') or row.source or '-'})"
        )
        row.case_id = case_id
        if degerler.get("case_party_id") is None and row.case_party_id is not None:
            logger.warning(
                f"Föy {row.sistem_no} taraf bağı düştü: eski taraf "
                f"{row.case_party_id} yeni kartın tarafı değil"
            )
            row.case_party_id = None
    for alan, deger in degerler.items():
        if deger is not None:
            setattr(row, alan, deger)
    db.flush()
    return row


def upsert_foy(
    db: Session,
    case: models.Case,
    *,
    sistem_no: str,
    case_party_id: Optional[int] = None,
    tku_no: Optional[str] = None,
    hasar_no: Optional[str] = None,
    source: Optional[str] = None,
) -> models.CaseFoy:
    """Föyü kartın (ve varsa müvekkilin) altına yazar — İDEMPOTENT.

    Aynı `sistem_no` ikinci kez gelirse satır ikilenmez, güncellenir; teslim
    partiler hâlinde ve düzeltme listeleriyle tekrar geleceği için bu
    aktarımın temel sözleşmesidir. Dönen satır flush edilmiştir (id dolu);
    commit çağıranın işi.
    """
    anahtar = _validated_sistem_no(sistem_no)

    if case.id is None:
        db.flush()          # FK için kart id'si şart (sync_current_esas deseni)
    case_id = cast(int, case.id)

    degerler: Dict[str, Any] = {
        "case_party_id": _validated_party(db, case_id, case_party_id),
        "tku_no": _clamped(tku_no, "tku_no"),
        "hasar_no": _clamped(hasar_no, "hasar_no"),
        "source": _clamped(source, "source"),
    }

    mevcut = get_foy(db, anahtar)
    if mevcut is not None:
        return _apply_update(db, mevcut, case_id, degerler)

    try:
        return _insert_foy(db, {"sistem_no": anahtar, "case_id": case_id, **degerler})
    except IntegrityError as exc:
        # Yarış: başka bir worker aynı föyü aramızda yazdı. Kısıt kırmızısı
        # doğruluğun KANITIDIR (G049) — satırı okuyup güncelleyerek devam et.
        if not _is_duplicate_violation(exc):
            raise
        mevcut = get_foy(db, anahtar)
        if mevcut is None:
            raise           # çakışma değilmiş (FK/NOT NULL) — gerçek hatayı gizleme
        return _apply_update(db, mevcut, case_id, degerler)


def get_foy(db: Session, sistem_no: str) -> Optional[models.CaseFoy]:
    """SistemNo → föy satırı (yoksa None). Anahtar upsert'le AYNI normalizasyondan
    geçer; yoksa 'yazdım ama bulamıyorum' sınıfı sessiz kusur doğardı."""
    if sistem_no is None:
        return None
    anahtar = " ".join(str(sistem_no).split())
    if not anahtar:
        return None
    return (
        db.query(models.CaseFoy)
        .filter(models.CaseFoy.sistem_no == anahtar)
        .first()
    )


def get_case_foys(db: Session, case_id: int) -> List[models.CaseFoy]:
    """Kartın FÖYLERİ — `sistem_no` sırasıyla ORM satırları.

    Bir kartta birden çok föy OLAĞANDIR (1.211 mevcut kart böyle); okuma/yazma
    uçları ve UI bu görevin kapsamı dışında (FAZ F + sonrası), testler ve
    gelecekteki route katmanı bu tek noktadan okur.
    """
    return (
        db.query(models.CaseFoy)
        .filter(models.CaseFoy.case_id == case_id)
        .order_by(models.CaseFoy.sistem_no)
        .all()
    )


def map_sistem_no_to_case(db: Session, sistem_nolar) -> Dict[str, int]:
    """Toplu eşleme: {sistem_no: case_id} — bilinmeyen anahtarlar sözlükte YOK.

    Aktarım turunun sıcak sorgusu: elindeki föy listesinin hangilerinin zaten
    bir kartta olduğunu TEK turda sorar (satır başına SELECT değil). Sonuç ORM
    satırı değil iki kolondur; binlerce satırı hydrate etmenin anlamı yok.
    """
    anahtarlar = []
    for ham in sistem_nolar or []:
        if ham is None:
            continue
        anahtar = " ".join(str(ham).split())
        if anahtar:
            anahtarlar.append(anahtar)
    if not anahtarlar:
        return {}

    sonuc: Dict[str, int] = {}
    benzersiz = list(dict.fromkeys(anahtarlar))     # sıra korunur, mükerrer düşer
    for i in range(0, len(benzersiz), _CHUNK):
        parca = benzersiz[i:i + _CHUNK]
        rows = (
            db.query(models.CaseFoy.sistem_no, models.CaseFoy.case_id)
            .filter(models.CaseFoy.sistem_no.in_(parca))
            .all()
        )
        for sistem_no, case_id in rows:
            sonuc[sistem_no] = case_id
    return sonuc
