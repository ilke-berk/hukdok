import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from dependencies import get_current_user
from schemas import ConfigItem, EmailItem, DeleteRequest, ReorderRequest, CourtTypeItem, PartyRoleItem
from managers.config_manager import DynamicConfig
from managers.admin_manager import (
    get_lawyers, get_statuses, get_doctypes, get_email_recipients, get_case_subjects,
    add_lawyer, delete_lawyer,
    add_status, delete_status,
    add_doctype, delete_doctype,
    add_email_recipient, delete_email_recipient,
    add_case_subject, delete_case_subject,
    get_file_types, add_file_type, delete_file_type,
    get_court_types, add_court_type, delete_court_type,
    get_party_roles, add_party_role, delete_party_role,
    get_bureau_types, add_bureau_type, delete_bureau_type,
    get_cities, add_city, delete_city,
    get_specialties, add_specialty, delete_specialty,
    get_client_categories, add_client_category, delete_client_category,
    seed_all_lists,
    reorder_list,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/config/lawyers")
@router.get("/api/config/lawyers")
def get_lawyers_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    lawyers = config.get_lawyers()
    if not lawyers:
        lawyers = get_lawyers()
    return lawyers


@router.get("/config/statuses")
@router.get("/api/config/statuses")
def get_statuses_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    statuses = config.get_statuses()
    if not statuses:
        statuses = get_statuses()
    return statuses


@router.get("/config/doctypes")
@router.get("/api/config/doctypes")
def get_doctypes_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    doctypes = config.get_doctypes()
    if not doctypes:
        doctypes = get_doctypes()
    return doctypes


@router.get("/config/case_subjects")
@router.get("/api/config/case_subjects")
def get_case_subjects_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    subjects = config.get_case_subjects()
    if not subjects:
        subjects = get_case_subjects()
    return subjects


@router.get("/config/email_recipients")
@router.get("/api/config/email_recipients")
def get_email_recipients_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    data = config.get_email_recipients()
    return JSONResponse(content=data, headers={"Content-Type": "application/json; charset=utf-8"})


@router.post("/api/config/lawyers")
def api_add_lawyer(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_lawyer(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add lawyer")
    return {"status": "success", "message": "Lawyer added"}


@router.delete("/api/config/lawyers/{code}")
def api_delete_lawyer(code: str, user: dict = Depends(get_current_user)):
    success = delete_lawyer(code)
    if not success:
        raise HTTPException(status_code=404, detail="Lawyer not found or failed to delete")
    return {"status": "success", "message": "Lawyer deleted"}


@router.post("/api/config/statuses")
def api_add_status(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_status(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add status")
    return {"status": "success", "message": "Status added"}


@router.delete("/api/config/statuses/{code}")
def api_delete_status(code: str, user: dict = Depends(get_current_user)):
    success = delete_status(code)
    if not success:
        raise HTTPException(status_code=404, detail="Status not found or failed to delete")
    return {"status": "success", "message": "Status deleted"}


@router.post("/api/config/doctypes")
def api_add_doctype(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_doctype(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add doctype")
    return {"status": "success", "message": "Doctype added"}


@router.delete("/api/config/doctypes/{code}")
def api_delete_doctype(code: str, user: dict = Depends(get_current_user)):
    success = delete_doctype(code)
    if not success:
        raise HTTPException(status_code=404, detail="Doctype not found or failed to delete")
    return {"status": "success", "message": "Doctype deleted"}


@router.post("/api/config/email_recipients")
def api_add_email(item: EmailItem, user: dict = Depends(get_current_user)):
    success = add_email_recipient(item.name, item.email, item.description)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add email (maybe duplicate?)")
    return {"status": "success", "message": "Email recipient added"}


@router.delete("/api/config/email_recipients")
def api_delete_email(request: DeleteRequest, user: dict = Depends(get_current_user)):
    if not request.email:
        raise HTTPException(status_code=400, detail="Email required")
    success = delete_email_recipient(request.email)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"status": "success", "message": "Email deleted"}


@router.post("/api/config/case_subjects")
def api_add_case_subject(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_case_subject(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add case subject")
    return {"status": "success", "message": "Case subject added"}


@router.delete("/api/config/case_subjects/{code}")
def api_delete_case_subject(code: str, user: dict = Depends(get_current_user)):
    success = delete_case_subject(code)
    if not success:
        raise HTTPException(status_code=404, detail="Case subject not found or failed to delete")
    return {"status": "success", "message": "Case subject deleted"}


@router.post("/api/config/reorder")
def api_reorder_list(request: ReorderRequest, user: dict = Depends(get_current_user)):
    success = reorder_list(request.type, request.ordered_ids)
    if not success:
        raise HTTPException(status_code=500, detail="Reorder failed")
    return {"status": "success", "message": "List reordered"}


# ─── FILE TYPES ───────────────────────────────────────────────────────────────

@router.get("/api/config/file_types")
def api_get_file_types(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_file_types()
    if not data:
        data = get_file_types()
    return data

@router.post("/api/config/file_types")
def api_add_file_type(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_file_type(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add file type")
    return {"status": "success"}

@router.delete("/api/config/file_types/{code}")
def api_delete_file_type(code: str, user: dict = Depends(get_current_user)):
    success = delete_file_type(code)
    if not success:
        raise HTTPException(status_code=404, detail="File type not found")
    return {"status": "success"}


# ─── COURT TYPES ──────────────────────────────────────────────────────────────

@router.get("/api/config/court_types")
def api_get_court_types(parent_code: str = None, user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_court_types()
    if not data:
        data = get_court_types()
    if parent_code:
        data = [d for d in data if d.get("parent_code") == parent_code]
    return data

@router.post("/api/config/court_types")
def api_add_court_type(item: CourtTypeItem, user: dict = Depends(get_current_user)):
    success = add_court_type(item.code, item.name, item.parent_code)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add court type")
    return {"status": "success"}

@router.delete("/api/config/court_types/{code}")
def api_delete_court_type(code: str, user: dict = Depends(get_current_user)):
    success = delete_court_type(code)
    if not success:
        raise HTTPException(status_code=404, detail="Court type not found")
    return {"status": "success"}


# ─── PARTY ROLES ──────────────────────────────────────────────────────────────

@router.get("/api/config/party_roles")
def api_get_party_roles(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_party_roles()
    if not data:
        data = get_party_roles()
    return data

@router.post("/api/config/party_roles")
def api_add_party_role(item: PartyRoleItem, user: dict = Depends(get_current_user)):
    success = add_party_role(item.code, item.name, item.role_type)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add party role")
    return {"status": "success"}

@router.delete("/api/config/party_roles/{code}")
def api_delete_party_role(code: str, user: dict = Depends(get_current_user)):
    success = delete_party_role(code)
    if not success:
        raise HTTPException(status_code=404, detail="Party role not found")
    return {"status": "success"}


# ─── BUREAU TYPES ─────────────────────────────────────────────────────────────

@router.get("/api/config/bureau_types")
def api_get_bureau_types(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_bureau_types()
    if not data:
        data = get_bureau_types()
    return data

@router.post("/api/config/bureau_types")
def api_add_bureau_type(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_bureau_type(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add bureau type")
    return {"status": "success"}

@router.delete("/api/config/bureau_types/{code}")
def api_delete_bureau_type(code: str, user: dict = Depends(get_current_user)):
    success = delete_bureau_type(code)
    if not success:
        raise HTTPException(status_code=404, detail="Bureau type not found")
    return {"status": "success"}


# ─── CITIES ───────────────────────────────────────────────────────────────────

@router.get("/api/config/cities")
def api_get_cities(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_cities()
    if not data:
        data = get_cities()
    return data

@router.post("/api/config/cities")
def api_add_city(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_city(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add city")
    return {"status": "success"}

@router.delete("/api/config/cities/{code}")
def api_delete_city(code: str, user: dict = Depends(get_current_user)):
    success = delete_city(code)
    if not success:
        raise HTTPException(status_code=404, detail="City not found")
    return {"status": "success"}


# ─── SPECIALTIES ──────────────────────────────────────────────────────────────

@router.get("/api/config/specialties")
def api_get_specialties(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_specialties()
    if not data:
        data = get_specialties()
    return data

@router.post("/api/config/specialties")
def api_add_specialty(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_specialty(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add specialty")
    return {"status": "success"}

@router.delete("/api/config/specialties/{code}")
def api_delete_specialty(code: str, user: dict = Depends(get_current_user)):
    success = delete_specialty(code)
    if not success:
        raise HTTPException(status_code=404, detail="Specialty not found")
    return {"status": "success"}


# ─── CLIENT CATEGORIES ────────────────────────────────────────────────────────

@router.get("/api/config/client_categories")
def api_get_client_categories(user: dict = Depends(get_current_user)):
    from managers.config_manager import DynamicConfig
    config = DynamicConfig.get_instance()
    data = config.get_client_categories()
    if not data:
        data = get_client_categories()
    return data

@router.post("/api/config/client_categories")
def api_add_client_category(item: ConfigItem, user: dict = Depends(get_current_user)):
    success = add_client_category(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add client category")
    return {"status": "success"}

@router.delete("/api/config/client_categories/{code}")
def api_delete_client_category(code: str, user: dict = Depends(get_current_user)):
    success = delete_client_category(code)
    if not success:
        raise HTTPException(status_code=404, detail="Client category not found")
    return {"status": "success"}


# ─── SEED ─────────────────────────────────────────────────────────────────────

@router.post("/api/config/seed")
def api_seed_all(user: dict = Depends(get_current_user)):
    # Ensure new tables exist before seeding
    try:
        from database import Base, engine
        import models  # noqa — registers models in metadata
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"create_all during seed: {e}")
    seed_all_lists()
    return {"status": "success", "message": "Seed tamamlandı"}
