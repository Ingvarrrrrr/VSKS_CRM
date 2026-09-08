"""
Сводные таблицы и фиды дашборда автопарка: полная таблица ТС, география по
регионам, лента событий водителей, счётчики для чипов-фильтров.

ПЕРЕНЕСЕНО (не изменено) из app/routers/vehicles_dashboard.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/vehicles-dashboard, регистрируется рядом с ядром в app/routes.py.
Общие хелперы видимости/дедупликации/state — из
app/services/fleet_dashboard_helpers.py (Правило №6, не дублировать).

Endpoints:
  /api/vehicles-dashboard/all-vehicles-summary — полная таблица ТС за период
  /api/vehicles-dashboard/by-region            — география по location_city
  /api/vehicles-dashboard/driver-reports       — лента событий (одометр/ремонт)
  /api/vehicles-dashboard/filter-counts        — счётчики для чипов-фильтров
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
    _dedup_key,
    _state_rank,
)

router = APIRouter(prefix="/api/vehicles-dashboard", tags=["vehicles"])


@router.get("/all-vehicles-summary")
async def all_vehicles_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    owner_org_ids: Optional[str] = Query(None, description="Comma-separated org ids"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Full vehicles table with aggregated fuel cost, repair cost, mileage for the period.
    No LIMIT — returns all visible vehicles.
    """
    first, last = _current_month_range()
    d_from = _parse_date(date_from, first)
    d_to = _parse_date(date_to, last)

    extra_org_ids: Optional[List[int]] = None
    if owner_org_ids:
        try:
            extra_org_ids = [int(x.strip()) for x in owner_org_ids.split(",") if x.strip()]
        except ValueError:
            extra_org_ids = None

    from app.models.purchase import Purchase as PurchaseModel
    from app.models.vehicle_odometer import VehicleOdometer

    fuel_expr = func.coalesce(FuelLog.total_amount, FuelLog.liters * FuelLog.price_per_liter)

    fuel_sq = (
        select(
            FuelLog.vehicle_id,
            func.coalesce(func.sum(fuel_expr), 0).label("fuel_cost"),
        )
        .where(FuelLog.date >= d_from, FuelLog.date <= d_to)
        .group_by(FuelLog.vehicle_id)
    ).subquery("all_veh_fuel")

    repair_sq = (
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
    ).subquery("all_veh_repair")

    mileage_sq = (
        select(
            VehicleOdometer.vehicle_id,
            (func.max(VehicleOdometer.odometer_km) - func.min(VehicleOdometer.odometer_km)).label("mileage_km"),
        )
        .where(VehicleOdometer.date >= d_from, VehicleOdometer.date <= d_to)
        .group_by(VehicleOdometer.vehicle_id)
    ).subquery("all_veh_mileage")

    today = date.today()
    horizon_30 = today + timedelta(days=30)

    q = (
        select(
            Vehicle.id,
            Vehicle.plate,
            Vehicle.vin,
            Vehicle.brand,
            Vehicle.model,
            Vehicle.state,
            Vehicle.insurance_until,
            Vehicle.assigned_text,
            Vehicle.location_city,
            Organization.name.label("owner_org_name"),
            func.coalesce(fuel_sq.c.fuel_cost, 0).label("fuel_cost"),
            func.coalesce(repair_sq.c.repair_cost, 0).label("repair_cost"),
            func.coalesce(mileage_sq.c.mileage_km, 0).label("mileage_km"),
        )
        .outerjoin(Organization, Organization.id == Vehicle.owner_org_id)
        .outerjoin(fuel_sq, fuel_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(repair_sq, repair_sq.c.vehicle_id == Vehicle.id)
        .outerjoin(mileage_sq, mileage_sq.c.vehicle_id == Vehicle.id)
        .order_by(Vehicle.plate)
    )
    q = _apply_visibility(q, current_user)
    if extra_org_ids:
        q = q.where(Vehicle.owner_org_id.in_(extra_org_ids))

    rows = (await db.execute(q)).all()

    # Phase 29.3-R3: дедубликация по VIN→plate→id (см. _dedup_key)
    seen: dict[str, dict] = {}
    for r in rows:
        norm = _dedup_key(getattr(r, "vin", None), r.plate, r.id)
        item = {
            "vehicle_id": r.id,
            "plate": r.plate or "",
            "brand_model": f"{r.brand or ''} {r.model or ''}".strip() or (r.plate or ""),
            "state": r.state or "unknown",
            "owner_org_name": r.owner_org_name or "",
            "assigned_text": r.assigned_text or "",
            "location_city": r.location_city or "",
            "fuel_cost": float(r.fuel_cost or 0),
            "repair_cost": float(r.repair_cost or 0),
            "mileage_km": int(r.mileage_km or 0),
            "insurance_overdue": (
                r.insurance_until is not None and r.insurance_until < today
            ),
            "insurance_until": r.insurance_until.isoformat() if r.insurance_until else None,
        }
        prev = seen.get(norm)
        # Phase 29.3-R3 (pt-tie), обновлено 2026-09: при равном state_rank — выигрывает запись
        # с non-empty location_city (это устраняет mismatch между /by-region, теперь по
        # location_city — месту нахождения машины, а не assigned_text/организации — и
        # /all-vehicles-summary).
        if not prev:
            seen[norm] = item
        else:
            cur_rank = _state_rank(item["state"])
            prev_rank = _state_rank(prev["state"])
            cur_has_location = bool(item.get("location_city"))
            prev_has_location = bool(prev.get("location_city"))
            if cur_rank > prev_rank or (cur_rank == prev_rank and cur_has_location and not prev_has_location):
                seen[norm] = item
    return list(seen.values())


# ─────────────────────────── 11. By-region (Phase 29.1) ──────────────────────

@router.get("/by-region")
async def by_region(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Fleet geography — group vehicles by Vehicle.location_city (место нахождения машины).

    2026-09 (распоряжение владельца): география эксплуатации привязана к месту
    нахождения ТС, а НЕ к тому, кто им пользуется/владеет — раньше группировка шла
    по assigned_text ("у кого в эксплуатации"), что фактически подменяло географию
    организацией. Тихого фолбэка на assigned_text нет: пустой location_city → группа
    «Место не указано».

    Returns list sorted by count desc. If fewer than 5 vehicles visible, adds mock_demo flag.
    """
    from app.services.geo_normalize import normalize_city, shtab_label_for_city

    # Phase 29.3-R3: дедубликация по VIN→plate→id
    q = (
        select(Vehicle.id, Vehicle.vin, Vehicle.plate, Vehicle.state, Vehicle.location_city)
    )
    q = _apply_visibility(q, current_user)
    raw_rows = (await db.execute(q)).all()

    seen_v: dict[str, dict] = {}
    for r in raw_rows:
        norm = _dedup_key(r.vin, r.plate, r.id)
        city = normalize_city(r.location_city)
        cur = {"region": city or "Место не указано", "state": r.state or "unknown"}
        prev = seen_v.get(norm)
        if not prev or _state_rank(cur["state"]) > _state_rank(prev["state"]):
            seen_v[norm] = cur

    region_map: dict = {}
    for v in seen_v.values():
        rg = v["region"]
        if rg not in region_map:
            region_map[rg] = {"region": rg, "count": 0, "by_state": {}}
        region_map[rg]["count"] += 1
        sk = v["state"]
        region_map[rg]["by_state"][sk] = region_map[rg]["by_state"].get(sk, 0) + 1

    result = sorted(region_map.values(), key=lambda x: x["count"], reverse=True)

    for item in result:
        item["shtab_label"] = shtab_label_for_city(item["region"])

    total = sum(item["count"] for item in result)
    mock_demo = total < 5

    return {"items": result, "mock_demo": mock_demo}


# ─────────────────────────── 12. Driver reports feed (Phase 29.1 / 30) ───────

@router.get("/driver-reports")
async def driver_reports(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Phase 29.1: Feed of recent events for Driver Reports panel.
    Phase 30 (mobile app) will populate this with real driver checklist submissions.
    Currently sources from: VehicleOdometer (last updates) + VehicleRepair (recent).
    Returns [] when empty — UI shows placeholder message.
    """
    from app.models.vehicle_odometer import VehicleOdometer

    feed: list[dict] = []

    # Recent odometer updates
    odo_q = (
        select(
            VehicleOdometer.vehicle_id,
            VehicleOdometer.odometer_km,
            VehicleOdometer.date,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
        )
        .join(Vehicle, Vehicle.id == VehicleOdometer.vehicle_id)
        .order_by(VehicleOdometer.created_at.desc())
        .limit(limit)
    )
    odo_q = _apply_visibility(odo_q, current_user)
    try:
        odo_rows = (await db.execute(odo_q)).all()
        for r in odo_rows:
            feed.append({
                "vehicle_id": r.vehicle_id,
                "plate": r.plate or "",
                "type": "odometer_update",
                "ic": "ok",
                "title": f"Пробег обновлён: {r.odometer_km:,} км".replace(",", "\u00a0"),
                "author": "",
                "timestamp": r.date.isoformat() if r.date else "",
            })
    except Exception:
        pass

    # Recent repair requests
    rep_q = (
        select(
            VehicleRepair.vehicle_id,
            VehicleRepair.description,
            VehicleRepair.date,
            Vehicle.plate,
            Vehicle.brand,
            Vehicle.model,
        )
        .join(Vehicle, Vehicle.id == VehicleRepair.vehicle_id)
        .order_by(VehicleRepair.created_at.desc())
        .limit(limit)
    )
    rep_q = _apply_visibility(rep_q, current_user)
    try:
        rep_rows = (await db.execute(rep_q)).all()
        for r in rep_rows:
            feed.append({
                "vehicle_id": r.vehicle_id,
                "plate": r.plate or "",
                "type": "issue",
                "ic": "alert",
                "title": r.description or "Заявка на ремонт",
                "author": "",
                "timestamp": r.date.isoformat() if r.date else "",
            })
    except Exception:
        pass

    # Sort by timestamp desc, take top limit
    feed.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return feed[:limit]


# ─────────────────────────── 13. Filter counts (Phase 29.1) ──────────────────

@router.get("/filter-counts")
async def filter_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Phase 29.1: Counts for filter chips in VehicleDashboardView.
    Returns: all, working, in_repair, not_running, no_report_30d, for_disposal.
    """
    from app.models.vehicle_odometer import VehicleOdometer

    today = date.today()
    cutoff_30d = today - timedelta(days=30)

    # Phase 29.3-R3: дедубликация по VIN→plate→id
    raw_q = select(Vehicle.id, Vehicle.vin, Vehicle.plate, Vehicle.state)
    raw_q = _apply_visibility(raw_q, current_user)
    raw_rows = (await db.execute(raw_q)).all()

    seen_v: dict[str, tuple[int, str]] = {}  # norm_key -> (id, state)
    for r in raw_rows:
        norm = _dedup_key(r.vin, r.plate, r.id)
        prev = seen_v.get(norm)
        if not prev or _state_rank(r.state) > _state_rank(prev[1]):
            seen_v[norm] = (r.id, r.state or "unknown")

    unique_ids = {v[0] for v in seen_v.values()}
    total_all = len(unique_ids)
    state_map: dict = {}
    for _id, st in seen_v.values():
        state_map[st] = state_map.get(st, 0) + 1

    working = state_map.get("working", 0)
    # in_repair bucket mirrors frontend filteredVehicles: ['in_repair', 'broken', 'needs_repair']
    in_repair = (
        state_map.get("in_repair", 0)
        + state_map.get("broken", 0)
        + state_map.get("needs_repair", 0)
    )
    # not_running bucket: destroyed + utilized (списаны/утилизированы)
    not_running = (
        state_map.get("destroyed", 0)
        + state_map.get("utilized", 0)
    )

    # No report in 30d: working vehicles with NO odometer record in last 30 days
    recent_odo_sq = (
        select(VehicleOdometer.vehicle_id)
        .where(VehicleOdometer.date >= cutoff_30d)
        .distinct()
    ).subquery("recent_odo")

    no_report_q = (
        select(Vehicle.id)
        .outerjoin(recent_odo_sq, recent_odo_sq.c.vehicle_id == Vehicle.id)
        .where(recent_odo_sq.c.vehicle_id.is_(None))
        .where(Vehicle.state == "working")
    )
    no_report_q = _apply_visibility(no_report_q, current_user)
    no_report_ids = {r.id for r in (await db.execute(no_report_q)).all()}
    no_report_30d = len(no_report_ids & unique_ids)

    # For disposal: destroyed + utilized
    for_disposal = state_map.get("destroyed", 0) + state_map.get("utilized", 0)

    return {
        "all": total_all,
        "working": working,
        "in_repair": in_repair,
        "not_running": not_running,
        "no_report_30d": no_report_30d,
        "for_disposal": for_disposal,
        "mock_demo": total_all < 5,
    }


