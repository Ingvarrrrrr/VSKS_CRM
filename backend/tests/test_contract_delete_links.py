# -*- coding: utf-8 -*-
"""app/services/contract_delete.py — гвард удаления договора (contracts.py::

DELETE /api/contracts/{cid} раньше делал просто db.delete(c) + commit и падал
IntegrityError-ом на FK bank_payments.matched_contract_id (NO ACTION) — живой
пример: договор id=1137 «ВРЕМ-635» с 17 неподтверждёнными строками выписки.

Три сценария ниже:
  (а) договор с НЕподтверждённой строкой bank_payments — удаляется, у строки
      matched_contract_id становится NULL;
  (б) договор с ПОДТВЕРЖДЁННОЙ строкой — 409, договор остаётся в БД;
  (в) договор с привязанной закупкой — 409, текст содержит номер закупки
      (registry_number, формат «РЕЕ-2026-00001»).

Тесты идут через реальную БД (db_session — транзакция с откатом, см.
conftest.py), т.к. assert_contract_deletable_and_unlink делает реальные
SELECT/UPDATE с FK-зависимостями, которые нельзя подделать офлайн.
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.contract import Contract
from app.models.bank_statement import BankPayment
from app.services.contract_delete import assert_contract_deletable_and_unlink


async def _make_contract(db_session, number=None) -> Contract:
    contract = Contract(
        number=number or f"ДОГ-{uuid.uuid4().hex[:8]}",
        contract_type="single",
        status="active",
    )
    db_session.add(contract)
    await db_session.commit()
    await db_session.refresh(contract)
    return contract


async def _make_bank_payment(db_session, contract_id, confirmed: bool) -> BankPayment:
    bp = BankPayment(
        matched_contract_id=contract_id,
        matched_confirmed=confirmed,
        amount=1000,
        payment_date=date(2026, 1, 1),
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)
    return bp


@pytest.mark.asyncio
async def test_unconfirmed_bank_payment_unlinked_and_contract_deleted(db_session):
    contract = await _make_contract(db_session)
    bp = await _make_bank_payment(db_session, contract.id, confirmed=False)

    # Не должно бросить — неподтверждённое автосопоставление снимается само.
    await assert_contract_deletable_and_unlink(db_session, contract.id)
    await db_session.delete(contract)
    await db_session.commit()

    await db_session.refresh(bp)
    assert bp.matched_contract_id is None

    gone = (await db_session.execute(
        select(Contract).where(Contract.id == contract.id)
    )).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_confirmed_bank_payment_blocks_delete(db_session):
    contract = await _make_contract(db_session)
    bp = await _make_bank_payment(db_session, contract.id, confirmed=True)

    with pytest.raises(HTTPException) as exc_info:
        await assert_contract_deletable_and_unlink(db_session, contract.id)
    assert exc_info.value.status_code == 409
    assert "подтверждены" in exc_info.value.detail

    # Договор жив, строка выписки не тронута.
    still_there = (await db_session.execute(
        select(Contract).where(Contract.id == contract.id)
    )).scalar_one_or_none()
    assert still_there is not None
    await db_session.refresh(bp)
    assert bp.matched_contract_id == contract.id


@pytest.mark.asyncio
async def test_purchase_on_contract_blocks_delete_and_names_it(db_session, make_purchase):
    contract = await _make_contract(db_session)
    purchase = await make_purchase(contract_id=contract.id)
    # registry_number проставляется листенером after_flush при INSERT — к
    # этому моменту (после make_purchase's commit+refresh) уже должен стоять.
    await db_session.refresh(purchase)
    assert purchase.registry_number, "registry_number должен быть проставлен автособытием after_flush"

    with pytest.raises(HTTPException) as exc_info:
        await assert_contract_deletable_and_unlink(db_session, contract.id)
    assert exc_info.value.status_code == 409
    assert purchase.registry_number in exc_info.value.detail

    still_there = (await db_session.execute(
        select(Contract).where(Contract.id == contract.id)
    )).scalar_one_or_none()
    assert still_there is not None
