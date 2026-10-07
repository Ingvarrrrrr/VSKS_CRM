"""Purchase export router — Excel export of purchases.

Handles:
  GET  /api/purchases/export/columns   — list available Excel export columns
  GET  /api/purchases/export/excel     — stream .xlsx export of purchases

ALL_EXPORT_COLUMNS, DEFAULT_EXPORT_COLUMNS and _get_cell_value() now live in
app/services/purchase_export_cells.py (ПРАВИЛО №6, 07.10.2026 — единственная
реализация, переиспользуемая также экспортом плана-графика субсидии); здесь
только re-export под историческими именами so existing call sites that still
import them from this module keep working unchanged.
The *_LABELS dictionaries themselves (Правило №6, single source of truth for
status/method/basis/contract-type labels) live in app/services/dictionaries.py;
here they are re-imported under their historical `_FOO_LABELS` names so that
existing call sites (purchases.py, wishes.py, feo_planned_items.py,
purchase_items_edit.py, services/purchase_summary.py,
services/wish_distribution.py) keep importing them from this module unchanged.
See also GET /api/dictionaries/purchase (app/routers/dictionaries.py) — the
same values, exposed to the frontend.

Import-template and import endpoints were split out of this module into
purchase_import_template.py and purchase_import.py (refactor, 2026-09;
originally this file also handled GET /import/template, POST /import and
POST /import/preview).
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from datetime import datetime
from urllib.parse import quote

from app.database import get_db
from app.models.purchase import Purchase
from app.utils.text import normalize_feo_name
from app.utils.numbers import to_decimal
from app.auth.jwt import get_current_user
from app.services.dictionaries import (
    PURCHASE_METHOD_LABELS as _PURCHASE_METHOD_LABELS,
    PURCHASE_BASIS_LABELS as _PURCHASE_BASIS_LABELS,
    CONTRACT_TYPE_LABELS as _CONTRACT_TYPE_LABELS,
    STATUS_LABELS as _STATUS_LABELS,
    SUBSTATUS_LABELS as _SUBSTATUS_LABELS,
)
from app.services.item_forms import ITEM_FORMS, item_form_for_purchase
from app.services.item_form_summary import item_form_summary, _fmt_datetime
# ПРАВИЛО №6 (07.10.2026): реестр столбцов, извлечение значения ячейки и сборка
# справочников-ctx — единая реализация в app.services.purchase_export_cells,
# переиспользуемая также экспортом плана-графика субсидии (группа «Договор и
# оплата», app/services/plan_graph_export_data.py). Здесь только импорт —
# поведение экспорта закупок не изменилось.
from app.services.purchase_export_cells import (
    ALL_EXPORT_COLUMNS,
    DEFAULT_EXPORT_COLUMNS,
    get_cell_value as _get_cell_value,
    build_purchase_export_ctx,
)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])

# ---------------------------------------------------------------------------
# item-forms-accommodation-transport.md, шаг 4: закупки со спец-формой позиции
# («Проживание»/«Перевозки автобусом», см. app.services.item_forms) получают
# в экспорте доп. колонки полей формы + колонку с человекочитаемым описанием.
# Обычные закупки (item_form=None) — колонки не добавляются вовсе, поведение
# как было (регресс-риск, см. план шаг 5).
# ---------------------------------------------------------------------------

def _representative_item(p: Purchase):
    """Позиция закупки для чтения extra_attrs — спец-формы (в текущей модели,
    см. план item-forms-accommodation-transport.md, раздел «Модель») задаются
    на закупку целиком, представитель — первая позиция ТЗ."""
    items = getattr(p, "items", None) or []
    return items[0] if items else None


def _format_form_field(item, field: dict):
    """Значение одного поля спец-формы для экспорта — подписи те же, что в
    реестре ITEM_FORMS (Правило №6, единый источник состава полей)."""
    extra = getattr(item, "extra_attrs", None) if item else None
    value = (extra or {}).get(field["key"])
    if value in (None, ""):
        return ""
    field_type = field.get("type")
    if field_type in ("select", "switch"):
        options = {opt["value"]: opt["label"] for opt in field.get("options", [])}
        return options.get(value, value)
    if field_type == "number":
        try:
            f = float(value)
            return int(f) if f == int(f) else f
        except (TypeError, ValueError):
            return value
    if field_type == "datetime":
        return _fmt_datetime(value)
    return value


def _build_item_form_columns(purchases: list) -> tuple[dict[int, str | None], list[tuple]]:
    """(item_forms_by_purchase_id, extra_col_defs).

    extra_col_defs — список (col_key, header, item_form, field) для КАЖДОЙ
    спец-формы, реально встретившейся среди экспортируемых закупок (порядок —
    как в ITEM_FORMS), плюс финальная колонка "form_summary" (None field), если
    хотя бы одна закупка со спец-формой попала в выгрузку."""
    item_forms_by_id = {p.id: item_form_for_purchase(p) for p in purchases}
    present = {f for f in item_forms_by_id.values() if f}
    extra_col_defs: list[tuple] = []
    if not present:
        return item_forms_by_id, extra_col_defs
    for form_code, form_def in ITEM_FORMS.items():
        if form_code not in present:
            continue
        for field in form_def["fields"]:
            col_key = f"{form_code}__{field['key']}"
            header = f"{form_def['label']}: {field['label']}"
            extra_col_defs.append((col_key, header, form_code, field))
    extra_col_defs.append(("form_summary", "Описание позиции (форма)", None, None))
    return item_forms_by_id, extra_col_defs


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/export/columns")
async def get_export_columns(_=Depends(get_current_user)):
    """Return available export column definitions."""
    return [
        {"key": k, "label": v["label"], "group": v["group"]}
        for k, v in ALL_EXPORT_COLUMNS.items()
    ]


@router.get("/export/excel")
async def export_purchases_to_excel(
    subsidy_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    columns: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    col_keys = (
        [k.strip() for k in columns.split(",") if k.strip() in ALL_EXPORT_COLUMNS]
        if columns else DEFAULT_EXPORT_COLUMNS
    )
    if not col_keys:
        col_keys = DEFAULT_EXPORT_COLUMNS

    q = select(Purchase).order_by(Purchase.id.desc())
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        q = q.where(Purchase.status == status)
    purchases = (await db.execute(q)).scalars().all()

    ctx = await build_purchase_export_ctx(db, purchases)

    # item-forms-accommodation-transport.md, шаг 4: доп. колонки только если
    # среди выгружаемых закупок есть хоть одна со спец-формой позиции —
    # иначе набор колонок побайтово тот же, что и раньше.
    item_forms_by_id, extra_col_defs = _build_item_form_columns(purchases)

    wb = Workbook()
    ws = wb.active
    ws.title = "Закупки"

    col_headers = [ALL_EXPORT_COLUMNS[k]["label"] for k in col_keys] + [c[1] for c in extra_col_defs]
    ws.append(col_headers)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    empty_counts = {k: 0 for k in col_keys}
    for p in purchases:
        row = []
        for k in col_keys:
            val = _get_cell_value(k, p, ctx)
            row.append(val)
            if val == "" or val is None:
                empty_counts[k] += 1
        if extra_col_defs:
            p_form = item_forms_by_id.get(p.id)
            rep_item = _representative_item(p) if p_form else None
            for col_key, _header, form_code, field in extra_col_defs:
                if col_key == "form_summary":
                    row.append(item_form_summary(rep_item, p_form) if p_form and rep_item is not None else "")
                elif p_form == form_code and rep_item is not None:
                    row.append(_format_form_field(rep_item, field))
                else:
                    row.append("")
        ws.append(row)

    for i, header in enumerate(col_headers, 1):
        col_letter = ws.cell(1, i).column_letter
        ws.column_dimensions[col_letter].width = max(len(header) + 2, 12)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"Закупки_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    missing = []
    if len(purchases) >= 5:
        for k in col_keys:
            if empty_counts[k] / len(purchases) > 0.8:
                missing.append(ALL_EXPORT_COLUMNS[k]["label"])

    resp_headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='-_.~')}",
        "Access-Control-Expose-Headers": "X-Missing-Columns",
    }
    if missing:
        # HTTP-заголовки кодируются latin-1; кириллица в названиях колонок → percent-encode.
        resp_headers["X-Missing-Columns"] = quote(",".join(missing[:5]))

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=resp_headers,
    )



# ---------------------------------------------------------------------------
# Backward-compat aliases: a couple of private helpers used to live in this
# module (before the import/template code was split out) and some tests /
# call sites still import them from here. Both just alias the single
# app.utils implementation (Правило №6) — no separate logic lives here.
# ---------------------------------------------------------------------------
_norm_feo = normalize_feo_name
_to_dec = to_decimal
