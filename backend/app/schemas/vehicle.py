"""
Pydantic v2 schemas for Vehicle Fleet module — Plan 29-01, Phase 29.

Decisions covered: D-04, D-06, D-07, D-08, D-10, D-11, D-12, D-13, D-15, D-18.

Schema hierarchy:
  VehicleCreate / VehiclePatch / VehicleOut / VehicleListItem
  VehicleAttachmentOut
  RepairOut / RepairCreate / RepairPatch
  OdometerOut / OdometerCreate
  FuelLogOut / FuelLogCreate
  TripOut / TripCreate
  ExternalDriverOut / ExternalDriverCreate
  FieldHistoryOut
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, model_validator, Field
from typing import Optional, List, Any, Dict
from datetime import date, datetime
from decimal import Decimal

# ─────────────────────── VehicleAttachment ───────────────────────

class VehicleAttachmentOut(BaseModel):
    """Метаданные документа/фото ТС без file_data (bytea не отдаём в списках)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    kind: str
    name: str
    mime: Optional[str] = None
    size: Optional[int] = None
    sha256: Optional[str] = None
    uploaded_at: datetime
    uploaded_by_id: Optional[int] = None
    policy_number: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None


# ─────────────────────── FieldHistory ───────────────────────

class FieldHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    field_key: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: datetime
    changed_by_user_id: Optional[int] = None
    comment: Optional[str] = None


# ─────────────────────── RepairAttachment ───────────────────────

class RepairAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repair_id: int
    kind: str
    name: str
    mime: Optional[str] = None
    size: Optional[int] = None
    sha256: Optional[str] = None
    uploaded_at: datetime
    uploaded_by_id: Optional[int] = None


# ─────────────────────── VehicleRepair ───────────────────────

class RepairCreate(BaseModel):
    vehicle_id: int
    date: date
    description: Optional[str] = None
    cost_amount: Optional[Decimal] = None
    performed_by_name: Optional[str] = None
    mileage_at_repair: Optional[int] = None
    status: str = "planned"
    purchase_id: Optional[int] = None


class RepairPatch(BaseModel):
    date: Optional[date] = None
    description: Optional[str] = None
    cost_amount: Optional[Decimal] = None
    performed_by_name: Optional[str] = None
    mileage_at_repair: Optional[int] = None
    status: Optional[str] = None
    purchase_id: Optional[int] = None


class RepairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    date: date
    description: Optional[str] = None
    cost_amount: Optional[Decimal] = None
    performed_by_name: Optional[str] = None
    mileage_at_repair: Optional[int] = None
    status: str
    purchase_id: Optional[int] = None
    created_at: datetime
    created_by_id: Optional[int] = None
    attachments: List[RepairAttachmentOut] = []


# ─────────────────────── VehicleOdometer ───────────────────────

class OdometerCreate(BaseModel):
    vehicle_id: int
    date: date
    odometer_km: int
    note: Optional[str] = None
    source: str = "manual"


class OdometerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    date: date
    odometer_km: int
    entered_by_id: Optional[int] = None
    note: Optional[str] = None
    source: str
    created_at: datetime


# ─────────────────────── FuelLog ───────────────────────

class FuelLogCreate(BaseModel):
    vehicle_id: int
    date: date
    liters: Optional[Decimal] = None
    price_per_liter: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    fuel_type: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    note: Optional[str] = None
    source: str = "manual"


class FuelLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    date: date
    liters: Optional[Decimal] = None
    price_per_liter: Optional[Decimal] = None
    fuel_type: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    note: Optional[str] = None
    source: str
    created_at: datetime
    created_by_id: Optional[int] = None

    # Computed: total_amount = liters * price_per_liter if NULL
    total_amount: Optional[Decimal] = None

    @model_validator(mode="after")
    def compute_total(self) -> "FuelLogOut":
        if self.total_amount is None and self.liters and self.price_per_liter:
            self.total_amount = self.liters * self.price_per_liter
        return self


# ─────────────────────── ExternalDriver ───────────────────────

class ExternalDriverCreate(BaseModel):
    full_name: str
    phone: Optional[str] = None
    license_series: Optional[str] = None
    license_number: Optional[str] = None
    license_categories: Optional[str] = None
    license_issued_at: Optional[date] = None
    license_expires_at: Optional[date] = None
    medical_cert_expires_at: Optional[date] = None
    org_id: Optional[int] = None
    notes: Optional[str] = None


class ExternalDriverPatch(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    license_series: Optional[str] = None
    license_number: Optional[str] = None
    license_categories: Optional[str] = None
    license_issued_at: Optional[date] = None
    license_expires_at: Optional[date] = None
    medical_cert_expires_at: Optional[date] = None
    org_id: Optional[int] = None
    notes: Optional[str] = None


class ExternalDriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone: Optional[str] = None
    license_series: Optional[str] = None
    license_number: Optional[str] = None
    license_categories: Optional[str] = None
    license_issued_at: Optional[date] = None
    license_expires_at: Optional[date] = None
    medical_cert_expires_at: Optional[date] = None
    org_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    created_by_id: Optional[int] = None


# ─────────────────────── Trip ───────────────────────

class TripCreate(BaseModel):
    vehicle_id: int
    date: date
    driver_user_id: Optional[int] = None
    driver_external_id: Optional[int] = None
    route_from: Optional[str] = None
    route_to: Optional[str] = None
    purpose: Optional[str] = None
    odometer_start: Optional[int] = None
    odometer_finish: Optional[int] = None
    fuel_remaining_start: Optional[Decimal] = None
    fuel_remaining_finish: Optional[Decimal] = None
    fuel_issued_l: Optional[Decimal] = None
    cargo_name: Optional[str] = None
    cargo_weight_t: Optional[Decimal] = None
    status: str = "draft"


class TripPatch(BaseModel):
    date: Optional[date] = None
    driver_user_id: Optional[int] = None
    driver_external_id: Optional[int] = None
    route_from: Optional[str] = None
    route_to: Optional[str] = None
    purpose: Optional[str] = None
    odometer_start: Optional[int] = None
    odometer_finish: Optional[int] = None
    fuel_remaining_start: Optional[Decimal] = None
    fuel_remaining_finish: Optional[Decimal] = None
    fuel_issued_l: Optional[Decimal] = None
    cargo_name: Optional[str] = None
    cargo_weight_t: Optional[Decimal] = None
    status: Optional[str] = None
    docx_path: Optional[str] = None


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    date: date
    driver_user_id: Optional[int] = None
    driver_external_id: Optional[int] = None
    route_from: Optional[str] = None
    route_to: Optional[str] = None
    purpose: Optional[str] = None
    odometer_start: Optional[int] = None
    odometer_finish: Optional[int] = None
    fuel_remaining_start: Optional[Decimal] = None
    fuel_remaining_finish: Optional[Decimal] = None
    fuel_issued_l: Optional[Decimal] = None
    cargo_name: Optional[str] = None
    cargo_weight_t: Optional[Decimal] = None
    docx_path: Optional[str] = None
    status: str
    created_at: datetime
    created_by_id: Optional[int] = None


# ─────────────────────── Vehicle ───────────────────────

class VehicleTransferHistoryOut(BaseModel):
    """История передач ТС — Phase 29.3."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    from_owner_org_id: Optional[int] = None
    to_owner_org_id: Optional[int] = None
    from_assigned_org_id: Optional[int] = None
    to_assigned_org_id: Optional[int] = None
    from_assigned_text: Optional[str] = None
    to_assigned_text: Optional[str] = None
    basis: Optional[str] = None
    doc_number: Optional[str] = None
    doc_date: Optional[date] = None
    comment: Optional[str] = None
    changed_at: datetime
    changed_by_user_id: Optional[int] = None


class VehicleCreate(BaseModel):
    owner_org_id: int
    assigned_org_id: Optional[int] = None
    assigned_text: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    vin: Optional[str] = None
    plate: str
    registered_at: Optional[date] = None
    insurance_until: Optional[date] = None
    type: Optional[str] = None
    state: Optional[str] = "working"
    fuel_type: Optional[str] = None
    fuel_norm_summer: Optional[float] = None
    fuel_norm_winter: Optional[float] = None
    has_tracker: Optional[bool] = None
    akb_ok: Optional[bool] = None
    has_radio: Optional[bool] = None
    mirrors_ok: Optional[bool] = None
    has_keys: Optional[bool] = None
    has_first_aid_kit: Optional[bool] = None
    has_spare_wheel: Optional[bool] = None
    has_extinguisher: Optional[bool] = None
    next_to_km: Optional[int] = None
    current_odometer_km: Optional[int] = None
    props: Optional[Dict[str, Any]] = Field(default_factory=dict)
    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture: Optional[int] = None
    last_to_mileage_km: Optional[int] = None
    last_to_date: Optional[date] = None
    pts_number: Optional[str] = None
    sts_number: Optional[str] = None
    tech_inspection_until: Optional[date] = None
    purchase_info: Optional[str] = None
    # Phase 29.3: assignment + engine
    assignment_basis: Optional[str] = None
    assignment_doc_number: Optional[str] = None
    assignment_doc_date: Optional[date] = None
    engine_power_hp: Optional[int] = None
    engine_volume_l: Optional[float] = None


class VehiclePatch(BaseModel):
    """Все поля Optional для PATCH (partial update)."""
    owner_org_id: Optional[int] = None
    assigned_org_id: Optional[int] = None
    assigned_text: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    registered_at: Optional[date] = None
    insurance_until: Optional[date] = None
    type: Optional[str] = None
    state: Optional[str] = None
    fuel_type: Optional[str] = None
    fuel_norm_summer: Optional[float] = None
    fuel_norm_winter: Optional[float] = None
    has_tracker: Optional[bool] = None
    akb_ok: Optional[bool] = None
    has_radio: Optional[bool] = None
    mirrors_ok: Optional[bool] = None
    has_keys: Optional[bool] = None
    has_first_aid_kit: Optional[bool] = None
    has_spare_wheel: Optional[bool] = None
    has_extinguisher: Optional[bool] = None
    next_to_km: Optional[int] = None
    current_odometer_km: Optional[int] = None
    props: Optional[Dict[str, Any]] = None
    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture: Optional[int] = None
    last_to_mileage_km: Optional[int] = None
    last_to_date: Optional[date] = None
    pts_number: Optional[str] = None
    sts_number: Optional[str] = None
    tech_inspection_until: Optional[date] = None
    purchase_info: Optional[str] = None
    # Phase 29.3: assignment + engine
    assignment_basis: Optional[str] = None
    assignment_doc_number: Optional[str] = None
    assignment_doc_date: Optional[date] = None
    engine_power_hp: Optional[int] = None
    engine_volume_l: Optional[float] = None


class VehicleOut(BaseModel):
    """Полная карточка ТС."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_org_id: int
    owner_org_name: Optional[str] = None
    owner_org_color: Optional[str] = None
    assigned_org_id: Optional[int] = None
    assigned_org_name: Optional[str] = None
    assigned_org_color: Optional[str] = None
    assigned_text: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    vin: Optional[str] = None
    plate: str
    registered_at: Optional[date] = None
    insurance_until: Optional[date] = None
    type: Optional[str] = None
    state: Optional[str] = None
    fuel_type: Optional[str] = None
    fuel_norm_summer: Optional[float] = None
    fuel_norm_winter: Optional[float] = None
    has_tracker: Optional[bool] = None
    akb_ok: Optional[bool] = None
    has_radio: Optional[bool] = None
    mirrors_ok: Optional[bool] = None
    has_keys: Optional[bool] = None
    has_first_aid_kit: Optional[bool] = None
    has_spare_wheel: Optional[bool] = None
    has_extinguisher: Optional[bool] = None
    next_to_km: Optional[int] = None
    current_odometer_km: Optional[int] = None
    props: Dict[str, Any] = Field(default_factory=dict)
    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture: Optional[int] = None
    last_to_mileage_km: Optional[int] = None
    last_to_date: Optional[date] = None
    pts_number: Optional[str] = None
    sts_number: Optional[str] = None
    tech_inspection_until: Optional[date] = None
    purchase_info: Optional[str] = None
    # Phase 29.3: assignment + engine
    assignment_basis: Optional[str] = None
    assignment_doc_number: Optional[str] = None
    assignment_doc_date: Optional[date] = None
    engine_power_hp: Optional[int] = None
    engine_volume_l: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    attachments: List[VehicleAttachmentOut] = []
    repairs: List[RepairOut] = []
    odometer_entries: List[OdometerOut] = []
    fuel_logs: List[FuelLogOut] = []
    trips: List[TripOut] = []
    field_history: List[FieldHistoryOut] = []
    transfer_history: List["VehicleTransferHistoryOut"] = []


class VehicleListItem(BaseModel):
    """Минимальный набор полей для списка ТС (без тяжёлых relationship'ов)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_org_id: int
    owner_org_name: Optional[str] = None
    owner_org_color: Optional[str] = None
    assigned_org_id: Optional[int] = None
    assigned_org_name: Optional[str] = None
    assigned_org_color: Optional[str] = None
    assigned_text: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    plate: str
    type: Optional[str] = None
    state: Optional[str] = None
    fuel_type: Optional[str] = None
    current_odometer_km: Optional[int] = None
    next_to_km: Optional[int] = None
    insurance_until: Optional[date] = None
    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture: Optional[int] = None
    tech_inspection_until: Optional[date] = None
    pts_number: Optional[str] = None
    sts_number: Optional[str] = None
    purchase_info: Optional[str] = None
    # Phase 29.3: assignment + engine
    assignment_basis: Optional[str] = None
    assignment_doc_number: Optional[str] = None
    assignment_doc_date: Optional[date] = None
    engine_power_hp: Optional[int] = None
    engine_volume_l: Optional[float] = None
    created_at: datetime
    updated_at: datetime
