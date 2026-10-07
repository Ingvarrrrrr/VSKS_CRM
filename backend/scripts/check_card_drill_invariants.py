# -*- coding: utf-8 -*-
"""check_card_drill_invariants.py — проверка на ЖИВОЙ локальной базе (не
фикстуры), план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 4,
раздел «Тесты»: для КАЖДОЙ субсидии локальной БД числа карточек «Бюджет
(ФЭО)»/«Запланировано»/«Свободно» — ТЕ ЖЕ, что отдаёт /api/dashboard/charts
(через app.services.subsidy_money_summary/app.services.type_totals, ПРАВИЛО
№6 — не второй расчёт для проверки) — ОБЯЗАНЫ совпасть с Σ строк
app.services.feo_card_drill.card_drill_rows по каждой карточке и каждому
типу (goods/services/payroll/unspecified). Выводит расхождения, если они
есть; иначе печатает "OK" по каждой субсидии и сводку.

Запуск (из контейнера backend, см. docker-compose exec):
    docker compose -p vsks_crm exec -T backend_a python scripts/check_card_drill_invariants.py
    docker compose -p vsks_crm exec -T backend_a python scripts/check_card_drill_invariants.py --subsidy-id 10338
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

_EPS = 0.02  # копеечный люфт округления (та же величина, что в split_amount_by_shares)


async def _check_subsidy(db, sid: int, name: str) -> list:
    from app.services.feo_card_drill import card_drill_rows
    from app.services.feo_plan_tree import compute_feo_plan_tree
    from app.services.item_type_split import ALL_KINDS
    from app.services.subsidy_money_summary import subsidy_money_summary
    from app.services.type_totals import subsidy_type_totals

    problems: list = []
    tree = await compute_feo_plan_tree(db, [sid])
    money = (await subsidy_money_summary(db, [sid])).get(sid, {})
    feo_entered = bool(money.get("feo_entered"))
    tt = dict((await subsidy_type_totals(db, [sid], tree=tree)).get(sid, {}))

    # Та же override-ветка, что dashboard_charts.py строит по-месту (не
    # фильтрует type_totals по feo_filled, как subsidy_money_summary.py,
    # поэтому здесь воспроизведена байт-в-байт, см. её докстринг у себя):
    # субсидия БЕЗ typed-разбивки дерева (calc<=0), но с РУЧНЫМ Subsidy.budget
    # (feo_budget_total>0) — budget_unspecified = feo_budget_total целиком,
    # goods/services/payroll = 0.
    from app.services.subsidy_budget import calculate_budgets_bulk
    calc = float((await calculate_budgets_bulk(db, [sid])).get(sid, 0.0) or 0.0)
    feo_budget_total = money.get("budget_basis")
    if calc <= 0 and feo_budget_total and feo_budget_total > 0:
        tt["feo_goods"] = 0.0
        tt["feo_services"] = 0.0
        tt["feo_payroll"] = 0.0
        tt["feo_unspecified"] = feo_budget_total

    # ── "budget" ──────────────────────────────────────────────────────────
    official_budget_total = money.get("budget_basis") if feo_entered else 0.0
    drill = await card_drill_rows(db, sid, "budget", "all", tree=tree)
    drill_total = drill["total"]
    rows_sum = sum(r["amount"] for r in drill["rows"])
    if abs(rows_sum - drill_total) > _EPS:
        problems.append(f"budget/all: Σrows={rows_sum:.2f} != drill.total={drill_total:.2f}")
    if feo_entered and abs(drill_total - (official_budget_total or 0.0)) > _EPS:
        problems.append(f"budget/all: drill.total={drill_total:.2f} != budget_basis={official_budget_total:.2f}")
    for k in ALL_KINDS:
        d = await card_drill_rows(db, sid, "budget", k, tree=tree)
        rsum = sum(r["amount"] for r in d["rows"])
        if abs(rsum - d["total"]) > _EPS:
            problems.append(f"budget/{k}: Σrows={rsum:.2f} != drill.total={d['total']:.2f}")
        if feo_entered:
            official_k = tt.get(f"feo_{k}", 0.0)
            if abs(d["total"] - official_k) > _EPS:
                problems.append(f"budget/{k}: drill.total={d['total']:.2f} != type_totals.feo_{k}={official_k:.2f}")

    # ── "planned" ─────────────────────────────────────────────────────────
    from app.services.feo_plan_totals import feo_plan_subsidy_totals
    official_planned_total = (await feo_plan_subsidy_totals(db, [sid])).get(sid, 0.0)
    drill = await card_drill_rows(db, sid, "planned", "all", tree=tree)
    drill_total = drill["total"]
    rows_sum = sum(r["amount"] for r in drill["rows"])
    if abs(rows_sum - drill_total) > _EPS:
        problems.append(f"planned/all: Σrows={rows_sum:.2f} != drill.total={drill_total:.2f}")
    if abs(drill_total - official_planned_total) > _EPS:
        problems.append(f"planned/all: drill.total={drill_total:.2f} != feo_plan_subsidy_totals={official_planned_total:.2f}")
    n_rows_all = len(drill["rows"])
    for k in ALL_KINDS:
        d = await card_drill_rows(db, sid, "planned", k, tree=tree)
        rsum = sum(r["amount"] for r in d["rows"])
        if abs(rsum - d["total"]) > _EPS:
            problems.append(f"planned/{k}: Σrows={rsum:.2f} != drill.total={d['total']:.2f}")
        official_k = tt.get(f"plan_{k}", 0.0)
        if abs(d["total"] - official_k) > _EPS:
            problems.append(f"planned/{k}: drill.total={d['total']:.2f} != type_totals.plan_{k}={official_k:.2f}")

    # ── "free" ────────────────────────────────────────────────────────────
    official_free_total = money.get("free_basis") if feo_entered else 0.0
    drill = await card_drill_rows(db, sid, "free", "all", tree=tree)
    drill_total = drill["total"]
    rows_sum = sum(r["amount"] for r in drill["rows"])
    if abs(rows_sum - drill_total) > _EPS:
        problems.append(f"free/all: Σrows={rows_sum:.2f} != drill.total={drill_total:.2f}")
    if feo_entered and abs(drill_total - (official_free_total or 0.0)) > _EPS:
        problems.append(f"free/all: drill.total={drill_total:.2f} != free_basis={official_free_total:.2f}")
    for k in ALL_KINDS:
        d = await card_drill_rows(db, sid, "free", k, tree=tree)
        rsum = sum(r["amount"] for r in d["rows"])
        if abs(rsum - d["total"]) > _EPS:
            problems.append(f"free/{k}: Σrows={rsum:.2f} != drill.total={d['total']:.2f}")

    status = "OK" if not problems else "MISMATCH"
    print(f"[{status}] subsidy {sid} «{name}» — planned.total={official_planned_total:.2f}, "
          f"planned.rows={n_rows_all}, feo_entered={feo_entered}")
    for p in problems:
        print(f"    - {p}")
    return problems


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subsidy-id", type=int, default=None)
    args = parser.parse_args()

    from app.database import async_session
    from app.models.subsidy import Subsidy
    from sqlalchemy import select

    async with async_session() as db:
        if args.subsidy_id is not None:
            rows = (await db.execute(
                select(Subsidy.id, Subsidy.name).where(Subsidy.id == args.subsidy_id)
            )).all()
        else:
            rows = (await db.execute(select(Subsidy.id, Subsidy.name))).all()

        total_problems = 0
        for sid, name in rows:
            problems = await _check_subsidy(db, sid, name or "")
            total_problems += len(problems)

        print()
        print(f"Проверено субсидий: {len(rows)}; расхождений: {total_problems}")
        if total_problems:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
