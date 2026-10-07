"""test_feo_card_drill.py — «из чего сложено» число карточек «Бюджет (ФЭО)»/
«Запланировано»/«Свободно» (владелец, 07.10.2026, план .planning/quick/
2026-10-07-dnr-feo-cards/PLAN.md шаг 4).

Главный инвариант (ПРАВИЛО №6, одна функция на карточку): Σ rows["amount"]
ОБЯЗАНА совпасть с rows["total"] И с числом, которое дают dashboard_charts.py/
subsidy_money_summary.py/type_totals.py для той же субсидии (budget_basis,
planned (feo_plan_subsidy_totals), free_basis) — card_drill_rows читает ТЕ ЖЕ
узлы compute_feo_plan_tree, что и они, см. докстринг app.services.feo_card_drill.

Переиспользует фабрики test_feo_plan_tree_scenarios.py (ПРАВИЛО №6, не вторые
фабрики)."""
from decimal import Decimal

import pytest

from app.services.feo_card_drill import card_drill_rows
from app.services.feo_plan_tree import compute_feo_plan_tree
from app.services.item_type_split import ALL_KINDS, KIND_PAYROLL
from app.services.subsidy_budget import calculate_budgets_bulk
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


async def _set_feo(db_session, item, feo_amount, is_feo_breakdown=True):
    item.feo_amount = Decimal(str(feo_amount))
    item.is_feo_breakdown = is_feo_breakdown
    await db_session.commit()
    await db_session.refresh(item)


def _sum_rows(rows: list) -> float:
    return sum(r["amount"] for r in rows)


@pytest.mark.asyncio
async def test_planned_card_dnr_like_368_positions_sum_matches_total(db_session, test_org):
    """Срез «ДНР» (409 записей, 368 плановых позиций, ФЭО не введено ни у одной
    статьи) — ОДНА статья ФОТ (is_payroll) + N обычных статей товар/услуга/без
    типа, БЕЗ закупок (как в реальной ДНР на момент находки). Σ строк карточки
    «Запланировано» ОБЯЗАНА совпасть с итогом байт-в-байт, и количество строк
    == количеству активных плановых позиций (владелец явно требует отдельные
    позиции в окне, не агрегат по статье)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)

    payroll_cat = await _make_category(db_session, subsidy.id, name="ФОТ ДНР", is_payroll=True)
    goods_cat = await _make_category(db_session, subsidy.id, name="Канцтовары")
    services_cat = await _make_category(db_session, subsidy.id, name="Обслуживание ТС")
    unspecified_cat = await _make_category(db_session, subsidy.id, name="Прочее")

    n_total = 0
    total_amount = Decimal("0")
    for i in range(5):
        it = await _make_planned_item(db_session, payroll_cat.id, f"ФОТ позиция {i}", 1, 1000 + i)
        it.item_type = "товар"  # payroll ИГНОРИРУЕТ item_type — должно всё равно стать payroll
        n_total += 1
        total_amount += Decimal(str(1000 + i))
    for i in range(4):
        it = await _make_planned_item(db_session, goods_cat.id, f"Товар {i}", 1, 2000 + i)
        it.item_type = "товар"
        n_total += 1
        total_amount += Decimal(str(2000 + i))
    for i in range(3):
        it = await _make_planned_item(db_session, services_cat.id, f"Услуга {i}", 1, 3000 + i)
        it.item_type = "услуга"
        n_total += 1
        total_amount += Decimal(str(3000 + i))
    for i in range(2):
        it = await _make_planned_item(db_session, unspecified_cat.id, f"Без типа {i}", 1, 4000 + i)
        n_total += 1
        total_amount += Decimal(str(4000 + i))
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    assert result["reason"] is None
    assert len(result["rows"]) == n_total
    assert result["total"] == pytest.approx(float(total_amount))
    assert _sum_rows(result["rows"]) == pytest.approx(result["total"])

    # Payroll-строки — все 5, независимо от item_type="товар" на позициях.
    payroll_rows = [r for r in result["rows"] if r["kind"] == KIND_PAYROLL]
    assert len(payroll_rows) == 5
    assert sum(r["amount"] for r in payroll_rows) == pytest.approx(5010.0)

    # Инвариант с «официальным» итогом карточки (feo_plan_subsidy_totals, та
    # же величина, что и KPI «Запланировано» на дашборде).
    from app.services.feo_plan_totals import feo_plan_subsidy_totals
    official_total = (await feo_plan_subsidy_totals(db_session, [subsidy.id]))[subsidy.id]
    assert result["total"] == pytest.approx(official_total)


@pytest.mark.asyncio
async def test_planned_card_shows_category_with_all_zero_amount_items(db_session, test_org):
    """Боевая находка (10338 «ДНР (копия прода)», 07.10.2026): статьи 18081
    «Комплект оборудования для ССО»/18082 «Комплект оборудования для ШСО» —
    ВСЕ 68 плановых позиций нулевые (статус «Желания», amount=0). own-доля
    такой статьи тоже 0, но позиции обязаны попасть в окно «Запланировано»
    строками с amount=0, а не пропасть молча (feo_card_drill.py строки
    323-330, cat_items проверяется ОТДЕЛЬНО от own_amt). Σ строк (включая
    нулевые) всё равно обязана совпасть с total статьи с деньгами рядом."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    zero_cat = await _make_category(db_session, subsidy.id, name="Комплект оборудования для ССО")
    money_cat = await _make_category(db_session, subsidy.id, name="Канцтовары")

    zero_items = []
    for i in range(3):
        it = await _make_planned_item(db_session, zero_cat.id, f"Желание {i}", 1, 0)
        it.item_type = "товар"
        zero_items.append(it)
    money_item = await _make_planned_item(db_session, money_cat.id, "Бумага", 1, 5000)
    money_item.item_type = "товар"
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "planned", "all")
    assert result["reason"] is None
    # 3 нулевые позиции статьи "желаний" + 1 денежная — ни одна не потерялась.
    assert len(result["rows"]) == 4
    zero_cat_rows = [r for r in result["rows"] if r["feo_category_id"] == zero_cat.id]
    assert len(zero_cat_rows) == 3
    assert all(r["amount"] == pytest.approx(0.0) for r in zero_cat_rows)
    assert {r["planned_item_id"] for r in zero_cat_rows} == {it.id for it in zero_items}
    assert result["total"] == pytest.approx(5000.0)
    assert _sum_rows(result["rows"]) == pytest.approx(result["total"])


@pytest.mark.asyncio
async def test_planned_card_per_kind_filter_matches_subset(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    it1 = await _make_planned_item(db_session, cat.id, "Товар", 1, 1000)
    it1.item_type = "товар"
    it2 = await _make_planned_item(db_session, cat.id, "Услуга", 1, 500)
    it2.item_type = "услуга"
    await db_session.commit()

    goods_only = await card_drill_rows(db_session, subsidy.id, "planned", "goods")
    assert len(goods_only["rows"]) == 1
    assert goods_only["total"] == pytest.approx(1000.0)
    assert all(r["kind"] == "goods" for r in goods_only["rows"])


@pytest.mark.asyncio
async def test_budget_card_empty_reason_when_feo_not_entered(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья без ФЭО")
    await _make_planned_item(db_session, cat.id, "Позиция", 1, 100_000)

    budget_result = await card_drill_rows(db_session, subsidy.id, "budget", "all")
    assert budget_result["rows"] == []
    assert budget_result["total"] == 0.0
    assert budget_result["reason"]

    free_result = await card_drill_rows(db_session, subsidy.id, "free", "all")
    assert free_result["rows"] == []
    assert free_result["reason"]


@pytest.mark.asyncio
async def test_budget_card_rows_sum_to_total_with_payroll_category_budget(db_session, test_org):
    """Статья «ФОТ» с ЯВНЫМ budget (is_payroll) — вся сумма целиком payroll,
    без деления на товары/услуги (решение владельца 07.10.2026, план .planning/
    quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    payroll_cat = await _make_category(
        db_session, subsidy.id, name="ФОТ и иные выплаты персоналу", is_payroll=True, budget=Decimal("185000"),
    )
    goods_cat = await _make_category(db_session, subsidy.id, name="Канцтовары", budget=Decimal("50000"))
    await _make_planned_item(db_session, goods_cat.id, "Бумага", 1, 10_000)

    result = await card_drill_rows(db_session, subsidy.id, "budget", "all")
    assert result["reason"] is None
    assert _sum_rows(result["rows"]) == pytest.approx(result["total"])
    assert result["total"] == pytest.approx(235_000.0)

    payroll_rows = [r for r in result["rows"] if r["kind"] == KIND_PAYROLL]
    assert len(payroll_rows) == 1
    assert payroll_rows[0]["amount"] == pytest.approx(185_000.0)
    assert payroll_rows[0]["feo_category_id"] == payroll_cat.id

    # Инвариант с calculate_budgets_bulk (та же сумма, что budget_basis карточки).
    official = await calculate_budgets_bulk(db_session, [subsidy.id])
    assert result["total"] == pytest.approx(float(official[subsidy.id]))


@pytest.mark.asyncio
async def test_budget_card_chainik_termopot_regression(db_session, test_org):
    """Боевая причина 8 191,49 (ДНР) — позиции, привязанные ПРЯМО к статье с
    подстатьями (Чайник+Термопот на «Оргтехника»), должны попасть в строки
    карточки «Бюджет (ФЭО)» через собственный ФЭО статьи, а не потеряться
    из-за наличия подкатегории."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    parent = await _make_category(db_session, subsidy.id, name="Оргтехника")
    child = await _make_category(db_session, subsidy.id, name="Мебель", parent_id=parent.id)

    chainik = await _make_planned_item(db_session, parent.id, "Чайник электрический", 1, Decimal("1904.45"))
    termopot = await _make_planned_item(db_session, parent.id, "Термопот", 1, Decimal("6287.04"))
    stol = await _make_planned_item(db_session, child.id, "Стол", 1, 50_000)
    await _set_feo(db_session, chainik, Decimal("1904.45"))
    await _set_feo(db_session, termopot, Decimal("6287.04"))
    await _set_feo(db_session, stol, Decimal("50000"))

    result = await card_drill_rows(db_session, subsidy.id, "budget", "all")
    assert result["reason"] is None
    assert result["total"] == pytest.approx(1904.45 + 6287.04 + 50_000.0)
    assert _sum_rows(result["rows"]) == pytest.approx(result["total"])
    # Строка статьи "Оргтехника" (own) должна нести именно 1904.45+6287.04,
    # НЕ потеряв чайник/термопот.
    parent_rows_total = sum(r["amount"] for r in result["rows"] if r["feo_category_id"] == parent.id)
    assert parent_rows_total == pytest.approx(1904.45 + 6287.04)


@pytest.mark.asyncio
async def test_free_card_equals_feo_minus_plan_per_kind(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья", budget=Decimal("100000"))
    item = await _make_planned_item(db_session, cat.id, "Товар", 1, 40_000)
    item.item_type = "товар"
    await db_session.commit()

    free_result = await card_drill_rows(db_session, subsidy.id, "free", "all")
    assert free_result["reason"] is None
    assert free_result["total"] == pytest.approx(60_000.0)
    assert _sum_rows(free_result["rows"]) == pytest.approx(free_result["total"])


@pytest.mark.asyncio
async def test_free_card_by_kind_is_per_direction_with_items(db_session, test_org):
    """Задача 3 (владелец, 07.10.2026): card="free" с конкретной корзиной
    (goods/services) — строки по НАПРАВЛЕНИЮ (корню), не по статьям:
    budget_amount/planned_amount — raw кумулятивные поля корня, amount —
    их разность, == той же сумме, что даёт general-формула (kind="all"
    декомпозиция). При превышении (amount<0) — items: позиции поддерева
    этого kind, созданные позже — первыми (created_at DESC)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("50000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    import datetime as _dt

    old_item = await _make_planned_item(db_session, article.id, "Старая позиция", 1, 30_000)
    old_item.item_type = "товар"
    new_item = await _make_planned_item(db_session, article.id, "Новая позиция (перевела в превышение)", 1, 40_000)
    new_item.item_type = "товар"
    # created_at ОБЕИХ позиций в тесте может совпасть до секунды (та же
    # транзакция/func.now()) — задаём явно, чтобы сортировка DESC была
    # детерминированной (в бою created_at различаются реальным временем).
    old_item.created_at = _dt.datetime(2026, 1, 1, 10, 0, 0)
    new_item.created_at = _dt.datetime(2026, 1, 2, 10, 0, 0)
    await db_session.commit()
    await db_session.refresh(old_item)
    await db_session.refresh(new_item)
    assert new_item.created_at > old_item.created_at

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    assert result["reason"] is None
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["feo_category_id"] == direction.id
    assert row["budget_amount"] == pytest.approx(50_000.0)
    assert row["planned_amount"] == pytest.approx(70_000.0)
    assert row["amount"] == pytest.approx(-20_000.0)
    assert row["amount"] == pytest.approx(row["budget_amount"] - row["planned_amount"])
    assert result["total"] == pytest.approx(row["amount"])

    item_names = [it["name"] for it in row["items"]]
    assert item_names == ["Новая позиция (перевела в превышение)", "Старая позиция"]

    # Σ по направлениям (эта функция) == декомпозиции по статьям (kind="all"
    # own-ветка, не меняется этой задачей) — тот же общий инвариант.
    all_kind_result = await card_drill_rows(db_session, subsidy.id, "free", "all")
    goods_rows_sum = sum(r["amount"] for r in all_kind_result["rows"] if r["kind"] == "goods")
    assert goods_rows_sum == pytest.approx(result["total"])


@pytest.mark.asyncio
async def test_all_three_cards_rows_sum_to_total_random_mix(db_session, test_org):
    """Смешанный сценарий (товар/услуга/payroll/без типа, статья с подкатегорией
    и собственными позициями, явный budget на одной статье) — прогоняется по
    ВСЕМ картам и ВСЕМ корзинам (как это будет делать скрипт инвариантов)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    payroll_cat = await _make_category(db_session, subsidy.id, name="ФОТ", is_payroll=True, budget=Decimal("20000"))
    parent = await _make_category(db_session, subsidy.id, name="Техника", budget=Decimal("15000"))
    child = await _make_category(db_session, subsidy.id, name="Подкатегория", parent_id=parent.id)

    it_child = await _make_planned_item(db_session, child.id, "Товар в подкатегории", 1, 9000)
    it_child.item_type = "товар"
    it_parent = await _make_planned_item(db_session, parent.id, "Услуга на статье", 1, 6000)
    it_parent.item_type = "услуга"
    await db_session.commit()

    for card in ("budget", "planned", "free"):
        for kind in ("all",) + ALL_KINDS:
            result = await card_drill_rows(db_session, subsidy.id, card, kind)
            assert _sum_rows(result["rows"]) == pytest.approx(result["total"], abs=0.01), (card, kind)
