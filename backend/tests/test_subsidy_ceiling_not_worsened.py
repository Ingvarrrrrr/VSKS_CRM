"""Тесты механизма assert_ceiling_not_worsened и ceiling_snapshot (владелец 09.11.2026,
ложный 409 PLAN_OVER_SUBSIDY_CEILING на закупке 4882).

Проверяет:
1) Юнит-тесты:
   - invalidate_tree_cache сбрасывает request-scope и глобальный LRU кэш;
   - assert_ceiling_not_worsened пропускает нейтральные и уменьшающие правки;
   - assert_ceiling_not_worsened блокирует рост плана выше потолка (409 PLAN_OVER_SUBSIDY_CEILING)
     с заполнением plan_before, growth, growth_by_category и правильным текстом ошибки;
   - assert_subsidy_ceiling содержит в конце сообщения «Свободно до потолка до этого действия: F ₽.»;
   - assert_no_unapproved_excess с check_ceiling=False не вызывает assert_subsidy_ceiling.
2) Интеграционные сценарии:
   a) план == потолку, закупка с позицией привязана к плановой строке дороже позиции;
      PUT поднимает цену позиции в пределах плановой -> 200 (раньше 409);
   b) PUT добавляет позицию over_plan / без плана (реальный рост плана) при запасе 0 -> 409 с growth_by_category;
   c) перенос позиции между двумя категориями без изменения суммы -> 200;
   d) PATCH позиции в пределах плановой -> 200.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi import HTTPException

from app.services.feo_plan_tree_cache import (
    invalidate_tree_cache,
    feo_plan_tree_request_scope,
    get_cached_tree,
    store_cached_tree,
    _global_cache,
)
from app.services.subsidy_ceiling import (
    assert_ceiling_not_worsened,
    ceiling_snapshot,
    assert_subsidy_ceiling,
)
from app.services.feo_plan_excess import assert_no_unapproved_excess


@pytest.mark.asyncio
async def test_invalidate_tree_cache_clears_request_and_global():
    """Проверка, что invalidate_tree_cache гарантирует очистку request-scope и global кэша."""
    with feo_plan_tree_request_scope():
        store_cached_tree([111], {1: {"plan": 100}})
        _global_cache[(tuple([111]), tuple([1]), 1)] = {1: {"plan": 100}}

        assert get_cached_tree([111]) is not None
        assert len(_global_cache) > 0

        # Сброс только для субсидии 111
        invalidate_tree_cache([111])

        assert get_cached_tree([111]) is None
        assert len(_global_cache) == 0


@pytest.mark.asyncio
async def test_ceiling_snapshot_leaf_nodes_only():
    """Проверка, что ceiling_snapshot берёт только листовые узлы в per_cat без задвоения родителей."""
    mock_db = AsyncMock()
    subsidy_id = 111

    # Дерево: узел 1 (корень, parent_id=None), узел 2 (лист, parent_id=1), узел 3 (лист, parent_id=1)
    fake_tree = {
        1: {"parent_id": None, "plan": 300.0, "over": 50.0},
        2: {"parent_id": 1, "plan": 100.0, "over": 20.0},
        3: {"parent_id": 1, "plan": 200.0, "over": 30.0},
    }

    with patch("app.services.subsidy_ceiling_diff.compute_feo_plan_tree", new_callable=AsyncMock) as mock_tree, \
         patch("app.services.subsidy_budget.feo_entered_ceiling_and_plan", new_callable=AsyncMock) as mock_entered:
        mock_tree.return_value = fake_tree
        mock_entered.return_value = (500.0, 350.0, {1})

        snap = await ceiling_snapshot(mock_db, subsidy_id)

        assert snap["subsidy_id"] == 111
        assert snap["ceiling"] == 500.0
        assert snap["total_plan"] == 350.0
        # В per_cat должны быть ТОЛЬКО листья 2 и 3, без корня 1
        assert 1 not in snap["per_cat"]
        assert snap["per_cat"][2] == 120.0
        assert snap["per_cat"][3] == 230.0


@pytest.mark.asyncio
async def test_assert_ceiling_not_worsened_allows_neutral_or_decreasing():
    """Нейтральные правки или уменьшение плана не должны блокироваться, даже если план >= потолка."""
    mock_db = AsyncMock()
    subsidy_id = 111

    # Before: plan = 35 000 000, ceiling = 35 000 000
    before = {
        "subsidy_id": subsidy_id,
        "ceiling": 35000000.0,
        "total_plan": 35000000.0,
        "per_cat": {10: 1000000.0, 20: 34000000.0},
    }

    # After: тот же план 35 000 000 (подорожание внутри плановой строки не изменило план)
    with patch("app.services.subsidy_ceiling_diff.ceiling_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = {
            "subsidy_id": subsidy_id,
            "ceiling": 35000000.0,
            "total_plan": 35000000.0,
            "per_cat": {10: 1000000.0, 20: 34000000.0},
        }
        # Не должно бросать исключение
        await assert_ceiling_not_worsened(mock_db, subsidy_id, before)

    # After: план уменьшился до 34 500 000
    with patch("app.services.subsidy_ceiling_diff.ceiling_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = {
            "subsidy_id": subsidy_id,
            "ceiling": 35000000.0,
            "total_plan": 34500000.0,
            "per_cat": {10: 500000.0, 20: 34000000.0},
        }
        await assert_ceiling_not_worsened(mock_db, subsidy_id, before)


@pytest.mark.asyncio
async def test_assert_ceiling_not_worsened_blocks_real_growth_over_ceiling():
    """Реальный рост плана выше потолка должен блокироваться 409 с деталями и категориями."""
    mock_db = AsyncMock()
    subsidy_id = 111

    before = {
        "subsidy_id": subsidy_id,
        "ceiling": 35000000.0,
        "total_plan": 35000000.0,
        "per_cat": {10: 1000000.0, 20: 34000000.0},
    }

    # After: выросла категория 10 на 200 000 руб
    with patch("app.services.subsidy_ceiling_diff.ceiling_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = {
            "subsidy_id": subsidy_id,
            "ceiling": 35000000.0,
            "total_plan": 35200000.0,
            "per_cat": {10: 1200000.0, 20: 34000000.0},
        }
        # Мокаем получение имени категории и субсидии
        mock_res = MagicMock()
        mock_res.all.return_value = [(10, "Спецодежда")]
        mock_db.execute.return_value = mock_res
        mock_db.get.return_value = MagicMock(name="ЗО_актуальная")

        with pytest.raises(HTTPException) as exc_info:
            await assert_ceiling_not_worsened(mock_db, subsidy_id, before)

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["code"] == "PLAN_OVER_SUBSIDY_CEILING"
        assert detail["subsidy_id"] == 111
        assert detail["total_plan"] == 35200000.0
        assert detail["ceiling"] == 35000000.0
        assert detail["over_amount"] == 200000.0
        assert detail["plan_before"] == 35000000.0
        assert detail["growth"] == 200000.0
        assert len(detail["growth_by_category"]) == 1
        assert detail["growth_by_category"][0]["category_id"] == 10
        assert detail["growth_by_category"][0]["name"] == "Спецодежда"
        assert detail["growth_by_category"][0]["delta"] == 200000.0
        assert "Рост плана дают категории: «Спецодежда» +200 000,00 ₽" in detail["message"]
        assert "уменьшите план минимум на 200 000,00 ₽" in detail["message"]


@pytest.mark.asyncio
async def test_assert_subsidy_ceiling_message_free_margin():
    """Существующий assert_subsidy_ceiling должен содержать свободный остаток в конце."""
    mock_db = AsyncMock()
    subsidy_id = 111

    with patch("app.services.subsidy_ceiling.compute_feo_plan_tree", new_callable=AsyncMock) as mock_tree, \
         patch("app.services.subsidy_budget.feo_entered_ceiling_and_plan", new_callable=AsyncMock) as mock_entered:
        mock_tree.return_value = {}
        # ceiling=1000, total_plan_now=800, entered_node_ids={1}
        mock_entered.return_value = (1000.0, 800.0, {1})
        mock_db.get.return_value = MagicMock(name="Тестовая")

        # adding_amount 300 -> total becomes 1100 > ceiling 1000
        with pytest.raises(HTTPException) as exc_info:
            await assert_subsidy_ceiling(mock_db, subsidy_id, adding_amount=Decimal("300"))

        assert exc_info.value.status_code == 409
        msg = exc_info.value.detail["message"]
        assert "Свободно до потолка до этого действия: 200,00 ₽." in msg


@pytest.mark.asyncio
async def test_assert_no_unapproved_excess_check_ceiling_flag():
    """При check_ceiling=False вызов assert_subsidy_ceiling не производится."""
    mock_db = AsyncMock()
    mock_cat = MagicMock(subsidy_id=111, parent_id=None)
    mock_db.get.return_value = mock_cat

    with patch("app.services.feo_plan_excess.compute_feo_plan_tree", new_callable=AsyncMock) as mock_tree, \
         patch("app.services.feo_plan_excess.assert_subsidy_ceiling", new_callable=AsyncMock) as mock_ceiling:
        mock_tree.return_value = {
            1: {"parent_id": None, "plan": 100, "over": 0, "excess_fact_over_plan": 0, "excess_plan_over_manual": 0}
        }
        await assert_no_unapproved_excess(mock_db, 1, adding_amount=Decimal("50"), check_ceiling=False)
        mock_ceiling.assert_not_called()

        await assert_no_unapproved_excess(mock_db, 1, adding_amount=Decimal("50"), check_ceiling=True)
        mock_ceiling.assert_called_once()


# ---------------------------------------------------------------------------
# Интеграционные сценарии (против db_session):
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_a_price_increase_within_planned_line_passes_put(db_session, test_user, test_org):
    """Сценарий a: план субсидии = потолку, позиция закупки привязана к плановой строке дороже позиции.
    PUT поднимает цену позиции в пределах плановой строки -> 200 (ранее ложный 409)."""
    import uuid
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchases import update_purchase
    from app.schemas.schemas import PurchaseCreate, PurchaseItemCreate

    subsidy = Subsidy(name=f"Sub-{uuid.uuid4().hex[:6]}", year=2026, budget=Decimal("1599800"), org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat = FeoCategory(subsidy_id=subsidy.id, name="Категория А", budget=Decimal("1599800"), level=1)
    db_session.add(cat)
    await db_session.flush()

    # Плановая строка на 1 599 800 (заполняет весь бюджет, потолок = плану)
    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Оборудование", quantity=Decimal("1"), unit="компл",
        amount=Decimal("1599800"), is_active=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    # Закупка с позицией на 1 000 000
    p = Purchase(
        status="planned", item_type="goods", item_name="Закупка оборудования",
        subsidy_id=subsidy.id, org_id=test_org.id, feo_category_id=cat.id,
    )
    db_session.add(p)
    await db_session.flush()

    pi = PurchaseItem(
        purchase_id=p.id, item_name="Оборудование", quantity=Decimal("1"), unit="компл",
        unit_price=Decimal("1000000"), total_price=Decimal("1000000"),
        feo_category_id=cat.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(pi)
    await db_session.flush()

    # PUT поднимает цену до 1 200 000 (в пределах плановой строки 1 599 800)
    payload = PurchaseCreate(
        name="Закупка оборудования",
        item_type="goods",
        status="planned",
        subsidy_id=subsidy.id,
        feo_category_id=cat.id,
        items=[
            PurchaseItemCreate(
                name="Оборудование",
                quantity=Decimal("1"),
                unit="компл",
                unit_price=Decimal("1200000"),
                total_price=Decimal("1200000"),
                feo_category_id=cat.id,
                feo_planned_item_id=fpi.id,
            )
        ],
    )

    res = await update_purchase(pid=p.id, data=payload, admin_override=False, current_user=test_user, db=db_session)
    assert res.id == p.id


@pytest.mark.asyncio
async def test_scenario_b_adding_unplanned_item_at_zero_margin_blocks_409(db_session, test_user, test_org):
    """Сценарий b: PUT добавляет позицию over_plan/без плана при запасе 0 -> 409 PLAN_OVER_SUBSIDY_CEILING."""
    import uuid
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchases import update_purchase
    from app.schemas.schemas import PurchaseCreate, PurchaseItemCreate

    subsidy = Subsidy(name=f"Sub-{uuid.uuid4().hex[:6]}", year=2026, budget=Decimal("1000000"), org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat = FeoCategory(subsidy_id=subsidy.id, name="Категория Б", budget=Decimal("1000000"), level=1)
    db_session.add(cat)
    await db_session.flush()

    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Базовый план", quantity=Decimal("1"), unit="шт",
        amount=Decimal("1000000"), is_active=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Закупка",
        subsidy_id=subsidy.id, org_id=test_org.id, feo_category_id=cat.id,
    )
    db_session.add(p)
    await db_session.flush()

    pi = PurchaseItem(
        purchase_id=p.id, item_name="Базовый план", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("1000000"), total_price=Decimal("1000000"),
        feo_category_id=cat.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(pi)
    await db_session.flush()

    # PUT добавляет позицию без плана (over_plan=True) на 50 000 при запасе 0
    payload = PurchaseCreate(
        name="Закупка",
        item_type="goods",
        status="planned",
        subsidy_id=subsidy.id,
        feo_category_id=cat.id,
        items=[
            PurchaseItemCreate(
                name="Базовый план",
                quantity=Decimal("1"),
                unit="шт",
                unit_price=Decimal("1000000"),
                total_price=Decimal("1000000"),
                feo_category_id=cat.id,
                feo_planned_item_id=fpi.id,
            ),
            PurchaseItemCreate(
                name="Сверх плана",
                quantity=Decimal("1"),
                unit="шт",
                unit_price=Decimal("50000"),
                total_price=Decimal("50000"),
                feo_category_id=cat.id,
                over_plan=True,
            ),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_purchase(pid=p.id, data=payload, admin_override=False, current_user=test_user, db=db_session)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PLAN_OVER_SUBSIDY_CEILING"
    assert "growth_by_category" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scenario_c_category_transfer_same_amount_passes_put(db_session, test_user, test_org):
    """Сценарий c: перенос позиции между двумя категориями без изменения суммы -> 200."""
    import uuid
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchases import update_purchase
    from app.schemas.schemas import PurchaseCreate, PurchaseItemCreate

    subsidy = Subsidy(name=f"Sub-{uuid.uuid4().hex[:6]}", year=2026, budget=Decimal("2000000"), org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat1 = FeoCategory(subsidy_id=subsidy.id, name="Категория 1", budget=Decimal("1000000"), level=1)
    cat2 = FeoCategory(subsidy_id=subsidy.id, name="Категория 2", budget=Decimal("1000000"), level=1)
    db_session.add_all([cat1, cat2])
    await db_session.flush()

    fpi1 = FeoPlannedItem(
        feo_category_id=cat1.id, name="План 1", quantity=Decimal("1"), unit="шт",
        amount=Decimal("1000000"), is_active=True,
    )
    fpi2 = FeoPlannedItem(
        feo_category_id=cat2.id, name="План 2", quantity=Decimal("1"), unit="шт",
        amount=Decimal("1000000"), is_active=True,
    )
    db_session.add_all([fpi1, fpi2])
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Закупка",
        subsidy_id=subsidy.id, org_id=test_org.id, feo_category_id=cat1.id,
    )
    db_session.add(p)
    await db_session.flush()

    pi = PurchaseItem(
        purchase_id=p.id, item_name="План 2", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("500000"), total_price=Decimal("500000"),
        feo_category_id=cat1.id, feo_planned_item_id=fpi1.id,
    )
    db_session.add(pi)
    await db_session.flush()

    # Переносим позицию из cat1 в cat2 с привязкой к fpi2, сумма та же (500 000)
    payload = PurchaseCreate(
        name="Закупка",
        item_type="goods",
        status="planned",
        subsidy_id=subsidy.id,
        feo_category_id=cat2.id,
        items=[
            PurchaseItemCreate(
                name="План 2",
                quantity=Decimal("1"),
                unit="шт",
                unit_price=Decimal("500000"),
                total_price=Decimal("500000"),
                feo_category_id=cat2.id,
                feo_planned_item_id=fpi2.id,
            ),
        ],
    )

    res = await update_purchase(pid=p.id, data=payload, admin_override=False, current_user=test_user, db=db_session)
    assert res.id == p.id


@pytest.mark.asyncio
async def test_scenario_d_patch_purchase_item_within_planned_passes(db_session, test_user, test_org):
    """Сценарий d: PATCH позиции в пределах плановой строки -> 200."""
    import uuid
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_items_edit import patch_purchase_item, _ItemPatchBody

    subsidy = Subsidy(name=f"Sub-{uuid.uuid4().hex[:6]}", year=2026, budget=Decimal("1599800"), org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat = FeoCategory(subsidy_id=subsidy.id, name="Категория А", budget=Decimal("1599800"), level=1)
    db_session.add(cat)
    await db_session.flush()

    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Оборудование", quantity=Decimal("1"), unit="компл",
        amount=Decimal("1599800"), is_active=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Закупка оборудования",
        subsidy_id=subsidy.id, org_id=test_org.id, feo_category_id=cat.id,
    )
    db_session.add(p)
    await db_session.flush()

    pi = PurchaseItem(
        purchase_id=p.id, item_name="Оборудование", quantity=Decimal("1"), unit="компл",
        unit_price=Decimal("1000000"), total_price=Decimal("1000000"),
        feo_category_id=cat.id, feo_planned_item_id=fpi.id,
    )
    db_session.add(pi)
    await db_session.flush()

    body = _ItemPatchBody(unit_price=Decimal("1200000"))
    res = await patch_purchase_item(pid=p.id, item_id=pi.id, body=body, db=db_session, current_user=test_user)
    assert res["ok"] is True
    assert res["unit_price"] == 1200000.0
