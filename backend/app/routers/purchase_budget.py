"""
purchase_budget.py — Helper-only module (no router, no endpoints).

Contains budget-validation and framework-sequence helpers extracted from
purchases.py per refactor Plan 16-04 (D-05 + D-19).

Design decisions
----------------
- D-05: helpers that are shared across multiple CRUD routers live in their own
  module so both purchases.py and (future) purchase_transitions.py can import
  without circular imports.
- D-19: helper stays in the originating module; others import from here.
- NO APIRouter instance — this module is never passed to include_router().
- NOT registered in backend/app/__init__.py.

Public API
----------
FRAMEWORK_TYPES          set[str]   — contract types that carry framework seq
_assign_framework_seq    coroutine  — auto-fills framework_seq on a Purchase
_check_budget            coroutine  — raises 422 if subsidy budget exceeded

Downstream consumers (import from this module)
-----------------------------------------------
- app.routers.purchases          (create / update endpoints)
- app.routers.purchase_transitions  (Plan 16-06, future)

FEO cap helpers
---------------
No FEO cap helpers were found in purchases.py at the time of extraction
(grep for feo_cap / FEO_CAP / feo_limit returned 0 matches). If FEO cap
validation is added later it should live here alongside _check_budget.
"""
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from decimal import Decimal

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRAMEWORK_TYPES: set = {"framework_cumulative", "framework_with_amount"}
"""Contract purchase_contract_type values that trigger framework sequencing."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assign_framework_seq(
    p: Purchase,
    db: AsyncSession,
    exclude_id: Optional[int] = None,
) -> None:
    """Auto-assign framework_seq if purchase belongs to a framework contract and seq is not set.

    No-op when:
    - purchase_contract_type is not in FRAMEWORK_TYPES
    - purchase has no contract_id
    - framework_seq is already set (manual override is respected)

    Args:
        p: Purchase ORM instance (mutated in place).
        db: Active async DB session.
        exclude_id: Purchase ID to exclude from the MAX query (used during
            UPDATE so the current row does not count against itself).
    """
    if p.purchase_contract_type not in FRAMEWORK_TYPES or not p.contract_id:
        return
    if p.framework_seq is not None:
        return  # already set (manual override)
    q = select(func.coalesce(func.max(Purchase.framework_seq), 0)).where(
        Purchase.contract_id == p.contract_id
    )
    if exclude_id:
        q = q.where(Purchase.id != exclude_id)
    result = await db.execute(q)
    p.framework_seq = (result.scalar() or 0) + 1


async def _check_budget(
    subsidy_id: Optional[int],
    amount: Optional[Decimal],
    exclude_pid: Optional[int],
    db: AsyncSession,
    feo_items: Optional[list] = None,
    is_admin: bool = False,
) -> None:
    """Raises 422 if adding `amount` to subsidy total would exceed its budget.

    Args:
        subsidy_id: ID of the Subsidy to check against. If None, returns silently.
        amount: The planned_total_price being added/updated. If None, returns silently.
        exclude_pid: Purchase ID to exclude from the running SUM.
        db: Active async DB session.
        feo_items: list of {"feo_planned_item_id": int, "amount": Decimal} for per-item check.
        is_admin: If True, skip FEO-item-level check (admin bypass).

    Raises:
        HTTPException(422): When budget exceeded.
    """
    # ── 1. Subsidy-level check (unchanged) ──
    if subsidy_id and amount:
        subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
        subsidy = subsidy_r.scalar_one_or_none()
        if subsidy:
            q = select(func.coalesce(func.sum(Purchase.planned_total_price), 0)).where(
                Purchase.subsidy_id == subsidy_id
            )
            if exclude_pid:
                q = q.where(Purchase.id != exclude_pid)
            total_r = await db.execute(q)
            total = Decimal(str(total_r.scalar() or 0))
            amt = Decimal(str(amount))
            budget = Decimal(str(subsidy.budget))
            if total + amt > budget:
                remaining = budget - total
                raise HTTPException(
                    422,
                    f"Превышение бюджета субсидии «{subsidy.name}». "
                    f"Доступно: {remaining:,.2f} ₽, запрашивается: {amt:,.2f} ₽"
                )

    # ── 2. FEO-item-level check (non-admin only) ──
    if is_admin or not feo_items:
        return

    from app.models.feo_planned_item import FeoPlannedItem as _FPI

    for entry in feo_items:
        fpi_id = entry.get("feo_planned_item_id")
        item_amount = entry.get("amount")
        if not fpi_id or not item_amount:
            continue

        planned = (await db.execute(
            select(_FPI).where(_FPI.id == fpi_id)
        )).scalar_one_or_none()
        if not planned or not planned.amount:
            continue

        used_q = select(
            func.coalesce(func.sum(PurchaseItem.total_price), 0)
        ).join(Purchase, PurchaseItem.purchase_id == Purchase.id).where(
            PurchaseItem.feo_planned_item_id == fpi_id
        )
        if exclude_pid:
            used_q = used_q.where(Purchase.id != exclude_pid)
        used = Decimal(str((await db.execute(used_q)).scalar() or 0))
        new_amt = Decimal(str(item_amount))

        if used + new_amt > Decimal(str(planned.amount)):
            remaining = Decimal(str(planned.amount)) - used
            raise HTTPException(
                422,
                f"Превышение плана по позиции «{planned.name}». "
                f"Доступный остаток: {remaining:,.2f} ₽, запрашивается: {new_amt:,.2f} ₽"
            )
