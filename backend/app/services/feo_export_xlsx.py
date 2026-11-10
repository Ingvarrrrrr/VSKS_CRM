"""feo_export_xlsx.py — построение книги Excel «Выгрузить ФЭО»
(GET /api/feo-categories/export, задача владельца 20.10.2026).

Вынесено из app.routers.feo_import_export (ПРАВИЛО №5 — роутер тонкий,
только читает параметры/права и зовёт builder). Источник сумм по стадиям —
ЕДИНСТВЕННЫЙ app.services.plan_item_stage (planned_item_stage_segments —
позиции с собственной FeoPlannedItem, category_plan_stage_segments — план на
самой листовой категории без собственной FeoPlannedItem; ПРАВИЛО №6, второй
расчёт стадии закупки здесь не заводится).

Стадии и накопление (владелец 20.10.2026):
  Шкала рангов — app.services.plan_item_stage._STAGE_RANK (in_work < contracted
  < ordered < paid_marked < paid_confirmed). Сумма/доля стадии X = Σ amount/
  share сегментов, чей ранг >= ранга X («дошло до X или дальше»), т.е. ТОТ ЖЕ
  каскадный приём, что app.services.plan_graph_export_xlsx._money_cols_dict
  (contract_cum/ordered_cum/...) — здесь применён к segments[] вместо
  status_sums_map, второй алгоритм каскада не придумываем.
  «Товар поставлен» — НЕ по рангу шкалы (delivered сливается в ordered в
  _resolve_stage), а по отдельному признаку segments[].delivered.
"""
from __future__ import annotations

from typing import Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Protection, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import FormulaRule, CellIsRule
except ImportError:  # pragma: no cover
    Workbook = None
    FormulaRule = None
    CellIsRule = None

from app.services.feo_export_columns import (
    MONEY_KEYS,
    STAGE_AMOUNT_KEYS,
    STAGE_DEFS,
    column_index,
    headers_and_widths,
)
from app.services.plan_item_stage import _STAGE_RANK

HEADER_ROW = 3
DATA_FIRST_ROW = 4
# Формат выгрузки «туда-обратно» (задача владельца 20.10.2026) — лист _meta
# несёт версию формата, читает app.services.feo_roundtrip_import.parse
# (ПРАВИЛО №6: одна константа версии на экспорт и импорт, не дублировать
# строкой по месту).
ROUNDTRIP_FORMAT_VERSION = "feo-export-1"
_ORDERED_RANK = _STAGE_RANK["ordered"]
_DONE_EPS = 0.999


def _stage_amounts(segments: list) -> dict:
    """{stage_key: (amount_sum, share_sum)} по каждой из колонок
    «Стадии» для одного набора segments[] (одна плановая позиция ИЛИ одна
    листовая категория с собственным планом) — см. докстринг модуля."""
    out: dict = {}
    for key, _label in STAGE_DEFS:
        if key == "delivered":
            amt = sum(s["amount"] for s in segments if s.get("delivered"))
            share = sum(s["share"] for s in segments if s.get("delivered"))
        elif key == "purchase_done":
            amt = sum(s["amount"] for s in segments if s.get("purchase_done"))
            share = sum(s["share"] for s in segments if s.get("purchase_done"))
        else:
            rank = _STAGE_RANK[key if key != "ordered_flag" else "ordered"]
            amt = sum(s["amount"] for s in segments if _STAGE_RANK.get(s["stage"], 0) >= rank)
            share = sum(s["share"] for s in segments if _STAGE_RANK.get(s["stage"], 0) >= rank)
        out[key] = (amt, share)
    return out


def _stage_status_label(share: float) -> str:
    if share >= _DONE_EPS:
        return "Да"
    if share > 0:
        return "Частично"
    return "Нет"


def compute_row_stage_values(segments: list, plan_amount: float) -> dict:
    """Проекция segments[] в значения колонок листа: 6 пар («стадия»→Да/
    Частично/Нет, «стадия, ₽») + ordered/to_order/residual (сумма — без
    residual, residual считает вызывающий код формулой/числом).

    Заказано (₽) = сумма стадии "ordered" (накопительно); «Надо заказать» = 0,
    если доля ordered >= 0.999, иначе max(0, План − Заказано) — владелец
    20.10.2026."""
    stage_vals = _stage_amounts(segments)
    out: dict = {}
    for key, _label in STAGE_DEFS:
        amt, share = stage_vals[key]
        out[key] = _stage_status_label(share)
        out[f"{key}_amt"] = round(amt, 2) if abs(amt) > 0.005 else 0.0

    ordered_amt, ordered_share = stage_vals["ordered_flag"]
    out["ordered"] = round(ordered_amt, 2) if abs(ordered_amt) > 0.005 else 0.0
    if ordered_share >= _DONE_EPS:
        out["to_order"] = 0.0
    else:
        out["to_order"] = round(max(0.0, plan_amount - ordered_amt), 2)
    return out


async def load_item_procurement_and_payments(
    db,
    item_ids: list[int],
    leaf_cat_ids: Optional[list[int]] = None,
) -> dict:
    """Загружает данные закупок, договоров и платежей для строк выгрузки ФЭО:
    номер договора, сумма по договору, сумма заказа, номер закупки,
    контрагент, ИНН, дата платежа, номер платёжного документа,
    сумма платёжного документа, назначение платежа, КБК, статус платежа."""
    from sqlalchemy import select, func
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase import Purchase
    from app.models.contract import Contract
    from app.models.contractor import Contractor
    from app.models.payment import Payment
    from app.models.bank_statement import BankPayment

    result: dict = {}
    if not item_ids and not leaf_cat_ids:
        return result

    pi_rows = []
    if item_ids:
        q_pi = (
            select(
                PurchaseItem.feo_planned_item_id,
                PurchaseItem.quantity.label("pi_qty"),
                PurchaseItem.unit_price.label("pi_unit_price"),
                PurchaseItem.final_unit_price.label("pi_final_unit_price"),
                PurchaseItem.total_price.label("pi_total_price"),
                PurchaseItem.final_total.label("pi_final_total"),
                PurchaseItem.contractor_name.label("pi_c_name"),
                PurchaseItem.contractor_inn.label("pi_c_inn"),
                Purchase.id.label("p_id"),
                Purchase.purchase_number,
                Purchase.order_number.label("p_order_number"),
                Purchase.registry_number,
                Purchase.procurement_protocol_number.label("p_protocol_num"),
                Purchase.contract_id,
                Purchase.contract_number.label("p_contract_num"),
                Purchase.contract_price.label("p_contract_price"),
                Purchase.final_total_amount.label("p_final_amt"),
                Purchase.payment_doc_number.label("p_pay_doc"),
                Purchase.payment_doc_date.label("p_pay_date"),
                Purchase.payment_amount.label("p_pay_amt"),
                Purchase.status.label("p_status"),
                Purchase.contractor_id,
                Contractor.name.label("c_name"),
                Contractor.inn.label("c_inn"),
                Contract.number.label("contract_num"),
                Contract.max_amount.label("contract_max_amt"),
            )
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .outerjoin(Contractor, Purchase.contractor_id == Contractor.id)
            .outerjoin(Contract, Purchase.contract_id == Contract.id)
            .where(
                PurchaseItem.feo_planned_item_id.in_(item_ids),
                Purchase.stopped_at.is_(None),
            )
        )
        pi_rows = (await db.execute(q_pi)).all()

    cat_p_rows = []
    if leaf_cat_ids:
        q_cat = (
            select(
                Purchase.feo_category_id,
                Purchase.id.label("p_id"),
                Purchase.purchase_number,
                Purchase.order_number.label("p_order_number"),
                Purchase.registry_number,
                Purchase.procurement_protocol_number.label("p_protocol_num"),
                Purchase.contract_id,
                Purchase.contract_number.label("p_contract_num"),
                Purchase.contract_price.label("p_contract_price"),
                Purchase.final_total_amount.label("p_final_amt"),
                Purchase.payment_doc_number.label("p_pay_doc"),
                Purchase.payment_doc_date.label("p_pay_date"),
                Purchase.payment_amount.label("p_pay_amt"),
                Purchase.status.label("p_status"),
                Purchase.contractor_id,
                Contractor.name.label("c_name"),
                Contractor.inn.label("c_inn"),
                Contract.number.label("contract_num"),
                Contract.max_amount.label("contract_max_amt"),
            )
            .outerjoin(Contractor, Purchase.contractor_id == Contractor.id)
            .outerjoin(Contract, Purchase.contract_id == Contract.id)
            .where(
                Purchase.feo_category_id.in_(leaf_cat_ids),
                Purchase.stopped_at.is_(None),
            )
        )
        cat_p_rows = (await db.execute(q_cat)).all()

    all_c_ids = list({r.contract_id for r in pi_rows if r.contract_id} | {r.contract_id for r in cat_p_rows if r.contract_id})
    contract_orders_totals: dict[int, float] = {}
    if all_c_ids:
        q_c_tot = (
            select(
                Purchase.contract_id,
                func.sum(func.coalesce(Purchase.final_total_amount, Purchase.contract_price, 0)).label("tot"),
            )
            .where(
                Purchase.contract_id.in_(all_c_ids),
                Purchase.stopped_at.is_(None),
            )
            .group_by(Purchase.contract_id)
        )
        for c_id, tot in (await db.execute(q_c_tot)).all():
            contract_orders_totals[c_id] = float(tot or 0.0)

    all_p_ids = list({r.p_id for r in pi_rows} | {r.p_id for r in cat_p_rows})
    payments_by_pid: dict[int, list] = {}
    if all_p_ids:
        q_pay = (
            select(
                Payment.purchase_id,
                Payment.document_number.label("pay_doc"),
                Payment.payment_date.label("pay_date"),
                Payment.amount.label("pay_amt"),
                Payment.payment_purpose.label("pay_purpose"),
                Payment.expense_code.label("pay_expense_code"),
                BankPayment.payment_number.label("bp_num"),
                BankPayment.payment_date.label("bp_date"),
                BankPayment.amount.label("bp_amt"),
                BankPayment.purpose_text.label("bp_purpose"),
                BankPayment.parsed_kbk,
                BankPayment.expense_code,
                BankPayment.raw_json.label("bp_raw_json"),
                BankPayment.status.label("bp_status"),
                BankPayment.payee_name.label("bp_payee_name"),
                BankPayment.payee_inn.label("bp_payee_inn"),
            )
            .outerjoin(BankPayment, Payment.bank_payment_id == BankPayment.id)
            .where(Payment.purchase_id.in_(all_p_ids))
        )
        pay_rows = (await db.execute(q_pay)).all()
        for pr in pay_rows:
            payments_by_pid.setdefault(pr.purchase_id, []).append(pr)

    def _make_bucket():
        return {
            "purchases": set(), "contractors": set(), "inns": set(),
            "contracts": set(), "contract_amounts": set(), "contract_residuals": set(),
            "order_amount": 0.0,
            "fact_amount": 0.0,
            "purchase_totals_by_pid": {},
            "seen_p_ids": set(),
            "fact_quantities": [], "fact_unit_prices": [], "order_numbers": set(),
            "protocol_numbers": set(),
            "docs": set(), "dates": set(), "total_paid": 0.0,
            "purposes": set(), "kbk": set(), "expense_groups": set(), "statuses": set(),
        }

    def _format_bucket(b: dict) -> dict:
        p_num = ", ".join(sorted(b["purchases"])) if b["purchases"] else ""
        c_name = ", ".join(sorted(b["contractors"])) if b["contractors"] else ""
        c_inn = ", ".join(sorted(b["inns"])) if b["inns"] else ""
        c_doc = ", ".join(sorted(b["contracts"])) if b["contracts"] else ""
        c_amt = max(b["contract_amounts"]) if b["contract_amounts"] else 0.0
        c_res = max(b["contract_residuals"]) if b["contract_residuals"] else 0.0
        p_amt = sum(b["purchase_totals_by_pid"].values()) if b["purchase_totals_by_pid"] else 0.0
        expense_grp = ", ".join(sorted(b["expense_groups"])) if b["expense_groups"] else ""
        pay_doc = ", ".join(sorted(b["docs"])) if b["docs"] else ""
        pay_dt = ", ".join(sorted(b["dates"])) if b["dates"] else ""
        pay_amt = round(b["total_paid"], 2) if b["total_paid"] > 0 else ""
        pay_purpose = "; ".join(sorted(b["purposes"])) if b["purposes"] else ""
        pay_kbk = ", ".join(sorted(b["kbk"])) if b["kbk"] else ""
        pay_status = ", ".join(sorted(b["statuses"])) if b["statuses"] else ""
        fact_q = sum(b["fact_quantities"]) if b["fact_quantities"] else ""
        fact_up = round(b["fact_unit_prices"][0], 2) if b["fact_unit_prices"] else ""
        order_no = ", ".join(sorted(b["order_numbers"])) if b["order_numbers"] else ""
        proto_no = ", ".join(sorted(b["protocol_numbers"])) if b["protocol_numbers"] else ""
        return {
            "contract_number": c_doc,
            "contract_amount": round(c_amt, 2) if c_amt > 0 else "",
            "contract_residual": round(c_res, 2) if c_res > 0 else "",
            "order_amount": round(b["order_amount"], 2) if b["order_amount"] > 0 else "",
            "purchase_number": p_num,
            "order_number": order_no,
            "procurement_protocol_number": proto_no,
            "purchase_amount": round(p_amt, 2) if p_amt > 0 else "",
            "contractor_name": c_name,
            "contractor_inn": c_inn,
            "fact_qty": fact_q,
            "fact_unit_price": fact_up,
            "fact_amount": round(b["fact_amount"], 2) if b["fact_amount"] > 0 else "",
            "paid_amount_money": pay_amt,
            "payment_doc_number": pay_doc,
            "payment_date": pay_dt,
            "payment_amount": pay_amt,
            "expense_group_code": expense_grp,
            "payment_kbk": pay_kbk,
            "payment_purpose": pay_purpose,
            "payment_status": pay_status,
        }

    buckets: dict = {}
    for r in pi_rows:
        b = buckets.setdefault(r.feo_planned_item_id, _make_bucket())
        p_num = str(r.purchase_number) if r.purchase_number is not None else (r.registry_number or f"#{r.p_id}")
        if p_num:
            b["purchases"].add(p_num)
        p_tot = float(r.p_final_amt or r.p_contract_price or 0.0)
        if p_tot > 0:
            b["purchase_totals_by_pid"][r.p_id] = p_tot
        c_name = r.c_name or getattr(r, "pi_c_name", None)
        c_inn = r.c_inn or getattr(r, "pi_c_inn", None)
        if c_name:
            b["contractors"].add(c_name)
        if c_inn:
            b["inns"].add(c_inn)

        c_num = r.contract_num or r.p_contract_num
        if c_num:
            b["contracts"].add(str(c_num))

        if r.p_order_number:
            b["order_numbers"].add(str(r.p_order_number))

        if getattr(r, "p_protocol_num", None):
            b["protocol_numbers"].add(str(r.p_protocol_num))

        is_contracted = (r.p_status in ("contracted", "ordered", "delivered", "paid")) or bool(
            r.contract_num or getattr(r, "p_contract_num", None) or r.contract_id
        )
        has_final_price = (
            getattr(r, "pi_final_unit_price", None) is not None
            or getattr(r, "pi_final_total", None) is not None
        )

        if is_contracted or has_final_price:
            if r.pi_qty is not None and float(r.pi_qty) > 0:
                b["fact_quantities"].append(float(r.pi_qty))
            f_up = r.pi_final_unit_price if r.pi_final_unit_price is not None else r.pi_unit_price
            if f_up is not None and float(f_up) > 0:
                b["fact_unit_prices"].append(float(f_up))

            if r.pi_final_total is not None and float(r.pi_final_total) > 0:
                fact_item_amt = float(r.pi_final_total)
            elif r.pi_total_price is not None and float(r.pi_total_price) > 0:
                fact_item_amt = float(r.pi_total_price)
            else:
                fact_item_amt = float(r.p_final_amt or r.p_contract_price or 0.0)
            b["fact_amount"] += fact_item_amt

        if r.pi_final_total is not None and float(r.pi_final_total) > 0:
            item_amt = float(r.pi_final_total)
        elif r.pi_total_price is not None and float(r.pi_total_price) > 0:
            item_amt = float(r.pi_total_price)
        else:
            item_amt = float(r.p_final_amt or r.p_contract_price or 0.0)
        b["order_amount"] += item_amt

        if r.p_id not in b["seen_p_ids"]:
            b["seen_p_ids"].add(r.p_id)
            c_tot = 0.0
            c_res = 0.0
            if r.contract_max_amt is not None and float(r.contract_max_amt) > 0:
                c_tot = float(r.contract_max_amt)
                orders_sum = contract_orders_totals.get(r.contract_id, float(r.p_final_amt or r.p_contract_price or 0.0))
                c_res = max(0.0, c_tot - orders_sum)
            elif r.contract_id and r.contract_id in contract_orders_totals:
                c_tot = contract_orders_totals[r.contract_id]
            elif r.p_final_amt or r.p_contract_price:
                c_tot = float(r.p_final_amt or r.p_contract_price or 0.0)
            if c_tot > 0:
                b["contract_amounts"].add(c_tot)
            if c_res > 0:
                b["contract_residuals"].add(c_res)

        p_pays = payments_by_pid.get(r.p_id, [])
        if p_pays:
            for pay in p_pays:
                doc = pay.bp_num or pay.pay_doc
                if doc: b["docs"].add(str(doc))
                dt = pay.bp_date or pay.pay_date
                if dt: b["dates"].add(dt.strftime("%d.%m.%Y"))
                amt = pay.bp_amt if pay.bp_amt is not None else pay.pay_amt
                if amt and float(amt) > 0:
                    b["total_paid"] += float(amt)
                purp = pay.bp_purpose or pay.pay_purpose
                if purp: b["purposes"].add(str(purp).strip()[:150])
                kbk_val = pay.expense_code or pay.parsed_kbk
                if kbk_val: b["kbk"].add(str(kbk_val))
                # Недетализированный код расходов (200 / 300)
                short_code = None
                raw_j = pay.bp_raw_json
                if raw_j and isinstance(raw_j, dict):
                    short_code = raw_j.get("КОД РАСХОДОВ") or raw_j.get("Код расходов")
                if not short_code:
                    ec = pay.expense_code or getattr(pay, "pay_expense_code", None)
                    if ec:
                        ec_str = str(ec).strip()
                        short_code = ec_str[:4] if len(ec_str) >= 4 else ec_str
                if short_code:
                    b["expense_groups"].add(str(short_code))
                st = pay.bp_status or "Оплачено"
                if st: b["statuses"].add(str(st))
                if not c_name and pay.bp_payee_name: b["contractors"].add(pay.bp_payee_name)
                if not c_inn and pay.bp_payee_inn: b["inns"].add(pay.bp_payee_inn)
        else:
            if r.p_pay_doc: b["docs"].add(str(r.p_pay_doc))
            if r.p_pay_date: b["dates"].add(r.p_pay_date.strftime("%d.%m.%Y"))
            if r.p_pay_amt and float(r.p_pay_amt) > 0:
                b["total_paid"] += float(r.p_pay_amt)

    for r in cat_p_rows:
        b = buckets.setdefault(f"c{r.feo_category_id}", _make_bucket())
        p_num = str(r.purchase_number) if r.purchase_number is not None else (r.registry_number or f"#{r.p_id}")
        if p_num:
            b["purchases"].add(p_num)
        p_tot = float(r.p_final_amt or r.p_contract_price or 0.0)
        if p_tot > 0:
            b["purchase_totals_by_pid"][r.p_id] = p_tot
        c_name = r.c_name
        c_inn = r.c_inn
        if c_name: b["contractors"].add(c_name)
        if c_inn: b["inns"].add(c_inn)

        c_num = r.contract_num or r.p_contract_num
        if c_num:
            b["contracts"].add(str(c_num))

        if r.p_order_number:
            b["order_numbers"].add(str(r.p_order_number))

        if getattr(r, "p_protocol_num", None):
            b["protocol_numbers"].add(str(r.p_protocol_num))

        is_contracted = (r.p_status in ("contracted", "ordered", "delivered", "paid")) or bool(
            r.contract_num or getattr(r, "p_contract_num", None) or r.contract_id
        )
        item_amt = float(r.p_final_amt or r.p_contract_price or 0.0)
        b["order_amount"] += item_amt
        if is_contracted:
            b["fact_amount"] += item_amt

        if r.p_id not in b["seen_p_ids"]:
            b["seen_p_ids"].add(r.p_id)
            c_tot = 0.0
            c_res = 0.0
            if r.contract_max_amt is not None and float(r.contract_max_amt) > 0:
                c_tot = float(r.contract_max_amt)
                orders_sum = contract_orders_totals.get(r.contract_id, float(r.p_final_amt or r.p_contract_price or 0.0))
                c_res = max(0.0, c_tot - orders_sum)
            elif r.contract_id and r.contract_id in contract_orders_totals:
                c_tot = contract_orders_totals[r.contract_id]
            elif r.p_final_amt or r.p_contract_price:
                c_tot = float(r.p_final_amt or r.p_contract_price or 0.0)
            if c_tot > 0:
                b["contract_amounts"].add(c_tot)
            if c_res > 0:
                b["contract_residuals"].add(c_res)

        p_pays = payments_by_pid.get(r.p_id, [])
        if p_pays:
            for pay in p_pays:
                doc = pay.bp_num or pay.pay_doc
                if doc: b["docs"].add(str(doc))
                dt = pay.bp_date or pay.pay_date
                if dt: b["dates"].add(dt.strftime("%d.%m.%Y"))
                amt = pay.bp_amt if pay.bp_amt is not None else pay.pay_amt
                if amt and float(amt) > 0:
                    b["total_paid"] += float(amt)
                purp = pay.bp_purpose or pay.pay_purpose
                if purp: b["purposes"].add(str(purp).strip()[:150])
                kbk_val = pay.expense_code or pay.parsed_kbk
                if kbk_val: b["kbk"].add(str(kbk_val))
                short_code = None
                raw_j = pay.bp_raw_json
                if raw_j and isinstance(raw_j, dict):
                    short_code = raw_j.get("КОД РАСХОДОВ") or raw_j.get("Код расходов")
                if not short_code:
                    ec = pay.expense_code or getattr(pay, "pay_expense_code", None)
                    if ec:
                        ec_str = str(ec).strip()
                        short_code = ec_str[:4] if len(ec_str) >= 4 else ec_str
                if short_code:
                    b["expense_groups"].add(str(short_code))
                st = pay.bp_status or "Оплачено"
                if st: b["statuses"].add(str(st))
                if not c_name and pay.bp_payee_name: b["contractors"].add(pay.bp_payee_name)
                if not c_inn and pay.bp_payee_inn: b["inns"].add(pay.bp_payee_inn)

    return {k: _format_bucket(v) for k, v in buckets.items()}


async def build_feo_export_workbook(db, sub, selected_keys: list, with_summary: bool = False):
    """Строит openpyxl.Workbook «Выгрузить ФЭО» по субсидии `sub` (столбцы —
    `selected_keys`, см. app.services.feo_export_columns). Единственная точка
    обращения к БД для этой выгрузки — одна выборка категорий, одна выборка
    позиций (_active_feo_items_with_amount), один вызов
    planned_item_stage_segments на ВСЕ позиции субсидии и один вызов
    category_plan_stage_segments на ВСЕ листовые категории (не в цикле —
    задача владельца, п.3: «одним вызовом на все позиции субсидии»).

    Само рисование дерева по готовым данным (без обращения к БД) — в
    render_feo_tree_sheet ниже, ПРАВИЛО №6: шаблон «Загрузить выгрузку ФЭО»
    (app.routers.feo_roundtrip_import, GET .../roundtrip/template) зовёт ТОТ
    ЖЕ render_feo_tree_sheet с вымышленным деревом в памяти вместо второй
    копии оформления/формул."""
    if Workbook is None:
        raise RuntimeError("openpyxl не установлен")

    from sqlalchemy import select
    from app.models.feo_category import FeoCategory
    from app.services.subsidy_budget import _active_feo_items_with_amount
    from app.services.plan_item_stage import (
        category_plan_stage_segments,
        planned_item_stage_segments,
    )

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == sub.id)
        .order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()
    cat_ids = [c.id for c in cats]

    from app.models.feo_planned_item import FeoPlannedItem
    from sqlalchemy import or_, and_, exists

    # Проверяем, есть ли у субсидии позиции с явно заданным feo_amount.
    # Если да (субсидии со строгим разделением ФЭО и плана) — выгружаем позиции ФЭО (feo_amount is not None).
    # Если нет (субсидии, где план = ФЭО, напр. ДНР) — выгружаем все активные позиции (is_active == True).
    has_explicit_feo = (await db.execute(
        select(exists().where(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active == True,
            FeoPlannedItem.feo_amount.is_not(None),
        ))
    )).scalar()

    if has_explicit_feo:
        feo_items_filter = and_(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active == True,
            FeoPlannedItem.feo_amount.is_not(None),
        )
    else:
        feo_items_filter = and_(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active == True,
        )

    feo_items = (await db.execute(
        select(FeoPlannedItem).where(feo_items_filter)
    )).scalars().all()
    items_by_cat: dict = {}
    for it in sorted(feo_items, key=lambda x: (x.sort_order is None, x.sort_order or 0, x.id)):
        items_by_cat.setdefault(it.feo_category_id, []).append(it)

    by_id = {c.id: {"cat": c, "children": []} for c in cats}
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(by_id[c.id])
        else:
            roots.append(by_id[c.id])

    leaf_cat_ids = [c.id for c in cats if not by_id[c.id]["children"]]
    item_ids = [it.id for it in feo_items]
    item_segments_map = await planned_item_stage_segments(db, item_ids)
    cat_segments_map = await category_plan_stage_segments(db, leaf_cat_ids)
    procurement_map = await load_item_procurement_and_payments(db, item_ids, leaf_cat_ids)

    wb = Workbook()
    ws, top_rows, last_row = render_feo_tree_sheet(
        wb, sub.name[:31], selected_keys, roots, items_by_cat,
        item_segments_map, cat_segments_map, totals_label=f"{sub.name} — итого всего",
        procurement_map=procurement_map,
    )

    if with_summary:
        from app.services.feo_export_summary import write_feo_summary_and_dashboard
        top_rows_info = [{"name": root["cat"].name, "row": tr} for root, tr in zip(roots, top_rows)]
        write_feo_summary_and_dashboard(wb, sub, ws.title, selected_keys, top_rows_info)

    _write_roundtrip_meta_sheet(wb, sub.id)

    return wb


def render_feo_tree_sheet(
    wb, sheet_title: str, selected_keys: list, roots: list,
    items_by_cat: dict, item_segments_map: dict, cat_segments_map: dict,
    *, totals_label: str, include_row_ids: bool = True,
    procurement_map: Optional[dict] = None,
):
    """Рисует дерево категорий/позиций на активном листе новой книги `wb` —
    ЕДИНСТВЕННОЕ место, которое знает оформление/формулы выгрузки «Выгрузить
    ФЭО» (ПРАВИЛО №6). Без обращения к БД: `roots`/`items_by_cat` — те же
    структуры, что строит build_feo_export_workbook (`cat`-объекты нужны
    атрибуты name/code/appendix/budget/is_active/level/id; `item`-объекты —
    name/quantity/unit/feo_amount/amount/is_active/id), `item_segments_map`/
    `cat_segments_map` — {id: {"segments": [...]}}  (пустой словарь — у строк
    просто не будет накопленных стадий, безопасно для вымышленного дерева
    шаблона). `id` объекта нужен настоящим (хотя бы синтетическим уникальным),
    чтобы items_by_cat.get(c.id)/сегменты работали, НО колонка «№ в системе»
    в файле всё равно пишется пустой у всех строк — пример в шаблоне
    «Загрузить выгрузку ФЭО» (GET .../roundtrip/template) весь состоит из
    НОВЫХ строк (include_row_ids=False, см. app.routers.feo_roundtrip_import).

    Возвращает (ws, top_rows, last_row) — top_rows/last_row нужны вызывающему
    коду только для необязательных листов «Сводная»/«Дашборд» выгрузки."""
    ws = wb.active
    ws.title = sheet_title
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.sheet_view.showGridLines = True

    THIN_BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    HEADER_FILL = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
    L1_FILL = PatternFill(start_color="9DC3E6", end_color="9DC3E6", fill_type="solid")
    L2_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
    L3_FILL = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
    L4_FILL = PatternFill(start_color="EEF4FB", end_color="EEF4FB", fill_type="solid")

    # Палитра градиента от жёлтого к зелёному (задача владельца 03.11.2026)
    FILL_CONFIRMED = PatternFill(start_color="86EFAC", end_color="86EFAC", fill_type="solid")  # насыщенный зелёный (Подтверждено выпиской)
    FILL_MARKED = PatternFill(start_color="A7F3D0", end_color="A7F3D0", fill_type="solid")     # светло-зелёный (Оплачено по отметке)
    FILL_ORDERED = PatternFill(start_color="D9F99D", end_color="D9F99D", fill_type="solid")   # лайм / жёлто-зелёный (Товар заказан)
    FILL_IN_WORK = PatternFill(start_color="FEF08A", end_color="FEF08A", fill_type="solid")   # тёплый жёлтый (Закупка в работе)
    FILL_PLAN = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")      # светло-жёлтый (Запланировано)

    # Цвета для условного форматирования ячеек «Да» / «Нет» и колонок факта
    FILL_YES_GREEN = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    FONT_YES_GREEN = Font(color="166534", bold=True)
    FILL_NO_RED = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    FONT_NO_RED = Font(color="991B1B")

    FILL_DIFF_RED = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    FONT_DIFF_RED = Font(color="991B1B")
    FILL_DIFF_GREEN = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    FONT_DIFF_GREEN = Font(color="166534")

    BOLD_FONT = Font(bold=True)
    SEMI_FONT = Font(bold=False)
    ITEM_FONT = Font(italic=True, color="475569")
    TOTAL_FONT = Font(bold=True, color="1E3A5F")
    NUM_FMT = "#,##0.00"
    _MAX_OUTLINE = 7

    headers, widths = headers_and_widths(selected_keys)
    n_cols = len(selected_keys)

    ws.cell(row=1, column=1, value=totals_label).font = TOTAL_FONT
    ws.cell(row=2, column=1, value="Итого по фильтру").font = TOTAL_FONT
    for c in range(1, n_cols + 1):
        ws.cell(row=1, column=c).border = THIN_BORDER
        ws.cell(row=2, column=c).border = THIN_BORDER

    for col_idx, (header, width) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[HEADER_ROW].height = 36
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    # Уникальный хэш / ID строки (задача владельца 03.11.2026):
    # колонка видна в конце таблицы, заблокирована от ручного редактирования.
    ci_row_id = column_index(selected_keys, "row_id")

    row_num = DATA_FIRST_ROW

    def _write_row(values: dict, fill, font) -> int:
        nonlocal row_num
        for ci, key in enumerate(selected_keys, 1):
            val = values.get(key, "")
            cell = ws.cell(row=row_num, column=ci, value=val if val != "" else None)
            if fill:
                cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            cell.protection = Protection(locked=(key == "row_id"))
            if key in MONEY_KEYS and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        r = row_num
        row_num += 1
        return r

    def write_item_row(item, depth, ancestors=None):
        ancestors = ancestors or []
        dir_val = ancestors[0] if len(ancestors) > 0 else ""
        type_val = ancestors[1] if len(ancestors) > 1 else ""
        subdir_val = ancestors[2] if len(ancestors) > 2 else (ancestors[-1] if len(ancestors) > 0 else "")

        plan_amount = float(item.amount) if item.amount is not None else 0.0
        feo_amount = float(item.feo_amount) if item.feo_amount is not None else (plan_amount if plan_amount > 0 else None)
        feo_unit_price = getattr(item, "feo_unit_price", None) or getattr(item, "unit_price", None)
        plan_unit_price = getattr(item, "unit_price", None)
        feo_quantity = getattr(item, "feo_quantity", None) or getattr(item, "quantity", None)
        segments = item_segments_map.get(item.id, {}).get("segments", [])
        stage_vals = compute_row_stage_values(segments, plan_amount)
        ordered_amt = stage_vals["ordered"]
        to_order = stage_vals["to_order"]
        proc = (procurement_map or {}).get(item.id, {})

        in_w = stage_vals.get("in_work", "Нет")
        cont = stage_vals.get("contracted", "Нет")
        ord_f = stage_vals.get("ordered_flag", "Нет")
        deliv = stage_vals.get("delivered", "Нет")
        paid_m = stage_vals.get("paid_marked", "Нет")
        paid_c = stage_vals.get("paid_confirmed", "Нет")
        is_done = stage_vals.get("purchase_done", "Нет")
        prot = "Да" if (cont == "Да" or proc.get("procurement_protocol_number")) else "Нет"

        if paid_c == "Да" or paid_m == "Да":
            st_name = "Оплачено"
        elif deliv == "Да":
            st_name = "Товар поставлен"
        elif ord_f == "Да":
            st_name = "Товар заказан"
        elif cont == "Да":
            st_name = "Договор заключен"
        elif is_done == "Да":
            st_name = "Закупка проведена"
        elif in_w == "Да":
            st_name = "Ведётся работа"
        else:
            st_name = "План закупок"

        item_raw_type = getattr(item, "item_type", "")
        if not item_raw_type:
            low_n = item.name.lower()
            if any(k in low_n for k in ("услуг", "работ", "аренд", "перевоз", "проживан", "монтаж", "ремонт")):
                item_raw_type = "Услуги"
            else:
                item_raw_type = "Товары"
        elif item_raw_type.lower().startswith("услуг"):
            item_raw_type = "Услуги"
        elif item_raw_type.lower().startswith("товар"):
            item_raw_type = "Товары"
        elif item_raw_type.lower().startswith("работ"):
            item_raw_type = "Работы"

        # Оплачено в деньгах по данной конкретной позиции:
        # Берём фактическую оплату именно этой позиции из сегментов стадий (paid_confirmed_amt или paid_marked_amt).
        # Это исключает раздувание суммы при объединении нескольких товаров в одну общую закупку/платёж.
        item_paid_amt = stage_vals.get("paid_confirmed_amt") or stage_vals.get("paid_marked_amt")
        if item_paid_amt is None or float(item_paid_amt) == 0.0:
            if stage_vals.get("paid_confirmed") == "Да" or stage_vals.get("paid_marked") == "Да":
                item_paid_amt = proc.get("fact_amount") or plan_amount
            else:
                raw_paid = proc.get("paid_amount_money")
                if raw_paid and float(raw_paid) > 0:
                    fact_amt = proc.get("fact_amount") or plan_amount
                    item_paid_amt = min(float(fact_amt), float(raw_paid)) if fact_amt else float(raw_paid)
                else:
                    item_paid_amt = ""
        else:
            item_paid_amt = round(float(item_paid_amt), 2)

        values = {
            "feo_direction": dir_val,
            "feo_type": type_val,
            "feo_subdirection": subdir_val,
            "name": "  " * depth + item.name,
            "feo_unit": item.unit or "",
            "plan_qty": float(item.quantity) if item.quantity is not None else "",
            "plan_unit_price": float(plan_unit_price) if plan_unit_price is not None else "",
            "plan": plan_amount,
            "notes": getattr(item, "notes", "") or "",
            "stage_status": st_name,
            "item_type": item_raw_type,
            "is_in_plan": "Да",
            "in_work": in_w,
            "purchase_done": is_done,
            "protocol_signed": prot,
            "contracted": cont,
            "ordered_flag": ord_f,
            "delivered": deliv,
            "paid_marked": paid_m,
            "paid_confirmed": paid_c,
            "fact_qty": proc.get("fact_qty", ""),
            "fact_unit_price": proc.get("fact_unit_price", ""),
            "fact_amount": proc.get("fact_amount", ""),
            "paid_amount_money": item_paid_amt,
            "purchase_number": proc.get("purchase_number", ""),
            "order_number": proc.get("order_number", ""),
            "contractor_name": proc.get("contractor_name", ""),
            "contractor_inn": proc.get("contractor_inn", ""),
            "contract_number": proc.get("contract_number", ""),
            "contract_amount": proc.get("contract_amount", ""),
            "contract_residual": proc.get("contract_residual", ""),
            "purchase_amount": proc.get("purchase_amount", ""),
            "order_amount": proc.get("order_amount", ""),
            "payment_doc_number": proc.get("payment_doc_number", ""),
            "payment_date": proc.get("payment_date", ""),
            "payment_amount": proc.get("payment_amount", ""),
            "expense_group_code": proc.get("expense_group_code", ""),
            "payment_kbk": proc.get("payment_kbk", ""),
            "payment_purpose": proc.get("payment_purpose", ""),
            "payment_status": proc.get("payment_status", ""),
            "feo_qty": float(feo_quantity) if feo_quantity is not None else "",
            "feo_unit_price": float(feo_unit_price) if feo_unit_price is not None else "",
            "feo": feo_amount if feo_amount is not None else "",
            "active": "Да" if item.is_active else "Нет",
            "row_type": "Позиция",
            "row_id": (f"p{item.id}" if item.id is not None else "") if include_row_ids else "",
            **stage_vals,
        }
        # Градиент от жёлтого к зелёному в зависимости от стадии (задача владельца 03.11.2026)
        if stage_vals.get("paid_confirmed") == "Да":
            row_fill = FILL_CONFIRMED
        elif stage_vals.get("paid_marked") == "Да":
            row_fill = FILL_MARKED
        elif stage_vals.get("ordered_flag") == "Да" or ordered_amt > 0:
            row_fill = FILL_ORDERED
        elif stage_vals.get("in_work") == "Да":
            row_fill = FILL_IN_WORK
        elif plan_amount > 0:
            row_fill = FILL_PLAN
        else:
            row_fill = None

        row_idx = _write_row(values, row_fill, ITEM_FONT)

        # Сохранение формул произведения количества на цену (задача владельца):
        # 1. План: кол-во по плану * цена по плану
        ci_plan = column_index(selected_keys, "plan")
        ci_plan_qty = column_index(selected_keys, "plan_qty")
        ci_plan_price = column_index(selected_keys, "plan_unit_price")
        if (
            ci_plan is not None
            and ci_plan_qty is not None
            and ci_plan_price is not None
            and item.quantity is not None
            and plan_unit_price is not None
        ):
            lpq = ws.cell(row_idx, ci_plan_qty).column_letter
            lpp = ws.cell(row_idx, ci_plan_price).column_letter
            ws.cell(row_idx, ci_plan, value=f"={lpq}{row_idx}*{lpp}{row_idx}").number_format = NUM_FMT

        # 2. Факт сумма: факт кол-во * факт цена (если закупка состоялась и есть факт кол-во и цена)
        ci_fact_amt = column_index(selected_keys, "fact_amount")
        ci_fact_qty = column_index(selected_keys, "fact_qty")
        ci_fact_price = column_index(selected_keys, "fact_unit_price")
        if (
            ci_fact_amt is not None
            and ci_fact_qty is not None
            and ci_fact_price is not None
        ):
            fq = proc.get("fact_qty")
            fup = proc.get("fact_unit_price")
            if fq not in (None, "") and fup not in (None, "") and float(fq) > 0 and float(fup) > 0:
                lfq = ws.cell(row_idx, ci_fact_qty).column_letter
                lfup = ws.cell(row_idx, ci_fact_price).column_letter
                ws.cell(row_idx, ci_fact_amt, value=f"={lfq}{row_idx}*{lfup}{row_idx}").number_format = NUM_FMT

        # 3. ФЭО: кол-во по ФЭО * цена по ФЭО
        ci_feo = column_index(selected_keys, "feo")
        ci_feo_qty = column_index(selected_keys, "feo_qty")
        ci_feo_price = column_index(selected_keys, "feo_unit_price")
        if (
            ci_feo is not None
            and ci_feo_qty is not None
            and ci_feo_price is not None
            and feo_quantity is not None
            and feo_unit_price is not None
        ):
            lfqty = ws.cell(row_idx, ci_feo_qty).column_letter
            lfprice = ws.cell(row_idx, ci_feo_price).column_letter
            ws.cell(row_idx, ci_feo, value=f"={lfqty}{row_idx}*{lfprice}{row_idx}").number_format = NUM_FMT
        ci_feo = column_index(selected_keys, "feo")
        ci_ordered = column_index(selected_keys, "ordered")
        ci_to_order = column_index(selected_keys, "to_order")
        ci_residual = column_index(selected_keys, "residual")
        if ci_residual is not None:
            if ci_feo is not None and ci_ordered is not None and ci_to_order is not None:
                lf, lo, lt = (ws.cell(row_idx, c).column_letter for c in (ci_feo, ci_ordered, ci_to_order))
                ws.cell(row_idx, ci_residual, value=f"={lf}{row_idx}-{lo}{row_idx}-{lt}{row_idx}")
            else:
                feo_val = feo_amount if feo_amount is not None else 0.0
                ws.cell(row_idx, ci_residual, value=round(feo_val - ordered_amt - to_order, 2))
            ws.cell(row_idx, ci_residual).number_format = NUM_FMT
        ws.row_dimensions[row_idx].outline_level = min(depth, _MAX_OUTLINE)
        ws.row_dimensions[row_idx].hidden = False
        return row_idx

    def _money_subtotal(row_idx: int, child_rows: list) -> None:
        """Денежные/стадийные столбцы строки-категории = SUM(прямые дети)."""
        keys = (
            "plan", "fact_amount", "paid_amount_money", "order_amount",
            "feo", "ordered", "to_order", "residual",
        ) + STAGE_AMOUNT_KEYS
        for key in keys:
            ci = column_index(selected_keys, key)
            if ci is None or not child_rows:
                continue
            col_letter = ws.cell(row=row_idx, column=ci).column_letter
            refs = ",".join(f"{col_letter}{cr}" for cr in child_rows)
            cell = ws.cell(row_idx, ci, value=f"=SUM({refs})")
            cell.number_format = NUM_FMT
            cell.border = THIN_BORDER

    def write_node(node, depth=0, ancestors=None):
        ancestors = ancestors or []
        c = node["cat"]
        dir_val = ancestors[0] if len(ancestors) > 0 else c.name
        type_val = ancestors[1] if len(ancestors) > 1 else (c.name if len(ancestors) == 1 else "")
        subdir_val = ancestors[2] if len(ancestors) > 2 else (c.name if len(ancestors) >= 2 else "")

        has_own_items = bool(items_by_cat.get(c.id))
        has_subcats = bool(node["children"])
        is_leaf = not has_own_items and not has_subcats
        leaf_segments = cat_segments_map.get(c.id, {}).get("segments", []) if is_leaf else []
        own_plan = sum(float(s["amount"]) for s in leaf_segments) if leaf_segments else 0.0
        stage_vals = compute_row_stage_values(leaf_segments, own_plan) if is_leaf else {}

        values = {
            "feo_direction": dir_val,
            "feo_type": type_val,
            "feo_subdirection": subdir_val,
            "name": "  " * depth + c.name,
            "code": c.code or "",
            "app": c.appendix or "",
            "feo": float(c.budget) if c.budget is not None else "",
            "active": "Да" if c.is_active else "Нет",
            "row_type": "Категория без позиций" if is_leaf else "Категория",
            "row_id": (f"c{c.id}" if c.id is not None else "") if include_row_ids else "",
        }
        if is_leaf:
            values["plan"] = own_plan
            values["is_in_plan"] = "Да"
            values.update(stage_vals)
            cat_proc = (procurement_map or {}).get(f"c{c.id}", {})
            values.update({
                "fact_qty": cat_proc.get("fact_qty", ""),
                "fact_unit_price": cat_proc.get("fact_unit_price", ""),
                "fact_amount": cat_proc.get("fact_amount", ""),
                "paid_amount_money": cat_proc.get("paid_amount_money", ""),
                "purchase_number": cat_proc.get("purchase_number", ""),
                "order_number": cat_proc.get("order_number", ""),
                "contractor_name": cat_proc.get("contractor_name", ""),
                "contractor_inn": cat_proc.get("contractor_inn", ""),
                "contract_number": cat_proc.get("contract_number", ""),
                "contract_amount": cat_proc.get("contract_amount", ""),
                "contract_residual": cat_proc.get("contract_residual", ""),
                "purchase_amount": cat_proc.get("purchase_amount", ""),
                "order_amount": cat_proc.get("order_amount", ""),
                "payment_doc_number": cat_proc.get("payment_doc_number", ""),
                "payment_date": cat_proc.get("payment_date", ""),
                "payment_amount": cat_proc.get("payment_amount", ""),
                "expense_group_code": cat_proc.get("expense_group_code", ""),
                "payment_kbk": cat_proc.get("payment_kbk", ""),
                "payment_purpose": cat_proc.get("payment_purpose", ""),
                "payment_status": cat_proc.get("payment_status", ""),
            })
        if is_leaf:
            if stage_vals.get("paid_confirmed") == "Да":
                fill = FILL_CONFIRMED
            elif stage_vals.get("paid_marked") == "Да":
                fill = FILL_MARKED
            elif stage_vals.get("ordered_flag") == "Да" or stage_vals.get("ordered", 0) > 0:
                fill = FILL_ORDERED
            elif stage_vals.get("in_work") == "Да":
                fill = FILL_IN_WORK
            elif own_plan > 0:
                fill = FILL_PLAN
            else:
                fill = L4_FILL
        elif c.level == 1:
            fill = L1_FILL
        elif c.level == 2:
            fill = L2_FILL
        elif c.level == 3:
            fill = L3_FILL
        else:
            fill = L4_FILL
        font = BOLD_FONT if c.level == 1 else SEMI_FONT
        row_idx = _write_row(values, fill, font)
        if depth > 0:
            ws.row_dimensions[row_idx].outline_level = min(depth, _MAX_OUTLINE)

        child_rows = [write_item_row(it, depth + 1, ancestors + [c.name]) for it in items_by_cat.get(c.id, [])]
        child_rows += [write_node(ch, depth + 1, ancestors + [c.name]) for ch in node["children"]]

        if child_rows:
            _money_subtotal(row_idx, child_rows)
        else:
            ci_ordered = column_index(selected_keys, "ordered")
            ci_feo = column_index(selected_keys, "feo")
            ci_to_order = column_index(selected_keys, "to_order")
            ci_residual = column_index(selected_keys, "residual")
            if ci_residual is not None:
                if ci_feo is not None and ci_ordered is not None and ci_to_order is not None:
                    lf, lo, lt = (ws.cell(row_idx, c_).column_letter for c_ in (ci_feo, ci_ordered, ci_to_order))
                    ws.cell(row_idx, ci_residual, value=f"={lf}{row_idx}-{lo}{row_idx}-{lt}{row_idx}")
                else:
                    feo_val = float(c.budget) if c.budget is not None else 0.0
                    ws.cell(row_idx, ci_residual, value=round(feo_val - stage_vals.get("ordered", 0.0) - stage_vals.get("to_order", 0.0), 2))
                ws.cell(row_idx, ci_residual).number_format = NUM_FMT
                ws.cell(row_idx, ci_residual).border = THIN_BORDER

        return row_idx

    top_rows = [write_node(root, 0, []) for root in roots]
    last_row = row_num - 1

    # Строка 1 «Итого всего» — SUM по корневым категориям верхнего уровня
    # (их собственные значения — уже SUM по всем потомкам рекурсивно).
    #
    # Строка 2 «Итого по фильтру» — НЕ SUBTOTAL(9, весь_столбец): это
    # задвоило бы суммы (строки категорий сами содержат SUM по детям, и
    # SUBTOTAL(9,...) сложил бы и категорию, и её же позиции ещё раз).
    # SUMPRODUCT(SUBTOTAL(9,OFFSET(...)),--(тип<>"Категория")) — считает
    # по каждой строке данных отдельный SUBTOTAL(9, одна ячейка) (= 0, если
    # строка скрыта автофильтром «по фильтру», иначе — значение ячейки) и
    # умножает на 1/0 по столбцу «Тип строки» (row_type): складываются
    # только «Позиция» и «Категория без позиций», категории с SUM-формулой
    # исключены, чтобы не задваивать.
    money_keys = (
        "feo",
        "plan",
        "fact_amount",
        "paid_amount_money",
        "purchase_amount",
        "order_amount",
        "contract_amount",
        "payment_amount",
        "ordered",
        "to_order",
        "residual",
    ) + STAGE_AMOUNT_KEYS
    ci_row_type = column_index(selected_keys, "row_type")
    row_type_col_letter = ws.cell(row=1, column=ci_row_type).column_letter if ci_row_type else None
    for key in money_keys:
        ci = column_index(selected_keys, key)
        if ci is None:
            continue
        col_letter = ws.cell(row=1, column=ci).column_letter
        if top_rows:
            refs = ",".join(f"{col_letter}{r}" for r in top_rows)
            ws.cell(row=1, column=ci, value=f"=SUM({refs})").font = TOTAL_FONT
        if last_row >= DATA_FIRST_ROW and row_type_col_letter:
            first_cell = f"{col_letter}{DATA_FIRST_ROW}"
            formula = (
                f"=SUMPRODUCT(SUBTOTAL(9,OFFSET({first_cell},"
                f"ROW({col_letter}{DATA_FIRST_ROW}:{col_letter}{last_row})-ROW({first_cell}),0)),"
                f"--(${row_type_col_letter}${DATA_FIRST_ROW}:${row_type_col_letter}${last_row}<>\"Категория\"))"
            )
            ws.cell(row=2, column=ci, value=formula).font = TOTAL_FONT
        ws.cell(row=1, column=ci).number_format = NUM_FMT
        ws.cell(row=2, column=ci).number_format = NUM_FMT

    last_col_letter = ws.cell(row=HEADER_ROW, column=n_cols).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"

    max_validation_row = max(last_row + 100, 200)
    max_cf_row = max(last_row, max_validation_row)

    status_keys = (
        "active",
        "is_in_plan",
        "in_work",
        "purchase_done",
        "protocol_signed",
        "contracted",
        "ordered_flag",
        "delivered",
        "paid_marked",
        "paid_confirmed",
    )

    # 1. Условное форматирование ячеек «Да» / «Нет» (задача владельца):
    # Добавляется ПЕРЕД строчными правилами (gradual row rules), чтобы иметь приоритет.
    if CellIsRule is not None and last_row >= DATA_FIRST_ROW:
        rule_yes = CellIsRule(
            operator="equal",
            formula=['"Да"'],
            fill=FILL_YES_GREEN,
            font=FONT_YES_GREEN,
            border=THIN_BORDER,
            stopIfTrue=True,
        )
        rule_no = CellIsRule(
            operator="equal",
            formula=['"Нет"'],
            fill=FILL_NO_RED,
            font=FONT_NO_RED,
            border=THIN_BORDER,
            stopIfTrue=True,
        )
        for sk in status_keys:
            ci_st = column_index(selected_keys, sk)
            if ci_st is not None:
                col_letter = ws.cell(row=HEADER_ROW, column=ci_st).column_letter
                st_range = f"{col_letter}{DATA_FIRST_ROW}:{col_letter}{max_cf_row}"
                ws.conditional_formatting.add(st_range, rule_yes)
                ws.conditional_formatting.add(st_range, rule_no)

    # 2. Условное форматирование колонок факта (fact_qty, fact_unit_price, fact_amount):
    # Добавляется ПЕРЕД строчными правилами (gradual row rules), чтобы иметь приоритет.
    if FormulaRule is not None and last_row >= DATA_FIRST_ROW:
        ci_rt = column_index(selected_keys, "row_type")
        col_rt = ws.cell(row=HEADER_ROW, column=ci_rt).column_letter if ci_rt else None

        ci_fact_qty = column_index(selected_keys, "fact_qty")
        ci_plan_qty = column_index(selected_keys, "plan_qty")
        ci_fact_price = column_index(selected_keys, "fact_unit_price")
        ci_plan_price = column_index(selected_keys, "plan_unit_price")
        ci_fact_amt = column_index(selected_keys, "fact_amount")
        ci_plan = column_index(selected_keys, "plan")

        if col_rt:
            # fact_qty: если заполнено и отличается от плана в строках не категорий -> мягкий красный
            if ci_fact_qty and ci_plan_qty:
                col_fq = ws.cell(row=HEADER_ROW, column=ci_fact_qty).column_letter
                col_pq = ws.cell(row=HEADER_ROW, column=ci_plan_qty).column_letter
                rule_fq = FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_fq}{DATA_FIRST_ROW}<>"", ${col_fq}{DATA_FIRST_ROW}<>${col_pq}{DATA_FIRST_ROW})'],
                    fill=FILL_DIFF_RED,
                    font=FONT_DIFF_RED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                )
                ws.conditional_formatting.add(f"{col_fq}{DATA_FIRST_ROW}:{col_fq}{max_cf_row}", rule_fq)

            # fact_unit_price: если факт > плана -> красный, факт < плана -> зелёный
            if ci_fact_price and ci_plan_price:
                col_fup = ws.cell(row=HEADER_ROW, column=ci_fact_price).column_letter
                col_pup = ws.cell(row=HEADER_ROW, column=ci_plan_price).column_letter
                rule_fup_red = FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_fup}{DATA_FIRST_ROW}<>"", ${col_pup}{DATA_FIRST_ROW}<>"", ${col_fup}{DATA_FIRST_ROW}>${col_pup}{DATA_FIRST_ROW})'],
                    fill=FILL_DIFF_RED,
                    font=FONT_DIFF_RED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                )
                rule_fup_green = FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_fup}{DATA_FIRST_ROW}<>"", ${col_pup}{DATA_FIRST_ROW}<>"", ${col_fup}{DATA_FIRST_ROW}>0, ${col_fup}{DATA_FIRST_ROW}<${col_pup}{DATA_FIRST_ROW})'],
                    fill=FILL_DIFF_GREEN,
                    font=FONT_DIFF_GREEN,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                )
                ws.conditional_formatting.add(f"{col_fup}{DATA_FIRST_ROW}:{col_fup}{max_cf_row}", rule_fup_red)
                ws.conditional_formatting.add(f"{col_fup}{DATA_FIRST_ROW}:{col_fup}{max_cf_row}", rule_fup_green)

            # fact_amount: если факт > плана -> красный, факт < плана -> зелёный
            if ci_fact_amt and ci_plan:
                col_fa = ws.cell(row=HEADER_ROW, column=ci_fact_amt).column_letter
                col_plan_l = ws.cell(row=HEADER_ROW, column=ci_plan).column_letter
                rule_fa_red = FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_fa}{DATA_FIRST_ROW}<>"", ${col_plan_l}{DATA_FIRST_ROW}<>"", ${col_fa}{DATA_FIRST_ROW}>${col_plan_l}{DATA_FIRST_ROW})'],
                    fill=FILL_DIFF_RED,
                    font=FONT_DIFF_RED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                )
                rule_fa_green = FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_fa}{DATA_FIRST_ROW}<>"", ${col_plan_l}{DATA_FIRST_ROW}<>"", ${col_fa}{DATA_FIRST_ROW}>0, ${col_fa}{DATA_FIRST_ROW}<${col_plan_l}{DATA_FIRST_ROW})'],
                    fill=FILL_DIFF_GREEN,
                    font=FONT_DIFF_GREEN,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                )
                ws.conditional_formatting.add(f"{col_fa}{DATA_FIRST_ROW}:{col_fa}{max_cf_row}", rule_fa_red)
                ws.conditional_formatting.add(f"{col_fa}{DATA_FIRST_ROW}:{col_fa}{max_cf_row}", rule_fa_green)

    # 3. Условное форматирование строк: плавный градиент от жёлтого к зелёному (задача владельца 03.11.2026)
    if FormulaRule is not None and last_row >= DATA_FIRST_ROW:
        ci_rt = column_index(selected_keys, "row_type")
        ci_plan = column_index(selected_keys, "plan")
        ci_ord = column_index(selected_keys, "ordered")
        ci_iw = column_index(selected_keys, "in_work")
        ci_of = column_index(selected_keys, "ordered_flag")
        ci_pm = column_index(selected_keys, "paid_marked")
        ci_pc = column_index(selected_keys, "paid_confirmed")

        if ci_rt:
            col_rt = ws.cell(row=HEADER_ROW, column=ci_rt).column_letter
            cf_range = f"A{DATA_FIRST_ROW}:{last_col_letter}{last_row}"

            rules = []
            if ci_pc:
                col_pc = ws.cell(row=HEADER_ROW, column=ci_pc).column_letter
                rules.append(FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_pc}{DATA_FIRST_ROW}="Да")'],
                    fill=FILL_CONFIRMED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                ))
            if ci_pm:
                col_pm = ws.cell(row=HEADER_ROW, column=ci_pm).column_letter
                rules.append(FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_pm}{DATA_FIRST_ROW}="Да")'],
                    fill=FILL_MARKED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                ))
            if ci_of or ci_ord:
                conds = []
                if ci_of:
                    col_of = ws.cell(row=HEADER_ROW, column=ci_of).column_letter
                    conds.append(f'${col_of}{DATA_FIRST_ROW}="Да"')
                if ci_ord:
                    col_ord = ws.cell(row=HEADER_ROW, column=ci_ord).column_letter
                    conds.append(f'${col_ord}{DATA_FIRST_ROW}>0')
                or_cond = f'OR({", ".join(conds)})' if len(conds) > 1 else conds[0]
                rules.append(FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", {or_cond})'],
                    fill=FILL_ORDERED,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                ))
            if ci_iw:
                col_iw = ws.cell(row=HEADER_ROW, column=ci_iw).column_letter
                rules.append(FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_iw}{DATA_FIRST_ROW}="Да")'],
                    fill=FILL_IN_WORK,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                ))
            if ci_plan:
                col_plan = ws.cell(row=HEADER_ROW, column=ci_plan).column_letter
                rules.append(FormulaRule(
                    formula=[f'AND(${col_rt}{DATA_FIRST_ROW}<>"Категория", ${col_plan}{DATA_FIRST_ROW}>0)'],
                    fill=FILL_PLAN,
                    border=THIN_BORDER,
                    stopIfTrue=True,
                ))

            for rule in rules:
                ws.conditional_formatting.add(cf_range, rule)

    # 4. Выпадающий список «Да / Нет» для статусных колонок (задача владельца 03.11.2026)
    dv_yes_no = DataValidation(
        type="list",
        formula1="_meta!$D$1:$D$2",
        allow_blank=True,
    )
    dv_yes_no.error = "Выберите значение из списка (Да / Нет)"
    dv_yes_no.errorTitle = "Недопустимое значение"
    ws.add_data_validation(dv_yes_no)

    for sk in status_keys:
        ci_st = column_index(selected_keys, sk)
        if ci_st is not None:
            col_letter = ws.cell(row=HEADER_ROW, column=ci_st).column_letter
            dv_yes_no.add(f"{col_letter}{DATA_FIRST_ROW}:{col_letter}{max_validation_row}")

    # 5. Запасные строки с формулой автогенерации хэша/ID и формулой плана (задача владельца):
    # При заполнении колонки наименования в столбце Хэш автоматически появляется NEW-<номер_строки>
    # В столбце plan (Плановая стоимость за объём) формула произведения кол-ва на цену:
    # =IF(AND(${col_plan_qty}{spare_r}<>"",${col_plan_price}{spare_r}<>""),${col_plan_qty}{spare_r}*${col_plan_price}{spare_r},"")
    ci_name = column_index(selected_keys, "name")
    ci_plan = column_index(selected_keys, "plan")
    ci_plan_qty = column_index(selected_keys, "plan_qty")
    ci_plan_price = column_index(selected_keys, "plan_unit_price")
    col_name_letter = ws.cell(row=HEADER_ROW, column=ci_name).column_letter if ci_name else "A"
    col_pq_letter = ws.cell(row=HEADER_ROW, column=ci_plan_qty).column_letter if ci_plan_qty else None
    col_pp_letter = ws.cell(row=HEADER_ROW, column=ci_plan_price).column_letter if ci_plan_price else None

    if ci_row_id is not None or (ci_plan and col_pq_letter and col_pp_letter):
        for spare_r in range(last_row + 1, last_row + 51):
            if ci_row_id is not None:
                c_spare = ws.cell(row=spare_r, column=ci_row_id, value=f'=IF(${col_name_letter}{spare_r}<>"","NEW-"&ROW(),"")')
                c_spare.protection = Protection(locked=True)
                c_spare.border = THIN_BORDER
            for ci_other in range(1, n_cols + 1):
                cell_other = ws.cell(row=spare_r, column=ci_other)
                cell_other.border = THIN_BORDER
                if ci_other != ci_row_id:
                    cell_other.protection = Protection(locked=False)
            if ci_plan and col_pq_letter and col_pp_letter:
                c_plan_spare = ws.cell(
                    row=spare_r,
                    column=ci_plan,
                    value=f'=IF(AND(${col_pq_letter}{spare_r}<>"",${col_pp_letter}{spare_r}<>""),${col_pq_letter}{spare_r}*${col_pp_letter}{spare_r},"")',
                )
                c_plan_spare.number_format = NUM_FMT

    # Защита листа от случайного изменения заблокированных ячеек (столбец row_id),
    # без пароля, разрешая сортировку, фильтрацию, форматирование, добавление и удаление строк:
    ws.protection.sheet = True
    ws.protection.enable()
    ws.protection.autoFilter = False
    ws.protection.sort = False
    ws.protection.formatCells = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    ws.protection.insertRows = False
    ws.protection.deleteRows = False

    return ws, top_rows, last_row


def _write_roundtrip_meta_sheet(wb, subsidy_id: Optional[int]) -> None:
    """Скрытый лист `_meta` — subsidy_id/дата выгрузки/версия формата, чтобы
    app.services.feo_roundtrip_import.parse могла при загрузке назад
    отличить «файл этой субсидии» от «файл другой субсидии» (см. докстринг
    модуля parse.py — расхождение subsidy_id там жёстко отклоняется, без
    флага-обхода). Пустая субсидия (нет категорий) экспортируется тем же
    кодом ВЫШЕ без единой строки данных — лист _meta пишется всегда, это и
    есть «шаблон для заполнения с нуля» из задачи владельца."""
    from datetime import datetime, timezone

    meta = wb.create_sheet("_meta")
    meta.sheet_state = "hidden"
    meta["A1"] = "subsidy_id"
    meta["B1"] = subsidy_id
    meta["A2"] = "exported_at"
    meta["B2"] = datetime.now(timezone.utc).isoformat()
    meta["A3"] = "format_version"
    meta["B3"] = ROUNDTRIP_FORMAT_VERSION
    # Справочник для выпадающего списка DataValidation (Да / Нет)
    meta["D1"] = "Да"
    meta["D2"] = "Нет"


def build_feo_roundtrip_template_workbook():
    """Шаблон формата «Выгрузить ФЭО» для загрузки обратно (GET
    .../roundtrip/template, задача владельца 20.10.2026, часть «шаблон»).
    Строится ТЕМ ЖЕ render_feo_tree_sheet, что и настоящая выгрузка (ПРАВИЛО
    №6) — дерево ниже вымышленное (волонтёрская тематика, никаких реальных
    субсидий/организаций), БД не трогаем вовсе (синхронная функция).

    Колонки — Наименование/Код/Прил./Кол-во по ФЭО/Ед./Финансирование по
    ФЭО/Запланировано/Активна/Тип строки (+ скрытая «№ в системе», всегда
    пустая — include_row_ids=False, строки примера «новые»). Колонки заказов/
    стадий сюда не включаем (задача владельца, п.2) — их нет в
    READABLE_KEYS (feo_roundtrip_import/parse.py), шаблон человек заполняет
    руками, стадии считает система.

    _meta пишется с subsidy_id=None — check_meta_mismatch (feo_roundtrip_
    import/diff.py) не отклоняет файл ни для какой субсидии (мета без
    subsidy_id трактуется как «не привязан», это НЕ второй случай
    расхождения, которое там же жёстко отклоняется)."""
    if Workbook is None:
        raise RuntimeError("openpyxl не установлен")

    from types import SimpleNamespace

    from app.services.feo_export_columns import resolve_selected_keys

    selected_keys = resolve_selected_keys(
        "code,app,feo_qty,feo_unit,feo_unit_price,feo,plan_qty,plan_unit_price,plan,active"
    )

    def _cat(id_, name, level, *, code="", appendix="", budget=None, active=True):
        return SimpleNamespace(id=id_, name=name, code=code, appendix=appendix, budget=budget, is_active=active, level=level)

    def _item(
        id_, name, *, unit, feo_qty, feo_unit_price, feo, plan_qty, plan_unit_price, plan, active=True,
    ):
        # ДВА независимых комплекта чисел — «по ФЭО» (feo_quantity/
        # feo_unit_price/feo_amount) и «план» (quantity/unit_price/amount),
        # см. докстринг FeoPlannedItem — ЕД. (unit) общая на оба количества.
        return SimpleNamespace(
            id=id_, name=name, unit=unit, is_active=active,
            feo_quantity=feo_qty, feo_unit_price=feo_unit_price, feo_amount=feo,
            quantity=plan_qty, unit_price=plan_unit_price, amount=plan,
        )

    cat_lager = _cat(-1, "Оснащение полевого лагеря", 1)
    cat_tents = _cat(-2, "Палатки и спальное", 2)
    cat_kitchen_parent = _cat(-3, "Освещение и кухня", 2)
    cat_kitchen = _cat(-4, "Кухонный инвентарь", 3)
    cat_power = _cat(-5, "Электроснабжение", 2, budget=80000)

    cat_training = _cat(-6, "Обучение добровольцев", 1)
    cat_training_org = _cat(-7, "Организация обучения", 2)

    items_by_cat = {
        cat_tents.id: [
            _item(-101, "Палатка 4-местная", unit="шт", feo_qty=5, feo_unit_price=50000, feo=250000, plan_qty=5, plan_unit_price=50000, plan=250000),
            # Пример расхождения плана с ФЭО (владелец, п.4): по ФЭО 20 шт, в
            # плане решили закупить меньше — 18 шт, цена за ед. та же.
            _item(-102, "Спальник", unit="шт", feo_qty=20, feo_unit_price=5000, feo=100000, plan_qty=18, plan_unit_price=5000, plan=90000),
        ],
        cat_kitchen.id: [
            _item(-103, "Казан походный", unit="шт", feo_qty=3, feo_unit_price=9000, feo=27000, plan_qty=3, plan_unit_price=9000, plan=27000),
            _item(-104, "Горелка газовая", unit="шт", feo_qty=4, feo_unit_price=4500, feo=18000, plan_qty=4, plan_unit_price=4500, plan=18000, active=False),
        ],
        cat_training_org.id: [
            _item(-105, "Аренда зала", unit="дн.", feo_qty=3, feo_unit_price=40000, feo=120000, plan_qty=3, plan_unit_price=40000, plan=120000),
            # Пример расхождения цены за ед. (то же количество, план дешевле).
            _item(-106, "Печать методичек", unit="шт", feo_qty=200, feo_unit_price=225, feo=45000, plan_qty=200, plan_unit_price=200, plan=40000),
        ],
    }

    node_tents = {"cat": cat_tents, "children": []}
    node_kitchen = {"cat": cat_kitchen, "children": []}
    node_kitchen_parent = {"cat": cat_kitchen_parent, "children": [node_kitchen]}
    node_power = {"cat": cat_power, "children": []}
    node_lager = {"cat": cat_lager, "children": [node_tents, node_kitchen_parent, node_power]}

    node_training_org = {"cat": cat_training_org, "children": []}
    node_training = {"cat": cat_training, "children": [node_training_org]}

    roots = [node_lager, node_training]

    wb = Workbook()
    render_feo_tree_sheet(
        wb, "Шаблон", selected_keys, roots, items_by_cat, {}, {},
        totals_label="Шаблон — итого всего", include_row_ids=False,
    )

    _write_feo_roundtrip_howto_sheet(wb)
    _write_roundtrip_meta_sheet(wb, None)

    wb.active = 0
    return wb


def _write_feo_roundtrip_howto_sheet(wb) -> None:
    """Лист «Как заполнять» шаблона «Выгрузить ФЭО» (загрузка обратно) —
    текстовые правила, см. docstring build_feo_roundtrip_template_workbook."""
    ws = wb.create_sheet("Как заполнять")
    ws.column_dimensions["A"].width = 115
    rules = [
        "Как заполнять шаблон «Выгрузить ФЭО» (загрузка обратно)",
        "",
        "Этот файл — тот же формат, что скачивается через «Ещё» → «Выгрузить ФЭО». "
        "Загружается обратно через «Ещё» → «Загрузить выгрузку ФЭО»: сначала показывается предпросмотр "
        "(что изменится/что создастся), и только после подтверждения — запись в систему.",
        "",
        "Примеры на листе «Шаблон» ВЫМЫШЛЕННЫЕ («Оснащение полевого лагеря», «Обучение добровольцев» и т.п.) — "
        "удалите их и впишите свои направления/категории/позиции.",
        "",
        "«Тип строки»:",
        "  Категория — у строки есть вложенные строки (подкатегории и/или плановые позиции); суммы в такой строке считаются формулой по детям, вручную их менять не нужно.",
        "  Категория без позиций — лист дерева без вложенных строк, но сам несёт сумму по ФЭО (например «Электроснабжение» в примере).",
        "  Позиция — конкретный товар/услуга внутри категории (у неё есть количество/ед./сумма по ФЭО и план).",
        "",
        "Уровень вложенности задаётся ОДНИМ из двух способов:",
        "  — группировкой Excel (выделите строки → Данные → Группировать) — предпочтительно, так же сделан этот шаблон;",
        "  — ИЛИ отступом: 2 пробела в начале «Наименования» на каждый уровень вложенности (если группировку не ставили).",
        "",
        "Какие колонки загружаются: Наименование, Код, Прил., Кол-во по ФЭО, Ед., «Цена за ед. по ФЭО», «Финансирование по ФЭО» "
        "(у позиций и у «Категория без позиций»), «Кол-во по плану», «Цена за ед. по плану», «Запланировано» (три последних — только у позиций), "
        "Активна (Да/Нет). Суммы категорий с детьми — формулы, считаются сами, их трогать не нужно. "
        "Колонки заказов и стадий закупки в этот шаблон не включены — их считает система, в загрузке они не участвуют.",
        "",
        "Сумма (по ФЭО и по плану) и кол-во/цена за единицу — связаны: можно указать кол-во и цену за единицу, "
        "а сумма посчитается сама (кол-во × цена); можно указать только сумму, не заполняя кол-во/цену. "
        "Если заполнены и сумма, и кол-во с ценой, и они не сходятся — загрузка не ошибётся, но предупредит об этом в предпросмотре "
        "и запишет именно ту сумму, что указана в файле.",
        "",
        "«№ в системе» — скрытая служебная колонка. В выгрузке УЖЕ существующей субсидии по ней строки находят себя в базе при повторной загрузке; "
        "в этом шаблоне она пустая у всех строк — все строки примера новые. Не копируйте номер из одной строки в другую.",
        "",
        "Числа — без знака «₽», пробелы-разделители тысяч и запятая вместо точки допускаются.",
        "",
        "Строки, которые вы удалите из файла перед загрузкой, в системе НЕ удаляются — чтобы отключить существующую категорию/позицию, "
        "поставьте ей «Активна = Нет», а не убирайте строку из файла.",
    ]
    for line in rules:
        ws.append([line])
    ws["A1"].font = Font(bold=True, size=12)
