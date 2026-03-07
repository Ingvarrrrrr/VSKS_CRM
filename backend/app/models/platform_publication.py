from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlatformPublication(Base):
    __tablename__ = "platform_publications"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)   # fabrikant / roseltorg_rb
    status = Column(String(30), nullable=False, default="pending")  # pending / publishing / published / error
    external_id = Column(String(200), nullable=True)   # ID лота на площадке
    external_url = Column(Text, nullable=True)         # ссылка на опубликованный лот
    error_text = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    purchase = relationship("Purchase", backref="publications")
