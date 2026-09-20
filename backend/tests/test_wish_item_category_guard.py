"""Задача 3 (владелец, 2026-09-20): «Гейт категории у позиций заявки из
плана» — app.services.wish_item_category_guard.assert_wish_item_category_from_plan.

Позиция, привязанная к плановой позиции плана закупок (feo_planned_item_id),
не может сменить категорию ФЭО мимо неё — сначала прямой вызов сервисной
функции, затем оба подключённых места: PATCH /api/wishes/{wish_id}/items/{item_id}
и PUT /api/wishes/{wish_id} (черновик, пересбор позиций).
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.services.wish_item_category_guard import (
    CATEGORY_FROM_PLAN_MESSAGE,
    assert_wish_item_category_from_plan,
)


async def _make_subsidy_two_categories(db_session):
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, status="approved", require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=3, name="Категория А")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=3, name="Категория Б")
    db_session.add_all([cat_a, cat_b])
    await db_session.commit()
    await db_session.refresh(cat_a)
    await db_session.refresh(cat_b)
    return subsidy, cat_a, cat_b


@pytest.mark.asyncio
async def test_guard_blocks_mismatched_category(db_session):
    subsidy, cat_a, cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.commit()
    await db_session.refresh(planned)

    item = WishItem(item_name="Тест", feo_planned_item_id=planned.id, feo_category_id=cat_a.id, quantity=1, unit_price=100, total_price=100)

    with pytest.raises(HTTPException) as exc_info:
        await assert_wish_item_category_from_plan(db_session, item, cat_b.id)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == CATEGORY_FROM_PLAN_MESSAGE


@pytest.mark.asyncio
async def test_guard_allows_matching_category(db_session):
    subsidy, cat_a, _cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.commit()
    await db_session.refresh(planned)

    item = WishItem(item_name="Тест", feo_planned_item_id=planned.id, feo_category_id=cat_a.id, quantity=1, unit_price=100, total_price=100)

    # Не должно бросать — категория совпадает с плановой позицией.
    await assert_wish_item_category_from_plan(db_session, item, cat_a.id)


@pytest.mark.asyncio
async def test_guard_noop_without_planned_item(db_session):
    """Позиция без feo_planned_item_id — гейт не касается, любая категория ОК."""
    item = WishItem(item_name="Тест", feo_planned_item_id=None, feo_category_id=None, quantity=1, unit_price=100, total_price=100)
    await assert_wish_item_category_from_plan(db_session, item, 999999)  # любой id, не бросает


@pytest.mark.asyncio
async def test_patch_wish_item_feo_category_blocked_when_mismatched(client, db_session, test_org, test_user, auth_headers):
    subsidy, cat_a, cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.flush()

    w = Wish(org_id=test_org.id, title="Заявка", status="draft", created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id)
    db_session.add(w)
    await db_session.flush()
    item = WishItem(wish_id=w.id, item_name="Позиция", feo_planned_item_id=planned.id, feo_category_id=cat_a.id, quantity=1, unit_price=100, total_price=100)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(f"/api/wishes/{w.id}/items/{item.id}", json={"feo_category_id": cat_b.id}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["message"] == CATEGORY_FROM_PLAN_MESSAGE

    await db_session.refresh(item)
    assert item.feo_category_id == cat_a.id  # не изменилось


@pytest.mark.asyncio
async def test_patch_wish_item_feo_category_allowed_when_matching(client, db_session, test_org, test_user, auth_headers):
    subsidy, cat_a, _cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.flush()

    w = Wish(org_id=test_org.id, title="Заявка", status="draft", created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id)
    db_session.add(w)
    await db_session.flush()
    item = WishItem(wish_id=w.id, item_name="Позиция", feo_planned_item_id=planned.id, feo_category_id=cat_a.id, quantity=1, unit_price=100, total_price=100)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(f"/api/wishes/{w.id}/items/{item.id}", json={"feo_category_id": cat_a.id, "target_column_key": "col-1"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["feo_category_id"] == cat_a.id
    assert resp.json()["target_column_key"] == "col-1"


@pytest.mark.asyncio
async def test_patch_wish_item_target_column_key_only_untouched_category(client, db_session, test_org, test_user, auth_headers):
    """Обычный drag-drop (без feo_category_id в теле) не трогает и не гейтит
    существующую категорию, даже если она рассогласована с плановой позицией."""
    subsidy, cat_a, cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.flush()

    w = Wish(org_id=test_org.id, title="Заявка", status="draft", created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id)
    db_session.add(w)
    await db_session.flush()
    item = WishItem(wish_id=w.id, item_name="Позиция", feo_planned_item_id=planned.id, feo_category_id=cat_b.id, quantity=1, unit_price=100, total_price=100)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(f"/api/wishes/{w.id}/items/{item.id}", json={"target_column_key": "col-2"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_update_wish_draft_recreate_blocks_stale_planned_item_link(client, db_session, test_org, test_user, auth_headers):
    """Пересбор черновика: payload несёт feo_planned_item_id (старая привязка),
    но feo_category_id новой (другой) категории — гейт блокирует 422, WishItem
    для этой позиции НЕ создаётся (транзакция не коммитится)."""
    subsidy, cat_a, cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.flush()

    w = Wish(org_id=test_org.id, title="Заявка", status="draft", created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    payload = {
        "items": [
            {
                "item_name": "Позиция",
                "quantity": 1,
                "unit_price": 100,
                "total_price": 100,
                "feo_planned_item_id": planned.id,
                "feo_category_id": cat_b.id,  # рассогласовано с planned.feo_category_id == cat_a.id
            }
        ]
    }
    resp = await client.put(f"/api/wishes/{w.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["message"] == CATEGORY_FROM_PLAN_MESSAGE

    # Гейт сработал ДО db.add(wi) для этой позиции — ничего не должно было
    # persist-иться (вся заявка осталась без позиций).
    from sqlalchemy import select as _select
    rows = (await db_session.execute(_select(WishItem).where(WishItem.wish_id == w.id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_update_wish_draft_recreate_allows_consistent_planned_item_link(client, db_session, test_org, test_user, auth_headers):
    subsidy, cat_a, _cat_b = await _make_subsidy_two_categories(db_session)
    planned = FeoPlannedItem(feo_category_id=cat_a.id, name="Позиция плана", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"), is_active=True)
    db_session.add(planned)
    await db_session.flush()

    w = Wish(org_id=test_org.id, title="Заявка", status="draft", created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat_a.id)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    payload = {
        "items": [
            {
                "item_name": "Позиция",
                "quantity": 1,
                "unit_price": 100,
                "total_price": 100,
                "feo_planned_item_id": planned.id,
                "feo_category_id": cat_a.id,
            }
        ]
    }
    resp = await client.put(f"/api/wishes/{w.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    # Проверка по БД, не по resp.json()["items"]: у update_wish (draft-ветка)
    # есть отдельная, не связанная с этой задачей особенность — `wish` внутри
    # обработчика уже был загружен (selectinload) ДО пересборки позиций, и
    # session создан с expire_on_commit=False (app/database.py), поэтому
    # relationship-коллекция `wish.items`, участвующая в финальной сериализации
    # ответа, может не увидеть строки, добавленные позже в ТОМ ЖЕ запросе, пока
    # объект не будет явно инвалидирован. Позиция гейта здесь — что запись
    # реально дошла до БД (успешный путь через assert_wish_item_category_from_plan
    # не блокирует persist), это и проверяем напрямую.
    from sqlalchemy import select as _select
    db_rows = (await db_session.execute(_select(WishItem).where(WishItem.wish_id == w.id))).scalars().all()
    assert len(db_rows) == 1
    assert db_rows[0].feo_category_id == cat_a.id
    assert db_rows[0].feo_planned_item_id == planned.id
