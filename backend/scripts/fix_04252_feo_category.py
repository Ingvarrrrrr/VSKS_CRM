#!/usr/bin/env python3
"""
CLI: разовая починка прода — закупка РЕЕ-2026-04252 (заявка №206, 20.10.2026).

Согласующий сменил категорию ФЭО шапки заявки (была «Орг. расходы» id 10712
-> стала «Ремонт техники» id 10711, feo_per_item=False — «одна категория на
всю заявку»). 14 плановых позиций (FeoPlannedItem, id 43143..43156,
auto_created=True), заведённых при конвертации заявки в закупку, остались в
протухшей категории 10712 (категория ТОВАРА, а не шапки) — закупка показывает
«Расхождение категории ФЭО» по всем 14 товарам.

Правка кода (та же сессия, Правило №6) устраняет причину на будущее
(app/services/feo_effective_category.py + app/services/plan_autoassign.py +
app/routers/wish_transitions.py/wishes.py) — этот скрипт чинит ТОЛЬКО уже
испорченные 14 строк, тем же механизмом, что код использует сам:
move_planned_item_to_category (app/services/plan_autoassign.py) — каскадит
PurchaseItem/WishItem, ссылающиеся на плановую позицию, одним SQL UPDATE,
плюс запись в журнал ФЭО (feo_history).

Перед записью скрипт ПРОВЕРЯЕТ (abort, если не так):
  - все id из --fpi-ids реально существуют, feo_category_id == --from-category
    (10712 по умолчанию), auto_created == True;
  - все ссылающиеся PurchaseItem/WishItem принадлежат ИМЕННО purchase_id=4252 /
    wish_id=206 (--purchase-id/--wish-id) — если найдётся чужая ссылка, abort
    (значит список id собран неверно, нужно пересчитать).

РЕЖИМЫ: без --apply — отчёт печатается, вся работа идёт в ОДНОЙ транзакции,
которая откатывается (ROLLBACK), безопасно гонять повторно; --apply — та же
работа, в конце COMMIT. НЕ запускать здесь (в песочнице) против прода.

ЗАПУСК (по образцу соседних backend/scripts/*.py, backend/scripts НЕ
примонтирован volume'ом — нужен docker cp перед запуском):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/fix_04252_feo_category.py \\
        vsks_crm-backend_a-1:/app/scripts/fix_04252_feo_category.py
    docker exec vsks_crm-backend_a-1 python -m scripts.fix_04252_feo_category
    (повторить с --apply, когда отчёт одобрен)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.wish_item import WishItem  # noqa: E402
from app.services.plan_autoassign import move_planned_item_to_category  # noqa: E402

_DEFAULT_FPI_IDS = list(range(43143, 43157))  # 43143..43156 включительно


async def main_async(args: argparse.Namespace) -> int:
    fpi_ids = args.fpi_ids or _DEFAULT_FPI_IDS
    lines: list[str] = []

    async with async_session() as db:
        try:
            rows = (await db.execute(
                select(FeoPlannedItem).where(FeoPlannedItem.id.in_(fpi_ids))
            )).scalars().all()
            found_ids = {r.id for r in rows}
            missing = set(fpi_ids) - found_ids
            if missing:
                print(f"ABORT: плановые позиции не найдены: {sorted(missing)}")
                return 1

            bad_cat = [r for r in rows if r.feo_category_id != args.from_category]
            if bad_cat:
                print(
                    "ABORT: не все позиции в ожидаемой протухшей категории "
                    f"{args.from_category}: {[(r.id, r.feo_category_id) for r in bad_cat]}"
                )
                return 1

            not_auto = [r for r in rows if not r.auto_created]
            if not_auto:
                print(
                    "ABORT: среди переданных id есть НЕ auto_created позиции (человеческий план, "
                    f"трогать нельзя этим скриптом): {[r.id for r in not_auto]}"
                )
                return 1

            # Проверка "ссылки только из purchase_id/wish_id" — иначе список id
            # собран неверно (задевает чужую закупку/заявку).
            pi_rows = (await db.execute(
                select(PurchaseItem.id, PurchaseItem.purchase_id, PurchaseItem.feo_planned_item_id)
                .where(PurchaseItem.feo_planned_item_id.in_(fpi_ids))
            )).all()
            bad_pi = [(pid, purch_id, fid) for pid, purch_id, fid in pi_rows if purch_id != args.purchase_id]
            if bad_pi:
                print(f"ABORT: PurchaseItem ссылается на чужую закупку: {bad_pi}")
                return 1

            wi_rows = (await db.execute(
                select(WishItem.id, WishItem.wish_id, WishItem.feo_planned_item_id)
                .where(WishItem.feo_planned_item_id.in_(fpi_ids))
            )).all()
            bad_wi = [(wid, wish_id, fid) for wid, wish_id, fid in wi_rows if wish_id != args.wish_id]
            if bad_wi:
                print(f"ABORT: WishItem ссылается на чужую заявку: {bad_wi}")
                return 1

            lines.append(
                f"=== Починка ФЭО-категории: закупка id={args.purchase_id} / заявка id={args.wish_id} — "
                f"{len(rows)} плановых позиций {args.from_category} -> {args.to_category} ==="
            )
            for fpi in rows:
                lines.append(
                    f"  FeoPlannedItem id={fpi.id} «{fpi.name}»: feo_category_id "
                    f"{fpi.feo_category_id} -> {args.to_category} "
                    f"(и все PurchaseItem/WishItem, ссылающиеся на неё)"
                )
                await move_planned_item_to_category(db, fpi, args.to_category)

        finally:
            if args.apply:
                await db.commit()
            else:
                await db.rollback()

    print("\n".join(lines))
    print()
    print("=== РЕЖИМ: COMMIT (--apply) ===" if args.apply else "=== РЕЖИМ: DRY-RUN (без --apply, откат) ===")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--purchase-id", type=int, default=4252, help="id закупки РЕЕ-2026-04252")
    parser.add_argument("--wish-id", type=int, default=206, help="id заявки №206")
    parser.add_argument("--from-category", type=int, default=10712, help="протухшая категория (товара)")
    parser.add_argument("--to-category", type=int, default=10711, help="верная категория (шапки заявки)")
    parser.add_argument(
        "--fpi-ids", type=int, nargs="*", default=None,
        help="id плановых позиций для переноса (по умолчанию 43143..43156)",
    )
    parser.add_argument("--apply", action="store_true", help="закоммитить изменения (по умолчанию — dry-run)")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
