"""Часть объединённой плановой позиции в импорте факта (владелец,
12.10.2026, план merged-item-parts.md).

Плановая позиция, собранная загрузкой плана «Объединить в одну» (см.
feo_import_duplicates.py), несёт `parts` — состав исходных строк файла плана
(каждая часть = отдельная закупка, напр. «Gaz A22R35 Х920АЕ 180»: 317 400 +
20 000 + 10 000 + 5 000). При импорте факта строка файла, привязанная к такой
позиции, должна получить СВОЮ часть — чтобы «Проезд» 151 (407 184,10) и 152
(292 815,90) не слиплись в одну закупку с одним числом.

Правило выбора части (ЕДИНСТВЕННОЕ место, ПРАВИЛО №6 — preview.py и
commit.py читают его результат, не считают заново):
  1. Явный выбор человека (decisions.row_overrides[row].plan_part_key) —
     побеждает всегда.
  2. Иначе — точное совпадение (±0,01) суммы ПЛАНА строки файла с суммой
     части, среди частей, ещё НЕ занятых более ранней строкой ЭТОГО же
     прогона (assigned, см. build_preview). Несколько частей совпали —
     выбирается с наименьшим номером строки плана (part['row']).
  3. Не нашлось — part_key=None, человек должен выбрать часть вручную в
     колонке «Сопоставление» (warning). Решение «часть не выбрана» НЕ
     блокирует строку — закупка создаётся без части (безопаснее, чем
     заблокировать весь импорт из-за одной неоднозначной части; владелец
     не просил блокировать, см. план «Не делаем» — там запрещено только
     ручное редактирование состава, не создание закупки без части)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional


def resolve_row_plan_part(
    parts: list[dict],
    override_key: Optional[str],
    row_plan_amount,
    assigned: set[str],
) -> Optional[str]:
    """Возвращает key выбранной части или None (часть не определена —
    вызывающий код формирует предупреждение сам, текст зависит от места,
    где оно показывается)."""
    if override_key:
        return override_key
    if row_plan_amount is None:
        return None
    target = Decimal(str(row_plan_amount))
    candidates = [
        p for p in parts
        if p.get("key") not in assigned and p.get("amount") is not None
        and abs(Decimal(str(p["amount"])) - target) <= Decimal("0.01")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.get("row") if p.get("row") is not None else 0))
    return candidates[0]["key"]


def resolve_bound_row_part(
    parts: list[dict],
    bound_keys: set[str],
    row_plan_amount,
) -> Optional[str]:
    """Чек-лист 13.10.2026, п.2: когда `resolve_row_plan_part` не находит
    СВОБОДНУЮ часть по сумме строки (все точные совпадения уже заняты
    существующей закупкой — `bound_keys`, см. matching.py::ctx['bound_
    parts']), нужно отличить «строка 151 = уже закупленная часть 151» от
    «строка вообще не про эту позицию»: ищем точное совпадение (±0,01) среди
    ИМЕННО занятых частей. Вызывающий код (preview.py) переводит результат в
    match.state='already_purchased' — та же ветка «обновить существующую»,
    что и у обычной (без parts) позиции. Второе место сравнения сумм не
    заводим — та же точность ±0,01, что и в resolve_row_plan_part выше."""
    if row_plan_amount is None or not bound_keys:
        return None
    target = Decimal(str(row_plan_amount))
    for p in parts:
        key = p.get("key")
        if key not in bound_keys or p.get("amount") is None:
            continue
        if abs(Decimal(str(p["amount"])) - target) <= Decimal("0.01"):
            return key
    return None


def part_by_key(parts: list[dict], key: Optional[str]) -> Optional[dict]:
    if not key:
        return None
    return next((p for p in parts if p.get("key") == key), None)


def build_part_excess_warning(part: dict, fact_amount) -> Optional[str]:
    """«Факт больше плана части» — ДОПОЛНИТЕЛЬНО к общей проверке «факт
    больше плана позиции» (её не меняем, см. план), т.к. одна часть может
    быть превышена, даже когда сумма по ВСЕЙ позиции ещё в пределах плана
    (другие части недоизрасходованы)."""
    from app.services.historical_fact_import.plan_diff_warnings import _rub

    part_amount = part.get("amount")
    if part_amount is None or fact_amount is None:
        return None
    if Decimal(str(fact_amount)) <= Decimal(str(part_amount)) + Decimal("0.01"):
        return None
    row_label = part.get("row")
    return (
        f"Факт больше плана части: строка {row_label}, план {_rub(part_amount)}, "
        f"факт {_rub(fact_amount)}"
    )
