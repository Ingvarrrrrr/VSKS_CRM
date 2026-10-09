"""Разбор строк листа (оба формата) в нормализованные записи.

🟢🔵 Правка (план lazy-swimming-hollerith.md): ничего не переносится из
соседних строк — ни уровни (`path_l2/l3/l4`), ни название позиции. Единственное
исключение — ячейка, объединённая в Excel на несколько строк физически (это
ОДНА ячейка): её читает `import_preview_sheets.read_full_sheet_rows(...,
fill_merged=True)` ДО того, как строки попадают сюда (см. `columns.py::
detect_format_and_header`) — это не повторный carry, а честное прочтение одной
ячейки.

Правило «эта строка — плановая позиция?» — ОДНО на оба импорта (ПРАВИЛО №6,
`feo_import_common.row_is_position`, как в импорте ФЭО):
- если в файле ВООБЩЕ нигде не используется «Плановая позиция»
  (`item_column_in_use=False`) — старое поведение: имя строки = «Плановая
  позиция» (если есть) ИЛИ самый глубокий заполненный уровень СВОЕЙ строки
  (без переноса). Строка без имени — пропуск молча (итог раздела без своих
  детей никогда не бывает в таких файлах — там план лежит прямо на статье).
- если колонка используется хоть где-то в файле — решает СВОЯ строка:
  - есть своё «Плановая позиция» → строка — позиция, имя = это значение,
    путь = свои l2/l3/l4 (без дублей с именем позиции);
  - нет своего имени → строка — категория (статья), не становится
    позицией:
    - **итог**: следующая (непустая) строка не противоречит текущей ни на
      одном уровне, заполненном В ОБЕИХ (пустой уровень у следующей строки —
      не противоречие), и лежит ГЛУБЖЕ (у неё есть своё «Плановая позиция»,
      ИЛИ заполнен уровень глубже самого глубокого заполненного уровня
      текущей строки) — пропуск молча;
    - иначе, если в строке есть данные (status_raw НЕ пуст — ЛЮБОЙ текст, в
      т.ч. нераспознанный или «План закупок»/пусто-код — владелец, ДНРР
      152: «Плановая позиция» пуста, статус «План закупок», об этой строке
      тоже надо уведомить, не пропускать молча; ИЛИ факт не пуст/не 0, ИЛИ
      оплата не пуста/не 0) — строка возвращается с флагом
      `no_item_name=True`, имя = самый глубокий заполненный уровень своей
      строки (только подсказка для предпросмотра — не плановая позиция);
      `preview.py` решает, как это показать владельцу (уведомление, не
      автопривязка);
    - иначе (нет данных вообще — пустой status_raw/факт/оплата) — пропуск
      молча.

Склейка одинаковых названий уровней (path без дублей с именем позиции) —
только внутри одной строки, как и раньше.

ХО: количество факта (колонка S) бывает испорчено порядковыми номерами
(владелец) — кол-во ВСЕГДА пересчитывается из сумма/цена, когда и то, и то
заполнено и цена ненулевая (не читаем сырое значение колонки вообще).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.services.feo_import_common import row_is_position

_WS_RE = re.compile(r"\s+")


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip().replace("\xa0", "").replace(" ", "")
        if not v:
            return None
        v = v.replace(",", ".")
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d


def _to_text(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm_level(v: Optional[str]) -> str:
    """Нормализация значения уровня для сравнения «итог/не итог» — регистр и
    повторные пробелы/табы не важны (owner, план lazy-swimming-hollerith.md)."""
    if not v:
        return ""
    return _WS_RE.sub(" ", str(v).strip()).lower()


_ADVANCE_TRUE = {"да", "yes", "true", "1", "y", "аванс"}


def _to_advance_bool(v) -> bool:
    """Колонка «Аванс (да/нет)» (задача 2, владелец 05.10.2026) — пусто/«нет»/
    что угодно непризнанное = False (постоплата, текущее поведение), «да»/
    «yes»/«true»/«1» = True. Не блокирующий список (как и остальные dropdown
    колонки шаблона — lesson feedback_excel_template_dropdowns), нераспознанный
    текст не считается авансом."""
    s = _to_text(v)
    if not s:
        return False
    return s.strip().lower().replace("ё", "е") in _ADVANCE_TRUE


# Уровни, которые участвуют в сравнении «итог/не итог» (глубина — порядок в
# списке: path_l2 < path_l3 < path_l4 < своё имя позиции).
_LEVEL_FIELDS = ("l2", "l3", "l4")
_LEVEL_DEPTH = {"l2": 2, "l3": 3, "l4": 4}


def _row_is_total_of_next(cur: dict, nxt: dict) -> bool:
    """«Следующая строка — её дети?» — пункт 2 плана lazy-swimming-hollerith.md:
    (а) НЕ противоречит текущей ни на одном уровне, заполненном в ОБЕИХ
    (пустой уровень следующей строки — не противоречие, ДНРР 101-112 после
    строки 100 с L4 пустым); (б) лежит ГЛУБЖЕ текущей — у неё есть своё имя
    позиции, или заполнен уровень глубже самого глубокого заполненного уровня
    текущей строки."""
    for lvl in _LEVEL_FIELDS:
        cur_v, nxt_v = cur[lvl], nxt[lvl]
        if cur_v and nxt_v and _norm_level(cur_v) != _norm_level(nxt_v):
            return False
    cur_depth = max((_LEVEL_DEPTH[lvl] for lvl in _LEVEL_FIELDS if cur[lvl]), default=1)
    if nxt["own_item_name"]:
        return True
    nxt_deeper = any(
        _LEVEL_DEPTH[lvl] > cur_depth and nxt[lvl] for lvl in _LEVEL_FIELDS
    )
    return nxt_deeper


def _row_has_meaningful_data(status_raw: Optional[str], fact_amount, paid) -> bool:
    """Категория без своих позиций, но с данными — не пропуск молча, а
    уведомление (owner, 🔵 правка 3). Данные — это ЛЮБОЙ непустой
    `status_raw` (координатор, повторная правка 10.10: ДНРР 152 — статус
    «План закупок», владелец всё равно хочет уведомление, а не тихий
    пропуск — отличать «План закупок» от «ничего не написано» не нужно; это
    не ветка «статус распознан и это не план закупок», как было раньше),
    ИЛИ есть факт, ИЛИ есть оплата. Итоги (следующая строка — её дети)
    сюда не попадают вообще — та проверка идёт раньше, в `parse_rows`."""
    if status_raw:
        return True
    if fact_amount:
        return True
    if paid:
        return True
    return False


def _build_path(l2: Optional[str], l3: Optional[str], l4: Optional[str], leaf_name: str) -> list:
    path = [p for p in (l2, l3) if p and p != leaf_name]
    if l4 and l4 != leaf_name:
        path.append(l4)
    return path


def parse_rows(detected: dict, columns: list, header_row: int) -> list:
    """Возвращает [{row, name, path, item_type, unit, plan:{...}, fact:{...},
    paid, contracted, status_raw, purchase_no, supplier, comment,
    no_item_name}, ...].

    `row` — номер строки Excel (1-based), для ссылок в предупреждениях/
    decisions.row_overrides. `no_item_name=True` — строка-категория без своей
    «Плановой позиции», но с данными (статус/факт/оплата) — `preview.py`
    превращает её в уведомление, не в плановую позицию (см. docstring модуля).
    """
    all_rows = detected["rows"]
    by_field = {}
    for c in columns:
        if c.get("field"):
            by_field.setdefault(c["field"], c["index"])

    def get(raw_row: list, field: str):
        idx = by_field.get(field)
        if idx is None or idx >= len(raw_row):
            return None
        return raw_row[idx]

    data_rows = all_rows[header_row:]

    # Проход 0: собрать записи по непустым строкам файла (полностью пустые
    # строки Excel — не данные вообще, пропускаются ещё до разбора уровней/
    # имени). Без переноса — l2/l3/l4/own_item_name читаются только из своей
    # строки.
    records: list[dict] = []
    for offset, raw_row in enumerate(data_rows):
        excel_row = header_row + offset + 1
        if raw_row is None or not any(c is not None and str(c).strip() != "" for c in raw_row):
            continue
        records.append({
            "excel_row": excel_row,
            "raw": raw_row,
            "l2": _to_text(get(raw_row, "path_l2")),
            "l3": _to_text(get(raw_row, "path_l3")),
            "l4": _to_text(get(raw_row, "path_l4")),
            "own_item_name": _to_text(get(raw_row, "plan_item_name")),
        })

    # «Плановая позиция» используется в файле хоть где-то (feedback_no_logic_
    # keyed_to_optional_level.md — решает файл целиком, не отдельная строка).
    item_column_in_use = "plan_item_name" in by_field and any(
        r["own_item_name"] for r in records
    )

    out = []
    for idx, rec in enumerate(records):
        raw_row = rec["raw"]
        excel_row = rec["excel_row"]
        l2, l3, l4, own_item_name = rec["l2"], rec["l3"], rec["l4"], rec["own_item_name"]

        is_position = row_is_position(bool(own_item_name), item_column_in_use)

        if is_position:
            leaf_name = own_item_name or l4 or l3  # old-format fallback (item_column_in_use=False)
            if not leaf_name:
                # Строка-итог раздела/направления расходов (нет листового имени) — пропуск.
                continue
            no_item_name_flag = False
        else:
            # Категория (статья) без своей «Плановой позиции» — item_column_in_use=True.
            status_raw_val = _to_text(get(raw_row, "status_raw")) or _to_text(get(raw_row, "status"))
            fact_amount_val = _to_dec(get(raw_row, "fact_amount"))
            paid_val = _to_dec(get(raw_row, "paid"))

            next_rec = records[idx + 1] if idx + 1 < len(records) else None
            if next_rec is not None and _row_is_total_of_next(rec, next_rec):
                continue  # итог — её дети идут следующими строками, пропуск молча

            leaf_name = l4 or l3 or l2
            if not leaf_name:
                continue  # нечем подписать категорию — ничего показать владельцу
            if not _row_has_meaningful_data(status_raw_val, fact_amount_val, paid_val):
                continue  # категория без позиций и без данных — пропуск молча
            no_item_name_flag = True

        path = _build_path(l2, l3, l4, leaf_name)

        plan_qty = _to_dec(get(raw_row, "plan_qty"))
        plan_price = _to_dec(get(raw_row, "plan_price"))
        plan_amount = _to_dec(get(raw_row, "plan_amount"))

        fact_amount = _to_dec(get(raw_row, "fact_amount"))
        fact_price = _to_dec(get(raw_row, "fact_price"))
        fact_qty_raw = _to_dec(get(raw_row, "fact_qty"))
        fact_qty = fact_qty_raw
        if fact_amount is not None and fact_price not in (None, Decimal(0)):
            fact_qty = (fact_amount / fact_price)

        paid = _to_dec(get(raw_row, "paid"))
        advance = _to_advance_bool(get(raw_row, "advance"))
        contracted = _to_dec(get(raw_row, "contracted"))
        status_raw = _to_text(get(raw_row, "status_raw")) or _to_text(get(raw_row, "status"))
        purchase_no = _to_text(get(raw_row, "purchase_no"))
        supplier = _to_text(get(raw_row, "supplier"))
        comment = _to_text(get(raw_row, "comment"))
        item_type = _to_text(get(raw_row, "item_type"))
        unit = _to_text(get(raw_row, "unit"))

        out.append({
            "row": excel_row,
            "name": leaf_name,
            "path": path,
            "item_type": item_type,
            "unit": unit,
            "plan": {"qty": plan_qty, "price": plan_price, "amount": plan_amount},
            "fact": {"qty": fact_qty, "price": fact_price, "amount": fact_amount},
            "paid": paid,
            "advance": advance,
            "contracted": contracted,
            "status_raw": status_raw,
            "purchase_no": purchase_no,
            "supplier": supplier,
            "comment": comment,
            "no_item_name": no_item_name_flag,
        })
    return out
