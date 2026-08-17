from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Wish(Base):
    __tablename__ = "wishes"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    category = Column(String(50), nullable=True)   # Товар / Услуга / Работа
    description = Column(Text, nullable=True)
    quantity = Column(Numeric(15, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    estimated_price = Column(Numeric(15, 2), nullable=True)
    link = Column(String(2000), nullable=True)      # URL reference
    priority = Column(String(20), nullable=True)    # low / medium / high / urgent
    desired_date = Column(Date, nullable=True)       # желаемый срок
    justification = Column(Text, nullable=True)
    status = Column(String(30), default="draft", nullable=False, index=True)
    rejection_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True)
    feo_category_id = Column(Integer, ForeignKey("feo_categories.id", ondelete="SET NULL"), nullable=True)
    # Контрагент заявки — необязательный (владелец, 2026-08-17): «должна быть
    # возможность указывать контрагента и его имя, но это по желанию».
    # contractor_id — ссылка на справочник (mirrors PurchaseItem.contractor_id);
    # contractor_name — просто имя от руки, когда контрагента в справочнике ещё
    # нет (mirrors PurchaseItem.contractor_name). Оба поля НЕ валидируются и не
    # блокируют сохранение/согласование/конвертацию.
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True)
    contractor_name = Column(String(500), nullable=True)
    # Режим «своя категория ФЭО для каждого товара» — раньше вычислялся эвристикой
    # на фронте (отдельно и по-разному для заявки и закупки) и слетал при конвертации.
    feo_per_item = Column(Boolean, nullable=False, default=False, server_default="false")
    # НДС режим — 'uniform' (одинаковый) или 'per_item' (для каждого товара), см. Purchase.vat_mode
    vat_mode = Column(String(20), nullable=True, default="uniform", server_default="uniform")
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    executor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Кто исполняет (ставит approver)
    execution_deadline = Column(Date, nullable=True)  # Срок исполнения (ставит approver)
    approval_mode = Column(String(20), nullable=False, default="sequential", server_default="sequential")  # sequential/parallel
    source = Column(String(30), nullable=True)  # 'advance_report' = авто-заявка из авансового; NULL = обычная

    # Остановка заявки (владелец, 2026-08-13): «Останавливать могут все» —
    # заявка не удаляется, а исчезает из плана закупок и перестаёт считаться в
    # ФЭО. Обратной операции (возобновление) нет — владелец её не просил.
    # См. app/routers/wishes.py::stop_wish, app/services/feo_plan.py.
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    stopped_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stopped_reason = Column(Text, nullable=True)
    # True — остановились НЕ все привязанные закупки (часть уже была на стадии
    # договора/заказано для рамочных — см. Purchase.stopped_at).
    stopped_partial = Column(Boolean, nullable=False, default=False, server_default="false")

    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    approver = relationship("User", foreign_keys=[approved_by], lazy="joined")
    assignee = relationship("User", foreign_keys=[assigned_to], lazy="selectin")
    executor = relationship("User", foreign_keys=[executor_id], lazy="selectin")
    stopped_by_user = relationship("User", foreign_keys=[stopped_by], lazy="selectin")
    purchase = relationship("Purchase", foreign_keys=[purchase_id])
    contractor = relationship("Contractor", foreign_keys=[contractor_id], lazy="selectin")
    subsidy = relationship("Subsidy", lazy="selectin")
    event = relationship("Event", foreign_keys=[event_id], lazy="selectin")
    items = relationship("WishItem", back_populates="wish", cascade="all, delete-orphan", lazy="selectin")
    approvals = relationship("WishApproval", back_populates="wish", cascade="all, delete-orphan", lazy="selectin", order_by="WishApproval.order_num")
