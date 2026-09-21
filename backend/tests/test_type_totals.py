"""Тесты app/services/type_totals.py (план ancient-prancing-music.md, раздел B/2).

Инвариант владельца (Правило №6): план_goods+plan_services+plan_unspecified
обязана РОВНО совпадать с тем, как общий план субсидии считает существующий
код (app.routers.subsidies._calculate_planned_amounts_bulk — Σ активных
FeoPlannedItem.amount). Аналогично feo_goods+feo_services+feo_unspecified
обязана совпадать с calculate_budgets_bulk (subsidy_budget.py) на дереве без
собственного subsidy.budget (calc из категорий).
"""
import uuid
from decimal import Decimal

import pytest

from app.routers.subsidies import _calculate_planned_amounts_bulk, calculate_budgets_bulk
from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary
from app.services.type_totals import effective_item_types, subsidy_type_totals


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TypeTotalsSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=None):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(subsidy_id=subsidy_id, parent_id=None, level=1, name=f"Cat-{uuid.uuid4().hex[:8]}", budget=budget)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(
    db_session, feo_category_id, item_type, amount, feo_amount=None, is_active=True, is_feo_breakdown=None,
):
    """is_feo_breakdown=None (по умолчанию) — авто True, если задан feo_amount:
    own_feo_by_kind (feo_plan_tree.py, см. её докстринг) и, теперь синхронно,
    subsidy_type_totals (type_totals.py, ПРАВИЛО №6) учитывают строку в
    ФЭО-по-типу только когда is_feo_breakdown=true — feo_amount без этого
    флага в реальных данных не встречается (см. докстринг FeoPlannedItem)."""
    from app.models.feo_planned_item import FeoPlannedItem
    if is_feo_breakdown is None:
        is_feo_breakdown = feo_amount is not None
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=f"Item-{uuid.uuid4().hex[:8]}",
        item_type=item_type,
        amount=Decimal(str(amount)),
        feo_amount=Decimal(str(feo_amount)) if feo_amount is not None else None,
        is_active=is_active,
        is_feo_breakdown=is_feo_breakdown,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _link_purchase_item(db_session, feo_planned_item_id, item_type, status="plan_schedule"):
    """Позиция закупки, связанная с плановой позицией через feo_planned_item_id —
    источник наследования типа (effective_item_types)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    p = Purchase(status=status, item_name="linked purchase", planned_total_price=Decimal("10"))
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="linked item", item_type=item_type,
        quantity=Decimal("1"), unit_price=Decimal("10"), total_price=Decimal("10"),
        feo_planned_item_id=feo_planned_item_id,
    )
    db_session.add(pi)
    await db_session.commit()
    return p, pi


@pytest.mark.asyncio
class TestSubsidyTypeTotals:
    async def test_plan_split_matches_existing_planned_amounts(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)  # no explicit budget
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)
        await _make_planned_item(db_session, cat.id, "услуга", 200)
        await _make_planned_item(db_session, cat.id, None, 50)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]

        assert t["plan_goods"] == pytest.approx(100.0)
        assert t["plan_services"] == pytest.approx(200.0)
        assert t["plan_unspecified"] == pytest.approx(50.0)

        existing_plan = (await _calculate_planned_amounts_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert t["plan_goods"] + t["plan_services"] + t["plan_unspecified"] == pytest.approx(existing_plan)
        assert existing_plan == pytest.approx(350.0)

    async def test_feo_split_matches_existing_budget(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        # только первая позиция несёт feo_amount (90, товар) — единственный
        # вклад в «по ФЭО» категории (см. compute_budget_map: категория без
        # собственного budget = Σ feo_amount собственных активных позиций).
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)
        await _make_planned_item(db_session, cat.id, "услуга", 200)
        await _make_planned_item(db_session, cat.id, None, 50)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]

        assert t["feo_goods"] == pytest.approx(90.0)
        assert t["feo_services"] == pytest.approx(0.0)
        assert t["feo_unspecified"] == pytest.approx(0.0)

        existing_budget = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert t["feo_goods"] + t["feo_services"] + t["feo_unspecified"] == pytest.approx(existing_budget)
        assert existing_budget == pytest.approx(90.0)

    async def test_category_explicit_budget_goes_to_unspecified(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id, budget=500)
        # Позиция с типом ЕСТЬ, но она НЕ участвует в «по ФЭО» — категория имеет
        # собственную явную budget, которая главнее (compute_budget_map) и не
        # помечена типом — идёт целиком в feo_unspecified.
        await _make_planned_item(db_session, cat.id, "товар", 100, feo_amount=90)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["feo_goods"] == pytest.approx(0.0)
        assert t["feo_unspecified"] == pytest.approx(500.0)
        existing_budget = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert existing_budget == pytest.approx(500.0)

    async def test_inherited_type_from_linked_purchase_item(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        fpi = await _make_planned_item(db_session, cat.id, None, 30)  # no own type
        await _link_purchase_item(db_session, fpi.id, "услуга")

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_services"] == pytest.approx(30.0)
        assert t["plan_goods"] == pytest.approx(0.0)
        assert t["plan_unspecified"] == pytest.approx(0.0)

    async def test_conflicting_inherited_types_stay_unspecified(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        fpi = await _make_planned_item(db_session, cat.id, None, 40)
        await _link_purchase_item(db_session, fpi.id, "товар")
        await _link_purchase_item(db_session, fpi.id, "услуга")

        types = await effective_item_types(db_session, [fpi.id])
        assert types.get(fpi.id) is None  # разные типы — не выдумываем

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_unspecified"] == pytest.approx(40.0)

    async def test_empty_subsidy_ids(self, db_session):
        assert await subsidy_type_totals(db_session, []) == {}

    async def test_inactive_planned_items_excluded(self, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)
        await _make_planned_item(db_session, cat.id, "товар", 100, is_active=False)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["plan_goods"] == pytest.approx(0.0)
        existing_plan = (await _calculate_planned_amounts_bulk(db_session, [subsidy.id]))[subsidy.id]
        assert existing_plan == pytest.approx(0.0)

    async def test_zero_budget_category_no_feo_lines_not_unspecified(self, db_session):
        """Правило №6 + решение владельца 15.09: FeoCategory.budget=0 значит
        «не задано» — категория с budget=0 и без собственных ФЭО-строк не
        должна закидывать ноль в feo_unspecified (тот же контракт, что и
        normalize_feo_category_budget в feo_plan_tree.py)."""
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id, budget=0)
        # план есть, но ни одна позиция не несёт feo_amount — «по ФЭО» пусто.
        await _make_planned_item(db_session, cat.id, "товар", 100)

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        assert t["feo_goods"] == pytest.approx(0.0)
        assert t["feo_services"] == pytest.approx(0.0)
        assert t["feo_unspecified"] == pytest.approx(0.0)

    async def test_tree_vs_bulk_equal_with_zero_budget_category(self, db_session):
        """Инвариант владельца (Правило №6): дерево (compute_feo_plan_tree +
        compute_subsidy_type_summary) и bulk (subsidy_type_totals) обязаны
        давать ОДНИ И ТЕ ЖЕ feo_goods/feo_services/feo_unspecified на общей
        фикстуре. cat1.budget=0 — до правки bulk трактовал 0 как «явный
        бюджет узла» и терял typed feo_amount строк узла (feo_goods=0 вместо
        90); дерево уже нормализовало 0->None. 2 категории, 3 позиции."""
        subsidy = await _make_subsidy(db_session)

        cat1 = await _make_category(db_session, subsidy.id, budget=0)
        await _make_planned_item(db_session, cat1.id, "товар", 100, feo_amount=90)
        await _make_planned_item(db_session, cat1.id, "услуга", 200)  # feo_amount=None, план-только

        cat2 = await _make_category(db_session, subsidy.id)  # budget=None
        await _make_planned_item(db_session, cat2.id, None, 50, feo_amount=50)

        bulk = (await subsidy_type_totals(db_session, [subsidy.id]))[subsidy.id]

        tree = await compute_feo_plan_tree(db_session, [subsidy.id])
        summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
        tree_totals = summary["totals"]

        assert bulk["feo_goods"] == pytest.approx(tree_totals["feo_goods"])
        assert bulk["feo_services"] == pytest.approx(tree_totals["feo_services"])
        assert bulk["feo_unspecified"] == pytest.approx(tree_totals["feo_unspecified"])

        assert bulk["feo_goods"] == pytest.approx(90.0), "budget=0 не должен глушить typed feo_amount узла"
        assert bulk["feo_services"] == pytest.approx(0.0)
        assert bulk["feo_unspecified"] == pytest.approx(50.0)

    async def test_feo_amount_without_breakdown_flag_counts_as_unspecified(self, db_session):
        """ИСПРАВЛЕНО 2026-09-21 (боевой замер GET /api/dashboard/charts:
        субсидия «ДНР» id 61 — split 63 477 577,92 vs feo_budget_total
        64 312 577,92, diff 835 000; «ФАДМ_2026» id 7 — diff 308 800):
        calculate_budgets_bulk (_active_feo_items_with_amount, subsidy_budget.py)
        учитывает ЛЮБУЮ активную строку с непустым feo_amount, НЕ проверяя
        is_feo_breakdown — а старый subsidy_type_totals фильтровал
        is_feo_breakdown=true и терял такие строки целиком (split < scalar).
        Строка без флага теперь тоже входит в сумму (split == scalar), но
        владелец её не размечал типом — целиком в feo_unspecified, а не
        kind_of(item_type) (см. docstring own_feo_by_kind, feo_plan_tree.py)."""
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id)  # budget не задан
        await _make_planned_item(
            db_session, cat.id, "товар", 100, feo_amount=100, is_feo_breakdown=False,
        )

        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        scalar = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]

        assert scalar == pytest.approx(100.0), "calculate_budgets_bulk не смотрит на is_feo_breakdown вообще"
        assert t["feo_goods"] == pytest.approx(0.0), "is_feo_breakdown=false -> не размечено типом, 'товар' не считается"
        assert t["feo_unspecified"] == pytest.approx(100.0)
        split_sum = t["feo_goods"] + t["feo_services"] + t["feo_unspecified"]
        assert split_sum == pytest.approx(scalar), "Правило №6: split обязан суммироваться в scalar"

    async def test_zero_budget_scalar_matches_split_when_items_present(self, db_session):
        """ИСПРАВЛЕНО 2026-09-21 (боевой замер: субсидия «Тестовая» id 59 —
        split 100 000 vs feo_budget_total 0): решение владельца Волна 1 п.8
        (0 в «финансирование по ФЭО» == «не задано») было применено в дереве
        (app.services.feo_plan_tree), но НЕ в самом scalar'е
        calculate_budgets_bulk (app.services.subsidy_budget.compute_budget_map)
        — категория с budget=0 трактовалась как явное финансирование «ноль»,
        собственные ФЭО-строки узла отбрасывались целиком. normalize_feo_category_budget
        перенесена в subsidy_budget.py (ЕДИНСТВЕННАЯ реализация) и применена
        в compute_budget_map._calc — теперь и scalar, и split видят одну и ту
        же сумму на категории с budget=0."""
        subsidy = await _make_subsidy(db_session)
        cat = await _make_category(db_session, subsidy.id, budget=0)
        await _make_planned_item(db_session, cat.id, "товар", 100_000, feo_amount=100_000)

        scalar = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
        totals = await subsidy_type_totals(db_session, [subsidy.id])
        t = totals[subsidy.id]
        split_sum = t["feo_goods"] + t["feo_services"] + t["feo_unspecified"]

        assert scalar == pytest.approx(100_000.0), (
            "budget=0 не должен глушить собственные ФЭО-строки узла в scalar'е — "
            "та же нормализация 0->None, что и в дереве"
        )
        assert split_sum == pytest.approx(scalar)
        assert t["feo_goods"] == pytest.approx(100_000.0)
