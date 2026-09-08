"""Этап 3 импорта ФЭО: снимок предыдущей редакции + основной цикл по строкам.

Перенесено из тела `_do_feo_import` (было ~строки 277–352, 374–385, 410–892 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) БЕЗ
изменения порядка side-effect'ов — `flush`/`commit`, накопление
warnings/errors идут в том же порядке, что и раньше, тот же код просто
читает свои входы из `state` вместо замыкания над локальными переменными
`_do_feo_import`.

`_check_unit_shift`/`_numeric_shift_scan`/`find_or_create` остаются
вложенными функциями (как и в оригинале) — они замыкаются на `warnings`/
`cat_cache`/`db`/переменную цикла `row`, вынести их отдельно значило бы
менять сигнатуры без необходимости. `_full_path` заменена на модульную
`feo_import_snapshot.full_path(existing_by_id, cat_id)` — в оригинале это
было замыкание над `existing_by_id`, здесь тот же существующий helper
(Правило №6, не заводить второй).
"""
from decimal import Decimal

from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.services.feo_import_common import QUANT, ZERO, get_cell, to_bool, to_dec
from app.services.feo_import_common import fmt as _fmt
from app.services.feo_import_common import norm as _norm
from app.services.feo_import_snapshot import full_path


async def apply_rows(state) -> None:
    db = state.db
    user = state.user
    rows = state.rows
    remap_list = state.remap_list
    sub_by_name = state.sub_by_name
    default_subsidy_id = state.default_subsidy_id
    cat_cache = state.cat_cache
    existing_by_id = state.existing_by_id
    touched_subsidies = state.touched_subsidies

    c_subsidy = state.c_subsidy
    c_lvl2 = state.c_lvl2
    c_lvl3 = state.c_lvl3
    c_lvl4 = state.c_lvl4
    c_lvl5 = state.c_lvl5
    c_qty = state.c_qty
    c_unit = state.c_unit
    c_item_amt = state.c_item_amt
    c_code = state.c_code
    c_appendix = state.c_appendix
    c_budget = state.c_budget
    c_active = state.c_active
    c_qty_lvl2 = state.c_qty_lvl2
    c_qty_lvl3 = state.c_qty_lvl3
    c_qty_lvl4 = state.c_qty_lvl4
    c_unit_lvl2 = state.c_unit_lvl2
    c_unit_lvl3 = state.c_unit_lvl3
    c_unit_lvl4 = state.c_unit_lvl4
    c_amt_lvl2 = state.c_amt_lvl2
    c_amt_lvl3 = state.c_amt_lvl3
    c_amt_lvl4 = state.c_amt_lvl4
    c_feo_qty_lvl2 = state.c_feo_qty_lvl2
    c_feo_qty_lvl3 = state.c_feo_qty_lvl3
    c_feo_qty_lvl4 = state.c_feo_qty_lvl4
    c_feo_unit_lvl2 = state.c_feo_unit_lvl2
    c_feo_unit_lvl3 = state.c_feo_unit_lvl3
    c_feo_unit_lvl4 = state.c_feo_unit_lvl4
    c_feo_amt_lvl2 = state.c_feo_amt_lvl2
    c_feo_amt_lvl3 = state.c_feo_amt_lvl3
    c_feo_amt_lvl4 = state.c_feo_amt_lvl4
    c_feo_sum_lvl2 = state.c_feo_sum_lvl2
    c_feo_sum_lvl3 = state.c_feo_sum_lvl3
    c_feo_sum_lvl4 = state.c_feo_sum_lvl4
    c_plan_sum_lvl2 = state.c_plan_sum_lvl2
    c_plan_sum_lvl3 = state.c_plan_sum_lvl3
    c_plan_sum_lvl4 = state.c_plan_sum_lvl4
    c_item_price = state.c_item_price
    c_row_feo_qty = state.c_row_feo_qty
    c_row_feo_unit = state.c_row_feo_unit
    c_row_feo_price = state.c_row_feo_price
    c_row_feo_sum = state.c_row_feo_sum
    c_row_plan_qty = state.c_row_plan_qty
    c_row_plan_unit = state.c_row_plan_unit
    c_row_plan_price = state.c_row_plan_price
    c_row_plan_sum = state.c_row_plan_sum
    c_item_type = state.c_item_type

    errors = state.errors
    warnings = state.warnings
    created_details = state.created_details
    updated_details = state.updated_details
    skipped_details = state.skipped_details
    seen_ids = state.seen_ids
    seen_roots = state.seen_roots
    new_paths = state.new_paths
    new_path_cats = state.new_path_cats
    collected_plan = state.collected_plan
    lvl5_leaves = state.lvl5_leaves
    lvl5_sum_by_cat = state.lvl5_sum_by_cat
    touched_parents = state.touched_parents

    created = state.created
    updated = state.updated
    skipped = state.skipped

    _new_paths_seen: set[str] = set()

    try:
        # Нормализатор типа плановой позиции (Товар/Услуга/Работа) — общий с
        # app.routers.feo_planned_items, чтобы не разъезжались правила. Локальный
        # fallback ниже — только на случай, если модуль/функция ещё не готовы
        # (параллельная задача добавляет и её, и поле FeoPlannedItem.item_type);
        # предпочтителен импорт, fallback не должен жить долго.
        from app.routers.feo_planned_items import normalize_item_type
    except ImportError:
        def normalize_item_type(v):
            if not v:
                return None
            s = str(v).strip().lower()
            mapping = {
                "товар": "товар", "товары": "товар", "т": "товар",
                "услуга": "услуга", "услуги": "услуга", "у": "услуга",
                "работа": "работа", "работы": "работа", "р": "работа",
            }
            return mapping.get(s)

    def _check_unit_shift(raw: str | None, row_num: int, name: str, col_label: str) -> str | None:
        """Признак сдвига колонок при импорте ФЭО (задача владельца 2026-08-07,
        прод: часть категорий получила ЧИСЛО в feo_categories.unit, а сумму — в
        planned_amount/feo_amount вместо цены за единицу). Если значение, попавшее
        в колонку «Ед. изм.», само выглядит числом (после нормализации пробелов/
        неразрывных пробелов и запятой→точка) — это почти наверняка не единица
        измерения, а число из соседней колонки, уехавшей на одну позицию влево.
        Не молчим: пишем warning нового вида "column_shift" в тот же массив
        `warnings`, что уже уходит на фронт, и НЕ отдаём число дальше как unit —
        вызывающий код оставит прежнее/пустое значение вместо мусора.
        Существующая проверка sum_mismatch (см. ниже) здесь бессильна: она
        сравнивает сумму с кол-во×цена только когда в файле ЕСТЬ отдельная колонка
        «Сумма по ФЭО» — а типичный сдвиг (нет колонки «Ед.изм.» в исходнике)
        одновременно сдвигает и её, оставляя feo_sum пустым, так что сравнивать
        не с чем. Эта проверка — независимый сигнал, не требующий колонки суммы.
        """
        if raw is None:
            return None
        s = raw.strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
        if not s:
            return raw
        try:
            float(s)
        except (ValueError, TypeError):
            return raw
        warnings.append({
            "kind": "column_shift",
            "row": row_num,
            "name": name or "",
            "message": f"Строка {row_num}: в колонке «{col_label}» число {raw} — похоже, колонки сдвинуты, проверьте раскладку файла",
        })
        return None

    def _numeric_shift_scan(row_num: int, level_n: int, next_name: str | None, cols_and_labels: list) -> str | None:
        """Обратный случай column_shift (задача владельца, боевой файл «Субсидия
        ДНР 2.xlsx», 82 строки): не единица измерения попала в числовую колонку,
        а НАЗВАНИЕ следующего уровня — стояло в числовой колонке уровня N (между
        заголовком уровня и его собственными числовыми колонками — до семи
        числовых колонок, легко промахнуться). to_dec() на таком тексте молча
        возвращает None и уровень N+1 просто исчезает — соседний уровень N+2
        (например «Уровень 4») поджимается на его место и становится СОСЕДОМ
        уровня N, а не его ребёнком (баг «лишняя папка-двойник»).

        Признак: значение длиннее 15 символов, не приводится к числу, строка не
        служебная (не начинается с «←»). Если колонка «Уровень N+1» пуста —
        текст принимается как её имя (то самое, что «должно было» туда попасть).
        Если колонка «Уровень N+1» уже заполнена — текст игнорируется, тем не
        менее предупреждаем (возможно опечатка/дублирование, стоит проверить строку).
        Возвращает восстановленное имя уровня N+1 (или None, если восстанавливать нечего).
        """
        recovered: str | None = None
        cur_next = next_name
        for col, label in cols_and_labels:
            raw = get_cell(row, col)
            if raw is None or raw.startswith("←"):
                continue
            if len(raw) <= 15 or to_dec(raw) is not None:
                continue
            short = raw if len(raw) <= 40 else raw[:40] + "…"
            if not cur_next:
                warnings.append({
                    "kind": "level_name_in_number_column",
                    "row": row_num,
                    "name": raw,
                    "message": f"Название «{short}» стояло в колонке «{label}» — принято как Уровень {level_n + 1}",
                })
                recovered = raw
                cur_next = raw
            else:
                warnings.append({
                    "kind": "level_name_in_number_column",
                    "row": row_num,
                    "name": raw,
                    "message": f"Название «{short}» стояло в колонке «{label}» — Уровень {level_n + 1} уже заполнен, проверьте строку",
                })
        return recovered

    async def find_or_create(subsidy_id: int, parent_id, name: str, level: int):
        key = (subsidy_id, parent_id, name.lower().strip())
        if key in cat_cache:
            return cat_cache[key], False
        cat = FeoCategory(
            name=name, subsidy_id=subsidy_id, parent_id=parent_id, level=level,
            is_active=True,
        )
        db.add(cat)
        await db.flush()
        cat_cache[key] = cat
        return cat, True

    # --- N2б: снимок предыдущей редакции — ВСЕГДА и ДО основного цикла.
    # _create_plan_graph_version заново селектит FeoCategory, поэтому вызывать
    # её нужно именно здесь: после основного цикла дерево уже было бы изменено
    # (создание/обновление/удаление), и снимок перестал бы быть "предыдущей"
    # редакцией. Снимок самодостаточен (дерево пишется в JSON инлайном), так
    # что последующее удаление узлов не портит уже сохранённую версию.
    state.version_created = False
    if user is not None:
        _remap_note_suffix = ""
        if remap_list:
            _pairs = []
            for _rm in remap_list[:5]:
                _pairs.append(f"«{full_path(existing_by_id, _rm['old_id'])}» → «{_rm['new_path']}»")
            _remap_note_suffix = "; перенос узлов: " + "; ".join(_pairs)
            if len(remap_list) > 5:
                _remap_note_suffix += f" и ещё {len(remap_list) - 5}"
        _note = "Загрузка новой редакции разбивки ФЭО" + _remap_note_suffix
        from app.routers.purchases import _create_plan_graph_version
        for _sid in touched_subsidies:
            _v_created = await _create_plan_graph_version(subsidy_id=_sid, db=db, user=user, note=_note)
            if _v_created:
                state.version_created = True

    for row_num, row in enumerate(rows, start=2):
        lvl2_name = get_cell(row, c_lvl2)

        # Строка-подсказка («← ...») — всегда служебная, ничего в ней (включая
        # числовые колонки) реальными данными не считаем.
        if lvl2_name and lvl2_name.startswith("←"):
            skipped += 1
            skipped_details.append({"row": row_num, "name": lvl2_name, "reason": "служебная строка"})
            continue

        lvl3_name = get_cell(row, c_lvl3)
        lvl4_name = get_cell(row, c_lvl4)
        lvl5_name = get_cell(row, c_lvl5)

        # Защита от сдвига колонок (боевой файл «Субсидия ДНР 2.xlsx»): название
        # уровня N+1, случайно набранное в числовой колонке уровня N, — вернуть
        # на место ДО того, как из lvl2/3/4/5_name соберётся дерево строки.
        lvl3_name = _numeric_shift_scan(row_num, 2, lvl3_name, [
            (c_feo_qty_lvl2, "Кол-во по ФЭО (Ур.2)"),
            (c_feo_amt_lvl2, "Стоимость по ФЭО (Ур.2)"),
            (c_feo_sum_lvl2, "Сумма по ФЭО (Ур.2)"),
            (c_qty_lvl2, "Плановое кол-во (Ур.2)"),
            (c_amt_lvl2, "Плановая стоимость за ед. (Ур.2)"),
            (c_plan_sum_lvl2, "Сумма плана (Ур.2)"),
        ]) or lvl3_name
        lvl4_name = _numeric_shift_scan(row_num, 3, lvl4_name, [
            (c_feo_qty_lvl3, "Кол-во по ФЭО (Ур.3)"),
            (c_feo_amt_lvl3, "Стоимость по ФЭО (Ур.3)"),
            (c_feo_sum_lvl3, "Сумма по ФЭО (Ур.3)"),
            (c_qty_lvl3, "Плановое кол-во (Ур.3)"),
            (c_amt_lvl3, "Плановая стоимость за ед. (Ур.3)"),
            (c_plan_sum_lvl3, "Сумма плана (Ур.3)"),
        ]) or lvl4_name
        lvl5_name = _numeric_shift_scan(row_num, 4, lvl5_name, [
            (c_feo_qty_lvl4, "Кол-во по ФЭО (Ур.4)"),
            (c_feo_amt_lvl4, "Стоимость по ФЭО (Ур.4)"),
            (c_feo_sum_lvl4, "Сумма по ФЭО (Ур.4)"),
            (c_qty_lvl4, "Плановое кол-во (Ур.4)"),
            (c_amt_lvl4, "Плановая стоимость за ед. (Ур.4)"),
            (c_plan_sum_lvl4, "Сумма плана (Ур.4)"),
        ]) or lvl5_name

        # Позиция без уровней → переезжает на Уровень 2 (задача владельца,
        # шаблон 2026-08-14): если Ур.2/3/4 пусты, а «Плановая позиция» заполнена —
        # её название становится направлением (Ур.2), плановая позиция при этом
        # НЕ создаётся — продолжение правила «пропущенный уровень поджимается
        # вверх», доведённое до предела (когда поджиматься уже некуда). Никакой
        # памяти между строками не заводим, к предыдущей строке ничего не цепляем.
        if (not lvl2_name) and (not lvl3_name or lvl3_name.startswith("←")) and (not lvl4_name or lvl4_name.startswith("←")):
            if lvl5_name and not lvl5_name.startswith("←"):
                warnings.append({
                    "kind": "item_promoted_to_level2",
                    "row": row_num,
                    "name": lvl5_name,
                    "message": f"Плановая позиция «{lvl5_name}» — в строке нет ни одного уровня, создана направлением (Ур.2)",
                })
                lvl2_name = lvl5_name
                lvl5_name = None

        if not lvl2_name:
            skipped += 1
            skipped_details.append({
                "row": row_num,
                "name": lvl2_name or "(пустая строка)",
                "reason": "нет наименования (уровень 2 пуст)",
            })
            continue

        sub_name = get_cell(row, c_subsidy) if c_subsidy is not None else None
        if sub_name and not sub_name.startswith("←"):
            subsidy_id = sub_by_name.get(sub_name.lower().strip()) or default_subsidy_id
            if not subsidy_id:
                errors.append({"row": row_num, "name": lvl2_name, "message": f"Субсидия не найдена: '{sub_name}'"})
                continue
        else:
            subsidy_id = default_subsidy_id
            if not subsidy_id:
                skipped += 1
                skipped_details.append({"row": row_num, "name": lvl2_name, "reason": "не указана субсидия назначения"})
                continue

        code      = get_cell(row, c_code)
        appendix  = get_cell(row, c_appendix)
        budget    = to_dec(get_cell(row, c_budget))
        is_active = to_bool(get_cell(row, c_active))

        item_qty    = to_dec(get_cell(row, c_qty))
        item_unit   = get_cell(row, c_unit)
        item_unit   = _check_unit_shift(
            item_unit, row_num, lvl5_name or lvl4_name or lvl3_name or lvl2_name, "Ед. изм. (Ур.5)"
        )
        item_amount = to_dec(get_cell(row, c_item_amt))
        item_price  = to_dec(get_cell(row, c_item_price)) if c_item_price is not None else None

        raw_item_type = get_cell(row, c_item_type) if c_item_type is not None else None
        item_type = normalize_item_type(raw_item_type) if raw_item_type else None
        if raw_item_type and item_type is None:
            warnings.append({
                "kind": "item_type_unknown",
                "row": row_num,
                "name": lvl5_name or lvl2_name,
                "message": f"Тип позиции «{raw_item_type}» не распознан (ожидались: товар/услуга/работа) — не заполнен",
            })

        # Считать все данные по уровням (raw, без приоритизации)
        _lv = [
            {
                "level_src": 2,
                "name": lvl2_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl2))  if c_feo_qty_lvl2  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl2) if c_feo_unit_lvl2 is not None else get_cell(row, c_unit_lvl2),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl2))  if c_feo_amt_lvl2  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl2))  if c_feo_sum_lvl2  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl2))      if c_qty_lvl2      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl2)             if c_unit_lvl2     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl2))      if c_amt_lvl2      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl2)) if c_plan_sum_lvl2 is not None else None,
            },
            {
                "level_src": 3,
                "name": lvl3_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl3))  if c_feo_qty_lvl3  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl3) if c_feo_unit_lvl3 is not None else get_cell(row, c_unit_lvl3),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl3))  if c_feo_amt_lvl3  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl3))  if c_feo_sum_lvl3  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl3))      if c_qty_lvl3      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl3)             if c_unit_lvl3     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl3))      if c_amt_lvl3      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl3)) if c_plan_sum_lvl3 is not None else None,
            },
            {
                "level_src": 4,
                "name": lvl4_name,
                "feo_qty":  to_dec(get_cell(row, c_feo_qty_lvl4))  if c_feo_qty_lvl4  is not None else None,
                "feo_unit": get_cell(row, c_feo_unit_lvl4) if c_feo_unit_lvl4 is not None else get_cell(row, c_unit_lvl4),
                "feo_amt":  to_dec(get_cell(row, c_feo_amt_lvl4))  if c_feo_amt_lvl4  is not None else None,
                "feo_sum":  to_dec(get_cell(row, c_feo_sum_lvl4))  if c_feo_sum_lvl4  is not None else None,
                "plan_qty": to_dec(get_cell(row, c_qty_lvl4))      if c_qty_lvl4      is not None else None,
                "plan_unit":get_cell(row, c_unit_lvl4)             if c_unit_lvl4     is not None else None,
                "plan_amt": to_dec(get_cell(row, c_amt_lvl4))      if c_amt_lvl4      is not None else None,
                "plan_sum": to_dec(get_cell(row, c_plan_sum_lvl4)) if c_plan_sum_lvl4 is not None else None,
            },
        ]

        # Обратная совместимость: если нет явного c_feo_qty_lvlN — берём plan_qty за feo_qty
        for lv in _lv:
            if lv["level_src"] == 2 and c_feo_qty_lvl2 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]
            elif lv["level_src"] == 3 and c_feo_qty_lvl3 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]
            elif lv["level_src"] == 4 and c_feo_qty_lvl4 is None and lv["feo_qty"] is None and lv["plan_qty"] is not None:
                lv["feo_qty"] = lv["plan_qty"]

        # --- Плоские числа нового 18-колоночного шаблона (2026-08-14): «Количество/
        # Ед.изм./Цена/Сумма по ФЭО» и «Плановое количество/Ед.изм./Цена/Сумма плана» —
        # ОДНА пара колонок на всю строку, не по уровням. Прикрепляются к САМОМУ
        # ГЛУБОКОМУ заполненному уровню строки, либо — если заполнена «Плановая
        # позиция» — к переменной позиции (item_qty/item_unit/item_price/item_amount).
        # Значения из per-level колонок (уже посчитаны в _lv выше) ИМЕЮТ ПРИОРИТЕТ —
        # присваиваем только там, где ещё None, — так старые 37-колоночные файлы
        # (с явными per-level колонками) ведут себя ровно как раньше.
        _row_feo_qty   = to_dec(get_cell(row, c_row_feo_qty))   if c_row_feo_qty   is not None else None
        _row_feo_unit  = get_cell(row, c_row_feo_unit)          if c_row_feo_unit  is not None else None
        _row_feo_price = to_dec(get_cell(row, c_row_feo_price)) if c_row_feo_price is not None else None
        _row_feo_sum   = to_dec(get_cell(row, c_row_feo_sum))   if c_row_feo_sum   is not None else None
        _row_plan_qty   = to_dec(get_cell(row, c_row_plan_qty))   if c_row_plan_qty   is not None else None
        _row_plan_unit  = get_cell(row, c_row_plan_unit)          if c_row_plan_unit  is not None else None
        _row_plan_price = to_dec(get_cell(row, c_row_plan_price)) if c_row_plan_price is not None else None
        _row_plan_sum   = to_dec(get_cell(row, c_row_plan_sum))   if c_row_plan_sum   is not None else None

        _deepest_lv = next((lv for lv in reversed(_lv) if lv["name"]), None)

        if _deepest_lv is not None and any(v is not None for v in (_row_feo_qty, _row_feo_unit, _row_feo_price, _row_feo_sum)):
            if _deepest_lv["feo_qty"] is None:
                _deepest_lv["feo_qty"] = _row_feo_qty
            if _deepest_lv["feo_unit"] is None:
                _deepest_lv["feo_unit"] = _row_feo_unit
            if _deepest_lv["feo_amt"] is None:
                _deepest_lv["feo_amt"] = _row_feo_price
            if _deepest_lv["feo_sum"] is None:
                _deepest_lv["feo_sum"] = _row_feo_sum

        if any(v is not None for v in (_row_plan_qty, _row_plan_unit, _row_plan_price, _row_plan_sum)):
            if lvl5_name and not lvl5_name.startswith("←"):
                # «Плановая позиция» заполнена — плоский план описывает ЕЁ (переменную
                # позицию), а не категорию; см. item_qty/item_unit/item_price/item_amount ниже.
                if item_qty is None:
                    item_qty = _row_plan_qty
                if item_unit is None:
                    item_unit = _row_plan_unit
                if item_price is None:
                    item_price = _row_plan_price
                if item_amount is None:
                    item_amount = _row_plan_sum
            elif _deepest_lv is not None:
                if _deepest_lv["plan_qty"] is None:
                    _deepest_lv["plan_qty"] = _row_plan_qty
                if _deepest_lv["plan_unit"] is None:
                    _deepest_lv["plan_unit"] = _row_plan_unit
                if _deepest_lv["plan_amt"] is None:
                    _deepest_lv["plan_amt"] = _row_plan_price
                if _deepest_lv["plan_sum"] is None:
                    _deepest_lv["plan_sum"] = _row_plan_sum

        # Оставляем только уровни с непустым именем
        filled = [lv for lv in _lv if lv["name"]]

        # Схлопываем соседние дубли по нормализованному имени
        deduped: list[dict] = []
        for lv in filled:
            if deduped and _norm(deduped[-1]["name"]) == _norm(lv["name"]):
                warnings.append({
                    "kind": "level_duplicate",
                    "row": row_num,
                    "name": lv["name"],
                    "message": f"Ур.{lv['level_src']} и Ур.{deduped[-1]['level_src']} названы одинаково — склеены в один узел",
                })
                # Числа объединяем с приоритетом нижнего непустого
                prev = deduped[-1]
                for k in ("feo_qty", "feo_unit", "feo_amt", "feo_sum", "plan_qty", "plan_unit", "plan_amt", "plan_sum"):
                    if lv[k] is not None:
                        prev[k] = lv[k]
            else:
                # Проверяем пропуск уровня: если предыдущий src=2 а текущий src=4 — Ур.3 был пропущен
                if deduped and lv["level_src"] - deduped[-1]["level_src"] > 1:
                    warnings.append({
                        "kind": "level_gap",
                        "row": row_num,
                        "name": lv["name"],
                        "message": f"Ур.{lv['level_src']} поднят на место Ур.{deduped[-1]['level_src'] + 1} — промежуточный уровень не заполнен",
                    })
                deduped.append(lv)

        # Нет ни одного заполненного уровня — уже пропустили по lvl2_name выше
        try:
            prev_cat = None
            cats_in_row: list[FeoCategory] = []
            leaf_is_new = False  # будет обновлён на последней итерации
            # Базовый level в БД для первого элемента = 1 (совпадает со старым поведением)
            for seq_idx, lv in enumerate(deduped):
                db_level = seq_idx + 1
                parent_id = prev_cat.id if prev_cat else None
                cat, is_new = await find_or_create(subsidy_id, parent_id, lv["name"], db_level)
                leaf_is_new = is_new  # последнее значение = флаг создания листового узла

                if is_new:
                    created += 1
                    label = {1: "направление (ур. 2)", 2: "категория (ур. 3)", 3: "статья (ур. 4)"}.get(db_level, f"уровень {db_level + 1}")
                    created_details.append({"row": row_num, "name": lv["name"], "reason": label})

                # --- ФЭО-поля ---
                feo_qty  = lv["feo_qty"]
                feo_unit = lv["feo_unit"]
                feo_unit = _check_unit_shift(
                    feo_unit, row_num, lv["name"], f"Ед. изм. по ФЭО (Ур.{lv['level_src']})"
                )
                feo_amt  = lv["feo_amt"]
                feo_sum  = lv["feo_sum"]

                # Сумма ФЭО → budget
                if feo_sum is not None:
                    # Проверяем расхождение с кол-во × цена
                    if feo_qty is not None and feo_amt is not None and feo_qty != ZERO:
                        calc = (feo_qty * feo_amt).quantize(QUANT)
                        if abs(calc - feo_sum) > Decimal("0.01"):
                            warnings.append({
                                "kind": "sum_mismatch",
                                "row": row_num,
                                "name": lv["name"],
                                "message": f"Сумма по ФЭО {_fmt(feo_sum)} ≠ кол-во × цена = {_fmt(calc)}; взята сумма из файла",
                            })
                    if cat.budget != feo_sum:
                        cat.budget = feo_sum
                    # Если feo_amt пуст, но есть кол-во — восстановим цену
                    if feo_amt is None and feo_qty is not None and feo_qty != ZERO:
                        feo_amt = (feo_sum / feo_qty).quantize(QUANT)

                if feo_qty is not None and cat.feo_quantity != feo_qty:
                    cat.feo_quantity = feo_qty
                if feo_unit and cat.feo_unit != feo_unit:
                    cat.feo_unit = feo_unit
                if feo_amt is not None and cat.feo_amount != feo_amt:
                    cat.feo_amount = feo_amt

                # --- Плановые поля ---
                # 2026-08: план строки больше НЕ пишется в cat.planned_quantity/
                # cat.planned_amount — только копится в collected_plan. Присвоение
                # полей категории отсюда убрано намеренно: план должен жить
                # ЗАПИСЬЮ FeoPlannedItem внутри категории (там amount — СУММА,
                # не цена за единицу), а не полями категории. Что именно делать
                # с собранным планом (создать позицию листа / обновить существующую /
                # обнулить поля группы) решается ПОСЛЕ цикла по всем строкам файла —
                # см. блок обработки collected_plan ниже, там уже видно, у какой
                # категории есть дети, а у какой — свои позиции Ур.5.
                plan_qty  = lv["plan_qty"]
                plan_unit = lv["plan_unit"]
                plan_unit = _check_unit_shift(
                    plan_unit, row_num, lv["name"], f"Ед. изм. плана (Ур.{lv['level_src']})"
                )
                plan_amt  = lv["plan_amt"]
                plan_sum  = lv["plan_sum"]

                _pu = plan_unit if plan_unit is not None else feo_unit

                if plan_sum is not None:
                    # Проверяем расхождение
                    if plan_qty is not None and plan_amt is not None and plan_qty != ZERO:
                        calc_ps = (plan_qty * plan_amt).quantize(QUANT)
                        if abs(calc_ps - plan_sum) > Decimal("0.01"):
                            warnings.append({
                                "kind": "sum_mismatch",
                                "row": row_num,
                                "name": lv["name"],
                                "message": f"Сумма плана {_fmt(plan_sum)} ≠ кол-во × цена = {_fmt(calc_ps)}; взята сумма из файла",
                            })
                    if plan_qty is None:
                        warnings.append({
                            "kind": "sum_without_qty",
                            "row": row_num,
                            "name": lv["name"],
                            "message": f"Сумма плана {_fmt(plan_sum)} задана без кол-во; установлено кол-во = 1",
                        })
                    # amount = сумма плана как есть; qty = кол-во из файла, иначе 1
                    eff_plan_qty = plan_qty if (plan_qty is not None and plan_qty != ZERO) else Decimal("1")
                    collected_plan[cat.id] = {
                        "qty": eff_plan_qty,
                        "unit": _pu,
                        "amount": plan_sum,
                        "row": row_num,
                        "name": cat.name,
                        "item_type": item_type,
                        "from_feo_fallback": False,
                    }
                else:
                    # Старое поведение источника данных: план кол-во/ед/цена напрямую.
                    # Если ОБЕ плановые колонки (кол-во и цена) пусты — сумма целиком
                    # взята из чисел «по ФЭО» (feo_qty × feo_amt), а не из плановых
                    # колонок; помечаем происхождение флагом from_feo_fallback, чтобы
                    # предупреждение plan_vs_items_mismatch ниже не выдавало эту сумму
                    # за «план строки» без уточнения, откуда она на самом деле взята.
                    _pq = plan_qty if plan_qty is not None else feo_qty
                    _pa = plan_amt if plan_amt is not None else feo_amt
                    if _pq is not None and _pa is not None:
                        collected_plan[cat.id] = {
                            "qty": _pq,
                            "unit": _pu,
                            "amount": (_pq * _pa).quantize(QUANT),
                            "row": row_num,
                            "name": cat.name,
                            "item_type": item_type,
                            "from_feo_fallback": plan_qty is None and plan_amt is None,
                        }

                if _pu and cat.unit != _pu:
                    cat.unit = _pu

                cats_in_row.append(cat)
                if prev_cat is not None and prev_cat.id is not None:
                    touched_parents.add(prev_cat.id)
                prev_cat = cat

            leaf = cats_in_row[-1]

            # --- Учёт для отчёта "несопоставленные узлы" (только анализ) ---
            root_c = cats_in_row[0]
            if root_c.id is not None:
                seen_roots.add(root_c.id)
            _path_parts: list[str] = []
            for _c in cats_in_row:
                if _c.id is not None:
                    seen_ids.add(_c.id)
                _path_parts.append(_c.name)
                _p = " / ".join(_path_parts)
                if _p not in _new_paths_seen:
                    _new_paths_seen.add(_p)
                    new_paths.append(_p)
                new_path_cats[_p] = _c

            changed = False
            if code is not None and leaf.code != code:
                leaf.code = code; changed = True
            if appendix is not None and leaf.appendix != appendix:
                leaf.appendix = appendix; changed = True
            # budget из легаси-колонки «Финансирование» пишем только если per-level сумма не задана
            if budget is not None:
                # per-level feo_sum уже записан выше; не перезаписываем
                if deduped and deduped[-1].get("feo_sum") is None:
                    if leaf.budget != budget:
                        leaf.budget = budget; changed = True
            if leaf.is_active != is_active:
                leaf.is_active = is_active; changed = True
            if changed and not leaf_is_new:
                updated += 1
                updated_details.append({"row": row_num, "name": leaf.name, "reason": "обновлены поля категории"})

            if lvl5_name and lvl5_name not in ("←", ""):
                from app.models.feo_planned_item import FeoPlannedItem

                # Вычислить итоговую сумму позиции: item_amount приоритетнее
                eff_item_amount = item_amount
                if eff_item_amount is None and item_price is not None:
                    eff_item_qty = item_qty if item_qty is not None else Decimal("1")
                    eff_item_amount = (item_price * eff_item_qty).quantize(QUANT)

                # Категория получила позицию Ур.5 в ЭТОМ импорте — план строки
                # (собранный выше в collected_plan) для неё уже не отдельная
                # позиция, а описание её содержимого; см. блок ниже.
                lvl5_leaves.add(leaf.id)
                lvl5_sum_by_cat[leaf.id] = lvl5_sum_by_cat.get(leaf.id, ZERO) + (eff_item_amount or ZERO)

                existing_item = (await db.execute(
                    select(FeoPlannedItem).where(
                        FeoPlannedItem.feo_category_id == leaf.id,
                        FeoPlannedItem.name == lvl5_name,
                    )
                )).scalar_one_or_none()
                if not existing_item:
                    # item_type (Товар/Услуга/Работа, задача владельца 2026-08-14):
                    # поле добавляется параллельно в модель FeoPlannedItem — hasattr-
                    # проверка, чтобы этот код не падал, пока миграция ещё не применена.
                    _fpi_kwargs = dict(
                        feo_category_id=leaf.id,
                        name=lvl5_name,
                        quantity=item_qty,
                        unit=item_unit,
                        amount=eff_item_amount,
                        is_active=is_active,
                    )
                    if hasattr(FeoPlannedItem, "item_type"):
                        _fpi_kwargs["item_type"] = item_type
                    # Происхождение (владелец, 2026-09-01): эта ветка — детальная
                    # строка Ур.5 из файла ФЭО, жёсткая построчная разбивка есть
                    # по построению (см. докстринг миграции
                    # aa1b2c3d4e5f_feo_planned_item_origin.py) — is_feo_breakdown.
                    if hasattr(FeoPlannedItem, "is_feo_breakdown"):
                        _fpi_kwargs["is_feo_breakdown"] = True
                    pi = FeoPlannedItem(**_fpi_kwargs)
                    db.add(pi)
                    await db.flush()
                    created += 1
                    created_details.append({"row": row_num, "name": lvl5_name, "reason": "плановая позиция (ур. 5)"})
                else:
                    ch2 = False
                    if item_qty is not None and existing_item.quantity != item_qty:
                        existing_item.quantity = item_qty; ch2 = True
                    if item_unit is not None and existing_item.unit != item_unit:
                        existing_item.unit = item_unit; ch2 = True
                    if eff_item_amount is not None and existing_item.amount != eff_item_amount:
                        existing_item.amount = eff_item_amount; ch2 = True
                    if item_type is not None and hasattr(existing_item, "item_type") and existing_item.item_type != item_type:
                        existing_item.item_type = item_type; ch2 = True
                    if ch2:
                        updated += 1
                        updated_details.append({"row": row_num, "name": lvl5_name, "reason": "обновлена позиция"})
                    else:
                        skipped += 1
                        skipped_details.append({"row": row_num, "name": lvl5_name, "reason": "без изменений"})

        except Exception as e:
            errors.append({"row": row_num, "name": lvl2_name, "message": str(e)})

    state.created, state.updated, state.skipped = created, updated, skipped
