from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base


class ResponsiblePerson(Base):
    __tablename__ = "responsible_persons"

    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=True)
    full_name = Column(String(500), nullable=False)
    position = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
