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
    «Сумма договора, ₽», «Сумма заявок по договору, ₽», «Осталось
    недозаказанных средств на договоре, ₽» (= сумма договора − сумма заявок),
    «Поставлено по договору, ₽», «Оплачено по договору, ₽» — первые три
    читаются из app.services.contract_balances.contract_balances (ПРАВИЛО
    №6 — не второй расчёт), «Поставлено/Оплачено по договору» — Σ по
    строкам заявок этого договора (считается здесь же, тем же cascade_
    by_stage, что и сами строки заявок — не вторая формула факта);
  уровень ЗАЯВКИ (заполнен в строках заявок и у разовой закупки — она сама
    себе единственная «заявка»): «Сумма заявки, ₽», «Поставлено, ₽»,
    «Оплачено, ₽», № ПП/дата/сумма. У строки РАМОЧНОГО договора эти три
    столбца — ПУСТЫЕ (факт целиком на заявках, не повторяется у головы) —
    поэтому обычный SUM/SUBTOTAL по любому денежному столбцу не задваивает.

ИСПРАВЛЕНО (владелец 09.10.2026, 3-й заход — «это всё должно быть в
цифрах»): формулы Excel (=SUM/=I-J) в строках реестра заменены на обычные
числа — владелец видел формулы как пустые/непонятные ячейки в Excel. Формулы
остаются ТОЛЬКО в двух верхних строках итогов (строка 1 — SUM, строка 2 —
SUBTOTAL(109), см. write_flat_top_summary_rows) — туда не задваиваются,
т.к. уровни ДОГОВОРА/ЗАЯВКИ/ПОЗИЦИИ пишут в непересекающиеся столбцы.
Добавлено:
  - служебный столбец «Уровень» первым (Договор / Заявка / Позиция) —
    фильтр + основа независимости столбцов от задваивания;
  - строки «Позиция» (PurchaseItem) под строкой разового договора и под
    каждой заявкой рамочного («Состав», Ед., Кол-во, «Цена за ед.», «Сумма
    позиции» — свой столбец, НЕ то же самое, что «Сумма заявки»; закупка
    без позиций — без строк состава);
  - «Контрагент»/«ИНН»/«№ договора» заполнены ВО ВСЕХ строках (договор,
    заявка, позиция) — фильтр по «Контрагент» + строка SUBTOTAL дают сумму
    по контрагенту без потери строк заявок/позиций.

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
  - каскад по стадиям (Поставлено/Оплачено заявки, и Σ по ним — Поставлено/
    Оплачено по договору) — app.services.plan_graph_export_rows.
    cascade_by_stage;
  - сумма/заказано/остаток договора — app.services.contract_balances.
    contract_balances;
  - признак рамочного договора — Purchase.purchase_contract_type/
    parent_purchase_id (тот же критерий, что app.services.committed_amounts
    .is_framework_purchase_expr, здесь — питоновский эквивалент);
  - «Статья ФЭО» — тот же coalesce PurchaseItem→Purchase→FeoPlannedItem, что
    app.services.plan_graph_export_data.gather_live_plan_graph_data; у
    головы — статья, если у всех её заявок одна и та же, иначе «Разные»;
  - состав позиций (Ед./Кол-во/Цена за ед./Сумма позиции) — сырые поля
    PurchaseItem (unit/quantity/unit_price/total_price), тот же набор полей,
    что читает app.services.plan_graph_export_rows._composition_values для
    «Состав закупки»/«Цена за ед.» листа «План закупок»."""
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
from app.services.feo_payroll import payroll_category_ids
from app.services.plan_graph_export_data import item_kind_label
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

_LEVEL_CONTRACT = "Договор"
_LEVEL_ORDER = "Заявка"
_LEVEL_ITEM = "Позиция"

_HEADERS = [
    "Уровень",
    "№ закупки", "№ заявки в договоре", "Реестровый №", "№ договора", "Дата договора",
    "Контрагент", "ИНН", "Предмет / состав",
    "Сумма договора, ₽", "Сумма заявок по договору, ₽",
    "Осталось недозаказанных средств на договоре, ₽",
    "Поставлено по договору, ₽", "Оплачено по договору, ₽",
    "Сумма заявки, ₽", "Поставлено, ₽", "Оплачено, ₽",
    "Статус", "№ ПП", "Дата ПП", "Сумма ПП, ₽", "Статья ФЭО",
    "Ед.", "Кол-во", "Цена за ед., ₽", "Сумма позиции, ₽",
    # Добавлено владельцем 08.10.2026 (замечания 1 и 2) — в конце, чтобы не
    # сдвигать 1-based индексы уже существующих столбцов выше.
    "Товар / услуга", "План. месяц платежа", "Факт. месяц платежа (по ПП)",
]
_WIDTHS = [
    12,
    10, 16, 16, 18, 14, 28, 16, 32,
    16, 18,
    22,
    18, 18,
    16, 16, 16,
    15, 14, 12, 14, 35,
    10, 10, 14, 16,
    12, 14, 16,
]
# 1-based индексы столбцов (владелец 09.10.2026, волна 3 — «Уровень» первым
# сдвинул все номера на +1 относительно волны 2).
_COL_LEVEL = 1
_COL_PURCHASE_NUMBER = 2
_COL_ORDER_NUMBER = 3
_COL_REGISTRY_NUMBER = 4
_COL_CONTRACT_NUMBER = 5
_COL_CONTRACT_DATE = 6
_COL_CONTRACTOR = 7
_COL_CONTRACTOR_INN = 8
_COL_SUBJECT = 9
_COL_CONTRACT_SUM = 10
_COL_CONTRACT_ORDERED = 11
_COL_CONTRACT_REMAINING = 12
_COL_CONTRACT_DELIVERED = 13
_COL_CONTRACT_PAID = 14
_COL_ORDER_SUM = 15
_COL_ORDER_DELIVERED = 16
_COL_ORDER_PAID = 17
_COL_STATUS = 18
_COL_PP_NUMBER = 19
_COL_PP_DATE = 20
_COL_PP_AMOUNT = 21
_COL_CATEGORY_PATH = 22
_COL_ITEM_UNIT = 23
_COL_ITEM_QTY = 24
_COL_ITEM_UNIT_PRICE = 25
_COL_ITEM_SUM = 26
# Владелец 08.10.2026, замечания 1/2 — добавлены в конец (см. _HEADERS).
# «Товар / услуга»: строки Заявка/Позиция и у разового договора — НЕ у
# головы рамочного (та не несёт своего вида, это заявки/позиции под ней).
# Месяцы платежа: только Заявка и разовый договор (владелец явно ограничил
# этими двумя уровнями — не Позиция).
_COL_ITEM_KIND = 27
_COL_PLANNED_PAYMENT_MONTH = 28
_COL_PAYMENT_MONTH = 29

# Денежные столбцы (владелец 09.10.2026, волна 3 — «кроме Цены за ед.»).
# Договорные/заявочные/позиционные НИКОГДА не заполнены в одной и той же
# строке (см. докстринг модуля) — SUM/SUBTOTAL по любому из них не
# задваивает.
_CONTRACT_MONEY_COLS = {_COL_CONTRACT_SUM, _COL_CONTRACT_ORDERED, _COL_CONTRACT_REMAINING,
                        _COL_CONTRACT_DELIVERED, _COL_CONTRACT_PAID}
_ORDER_MONEY_COLS = {_COL_ORDER_SUM, _COL_ORDER_DELIVERED, _COL_ORDER_PAID, _COL_PP_AMOUNT}
_ITEM_MONEY_COLS = {_COL_ITEM_SUM}
_MONEY_COLS = _CONTRACT_MONEY_COLS | _ORDER_MONEY_COLS | _ITEM_MONEY_COLS


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


async def _items_by_purchase(db: AsyncSession, purchase_ids: list[int]) -> dict[int, list]:
    """{purchase_id: [{"name","unit","qty","unit_price","total"}, ...]} —
    состав закупки (владелец 09.10.2026, часть 3 — «внутри разового договора
    может быть несколько позиций»). Сырые поля PurchaseItem (quantity/unit/
    unit_price/total_price) — та же пара, что читает app.services.
    plan_graph_export_rows._composition_values («Состав закупки»/«Цена за
    ед.» листа «План закупок»), не вторая формула. "total" — total_price,
    если задан, иначе qty*unit_price, иначе 0.0 (закупка без позиций просто
    не попадает в словарь — вызывающий код выводит строки состава только
    при наличии хотя бы одной)."""
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(PurchaseItem)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .order_by(PurchaseItem.purchase_id, PurchaseItem.id)
    )).scalars().all()
    result: dict[int, list] = {}
    for it in rows:
        qty = float(it.quantity) if it.quantity is not None else None
        unit_price = float(it.unit_price) if it.unit_price is not None else None
        if it.total_price is not None:
            total = float(it.total_price)
        elif qty is not None and unit_price is not None:
            total = qty * unit_price
        else:
            total = 0.0
        result.setdefault(it.purchase_id, []).append({
            "name": it.item_name or "",
            "unit": it.unit or "",
            "qty": round(qty, 3) if qty is not None else "",
            "unit_price": round(unit_price, 2) if unit_price is not None else "",
            "total": round(total, 2),
        })
    return result


async def gather_contracts_sheet_data(db: AsyncSession, subsidy_id: int) -> list[dict]:
    """[{head: {...}, orders: [{...}, ...]}, ...] — отсортировано по № закупки
    головы/разовой закупки по возрастанию (владелец: «по номеру закупки»).
    head/orders несут "items" — список позиций (PurchaseItem) этой строки
    (владелец 09.10.2026, часть 3), [] если позиций нет."""
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
    items_by_purchase = await _items_by_purchase(db, [p.id for p in rows])
    # «Товар / услуга» (владелец 08.10.2026, замечание 1) — тот же резолвер
    # payroll-категорий, что у листов «План закупок» (ПРАВИЛО №6).
    payroll_ids = await payroll_category_ids(db, [subsidy_id])
    # ПРАВИЛО №6 — сумма/заказано/остаток договора ЧИТАЮТСЯ отсюда, второй
    # расчёт этих трёх величин здесь не заводится.
    balances = (await contract_balances(db, subsidy_id))["by_purchase"]

    def _cell(key: str, p: Purchase):
        return get_cell_value(key, p, ctx)

    def _kind(p: Purchase) -> str:
        """«Товар / услуга» закупки `p` — та же item_kind_label, что листы
        «План закупок» (app.services.plan_graph_export_data, ПРАВИЛО №6).
        Строки «Позиция» (состав PurchaseItem) наследуют этот же вид у
        своей заявки/разового договора — PurchaseItem.item_type не несёт
        товар/услугу (см. plan_graph_export_data.py), второй классификатор
        на уровне позиции не заводим."""
        return item_kind_label(p.item_type, eff_cat_ids.get(p.id), payroll_ids)

    def _eff(p: Purchase) -> float:
        a = amounts_by_id.get(p.id)
        return float(a.effective) if a and a.effective is not None else 0.0

    def _stage(p: Purchase) -> tuple:
        _planned, _contract, _ordered, delivered, paid = cascade_by_stage(p.status, _eff(p))
        return delivered, paid

    def _items(p: Purchase) -> list:
        return items_by_purchase.get(p.id, [])

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
                "items": _items(o),
                "item_kind": _kind(o),
                "planned_payment_month": _cell("planned_payment_month", o),
                "payment_month": _cell("payment_month", o),
            })

        if len(order_cat_paths) == 1:
            head_cat_path = next(iter(order_cat_paths))
        elif order_cat_paths:
            head_cat_path = "Разные"
        else:
            head_cat_path = category_full_path(cats, eff_cat_ids.get(head.id))

        # «Поставлено/Оплачено по договору» (владелец 09.10.2026, часть 2) —
        # Σ по строкам заявок ЭТОГО договора (тем же cascade_by_stage, что и
        # сами строки заявок) — не второй расчёт факта.
        delivered_total = round(sum(o["delivered"] for o in order_rows), 2)
        paid_total = round(sum(o["paid"] for o in order_rows), 2)

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
                "remaining": round(bal["remaining"], 2),
                "delivered_total": delivered_total, "paid_total": paid_total,
                "is_framework": True,
                "status": _cell("status", head),
                "category_path": head_cat_path,
                "purchase_id": head.id,
                "items": [],  # владелец: у организационной "головы" своих позиций нет
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
                "remaining": round(bal["remaining"], 2),
                "delivered_total": round(delivered, 2), "paid_total": round(paid, 2),
                "is_framework": False,
                "status": _cell("status", p),
                "category_path": category_full_path(cats, eff_cat_ids.get(p.id)),
                "purchase_id": p.id,
                # Разовая закупка — сама себе единственная «заявка» (владелец,
                # часть A): «Сумма заявки»/«Поставлено»/«Оплачено» заполнены В
                # ТОЙ ЖЕ строке договора (нет отдельной строки заявки).
                "single_sum": eff, "single_delivered": round(delivered, 2), "single_paid": round(paid, 2),
                "single_status": _cell("status", p),
                "items": _items(p),
                "item_kind": _kind(p),
                "planned_payment_month": _cell("planned_payment_month", p),
                "payment_month": _cell("payment_month", p),
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
    видел «договоров нет», а не отсутствие листа.

    Владелец 09.10.2026, волна 3 — все строки данных несут ЧИСЛА (не
    формулы Excel); формулы — только в строках 1-2 итогов (write_flat_top_
    summary_rows). Три уровня строк («Уровень»): Договор (голова рамочного
    ИЛИ разовая закупка), Заявка (заказ рамочного), Позиция (PurchaseItem
    под разовым договором или под заявкой)."""
    from app.utils.xlsx_row_height import apply_row_heights

    HEADER_FILL   = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT   = Font(color="FFFFFF", bold=True, size=9)
    CONTRACT_FILL = PatternFill("solid", fgColor="DBEAFE")
    CONTRACT_FONT = Font(bold=True, size=9)
    ORDER_FONT    = Font(size=9, color="374151")
    ITEM_FONT     = Font(size=9, color="6B7280", italic=True)
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

    def _write_item_row(level: str, purchase_number, order_number, contract_number, contractor, contractor_inn, item: dict, item_kind: str = "") -> int:
        """Строка «Позиция» (владелец 09.10.2026, часть 3) — «Контрагент»/
        «ИНН»/«№ договора» заполнены, как и во всех остальных строках
        (владелец, часть 4); денежные столбцы уровня ДОГОВОРА/ЗАЯВКИ —
        пусто (факт целиком на строке заявки/договора выше, не задваивается
        «Сумма позиции» в отдельном столбце). «Товар / услуга» (владелец
        08.10.2026, замечание 1) — наследуется от родительской заявки/
        разового договора (`item_kind`); месяцы платежа сюда НЕ попадают
        (владелец ограничил ими только Заявку/разовый договор)."""
        cells = [""] * len(_HEADERS)
        cells[_COL_LEVEL - 1] = level
        cells[_COL_PURCHASE_NUMBER - 1] = purchase_number
        cells[_COL_ORDER_NUMBER - 1] = order_number
        cells[_COL_CONTRACT_NUMBER - 1] = contract_number
        cells[_COL_CONTRACTOR - 1] = contractor
        cells[_COL_CONTRACTOR_INN - 1] = contractor_inn
        cells[_COL_SUBJECT - 1] = item["name"]
        cells[_COL_ITEM_UNIT - 1] = item["unit"]
        cells[_COL_ITEM_QTY - 1] = item["qty"]
        cells[_COL_ITEM_UNIT_PRICE - 1] = item["unit_price"]
        cells[_COL_ITEM_SUM - 1] = item["total"]
        cells[_COL_ITEM_KIND - 1] = item_kind
        return _write_row(cells, None, ITEM_FONT)

    for g in groups:
        h = g["head"]
        if h.get("is_framework"):
            # Голова: уровень ДОГОВОРА заполнен числами, уровень ЗАЯВКИ —
            # пусто (факт целиком на строках заявок ниже).
            cells = [""] * len(_HEADERS)
            cells[_COL_LEVEL - 1] = _LEVEL_CONTRACT
            cells[_COL_PURCHASE_NUMBER - 1] = h["purchase_number"]
            cells[_COL_REGISTRY_NUMBER - 1] = h["registry_number"]
            cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
            cells[_COL_CONTRACT_DATE - 1] = h["contract_date"]
            cells[_COL_CONTRACTOR - 1] = h["contractor"]
            cells[_COL_CONTRACTOR_INN - 1] = h["contractor_inn"]
            cells[_COL_SUBJECT - 1] = h["subject"]
            cells[_COL_CONTRACT_SUM - 1] = h["contract_sum"]
            cells[_COL_CONTRACT_ORDERED - 1] = h["ordered"]
            cells[_COL_CONTRACT_REMAINING - 1] = h["remaining"]
            cells[_COL_CONTRACT_DELIVERED - 1] = h["delivered_total"]
            cells[_COL_CONTRACT_PAID - 1] = h["paid_total"]
            cells[_COL_STATUS - 1] = h["status"]
            cells[_COL_CATEGORY_PATH - 1] = h["category_path"]
            _write_row(cells, CONTRACT_FILL, CONTRACT_FONT)

            for o in g["orders"]:
                order_cells = [""] * len(_HEADERS)
                order_cells[_COL_LEVEL - 1] = _LEVEL_ORDER
                order_cells[_COL_ORDER_NUMBER - 1] = o["order_number"]
                order_cells[_COL_REGISTRY_NUMBER - 1] = o["registry_number"]
                order_cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
                order_cells[_COL_CONTRACTOR - 1] = h["contractor"]
                order_cells[_COL_CONTRACTOR_INN - 1] = h["contractor_inn"]
                order_cells[_COL_SUBJECT - 1] = o["subject"]
                order_cells[_COL_ORDER_SUM - 1] = o["sum"]
                order_cells[_COL_ORDER_DELIVERED - 1] = o["delivered"]
                order_cells[_COL_ORDER_PAID - 1] = o["paid"]
                order_cells[_COL_STATUS - 1] = o["status"]
                order_cells[_COL_PP_NUMBER - 1] = o["pp_number"]
                order_cells[_COL_PP_DATE - 1] = o["pp_date"]
                order_cells[_COL_PP_AMOUNT - 1] = o["pp_amount"]
                order_cells[_COL_CATEGORY_PATH - 1] = o["category_path"]
                order_cells[_COL_ITEM_KIND - 1] = o.get("item_kind", "")
                order_cells[_COL_PLANNED_PAYMENT_MONTH - 1] = o.get("planned_payment_month", "")
                order_cells[_COL_PAYMENT_MONTH - 1] = o.get("payment_month", "")
                _write_row(order_cells, None, ORDER_FONT)

                for item in o["items"]:
                    _write_item_row(
                        _LEVEL_ITEM, "", o["order_number"], h["contract_number"],
                        h["contractor"], h["contractor_inn"], item, item_kind=o.get("item_kind", ""),
                    )
        else:
            # Разовая закупка — одна строка, оба уровня заполнены в ней же
            # (владелец, часть A: «и «Сумма договора», и «Сумма заявки»»).
            cells = [""] * len(_HEADERS)
            cells[_COL_LEVEL - 1] = _LEVEL_CONTRACT
            cells[_COL_PURCHASE_NUMBER - 1] = h["purchase_number"]
            cells[_COL_REGISTRY_NUMBER - 1] = h["registry_number"]
            cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
            cells[_COL_CONTRACT_DATE - 1] = h["contract_date"]
            cells[_COL_CONTRACTOR - 1] = h["contractor"]
            cells[_COL_CONTRACTOR_INN - 1] = h["contractor_inn"]
            cells[_COL_SUBJECT - 1] = h["subject"]
            cells[_COL_CONTRACT_SUM - 1] = h["contract_sum"]
            cells[_COL_CONTRACT_ORDERED - 1] = h["ordered"]
            cells[_COL_CONTRACT_REMAINING - 1] = h["remaining"]
            cells[_COL_CONTRACT_DELIVERED - 1] = h["delivered_total"]
            cells[_COL_CONTRACT_PAID - 1] = h["paid_total"]
            cells[_COL_ORDER_SUM - 1] = h["single_sum"]
            cells[_COL_ORDER_DELIVERED - 1] = h["single_delivered"]
            cells[_COL_ORDER_PAID - 1] = h["single_paid"]
            cells[_COL_STATUS - 1] = h["status"]
            cells[_COL_CATEGORY_PATH - 1] = h["category_path"]
            cells[_COL_ITEM_KIND - 1] = h.get("item_kind", "")
            cells[_COL_PLANNED_PAYMENT_MONTH - 1] = h.get("planned_payment_month", "")
            cells[_COL_PAYMENT_MONTH - 1] = h.get("payment_month", "")
            _write_row(cells, CONTRACT_FILL, CONTRACT_FONT)

            for item in h["items"]:
                _write_item_row(
                    _LEVEL_ITEM, h["purchase_number"], "", h["contract_number"],
                    h["contractor"], h["contractor_inn"], item, item_kind=h.get("item_kind", ""),
                )

    last_row = row_num - 1
    last_col_letter = ws.cell(row=HEADER_ROW, column=len(_HEADERS)).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"
    apply_row_heights(ws, range(1, last_row + 1))
