"""item-forms-accommodation-transport.md, шаг 1: PUT закупки с формой
позиции пересчитывает total_price сервером (ПРАВИЛО №6 — сервер побеждает,
как и остальные суммы закупки), GET/PUT-ответ отдаёт extra_attrs как есть, и
конвертация заявки копирует extra_attrs из WishItem в PurchaseItem.

Паттерн PUT/wish-фикстур — по образцу tests/test_item_contractor_write_paths.py
(тот же файл семьи «единственный писатель», тот же способ поднять
Purchase/Wish в тесте).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_put_purchase_accommodation_recomputes_total(client, db_session, make_purchase, auth_headers):
    """contract_form=services_accommodation → item_form=accommodation:
    quantity/total_price выставляются сервером из extra_attrs (rooms/price_basis/
    nights), не из присланных quantity/total_price. Владелец: 6600 × 8 × 1 = 52800."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(status="plan_schedule", purchase_method="advance", subject="Проживание")

    payload = {
        "subject": "Проживание",
        "purchase_method": "advance",
        "contract_form": "services_accommodation",
        "items": [{
            "item_name": "Номер стандарт",
            # quantity/total_price ниже — заведомо ЛОЖНЫЕ значения, чтобы
            # доказать, что сервер их игнорирует и считает сам из extra_attrs.
            "quantity": "1",
            "unit_price": "6600",
            "total_price": "1",
            "extra_attrs": {"price_basis": "room", "rooms": 8, "persons": 0, "nights": 1},
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    assert Decimal(str(out_item["quantity"])) == Decimal("8")
    assert Decimal(str(out_item["total_price"])) == Decimal("52800.00")
    assert out_item["extra_attrs"]["rooms"] == 8

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().first()
    assert db_item.quantity == Decimal("8")
    assert db_item.total_price == Decimal("52800.00")
    assert db_item.extra_attrs == {"price_basis": "room", "rooms": 8, "persons": 0, "nights": 1}


@pytest.mark.asyncio
async def test_put_purchase_transport_recomputes_total(client, db_session, make_purchase, auth_headers):
    """contract_form=services_transport → item_form=transport, режим «по часам»:
    quantity = work_hours + supply_hours, unit_price = hourly_rate.
    Владелец: 1500 ₽/ч × (5 работы + 2 подачи) = 10500."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(status="plan_schedule", purchase_method="advance", subject="Перевозки")

    payload = {
        "subject": "Перевозки",
        "purchase_method": "advance",
        "contract_form": "services_transport",
        "items": [{
            "item_name": "Автобус",
            "quantity": "1",
            "unit_price": "1",
            "total_price": "1",
            "extra_attrs": {
                "work_hours": 5, "supply_hours": 2, "hourly_rate": 1500, "cost_mode": "hours",
            },
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    assert Decimal(str(out_item["quantity"])) == Decimal("7")
    assert Decimal(str(out_item["unit_price"])) == Decimal("1500")
    assert Decimal(str(out_item["total_price"])) == Decimal("10500.00")

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().first()
    assert db_item.total_price == Decimal("10500.00")


@pytest.mark.asyncio
async def test_put_purchase_transport_trip_mode(client, db_session, make_purchase, auth_headers):
    """Режим «стоимость рейса вручную»: total = введённая сумма, quantity=1."""
    p = await make_purchase(status="plan_schedule", purchase_method="advance", subject="Перевозки рейс")

    payload = {
        "subject": "Перевозки рейс",
        "purchase_method": "advance",
        "contract_form": "services_transport",
        "items": [{
            "item_name": "Автобус (рейс)",
            "quantity": "1",
            "unit_price": "1",
            "total_price": "1",
            "extra_attrs": {"cost_mode": "trip", "trip_cost": 12000},
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    assert Decimal(str(out_item["quantity"])) == Decimal("1")
    assert Decimal(str(out_item["total_price"])) == Decimal("12000.00")


@pytest.mark.asyncio
async def test_put_purchase_ordinary_form_trusts_client_total(client, db_session, make_purchase, auth_headers):
    """Регресс: без contract_form (обычная позиция) сервер НЕ пересчитывает
    total_price — существующее поведение (клиент считает сам) не меняется."""
    p = await make_purchase(status="plan_schedule", purchase_method="advance", subject="Обычная")

    payload = {
        "subject": "Обычная",
        "purchase_method": "advance",
        "items": [{
            "item_name": "Товар",
            "quantity": "3",
            "unit_price": "100",
            "total_price": "300",
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    assert Decimal(str(out_item["total_price"])) == Decimal("300")
    assert out_item["extra_attrs"] == {}


@pytest.mark.asyncio
async def test_wish_convert_copies_extra_attrs(
    client, db_session, superadmin_headers, test_org, test_user,
):
    """POST /api/wishes/{id}/convert копирует WishItem.extra_attrs в
    PurchaseItem.extra_attrs (item-forms-accommodation-transport.md, шаг 4:
    «конвертация заявки копирует extra_attrs») — тот же сценарий, что и
    существующий tests/test_item_contractor_write_paths.py::
    test_wish_convert_item_contractor_fk_wins_over_mismatched_text, только
    проверяем extra_attrs вместо контрагента."""
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = Subsidy(name=f"TestSubsidy-extra-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    wish = Wish(
        org_id=test_org.id,
        title="Заявка на проживание",
        status="approved",
        created_by=test_user.id,
        subsidy_id=subsidy.id,
        feo_category_id=feo_cat.id,
    )
    db_session.add(wish)
    await db_session.flush()
    _extra = {"price_basis": "room", "rooms": 8, "persons": 0, "nights": 1}
    db_session.add(WishItem(
        wish_id=wish.id, item_name="Номер стандарт",
        quantity=8, unit_price=6600, total_price=52800,
        feo_category_id=feo_cat.id,
        extra_attrs=_extra,
    ))
    await db_session.commit()

    resp = await client.post(f"/api/wishes/{wish.id}/convert", json={}, headers=superadmin_headers)
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["purchase_id"]

    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase is not None

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().first()
    assert db_item is not None
    assert db_item.extra_attrs == _extra
