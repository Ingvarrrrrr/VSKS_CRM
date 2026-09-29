"""Единственное место, пересчитывающее amount/unit_price плановой позиции
(FeoPlannedItem, one_time-режим) при правке КОЛИЧЕСТВА без явной цены за
единицу (владелец, 30.09.2026: «Багажник экспедиционный», план 2→4, сумма
плана осталась 169 000 ₽, хотя количество удвоилось).

Правило:
  unit_price задан на входе (data.unit_price is not None) — ничего не трогаем,
  фронт уже прислал amount = quantity × unit_price (PlannedItemEditDialog.vue::
  recalcEditAmountFromUnitPrice) — тут второй такой же расчёт не заводим
  (Правило №6).

  unit_price НЕ задан, но у позиции ДО правки были qty>0 и amount>0 (т.е.
  фактически подразумевалась цена за единицу, просто её не зафиксировали),
  количество РЕАЛЬНО меняется, а сумма явно НЕ менялась пользователем (осталась
  равна старой) — считаем, что пользователь правил только количество: фиксируем
  подразумевавшуюся цену (old_amount / old_qty) и пересчитываем сумму по новому
  количеству. «Явно поменял сумму» — единственный случай, когда авторасчёт НЕ
  трогает amount/unit_price: пользователь мог намеренно ввести новую сумму, не
  привязанную к цене за единицу.

Используется ТОЛЬКО update_planned_item (PUT) — у create_planned_item нет
«старых» значений для сравнения, там принимается ровно то, что прислал клиент.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.services.item_amounts import line_total

_CENTS = Decimal("0.01")


def _dec_or_none(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def backfill_unit_price_on_quantity_change(
    *, old_quantity, old_amount, old_unit_price,
    new_quantity, new_amount, new_unit_price,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Возвращает (amount, unit_price), которые нужно реально записать.

    Если условия автопересчёта не выполнены — возвращает (new_amount,
    new_unit_price) без изменений (штатный путь, сумма/цена приходят как есть)."""
    if new_unit_price is not None:
        return new_amount, new_unit_price

    old_qty_d = _dec_or_none(old_quantity)
    old_amount_d = _dec_or_none(old_amount)
    new_qty_d = _dec_or_none(new_quantity)
    new_amount_d = _dec_or_none(new_amount)

    if old_qty_d is None or old_qty_d <= 0 or old_amount_d is None or old_amount_d <= 0:
        return new_amount, new_unit_price
    if new_qty_d is None or new_qty_d == old_qty_d:
        return new_amount, new_unit_price  # количество не менялось — нечего пересчитывать
    amount_untouched = new_amount_d is not None and new_amount_d == old_amount_d
    if not amount_untouched:
        return new_amount, new_unit_price  # пользователь явно поменял сумму — не перетираем

    implied_unit_price = (old_amount_d / old_qty_d).quantize(_CENTS, rounding=ROUND_HALF_UP)
    recomputed_amount = line_total(new_qty_d, implied_unit_price)
    return recomputed_amount, implied_unit_price
