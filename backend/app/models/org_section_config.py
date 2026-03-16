from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from app.database import Base


class OrgSectionConfig(Base):
    __tablename__ = "org_section_configs"
    __table_args__ = (UniqueConstraint("org_id", "section_key", name="uq_org_section"),)

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    section_key = Column(String(50), nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)
