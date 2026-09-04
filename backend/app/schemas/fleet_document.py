"""
FleetDocument schemas — Phase 30-PR1.
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


class FleetDocumentCreate(BaseModel):
    vehicle_id: int
    type: str  # osago/sts/pts/to/tachograph/fpg/purchase_contract
    number: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    counterparty: Optional[str] = None
    amount_rub: Optional[Decimal] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    notes: Optional[str] = None


class FleetDocumentPatch(BaseModel):
    type: Optional[str] = None
    number: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    counterparty: Optional[str] = None
    amount_rub: Optional[Decimal] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    notes: Optional[str] = None


class FleetDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    type: str
    number: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    counterparty: Optional[str] = None
    amount_rub: Optional[Decimal] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    created_by_user_id: Optional[int] = None

    # Phase 29.3-R3 (Д-2): denormalized vehicle info (plate, model, type, operator)
    vehicle_plate: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_type: Optional[str] = None
    # 2026-09: «Кузов» — та же денормализация, что и vehicle_type выше; нужен
    # для единой иконки ТС (по кузову, не по типу) в реестре документов парка.
    vehicle_body_type: Optional[str] = None
    operator_org_name: Optional[str] = None  # Эксплуатант = Vehicle.assigned_org.name
    has_file: bool = False

    @computed_field
    @property
    def status(self) -> str:
        """valid / expiring_soon (<30d) / expired / no_expiry"""
        if self.expires_at is None:
            return "no_expiry"
        from datetime import date as _date
        today = _date.today()
        from datetime import timedelta
        if self.expires_at < today:
            return "expired"
        if self.expires_at <= today + timedelta(days=30):
            return "expiring_soon"
        return "valid"

    @computed_field
    @property
    def days_until_expiry(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        from datetime import date as _date
        return (self.expires_at - _date.today()).days


class FleetDocumentSummary(BaseModel):
    total: int
    valid: int
    expiring_soon: int
    expired: int
    no_expiry: int
    by_type: dict
