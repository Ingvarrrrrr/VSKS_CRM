"""Аудит безопасности 20.10.2026: оплаты закупки одной организации не должны
быть доступны пользователю другой организации только потому, что у него есть
право payment.register/payment.confirm (эффективный ключ проверялся в ЛЮБОЙ
своей орге, без проверки принадлежности самой закупки/BankPayment).

Покрывает: DELETE/POST /api/payments/ и POST /api/payments/registry/{id}/confirm
— все они теперь зовут app.services.payment_object_access.ensure_purchase_payment_access
(ПРАВИЛО №6, единый гейт — см. app/auth/object_visibility.py::ensure_purchase_visible
+ app/auth/permissions.py::has_org_key)."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.auth.jwt import create_access_token
from app.models.bank_statement import BankPayment
from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.subsidy import Subsidy
from sqlalchemy import select


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _make_org(db_session) -> Organization:
    contractor = Contractor(name=f"Org-{_uid()}")
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _make_subsidy(db_session, org_id: int) -> Subsidy:
    s = Subsidy(name=f"Субсидия-{_uid()}", year=2026, org_id=org_id)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_purchase(db_session, subsidy_id: int) -> Purchase:
    p = Purchase(
        item_name=f"Закупка-{_uid()}", item_type="goods",
        subsidy_id=subsidy_id, status="paid",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _headers(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_delete_payment_other_org_purchase_is_404(client, db_session, make_user):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    sub_b = await _make_subsidy(db_session, org_b.id)
    purchase_b = await _make_purchase(db_session, sub_b.id)

    pay_b = Payment(purchase_id=purchase_b.id, amount=Decimal("1000.00"),
                     payment_source="manual", confirmed_by_statement=False)
    db_session.add(pay_b)
    await db_session.commit()
    await db_session.refresh(pay_b)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.delete(f"/api/payments/{pay_b.id}", headers=_headers(user_a))
    assert resp.status_code == 404, resp.text

    # Платёж чужой организации остался на месте.
    still = await db_session.get(Payment, pay_b.id)
    assert still is not None


@pytest.mark.asyncio
async def test_create_payment_other_org_purchase_is_404(client, db_session, make_user):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    sub_b = await _make_subsidy(db_session, org_b.id)
    purchase_b = await _make_purchase(db_session, sub_b.id)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.post(
        "/api/payments/",
        json={"purchase_id": purchase_b.id, "amount": "500.00",
              "payment_date": "2026-10-20"},
        headers=_headers(user_a),
    )
    assert resp.status_code == 404, resp.text

    count = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase_b.id)
    )).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_delete_payment_confirmed_by_statement_is_409(client, db_session, make_user):
    org_a = await _make_org(db_session)
    sub_a = await _make_subsidy(db_session, org_a.id)
    purchase_a = await _make_purchase(db_session, sub_a.id)

    pay_a = Payment(purchase_id=purchase_a.id, amount=Decimal("1000.00"),
                     payment_source="statement", confirmed_by_statement=True)
    db_session.add(pay_a)
    await db_session.commit()
    await db_session.refresh(pay_a)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.delete(f"/api/payments/{pay_a.id}", headers=_headers(user_a))
    assert resp.status_code == 409, resp.text

    still = await db_session.get(Payment, pay_a.id)
    assert still is not None


@pytest.mark.asyncio
async def test_delete_own_purchase_payment_succeeds_and_logs_event(client, db_session, make_user):
    org_a = await _make_org(db_session)
    sub_a = await _make_subsidy(db_session, org_a.id)
    purchase_a = await _make_purchase(db_session, sub_a.id)

    pay_a = Payment(purchase_id=purchase_a.id, amount=Decimal("777.00"),
                     payment_source="manual", confirmed_by_statement=False,
                     payment_date=date(2026, 10, 1))
    db_session.add(pay_a)
    await db_session.commit()
    await db_session.refresh(pay_a)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.delete(f"/api/payments/{pay_a.id}", headers=_headers(user_a))
    assert resp.status_code == 200, resp.text

    assert await db_session.get(Payment, pay_a.id) is None

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == purchase_a.id,
            PurchaseEvent.event_type == "payment_deleted",
        )
    )).scalars().all()
    assert len(events) == 1
    assert events[0].data["payment_id"] == pay_a.id


@pytest.mark.asyncio
async def test_create_own_purchase_payment_succeeds(client, db_session, make_user):
    org_a = await _make_org(db_session)
    sub_a = await _make_subsidy(db_session, org_a.id)
    purchase_a = await _make_purchase(db_session, sub_a.id)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.post(
        "/api/payments/",
        json={"purchase_id": purchase_a.id, "amount": "321.00",
              "payment_date": "2026-10-20"},
        headers=_headers(user_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchase_id"] == purchase_a.id


@pytest.mark.asyncio
async def test_confirm_bank_payment_with_other_org_purchase_is_rejected(client, db_session, make_user):
    org_a = await _make_org(db_session)
    org_b = await _make_org(db_session)
    sub_a = await _make_subsidy(db_session, org_a.id)
    sub_b = await _make_subsidy(db_session, org_b.id)
    purchase_b = await _make_purchase(db_session, sub_b.id)

    contract_a = Contract(number=f"Д-{_uid()}", contract_type="single", subsidy_id=sub_a.id, status="active")
    db_session.add(contract_a)
    await db_session.commit()
    await db_session.refresh(contract_a)

    bp = BankPayment(
        payment_number=f"ПП-{_uid()}", amount=Decimal("1000.00"), status="ИСПОЛНЕН",
        payment_date=date(2026, 5, 1), org_id=org_a.id, matched_contract_id=contract_a.id,
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    user_a = await make_user(role="account_owner", org_id=org_a.id)

    resp = await client.post(
        f"/api/payments/registry/{bp.id}/confirm",
        json={"purchase_ids": [purchase_b.id]},
        headers=_headers(user_a),
    )
    assert resp.status_code in (404, 422), resp.text
    assert bp.matched_confirmed is False

    assert (await db_session.execute(
        select(Payment).where(Payment.bank_payment_id == bp.id)
    )).scalars().all() == []
