from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class SubsidyContractorOverride(Base):
    __tablename__ = "subsidy_contractor_overrides"
    __table_args__ = (
        UniqueConstraint("subsidy_id", "contractor_id", name="uq_subsidy_contractor"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="CASCADE"), nullable=False)

    # Override fields — if set, these take precedence over contractor's defaults
    org_type = Column(String(50), nullable=True)
    inn = Column(String(20), nullable=True)
    kpp = Column(String(20), nullable=True)
    ogrn = Column(String(20), nullable=True)
    signatory = Column(String(255), nullable=True)
    signatory_basis = Column(String(500), nullable=True)
    address = Column(Text, nullable=True)
    postal_address = Column(Text, nullable=True)
    bank_details = Column(Text, nullable=True)
    settlement_account = Column(String(100), nullable=True)
    bank_name = Column(String(500), nullable=True)
    bik = Column(String(20), nullable=True)
    correspondent_account = Column(String(100), nullable=True)
    contact_person = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    org_phone = Column(String(50), nullable=True)
    org_email = Column(String(255), nullable=True)

    subsidy = relationship("Subsidy", back_populates="contractor_overrides")
    contractor = relationship("Contractor")
