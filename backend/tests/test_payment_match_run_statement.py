"""«Разнести платежи» (run_match_payments) — 15.10.2026, ФАДМ 2026_3: кнопка
находила 110 из 122 платежей выписки, которые загрузчик разнёс на ФАДМ 2026_2.
Три причины, по тесту на каждую:
  1. пробный прогон не помнил выбранные строки — одинаковые суммы у одного ИНН
     получали один и тот же платёж;
  2. код расхода платежа («товар») не совпал с видом позиций закупки
     («услуга») — платёж отбрасывался, хотя другого нет;
  3. закупка разбита на товары и услуги, а оплачена одним платежом на всю сумму.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.expense_code import ExpenseCode
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_matching_run import run_match_payments

GOODS_CODE, SERVICES_CODE = "9300022", "9200032"


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _setup(db):
    for code, kind in ((GOODS_CODE, "товар"), (SERVICES_CODE, "услуга")):
        await db.merge(ExpenseCode(code=code, name=f"тест {kind}", kind=kind))
    s = Subsidy(name=f"Субсидия-{_uid()}", year=2026, require_planned_dates=False)
    c = Contractor(name=f"Контрагент-{_uid()}", inn=f"77{uuid.uuid4().int % 10**8:08d}")
    db.add_all([s, c])
    await db.commit()
    await db.refresh(s)
    await db.refresh(c)
    return s, c


async def _purchase(db, s, c, items):
    p = Purchase(item_name="Закупка", status="delivered", contractor_id=c.id, subsidy_id=s.id,
                 registry_number=f"REG-{_uid()}", contract_number=f"Д-{_uid()}")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    db.add_all([PurchaseItem(purchase_id=p.id, item_name="Позиция", item_type=t, quantity=1,
                             unit_price=Decimal(a), total_price=Decimal(a)) for t, a in items])
    await db.commit()
    return p


async def _bp(db, s, c, amount, day, code):
    bp = BankPayment(payee_inn=c.inn, amount=Decimal(amount), status=next(iter(EXECUTED_STATUSES)),
                     payment_number=_uid(), payment_date=date(2026, 5, day), subsidy_id=s.id,
                     purpose_text=f"(711К0232001;{code}) Соглашение 091-10-2026-008 от 28.01.2026 УПД {_uid()}")
    db.add(bp)
    await db.commit()
    await db.refresh(bp)
    return bp


def _found(report) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for g in report["attached"]:
        for it in g["items"]:
            out.setdefault(g["registry_number"], []).append(it["bank_payment_id"])
    return out


@pytest.mark.asyncio
async def test_same_amounts_get_distinct_payments_in_dry_run(db_session, test_org):
    """Ростелеком 11 870,60 ×3: три закупки, три платежа — каждой свой."""
    s, c = await _setup(db_session)
    purchases = [await _purchase(db_session, s, c, [("услуга", "11870.60")]) for _ in range(3)]
    bps = [await _bp(db_session, s, c, "11870.60", d, SERVICES_CODE) for d in (6, 9, 17)]

    found = _found(await run_match_payments(db_session, s.id, dry_run=True))

    assert {p.registry_number for p in purchases} == set(found)
    assert sorted(i for ids in found.values() for i in ids) == sorted(bp.id for bp in bps)


@pytest.mark.asyncio
async def test_expense_code_kind_mismatch_does_not_block(db_session, test_org):
    """390 000: в закупке «услуга», платёж кодом «товар» — другого платежа нет, берём его."""
    s, c = await _setup(db_session)
    p = await _purchase(db_session, s, c, [("услуга", "390000.00")])
    bp = await _bp(db_session, s, c, "390000.00", 21, GOODS_CODE)

    found = _found(await run_match_payments(db_session, s.id, dry_run=True))

    assert found == {p.registry_number: [bp.id]}


@pytest.mark.asyncio
async def test_goods_and_services_paid_by_one_payment(db_session, test_org):
    """ЦЕНТРАВТО 89 360,02 = товары 28 652,50 + услуги 60 707,52, один платёж."""
    s, c = await _setup(db_session)
    p = await _purchase(db_session, s, c, [("товар", "28652.50"), ("услуга", "60707.52")])
    bp = await _bp(db_session, s, c, "89360.02", 10, SERVICES_CODE)

    assert _found(await run_match_payments(db_session, s.id, dry_run=True)) == {p.registry_number: [bp.id]}

    await run_match_payments(db_session, s.id, dry_run=False)
    payments = (await db_session.execute(select(Payment).where(Payment.bank_payment_id == bp.id))).scalars().all()
    assert [pm.purchase_id for pm in payments] == [p.id]
    assert sum(pm.amount for pm in payments) == Decimal("89360.02")
