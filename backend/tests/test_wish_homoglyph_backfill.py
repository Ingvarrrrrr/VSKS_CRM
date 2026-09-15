"""Бэкфилл product_id у позиций заявки при конверсии в закупку — тот же
дефект FISKARS X17/Х17, но на пути «заявка → закупка», которым владелец
реально пользуется (владелец, дословно: «скопировал позиции из файла в
заявку, согласовал, и теперь всё в закупке»).

ПРИЧИНА (найдено 2026-09-16 при доработке product_catalog_match.py):
app/services/wish_distribution.py и app/routers/wish_convert.py сужали
кандидатов на бэкфилл через `Product.name.in_(names)` — сравнение БАЙТ
СЫРОГО имени ДО normalize_product_name. Товар с гомоглифом/ё/лишним
пробелом в имя не искал себя по нормализованному ключу, а искал БУКВАЛЬНО
себя же среди `names` — заведомо мимо, поэтому гомоглиф-фикс в
product_catalog_match.py на этом пути не работал вовсе, хотя работал на
импорте позиций закупки. Заменено на find_products_by_normalized_names
(app/services/product_catalog_match.py) — та же SQL-нормализация через
Postgres translate(), что и find_exact_product (Правило №6, единая точка).

Гоняется ПО ОДНОМУ УЗЛУ за вызов pytest (флейк pytest-asyncio «different
loop», см. project_pytest_asyncio_loop_flake).
"""
import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory


@pytest.mark.asyncio
async def test_approve_distribution_links_cyrillic_letter_item_to_latin_catalog_product(
    client, db_session, admin_headers, test_org, test_user,
):
    """Сценарий владельца целиком: заявка с позицией, набранной кириллическими
    Х/М (визуальный двойник латинских X/M из каталога), после
    /approve-distribution (wish_distribution.py::_distribute_wish_to_purchases)
    ДОЛЖНА привязаться к уже существующему товару с ТЗ — а не остаться
    сиротой без product_id."""
    subsidy = Subsidy(name=f"TestSubsidyHomoglyph-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    latin_name = f"ТестГомоглифКонверсии-{id(db_session)} Топор FISKARS X17 M"
    cyrillic_name = f"ТестГомоглифКонверсии-{id(db_session)} Топор FISKARS Х17 М"
    product = Product(
        name=latin_name, category="Прочее", description="Полное ТЗ топора",
        photo_url="https://example.test/axe.jpg", org_id=test_org.id,
    )
    db_session.add(product)
    await db_session.flush()

    wish = Wish(
        org_id=test_org.id,
        title="Заявка на топор (кириллица в названии позиции)",
        status="submitted",
        created_by=test_user.id,
        subsidy_id=subsidy.id,
        feo_category_id=feo_cat.id,
    )
    db_session.add(wish)
    await db_session.flush()

    db_session.add(WishItem(
        wish_id=wish.id, item_name=cyrillic_name,  # product_id НЕ задан — легаси-путь
        quantity=1, unit_price=1000, total_price=1000,
    ))
    await db_session.commit()

    resp = await client.post(f"/api/wishes/{wish.id}/approve-distribution", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["purchase_ids"]) >= 1

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_(body["purchase_ids"]))
    )).scalars().all()
    assert len(items) == 1
    item = items[0]
    assert item.product_id == product.id, (
        "позиция с кириллическими буквами должна была привязаться к "
        "существующему товару (латинские буквы), а не остаться сиротой"
    )
