"""Правило №6 (сессия 2026-09-08): GET /api/feo-categories/leaves и GET
/api/feo-categories/budget-residuals раньше считали «использовано по листу
ФЭО» (contracted_used/planned_used, через CONTRACTED_STATUSES/PLANNED_STATUSES)
одинаковым SQL-агрегатом, продублированным в обоих эндпоинтах
(routers/feo_plan_reads_budget.py). Вынесено в единственную реализацию —
app.services.feo_plan_totals.leaf_used_totals — оба эндпоинта теперь зовут её.

Тест проверяет то, что и должно быть инвариантом: для ОДНОГО и того же листа
оба эндпоинта отдают ОДНО И ТО ЖЕ число (а не две независимые копии формулы,
которые могут разъехаться), и это число совпадает с прямым расчётом по
статусам закупки.
"""
from decimal import Decimal

import pytest

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


@pytest.mark.asyncio
async def test_leaves_and_budget_residuals_agree_on_leaf_used(client, db_session, auth_headers, test_user):
    """Один лист ФЭО с одной закупкой в статусе 'contracted' (входит и в
    CONTRACTED_STATUSES, и в PLANNED_STATUSES) — оба эндпоинта обязаны
    отдать contracted_used=planned_used=500 для этого листа."""
    subsidy = Subsidy(name="Test subsidy leaf_used_totals", year=2026, budget=0, org_id=test_user.org_id)
    db_session.add(subsidy)
    await db_session.flush()

    leaf = FeoCategory(subsidy_id=subsidy.id, level=1, name="Лист", budget=Decimal("1000"))
    db_session.add(leaf)
    await db_session.flush()

    purchase = Purchase(status="contracted", item_type="goods", item_name="Test purchase")
    db_session.add(purchase)
    await db_session.flush()

    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Товар", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("500"), total_price=Decimal("500"), feo_category_id=leaf.id,
    )
    db_session.add(item)
    await db_session.commit()

    r_leaves = await client.get(
        "/api/feo-categories/leaves", params={"subsidy_id": subsidy.id}, headers=auth_headers
    )
    assert r_leaves.status_code == 200, r_leaves.text
    leaves_body = r_leaves.json()
    assert len(leaves_body) == 1
    assert leaves_body[0]["id"] == leaf.id
    assert leaves_body[0]["contracted_used"] == 500.0
    assert leaves_body[0]["planned_used"] == 500.0

    r_residuals = await client.get(
        "/api/feo-categories/budget-residuals",
        params={"subsidy_id": subsidy.id, "category_ids": str(leaf.id)},
        headers=auth_headers,
    )
    assert r_residuals.status_code == 200, r_residuals.text
    residuals_body = r_residuals.json()
    assert len(residuals_body["leaves"]) == 1
    leaf_out = residuals_body["leaves"][0]
    assert leaf_out["id"] == leaf.id

    # Инвариант Правило №6: оба эндпоинта берут число из ОДНОЙ функции —
    # значения обязаны совпадать друг с другом и с прямым расчётом.
    assert leaf_out["contracted_used"] == leaves_body[0]["contracted_used"] == 500.0
    assert leaf_out["planned_used"] == leaves_body[0]["planned_used"] == 500.0


@pytest.mark.asyncio
async def test_leaves_empty_subsidy_returns_empty_list(client, db_session, auth_headers, test_user):
    """Субсидия без FeoCategory — оба эндпоинта отдают пустой ответ (не 500)."""
    subsidy = Subsidy(name="Empty subsidy", year=2026, budget=0, org_id=test_user.org_id)
    db_session.add(subsidy)
    await db_session.commit()

    r_leaves = await client.get(
        "/api/feo-categories/leaves", params={"subsidy_id": subsidy.id}, headers=auth_headers
    )
    assert r_leaves.status_code == 200
    assert r_leaves.json() == []

    r_residuals = await client.get(
        "/api/feo-categories/budget-residuals",
        params={"subsidy_id": subsidy.id, "category_ids": ""},
        headers=auth_headers,
    )
    assert r_residuals.status_code == 200
    assert r_residuals.json() == {"directions": [], "leaves": []}
