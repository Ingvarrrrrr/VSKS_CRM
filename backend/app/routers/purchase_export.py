"""Purchase export/import router — extracted from purchases.py (Phase 16-02).

Handles:
  GET  /api/purchases/export/columns   — list available Excel export columns
  GET  /api/purchases/export/excel     — stream .xlsx export of purchases
  GET  /api/purchases/import/template  — download blank import template
  POST /api/purchases/import           — Scroller-format xlsx import
"""
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from decimal import Decimal
from datetime import datetime
from urllib.parse import quote

from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])

# ---------------------------------------------------------------------------
# Excel export: column registry
# ---------------------------------------------------------------------------

ALL_EXPORT_COLUMNS = {
    "purchase_number":        {"label": "№ п/п",                 "group": "Идентификация"},
    "order_number":           {"label": "Номер заявки",          "group": "Идентификация"},
    "registry_number":        {"label": "Реестровый №",          "group": "Идентификация"},
    "status":                 {"label": "Статус",                "group": "Идентификация"},
    "subsidy":                {"label": "Субсидия",              "group": "Идентификация"},
    "feo_category":           {"label": "Категория ФЭО",         "group": "Идентификация"},
    "item_name":              {"label": "Наименование",          "group": "Позиция"},
    "item_type":              {"label": "Тип",                   "group": "Позиция"},
    "unit":                   {"label": "Ед. изм",               "group": "Позиция"},
    "quantity":               {"label": "Кол-во",                "group": "Позиция"},
    "subject":                {"label": "Предмет закупки",       "group": "Позиция"},
    "country_origin":         {"label": "Страна происхождения",  "group": "Позиция"},
    "planned_unit_price":     {"label": "Плановая цена за ед.",  "group": "Цены"},
    "planned_total_price":    {"label": "Плановая сумма",        "group": "Цены"},
    "nmck":                   {"label": "НМЦК",                  "group": "Цены"},
    "contract_price":         {"label": "Цена договора",         "group": "Цены"},
    "economy":                {"label": "Экономия",              "group": "Цены"},
    "price_increase":         {"label": "Удорожание",            "group": "Цены"},
    "purchase_method":        {"label": "Способ закупки",        "group": "Закупка"},
    "purchase_basis":         {"label": "Основание",             "group": "Закупка"},
    "purchase_contract_type": {"label": "Тип договора",          "group": "Закупка"},
    "framework_seq":          {"label": "№ в рамочном",          "group": "Закупка"},
    "contract_number":        {"label": "№ договора",            "group": "Договор"},
    "contract_date":          {"label": "Дата договора",         "group": "Договор"},
    "execution_term":         {"label": "Срок исполнения",       "group": "Договор"},
    "execution_term_changed": {"label": "Срок (изменён)",        "group": "Договор"},
    "delivery_date":          {"label": "Дата доставки",         "group": "Договор"},
    "contractor":             {"label": "Контрагент",            "group": "Контрагент"},
    "contractor_inn":         {"label": "ИНН контрагента",       "group": "Контрагент"},
    "responsible_person":     {"label": "Ответственное лицо",    "group": "Контрагент"},
    "acceptance_doc_name":    {"label": "Закрывающий документ: наименование", "group": "Исполнение"},
    "acceptance_doc_number":  {"label": "Закрывающий документ: №",           "group": "Исполнение"},
    "acceptance_doc_date":    {"label": "Закрывающий документ: дата",         "group": "Исполнение"},
    "acceptance_doc_amount":  {"label": "Закрывающий документ: сумма",        "group": "Исполнение"},
    "payment_doc_number":     {"label": "ПП: №",                 "group": "Оплата"},
    "payment_doc_date":       {"label": "ПП: дата",              "group": "Оплата"},
    "payment_amount":         {"label": "ПП: сумма",             "group": "Оплата"},
    "payment_federal":        {"label": "В т.ч. фед. бюджет",   "group": "Оплата"},
    "delivery_payment_amount":{"label": "Оплата с доставкой",    "group": "Оплата"},
    "vat_applicable":         {"label": "НДС применяется",       "group": "НДС"},
    "vat_rate":               {"label": "Ставка НДС",            "group": "НДС"},
    "vat_exemption_article":  {"label": "Статья НК РФ",          "group": "НДС"},
    "etp_url":                {"label": "Ссылка ЭТП",            "group": "Закупка"},
}

DEFAULT_EXPORT_COLUMNS = [
    "purchase_number", "registry_number", "item_name", "item_type", "unit", "quantity",
    "nmck", "contract_price", "economy", "purchase_method",
    "contract_number", "contract_date", "contractor", "contractor_inn",
    "execution_term", "country_origin",
    "acceptance_doc_name", "acceptance_doc_number", "acceptance_doc_date", "acceptance_doc_amount",
    "payment_doc_number", "payment_doc_date", "payment_amount", "payment_federal",
    "status",
]

_PURCHASE_METHOD_LABELS = {
    "single": "Единственный поставщик",
    "competitive": "Конкурсная процедура",
    "quote_request": "Запрос котировок",
}
_PURCHASE_BASIS_LABELS = {
    "plan_schedule": "план-график",
    "service_note": "служебная записка",
}
_CONTRACT_TYPE_LABELS = {
    "single": "Разовая поставка",
    "framework_cumulative": "Рамочный (нарастающий итог)",
    "framework_with_amount": "Рамочный (с указанием суммы)",
}
_STATUS_LABELS = {
    "wishes": "Желания сотрудников",
    "plan_schedule": "План-график",
    "confirmed": "Подтверждено руководством",
    "work_in_progress": "Ведётся работа",
    "contracted": "Заключён договор",
    "delivered": "Поставлено",
    "paid": "Оплачено",
}


def _get_cell_value(key: str, p: Purchase, ctx: dict):
    if key == "purchase_number":         return p.purchase_number or ""
    if key == "order_number":            return p.order_number or ""
    if key == "registry_number":         return p.registry_number or ""
    if key == "status":                  return _STATUS_LABELS.get(p.status, p.status or "")
    if key == "subsidy":                 return ctx["subsidies"].get(p.subsidy_id, "")
    if key == "feo_category":            return ctx["feo_categories"].get(p.feo_category_id, "")
    if key == "item_name":               return p.item_name or ""
    if key == "item_type":               return p.item_type or ""
    if key == "unit":                    return p.unit or ""
    if key == "quantity":                return float(p.planned_quantity) if p.planned_quantity else ""
    if key == "subject":                 return p.subject or ""
    if key == "country_origin":          return p.country_origin or ""
    if key == "planned_unit_price":      return float(p.planned_unit_price) if p.planned_unit_price else ""
    if key == "planned_total_price":     return float(p.planned_total_price) if p.planned_total_price else ""
    if key == "nmck":                    return float(p.nmck or p.planned_total_price or 0) or ""
    if key == "contract_price":          return float(p.contract_price) if p.contract_price else ""
    if key == "economy":                 return float(p.economy) if p.economy else ""
    if key == "price_increase":          return float(p.price_increase) if p.price_increase else ""
    if key == "purchase_method":         return _PURCHASE_METHOD_LABELS.get(p.purchase_method, p.purchase_method or "")
    if key == "purchase_basis":          return _PURCHASE_BASIS_LABELS.get(p.purchase_basis, p.purchase_basis or "")
    if key == "purchase_contract_type":  return _CONTRACT_TYPE_LABELS.get(p.purchase_contract_type, p.purchase_contract_type or "")
    if key == "framework_seq":           return p.framework_seq if p.framework_seq is not None else ""
    if key == "contract_number":         return p.contract_number or ""
    if key == "contract_date":           return str(p.contract_date) if p.contract_date else ""
    if key == "execution_term":          return str(p.execution_term) if p.execution_term else ""
    if key == "execution_term_changed":  return str(p.execution_term_changed) if p.execution_term_changed else ""
    if key == "delivery_date":           return str(p.delivery_date) if p.delivery_date else ""
    if key == "contractor":              return ctx["contractors"].get(p.contractor_id, "")
    if key == "contractor_inn":          return ctx["contractor_inns"].get(p.contractor_id, "")
    if key == "responsible_person":      return p.responsible_person or ""
    if key == "acceptance_doc_name":     return p.acceptance_doc_name or ""
    if key == "acceptance_doc_number":   return p.acceptance_doc_number or ""
    if key == "acceptance_doc_date":     return str(p.acceptance_doc_date) if p.acceptance_doc_date else ""
    if key == "acceptance_doc_amount":   return float(p.acceptance_doc_amount) if p.acceptance_doc_amount else ""
    if key == "payment_doc_number":      return p.payment_doc_number or ""
    if key == "payment_doc_date":        return str(p.payment_doc_date) if p.payment_doc_date else ""
    if key == "payment_amount":          return float(p.payment_amount) if p.payment_amount else ""
    if key == "payment_federal":         return float(p.payment_federal) if p.payment_federal else ""
    if key == "delivery_payment_amount": return float(p.delivery_payment_amount) if p.delivery_payment_amount else ""
    if key == "vat_applicable":          return "Да" if p.vat_applicable else ""
    if key == "vat_rate":                return p.vat_rate if p.vat_rate is not None else ""
    if key == "vat_exemption_article":   return p.vat_exemption_article or ""
    if key == "etp_url":                 return p.etp_url or ""
    return ""


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

    contractor_rows = (await db.execute(select(Contractor))).scalars().all()
    contractors = {c.id: c.name for c in contractor_rows}
    contractor_inns = {c.id: (c.inn or "") for c in contractor_rows}
    subsidies_map = {s.id: s.name for s in (await db.execute(select(Subsidy))).scalars().all()}
    feo_map = {f.id: f.name for f in (await db.execute(select(FeoCategory))).scalars().all()}
    ctx = {"contractors": contractors, "contractor_inns": contractor_inns, "subsidies": subsidies_map, "feo_categories": feo_map}

    wb = Workbook()
    ws = wb.active
    ws.title = "Закупки"

    col_headers = [ALL_EXPORT_COLUMNS[k]["label"] for k in col_keys]
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
        ws.append(row)

    for i, key in enumerate(col_keys, 1):
        col_letter = ws.cell(1, i).column_letter
        ws.column_dimensions[col_letter].width = max(len(col_headers[i - 1]) + 2, 12)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"purchases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    missing = []
    if len(purchases) >= 5:
        for k in col_keys:
            if empty_counts[k] / len(purchases) > 0.8:
                missing.append(ALL_EXPORT_COLUMNS[k]["label"])

    resp_headers = {
        "Content-Disposition": f"attachment; filename={filename}",
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


@router.get("/import/template")
async def download_import_template():
    """Скачать шаблон Excel для импорта закупок."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    wb = Workbook()
    ws = wb.active
    ws.title = "Закупки"

    headers = [
        "Наименование", "Субсидия", "Категория ФЭО", "Контрагент", "ИНН контрагента",
        "НМЦК", "Способ закупки", "Реестровый №", "№ договора", "Дата договора",
        "Цена договора", "Срок исполнения", "ПП №", "ПП дата", "Оплачено",
        "Статус", "Год",
    ]
    ws.append(headers)

    # Style header row
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Sample row
    ws.append([
        "Закупка компьютеров", "ФАДМ_2026", "Техническое оснащение", "ООО Поставщик", "1234567890",
        "500000", "ЕИ", "2026/001", "Д-001", "15.03.2026",
        "490000", "30.06.2026", "", "", "",
        "confirmed", "2026",
    ])

    # Column widths
    col_widths = [35, 20, 30, 25, 15, 12, 15, 14, 14, 14, 14, 14, 12, 12, 12, 14, 6]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w

    ws.freeze_panes = "A2"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=import_template.xlsx"}
    )


@router.post("/import")
async def import_purchases_from_excel(
    file: UploadFile = File(...),
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Импорт закупок из Excel. Возвращает {created, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой или содержит только заголовки")

    # Parse headers (case-insensitive)
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    COLUMN_MAP = {
        "наименование": "item_name", "предмет закупки": "item_name",
        "субсидия": "subsidy_name",
        "категория фэо": "feo_category_name",
        "контрагент": "contractor_name",
        "инн контрагента": "contractor_inn", "инн": "contractor_inn",
        "нмцк": "nmck", "сумма": "nmck", "цена": "nmck",
        "способ закупки": "purchase_method", "способ": "purchase_method",
        "реестровый №": "registry_number", "реестровый номер": "registry_number", "реестр. №": "registry_number",
        "№ договора": "contract_number", "номер договора": "contract_number",
        "дата договора": "contract_date",
        "цена договора": "contract_price",
        "срок исполнения": "execution_term",
        "пп №": "payment_doc_number", "пп номер": "payment_doc_number",
        "пп дата": "payment_doc_date",
        "оплачено": "payment_amount",
        "статус": "status",
        "ссылка этп": "etp_url", "этп": "etp_url", "процедура этп": "etp_url",
        "год": "year",
        "№ п/п": "purchase_number",
    }
    col_idx: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i

    # Load lookup tables
    subs_rows = (await db.execute(select(Subsidy))).scalars().all()
    subs_by_name = {s.name.lower().strip(): s.id for s in subs_rows}

    contractors_rows = (await db.execute(select(Contractor))).scalars().all()
    cont_by_name = {c.name.lower().strip(): c.id for c in contractors_rows}
    cont_by_inn  = {c.inn.strip(): c.id for c in contractors_rows if c.inn}

    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name = {f.name.lower().strip(): f.id for f in feo_rows}

    STATUS_MAP = {
        "wishes": "wishes", "желания": "wishes", "planned": "wishes", "планируется": "wishes", "план": "wishes",
        "plan_schedule": "plan_schedule", "план-график": "plan_schedule",
        "confirmed": "confirmed", "подтверждено": "confirmed",
        "work_in_progress": "work_in_progress", "в работе": "work_in_progress", "in_progress": "work_in_progress",
        "contracted": "contracted", "законтрактовано": "contracted",
        "delivered": "delivered", "исполнено": "delivered",
        "paid": "paid", "оплачено": "paid",
    }
    METHOD_MAP = {
        "еи": "single", "единственный исполнитель": "single", "single": "single",
        "кп": "competitive", "конкурсная процедура": "competitive", "competitive": "competitive",
    }

    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None

    def to_dec(v):
        if v is None:
            return None
        try:
            return Decimal(str(v).replace(" ", "").replace(",", "."))
        except Exception:
            return None

    def to_date_val(v):
        if v is None:
            return None
        if hasattr(v, "date"):
            return v.date()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(str(v).strip(), fmt).date()
            except Exception:
                pass
        return None

    created = 0
    skipped = 0
    errors: list[dict] = []

    for row_num, row in enumerate(rows[1:], start=2):
        try:
            item_name = cell(row, "item_name")
            if not item_name:
                skipped += 1
                continue

            # Resolve subsidy
            sid = subsidy_id
            if not sid:
                sub_name = cell(row, "subsidy_name")
                if sub_name:
                    sid = subs_by_name.get(sub_name.lower().strip())
            if not sid:
                errors.append({"row": row_num, "name": item_name, "message": "Субсидия не найдена"})
                continue

            # Resolve contractor
            cid = None
            c_name = cell(row, "contractor_name")
            c_inn  = cell(row, "contractor_inn")
            if c_inn:
                cid = cont_by_inn.get(c_inn.strip())
            if not cid and c_name:
                cid = cont_by_name.get(c_name.lower().strip())

            # Resolve FEO
            feo_id = None
            feo_name = cell(row, "feo_category_name")
            if feo_name:
                feo_id = feo_by_name.get(feo_name.lower().strip())

            # Status
            status_raw = (cell(row, "status") or "wishes").lower().strip()
            status = STATUS_MAP.get(status_raw, "wishes")

            # Method
            method_raw = (cell(row, "purchase_method") or "").lower().strip()
            method = METHOD_MAP.get(method_raw)

            nmck = to_dec(cell(row, "nmck"))
            p = Purchase(
                subsidy_id=sid,
                feo_category_id=feo_id,
                contractor_id=cid,
                item_name=item_name,
                status=status,
                nmck=nmck,
                total_nmck=nmck,
                planned_total_price=nmck,
                contract_price=to_dec(cell(row, "contract_price")),
                payment_amount=to_dec(cell(row, "payment_amount")),
                purchase_method=method,
                registry_number=cell(row, "registry_number"),
                contract_number=cell(row, "contract_number"),
                contract_date=to_date_val(cell(row, "contract_date")),
                execution_term=to_date_val(cell(row, "execution_term")),
                payment_doc_number=cell(row, "payment_doc_number"),
                payment_doc_date=to_date_val(cell(row, "payment_doc_date")),
            )
            db.add(p)
            created += 1
        except Exception as e:
            errors.append({"row": row_num, "name": cell(row, "item_name") or "?", "message": str(e)})

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
