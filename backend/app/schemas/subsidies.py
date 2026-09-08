"""Subsidies, responsible persons, approvers, and FEO categories schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal

_Date = date

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
    # Требовать дату потребности у позиций (для помесячного плана)
    require_planned_dates: bool = True
    # Fabrikant: номер соглашения о субсидии
    agreement_number: Optional[str] = None
    # Владелец (2026-08-30): порог предупреждения о подходе к потолку субсидии (%)
    ceiling_warn_percent: Optional[float] = None

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
    require_planned_dates: Optional[bool] = None
    # Fabrikant: номер соглашения о субсидии
    agreement_number: Optional[str] = None
    # Владелец (2026-08-30): порог предупреждения о подходе к потолку субсидии (%)
    ceiling_warn_percent: Optional[float] = None

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
    # Phase 31-05: canonical budget fields (D-14..D-17)
    remaining: Optional[float] = None          # limit - spent (calculated_budget_from_categories - Σ purchases)
    planned_amount: Optional[float] = None     # Σ FeoPlannedItem.amount (ФЭО плановая сумма)
    budget_discrepancy: Optional[float] = None  # limit - planned_amount (Δ ФЭО vs плановая)
    require_planned_dates: bool = True
    # Fabrikant: номер соглашения о субсидии
    agreement_number: Optional[str] = None
    # Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
    # потолку субсидии». ceiling_warn_percent — настраиваемый порог (хранится
    # в БД, умолчание 90 применяется в сервисе если NULL). Остальные поля —
    # расчёт на лету, см. app.services.feo_plan.calculate_ceiling_forecast*:
    #   ceiling_total            — потолок (calculate_budget_from_categories,
    #                              тот же источник, что и жёсткий гейт
    #                              PLAN_OVER_SUBSIDY_CEILING)
    #   ceiling_committed_total  — «сумма заказанного»: разовые/авансовые/
    #                              рамочные закупки в статусах Заказано+, ПЛЮС
    #                              ежемесячные платежи ВЕСЬ график целиком
    #   ceiling_committed_percent — committed / ceiling * 100
    #   ceiling_near_warning     — percent >= ceiling_warn_percent (и ceiling > 0)
    #   ceiling_exceeded         — committed > ceiling (потолок уже превышен)
    ceiling_warn_percent: Optional[float] = None
    ceiling_total: Optional[float] = None
    ceiling_committed_total: Optional[float] = None
    ceiling_committed_one_off: Optional[float] = None   # разовые/авансовые/рамочные (статусы Заказано+)
    ceiling_committed_monthly: Optional[float] = None   # ежемесячные платежи, весь график целиком
    ceiling_committed_percent: Optional[float] = None
    ceiling_near_warning: bool = False
    ceiling_exceeded: bool = False
    # Черновые субсидии (план C1/C2): статус 'draft' | 'approved', автор,
    # утвердивший и когда — чтобы фронт показал чип статуса и кнопку «Утвердить».
    status: str = 'draft'
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class SubsidyContractorOverrideCreate(BaseModel):
    org_type: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    signatory: Optional[str] = None
    signatory_position: Optional[str] = None
    signatory_last_name: Optional[str] = None
    signatory_first_name: Optional[str] = None
    signatory_middle_name: Optional[str] = None
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
    # Дефект 2026-08-31 (владелец, форма «Редактировать направление ФЭО»): фронт
    # иногда шлёт пустую строку вместо null для очищенного числового поля (напр.
    # v-model.number на Vuetify оставляет '' как есть, если поле не парсится в
    # число) — pydantic валит это 422 «ожидается число» с техническим именем поля
    # (fields без русской подписи в field_labels в app/__init__.py). Пустая строка
    # для ЧИСЛОВОГО поля этой схемы = «не задано», а не ошибка — нормализуем в None
    # ДО валидации типов, тем же паттерном, что и ContractorCreate.empty_strings_to_none
    # ниже. Фронт всё равно должен слать null (см. SubsidiesView.vue), это —
    # защита от повторения, не замена фикса на фронте.
    @model_validator(mode='before')
    @classmethod
    def empty_numeric_strings_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in (
                'budget', 'feo_quantity', 'feo_amount',
                'planned_quantity', 'planned_amount', 'manual_plan_amount',
            ):
                if data.get(key) == '':
                    data[key] = None
        return data

    parent_id: Optional[int] = None
    subsidy_id: int
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None
    budget: Optional[float] = None
    feo_quantity: Optional[float] = None
    feo_unit: Optional[str] = None
    feo_amount: Optional[float] = None
    planned_quantity: Optional[float] = None
    planned_amount: Optional[float] = None
    unit: Optional[str] = None
    # Владелец, план zany-fluttering-mountain.md (2026-08-13): переключатель способа
    # расчёта плана — см. app/models/feo_category.py. Дефолт строкой (не None) —
    # колонка NOT NULL, а FastAPI/pydantic отправляет явный None при пропуске поля
    # старым клиентом, что уронило бы INSERT/UPDATE constraint-нарушением.
    plan_source: str = "planned_items"
    manual_plan_amount: Optional[float] = None

class FeoCategoryOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    subsidy_id: int
    level: int
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None
    budget: Optional[float] = None
    feo_quantity: Optional[float] = None
    feo_unit: Optional[str] = None
    feo_amount: Optional[float] = None
    planned_quantity: Optional[float] = None
    planned_amount: Optional[float] = None
    unit: Optional[str] = None
    plan_source: str = "planned_items"
    manual_plan_amount: Optional[float] = None
    # Задача владельца «план ≠ факт» (шаг D, сессия 2026-08-06): непустое — только
    # когда PUT /feo-categories/{id} заподозрил, что в planned_amount (цена ЗА
    # ЕДИНИЦУ) записана СУММА (защита от повторения К1, см. update_category).
    # Ничего не блокирует, чисто предупреждение для UI.
    warning: Optional[str] = None
    model_config = {"from_attributes": True}

class FeoCategoryTree(FeoCategoryOut):
    children: List["FeoCategoryTree"] = []

