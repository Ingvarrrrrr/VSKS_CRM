from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.contract import Contract
from app.models.contract_subsidy import ContractSubsidy
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.schemas.schemas import ContractCreate, ContractOut, ContractSubsidyOut
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.models.subsidy import Subsidy
from typing import List, Optional
from decimal import Decimal

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

@router.get("/", response_model=List[ContractOut])
async def list_contracts(
    subsidy_id: Optional[int] = Query(None),
    contract_type: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contractor_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Contract).options(
        selectinload(Contract.contractor),
        selectinload(Contract.subsidy),
        selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy),
    ).order_by(Contract.id.desc())
    if subsidy_id is not None:
        q = q.where(Contract.subsidy_id == subsidy_id)
    if contract_type is not None:
        q = q.where(Contract.contract_type == contract_type)
    if purchase_method is not None:
        q = q.where(Contract.purchase_method == purchase_method)
    if status is not None:
        q = q.where(Contract.status == status)
    if contractor_id is not None:
        q = q.where(Contract.contractor_id == contractor_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Contract.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q)
    contracts = result.scalars().all()
    out = []
    for c in contracts:
        pay_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.delivery_payment_amount), 0))
            .where(Purchase.contract_id == c.id)
        )
        total_payment = pay_result.scalar() or Decimal("0")
        ordered_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.contract_price), 0))
            .where(Purchase.contract_id == c.id)
        )
        total_ordered = ordered_result.scalar() or Decimal("0")
        paid_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.payment_amount), 0))
            .where(Purchase.contract_id == c.id, Purchase.status == "paid")
        )
        total_paid = paid_result.scalar() or Decimal("0")
        d = ContractOut.model_validate(c)
        d.total_payment = total_payment
        d.remaining = (c.max_amount or Decimal("0")) - total_payment
        d.total_ordered = total_ordered
        d.total_paid = total_paid
        if c.contractor:
            d.contractor_name = c.contractor.name
            d.contractor_inn = c.contractor.inn
        if c.subsidy:
            d.subsidy_name = c.subsidy.name
        d.extra_subsidies = [
            ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
            for es in (c.extra_subsidies or [])
        ]
        out.append(d)
    return out

@router.post("/", response_model=ContractOut)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ALL_ROLES)),
):
    # Duplicate check: same number + contractor INN + date + amount
    if data.contractor_id and data.number:
        dup_q = select(Contract).where(
            Contract.number == data.number,
            Contract.contractor_id == data.contractor_id,
        )
        if data.date:
            dup_q = dup_q.where(Contract.date == data.date)
        if data.max_amount is not None:
            dup_q = dup_q.where(Contract.max_amount == data.max_amount)
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            raise HTTPException(
                409,
                f"Договор с таким номером, контрагентом и датой уже существует (ID {dup.id})"
            )
    extra_ids = data.extra_subsidy_ids or []
    dump = data.model_dump(exclude={"extra_subsidy_ids"})
    c = Contract(**dump)
    db.add(c)
    await db.flush()
    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=c.id, subsidy_id=sid))
    await db.commit()
    await db.refresh(c)
    result = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == c.id)
    )
    c = result.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return d

@router.put("/{cid}", response_model=ContractOut)
async def update_contract(cid: int, data: ContractCreate, db: AsyncSession = Depends(get_db), _=Depends(require_role(*MANAGER_ROLES))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    old_number = c.number
    extra_ids = data.extra_subsidy_ids or []
    for k, v in data.model_dump(exclude={"extra_subsidy_ids"}).items():
        setattr(c, k, v)
    # Sync changes to linked purchases
    if data.number != old_number or data.date is not None:
        linked = await db.execute(select(Purchase).where(Purchase.contract_id == cid))
        for p in linked.scalars().all():
            if data.number != old_number:
                p.contract_number = data.number
            if data.date is not None:
                p.contract_date = data.date
            if data.contractor_id is not None:
                p.contractor_id = data.contractor_id
    # Replace extra subsidies
    old_extras = await db.execute(select(ContractSubsidy).where(ContractSubsidy.contract_id == cid))
    for es in old_extras.scalars().all():
        await db.delete(es)
    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=cid, subsidy_id=sid))
    await db.commit()
    result2 = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == cid)
    )
    c = result2.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return d

@router.delete("/{cid}")
async def delete_contract(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_role(*ADMIN_ROLES))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/migrate-from-purchases")
async def migrate_contracts_from_purchases(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("superadmin", "account_owner", "admin")),
):
    """Create Contract records from purchases.contract_number strings (skip existing)."""
    # Get all purchases with a contract_number set but no contract_id
    q = select(Purchase).where(
        Purchase.contract_number.isnot(None),
        Purchase.contract_number != "",
    )
    result = await db.execute(q)
    purchases = result.scalars().all()

    # Existing contract numbers
    existing_result = await db.execute(select(Contract.number))
    existing_numbers = {row[0] for row in existing_result.all() if row[0]}

    created = 0
    skipped = 0
    # Map: contract_number -> new Contract (for purchases to link to)
    new_contracts: dict[str, Contract] = {}

    for p in purchases:
        num = (p.contract_number or "").strip()
        if not num:
            continue
        if num in existing_numbers or num in new_contracts:
            skipped += 1
            continue
        c = Contract(
            number=num,
            date=p.contract_date if hasattr(p, "contract_date") else None,
            contract_type="single",
            subsidy_id=p.subsidy_id,
            status="active",
        )
        db.add(c)
        new_contracts[num] = c
        created += 1

    if new_contracts:
        await db.flush()
        # Link purchases to their new contracts
        for p in purchases:
            num = (p.contract_number or "").strip()
            if num in new_contracts and p.contract_id is None:
                p.contract_id = new_contracts[num].id

    await db.commit()
    return {"created": created, "skipped": skipped}


# ── Non-router helper ──────────────────────────────────────────────────────────

async def ensure_contract_linked(p: Purchase, db: AsyncSession) -> None:
    """Find-or-create a Contract for this purchase and link it via purchase.contract_id.

    Uniqueness key: contract_number + contractor_id + contractor INN + contract_date.
    If any of the last 3 are absent they are simply omitted from the lookup
    (making the match less strict when data is incomplete).
    """
    num = (p.contract_number or "").strip()
    if not num:
        return

    # Already linked — sync any changed fields (date, contractor) to contract record
    if p.contract_id:
        existing = await db.get(Contract, p.contract_id)
        if existing and existing.number == num:
            if p.contract_date and existing.date != p.contract_date:
                existing.date = p.contract_date
            if p.contractor_id and existing.contractor_id != p.contractor_id:
                existing.contractor_id = p.contractor_id
            return

    # Resolve contractor INN if we have a contractor_id
    inn: Optional[str] = None
    if p.contractor_id:
        inn_row = await db.execute(
            select(Contractor.inn).where(Contractor.id == p.contractor_id)
        )
        inn = inn_row.scalar_one_or_none()

    # Build lookup query with all 4 uniqueness parameters
    q = (
        select(Contract)
        .outerjoin(Contractor, Contract.contractor_id == Contractor.id)
        .where(Contract.number == num)
    )
    if p.contractor_id:
        q = q.where(Contract.contractor_id == p.contractor_id)
    if p.contract_date:
        q = q.where(Contract.date == p.contract_date)
    if inn:
        q = q.where(Contractor.inn == inn)

    contract = (await db.execute(q)).scalar_one_or_none()

    if not contract:
        contract = Contract(
            number=num,
            date=p.contract_date,
            contract_type=p.purchase_contract_type or "single",
            contractor_id=p.contractor_id,
            subsidy_id=p.subsidy_id,
            status="active",
        )
        db.add(contract)
        await db.flush()

    p.contract_id = contract.id
