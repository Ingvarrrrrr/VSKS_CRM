import logging
import re
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.object_visibility import ensure_purchase_visible
from app.database import get_db
from app.models.contract_item import ContractItem
from app.models.delivery_item import DeliveryItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.user import User
from app.schemas.delivery_items import (
    DeliveryItemCreate,
    DeliveryItemOut,
    DeliveryItemsResponse,
    DeliveryItemUpdate,
    DeliverySummary,
    WaybillApplyRequest,
    WaybillParseResponse,
    WaybillParsedItem,
)
from app.utils.numbers import to_decimal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/purchases/{pid}/delivery-items", tags=["delivery-items"])


def _coerce_date(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        s = v.strip()
        for parse_fn in (
            lambda: date.fromisoformat(s[:10]),
            lambda: date(int(s.split(".")[2]), int(s.split(".")[1]), int(s.split(".")[0])),
        ):
            try:
                return parse_fn()
            except Exception:
                pass
    return None


def _calc_total(qty: Any, unit_price: Any) -> Decimal:
    try:
        return (Decimal(str(qty or 0)) * Decimal(str(unit_price or 0))).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


async def _build_summary(pid: int, purchase: Purchase, db: AsyncSession) -> DeliverySummary:
    items = (await db.execute(select(DeliveryItem).where(DeliveryItem.purchase_id == pid))).scalars().all()
    cis = (await db.execute(select(ContractItem).where(ContractItem.purchase_id == pid))).scalars().all()
    pis = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == pid))).scalars().all()

    if cis:
        contract_total = sum((ci.total or Decimal("0")) for ci in cis)
        target_qty = sum((ci.quantity or Decimal("0")) for ci in cis)
    else:
        contract_total = Decimal(str(purchase.contract_price or purchase.total_nmck or "0"))
        target_qty = sum((pi.quantity or Decimal("0")) for pi in pis)

    status_counts = {"pending": 0, "partial": 0, "delivered": 0}
    delivered_total = Decimal("0")
    delivered_qty = Decimal("0")

    for item in items:
        st = item.status or "pending"
        status_counts[st] = status_counts.get(st, 0) + 1
        if st in ("delivered", "partial"):
            delivered_total += item.total or Decimal("0")
            delivered_qty += item.qty or Decimal("0")

    pct_qty = min(100.0, round(float(delivered_qty / target_qty * 100), 1)) if target_qty > 0 else 0.0
    pct_amt = min(100.0, round(float(delivered_total / contract_total * 100), 1)) if contract_total > 0 else 0.0

    return DeliverySummary(
        contract_total=contract_total,
        delivered_total=delivered_total,
        delivered_qty_pct=pct_qty,
        delivered_amount_pct=pct_amt,
        status_counts=status_counts,
    )


@router.get("", response_model=DeliveryItemsResponse)
async def list_delivery_items(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    purchase = await ensure_purchase_visible(current_user, pid, db)
    res = await db.execute(select(DeliveryItem).where(DeliveryItem.purchase_id == pid).order_by(DeliveryItem.id))
    return DeliveryItemsResponse(items=list(res.scalars().all()), summary=await _build_summary(pid, purchase, db))


@router.post("", response_model=DeliveryItemOut, status_code=201)
async def create_delivery_item(
    pid: int,
    data: DeliveryItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    item = DeliveryItem(
        purchase_id=pid,
        contract_item_id=data.contract_item_id,
        purchase_item_id=data.purchase_item_id,
        product_id=data.product_id,
        name=data.name.strip(),
        unit=data.unit,
        qty=data.qty,
        unit_price=data.unit_price,
        total=_calc_total(data.qty, data.unit_price),
        delivery_date=_coerce_date(data.delivery_date),
        doc_number=data.doc_number,
        status=data.status or "pending",
        notes=data.notes,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=DeliveryItemOut)
async def update_delivery_item(
    pid: int,
    item_id: int,
    data: DeliveryItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    item = await db.get(DeliveryItem, item_id)
    if not item or item.purchase_id != pid:
        raise HTTPException(404, "Позиция поставки не найдена")

    update_dict = data.model_dump(exclude_unset=True)
    if "delivery_date" in update_dict:
        update_dict["delivery_date"] = _coerce_date(update_dict["delivery_date"])
    for k, v in update_dict.items():
        setattr(item, k, v)
    item.total = _calc_total(item.qty, item.unit_price)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_delivery_item(
    pid: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    item = await db.get(DeliveryItem, item_id)
    if not item or item.purchase_id != pid:
        raise HTTPException(404, "Позиция поставки не найдена")
    await db.delete(item)
    await db.commit()
    return None


@router.post("/from-contract", response_model=List[DeliveryItemOut])
async def create_delivery_items_from_contract(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    existing = (await db.execute(select(DeliveryItem).where(DeliveryItem.purchase_id == pid))).scalars().all()
    exist_c_ids = {d.contract_item_id for d in existing if d.contract_item_id}
    exist_p_ids = {d.purchase_item_id for d in existing if d.purchase_item_id}

    cis = (await db.execute(select(ContractItem).where(ContractItem.purchase_id == pid).order_by(ContractItem.id))).scalars().all()
    created: List[DeliveryItem] = []

    if cis:
        for ci in cis:
            if ci.id in exist_c_ids:
                continue
            q, p = Decimal(str(ci.quantity or 0)), Decimal(str(ci.unit_price or 0))
            item = DeliveryItem(
                purchase_id=pid, contract_item_id=ci.id, purchase_item_id=ci.source_item_id,
                product_id=ci.product_id, name=ci.name, unit=ci.unit, qty=q, unit_price=p,
                total=_calc_total(q, p), status="pending",
            )
            db.add(item)
            created.append(item)
    else:
        pis = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == pid).order_by(PurchaseItem.id))).scalars().all()
        for pi in pis:
            if pi.id in exist_p_ids:
                continue
            q, p = Decimal(str(pi.quantity or 0)), Decimal(str(pi.unit_price or 0))
            pi_name = getattr(pi, "item_name", None) or getattr(pi, "name", "")
            item = DeliveryItem(
                purchase_id=pid, purchase_item_id=pi.id, product_id=pi.product_id,
                name=pi_name, unit=pi.unit, qty=q, unit_price=p, total=_calc_total(q, p), status="pending",
            )
            db.add(item)
            created.append(item)

    if created:
        await db.commit()
        for it in created:
            await db.refresh(it)
    return created


@router.post("/parse-waybill", response_model=WaybillParseResponse)
async def parse_waybill(
    pid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    cis = (await db.execute(select(ContractItem).where(ContractItem.purchase_id == pid))).scalars().all()
    pis = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == pid))).scalars().all()

    content = await file.read()
    filename = (file.filename or "").lower()
    parsed_rows: List[dict] = []
    warnings: List[str] = []

    if filename.endswith((".xlsx", ".xls")):
        from app.services.items_import_parsing import _smart_import_xlsx_direct
        try:
            preview_rows, _, warns = _smart_import_xlsx_direct(content, fname=filename)
            for r in preview_rows:
                parsed_rows.append({
                    "name": r.get("item_name") or "",
                    "qty": to_decimal(r.get("quantity")) or Decimal("0"),
                    "unit_price": to_decimal(r.get("unit_price")) or Decimal("0"),
                    "total": to_decimal(r.get("total_price")) or Decimal("0"),
                    "unit": r.get("unit"),
                })
            warnings.extend([w.get("detail", str(w)) for w in warns])
        except Exception as e:
            warnings.append(f"Ошибка Excel: {e}")
    else:
        from app.services.items_import_parsing import _legacy_extract_tables
        ftype = "pdf" if filename.endswith(".pdf") else ("docx" if filename.endswith(".docx") else "image")
        try:
            tables = _legacy_extract_tables(content, filename, ftype)
            for row in (tables[0][1:] if tables else []):
                if len(row) >= 2 and row[1]:
                    parsed_rows.append({
                        "name": str(row[1]).strip(),
                        "qty": to_decimal(row[2]) if len(row) > 2 else Decimal("0"),
                        "unit_price": to_decimal(row[3]) if len(row) > 3 else Decimal("0"),
                        "total": to_decimal(row[4]) if len(row) > 4 else Decimal("0"),
                        "unit": str(row[5]).strip() if len(row) > 5 else None,
                    })
        except Exception as e:
            warnings.append(f"Ошибка парсера: {e}")

    num_m = re.search(r'(?:№|N|no)[.\s]*([A-Za-z0-9\-_/]+)', filename, re.IGNORECASE)
    doc_number = num_m.group(1) if num_m else None
    dt_m = re.search(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})', filename)
    doc_date = _coerce_date(f"{dt_m.group(3)}-{dt_m.group(2)}-{dt_m.group(1)}") if dt_m else None

    matched: List[WaybillParsedItem] = []
    for r in parsed_rows:
        raw_name, q, p = r.get("name") or "Позиция", r.get("qty") or Decimal("0"), r.get("unit_price") or Decimal("0")
        tot = r.get("total") or _calc_total(q, p)
        best_score, best_ci_id, best_pi_id = 0.0, None, None

        targets = [(ci.id, ci.source_item_id, ci.name, ci.quantity) for ci in cis] or \
                  [(None, pi.id, getattr(pi, "item_name", None) or getattr(pi, "name", ""), pi.quantity) for pi in pis]
        for c_id, p_id, t_name, t_qty in targets:
            s_name = SequenceMatcher(None, raw_name.lower(), (t_name or "").lower()).ratio()
            if q > 0 and t_qty and abs(float(q) - float(t_qty)) < 0.01:
                s_name = min(1.0, s_name + 0.15)
            if s_name > best_score:
                best_score, best_ci_id, best_pi_id = s_name, c_id, p_id

        matched.append(WaybillParsedItem(
            raw_name=raw_name, qty=q, unit_price=p, total=tot, unit=r.get("unit"),
            doc_number=doc_number, delivery_date=doc_date,
            suggested_contract_item_id=best_ci_id if best_score >= 0.35 else None,
            suggested_purchase_item_id=best_pi_id if best_score >= 0.35 else None,
            confidence=round(best_score, 2),
        ))

    return WaybillParseResponse(doc_number=doc_number, delivery_date=doc_date, items=matched, warnings=warnings)


@router.post("/apply-waybill", response_model=List[DeliveryItemOut])
async def apply_waybill(
    pid: int,
    data: WaybillApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    doc_d = _coerce_date(data.delivery_date)
    created: List[DeliveryItem] = []

    for item_data in data.items:
        d_date = _coerce_date(item_data.delivery_date) or doc_d
        doc_num = item_data.doc_number or data.doc_number
        st = item_data.status or "delivered"
        if item_data.contract_item_id:
            ci = await db.get(ContractItem, item_data.contract_item_id)
            if ci and ci.quantity and item_data.qty < ci.quantity:
                st = "partial"

        item = DeliveryItem(
            purchase_id=pid,
            contract_item_id=item_data.contract_item_id,
            purchase_item_id=item_data.purchase_item_id,
            product_id=item_data.product_id,
            name=item_data.name.strip(),
            unit=item_data.unit,
            qty=item_data.qty,
            unit_price=item_data.unit_price,
            total=_calc_total(item_data.qty, item_data.unit_price),
            delivery_date=d_date,
            doc_number=doc_num,
            status=st,
            notes=item_data.notes,
        )
        db.add(item)
        created.append(item)

    await db.commit()
    for it in created:
        await db.refresh(it)
    return created
