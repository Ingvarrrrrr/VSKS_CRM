"""«Чего не хватает» по каждой закупке прогона — слова владельца (контракт
GET /runs/{id}): «нет № и даты договора», «нет ИНН поставщика», «нет акта»,
«нет реквизитов платёжки»."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def build_report(db: AsyncSession, purchase_ids: list[int]) -> list[dict]:
    if not purchase_ids:
        return []

    from app.models.purchase import Purchase
    from app.models.contractor import Contractor
    from app.models.payment import Payment

    purchases = (await db.execute(
        select(Purchase).where(Purchase.id.in_(purchase_ids))
    )).scalars().all()
    contractor_ids = {p.contractor_id for p in purchases if p.contractor_id}
    contractors = {}
    if contractor_ids:
        rows = (await db.execute(select(Contractor).where(Contractor.id.in_(contractor_ids)))).scalars().all()
        contractors = {c.id: c for c in rows}

    payments = (await db.execute(
        select(Payment).where(Payment.purchase_id.in_(purchase_ids))
    )).scalars().all()
    payments_by_purchase: dict = {}
    for pay in payments:
        payments_by_purchase.setdefault(pay.purchase_id, []).append(pay)

    out = []
    for p in purchases:
        missing = []
        if p.contract_number_is_temporary or not p.contract_date:
            missing.append("нет № и даты договора")
        contractor = contractors.get(p.contractor_id) if p.contractor_id else None
        if not contractor or not contractor.inn:
            missing.append("нет ИНН поставщика")
        if not p.acceptance_doc_number and not p.acceptance_docs:
            missing.append("нет акта")
        pay_rows = payments_by_purchase.get(p.id, [])
        if pay_rows and all(not pay.document_number for pay in pay_rows):
            missing.append("нет реквизитов платёжки")

        out.append({
            "purchase_id": p.id,
            "registry_number": p.registry_number,
            "supplier": contractor.name if contractor else None,
            "status": p.status,
            "contract_amount": float(p.contract_price) if p.contract_price is not None else None,
            "paid_amount": float(sum((Decimal(str(pay.amount)) for pay in pay_rows if pay.amount is not None), Decimal(0))) if pay_rows else None,
            "missing": missing,
        })
    return out
