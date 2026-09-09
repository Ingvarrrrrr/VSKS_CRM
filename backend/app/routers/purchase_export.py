"""Purchase export router — Excel export of purchases.

Handles:
  GET  /api/purchases/export/columns   — list available Excel export columns
  GET  /api/purchases/export/excel     — stream .xlsx export of purchases

Also defines ALL_EXPORT_COLUMNS, DEFAULT_EXPORT_COLUMNS and _get_cell_value().
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
from collections import defaultdict

from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
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
from app.services.acceptance_docs import derived_scalars as _acceptance_derived_scalars
from app.services.item_forms import ITEM_FORMS, item_form_for_purchase
from app.services.item_form_summary import item_form_summary, _fmt_datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None

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
    "payment_purpose":        {"label": "Назначение платежа",    "group": "Оплата"},
    "delivery_payment_amount":{"label": "Оплата с доставкой",    "group": "Оплата"},
    "vat_applicable":         {"label": "НДС применяется",       "group": "НДС"},
    "vat_rate":               {"label": "Ставка НДС",            "group": "НДС"},
    "vat_exemption_article":  {"label": "Статья НК РФ",          "group": "НДС"},
    "vat_mode":               {"label": "Режим НДС",             "group": "НДС"},
    "etp_url":                {"label": "Ссылка ЭТП",            "group": "Закупка"},
    "region":                 {"label": "Регион мероприятия",     "group": "Позиция"},
    "delivery_region":        {"label": "Регион поставки",        "group": "Позиция"},
    "delivery_location":      {"label": "Место доставки/услуг",  "group": "Позиция"},
    "delivery_address":       {"label": "Адрес доставки",        "group": "Позиция"},
    "final_unit_price":       {"label": "Факт. цена за ед.",     "group": "Цены"},
    "final_total_amount":     {"label": "Факт. сумма",           "group": "Цены"},
    "contract_end_date":      {"label": "Срок действия договора","group": "Договор"},
    "submission_deadline":    {"label": "Окончание приёма заявок","group": "Договор"},
    "commitment_quarter":     {"label": "Квартал обязательств",  "group": "Оплата"},
    "planned_payment_month":  {"label": "План. месяц платежа",   "group": "Оплата"},
    "payment_month":          {"label": "Месяц платежа",         "group": "Оплата"},
    "stage_label":            {"label": "Этап (подпись)",        "group": "Идентификация"},
    "substatus":              {"label": "Подстатус",             "group": "Идентификация"},
}

DEFAULT_EXPORT_COLUMNS = [
    "purchase_number", "registry_number", "item_name", "item_type", "unit", "quantity",
    "region", "delivery_region", "nmck", "planned_total_price", "contract_price", "final_total_amount", "economy",
    "purchase_method", "contract_number", "contract_date", "contract_end_date",
    "contractor", "contractor_inn", "execution_term", "country_origin",
    "acceptance_doc_name", "acceptance_doc_number", "acceptance_doc_date", "acceptance_doc_amount",
    "payment_doc_number", "payment_doc_date", "payment_amount", "payment_federal", "payment_purpose",
    "status",
]


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
    # ПРАВИЛО №6 (2026-09-05): колонка «НМЦК» — total_nmck (источник истины;
    # nmck — deprecated-алиас, всегда ему равен, см. purchase_money_writer.py).
    # Раньше здесь читался nmck с Python-truthy фолбэком на planned_total_price —
    # своя третья формула вместо одного из двух полей.
    if key == "nmck":                    return float(p.total_nmck) if p.total_nmck else ""
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
    # ПРАВИЛО №6 (2026-09-07, группа D4): закрывающий документ — из JSONB
    # acceptance_docs (первый документ), не напрямую из скаляров.
    if key in ("acceptance_doc_name", "acceptance_doc_number", "acceptance_doc_date", "acceptance_doc_amount"):
        _acc = _acceptance_derived_scalars(p)
        if key == "acceptance_doc_name":     return _acc["name"] or ""
        if key == "acceptance_doc_number":   return _acc["number"] or ""
        if key == "acceptance_doc_date":     return str(_acc["date"]) if _acc["date"] else ""
        if key == "acceptance_doc_amount":   return float(_acc["amount"]) if _acc["amount"] else ""
    if key == "payment_doc_number":      return p.payment_doc_number or ""
    if key == "payment_doc_date":        return str(p.payment_doc_date) if p.payment_doc_date else ""
    if key == "payment_amount":          return float(p.payment_amount) if p.payment_amount else ""
    if key == "payment_federal":         return float(p.payment_federal) if p.payment_federal else ""
    if key == "payment_purpose":         return ctx["payment_purposes"].get(p.id, "")
    if key == "delivery_payment_amount": return float(p.delivery_payment_amount) if p.delivery_payment_amount else ""
    if key == "vat_applicable":          return "Да" if p.vat_applicable else ""
    if key == "vat_rate":                return p.vat_rate if p.vat_rate is not None else ""
    if key == "vat_exemption_article":   return p.vat_exemption_article or ""
    if key == "vat_mode":
        _vat_mode_labels = {"uniform": "Одинаковый", "per_item": "Для каждого товара"}
        return _vat_mode_labels.get(p.vat_mode or "uniform", p.vat_mode or "")
    if key == "etp_url":                 return "" if getattr(p, 'purchase_method', None) == 'advance' else (p.etp_url or "")
    if key == "region":                  return p.region or ""
    if key == "delivery_region":         return p.delivery_region or ""
    if key == "delivery_location":       return p.delivery_location or ""
    if key == "delivery_address":        return p.delivery_address or ""
    if key == "final_unit_price":        return float(p.final_unit_price) if p.final_unit_price else ""
    if key == "final_total_amount":      return float(p.final_total_amount) if p.final_total_amount else ""
    if key == "contract_end_date":       return str(p.contract_end_date) if p.contract_end_date else ""
    if key == "submission_deadline":
        if p.submission_deadline:
            try:
                return str(p.submission_deadline.date()) if hasattr(p.submission_deadline, 'date') else str(p.submission_deadline)
            except Exception:
                return str(p.submission_deadline)
        return ""
    if key == "commitment_quarter":      return p.commitment_quarter if p.commitment_quarter is not None else ""
    if key == "planned_payment_month":   return str(p.planned_payment_month) if p.planned_payment_month else ""
    if key == "payment_month":
        if p.payment_doc_date:
            try:
                d = p.payment_doc_date
                return f"{d.month:02d}.{d.year}"
            except Exception:
                return ""
        return ""
    if key == "stage_label":             return p.stage_label or ""
    if key == "substatus":               return _SUBSTATUS_LABELS.get(p.substatus or "", p.substatus or "")
    return ""


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

    contractor_rows = (await db.execute(select(Contractor))).scalars().all()
    contractors = {c.id: c.name for c in contractor_rows}
    contractor_inns = {c.id: (c.inn or "") for c in contractor_rows}
    subsidies_map = {s.id: s.name for s in (await db.execute(select(Subsidy))).scalars().all()}
    feo_map = {f.id: f.name for f in (await db.execute(select(FeoCategory))).scalars().all()}

    purchase_ids = [p.id for p in purchases]
    payment_purposes: dict[int, str] = {}
    if purchase_ids:
        pay_rows = (
            await db.execute(
                select(Payment)
                .where(Payment.purchase_id.in_(purchase_ids))
                .order_by(Payment.payment_date.asc().nullsfirst(), Payment.id.asc())
            )
        ).scalars().all()
        _pp_map: dict[int, list[str]] = defaultdict(list)
        for pay in pay_rows:
            if pay.payment_purpose and pay.payment_purpose.strip():
                _pp_map[pay.purchase_id].append(pay.payment_purpose.strip())
        payment_purposes = {pid: "; ".join(purposes) for pid, purposes in _pp_map.items()}

    ctx = {
        "contractors": contractors,
        "contractor_inns": contractor_inns,
        "subsidies": subsidies_map,
        "feo_categories": feo_map,
        "payment_purposes": payment_purposes,
    }

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

