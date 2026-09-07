"""ПРАВИЛО №6, группа D5 — QA-находка (лимит сброшен, повторная проверка):

POST /api/purchases/ и PUT /api/purchases/{id} строили PurchaseItem прямо из
сырого dict позиции (PurchaseItem(**d)), в обход set_item_contractor. Обычное
сохранение из UI (PurchaseItemsEditor.vue шлёт contractor_id ВМЕСТЕ с
contractor_inn/contractor_name на позиции) снова заводило текст рядом с FK.

Покрывает: при позиции {contractor_id=<реальный>, contractor_inn/name=<чужой
текст>} — в БД текст NULL (FK — источник истины); в ОТВЕТЕ (не только в БД)
виден верный contractor_name/contractor_inn контрагента — POST/PUT отдают
items через тот же item_contractor.item_contractor, что и GET (QA, повторная
проверка: «голый» ORM-ответ раньше отдавал бы NULL вместо имени).

QA round 2 (P0, прод-инцидент на закупке 856): позиция ОБЯЗАНА нести реальный
product_id — сериализатор (_item_to_out) дереференсит PurchaseItem.product;
без eager-load после delete+recreate+commit это ловит MissingGreenlet. Тесты
ниже намеренно передают product_id СУЩЕСТВУЮЩЕГО (не авто-созданного в этом же
запросе) товара — фикстура с product_id=None этот баг прятала бы.
"""
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_create_purchase_item_contractor_fk_wins_over_mismatched_text(client, db_session, auth_headers):
    from app.models.contractor import Contractor
    from app.models.product import Product
    from app.models.purchase_item import PurchaseItem

    contractor = Contractor(name="ООО Ромашка", inn="7700000001")
    product = Product(name="Существующий товар для теста")
    db_session.add_all([contractor, product])
    await db_session.commit()
    await db_session.refresh(contractor)
    await db_session.refresh(product)

    payload = {
        "subject": "Test advance",
        "purchase_method": "advance",
        "items": [{
            "product_id": product.id,
            "item_name": "Товар",
            "quantity": "1",
            "unit": "шт",
            "unit_price": "100",
            "total_price": "100",
            "contractor_id": contractor.id,
            "contractor_inn": "9999999999",       # чужой текст — не должен попасть в БД
            "contractor_name": "Совсем другая контора",
        }],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    out_item = body["items"][0]
    # product_id дереференсится сериализатором (item.product.name) — если бы
    # eager-load не сработал, тут был бы 500 MissingGreenlet, а не 200.
    assert out_item["product_id"] == product.id
    assert out_item["product_name"] == product.name
    assert out_item["contractor_id"] == contractor.id
    # Ответ ОБЯЗАН показывать данные реального контрагента (не подсунутый
    # чужой текст) — тот же item_contractor(), что и GET.
    assert out_item["contractor_inn"] == contractor.inn
    assert out_item["contractor_name"] == contractor.name

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == body["id"])
    )).scalars().first()
    assert db_item.contractor_id == contractor.id
    assert db_item.contractor_inn is None
    assert db_item.contractor_name is None


@pytest.mark.asyncio
async def test_update_purchase_item_contractor_fk_wins_over_mismatched_text(client, db_session, make_purchase, auth_headers):
    from app.models.contractor import Contractor
    from app.models.product import Product
    from app.models.purchase_item import PurchaseItem

    contractor = Contractor(name="ООО Вектор", inn="7700000002")
    product = Product(name="Существующий товар для PUT-теста")
    db_session.add_all([contractor, product])
    await db_session.commit()
    await db_session.refresh(contractor)
    await db_session.refresh(product)

    p = await make_purchase(status="wishes", purchase_method="advance", subject="Test PUT")

    payload = {
        "subject": "Test PUT",
        "purchase_method": "advance",
        "items": [{
            "product_id": product.id,
            "item_name": "Товар",
            "quantity": "1",
            "unit": "шт",
            "unit_price": "100",
            "total_price": "100",
            "contractor_id": contractor.id,
            "contractor_inn": "8888888888",
            "contractor_name": "Ещё одна чужая контора",
        }],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    out_item = body["items"][0]
    # QA round 2 (P0): PUT удаляет и пересоздаёт items — без eager-load это
    # дереференсирование product дало бы 500 MissingGreenlet вместо 200.
    assert out_item["product_id"] == product.id
    assert out_item["product_name"] == product.name
    assert out_item["contractor_id"] == contractor.id
    # QA (лимит сброшен): ответ PUT обязан содержать contractor_name/inn
    # РЕАЛЬНОГО контрагента, хотя в БД текстовые колонки NULL.
    assert out_item["contractor_name"] == contractor.name
    assert out_item["contractor_inn"] == contractor.inn

    db_item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().first()
    assert db_item.contractor_id == contractor.id
    assert db_item.contractor_inn is None
    assert db_item.contractor_name is None
