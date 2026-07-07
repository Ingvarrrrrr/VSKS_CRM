import re
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from typing import Optional, List, Any, Dict, Literal
from datetime import date, datetime
from decimal import Decimal

# Alias to avoid Pydantic v2 field-name-shadows-type bug for 'date: Optional[date]'
_Date = date

# Auth
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    user_id: Optional[int] = None
    can_publish: bool = False

# User
class UserCreate(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    role: str = "employee"
    full_name: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    work_phone: Optional[str] = None
    telegram_id: Optional[str] = None
    max_chat_id: Optional[str] = None
    avatar: Optional[str] = None
    org_id: Optional[int] = None
    inn: Optional[str] = None
    exclude_from_directory: bool = False

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    work_phone: Optional[str] = None
    telegram_id: Optional[str] = None
    max_chat_id: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    avatar: Optional[str] = None
    inn: Optional[str] = None
    exclude_from_directory: Optional[bool] = None
    # Phase 29 D-04: driver fields
    can_drive: Optional[bool] = None
    license_series: Optional[str] = None
    license_number: Optional[str] = None
    license_categories: Optional[str] = None
    license_issued_at: Optional[_Date] = None
    license_expires_at: Optional[_Date] = None
    medical_cert_expires_at: Optional[_Date] = None
    tachograph_card_expires_at: Optional[_Date] = None
    psych_cert_expires_at: Optional[_Date] = None
    periodic_medical_expires_at: Optional[_Date] = None

class PermissionsOut(BaseModel):
    tabs: List[str] = []
    actions: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    full_name: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    phone: Optional[str] = None
    work_phone: Optional[str] = None
    telegram_id: Optional[str] = None
    max_chat_id: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None
    photo_url: Optional[str] = None
    org_id: Optional[int] = None
    is_email_confirmed: bool = True
    has_signature: bool = False
    can_publish: bool = False
    inn: Optional[str] = None
    exclude_from_directory: bool = False
    # Phase 29 D-04 / 30: driver fields exposed to frontend
    can_drive: bool = False
    license_series: Optional[str] = None
    license_number: Optional[str] = None
    license_categories: Optional[str] = None
    license_issued_at: Optional[_Date] = None
    license_expires_at: Optional[_Date] = None
    medical_cert_expires_at: Optional[_Date] = None
    tachograph_card_expires_at: Optional[_Date] = None
    psych_cert_expires_at: Optional[_Date] = None
    periodic_medical_expires_at: Optional[_Date] = None
    medical_cert_number: Optional[str] = None
    driver_tab_number: Optional[str] = None
    experience_years: Optional[int] = None
    fleet_role: Optional[str] = None
    has_license_scan: bool = False
    permissions: Optional[PermissionsOut] = None

    @classmethod
    def from_orm_with_signature(cls, user):
        d = cls.model_validate(user)
        d.has_signature = bool(user.signature_image)
        d.photo_url = user.profile_photo or None
        d.has_license_scan = bool(getattr(user, 'license_scan', None))
        return d

    model_config = {"from_attributes": True}

# Organization
class OrganizationCreate(BaseModel):
    name: str
    full_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    address: Optional[str] = None
    signatory: Optional[str] = None
    contractor_id: Optional[int] = None
    color: Optional[str] = None
    # Phase 30: geo + head
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None
    head_user_id: Optional[int] = None

class OrganizationOut(BaseModel):
    id: int
    name: str
    full_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    address: Optional[str] = None
    signatory: Optional[str] = None
    is_active: bool
    created_at: datetime
    user_count: int = 0
    root_org_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    # Phase 17.1-03 — link to Contractor as single source of truth for legal requisites
    contractor_id: Optional[int] = None
    # Extra enrichment fields (optional) populated from linked Contractor
    org_phone: Optional[str] = None
    org_email: Optional[str] = None
    color: Optional[str] = None
    # Phase 30: geo + head
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None
    head_user_id: Optional[int] = None
    # Extended contractor requisites (populated when contractor_id is set)
    postal_address: Optional[str] = None
    okpo: Optional[str] = None
    okved: Optional[str] = None
    bank_name: Optional[str] = None
    treasury_account: Optional[str] = None
    bik: Optional[str] = None
    single_treasury_account: Optional[str] = None
    registration_date: Optional[str] = None
    signatory_position: Optional[str] = None
    signatory_basis: Optional[str] = None
    website: Optional[str] = None
    model_config = {"from_attributes": True}

class RegisterRequest(BaseModel):
    org_name: str
    org_inn: Optional[str] = None
    username: Optional[str] = None
    password: str
    full_name: Optional[str] = None
    email: str

# Subsidy
class SubsidyCreate(BaseModel):
    model_config = ConfigDict(extra='ignore')

    name: str
    year: int
    budget: float
    description: Optional[str] = None
    contractor_id: Optional[int] = None
    # Phase 19: large agreement-text clause for docx templates
    agreement_text: Optional[str] = None
    # Phase 22: № и дата документа-основания
    basis_doc_number: Optional[str] = None
    basis_doc_date: Optional[_Date] = None
    # Phase 28: реквизиты грантодателя для шаблонов договоров
    grantor_name: Optional[str] = None
    ministry_name: Optional[str] = None
    # Phase 28: subsidy-specific clauses (пункты договора зависящие от субсидии)
    extra_contract_clause_1: Optional[str] = None
    extra_contract_clause_2: Optional[str] = None

    @field_validator('basis_doc_date', mode='before')
    @classmethod
    def empty_str_to_none_date(cls, v):
        if v == '' or v is None:
            return None
        return v

    @field_validator('basis_doc_number', mode='before')
    @classmethod
    def empty_str_to_none_number(cls, v):
        if v == '' or v is None:
            return None
        return v


class SubsidyUpdate(BaseModel):
    """Partial update — all fields optional."""
    name: Optional[str] = None
    year: Optional[int] = None
    budget: Optional[float] = None
    description: Optional[str] = None
    contractor_id: Optional[int] = None
    agreement_text: Optional[str] = None
    # Phase 22: № и дата документа-основания
    basis_doc_number: Optional[str] = None
    basis_doc_date: Optional[_Date] = None
    # Phase 28: реквизиты грантодателя для шаблонов договоров
    grantor_name: Optional[str] = None
    ministry_name: Optional[str] = None
    # Phase 28: subsidy-specific clauses (пункты договора зависящие от субсидии)
    extra_contract_clause_1: Optional[str] = None
    extra_contract_clause_2: Optional[str] = None

    @field_validator('basis_doc_date', mode='before')
    @classmethod
    def empty_str_to_none_date(cls, v):
        if v == '' or v is None:
            return None
        return v

    @field_validator('basis_doc_number', mode='before')
    @classmethod
    def empty_str_to_none_number(cls, v):
        if v == '' or v is None:
            return None
        return v


class SubsidyOut(BaseModel):
    id: int
    name: str
    year: int
    budget: float
    calculated_budget: Optional[float] = None
    description: Optional[str] = None
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    contractor_inn: Optional[str] = None
    org_id: Optional[int] = None
    org_inn: Optional[str] = None
    feo_filled: bool = False
    feo_budget_total: float = 0.0
    # Phase 19
    agreement_text: Optional[str] = None
    # Phase 22
    basis_doc_number: Optional[str] = None
    basis_doc_date: Optional[_Date] = None
    # Phase 28: реквизиты грантодателя для шаблонов договоров
    grantor_name: Optional[str] = None
    ministry_name: Optional[str] = None
    # Phase 28: subsidy-specific clauses (пункты договора зависящие от субсидии)
    extra_contract_clause_1: Optional[str] = None
    extra_contract_clause_2: Optional[str] = None
    model_config = {"from_attributes": True}


class SubsidyContractorOverrideCreate(BaseModel):
    org_type: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    signatory: Optional[str] = None
    signatory_basis: Optional[str] = None
    address: Optional[str] = None
    postal_address: Optional[str] = None
    bank_details: Optional[str] = None
    settlement_account: Optional[str] = None
    bank_name: Optional[str] = None
    bik: Optional[str] = None
    correspondent_account: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    org_phone: Optional[str] = None
    org_email: Optional[str] = None

class SubsidyContractorOverrideOut(SubsidyContractorOverrideCreate):
    id: int
    subsidy_id: int
    contractor_id: int
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
    user_id: Optional[int] = None

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
    planned_quantity: Optional[float] = None
    planned_amount: Optional[float] = None
    unit: Optional[str] = None

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
    planned_quantity: Optional[float] = None
    planned_amount: Optional[float] = None
    unit: Optional[str] = None
    model_config = {"from_attributes": True}

class FeoCategoryTree(FeoCategoryOut):
    children: List["FeoCategoryTree"] = []

# Contractor
class ContractorCreate(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def empty_strings_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, value in list(data.items()):
                if value == '':
                    data[key] = None
                elif isinstance(value, str) and key.endswith('_date'):
                    m = re.fullmatch(r'(\d{2})\.(\d{2})\.(\d{4})', value.strip())
                    if m:
                        data[key] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return data

    name: str
    full_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    org_phone: Optional[str] = None
    org_email: Optional[str] = None
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
    manual_product_categories: Optional[List[str]] = None
    # ГПХ-поля для физ.лица
    passport_series: Optional[str] = None
    passport_number: Optional[str] = None
    passport_issuer: Optional[str] = None
    passport_issued_date: Optional[_Date] = None
    snils: Optional[str] = None
    registration_address: Optional[str] = None
    birth_date: Optional[_Date] = None
    website: Optional[str] = None
    registration_date: Optional[_Date] = None
    okpo: Optional[str] = None
    okved: Optional[str] = None
    treasury_account: Optional[str] = None
    single_treasury_account: Optional[str] = None
    signatory_position: Optional[str] = None

class ContractorOut(ContractorCreate):
    id: int
    model_config = {"from_attributes": True}

# Contract
class ContractSubsidyOut(BaseModel):
    id: int
    subsidy_id: int
    subsidy_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ContractCreate(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def empty_strings_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, value in data.items():
                if value == '' or value == '':
                    data[key] = None
        return data

    number: str
    date: Optional[_Date] = None
    contract_type: str  # single / framework_cumulative / framework_with_amount
    contractor_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    subject: Optional[str] = None
    max_amount: Optional[Decimal] = None
    status: str = "active"
    notes: Optional[str] = None
    start_date: Optional[_Date] = None
    end_date: Optional[_Date] = None
    purchase_method: Optional[str] = None
    item_type: Optional[str] = None  # товар / услуга
    planned_monthly: Optional[Decimal] = None
    extra_subsidy_ids: List[int] = []

class ContractOut(ContractCreate):
    id: int
    total_payment: Optional[Decimal] = None
    remaining: Optional[Decimal] = None  # legacy: same as remaining_ordered
    remaining_ordered: Optional[Decimal] = None  # max_amount - SUM(contract_price)
    remaining_delivered: Optional[Decimal] = None  # SUM(contract_price) - SUM(delivery_payment_amount)
    remaining_paid: Optional[Decimal] = None  # SUM(delivery_payment_amount) - SUM(payment_amount)
    total_ordered: Optional[Decimal] = None
    total_delivered: Optional[Decimal] = None  # SUM(delivery_payment_amount)
    total_paid: Optional[Decimal] = None
    contractor_name: Optional[str] = None
    contractor_inn: Optional[str] = None
    subsidy_name: Optional[str] = None
    extra_subsidies: List[ContractSubsidyOut] = []
    model_config = {"from_attributes": True}

# Phase 31-04: contract cascade response
class ContractSyncWarnings(BaseModel):
    amount_over_max: bool = False
    date_out_of_validity: List[int] = []

class ContractUpdateResponse(BaseModel):
    contract: ContractOut
    n_updated_purchases: int = 0
    warnings: ContractSyncWarnings = ContractSyncWarnings()

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
    country_origin: Optional[str] = None
    match_confirmed: bool = True
    contractor_id: Optional[int] = None
    contractor_inn: Optional[str] = None
    contractor_name: Optional[str] = None
    vat_rate: Optional[str] = None  # Phase 26-U-3: per-item НДС ставка
    vat_amount: Optional[float] = None       # import-vat-cols: сумма НДС по позиции
    total_with_vat: Optional[float] = None   # import-vat-cols: стоимость с НДС
    feo_planned_item_id: Optional[int] = None  # 27.4-15: FEO link для plan-graph version
    feo_category_id: Optional[int] = None  # FCAT-B1: per-item привязка к leaf FeoCategory

class PurchaseItemOut(PurchaseItemCreate):
    id: int
    product_name: Optional[str] = None
    product_photo_url: Optional[str] = None
    product_description: Optional[str] = None
    product_description_44fz: Optional[str] = None
    receipt_id: Optional[int] = None  # Phase 26-BB
    model_config = {"from_attributes": True}

class PurchaseFileOut(BaseModel):
    id: int
    purchase_id: int
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    file_type: Optional[str] = "other"
    doc_format: Optional[str] = "scan"
    content_hash: Optional[str] = None
    is_active: Optional[bool] = True
    created_at: Optional[datetime] = None
    uploaded_by_id: Optional[int] = None
    uploaded_by_name: Optional[str] = None
    model_config = {"from_attributes": True}

# SubsidyAllocation
class SubsidyAllocationIn(BaseModel):
    subsidy_id: int
    amount: Optional[Decimal] = None

class SubsidyAllocationOut(BaseModel):
    id: int
    subsidy_id: int
    subsidy_name: Optional[str] = None
    amount: Optional[Decimal] = None
    model_config = ConfigDict(from_attributes=True)

# Purchase
class PurchaseCreate(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def empty_strings_to_none(cls, data: Any) -> Any:
        """Convert empty strings to None for Optional fields to avoid validation errors."""
        if isinstance(data, dict):
            for key, value in data.items():
                if value == '' or value == '':
                    data[key] = None
        return data

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
    status: str = "wishes"
    substatus: Optional[str] = None
    is_monthly_payment: Optional[bool] = False
    monthly_payment_count: Optional[int] = None
    monthly_payment_amount: Optional[Decimal] = None
    # Phase 24: stages + financial plan
    is_likely_needed: Optional[bool] = True
    is_prepayment: Optional[bool] = False
    prepayment_date: Optional[date] = None
    stage_label: Optional[str] = None
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
    delivery_address: Optional[str] = None
    procurement_planned_date: Optional[date] = None
    country_origin: Optional[str] = None
    subject: Optional[str] = None
    acceptance_doc_name: Optional[str] = None
    acceptance_doc_date: Optional[date] = None
    acceptance_doc_number: Optional[str] = None
    acceptance_doc_amount: Optional[Decimal] = None
    acceptance_docs: Optional[list] = None  # [{name, number, date, amount}, ...]
    payment_doc_number: Optional[str] = None
    payment_doc_date: Optional[date] = None
    payment_amount: Optional[Decimal] = None
    payment_federal: Optional[Decimal] = None
    total_nmck: Optional[Decimal] = None
    purchase_contract_type: Optional[str] = None
    framework_seq: Optional[int] = None          # порядковый номер в рамочном договоре
    # Contract document generation fields
    vat_applicable: Optional[bool] = False
    vat_rate: Optional[int] = None
    vat_exemption_article: Optional[str] = None
    third_party_involved: Optional[bool] = False
    contract_end_date: Optional[date] = None
    service_period_type: Optional[str] = None
    service_start_date: Optional[date] = None
    service_end_date: Optional[date] = None
    description_mode: Optional[str] = "exact"
    event_id: Optional[int] = None
    approval_status: Optional[str] = None
    approval_mode: Optional[str] = None
    approval_sign_type: Optional[str] = None
    treasury_code: Optional[str] = None
    has_pretension: Optional[bool] = False
    payment_basis_type: Optional[str] = "contract"
    service_note_text: Optional[str] = None
    service_note_by: Optional[int] = None
    service_note_at: Optional[datetime] = None
    # Phase 19: template fields for docx context
    submission_deadline: Optional[datetime] = None
    delivery_location: Optional[str] = None
    delivery_location_kind: Optional[str] = None    # '' | 'delivery' | 'service' (фидбек 5 мая, ручной тогл)
    region: Optional[str] = None                    # Регион проведения мероприятия (89 субъектов РФ или спец-значения)
    service_term_mode: Optional[str] = None         # 'range' | 'duration' | 'deadline'
    service_term_days: Optional[int] = None         # mode='duration'
    service_term_type: Optional[str] = None         # 'calendar' | 'working' (mode='duration')
    service_deadline_date: Optional[date] = None    # mode='deadline'
    reimbursement_user_id: Optional[int] = None
    assigned_user_id: Optional[int] = None  # Phase 28 B4: ответственный исполнитель
    service_note_to_user_id: Optional[int] = None  # SN-UX: адресат служебной записки
    vat_mode: Optional[str] = None  # Phase 26-U-3: 'uniform' | 'per_item'
    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number: Optional[str] = None
    agreement_date: Optional[date] = None
    order_date: Optional[date] = None
    # Phase 28: форма договора для выбора шаблона при генерации
    contract_form: Optional[str] = None
    # Phase 28: contract-specific поля (условия конкретного договора)
    acceptance_term_days: Optional[int] = None
    penalty_rate: Optional[Decimal] = None
    contractor_ogrnip_date: Optional[date] = None
    repair_request_number: Optional[str] = None
    commission_member_1_name: Optional[str] = None
    commission_member_2_name: Optional[str] = None
    commission_member_3_name: Optional[str] = None
    advance_amount: Optional[Decimal] = None
    # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
    warranty_period_days: Optional[int] = None
    is_retroactive: Optional[bool] = False
    # Phase 29: связь с ТС
    vehicle_id: Optional[int] = None
    # ЭТП: ссылка на конкурсную процедуру
    etp_url: Optional[str] = None
    items: List[PurchaseItemCreate] = []
    subsidy_allocations: Optional[List[SubsidyAllocationIn]] = None


class PurchaseUpdate(BaseModel):
    """Partial update — all fields optional. Accepts any known Purchase field."""
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
    confirmed: Optional[bool] = None
    final_unit_price: Optional[Decimal] = None
    final_total_amount: Optional[Decimal] = None
    delivery_payment_amount: Optional[Decimal] = None
    contract_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    status: Optional[str] = None
    substatus: Optional[str] = None
    is_monthly_payment: Optional[bool] = None
    monthly_payment_count: Optional[int] = None
    monthly_payment_amount: Optional[Decimal] = None
    # Phase 24: stages + financial plan
    is_likely_needed: Optional[bool] = None
    is_prepayment: Optional[bool] = None
    prepayment_date: Optional[date] = None
    stage_label: Optional[str] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    registry_number: Optional[str] = None
    purchase_method: Optional[str] = None
    purchase_basis: Optional[str] = None
    responsible_person: Optional[str] = None
    nmck: Optional[Decimal] = None
    contract_price: Optional[Decimal] = None
    economy: Optional[Decimal] = None
    price_increase: Optional[Decimal] = None
    execution_term: Optional[date] = None
    execution_term_changed: Optional[date] = None
    delivery_date: Optional[date] = None
    delivery_address: Optional[str] = None
    procurement_planned_date: Optional[date] = None
    country_origin: Optional[str] = None
    subject: Optional[str] = None
    acceptance_doc_name: Optional[str] = None
    acceptance_doc_date: Optional[date] = None
    acceptance_doc_number: Optional[str] = None
    acceptance_doc_amount: Optional[Decimal] = None
    acceptance_docs: Optional[list] = None
    payment_doc_number: Optional[str] = None
    payment_doc_date: Optional[date] = None
    payment_amount: Optional[Decimal] = None
    payment_federal: Optional[Decimal] = None
    total_nmck: Optional[Decimal] = None
    purchase_contract_type: Optional[str] = None
    framework_seq: Optional[int] = None
    vat_applicable: Optional[bool] = None
    vat_rate: Optional[int] = None
    vat_exemption_article: Optional[str] = None
    third_party_involved: Optional[bool] = None
    contract_end_date: Optional[date] = None
    service_period_type: Optional[str] = None
    service_start_date: Optional[date] = None
    service_end_date: Optional[date] = None
    description_mode: Optional[str] = None
    event_id: Optional[int] = None
    approval_status: Optional[str] = None
    approval_mode: Optional[str] = None
    approval_sign_type: Optional[str] = None
    treasury_code: Optional[str] = None
    has_pretension: Optional[bool] = None
    payment_basis_type: Optional[str] = None
    service_note_text: Optional[str] = None
    service_note_by: Optional[int] = None
    service_note_at: Optional[datetime] = None
    # Phase 19
    submission_deadline: Optional[datetime] = None
    delivery_location: Optional[str] = None
    delivery_location_kind: Optional[str] = None
    region: Optional[str] = None                    # Регион проведения мероприятия
    service_term_mode: Optional[str] = None
    service_term_days: Optional[int] = None
    service_term_type: Optional[str] = None
    service_deadline_date: Optional[date] = None
    reimbursement_user_id: Optional[int] = None
    assigned_user_id: Optional[int] = None  # Phase 28 B4
    vat_mode: Optional[str] = None  # Phase 26-U-3: 'uniform' | 'per_item'
    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number: Optional[str] = None
    agreement_date: Optional[date] = None
    order_date: Optional[date] = None
    # Phase 28: форма договора для выбора шаблона при генерации
    contract_form: Optional[str] = None
    # Phase 28: contract-specific поля (условия конкретного договора)
    acceptance_term_days: Optional[int] = None
    penalty_rate: Optional[Decimal] = None
    contractor_ogrnip_date: Optional[date] = None
    repair_request_number: Optional[str] = None
    commission_member_1_name: Optional[str] = None
    commission_member_2_name: Optional[str] = None
    commission_member_3_name: Optional[str] = None
    advance_amount: Optional[Decimal] = None
    # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
    warranty_period_days: Optional[int] = None
    is_retroactive: Optional[bool] = None
    # Phase 29: связь с ТС
    vehicle_id: Optional[int] = None
    # ЭТП: ссылка на конкурсную процедуру
    etp_url: Optional[str] = None


class PurchaseOut(PurchaseCreate):
    id: int
    items: List[PurchaseItemOut] = []
    files: List[PurchaseFileOut] = []
    subsidy_allocations: Optional[List[SubsidyAllocationOut]] = None
    # Phase 31: diff-tracking — unseen changes from other users
    unseen_fields: List[str] = []
    unseen_changes_count: int = 0
    # Phase 31-04: contract sync — True when linked contract data differs from purchase copy
    contract_conflict: bool = False
    model_config = {"from_attributes": True}

class PurchaseOutFull(PurchaseOut):
    contractor_name: Optional[str] = None
    contractor_inn: Optional[str] = None
    feo_category_name: Optional[str] = None
    subsidy_name: Optional[str] = None
    event_name: Optional[str] = None
    last_receipt_date: Optional[datetime] = None
    reimbursement_user_name: Optional[str] = None
    multi_contractor_label: Optional[str] = None
    # phase26-m: для рамочных закупок — max_amount договора или SUM(contract_price) всех закупок по нему
    framework_contract_total: Optional[Decimal] = None

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
    bank_payment_id: Optional[int] = None
    matched_confirmed: bool = False
    model_config = {"from_attributes": True}

# Product
class PriceLink(BaseModel):
    url: str
    price: Optional[float] = None

class ProductCreate(BaseModel):
    feo_category_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    description_44fz: Optional[str] = None
    category: str = Field(..., min_length=1)
    product_type: Optional[str] = None
    item_kind: Optional[str] = "товар"  # "товар" или "услуга"
    is_reusable: Optional[bool] = True
    photo_url: Optional[str] = None
    photo_link: Optional[str] = None
    clarification_link: Optional[str] = None
    is_active: bool = True
    price: Optional[Decimal] = None
    price_links: List[PriceLink] = []
    country_origin: Optional[str] = "Россия"

class ProductOut(ProductCreate):
    id: int
    # Override: in the DB old rows may still have category=NULL until the
    # n1o2p3q4r5s6 backfill migration is applied. ProductCreate enforces
    # non-empty on input, but responses must tolerate legacy NULLs.
    category: Optional[str] = None
    contract_price: Optional[Decimal] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    contract_org_id: Optional[int] = None
    price_shared: bool = False
    tz_verified_at: Optional[datetime] = None
    tz_verified_by: Optional[str] = None
    tz_44fz_verified_at: Optional[datetime] = None
    tz_44fz_verified_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    # Phase 17.1-08 — photo bytea storage. We expose only metadata here,
    # never the raw bytes (would bloat API responses to MBs per product).
    has_photo: bool = False
    photo_size: Optional[int] = None
    photo_mime: Optional[str] = None
    model_config = {"from_attributes": True}

    @model_validator(mode='before')
    @classmethod
    def _compute_has_photo(cls, data):
        # Derive `has_photo` from ORM object / dict so callers don't need to
        # set it manually. Phase 17.1-08 perf: check `photo_size` (cheap scalar)
        # instead of `photo_data` (bytea — triggers lazy load when deferred on
        # the list query). `photo_size` is populated whenever bytes are cached
        # (see _download_and_save_photo / upload_product_photo).
        try:
            if hasattr(data, 'photo_size'):
                has_photo_val = getattr(data, 'photo_size', None) is not None
                try:
                    object.__setattr__(data, 'has_photo', has_photo_val)
                except Exception:
                    pass
            elif isinstance(data, dict) and 'has_photo' not in data:
                data['has_photo'] = (
                    data.get('photo_size') is not None
                    or data.get('photo_data') is not None
                )
        except Exception:
            pass
        return data

# Product Summary (сводная по продукции)
class ProductSummaryItem(BaseModel):
    purchase_id: int
    subsidy_name: str
    org_name: Optional[str] = None
    org_id: Optional[int] = None
    region: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    status: Optional[str] = None
    delivery_date: Optional[date] = None
    delivery_address: Optional[str] = None
    procurement_planned_date: Optional[date] = None
    purchase_method: Optional[str] = None

class ProductSummaryGroup(BaseModel):
    product_id: int
    product_name: str
    category: Optional[str] = None
    product_type: Optional[str] = None
    total_quantity: Decimal
    total_amount: Decimal
    purchase_count: int
    items: List[ProductSummaryItem]

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
    procedure_type: Optional[str] = None  # только для roseltorg_rb: request_quotations / request_proposals / competition / auction
    proposal_start: Optional[str] = None       # ISO datetime, Фабрикант: начало приёма предложений
    proposal_end: Optional[str] = None         # ISO datetime, Фабрикант: конец приёма предложений
    determination_date: Optional[str] = None   # ISO datetime, Фабрикант: определение победителя
    summing_up_date: Optional[str] = None      # ISO datetime, Фабрикант: подведение итогов
    okpd2_code: Optional[str] = None           # ОКПД2 для всех позиций закупки (Фабрикант)

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


# ── Commercial Requests ────────────────────────────────────────────────────────

class CommercialRequestRecipientOut(BaseModel):
    id: int
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    email: Optional[str] = None
    status: str

class FreeRecipient(BaseModel):
    name: Optional[str] = None
    email: str

class CommercialRequestCreate(BaseModel):
    purchase_id: int
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None
    recipient_ids: Optional[List[int]] = None
    free_recipients: Optional[List[FreeRecipient]] = None

class CommercialRequestUpdate(BaseModel):
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None

class CommercialRequestStatusUpdate(BaseModel):
    status: str

class CommercialRequestRecipientStatusUpdate(BaseModel):
    status: str

class CommercialRequestOut(BaseModel):
    id: int
    purchase_id: int
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    recipients: List[CommercialRequestRecipientOut] = []


# ── Suppliers ──────────────────────────────────────────────────────────────────

class SupplierProductOut(BaseModel):
    id: int
    supplier_id: int
    product_id: Optional[int] = None
    price_notes: Optional[str] = None
    source: Optional[str] = None

class SupplierCreate(BaseModel):
    name: str
    inn: Optional[str] = None
    kpp: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None

class SupplierOut(BaseModel):
    id: int
    name: str
    inn: Optional[str] = None
    kpp: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    products: List[SupplierProductOut] = []

class SupplierProductCreate(BaseModel):
    product_id: Optional[int] = None
    price_notes: Optional[str] = None
    source: Optional[str] = None


# ── Events (Мероприятия) ──────────────────────────────────────────────────────

class EventCreate(BaseModel):
    subsidy_id: int
    name: str
    is_active: bool = True
    region: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    order_decree: Optional[str] = None
    planned_indicators: Optional[str] = None
    actual_indicators: Optional[str] = None
    media_link_1: Optional[str] = None
    media_link_2: Optional[str] = None
    media_link_3: Optional[str] = None

class EventOut(EventCreate):
    id: int
    model_config = {"from_attributes": True}


# ── Purchase Approvals (электронное согласование) ─────────────────────────────

class PurchaseApprovalOut(BaseModel):
    id: int
    purchase_id: int
    subsidy_approver_id: Optional[int] = None
    order_num: int
    role_name: str
    approver_full_name: str
    user_id: Optional[int] = None
    status: str
    comment: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[int] = None
    decided_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    has_signature: bool = False
    signature_algorithm: Optional[str] = None
    model_config = {"from_attributes": True}

class ApprovalDecisionRequest(BaseModel):
    action: str  # "approve" | "reject"
    comment: Optional[str] = None
    sign_electronically: bool = False

# Task (общие задачи, не связанные с закупками)
class TaskAssigneeOut(BaseModel):
    user_id: int
    user_name: Optional[str] = None
    consent_pending: bool = False
    model_config = {"from_attributes": True}

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    assignee_ids: List[int] = []
    category: Optional[str] = None
    parent_task_id: Optional[int] = None
    purchase_id: Optional[int] = None
    import_to_parent: bool = False

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    assignee_ids: Optional[List[int]] = None
    category: Optional[str] = None
    purchase_id: Optional[int] = None
    import_to_parent: Optional[bool] = None

class ReviewCompleteRequest(BaseModel):
    confirm: bool

class TaskOut(BaseModel):
    id: int
    task_number: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[datetime] = None
    assignees: List[TaskAssigneeOut] = []
    # legacy single-assignee fields (for backward compat in frontend)
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    created_by_id: int
    created_by_name: Optional[str] = None
    org_id: Optional[int] = None
    category: Optional[str] = None
    parent_task_id: Optional[int] = None
    purchase_id: Optional[int] = None
    purchase_subject: Optional[str] = None
    purchase_number: Optional[int] = None
    purchase_status: Optional[str] = None
    import_to_parent: bool = False
    subtask_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_comment: Optional[str] = None
    last_comment_user: Optional[str] = None
    last_comment_at: Optional[datetime] = None
    comment_count: int = 0
    needs_my_consent: bool = False
    unseen_changes_count: int = 0
    unseen_fields: List[str] = []
    model_config = {"from_attributes": True}


class DismissFieldRequest(BaseModel):
    field_name: str

# Task Comments
class TaskCommentCreate(BaseModel):
    text: str

class TaskCommentOut(BaseModel):
    id: int
    task_id: int
    user_id: int
    user_name: Optional[str] = None
    text: str
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── FeoPlannedItem ──────────────────────────────────────────────────────────

class FeoPlannedItemCreate(BaseModel):
    feo_category_id: int
    name: str
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: bool = True

class FeoPlannedItemOut(FeoPlannedItemCreate):
    id: int
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class FeoActualItemOut(BaseModel):
    """Фактическая позиция — purchase_item, связанный с feo_category через purchase."""
    purchase_item_id: int
    item_name: str
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    feo_planned_item_id: Optional[int] = None  # если сопоставлено
    purchase_id: int
    purchase_number: Optional[int] = None
    registry_number: Optional[str] = None
    purchase_status: Optional[str] = None
    contract_number: Optional[str] = None
    contractor_name: Optional[str] = None
    model_config = {"from_attributes": True}


class FeoComparisonOut(BaseModel):
    planned: list[FeoPlannedItemOut]
    actual: list[FeoActualItemOut]


# Budget History
class BudgetHistoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    purchase_id: Optional[int] = None
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    changed_by_name: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 17 Plan 05: permission matrix + per-user overrides schemas
# ---------------------------------------------------------------------------

class PermissionTabOut(BaseModel):
    tab_key: str
    title: str
    model_config = ConfigDict(from_attributes=True)


class PermissionActionOut(BaseModel):
    action_key: str
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class RolePermissionOut(BaseModel):
    role_name: str
    key: str
    granted: bool
    model_config = ConfigDict(from_attributes=True)


class RoleMatrixRow(BaseModel):
    role_name: str
    tabs: List[str]        # tab_keys where granted=True
    actions: List[str]     # action_keys where granted=True


class PermissionUpdate(BaseModel):
    key: str
    granted: bool


class RoleUpdate(BaseModel):
    role: str


class OverrideOut(BaseModel):
    key: str
    granted: bool
    model_config = ConfigDict(from_attributes=True)
    changed_at: Optional[datetime] = None


# ── Phase 21: purchase receipts ──────────────────────────────────────────────
class ReceiptItemIn(BaseModel):
    name: str
    quantity: Optional[Decimal] = Decimal('1')
    price: Optional[Decimal] = None   # ₽ already
    sum: Optional[Decimal] = None     # ₽ already
    nds: Optional[int] = None


class ReceiptCreate(BaseModel):
    fiscal_drive_number: Optional[str] = None
    fiscal_document_number: Optional[int] = None
    fiscal_sign: Optional[str] = None
    kkt_reg_id: Optional[str] = None
    receipt_datetime: Optional[datetime] = None
    total_sum: Optional[Decimal] = None
    cash_sum: Optional[Decimal] = None
    ecash_sum: Optional[Decimal] = None
    prepaid_sum: Optional[Decimal] = None
    nds_sum: Optional[Decimal] = None
    seller_name: Optional[str] = None
    seller_inn: Optional[str] = None
    retail_place: Optional[str] = None
    retail_place_address: Optional[str] = None
    operator: Optional[str] = None
    operator_inn: Optional[str] = None
    taxation_type: Optional[int] = None
    source: Optional[str] = 'manual'
    items: Optional[List[ReceiptItemIn]] = None


class ReceiptOut(BaseModel):
    id: int
    purchase_id: int
    fiscal_drive_number: Optional[str] = None
    fiscal_document_number: Optional[int] = None
    fiscal_sign: Optional[str] = None
    kkt_reg_id: Optional[str] = None
    receipt_datetime: Optional[datetime] = None
    total_sum: Optional[Decimal] = None
    cash_sum: Optional[Decimal] = None
    ecash_sum: Optional[Decimal] = None
    nds_sum: Optional[Decimal] = None
    seller_name: Optional[str] = None
    seller_inn: Optional[str] = None
    retail_place: Optional[str] = None
    retail_place_address: Optional[str] = None
    operator: Optional[str] = None
    operator_inn: Optional[str] = None
    taxation_type: Optional[int] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Phase 22 — Bank Statements
# ---------------------------------------------------------------------------

class BankStatementImportOut(BaseModel):
    id: int
    uploaded_by_id: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    file_name: Optional[str] = None
    sheet_name: Optional[str] = None
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    rows_matched: int = 0
    rows_unmatched: int = 0
    rows_dup: int = 0
    status: str = "processing"
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BankPaymentOut(BaseModel):
    id: int
    import_id: Optional[int] = None
    payment_number: Optional[str] = None
    payment_date: Optional[_Date] = None
    execution_datetime: Optional[datetime] = None
    status: Optional[str] = None
    amount: Optional[Decimal] = None
    payer_inn: Optional[str] = None
    payer_name: Optional[str] = None
    payer_name_resolved: Optional[str] = None  # Phase 22.5: разрешённое имя из Organization/Contractor по ИНН
    payee_inn: Optional[str] = None
    payee_name: Optional[str] = None
    payee_name_resolved: Optional[str] = None  # Phase 22.5: разрешённое имя из Organization/Contractor по ИНН
    payee_account: Optional[str] = None
    purpose_text: Optional[str] = None
    parsed_contract_number: Optional[str] = None
    parsed_contract_date: Optional[_Date] = None
    parsed_kbk: Optional[str] = None
    parsed_documents: Optional[Dict[str, List[Dict]]] = None
    basis_doc_number: Optional[str] = None
    basis_doc_date: Optional[_Date] = None
    basis_doc_text: Optional[str] = None
    subsidy_code: Optional[str] = None
    matched_contractor_id: Optional[int] = None
    matched_contract_id: Optional[int] = None
    matched_purchase_id: Optional[int] = None
    matched_subsidy_id: Optional[int] = None
    matched_confirmed: bool = False
    # 27.4-23: enriched human-readable значения для колонок «Match: ...»
    matched_contractor_name: Optional[str] = None
    matched_subsidy_name: Optional[str] = None
    matched_contract_number: Optional[str] = None
    matched_contract_subject: Optional[str] = None
    matched_contract_date: Optional[str] = None
    matched_purchase_number: Optional[int] = None
    matched_purchase_item_name: Optional[str] = None
    matched_purchase_amount: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class BankPaymentMatchUpdate(BaseModel):
    contract_id: Optional[int] = None
    contractor_id: Optional[int] = None


class BankPaymentConfirm(BaseModel):
    purchase_ids: List[int]


class ReportConfigCreate(BaseModel):
    kind: Literal['list', 'pivot', 'dashboard']
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config_json: dict = Field(default_factory=dict)
    parameters_json: list = Field(default_factory=list)
    is_default: bool = False
    is_shared: bool = True


class ReportConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_json: Optional[dict] = None
    parameters_json: Optional[list] = None
    is_default: Optional[bool] = None
    is_shared: Optional[bool] = None


class ReportConfigOut(BaseModel):
    id: int
    org_id: int
    kind: str
    name: str
    description: Optional[str] = None
    config_json: dict
    parameters_json: list
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    is_default: bool
    is_shared: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Phase 27.1: contract_items — фактически заказанные позиции по договору
# ---------------------------------------------------------------------------

class ContractItemBase(BaseModel):
    source_item_id: Optional[int] = None
    contract_id: Optional[int] = None
    product_id: Optional[int] = None
    name: str
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total: Optional[Decimal] = None
    vat_rate: Optional[str] = None  # Phase 27.1.17
    match_confirmed: bool = True


class ContractItemCreate(ContractItemBase):
    pass


class ContractItemUpdate(BaseModel):
    source_item_id: Optional[int] = None
    contract_id: Optional[int] = None
    product_id: Optional[int] = None
    name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total: Optional[Decimal] = None
    vat_rate: Optional[str] = None  # Phase 27.1.17
    match_confirmed: Optional[bool] = None


class ContractItemOut(ContractItemBase):
    id: int
    purchase_id: int
    source_item_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
