"""Проверка «количество × цена = сумма» при импорте позиций закупки —
единый источник (Правило №6). Раньше такой проверки не было ни в одном из
путей импорта позиций (обычный/с маппингом/умный), только у импорта ФЭО
(`feo_import_apply.py`, warning kind="sum_mismatch") — оттуда взяты допуск
на копейку и текст предупреждения, второй вариант не изобретаем.

Владелец (2026-09-14): позиция закупки id=3166 «5 шт по 99 990» была молча
сохранена с суммой 499.95 вместо 499 950 (см. также app/utils/numbers.py) —
импорт обязан УВИДЕТЬ такое расхождение и спросить пользователя, что
оставить, а не тихо взять то, что написано в файле. В отличие от импорта
ФЭО (который при расхождении молча берёт сумму из файла и только
предупреждает), здесь пользователь выбирает сам — см. `resolve_qty_price_choice`.

Расчёт суммы делается через `item_amounts.line_total` (Правило №6 — тот же
источник, что пишет `total_price` у обычной позиции везде в проекте), а не
повторным `quantity * unit_price` по месту.
"""
from decimal import Decimal
from typing import Optional

from app.services.item_amounts import line_total
from app.services.feo_import_common import fmt as _fmt

TOLERANCE = Decimal("0.01")


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return None


def check_qty_price_sum(row_num, name: str, quantity, unit_price, total_price) -> Optional[dict]:
    """Если в строке заданы ВСЕ ТРИ значения (количество, цена, сумма) и
    кол-во × цена расходится с суммой из файла больше, чем на копейку —
    вернуть warning-словарь {kind, row, name, message, file_total,
    calc_total}. Если хоть одного значения нет — тишина (это не дефект
    строки, а просто «сумма»/«цена» не заполнена файлом)."""
    q, p, t = _dec(quantity), _dec(unit_price), _dec(total_price)
    if q is None or p is None or t is None:
        return None
    calc = line_total(q, p)
    if abs(calc - t) <= TOLERANCE:
        return None
    return {
        "kind": "sum_mismatch",
        "row": row_num,
        "name": name,
        "message": f"Сумма {_fmt(t)} ≠ кол-во × цена = {_fmt(calc)}",
        "file_total": float(t),
        "calc_total": float(calc),
    }


def resolve_qty_price_choice(quantity, unit_price, total_price, choice: Optional[str]):
    """Применяет выбор пользователя к расхождению кол-во × цена ≠ сумма:
      - 'recalc_sum'   — сумма = кол-во × цена (в файле ошиблись в сумме);
      - 'recalc_price' — цена = сумма / кол-во (в файле ошиблись в цене);
      - 'keep' / None  — оставить как в файле, ничего не менять.
    Возвращает (unit_price, total_price). Молчаливого третьего поведения
    нет — при отсутствии данных, нужных для пересчёта, значения остаются
    как были переданы (вызывающий код не должен трактовать это как выбор
    'keep', см. вызовы ниже по стеку)."""
    if choice == "recalc_sum":
        q, p = _dec(quantity), _dec(unit_price)
        if q is not None and p is not None:
            return unit_price, line_total(q, p)
    elif choice == "recalc_price":
        q, t = _dec(quantity), _dec(total_price)
        if q not in (None, Decimal(0)) and t is not None:
            return (t / q).quantize(TOLERANCE), total_price
    return unit_price, total_price
