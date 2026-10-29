"""Preflight ТЗ перед отправкой закупки на площадку (владелец, 30.10.2026:
«без ТЗ не давать выставлять закупку на площадки или хотя бы уведомлять, что
нет ТЗ, и стрелочки к этим пунктам») — publications.py::publish_purchase,
HTTPException(422, detail={"code": "TZ_MISSING", ...}). Единственный источник
гейта — app/services/tz_items.py::tz_required/items_without_tz (ПРАВИЛО №6),
effective_item_tz (item_tz.py) для формулы «пусто ли ТЗ позиции».

Паттерн теста (client/db_session/auth_headers, Purchase/PurchaseItem прямо в
БД) — по образцу test_purchase_tz.py.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.tz_items import items_without_tz


# ── Юнит-тест хелпера напрямую (без HTTP) — на случай известной проблемы
# изоляции сессий (фикстуры клиента отдают 404 «Закупка не найдена» для
# созданных в db_session объектов на некоторых стендах) формула проверяется
# и без похода через HTTP. ──
def test_items_without_tz_unit():
    item_no_tz = SimpleNamespace(item_name="Огнетушитель ОП-5", tz_description=None, product=None)
    item_with_own_tz = SimpleNamespace(item_name="Стул офисный", tz_description="Стул, металл, ткань", product=None)
    item_blank_name = SimpleNamespace(item_name="   ", tz_description=None, product=None)
    catalog_product = SimpleNamespace(description="Каталожное описание товара", characteristics=None)
    item_catalog_tz = SimpleNamespace(item_name="Шкаф", tz_description=None, product=catalog_product)
    # Услуга — tz_required() говорит «ТЗ нужно для всех товаров» без разбора
    # item_type, поэтому items_without_tz не смотрит на item_type вовсе; эта
    # позиция проверяется ровно как товарная (item_type здесь намеренно не
    # задан — функция вообще не читает этот атрибут).
    item_service_no_tz = SimpleNamespace(item_name="Уборка помещения", tz_description=None, product=None)

    missing = items_without_tz([
        item_no_tz, item_with_own_tz, item_blank_name, item_catalog_tz, item_service_no_tz,
    ])
    assert missing == [item_no_tz, item_service_no_tz]


async def _make_purchase_item_no_tz(db_session, item_name="Огнетушитель ОП-5", **purchase_kwargs) -> Purchase:
    p = Purchase(status="planned", item_type="товар", item_name="Test publish TZ gate", **purchase_kwargs)
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name=item_name, unit="шт",
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["fabrikant", "roseltorg_rb"])
async def test_publish_blocks_without_tz_both_platforms(
    client, db_session, auth_headers, user_org_access, make_override, platform,
):
    # require_action('publication.create') — Depends, выполняется ДО тела
    # роута (см. test_publication_requires_action.py); без override 403
    # раньше, чем мы доходим до гейта ТЗ.
    await make_override(user_org_access.id, "publication.create", True)
    p = await _make_purchase_item_no_tz(db_session)
    resp = await client.post(
        f"/api/publications/purchases/{p.id}",
        json={"platform": platform},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    # Глобальный обработчик HTTPException (app/errors.py::http_exception_handler)
    # поднимает dict-detail на верхний уровень ответа: {"code","message",
    # "details": <наш dict целиком>, "correlation_id"} — НЕ стандартный
    # FastAPI {"detail": ...}. Тот же контракт читает api.ts на фронте
    # (structuredDetail/err.payload).
    body = resp.json()
    assert body.get("code") == "TZ_MISSING", body
    assert "Огнетушитель" in body.get("message", "")
    item_ids = (body.get("details") or {}).get("item_ids")
    assert isinstance(item_ids, list) and item_ids


@pytest.mark.asyncio
async def test_publish_tz_not_required_does_not_block_on_tz(
    client, db_session, auth_headers, user_org_access, make_override,
):
    """tz_not_required=True (решение согласующего по заявке) освобождает от
    гейта ТЗ — закупка может дальше упасть на другой проверке (нет региона/
    адреса доставки у Фабриканта), но НЕ с кодом TZ_MISSING."""
    await make_override(user_org_access.id, "publication.create", True)
    p = await _make_purchase_item_no_tz(db_session, tz_not_required=True)
    resp = await client.post(
        f"/api/publications/purchases/{p.id}",
        json={"platform": "fabrikant"},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") != "TZ_MISSING", resp.text


@pytest.mark.asyncio
async def test_publish_advance_purchase_does_not_block_on_tz(
    client, db_session, auth_headers, user_org_access, make_override,
):
    """Авансовый (purchase_method='advance') — второе историческое освобождение
    в tz_required(), та же проверка, что и для tz_not_required выше."""
    await make_override(user_org_access.id, "publication.create", True)
    p = await _make_purchase_item_no_tz(db_session, purchase_method="advance")
    resp = await client.post(
        f"/api/publications/purchases/{p.id}",
        json={"platform": "roseltorg_rb"},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") != "TZ_MISSING", resp.text


@pytest.mark.asyncio
async def test_publish_item_with_catalog_tz_is_not_missing(
    client, db_session, auth_headers, user_org_access, make_override,
):
    """Позиция без своего tz_description, но привязанная к товару каталога с
    заполненным description, — действующее ТЗ есть (effective_item_tz), гейт
    TZ_MISSING не должен сработать."""
    await make_override(user_org_access.id, "publication.create", True)
    product = Product(name="Огнетушитель каталожный", description="ОП-5, порошковый, 5 кг, с манометром")
    db_session.add(product)
    await db_session.flush()
    p = Purchase(status="planned", item_type="товар", item_name="Test publish catalog TZ")
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Огнетушитель", unit="шт", product_id=product.id,
        quantity=Decimal("1"), unit_price=Decimal("1000"), total_price=Decimal("1000"),
    ))
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.post(
        f"/api/publications/purchases/{p.id}",
        json={"platform": "fabrikant"},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") != "TZ_MISSING", resp.text
