from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # "admin" or "user"
    subscription_status = Column(String, default="inactive") # "active", "inactive", "pending"
    package_type = Column(String, default="monthly") # "monthly" or "yearly"
    expiry_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    telegram_chat_id = Column(String, nullable=True, unique=True)

    # Relasi
    leads = relationship("Lead", back_populates="owner")
    templates = relationship("Template", back_populates="owner")
    transactions = relationship("MidtransTransaction", back_populates="owner")
    scraping_jobs = relationship("ScrapingJob", back_populates="owner")
    broadcast_campaigns = relationship("BroadcastCampaign", back_populates="owner")

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True)
    name = Column(String, nullable=True)
    business_name = Column(String, nullable=True)
    source = Column(String, nullable=True)
    status = Column(String, default="Pending") # "Pending", "WA Active", "Invalid"
    date_added = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="leads")

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Untitled")
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="templates")

class MidtransTransaction(Base):
    __tablename__ = "midtrans_transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    gross_amount = Column(Integer)
    payment_type = Column(String, nullable=True)
    transaction_status = Column(String) # "pending", "settlement", "expire", "cancel"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="transactions")

class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # "basic" or "advance"
    display_name = Column(String)  # "Paket Basic" or "Paket Advance"
    price = Column(Integer)  # Harga dalam Rupiah
    max_senders = Column(Integer)  # Batas jumlah sender WA
    duration_days = Column(Integer, default=30)  # Durasi langganan dalam hari
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    keyword = Column(String)
    limit = Column(Integer, default=50)
    status = Column(String, default="pending") # pending, running, completed, failed, stopped
    result_file_path = Column(String, nullable=True)
    log_file_path = Column(String, nullable=True)
    total_results = Column(Integer, default=0)
    pid = Column(Integer, nullable=True) # Store Process ID for kill switch
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="scraping_jobs")

class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, default="Untitled Campaign")
    template_body = Column(Text)
    target_type = Column(String) # all, verified
    session_used = Column(String, nullable=True)
    status = Column(String, default="pending") # pending, running, paused, completed, stopped
    total_recipients = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="broadcast_campaigns")
    logs = relationship("BroadcastLog", back_populates="campaign", cascade="all, delete-orphan")

class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("broadcast_campaigns.id"))
    phone = Column(String, index=True)
    name = Column(String, nullable=True)
    status = Column(String) # sent, failed, skipped
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    campaign = relationship("BroadcastCampaign", back_populates="logs")
