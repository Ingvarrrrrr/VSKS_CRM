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


@pytest.mark.asyncio
async def test_pending_excess_keeps_redistributable_rows_summing_to_total(
    db_session, test_org,
):
    """ИЗМЕНЕНО (Шаг 2 плана humble-stirring-emerson.md, 23.10.2026) —
    владелец: «не запланировано» ОБЯЗАНО быть тем же числом, что карточка
    «Свободно» (находка на синтетической 30871: 9 997,90 ≠ 19 997,90; на
    копии прода ФАДМ 2026_3 id 100: −326 492,00 ≠ 0,00). Старая
    pending_excess-поправка (вычитание несогласованной прибавки из
    «не запланировано», см. git-историю) ровно это и нарушала — тест ниже
    раньше ЗАКРЕПЛЯЛ её как верную (redistributable_unplanned=-20, ≠ free=0);
    теперь закрепляет НОВУЮ формулу: redistributable_unplanned ВСЕГДА ==
    free_basis, а несогласованная прибавка (full_display − display) просто
    остаётся внутри R = planned − committed и выходит в «скорее всего
    понадобится» (likely = R − nice − monthly − manual_gap, остаток).

    Фикстура: budget=100, ОДНА плановая позиция 120 (без согласования,
    excess_amount=20), committed=0 → planned(display)=100 (капнуто), free=0,
    redistributable=budget−committed=100, R=planned(100)−committed(0)=100,
    likely=R−0−0−0=100, redistributable_unplanned=free_basis=0,
    Σ строк = 0+0+100+0+0 = 100 = redistributable."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=100)
    leaf = await _make_category(db_session, subsidy.id, name="Над бюджетом, не согласовано", budget=Decimal("100"))
    await _make_planned_item(db_session, leaf.id, "Позиция сверх бюджета", 1, 120)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["planned"] == pytest.approx(100.0), "Запланировано капнуто budget до согласования"
    assert row["free"] == pytest.approx(0.0), "Свободно честно 0, не отрицательное"
    assert row["committed"] == pytest.approx(0.0)
    assert row["redistributable"] == pytest.approx(100.0)
    assert row["redistributable_unplanned"] == pytest.approx(row["free"]), (
        "«не запланировано» ОБЯЗАНО быть тем же числом, что «Свободно» — "
        "несогласованная прибавка больше не вычитается отдельно"
    )
    assert row["redistributable_unplanned"] == pytest.approx(0.0)
    assert row["not_committed_nice"] == pytest.approx(0.0)
    assert row["not_committed_likely"] == pytest.approx(100.0), (
        "несогласованная прибавка (20) остаётся внутри R=planned−committed "
        "и выходит в «скорее всего понадобится» (остаток)"
    )
    assert (
        row["redistributable_unplanned"] + row["not_committed_nice"] + row["not_committed_likely"]
        + row["monthly_future_not_started"] + row["manual_plan_gap"]
    ) == pytest.approx(row["redistributable"])


@pytest.mark.asyncio
async def test_redistributable_card_builds_up_on_realistic_mixed_data(
    db_session, test_org, make_user,
):
    """Шаг 2 плана humble-stirring-emerson.md (23.10.2026) — «собрать карточку
    «Можно перераспределить» так, чтобы сходилось ПО ПОСТРОЕНИЮ», проверено
    на ОДНОЙ субсидии, где сразу перемешаны все ингредиенты примера 30871:

      - «Товары» (budget=200000, разбит по типу): позиция, закупленная ЦЕЛИКОМ
        по количеству дешевле плана (экономия 30000, уходит в «Свободно»
        автоматически — order-substitution), и позиция, закупленная ЧАСТИЧНО
        (1 из 2 шт) дороже цены за единицу (перерасход по заказу, количество
        не закрыто — contribution остаётся планом, raw отрицательный);
      - «Без плановой позиции» (budget=30000, категория без единой плановой
        позиции, закупка целиком на статью) — «пол»: plan_floor_added=30000;
      - «Услуги» (budget=100000): одна плановая позиция 120000 — НЕСОГЛАСОВАННОЕ
        превышение (план статьи капается budget'ом до согласования);
      - «ФОТ» (budget=90000, is_payroll=True, «задано на категорию»=90000,
        одна позиция 60000 → manual_plan_gap=30000), частично законтрактована
        (40000 из 60000) — ФОТ не даёт «экономии» даже закрытым количеством.

    Инварианты владельца (не хардкодим ни одного промежуточного числа —
    только алгебраические соотношения, которые должны держаться НА ЛЮБЫХ
    данных, по построению):
      1) Σ подстрок карточки == её итогу;
      2) «не запланировано» == «Свободно» (budget_basis − planned) — байт-в-
         байт, никакой отдельной «несогласованной» поправки;
      3) Σ строк по видам == итогу, и «товары»/«услуги» НЕ отрицательны.
    """
    from app.models.feo_category import FeoCategory as _FC

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)

    cat_goods = await _make_category(db_session, subsidy.id, name="Товары", budget=Decimal("200000"))
    item_economy = await _make_planned_item(db_session, cat_goods.id, "Станок (закуплен целиком дешевле)", 1, 100_000)
    item_economy.item_type = "товар"
    item_overspend = await _make_planned_item(db_session, cat_goods.id, "Партия (1 из 2, дороже цены/ед.)", 2, 100_000)
    item_overspend.item_type = "товар"
    db_session.add_all([item_economy, item_overspend])
    await db_session.commit()
    # Экономия: 1 шт из 1 — количество ЗАКРЫТО целиком, цена дешевле плана.
    await _make_linked_purchase(db_session, subsidy.id, cat_goods.id, item_economy.id, 1, 70_000)
    # Перерасход по заказу: 1 шт из 2 — количество НЕ закрыто, но цена за
    # единицу (70000/шт) дороже плановой (50000/шт) — raw = 100000−70000 = 30000
    # (контрибуция остаётся планом целиком, не замещается).
    await _make_linked_purchase(db_session, subsidy.id, cat_goods.id, item_overspend.id, 1, 70_000)

    # «Пол»: категория БЕЗ единой плановой позиции, закупка целиком на статью
    # (feo_planned_item_id=None) — plan_floor_addition поднимает её «план»
    # до committed, чтобы категория не выглядела «законтрактовано сверх плана».
    cat_floor = await _make_category(db_session, subsidy.id, name="Без плановой позиции", budget=Decimal("30000"))
    await _make_linked_purchase(db_session, subsidy.id, cat_floor.id, None, 1, 30_000)

    # Несогласованное превышение: план позиции (120000) больше budget статьи
    # (100000) — «Запланировано» капается budget'ом до согласования.
    cat_services = await _make_category(db_session, subsidy.id, name="Услуги", budget=Decimal("100000"))
    item_excess = await _make_planned_item(db_session, cat_services.id, "Услуга сверх бюджета статьи", 1, 120_000)
    item_excess.item_type = "услуга"
    db_session.add(item_excess)
    await db_session.commit()

    # ФОТ: «задано на категорию» (manual_sum) 90000, позиции на 60000
    # (gap=30000), частично законтрактовано (40000 из 60000) — ФОТ НЕ даёт
    # «экономии» даже при закрытом количестве (шаг 1 плана, 22.10.2026).
    cat_payroll = await _make_category(db_session, subsidy.id, name="ФОТ", is_payroll=True, budget=Decimal("90000"))
    await db_session.execute(
        _FC.__table__.update().where(_FC.id == cat_payroll.id).values(
            plan_source="manual_sum", manual_plan_amount=Decimal("90000"),
        )
    )
    item_payroll = await _make_planned_item(db_session, cat_payroll.id, "ЗП — план на год", 1, 60_000)
    await db_session.commit()
    await _make_linked_purchase(db_session, subsidy.id, cat_payroll.id, item_payroll.id, 1, 40_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["feo_entered"] is True
    assert row["redistributable"] is not None

    # 1) Σ подстрок карточки == её итогу (до копейки, алгебраически).
    subrows_sum = (
        row["redistributable_unplanned"] + row["not_committed_nice"] + row["not_committed_likely"]
        + row["monthly_future_not_started"] + row["manual_plan_gap"]
    )
    assert subrows_sum == pytest.approx(row["redistributable"], abs=0.01)

    # 2) «Не запланировано» == «Свободно» — ОДНО число, не вычитаем отдельно
    #    несогласованную прибавку (пример услуги сверх бюджета статьи выше).
    assert row["redistributable_unplanned"] == pytest.approx(row["free_basis"], abs=0.01)
    assert row["free_basis"] == pytest.approx(row["budget_basis"] - row["planned"], abs=0.01)

    # 3) Σ строк по видам == итогу, товары/услуги не отрицательны (ФОТ-долг
    #    может уйти в «без типа», но не в «товары»/«услуги» — владелец,
    #    копия прода ФАДМ 2026_3 id 100).
    by_kind = row["redistributable_by_kind"]
    assert by_kind is not None
    assert sum(by_kind.values()) == pytest.approx(row["redistributable"], abs=0.01)
    assert by_kind["goods"] >= -0.01
    assert by_kind["services"] >= -0.01

    # «Пол» и manual_plan_gap видны в своих полях (не потеряны, не задвоены).
    assert row["plan_floor_added"] == pytest.approx(30_000.0, abs=0.01)
    assert row["manual_plan_gap"] == pytest.approx(30_000.0, abs=0.01)

    # Без права «Видеть ФОТ» — та же пара инвариантов держится на вычищенных
    # числах (владелец, D7 21.10.2026 — находка «подстроки не совпадали со
    # «Свободно»/«Запланировано» без ФОТ»).
    from app.services.payroll_visibility import scrub_payroll_from_dashboard_charts
    from tests.test_payroll_visibility import _manager_with_access

    manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)
    fake_row = {
        "id": subsidy.id, "redistributable": row["redistributable"],
        "redistributable_by_kind": dict(by_kind),
        "manual_plan_gap": row["manual_plan_gap"],
        "not_committed_nice": row["not_committed_nice"],
        "not_committed_likely": row["not_committed_likely"],
        "monthly_future_not_started": row["monthly_future_not_started"],
        "redistributable_unplanned": row["redistributable_unplanned"],
        "committed_by_kind": row["committed_by_kind"], "planned_not_committed_by_kind": row["planned_not_committed_by_kind"],
        "widget": {}, "feo_budget_total": row["budget"], "total_feo_planned": row["planned"],
        "calculated_budget": row["budget"], "planned_tree": row["planned"],
        "balance_paid_marked": None, "balance_paid_confirmed": None,
        "balance_by_marks": None, "balance_by_statement": None,
    }
    await scrub_payroll_from_dashboard_charts(manager, db_session, [fake_row], {})
    scrubbed_subrows_sum = (
        fake_row["redistributable_unplanned"] + fake_row["not_committed_nice"] + fake_row["not_committed_likely"]
        + fake_row["monthly_future_not_started"] + fake_row["manual_plan_gap"]
    )
    assert scrubbed_subrows_sum == pytest.approx(fake_row["redistributable"], abs=0.01)
    assert fake_row["redistributable_by_kind"]["goods"] >= -0.01
    assert fake_row["redistributable_by_kind"]["services"] >= -0.01
    assert sum(fake_row["redistributable_by_kind"].values()) == pytest.approx(fake_row["redistributable"], abs=0.01)


@pytest.mark.asyncio
async def test_redistributable_by_kind_sums_to_total_without_type_split(
    db_session, test_org,
):
    """Та же проверка (Σ видов == итогу), когда у субсидии НЕТ разбивки
    бюджета ФЭО по видам вообще (ни одной категории с budget/feo_amount) —
    падает в старую (не тронутую этой правкой) построчную ветку
    redistributable_raw.py, которую проверяют test_redistributable_drill.py/
    test_monthly_future_payments.py; здесь — та же Σ-проверка, что и выше,
    на другом коде."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=500_000)
    cat = await _make_category(db_session, subsidy.id, name="Без разбивки по видам")
    item_a = await _make_planned_item(db_session, cat.id, "Товар без ФЭО-разбивки", 1, 150_000)
    item_a.item_type = "товар"
    item_b = await _make_planned_item(db_session, cat.id, "Услуга без ФЭО-разбивки", 1, 100_000)
    item_b.item_type = "услуга"
    db_session.add_all([item_a, item_b])
    await db_session.commit()
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item_a.id, 1, 90_000)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["redistributable"] is not None
    by_kind = row["redistributable_by_kind"]
    assert by_kind is not None
    assert sum(by_kind.values()) == pytest.approx(row["redistributable"], abs=0.01)
    assert row["redistributable_unplanned"] == pytest.approx(row["free_basis"], abs=0.01)
