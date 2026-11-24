from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class CellMark(Base):
    """Server-side storage for cell/row highlights and attached comments.

    entity_type: 'feo_item' | 'feo_category' | 'purchase' | 'wish' | 'task' | 'contract' | 'payment' | 'vehicle'
    field_name: '*' for entire row, or specific column/field name
    group_id: UUID4 uniting cells/rows marked together in a single batch
    visibility: 'shared' (visible to everyone with access) | 'private' (visible only to creator)
    is_resolved: False (active) | True (resolved question, preserved in DB for history)
    """
    __tablename__ = "cell_marks"
    __table_args__ = (
        Index("ix_cell_marks_lookup", "entity_type", "entity_id", "field_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(String(36), nullable=False, index=True)
    entity_type = Column(String(40), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    field_name = Column(String(80), nullable=False, server_default="*", default="*")
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=True, index=True)
    color = Column(String(24), nullable=True)
    comment = Column(Text, nullable=True)
    visibility = Column(String(16), nullable=False, server_default="shared", default="shared")
    is_resolved = Column(Boolean, nullable=False, server_default="false", default=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_by_name = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __init__(self, **kwargs):
        kwargs.setdefault("field_name", "*")
        kwargs.setdefault("visibility", "shared")
        kwargs.setdefault("is_resolved", False)
        super().__init__(**kwargs)
