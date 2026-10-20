"""Тест загрузки обратно «Выгрузить ФЭО» (владелец, 20.10.2026).

Сценарии (см. задание):
  (а) выгрузка субсидии с деревом -> правки (ФЭО позиции, переименование
      категории, новая позиция, новая подкатегория с позицией) -> preview
      показывает ровно это -> apply -> БД совпадает, прогон в журнале.
  (б) пустая субсидия, файл без № (уровни отступами, без outline) -> apply
      строит дерево.
  (в) файл другой субсидии -> ошибка.

Использует общие фикстуры conftest.py (db_session/client/test_org/
make_user) — всё внутри одной тестовой транзакции, которая откатывается в
конце (см. докстринг db_session): ничего не остаётся в реальной БД.

Запуск: docker compose -p vsks_crm exec backend_a pytest
tests/test_feo_roundtrip_import.py -q
"""
import io

import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_import_run import FeoImportRun
from app.auth.jwt import create_access_token


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


async def _mk_subsidy(db_session, org_id, name):
    sub = Subsidy(name=name, org_id=org_id, year=2026)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


def _headers_map(ws, header_row=3):
    out = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v:
            out[str(v).strip()] = c
    return out


@pytest.mark.asyncio
async def test_roundtrip_export_edit_import_tree(db_session, test_org, make_user, client):
    owner = await make_user(role="superadmin", org_id=test_org.id)
    headers = _headers_for(owner)
    sub = await _mk_subsidy(db_session, test_org.id, "RT-tree")
    sub_id = sub.id

    cat1 = FeoCategory(name="Equipment", subsidy_id=sub.id, level=1, is_active=True, budget=100000)
    db_session.add(cat1)
    await db_session.flush()
    item1 = FeoPlannedItem(
        feo_category_id=cat1.id, name="Jacket", quantity=10, unit="pcs",
        amount=50000, feo_amount=50000, is_active=True,
    )
    cat2 = FeoCategory(name="Transport", subsidy_id=sub.id, level=1, is_active=True, budget=200000)
    db_session.add_all([item1, cat2])
    await db_session.commit()
    cat1_id, item1_id = cat1.id, item1.id

    resp = await client.get(f"/api/feo-categories/export?subsidy_id={sub_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    content = resp.content

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    hmap = _headers_map(ws)
    last_row = ws.max_row

    insert_at = None
    transport_outline = None
    for r in range(4, last_row + 1):
        name_cell = ws.cell(row=r, column=hmap["Наименование"])
        name_val = (name_cell.value or "").strip()
        if name_val == "Equipment":
            name_cell.value = "Equipment and PPE"
        if name_val == "Jacket":
            ws.cell(row=r, column=hmap["Финансирование по ФЭО (₽)"]).value = 60000
        if name_val == "Transport":
            insert_at = r + 1
            transport_outline = ws.row_dimensions[r].outline_level or 0
    assert insert_at is not None

    ws.insert_rows(insert_at, amount=2)
    # Строки, добавленные руками в файл с группировкой Excel (outline), — им
    # нужен СВОЙ outline_level (та же глубина, что у плановой позиции прямо
    # под категорией «Transport»), иначе build_hierarchy увидит их уровнем 0
    # (т.к. use_outline=True для всего файла) — то же, что сделал бы живой
    # человек через «Группировать» в Excel, не просто отступ в тексте.
    item_outline = transport_outline + 1
    ws.cell(row=insert_at, column=hmap["Наименование"]).value = "Hat"
    ws.cell(row=insert_at, column=hmap["Финансирование по ФЭО (₽)"]).value = 5000
    ws.cell(row=insert_at, column=hmap["Запланировано (₽)"]).value = 5000
    ws.cell(row=insert_at, column=hmap["Тип строки"]).value = "Позиция"
    ws.row_dimensions[insert_at].outline_level = item_outline

    ws.cell(row=insert_at + 1, column=hmap["Наименование"]).value = "Radio"
    ws.cell(row=insert_at + 1, column=hmap["Финансирование по ФЭО (₽)"]).value = 15000
    ws.cell(row=insert_at + 1, column=hmap["Запланировано (₽)"]).value = 15000
    ws.cell(row=insert_at + 1, column=hmap["Тип строки"]).value = "Позиция"
    ws.row_dimensions[insert_at + 1].outline_level = item_outline

    buf = io.BytesIO()
    wb.save(buf)
    content2 = buf.getvalue()

    files = {"file": ("export.xlsx", content2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"subsidy_id": str(sub_id)}
    resp = await client.post("/api/feo-categories/roundtrip/preview", headers=headers, files=files, data=data)
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert not preview["errors"], preview["errors"]
    change_fields = {(c["name"], c["field"]) for c in preview["changes"]}
    assert ("Equipment", "name") in change_fields
    assert ("Jacket", "feo_amount") in change_fields
    created_names = {c["name"] for c in preview["created"]}
    assert "Hat" in created_names
    assert "Radio" in created_names

    files2 = {"file": ("export.xlsx", content2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp2 = await client.post("/api/feo-categories/roundtrip/apply", headers=headers, files=files2, data=data)
    assert resp2.status_code == 200, resp2.text
    result = resp2.json()
    assert result["created"] >= 2
    assert result["updated"] >= 2

    db_session.expire_all()
    cat1_db = await db_session.get(FeoCategory, cat1_id)
    assert cat1_db.name == "Equipment and PPE"
    item1_db = await db_session.get(FeoPlannedItem, item1_id)
    assert float(item1_db.feo_amount) == 60000.0
    new_items = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.name.in_(["Hat", "Radio"]))
    )).scalars().all()
    assert len(new_items) == 2

    runs = (await db_session.execute(
        select(FeoImportRun).where(FeoImportRun.subsidy_id == sub_id)
    )).scalars().all()
    assert len(runs) == 1
    assert runs[0].created_count >= 2


@pytest.mark.asyncio
async def test_roundtrip_empty_subsidy_builds_tree_from_indentation(db_session, test_org, make_user, client):
    owner = await make_user(role="superadmin", org_id=test_org.id)
    headers = _headers_for(owner)
    sub = await _mk_subsidy(db_session, test_org.id, "RT-empty")
    sub_id = sub.id

    resp = await client.get(f"/api/feo-categories/export?subsidy_id={sub_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    content = resp.content

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    hmap = _headers_map(ws)

    r = 4
    ws.cell(row=r, column=hmap["Наименование"]).value = "Article A"
    ws.cell(row=r, column=hmap["Финансирование по ФЭО (₽)"]).value = 100000
    r += 1
    ws.cell(row=r, column=hmap["Наименование"]).value = "  Item A1"
    ws.cell(row=r, column=hmap["Финансирование по ФЭО (₽)"]).value = 40000
    ws.cell(row=r, column=hmap["Запланировано (₽)"]).value = 40000

    buf = io.BytesIO()
    wb.save(buf)
    content2 = buf.getvalue()

    files = {"file": ("export.xlsx", content2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"subsidy_id": str(sub_id)}
    resp = await client.post("/api/feo-categories/roundtrip/apply", headers=headers, files=files, data=data)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 2

    db_session.expire_all()
    cats = (await db_session.execute(select(FeoCategory).where(FeoCategory.subsidy_id == sub_id))).scalars().all()
    assert len(cats) == 1
    assert cats[0].name == "Article A"
    items = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == cats[0].id)
    )).scalars().all()
    assert len(items) == 1
    assert items[0].name == "Item A1"


@pytest.mark.asyncio
async def test_roundtrip_rejects_other_subsidy_file(db_session, test_org, make_user, client):
    owner = await make_user(role="superadmin", org_id=test_org.id)
    headers = _headers_for(owner)
    sub_a = await _mk_subsidy(db_session, test_org.id, "RT-A")
    sub_b = await _mk_subsidy(db_session, test_org.id, "RT-B")

    resp = await client.get(f"/api/feo-categories/export?subsidy_id={sub_a.id}", headers=headers)
    content = resp.content

    files = {"file": ("export.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"subsidy_id": str(sub_b.id)}
    resp2 = await client.post("/api/feo-categories/roundtrip/preview", headers=headers, files=files, data=data)
    assert resp2.status_code == 400, resp2.text
    assert "другой субсидии" in str(resp2.json())


@pytest.mark.asyncio
async def test_roundtrip_noop_export_then_import_without_edits(db_session, test_org, make_user, client):
    """Выгрузил -> загрузил ОБРАТНО без единой правки -> 0 changes/created/
    moved/missing (прод-находка, субсидии 46/61, 20.10.2026):
    - категория с ВЕДУЩИМИ ПРОБЕЛАМИ в имени в БД ("  Leading Space Rent") —
      экспорт сам добавляет отступ "  "*depth к имени, сравнение по сырой
      строке ложно считало это изменением (diff.py::_norm_name);
    - плановая позиция БЕЗ feo_amount (план без ФЭО) — выгрузка её не
      выводит (тот же фильтр app.services.subsidy_budget.
      _active_feo_items_with_amount, что и build_feo_export_workbook), но
      раньше diff.py сравнивал со ВСЕМИ позициями субсидии и ложно считал
      её "нет в файле"."""
    owner = await make_user(role="superadmin", org_id=test_org.id)
    headers = _headers_for(owner)
    sub = await _mk_subsidy(db_session, test_org.id, "RT-noop")
    sub_id = sub.id

    cat1 = FeoCategory(name="  Leading Space Rent", subsidy_id=sub.id, level=1, is_active=True, budget=100000)
    db_session.add(cat1)
    await db_session.flush()
    item_with_feo = FeoPlannedItem(
        feo_category_id=cat1.id, name="Jacket", quantity=10, unit="pcs",
        amount=50000, feo_amount=50000, is_active=True,
    )
    # Позиция без feo_amount (план без ФЭО) — выгрузка её не печатает строкой.
    item_no_feo = FeoPlannedItem(
        feo_category_id=cat1.id, name="Internal plan only", quantity=1, unit="pcs",
        amount=1000, feo_amount=None, is_active=True,
    )
    db_session.add_all([item_with_feo, item_no_feo])
    await db_session.commit()

    resp = await client.get(f"/api/feo-categories/export?subsidy_id={sub_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    content = resp.content

    files = {"file": ("export.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"subsidy_id": str(sub_id)}
    resp2 = await client.post("/api/feo-categories/roundtrip/preview", headers=headers, files=files, data=data)
    assert resp2.status_code == 200, resp2.text
    preview = resp2.json()
    assert preview["changes"] == [], preview["changes"]
    assert preview["created"] == [], preview["created"]
    assert preview["moved"] == [], preview["moved"]
    assert preview["missing"] == [], preview["missing"]
    assert preview["errors"] == [], preview["errors"]
