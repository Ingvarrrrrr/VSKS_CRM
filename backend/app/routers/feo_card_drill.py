# -*- coding: utf-8 -*-
"""GET /api/subsidies/{subsidy_id}/card-drill — «из чего сложено» число
карточки дерева ФЭО (владелец, 07.10.2026, план .planning/quick/2026-10-07-
dnr-feo-cards/PLAN.md шаг 4). Вся формула — app.services.feo_card_drill
(ПРАВИЛО №6: один расчёт на карточку, эта ручка только отдаёт его наружу).

Видимость/права — ТОТ ЖЕ canonical read-access гейт, что и GET /api/subsidies/
{subsidy_id} (видимые субсидии + фолбэк по видимой закупке этой субсидии для
исполнителя без вкладки «Субсидии», аудит безопасности 2026-09-29) — вторая
проверка видимости не вводится. Денежные поля зависят от того же action,
что и GET /api/feo-categories/plan-tree (feo_budget.view_tree_amounts) —
без него 403, а не null-поля (здесь ответ ЦЕЛИКОМ денежный, усечение не
имеет смысла)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.routers import feo_categories as fc
from app.services.feo_card_drill import CARDS, card_drill_rows

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


@router.get("/{subsidy_id}/card-drill")
async def get_card_drill(
    subsidy_id: int,
    card: str = Query(..., regex=rf"^({'|'.join(CARDS)})$"),
    kind: str = Query("all", regex="^(all|goods|services|payroll|unspecified)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Видимость — байт-в-байт тот же гейт, что GET /api/subsidies/{subsidy_id}
    # (app.routers.subsidies.get_subsidy, ПРАВИЛО №6).
    from app.auth.visibility import get_visible_subsidy_ids, build_visibility_clause
    visible = await get_visible_subsidy_ids(current_user, db)
    if visible is not None and subsidy_id not in visible:
        clause = await build_visibility_clause(current_user, db, "purchase")
        allowed = clause is None
        if clause is not None:
            cnt = (await db.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.subsidy_id == subsidy_id, clause
                )
            )).scalar() or 0
            allowed = cnt > 0
        if not allowed:
            raise HTTPException(status_code=404, detail="Subsidy not found")

    subsidy = (await db.execute(select(Subsidy.id).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if subsidy is None:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    can_view_amounts = await fc._has_feo_action(current_user, db, "feo_budget.view_tree_amounts")
    if not can_view_amounts:
        raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра сумм ФЭО")

    return await card_drill_rows(db, subsidy_id, card, kind)
