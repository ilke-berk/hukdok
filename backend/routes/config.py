"""Referans listelerinin (avukat, statü, belge türü, şehir, taraf rolü…) yönetim API'si.

`/api/config/*` route'ları; `api.py` include_router ile bağlanır. Okuma
`get_current_user`, yazma `require_admin` (ADMIN_EMAILS env) ister — `require_admin`
buradan `routes/activity.py` tarafından da import edilir. DB işleri
`managers/reference_lists`'te, süreç-içi kopya `managers/config_manager.DynamicConfig`'te.
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from dependencies import get_current_user
from schemas import (
    ConfigItem, EmailItem, DeleteRequest, ReorderRequest, RenameRequest,
    CourtTypeItem, PartyRoleItem, LawyerUpdateItem, ListUpdateRequest, ListDeleteRequest,
)
from managers.config_manager import DynamicConfig
from managers.seed_data import seed_all_lists
from managers.reference_lists import (
    get_lawyers, get_statuses, get_doctypes, get_case_subjects,
    add_lawyer, update_lawyer, delete_lawyer,
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
    get_file_statuses, add_file_status, delete_file_status,
    get_alleged_faults, add_alleged_fault, delete_alleged_fault,
    get_appealing_parties, add_appealing_party, delete_appealing_party,
    reorder_list, rename_item, update_item, delete_item, get_usage,
    resolve_list_type, LIST_REGISTRY,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _admin_emails() -> set:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def require_admin(user: dict = Depends(get_current_user)):
    email = (user.get("preferred_username") or user.get("upn") or user.get("email") or "").lower()
    if email not in _admin_emails():
        raise HTTPException(status_code=403, detail="Yönetici yetkisi gerekli")
    return user


# ─── AUTH ─────────────────────────────────────────────────────────────────────

@router.get("/api/config/is_admin")
def api_is_admin(user: dict = Depends(get_current_user)):
    email = (user.get("preferred_username") or user.get("upn") or user.get("email") or "").lower()
    return {"is_admin": email in _admin_emails()}


# ─── ZORUNLU DAVA ALANLARI ────────────────────────────────────────────────────

@router.get("/api/config/required_case_fields")
def api_required_case_fields(user: dict = Depends(get_current_user)):
    """Dava kartı zorunlu alan listesi (tek kaynak: backend/required_fields.py)."""
    from required_fields import PARTY_TC_FIELD, REQUIRED_CASE_FIELDS
    return {"fields": REQUIRED_CASE_FIELDS, "party_rule": PARTY_TC_FIELD}


# ─── LAWYERS ──────────────────────────────────────────────────────────────────

@router.get("/api/config/lawyers")
def get_lawyers_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    lawyers = config.get_lawyers()
    if not lawyers:
        lawyers = get_lawyers()
    return lawyers


@router.post("/api/config/lawyers")
def api_add_lawyer(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_lawyer(item.code, item.name, tc_no=item.tc_no, sicil_no=item.sicil_no,
                         gorev=item.gorev, email=item.email, phone=item.phone,
                         address=item.address, city=item.city)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add lawyer")
    return {"status": "success", "message": "Lawyer added"}


@router.put("/api/config/lawyers/{code}")
def api_update_lawyer(code: str, item: LawyerUpdateItem, user: dict = Depends(require_admin)):
    success = update_lawyer(code, tc_no=item.tc_no, sicil_no=item.sicil_no,
                            gorev=item.gorev, email=item.email, phone=item.phone, address=item.address)
    if not success:
        raise HTTPException(status_code=404, detail="Lawyer not found or failed to update")
    return {"status": "success", "message": "Lawyer updated"}


@router.delete("/api/config/lawyers/{code}")
def api_delete_lawyer(code: str, user: dict = Depends(require_admin)):
    success = delete_lawyer(code)
    if not success:
        raise HTTPException(status_code=404, detail="Lawyer not found or failed to delete")
    return {"status": "success", "message": "Lawyer deleted"}


# ─── STATUSES ─────────────────────────────────────────────────────────────────

@router.get("/api/config/statuses")
def get_statuses_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    statuses = config.get_statuses()
    if not statuses:
        statuses = get_statuses()
    return statuses


@router.post("/api/config/statuses")
def api_add_status(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_status(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add status")
    return {"status": "success", "message": "Status added"}


@router.delete("/api/config/statuses/{code}")
def api_delete_status(code: str, user: dict = Depends(require_admin)):
    success = delete_status(code)
    if not success:
        raise HTTPException(status_code=404, detail="Status not found or failed to delete")
    return {"status": "success", "message": "Status deleted"}


# ─── DOCTYPES ─────────────────────────────────────────────────────────────────

@router.get("/api/config/doctypes")
def get_doctypes_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    doctypes = config.get_doctypes()
    if not doctypes:
        doctypes = get_doctypes()
    return doctypes


@router.post("/api/config/doctypes")
def api_add_doctype(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_doctype(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add doctype")
    return {"status": "success", "message": "Doctype added"}


@router.delete("/api/config/doctypes/{code}")
def api_delete_doctype(code: str, user: dict = Depends(require_admin)):
    success = delete_doctype(code)
    if not success:
        raise HTTPException(status_code=404, detail="Doctype not found or failed to delete")
    return {"status": "success", "message": "Doctype deleted"}


# ─── CASE SUBJECTS ────────────────────────────────────────────────────────────

@router.get("/api/config/case_subjects")
def get_case_subjects_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    subjects = config.get_case_subjects()
    if not subjects:
        subjects = get_case_subjects()
    return subjects


@router.post("/api/config/case_subjects")
def api_add_case_subject(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_case_subject(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add case subject")
    return {"status": "success", "message": "Case subject added"}


@router.delete("/api/config/case_subjects/{code}")
def api_delete_case_subject(code: str, user: dict = Depends(require_admin)):
    success = delete_case_subject(code)
    if not success:
        raise HTTPException(status_code=404, detail="Case subject not found or failed to delete")
    return {"status": "success", "message": "Case subject deleted"}


# ─── EMAIL RECIPIENTS ─────────────────────────────────────────────────────────

@router.get("/api/config/email_recipients")
def get_email_recipients_endpoint(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    data = config.get_email_recipients()
    return JSONResponse(content=data, headers={"Content-Type": "application/json; charset=utf-8"})


@router.post("/api/config/email_recipients")
def api_add_email(item: EmailItem, user: dict = Depends(require_admin)):
    success = add_email_recipient(item.name, item.email, item.description or "")
    if not success:
        # Faz 5-B: mükerrer kayıt artık buraya DÜŞMEZ — DuplicateItemError
        # api.py'deki handler'da 409 olur. Buraya kalan tek şey gerçek arıza.
        raise HTTPException(status_code=500, detail="E-posta alıcısı eklenemedi. Lütfen tekrar deneyin.")
    return {"status": "success", "message": "Email recipient added"}


@router.delete("/api/config/email_recipients")
def api_delete_email(request: DeleteRequest, user: dict = Depends(require_admin)):
    if not request.email:
        raise HTTPException(status_code=400, detail="Email required")
    success = delete_email_recipient(request.email)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"status": "success", "message": "Email deleted"}


# ─── RENAME / UPDATE / DELETE (tüm listeler için generic) ────────────────────

@router.post("/api/config/rename")
def api_rename_item(request: RenameRequest, user: dict = Depends(require_admin)):
    """Yalnızca adı değiştirir — /api/config/update'in eski, dar kapsamlı hâli."""
    result = rename_item(request.type, request.code, request.name)
    if result is None:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    if result is False:
        raise HTTPException(status_code=500, detail="Yeniden adlandırma başarısız")
    return {"status": "success", "updated": result["updated"]}


@router.get("/api/config/fields/{list_type}")
def api_list_fields(list_type: str, user: dict = Depends(require_admin)):
    """Listenin düzenlenebilir kolonları — arayüz düzenleme formunu buna göre kurar."""
    key = resolve_list_type(list_type)
    if not key:
        raise HTTPException(status_code=404, detail="Bilinmeyen liste")
    spec = LIST_REGISTRY[key]
    return {"type": key, "key": spec.key, "editable": list(spec.editable)}


@router.get("/api/config/export/{list_type}")
def api_export_list(list_type: str, user: dict = Depends(get_current_user)):
    """Listeyi Excel (.xlsx) olarak indirir — hukdok-<liste>-<tarih>.xlsx."""
    if not resolve_list_type(list_type):
        raise HTTPException(status_code=404, detail="Bilinmeyen liste")
    from managers.reference_list_export import build_filename, list_to_excel
    return Response(
        content=list_to_excel(list_type),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{build_filename(list_type)}.xlsx"'},
    )


@router.get("/api/config/usage")
def api_item_usage(type: str, code: str, user: dict = Depends(require_admin)):
    """Öğenin adını taşıyan dava / müvekkil / belge sayısı — silme onayı için."""
    if not resolve_list_type(type):
        raise HTTPException(status_code=404, detail="Bilinmeyen liste")
    usage = get_usage(type, code)
    if usage is None:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return usage


@router.post("/api/config/update")
def api_update_item(request: ListUpdateRequest, user: dict = Depends(require_admin)):
    """Liste öğesini düzenler; ad değiştiyse bağlı kayıtlara yayar (updated = yansıyan kayıt)."""
    if not resolve_list_type(request.type):
        raise HTTPException(status_code=404, detail="Bilinmeyen liste")
    result = update_item(request.type, request.code, request.fields)
    if result is None:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    if result is False:
        raise HTTPException(status_code=400, detail="Güncelleme başarısız — alanları kontrol edin")
    return {"status": "success", "updated": result["updated"]}


@router.post("/api/config/delete")
def api_delete_item(request: ListDeleteRequest, user: dict = Depends(require_admin)):
    """Liste öğesini siler. mode: block | clear | reassign | keep.

    Kullanımdaki öğede mode="block" 409 döner (gövdede usage ile birlikte);
    arayüz bunu "boşalt / başka değere taşı" seçimine çevirir.
    """
    if not resolve_list_type(request.type):
        raise HTTPException(status_code=404, detail="Bilinmeyen liste")
    if request.mode not in ("block", "clear", "reassign", "keep"):
        raise HTTPException(status_code=400, detail="Geçersiz silme modu")
    if request.mode == "reassign" and not request.target_code:
        raise HTTPException(status_code=400, detail="Taşıma için hedef kayıt seçin")
    result = delete_item(request.type, request.code, mode=request.mode, target=request.target_code)
    if not result:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı veya silinemedi")
    return {"status": "success", "affected": result["affected"]}


# ─── REORDER ──────────────────────────────────────────────────────────────────

@router.post("/api/config/reorder")
def api_reorder_list(request: ReorderRequest, user: dict = Depends(require_admin)):
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
def api_add_file_type(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_file_type(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add file type")
    return {"status": "success"}

@router.delete("/api/config/file_types/{code}")
def api_delete_file_type(code: str, user: dict = Depends(require_admin)):
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
def api_add_court_type(item: CourtTypeItem, user: dict = Depends(require_admin)):
    success = add_court_type(item.code, item.name, item.parent_code)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add court type")
    return {"status": "success"}

@router.delete("/api/config/court_types/{code}")
def api_delete_court_type(code: str, user: dict = Depends(require_admin)):
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
def api_add_party_role(item: PartyRoleItem, user: dict = Depends(require_admin)):
    success = add_party_role(item.code, item.name, item.role_type)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add party role")
    return {"status": "success"}

@router.delete("/api/config/party_roles/{code}")
def api_delete_party_role(code: str, user: dict = Depends(require_admin)):
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
def api_add_bureau_type(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_bureau_type(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add bureau type")
    return {"status": "success"}

@router.delete("/api/config/bureau_types/{code}")
def api_delete_bureau_type(code: str, user: dict = Depends(require_admin)):
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
def api_add_city(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_city(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add city")
    return {"status": "success"}

@router.delete("/api/config/cities/{code}")
def api_delete_city(code: str, user: dict = Depends(require_admin)):
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
def api_add_specialty(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_specialty(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add specialty")
    return {"status": "success"}

@router.delete("/api/config/specialties/{code}")
def api_delete_specialty(code: str, user: dict = Depends(require_admin)):
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
def api_add_client_category(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_client_category(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add client category")
    return {"status": "success"}

@router.delete("/api/config/client_categories/{code}")
def api_delete_client_category(code: str, user: dict = Depends(require_admin)):
    success = delete_client_category(code)
    if not success:
        raise HTTPException(status_code=404, detail="Client category not found")
    return {"status": "success"}


# ─── FILE STATUSES ────────────────────────────────────────────────────────────

@router.get("/api/config/file_statuses")
def api_get_file_statuses(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    data = config.get_file_statuses()
    if not data:
        data = get_file_statuses()
    return data

@router.post("/api/config/file_statuses")
def api_add_file_status(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_file_status(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add file status")
    return {"status": "success"}

@router.delete("/api/config/file_statuses/{code}")
def api_delete_file_status(code: str, user: dict = Depends(require_admin)):
    success = delete_file_status(code)
    if not success:
        raise HTTPException(status_code=404, detail="File status not found")
    return {"status": "success"}


# ─── ALLEGED FAULTS / APPEALING PARTIES (FAZ F kapalı listeleri, G044) ───────
#
# Dava kartındaki `iddia_edilen_kusur` ve `istinaf_basvuran_taraf` alanları
# serbest metin DEĞİL bu listelerden seçilir; arayüz değerleri buradan okur
# (frontend'de sabit liste tutulmaz — G048 kriteri).

@router.get("/api/config/alleged_faults")
def api_get_alleged_faults(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    data = config.get_alleged_faults()
    if not data:
        data = get_alleged_faults()
    return data


@router.post("/api/config/alleged_faults")
def api_add_alleged_fault(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_alleged_fault(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add alleged fault")
    return {"status": "success"}


@router.delete("/api/config/alleged_faults/{code}")
def api_delete_alleged_fault(code: str, user: dict = Depends(require_admin)):
    success = delete_alleged_fault(code)
    if not success:
        raise HTTPException(status_code=404, detail="Alleged fault not found")
    return {"status": "success"}


@router.get("/api/config/appealing_parties")
def api_get_appealing_parties(user: dict = Depends(get_current_user)):
    config = DynamicConfig.get_instance()
    data = config.get_appealing_parties()
    if not data:
        data = get_appealing_parties()
    return data


@router.post("/api/config/appealing_parties")
def api_add_appealing_party(item: ConfigItem, user: dict = Depends(require_admin)):
    success = add_appealing_party(item.code, item.name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add appealing party")
    return {"status": "success"}


@router.delete("/api/config/appealing_parties/{code}")
def api_delete_appealing_party(code: str, user: dict = Depends(require_admin)):
    success = delete_appealing_party(code)
    if not success:
        raise HTTPException(status_code=404, detail="Appealing party not found")
    return {"status": "success"}


# ─── SEED ─────────────────────────────────────────────────────────────────────

@router.post("/api/config/seed")
def api_seed_all(user: dict = Depends(require_admin)):
    try:
        from database import Base, engine
        import models  # noqa — registers models in metadata
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"create_all during seed: {e}")
    seed_all_lists()
    return {"status": "success", "message": "Seed tamamlandı"}
