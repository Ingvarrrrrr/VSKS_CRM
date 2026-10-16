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
from app.services.historical_fact_import import statuses as statuses_mod

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
    if isinstance(v, float) and v.is_integer():
        # ИНН/«Номер закупки»/«Номер заказа» на листе GoodsService владельца
        # приходят из openpyxl как float (1.0, 2.0, 7707049388.0) — текстом
        # должно остаться "1"/"7707049388", не "1.0" (natural_purchase_key/
        # classify_contract_kind/valid_inn сравнивают цифровой текст).
        v = int(v)
    s = str(v).strip()
    return s or None


def _to_date(v):
    """«Дата Договора» — на листе владельца встречается И датой Excel
    (datetime.date/datetime через openpyxl), И текстом «24.11.2023» в одной
    и той же колонке (разные строки) — обе формы приводим к date."""
    import datetime as _dt
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


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


def _build_path(l2: Optional[str], l3: Optional[str], l4: Optional[str], l5: Optional[str], leaf_name: str) -> list:
    path = [p for p in (l2, l3) if p and p != leaf_name]
    if l4 and l4 != leaf_name:
        path.append(l4)
    # Лист GoodsService владельца (16.10.2026) — 4-й (новый) уровень «Тип
    # расходов конкретизированный (сам придумываю…)», тот же принцип, что и
    # l2/l3/l4: пустой уровень пропускается, совпадающий с именем позиции —
    # не дублируется.
    if l5 and l5 != leaf_name:
        path.append(l5)
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
            "l5": _to_text(get(raw_row, "path_l5")),
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
        l2, l3, l4, l5, own_item_name = rec["l2"], rec["l3"], rec["l4"], rec["l5"], rec["own_item_name"]

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

        path = _build_path(l2, l3, l4, l5, leaf_name)
        # Чек-лист 13.10.2026 (прод «ДНР 3», «Проезд, проживание, питание»):
        # `path` НЕ годится как категория строки для матчинга — _build_path
        # выбрасывает уровень, РАВНЫЙ имени позиции (чтобы не дублировать его
        # в отображаемом пути), а когда сам Ур.4 файла совпадает с именем
        # позиции (как у строк 151/152), path обрывается на Ур.3 — категория
        # «уезжает» на уровень выше настоящей. `category_name` — самый
        # глубокий ЗАПОЛНЕННЫЙ уровень строки СЕБЯ, независимо от совпадения
        # с leaf_name/именем позиции (matching.py::_row_category_key читает
        # ЕГО, не path — ПРАВИЛО №6, одно поле «категория строки» для
        # матчинга, path остаётся только для отображения/авто-раскрытия
        # дерева, см. FeoPlanTreePicker.vue).
        # Правка (владелец, 16.10.2026, сверка карточек субсидии 26121):
        # лист GoodsService завёл 4-й уровень категории (l5/AH, задача 1
        # «Уровень 5 (категория)») — здесь он не учитывался вовсе, строка с
        # реальной категорией на этом уровне (например, «Услуги связи» под
        # AH) получала category_name НА УРОВЕНЬ ВЫШЕ настоящей категории
        # дерева ФЭО (l4/l3/l2) — _row_category_key не совпадал с
        # _candidate_category_key (последний сегмент пути позиции —
        # настоящая глубокая категория), 14 строк «БРОНИРОВАНИЕ ГОСТИНИЦ» (и
        # другие) уходили в ambiguous/not_found, хотя для каждой строки в
        # плане была СВОЯ позиция с той же суммой в правильной категории.
        category_name = l5 or l4 or l3 or l2

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
        # Группировка по договору (владелец, 16.10.2026, шаг 2) — см.
        # contract_groups.py (ключ группы/разбивка на заказы/лимит/настоящий
        # номер договора — там же, одно определение). Прочитан ДО статуса —
        # правило владельца (16.10.2026, правило 2) для разовых договоров
        # ниже читает contract_kind этой же строки (ПРАВИЛО №6, без второй
        # копии classify_contract_kind).
        inn = _to_text(get(raw_row, "inn"))
        contract_kind = _to_text(get(raw_row, "contract_kind"))
        status_raw = _to_text(get(raw_row, "status_raw")) or _to_text(get(raw_row, "status"))
        if not status_raw and any(
            f in by_field for f in (
                "stage_purchase_done", "stage_contracted", "stage_ordered",
                "stage_delivered", "stage_paid",
            )
        ):
            # Лист GoodsService владельца (16.10.2026) — нет колонки «Статус»/
            # «Правильный статус» вовсе, стадия закупки лежит в 5 колонках
            # Да/Нет — сводим их в тот же текст статуса (подпись одного из 6
            # кодов GALA), чтобы дальше статус разбирал ОДИН источник истины
            # (statuses.resolve_status, ПРАВИЛО №6), а не второй механизм.
            status_raw = statuses_mod.status_label_from_stage_flags(
                purchase_done=_to_advance_bool(get(raw_row, "stage_purchase_done")),
                contracted=_to_advance_bool(get(raw_row, "stage_contracted")),
                ordered_raw=_to_text(get(raw_row, "stage_ordered")),
                delivered=_to_advance_bool(get(raw_row, "stage_delivered")),
                paid=_to_advance_bool(get(raw_row, "stage_paid")),
                contract_kind=contract_kind,
            )
        purchase_no = _to_text(get(raw_row, "purchase_no"))
        supplier = _to_text(get(raw_row, "supplier"))
        comment = _to_text(get(raw_row, "comment"))
        item_type = _to_text(get(raw_row, "item_type"))
        unit = _to_text(get(raw_row, "unit"))
        order_no = _to_text(get(raw_row, "order_no"))
        contract_number = _to_text(get(raw_row, "contract_number"))
        contract_date = _to_date(get(raw_row, "contract_date"))

        out.append({
            "row": excel_row,
            "name": leaf_name,
            "path": path,
            "category_name": category_name,
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
            "inn": inn,
            "contract_kind": contract_kind,
            "order_no": order_no,
            "contract_number": contract_number,
            "contract_date": contract_date,
        })
    return out
