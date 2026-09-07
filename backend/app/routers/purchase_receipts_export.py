"""Purchase-receipts PDF/PNG export endpoints.

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).
Actual rendering lives in app/services/receipts_render.py; these are thin
HTTP wrappers.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.purchase_receipt import PurchaseReceipt
from app.services.receipts_render import _render_fallback_pdf, _render_receipt_pdf, _render_receipt_png

router = APIRouter(prefix="/api/purchases", tags=["receipts"])


@router.get("/{purchase_id}/receipts/{receipt_id}/pdf")
async def receipt_pdf(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF on-the-fly from receipt raw_json. No auth — fiscal receipts
    are not sensitive (already public on ФНС side via the QR code). Stable URL
    allows embedding as hyperlinks in Excel exports."""
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")
    try:
        pdf_bytes = _render_receipt_pdf(r)
    except Exception:
        pdf_bytes = _render_fallback_pdf(r)
    filename = f"Cheque_{r.fiscal_drive_number or 'unknown'}_{r.fiscal_document_number or r.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/{purchase_id}/receipts/{receipt_id}/png")
async def receipt_png(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
):
    """PNG render of a receipt — for inline <img> embedding."""
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")
    png_bytes = _render_receipt_png(r)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
