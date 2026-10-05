"""Контрольные суммы «выписка ↔ закупки» по субсидии — план
.planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1.

GET  /api/subsidies/{id}/payment-control                       — сверка целиком
GET  /api/subsidies/{id}/payment-control/codes                  — выбор статей (GET)
PUT  /api/subsidies/{id}/payment-control/codes                  — выбор статей (PUT, subsidy.edit)
GET  /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/candidates
POST /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/attach
POST /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/create-purchase

Права GET — видимость субсидии (та же двухуровневая модель, что у других
subsidy-scoped вкладок, см. app/auth/visibility.py::get_visible_subsidy_ids,
tab_key="payment_registry" — тот же, что уже использует реестр платежей для
субсидийного среза, ПРАВИЛО №6: не заводим отдельный tab_key только для этой
вкладки). Действия (PUT codes / attach / create-purchase) — subsidy.edit
(app/auth/permissions.py::has_org_key), тот же гейт, что у разнесения платежей
(app/routers/purchase_payment_matching.py::_get_subsidy_for_payments).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.auth.visibility import get_visible_subsidy_ids
from app.models.bank_statement import BankPayment
from app.models.subsidy import Subsidy

router = APIRouter(prefix="/api/subsidies", tags=["subsidy-payment-control"])

_PAYMENT_CONTROL_TAB_KEY = "payment_registry"


async def _get_subsidy_for_read(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await db.get(Subsidy, sid)
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    vis = await get_visible_subsidy_ids(current_user, db, _PAYMENT_CONTROL_TAB_KEY)
    if vis is not None and sid not in vis:
        raise HTTPException(403, "Нет доступа к сверке платежей этой субсидии")
    return s


async def _get_subsidy_for_write(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await _get_subsidy_for_read(sid, db, current_user)
    if not await has_org_key(current_user, db, s.org_id, "subsidy.edit", subsidy_id=sid):
        raise HTTPException(
            403,
            "Действие доступно только тому, у кого есть право редактировать субсидию",
        )
    return s


async def _get_bank_payment_or_404(bp_id: int, db: AsyncSession) -> BankPayment:
    bp = await db.get(BankPayment, bp_id)
    if not bp:
        raise HTTPException(404, "Платёж не найден")
    return bp


# ---------------------------------------------------------------------------
# GET /payment-control
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control")
async def get_payment_control(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.services.subsidy_payment_control import build_payment_control

    subsidy = await _get_subsidy_for_read(sid, db, current_user)
    return await build_payment_control(db, subsidy)


# ---------------------------------------------------------------------------
# GET/PUT /payment-control/codes
# ---------------------------------------------------------------------------

class _CodesBody(BaseModel):
    codes: List[str]


@router.get("/{sid}/payment-control/codes")
async def get_payment_control_codes(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.expense_code import ExpenseCode
    from sqlalchemy import select
    from app.services.subsidy_payment_control import get_search_codes

    await _get_subsidy_for_read(sid, db, current_user)
    codes, is_default = await get_search_codes(db, sid)
    directory_rows = (await db.execute(
        select(ExpenseCode).where(ExpenseCode.is_active.is_(True)).order_by(ExpenseCode.code)
    )).scalars().all()
    return {
        "codes": sorted(codes),
        "is_default": is_default,
        "directory": [
            {"code": c.code, "name": c.name, "kind": c.kind, "is_procurement": c.is_procurement}
            for c in directory_rows
        ],
    }


@router.put("/{sid}/payment-control/codes")
async def put_payment_control_codes(
    sid: int,
    body: _CodesBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.expense_code import ExpenseCode
    from sqlalchemy import select
    from app.services.subsidy_payment_control import get_search_codes, set_search_codes

    await _get_subsidy_for_write(sid, db, current_user)
    await set_search_codes(db, sid, body.codes)
    await db.commit()

    codes, is_default = await get_search_codes(db, sid)
    directory_rows = (await db.execute(
        select(ExpenseCode).where(ExpenseCode.is_active.is_(True)).order_by(ExpenseCode.code)
    )).scalars().all()
    return {
        "codes": sorted(codes),
        "is_default": is_default,
        "directory": [
            {"code": c.code, "name": c.name, "kind": c.kind, "is_procurement": c.is_procurement}
            for c in directory_rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /payment-control/bank-payments/{bp_id}/candidates
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control/bank-payments/{bp_id}/candidates")
async def get_bank_payment_candidates(
    sid: int,
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Кандидаты-закупки ЭТОЙ субсидии для строки выписки — переиспользует
    app/services/match_candidates.py::build_candidates (та же логика, что и
    общий /api/payments/registry/{bp_id}/match-suggestions), с фильтром по
    subsidy_id (ПРАВИЛО №6 — не второй скоринг).

    build_candidates() ищет среди закупок matched_contract_id/matched_contractor_id
    строки — для свежей (не прошедшей /match) строки оба пусты; подставляем
    contractor_id по ИНН получателя ВРЕМЕННО (на объекте ORM в памяти, без
    flush/commit — GET ничего не пишет) — тот же приём, что и обычный
    /match перед вызовом сверки, но без сохранения выбора."""
    await _get_subsidy_for_read(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from sqlalchemy import select
    from app.models.contractor import Contractor
    from app.models.purchase import Purchase as _Purchase
    from app.services.match_candidates import build_candidates

    orig_contractor_id = bp.matched_contractor_id
    if not bp.matched_contract_id and not bp.matched_contractor_id and bp.payee_inn:
        c = (await db.execute(
            select(Contractor).where(Contractor.inn == bp.payee_inn)
        )).scalars().first()
        if c:
            bp.matched_contractor_id = c.id
    try:
        candidates = await build_candidates(bp, db)
    finally:
        bp.matched_contractor_id = orig_contractor_id

    items = []
    seen_purchase_ids: set[int] = set()
    for c in candidates:
        for pid in c.get("purchase_ids", []):
            if pid in seen_purchase_ids:
                continue
            p = await db.get(_Purchase, pid)
            if p is None or p.subsidy_id != sid:
                continue
            seen_purchase_ids.add(pid)
            contractor_name = None
            if p.contractor_id:
                contractor = await db.get(Contractor, p.contractor_id)
                contractor_name = contractor.name if contractor else None
            items.append({
                "purchase_id": p.id,
                "registry_number": p.registry_number,
                "subject": p.subject or p.item_name,
                "contractor_name": contractor_name,
                "contract_price": float(p.contract_price) if p.contract_price is not None else None,
                "paid_by_statement": float(p.payment_amount) if p.payment_amount is not None else None,
                "reason": c.get("label"),
            })
    return {"items": items}


# ---------------------------------------------------------------------------
# POST /payment-control/bank-payments/{bp_id}/attach
# ---------------------------------------------------------------------------

class _AttachBody(BaseModel):
    purchase_id: int


@router.post("/{sid}/payment-control/bank-payments/{bp_id}/attach")
async def attach_bank_payment(
    sid: int,
    bp_id: int,
    body: _AttachBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    subsidy = await _get_subsidy_for_write(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from app.models.purchase import Purchase
    from decimal import Decimal
    purchase = await db.get(Purchase, body.purchase_id)
    if not purchase or purchase.subsidy_id != sid:
        raise HTTPException(404, "Закупка не найдена в этой субсидии")

    from app.services.payment_target import PaymentGroup
    from app.services.payment_lookup import attach, PaymentAttachError, ServicePeriodAttachConflict
    from app.services.payment_service_period import service_period_conflict_detail

    group = PaymentGroup(
        group_key=f"payment-control-{purchase.id}",
        subsidy_id=sid,
        registry_number=purchase.registry_number,
        contract_number=purchase.contract_number,
        is_framework=False,
        contractor_id=purchase.contractor_id,
        contractor_inn=bp.payee_inn,
        contractor_name=bp.payee_name,
        goods_amount=Decimal(0),
        services_amount=Decimal(0),
        unspecified_amount=Decimal(0),
        purchase_ids=[purchase.id],
        payments=[],
    )
    warnings: list[str] = []
    try:
        await attach(
            db, group, [bp.id],
            allocations={purchase.id: Decimal(str(bp.amount or 0))},
            warnings_out=warnings,
        )
    except ServicePeriodAttachConflict as exc:
        await db.rollback()
        raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
    except PaymentAttachError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))

    await db.commit()
    return {"ok": True, "warnings": warnings}


# ---------------------------------------------------------------------------
# POST /payment-control/bank-payments/{bp_id}/create-purchase
# ---------------------------------------------------------------------------

class _CreatePurchaseBody(BaseModel):
    feo_category_id: Optional[int] = None


@router.post("/{sid}/payment-control/bank-payments/{bp_id}/create-purchase")
async def create_purchase_from_bank_payment_endpoint(
    sid: int,
    bp_id: int,
    body: _CreatePurchaseBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    subsidy = await _get_subsidy_for_write(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from app.services.purchase_from_bank_payment import create_purchase_from_bank_payment

    try:
        result = await create_purchase_from_bank_payment(
            db, current_user, subsidy, bp, feo_category_id=body.feo_category_id,
        )
    except HTTPException:
        await db.rollback()
        raise

    await db.commit()
    await db.refresh(result.purchase)
    return {
        "purchase_id": result.purchase.id,
        "registry_number": result.purchase.registry_number,
        "warnings": result.warnings,
    }
