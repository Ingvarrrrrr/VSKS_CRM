#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разовая правка feo_planned_items.plan_changed_at для позиций конкретной
закупки/субсидии — владелец 08.10.2026, план binary-crunching-island.md,
раздел 1, пункт «Данные «ФАДМ 2026_2»».

ПОВОД. plan_changed_at — момент, когда ВКЛАД позиции в план появился или
изменился (см. app/models/feo_planned_item.py). Для НОВЫХ изменений он
проставляется автоматически событием модели. Но у позиций закупки №975
(ФАДМ 2026_2) created_at=01.10.2026 (создание из заявки №98), а РЕАЛЬНЫЙ
перенос позиций в субсидию произошёл позже массовой операцией (05-07.10) —
plan_changed_at унаследовал бэкфилл = created_at (миграция
q2s4u6w8y0a2), т.е. «не знает» про этот перенос. Этот скрипт — ЕДИНСТВЕННЫЙ
способ поправить историческое значение ВРУЧНУЮ (через core UPDATE, минуя
ORM-событие before_update, которое всегда ставит «сейчас» — см. докстринг
_feo_planned_item_touch_plan_changed_at_on_update).

НЕ запускать на проде без --apply ПОСЛЕ явного одобрения владельцем — см.
план, пункт «Данные «ФАДМ 2026_2»: запись в прод, по одобрению этого плана».

Отбор позиций — ЛИБО --purchase-id (все FeoPlannedItem, на которые ссылается
хоть одна PurchaseItem.feo_planned_item_id этой закупки), ЛИБО --subsidy-id
(все активные FeoPlannedItem субсидии, тогда --purchase-id не передаётся).
Хотя бы один из двух обязателен.

Запуск (backend-код смонтирован, перезапуск контейнера не нужен):
  docker compose -p vsks_crm exec -T backend_a python scripts/set_plan_changed_at.py \\
      --purchase-id 975 --at 2026-10-07T12:00:00+03:00
  docker compose -p vsks_crm exec -T backend_a python scripts/set_plan_changed_at.py \\
      --purchase-id 975 --at 2026-10-07T12:00:00+03:00 --apply

Без --apply — только печать (dry-run, транзакция откатывается)."""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402


def _to_naive_local(dt: datetime) -> datetime:
    """plan_changed_at — TIMESTAMP WITHOUT TIME ZONE (как created_at) —
    asyncpg валит DataError на aware datetime для такой колонки (владелец
    09.10.2026, прогон на проде). Если --at пришёл со смещением (+03:00 и
    т.п.) — переводим на ЛОКАЛЬНОЕ время сервера/БД (astimezone() без
    аргументов берёт системный tz процесса) и обрезаем tzinfo — тот же
    смысл, что у created_at (func.now() пишет локальное время сессии БД,
    без зоны). Наивный datetime (без смещения) передаётся как есть —
    предполагается, что он уже в локальном времени сервера."""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


async def _resolve_planned_item_ids(db, purchase_id, subsidy_id) -> list[int]:
    if purchase_id:
        res = await db.execute(
            select(PurchaseItem.feo_planned_item_id)
            .where(PurchaseItem.purchase_id == purchase_id)
            .where(PurchaseItem.feo_planned_item_id.isnot(None))
        )
        return sorted({r[0] for r in res.all()})
    if subsidy_id:
        from app.models.feo_category import FeoCategory
        cat_ids = (await db.execute(
            select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy_id)
        )).scalars().all()
        res = await db.execute(
            select(FeoPlannedItem.id)
            .where(FeoPlannedItem.feo_category_id.in_(cat_ids))
            .where(FeoPlannedItem.is_active.is_(True))
        )
        return sorted({r[0] for r in res.all()})
    return []


async def run(db, purchase_id, subsidy_id, at: datetime, apply: bool) -> int:
    ids = await _resolve_planned_item_ids(db, purchase_id, subsidy_id)
    if not ids:
        print("Не найдено ни одной плановой позиции по заданному отбору — ничего не меняю.")
        return 0

    rows = (await db.execute(
        select(FeoPlannedItem.id, FeoPlannedItem.name, FeoPlannedItem.amount, FeoPlannedItem.plan_changed_at)
        .where(FeoPlannedItem.id.in_(ids))
        .order_by(FeoPlannedItem.id)
    )).all()

    print(f"Найдено {len(rows)} плановых позиций. Новое plan_changed_at = {at.isoformat()}.")
    for r in rows:
        print(
            f"  id={r.id:>6}  «{(r.name or '')[:60]}»  сумма={r.amount}  "
            f"было={r.plan_changed_at.isoformat() if r.plan_changed_at else None}  "
            f"-> станет={at.isoformat()}"
        )

    if apply:
        await db.execute(
            FeoPlannedItem.__table__.update()
            .where(FeoPlannedItem.id.in_(ids))
            .values(plan_changed_at=at)
        )
    return len(rows)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--purchase-id", type=int, default=None, help="закупка — все позиции, на которые ссылается хоть одна её строка")
    parser.add_argument("--subsidy-id", type=int, default=None, help="субсидия — ВСЕ активные плановые позиции (используй осторожно)")
    parser.add_argument(
        "--at", type=str, required=True,
        help=(
            "новое plan_changed_at, ISO-8601 (напр. 2026-10-07T12:00:00+03:00 "
            "или 2026-10-07T12:00:00 без зоны). Колонка — TIMESTAMP WITHOUT "
            "TIME ZONE: значение со смещением автоматически переводится в "
            "ЛОКАЛЬНОЕ время сервера/БД и зона отбрасывается (как у "
            "created_at); значение без смещения считается уже локальным и "
            "передаётся как есть."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="применить (без флага — только печать, dry-run)")
    args = parser.parse_args()

    if not args.purchase_id and not args.subsidy_id:
        print("Нужен хотя бы один из --purchase-id / --subsidy-id.")
        return 1

    at = _to_naive_local(datetime.fromisoformat(args.at))

    async with async_session() as db:
        count = await run(db, args.purchase_id, args.subsidy_id, at, apply=args.apply)
        if args.apply and count:
            await db.commit()
            print(f"COMMIT — применено, изменено позиций: {count}.")
        else:
            await db.rollback()
            print("ROLLBACK — это был dry-run (--apply не передан), изменения НЕ применены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
