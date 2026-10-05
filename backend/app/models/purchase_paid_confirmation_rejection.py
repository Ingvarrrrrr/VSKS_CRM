"""Память об отклонённых парах «строка выписки — закупка» (доработка плана
2026-10-04-fadm-statement, п.3, после первого прохода).

Владелец: reject без памяти об отклонённой паре позволял следующему авто-
match-payments тут же снова привязать ТУ ЖЕ строку выписки к ТОЙ ЖЕ закупке и
переоткрыть тот же самый запрос подтверждения по кругу. Одна запись — одна
отклонённая пара (purchase_id, bank_payment_id); app/services/payment_lookup.py
(find_candidates/attach) читает её, чтобы не предлагать пару автоматически —
ручная привязка (attach-payments явным выбором человека) остаётся доступна,
помечается предупреждением в ответе (см. app/routers/purchase_payment_matching.py)."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PurchasePaidConfirmationRejection(Base):
    __tablename__ = "purchase_paid_confirmation_rejections"
    __table_args__ = (
        Index(
            "ux_paid_confirmation_rejection_pair",
            "purchase_id", "bank_payment_id",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Запрос, в ходе отклонения которого запомнена пара — только для аудита,
    # сама память переживает удаление запроса (SET NULL, не CASCADE).
    confirmation_id = Column(
        Integer, ForeignKey("purchase_paid_confirmations.id", ondelete="SET NULL"), nullable=True,
    )
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_payment_id = Column(Integer, ForeignKey("bank_payments.id", ondelete="CASCADE"), nullable=False, index=True)
    rejected_at = Column(DateTime(timezone=True), server_default=func.now())

    confirmation = relationship("PurchasePaidConfirmation")
