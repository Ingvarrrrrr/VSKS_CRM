from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from decimal import Decimal

# Auth
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None

# User
class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    full_name: Optional[str] = None
    city: Optional[str] = None

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    full_name: Optional[str] = None
    city: Optional[str] = None
    model_config = {"from_attributes": True}

# Subsidy
class SubsidyCreate(BaseModel):
    name: str
    year: int
    budget: float
    description: Optional[str] = None

class SubsidyOut(BaseModel):
    id: int
    name: str
    year: int
    budget: float
    description: Optional[str] = None
    model_config = {"from_attributes": True}

# FeoCategory
class FeoCategoryOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    subsidy_id: int
    level: int
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    is_active: bool = True
    model_config = {"from_attributes": True}

class FeoCategoryTree(FeoCategoryOut):
    children: List["FeoCategoryTree"] = []

# Contractor
class ContractorCreate(BaseModel):
    name: str
    inn: Optional[str] = None
    kpp: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    bank_details: Optional[str] = None

class ContractorOut(ContractorCreate):
    id: int
    model_config = {"from_attributes": True}

# Contract
class ContractCreate(BaseModel):
    number: str
    date: Optional[date] = None
    contract_type: str  # framework / one-time
    contractor_id: Optional[int] = None
    subject: Optional[str] = None
    max_amount: Optional[Decimal] = None
    status: str = "active"
    notes: Optional[str] = None

class ContractOut(ContractCreate):
    id: int
    total_payment: Optional[Decimal] = None
    remaining: Optional[Decimal] = None
    model_config = {"from_attributes": True}

# Purchase
class PurchaseCreate(BaseModel):
    row_number: Optional[int] = None
    purchase_number: Optional[int] = None
    order_number: Optional[str] = None
    feo_category_id: Optional[int] = None
    item_type: Optional[str] = None
    item_name: Optional[str] = None
    contractor_id: Optional[int] = None
    planned_quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    planned_unit_price: Optional[Decimal] = None
    planned_total_price: Optional[Decimal] = None
    confirmed: bool = False
    final_unit_price: Optional[Decimal] = None
    final_total_amount: Optional[Decimal] = None
    delivery_payment_amount: Optional[Decimal] = None
    contract_id: Optional[int] = None
    status: str = "planned"

class PurchaseOut(PurchaseCreate):
    id: int
    model_config = {"from_attributes": True}

# Payment
class PaymentCreate(BaseModel):
    contract_id: Optional[int] = None
    purchase_id: Optional[int] = None
    document_number: Optional[str] = None
    payment_purpose: Optional[str] = None
    payment_date: Optional[date] = None
    amount: Optional[Decimal] = None

class PaymentOut(PaymentCreate):
    id: int
    model_config = {"from_attributes": True}

# Product
class ProductCreate(BaseModel):
    feo_category_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    product_type: Optional[str] = None
    is_reusable: Optional[bool] = True
    photo_url: Optional[str] = None
    photo_link: Optional[str] = None
    clarification_link: Optional[str] = None
    is_active: bool = True
    price: Optional[Decimal] = None

class ProductOut(ProductCreate):
    id: int
    model_config = {"from_attributes": True}

# Dashboard
class DashboardCategory(BaseModel):
    id: int
    name: str
    level: int
    total_planned: Decimal = Decimal("0")
    total_confirmed: Decimal = Decimal("0")
    total_payment: Decimal = Decimal("0")
    children: List["DashboardCategory"] = []

class DashboardSummary(BaseModel):
    subsidy_limit: Decimal
    total_obligations: Decimal
    total_payments: Decimal
    remaining: Decimal
    categories: List[DashboardCategory]
