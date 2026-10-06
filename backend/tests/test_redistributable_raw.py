"""app.services.redistributable_raw — подстроки карточки «Можно
перераспределить» БЕЗ клэмпа дерева по направлениям (план sleepy-fluttering-
walrus.md, п.1, владелец 06.10.2026).

Контрольный пример владельца (живая находка на проде id=89, категория
«Организация мероприятий», см. отчёт задачи): позиция закупки физически
записана с feo_category_id НАПРАВЛЕНИЯ А (похоже, так завёл импорт), но её
feo_planned_item_id указывает на плановую позицию, которая на самом деле
лежит в НАПРАВЛЕНИИ Б. Committed дерева считается по Purchase/PurchaseItem.
feo_category_id (физическая метка — направление А), а contribution/
committed_by_planned_item — по самой плановой позиции (направление Б).
Направление А из-за этого видит "committed > свой план" (хотя его СОБСТВЕННЫЕ
nice-позиции ни копейкой не тронуты) — compute_feo_plan_tree поднимает «пол
плана» направления А до committed ЦЕЛИКОМ (plan_floor_added), и клэмп
not_committed_nice в [0, planned_not_committed=0] обнуляет nice направления А
полностью, пряча их честный план. Новая raw-формула считает remainder ПО
КАЖДОЙ ПОЗИЦИИ (contribution − committed_by_planned_item ЭТОЙ позиции,
app.services.committed_amounts.planned_item_contributions/
committed_by_planned_item — ПРАВИЛО №6, вторая формула не вводится) — nice-
позиции направления А остаются на своём полном плане независимо от чужого
перерасхода, привязанного к ЧУЖОЙ плановой позиции.

Переиспользует фабрики test_feo_plan_tree_scenarios.py/test_money_committed.py
(ПРАВИЛО №6 — вторая копия не заводится)."""
from decimal import Decimal

import pytest

from app.services.committed_amounts import subsidy_committed_totals
from app.services.feo_plan import compute_feo_plan_tree
from app.services.redistributable_raw import (
    not_committed_raw_by_subsidy,
    over_plan_categories_by_subsidy,
)
from app.services.stage_cumulative import (
    contracted_not_ordered_by_subsidy,
    contracted_not_ordered_need_level_split,
)
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_not_committed_raw_isolates_miscategorized_overspend(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=2_000_000)
    cat_a = await _make_category(db_session, subsidy.id, name="Направление А", budget=Decimal("500000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Направление Б", budget=Decimal("1000000"))

    item_nice_1 = await _make_planned_item(db_session, cat_a.id, "Прочие мат.затраты 1", 1, 400_000)
    item_nice_2 = await _make_planned_item(db_session, cat_a.id, "Прочие мат.затраты 2", 1, 100_000)
    item_nice_1.need_level = "nice_to_have"
    item_nice_2.need_level = "nice_to_have"
    item_b = await _make_planned_item(db_session, cat_b.id, "Костюм повседневный", 1, 1_000_000)
    await db_session.commit()

    # Закупка на 1 000 000 физически заведена с feo_category_id=А (ошибка
    # импорта на проде), но привязана (feo_planned_item_id) к плановой
    # позиции направления Б.
    await _make_linked_purchase(db_session, subsidy.id, cat_a.id, item_b.id, 1, 1_000_000)

    # ── Старая (клэмпнутая по узлу) формула: направление А видит committed=
    # 1 000 000 (по физической метке закупки), plan_floor_added поднимает его
    # "план" до committed ЦЕЛИКОМ → planned_not_committed=0 → nice клэмпится
    # в 0, хотя nice1/nice2 не задействованы НИ ОДНОЙ закупкой.
    committed_totals = await subsidy_committed_totals(db_session, [subsidy.id])
    assert committed_totals[subsidy.id]["committed"] == pytest.approx(1_000_000.0)
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree[cat_a.id]["not_committed_nice"] == pytest.approx(0.0)  # старый баг

    # ── Новая raw-формула: nice-позиции направления А остаются на полном
    # плане 500 000 (их СОБСТВЕННЫЙ committed_by_planned_item == 0) — ровно
    # то число, которое владелец сверяет по листу Excel.
    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    row = raw_map[subsidy.id]
    assert row["nice_raw"] == pytest.approx(500_000.0)


@pytest.mark.asyncio
async def test_not_committed_raw_matches_tree_total_without_miscategorization(db_session, test_org):
    """Без путаницы категорий (закупка и её плановая позиция — в ОДНОЙ
    категории, просто перезаконтрактована дороже плана и НЕ закрыта по
    количеству) raw-Σ обязана совпасть с planned_not_committed дерева —
    инвариант не меняется, когда plan_floor не вмешивается."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    cat = await _make_category(db_session, subsidy.id, name="Перерасход в своей категории", budget=Decimal("200000"))
    item = await _make_planned_item(db_session, cat.id, "Партия товара", 2, 200_000)  # 100 000/ед

    # Заказана только 1 из 2 единиц (количество НЕ закрыто — contribution
    # остаётся планом целиком, не committed), но по цене 900 000 за штуку.
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item.id, 1, 900_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["committed"] == pytest.approx(900_000.0)
    assert node["plan"] == pytest.approx(200_000.0)
    old_total = node["not_committed_nice"] + node["not_committed_likely"]
    assert old_total == pytest.approx(200_000.0 - 900_000.0)

    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    row = raw_map[subsidy.id]
    assert row["nice_raw"] + row["likely_raw"] == pytest.approx(old_total)

    # ── Красная строка «законтрактовано сверх плана» — ловит ИМЕННО этот
    # случай (без путаницы категорий, plan_floor не маскирует committed>plan).
    over = await over_plan_categories_by_subsidy(db_session, [subsidy.id])
    over_rows = over[subsidy.id]
    assert len(over_rows) == 1
    assert over_rows[0]["category_id"] == cat.id
    assert over_rows[0]["excess_amount"] == pytest.approx(700_000.0)


@pytest.mark.asyncio
async def test_contracted_not_ordered_empty_without_framework_children(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    result = await contracted_not_ordered_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert result[subsidy.id] == 0.0


@pytest.mark.asyncio
async def test_over_plan_categories_empty_when_within_plan(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    cat = await _make_category(db_session, subsidy.id, name="В рамках плана", budget=Decimal("500000"))
    item = await _make_planned_item(db_session, cat.id, "Товар", 1, 500_000)
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item.id, 1, 100_000)

    over = await over_plan_categories_by_subsidy(db_session, [subsidy.id])
    assert over[subsidy.id] == []


@pytest.mark.asyncio
async def test_contracted_not_ordered_is_carved_out_of_likely_not_added_on_top(db_session, test_org):
    """Находка координатора (06.10.2026, ДВА исправления подряд): сначала
    «ежемесячные по договорам» искали через is_monthly_payment-график — на
    проде id=89 разрыв «Ведётся работа»−«Заказано» целиком состоял из
    ДОЧЕРНИХ ЗАКАЗОВ РАМОЧНЫХ ДОГОВОРОВ в статусе 'contracted' (договор уже
    заключён, сам заказ как закупка ещё не оформлен) — is_monthly_payment=
    False у всех. committed_status_predicate НЕ считает 'contracted' для
    framework-закупок (FRAMEWORK_COMMITTED_STATUSES={ordered,delivered,paid}),
    поэтому плановая позиция такого заказа целиком остаётся «не
    законтрактовано» в not_committed_raw_by_subsidy. contracted_not_ordered
    обязан быть ВЫРЕЗКОЙ из not_committed_likely/not_committed_nice (по
    need_level заказа), а не добавкой поверх, и redistributable_by_kind НЕ
    трогается (товары/услуги уже включают эту сумму — по заданию
    координатора).

    Бюджет субсидии/категории не задаём (budget_from_plan=True) — тогда
    budget_basis == planned и redistributable_unplanned == 0 РОВНО."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(db_session, subsidy.id, name="Рамочный договор")
    item = await _make_planned_item(db_session, cat.id, "Услуга связи", 1, 250_000)
    item.item_type = "услуга"
    await db_session.commit()

    # Рамочная голова (сам договор) + дочерний заказ в статусе 'contracted'
    # (контракт заключён, заказ как отдельная закупка ещё НЕ создан) — ровно
    # находка координатора. Позиция заказа привязана к плановой позиции item
    # (need_level по умолчанию 'likely').
    head = Purchase(
        subsidy_id=subsidy.id, item_name="Рамочный договор",
        status="contracted", purchase_contract_type="framework_with_amount",
    )
    db_session.add(head)
    await db_session.flush()
    child = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Заказ по рамочному",
        status="contracted", purchase_contract_type="framework_with_amount",
        parent_purchase_id=head.id,
        contract_price=Decimal("250000"), total_nmck=Decimal("250000"), nmck=Decimal("250000"),
    )
    db_session.add(child)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=child.id, item_name="Услуга связи", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("250000"), total_price=Decimal("250000"), item_type="услуга",
        feo_category_id=cat.id, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    likely_raw = raw_map[subsidy.id]["likely_raw"]
    assert likely_raw == pytest.approx(250_000.0)  # 'contracted' не считается committed для framework

    contracted_total = await contracted_not_ordered_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert contracted_total[subsidy.id] == pytest.approx(250_000.0)
    split = await contracted_not_ordered_need_level_split(db_session, subsidy_ids=[subsidy.id])
    assert split[subsidy.id]["nice"] == pytest.approx(0.0)
    assert split[subsidy.id]["likely"] == pytest.approx(250_000.0)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["redistributable_unplanned"] == pytest.approx(0.0)
    assert row["contracted_not_ordered"] == pytest.approx(250_000.0)
    # Вырезка, не добавка: likely карточки = likely_raw МИНУС заказ целиком.
    assert row["not_committed_likely"] == pytest.approx(0.0)
    assert row["not_committed_nice"] == pytest.approx(0.0)

    # Σ by_kind == итогу (by_kind НЕ уменьшается вырезкой — по заданию).
    by_kind = row["redistributable_by_kind"]
    total_by_kind = by_kind["goods"] + by_kind["services"] + by_kind["unspecified"]
    assert total_by_kind == pytest.approx(row["redistributable"])
    assert by_kind["services"] == pytest.approx(250_000.0)
    assert by_kind["goods"] == pytest.approx(0.0)

    # Инвариант карточки: 4 строки складываются в итог ровно.
    assert row["redistributable_unplanned"] + row["not_committed_nice"] \
        + row["not_committed_likely"] + row["contracted_not_ordered"] \
        == pytest.approx(row["redistributable"])
