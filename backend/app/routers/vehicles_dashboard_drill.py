"""
Drill-down эндпоинты дашборда автопарка: детализация списка ТС по клику на
диаграмму + просроченные документы (ОСАГО/ТО/права/медсправки).

ПЕРЕНЕСЕНО (не изменено) из app/routers/vehicles_dashboard.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/vehicles-dashboard, регистрируется рядом с ядром в app/routes.py.
Общие хелперы видимости/дедупликации/state — из
app/services/fleet_dashboard_helpers.py (Правило №6, не дублировать).

Endpoints:
  /api/vehicles-dashboard/drill               — список ТС по клику на диаграмму
  /api/vehicles-dashboard/expiring-docs-drill  — drill для KPI «Документы истекают»
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_org_filter
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_repair import VehicleRepair
from app.models.fuel_log import FuelLog
from app.models.organization import Organization
from app.services.fleet_dashboard_helpers import (
    _current_month_range,
    _parse_date,
    _apply_visibility,
    _visibility_filter,
    _STATE_LABELS,
)

router = APIRouter(prefix="/api/vehicles-dashboard", tags=["vehicles"])


def _vehicle_item(r, fuel_cost: float = 0.0, repair_cost: float = 0.0) -> dict:
    return {
        "vehicle_id": r.id,
        "plate": r.plate or "",
        "brand": r.brand or "",
        "model": r.model or "",
        "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or (r.plate or ""),
        "state": r.state or "unknown",
        # 2026-09 (fleet/regions defect #3): попап списка машин по месту нахождения
        # показывает иконку типа ТС (VehicleTypeIcon.vue) — нужен сам тип, раньше
        # эндпоинт его не отдавал вовсе.
        "type": r.type if hasattr(r, "type") else None,
        # 2026-09: «Кузов» — попап на карте (/fleet/regions) должен рисовать ту же
        # иконку, что и остальной интерфейс (по кузову, не по типу); раньше эндпоинт
        # отдавал только type (см. комментарий выше про #3), body_type не было вовсе.
        "body_type": r.body_type if hasattr(r, "body_type") else None,
        "owner_org_name": r.owner_org_name if hasattr(r, "owner_org_name") else "",
        "fuel_cost": round(fuel_cost, 2),
        "repair_cost": round(repair_cost, 2),
    }


@router.get("/drill")
async def drill_vehicles(
    dimension: str = Query(..., description="bar_org | donut_state | line_fuel | top_expenses"),
    value: str = Query(..., description="Dimension value to drill into"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Return list of vehicles matching the clicked dimension+value."""
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    from app.models.purchase import Purchase as PurchaseModel

    OwnerOrg = Organization.__table__.alias("owner_org")

    base_q = (
        select(
            Vehicle.id,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.state,
            Vehicle.owner_org_id,
            Vehicle.type,
            Vehicle.body_type,
        )
    )
    base_q = _apply_visibility(base_q, current_user)

    items: list[dict] = []

    if dimension == "bar_org":
        # value = org_name → vehicles WHERE owner org name = value
        q = (
            base_q
            .join(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(Organization.name == value)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "donut_state":
        # value = label (например "Работает") → find internal state key
        reverse_labels = {v: k for k, v in _STATE_LABELS.items()}
        state_key = reverse_labels.get(value, value)
        # Robust: case-insensitive + trim (защита от заглавных букв / пробелов в БД)
        state_norm = state_key.lower().strip() if state_key else ""
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(func.lower(func.coalesce(Vehicle.state, "")) == state_norm)
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

        # Phase 29.2 diagnostic: если результат пуст, логируем distinct values
        # которые видны user'у — это вскроет case/whitespace/NULL mismatch.
        if not items:
            try:
                diag_q = select(Vehicle.state, func.count(Vehicle.id).label("cnt"))
                diag_q = _apply_visibility(diag_q, current_user)
                diag_q = diag_q.group_by(Vehicle.state)
                diag_rows = (await db.execute(diag_q)).all()
                import logging
                logging.warning(
                    f"[vehicles_drill donut_state] EMPTY result; "
                    f"value={value!r} state_key={state_key!r} state_norm={state_norm!r}; "
                    f"distinct states in visible DB: "
                    f"{[(r[0], int(r[1] or 0)) for r in diag_rows]}"
                )
            except Exception as exc:
                import logging
                logging.warning(f"[vehicles_drill donut_state] diag failed: {exc!r}")

    elif dimension == "line_fuel":
        # value = YYYY-MM-DD → vehicles that have a fuel log on that date
        fuel_date = _parse_date(value, d_from)
        fuel_sq = (
            select(FuelLog.vehicle_id)
            .where(FuelLog.date == fuel_date)
            .distinct()
        ).subquery("fuel_date_veh")
        fuel_amount_expr = func.coalesce(
            FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter
        )
        fuel_agg_sq = (
            select(
                FuelLog.vehicle_id,
                func.coalesce(func.sum(fuel_amount_expr), 0).label("fuel_cost"),
            )
            .where(FuelLog.date == fuel_date)
            .group_by(FuelLog.vehicle_id)
        ).subquery("fuel_agg_drill")
        q = (
            base_q
            .join(fuel_sq, fuel_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(fuel_agg_sq, fuel_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(
                Organization.name.label("owner_org_name"),
                func.coalesce(fuel_agg_sq.c.fuel_cost, 0).label("fuel_cost"),
            )
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r, fuel_cost=float(r.fuel_cost or 0)) for r in rows]

    elif dimension == "top_expenses":
        # value = vehicle_id string → single vehicle + expense breakdown
        try:
            vid = int(value)
        except ValueError:
            return {"items": [], "total": 0, "dimension": dimension, "value": value}
        fuel_amount_expr = func.coalesce(
            FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter
        )
        fuel_agg_sq = (
            select(
                FuelLog.vehicle_id,
                func.coalesce(func.sum(fuel_amount_expr), 0).label("fuel_cost"),
            )
            .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
            .group_by(FuelLog.vehicle_id)
        ).subquery("fuel_agg_te")
        repair_agg_sq = (
            select(
                VehicleRepair.vehicle_id,
                func.coalesce(
                    func.sum(func.coalesce(PurchaseModel.contract_price, VehicleRepair.cost_amount, 0)), 0
                ).label("repair_cost"),
            )
            .select_from(VehicleRepair)
            .outerjoin(PurchaseModel, PurchaseModel.id == VehicleRepair.purchase_id)
            .where(VehicleRepair.date >= d_from, VehicleRepair.date <= d_to)
            .group_by(VehicleRepair.vehicle_id)
        ).subquery("repair_agg_te")
        q = (
            base_q
            .outerjoin(fuel_agg_sq, fuel_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(repair_agg_sq, repair_agg_sq.c.vehicle_id == Vehicle.id)
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(
                Organization.name.label("owner_org_name"),
                func.coalesce(fuel_agg_sq.c.fuel_cost, 0).label("fuel_cost"),
                func.coalesce(repair_agg_sq.c.repair_cost, 0).label("repair_cost"),
            )
            .where(Vehicle.id == vid)
        )
        rows = (await db.execute(q)).all()
        items = [
            _vehicle_item(r, fuel_cost=float(r.fuel_cost or 0), repair_cost=float(r.repair_cost or 0))
            for r in rows
        ]

    elif dimension == "region":
        # value = location_city (место нахождения ТС) → vehicles WHERE location_city = value.
        # 2026-09: география больше не берётся из assigned_text (кто эксплуатирует) —
        # только из места нахождения самой машины. "Место не указано" = NULL/пусто.
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
        )
        if value == "Место не указано":
            q = q.where(or_(Vehicle.location_city.is_(None), Vehicle.location_city == ""))
        else:
            q = q.where(Vehicle.location_city == value)
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "state":
        # value = state key string (e.g. 'working', 'in_repair')
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(func.lower(func.coalesce(Vehicle.state, "")) == (value or "").lower().strip())
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    elif dimension == "warning":
        # value = 'all' → all vehicles with active maintenance warnings
        today = date.today()
        horizon = today + timedelta(days=30)
        q = (
            base_q
            .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
            .add_columns(Organization.name.label("owner_org_name"))
            .where(
                or_(
                    and_(Vehicle.insurance_until.is_not(None), Vehicle.insurance_until <= horizon),
                    and_(Vehicle.next_to_km.is_not(None), Vehicle.current_odometer_km.is_not(None),
                         (Vehicle.next_to_km - Vehicle.current_odometer_km) < 1000),
                )
            )
        )
        rows = (await db.execute(q)).all()
        items = [_vehicle_item(r) for r in rows]

    else:
        return {"items": [], "total": 0, "dimension": dimension, "value": value}

    return {"items": items, "total": len(items), "dimension": dimension, "value": value}


# ─────────────────────────── 10. Expiring docs drill ─────────────────────────

@router.get("/expiring-docs-drill")
async def expiring_docs_drill(
    days: int = Query(30, ge=1, le=365, description="Горизонт в днях"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
) -> dict:
    """Drill для KPI «Документы истекают»: ТС + водители с истекающими документами."""
    today = date.today()
    horizon = today + timedelta(days=days)

    # === ТС с истекающими документами ===
    vehicles_q = select(Vehicle).where(
        or_(
            and_(Vehicle.insurance_until.isnot(None), Vehicle.insurance_until <= horizon),
            and_(Vehicle.tech_inspection_until.isnot(None), Vehicle.tech_inspection_until <= horizon),
        )
    )
    vis_clause = _visibility_filter(current_user)
    if vis_clause is not None:
        vehicles_q = vehicles_q.where(vis_clause)

    v_rows = (await db.execute(vehicles_q)).scalars().unique().all()

    vehicles_out = []
    for v in v_rows:
        expiring = []
        if v.insurance_until and v.insurance_until <= horizon:
            expiring.append({
                "type": "osago",
                "label": "ОСАГО",
                "expires_at": v.insurance_until.isoformat(),
                "days_left": (v.insurance_until - today).days,
            })
        if v.tech_inspection_until and v.tech_inspection_until <= horizon:
            expiring.append({
                "type": "tech_inspection",
                "label": "Технический осмотр",
                "expires_at": v.tech_inspection_until.isoformat(),
                "days_left": (v.tech_inspection_until - today).days,
            })
        if not expiring:
            continue
        vehicles_out.append({
            "id": v.id,
            "plate": v.plate,
            "brand": v.brand,
            "model": v.model,
            "state": v.state,
            "expiring_docs": expiring,
        })

    # === Водители с истекающими документами ===
    drivers_q = select(User).where(
        User.can_drive == True,
        or_(
            and_(User.license_expires_at.isnot(None), User.license_expires_at <= horizon),
            and_(User.medical_cert_expires_at.isnot(None), User.medical_cert_expires_at <= horizon),
            and_(User.tachograph_card_expires_at.isnot(None), User.tachograph_card_expires_at <= horizon),
            and_(User.psych_cert_expires_at.isnot(None), User.psych_cert_expires_at <= horizon),
            and_(User.periodic_medical_expires_at.isnot(None), User.periodic_medical_expires_at <= horizon),
        )
    )
    # Org visibility for drivers: filter by org_ids the current user can see
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        drivers_q = drivers_q.where(User.org_id.in_(org_ids))

    d_rows = (await db.execute(drivers_q)).scalars().unique().all()

    drivers_out = []
    for u in d_rows:
        expiring = []
        for field, type_key, label in [
            ("license_expires_at", "license", "Водительское удостоверение"),
            ("medical_cert_expires_at", "medical", "Медсправка водителя"),
            ("periodic_medical_expires_at", "periodic_medical", "Периодический медосмотр (302-пр.)"),
            ("psych_cert_expires_at", "psych", "Психиатрия (302-пр.)"),
            ("tachograph_card_expires_at", "tachograph", "Карточка тахографа"),
        ]:
            val = getattr(u, field, None)
            if val and val <= horizon:
                expiring.append({
                    "type": type_key,
                    "label": label,
                    "expires_at": val.isoformat(),
                    "days_left": (val - today).days,
                })
        if not expiring:
            continue
        drivers_out.append({
            "id": u.id,
            "full_name": u.full_name or u.username,
            "fleet_role": u.fleet_role,
            "expiring_docs": expiring,
        })

    # Сортировка по min days_left (самые срочные сверху)
    vehicles_out.sort(key=lambda x: min(d["days_left"] for d in x["expiring_docs"]))
    drivers_out.sort(key=lambda x: min(d["days_left"] for d in x["expiring_docs"]))

    return {
        "vehicles": vehicles_out,
        "drivers": drivers_out,
        "horizon_days": days,
        "horizon_date": horizon.isoformat(),
    }


