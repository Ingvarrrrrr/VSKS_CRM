"""Владелец, 30.09.2026: «Багажник экспедиционный STC» — плановое количество
2→4, цена за единицу не зафиксирована, сумма плана осталась 169 000 ₽ вместо
пересчёта. backfill_unit_price_on_quantity_change (app/services/
feo_planned_item_amount.py) — единственное место автопересчёта (PUT
/feo-planned-items/{id}, one_time-режим), см. её докстринг.
"""
from decimal import Decimal
from types import SimpleNamespace

from app.services.feo_planned_item_amount import (
    backfill_unit_price_on_quantity_change,
    effective_plan_unit_price,
)


def test_owner_example_backfills_unit_price_and_recomputes_amount():
    # qty 2→4, unit_price не задан, сумма пришла НЕТРОНУТОЙ (169000) — как
    # присылает фронт, когда правили только количество (PlannedItemEditDialog.vue
    # не пересчитывает сумму без явной цены за единицу).
    amount, unit_price = backfill_unit_price_on_quantity_change(
        old_quantity=Decimal("2"), old_amount=Decimal("169000"), old_unit_price=None,
        new_quantity=Decimal("4"), new_amount=Decimal("169000"), new_unit_price=None,
    )
    assert unit_price == Decimal("84500.00")
    assert amount == Decimal("338000.00")


def test_explicit_unit_price_wins_no_backfill():
    """unit_price задан явно — фронт уже прислал верную сумму, второй расчёт не
    заводим (Правило №6), функция возвращает вход как есть."""
    amount, unit_price = backfill_unit_price_on_quantity_change(
        old_quantity=Decimal("2"), old_amount=Decimal("169000"), old_unit_price=None,
        new_quantity=Decimal("4"), new_amount=Decimal("400000"), new_unit_price=Decimal("100000"),
    )
    assert unit_price == Decimal("100000")
    assert amount == Decimal("400000")


def test_explicit_amount_change_is_not_overwritten():
    """Пользователь сам поменял сумму (не равна старой) — не перетираем её
    подразумеваемой ценой, даже если количество тоже изменилось."""
    amount, unit_price = backfill_unit_price_on_quantity_change(
        old_quantity=Decimal("2"), old_amount=Decimal("169000"), old_unit_price=None,
        new_quantity=Decimal("4"), new_amount=Decimal("250000"), new_unit_price=None,
    )
    assert amount == Decimal("250000")
    assert unit_price is None


def test_quantity_unchanged_no_backfill():
    amount, unit_price = backfill_unit_price_on_quantity_change(
        old_quantity=Decimal("2"), old_amount=Decimal("169000"), old_unit_price=None,
        new_quantity=Decimal("2"), new_amount=Decimal("169000"), new_unit_price=None,
    )
    assert amount == Decimal("169000")
    assert unit_price is None


def test_no_old_amount_or_quantity_no_backfill():
    """Раньше не было ни количества, ни суммы (новая/пустая позиция) — считать
    подразумеваемую цену не из чего, отдаём вход как есть."""
    amount, unit_price = backfill_unit_price_on_quantity_change(
        old_quantity=None, old_amount=None, old_unit_price=None,
        new_quantity=Decimal("4"), new_amount=Decimal("169000"), new_unit_price=None,
    )
    assert amount == Decimal("169000")
    assert unit_price is None


def test_effective_plan_unit_price_derives_from_amount_when_unit_price_null():
    """Субсидия «Абхазия», позиция «Катер» (id=5730): quantity=1, amount=4 484 400,
    unit_price=None — подразумеваемая плановая цена за единицу = 4 484 400.00."""
    kater = SimpleNamespace(quantity=Decimal("1.0000"), unit_price=None, amount=Decimal("4484400.00"))
    assert effective_plan_unit_price(kater) == Decimal("4484400.00")

    multi = SimpleNamespace(quantity=Decimal("4"), unit_price=None, amount=Decimal("338000.00"))
    assert effective_plan_unit_price(multi) == Decimal("84500.00")

    explicit = SimpleNamespace(quantity=Decimal("4"), unit_price=Decimal("80000.00"), amount=Decimal("338000.00"))
    assert effective_plan_unit_price(explicit) == Decimal("80000.00")

    empty = SimpleNamespace(quantity=Decimal("1"), unit_price=None, amount=None)
    assert effective_plan_unit_price(empty) is None

