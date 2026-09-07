"""Purchase-receipts recompute/dedup endpoints.

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).
Thin HTTP wrappers over app/services/receipts_recompute.py — see that module
for the actual logic.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.purchase import Purchase
from app.services.receipts_recompute import _dedup_purchase_items_core, _recompute_from_receipts_core

router = APIRouter(prefix="/api/purchases", tags=["receipts"])


@router.post("/{purchase_id}/recompute-from-receipts")
async def recompute_from_receipts(
    purchase_id: int,
    force: bool = Query(False, description="Байпас snapshot-hash gate. Использовать после изменений логики парсинга (например НДС-маппинг)."),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Phase 26-Z: ручной пересчёт авансовой закупки из её PurchaseReceipt.
    Идемпотентно. Thin wrapper над _recompute_from_receipts_core.

    Параметр ?force=true (Phase 26-AAA-3) — байпасит snapshot-hash gate,
    нужно для ретроактивного обновления старых позиций при изменении
    логики парсинга (например после фикса НДС 22%/5%/7% маппинга).
    """
    p = await db.get(Purchase, purchase_id)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    return await _recompute_from_receipts_core(purchase_id, db, force=force)


@router.post("/{purchase_id}/dedup-items")
async def dedup_items_endpoint(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Phase 26-WW-2: ручное удаление точных дубликатов PurchaseItem.
    Идемпотентно. Возвращает {ok, deduplicated, kept}.
    Нужен потому что auto-recompute (_recompute_from_receipts_core) триггерится
    в purchases.py только при null_items / mismatch / orphan_receipts."""
    res = await _dedup_purchase_items_core(purchase_id, db)
    await db.commit()
    return res
