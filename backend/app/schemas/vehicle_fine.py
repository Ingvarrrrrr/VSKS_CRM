"""
Pydantic schemas for VehicleFine — Phase 29.3-fines.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class VehicleFineCreate(BaseModel):
    vehicle_id: int
    issued_at: datetime
    amount: Decimal = Field(gt=0)
    doc_number: Optional[str] = None
    violation_type: Optional[str] = None
    location: Optional[str] = None
    comment: Optional[str] = None


class VehicleFinePatch(BaseModel):
    issued_at: Optional[datetime] = None
    amount: Optional[Decimal] = Field(default=None, gt=0)
    doc_number: Optional[str] = None
    violation_type: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None      # unpaid / paid / disputed
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    # Manual driver override (если авто-матч не нашёл)
    driver_user_id: Optional[int] = None
    driver_external_id: Optional[int] = None


class VehicleFineOut(BaseModel):
    id: int
    vehicle_id: int
    issued_at: datetime
    amount: Decimal
    doc_number: Optional[str] = None
    violation_type: Optional[str] = None
    location: Optional[str] = None
    status: str
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    driver_user_id: Optional[int] = None
    driver_external_id: Optional[int] = None
    matched_trip_id: Optional[int] = None
    created_at: datetime
    created_by_id: Optional[int] = None
    # Computed: resolved driver info
    driver_name: Optional[str] = None    # ФИО водителя или None
    driver_kind: str = "unmatched"       # 'user' / 'external' / 'unmatched'

    model_config = {"from_attributes": True}
