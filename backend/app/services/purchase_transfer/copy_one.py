"""copy_to_subsidy — создать копию закупки(ок) в другой (уже существующей)
субсидии. Оригинал НЕ меняется.

ПРАВИЛО №6 — не вторая копия, переиспользует:
  - app.services.subsidy_copy.copy_purchases.copy_purchases — сама копия
    (договор/позиции/чеки/платежи/аллокации), с фильтром purchase_ids;
  - app.services.subsidy_copy.copy_into_existing.build_category_map/
    build_planned_item_map — сопоставление дерева ФЭО и плановых позиций
    источник↔целевая по имени;
  - app.services.feo_unallocated.get_or_create_unallocated — категория
    «Не определена», если путь категории не сопоставился;
  - app.services.subsidy_draft_guard.assert_subsidy_approved_for_binding —
    та же проверка «субсидия утверждена», что и PATCH /purchases/{id};
  - app.services.purchase_transfer.doc_transfer/people_transfer/
    comments_transfer — документы/люди/комментарии.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.feo_unallocated import get_or_create_unallocated
from app.services.subsidy_copy.copy_into_existing import build_category_map, build_planned_item_map
from app.services.subsidy_copy.copy_purchases import copy_purchases
from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding

from .comments_transfer import copy_comments
from .doc_transfer import DocCopyCounters, copy_purchase_documents
from .people_transfer import copy_members, copy_person_fields_always


@dataclass
class CopyOutcome:
    source_id: int
    source_registry_number: str
    new_id: int
    new_registry_number: str


async def _copy_group(
    db: AsyncSession, source_subsidy_id: int, purchase_ids: list[int], target_subsidy_id: int, user: User,
    warnings_out: list[str] | None = None,
) -> list[CopyOutcome]:
    await assert_subsidy_approved_for_binding(db, target_subsidy_id)

    source_purchases = (await db.execute(
        select(Purchase).where(Purchase.id.in_(purchase_ids))
    )).scalars().all()
    source_by_id = {p.id: p for p in source_purchases}

    category_map = await build_category_map(db, source_subsidy_id, target_subsidy_id)

    used_planned_item_ids = {
        row[0] for row in (await db.execute(
            select(PurchaseItem.feo_planned_item_id).where(
                PurchaseItem.purchase_id.in_(purchase_ids),
                PurchaseItem.feo_planned_item_id.isnot(None),
            )
        )).all()
    }
    planned_map = await build_planned_item_map(
        db, category_map.map, item_ids=used_planned_item_ids or None,
    )

    result = await copy_purchases(
        db, source_subsidy_id, target_subsidy_id,
        category_map.map, planned_map.map, purchase_ids=set(purchase_ids),
    )

    # copy_purchases молча не копирует закупку, чей чек уже лежит в другой
    # закупке (вероятный дубль) — пишет только в result.warnings. Не теряем:
    # человек должен увидеть, что закупка НЕ скопирована и почему.
    if warnings_out is not None:
        for pid in purchase_ids:
            if pid in result.purchase_id_map:
                continue
            p = source_by_id.get(pid)
            reg = (p.registry_number if p else None) or f"№{pid}"
            reason = next((w.split(": ", 1)[1] for w in result.warnings if f"id={pid} " in w and ": " in w), None)
            warnings_out.append(f"{reg} не скопирована: {reason or 'копирование отклонено'}")

    source_subsidy = await db.get(Subsidy, source_subsidy_id)
    target_subsidy = await db.get(Subsidy, target_subsidy_id)
    na_category = None  # lazy — создаётся максимум раз на весь прогон

    outcomes: list[CopyOutcome] = []
    for old_id, new_id in result.purchase_id_map.items():
        old_p = source_by_id[old_id]
        new_p = await db.get(Purchase, new_id)

        # Категория по имени не нашлась -> «Не определена» целевой субсидии
        # (не пишем свой find-or-create — ПРАВИЛО №6, get_or_create_unallocated).
        if old_p.feo_category_id is not None and new_p.feo_category_id is None:
            if na_category is None:
                # source='purchase' — тот же source, что purchase_from_bank_payment.py
                # использует для той же ситуации «закупка без сопоставленной
                # категории» (feo_history.SOURCES — закрытый список, 'purchase_
                # transfer_copy' туда не входит, не плодим новое значение).
                na_category, _created = await get_or_create_unallocated(
                    db, target_subsidy_id, current_user=user, source="purchase",
                )
            new_p.feo_category_id = na_category.id
            await db.execute(
                PurchaseItem.__table__.update()
                .where(PurchaseItem.purchase_id == new_p.id, PurchaseItem.feo_category_id.is_(None))
                .values(feo_category_id=na_category.id)
            )

        # Копия — участники и люди копируются как есть (целевая закупка новая).
        copy_person_fields_always(old_p, new_p)
        await copy_members(db, old_p, new_p)
        await copy_comments(db, old_p, new_p)

        counters = DocCopyCounters()
        await copy_purchase_documents(db, old_p.id, new_p.id, counters)

        new_p.copied_from_purchase_id = old_p.id

        db.add(PurchaseEvent(
            purchase_id=old_p.id, user_id=user.id if user else None, event_type="copied_to",
            data={
                "target_purchase_id": new_p.id, "registry_number": new_p.registry_number,
                "subsidy_id": target_subsidy_id,
                "subsidy_name": target_subsidy.name if target_subsidy else None,
            },
        ))
        db.add(PurchaseEvent(
            purchase_id=new_p.id, user_id=user.id if user else None, event_type="copied_from",
            data={
                "source_purchase_id": old_p.id, "registry_number": old_p.registry_number,
                "subsidy_id": source_subsidy_id,
                "subsidy_name": source_subsidy.name if source_subsidy else None,
            },
        ))

        outcomes.append(CopyOutcome(
            source_id=old_p.id, source_registry_number=old_p.registry_number or "",
            new_id=new_p.id, new_registry_number=new_p.registry_number or "",
        ))

    await db.flush()
    return outcomes


async def copy_to_subsidy(
    db: AsyncSession, purchase_ids: list[int], target_subsidy_id: int, user: User,
    warnings_out: list[str] | None = None,
) -> list[CopyOutcome]:
    """purchase_ids может включать закупки из нескольких исходных субсидий —
    группируем по Purchase.subsidy_id и копируем группу за группой (карта
    категорий/плановых строится один раз на пару субсидий, не на закупку)."""
    if not purchase_ids:
        return []
    purchases = (await db.execute(
        select(Purchase.id, Purchase.subsidy_id).where(Purchase.id.in_(purchase_ids))
    )).all()
    by_source: dict[int, list[int]] = defaultdict(list)
    for pid, sid in purchases:
        if sid is not None:
            by_source[sid].append(pid)

    outcomes: list[CopyOutcome] = []
    for source_subsidy_id, ids in by_source.items():
        outcomes.extend(await _copy_group(db, source_subsidy_id, ids, target_subsidy_id, user, warnings_out))
    return outcomes
