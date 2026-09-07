"""Purchase receipts router (Phase 21).

Historical module — sliced up (Правило №5, сессия 2026-09-08) into:
  app/services/receipts_parsing.py    — FNS-JSON/QR/HTML parsing, item matching
  app/services/receipts_render.py     — PDF/PNG rendering
  app/services/receipts_creation.py   — insert PurchaseReceipt + PurchaseItem rows
  app/services/receipts_recompute.py  — recompute + exact-duplicate cleanup
  app/routers/purchase_receipts_import.py    — JSON/QR/QR-fetch import endpoints
  app/routers/purchase_receipts_recompute.py — recompute/dedup endpoints
  app/routers/purchase_receipts_export.py    — PDF/PNG export endpoints

This module keeps the basic CRUD endpoints (list/create-manual/delete) and
re-exports every private helper that external modules import directly
(contractors.py, diag.py, purchases.py, backfills.py, purchase_files.py,
purchase_items_import.py, services/documents/stages_receipts.py) so
`from app.routers.purchase_receipts import _whatever` keeps working
unchanged — do not remove these re-exports without updating every caller.

5 endpoints scoped under /api/purchases/{purchase_id}/receipts:
  GET    /                — list receipts of a purchase
  POST   /import-json     — multipart upload of FNS mobile-app JSON export
  POST   /from-qr         — body { qr: "t=...&s=...&fn=..." } from QR scan
  POST   /                — manual entry (fiscal data + optional items)
  DELETE /{receipt_id}    — remove a receipt (related PurchaseItems stay)

Idempotent on (fiscal_drive_number, fiscal_document_number, fiscal_sign):
re-importing the same receipt returns the existing row, items not duplicated.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_receipt import PurchaseReceipt
from app.models.user import User
from app.schemas.schemas import ReceiptCreate, ReceiptOut
from app.services import acceptance_docs as _acc_docs

# ── re-exports for external callers (see module docstring) ──────────────────
from app.services.receipts_parsing import (  # noqa: F401
    _extract_items,
    _items_match_score,
    _parse_fns_json_receipt,
    _parse_qr_string,
)
from app.services.receipts_creation import (  # noqa: F401
    _create_or_enrich_contractor_from_receipt,
    _create_receipt_with_items,
)
from app.services.receipts_recompute import _recompute_from_receipts_core  # noqa: F401
from app.services.receipts_render import _render_receipt_png  # noqa: F401


router = APIRouter(prefix="/api/purchases", tags=["receipts"])


@router.get("/{purchase_id}/receipts", response_model=List[ReceiptOut])
async def list_receipts(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(PurchaseReceipt)
        .where(PurchaseReceipt.purchase_id == purchase_id)
        .order_by(PurchaseReceipt.created_at.desc())
    )).scalars().all()
    return rows


@router.post("/{purchase_id}/receipts", response_model=ReceiptOut)
async def create_receipt_manual(
    purchase_id: int,
    data: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Manual entry of fiscal data + optional items."""
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    payload = data.model_dump(exclude_unset=True)
    src = payload.pop('source', None) or 'manual'
    raw_dump = data.model_dump(mode='json')
    return await _create_receipt_with_items(
        purchase_id, payload, src, raw_dump, db,
    )


@router.delete("/{purchase_id}/receipts/{receipt_id}")
async def delete_receipt(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")

    # U-4: при удалении чека — убрать запись из acceptance_docs (если авансовый)
    purchase = await db.get(Purchase, purchase_id)
    if purchase and purchase.purchase_method == 'advance' and purchase.acceptance_docs:
        _acc_docs.remove_doc(purchase, lambda d: d.get("receipt_id") == receipt_id)

    await db.delete(r)
    await db.commit()
    return {"status": "ok"}
