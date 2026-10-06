"""Регрессия (06.10.2026, субсидия «ФАДМ 2026_2»): узел «Не определена»
показывал ложный перерасход — рамочная ГОЛОВА (framework_with_amount,
parent_purchase_id IS NULL, единственная позиция «Лимит договора …» на сумму
лимита) засчитывалась в «законтрактовано»/«в закупках» СВОЕЙ категории наравне
с реальными заказами, а объяснение «из-за» («find_excess_culprit»,
feo_plan_excess.py) называло саму голову виновником.

Карточки субсидии уже исключают такую голову, когда у неё есть хотя бы один
РЕАЛЬНЫЙ дочерний заказ (parent_purchase_id → неё) — см.
app.services.purchase_amounts.aggregate_scope_expr (решение владельца
05.10.2026). Committed-считалка дерева ФЭО (app.services.committed_amounts.
committed_consumption_by_category) и построчный разбор виновника
(app.services.feo_plan_excess.find_excess_culprit) не применяли этот же
предикат — заводили фактически ВТОРУЮ точку «кто считается» (ПРАВИЛО №6).

06.10.2026, ВТОРОЙ заход (прод-проверка коммита cd858559): committed стал 0,
но узел ПО-ПРЕЖНЕМУ показывал consumed/fact/fact_services/
excess_fact_over_plan(_services) — голова (статус 'contracted'/'ordered',
входит в PLANNED_STATUSES/FACT_ELIGIBLE_STATUSES/ORDERED_STATUSES) считалась
в app.services.feo_plan_fact.plan_consumption_by_category/
fact_consumption_by_category/ordered_consumption_by_category — ТРЕТЬЯ и
ЧЕТВЁРТАЯ точки с тем же пробелом, committed_amounts.py их не затрагивает.
Эта регрессия проверяет, что ВСЕ эти точки теперь используют ОДИН и тот же
aggregate_scope_expr(), не вторую-третью-четвёртую копию условия.
"""
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan_tree import compute_feo_plan_tree
from app.services.feo_plan_excess import find_excess_culprit
from app.services.committed_amounts import committed_consumption_by_category
from app.services.purchase_amounts import aggregate_scope_expr
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


async def _make_framework_purchase(
    db_session, subsidy_id, feo_category_id, item_name, amount, quantity=1,
    parent_purchase_id=None, status="ordered",
):
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name=item_name,
        status=status,
        contract_price=Decimal(str(amount)),
        total_nmck=Decimal(str(amount)),
        nmck=Decimal(str(amount)),
        purchase_contract_type="framework_with_amount",
        parent_purchase_id=parent_purchase_id,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name=item_name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(amount)) / Decimal(str(quantity)),
        total_price=Decimal(str(amount)),
        feo_category_id=feo_category_id,
        feo_planned_item_id=None,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_framework_head_excluded_from_tree_committed_and_culprit(db_session, test_org):
    """Шапка 1 000 000 (категория A, без плана, planned_quantity=1, чтобы узел
    считался «законтрактован целиком» — та же ветка замещения, что воспроизвела
    реальный баг) + дочерний заказ 300 000 (категория B, план 300 000, уже
    точно набран). После фикса: у A нет ни «в закупках», ни перерасхода; у B
    committed == 300 000; шапка не входит в список виновников «из-за»."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=10_000_000)
    cat_a = await _make_category(
        db_session, subsidy.id, name="Не определена (тест)",
        budget=Decimal("100000"), planned_quantity=1,
    )
    cat_b = await _make_category(
        db_session, subsidy.id, name="Категория B (тест)",
        budget=Decimal("1000000"), planned_quantity=1,
    )
    await _make_planned_item(db_session, cat_b.id, "Плановая позиция B", 1, 300_000)

    head, head_item = await _make_framework_purchase(
        db_session, subsidy.id, cat_a.id, "Лимит договора ТЕСТ-1", 1_000_000,
        quantity=1, parent_purchase_id=None,
    )
    child, child_item = await _make_framework_purchase(
        db_session, subsidy.id, cat_b.id, "Заказ по рамочному ТЕСТ-1", 300_000,
        quantity=1, parent_purchase_id=head.id,
    )

    # ── Предикат совпадает с тем, что используют карточки субсидии ──
    from sqlalchemy import select
    scope_rows = (await db_session.execute(
        select(Purchase.id, aggregate_scope_expr()).where(Purchase.id.in_([head.id, child.id]))
    )).all()
    scope_by_id = dict(scope_rows)
    assert scope_by_id[head.id] is False  # голова с реальным ребёнком — исключена
    assert scope_by_id[child.id] is True  # заказ — всегда в Σ

    # ── committed_consumption_by_category напрямую (единая точка дерева) ──
    committed = await committed_consumption_by_category(db_session, [subsidy.id], include_over_plan=True)
    assert cat_a.id not in committed or committed[cat_a.id]["committed"] == 0.0
    assert committed[cat_b.id]["committed"] == 300_000.0

    # ── Дерево ФЭО: у A нет «в закупках»/перерасхода, у B 300 000 ──
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_a = tree[cat_a.id]
    node_b = tree[cat_b.id]
    assert node_a["committed"] == 0.0
    assert node_a["plan"] == 0.0
    assert node_a["excess_amount"] == 0.0
    # ── Второй заход (прод-проверка 06.10.2026): consumed/fact/excess_fact_* ──
    assert node_a["consumed"] == 0.0
    assert node_a["fact"] == 0.0
    assert node_a["fact_goods"] == 0.0
    assert node_a["fact_services"] == 0.0
    assert node_a["fact_unspecified"] == 0.0
    assert node_a["excess_fact_over_plan"] == 0.0
    assert node_a["excess_fact_over_plan_goods"] == 0.0
    assert node_a["excess_fact_over_plan_services"] == 0.0
    assert node_b["committed"] == 300_000.0
    assert node_b["plan"] == 300_000.0
    assert node_b["excess_amount"] == 0.0

    # ── Объяснение «из-за»: шапка не виновник, и вообще превышения нет ──
    culprit = await find_excess_culprit(db_session, cat_a.id, budget=100_000.0)
    assert culprit is None or culprit.get("purchase_id") != head.id


@pytest.mark.asyncio
async def test_framework_head_without_children_still_counts(db_session, test_org):
    """Контроль (не регрессия, но обязана остаться в силе, см. aggregate_scope_expr
    docstring): голова БЕЗ реального дочернего заказа — считается обычной
    закупкой, своей суммой по стадии, Σ её не теряет."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=10_000_000)
    cat_a = await _make_category(
        db_session, subsidy.id, name="Одинокая голова (тест)",
        budget=Decimal("5000000"), planned_quantity=1,
    )
    lone_head, _ = await _make_framework_purchase(
        db_session, subsidy.id, cat_a.id, "Лимит договора ТЕСТ-2", 1_000_000,
        quantity=1, parent_purchase_id=None,
    )

    committed = await committed_consumption_by_category(db_session, [subsidy.id], include_over_plan=True)
    assert committed[cat_a.id]["committed"] == 1_000_000.0
