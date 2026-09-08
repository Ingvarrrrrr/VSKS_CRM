"""Find-or-create Contract for a Purchase, keeping purchase.contract_id linked.

Вынесено из app/routers/contracts.py (Правило №5, резка волны 2026-09-08,
сессия «contracts.py 1323 → core»). purchases.py и purchase_transitions.py
импортируют `from app.routers.contracts import ensure_contract_linked` —
contracts.py ре-экспортирует это имя отсюда, чтобы оба потребителя
продолжали работать без изменений импорта.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.purchase import Purchase


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
