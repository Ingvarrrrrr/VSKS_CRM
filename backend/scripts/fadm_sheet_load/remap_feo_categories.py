"""Пересчёт категорий ФЭО уже загруженной субсидии «ФАДМ 2026_2»/«ФАДМ
2026_2» по исправленному правилу сопоставления (AE, AF, AG) — см. задание
06.10.2026 и docstring feo_path_resolve.py: загрузчик (sheet_v2_build.py)
раньше искал категорию глобально по имени, из-за чего много плановых позиций
и позиций закупок осело в корне направления (AE) вместо подкатегории (AF/AG).

Этот скрипт НЕ пересоздаёт закупки — он только переставляет feo_category_id
у уже существующих FeoPlannedItem/PurchaseItem/Purchase, используя ТУ ЖЕ
функцию сопоставления, что и загрузчик (ПРАВИЛО №6, см. импорт
feo_path_resolve.resolve_feo_path ниже — не вторая копия правила).

СВЯЗЬ «строка листа → плановая позиция»: SheetRowV2.plan_key = (inn,
purchase_no, order_no, item_kind) — тот же ключ, что строит
sheet_v2_build.py::_build_plan_items_v2 (plan_groups_v2 группирует ВСЕ строки
листа, включая ещё не заказанные, по этому ключу; группа одна = одна
FeoPlannedItem, см. docstring PlanGroupV2 в sheet_v2_parse.py). Сама
FeoPlannedItem опознаётся по notes — загрузчик пишет туда дословно
"Создано импорт GoodsService (план Y, ключ (...))" (plan_autoassign.
create_auto_planned_item добавляет префикс "Создано ", сам текст — из
_build_plan_items_v2). Отсюда ключ можно разобрать обратно regex'ом +
ast.literal_eval и перегруппировать СВЕЖИЙ CSV листа ТЕМ ЖЕ plan_groups_v2 —
совпадение по значению ключа, не по порядку строк.

Что НЕ трогаем (см. задание):
  - FeoPlannedItem с is_feo_breakdown=True — бюджетные строки «План ФЭО
    (лист GoodsService, AE×AD)…», заведённые run_build_v2 отдельно (НЕ через
    _build_plan_items_v2, значит и notes у них другой — наш фильтр по notes
    их не заденет вовсе, но проверка is_feo_breakdown оставлена явным
    фильтром-страховкой);
  - PurchaseItem «Лимит договора …» (шапка рамочного) — у неё
    feo_planned_item_id ВСЕГДА NULL (build_framework заводит её напрямую, см.
    sheet_v2_build.py), поэтому она просто не попадает в выборку по
    feo_planned_item_id IN (...).

РЕЖИМЫ:
  без --apply — отчёт (таблица переносов, итоги, суммы план по категориям
                до/после, сверка Σ) печатается, транзакция откатывается;
  --apply     — та же работа внутри ОДНОЙ транзакции, ПЕРЕД изменением
                создаются резервные таблицы bk_<YYYYMMDD>_remap_feo_items_<sid>/
                _remap_pitems_<sid>/_remap_purchases_<sid> (CREATE TABLE AS
                SELECT только затронутых строк), затем commit.

ЗАПУСК (внутри контейнера backend — backend/scripts не смонтирован volume'ом,
см. docstring __main__.py — нужен docker cp ПЕРЕД запуском):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/fadm_sheet_load/. \\
        vsks_crm-backend_b-1:/app/scripts/fadm_sheet_load/
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/data/fadm_2026_goodsservice.csv \\
        vsks_crm-backend_b-1:/app/scripts/data/fadm_2026_goodsservice.csv
    docker exec vsks_crm-backend_b-1 python -m scripts.fadm_sheet_load.remap_feo_categories \\
        --subsidy-id 7320 --csv scripts/data/fadm_2026_goodsservice.csv
    (повторить с --apply, когда отчёт одобрен)
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

from .feo_path_resolve import FeoTree, load_feo_tree, resolve_feo_path
from .sheet_v2_parse import PlanGroupV2, SheetRowV2, parse_goodsservice_csv, plan_groups_v2

_NOTES_KEY_RE = re.compile(r"ключ (\(.*\))\)\s*$")
_LOADER_NOTE_PREFIX = "Создано импорт GoodsService (план Y, ключ "


def _parse_plan_key_from_notes(notes: Optional[str]) -> Optional[tuple]:
    if not notes or not notes.startswith(_LOADER_NOTE_PREFIX):
        return None
    m = _NOTES_KEY_RE.search(notes)
    if not m:
        return None
    try:
        key = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return None
    return key if isinstance(key, tuple) else None


@dataclass
class ItemMove:
    planned_item_id: int
    plan_key: tuple
    label: str
    amount: Decimal
    before_category_id: Optional[int]
    before_path: str
    after_category_id: Optional[int]
    after_path: str
    ambiguous: bool
    reason: str
    purchase_item_ids: list = field(default_factory=list)
    # Доп. правка 06.10.2026 (владелец): способ, которым найден after_category_id
    # (exact/prefix/common_prefix/None — None значит «не нашли дальше корня»),
    # и диагностика ОСТАНОВКИ ВЫШЕ самой глубокой доступной категории —
    # stopped_at ('root'/'af'/'ag'/'ag_global'), сырые AE/AF/AG из листа, имена
    # не подошедших детей на уровне остановки, и флаг «дальше всё равно некуда
    # идти» (у найденного узла просто нет детей — это НЕ проблема, это предел
    # дерева, не недостаток сопоставления).
    match_method: Optional[str] = None
    stopped_at: str = ""
    ae_raw: str = ""
    af_raw: str = ""
    ag_raw: str = ""
    considered_siblings: list = field(default_factory=list)
    at_max_depth: bool = False


@dataclass
class RemapResult:
    moves: list  # [ItemMove] — реально переносятся (after != before)
    staying_root: list  # [ItemMove] — остаются как были (after == before)
    ambiguous: list  # [ItemMove]
    no_sheet_row: list  # [{planned_item_id, plan_key}] — ключ не нашёлся в свежем CSV
    purchase_updates: dict  # purchase_id -> (before_cat, after_cat)
    purchase_mismatch: list  # [{purchase_id, categories}] — позиции закупки в разных категориях, не трогаем
    sums_before: dict  # category_id -> Decimal
    sums_after: dict  # category_id -> Decimal
    method_counts: dict  # 'exact'/'prefix'/'common_prefix'/'(нет глубже корня)' -> count (moves+staying)


def _category_path_str(tree: FeoTree, category_id: Optional[int]) -> str:
    if category_id is None:
        return "(нет категории)"
    node = tree.by_id.get(category_id)
    if node is None:
        return f"#{category_id} (не в дереве субсидии)"
    return " / ".join(tree.path_to(node))


async def compute_remap(db: AsyncSession, subsidy_id: int, csv_path: str) -> RemapResult:
    rows: list[SheetRowV2] = parse_goodsservice_csv(csv_path)
    groups: dict[tuple, PlanGroupV2] = plan_groups_v2(rows)

    tree = await load_feo_tree(db, subsidy_id)
    na_category = (await db.execute(
        select(FeoCategory).where(
            FeoCategory.subsidy_id == subsidy_id, FeoCategory.parent_id.is_(None),
            FeoCategory.name.ilike("не определена"),
        )
    )).scalars().first()
    na_category_id = na_category.id if na_category else None

    category_ids = [c.id for c in tree.by_id.values()]
    planned_items = (await db.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(category_ids),
            FeoPlannedItem.is_feo_breakdown.is_(False),
            FeoPlannedItem.notes.like(f"{_LOADER_NOTE_PREFIX}%"),
        )
    )).scalars().all()

    moves: list[ItemMove] = []
    staying_root: list[ItemMove] = []
    ambiguous: list[ItemMove] = []
    no_sheet_row: list[dict] = []
    sums_before: dict = defaultdict(lambda: Decimal("0"))
    sums_after: dict = defaultdict(lambda: Decimal("0"))

    purchase_item_rows = (await db.execute(
        select(PurchaseItem.id, PurchaseItem.purchase_id, PurchaseItem.feo_planned_item_id)
        .where(PurchaseItem.feo_planned_item_id.in_([p.id for p in planned_items] or [-1]))
    )).all()
    pitems_by_planned: dict[int, list[tuple]] = defaultdict(list)
    for pid, purchase_id, planned_id in purchase_item_rows:
        pitems_by_planned[planned_id].append((pid, purchase_id))

    for fpi in planned_items:
        before_cat = fpi.feo_category_id
        amount = fpi.amount or Decimal("0")
        sums_before[before_cat] += amount
        key = _parse_plan_key_from_notes(fpi.notes)
        label = f"план {key}" if key else f"план (ключ не распознан, fpi#{fpi.id})"

        if key is None or key not in groups:
            no_sheet_row.append({"planned_item_id": fpi.id, "plan_key": key, "amount": amount,
                                  "before_path": _category_path_str(tree, before_cat)})
            sums_after[before_cat] += amount
            continue

        group = groups[key]
        main = group.main_row
        result = resolve_feo_path(tree, main.feo_direction, main.feo_type, main.feo_appendix_direction)
        after_cat = result.category_id or na_category_id
        # «Дальше некуда» — у найденного узла просто нет детей в дереве (не
        # путать с «AF/AG не нашлись» — это именно отсутствие вариантов).
        at_max_depth = (result.category_id is not None
                        and not tree.kids(result.category_id))

        move = ItemMove(
            planned_item_id=fpi.id, plan_key=key, label=label, amount=amount,
            before_category_id=before_cat, before_path=_category_path_str(tree, before_cat),
            after_category_id=after_cat, after_path=_category_path_str(tree, after_cat),
            ambiguous=result.ambiguous, reason=result.reason,
            purchase_item_ids=[pid for pid, _pur in pitems_by_planned.get(fpi.id, [])],
            match_method=result.match_method, stopped_at=result.stopped_at,
            ae_raw=main.feo_direction, af_raw=main.feo_type, ag_raw=main.feo_appendix_direction,
            considered_siblings=result.considered_siblings, at_max_depth=at_max_depth,
        )
        sums_after[after_cat] += amount

        if result.ambiguous:
            ambiguous.append(move)
        elif after_cat != before_cat:
            moves.append(move)
        else:
            staying_root.append(move)

    # Purchase.feo_category_id — по позициям закупки ПОСЛЕ переноса их плана.
    planned_target = {m.planned_item_id: m.after_category_id for m in moves}
    moved_item_ids = {i for m in moves for i in m.purchase_item_ids}
    affected_purchase_ids = sorted({purchase_id for pid, purchase_id, _planned_id in purchase_item_rows
                                     if pid in moved_item_ids})
    purchase_updates: dict = {}
    purchase_mismatch: list = []
    if affected_purchase_ids:
        all_items = (await db.execute(
            select(PurchaseItem.purchase_id, PurchaseItem.id, PurchaseItem.feo_planned_item_id,
                   PurchaseItem.feo_category_id)
            .where(PurchaseItem.purchase_id.in_(affected_purchase_ids))
        )).all()
        purchases = {p.id: p for p in (await db.execute(
            select(Purchase).where(Purchase.id.in_(affected_purchase_ids))
        )).scalars().all()}
        by_purchase: dict[int, list[tuple]] = defaultdict(list)
        for purchase_id, item_id, planned_id, cat_id in all_items:
            eff_cat = planned_target.get(planned_id, cat_id)
            by_purchase[purchase_id].append((item_id, eff_cat))
        for purchase_id, items in by_purchase.items():
            cats = {c for _iid, c in items if c is not None}
            purchase = purchases.get(purchase_id)
            before_cat = purchase.feo_category_id if purchase else None
            if len(cats) == 1:
                after_cat = next(iter(cats))
                if after_cat != before_cat:
                    purchase_updates[purchase_id] = (before_cat, after_cat)
            else:
                purchase_mismatch.append({"purchase_id": purchase_id,
                                           "categories": sorted(c for c in cats)})

    method_counts: dict = defaultdict(int)
    for m in moves + staying_root:
        method_counts[m.match_method or "(нет глубже корня)"] += 1

    return RemapResult(
        moves=moves, staying_root=staying_root, ambiguous=ambiguous, no_sheet_row=no_sheet_row,
        purchase_updates=purchase_updates, purchase_mismatch=purchase_mismatch,
        sums_before=dict(sums_before), sums_after=dict(sums_after),
        method_counts=dict(method_counts),
    )


def render_report(result: RemapResult, tree: FeoTree, subsidy_id: int) -> str:
    lines = [f"=== Пересчёт категорий ФЭО — субсидия id={subsidy_id} ==="]
    lines.append(f"Переносится позиций: {len(result.moves)}")
    lines.append(f"Остаются как были (путь привёл туда же): {len(result.staying_root)}")
    lines.append(f"Неоднозначно (не трогаем): {len(result.ambiguous)}")
    lines.append(f"Ключ листа не найден в свежем CSV (не трогаем): {len(result.no_sheet_row)}")
    lines.append("")

    if result.method_counts:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(result.method_counts.items(), key=lambda kv: -kv[1]))
        lines.append(f"По способу сопоставления (переносы + остающиеся): {parts}")
        lines.append("")

    if result.moves:
        lines.append("Переносы (топ по сумме):")
        for m in sorted(result.moves, key=lambda x: -x.amount)[:30]:
            lines.append(f"  - [{m.match_method or '-'}] {m.label}: {m.amount} — "
                         f"было «{m.before_path}» -> стало «{m.after_path}»")
        if len(result.moves) > 30:
            lines.append(f"  ... и ещё {len(result.moves) - 30}")
        lines.append("")

    if result.staying_root:
        at_depth = [m for m in result.staying_root if m.at_max_depth]
        above = [m for m in result.staying_root if not m.at_max_depth]
        lines.append(f"Разбор «остаются как были» ({len(result.staying_root)}):")
        lines.append(f"  - уже в самой глубокой доступной категории (дальше в дереве детей нет): {len(at_depth)}")
        lines.append(f"  - остановились ВЫШЕ возможного (AF/AG не нашлись/пусты/неоднозначны): {len(above)}")
        if above:
            by_reason: dict = defaultdict(list)
            for m in above:
                by_reason[m.reason].append(m)
            lines.append("  По причине остановки:")
            for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
                total = sum((m.amount for m in items), Decimal("0"))
                lines.append(f"    - {reason}: {len(items)} шт. на сумму {total}")
            lines.append("  Топ примеров (AF/AG из листа и дети дерева на уровне остановки):")
            for m in sorted(above, key=lambda x: -x.amount)[:15]:
                siblings = ", ".join(m.considered_siblings) if m.considered_siblings else "(нет детей)"
                lines.append(f"    - {m.label}: {m.amount}, сейчас «{m.before_path}»")
                lines.append(f"        AF листа: {m.af_raw!r}")
                lines.append(f"        AG листа: {m.ag_raw!r}")
                lines.append(f"        дети дерева на этом уровне: {siblings}")
        lines.append("")

    if result.ambiguous:
        lines.append("Неоднозначные (оставлены как есть):")
        for m in result.ambiguous[:30]:
            lines.append(f"  - {m.label}: {m.reason} (сейчас «{m.before_path}»)")
        lines.append("")

    if result.no_sheet_row:
        total = sum((x["amount"] for x in result.no_sheet_row), Decimal("0"))
        lines.append(f"Без строки в свежем CSV: {len(result.no_sheet_row)} шт. на сумму {total} (не трогаем)")
        lines.append("")

    lines.append(f"Закупок, у которых переставится Purchase.feo_category_id: {len(result.purchase_updates)}")
    for purchase_id, (before, after) in list(result.purchase_updates.items())[:30]:
        lines.append(f"  - закупка #{purchase_id}: «{_category_path_str(tree, before)}» -> "
                      f"«{_category_path_str(tree, after)}»")
    if result.purchase_mismatch:
        lines.append(f"Закупок с позициями в РАЗНЫХ категориях (Purchase.feo_category_id НЕ трогаем): "
                      f"{len(result.purchase_mismatch)}")
        for pm in result.purchase_mismatch[:30]:
            lines.append(f"  - закупка #{pm['purchase_id']}: категории {pm['categories']}")
    lines.append("")

    lines.append("Σ плана по категориям ДО / ПОСЛЕ:")
    all_cats = sorted(set(result.sums_before) | set(result.sums_after), key=lambda c: (c is None, c))
    for cat_id in all_cats:
        before = result.sums_before.get(cat_id, Decimal("0"))
        after = result.sums_after.get(cat_id, Decimal("0"))
        marker = "  (изменилось)" if before != after else ""
        lines.append(f"  {_category_path_str(tree, cat_id)}: {before} -> {after}{marker}")

    total_before = sum(result.sums_before.values(), Decimal("0"))
    total_after = sum(result.sums_after.values(), Decimal("0"))
    ok = "OK" if total_before == total_after else "РАСХОЖДЕНИЕ!"
    lines.append(f"Σ по субсидии: {total_before} -> {total_after} [{ok}]")
    return "\n".join(lines)


async def _unique_backup_table_name(db: AsyncSession, base: str) -> str:
    """base уже существует (повторный --apply в тот же день — находка
    06.10.2026, второй прогон с улучшенным алгоритмом нашёл ДОПОЛНИТЕЛЬНЫЕ
    переносы, которые первый прогон не ловил) — добавляем числовой суффикс
    _2, _3, ..., не перезаписываем и не теряем предыдущий бэкап."""
    name = base
    suffix = 1
    while (await db.execute(text(
        "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename = :t"
    ), {"t": name})).scalar():
        suffix += 1
        name = f"{base}_{suffix}"
    return name


async def apply_remap(db: AsyncSession, result: RemapResult, subsidy_id: int) -> None:
    today = date.today().strftime("%Y%m%d")
    fpi_ids = [m.planned_item_id for m in result.moves]
    pitem_ids = [iid for m in result.moves for iid in m.purchase_item_ids]
    purchase_ids = list(result.purchase_updates.keys())

    if fpi_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_remap_feo_items_{subsidy_id}")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM feo_planned_items WHERE id = ANY(:ids)"
        ), {"ids": fpi_ids})
    if pitem_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_remap_pitems_{subsidy_id}")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM purchase_items WHERE id = ANY(:ids)"
        ), {"ids": pitem_ids})
    if purchase_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_remap_purchases_{subsidy_id}")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM purchases WHERE id = ANY(:ids)"
        ), {"ids": purchase_ids})

    for m in result.moves:
        await db.execute(text(
            "UPDATE feo_planned_items SET feo_category_id = :cat WHERE id = :id"
        ), {"cat": m.after_category_id, "id": m.planned_item_id})
        if m.purchase_item_ids:
            await db.execute(text(
                "UPDATE purchase_items SET feo_category_id = :cat WHERE id = ANY(:ids)"
            ), {"cat": m.after_category_id, "ids": m.purchase_item_ids})

    for purchase_id, (_before, after) in result.purchase_updates.items():
        await db.execute(text(
            "UPDATE purchases SET feo_category_id = :cat WHERE id = :id"
        ), {"cat": after, "id": purchase_id})


async def main_async(args: argparse.Namespace) -> int:
    async with async_session() as db:
        try:
            result = await compute_remap(db, args.subsidy_id, args.csv)
            tree = await load_feo_tree(db, args.subsidy_id)
            report = render_report(result, tree, args.subsidy_id)
        except Exception:
            await db.rollback()
            raise

        print(report)

        if not args.apply:
            await db.rollback()
            print("\nБЕЗ --apply: изменения НЕ применены (rollback).")
            return 0

        await apply_remap(db, result, args.subsidy_id)
        await db.commit()
        print(f"\nГотово: категории пересчитаны для субсидии id={args.subsidy_id} "
              f"(перенесено {len(result.moves)} плановых позиций).")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subsidy-id", type=int, required=True)
    ap.add_argument("--csv", required=True, help="Путь к scripts/data/fadm_2026_goodsservice.csv (внутри контейнера)")
    ap.add_argument("--apply", action="store_true", help="Применить (без флага — только отчёт, rollback)")
    args = ap.parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
