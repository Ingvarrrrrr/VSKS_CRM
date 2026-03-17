from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user, get_org_filter
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


@router.get("/purchase-totals")
async def get_purchase_totals(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Sum of planned_total_price per feo_category_id for a given subsidy."""
    from app.models.purchase import Purchase
    stmt = (
        select(
            Purchase.feo_category_id,
            func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total_planned"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .group_by(Purchase.feo_category_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r.feo_category_id: float(r.total_planned) for r in rows}


@router.get("/", response_model=List[FeoCategoryOut])
async def list_categories(
    parent_id: Optional[int] = Query(None),
    level: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    appendix: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(FeoCategory)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, FeoCategory.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    if parent_id is not None:
        q = q.where(FeoCategory.parent_id == parent_id)
    if level is not None:
        q = q.where(FeoCategory.level == level)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    if appendix is not None:
        q = q.where(FeoCategory.appendix == appendix)
    if is_active is not None:
        q = q.where(FeoCategory.is_active == is_active)
    result = await db.execute(q.order_by(FeoCategory.id))
    return result.scalars().all()


@router.get("/tree")
async def category_tree(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(FeoCategory)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, FeoCategory.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q.order_by(FeoCategory.level, FeoCategory.id))
    all_cats = result.scalars().all()
    by_id = {c.id: {"id": c.id, "parent_id": c.parent_id, "subsidy_id": c.subsidy_id,
                    "level": c.level, "name": c.name, "code": c.code,
                    "appendix": c.appendix, "is_active": c.is_active,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "children": []} for c in all_cats}
    roots = []
    for c in all_cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/", response_model=FeoCategoryOut)
async def create_category(
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    if category_data.parent_id:
        parent_result = await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена")
        level = parent.level + 1
    else:
        level = 1

    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active,
        budget=category_data.budget,
    )
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category


@router.get("/import/template")
async def download_feo_template():
    """Шаблон Excel для импорта категорий ФЭО (5 уровней: A-D иерархия, E-H плановые позиции, I-L атрибуты)."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Категории ФЭО"
    headers = [
        "Субсидия",                                      # A
        "Уровень 2 (Направление расходов по ФЭО)",       # B
        "Уровень 3 (Тип расходов по ФЭО)",               # C
        "Уровень 4 (Конкретизированный)",                # D
        "Уровень 5 (Плановый товар/услуга)",             # E
        "Количество (Ур.5)",                             # F
        "Ед. измерения (Ур.5)",                          # G
        "Сумма плановая (Ур.5)",                         # H
        "Код",                                           # I
        "Приложение",                                    # J
        "Финансирование (Ур.4)",                         # K
        "Активна",                                       # L
    ]
    ws.append(headers)

    # Цветовое кодирование заголовков
    fill_cat  = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")   # синий — категории
    fill_item = PatternFill(start_color="059669", end_color="059669", fill_type="solid")   # зелёный — позиции
    fill_attr = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")  # фиолетовый — атрибуты
    font_w = Font(color="FFFFFF", bold=True, size=10)

    for i, cell in enumerate(ws[1], start=1):
        if i <= 4:
            cell.fill = fill_cat
        elif i <= 8:
            cell.fill = fill_item
        else:
            cell.fill = fill_attr
        cell.font = font_w
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 52

    # Пример: категории без плановых позиций (старый формат — совместимо)
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "Техническое оснащение штаба", "Закупка компьютеров", "", "", "", "", "01.01.01", "Прил. 1", "2000000", "да"])
    # Пример: категория + плановые позиции уровня 5
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "Техническое оснащение штаба", "Закупка компьютеров", "Ноутбук HP 15 Intel i5", "3", "шт", "150000", "01.01.01", "Прил. 1", "2000000", "да"])
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "Техническое оснащение штаба", "Закупка компьютеров", "Монитор Dell 24\"", "3", "шт", "90000", "01.01.01", "Прил. 1", "", "да"])
    ws.append(["ФАДМ_2026", "Организация мероприятий", "Слёт студентов-спасателей", "Услуги по организации", "Услуга проживания участников", "100", "чел.", "3000000", "02.01.01", "Прил. 2", "3000000", "да"])
    ws.append(["ФАДМ_2026", "Организация мероприятий", "Слёт студентов-спасателей", "Услуги по организации", "Услуга логистики участников", "2", "рейс", "500000", "02.01.02", "Прил. 2", "", "да"])

    # Комментарий в строке 7
    hints = [
        "← Точное название как в системе",
        "← Направление расходов (создаётся если нет)",
        "← Тип расходов (если пусто — атрибуты к Ур.3)",
        "← Конкретизированный (если пусто — к Ур.3)",
        "← Плановый товар/услуга (необязательно)",
        "← Кол-во (необязательно)",
        "← Ед. изм. (шт, кг, услуга...)",
        "← Плановая сумма позиции",
        "← Код категории",
        "← Номер приложения",
        "← Бюджет категории Ур.4",
        "← да/нет",
    ]
    for col, hint in enumerate(hints, start=1):
        ws.cell(7, col).value = hint
        ws.cell(7, col).font = Font(italic=True, color="888888", size=8)

    for i, w in enumerate([18, 42, 42, 45, 45, 12, 14, 18, 10, 12, 18, 10], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=feo_categories_template.xlsx"})


@router.post("/import")
async def import_feo_from_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Импорт категорий ФЭО из Excel.
    Формат: Субсидия | Уровень 2 | Уровень 3 | Уровень 4 | Код | Приложение | Финансирование | Активна
    Каждая строка задаёт путь в иерархии. Промежуточные узлы создаются автоматически.
    Код/Приложение/Финансирование/Активна применяются к самому глубокому указанному уровню.
    Возвращает {created, updated, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    # Определяем индексы столбцов по заголовку строки 1
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    def find_col(keywords: list[str]) -> int | None:
        for kw in keywords:
            for i, h in enumerate(raw_headers):
                if kw in h:
                    return i
        return None

    c_subsidy  = find_col(["субсидия"])
    c_lvl2     = find_col(["уровень 2", "направление расходов", "level 2"])
    c_lvl3     = find_col(["уровень 3", "тип расходов", "level 3"])
    c_lvl4     = find_col(["уровень 4", "конкретизир", "level 4"])
    c_lvl5     = find_col(["уровень 5", "плановый товар", "level 5"])
    c_qty      = find_col(["количество", "кол-во", "qty"])
    c_unit     = find_col(["ед. изм", "единица изм", "ед.изм"])
    c_item_amt = find_col(["сумма плановая", "сумма (ур.5)", "сумма ур"])
    c_code     = find_col(["код"])
    c_appendix = find_col(["приложение"])
    c_budget   = find_col(["финансирование", "бюджет", "budget"])
    c_active   = find_col(["активна", "активен", "active"])

    if c_subsidy is None or c_lvl2 is None:
        raise HTTPException(400, "Не найдены обязательные столбцы: 'Субсидия' и 'Уровень 2 (Направление расходов)'")

    def get_cell(row: tuple, col: int | None) -> str | None:
        if col is None or col >= len(row): return None
        v = row[col]
        return str(v).strip() if v is not None else None

    def to_bool(v: str | None) -> bool:
        if v is None: return True
        return v.lower() in ("да", "yes", "true", "1", "+")

    def to_dec(v: str | None):
        if not v: return None
        try: return Decimal(v.replace(" ", "").replace(",", ".").replace("\xa0", ""))
        except: return None

    from app.models.subsidy import Subsidy
    sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    sub_by_name = {s.name.lower().strip(): s.id for s in sub_rows}

    # Кэш: (subsidy_id, parent_id_or_None, name_lower) → FeoCategory
    existing_cats = (await db.execute(select(FeoCategory))).scalars().all()
    cat_cache: dict[tuple, FeoCategory] = {}
    for c in existing_cats:
        cat_cache[(c.subsidy_id, c.parent_id, c.name.lower().strip())] = c

    created = 0; updated = 0; skipped = 0; errors: list[dict] = []

    async def find_or_create(subsidy_id: int, parent_id, name: str, level: int) -> FeoCategory:
        key = (subsidy_id, parent_id, name.lower().strip())
        if key in cat_cache:
            return cat_cache[key]
        cat = FeoCategory(
            name=name, subsidy_id=subsidy_id, parent_id=parent_id, level=level,
            is_active=True,
        )
        db.add(cat)
        await db.flush()
        cat_cache[key] = cat
        return cat

    for row_num, row in enumerate(rows[1:], start=2):
        # Пропускаем строки-комментарии (строка 6 в шаблоне — подсказка)
        sub_name = get_cell(row, c_subsidy)
        if not sub_name or sub_name.startswith("←"):
            skipped += 1
            continue

        lvl2_name = get_cell(row, c_lvl2)
        if not lvl2_name or lvl2_name.startswith("←"):
            skipped += 1
            continue

        subsidy_id = sub_by_name.get(sub_name.lower().strip())
        if not subsidy_id:
            errors.append({"row": row_num, "name": lvl2_name, "message": f"Субсидия не найдена: '{sub_name}'"})
            continue

        lvl3_name = get_cell(row, c_lvl3) if c_lvl3 is not None else None
        lvl4_name = get_cell(row, c_lvl4) if c_lvl4 is not None else None
        lvl5_name = get_cell(row, c_lvl5) if c_lvl5 is not None else None

        code      = get_cell(row, c_code)
        appendix  = get_cell(row, c_appendix)
        budget    = to_dec(get_cell(row, c_budget))
        is_active = to_bool(get_cell(row, c_active))

        # Уровень 5 (плановый товар)
        item_qty    = to_dec(get_cell(row, c_qty)) if c_qty is not None else None
        item_unit   = get_cell(row, c_unit) if c_unit is not None else None
        item_amount = to_dec(get_cell(row, c_item_amt)) if c_item_amt is not None else None

        try:
            # Уровень 2 → FeoCategory.level=1
            cat_l1 = await find_or_create(subsidy_id, None, lvl2_name, 1)
            if cat_l1.id and (subsidy_id, None, lvl2_name.lower().strip()) not in {k for k in cat_cache if cat_cache[k] is cat_l1 and cat_cache[k].id == cat_l1.id}:
                created += 1
            leaf = cat_l1

            if lvl3_name:
                # Уровень 3 → FeoCategory.level=2, родитель = l1
                is_new_l2 = (subsidy_id, cat_l1.id, lvl3_name.lower().strip()) not in cat_cache
                cat_l2 = await find_or_create(subsidy_id, cat_l1.id, lvl3_name, 2)
                if is_new_l2 and cat_l2.id:
                    created += 1
                leaf = cat_l2

                if lvl4_name:
                    # Уровень 4 → FeoCategory.level=3, родитель = l2
                    is_new_l3 = (subsidy_id, cat_l2.id, lvl4_name.lower().strip()) not in cat_cache
                    cat_l3 = await find_or_create(subsidy_id, cat_l2.id, lvl4_name, 3)
                    if is_new_l3 and cat_l3.id:
                        created += 1
                    leaf = cat_l3

            # Применяем атрибуты к листовому узлу (уровень 4 или выше)
            changed = False
            if code is not None and leaf.code != code:
                leaf.code = code; changed = True
            if appendix is not None and leaf.appendix != appendix:
                leaf.appendix = appendix; changed = True
            if budget is not None and leaf.budget != budget:
                leaf.budget = budget; changed = True
            if leaf.is_active != is_active:
                leaf.is_active = is_active; changed = True
            if changed:
                updated += 1

            # Уровень 5 → FeoPlannedItem (если заполнено)
            if lvl5_name and lvl5_name not in ("←", ""):
                from app.models.feo_planned_item import FeoPlannedItem
                # Проверяем дубликат: (feo_category_id, name)
                existing_item = (await db.execute(
                    select(FeoPlannedItem).where(
                        FeoPlannedItem.feo_category_id == leaf.id,
                        FeoPlannedItem.name == lvl5_name,
                    )
                )).scalar_one_or_none()
                if not existing_item:
                    pi = FeoPlannedItem(
                        feo_category_id=leaf.id,
                        name=lvl5_name,
                        quantity=item_qty,
                        unit=item_unit,
                        amount=item_amount,
                        is_active=is_active,
                    )
                    db.add(pi)
                    await db.flush()
                    created += 1
                else:
                    # Обновляем если изменились
                    ch2 = False
                    if item_qty is not None and existing_item.quantity != item_qty:
                        existing_item.quantity = item_qty; ch2 = True
                    if item_unit is not None and existing_item.unit != item_unit:
                        existing_item.unit = item_unit; ch2 = True
                    if item_amount is not None and existing_item.amount != item_amount:
                        existing_item.amount = item_amount; ch2 = True
                    if ch2:
                        updated += 1
                    else:
                        skipped += 1

        except Exception as e:
            errors.append({"row": row_num, "name": lvl2_name, "message": str(e)})

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


@router.get("/export")
async def export_feo_to_excel(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Экспорт дерева категорий ФЭО в Excel."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.id)
    )).scalars().all()

    # purchase totals
    pt_rows = (await db.execute(
        select(Purchase.feo_category_id, func.coalesce(func.sum(Purchase.planned_total_price), 0).label("t"))
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .group_by(Purchase.feo_category_id)
    )).all()
    purchase_totals = {r.feo_category_id: float(r.t) for r in pt_rows}

    # Build tree
    by_id = {c.id: {"cat": c, "children": []} for c in cats}
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(by_id[c.id])
        else:
            roots.append(by_id[c.id])

    def calc_budget(node):
        c = node["cat"]
        if not node["children"]:
            return float(c.budget) if c.budget is not None else None
        child_sum = sum(v for ch in node["children"] if (v := calc_budget(ch)) is not None)
        return child_sum if any(calc_budget(ch) is not None for ch in node["children"]) else (float(c.budget) if c.budget is not None else None)

    def calc_purchased(node):
        c = node["cat"]
        if not node["children"]:
            return purchase_totals.get(c.id, 0.0)
        return sum(calc_purchased(ch) for ch in node["children"])

    wb = Workbook()
    ws = wb.active
    ws.title = sub.name[:31]

    header_fill = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    l1_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    l2_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    bold_font = Font(bold=True)
    semi_font = Font(bold=False)

    ws.append(["Наименование", "Код", "Прил.", "Финансирование по ФЭО (₽)", "Фактически запланировано (₽)", "Активна"])
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32

    def write_node(node, depth=0):
        c = node["cat"]
        indent = "  " * depth
        budget = calc_budget(node)
        purchased = calc_purchased(node)
        row = [
            indent + c.name,
            c.code or "",
            c.appendix or "",
            budget if budget is not None else "",
            purchased if purchased > 0 else "",
            "Да" if c.is_active else "Нет",
        ]
        ws.append(row)
        r = ws.max_row
        fill = l1_fill if c.level == 1 else (l2_fill if c.level == 2 else None)
        font = bold_font if c.level == 1 else (semi_font)
        for col in range(1, 7):
            cell = ws.cell(r, col)
            if fill:
                cell.fill = fill
            cell.font = font
            if col in (4, 5) and isinstance(cell.value, float):
                cell.number_format = '#,##0.00'
        for ch in node["children"]:
            write_node(ch, depth + 1)

    for root in roots:
        write_node(root)

    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 22
    ws.column_dimensions["F"].width = 10
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = sub.name.replace(" ", "_").replace("/", "-")[:40]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=feo_{safe_name}.xlsx"},
    )


@router.put("/{cat_id}", response_model=FeoCategoryOut)
async def update_category(
    cat_id: int,
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    cat.name = category_data.name
    cat.code = category_data.code
    cat.appendix = category_data.appendix
    cat.is_active = category_data.is_active
    cat.budget = category_data.budget
    await db.commit()
    await db.refresh(cat)
    return cat


async def _collect_subtree_ids(cat_id: int, db: AsyncSession) -> list[int]:
    """Recursively collect all descendant IDs including the given cat_id."""
    ids = [cat_id]
    children = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for cid in children:
        ids.extend(await _collect_subtree_ids(cid, db))
    return ids


async def _update_subtree_levels(cat_id: int, level_delta: int, db: AsyncSession):
    """Recursively update levels of all children by delta."""
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for child in children:
        child.level = child.level + level_delta
        await _update_subtree_levels(child.id, level_delta, db)


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db)
):
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Collect entire subtree
    all_ids = await _collect_subtree_ids(cat_id, db)

    # Check linked purchases across entire subtree
    from app.models.purchase import Purchase
    linked_count = (await db.execute(
        select(func.count()).select_from(Purchase).where(Purchase.feo_category_id.in_(all_ids))
    )).scalar() or 0
    if linked_count:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить: {linked_count} закупок привязано к этой категории или дочерним."
        )

    # Cascade delete (children first)
    for cid in reversed(all_ids):
        obj = await db.get(FeoCategory, cid)
        if obj:
            await db.delete(obj)
    await db.commit()
    deleted_count = len(all_ids)
    return {"ok": True, "deleted_count": deleted_count}


@router.patch("/{cat_id}/move")
async def move_category(
    cat_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Move category to a new parent. Set parent_id=null to make root."""
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    new_parent_id = data.get("parent_id")
    warning = None

    # Determine new level
    if new_parent_id:
        parent = (await db.execute(select(FeoCategory).where(FeoCategory.id == new_parent_id))).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != cat.subsidy_id:
            raise HTTPException(status_code=400, detail="Нельзя переместить в другую субсидию")
        new_level = parent.level + 1
    else:
        new_level = 1

    level_delta = new_level - cat.level

    # Check for circular reference
    if new_parent_id:
        subtree_ids = await _collect_subtree_ids(cat_id, db)
        if new_parent_id in subtree_ids:
            raise HTTPException(status_code=400, detail="Нельзя переместить в собственное поддерево")

    # Check if new max depth creates a previously unseen level
    max_child_depth = 0
    all_ids = await _collect_subtree_ids(cat_id, db)
    if len(all_ids) > 1:
        max_existing = (await db.execute(
            select(func.max(FeoCategory.level)).where(FeoCategory.id.in_(all_ids))
        )).scalar() or cat.level
        max_child_depth = max_existing - cat.level
    new_max_level = new_level + max_child_depth
    existing_max = (await db.execute(
        select(func.max(FeoCategory.level)).where(FeoCategory.subsidy_id == cat.subsidy_id)
    )).scalar() or 1
    if new_max_level > existing_max:
        warning = f"Создан новый уровень вложенности: {new_max_level}"

    # Update category
    cat.parent_id = new_parent_id
    cat.level = new_level

    # Recursively update children levels
    if level_delta != 0:
        await _update_subtree_levels(cat_id, level_delta, db)

    await db.commit()
    result = {"ok": True, "new_level": new_level}
    if warning:
        result["warning"] = warning
    return result
