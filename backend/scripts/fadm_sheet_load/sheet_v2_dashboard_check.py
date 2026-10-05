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
    # Владелец, дополнение 05.10.2026 (п.3) — «Подтверждено выпиской»
    # (Payment.confirmed_by_statement=True, 115 платежей выписки); без
    # разбивки товары/услуги — владелец дал только общую сумму.
    "paid_confirmed": (Decimal("8848230.38"), None, None),
    "delivered_unpaid": (Decimal("2227264.89"), Decimal("130821.29"), Decimal("2096443.60")),
    "future_monthly": (Decimal("373611.40"), Decimal("0"), Decimal("373611.40")),
    "future_likely": (Decimal("1838000.00"), Decimal("100000.00"), Decimal("1738000.00")),
    "future_nice": (Decimal("1019355.79"), Decimal("469355.79"), Decimal("550000.00")),
}


def _f(v) -> Decimal:
    return Decimal(str(v or 0))


async def debug_unspecified_work_rows(db: AsyncSession, current_user, subsidy_id: int) -> str:
    """Диагностика (владелец, доп. правка 05.10.2026, п.2) — построчно, какие
    закупки субсидии дают «без типа» в этапе «work» (compute_type_split_detail,
    ТА ЖЕ функция, что и дашборд — не вторая формула). Только для отчёта
    загрузчика, в БД ничего не пишет."""
    from app.auth.visibility import get_visible_subsidy_ids
    from app.routers.dashboard import _apply_purchase_org_filter
    from app.services.dashboard_type_split import compute_type_split_detail

    visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db, "dashboard")
    detail = await compute_type_split_detail(
        db, apply_filter=lambda q: _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids),
        use_sids=True, visible_subsidy_ids=visible_subsidy_ids, org_ids=None, stage="work",
    )
    from app.models.purchase import Purchase
    bad_rows = [r for r in detail["rows"] if r["kind"] == "unspecified" and r["amount"]]
    purchase_ids = {r["purchase_id"] for r in bad_rows if r.get("purchase_id")}
    purchases = {}
    if purchase_ids:
        rows = (await db.execute(
            select(Purchase).where(Purchase.id.in_(purchase_ids), Purchase.subsidy_id == subsidy_id)
        )).scalars().all()
        purchases = {p.id: p for p in rows}
    lines = [f"=== Без типа в «work» — построчно (compute_type_split_detail) ==="]
    total = Decimal("0")
    for r in bad_rows:
        p = purchases.get(r.get("purchase_id"))
        if p is None:
            continue
        total += _f(r["amount"])
        lines.append(f"  purchase#{p.id} статус={p.status} тип_договора={p.purchase_contract_type} "
                     f"родитель={p.parent_purchase_id} subject={p.subject!r} "
                     f"сумма_без_типа={_f(r['amount'])} item_name={r.get('item_name')!r}")
    lines.append(f"Σ без типа (эта субсидия): {total}")
    return "\n".join(lines)


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


def render_dashboard_comparison(stats: dict, paid_statement_total: Decimal,
                                 future_monthly_total: Decimal = Decimal("0")) -> str:
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
    # Задание владельца 05.10.2026, п.3 — «Оплачено по отметке» (AW, см.
    # sheet_v2_payments.py::create_declared_payments_for_paid_rows) обязано
    # сойтись с BD листа (товары/услуги); «подтверждено выпиской» — тот же
    # контроль, но до загрузки выписки должен быть 0 (ПРАВИЛО №6 — оба поля
    # из dashboard_charts.py::subsidy_stats, см. app/services/
    # subsidy_paid_breakdown.py, не вторая формула здесь).
    declared_by_kind = stats.get("paid_declared_by_kind") or {}
    row("Оплачено по отметке", stats.get("paid_declared"),
        declared_by_kind.get("goods"), declared_by_kind.get("services"), "paid_statement")
    confirmed_by_kind = stats.get("paid_confirmed_by_kind") or {}
    row("Подтверждено выпиской", stats.get("paid_confirmed"),
        confirmed_by_kind.get("goods"), confirmed_by_kind.get("services"), "paid_confirmed")
    du_w = stats.get("widget", {}).get("delivered_unpaid", {})
    row("Поставлено, не оплачено", du_w.get("amount"), None, None, "delivered_unpaid")
    # Решение владельца 05.10.2026 (5-я доп. правка): «ещё не заказано —
    # ежемесячные» (BA) — это НЕ плановая позиция (not_committed_likely мешает
    # BA с BB «скорее всего») — BA уже реальные будущие заказы СВОИХ рамочных
    # договоров (status='contracted', не "план"). Сверяем Σ BA НАПРЯМУЮ по
    # листу (future_monthly_total, считает вызывающий код из SheetRowV2 —
    # ОДИН источник, не вторая формула: то же monthly_ba, что уже парсит
    # sheet_v2_parse.py), а не через dashboard-метрику, которой для такой
    # величины просто нет штатного поля.
    row("Ещё не заказано: ежемесячные (BA, Σ по листу)", future_monthly_total, None, None, "future_monthly")

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
