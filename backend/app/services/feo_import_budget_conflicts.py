"""«Сумма по ФЭО» одной категории, заданная в файле НЕСКОЛЬКИМИ строками с
РАЗНЫМИ значениями — решение владельца (2026-09-15, опрос): не брать молча
последнюю, а спросить человека ПО КАЖДОЙ такой категории отдельно — тот же
паттерн, что уже применён к полным совпадениям имени плановой позиции
(feo_import_duplicates.py, group_key/duplicate_groups/FeoImportWizard.vue).

Пример владельца: категория «Пожарное оборудование» объявлена дважды —
строка 10 (1 400 000) и строка 50 (1 500 000). Варианты: «взять первую»,
«взять последнюю» (было раньше — молча, без выбора), «сложить».

НЕ конфликт (без группы, без предупреждения) — несколько строк ЗАДАЮТ ТО ЖЕ
САМОЕ число этой категории (обычное дело для «строк-подытогов» без Уровня 3,
см. комментарий у budget_writes в feo_import_apply.py) — там реально нечего
выбирать, вопрос был бы шумом.

Ключ группы — ТА ЖЕ схема, что и у `group_key` дублей позиций
(feo_import_duplicates.py, Правило №6 — не заводить второй способ строить
ключ): subsidy_id + нормализованные имена узлов пути, НЕ id категории (id —
autoincrement внутри текущей транзакции, не совпадает между dry-run и боевым
вызовом — см. докстринг feo_import_duplicates.py). Пространство имён
отдельное — префикс `budget::` (KEY_PREFIX) — чтобы не столкнуться с ключами
групп дублей позиций в том же словаре `duplicate_resolutions` (общий JSON-
канал с фронта — Правило №6: один канал решений на весь импорт, не два).

Публичный API:
    register_budget_write(state, cat, subsidy_id, path_names, row_num, value, name)
        — единственное место, пишущее в state.budget_writes (заменяет прямые
          budget_writes.setdefault(...).append(...) в feo_import_apply.py);
          дополнительно запоминает объект категории и её путь — нужны, чтобы
          применить решение человека к cat.budget и построить группу ПОСЛЕ
          основного цикла по строкам.
    apply_budget_conflict_resolutions(state)
        — вызывается ПОСЛЕ основного цикла (feo_import_apply.py, там же, где
          раньше стоял безусловный warning `budget_overwritten_by_row`): для
          каждой категории с ≥2 РАЗНЫМИ значениями строит группу (кладёт в
          state.budget_conflict_groups), применяет решение человека
          (state.duplicate_resolutions[key] — 'first'/'last'/'sum', по
          умолчанию 'last' — как было раньше, поведение тех, кто ничего не
          выбрал, не меняется) и добавляет ОДНО информационное
          предупреждение kind=`budget_overwritten_by_row` (тот же kind, что и
          раньше, — фронт/тесты, завязанные на него, не ломаются).
"""
from decimal import Decimal

from app.services.feo_import_common import ZERO
from app.services.feo_import_common import fmt as _fmt
from app.services.feo_import_duplicates import group_key as _item_group_key

KEY_PREFIX = "budget::"


def _num(v) -> float | None:
    return None if v is None else float(v)


def budget_group_key(subsidy_id, path_names: list) -> str:
    """Ключ группы конфликта Суммы по ФЭО — обёртка над `group_key` дублей
    позиций (Правило №6, не дублировать нормализацию пути): последний элемент
    `path_names` — сама категория, остальные — её родители, ровно то же
    разложение (parents, item_name), что и у group_key. Префикс `budget::`
    отделяет пространство имён от ключей групп дублей Ур.5 в том же словаре
    `duplicate_resolutions`."""
    return KEY_PREFIX + _item_group_key(subsidy_id, path_names[:-1], path_names[-1])


def register_budget_write(state, cat, subsidy_id, path_names: list, row_num: int, value: Decimal, name: str) -> None:
    """Строка файла задала Сумму по ФЭО (или легаси «Финансирование») узла
    `cat` — копим ВСЕ попытки (не только изменившие значение), как и раньше
    (см. комментарий в feo_import_apply.py у прежнего места вызова), плюс
    объект категории и путь — нужны только здесь, для построения группы и
    применения решения ПОСЛЕ цикла по всем строкам файла."""
    state.budget_writes.setdefault(cat.id, []).append((row_num, value, name))
    state.budget_write_cats[cat.id] = cat
    state.budget_write_paths[cat.id] = (subsidy_id, path_names)


def apply_budget_conflict_resolutions(state) -> None:
    """Единственное место, разбирающее `state.budget_writes` в группы
    конфликтов + применяющее решение человека к `cat.budget`. Категория,
    записанная только ОДИН раз или НЕСКОЛЬКО раз одним и тем же значением, —
    не конфликт: группы и предупреждения нет, cat.budget остаётся тем, что
    уже поставил основной цикл (последняя по порядку строка — то же
    поведение, что и всегда было)."""
    for cat_id, writes in state.budget_writes.items():
        values = {v for _, v, _ in writes}
        if len(values) < 2:
            continue  # одинаковые повторы — не конфликт (владелец, 2026-09-15)

        cat = state.budget_write_cats[cat_id]
        subsidy_id, path_names = state.budget_write_paths[cat_id]
        key = budget_group_key(subsidy_id, path_names)
        name = writes[-1][2]

        first_row, first_val, _ = writes[0]
        last_row, last_val, _ = writes[-1]
        total = sum((v for _, v, _ in writes), ZERO)

        resolution = state.duplicate_resolutions.get(key, "last")
        if resolution == "first":
            chosen = first_val
            _tail = f"по вашему выбору взята первая (строка {first_row}, {_fmt(first_val)})"
        elif resolution == "sum":
            chosen = total
            _tail = f"по вашему выбору сложены: {_fmt(total)}"
        else:
            resolution = "last"
            chosen = last_val
            _tail = f"учтена последняя (строка {last_row})"

        if cat.budget != chosen:
            cat.budget = chosen

        state.budget_conflict_groups.append({
            "key": key,
            "name": name,
            "category_path": " / ".join(path_names),
            "rows": [{"row": r, "amount": _num(v)} for r, v, _ in writes],
            "options": {
                "first": {"row": first_row, "amount": _num(first_val)},
                "last": {"row": last_row, "amount": _num(last_val)},
                "sum": {"amount": _num(total)},
            },
            "resolution": resolution,
        })

        _rows_vals = ", ".join(f"{r} ({_fmt(v)})" for r, v, _ in writes)
        state.warnings.append({
            "kind": "budget_overwritten_by_row",
            "row": None,
            "name": name,
            "message": f"Сумма по ФЭО для «{name}» задана в строках {_rows_vals} — {_tail}",
        })
