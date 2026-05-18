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
    # ВАЖНО: пропускаем номера из agreements — они относятся к субсидии, не к договору
    contracts_list = (bp.parsed_documents or {}).get("contracts", [])
    agreements_list_nums = {
        normalize_doc_number(a.get("number", ""))
        for a in (bp.parsed_documents or {}).get("agreements", [])
        if a.get("number")
    }

    if contracts_list:
        q = await db.execute(
            select(Contract).where(Contract.contractor_id == bp.matched_contractor_id)
        )
        all_contracts = q.scalars().all()

        for doc in contracts_list:
            norm_num = normalize_doc_number(doc.get("number", ""))
            if not norm_num:
                continue
            # Если этот номер совпадает с номером соглашения о субсидии — пропустить
            if norm_num in agreements_list_nums:
                continue
            # Дополнительная проверка: если номер совпадает с Subsidy.basis_doc_number в БД — пропустить
            sub_check = await db.execute(
                select(Subsidy).where(Subsidy.basis_doc_number == doc.get("number", "")).limit(1)
            )
            if sub_check.scalars().first():
                continue
            for contract in all_contracts:
                if normalize_doc_number(contract.number or "") == norm_num:
                    bp.matched_contract_id = contract.id
                    break
            if bp.matched_contract_id:
                break

    # Fallback: если contracts[] не нашёл — ищем по contractor_id (ровно 1 договор → берём его)
    if not bp.matched_contract_id and bp.matched_contractor_id:
        q2 = await db.execute(
            select(Contract).where(Contract.contractor_id == bp.matched_contractor_id)
        )
        fallback_contracts = q2.scalars().all()
        if len(fallback_contracts) == 1:
            bp.matched_contract_id = fallback_contracts[0].id

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

        # 27.4-19: amount-based exact match — если ровно одна закупка точно совпадает
        # по сумме с платежом (contract_price ИЛИ planned_total_price ИЛИ total_nmck)
        # → авто-привязка. Покрывает Юг-Логистика case: платёж 12090.25 → закупка 775 на 12090.25.
        if not matched_purchase and bp.amount is not None:
            from decimal import Decimal as _Dec
            bp_amt = _Dec(str(bp.amount))
            exact_matches = []
            for p in purchases:
                for fld in (p.contract_price, p.planned_total_price, p.total_nmck):
                    if fld is not None and _Dec(str(fld)) == bp_amt:
                        exact_matches.append(p)
                        break
            if len(exact_matches) == 1:
                bp.matched_purchase_id = exact_matches[0].id
                matched_purchase = True

        # Fallback: если у Contract ровно 1 Purchase — авто-привязка
        if not matched_purchase and len(purchases) == 1:
            bp.matched_purchase_id = purchases[0].id

    # Для advance purchases: parsed_documents.advance_reports[0] перезаписывает
    # contract_number/date в Purchase. Override (не if not) — bank_payment авторитетнее чека.
    if bp.matched_purchase_id:
        from datetime import datetime as _dt2
        purchase = await db.get(Purchase, bp.matched_purchase_id)
        if purchase and purchase.purchase_method == 'advance':
            advance_reports = (bp.parsed_documents or {}).get('advance_reports', [])
            if advance_reports:
                first = advance_reports[0] or {}
                if first.get('number'):
                    purchase.contract_number = str(first['number'])
                if first.get('date'):
                    try:
                        purchase.contract_date = _dt2.strptime(first['date'], "%d.%m.%Y").date()
                    except (ValueError, TypeError):
                        pass


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
