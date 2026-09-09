"""Contractors, contracts, and contract items schemas (extracted from schemas.py)."""
import re
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal

_Date = date

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
    signatory_last_name: Optional[str] = None
    signatory_first_name: Optional[str] = None
    signatory_middle_name: Optional[str] = None

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
    # Владелец (2026-09-02): состояние согласования рамочной ГОЛОВЫ договора —
    # вычисляется из Purchase.approval_status привязанной рамочной головы, не
    # хранится отдельной колонкой (см. contracts.py::list_contracts).
    # pending — голова ждёт согласования по цепочке руководителей, approved —
    # согласована, None — головы нет или цепочка не строилась (историческая).
    approval_state: Optional[str] = None
    model_config = {"from_attributes": True}

# Phase 31-04: contract cascade response
class ContractSyncWarnings(BaseModel):
    amount_over_max: bool = False
    date_out_of_validity: List[int] = []

class ContractUpdateResponse(BaseModel):
    contract: ContractOut
    n_updated_purchases: int = 0
    warnings: ContractSyncWarnings = ContractSyncWarnings()


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
    # item-forms-accommodation-transport.md: копия extra_attrs исходной
    # purchase_items (см. app/models/contract_item.py).
    extra_attrs: dict = {}


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
    extra_attrs: Optional[dict] = None


class ContractItemOut(ContractItemBase):
    id: int
    purchase_id: int
    source_item_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
