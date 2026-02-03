from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserUpdate(BaseModel):
    telegram_chat_id: Optional[str] = None

class UserResponse(UserBase):
    id: int
    role: str
    subscription_status: str
    package_type: str
    expiry_date: Optional[datetime]
    created_at: datetime
    telegram_chat_id: Optional[str]

    class Config:
        from_attributes = True

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Lead Schemas ---
class LeadBase(BaseModel):
    phone: str
    name: Optional[str] = None
    business_name: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = "Pending"

class LeadCreate(LeadBase):
    pass

class LeadResponse(LeadBase):
    id: int
    date_added: datetime
    owner_id: int

    class Config:
        from_attributes = True

# --- Template Schemas ---
class TemplateBase(BaseModel):
    name: Optional[str] = "Untitled"
    content: str

class TemplateCreate(TemplateBase):
    pass

class TemplateResponse(TemplateBase):
    id: int
    created_at: datetime
    owner_id: int

    class Config:
        from_attributes = True

# --- Midtrans Schemas ---
class MidtransTransactionBase(BaseModel):
    order_id: str
    gross_amount: int
    transaction_status: str

class MidtransTransactionResponse(MidtransTransactionBase):
    id: int
    payment_type: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class MidtransWebhook(BaseModel):
    transaction_time: str
    transaction_status: str
    transaction_id: str
    status_message: str
    status_code: str
    signature_key: str
    payment_type: str
    order_id: str
    merchant_id: str
    gross_amount: str
    fraud_status: Optional[str] = None
    currency: str

# --- Package Schemas ---
class PackageBase(BaseModel):
    name: str
    display_name: str
    price: int
    max_senders: int
    duration_days: int = 30

class PackageCreate(PackageBase):
    pass

class PackageUpdate(BaseModel):
    display_name: Optional[str] = None
    price: Optional[int] = None
    max_senders: Optional[int] = None
    duration_days: Optional[int] = None
    is_active: Optional[bool] = None

class PackageResponse(PackageBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Payment Request ---
class PaymentRequest(BaseModel):
    package_name: str  # "basic" or "advance"
