from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.auth.jwt import get_current_user
from app.config import settings
from decimal import Decimal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/")
async def dashboard(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
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
