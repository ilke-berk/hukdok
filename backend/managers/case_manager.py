"""Dava CRUD ve takip işlemleri.

Avukat adı çözümleme mantığı managers/lawyer_resolver.py'de,
referans listeleri managers/reference_lists.py'dedir.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import SessionLocal, SQL_FOLD_FROM, SQL_FOLD_TO
from db_errors import is_unique_violation
import models
from party_check import normalize_party_key, normalize_tc
from required_fields import REQUIRED_CASE_FIELDS, compute_missing_fields
from managers.lawyer_resolver import (
    _norm_name, _split_persons, _resolve_lawyer_aliases, _value_matches,
    canonicalize_lawyers,
)

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


def _missing_required_clause():
    """Zorunlu alanlardan en az biri boş olan davalar için SQL koşulu.

    compute_missing_fields'ın SQL karşılığı — REQUIRED_CASE_FIELDS'tan türetilir,
    liste değişince otomatik uyum sağlar. Tarih kolonlarında yalnız NULL,
    metinlerde NULL/boş-trim kontrolü yapılır; karşı taraf TC kuralı da dahildir.
    """
    from sqlalchemy import Date, and_, exists, func, or_

    conds = []
    for f in REQUIRED_CASE_FIELDS:
        col = getattr(models.Case, f["field"], None)
        if col is None:
            continue
        if isinstance(col.type, Date):
            conds.append(col.is_(None))
        else:
            conds.append(or_(col.is_(None), func.trim(col) == ""))

    cp = models.CaseParty
    has_counter = exists().where(
        and_(cp.case_id == models.Case.id, cp.party_type == "COUNTER")
    )
    has_counter_tc = exists().where(
        and_(
            cp.case_id == models.Case.id,
            cp.party_type == "COUNTER",
            cp.tc_no.isnot(None),
            func.trim(cp.tc_no) != "",
        )
    )
    conds.append(and_(has_counter, ~has_counter_tc))
    return or_(*conds)


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
) -> "tuple[list[dict], int]":
    """Filtrelenmiş dava listesini ve OFFSET/LIMIT öncesi toplam sayıyı döndürür."""
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
            query = query.filter(_missing_required_clause())

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
            from sqlalchemy import or_, and_
            terms = q.strip().split()
            term_filters = []

            for term in terms:
                if not exact and len(term) < 2:
                    continue
                search_pattern = term if exact else f"%{term}%"

                if exact:
                    # Exact mode: case number fields exact match + tüm diğer alanlar contains
                    contains = f"%{term}%"
                    conditions = [
                        models.Case.esas_no.ilike(search_pattern),
                        models.Case.tracking_no.ilike(search_pattern),
                        models.Case.klasor_no_2.ilike(search_pattern),
                        models.Case.tku_no.ilike(search_pattern),      # Eski sistem olay no
                        models.Case.sistem_no.ilike(search_pattern),   # Eski sistem kayıt no
                        models.Case.court.ilike(contains),
                        models.Case.subject.ilike(contains),
                        models.Case.responsible_lawyer_name.ilike(contains),
                        models.Case.uyap_lawyer_name.ilike(contains),
                        models.Case.parties.any(models.CaseParty.name.ilike(contains)),
                        models.Case.lawyers.any(models.CaseLawyer.name.ilike(contains)),
                    ]
                else:
                    # Normal mode: search all fields
                    conditions = [
                        models.Case.tracking_no.ilike(search_pattern),
                        models.Case.esas_no.ilike(search_pattern),
                        models.Case.klasor_no_2.ilike(search_pattern),  # Eski sistem no
                        models.Case.tku_no.ilike(search_pattern),       # Eski sistem olay no (TKU-784)
                        models.Case.sistem_no.ilike(search_pattern),    # Eski sistem kayıt no (SSTMN-9425)
                        models.Case.court.ilike(search_pattern),
                        models.Case.subject.ilike(search_pattern),
                        models.Case.notes.ilike(search_pattern),
                        models.Case.responsible_lawyer_name.ilike(search_pattern),
                        models.Case.uyap_lawyer_name.ilike(search_pattern),
                        models.Case.parties.any(models.CaseParty.name.ilike(search_pattern)),
                        models.Case.lawyers.any(models.CaseLawyer.name.ilike(search_pattern)),
                        models.Case.history.any(models.CaseHistory.old_value.ilike(search_pattern)),
                    ]

                term_filters.append(or_(*conditions))

            if term_filters:
                query = query.filter(and_(*term_filters))

        # Toplam sayı — sayfalama (offset/limit) uygulanmadan önce.
        # Filtreler .any()/EXISTS tabanlı olduğundan satır çoğalması yok.
        total = query.count()

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
    items, _total = get_cases(q=query, limit=25, exact=exact, status=status, tenant_id=tenant_id)
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
        new_case = models.Case(
            tracking_no=data.get("tracking_no"),
            esas_no=data.get("esas_no"),
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
TRACKING_FIELDS = [
    "case_stage",
    "dosya_son_durumu",
    # Dosya durumu
    "status",
    # Yerel Karar
    "karar_tarihi", "karar_turu", "karar_lehine",
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
    # Kesinleşme / İnfaz
    "kesinlesme_tarihi", "infaz_tarihi",
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

        for field, value in tracking_changes(data):
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
