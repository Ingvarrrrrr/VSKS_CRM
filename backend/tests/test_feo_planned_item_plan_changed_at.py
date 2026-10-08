# -*- coding: utf-8 -*-
"""test_feo_planned_item_plan_changed_at.py — событие модели FeoPlannedItem
(app/models/feo_planned_item.py, before_insert/before_update), владелец
08.10.2026, план binary-crunching-island.md раздел 1: правка amount/quantity/
unit_price/item_type/feo_category_id/is_active двигает plan_changed_at на
«сейчас», правка названия — нет."""
import datetime as _dt
from decimal import Decimal

import pytest

from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


@pytest.mark.asyncio
async def test_plan_changed_at_set_on_insert(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    item = await _make_planned_item(db_session, cat.id, "Позиция", 1, 1000)
    assert item.plan_changed_at is not None


@pytest.mark.asyncio
async def test_plan_changed_at_moves_on_amount_change(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    item = await _make_planned_item(db_session, cat.id, "Позиция", 1, 1000)
    old_at = item.plan_changed_at
    await db_session.refresh(item)
    old_at = item.plan_changed_at

    item.amount = Decimal("2000")
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at >= old_at


@pytest.mark.asyncio
async def test_plan_changed_at_moves_on_item_type_change(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    item = await _make_planned_item(db_session, cat.id, "Позиция", 1, 1000)
    await db_session.refresh(item)
    old_at = item.plan_changed_at
    # Искусственно «отодвигаем» старое значение в прошлое, чтобы отличить
    # «не изменилось» от «изменилось, но сервер вернул ту же секунду».
    old_at_past = old_at - _dt.timedelta(days=1)
    item.plan_changed_at = old_at_past
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at == old_at_past

    item.item_type = "услуга"
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at > old_at_past


@pytest.mark.asyncio
async def test_plan_changed_at_untouched_on_name_change(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    item = await _make_planned_item(db_session, cat.id, "Позиция", 1, 1000)
    await db_session.refresh(item)
    old_at = item.plan_changed_at
    old_at_past = old_at - _dt.timedelta(days=1)
    item.plan_changed_at = old_at_past
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at == old_at_past

    item.name = "Позиция (переименована)"
    item.notes = "просто заметка"
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at == old_at_past


@pytest.mark.asyncio
async def test_plan_changed_at_moves_on_feo_category_change(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat1 = await _make_category(db_session, subsidy.id, name="Статья 1")
    cat2 = await _make_category(db_session, subsidy.id, name="Статья 2")
    item = await _make_planned_item(db_session, cat1.id, "Позиция", 1, 1000)
    await db_session.refresh(item)
    old_at = item.plan_changed_at
    old_at_past = old_at - _dt.timedelta(days=1)
    item.plan_changed_at = old_at_past
    await db_session.commit()
    await db_session.refresh(item)

    item.feo_category_id = cat2.id
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at > old_at_past


@pytest.mark.asyncio
async def test_explicit_plan_changed_at_not_overwritten_on_insert(db_session, test_org):
    """Скрипт set_plan_changed_at.py / бэкфилл задают историческое время
    явно — событие before_insert не должно его перетирать."""
    from app.models.feo_planned_item import FeoPlannedItem

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    explicit_dt = _dt.datetime(2026, 7, 1, 12, 0, 0)
    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Позиция историческая", quantity=Decimal("1"),
        amount=Decimal("1000"), plan_changed_at=explicit_dt,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    assert fpi.plan_changed_at == explicit_dt
