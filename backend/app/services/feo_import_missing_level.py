"""Импорт ФЭО: предупреждение «похоже, забыт уровень подкатегории».

Решение владельца 10.10.2026: программа НЕ угадывает и НЕ переносит данные —
только предупреждает, когда файл выглядит как типичная человеческая ошибка
«итог без названия подкатегории» (строка-итог суммы подкатегории осталась
без «Уровня N+1», а её позиции легли прямо в родительскую категорию).

Боевой пример (файл «ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx», лист «ДНРР»):
  стр.250  L3=«Расходы на приобретение основных средств…» L4=«Мебель»           ПП=«Столы для спикеров»        8000
  стр.251  L3 то же                                        L4 ПУСТО            ПП ПУСТО   Сумма плана 10954.41  (итог)
  стр.252  L3 то же                                        L4=«Бытовая техника» ПП=«Чайник электрический»     2762.92
  стр.253  L3 то же                                        L4 ПУСТО            ПП=«Чайник электрический»     1904.45
  стр.254  L3 то же                                        L4 ПУСТО            ПП=«Термопот»                 6287.04
2762.92+1904.45+6287.04 = 10954.41 (строка 251) — чайник и термопот должны
были лежать в «Бытовой технике», как чайник из строки 252, но у них не
указан «Уровень 4» — в GALA они легли прямо в «Расходы на приобретение
основных средств…».

Правило обнаружения (только внутри ОДНОЙ строки-итога R — из соседних строк
ничего не «подсматриваем» для определения её собственных уровней, только
для подтверждения суммы и факта, что у категории вообще есть подкатегории):

1. Строка R: «Плановая позиция» (Уровень 5) пуста, сумма плана S>0.
2. Самый глубокий ЗАПОЛНЕННЫЙ уровень R — k (2 или 3); если в R заполнен
   Уровень 4 — у неё и так нет уровня глубже, правило не применяется.
3. У категории k (тот же путь до неё) В ФАЙЛЕ ЕСТЬ хоть одна строка с
   заполненным уровнем k+1 — иначе сравнивать не с чем (категория вообще
   без подкатегорий), это не аномалия.
4. Берём строки, идущие СРАЗУ после R, с тем же путём до уровня k и с
   заполненной «Плановой позицией» (это и есть позиции категории k) —
   набираем подряд, пока их сумма не достигнет S (включая её).
5. Если сумма набранных строк совпала с S (±0,01) И среди них есть хотя бы
   одна с ПУСТЫМ уровнем k+1 → предупреждение. Если среди набранных ровно
   одна подкатегория названа — называем её в тексте как ожидаемое место.

Единственное место этой логики (Правило №6) — вызывается один раз из
`feo_import_apply.py` (`apply_rows`), использует только существующие
хелперы `feo_import_common.py` (format_rows/fmt/norm/level_label/get_cell/
row_plan_money) — своих копий форматирования/разбора ячеек не заводит.
"""
from app.services.feo_import_common import QUANT, ZERO, format_rows, get_cell, level_label, norm, row_plan_money
from app.services.feo_import_common import fmt as _fmt

KIND = "missing_level_hint"
_MAX_NAME_LEN = 70


def _short(name: str | None) -> str:
    """Обрезка длинного имени категории для читаемого текста предупреждения —
    тот же приём (срез + «…»), что уже используется в feo_import_apply.py
    (`_numeric_shift_scan`), отдельно не заводим второй формат обрезки."""
    s = (name or "").strip()
    if len(s) <= _MAX_NAME_LEN:
        return s
    return s[:_MAX_NAME_LEN].rstrip() + "…"


def _rows_word(nums: list[int], genitive: bool) -> str:
    """`format_rows` без слова впереди + склонение «строка/строки» (им.) или
    «строки/строк» (род.) — тонкая грамматическая обёртка над ОДНИМ источником
    форматирования номеров строк (`format_rows`), не второй список строк."""
    bare = format_rows(nums)
    for prefix in ("строки ", "строка "):
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    if genitive:
        word = "строки" if len(set(nums)) == 1 else "строк"
    else:
        word = "строка" if len(set(nums)) == 1 else "строки"
    return f"{word} {bare}"


def detect_missing_level_hints(
    rows,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
    c_lvl5: int | None,
    c_row_plan_sum: int | None,
    c_plan_sum_lvl2: int | None,
    c_plan_sum_lvl3: int | None,
    c_plan_sum_lvl4: int | None,
) -> list[dict]:
    if c_lvl2 is None:
        return []

    # --- Разбор строк файла в плоский список записей (один проход) ----------
    records = []
    for row_num, row in enumerate(rows, start=2):
        lvl2 = get_cell(row, c_lvl2)
        if lvl2 and lvl2.startswith("←"):
            continue  # служебная строка-подсказка — не данные
        lvl3 = get_cell(row, c_lvl3)
        lvl4 = get_cell(row, c_lvl4)
        lvl5 = get_cell(row, c_lvl5)
        plan_sum = row_plan_money(row, c_row_plan_sum, c_plan_sum_lvl2, c_plan_sum_lvl3, c_plan_sum_lvl4)
        records.append({
            "row_num": row_num, "lvl2": lvl2, "lvl3": lvl3, "lvl4": lvl4, "lvl5": lvl5,
            "plan_sum": plan_sum,
        })

    if not records:
        return []

    # --- Предпроход: где в файле ЕСТЬ подкатегории уровня 3/4 ----------------
    # level3_evidence[norm(lvl2)] -> категория 2 имеет хотя бы одну строку с
    # заполненным Уровнем 3 (сама подкатегория может быть позицией или итогом —
    # неважно, важен только факт, что уровень заполнен хоть где-то).
    level3_evidence: dict[str, bool] = {}
    # level4_evidence[(norm(lvl2), norm(lvl3))] -> та же идея для Уровня 4.
    level4_evidence: dict[tuple[str, str], bool] = {}
    for rec in records:
        if rec["lvl3"]:
            level3_evidence[norm(rec["lvl2"] or "")] = True
        if rec["lvl4"]:
            level4_evidence[(norm(rec["lvl2"] or ""), norm(rec["lvl3"] or ""))] = True

    warnings: list[dict] = []

    for i, rec in enumerate(records):
        if rec["lvl5"]:
            continue  # у строки своя «Плановая позиция» — это не итог категории
        S = rec["plan_sum"]
        if not S or S <= ZERO:
            continue

        if rec["lvl4"]:
            continue  # глубже Уровня 4 категорий не бывает — нет «следующего уровня»

        if rec["lvl3"]:
            k_next = 4
            path2, path3 = norm(rec["lvl2"] or ""), norm(rec["lvl3"])
            has_subcats = level4_evidence.get((path2, path3), False)
            path_name = rec["lvl3"]

            def _matches(nr, _p2=path2, _p3=path3):
                return norm(nr["lvl2"] or "") == _p2 and norm(nr["lvl3"] or "") == _p3

            def _next_level_value(nr):
                return nr["lvl4"]
        elif rec["lvl2"]:
            k_next = 3
            path2 = norm(rec["lvl2"])
            has_subcats = level3_evidence.get(path2, False)
            path_name = rec["lvl2"]

            def _matches(nr, _p2=path2):
                return norm(nr["lvl2"] or "") == _p2

            def _next_level_value(nr):
                return nr["lvl3"]
        else:
            continue  # строка-итог вообще без уровней — нечего сравнивать

        if not has_subcats:
            continue  # у категории нет подкатегорий в файле — не аномалия

        # --- Набираем строки-позиции сразу после R с тем же путём ----------
        acc = []
        acc_sum = ZERO
        j = i + 1
        while j < len(records):
            nr = records[j]
            if not _matches(nr) or not nr["lvl5"]:
                break
            acc.append(nr)
            acc_sum += (nr["plan_sum"] or ZERO)
            if acc_sum >= S - QUANT:
                break
            j += 1

        if not acc or abs(acc_sum - S) > QUANT:
            continue  # сумма не совпала — не наш случай (или пуст)

        missing = [r for r in acc if not _next_level_value(r)]
        if not missing:
            continue  # у всех набранных позиций уровень k+1 указан — всё в порядке

        named = {}
        for r in acc:
            v = _next_level_value(r)
            if v:
                named[norm(v)] = v
        subcat_part = f", а не в «{_short(next(iter(named.values())))}»" if len(named) == 1 else ""

        header_nums = [rec["row_num"]] + [r["row_num"] for r in missing]
        header = _rows_word(header_nums, genitive=False)
        header = header[0].upper() + header[1:]
        sum_phrase = _rows_word([r["row_num"] for r in acc], genitive=True)
        missing_phrase = _rows_word([r["row_num"] for r in missing], genitive=True)
        level_lbl = level_label(k_next)

        message = (
            f"{header}: похоже, забыт «{level_lbl}». "
            f"Итог {_fmt(S)} в строке {rec['row_num']} равен сумме {sum_phrase}, "
            f"но у {missing_phrase} подкатегория не указана — позиции попадут "
            f"прямо в «{_short(path_name)}»{subcat_part}. "
            f"Впишите «{level_lbl}» в файле и загрузите заново."
        )
        warnings.append({
            "kind": KIND,
            "row": rec["row_num"],
            "name": path_name,
            "message": message,
        })

    return warnings
