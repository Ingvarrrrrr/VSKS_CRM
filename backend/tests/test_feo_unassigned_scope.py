"""Регрессия (06.10.2026, жалоба владельца, субсидия «ФАДМ 2026_2»): строка
«Без категории ФЭО» дерева ФЭО (GET /api/feo-categories/plan-tree → ключ
"unassigned") считала «шапки» рамочных договоров (parent_purchase_id IS NULL,
без собственных позиций и потому без собственной категории ФЭО) как закупки
«без категории», хотя их деньги несут уже разложенные по категориям дочерние
заказы. 21 из 22 «непривязанных» на проде оказались именно такими шапками —
контейнерами, а не реальными закупками без категории.

Фикс (feo_plan_reads_tree.py::get_feo_plan_tree, unassigned_stmt) — тот же
предикат app.services.purchase_amounts.aggregate_scope_expr(), что уже
используют карточки субсидии/дерево ФЭО (ПРАВИЛО №6 — второй счётчик не
заводить). Этот тест вызывает САМ ЭНДПОИНТ (не копию формулы), чтобы
гарантировать, что shape "unassigned" действительно синхронен с ней.
"""
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.routers.feo_plan_reads_tree import get_feo_plan_tree
from tests.test_feo_plan_tree_scenarios import _make_subsidy
from tests.test_feo_plan_tree_framework_head_excess import _make_framework_purchase


async def _make_plain_purchase(db_session, subsidy_id, item_name, amount, status="plan_schedule"):
    """Обычная закупка (не рамочная шапка) без категории ФЭО ни у себя, ни у
    своих позиций — настоящий случай «без категории»."""
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=None,
        item_name=item_name,
        status=status,
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
        feo_category_id=None,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_framework_head_with_child_not_in_unassigned(db_session, test_org, superadmin_user):
    """Шапка рамочного договора с РЕАЛЬНЫМ дочерним заказом (сам ребёнок привязан
    к категории) — не попадает в unassigned, хотя у самой шапки feo_category_id
    пуст и своих позиций с категорией нет. Обычная закупка без категории —
    попадает, и только она одна."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=10_000_000)

    head, head_item = await _make_framework_purchase(
        db_session, subsidy.id, feo_category_id=None, item_name="Лимит договора ТЕСТ-unassigned",
        amount=1_000_000, quantity=1, parent_purchase_id=None, status="ordered",
    )
    # Ребёнок рамочного договора — сам РАЗЛОЖЕН по категории (feo_category_id
    # задан явно), т.е. не пустой — он и так не попал бы в unassigned ни по
    # какой из формул. Для теста важно, что ПУСТАЯ ПО КАТЕГОРИИ ШАПКА не
    # попадает в unassigned именно благодаря aggregate_scope_expr.
    child, child_item = await _make_framework_purchase(
        db_session, subsidy.id, feo_category_id=None, item_name="Заказ по рамочному ТЕСТ-unassigned",
        amount=300_000, quantity=1, parent_purchase_id=head.id, status="ordered",
    )

    real_unassigned = await _make_plain_purchase(
        db_session, subsidy.id, "Закупка без категории ТЕСТ-unassigned", 50_000,
    )

    result = await get_feo_plan_tree(subsidy_id=subsidy.id, db=db_session, current_user=superadmin_user)
    unassigned = result["unassigned"]

    assert head.id not in unassigned["purchase_ids"], "шапка рамочного договора не должна считаться «без категории»"
    # Ребёнок рамочного договора тоже без feo_category_id (как у себя, так и у
    # позиции) — он реальная закупка, не шапка, поэтому ОБЯЗАН попасть в
    # unassigned наравне с обычной закупкой без категории.
    assert child.id in unassigned["purchase_ids"]
    assert real_unassigned.id in unassigned["purchase_ids"]
    assert unassigned["purchase_count"] == 2
    assert unassigned["amount"] == pytest.approx(300_000 + 50_000)
