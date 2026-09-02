"""Владелец (2026-09-02), «Логистические услуги»: FeoPlannedItem получила
отдельное поле unit_price (миграция z1a2b3c4d5e6_feo_planned_item_unit_price.py).
Проверяем новую семантику assert_tz_not_over_plan (app/services/feo_plan.py):

  - unit_price ЗАПОЛНЕНА  -> план полноценный, amount = quantity × unit_price;
    проверяются количество, цена за единицу И сумма (прежнее поведение).
  - unit_price ПУСТА      -> amount сама по себе ИТОГОВАЯ сумма, деления
    amount/quantity больше НЕТ; количество ОРИЕНТИРОВОЧНОЕ и по нему НЕ
    ограничиваем, по цене за единицу тоже НЕ ограничиваем — единственное
    ограничение остаётся по сумме.

Фикстуры/стиль — по образцу test_feo_plan_tree_scenarios.py (_make_subsidy /
_make_category / _make_planned_item), настоящая AsyncSession из db_session
(conftest.py), не подставные объекты — assert_tz_not_over_plan делает
db.get(FeoPlannedItem, id), который подставными SimpleNamespace не проходит
(нужен реальный ORM-инстанс с реальным id)."""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_plan import assert_tz_not_over_plan


async def _make_subsidy(db_session, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, name, quantity, amount, unit_price=None):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)) if quantity is not None else None,
        unit="шт",
        amount=Decimal(str(amount)) if amount is not None else None,
        unit_price=Decimal(str(unit_price)) if unit_price is not None else None,
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _get_409(coro):
    try:
        await coro
    except Exception as e:  # HTTPException
        assert getattr(e, "status_code", None) == 409, f"ожидался 409, получено {e!r}"
        return e
    raise AssertionError("ожидался HTTPException 409, исключения не было")


# ---------------------------------------------------------------------------
# 1-2) unit_price ПУСТА — amount это ИТОГОВАЯ сумма, quantity ориентировочное.
# План: quantity=20 (ориентировочно), amount=200 000 (вся сумма).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_unit_price_allows_more_units_within_total_sum(db_session, test_org):
    """21 услуга на 150 000 при плане «примерно 20 услуг на 200 000» — НЕ
    блокируется: количество ориентировочное (превышено, 21 > 20, но по нему
    больше не ограничиваем), сумма 150 000 <= 200 000."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Логистические услуги")
    fpi = await _make_planned_item(
        db_session, cat.id, "Логистические услуги", quantity=20, amount=200_000, unit_price=None,
    )

    total = Decimal("150000")
    qty = Decimal("21")
    unit_price = total / qty
    await assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=fpi.id,
        feo_category_id=None,
        quantity=qty,
        unit_price=unit_price,
        total_price=total,
        item_name="Логистические услуги",
    )  # не должно бросить


@pytest.mark.asyncio
async def test_no_unit_price_blocks_when_total_sum_exceeded(db_session, test_org):
    """Та же плановая позиция (20 шт / 200 000 без unit_price) — покупка на
    250 000 БЛОКИРУЕТСЯ по сумме, 409."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Логистические услуги")
    fpi = await _make_planned_item(
        db_session, cat.id, "Логистические услуги", quantity=20, amount=200_000, unit_price=None,
    )

    total = Decimal("250000")
    qty = Decimal("21")
    unit_price = total / qty
    e = await _get_409(assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=fpi.id,
        feo_category_id=None,
        quantity=qty,
        unit_price=unit_price,
        total_price=total,
        item_name="Логистические услуги",
    ))
    assert "сумма" in str(e.detail)


@pytest.mark.asyncio
async def test_no_unit_price_blocks_by_sum_without_per_unit_complaint(db_session, test_org):
    """Живой случай прода: план quantity=1, amount=11 270.19 (без unit_price),
    ТЗ 48 935,05 — блокируется по СУММЕ, но в тексте НЕТ претензии по цене за
    единицу (деления amount/quantity больше нет)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Логистические услуги")
    fpi = await _make_planned_item(
        db_session, cat.id, "Логистические услуги",
        quantity=1, amount=Decimal("11270.19"), unit_price=None,
    )

    total = Decimal("48935.05")
    e = await _get_409(assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=fpi.id,
        feo_category_id=None,
        quantity=Decimal("1"),
        unit_price=total,
        total_price=total,
        item_name="Логистические услуги",
    ))
    message = str(e.detail)
    assert "сумма" in message
    assert "цена за единицу" not in message, (
        f"деления amount/quantity больше нет — цена за единицу не должна упоминаться: {message!r}"
    )


# ---------------------------------------------------------------------------
# 4-5) unit_price ЗАПОЛНЕНА — план полноценный, проверяются все три величины.
# План: unit_price=10 000, quantity=20 (итог 200 000).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_with_unit_price_blocks_by_per_unit_price(db_session, test_org):
    """unit_price=10 000 задана явно — позиция по 15 000/ед БЛОКИРУЕТСЯ по цене
    за единицу, как раньше (количество/сумма в пределах плана)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Оборудование")
    fpi = await _make_planned_item(
        db_session, cat.id, "Оборудование", quantity=20, amount=200_000, unit_price=10_000,
    )

    qty = Decimal("1")
    unit_price = Decimal("15000")
    e = await _get_409(assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=fpi.id,
        feo_category_id=None,
        quantity=qty,
        unit_price=unit_price,
        total_price=qty * unit_price,
        item_name="Оборудование",
    ))
    assert "цена за единицу" in str(e.detail)


@pytest.mark.asyncio
async def test_with_unit_price_blocks_by_quantity(db_session, test_org):
    """unit_price=10 000 задана явно — покупка 25 шт (при плане 20 шт)
    БЛОКИРУЕТСЯ по количеству. Цена за единицу и сумма намеренно в пределах
    плана (8 000 <= 10 000/ед, 25*8 000 = 200 000 == план), чтобы нарушение
    было изолированным именно по количеству."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Оборудование")
    fpi = await _make_planned_item(
        db_session, cat.id, "Оборудование", quantity=20, amount=200_000, unit_price=10_000,
    )

    qty = Decimal("25")
    unit_price = Decimal("8000")
    e = await _get_409(assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=fpi.id,
        feo_category_id=None,
        quantity=qty,
        unit_price=unit_price,
        total_price=qty * unit_price,
        item_name="Оборудование",
    ))
    message = str(e.detail)
    assert "количество" in message
    assert "цена за единицу" not in message
    assert "сумма" not in message
