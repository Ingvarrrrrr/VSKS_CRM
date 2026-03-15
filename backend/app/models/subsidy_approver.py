from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SubsidyApprover(Base):
    __tablename__ = "subsidy_approvers"

    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    role_name = Column(String(255), nullable=False)
    full_name = Column(String(500), nullable=False)
    order_num = Column(Integer, default=0)
    is_default = Column(Boolean, default=True)
    can_initiate = Column(Boolean, default=False)
    show_feo_path = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    subsidy = relationship("Subsidy", back_populates="approvers")
    user = relationship("User")
