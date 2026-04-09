from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
    current_user=Depends(require_role(*ADMIN_ROLES)),
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
    current_user=Depends(require_role(*ADMIN_ROLES)),
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
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "unit": c.unit,
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
        planned_quantity=category_data.planned_quantity,
        planned_amount=category_data.planned_amount,
    )
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category


@router.get("/import/template")
async def download_feo_template():
    """Шаблон Excel для импорта категорий ФЭО (5 уровней: A-G иерархия+кол-во, H-K плановые позиции, L-O атрибуты)."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Категории ФЭО"
    headers = [
        "Субсидия",                                      # A
        "Уровень 2 (Направление расходов по ФЭО)",       # B
        "Кол-во (Ур.2)",                                 # C
        "Ед. изм. (Ур.2)",                               # D
        "Плановая стоимость за ед. (Ур.2)",                       # E  ← NEW
        "Уровень 3 (Тип расходов по ФЭО)",               # F
        "Кол-во (Ур.3)",                                 # G
        "Ед. изм. (Ур.3)",                               # H
        "Плановая стоимость за ед. (Ур.3)",                       # I  ← NEW
        "Уровень 4 (Конкретизированный)",                # J
        "Кол-во (Ур.4)",                                 # K
        "Ед. изм. (Ур.4)",                               # L
        "Плановая стоимость за ед. (Ур.4)",                       # M  ← NEW
        "Уровень 5 (Плановый товар/услуга)",             # N
        "Количество (Ур.5)",                             # O
        "Ед. измерения (Ур.5)",                          # P
        "Плановая стоимость за ед. (Ур.5)",                       # Q
        "Код",                                           # R
        "Приложение",                                    # S
        "Финансирование",                                # T
        "Активна",                                       # U
    ]
    ws.append(headers)

    # Цветовое кодирование заголовков
    fill_cat  = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")   # синий — категории + их кол-во
    fill_item = PatternFill(start_color="059669", end_color="059669", fill_type="solid")   # зелёный — позиции уровня 5
    fill_attr = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")  # фиолетовый — атрибуты
    font_w = Font(color="FFFFFF", bold=True, size=10)

    for i, cell in enumerate(ws[1], start=1):
        if i <= 13:
            cell.fill = fill_cat
        elif i <= 17:
            cell.fill = fill_item
        else:
            cell.fill = fill_attr
        cell.font = font_w
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 52

    # Пример: Ур.2 с общим количеством 500 компл., Ур.4 с кол-вом 6 шт
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "500", "компл.", "", "Техническое оснащение штаба", "", "", "", "Закупка компьютеров", "6", "шт", "", "", "", "", "", "01.01.01", "Прил. 1", "2000000", "да"])
    # Пример: категория + плановые позиции уровня 5
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "500", "компл.", "", "Техническое оснащение штаба", "", "", "", "Закупка компьютеров", "6", "шт", "", "Ноутбук HP 15 Intel i5", "3", "шт", "150000", "01.01.01", "Прил. 1", "2000000", "да"])
    ws.append(["ФАДМ_2026", "Техническое оснащение штаба", "500", "компл.", "", "Техническое оснащение штаба", "", "", "", "Закупка компьютеров", "6", "шт", "", "Монитор Dell 24\"", "3", "шт", "90000", "01.01.01", "Прил. 1", "", "да"])
    ws.append(["ФАДМ_2026", "Организация мероприятий", "", "", "", "Слёт студентов-спасателей", "102", "чел.", "", "Услуги по организации", "", "", "", "Услуга проживания участников", "100", "чел.", "3000000", "02.01.01", "Прил. 2", "3000000", "да"])
    ws.append(["ФАДМ_2026", "Организация мероприятий", "", "", "", "Слёт студентов-спасателей", "102", "чел.", "", "Услуги по организации", "", "", "", "Услуга логистики участников", "2", "рейс", "500000", "02.01.02", "Прил. 2", "", "да"])

    # Комментарий в строке 7
    hints = [
        "← Точное название как в системе",
        "← Направление расходов (создаётся если нет)",
        "← Кол-во для Ур.2 (необязательно)",
        "← Ед. изм. Ур.2 (шт, компл...)",
        "← Плановая стоимость за ед. для Ур.2 (руб.)",
        "← Тип расходов (если пусто — атрибуты к Ур.2)",
        "← Кол-во для Ур.3 (необязательно)",
        "← Ед. изм. Ур.3 (шт, кг...)",
        "← Плановая стоимость за ед. для Ур.3 (руб.)",
        "← Конкретизированный (если пусто — к Ур.3)",
        "← Кол-во для Ур.4 (необязательно)",
        "← Ед. изм. Ур.4 (шт, услуга...)",
        "← Плановая стоимость за ед. для Ур.4 (руб.)",
        "← Плановый товар/услуга (необязательно)",
        "← Кол-во Ур.5 (необязательно)",
        "← Ед. изм. (шт, кг, услуга...)",
        "← Плановая стоимость за ед. позиции",
        "← Код категории",
        "← Номер приложения",
        "← Бюджет категории",
        "← да/нет",
    ]
    for col, hint in enumerate(hints, start=1):
        ws.cell(7, col).value = hint
        ws.cell(7, col).font = Font(italic=True, color="888888", size=8)

    for i, w in enumerate([18, 42, 12, 14, 16, 42, 12, 14, 16, 45, 12, 14, 16, 45, 12, 14, 18, 10, 12, 18, 10], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=feo_categories_template.xlsx"})


@router.post("/import-preview")
async def feo_import_preview(
    file: UploadFile = File(...),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    """Read Excel/DOCX file and return headers + sample rows for column mapping."""
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".docx", ".doc", ".pdf")):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .docx, .pdf")

    content = await file.read()

    _FEO_HINTS = (
        "субсидия", "наименован", "направлен", "расходов", "уровень",
        "код", "финансирован", "количеств", "ед. изм", "ед.изм",
        "активн", "приложен", "бюджет", "плановый", "тип расх",
    )

    def _detect_hdr(rows):
        best_score, best_idx = 0, 0
        for ri, row in enumerate(rows[:20]):
            norm = [str(h).strip().lower() if h is not None else "" for h in row]
            score = sum(1 for h in norm if h and any(x in h for x in _FEO_HINTS))
            if score > best_score:
                best_score = score
                best_idx = ri
        return best_idx

    try:
        # ── PDF ──
        if fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь таблицы из PDF")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "PDF", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── DOCX ──
        if fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
            if not all_rows:
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        all_rows.append([text])
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь данные из документа")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "Document", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── XLS ──
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            sheets = []
            for sheet_name in wb_xls.sheet_names():
                ws_xls = wb_xls.sheet_by_name(sheet_name)
                all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": ws_xls.nrows - hdr_idx - 1, "header_row_offset": hdr_idx})

        # ── XLSX ──
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            sheets = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                all_rows = list(ws.iter_rows(values_only=True))
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": len(all_rows) - hdr_idx - 1, "header_row_offset": hdr_idx})
            wb.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}


async def _do_feo_import(
    rows: list,
    c_subsidy: int | None,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
    c_lvl5: int | None,
    c_qty: int | None,
    c_unit: int | None,
    c_item_amt: int | None,
    c_code: int | None,
    c_appendix: int | None,
    c_budget: int | None,
    c_active: int | None,
    db: AsyncSession,
    c_qty_lvl2: int | None = None,
    c_qty_lvl3: int | None = None,
    c_qty_lvl4: int | None = None,
    c_unit_lvl2: int | None = None,
    c_unit_lvl3: int | None = None,
    c_unit_lvl4: int | None = None,
    c_amt_lvl2: int | None = None,
    c_amt_lvl3: int | None = None,
    c_amt_lvl4: int | None = None,
) -> dict:
    """Core import logic shared by /import and /import-mapped endpoints."""

    if c_subsidy is None or c_lvl2 is None:
        raise HTTPException(400, "Не найдены обязательные столбцы: 'Субсидия' и 'Уровень 2 (Направление расходов)'")

    def get_cell(row: tuple, col: int | None) -> str | None:
        if col is None or col < 0 or col >= len(row): return None
        v = row[col]
        return str(v).strip() if v is not None else None

    def to_bool(v: str | None) -> bool:
        if v is None: return True
        return v.lower() in ("да", "yes", "true", "1", "+")

    def to_dec(v: str | None):
        if not v: return None
        s = str(v).strip()
        if not s or s in ('-', '—', '–', 'None', 'null', 'н/д', 'N/A'):
            return None
        # Remove currency symbols, spaces, non-breaking spaces
        s = s.replace(" ", "").replace("\xa0", "").replace("\u202f", "")
        s = s.replace("₽", "").replace("руб", "").replace("р.", "").replace("р", "")
        s = s.replace(",", ".")
        # Remove trailing dots
        s = s.rstrip(".")
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            return None

    from app.models.subsidy import Subsidy
    sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    sub_by_name = {s.name.lower().strip(): s.id for s in sub_rows}

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

    for row_num, row in enumerate(rows, start=2):
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

        lvl3_name = get_cell(row, c_lvl3)
        lvl4_name = get_cell(row, c_lvl4)
        lvl5_name = get_cell(row, c_lvl5)

        code      = get_cell(row, c_code)
        appendix  = get_cell(row, c_appendix)
        budget    = to_dec(get_cell(row, c_budget))
        is_active = to_bool(get_cell(row, c_active))

        item_qty    = to_dec(get_cell(row, c_qty))
        item_unit   = get_cell(row, c_unit)
        item_amount = to_dec(get_cell(row, c_item_amt))

        qty_lvl2 = to_dec(get_cell(row, c_qty_lvl2)) if c_qty_lvl2 is not None else None
        qty_lvl3 = to_dec(get_cell(row, c_qty_lvl3)) if c_qty_lvl3 is not None else None
        qty_lvl4 = to_dec(get_cell(row, c_qty_lvl4)) if c_qty_lvl4 is not None else None
        unit_lvl2 = get_cell(row, c_unit_lvl2) if c_unit_lvl2 is not None else None
        unit_lvl3 = get_cell(row, c_unit_lvl3) if c_unit_lvl3 is not None else None
        unit_lvl4 = get_cell(row, c_unit_lvl4) if c_unit_lvl4 is not None else None
        amt_lvl2 = to_dec(get_cell(row, c_amt_lvl2)) if c_amt_lvl2 is not None else None
        amt_lvl3 = to_dec(get_cell(row, c_amt_lvl3)) if c_amt_lvl3 is not None else None
        amt_lvl4 = to_dec(get_cell(row, c_amt_lvl4)) if c_amt_lvl4 is not None else None

        try:
            cat_l1 = await find_or_create(subsidy_id, None, lvl2_name, 1)
            if cat_l1.id and (subsidy_id, None, lvl2_name.lower().strip()) not in {k for k in cat_cache if cat_cache[k] is cat_l1 and cat_cache[k].id == cat_l1.id}:
                created += 1
            if qty_lvl2 is not None and cat_l1.planned_quantity != qty_lvl2:
                cat_l1.planned_quantity = qty_lvl2
            if unit_lvl2 and cat_l1.unit != unit_lvl2:
                cat_l1.unit = unit_lvl2
            if amt_lvl2 is not None and cat_l1.planned_amount != amt_lvl2:
                cat_l1.planned_amount = amt_lvl2
            leaf = cat_l1

            if lvl3_name:
                is_new_l2 = (subsidy_id, cat_l1.id, lvl3_name.lower().strip()) not in cat_cache
                cat_l2 = await find_or_create(subsidy_id, cat_l1.id, lvl3_name, 2)
                if is_new_l2 and cat_l2.id:
                    created += 1
                if qty_lvl3 is not None and cat_l2.planned_quantity != qty_lvl3:
                    cat_l2.planned_quantity = qty_lvl3
                if unit_lvl3 and cat_l2.unit != unit_lvl3:
                    cat_l2.unit = unit_lvl3
                if amt_lvl3 is not None and cat_l2.planned_amount != amt_lvl3:
                    cat_l2.planned_amount = amt_lvl3
                leaf = cat_l2

                if lvl4_name:
                    is_new_l3 = (subsidy_id, cat_l2.id, lvl4_name.lower().strip()) not in cat_cache
                    cat_l3 = await find_or_create(subsidy_id, cat_l2.id, lvl4_name, 3)
                    if is_new_l3 and cat_l3.id:
                        created += 1
                    if qty_lvl4 is not None and cat_l3.planned_quantity != qty_lvl4:
                        cat_l3.planned_quantity = qty_lvl4
                    if unit_lvl4 and cat_l3.unit != unit_lvl4:
                        cat_l3.unit = unit_lvl4
                    if amt_lvl4 is not None and cat_l3.planned_amount != amt_lvl4:
                        cat_l3.planned_amount = amt_lvl4
                    leaf = cat_l3

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

            if lvl5_name and lvl5_name not in ("←", ""):
                from app.models.feo_planned_item import FeoPlannedItem
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


@router.post("/import")
async def import_feo_from_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
    c_qty      = find_col(["количество (ур.5)", "количество ур.5", "кол-во (ур.5)", "кол-во ур.5"])
    c_qty_lvl2 = find_col(["кол-во (ур.2)", "кол-во ур.2", "количество (ур.2)"])
    c_qty_lvl3 = find_col(["кол-во (ур.3)", "кол-во ур.3", "количество (ур.3)"])
    c_qty_lvl4 = find_col(["кол-во (ур.4)", "кол-во ур.4", "количество (ур.4)"])
    c_unit_lvl2 = find_col(["ед. изм. (ур.2)", "ед.изм. ур.2", "единица ур.2"])
    c_unit_lvl3 = find_col(["ед. изм. (ур.3)", "ед.изм. ур.3", "единица ур.3"])
    c_unit_lvl4 = find_col(["ед. изм. (ур.4)", "ед.изм. ур.4", "единица ур.4"])
    c_amt_lvl2 = find_col(["плановая сумма (ур.2)", "сумма ур.2", "план.сумма ур.2"])
    c_amt_lvl3 = find_col(["плановая сумма (ур.3)", "сумма ур.3"])
    c_amt_lvl4 = find_col(["плановая сумма (ур.4)", "сумма ур.4"])
    # Fallback: generic qty column if no specific level columns present
    if c_qty is None and c_qty_lvl2 is None and c_qty_lvl3 is None and c_qty_lvl4 is None:
        c_qty = find_col(["количество", "кол-во", "qty"])
    c_unit     = find_col(["ед. изм", "единица изм", "ед.изм"])
    c_item_amt = find_col(["сумма плановая", "сумма (ур.5)", "сумма ур"])
    c_code     = find_col(["код"])
    c_appendix = find_col(["приложение"])
    c_budget   = find_col(["финансирование", "бюджет", "budget"])
    c_active   = find_col(["активна", "активен", "active"])

    return await _do_feo_import(
        rows=rows[1:],
        c_subsidy=c_subsidy, c_lvl2=c_lvl2, c_lvl3=c_lvl3, c_lvl4=c_lvl4,
        c_lvl5=c_lvl5, c_qty=c_qty, c_unit=c_unit, c_item_amt=c_item_amt,
        c_code=c_code, c_appendix=c_appendix, c_budget=c_budget, c_active=c_active,
        c_qty_lvl2=c_qty_lvl2, c_qty_lvl3=c_qty_lvl3, c_qty_lvl4=c_qty_lvl4,
        c_unit_lvl2=c_unit_lvl2, c_unit_lvl3=c_unit_lvl3, c_unit_lvl4=c_unit_lvl4,
        c_amt_lvl2=c_amt_lvl2, c_amt_lvl3=c_amt_lvl3, c_amt_lvl4=c_amt_lvl4,
        db=db,
    )


@router.post("/import-mapped")
async def import_feo_mapped(
    file: UploadFile = File(...),
    sheet_name: str = Query(""),
    header_row_offset: int = Query(0),
    col_subsidy: int = Query(-1),
    col_lvl2: int = Query(-1),
    col_lvl3: int = Query(-1),
    col_lvl4: int = Query(-1),
    col_lvl5: int = Query(-1),
    col_code: int = Query(-1),
    col_appendix: int = Query(-1),
    col_budget: int = Query(-1),
    col_quantity: int = Query(-1),
    col_unit: int = Query(-1),
    col_item_amt: int = Query(-1),
    col_active: int = Query(-1),
    col_qty_lvl2: int = Query(-1),
    col_qty_lvl3: int = Query(-1),
    col_qty_lvl4: int = Query(-1),
    col_unit_lvl2: int = Query(-1),
    col_unit_lvl3: int = Query(-1),
    col_unit_lvl4: int = Query(-1),
    col_amt_lvl2: int = Query(-1),
    col_amt_lvl3: int = Query(-1),
    col_amt_lvl4: int = Query(-1),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    """Импорт категорий ФЭО с пользовательским маппингом столбцов."""
    if col_subsidy < 0 or col_lvl2 < 0:
        raise HTTPException(400, "Не указаны обязательные столбцы: Субсидия и Уровень 2")

    fname = (file.filename or "").lower()
    content = await file.read()

    try:
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            ws_names = wb_xls.sheet_names()
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws_xls = wb_xls.sheet_by_name(target_sheet)
            all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
        elif fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
        elif fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), data_only=True)
            ws_names = wb.sheetnames
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws = wb[target_sheet]
            all_rows = list(ws.iter_rows(values_only=True))
            wb.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    if len(all_rows) <= header_row_offset + 1:
        raise HTTPException(400, "Файл пустой или не содержит данных после строки заголовка")

    data_rows = all_rows[header_row_offset + 1:]

    return await _do_feo_import(
        rows=data_rows,
        c_subsidy=col_subsidy,
        c_lvl2=col_lvl2,
        c_lvl3=col_lvl3 if col_lvl3 >= 0 else None,
        c_lvl4=col_lvl4 if col_lvl4 >= 0 else None,
        c_lvl5=col_lvl5 if col_lvl5 >= 0 else None,
        c_qty=col_quantity if col_quantity >= 0 else None,
        c_unit=col_unit if col_unit >= 0 else None,
        c_item_amt=col_item_amt if col_item_amt >= 0 else None,
        c_code=col_code if col_code >= 0 else None,
        c_appendix=col_appendix if col_appendix >= 0 else None,
        c_budget=col_budget if col_budget >= 0 else None,
        c_active=col_active if col_active >= 0 else None,
        c_qty_lvl2=col_qty_lvl2 if col_qty_lvl2 >= 0 else None,
        c_qty_lvl3=col_qty_lvl3 if col_qty_lvl3 >= 0 else None,
        c_qty_lvl4=col_qty_lvl4 if col_qty_lvl4 >= 0 else None,
        c_unit_lvl2=col_unit_lvl2 if col_unit_lvl2 >= 0 else None,
        c_unit_lvl3=col_unit_lvl3 if col_unit_lvl3 >= 0 else None,
        c_unit_lvl4=col_unit_lvl4 if col_unit_lvl4 >= 0 else None,
        c_amt_lvl2=col_amt_lvl2 if col_amt_lvl2 >= 0 else None,
        c_amt_lvl3=col_amt_lvl3 if col_amt_lvl3 >= 0 else None,
        c_amt_lvl4=col_amt_lvl4 if col_amt_lvl4 >= 0 else None,
        db=db,
    )


@router.get("/export")
async def export_feo_to_excel(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
    cat.planned_quantity = category_data.planned_quantity
    cat.planned_amount = category_data.planned_amount
    cat.unit = category_data.unit
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    # Collect entire subtree
    all_ids = await _collect_subtree_ids(cat_id, db)

    # Block deletion if purchases are linked — return their IDs for navigation
    from app.models.purchase import Purchase
    linked_purchases = (await db.execute(
        select(Purchase.id, Purchase.subject).where(Purchase.feo_category_id.in_(all_ids))
    )).all()
    if linked_purchases:
        purchase_ids = [p.id for p in linked_purchases]
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Нельзя удалить: {len(linked_purchases)} закупок привязано к этой категории.",
                "purchase_ids": purchase_ids,
                "feo_category_ids": all_ids,
            }
        )

    # Nullify FK references in products before deleting
    from app.models.product import Product
    await db.execute(
        Product.__table__.update().where(Product.feo_category_id.in_(all_ids)).values(feo_category_id=None)
    )

    # Nullify FK in purchase_items referencing planned_items of these categories
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase_item import PurchaseItem
    planned_item_ids = (await db.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_(all_ids))
    )).scalars().all()
    if planned_item_ids:
        await db.execute(
            PurchaseItem.__table__.update().where(
                PurchaseItem.feo_planned_item_id.in_(planned_item_ids)
            ).values(feo_planned_item_id=None)
        )

    # Delete planned items explicitly (in case DB lacks CASCADE)
    await db.execute(
        FeoPlannedItem.__table__.delete().where(FeoPlannedItem.feo_category_id.in_(all_ids))
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
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
