from enum import Enum
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class ContactType(str, Enum):
    CLIENT = "Client"
    OTHER = "Other"


class ConfigItem(BaseModel):
    code: str
    name: str
    tc_no: Optional[str] = None
    sicil_no: Optional[str] = None
    gorev: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class EmailItem(BaseModel):
    name: str
    email: str
    description: Optional[str] = ""


class DeleteRequest(BaseModel):
    code: Optional[str] = None
    email: Optional[str] = None


class ReorderRequest(BaseModel):
    type: str
    ordered_ids: List[str]

class LawyerUpdateItem(BaseModel):
    tc_no: Optional[str] = None
    sicil_no: Optional[str] = None
    gorev: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class CourtTypeItem(BaseModel):
    code: str
    name: str
    parent_code: str

class PartyRoleItem(BaseModel):
    code: str
    name: str
    role_type: str = "MAIN"


class ClientCreate(BaseModel):
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: ContactType = ContactType.CLIENT
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None


class ClientRead(BaseModel):
    id: int
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: str = "Client"
    active: bool
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: Optional[ContactType] = None
    active: Optional[bool] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CasePartyCreate(BaseModel):
    client_id: Optional[int] = None
    name: str
    role: str
    party_type: str  # "CLIENT", "COUNTER", "THIRD"
    birth_year: Optional[int] = None
    gender: Optional[str] = None


class CaseLawyerCreate(BaseModel):
    lawyer_id: Optional[int] = None
    name: str


class CaseCreate(BaseModel):
    tracking_no: str
    esas_no: Optional[str] = None
    status: str = "DERDEST"
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: Optional[float] = 0
    manevi_tazminat: Optional[float] = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    # Excel import / ek alanlar
    atama_tarihi: Optional[str] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []


class CaseListRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    status: str
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: float = 0
    manevi_tazminat: float = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    atama_tarihi: Optional[date] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []

    model_config = ConfigDict(from_attributes=True)


class CaseRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    status: str
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: float = 0
    manevi_tazminat: float = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    # Excel import / ek alanlar
    atama_tarihi: Optional[date] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    # Takip alanları
    case_stage: Optional[str] = None
    dosya_son_durumu: Optional[str] = None
    # Yerel Karar
    karar_tarihi: Optional[date] = None
    karar_turu: Optional[str] = None
    karar_lehine: Optional[str] = None
    karar_no: Optional[str] = None
    karar_teblig_tarihi: Optional[date] = None
    karar_aciklama: Optional[str] = None
    # İstinaf
    istinaf_basvuru_tarihi: Optional[date] = None
    istinaf_karar_durumu: Optional[str] = None
    istinaf_karar_tarihi: Optional[date] = None
    istinaf_mahkemesi: Optional[str] = None
    istinaf_esas_no: Optional[str] = None
    istinaf_karar_no: Optional[str] = None
    istinaf_karar_aciklama: Optional[str] = None
    istinaf_teblig_tarihi: Optional[date] = None
    # Temyiz
    temyiz_basvuru_tarihi: Optional[date] = None
    temyiz_karar_durumu: Optional[str] = None
    temyiz_karar_tarihi: Optional[date] = None
    temyiz_mahkemesi: Optional[str] = None
    temyiz_esas_no: Optional[str] = None
    temyiz_karar_no: Optional[str] = None
    temyiz_eden_durumu: Optional[str] = None
    temyiz_karar_aciklama: Optional[str] = None
    temyiz_teblig_tarihi: Optional[date] = None
    # Karar Düzeltme
    karar_duzeltme_durumu: Optional[str] = None
    karar_duzeltme_esas_no: Optional[str] = None
    karar_duzeltme_karar_no: Optional[str] = None
    karar_duzeltme_tarihi: Optional[date] = None
    karar_duzeltme_teblig_tarihi: Optional[date] = None
    karar_duzeltme_aciklama: Optional[str] = None
    yeni_esas_no: Optional[str] = None
    # Kesinleşme / İnfaz
    kesinlesme_tarihi: Optional[date] = None
    infaz_tarihi: Optional[date] = None
    created_at: datetime
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []
    history: List[Dict[str, Any]] = []
    documents: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)


class CaseTrackingUpdate(BaseModel):
    case_stage: Optional[str] = None
    dosya_son_durumu: Optional[str] = None
    # Yerel Karar
    karar_tarihi: Optional[date] = None
    karar_turu: Optional[str] = None
    karar_lehine: Optional[str] = None
    karar_no: Optional[str] = None
    karar_teblig_tarihi: Optional[date] = None
    karar_aciklama: Optional[str] = None
    # İstinaf
    istinaf_basvuru_tarihi: Optional[date] = None
    istinaf_karar_durumu: Optional[str] = None
    istinaf_karar_tarihi: Optional[date] = None
    istinaf_mahkemesi: Optional[str] = None
    istinaf_esas_no: Optional[str] = None
    istinaf_karar_no: Optional[str] = None
    istinaf_karar_aciklama: Optional[str] = None
    istinaf_teblig_tarihi: Optional[date] = None
    # Temyiz
    temyiz_basvuru_tarihi: Optional[date] = None
    temyiz_karar_durumu: Optional[str] = None
    temyiz_karar_tarihi: Optional[date] = None
    temyiz_mahkemesi: Optional[str] = None
    temyiz_esas_no: Optional[str] = None
    temyiz_karar_no: Optional[str] = None
    temyiz_eden_durumu: Optional[str] = None
    temyiz_karar_aciklama: Optional[str] = None
    temyiz_teblig_tarihi: Optional[date] = None
    # Karar Düzeltme
    karar_duzeltme_durumu: Optional[str] = None
    karar_duzeltme_esas_no: Optional[str] = None
    karar_duzeltme_karar_no: Optional[str] = None
    karar_duzeltme_tarihi: Optional[date] = None
    karar_duzeltme_teblig_tarihi: Optional[date] = None
    karar_duzeltme_aciklama: Optional[str] = None
    yeni_esas_no: Optional[str] = None
    # Kesinleşme / İnfaz
    kesinlesme_tarihi: Optional[date] = None
    infaz_tarihi: Optional[date] = None
    note: Optional[str] = None


class CaseStageLogRead(BaseModel):
    id: int
    case_id: int
    stage: str
    changed_at: datetime
    changed_by: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---- İlişkili Davalar ----

class CaseRelationCreate(BaseModel):
    target_case_id: int
    relation_type: str = "ILGILI"
    note: Optional[str] = None


class CaseRelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_case_id: int
    target_case_id: int
    relation_type: str
    note: Optional[str]
    created_by: Optional[str]
    created_at: datetime


class RelatedCaseSummary(BaseModel):
    """Hem manuel hem otomatik için ortak şema — frontend bu yapıyı bekliyor."""
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    court: Optional[str] = None
    status: str
    file_type: Optional[str] = None
    parties: List[Dict[str, str]] = []
    relation_id: Optional[int] = None
    relation_type: str
    match_reason: str
    confidence_score: Optional[int] = None
    is_manual: bool
    note: Optional[str] = None


class RelatedCasesResponse(BaseModel):
    manual: List[RelatedCaseSummary]
    automatic: List[RelatedCaseSummary]
