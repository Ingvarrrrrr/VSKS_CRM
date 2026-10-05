"""Карточки GALA ДО записи (задание 05.10.2026, доп. п.5) — ЕДИНЫЙ источник
(ПРАВИЛО №6): штатный роутер GET /api/dashboard/charts (app/routers/
dashboard_charts.py::dashboard_charts) вызывается НАПРЯМУЮ как обычная
async-функция (db/current_user — уже открытая сессия и выбранный пользователь
этого загрузчика, остальные параметры — Query(...) со значениями по
умолчанию) — та же функция, что отдаёт фронту, НЕ вторая формула карточек
здесь. Вызывается ВНУТРИ той же транзакции, ДО commit/rollback — у --dry-run
отчёт покажет то же, что увидел бы владелец на дашборде после реальной записи.

Контрольные числа — лист «Дашборд» + сводная шапка GoodsService (план
sleepy-fluttering-walrus.md, таблица «Контрольные числа»).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CONTROL = {
    "budget": (Decimal("15880100.00"), Decimal("4380000.00"), Decimal("11500100.00")),
    "planned": (Decimal("15880100.00"), Decimal("3348602.80"), Decimal("12531497.20")),
    "ordered": (Decimal("12649132.81"), Decimal("2779247.01"), Decimal("9869885.80")),
    "delivered": (Decimal("12464098.81"), Decimal("2599247.01"), Decimal("9864851.80")),
    "paid_statement": (Decimal("10236833.92"), Decimal("2468425.72"), Decimal("7768408.20")),
    "delivered_unpaid": (Decimal("2227264.89"), Decimal("130821.29"), Decimal("2096443.60")),
    "future_monthly": (Decimal("373611.40"), Decimal("0"), Decimal("373611.40")),
    "future_likely": (Decimal("1838000.00"), Decimal("100000.00"), Decimal("1738000.00")),
    "future_nice": (Decimal("1019355.79"), Decimal("469355.79"), Decimal("550000.00")),
}


def _f(v) -> Decimal:
    return Decimal(str(v or 0))


async def compute_subsidy_dashboard_stats(db: AsyncSession, current_user, subsidy_id: int) -> dict:
    """Вызов штатного роутера напрямую (см. докстринг модуля). scope="dashboard"
    — тот же режим видимости, что у вкладки «Дашборд» владельца."""
    from app.routers.dashboard_charts import dashboard_charts

    payload = await dashboard_charts(db=db, current_user=current_user, scope="dashboard", type_split=True)
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise ValueError(f"Субсидия id={subsidy_id} не найдена в /api/dashboard/charts (видимость/фильтр?)")


async def paid_by_statement(db: AsyncSession, subsidy_id: int) -> Decimal:
    """«Оплачено по выписке» — сверка (Σ привязанных Payment), отдельно от
    штатной карточки «Оплачено» (та наполняется подтверждением согласующих,
    задание/план, раздел «Контрольные числа», последняя строка)."""
    from app.models.payment import Payment
    from app.models.purchase import Purchase

    rows = (await db.execute(
        select(Payment.amount).join(Purchase, Payment.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy_id)
    )).scalars().all()
    return sum((_f(a) for a in rows), Decimal("0"))


def render_dashboard_comparison(stats: dict, paid_statement_total: Decimal) -> str:
    lines = []
    lines.append("=== Карточки GALA vs лист (ДО записи, /api/dashboard/charts) ===")
    lines.append("")

    def row(label: str, key_total, key_goods=None, key_services=None, control_key=None):
        total = _f(key_total)
        goods = _f(key_goods) if key_goods is not None else None
        services = _f(key_services) if key_services is not None else None
        c_total, c_goods, c_services = CONTROL.get(control_key, (None, None, None))
        diff = (total - c_total) if c_total is not None else None
        mark = "OK" if diff is not None and abs(diff) < Decimal("1") else ("?" if diff is None else "РАСХОЖДЕНИЕ")
        lines.append(f"{label}: лист {c_total} / GALA {total} / разница {diff} [{mark}]")
        if goods is not None:
            lines.append(f"    товары: лист {c_goods} / GALA {goods} / разница {(goods - c_goods) if c_goods is not None else '?'}")
        if services is not None:
            lines.append(f"    услуги: лист {c_services} / GALA {services} / разница {(services - c_services) if c_services is not None else '?'}")

    row("Бюджет (ФЭО)", stats.get("feo_budget_total"), stats.get("budget_goods"), stats.get("budget_services"), "budget")
    row("Запланировано", stats.get("planned_tree"), stats.get("planned_goods"), stats.get("planned_services"), "planned")
    ordered_w = stats.get("widget", {}).get("ordered", {})
    row("Заказано", ordered_w.get("amount"), ordered_w.get("ordered_goods"), ordered_w.get("ordered_services"), "ordered")
    delivered_w = stats.get("widget", {}).get("delivered", {})
    row("Поставлено", delivered_w.get("amount"), delivered_w.get("delivered_goods"), delivered_w.get("delivered_services"), "delivered")
    row("Оплачено по выписке (сверка)", paid_statement_total, None, None, "paid_statement")
    du_w = stats.get("widget", {}).get("delivered_unpaid", {})
    row("Поставлено, не оплачено", du_w.get("amount"), None, None, "delivered_unpaid")
    row("Ещё не заказано: ежемесячные", stats.get("not_committed_likely"), None, None, "future_monthly")

    lines.append("")
    lines.append(f"«Заключено договоров» (widget.contracts): {_f(stats.get('widget', {}).get('contracts', {}).get('amount'))}")
    contracts_ge_ordered = _f(stats.get("widget", {}).get("contracts", {}).get("amount")) >= _f(ordered_w.get("amount")) - Decimal("1")
    lines.append(f"  Заключено >= Заказано: {'OK' if contracts_ge_ordered else 'НАРУШЕНО'}")

    work_amt = _f(stats.get("total_work"))
    planned_amt = _f(stats.get("planned_tree"))
    work_le_planned = work_amt <= planned_amt + Decimal("1")
    lines.append(f"«Ведётся работа» {work_amt} vs «Запланировано» {planned_amt}: "
                 f"{'OK' if work_le_planned else 'НАРУШЕНО (закупки сверх плана)'}")

    work_w = stats.get("widget", {}).get("work", {})
    unspecified_bits = [
        _f(work_w.get("work_unspecified")), _f(ordered_w.get("ordered_unspecified")),
        _f(delivered_w.get("delivered_unspecified")), _f(stats.get("planned_unspecified")),
    ]
    no_unspecified = all(abs(v) < Decimal("1") for v in unspecified_bits)
    lines.append(f"«Без типа» (work/ordered/delivered/planned) = {unspecified_bits}: "
                 f"{'OK (все 0)' if no_unspecified else 'НАРУШЕНО'}")

    return "\n".join(lines)
