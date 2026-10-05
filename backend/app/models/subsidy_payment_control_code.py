from sqlalchemy import Column, Integer, String, ForeignKey
from app.database import Base


class SubsidyPaymentControlCode(Base):
    """Коды расходов (ExpenseCode.code), по которым СВЕРКА «выписка ↔ закупки»
    (app/services/subsidy_payment_control.py) обязана найти закупку, для
    КОНКРЕТНОЙ субсидии (владелец, план .planning/quick/2026-10-05-payment-control/
    PLAN.md: «Статьи, по которым ищем закупку, — выбор субсидии»).

    Если для субсидии нет ни одной записи — действует умолчание: коды с
    ExpenseCode.is_procurement=true (см. subsidy_payment_control.get_search_codes).
    Наличие хотя бы одной записи означает «субсидия сделала явный выбор» — даже
    если выбор совпадает с умолчанием, записи сохраняются как сделанный выбор.
    """
    __tablename__ = "subsidy_payment_control_codes"

    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), primary_key=True)
    code = Column(String(10), primary_key=True)
