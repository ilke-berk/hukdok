import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from dependencies import get_current_user
from schemas import ConfigItem, EmailItem, DeleteRequest, ReorderRequest
from managers.config_manager import DynamicConfig
from managers.admin_manager import (
    get_lawyers, get_statuses, get_doctypes, get_email_recipients, get_case_subjects,
    add_lawyer, delete_lawyer,
    add_status, delete_status,
    add_doctype, delete_doctype,
    add_email_recipient, delete_email_recipient,
    add_case_subject, delete_case_subject,
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
