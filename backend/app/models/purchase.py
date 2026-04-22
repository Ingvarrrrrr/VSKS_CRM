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

    # Основание для оплаты: 'contract' | 'invoice' | 'invoice_contract'
    payment_basis_type = Column(String(30), nullable=True, default="contract")

    # Ссылка на родительскую закупку — если эту создали разбиением другой
    parent_purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True)

    feo_category = relationship("FeoCategory")
    contractor = relationship("Contractor")
    contract = relationship("Contract", back_populates="purchases")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    service_note_author = relationship("User", foreign_keys=[service_note_by])
    event = relationship("Event")
    total_nmck = Column(Numeric(15, 2))
    items = relationship("PurchaseItem", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
    files = relationship("PurchaseFile", back_populates="purchase",
                         cascade="all, delete-orphan", lazy="selectin")
    approvals = relationship("PurchaseApproval", back_populates="purchase",
                             cascade="all, delete-orphan", lazy="selectin",
                             order_by="PurchaseApproval.order_num")
