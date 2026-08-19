from datetime import date as _date
from sqlalchemy import Column, Integer, SmallInteger, String, Numeric, Boolean, ForeignKey, Date, Text, DateTime, event, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.attributes import set_committed_value
from app.database import Base

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True, index=True)
    row_number = Column(Integer)
    purchase_number = Column(Integer)
    order_number = Column(String(100))
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"))
    item_type = Column(String(20))
    item_name = Column(String(500))
    contractor_id = Column(Integer, ForeignKey("contractors.id"))
    planned_quantity = Column(Numeric(15, 4))
    unit = Column(String(50))
    planned_unit_price = Column(Numeric(15, 2))
    planned_total_price = Column(Numeric(15, 2))
    confirmed = Column(Boolean, default=False)
    final_unit_price = Column(Numeric(15, 2))
    final_total_amount = Column(Numeric(15, 2))
    delivery_payment_amount = Column(Numeric(15, 2))
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"))
    status = Column(String(30), default="wishes")
    substatus = Column(String(30), nullable=True)          # tz_forming / kp_collecting / on_platform
    is_monthly_payment = Column(Boolean, default=False)    # ежемесячный платёж
    monthly_payment_count = Column(Integer, nullable=True)   # кол-во ежемесячных платежей
    monthly_payment_amount = Column(Numeric(15, 2), nullable=True)  # сумма одного платежа
    is_likely_needed = Column(Boolean, default=True, nullable=True)   # «Скорее всего понадобится»
    is_prepayment = Column(Boolean, default=False, nullable=True)     # Предоплата
    prepayment_date = Column(Date, nullable=True)                      # Дата возникновения обязательств для предоплаты
    stage_label = Column(String(100), nullable=True)                   # Подпись этапа (напр. «Февраль 2026»)

    # Phase 1: new fields
    contract_number = Column(String(100))
    contract_date = Column(Date)
    registry_number = Column(String(100))
    purchase_method = Column(String(50))  # 'single' | 'competitive'
    nmck = Column(Numeric(15, 2))
    contract_price = Column(Numeric(15, 2))
    economy = Column(Numeric(15, 2))
    price_increase = Column(Numeric(15, 2))
    execution_term = Column(Date)
    execution_term_changed = Column(Date)
    delivery_date = Column(Date)
    country_origin = Column(String(100))
    subject = Column(String(500))
    acceptance_doc_name = Column(String(200))
    acceptance_doc_date = Column(Date)
    acceptance_doc_number = Column(String(100))
    acceptance_doc_amount = Column(Numeric(15, 2))
    acceptance_docs = Column(JSONB, default=list)  # [{name, number, date, amount}, ...]
    payment_doc_number = Column(String(100))
    payment_doc_date = Column(Date)
    # Сумма ПОДТВЕРЖДЁННЫХ казначейством платежей ("оплачено") — считается по
    # payments.confirmed_by_statement=True, см. app/services/purchase_payments.py.
    payment_amount = Column(Numeric(15, 2))
    # Владелец (2026-08-19): сумма РУЧНЫХ неподтверждённых платежей ("отмечено
    # человеком, ждёт подтверждения выпиской") — считается по payments с
    # payment_source='manual' AND confirmed_by_statement=False. НЕ участвует в
    # авто-переходе закупки в статус paid (см. recompute_purchase_payments).
    payment_amount_declared = Column(Numeric(15, 2))
    payment_federal = Column(Numeric(15, 2))
    purchase_contract_type = Column(String(50), nullable=True)  # single / framework_cumulative / framework_with_amount
    framework_seq = Column(Integer, nullable=True)              # порядковый номер закупки в рамках рамочного договора
    purchase_basis = Column(String(50), nullable=True)  # 'plan_schedule' | 'service_note'
    responsible_person = Column(String(500), nullable=True)
    # Contract document generation fields
    vat_applicable = Column(Boolean, nullable=True, default=False)       # НДС применяется
    vat_rate = Column(Integer, nullable=True)                             # Ставка НДС (20, 10)
    vat_exemption_article = Column(String(200), nullable=True)           # Статья НК РФ
    third_party_involved = Column(Boolean, nullable=True, default=False)  # Привлечение третьих лиц
    contract_end_date = Column(Date, nullable=True)                      # срок действия договора
    service_period_type = Column(String(10), nullable=True)              # 'period' | 'date'
    service_start_date = Column(Date, nullable=True)                     # начало периода / разовая дата
    service_end_date = Column(Date, nullable=True)                       # конец периода
    description_mode = Column(String(10), default="exact")               # 'exact' | '44fz'
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)

    # Approval
    approval_status = Column(String(30), nullable=True)  # None / in_progress / approved / rejected
    approval_mode = Column(String(20), nullable=True, default="sequential")  # sequential / parallel
    approval_sign_type = Column(String(20), nullable=True, default="electronic")  # electronic / paper

    # Kanban / task assignment
    assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    task_comment = Column(Text, nullable=True)

    # Служебка (service note) — D-22
    service_note_text = Column(Text, nullable=True)
    service_note_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    service_note_at = Column(DateTime(timezone=True), nullable=True)

    # Приложение №3 fields
    treasury_code = Column(String(50), nullable=True)          # S: Казначейский код
    has_pretension = Column(Boolean, nullable=True, default=False)  # U: Претензионная работа

    # Сводная по продукции
    delivery_address = Column(Text, nullable=True)          # адрес доставки (свободная строка / фолбэк)
    # Структурированный адрес доставки (Фабрикант: место поставки)
    delivery_region = Column(String(100), nullable=True)    # субъект РФ доставки (→ ОКАТО / фед.округ)
    delivery_city = Column(String(200), nullable=True)      # город / населённый пункт
    delivery_street = Column(String(300), nullable=True)    # улица
    delivery_house = Column(String(50), nullable=True)      # дом
    delivery_building = Column(String(50), nullable=True)   # корпус / строение
    delivery_postcode = Column(String(20), nullable=True)   # почтовый индекс
    procurement_planned_date = Column(Date, nullable=True)  # планируемая дата закупки

    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number = Column(String(100), nullable=True)   # № доп. соглашения
    agreement_date = Column(Date, nullable=True)             # Дата доп. соглашения
    order_date = Column(Date, nullable=True)                 # Дата заказа

    # Основание для оплаты: 'contract' | 'invoice' | 'invoice_contract'
    payment_basis_type = Column(String(30), nullable=True, default="contract")

    # Ссылка на родительскую закупку — если эту создали разбиением другой
    parent_purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True)

    # Связь с заявкой-источником (Wish), из которой эта закупка была распределена.
    # Распределённая заявка переходит в status='converted' и уходит из «Заявок» в «Закупки».
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="SET NULL"), nullable=True, index=True)

    # Остановка закупки (владелец, 2026-08-13) — каскадом от остановки заявки
    # (app/routers/wishes.py::stop_wish): останавливается закупка, ещё не
    # дошедшая до договора (для рамочных — ещё не «Заказано»). Не удаляется —
    # сохраняется история. stopped_wish_id — какая именно заявка её остановила.
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    stopped_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stopped_wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="SET NULL"), nullable=True)

    # Авансовый отчёт: кому возмещать (сотрудник)
    reimbursement_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Служебная записка: адресат (кому)
    service_note_to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Phase 26-U-3: НДС режим — 'uniform' (одинаковый) или 'per_item' (для каждого товара)
    vat_mode = Column(String(20), nullable=True, default='uniform', server_default='uniform')

    # Режим «своя категория ФЭО для каждого товара» — раньше вычислялся эвристикой
    # на фронте (отдельно и по-разному для заявки и закупки) и слетал при конвертации.
    feo_per_item = Column(Boolean, nullable=False, default=False, server_default='false')

    # Phase 26-YY: snapshot-hash гейт для auto-recompute (SHA-1 от items+receipts).
    # Если current_hash == recompute_snapshot_hash → skip fuzzy/autocreate/dedup.
    recompute_snapshot_hash = Column(String(64), nullable=True)

    # Phase 28: форма договора для выбора нужного шаблона при генерации документа.
    # Значения: 'services_large' | 'services_small' | 'services_food' | 'goods_single'
    # | 'gph_individual' | 'gph_individual_rid' | 'repair_vehicle' | 'repair_framework'
    contract_form = Column(String(50), nullable=True)

    # Phase 29 D-18: связь с ТС (nullable FK, ON DELETE SET NULL)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)

    # ЭТП: ссылка на конкурсную процедуру (заполнена → закупка проводилась через ЭТП)
    etp_url = Column(Text, nullable=True)

    # Квартал принятия обязательств (1-4)
    commitment_quarter = Column(SmallInteger, nullable=True)
    # Планируемый месяц платежа (хранится первое число месяца)
    planned_payment_month = Column(Date, nullable=True)

    # Fabrikant: срок оплаты в днях
    payment_term_days = Column(Integer, nullable=True)
    # Fabrikant: дата рассмотрения заявок (asyncpg требует date-объект, не строку — в _DATE_FIELDS)
    applications_review_date = Column(Date, nullable=True)

    # Phase 28: гарантия договора + ретроактивный флаг (комментарии пользователя 2026-05-19)
    warranty_period_days = Column(Integer, nullable=True)   # срок гарантии товара/услуги в раб.днях (для договора)
    is_retroactive = Column(Boolean, nullable=False, server_default='false')  # договор задним числом — применяется ст. 425 ГК блок

    # Phase 28: contract-specific поля (условия конкретного договора)
    acceptance_term_days = Column(Integer, nullable=True)         # срок приёмки товара (поставка)
    penalty_rate = Column(Numeric(5, 3), nullable=True)           # неустойка в процентах (например 0.1 = 0.1%/день)
    contractor_ogrnip_date = Column(Date, nullable=True)          # дата присвоения ОГРНИП (договор ремонт ТС с ИП)
    repair_request_number = Column(String(50), nullable=True)     # номер заявки на ремонт (рамочный)
    commission_member_1_name = Column(String(200), nullable=True) # член закупочной комиссии 1
    commission_member_2_name = Column(String(200), nullable=True) # член комиссии 2
    commission_member_3_name = Column(String(200), nullable=True) # член комиссии 3
    advance_amount = Column(Numeric(15, 2), nullable=True)        # сумма аванса (для актов «большой отчётности»)

    # Phase 28 T6/T7: условные блоки шаблонов + протокол/приказ закупки
    delivery_by_supplier = Column(Boolean, nullable=False, server_default='true')   # True=поставщик доставляет, False=самовывоз
    has_stages = Column(Boolean, nullable=False, server_default='false')            # True=в Приложении №1 есть этапы оказания услуг
    procurement_protocol_number = Column(String(100), nullable=True)                # номер протокола закупочной комиссии
    procurement_order_number = Column(String(100), nullable=True)                   # номер приказа о закупке

    # Phase 19: template fields for docx context ---------------------------
    submission_deadline = Column(DateTime, nullable=True)          # дата+время завершения приёма заявок
    delivery_location = Column(String(500), nullable=True)          # место оказания услуг / доставки
    delivery_location_kind = Column(String(20), nullable=True)      # '' | 'delivery' | 'service' (ручной тогл лейбла, фидбек 5 мая)
    region = Column(String(200), nullable=True)                      # Регион проведения мероприятия (89 субъектов РФ или спец-значения)
    service_term_mode = Column(String(20), nullable=True)           # 'range' | 'duration' | 'deadline'
    # service_start_date / service_end_date already declared above (Phase 1) — reused for mode='range'
    service_term_days = Column(Integer, nullable=True)              # N дней для mode='duration'
    service_term_type = Column(String(20), nullable=True)           # 'calendar' | 'working' для mode='duration'
    service_deadline_date = Column(Date, nullable=True)             # до даты включительно для mode='deadline'

    feo_category = relationship("FeoCategory")
    contractor = relationship("Contractor")
    contract = relationship("Contract", back_populates="purchases")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    service_note_author = relationship("User", foreign_keys=[service_note_by])
    stopped_by_user = relationship("User", foreign_keys=[stopped_by])
    reimbursement_user = relationship("User", foreign_keys=[reimbursement_user_id])
    service_note_to_user = relationship("User", foreign_keys=[service_note_to_user_id])
    event = relationship("Event")
    total_nmck = Column(Numeric(15, 2))
    items = relationship("PurchaseItem", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
    contract_items = relationship(
        "ContractItem",
        back_populates="purchase",
        cascade="all, delete-orphan",
        lazy="selectin",
    )  # Phase 27.1: фактически заказанные позиции по договору (D-11)
    files = relationship("PurchaseFile", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
    approvals = relationship("PurchaseApproval", back_populates="purchase",
                             cascade="all, delete-orphan", lazy="selectin",
                             order_by="PurchaseApproval.order_num")


def _registry_number_for(purchase_id: int) -> str:
    """Единый формат номера — тот же, что раньше жил только в purchases.py (~стр. 1339-1341)
    и в бэкфилле app/__init__.py (Phase 26-BBB). Год берётся из текущей даты, т.к. в модели
    нет created_at."""
    return f"РЕЕ-{_date.today().year}-{purchase_id:05d}"


@event.listens_for(Session, "after_flush")
def _assign_purchase_registry_number(session, flush_context):
    """Жалоба владельца (2026-08-13): закупка «Закупка огнетушителей ОУ-2 в Москву»,
    созданная конвертацией заявки, осталась БЕЗ реестрового номера — искать/привязать
    её было нельзя. Причина: registry_number присваивался только вручную, одной строкой
    в purchases.py (POST /api/purchases, ~стр. 1339-1341), сразу после db.flush(). Но
    объекты Purchase(...) создаются минимум в семи местах (wishes.py x2 — конвертация
    заявки и есть источник этого бага, purchases.py x2, contracts.py, purchase_export.py,
    purchase_items_import.py) — точечная правка в одном месте гарантированно забудется
    в следующем (и в любом будущем). Поэтому гарантия перенесена на уровень модели/сессии:
    ЛЮБАЯ новая запись Purchase без registry_number получает номер сразу после INSERT,
    независимо от пути создания.

    Технически: after_flush видит объекты Purchase в session.new ПОСЛЕ того, как для них
    уже выполнен INSERT (id заполнен autoincrement'ом), но ДО того, как flush полностью
    завершится — документированное место для доп. SQL в той же транзакции
    (docs.sqlalchemy.org/en/20/orm/session_events.html#after-flush). Обновление идёт
    через core UPDATE на session.connection() (не через ORM-атрибут — это не триггерит
    повторный autoflush/рекурсию), а значение в самом Python-объекте синхронизируется
    через set_committed_value, чтобы объект НЕ считался «грязным» и не улетел лишним
    UPDATE на следующем flush/commit.

    Импорт из Excel и любой другой путь, где registry_number уже проставлен явно, —
    пропускается: чужой номер главнее (он мог прийти из внешней системы).

    AsyncSession оборачивает синхронную Session — слушать нужно именно её (см.
    docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#synopsis-orm), поэтому
    listener навешан глобально на sqlalchemy.orm.Session, а не на конкретный класс.
    """
    new_purchases = [
        obj for obj in session.new
        if isinstance(obj, Purchase) and not getattr(obj, "registry_number", None)
    ]
    if not new_purchases:
        return
    connection = session.connection()
    for p in new_purchases:
        if p.id is None:
            continue  # не должно случиться после INSERT, но не падать в этом случае
        number = _registry_number_for(p.id)
        connection.execute(
            update(Purchase.__table__)
            .where(Purchase.__table__.c.id == p.id)
            .values(registry_number=number)
        )
        set_committed_value(p, "registry_number", number)
