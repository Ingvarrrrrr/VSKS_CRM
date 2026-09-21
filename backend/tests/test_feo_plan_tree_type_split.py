"""Задача владельца (план ancient-prancing-music.md, раздел E, 2026-09-21):
«товары/услуги» по узлу дерева ФЭО — compute_feo_plan_tree.node несёт
plan_goods/plan_services/plan_unspecified, feo_goods/feo_services/
feo_unspecified, fact_goods/fact_services/fact_unspecified, плюс 4 независимых
контроля превышения (excess_plan_over_feo_goods/services,
excess_fact_over_plan_goods/services).

Проверяет:
  (1) plan_goods+plan_services+plan_unspecified == Σ активных FeoPlannedItem.amount
      узла (инвариант суммы, по образцу test_feo_plan_tree_scenarios.py).
  (2) feo_goods/feo_services — Σ feo_amount строк is_feo_breakdown=true по типу;
      feo_unspecified — явный FeoCategory.budget узла (нетипизированный).
  (3) excess_plan_over_feo_services срабатывает, когда план услуг выше ФЭО
      услуг, а excess_plan_over_feo_goods — НЕТ, когда feo_goods=0 (нет
      типизированного ФЭО по товарам).
  (4) fact_goods/fact_services — из позиций закупки (item_type), и
      excess_fact_over_plan_goods > 0, когда факт по товарам выше плана.
  (5) уровень субсидии (compute_subsidy_type_summary) — сумма корневых узлов.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TypeSplit-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(
    db_session, feo_category_id, name, amount, item_type=None,
    is_feo_breakdown=False, feo_amount=None, quantity=1,
):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        item_type=item_type,
        is_feo_breakdown=is_feo_breakdown,
        feo_amount=Decimal(str(feo_amount)) if feo_amount is not None else None,
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_purchase_item(db_session, subsidy_id, feo_category_id, item_name, item_type, amount, status="work_in_progress"):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name=item_name,
        status=status,
        contract_price=Decimal(str(amount)),
        planned_total_price=Decimal(str(amount)),
        total_nmck=Decimal(str(amount)),
        nmck=Decimal(str(amount)),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name=item_name,
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal(str(amount)),
        total_price=Decimal(str(amount)),
        feo_category_id=feo_category_id,
        item_type=item_type,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_plan_by_type_sums_to_items_total(db_session, test_org):
    """(1) plan_goods+services+unspecified == Σ активных плановых позиций узла."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — товары/услуги/без типа")
    await _make_planned_item(db_session, cat.id, "Ноутбук", 100_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Обслуживание", 40_000, item_type="услуга")
    await _make_planned_item(db_session, cat.id, "Монтаж", 10_000, item_type="работа")  # работа -> services
    await _make_planned_item(db_session, cat.id, "Без типа", 5_000, item_type=None)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan_goods"] == pytest.approx(100_000.0)
    assert node["plan_services"] == pytest.approx(50_000.0), "услуга (40к) + работа (10к) = 50к"
    assert node["plan_unspecified"] == pytest.approx(5_000.0)
    total = node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]
    assert total == pytest.approx(155_000.0)


@pytest.mark.asyncio
async def test_feo_by_type_from_breakdown_rows_and_explicit_budget_is_unspecified(db_session, test_org):
    """(2) feo_goods/feo_services — Σ feo_amount строк is_feo_breakdown=true по
    типу; отдельный узел с ЯВНЫМ FeoCategory.budget (без строк) — budget
    целиком уходит в feo_unspecified (нетипизированный бюджет категории)."""
    subsidy = await _make_subsidy(db_session, test_org.id)

    cat_typed = await _make_category(db_session, subsidy.id, name="Узел — типизированное ФЭО")
    await _make_planned_item(
        db_session, cat_typed.id, "Ноутбук (по ФЭО)", 90_000, item_type="товар",
        is_feo_breakdown=True, feo_amount=90_000,
    )
    await _make_planned_item(
        db_session, cat_typed.id, "Обслуживание (по ФЭО)", 30_000, item_type="услуга",
        is_feo_breakdown=True, feo_amount=30_000,
    )
    # Позиция БЕЗ is_feo_breakdown — не должна попасть в feo_goods/services.
    await _make_planned_item(db_session, cat_typed.id, "Просто план", 5_000, item_type="товар")

    cat_untyped = await _make_category(
        db_session, subsidy.id, name="Узел — нетипизированный бюджет", budget=Decimal("500000"),
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_typed = tree[cat_typed.id]
    assert node_typed["feo_goods"] == pytest.approx(90_000.0)
    assert node_typed["feo_services"] == pytest.approx(30_000.0)
    assert node_typed["feo_unspecified"] == pytest.approx(0.0)

    node_untyped = tree[cat_untyped.id]
    assert node_untyped["feo_goods"] == pytest.approx(0.0)
    assert node_untyped["feo_services"] == pytest.approx(0.0)
    assert node_untyped["feo_unspecified"] == pytest.approx(500_000.0)


@pytest.mark.asyncio
async def test_excess_plan_over_feo_only_fires_when_feo_typed_exists(db_session, test_org):
    """(3) План услуг (60к) выше ФЭО услуг (30к) -> excess_plan_over_feo_services
    > 0. ФЭО товаров типизировано не задано (0) -> excess_plan_over_feo_goods
    остаётся 0 даже при плане товаров > 0 (контроль не срабатывает без
    типизированного ФЭО, владелец: «на категории без типизированного ФЭО
    контроль не срабатывает»)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — план услуг выше ФЭО услуг")
    await _make_planned_item(
        db_session, cat.id, "Ноутбук", 20_000, item_type="товар",
    )  # товар без is_feo_breakdown -> feo_goods=0
    await _make_planned_item(
        db_session, cat.id, "Обслуживание по ФЭО", 30_000, item_type="услуга",
        is_feo_breakdown=True, feo_amount=30_000,
    )
    await _make_planned_item(
        db_session, cat.id, "Доп. услуга сверх ФЭО", 30_000, item_type="услуга",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan_services"] == pytest.approx(60_000.0)
    assert node["feo_services"] == pytest.approx(30_000.0)
    assert node["excess_plan_over_feo_services"] == pytest.approx(30_000.0)
    assert not node["excess_plan_over_feo_services_approved"]

    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["excess_plan_over_feo_goods"] == pytest.approx(0.0), (
        "без типизированного ФЭО по товарам контроль не должен подниматься"
    )


@pytest.mark.asyncio
async def test_excess_fact_over_plan_goods_from_purchase_items(db_session, test_org):
    """(4) Факт по товарам (80к, закупка work_in_progress) выше плана по
    товарам (50к) -> excess_fact_over_plan_goods > 0; факт по услугам в плане
    -> excess_fact_over_plan_services остаётся 0."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — факт товаров выше плана")
    await _make_planned_item(db_session, cat.id, "Ноутбуки (план)", 50_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Обслуживание (план)", 40_000, item_type="услуга")

    await _make_purchase_item(db_session, subsidy.id, cat.id, "Ноутбуки (факт)", "товар", 80_000)
    await _make_purchase_item(db_session, subsidy.id, cat.id, "Обслуживание (факт)", "услуга", 20_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["fact_goods"] == pytest.approx(80_000.0)
    assert node["fact_services"] == pytest.approx(20_000.0)
    assert node["excess_fact_over_plan_goods"] == pytest.approx(30_000.0)
    assert node["excess_fact_over_plan_services"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_subsidy_level_summary_sums_root_nodes(db_session, test_org):
    """(5) compute_subsidy_type_summary.totals — сумма КОРНЕВЫХ узлов дерева по
    типу (двух независимых категорий верхнего уровня)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория А")
    await _make_planned_item(db_session, cat_a.id, "Товар А", 100_000, item_type="товар")
    cat_b = await _make_category(db_session, subsidy.id, name="Категория Б")
    await _make_planned_item(db_session, cat_b.id, "Услуга Б", 40_000, item_type="услуга")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)

    assert summary["totals"]["plan_goods"] == pytest.approx(100_000.0)
    assert summary["totals"]["plan_services"] == pytest.approx(40_000.0)
    assert "plan_over_feo_goods" in summary["excess"]
    assert "fact_over_plan_services" in summary["excess"]
