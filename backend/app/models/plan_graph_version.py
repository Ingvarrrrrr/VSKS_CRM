from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base


class PlanGraphVersion(Base):
    __tablename__ = "plan_graph_versions"

    id = Column(Integer, primary_key=True)
    subsidy_id = Column(
        Integer,
        ForeignKey("subsidies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_name = Column(String(200), nullable=True)
    snapshot = Column(JSONB, nullable=False)
    # snapshot structure:
    # {
    #   "subsidy_id": int,
    #   "total_planned": float,
    #   "total_used": float,
    #   "items": [
    #     {"feo_item_id": int, "name": str, "category_id": int,
    #      "planned_amount": float, "used_amount": float, "residual": float,
    #      "linked_purchase_ids": [int, ...]}
    #   ]
    # }
    note = Column(Text, nullable=True)
    effective_date = Column(Date, nullable=True, index=True)
