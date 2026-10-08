"""plan_graph_export_contracts_sheet.py — лист «Реестр договоров» (владелец
08.10.2026…09.10.2026, 4 волны): «реестр договоров, там должно быть по
номеру закупки и уже внутри них номера заявок».

РЕНДЕРЕР ТОЛЬКО ПИШЕТ ЛИСТ (ПРАВИЛО №5, 09.10.2026, 4-й заход — модуль
разросся до 606 строк): сбор данных (gather_contracts_sheet_data) переехал в
app.services.plan_graph_export_contracts_data; этот файл импортирует её и
реэкспортирует под тем же именем — роутер (app.routers.
subsidy_plan_graph_export) и test_plan_graph_export_framework_head_excluded.py
продолжают импортировать отсюда без изменений.

Закупки субсидии с договором (contract_id/contract_number, или статус от
«Договор» и выше), без отменённых: строка договора (рамочный — Contract.
max_amount, фолбэк — Σ заказов; разовый — effective самой закупки), под
рамочным — строки его заявок по № заявки в договоре.

Три уровня строк («Уровень»): Договор (голова рамочного ИЛИ разовая закупка),
Заявка (заказ рамочного), Позиция (PurchaseItem под разовым договором или
под заявкой). Денежные столбцы разнесены на НЕПЕРЕСЕКАЮЩИЕСЯ уровни —
договор / заявка / позиция — обычный SUM/SUBTOTAL по любому денежному
столбцу не задваивает (см. _MONEY_COLS).

ДОБАВЛЕНО (владелец 09.10.2026, 4-й заход):
  1. Группировка Excel (row outline): договор — уровень 0, заявки рамочного
     — 1, позиции под заявкой — 2; позиции под разовым — 1. По умолчанию всё
     развёрнуто (hidden=False), summaryBelow=False (строка-итог группы —
     договор/заявка — СВЕРХУ своих детей).
  2. У разового договора С ПОЗИЦИЯМИ «Сумма заявки»/«Поставлено»/«Оплачено»
     пишутся в строках ПОЗИЦИЙ (по сумме позиции, тот же cascade_by_stage),
     а не в строке договора — она занята только уровнем ДОГОВОРА. Закупка
     без позиций (itemless) — эти три величины остаются в строке договора
     (иначе потерялись бы).
  3. «Вид договора» (после «№ договора»): Рамочный / Рамочный накопительный
     / Разовый — во всех строках группы (для фильтра).
  4. «Тип договора» (после «Вид договора»): Поставка товаров / Оказание
     услуг / ФОТ — во всех строках группы (для фильтра); «Товар / услуга»
     позиции остаётся отдельным столбцом (своим per-строка).
  5. Денежные ячейки верхних строк итогов (write_flat_top_summary_rows) —
     тот же number_format/alignment, что и у данных столбца (поправлено в
     plan_graph_export_rows.py один раз, не здесь).

ПРАВИЛО №6 — классификация/суммы/подписи полей не считаются второй формулой
здесь — см. докстринг plan_graph_export_contracts_data.py (там же живёт сам
расчёт, этот файл только проецирует готовые значения в ячейки)."""
from __future__ import annotations

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

from app.services.plan_graph_export_contracts_data import gather_contracts_sheet_data
from app.services.plan_graph_export_rows import write_flat_top_summary_rows

__all__ = ["gather_contracts_sheet_data", "write_contracts_sheet", "DATA_FIRST_ROW", "HEADER_ROW"]

SHEET_NAME = "Реестр договоров"
HEADER_ROW = 3
DATA_FIRST_ROW = 4

_LEVEL_CONTRACT = "Договор"
_LEVEL_ORDER = "Заявка"
_LEVEL_ITEM = "Позиция"

_HEADERS = [
    "Уровень",
    "№ закупки", "№ заявки в договоре", "Реестровый №", "№ договора",
    # Владелец 09.10.2026, замечания 3/4 — сразу после «№ договора».
    "Вид договора", "Тип договора",
    "Дата договора",
    "Контрагент", "ИНН", "Предмет / состав",
    "Сумма договора, ₽", "Сумма заявок по договору, ₽",
    "Осталось недозаказанных средств на договоре, ₽",
    "Поставлено по договору, ₽", "Оплачено по договору, ₽",
    "Сумма заявки, ₽", "Поставлено, ₽", "Оплачено, ₽",
    "Статус", "№ ПП", "Дата ПП", "Сумма ПП, ₽", "Статья ФЭО",
    "Ед.", "Кол-во", "Цена за ед., ₽", "Сумма позиции, ₽",
    "Товар / услуга", "План. месяц платежа", "Факт. месяц платежа (по ПП)",
]
_WIDTHS = [
    12,
    10, 16, 16, 18,
    16, 18,
    14, 28, 16, 32,
    16, 18,
    22,
    18, 18,
    16, 16, 16,
    15, 14, 12, 14, 35,
    10, 10, 14, 16,
    12, 14, 16,
]
# 1-based индексы столбцов (владелец 09.10.2026, 4-й заход — «Вид договора»/
# «Тип договора» вставлены после «№ договора», все последующие номера +2
# относительно волны 3).
_COL_LEVEL = 1
_COL_PURCHASE_NUMBER = 2
_COL_ORDER_NUMBER = 3
_COL_REGISTRY_NUMBER = 4
_COL_CONTRACT_NUMBER = 5
_COL_CONTRACT_VIEW = 6
_COL_CONTRACT_KIND = 7
_COL_CONTRACT_DATE = 8
_COL_CONTRACTOR = 9
_COL_CONTRACTOR_INN = 10
_COL_SUBJECT = 11
_COL_CONTRACT_SUM = 12
_COL_CONTRACT_ORDERED = 13
_COL_CONTRACT_REMAINING = 14
_COL_CONTRACT_DELIVERED = 15
_COL_CONTRACT_PAID = 16
_COL_ORDER_SUM = 17
_COL_ORDER_DELIVERED = 18
_COL_ORDER_PAID = 19
_COL_STATUS = 20
_COL_PP_NUMBER = 21
_COL_PP_DATE = 22
_COL_PP_AMOUNT = 23
_COL_CATEGORY_PATH = 24
_COL_ITEM_UNIT = 25
_COL_ITEM_QTY = 26
_COL_ITEM_UNIT_PRICE = 27
_COL_ITEM_SUM = 28
_COL_ITEM_KIND = 29
_COL_PLANNED_PAYMENT_MONTH = 30
_COL_PAYMENT_MONTH = 31

# Денежные столбцы — договорные/заявочные/позиционные НИКОГДА не заполнены в
# одной и той же строке (см. докстринг модуля) — SUM/SUBTOTAL по любому из
# них не задваивает.
_CONTRACT_MONEY_COLS = {_COL_CONTRACT_SUM, _COL_CONTRACT_ORDERED, _COL_CONTRACT_REMAINING,
                        _COL_CONTRACT_DELIVERED, _COL_CONTRACT_PAID}
_ORDER_MONEY_COLS = {_COL_ORDER_SUM, _COL_ORDER_DELIVERED, _COL_ORDER_PAID, _COL_PP_AMOUNT}
_ITEM_MONEY_COLS = {_COL_ITEM_SUM}
_MONEY_COLS = _CONTRACT_MONEY_COLS | _ORDER_MONEY_COLS | _ITEM_MONEY_COLS
# «Цена за ед., ₽» (владелец/QA 09.10.2026) — числовое денежное оформление
# (number_format + выравнивание вправо), как у _MONEY_COLS, но в верхние
# строки SUM/SUBTOTAL (write_flat_top_summary_rows(ws, _MONEY_COLS, ...)) НЕ
# входит — цена за единицу суммировать по столбцу бессмысленно.
_PRICE_COLS = {_COL_ITEM_UNIT_PRICE}


def write_contracts_sheet(wb, groups: list, title: str = "") -> None:
    """Строит лист `SHEET_NAME` в книге `wb` (добавляется в конец книги —
    порядок листов определяет вызывающий роутер порядком вызовов). Пустые
    `groups` — лист всё равно создаётся (только заголовок).

    Три уровня строк («Уровень»): Договор (голова рамочного ИЛИ разовая
    закупка), Заявка (заказ рамочного), Позиция (PurchaseItem под разовым
    договором или под заявкой рамочного) — сгруппированы Excel row outline
    (владелец 09.10.2026, замечание 1): договор — уровень 0, заявки — 1,
    позиции — 2 (под разовым — 1); всё развёрнуто по умолчанию."""
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
    # Владелец 09.10.2026, замечание 1 — строка-итог группы сверху (договор/
    # заявка выше своих детей); всё развёрнуто по умолчанию (outline_level
    # пишется на строки, не здесь — см. _write_row).
    ws.sheet_properties.outlinePr.summaryBelow = False

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

    def _write_row(cells: list, fill, font, outline_level: int = 0) -> int:
        nonlocal row_num
        idx = row_num
        for ci, val in enumerate(cells, 1):
            cell = ws.cell(row=idx, column=ci, value=val)
            if fill is not None:
                cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            # «Цена за ед.» (владелец/QA 09.10.2026) — тот же числовой вид,
            # что денежные столбцы (_MONEY_COLS), но не входит в их SUM/
            # SUBTOTAL (_PRICE_COLS отдельно от _MONEY_COLS — см. докстринг).
            is_money = ci in _MONEY_COLS or ci in _PRICE_COLS
            cell.alignment = RIGHT_ALIGN if is_money else LEFT_ALIGN
            if is_money and isinstance(val, (int, float)):
                cell.number_format = NUM_FMT
        # Владелец 09.10.2026, замечание 1 — группировка; развёрнуто по
        # умолчанию (hidden=False).
        ws.row_dimensions[idx].outline_level = outline_level
        ws.row_dimensions[idx].hidden = False
        row_num += 1
        return idx

    def _write_item_row(
        level: str, purchase_number, order_number, contract_number, contractor, contractor_inn,
        item: dict, item_kind: str, contract_view: str, contract_kind: str, outline_level: int,
        order_money: dict | None = None,
    ) -> int:
        """Строка «Позиция» — «Контрагент»/«ИНН»/«№ договора»/«Вид
        договора»/«Тип договора» заполнены, как и во всех остальных строках
        группы. «Товар / услуга» наследуется от родительской заявки/разового
        договора; месяцы платежа сюда не попадают (владелец ограничил ими
        только Заявку/разовый договор). `order_money` (владелец, замечание
        2) — {"order_sum","order_delivered","order_paid"} ТОЛЬКО для позиций
        РАЗОВОГО договора (у позиций рамочной заявки — None, деньги заявки
        уже в её собственной строке)."""
        cells = [""] * len(_HEADERS)
        cells[_COL_LEVEL - 1] = level
        cells[_COL_PURCHASE_NUMBER - 1] = purchase_number
        cells[_COL_ORDER_NUMBER - 1] = order_number
        cells[_COL_CONTRACT_NUMBER - 1] = contract_number
        cells[_COL_CONTRACT_VIEW - 1] = contract_view
        cells[_COL_CONTRACT_KIND - 1] = contract_kind
        cells[_COL_CONTRACTOR - 1] = contractor
        cells[_COL_CONTRACTOR_INN - 1] = contractor_inn
        cells[_COL_SUBJECT - 1] = item["name"]
        cells[_COL_ITEM_UNIT - 1] = item["unit"]
        cells[_COL_ITEM_QTY - 1] = item["qty"]
        cells[_COL_ITEM_UNIT_PRICE - 1] = item["unit_price"]
        cells[_COL_ITEM_SUM - 1] = item["total"]
        cells[_COL_ITEM_KIND - 1] = item_kind
        if order_money is not None:
            cells[_COL_ORDER_SUM - 1] = order_money["order_sum"]
            cells[_COL_ORDER_DELIVERED - 1] = order_money["order_delivered"]
            cells[_COL_ORDER_PAID - 1] = order_money["order_paid"]
        return _write_row(cells, None, ITEM_FONT, outline_level=outline_level)

    for g in groups:
        h = g["head"]
        contract_view = h.get("contract_type_view", "")
        contract_kind = h.get("contract_kind", "")
        if h.get("is_framework"):
            # Голова: уровень ДОГОВОРА заполнен числами, уровень ЗАЯВКИ —
            # пусто (факт целиком на строках заявок ниже).
            cells = [""] * len(_HEADERS)
            cells[_COL_LEVEL - 1] = _LEVEL_CONTRACT
            cells[_COL_PURCHASE_NUMBER - 1] = h["purchase_number"]
            cells[_COL_REGISTRY_NUMBER - 1] = h["registry_number"]
            cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
            cells[_COL_CONTRACT_VIEW - 1] = contract_view
            cells[_COL_CONTRACT_KIND - 1] = contract_kind
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
            _write_row(cells, CONTRACT_FILL, CONTRACT_FONT, outline_level=0)

            for o in g["orders"]:
                order_cells = [""] * len(_HEADERS)
                order_cells[_COL_LEVEL - 1] = _LEVEL_ORDER
                order_cells[_COL_ORDER_NUMBER - 1] = o["order_number"]
                order_cells[_COL_REGISTRY_NUMBER - 1] = o["registry_number"]
                order_cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
                order_cells[_COL_CONTRACT_VIEW - 1] = contract_view
                order_cells[_COL_CONTRACT_KIND - 1] = contract_kind
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
                _write_row(order_cells, None, ORDER_FONT, outline_level=1)

                for item in o["items"]:
                    _write_item_row(
                        _LEVEL_ITEM, "", o["order_number"], h["contract_number"],
                        h["contractor"], h["contractor_inn"], item, o.get("item_kind", ""),
                        contract_view, contract_kind, outline_level=2,
                        order_money=None,  # владелец: деньги заявки рамочного — на её строке, не на позиции
                    )
        else:
            items = h["items"]
            # Разовая закупка — одна строка (уровень ДОГОВОРА); уровень
            # ЗАЯВКИ («Сумма заявки»/«Поставлено»/«Оплачено») — в строке
            # договора ТОЛЬКО если позиций нет (владелец, замечание 2); с
            # позициями — эти три величины уходят в строки «Позиция».
            cells = [""] * len(_HEADERS)
            cells[_COL_LEVEL - 1] = _LEVEL_CONTRACT
            cells[_COL_PURCHASE_NUMBER - 1] = h["purchase_number"]
            cells[_COL_REGISTRY_NUMBER - 1] = h["registry_number"]
            cells[_COL_CONTRACT_NUMBER - 1] = h["contract_number"]
            cells[_COL_CONTRACT_VIEW - 1] = contract_view
            cells[_COL_CONTRACT_KIND - 1] = contract_kind
            cells[_COL_CONTRACT_DATE - 1] = h["contract_date"]
            cells[_COL_CONTRACTOR - 1] = h["contractor"]
            cells[_COL_CONTRACTOR_INN - 1] = h["contractor_inn"]
            cells[_COL_SUBJECT - 1] = h["subject"]
            cells[_COL_CONTRACT_SUM - 1] = h["contract_sum"]
            cells[_COL_CONTRACT_ORDERED - 1] = h["ordered"]
            cells[_COL_CONTRACT_REMAINING - 1] = h["remaining"]
            cells[_COL_CONTRACT_DELIVERED - 1] = h["delivered_total"]
            cells[_COL_CONTRACT_PAID - 1] = h["paid_total"]
            if not items:
                cells[_COL_ORDER_SUM - 1] = h["single_sum"]
                cells[_COL_ORDER_DELIVERED - 1] = h["single_delivered"]
                cells[_COL_ORDER_PAID - 1] = h["single_paid"]
            cells[_COL_STATUS - 1] = h["status"]
            cells[_COL_CATEGORY_PATH - 1] = h["category_path"]
            cells[_COL_ITEM_KIND - 1] = h.get("item_kind", "")
            cells[_COL_PLANNED_PAYMENT_MONTH - 1] = h.get("planned_payment_month", "")
            cells[_COL_PAYMENT_MONTH - 1] = h.get("payment_month", "")
            _write_row(cells, CONTRACT_FILL, CONTRACT_FONT, outline_level=0)

            for item in items:
                _write_item_row(
                    _LEVEL_ITEM, h["purchase_number"], "", h["contract_number"],
                    h["contractor"], h["contractor_inn"], item, h.get("item_kind", ""),
                    contract_view, contract_kind, outline_level=1,
                    order_money={
                        "order_sum": item["order_sum"],
                        "order_delivered": item["order_delivered"],
                        "order_paid": item["order_paid"],
                    },
                )

    last_row = row_num - 1
    last_col_letter = ws.cell(row=HEADER_ROW, column=len(_HEADERS)).column_letter
    ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col_letter}{max(last_row, HEADER_ROW)}"
    apply_row_heights(ws, range(1, last_row + 1))
