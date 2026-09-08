"""Ядро парсинга импорта категорий ФЭО из Excel-подобных строк — _do_feo_import.

Вынесено из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения — самая тяжёлая функция файла (~1230 строк), общий код
для POST /import и /import-mapped (app/routers/feo_import.py).

Гейт записи по субсидиям файла (_require_feo_import_write) и чистка
опустевших узлов (_purge_feo_categories) зовутся через `from app.routers
import feo_categories as fc` — так monkeypatch `fc._require_feo_category_write`
(который _require_feo_import_write вызывает поштучно по каждой субсидии) в
тестах продолжает работать. _feo_category_load/_relink_feo_category
импортируются ЛОКАЛЬНО (внутри функции, не на уровне модуля) из
app.routers.feo_import — тот модуль сам импортирует _do_feo_import ИЗ этого
файла на уровне модуля (для /import, /import-mapped), top-level импорт в обе
стороны дал бы цикл.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.utils.text import normalize_feo_name
from app.routers import feo_categories as fc


async def _do_feo_import(
    rows: list,
    c_subsidy: int | None,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
    c_lvl5: int | None,
    c_qty: int | None,
    c_unit: int | None,
    c_item_amt: int | None,
    c_code: int | None,
    c_appendix: int | None,
    c_budget: int | None,
    c_active: int | None,
    db: AsyncSession,
    c_qty_lvl2: int | None = None,
    c_qty_lvl3: int | None = None,
    c_qty_lvl4: int | None = None,
    c_unit_lvl2: int | None = None,
    c_unit_lvl3: int | None = None,
    c_unit_lvl4: int | None = None,
    c_amt_lvl2: int | None = None,
    c_amt_lvl3: int | None = None,
    c_amt_lvl4: int | None = None,
    c_feo_qty_lvl2: int | None = None,
    c_feo_qty_lvl3: int | None = None,
    c_feo_qty_lvl4: int | None = None,
    c_feo_unit_lvl2: int | None = None,
    c_feo_unit_lvl3: int | None = None,
    c_feo_unit_lvl4: int | None = None,
    c_feo_amt_lvl2: int | None = None,
    c_feo_amt_lvl3: int | None = None,
    c_feo_amt_lvl4: int | None = None,
    c_feo_sum_lvl2: int | None = None,
    c_feo_sum_lvl3: int | None = None,
    c_feo_sum_lvl4: int | None = None,
    c_plan_sum_lvl2: int | None = None,
    c_plan_sum_lvl3: int | None = None,
    c_plan_sum_lvl4: int | None = None,
    c_item_price: int | None = None,
    # Новый 18-колоночный шаблон (2026-08-14): числа «по ФЭО»/«плана» — ОДНА пара
    # колонок на всю строку (не по уровням), см. блок «плоские числа» ниже.
    c_row_feo_qty: int | None = None,
    c_row_feo_unit: int | None = None,
    c_row_feo_price: int | None = None,
    c_row_feo_sum: int | None = None,
    c_row_plan_qty: int | None = None,
    c_row_plan_unit: int | None = None,
    c_row_plan_price: int | None = None,
    c_row_plan_sum: int | None = None,
    c_item_type: int | None = None,
    default_subsidy_id: int | None = None,
    dry_run: bool = False,
    user=None,
    remap: str = "",
    apply_remap: bool = False,
) -> dict:
    """Core import logic shared by /import и /import-mapped endpoints.

    dry_run=True: вся обработка выполняется, но транзакция откатывается.
    Возвращает {created, updated, skipped, errors, warnings, ...}.

    N2б: `remap` — JSON-список {"old_id": int, "new_path": str} для явного
    переезда несопоставленных узлов на новые (переезд + удаление опустевших
    старых узлов выполняются после основного цикла, см. блок ниже unmatched).
    Фаза переезда/удаления выполняется ТОЛЬКО при apply_remap=True — иначе
    (обычная загрузка без мастера сопоставления) выполняется только анализ.
    """
    import re as _re
    import json as _json
    # _feo_category_load/_relink_feo_category живут в app.routers.feo_import
    # (Правило №5, разрезание feo_categories.py) — локальный импорт здесь
    # (а не на уровне модуля) намеренно: feo_import.py сам импортирует
    # _do_feo_import ИЗ этого модуля при загрузке (для /import, /import-mapped),
    # top-level импорт в обе стороны дал бы цикл.
    from app.routers.feo_import import _feo_category_load, _relink_feo_category

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

    if c_lvl2 is None:
        raise HTTPException(400, "Не найден обязательный столбец: 'Уровень 2 (Направление расходов)'")
    if c_subsidy is None and default_subsidy_id is None:
        raise HTTPException(400, "Укажите столбец 'Субсидия' или выберите субсидию назначения")
    if remap and not apply_remap:
        raise HTTPException(400, "Параметр remap передан без apply_remap=true")

    remap_list: list[dict] = []
    if remap:
        try:
            _raw_remap = _json.loads(remap)
            if not isinstance(_raw_remap, list):
                raise ValueError("ожидался список")
            for _item in _raw_remap:
                if not isinstance(_item, dict) or "old_id" not in _item or "new_path" not in _item:
                    raise ValueError("каждый элемент должен содержать old_id и new_path")
                remap_list.append({
                    "old_id": int(_item["old_id"]),
                    "new_path": str(_item["new_path"]).strip(),
                })
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Неверный формат параметра remap: {e}")

    def get_cell(row, col: int | None) -> str | None:
        if col is None or col < 0: return None
        if col >= len(row): return None
        v = row[col]
        if v is None: return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null'):
            return None
        return s

    def to_bool(v: str | None) -> bool:
        if v is None: return True
        return v.lower() in ("да", "yes", "true", "1", "+")

    def to_dec(v: str | None):
        if not v: return None
        s = str(v).strip()
        if not s or s in ('-', '—', '–', 'None', 'null', 'н/д', 'N/A'):
            return None
        s = s.replace(" ", "").replace("\xa0", "").replace("\u202f", "")
        s = s.replace("₽", "").replace("руб", "").replace("р.", "").replace("р", "")
        s = s.replace(",", ".")
        s = s.rstrip(".")
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            return None

    def _fmt(v) -> str:
        """Число с разделителями разрядов для читаемых предупреждений."""
        try:
            return f"{float(v):,.2f}".replace(",", " ")
        except Exception:
            return str(v)

    def _norm(s: str) -> str:
        """Нормализация имени уровня для сравнения."""
        return normalize_feo_name(s)

    ZERO = Decimal("0")
    QUANT = Decimal("0.01")

    from app.models.subsidy import Subsidy
    sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    sub_by_name = {s.name.lower().strip(): s.id for s in sub_rows}

    existing_cats = (await db.execute(select(FeoCategory))).scalars().all()
    cat_cache: dict[tuple, FeoCategory] = {}
    for c in existing_cats:
        cat_cache[(c.subsidy_id, c.parent_id, c.name.lower().strip())] = c

    # --- Снимок дерева ДО импорта (нужен и для отчёта "несопоставленные узлы",
    # и для фазы переезда/удаления N2б). Перенесено сюда с места ниже (после
    # основного цикла) — переезд/удаление должны опираться на состояние дерева
    # ДО того, как основной цикл его изменит.
    existing_by_id: dict[int, FeoCategory] = {c.id: c for c in existing_cats}
    existing_children: dict[int, list[int]] = {}
    for c in existing_cats:
        if c.parent_id is not None:
            existing_children.setdefault(c.parent_id, []).append(c.id)

    def _get_root_id(cat_id: int) -> int:
        cur = existing_by_id.get(cat_id)
        if cur is None:
            return cat_id
        visited: set[int] = set()
        while cur.parent_id is not None and cur.parent_id in existing_by_id:
            if cur.id in visited:
                break
            visited.add(cur.id)
            cur = existing_by_id[cur.parent_id]
        return cur.id

    def _full_path(cat_id: int) -> str:
        chain: list[str] = []
        cur = existing_by_id.get(cat_id)
        visited: set[int] = set()
        while cur is not None and cur.id not in visited:
            chain.append(cur.name)
            visited.add(cur.id)
            if cur.parent_id is None:
                break
            cur = existing_by_id.get(cur.parent_id)
        return " / ".join(reversed(chain))

    def _subtree_ids_local(root_id: int) -> list[int]:
        ids = [root_id]
        stack = [root_id]
        while stack:
            cur_id = stack.pop()
            for ch_id in existing_children.get(cur_id, []):
                ids.append(ch_id)
                stack.append(ch_id)
        return ids

    def _strip_num(s: str) -> str:
        return _re.sub(r'^\s*\d+([.\)]\d+)*[.\)]?\s*', '', s).strip()

    def _canon_path(path: str, *, lower: bool, yo: bool) -> str:
        out = []
        for seg in path.split(" / "):
            s = _strip_num(seg)
            if lower:
                s = _re.sub(r'\s+', ' ', s.lower()).strip()
            if yo:
                s = s.replace('ё', 'е')
            out.append(s)
        return " / ".join(out)

    created = 0; updated = 0; skipped = 0; errors: list[dict] = []
    warnings: list[dict] = []
    created_details: list[dict] = []
    updated_details: list[dict] = []
    skipped_details: list[dict] = []

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

    # Множество id родительских узлов, затронутых импортом — для parent_sum_mismatch
    touched_parents: set[int] = set()

    # --- Для отчёта "несопоставленные узлы" (только анализ, БЕЗ мутаций) ---
    seen_ids: set[int] = set()      # id всех категорий, вернувшихся из find_or_create
    seen_roots: set[int] = set()    # id корневых (ур.2) узлов, затронутых файлом
    new_paths: list[str] = []       # пути узлов, которые описывает файл ("Ур2 / Ур3 / Ур4")
    _new_paths_seen: set[str] = set()
    new_path_cats: dict[str, FeoCategory] = {}  # путь → объект категории (для резолва remap.new_path)

    # --- 2026-08: план больше не пишется прямо в cat.planned_quantity/planned_amount
    # (владелец требует, чтобы план жил ЗАПИСЯМИ внутри категории — FeoPlannedItem,
    # у которой amount — это СУММА, а не цена за единицу). Пока идёт цикл по строкам,
    # копим посчитанный план каждого уровня сюда, а после цикла (когда уже видно,
    # у какой категории есть дети, а у какой — свои позиции Ур.5) превращаем
    # в FeoPlannedItem, см. блок обработки collected_plan ниже.
    collected_plan: dict[int, dict] = {}  # cat.id -> {"qty","unit","amount","row","name"}
    lvl5_leaves: set[int] = set()         # id категорий, которым в ЭТОМ импорте заведены/обновлены позиции Ур.5
    lvl5_sum_by_cat: dict[int, Decimal] = {}  # сумма amount позиций Ур.5 по категории (из этого импорта)

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

    # --- N2б: пред-проход ТОЛЬКО ради определения затронутых субсидий (для
    # снимка предыдущей редакции ниже) — лёгкая версия резолва subsidy_id,
    # без накопления ошибок (их соберёт основной цикл).
    touched_subsidies: set[int] = set()
    for _row in rows:
        _lvl2 = get_cell(_row, c_lvl2)
        if not _lvl2 or _lvl2.startswith("←"):
            continue
        _sub_name = get_cell(_row, c_subsidy) if c_subsidy is not None else None
        if _sub_name and not _sub_name.startswith("←"):
            _sid = sub_by_name.get(_sub_name.lower().strip()) or default_subsidy_id
        else:
            _sid = default_subsidy_id
        if _sid:
            touched_subsidies.add(_sid)

    # --- B2 (дыра импорта, закрыта 2026-09-01): гейт ЗАПИСИ по КАЖДОЙ субсидии
    # из touched_subsidies — ДО снимка версии дерева ниже (первая запись в БД
    # этого импорта) и ДО основного цикла, а значит и ДО выдачи dry_run-превью
    # (в dry_run обработка идёт точно так же, откат — только в самом конце).
    # См. docstring _require_feo_import_write за картиной дыры.
    await fc._require_feo_import_write(user, db, touched_subsidies, sub_rows)

    # --- N2б: снимок предыдущей редакции — ВСЕГДА и ДО основного цикла.
    # _create_plan_graph_version заново селектит FeoCategory, поэтому вызывать
    # её нужно именно здесь: после основного цикла дерево уже было бы изменено
    # (создание/обновление/удаление), и снимок перестал бы быть "предыдущей"
    # редакцией. Снимок самодостаточен (дерево пишется в JSON инлайном), так
    # что последующее удаление узлов не портит уже сохранённую версию.
    version_created = False
    if user is not None:
        _remap_note_suffix = ""
        if remap_list:
            _pairs = []
            for _rm in remap_list[:5]:
                _pairs.append(f"«{_full_path(_rm['old_id'])}» → «{_rm['new_path']}»")
            _remap_note_suffix = "; перенос узлов: " + "; ".join(_pairs)
            if len(remap_list) > 5:
                _remap_note_suffix += f" и ещё {len(remap_list) - 5}"
        _note = "Загрузка новой редакции разбивки ФЭО" + _remap_note_suffix
        from app.routers.purchases import _create_plan_graph_version
        for _sid in touched_subsidies:
            _v_created = await _create_plan_graph_version(subsidy_id=_sid, db=db, user=user, note=_note)
            if _v_created:
                version_created = True

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
                # обнулить поля группы) решается ПОСЛЕ цикла по всем строкам —
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

                if plan_sum is not None and plan_sum == ZERO and (plan_qty is None or plan_qty == ZERO):
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

    # Собираем актуальные объекты категорий по id через cat_cache (все объекты
    # уже в сессии) — нужно и для обработки collected_plan ниже, и для проверки
    # "родитель vs сумма детей" после неё.
    cat_by_db_id: dict[int, FeoCategory] = {c.id: c for c in cat_cache.values() if c.id is not None}

    # --- Обработка collected_plan: план строки → FeoPlannedItem внутри
    # категории, а не поля категории (см. комментарий у объявления collected_plan
    # выше цикла по строкам). Делается ЗДЕСЬ, после цикла по всем строкам файла,
    # потому что только сейчас окончательно видно: у категории есть подкатегории
    # (группа) или нет (лист), и получила ли она в этом же импорте отдельные
    # позиции Ур.5.
    if collected_plan:
        from app.models.feo_planned_item import FeoPlannedItem

        _plan_ids = list(collected_plan.keys())
        # Кто из собранных категорий — родитель (группа): есть хотя бы один
        # ребёнок — существующий или только что созданный в этом же импорте
        # (find_or_create уже сделал flush, поэтому дети видны через запрос).
        _parent_rows = (await db.execute(
            select(FeoCategory.parent_id).where(FeoCategory.parent_id.in_(_plan_ids))
        )).scalars().all()
        _groups_with_plan = {pid for pid in _parent_rows if pid is not None}

        for _cat_id, _pdata in collected_plan.items():
            _cat_obj = cat_by_db_id.get(_cat_id)
            if _cat_obj is None:
                continue
            _plan_name = _pdata["name"]
            _plan_row = _pdata["row"]

            if _cat_id in _groups_with_plan:
                # Категория-ГРУППА: собственный план группы в compute_feo_plan_tree
                # (app/services/feo_plan.py) вообще не участвует в расчёте — план
                # группы считается только по сумме подкатегорий. Оставлять здесь
                # значения — мёртвые данные, которые незаметно всплывают и ломают
                # числа, если подкатегория потом пропадёт из файла (боевой случай:
                # категория «Микроавтобус (автобус)» после исчезновения подкатегории
                # (DONGFENG) JUNFENG K33 внезапно показала цену 10 130 000 за штуку
                # и превышение на «Транспорт и техника»).
                if _cat_obj.planned_quantity is not None:
                    _cat_obj.planned_quantity = None
                if _cat_obj.planned_amount is not None:
                    _cat_obj.planned_amount = None
                warnings.append({
                    "kind": "group_plan_ignored",
                    "row": _plan_row,
                    "name": _plan_name,
                    "message": f"План строки «{_plan_name}» не записан: у категории есть подкатегории, план группы считается по ним",
                })
                continue

            if _cat_id in lvl5_leaves:
                # Лист уже описан отдельными позициями Ур.5 в этом же импорте —
                # план строки дублировал бы их сумму, отдельную позицию с именем
                # самой категории не создаём.
                if _cat_obj.planned_quantity is not None:
                    _cat_obj.planned_quantity = None
                if _cat_obj.planned_amount is not None:
                    _cat_obj.planned_amount = None
                _items_sum = lvl5_sum_by_cat.get(_cat_id, ZERO)
                if abs(_items_sum - (_pdata["amount"] or ZERO)) > Decimal("0.01"):
                    # Честное указание источника (задача владельца): если этот план
                    # строки на самом деле собран старым фолбэком из чисел «по ФЭО»
                    # (см. from_feo_fallback выше — плановых кол-ва/цены в файле не
                    # было), пользователь не должен думать, что цифра пришла из
                    # плановых колонок — уточняем происхождение прямо в тексте.
                    _fallback_note = (
                        " (взят из чисел по ФЭО, плановые колонки пустые)"
                        if _pdata.get("from_feo_fallback") else ""
                    )
                    warnings.append({
                        "kind": "plan_vs_items_mismatch",
                        "row": _plan_row,
                        "name": _plan_name,
                        "message": (
                            f"План строки «{_plan_name}» = {_fmt(_pdata['amount'])}{_fallback_note}, а сумма позиций Ур.5 "
                            f"= {_fmt(_items_sum)} — расхождение, план строки не записан"
                        ),
                    })
                continue

            # ЛИСТ без своих позиций Ур.5 в этом импорте — план строки описывает
            # саму категорию; реализуем плановой позицией с именем категории.
            # Ищем существующую активную позицию по точному совпадению имени
            # (TRIM+LOWER) — повторная загрузка того же файла обязана найти и
            # обновить именно её, а не плодить дубли.
            _name_norm = (_plan_name or "").strip().lower()
            _existing_items = (await db.execute(
                select(FeoPlannedItem).where(
                    FeoPlannedItem.feo_category_id == _cat_id,
                    FeoPlannedItem.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            _match_item = next(
                (it for it in _existing_items if (it.name or "").strip().lower() == _name_norm),
                None,
            )
            if _match_item is not None:
                _ch = False
                if _pdata["qty"] is not None and _match_item.quantity != _pdata["qty"]:
                    _match_item.quantity = _pdata["qty"]; _ch = True
                if _pdata["unit"] is not None and _match_item.unit != _pdata["unit"]:
                    _match_item.unit = _pdata["unit"]; _ch = True
                if _pdata["amount"] is not None and _match_item.amount != _pdata["amount"]:
                    _match_item.amount = _pdata["amount"]; _ch = True
                if _pdata.get("item_type") is not None and hasattr(_match_item, "item_type") and _match_item.item_type != _pdata["item_type"]:
                    _match_item.item_type = _pdata["item_type"]; _ch = True
                if _ch:
                    updated += 1
                    updated_details.append({"row": _plan_row, "name": _plan_name, "reason": "плановая позиция из плана строки"})
            else:
                _other_active = [it for it in _existing_items if (it.amount or ZERO) != ZERO]
                if _other_active:
                    # У категории уже есть свои плановые позиции — не задваиваем.
                    warnings.append({
                        "kind": "plan_skipped_has_items",
                        "row": _plan_row,
                        "name": _plan_name,
                        "message": f"У категории «{_plan_name}» уже есть плановые позиции — план строки не записан, чтобы не задвоить",
                    })
                else:
                    _pi_kwargs = dict(
                        feo_category_id=_cat_id,
                        name=(_plan_name or "")[:500],
                        quantity=_pdata["qty"],
                        unit=_pdata["unit"],
                        amount=_pdata["amount"],
                        is_active=True,
                        notes="из импорта ФЭО",
                    )
                    if hasattr(FeoPlannedItem, "item_type"):
                        _pi_kwargs["item_type"] = _pdata.get("item_type")
                    # Происхождение (владелец, 2026-09-01): эта ветка — колонка
                    # «Плановая» на категории целиком, БЕЗ построчной разбивки ФЭО
                    # (см. докстринг миграции aa1b2c3d4e5f_feo_planned_item_origin.py) —
                    # is_internal_plan, не is_feo_breakdown.
                    if hasattr(FeoPlannedItem, "is_internal_plan"):
                        _pi_kwargs["is_internal_plan"] = True
                    _pi = FeoPlannedItem(**_pi_kwargs)
                    db.add(_pi)
                    await db.flush()
                    created += 1
                    created_details.append({"row": _plan_row, "name": _plan_name, "reason": "плановая позиция из плана строки"})

            if _cat_obj.planned_quantity is not None:
                _cat_obj.planned_quantity = None
            if _cat_obj.planned_amount is not None:
                _cat_obj.planned_amount = None

    # Проверка родитель vs сумма ВСЕХ дочерних узлов (до commit)
    for parent_id in touched_parents:
        if parent_id not in cat_by_db_id:
            continue
        parent_cat = cat_by_db_id[parent_id]
        parent_budget = parent_cat.budget or ZERO
        if not parent_budget:
            continue
        # Сумма budget всех прямых детей из cat_cache (весь справочник)
        children_sum = sum(
            (c.budget or ZERO)
            for c in cat_cache.values()
            if c.parent_id == parent_id and c.id is not None
        )
        if abs(parent_budget - children_sum) > Decimal("0.01"):
            warnings.append({
                "kind": "parent_sum_mismatch",
                "row": None,
                "name": parent_cat.name,
                "message": (
                    f"Родитель «{parent_cat.name}»: бюджет {_fmt(parent_budget)} ≠ "
                    f"сумма всех дочерних узлов {_fmt(children_sum)}; победит значение родителя"
                ),
            })

    # --- Отчёт "несопоставленные узлы": ТОЛЬКО анализ, без мутаций/перепривязок ---
    # Дерево родитель→дети (existing_by_id/existing_children) и хелперы
    # (_get_root_id/_full_path/_subtree_ids_local/_strip_num/_canon_path)
    # определены выше, сразу после загрузки existing_cats — они нужны и здесь,
    # и в фазе переезда/удаления ниже.
    unmatched: list[dict] = []
    if seen_roots:
        candidates = [
            c for c in existing_cats
            if c.id not in seen_ids and _get_root_id(c.id) in seen_roots
        ]
        # Предрасчёт канонических форм всех new_paths (для подсказок)
        _np_nonum = [(np, _canon_path(np, lower=False, yo=False)) for np in new_paths]
        _np_norm = [(np, _canon_path(np, lower=True, yo=False)) for np in new_paths]
        _np_yo = [(np, _canon_path(np, lower=True, yo=True)) for np in new_paths]

        for cand in candidates:
            cand_path = _full_path(cand.id)
            subtree_ids = _subtree_ids_local(cand.id)
            load = await _feo_category_load(subtree_ids, db)
            # own_data (свой план/финансирование/поля ФЭО) считается наравне со
            # внешними ссылками — узел с собственными данными не «пустой», даже
            # если на него никто не ссылается (см. own_data в _feo_category_load,
            # причина — боевая пропажа категории (DONGFENG) JUNFENG K33).
            has_refs = any(load[k] for k in (
                "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
                "own_data",
            ))
            kind = "needs_mapping" if has_refs else "empty"

            suggestion = None
            suggestion_reason = None
            suggestion_candidates: list[str] | None = None
            if kind == "needs_mapping":
                cand_nonum = _canon_path(cand_path, lower=False, yo=False)
                for np, np_c in _np_nonum:
                    if np != cand_path and np_c == cand_nonum:
                        suggestion, suggestion_reason = np, "отличается нумерацией"
                        break
                if suggestion is None:
                    cand_norm = _canon_path(cand_path, lower=True, yo=False)
                    for np, np_c in _np_norm:
                        if np != cand_path and np_c == cand_norm:
                            suggestion, suggestion_reason = np, "отличается регистром или пробелами"
                            break
                if suggestion is None:
                    cand_yo = _canon_path(cand_path, lower=True, yo=True)
                    for np, np_c in _np_yo:
                        if np != cand_path and np_c == cand_yo:
                            suggestion, suggestion_reason = np, "отличается ё/е"
                            break
                if suggestion is None:
                    # Уровень вложенности мог измениться (в файле появился/пропал
                    # промежуточный узел) — тогда полный путь никогда не совпадёт
                    # ни по одной из трёх канонизаций выше, хотя лист (последний
                    # сегмент) и корень (первый сегмент) — те же самые. Пример
                    # боевого случая: «Организация питания / ИРП/Сухпай» (в БД,
                    # 2 уровня) vs «Организация питания / Питание.../ИРП/Сухпай»
                    # (в новом файле, 3 уровня). Сопоставляем по (корень, лист);
                    # предлагаем ТОЛЬКО если кандидат в new_paths ровно один —
                    # неоднозначность не разрешаем автоматически.
                    cand_yo2 = _canon_path(cand_path, lower=True, yo=True)
                    cand_segs = cand_yo2.split(" / ")
                    if len(cand_segs) >= 2:
                        cand_root, cand_leaf = cand_segs[0], cand_segs[-1]
                        _leaf_matches: list[str] = []
                        for np, np_c in _np_yo:
                            if np == cand_path:
                                continue
                            np_segs = np_c.split(" / ")
                            if len(np_segs) >= 2 and np_segs[0] == cand_root and np_segs[-1] == cand_leaf:
                                if np not in _leaf_matches:
                                    _leaf_matches.append(np)
                        if len(_leaf_matches) == 1:
                            suggestion, suggestion_reason = _leaf_matches[0], "отличается уровнем вложенности"
                        elif len(_leaf_matches) > 1:
                            suggestion_candidates = _leaf_matches

            unmatched.append({
                "id": cand.id,
                "path": cand_path,
                "kind": kind,
                "suggestion": suggestion,
                "suggestion_reason": suggestion_reason,
                "suggestion_candidates": suggestion_candidates,
                "load": {
                    "purchases": load["purchases"],
                    "purchase_items": load["purchase_items"],
                    "wishes": load["wishes"],
                    "wish_items": load["wish_items"],
                    "products": load["products"],
                    "feo_planned_items": load["feo_planned_items"],
                },
                "blocking_purchases": load["blocking_purchases"],
            })

    # --- N2б: переезд (remap) + удаление опустевших старых узлов ---
    # Обязательно ДО dry_run rollback/commit — все строки путей ниже нужно
    # материализовать в обычные str/dict, пока ORM-объекты ещё не просрочены.
    # Выполняется ТОЛЬКО при apply_remap=True (см. docstring) — обычная
    # загрузка (без явного согласия из мастера сопоставления) делает только
    # анализ unmatched/new_paths выше, ничего не переносит и не удаляет.
    relinked_count = 0
    deleted_count = 0
    remap_applied: list[dict] = []
    deleted_details: list[dict] = []
    remap_aborted_reason: str | None = None

    if apply_remap:
        _unmatched_ids = {u["id"] for u in unmatched}

        if errors:
            remap_aborted_reason = "переезд отменён: в файле есть ошибки"
        elif any(sd.get("reason") == "не указана субсидия назначения" for sd in skipped_details):
            remap_aborted_reason = "переезд отменён: часть строк без субсидии назначения"
        elif not seen_ids:
            remap_aborted_reason = "переезд отменён: файл не описал ни одного узла"

        _resolved_remap: list[tuple[int, FeoCategory, str]] = []
        if remap_aborted_reason is None:
            for _rm in remap_list:
                _old_id = _rm["old_id"]
                _new_path = _rm["new_path"]
                if _old_id not in _unmatched_ids:
                    remap_aborted_reason = f"переезд отменён: узел не найден среди несопоставленных (id={_old_id})"
                    break
                _new_cat = new_path_cats.get(_new_path)
                if _new_cat is None or _new_cat.id is None:
                    remap_aborted_reason = f"переезд отменён: цель сопоставления не найдена в новой разбивке: «{_new_path}»"
                    break
                _resolved_remap.append((_old_id, _new_cat, _new_path))

        if remap_aborted_reason is None:
            # Шаг A — применить переезды. Пути берём СЕЙЧАС (пока объекты живы).
            for _old_id, _new_cat, _new_path in _resolved_remap:
                _old_path = _full_path(_old_id)
                _counts = await _relink_feo_category(_old_id, _new_cat.id, db)
                relinked_count += sum(_counts.values())
                remap_applied.append({
                    "old_path": _old_path,
                    "new_path": _new_path,
                    "counts": _counts,
                })

            # Шаг B — удалить опустевшие несопоставленные узлы (кроме тех, кого
            # файл всё-таки назвал где-то в поддереве — их каскадом не трогаем).
            already_deleted: set[int] = set()
            # обходим от корня к листьям (по глубине path), иначе ребёнок удалится раньше родителя и родитель останется пустым висяком
            _unmatched_by_depth = sorted(unmatched, key=lambda _c: _c["path"].count(" / "))
            for _cand in _unmatched_by_depth:
                _cand_id = _cand["id"]
                if _cand_id in already_deleted:
                    continue
                subtree = _subtree_ids_local(_cand_id)
                if any(_sid in already_deleted for _sid in subtree):
                    continue
                if any(_sid in seen_ids for _sid in subtree):
                    continue
                load = await _feo_category_load(subtree, db)
                _real_refs = any(load[k] for k in (
                    "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
                ))
                # own_data (свой план/финансирование/поля ФЭО) считается наравне со
                # внешними ссылками — узел с собственными данными НЕ удаляется, даже
                # если в файле его нет и ссылок на него нет. Боевая причина: категория
                # «(DONGFENG) JUNFENG K33» дважды исчезала с прода — в ней был план
                # (planned_quantity/planned_amount) на 10 130 000, но ссылок не было,
                # и старая проверка has_refs их не видела, поэтому узел молча удалялся.
                has_refs = _real_refs or bool(load.get("own_data"))
                if has_refs:
                    if not _real_refs:
                        warnings.append({
                            "kind": "kept_has_own_plan",
                            "row": None,
                            "name": _cand["path"],
                            "message": (
                                f"Категория «{_cand['path']}» не удалена: в ней есть собственный план или "
                                f"финансирование по ФЭО, хотя в файле её нет. Проверьте, не потерялась ли строка в файле"
                            ),
                        })
                    continue
                for _sid in subtree:
                    if _sid == _cand_id:
                        deleted_details.append({"path": _cand["path"], "reason": "нет в новом файле, ссылок нет"})
                    else:
                        deleted_details.append({"path": _full_path(_sid), "reason": f"внутри удаляемого «{_cand['path']}»"})
                await fc._purge_feo_categories(subtree, db)
                deleted_count += len(subtree)
                already_deleted.update(subtree)

            # Шаг C — вычистить cat_cache от удалённых id, чтобы ниже по коду
            # (если он появится) не переиспользовать протухшие объекты.
            if already_deleted:
                for _k in [k for k, c in cat_cache.items() if c.id in already_deleted]:
                    del cat_cache[_k]

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    # Схлопываем одинаковые предупреждения по ключу (kind, name, message-без-суффикса)
    # Сохраняем номер строки первого вхождения и порядок появления
    _seen: dict[tuple, int] = {}   # ключ → индекс в _dedup_warnings
    _dedup_counts: list[int] = []
    _dedup_warnings: list[dict] = []
    for w in warnings:
        key = (w.get("kind"), w.get("name"), w.get("message"))
        if key in _seen:
            _dedup_counts[_seen[key]] += 1
        else:
            _seen[key] = len(_dedup_warnings)
            _dedup_warnings.append(dict(w))
            _dedup_counts.append(1)
    for i, cnt in enumerate(_dedup_counts):
        if cnt > 1:
            _dedup_warnings[i]["message"] = _dedup_warnings[i]["message"] + f" (строк: {cnt})"
    warnings = _dedup_warnings

    return {
        "created": created, "updated": updated, "skipped": skipped,
        "errors": errors, "warnings": warnings,
        "created_details": created_details,
        "updated_details": updated_details, "skipped_details": skipped_details,
        "dry_run": dry_run,
        "unmatched": unmatched,
        "new_paths": new_paths,
        "deleted_count": deleted_count,
        "relinked_count": relinked_count,
        "deleted_details": deleted_details,
        "remap_applied": remap_applied,
        "remap_aborted_reason": remap_aborted_reason,
        "version_created": version_created,
        "deletes_applied": bool(apply_remap),
    }
