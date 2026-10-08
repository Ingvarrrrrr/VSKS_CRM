"""plan_graph_export_contracts_sheet.py — лист «Реестр договоров» (владелец
08.10.2026): «реестр договоров, там должно быть по номеру закупки и уже
внутри них номера заявок».

Закупки субсидии с договором (contract_id/contract_number, или статус от
«Договор» и выше), без отменённых: строка договора (рамочный — Contract.
max_amount, фолбэк — Σ заказов; разовый — effective самой закупки), под
рамочным — строки его заявок по № заявки в договоре.

ИСПРАВЛЕНО (владелец 08.10.2026, прод ФАДМ 2026_2, 2-й заход): прежняя
колонка «Сумма, ₽» одна на оба уровня (договор и заявка) задваивала суммы
при обычном SUM по столбцу. Разнесена на ДВА уровня непересекающихся
столбцов:
  уровень ДОГОВОРА (заполнен только в строке договора/разовой закупки):
    «Сумма договора, ₽», «Заказано по договору, ₽» (=SUM по «Сумма заявки»
    её заявок), «Остаток по договору, ₽» (=сумма договора − заказано) —
    ВСЕ ТРИ читаются из app.services.contract_balances.contract_balances
    (ПРАВИЛО №6 — не второй расчёт, «Заказано»/«Остаток» дополнительно
    выражены формулой Excel, но число совпадает с contract_balances);
  уровень ЗАЯВКИ (заполнен в строках заявок и у разовой закупки — она сама
    себе единственная «заявка»): «Сумма заявки, ₽», «Поставлено, ₽»,
    «Оплачено, ₽», № ПП/дата/сумма. У строки РАМОЧНОГО договора эти три
    столбца — ПУСТЫЕ (факт целиком на заявках, не повторяется у головы) —
    поэтому обычный SUM/SUBTOTAL по любому денежному столбцу теперь даёт
    верный итог без учёта задвоения.

Часть B (владелец 08.10.2026) — строки 1-3 (подпись/«Итого всего»/«Итого по
фильтру») через общую app.services.plan_graph_export_rows.
write_flat_top_summary_rows (лист НЕ иерархический — как «План закупок (по
порядку)»); шапка — строка 4, данные — с 5-й, автофильтр на шапке,
закрепление под шапкой.

ПРАВИЛО №6 — ни одна сумма/подпись здесь не считается второй формулой:
  - значения полей закупки (предмет, реестровый №, контрагент/ИНН, статус,
    № и дата платёжки) — app.services.purchase_export_cells.get_cell_value;
  - эффективная сумма закупки — app.services.purchase_amounts.
    load_purchase_amounts (effective);
  - каскад по стадиям (Поставлено/Оплачено заявки) — app.services.
    plan_graph_export_rows.cascade_by_stage;
  - сумма/заказано/остаток договора — app.services.contract_balances.
    contract_balances;
  - признак рамочного договора — Purchase.purchase_contract_type/
    parent_purchase_id (тот же критерий, что app.services.committed_amounts
    .is_framework_purchase_expr, здесь — питоновский эквивалент);
  - «Статья ФЭО» — тот же coalesce PurchaseItem→Purchase→FeoPlannedItem, что
    app.services.plan_graph_export_data.gather_live_plan_graph_data; у
    головы — статья, если у всех её заявок одна и та же, иначе «Разные»."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.contract_balances import contract_balances, contract_scope_predicate
from app.services.plan_graph_export_rows import (
    cascade_by_stage,
    category_full_path,
    write_flat_top_summary_rows,
)
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_export_cells import build_purchase_export_ctx, get_cell_value

SHEET_NAME = "Реестр договоров"
HEADER_ROW = 3
DATA_FIRST_ROW = 4

_HEADERS = [
    "№ закупки", "№ заявки в договоре", "Реестровый №", "№ договора", "Дата договора",
    "Контрагент", "ИНН", "Предмет / состав",
    "Сумма договора, ₽", "Заказано по договору, ₽", "Остаток по договору, ₽",
    "Сумма заявки, ₽", "Поставлено, ₽", "Оплачено, ₽",
    "Статус", "№ ПП", "Дата ПП", "Сумма ПП, ₽", "Статья ФЭО",
]
_WIDTHS = [10, 16, 16, 18, 14, 28, 16, 32, 16, 18, 18, 16, 16, 16, 15, 14, 12, 14, 35]
# 1-based индексы денежных столбцов. Договорные (9,10,11) и заявочные
# (12,13,14,18) НИКОГДА не заполнены в одной и той же строке — SUM/SUBTOTAL
# по любому из них не задваивает.
_CONTRACT_MONEY_COLS = {9, 10, 11}
_ORDER_MONEY_COLS = {12, 13, 14, 18}
_MONEY_COLS = _CONTRACT_MONEY_COLS | _ORDER_MONEY_COLS


def _is_framework(p: Purchase) -> bool:
    return bool(p.purchase_contract_type) and p.purchase_contract_type.startswith("framework")


def _order_sort_key(o: Purchase):
    try:
        n = float(o.order_number) if o.order_number not in (None, "") else float("inf")
    except (TypeError, ValueError):
        n = float("inf")
    return (n, o.purchase_number if o.purchase_number is not None else 10 ** 9)


async def _effective_category_ids(db: AsyncSession, purchase_ids: list[int]) -> dict[int, int]:
    """{purchase_id: feo_category_id} — тот же coalesce PurchaseItem.
    feo_category_id → Purchase.feo_category_id → FeoPlannedItem.
    feo_category_id, что в app.services.plan_graph_export_data.
    gather_live_plan_graph_data (не второй признак категории закупки)."""
    if not purchase_ids:
        return {}
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id, FeoPlannedItem.feo_category_id)
    rows = (await db.execute(
        select(Purchase.id, cat_col.label("cat"))
        .outerjoin(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(FeoPlannedItem, FeoPlannedItem.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.id.in_(purchase_ids))
    )).all()
    result: dict[int, int] = {}
    for pid, cat in rows:
        if cat is not None and pid not in result:
            result[pid] = cat
    return result


async def gather_contracts_sheet_data(db: AsyncSession, subsidy_id: int) -> list[dict]:
    """[{head: {...}, orders: [{...}, ...]}, ...] — отсортировано по № закупки
    головы/разовой закупки по возрастанию (владелец: «по номеру закупки»)."""
    # ПРАВИЛО №6 (владелец 09.10.2026): предикат «входит в реестр договоров»
    # — ОДИН, читается из contract_balances.contract_scope_predicate (не
    # второй набор условий здесь — тот был шире и ложно пускал wishes-статус
    # с заполненным № договора).
    rows = (await db.execute(
        select(Purchase)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status != "cancelled")
        .where(contract_scope_predicate(Purchase))
    )).scalars().all()
    if not rows:
        return []

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    ctx = await build_purchase_export_ctx(db, rows)
    amounts_by_id = await load_purchase_amounts(db, [p.id for p in rows])
    eff_cat_ids = await _effective_category_ids(db, [p.id for p in rows])
    # ПРАВИЛО №6 — сумма/заказано/остаток договора ЧИТАЮТСЯ отсюда, второй
    # расчёт этих трёх величин здесь не заводится.
    balances = (await contract_balances(db, subsidy_id))["by_purchase"]

    def _cell(key: str, p: Purchase):
        return get_cell_value(key, p, ctx)

    def _eff(p: Purchase) -> float:
        a = amounts_by_id.get(p.id)
        return float(a.effective) if a and a.effective is not None else 0.0

    def _stage(p: Purchase) -> tuple:
        _planned, _contract, _ordered, delivered, paid = cascade_by_stage(p.status, _eff(p))
        return delivered, paid

    contract_ids = {p.contract_id for p in rows if p.contract_id}
    contracts_by_id: dict = {}
    if contract_ids:
        contracts_by_id = {
            c.id: c for c in (await db.execute(
                select(Contract).where(Contract.id.in_(contract_ids))
            )).scalars().all()
        }

    heads = [p for p in rows if _is_framework(p) and p.parent_purchase_id is None]
    head_ids = {p.id for p in heads}
    orders_by_head: dict = {}
    singles: list = []
    for p in rows:
        if p.id in head_ids:
            continue
        if p.parent_purchase_id in head_ids:
            orders_by_head.setdefault(p.parent_purchase_id, []).append(p)
        else:
            singles.append(p)

    # Владелец 09.10.2026, прод ФАДМ 2026_2, 3-й заход (РЕЕ-2026-03110 — тот
    # же contract_id, что и настоящая голова РЕЕ-2026-03095, но заявок под
    # НЕЙ нет): формальный признак головы (рамочный тип + без родителя) без
    # заявок — не голова по смыслу, выводить как разовый договор (ПРАВИЛО
    # №6 — тот же приём, что contract_balances.contract_balances).
    heads_without_orders = [h for h in heads if not orders_by_head.get(h.id)]
    heads = [h for h in heads if orders_by_head.get(h.id)]
    singles.extend(heads_without_orders)

    groups: list = []
    for head in heads:
        orders = sorted(orders_by_head.get(head.id, []), key=_order_sort_key)
        bal = balances.get(head.id) or {"contract_sum": 0.0, "ordered": 0.0, "remaining": 0.0}

        order_rows = []
        order_cat_paths: set = set()
        for o in orders:
            odelivered, opaid = _stage(o)
            o_cat_path = category_full_path(cats, eff_cat_ids.get(o.id))
            order_cat_paths.add(o_cat_path)
            order_rows.append({
                "order_number": o.order_number or "", "purchase_number": o.purchase_number or "",
                "registry_number": _cell("registry_number", o),
                "subject": _cell("subject", o) or o.item_name or "",
                "sum": round(_eff(o), 2), "delivered": round(odelivered, 2), "paid": round(opaid, 2),
                "status": _cell("status", o),
                "pp_number": _cell("payment_doc_number", o), "pp_date": _cell("payment_doc_date", o),
                "pp_amount": _cell("payment_amount", o),
                "category_path": o_cat_path,
                "purchase_id": o.id,
            })

        if len(order_cat_paths) == 1:
            head_cat_path = next(iter(order_cat_paths))
        elif order_cat_paths:
            head_cat_path = "Разные"
        else:
            head_cat_path = category_full_path(cats, eff_cat_ids.get(head.id))

        groups.append({
            "head": {
                "purchase_number": head.purchase_number or "",
                "registry_number": _cell("registry_number", head),
                "contract_number": (
                    contracts_by_id.get(head.contract_id).number if head.contract_id in contracts_by_id else None
                ) or head.contract_number or "",
                "contract_date": (
                    str(contracts_by_id[head.contract_id].date)
                    if head.contract_id in contracts_by_id and contracts_by_id[head.contract_id].date
                    else (str(head.contract_date) if head.contract_date else "")
                ),
                "contractor": _cell("contractor", head), "contractor_inn": _cell("contractor_inn", head),
                "subject": _cell("subject", head) or head.item_name or "",
                "contract_sum": round(bal["contract_sum"], 2), "ordered": round(bal["ordered"], 2),
                "is_framework": True,
                "status": _cell("status", head),
                "category_path": head_cat_path,
                "purchase_id": head.id,
            },
            "orders": order_rows,
            "sort_key": head.purchase_number if head.purchase_number is not None else 10 ** 9,
        })

    for p in singles:
        delivered, paid = _stage(p)
        bal = balances.get(p.id) or {"contract_sum": 0.0, "ordered": 0.0, "remaining": 0.0}
        eff = round(_eff(p), 2)
        groups.append({
            "head": {
                "purchase_number": p.purchase_number or "",
                "registry_number": _cell("registry_number", p),
                "contract_number": _cell("contract_number", p),
                "contract_date": _cell("contract_date", p),
                "contractor": _cell("contractor", p), "contractor_inn": _cell("contractor_inn", p),
                "subject": _cell("subject", p) or p.item_name or "",
                "contract_sum": round(bal["contract_sum"], 2), "ordered": round(bal["ordered"], 2),
                "is_framework": False,
                "status": _cell("status", p),
                "category_path": category_full_path(cats, eff_cat_ids.get(p.id)),
                "purchase_id": p.id,
                # Разовая закупка — сама себе единственная «заявка» (владелец,
                # часть A): «Сумма заявки»/«Поставлено»/«Оплачено» заполнены В
                # ТОЙ ЖЕ строке договора (нет отдельной строки заявки).
                "single_sum": eff, "single_delivered": round(delivered, 2), "single_paid": round(paid, 2),
                "single_status": _cell("status", p),
            },
            "orders": [],
            "sort_key": p.purchase_number if p.purchase_number is not None else 10 ** 9,
        })

    groups.sort(key=lambda g: g["sort_key"])
    return groups


def write_contracts_sheet(wb, groups: list, title: str = "") -> None:
    """Строит лист `SHEET_NAME` в книге `wb` (добавляется в конец книги —
    порядок листов определяет вызывающий роутер порядком вызовов). Пустые
    `groups` — лист всё равно создаётся (только заголовок), чтобы владелец
    видел «договоров нет», а не отсутствие листа."""
    from app.utils.xlsx_row_height import apply_row_heights

    HEADER_FILL   = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT   = Font(color="FFFFFF", bold=True, size=9)
    CONTRACT_FILL = PatternFill("solid", fgColor="DBEAFE")
    CONTRACT_FONT = Font(bold=True, size=9)
    ORDER_FONT    = Font(size=9, color="374151")
    CENTER_ALIGN  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN    = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN   = Alignment(horizontal="right", vertical="center", wrap_text=True)
    THIN_BORDER   = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    NUM_FMT = "#,##0.00"

    ws = wb.create_sheet(SHEET_NAME)
    write_flat_top_summary_rows(ws, _MONEY_COLS, title=title or f"{SHEET_NAME} — итого всего", data_first_row=DATA_FIRST_ROW)

    for ci, (header, width) in enumerate(zip(_HEADERS, _WIDTHS), 1):
        cell = ws.cell(row=HEADER_ROW, column=ci, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = f"A{DATA_FIRST_ROW}"

    row_num = DATA_FIRST_ROW

    def _write_row(cells: list, fill, font) -> int:
        nonlocal row_num
        idx = row_num
        for ci, val in enumerate(cells, 1):
            cell = ws.cell(row=idx, column=ci, value=val)
            if fill is not None:
                cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            is_money = ci in _MONEY_COLS
            cell.alignment = RIGHT_ALIGN if is_money else LEFT_ALIGN
            if is_money and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        row_num += 1
        return idx

    def _set_cell(row_idx: int, col: int, value, fill, font) -> None:
        cell = ws.cell(row=row_idx, column=col, value=value)
        if fill is not None:
            cell.fill = fill
        cell.font = font
        cell.border = THIN_BORDER
        is_money = col in _MONEY_COLS
        cell.alignment = RIGHT_ALIGN if is_money else LEFT_ALIGN
        if is_money and isinstance(value, (int, float)):
            cell.number_format = NUM_FMT

    for g in groups:
        h = g["head"]
        if h.get("is_framework"):
            # Голова: уровень ДОГОВОРА заполнен, уровень ЗАЯВКИ — пусто
            # (факт целиком на строках заявок ниже).
            idx = _write_row([
                h["purchase_number"], "", h["registry_number"], h["contract_number"], h["contract_date"],
                h["contractor"], h["contractor_inn"], h["subject"],
                h["contract_sum"], None, None,
                "", "", "",
                h["status"], "", "", "", h["category_path"],
            ], CONTRACT_FILL, CONTRACT_FONT)
            _set_cell(idx, 11, f"=I{idx}-J{idx}", CONTRACT_FILL, CONTRACT_FONT)

            orders_start = row_num
            for o in g["orders"]:
                _write_row([
                    "", o["order_number"], o["registry_number"], "", "",
                    "", "", o["subject"],
                    None, None, None,
                    o["sum"], o["delivered"], o["paid"],
                    o["status"], o["pp_number"], o["pp_date"], o["pp_amount"], o["category_path"],
                ], None, ORDER_FONT)
            orders_end = row_num - 1

            # «Заказано по договору» = Σ «Сумма заявки» (col 12) её заявок.
            if orders_end >= orders_start:
                col_letter = ws.cell(row=HEADER_ROW, column=12).column_letter
                formula = f"=SUM({col_letter}{orders_start}:{col_letter}{orders_end})"
                _set_cell(idx, 10, formula, CONTRACT_FILL, CONTRACT_FONT)
            else:
                _set_cell(idx, 10, 0.0, CONTRACT_FILL, CONTRACT_FONT)
        else:
            # Разовая закупка — одна строка, оба уровня заполнены в ней же
            # (владелец, часть A: «и «Сумма договора», и «Сумма заявки»»).
            idx = _write_row([
                h["purchase_number"], "", h["registry_number"], h["contract_number"], h["contract_date"],
                h["contractor"], h["contractor_inn"], h["subject"],
                h["contract_sum"], h["ordered"], None,
                h["single_sum"], h["single_delivered"], h["single_paid"],
                h["status"], "", "", "", h["category_path"],
            ], CONTRACT_FILL, CONTRACT_FONT)
            _set_cell(idx, 11, f"=I{idx}-J{idx}", CONTRACT_FILL, CONTRACT_FONT)

    last_row = row_num - 1
    last_col_letter = ws.cell(row=HEADER_ROW, column=len(_HEADERS)).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"
    apply_row_heights(ws, range(1, last_row + 1))
