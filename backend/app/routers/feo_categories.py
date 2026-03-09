from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user
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
    db: AsyncSession = Depends(get_db)
):
    q = select(FeoCategory)
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
    db: AsyncSession = Depends(get_db)
):
    q = select(FeoCategory)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
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
        if level > 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Максимальный уровень вложенности - 3")
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
    """Шаблон Excel для импорта категорий ФЭО."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Категории ФЭО"
    headers = [
        "Наименование", "Субсидия", "Родительская категория",
        "Код", "Приложение", "Финансирование", "Активна",
    ]
    ws.append(headers)
    fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = fill; cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    # Example rows showing hierarchy
    ws.append(["Техническое оснащение", "ФАДМ_2026", "", "01", "Прил. 1", "5000000", "да"])
    ws.append(["Компьютерная техника", "ФАДМ_2026", "Техническое оснащение", "01.01", "Прил. 1", "2000000", "да"])
    ws.append(["Мониторы", "ФАДМ_2026", "Компьютерная техника", "01.01.01", "Прил. 1", "500000", "да"])
    for i, w in enumerate([40, 20, 40, 12, 15, 18, 10], 1):
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
    """Импорт категорий ФЭО из Excel. Иерархия строится за 3 прохода (уровни 1→2→3).
    Возвращает {created, skipped, errors}."""
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

    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    COLUMN_MAP = {
        "наименование": "name",
        "субсидия": "subsidy_name",
        "родительская категория": "parent_name",
        "код": "code",
        "приложение": "appendix",
        "финансирование": "budget",
        "активна": "is_active",
        "активен": "is_active",
    }
    col_idx: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i

    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row): return None
        v = row[idx]; return str(v).strip() if v is not None else None

    def to_bool(v):
        if v is None: return True
        return str(v).lower().strip() in ("да", "yes", "true", "1", "+")

    def to_dec(v):
        if v is None: return None
        try: return Decimal(str(v).replace(" ", "").replace(",", "."))
        except: return None

    # Load subsidies by name (case-insensitive)
    from app.models.subsidy import Subsidy
    sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    sub_by_name = {s.name.lower().strip(): s.id for s in sub_rows}

    # Load existing FEO categories for parent lookup: (subsidy_id, name.lower) → id
    existing = (await db.execute(select(FeoCategory))).scalars().all()
    created_map: dict[tuple, int] = {(c.subsidy_id, c.name.lower().strip()): c.id for c in existing}

    data_rows = [(i + 2, row) for i, row in enumerate(rows[1:])]
    created = 0; skipped = 0; errors: list[dict] = []

    # Up to 3 passes to handle parent-child ordering
    pending = data_rows[:]
    for _pass in range(3):
        if not pending:
            break
        still_pending = []
        for row_num, row in pending:
            try:
                name = cell(row, "name")
                if not name:
                    skipped += 1
                    continue

                sub_name = cell(row, "subsidy_name")
                if not sub_name:
                    errors.append({"row": row_num, "name": name, "message": "Не указана субсидия"})
                    continue
                subsidy_id = sub_by_name.get(sub_name.lower().strip())
                if not subsidy_id:
                    errors.append({"row": row_num, "name": name, "message": f"Субсидия не найдена: {sub_name}"})
                    continue

                parent_name = cell(row, "parent_name")
                parent_id = None
                level = 1
                if parent_name:
                    parent_id = created_map.get((subsidy_id, parent_name.lower().strip()))
                    if parent_id is None:
                        # Parent not yet created — defer to next pass
                        still_pending.append((row_num, row))
                        continue
                    # Determine level from parent
                    parent_obj = (await db.execute(
                        select(FeoCategory).where(FeoCategory.id == parent_id)
                    )).scalar_one_or_none()
                    level = (parent_obj.level + 1) if parent_obj else 2
                    if level > 3:
                        errors.append({"row": row_num, "name": name, "message": "Превышен макс. уровень вложенности (3)"})
                        continue

                # Skip duplicate (same subsidy + name)
                if (subsidy_id, name.lower().strip()) in created_map:
                    skipped += 1
                    continue

                cat = FeoCategory(
                    name=name,
                    subsidy_id=subsidy_id,
                    parent_id=parent_id,
                    level=level,
                    code=cell(row, "code"),
                    appendix=cell(row, "appendix"),
                    budget=to_dec(cell(row, "budget")),
                    is_active=to_bool(cell(row, "is_active")),
                )
                db.add(cat)
                await db.flush()  # get cat.id
                created_map[(subsidy_id, name.lower().strip())] = cat.id
                created += 1
            except Exception as e:
                errors.append({"row": row_num, "name": cell(row, "name") or "?", "message": str(e)})
        pending = still_pending

    # Rows still pending after 3 passes → circular or unresolvable parent
    for row_num, row in pending:
        name = cell(row, "name") or "?"
        errors.append({"row": row_num, "name": name, "message": "Родительская категория не найдена"})

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


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


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Check children
    children = (await db.execute(
        select(FeoCategory).where(FeoCategory.parent_id == cat_id).limit(1)
    )).scalar_one_or_none()
    if children:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить категорию: есть дочерние направления. Сначала удалите их."
        )

    # Check linked purchases
    from app.models.purchase import Purchase
    linked = (await db.execute(
        select(Purchase).where(Purchase.feo_category_id == cat_id).limit(1)
    )).scalar_one_or_none()
    if linked:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить категорию: есть связанные закупки."
        )

    await db.delete(cat)
    await db.commit()
    return {"ok": True}
