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
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import List

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
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


# ── PDF render ──────────────────────────────────────────────────────────────
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


def _register_cyrillic_font() -> str:
    """Register a Cyrillic-capable TTF font. Returns the registered font name
    (or "Helvetica" as a fallback). Idempotent — safe to call multiple times."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # If we've already registered DejaVu in a previous call, reuse it.
    try:
        if "DejaVu" in pdfmetrics.getRegisteredFontNames():
            return "DejaVu"
    except Exception:
        pass

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", path))
            bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
            else:
                # No bold available — register the regular face under the bold name
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", path))
            return "DejaVu"
        except Exception:
            continue
    return "Helvetica"


def _extract_items(raw) -> list:
    """Pull items out of the raw_json regardless of FNS shape variant."""
    if not isinstance(raw, dict):
        return []
    items_src = None
    ticket = raw.get('ticket')
    if isinstance(ticket, dict):
        doc = ticket.get('document')
        if isinstance(doc, dict):
            rcpt = doc.get('receipt')
            if isinstance(rcpt, dict):
                items_src = rcpt.get('items')
    if items_src is None:
        rcpt = raw.get('receipt')
        if isinstance(rcpt, dict):
            items_src = rcpt.get('items')
    if items_src is None:
        items_src = raw.get('items')
    if not isinstance(items_src, list):
        return []
    out = []
    for it in items_src:
        if not isinstance(it, dict):
            continue
        try:
            qty = float(it.get('quantity') or 1)
        except Exception:
            qty = 1.0
        try:
            price = float(it.get('price') or 0) / 100.0
        except Exception:
            price = 0.0
        try:
            sm = float(it.get('sum') or 0) / 100.0
        except Exception:
            sm = 0.0
        out.append({
            'name': str(it.get('name') or '').strip(),
            'qty': qty,
            'price': price,
            'sum': sm,
        })
    return out


def _render_fallback_pdf(r) -> bytes:
    """Minimal PDF when raw_json is missing or rendering threw."""
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    c.setFont(font_name, 10)
    w, h = A6
    c.drawString(8 * mm, h - 12 * mm, f"Чек #{r.id} — данные недоступны")
    if r.fiscal_drive_number:
        c.drawString(8 * mm, h - 20 * mm, f"ФН: {r.fiscal_drive_number}")
    if r.fiscal_document_number:
        c.drawString(8 * mm, h - 26 * mm, f"ФД: {r.fiscal_document_number}")
    c.showPage()
    c.save()
    return buf.getvalue()


def _render_receipt_pdf(r) -> bytes:
    """Render a fiscal receipt as a narrow thermal-cheque-style PDF."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    bold_name = "DejaVu-Bold" if font_name == "DejaVu" else "Helvetica-Bold"

    items_data = _extract_items(r.raw_json)

    width = 80 * mm
    # Rough dynamic height: header + items + footer
    height = (60 + max(1, len(items_data)) * 4 + 80) * mm

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    state = {"y": height - 6 * mm}

    def text(s, size=8, bold=False, x=4 * mm, dy=4):
        c.setFont(bold_name if bold else font_name, size)
        c.drawString(x, state["y"], str(s)[:80])
        state["y"] -= dy * mm

    def hr():
        c.setLineWidth(0.3)
        c.line(2 * mm, state["y"], width - 2 * mm, state["y"])
        state["y"] -= 2 * mm

    text("КАССОВЫЙ ЧЕК", 11, bold=True, dy=5)
    hr()
    if r.seller_name:
        text(r.seller_name, 8, bold=True)
    if r.seller_inn:
        text(f"ИНН {r.seller_inn}", 7)
    if r.retail_place:
        text(str(r.retail_place)[:70], 7)
    if r.retail_place_address:
        text(str(r.retail_place_address)[:80], 6)
    if r.operator:
        text(f"Кассир: {r.operator}", 7)
    hr()

    if r.receipt_datetime:
        try:
            text(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H:%M')}", 7)
        except Exception:
            text(f"Дата: {r.receipt_datetime}", 7)

    hr()
    text(f"{'№':<3}{'Наименование':<28}{'Кол':>4}{'Цена':>8}{'Сумма':>9}", 6)
    hr()

    for i, it in enumerate(items_data, 1):
        name = (it['name'] or '')[:28]
        line = f"{i:<3}{name:<28}{it['qty']:>4.0f}{it['price']:>8.2f}{it['sum']:>9.2f}"
        text(line, 6, dy=3)

    if not items_data:
        text("(позиции не указаны)", 6, dy=3)

    hr()
    if r.total_sum is not None:
        text(f"ИТОГО: {float(r.total_sum):.2f} \u20bd", 9, bold=True, dy=5)
    if r.nds_sum is not None:
        text(f"в т.ч. НДС: {float(r.nds_sum):.2f} \u20bd", 7)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        text(f"Наличными: {float(r.cash_sum):.2f} \u20bd", 7)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        text(f"Безналичными: {float(r.ecash_sum):.2f} \u20bd", 7)

    hr()
    text("ФН:  " + (r.fiscal_drive_number or "—"), 6)
    text("ФД:  " + str(r.fiscal_document_number or "—"), 6)
    text("ФПД: " + (r.fiscal_sign or "—"), 6)
    if r.kkt_reg_id:
        text("ККТ: " + str(r.kkt_reg_id), 6)
    if r.taxation_type is not None:
        sno = {1: "ОСН", 2: "УСН доход", 4: "УСН доход-расход",
               8: "ЕНВД", 16: "ЕСХН", 32: "Патент"}.get(r.taxation_type, str(r.taxation_type))
        text(f"СНО: {sno}", 6)

    c.showPage()
    c.save()
    return buf.getvalue()
