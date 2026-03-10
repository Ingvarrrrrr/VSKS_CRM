from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
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

# ResponsiblePerson
class ResponsiblePersonCreate(BaseModel):
    full_name: str
    position: Optional[str] = None

class ResponsiblePersonOut(ResponsiblePersonCreate):
    id: int
    subsidy_id: Optional[int] = None
    is_active: bool = True
    model_config = {"from_attributes": True}

# SubsidyApprover
class SubsidyApproverCreate(BaseModel):
    role_name: str
    full_name: str
    order_num: int = 0
    is_default: bool = True
    can_initiate: bool = False
    show_feo_path: bool = False

class SubsidyApproverOut(SubsidyApproverCreate):
    id: int
    subsidy_id: int
    model_config = {"from_attributes": True}

# FeoCategory
class FeoCategoryCreate(BaseModel):
    parent_id: Optional[int] = None
    subsidy_id: int
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    is_active: bool = True
    budget: Optional[float] = None

class FeoCategoryOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    subsidy_id: int
    level: int
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    is_active: bool = True
    budget: Optional[float] = None
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
    # Contract document fields
    signatory: Optional[str] = None
    signatory_basis: Optional[str] = None
    postal_address: Optional[str] = None
    ogrn: Optional[str] = None
    settlement_account: Optional[str] = None
    bank_name: Optional[str] = None
    bik: Optional[str] = None
    correspondent_account: Optional[str] = None
    org_type: Optional[str] = None

class ContractorOut(ContractorCreate):
    id: int
    model_config = {"from_attributes": True}

# Contract
class ContractCreate(BaseModel):
    number: str
    date: Optional[date] = None
    contract_type: str  # single / framework_cumulative / framework_with_amount
    contractor_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    subject: Optional[str] = None
    max_amount: Optional[Decimal] = None
    status: str = "active"
    notes: Optional[str] = None

class ContractOut(ContractCreate):
    id: int
    total_payment: Optional[Decimal] = None
    remaining: Optional[Decimal] = None
    contractor_name: Optional[str] = None
    contractor_inn: Optional[str] = None
    model_config = {"from_attributes": True}

# PurchaseItem
class PurchaseItemCreate(BaseModel):
    product_id: Optional[int] = None
    item_name: str
    item_type: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    final_unit_price: Optional[Decimal] = None
    final_total: Optional[Decimal] = None

class PurchaseItemOut(PurchaseItemCreate):
    id: int
    product_name: Optional[str] = None
    product_photo_url: Optional[str] = None
    product_description: Optional[str] = None
    model_config = {"from_attributes": True}

class PurchaseFileOut(BaseModel):
    id: int
    purchase_id: int
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    file_type: Optional[str] = "other"
    doc_format: Optional[str] = "scan"
    created_at: Optional[str] = None
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
    confirmed: Optional[bool] = False
    final_unit_price: Optional[Decimal] = None
    final_total_amount: Optional[Decimal] = None
    delivery_payment_amount: Optional[Decimal] = None
    contract_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    status: str = "planned"
    # Phase 1: extended fields
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    registry_number: Optional[str] = None
    purchase_method: Optional[str] = None  # 'single' | 'competitive'
    purchase_basis: Optional[str] = None   # 'plan_schedule' | 'service_note'
    responsible_person: Optional[str] = None
    nmck: Optional[Decimal] = None
    contract_price: Optional[Decimal] = None
    economy: Optional[Decimal] = None
    price_increase: Optional[Decimal] = None
    execution_term: Optional[date] = None
    execution_term_changed: Optional[date] = None
    delivery_date: Optional[date] = None
    country_origin: Optional[str] = None
    subject: Optional[str] = None
    acceptance_doc_name: Optional[str] = None
    acceptance_doc_date: Optional[date] = None
    acceptance_doc_number: Optional[str] = None
    acceptance_doc_amount: Optional[Decimal] = None
    payment_doc_number: Optional[str] = None
    payment_doc_date: Optional[date] = None
    payment_amount: Optional[Decimal] = None
    payment_federal: Optional[Decimal] = None
    total_nmck: Optional[Decimal] = None
    purchase_contract_type: Optional[str] = None
    items: List[PurchaseItemCreate] = []

class PurchaseOut(PurchaseCreate):
    id: int
    items: List[PurchaseItemOut] = []
    files: List[PurchaseFileOut] = []
    model_config = {"from_attributes": True}

class PurchaseOutFull(PurchaseOut):
    contractor_name: Optional[str] = None
    feo_category_name: Optional[str] = None
    subsidy_name: Optional[str] = None

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
class PriceLink(BaseModel):
    url: str
    price: Optional[float] = None

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
    price_links: List[PriceLink] = []

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


# Platform publications
class PublishRequest(BaseModel):
    platform: str  # fabrikant / roseltorg_rb

class PublicationStatusUpdate(BaseModel):
    status: str             # published / error
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_text: Optional[str] = None

class PublicationOut(BaseModel):
    id: int
    purchase_id: int
    platform: str
    status: str
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_text: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Memory/Notes
class MemoryCreate(BaseModel):
    title: str
    problem: Optional[str] = None
    solution: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: bool = False

class MemoryOut(MemoryCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
