"""Ручное заполнение характеристик карточки товара (владелец, 26.10.2026):
  - разбор текста, вставленного копированием с сайта поставщика
    (POST /api/products/characteristics/parse) — 4 формата;
  - сохранение characteristics через PUT/PATCH товара — та же защита каталога
    (products.edit_catalog), что и у description (app/services/product_catalog_guard.py);
  - сборка техописания из характеристик (POST /api/products/characteristics/describe)
    через ЕДИНСТВЕННЫЙ сборщик build_tech_description (ПРАВИЛО №6)."""
import pytest
from sqlalchemy import select

from app.models.permission import RolePermission


async def _set_role_permission(db_session, role: str, key: str, granted: bool) -> None:
    row = (await db_session.execute(
        select(RolePermission).where(RolePermission.role_name == role, RolePermission.key == key)
    )).scalar_one_or_none()
    if row is None:
        db_session.add(RolePermission(role_name=role, key=key, granted=granted))
    else:
        row.granted = granted
    await db_session.commit()


async def _create_product(client, headers, name="Товар для теста характеристик", characteristics=None):
    payload = {"name": name, "category": "Прочее"}
    if characteristics is not None:
        payload["characteristics"] = characteristics
    r = await client.post("/api/products/", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- parse ----

@pytest.mark.asyncio
async def test_parse_requires_auth(client):
    r = await client.post("/api/products/characteristics/parse", json={"text": "Вес: 1 кг"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_parse_colon_format(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Вес брутто: 2786 г\nЦвет: Красный"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Вес брутто"]["value"] == "2786"
    assert by_name["Вес брутто"]["unit"] == "г"
    assert by_name["Цвет"]["value"] == "Красный"


@pytest.mark.asyncio
async def test_parse_tab_format(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Напряжение\t220 В\nМатериал\tПластик"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Напряжение"]["value"] == "220"
    assert by_name["Напряжение"]["unit"] == "В"
    assert by_name["Материал"]["value"] == "Пластик"


@pytest.mark.asyncio
async def test_parse_dots_separator_format(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Объём ..................... 1.5 л\nВысота .......... 15 см"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Объём"]["value"] == "1.5"
    assert by_name["Объём"]["unit"] == "л"
    assert by_name["Высота"]["value"] == "15"
    assert by_name["Высота"]["unit"] == "см"


@pytest.mark.asyncio
async def test_parse_dash_separator_format(client, auth_headers):
    """27.10.2026, задача «нет данных — заполняются из описания» (товар 3002
    с прода): "Метка - значение" / "Метка — значение" (дефис/тире, с
    пробелами по обе стороны)."""
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Высота огнетушителя  - 440 мм\nЦвет — Красный"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Высота огнетушителя"]["value"] == "440"
    assert by_name["Высота огнетушителя"]["unit"] == "мм"
    assert by_name["Цвет"]["value"] == "Красный"


@pytest.mark.asyncio
async def test_parse_dash_does_not_split_hyphenated_range(client, auth_headers):
    """Дефис БЕЗ пробелов (диапазон "108-112" или слово "литий-ионный") —
    не разделитель метка/значение, строка остаётся нераспознанной."""
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Типоразмер: 108-112 (XL)\nАккумулятор литий-ионный"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Типоразмер"]["value"] == "108-112 (XL)"
    assert "Аккумулятор литий-ионный" not in by_name


@pytest.mark.asyncio
async def test_parse_alternating_lines_format(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "Вес\n3.5 кг\nСтрана\nКитай"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["Вес"]["value"] == "3.5"
    assert by_name["Вес"]["unit"] == "кг"
    assert by_name["Страна"]["value"] == "Китай"


@pytest.mark.asyncio
async def test_parse_text_too_long_400(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "a" * 50_001},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_parse_empty_text_returns_empty_list(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/parse", headers=auth_headers,
        json={"text": "   "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


# -------------------------------------------------------------- describe ---

@pytest.mark.asyncio
async def test_describe_requires_auth(client):
    r = await client.post("/api/products/characteristics/describe", json={"characteristics": []})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_describe_calls_build_tech_description(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/describe", headers=auth_headers,
        json={
            "characteristics": [
                {"name": "Вес", "value": "0.5", "unit": "кг"},
                {"name": "Служебное", "value": "123", "in_description": False},
            ],
            "base_text": "Хороший товар.",
        },
    )
    assert r.status_code == 200, r.text
    text = r.json()["text"]
    assert "Хороший товар." in text
    assert "Вес: 0.5 кг" in text
    assert "Служебное" not in text


@pytest.mark.asyncio
async def test_describe_empty_returns_null(client, auth_headers):
    r = await client.post(
        "/api/products/characteristics/describe", headers=auth_headers,
        json={"characteristics": []},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] is None


# ------------------------------------------------------- save via PUT/PATCH

@pytest.mark.asyncio
async def test_create_product_with_characteristics(client, auth_headers):
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    assert product["characteristics"] == [
        {"name": "Вес", "value": "1", "unit": "кг", "in_description": None},
    ]


@pytest.mark.asyncio
async def test_empty_rows_dropped_on_save(client, auth_headers):
    """Строка с пустым name ИЛИ пустым value отбрасывается целиком."""
    product = await _create_product(
        client, auth_headers,
        characteristics=[
            {"name": "Вес", "value": "1", "unit": "кг"},
            {"name": "", "value": "мусор"},
            {"name": "Без значения", "value": ""},
        ],
    )
    assert len(product["characteristics"]) == 1
    assert product["characteristics"][0]["name"] == "Вес"


@pytest.mark.asyncio
async def test_employee_without_permission_fills_empty_characteristics(client, auth_headers):
    product = await _create_product(client, auth_headers)
    assert not product["characteristics"]

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={
            "name": product["name"], "category": "Прочее",
            "characteristics": [{"name": "Вес", "value": "1", "unit": "кг"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["characteristics"][0]["name"] == "Вес"


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_overwrite_filled_characteristics(client, auth_headers):
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={
            "name": product["name"], "category": "Прочее",
            "characteristics": [{"name": "Вес", "value": "999", "unit": "кг"}],
        },
    )
    assert r.status_code == 403, r.text

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["characteristics"][0]["value"] == "1"


@pytest.mark.asyncio
async def test_employee_with_permission_can_overwrite_characteristics(client, db_session, auth_headers):
    await _set_role_permission(db_session, "employee", "products.edit_catalog", True)
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={
            "name": product["name"], "category": "Прочее",
            "characteristics": [{"name": "Вес", "value": "999", "unit": "кг"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["characteristics"][0]["value"] == "999"


@pytest.mark.asyncio
async def test_put_resending_unchanged_characteristics_not_blocked(client, auth_headers):
    """PUT шлёт форму целиком — повторная отправка ТЕХ ЖЕ характеристик не
    должна считаться правкой и блокироваться (как и description/price)."""
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={
            "name": product["name"], "category": "Прочее",
            "characteristics": [{"name": "Вес", "value": "1", "unit": "кг"}],
        },
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_patch_characteristics_same_guard_as_put(client, auth_headers):
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )

    r = await client.patch(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"characteristics": [{"name": "Вес", "value": "999", "unit": "кг"}]},
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_patch_characteristics_fills_empty(client, auth_headers):
    product = await _create_product(client, auth_headers)

    r = await client.patch(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"characteristics": [{"name": "Вес", "value": "1", "unit": "кг"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["characteristics"][0]["name"] == "Вес"


@pytest.mark.asyncio
async def test_too_many_characteristics_rejected(client, auth_headers):
    too_many = [{"name": f"Поле {i}", "value": str(i)} for i in range(201)]
    r = await client.post(
        "/api/products/", headers=auth_headers,
        json={"name": "Товар с перебором характеристик", "category": "Прочее", "characteristics": too_many},
    )
    assert r.status_code == 400, r.text


# ------------------------------------- QA 26.10.2026: characteristics=None --
# подтверждённая потеря данных (товар 50014): форма шлёт characteristics=null
# ДО того, как _loadCharacteristics отработал — normalize_characteristics(None)
# превращал это в [] и ЗАТИРАЛ уже сохранённые характеристики (админ — молча,
# employee без products.edit_catalog — 403 "на ЛЮБЫЕ поля", потому что
# characteristics_changed(старое непустое, []) считался правкой). Теперь
# characteristics=None/ключ отсутствует = «не трогать» на всех трёх роутах
# (POST/PUT/PATCH, products.py) — явная очистка только через [].

@pytest.mark.asyncio
async def test_put_null_characteristics_does_not_erase_existing(client, superadmin_headers):
    """Админ (bypass guard) — null в characteristics не должен стирать уже
    сохранённые характеристики, остальные поля (name) при этом сохраняются."""
    product = await _create_product(
        client, superadmin_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    r = await client.put(
        f"/api/products/{product['id']}", headers=superadmin_headers,
        json={"name": "Товар переименован", "category": "Прочее", "characteristics": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Товар переименован"
    assert body["characteristics"][0]["name"] == "Вес"
    assert body["characteristics"][0]["value"] == "1"


@pytest.mark.asyncio
async def test_put_null_characteristics_not_blocked_without_permission(client, auth_headers):
    """employee без products.edit_catalog: PUT формой целиком (name/category
    НЕ меняются — только это разрешено без галочки на прочих полях) с
    characteristics=null на товаре с уже непустыми характеристиками — 200, а
    НЕ 403 (баг: null нормализовался в [], считался «стиранием непустого» и
    403-ил весь запрос, хотя пользователь характеристики не трогал)."""
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": product["category"], "price": 1, "characteristics": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["characteristics"][0]["name"] == "Вес"
    assert float(body["price"]) == 1


@pytest.mark.asyncio
async def test_put_explicit_empty_list_clears_characteristics_for_admin(client, superadmin_headers):
    """Явный [] (не null) — это НАМЕРЕННАЯ очистка, она должна сработать."""
    product = await _create_product(
        client, superadmin_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    r = await client.put(
        f"/api/products/{product['id']}", headers=superadmin_headers,
        json={"name": product["name"], "category": "Прочее", "characteristics": []},
    )
    assert r.status_code == 200, r.text
    assert r.json()["characteristics"] == []


@pytest.mark.asyncio
async def test_put_explicit_empty_list_still_blocked_without_permission(client, auth_headers):
    """Явный [] от employee без products.edit_catalog на непустых
    характеристиках — это стирание непустого поля, остаётся 403 (guard не
    ослаблен, ослаблена только интерпретация null)."""
    product = await _create_product(
        client, auth_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "characteristics": []},
    )
    assert r.status_code == 403, r.text
    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["characteristics"][0]["name"] == "Вес"


@pytest.mark.asyncio
async def test_patch_null_characteristics_does_not_erase_existing(client, superadmin_headers):
    """Тот же принцип null="не трогать" и на PATCH (data: dict, не схема)."""
    product = await _create_product(
        client, superadmin_headers,
        characteristics=[{"name": "Вес", "value": "1", "unit": "кг"}],
    )
    r = await client.patch(
        f"/api/products/{product['id']}", headers=superadmin_headers,
        json={"price": 123, "characteristics": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["characteristics"][0]["name"] == "Вес"
