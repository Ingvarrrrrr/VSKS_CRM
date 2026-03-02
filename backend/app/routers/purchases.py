from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.schemas.schemas import PurchaseCreate, PurchaseOut
from app.auth.jwt import get_current_user, require_role
from app.config import settings
from typing import List, Optional
from decimal import Decimal
from io import BytesIO
from datetime import datetime
try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

@router.get("/", response_model=List[PurchaseOut])
async def list_purchases(
    contract_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user)
):
    q = select(Purchase)
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        q = q.where(Purchase.feo_category_id == feo_category_id)
    if status:
        q = q.where(Purchase.status == status)
    result = await db.execute(q.order_by(Purchase.id.desc()))
    return result.scalars().all()

@router.post("/", response_model=PurchaseOut)
async def create_purchase(data: PurchaseCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    # Auto-increment purchase_number
    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    # Check subsidy limit
    if data.final_total_amount:
        total_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.final_total_amount), 0))
            .where(Purchase.confirmed == True)
        )
        current_total = total_result.scalar() or Decimal("0")
        if current_total + data.final_total_amount > Decimal(str(settings.SUBSIDY_LIMIT)):
            raise HTTPException(400, f"Превышен лимит субсидии ({settings.SUBSIDY_LIMIT} ₽)")

    p = Purchase(**data.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

@router.put("/{pid}", response_model=PurchaseOut)
async def update_purchase(pid: int, data: PurchaseCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin", "manager"))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return p

@router.delete("/{pid}")
async def delete_purchase(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role("admin"))):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}

@router.get("/export/excel")
async def export_purchases_to_excel(
    contract_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user)
):
    """Экспорт заказов в Excel"""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    
    # Получаем данные
    q = select(Purchase).order_by(Purchase.id.desc())
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if status:
        q = q.where(Purchase.status == status)
    result = await db.execute(q)
    purchases = result.scalars().all()
    
    # Получаем подрядчиков и контракты для связей
    contractors_result = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_result.scalars().all()}
    
    contracts_result = await db.execute(select(Contract))
    contracts = {c.id: c.number for c in contracts_result.scalars().all()}
    
    # Создаём Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Заказы"
    
    # Заголовки
    headers = [
        "ID", "Номер заказа", "Наименование", "Тип", "Кол-во", "Ед.",
        "Цена ед.", "Сумма", "Статус", "Подрядчик", "Контракт",
        "Подтверждён", "Итого сумма"
    ]
    ws.append(headers)
    
    # Данные
    for p in purchases:
        ws.append([
            p.id,
            p.order_number or "",
            p.item_name or "",
            p.item_type or "",
            float(p.planned_quantity) if p.planned_quantity else 0,
            p.unit or "",
            float(p.planned_unit_price) if p.planned_unit_price else 0,
            float(p.planned_total_price) if p.planned_total_price else 0,
            p.status or "",
            contractors.get(p.contractor_id, ""),
            contracts.get(p.contract_id, ""),
            "Да" if p.confirmed else "Нет",
            float(p.final_total_amount) if p.final_total_amount else 0
        ])
    
    # Сохраняем в буфер
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# PATCH /purchases/{id}/status - смена статуса
@router.patch("/{purchase_id}/status")
async def change_purchase_status(
    purchase_id: int,
    status: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    
    purchase.status = status
    db.commit()
    
    return {"ok": True, "status": status}
