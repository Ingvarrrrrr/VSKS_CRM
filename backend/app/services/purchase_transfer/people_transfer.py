"""Исполнитель/инициатор/«на чьё имя»/получатель возмещения + участники
закупки → другая закупка.

ПЕРЕНЕСЕНО из scripts/fadm_sheet_load/sheet_v2_enrich.py::_transfer_pair_people
(ПРАВИЛО №6 — тот скрипт теперь импортирует отсюда вместо собственной копии).
Роли по memory project_service_note_roles: assigned_user_id=исполнитель,
service_note_by=инициатор, service_note_to_user_id="на чьё имя",
reimbursement_user_id=авансовый.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseMember
from app.services.subsidy_copy._clone import clone_row

PEOPLE_FIELDS = (
    "assigned_user_id", "service_note_by", "service_note_to_user_id", "reimbursement_user_id",
)


def transfer_person_fields_into_empty(old: Purchase, new: Purchase) -> list[str]:
    """Переносит поля-люди ТОЛЬКО в пустые поля целевой закупки (merge —
    «это та же закупка, дополнить», заполненное поле получателя не затирается).
    Возвращает имена изменённых полей."""
    changed: list[str] = []
    for attr in PEOPLE_FIELDS:
        old_value = getattr(old, attr)
        if old_value is not None and getattr(new, attr) is None:
            setattr(new, attr, old_value)
            changed.append(attr)
    return changed


def copy_person_fields_always(old: Purchase, new: Purchase) -> list[str]:
    """Копия (copy_to_subsidy) — поля-люди копируются как есть (целевая
    закупка только что создана, пустая по определению)."""
    changed: list[str] = []
    for attr in PEOPLE_FIELDS:
        old_value = getattr(old, attr)
        if old_value is not None:
            setattr(new, attr, old_value)
            changed.append(attr)
    return changed


async def copy_members(db: AsyncSession, old: Purchase, new: Purchase) -> int:
    """Добавляет участников (PurchaseMember) old → new, пропуская тех, кто у
    new уже есть (idempotent — повторный вызов не плодит дубли)."""
    existing = {m.user_id for m in (await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == new.id)
    )).scalars().all()}
    old_members = (await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == old.id)
    )).scalars().all()
    added = 0
    for m in old_members:
        if m.user_id in existing:
            continue
        db.add(clone_row(m, PurchaseMember, purchase_id=new.id))
        existing.add(m.user_id)
        added += 1
    return added
