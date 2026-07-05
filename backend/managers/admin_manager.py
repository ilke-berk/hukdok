"""Geriye dönük uyumluluk katmanı — YENİ KOD BURADAN IMPORT ETMESİN.

Eski tanrı-modül dört odaklı modüle bölündü:
  - managers/reference_lists.py  → referans listeleri (generic CRUD + LIST_REGISTRY)
  - managers/lawyer_resolver.py  → avukat adı normalize/çözümleme motoru
  - managers/case_manager.py     → dava CRUD ve takip
  - managers/client_manager.py   → müvekkil yazma işlemleri
  - managers/seed_data.py        → başlangıç (seed) verileri

Bu modül yalnızca eski import yollarını (`from managers.admin_manager import X`)
kırmamak için mevcut. Yeni kodda doğrudan ilgili modülü import edin.
"""
from managers.reference_lists import (  # noqa: F401
    LIST_REGISTRY, get_items, add_item, delete_item, reorder_list, refresh_cache,
    get_lawyers, add_lawyer, update_lawyer, delete_lawyer,
    get_statuses, add_status, delete_status,
    get_doctypes, add_doctype, delete_doctype,
    get_case_subjects, add_case_subject, delete_case_subject,
    get_email_recipients, add_email_recipient, delete_email_recipient,
    get_file_types, add_file_type, delete_file_type,
    get_court_types, add_court_type, delete_court_type,
    get_party_roles, add_party_role, delete_party_role,
    get_bureau_types, add_bureau_type, delete_bureau_type,
    get_cities, add_city, delete_city,
    get_specialties, add_specialty, delete_specialty,
    get_client_categories, add_client_category, delete_client_category,
    get_file_statuses, add_file_status, delete_file_status,
)
from managers.lawyer_resolver import (  # noqa: F401
    resolve_lawyer, resolve_lawyers_field, canonicalize_lawyers,
    _norm_name, _name_tokens, _split_persons,
)
from managers.case_manager import (  # noqa: F401
    get_case, get_cases, get_case_stats, add_case, update_case, search_cases,
    update_case_tracking, get_case_stage_log,
    _apply_tenant_filter, _lawyer_filter_case_ids,
)
from managers.client_manager import add_client  # noqa: F401
from managers.seed_data import seed_all_lists  # noqa: F401
