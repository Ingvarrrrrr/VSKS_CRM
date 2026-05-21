"""
Checklist schemas — Phase 30-PR1.
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ChecklistItemCreate(BaseModel):
    key: str
    status: str  # ok/issue/missing
    photo_url: Optional[str] = None
    note: Optional[str] = None


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    checklist_id: int
    key: str
    status: str
    photo_url: Optional[str] = None
    note: Optional[str] = None


class ChecklistCreate(BaseModel):
    vehicle_id: int
    driver_user_id: Optional[int] = None
    waybill_id: Optional[int] = None
    type: str  # pre_trip/post_trip/weekly/monthly
    overall_state: Optional[str] = None
    fuel_level: Optional[str] = None
    paint_condition: Optional[str] = None
    notes: Optional[str] = None
    items: List[ChecklistItemCreate] = []


class ChecklistPatch(BaseModel):
    overall_state: Optional[str] = None
    fuel_level: Optional[str] = None
    paint_condition: Optional[str] = None
    notes: Optional[str] = None
    signed_at: Optional[datetime] = None


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    driver_user_id: Optional[int] = None
    waybill_id: Optional[int] = None
    type: str
    overall_state: Optional[str] = None
    fuel_level: Optional[str] = None
    paint_condition: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    signed_at: Optional[datetime] = None
    items: List[ChecklistItemOut] = []
