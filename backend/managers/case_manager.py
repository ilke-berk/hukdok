"""Dava CRUD ve takip işlemleri.

Avukat adı çözümleme mantığı managers/lawyer_resolver.py'de,
referans listeleri managers/reference_lists.py'dedir.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import SessionLocal
import models
from party_check import normalize_party_key, normalize_tc
from required_fields import REQUIRED_CASE_FIELDS, compute_missing_fields
from managers.lawyer_resolver import (
    _norm_name, _split_persons, _resolve_lawyer_aliases, _value_matches,
    canonicalize_lawyers,
)

logger = logging.getLogger("AdminManager")


def _parse_date_field(value, field_name: str):
    """'YYYY-MM-DD' formatındaki alanı date'e çevirir; geçersizse loglayıp None döner."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Geçersiz tarih değeri atlandı: {field_name}={value!r}")
        return None


def _apply_tenant_filter(query, tenant_id: Optional[str]):
    """Sorguya tenant izolasyon filtresi uygular.
    tenant_id'si NULL olan kayıtlar (eski/migrasyon öncesi) her tenant'a görünür.
    """
    if tenant_id:
        from sqlalchemy import or_
        return query.filter(
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        )
    return query


def _lawyer_filter_case_ids(db, selected: str, tenant_id: Optional[str]):
    """Seçilen avukatla eşleşen dava ID kümesini döndürür (toleranslı).
    responsible_lawyer_name + case_lawyers ilişkisinin ikisini de tarar."""
    aliases = _resolve_lawyer_aliases(selected)
    matched: set = set()

    if aliases is None:
        # Config'te çözülemedi → normalize edilmiş "contains" ile geriye dönük güvenli arama
        sel_norm = _norm_name(selected)
        if not sel_norm:
            return matched
        q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(models.Case.active.is_(True))
        q = _apply_tenant_filter(q, tenant_id)
        for cid, rn in q.all():
            if any(sel_norm in _norm_name(p) for p in _split_persons(rn)):
                matched.add(cid)
        for cid, nm in db.query(models.CaseLawyer.case_id, models.CaseLawyer.name).all():
            if sel_norm in _norm_name(nm):
                matched.add(cid)
        return matched

    core_tokens, code_norm, surname, surname_unique = aliases
    q = db.query(models.Case.id, models.Case.responsible_lawyer_name).filter(models.Case.active.is_(True))
    q = _apply_tenant_filter(q, tenant_id)
    for cid, rn in q.all():
        if _value_matches(rn, core_tokens, code_norm, surname, surname_unique):
            matched.add(cid)
    for cid, nm in db.query(models.CaseLawyer.case_id, models.CaseLawyer.name).all():
        if _value_matches(nm, core_tokens, code_norm, surname, surname_unique):
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
            "notes": item.notes,
            "parties": [{"id": p.id, "name": p.name, "role": p.role, "party_type": p.party_type, "client_id": p.client_id, "birth_year": p.birth_year, "gender": p.gender, "tc_no": p.tc_no} for p in item.parties],
            "lawyers": [{"name": lw.name, "lawyer_id": lw.lawyer_id} for lw in item.lawyers],
            "history": [{"field": h.field_name, "old": h.old_value, "new": h.new_value, "date": h.changed_at.isoformat()} for h in sorted(item.history, key=lambda x: x.changed_at, reverse=True)],
            "documents": [{"id": d.id, "original_filename": d.original_filename, "stored_filename": d.stored_filename, "sharepoint_url": d.sharepoint_url, "belge_turu_kodu": d.belge_turu_kodu, "belge_turu_adi": d.belge_turu_adi, "ai_summary": d.ai_summary, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None, "case_party_id": d.case_party_id, "case_party_name": d.case_party.name if d.case_party else None} for d in item.documents],
            # Takip alanları
            "case_stage": item.case_stage,
            "dosya_son_durumu": item.dosya_son_durumu,
            "karar_tarihi": item.karar_tarihi.isoformat() if item.karar_tarihi else None,
            "karar_turu": item.karar_turu,
            "karar_lehine": item.karar_lehine,
            "karar_no": item.karar_no,
            "karar_teblig_tarihi": item.karar_teblig_tarihi.isoformat() if item.karar_teblig_tarihi else None,
            "karar_aciklama": item.karar_aciklama,
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
                (models.Case.esas_no.ilike(f"{raw}%"), 2),
                (models.Case.tracking_no.ilike(f"{raw}%"), 2),
                (models.Case.klasor_no_2.ilike(f"{raw}%"), 2),
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
    by_tc, by_name = {}, {}
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


def update_case(case_id: int, data: dict, tenant_id: str = None):
    try:
        db = SessionLocal()
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = _apply_tenant_filter(query, tenant_id)
        case = query.first()
        if not case:
            return False

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

        def _resolve_client_id(p):
            client_id = p.get("client_id")
            name = p.get("name")
            # Otomatik Müşteri Oluşturma Yükseltmesi
            if p.get("party_type") == "CLIENT" and name and not client_id:
                existing_client = db.query(models.Client).filter(
                    models.Client.name.ilike(name.strip())
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

        rows_by_id = {ep.id: ep for ep in existing_parties}
        for pid, p in updates:
            row = rows_by_id[pid]
            row.client_id = _resolve_client_id(p)
            row.name = p.get("name")
            row.role = p.get("role")
            row.party_type = p.get("party_type")
            row.birth_year = p.get("birth_year")
            row.gender = p.get("gender")
            row.tc_no = (p.get("tc_no") or "").strip() or None
        for p in inserts:
            db.add(models.CaseParty(
                case_id=case_id,
                client_id=_resolve_client_id(p),
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


def find_duplicate_cases(esas_no: str, court: str = None, tenant_id: str = None):
    """Aynı esas no'lu aktif davaları bulur (mükerrer açılış uyarısı için).

    Esas no karşılaştırması normalize + sıfır dolgu toleranslıdır
    ("2024/123" == "2024 / 0123"); mahkeme benzerliği bilgi amaçlı
    `court_match` bayrağı olarak döner — aynı esas no farklı mahkemede
    meşru olabilir, karar kullanıcının.
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
    except Exception as e:
        logger.error(f"Find Duplicate Cases Error: {e}")
        return []
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
                        models.Client.tc_no == tc
                    ).first()
                if not existing_client:
                    existing_client = db.query(models.Client).filter(
                        models.Client.name.ilike(name.strip())
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
        if "tracking_no" in str(getattr(e, "orig", e)):
            logger.error(f"Add Case Error: tracking_no çakışması — {data.get('tracking_no')}")
            # Telemetri (Faz 6.3): öneri mantığı hâlâ dolu numara üretiyorsa
            # SharePoint'teki teknik loglardan görülebilsin (ERROR → anlık sync)
            from managers.log_manager import TechnicalLogger
            TechnicalLogger.log(
                "ERROR",
                "[TRACKING_NO_COLLISION] Önerilen ofis numarası zaten kayıtlı",
                details={"tracking_no": data.get("tracking_no")},
            )
            return {"error": "duplicate_tracking_no"}
        logger.error(f"Add Case Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Add Case Error: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def update_case_tracking(case_id: int, data: dict, changed_by: str, source: str = "MANUAL", tenant_id: str = None) -> bool:
    """Dava takip bilgilerini günceller ve aşama değişmişse CaseStageLog kaydı ekler."""
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

        tracking_fields = [
            "case_stage",
            "dosya_son_durumu",
            # Dosya durumu
            "status",
            # Yerel Karar
            "karar_tarihi", "karar_turu", "karar_lehine",
            "karar_no", "karar_teblig_tarihi", "karar_aciklama",
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
        for field in tracking_fields:
            if field in data and data[field] is not None:
                setattr(case, field, data[field])

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
