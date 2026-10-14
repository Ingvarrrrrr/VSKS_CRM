"""Баг владельца «категория закупки не сохраняется» (товар 5461): PUT сохранял
purchase_categories, но GET отдавал purchase_category_ids=[] — поле было
унаследовано от ProductCreate с дефолтом [] и не пересчитывалось из
relationship (backend/app/schemas/products.py). Фронт (useProductsForm.openEdit)
брал purchase_category_ids ?? ... — [] не None, поэтому форма открывалась с
пустыми категориями и следующее «Сохранить» стирало их.

Фикс: ProductOut._sync_purchase_category_ids (model_validator mode='after')
всегда пересчитывает purchase_category_ids из purchase_categories — один
источник истины (ПРАВИЛО №6)."""
import pytest


@pytest.mark.asyncio
async def test_product_put_then_get_purchase_category_ids_match(client, superadmin_headers):
    r1 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers, json={"name": "Категория A (ids test)"},
    )
    r2 = await client.post(
        "/api/purchase-categories", headers=superadmin_headers, json={"name": "Категория B (ids test)"},
    )
    cat_a, cat_b = r1.json()["id"], r2.json()["id"]

    r_prod = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={"name": "Товар purchase_category_ids (тест)", "category": "Прочее", "purchase_category_ids": []},
    )
    assert r_prod.status_code == 200, r_prod.text
    prod_id = r_prod.json()["id"]
    assert r_prod.json()["purchase_category_ids"] == []

    r_put = await client.put(
        f"/api/products/{prod_id}", headers=superadmin_headers,
        json={"name": "Товар purchase_category_ids (тест)", "category": "Прочее", "purchase_category_ids": [cat_a, cat_b]},
    )
    assert r_put.status_code == 200, r_put.text
    put_body = r_put.json()
    assert sorted(put_body["purchase_category_ids"]) == sorted([cat_a, cat_b])
    assert sorted(put_body["purchase_category_ids"]) == sorted(c["id"] for c in put_body["purchase_categories"])

    r_get = await client.get(f"/api/products/{prod_id}", headers=superadmin_headers)
    assert r_get.status_code == 200
    get_body = r_get.json()
    # Главная проверка бага: GET после PUT должен отдавать те же id, что сохранены.
    assert sorted(get_body["purchase_category_ids"]) == sorted([cat_a, cat_b])
    assert sorted(get_body["purchase_category_ids"]) == sorted(c["id"] for c in get_body["purchase_categories"])

    r_list = await client.get("/api/products/", headers=superadmin_headers, params={"search": "purchase_category_ids (тест)"})
    assert r_list.status_code == 200
    listed = next(p for p in r_list.json() if p["id"] == prod_id)
    assert sorted(listed["purchase_category_ids"]) == sorted([cat_a, cat_b])
