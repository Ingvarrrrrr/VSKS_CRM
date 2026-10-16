"""Комментарии закупки (PurchaseComment) → другая закупка.

ПЕРЕНЕСЕНО из scripts/fadm_sheet_load/sheet_v2_enrich.py::
_transfer_pair_comments_events — только часть про комментарии (ПРАВИЛО №6).
Перенос PurchaseEvent там остаётся специфичным для скрипта (копирует ВСЮ
историю событий old с пометкой fadm_enrich_transfer_note) — copy_to_subsidy/
merge_into пишут свои собственные события (copied_from/copied_to/merged_from/
merged_to), а не копируют старую историю событий целиком, поэтому эта функция
переносит только комментарии.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_comment import PurchaseComment
from app.services.subsidy_copy._clone import clone_row


async def copy_comments(db: AsyncSession, old: Purchase, new: Purchase, *, note: Optional[str] = None) -> int:
    """Копирует все комментарии old → new. note (если задан) добавляется в
    конец текста каждой копии — так видно, что комментарий перенесён."""
    old_comments = (await db.execute(
        select(PurchaseComment).where(PurchaseComment.purchase_id == old.id)
    )).scalars().all()
    n = 0
    for c in old_comments:
        text = f"{c.text}\n\n[{note}]" if note else c.text
        db.add(clone_row(c, PurchaseComment, purchase_id=new.id, text=text))
        n += 1
    return n
