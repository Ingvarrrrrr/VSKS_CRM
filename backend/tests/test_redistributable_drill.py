"""test_redistributable_drill.py — построчная расшифровка карточки «Можно
перераспределить» (владелец, 06.10.2026, доп. задача: клик по «Товары»/
«Услуги» на карточке SubsidyMoneyCards.vue открывает список).

ПРАВИЛО №6 — Σ not_committed_raw_rows(...)[sid] по kind ОБЯЗАНА совпасть И с
not_committed_raw_by_subsidy(...)[sid]['by_kind'][kind] (агрегат того же
модуля), И с subsidy_money_summary(...)[sid]['redistributable_by_kind'][kind]
(карточка) — три пути чтения одного числа. Сценарий на синтетических данных:
рамочный договор с дочерним заказом в статусе 'contracted' (owner: «договор
заключён, заказ ещё не создан»), одна nice_to_have и одна likely позиция без
закупок, и одна позиция с отрицательным остатком (законтрактовано больше
плана — тоже должна попасть в список, см. докстринг модуля за условием
|raw| < 0.005)."""
from decimal import Decimal

import pytest

from app.services.redistributable_raw import not_committed_raw_by_subsidy, not_committed_raw_rows
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_redistributable_drill_rows_match_card_by_kind(db_session, test_org):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(db_session, subsidy.id, name="Товары и услуги")

    # 1) «Хотелось бы» — товар, без закупок, остаток = план целиком.
    item_nice = await _make_planned_item(db_session, cat.id, "Хотелось бы", 1, 100_000)
    item_nice.need_level = "nice_to_have"
    item_nice.item_type = "товар"

    # 2) «Скорее всего» — услуга, частично законтрактована. quantity=2 (план
    #    на 2 единицы), закуплена пока 1 — количество НЕ закрыто, contribution
    #    остаётся планом целиком (committed_amounts.planned_item_contributions:
    #    contribution переключается на committed-сумму ТОЛЬКО когда
    #    законтрактованное количество ≥ plan quantity).
    item_likely = await _make_planned_item(db_session, cat.id, "Скорее всего", 2, 50_000)
    item_likely.item_type = "услуга"

    # 3) Отрицательный остаток — товар, законтрактовано БОЛЬШЕ плана, но
    #    количество (1 из 2) тоже не закрыто — contribution остаётся планом
    #    (10 000), committed дороже плана (15 000) → raw отрицательный.
    item_over = await _make_planned_item(db_session, cat.id, "Перерасход", 2, 10_000)
    item_over.item_type = "товар"
    await db_session.commit()

    await _make_linked_purchase(db_session, subsidy.id, cat.id, item_likely.id, 1, 20_000)
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item_over.id, 1, 15_000)

    # 4) «Договор заключён, заказ ещё не создан» — рамочная голова + дочерний
    #    заказ в статусе 'contracted' (committed_status_predicate НЕ считает
    #    'contracted' для framework — вся сумма остаётся в not_committed).
    item_framework = await _make_planned_item(db_session, cat.id, "Связь по рамочному", 1, 40_000)
    item_framework.item_type = "услуга"
    await db_session.commit()

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
        contract_price=Decimal("40000"), total_nmck=Decimal("40000"), nmck=Decimal("40000"),
    )
    db_session.add(child)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=child.id, item_name="Связь по рамочному", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("40000"), total_price=Decimal("40000"), item_type="услуга",
        feo_category_id=cat.id, feo_planned_item_id=item_framework.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    rows_map = await not_committed_raw_rows(db_session, [subsidy.id])
    rows = rows_map[subsidy.id]
    by_id = {r["planned_item_id"]: r for r in rows}

    assert by_id[item_nice.id]["raw"] == pytest.approx(100_000.0)
    assert by_id[item_nice.id]["kind"] == "goods"
    assert by_id[item_nice.id]["need_level"] == "nice_to_have"
    assert by_id[item_nice.id]["contracted_not_ordered"] is False

    assert by_id[item_likely.id]["raw"] == pytest.approx(30_000.0)
    assert by_id[item_likely.id]["kind"] == "services"

    assert by_id[item_over.id]["raw"] == pytest.approx(-5_000.0)
    assert by_id[item_over.id]["kind"] == "goods"

    assert by_id[item_framework.id]["raw"] == pytest.approx(40_000.0)
    assert by_id[item_framework.id]["kind"] == "services"
    assert by_id[item_framework.id]["contracted_not_ordered"] is True
    assert "Товары и услуги" in by_id[item_framework.id]["category_path"]

    # Σ по виду == агрегату того же модуля (not_committed_raw_by_subsidy).
    goods_rows_total = sum(r["raw"] for r in rows if r["kind"] == "goods")
    services_rows_total = sum(r["raw"] for r in rows if r["kind"] == "services")

    agg_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    agg_by_kind = agg_map[subsidy.id]["by_kind"]
    assert goods_rows_total == pytest.approx(agg_by_kind["goods"])
    assert services_rows_total == pytest.approx(agg_by_kind["services"])
    assert goods_rows_total == pytest.approx(95_000.0)  # 100 000 - 5 000
    assert services_rows_total == pytest.approx(70_000.0)  # 30 000 + 40 000

    # Σ по виду == карточке (subsidy_money_summary.redistributable_by_kind) —
    # то же число, которое показывает SubsidyMoneyCards.vue.
    summary = await subsidy_money_summary(db_session, [subsidy.id])
    card_by_kind = summary[subsidy.id]["redistributable_by_kind"]
    assert goods_rows_total == pytest.approx(card_by_kind["goods"])
    assert services_rows_total == pytest.approx(card_by_kind["services"])


@pytest.mark.asyncio
async def test_redistributable_drill_hides_zero_remainder_rows(db_session, test_org):
    """Позиция, закрытая законтрактованным ровно по плану (raw ≈ 0), не
    должна засорять список (владелец: «строки с остатком 0 не выводить»)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(db_session, subsidy.id, name="Закрытая категория")
    item = await _make_planned_item(db_session, cat.id, "Полностью закрыто", 1, 50_000)
    item.item_type = "товар"
    await db_session.commit()

    await _make_linked_purchase(db_session, subsidy.id, cat.id, item.id, 1, 50_000)

    rows_map = await not_committed_raw_rows(db_session, [subsidy.id])
    assert rows_map[subsidy.id] == []
