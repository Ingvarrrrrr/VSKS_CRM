"""Владелец (2026-09-16): «В заявку импортировал лист из экселя — для позиций,
которые есть в БД, должны подтягиваться картинки».

До этой правки POST /api/purchases/items/import-mapped-nopid и
/items/import-smart-nopid (используются при импорте позиций В ЗАЯВКУ — нет
purchase_id ещё) возвращали распарсенные строки БЕЗ какого-либо сопоставления
с каталогом: product_id всегда None, photo_url отсутствовал вовсе — фронт не
мог подставить картинку/описание, даже если товар с точно таким именем уже
есть в каталоге (в отличие от импорта В закупку, где это сопоставление уже
было).

Фикс: обе nopid-ветки теперь делают ТОЧНОЕ (не fuzzy) сопоставление по
нормализованному имени через find_products_by_normalized_names
(app/services/product_catalog_match.py — единая точка входа, Правило №6,
никакого второго матчера) и отдают по строке product_id/photo_url/description/
unit НАЙДЕННОГО товара. Каталог при этом НЕ меняется — заявка ещё может быть
не одобрена (то же правило, что владелец сформулировал 2026-09-04).

Гоняется по одному узлу (см. project_pytest_asyncio_loop_flake в памяти
проекта). Тестовые данные — внутри db_session/client outer-transaction
(conftest.py), откатываются автоматически.
"""
from decimal import Decimal
from io import BytesIO

import pytest
from sqlalchemy import select

from app.models.product import Product

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

_UNIQ = "ТестWishImportPhoto20260916"


def _xlsx(rows: list[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Наименование", "Количество", "Цена за ед.", "Ед. изм."])
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_mapped_nopid_fills_product_id_and_photo_for_catalog_item(client, auth_headers, db_session):
    if Workbook is None:
        pytest.skip("openpyxl не установлен")

    catalog_name = f"{_UNIQ} Бензорез Champion 3.5 кВт"
    p = Product(
        name=catalog_name, category="Прочее", price=Decimal("15000"),
        description="Штатное описание из ТЗ", unit="шт", photo_url="https://example.com/photo.jpg",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    other_name = f"{_UNIQ} Товар не из каталога"
    xlsx = _xlsx([(catalog_name, 2, 15000, "шт"), (other_name, 1, 500, "шт")])

    resp = await client.post(
        "/api/purchases/items/import-mapped-nopid",
        headers=auth_headers,
        files={"file": ("wish_items.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params={
            "col_item_name": 0, "col_quantity": 1, "col_unit_price": 2, "col_unit": 3,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = {it["item_name"]: it for it in data["items"]}

    matched = items[catalog_name]
    assert matched["product_id"] == p.id
    assert matched["photo_url"] == "https://example.com/photo.jpg"
    assert matched["description"] == "Штатное описание из ТЗ"

    unmatched = items[other_name]
    assert unmatched["product_id"] is None
    assert unmatched["photo_url"] is None

    # Каталог не пополнился новым товаром для несматченной строки (владелец,
    # 2026-09-04: «на этапе заявки вносить в БД не нужно»).
    rows = (await db_session.execute(
        select(Product).where(Product.name == other_name)
    )).scalars().all()
    assert rows == [], "nopid-импорт не должен писать в каталог"


@pytest.mark.asyncio
async def test_smart_nopid_fills_product_id_and_photo_for_catalog_item(client, auth_headers, db_session):
    if Workbook is None:
        pytest.skip("openpyxl не установлен")

    catalog_name = f"{_UNIQ} Коммутатор D-Link DGS-1024D"
    p = Product(
        name=catalog_name, category="Прочее", price=Decimal("12000"),
        description="Сетевой коммутатор 24 порта", unit="шт",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    other_name = f"{_UNIQ} Стол офисный не из каталога"
    xlsx = _xlsx([(catalog_name, 1, 12000, "шт"), (other_name, 1, 15000, "шт")])

    resp = await client.post(
        "/api/purchases/items/import-smart-nopid",
        headers=auth_headers,
        files={"file": ("wish_items_smart.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    preview = {row["item_name"]: row for row in data["preview"]}

    matched = preview[catalog_name]
    assert matched["product_id"] == p.id
    # У товара нет ни photo_url, ни фото в bytea — эффективный URL пуст, но
    # описание/ед.изм. из каталога должны быть подтянуты.
    assert matched["photo_url"] is None
    assert matched["description"] == "Сетевой коммутатор 24 порта"
    assert matched["unit"] == "шт"

    unmatched = preview[other_name]
    assert unmatched["product_id"] is None
    assert unmatched["photo_url"] is None

    rows = (await db_session.execute(
        select(Product).where(Product.name == other_name)
    )).scalars().all()
    assert rows == [], "nopid-импорт не должен писать в каталог"
