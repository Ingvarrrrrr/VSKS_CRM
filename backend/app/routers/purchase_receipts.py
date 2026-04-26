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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
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
        raw_name = (it.get('name') or f'Позиция {idx}')[:5000]
        # Phase 21.06: try to auto-match a catalog product by case-insensitive
        # exact name. The match is always marked unconfirmed — the user must
        # explicitly approve each linked item before the report can be saved.
        norm = raw_name.strip().lower()
        matched_id = None
        if norm:
            mp = (await db.execute(
                select(Product.id)
                .where(func.lower(Product.name) == norm)
                .limit(1)
            )).scalar_one_or_none()
            if mp:
                matched_id = mp
        db.add(PurchaseItem(
            purchase_id=purchase_id,
            product_id=matched_id,
            item_name=raw_name,
            quantity=qty,
            unit='шт.',
            unit_price=price,
            total_price=total,
            match_confirmed=False,
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


# ── PDF / PNG render ────────────────────────────────────────────────────────
# Constant maps for ФФД 1.2 codes → human-readable Russian labels.
OPERATION_TYPE_RU = {
    1: "Приход",
    2: "Возврат прихода",
    3: "Расход",
    4: "Возврат расхода",
}
PRODUCT_TYPE_RU = {
    1: "ТОВАР",
    2: "ПОДАКЦИЗНЫЙ ТОВАР",
    3: "РАБОТА",
    4: "УСЛУГА",
    5: "СТАВКА АЗАРТНОЙ ИГРЫ",
    6: "ВЫИГРЫШ АЗАРТНОЙ ИГРЫ",
    7: "ЛОТЕРЕЙНЫЙ БИЛЕТ",
    8: "ВЫИГРЫШ ЛОТЕРЕИ",
    9: "ПРЕДОСТАВЛЕНИЕ РИД",
    10: "ПЛАТЕЖ",
    11: "АГЕНТСКОЕ ВОЗНАГРАЖДЕНИЕ",
    12: "ВЫПЛАТА",
    13: "ИНОЙ ПРЕДМЕТ РАСЧЕТА",
    14: "ИМУЩЕСТВЕННОЕ ПРАВО",
    15: "ВНЕРЕАЛИЗАЦИОННЫЙ ДОХОД",
    16: "СТРАХОВЫЕ ВЗНОСЫ",
    17: "ТОРГОВЫЙ СБОР",
    18: "КУРОРТНЫЙ СБОР",
    19: "ЗАЛОГ",
    20: "РАСХОД",
    21: "ВЗНОСЫ НА ОПС ИП",
    22: "ВЗНОСЫ НА ОПС",
    23: "ВЗНОСЫ НА ОМС ИП",
    24: "ВЗНОСЫ НА ОМС",
    25: "ВЗНОСЫ НА ОСС",
    26: "ПЛАТЕЖ КАЗИНО",
    27: "ВЫДАЧА ДЕНЕЖНЫХ СРЕДСТВ",
    30: "АТНМ",
    31: "АТМ",
    32: "АТНМ",
    33: "АТМ",
}
PAYMENT_TYPE_RU = {
    1: "ПРЕДОПЛАТА 100%",
    2: "ПРЕДОПЛАТА",
    3: "АВАНС",
    4: "ПОЛНЫЙ РАСЧЕТ",
    5: "ЧАСТИЧНЫЙ РАСЧЕТ И КРЕДИТ",
    6: "ПЕРЕДАЧА В КРЕДИТ",
    7: "ОПЛАТА КРЕДИТА",
}
NDS_LABEL_RU = {
    1: "НДС 20%",
    2: "НДС 10%",
    3: "НДС 20/120",
    4: "НДС 10/110",
    5: "НДС 0%",
    6: "НДС не облагается",
    7: "НДС не облагается",
}
TAXATION_RU = {
    1: "ОСН",
    2: "УСН доход",
    4: "УСН доход-расход",
    8: "ЕНВД",
    16: "ЕСХН",
    32: "ПАТЕНТ",
}


def _get_raw_receipt(r) -> dict:
    """Pull the FNS receipt sub-dict regardless of payload shape variant."""
    raw = r.raw_json or {}
    if not isinstance(raw, dict):
        return {}
    if 'ticket' in raw and isinstance(raw['ticket'], dict):
        return raw.get('ticket', {}).get('document', {}).get('receipt', {}) or {}
    if 'receipt' in raw and isinstance(raw['receipt'], dict):
        return raw['receipt']
    return raw


def _build_qr_string(r) -> str:
    """Compose the canonical ФНС QR string `t=...&s=...&fn=...&i=...&fp=...&n=...`."""
    parts = []
    if r.receipt_datetime:
        try:
            parts.append(f"t={r.receipt_datetime.strftime('%Y%m%dT%H%M')}")
        except Exception:
            pass
    if r.total_sum is not None:
        try:
            parts.append(f"s={float(r.total_sum):.2f}")
        except Exception:
            pass
    if r.fiscal_drive_number:
        parts.append(f"fn={r.fiscal_drive_number}")
    if r.fiscal_document_number:
        parts.append(f"i={r.fiscal_document_number}")
    if r.fiscal_sign:
        parts.append(f"fp={r.fiscal_sign}")
    raw = _get_raw_receipt(r)
    op = raw.get('operationType') or 1
    parts.append(f"n={op}")
    return '&'.join(parts)


def _make_qr_image_buf(data: str) -> BytesIO:
    """Build a QR-code PNG into an in-memory buffer (for ReportLab drawImage)."""
    import qrcode
    img = qrcode.make(data, box_size=4, border=2)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


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
    """Render a fiscal receipt in ФФД 1.2 layout (matches ФНС 'Проверка чека' app).

    A5 portrait, dynamic height. Sections (top→bottom):
      • Header (КАССОВЫЙ ЧЕК / версия ФФД 1.2 / operation type)
      • Items table — for each item: row + НДС label + НДС sum + product type + payment type
      • Totals (ИТОГО, Безналичные/Наличные/Аванс/…, НДС итог)
      • Fiscal block (СНО, РЕГ.НОМЕР ККТ, ФН, ФД, ФПД)
      • Seller block (Пользователь, Адрес, Место, ИНН, Дата, Чек №, Смена №, Кассир)
      • QR code centered
    """
    import textwrap
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    bold_name = "DejaVu-Bold" if font_name == "DejaVu" else "Helvetica-Bold"

    raw = _get_raw_receipt(r)
    items_data = list(raw.get('items') or [])

    # Dynamic height — A5 width (148mm) is enough; height grows with content.
    width = 148 * mm
    base_h = 180 * mm
    items_h = (25 * mm) * max(1, len(items_data))
    tail_h = 60 * mm
    height = base_h + items_h + tail_h

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    # Drawing state ----------------------------------------------------------
    state = {"y": height - 8 * mm}
    margin_l = 6 * mm
    margin_r = width - 6 * mm
    inner_w = margin_r - margin_l

    def set_font(size=9, bold=False, italic=False):
        # ReportLab DejaVu doesn't have an italic variant registered — use regular.
        c.setFont(bold_name if bold else font_name, size)

    def line(s, size=9, bold=False, x=None, dy=4.5):
        set_font(size, bold)
        c.drawString(x if x is not None else margin_l, state["y"], str(s))
        state["y"] -= dy * mm

    def line_center(s, size=9, bold=False, italic=False, dy=4.5):
        set_font(size, bold, italic)
        text_w = c.stringWidth(str(s), bold_name if bold else font_name, size)
        c.drawString((width - text_w) / 2, state["y"], str(s))
        state["y"] -= dy * mm

    def line_right(label, value, size=9, bold=False, dy=4.5):
        set_font(size, bold)
        c.drawString(margin_l, state["y"], str(label))
        text_w = c.stringWidth(str(value), bold_name if bold else font_name, size)
        c.drawString(margin_r - text_w, state["y"], str(value))
        state["y"] -= dy * mm

    def hr_dashed():
        c.setDash(2, 2)
        c.setLineWidth(0.4)
        c.line(margin_l, state["y"], margin_r, state["y"])
        c.setDash()
        state["y"] -= 3 * mm

    # ── Header ─────────────────────────────────────────────────────────────
    line_center("КАССОВЫЙ ЧЕК", 14, bold=True, dy=5.5)
    line_center("«версия ФФД 1.2»", 9, dy=5)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    line_center(op_word, 11, bold=True, dy=6)

    hr_dashed()

    # ── Items table ────────────────────────────────────────────────────────
    # Header row
    set_font(8, bold=True)
    c.drawString(margin_l, state["y"], "№")
    c.drawString(margin_l + 6 * mm, state["y"], "Название")
    c.drawString(margin_l + 80 * mm, state["y"], "Цена")
    c.drawString(margin_l + 100 * mm, state["y"], "Кол.")
    c.drawString(margin_l + 118 * mm, state["y"], "Сумма")
    state["y"] -= 5 * mm

    if not items_data:
        line("(позиции не указаны)", 8, dy=5)

    for idx, it in enumerate(items_data, start=1):
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
        nds_code = it.get('nds')
        nds_sum_kop = it.get('ndsSum')
        try:
            nds_sum_rub = float(nds_sum_kop) / 100.0 if nds_sum_kop is not None else None
        except Exception:
            nds_sum_rub = None
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()

        # Wrap long names — the name column is ~70mm wide.
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1 — number + first name line + price/qty/sum
        set_font(8)
        c.drawString(margin_l, state["y"], str(idx))
        c.drawString(margin_l + 6 * mm, state["y"], wrapped[0][:42])
        c.drawString(margin_l + 80 * mm, state["y"], f"{price:.2f}")
        c.drawString(margin_l + 100 * mm, state["y"], f"{qty:g}")
        c.drawString(margin_l + 118 * mm, state["y"], f"{sm:.2f}")
        state["y"] -= 4.5 * mm

        # Continuation lines of the name (if wrapped)
        for cont in wrapped[1:]:
            set_font(8)
            c.drawString(margin_l + 6 * mm, state["y"], cont[:42])
            state["y"] -= 4 * mm

        # НДС label
        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        line(f"   {nds_label}", 7, dy=3.8)

        # НДС sum (if non-zero)
        if nds_sum_rub is not None and nds_sum_rub > 0:
            line_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", 7, dy=3.8)

        # Product type
        if product_type:
            line(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", 7, dy=3.8)

        # Payment type
        if payment_type:
            line(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", 7, dy=3.8)

        state["y"] -= 1 * mm

    hr_dashed()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        line_right("ИТОГО:", f"{float(r.total_sum):.2f}", 12, bold=True, dy=6)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        line_right("Безналичные", f"{float(r.ecash_sum):.2f}", 9, dy=4.5)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        line_right("Наличные", f"{float(r.cash_sum):.2f}", 9, dy=4.5)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        line_right("Аванс", f"{float(r.prepaid_sum):.2f}", 9, dy=4.5)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            line_right("НДС", f"{nds_total:.2f}", 9, dy=4.5)
        else:
            line_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", 9, dy=4.5)

    hr_dashed()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        line(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", 8, dy=4.5)
    if r.kkt_reg_id:
        line(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", 8, dy=4.5)
    if r.fiscal_drive_number:
        line(f"ФН: № {r.fiscal_drive_number}", 8, dy=4.5)
    if r.fiscal_document_number:
        line(f"ФД: № {r.fiscal_document_number}", 8, dy=4.5)
    if r.fiscal_sign:
        line(f"ФПД: # {r.fiscal_sign}", 8, dy=4.5)

    hr_dashed()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        line(f"Пользователь: {r.seller_name}", 8, dy=4.5)
    if r.retail_place_address:
        line(f"Адрес расчета: {str(r.retail_place_address)[:90]}", 8, dy=4.5)
    if r.retail_place:
        line(f"Место расчета: {str(r.retail_place)[:90]}", 8, dy=4.5)
    if r.seller_inn:
        line(f"ИНН {r.seller_inn}", 8, dy=4.5)
    if r.receipt_datetime:
        try:
            line(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", 8, dy=4.5)
        except Exception:
            line(f"Дата: {r.receipt_datetime}", 8, dy=4.5)
    request_number = raw.get('requestNumber')
    if request_number:
        line(f"Чек № {request_number}", 8, dy=4.5)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        line(f"Смена № {shift_number}", 8, dy=4.5)
    if r.operator:
        line(f"Кассир {r.operator}", 8, dy=4.5)
    if r.operator_inn:
        line(f"ИНН кассира: {r.operator_inn}", 8, dy=4.5)

    state["y"] -= 4 * mm

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_buf = _make_qr_image_buf(qr_str)
        qr_size = 40 * mm
        qr_x = (width - qr_size) / 2
        qr_y = max(state["y"] - qr_size, 8 * mm)
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        pass

    c.showPage()
    c.save()
    return buf.getvalue()


def _render_receipt_png(r) -> bytes:
    """Render a fiscal receipt as PNG (Pillow). Same layout as PDF.

    Returns raw PNG bytes ready to send back as image/png.
    """
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    import qrcode

    raw = _get_raw_receipt(r)
    items_data = [it for it in (raw.get('items') or []) if isinstance(it, dict)]

    width = 600

    # ── Font loading ───────────────────────────────────────────────────────
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    bold_paths = [p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") for p in font_paths]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)
    bold_path = next((p for p in bold_paths if os.path.exists(p)), font_path)

    def f(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size) \
                if (bold_path if bold else font_path) else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    F_TITLE = f(20, bold=True)
    F_SUB = f(13)
    F_OP = f(16, bold=True)
    F_TBL_HEAD = f(12, bold=True)
    F_TXT = f(12)
    F_SMALL = f(11)
    F_TOTAL = f(20, bold=True)
    F_TOTAL_NUM = f(20, bold=True)
    F_LINE = f(13)

    line_h = 18

    # ── Pre-compute height ─────────────────────────────────────────────────
    title_h = 28 + 22 + 28 + 12  # title + sub + op + spacing
    items_h = 28  # table header
    for it in items_data:
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']
        items_h += line_h * len(wrapped)  # name lines
        items_h += line_h  # nds label
        if it.get('ndsSum'):
            items_h += line_h
        if it.get('productType'):
            items_h += line_h
        if it.get('paymentType'):
            items_h += line_h
        items_h += 6
    if not items_data:
        items_h += line_h

    totals_h = 60 + line_h * 5
    fiscal_h = line_h * 6
    seller_h = line_h * 10
    qr_h = 220
    height = title_h + items_h + totals_h + fiscal_h + seller_h + qr_h + 60

    img = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(img)

    margin_l = 20
    margin_r = width - 20

    state = {"y": 16}

    def hr():
        # Dashed
        x = margin_l
        while x < margin_r:
            d.line([(x, state["y"]), (min(x + 4, margin_r), state["y"])], fill='black', width=1)
            x += 8
        state["y"] += 10

    def text(s, font=F_TXT, x=None, dy=None, fill='black'):
        d.text((x if x is not None else margin_l, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_center(s, font=F_TXT, dy=None, fill='black'):
        try:
            tw = d.textlength(str(s), font=font)
        except Exception:
            tw = len(str(s)) * 7
        d.text(((width - tw) / 2, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_right(label, value, font=F_TXT, value_font=None, dy=None, fill='black'):
        vfont = value_font or font
        d.text((margin_l, state["y"]), str(label), font=font, fill=fill)
        try:
            vw = d.textlength(str(value), font=vfont)
        except Exception:
            vw = len(str(value)) * 7
        d.text((margin_r - vw, state["y"]), str(value), font=vfont, fill=fill)
        state["y"] += dy if dy is not None else line_h

    # ── Header ─────────────────────────────────────────────────────────────
    text_center("КАССОВЫЙ ЧЕК", F_TITLE, dy=28)
    text_center("«версия ФФД 1.2»", F_SUB, dy=22)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    text_center(op_word, F_OP, dy=28)
    state["y"] += 4
    hr()

    # ── Items table ────────────────────────────────────────────────────────
    # Column header
    d.text((margin_l, state["y"]), "№", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 30, state["y"]), "Название", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 340, state["y"]), "Цена", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 420, state["y"]), "Кол.", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 480, state["y"]), "Сумма", font=F_TBL_HEAD, fill='black')
    state["y"] += line_h + 4

    if not items_data:
        text("(позиции не указаны)", F_SMALL)

    for idx, it in enumerate(items_data, start=1):
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
        nds_code = it.get('nds')
        nds_sum_kop = it.get('ndsSum')
        try:
            nds_sum_rub = float(nds_sum_kop) / 100.0 if nds_sum_kop is not None else None
        except Exception:
            nds_sum_rub = None
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1
        d.text((margin_l, state["y"]), str(idx), font=F_TXT, fill='black')
        d.text((margin_l + 30, state["y"]), wrapped[0][:42], font=F_TXT, fill='black')
        d.text((margin_l + 340, state["y"]), f"{price:.2f}", font=F_TXT, fill='black')
        d.text((margin_l + 420, state["y"]), f"{qty:g}", font=F_TXT, fill='black')
        d.text((margin_l + 480, state["y"]), f"{sm:.2f}", font=F_TXT, fill='black')
        state["y"] += line_h

        # Wrapped name continuation
        for cont in wrapped[1:]:
            d.text((margin_l + 30, state["y"]), cont[:42], font=F_TXT, fill='black')
            state["y"] += line_h

        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        text(f"   {nds_label}", F_SMALL)

        if nds_sum_rub is not None and nds_sum_rub > 0:
            text_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", F_SMALL)

        if product_type:
            text(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", F_SMALL)

        if payment_type:
            text(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", F_SMALL)

        state["y"] += 4

    hr()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        text_right("ИТОГО:", f"{float(r.total_sum):.2f}", F_TOTAL, F_TOTAL_NUM, dy=30)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        text_right("Безналичные", f"{float(r.ecash_sum):.2f}", F_LINE)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        text_right("Наличные", f"{float(r.cash_sum):.2f}", F_LINE)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        text_right("Аванс", f"{float(r.prepaid_sum):.2f}", F_LINE)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            text_right("НДС", f"{nds_total:.2f}", F_LINE)
        else:
            text_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", F_LINE)

    hr()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        text(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", F_LINE)
    if r.kkt_reg_id:
        text(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", F_LINE)
    if r.fiscal_drive_number:
        text(f"ФН: № {r.fiscal_drive_number}", F_LINE)
    if r.fiscal_document_number:
        text(f"ФД: № {r.fiscal_document_number}", F_LINE)
    if r.fiscal_sign:
        text(f"ФПД: # {r.fiscal_sign}", F_LINE)

    hr()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        text(f"Пользователь: {r.seller_name}", F_LINE)
    if r.retail_place_address:
        text(f"Адрес расчета: {str(r.retail_place_address)[:90]}", F_LINE)
    if r.retail_place:
        text(f"Место расчета: {str(r.retail_place)[:90]}", F_LINE)
    if r.seller_inn:
        text(f"ИНН {r.seller_inn}", F_LINE)
    if r.receipt_datetime:
        try:
            text(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", F_LINE)
        except Exception:
            text(f"Дата: {r.receipt_datetime}", F_LINE)
    request_number = raw.get('requestNumber')
    if request_number:
        text(f"Чек № {request_number}", F_LINE)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        text(f"Смена № {shift_number}", F_LINE)
    if r.operator:
        text(f"Кассир {r.operator}", F_LINE)
    if r.operator_inn:
        text(f"ИНН кассира: {r.operator_inn}", F_LINE)

    state["y"] += 12

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_img = qrcode.make(qr_str, box_size=5, border=2).get_image().convert('RGB')
        qr_size = 200
        qr_resized = qr_img.resize((qr_size, qr_size))
        img.paste(qr_resized, ((width - qr_size) // 2, state["y"]))
    except Exception:
        pass

    out = BytesIO()
    img.save(out, format='PNG', optimize=True)
    return out.getvalue()
