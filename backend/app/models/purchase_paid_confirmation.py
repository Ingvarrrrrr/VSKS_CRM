"""Запрос подтверждения перевода закупки в «Оплачено» (план 2026-10-04,
.planning/quick/2026-10-04-fadm-statement/PLAN.md, п.3).

Владелец: «нашлась закупка в выгрузке → в Оплаченные, но с уведомлением и
согласованием» — вместо молчаливого автоперевода в paid
(app/services/purchase_payments.py::recompute_purchase_payments, раньше
просто `p.status = "paid"`) заводится запрос; согласующий субсидии (см.
app/models/subsidy_approver.py::SubsidyApprover, достаточно одного) либо
superadmin/account_owner подтверждает или отклоняет — см.
app/routers/purchase_paid_confirmations.py. Статус закупки не меняется, пока
запрос pending.

Не больше ОДНОЙ pending-записи на закупку одновременно — частичный уникальный
индекс ниже; recompute_purchase_payments проверяет наличие pending-записи
перед созданием новой (ПРАВИЛО №6 — не плодить вторую на ту же закупку)."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PurchasePaidConfirmation(Base):
    __tablename__ = "purchase_paid_confirmations"
    __table_args__ = (
        Index(
            "ux_purchase_paid_confirmation_one_pending",
            "purchase_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    # Сумма, подтверждённая казначейской выпиской (Purchase.payment_amount) на
    # момент создания запроса — снимок, не живая ссылка: если платежи потом
    # изменятся, в запросе остаётся то, что видел согласующий при решении.
    amount_confirmed = Column(Numeric(15, 2), nullable=True)

    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    # pending / confirmed / rejected

    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, nullable=True)
    # Владелец (доработка «оплата из выписки — факт»): confirm НЕ блокируется
    # превышением плана по категории ФЭО (ни «план над ФЭО», ни «ТЗ/договор над
    # плановой позицией») — текст обойдённого превышения (если было) сохраняется
    # здесь в момент реального confirm (app/routers/purchase_paid_confirmations.py),
    # NULL — превышения не было. Для ЕЩЁ не решённых (pending) записей то же самое
    # считается «на лету» дорогим сухим прогоном (_simulate_confirm_chain) — сюда
    # не пишется, пока согласующий не нажал confirm.
    plan_excess_warning = Column(Text, nullable=True)

    purchase = relationship("Purchase")
    subsidy = relationship("Subsidy")
    decided_by_user = relationship("User", foreign_keys=[decided_by])
