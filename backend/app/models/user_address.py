from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class UserAddress(Base):
    """Кастомные адреса пользователя для автокомплита (delivery_location и т.п.)."""
    __tablename__ = "user_addresses"
    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_user_addr"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    address = Column(String(500), nullable=False)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
