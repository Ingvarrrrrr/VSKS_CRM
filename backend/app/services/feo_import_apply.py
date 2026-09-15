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

from app.models.feo_category import FeoCategory
from app.services.feo_import_common import (
    QUANT, ZERO, build_level_name_index, find_uniformly_empty_levels, format_rows, get_cell, level_label,
    resolve_origin_flags, resolve_target_subsidy_id, row_feo_money, row_plan_money, to_bool, to_dec,
)
from app.services.feo_import_common import fmt as _fmt
from app.services.feo_import_common import norm as _norm
from app.services.feo_import_snapshot import full_path
from app.services.feo_import_duplicates import group_key, register_pending_item
from app.services.feo_import_budget_conflicts import apply_budget_conflict_resolutions, register_budget_write
from app.routers.feo_planned_items import normalize_item_type


async def apply_rows(state) -> None:
    db = state.db
    user = state.user
    rows = state.rows
    remap_list = state.remap_list
    sub_rows = state.sub_rows
    sub_by_name = state.sub_by_name
    default_subsidy_id = state.default_subsidy_id
    cat_cache = state.cat_cache
    existing_by_id = state.existing_by_id
    touched_subsidies = state.touched_subsidies
    ignored_subsidy_rows = 0
    ignored_subsidy_names: set[str] = set()
    # Хвост Б (боевой инцидент 2026-09-15, файл «Абхазия ЦЭМАК (1).xlsx»):
    # колонка «Код» в 165 из 189 строк повторяет «Сумму по ФЭО» этой же строки
    # (23970, 4770, 17440…) — брак/сдвиг заполнения файла, не настоящий код.
    # Копится по ходу цикла тем же стилем, что budget_writes/ignored_subsidy_rows
    # (список, агрегируем ПОСЛЕ цикла — только тогда видно, файловый это сигнал
    # или единичное совпадение). code_present_rows — знаменатель для доли
    # совпадений среди строк, где колонка «Код» вообще заполнена.
    code_amount_matches: list[tuple[int, str | None, Decimal]] = []
    code_present_rows = 0

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
    plan_writes = state.plan_writes
    lvl5_item_rows = state.lvl5_item_rows

    created = state.created
    updated = state.updated
    skipped = state.skipped

    _new_paths_seen: set[str] = set()

    def _row_feo_money(row):
        """Обёртка над общим `feo_import_common.row_feo_money` с уже
        известными индексами колонок ЭТОГО импорта (Правило №6 — один
        источник; используется и продвижением «Плановой позиции» в уровень
        ниже, и веткой amount_without_level2)."""
        return row_feo_money(row, c_row_feo_sum, c_feo_sum_lvl2, c_feo_sum_lvl3, c_feo_sum_lvl4, c_budget)

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

    # Пред-проход по ВСЕМ строкам файла (задача владельца 2026-09-09, вторая
    # часть правила «Плановая позиция становится узлом уровня») — ДО основного
    # цикла, см. докстринг build_level_name_index в feo_import_common.py.
    level_name_index = build_level_name_index(rows, c_lvl2, c_lvl3, c_lvl4)

    # Тот же пред-проход (боевой инцидент 2026-09-15, владелец, файл «Абхазия
    # ЦЭМАК (1).xlsx»): колонки уровня, пустые ВО ВСЕХ строках данных файла —
    # это раскладка файла («Уровень 2» здесь не используется вовсе, категории
    # всегда начинаются с «Уровень 3»), а не N отдельных построчных аномалий.
    # Используется ниже, чтобы построчный `level_gap` не плодился на каждую
    # такую строку файла — вместо этого одно агрегированное предупреждение
    # `level_column_empty_in_file` после цикла (см. также блок продвижения
    # «Плановой позиции» — у него своя, независимая от файловой уникальности,
    # защита от разрыва: смотрит только на ЭТУ строку).
    uniformly_empty_levels = find_uniformly_empty_levels(rows, c_lvl2, c_lvl3, c_lvl4)

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
            (c_feo_qty_lvl2, f"Кол-во по ФЭО ({level_label(2)})"),
            (c_feo_amt_lvl2, f"Стоимость по ФЭО ({level_label(2)})"),
            (c_feo_sum_lvl2, f"Сумма по ФЭО ({level_label(2)})"),
            (c_qty_lvl2, f"Плановое кол-во ({level_label(2)})"),
            (c_amt_lvl2, f"Плановая стоимость за ед. ({level_label(2)})"),
            (c_plan_sum_lvl2, f"Сумма плана ({level_label(2)})"),
        ]) or lvl3_name
        lvl4_name = _numeric_shift_scan(row_num, 3, lvl4_name, [
            (c_feo_qty_lvl3, f"Кол-во по ФЭО ({level_label(3)})"),
            (c_feo_amt_lvl3, f"Стоимость по ФЭО ({level_label(3)})"),
            (c_feo_sum_lvl3, f"Сумма по ФЭО ({level_label(3)})"),
            (c_qty_lvl3, f"Плановое кол-во ({level_label(3)})"),
            (c_amt_lvl3, f"Плановая стоимость за ед. ({level_label(3)})"),
            (c_plan_sum_lvl3, f"Сумма плана ({level_label(3)})"),
        ]) or lvl4_name
        lvl5_name = _numeric_shift_scan(row_num, 4, lvl5_name, [
            (c_feo_qty_lvl4, f"Кол-во по ФЭО ({level_label(4)})"),
            (c_feo_amt_lvl4, f"Стоимость по ФЭО ({level_label(4)})"),
            (c_feo_sum_lvl4, f"Сумма по ФЭО ({level_label(4)})"),
            (c_qty_lvl4, f"Плановое кол-во ({level_label(4)})"),
            (c_amt_lvl4, f"Плановая стоимость за ед. ({level_label(4)})"),
            (c_plan_sum_lvl4, f"Сумма плана ({level_label(4)})"),
        ]) or lvl5_name

        # --- Продвижение «Плановой позиции» в уровень (задача владельца
        # 2026-09-09, план dreamy-booping-piglet.md, задача A, п.2) --------------
        # Боевой файл «ЦЕНТРПОИСК...xlsx» не всегда пишет название категории в
        # её «родную» колонку уровня:
        #   (а) строка-заголовок называет направление/категорию ТОЛЬКО в
        #       «Плановой позиции», а сама колонка уровня, которой это имя по
        #       смыслу принадлежит, пуста (строки 2, 3, 9, 24 — «Экипировка» и
        #       три её ребёнка; 33 — «Транспорт и техника» с Ур.2 пустым, Ур.3
        #       заполненным тем же текстом; 251 — «Расходные материалы» с ОБОИМИ
        #       Ур.2/Ур.3 пустыми). Продвигаем имя в БЛИЖАЙШИЙ (не самый
        #       глубокий — иначе ложный level_gap, см. :525 и далее) размеченный
        #       (для которого в файле вообще есть колонка) уровень, который для
        #       ЭТОЙ строки пуст — но ТОЛЬКО когда по строке есть «Сумма по
        #       ФЭО» (_row_feo_money) — без суммы это просто позиция без
        #       уровня, ветка ниже (item_promoted_to_level2) уже её обрабатывает.
        #   (б) строка-заголовок называет направление/категорию И в её родной
        #       колонке уровня, И (тем же текстом) в «Плановой позиции» —
        #       размеченных пустых уровней уже нет (строки 186/187 — «Логистика
        #       и проживание» / «Аренда автотранспортных средств...», 252/257/259
        #       — дети «Расходных материалов»). Это не отдельная позиция, а
        #       итоговая сумма для уже заполненного уровня — «Плановую позицию»
        #       очищаем так же, чтобы её сумма отправилась в cat.budget этого
        #       уровня обычным путём (см. блок «плоские числа», :с _deepest_lv),
        #       а не задвоилась позицией с именем своей же категории.
        # Настоящие позиции (строка 188: «Аренда Хендей ГрандСтарекс» ≠ имя
        # категории) сюда не попадают — их «Сумма по ФЭО» становится суммой
        # ПОЗИЦИИ (см. правку у _deepest_lv в блоке «плоские числа» ниже), а не
        # бюджетом родителя.
        if lvl5_name and not lvl5_name.startswith("←"):
            _level_cols = ((2, c_lvl2), (3, c_lvl3), (4, c_lvl4))
            _level_vals = {2: lvl2_name, 3: lvl3_name, 4: lvl4_name}

            def _is_level_free(lvl: int) -> bool:
                """Уровень СВОБОДЕН для продвижения не только когда буквально
                пуст, но и когда его значение — ДУБЛЬ значения уровня НАД ним
                (задача владельца 2026-09-09, повторный разбор владельца:
                строка 216 — Ур.2=Ур.3=«Организация питания» — после
                нормализации совпадают, значит при схлопывании дублей ниже
                («Схлопываем соседние дубли») всё равно получится ОДИН узел —
                Ур.3 фактически лишний текст, а не отдельный узел, и свободен
                под «Питание, в т.ч. закупка продуктов...». Тот же случай —
                строка 31/29 внутри «Медицинское оснащение...», где Ур.2=Ур.3.
                У Уровня 2 нет уровня над ним — для него дубль невозможен,
                свобода только через буквальную пустоту."""
                if not _level_vals[lvl]:
                    return True
                if lvl == 2:
                    return False
                _shallower = 2 if lvl == 3 else 3
                _shallower_val = _level_vals.get(_shallower)
                return bool(_shallower_val) and _norm(_shallower_val) == _norm(_level_vals[lvl])

            _target_level = next(
                (lvl for lvl, col in _level_cols if col is not None and _is_level_free(lvl)),
                None,
            )
            if _target_level is not None and any(
                _level_vals.get(_deeper_lvl) and not _level_vals[_deeper_lvl].startswith("←")
                for _deeper_lvl, _deeper_col in _level_cols
                if _deeper_col is not None and _deeper_lvl > _target_level
            ):
                # Боевой инцидент 2026-09-15 (владелец, файл «Абхазия ЦЭМАК
                # (1).xlsx»): ближайший ПУСТОЙ уровень — не всегда свободное
                # место для позиции. Если ГЛУБЖЕ него в этой же строке стоят
                # заполненные уровни (здесь Ур.2 пуст, а Ур.3 «Оборудование и
                # снаряжение» / Ур.4 «Альпинистское снаряжение» и т.п.
                # заполнены КАЖДОЙ из 189 строк), пустой уровень — это РАЗРЫВ
                # в цепочке категорий (файл просто не использует Ур.2 вовсе),
                # а не отсутствие категории для этой позиции. Слова владельца:
                # «перед ними заполнены категории, максимум что должно было
                # произойти — это всё вместе сместиться». Продвигать сюда имя
                # позиции нельзя — иначе 744 подраздела вместо 189 позиций, и
                # дубли (feo_import_duplicates.py: «объединить»/«оставить как
                # есть») до них не доходят, потому что они уже не позиции.
                # Правильное поведение — вообще НЕ продвигать здесь: категории
                # (Ур.3/Ур.4) поджимаются вверх обычным дедупом ниже
                # («Схлопываем соседние дубли» / level_gap), а «Плановая
                # позиция» остаётся позицией под самым глубоким уровнем.
                # Старый файл ЦЕНТРПОИСК (ради которого писалось продвижение)
                # эту ветку почти не задевает: там за пустым уровнем ничего
                # глубже не заполнено (строки 2/3/9/24/251 — Ур.3/Ур.4 у них
                # тоже пусты). Исключение — строка 33 (тест
                # test_row33_style_missing_level2_creates_category_not_dropped):
                # Ур.3 занят тем же именем, что и «Плановая позиция» — раньше
                # продвигалось на Ур.2, теперь эта ветка отключает продвижение
                # и код уходит в ветку «строка-итог для самого глубокого
                # уровня» (см. else ниже) — тот же результат: 1 узел, бюджет
                # цел, просто через другой путь.
                _target_level = None
            if _target_level is not None:
                _promo_money = _row_feo_money(row)
                if _promo_money is not None:
                    _old_val = _level_vals[_target_level]  # непустое ⇒ был дубль уровня над ним
                    if _target_level == 2:
                        lvl2_name = lvl5_name
                    elif _target_level == 3:
                        lvl3_name = lvl5_name
                    else:
                        lvl4_name = lvl5_name
                    if _old_val:
                        # Занятый уровень (дубль уровня над ним) — но если то же
                        # имя ГДЕ-ТО в файле само встречается как значение уровня
                        # (level_name_index — пред-проход строки 266, тот же
                        # индекс, что и у item_name_used_as_level ниже), простое
                        # «дублирует и свободен» вводит в заблуждение: возможно,
                        # это настоящий подраздел, а не позиция — предупреждаем
                        # отдельным kind, требующим ручной проверки (задача
                        # владельца 2026-09-09, третья часть правила).
                        # Самообъявление (боевой файл, строка 186: Ур.2=Ур.3=
                        # «Логистика и проживание»=Плановая позиция, все три —
                        # ОДНО имя) — строка-итог раздела, а не человеческий
                        # фактор: остальные вхождения этого же имени как
                        # значения уровня (187–214) — это её СОБСТВЕННЫЙ
                        # раздел, разбирать нечего. Проверяем ДО вычисления
                        # _occ, аналог _is_self_declared в блоке
                        # item_name_used_as_level ниже (не то же место — тот
                        # блок не трогаем).
                        _shallower_lvl = 2 if _target_level == 3 else 3
                        _is_self_declared = _norm(_old_val) == _norm(lvl5_name)
                        _occ = [] if _is_self_declared else [
                            (_lvl, _r) for _lvl, _r in level_name_index.get(_norm(lvl5_name), [])
                            if _r != row_num
                        ]
                        if _occ:
                            _kind = "item_promoted_needs_review"
                            _occ_rows = sorted({_r for _lvl, _r in _occ})
                            _occ_levels = sorted({_lvl for _lvl, _r in _occ})
                            _occ_levels_text = ", ".join(level_label(_lvl) for _lvl in _occ_levels)
                            _msg = (
                                f"Плановая позиция «{lvl5_name}»: {format_rows(_occ_rows)} — "
                                f"это же название стоит как {_occ_levels_text}. "
                                f"{level_label(_target_level)} этой строки дублировал "
                                f"{level_label(_shallower_lvl)} («{_old_val}»), поэтому название "
                                f"поставлено {level_label(_target_level)} и сумма {_fmt(_promo_money)} "
                                f"ушла в него. Проверьте вручную: это подраздел или всё-таки позиция."
                            )
                        else:
                            _kind = "item_promoted_to_level"
                            _msg = (
                                f"Плановая позиция «{lvl5_name}» — {level_label(_target_level)} "
                                f"дублирует {level_label(_shallower_lvl)} («{_old_val}») и фактически "
                                f"свободен: название стало {level_label(_target_level)}"
                            )
                    else:
                        # Пустой уровень алертов не даёт (явное решение
                        # владельца, задача 2026-09-09) — occurrences не считаем.
                        _kind = "item_promoted_to_level"
                        _msg = (
                            f"Плановая позиция «{lvl5_name}» — по строке указана Сумма по ФЭО "
                            f"{_fmt(_promo_money)}, но {level_label(_target_level)} не заполнен: "
                            f"название стало {level_label(_target_level)}"
                        )
                    warnings.append({
                        "kind": _kind,
                        "row": row_num,
                        "name": lvl5_name,
                        "message": _msg,
                    })
                    lvl5_name = None
            else:
                # Все размеченные уровни уже заняты СВОИМИ именами — «Плановая
                # позиция» с тем же именем, что и самый глубокий из них, не
                # отдельная позиция, а строка-итог для него.
                _deepest_level = max(
                    (lvl for lvl, col in _level_cols if col is not None and _level_vals[lvl]),
                    default=None,
                )
                if _deepest_level is not None and _norm(_level_vals[_deepest_level]) == _norm(lvl5_name):
                    lvl5_name = None

        # --- Предупреждение: «Плановая позиция» остаётся ПОЗИЦИЕЙ, но её имя
        # ГДЕ-ТО в файле встречается как значение колонки уровня (задача
        # владельца 2026-09-09, повторный разбор — решение владельца: файл
        # читаем БУКВАЛЬНО, дерево/суммы НЕ меняем; расхождение — человеческий
        # фактор заполнения файла, который нужно ПОКАЗАТЬ, а не решать за
        # пользователя). level_name_index — пред-проход выше (build_level_name_
        # index в feo_import_common.py). Боевой пример: строка 211 (Ур2=
        # «Логистика и проживание», Ур3=«Межрегиональные перевозки», Плановая
        # позиция=«Обеспечение топливом...», Сумма по ФЭО=200 000) — Ур.3 этой
        # строки остаётся «Межрегиональные перевозки» как и было (позиция
        # внутри них, сумма входит в их расшифровку), но то же имя «Обеспечение
        # топливом...» стоит как Уровень 3 в строке 212 — стоит предупредить,
        # это подраздел или позиция. Настоящие расшифровки без такого
        # совпадения (строка 188: «Аренда Хендей ГрандСтарекс» нигде не
        # встречается как уровень) предупреждения не получают.
        #
        # ТРЕТИЙ разбор владельца (2026-09-09): требование «есть Сумма по
        # ФЭО» скрывало настоящий дефект дальше по тому же боевому файлу —
        # строка 214 (Ур.3=«Обеспечение топливом...», Плановая позиция=
        # «Хозяйственные, административные расходы...», ПЛАН 200 000, Суммы
        # по ФЭО у строки нет вовсе) — тот же человеческий фактор (это же имя
        # объявлено Уровнем 3 строкой раньше, 213, а тут забыли поправить
        # Уровень 3 этой строки), но предупреждение молчало, потому что
        # смотрело только на _row_feo_money. Условие теперь — ровно три пункта
        # из требования владельца: (1) позиция осталась позицией — раз мы
        # здесь, значит да; (2) имя где-то в файле объявлено значением уровня
        # (_occ_all); (3) имя НЕ совпадает с самым глубоким заполненным
        # уровнем ЭТОЙ строки (не самообъявление — уже гарантировано блоком
        # продвижения выше, но проверяем явно, а не полагаемся на побочный
        # эффект). Деньги по строке для самого условия больше не нужны — если
        # они есть (ФЭО и/или план), называем их в тексте; если нет —
        # называем просто позицию.
        if lvl5_name and not lvl5_name.startswith("←"):
            _cur_deepest_pair = next(
                ((lvl, v) for lvl, v in ((4, lvl4_name), (3, lvl3_name), (2, lvl2_name)) if v),
                None,
            )
            _current_deepest = _cur_deepest_pair[1] if _cur_deepest_pair else None
            _current_deepest_level = _cur_deepest_pair[0] if _cur_deepest_pair else None
            _is_self_declared = bool(_current_deepest) and _norm(_current_deepest) == _norm(lvl5_name)
            _occ_all = [
                (_lvl, _r) for _lvl, _r in level_name_index.get(_norm(lvl5_name), []) if _r != row_num
            ]
            if _occ_all and not _is_self_declared:
                _item_feo_money = _row_feo_money(row)
                _item_plan_money = row_plan_money(
                    row, c_row_plan_sum, c_plan_sum_lvl2, c_plan_sum_lvl3, c_plan_sum_lvl4
                )
                _value_bits: list[tuple[str, str]] = []
                if _item_feo_money is not None:
                    _value_bits.append(("feo", f"Сумма по ФЭО {_fmt(_item_feo_money)}"))
                if _item_plan_money is not None:
                    _value_bits.append(("plan", f"план {_fmt(_item_plan_money)}"))
                if not _value_bits:
                    _value_phrase, _verb = "эта позиция", "учтена"
                elif len(_value_bits) == 1:
                    _kind, _value_phrase = _value_bits[0]
                    _verb = "учтён" if _kind == "plan" else "учтена"
                else:
                    _value_phrase = " и ".join(t for _, t in _value_bits)
                    _verb = "учтены"
                _levels_found = sorted({_lvl for _lvl, _r in _occ_all})
                _levels_text = ", ".join(level_label(_lvl) for _lvl in _levels_found)
                _rows_found = sorted({_r for _lvl, _r in _occ_all})
                _rows_text = format_rows(_rows_found, max_parts=5)
                warnings.append({
                    "kind": "item_name_used_as_level",
                    "row": row_num,
                    "name": lvl5_name,
                    "message": (
                        f"Строка {row_num}: «{lvl5_name}» объявлена как {_levels_text} "
                        f"({_rows_text}), но здесь записана позицией внутри «{_current_deepest}» — "
                        f"{_value_phrase} {_verb} не в том подразделе; проверьте "
                        f"{level_label(_current_deepest_level)} этой строки"
                    ),
                })

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
                    "message": f"Плановая позиция «{lvl5_name}» — в строке нет ни одного уровня, создана направлением ({level_label(2)})",
                })
                lvl2_name = lvl5_name
                lvl5_name = None

        if not (lvl2_name or lvl3_name or lvl4_name):
            # Правило владельца 2026-09-09/2026-09-15: пропускаем строку
            # целиком ТОЛЬКО когда ВООБЩЕ ни одного уровня не заполнено — до
            # 2026-09-15 здесь стояла проверка одного lvl2_name, из-за которой
            # боевой файл «Абхазия ЦЭМАК (1).xlsx» (Ур.2 пуст ВО ВСЕХ строках,
            # Ур.3/Ур.4 заполнены) полностью пропускал бы каждую строку заново
            # после того, как продвижение (блок выше) перестало заполнять
            # lvl2_name суммой при разрыве — раньше промоушен «на Ур.2» решал
            # это побочно, теперь разрыв поджимается обычным дедупом ниже
            # (Ур.3→level1, Ур.4→level2), и категория обязана строиться из
            # lvl3_name/lvl4_name, а не только из lvl2_name. Строка 33 боевого
            # файла ЦЕНТРПОИСК — тот же случай: Ур.3 заполнен, Ур.2 нет.
            # Ищем деньги в ЛЮБОЙ из колонок, которые могли бы их нести
            # (плоская «Сумма по ФЭО» и её per-level варианты + легаси
            # «Финансирование») — если что-то есть, называем сумму прямо,
            # а не сваливаем строку в общее "(пустая строка) — нет наименования".
            _money_hint = _row_feo_money(row)
            if _money_hint is not None:
                warnings.append({
                    "kind": "amount_without_level2",
                    "row": row_num,
                    "name": None,
                    "message": (
                        f"Строка {row_num}: указана Сумма по ФЭО {_fmt(_money_hint)}, но не заполнен "
                        f"{level_label(2)} — строка пропущена, сумма НЕ учтена"
                    ),
                })
            skipped += 1
            skipped_details.append({
                "row": row_num,
                "name": lvl2_name or "(пустая строка)",
                "reason": (
                    "нет наименования (уровень 2 пуст)" if _money_hint is None else
                    f"указана Сумма по ФЭО {_fmt(_money_hint)}, но не заполнен {level_label(2)} — сумма НЕ учтена"
                ),
            })
            continue

        sub_name = get_cell(row, c_subsidy) if c_subsidy is not None else None
        subsidy_id = resolve_target_subsidy_id(sub_name, sub_by_name, default_subsidy_id)
        if default_subsidy_id:
            # Открытая субсидия (карточка, из которой запущен импорт) побеждает
            # БЕЗУСЛОВНО — баг 2026-09-09: шаблон, заполненный под другую
            # субсидию, не должен перебивать субсидию назначения. Колонка
            # «Субсидия» файла здесь НЕ маршрутизирует — если она называет
            # ДРУГУЮ существующую субсидию, копим для одного агрегированного
            # предупреждения после цикла (не молча, но и не на каждую строку).
            if sub_name and not sub_name.startswith("←"):
                _named_sid = sub_by_name.get(sub_name.lower().strip())
                if _named_sid and _named_sid != default_subsidy_id:
                    ignored_subsidy_rows += 1
                    ignored_subsidy_names.add(sub_name.strip())
        else:
            # Мультисубсидийный режим (default_subsidy_id не передан — сегодня
            # только самостоятельная страница FeoCategoriesView.vue, без
            # карточки субсидии): колонка «Субсидия» файла — единственный
            # источник маршрутизации, поведение прежнее.
            if sub_name and not sub_name.startswith("←"):
                if not subsidy_id:
                    errors.append({"row": row_num, "name": lvl2_name, "message": f"Субсидия не найдена: '{sub_name}'"})
                    continue
            else:
                if not subsidy_id:
                    skipped += 1
                    skipped_details.append({"row": row_num, "name": lvl2_name, "reason": "не указана субсидия назначения"})
                    continue

        code      = get_cell(row, c_code)
        if code is not None:
            code_present_rows += 1
            _code_dec = to_dec(code)
            if _code_dec is not None:
                _code_row_money = _row_feo_money(row)
                if _code_row_money is not None and _code_dec == _code_row_money:
                    # Брак/сдвиг заполнения файла (см. code_amount_matches
                    # выше) — «Код» этой строки на самом деле «Сумма по ФЭО»,
                    # случайно продублированная в соседнюю колонку. Не пишем
                    # её в leaf.code (категория получила бы «код» вида
                    # «23970», а предпросмотр — ложное «обновлено»). Само
                    # предупреждение (файловое или построчное) собирается
                    # после цикла по всем строкам — см. code_column_holds_amounts.
                    code_amount_matches.append((row_num, lvl5_name or lvl4_name or lvl3_name or lvl2_name, _code_dec))
                    code = None
        appendix  = get_cell(row, c_appendix)
        budget    = to_dec(get_cell(row, c_budget))
        is_active = to_bool(get_cell(row, c_active))

        item_qty    = to_dec(get_cell(row, c_qty))
        item_unit   = get_cell(row, c_unit)
        item_unit   = _check_unit_shift(
            item_unit, row_num, lvl5_name or lvl4_name or lvl3_name or lvl2_name, f"Ед. изм. ({level_label(5)})"
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

        # Происхождение позиции этой строки (Правило №6, единственный источник —
        # resolve_origin_flags в feo_import_common.py): считаем ОДИН раз на
        # строку, по деньгам, реально найденным в разделе ФЭО/плана ЭТОЙ строки
        # (включая per-level колонки и легаси «Финансирование» — те же наборы
        # колонок, что и у cat.budget/collected_plan ниже). Используется и для
        # позиции Ур.5 (создание/обновление ниже), и передаётся дальше через
        # collected_plan — feo_import_plan.py создаёт позицию из категории без
        # собственного Ур.5 тем же признаком, не пересчитывая его заново.
        _row_is_feo_breakdown, _row_is_internal_plan = resolve_origin_flags(
            row_feo_money(row, c_row_feo_sum, c_feo_sum_lvl2, c_feo_sum_lvl3, c_feo_sum_lvl4, c_budget),
            row_plan_money(row, c_row_plan_sum, c_plan_sum_lvl2, c_plan_sum_lvl3, c_plan_sum_lvl4),
        )

        _deepest_lv = next((lv for lv in reversed(_lv) if lv["name"]), None)

        if any(v is not None for v in (_row_feo_qty, _row_feo_unit, _row_feo_price)):
            if lvl5_name and not lvl5_name.startswith("←"):
                # Боевой инцидент 2026-09-15 (владелец, файл «Абхазия ЦЭМАК
                # (1).xlsx»): КАЖДАЯ строка категории «Альпинистское
                # снаряжение» (строки 2–26) несёт свою «Плановую позицию» —
                # кол-во/ед./цена по ФЭО этой строки принадлежат ЭТОЙ позиции,
                # а не глубокому уровню категории. Раньше они безусловно
                # уходили в _deepest_lv["feo_*"], и ПЕРВАЯ строка категории
                # "заражала" уровень фантомным планом (см. ветку «Старое
                # поведение источника данных» ниже, from_feo_fallback), хотя у
                # категории вообще нет собственного плана — только сумма её
                # позиций. Этот фантомный план потом сравнивался с суммой ВСЕХ
                # 25 позиций категории и давал ложный plan_vs_items_mismatch.
                # Приоритет как у остальных row-flat полей (см. row_plan_*
                # ниже) — заполняем item_qty/item_unit/item_price, только
                # если они ещё не заданы отдельными колонками позиции.
                if item_qty is None:
                    item_qty = _row_feo_qty
                if item_unit is None:
                    item_unit = _row_feo_unit
                if item_price is None:
                    item_price = _row_feo_price
            elif _deepest_lv is not None:
                # Строка-категория БЕЗ позиции (файл ЦЕНТРПОИСК, строки-
                # заголовки без «Плановой позиции») — поведение прежнее:
                # кол-во/ед./цена по ФЭО безусловно к самому глубокому
                # заполненному УРОВНЮ. Их единственный потребитель — фолбэк
                # «план категории = feo_qty × feo_amt», когда у категории нет
                # собственных плановых колонок (см. ветку ниже, «Старое
                # поведение источника данных»).
                if _deepest_lv["feo_qty"] is None:
                    _deepest_lv["feo_qty"] = _row_feo_qty
                if _deepest_lv["feo_unit"] is None:
                    _deepest_lv["feo_unit"] = _row_feo_unit
                if _deepest_lv["feo_amt"] is None:
                    _deepest_lv["feo_amt"] = _row_feo_price

        if _row_feo_sum is not None:
            if lvl5_name and not lvl5_name.startswith("←"):
                # Задача владельца 2026-09-09 (боевой файл, строка 188: «Аренда
                # Хендей ГрандСтарекс» под уже занятой категорией «Аренда
                # автотранспортных средств...», у которой своя Сумма по ФЭО уже
                # задана отдельной строкой-заголовком, 500 000). «Плановая
                # позиция» на этом этапе (после блока продвижения выше) заполнена
                # ТОЛЬКО у настоящих позиций — категория-заголовок или строка
                # без уровня уже очистили lvl5_name. Раз это настоящая позиция,
                # «Сумма по ФЭО» строки — её СОБСТВЕННАЯ сумма (жёсткая
                # расшифровка внутри родителя, происхождение позиции считается
                # по _row_is_feo_breakdown/_row_is_internal_plan выше — реальным
                # деньгам строки, а не безусловно), а не бюджет родителя: раньше
                # она безусловно уходила в cat.budget и затирала итог, заданный
                # строкой-заголовком категории.
                if item_amount is None:
                    item_amount = _row_feo_sum
            elif _deepest_lv is not None and _deepest_lv["feo_sum"] is None:
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
                    "message": f"{level_label(lv['level_src'])} и {level_label(deduped[-1]['level_src'])} названы одинаково — склеены в один узел",
                })
                # Числа объединяем с приоритетом нижнего непустого
                prev = deduped[-1]
                for k in ("feo_qty", "feo_unit", "feo_amt", "feo_sum", "plan_qty", "plan_unit", "plan_amt", "plan_sum"):
                    if lv[k] is not None:
                        prev[k] = lv[k]
            else:
                # Проверяем пропуск уровня: если предыдущий src=2 а текущий src=4 — Ур.3 был пропущен
                if deduped and lv["level_src"] - deduped[-1]["level_src"] > 1:
                    _gap_levels = set(range(deduped[-1]["level_src"] + 1, lv["level_src"]))
                    # Боевой инцидент 2026-09-15: если ВСЕ промежуточные уровни
                    # этого разрыва пусты ВО ВСЕХ строках файла (раскладка
                    # файла — см. find_uniformly_empty_levels), это не 189
                    # отдельных построчных аномалий, а одно свойство файла —
                    # предупреждаем один раз после цикла (level_column_empty_
                    # in_file), построчный level_gap здесь не плодим. Если хотя
                    # бы один из промежуточных уровней где-то в файле всё же
                    # заполнен (разрыв — исключение, а не правило), построчное
                    # предупреждение остаётся как было.
                    if not _gap_levels <= uniformly_empty_levels:
                        warnings.append({
                            "kind": "level_gap",
                            "row": row_num,
                            "name": lv["name"],
                            "message": f"{level_label(lv['level_src'])} поднят на место {level_label(deduped[-1]['level_src'] + 1)} — промежуточный уровень не заполнен",
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
                    label = {
                        1: f"направление ({level_label(2)})",
                        2: f"категория ({level_label(3)})",
                        3: f"статья ({level_label(4)})",
                    }.get(db_level, f"уровень {db_level + 1}")
                    created_details.append({"row": row_num, "name": lv["name"], "reason": label})

                # --- ФЭО-поля ---
                feo_qty  = lv["feo_qty"]
                feo_unit = lv["feo_unit"]
                feo_unit = _check_unit_shift(
                    feo_unit, row_num, lv["name"], f"Ед. изм. по ФЭО ({level_label(lv['level_src'])})"
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
                    # Задача владельца 2026-09-09: каждая строка, задавшая Сумму
                    # по ФЭО ЭТОГО узла — не только последняя, что реально
                    # победила (cat.budget). Несколько строк на один и тот же
                    # узел — обычное дело для «строк-подытогов» без Уровня 3
                    # (боевой пример: «Экипировка», строки 2/3/9/24) — раньше
                    # это было видно только косвенно, через parent_sum_mismatch
                    # без единого номера строки. Копим ВСЕ попытки (не только
                    # изменившие значение) — задача владельца 2026-09-15: если
                    # среди них окажутся РАЗНЫЕ значения, apply_budget_conflict_
                    # resolutions (после цикла) спросит решение человека вместо
                    # молчаливого «последняя побеждает».
                    register_budget_write(
                        state, cat, subsidy_id, [c.name for c in cats_in_row] + [cat.name],
                        row_num, feo_sum, lv["name"],
                    )
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
                    plan_unit, row_num, lv["name"], f"Ед. изм. плана ({level_label(lv['level_src'])})"
                )
                plan_amt  = lv["plan_amt"]
                plan_sum  = lv["plan_sum"]

                _pu = plan_unit if plan_unit is not None else feo_unit

                # Задача владельца 2026-09-09 (боевой файл, строки 239, 242-244,
                # 246-248): строка без единого содержательного значения — нет ни
                # «Плановой позиции»/«Товар-услуга», ни чисел по ФЭО, ни ненулевых
                # цены/суммы плана — но «Плановое количество» технически заполнено
                # (100 или скопированная 1). Раньше такая строка всё равно
                # перезаписывала collected_plan этой категории суммой 0 (условие
                # zero_plan_skipped требует qty ТОЖЕ 0/пусто, а тут qty≠0) —
                # последняя из таких пустых строк "побеждала" в
                # plan_vs_items_mismatch, выглядя как «план строки = 0» для
                # категории, у которой реальный план — только сумма её
                # собственных строк «Товар/услуга». Полностью пустую строку не
                # считаем планом строки вообще — ни в плюс, ни в ноль.
                _row_has_any_content = bool(
                    (lvl5_name and lvl5_name not in ("←", ""))
                    or item_qty is not None or item_price is not None or item_amount is not None
                    or feo_qty is not None or feo_amt is not None or feo_sum is not None
                    or (plan_amt is not None and plan_amt != ZERO)
                    or (plan_sum is not None and plan_sum != ZERO)
                )
                # Условие сужено до plan_qty≠0/None намеренно: строка с
                # plan_sum=0 И plan_qty пустым/нулевым — это УЖЕ существующий
                # (более ранний) сценарий zero_plan_skipped ниже, менять его не
                # нужно. Отличие боевого дефекта — именно НЕНУЛЕВОЕ "Плановое
                # количество" (технический дубль/копипаста), при котором
                # старое условие zero_plan_skipped не срабатывало вообще.
                if not _row_has_any_content and plan_qty is not None and plan_qty != ZERO:
                    skipped += 1
                    skipped_details.append({
                        "row": row_num,
                        "name": lv["name"],
                        "reason": "нет ни плановой позиции, ни товара/услуги, суммы нулевые — строка пропущена",
                    })
                elif plan_sum is not None and plan_sum == ZERO and (plan_qty is None or plan_qty == ZERO):
                    # Сумма плана прямо равна нулю (не пуста!) и кол-во не задано —
                    # раньше здесь всё равно подставлялось qty=1, что превращало
                    # "плана нет" в "план = 0 шт. по цене 0" (видимую, но ложную
                    # плановую позицию). Ноль — это значение, а не "поле не
                    # заполнено": плановая позиция по строке не создаётся вовсе,
                    # категория при этом продолжает создаваться/читаться как обычно
                    # (см. дальше по циклу — этот блок только про collected_plan).
                    warnings.append({
                        "kind": "zero_plan_skipped",
                        "row": row_num,
                        "name": lv["name"],
                        "message": "Сумма плана 0 — плановая позиция не создана",
                    })
                elif plan_sum is not None:
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
                        # Происхождение (Правило №6) — посчитано один раз выше по
                        # РЕАЛЬНЫМ деньгам этой строки, feo_import_plan.py читает
                        # готовое значение, а не пересчитывает.
                        "is_feo_breakdown": _row_is_feo_breakdown,
                        "is_internal_plan": _row_is_internal_plan,
                    }
                    plan_writes.setdefault(cat.id, []).append(row_num)
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
                            "is_feo_breakdown": _row_is_feo_breakdown,
                            "is_internal_plan": _row_is_internal_plan,
                        }
                        plan_writes.setdefault(cat.id, []).append(row_num)

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
                    register_budget_write(
                        state, leaf, subsidy_id, [c.name for c in cats_in_row],
                        row_num, budget, leaf.name,
                    )
            if leaf.is_active != is_active:
                leaf.is_active = is_active; changed = True
            if changed and not leaf_is_new:
                updated += 1
                updated_details.append({"row": row_num, "name": leaf.name, "reason": "обновлены поля категории"})

            if lvl5_name and lvl5_name not in ("←", ""):
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
                lvl5_item_rows.setdefault(leaf.id, []).append(row_num)

                # Волна 4, п.23 (владелец): «5 строк с именем «чайник» — не
                # ставить одну позицию с ценой последней строки, а предложить
                # человеку решение — оставить как есть или объединить». Строка
                # больше НЕ создаёт/обновляет FeoPlannedItem немедленно — она
                # копится по ключу группы (полное совпадение имени ПОСЛЕ
                # нормализации, см. group_key в feo_import_duplicates.py) и
                # разбирается ПОСЛЕ основного цикла по всем строкам файла
                # (finalize_lvl5_items, feo_import_core.py) — только тогда
                # известно, сколько строк реально попало в одну группу, и есть
                # решение человека (state.duplicate_resolutions) по этой
                # конкретной группе.
                _dup_key = group_key(subsidy_id, [c.name for c in cats_in_row], lvl5_name)
                register_pending_item(state, _dup_key, leaf, {
                    "row": row_num,
                    "name": lvl5_name,
                    "qty": item_qty,
                    "unit": item_unit,
                    "amount": eff_item_amount,
                    "item_type": item_type,
                    "is_active": is_active,
                    "is_feo_breakdown": _row_is_feo_breakdown,
                    "is_internal_plan": _row_is_internal_plan,
                    "path": [c.name for c in cats_in_row],
                })

        except Exception as e:
            errors.append({"row": row_num, "name": lvl2_name, "message": str(e)})

    # Один файл-уровневый сигнал вместо N одинаковых построчных (боевой
    # инцидент 2026-09-15, файл «Абхазия ЦЭМАК (1).xlsx»): колонка уровня,
    # пустая ВО ВСЕХ строках данных — раскладка файла, а не аномалия каждой
    # строки. Построчные level_gap для разрывов, вызванных именно такой
    # колонкой, уже подавлены выше (см. uniformly_empty_levels) — здесь
    # единственное упоминание об этом на весь импорт.
    if uniformly_empty_levels:
        _existing_levels = sorted(
            lvl for lvl, col in ((2, c_lvl2), (3, c_lvl3), (4, c_lvl4)) if col is not None
        )
        for _empty_lvl in sorted(uniformly_empty_levels):
            _deeper = [
                lvl for lvl in _existing_levels
                if lvl > _empty_lvl and lvl not in uniformly_empty_levels
            ]
            if not _deeper:
                continue
            _landed = {lvl: lvl - sum(1 for e in uniformly_empty_levels if e < lvl) for lvl in _deeper}
            _from_text = " и ".join(level_label(lvl) for lvl in _deeper)
            _to_text = " и ".join(level_label(_landed[lvl]) for lvl in _deeper)
            _verb = "поднят" if len(_deeper) == 1 else "подняты"
            warnings.append({
                "kind": "level_column_empty_in_file",
                "row": None,
                "name": None,
                "message": (
                    f"Колонка «{level_label(_empty_lvl)}» пуста во всём файле — "
                    f"{_from_text} {_verb} на место {_to_text}"
                ),
            })

    # Хвост Б (боевой инцидент 2026-09-15, файл «Абхазия ЦЭМАК (1).xlsx»):
    # агрегирование code_amount_matches, накопленных по ходу цикла выше. 1–2
    # совпадения — построчный column_shift, тем же kind'ом и стилем, что и
    # `_check_unit_shift` для единиц измерения (не отдельный механизм).
    # ≥3 строк ИЛИ ≥20% строк с заполненным «Кодом» — один файловый сигнал
    # `code_column_holds_amounts` (иначе на боевом файле было бы 165
    # одинаковых построчных предупреждений — тот же принцип, что и у
    # level_column_empty_in_file выше). Доля считается ТОЛЬКО при разумном
    # размере выборки (от 5 строк с «Кодом») — иначе единственная строка файла
    # с совпадением даёт 100% и ложно выглядит как «раскладка файла», хотя это
    # ровно тот самый одиночный случай, который должен остаться column_shift.
    _CODE_SHARE_MIN_ROWS = 5
    if code_amount_matches:
        _code_match_rows = [r for r, _n, _v in code_amount_matches]
        _code_match_count = len(code_amount_matches)
        _code_share = _code_match_count / code_present_rows if code_present_rows else 0
        if _code_match_count >= 3 or (code_present_rows >= _CODE_SHARE_MIN_ROWS and _code_share >= 0.2):
            warnings.append({
                "kind": "code_column_holds_amounts",
                "row": None,
                "name": None,
                "message": (
                    f"Колонка «Код» в {_code_match_count} строках повторяет «Сумму по ФЭО» "
                    f"({format_rows(_code_match_rows)}) — похоже на сдвиг колонок; код категорий "
                    f"из этих строк не записан"
                ),
            })
        else:
            for _r, _n, _v in code_amount_matches:
                warnings.append({
                    "kind": "column_shift",
                    "row": _r,
                    "name": _n or "",
                    "message": (
                        f"Строка {_r}: в колонке «Код» число {_fmt(_v)} совпадает с «Суммой по ФЭО» "
                        f"этой строки — похоже, колонки сдвинуты, код не записан"
                    ),
                })

    if ignored_subsidy_rows:
        _target_name = next((s.name for s in sub_rows if s.id == default_subsidy_id), None) or f"#{default_subsidy_id}"
        _ignored_names_str = "«" + "», «".join(sorted(ignored_subsidy_names)) + "»"
        warnings.append({
            "kind": "subsidy_name_ignored",
            "row": None,
            "name": None,
            "message": (
                f"В файле указана субсидия {_ignored_names_str}, импорт идёт в открытую "
                f"«{_target_name}» — строки будут созданы в ней (затронуто строк: {ignored_subsidy_rows})"
            ),
        })

    # Задача владельца 2026-09-09: узел, чью Сумму по ФЭО задавали НЕСКОЛЬКО
    # строк файла (боевой пример: «Экипировка» — строки 2/3/9/24) — БЕЗ
    # предупреждения не видно, что она вообще перезаписывалась, и уж тем более
    # какие строки/суммы проиграли. Задача владельца 2026-09-15 (опрос): если
    # среди этих строк есть РАЗНЫЕ значения — это уже не просто уведомление,
    # решение принимает человек по каждой такой категории отдельно (см.
    # feo_import_budget_conflicts.py); одинаковые повторы одного и того же
    # числа по-прежнему остаются без группы и без предупреждения — там нечего
    # выбирать.
    apply_budget_conflict_resolutions(state)

    state.created, state.updated, state.skipped = created, updated, skipped
