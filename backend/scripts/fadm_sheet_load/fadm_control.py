"""Единый источник контрольных чисел листа GoodsService (ПРАВИЛО №6).

До этого файла одни и те же суммы (план/заказано/поставлено/оплачено,
разбивка товары/услуги) были прописаны по отдельности в
sheet_v2_dashboard_check.py::CONTROL, sheet_v2_report.py::CONTROL_TOTALS и
report_common.py::EXPECTED_TOTALS — три копии одного показателя, которые
при правке листа владельцем обновлялись бы вразнобой (ровно как описано в
CLAUDE.md, ПРАВИЛО №6). Теперь все три модуля читают отсюда.

Обновлено 06.10.2026 — владелец поправил лист GoodsService (АльфаСтрахование,
Цыганов и др.), контрольные числа сводной шапки пересчитались.

Формат: ключ -> (total, goods, services). goods/services = None там, где
владелец дал только общую сумму (не додумывать разбивку по старому
соотношению — см. feedback_single_source_of_truth / ПРАВИЛО №6)."""
from __future__ import annotations

from decimal import Decimal

SHEET_CONTROL: dict[str, tuple[Decimal, Decimal | None, Decimal | None]] = {
    "budget": (Decimal("15880100.00"), Decimal("4380000.00"), Decimal("11500100.00")),
    "planned": (Decimal("15880100.00"), Decimal("3336612.66"), Decimal("12543487.34")),
    "ordered": (Decimal("12672993.55"), Decimal("2779247.01"), Decimal("9893746.54")),
    "delivered": (Decimal("12487959.55"), Decimal("2599247.01"), Decimal("9888712.54")),
    "paid_statement": (Decimal("10216748.46"), Decimal("2468425.72"), Decimal("7748322.74")),
    # Владелец, дополнение 05.10.2026 (п.3) — «Подтверждено выпиской»
    # (Payment.confirmed_by_statement=True, 115 платежей выписки); без
    # разбивки товары/услуги — владелец дал только общую сумму.
    "paid_confirmed": (Decimal("8848230.38"), None, None),
    "delivered_unpaid": (Decimal("2227264.89"), Decimal("130821.29"), Decimal("2096443.60")),
    # Ежемесячные/выдуманные — владелец 06.10.2026 дал только общую сумму.
    "future_monthly": (Decimal("361740.80"), None, None),
    "future_likely": (Decimal("1838000.00"), Decimal("100000.00"), Decimal("1738000.00")),
    "future_nice": (Decimal("1007365.65"), None, None),
    # AT «Договор» — новой цифры от владельца 06.10.2026 не было, оставлено
    # прежним (сходится с расчётом из CSV, см. дашборд-сверку загрузчика).
    "contracted": (Decimal("13652744.21"), None, None),
}
