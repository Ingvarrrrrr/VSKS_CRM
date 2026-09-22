"""Иерархия ФЭО по явной нумерации строк файла (колонки A–D) — приоритетный
источник дерева категорий, когда они замаплены (решение владельца, 22.09,
боевой случай субсидия ДНР_2026: файл, где F/G/H "Уровень 2/3/4" не следуют
одному подряд идущему столбцу — Ур.2 одной строки может оказаться "Ур.3" по
смыслу для другой, а строка без единого уровня, но с позицией, раньше
становилась ложным новым корнем, см. feo_import_apply.py::item_attached_to_
previous_node — та же беда, но БЕЗ нумерации).

Разрезано отдельным модулем от feo_import_apply.py (Правило №5 — тот файл и
так под 1400 строк). Вызывается ВМЕСТО `apply_rows` из feo_import_core.py,
когда обнаружены минимум 2 ведущие числовые колонки (см.
routers/feo_import.py::_detect_numbering_columns) — весь остальной пайплайн
(finalize_lvl5_items/apply_collected_plan/build_unmatched_report/remap_and_
prune) общий для обоих путей, читает те же поля `state` (collected_plan,
pending_lvl5_items, cat_cache, warnings, ...), которые заполняет и обычный
apply_rows.

Путь строки — непустой ПРЕФИКС значений колонок нумерации (num1, [num2,
[num3, [num4]]]): первая пустая или нецелая ячейка обрывает путь (см.
`_row_number_path`). Путь P — прямой родитель строк с путём P + (x,); если
такой строки-предка нет (пропущен промежуточный уровень), родителем
становится БЛИЖАЙШИЙ по убыванию длины путь, который уже стал узлом —
устойчиво к дыркам в нумерации.

Строка-УЗЕЛ (есть хотя бы одна другая строка файла с путём глубже её
собственного, начинающимся с её пути) становится FeoCategory; своей плановой
позиции не получает — её сумма (колонка "Сумма по ФЭО", иначе колонка "Сумма
плана" с warning `group_total_row` — тот же термин, что и у одноимённого
предупреждения без нумерации, feo_import_apply.py, Правило №6: одно явление —
одно имя) идёт в cat.budget так же, как это делает построчная категория без
нумерации.

Строка-ЛИСТ (нет строк файла глубже неё по пути) НЕ создаёт свою категорию —
становится ПОЗИЦИЕЙ (`FeoPlannedItem`) ближайшего узла-предка по нумерации,
тем же каналом `pending_lvl5_items`/`register_pending_item`/
`finalize_lvl5_items` (feo_import_duplicates.py), что и построчная «Плановая
позиция» без нумерации — Правило №6, не заводить второй механизм создания
позиций. Имя листа-позиции — колонка "Плановая позиция"; если она пуста —
имя уровня строки (последний непустой из Уровень2/3/4).

Если у ЛИСТА имя уровня (Уровень2/3/4 этой же строки) заполнено и после
нормализации отличается от имени узла-предка, которому её приписала нумерация
— строки, где это произошло, собираются в предупреждение `numbering_vs_levels`
(нумерация ВСЕГДА побеждает — узел строится по ней, а не по имени уровня;
расхождение только показывается человеку, дерево не меняется по нему)."""
from decimal import Decimal

from app.models.feo_category import FeoCategory
from app.services.feo_import_budget_conflicts import (
    apply_budget_conflict_resolutions,
    apply_category_sum_conflicts,
    register_budget_write,
)
from app.services.feo_import_common import (
    QUANT, ZERO, find_or_create_category, format_rows, get_cell, resolve_origin_flags,
    resolve_target_subsidy_id, row_feo_money, to_dec,
)
from app.services.feo_import_common import fmt as _fmt
from app.services.feo_import_common import norm as _norm
from app.services.feo_import_duplicates import group_key, register_pending_item
from app.services.feo_import_item_types import resolve_item_type_for_row
from app.routers.feo_planned_items import normalize_item_type

ONE = Decimal("1")


def _row_number_path(row, c_num1, c_num2, c_num3, c_num4) -> tuple[int, ...] | None:
    """Непустой префикс колонок нумерации A–D. Колонка, не замапленная в этом
    импорте (None), считается пустой ячейкой КАЖДОЙ строки — путь просто
    короче на этот сегмент, а не обрывается раньше времени."""
    path: list[int] = []
    for col in (c_num1, c_num2, c_num3, c_num4):
        if col is None:
            break
        v = to_dec(get_cell(row, col))
        if v is None or v != v.to_integral_value():
            break
        path.append(int(v))
    return tuple(path) if path else None


def _own_level_name(row, c_lvl2, c_lvl3, c_lvl4) -> str | None:
    """Имя уровня строки — последний непустой из Уровень2/3/4 (тот же приём
    «самый глубокий заполненный уровень», что и `_deepest_lv` в
    feo_import_apply.py, Правило №6 — общий смысл, отдельная маленькая копия
    здесь оправдана тем, что модуль не читает `_lv`-список apply_rows)."""
    for col in (c_lvl4, c_lvl3, c_lvl2):
        if col is None:
            continue
        v = get_cell(row, col)
        if v and not v.startswith("←"):
            return v
    return None


async def apply_rows_numbered(state) -> None:
    db = state.db
    rows = state.rows
    cat_cache = state.cat_cache
    warnings = state.warnings

    c_num1, c_num2, c_num3, c_num4 = state.c_num1, state.c_num2, state.c_num3, state.c_num4
    c_lvl2, c_lvl3, c_lvl4, c_lvl5 = state.c_lvl2, state.c_lvl3, state.c_lvl4, state.c_lvl5
    c_qty, c_unit, c_item_price = state.c_qty, state.c_unit, state.c_item_price
    c_item_type = state.c_item_type
    c_row_feo_sum, c_row_plan_sum = state.c_row_feo_sum, state.c_row_plan_sum
    c_budget = state.c_budget

    async def find_or_create(subsidy_id, parent_id, name: str, level: int):
        # Единственная реализация — feo_import_common.find_or_create_category
        # (Правило №6; общая с feo_import_apply.py).
        return await find_or_create_category(db, cat_cache, subsidy_id, parent_id, name, level)

    # PASS 1: путь каждой строки + множество всех путей (нужно, чтобы понять,
    # У КОГО есть дети по нумерации, ДО того как строки обработаны по порядку —
    # родитель обычно идёт раньше детей в файле, но "есть ли у МЕНЯ дети"
    # знать заранее нельзя без взгляда вперёд).
    row_paths: dict[int, tuple | None] = {}
    for row_num, row in enumerate(rows, start=2):
        row_paths[row_num] = _row_number_path(row, c_num1, c_num2, c_num3, c_num4)
    all_paths = {p for p in row_paths.values() if p}

    def _has_child(path: tuple) -> bool:
        return any(len(q) > len(path) and q[: len(path)] == path for q in all_paths)

    nodes_by_path: dict[tuple, FeoCategory] = {}
    # cat.id -> имена узлов от корня ВКЛЮЧАЯ сам узел (тот же формат, что и
    # `[c.name for c in cats_in_row] + [cat.name]` в feo_import_apply.py) —
    # нужен для register_budget_write/group_key без похода по parent_id.
    node_path_names: dict[int, list] = {}
    _mismatch_groups: dict[tuple, list] = {}

    def _find_ancestor(path: tuple):
        """Ближайший УЖЕ СОЗДАННЫЙ узел, чей путь — префикс `path` (устойчиво
        к пропущенным промежуточным уровням нумерации)."""
        for cut in range(len(path) - 1, 0, -1):
            node = nodes_by_path.get(path[:cut])
            if node is not None:
                return node
        return None

    for row_num, row in enumerate(rows, start=2):
        path = row_paths[row_num]
        if path is None:
            continue

        sub_name = get_cell(row, state.c_subsidy) if state.c_subsidy is not None else None
        subsidy_id = resolve_target_subsidy_id(sub_name, state.sub_by_name, state.default_subsidy_id)
        if not subsidy_id:
            state.skipped += 1
            state.skipped_details.append({"row": row_num, "name": None, "reason": "не указана субсидия назначения"})
            continue

        own_level_name = _own_level_name(row, c_lvl2, c_lvl3, c_lvl4)
        item_name_cell = get_cell(row, c_lvl5)
        ancestor = _find_ancestor(path)
        path_str = ".".join(map(str, path))

        if _has_child(path):
            # --- УЗЕЛ: есть строки-дети по нумерации → FeoCategory, позиция
            # для НЕГО САМОГО не создаётся (см. докстринг модуля, п.1). ---
            name = own_level_name or item_name_cell
            if not name:
                state.skipped += 1
                state.skipped_details.append({
                    "row": row_num, "name": None,
                    "reason": f"узел по нумерации {path_str} без имени — строка пропущена",
                })
                continue
            parent_id = ancestor.id if ancestor else None
            cat, is_new = await find_or_create(subsidy_id, parent_id, name, len(path))
            nodes_by_path[path] = cat
            node_path_names[cat.id] = (node_path_names.get(ancestor.id, []) if ancestor else []) + [name]
            if is_new:
                state.created += 1
                state.created_details.append({
                    "row": row_num, "name": name, "reason": f"узел по нумерации {path_str}",
                })
            state.seen_ids.add(cat.id)
            if parent_id is None:
                state.seen_roots.add(cat.id)
            else:
                state.touched_parents.add(parent_id)
            _path_str_full = " / ".join(node_path_names[cat.id])
            if _path_str_full not in state.new_path_cats:
                state.new_paths.append(_path_str_full)
            state.new_path_cats[_path_str_full] = cat

            feo_sum = row_feo_money(row, c_row_feo_sum, None, None, None, c_budget)
            if feo_sum is not None:
                if cat.budget != feo_sum:
                    cat.budget = feo_sum
                register_budget_write(state, cat, subsidy_id, node_path_names[cat.id], row_num, feo_sum, name)
            else:
                plan_sum = to_dec(get_cell(row, c_row_plan_sum))
                if plan_sum is not None:
                    if cat.budget != plan_sum:
                        cat.budget = plan_sum
                    register_budget_write(state, cat, subsidy_id, node_path_names[cat.id], row_num, plan_sum, name)
                    warnings.append({
                        "kind": "group_total_row",
                        "row": row_num,
                        "name": name,
                        "message": (
                            f"«{name}»: Сумма по ФЭО не заполнена, итог группы {_fmt(plan_sum)} "
                            f"взят из Суммы плана — позицией не записан"
                        ),
                    })
            continue

        # --- ЛИСТ: у строки нет детей по нумерации → позиция, не категория. --
        if ancestor is None:
            # Лист-сирота без узла-предка (верхний уровень пути без узла над
            # ним) — заводим ЛИСТ-КАТЕГОРИЮ тем же приёмом, что и обычный лист
            # без Ур.5-детей: apply_collected_plan (feo_import_plan.py) сама
            # создаст ОДНУ авто-позицию по collected_plan — Правило №6, не
            # дублировать создание FeoPlannedItem второй раз здесь.
            name = own_level_name or item_name_cell
            if not name:
                state.skipped += 1
                state.skipped_details.append({
                    "row": row_num, "name": None,
                    "reason": f"строка по нумерации {path_str} без имени и без узла-предка — пропущена",
                })
                continue
            cat, is_new = await find_or_create(subsidy_id, None, name, len(path))
            nodes_by_path[path] = cat
            node_path_names[cat.id] = [name]
            if is_new:
                state.created += 1
                state.created_details.append({
                    "row": row_num, "name": name, "reason": f"узел по нумерации {path_str}",
                })
            state.seen_ids.add(cat.id)
            state.seen_roots.add(cat.id)
            if name not in state.new_path_cats:
                state.new_paths.append(name)
            state.new_path_cats[name] = cat
            feo_amount = row_feo_money(row, c_row_feo_sum, None, None, None, c_budget)
            amount = to_dec(get_cell(row, c_row_plan_sum))
            if amount is None:
                amount = feo_amount
            if amount is not None:
                qty = to_dec(get_cell(row, c_qty)) or ONE
                is_feo, is_plan = resolve_origin_flags(feo_amount, amount if amount != feo_amount else None)
                _leaf_item_name = item_name_cell or name
                _leaf_item_type = await resolve_item_type_for_row(state, row_num, _leaf_item_name, None)
                state.collected_plan[cat.id] = {
                    "qty": qty, "unit": get_cell(row, c_unit), "amount": amount,
                    "row": row_num, "name": _leaf_item_name, "item_type": _leaf_item_type,
                    "from_feo_fallback": False,
                    "is_feo_breakdown": is_feo, "is_internal_plan": is_plan,
                }
                state.plan_writes.setdefault(cat.id, []).append(row_num)
            continue

        item_name = item_name_cell or own_level_name
        if not item_name:
            state.skipped += 1
            state.skipped_details.append({
                "row": row_num, "name": None,
                "reason": f"строка по нумерации {path_str} без имени позиции — пропущена",
            })
            continue

        # Расхождение «имя уровня строки vs узел, назначенный нумерацией» —
        # нумерация побеждает всегда, здесь только предупреждаем (п.1 задания,
        # боевой пример r17–r20 «Расходы на арендную плату» под узлом
        # «Коммунальные расходы»).
        if own_level_name and _norm(own_level_name) != _norm(ancestor.name):
            _mismatch_groups.setdefault((ancestor.name, own_level_name), []).append(row_num)

        qty = to_dec(get_cell(row, c_qty))
        unit = get_cell(row, c_unit)
        price = to_dec(get_cell(row, c_item_price))
        amount = to_dec(get_cell(row, c_row_plan_sum))
        if amount is None and price is not None:
            amount = (price * (qty or ONE)).quantize(QUANT)
        if amount is None:
            amount = row_feo_money(row, c_row_feo_sum, None, None, None, c_budget)

        raw_item_type = get_cell(row, c_item_type) if c_item_type is not None else None
        item_type = normalize_item_type(raw_item_type) if raw_item_type else None
        item_type = await resolve_item_type_for_row(state, row_num, item_name, item_type)

        state.lvl5_leaves.add(ancestor.id)
        state.lvl5_sum_by_cat[ancestor.id] = state.lvl5_sum_by_cat.get(ancestor.id, ZERO) + (amount or ZERO)
        state.lvl5_item_rows.setdefault(ancestor.id, []).append(row_num)

        _path_names = node_path_names.get(ancestor.id, [ancestor.name])
        _dup_key = group_key(subsidy_id, _path_names, item_name)
        register_pending_item(state, _dup_key, ancestor, {
            "row": row_num, "name": item_name,
            "qty": qty if qty is not None else ONE, "unit": unit, "amount": amount, "unit_price": price,
            "feo_qty": None, "feo_unit": None, "feo_unit_price": None, "feo_amount": None,
            "item_type": item_type, "is_active": True,
            "is_feo_breakdown": False, "is_internal_plan": True,
            "path": _path_names,
        })

    for (parent_name, own_name), row_nums in _mismatch_groups.items():
        warnings.append({
            "kind": "numbering_vs_levels",
            "row": row_nums[0],
            "name": own_name,
            "message": (
                f"{format_rows(row_nums)}: имя уровня «{own_name}» отличается от узла «{parent_name}», "
                f"к которому строки привязаны по нумерации — привязка по нумерации сохранена"
            ),
        })

    # Тот же хвост, что и у apply_rows (feo_import_apply.py) — общие функции,
    # читающие state.budget_writes/state.pending_lvl5_items независимо от
    # того, каким путём они заполнены (Правило №6).
    apply_budget_conflict_resolutions(state)
    apply_category_sum_conflicts(state)
