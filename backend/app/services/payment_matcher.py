"""Phase 22 — матчинг BankPayment с Contractor / Subsidy / Contract / Purchase.

4-шаговый алгоритм:
  1. Contractor по ИНН (точное совпадение payee_inn)
  2. Subsidy по basis_doc_number + basis_doc_date; fallback: только по номеру
  3. Contract: contractor_id + любой номер из parsed_documents.contracts[]
  4. Purchase: acceptance_doc_number из parsed_documents.acts[]; fallback: единственный Purchase контракта
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy


def normalize_doc_number(s: str) -> str:
    if not s:
        return ""
    return s.replace(" ", "").replace("-", "").replace("/", "").replace(".", "").upper()


async def auto_match(bp: BankPayment, db: AsyncSession) -> None:
    """Заполняет matched_*_id поля без commit. Caller сам делает db.commit()."""

    # 1. Contractor по ИНН (точное совпадение)
    if bp.payee_inn:
        q = await db.execute(select(Contractor).where(Contractor.inn == bp.payee_inn).limit(1))
        contractor = q.scalar_one_or_none()
        if contractor:
            bp.matched_contractor_id = contractor.id

    if not bp.matched_contractor_id:
        return  # Без контрагента дальше не идём

    # 2. Subsidy: basis_doc_number + basis_doc_date (точная) → fallback только по номеру
    if bp.basis_doc_number and bp.basis_doc_date:
        q = await db.execute(
            select(Subsidy).where(
                Subsidy.basis_doc_number == bp.basis_doc_number,
                Subsidy.basis_doc_date == bp.basis_doc_date,
            ).limit(1)
        )
        s = q.scalar_one_or_none()
        if s:
            bp.matched_subsidy_id = s.id

    if not bp.matched_subsidy_id and bp.basis_doc_number:
        q = await db.execute(
            select(Subsidy).where(Subsidy.basis_doc_number == bp.basis_doc_number).limit(1)
        )
        s = q.scalar_one_or_none()
        if s:
            bp.matched_subsidy_id = s.id

    # Fallback: СОГЛАШЕНИЕ из parsed_documents.agreements (purpose_text)
    if not bp.matched_subsidy_id:
        from datetime import datetime as _dt
        agreements_list = (bp.parsed_documents or {}).get("agreements", [])
        for a in agreements_list:
            num = a.get("number")
            date_str = a.get("date")
            if not num:
                continue
            # с датой — точное совпадение
            if date_str:
                try:
                    d = _dt.strptime(date_str, "%d.%m.%Y").date()
                    q = await db.execute(
                        select(Subsidy).where(
                            Subsidy.basis_doc_number == num,
                            Subsidy.basis_doc_date == d,
                        ).limit(1)
                    )
                    s = q.scalar_one_or_none()
                    if s:
                        bp.matched_subsidy_id = s.id
                        break
                except (ValueError, TypeError):
                    pass
            # без даты — только по номеру
            if not bp.matched_subsidy_id:
                q = await db.execute(
                    select(Subsidy).where(Subsidy.basis_doc_number == num).limit(1)
                )
                s = q.scalar_one_or_none()
                if s:
                    bp.matched_subsidy_id = s.id
                    break

    # Дополнительный fallback: subsidy_code если есть поле
    if not bp.matched_subsidy_id and bp.subsidy_code:
        try:
            q = await db.execute(
                select(Subsidy).where(Subsidy.code == bp.subsidy_code).limit(1)
            )
            s = q.scalar_one_or_none()
            if s:
                bp.matched_subsidy_id = s.id
        except Exception:
            pass  # Поле code может отсутствовать в модели Subsidy

    # 3. Contract: contractor_id + ANY parsed_documents.contracts[*].number
    contracts_list = (bp.parsed_documents or {}).get("contracts", [])
    if contracts_list:
        q = await db.execute(
            select(Contract).where(Contract.contractor_id == bp.matched_contractor_id)
        )
        all_contracts = q.scalars().all()

        for doc in contracts_list:
            norm_num = normalize_doc_number(doc.get("number", ""))
            if not norm_num:
                continue
            for contract in all_contracts:
                if normalize_doc_number(contract.number or "") == norm_num:
                    bp.matched_contract_id = contract.id
                    break
            if bp.matched_contract_id:
                break

    # 4. Purchase: acceptance_doc_number из acts[]; fallback: единственный Purchase контракта
    if bp.matched_contract_id:
        q = await db.execute(
            select(Purchase).where(Purchase.contract_id == bp.matched_contract_id)
        )
        purchases = q.scalars().all()

        acts_list = (bp.parsed_documents or {}).get("acts", [])
        matched_purchase = False
        for act in acts_list:
            norm_act = normalize_doc_number(act.get("number", ""))
            if not norm_act:
                continue
            for p in purchases:
                if p.acceptance_doc_number and normalize_doc_number(p.acceptance_doc_number) == norm_act:
                    bp.matched_purchase_id = p.id
                    matched_purchase = True
                    break
            if matched_purchase:
                break

        # Fallback: если у Contract ровно 1 Purchase — авто-привязка
        if not matched_purchase and len(purchases) == 1:
            bp.matched_purchase_id = purchases[0].id


async def match_all_in_import(db: AsyncSession, import_id: int) -> dict:
    """Прогоняет auto_match на все BankPayment этого импорта. Возвращает счётчики."""
    q = await db.execute(select(BankPayment).where(BankPayment.import_id == import_id))
    counts = {
        "matched_contractor": 0,
        "matched_subsidy": 0,
        "matched_contract": 0,
        "matched_purchase": 0,
        "total": 0,
    }
    for bp in q.scalars().all():
        counts["total"] += 1
        await auto_match(bp, db)
        if bp.matched_contractor_id:
            counts["matched_contractor"] += 1
        if bp.matched_subsidy_id:
            counts["matched_subsidy"] += 1
        if bp.matched_contract_id:
            counts["matched_contract"] += 1
        if bp.matched_purchase_id:
            counts["matched_purchase"] += 1
    await db.commit()
    return counts
