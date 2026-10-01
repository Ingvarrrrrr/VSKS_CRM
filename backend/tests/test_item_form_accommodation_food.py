"""«Проживание и питание» (contract_form='services_accommodation_food') —
единственный contract_form, где форма позиции не одна на весь договор, а
хранится НА СТРОКЕ (PurchaseItem.item_form, миграция w7x8y9z0a1b2) — см.
app/services/item_forms.py::CONTRACT_FORM_ROW_CHOICES/item_form_for_row.

Паттерн PUT-фикстур — по образцу tests/test_item_forms_api.py (та же закупка-
фикстура make_purchase, тот же способ собрать payload).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_accommodation_and_food_rows_in_one_purchase(client, db_session, make_purchase, auth_headers):
    """Одна закупка contract_form=services_accommodation_food, две строки:
    проживание (item_form=accommodation, 133 чел., 1 сутки, 1265 ₽/чел.) и
    питание (item_form=food, просто: 133 чел., 1 приём, 1 день, 735 ₽/приём).
    Владелец: 133×1265=168245, 133×735=97755, итого 266000."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(
        status="plan_schedule", purchase_method="advance", subject="Проживание и питание",
    )

    payload = {
        "subject": "Проживание и питание",
        "purchase_method": "advance",
        "contract_form": "services_accommodation_food",
        "items": [
            {
                "item_name": "Услуги по организации проживания",
                "item_form": "accommodation",
                # unit_price у accommodation — прямой ввод (не производное),
                # 1265 ₽ за человека в сутки, см. extra_attrs.price_basis.
                "quantity": "1", "unit_price": "1265", "total_price": "1",
                "extra_attrs": {"price_basis": "person", "persons": 133, "rooms": 0, "nights": 1},
            },
            {
                "item_name": "Услуга по организации питания",
                "item_form": "food",
                # unit_price у food/простой режим — тоже прямой ввод, 735 ₽ за приём.
                "quantity": "1", "unit_price": "735", "total_price": "1",
                "extra_attrs": {"mode": "simple", "persons": 133, "meals_per_day": 1, "days": 1},
            },
        ],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items_out = resp.json()["items"]
    by_form = {it["item_form"]: it for it in items_out}

    accommodation_out = by_form["accommodation"]
    assert Decimal(str(accommodation_out["quantity"])) == Decimal("133")
    assert Decimal(str(accommodation_out["total_price"])) == Decimal("168245.00")

    food_out = by_form["food"]
    assert Decimal(str(food_out["quantity"])) == Decimal("133")
    assert Decimal(str(food_out["total_price"])) == Decimal("97755.00")

    purchase_total = Decimal(str(accommodation_out["total_price"])) + Decimal(str(food_out["total_price"]))
    assert purchase_total == Decimal("266000.00")

    db_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id).order_by(PurchaseItem.id)
    )).scalars().all()
    db_by_form = {it.item_form: it for it in db_items}
    assert db_by_form["accommodation"].total_price == Decimal("168245.00")
    assert db_by_form["food"].total_price == Decimal("97755.00")


@pytest.mark.asyncio
async def test_row_without_item_form_defaults_to_accommodation(client, db_session, make_purchase, auth_headers):
    """Строка без item_form (не выбрала форму) считается ПО УМОЛЧАНИЮ как
    accommodation — первая форма в CONTRACT_FORM_ROW_CHOICES (item_form_for_row)."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(
        status="plan_schedule", purchase_method="advance", subject="Проживание и питание — дефолт",
    )

    payload = {
        "subject": "Проживание и питание — дефолт",
        "purchase_method": "advance",
        "contract_form": "services_accommodation_food",
        "items": [{
            "item_name": "Без выбранной формы",
            "quantity": "1", "unit_price": "1", "total_price": "1",
            "extra_attrs": {"price_basis": "room", "rooms": 10, "nights": 2},
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    # price_basis=room, rooms=10, nights=2, unit_price было "1" до пересчёта
    # формой — для accommodation unit_price НЕ производное (вводится прямо),
    # остаётся присланным значением 1; quantity=10 (комнаты), total=10*1*2=20.
    assert Decimal(str(out_item["quantity"])) == Decimal("10")
    assert Decimal(str(out_item["total_price"])) == Decimal("20.00")

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().first()
    # Строка сама item_form не получила (клиент не прислал) — колонка остаётся
    # NULL, но расчёт уже прошёл как accommodation (дефолт item_form_for_row).
    assert db_item.item_form is None
    assert db_item.quantity == Decimal("10")


@pytest.mark.asyncio
async def test_plain_services_food_behaviour_unchanged(client, db_session, make_purchase, auth_headers):
    """Контроль: обычная закупка contract_form=services_food (форма одна на
    весь договор, НЕ строковый выбор) продолжает считаться как раньше —
    item_form_for_row не меняет поведение CONTRACT_FORM_TO_ITEM_FORM."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(status="plan_schedule", purchase_method="advance", subject="Питание")

    payload = {
        "subject": "Питание",
        "purchase_method": "advance",
        "contract_form": "services_food",
        "items": [{
            "item_name": "Организация питания",
            "quantity": "1", "unit_price": "250", "total_price": "1",
            "extra_attrs": {"mode": "simple", "persons": 10, "meals_per_day": 3, "days": 5},
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    out_item = resp.json()["items"][0]
    assert Decimal(str(out_item["quantity"])) == Decimal("150")
    assert Decimal(str(out_item["total_price"])) == Decimal("37500.00")

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().first()
    assert db_item.total_price == Decimal("37500.00")
