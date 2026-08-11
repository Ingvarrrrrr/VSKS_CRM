#!/usr/bin/env python3
"""
Миграция «план категории ФЭО → плановая позиция внутри категории».

ПРИЧИНА (задача владельца). У FeoCategory есть поля planned_quantity и
planned_amount — план, записанный прямо на категории («безымянными» полями),
причём planned_amount — это ЦЕНА ЗА ЕДИНИЦУ, а не сумма (итог = planned_quantity
× planned_amount). У FeoPlannedItem (Ур.5, «плановые позиции внутри категории»)
свой amount — уже СУММА, а не цена за единицу. Владелец требует, чтобы ВСЁ
планирование жило записями внутри категории («плановыми позициями»), а не
безымянными полями на самой категории — так план видно построчно (что именно
запланировано), а не одним числом без названия.

Расчёт (app/services/feo_plan.py, compute_feo_plan_tree) уже умеет читать ОБА
источника: план листа = planned_quantity × planned_amount, а если эти поля не
заданы — Σ amount активных FeoPlannedItem того же листа (fallback). Поэтому
эта миграция НЕ трогает формулу расчёта — она просто переносит число с полей
категории в запись внутри неё, соблюдая тот же итог.

⚠️ ТОЛЬКО ЛИСТЬЯ. Мигрируются только категории БЕЗ дочерних категорий. У
категории-ГРУППЫ (есть дети) собственные planned_quantity/planned_amount в
compute_feo_plan_tree вообще не участвуют в расчёте — план группы это Σ плана
её детей (own-часть группы всегда даёт 0, см. docstring compute_feo_plan_tree).
Fallback на Σ FeoPlannedItem тоже считается только по leaf_ids. Если создать
плановую позицию на группе, она осядет в БД, но НЕ попадёт ни в один расчёт —
получится «план N ₽», которого нет ни в одной формуле. Такие категории (на
боевых данных — ровно одна, id 907 «Специализированные средства передвижения -
прицепы, лодки, квадроциклы», 6 детей) не трогаются, идут в --report с
причиной «категория-группа: собственный план не участвует в расчёте (план
берётся с детей)».

ПРАВИЛА ОТБОРА (проверены замером на копии боевой базы — см. план задачи,
менять их нельзя без нового замера):

Кандидат — категория-ЛИСТ с planned_quantity > 0 AND planned_amount > 0,
подтверждённая ОДНИМ ИЗ ДВУХ независимых классов:

  Класс «бюджет» — budget IS NOT NULL AND
      abs(planned_quantity * planned_amount - budget) <= 0.01.
  Если произведение planned_quantity × planned_amount сходится с
  финансированием по ФЭО (budget), значит planned_amount — действительно
  цена за единицу, а не что-то другое. Замер на копии боевой базы: 230
  категорий.

  Класс «количество = 1» — planned_quantity = 1. Единственный риск всей
  миграции — что в planned_amount на самом деле лежит не цена за единицу, а
  готовая СУММА (тогда перенос её как unit-цены исказил бы план). Но при
  planned_quantity = 1 цена за единицу и сумма — это одно и то же число:
  толковать нечего, произведение равно самому planned_amount при любом из
  двух прочтений поля. Перенос точен по построению, без допущений о
  семантике — budget тут ничего не подтверждает и не опровергает, поэтому
  этот класс применяется, даже если budget не задан или расходится. Замер на
  копии боевой базы: ещё 99 категорий (сверх уже подтверждённых бюджетом).

Категории, не подпадающие НИ под один класс (включая случай, когда budget не
задан/расходится И planned_quantity != 1), НЕ трогаем — они летят в --report
как «остались в старом формате».

Дальше по каждому кандидату:
  1. Если у категории уже есть активные FeoPlannedItem с Σ amount > 0:
     - если |Σ amount − planned_quantity×planned_amount| <= 0.01 → план УЖЕ
       перенесён позициями (эталонный боевой случай — категория «Great Wall
       POER»): новую запись НЕ создаём (иначе план задвоится), только
       проставляем существующим позициям quantity/unit там, где они NULL
       (COALESCE), и очищаем поля категории;
     - иначе → категория ПРОПУСКАЕТСЯ целиком (поля и позиции расходятся,
       трогать нельзя — непонятно, что из двух источников правда), в отчёт.
  2. Иначе создаём одну новую FeoPlannedItem:
       feo_category_id = категория, quantity = planned_quantity,
       unit = unit категории,
       amount = (Decimal(planned_quantity) × Decimal(planned_amount)).quantize(0.01),
       is_active = True, notes = 'перенесено из плана категории'.
     Имя записи: если среди позиций закупок этой категории
     (purchase_items.feo_category_id = cat.id) ровно ОДНО РАЗЛИЧНОЕ непустое
     item_name — берём его (обрезано до 500 символов); иначе — имя категории.
  3. После этого у категории planned_quantity = NULL, planned_amount = NULL
     (unit категории НЕ трогаем — он остаётся для UI формы категории).

ПРОВЕРКА (обязательна, это и есть приёмка миграции). До изменений считается
compute_feo_plan_tree по ВСЕМ субсидиям и запоминаются по каждой категории:
plan_manual, plan, display, qty_plan, display_quantity, ordered, over, fact,
excess_over_feo, residual. После изменений (db.flush(); db.expire_all())
считается заново и сравнивается. Расхождение больше 0.005 хотя бы по одному
полю хотя бы у одной категории → печатаются подробности и делается ROLLBACK
с ненулевым кодом выхода, ДАЖЕ если передан --apply (миграция не должна
поменять ни одно число в дереве плана — только переложить его между
хранилищами). Отдельно печатается таблица ИТОГО по субсидиям (Σ display
корневых категорий, parent_id IS NULL) до/после.

ФЛАГИ:
  --apply         без него — dry-run: показывает, что было бы сделано, и в
                   конце всегда ROLLBACK (по умолчанию ничего не меняется);
  --report PATH   CSV (utf-8-sig, разделитель «;», открывается в Excel) со
                   списком категорий, оставшихся в старом формате (не
                   мигрированы — не прошли отбор, разошлись с позициями или
                   являются группой): id, subsidy_id, название субсидии, путь
                   категории (имена предков через « / »), planned_quantity,
                   planned_amount, произведение, budget, есть ли активные
                   плановые позиции и их Σ amount, количество привязанных
                   позиций закупок, причина непереноса.

Запуск (dry-run, внутри контейнера backend):
    docker compose exec -T backend python /app/scripts/migrate_category_plan_to_planned_items.py --report /tmp/old_format.csv

Применение (реальные изменения БД — ТОЛЬКО после того, как владелец увидел
0 расхождений в dry-run и подтвердил):
    docker compose exec -T backend python /app/scripts/migrate_category_plan_to_planned_items.py --apply
"""
import argparse
import asyncio
import csv
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.feo_category import FeoCategory  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.services.feo_plan import compute_feo_plan_tree  # noqa: E402

CENTS = Decimal("0.01")
TOLERANCE = Decimal("0.005")
BUDGET_TOLERANCE = Decimal("0.01")

# Поля дерева плана, которые обязаны совпасть до/после (см. compute_feo_plan_tree).
TRACKED_FIELDS = [
    "plan_manual", "plan", "display", "qty_plan", "display_quantity",
    "ordered", "over", "fact", "excess_over_feo", "residual",
]


def _dec(v) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def _category_path(by_id: dict, cat_id: int) -> str:
    """Путь категории «Предок / Родитель / Сама категория» через by_id[*].name."""
    names = []
    seen: set = set()
    cur = by_id.get(cat_id)
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        names.append(cur.name)
        cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
    return " / ".join(reversed(names))


def _diff_tree(before: dict, after: dict, cat_names: dict) -> list[dict]:
    """Список расхождений между двумя снимками compute_feo_plan_tree (> TOLERANCE).

    cat_names — простой dict {id: name}, СНЯТЫЙ ДО db.expire_all() (не ORM-объекты
    FeoCategory) — после expire_all() обращение к .name у истёкшего объекта в
    синхронном коде вне greenlet роняет MissingGreenlet."""
    mismatches = []
    for cat_id, b in before.items():
        a = after.get(cat_id)
        cat_name = cat_names.get(cat_id, f"#{cat_id}")
        if a is None:
            mismatches.append({"cat_id": cat_id, "name": cat_name, "field": "(узел)", "before": "существовал", "after": "исчез"})
            continue
        for field in TRACKED_FIELDS:
            bv = Decimal(str(b.get(field) or 0))
            av = Decimal(str(a.get(field) or 0))
            if abs(bv - av) > TOLERANCE:
                mismatches.append({"cat_id": cat_id, "name": cat_name, "field": field, "before": bv, "after": av})
    return mismatches


def _subsidy_totals(tree: dict, subsidy_ids: list[int]) -> dict[int, Decimal]:
    """Σ display корневых категорий (parent_id IS NULL) по каждой субсидии."""
    totals: dict[int, Decimal] = {sid: Decimal("0") for sid in subsidy_ids}
    for cat_id, node in tree.items():
        if node.get("parent_id") is None:
            sid = node.get("subsidy_id")
            if sid in totals:
                totals[sid] += Decimal(str(node.get("display") or 0))
    return totals


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="применить изменения (без флага — dry-run, в конце всегда ROLLBACK)")
    parser.add_argument("--report", type=str, default=None, help="путь CSV с категориями, оставшимися в старом формате")
    args = parser.parse_args()

    async with async_session() as db:
        subsidy_rows = (await db.execute(select(Subsidy.id, Subsidy.name))).all()
        subsidy_ids = [r.id for r in subsidy_rows]
        subsidy_names = {r.id: r.name for r in subsidy_rows}

        print("Считаю дерево плана ДО изменений...")
        tree_before = await compute_feo_plan_tree(db, subsidy_ids)

        cat_rows = (await db.execute(select(FeoCategory))).scalars().all()
        by_id: dict[int, FeoCategory] = {c.id: c for c in cat_rows}
        # Снимок имён ДО db.expire_all() ниже — см. docstring _diff_tree.
        cat_names_snapshot: dict[int, str] = {c.id: c.name for c in cat_rows}

        # Категории-группы — есть хотя бы один ребёнок (см. уточнение владельца:
        # собственный план группы не участвует в compute_feo_plan_tree).
        has_children: set = set()
        for c in cat_rows:
            if c.parent_id is not None:
                has_children.add(c.parent_id)

        # ---- батч-предзапросы (без N+1 в цикле по категориям) -------------
        active_fpi_rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.is_active.is_(True))
        )).scalars().all()
        active_fpi_by_cat: dict[int, list[FeoPlannedItem]] = {}
        for fpi in active_fpi_rows:
            active_fpi_by_cat.setdefault(fpi.feo_category_id, []).append(fpi)

        pi_rows = (await db.execute(
            select(PurchaseItem.feo_category_id, PurchaseItem.item_name)
            .where(PurchaseItem.feo_category_id.isnot(None))
        )).all()
        pi_names_by_cat: dict[int, list[str]] = {}
        for r in pi_rows:
            pi_names_by_cat.setdefault(r.feo_category_id, []).append(r.item_name or "")

        # ---- отбор кандидатов ---------------------------------------------
        old_format_rows: list[dict] = []  # для --report
        candidates: list[tuple] = []  # (cat, qty, amt, product, confirm_class)

        for cat in cat_rows:
            qty = _dec(cat.planned_quantity)
            amt = _dec(cat.planned_amount)
            budget = _dec(cat.budget)

            if qty is None or amt is None or qty <= 0 or amt <= 0:
                # Плана на полях категории вообще нет (или он нулевой) —
                # переносить нечего, в отчёт «старого формата» не попадает.
                continue

            product = qty * amt

            # Два независимых класса подтверждения (см. docstring):
            #  1) «бюджет» — произведение сходится с финансированием по ФЭО;
            #  2) «количество = 1» — цена за единицу и сумма это одно и то же
            #     число при qty=1, толковать нечего, перенос точен по
            #     построению вне зависимости от budget.
            budget_confirmed = budget is not None and abs(product - budget) <= BUDGET_TOLERANCE
            qty1_confirmed = qty == Decimal("1")

            reason = None
            confirm_class = None
            if budget_confirmed:
                confirm_class = "бюджет"
            elif qty1_confirmed:
                confirm_class = "количество = 1"
            elif budget is None:
                reason = "budget категории не задан, а planned_quantity != 1 — нечем подтвердить, что planned_amount это цена за единицу"
            else:
                reason = (
                    f"произведение planned_quantity×planned_amount ({product}) не совпадает "
                    f"с budget ({budget}), расхождение {abs(product - budget)}, и planned_quantity != 1"
                )

            if confirm_class is not None and cat.id in has_children:
                reason = "категория-группа: собственный план не участвует в расчёте (план берётся с детей)"
                confirm_class = None

            if reason:
                fpis = active_fpi_by_cat.get(cat.id, [])
                active_sum = sum((_dec(f.amount) or Decimal("0")) for f in fpis)
                old_format_rows.append({
                    "id": cat.id,
                    "subsidy_id": cat.subsidy_id,
                    "subsidy_name": subsidy_names.get(cat.subsidy_id, ""),
                    "path": _category_path(by_id, cat.id),
                    "planned_quantity": qty,
                    "planned_amount": amt,
                    "product": product,
                    "budget": budget,
                    "has_active_items": bool(fpis),
                    "active_items_sum": active_sum,
                    "linked_purchase_items": len(pi_names_by_cat.get(cat.id, [])),
                    "reason": reason,
                })
                continue

            candidates.append((cat, qty, amt, product, confirm_class))

        candidates_budget_count = sum(1 for c in candidates if c[4] == "бюджет")
        candidates_qty1_count = sum(1 for c in candidates if c[4] == "количество = 1")
        print(
            f"Кандидатов (лист, подтверждено бюджетом или количеством=1): {len(candidates)} "
            f"(подтверждено бюджетом: {candidates_budget_count}, подтверждено количеством=1: {candidates_qty1_count})"
        )

        created_count = 0
        cleared_only_count = 0
        skipped: list[dict] = []

        for cat, qty, amt, product, confirm_class in candidates:
            fpis = active_fpi_by_cat.get(cat.id, [])
            active_sum = sum((_dec(f.amount) or Decimal("0")) for f in fpis)

            if active_sum > 0:
                if abs(active_sum - product) <= BUDGET_TOLERANCE:
                    # План уже перенесён позициями — только дозаполняем NULL
                    # quantity/unit и чистим поля категории (Great Wall POER).
                    for f in fpis:
                        if f.quantity is None:
                            f.quantity = qty
                        if f.unit is None and cat.unit is not None:
                            f.unit = cat.unit
                    cat.planned_quantity = None
                    cat.planned_amount = None
                    cleared_only_count += 1
                else:
                    reason = (
                        f"поля и позиции расходятся: Σ amount активных плановых позиций "
                        f"({active_sum}) != planned_quantity×planned_amount ({product})"
                    )
                    skipped.append({
                        "id": cat.id, "name": cat.name, "subsidy_id": cat.subsidy_id,
                        "subsidy_name": subsidy_names.get(cat.subsidy_id, ""), "reason": reason,
                    })
                    old_format_rows.append({
                        "id": cat.id,
                        "subsidy_id": cat.subsidy_id,
                        "subsidy_name": subsidy_names.get(cat.subsidy_id, ""),
                        "path": _category_path(by_id, cat.id),
                        "planned_quantity": qty,
                        "planned_amount": amt,
                        "product": product,
                        "budget": _dec(cat.budget),
                        "has_active_items": True,
                        "active_items_sum": active_sum,
                        "linked_purchase_items": len(pi_names_by_cat.get(cat.id, [])),
                        "reason": reason,
                    })
                continue

            # Нет активных позиций (или их сумма 0) — создаём новую.
            names = sorted({n.strip() for n in pi_names_by_cat.get(cat.id, []) if n and n.strip()})
            item_name = names[0] if len(names) == 1 else cat.name
            item_name = (item_name or cat.name or "")[:500]

            new_item = FeoPlannedItem(
                feo_category_id=cat.id,
                name=item_name,
                quantity=qty,
                unit=cat.unit,
                amount=product.quantize(CENTS),
                is_active=True,
                notes="перенесено из плана категории",
            )
            db.add(new_item)
            cat.planned_quantity = None
            cat.planned_amount = None
            created_count += 1

        print(f"Создано новых плановых позиций: {created_count}")
        print(f"Только очищены поля категории (план уже был в позициях): {cleared_only_count}")
        print(f"Пропущено (поля и позиции расходятся): {len(skipped)}")
        if skipped:
            for s in skipped[:20]:
                print(f"  #{s['id']} «{s['name']}» (субсидия «{s['subsidy_name']}»): {s['reason']}")
            if len(skipped) > 20:
                print(f"  ... и ещё {len(skipped) - 20}")

        # ---- проверка: пересчитать дерево и сравнить -----------------------
        await db.flush()
        db.expire_all()
        print("Считаю дерево плана ПОСЛЕ изменений...")
        tree_after = await compute_feo_plan_tree(db, subsidy_ids)

        totals_before = _subsidy_totals(tree_before, subsidy_ids)
        totals_after = _subsidy_totals(tree_after, subsidy_ids)

        print()
        print("=" * 100)
        print("ИТОГО ПО СУБСИДИЯМ (Σ display корневых категорий)")
        print("=" * 100)
        totals_mismatch = False
        for sid in sorted(subsidy_ids, key=lambda x: subsidy_names.get(x, "")):
            b = totals_before.get(sid, Decimal("0"))
            a = totals_after.get(sid, Decimal("0"))
            diff = abs(b - a)
            mark = ""
            if diff > TOLERANCE:
                mark = "  <-- РАСХОЖДЕНИЕ"
                totals_mismatch = True
            print(f"  «{subsidy_names.get(sid)}» (id={sid}): до={b:,.2f} ₽  после={a:,.2f} ₽  разница={diff:,.2f} ₽{mark}")
        print()

        mismatches = _diff_tree(tree_before, tree_after, cat_names_snapshot)
        print("=" * 100)
        if not mismatches:
            print("ПРОВЕРКА: 0 расхождений по всем полям дерева плана (plan_manual/plan/display/qty_plan/"
                  "display_quantity/ordered/over/fact/excess_over_feo/residual).")
        else:
            print(f"ПРОВЕРКА ПРОВАЛЕНА: найдено {len(mismatches)} расхождений (> {TOLERANCE}):")
            for m in mismatches:
                print(f"  категория #{m['cat_id']} «{m['name']}», поле «{m['field']}»: было {m['before']} -> стало {m['after']}")
        print("=" * 100)

        # ---- CSV-отчёт по категориям старого формата ------------------------
        if args.report:
            with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "id", "subsidy_id", "название субсидии", "путь категории",
                    "planned_quantity", "planned_amount", "произведение", "budget",
                    "есть активные плановые позиции", "Σ amount плановых позиций",
                    "кол-во привязанных позиций закупок", "причина непереноса",
                ])
                for row in sorted(old_format_rows, key=lambda r: (r["subsidy_name"], r["path"])):
                    writer.writerow([
                        row["id"], row["subsidy_id"], row["subsidy_name"], row["path"],
                        row["planned_quantity"], row["planned_amount"], row["product"], row["budget"],
                        "да" if row["has_active_items"] else "нет", row["active_items_sum"],
                        row["linked_purchase_items"], row["reason"],
                    ])
            print(f"CSV-отчёт ({len(old_format_rows)} категорий старого формата) записан в {args.report}")

        # ---- решение: commit / rollback -------------------------------------
        if mismatches or totals_mismatch:
            await db.rollback()
            print("ROLLBACK — расхождение в дереве плана, изменения НЕ применены (даже если был передан --apply).")
            return 1

        if args.apply:
            await db.commit()
            print("COMMIT — изменения применены.")
        else:
            await db.rollback()
            print("ROLLBACK — это был dry-run (--apply не передан), изменения НЕ применены.")

        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
