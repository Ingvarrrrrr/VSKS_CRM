"""Phase 27.1: contract_items CRUD router.

6 endpoints scoped under /api/purchases/{pid}/contract-items:
  GET    /                    — list contract items for a purchase
  POST   /                    — create a single contract item
  PUT    /                    — bulk replace all contract items (atomic delete-then-insert)
  PATCH  /{item_id}           — partial update a single contract item
  DELETE /{item_id}           — delete a single contract item
  POST   /copy-from-purchase  — D-01: copy all purchase_items → contract_items 1↔1

D-17-симметрия: все endpoints используют require_tab("purchases") — новых action'ов нет.
CD-3: router зарегистрирован в __init__.py ПЕРЕД purchases.router (catch-all guard).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.product_matcher import find_matching_product
from app.routers.purchases import _recalc_contract_price_from_contract_items
from app.schemas.schemas import ContractItemCreate, ContractItemOut, ContractItemUpdate

router = APIRouter(prefix="/api/purchases/{pid}/contract-items", tags=["contract_items"])


@router.get("", response_model=List[ContractItemOut],
            dependencies=[Depends(require_tab("purchases"))])
async def list_contract_items(pid: int, db: AsyncSession = Depends(get_db)):
    """List all contract items for a purchase, ordered by id."""
    result = await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == pid)
        .order_by(ContractItem.id)
    )
    return result.scalars().all()


@router.post("", response_model=ContractItemOut, status_code=201,
             dependencies=[Depends(require_tab("purchases"))])
async def create_contract_item(pid: int, data: ContractItemCreate,
                                db: AsyncSession = Depends(get_db)):
    """Create a single contract item for a purchase. Triggers D-07 auto-recalc."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})
    payload = data.model_dump(exclude_none=True)
    # D-08-симметрия: Fuzzy auto-link product if missing
    if not payload.get("product_id") and payload.get("name"):
        matched = await find_matching_product(db, payload["name"], org_id=p.org_id)
        if matched:
            payload["product_id"] = matched.id
            payload["match_confirmed"] = False
    ci = ContractItem(purchase_id=pid, **payload)
    db.add(ci)
    await db.commit()
    await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return ci


@router.put("", response_model=List[ContractItemOut],
            dependencies=[Depends(require_tab("purchases"))])
async def replace_all_contract_items(pid: int, items: List[ContractItemCreate],
                                      db: AsyncSession = Depends(get_db)):
    """Bulk replace — atomic delete-then-insert (паттерн purchases.py bulk replace)."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})
    await db.execute(delete(ContractItem).where(ContractItem.purchase_id == pid))

    # phase26-dd: validate source_item_id existence — фронт может слать ID
    # старых purchase_items, которые уже удалены в update_purchase bulk replace.
    from app.models.purchase_item import PurchaseItem
    src_ids = {it.source_item_id for it in items if getattr(it, 'source_item_id', None)}
    existing_src_ids: set = set()
    if src_ids:
        rows = await db.execute(
            select(PurchaseItem.id).where(PurchaseItem.id.in_(src_ids))
        )
        existing_src_ids = {r[0] for r in rows.all()}

    created = []
    for it in items:
        payload = it.model_dump(exclude_none=True)
        # Drop stale source_item_id silently — purchase_item уже не существует
        if payload.get("source_item_id") and payload["source_item_id"] not in existing_src_ids:
            payload.pop("source_item_id", None)
        if not payload.get("product_id") and payload.get("name"):
            matched = await find_matching_product(db, payload["name"], org_id=p.org_id)
            if matched:
                payload["product_id"] = matched.id
                payload["match_confirmed"] = False
        ci = ContractItem(purchase_id=pid, **payload)
        db.add(ci)
        created.append(ci)
    await db.commit()
    for ci in created:
        await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return created


@router.patch("/{item_id}", response_model=ContractItemOut,
              dependencies=[Depends(require_tab("purchases"))])
async def patch_contract_item(pid: int, item_id: int, data: ContractItemUpdate,
                               db: AsyncSession = Depends(get_db)):
    """Partial update a single contract item. Triggers D-07 auto-recalc."""
    ci = await db.get(ContractItem, item_id)
    if not ci or ci.purchase_id != pid:
        raise HTTPException(404, detail={"code": "CONTRACT_ITEM_NOT_FOUND",
                                          "message": f"Позиция договора #{item_id} не найдена"})
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(ci, k, v)
    await db.commit()
    await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return ci


@router.delete("/{item_id}", status_code=204,
               dependencies=[Depends(require_tab("purchases"))])
async def delete_contract_item(pid: int, item_id: int,
                                db: AsyncSession = Depends(get_db)):
    """Delete a single contract item. Triggers D-07 auto-recalc."""
    ci = await db.get(ContractItem, item_id)
    if not ci or ci.purchase_id != pid:
        raise HTTPException(404, detail={"code": "CONTRACT_ITEM_NOT_FOUND",
                                          "message": f"Позиция договора #{item_id} не найдена"})
    await db.delete(ci)
    await db.commit()
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return None


@router.post("/copy-from-purchase", response_model=List[ContractItemOut],
             dependencies=[Depends(require_tab("purchases"))])
async def copy_from_purchase_items(pid: int, db: AsyncSession = Depends(get_db)):
    """D-01: «Скопировать из заявки» — 1↔1 копия purchase_items → contract_items.

    Перезаписывает существующие contract_items для этой закупки.
    Возвращает 422 если у закупки нет purchase_items.
    """
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})
    items_res = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
        .order_by(PurchaseItem.id)
    )
    purchase_items = items_res.scalars().all()
    if not purchase_items:
        raise HTTPException(
            422,
            detail={
                "code": "NO_PURCHASE_ITEMS",
                "message": (
                    "В заявке нет позиций для копирования. Добавьте позиции в раздел «Заявка» "
                    "или импортируйте КП через кнопку «Импорт из файла/QR»."
                ),
            }
        )
    # Overwrite existing contract_items
    await db.execute(delete(ContractItem).where(ContractItem.purchase_id == pid))
    created = []
    for pi in purchase_items:
        ci = ContractItem(
            purchase_id=pid,
            source_item_id=pi.id,
            product_id=pi.product_id,
            name=pi.item_name,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total=pi.total_price,
            match_confirmed=True,
        )
        db.add(ci)
        created.append(ci)
    await db.commit()
    for ci in created:
        await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return created
