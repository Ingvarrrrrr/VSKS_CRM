"""
Incident schemas — Phase 30-PR1.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class IncidentCreate(BaseModel):
    vehicle_id: int
    driver_user_id: Optional[int] = None
    waybill_id: Optional[int] = None
    incident_type: str   # accident/breakdown/other
    severity: str = 'medium'
    affected_system: Optional[str] = None
    is_operational: Optional[bool] = None
    location: Optional[str] = None
    description: str
    photos: List[Dict[str, Any]] = []
    notify_user_id: Optional[int] = None


class IncidentPatch(BaseModel):
    incident_type: Optional[str] = None
    severity: Optional[str] = None
    affected_system: Optional[str] = None
    is_operational: Optional[bool] = None
    location: Optional[str] = None
    description: Optional[str] = None
    photos: Optional[List[Dict[str, Any]]] = None
    resolved_at: Optional[datetime] = None
    notify_user_id: Optional[int] = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    driver_user_id: Optional[int] = None
    waybill_id: Optional[int] = None
    incident_type: str
    severity: str
    affected_system: Optional[str] = None
    is_operational: Optional[bool] = None
    location: Optional[str] = None
    description: str
    photos: List[Dict[str, Any]] = []
    created_at: datetime
    resolved_at: Optional[datetime] = None
    notify_user_id: Optional[int] = None
