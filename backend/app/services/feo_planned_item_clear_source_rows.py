"""clear_source_rows — «Убрать номера строк файла» (владелец, 12.10.2026,
план lazy-swimming-hollerith.md п.4г): кнопка у плана субсидии обнуляет
FeoPlannedItem.source_row у ВСЕХ позиций субсидии и parts[].row у каждой
части объединённой позиции — подписи «строка N файла» (FeoLevel5Panel.vue)
исчезают. parts[].key НЕ трогается — привязки закупок к частям
(purchase_items.feo_plan_part_key) переживают эту операцию, их читает
feo_plan_part_purchases.py по key, не по row.

Права — ADMIN_ROLES (администратор организации и выше), гейт ЗДЕСЬ, не
дублируется второй проверкой в роутере (ПРАВИЛО №6 — единственная точка
решения, роутер только вызывает); сам предикат совпадает с тем, что уже
применяет feo_import_runs.py::_check_subsidy_read_access (has_role_via_
hierarchy(*ADMIN_ROLES, org_id=...)), второй механизм иерархии не заводим.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import ADMIN_ROLES, has_role_via_hierarchy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy
from app.models.user import User


class ClearSourceRowsForbidden(Exception):
    """Недостаточно прав — роутер превращает в HTTPException(403)."""


async def assert_can_clear_source_rows(user: User, db: AsyncSession, subsidy_id: int) -> None:
    subsidy_org_id = (await db.execute(
        select(Subsidy.org_id).where(Subsidy.id == subsidy_id)
    )).scalar_one_or_none()
    if not await has_role_via_hierarchy(user, db, *ADMIN_ROLES, org_id=subsidy_org_id):
        raise ClearSourceRowsForbidden(
            "Убрать номера строк файла может только администратор организации"
        )


async def clear_source_rows(db: AsyncSession, subsidy_id: int) -> dict:
    """Обнуляет source_row всех FeoPlannedItem субсидии и parts[].row каждой
    части (key НЕ трогается — ПРАВИЛО №6, привязки закупок читают part по
    key, не по row, см. feo_plan_part_purchases.py). Возвращает
    {cleared_items, cleared_parts} — числа для тоста подтверждения."""
    items = (await db.execute(
        select(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()

    cleared_items = 0
    cleared_parts = 0
    for it in items:
        changed = False
        if it.source_row is not None:
            it.source_row = None
            changed = True
        parts = it.parts or []
        if parts and any(p.get("row") is not None for p in parts):
            new_parts = []
            for p in parts:
                if p.get("row") is not None:
                    cleared_parts += 1
                new_parts.append({**p, "row": None})
            it.parts = new_parts
            changed = True
        if changed:
            cleared_items += 1

    await db.flush()
    return {"cleared_items": cleared_items, "cleared_parts": cleared_parts}
