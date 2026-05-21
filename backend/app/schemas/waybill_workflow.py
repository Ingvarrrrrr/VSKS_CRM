"""
Pydantic schemas для workflow операций путевых листов — Phase 30-PR3.

TechInspectIn, MedInspectIn, PostTripMechanicIn, PostTripDoctorIn,
DriverSignIn, RouteStopIn, OdometerReadingIn, FuelRefillIn.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TechInspectIn(BaseModel):
    mechanic_id: int
    inspected_at: datetime
    result: str = Field(..., min_length=1, max_length=1000)


class MedInspectIn(BaseModel):
    doctor_id: int
    inspected_at: datetime
    result: str = Field(..., min_length=1, max_length=1000)


class PostTripMechanicIn(BaseModel):
    mechanic_id: int
    inspected_at: datetime
    result: str = Field(..., min_length=1, max_length=1000)


class PostTripDoctorIn(BaseModel):
    doctor_id: int
    inspected_at: datetime
    result: str = Field(..., min_length=1, max_length=1000)


class DriverSignIn(BaseModel):
    signature: str = Field(..., description="data:image/png;base64,... или просто base64")
    signed_at: datetime


class RouteStopIn(BaseModel):
    ord: int = Field(..., ge=1)
    kind: str = Field(..., description="start/regular/end")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    planned_time: Optional[datetime] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class OdometerReadingIn(BaseModel):
    recorded_at: datetime
    location: Optional[str] = Field(None, max_length=200)
    mileage_km: int = Field(..., ge=0)
    fuel_remaining_l: Optional[float] = None
    note: Optional[str] = None


class FuelRefillIn(BaseModel):
    refilled_at: datetime
    station_name: Optional[str] = Field(None, max_length=200)
    liters: float = Field(..., gt=0)
    amount_rub: Optional[float] = None
    receipt_photo_data: Optional[str] = Field(None, description="base64 encoded photo")
