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


@pytest.mark.asyncio
async def test_food_and_accommodation_copy_contract_and_delivery_stages(
    client, db_session, make_purchase, admin_headers,
):
    """Перенос ТЗ → Договор (с сохранением extra_attrs/item_form и пересчётом
    сумм договора) и перенос Договор → Поставка (extra_attrs['_accepted'] и
    final_total) для Проживания и Питания."""
    from app.models.contract_item import ContractItem
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(
        status="delivered", purchase_method="advance", subject="Проживание и питание стадии",
    )
    tz_payload = {
        "subject": "Проживание и питание стадии",
        "purchase_method": "advance",
        "contract_form": "services_accommodation_food",
        "items": [
            {
                "item_name": "Проживание",
                "item_form": "accommodation",
                "unit_price": "5000",
                "extra_attrs": {"price_basis": "room", "rooms": 4, "nights": 2},
            },
            {
                "item_name": "Организация питания",
                "item_form": "food",
                "unit_price": "300",
                "extra_attrs": {"mode": "simple", "persons": 10, "meals_per_day": 3, "days": 2},
            },
        ],
    }
    r_tz = await client.put(f"/api/purchases/{p.id}", json=tz_payload, headers=admin_headers)
    assert r_tz.status_code == 200, r_tz.text

    # 1. Кнопка «Перенести все позиции из ТЗ в договор»
    r_copy = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase",
        headers=admin_headers,
    )
    assert r_copy.status_code == 200, r_copy.text
    ci_list = r_copy.json()
    assert len(ci_list) == 2
    ci_by_form = {c["item_form"]: c for c in ci_list}
    assert Decimal(str(ci_by_form["accommodation"]["total"])) == Decimal("40000.00")
    assert Decimal(str(ci_by_form["food"]["total"])) == Decimal("18000.00")
    assert ci_by_form["accommodation"]["extra_attrs"]["nights"] == 2
    assert ci_by_form["food"]["extra_attrs"]["days"] == 2

    # 2. Правка «Как в договоре» через PUT /contract-items — сервер пересчитывает
    #    quantity и total по extra_attrs (nights=3 для проживания, уменьшение человек для питания).
    ci_acc = ci_by_form["accommodation"]
    ci_food = ci_by_form["food"]
    put_ci_payload = [
        {
            "source_item_id": ci_acc["source_item_id"],
            "name": ci_acc["name"],
            "item_form": "accommodation",
            "unit_price": "4500",
            "extra_attrs": {"price_basis": "room", "rooms": 4, "nights": 2},
        },
        {
            "source_item_id": ci_food["source_item_id"],
            "name": ci_food["name"],
            "item_form": "food",
            "unit_price": "250",
            "extra_attrs": {"mode": "simple", "persons": 10, "meals_per_day": 3, "days": 2},
        },
    ]
    r_put_ci = await client.put(
        f"/api/purchases/{p.id}/contract-items",
        json=put_ci_payload,
        headers=admin_headers,
    )
    assert r_put_ci.status_code == 200, r_put_ci.text
    updated_cis = {c["item_form"]: c for c in r_put_ci.json()}
    assert Decimal(str(updated_cis["accommodation"]["total"])) == Decimal("36000.00")
    assert Decimal(str(updated_cis["food"]["total"])) == Decimal("15000.00")

    # 3. Перенос «из договора в поставку» (Как поставили)
    r_del = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-to-delivery",
        headers=admin_headers,
    )
    assert r_del.status_code == 200, r_del.text
    del_items = r_del.json()["items"]
    assert len(del_items) == 2
    totals = sorted(Decimal(str(it["final_total"])) for it in del_items)
    assert totals == [Decimal("15000.00"), Decimal("36000.00")]
    assert all("_accepted" in (it["extra_attrs"] or {}) for it in del_items)

    # Проверяем, что копирование обратно ТЗ → Договор не тянет служебный ключ _accepted
    r_recopy = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase",
        headers=admin_headers,
    )
    assert r_recopy.status_code == 200, r_recopy.text
    assert all("_accepted" not in (c["extra_attrs"] or {}) for c in r_recopy.json())
    db_cis = (await db_session.execute(
        select(ContractItem).where(ContractItem.purchase_id == p.id)
    )).scalars().all()
    assert all("_accepted" not in (ci.extra_attrs or {}) for ci in db_cis)
    db_pis = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert all("_accepted" in (pi.extra_attrs or {}) for pi in db_pis)
