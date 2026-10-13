"""Правка ОДНОЙ части объединённой плановой позиции (владелец, 13.10.2026,
«План закупок» → «План vs факт» → строка «Как запланировано»).

FeoPlannedItem.parts — [{key, row, qty, unit, unit_price, amount}], состав
объединённой позиции (см. докстринг модели и app/services/
feo_import_duplicates.py::_build_parts, Правило №6 — единственное место,
где parts собираются ЦЕЛИКОМ при загрузке плана). Эта правка — ВТОРОЕ, но не
конкурирующее место записи: редактирует РОВНО ОДИН элемент списка руками,
после загрузки, а не пересобирает список с нуля.

Правило позиции (владелец, задача): Σ amount ВСЕХ частей позиции (и
запланированных, и тех, по которым уже есть закупка — feo_plan_part_key на
PurchaseItem) не может быть больше плана позиции (FeoPlannedItem.amount).
Часть, по которой уже есть закупка (committed_part_keys ниже), не
редактируется вовсе — у неё есть собственная закупка со своими цифрами,
значение part.qty/unit_price/amount на этот момент уже историческое.

Права — ТЕ ЖЕ, что у PUT /feo-planned-items/{id} (require_tab('feo_categories')
на роутере) + тот же гейт корректировки утверждённой субсидии
(subsidy_revision_guard.assert_direct_edit) — вызываются в роутере, здесь
только тело правки (Правило №6 — второй проверки прав не заводим).

plan_changed_at НЕ трогается: _PLAN_CHANGED_AT_WATCHED_FIELDS
(app/models/feo_planned_item.py) не включает parts, а эта правка не меняет
FeoPlannedItem.amount/quantity/unit_price самой позиции — только состав
parts, который в арифметике дерева плана/контроля превышения не участвует
(см. докстринг FeoPlannedItem.feo_quantity про parts/feo_* — дерево считает
quantity/unit_price/amount позиции, не parts).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase_item import PurchaseItem
from app.services import feo_history


class FeoPlannedItemPartUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    # Можно ввести ТОЛЬКО сумму (без кол-ва/цены) — задача владельца, п.
    # «можно ввести только сумму». Если заданы и quantity, и unit_price —
    # amount игнорируется на входе и считается сервером (кол-во × цена),
    # тот же приём, что и у самой плановой позиции (editAmountIsComputed,
    # useFeoPlannedItemEditDialog.ts) — Правило №6, та же формула словами.
    amount: Optional[Decimal] = None


def _fmt_money(d: Decimal) -> str:
    return f"{d:,.2f} ₽"


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (InvalidOperation, ValueError, TypeError):
        return None


async def _committed_part_keys(db: AsyncSession, item_id: int) -> set[str]:
    """Ключи частей позиции `item_id`, у которых уже есть хотя бы одна строка
    закупки (PurchaseItem.feo_plan_part_key) — ТА ЖЕ привязка, что заполняет
    импорт факта и читает app/services/feo_plan_part_purchases.py (Правило
    №6, второй способ узнать «есть ли закупка у части» не заводим)."""
    rows = (await db.execute(
        select(PurchaseItem.feo_plan_part_key)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .where(PurchaseItem.feo_plan_part_key.isnot(None))
        .distinct()
    )).scalars().all()
    return {k for k in rows if k}


class PartEditForbidden(Exception):
    """Часть уже закуплена — редактирование недоступно (409)."""


class PartNotFound(Exception):
    pass


async def update_planned_item_part(
    db: AsyncSession,
    user,
    item: FeoPlannedItem,
    part_key: str,
    data: FeoPlannedItemPartUpdate,
) -> FeoPlannedItem:
    """Тело PATCH /feo-planned-items/{id}/parts/{key} — без прав доступа/гейта
    субсидии и без commit (см. докстринг модуля). `item` — уже загруженная
    позиция. Бросает PartNotFound (→ 404), PartEditForbidden (→ 409, часть
    закуплена) или HTTPException(409) при превышении плана позиции."""
    parts = list(item.parts or [])
    idx = next((i for i, p in enumerate(parts) if p.get("key") == part_key), None)
    if idx is None:
        raise PartNotFound(f"Часть «{part_key}» не найдена в составе позиции")

    committed = await _committed_part_keys(db, item.id)
    if part_key in committed:
        raise PartEditForbidden(
            "По этой части уже есть закупка — редактирование доступно только "
            "для частей, по которым закупки ещё нет"
        )

    old_part = dict(parts[idx])

    qty = data.quantity
    unit_price = data.unit_price
    if qty is not None and unit_price is not None:
        amount = (qty * unit_price).quantize(Decimal("0.01"))
    else:
        amount = data.amount

    new_part = {
        **old_part,
        "qty": _num(qty) if qty is not None else old_part.get("qty"),
        "unit": data.unit if data.unit is not None else old_part.get("unit"),
        "unit_price": _num(unit_price) if unit_price is not None else old_part.get("unit_price"),
        "amount": _num(amount) if amount is not None else old_part.get("amount"),
    }
    # part.key НЕ меняется (привязки закупок по key переживают эту правку).
    new_part["key"] = old_part["key"]

    candidate_parts = list(parts)
    candidate_parts[idx] = new_part
    parts_total = sum(Decimal(str(p["amount"])) for p in candidate_parts if p.get("amount") is not None)

    if item.amount is not None and parts_total > item.amount:
        excess = parts_total - item.amount
        raise HTTPException(
            409,
            f"Сумма частей превышает план позиции на {_fmt_money(excess)} — увеличьте план позиции",
        )

    item.parts = candidate_parts

    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_ITEM, item.id, user,
        {f"part_{part_key}": old_part},
        {f"part_{part_key}": new_part},
        source=feo_history.SOURCE_MANUAL,
        commit=False,
    )
    return item
