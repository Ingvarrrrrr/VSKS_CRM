#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оркестратор полной пересборки «ФАДМ 2026_2» (план sleepy-fluttering-
walrus.md, 15.10.2026) — ОДНА транзакция, два уже существующих шага вызваны
по очереди, НИ ОДИН не переписан:

  1. `sheet_v2_rebuild.run_rebuild_in_place` — снимок -> удаление созданного
     загрузчиком -> `populate_subsidy_v2` из CSV листа GoodsService.
  2. `sheet_v2_enrich.run_enrich` — пары со старой субсидией, перенос данных,
     остановка старых, перенос без пары, подтверждения «Оплачено» ИЗ ТОГО ЖЕ
     снимка (`RebuildResult.snapshot`, из памяти, файл на диске не
     перечитывается — ПРАВИЛО №6, один снимок, не два прочтения).

ПРАВИЛО №5 — этот модуль НЕ знает внутренностей rebuild/enrich, только вызывает
их публичные функции и собирает единый отчёт (до/после по
`subsidy_money_summary`/`contracted_total_by_subsidy`/`compute_feo_plan_tree`
— ТЕ ЖЕ сервисы, что карточка субсидии и вкладка «Договоры», не вторая
формула).

ЗАПУСК (внутри контейнера backend; backend/scripts не смонтирован volume'ом
на backend_b — см. docstring __main__.py, нужен docker cp; backend_a монтирует
автоматически):
    docker exec vsks_crm-backend_b-1 python -m scripts.fadm_sheet_load.sheet_v2_full_rebuild \\
        --target-id 7320 --source-subsidy-id 7 \\
        --csv scripts/data/fadm_2026_goodsservice.csv --dry-run
    (повторить с --apply, когда отчёт одобрен)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.services.stage_cumulative import contracted_total_by_subsidy
from app.services.subsidy_money_summary import subsidy_money_summary

from .__main__ import _pick_current_user  # ПРАВИЛО №6 — тот же выбор created_by/assigned_user_id, что у всех режимов __main__.py
from .sheet_v2_enrich import EnrichReport, render_report, run_enrich
from .sheet_v2_parse import parse_goodsservice_csv
from .sheet_v2_rebuild import RebuildResult, run_rebuild_in_place
from .sheet_v2_rebuild_report import render_rebuild_report


@dataclass
class MoneySnapshot:
    budget: float = 0.0
    planned: float = 0.0
    committed: float = 0.0
    free: float = 0.0
    redistributable: Optional[float] = None
    paid_confirmed: float = 0.0
    contracted_total: float = 0.0
    excess_goods: float = 0.0
    excess_services: float = 0.0


async def _capture_money_snapshot(db: AsyncSession, subsidy_id: int) -> MoneySnapshot:
    """Карточки «было -> станет» (п.е/ж оркестратора) — ТЕ ЖЕ сервисы, что
    карточка субсидии (subsidy_money_summary), вкладка «Договоры»
    (contracted_total_by_subsidy) и дерево ФЭО (compute_feo_plan_tree) — не
    вторая формула (ПРАВИЛО №6). compute_feo_plan_tree считается ОДИН раз и
    передаётся в subsidy_money_summary (та умеет принять уже готовое дерево —
    см. её docstring), экономя второй проход по дереву."""
    from app.services.feo_plan_tree import compute_feo_plan_tree

    tree = await compute_feo_plan_tree(db, [subsidy_id])
    summary = (await subsidy_money_summary(db, [subsidy_id], tree=tree)).get(subsidy_id, {})
    contracted = (await contracted_total_by_subsidy(db, subsidy_ids=[subsidy_id])).get(subsidy_id, {})

    excess_goods = 0.0
    excess_services = 0.0
    for node in tree.values():
        if node.get("subsidy_id") == subsidy_id and node.get("parent_id") is None:
            excess_goods += float(node.get("excess_fact_over_plan_goods", 0.0) or 0.0)
            excess_services += float(node.get("excess_fact_over_plan_services", 0.0) or 0.0)

    return MoneySnapshot(
        budget=float(summary.get("budget") or 0.0),
        planned=float(summary.get("planned") or 0.0),
        committed=float(summary.get("committed") or 0.0),
        free=float(summary.get("free") or 0.0),
        redistributable=summary.get("redistributable"),
        paid_confirmed=float(summary.get("balance_paid_confirmed") or 0.0),
        contracted_total=float(contracted.get("amount") or 0.0),
        excess_goods=excess_goods,
        excess_services=excess_services,
    )


@dataclass
class FullRebuildResult:
    rebuild: RebuildResult
    enrich: EnrichReport
    money_before: MoneySnapshot
    money_after: MoneySnapshot


async def run_full_rebuild(
    db: AsyncSession, *, csv_path: str, target_id: Optional[int], target_name: Optional[str],
    source_subsidy_id: int, skip_source_ids: Optional[list] = None, snapshot_out: Optional[str] = None,
) -> FullRebuildResult:
    rows = parse_goodsservice_csv(csv_path)
    if not rows:
        raise ValueError(f"CSV {csv_path} пуст или не содержит строк")

    current_user = await _pick_current_user(db)

    # «Было» — ДО удаления созданного загрузчиком (та же субсидия, её
    # дерево/budget не трогаются ребилдом, но planned/committed/excess
    # зависят от закупок листа, которые сейчас будут снесены и пересобраны).
    from .sheet_v2_rebuild import find_target_subsidy
    target_before = await find_target_subsidy(db, target_id=target_id, target_name=target_name)
    money_before = await _capture_money_snapshot(db, target_before.id)

    rebuild_result = await run_rebuild_in_place(
        db, rows=rows, target_id=target_id, target_name=target_name,
        current_user=current_user, snapshot_out=snapshot_out,
    )

    enrich_report = await run_enrich(
        db, source_subsidy_id=source_subsidy_id, target_subsidy_id=rebuild_result.subsidy.id,
        snapshot=rebuild_result.snapshot, skip_source_ids=skip_source_ids,
    )

    money_after = await _capture_money_snapshot(db, rebuild_result.subsidy.id)

    return FullRebuildResult(
        rebuild=rebuild_result, enrich=enrich_report, money_before=money_before, money_after=money_after,
    )


def _fmt(v) -> str:
    if v is None:
        return "—"
    return f"{Decimal(str(v)):,.2f}".replace(",", " ").replace(".", ",")


def render_full_report(result: FullRebuildResult, rows, *, dry_run: bool) -> str:
    lines = [f"=== sheet_v2_full_rebuild — субсидия id={result.rebuild.subsidy.id} "
             f"«{result.rebuild.subsidy.name}» ({'DRY-RUN' if dry_run else 'APPLY'}) ==="]
    lines.append("")
    lines.append("--- Шаг 1: rebuild-in-place ---")
    lines.append(render_rebuild_report(rows, result.rebuild, dry_run=dry_run))
    lines.append("")
    lines.append("--- Шаг 2: enrich (пары/без пары/подтверждения) ---")
    lines.append(render_report(result.enrich, apply=not dry_run))
    lines.append("")

    lines.append("--- Карточки «было -> станет» (subsidy_money_summary + contracted_total_by_subsidy) ---")
    b, a = result.money_before, result.money_after
    for label, before, after in (
        ("Бюджет", b.budget, a.budget),
        ("Запланировано", b.planned, a.planned),
        ("Законтрактовано (money_summary)", b.committed, a.committed),
        ("Сумма договоров (contracted_total_by_subsidy)", b.contracted_total, a.contracted_total),
        ("Свободно", b.free, a.free),
        ("Можно перераспределить", b.redistributable, a.redistributable),
        ("Подтверждено выпиской (оплачено)", b.paid_confirmed, a.paid_confirmed),
    ):
        lines.append(f"  {label}: {_fmt(before)} -> {_fmt(after)}")
    lines.append("")

    lines.append("--- Превышения по типам (compute_feo_plan_tree, Σ по корням) ---")
    lines.append(f"  excess_fact_over_plan_goods: {_fmt(b.excess_goods)} -> {_fmt(a.excess_goods)}")
    lines.append(f"  excess_fact_over_plan_services: {_fmt(b.excess_services)} -> {_fmt(a.excess_services)}")

    return "\n".join(lines)


def default_report_path(subsidy_id: int) -> Path:
    today = date.today().strftime("%Y%m%d")
    return Path(__file__).resolve().parent.parent / "data" / f"fadm_full_rebuild_report_{subsidy_id}_{today}.txt"


async def _create_backups(db: AsyncSession, target_subsidy_id: int) -> None:
    """Бэкап-таблицы ПЕРЕД изменением (п. «Флаги» задания) — те же три
    таблицы, что sheet_v2_enrich._create_backups (переиспользуем её, не
    копируем SQL второй раз, ПРАВИЛО №6) плюс плановые позиции субсидии
    (их тоже снесёт/пересоберёт rebuild-in-place)."""
    from .sheet_v2_enrich import _create_backups as _enrich_backups

    await _enrich_backups(db, target_subsidy_id)
    today = date.today().strftime("%Y%m%d")
    await db.execute(text(
        f"CREATE TABLE IF NOT EXISTS bk_{today}_full_rebuild_{target_subsidy_id}_plan_items AS "
        "SELECT fpi.* FROM feo_planned_items fpi "
        "JOIN feo_categories fc ON fc.id = fpi.feo_category_id "
        "WHERE fc.subsidy_id = :sid"
    ), {"sid": target_subsidy_id})


async def main_async(args: argparse.Namespace) -> int:
    skip_ids = [int(x) for x in args.skip_source_ids.split(",") if x.strip()] if args.skip_source_ids else []
    rows_for_report = parse_goodsservice_csv(args.csv)

    async with async_session() as db:
        try:
            if args.apply:
                target_sid = args.target_id
                if target_sid is None:
                    from .sheet_v2_rebuild import find_target_subsidy
                    target_sid = (await find_target_subsidy(db, target_id=None, target_name=args.name)).id
                await _create_backups(db, target_sid)

            result = await run_full_rebuild(
                db, csv_path=args.csv, target_id=args.target_id, target_name=args.name,
                source_subsidy_id=args.source_subsidy_id, skip_source_ids=skip_ids,
                snapshot_out=args.snapshot_out,
            )
        except Exception:
            await db.rollback()
            raise

        report_text = render_full_report(result, rows_for_report, dry_run=args.dry_run)
        print(report_text)

        report_path = Path(args.report_out) if args.report_out else default_report_path(result.rebuild.subsidy.id)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
        print(f"\nОтчёт сохранён: {report_path}")

        if args.apply:
            await db.commit()
            print("Готово: применено.")
        else:
            await db.rollback()
            print("БЕЗ --apply: изменения НЕ применены (rollback).")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target-id", type=int, default=None, help="id уже существующей целевой субсидии (ФАДМ 2026_2)")
    ap.add_argument("--name", default=None, help="имя целевой субсидии (альтернатива --target-id)")
    ap.add_argument("--source-subsidy-id", type=int, default=7, help="id субсидии-источника (ФАДМ_2026)")
    ap.add_argument("--csv", required=True, help="Путь к scripts/data/fadm_2026_goodsservice.csv (внутри контейнера)")
    ap.add_argument("--skip-source-ids", default=None, help="id закупок источника, уже есть в получателе — через запятую")
    ap.add_argument("--snapshot-out", default=None, help="Путь для JSON-снимка (по умолчанию — см. sheet_v2_rebuild.py)")
    ap.add_argument("--report-out", default=None, help="Путь для текстового отчёта (по умолчанию scripts/data/fadm_full_rebuild_report_<sid>_<дата>.txt)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    args.apply = bool(args.apply)
    if not args.target_id and not args.name:
        ap.error("укажите --target-id или --name")
    if args.target_id and args.name:
        ap.error("укажите ТОЛЬКО --target-id ИЛИ ТОЛЬКО --name, не оба")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
