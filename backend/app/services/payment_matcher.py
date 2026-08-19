"""Phase 22 — матчинг BankPayment с Contractor / Subsidy / Contract / Purchase.

4-шаговый алгоритм:
  1. Contractor по ИНН (точное совпадение payee_inn)
  2. Subsidy по basis_doc_number + basis_doc_date; fallback: только по номеру
  3. Contract: contractor_id + любой номер из parsed_documents.contracts[]
  4. Purchase: acceptance_doc_number из parsed_documents.acts[]; fallback: единственный Purchase контракта
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy

# Этап 3: normalize_doc_number перенесена в payment_basis.py — ре-экспорт
# здесь, чтобы существующие импорты (`from app.services.payment_matcher import
# normalize_doc_number`) не сломались.
from app.services.payment_basis import normalize_doc_number  # noqa: F401


async def resolve_subsidy(
    db: AsyncSession,
    basis_doc_number: Optional[str],
    basis_doc_date=None,
    parsed_documents: Optional[dict] = None,
    subsidy_code: Optional[str] = None,
) -> Optional[Subsidy]:
    """Единая логика поиска Subsidy по документу-основанию платежа.

    Порядок: basis_doc_number+date (точно) → basis_doc_number (только номер) →
    agreements[] из parsed_documents (СОГЛАШЕНИЕ в назначении платежа) →
    subsidy_code. Используется и в auto_match (для matched_subsidy_id, после
    того как найден контрагент), и напрямую при импорте — для bank_payments.subsidy_id/
    org_id (Этап 1), где привязка НЕ должна зависеть от того, опознан ли контрагент
    (платежи физлицам/авансовые тоже относятся к субсидии по тому же basis_doc_number).
    """
    if basis_doc_number and basis_doc_date:
        q = await db.execute(
            select(Subsidy).where(
                Subsidy.basis_doc_number == basis_doc_number,
                Subsidy.basis_doc_date == basis_doc_date,
            ).limit(1)
        )
        s = q.scalar_one_or_none()
        if s:
            return s

    if basis_doc_number:
        q = await db.execute(
            select(Subsidy).where(Subsidy.basis_doc_number == basis_doc_number).limit(1)
        )
        s = q.scalar_one_or_none()
        if s:
            return s

    # Fallback: СОГЛАШЕНИЕ из parsed_documents.agreements (purpose_text)
    if parsed_documents:
        from datetime import datetime as _dt
        agreements_list = parsed_documents.get("agreements", [])
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
                        return s
                except (ValueError, TypeError):
                    pass
            # без даты — только по номеру
            q = await db.execute(
                select(Subsidy).where(Subsidy.basis_doc_number == num).limit(1)
            )
            s = q.scalar_one_or_none()
            if s:
                return s

    # Дополнительный fallback: subsidy_code если есть поле
    if subsidy_code:
        try:
            q = await db.execute(
                select(Subsidy).where(Subsidy.code == subsidy_code).limit(1)
            )
            s = q.scalar_one_or_none()
            if s:
                return s
        except Exception:
            pass  # Поле code может отсутствовать в модели Subsidy

    return None


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

    # 2. Subsidy
    s = await resolve_subsidy(db, bp.basis_doc_number, bp.basis_doc_date, bp.parsed_documents, bp.subsidy_code)
    if s:
        bp.matched_subsidy_id = s.id

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

    # Этап 0 (попутная гигиена, synchronous-knitting-thacker.md): раньше здесь
    # advance_reports[0] безусловно перезаписывал Purchase.contract_number/date
    # как побочный эффект КАЖДОГО auto_match — включая rematch(only_unmatched=false),
    # то есть чужая закупка переписывалась при каждом переигрывании матчинга.
    # Вынесено в apply_advance_report_override() ниже — вызывается ЯВНО только в
    # момент подтверждения платежа (bank_statements.py::confirm_bank_payment →
    # purchase_payments.py::create_payments_from_bank, и
    # payment_lookup.py::attach), а не при каждом (re)matching.


def apply_advance_report_override(purchase: Optional[Purchase], bp: BankPayment) -> None:
    """Аванс-отчёт из назначения платежа (parsed_documents.advance_reports[0])
    авторитетнее уже сохранённого Purchase.contract_number/contract_date для
    авансовых закупок (purchase_method == 'advance') — bank_payment это
    реальный чек, а не то, что менеджер мог ввести вручную при создании.

    Вызывать ТОЛЬКО в момент, когда платёж реально подтверждается/разносится
    на эту закупку (не на каждый auto_match/rematch — см. докстринг в
    auto_match() выше, почему раньше это было ошибкой)."""
    if not purchase or purchase.purchase_method != 'advance':
        return
    advance_reports = (bp.parsed_documents or {}).get('advance_reports', [])
    if not advance_reports:
        return
    first = advance_reports[0] or {}
    if first.get('number'):
        purchase.contract_number = str(first['number'])
    if first.get('date'):
        from datetime import datetime as _dt2
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
