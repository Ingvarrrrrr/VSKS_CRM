"""Защита общего каталога товаров (Этап В, план item-tz-description.md,
владелец 14.10.2026): правка описания СУЩЕСТВУЮЩЕГО товара — только с
правом products.edit_catalog; без права — предложение (pending), принятое
применяется и пишет историю; создание НОВОГО товара не блокируется."""
import pytest
from sqlalchemy import select

from app.models.permission import RolePermission
from app.models.product import Product
from app.models.product_description_history import ProductDescriptionHistory
from app.models.product_description_proposal import ProductDescriptionProposal


async def _set_role_permission(db_session, role: str, key: str, granted: bool) -> None:
    """Upsert RolePermission — используется ВМЕСТО фикстуры make_role_permission
    (та делает чистый INSERT и падает на уникальном (role_name, key), а сид
    app.startup.permission_seeds.py::_products_edit_catalog_action уже вставил
    строки для products.edit_catalog на реальной БД при старте контейнера)."""
    row = (await db_session.execute(
        select(RolePermission).where(RolePermission.role_name == role, RolePermission.key == key)
    )).scalar_one_or_none()
    if row is None:
        db_session.add(RolePermission(role_name=role, key=key, granted=granted))
    else:
        row.granted = granted
    await db_session.commit()


async def _create_product(client, headers, name="Товар для теста защиты каталога", description="Старое описание"):
    r = await client.post(
        "/api/products/", headers=headers,
        json={"name": name, "category": "Прочее", "description": description},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_edit_description(client, auth_headers):
    product = await _create_product(client, auth_headers)

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Новое описание от сотрудника"},
    )
    assert r.status_code == 403, r.text
    # Глобальный форматтер ошибок оборачивает detail в {"message": ...} (см.
    # correlation_id/code в теле ответа — не второй формат, тот же везде).
    assert "Редактировать каталог товаров" in r.json()["message"]

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Старое описание"


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_delete_or_patch(client, auth_headers):
    product = await _create_product(client, auth_headers)

    r_patch = await client.patch(
        f"/api/products/{product['id']}", headers=auth_headers, json={"category": "Другая"},
    )
    assert r_patch.status_code == 403, r_patch.text

    r_delete = await client.delete(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_delete.status_code == 403, r_delete.text


@pytest.mark.asyncio
async def test_employee_creating_new_product_not_blocked(client, auth_headers):
    """Создание НОВОГО товара (POST) не требует products.edit_catalog —
    решение владельца, см. докстринг app/services/product_catalog_guard.py."""
    r = await client.post(
        "/api/products/", headers=auth_headers,
        json={"name": "Новый товар от сотрудника без галочки", "category": "Прочее", "description": "ТЗ из файла"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "ТЗ из файла"


@pytest.mark.asyncio
async def test_employee_with_permission_can_edit_and_history_recorded(
    client, db_session, auth_headers, test_user,
):
    await _set_role_permission(db_session, "employee", "products.edit_catalog", True)
    product = await _create_product(client, auth_headers)

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Правка с галочкой"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Правка с галочкой"

    history = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product["id"])
    )).scalars().all()
    assert len(history) == 1
    assert history[0].field == "description"
    assert history[0].old_value == "Старое описание"
    assert history[0].new_value == "Правка с галочкой"
    assert history[0].source == "edit"
    assert history[0].user_id == test_user.id


@pytest.mark.asyncio
async def test_revert_history_requires_permission_and_restores_value(
    client, db_session, auth_headers,
):
    await _set_role_permission(db_session, "employee", "products.edit_catalog", True)
    product = await _create_product(client, auth_headers)

    r_edit = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Новая версия"},
    )
    assert r_edit.status_code == 200, r_edit.text

    r_hist = await client.get(f"/api/products/{product['id']}/description-history", headers=auth_headers)
    assert r_hist.status_code == 200, r_hist.text
    history_id = r_hist.json()[0]["id"]

    r_revert = await client.post(
        f"/api/products/{product['id']}/description-history/{history_id}/revert",
        headers=auth_headers,
    )
    assert r_revert.status_code == 200, r_revert.text
    assert r_revert.json()["source"] == "revert"
    assert r_revert.json()["new_value"] == "Старое описание"

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Старое описание"


@pytest.mark.asyncio
async def test_proposal_pending_then_accepted_applies_change(
    client, db_session, auth_headers, test_user, make_user,
):
    """Сотрудник без галочки предлагает правку — pending, описание не
    меняется. Сотрудник с галочкой принимает — применяется + история."""
    product = await _create_product(client, auth_headers)

    r_propose = await client.post(
        f"/api/products/{product['id']}/description-proposals", headers=auth_headers,
        json={"field": "description", "proposed_value": "Предложение от сотрудника"},
    )
    assert r_propose.status_code == 200, r_propose.text
    body = r_propose.json()
    assert body["status"] == "pending"
    proposal_id = body["id"]

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Старое описание"

    approver = await make_user(role="org_admin")
    await _set_role_permission(db_session, "org_admin", "products.edit_catalog", True)
    from app.auth.jwt import create_access_token
    approver_headers = {"Authorization": f"Bearer {create_access_token({'sub': approver.username, 'org_id': approver.org_id})}"}

    r_list = await client.get("/api/products/description-proposals?status=pending", headers=approver_headers)
    assert r_list.status_code == 200, r_list.text
    assert any(p["id"] == proposal_id for p in r_list.json())

    r_accept = await client.post(
        f"/api/products/description-proposals/{proposal_id}/accept", headers=approver_headers,
    )
    assert r_accept.status_code == 200, r_accept.text
    accepted = r_accept.json()
    assert accepted["proposal"]["status"] == "accepted"
    assert accepted["changed_since_proposal"] is False

    r_get2 = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get2.json()["description"] == "Предложение от сотрудника"

    history = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product["id"])
    )).scalars().all()
    assert len(history) == 1
    assert history[0].source == "proposal"
    assert history[0].proposal_id == proposal_id


@pytest.mark.asyncio
async def test_proposal_reject_does_not_change_description(
    client, db_session, auth_headers, make_user,
):
    product = await _create_product(client, auth_headers)
    r_propose = await client.post(
        f"/api/products/{product['id']}/description-proposals", headers=auth_headers,
        json={"field": "description", "proposed_value": "Предложение, которое отклонят"},
    )
    proposal_id = r_propose.json()["id"]

    approver = await make_user(role="org_admin")
    await _set_role_permission(db_session, "org_admin", "products.edit_catalog", True)
    from app.auth.jwt import create_access_token
    approver_headers = {"Authorization": f"Bearer {create_access_token({'sub': approver.username, 'org_id': approver.org_id})}"}

    r_reject = await client.post(
        f"/api/products/description-proposals/{proposal_id}/reject", headers=approver_headers,
        json={"comment": "Не подходит"},
    )
    assert r_reject.status_code == 200, r_reject.text
    assert r_reject.json()["status"] == "rejected"

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Старое описание"


@pytest.mark.asyncio
async def test_dedup_without_permission_forbidden(client, auth_headers):
    """POST /api/products/deduplicate (слияние/удаление дублей каталога) —
    та же защита products.edit_catalog, что у PUT/PATCH/DELETE товара
    (Правило №6, app/services/product_catalog_guard.py). Без права — 403,
    даже на dry_run=true (сама операция решает судьбу чужих карточек)."""
    r = await client.post("/api/products/deduplicate", headers=auth_headers, params={"dry_run": "true"})
    assert r.status_code == 403, r.text
    assert "Редактировать каталог товаров" in r.json()["message"]


@pytest.mark.asyncio
async def test_dedup_with_permission_allowed(client, db_session, auth_headers):
    await _set_role_permission(db_session, "employee", "products.edit_catalog", True)
    r = await client.post("/api/products/deduplicate", headers=auth_headers, params={"dry_run": "true"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_proposal_from_user_with_permission_applies_immediately(
    client, db_session, make_user,
):
    """Владелец 14.10.2026: «с галочкой — сразу применяется, тоже с историей»."""
    from app.auth.jwt import create_access_token
    editor = await make_user(role="org_admin")
    await _set_role_permission(db_session, "org_admin", "products.edit_catalog", True)
    editor_headers = {"Authorization": f"Bearer {create_access_token({'sub': editor.username, 'org_id': editor.org_id})}"}

    product = await _create_product(client, editor_headers)
    r_propose = await client.post(
        f"/api/products/{product['id']}/description-proposals", headers=editor_headers,
        json={"field": "description", "proposed_value": "Правка сразу применена"},
    )
    assert r_propose.status_code == 200, r_propose.text
    assert r_propose.json()["status"] == "accepted"

    r_get = await client.get(f"/api/products/{product['id']}", headers=editor_headers)
    assert r_get.json()["description"] == "Правка сразу применена"

    proposal_id = r_propose.json()["id"]
    proposal = await db_session.get(ProductDescriptionProposal, proposal_id)
    assert proposal.status == "accepted"


# --- Часть 1 плана clever-bouncing-lantern.md (владелец 14.10.2026): -------
# «без галочки — заполнить ПУСТОЕ поле можно, заменить заполненное — нет».


async def _create_empty_product(client, headers, name="Товар без ТЗ/цены/фото"):
    r = await client.post(
        "/api/products/", headers=headers,
        json={"name": name, "category": "Прочее"},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_employee_without_permission_fills_empty_description_recorded_as_fill_empty(
    client, db_session, auth_headers, test_user,
):
    product = await _create_empty_product(client, auth_headers)
    assert product["description"] is None

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "ТЗ от сотрудника без галочки"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "ТЗ от сотрудника без галочки"

    history = (await db_session.execute(
        select(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == product["id"])
    )).scalars().all()
    assert len(history) == 1
    assert history[0].source == "fill_empty"
    assert history[0].user_id == test_user.id


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_overwrite_filled_description_via_put(
    client, auth_headers,
):
    product = await _create_product(client, auth_headers, description="Уже заполненное ТЗ")
    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Попытка заменить"},
    )
    assert r.status_code == 403, r.text
    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Уже заполненное ТЗ"


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_erase_filled_description(client, auth_headers):
    product = await _create_product(client, auth_headers, description="Уже заполненное ТЗ")
    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": ""},
    )
    assert r.status_code == 403, r.text
    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert r_get.json()["description"] == "Уже заполненное ТЗ"


@pytest.mark.asyncio
async def test_employee_without_permission_sets_price_when_product_has_none(client, auth_headers):
    product = await _create_empty_product(client, auth_headers)
    assert product["price"] is None

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "price": 150},
    )
    assert r.status_code == 200, r.text
    assert float(r.json()["price"]) == 150.0


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_change_price_when_product_has_one(client, auth_headers):
    product = await _create_empty_product(client, auth_headers)
    r_set = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "price": 150},
    )
    assert r_set.status_code == 200, r_set.text

    r = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "price": 200},
    )
    assert r.status_code == 403, r.text
    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert float(r_get.json()["price"]) == 150.0


@pytest.mark.asyncio
async def test_put_resending_unchanged_description_and_price_not_blocked(client, auth_headers):
    """PUT шлёт форму целиком (не exclude_unset на фронте) — повторная
    отправка ТЕХ ЖЕ значений description/price не должна считаться правкой
    и блокироваться (защита каталога реагирует только на РЕАЛЬНОЕ
    изменение, см. _real_changes в update_product)."""
    product = await _create_product(client, auth_headers, description="Старое описание")
    r_set_price = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Старое описание", "price": 150},
    )
    # Цена у товара ещё не была заполнена — заполнение пустого разрешено,
    # описание прислано тем же значением — не изменение.
    assert r_set_price.status_code == 200, r_set_price.text

    r_resend = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "description": "Старое описание", "price": 150},
    )
    assert r_resend.status_code == 200, r_resend.text


@pytest.mark.asyncio
async def test_employee_without_permission_uploads_photo_when_none(client, auth_headers):
    product = await _create_empty_product(client, auth_headers)
    r = await client.post(
        f"/api/products/{product['id']}/photo", headers=auth_headers,
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_photo"] is True


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_replace_existing_photo(client, auth_headers):
    product = await _create_empty_product(client, auth_headers)
    r1 = await client.post(
        f"/api/products/{product['id']}/photo", headers=auth_headers,
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/api/products/{product['id']}/photo", headers=auth_headers,
        files={"file": ("photo2.png", b"\x89PNG\r\n\x1a\n" + b"1" * 32, "image/png")},
    )
    assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_employee_without_permission_cannot_delete_photo(client, auth_headers):
    product = await _create_empty_product(client, auth_headers)
    r1 = await client.post(
        f"/api/products/{product['id']}/photo", headers=auth_headers,
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.delete(f"/api/products/{product['id']}/photo", headers=auth_headers)
    assert r2.status_code == 403, r2.text


# --- Часть 1 плана clever-bouncing-lantern.md, п.2 (15.10): POST ----------
# /{id}/price-history без галочки — только история, Product.price не трогаем,
# если у товара цена уже есть (routers/products_price.py::add_manual_price_history).


@pytest.mark.asyncio
async def test_price_history_without_permission_fills_empty_price(client, auth_headers):
    """У товара цены нет — запись «КП»/«мониторинг»/«вручную» без галочки
    заполняет Product.price (это заполнение пустого, как и PUT)."""
    product = await _create_empty_product(client, auth_headers)
    assert product["price"] is None

    r = await client.post(
        f"/api/products/{product['id']}/price-history", headers=auth_headers,
        json={"price": 150, "source": "kp"},
    )
    assert r.status_code == 200, r.text

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert float(r_get.json()["price"]) == 150.0


@pytest.mark.asyncio
async def test_price_history_without_permission_does_not_overwrite_existing_price(client, auth_headers):
    """У товара цена УЖЕ есть — без галочки «Редактировать каталог товаров»
    запись уходит только в историю (учитывается в средней), Product.price
    остаётся прежним. Раньше этот эндпоинт обходил защиту каталога и
    переставлял цену кому угодно."""
    product = await _create_empty_product(client, auth_headers)
    r_set = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "price": 150},
    )
    assert r_set.status_code == 200, r_set.text

    r = await client.post(
        f"/api/products/{product['id']}/price-history", headers=auth_headers,
        json={"price": 999, "source": "monitoring"},
    )
    assert r.status_code == 200, r.text
    assert float(r.json()["price"]) == 999.0  # точка истории — своя цена

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert float(r_get.json()["price"]) == 150.0  # Product.price не сдвинулся

    r_hist = await client.get(f"/api/products/{product['id']}/price-history", headers=auth_headers)
    assert r_hist.status_code == 200, r_hist.text
    assert any(row["price"] == "999.00" or float(row["price"]) == 999.0 for row in r_hist.json())


@pytest.mark.asyncio
async def test_price_history_with_permission_overwrites_existing_price(
    client, db_session, auth_headers,
):
    """С галочкой «Редактировать каталог товаров» поведение не меняется —
    запись «КП»/«мониторинг»/«вручную» продолжает переставлять Product.price,
    как и раньше."""
    await _set_role_permission(db_session, "employee", "products.edit_catalog", True)
    product = await _create_empty_product(client, auth_headers)
    r_set = await client.put(
        f"/api/products/{product['id']}", headers=auth_headers,
        json={"name": product["name"], "category": "Прочее", "price": 150},
    )
    assert r_set.status_code == 200, r_set.text

    r = await client.post(
        f"/api/products/{product['id']}/price-history", headers=auth_headers,
        json={"price": 999, "source": "monitoring"},
    )
    assert r.status_code == 200, r.text

    r_get = await client.get(f"/api/products/{product['id']}", headers=auth_headers)
    assert float(r_get.json()["price"]) == 999.0
