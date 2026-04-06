from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class ContactType(str, Enum):
    CLIENT = "Client"
    OTHER = "Other"


class ConfigItem(BaseModel):
    code: str
    name: str


class EmailItem(BaseModel):
    name: str
    email: str
    description: Optional[str] = ""


class DeleteRequest(BaseModel):
    code: Optional[str] = None
    email: Optional[str] = None


class ReorderRequest(BaseModel):
    type: str  # lawyers, statuses, doctypes, emails
    ordered_ids: List[str]


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
    merci_no: Optional[str] = None
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
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []


class CaseListRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    merci_no: Optional[str] = None
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
    created_at: datetime
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []

    model_config = ConfigDict(from_attributes=True)


class CaseRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    merci_no: Optional[str] = None
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
    created_at: datetime
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []
    history: List[Dict[str, Any]] = []
    documents: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)
