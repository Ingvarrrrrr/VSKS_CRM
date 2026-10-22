# -*- coding: utf-8 -*-
"""Правило владельца (22.10.2026, заявка №209: генераторы из плана «Закупка
оборудования» согласующий перевёл в статью «Заработная плата работников» —
система молча приняла): товар/услуга/работа не могут лежать в статье ФЭО,
которая эффективно ФОТ (FeoCategory.is_payroll=True у самой статьи ИЛИ у
любого предка). Единственная проверка — app/services/payroll_category_guard.py
(ПРАВИЛО №6).

(а) юнит-тесты самой функции assert_no_goods_in_payroll;
(б) API-сценарии: смена категории позиции закупки на ФОТ, плановая позиция
«товар» в статье ФОТ, включение is_payroll на статье с товарами."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.payroll_category_guard import (
    assert_category_can_become_payroll,
    assert_no_goods_in_payroll,
)


async def _make_subsidy_with_payroll_category(db_session, *, payroll=True, name="ФОТ ДНР"):
    subsidy = Subsidy(
        name=f"TestPayrollGuard-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name=name, is_payroll=payroll)
    db_session.add(cat)
    await db_session.flush()
    return subsidy, cat


# ---------------------------------------------------------------------------
# (а) Юнит-тесты assert_no_goods_in_payroll
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_goods_in_payroll_category_rejected(db_session):
    _, cat = await _make_subsidy_with_payroll_category(db_session)
    with pytest.raises(HTTPException) as exc:
        await assert_no_goods_in_payroll(
            db_session, cat.id, [{"item_name": "Генератор", "item_type": "товар"}],
        )
    assert exc.value.status_code == 422
    assert "ФОТ" in exc.value.detail
    assert "Генератор" in exc.value.detail
    assert cat.name in exc.value.detail


@pytest.mark.asyncio
async def test_empty_item_type_in_payroll_category_allowed(db_session):
    """Зарплатные выплаты из импорта факта (закупка «ЗП», item_type NULL) —
    разрешены, правило бьёт только по товар/услуга/работа."""
    _, cat = await _make_subsidy_with_payroll_category(db_session)
    await assert_no_goods_in_payroll(
        db_session, cat.id, [{"item_name": "Выплата ЗП", "item_type": None}],
    )


@pytest.mark.asyncio
async def test_goods_in_regular_category_allowed(db_session):
    _, cat = await _make_subsidy_with_payroll_category(db_session, payroll=False, name="Товары")
    await assert_no_goods_in_payroll(
        db_session, cat.id, [{"item_name": "Генератор", "item_type": "товар"}],
    )


@pytest.mark.asyncio
async def test_goods_in_payroll_subcategory_rejected(db_session):
    """Наследование по дереву — потомок статьи ФОТ тоже ФОТ (payroll_category_ids)."""
    subsidy, parent_cat = await _make_subsidy_with_payroll_category(db_session)
    child = FeoCategory(subsidy_id=subsidy.id, parent_id=parent_cat.id, level=2, name="НДФЛ 13%")
    db_session.add(child)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await assert_no_goods_in_payroll(
            db_session, child.id, [{"item_name": "Услуга консультирования", "item_type": "услуга"}],
        )
    assert exc.value.status_code == 422
    assert child.name in exc.value.detail


# ---------------------------------------------------------------------------
# (б) API-сценарии
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_purchase_item_category_to_payroll_rejected(
    client, db_session, superadmin_user, superadmin_headers,
):
    """Смена категории позиции закупки на ФОТ → 422, в БД feo_category_id
    позиции не меняется (проверка ДО записи/commit)."""
    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    goods_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Товары")
    db_session.add(goods_cat)
    await db_session.flush()

    purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=goods_cat.id,
        status="plan_schedule", purchase_method="advance",
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Генератор", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
        feo_category_id=goods_cat.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    item_id, purchase_id, goods_cat_id = item.id, purchase.id, goods_cat.id

    resp = await client.patch(
        f"/api/purchases/{purchase_id}/items/{item_id}",
        json={"feo_category_id": payroll_cat.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")

    # Эндпоинт мутирует it.feo_category_id в памяти ДО guard-проверки (как и
    # до этой правки — обычная последовательность патч-роутера), но без
    # db.commit() — реальный процесс закрывает/откатывает сессию запроса на
    # исключении (app/database.py::get_db, async with). Тестовая сессия общая
    # с клиентом (conftest.client) — откатываем явно до SAVEPOINT, иначе
    # db.refresh() сделает autoflush и покажет НЕЗАКОММИЧЕННУЮ мутацию. id
    # захвачены ДО rollback — после него атрибуты ORM-объектов expired.
    await db_session.rollback()
    from sqlalchemy import select as _select
    _db_cat_id = (await db_session.execute(
        _select(PurchaseItem.feo_category_id).where(PurchaseItem.id == item_id)
    )).scalar_one()
    assert _db_cat_id == goods_cat_id


@pytest.mark.asyncio
async def test_create_planned_item_goods_in_payroll_rejected(
    client, db_session, superadmin_headers,
):
    """Плановая позиция «товар» в статье ФОТ → 422 при создании."""
    _, payroll_cat = await _make_subsidy_with_payroll_category(db_session)

    resp = await client.post(
        "/api/feo-planned-items/",
        json={
            "feo_category_id": payroll_cat.id,
            "name": "Генератор",
            "item_type": "товар",
            "quantity": "1",
            "unit_price": "1000",
            "amount": "1000",
        },
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")


@pytest.mark.asyncio
async def test_enable_payroll_on_category_with_goods_rejected(
    client, db_session, superadmin_headers,
):
    """Включение is_payroll на статье, где уже лежат товары, — 422."""
    subsidy = Subsidy(
        name=f"TestPayrollToggle-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование", is_payroll=False)
    db_session.add(cat)
    await db_session.flush()
    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Генератор", item_type="товар",
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()

    resp = await client.put(
        f"/api/feo-categories/{cat.id}",
        json={"subsidy_id": subsidy.id, "level": 1, "name": "Оборудование", "is_payroll": True},
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")


@pytest.mark.asyncio
async def test_assert_category_can_become_payroll_unit(db_session):
    """Юнит-вызов напрямую — тот же инвариант без HTTP-слоя."""
    subsidy = Subsidy(
        name=f"TestPayrollToggleUnit-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование", is_payroll=False)
    db_session.add(cat)
    await db_session.flush()
    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Генератор", item_type="товар",
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await assert_category_can_become_payroll(db_session, cat.id)
    assert exc.value.status_code == 422
    assert "Генератор" in exc.value.detail


# ---------------------------------------------------------------------------
# (в) Вторая очередь — заявки (wishes.py, wish_transitions.py, plan_to_wish.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_wish_goods_in_payroll_rejected(
    client, db_session, test_org, superadmin_headers,
):
    """create_wish: товар в статье ФОТ → 422, заявка не создаётся."""
    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/wishes/",
        json={
            "title": "Заявка на генератор",
            "subsidy_id": subsidy.id,
            "feo_category_id": payroll_cat.id,
            "items": [{
                "item_name": "Генератор",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 1000,
                "total_price": 1000,
            }],
        },
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")


@pytest.mark.asyncio
async def test_patch_wish_execution_header_to_payroll_rejected(
    client, db_session, test_org, test_user, make_user,
):
    """PATCH /wishes/{id}/execution: смена шапки на ФОТ при позиции «товар» —
    422, статья и позиции заявки в БД не меняются."""
    from app.auth.jwt import create_access_token
    from app.models.permission import UserOrgPermissionOverride
    from app.models.user_org_access import UserOrgAccess

    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    goods_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Товары")
    db_session.add(goods_cat)
    await db_session.flush()

    wish = Wish(
        org_id=test_org.id, title="Заявка на генератор", status="submitted",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=goods_cat.id,
        feo_per_item=False, assigned_to=test_user.id,
    )
    db_session.add(wish)
    await db_session.flush()
    item = WishItem(
        wish_id=wish.id, item_name="Генератор", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
        feo_category_id=goods_cat.id,
    )
    db_session.add(item)
    await db_session.commit()
    wish_id, item_id, goods_cat_id = wish.id, item.id, goods_cat.id

    # Согласующий: право wish.edit_feo через override (тот же приём, что и
    # test_wish_header_category_sync.py::_grant_wish_edit_feo).
    uoa = UserOrgAccess(user_id=test_user.id, org_id=test_org.id, role=test_user.role)
    db_session.add(uoa)
    await db_session.flush()
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="wish.edit_feo", granted=True,
    ))
    await db_session.commit()
    token = create_access_token({"sub": test_user.username, "org_id": test_user.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.patch(
        f"/api/wishes/{wish_id}/execution",
        json={"feo_category_id": payroll_cat.id},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")

    await db_session.rollback()
    from sqlalchemy import select as _select
    _wish_cat_id, _item_cat_id = (
        (await db_session.execute(_select(Wish.feo_category_id).where(Wish.id == wish_id))).scalar_one(),
        (await db_session.execute(_select(WishItem.feo_category_id).where(WishItem.id == item_id))).scalar_one(),
    )
    assert _wish_cat_id == goods_cat_id
    assert _item_cat_id == goods_cat_id


@pytest.mark.asyncio
async def test_plan_to_wish_untyped_item_in_payroll_allowed(db_session):
    """Заявка из плана по плановой позиции БЕЗ типа (как «ЗП») в статье ФОТ —
    создаётся: item_type приходит из плана как есть (None), дефолт 'товар'
    (create_wish/plan_to_wish) не применяется в статье ФОТ (иначе
    payroll_category_guard отклонил бы законную заявку)."""
    from app.services.plan_to_wish import PlanToWishItemInput, build_items_from_plan

    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session, name="ФОТ")
    fpi = FeoPlannedItem(
        feo_category_id=payroll_cat.id, name="ЗП", item_type=None,
        quantity=Decimal("1"), amount=Decimal("50000.00"), unit_price=Decimal("50000.00"),
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()

    item_dicts, warnings, categories_used, _subsidy = await build_items_from_plan(
        db_session, subsidy.id,
        [PlanToWishItemInput(feo_planned_item_id=fpi.id, quantity=Decimal("1"), item_name="ЗП")],
    )
    assert len(item_dicts) == 1
    assert item_dicts[0]["item_type"] is None
    assert payroll_cat.id in categories_used


# ---------------------------------------------------------------------------
# (г) Ревью-правки координатора 22.10.2026, пакет 2
# ---------------------------------------------------------------------------

def test_is_goods_or_services_public_helper():
    """ЕДИНСТВЕННАЯ проверка «товар/услуга/работа» — построена на kind_of,
    без второго захардкоженного кортежа (найден дублем в feo_import_apply.py,
    переведён на эту функцию)."""
    from app.services.payroll_category_guard import is_goods_or_services

    assert is_goods_or_services("товар") is True
    assert is_goods_or_services("услуга") is True
    assert is_goods_or_services("работа") is True
    assert is_goods_or_services(None) is False
    assert is_goods_or_services("") is False


@pytest.mark.asyncio
async def test_create_purchase_header_payroll_beats_stale_item_category(
    client, db_session, test_org, superadmin_headers,
):
    """create_purchase, feo_per_item=False («одна категория на всю закупку»):
    эффективная категория позиции — ВСЕГДА категория шапки, даже если у
    позиции прислана СВОЯ (протухшая) категория товаров — effective_item_
    feo_category_id (app/services/feo_effective_category.py), не `item.cat
    or header`. Раньше `_pi.feo_category_id or data.feo_category_id` брал
    протухшую категорию товаров и МОЛЧА пропускал товар в ФОТ-закупку."""
    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    goods_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Товары (протухшая)")
    db_session.add(goods_cat)
    await db_session.commit()

    resp = await client.post(
        "/api/purchases/?context=service_note_delivery",
        json={
            "subsidy_id": subsidy.id,
            "feo_category_id": payroll_cat.id,
            "feo_per_item": False,
            "purchase_method": "advance",
            "items": [{
                "item_name": "Генератор",
                "item_type": "товар",
                "feo_category_id": goods_cat.id,
                "quantity": 1,
                "unit_price": 1000,
                "total_price": 1000,
            }],
        },
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "ФОТ" in resp.json().get("message", "")


@pytest.mark.asyncio
async def test_create_purchase_per_item_mode_uses_own_category_not_header(
    client, db_session, test_org, superadmin_headers,
):
    """feo_per_item=True («разные категории для каждого товара»): шапка в
    ФОТ не блокирует позицию с СОБСТВЕННОЙ категорией товаров — эффективная
    категория позиции здесь своя, не шапки."""
    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    goods_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Товары")
    db_session.add(goods_cat)
    await db_session.commit()

    resp = await client.post(
        "/api/purchases/?context=service_note_delivery",
        json={
            "subsidy_id": subsidy.id,
            "feo_category_id": payroll_cat.id,
            "feo_per_item": True,
            "purchase_method": "advance",
            "items": [{
                "item_name": "Генератор",
                "item_type": "товар",
                "feo_category_id": goods_cat.id,
                "quantity": 1,
                "unit_price": 1000,
                "total_price": 1000,
            }],
        },
        headers=superadmin_headers,
    )
    assert resp.status_code in (200, 201), resp.text


@pytest.mark.asyncio
async def test_update_planned_item_type_change_to_goods_in_payroll_rejected(db_session, superadmin_user):
    """feo_item_write.update_planned_item: позиция УЖЕ лежит в статье ФОТ без
    типа (как «ЗП»), смена ТОЛЬКО item_type на «товар» (категория не
    меняется) — 422 (итоговая пара категория+тип проверяется, не только
    момент смены категории)."""
    from app.services import feo_item_write
    from app.schemas.feo import FeoPlannedItemCreate

    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    item = FeoPlannedItem(
        feo_category_id=payroll_cat.id, name="ЗП", item_type=None,
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=True,
    )
    db_session.add(item)
    await db_session.commit()

    data = FeoPlannedItemCreate(
        feo_category_id=payroll_cat.id, name="ЗП", item_type="товар",
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=True,
    )
    with pytest.raises(HTTPException) as exc:
        await feo_item_write.update_planned_item(db_session, superadmin_user, item, data, create_version=False)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_update_planned_item_untouched_legacy_violation_not_blocked(db_session, superadmin_user):
    """Позиция, заведённая ДО этого правила (товар уже лежит в статье ФОТ) —
    PUT, не трогающий ни категорию, ни тип (например, правка количества), не
    спотыкается на уже существующем нарушении — проверка только при
    РЕАЛЬНОЙ смене категории или типа."""
    from app.services import feo_item_write
    from app.schemas.feo import FeoPlannedItemCreate

    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session)
    item = FeoPlannedItem(
        feo_category_id=payroll_cat.id, name="Генератор (легаси)", item_type="товар",
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=True,
    )
    db_session.add(item)
    await db_session.commit()

    data = FeoPlannedItemCreate(
        feo_category_id=payroll_cat.id, name="Генератор (легаси)", item_type="товар",
        quantity=Decimal("2"), amount=Decimal("2000"), is_active=True,
    )
    result = await feo_item_write.update_planned_item(db_session, superadmin_user, item, data, create_version=False)
    assert result.quantity == Decimal("2")


@pytest.mark.asyncio
async def test_assert_category_can_become_payroll_finds_purchase_item_via_header(
    db_session,
):
    """Товар закупки без СВОЕЙ feo_category_id (категория только на шапке,
    feo_per_item=False) — должен найтись через эффективную категорию, иначе
    такую закупку assert_category_can_become_payroll молча не увидел бы."""
    subsidy = Subsidy(
        name=f"TestPayrollToggleHeader-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование", is_payroll=False)
    db_session.add(cat)
    await db_session.flush()
    purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, feo_per_item=False,
        status="plan_schedule", purchase_method="advance",
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Генератор", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
        feo_category_id=None,  # категория ТОЛЬКО на шапке
    )
    db_session.add(item)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await assert_category_can_become_payroll(db_session, cat.id)
    assert exc.value.status_code == 422
    assert "Генератор" in exc.value.detail


@pytest.mark.asyncio
async def test_assert_category_can_become_payroll_ignores_stopped_purchase(db_session):
    """Остановленная закупка (stopped_at задан) не блокирует включение
    is_payroll — она больше не расходует план."""
    import datetime

    subsidy = Subsidy(
        name=f"TestPayrollToggleStopped-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование", is_payroll=False)
    db_session.add(cat)
    await db_session.flush()
    purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, feo_per_item=False,
        status="plan_schedule", purchase_method="advance",
        stopped_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Генератор", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
        feo_category_id=None,
    )
    db_session.add(item)
    await db_session.commit()

    await assert_category_can_become_payroll(db_session, cat.id)  # не бросает


# ---------------------------------------------------------------------------
# (д) QA S5 (22.10.2026): WishItem.item_type Column(default="товар") срабатывал
# и на явный None — убран, дефолт теперь только в default_wish_item_type.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_wish_from_plan_untyped_item_in_payroll_stores_null(
    db_session, test_org, superadmin_user,
):
    """Заявка «на основе плана» по плановой позиции БЕЗ типа (как «ЗП») в
    статье ФОТ — в БД WishItem.item_type IS NULL (не 'товар'), иначе
    payroll_category_guard отклонил бы законную заявку."""
    from app.services.plan_to_wish import PlanToWishItemInput, create_wish_from_plan
    from sqlalchemy import select as _select

    subsidy, payroll_cat = await _make_subsidy_with_payroll_category(db_session, name="ФОТ")
    fpi = FeoPlannedItem(
        feo_category_id=payroll_cat.id, name="ЗП", item_type=None,
        quantity=Decimal("1"), amount=Decimal("50000.00"), unit_price=Decimal("50000.00"),
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()

    result = await create_wish_from_plan(
        db_session, superadmin_user, subsidy.id, "Заявка на ЗП",
        [PlanToWishItemInput(feo_planned_item_id=fpi.id, quantity=Decimal("1"), item_name="ЗП")],
    )
    wish_id = result["wish_id"]

    db_item_type = (await db_session.execute(
        _select(WishItem.item_type).where(WishItem.wish_id == wish_id)
    )).scalar_one()
    assert db_item_type is None


@pytest.mark.asyncio
async def test_create_wish_no_item_type_key_defaults_to_goods(
    client, db_session, test_org, superadmin_headers,
):
    """Обычная заявка (ручное создание, ключ item_type вообще не прислан) —
    дефолт 'товар' сохраняется (поведение не изменилось для обычных заявок)."""
    from sqlalchemy import select as _select

    subsidy = Subsidy(
        name=f"TestWishDefaultType-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.commit()

    resp = await client.post(
        "/api/wishes/",
        json={
            "title": "Заявка без указания типа",
            "subsidy_id": subsidy.id,
            "items": [{
                "item_name": "Молоток",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 500,
                "total_price": 500,
            }],
        },
        headers=superadmin_headers,
    )
    assert resp.status_code == 201, resp.text
    wish_id = resp.json()["id"]

    db_item_type = (await db_session.execute(
        _select(WishItem.item_type).where(WishItem.wish_id == wish_id)
    )).scalar_one()
    assert db_item_type == "товар"


@pytest.mark.asyncio
async def test_assert_category_can_become_payroll_ignores_inactive_planned_item(db_session):
    """Деактивированная плановая позиция (is_active=False) не считается
    «лежащей в статье» — не блокирует включение is_payroll."""
    subsidy = Subsidy(
        name=f"TestPayrollToggleInactive-{id(db_session)}", year=2026, budget=0,
        require_planned_dates=False, status="approved",
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Оборудование", is_payroll=False)
    db_session.add(cat)
    await db_session.flush()
    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Генератор", item_type="товар",
        quantity=Decimal("1"), amount=Decimal("1000"), is_active=False,
    )
    db_session.add(fpi)
    await db_session.commit()

    await assert_category_can_become_payroll(db_session, cat.id)  # не бросает
