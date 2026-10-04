"""app.services.subsidy_money_summary — ОДНА функция денежной сводки субсидии
(PLAN.md шаг 5 отчёта, ПРАВИЛО №6: «Один показатель — один источник истины»,
вынесено из app.routers.dashboard_charts.dashboard_charts).

Проверяет на фикстуре с бюджетом/планом/договором:
  1) инвариант free + planned_not_committed == redistributable == budget − committed;
  2) значения byte-в-byte совпадают с subsidy_stats GET /api/dashboard/charts
     (dashboard_charts.py теперь читает эти же числа из этого же модуля).

Переиспользует фабрики test_feo_plan_tree_scenarios.py и
_make_linked_purchase из test_money_committed.py (ПРАВИЛО №6 — вторая копия
не заводится)."""
from decimal import Decimal

import pytest

from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_subsidy_money_summary_invariant_and_values(
    client, superadmin_headers, db_session, test_org,
):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Сводка", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)
    # Одна штука из двух законтрактована за 101 000 — вторая остаётся в плане
    # без договора (контрольный пример владельца, PLAN.md «Термины»).
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 101_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["committed"] == pytest.approx(101_000.0)
    assert row["budget"] == pytest.approx(1_000_000.0)
    assert row["planned"] == pytest.approx(200_000.0)  # план позиции целиком — вторая штука не набрана
    assert row["free"] == pytest.approx(row["budget"] - row["planned"])
    assert row["planned_not_committed"] == pytest.approx(row["planned"] - row["committed"])
    assert row["redistributable"] == pytest.approx(row["budget"] - row["committed"])
    # Инвариант владельца: Свободно + В плане без договоров == Можно перераспределить.
    assert row["free"] + row["planned_not_committed"] == pytest.approx(row["redistributable"])
    assert row["committed_by_kind"]["goods"] + row["committed_by_kind"]["services"] + row["committed_by_kind"]["unspecified"] \
        == pytest.approx(row["committed"])
    assert row["committed_missing_fact_items"] == 0
    # Карточка «Можно перераспределить» (04.10.2026): redistributable_unplanned
    # == free при заданном бюджете, и три строки карточки обязаны сходиться
    # в сумму с итогом — budget > 0.
    assert row["redistributable_unplanned"] == pytest.approx(row["free"])
    assert row["redistributable_unplanned"] + row["not_committed_nice"] + row["not_committed_likely"] \
        == pytest.approx(row["redistributable"])

    # Совпадение с GET /api/dashboard/charts subsidy_stats — та же точка чтения.
    resp = await client.get("/api/dashboard/charts", headers=superadmin_headers)
    assert resp.status_code == 200
    stats = {s["id"]: s for s in resp.json()["subsidy_stats"]}
    chart_row = stats[subsidy.id]
    assert chart_row["committed"] == pytest.approx(row["committed"])
    assert chart_row["remaining"] == pytest.approx(row["free"])
    assert chart_row["planned_not_committed"] == pytest.approx(row["planned_not_committed"])
    assert chart_row["redistributable"] == pytest.approx(row["redistributable"])
    assert chart_row["committed_missing_fact_items"] == row["committed_missing_fact_items"]


@pytest.mark.asyncio
async def test_subsidy_money_summary_no_purchases_redistributable_eq_budget(
    client, superadmin_headers, db_session, test_org,
):
    """Без единой закупки — committed=0, поэтому redistributable == budget
    (ничего ещё не связано договором), а free == budget − planned (план есть,
    хоть и без договора) — redistributable = free + planned_not_committed."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=500_000)
    leaf = await _make_category(db_session, subsidy.id, name="Пусто", budget=Decimal("500000"))
    await _make_planned_item(db_session, leaf.id, "Компьютер", 1, 100_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["committed"] == pytest.approx(0.0)
    assert row["planned"] == pytest.approx(100_000.0)
    assert row["free"] == pytest.approx(400_000.0)
    assert row["planned_not_committed"] == pytest.approx(100_000.0)
    assert row["redistributable"] == pytest.approx(500_000.0)
    assert row["free"] + row["planned_not_committed"] == pytest.approx(row["redistributable"])
    assert row["redistributable_unplanned"] == pytest.approx(row["free"])
    assert row["redistributable_unplanned"] + row["not_committed_nice"] + row["not_committed_likely"] \
        == pytest.approx(row["redistributable"])


@pytest.mark.asyncio
async def test_subsidy_money_summary_no_budget_redistributable_eq_planned(
    client, superadmin_headers, db_session, test_org,
):
    """Баг владельца (субсидия id 75 «ХО», 04.10.2026): официального бюджета
    нет вовсе (ни ручной Subsidy.budget, ни сумма «по ФЭО» дерева) — budget
    после effective_subsidy_budget == 0. «Можно перераспределить» не смеет
    быть budget − committed (= −committed, отрицательное число без смысла):
    фолбэк на planned_not_committed, та же логика, что у узлов дерева без
    бюджета (feo_plan_tree.py) и у фронта (useFeoTreeAmounts.ts)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    # leaf без budget= — calculate_budgets_bulk не находит сумм «по ФЭО», calc=0.
    leaf = await _make_category(db_session, subsidy.id, name="Без бюджета")
    fpi = await _make_planned_item(db_session, leaf.id, "Станок", 2, 200_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["budget"] == pytest.approx(0.0)
    assert row["planned"] == pytest.approx(200_000.0)
    assert row["committed"] == pytest.approx(0.0)
    # Без договоров: перераспределить можно весь план.
    assert row["redistributable"] == pytest.approx(row["planned"])
    assert row["redistributable_by_kind"] is not None
    assert row["redistributable_by_kind"] == row["planned_not_committed_by_kind"]
    # Без бюджета «не запланировано от бюджета» не определено — 0.0, не free
    # (budget дефект владельца: три строки карточки не сходились в сумму
    # именно на субсидии без бюджета).
    assert row["redistributable_unplanned"] == pytest.approx(0.0)
    assert row["redistributable_unplanned"] + row["not_committed_nice"] + row["not_committed_likely"] \
        == pytest.approx(row["redistributable"])

    # Частично законтрактовано — redistributable = planned − committed, не budget − committed.
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 150_000)
    summary2 = await subsidy_money_summary(db_session, [subsidy.id])
    row2 = summary2[subsidy.id]

    assert row2["committed"] == pytest.approx(150_000.0)
    assert row2["redistributable"] == pytest.approx(row2["planned"] - row2["committed"])
    assert row2["redistributable"] == pytest.approx(row2["planned_not_committed"])
    assert row2["redistributable_by_kind"] == row2["planned_not_committed_by_kind"]
    assert row2["redistributable_unplanned"] == pytest.approx(0.0)
    assert row2["redistributable_unplanned"] + row2["not_committed_nice"] + row2["not_committed_likely"] \
        == pytest.approx(row2["redistributable"])
