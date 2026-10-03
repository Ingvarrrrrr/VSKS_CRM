"""Копия дерева ФЭО, плановых позиций, доступов/согласующих и docx-шаблонов
субсидии — часть «Копия субсидии для экспериментов» (план
breezy-mixing-lovelace.md, Часть Б, 03.10.2026, ПРАВИЛО №5).

copy_purchases.py копирует закупки отдельно (нужны готовые category_id_map /
planned_item_id_map ОТСЮДА, чтобы перепривязать позиции закупок на строки
плана копии, а не оригинала).
"""
from __future__ import annotations

import os
import shutil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy_approver import SubsidyApprover
from app.models.subsidy_member import SubsidyMember
from app.models.user_subsidy_access import UserSubsidyAccess, UserSubsidyPermissionOverride
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.responsible_person import ResponsiblePerson
from app.routers.subsidy_approvers import SUBSIDY_TEMPLATES_DIR

from ._clone import clone_row


class TreeCopyResult:
    __slots__ = ("category_id_map", "planned_item_id_map")

    def __init__(self) -> None:
        self.category_id_map: dict[int, int] = {}
        self.planned_item_id_map: dict[int, int] = {}


async def copy_feo_tree(db: AsyncSession, source_sid: int, new_sid: int) -> TreeCopyResult:
    """Дерево ФЭО (все уровни, parent_id перепривязан на копии) + плановые
    позиции каждой категории. Возвращает карты старый→новый id — нужны
    copy_purchases.py для перепривязки позиций закупок."""
    result = TreeCopyResult()

    categories = (await db.execute(
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == source_sid)
        .order_by(FeoCategory.level, FeoCategory.id)
    )).scalars().all()

    # level возрастает → родитель уже скопирован (и его новый id известен) до
    # того, как обрабатывается ребёнок — flush после КАЖДОЙ строки, чтобы
    # получить новый id сразу (self-referencing FK).
    for cat in categories:
        new_parent_id = result.category_id_map.get(cat.parent_id) if cat.parent_id else None
        new_cat = clone_row(
            cat, FeoCategory,
            subsidy_id=new_sid,
            parent_id=new_parent_id,
        )
        db.add(new_cat)
        await db.flush()
        result.category_id_map[cat.id] = new_cat.id

    if result.category_id_map:
        planned_items = (await db.execute(
            select(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id.in_(result.category_id_map.keys())
            )
        )).scalars().all()
        for item in planned_items:
            new_item = clone_row(
                item, FeoPlannedItem,
                feo_category_id=result.category_id_map[item.feo_category_id],
            )
            db.add(new_item)
            await db.flush()
            result.planned_item_id_map[item.id] = new_item.id

    return result


async def copy_access_and_approvers(db: AsyncSession, source_sid: int, new_sid: int) -> None:
    """Согласующие, участники совместной работы, персональные доступы (+их
    пер-право оверрайды), оверрайды реквизитов контрагента, ответственные
    лица — всё, что определяет «кто видит/может работать» с субсидией."""
    approvers = (await db.execute(
        select(SubsidyApprover).where(SubsidyApprover.subsidy_id == source_sid)
    )).scalars().all()
    for a in approvers:
        db.add(clone_row(a, SubsidyApprover, subsidy_id=new_sid))

    members = (await db.execute(
        select(SubsidyMember).where(SubsidyMember.subsidy_id == source_sid)
    )).scalars().all()
    for m in members:
        db.add(clone_row(m, SubsidyMember, subsidy_id=new_sid))

    accesses = (await db.execute(
        select(UserSubsidyAccess).where(UserSubsidyAccess.subsidy_id == source_sid)
    )).scalars().all()
    for acc in accesses:
        new_acc = clone_row(acc, UserSubsidyAccess, subsidy_id=new_sid)
        db.add(new_acc)
        await db.flush()
        overrides = (await db.execute(
            select(UserSubsidyPermissionOverride).where(
                UserSubsidyPermissionOverride.user_subsidy_access_id == acc.id
            )
        )).scalars().all()
        for ov in overrides:
            db.add(clone_row(
                ov, UserSubsidyPermissionOverride,
                user_subsidy_access_id=new_acc.id,
            ))

    overrides_c = (await db.execute(
        select(SubsidyContractorOverride).where(SubsidyContractorOverride.subsidy_id == source_sid)
    )).scalars().all()
    for ov in overrides_c:
        db.add(clone_row(ov, SubsidyContractorOverride, subsidy_id=new_sid))

    resp = (await db.execute(
        select(ResponsiblePerson).where(ResponsiblePerson.subsidy_id == source_sid)
    )).scalars().all()
    for r in resp:
        db.add(clone_row(r, ResponsiblePerson, subsidy_id=new_sid))

    await db.flush()


def copy_templates(source_sid: int, new_sid: int) -> None:
    """Кастомные .docx шаблоны субсидии — файлы на диске, ссылкой не обойтись
    (оригинал может потом удалить/заменить свой шаблон). Та же директория и
    тот же приём (shutil.copy2), что и POST /{sid}/templates/copy-from/{src}
    (routers/subsidy_approvers.py) — не файловая операция транзакции БД,
    делается синхронно после commit копии в вызывающем коде."""
    src_dir = os.path.join(SUBSIDY_TEMPLATES_DIR, str(source_sid))
    if not os.path.isdir(src_dir):
        return
    dst_dir = os.path.join(SUBSIDY_TEMPLATES_DIR, str(new_sid))
    os.makedirs(dst_dir, exist_ok=True)
    for fn in os.listdir(src_dir):
        if not fn.endswith(".docx"):
            continue
        shutil.copy2(os.path.join(src_dir, fn), os.path.join(dst_dir, fn))
