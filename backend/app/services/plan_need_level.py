"""plan_need_level.py — статус «нужности» плановой позиции (FeoPlannedItem.
need_level), владелец 04.10.2026, план .planning/quick/2026-10-04-sheet-ideas.

ЕДИНСТВЕННОЕ место констант/подписей (ПРАВИЛО №6) — ничто другое в проекте не
заводит свой список значений need_level или свой текст подписи.

  'likely'       — «Скорее всего понадобится» (умолчание; ВСЕ позиции,
                    заведённые до этого поля, трактуются так же — см.
                    server_default миграции p1q3r5s7t9v1).
  'nice_to_have' — «Хотелось бы, но можно и отказаться».

Заявки (Wish) и позиции закупок БЕЗ привязанной плановой позиции формально не
имеют need_level — вызывающий код (compute_feo_plan_tree, Задача 2) трактует
такой «безхозный» остаток плана как 'likely' (см. docstring там), эта
трактовка — НЕ значение колонки, отдельное решение на месте использования.
"""

NEED_LEVEL_LIKELY = "likely"
NEED_LEVEL_NICE_TO_HAVE = "nice_to_have"

NEED_LEVELS: tuple = (NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE)

NEED_LEVEL_LABELS: dict = {
    NEED_LEVEL_LIKELY: "Скорее всего понадобится",
    NEED_LEVEL_NICE_TO_HAVE: "Хотелось бы, но можно и отказаться",
}


def normalize_need_level(value) -> str:
    """Валидация/нормализация значения need_level на входе (роутер/сервис).
    Пусто/неизвестное значение → умолчание 'likely' (то же поведение, что и
    у существующих позиций без этого поля, см. docstring модуля)."""
    if value in NEED_LEVELS:
        return value
    return NEED_LEVEL_LIKELY
