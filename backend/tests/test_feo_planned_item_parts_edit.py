"""PATCH /api/feo-planned-items/{id}/parts/{key} — правка одной части
объединённой плановой позиции (владелец, 13.10.2026, «План закупок» →
«План vs факт» → строка «Как запланировано»).

Переиспользует subsidy_with_plan/_grant из test_fact_import_commit.py и
test_fact_import_merged_parts.py (Правило №6 — та же фикстура субсидии с
планом, второй копии не заводим). Тело правки — app.services.
feo_planned_item_parts_edit (прямой юнит-тест сервиса) + обёртка роутера
(HTTP-тест прав/гейта/404).

Запускать по одному файлу (флейк "different loop", см. conftest.py)."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.entity_change import EntityChange
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services import feo_history
from app.services.feo_planned_item_parts_edit import (
    FeoPlannedItemPartUpdate, PartEditForbidden, PartNotFound,
    update_planned_item_part,
)

from tests.test_fact_import_commit import subsidy_with_plan  # noqa: F401


async def _grant_tab(db_session, key: str = "feo_categories"):
    db_session.add(RolePermission(role_name="employee", key=key, granted=True))
    await db_session.commit()


def _item_with_parts(cat, amount, parts):
    return FeoPlannedItem(feo_category_id=cat.id, name="Позиция с частями", amount=amount, is_active=True, parts=parts)


# ── Сервис (юнит, без HTTP) ──────────────────────────────────────────────

async def test_service_edits_part_within_plan(db_session, test_user, subsidy_with_plan):
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 103000, [
        {"key": "1", "row": 1, "qty": 2.0, "unit": "шт", "unit_price": 1000.0, "amount": 2000.0},
        {"key": "2", "row": 2, "qty": None, "unit": None, "unit_price": None, "amount": 98000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    updated = await update_planned_item_part(
        db_session, test_user, item, "1",
        FeoPlannedItemPartUpdate(quantity=Decimal("5"), unit_price=Decimal("1000")),
    )
    await db_session.commit()

    part1 = next(p for p in updated.parts if p["key"] == "1")
    assert part1["qty"] == 5.0
    assert part1["unit_price"] == 1000.0
    # amount = qty × unit_price, посчитано сервером (задача владельца).
    assert part1["amount"] == 5000.0
    assert part1["key"] == "1"  # part.key не меняется


async def test_service_amount_only_input(db_session, test_user, subsidy_with_plan):
    """«Можно ввести только сумму» — без кол-ва/цены."""
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 100000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 2000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    updated = await update_planned_item_part(
        db_session, test_user, item, "1", FeoPlannedItemPartUpdate(amount=Decimal("3500")),
    )
    await db_session.commit()
    part1 = next(p for p in updated.parts if p["key"] == "1")
    assert part1["amount"] == 3500.0
    assert part1["qty"] is None


async def test_service_rejects_excess_over_plan(db_session, test_user, subsidy_with_plan):
    """Σ частей > план позиции → ValueError/HTTPException 409 с суммой
    превышения, ничего не сохраняется."""
    from fastapi import HTTPException

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
        {"key": "2", "row": 2, "qty": None, "unit": None, "unit_price": None, "amount": 6000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    with pytest.raises(HTTPException) as exc_info:
        await update_planned_item_part(
            db_session, test_user, item, "1", FeoPlannedItemPartUpdate(amount=Decimal("5000")),
        )
    assert exc_info.value.status_code == 409
    assert "превышает план позиции" in str(exc_info.value.detail)
    assert "1,000.00" in str(exc_info.value.detail) or "1 000" in str(exc_info.value.detail)
    # Ничего не сохранилось — часть осталась прежней.
    await db_session.refresh(item)
    part1 = next(p for p in item.parts if p["key"] == "1")
    assert part1["amount"] == 4000.0


async def test_service_rejects_edit_of_purchased_part(db_session, test_user, subsidy_with_plan):
    """Часть, по которой уже есть закупка (PurchaseItem.feo_plan_part_key) —
    редактирование недоступно (PartEditForbidden → 409)."""
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    purchase = Purchase(subsidy_id=subsidy.id, status="paid", registry_number="РЕЕ-ТЕСТ-1")
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name=item.name, total_price=4000,
        feo_planned_item_id=item.id, feo_plan_part_key="1",
    ))
    await db_session.commit()

    with pytest.raises(PartEditForbidden):
        await update_planned_item_part(
            db_session, test_user, item, "1", FeoPlannedItemPartUpdate(amount=Decimal("1000")),
        )


async def test_service_part_not_found(db_session, test_user, subsidy_with_plan):
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    with pytest.raises(PartNotFound):
        await update_planned_item_part(
            db_session, test_user, item, "999", FeoPlannedItemPartUpdate(amount=Decimal("100")),
        )


async def test_service_records_history(db_session, test_user, subsidy_with_plan):
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    await update_planned_item_part(
        db_session, test_user, item, "1", FeoPlannedItemPartUpdate(amount=Decimal("4500")),
    )
    await db_session.commit()

    rows = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == feo_history.ENTITY_FEO_ITEM,
            EntityChange.entity_id == item.id,
            EntityChange.field_name == "part_1",
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == feo_history.SOURCE_MANUAL
    assert "4000" in (rows[0].old_value or "")
    assert "4500" in (rows[0].new_value or "")


async def test_service_does_not_touch_plan_changed_at(db_session, test_user, subsidy_with_plan):
    """Правка частей не меняет FeoPlannedItem.amount/quantity/unit_price
    самой позиции — plan_changed_at не должен сдвигаться (см. докстринг
    модуля и _PLAN_CHANGED_AT_WATCHED_FIELDS в app/models/feo_planned_item.py)."""
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    before = item.plan_changed_at

    await update_planned_item_part(
        db_session, test_user, item, "1", FeoPlannedItemPartUpdate(amount=Decimal("4500")),
    )
    await db_session.commit()
    await db_session.refresh(item)
    assert item.plan_changed_at == before


# ── HTTP (права/гейт/404) ────────────────────────────────────────────────

async def test_endpoint_requires_feo_categories_tab(client, auth_headers, test_user, db_session, subsidy_with_plan):
    """Без вкладки feo_categories (и без остальных прав) — 403, как у PUT
    /feo-planned-items/{id} (require_tab('feo_categories'))."""
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(
        f"/api/feo-planned-items/{item.id}/parts/1",
        json={"amount": 4500},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_endpoint_happy_path(client, auth_headers, test_user, db_session, subsidy_with_plan):
    await _grant_tab(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
        {"key": "2", "row": 2, "qty": None, "unit": None, "unit_price": None, "amount": 6000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(
        f"/api/feo-planned-items/{item.id}/parts/1",
        json={"amount": 3500},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    part1 = next(p for p in data["parts"] if p["key"] == "1")
    assert part1["amount"] == 3500.0


async def test_endpoint_excess_returns_409_with_formatted_amount(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    await _grant_tab(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
        {"key": "2", "row": 2, "qty": None, "unit": None, "unit_price": None, "amount": 6000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(
        f"/api/feo-planned-items/{item.id}/parts/1",
        json={"amount": 5000},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "превышает план позиции" in resp.text


async def test_endpoint_rejects_purchased_part(client, auth_headers, test_user, db_session, subsidy_with_plan):
    await _grant_tab(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    purchase = Purchase(subsidy_id=subsidy.id, status="paid", registry_number="РЕЕ-ТЕСТ-2")
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name=item.name, total_price=4000,
        feo_planned_item_id=item.id, feo_plan_part_key="1",
    ))
    await db_session.commit()

    resp = await client.patch(
        f"/api/feo-planned-items/{item.id}/parts/1",
        json={"amount": 1000},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


async def test_endpoint_404_unknown_part(client, auth_headers, test_user, db_session, subsidy_with_plan):
    await _grant_tab(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item = _item_with_parts(cat, 10000, [
        {"key": "1", "row": 1, "qty": None, "unit": None, "unit_price": None, "amount": 4000.0},
    ])
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(
        f"/api/feo-planned-items/{item.id}/parts/999",
        json={"amount": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 404
