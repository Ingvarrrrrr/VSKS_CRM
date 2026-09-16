"""Тесты PATCH /api/purchases/{pid}/items/{item_id}/split-column
(app/routers/purchase_split_columns.py).

Владелец (2026-09-16, прод): «перекидывал позиции по колонкам в канбане
разбиения закупки («Разбить закупку на несколько»), случайно вышел из окна —
всё слетело». Черновая раскладка теперь сохраняется per-позиция сразу
(purchase_items.split_column_key), а не только в памяти компонента —
проверяем, что PATCH пишет и читает это поле, гейтится статусом закупки и не
затрагивает соседние позиции/закупки.
"""
import pytest
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


async def _seed_purchase_with_items(db_session, n=2, status="plan_schedule"):
    p = Purchase(item_name="Тестовая закупка split-column", status=status)
    db_session.add(p)
    await db_session.flush()
    items = []
    for i in range(n):
        it = PurchaseItem(
            purchase_id=p.id, item_name=f"Позиция {i}",
            quantity=1, unit="шт", unit_price=100, total_price=100,
        )
        db_session.add(it)
        items.append(it)
    await db_session.commit()
    await db_session.refresh(p)
    for it in items:
        await db_session.refresh(it)
    return p, items


@pytest.mark.asyncio
async def test_patch_sets_and_clears_split_column_key(client, db_session, admin_headers):
    p, items = await _seed_purchase_with_items(db_session)
    item = items[0]

    resp = await client.patch(
        f"/api/purchases/{p.id}/items/{item.id}/split-column",
        json={"split_column_key": "Моя колонка"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["split_column_key"] == "Моя колонка"

    get_resp = await client.get(f"/api/purchases/{p.id}", headers=admin_headers)
    assert get_resp.status_code == 200
    got_items = {it["id"]: it for it in get_resp.json()["items"]}
    assert got_items[item.id]["split_column_key"] == "Моя колонка"
    # Соседняя позиция не затронута.
    assert got_items[items[1].id]["split_column_key"] is None

    # Сброс к None (перетащили обратно в "естественную" колонку).
    resp2 = await client.patch(
        f"/api/purchases/{p.id}/items/{item.id}/split-column",
        json={"split_column_key": None},
        headers=admin_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["split_column_key"] is None


@pytest.mark.asyncio
async def test_patch_404_for_item_of_another_purchase(client, db_session, admin_headers):
    p1, items1 = await _seed_purchase_with_items(db_session, n=1)
    p2, _items2 = await _seed_purchase_with_items(db_session, n=1)

    resp = await client.patch(
        f"/api/purchases/{p2.id}/items/{items1[0].id}/split-column",
        json={"split_column_key": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_409_when_purchase_already_split(client, db_session, admin_headers):
    p, items = await _seed_purchase_with_items(db_session, status="split")

    resp = await client.patch(
        f"/api/purchases/{p.id}/items/{items[0].id}/split-column",
        json={"split_column_key": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_split_purchase_still_works_and_drops_split_column_key(client, db_session, admin_headers):
    """Регресс: split-column — черновик, использованный ТОЛЬКО на клиенте до
    вызова POST /split (payload сам несёт финальную раскладку групп) — эндпоинт
    разбиения не читает split_column_key вовсе, поведение POST /split не
    изменилось. Строки исходной закупки удаляются целиком (см.
    purchase_ops.py::split_purchase), так что split_column_key естественным
    образом не переживает разбиение — второй очистки не требуется."""
    p, items = await _seed_purchase_with_items(db_session, n=2)
    await client.patch(
        f"/api/purchases/{p.id}/items/{items[0].id}/split-column",
        json={"split_column_key": "Группа А"},
        headers=admin_headers,
    )

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "Группа А", "item_ids": [items[0].id]},
            {"column_key": "Группа Б", "item_ids": [items[1].id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 2

    await db_session.refresh(p)
    assert p.status == "split"
