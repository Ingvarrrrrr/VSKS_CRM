"""merge_into — «это та же закупка, дополнить»: переносит из source в target
то, чего у target ещё нет (файлы/чеки, участники, поля-люди ТОЛЬКО в пустые,
комментарии), не трогая и не останавливая source (в отличие от
scripts/fadm_sheet_load/sheet_v2_enrich.py::transfer_pair, которая дополнительно
останавливает старую закупку — здесь это не нужно, обе стороны продолжают жить
своей жизнью, просто «та же» помечена связью copied_from_purchase_id)."""
from __future__ import annotations

from dataclasses import dataclass

from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.subsidy import Subsidy
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

from .comments_transfer import copy_comments
from .doc_transfer import DocCopyCounters, copy_purchase_documents
from .people_transfer import copy_members, transfer_person_fields_into_empty


@dataclass
class MergeResult:
    source_id: int
    target_id: int
    target_registry_number: str
    members_added: int
    comments_copied: int
    person_fields_filled: list


async def merge_into(db: AsyncSession, source: Purchase, target: Purchase, user: User) -> MergeResult:
    counters = DocCopyCounters()
    await copy_purchase_documents(db, source.id, target.id, counters)

    members_added = await copy_members(db, source, target)
    person_fields_filled = transfer_person_fields_into_empty(source, target)
    comments_copied = await copy_comments(db, source, target)

    if target.copied_from_purchase_id is None:
        target.copied_from_purchase_id = source.id

    source_subsidy = await db.get(Subsidy, source.subsidy_id) if source.subsidy_id else None
    target_subsidy = await db.get(Subsidy, target.subsidy_id) if target.subsidy_id else None

    db.add(PurchaseEvent(
        purchase_id=target.id, user_id=user.id if user else None, event_type="merged_from",
        data={
            "source_purchase_id": source.id, "registry_number": source.registry_number,
            "subsidy_id": source.subsidy_id,
            "subsidy_name": source_subsidy.name if source_subsidy else None,
        },
    ))
    db.add(PurchaseEvent(
        purchase_id=source.id, user_id=user.id if user else None, event_type="merged_to",
        data={
            "target_purchase_id": target.id, "registry_number": target.registry_number,
            "subsidy_id": target.subsidy_id,
            "subsidy_name": target_subsidy.name if target_subsidy else None,
        },
    ))

    await db.flush()
    return MergeResult(
        source_id=source.id, target_id=target.id, target_registry_number=target.registry_number or "",
        members_added=members_added, comments_copied=comments_copied,
        person_fields_filled=person_fields_filled,
    )
