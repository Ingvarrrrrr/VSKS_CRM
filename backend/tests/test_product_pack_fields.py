"""Упаковка товара (владелец, 14.10: «когда товар меряется упаковками, должно
быть количество в упаковке») — pack_quantity/pack_unit на Product (см.
backend/app/routers/products.py, backend/app/services/units.py)."""
import pytest


@pytest.mark.asyncio
async def test_create_and_get_pack_fields(client, superadmin_headers):
    r = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={
            "name": "Бумага А4 для теста упаковки",
            "unit": "упак.",
            "pack_quantity": 10,
            "pack_unit": "шт.",
        },
    )
    assert r.status_code == 200, r.text
    prod = r.json()
    assert prod["unit"] == "упак."
    assert float(prod["pack_quantity"]) == 10.0
    assert prod["pack_unit"] == "шт."

    r_get = await client.get(f"/api/products/{prod['id']}", headers=superadmin_headers)
    assert r_get.status_code == 200
    got = r_get.json()
    assert float(got["pack_quantity"]) == 10.0
    assert got["pack_unit"] == "шт."


@pytest.mark.asyncio
async def test_partial_put_does_not_erase_pack_fields(client, superadmin_headers):
    r_create = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={
            "name": "Перчатки для теста частичного PUT",
            "unit": "упак.",
            "pack_quantity": 5,
            "pack_unit": "пара",
        },
    )
    prod = r_create.json()

    # PUT без упоминания unit/pack_* (exclude_unset) — не должен стирать упаковку.
    r_put = await client.put(
        f"/api/products/{prod['id']}", headers=superadmin_headers,
        json={"name": "Перчатки для теста частичного PUT", "description": "обновили только описание"},
    )
    assert r_put.status_code == 200, r_put.text
    updated = r_put.json()
    assert float(updated["pack_quantity"]) == 5.0
    assert updated["pack_unit"] == "пара"


@pytest.mark.asyncio
async def test_put_unit_to_non_pack_clears_pack_fields(client, superadmin_headers):
    r_create = await client.post(
        "/api/products/", headers=superadmin_headers,
        json={
            "name": "Карандаш для теста очистки упаковки",
            "unit": "упак.",
            "pack_quantity": 12,
            "pack_unit": "шт.",
        },
    )
    prod = r_create.json()

    r_put = await client.put(
        f"/api/products/{prod['id']}", headers=superadmin_headers,
        json={"name": "Карандаш для теста очистки упаковки", "unit": "шт."},
    )
    assert r_put.status_code == 200, r_put.text
    updated = r_put.json()
    assert updated["unit"] == "шт."
    assert updated["pack_quantity"] is None
    assert updated["pack_unit"] is None
