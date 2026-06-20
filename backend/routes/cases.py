import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from auth_helpers import (
    get_tenant_owned_case,
    get_tenant_owned_hearing,
    tenant_filter_clause,
)
from dependencies import get_current_user, get_current_tenant
from schemas import (
    CaseCreate, CaseListRead, CaseRelationCreate, RelatedCaseSummary, RelatedCasesResponse,
    CaseTrackingUpdate, CaseStageLogRead,
)
from database import SessionLocal
from managers.admin_manager import (
    add_case, get_case, get_cases, get_case_stats, update_case, search_cases,
    update_case_tracking, get_case_stage_log,
)
import models


class HearingDateCreate(BaseModel):
    hearing_date: date
    hearing_time: Optional[str] = None
    lawyer_name: Optional[str] = None
    extracted_from_doc: Optional[str] = None
    note: Optional[str] = None


class CalendarEventCreate(BaseModel):
    title: str
    event_date: date
    event_time: Optional[str] = None

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/cases")
def api_add_case(case_data: CaseCreate, tenant_id: str = Depends(get_current_tenant)):
    # Hanyaloğlu Acar + LexisBio ortak çalıştığı için yeni davalar paylaşımlı (tenant_id=NULL).
    # tenant_id Depends'i token doğrulaması için kalıyor ama damgalamada kullanılmıyor.
    result = add_case(case_data.model_dump())
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save case")
    return {"status": "success", "message": "Case saved", **result}


@router.get("/api/cases/stats")
def api_get_case_stats(tenant_id: str = Depends(get_current_tenant)):
    return get_case_stats(tenant_id=tenant_id)


@router.get("/api/cases", response_model=List[CaseListRead])
def get_cases_api(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    lawyer: Optional[str] = None,
    q: Optional[str] = None,
    exact: bool = False,
    tenant_id: str = Depends(get_current_tenant),
):
    return get_cases(limit=limit, offset=offset, status=status, lawyer=lawyer, q=q, exact=exact, tenant_id=tenant_id)


@router.get("/api/cases/client-sequence")
def get_client_case_sequence(client_name: str, tenant_id: str = Depends(get_current_tenant)):
    db = SessionLocal()
    try:
        if not client_name:
            return {"sequence": 1}

        clean_name = client_name.strip().upper()
        for suffix in [" DR.", " DR"]:
            if clean_name.endswith(suffix):
                clean_name = clean_name[: -len(suffix)].strip()
                break

        query_pattern = f"{clean_name}%"
        count = (
            db.query(func.count(func.distinct(models.CaseParty.case_id)))
            .join(models.Case, models.CaseParty.case_id == models.Case.id)
            .filter(models.CaseParty.party_type == "CLIENT")
            .filter(models.CaseParty.name.ilike(query_pattern))
            .filter(tenant_filter_clause(models.Case, tenant_id))
            .scalar()
        )
        return {"sequence": (count or 0) + 1}
    except Exception as e:
        logger.error(f"Error getting client sequence: {e}")
        return {"sequence": 1}
    finally:
        db.close()


@router.get("/api/cases/search")
def api_search_cases(q: str, exact: bool = False, active_only: bool = False, tenant_id: str = Depends(get_current_tenant)):
    return search_cases(q, exact=exact, active_only=active_only, tenant_id=tenant_id)


@router.get("/api/cases/{case_id}")
def api_get_case(case_id: int, tenant_id: str = Depends(get_current_tenant)):
    case = get_case(case_id, tenant_id=tenant_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/api/cases/{case_id}/client-notice-target")
def get_case_client_notice_target(
    case_id: int,
    belge_turu_kodu: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant),
):
    """Müvekkil bilgilendirme maili için hedef bilgisini döndürür.

    Müvekkil bilgilendirme metni müvekkile DEĞİL, davanın sorumlu avukatına
    "[Müvekkil Bilgilendirme]" konu başlığıyla gönderilir (avukat metni gözden
    geçirip müvekkile iletir). Bu endpoint modalda göstermek için:
      - sorumlu avukatı (lawyer: {name, email})
      - bilgilendirme metninde hitap edilecek müvekkil adını (client_name)
      - belge türü uygunluğunu (eligible)
    döndürür.
    """
    from email_sender import should_notify_client
    from managers.config_manager import DynamicConfig

    db = SessionLocal()
    try:
        case = get_tenant_owned_case(db, case_id, tenant_id)
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        # Müvekkil ad(lar)ı — bilgilendirme metninin hitabı için.
        client_names = [
            (p.client.name if p.client else None) or p.name
            for p in (case.parties or [])
            if p.party_type == "CLIENT" and ((p.client.name if p.client else None) or p.name)
        ]
        if len(client_names) > 1:
            client_name = ", ".join(client_names[:-1]) + " ve " + client_names[-1]
        elif client_names:
            client_name = client_names[0]
        else:
            client_name = None

        # Sorumlu avukat → email (lawyers config'inden).
        lawyer = None
        responsible_name = case.responsible_lawyer_name
        if responsible_name:
            try:
                for l in DynamicConfig.get_instance().get_lawyers():
                    if l.get("name") == responsible_name:
                        email = (l.get("email") or "").strip()
                        lawyer = {"name": responsible_name, "email": email}
                        break
            except Exception as e:
                logger.warning(f"Sorumlu avukat email lookup hatası: {e}")
            if lawyer is None:
                # Avukat lawyers config'inde bulunamadı; en azından adı döndür.
                lawyer = {"name": responsible_name, "email": ""}

        return {
            "eligible": should_notify_client(belge_turu_kodu),
            "lawyer": lawyer,
            "client_name": client_name,
        }
    finally:
        db.close()


@router.put("/api/cases/{case_id}")
def api_update_case(case_id: int, case_data: CaseCreate, tenant_id: str = Depends(get_current_tenant)):
    success = update_case(case_id, case_data.model_dump(), tenant_id=tenant_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update case")
    return {"status": "success", "message": "Case updated"}


@router.delete("/api/cases/{case_id}")
def api_delete_case(case_id: int, tenant_id: str = Depends(get_current_tenant)):
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        query = db.query(models.Case).filter(models.Case.id == case_id)
        query = query.filter(or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None)))
        case = query.first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        db.delete(case)
        db.commit()
        return {"status": "success", "message": "Case deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Dava silme hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Dava silinemedi. Lütfen tekrar deneyin.")
    finally:
        db.close()


def _case_to_summary(case, relation_id, relation_type, match_reason, score, is_manual, note) -> RelatedCaseSummary:
    """ORM Case nesnesini RelatedCaseSummary'e dönüştür."""
    parties = [
        {"name": p.name, "role": p.role}
        for p in (case.parties or [])[:3]
    ]
    return RelatedCaseSummary(
        id=case.id,
        tracking_no=case.tracking_no,
        esas_no=case.esas_no,
        court=case.court,
        status=case.status,
        file_type=case.file_type,
        parties=parties,
        relation_id=relation_id,
        relation_type=relation_type,
        match_reason=match_reason,
        confidence_score=score,
        is_manual=is_manual,
        note=note,
    )


@router.get("/api/cases/{case_id}/relations", response_model=RelatedCasesResponse)
def get_case_relations(
    case_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    """Manuel olarak bağlanan ilişkili davaları getirir."""
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        case = db.query(models.Case).filter(
            models.Case.id == case_id,
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        ).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        manual_rows = db.query(models.CaseRelation).filter(
            (models.CaseRelation.source_case_id == case_id) |
            (models.CaseRelation.target_case_id == case_id)
        ).all()

        manual_list = []
        for row in manual_rows:
            other_id = row.target_case_id if row.source_case_id == case_id else row.source_case_id
            other = (
                db.query(models.Case)
                .options(selectinload(models.Case.parties))
                .filter(models.Case.id == other_id)
                .first()
            )
            if other:
                manual_list.append(_case_to_summary(
                    case=other,
                    relation_id=row.id,
                    relation_type=row.relation_type,
                    match_reason="Kullanıcı tarafından bağlandı",
                    score=None,
                    is_manual=True,
                    note=row.note,
                ))

        return RelatedCasesResponse(manual=manual_list, automatic=[])

    finally:
        db.close()


@router.post("/api/cases/{case_id}/relations", response_model=dict)
def add_case_relation(
    case_id: int,
    data: CaseRelationCreate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """İki dava arasında manuel bağlantı oluştur."""
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        if data.target_case_id == case_id:
            raise HTTPException(status_code=400, detail="Dava kendisiyle ilişkilendirilemez")

        tenant_filter = or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        source = db.query(models.Case).filter(models.Case.id == case_id, tenant_filter).first()
        target = db.query(models.Case).filter(models.Case.id == data.target_case_id, tenant_filter).first()
        if not source or not target:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        existing = db.query(models.CaseRelation).filter(
            ((models.CaseRelation.source_case_id == case_id) & (models.CaseRelation.target_case_id == data.target_case_id)) |
            ((models.CaseRelation.source_case_id == data.target_case_id) & (models.CaseRelation.target_case_id == case_id))
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Bu iki dava zaten ilişkilendirilmiş")

        relation = models.CaseRelation(
            source_case_id=case_id,
            target_case_id=data.target_case_id,
            relation_type=data.relation_type,
            note=data.note,
            created_by=user.get("name") or user.get("preferred_username"),
        )
        db.add(relation)
        db.commit()
        db.refresh(relation)
        return {"id": relation.id, "status": "created"}

    finally:
        db.close()


@router.delete("/api/cases/{case_id}/relations/{relation_id}")
def delete_case_relation(
    case_id: int,
    relation_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    """Manuel bağlantıyı sil."""
    db = SessionLocal()
    try:
        # Önce bu davaya istek sahibi tenant'ın erişip erişemediğini doğrula
        case = get_tenant_owned_case(db, case_id, tenant_id)
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        relation = db.query(models.CaseRelation).filter(
            models.CaseRelation.id == relation_id,
            (
                (models.CaseRelation.source_case_id == case_id) |
                (models.CaseRelation.target_case_id == case_id)
            )
        ).first()

        if not relation:
            raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

        db.delete(relation)
        db.commit()
        return {"status": "deleted"}

    finally:
        db.close()


@router.patch("/api/cases/{case_id}/tracking")
def api_update_case_tracking(
    case_id: int,
    data: CaseTrackingUpdate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Dava takip bilgilerini güncelle (aşama, tarihler, karar bilgileri)."""
    changed_by = user.get("name") or user.get("preferred_username") or "unknown"
    success = update_case_tracking(case_id, data.model_dump(exclude_none=False), changed_by=changed_by, tenant_id=tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dava bulunamadı veya güncelleme başarısız")
    return {"status": "success"}


@router.get("/api/cases/{case_id}/stage-log", response_model=List[CaseStageLogRead])
def api_get_case_stage_log(
    case_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    """Davanın aşama tarihçesini döner."""
    return get_case_stage_log(case_id, tenant_id=tenant_id)


@router.post("/api/cases/{case_id}/hearing-dates")
def add_hearing_date(
    case_id: int,
    data: HearingDateCreate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Duruşma zaptından çıkarılan sonraki duruşma tarihini kaydet."""
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        case = db.query(models.Case).filter(
            models.Case.id == case_id,
            or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
        ).first()
        if not case:
            raise HTTPException(status_code=404, detail="Dava bulunamadı")

        hearing = models.HearingDate(
            case_id=case_id,
            hearing_date=data.hearing_date,
            hearing_time=data.hearing_time,
            lawyer_name=data.lawyer_name or case.responsible_lawyer_name,
            extracted_from_doc=data.extracted_from_doc,
            note=data.note,
            created_by=user.get("name") or user.get("preferred_username"),
        )
        db.add(hearing)
        db.commit()
        db.refresh(hearing)
        return {
            "id": hearing.id,
            "case_id": case_id,
            "hearing_date": hearing.hearing_date.isoformat(),
            "hearing_time": hearing.hearing_time,
            "lawyer_name": hearing.lawyer_name,
        }
    finally:
        db.close()


@router.get("/api/hearing-dates")
def get_hearing_dates(
    lawyer: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant),
):
    """Tüm duruşma tarihlerini döndürür (ajanda için)."""
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        q = db.query(models.HearingDate)
        if lawyer:
            q = q.filter(models.HearingDate.lawyer_name == lawyer)
        rows = (
            q.outerjoin(models.Case, models.HearingDate.case_id == models.Case.id)
            .filter(or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None)))
            .add_columns(models.Case.esas_no, models.Case.court)
            .order_by(models.HearingDate.hearing_date)
            .all()
        )
        return [
            {
                "id": r.HearingDate.id,
                "case_id": r.HearingDate.case_id,
                "hearing_date": r.HearingDate.hearing_date.isoformat(),
                "hearing_time": r.HearingDate.hearing_time,
                "lawyer_name": r.HearingDate.lawyer_name,
                "extracted_from_doc": r.HearingDate.extracted_from_doc,
                "note": r.HearingDate.note,
                "esas_no": r.esas_no,
                "court": r.court,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.delete("/api/hearing-dates/{hearing_id}")
def delete_hearing_date(
    hearing_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    db = SessionLocal()
    try:
        row = get_tenant_owned_hearing(db, hearing_id, tenant_id)
        if not row:
            raise HTTPException(status_code=404, detail="Duruşma tarihi bulunamadı")
        db.delete(row)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


@router.post("/api/calendar-events")
def add_calendar_event(
    data: CalendarEventCreate,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant),
):
    """Takvime elle bir tarih işareti (hatırlatma) ekle."""
    title = (data.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Başlık (ne olduğu) gerekli")
    db = SessionLocal()
    try:
        event = models.CalendarEvent(
            tenant_id=None,  # ortak havuz — her iki büro da görür (paylaşımlı kayıt modeli)
            title=title,
            event_date=data.event_date,
            event_time=data.event_time,
            created_by=user.get("name") or user.get("preferred_username"),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return {
            "id": event.id,
            "title": event.title,
            "event_date": event.event_date.isoformat(),
            "event_time": event.event_time,
            "created_by": event.created_by,
        }
    finally:
        db.close()


@router.get("/api/calendar-events")
def get_calendar_events(tenant_id: str = Depends(get_current_tenant)):
    """Takvime elle eklenen tüm tarih işaretlerini döndürür."""
    db = SessionLocal()
    try:
        rows = (
            db.query(models.CalendarEvent)
            .filter(or_(models.CalendarEvent.tenant_id == tenant_id, models.CalendarEvent.tenant_id.is_(None)))
            .order_by(models.CalendarEvent.event_date)
            .all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "event_date": r.event_date.isoformat(),
                "event_time": r.event_time,
                "created_by": r.created_by,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.delete("/api/calendar-events/{event_id}")
def delete_calendar_event(
    event_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    db = SessionLocal()
    try:
        row = (
            db.query(models.CalendarEvent)
            .filter(
                models.CalendarEvent.id == event_id,
                or_(models.CalendarEvent.tenant_id == tenant_id, models.CalendarEvent.tenant_id.is_(None)),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Tarih işareti bulunamadı")
        db.delete(row)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


@router.get("/api/calendar-report")
def calendar_report(
    start: date,
    end: date,
    format: str = "pdf",
    tenant_id: str = Depends(get_current_tenant),
):
    """Tarih aralığındaki tüm işaretleri (duruşma + elle) PDF/Excel/JSON döndürür.

    Davaya bağlı işaretler için müvekkil, karşı taraf, mahkeme, esas no ve sorumlu
    avukat detayları rapora eklenir.
    """
    if end < start:
        start, end = end, start
    fmt = (format or "pdf").lower()
    db = SessionLocal()
    try:
        from report_builder import build_report_rows, rows_to_excel, rows_to_pdf
        rows = build_report_rows(db, tenant_id, start, end)

        fname = f"takvim-raporu-{start.isoformat()}_{end.isoformat()}"
        if fmt == "json":
            return {"start": start.isoformat(), "end": end.isoformat(), "count": len(rows), "rows": rows}
        if fmt in ("excel", "xlsx"):
            data = rows_to_excel(rows, start, end)
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
            )
        # default: pdf
        data = rows_to_pdf(rows, start, end)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
        )
    finally:
        db.close()


@router.get("/api/incomplete-tasks")
def get_incomplete_tasks(tenant_id: str = Depends(get_current_tenant)):
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        incomplete_cases = []
        incomplete_clients = []

        cases = (
            db.query(models.Case)
            .options(selectinload(models.Case.parties))
            .filter(
                models.Case.active == True,
                or_(models.Case.tenant_id == tenant_id, models.Case.tenant_id.is_(None))
            )
            .order_by(models.Case.created_at.desc())
            .limit(100)
            .all()
        )

        for c in cases:
            missing = []
            if not c.court:
                missing.append("Mahkeme")
            if not c.responsible_lawyer_name:
                missing.append("Avukat")
            if not c.subject:
                missing.append("Konu")

            client_parties = [p for p in c.parties if p.party_type == "CLIENT"]
            for p in client_parties:
                if not p.client_id:
                    missing.append(f"Müvekkil bağlantısı ({p.name})")

            if len(client_parties) == 0:
                missing.append("Müvekkil yok")

            if missing:
                incomplete_cases.append(
                    {
                        "id": c.id,
                        "type": "case",
                        "esas_no": c.esas_no or c.tracking_no,
                        "court": c.court or "",
                        "status": c.status,
                        "missing_fields": missing,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                )

        clients = (
            db.query(models.Client)
            .filter(models.Client.active == True)
            .filter(tenant_filter_clause(models.Client, tenant_id))
            .order_by(models.Client.updated_at.desc())
            .limit(50)
            .all()
        )

        for cl in clients:
            missing = []
            if not cl.phone and not cl.mobile_phone:
                missing.append("Telefon")
            if not cl.email:
                missing.append("E-posta")
            if not cl.tc_no:
                missing.append("TC No")

            if len(missing) >= 2:
                incomplete_clients.append(
                    {
                        "id": cl.id,
                        "type": "client",
                        "name": cl.name,
                        "client_type": cl.client_type or "Belirtilmemiş",
                        "missing_fields": missing,
                    }
                )

        return {
            "incomplete_cases": incomplete_cases[:30],
            "incomplete_clients": incomplete_clients[:20],
            "total_incomplete_cases": len(incomplete_cases),
            "total_incomplete_clients": len(incomplete_clients),
        }
    except Exception as e:
        logger.error(f"Incomplete Tasks Error: {e}")
        return {
            "incomplete_cases": [],
            "incomplete_clients": [],
            "total_incomplete_cases": 0,
            "total_incomplete_clients": 0,
        }
    finally:
        db.close()
