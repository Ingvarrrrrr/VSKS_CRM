"""plan_need_level.py — статус «нужности» плановой позиции (FeoPlannedItem.
need_level), владелец 04.10.2026, план .planning/quick/2026-10-04-sheet-ideas;
🟡 третий вариант добавлен 16.10.2026 (план composed-noodling-lampson.md,
импорт GoodsService, колонка AU «Непредвиденные расходы»).

🟢 Правка (16.10.2026, та же задача): лист владельца GoodsService в колонке
AU использует свободный текст, не совпадающий буквально с подписями ниже —
см. NEED_LEVEL_TEXT_SYNONYMS и resolve_need_level_text(). ЕДИНСТВЕННОЕ место
этого словаря (Правило №6) — feo_import_common.py (парсер импорта ФЭО) зовёт
resolve_need_level_text(), а не заводит свою копию синонимов.

ЕДИНСТВЕННОЕ место констант/подписей (ПРАВИЛО №6) — ничто другое в проекте не
заводит свой список значений need_level, свой текст подписи, или свою копию
правила «что считается резервом в денежных итогах».

  'likely'       — «Скорее всего понадобится» (умолчание; ВСЕ позиции,
                    заведённые до этого поля, трактуются так же — см.
                    server_default миграции p1q3r5s7t9v1).
  'nice_to_have' — «Хотелось бы, но можно и отказаться».
  'unforeseen'   — 🟡 «Непредвиденные расходы» (лист GoodsService, колонка AU
                    = «Непредвиденные расходы», сумма в BC). В ДЕНЕЖНЫХ
                    ИТОГАХ (committed_amounts, redistributable_raw,
                    stage_cumulative, subsidy_summary_by_kind, feo_plan_tree,
                    metric_drill_rows, plan_funding_sources, dashboard_charts)
                    трактуется ТАК ЖЕ, как 'nice_to_have' — резерв, который
                    можно перераспределить. Используйте RESERVE_NEED_LEVELS /
                    is_reserve_need_level() ниже, а не копию списка/сравнения.

Заявки (Wish) и позиции закупок БЕЗ привязанной плановой позиции формально не
имеют need_level — вызывающий код (compute_feo_plan_tree, Задача 2) трактует
такой «безхозный» остаток плана как 'likely' (см. docstring там), эта
трактовка — НЕ значение колонки, отдельное решение на месте использования.
"""

NEED_LEVEL_LIKELY = "likely"
NEED_LEVEL_NICE_TO_HAVE = "nice_to_have"
NEED_LEVEL_UNFORESEEN = "unforeseen"

NEED_LEVELS: tuple = (NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE, NEED_LEVEL_UNFORESEEN)

# 🟡 Значения, которые в ДЕНЕЖНЫХ ИТОГАХ считаются резервом (как
# 'nice_to_have') — единственное место этого списка, см. докстринг модуля.
RESERVE_NEED_LEVELS: frozenset = frozenset({NEED_LEVEL_NICE_TO_HAVE, NEED_LEVEL_UNFORESEEN})

NEED_LEVEL_LABELS: dict = {
    NEED_LEVEL_LIKELY: "Скорее всего понадобится",
    NEED_LEVEL_NICE_TO_HAVE: "Хотелось бы, но можно и отказаться",
    NEED_LEVEL_UNFORESEEN: "Непредвиденные расходы",
}


import re


def _collapse_ws(s: str) -> str:
    """Несколько пробелов/NBSP -> один; пробел перед знаком пунктуации убран
    (лист владельца содержит «поставлено , но  будет» — пробелы вразнобой)."""
    s = re.sub(r"\s+", " ", s.strip())
    return re.sub(r"\s+([,.;:])", r"\1", s)


# 🟢 Правка (16.10.2026): свободный текст колонки AU листа GoodsService ->
# код need_level. Ключи — уже нормализованные через _collapse_ws().lower().
# «Да» и «Еще не поставлено, но будет.Ежемесячная услуга» — по решению
# владельца это уже законтрактованное/нужное, т.е. 'likely'.
NEED_LEVEL_TEXT_SYNONYMS: dict[str, str] = {
    "скорее всего поставка потребуется": NEED_LEVEL_LIKELY,
    "да": NEED_LEVEL_LIKELY,
    "еще не поставлено, но будет.ежемесячная услуга": NEED_LEVEL_LIKELY,
}


def resolve_need_level_text(value) -> str | None:
    """Текст ячейки (код / русская подпись NEED_LEVEL_LABELS / синоним листа
    владельца NEED_LEVEL_TEXT_SYNONYMS) -> код need_level. Пустое значение ->
    NEED_LEVEL_LIKELY. Нераспознанное -> None (вызывающий код сам решает, что
    делать с ошибкой — см. feo_import_apply.py). ЕДИНСТВЕННОЕ место разбора
    свободного текста "Нужности" (Правило №6)."""
    if value is None:
        return NEED_LEVEL_LIKELY
    s = _collapse_ws(str(value))
    if not s:
        return NEED_LEVEL_LIKELY
    s_low = s.lower()
    if s_low in NEED_LEVELS:
        return s_low
    for code, label in NEED_LEVEL_LABELS.items():
        if _collapse_ws(label).lower() == s_low:
            return code
    return NEED_LEVEL_TEXT_SYNONYMS.get(s_low)


def normalize_need_level(value) -> str:
    """Валидация/нормализация значения need_level на входе (роутер/сервис).
    Пусто/неизвестное значение → умолчание 'likely' (то же поведение, что и
    у существующих позиций без этого поля, см. docstring модуля)."""
    if value in NEED_LEVELS:
        return value
    return NEED_LEVEL_LIKELY


def is_reserve_need_level(value) -> bool:
    """🟡 True для 'nice_to_have' И 'unforeseen' — ЕДИНСТВЕННОЕ место, где
    решается, какие need_level трактуются как резерв в денежных итогах
    (ПРАВИЛО №6). Вызывающий денежный код сравнивает через эту функцию, а не
    через `== NEED_LEVEL_NICE_TO_HAVE`."""
    return value in RESERVE_NEED_LEVELS
