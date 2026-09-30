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
async def test_leaves_residual_counts_header_category_and_excludes_current_purchase(
    client, db_session, auth_headers, test_user
):
    """Баг владельца 2026-09-30 (закупка РЕЕ-2026-00913, категория «Ремонт
    техники»): GET /leaves.residual обязан вычитать ВСЕ закупки листа —
    и те, где feo_category_id стоит на позиции, и те, где только в шапке
    закупки (Purchase.feo_category_id, PurchaseItem.feo_category_id IS NULL),
    см. COALESCE в leaf_used_totals (app/services/feo_plan_totals.py). До
    фикса группировка шла по «голому» PurchaseItem.feo_category_id — закупка
    с категорией только в шапке вообще не попадала в used_map, и residual
    показывал budget целиком.

    Плюс exclude_purchase_id: редактируемая закупка не должна вычитать саму
    себя из своего же остатка.

    Доработка владельца 2026-09-30 (сверка на проде, категория 124): закупка в
    статусе 'wishes' (черновик заявки, ещё не поданной) НЕ должна попадать в
    planned_used/residual — leaf_used_totals обязан считать РОВНО те же
    статусы, что и `fact` в compute_feo_plan_tree (FACT_ELIGIBLE_STATUSES из
    app.services.feo_plan_fact, импортом, не копией).
    """
    subsidy = Subsidy(name="Test subsidy header category", year=2026, budget=0, org_id=test_user.org_id)
    db_session.add(subsidy)
    await db_session.flush()

    leaf = FeoCategory(subsidy_id=subsidy.id, level=1, name="Ремонт техники", budget=Decimal("2700000"))
    db_session.add(leaf)
    await db_session.flush()

    # Закупка №1: категория проставлена на позиции (как раньше уже работало).
    purchase_on_item = Purchase(status="contracted", item_type="goods", item_name="На позиции")
    db_session.add(purchase_on_item)
    await db_session.flush()
    item_on_item = PurchaseItem(
        purchase_id=purchase_on_item.id, item_name="Товар1", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("78100"), total_price=Decimal("78100"), feo_category_id=leaf.id,
    )
    db_session.add(item_on_item)

    # Закупка №2 (текущая редактируемая): категория ТОЛЬКО в шапке, позиция без
    # своей feo_category_id — раньше пропадала из used_map целиком.
    purchase_header = Purchase(
        status="contracted", item_type="goods", item_name="Только в шапке", feo_category_id=leaf.id,
    )
    db_session.add(purchase_header)
    await db_session.flush()
    item_header = PurchaseItem(
        purchase_id=purchase_header.id, item_name="Товар2", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("169000"), total_price=Decimal("169000"), feo_category_id=None,
    )
    db_session.add(item_header)

    # Закупка №3: статус 'wishes' (черновик заявки) — не входит в
    # FACT_ELIGIBLE_STATUSES, обязана быть проигнорирована planned_used/residual.
    purchase_wish = Purchase(status="wishes", item_type="goods", item_name="Черновик заявки")
    db_session.add(purchase_wish)
    await db_session.flush()
    item_wish = PurchaseItem(
        purchase_id=purchase_wish.id, item_name="Товар3", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("4000"), total_price=Decimal("4000"), feo_category_id=leaf.id,
    )
    db_session.add(item_wish)
    await db_session.commit()

    # Без exclude_purchase_id: contracted+header считаются, 'wishes' — нет.
    # budget - (78100+169000).
    r_all = await client.get(
        "/api/feo-categories/leaves", params={"subsidy_id": subsidy.id}, headers=auth_headers
    )
    assert r_all.status_code == 200, r_all.text
    leaf_all = r_all.json()[0]
    assert leaf_all["contracted_used"] == 78100.0 + 169000.0
    assert leaf_all["residual"] == 2700000.0 - (78100.0 + 169000.0)

    # exclude_purchase_id=purchase_header.id (редактируем закупку "в шапке") —
    # она не должна вычитать саму себя: остаётся только 78100 от соседней закупки.
    r_excl = await client.get(
        "/api/feo-categories/leaves",
        params={"subsidy_id": subsidy.id, "exclude_purchase_id": purchase_header.id},
        headers=auth_headers,
    )
    assert r_excl.status_code == 200, r_excl.text
    leaf_excl = r_excl.json()[0]
    assert leaf_excl["contracted_used"] == 78100.0
    assert leaf_excl["residual"] == 2700000.0 - 78100.0


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
