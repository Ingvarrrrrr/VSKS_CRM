"""Справочник кодов направления расходования целевых средств (КРЦС).

Этап 2 утверждённого плана. CRUD по образцу других справочников проекта
(см. app.routers.okpd2 — публичное чтение; запись — только admin.settings,
как и настройки организации в app.routers.settings).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.expense_code import ExpenseCode

router = APIRouter(prefix="/api/expense-codes", tags=["expense-codes"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ExpenseCodeOut(BaseModel):
    code: str
    parent_code: Optional[str] = None
    name: str
    kind: Optional[str] = None
    is_procurement: bool
    is_active: bool

    class Config:
        from_attributes = True


class ExpenseCodeCreate(BaseModel):
    code: str
    parent_code: Optional[str] = None
    name: str
    kind: Optional[str] = None
    is_procurement: bool = False
    is_active: bool = True


class ExpenseCodeUpdate(BaseModel):
    parent_code: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    is_procurement: Optional[bool] = None
    is_active: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ExpenseCodeOut])
async def list_expense_codes(
    q: Optional[str] = Query(None, description="Поиск по коду или наименованию"),
    kind: Optional[str] = Query(None),
    is_procurement: Optional[bool] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    stmt = select(ExpenseCode)
    if not include_inactive:
        stmt = stmt.where(ExpenseCode.is_active.is_(True))
    if kind:
        stmt = stmt.where(ExpenseCode.kind == kind)
    if is_procurement is not None:
        stmt = stmt.where(ExpenseCode.is_procurement.is_(is_procurement))
    if q:
        q = q.strip()
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    ExpenseCode.code.like(f"{q}%"),
                    func.lower(ExpenseCode.name).like(like),
                )
            )
    stmt = stmt.order_by(ExpenseCode.code)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ExpenseCodeOut)
async def create_expense_code(
    body: ExpenseCodeCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("admin.settings")),
):
    code = body.code.strip()
    if not code:
        raise HTTPException(400, "Код обязателен")
    existing = await db.get(ExpenseCode, code)
    if existing:
        raise HTTPException(409, f"Код {code} уже существует")

    row = ExpenseCode(
        code=code,
        parent_code=(body.parent_code or None),
        name=body.name.strip(),
        kind=(body.kind or None),
        is_procurement=body.is_procurement,
        is_active=body.is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{code}", response_model=ExpenseCodeOut)
async def update_expense_code(
    code: str,
    body: ExpenseCodeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("admin.settings")),
):
    row = await db.get(ExpenseCode, code)
    if not row:
        raise HTTPException(404, "Код расходов не найден")

    if body.parent_code is not None:
        row.parent_code = body.parent_code or None
    if body.name is not None:
        row.name = body.name.strip()
    if body.kind is not None:
        row.kind = body.kind or None
    if body.is_procurement is not None:
        row.is_procurement = body.is_procurement
    if body.is_active is not None:
        row.is_active = body.is_active

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{code}")
async def delete_expense_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("admin.settings")),
):
    row = await db.get(ExpenseCode, code)
    if not row:
        raise HTTPException(404, "Код расходов не найден")
    # Мягкое удаление — как ResponsiblePerson: код мог быть уже использован
    # в исторических платежах, физическое удаление сломало бы им expense_kind.
    row.is_active = False
    await db.commit()
    return {"ok": True}
