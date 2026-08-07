#!/usr/bin/env python3
"""
Легаси-отчёт: закупки в PLANNED_STATUSES без привязки к плановой позиции
(feo_planned_item_id IS NULL) — задача владельца «закупки вне плана не бывает»
(план zany-fluttering-mountain.md, шаг 3, легаси-абзац, сессия 2026-08-07).

ТОЛЬКО ОТЧЁТ — ничего не создаёт и не меняет в БД. Симулирует, что сделало бы
применение той же логики автозаведения, что и Шаг 3
(app.routers.wishes._auto_assign_planned_items): для каждой позиции без
feo_planned_item_id — точный дедуп по нормализованному имени (trim+lower)
в пределах категории; если активная FeoPlannedItem с таким именем уже есть —
позиция привязалась бы к ней (рост плана = 0, план не задваивается); если нет —
создалась бы новая плановая строка на сумму total_price позиции (первая
позиция с таким именем в категории «платит» за рост, дубли внутри одной
категории просто присоединяются к уже посчитанной новой строке).

Печатает разбивку по субсидиям и категориям: сколько позиций без привязки,
сколько новых плановых строк создалось бы, на сколько вырос бы план каждой
категории.

Запуск (внутри контейнера backend, БД смонтирована как vsks_crm-db-1):
    docker exec vsks_crm-backend-1 python /app/scripts/legacy_report_unlinked_purchase_items.py

Применение (перевод отчёта в реальные изменения БД) — ОТДЕЛЬНЫЙ скрипт,
запускается только после того, как владелец увидел этот отчёт и подтвердил
цифры (см. план, раздел «Риски»: легаси-скрипт трогает боевые данные, дамп
БД до применения обязателен).
"""
import asyncio
import os
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.feo_category import FeoCategory  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.routers.purchase_budget import PLANNED_STATUSES  # noqa: E402


async def main() -> None:
    async with async_session() as db:
        rows = (await db.execute(
            select(
                PurchaseItem.id,
                PurchaseItem.item_name,
                PurchaseItem.total_price,
                PurchaseItem.feo_category_id,
                Purchase.id.label("purchase_id"),
                Purchase.purchase_number,
                Purchase.feo_category_id.label("purchase_feo_category_id"),
                Purchase.subsidy_id,
                Purchase.status,
            )
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(
                Purchase.status.in_(list(PLANNED_STATUSES)),
                PurchaseItem.feo_planned_item_id.is_(None),
            )
        )).all()

        if not rows:
            print("Позиций закупок без привязки к плановой позиции не найдено — легаси-долга нет.")
            return

        subsidy_ids = {r.subsidy_id for r in rows if r.subsidy_id}
        subsidy_names: dict[int, str] = {}
        if subsidy_ids:
            subs = (await db.execute(
                select(Subsidy.id, Subsidy.name).where(Subsidy.id.in_(subsidy_ids))
            )).all()
            subsidy_names = {s.id: s.name for s in subs}

        cat_ids = {(r.feo_category_id or r.purchase_feo_category_id) for r in rows}
        cat_ids.discard(None)
        cat_names: dict[int, str] = {}
        if cat_ids:
            cats = (await db.execute(
                select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids))
            )).all()
            cat_names = {c.id: c.name for c in cats}

        # Существующие активные плановые позиции по затронутым категориям — чтобы
        # симулировать дедуп ровно как это делает _auto_assign_planned_items.
        existing_fpi_keys: set[tuple] = set()
        if cat_ids:
            fpis = (await db.execute(
                select(FeoPlannedItem.feo_category_id, FeoPlannedItem.name)
                .where(FeoPlannedItem.feo_category_id.in_(cat_ids), FeoPlannedItem.is_active == True)
            )).all()
            existing_fpi_keys = {(f.feo_category_id, (f.name or "").strip().lower()) for f in fpis}

        no_category_rows = []
        total_items_no_link = 0
        by_subsidy_cat: dict[tuple, dict] = defaultdict(lambda: {
            "item_count": 0,
            "total_amount": Decimal("0"),
            "attach_existing": 0,
            "new_keys": set(),
            "growth": Decimal("0"),
        })
        simulated_new_keys: set[tuple] = set()

        for r in rows:
            eff_cat = r.feo_category_id or r.purchase_feo_category_id
            total_items_no_link += 1
            if not eff_cat:
                no_category_rows.append(r)
                continue
            norm_name = (r.item_name or "").strip().lower()
            key = (eff_cat, norm_name)
            bucket = by_subsidy_cat[(r.subsidy_id, eff_cat)]
            bucket["item_count"] += 1
            bucket["total_amount"] += Decimal(str(r.total_price or 0))

            if key in existing_fpi_keys:
                bucket["attach_existing"] += 1
            elif key in simulated_new_keys:
                # Дубль внутри категории — присоединится к уже посчитанной новой
                # строке (первая позиция с этим именем), роста плана НЕ добавляет.
                pass
            else:
                simulated_new_keys.add(key)
                bucket["new_keys"].add(key)
                bucket["growth"] += Decimal(str(r.total_price or 0))

        print("=" * 100)
        print("ЛЕГАСИ-ОТЧЁТ: позиции закупок (PLANNED_STATUSES) без feo_planned_item_id")
        print("=" * 100)
        print(f"Всего позиций без привязки к плану: {total_items_no_link}")
        if no_category_rows:
            print(
                f"  из них БЕЗ категории ФЭО (ни у позиции, ни у закупки) — "
                f"не с чем сопоставить, требуется ручной разбор: {len(no_category_rows)}"
            )
            for r in no_category_rows[:20]:
                print(f"    закупка №{r.purchase_number or r.purchase_id} — «{r.item_name or ''}»")
            if len(no_category_rows) > 20:
                print(f"    ... и ещё {len(no_category_rows) - 20}")
        print()

        grand_new_rows = 0
        grand_growth = Decimal("0")
        grand_attach = 0

        def _sort_key(kv):
            (sid, cid), _ = kv
            return (subsidy_names.get(sid) or "", cat_names.get(cid) or "")

        for (subsidy_id, cat_id), b in sorted(by_subsidy_cat.items(), key=_sort_key):
            sub_name = subsidy_names.get(subsidy_id, f"#{subsidy_id}" if subsidy_id else "(без субсидии)")
            cat_name = cat_names.get(cat_id, f"#{cat_id}")
            new_rows = len(b["new_keys"])
            grand_new_rows += new_rows
            grand_growth += b["growth"]
            grand_attach += b["attach_existing"]
            print(f"Субсидия «{sub_name}» / категория «{cat_name}» (id={cat_id}):")
            print(f"  позиций без привязки: {b['item_count']}, их сумма: {b['total_amount']:,.2f} ₽")
            print(f"  создалось бы новых плановых строк: {new_rows}")
            print(f"  привязалось бы к уже существующим плановым позициям: {b['attach_existing']}")
            print(f"  рост плана категории (Σ amount новых строк): {b['growth']:,.2f} ₽")
            print()

        print("=" * 100)
        print(
            f"ИТОГО: {grand_new_rows} новых плановых строк, "
            f"{grand_attach} позиций присоединились бы к уже существующим, "
            f"суммарный рост плана: {grand_growth:,.2f} ₽"
        )
        print("=" * 100)
        print("Ничего не изменено в БД — это отчёт. Применение (реальное создание/привязка) — отдельный шаг, только после подтверждения владельца и дампа БД.")


if __name__ == "__main__":
    asyncio.run(main())
