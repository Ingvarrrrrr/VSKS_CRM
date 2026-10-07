"""Единая сборка данных и значений ячеек для экспорта закупок в Excel.

Вынесено из app/routers/purchase_export.py (ПРАВИЛО №6, 07.10.2026): реестр
столбцов (ALL_EXPORT_COLUMNS/DEFAULT_EXPORT_COLUMNS), извлечение значения
одной ячейки по ключу (get_cell_value) и сборка контекста-справочников
(build_purchase_export_ctx) — единственное место, где считаются эти значения.
purchase_export.py импортирует отсюда и использует как было (экспорт закупок
не изменился). app/services/plan_graph_export_data.py и
plan_graph_export_xlsx.py переиспользуют тот же код для группы столбцов
«Договор и оплата» в экспорте плана-графика субсидии — вместо повторного
написания извлечения полей закупки.

Группа «Договор и оплата» в живом плане-графике применяется только к
под-строкам фактических позиций (у них есть purchase_id); сами ключи и
подписи — те же самые ALL_EXPORT_COLUMNS, что и в экспорте закупок (одна
подпись = одно значение, см. feedback_no_duplicate_metrics_same_label)."""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
from app.models.user import User
from app.services.purchase_contractor_display import display_contractor_name as _display_contractor_name
from app.services.dictionaries import (
    PURCHASE_METHOD_LABELS as _PURCHASE_METHOD_LABELS,
    PURCHASE_BASIS_LABELS as _PURCHASE_BASIS_LABELS,
    CONTRACT_TYPE_LABELS as _CONTRACT_TYPE_LABELS,
    STATUS_LABELS as _STATUS_LABELS,
    SUBSTATUS_LABELS as _SUBSTATUS_LABELS,
)
from app.services.acceptance_docs import derived_scalars as _acceptance_derived_scalars
from app.services.purchase_economy import purchase_economy_bulk

# ---------------------------------------------------------------------------
# Реестр столбцов экспорта закупок (ПРАВИЛО №6 — единственное определение;
# app/routers/purchase_export.py и app/services/plan_graph_export_columns.py
# читают ключи/подписи отсюда, не заводят своих копий).
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
    # Владелец (2026-09-20): подпись расходилась с полем — «Предмет закупки»
    # здесь vs «Предмет договора» в списке (OrdersTable.vue) и в
    # field_registry.py (единый справочник полей). Свели к одной подписи.
    "subject":                {"label": "Предмет договора",      "group": "Позиция"},
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


def get_cell_value(key: str, p: Purchase, ctx: dict):
    """Значение одной ячейки экспорта закупок по ключу столбца (см.
    ALL_EXPORT_COLUMNS). `ctx` — справочники, собранные build_purchase_export_ctx
    (contractors, contractor_inns, subsidies, feo_categories, payment_purposes,
    ru_map, sn_map, economy)."""
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
    if key == "economy":
        # ПРАВИЛО №6 (02.10.2026) — расчёт, не колонка БД (см. ctx["economy"] выше).
        _econ = ctx["economy"].get(p.id)
        return float(_econ) if _econ is not None else ""
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
    # Владелец (30.09): авансовый отчёт — контрагент строки = получатель
    # возмещения (или автор/инициатор, если получатель ещё не выбран), а не
    # продавец из чеков. Единственная точка развилки — display_contractor_name
    # (app.services.purchase_contractor_display), переиспользуется и списком
    # закупок (см. purchase_serializers._purchase_to_full) — ПРАВИЛО №6.
    if key == "contractor":
        return _display_contractor_name(
            p,
            contractor_name=ctx["contractors"].get(p.contractor_id),
            reimbursement_user_name=ctx["ru_map"].get(p.reimbursement_user_id),
            service_note_by_name=ctx["sn_map"].get(p.service_note_by),
        ) or ""
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


async def build_purchase_export_ctx(db: AsyncSession, purchases: list[Purchase]) -> dict:
    """Собирает справочники (ctx), нужные get_cell_value, для переданного
    набора закупок `purchases` — contractors/contractor_inns/subsidies/
    feo_categories целиком (как в исходном экспорте закупок — дешёвые общие
    справочники), payment_purposes/ru_map/sn_map/economy — только по
    purchase_ids переданного набора (без лишней нагрузки на маленький набор
    закупок экспорта плана-графика)."""
    contractor_rows = (await db.execute(select(Contractor))).scalars().all()
    contractors = {c.id: c.name for c in contractor_rows}
    contractor_inns = {c.id: (c.inn or "") for c in contractor_rows}
    subsidies_map = {s.id: s.name for s in (await db.execute(select(Subsidy))).scalars().all()}
    feo_map = {f.id: f.name for f in (await db.execute(select(FeoCategory))).scalars().all()}

    purchase_ids = [p.id for p in purchases]
    # ПРАВИЛО №6 (02.10.2026, шаг 3 плана «Деньги субсидии»): Purchase.economy
    # больше не заполняется — колонка «Экономия» в выгрузке считается через
    # purchase_economy_bulk (app.services.purchase_economy), ЕДИНУЮ точку
    # расчёта (planned_total − факт законтрактованных позиций).
    economy_map = {
        pid: bucket["economy"]
        for pid, bucket in (await purchase_economy_bulk(db, purchase_ids)).items()
    }
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

    # Владелец (30.09): те же две карты, что и список закупок (см. purchases.py
    # ru_map/sn_map) — получатель возмещения и фолбэк на автора/инициатора
    # авансового, для колонки "contractor" (display_contractor_name выше).
    ru_ids = [p.reimbursement_user_id for p in purchases if p.reimbursement_user_id]
    ru_map: dict = {}
    if ru_ids:
        res = await db.execute(select(User.id, User.full_name).where(User.id.in_(ru_ids)))
        ru_map = {uid: name for uid, name in res.all()}
    sn_ids = [p.service_note_by for p in purchases if p.service_note_by]
    sn_map: dict = {}
    if sn_ids:
        res = await db.execute(select(User.id, User.full_name, User.username).where(User.id.in_(sn_ids)))
        sn_map = {uid: (fn or un) for uid, fn, un in res.all()}

    return {
        "contractors": contractors,
        "contractor_inns": contractor_inns,
        "subsidies": subsidies_map,
        "feo_categories": feo_map,
        "payment_purposes": payment_purposes,
        "ru_map": ru_map,
        "sn_map": sn_map,
        "economy": economy_map,
    }
