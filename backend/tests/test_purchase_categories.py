"""Владелец, 2026-09-16, п.A: справочник категорий закупки — CRUD + запрет
удаления категории, привязанной к товарам (409 с числом товаров)."""
import pytest


@pytest.mark.asyncio
async def test_create_list_update_purchase_category(client, superadmin_headers):
    r = await client.post(
        "/api/purchase-categories",
        headers=superadmin_headers,
        json={"name": "Пожарное оборудование", "sort_order": 5},
    )
    assert r.status_code == 200, r.text
    cat = r.json()
    assert cat["name"] == "Пожарное оборудование"
    assert cat["sort_order"] == 5
    assert cat["is_active"] is True

    r_list = await client.get("/api/purchase-categories", headers=superadmin_headers)
    assert r_list.status_code == 200
    names = [c["name"] for c in r_list.json()]
    assert "Пожарное оборудование" in names

    r_upd = await client.put(
        f"/api/purchase-categories/{cat['id']}",
        headers=superadmin_headers,
        json={"is_active": False},
    )
    assert r_upd.status_code == 200
    assert r_upd.json()["is_active"] is False

    r_list2 = await client.get("/api/purchase-categories?active_only=true", headers=superadmin_headers)
    assert cat["id"] not in [c["id"] for c in r_list2.json()]


@pytest.mark.asyncio
async def test_duplicate_name_rejected(client, superadmin_headers):
    body = {"name": "СИЗ"}
    r1 = await client.post("/api/purchase-categories", headers=superadmin_headers, json=body)
    assert r1.status_code == 200
    r2 = await client.post("/api/purchase-categories", headers=superadmin_headers, json=body)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_delete_blocked_when_used_by_product(client, superadmin_headers):
    r_cat = await client.post(
        "/api/purchase-categories", headers=superadmin_headers, json={"name": "Спецодежда"},
    )
    cat_id = r_cat.json()["id"]

    r_prod = await client.post(
        "/api/products/",
        headers=superadmin_headers,
        json={
            "name": "Краги пожарного", "category": "СИЗ",
            "purchase_category_ids": [cat_id],
        },
    )
    assert r_prod.status_code == 200, r_prod.text

    r_del = await client.delete(f"/api/purchase-categories/{cat_id}", headers=superadmin_headers)
    assert r_del.status_code == 409
    # Глобальный HTTPException-хендлер (app/errors.py) разворачивает dict-detail
    # в {code, message, details, correlation_id} — не {"detail": {...}}.
    assert r_del.json()["details"]["count"] == 1

    # Товар без категорий закупки — категорию теперь можно удалить.
    prod_id = r_prod.json()["id"]
    r_upd = await client.put(
        f"/api/products/{prod_id}",
        headers=superadmin_headers,
        json={"name": "Краги пожарного", "category": "СИЗ", "purchase_category_ids": []},
    )
    assert r_upd.status_code == 200
    assert r_upd.json()["purchase_categories"] == []

    r_del2 = await client.delete(f"/api/purchase-categories/{cat_id}", headers=superadmin_headers)
    assert r_del2.status_code == 200
