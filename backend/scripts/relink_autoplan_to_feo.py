#!/usr/bin/env python3
"""Перепривязка auto_created дублей плана ФЭО, созданных заявкой, к настоящим
плановым позициям ФЭО (прод-инцидент, субсидия «Абхазия», id 68, 08.10.2026).

ПРИЧИНА. ФЭО загружено 16.09 — 189 плановых позиций по категориям. Тот же день
заявка №67 превратилась в закупку 919 (далее разбита на части 920-940,
922->955-956) — позиции заявки не имели своей feo_category_id, попали в
fallback-категорию «Не определена», и auto_assign_planned_items
(app/services/plan_autoassign.py — ИСКАЛА пару ТОЛЬКО внутри этой одной
категории) создала 186 НОВЫХ auto_created FeoPlannedItem там же вместо того,
чтобы найти уже существующие позиции плана в их настоящих категориях. План
субсидии задвоился (29 945 816 ₽ лишних плановых позиций).

Корень причины исправлен в app/services/plan_autoassign.py (ищет пару по всей
субсидии ДО создания новой позиции, правило — app/services/
feo_plan_duplicate_match.py, ПРАВИЛО №6) — этот скрипт разово лечит уже
существующие дубли ТЕМ ЖЕ правилом (одна функция, не вторая копия).

ПРАВИЛО СОПОСТАВЛЕНИЯ (find_unique_feo_plan_match, Rule №6):
  (а) нормализованное имя + сумма совпадают — если среди ещё не занятых НЕ-auto
      позиций ФЭО субсидии такая ровно ОДНА;
  (б) иначе — совпадение только по сумме среди ещё не занятых, если ровно ОДНА.
Неоднозначно (0 или 2+) — дубль НЕ трогаем, попадает в отчёт отдельно.

ЧТО ДЕЛАЕТ С КАЖДОЙ НАЙДЕННОЙ ПАРОЙ (дубль -> настоящая позиция ФЭО):
  1. Каждая PurchaseItem с feo_planned_item_id == дубль перепривязывается на
     настоящую позицию СУЩЕСТВУЮЩЕЙ функцией GALA
     app.services.feo_item_linking.link_purchase_item_to_planned (ТО ЖЕ тело,
     что у POST /feo-planned-items/map) — она сама:
       - проставляет feo_category_id позиции = категория настоящей позиции
         (enforce_category_check=False — сопоставление уже проверено правилом
         выше, 409 здесь неуместен, ровно тот же путь, которым существующий
         импорт факта пользуется для решения владельца «та же закупка», см.
         docstring feo_item_linking.py);
       - зеркалит привязку в связанную WishItem (pi.wish_item_id), если есть —
         тот же код, что и в проде устраняет рассинхрон заявка/закупка.
  2. Отдельные WishItem, которые ссылались на дубль НЕ через PurchaseItem (если
     остались) — для них нет отдельного сервиса-обёртки (вся логика живёт
     внутри больших PUT-эндпоинтов правки заявки целиком), поэтому
     перепривязка здесь — ТОЧНО ТЕ ЖЕ ДВЕ СТРОКИ, что и в зеркалящей ветке
     link_purchase_item_to_planned (feo_item_linking.py:79-84): проставить
     feo_planned_item_id и (если отличается) feo_category_id.
  3. Если у самой закупки (Purchase.feo_category_id) категория была пуста и
     ПОСЛЕ перепривязки все её позиции легли в одну и ту же категорию —
     проставляем её и закупке (прямой UPDATE: единого сервиса на «подстановку
     категории шапки закупки из её позиций» в проекте нет — она либо задаётся
     пользователем, либо наследуется построчно).
  4. Сам дубль удаляется СУЩЕСТВУЮЩЕЙ функцией
     app.services.feo_item_write.delete_planned_item (тело DELETE
     /feo-planned-items/{id}) — к этому моменту у него уже 0 держателей
     (п.1-2 всё перепривязали), поэтому удаление проходит без 409.

РЕЖИМЫ:
  без --apply — отчёт (таблица пар, план ДО/ПОСЛЕ по feo_plan_subsidy_totals,
                сколько позиций перепривязано), транзакция откатывается;
  --apply     — та же работа в ОДНОЙ транзакции; ПЕРЕД изменением создаются
                резервные таблицы bk_<YYYYMMDD>_relink_<sid>_{fpi,pitems,
                witems,purchases} (CREATE TABLE AS SELECT только затронутых
                строк), затем commit. Повторный прогон после --apply находит
                0 дублей (notes-маркер уже удалён вместе со строкой) — 0 изменений.

ЗАПУСК (локально, контейнер backend_b):
    docker compose -p vsks_crm exec -T backend_b python -m scripts.relink_autoplan_to_feo --subsidy-id <ID>
    (повторить с --apply, когда отчёт одобрен)

НА ПРОДЕ (субсидия «Абхазия», id 68):
    docker exec vsks_crm-backend-1 python -m scripts.relink_autoplan_to_feo --subsidy-id 68
    (повторить с --apply после проверки отчёта)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
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
from app.models.wish_item import WishItem
from app.services.feo_plan_duplicate_match import find_unique_feo_plan_match
from app.services.feo_plan_totals import feo_plan_subsidy_totals

_WISH_NOTE_PREFIX = "Создано заявкой"


@dataclass
class DupMatch:
    dup_id: int
    dup_name: str
    dup_amount: Decimal
    target_id: int
    target_name: str
    target_category_id: int
    target_category_path: str
    method: str  # 'name_amount' | 'amount'
    purchase_item_ids: list = field(default_factory=list)
    wish_item_ids: list = field(default_factory=list)  # «свои» WishItem без PurchaseItem-посредника


def _category_path(cat_by_id: dict, cat_id: Optional[int]) -> str:
    if cat_id is None:
        return "(нет категории)"
    names = []
    seen: set = set()
    cur = cat_by_id.get(cat_id)
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        names.append(cur.name)
        cur = cat_by_id.get(cur.parent_id) if cur.parent_id is not None else None
    return " / ".join(reversed(names)) if names else f"#{cat_id}"


async def _load_duplicates(db: AsyncSession, subsidy_id: int) -> tuple[list[FeoPlannedItem], dict]:
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    cat_by_id = {c.id: c for c in cats}
    cat_ids = list(cat_by_id.keys())
    if not cat_ids:
        return [], cat_by_id

    dups = (await db.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active.is_(True),
            FeoPlannedItem.auto_created.is_(True),
            FeoPlannedItem.notes.like(f"{_WISH_NOTE_PREFIX}%"),
        )
    )).scalars().all()
    return dups, cat_by_id


async def _load_real_candidates(db: AsyncSession, subsidy_id: int, cat_by_id: dict) -> list[FeoPlannedItem]:
    cat_ids = list(cat_by_id.keys())
    if not cat_ids:
        return []
    return (await db.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(cat_ids),
            FeoPlannedItem.is_active.is_(True),
            FeoPlannedItem.auto_created.is_(False),
        )
    )).scalars().all()


async def compute_matches(db: AsyncSession, subsidy_id: int) -> tuple[list[DupMatch], list[FeoPlannedItem], dict]:
    dups, cat_by_id = await _load_duplicates(db, subsidy_id)
    if not dups:
        return [], [], cat_by_id
    candidates = await _load_real_candidates(db, subsidy_id, cat_by_id)

    claimed: set = set()
    matches: list[DupMatch] = []
    unmatched: list[FeoPlannedItem] = []
    for dup in dups:
        target_id, method = find_unique_feo_plan_match(
            dup.name, dup.amount, candidates, claimed, allow_amount_only=True,
        )
        if target_id is None:
            unmatched.append(dup)
            continue
        claimed.add(target_id)
        target = next(c for c in candidates if c.id == target_id)
        matches.append(DupMatch(
            dup_id=dup.id, dup_name=dup.name or "", dup_amount=dup.amount or Decimal("0"),
            target_id=target.id, target_name=target.name or "",
            target_category_id=target.feo_category_id,
            target_category_path=_category_path(cat_by_id, target.feo_category_id),
            method=method,
        ))

    # Держатели (PurchaseItem/«осиротевшие» WishItem) — считаем отдельным
    # запросом, чтобы отчёт показывал реальный объём перепривязки ещё до --apply.
    dup_ids = [m.dup_id for m in matches]
    if dup_ids:
        pi_rows = (await db.execute(
            select(PurchaseItem.id, PurchaseItem.feo_planned_item_id, PurchaseItem.wish_item_id)
            .where(PurchaseItem.feo_planned_item_id.in_(dup_ids))
        )).all()
        pi_by_dup: dict[int, list] = {}
        mirrored_wish_item_ids: set = set()
        for pid, dup_id, wiid in pi_rows:
            pi_by_dup.setdefault(dup_id, []).append(pid)
            if wiid is not None:
                mirrored_wish_item_ids.add(wiid)

        wi_rows = (await db.execute(
            select(WishItem.id, WishItem.feo_planned_item_id)
            .where(WishItem.feo_planned_item_id.in_(dup_ids))
        )).all()
        wi_by_dup: dict[int, list] = {}
        for wid, dup_id in wi_rows:
            if wid in mirrored_wish_item_ids:
                continue  # уже перепривяжется зеркалом link_purchase_item_to_planned
            wi_by_dup.setdefault(dup_id, []).append(wid)

        for m in matches:
            m.purchase_item_ids = pi_by_dup.get(m.dup_id, [])
            m.wish_item_ids = wi_by_dup.get(m.dup_id, [])

    return matches, unmatched, cat_by_id


def render_report(matches: list[DupMatch], unmatched: list[FeoPlannedItem],
                   plan_before: Decimal, plan_after: Decimal, subsidy_id: int) -> str:
    lines = [f"=== Перепривязка auto-дублей плана ФЭО — субсидия id={subsidy_id} ==="]
    lines.append(f"Пар найдено: {len(matches)}  |  Неоднозначно/без пары (не трогаем): {len(unmatched)}")
    lines.append("")
    total_pi = sum(len(m.purchase_item_ids) for m in matches)
    total_wi = sum(len(m.wish_item_ids) for m in matches)
    lines.append(f"Позиций закупок к перепривязке: {total_pi}")
    lines.append(f"«Осиротевших» позиций заявки к перепривязке (без посредника-закупки): {total_wi}")
    lines.append("")
    if matches:
        lines.append("Пары (дубль -> позиция ФЭО):")
        for m in sorted(matches, key=lambda x: -float(x.dup_amount or 0)):
            lines.append(
                f"  - [{m.method}] дубль #{m.dup_id} «{m.dup_name}» ({m.dup_amount}) -> "
                f"позиция #{m.target_id} «{m.target_name}» ({m.target_category_path}); "
                f"позиций закупок: {len(m.purchase_item_ids)}, заявки: {len(m.wish_item_ids)}"
            )
        lines.append("")
    if unmatched:
        lines.append("Без пары / неоднозначно (НЕ трогаем):")
        for d in unmatched:
            lines.append(f"  - #{d.id} «{d.name}» ({d.amount})")
        lines.append("")
    lines.append(f"План субсидии ДО: {plan_before:,.2f} ₽")
    lines.append(f"План субсидии ПОСЛЕ (ожидаемо, после --apply): {plan_after:,.2f} ₽")
    lines.append(f"Разница (должна быть = Σ сумм перепривязанных дублей): {plan_before - plan_after:,.2f} ₽")
    return "\n".join(lines)


async def _unique_backup_table_name(db: AsyncSession, base: str) -> str:
    name = base
    suffix = 1
    while (await db.execute(text(
        "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename = :t"
    ), {"t": name})).scalar():
        suffix += 1
        name = f"{base}_{suffix}"
    return name


async def apply_matches(db: AsyncSession, matches: list[DupMatch], subsidy_id: int) -> dict:
    today = date.today().strftime("%Y%m%d")
    dup_ids = [m.dup_id for m in matches]
    pitem_ids = [pid for m in matches for pid in m.purchase_item_ids]
    witem_ids = [wid for m in matches for wid in m.wish_item_ids]
    purchase_ids = sorted({
        row[0] for row in (await db.execute(
            select(PurchaseItem.purchase_id).where(PurchaseItem.id.in_(pitem_ids or [-1]))
        )).all()
    }) if pitem_ids else []

    if dup_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_relink_{subsidy_id}_fpi")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM feo_planned_items WHERE id = ANY(:ids)"
        ), {"ids": dup_ids})
    if pitem_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_relink_{subsidy_id}_pitems")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM purchase_items WHERE id = ANY(:ids)"
        ), {"ids": pitem_ids})
    if witem_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_relink_{subsidy_id}_witems")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM wish_items WHERE id = ANY(:ids)"
        ), {"ids": witem_ids})
    if purchase_ids:
        name = await _unique_backup_table_name(db, f"bk_{today}_relink_{subsidy_id}_purchases")
        await db.execute(text(
            f"CREATE TABLE {name} AS SELECT * FROM purchases WHERE id = ANY(:ids)"
        ), {"ids": purchase_ids})

    from app.services.feo_item_linking import link_purchase_item_to_planned

    relinked_pi = 0
    relinked_wi = 0
    touched_purchase_ids: set = set()
    for m in matches:
        for pid in m.purchase_item_ids:
            pi = (await db.execute(select(PurchaseItem).where(PurchaseItem.id == pid))).scalar_one_or_none()
            if pi is None:
                continue
            await link_purchase_item_to_planned(
                db, pi=pi, planned_item_id=m.target_id, current_user=None,
                enforce_category_check=False,
            )
            relinked_pi += 1
            touched_purchase_ids.add(pi.purchase_id)

        # «Осиротевшие» WishItem без PurchaseItem-посредника (см. docstring
        # модуля, п.2) — та же пара строк, что в зеркалящей ветке
        # link_purchase_item_to_planned (feo_item_linking.py:79-84).
        for wid in m.wish_item_ids:
            wi = (await db.execute(select(WishItem).where(WishItem.id == wid))).scalar_one_or_none()
            if wi is None:
                continue
            wi.feo_planned_item_id = m.target_id
            if wi.feo_category_id != m.target_category_id:
                wi.feo_category_id = m.target_category_id
            relinked_wi += 1

    # Шапка закупки без собственной категории, но все позиции легли в одну —
    # проставляем (см. docstring модуля, п.3: нет отдельного сервиса на это).
    purchases_cat_set = 0
    for purchase_id in touched_purchase_ids:
        purchase = (await db.execute(select(Purchase).where(Purchase.id == purchase_id))).scalar_one_or_none()
        if purchase is None or purchase.feo_category_id is not None:
            continue
        cat_ids = {row[0] for row in (await db.execute(
            select(PurchaseItem.feo_category_id).where(
                PurchaseItem.purchase_id == purchase_id, PurchaseItem.feo_category_id.isnot(None),
            )
        )).all()}
        if len(cat_ids) == 1:
            purchase.feo_category_id = next(iter(cat_ids))
            purchases_cat_set += 1

    await db.flush()

    # Удаление самих дублей — существующей функцией feo_item_write.delete_planned_item
    # (тело DELETE /feo-planned-items/{id}); к этому моменту держателей уже 0.
    from app.services.feo_item_write import delete_planned_item as _delete_planned_item

    deleted = 0
    for m in matches:
        dup = (await db.execute(select(FeoPlannedItem).where(FeoPlannedItem.id == m.dup_id))).scalar_one_or_none()
        if dup is None:
            continue
        cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == dup.feo_category_id))).scalar_one_or_none()
        await _delete_planned_item(db, None, dup, cat)
        deleted += 1

    return {
        "relinked_purchase_items": relinked_pi,
        "relinked_wish_items": relinked_wi,
        "purchase_categories_set": purchases_cat_set,
        "deleted_duplicates": deleted,
    }


async def main_async(args: argparse.Namespace) -> int:
    async with async_session() as db:
        try:
            matches, unmatched, _cat_by_id = await compute_matches(db, args.subsidy_id)
        except Exception:
            await db.rollback()
            raise

        if not matches:
            print(f"Пар не найдено для субсидии id={args.subsidy_id} (дублей нет, либо все неоднозначны).")
            await db.rollback()
            return 0

        plan_before = Decimal(str((await feo_plan_subsidy_totals(db, [args.subsidy_id])).get(args.subsidy_id, 0.0)))

        if not args.apply:
            # dry-run: план "после" считаем приблизительно — Σ плана минус Σ
            # сумм дублей (сам тип расчёта дерева ФЭО не меняет после apply:
            # удаление дубля убирает его сумму из корня "Не определена").
            approx_after = plan_before - sum((m.dup_amount or Decimal("0")) for m in matches)
            print(render_report(matches, unmatched, plan_before, approx_after, args.subsidy_id))
            await db.rollback()
            print("\nБЕЗ --apply: изменения НЕ применены (rollback).")
            return 0

        stats = await apply_matches(db, matches, args.subsidy_id)
        db.expire_all()
        plan_after = Decimal(str((await feo_plan_subsidy_totals(db, [args.subsidy_id])).get(args.subsidy_id, 0.0)))
        print(render_report(matches, unmatched, plan_before, plan_after, args.subsidy_id))
        print()
        print(f"Перепривязано позиций закупок: {stats['relinked_purchase_items']}")
        print(f"Перепривязано «осиротевших» позиций заявки: {stats['relinked_wish_items']}")
        print(f"Проставлена категория шапки закупки: {stats['purchase_categories_set']}")
        print(f"Удалено дублей: {stats['deleted_duplicates']}")

        await db.commit()
        print(f"\nГотово: субсидия id={args.subsidy_id}, применено {len(matches)} перепривязок.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subsidy-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="Применить (без флага — только отчёт, rollback)")
    args = ap.parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
