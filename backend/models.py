from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base

class Lawyer(Base):
    __tablename__ = "lawyers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False) # e.g. "AGH"
    name = Column(String, nullable=False) # e.g. "Ayşe..."
    active = Column(Boolean, default=True)
    sequence = Column(Integer, default=0) # Ordering
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())

class Client(Base):
    __tablename__ = "clients" # Muvekkiller

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False) # Normalized Unique Name (e.g. "AHMET YILMAZ")
    source_ids = Column(String) # JSON or Comma-separated list of SharePoint IDs
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
    
    # New Fields for Client Management
    tc_no = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    address = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    contact_type = Column(String, default="Client") # "Client" or "Other"
    client_type = Column(String, nullable=True) # "Individual" or "Corporate"
    category = Column(String, nullable=True) # e.g. "Sigorta", "Özel"

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
