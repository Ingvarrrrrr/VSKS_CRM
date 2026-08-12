#!/usr/bin/env python3
"""
Бэкфилл «закупка сама становится планом» — плановые позиции ФЭО для позиций
закупок, созданных В ОБХОД заявки.

ПРИЧИНА (задача владельца, 2026-08-12). Категория 3716 «Приобретение
брендированных футболок участников финала соревнований» (МИНПРОС) имеет
финансирование по ФЭО 175 000 ₽, НИ ОДНОЙ плановой позиции и закупку на
149 282,50 ₽ в статусе «Поставлено» — панель писала «план 0 · выбрано
149 282,50 · остаток −149 282,50» и «итог закупки дороже плана — требуется
согласование», хотя деньги потрачены в рамках ФЭО. Причина: автозаведение
плановой позиции (app/services/plan_autoassign.py, до переноса —
wishes.py._auto_assign_planned_items) раньше вызывалось ТОЛЬКО на пути
«заявка → закупка»; эта закупка создана в обход заявки, поэтому позиция
осталась с feo_category_id, но без feo_planned_item_id и без единой строки
плана в своей категории. С этой сессии purchases.py тоже зовёт автозаведение
(update_purchase / patch_purchase_item) — но ТОЛЬКО для будущих правок. Этот
скрипт — разовый бэкфилл уже существующих осиротевших позиций.

ПРАВИЛА ОТБОРА.

Кандидат — PurchaseItem с:
  - feo_category_id IS NOT NULL (СВОЯ категория позиции — НЕ фолбэк на
    Purchase.feo_category_id целиком; проверено на боевой копии: у позиции
    #2770 категории 3716 feo_category_id стоит НА САМОЙ ПОЗИЦИИ, 3677 — это
    категория закупки целиком, другая категория той же ветки);
  - feo_planned_item_id IS NULL (ещё ни к чему не привязана);
  - Purchase.status ∈ PLANNED_STATUSES (plan_schedule/work_in_progress/
    contracted/ordered/delivered/paid — тот же набор, что везде в проекте
    считает «реальный» план/факт, app.routers.purchase_budget.PLANNED_STATUSES);
    закупки в 'wishes' (скрыта до одобрения), 'cancelled', 'split' вне
    жизненного цикла плана — заводить им план рано/незачем.

РАСШИРЕНИЕ (сессия 2026-08-12, часть 2 — задача владельца «Разобрано по
данным: ... Должно уже быть за всё», распространить бэкфилл на ВСЕ
непривязанные позиции). ДО этой правки категория подходила для бэкфилла,
ТОЛЬКО если плана не было вовсе (ни активных FeoPlannedItem, ни ручных полей) —
любая категория, где план в каком-то виде уже существовал, пропускалась
целиком, даже если рядом лежали другие непривязанные позиции той же
категории. Теперь категория подходит для бэкфилла, ЕСЛИ у неё:
  - НЕТ собственного «ручного плана» в полях категории (planned_quantity > 0
    AND planned_amount > 0 — та же формула, что и в compute_feo_plan_tree;
    там СВОЯ семантика ввода плана, трогать нельзя).
Наличие уже существующих активных FeoPlannedItem категорию БОЛЬШЕ НЕ
дисквалифицирует — план в такой категории просто вырастет (дозаведутся
позиции для оставшихся непривязанных кандидатов); это тоже отдельно попадает
в отчёт («категорий, где план УЖЕ был»), чтобы владелец видел рост явно, а
не только «появление» плана с нуля. Категории-НАПРАВЛЕНИЯ (с подкатегориями)
участвуют наравне с листьями — feo_category_id позиции закупки может
указывать и на них (боевой пример — «Бинт марлевый» на категории 3677
«Окружные»); после задачи 1 (compute_feo_plan_tree суммирует собственные
плановые позиции узла с детьми) такой план теперь виден в дереве.

Дедуп — ТОЧНОЕ совпадение нормализованного имени (app.services.text_match.
normalize — тот же движок, что у plan_autoassign.py и создания плановой
позиции руками) В ПРЕДЕЛАХ ОДНОЙ категории: несколько кандидатов с одинаковым
именем схлопываются в ОДНУ новую FeoPlannedItem (auto_created=True); quantity/
amount новой записи — Σ quantity/Σ total_price всех дедуплицированных позиций,
unit — берётся у первой позиции группы, где он задан. Все позиции группы
привязываются (feo_planned_item_id) к этой одной записи. Дедуп — ТОЛЬКО среди
кандидатов этого запуска; с уже существующими активными FeoPlannedItem
категории (если они есть) новые записи не сливаются — даже при совпадении
имени заводится отдельная позиция (сохранение поведения «как есть», задача
не просила слияние с существующим планом).

⚠️ ОТЛИЧИЕ от backend/scripts/migrate_category_plan_to_planned_items.py: там
числа НЕ должны были поменяться (перенос одного и того же плана между двумя
хранилищами), поэтому скрипт откатывался при ЛЮБОМ расхождении дерева плана.
ЗДЕСЬ числа МЕНЯЮТСЯ ОСОЗНАННО: план вырастает с нуля (или с «ручного» числа,
которого не было) до суммы уже состоявшихся закупок, а «перерасход факта над
планом» (compute_feo_plan_tree.excess_fact_over_plan) на этих листьях
закономерно исчезает — именно это и есть цель бэкфилла. Поэтому вместо
«откат при любом расхождении» скрипт печатает ТАБЛИЦУ ИЗМЕНЕНИЙ (план до →
после, превышение факт>план до → после, сколько позиций затронуто) по каждой
затронутой категории и ИТОГ по субсидиям, плюс отдельно считает, у скольких
категорий превышение исчезло. Откат — ТОЛЬКО при технической ошибке
(исключение при записи), не по результату сравнения чисел.

ДВА ДОПОЛНИТЕЛЬНЫХ РАЗДЕЛА ОТЧЁТА (часть 2, см. РАСШИРЕНИЕ выше):
  1) «Позиций попало в категории, где план УЖЕ был» — сколько кандидатов
     привязано к категориям, у которых на момент запуска уже была хотя бы
     одна активная FeoPlannedItem (эти категории не появляются в плане
     впервые, а РАСТУТ — важно показать отдельно от «плана не было вовсе»).
  2) «Новое превышение план > ручной план» — категории (в т.ч. родительские
     направления, за счёт rollup), где compute_feo_plan_tree.
     excess_plan_over_manual ПОСЛЕ бэкфилла стало > 0 (и/или выросло), со
     старым/новым значением. Владелец должен увидеть этот список ДО --apply
     и решить, что уменьшать вручную (или согласовать превышение отдельно,
     см. app/routers/plan_excess.py).

ФЛАГИ:
  --apply         без него — dry-run: показывает, что было бы сделано, и в
                   конце всегда ROLLBACK (по умолчанию ничего не меняется);
  --report PATH   CSV (utf-8-sig, разделитель «;», Excel) со всеми затронутыми
                   и всеми пропущенными категориями и причиной.

Запуск (dry-run, внутри контейнера backend):
    docker compose exec -T backend python /app/scripts/backfill_plan_items_from_purchases.py

Применение (реальные изменения БД — ТОЛЬКО после того, как владелец увидел
таблицу изменений в dry-run и подтвердил):
    docker compose exec -T backend python /app/scripts/backfill_plan_items_from_purchases.py --apply
"""
import argparse
import asyncio
import csv
import os
import sys
from collections import defaultdict
from decimal import Decimal
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.feo_category import FeoCategory  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.routers.purchase_budget import PLANNED_STATUSES  # noqa: E402
from app.services.feo_plan import compute_feo_plan_tree  # noqa: E402
from app.services.text_match import normalize  # noqa: E402

CENTS = Decimal("0.01")
TOLERANCE = Decimal("0.005")


def _dec(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def _category_path(by_id: dict, cat_id: int) -> str:
    """Путь категории «Предок / Родитель / Сама категория» — та же логика,
    что и в migrate_category_plan_to_planned_items.py (не импортируем оттуда,
    это самостоятельный offline-скрипт с собственным маленьким хелпером)."""
    names = []
    seen: set = set()
    cur = by_id.get(cat_id)
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        names.append(cur.name)
        cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
    return " / ".join(reversed(names))


def _tree_num(tree: dict, cat_id: int, field: str) -> Decimal:
    node = tree.get(cat_id)
    if node is None:
        return Decimal("0")
    return Decimal(str(node.get(field) or 0))


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
    parser.add_argument("--report", type=str, default=None, help="путь CSV со всеми затронутыми/пропущенными категориями")
    args = parser.parse_args()

    async with async_session() as db:
        # ---- кандидаты -------------------------------------------------
        cand_rows = (await db.execute(
            select(PurchaseItem)
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .where(PurchaseItem.feo_category_id.isnot(None))
            .where(PurchaseItem.feo_planned_item_id.is_(None))
            .where(Purchase.status.in_(list(PLANNED_STATUSES)))
            .order_by(PurchaseItem.feo_category_id, PurchaseItem.purchase_id, PurchaseItem.id)
        )).scalars().all()

        if not cand_rows:
            print("Кандидатов нет — все позиции закупок с категорией ФЭО уже привязаны к плановой позиции (или таких категорий нет).")
            return 0

        candidates_by_cat: dict[int, list[PurchaseItem]] = defaultdict(list)
        for pi in cand_rows:
            candidates_by_cat[pi.feo_category_id].append(pi)
        cat_ids = sorted(candidates_by_cat.keys())
        print(f"Кандидатов (позиций закупок без плановой позиции, с собственной категорией ФЭО): {len(cand_rows)}, категорий: {len(cat_ids)}")

        # Все категории (для путей предков в отчёте нужны и не-кандидаты)
        all_cat_rows = (await db.execute(select(FeoCategory))).scalars().all()
        cat_by_id: dict[int, FeoCategory] = {c.id: c for c in all_cat_rows}
        # Снимок имени/субсидии ДО db.expire_all() ниже (после мутаций) — обращение
        # к атрибутам истёкшего ORM-объекта вне greenlet роняет MissingGreenlet
        # (та же ловушка, что описана в docstring migrate_category_plan_to_planned_items.py).
        cat_names_snapshot: dict[int, str] = {c.id: c.name for c in all_cat_rows}
        cat_subsidy_snapshot: dict[int, Optional[int]] = {c.id: c.subsidy_id for c in all_cat_rows}

        existing_active = (await db.execute(
            select(FeoPlannedItem.feo_category_id)
            .where(FeoPlannedItem.feo_category_id.in_(cat_ids))
            .where(FeoPlannedItem.is_active.is_(True))
        )).scalars().all()
        cats_with_active_plan = set(existing_active)

        subsidy_rows = (await db.execute(select(Subsidy.id, Subsidy.name))).all()
        subsidy_names = {r.id: r.name for r in subsidy_rows}

        # ---- отбор категорий --------------------------------------------
        # РАСШИРЕНИЕ (часть 2, см. docstring): «уже есть активные плановые
        # позиции» БОЛЬШЕ НЕ дисквалифицирует категорию — она просто растёт.
        # Дисквалифицирует ТОЛЬКО ручной план в полях категории (своя
        # семантика, старый формат, planned_quantity×planned_amount).
        qualifying_cat_ids: list[int] = []
        already_had_plan_cat_ids: set[int] = set()
        skipped: list[dict] = []
        for cid in cat_ids:
            cat = cat_by_id.get(cid)
            if cat is None:
                skipped.append({
                    "id": cid, "path": f"#{cid} (удалена из справочника)",
                    "subsidy_id": None, "subsidy_name": "",
                    "candidates": len(candidates_by_cat[cid]),
                    "reason": "категория удалена из справочника FeoCategory — не создаём план на несуществующей категории",
                })
                continue
            qty = _dec(cat.planned_quantity)
            amt = _dec(cat.planned_amount)
            has_manual_plan = qty > 0 and amt > 0
            if has_manual_plan:
                skipped.append({
                    "id": cid, "path": _category_path(cat_by_id, cid),
                    "subsidy_id": cat.subsidy_id, "subsidy_name": subsidy_names.get(cat.subsidy_id, ""),
                    "candidates": len(candidates_by_cat[cid]),
                    "reason": f"есть ручной план в полях категории ({qty}×{amt}={qty*amt}) — своя семантика, не трогаем",
                })
                continue
            qualifying_cat_ids.append(cid)
            if cid in cats_with_active_plan:
                already_had_plan_cat_ids.add(cid)

        already_had_plan_candidates = sum(len(candidates_by_cat[cid]) for cid in already_had_plan_cat_ids)
        print(f"Категорий, подходящих для бэкфилла: {len(qualifying_cat_ids)}")
        print(f"  из них — план уже был (категория ВЫРАСТЕТ): {len(already_had_plan_cat_ids)} категорий, "
              f"{already_had_plan_candidates} позиций закупок")
        print(f"  из них — плана не было вовсе (категория появится в плане впервые): "
              f"{len(qualifying_cat_ids) - len(already_had_plan_cat_ids)} категорий")
        print(f"Категорий пропущено (ручной план в полях категории / категория удалена): {len(skipped)}")
        if skipped:
            for s in skipped[:20]:
                print(f"  #{s['id']} «{cat_names_snapshot.get(s['id'], s['path'])}» (субсидия «{s['subsidy_name']}», {s['candidates']} кандидат(ов)): {s['reason']}")
            if len(skipped) > 20:
                print(f"  ... и ещё {len(skipped) - 20}")

        # Пути категорий для итогового отчёта — считаем СЕЙЧАС, пока cat_by_id ещё
        # не истёк (см. предупреждение у cat_names_snapshot выше): после
        # db.expire_all() ниже (после мутаций) _category_path не сможет читать
        # .name/.parent_id живых ORM-объектов вне greenlet. all_cat_paths — ПО
        # ВСЕМ категориям (не только qualifying_cat_ids), нужно для отчёта
        # «новое превышение план>ручной план» — он смотрит и на родительские
        # направления, куда excess_plan_over_manual поднимается rollup'ом и
        # которые сами могли не быть кандидатами на бэкфилл.
        qualifying_cat_paths: dict[int, str] = {cid: _category_path(cat_by_id, cid) for cid in qualifying_cat_ids}
        all_cat_paths: dict[int, str] = {cid: _category_path(cat_by_id, cid) for cid in cat_by_id}

        if not qualifying_cat_ids:
            print("Применять нечего — ни одна категория не подошла под отбор.")
            if args.report:
                with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow(["id", "путь категории", "subsidy_id", "субсидия", "кандидатов", "причина пропуска"])
                    for s in skipped:
                        writer.writerow([s["id"], s["path"], s["subsidy_id"], s["subsidy_name"], s["candidates"], s["reason"]])
                print(f"CSV-отчёт записан в {args.report}")
            await db.rollback()
            return 0

        subsidy_ids_touched = sorted({cat_by_id[cid].subsidy_id for cid in qualifying_cat_ids if cat_by_id[cid].subsidy_id is not None})

        print("Считаю дерево плана ДО изменений...")
        tree_before = await compute_feo_plan_tree(db, subsidy_ids_touched)
        totals_before = _subsidy_totals(tree_before, subsidy_ids_touched)

        # ---- создание плановых позиций + привязка ------------------------
        category_reports: list[dict] = []
        total_new_items = 0
        total_linked_positions = 0
        try:
            for cid in qualifying_cat_ids:
                cat = cat_by_id[cid]
                items = candidates_by_cat[cid]
                groups: dict[str, list[PurchaseItem]] = defaultdict(list)
                for pi in items:
                    key = normalize(pi.item_name or "") or f"__noname_{pi.id}__"
                    groups[key].append(pi)

                cat_new_items = 0
                cat_linked = 0
                for group_items in groups.values():
                    first = group_items[0]
                    qty_sum = sum((_dec(g.quantity) for g in group_items), Decimal("0"))
                    amt_sum = sum((_dec(g.total_price) for g in group_items), Decimal("0"))
                    unit = next((g.unit for g in group_items if g.unit), None)
                    name = (first.item_name or cat.name or "")[:500]
                    n = len(group_items)
                    new_fpi = FeoPlannedItem(
                        feo_category_id=cid,
                        name=name,
                        quantity=qty_sum if qty_sum > 0 else None,
                        unit=unit,
                        amount=amt_sum.quantize(CENTS),
                        is_active=True,
                        notes=(
                            f"Бэкфилл (2026-08-12, «закупка сама становится планом»): перенесено "
                            f"из {n} позици{'и' if n == 1 else ('й' if n >= 5 else 'ий')} закупок вне плана"
                        ),
                        auto_created=True,
                    )
                    db.add(new_fpi)
                    await db.flush()
                    for g in group_items:
                        g.feo_planned_item_id = new_fpi.id
                        g.over_plan = False
                    cat_new_items += 1
                    cat_linked += n

                total_new_items += cat_new_items
                total_linked_positions += cat_linked
                category_reports.append({
                    "cat_id": cid,
                    "new_items": cat_new_items, "linked": cat_linked,
                    "already_had_plan": cid in already_had_plan_cat_ids,
                })

            await db.flush()
        except Exception as exc:
            await db.rollback()
            print(f"ОШИБКА при записи — ROLLBACK, изменения НЕ применены: {exc!r}")
            return 1

        print(f"Создано новых плановых позиций: {total_new_items}")
        print(f"Привязано позиций закупок к ним: {total_linked_positions}")

        db.expire_all()
        print("Считаю дерево плана ПОСЛЕ изменений...")
        tree_after = await compute_feo_plan_tree(db, subsidy_ids_touched)
        totals_after = _subsidy_totals(tree_after, subsidy_ids_touched)

        # ---- таблица изменений по категориям ------------------------------
        print()
        print("=" * 130)
        print("ТАБЛИЦА ИЗМЕНЕНИЙ ПО КАТЕГОРИЯМ")
        print("=" * 130)
        excess_resolved_count = 0
        report_rows: list[dict] = []
        for cr in sorted(
            category_reports,
            key=lambda x: (subsidy_names.get(cat_subsidy_snapshot.get(x["cat_id"]), ""), cat_names_snapshot.get(x["cat_id"]) or ""),
        ):
            cid = cr["cat_id"]
            cat_name = cat_names_snapshot.get(cid) or f"#{cid}"
            cat_subsidy_id = cat_subsidy_snapshot.get(cid)
            plan_before = _tree_num(tree_before, cid, "display")
            plan_after = _tree_num(tree_after, cid, "display")
            excess_before = _tree_num(tree_before, cid, "excess_fact_over_plan")
            excess_after = _tree_num(tree_after, cid, "excess_fact_over_plan")
            resolved = excess_before > TOLERANCE and excess_after <= TOLERANCE
            if resolved:
                excess_resolved_count += 1
            mark = "  <-- превышение исчезло" if resolved else ""
            grown_mark = "  [план УЖЕ был — категория растёт]" if cr["already_had_plan"] else ""
            print(
                f"  #{cid} «{cat_name}» (субсидия «{subsidy_names.get(cat_subsidy_id, '')}»): "
                f"позиций {cr['linked']} → {cr['new_items']} план. поз.; "
                f"план {plan_before:,.2f} -> {plan_after:,.2f} ₽; "
                f"превышение факт>план {excess_before:,.2f} -> {excess_after:,.2f} ₽{mark}{grown_mark}"
            )
            report_rows.append({
                "id": cid, "name": cat_name, "path": qualifying_cat_paths.get(cid, f"#{cid}"),
                "subsidy_id": cat_subsidy_id, "subsidy_name": subsidy_names.get(cat_subsidy_id, ""),
                "linked_positions": cr["linked"], "new_plan_items": cr["new_items"],
                "plan_before": plan_before, "plan_after": plan_after,
                "excess_before": excess_before, "excess_after": excess_after,
                "excess_resolved": "да" if resolved else "нет",
                "already_had_plan": "да" if cr["already_had_plan"] else "нет",
            })
        print("=" * 130)
        print(f"У категорий, где было превышение факта над планом, оно ИСЧЕЗЛО у: {excess_resolved_count} из {len(category_reports)}")
        print(f"Категорий, где план УЖЕ был (выросли, а не появились впервые): "
              f"{len(already_had_plan_cat_ids)} из {len(category_reports)}, "
              f"{already_had_plan_candidates} позиций закупок в них")
        print()

        print("=" * 100)
        print("ИТОГО ПО СУБСИДИЯМ (Σ display корневых категорий, только затронутые субсидии)")
        print("=" * 100)
        for sid in sorted(subsidy_ids_touched, key=lambda x: subsidy_names.get(x, "")):
            b = totals_before.get(sid, Decimal("0"))
            a = totals_after.get(sid, Decimal("0"))
            print(f"  «{subsidy_names.get(sid)}» (id={sid}): до={b:,.2f} ₽  после={a:,.2f} ₽  разница={a - b:,.2f} ₽")
        print("=" * 100)

        # ---- НОВОЕ превышение «план больше ручного плана» после бэкфилла -----
        # Задача владельца (часть 2): показать ДО --apply, где после бэкфилла
        # появится/вырастет excess_plan_over_manual (compute_feo_plan_tree,
        # задача владельца п.2 сессии 2026-08-12) — «планируются одни траты, а
        # тут уже превысили», владелец должен решить, что уменьшать вручную.
        # Смотрим ВСЕ категории обеих деревьев (не только qualifying_cat_ids) —
        # превышение листа рекурсивно поднимается rollup'ом и на родительские
        # направления (см. ветку группы в compute_feo_plan_tree).
        print()
        print("=" * 130)
        print("НОВОЕ ПРЕВЫШЕНИЕ «ПЛАН > РУЧНОЙ ПЛАН» (excess_plan_over_manual) ПОСЛЕ БЭКФИЛЛА")
        print("=" * 130)
        excess_manual_rows: list[dict] = []
        all_touched_cat_ids = sorted(set(tree_after.keys()) | set(tree_before.keys()))
        for cid in all_touched_cat_ids:
            excess_before_m = _tree_num(tree_before, cid, "excess_plan_over_manual")
            excess_after_m = _tree_num(tree_after, cid, "excess_plan_over_manual")
            if excess_after_m <= TOLERANCE:
                continue
            cat_name = cat_names_snapshot.get(cid) or f"#{cid}"
            cat_subsidy_id = cat_subsidy_snapshot.get(cid)
            is_new = excess_before_m <= TOLERANCE
            print(
                f"  #{cid} «{cat_name}» (субсидия «{subsidy_names.get(cat_subsidy_id, '')}»): "
                f"превышение план>ручной план {excess_before_m:,.2f} -> {excess_after_m:,.2f} ₽"
                f"{'  <-- НОВОЕ' if is_new else '  (уже было, выросло)'}"
            )
            excess_manual_rows.append({
                "id": cid, "name": cat_name,
                "path": all_cat_paths.get(cid, f"#{cid}"),
                "subsidy_id": cat_subsidy_id, "subsidy_name": subsidy_names.get(cat_subsidy_id, ""),
                "excess_before": excess_before_m, "excess_after": excess_after_m,
                "is_new": "да" if is_new else "нет",
            })
        if not excess_manual_rows:
            print("  Нет ни одной категории с превышением плана над ручным планом после бэкфилла.")
        print("=" * 130)
        print(f"Категорий с превышением план>ручной план после бэкфилла: {len(excess_manual_rows)}")
        print()

        # ---- CSV-отчёт ------------------------------------------------------
        if args.report:
            with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "id", "название", "путь категории", "subsidy_id", "субсидия",
                    "затронуто позиций закупок", "создано плановых позиций",
                    "план до", "план после", "превышение факт>план до", "превышение факт>план после",
                    "превышение исчезло", "план уже был (категория растёт)",
                ])
                for row in report_rows:
                    writer.writerow([
                        row["id"], row["name"], row["path"], row["subsidy_id"], row["subsidy_name"],
                        row["linked_positions"], row["new_plan_items"],
                        row["plan_before"], row["plan_after"], row["excess_before"], row["excess_after"],
                        row["excess_resolved"], row["already_had_plan"],
                    ])
                writer.writerow([])
                writer.writerow(["НОВОЕ ПРЕВЫШЕНИЕ ПЛАН > РУЧНОЙ ПЛАН (excess_plan_over_manual) ПОСЛЕ БЭКФИЛЛА"])
                writer.writerow([
                    "id", "название", "путь категории", "subsidy_id", "субсидия",
                    "превышение до", "превышение после", "новое",
                ])
                for row in excess_manual_rows:
                    writer.writerow([
                        row["id"], row["name"], row["path"], row["subsidy_id"], row["subsidy_name"],
                        row["excess_before"], row["excess_after"], row["is_new"],
                    ])
                writer.writerow([])
                writer.writerow(["ПРОПУЩЕННЫЕ КАТЕГОРИИ"])
                writer.writerow(["id", "путь категории", "subsidy_id", "субсидия", "кандидатов", "причина пропуска"])
                for s in skipped:
                    writer.writerow([s["id"], s["path"], s["subsidy_id"], s["subsidy_name"], s["candidates"], s["reason"]])
            print(f"CSV-отчёт записан в {args.report}")

        # ---- решение: commit / rollback -------------------------------------
        if args.apply:
            await db.commit()
            print("COMMIT — изменения применены.")
        else:
            await db.rollback()
            print("ROLLBACK — это был dry-run (--apply не передан), изменения НЕ применены.")

        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
