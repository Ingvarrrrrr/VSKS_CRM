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

Владелец 2026-09-16 (дословно по смыслу): сумма категории «по ФЭО» — либо её
СОБСТВЕННАЯ сумма (строка-заголовок с числом), либо сумма ВЛОЖЕННЫХ позиций.
Сейчас (см. `app/services/subsidy_budget.py::compute_budget_map`) при наличии
ОБЕИХ молча побеждает собственная сумма узла — это ОСТАЁТСЯ поведением по
умолчанию (`compute_budget_map` не трогаем — единственная формула, Правило
№6). Но если у категории в ЭТОМ импорте есть И собственная сумма, И
заполненные позиции (`feo_amount` вложенных позиций Ур.5, СОБСТВЕННЫХ узла,
не потомков) — «при переносе должно давать выбирать», тем же механизмом, что
и выше (третий канал не заводим):

    apply_category_sum_conflicts(state)
        — вызывается СРАЗУ ПОСЛЕ apply_budget_conflict_resolutions (тот же
          вызов в feo_import_apply.py), когда `cat.budget` уже разрешён (если
          у самой суммы категории тоже был конфликт нескольких строк — см.
          выше). Собственная сумма позиций считается по `state.pending_
          lvl5_items` (наполнено feo_import_apply.py в основном цикле,
          ДО вызова этой функции) — сумма/число СОБСТВЕННЫХ (не через
          дочерние категории) активных строк узла с непустым feo_amount;
          объединение/разделение дублей Ур.5 (feo_import_duplicates.py) на
          эту сумму не влияет — деньги при объединении складываются
          тождественно (см. `_combine_rows`), при «оставить как есть» просто
          не меняются, так что считать можно ДО finalize_lvl5_items.
          Группа — `state.category_sum_conflict_groups`, ключ —
          `catsum::<то же построение, что и budget_group_key>` (свой
          префикс — Правило №6, не путать пространства имён одного канала
          `duplicate_resolutions`). Решение человека — 'own' (по умолчанию,
          прежнее поведение не меняется) | 'items'; 'items' — `cat.budget :=
          None`, тогда единственная формула `compute_budget_map` сама
          возьмёт сумму позиций (не дублируем расчёт здесь) — плюс одно
          информационное предупреждение.
"""
from decimal import Decimal

from app.services.feo_import_common import ZERO
from app.services.feo_import_common import fmt as _fmt
from app.services.feo_import_duplicates import group_key as _item_group_key

KEY_PREFIX = "budget::"
# Правило №6 — тот же канал `duplicate_resolutions`, отдельное пространство
# имён ключей (см. докстринг выше, category_sum_conflict_key).
CATSUM_KEY_PREFIX = "catsum::"


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


def category_sum_conflict_key(subsidy_id, path_names: list) -> str:
    """Ключ группы «собственная сумма категории vs сумма её позиций» — та же
    обёртка над `group_key`, что и `budget_group_key` выше (Правило №6, один
    построитель пути), другой префикс — своё пространство имён в общем
    словаре `duplicate_resolutions`."""
    return CATSUM_KEY_PREFIX + _item_group_key(subsidy_id, path_names[:-1], path_names[-1])


def _own_items_feo_totals(state) -> dict:
    """cat_id (leaf.id) -> (сумма feo_amount, число строк) по ВСЕМ строкам
    `state.pending_lvl5_items`, накопленным основным циклом `apply_rows` для
    ЭТОГО импорта — считаем ДО `finalize_lvl5_items` (см. докстринг модуля):
    объединение группы дублей Ур.5 сохраняет сумму тождественно, «оставить
    как есть» её не меняет вовсе, так что число здесь совпадёт с тем, что
    реально ляжет в БД при любом решении по дублям. Неактивная строка (файл
    явно пометил "Активна" = нет) в счёт не идёт — тем же признаком, каким
    `compute_budget_map` (subsidy_budget.py) фильтрует позиции при подсчёте
    суммы по дереву, иначе число здесь разошлось бы с тем, что покажет дерево
    после выбора «взять сумму позиций»."""
    totals: dict = {}
    for rows in state.pending_lvl5_items.values():
        for r in rows:
            leaf = r.get("leaf")
            fa = r.get("feo_amount")
            if leaf is None or fa is None or not r.get("is_active", True):
                continue
            amt, cnt = totals.get(leaf.id, (ZERO, 0))
            totals[leaf.id] = (amt + fa, cnt + 1)
    return totals


def apply_category_sum_conflicts(state) -> None:
    """Единственное место, строящее группы «собственная сумма vs сумма
    позиций» и применяющее решение человека — вызывается ПОСЛЕ
    `apply_budget_conflict_resolutions` (см. докстринг модуля), чтобы читать
    уже РАЗРЕШЁННУЮ собственную сумму категории (`cat.budget`), если у неё
    самой был конфликт нескольких строк. Категория без собственной явной
    суммы в этом импорте (не побывавшая в `state.budget_write_cats`) или без
    СОБСТВЕННЫХ позиций с feo_amount — не кандидат, группы и предупреждения
    нет, `cat.budget` не трогаем (то же самое поведение, что и всегда было —
    задача владельца требует выбор ТОЛЬКО когда оба источника реально
    заполнены одновременно)."""
    items_totals = _own_items_feo_totals(state)
    for cat_id, cat in state.budget_write_cats.items():
        own_amount = cat.budget
        if own_amount is None:
            continue
        items_amount, items_count = items_totals.get(cat_id, (ZERO, 0))
        if items_count == 0:
            continue

        subsidy_id, path_names = state.budget_write_paths[cat_id]
        key = category_sum_conflict_key(subsidy_id, path_names)
        name = path_names[-1] if path_names else cat.name

        resolution = state.duplicate_resolutions.get(key, "own")
        if resolution == "items":
            if cat.budget is not None:
                cat.budget = None
            state.warnings.append({
                "kind": "category_sum_replaced_by_items",
                "row": None,
                "name": name,
                "message": (
                    f"«{name}»: по вашему выбору взята сумма позиций "
                    f"({_fmt(items_amount)}, позиций: {items_count}) вместо "
                    f"собственной суммы категории ({_fmt(own_amount)})"
                ),
            })
        else:
            resolution = "own"

        state.category_sum_conflict_groups.append({
            "key": key,
            "name": name,
            "category_path": " / ".join(path_names),
            "own_amount": _num(own_amount),
            "items_amount": _num(items_amount),
            "items_count": items_count,
            "options": ["own", "items"],
            "resolution": resolution,
        })
