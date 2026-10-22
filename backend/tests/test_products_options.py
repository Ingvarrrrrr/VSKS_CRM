"""GET /api/products/options — подсказки категории/типа по всему каталогу
(баг владельца 22.10.2026: ProductEditorDialog.vue строил подсказки из ≤20
товаров, найденных поиском по названию РЕДАКТИРУЕМОГО товара — обычно там
только сам товар). Проверяем: уникальные непустые отсортированные значения,
и 401 без логина."""
import pytest

from app.models.product import Product


@pytest.mark.asyncio
async def test_product_options_returns_unique_sorted_nonempty(client, db_session, auth_headers):
    db_session.add_all([
        Product(name="Товар 1", category="Мебель", product_type="Стол"),
        Product(name="Товар 2", category="Мебель", product_type="Стул"),  # дубль категории
        Product(name="Товар 3", category="Техника", product_type=None),
        Product(name="Товар 4", category=None, product_type=""),  # пустые/None — не попадают
        Product(name="Товар 5", category="  ", product_type="Стол"),  # пробелы — не попадают
    ])
    await db_session.commit()

    resp = await client.get("/api/products/options", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["categories"] == sorted(set(data["categories"]))
    assert data["types"] == sorted(set(data["types"]))
    assert "Мебель" in data["categories"]
    assert "Техника" in data["categories"]
    assert data["categories"].count("Мебель") == 1
    assert None not in data["categories"] and "" not in data["categories"]
    assert "" not in data["types"]
    assert "Стол" in data["types"]
    assert "Стул" in data["types"]


@pytest.mark.asyncio
async def test_product_options_requires_auth(client):
    resp = await client.get("/api/products/options")
    assert resp.status_code == 401
