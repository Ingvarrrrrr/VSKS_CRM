from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    full_name = Column(String(1000), nullable=True)
    inn = Column(String(20), nullable=True)
    kpp = Column(String(20), nullable=True)
    ogrn = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)
    signatory = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Multi-org / contour support
    root_org_id   = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    # Оргструктура «кто кому подчиняется» (редактор иерархии, стрелки орг→орг).
    # Отдельно от root_org_id (контур/видимость) — подчинение НЕ наследует видимость.
    parent_org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id",         ondelete="SET NULL"), nullable=True)
    # Phase 17.1-03 — single-entity link to Contractor (source of truth for legal requisites)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True, index=True)
    # Phase 29.3: HEX цвет организации для UI акцентов (напр. #1976d2)
    color = Column(String(20), nullable=True)
    # Phase 30: geo координаты штаба (station-mapping)
    lat = Column(Numeric(9, 6), nullable=True)
    lon = Column(Numeric(9, 6), nullable=True)
    region = Column(String(100), nullable=True)
    head_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    users      = relationship("User", back_populates="organization", foreign_keys="User.org_id")
    child_orgs = relationship("Organization", foreign_keys="Organization.root_org_id", lazy="selectin")
    contractor = relationship("Contractor", foreign_keys="Organization.contractor_id", lazy="joined")
