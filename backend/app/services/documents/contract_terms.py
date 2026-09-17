"""Срок гарантии договора — человекочитаемый текст с единицей измерения.

Владелец (жалоба п.10, 2026-09-17): «Срок гарантии может быть в днях, в
месяцах, в годах. ... В документ должно уходить то, что выбрано словами
(«12 месяцев», «1 год», «30 дней»), а не пересчёт в дни.»

purchases.warranty_period_days хранит ЧИСЛО, введённое пользователем, а
purchases.warranty_period_unit — единицу ('days' | 'months' | 'years', NULL
у старых закупок трактуется как 'days'). Эта функция строит фразу с ПРАВИЛЬНЫМ
русским склонением по числу — единственное место, где это считается
(ПРАВИЛО №6); все контекст-билдеры документов (contexts_extra.py,
fabrikant_package.py) обязаны звать её, а не собирать текст сами.
"""
from typing import Optional


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Возвращает форму слова по числу n: 1 год / 2 года / 5 лет и т.п."""
    n_abs = abs(int(n))
    last_two = n_abs % 100
    last_one = n_abs % 10
    if 11 <= last_two <= 14:
        return many
    if last_one == 1:
        return one
    if 2 <= last_one <= 4:
        return few
    return many


_UNIT_WORDS = {
    "days": ("день", "дня", "дней"),
    "months": ("месяц", "месяца", "месяцев"),
    "years": ("год", "года", "лет"),
}


def warranty_period_text(value: Optional[int], unit: Optional[str]) -> str:
    """«1 год» / «2 года» / «5 лет» / «1 месяц» / «12 месяцев» / «30 дней».

    unit=None (старые закупки, заведённые до появления warranty_period_unit)
    трактуется как 'days' — сохраняет прежний смысл поля (число рабочих дней).
    value=None → пустая строка (гарантия не задана).
    """
    if value is None:
        return ""
    unit_key = unit if unit in _UNIT_WORDS else "days"
    one, few, many = _UNIT_WORDS[unit_key]
    word = _ru_plural(value, one, few, many)
    return f"{value} {word}"
