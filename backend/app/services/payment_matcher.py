"""Phase 22 — матчинг BankPayment с Contractor / Contract / Purchase."""
from __future__ import annotations
import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.purchase import Purchase


def _norm_inn(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\D", "", str(s))


def _norm_contract_number(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", "", str(s).upper().strip())


async def auto_match(db: AsyncSession, bp: BankPayment) -> dict:
    """Прогонит auto-matching для одной BankPayment in-place
    (мутирует bp.matched_contractor_id / matched_contract_id).

    Возвращает {contractor, contract, candidate_purchases: list[Purchase]}.
    Менеджер должен потом подтвердить матч через separate API endpoint.
    """
    result: dict = {"contractor": None, "contract": None, "candidate_purchases": []}

    # 1. Contractor по ИНН (exact)
    inn = _norm_inn(bp.payee_inn)
    if inn:
        c = (await db.execute(
            select(Contractor).where(Contractor.inn == inn).limit(1)
        )).scalar_one_or_none()
        if c:
            bp.matched_contractor_id = c.id
            result["contractor"] = c

    # 2. Contract по contract_number + contractor_id
    cn = _norm_contract_number(bp.parsed_contract_number)
    if cn and result["contractor"]:
        # Сравнение нормализованных номеров (case-insensitive, без пробелов)
        all_contracts = (await db.execute(
            select(Contract).where(Contract.contractor_id == result["contractor"].id)
        )).scalars().all()
        for ct in all_contracts:
            if _norm_contract_number(ct.number) == cn:
                bp.matched_contract_id = ct.id
                result["contract"] = ct
                break

    # 3. Candidate purchases — все Purchase под этим контрактом, не paid
    if result["contract"]:
        purchases = (await db.execute(
            select(Purchase).where(
                Purchase.contract_id == result["contract"].id,
                Purchase.status.in_(["delivered", "contracted", "ordered", "work_in_progress"]),
            )
        )).scalars().all()
        result["candidate_purchases"] = list(purchases)

    return result


async def match_all_in_import(db: AsyncSession, import_id: int) -> dict:
    """Прогон auto_match для всех bank_payments одного import. Не подтверждает,
    только заполняет matched_contractor_id / matched_contract_id."""
    rows = (await db.execute(
        select(BankPayment).where(BankPayment.import_id == import_id)
    )).scalars().all()
    matched = unmatched = 0
    for bp in rows:
        r = await auto_match(db, bp)
        if r["contract"]:
            matched += 1
        else:
            unmatched += 1
    await db.flush()
    return {"matched": matched, "unmatched": unmatched, "total": len(rows)}
