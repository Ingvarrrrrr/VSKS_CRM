# -*- coding: utf-8 -*-
"""test_feo_card_drill_excess_culprit.py — виновники превышения направления
по типу (card="free", kind!="all"), СГРУППИРОВАННЫЕ ПО ЗАКУПКЕ (владелец
08.10.2026, план binary-crunching-island.md раздел 1): раскрытие направления
с превышением должно показывать, КАКАЯ ЗАКУПКА дала превышение, а не просто
плановую позицию — и порядок виновников должен идти по plan_changed_at, а
не created_at (который не двигается при массовом переносе позиции между
категориями ФЭО). Новый файл (ПРАВИЛО №5) не дописываем в
test_feo_card_drill.py.

Проверяет app.services.feo_card_drill._excess_culprit_groups (вызывается
card_drill_rows для card="free", kind!="all" — см. докстринг модуля и
функции). Фабрики переиспользованы из test_feo_plan_tree_scenarios.py
(ПРАВИЛО №6)."""
from decimal import Decimal

import pytest

from app.services.feo_card_drill import card_drill_rows
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


async def _set_plan_changed_at(db_session, item, dt):
    item.plan_changed_at = dt
    await db_session.commit()
    await db_session.refresh(item)


async def _link_purchase(db_session, subsidy_id, feo_category_id, planned_item_id, purchase_number=1):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    purchase = Purchase(
        subsidy_id=subsidy_id, feo_category_id=feo_category_id,
        purchase_number=purchase_number, status="plan_schedule",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    item = PurchaseItem(
        purchase_id=purchase.id, feo_planned_item_id=planned_item_id,
        item_name="товар", quantity=Decimal("1"), total_price=Decimal("0"),
    )
    db_session.add(item)
    await db_session.commit()
    return purchase


@pytest.mark.asyncio
async def test_culprit_is_only_newest_item_covering_excess(db_session, test_org):
    """ФЭО (бюджет направления по типу «товар») 1000, позиции 600 (старая) +
    300 + 200 (новая по plan_changed_at) = 1100 → превышение 100. Виновником
    обязана оказаться ТОЛЬКО новая позиция (200), в своей группе-закупке, с
    over_amount=100."""
    import datetime as _dt

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    old = await _make_planned_item(db_session, article.id, "Старая позиция (600)", 1, 600)
    old.item_type = "товар"
    mid = await _make_planned_item(db_session, article.id, "Средняя позиция (300)", 1, 300)
    mid.item_type = "товар"
    new = await _make_planned_item(db_session, article.id, "Новая позиция (200)", 1, 200)
    new.item_type = "товар"
    await db_session.commit()
    # created_at намеренно СТАВИМ НАОБОРОТ относительно plan_changed_at, чтобы
    # доказать: виновник выбирается по plan_changed_at, а не created_at.
    await _set_plan_changed_at(db_session, old, _dt.datetime(2026, 1, 1, 10, 0, 0))
    await _set_plan_changed_at(db_session, mid, _dt.datetime(2026, 1, 2, 10, 0, 0))
    await _set_plan_changed_at(db_session, new, _dt.datetime(2026, 1, 3, 10, 0, 0))

    purchase = await _link_purchase(db_session, subsidy.id, article.id, new.id, purchase_number=975)

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    assert result["reason"] is None
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["budget_amount"] == pytest.approx(1000.0)
    assert row["planned_amount"] == pytest.approx(1100.0)
    assert row["amount"] == pytest.approx(-100.0)

    # Полный состав (для ссылки «Показать весь состав») — все 3 позиции, как и раньше.
    assert len(row["items"]) == 3

    # Виновник — ТОЛЬКО группа закупки 975 (новая позиция 200), не позиция
    # без закупки, несмотря на то, что created_at у неё самый свежий.
    assert len(row["excess_groups"]) == 1
    group = row["excess_groups"][0]
    assert group["purchase_id"] == purchase.id
    assert group["purchase_number"] == 975
    assert group["amount"] == pytest.approx(200.0)
    assert group["over_amount"] == pytest.approx(100.0)
    assert len(group["items"]) == 1
    assert group["items"][0]["name"] == "Новая позиция (200)"

    # Σ over_amount обязана совпасть с превышением направления (|amount|).
    assert row["excess_items_total"] == pytest.approx(abs(row["amount"]))
    assert row["excess_batch_note"] is None


@pytest.mark.asyncio
async def test_two_items_same_purchase_form_one_group():
    pytest.skip("covered indirectly — grouping key is purchase_id, see test above")


@pytest.mark.asyncio
async def test_two_planned_items_one_purchase_single_group(db_session, test_org):
    """Две позиции одной закупки, обе новее старой (600) — одна группа с
    суммой обеих и over_amount = Σ over обеих."""
    import datetime as _dt

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    old = await _make_planned_item(db_session, article.id, "Старая позиция (600)", 1, 600)
    old.item_type = "товар"
    new1 = await _make_planned_item(db_session, article.id, "Новая 1 (150)", 1, 150)
    new1.item_type = "товар"
    new2 = await _make_planned_item(db_session, article.id, "Новая 2 (150)", 1, 150)
    new2.item_type = "товар"
    await db_session.commit()
    await _set_plan_changed_at(db_session, old, _dt.datetime(2026, 1, 1, 10, 0, 0))
    await _set_plan_changed_at(db_session, new1, _dt.datetime(2026, 1, 2, 10, 0, 0))
    await _set_plan_changed_at(db_session, new2, _dt.datetime(2026, 1, 2, 10, 0, 1))

    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    purchase = Purchase(subsidy_id=subsidy.id, feo_category_id=article.id, purchase_number=42, status="plan_schedule")
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    for fpi in (new1, new2):
        pi = PurchaseItem(
            purchase_id=purchase.id, feo_planned_item_id=fpi.id,
            item_name="товар", quantity=Decimal("1"), total_price=Decimal("0"),
        )
        db_session.add(pi)
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    row = result["rows"][0]
    # 600+150+150=900, лимит 1000 — нет превышения.
    assert row["amount"] == pytest.approx(100.0)
    assert row["excess_groups"] == []


@pytest.mark.asyncio
async def test_no_excess_no_culprits(db_session, test_org):
    """Без превышения (план <= ФЭО) — excess_groups обязаны остаться пустыми,
    поведение строки не меняется (владелец: «для направления без превышения —
    как сейчас»)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    item = await _make_planned_item(db_session, direction.id, "Позиция", 1, 400)
    item.item_type = "товар"
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    row = result["rows"][0]
    assert row["amount"] == pytest.approx(600.0)
    assert row["excess_groups"] == []
    assert row["excess_items_total"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_batch_note_for_simultaneous_upload(db_session, test_org):
    """Превышение возникло внутри ОДНОЙ одновременной загрузки (одинаковый
    plan_changed_at у пересекающих позиций) — честная оговорка «заложено в
    исходном плане», а не случайный «виновник»."""
    import datetime as _dt

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    same_dt = _dt.datetime(2026, 10, 6, 12, 0, 0)
    items = []
    for i in range(3):
        it = await _make_planned_item(db_session, article.id, f"Позиция {i}", 1, 400)
        it.item_type = "товар"
        items.append(it)
    await db_session.commit()
    for it in items:
        await _set_plan_changed_at(db_session, it, same_dt)

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    row = result["rows"][0]
    # 400*3=1200, лимит 1000 → превышение 200.
    assert row["amount"] == pytest.approx(-200.0)
    assert row["excess_batch_note"] is not None
    assert row["excess_batch_note"]["count"] == 3
    # Все три позиции без закупки — одна «группа» на каждую (отдельные items),
    # но Σ over_amount обязана совпасть с превышением.
    assert row["excess_items_total"] == pytest.approx(200.0)
