"""Dava CRUD ve takip işlemleri.

Avukat adı çözümleme mantığı managers/lawyer_resolver.py'de,
referans listeleri managers/reference_lists.py'dedir.
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import intersect, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import SessionLocal, SQL_FOLD_FROM, SQL_FOLD_TO
from db_errors import is_unique_violation
import models
from party_check import normalize_party_key, normalize_tc
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
    canonicalize_lawyers,
)
# G066: karar durumu kapalı havuz kapısı tarihçe modülünde yaşar (ikinci
# uygulama çıkarılmadı). Import yönü tek yönlüdür — `stage_decisions` yalnız
# `models`/`db_errors` import eder, `case_manager`ı ÇAĞIRMAZ: döngü yok,
# "sonra import" hilesine gerek kalmadı.
from managers import stage_decisions

logger = logging.getLogger("AdminManager")

# Faz 5-B (plan 5.3): tracking_no çakışması SQLSTATE 23505 + ihlal edilen
# indeksin ADIYLA tespit edilir (eski `"tracking_no" in str(e)` metin eşlemesi
# kalktı). Ad, models.Case.tracking_no'nun `unique=True, index=True`
# tanımından SQLAlchemy'nin ürettiği indekstir — `cases` tablosunda
# `uq_cases_sistem_no` da UNIQUE olduğu için ad eşlemesi ŞART: sistem_no
# çakışmasına "ofis numarası zaten kayıtlı" demek kullanıcıyı boşuna sıra
# numarası artırmaya iterdi.
TRACKING_NO_UNIQUE_INDEX = "ix_cases_tracking_no"


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

    `_value_matches`in ÜÇ kuralı da (kod birebir / ≥2 ortak token / benzersiz
    soyad) eşleşebilmek için değerin normalize halinde `tokens` kümesinden en az
    bir öğe bulunmasını GEREKTİRİR — kural 2 en az bir çekirdek token, kural 3
    soyadın kendisi, kural 1 kodun kendisi. Dolayısıyla bu koşul Python
    doğrulamasının sonucunu asla eleyemez; yalnız aday sayısını kırpar. Kesin
    kararı yine `_value_matches` verir, sonuç kümesi bit-bit aynı kalır.

    Ünvan atma (`_TITLE_TOKENS`) SQL tarafında YAPILMAZ; gerekmiyor da: ünvan
    atmak yalnız token siler, kalan token'ların karakter dizisini bozmaz →
    '%token%' araması ünvanlı ham metinde de bulur (yön: SQL ⊇ Python).
    """
    from sqlalchemy import or_
    folded = _sql_folded(column)
    return or_(*[folded.like(f"%{t}%") for t in sorted(tokens)])


def _lawyer_filter_case_ids(db, selected: str, tenant_id: Optional[str]):
    """Seçilen avukatla eşleşen dava ID kümesini döndürür (toleranslı).
    responsible_lawyer_name + case_lawyers ilişkisinin ikisini de tarar.

    FAZ E/E7: eşleştirme mantığı Python'da kalır (ünvan/diakritik/çoklu-avukat
    kuralları SQL'e sadakatle çevrilemez), ama ADAYLAR artık SQL'de daralır —
    eskiden her filtrede `cases` tablosunun tamamı (14.345 satır) Python'a
    çekiliyordu. Ölçüm: 159 avukat seçimi, ortalama 47,4 ms → 3,0 ms (~16×);
    159/159'unda eski ve yeni id kümeleri birebir aynı.
    """
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
        core_tokens, code_norm, surname, surname_unique = aliases
        tokens = {t for t in core_tokens if t}
        if code_norm:
            tokens.add(code_norm)

        def _case_matches(value):
            return _value_matches(value, core_tokens, code_norm, surname, surname_unique)

        _lawyer_matches = _case_matches

    if not tokens:
        # Çekirdek token da kod da yok → üç kuralın hiçbiri eşleşemez.
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
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
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
        }
        result["service_type"] = item.service_type
        result["missing_required_fields"] = compute_missing_fields(result, result["parties"])
        return result
    except Exception as e:
        logger.error(f"Get Case Error: {e}")
        return None
    finally:
        db.close()


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
            elif s in ("KAPALI", "MAHZEN"):
                stats["closed"] += count
            elif s == "TEMYIZ":
                stats["appeal"] += count

        for status, count in stats["statuses"].items():
            if (status or "").upper().startswith("DANI"):
                stats["danis_active"] += count

        return stats
    except Exception as e:
        logger.error(f"Get Case Stats Error: {e}")
        return {"total": 0, "active": 0, "closed": 0, "appeal": 0, "danis_active": 0, "statuses": {}}
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
    """
    db.flush()
    parties = db.query(models.CaseParty.party_type, models.CaseParty.tc_no).filter(
        models.CaseParty.case_id == case.id
    ).all()
    missing = compute_missing_fields(_case_snapshot(case), parties)
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
    davranışın aynısı, normal moddaki 14 koldan ikisi eksik kalır.
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
        select(models.Case.id).where(models.Case.tku_no.ilike(pattern)),  # Eski sistem olay no (TKU-784)
        select(models.Case.id).where(models.Case.sistem_no.ilike(pattern)),  # Eski sistem kayıt no (SSTMN-9425)
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
    """
    try:
        db = SessionLocal()
        query = db.query(models.Case).options(
            selectinload(models.Case.parties),
            selectinload(models.Case.lawyers)
        ).filter(models.Case.active.is_(True))
        query = _apply_tenant_filter(query, tenant_id)

        if status and status != "ALL":
            query = query.filter(models.Case.status == status)

        if file_type and file_type != "ALL":
            query = query.filter(models.Case.file_type == file_type)

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

        # Toplam sayı — sayfalama (offset/limit) uygulanmadan önce.
        # UNION'lı id kümesi zaten DISTINCT'tir, satır çoğalması yok.
        # İstenmezse COUNT hiç koşmaz: aramada bu, her tuş vuruşunda ikinci bir
        # tam taramayı ortadan kaldırır (E3).
        total = query.count() if with_total else -1

        # Relevance sıralaması: sorgu varsa exact > prefix > partial > diğer
        if q and len(q.strip()) >= min_len:
            from sqlalchemy import case as sa_case
            raw = q.strip()
            relevance = sa_case(
                (models.Case.esas_no.ilike(raw), 1),
                (models.Case.tracking_no.ilike(raw), 1),
                (models.Case.klasor_no_2.ilike(raw), 1),
                (models.Case.tku_no.ilike(raw), 1),
                (models.Case.sistem_no.ilike(raw), 1),
                (models.Case.esas_no.ilike(f"{raw}%"), 2),
                (models.Case.tracking_no.ilike(f"{raw}%"), 2),
                (models.Case.klasor_no_2.ilike(f"{raw}%"), 2),
                (models.Case.tku_no.ilike(f"{raw}%"), 2),
                (models.Case.sistem_no.ilike(f"{raw}%"), 2),
                else_=3,
            )
            # id tiebreaker: updated_at unique değil — eşitlikte sayfalar arası
            # satır tekrarı/atlamasını önler
            items = query.order_by(relevance, models.Case.updated_at.desc(), models.Case.id.desc()).offset(offset).limit(limit).all()
        else:
            items = query.order_by(models.Case.updated_at.desc(), models.Case.id.desc()).offset(offset).limit(limit).all()

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


def update_case(case_id: int, data: dict, tenant_id: str = None):
    """Dava alanlarını günceller.

    Dönüş (Faz 5-B, plan 5.3 — reference_lists.update_item ile AYNI ayrım):
      True  — başarı
      None  — dava yok / bu tenant'a görünmüyor → route 404 döner
      False — güncelleme sırasında hata → route 500 döner
    Ayrımdan önce ikisi de False'tu; "olmayan davayı güncelle" 500 oluyordu.
    """
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return None

        # Fields to track for history
        tracked_fields = ["esas_no", "court", "status"]

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
                    new_value=str(new_val)
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
        case.service_type = data.get("service_type", case.service_type)
        case.subject = data.get("subject", case.subject)
        case.responsible_lawyer_name = data.get("responsible_lawyer_name", case.responsible_lawyer_name)
        case.uyap_lawyer_name = data.get("uyap_lawyer_name", case.uyap_lawyer_name)
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
        for p in new_parties:
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


def add_case(data: dict, tenant_id: str = None):
    # Zorunlu alan eksikliği kaydı ENGELLEMEZ (kullanıcı kararı 2026-07-31 rev.2):
    # dosya DERDEST olarak açılır, eksikler get_case/get_cases'teki
    # missing_required_fields ile panelde uyarı olarak görünür ve filtrelenir.
    try:
        db = SessionLocal()

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

        # 1. Create Case
        # esas_no BİLİNÇLİ olarak burada verilmez — türetilmiş değerdir ve
        # yalnız sync_current_esas yazar (flush'tan sonra, G045).
        new_case = models.Case(
            tracking_no=data.get("tracking_no"),
            status=data.get("status", "DERDEST"),
            service_type=data.get("service_type"),
            file_type=data.get("file_type"),
            sub_type=data.get("sub_type"),
            subject=data.get("subject"),
            court=data.get("court"),
            opening_date=opening_date,
            responsible_lawyer_name=data.get("responsible_lawyer_name"),
            uyap_lawyer_name=data.get("uyap_lawyer_name"),
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
        is_consult = (data.get("status") == "DANIŞ")
        parties = data.get("parties", [])
        for p in parties:
            client_id = p.get("client_id")
            party_type = p.get("party_type")
            name = p.get("name")

            # Otomatik Müşteri Oluşturma Yükseltmesi
            if party_type == "CLIENT" and name and not client_id:
                existing_client = None
                # TC verilmişse önce TC ile eşle — aynı isimli iki cari belirsizliğini çözer
                tc = (p.get("tc_no") or "").strip()
                if tc:
                    existing_client = db.query(models.Client).filter(
                        models.Client.tc_no == tc,
                        models.Client.deleted_at.is_(None),  # silinmiş cariye oto-bağlanma
                    ).first()
                if not existing_client:
                    existing_client = db.query(models.Client).filter(
                        models.Client.name.ilike(name.strip()),
                        models.Client.deleted_at.is_(None),
                    ).first()
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
        if is_unique_violation(e, TRACKING_NO_UNIQUE_INDEX):
            # Faz 3-D: çakışma burada NİHAİ değildir — /commit route'u önce
            # idempotent çözümleme dener (kaybolan yanıt sonrası retry kendi
            # davasına çarpmış olabilir). Log sözleşmesi gereği burada WARNING;
            # [TRACKING_NO_COLLISION] ERROR telemetrisini gerçek 409'u döndüren
            # route'lar üretir (case_intake.py commit + cases.py api_add_case).
            logger.warning(f"Add Case: tracking_no çakışması — {data.get('tracking_no')}")
            return {"error": "duplicate_tracking_no"}
        logger.error(f"Add Case Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Add Case Error: {e}")
        db.rollback()
        return None
    finally:
        db.close()


# find_idempotent_commit_match: "kaybolan yanıt" retry penceresi. Otomatik
# retry saniyeler, elle tekrar tıklama dakikalar, taslaktan devam ertesi gün
# olabilir — 24 saat hepsini kapsar; daha eski bir dava aynı numarayı gerçek
# çakışmayla (sayaç önerisi bug'ı, 2026-07-16) tutuyordur.
IDEMPOTENT_MATCH_WINDOW_HOURS = 24


def _norm_plain(value) -> str:
    """esas_no/mahkeme karşılaştırma anahtarı: boşluk sadeleştir + casefold.
    Aynı taslaktan gelen retry'da değerler bayt-bayt aynıdır; bu normalize
    yalnız zararsız boşluk/büyüklük farklarını tolere eder. (Parametre
    bilinçli tipsiz: eski stil Column[] modellerinde mypy arg-type üretiyor.)"""
    return " ".join(str(value or "").split()).casefold()


def find_idempotent_commit_match(data: dict, tenant_id: Optional[str] = None) -> Optional[dict]:
    """duplicate_tracking_no anında: mevcut dava BU isteğin daha önce başarıyla
    kaydolmuş hâli mi? (yanıtı kaybolan commit / çift tıklama — Faz 3-D, 3.5)

    MUHAFAZAKÂR eşleşme: yanlış pozitif (farklı davayı "aynı" sanmak) yeni
    davayı sessizce yutar ve belgeleri yanlış karta arşivler; şüphede None
    dönülür → çağıran 409'a düşer (bugünkü davranış, kullanıcı karar verir).
    Kriterlerin HEPSİ:
      1. tracking_no birebir + dava soft-delete edilmemiş (silinmiş kayıtla
         çakışma sayaç bug'ının bilinen hali → gerçek 409)
      2. tenant görünürlüğü: dava başka tenant'a damgalıysa eşleşme yok
      3. created_at son IDEMPOTENT_MATCH_WINDOW_HOURS içinde
      4. esas_no ve court normalize eşit (ikisi de boş dahil — aynı taslaktan
         gelen retry'da birebir aynıdırlar)
      5. taraf kümesi eşit ve BOŞ DEĞİL: {(party_type, normalize_party_key(ad))}
    Eşleşmede add_case dönüş şekli + "reused": True döner.
    """
    tracking_no = data.get("tracking_no")
    if not tracking_no:
        return None
    req_parties = {
        ((p.get("party_type") or "").strip().upper(), normalize_party_key(p.get("name") or ""))
        for p in (data.get("parties") or [])
        if (p.get("name") or "").strip()
    }
    if not req_parties:
        # Tarafsız istek için elimizde güçlü kimlik yok — 409 sürsün.
        return None

    db = SessionLocal()
    try:
        case = (
            db.query(models.Case)
            .options(selectinload(models.Case.parties))
            .filter(
                models.Case.tracking_no == tracking_no,
                models.Case.deleted_at.is_(None),
            )
            .first()
        )
        if case is None:
            return None
        if tenant_id and case.tenant_id and case.tenant_id != tenant_id:
            return None

        created_at = case.created_at
        if created_at is None:
            return None
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created_at
        if age > timedelta(hours=IDEMPOTENT_MATCH_WINDOW_HOURS):
            return None

        if _norm_plain(data.get("esas_no")) != _norm_plain(case.esas_no):
            return None
        if _norm_plain(data.get("court")) != _norm_plain(case.court):
            return None

        case_parties = {
            ((p.party_type or "").strip().upper(), normalize_party_key(p.name or ""))
            for p in case.parties
            if (p.name or "").strip()
        }
        if req_parties != case_parties:
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
    except Exception as e:
        # Çözümleme başarısızlığı 409'u engellememeli (bugünkü davranışa düş).
        logger.warning(f"Idempotent commit eşleşmesi bakılamadı: {e}")
        return None
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
]


def tracking_changes(data: dict) -> list:
    """exclude_unset dict'inden uygulanacak (alan, değer) çiftleri (saf).

    Sözleşme (Faz 1): data yalnız istemcinin GÖNDERDİĞİ alanları içerir
    (route model_dump(exclude_unset=True) ile üretir). Gönderilmeyen alan
    listeye girmez → dokunulmaz; None gönderilen girer → alan silinir.
    """
    return [(f, data[f]) for f in TRACKING_FIELDS if f in data]


def update_case_tracking(case_id: int, data: dict, changed_by: str, source: str = "MANUAL", tenant_id: str = None) -> bool:
    """Dava takip bilgilerini günceller ve aşama değişmişse CaseStageLog kaydı ekler.

    data yalnız güncellenecek alanları içermeli (exclude_unset); None değer
    alanı temizler.

    Dört karar durumu alanı (yerel/istinaf/temyiz/karar düzeltme) G060 kapalı
    havuzlarına karşı doğrulanır (G066): kapalılık artık yalnız arayüzde değil
    — API'yi doğrudan çağıran da liste dışı değer yazamaz. Doğrulama YAZIMDAN
    ÖNCE toptan koşar: bir alan reddedilirse HİÇBİRİ yazılmaz, hata
    `InvalidDecisionStatusError` olarak yükselir (api.py 400'e çevirir) — bu
    fonksiyonun `False` dönüşü "dava bulunamadı/yazılamadı" anlamını korur.
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

        # Kapalı havuz kapısı (G066) ÖNCE, yazım SONRA: kısmi uygulama olmasın.
        degisiklikler = [
            (field, stage_decisions.validated_status_for_column(db, field, value))
            for field, value in tracking_changes(data)
        ]
        for field, value in degisiklikler:
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
    except stage_decisions.InvalidDecisionStatusError:
        # İstemci hatası — nihai başarısızlık DEĞİL: ERROR basılmaz (log
        # sözleşmesi) ve False'a yutulmaz; route katmanına 400 olarak çıkar.
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"update_case_tracking error: {e}")
        db.rollback()
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
