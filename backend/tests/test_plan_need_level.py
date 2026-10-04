"""Статус «нужности» плановой позиции (FeoPlannedItem.need_level) — Задача 1-2
владельца (04.10.2026, план .planning/quick/2026-10-04-sheet-ideas):
  - 'likely' по умолчанию (все существующие позиции);
  - PATCH (PUT) меняет статус на 'nice_to_have';
  - разбивка узла дерева (compute_feo_plan_tree) и subsidy_money_summary по
    need_level: not_committed_likely + not_committed_nice == planned_not_committed.

Переиспользует фабрики test_feo_plan_tree_scenarios.py/test_money_committed.py
(ПРАВИЛО №6 — вторая копия не заводится)."""
from decimal import Decimal

import pytest

from app.models.feo_planned_item import FeoPlannedItem
from app.schemas.schemas import FeoPlannedItemCreate
from app.services import feo_item_write
from app.services.feo_plan import compute_feo_plan_tree
from app.services.plan_need_level import NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_new_planned_item_defaults_to_likely(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Нужность-умолчание")
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 1, 100_000)

    await db_session.refresh(fpi)
    assert fpi.need_level == NEED_LEVEL_LIKELY


@pytest.mark.asyncio
async def test_update_sets_nice_to_have(db_session, test_org, superadmin_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Нужность-PUT")
    fpi = await _make_planned_item(db_session, leaf.id, "Генератор", 1, 50_000)
    assert fpi.need_level == NEED_LEVEL_LIKELY

    data = FeoPlannedItemCreate(
        feo_category_id=leaf.id, name="Генератор", quantity=1, amount=50_000,
        need_level=NEED_LEVEL_NICE_TO_HAVE,
    )
    updated = await feo_item_write.update_planned_item(db_session, superadmin_user, fpi, data)
    await db_session.commit()
    await db_session.refresh(updated)

    assert updated.need_level == NEED_LEVEL_NICE_TO_HAVE


@pytest.mark.asyncio
async def test_update_without_need_level_in_payload_keeps_existing_value(
    db_session, test_org, superadmin_user,
):
    """model_fields_set-паттерн (как у is_feo_breakdown/item_type) — PUT, не
    приславший need_level явно, не должен молча сбросить его на 'likely'."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Нужность-keep")
    fpi = await _make_planned_item(db_session, leaf.id, "Рация", 1, 20_000)
    fpi.need_level = NEED_LEVEL_NICE_TO_HAVE
    await db_session.commit()
    await db_session.refresh(fpi)

    # FeoPlannedItemCreate(...) без need_level в конструкторе → поле НЕ входит
    # в model_fields_set (дефолт не считается «явно присланным» в pydantic v2).
    data = FeoPlannedItemCreate(feo_category_id=leaf.id, name="Рация", quantity=1, amount=20_000)
    assert "need_level" not in data.model_fields_set
    updated = await feo_item_write.update_planned_item(db_session, superadmin_user, fpi, data)
    await db_session.commit()
    await db_session.refresh(updated)

    assert updated.need_level == NEED_LEVEL_NICE_TO_HAVE


async def _make_planned_item_with_level(db_session, feo_category_id, name, quantity, amount, need_level):
    fpi = await _make_planned_item(db_session, feo_category_id, name, quantity, amount)
    fpi.need_level = need_level
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_node_splits_not_committed_by_need_level(db_session, test_org):
    """Узел с двумя позициями (одна likely, одна nice_to_have), ОБЕ без
    договоров — planned_not_committed целиком распадается на свои уровни,
    инвариант likely+nice == planned_not_committed."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Разбивка-нужность")
    await _make_planned_item_with_level(db_session, leaf.id, "Бензопила", 1, 100_000, NEED_LEVEL_LIKELY)
    await _make_planned_item_with_level(db_session, leaf.id, "Доп. оснастка", 1, 30_000, NEED_LEVEL_NICE_TO_HAVE)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    assert node["planned_not_committed"] == pytest.approx(130_000.0)
    assert node["not_committed_likely"] == pytest.approx(100_000.0)
    assert node["not_committed_nice"] == pytest.approx(30_000.0)
    assert node["not_committed_likely"] + node["not_committed_nice"] == pytest.approx(
        node["planned_not_committed"]
    )


@pytest.mark.asyncio
async def test_node_splits_not_committed_with_partial_commitment(db_session, test_org):
    """nice_to_have-позиция частично законтрактована — её незаконтрактованный
    остаток уменьшается, likely-позиция не тронута, инвариант держится."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Разбивка-частично")
    likely_item = await _make_planned_item_with_level(
        db_session, leaf.id, "Бензопила", 1, 100_000, NEED_LEVEL_LIKELY
    )
    nice_item = await _make_planned_item_with_level(
        db_session, leaf.id, "Доп. оснастка", 2, 40_000, NEED_LEVEL_NICE_TO_HAVE
    )
    # Законтрактована ОДНА из двух штук оснастки (количество не набрано целиком
    # → contribution остаётся полной плановой суммой 40 000, см. docstring
    # planned_item_contributions/committed_amounts.py).
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, nice_item.id, 1, 18_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    assert node["committed"] == pytest.approx(18_000.0)
    assert node["planned_not_committed"] == pytest.approx(100_000.0 + 40_000.0 - 18_000.0)
    assert node["not_committed_likely"] == pytest.approx(100_000.0)
    assert node["not_committed_nice"] == pytest.approx(40_000.0 - 18_000.0)
    assert node["not_committed_likely"] + node["not_committed_nice"] == pytest.approx(
        node["planned_not_committed"]
    )


@pytest.mark.asyncio
async def test_wish_without_planned_item_counts_as_likely(db_session, test_org):
    """Непривязанная (к плановой позиции) законтрактованная закупка — её
    «пол плана» (plan_floor_added) добавляется в plan, но не числится ни за
    одной позицией с need_level — по решению владельца весь остаток такого
    добавленного «пола» идёт в 'likely', не в 'nice_to_have'."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="Без-позиции")
    nice_item = await _make_planned_item_with_level(
        db_session, leaf.id, "Доп. оснастка", 1, 10_000, NEED_LEVEL_NICE_TO_HAVE
    )
    # Договор БЕЗ привязки к плановой позиции, сверх плана узла (10 000) —
    # поднимает «пол плана» (plan_floor_added), см. feo_plan_common.plan_floor_addition.
    from tests.test_money_committed import _make_unlinked_purchase
    await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 25_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    # Весь остаток узла по-прежнему распределяется без ущерба для инварианта;
    # nice_to_have не может превышать own-вклад nice_item (10 000, полностью
    # законтрактован нулём → contribution-committed = 10 000 - 0 = 10 000, но
    # денег этой позиции конкретно не касалась непривязанная закупка).
    assert node["not_committed_likely"] + node["not_committed_nice"] == pytest.approx(
        node["planned_not_committed"]
    )
    assert node["not_committed_nice"] <= 10_000.0 + 0.01


@pytest.mark.asyncio
async def test_subsidy_money_summary_exposes_need_level_split(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Сводка-нужность", budget=Decimal("1000000"))
    await _make_planned_item_with_level(db_session, leaf.id, "Бензопила", 1, 200_000, NEED_LEVEL_LIKELY)
    await _make_planned_item_with_level(db_session, leaf.id, "Оснастка", 1, 50_000, NEED_LEVEL_NICE_TO_HAVE)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["not_committed_likely"] == pytest.approx(200_000.0)
    assert row["not_committed_nice"] == pytest.approx(50_000.0)
    assert row["not_committed_likely"] + row["not_committed_nice"] == pytest.approx(
        row["planned_not_committed"]
    )


@pytest.mark.asyncio
async def test_plan_positions_not_committed_raw_matches_tree_when_all_linked(db_session, test_org):
    """PlanToOrderDialog «Что ещё заказать» (владелец, 04.10.2026, приёмка
    субсидии «ХО» id 75) — Σ not_committed_raw позиций листа (kind='planned_item')
    обязана совпасть с own-частью planned_not_committed узла (compute_feo_plan_tree),
    когда ВСЕ закупки категории привязаны к плановым позициям (нет «непривязанных
    фактических» — unlinked_actual_by_category=0 — иначе own-часть узла размывается
    непривязанными закупками, см. test_wish_without_planned_item_counts_as_likely).
    Обе точки (plan-positions.not_committed_raw и compute_feo_plan_tree.
    planned_not_committed) обязаны читать ОДНУ формулу — planned_item_contributions
    минус committed_by_planned_item (ПРАВИЛО №6)."""
    from app.routers.feo_plan_reads_tree import get_plan_positions

    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(db_session, subsidy.id, name="not_committed_raw-лист")
    likely_item = await _make_planned_item_with_level(
        db_session, leaf.id, "Бензопила", 1, 100_000, NEED_LEVEL_LIKELY
    )
    nice_item = await _make_planned_item_with_level(
        db_session, leaf.id, "Доп. оснастка", 2, 40_000, NEED_LEVEL_NICE_TO_HAVE
    )
    # Законтрактована ОДНА из двух штук оснастки — count не набран, contribution
    # остаётся полной плановой суммой (см. test_node_splits_not_committed_with_partial_commitment).
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, nice_item.id, 1, 18_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]

    rows = await get_plan_positions(
        subsidy_id=subsidy.id, exclude_purchase_id=None, exclude_wish_id=None, db=db_session, _=None,
    )
    leaf_rows = [r for r in rows if r["kind"] == "planned_item" and r["category_id"] == leaf.id]
    assert {r["id"] for r in leaf_rows} == {likely_item.id, nice_item.id}

    sum_not_committed_raw = sum(r["not_committed_raw"] for r in leaf_rows)
    assert sum_not_committed_raw == pytest.approx(node["planned_not_committed"])
    assert sum_not_committed_raw == pytest.approx(100_000.0 + 40_000.0 - 18_000.0)
