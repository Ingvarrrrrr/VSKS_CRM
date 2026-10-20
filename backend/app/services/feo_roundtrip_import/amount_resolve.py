"""Сведение «сумма» vs «кол-во × цена за единицу» при загрузке «Выгрузить
ФЭО» (задача владельца 20.10.2026, п.3): файл может нести любое из двух —
только сумму, или кол-во и цену (сумма тогда считается), или оба сразу.

ПРАВИЛО №6: формула «кол-во × цена» не пишется здесь заново — зовём ТОТ ЖЕ
line_total (app.services.item_amounts), которым считает позиции закупки/
заявки. Используется И diff.py (предпросмотр — подставить эффективную сумму
в сравнение и предупредить о расхождении), И apply.py (та же эффективная
сумма реально пишется в БД) — второй копии правила на запись не заводим.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services.item_amounts import line_total

_EPS = Decimal("0.01")


def resolve_amount(
    qty: Optional[Decimal], price: Optional[Decimal], amount: Optional[Decimal],
) -> tuple[Optional[Decimal], Optional[str]]:
    """(эффективная_сумма, предупреждение_или_None).

    - сумма пуста, кол-во и цена заданы -> сумма = кол-во × цена;
    - сумма задана, кол-во и цена оба заданы, и |сумма - кол-во×цена| > 1 коп. ->
      сумма ИЗ ФАЙЛА (владелец: записывается как в файле) + текст предупреждения,
      НЕ ошибка;
    - иначе -> сумма как есть, без предупреждения."""
    if amount is None:
        if qty is not None and price is not None:
            return line_total(qty, price), None
        return None, None
    if qty is not None and price is not None:
        computed = line_total(qty, price)
        if abs(computed - Decimal(str(amount))) > _EPS:
            return amount, (
                f"сумма ({amount}) не совпадает с кол-во × цена "
                f"({qty} × {price} = {computed})"
            )
    return amount, None
