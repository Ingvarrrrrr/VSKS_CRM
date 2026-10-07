"""GET /api/feo-categories/row-contract-totals и GET /api/feo-categories/{cat_id}/row-drill
— строка дерева ФЭО «Законтрактовано/из них заказано/зарезервировано/не
распределено» (владелец, 06.10.2026, план
.planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаги 2-3). Вся арифметика —
app.services.feo_row_contracted (Правило №6 — этот файл только HTTP-обвязка:
права/видимость, разворот поддерева через уже существующий
feo_categories._collect_subtree_ids, сериализация ответа).

Права — ТЕ ЖЕ, что у /planned-purchase-totals (feo_plan_reads.py): только
get_current_user, без доп. гейта по роли — эти эндпоинты read-only и отдают
те же суммы, что уже видны в дереве ФЭО любому, кто видит саму субсидию
(subsidy_id/cat_id, не принадлежащий пользователю, просто не найдётся выше по
UI — отдельного фильтра видимости в planned-purchase-totals тоже нет).

Путь "/{cat_id}/row-drill" — короче "/{cat_id}/subtree"
(feo_categories.py), но длиннее голого "/{cat_id}" catch-all того же модуля
— порядок регистрации относительно feo_categories.router не важен (тот же
принцип, что и у feo_tree_ops.router, см. докстринг feo_categories.py).
"row-contract-totals" — путь БЕЗ {cat_id}, обязан регистрироваться ДО
feo_categories.router (иначе Starlette матчит его на catch-all GET "/{cat_id}"
первым, т.к. "row-contract-totals" синтаксически подходит под "{cat_id}" как
строку)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.routers.feo_categories import _collect_subtree_ids
from app.services.feo_row_contracted import feo_row_contract_totals, feo_row_drill
from sqlalchemy import select

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])

_VALID_KINDS = ("in_purchases", "contracted", "ordered", "reserved", "unallocated")


@router.get("/row-contract-totals")
async def get_row_contract_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """{"<cat_id>": {"contracted":, "ordered":, "reserved":}, ..., "none": {...}}
    — СОБСТВЕННЫЕ суммы категории (без поддерева, см. app.services.feo_row_contracted)."""
    totals = await feo_row_contract_totals(db, subsidy_id)
    return {("none" if cat_id is None else str(cat_id)): v for cat_id, v in totals.items()}


@router.get("/{cat_id}/row-drill")
async def get_row_drill(
    cat_id: int,
    subsidy_id: int = Query(...),
    kind: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Построчный список закупок, формирующих сумму строки дерева (по
    ПОДДЕРЕВУ cat_id) — `total` ОБЯЗАН совпадать с числом из
    row-contract-totals/planned-purchase-totals по тому же поддереву (см.
    инвариант-тест test_feo_row_contracted.py)."""
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"kind должен быть одним из {_VALID_KINDS}")

    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    cat_ids = await _collect_subtree_ids(cat_id, db)
    result = await feo_row_drill(db, subsidy_id=subsidy_id, cat_ids=cat_ids, kind=kind)
    return result
