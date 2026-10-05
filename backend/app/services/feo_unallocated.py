"""Найти или создать категорию ФЭО «Не определена» для субсидии — ПРАВИЛО №6,
единственное место этой логики.

Вынесено из app/routers/feo_categories.py::get_or_create_unallocated (эндпоинт
POST /api/feo-categories/unallocated, B3) — задача «Контрольные суммы выписка
↔ закупки» (.planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1):
app/services/purchase_from_bank_payment.py тоже заводит закупку без выбранного
направления ФЭО и должен попадать в ТУ ЖЕ папку «Не определена», а не плодить
вторую копию find-or-create (было ровно это на проде с категорией 3716,
lesson project_hierarchy_read_only_inheritance соседняя — «закупка сама
становится планом»).

Эта функция — только ORM find-or-create + запись в историю ФЭО, БЕЗ проверки
прав (права — на вызывающем: роутер feo_categories.py делает
_check_unallocated_write_access, purchase_from_bank_payment.py уже находится
внутри операции, разрешённой subsidy.edit). db.flush() делает сама (нужен id
для истории), db.commit() — на вызывающем.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services import feo_history

_UNALLOCATED_NAMES = ("не определена", "нераспределённое", "нераспределенное")


async def get_or_create_unallocated(
    db: AsyncSession,
    subsidy_id: int,
    parent_id: Optional[int] = None,
    *,
    current_user=None,
    source: Optional[str] = None,
) -> tuple[FeoCategory, bool]:
    """Вернуть (категория, created) — существующую категорию «Не определена»/
    «Нераспределённое» в пределах subsidy_id (+ parent_id, если задан), либо
    создать новую (тогда created=True).

    current_user — для записи в историю ФЭО (feo_history.record_created);
    None допустим для системных вызовов без пользователя (тогда запись в
    историю не делается — см. ниже).
    """
    parent: Optional[FeoCategory] = None
    if parent_id is not None:
        parent = (await db.execute(
            select(FeoCategory).where(FeoCategory.id == parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != subsidy_id:
            raise HTTPException(
                status_code=422,
                detail="Родительская категория относится к другой субсидии",
            )

    stmt = (
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(FeoCategory.is_active.is_(True))
        .where(func.lower(FeoCategory.name).in_(_UNALLOCATED_NAMES))
    )
    if parent_id is None:
        stmt = stmt.where(FeoCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(FeoCategory.parent_id == parent_id)

    existing = (await db.execute(stmt.order_by(FeoCategory.id).limit(1))).scalars().first()
    if existing:
        return existing, False

    new_level = (parent.level + 1) if parent is not None else 1
    new_cat = FeoCategory(
        name="Не определена",
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=new_level,
        sort_order=9999,
        is_active=True,
    )
    db.add(new_cat)
    await db.flush()
    if current_user is not None:
        await feo_history.record_created(
            db, feo_history.ENTITY_FEO_CATEGORY, new_cat.id, current_user,
            source=source or feo_history.SOURCE_MANUAL, commit=False,
        )
    return new_cat, True
