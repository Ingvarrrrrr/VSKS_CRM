"""GET /api/feo-categories/export (backend/app/routers/feo_import_export.py) —
выгрузка теперь включает плановые позиции ФЭО и группировку Excel (плюсики).

Проверяет:
  - позиции, запланированные ПО ФЭО (feo_amount задан, активна) — выведены;
    чисто внутренний план (is_internal_plan, feo_amount=NULL) — не выведен;
  - формулы в D ссылаются РОВНО на строки ПРЯМЫХ детей (не внуков);
  - outline_level: категория 1-го уровня = 0, подкатегория = 1, позиции под
    ней = 2; категория без детей — число, не формула;
  - строки позиций hidden=True, ws.sheet_properties.outlinePr.summaryBelow
    is False.
"""
import uuid
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from io import BytesIO


async def _make_subsidy(db_session, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, level=1, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_item(db_session, feo_category_id, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=kwargs.pop("name", "Позиция плана"),
        unit="шт",
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_export_outline_and_feo_items(client, db_session, admin_headers, test_admin_user):
    subsidy = await _make_subsidy(db_session)

    root = await _make_category(db_session, subsidy.id, level=1, name="Направление", budget=Decimal("500000"))
    sub = await _make_category(db_session, subsidy.id, parent_id=root.id, level=2, name="Подкатегория", budget=Decimal("300000"))
    leaf_no_children = await _make_category(db_session, subsidy.id, parent_id=root.id, level=2, name="Категория без детей", budget=Decimal("77000"))

    # Две позиции по ФЭО под подкатегорией (выводятся).
    item1 = await _make_item(
        db_session, sub.id, name="Позиция ФЭО 1",
        feo_amount=Decimal("1000"), amount=Decimal("900"),
    )
    item2 = await _make_item(
        db_session, sub.id, name="Позиция ФЭО 2",
        feo_amount=Decimal("2000"), amount=Decimal("1800"),
    )
    # Чисто внутренний план — feo_amount NULL, не выводится.
    item_internal = await _make_item(
        db_session, sub.id, name="Только внутренний план",
        feo_amount=None, amount=Decimal("5000"), is_internal_plan=True,
    )

    r = await client.get(
        "/api/feo-categories/export", params={"subsidy_id": subsidy.id}, headers=admin_headers
    )
    assert r.status_code == 200, r.text

    wb = load_workbook(BytesIO(r.content))
    ws = wb.active

    assert ws.sheet_properties.outlinePr.summaryBelow is False

    names = [c.value.strip() for c in ws["A"] if c.value]
    assert "Позиция ФЭО 1" in names
    assert "Позиция ФЭО 2" in names
    assert "Только внутренний план" not in names

    def _find_row(name_contains):
        for row in ws.iter_rows(min_row=2):
            v = row[0].value
            if v and name_contains in v:
                return row[0].row
        raise AssertionError(f"row not found: {name_contains}")

    r_root = _find_row("Направление")
    r_sub = _find_row("Подкатегория")
    r_leaf = _find_row("Категория без детей")
    r_item1 = _find_row("Позиция ФЭО 1")
    r_item2 = _find_row("Позиция ФЭО 2")

    # outline_level: корень=0, подкатегория=1, позиции под ней=2.
    assert (ws.row_dimensions[r_root].outline_level or 0) == 0
    assert ws.row_dimensions[r_sub].outline_level == 1
    assert ws.row_dimensions[r_leaf].outline_level == 1
    assert ws.row_dimensions[r_item1].outline_level == 2
    assert ws.row_dimensions[r_item2].outline_level == 2

    # Строки позиций скрыты по умолчанию.
    assert ws.row_dimensions[r_item1].hidden is True
    assert ws.row_dimensions[r_item2].hidden is True

    # D у позиций — числа (feo_amount), E — числа (amount, "план").
    assert ws.cell(r_item1, 4).value == 1000.0
    assert ws.cell(r_item1, 5).value == 900.0
    assert ws.cell(r_item2, 4).value == 2000.0
    assert ws.cell(r_item2, 5).value == 1800.0

    # D подкатегории — формула SUM по её прямым детям (две позиции, не внуки).
    d_sub = ws.cell(r_sub, 4).value
    assert isinstance(d_sub, str) and d_sub.startswith("=SUM(")
    assert f"D{r_item1}" in d_sub and f"D{r_item2}" in d_sub
    # Ровно два слагаемых (не более — никаких внуков/чужих строк).
    assert d_sub.count("D") == 2

    # D корня — формула SUM по его прямым детям (подкатегория + категория без
    # детей), НЕ по внукам (позициям).
    d_root = ws.cell(r_root, 4).value
    assert isinstance(d_root, str) and d_root.startswith("=SUM(")
    assert f"D{r_sub}" in d_root and f"D{r_leaf}" in d_root
    assert f"D{r_item1}" not in d_root and f"D{r_item2}" not in d_root

    # Категория без детей — число (budget), не формула.
    assert ws.cell(r_leaf, 4).value == 77000.0
