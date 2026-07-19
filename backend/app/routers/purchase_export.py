"""Purchase export/import router — extracted from purchases.py (Phase 16-02).

Handles:
  GET  /api/purchases/export/columns   — list available Excel export columns
  GET  /api/purchases/export/excel     — stream .xlsx export of purchases
  GET  /api/purchases/import/template  — download blank import template (1-sheet, inline payments)
  POST /api/purchases/import           — Scroller-format xlsx import
  POST /api/purchases/import/preview   — preview without committing
"""
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import quote
from collections import defaultdict

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
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
    "competitive": "Конкурентная процедура",
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


# ---------------------------------------------------------------------------
# Import template (2 sheets: «Закупки» + «Платежи»)
# ---------------------------------------------------------------------------

# (header_text, is_required, column_width)
# «Закупки» sheet — inline payments (no separate «Платежи» sheet)
_TEMPLATE_COLUMNS = [
    ("Тип договора",                    False, 18),
    ("Номер закупки",                   False, 16),
    ("Номер заказа внутри закупки",     False, 26),
    ("Предмет договора (общий)",        False, 30),
    ("Наименование товара",             True,  32),
    ("ФЭО Ур.1",                        True,  22),
    ("ФЭО Ур.2",                        False, 22),
    ("ФЭО Ур.3",                        False, 22),
    ("ФЭО Ур.4",                        False, 22),
    ("ФЭО Ур.5",                        False, 22),
    ("Мероприятие",                     False, 25),
    ("Контрагент",                      False, 25),
    ("ИНН контрагента",                 True,  18),
    ("Способ закупки",                  False, 28),
    ("Реестровый №",                    False, 16),
    ("№ договора",                      True,  16),
    ("Дата договора",                   True,  14),
    ("Максимальная цена договора",      False, 24),
    ("Срок исполнения",                 False, 16),
    ("Статус",                          False, 14),
    ("Номер платёжного документа",      False, 24),
    ("Дата платёжного документа",       False, 22),
    ("Сумма оплаты",                    False, 16),
    ("Назначение платежа",              False, 30),
    ("Количество (план)",               True,  16),
    ("Ед. изм.",                        False, 10),
    ("Цена за ед. (план)",              True,  18),
    ("Сумма план",                      False, 14),
    ("Кол-во факт",                     False, 14),
    ("Цена за ед. (факт)",              False, 18),
    ("Сумма факт",                      True,  14),
    ("Страна происхождения",            False, 22),
    ("Ставка НДС",                      False, 12),
    ("Год",                             False,  8),
]

# Row 1: закупка 20, Заказ 1 — 34 values aligned to _TEMPLATE_COLUMNS
_TEMPLATE_EXAMPLE_ROW = [
    "Рамочный",                         # Тип договора
    "20",                               # Номер закупки
    "Заказ 1 (март)",                   # Номер заказа внутри закупки
    "Обмундирование к слёту",           # Предмет договора (общий)
    "Кепи камуфляж",                    # Наименование товара
    "Снаряжение",                       # ФЭО Ур.1
    "Одежда",                           # ФЭО Ур.2
    "Кепи",                             # ФЭО Ур.3
    "",                                 # ФЭО Ур.4
    "",                                 # ФЭО Ур.5
    "Форма к слёту",                    # Мероприятие
    "ООО Поставщик",                    # Контрагент
    "1234567890",                       # ИНН контрагента
    "Единственный поставщик",           # Способ закупки
    "2026/001",                         # Реестровый №
    "Д-001",                            # № договора
    "15.03.2026",                       # Дата договора
    "600000",                           # Максимальная цена договора
    "30.06.2026",                       # Срок исполнения
    "paid",                             # Статус
    "ПП-101",                           # Номер платёжного документа
    "01.04.2026",                       # Дата платёжного документа
    "245000",                           # Сумма оплаты
    "Оплата по Д-001, 1-й платёж",      # Назначение платежа
    "100",                              # Количество (план)
    "шт",                               # Ед. изм.
    "4900",                             # Цена за ед. (план)
    "490000",                           # Сумма план
    "100",                              # Кол-во факт
    "4900",                             # Цена за ед. (факт)
    "490000",                           # Сумма факт
    "Россия",                           # Страна происхождения
    "20",                               # Ставка НДС
    "2026",                             # Год
]

# Row 2: закупка 20, Заказ 2 — same рамочный contract, different order — 34 values
_TEMPLATE_EXAMPLE_ROW_2 = [
    "Рамочный",                         # Тип договора
    "20",                               # Номер закупки
    "Заказ 2 (май)",                    # Номер заказа внутри закупки
    "Обмундирование к слёту",           # Предмет договора (общий)
    "Берцы тактические",                # Наименование товара
    "Снаряжение",                       # ФЭО Ур.1
    "Обувь",                            # ФЭО Ур.2
    "Берцы",                            # ФЭО Ур.3
    "",                                 # ФЭО Ур.4
    "",                                 # ФЭО Ур.5
    "Форма к слёту",                    # Мероприятие
    "ООО Поставщик",                    # Контрагент
    "1234567890",                       # ИНН контрагента
    "Единственный поставщик",           # Способ закупки
    "2026/001",                         # Реестровый №
    "Д-001",                            # № договора
    "15.03.2026",                       # Дата договора
    "600000",                           # Максимальная цена договора
    "30.06.2026",                       # Срок исполнения
    "paid",                             # Статус
    "ПП-205",                           # Номер платёжного документа
    "15.05.2026",                       # Дата платёжного документа
    "110000",                           # Сумма оплаты
    "Оплата по Д-001, 2-й платёж",      # Назначение платежа
    "20",                               # Количество (план)
    "пар",                              # Ед. изм.
    "5500",                             # Цена за ед. (план)
    "110000",                           # Сумма план
    "20",                               # Кол-во факт
    "5500",                             # Цена за ед. (факт)
    "110000",                           # Сумма факт
    "Россия",                           # Страна происхождения
    "20",                               # Ставка НДС
    "2026",                             # Год
]


@router.get("/import/template")
async def download_import_template():
    """Скачать шаблон Excel для импорта закупок (1 лист «Закупки», платежи inline)."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()

    fill_req = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    fill_opt = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    font_hdr = Font(color="FFFFFF", bold=True, size=11)
    align_c  = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # ---- Sheet 1: «Закупки» (single sheet, payments inline) ----
    ws = wb.active
    ws.title = "Закупки"

    headers = [col[0] for col in _TEMPLATE_COLUMNS]
    ws.append(headers)

    for i, (_, is_req, _) in enumerate(_TEMPLATE_COLUMNS, 1):
        c = ws.cell(1, i)
        c.fill = fill_req if is_req else fill_opt
        c.font = font_hdr
        c.alignment = align_c

    ws.append(_TEMPLATE_EXAMPLE_ROW)
    ws.append(_TEMPLATE_EXAMPLE_ROW_2)

    for i, (_, _, width) in enumerate(_TEMPLATE_COLUMNS, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = width

    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    def _col_ix(title: str) -> int:
        for i, (h, _, _) in enumerate(_TEMPLATE_COLUMNS, 1):
            if h == title:
                return i
        return 1

    # Note about FEO levels — write in row 4 (after 2 example rows)
    feo_note_col = _col_ix("ФЭО Ур.1")
    note_cell = ws.cell(4, feo_note_col)
    note_cell.value = "Заполняйте столько уровней ФЭО, сколько есть в вашей субсидии; лишние оставьте пустыми"
    note_cell.font = Font(italic=True, color="6B7280", size=9)

    # Payment hint — write after FEO note
    pay_note_col = _col_ix("Номер платёжного документа")
    pay_note = ws.cell(4, pay_note_col)
    pay_note.value = (
        "Помесячные / несколько платежей по одному договору — "
        "заполняйте отдельной строкой с тем же № договора; "
        "реквизиты платежа (номер, дата, сумма, назначение) — в колонках справа"
    )
    pay_note.font = Font(italic=True, color="6B7280", size=9)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=import_template.xlsx"}
    )


# ---------------------------------------------------------------------------
# Import helpers & COLUMN_MAP
# ---------------------------------------------------------------------------

# Full column map: lower-stripped header → internal field name.
# New template keys + old keys for backward compat.
_COLUMN_MAP: Dict[str, str] = {
    # --- New template: «Закупки» sheet ---
    "тип договора":                                              "contract_type_raw",
    "тип договора (разовый/рамочный)":                          "contract_type_raw",
    "номер закупки":                                             "purchase_group_num",
    "номер закупки (группа)":                                   "purchase_group_num",
    "номер заказа внутри закупки":                              "order_number",
    "номер заказа внутри закупки или период оказания услуг":   "order_number",
    "номер заказа":                                              "order_number",
    "предмет договора (общий)":                                 "subject",
    "предмет договора":                                         "subject",
    "наименование товара":                                       "item_name",
    "максимальная цена договора":                               "contract_price",
    "максимальная цена договора (предел рамочного)":           "contract_price",
    "наименование позиции":         "item_name",
    "наименование позиции *":       "item_name",
    "тип (товар/услуга/работа)":    "item_type",
    "тип":                          "item_type",
    # New 5-level FEO columns
    "фэо ур.1":                     "feo_l1",
    "фэо ур.2":                     "feo_l2",
    "фэо ур.3":                     "feo_l3",
    "фэо ур.4":                     "feo_l4",
    "фэо ур.5":                     "feo_l5",
    # Old single-path FEO column (backward compat)
    "категория фэо (полный путь) *": "feo_path",
    "категория фэо (полный путь)":  "feo_path",
    "категория фэо *":              "feo_path",
    "категория фэо":                "feo_category_name",
    "мероприятие":                  "event_name",
    "контрагент":                   "contractor_name",
    "инн контрагента *":            "contractor_inn",
    "инн контрагента":              "contractor_inn",
    "способ закупки (еи/кп)":       "purchase_method",
    "способ закупки":               "purchase_method",
    "реестровый №":                 "registry_number",
    "реестровый номер":             "registry_number",
    "реестр. №":                    "registry_number",
    "№ договора *":                 "contract_number",
    "№ договора":                   "contract_number",
    "дата договора *":              "contract_date",
    "дата договора":                "contract_date",
    "цена договора (итого)":        "contract_price",
    "цена договора":                "contract_price",
    "срок исполнения":              "execution_term",
    "статус":                       "status",
    "количество (план) *":          "plan_qty",
    "количество (план)":            "plan_qty",
    "ед. изм.":                     "unit",
    "ед. изм":                      "unit",
    "цена за ед. (план) *":         "plan_unit_price",
    "цена за ед. (план)":           "plan_unit_price",
    "сумма план":                   "plan_total",
    "кол-во факт":                  "fact_qty",
    "цена за ед. (факт)":           "fact_unit_price",
    "сумма факт *":                 "fact_total",
    "сумма факт":                   "fact_total",
    "страна происхождения":         "country_origin",
    "ставка ндс":                   "vat_rate",
    "год":                          "year",
    # --- Inline payment columns (new template) ---
    "номер платёжного документа":   "payment_doc_number",
    "номер платежного документа":   "payment_doc_number",
    "дата платёжного документа":    "payment_doc_date",
    "дата платежного документа":    "payment_doc_date",
    "назначение платежа":           "payment_purpose",
    # --- Removed columns from old template (keep for backward compat) ---
    "№ пп *":                       "payment_doc_number",
    "№ пп":                         "payment_doc_number",
    "дата платежа *":               "payment_doc_date",
    "дата платежа":                 "payment_doc_date",
    "сумма оплаты *":               "payment_amount",
    "сумма оплаты":                 "payment_amount",
    # --- Old 17-col backward compat ---
    "наименование":                 "item_name",
    "предмет закупки":              "item_name",
    "субсидия":                     "subsidy_name",
    "инн":                          "contractor_inn",
    "нмцк":                         "nmck",
    "сумма":                        "nmck",
    "цена":                         "nmck",
    "способ":                       "purchase_method",
    "номер договора":               "contract_number",
    "пп №":                         "payment_doc_number",
    "пп номер":                     "payment_doc_number",
    "пп дата":                      "payment_doc_date",
    "оплачено":                     "payment_amount",
    "ссылка этп":                   "etp_url",
    "этп":                          "etp_url",
    "процедура этп":                "etp_url",
    "№ п/п":                        "purchase_number",
}

# «Платежи» sheet column map
_PAYMENTS_COLUMN_MAP: Dict[str, str] = {
    "№ договора":           "contract_number",
    "№ пп":                 "document_number",
    "дата платежа":         "payment_date",
    "сумма":                "amount",
    "назначение платежа":   "payment_purpose",
}

_STATUS_MAP = {
    "wishes": "wishes", "желания": "wishes", "planned": "wishes", "планируется": "wishes", "план": "wishes",
    "plan_schedule": "plan_schedule", "план-график": "plan_schedule",
    "confirmed": "confirmed", "подтверждено": "confirmed",
    "work_in_progress": "work_in_progress", "в работе": "work_in_progress", "in_progress": "work_in_progress",
    "contracted": "contracted", "законтрактовано": "contracted",
    "delivered": "delivered", "исполнено": "delivered",
    "paid": "paid", "оплачено": "paid",
}

_METHOD_MAP = {
    # full names (new template)
    "единственный поставщик":   "single",
    "единственный исполнитель": "single",
    "единый поставщик":         "single",
    "конкурентная процедура":   "competitive",
    "конкурсная процедура":     "competitive",
    # abbreviations (backward compat)
    "еи":  "single",
    "ед":  "single",
    "кп":  "competitive",
    # english keys
    "single":      "single",
    "competitive": "competitive",
}

# Required fields for new-format validation (field_name, display_label)
_REQUIRED_FIELDS = [
    ("item_name",       "Наименование товара"),
    ("feo_l1",          "ФЭО Ур.1"),
    ("contractor_inn",  "ИНН контрагента"),
    ("contract_number", "№ договора"),
    ("contract_date",   "Дата договора"),
    ("plan_qty",        "Количество (план)"),
    ("plan_unit_price", "Цена за ед. (план)"),
    ("fact_total",      "Сумма факт"),
]

# Marker fields that distinguish new template from old legacy template
_NEW_TEMPLATE_MARKER_FIELDS = {"feo_l1", "plan_qty", "plan_unit_price", "fact_total"}
# Old-template marker (single path column)
_OLD_TEMPLATE_MARKER_FIELDS = {"feo_path", "feo_category_name"}


def _make_cell_helper(col_idx: Dict[str, int]):
    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None
    return cell


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(" ", "").replace(",", ".").replace("\xa0", ""))
    except Exception:
        return None


def _to_date_val(v):
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


def _build_feo_index(feo_rows: List[FeoCategory], sid: int) -> Dict[int, FeoCategory]:
    """Return {id: FeoCategory} for categories belonging to given subsidy."""
    return {f.id: f for f in feo_rows if f.subsidy_id == sid}


def _resolve_feo_levels(
    levels: List[str],
    sid: int,
    feo_index: Dict[int, FeoCategory],
) -> tuple:
    """
    Walk the FEO tree of THIS subsidy using ordered level values.
    levels = non-empty strings in order (e.g. ['Снаряжение', 'Одежда', 'Кепи']).
    Returns (feo_category_id, error_message_or_None).
    """
    if not levels:
        return None, "Не указан ни один уровень ФЭО"

    roots = [f for f in feo_index.values() if f.parent_id is None or f.parent_id not in feo_index]
    current_candidates = roots
    current_node = None

    for level_idx, part in enumerate(levels):
        needle = part.lower().strip()
        matched = None
        # exact match first
        for candidate in current_candidates:
            if candidate.name.lower().strip() == needle:
                matched = candidate
                break
        # fallback: contains
        if matched is None:
            for candidate in current_candidates:
                if needle in candidate.name.lower().strip():
                    matched = candidate
                    break
        if matched is None:
            return None, f"ФЭО не найдено на уровне {level_idx + 1}: '{part}'"
        current_node = matched
        current_candidates = [f for f in feo_index.values() if f.parent_id == matched.id]

    if current_node is None:
        return None, "ФЭО не найдено"
    return current_node.id, None


def _resolve_feo_path(
    path_str: str,
    feo_index: Dict[int, FeoCategory],
) -> tuple:
    """
    Backward-compat: resolve old single path string (parts separated by ' / ' or '>').
    Returns (feo_category_id, error_message_or_None).
    """
    import re
    parts = [p.strip() for p in re.split(r"\s*/\s*|\s*>\s*", path_str) if p.strip()]
    if not parts:
        return None, "Пустой путь ФЭО"
    return _resolve_feo_levels(parts, 0, feo_index)


def _find_payments_sheet(wb):
    """Find the «Платежи» worksheet (case-insensitive match on 'платеж')."""
    for sheet in wb.worksheets:
        if "платеж" in sheet.title.lower():
            return sheet
    return None


# ---------------------------------------------------------------------------
# Core parse-and-group logic (shared by /import and /import/preview)
# ---------------------------------------------------------------------------

async def _parse_and_group(
    content: bytes,
    sid: int,
    db: AsyncSession,
    commit: bool,
) -> Dict[str, Any]:
    """
    Parse Excel content (2-sheet workbook), validate rows, group into purchases,
    optionally commit. Handles both new (5-level FEO, 2-sheet) and old (path, 1-sheet) templates.

    Returns dict with keys:
      created_purchases, created_items, created_payments, skipped, errors   (commit=True)
      purchases (list of preview dicts), payments_errors, skipped, errors   (commit=False)
    """
    wb = load_workbook(BytesIO(content), data_only=True)

    # Find «Закупки» sheet — use first sheet (active) as primary
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой или содержит только заголовки")

    # --- Build col_idx for «Закупки» ---
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    col_idx: Dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = _COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i

    cell = _make_cell_helper(col_idx)

    # Detect template format: prefer new (feo_l1) over old (feo_path)
    has_new_feo = bool(_NEW_TEMPLATE_MARKER_FIELDS & set(col_idx.keys()))
    has_old_feo = bool(_OLD_TEMPLATE_MARKER_FIELDS & set(col_idx.keys()))
    # is_new_template: new format with level cols, OR both — prefer levels
    is_new_template = has_new_feo

    # --- Load lookup tables ---
    subs_rows = (await db.execute(select(Subsidy))).scalars().all()
    subs_by_name = {s.name.lower().strip(): s.id for s in subs_rows}

    contractors_all = (await db.execute(select(Contractor))).scalars().all()
    cont_by_inn  = {c.inn.strip(): c.id for c in contractors_all if c.inn}
    cont_by_name = {c.name.lower().strip(): c.id for c in contractors_all}

    feo_rows_all = (await db.execute(select(FeoCategory))).scalars().all()
    feo_index = _build_feo_index(feo_rows_all, sid)

    # Anti-dup: existing (contract_number, order_number) pairs for this subsidy
    existing_q = await db.execute(
        select(Purchase.contract_number, Purchase.order_number).where(
            Purchase.subsidy_id == sid,
            Purchase.contract_number.isnot(None),
            Purchase.contract_number != "",
        )
    )
    existing_keys = {(r[0], r[1]) for r in existing_q.fetchall()}

    errors: list[dict] = []
    skipped = 0

    # --- Parse «Закупки» rows ---
    parsed_rows = []
    for row_num, row in enumerate(rows[1:], start=2):
        # Blank row guard
        non_empty = any(
            v is not None and str(v).strip() != ""
            for v in row
        )
        if not non_empty:
            skipped += 1
            continue

        item_name = cell(row, "item_name")
        if not item_name:
            skipped += 1
            continue

        # ---- Resolve FEO ----
        feo_id = None
        feo_levels_display = None  # list of non-empty level strings, for preview display

        if has_new_feo and any(cell(row, f"feo_l{n}") for n in range(1, 6)):
            # New: collect non-empty level values in order
            raw_levels = [cell(row, f"feo_l{n}") or "" for n in range(1, 6)]
            levels = [v for v in raw_levels if v.strip()]
            feo_levels_display = levels

            if is_new_template:
                # feo_l1 is required — already validated below in required-field check,
                # but guard here too
                if not levels:
                    errors.append({"row": row_num, "name": item_name, "message": "ФЭО Ур.1 обязателен"})
                    continue
                feo_id, feo_err = _resolve_feo_levels(levels, sid, feo_index)
                if feo_err:
                    errors.append({"row": row_num, "name": item_name, "message": feo_err})
                    continue
            else:
                if levels:
                    feo_id, _ = _resolve_feo_levels(levels, sid, feo_index)
        elif has_old_feo:
            # Old: single path column (backward compat)
            feo_path_raw = cell(row, "feo_path") or cell(row, "feo_category_name")
            if feo_path_raw:
                feo_id, feo_err = _resolve_feo_path(feo_path_raw, feo_index)
                if feo_err and not has_new_feo:
                    # only hard-error in old-style-only templates if it was new-enough format
                    pass  # leave feo_id as None
                feo_levels_display = [p.strip() for p in feo_path_raw.replace(">", "/").split("/") if p.strip()]

        # ---- Required-field validation (new template) ----
        if is_new_template:
            missing_labels = []
            for field, label in _REQUIRED_FIELDS:
                val = cell(row, field)
                if not val:
                    missing_labels.append(label)
            if missing_labels:
                errors.append({"row": row_num, "name": item_name, "missing": missing_labels})
                continue

        # ---- Contract number required (all modes) ----
        contract_num = cell(row, "contract_number")
        if is_new_template and not contract_num:
            errors.append({"row": row_num, "name": item_name, "message": "№ договора обязателен"})
            continue

        # ---- Subsidy ----
        row_sid = sid
        sub_name = cell(row, "subsidy_name")
        if not row_sid and sub_name:
            row_sid = subs_by_name.get(sub_name.lower().strip())
        if not row_sid:
            errors.append({"row": row_num, "name": item_name, "message": "Субсидия не указана"})
            continue

        # ---- Contractor ----
        c_inn  = cell(row, "contractor_inn")
        c_name = cell(row, "contractor_name")
        cont_id = None
        if c_inn:
            cont_id = cont_by_inn.get(c_inn.strip())
        if not cont_id and c_name:
            cont_id = cont_by_name.get(c_name.lower().strip())
        if not cont_id and c_inn:
            if commit:
                new_cont = Contractor(name=c_name or c_inn, inn=c_inn.strip())
                db.add(new_cont)
                await db.flush()
                cont_id = new_cont.id
                cont_by_inn[c_inn.strip()] = cont_id
                if c_name:
                    cont_by_name[c_name.lower().strip()] = cont_id

        # ---- Status ----
        status_raw = (cell(row, "status") or "").lower().strip()
        status = _STATUS_MAP.get(status_raw)
        if not status:
            # old-style payment columns on this sheet (backward compat)
            pay_amt = _to_dec(cell(row, "payment_amount"))
            if pay_amt and pay_amt > 0:
                status = "paid"
            elif contract_num:
                status = "contracted"
            else:
                status = "confirmed"

        # ---- Method ----
        method_raw = (cell(row, "purchase_method") or "").lower().strip()
        method = _METHOD_MAP.get(method_raw)

        # ---- New fields: purchase group number, order number, contract subject ----
        pg = cell(row, "purchase_group_num")
        order_no = cell(row, "order_number")
        subject_val = cell(row, "subject")

        # ---- Group key: prioritise purchase+order, then contract, then row ----
        if pg:
            group_key = f"pg:{pg}|{order_no or ''}"
        elif contract_num:
            group_key = f"contract:{contract_num}"
        else:
            group_key = f"row:{row_num}"

        # ---- Collect raw date cells for post-processing ----
        raw_contract_date   = row[col_idx["contract_date"]]   if "contract_date"   in col_idx else None
        raw_execution_term  = row[col_idx["execution_term"]]  if "execution_term"  in col_idx else None
        raw_payment_doc_date= row[col_idx["payment_doc_date"]]if "payment_doc_date" in col_idx else None

        parsed_rows.append({
            "row_num":          row_num,
            "group_key":        group_key,
            "purchase_group_num": pg,
            "order_number":     order_no,
            "subject":          subject_val,
            "item_name":        item_name,
            "item_type":        cell(row, "item_type"),
            "feo_id":           feo_id,
            "feo_levels":       feo_levels_display or [],
            "cont_id":          cont_id,
            "cont_inn":         c_inn,
            "cont_name":        c_name,
            "event_name":       cell(row, "event_name"),
            "status":           status,
            "method":           method,
            "registry_number":  cell(row, "registry_number"),
            "contract_number":  contract_num,
            "contract_date":    _to_date_val(raw_contract_date),
            "contract_price":   _to_dec(cell(row, "contract_price")),
            "execution_term":   _to_date_val(raw_execution_term),
            # Inline payment fields (new template) + legacy backward compat
            "payment_doc_number": cell(row, "payment_doc_number"),
            "payment_doc_date":   _to_date_val(raw_payment_doc_date),
            "payment_amount":     _to_dec(cell(row, "payment_amount")),
            "payment_purpose":    cell(row, "payment_purpose"),
            "plan_qty":         _to_dec(cell(row, "plan_qty")),
            "unit":             cell(row, "unit"),
            "plan_unit_price":  _to_dec(cell(row, "plan_unit_price")),
            "plan_total":       _to_dec(cell(row, "plan_total")),
            "fact_qty":         _to_dec(cell(row, "fact_qty")),
            "fact_unit_price":  _to_dec(cell(row, "fact_unit_price")),
            "fact_total":       _to_dec(cell(row, "fact_total")),
            "country_origin":   cell(row, "country_origin"),
            "vat_rate":         cell(row, "vat_rate"),
            "nmck":             _to_dec(cell(row, "nmck")),
            "sid":              row_sid,
        })

    # --- Parse «Платежи» sheet ---
    pay_sheet = _find_payments_sheet(wb)
    parsed_payments: List[Dict[str, Any]] = []
    payments_errors: List[dict] = []

    if pay_sheet is not None:
        pay_rows = list(pay_sheet.iter_rows(values_only=True))
        if len(pay_rows) >= 2:
            raw_pay_headers = [str(h).strip().lower() if h is not None else "" for h in pay_rows[0]]
            pay_col_idx: Dict[str, int] = {}
            for i, h in enumerate(raw_pay_headers):
                field = _PAYMENTS_COLUMN_MAP.get(h)
                if field and field not in pay_col_idx:
                    pay_col_idx[field] = i

            pay_cell = _make_cell_helper(pay_col_idx)

            for pay_row_num, pay_row in enumerate(pay_rows[1:], start=2):
                # Skip blank rows and note rows (e.g. the hint text we put in row 3)
                non_empty = any(
                    v is not None and str(v).strip() != ""
                    for v in pay_row
                )
                if not non_empty:
                    continue

                p_contract = pay_cell(pay_row, "contract_number")
                if not p_contract:
                    continue
                # Skip the hint-text row if it landed in col 1
                if "одна строка" in p_contract.lower() or "платёж" in p_contract.lower():
                    continue

                raw_pay_date = pay_row[pay_col_idx["payment_date"]] if "payment_date" in pay_col_idx else None

                parsed_payments.append({
                    "pay_row_num":      pay_row_num,
                    "contract_number":  p_contract,
                    "document_number":  pay_cell(pay_row, "document_number"),
                    "payment_date":     _to_date_val(raw_pay_date),
                    "amount":           _to_dec(pay_cell(pay_row, "amount")),
                    "payment_purpose":  pay_cell(pay_row, "payment_purpose"),
                })

    # --- Group rows ---
    groups: Dict[str, List[dict]] = defaultdict(list)
    for pr in parsed_rows:
        groups[pr["group_key"]].append(pr)

    created_purchases = 0
    created_items = 0
    created_payments = 0
    preview_list = []

    # Map contract_number → Purchase (built during commit, used for payment linking)
    contract_to_purchase: Dict[str, Purchase] = {}

    for group_key, group_rows in groups.items():
        first = group_rows[0]
        contract_num = first["contract_number"]

        # Anti-dup check (keyed on contract_number + order_number for рамочные)
        order_no = first.get("order_number")
        if contract_num and (contract_num, order_no) in existing_keys:
            skipped += 1
            if not commit:
                preview_list.append({
                    "group_key": group_key,
                    "contract_number": contract_num,
                    "purchase_group": first.get("purchase_group_num") or "",
                    "order_number": first.get("order_number") or "",
                    "contractor": first["cont_name"] or first["cont_inn"] or "",
                    "feo_path": " / ".join(first["feo_levels"]) if first["feo_levels"] else "",
                    "items_count": len(group_rows),
                    "plan_total": None,
                    "fact_total": None,
                    "status": first["status"],
                    "payments_count": 0,
                    "payments_total": None,
                    "skipped": True,
                    "skip_reason": "Дублирующийся договор",
                })
            continue

        # Aggregate sums
        plan_total_sum = sum(
            (pr["plan_total"] or (
                (pr["plan_qty"] or Decimal(0)) * (pr["plan_unit_price"] or Decimal(0))
            ))
            for pr in group_rows
        )
        fact_total_sum = sum(
            (pr["fact_total"] or Decimal(0))
            for pr in group_rows
        )

        # --- Collect inline payments from group rows ---
        inline_payments = []
        for pr in group_rows:
            if pr.get("payment_doc_number") or pr.get("payment_amount") or pr.get("payment_doc_date"):
                inline_payments.append({
                    "document_number": pr.get("payment_doc_number"),
                    "payment_date":    pr.get("payment_doc_date"),
                    "amount":          pr.get("payment_amount"),
                    "payment_purpose": pr.get("payment_purpose"),
                    "row_num":         pr["row_num"],
                })

        # Payments for preview: inline first, then sheet (backward compat)
        sheet_payments = [pp for pp in parsed_payments if pp["contract_number"] == contract_num] if contract_num else []

        # Deduplicate inline payments by fingerprint
        def _pay_fp_local(dn, pd, am):
            return (
                str(dn or "").strip(),
                str(pd or ""),
                round(float(am), 2) if am is not None else None,
            )
        seen_fps: set = set()
        unique_inline: list = []
        for ip in inline_payments:
            fp = _pay_fp_local(ip["document_number"], ip["payment_date"], ip["amount"])
            if fp not in seen_fps:
                seen_fps.add(fp)
                unique_inline.append(ip)

        # Total payments for preview = unique inline + sheet (deduped against inline)
        all_preview_payments = list(unique_inline)
        for sp in sheet_payments:
            fp = _pay_fp_local(sp.get("document_number"), sp.get("payment_date"), sp.get("amount"))
            if fp not in seen_fps:
                seen_fps.add(fp)
                all_preview_payments.append(sp)

        pay_count = len(all_preview_payments)
        pay_total = sum((ip.get("amount") or Decimal(0)) for ip in all_preview_payments)

        # Deduped item count (same key as commit-side PurchaseItem dedup)
        unique_item_keys = {
            ((pr["item_name"] or "").lower().strip(), pr["plan_qty"], pr["plan_unit_price"])
            for pr in group_rows
        }

        if not commit:
            preview_list.append({
                "group_key": group_key,
                "contract_number": contract_num or "",
                "purchase_group": first.get("purchase_group_num") or "",
                "order_number": first.get("order_number") or "",
                "contractor": first["cont_name"] or first["cont_inn"] or "",
                "feo_path": " / ".join(first["feo_levels"]) if first["feo_levels"] else "",
                "items_count": len(unique_item_keys),
                "plan_total": float(plan_total_sum) if plan_total_sum else None,
                "fact_total": float(fact_total_sum) if fact_total_sum else None,
                "status": first["status"],
                "payments_count": pay_count,
                "payments_total": float(pay_total) if pay_total else None,
                "skipped": False,
            })
            continue

        # --- Create Purchase ---
        # For inline payments: sum all unique amounts, first doc_number, min date
        inline_amounts  = [ip["amount"] for ip in unique_inline if ip["amount"] is not None]
        inline_dates    = [ip["payment_date"] for ip in unique_inline if ip["payment_date"] is not None]
        inline_doc_nums = [ip["document_number"] for ip in unique_inline if ip["document_number"]]

        p = Purchase(
            subsidy_id=first["sid"],
            feo_category_id=first["feo_id"],
            contractor_id=first["cont_id"] if (first["cont_id"] and first["cont_id"] != -1) else None,
            item_name=(first.get("subject") or first["item_name"]),
            purchase_number=int(first["purchase_group_num"]) if (first.get("purchase_group_num") or "").strip().isdigit() else None,
            order_number=first.get("order_number"),
            subject=first.get("subject"),
            status=first["status"],
            purchase_method=first["method"],
            registry_number=first["registry_number"],
            contract_number=contract_num,
            contract_date=first["contract_date"],
            contract_price=first["contract_price"],
            execution_term=first["execution_term"],
            # Summary payment fields from inline rows (or legacy single-row if no inline)
            payment_doc_number=inline_doc_nums[0] if inline_doc_nums else first.get("payment_doc_number"),
            payment_doc_date=min(inline_dates) if inline_dates else first.get("payment_doc_date"),
            payment_amount=sum(inline_amounts) if inline_amounts else first.get("payment_amount"),
            nmck=first["nmck"],
            total_nmck=first["nmck"],
            planned_quantity=first["plan_qty"],
            planned_unit_price=first["plan_unit_price"],
            planned_total_price=plan_total_sum if plan_total_sum else first["nmck"],
            final_total_amount=fact_total_sum if fact_total_sum else None,
            country_origin=first["country_origin"],
            vat_rate=int(first["vat_rate"]) if first["vat_rate"] and str(first["vat_rate"]).isdigit() else None,
        )

        # --- Create PurchaseItems (dedup by key within group) ---
        items = []
        seen_item_keys: set = set()
        for pr in group_rows:
            # Normalize item key to avoid duplicates for monthly-payment rows
            norm_name = (pr["item_name"] or "").lower().strip()
            item_key = (norm_name, pr["plan_qty"], pr["plan_unit_price"])
            if item_key in seen_item_keys:
                continue
            seen_item_keys.add(item_key)

            item_plan_total = pr["plan_total"] or (
                (pr["plan_qty"] or Decimal(0)) * (pr["plan_unit_price"] or Decimal(0))
            ) or None
            pi = PurchaseItem(
                item_name=pr["item_name"],
                item_type=pr["item_type"],
                quantity=pr["plan_qty"],
                unit=pr["unit"],
                unit_price=pr["plan_unit_price"],
                total_price=item_plan_total,
                final_unit_price=pr["fact_unit_price"],
                final_total=pr["fact_total"],
                country_origin=pr["country_origin"],
                feo_category_id=pr["feo_id"],
                contractor_id=pr["cont_id"] if (pr["cont_id"] and pr["cont_id"] != -1) else None,
                contractor_inn=pr["cont_inn"],
                contractor_name=pr["cont_name"],
                vat_rate=str(pr["vat_rate"]) if pr["vat_rate"] else None,
            )
            items.append(pi)

        p.items = items
        db.add(p)
        await db.flush()  # get p.id

        if contract_num:
            existing_keys.add((contract_num, order_no))
            contract_to_purchase[contract_num] = p

        created_purchases += 1
        created_items += len(items)

        # --- Create Payment records from inline rows ---
        if unique_inline:
            # Anti-dup against already-existing payments (freshly flushed purchase has no payments yet)
            existing_pays_q = (await db.execute(
                select(Payment.document_number, Payment.payment_date, Payment.amount)
                .where(Payment.purchase_id == p.id)
            )).all()

            def _pay_fp(dn, pd, am):
                return (
                    str(dn or "").strip(),
                    str(pd or ""),
                    round(float(am), 2) if am is not None else None,
                )

            existing_fps_inline = {_pay_fp(dn, pd, am) for dn, pd, am in existing_pays_q}

            for ip in unique_inline:
                fp = _pay_fp(ip["document_number"], ip["payment_date"], ip["amount"])
                if fp in existing_fps_inline:
                    continue
                existing_fps_inline.add(fp)
                pay_obj = Payment(
                    purchase_id=p.id,
                    document_number=ip["document_number"],
                    payment_date=ip["payment_date"],
                    amount=ip["amount"],
                    payment_purpose=ip["payment_purpose"],
                )
                db.add(pay_obj)
                created_payments += 1

    # --- Process «Платежи» sheet (commit mode) ---
    if commit and parsed_payments:
        pay_by_contract: Dict[str, List[dict]] = defaultdict(list)
        for pp in parsed_payments:
            pay_by_contract[pp["contract_number"]].append(pp)

        for contract_num, pay_list in pay_by_contract.items():
            # Find the Purchase — may be newly created or already existing
            purchase = contract_to_purchase.get(contract_num)
            if purchase is None:
                # Check DB for existing purchases with this contract_number
                existing_p = (await db.execute(
                    select(Purchase).where(
                        Purchase.subsidy_id == sid,
                        Purchase.contract_number == contract_num,
                    )
                )).scalars().first()
                purchase = existing_p

            if purchase is None:
                for pp in pay_list:
                    payments_errors.append({
                        "row": pp["pay_row_num"],
                        "name": contract_num,
                        "message": f"Платёж: закупка с № договора '{contract_num}' не найдена",
                    })
                continue

            # Anti-dup: fingerprints of payments already stored for this purchase
            existing_pays = (await db.execute(
                select(Payment.document_number, Payment.payment_date, Payment.amount)
                .where(Payment.purchase_id == purchase.id)
            )).all()
            def _pay_fp(dn, pd, am):
                return (
                    str(dn or "").strip(),
                    str(pd or ""),
                    round(float(am), 2) if am is not None else None,
                )
            existing_fps = {_pay_fp(dn, pd, am) for dn, pd, am in existing_pays}

            payment_objects = []
            for pp in pay_list:
                fp = _pay_fp(pp["document_number"], pp["payment_date"], pp["amount"])
                if fp in existing_fps:
                    continue
                existing_fps.add(fp)
                pay_obj = Payment(
                    purchase_id=purchase.id,
                    document_number=pp["document_number"],
                    payment_date=pp["payment_date"],
                    amount=pp["amount"],
                    payment_purpose=pp["payment_purpose"],
                )
                db.add(pay_obj)
                payment_objects.append(pay_obj)
                created_payments += 1

            # Update Purchase summary fields from payments
            amounts = [pp["amount"] for pp in pay_list if pp["amount"] is not None]
            dates   = [pp["payment_date"] for pp in pay_list if pp["payment_date"] is not None]
            doc_nums= [pp["document_number"] for pp in pay_list if pp["document_number"]]

            if amounts:
                purchase.payment_amount = sum(amounts)
            if doc_nums:
                purchase.payment_doc_number = doc_nums[0]
            if dates:
                purchase.payment_doc_date = min(dates)

    elif not commit and parsed_payments:
        # Preview mode: validate payment links only
        for pp in parsed_payments:
            contract_num = pp["contract_number"]
            # Check if any parsed group has this contract_number
            matched = any(
                pr["contract_number"] == contract_num
                for pr in parsed_rows
            )
            if not matched and not any(k[0] == contract_num for k in existing_keys):
                payments_errors.append({
                    "row": pp["pay_row_num"],
                    "name": contract_num,
                    "message": f"Платёж: закупка с № договора '{contract_num}' не найдена",
                })

    if commit:
        await db.commit()
        return {
            "created_purchases": created_purchases,
            "created_items": created_items,
            "created_payments": created_payments,
            "skipped": skipped,
            "errors": errors + payments_errors,
        }
    else:
        return {
            "purchases": preview_list,
            "payments_errors": payments_errors,
            "skipped": skipped,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# POST /import
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_purchases_from_excel(
    file: UploadFile = File(...),
    subsidy_id: int = Query(..., description="ID субсидии (обязательно)"),
    db: AsyncSession = Depends(get_db),
):
    """Импорт закупок из Excel. Возвращает {created_purchases, created_items, created_payments, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    return await _parse_and_group(content, subsidy_id, db, commit=True)


# ---------------------------------------------------------------------------
# POST /import/preview
# ---------------------------------------------------------------------------

@router.post("/import/preview")
async def preview_purchases_import(
    file: UploadFile = File(...),
    subsidy_id: int = Query(..., description="ID субсидии (обязательно)"),
    db: AsyncSession = Depends(get_db),
):
    """Превью импорта без сохранения. Возвращает {purchases, payments_errors, skipped, errors}."""
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    return await _parse_and_group(content, subsidy_id, db, commit=False)
