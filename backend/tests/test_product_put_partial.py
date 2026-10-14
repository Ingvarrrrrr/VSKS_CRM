"""PUT /api/products/{id} должен быть частичным (exclude_unset) — владелец,
14.10: урезанные экраны (FullProductDialog и т.п.) шлют не весь набор полей
ProductCreate, а старый update_product делал model_dump() без exclude_unset и
подставлял ДЕФОЛТЫ СХЕМЫ на отсутствующие поля — PUT молча стирал unit,
description_44fz, country_origin, purchase_category_ids и т.д. (см.
backend/app/routers/products.py::update_product). Эти тесты фиксируют новое
поведение: не присланное поле — не трогается; purchase_category_ids трогается
только если ключ прислан явно."""
import pytest


@pytest.mark.asyncio
async def test_put_partial_keeps_unset_fields(client, superadmin_headers):
    r_cat = await client.post(
        "/api/purchase-categories", headers=superadmin_headers,
        json={"name": "Категория для партиал-теста"},
    )
    cat_id = r_cat.json()["id"]

    r_create = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={
            "name": "Товар для партиал-PUT теста",
            "category": "Исходная категория",
            "unit": "шт",
            "country_origin": "Китай",
            "description_44fz": "Описание 44-ФЗ",
            "purchase_category_ids": [cat_id],
        },
    )
    assert r_create.status_code == 200, r_create.text
    prod = r_create.json()
    assert prod["unit"] == "шт"
    assert prod["country_origin"] == "Китай"
    assert prod["description_44fz"] == "Описание 44-ФЗ"
    assert [c["id"] for c in prod["purchase_categories"]] == [cat_id]

    # PUT только {name, category} — остальное НЕ прислано, должно сохраниться.
    r_put = await client.put(
        f"/api/products/{prod['id']}", headers=superadmin_headers,
        json={"name": "Товар для партиал-PUT теста (переименован)", "category": "новая категория"},
    )
    assert r_put.status_code == 200, r_put.text
    updated = r_put.json()
    assert updated["name"] == "Товар для партиал-PUT теста (переименован)"
    # Капитализация первой буквы (app.services.text_case.capitalize_first).
    assert updated["category"] == "Новая категория"
    assert updated["unit"] == "шт"
    assert updated["country_origin"] == "Китай"
    assert updated["description_44fz"] == "Описание 44-ФЗ"
    assert [c["id"] for c in updated["purchase_categories"]] == [cat_id]


@pytest.mark.asyncio
async def test_put_with_empty_purchase_category_ids_clears_them(client, superadmin_headers):
    r_cat = await client.post(
        "/api/purchase-categories", headers=superadmin_headers,
        json={"name": "Категория для очистки"},
    )
    cat_id = r_cat.json()["id"]

    r_create = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={
            "name": "Товар для очистки категорий закупки",
            "category": "Прочее",
            "purchase_category_ids": [cat_id],
        },
    )
    prod = r_create.json()
    assert [c["id"] for c in prod["purchase_categories"]] == [cat_id]

    r_put = await client.put(
        f"/api/products/{prod['id']}", headers=superadmin_headers,
        json={
            "name": "Товар для очистки категорий закупки",
            "category": "Прочее",
            "purchase_category_ids": [],
        },
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["purchase_categories"] == []
