"""Экспорт плана-графика (plan-graph) субсидии в Excel/.docx.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09-07):
GET .../plan-graph/export (живое дерево ФЭО → .xlsx), GET .../versions/
{version_id:int}/export (снапшот версии → .xlsx), POST .../plan-graph/template
(загрузка .docx-шаблона для export-docx), GET .../plan-graph/export-docx.

`_render_plan_graph_workbook` — общий рендерер книги Excel, используется
обоими export-эндпоинтами этого модуля.

Собственный APIRouter на префиксе /api/subsidies — регистрируется в
app/routes.py рядом с subsidies.router.
"""
import io
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from app.utils.http import content_disposition as _content_disposition

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.models.user import User
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


# ── Plan-Graph Export (Phase 12-04) ───────────────────────────────────────────

TEMPLATE_DIR = "media/plan_graph_templates"


def _render_plan_graph_workbook(tree: list, items: list, meta: dict):
    """
    Common renderer for plan-graph Excel workbook.

    Args:
        tree: recursive list of FeoCategory nodes
              [{id, name, level, code, appendix, budget, planned_amount,
                planned_quantity, unit, children:[...]}]
              If empty — fallback to flat `items` (v1 backward-compat).
        items: flat list of snapshot items (v1 backward-compat)
               [{name, planned_amount, used_amount, residual}]
        meta: dict with keys:
              subsidy_name, subsidy_year (optional), effective_date (str|None),
              version_number (int|None), note (str|None), generated_at (str|None)

    Returns:
        openpyxl.Workbook
    """
    if openpyxl is None:
        raise RuntimeError("openpyxl не установлен")

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    L1_FILL      = PatternFill("solid", fgColor="DBEAFE")
    L1_FONT      = Font(bold=True, size=9)
    L2_FILL      = PatternFill("solid", fgColor="F0F9FF")
    L2_FONT      = Font(bold=True, size=9, color="0C4A6E")
    L3_FILL      = PatternFill("solid", fgColor="F0FDF4")
    L3_FONT      = Font(size=9, color="166534")
    ITEM_FONT    = Font(size=9)
    RED_FONT     = Font(size=9, color="EF4444", bold=True)
    META_FONT    = Font(size=9, italic=True, color="374151")
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center")
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    HEADERS = [
        "№", "Направление расходов", "Тип расходов", "Наименование",
        "Ед.", "Кол-во план", "Плановая сумма, ₽",
        "Фактическая сумма, ₽", "Остаток, ₽",
        "% исполнения", "Исполнитель", "Статус",
    ]
    COL_WIDTHS = [5, 30, 25, 40, 8, 10, 18, 18, 18, 12, 30, 15]
    n_cols = len(HEADERS)
    last_col_letter = chr(64 + n_cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План закупок"

    # ── Title row ─────────────────────────────────────────────────────────────
    subsidy_name = meta.get("subsidy_name", "")
    subsidy_year = meta.get("subsidy_year", "")
    title_text = f"ПЛАН-ГРАФИК — {subsidy_name}"
    if subsidy_year:
        title_text += f" ({subsidy_year})"
    ws.append([title_text] + [""] * (n_cols - 1))
    title_cell = ws.cell(row=1, column=1)
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{last_col_letter}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    # ── Meta info rows (version, effective_date, note, generated_at) ──────────
    meta_start_row = 2
    meta_rows = []
    if meta.get("version_number") is not None:
        meta_rows.append(f"Версия: {meta['version_number']}")
    if meta.get("effective_date"):
        meta_rows.append(f"Дата редакции: {meta['effective_date']}")
    if meta.get("note"):
        meta_rows.append(f"Примечание: {meta['note']}")
    if meta.get("generated_at"):
        meta_rows.append(f"Сформировано: {meta['generated_at']}")

    for i, mtext in enumerate(meta_rows):
        r = meta_start_row + i
        ws.append([mtext] + [""] * (n_cols - 1))
        cell = ws.cell(row=r, column=1)
        cell.font = META_FONT
        cell.alignment = LEFT_ALIGN
        ws.merge_cells(f"A{r}:{last_col_letter}{r}")
        ws.row_dimensions[r].height = 16

    # ── Column headers ────────────────────────────────────────────────────────
    header_row = meta_start_row + len(meta_rows)
    ws.append(HEADERS)
    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[header_row].height = 32
    ws.freeze_panes = f"A{header_row + 1}"

    row_num = header_row + 1
    seq = 0

    def _write_row(values, fill, font, height=20):
        nonlocal row_num
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            cell.alignment = RIGHT_ALIGN if col_idx >= 6 else LEFT_ALIGN
        ws.row_dimensions[row_num].height = height
        row_num += 1

    if tree:
        # ── Tree mode (schema_version=2) ──────────────────────────────────────
        def _traverse_node(node, direction_name="", type_name=""):
            nonlocal seq
            level = node.get("level", 1)
            name = node.get("name", "")
            code = node.get("code") or ""
            budget = node.get("budget")

            if level == 1:
                direction_name = name
                _write_row(
                    [code, name, "", "", "", "", budget or "", "", "", "", "", ""],
                    L1_FILL, L1_FONT, height=22,
                )
            elif level == 2:
                type_name = name
                _write_row(
                    ["", direction_name, name, "", "", "", budget or "", "", "", "", "", ""],
                    L2_FILL, L2_FONT,
                )
            elif level == 3:
                _write_row(
                    ["", direction_name, type_name, name, "", "", budget or "", "", "", "", "", ""],
                    L3_FILL, L3_FONT,
                )

            for child in node.get("children", []):
                _traverse_node(child, direction_name, type_name)

        for root in tree:
            _traverse_node(root)
    else:
        # ── Flat mode (v1 backward-compat) ─────────────────────────────────────
        for item in items:
            seq += 1
            planned = float(item.get("planned_amount") or 0)
            used = float(item.get("used_amount") or 0)
            residual = float(item.get("residual") or (planned - used))
            pct = round(used / planned * 100) if planned > 0 else 0
            status = "Выполнено" if pct >= 100 else ("В работе" if used > 0 else "Не начато")
            font = RED_FONT if used > planned else ITEM_FONT
            _write_row(
                [
                    seq, "", "", item.get("name", ""),
                    "", "",
                    round(planned, 2), round(used, 2), round(residual, 2),
                    f"{pct}%", "", status,
                ],
                PatternFill(), font,
            )

    return wb


@router.get("/{subsidy_id}/plan-graph/export")
async def export_plan_graph_excel(
    subsidy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export plan-graph as Excel file with full FEO hierarchy (live data)."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase import Purchase as _P
    from app.models.contractor import Contractor as _C

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
        .order_by(FeoCategory.level, FeoCategory.id)
    )).scalars().all()

    feo_items = (await db.execute(
        select(_FPI)
        .join(FeoCategory, _FPI.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(_FPI.is_active == True)
        .order_by(_FPI.id)
    )).scalars().all()

    item_ids = [i.id for i in feo_items]
    used_map: dict[int, float] = {}
    if item_ids:
        used_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                func.coalesce(func.sum(_PI.total_price), 0).label("used"),
            )
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .group_by(_PI.feo_planned_item_id)
        )).all()
        used_map = {r.feo_planned_item_id: float(r.used) for r in used_rows}

    # Status breakdown: sum(PurchaseItem.total_price) per (feo_planned_item_id, Purchase.status)
    # статусы: plan_schedule, work_in_progress → «Запланировано»;
    #          contracted → «Договор»; ordered → «Заказано»;
    #          delivered → «Поставлено»; paid → «Оплачено»
    status_sums_map: dict[int, dict[str, float]] = {}
    if item_ids:
        st_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                _P.status,
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .group_by(_PI.feo_planned_item_id, _P.status)
        )).all()
        for r in st_rows:
            status_sums_map.setdefault(r.feo_planned_item_id, {})[r.status] = float(r.s)

    def _st(item_id: int, *statuses: str) -> float:
        d = status_sums_map.get(item_id, {})
        return sum(d.get(s, 0.0) for s in statuses)

    contractor_map: dict[int, str] = {}
    if item_ids:
        c_rows = (await db.execute(
            select(_PI.feo_planned_item_id, _C.name.label("cname"))
            .join(_P, _PI.purchase_id == _P.id)
            .join(_C, _P.contractor_id == _C.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .distinct()
        )).all()
        for r in c_rows:
            if r.feo_planned_item_id not in contractor_map:
                contractor_map[r.feo_planned_item_id] = r.cname

    # Фактически закупленные позиции (PurchaseItem) по каждой плановой статье —
    # чтобы в выгрузке было видно ЧТО куплено и ПО КАКОЙ ЦЕНЕ, а не только сумма.
    _STATUS_HUMAN = {
        "wishes": "Запланировано", "plan_schedule": "Запланировано",
        "work_in_progress": "Запланировано",
        "contracted": "Договор", "ordered": "Заказано",
        "delivered": "Поставлено", "paid": "Оплачено",
    }
    def _act_number(acc_number, acc_docs) -> str:
        if acc_number:
            return str(acc_number)
        if isinstance(acc_docs, list) and acc_docs:
            first = acc_docs[0]
            if isinstance(first, dict) and first.get("number"):
                return str(first["number"])
        return ""

    purchased_by_item: dict[int, list] = {}
    if item_ids:
        pi_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                _PI.item_name,
                _PI.unit,
                _PI.quantity,
                _PI.unit_price,
                _PI.total_price,
                _PI.contractor_name,
                _P.id.label("purchase_id"),
                _P.status,
                _P.acceptance_doc_number,
                _P.acceptance_docs,
            )
            .join(_P, _PI.purchase_id == _P.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .order_by(_PI.feo_planned_item_id, _PI.id)
        )).all()
        for r in pi_rows:
            purchased_by_item.setdefault(r.feo_planned_item_id, []).append({
                "name": r.item_name or "",
                "unit": r.unit or "",
                "qty": float(r.quantity or 0),
                "unit_price": float(r.unit_price or 0),
                "total": float(r.total_price or 0),
                "contractor": r.contractor_name or "",
                "raw_status": r.status or "",
                "status": _STATUS_HUMAN.get(r.status, r.status or ""),
                "purchase_id": r.purchase_id,
                "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
            })

    # FCAT: закупки часто привязаны к КАТЕГОРИИ (feo_category_id), а не к плановой
    # позиции. Агрегируем факт по категории — иначе колонки факта пустые.
    cat_ids = [c.id for c in cats]
    cat_status_map: dict[int, dict[str, float]] = {}
    cat_contractor_map: dict[int, str] = {}
    cat_monthly_map: dict[int, float] = {}  # факт по закупкам-регулярным (ежемес.) платежам
    purchased_by_cat: dict[int, list] = {}
    # Привязка к категории живёт на ТРЁХ уровнях: PurchaseItem.feo_category_id,
    # Purchase.feo_category_id (так работает вкладка «план vs факт») и через
    # плановую статью (feo_planned_item_id → её категория). Берём coalesce,
    # иначе часть факта выпадает из роллапа.
    _ecat = func.coalesce(_PI.feo_category_id, _P.feo_category_id, _FPI.feo_category_id)
    if cat_ids:
        cst_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                _P.status,
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .group_by(_ecat, _P.status)
        )).all()
        for r in cst_rows:
            cat_status_map.setdefault(r.ecat, {})[r.status] = float(r.s)

        mth_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .where(_P.is_monthly_payment.is_(True))
            .group_by(_ecat)
        )).all()
        for r in mth_rows:
            cat_monthly_map[r.ecat] = float(r.s)

        cpi_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                _PI.feo_planned_item_id,
                _PI.item_name,
                _PI.unit,
                _PI.quantity,
                _PI.unit_price,
                _PI.total_price,
                func.coalesce(_PI.contractor_name, _C.name).label("contractor_name"),
                _P.id.label("purchase_id"),
                _P.status,
                _P.is_monthly_payment,
                _P.monthly_payment_count,
                _P.monthly_payment_amount,
                _P.acceptance_doc_number,
                _P.acceptance_docs,
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_C, _P.contractor_id == _C.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .order_by(_ecat, _PI.id)
        )).all()
        for r in cpi_rows:
            if r.contractor_name and r.ecat not in cat_contractor_map:
                cat_contractor_map[r.ecat] = r.contractor_name
            # Детализацию по категории показываем только для позиций БЕЗ привязки к
            # плановой статье — иначе задвоится со строками под плановой позицией.
            if r.feo_planned_item_id is None:
                purchased_by_cat.setdefault(r.ecat, []).append({
                    "name": r.item_name or "",
                    "unit": r.unit or "",
                    "qty": float(r.quantity or 0),
                    "unit_price": float(r.unit_price or 0),
                    "total": float(r.total_price or 0),
                    "contractor": r.contractor_name or "",
                    "raw_status": r.status or "",
                    "status": _STATUS_HUMAN.get(r.status, r.status or ""),
                    "purchase_id": r.purchase_id,
                    "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
                    "is_monthly": bool(r.is_monthly_payment),
                    "monthly_count": r.monthly_payment_count,
                    "monthly_amount": float(r.monthly_payment_amount or 0),
                })

    # ── Закупки БЕЗ позиций: факт живёт на самой закупке (item_name/суммы) ──
    # Иначе такие закупки полностью выпадают из выгрузки.
    itemless_extra: list[dict] = []      # для «Сводной»
    unlinked_purchases: list[dict] = []  # секция «без категории ФЭО»
    pl_rows = (await db.execute(
        select(
            _P.id.label("purchase_id"), _P.feo_category_id, _P.item_name,
            _P.subject, _P.status,
            _P.planned_quantity, _P.unit, _P.planned_unit_price,
            _P.planned_total_price, _P.final_total_amount,
            _P.acceptance_doc_number, _P.acceptance_docs,
            _P.is_monthly_payment, _P.monthly_payment_count, _P.monthly_payment_amount,
            _P.item_type, _P.is_likely_needed,
            _C.name.label("contractor_name"),
        )
        .outerjoin(_C, _P.contractor_id == _C.id)
        .where(or_(
            _P.feo_category_id.in_(cat_ids or [-1]),
            _P.subsidy_id == subsidy_id,
        ))
        .where(~select(_PI.id).where(_PI.purchase_id == _P.id).exists())
        .order_by(_P.id)
    )).all()
    _cat_id_set = set(cat_ids)
    for r in pl_rows:
        amount = float(r.final_total_amount or r.planned_total_price or 0)
        qty = float(r.planned_quantity or 0)
        d = {
            "name": (r.item_name or r.subject or f"Закупка №{r.purchase_id}"),
            "unit": r.unit or "",
            "qty": qty,
            "unit_price": float(r.planned_unit_price or 0) or (amount / qty if qty else amount),
            "total": amount,
            "contractor": r.contractor_name or "",
            "raw_status": r.status or "",
            "status": _STATUS_HUMAN.get(r.status, r.status or ""),
            "purchase_id": r.purchase_id,
            "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
            "has_act": bool(r.acceptance_doc_number) or bool(
                isinstance(r.acceptance_docs, list) and r.acceptance_docs),
            "is_monthly": bool(r.is_monthly_payment),
            "monthly_count": r.monthly_payment_count,
            "monthly_amount": float(r.monthly_payment_amount or 0),
            "item_type": (r.item_type or "").strip().lower(),
            "is_likely_needed": bool(r.is_likely_needed),
        }
        itemless_extra.append(d)
        if r.feo_category_id in _cat_id_set:
            purchased_by_cat.setdefault(r.feo_category_id, []).append(d)
            if amount:
                m = cat_status_map.setdefault(r.feo_category_id, {})
                st_key = r.status or ""
                m[st_key] = m.get(st_key, 0.0) + amount
                if r.is_monthly_payment:
                    cat_monthly_map[r.feo_category_id] = \
                        cat_monthly_map.get(r.feo_category_id, 0.0) + amount
        else:
            unlinked_purchases.append(d)

    # ── Позиции закупок, привязанных к субсидии ТОЛЬКО через subsidy_id ──────
    # (ни у закупки, ни у позиций нет категории/плановой статьи)
    _ecat_u = func.coalesce(_PI.feo_category_id, _P.feo_category_id, _FPI.feo_category_id)
    upi_rows = (await db.execute(
        select(
            _PI.item_name, _PI.unit, _PI.quantity, _PI.unit_price, _PI.total_price,
            func.coalesce(_PI.contractor_name, _C.name).label("contractor_name"),
            func.coalesce(_PI.item_type, _P.item_type).label("item_type"),
            _P.id.label("purchase_id"), _P.status,
            _P.is_monthly_payment, _P.monthly_payment_count, _P.monthly_payment_amount,
            _P.acceptance_doc_number, _P.acceptance_docs, _P.is_likely_needed,
        )
        .join(_P, _PI.purchase_id == _P.id)
        .outerjoin(_C, _P.contractor_id == _C.id)
        .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
        .where(_P.subsidy_id == subsidy_id)
        .where(_ecat_u.is_(None))
        .order_by(_P.id, _PI.id)
    )).all()
    for r in upi_rows:
        unlinked_purchases.append({
            "name": r.item_name or "",
            "unit": r.unit or "",
            "qty": float(r.quantity or 0),
            "unit_price": float(r.unit_price or 0),
            "total": float(r.total_price or 0),
            "contractor": r.contractor_name or "",
            "raw_status": r.status or "",
            "status": _STATUS_HUMAN.get(r.status, r.status or ""),
            "purchase_id": r.purchase_id,
            "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
            "is_monthly": bool(r.is_monthly_payment),
            "monthly_count": r.monthly_payment_count,
            "monthly_amount": float(r.monthly_payment_amount or 0),
        })

    def _cst(cat_id: int, *statuses: str) -> float:
        d = cat_status_map.get(cat_id, {})
        return sum(d.get(s, 0.0) for s in statuses)

    items_by_cat: dict[int, list] = {}
    for item in feo_items:
        items_by_cat.setdefault(item.feo_category_id, []).append(item)

    # Build live tree for _render_plan_graph_workbook
    def _build_live_tree(all_cats, parent_id=None):
        nodes = []
        for c in all_cats:
            if c.parent_id == parent_id:
                cat_items = items_by_cat.get(c.id, [])
                children = _build_live_tree(all_cats, parent_id=c.id)
                node = {
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "children": children,
                    # live items embedded for leaf rendering
                    "_live_items": cat_items,
                    "_used_map": used_map,
                    "_contractor_map": contractor_map,
                }
                nodes.append(node)
        return nodes

    live_tree = _build_live_tree(list(cats))

    # Use dedicated live-render path (keeps contractor/used columns populated)
    from datetime import datetime as _dt
    meta = {
        "subsidy_name": sub.name,
        "subsidy_year": str(sub.year) if sub.year else "",
        "generated_at": _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Build workbook manually using existing logic (live tree with items)
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    L1_FILL      = PatternFill("solid", fgColor="DBEAFE")
    L1_FONT      = Font(bold=True, size=9)
    L2_FILL      = PatternFill("solid", fgColor="F0F9FF")
    L2_FONT      = Font(bold=True, size=9, color="0C4A6E")
    L3_FILL      = PatternFill("solid", fgColor="F0FDF4")
    L3_FONT      = Font(size=9, color="166534")
    ITEM_FONT    = Font(size=9)
    RED_FONT     = Font(size=9, color="EF4444", bold=True)
    SUB_FONT     = Font(size=8, italic=True, color="6B7280")
    SUB_FILL     = PatternFill("solid", fgColor="FAFAFA")
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center")
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    HEADERS = [
        "№", "Направление расходов", "Тип расходов", "Наименование",
        "Ед.", "Кол-во план", "Бюджет ФЭО, ₽", "Запланировано, ₽",
        "Договор, ₽", "Заказано, ₽", "Поставлено, ₽", "Оплачено, ₽",
        "Фактически (итого), ₽", "Остаток, ₽",
        "% исполнения", "Исполнитель", "Статус",
        "Ежемес. (регуляр.) платежи, ₽",
        "№ акта", "Документы",
    ]
    COL_WIDTHS = [5, 30, 25, 40, 8, 10, 18, 18, 18, 18, 18, 18, 20, 18, 12, 30, 15, 22, 16, 14]

    cats_by_parent: dict = {}
    for c in cats:
        cats_by_parent.setdefault(c.parent_id, []).append(c)

    # Роллап факта/бюджета вверх по дереву: направление (ур.1) и группа (ур.2)
    # показывают суммарные итоги по всем листовым категориям-потомкам.
    # Факт листа берём по feo_category_id (cat_status_map) — это включает все
    # закупки категории, поэтому суммирование по потомкам не задваивается.
    _cat_by_id = {c.id: c for c in cats}
    subtree_map: dict[int, dict] = {}

    def _compute_subtree(cat) -> dict:
        if cat.id in subtree_map:
            return subtree_map[cat.id]
        children = cats_by_parent.get(cat.id, [])
        status_agg: dict[str, float] = {}
        if not children:
            for k, v in cat_status_map.get(cat.id, {}).items():
                status_agg[k] = status_agg.get(k, 0.0) + v
            monthly = cat_monthly_map.get(cat.id, 0.0)
            if cat.budget is not None:
                budget = float(cat.budget)
            else:
                budget = sum(float(it.amount or 0) for it in items_by_cat.get(cat.id, []))
        else:
            budget = 0.0
            monthly = 0.0
            for ch in children:
                r = _compute_subtree(ch)
                for k, v in r["status"].items():
                    status_agg[k] = status_agg.get(k, 0.0) + v
                budget += r["budget"]
                monthly += r["monthly"]
        res = {"status": status_agg, "budget": budget, "monthly": monthly}
        subtree_map[cat.id] = res
        return res

    for c in cats:
        _compute_subtree(c)

    def _sub(cat_id: int, *statuses: str) -> float:
        d = subtree_map.get(cat_id, {}).get("status", {})
        return sum(d.get(s, 0.0) for s in statuses)

    base_url = str(request.base_url).rstrip("/")
    LINK_FONT = Font(size=8, italic=True, color="2563EB", underline="single")

    def _cascade(raw_status: str, total: float):
        """Каскад суммы поставки по стадиям: сумма падает во все столбцы до текущей
        стадии включительно; недостигнутые = 0. Столбцы: Заказано/Поставлено/Оплачено."""
        t = round(total or 0, 2)
        ordered = t if raw_status in ("ordered", "delivered", "paid") else 0
        delivered = t if raw_status in ("delivered", "paid") else 0
        paid = t if raw_status == "paid" else 0
        return ordered, delivered, paid

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План закупок"

    # Заголовок-титул в строке 1 (не через insert_rows — иначе гиперлинки не
    # сдвигаются вместе с ячейками и «съезжают» на строку выше).
    title_cell = ws.cell(row=1, column=1, value=f"ПЛАН-ГРАФИК — {sub.name} ({sub.year})")
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{chr(64 + len(HEADERS))}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[2].height = 32
    ws.freeze_panes = "A3"

    row_num = 3
    seq = 0

    def _write_row(values, fill, font, height=20):
        nonlocal row_num
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            cell.alignment = RIGHT_ALIGN if col_idx >= 6 else LEFT_ALIGN
        ws.row_dimensions[row_num].height = height
        row_num += 1

    def _set_doc_link(purchase_id):
        """Проставить гиперлинк «Открыть» в колонку 20 последней записанной строки —
        ведёт на страницу заказа, где под авторизацией доступны все документы."""
        if not purchase_id:
            return
        cell = ws.cell(row=row_num - 1, column=20)
        cell.value = "Открыть"
        cell.hyperlink = f"{base_url}/orders/{purchase_id}"
        cell.font = LINK_FONT

    E = ""  # пустая ячейка

    def _money_cols(cat_id: int, contractor: str) -> list:
        """Денежные колонки 7..18 из роллапа поддерева по статусам."""
        st = subtree_map.get(cat_id, {})
        budget = st.get("budget", 0.0)
        monthly = st.get("monthly", 0.0)
        plan = _sub(cat_id, "plan_schedule", "work_in_progress", "wishes")
        contract = _sub(cat_id, "contracted")
        ordered = _sub(cat_id, "ordered")
        delivered = _sub(cat_id, "delivered")
        paid = _sub(cat_id, "paid")
        used = plan + contract + ordered + delivered + paid
        resid = budget - used

        def _nz(v):
            return round(v, 2) if abs(v) > 0.005 else E

        return [
            round(budget, 2) if budget else E,
            _nz(plan), _nz(contract), _nz(ordered), _nz(delivered), _nz(paid),
            _nz(used),
            round(resid, 2) if (budget or abs(used) > 0.005) else E,
            (f"{round(used / budget * 100)}%" if budget > 0 else E),
            contractor, E,
            _nz(monthly),
        ]

    def _traverse(cat, direction_name="", type_name=""):
        nonlocal seq
        if cat.level == 1:
            direction_name = cat.name
            _write_row(
                [cat.code or "", cat.name, E, E, E, E] + _money_cols(cat.id, ""),
                L1_FILL, L1_FONT, height=22
            )
        elif cat.level == 2:
            type_name = cat.name
            _write_row(
                [E, direction_name, cat.name, E, E, E] + _money_cols(cat.id, ""),
                L2_FILL, L2_FONT
            )
        elif cat.level == 3:
            _write_row(
                [E, direction_name, type_name, cat.name, E, E]
                + _money_cols(cat.id, cat_contractor_map.get(cat.id, "")),
                L3_FILL, L3_FONT
            )
            # Под-строки: закупки, привязанные напрямую к категории (без плановой статьи).
            # По каждой фактической позиции — цена, кол-во, сумма, контрагент, № акта,
            # ссылка на документы + каскад Заказано/Поставлено/Оплачено.
            cat_purchases = purchased_by_cat.get(cat.id, [])
            cat_ord = cat_del = cat_paid = 0.0
            for pi in cat_purchases:
                price_note = f"    └ {pi['name']} — {round(pi['unit_price'], 2):,.2f} ₽/ед."
                status_txt = pi["status"]
                monthly_val = ""
                if pi.get("is_monthly"):
                    cnt = pi.get("monthly_count")
                    amt = pi.get("monthly_amount") or 0
                    status_txt = f"{status_txt} · ежемес." + (f" ×{cnt}" if cnt else "")
                    monthly_val = round(pi["total"], 2)
                    if amt:
                        price_note += f" ({round(amt, 2):,.2f} ₽/мес)"
                ord_a, del_a, paid_a = _cascade(pi["raw_status"], pi["total"])
                cat_ord += ord_a; cat_del += del_a; cat_paid += paid_a
                _write_row(
                    [
                        "", "", "", price_note,
                        pi["unit"], round(pi["qty"], 3),
                        "", "", "",
                        ord_a, del_a, paid_a,
                        round(pi["total"], 2), "",
                        "", pi["contractor"], status_txt,
                        monthly_val, pi["act_number"],
                    ],
                    SUB_FILL, SUB_FONT, height=16
                )
                _set_doc_link(pi["purchase_id"])
            if cat_purchases:
                _write_row(
                    [
                        "", "", "", "    Итого по факту:",
                        "", "",
                        "", "", "",
                        round(cat_ord, 2), round(cat_del, 2), round(cat_paid, 2),
                        "", "", "", "", "", "",
                    ],
                    SUB_FILL, Font(size=8, bold=True, color="374151"), height=16
                )
            for item in items_by_cat.get(cat.id, []):
                seq += 1
                feo_budget = float(item.amount or 0)
                plan_sum = _st(item.id, "plan_schedule", "work_in_progress", "wishes")
                contract_sum = _st(item.id, "contracted")
                ordered_sum = _st(item.id, "ordered")
                delivered_sum = _st(item.id, "delivered")
                paid_sum = _st(item.id, "paid")
                used = used_map.get(item.id, 0.0)
                residual = feo_budget - used
                pct = round(used / feo_budget * 100) if feo_budget > 0 else 0
                contractor = contractor_map.get(item.id, "")
                status = "Выполнено" if pct >= 100 else ("В работе" if used > 0 else "Не начато")
                font = RED_FONT if used > feo_budget else ITEM_FONT
                _write_row(
                    [
                        seq, direction_name, type_name, item.name,
                        item.unit or "", float(item.quantity or 0),
                        round(feo_budget, 2), round(plan_sum, 2),
                        round(contract_sum, 2), round(ordered_sum, 2),
                        round(delivered_sum, 2), round(paid_sum, 2),
                        round(used, 2), round(residual, 2),
                        f"{pct}%", contractor, status,
                    ],
                    PatternFill(), font
                )
                # Под-строки: реально закупленные позиции (что, по какой цене, № акта,
                # каскад статусов Заказано/Поставлено/Оплачено + ссылка на документы)
                for pi in purchased_by_item.get(item.id, []):
                    price_note = f"    └ {pi['name']} — {round(pi['unit_price'], 2):,.2f} ₽/ед."
                    ord_a, del_a, paid_a = _cascade(pi["raw_status"], pi["total"])
                    _write_row(
                        [
                            "", "", "", price_note,
                            pi["unit"], round(pi["qty"], 3),
                            "", "", "",
                            ord_a, del_a, paid_a,
                            round(pi["total"], 2), "",
                            "", pi["contractor"], pi["status"],
                            "", pi["act_number"],
                        ],
                        SUB_FILL, SUB_FONT, height=16
                    )
                    _set_doc_link(pi["purchase_id"])

        for child in cats_by_parent.get(cat.id, []):
            _traverse(child, direction_name, type_name)

    for root in cats_by_parent.get(None, []):
        _traverse(root)

    # ── Секция: закупки, привязанные к субсидии, но без категории ФЭО ────────
    if unlinked_purchases:
        _write_row(
            ["", "Закупки по субсидии без привязки к категории ФЭО", "", "", "", ""]
            + [""] * 12,
            L1_FILL, L1_FONT, height=22
        )
        u_ord = u_del = u_paid = 0.0
        for pi in unlinked_purchases:
            price_note = f"    └ {pi['name']} — {round(pi['unit_price'], 2):,.2f} ₽/ед."
            status_txt = pi["status"]
            monthly_val = ""
            if pi.get("is_monthly"):
                cnt = pi.get("monthly_count")
                amt = pi.get("monthly_amount") or 0
                status_txt = f"{status_txt} · ежемес." + (f" ×{cnt}" if cnt else "")
                monthly_val = round(pi["total"], 2)
                if amt:
                    price_note += f" ({round(amt, 2):,.2f} ₽/мес)"
            ord_a, del_a, paid_a = _cascade(pi["raw_status"], pi["total"])
            u_ord += ord_a; u_del += del_a; u_paid += paid_a
            _write_row(
                [
                    "", "", "", price_note,
                    pi["unit"], round(pi["qty"], 3),
                    "", "", "",
                    ord_a, del_a, paid_a,
                    round(pi["total"], 2), "",
                    "", pi["contractor"], status_txt,
                    monthly_val, pi["act_number"],
                ],
                SUB_FILL, SUB_FONT, height=16
            )
            _set_doc_link(pi["purchase_id"])
        _write_row(
            [
                "", "", "", "    Итого по факту:",
                "", "",
                "", "", "",
                round(u_ord, 2), round(u_del, 2), round(u_paid, 2),
                "", "", "", "", "", "",
            ],
            SUB_FILL, Font(size=8, bold=True, color="374151"), height=16
        )

    # ── Лист «Сводная»: деньги по Товары/Услуги × корзины обязательств ────────
    def _empty_buckets():
        return {"paid": 0.0, "delivered": 0.0, "accepted_unpaid": 0.0,
                "planned": 0.0, "monthly": 0.0, "likely": 0.0, "total": 0.0}

    summary = {"услуга": _empty_buckets(), "товар": _empty_buckets()}
    _planned_statuses = ("wishes", "plan_schedule", "work_in_progress", "contracted", "ordered")
    sum_rows = (await db.execute(
        select(
            func.coalesce(_PI.item_type, _P.item_type).label("item_type"),
            _PI.total_price,
            _P.status,
            _P.acceptance_doc_number,
            _P.acceptance_docs,
            _P.is_monthly_payment,
            _P.is_likely_needed,
        )
        .join(_P, _PI.purchase_id == _P.id)
        .where(or_(
            func.coalesce(_PI.feo_category_id, _P.feo_category_id).in_(cat_ids or [-1]),
            _PI.feo_planned_item_id.in_(item_ids or [-1]),
            _P.subsidy_id == subsidy_id,
        ))
    )).all()
    for r in sum_rows:
        key = "услуга" if (r.item_type or "").strip().lower() == "услуга" else "товар"
        b = summary[key]
        amt = float(r.total_price or 0)
        st = r.status or ""
        b["total"] += amt
        if st == "paid":
            b["paid"] += amt
        if st == "delivered":
            b["delivered"] += amt
        has_act = bool(r.acceptance_doc_number) or bool(
            isinstance(r.acceptance_docs, list) and r.acceptance_docs)
        if has_act and st != "paid":
            b["accepted_unpaid"] += amt
        if st in _planned_statuses:
            b["planned"] += amt
        if r.is_monthly_payment:
            b["monthly"] += amt
        if r.is_likely_needed:
            b["likely"] += amt

    # Закупки без позиций — их суммы живут на самой закупке
    for d in itemless_extra:
        key = "услуга" if d["item_type"] == "услуга" else "товар"
        b = summary[key]
        amt = d["total"]
        st = d["raw_status"]
        b["total"] += amt
        if st == "paid":
            b["paid"] += amt
        if st == "delivered":
            b["delivered"] += amt
        if d["has_act"] and st != "paid":
            b["accepted_unpaid"] += amt
        if st in _planned_statuses:
            b["planned"] += amt
        if d["is_monthly"]:
            b["monthly"] += amt
        if d["is_likely_needed"]:
            b["likely"] += amt

    sm = wb.create_sheet("Сводная", 0)
    SUM_HEADERS = [
        "Категория",
        "Оплаченные+поставленные (треб. оплата), ₽",
        "Оплаченные, ₽",
        "Принятые, не оплаченные, ₽",
        "Планируемые, ₽",
        "Ежемесячные оплаты, ₽",
        "Скорее всего понадобятся, ₽",
        "Всего, ₽",
    ]
    SUM_WIDTHS = [16, 28, 18, 24, 20, 22, 26, 20]
    sm_title = sm.cell(row=1, column=1, value=f"СВОДНАЯ — {sub.name} ({sub.year})")
    sm_title.font = Font(bold=True, size=12, color="1E3A5F")
    sm.merge_cells(f"A1:{chr(64 + len(SUM_HEADERS))}1")
    sm_title.alignment = CENTER_ALIGN
    sm.row_dimensions[1].height = 28
    for ci, (h, w) in enumerate(zip(SUM_HEADERS, SUM_WIDTHS), 1):
        cell = sm.cell(row=2, column=ci, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        sm.column_dimensions[cell.column_letter].width = w
    sm.row_dimensions[2].height = 34

    _order = ["delivered", "paid", "accepted_unpaid", "planned", "monthly", "likely", "total"]

    def _sum_row(sm_row, label, b, fill, font):
        sm.cell(row=sm_row, column=1, value=label)
        for j, k in enumerate(_order, 2):
            c = sm.cell(row=sm_row, column=j, value=round(b[k], 2) if b[k] else "")
            c.number_format = "#,##0.00"
            c.alignment = RIGHT_ALIGN
            c.border = THIN_BORDER
        lc = sm.cell(row=sm_row, column=1)
        lc.fill = fill; lc.font = font; lc.border = THIN_BORDER
        for j in range(2, 9):
            sm.cell(row=sm_row, column=j).fill = fill

    _sum_row(3, "Услуги", summary["услуга"], L2_FILL, L2_FONT)
    _sum_row(4, "Товары", summary["товар"], L3_FILL, L3_FONT)
    total_b = {k: summary["услуга"][k] + summary["товар"][k] for k in _empty_buckets()}
    _sum_row(5, "ИТОГО", total_b, L1_FILL, Font(bold=True, size=10))
    sm.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"План_график_{safe_name}_{sub.year}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/{subsidy_id}/plan-graph/versions/{version_id:int}/export")
async def export_plan_graph_version_excel(
    subsidy_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a specific plan-graph version snapshot as Excel."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from datetime import datetime as _dt

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    ver = (await db.execute(
        select(_PGV).where(
            _PGV.id == version_id,
            _PGV.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if not ver:
        raise HTTPException(404, "Версия плана закупок не найдена")

    snap = ver.snapshot or {}
    tree = snap.get("tree", [])
    flat_items = snap.get("items", [])

    eff_date = ver.effective_date.isoformat() if ver.effective_date else (
        snap.get("effective_date") or None
    )
    created_at_str = ver.created_at.strftime("%Y-%m-%d %H:%M UTC") if ver.created_at else None

    meta = {
        "subsidy_name": sub.name,
        "subsidy_year": str(sub.year) if sub.year else "",
        "version_number": ver.version_number,
        "effective_date": eff_date,
        "note": ver.note,
        "generated_at": created_at_str,
    }

    wb = _render_plan_graph_workbook(tree, flat_items, meta)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    date_part = (eff_date or (ver.created_at.strftime("%Y-%m-%d") if ver.created_at else "nodate"))
    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:30]
    filename = f"Субсидия_{subsidy_id}_план_v{ver.version_number}_{date_part}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
@router.post("/{subsidy_id}/plan-graph/template")
async def upload_plan_graph_template(
    subsidy_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Upload a .docx Word template for this subsidy's plan-graph export."""
    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Только .docx файлы поддерживаются")

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    dest = os.path.join(TEMPLATE_DIR, f"subsidy_{subsidy_id}.docx")
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return {"ok": True, "template_path": dest, "message": "Шаблон загружен"}


@router.get("/{subsidy_id}/plan-graph/export-docx")
async def export_plan_graph_docx(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fill the uploaded .docx template via docxtpl and return the filled document."""
    if DocxTemplate is None:
        raise HTTPException(500, "docxtpl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    template_path = os.path.join(TEMPLATE_DIR, f"subsidy_{subsidy_id}.docx")
    if not os.path.exists(template_path):
        raise HTTPException(404, "Шаблон не загружен. Загрузите через POST /plan-graph/template")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from datetime import datetime as _dt

    latest_ver = (await db.execute(
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(1)
    )).scalar_one_or_none()

    if latest_ver and latest_ver.snapshot:
        snap = latest_ver.snapshot
        items_ctx = snap.get("items", [])
        total_planned = snap.get("total_planned", 0)
        total_used = snap.get("total_used", 0)
    else:
        items_ctx = []
        total_planned = 0.0
        total_used = 0.0

    context = {
        "subsidy_name": sub.name,
        "subsidy_year": sub.year,
        "items": items_ctx,
        "total_planned": f"{total_planned:,.2f}",
        "total_used": f"{total_used:,.2f}",
        "total_residual": f"{total_planned - total_used:,.2f}",
        "export_date": _dt.now().strftime("%d.%m.%Y"),
    }

    doc = DocxTemplate(template_path)
    doc.render(context)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"План_график_{safe_name}_{sub.year}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
