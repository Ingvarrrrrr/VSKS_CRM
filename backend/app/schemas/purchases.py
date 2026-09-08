"""Purchases and purchase items schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal

_Date = date

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
    # Снимок плана (Шаг 1 «план ≠ факт») — обычно заполняется сервером, но поле
    # оставлено настраиваемым на входе на случай явной установки (импорт/скрипт).
    planned_quantity: Optional[Decimal] = None
    planned_unit_price: Optional[Decimal] = None
    planned_total: Optional[Decimal] = None
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
    needed_date: Optional[_Date] = None  # W2: дата потребности per-item
    over_plan: bool = False  # false — расходует план элемента ФЭО; true — сверх плана
    # Стадия «Приняли» (5-я стадия жизненного цикла позиции): заполняется автоматически
    # при переходе закупки в delivered, правится вручную — см. purchase_transitions.py.
    accepted_name: Optional[str] = None
    accepted_quantity: Optional[Decimal] = None
    accepted_unit: Optional[str] = None

class PurchaseItemOut(PurchaseItemCreate):
    id: int
    product_name: Optional[str] = None
    product_photo_url: Optional[str] = None
    product_description: Optional[str] = None
    product_description_44fz: Optional[str] = None
    receipt_id: Optional[int] = None  # Phase 26-BB
    # Владелец (план crystalline-soaring-heron.md, п.4): остаток плановой позиции
    # этой строки закупки, с учётом ВСЕХ расходов (включая саму эту строку) —
    # отрицательное значение = превышение. Источник — FeoPlannedItem (Ур.5), если
    # позиция к ней привязана (feo_planned_item_id), иначе узел дерева ФЭО её
    # категории (см. GET /api/purchases/{id} — _attach_feo_excess_fields). None —
    # у позиции вовсе нет категории ФЭО (план посчитать не от чего).
    plan_residual: Optional[Decimal] = None
    plan_planned_amount: Optional[Decimal] = None
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
    purchase_method: Optional[str] = None  # 'single' | 'competitive' | 'advance'
    # Уточнение к purchase_method == 'competitive': 'price_request' | 'auction' | 'tender'
    competitive_form: Optional[str] = None
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
    # Структурированный адрес доставки (Фабрикант: место поставки)
    delivery_region: Optional[str] = None
    delivery_city: Optional[str] = None
    delivery_street: Optional[str] = None
    delivery_house: Optional[str] = None
    delivery_building: Optional[str] = None
    delivery_postcode: Optional[str] = None
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
    # Владелец (2026-08-19): «заявлено, ждёт подтверждения» — сумма ручных
    # неподтверждённых платежей, отдельно от payment_amount («оплачено» —
    # только подтверждённое казначейством). См. app/services/purchase_payments.py.
    payment_amount_declared: Optional[Decimal] = None
    payment_federal: Optional[Decimal] = None
    total_nmck: Optional[Decimal] = None
    purchase_contract_type: Optional[str] = None
    framework_seq: Optional[int] = None          # порядковый номер в рамочном договоре
    # Владелец (2026-08-31): технический номер договора (рамочная голова без
    # известных номера/даты) — True, пока номер не актуализирован пользователем.
    contract_number_is_temporary: Optional[bool] = False
    # Contract document generation fields
    vat_applicable: Optional[bool] = False
    vat_rate: Optional[int] = None
    vat_exemption_article: Optional[str] = None
    third_party_involved: Optional[bool] = False
    contract_end_date: Optional[date] = None
    commitment_quarter: Optional[int] = None
    planned_payment_month: Optional[date] = None
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
    feo_per_item: bool = False  # режим «своя категория ФЭО для каждого товара»
    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number: Optional[str] = None
    agreement_date: Optional[date] = None
    order_date: Optional[date] = None
    # Phase 28: форма договора для выбора шаблона при генерации
    contract_form: Optional[str] = None
    # Методичка (большая/малая/без), приклеивается к договору отдельно от формы
    methodology: Optional[str] = None
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
    # Phase 28 T6/T7: условные блоки шаблонов + протокол/приказ закупки
    delivery_by_supplier: Optional[bool] = True
    has_stages: Optional[bool] = False
    procurement_protocol_number: Optional[str] = None
    procurement_order_number: Optional[str] = None
    # Phase 29: связь с ТС
    vehicle_id: Optional[int] = None
    # ЭТП: ссылка на конкурсную процедуру
    etp_url: Optional[str] = None
    wish_id: Optional[int] = None  # Связь с заявкой; при авансовом создаётся авто-заявка
    # Fabrikant: срок оплаты и дата рассмотрения заявок
    payment_term_days: Optional[int] = None
    applications_review_date: Optional[date] = None
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
    # Уточнение к purchase_method == 'competitive': 'price_request' | 'auction' | 'tender'
    competitive_form: Optional[str] = None
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
    # Структурированный адрес доставки (Фабрикант: место поставки)
    delivery_region: Optional[str] = None
    delivery_city: Optional[str] = None
    delivery_street: Optional[str] = None
    delivery_house: Optional[str] = None
    delivery_building: Optional[str] = None
    delivery_postcode: Optional[str] = None
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
    payment_amount_declared: Optional[Decimal] = None
    payment_federal: Optional[Decimal] = None
    total_nmck: Optional[Decimal] = None
    purchase_contract_type: Optional[str] = None
    framework_seq: Optional[int] = None
    # Владелец (2026-08-31): технический номер договора (рамочная голова без
    # известных номера/даты) — True, пока номер не актуализирован пользователем.
    contract_number_is_temporary: Optional[bool] = None
    vat_applicable: Optional[bool] = None
    vat_rate: Optional[int] = None
    vat_exemption_article: Optional[str] = None
    third_party_involved: Optional[bool] = None
    contract_end_date: Optional[date] = None
    commitment_quarter: Optional[int] = None
    planned_payment_month: Optional[date] = None
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
    feo_per_item: Optional[bool] = None  # режим «своя категория ФЭО для каждого товара»
    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number: Optional[str] = None
    agreement_date: Optional[date] = None
    order_date: Optional[date] = None
    # Phase 28: форма договора для выбора шаблона при генерации
    contract_form: Optional[str] = None
    # Методичка (большая/малая/без), приклеивается к договору отдельно от формы
    methodology: Optional[str] = None
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
    # Phase 28 T6/T7: условные блоки шаблонов + протокол/приказ закупки
    delivery_by_supplier: Optional[bool] = None
    has_stages: Optional[bool] = None
    procurement_protocol_number: Optional[str] = None
    procurement_order_number: Optional[str] = None
    # Phase 29: связь с ТС
    vehicle_id: Optional[int] = None
    # ЭТП: ссылка на конкурсную процедуру
    etp_url: Optional[str] = None
    # Fabrikant: срок оплаты и дата рассмотрения заявок
    payment_term_days: Optional[int] = None
    applications_review_date: Optional[date] = None


# Владелец (2026-09-02): «уведомление глобально, если позиция категории ФЭО
# вверху и в каждом товаре не соответствует друг другу — об этом должен быть
# алярм прям стоять» — см. app.routers.purchases._compute_purchase_feo_mismatch.
# НЕ голый булев флаг: пользователь должен понять, ЧТО именно расходится.
class FeoMismatchItemOut(BaseModel):
    item_id: Optional[int] = None
    item_name: Optional[str] = None
    reason: str  # 'planned' | 'header' | 'both'
    message: str
    item_category_id: Optional[int] = None
    item_category_name: Optional[str] = None
    header_category_id: Optional[int] = None
    header_category_name: Optional[str] = None
    planned_item_id: Optional[int] = None
    planned_item_name: Optional[str] = None
    planned_category_id: Optional[int] = None
    planned_category_name: Optional[str] = None


class PurchaseOut(PurchaseCreate):
    id: int
    # Заявка-источник (конвертация заявки в закупки)
    wish_id: Optional[int] = None
    items: List[PurchaseItemOut] = []
    files: List[PurchaseFileOut] = []
    subsidy_allocations: Optional[List[SubsidyAllocationOut]] = None
    # Phase 31: diff-tracking — unseen changes from other users
    unseen_fields: List[str] = []
    unseen_changes_count: int = 0
    # Phase 31-04: contract sync — True when linked contract data differs from purchase copy
    contract_conflict: bool = False
    # Phase 32: quick access to file count from list view
    files_count: int = 0
    # Владелец (2026-08-12): значок «закупка создаёт превышение плана ФЭО» в списке
    # закупок — считается опционально (?with_feo_excess=true), см. list_purchases.
    # Дополнено планом crystalline-soaring-heron.md (п.4, 2026-08-21): теперь
    # считается и в карточке закупки (GET /api/purchases/{id}), не только в
    # списке — см. app.routers.purchases._compute_purchase_feo_excess.
    feo_excess: bool = False
    feo_excess_hint: Optional[str] = None
    feo_excess_amount: Optional[Decimal] = None
    feo_excess_category: Optional[str] = None
    # Владелец (2026-09-03): id категории-виновника — НЕ гейтится правом
    # feo_budget.view_leaf (в отличие от FeoCategory.budget), см. докстринг
    # _compute_purchase_feo_excess. Фронт сверяет его с item.feo_category_id, чтобы
    # без права показать в позиции закупки только факт и размер превышения статьи.
    feo_excess_category_id: Optional[int] = None
    # "none" — превышения нет; "not_requested" — есть, согласование не запрошено;
    # "pending" — запрос на согласование превышения ФЭО на рассмотрении;
    # "approved" — согласовано (feo_excess при этом остаётся True — согласование
    # НЕ прячет сам факт превышения, см. докстринг _compute_purchase_feo_excess).
    feo_excess_state: str = "none"
    feo_excess_approved_by: Optional[str] = None
    feo_excess_approved_at: Optional[str] = None
    # Название родительской заявки (Wish.title) — «Создана из заявки №N «…»»
    # на карточке закупки (wish_id уже был на PurchaseOut, см. ниже).
    wish_title: Optional[str] = None
    # Статус родительской заявки (Wish.status: draft/submitted/approved/rejected/
    # converted) — владелец (2026-08-21, дефект «отцеплённая закупка»): карточка
    # закупки, скрытой в статусе 'wishes', обязана прямо объяснять, что с ней —
    # ждёт одобрения или отцеплена обратно в черновик (см. wish_id/wish_title,
    # используется вместе на карточке; см. get_purchase в purchases.py).
    wish_status: Optional[str] = None
    # Остановка закупки (владелец, 2026-08-13) — read-only, системой проставляется
    # в POST /api/wishes/{wish_id}/stop, НЕ через PUT/PATCH закупки напрямую
    # (намеренно отсутствует в PurchaseCreate/PurchaseUpdate — см. update_purchase
    # payload_dict/exclude_unset и PATCHABLE_FIELDS в purchases.py).
    stopped_at: Optional[datetime] = None
    stopped_by: Optional[int] = None
    stopped_by_name: Optional[str] = None
    stopped_wish_id: Optional[int] = None
    # Владелец (2026-09-02): расхождение категории ФЭО шапки/позиции/плановой
    # позиции — считается ВСЕГДА (см. _compute_purchase_feo_mismatch), в списке
    # достаточно признака для метки строки, в карточке нужен разбор по позициям.
    feo_mismatch: bool = False
    feo_mismatch_items: List[FeoMismatchItemOut] = []
    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # см. app.services.feo_plan.assert_no_unapproved_excess. Список предупреждений
    # о превышении плана ФЭО узла над его финансированием, собранных ИМЕННО этим
    # действием (создание/правка закупки, форвард-переход стадии) — для НЕМЕДЛЕННОЙ
    # обратной связи (тост), тот же паттерн, что excess_warnings в ответах
    # app.routers.wishes (decide/approve/convert). Пусто, если превышения нет —
    # persistent-источник истины на будущее остаётся feo_excess/feo_excess_* выше
    # (считается заново на КАЖДОМ GET независимо от того, кто и когда создал
    # превышение).
    excess_warnings: List[dict] = []
    model_config = {"from_attributes": True}

    @model_validator(mode='after')
    def _derive_acceptance_doc_scalars(self):
        """ПРАВИЛО №6 (2026-09-07, группа D4): acceptance_doc_name/date/number/
        amount больше НЕ пишутся в БД (источник истины — JSONB acceptance_docs,
        см. app.services.acceptance_docs) — но фронт продолжает их читать как
        обычные поля закупки, поэтому сериализатор ВЫЧИСЛЯЕТ их здесь из
        acceptance_docs (первый документ), с фолбэком на уже прочитанные из
        ORM legacy-скаляры для немигрированных закупок (acceptance_docs пуст).
        Единая логика с app.services.acceptance_docs.derived_scalars — не
        вторая копия («первый документ»/фолбэк совпадают дословно)."""
        from app.services.acceptance_docs import derived_scalars
        derived = derived_scalars(self)
        self.acceptance_doc_name = derived["name"]
        self.acceptance_doc_number = derived["number"]
        self.acceptance_doc_date = derived["date"]
        self.acceptance_doc_amount = derived["amount"]
        return self

class PurchaseAmountsOut(BaseModel):
    """ПРАВИЛО №6 (2026-09-05): единственный расчёт «суммы закупки» — см.
    app/services/purchase_amounts.py::purchase_amounts. plan/contract/fact/
    paid — сырые колонки Purchase (planned_total_price/contract_price/
    acceptance_doc_amount/payment_amount) БЕЗ фолбэков, для случаев, когда
    фронту нужно показать именно исходное поле, а не итог. effective — сумма
    по цепочке фолбэков владельца (см. докстринг purchase_amounts.py);
    effective_source — имя поля/формулы, откуда взято effective (отладка)."""
    plan: Optional[Decimal] = None
    contract: Optional[Decimal] = None
    fact: Optional[Decimal] = None
    paid: Optional[Decimal] = None
    effective: Optional[Decimal] = None
    effective_source: str


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
    # Владелец (2026-09-03): True только для рамочной ГОЛОВЫ договора (см.
    # app/routers/purchases.py::is_framework_head) — фронт использует это,
    # чтобы показать блок «Согласование необходимости договора» независимо
    # от статуса закупки/approval_status (см. CreateOrderView.vue::
    # showApprovalSection).
    is_framework_head: bool = False
    # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки — см. PurchaseAmountsOut.
    # Optional/None только если вызывающий код не передал amounts_map (защита от
    # регрессии на путях, которые ещё не переведены — не должно случаться на
    # GET /api/purchases и GET /api/purchases/{id}, см. _purchase_to_full).
    amounts: Optional[PurchaseAmountsOut] = None

