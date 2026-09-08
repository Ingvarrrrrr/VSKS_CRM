"""Auth, users, and organizations schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime

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
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None  # необязательно — не у всех есть отчество
    full_name: Optional[str] = None  # deprecated: обратная совместимость (одна строка ФИО), разбирается на бэкенде через split_fio, если last/first_name не переданы
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
    all_orgs_access: bool = False  # доступ ко всем организациям аккаунта, роль не меняется
    # Дата трудоустройства (владелец, 2026-09-01): если указана при приёме
    # с отделом/должностью — первая dept_assigned_at/position_assigned_at
    # равна ей, а не «сегодня» (см. app/services/org_assignment_dates.py).
    hired_at: Optional[datetime] = None

class UserUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None  # необязательно — не у всех есть отчество
    full_name: Optional[str] = None  # deprecated: обратная совместимость (одна строка ФИО), см. resolve_user_name_input
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
    all_orgs_access: Optional[bool] = None  # доступ ко всем организациям аккаунта, роль не меняется
    superior_user_id: Optional[int] = None  # вышестоящий начальник (иерархия согласования)
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
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
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
    all_orgs_access: bool = False  # доступ ко всем организациям аккаунта, роль не меняется
    superior_user_id: Optional[int] = None
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
    signatory_position: Optional[str] = None
    signatory_last_name: Optional[str] = None
    signatory_first_name: Optional[str] = None
    signatory_middle_name: Optional[str] = None
    contractor_id: Optional[int] = None
    color: Optional[str] = None
    # Phase 30: geo + head
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None
    head_user_id: Optional[int] = None
    # Fabrikant: город заключения договора
    contract_city: Optional[str] = None
    # 2026-09-01: явный выбор аккаунта (головной организации) при создании —
    # только superadmin; см. app/services/org_account_resolution.py. Для
    # остальных ролей игнорируется бэкендом (аккаунт = свой контур).
    root_org_id: Optional[int] = None

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
    signatory_last_name: Optional[str] = None
    signatory_first_name: Optional[str] = None
    signatory_middle_name: Optional[str] = None
    signatory_basis: Optional[str] = None
    website: Optional[str] = None
    # Fabrikant: город заключения договора
    contract_city: Optional[str] = None
    model_config = {"from_attributes": True}

class RegisterRequest(BaseModel):
    org_name: str
    org_inn: Optional[str] = None
    username: Optional[str] = None
    password: str
    full_name: Optional[str] = None
    email: str

