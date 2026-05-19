from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    tracking_no = Column(String, unique=True, index=True, nullable=False) # e.g. "2024/1234"
    esas_no = Column(String, index=True)
    status = Column(String, default="DERDEST") # "DERDEST", "DANIŞ", "MAHZEN"
    file_type = Column(String) # DOSYA_TURLERI
    sub_type = Column(String) # MAHKEME_TURLERI
    service_type = Column(String) # Algorithm Block 5
    subject = Column(String) # DAVA_KONULARI
    court = Column(String)
    opening_date = Column(Date)
    
    responsible_lawyer_name = Column(String)
    uyap_lawyer_name = Column(String)
    
    maddi_tazminat = Column(Numeric(precision=20, scale=2), default=0)
    manevi_tazminat = Column(Numeric(precision=20, scale=2), default=0)
    
    acceptance_date = Column(Date, nullable=True)  # İş Kabul Tarihi
    bureau_type = Column(String, nullable=True)  # Büro Özel Türü (DR ÖZEL, LEXİS, VEKALETSİZ TAKİP vs.)
    sub_type_extra = Column(String, nullable=True)  # Ek Alt Kırılım (RİNOPLASTİ;SEPTOPLASTİ vs.)
    
    notes = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    tenant_id = Column(String, index=True, nullable=True)  # Azure AD tenant (tid)

    # Excel import alanları (BIRLESIK_SONUC_v5)
    klasor_no_2    = Column(String(2000), nullable=True)  # Eski sistem no — gizli, aranabilir
    atama_tarihi   = Column(Date,   nullable=True)  # Atama Tarihi
    hasar_dosya_no = Column(String, nullable=True)  # Hasar Dosya Numarası
    hukuk_no       = Column(String, nullable=True)  # Hukuk Numarası

    # Takip alanları
    case_stage = Column(String(50), nullable=True)          # DERDEST | KARAR | ISTINAF | TEMYIZ | KARAR_DUZELTME | KESINLESME | INFAZ | KAPALI
    dosya_son_durumu = Column(String(100), nullable=True)   # Dosya son durumu (serbest seçim)

    # Yerel Karar
    karar_tarihi = Column(Date, nullable=True)
    karar_turu = Column(String(50), nullable=True)          # KABUL | RED | KISMI_KABUL | FERAGAT | UZLASMA | DUSME
    karar_lehine = Column(String(20), nullable=True)        # LEHINE | ALEYHINE | KISMI
    karar_no = Column(String(50), nullable=True)
    karar_teblig_tarihi = Column(Date, nullable=True)
    karar_aciklama = Column(String, nullable=True)

    # İstinaf
    istinaf_basvuru_tarihi = Column(Date, nullable=True)
    istinaf_karar_durumu = Column(String(100), nullable=True)
    istinaf_karar_tarihi = Column(Date, nullable=True)
    istinaf_mahkemesi = Column(String(200), nullable=True)
    istinaf_esas_no = Column(String(50), nullable=True)
    istinaf_karar_no = Column(String(50), nullable=True)
    istinaf_karar_aciklama = Column(String, nullable=True)
    istinaf_teblig_tarihi = Column(Date, nullable=True)

    # Temyiz
    temyiz_basvuru_tarihi = Column(Date, nullable=True)
    temyiz_karar_durumu = Column(String(100), nullable=True)
    temyiz_karar_tarihi = Column(Date, nullable=True)
    temyiz_mahkemesi = Column(String(200), nullable=True)
    temyiz_esas_no = Column(String(50), nullable=True)
    temyiz_karar_no = Column(String(50), nullable=True)
    temyiz_eden_durumu = Column(String(100), nullable=True)
    temyiz_karar_aciklama = Column(String, nullable=True)
    temyiz_teblig_tarihi = Column(Date, nullable=True)

    # Karar Düzeltme
    karar_duzeltme_durumu = Column(String(100), nullable=True)
    karar_duzeltme_esas_no = Column(String(50), nullable=True)
    karar_duzeltme_karar_no = Column(String(50), nullable=True)
    karar_duzeltme_tarihi = Column(Date, nullable=True)
    karar_duzeltme_teblig_tarihi = Column(Date, nullable=True)
    karar_duzeltme_aciklama = Column(String, nullable=True)
    yeni_esas_no = Column(String(100), nullable=True)

    # Kesinleşme / İnfaz
    kesinlesme_tarihi = Column(Date, nullable=True)
    infaz_tarihi = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

    # Relationships
    parties = relationship("CaseParty", back_populates="case", cascade="all, delete-orphan")
    history = relationship("CaseHistory", back_populates="case", cascade="all, delete-orphan")
    documents = relationship("CaseDocument", back_populates="case", cascade="all, delete-orphan")
    lawyers = relationship("CaseLawyer", back_populates="case", cascade="all, delete-orphan")
    relations_as_source = relationship("CaseRelation", foreign_keys="CaseRelation.source_case_id", cascade="all, delete-orphan")
    relations_as_target = relationship("CaseRelation", foreign_keys="CaseRelation.target_case_id", cascade="all, delete-orphan")
    stage_logs = relationship("CaseStageLog", back_populates="case", cascade="all, delete-orphan")

class CaseStageLog(Base):
    __tablename__ = "case_stage_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(50), nullable=False)
    changed_at = Column(DateTime(timezone=True), default=func.now())
    changed_by = Column(String(100), nullable=True)
    source = Column(String(20), default="MANUAL")   # "MANUAL" | "AUTO_DOCUMENT"
    note = Column(String, nullable=True)

    case = relationship("Case", back_populates="stage_logs")


class CaseRelation(Base):
    __tablename__ = "case_relations"

    id = Column(Integer, primary_key=True, index=True)
    source_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    target_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(30), nullable=False, default="ILGILI")
    # ICRA_CEZA | ICRA_HUKUK | ASIL_TEMYIZ | ASIL_YENIDEN | BIRLESEN | AYRISTIRILAN | ILGILI
    note = Column(String, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    source_case = relationship("Case", foreign_keys=[source_case_id], overlaps="relations_as_source")
    target_case = relationship("Case", foreign_keys=[target_case_id], overlaps="relations_as_target")


class CaseHistory(Base):
    __tablename__ = "case_history"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    field_name = Column(String, nullable=False) # e.g. "esas_no", "court", "status"
    old_value = Column(String)
    new_value = Column(String)
    changed_at = Column(DateTime(timezone=True), default=func.now())
    
    case = relationship("Case", back_populates="history")

class CaseParty(Base):
    __tablename__ = "case_parties"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True) # Linked if it's a registered client
    
    name = Column(String, nullable=False)
    role = Column(String, nullable=False) # "Davacı", "Davalı", etc.
    party_type = Column(String, nullable=False) # "CLIENT" (registered), "COUNTER", "THIRD"
    birth_year = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    
    case = relationship("Case", back_populates="parties")
    client = relationship("Client", back_populates="case_parties")

class CaseLawyer(Base):
    __tablename__ = "case_lawyers"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    lawyer_id = Column(Integer, ForeignKey("lawyers.id", ondelete="SET NULL"), nullable=True) # Linked if registered
    
    name = Column(String, nullable=False) # Actual name representation
    
    case = relationship("Case", back_populates="lawyers")
    lawyer = relationship("Lawyer")

class Lawyer(Base):
    __tablename__ = "lawyers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # e.g. "AGH"
    name = Column(String, nullable=False) # e.g. "Ayşe..."
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    tc_no = Column(String, nullable=True)    # T.C. Kimlik No
    sicil_no = Column(String, nullable=True) # Baro Sicil No
    gorev = Column(String, nullable=True)    # AVUKAT / DIŞ AVUKAT
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Client(Base):
    __tablename__ = "clients" # Muvekkiller

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False) # Müvekkil adı (unique değil, TC/cari_kod ile ayırt edilir)
    source_ids = Column(String) # JSON or Comma-separated list of SharePoint IDs
    active = Column(Boolean, default=True)
    tenant_id = Column(String, index=True, nullable=True)  # Azure AD tenant (tid). NULL = paylaşılan legacy
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
    
    # New Fields for Client Management
    tc_no = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    mobile_phone = Column(String, nullable=True) # New field for Cep Telefonu
    address = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    contact_type = Column(String, default="Client") # "Client" or "Other"
    client_type = Column(String, nullable=True) # "Individual" or "Corporate"
    category = Column(String, nullable=True) # e.g. "Sigorta", "Özel", "Doktor"
    cari_kod = Column(String, nullable=True) # 6 haneli sicil no
    birth_year = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    specialty = Column(String, nullable=True)

    # Yeni alanlar — Excel import (cari_mikro_guncellendi.xlsx)
    il                  = Column(String, nullable=True)   # Col 8  - İl / Şehir
    sektor              = Column(String, nullable=True)   # Col 10 - Sektörü
    yevmiye_no          = Column(String, nullable=True)   # Col 13 - Yevmiye No
    noterlik            = Column(String, nullable=True)   # Col 14 - Noterlik adı
    vekaletname_tarihi  = Column(Date,   nullable=True)   # Col 15 - Veriliş tarihi
    vekil_avukatlar     = Column(String, nullable=True)   # Col 16 - AD SOYAD;AD SOYAD formatı
    gecerlilik_tarihi   = Column(Date,   nullable=True)   # Col 17 - Geçerlilik tarihi
    vekalet_no          = Column(String, nullable=True)   # Col 18 - Vekalet No
    buro_vekalet_no     = Column(String, nullable=True)   # Col 19 - Büro Vekalet No

    # When a client is deleted, set client_id to NULL in case_parties (don't delete the party row)
    case_parties = relationship("CaseParty", back_populates="client", passive_deletes=True)

class DocType(Base):
    __tablename__ = "doctypes" # BelgeTuru

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "DAVA-DLK"
    name = Column(String, nullable=False) # "Dava Dilekçesi"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Status(Base):
    __tablename__ = "statuses" # Durum

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "B"
    name = Column(String, nullable=False) # "Büro"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class SyncLog(Base):
    """Logs when the last sync happened for each list type."""
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    list_name = Column(String, unique=True, index=True) # "Lawyers", "Clients", etc.
    last_sync = Column(DateTime(timezone=True), default=func.now())
    status = Column(String) # "SUCCESS", "FAILED"
    item_count = Column(Integer, default=0)

class EmailRecipient(Base):
    __tablename__ = "email_recipients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class CaseSubject(Base):
    __tablename__ = "case_subjects" # Dava Konulari

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # "BOSANMA"
    name = Column(String, nullable=False) # "Boşanma Davası"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class FileType(Base):
    __tablename__ = "file_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "Ceza"
    name = Column(String, nullable=False)                           # e.g. "Ceza"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class CourtType(Base):
    __tablename__ = "court_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, index=True, nullable=False)               # e.g. "AGIR-CEZA"
    name = Column(String, nullable=False)                           # e.g. "AĞIR CEZA MAHKEMESİ"
    parent_code = Column(String, nullable=False)                    # e.g. "Ceza"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class PartyRole(Base):
    __tablename__ = "party_roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "DAVACI"
    name = Column(String, nullable=False)                           # e.g. "Davacı"
    role_type = Column(String, default="MAIN")                      # "MAIN" or "THIRD"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class BureauType(Base):
    __tablename__ = "bureau_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ALEYHE"
    name = Column(String, nullable=False)                           # e.g. "ALEYHE"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ISTANBUL"
    name = Column(String, nullable=False)                           # e.g. "İstanbul"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Specialty(Base):
    __tablename__ = "specialties"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "ACIL-TIP"
    name = Column(String, nullable=False)                           # e.g. "Acil Tıp"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class ClientCategory(Base):
    __tablename__ = "client_categories"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "DOKTOR"
    name = Column(String, nullable=False)                           # e.g. "Doktor"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class FileStatus(Base):
    __tablename__ = "file_statuses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)  # e.g. "BILIRKISIDE"
    name = Column(String, nullable=False)                           # e.g. "Bilirkişide"
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class AnalysisCache(Base):
    """
    Cache for file analysis results to avoid re-processing.
    Moved from SQLite (db_manager.py) to Main DB (PostgreSQL).
    """
    __tablename__ = "analysis_cache"

    file_hash = Column(String, primary_key=True, index=True)
    data_json = Column(String, nullable=True) # JSON stored as Text
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())


class HearingDate(Base):
    """Duruşma zaptından çıkarılan bir sonraki duruşma tarihleri."""
    __tablename__ = "hearing_dates"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    hearing_date = Column(Date, nullable=False)
    hearing_time = Column(String(10), nullable=True)  # "09:43" formatında saat
    lawyer_name = Column(String, nullable=True)       # Sorumlu avukat (ajanda filtresi için)
    extracted_from_doc = Column(String, nullable=True) # Kaynak belge adı
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    note = Column(String, nullable=True)

    case = relationship("Case")


class CaseDocument(Base):
    """
    Faz 1: Belgeler ile Davalar arasındaki bağlantıyı tutar.
    Her yüklenen belge bir davaya bağlanır (veya TEST modunda serbest bırakılır).
    """
    __tablename__ = "case_documents"

    id = Column(Integer, primary_key=True, index=True)

    # Dava bağlantısı (nullable: TEST modunda dava seçilmeyebilir)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)

    # Dosya bilgileri
    original_filename = Column(String, nullable=False)        # Orijinal yüklenen dosya adı
    stored_filename = Column(String, nullable=False)          # Sistemin verdiği standart ad
    sharepoint_url = Column(String, nullable=True)            # SharePoint'teki tam URL (ileride)
    belge_turu_kodu = Column(String, nullable=True)           # "DAVA-DLK", "KARAR-BLG" vb.
    belge_turu_adi = Column(String, nullable=True)            # "Dava Dilekçesi" (okunabilir)
    ai_summary = Column(String, nullable=True)                # Gemini'nin kısa özeti
    muvekkil_adi = Column(String, nullable=True)              # İlgili müvekkil (deprecated: case_party_id kullan)
    case_party_id = Column(Integer, ForeignKey("case_parties.id", ondelete="SET NULL"), nullable=True)  # NULL → tüm dava, dolu → o tarafa ait
    avukat_kodu = Column(String, nullable=True)               # Sorumlu avukat kodu
    esas_no = Column(String, nullable=True)                   # Belgede geçen esas no

    # Bağlantı modu
    # "LINKED"  → Gerçek bir davaya bağlandı
    # "TEST"    → Test modunda yüklendi, dava seçilmedi
    # "UNLINKED"→ Analiz tamamlandı ama dava bulunamadı / kullanıcı seçmedi
    link_mode = Column(String, default="UNLINKED", nullable=False)

    # Meta
    uploaded_by = Column(String, nullable=True)              # Azure AD kullanıcı adı
    uploaded_at = Column(DateTime(timezone=True), default=func.now())

    # E-posta durumu
    email_sent = Column(Boolean, nullable=True)              # None=gönderilmedi/atlandı, True=başarılı, False=hata
    email_error = Column(String, nullable=True)              # Hata mesajı (email_sent=False ise)

    # Kullanıcı kimliği (UPN / preferred_username)
    uploaded_by_email = Column(String, nullable=True, index=True)

    # İlişkiler
    case = relationship("Case", back_populates="documents")
    case_party = relationship("CaseParty", foreign_keys=[case_party_id])


class DailyActivityReport(Base):
    """Kullanıcı başına günlük belge yükleme özeti — gece yarısı oluşturulur."""
    __tablename__ = "daily_activity_reports"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=True, index=True)
    user_email = Column(String, nullable=False, index=True)   # preferred_username (UPN)
    report_date = Column(Date, nullable=False)                # Raporlanan gün (dün)
    total_documents = Column(Integer, default=0)
    mailed_documents = Column(Integer, default=0)             # email_sent=True
    unmailed_documents = Column(Integer, default=0)           # email_sent=None (kullanıcı atladı)
    error_documents = Column(Integer, default=0)              # email_sent=False (hata)
    unmailed_doc_ids = Column(String, nullable=True)          # JSON liste: mailsiz belge id'leri
    mailed_doc_ids = Column(String, nullable=True)            # JSON liste: e-posta ile gitmiş belge id'leri
    error_doc_ids = Column(String, nullable=True)             # JSON liste: hata almış belge id'leri
    is_acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
