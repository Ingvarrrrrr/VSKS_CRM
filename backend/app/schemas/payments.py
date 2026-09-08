"""Payments, receipts, and bank statements schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict
from datetime import date, datetime
from decimal import Decimal

_Date = date

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
    # Владелец (2026-08-19): «по нашим данным» vs «подтверждено казначейством» —
    # см. app/models/payment.py::Payment.payment_source/confirmed_by_statement.
    payment_source: str = "manual"
    confirmed_by_statement: bool = False
    # Этап 4/5/7: код расходов и основание платежа (app/services/payment_basis.py) —
    # проставляются при разнесении через payment_lookup.py::attach; нужны PaymentsBlock.vue
    # для отображения «Назначение / основание» и «Код расходов» в карточке закупки.
    expense_code: Optional[str] = None
    basis_kind: Optional[str] = None
    basis_number: Optional[str] = None
    basis_date: Optional[date] = None
    basis_key: Optional[str] = None
    basis_label: Optional[str] = None
    model_config = {"from_attributes": True}


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
    org_id: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    file_name: Optional[str] = None
    sheet_name: Optional[str] = None
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    rows_matched: int = 0
    rows_unmatched: int = 0
    rows_dup: int = 0
    rows_no_subsidy: int = 0
    status: str = "processing"
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BankPaymentOut(BaseModel):
    id: int
    import_id: Optional[int] = None
    org_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    external_doc_id: Optional[str] = None
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
    # Этап 3/7: код направления расходования целевых средств (КРЦС) — см.
    # app/services/payment_basis.py::expense_code; expense_code_name — расшифровка
    # из справочника expense_codes, простановлена в bank_statements.py::list_bank_payment_registry.
    expense_code: Optional[str] = None
    expense_code_name: Optional[str] = None
    # Этап 7в: «Куда отнесён» — закупки, на которые платёж РЕАЛЬНО разнесён через
    # Payment(matched_confirmed=true); может быть несколько при allocations-сплите.
    attached_purchases: Optional[List[Dict]] = None
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


