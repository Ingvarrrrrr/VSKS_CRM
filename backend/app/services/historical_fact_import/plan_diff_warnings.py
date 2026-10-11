"""Задача B (владелец, файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист ДНРР,
11.10.2026): два текста предупреждений мастера «Импорт факта», оба словами
владельца, а не внутренним языком согласования ТЗ.

1) build_file_plan_vs_gala_warning — план строки файла (кол-во/цена/сумма)
   отличается от плана СОПОСТАВЛЕННОЙ позиции GALA (боевой пример: строка 89
   «Бочка металлическая с насосом…» — в файле 4 × 5 500 = 22 000, в GALA
   1 × 22 000 = 22 000, сумма сошлась случайно, количество и цена — нет).

2) build_tz_excess_message — тот же случай, когда факт строки ПРЕВЫШАЕТ план
   GALA, даёт сработать app.services.tz_excess_approval.
   collect_tz_over_plan_violations. Её message написан для карточки
   заявки/закупки («ТЗ позиции… измените плановую позицию… или уменьшите
   ТЗ») — владелец этот текст не понял («у него в файле и так 4»). Здесь
   другой читатель (мастер импорта факта) и другое действие (план грузится
   заново, ТЗ не существует) — свой текст, но ОДНИ И ТЕ ЖЕ цифры:
   violation_details, добавленные ТАМ ЖЕ, где нарушение формируется
   (app.services.feo_plan_tz_checks.tz_over_plan_violations, ПРАВИЛО №6 —
   одна формула сравнения, два текста по разным читателям, message/reason
   исходной функции не меняются).

_rub/_fmt_qty — единственные форматтеры этих двух величин (ПРАВИЛО №6):
_rub оборачивает app.services.documents.formatting._fmt_money (тот же, что
commit.py/шаблоны документов используют), _fmt_qty — тот же формат «без
хвостовых нулей», что и app.services.feo_plan_tz_checks._fmt_qty (не вторая
копия округления).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services.documents.formatting import _fmt_money
from app.services.feo_plan_tz_checks import _fmt_qty as _fmt_qty_raw

_KIND_LABELS = {
    "qty": "количество",
    "unit_price": "цена за единицу",
    "amount": "сумма",
}


def _rub(v) -> str:
    formatted = _fmt_money(v)
    return f"{formatted} ₽" if formatted else "0,00 ₽"


def _fmt_qty(v) -> str:
    return _fmt_qty_raw(Decimal(str(v)))


def _close(a, b, eps: Decimal = Decimal("0.01")) -> bool:
    if a is None or b is None:
        return True  # нет данных для сравнения — сам по себе не расхождение
    return abs(Decimal(str(a)) - Decimal(str(b))) <= eps


def build_file_plan_vs_gala_warning(row_plan: dict, catalog_entry: dict) -> Optional[str]:
    """row_plan — {qty, price, amount} строки файла (rows.py), catalog_entry —
    запись каталога сопоставленной плановой позиции (plan_catalog.py:
    quantity/unit_price/amount). Сравнение возможно только когда количество И
    цена заданы с ОБЕИХ сторон (иначе «1 × 22 000 = 22 000» не построить) —
    не пытаемся угадывать частичное сравнение."""
    f_qty, f_price, f_amount = row_plan.get("qty"), row_plan.get("price"), row_plan.get("amount")
    g_qty, g_price, g_amount = catalog_entry.get("quantity"), catalog_entry.get("unit_price"), catalog_entry.get("amount")
    if f_qty is None or f_price is None or g_qty is None or g_price is None:
        return None

    differs = (
        not _close(f_qty, g_qty)
        or not _close(f_price, g_price)
        or not _close(f_amount, g_amount)
    )
    if not differs:
        return None

    g_total = g_amount if g_amount is not None else (Decimal(str(g_qty)) * Decimal(str(g_price)))
    f_total = f_amount if f_amount is not None else (Decimal(str(f_qty)) * Decimal(str(f_price)))
    return (
        "План в файле отличается от плана в GALA: в GALA "
        f"{_fmt_qty(g_qty)} × {_rub(g_price)} = {_rub(g_total)}, в файле "
        f"{_fmt_qty(f_qty)} × {_rub(f_price)} = {_rub(f_total)}. "
        "Факт сравнивается с планом GALA — если в файле план верный, загрузите план (ФЭО) заново."
    )


def build_tz_excess_message(violation_details: list) -> str:
    """«Факт больше плана GALA: …» — словами владельца, из violation_details
    (kind/planned/actual/diff), без «ТЗ позиции…»/«уменьшите ТЗ». Если
    единственное нарушение — количество (сумма факта в пределах плана GALA
    по построению: amount не мог бы нарушиться при nonviolated amount),
    добавляется «…сумма в пределах плана»."""
    parts = []
    for d in violation_details:
        kind = d["kind"]
        label = _KIND_LABELS.get(kind, kind)
        if kind == "qty":
            planned, actual, diff = _fmt_qty(d["planned"]), _fmt_qty(d["actual"]), _fmt_qty(d["diff"])
        else:
            planned, actual, diff = _rub(d["planned"]), _rub(d["actual"]), _rub(d["diff"])
        parts.append(f"{label} — в плане {planned}, в строке {actual} (больше на {diff})")

    text = "Факт больше плана GALA: " + "; ".join(parts) if parts else "Факт больше плана GALA"
    if len(violation_details) == 1 and violation_details[0]["kind"] == "qty":
        text += "; сумма в пределах плана"
    return text
