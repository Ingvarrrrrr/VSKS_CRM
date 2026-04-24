from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship, backref
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

    request_type = Column(String(50), nullable=True)       # auction / competition / price_request / monitoring
    auction_date = Column(DateTime(timezone=True), nullable=True)  # дата розыгрыша

    # Phase 17.1-07 hotfix: cascade delete + passive_deletes so SQLAlchemy does not
    # try to NULL-out purchase_id on Purchase deletion (FK is NOT NULL).
    # DB-level CASCADE handles row removal.
    purchase = relationship(
        "Purchase",
        backref=backref(
            "publications",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
