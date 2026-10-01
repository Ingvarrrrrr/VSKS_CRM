"""Задача «Составная плановая позиция» (владелец, решение 2026-10-01).

Сценарий: плановая позиция «Проживание и питание участников…» на 133 чел.
(quantity=133, unit_price=2000, amount=266000). В договоре ДВЕ строки закупки
— «Услуги по организации проживания» 133×1265 и «Услуга по организации
питания» 133×735, ОБЕ привязаны (PurchaseItem.feo_planned_item_id) к ОДНОЙ
плановой позиции.

ДО этой задачи assert_tz_batch_not_over_plan (app/services/feo_plan_tz_checks.py)
и planned_item_consumption (app/services/feo_plan_fact.py) складывали
количество строк группы (133+133=266 > 133 план) → ложный 409 «ТЗ выше
плана» и residual_quantity = -133.

is_composite=True (FeoPlannedItem.is_composite) переключает агрегацию ГРУППЫ
строк одной закупки на ту же плановую позицию (см. composite_group_metrics,
app/services/feo_plan_common.py, ПРАВИЛО №6):
  - количество группы = MAX количеств строк (133, не 266);
  - цена за единицу группы = СУММА цен за единицу строк (1265+735=2000,
    сравнивается с unit_price плана);
  - сумма группы — без изменений (сумма сумм).

Фикстуры — по образцу test_excess_total_not_per_branch.py/
test_planned_item_unit_price.py (настоящая AsyncSession из db_session,
conftest.py; assert_tz_batch_not_over_plan и planned_item_consumption делают
реальные SQL-запросы, подставные объекты не проходят).

Известный флейк pytest-asyncio «different loop» (см. tests/conftest.py) —
гонять тесты этого файла по одному при диагностике
(pytest tests/test_feo_composite_plan_item.py::<name>), пачкой тоже должно
проходить штатно.
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.feo_plan import assert_tz_batch_not_over_plan
from app.services.feo_plan_fact import planned_item_consumption


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"Composite-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=Decimal("1000000")):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=f"Категория-{uuid.uuid4().hex[:8]}",
        budget=budget,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(
    db_session, feo_category_id, *, quantity, unit_price, amount, is_composite,
):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name="Проживание и питание участников",
        quantity=Decimal(str(quantity)),
        unit="чел",
        unit_price=Decimal(str(unit_price)),
        amount=Decimal(str(amount)),
        is_active=True,
        is_composite=is_composite,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_purchase_with_two_items(
    db_session, subsidy_id, cat_id, fpi_id, *, qty_a, price_a, qty_b, price_b,
    status="plan_schedule",
):
    """Договор с ДВУМЯ строками (проживание/питание), обе привязаны к fpi_id."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=cat_id,
        item_name="Проживание и питание участников",
        status=status,
    )
    db_session.add(p)
    await db_session.flush()

    total_a = Decimal(str(qty_a)) * Decimal(str(price_a))
    total_b = Decimal(str(qty_b)) * Decimal(str(price_b))
    pi_a = PurchaseItem(
        purchase_id=p.id,
        item_name="Услуги по организации проживания",
        quantity=Decimal(str(qty_a)),
        unit="чел",
        unit_price=Decimal(str(price_a)),
        total_price=total_a,
        feo_category_id=cat_id,
        feo_planned_item_id=fpi_id,
        over_plan=False,
    )
    pi_b = PurchaseItem(
        purchase_id=p.id,
        item_name="Услуга по организации питания",
        quantity=Decimal(str(qty_b)),
        unit="чел",
        unit_price=Decimal(str(price_b)),
        total_price=total_b,
        feo_category_id=cat_id,
        feo_planned_item_id=fpi_id,
        over_plan=False,
    )
    db_session.add(pi_a)
    db_session.add(pi_b)
    await db_session.commit()
    await db_session.refresh(pi_a)
    await db_session.refresh(pi_b)
    return p, pi_a, pi_b


@pytest.mark.asyncio
async def test_composite_two_lines_no_409_and_zero_residual(db_session, test_org):
    """Составная позиция (133 чел., unit_price=2000, amount=266000): строки
    133×1265 (проживание) + 133×735 (питание) — количество группы MAX=133
    (не 266), цена за единицу группы 1265+735=2000 (== план, не выше) →
    assert_tz_batch_not_over_plan НЕ бросает 409; residual_quantity = 0."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(
        db_session, cat.id, quantity=133, unit_price=2000, amount=266000, is_composite=True,
    )
    _, pi_a, pi_b = await _make_purchase_with_two_items(
        db_session, subsidy.id, cat.id, fpi.id,
        qty_a=133, price_a=1265, qty_b=133, price_b=735,
    )

    await assert_tz_batch_not_over_plan(db_session, [pi_a, pi_b])  # не должно бросить

    consumption = await planned_item_consumption(db_session, [fpi.id])
    consumed_qty = consumption[fpi.id]["used_qty"]
    residual_quantity = float(fpi.quantity) - consumed_qty
    assert consumed_qty == pytest.approx(133.0), (
        f"составная позиция: расход по количеству = MAX(133, 133) = 133, получено {consumed_qty}"
    )
    assert residual_quantity == pytest.approx(0.0), (
        f"остаток по количеству обязан быть 0 (133 план - 133 расход), получено {residual_quantity}"
    )


@pytest.mark.asyncio
async def test_non_composite_same_lines_blocks_by_quantity(db_session, test_org):
    """Контроль: ТА ЖЕ пара строк (133+133), но is_composite=False — старая
    формула (сумма количеств) возвращается: 266 > 133 план → 409 по
    количеству. Поведение БЕЗ составного режима не изменилось ни на копейку."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(
        db_session, cat.id, quantity=133, unit_price=2000, amount=266000, is_composite=False,
    )
    _, pi_a, pi_b = await _make_purchase_with_two_items(
        db_session, subsidy.id, cat.id, fpi.id,
        qty_a=133, price_a=1265, qty_b=133, price_b=735,
    )

    with pytest.raises(HTTPException) as exc_info:
        await assert_tz_batch_not_over_plan(db_session, [pi_a, pi_b])
    assert exc_info.value.status_code == 409
    assert "количество" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_composite_price_sum_over_plan_blocks_by_price(db_session, test_org):
    """Составная позиция (133 чел., unit_price=2000): строки 133×1500
    (проживание) + 133×735 (питание) — сумма цен за единицу 1500+735=2235 >
    план 2000 → 409 по цене за единицу (количество группы = MAX = 133, в
    пределах плана — нарушение изолированно по цене)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(
        db_session, cat.id, quantity=133, unit_price=2000, amount=266000, is_composite=True,
    )
    _, pi_a, pi_b = await _make_purchase_with_two_items(
        db_session, subsidy.id, cat.id, fpi.id,
        qty_a=133, price_a=1500, qty_b=133, price_b=735,
    )

    with pytest.raises(HTTPException) as exc_info:
        await assert_tz_batch_not_over_plan(db_session, [pi_a, pi_b])
    assert exc_info.value.status_code == 409
    message = str(exc_info.value.detail)
    assert "цена за единицу" in message
    assert "количество" not in message, (
        f"количество группы (MAX=133) в пределах плана — нарушение должно быть изолированно по цене: {message!r}"
    )
