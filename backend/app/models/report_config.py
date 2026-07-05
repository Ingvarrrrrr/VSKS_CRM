from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class ReportConfig(Base):
    __tablename__ = 'report_configs'
    __table_args__ = (
        UniqueConstraint('org_id', 'name', 'kind', name='uq_report_configs_org_name_kind'),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # 'list' | 'pivot' | 'dashboard'
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    config_json = Column(JSONB, nullable=False, default=dict)
    parameters_json = Column(JSONB, nullable=False, default=list)  # [{key, label, type, default, required}]
    created_by_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_default = Column(Boolean, nullable=False, default=False)
    is_shared = Column(Boolean, nullable=False, default=True)  # видима для всех в org, false = только автору
