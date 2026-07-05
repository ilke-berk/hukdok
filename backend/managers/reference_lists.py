"""Referans listeleri için generic CRUD katmanı.

13 liste varlığı (avukat, durum, belge türü, …) aynı get/add/delete/reorder/
refresh davranışını paylaşır. Varlık başına kopyalanan üçlüler yerine tek
LIST_REGISTRY sözlüğü + generic fonksiyonlar kullanılır; route'ların beklediği
isimli sarmalayıcılar (get_lawyers, add_status, …) altta tanımlıdır.
"""
import logging
from dataclasses import dataclass

from database import SessionLocal
import models
from managers.config_manager import DynamicConfig

logger = logging.getLogger("AdminManager")


@dataclass(frozen=True)
class ListSpec:
    model: type
    fields: tuple          # serialize edilen kolonlar
    setter: str            # DynamicConfig üzerindeki setter adı
    key: str = "code"      # add/delete/reorder kimlik kolonu
    order_by: tuple = ("sequence",)


LIST_REGISTRY = {
    "lawyers":           ListSpec(models.Lawyer, ("code", "name", "tc_no", "sicil_no", "gorev", "email", "phone", "address"), "set_lawyers"),
    "statuses":          ListSpec(models.Status, ("code", "name"), "set_statuses"),
    "doctypes":          ListSpec(models.DocType, ("code", "name"), "set_doctypes"),
    "case_subjects":     ListSpec(models.CaseSubject, ("code", "name"), "set_case_subjects"),
    "emails":            ListSpec(models.EmailRecipient, ("name", "email", "description"), "set_email_recipients", key="email"),
    "file_types":        ListSpec(models.FileType, ("code", "name"), "set_file_types"),
    "court_types":       ListSpec(models.CourtType, ("code", "name", "parent_code"), "set_court_types", order_by=("parent_code", "sequence")),
    "party_roles":       ListSpec(models.PartyRole, ("code", "name", "role_type"), "set_party_roles"),
    "bureau_types":      ListSpec(models.BureauType, ("code", "name"), "set_bureau_types"),
    "cities":            ListSpec(models.City, ("code", "name"), "set_cities"),
    "specialties":       ListSpec(models.Specialty, ("code", "name"), "set_specialties"),
    "client_categories": ListSpec(models.ClientCategory, ("code", "name"), "set_client_categories"),
    "file_statuses":     ListSpec(models.FileStatus, ("code", "name"), "set_file_statuses"),
}

# refresh_cache("email_recipients") gibi eski çağrılar için takma adlar
_ALIASES = {"email_recipients": "emails"}


def _spec(list_type: str):
    return LIST_REGISTRY.get(_ALIASES.get(list_type, list_type))


# ─── GENERIC CRUD ────────────────────────────────────────────────────────────

def get_items(list_type: str, extra_filter=None):
    """Aktif kayıtları sıra numarasına göre listeler ve dict'e serialize eder."""
    spec = _spec(list_type)
    if not spec:
        return []
    db = None
    try:
        db = SessionLocal()
        q = db.query(spec.model).filter(spec.model.active == True)
        if extra_filter is not None:
            q = q.filter(extra_filter)
        items = q.order_by(*(getattr(spec.model, col).asc() for col in spec.order_by)).all()
        return [{f: getattr(i, f) for f in spec.fields} for i in items]
    except Exception as e:
        logger.error(f"Error fetching {list_type}: {e}")
        return []
    finally:
        if db is not None:
            db.close()


def add_item(list_type: str, **fields):
    spec = _spec(list_type)
    if not spec:
        return False
    db = None
    try:
        db = SessionLocal()
        db.add(spec.model(active=True, **fields))
        db.commit()
        refresh_cache(list_type)
        return True
    except Exception as e:
        logger.error(f"Add {list_type} Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def delete_item(list_type: str, identifier: str):
    spec = _spec(list_type)
    if not spec:
        return False
    db = SessionLocal()
    try:
        key_col = getattr(spec.model, spec.key)
        item = db.query(spec.model).filter(key_col == identifier).first()
        if item:
            db.delete(item)
            db.commit()
            refresh_cache(list_type)
            return True
        return False
    finally:
        db.close()


def reorder_list(list_type: str, ordered_ids: list):
    spec = _spec(list_type)
    if not spec:
        return False
    db = None
    try:
        db = SessionLocal()
        key_col = getattr(spec.model, spec.key)
        for idx, identifier in enumerate(ordered_ids):
            item = db.query(spec.model).filter(key_col == identifier).first()
            if item:
                item.sequence = idx
        db.commit()
        refresh_cache(list_type)
        return True
    except Exception as e:
        logger.error(f"Reorder Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def refresh_cache(list_type: str):
    """DynamicConfig singleton'ını restart gerektirmeden günceller."""
    key = _ALIASES.get(list_type, list_type)
    spec = LIST_REGISTRY.get(key)
    if not spec:
        return
    config = DynamicConfig.get_instance()
    getattr(config, spec.setter)(get_items(key))


# ─── İSİMLİ SARMALAYICILAR (route'ların import ettiği API) ───────────────────

def get_lawyers():           return get_items("lawyers")
def get_statuses():          return get_items("statuses")
def get_doctypes():          return get_items("doctypes")
def get_case_subjects():     return get_items("case_subjects")
def get_email_recipients():  return get_items("emails")
def get_file_types():        return get_items("file_types")
def get_party_roles():       return get_items("party_roles")
def get_bureau_types():      return get_items("bureau_types")
def get_cities():            return get_items("cities")
def get_specialties():       return get_items("specialties")
def get_client_categories(): return get_items("client_categories")
def get_file_statuses():     return get_items("file_statuses")


def get_court_types(parent_code: str = None):
    extra = models.CourtType.parent_code == parent_code if parent_code else None
    return get_items("court_types", extra_filter=extra)


def add_lawyer(code: str, name: str, tc_no: str = None, sicil_no: str = None,
               gorev: str = None, email: str = None, phone: str = None, address: str = None):
    return add_item("lawyers", code=code, name=name,
                    tc_no=tc_no or None, sicil_no=sicil_no or None,
                    gorev=gorev or None, email=email or None,
                    phone=phone or None, address=address or None)


def update_lawyer(code: str, tc_no: str = None, sicil_no: str = None,
                  gorev: str = None, email: str = None, phone: str = None, address: str = None):
    """Updates lawyer fields."""
    db = None
    try:
        db = SessionLocal()
        item = db.query(models.Lawyer).filter(models.Lawyer.code == code).first()
        if not item:
            return False
        for field, value in [("tc_no", tc_no), ("sicil_no", sicil_no), ("gorev", gorev),
                             ("email", email), ("phone", phone), ("address", address)]:
            if value is not None:
                setattr(item, field, value or None)
        db.commit()
        refresh_cache("lawyers")
        return True
    except Exception as e:
        logger.error(f"Update Lawyer Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def add_status(code: str, name: str):           return add_item("statuses", code=code, name=name)
def add_doctype(code: str, name: str):          return add_item("doctypes", code=code, name=name)
def add_case_subject(code: str, name: str):     return add_item("case_subjects", code=code, name=name)
def add_file_type(code: str, name: str):        return add_item("file_types", code=code, name=name)
def add_bureau_type(code: str, name: str):      return add_item("bureau_types", code=code, name=name)
def add_city(code: str, name: str):             return add_item("cities", code=code, name=name)
def add_specialty(code: str, name: str):        return add_item("specialties", code=code, name=name)
def add_client_category(code: str, name: str):  return add_item("client_categories", code=code, name=name)
def add_file_status(code: str, name: str):      return add_item("file_statuses", code=code, name=name)


def add_court_type(code: str, name: str, parent_code: str):
    return add_item("court_types", code=code, name=name, parent_code=parent_code)


def add_party_role(code: str, name: str, role_type: str = "MAIN"):
    return add_item("party_roles", code=code, name=name, role_type=role_type)


def add_email_recipient(name: str, email: str, description: str = ""):
    db = None
    try:
        db = SessionLocal()
        existing = db.query(models.EmailRecipient).filter(models.EmailRecipient.email == email).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.name = name
                existing.description = description
                db.commit()
                refresh_cache("emails")
                return True
            return False

        from sqlalchemy import func
        max_seq = db.query(func.max(models.EmailRecipient.sequence)).scalar()
        new_seq = (max_seq if max_seq is not None else -1) + 1

        new_item = models.EmailRecipient(name=name, email=email, description=description, active=True, sequence=new_seq)
        db.add(new_item)
        db.commit()
        refresh_cache("emails")
        return True
    except Exception as e:
        logger.error(f"Add Email Error: {e}")
        return False
    finally:
        if db is not None:
            db.close()


def delete_lawyer(code: str):           return delete_item("lawyers", code)
def delete_status(code: str):           return delete_item("statuses", code)
def delete_doctype(code: str):          return delete_item("doctypes", code)
def delete_case_subject(code: str):     return delete_item("case_subjects", code)
def delete_email_recipient(email: str): return delete_item("emails", email)
def delete_file_type(code: str):        return delete_item("file_types", code)
def delete_court_type(code: str):       return delete_item("court_types", code)
def delete_party_role(code: str):       return delete_item("party_roles", code)
def delete_bureau_type(code: str):      return delete_item("bureau_types", code)
def delete_city(code: str):             return delete_item("cities", code)
def delete_specialty(code: str):        return delete_item("specialties", code)
def delete_client_category(code: str):  return delete_item("client_categories", code)
def delete_file_status(code: str):      return delete_item("file_statuses", code)
