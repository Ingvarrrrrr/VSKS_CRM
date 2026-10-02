"""GET /fact-import/template — xlsx-шаблон (формат ХО, иерархия колонками)
предзаполненный строками ТЕКУЩЕГО плана субсидии (путь ФЭО + плановая
позиция + план), чтобы пользователь дописал только факт/статус/поставщика.

🔵 Правка 3: «Правильный статус» — выпадающий список (DataValidation, НЕ
блокирующая — showErrorMessage=False) из РОВНО 6 статусов GALA, плюс лист
«Справочники» с тем же списком (память проекта feedback_excel_template_
dropdowns: enum → dropdown + лист «Справочники»).

Переиспользует plan_catalog.load_plan_catalog (ПРАВИЛО №6 — тот же каталог,
что matching.py и ручной матчинг /feo-planned-items/match), а не второй
обход дерева ФЭО.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import statuses as statuses_mod
from app.services.plan_catalog import load_plan_catalog


async def build_template_workbook(db: AsyncSession, subsidy_id: int) -> bytes:
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    catalog = await load_plan_catalog(db, subsidy_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Импорт факта"
    ws.append(columns_mod.TEMPLATE_HEADER)

    for entry in catalog:
        path_parts = [p for p in (entry.get("path") or "").split(" › ") if p]
        if entry.get("kind") == "planned_item":
            plan_item_name = entry.get("name")
        else:
            # Лист дерева без собственной FeoPlannedItem — сама категория и
            # есть «плановая позиция» шаблона.
            path_parts = path_parts + [entry.get("name")] if path_parts else [entry.get("name")]
            plan_item_name = None
        levels = ([None] * 3 + path_parts)[-3:]  # последние 3 уровня → l2/l3/l4

        row = [None] * 28
        row[0] = "ХО_2026" if subsidy_id else None
        row[4], row[5], row[6] = levels[0], levels[1], levels[2]
        row[7] = plan_item_name
        row[15] = entry.get("quantity")
        row[16] = entry.get("unit_price")
        row[17] = entry.get("amount")
        ws.append(row)

    # «Справочники» — РОВНО 6 статусов GALA (owner: enum → dropdown + лист
    # справочника, не блокирующая валидация — lesson feedback_excel_template_
    # dropdowns).
    ref = wb.create_sheet("Справочники")
    ref.append(["Правильный статус"])
    for choice in statuses_mod.STATUS_CHOICES:
        ref.append([choice["label"]])

    n_statuses = len(statuses_mod.STATUS_CHOICES)
    dv = DataValidation(
        type="list",
        formula1=f"Справочники!$A$2:$A${1 + n_statuses}",
        allow_blank=True,
        showErrorMessage=False,  # не блокирует свой ввод — lesson feedback_excel_template_dropdowns
    )
    last_row = max(ws.max_row, 2)
    dv.add(f"Y2:Y{last_row + 200}")  # запас строк под дозапись вручную
    ws.add_data_validation(dv)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
