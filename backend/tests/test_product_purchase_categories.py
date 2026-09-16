"""Владелец, 2026-09-16, п.B: у товара ДВЕ категории — «категория товара»
(products.category, как раньше) и «категории закупки» (несколько, из
purchase_categories). Пример владельца: краги пожарного — категория товара
«СИЗ», категории закупки «Пожарное оборудование» и «СИЗ»."""
import pytest


@pytest.mark.asyncio
async def test_product_create_with_two_purchase_categories(client, superadmin_headers):
    r1 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers,
        json={"name": "Пожарное оборудование (тест)"},
    )
    r2 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers,
        json={"name": "СИЗ (тест)"},
    )
    cat1, cat2 = r1.json()["id"], r2.json()["id"]

    r_prod = await client.post(
        "/api/products/",
        headers=superadmin_headers,
        json={
            "name": "Краги пожарного (тест)",
            "category": "СИЗ",  # категория ТОВАРА — отдельно
            "purchase_category_ids": [cat1, cat2],
        },
    )
    assert r_prod.status_code == 200, r_prod.text
    body = r_prod.json()
    assert body["category"] == "СИЗ"
    got_names = sorted(c["name"] for c in body["purchase_categories"])
    assert got_names == sorted(["Пожарное оборудование (тест)", "СИЗ (тест)"])

    # GET /{id} и GET / (список) отдают ту же связь.
    r_get = await client.get(f"/api/products/{body['id']}", headers=superadmin_headers)
    assert sorted(c["name"] for c in r_get.json()["purchase_categories"]) == sorted(got_names)

    r_list = await client.get("/api/products/", headers=superadmin_headers)
    listed = next(p for p in r_list.json() if p["id"] == body["id"])
    assert sorted(c["name"] for c in listed["purchase_categories"]) == sorted(got_names)


@pytest.mark.asyncio
async def test_product_update_replaces_purchase_categories(client, superadmin_headers):
    r1 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers, json={"name": "Категория Раз"},
    )
    r2 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers, json={"name": "Категория Два"},
    )
    cat1, cat2 = r1.json()["id"], r2.json()["id"]

    r_prod = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={"name": "Товар для замены категорий", "category": "Прочее", "purchase_category_ids": [cat1]},
    )
    prod_id = r_prod.json()["id"]
    assert [c["id"] for c in r_prod.json()["purchase_categories"]] == [cat1]

    r_upd = await client.put(
        f"/api/products/{prod_id}", headers=superadmin_headers,
        json={"name": "Товар для замены категорий", "category": "Прочее", "purchase_category_ids": [cat2]},
    )
    assert r_upd.status_code == 200
    assert [c["id"] for c in r_upd.json()["purchase_categories"]] == [cat2]
