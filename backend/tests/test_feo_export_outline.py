"""GET /api/feo-categories/export (backend/app/routers/feo_import_export.py) —
выгрузка теперь включает плановые позиции ФЭО и группировку Excel (плюсики).

ИЗМЕНЕНО (владелец 20.10.2026): столбцы выбираемые (app.services.
feo_export_columns), заголовок переехал на строку 3 (строки 1-2 — «Итого
всего»/«Итого по фильтру», см. app.services.feo_export_xlsx), колонка
«Финансирование по ФЭО» теперь B (ключ "feo", по умолчанию name,feo,plan,...),
формула категории — SUBTOTAL(9, ...) по прямым детям (функция 9 — считает и
скрытые строки позиций), не SUM.

Проверяет:
  - позиции, запланированные ПО ФЭО (feo_amount задан, активна) — выведены;
    чисто внутренний план (is_internal_plan, feo_amount=NULL) — не выведен;
  - формулы в колонке «feo» ссылаются РОВНО на строки ПРЯМЫХ детей (не внуков);
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
        for row in ws.iter_rows(min_row=4):
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

    # По умолчанию столбец B = "feo" (Финансирование по ФЭО), C = "plan"
    # (Запланировано) — см. app.services.feo_export_columns.DEFAULT_KEYS.
    assert ws.cell(r_item1, 2).value == 1000.0
    assert ws.cell(r_item1, 3).value == 900.0
    assert ws.cell(r_item2, 2).value == 2000.0
    assert ws.cell(r_item2, 3).value == 1800.0

    # B подкатегории — формула SUM(...) по её прямым детям (две позиции, не
    # внуки) — НЕ SUBTOTAL: SUBTOTAL(9,...) игнорирует ячейки, которые сами
    # результат другого SUBTOTAL/формулы-агрегата, и категория с детьми
    # получала бы 0 (баг владельца, исправлен 20.10.2026).
    b_sub = ws.cell(r_sub, 2).value
    assert isinstance(b_sub, str) and b_sub.startswith("=SUM(")
    assert f"B{r_item1}" in b_sub and f"B{r_item2}" in b_sub
    refs_sub = b_sub[len("=SUM("):-1].split(",")
    assert len(refs_sub) == 2

    # B корня — формула SUM(...) по его прямым детям (подкатегория +
    # категория без детей), НЕ по внукам (позициям).
    b_root = ws.cell(r_root, 2).value
    assert isinstance(b_root, str) and b_root.startswith("=SUM(")
    assert f"B{r_sub}" in b_root and f"B{r_leaf}" in b_root
    assert f"B{r_item1}" not in b_root and f"B{r_item2}" not in b_root

    # Категория без детей — число (budget), не формула.
    assert ws.cell(r_leaf, 2).value == 77000.0

    # Колонка «Тип строки» — последняя из дефолтных; категория с детьми =
    # «Категория», позиция = «Позиция», лист без детей = «Категория без
    # позиций».
    headers = [c.value for c in ws[3]]
    ci_row_type = headers.index("Тип строки") + 1
    assert ws.cell(r_root, ci_row_type).value == "Категория"
    assert ws.cell(r_sub, ci_row_type).value == "Категория"
    assert ws.cell(r_leaf, ci_row_type).value == "Категория без позиций"
    assert ws.cell(r_item1, ci_row_type).value == "Позиция"
    assert ws.cell(r_item2, ci_row_type).value == "Позиция"
