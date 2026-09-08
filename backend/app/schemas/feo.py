"""FEO planned/actual items, comparisons, and budget history schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

_Date = date

# ── FeoPlannedItem ──────────────────────────────────────────────────────────

class FeoPlannedItemCreate(BaseModel):
    feo_category_id: int
    name: str
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    amount: Optional[Decimal] = None
    # Цена ЗА ЕДИНИЦУ (владелец, 2026-09-02) — см. докстринг FeoPlannedItem.unit_price
    # (app/models/feo_planned_item.py) и assert_tz_not_over_plan (app/services/
    # feo_plan.py): задана → amount = quantity × unit_price, план полноценный
    # (кол-во/цена/сумма проверяются); NULL → amount сама по себе итоговая сумма,
    # quantity ориентировочное, деление не выполняется.
    unit_price: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: bool = True
    # Блок 1 (план zany-fluttering-mountain.md): товар / услуга / работа —
    # нормализуется normalize_item_type() в app/routers/feo_planned_items.py.
    item_type: Optional[str] = None
    # W1b: payment schedule fields
    payment_mode: str = "one_time"
    planned_date: Optional[_Date] = None
    monthly_start_date: Optional[_Date] = None
    months_count: Optional[int] = None
    monthly_amount: Optional[Decimal] = None
    # Владелец (2026-08-12, «закупка сама становится планом»): порядок позиций
    # внутри категории — настраиваемый на входе (ручное «менять местами»).
    sort_order: Optional[int] = None
    # Жалоба владельца (сессия 2026-08-19): дедуп по (категория, имя) в
    # create_planned_item раньше молча возвращал существующую позицию и терял
    # введённые пользователем количество/сумму. Теперь дедуп отдаёт 409 с
    # выбором — этот флаг явно говорит «я осознанно создаю вторую позицию с
    # тем же именем» (напр. похожий товар с другим нанесением). Дефолт False —
    # прежнее поведение дедупа (но через 409, а не молча).
    allow_duplicate_name: bool = False
    # Происхождение плановой позиции (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ
    # галочки, не переключатель (см. докстринг миграции
    # aa1b2c3d4e5f_feo_planned_item_origin.py и модели FeoPlannedItem):
    # is_feo_breakdown — жёсткая построчная разбивка ФЭО реально есть, покупать
    # будут именно это; is_internal_plan — в ФЭО была только более широкая
    # категория (или позиции не было вовсе), состав придумали сами. Менять
    # может только тот, кто вправе править ФЭО (см. create_planned_item —
    # тихо игнорирует эти поля без вкладки feo_categories; update_planned_item
    # уже целиком за require_tab('feo_categories')). model_fields_set-паттерн,
    # как у item_type: если поле не пришло в PUT-payload — не трогаем (иначе
    # любой другой PUT этого роутера, не приславший поле явно, молча сбросил
    # бы уже выставленный признак в False).
    is_feo_breakdown: bool = False
    is_internal_plan: bool = False

class FeoPlannedItemOut(FeoPlannedItemCreate):
    id: int
    created_at: Optional[datetime] = None
    # Заведена автоматически (plan_autoassign.py), а не человеком — только
    # для отображения, НЕ принимается на вход (см. create_planned_item).
    auto_created: bool = False
    # Владелец (2026-08-18): «в позициях точно прописано, к чему относятся
    # данные позиции — товар/услуга/работа... почему не подтягиваются?».
    # Считаются ТОЛЬКО в GET /feo-planned-items/comparison (см. get_comparison) —
    # остальные эндпоинты, отдающие FeoPlannedItemOut, оставляют дефолты
    # (item_type_effective=None, item_type_inherited=False), т.к. у них нет
    # под рукой связанных purchase_items. Собственный item_type НЕ трогается —
    # это read-only вычисление, не запись (правило «выбранное не меняется само»).
    item_type_effective: Optional[str] = None  # свой item_type, иначе унаследованный от закупок, иначе None
    item_type_inherited: bool = False           # True — item_type_effective взят у связанных purchase_items
    model_config = {"from_attributes": True}


class FeoPlannedItemBulkCreate(BaseModel):
    """POST /feo-planned-items/bulk — создать несколько плановых позиций (Ур.5)
    одной атомарной транзакцией (жалоба владельца, сессия 2026-08-17: «Создать в
    плане закупок» создавала только ОДНУ позицию на всю НМЦД закупки вместо одной
    позиции на каждый товар). Каждая позиция списка может относиться к своей
    категории ФЭО (per-item режим) либо все — к одной (общий режим)."""
    items: List[FeoPlannedItemCreate]


class FeoPlannedItemBulkCreateResult(BaseModel):
    items: List[FeoPlannedItemOut]


class FeoStageOut(BaseModel):
    """Одна стадия жизненного цикла позиции для /feo-planned-items/comparison.

    Порядок стадий строго: feo → plan → purchase → contract → accepted.
    Стадия попадает в массив, только если у неё есть хоть какие-то данные —
    см. get_comparison() в feo_planned_items.py.
    """
    key: str            # 'feo' | 'plan' | 'purchase' | 'contract' | 'accepted'
    label: str           # «ФЭО» | «План» | «Что выставляли на закупку» | «Номенклатура подрядчика» | «Приняли»
    name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total: Optional[Decimal] = None


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
    wish_id: Optional[int] = None  # заявка, из которой заведена закупка (пусто — закупка заведена напрямую)
    contract_number: Optional[str] = None
    contractor_name: Optional[str] = None
    product_photo: Optional[str] = None
    # Требование владельца (2026-08-05): факт появляется с «Заказано», уточняется закрывающими
    # документами при «Поставлено»/«Оплачено». См. get_comparison() в feo_planned_items.py.
    final_unit_price: Optional[Decimal] = None   # позиция: цена по закрывающему документу
    final_total: Optional[Decimal] = None        # позиция: сумма по закрывающему документу
    acceptance_doc_amount: Optional[Decimal] = None  # закупка: сумма акта приёмки
    contract_price: Optional[Decimal] = None         # закупка: цена по договору
    purchase_items_count: Optional[int] = None       # всего позиций в этой закупке (для распределения)
    fact_amount: Optional[Decimal] = None             # вычисленная фактическая сумма (см. правила выше)
    fact_confirmed: bool = False                      # True — подтверждено актом приёмки (delivered/paid)
    fact_allocated: bool = False                       # True — сумма распределена пропорционально между позициями
    over_plan: bool = False                            # позиция «сверх плана» (не расходует лимит своего элемента)
    # Стадия «Приняли» — см. FeoStageOut / accepted stage
    accepted_name: Optional[str] = None
    accepted_quantity: Optional[Decimal] = None
    accepted_unit: Optional[str] = None
    stages: list[FeoStageOut] = []  # цепочка стадий feo→plan→purchase→contract→accepted, только заполненные
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


