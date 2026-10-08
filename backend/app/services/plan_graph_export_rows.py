"""plan_graph_export_rows.py — общий сбор пронумерованных строк фактических
закупленных позиций плана-графика (владелец 08.10.2026, замечания к листу
«План закупок»).

ПРАВИЛО №5: один проход по дереву ФЭО собирает строки с ПОЛНЫМИ значениями
(направление/тип/наименование/состав/цена/контрагент/ИНН/№ закупки/№ заявки
и т.д.) и присваивает номера «N» (плановая позиция) / «N.k» (её фактические
строки) — используется ОБОИМИ листами: «План закупок (по направлениям)»
(app.services.plan_graph_export_xlsx, группировка по дереву) и «План закупок
(по порядку)» (app.services.plan_graph_export_flat_sheet, без группировки).
Второй сбор строк где-либо ещё не заводится.

Сортировка (владелец 08.10.2026): плановые позиции внутри статьи — по
наименьшему № закупки среди их закупок (без закупок — в конец, по исходному
порядку); фактические строки внутри позиции/категории — по № закупки, затем
по id закупки.

cascade_by_stage (каскад по стадиям) живёт здесь же — ЕДИНСТВЕННАЯ реализация
на весь экспорт плана-графика (ранее была в plan_graph_export_xlsx.py;
переехала сюда, т.к. теперь нужна и сборщику строк, и обоим листам). Модуль
plan_graph_export_xlsx.py импортирует её отсюда и реэкспортирует под тем же
именем (тесты импортируют cascade_by_stage из plan_graph_export_xlsx)."""
from __future__ import annotations

from app.routers.purchases import STATUS_ORDER as _STATUS_ORDER
from app.services.plan_graph_export_columns import PURCHASE_FIELD_COL_KEYS
from app.services.purchase_export_cells import get_cell_value as _purchase_cell_value

# ── Каскад стадий — ЕДИНСТВЕННАЯ реализация на весь модуль экспорта ────────
_PLANNED_STATUS_SET = {"wishes", "plan_schedule", "work_in_progress"}
_STAGE_BY_STATUS: dict = {}
for _s in _STATUS_ORDER:
    if _s in _PLANNED_STATUS_SET:
        _STAGE_BY_STATUS[_s] = 0
    elif _s == "contracted":
        _STAGE_BY_STATUS[_s] = 1
    elif _s == "ordered":
        _STAGE_BY_STATUS[_s] = 2
    elif _s == "delivered":
        _STAGE_BY_STATUS[_s] = 3
    elif _s == "paid":
        _STAGE_BY_STATUS[_s] = 4


def cascade_by_stage(raw_status: str, total: float) -> tuple:
    """(planned, contract, ordered, delivered, paid) — сумма позиции попадает
    НАКОПИТЕЛЬНО во все столбцы ДО текущей стадии включительно: Запланировано
    ⊇ Договор ⊇ Заказано ⊇ Поставлено ⊇ Оплачено. Отменённые (status=
    'cancelled') и статусы вне STATUS_ORDER (purchases.py) — везде 0."""
    t = round(total or 0, 2)
    idx = _STAGE_BY_STATUS.get(raw_status)
    if idx is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return tuple(t if i <= idx else 0.0 for i in range(5))


def _purchase_number_of(pi: dict, purchase_rows_by_id: dict) -> float:
    """№ закупки позиции `pi` (для сортировки) — float('inf'), если закупка
    не найдена или у неё нет purchase_number (такие позиции сортируются
    последними, владелец: "без закупок — в конце")."""
    p = purchase_rows_by_id.get(pi.get("purchase_id"))
    num = getattr(p, "purchase_number", None) if p is not None else None
    if num is None or num == "":
        return float("inf")
    try:
        return float(num)
    except (TypeError, ValueError):
        return float("inf")


def _sort_key(pi: dict, purchase_rows_by_id: dict) -> tuple:
    """(№ закупки, id закупки) — владелец: "по № закупки, затем по id"."""
    return (_purchase_number_of(pi, purchase_rows_by_id), pi.get("purchase_id") or 0)


def sort_purchased_list(items: list, purchase_rows_by_id: dict) -> list:
    """Сортировка под-строк фактических позиций — ЕДИНСТВЕННАЯ точка (оба
    листа экспорта плана-графика обязаны сортировать через неё)."""
    return sorted(items, key=lambda pi: _sort_key(pi, purchase_rows_by_id))


def sorted_items_for_cat(cat_id, items_by_cat: dict, purchased_by_item: dict, purchase_rows_by_id: dict) -> list:
    """Плановые позиции категории `cat_id`, отсортированные по наименьшему №
    закупки среди их фактических закупок; позиции без закупок (или без
    номера хоть у одной) — в конце, в исходном порядке items_by_cat."""
    items = items_by_cat.get(cat_id, [])

    def _key(pair):
        idx, item = pair
        purchases = purchased_by_item.get(item.id, [])
        nums = [
            n for n in (_purchase_number_of(pi, purchase_rows_by_id) for pi in purchases)
            if n != float("inf")
        ]
        return (min(nums) if nums else float("inf"), idx)

    indexed = sorted(enumerate(items), key=_key)
    return [item for _idx, item in indexed]


def _composition_values(pi: dict, purchase_rows_by_id: dict, purchase_export_ctx: dict) -> dict:
    """«Состав закупки» / «Цена за ед.» / контрагент (позиционный
    contractor_name, фолбэк — контрагент самой закупки через get_cell_value,
    ПРАВИЛО №6 — тот же механизм, что экспорт закупок)."""
    contractor = (pi.get("contractor") or "").strip()
    if not contractor:
        purchase_row = purchase_rows_by_id.get(pi.get("purchase_id"))
        if purchase_row is not None:
            contractor = _purchase_cell_value("contractor", purchase_row, purchase_export_ctx) or ""
    unit_price = pi.get("unit_price") or 0
    return {
        "composition": pi.get("name") or "",
        "unit_price": round(unit_price, 2) if unit_price else "",
        "contractor": contractor,
    }


def _purchase_field_values(pi: dict, purchase_rows_by_id: dict, purchase_export_ctx: dict) -> dict:
    """Значения столбцов, читаемых С САМОЙ ЗАКУПКИ (№ закупки/№ заявки/ИНН/
    группа «Договор и оплата») — через get_cell_value, только если закупка
    найдена (иначе столбец остаётся пустым — закупка под-строки неизвестна)."""
    purchase_row = purchase_rows_by_id.get(pi.get("purchase_id"))
    if purchase_row is None:
        return {}
    return {key: _purchase_cell_value(key, purchase_row, purchase_export_ctx) for key in PURCHASE_FIELD_COL_KEYS}


def _build_fact_row(
    pi: dict, purchase_rows_by_id: dict, purchase_export_ctx: dict,
    contract_balances_by_purchase: dict, *,
    num: str, direction: str, type_: str, name: str,
) -> dict:
    """Одна строка фактической закупленной позиции — полный набор значений
    (ключи PLAN_GRAPH_COLUMNS), проекция на выбранные столбцы делается
    вызывающим кодом (xlsx-модули) при записи. Служебные поля с префиксом
    "_" (сортировка/гиперссылка/суммы каскада) не являются ключами столбцов и
    не попадают в вывод. "level"="Закупка" — владелец 08.10.2026, часть B
    (служебный столбец «Уровень» для SUMIFS верхней строки иерархического
    листа)."""
    planned_a, contract_a, ordered_a, delivered_a, paid_a = cascade_by_stage(pi["raw_status"], pi["total"])
    total_display = 0.0 if pi["raw_status"] == "cancelled" else round(pi["total"], 2)
    status_txt = pi["status"]
    monthly_val = ""
    if pi.get("is_monthly"):
        cnt = pi.get("monthly_count")
        status_txt = f"{status_txt} · ежемес." + (f" ×{cnt}" if cnt else "")
        monthly_val = round(pi["total"], 2)

    row = {
        "level": "Закупка",
        "num": num, "direction": direction, "type": type_, "name": name,
        "unit": pi["unit"], "qty": round(pi["qty"], 3),
        "planned": planned_a, "contract": contract_a, "ordered": ordered_a,
        "delivered": delivered_a, "paid": paid_a, "fact_total": total_display,
        "status": status_txt, "act": pi["act_number"], "monthly": monthly_val,
        # «Товар / услуга» (владелец 08.10.2026, замечание 1) — уже посчитано
        # централизовано app.services.plan_graph_export_data (item_kind_label,
        # ПРАВИЛО №6 — не второй расчёт здесь); отсутствует в синтетических
        # данных старых тестов → "".
        "item_kind": pi.get("item_kind", ""),
    }
    row.update(_composition_values(pi, purchase_rows_by_id, purchase_export_ctx))
    row.update(_purchase_field_values(pi, purchase_rows_by_id, purchase_export_ctx))
    # «Остаток по договору» (владелец 08.10.2026, часть C) — ЕДИНЫЙ источник
    # app.services.contract_balances.contract_balances; без договора — пусто.
    _bal = contract_balances_by_purchase.get(pi.get("purchase_id"))
    row["contract_balance"] = round(_bal["remaining"], 2) if _bal else ""
    row["_purchase_id"] = pi.get("purchase_id")
    row["_sort_key"] = _sort_key(pi, purchase_rows_by_id)
    row["_stages"] = (planned_a, contract_a, ordered_a, delivered_a, paid_a)
    return row


# Верхняя граница диапазона для формул "итого" (часть B, владелец 08.10.2026):
# SUM/SUBTOTAL над строками 4..MAX_DATA_ROW — не нужно знать точное число
# строк данных на момент записи формулы (пишется ДО данных, одним проходом),
# Excel/Google Sheets игнорируют пустые ячейки диапазона.
MAX_DATA_ROW = 100000


def write_flat_top_summary_rows(ws, money_col_indices, *, title: str, data_first_row: int = 4) -> None:
    """Строки 1-2 ПРОСТОГО (не иерархического) листа — владелец 08.10.2026,
    часть B: строка 1 — «Итого всего» (подпись `title` в A1 + =SUM по всем
    строкам данных денежных столбцов), строка 2 — «Итого по фильтру»
    (=SUBTOTAL(109,...) — считает только видимые при автофильтре строки).
    Шапка пишется вызывающим кодом в строке `data_first_row - 1`, данные — с
    `data_first_row`. Общая реализация для «План закупок (по порядку)» и
    «Реестр договоров» (ПРАВИЛО №5 — не копия на каждый лист); иерархический
    «План закупок (по направлениям)» использует СВОЮ схему (SUBTOTAL на
    строках групп + SUMIFS по «Уровню» в строке 1), см.
    plan_graph_export_xlsx.py."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    label_font = Font(bold=True, size=9, color="1E3A5F")
    ws.cell(row=1, column=1, value=title).font = label_font
    ws.cell(row=2, column=1, value="Итого по фильтру").font = label_font
    for ci in money_col_indices:
        col_letter = get_column_letter(ci)
        rng = f"{col_letter}{data_first_row}:{col_letter}{MAX_DATA_ROW}"
        c1 = ws.cell(row=1, column=ci, value=f"=SUM({rng})")
        c1.font = label_font
        c2 = ws.cell(row=2, column=ci, value=f"=SUBTOTAL(109,{rng})")
        c2.font = label_font


def category_full_path(cats: list, cat_id) -> str:
    """"Направление / Тип / Статья" — путь категории ФЭО до корня, одной
    строкой (используется листом «Реестр договоров»,
    plan_graph_export_contracts_sheet.py). Не предполагает ровно 3 уровня
    (в отличие от _build_ancestor_names ниже, завязанного на фиксированную
    форму дерева «План закупок») — общий обход по parent_id, годится для
    категории любого уровня/глубины."""
    if cat_id is None:
        return ""
    by_id = {c.id: c for c in cats}
    names = []
    cur = by_id.get(cat_id)
    while cur is not None:
        names.append(cur.name)
        cur = by_id.get(cur.parent_id)
    return " / ".join(reversed(names))


def _build_ancestor_names(cats: list) -> dict:
    """{cat_id: (direction_name, type_name)} — ДЛЯ КАЖДОЙ категории, любого
    уровня и глубины (владелец 09.10.2026, прод ФАДМ 2026_2: «плановые
    позиции и закупки висят и на level 1/2», дерево местами глубже 3
    уровней) — direction = имя ближайшего предка (или себя) с level==1,
    type = имя ближайшего предка (или себя) с level==2; "" если такого
    предка нет (напр. у категории level==1 своего type нет)."""
    by_id = {c.id: c for c in cats}
    cache: dict = {}

    def _resolve(cat):
        if cat.id in cache:
            return cache[cat.id]
        direction = cat.name if cat.level == 1 else ""
        type_name = cat.name if cat.level == 2 else ""
        parent = by_id.get(cat.parent_id)
        if parent is not None:
            p_direction, p_type = _resolve(parent)
            direction = direction or p_direction
            type_name = type_name or p_type
        result = (direction, type_name)
        cache[cat.id] = result
        return result

    return {c.id: _resolve(c) for c in cats}


def _iter_cats_in_order(cats_by_parent: dict):
    """DFS по дереву категорий ЛЮБОГО уровня/глубины — ТОТ ЖЕ порядок
    обхода, что и в plan_graph_export_xlsx._traverse (направление → тип →
    статья → … → лист), владелец/подкатегория посещаются ДО своих детей —
    собственные позиции/закупки категории любого уровня учитываются."""
    def _walk(parent_id):
        for cat in cats_by_parent.get(parent_id, []):
            yield cat
            yield from _walk(cat.id)
    yield from _walk(None)


def collect_plan_graph_rows(data: dict) -> dict:
    """Один проход по дереву ФЭО — присваивает номера «N»/«N.k» плановым
    позициям и их фактическим закупленным строкам в ОДНОМ порядке для ОБОИХ
    листов экспорта плана-графика.

    Возвращает dict:
      item_seq               — {feo_planned_item_id: "N" (int)}
      items_order_by_cat      — {feo_category_id: [item, ...]} в порядке вывода
      fact_rows_by_item       — {feo_planned_item_id: [row, ...]}
      fact_rows_by_cat        — {feo_category_id: [row, ...]} (закупки прямо
                                 на статье, без плановой позиции)
      fact_rows_unlinked      — [row, ...] (закупки без категории ФЭО)
      items_without_purchase  — [{"cat", "item", "seq", "direction", "type"}, ...]
                                 в порядке дерева — хвост листа «по порядку»
    """
    cats = data["cats"]
    items_by_cat = data["items_by_cat"]
    purchased_by_item = data["purchased_by_item"]
    purchased_by_cat = data["purchased_by_cat"]
    unlinked_purchases = data["unlinked_purchases"]
    purchase_rows_by_id = data.get("purchase_rows_by_id") or {}
    purchase_export_ctx = data.get("purchase_export_ctx") or {}
    contract_balances_by_purchase = data.get("contract_balances_by_purchase") or {}

    cats_by_parent: dict = {}
    for c in cats:
        cats_by_parent.setdefault(c.parent_id, []).append(c)

    ancestor_names = _build_ancestor_names(cats)

    item_seq: dict = {}
    items_order_by_cat: dict = {}
    fact_rows_by_item: dict = {}
    fact_rows_by_cat: dict = {}
    items_without_purchase: list = []
    seq = 0

    for cat in _iter_cats_in_order(cats_by_parent):
        direction_name, type_name = ancestor_names.get(cat.id, ("", ""))

        cat_purchases = sort_purchased_list(purchased_by_cat.get(cat.id, []), purchase_rows_by_id)
        if cat_purchases:
            fact_rows_by_cat[cat.id] = [
                _build_fact_row(
                    pi, purchase_rows_by_id, purchase_export_ctx, contract_balances_by_purchase,
                    num="", direction=direction_name, type_=type_name, name=cat.name,
                )
                for pi in cat_purchases
            ]

        ordered_items = sorted_items_for_cat(cat.id, items_by_cat, purchased_by_item, purchase_rows_by_id)
        items_order_by_cat[cat.id] = ordered_items
        for item in ordered_items:
            seq += 1
            item_seq[item.id] = seq
            purchases = sort_purchased_list(purchased_by_item.get(item.id, []), purchase_rows_by_id)
            if purchases:
                fact_rows_by_item[item.id] = [
                    _build_fact_row(
                        pi, purchase_rows_by_id, purchase_export_ctx, contract_balances_by_purchase,
                        num=f"{seq}.{k}", direction=direction_name, type_=type_name, name=item.name,
                    )
                    for k, pi in enumerate(purchases, 1)
                ]
            else:
                items_without_purchase.append({
                    "cat": cat, "item": item, "seq": seq,
                    "direction": direction_name, "type": type_name,
                })

    fact_rows_unlinked = [
        _build_fact_row(
            pi, purchase_rows_by_id, purchase_export_ctx, contract_balances_by_purchase,
            num="", direction="", type_="", name="",
        )
        for pi in sort_purchased_list(unlinked_purchases, purchase_rows_by_id)
    ]

    return {
        "item_seq": item_seq,
        "items_order_by_cat": items_order_by_cat,
        "fact_rows_by_item": fact_rows_by_item,
        "fact_rows_by_cat": fact_rows_by_cat,
        "fact_rows_unlinked": fact_rows_unlinked,
        "items_without_purchase": items_without_purchase,
    }
