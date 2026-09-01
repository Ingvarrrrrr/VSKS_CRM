from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CommercialRequest(Base):
    __tablename__ = "commercial_requests"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(500), nullable=True)
    intro_text = Column(Text, nullable=True)
    delivery_date = Column(String(100), nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recipients = relationship(
        "CommercialRequestRecipient",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CommercialRequestRecipient(Base):
    __tablename__ = "commercial_request_recipients"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("commercial_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    contractor_id = Column(Integer, ForeignKey("contractors.id"), nullable=True)
    contractor_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    status = Column(String(50), default="prepared", nullable=False)

    request = relationship("CommercialRequest", back_populates="recipients")


class CommercialRequestOffer(Base):
    """Предложение (цена) полученное от получателя запроса КП (владелец, 2026-08-29).

    Заполняется вручную (PUT /api/commercial-requests/{id}/offers) после того, как
    контрагент прислал цену в ответ на запрос КП. POST .../accept помечает одно
    предложение принятым и актуализирует цену товара в каталоге (source='kp'),
    см. app/services/price_actualization.py.
    """
    __tablename__ = "commercial_request_offers"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("commercial_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("commercial_request_recipients.id", ondelete="CASCADE"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String(500), nullable=True)
    unit = Column(String(50), nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=True)
    is_accepted = Column(Boolean, default=False, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request = relationship("CommercialRequest")
    recipient = relationship("CommercialRequestRecipient")
