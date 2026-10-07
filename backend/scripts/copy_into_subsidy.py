#!/usr/bin/env python3
"""
CLI: продублировать ОТДЕЛЬНЫЕ закупки и/или заявку из одной субсидии в
ДРУГУЮ, уже существующую субсидию (задание владельца 06.10.2026: часть
закупок и одна заявка из «ФАДМ_2026» -> «ФАДМ 2026_2»). Старые записи НЕ
трогаются — создаются копии.

Логика ПЕРЕНЕСЕНА, не продублирована (ПРАВИЛО №6):
  - закупки/договоры/позиции/чеки/платежи/аллокации — app.services.subsidy_copy.
    copy_purchases.copy_purchases(..., purchase_ids={...}) — тот же код, что
    использует «Копия субсидии для экспериментов» (app/services/subsidy_copy/
    __init__.py::create_sandbox_copy), просто с фильтром по id;
  - сопоставление категорий ФЭО/плановых позиций ДВУХ субсидий по имени,
    клонирование несопоставленных плановых позиций, копия заявки и
    перепривязка связи заявка<->закупка между копиями —
    app.services.subsidy_copy.copy_into_existing (новый модуль, у «копии для
    экспериментов» этого шага нет — там дерево копируется целиком вместе с
    id, здесь оба дерева уже существуют независимо);
  - «эффективная сумма закупки» для отчёта — app.services.purchase_amounts.
    load_purchase_amounts (единственный источник истины по ПРАВИЛУ №6, не
    отдельная формула contract_price-или-ничего).

ПЛАНОВЫЕ ПОЗИЦИИ (задание владельца 07.10.2026, п.1): «всё купленное должно
быть привязано к плановым». Если плановая позиция старой субсидии НЕ нашлась
по имени в сопоставленной новой категории — она КЛОНИРУЕТСЯ в эту категорию
(см. build_planned_item_map), а не оставляется «без плановой». Клонируются
ТОЛЬКО плановые позиции, реально используемые копируемыми закупками/заявкой
(не весь план целевой субсидии). Одна и та же старая плановая позиция,
встреченная и у закупки, и у заявки (типичный случай — авансовый отчёт),
получает РОВНО ОДНУ новую (map строится один раз на оба вида копий).

СВЯЗЬ ЗАЯВКА<->ЗАКУПКА (задание 07.10.2026, п.2): если заявка — авансовый
отчёт копируемой закупки (Wish.purchase_id / Purchase.wish_id / PurchaseItem.
wish_item_id связаны у оригиналов), копии перепривязываются друг на друга тем
же способом (relink_wish_and_purchase_copies). Если одна из сторон связи не
попала в выборку для копирования — связь остаётся пустой, как раньше.

ЗАЩИТА ОТ ДВОЙНИКОВ: если в целевой субсидии у ТОГО ЖЕ контрагента уже есть
закупка на ТУ ЖЕ сумму (contract_price) — закупка пропускается с пометкой
«двойник: РЕЕ-...» (№ реестра уже существующей закупки в целевой субсидии).

РЕЖИМЫ:
  без --apply — отчёт (категории/плановые до->после, что скопировано/
                пропущено) печатается, вся работа идёт в ОДНОЙ транзакции,
                которая откатывается (ROLLBACK) — безопасно гонять повторно;
  --apply     — та же работа, в конце COMMIT вместо ROLLBACK.

ЗАПУСК (внутри контейнера backend — backend/scripts НЕ примонтирован volume'ом,
см. docstring других backend/scripts/*.py — нужен docker cp ПЕРЕД запуском):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/copy_into_subsidy.py \\
        vsks_crm-backend_a-1:/app/scripts/copy_into_subsidy.py
    docker exec vsks_crm-backend_a-1 python scripts/copy_into_subsidy.py \\
        --source-sid 7320 --target-sid 7410 \\
        --purchase-ids 101,102,103 --wish-ids 95
    (повторить с --apply, когда отчёт одобрен)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.contractor import Contractor  # noqa: E402
from app.models.wish import Wish  # noqa: E402
from app.models.wish_item import WishItem  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.services.purchase_amounts import load_purchase_amounts  # noqa: E402
from app.services.subsidy_copy.copy_purchases import copy_purchases  # noqa: E402
from app.services.subsidy_copy.copy_into_existing import (  # noqa: E402
    build_category_map,
    build_planned_item_map,
    category_path_str,
    copy_wishes,
    relink_wish_and_purchase_copies,
)


def _parse_id_list(raw: Optional[str]) -> set[int]:
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


async def _find_duplicate(db, target_sid: int, contractor_id: Optional[int],
                           contract_price: Optional[Decimal]) -> Optional[Purchase]:
    """Тот же контрагент + та же сумма (contract_price) уже есть в целевой
    субсидии -> «двойник», закупку не копируем (защита от случайного
    повторного запуска, задание 06.10.2026). Нет контрагента или суммы у
    исходной закупки — сравнивать не с чем, дубль не ищем."""
    if contractor_id is None or contract_price is None:
        return None
    return (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == target_sid,
            Purchase.contractor_id == contractor_id,
            Purchase.contract_price == contract_price,
        )
    )).scalars().first()


def _planned_label(planned_result, old_planned_id: Optional[int]) -> str:
    if old_planned_id is None:
        return "без плановой"
    new_id = planned_result.map.get(old_planned_id)
    if new_id is None:
        return "без плановой (категория не сопоставлена)"
    if old_planned_id in planned_result.cloned:
        return f"#{new_id} (перенесена)"
    return f"#{new_id} (найдена по имени)"


async def main_async(args: argparse.Namespace) -> int:
    purchase_ids = _parse_id_list(args.purchase_ids)
    wish_ids = _parse_id_list(args.wish_ids)
    if not purchase_ids and not wish_ids:
        print("Ничего не указано — нужен хотя бы один из --purchase-ids / --wish-ids.")
        return 1

    lines: list[str] = []

    async with async_session() as db:
        try:
            source = await db.get(Subsidy, args.source_sid)
            target = await db.get(Subsidy, args.target_sid)
            if source is None:
                print(f"Субсидия-источник id={args.source_sid} не найдена.")
                return 1
            if target is None:
                print(f"Целевая субсидия id={args.target_sid} не найдена.")
                return 1

            lines.append(f"=== Дублирование: «{source.name}» (id={source.id}) -> "
                         f"«{target.name}» (id={target.id}) ===")

            # --- Загрузка выбранных закупок/заявок ДО построения карты
            # плановых позиций — ей нужен набор РЕАЛЬНО используемых старых
            # planned_item_id (клонируем только то, что нужно, не весь план).
            skipped_as_duplicate: dict[int, Purchase] = {}
            source_purchases: dict[int, Purchase] = {}
            source_items_by_purchase: dict[int, list[PurchaseItem]] = {}
            contractor_names: dict[int, str] = {}

            if purchase_ids:
                rows = (await db.execute(
                    select(Purchase).where(Purchase.id.in_(purchase_ids))
                )).scalars().all()
                source_purchases = {p.id: p for p in rows}
                missing = purchase_ids - set(source_purchases)
                for mid in sorted(missing):
                    lines.append(f"Закупка id={mid}: НЕ НАЙДЕНА — пропущена.")

                contractor_ids = {p.contractor_id for p in rows if p.contractor_id}
                if contractor_ids:
                    for c in (await db.execute(
                        select(Contractor).where(Contractor.id.in_(contractor_ids))
                    )).scalars().all():
                        contractor_names[c.id] = c.name

                for p in rows:
                    items = (await db.execute(
                        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
                    )).scalars().all()
                    source_items_by_purchase[p.id] = items

                    dup = await _find_duplicate(db, args.target_sid, p.contractor_id, p.contract_price)
                    if dup is not None:
                        skipped_as_duplicate[p.id] = dup

            copy_ids = {pid for pid in source_purchases if pid not in skipped_as_duplicate}

            source_wishes: list[Wish] = []
            source_wish_items: dict[int, list[WishItem]] = {}
            if wish_ids:
                source_wishes = (await db.execute(
                    select(Wish).where(Wish.id.in_(wish_ids))
                )).scalars().all()
                for w in source_wishes:
                    source_wish_items[w.id] = (await db.execute(
                        select(WishItem).where(WishItem.wish_id == w.id)
                    )).scalars().all()

            # --- Карты категорий/плановых — ОДИН раз, используются и
            # закупками, и заявкой (общая старая плановая -> общая новая).
            cat_result = await build_category_map(db, args.source_sid, args.target_sid)

            referenced_planned_ids: set[int] = set()
            for pid in copy_ids:
                referenced_planned_ids |= {
                    it.feo_planned_item_id for it in source_items_by_purchase.get(pid, [])
                    if it.feo_planned_item_id
                }
            for w in source_wishes:
                referenced_planned_ids |= {
                    it.feo_planned_item_id for it in source_wish_items.get(w.id, [])
                    if it.feo_planned_item_id
                }

            planned_result = await build_planned_item_map(
                db, cat_result.map, item_ids=referenced_planned_ids,
            )

            # --- Закупки ---
            copy_result = None
            if copy_ids:
                copy_result = await copy_purchases(
                    db, args.source_sid, args.target_sid,
                    category_id_map={k: v for k, v in cat_result.map.items() if v is not None},
                    planned_item_id_map={k: v for k, v in planned_result.map.items() if v is not None},
                    purchase_ids=copy_ids,
                )

            # --- Заявка ---
            wish_copy_result = None
            if wish_ids:
                wish_copy_result = await copy_wishes(
                    db, wish_ids, args.target_sid, cat_result.map, planned_result.map,
                )

            # --- Связь заявка<->закупка между копиями (авансовый отчёт и
            # т.п.) — только если ОБЕ стороны копировались в этом прогоне.
            relink_warnings: list[str] = []
            if copy_result and wish_copy_result:
                relink_warnings = await relink_wish_and_purchase_copies(
                    db,
                    purchase_id_map=copy_result.purchase_id_map,
                    wish_id_map=wish_copy_result.wish_id_map,
                    wish_item_id_map=wish_copy_result.wish_item_id_map,
                    purchase_item_id_map=copy_result.item_id_map,
                )

            # --- Отчёт: закупки ---
            amounts_map = {}
            if source_purchases:
                amounts_map = await load_purchase_amounts(db, list(source_purchases.keys()))

            lines.append("")
            lines.append(f"Закупок выбрано: {len(purchase_ids)}; к копированию: {len(copy_ids)}; "
                         f"двойников пропущено: {len(skipped_as_duplicate)}.")
            for old_id, p in source_purchases.items():
                contractor_label = contractor_names.get(p.contractor_id, "(без контрагента)")
                amt = amounts_map.get(old_id)
                amt_label = amt.effective if amt and amt.effective is not None else p.contract_price
                if old_id in skipped_as_duplicate:
                    dup = skipped_as_duplicate[old_id]
                    lines.append(f"  - закупка id={old_id} (№{p.registry_number or '-'}), "
                                 f"{contractor_label}, {amt_label}: "
                                 f"ПРОПУЩЕНА — двойник: {dup.registry_number or ('id=' + str(dup.id))}")
                    continue
                new_id = copy_result.purchase_id_map.get(old_id) if copy_result else None
                new_registry = "?"
                new_p = None
                if new_id is not None:
                    new_p = await db.get(Purchase, new_id)
                    new_registry = new_p.registry_number if new_p else "?"
                old_cat_path = category_path_str(cat_result.source_by_id, p.feo_category_id)
                new_cat_id = cat_result.map.get(p.feo_category_id) if p.feo_category_id else None
                new_cat_path = (category_path_str(cat_result.target_by_id, new_cat_id)
                               if p.feo_category_id else "(нет категории)")
                if p.feo_category_id and new_cat_id is None:
                    new_cat_path = "НЕ НАЙДЕНА"
                contract_copied = (p.contract_id is not None and copy_result is not None
                                   and p.contract_id in copy_result.contract_id_map)
                lines.append(f"  - закупка id={old_id} № {p.registry_number or '-'} -> № {new_registry}, "
                             f"{contractor_label}, сумма {amt_label}; "
                             f"категория «{old_cat_path}» -> «{new_cat_path}»; "
                             f"договор: {'скопирован' if contract_copied else ('нет своего договора' if not p.contract_id else 'НЕ скопирован')}")
                if new_p is not None and new_p.wish_id:
                    lines.append(f"      связь с заявкой: восстановлена -> копия заявки id={new_p.wish_id}")
                for it in source_items_by_purchase.get(old_id, []):
                    planned_label = _planned_label(planned_result, it.feo_planned_item_id)
                    lines.append(f"      · позиция «{it.item_name}»: плановая -> {planned_label}")

            if copy_result:
                for w in copy_result.warnings:
                    lines.append(f"  [предупреждение] {w}")

            # --- Отчёт: заявка ---
            if wish_ids:
                lines.append("")
                lines.append(f"Заявок выбрано: {len(wish_ids)}; скопировано: "
                             f"{wish_copy_result.wish_count if wish_copy_result else 0}.")
                for w in source_wishes:
                    new_id = wish_copy_result.wish_id_map.get(w.id) if wish_copy_result else None
                    new_status = w.status if w.status in {"draft", "submitted"} else "submitted"
                    old_cat_path = category_path_str(cat_result.source_by_id, w.feo_category_id)
                    new_cat_id = cat_result.map.get(w.feo_category_id) if w.feo_category_id else None
                    new_cat_path = (category_path_str(cat_result.target_by_id, new_cat_id)
                                   if w.feo_category_id else "(нет категории)")
                    if w.feo_category_id and new_cat_id is None:
                        new_cat_path = "НЕ НАЙДЕНА"
                    lines.append(f"  - заявка id={w.id} \"{w.title}\" -> id={new_id}, "
                                 f"статус «{w.status}» -> «{new_status}»; "
                                 f"категория «{old_cat_path}» -> «{new_cat_path}»")
                    new_w = await db.get(Wish, new_id) if new_id is not None else None
                    if new_w is not None and new_w.purchase_id:
                        lines.append(f"      связь с закупкой: восстановлена -> копия закупки id={new_w.purchase_id}")
                    for it in source_wish_items.get(w.id, []):
                        planned_label = _planned_label(planned_result, it.feo_planned_item_id)
                        lines.append(f"      · позиция «{it.item_name}»: плановая -> {planned_label}")
                if wish_copy_result:
                    for w_warn in wish_copy_result.warnings:
                        lines.append(f"  [предупреждение] {w_warn}")

            if relink_warnings:
                for rw in relink_warnings:
                    lines.append(f"  [предупреждение] {rw}")

            if cat_result.unmatched:
                lines.append("")
                lines.append(f"Категорий ФЭО без соответствия в целевой субсидии: {len(cat_result.unmatched)} "
                             f"(список выше у каждой затронутой закупки/заявки).")

            if planned_result.cloned:
                lines.append(f"Плановых позиций перенесено (клонировано, т.к. по имени не нашлись): "
                             f"{len(planned_result.cloned)}.")

            print("\n".join(lines))

            if not args.apply:
                await db.rollback()
                print("\nБЕЗ --apply: изменения НЕ применены (rollback).")
                return 0

            await db.commit()
            print("\nГотово: изменения применены (commit).")
            return 0
        except Exception:
            await db.rollback()
            raise


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-sid", type=int, required=True)
    ap.add_argument("--target-sid", type=int, required=True)
    ap.add_argument("--purchase-ids", help="через запятую, напр. 101,102,103")
    ap.add_argument("--wish-ids", help="через запятую, напр. 95")
    ap.add_argument("--apply", action="store_true", help="Применить (без флага — только отчёт, rollback)")
    args = ap.parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
