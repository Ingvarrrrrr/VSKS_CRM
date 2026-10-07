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
async def test_subsidy_money_summary_balance_by_marks_and_statement(
    client, superadmin_headers, db_session, test_org,
):
    """«Остаток субсидии» (владелец, 06.10.2026) = бюджет ФЭО − оплачено, две
    версии: по отметке сотрудников (balance_by_marks) и по выписке
    (balance_by_statement). Бюджет 100k, закупка оплачена 30k по отметке
    (payment_amount_declared) и 20k подтверждено выпиской (payment_amount) —
    paid_marked = declared+confirmed = 50k, paid_confirmed = 20k,
    balance_by_marks = 100k-50k = 50k, balance_by_statement = 100k-20k = 80k."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=100_000)
    leaf = await _make_category(db_session, subsidy.id, name="Остаток", budget=Decimal("100000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Станок", 1, 100_000)
    purchase, _item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 100_000)
    purchase.payment_amount_declared = Decimal("30000")
    purchase.payment_amount = Decimal("20000")
    db_session.add(purchase)
    await db_session.commit()

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["balance_paid_marked"] == pytest.approx(50_000.0)
    assert row["balance_paid_confirmed"] == pytest.approx(20_000.0)
    assert row["balance_by_marks"] == pytest.approx(50_000.0)
    assert row["balance_by_statement"] == pytest.approx(80_000.0)

    # ИСПРАВЛЕНИЕ (2026-10-06, ФАДМ 2026_2, прод id=88): GET /api/dashboard/
    # charts раньше читало balance_by_marks/balance_by_statement НАПРЯМУЮ из
    # money_summary_map.get(sid) без фолбэка — «Остаток субсидии» мог
    # показать None («бюджет не введён»), пока «Бюджет (ФЭО)»
    # (calculated_budget/feo_budget_total, свой фолбэк budget_basis) в ТОЙ ЖЕ
    # строке честно показывал число. Теперь оба поля читают budget_basis —
    # проверяем, что они совпадают в живом ответе эндпойнта (ПРАВИЛО №6: один
    # источник budget_basis для «Бюджет (ФЭО)» и «Остаток субсидии»).
    resp = await client.get("/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers)
    assert resp.status_code == 200
    chart_row = {s["id"]: s for s in resp.json()["subsidy_stats"]}[subsidy.id]
    assert chart_row["feo_budget_total"] == pytest.approx(chart_row["calculated_budget"])
    assert chart_row["balance_by_marks"] == pytest.approx(row["balance_by_marks"])
    assert chart_row["balance_by_statement"] == pytest.approx(row["balance_by_statement"])
    assert chart_row["calculated_budget"] - chart_row["balance_paid_marked"] == pytest.approx(chart_row["balance_by_marks"])


@pytest.mark.asyncio
async def test_subsidy_money_summary_balance_none_without_budget(
    client, superadmin_headers, db_session, test_org,
):
    """Ни бюджета (budget <= 0), ни плана (planned <= 0) — feo_entered False,
    budget_basis None, balance_by_marks/balance_by_statement = None («ФЭО не
    введено», решение владельца 07.10.2026 — см. test_feo_not_entered.py для
    случая «план есть, ФЭО нет»: budget_basis остаётся None и там же, подмена
    планом отменена целиком)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    await _make_category(db_session, subsidy.id, name="Без бюджета и без плана")

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["budget"] == pytest.approx(0.0)
    assert row["feo_entered"] is False
    assert row["budget_basis"] is None
    assert row["budget_from_plan"] is False
    assert row["balance_by_marks"] is None
    assert row["balance_by_statement"] is None


@pytest.mark.asyncio
async def test_subsidy_money_summary_no_feo_entered_balance(
    client, superadmin_headers, db_session, test_org,
):
    """ОТМЕНЕНО решение владельца 06.10.2026 («бюджет = план, когда ФЭО не
    введён») — владелец 07.10.2026 (план .planning/quick/2026-10-07-dnr-feo-
    cards/PLAN.md шаг 1, решение №3, найдено на субсидии «ДНР»): субсидия без
    бюджета (ни ручного, ни «по ФЭО») с планом 100k — budget_basis/free_basis/
    redistributable*/balance_* теперь ВСЕ None («ФЭО не введено»), а не план.
    "budget" (effective_subsidy_budget) остаётся 0.0 (его читает
    корректировка, не трогаем)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    leaf = await _make_category(db_session, subsidy.id, name="По плану")
    fpi = await _make_planned_item(db_session, leaf.id, "Станок", 1, 100_000)
    purchase, _item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 100_000)
    purchase.payment_amount_declared = Decimal("30000")
    db_session.add(purchase)
    await db_session.commit()

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["budget"] == pytest.approx(0.0)  # не трогаем — читает корректировка
    assert row["planned"] == pytest.approx(100_000.0)
    assert row["feo_entered"] is False
    assert row["budget_basis"] is None
    assert row["budget_from_plan"] is False
    assert row["free_basis"] is None
    assert row["redistributable"] is None
    assert row["redistributable_unplanned"] is None
    assert row["redistributable_by_kind"] is None
    assert row["balance_paid_marked"] == pytest.approx(30_000.0)
    assert row["balance_by_marks"] is None
    assert row["balance_by_statement"] is None


@pytest.mark.asyncio
async def test_subsidy_money_summary_budget_from_feo_breakdown_items(
    client, superadmin_headers, db_session, test_org,
):
    """Воспроизводит живую субсидию «ФАДМ 2026_2» (прод id=88, найдено
    2026-10-06): ни у одной FeoCategory нет собственного budget, «бюджет по
    ФЭО» целиком лежит в ДВУХ служебных FeoPlannedItem с is_feo_breakdown=True
    на корневой категории (feo_amount=товары/услуги, amount=NULL — это не
    план, см. докстринг subsidy_budget.py) — ТОТ ЖЕ способ ввода бюджета, что
    даёт «Бюджет (ФЭО)» карточке 15 880 100 ₽ на проде. «Остаток субсидии»
    обязан взять budget_basis ИЗ ТОГО ЖЕ расчёта (calculate_budgets_bulk), а
    не остаться None («бюджет не введён») — баг, из-за которого
    balance_by_marks/balance_by_statement читались напрямую из
    money_summary_map без фолбэка (см. правку в dashboard_charts.py)."""
    from app.models.feo_planned_item import FeoPlannedItem
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    root = await _make_category(db_session, subsidy.id, name="Не определена")  # budget не задан
    db_session.add_all([
        FeoPlannedItem(
            feo_category_id=root.id, name="План ФЭО — товары", quantity=Decimal("1"), unit="шт",
            amount=None, feo_amount=Decimal("4380000"), is_feo_breakdown=True, is_active=True,
        ),
        FeoPlannedItem(
            feo_category_id=root.id, name="План ФЭО — услуги", quantity=Decimal("1"), unit="шт",
            amount=None, feo_amount=Decimal("11500100"), is_feo_breakdown=True, is_active=True,
        ),
    ])
    await db_session.commit()

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["budget"] == pytest.approx(15_880_100.0)
    assert row["budget_basis"] == pytest.approx(15_880_100.0)
    assert row["budget_from_plan"] is False
    assert row["balance_by_marks"] == pytest.approx(15_880_100.0)  # ничего не оплачено
    assert row["balance_by_statement"] == pytest.approx(15_880_100.0)

    resp = await client.get("/api/dashboard/charts", params={"scope": "managed"}, headers=superadmin_headers)
    assert resp.status_code == 200
    chart_row = {s["id"]: s for s in resp.json()["subsidy_stats"]}[subsidy.id]
    assert chart_row["calculated_budget"] == pytest.approx(15_880_100.0)
    # Регресс: раньше это было None («бюджет не введён»), хотя calculated_budget
    # (та же строка, «Бюджет (ФЭО)») уже показывал верное число.
    assert chart_row["balance_by_marks"] == pytest.approx(15_880_100.0)
    assert chart_row["balance_by_statement"] == pytest.approx(15_880_100.0)


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
async def test_subsidy_money_summary_no_budget_redistributable_is_none(
    client, superadmin_headers, db_session, test_org,
):
    """ОТМЕНЕНО решение владельца 04.10.2026 (субсидия id 75 «ХО»: без
    бюджета «Можно перераспределить» фолбэчило на planned_not_committed) —
    владелец 07.10.2026 (план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 1, решение №3, найдено на субсидии «ДНР»): «Можно
    перераспределить» теперь ПУСТО («ФЭО не введено»), не подставляет план,
    пока feo_entered=False (ни ручного Subsidy.budget, ни суммы «по ФЭО»
    дерева — calc=0, budget после effective_subsidy_budget == 0)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    # leaf без budget= — calculate_budgets_bulk не находит сумм «по ФЭО», calc=0.
    leaf = await _make_category(db_session, subsidy.id, name="Без бюджета")
    fpi = await _make_planned_item(db_session, leaf.id, "Станок", 2, 200_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["budget"] == pytest.approx(0.0)
    assert row["planned"] == pytest.approx(200_000.0)
    assert row["committed"] == pytest.approx(0.0)
    assert row["feo_entered"] is False
    assert row["redistributable"] is None
    assert row["redistributable_by_kind"] is None
    assert row["redistributable_unplanned"] is None
    # planned_not_committed (другая карточка — «В плане без договоров»)
    # decision №3 НЕ касается — считается как обычно.
    assert row["planned_not_committed"] == pytest.approx(200_000.0)

    # Частично законтрактовано — та же пустая карточка, planned_not_committed продолжает считаться.
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 150_000)
    summary2 = await subsidy_money_summary(db_session, [subsidy.id])
    row2 = summary2[subsidy.id]

    assert row2["committed"] == pytest.approx(150_000.0)
    assert row2["redistributable"] is None
    assert row2["redistributable_by_kind"] is None
    assert row2["redistributable_unplanned"] is None
    assert row2["planned_not_committed"] == pytest.approx(row2["planned"] - row2["committed"])
