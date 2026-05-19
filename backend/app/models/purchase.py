from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, Date, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True, index=True)
    row_number = Column(Integer)
    purchase_number = Column(Integer)
    order_number = Column(String(100))
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id"))
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
    subsidy_id = Column(Integer, ForeignKey("subsidies.id"))
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
    payment_amount = Column(Numeric(15, 2))
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
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    task_comment = Column(Text, nullable=True)

    # Служебка (service note) — D-22
    service_note_text = Column(Text, nullable=True)
    service_note_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    service_note_at = Column(DateTime(timezone=True), nullable=True)

    # Приложение №3 fields
    treasury_code = Column(String(50), nullable=True)          # S: Казначейский код
    has_pretension = Column(Boolean, nullable=True, default=False)  # U: Претензионная работа

    # Сводная по продукции
    delivery_address = Column(Text, nullable=True)          # адрес доставки
    procurement_planned_date = Column(Date, nullable=True)  # планируемая дата закупки

    # Phase 26-K: доп. соглашение и дата заказа
    agreement_number = Column(String(100), nullable=True)   # № доп. соглашения
    agreement_date = Column(Date, nullable=True)             # Дата доп. соглашения
    order_date = Column(Date, nullable=True)                 # Дата заказа

    # Основание для оплаты: 'contract' | 'invoice' | 'invoice_contract'
    payment_basis_type = Column(String(30), nullable=True, default="contract")

    # Ссылка на родительскую закупку — если эту создали разбиением другой
    parent_purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True)

    # Авансовый отчёт: кому возмещать (сотрудник)
    reimbursement_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Phase 26-U-3: НДС режим — 'uniform' (одинаковый) или 'per_item' (для каждого товара)
    vat_mode = Column(String(20), nullable=True, default='uniform', server_default='uniform')

    # Phase 26-YY: snapshot-hash гейт для auto-recompute (SHA-1 от items+receipts).
    # Если current_hash == recompute_snapshot_hash → skip fuzzy/autocreate/dedup.
    recompute_snapshot_hash = Column(String(64), nullable=True)

    # Phase 28: форма договора для выбора нужного шаблона при генерации документа.
    # Значения: 'services_large' | 'services_small' | 'services_food' | 'goods_single'
    # | 'gph_individual' | 'gph_individual_rid' | 'repair_vehicle' | 'repair_framework'
    contract_form = Column(String(50), nullable=True)

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
    reimbursement_user = relationship("User", foreign_keys=[reimbursement_user_id])
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
