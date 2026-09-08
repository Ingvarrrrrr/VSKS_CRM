"""
Штрафы автопарка: пьедестал нарушителей, агрегированные счётчики, разбивка по
филиалам.

ПЕРЕНЕСЕНО (не изменено) из app/routers/vehicles_dashboard.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/vehicles-dashboard, регистрируется рядом с ядром в app/routes.py.

Endpoints:
  /api/vehicles-dashboard/fine-leaders     — топ по штрафам (drivers|vehicles|filials)
  /api/vehicles-dashboard/fines-summary    — агрегированные счётчики по автопарку
  /api/vehicles-dashboard/fines-by-filial  — штрафы по филиалам (owner_org_id)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.organization import Organization

router = APIRouter(prefix="/api/vehicles-dashboard", tags=["vehicles"])


@router.get("/fine-leaders")
async def fine_leaders(
    kind: str = Query("drivers", description="Тип рейтинга: drivers | vehicles | filials"),
    limit: int = Query(10, ge=1, le=50),
    period_days: Optional[int] = Query(None, description="Окно за последние N дней; None = все"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Топ по штрафам — пьедестал. kind=drivers|vehicles|filials.

    drivers: группировка по водителю (snapshot + fallback JOIN trips).
    vehicles: группировка по ТС (plate / brand+model).
    filials: группировка по организации-владельцу ТС (owner_org_id).
    """
    period_filter = ""
    if period_days is not None:
        period_filter = f"AND f.issued_at >= NOW() - INTERVAL '{int(period_days)} days'"

    if kind == "vehicles":
        sql = text(f"""
            SELECT
                v.id::text                                             AS entity_key,
                COALESCE(v.plate, '—')                                AS entity_name,
                TRIM(CONCAT(COALESCE(v.brand,''), ' ', COALESCE(v.model,''))) AS entity_sub,
                v.id                                                  AS entity_id,
                COUNT(f.id)::int                                      AS fines_count,
                SUM(f.amount)                                         AS fines_total,
                COUNT(f.id) FILTER (WHERE f.status = 'unpaid')::int   AS unpaid_count,
                COALESCE(SUM(f.amount) FILTER (WHERE f.status = 'unpaid'), 0) AS unpaid_total
            FROM vehicle_fines f
            JOIN vehicles v ON v.id = f.vehicle_id
            WHERE 1=1 {period_filter}
            GROUP BY v.id, v.plate, v.brand, v.model
            ORDER BY fines_total DESC NULLS LAST
            LIMIT :lim
        """)
        rows = (await db.execute(sql, {"lim": limit})).mappings().all()
        return [
            {
                "entity_key": r["entity_key"],
                "entity_name": r["entity_name"],
                "entity_sub": r["entity_sub"],
                "entity_id": r["entity_id"],
                "fines_count": r["fines_count"],
                "fines_total": float(r["fines_total"] or 0),
                "unpaid_count": r["unpaid_count"],
                "unpaid_total": float(r["unpaid_total"] or 0),
            }
            for r in rows
        ]

    if kind == "filials":
        sql = text(f"""
            SELECT
                o.id::text                                             AS entity_key,
                COALESCE(o.name, '— Без филиала —')                   AS entity_name,
                NULL                                                   AS entity_sub,
                o.id                                                   AS entity_id,
                COUNT(f.id)::int                                       AS fines_count,
                SUM(f.amount)                                          AS fines_total,
                COUNT(f.id) FILTER (WHERE f.status = 'unpaid')::int    AS unpaid_count,
                COALESCE(SUM(f.amount) FILTER (WHERE f.status = 'unpaid'), 0) AS unpaid_total
            FROM vehicle_fines f
            JOIN vehicles v ON v.id = f.vehicle_id
            LEFT JOIN organizations o ON o.id = v.owner_org_id
            WHERE 1=1 {period_filter}
            GROUP BY o.id, o.name
            ORDER BY fines_total DESC NULLS LAST
            LIMIT :lim
        """)
        rows = (await db.execute(sql, {"lim": limit})).mappings().all()
        return [
            {
                "entity_key": r["entity_key"],
                "entity_name": r["entity_name"],
                "entity_sub": r["entity_sub"],
                "entity_id": r["entity_id"],
                "fines_count": r["fines_count"],
                "fines_total": float(r["fines_total"] or 0),
                "unpaid_count": r["unpaid_count"],
                "unpaid_total": float(r["unpaid_total"] or 0),
            }
            for r in rows
        ]

    # kind == "drivers" (default)
    sql = text(f"""
        WITH matched AS (
            SELECT
                f.id,
                f.amount,
                f.status,
                COALESCE(f.driver_user_id, t.driver_user_id)         AS user_id,
                COALESCE(f.driver_external_id, t.driver_external_id) AS ext_id
            FROM vehicle_fines f
            LEFT JOIN trips t
                ON t.vehicle_id = f.vehicle_id
               AND t.date = (f.issued_at AT TIME ZONE 'UTC')::date
            WHERE 1=1 {period_filter}
        )
        SELECT
            CASE
                WHEN user_id IS NOT NULL THEN 'user-' || user_id::text
                WHEN ext_id  IS NOT NULL THEN 'ext-'  || ext_id::text
                ELSE 'unmatched'
            END                                                    AS driver_key,
            COALESCE(u.full_name, ext.full_name, '— Не определён —') AS driver_name,
            CASE
                WHEN user_id IS NOT NULL THEN 'user'
                WHEN ext_id  IS NOT NULL THEN 'external'
                ELSE 'unmatched'
            END                                                    AS driver_kind,
            CASE
                WHEN user_id IS NOT NULL THEN user_id
                WHEN ext_id  IS NOT NULL THEN ext_id
                ELSE NULL
            END                                                    AS driver_id,
            COUNT(*)::int                                          AS fines_count,
            SUM(amount)                                            AS fines_total,
            COUNT(*) FILTER (WHERE status = 'unpaid')::int         AS unpaid_count,
            COALESCE(SUM(amount) FILTER (WHERE status = 'unpaid'), 0) AS unpaid_total
        FROM matched
        LEFT JOIN users u   ON u.id   = user_id
        LEFT JOIN external_drivers ext ON ext.id = ext_id
        GROUP BY driver_key, driver_name, driver_kind, driver_id
        ORDER BY fines_total DESC NULLS LAST
        LIMIT :lim
    """)

    rows = (await db.execute(sql, {"lim": limit})).mappings().all()
    return [
        {
            "driver_key": r["driver_key"],
            "driver_name": r["driver_name"],
            "driver_kind": r["driver_kind"],
            "driver_id": r["driver_id"],
            "fines_count": r["fines_count"],
            "fines_total": float(r["fines_total"] or 0),
            "unpaid_count": r["unpaid_count"],
            "unpaid_total": float(r["unpaid_total"] or 0),
        }
        for r in rows
    ]


@router.get("/fines-summary")
async def fines_summary(
    period_days: Optional[int] = Query(None, description="Окно за последние N дней; None = все"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """
    Агрегированные счётчики штрафов по всему автопарку.
    Используется для KPI-карточек в дашборде.
    """
    from app.models.vehicle_fine import VehicleFine

    q = select(
        func.count(VehicleFine.id).label("total_count"),
        func.coalesce(func.sum(VehicleFine.amount), 0).label("total_amount"),
        func.count(VehicleFine.id).filter(VehicleFine.status == "unpaid").label("unpaid_count"),
        func.coalesce(
            func.sum(VehicleFine.amount).filter(VehicleFine.status == "unpaid"), 0
        ).label("unpaid_amount"),
    )
    if period_days is not None:
        from sqlalchemy import func as safunc
        from datetime import timezone as tz
        import datetime as dt_mod
        cutoff = dt_mod.datetime.now(tz.utc) - dt_mod.timedelta(days=period_days)
        q = q.where(VehicleFine.issued_at >= cutoff)

    row = (await db.execute(q)).first()
    return {
        "total_count": row.total_count if row else 0,
        "total_amount": float(row.total_amount) if row else 0.0,
        "unpaid_count": row.unpaid_count if row else 0,
        "unpaid_amount": float(row.unpaid_amount) if row else 0.0,
    }


@router.get("/fines-by-filial")
async def fines_by_filial(
    period_days: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("vehicles")),
):
    """Phase 29.3-R3 (pt11): штрафы по филиалам (Vehicle.owner_org_id → Organization.name).
    Возвращает: [{org_id, org_name, total_count, total_amount, unpaid_count, unpaid_amount, overdue_count}]
    """
    from app.models.vehicle_fine import VehicleFine
    import datetime as dt_mod
    from datetime import timezone as tz

    now_utc = dt_mod.datetime.now(tz.utc)
    overdue_cutoff = now_utc + dt_mod.timedelta(days=7)  # «скоро срок» <7 дней — пока используем как proxy «overdue»

    q = (
        select(
            Organization.id.label("org_id"),
            Organization.name.label("org_name"),
            func.count(VehicleFine.id).label("total_count"),
            func.coalesce(func.sum(VehicleFine.amount), 0).label("total_amount"),
            func.count(VehicleFine.id).filter(VehicleFine.status == "unpaid").label("unpaid_count"),
            func.coalesce(
                func.sum(VehicleFine.amount).filter(VehicleFine.status == "unpaid"), 0
            ).label("unpaid_amount"),
        )
        .select_from(VehicleFine)
        .join(Vehicle, Vehicle.id == VehicleFine.vehicle_id)
        .join(Organization, Organization.id == Vehicle.owner_org_id)
        .group_by(Organization.id, Organization.name)
        .order_by(func.sum(VehicleFine.amount).desc())
    )
    if period_days is not None:
        cutoff = now_utc - dt_mod.timedelta(days=period_days)
        q = q.where(VehicleFine.issued_at >= cutoff)

    rows = (await db.execute(q)).all()
    return [{
        "org_id": r.org_id,
        "org_name": r.org_name,
        "total_count": int(r.total_count or 0),
        "total_amount": float(r.total_amount or 0),
        "unpaid_count": int(r.unpaid_count or 0),
        "unpaid_amount": float(r.unpaid_amount or 0),
    } for r in rows]
