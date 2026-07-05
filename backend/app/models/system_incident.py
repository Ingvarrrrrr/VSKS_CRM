from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class SystemIncident(Base):
    __tablename__ = "system_incidents"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String(500), nullable=False)
    details = Column(Text, nullable=True)
    code = Column(String(100), nullable=True)
    correlation_id = Column(String(64), nullable=False, index=True)
    path = Column(String(500), nullable=True)
    method = Column(String(16), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
