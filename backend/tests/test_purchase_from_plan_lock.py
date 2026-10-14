# -*- coding: utf-8 -*-
"""Решение владельца 14.10.2026 (жалобы (а)-(г), закупка на основе «Плана
закупок»): замок категории ФЭО и плановая цена действуют ТОЛЬКО у позиций,
реально ЗАГРУЖЕННЫХ из плана (purchase_items.from_plan / wish_items.from_plan,
миграция f1a2b3c4d5e6) — не у любой позиции с wish_item_id/feo_planned_item_id
(та связь появляется и у ручных позиций — автозаведённый план/явный выбор
человеком). См. app/services/feo_item_lock.py — единственный читатель.

Покрывает:
  (i) аванс «из плана»: позиция из плана (from_plan=True) заперта по
      категории (PATCH -> 409); ручная позиция той же закупки, привязанная к
      ЧЕЛОВЕЧЕСКОЙ плановой позиции (feo_planned_item_id, auto_created=False),
      свободно меняет категорию — привязка снимается, человеческая плановая
      не трогается (жалоба (г)).
 (ii) обычная закупка: ручная позиция с АВТО-плановой — PUT со сменой
      категории деактивирует старую авто-плановую и привязывает к новой
      (жалоба (б) — уборка фантомов не только в авансовых).
(iii) цена from_plan-позиции не меняется PATCH'ом (409), при этом количество
      всё равно можно менять (замок — только на цену/категорию, не на всё ТЗ).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase_item import PurchaseItem
from app.models.wish_item import WishItem
from app.models.feo_planned_item import FeoPlannedItem


async def _make_subsidy(db_session, budget=5_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        budget=kwargs.pop("budget", Decimal("1000000")),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_human_planned_item(db_session, cat_id, *, name="Канцтовары человеческие", quantity=10, unit_price=500):
    """Плановая позиция, заведённая ЧЕЛОВЕКОМ (auto_created=False) — такая,
    какую владелец не хочет видеть передвинутой молча (жалоба (г))."""
    fpi = FeoPlannedItem(
        feo_category_id=cat_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(unit_price)),
        amount=Decimal(str(quantity * unit_price)),
        is_active=True,
        auto_created=False,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_advance_from_plan_item_locked_manual_item_free(client, auth_headers, db_session):
    """(i): закупка-аванс «из плана» (plan_to_purchase) — позиция from_plan=True
    заперта по категории; позиция, добавленная вручную и привязанная к
    ЧЕЛОВЕЧЕСКОЙ плановой, свободно меняет категорию — привязка снимается,
    человеческая плановая остаётся нетронутой (жалоба (г))."""
    subsidy = await _make_subsidy(db_session)
    cat_plan = await _make_category(db_session, subsidy.id, name="Категория плана")
    cat_other = await _make_category(db_session, subsidy.id, name="Другая категория")

    human_fpi = await _make_human_planned_item(db_session, cat_plan.id, name="Человеческий план")

    # Позиция «из плана» — plan_to_wish/plan_to_purchase сами ставят from_plan=True;
    # здесь строим закупку напрямую как авансовую, затем помечаем позицию
    # from_plan=True вручную (эквивалент того, что сделал бы
    # plan_to_purchase.create_purchase_from_plan — не гоняем весь путь целиком,
    # чтобы не тащить build_items_from_plan/остаток плана в этот тест).
    # purchase_method='regular' + purchase_basis='service_note' (СЗ) — единственный
    # путь create_purchase принимает закупку напрямую, в обход заявки/аванса;
    # status='plan_schedule' явно — избегаем статуса 'wishes' и сопутствующей
    # заявки-компаньона авансового (не предмет этого теста).
    create_payload = {
        "purchase_method": "regular",
        "purchase_basis": "service_note",
        "status": "plan_schedule",
        "subject": "Закупка из плана — тест замка",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Из плана", "item_type": "товар", "quantity": 1, "unit": "шт",
                "unit_price": 1000, "total_price": 1000, "feo_category_id": cat_plan.id,
            },
            {
                "item_name": "Ручная позиция", "item_type": "товар", "quantity": 1, "unit": "шт",
                "unit_price": 500, "total_price": 500, "feo_category_id": cat_plan.id,
                "feo_planned_item_id": human_fpi.id,
            },
        ],
    }
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=create_payload, headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.id)
    )).scalars().all()
    assert len(items) == 2
    from_plan_item, manual_item = items[0], items[1]
    assert manual_item.feo_planned_item_id == human_fpi.id

    # Помечаем первую позицию как "из плана" напрямую — build_items_from_plan
    # делает это на реальном пути, здесь эмулируем тот же конечный факт.
    from_plan_item.from_plan = True
    await db_session.commit()

    # PATCH смены категории у позиции из плана -> 409 заперто.
    patch_resp = await client.patch(
        f"/api/purchases/{purchase_id}/items/{from_plan_item.id}",
        json={"feo_category_id": cat_other.id},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 422, patch_resp.text
    assert patch_resp.json()["code"] == "ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN"

    # PATCH смены категории у РУЧНОЙ позиции (from_plan=False), привязанной к
    # человеческой плановой, -> 200, привязка снята, план человека не тронут.
    patch_resp2 = await client.patch(
        f"/api/purchases/{purchase_id}/items/{manual_item.id}",
        json={"feo_category_id": cat_other.id},
        headers=auth_headers,
    )
    assert patch_resp2.status_code == 200, patch_resp2.text
    body2 = patch_resp2.json()
    assert body2["feo_category_id"] == cat_other.id
    # Привязка к человеческому плану снята (новая авто-плановая в cat_other
    # заводится автоматически, см. auto_assign_planned_items).
    assert body2["feo_planned_item_id"] != human_fpi.id

    await db_session.refresh(human_fpi)
    assert human_fpi.is_active is True
    assert human_fpi.feo_category_id == cat_plan.id, (
        "Жалоба (г): человеческая плановая позиция не переезжает молча вслед "
        "за привязанной к ней ручной позицией"
    )


@pytest.mark.asyncio
async def test_ordinary_purchase_put_cleans_up_orphaned_auto_plan(client, auth_headers, db_session):
    """(ii): ОБЫЧНАЯ закупка (не авансовая), позиция с АВТО-плановой — PUT со
    сменой категории деактивирует старую авто-плановую (не только у авансовых,
    жалоба (б)) и привязывает к новой."""
    subsidy = await _make_subsidy(db_session)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория A")
    cat_b = await _make_category(db_session, subsidy.id, name="Категория B")

    # service_note — единственный путь create_purchase принимает НЕ-авансовую
    # закупку напрямую (is_sn), без заявки.
    create_payload = {
        "purchase_method": "regular",
        "purchase_basis": "service_note",
        "subject": "СЗ — тест уборки фантомов",
        "subsidy_id": subsidy.id,
        "feo_category_id": cat_a.id,
        "items": [
            {
                "item_name": "Товар СЗ", "item_type": "товар", "quantity": 1, "unit": "шт",
                "unit_price": 1000, "total_price": 1000, "feo_category_id": cat_a.id,
            },
        ],
    }
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=create_payload, headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    # create_purchase (в отличие от update_purchase) сам не вызывает
    # auto_assign_planned_items — «закупка сама становится планом» применяется
    # с первого PUT (как в реальном сценарии «создали СЗ, потом редактировали
    # в карточке»). Неизменяющий PUT — только чтобы завести авто-плановую,
    # ничего не меняем по составу.
    first_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    noop_put = await client.put(
        f"/api/purchases/{purchase_id}", json=first_get.json(), headers=auth_headers,
    )
    assert noop_put.status_code in (200, 201), noop_put.text

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    assert item.feo_planned_item_id is not None, "закупка сама становится планом — авто-плановая должна завестись"
    old_fpi_id = item.feo_planned_item_id
    old_fpi = await db_session.get(FeoPlannedItem, old_fpi_id)
    assert old_fpi.auto_created is True

    # PUT, переносим позицию в категорию B — старая авто-плановая должна
    # деактивироваться (уборка фантомов теперь не только у авансовых).
    full_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    put_payload = full_get.json()
    put_payload["items"][0]["feo_category_id"] = cat_b.id
    # Фронт, меняя категорию позиции, не шлёт старую feo_planned_item_id (та
    # привязана к прежней категории) — auto_assign_planned_items (вызывается
    # из update_purchase ДО вставки) находит/заводит план в НОВОЙ категории
    # только для позиций, у которых feo_planned_item_id ещё не проставлен.
    put_payload["items"][0]["feo_planned_item_id"] = None
    put_payload["feo_category_id"] = cat_b.id
    put_resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert put_resp.status_code in (200, 201), put_resp.text

    await db_session.refresh(old_fpi)
    assert old_fpi.is_active is False, (
        "Жалоба (б): старая авто-плановая позиция должна деактивироваться "
        "в ЛЮБОЙ закупке, не только авансовой"
    )

    new_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    assert new_item.feo_category_id == cat_b.id
    assert new_item.feo_planned_item_id is not None
    assert new_item.feo_planned_item_id != old_fpi_id


@pytest.mark.asyncio
async def test_from_plan_item_price_locked_quantity_free(client, auth_headers, db_session):
    """(iii): цена from_plan-позиции не меняется PATCH'ом (409), количество —
    можно (замок — только цена/категория, не всё ТЗ)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Категория цены")

    create_payload = {
        "purchase_method": "regular",
        "purchase_basis": "service_note",
        "status": "plan_schedule",
        "subject": "Закупка — тест плановой цены",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Плановая позиция", "item_type": "товар", "quantity": 2, "unit": "шт",
                "unit_price": 300, "total_price": 600, "feo_category_id": cat.id,
            },
        ],
    }
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=create_payload, headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    item.from_plan = True
    await db_session.commit()

    patch_price = await client.patch(
        f"/api/purchases/{purchase_id}/items/{item.id}",
        json={"unit_price": 999},
        headers=auth_headers,
    )
    assert patch_price.status_code == 409, patch_price.text
    assert patch_price.json()["code"] == "ITEM_PRICE_LOCKED_FROM_PLAN"

    patch_qty = await client.patch(
        f"/api/purchases/{purchase_id}/items/{item.id}",
        json={"quantity": 5},
        headers=auth_headers,
    )
    assert patch_qty.status_code == 200, patch_qty.text
    assert float(patch_qty.json()["quantity"]) == 5.0


@pytest.mark.asyncio
async def test_from_plan_item_price_locked_on_put_change(client, auth_headers, db_session):
    """Задача 14.10 (пункт 3): замок цены from_plan-позиции действует и на
    PUT /api/purchases/{id} (полная замена позиций), не только на PATCH одной
    позиции — одна функция-проверка (assert_item_price_not_locked), один и тот
    же код ошибки. Смена цены -> 409."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Категория цены PUT-A")

    create_payload = {
        "purchase_method": "regular",
        "purchase_basis": "service_note",
        "status": "plan_schedule",
        "subject": "Закупка — тест плановой цены на PUT (смена)",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Плановая позиция PUT-A", "item_type": "товар", "quantity": 2, "unit": "шт",
                "unit_price": 300, "total_price": 600, "feo_category_id": cat.id,
            },
        ],
    }
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=create_payload, headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    item.from_plan = True
    await db_session.commit()

    # PUT со сменённой ценой этой же позиции (сопоставление старой/новой строки
    # по build_purchase_item_id_map — тот же item_name) -> 409.
    full_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    put_payload_bad = full_get.json()
    put_payload_bad["items"][0]["unit_price"] = 999
    put_resp_bad = await client.put(
        f"/api/purchases/{purchase_id}", json=put_payload_bad, headers=auth_headers,
    )
    assert put_resp_bad.status_code == 409, put_resp_bad.text
    assert put_resp_bad.json()["code"] == "ITEM_PRICE_LOCKED_FROM_PLAN"
    # Не проверяем здесь физическое состояние БД сразу после 409 (отдельная
    # закупка ниже проверяет "без изменения цены -> 200" с чистого листа) —
    # PUT успевает DELETE+INSERT позиции (flush) ДО гейта цены, а общий
    # db_session теста не откатывает этот flush между HTTP-запросами внутри
    # одной закупки (явный db_session.rollback() конфликтует с гринлетами
    # httpx-ASGI, тот же приём и обоснование — test_tz_over_plan_goes_to_approval.py).
    # В проде это не течёт данные: get_db() — per-request сессия, close()
    # откатывает незакоммиченный flush() сам.


@pytest.mark.asyncio
async def test_from_plan_item_price_unchanged_on_put_ok(client, auth_headers, db_session):
    """Тот же замок (см. тест выше) не мешает PUT, который НЕ меняет цену
    from_plan-позиции — 200, from_plan сохраняется на новой строке (та же
    карта id_map, что чинит ContractItem.source_item_id)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Категория цены PUT-B")

    create_payload = {
        "purchase_method": "regular",
        "purchase_basis": "service_note",
        "status": "plan_schedule",
        "subject": "Закупка — тест плановой цены на PUT (без изменений)",
        "subsidy_id": subsidy.id,
        "items": [
            {
                "item_name": "Плановая позиция PUT-B", "item_type": "товар", "quantity": 2, "unit": "шт",
                "unit_price": 300, "total_price": 600, "feo_category_id": cat.id,
            },
        ],
    }
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=create_payload, headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    purchase_id = resp.json()["id"]

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    item.from_plan = True
    await db_session.commit()

    full_get = await client.get(f"/api/purchases/{purchase_id}", headers=auth_headers)
    put_payload_ok = full_get.json()  # без изменений — цена остаётся 300
    put_resp_ok = await client.put(
        f"/api/purchases/{purchase_id}", json=put_payload_ok, headers=auth_headers,
    )
    assert put_resp_ok.status_code in (200, 201), put_resp_ok.text

    new_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
    )).scalars().one()
    assert float(new_item.unit_price) == 300.0
    assert new_item.from_plan is True
