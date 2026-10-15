"""subsidy_summary_by_kind.py — Задача А экспорта плана-графика (владелец
07.10.2026): лист «Сводная» больше не считает свои собственные корзины
(summary/_empty_summary_buckets в plan_graph_export_data.py — удалены), а
читает уже посчитанные числа из функций, которые показывает сам экран
субсидии (ПРАВИЛО №6 — ни одна сумма здесь не пересчитывается заново):

  feo/plan      — app.services.type_totals.subsidy_type_totals
                  (feo_{kind}/plan_{kind} по корневым узлам дерева ФЭО).
  committed     — app.services.subsidy_money_summary.subsidy_money_summary
                  ["committed_by_kind"] («Заказано» на экране субсидии).
  monthly/likely/nice — ВСЕ ТРИ из ОДНОГО прохода по
                  app.services.redistributable_raw.not_committed_raw_rows
                  (ИЗМЕНЕНО 15.10.2026, план abstract-noodling-pelican.md,
                  п.C — раньше «monthly» читался отдельно из
                  app.services.stage_cumulative.contracted_not_ordered_
                  split_by_kind, который не знает о месяце заказа; теперь
                  not_committed_raw_rows САМА помечает флагом
                  `monthly_future_not_started` строки, чей заказ рамочного
                  договора ещё не начал свой месяц — читаем этот флаг, вторая
                  формула не нужна, см. докстринг not_committed_raw_rows).
  paid          — app.services.subsidy_paid_breakdown.paid_breakdown_by_subsidy
                  ["declared_by_kind"] («Оплачено по отметке»); payroll там не
                  считается (нет such корзины в этом модуле) — 0.
  delivered_unpaid — app.services.delivered_unpaid_residual.
                  delivered_unpaid_residual_by_subsidy["by_kind"].

Единственная формула, добавленная ЭТИМ модулем — сложение/вычитание уже
готовых чисел (монтаж листа «Сводная»), не вторая версия ни одной из
перечисленных сумм."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.delivered_unpaid_residual import delivered_unpaid_residual_by_subsidy
from app.services.item_type_split import ALL_KINDS
from app.services.plan_need_level import NEED_LEVEL_NICE_TO_HAVE
from app.services.redistributable_raw import not_committed_raw_rows
from app.services.subsidy_money_summary import subsidy_money_summary
from app.services.subsidy_paid_breakdown import paid_breakdown_by_subsidy
from app.services.type_totals import subsidy_type_totals

_METRIC_KEYS: tuple = (
    "feo", "plan", "committed", "monthly", "likely", "nice", "paid", "delivered_unpaid",
)


def _empty_kind_summary() -> dict:
    return {k: 0.0 for k in _METRIC_KEYS}


async def subsidy_summary_by_kind(db: AsyncSession, subsidy_id: int) -> dict[str, dict]:
    """{kind: {"feo","plan","committed","monthly","likely","nice","paid",
    "delivered_unpaid"}} по ключам app.services.item_type_split.ALL_KINDS
    (goods/services/payroll/unspecified) — данные для листа «Сводная»
    (app.services.plan_graph_export_summary_sheet.write_summary_sheet)."""
    result: dict[str, dict] = {k: _empty_kind_summary() for k in ALL_KINDS}

    # Общее дерево ФЭО строится один раз и передаётся в subsidy_type_totals/
    # subsidy_money_summary (та же оптимизация, что уже применена в
    # dashboard_charts.py/subsidy_money_summary.py — не гонять дерево пять
    # раз подряд за один экспорт).
    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db, [subsidy_id])

    tt_map = await subsidy_type_totals(db, [subsidy_id], tree=tree)
    tt = tt_map.get(subsidy_id) or {}

    money_map = await subsidy_money_summary(db, [subsidy_id], tree=tree)
    committed_by_kind: dict = (money_map.get(subsidy_id) or {}).get("committed_by_kind") or {}

    monthly_by_kind: dict[str, float] = {k: 0.0 for k in ALL_KINDS}
    raw_nice_by_kind: dict[str, float] = {k: 0.0 for k in ALL_KINDS}
    raw_likely_by_kind: dict[str, float] = {k: 0.0 for k in ALL_KINDS}
    rows_by_sid = await not_committed_raw_rows(db, [subsidy_id])
    for row in rows_by_sid.get(subsidy_id, []):
        if row["monthly_future_not_started"]:
            monthly_by_kind[row["kind"]] += row["raw"]
            continue
        bucket = raw_nice_by_kind if row["need_level"] == NEED_LEVEL_NICE_TO_HAVE else raw_likely_by_kind
        bucket[row["kind"]] += row["raw"]

    paid_map = await paid_breakdown_by_subsidy(db, [subsidy_id])
    paid_by_kind: dict = (paid_map.get(subsidy_id) or {}).get("declared_by_kind") or {}

    du_map = await delivered_unpaid_residual_by_subsidy(db, [subsidy_id])
    du_by_kind: dict = (du_map.get(subsidy_id) or {}).get("by_kind") or {}

    for k in ALL_KINDS:
        result[k] = {
            "feo": float(tt.get(f"feo_{k}", 0.0) or 0.0),
            "plan": float(tt.get(f"plan_{k}", 0.0) or 0.0),
            "committed": float(committed_by_kind.get(k, 0.0) or 0.0),
            "monthly": float(monthly_by_kind.get(k, 0.0) or 0.0),
            # «Хотелось бы»/«Скорее всего» уже БЕЗ «ещё уйдёт помесячно, не
            # начато» — not_committed_raw_rows отвела такие строки в monthly
            # выше САМА (вырезка происходит один раз, при разборе rows, не
            # вторым вычитанием здесь).
            "likely": float(raw_likely_by_kind.get(k, 0.0)),
            "nice": float(raw_nice_by_kind.get(k, 0.0)),
            "paid": float(paid_by_kind.get(k, 0.0) or 0.0),
            "delivered_unpaid": float(du_by_kind.get(k, 0.0) or 0.0),
        }
    return result
