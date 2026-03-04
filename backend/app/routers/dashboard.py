from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user
from app.config import settings
from decimal import Decimal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/")
async def dashboard(db: AsyncSession = Depends(get_db)):
    # Get all categories
    cat_result = await db.execute(select(FeoCategory).order_by(FeoCategory.level, FeoCategory.id))
    cats = cat_result.scalars().all()

    # Get aggregated purchase data per feo_category_id
    agg = await db.execute(
        select(
            Purchase.feo_category_id,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("planned"),
            func.coalesce(func.sum(
                func.case((Purchase.confirmed == True, Purchase.final_total_amount), else_=0)
            ), 0).label("confirmed"),
            func.coalesce(func.sum(Purchase.delivery_payment_amount), 0).label("payment"),
        ).group_by(Purchase.feo_category_id)
    )
    agg_map = {}
    for row in agg:
        agg_map[row.feo_category_id] = {
            "total_planned": float(row.planned),
            "total_confirmed": float(row.confirmed),
            "total_payment": float(row.payment),
        }

    # Build tree
    by_id = {}
    for c in cats:
        by_id[c.id] = {
            "id": c.id, "name": c.name, "level": c.level, "code": c.code,
            "total_planned": 0, "total_confirmed": 0, "total_payment": 0,
            "children": []
        }
        if c.id in agg_map:
            by_id[c.id].update(agg_map[c.id])

    roots = []
    for c in cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)

    # Roll up totals
    def rollup(node):
        for child in node["children"]:
            rollup(child)
            node["total_planned"] += child["total_planned"]
            node["total_confirmed"] += child["total_confirmed"]
            node["total_payment"] += child["total_payment"]
    for r in roots:
        rollup(r)

    # Global totals
    total_obl_result = await db.execute(
        select(func.coalesce(func.sum(Purchase.final_total_amount), 0)).where(Purchase.confirmed == True)
    )
    total_obligations = float(total_obl_result.scalar() or 0)
    total_pay_result = await db.execute(
        select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
    )
    total_payments = float(total_pay_result.scalar() or 0)

    return {
        "subsidy_limit": settings.SUBSIDY_LIMIT,
        "total_obligations": total_obligations,
        "total_payments": total_payments,
        "remaining": settings.SUBSIDY_LIMIT - total_obligations,
        "categories": roots
    }


@router.get("/charts")
async def dashboard_charts(db: AsyncSession = Depends(get_db)):
    # Status counts for pie chart
    status_result = await db.execute(
        select(Purchase.status, func.count(Purchase.id).label("cnt"))
        .group_by(Purchase.status)
    )
    status_counts = {row.status: row.cnt for row in status_result}

    # Per-subsidy aggregated purchase data for bar chart
    # Join directly via Purchase.subsidy_id (purchases are linked directly to subsidies in this schema)
    subsidy_result = await db.execute(
        select(
            Subsidy.id,
            Subsidy.name,
            Subsidy.year,
            Subsidy.budget,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total_planned"),
            func.coalesce(func.sum(
                case((Purchase.confirmed == True, Purchase.final_total_amount), else_=0)
            ), 0).label("total_confirmed"),
            func.coalesce(func.sum(Purchase.delivery_payment_amount), 0).label("total_paid"),
        )
        .select_from(Subsidy)
        .outerjoin(Purchase, Purchase.subsidy_id == Subsidy.id)
        .group_by(Subsidy.id, Subsidy.name, Subsidy.year, Subsidy.budget)
        .order_by(Subsidy.year.desc(), Subsidy.name)
    )

    subsidy_stats = []
    for row in subsidy_result:
        subsidy_stats.append({
            "id": row.id,
            "name": row.name,
            "year": row.year,
            "budget": float(row.budget),
            "total_planned": float(row.total_planned),
            "total_confirmed": float(row.total_confirmed),
            "total_paid": float(row.total_paid),
        })

    return {
        "status_counts": status_counts,
        "subsidy_stats": subsidy_stats,
    }
