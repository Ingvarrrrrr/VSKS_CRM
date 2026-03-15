from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)

    subsidy = relationship("Subsidy", backref="events")
