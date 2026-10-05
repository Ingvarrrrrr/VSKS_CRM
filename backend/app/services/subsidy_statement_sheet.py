"""Лист «Выписка» субсидии — план .planning/quick/2026-10-06-statement-control/
PLAN.md, п.6: GET /api/subsidies/{id}/statement.

Все строки bank_payments, видные субсидии по правилу
app/services/bank_payment_subsidy_scope.py::subsidy_scope_clause (ВСЕ
статусы, не только исполненные — в отличие от контрольного листа
app/services/subsidy_payment_control.py, который смотрит только EXECUTED_STATUSES).
ПРАВИЛО №6 — видимость строки субсидии считается ровно тем же правилом, что и
везде, второй фильтр `BankPayment.subsidy_id == ...` здесь не заводится.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment, BankStatementImport
from app.models.expense_code import ExpenseCode
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
from app.services.purchase_sheet_ref import resolve_sheet_ref


async def build_statement_sheet(db: AsyncSession, subsidy: Subsidy) -> dict:
    bp_rows = (await db.execute(
        select(BankPayment).where(subsidy_scope_clause(subsidy))
    )).scalars().all()

    code_rows = (await db.execute(select(ExpenseCode))).scalars().all()
    code_map = {c.code: c for c in code_rows}

    pay_rows = []
    if bp_rows:
        pay_rows = (await db.execute(
            select(Payment).where(Payment.bank_payment_id.in_([bp.id for bp in bp_rows]))
        )).scalars().all()
    payments_by_bp: dict[int, list[Payment]] = defaultdict(list)
    for pay in pay_rows:
        payments_by_bp[pay.bank_payment_id].append(pay)

    purchase_ids = {pay.purchase_id for pay in pay_rows if pay.purchase_id}
    purchase_map: dict[int, Purchase] = {}
    if purchase_ids:
        prows = (await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))).scalars().all()
        purchase_map = {p.id: p for p in prows}

    import_ids = {bp.import_id for bp in bp_rows if bp.import_id}
    import_map: dict[int, str] = {}
    if import_ids:
        irows = (await db.execute(
            select(BankStatementImport.id, BankStatementImport.file_name).where(
                BankStatementImport.id.in_(import_ids)
            )
        )).all()
        import_map = {r.id: r.file_name for r in irows}

    out_rows = []
    for bp in bp_rows:
        meta = code_map.get(bp.expense_code) if bp.expense_code else None
        attached = []
        for pay in payments_by_bp.get(bp.id, []):
            p = purchase_map.get(pay.purchase_id)
            if p is None:
                continue
            attached.append({
                "purchase_id": p.id,
                "registry_number": p.registry_number,
                "sheet_ref": resolve_sheet_ref(p),
            })
        out_rows.append({
            "id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "status": bp.status,
            "payee_name": bp.payee_name,
            "payee_inn": bp.payee_inn,
            "amount": float(bp.amount or 0),
            "purpose_text": bp.purpose_text,
            "expense_code": bp.expense_code,
            "expense_name": meta.name if meta else None,
            "is_procurement": bool(meta.is_procurement) if meta else None,
            "attached": attached,
            "import_file_name": import_map.get(bp.import_id) if bp.import_id else None,
        })

    out_rows.sort(key=lambda r: (r["payment_date"] or "", r["payment_number"] or ""))
    return {"rows": out_rows, "count": len(out_rows)}
