"""economy_preview.py — «экономия видна», а не происходит молча (владелец,
правка 12.10.2026, план lazy-swimming-hollerith.md, п.4б): строка импорта
факта, которая ПОСЛЕ загрузки наберёт количество плановой позиции ЦЕЛИКОМ
дешевле плана (пример владельца — «Haval Dargo Р937ХУ 180»: план 25 000,00,
заказано одной строкой 8 826,23), получает явное предупреждение «Экономия
16 173,77 ₽: …», и это же число попадает в totals.economy шага предпросмотра.

ПРАВИЛО №6 — формула замещения «заказ вместо плана» НЕ повторяется здесь:
используется ТА ЖЕ единственная точка _order_substituted_plan
(app.services.feo_plan_common), что считает и дерево ФЭО
(compute_feo_plan_tree._own_plan_and_forecast), и find_excess_culprit —
план позиции замещается суммой заказа, когда planned_quantity > 0 и
ordered_qty (уже заказано в БД + количество ЭТОЙ строки) ≥ planned_quantity.

Данные «уже заказано» берутся из app.services.feo_plan_fact.
planned_item_consumption (тот же источник used/used_qty, что
/feo-planned-items/residuals и /feo-categories/plan-positions, ПРАВИЛО №6 —
второй запрос по PurchaseItem не заводится).

Известное ограничение (сознательно, ради срока): если ПОЛНОЕ количество
позиции набирается несколькими строками ОДНОГО импорта (а не одной строкой,
как в примере владельца), экономия сработает только на строке, после которой
already_ordered (из БД, без учёта более ранних строк ЭТОГО ЖЕ прогона) впервые
достигает planned_quantity — build_preview вызывает эту функцию в порядке
строк файла, поэтому на практике это последняя из них.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services.feo_plan_common import _order_substituted_plan
from app.services.historical_fact_import.plan_diff_warnings import _rub

_CENTS = Decimal("0.01")


def build_order_substitution_economy(
    *,
    planned_qty: Optional[float],
    planned_amount: Optional[float],
    already_ordered_qty: float,
    already_ordered_sum: float,
    row_qty: Optional[float],
    row_amount: Optional[float],
    planned_item_name: str,
) -> Optional[dict]:
    """None — нет новой экономии от ЭТОЙ строки. Иначе {message, amount,
    new_plan} — amount/new_plan это Decimal, округлённые до копеек."""
    if not planned_qty or planned_qty <= 0:
        return None
    if already_ordered_qty >= planned_qty:
        return None  # уже набрано ДО этой строки — не её заслуга, предупреждение не дублируем
    if not row_qty or row_qty <= 0:
        return None

    new_ordered_qty = already_ordered_qty + float(row_qty)
    if new_ordered_qty < planned_qty:
        return None  # эта строка не доводит количество позиции до плана целиком

    new_ordered_sum = already_ordered_sum + float(row_amount or 0)
    plan_manual = Decimal(str(planned_amount or 0))
    new_plan = Decimal(str(_order_substituted_plan(
        planned_qty, new_ordered_sum, new_ordered_qty, float(plan_manual),
    ))).quantize(_CENTS)
    economy = (plan_manual - new_plan).quantize(_CENTS)
    if economy <= 0:
        return None

    message = (
        f"Экономия {_rub(economy)}: план позиции «{planned_item_name}» {_rub(plan_manual)}, "
        f"заказано {_rub(new_plan)} — после загрузки план позиции станет {_rub(new_plan)}, "
        "разница вернётся в свободные деньги категории"
    )
    return {"message": message, "amount": economy, "new_plan": new_plan}


def build_order_substitution_overspend(
    *,
    planned_qty: Optional[float],
    planned_amount: Optional[float],
    already_ordered_qty: float,
    already_ordered_sum: float,
    row_qty: Optional[float],
    row_amount: Optional[float],
    planned_item_name: str,
) -> Optional[dict]:
    """Зеркало build_order_substitution_economy (владелец, задача 13.10.2026,
    «перерасход показывать так же, как экономию») — ОДНА И ТА ЖЕ точка
    _order_substituted_plan (ПРАВИЛО №6, второй формулы нет), только
    противоположный знак разницы: когда количество позиции набрано ЦЕЛИКОМ
    ЭТОЙ строкой И договор/заказ ДОРОЖЕ плана позиции, план позиции молча
    вырастет (заменится суммой заказа) — здесь это становится явным
    предупреждением «Перерасход …», а не тихим ростом «Запланировано».

    None — нет нового перерасхода от ЭТОЙ строки. Иначе {message, amount,
    new_plan} — amount/new_plan это Decimal, округлённые до копеек."""
    if not planned_qty or planned_qty <= 0:
        return None
    if already_ordered_qty >= planned_qty:
        return None  # уже набрано ДО этой строки — не её заслуга
    if not row_qty or row_qty <= 0:
        return None

    new_ordered_qty = already_ordered_qty + float(row_qty)
    if new_ordered_qty < planned_qty:
        return None  # эта строка не доводит количество позиции до плана целиком

    new_ordered_sum = already_ordered_sum + float(row_amount or 0)
    plan_manual = Decimal(str(planned_amount or 0))
    new_plan = Decimal(str(_order_substituted_plan(
        planned_qty, new_ordered_sum, new_ordered_qty, float(plan_manual),
    ))).quantize(_CENTS)
    overspend = (new_plan - plan_manual).quantize(_CENTS)
    if overspend <= 0:
        return None

    message = (
        f"Перерасход {_rub(overspend)}: план позиции «{planned_item_name}» {_rub(plan_manual)}, "
        f"договор {_rub(new_plan)} — разница пойдёт в «Запланировано» как перерасход по заказам"
    )
    return {"message": message, "amount": overspend, "new_plan": new_plan}
