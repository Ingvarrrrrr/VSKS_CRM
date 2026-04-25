"""Purchase receipts router (Phase 21).

5 endpoints scoped under /api/purchases/{purchase_id}/receipts:
  GET    /                — list receipts of a purchase
  POST   /import-json     — multipart upload of FNS mobile-app JSON export
  POST   /from-qr         — body { qr: "t=...&s=...&fn=..." } from QR scan
  POST   /                — manual entry (fiscal data + optional items)
  DELETE /{receipt_id}    — remove a receipt (related PurchaseItems stay)

Idempotent on (fiscal_drive_number, fiscal_document_number, fiscal_sign):
re-importing the same receipt returns the existing row, items not duplicated.
"""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_receipt import PurchaseReceipt
from app.models.user import User
from app.schemas.schemas import ReceiptCreate, ReceiptOut


router = APIRouter(prefix="/api/purchases", tags=["receipts"])


# ── helpers ──────────────────────────────────────────────────────────────────
def _kop_to_rub(v):
    """Convert копейки → рубли. Accepts None / int / float / str."""
    if v is None:
        return None
    try:
        return (Decimal(str(v)) / Decimal('100')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return None


def _parse_fns_json_receipt(raw: dict) -> dict:
    """Map a single FNS-mobile-app JSON entry → dict with internal field names."""
    r = (
        (raw.get('ticket') or {}).get('document', {}).get('receipt')
        or raw.get('receipt')
        or raw
    ) or {}

    items = []
    for it in (r.get('items') or []):
        try:
            qty = Decimal(str(it.get('quantity') or 1))
        except Exception:
            qty = Decimal('1')
        items.append({
            'name': (it.get('name') or '').strip(),
            'quantity': qty,
            'price': _kop_to_rub(it.get('price')),
            'sum': _kop_to_rub(it.get('sum')),
            'nds': it.get('nds'),
        })

    fd_num = r.get('fiscalDocumentNumber')
    if isinstance(fd_num, str) and fd_num.isdigit():
        fd_num = int(fd_num)
    elif not isinstance(fd_num, int):
        fd_num = None

    return {
        'fiscal_drive_number': (str(r.get('fiscalDriveNumber') or '').strip() or None),
        'fiscal_document_number': fd_num,
        'fiscal_sign': (str(r.get('fiscalSign') or '').strip() or None),
        'kkt_reg_id': (str(r.get('kktRegId') or '').strip() or None),
        'receipt_datetime': _parse_dt(r.get('dateTime')),
        'total_sum': _kop_to_rub(r.get('totalSum')),
        'cash_sum': _kop_to_rub(r.get('cashTotalSum')),
        'ecash_sum': _kop_to_rub(r.get('ecashTotalSum')),
        'prepaid_sum': _kop_to_rub(r.get('prepaidSum')),
        'nds_sum': _kop_to_rub(r.get('ndsSum')),
        'seller_name': ((r.get('user') or '').strip() or None),
        'seller_inn': (str(r.get('userInn') or '').strip() or None),
        'retail_place': r.get('retailPlace'),
        'retail_place_address': r.get('retailPlaceAddress'),
        'operator': r.get('operator'),
        'operator_inn': (str(r.get('operatorInn') or '').strip() or None),
        'taxation_type': r.get('appliedTaxationType') or r.get('taxationType'),
        'items': items,
    }


def _parse_qr_string(qr: str) -> dict:
    """Parse QR string `t=...&s=...&fn=...&i=...&fp=...&n=...` → dict."""
    parts = {}
    for chunk in (qr or '').strip().split('&'):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            parts[k.strip()] = v.strip()

    dt = None
    if 't' in parts:
        s = parts['t']
        for fmt in ('%Y%m%dT%H%M%S', '%Y%m%dT%H%M'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                continue

    total = None
    if 's' in parts:
        try:
            total = Decimal(parts['s'])
        except Exception:
            total = None

    fd_num = None
    if parts.get('i', '').isdigit():
        fd_num = int(parts['i'])

    return {
        'fiscal_drive_number': parts.get('fn') or None,
        'fiscal_document_number': fd_num,
        'fiscal_sign': parts.get('fp') or None,
        'receipt_datetime': dt,
        'total_sum': total,
    }


async def _create_receipt_with_items(
    purchase_id: int,
    data: dict,
    source: str,
    raw_payload,
    db: AsyncSession,
) -> PurchaseReceipt:
    """Insert PurchaseReceipt + auto-create PurchaseItem rows.

    Idempotent on the (fn, fd, fp) triple — re-importing the same receipt
    returns the already-existing row without duplicating items.
    """
    fn = data.get('fiscal_drive_number')
    fd = data.get('fiscal_document_number')
    fp = data.get('fiscal_sign')
    if fn and fd and fp:
        existing = (await db.execute(
            select(PurchaseReceipt).where(
                PurchaseReceipt.fiscal_drive_number == fn,
                PurchaseReceipt.fiscal_document_number == fd,
                PurchaseReceipt.fiscal_sign == fp,
            )
        )).scalar_one_or_none()
        if existing:
            return existing

    items_data = data.pop('items', None) or []

    valid_cols = {c.key for c in PurchaseReceipt.__table__.columns}
    receipt_kwargs = {k: v for k, v in data.items() if k in valid_cols}

    receipt = PurchaseReceipt(
        purchase_id=purchase_id,
        source=source,
        raw_json=raw_payload,
        **receipt_kwargs,
    )
    db.add(receipt)
    await db.flush()

    for idx, it in enumerate(items_data, start=1):
        try:
            qty = Decimal(str(it.get('quantity') or 1))
        except Exception:
            qty = Decimal('1')
        price = it.get('price') or Decimal('0')
        total = it.get('sum')
        if total is None:
            try:
                total = (qty * Decimal(str(price))).quantize(Decimal('0.01'))
            except Exception:
                total = Decimal('0')
        db.add(PurchaseItem(
            purchase_id=purchase_id,
            product_id=None,
            item_name=(it.get('name') or f'Позиция {idx}')[:5000],
            quantity=qty,
            unit='шт.',
            unit_price=price,
            total_price=total,
        ))

    await db.commit()
    await db.refresh(receipt)
    return receipt


# ── endpoints ────────────────────────────────────────────────────────────────
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


@router.post("/{purchase_id}/receipts/import-json", response_model=List[ReceiptOut])
async def import_receipt_json(
    purchase_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Import one or more receipts from FNS mobile-app JSON export."""
    if not (file.filename or "").lower().endswith('.json'):
        raise HTTPException(400, "Поддерживается только .json")

    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    content = await file.read()
    try:
        payload = json.loads(content)
    except Exception:
        raise HTTPException(400, "Не удалось распарсить JSON")

    if not isinstance(payload, list):
        payload = [payload]

    results: List[PurchaseReceipt] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            data = _parse_fns_json_receipt(entry)
            r = await _create_receipt_with_items(
                purchase_id, data, 'json_import', entry, db
            )
            results.append(r)
        except Exception:
            # Skip malformed entries — others should still import.
            continue
    return results


@router.post("/{purchase_id}/receipts/from-qr", response_model=ReceiptOut)
async def import_receipt_qr(
    purchase_id: int,
    qr: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Create a receipt from a QR-string. No items (admin adds them later)."""
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    data = _parse_qr_string(qr)
    if not data.get('fiscal_drive_number'):
        raise HTTPException(400, "QR не содержит фискальных данных")

    return await _create_receipt_with_items(
        purchase_id, data, 'qr_scan', {'qr': qr}, db,
    )


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
    await db.delete(r)
    await db.commit()
    return {"status": "ok"}
