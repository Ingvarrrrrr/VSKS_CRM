from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

# wishes.title — VARCHAR(500). Заголовок формируется на фронте из названий
# позиций; при множестве товаров он может превысить лимит → раньше падало
# INTERNAL_ERROR (StringDataRightTruncation). Клампим централизованно.
_TITLE_MAX = 500


def _clamp_title(v: Optional[str]) -> Optional[str]:
    if v and len(v) > _TITLE_MAX:
        return v[:_TITLE_MAX - 1] + "…"
    return v


def _blank_to_none(v):
    """Пустая строка из формы для опционального поля = «не заполнено» = None.
    Иначе pydantic роняет date/Decimal на '' с непонятным VALIDATION_ERROR."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class WishItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    item_name: str
    item_type: Optional[str] = "товар"
    quantity: Optional[float] = 1
    unit: Optional[str] = "шт"
    unit_price: Optional[float] = 0
    total_price: Optional[float] = 0
    country_origin: Optional[str] = "РФ"
    target_column_key: Optional[str] = None  # Phase 13 D-04: kanban column override
    feo_category_id: Optional[int] = None  # B9: per-item FEO category
    feo_planned_item_id: Optional[int] = None  # привязка к плановой позиции план-графика (mirrors PurchaseItem.feo_planned_item_id)
    needed_date: Optional[date] = None  # W2: дата потребности per-item
    vat_rate: Optional[str] = None  # per-item НДС ставка (mirrors PurchaseItem.vat_rate)
    over_plan: bool = False  # false — расходует план элемента ФЭО; true — сверх плана (mirrors PurchaseItem.over_plan)
    model_config = ConfigDict(from_attributes=True)


class WishItemPatch(BaseModel):
    """D-04: Patch payload for drag-drop column reassignment."""
    target_column_key: Optional[str] = None


class WishCreate(BaseModel):
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    event_id: Optional[int] = None
    assigned_to: Optional[int] = None
    feo_per_item: bool = False  # режим «своя категория ФЭО для каждого товара»
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin

    @field_validator('title')
    @classmethod
    def _v_title(cls, v):
        return _clamp_title(v)

    @field_validator('desired_date', 'quantity', 'estimated_price', mode='before')
    @classmethod
    def _v_blank(cls, v):
        return _blank_to_none(v)


class WishUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    event_id: Optional[int] = None
    assigned_to: Optional[int] = None
    # Optional[...] = None (не bool = False) намеренно: update_wish делает
    # body.model_dump(exclude_none=True) — default False затирал бы существующее
    # значение при каждом частичном PUT, не содержащем это поле.
    feo_per_item: Optional[bool] = None
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin

    @field_validator('title')
    @classmethod
    def _v_title(cls, v):
        return _clamp_title(v)

    @field_validator('desired_date', 'quantity', 'estimated_price', mode='before')
    @classmethod
    def _v_blank(cls, v):
        return _blank_to_none(v)


class WishReject(BaseModel):
    rejection_reason: str


class WishExecutionPatch(BaseModel):
    """B-exec: approver sets executor + execution deadline + event + assigned_to."""
    executor_id: Optional[int] = None
    execution_deadline: Optional[date] = None
    event_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    assigned_to: Optional[int] = None


class WishStatusForce(BaseModel):
    """Superadmin: force-set wish status (bypass workflow guards)."""
    status: str  # draft / submitted / approved / rejected / converted


class WishConvert(BaseModel):
    approved_quantity: Optional[Decimal] = None
    approved_price: Optional[Decimal] = None
    subsidy_id: Optional[int] = None


class WishOut(BaseModel):
    id: int
    org_id: int
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    approved_by: Optional[int] = None
    approver_name: Optional[str] = None
    purchase_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    subsidy_id: Optional[int] = None
    subsidy_name: Optional[str] = None
    feo_category_id: Optional[int] = None
    feo_per_item: bool = False  # режим «своя категория ФЭО для каждого товара»
    vat_mode: Optional[str] = None  # 'uniform' | 'per_item'
    event_id: Optional[int] = None
    event_name: Optional[str] = None
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    assigned_to_name: Optional[str] = None  # alias for legacy frontend
    executor_id: Optional[int] = None
    executor_name: Optional[str] = None
    execution_deadline: Optional[date] = None
    approval_mode: Optional[str] = None
    # «От кого»: имена участников заявки (WishMember), помимо автора
    member_names: List[str] = []
    # «Кому»: цепочка согласующих (WishApproval, по order_num)
    approver_names: List[str] = []
    # Все закупки, созданные из заявки (конвертация разбивает по категориям)
    purchase_ids: List[int] = []
    items: List[WishItemOut] = []
    # Phase 31: diff-tracking — unseen changes from other users
    unseen_fields: List[str] = []
    unseen_changes_count: int = 0
    # Предупреждение конвертации (например, удалённая категория ФЭО обнулена)
    convert_warning: Optional[str] = None
    # 'advance_report' = авто-заявка из авансового отчёта; NULL = обычная
    source: Optional[str] = None
    # W1: True если привязанная закупка перешла в Договор+ (редактирование запрещено)
    contracted_locked: bool = False

    class Config:
        from_attributes = True
