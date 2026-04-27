from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    document_number = Column(String(100))
    payment_purpose = Column(String(500))
    payment_date = Column(Date)
    amount = Column(Numeric(15, 2))

    # Phase 22: источник платежа из банковской выписки
    bank_payment_id = Column(
        Integer,
        ForeignKey("bank_payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    # True после явного подтверждения пользователем матча выписка↔закупка
    matched_confirmed = Column(Boolean, default=False, nullable=False)

    contract = relationship("Contract")
    purchase = relationship("Purchase")
    bank_payment = relationship("BankPayment", back_populates="payments")
