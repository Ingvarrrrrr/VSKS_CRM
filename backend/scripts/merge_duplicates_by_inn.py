#!/usr/bin/env python3
"""
CLI: разовый мерж дублей контрагентов/организаций по ИНН (D8/D9, волна 4b,
Правило №6 — «один показатель, один источник истины»).

ПРИЧИНА. Раньше слияние дублей запускалось при КАЖДОМ старте приложения:
  - app/startup/backfills.py::_phase26_qq_contractor_dedup_by_inn (контрагенты)
  - app/startup/backfills.py::_org_dedup_by_inn → org_dedup._merge_duplicate_orgs_by_inn (организации)
Это разовый data-fix (устранение уже накопленных дублей + защитный partial
unique index), а не часть жизненного цикла старта приложения — после первого
успешного прогона повторное сканирование ВСЕЙ таблицы contractors/
organizations на каждом рестарте контейнера не находит новых дублей (создание
записей и уникальный индекс их больше не допускают).

Логика ПЕРЕНЕСЕНА (не скопирована повторно):
  - контрагенты: app/services/contractor_dedup.py::merge_duplicate_contractors_by_inn
    (была в backfills.py, теперь только здесь и в сервисе)
  - организации:  app/services/org_dedup.py::_merge_duplicate_orgs_by_inn
    (не менялась по алгоритму, добавлен только параметр dry_run)

Раньше backfill молча пропускал автомерж контрагентов при >200 групп дублей
(защита от случайного массового изменения на старте, без участия человека).
В CLI эта защита не нужна и заменена на прозрачность: --dry-run печатает
ПОЛНЫЙ список групп (ИНН, id, имена, число FK-ссылок на каждого кандидата),
а реальное слияние требует явного флага --yes.

ФЛАГИ:
  --dry-run            показать группы дублей и что было бы сделано, ничего
                        не писать в БД (безопасно запускать в любой момент).
  --yes                применить слияние по-настоящему. Без --dry-run и без
                        --yes скрипт по умолчанию ведёт себя как --dry-run
                        (защита от случайного запуска без обеих читаемых опций).
  --contractors         обработать только контрагентов.
  --organizations        обработать только организации.
                        Без обоих флагов — оба вида (contractors, затем organizations).

Запуск (внутри контейнера backend, tests/scripts не примонтированы —
предварительно docker cp):
    docker exec vsks_crm-backend_a-1 python scripts/merge_duplicates_by_inn.py --dry-run
    docker exec vsks_crm-backend_a-1 python scripts/merge_duplicates_by_inn.py --yes
    docker exec vsks_crm-backend_a-1 python scripts/merge_duplicates_by_inn.py --dry-run --contractors
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from app.database import async_session  # noqa: E402
from app.services.contractor_dedup import (  # noqa: E402
    find_duplicate_contractor_groups,
    merge_duplicate_contractors_by_inn,
)
from app.services.org_dedup import _merge_duplicate_orgs_by_inn  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _print_contractor_groups(db) -> int:
    """Печатает группы дублей контрагентов (ИНН, id, имена, число FK-ссылок).
    Возвращает число групп."""
    groups = await find_duplicate_contractor_groups(db)
    if not groups:
        print("Контрагенты: дублей по ИНН не найдено.")
        return 0

    from app.services.contractor_dedup import FK_TABLES

    print(f"Контрагенты: найдено {len(groups)} групп дублей по ИНН:")
    for row in groups:
        norm_inn, ids = row.norm_inn, list(row.ids)
        names_result = await db.execute(
            text("SELECT id, name FROM contractors WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": ids},
        )
        names = {r[0]: r[1] for r in names_result.all()}
        ref_counts = {}
        for tbl, col in FK_TABLES:
            try:
                cnt_result = await db.execute(
                    text(f"SELECT COUNT(*) FROM {tbl} WHERE {col} = ANY(:ids)"),
                    {"ids": ids},
                )
                n = cnt_result.scalar() or 0
                if n:
                    ref_counts[f"{tbl}.{col}"] = n
            except Exception:
                continue
        print(f"  ИНН={norm_inn!r} keep_id={ids[0]} dup_ids={ids[1:]}")
        for _id in ids:
            print(f"    id={_id} name={names.get(_id)!r}")
        if ref_counts:
            print(f"    ссылок: {ref_counts}")
    return len(groups)


async def _print_org_groups(db) -> int:
    """Печатает группы дублей организаций (ИНН, id, имена). Возвращает число групп."""
    dup_result = await db.execute(text(
        "SELECT inn, array_agg(id ORDER BY id) AS ids "
        "FROM organizations "
        "WHERE inn IS NOT NULL AND btrim(inn) <> '' "
        "GROUP BY inn HAVING count(*) > 1"
    ))
    groups = dup_result.fetchall()
    if not groups:
        print("Организации: дублей по ИНН не найдено.")
        return 0

    print(f"Организации: найдено {len(groups)} групп дублей по ИНН:")
    for row in groups:
        inn_val, ids = row[0], list(row[1])
        names_result = await db.execute(
            text("SELECT id, name FROM organizations WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": ids},
        )
        names = {r[0]: r[1] for r in names_result.all()}
        print(f"  ИНН={inn_val!r} keep_id={ids[0]} dup_ids={ids[1:]}")
        for _id in ids:
            print(f"    id={_id} name={names.get(_id)!r}")
    return len(groups)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="показать группы, ничего не писать")
    parser.add_argument("--yes", action="store_true", help="применить слияние по-настоящему")
    parser.add_argument("--contractors", action="store_true", help="только контрагенты")
    parser.add_argument("--organizations", action="store_true", help="только организации")
    args = parser.parse_args()

    do_contractors = args.contractors or not args.organizations
    do_organizations = args.organizations or not args.contractors
    apply_changes = args.yes and not args.dry_run

    async with async_session() as db:
        if do_contractors:
            n_groups = await _print_contractor_groups(db)
            if n_groups and apply_changes:
                stats = await merge_duplicate_contractors_by_inn(db, dry_run=False)
                print(f"Контрагенты: применено — групп {stats['groups']}, слито {stats['merged']}.")
            elif n_groups:
                print("Контрагенты: dry-run — изменения НЕ применены (передайте --yes для применения).")

        if do_organizations:
            n_groups = await _print_org_groups(db)
            if n_groups and apply_changes:
                stats = await _merge_duplicate_orgs_by_inn(db, dry_run=False)
                print(f"Организации: применено — групп {stats['groups']}, слито {stats['merged']}.")
            elif n_groups:
                print("Организации: dry-run — изменения НЕ применены (передайте --yes для применения).")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
