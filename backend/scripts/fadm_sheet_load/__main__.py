#!/usr/bin/env python3
"""Разовый загрузчик субсидии «ФАДМ 2026_2» из строк Google-таблицы владельца
(задача 04.10.2026) — создаёт новую субсидию с деревом ФЭО и участниками,
скопированными из существующей субсидии «ФАДМ_2026» (ищется ПО ИМЕНИ, не по
id — на проде это id=7, но номер меняется между окружениями), раскладывает
строки таблицы по закупкам (разовые/рамочные с заказами/помесячные) и
плановым позициям (reserve/likely), подтягивает исполнителей/контрагентов из
«двойника» — той же закупки в старой субсидии (сопоставление по контрагенту
+ сумме с запасным матчем «только по сумме», см. scripts/fadm_sheet_load/
match.py::Matcher).

ПРАВИЛА РАСКЛАДКИ, СОПОСТАВЛЕНИЯ И РЕЖИМЫ — см. docstring'и parse.py
(группировка/помесячный график/MatchUnit), match.py (Matcher — двухпроходное
сопоставление), contractor_norm.py (нормализация ОПФ), build.py (создание
закупок/договоров/плановых позиций).

РЕЖИМЫ:
  --match-only  — ТОЛЬКО сопоставление и отчёт, сессия в READ ONLY
                  транзакции (SET TRANSACTION READ ONLY первой командой),
                  build.py и ни одна функция записи вообще не импортируются
                  в этой ветке (см. match_only.py/report_match_only.py).
  --dry-run     — полная сборка в транзакции, откат (rollback) в конце,
                  печатается тот же отчёт, что был бы при commit.
  (ни то, ни другое) — запись взаправду; требует --replace, если субсидия
                  с --name и copied_from_id=источник уже существует.

ЗАПУСК (внутри контейнера backend; backend/scripts НЕ смонтирован volume'ом
(см. docker-compose.yml — только ./backend/app и ./backend/templates), образ
собран ДО появления этого пакета — та же ситуация, что и у
scripts/cleanup_bad_product_import.py: нужен docker cp внутрь контейнера
ПЕРЕД запуском; в git bash — с MSYS_NO_PATHCONV=1, иначе путь /app/... внутри
контейнера портится подстановкой пути Windows):

    MSYS_NO_PATHCONV=1 docker cp backend/scripts/fadm_sheet_load vsks_crm-backend_a-1:/app/scripts/fadm_sheet_load
    docker exec vsks_crm-backend_a-1 python -m scripts.fadm_sheet_load \\
        --csv scripts/data/fadm_2026_sheet.csv --source "ФАДМ_2026" \\
        --name "ФАДМ 2026_2" --match-only
    docker exec vsks_crm-backend_a-1 python -m scripts.fadm_sheet_load \\
        --csv scripts/data/fadm_2026_sheet.csv --source "ФАДМ_2026" \\
        --name "ФАДМ 2026_2" --dry-run

Скрипт сам ни к какому проду не подключается — работает через
app.database.async_session той БД, к которой подключён контейнер, в котором
его запускают (ВНИМАНИЕ: запуск на проде без --dry-run/--match-only — только
после показа владельцу отчёта --dry-run).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select, text

from app.database import async_session
from app.models.user import User

from .parse import parse_csv

DEFAULT_BUDGET = Decimal("15880100.00")
GOODSSERVICE_AGREEMENT_NUMBER = "091-10-2026-008"


async def _pick_current_user(db) -> User:
    user = (await db.execute(
        select(User).where(User.role.in_(("superadmin", "account_owner"))).order_by(User.id)
    )).scalars().first()
    if user is None:
        user = (await db.execute(select(User).order_by(User.id))).scalars().first()
    if user is None:
        raise RuntimeError("В БД нет ни одного пользователя — некому назначить created_by/assigned_user_id")
    return user


async def run_match_only_mode(args: argparse.Namespace, rows) -> int:
    # Ленивый импорт НАРОЧНО внутри этой функции — match_only.py/
    # report_match_only.py не тянут build.py (ни одной функции записи), а
    # эта ветка вообще не импортирует build.py, даже транзитивно.
    from .match_only import run_match_only
    from .report_match_only import render_match_only_report

    async with async_session() as db:
        # ПЕРВАЯ команда транзакции — ничего не должно успеть выполниться до неё.
        await db.execute(text("SET TRANSACTION READ ONLY"))
        result = await run_match_only(db, rows, args.source)
        report = render_match_only_report(rows, result)
        await db.rollback()  # на всякий случай явно — транзакция и так READ ONLY
    print(report)
    return 0


async def run_relink_mode(args: argparse.Namespace, rows) -> int:
    # Ленивый импорт НАРОЧНО (тот же приём, что у match-only/build веток) —
    # relink.py тянет build.py ТОЛЬКО за find_existing_target_subsidy (чтение),
    # но раз уж он сам пишет (apply_relink_fields/cleanup_employee_contractors/
    # copy_purchase_documents), прятать импорт незачем — он уже в ветке записи.
    from .relink import run_relink
    from .report_relink import render_relink_report

    async with async_session() as db:
        try:
            result = await run_relink(
                db, rows=rows, source_name=args.source, target_name=args.name,
                ensure_employee_names=args.ensure_employee,
            )
            report = render_relink_report(result, dry_run=args.dry_run)
        except Exception:
            await db.rollback()
            raise

        print(report)

        if args.dry_run:
            await db.rollback()
            print("DRY-RUN: изменения отменены (rollback).")
        else:
            await db.commit()
            print(f"Готово: --relink субсидии id={result.target.id} «{result.target.name}» сохранён.")
    return 0


async def run_build_mode(args: argparse.Namespace, rows) -> int:
    from .build import run_build
    from .report import render_report

    async with async_session() as db:
        try:
            current_user = await _pick_current_user(db)
            subsidy, counters = await run_build(
                db,
                rows=rows,
                source_name=args.source,
                target_name=args.name,
                budget=DEFAULT_BUDGET,
                current_user=current_user,
                replace=args.replace,
            )
            report = render_report(rows, args.name, counters, dry_run=args.dry_run)
        except Exception:
            await db.rollback()
            raise

        print(report)

        if args.dry_run:
            await db.rollback()
            print("DRY-RUN: изменения отменены (rollback).")
        else:
            await db.commit()
            print(f"Готово: субсидия id={subsidy.id} «{subsidy.name}» сохранена.")
    return 0


async def run_goodsservice_mode(args: argparse.Namespace) -> int:
    from .sheet_v2_parse import parse_goodsservice_csv
    from .sheet_v2_build import run_build_v2
    from .sheet_v2_report import render_report_v2
    from .sheet_v2_dashboard_check import compute_subsidy_dashboard_stats, paid_by_statement, render_dashboard_comparison

    rows = parse_goodsservice_csv(args.goodsservice)
    if not rows:
        print(f"CSV {args.goodsservice} пуст или не содержит строк", file=sys.stderr)
        return 1

    async with async_session() as db:
        try:
            current_user = await _pick_current_user(db)
            subsidy, counters = await run_build_v2(
                db,
                rows=rows,
                source_name=args.source,
                target_name=args.name,
                budget=DEFAULT_BUDGET,
                agreement_number=GOODSSERVICE_AGREEMENT_NUMBER,
                current_user=current_user,
                replace=args.replace,
            )
            report = render_report_v2(rows, args.name, counters, dry_run=args.dry_run)
            # Задание 05.10.2026, доп. п.5 — карточки ДО записи, ОДНОЙ
            # транзакцией с созданием (см. докстринг sheet_v2_dashboard_check.py).
            dash_stats = await compute_subsidy_dashboard_stats(db, current_user, subsidy.id)
            paid_stmt_total = await paid_by_statement(db, subsidy.id)
            dash_report = render_dashboard_comparison(dash_stats, paid_stmt_total)
        except Exception:
            await db.rollback()
            raise

        print(report)
        print(dash_report)

        if args.dry_run:
            await db.rollback()
            print("DRY-RUN: изменения отменены (rollback).")
        else:
            await db.commit()
            print(f"Готово: субсидия id={subsidy.id} «{subsidy.name}» сохранена.")
    return 0


async def run_copy_docs_mode(args: argparse.Namespace) -> int:
    from .sheet_v2_docs import run_copy_docs
    from .sheet_v2_docs_report import render_copy_docs_report

    async with async_session() as db:
        try:
            pairs, counters = await run_copy_docs(
                db, target_name=args.name, source_name=args.source,
            )
            report = render_copy_docs_report(pairs, counters, dry_run=args.dry_run)
        except Exception:
            await db.rollback()
            raise

        print(report)

        if args.dry_run:
            await db.rollback()
            print("DRY-RUN: изменения отменены (rollback).")
        else:
            await db.commit()
            print("Готово: документы скопированы.")
    return 0


async def main_async(args: argparse.Namespace) -> int:
    if args.copy_docs:
        return await run_copy_docs_mode(args)
    if args.goodsservice:
        return await run_goodsservice_mode(args)

    rows = parse_csv(args.csv)
    if not rows:
        print(f"CSV {args.csv} пуст или не содержит строк", file=sys.stderr)
        return 1

    if args.match_only:
        return await run_match_only_mode(args, rows)
    if args.relink:
        return await run_relink_mode(args, rows)
    return await run_build_mode(args, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="Путь к CSV таблицы первого загрузчика (внутри контейнера)")
    parser.add_argument("--goodsservice", help="Путь к scripts/data/fadm_2026_goodsservice.csv — "
                         "режим v2 (пересборка из листа GoodsService, задание 05.10.2026)")
    parser.add_argument("--copy-docs", action="store_true",
                         help="Постфактум для уже существующей --name: скопировать документы/чеки двойника "
                              "из --source на закупки --name по (contractor_id, сумма) — см. sheet_v2_docs.py")
    parser.add_argument("--source", required=True, help='Имя субсидии-источника, напр. "ФАДМ_2026"')
    parser.add_argument("--name", help='Имя новой субсидии, напр. "ФАДМ 2026_2" (не нужно для --match-only)')
    parser.add_argument("--dry-run", action="store_true", help="Всё в транзакции, откат в конце, только отчёт")
    parser.add_argument("--match-only", action="store_true",
                         help="Только сопоставление со старой субсидией, READ ONLY транзакция, ничего не создаёт")
    parser.add_argument("--replace", action="store_true",
                         help="Если субсидия с --name и copied_from_id=источник уже есть — удалить и создать заново")
    parser.add_argument("--relink", action="store_true",
                         help="Работает с УЖЕ существующей субсидией --name: пересопоставление, исполнитель/"
                              "авансовые/статусы рамочных заказов, документы — БЕЗ повторного создания закупок "
                              "(см. docstring relink.py)")
    parser.add_argument("--ensure-employee", action="append", default=[], metavar="ФИО",
                         help="Гарантировать (идемпотентно) сотрудника с таким ФИО в организации целевой субсидии "
                              "ПЕРЕД сопоставлением — чтобы его закупки распознались как авансовые (см. employees.py). "
                              "Можно указывать несколько раз. Только с --relink.")
    args = parser.parse_args()

    if args.copy_docs:
        if args.match_only or args.relink or args.ensure_employee or args.replace or args.goodsservice:
            parser.error("--copy-docs несовместим с --match-only/--relink/--ensure-employee/--replace/--goodsservice")
        if not args.name:
            parser.error("--name обязателен для --copy-docs (целевая субсидия, уже существующая)")
    elif args.goodsservice:
        if args.match_only or args.relink or args.ensure_employee:
            parser.error("--goodsservice несовместим с --match-only/--relink/--ensure-employee")
        if not args.name:
            parser.error("--name обязателен для --goodsservice")
    else:
        if not args.csv:
            parser.error("--csv обязателен вне режима --goodsservice")
        if args.match_only and (args.dry_run or args.replace or args.relink):
            parser.error("--match-only несовместим с --dry-run/--replace/--relink (он ничего не создаёт и не удаляет)")
        if args.relink and args.replace:
            parser.error("--relink несовместим с --replace (--relink не пересоздаёт субсидию)")
        if args.ensure_employee and not args.relink:
            parser.error("--ensure-employee работает только вместе с --relink")
        if not args.match_only and not args.name:
            parser.error("--name обязателен вне режима --match-only")

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
