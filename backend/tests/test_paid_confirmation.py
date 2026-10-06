"""План 2026-10-04-fadm-statement (backend п.1-3):

1. bank_payment_subsidy_scope.py — строка выписки видна субсидии по номеру
   соглашения, не только по subsidy_id.
2. Занятость строки выписки — внутри субсидии, не глобально: вторая субсидия
   с тем же номером соглашения может опереться на ту же строку.
3. recompute_purchase_payments заводит pending PurchasePaidConfirmation вместо
   молчаливого paid; confirm/reject — app/routers/purchase_paid_confirmations.py.
"""
import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.bank_statement import BankPayment, BankStatementImport
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.services.bank_payment_subsidy_scope import (
    bank_payment_matches_subsidy,
    subsidy_scope_clause,
)
from app.models.purchase_paid_confirmation_rejection import PurchasePaidConfirmationRejection
from app.services.payment_lookup import attach, find_candidates
from app.services.payment_target import PaymentGroup
from app.services.purchase_payments import recompute_purchase_payments


def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def contractor(db_session):
    c = Contractor(name=f"ТестКонтрагент-{_uid()}", inn=f"77{uuid.uuid4().int % 10**8:08d}")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _make_subsidy(db_session, org_id=None, agreement_number=None):
    s = Subsidy(
        name=f"ФАДМ-{_uid()}", year=2026, require_planned_dates=False,
        org_id=org_id, agreement_number=agreement_number,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_user(db_session, org_id, role="employee"):
    from app.models.user import User
    from app.auth.jwt import hash_password, create_access_token
    username = f"u_{_uid()}"
    user = User(
        username=username, password_hash=hash_password("testpass123"),
        role=role, org_id=org_id, full_name=f"Тест {username}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username, 'org_id': user.org_id})}"}
    return user, headers


# ---------------------------------------------------------------------------
# Test 1 — строка выписки видна ДВУМ субсидиям с общим номером соглашения
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bank_payment_visible_to_two_subsidies_by_agreement(db_session, test_org):
    """Номер соглашения совпадает (с разницей в пробелах/регистре/символе №) —
    строка видна ОБЕИМ субсидиям, хотя bp.subsidy_id у неё пуст (как у ФАДМ_2026,
    где номер соглашения был не заполнен на момент импорта выписки)."""
    sub1 = await _make_subsidy(db_session, test_org.id, agreement_number="091-10-2026-008")
    sub2 = await _make_subsidy(db_session, test_org.id, agreement_number="  № 091-10-2026-008 ")

    bp = BankPayment(
        payment_number=f"ПП-{_uid()}",
        payee_inn="7700000001",
        amount=Decimal("5000.00"),
        status="ИСПОЛНЕН",
        purpose_text="Оплата по Соглашению № 091-10-2026-008 от 28.01.2026 за товар",
        subsidy_id=None,
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    assert bank_payment_matches_subsidy(bp, sub1) is True
    assert bank_payment_matches_subsidy(bp, sub2) is True

    # Сторонняя субсидия с ДРУГИМ номером соглашения строку не видит.
    sub3 = await _make_subsidy(db_session, test_org.id, agreement_number="000-00-0000-000")
    assert bank_payment_matches_subsidy(bp, sub3) is False

    # SQL-эквивалент (subsidy_scope_clause) даёт тот же результат на реальном запросе.
    rows1 = (await db_session.execute(
        select(BankPayment.id).where(subsidy_scope_clause(sub1))
    )).scalars().all()
    rows3 = (await db_session.execute(
        select(BankPayment.id).where(subsidy_scope_clause(sub3))
    )).scalars().all()
    assert bp.id in rows1
    assert bp.id not in rows3


# ---------------------------------------------------------------------------
# Test 2 — вторая субсидия (тот же номер соглашения) может опереться на ТУ ЖЕ
# строку выписки — занятость считается внутри субсидии, не глобально
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_subsidy_can_reuse_same_statement_line(db_session, test_org, contractor):
    sub1 = await _make_subsidy(db_session, test_org.id, agreement_number="091-10-2026-008")
    sub2 = await _make_subsidy(db_session, test_org.id, agreement_number="091-10-2026-008")

    p1 = Purchase(item_name="Товар-1", status="delivered", subsidy_id=sub1.id, contractor_id=contractor.id)
    p2 = Purchase(item_name="Товар-2", status="delivered", subsidy_id=sub2.id, contractor_id=contractor.id)
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    bp = BankPayment(
        payment_number=f"ПП-{_uid()}",
        payee_inn=contractor.inn,
        amount=Decimal("5000.00"),
        status="ИСПОЛНЕН",
        purpose_text="Соглашение 091-10-2026-008 от 28.01.2026",
        subsidy_id=None,
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    group1 = PaymentGroup(
        group_key="g1", subsidy_id=sub1.id, registry_number="REG-1", contract_number=None,
        is_framework=False, contractor_id=contractor.id, contractor_inn=contractor.inn,
        contractor_name=contractor.name, goods_amount=Decimal("5000.00"),
        services_amount=Decimal("0"), unspecified_amount=Decimal("0"), purchase_ids=[p1.id],
    )
    group2 = PaymentGroup(
        group_key="g2", subsidy_id=sub2.id, registry_number="REG-2", contract_number=None,
        is_framework=False, contractor_id=contractor.id, contractor_inn=contractor.inn,
        contractor_name=contractor.name, goods_amount=Decimal("5000.00"),
        services_amount=Decimal("0"), unspecified_amount=Decimal("0"), purchase_ids=[p2.id],
    )

    # Строка видна (и свободна) ОБЕИМ субсидиям до какого-либо разнесения.
    cands1 = await find_candidates(db_session, group1)
    cands2 = await find_candidates(db_session, group2)
    assert any(c.bank_payment_id == bp.id and c.auto for c in cands1["goods"])
    assert any(c.bank_payment_id == bp.id and c.auto for c in cands2["goods"])

    # Субсидия 1 разносит платёж на свою закупку.
    created1 = await attach(db_session, group1, [bp.id])
    await db_session.commit()
    assert len(created1) == 1
    assert created1[0].purchase_id == p1.id

    # Субсидия 2 — та же строка ВСЁ ЕЩЁ свободна (занятость внутри субсидии 1,
    # не глобальна) — план 2026-10-04-fadm-statement, п.2.
    cands2_after = await find_candidates(db_session, group2)
    assert any(c.bank_payment_id == bp.id and c.free for c in cands2_after["goods"])

    created2 = await attach(db_session, group2, [bp.id])
    await db_session.commit()
    assert len(created2) == 1
    assert created2[0].purchase_id == p2.id

    # Обе Payment-записи существуют одновременно на одну и ту же строку выписки.
    payments = (await db_session.execute(
        select(Payment).where(Payment.bank_payment_id == bp.id)
    )).scalars().all()
    assert {pay.purchase_id for pay in payments} == {p1.id, p2.id}


# ---------------------------------------------------------------------------
# Test 3 — recompute заводит pending-запрос, НЕ меняет статус закупки
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_creates_pending_confirmation_not_silent_paid(db_session, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-777", payment_date=__import__("datetime").date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, p.id)
    assert updated.status == "delivered"

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()
    assert conf.status == "pending"
    assert conf.subsidy_id == sub.id
    assert conf.amount_confirmed == Decimal("10000.00")


# ---------------------------------------------------------------------------
# Test 3b — владелец: «молчаливого перевода в Оплачено не должно быть НИГДЕ» —
# закупка БЕЗ субсидии (некого просить подтвердить) НЕ получает ни
# автоматический paid, ни запрос; статус меняет только человек вручную.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_without_subsidy_does_not_touch_status(db_session, contractor):
    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=None,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    pay = Payment(
        purchase_id=p.id, document_number="ПП-666", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, p.id)
    assert updated.status == "delivered"  # не меняется НИКАК — ни paid, ни pending

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one_or_none()
    assert conf is None


@pytest.mark.asyncio
async def test_recompute_without_subsidy_not_delivered_does_not_auto_pay(db_session, contractor):
    """Без субсидии прежнее поведение тоже прежнее: только 'delivered' молча
    закрывается — 'contracted'/'ordered' без субсидии остаются как есть
    (это и было правило до плана 2026-10-04-fadm-statement)."""
    p = Purchase(
        item_name="Товар", status="contracted", subsidy_id=None,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    pay = Payment(
        purchase_id=p.id, document_number="ПП-667", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    updated = await recompute_purchase_payments(db_session, p.id)
    assert updated.status == "contracted"

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one_or_none()
    assert conf is None


# ---------------------------------------------------------------------------
# Test 4 — confirm → paid (штатный переход) + событие в истории закупки
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_transitions_to_paid_and_logs_event(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    pay = Payment(
        purchase_id=p.id, document_number="ПП-888", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()
    assert conf.status == "pending"

    resp = await client.post(
        f"/api/paid-confirmations/{conf.id}/confirm", headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(p)
    assert p.status == "paid"

    await db_session.refresh(conf)
    assert conf.status == "confirmed"
    assert conf.decided_by == approver_user.id

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id, PurchaseEvent.event_type == "status_changed",
        )
    )).scalars().all()
    assert any(e.data.get("to") == "paid" for e in events)


# ---------------------------------------------------------------------------
# Test 4b — доработка приёмки 04.10: закупка на 'contracted' (не 'delivered')
# тоже заводит запрос и, при confirm, проходит ПОШАГОВО contracted→ordered→
# delivered→paid тем же штатным механизмом (два+ события в истории)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contracted_purchase_pending_then_confirm_walks_to_paid(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    import datetime
    p = Purchase(
        item_name="Товар", status="contracted", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
        # Закрывающие документы уже загружены заранее — иначе шаг 'delivered'
        # заблокирует переход (см. test_confirm_blocked_without_acceptance_docs).
        acceptance_doc_name="Акт приёмки", acceptance_doc_number="1",
        acceptance_doc_date=datetime.date(2026, 5, 2), acceptance_doc_amount=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-321", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    # Было бы молчаливо проигнорировано ДО доработки (гейт был === 'delivered').
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()
    assert conf.status == "pending"
    assert conf.subsidy_id == sub.id

    resp = await client.post(f"/api/paid-confirmations/{conf.id}/confirm", headers=approver_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchase"]["status"] == "paid"
    assert body["purchase"]["status_label"] == "Оплачено"

    await db_session.refresh(p)
    assert p.status == "paid"

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id, PurchaseEvent.event_type == "status_changed",
        ).order_by(PurchaseEvent.id)
    )).scalars().all()
    tos = [e.data.get("to") for e in events]
    assert tos == ["ordered", "delivered", "paid"]
    delivered_event = next(e for e in events if e.data.get("to") == "delivered")
    assert delivered_event.data.get("note") == "Поставлено (по подтверждению оплаты)"
    paid_event = next(e for e in events if e.data.get("to") == "paid")
    assert paid_event.data.get("note") is None


# ---------------------------------------------------------------------------
# Test 4c — confirm блокируется гейтом (нет закрывающих документов для
# delivered) → 409 с понятной причиной, запрос остаётся pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_blocked_without_acceptance_docs(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    import datetime
    p = Purchase(
        item_name="Товар", status="contracted", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
        # Закрывающих документов НЕТ — шаг 'delivered' обязан заблокировать переход.
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-322", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()

    status_before = p.status  # 'contracted'

    # Доработка «confirm атомарен»: цепочка contracted→ordered проходит без
    # проблем (нет обязательных полей для 'ordered'), только следующий шаг
    # (→delivered) упирается в отсутствие закрывающих документов — это НЕ
    # должно оставить закупку зависшей в 'ordered': откатывается ВСЁ разом.
    resp = await client.post(f"/api/paid-confirmations/{conf.id}/confirm", headers=approver_headers)
    assert resp.status_code == 409, resp.text

    await db_session.refresh(conf)
    assert conf.status == "pending"

    await db_session.refresh(p)
    assert p.status == status_before  # статус ДО == статус ПОСЛЕ — откат целиком, не завис на 'ordered'

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id, PurchaseEvent.event_type == "status_changed",
        )
    )).scalars().all()
    assert events == []  # ни одного «успешного» шага не осталось закоммиченным

    # Заранее видно (GET), что confirm упрётся — без записи.
    get_resp = await client.get(f"/api/purchases/{p.id}/paid-confirmation", headers=approver_headers)
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["status"] == "pending"
    assert body["blocked_reason"] is not None
    assert "Поставлено" in body["blocked_reason"]

    await db_session.refresh(p)
    assert p.status == status_before  # GET с blocked_reason тоже не должен ничего менять


# ---------------------------------------------------------------------------
# Test 5 — reject → платежи отвязаны, статус закупки не меняется
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_unlinks_payments_and_keeps_status(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    bp = BankPayment(
        payment_number="ПП-999", payee_inn=contractor.inn, amount=Decimal("10000.00"),
        status="ИСПОЛНЕН",
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-999", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True, bank_payment_id=bp.id,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    bp.matched_confirmed = True
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()

    resp = await client.post(
        f"/api/paid-confirmations/{conf.id}/reject",
        json={"comment": "Это оплата другой закупки"},
        headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(p)
    assert p.status == "delivered"

    await db_session.refresh(conf)
    assert conf.status == "rejected"
    assert conf.comment == "Это оплата другой закупки"

    remaining = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == p.id)
    )).scalars().all()
    assert remaining == []

    await db_session.refresh(bp)
    assert bp.matched_confirmed is False

    rejection = (await db_session.execute(
        select(PurchasePaidConfirmationRejection).where(
            PurchasePaidConfirmationRejection.purchase_id == p.id,
            PurchasePaidConfirmationRejection.bank_payment_id == bp.id,
        )
    )).scalar_one()
    assert rejection.confirmation_id == conf.id


# ---------------------------------------------------------------------------
# Test 5b — доработка: после reject та же пара не возвращается auto, но
# ручная привязка (attach-payments явным выбором) по-прежнему разрешена, с
# предупреждением
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rejected_pair_not_reselected_auto_but_manual_attach_allowed(
    db_session, client, test_org, contractor,
):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    bp = BankPayment(
        payment_number="ПП-555", payee_inn=contractor.inn, amount=Decimal("10000.00"),
        status="ИСПОЛНЕН", subsidy_id=sub.id,
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-555", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True, bank_payment_id=bp.id,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    bp.matched_confirmed = True
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()
    resp = await client.post(
        f"/api/paid-confirmations/{conf.id}/reject",
        json={"comment": "Не та оплата"},
        headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text

    # Платёж отвязан — строка выписки формально снова свободна по сумме/ИНН,
    # но find_candidates НЕ должен предложить её авто (пара запомнена отклонённой).
    group = PaymentGroup(
        group_key="g", subsidy_id=sub.id, registry_number="REG", contract_number=None,
        is_framework=False, contractor_id=contractor.id, contractor_inn=contractor.inn,
        contractor_name=contractor.name, goods_amount=Decimal("10000.00"),
        services_amount=Decimal("0"), unspecified_amount=Decimal("0"), purchase_ids=[p.id],
    )
    cands = await find_candidates(db_session, group)
    goods_cands = cands["goods"]
    assert any(c.bank_payment_id == bp.id for c in goods_cands)
    cand = next(c for c in goods_cands if c.bank_payment_id == bp.id)
    assert cand.auto is False
    assert cand.previously_rejected is True
    assert "отклоняли" in (cand.reason or "")

    # Ручная привязка (attach-payments, явный выбор) по-прежнему разрешена —
    # создаёт платёж, но дописывает предупреждение.
    warnings: list[str] = []
    created = await attach(db_session, group, [bp.id], warnings_out=warnings)
    await db_session.commit()
    assert len(created) == 1
    assert created[0].purchase_id == p.id
    assert any("отклоняли" in w for w in warnings)


# ---------------------------------------------------------------------------
# Test 6 — чужой пользователь (не согласующий субсидии) → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_forbidden_for_non_approver(db_session, client, test_org, contractor, test_user, auth_headers):
    sub = await _make_subsidy(db_session, test_org.id)
    # test_user существует (fixture), но НЕ входит в SubsidyApprover этой субсидии.
    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    conf = PurchasePaidConfirmation(purchase_id=p.id, subsidy_id=sub.id, amount_confirmed=Decimal("10000.00"))
    db_session.add(conf)
    await db_session.commit()
    await db_session.refresh(conf)

    resp = await client.post(f"/api/paid-confirmations/{conf.id}/confirm", headers=auth_headers)
    assert resp.status_code == 403, resp.text

    await db_session.refresh(p)
    assert p.status == "delivered"
    await db_session.refresh(conf)
    assert conf.status == "pending"


# ---------------------------------------------------------------------------
# Test 7 — владелец: оплата из выписки — факт, НЕ блокируется превышением
# плана по категории ФЭО («ТЗ/договор над плановой позицией») — confirm
# проходит, plan_excess_warning заполнен (русский денежный формат), событие
# «Оплачено» несёт пометку о несогласованном превышении.
# ---------------------------------------------------------------------------

async def _make_tz_over_plan_purchase(db_session, sub, contractor, *, planned_amount, item_total):
    """Закупка с ОДНОЙ позицией, чья сумма (item_total) выше её плановой
    позиции (planned_amount) — ровно сценарий, которым assert_no_pending_tz_excess
    блокирует дальнейшее движение (см. test_tz_over_plan_goes_to_approval.py)."""
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase_item import PurchaseItem
    import datetime

    cat = FeoCategory(
        subsidy_id=sub.id, parent_id=None, level=1,
        name=f"Категория-{_uid()}", budget=Decimal("10000000"),
    )
    db_session.add(cat)
    await db_session.flush()

    fpi = FeoPlannedItem(
        feo_category_id=cat.id, name="Плановая позиция", quantity=Decimal("1"),
        unit="усл", amount=planned_amount, is_active=True,
    )
    db_session.add(fpi)
    await db_session.flush()

    p = Purchase(
        item_name="Логистические услуги", status="contracted", subsidy_id=sub.id,
        feo_category_id=cat.id, contractor_id=contractor.id, contract_price=item_total,
        acceptance_doc_name="Акт приёмки", acceptance_doc_number="1",
        acceptance_doc_date=datetime.date(2026, 5, 2), acceptance_doc_amount=item_total,
    )
    db_session.add(p)
    await db_session.flush()

    item = PurchaseItem(
        purchase_id=p.id, item_name="Логистические услуги", quantity=Decimal("1"),
        unit="усл", unit_price=item_total, total_price=item_total,
        feo_category_id=cat.id, feo_planned_item_id=fpi.id, over_plan=False,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_confirm_not_blocked_by_plan_excess_and_warning_filled(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    item_total = Decimal("20000.00")
    p = await _make_tz_over_plan_purchase(
        db_session, sub, contractor, planned_amount=Decimal("10000.00"), item_total=item_total,
    )

    import datetime
    pay = Payment(
        purchase_id=p.id, document_number="ПП-900", payment_date=datetime.date(2026, 5, 1),
        amount=item_total, matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()
    assert conf.status == "pending"

    # GET заранее показывает предупреждение, НЕ блокировку.
    get_resp = await client.get(f"/api/purchases/{p.id}/paid-confirmation", headers=approver_headers)
    assert get_resp.status_code == 200, get_resp.text
    preview = get_resp.json()
    assert preview["blocked_reason"] is None
    assert preview["plan_excess_warning"] is not None
    assert "10 000,00 ₽" in preview["plan_excess_warning"]  # русский формат, не 10,000.00

    resp = await client.post(f"/api/paid-confirmations/{conf.id}/confirm", headers=approver_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchase"]["status"] == "paid"
    assert body["plan_excess_warning"] is not None
    assert "10 000,00 ₽" in body["plan_excess_warning"]
    assert "20 000,00 ₽" in body["plan_excess_warning"]

    await db_session.refresh(p)
    assert p.status == "paid"

    events = (await db_session.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id == p.id, PurchaseEvent.event_type == "status_changed",
        )
    )).scalars().all()
    paid_event = next(e for e in events if e.data.get("to") == "paid")
    assert paid_event.data.get("note") == "Оплачено по выписке при несогласованном превышении плана"


# ---------------------------------------------------------------------------
# Test 8 — обычный ручной переход при том же превышении остаётся 409
# (превышение плана обходит только confirm, не ручные переходы)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_transition_still_blocked_by_plan_excess(db_session, client, test_org, contractor):
    manager_user, manager_headers = await _make_user(db_session, test_org.id, role="manager")

    sub = await _make_subsidy(db_session, test_org.id)
    item_total = Decimal("20000.00")
    p = await _make_tz_over_plan_purchase(
        db_session, sub, contractor, planned_amount=Decimal("10000.00"), item_total=item_total,
    )

    resp = await client.post(
        f"/api/purchases/{p.id}/transition", params={"status": "delivered"}, headers=manager_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "ТЗ" in resp.text

    await db_session.refresh(p)
    assert p.status == "contracted"


# ---------------------------------------------------------------------------
# Test 9 — QA (05.10.2026): уведомление о запросе «Оплачено» откладывается до
# реального коммита вызывающей транзакции (app/services/notify_after_commit.py).
# Откат ДО коммита — уведомление не уходит; коммит — уходит ровно один раз.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paid_confirmation_notify_deferred_until_commit(db_session, test_org, contractor, monkeypatch):
    calls: list[tuple] = []

    async def _fake_notify(purchase, user, confirmation):
        calls.append((purchase.id, user.id, confirmation.id))

    monkeypatch.setattr(
        "app.notifications.notify_purchase_paid_confirmation_requested", _fake_notify,
    )

    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, _ = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    p = Purchase(
        item_name="Товар", status="delivered", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    import datetime
    pay = Payment(
        purchase_id=p.id, document_number="ПП-RB1", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()

    # id — простым int'ом, а не через p.* ПОСЛЕ rollback ниже: rollback истекает
    # (expire) ORM-объекты сессии целиком, обращение к p.id после него (даже
    # просто чтобы построить WHERE) падает MissingGreenlet в asyncio-режиме
    # (тот же нюанс, что уже встречался в _simulate_confirm_chain).
    pid = p.id
    approver_id = approver_user.id

    # --- Фаза 1: recompute создаёт запрос и ставит уведомление в очередь, но
    # вызывающий код откатывает ДО коммита — уведомление НЕ должно уйти.
    await recompute_purchase_payments(db_session, pid)
    await asyncio.sleep(0)  # дать бы шанс фоновой задаче, если бы она уже была создана
    assert calls == []

    await db_session.rollback()
    await asyncio.sleep(0)
    assert calls == []  # и после отката — тоже ничего не ушло

    conf_after_rollback = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == pid)
    )).scalar_one_or_none()
    assert conf_after_rollback is None  # запись отката тоже не пережила

    # --- Фаза 2: тот же сценарий, но теперь вызывающий код коммитит —
    # уведомление должно уйти РОВНО один раз.
    await recompute_purchase_payments(db_session, pid)
    await db_session.commit()
    await asyncio.sleep(0)  # дать фоновой asyncio.create_task отработать

    assert len(calls) == 1
    assert calls[0][0] == pid
    assert calls[0][1] == approver_id

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == pid)
    )).scalar_one()
    assert conf.status == "pending"


# ---------------------------------------------------------------------------
# Перф-доработка 2026-10-06: список по субсидии не симулирует переход,
# симуляция вынесена в отдельный POST .../paid-confirmations/check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_does_not_simulate_confirm_chain(db_session, client, test_org, contractor, monkeypatch):
    """Список pending по субсидии раньше гонял _simulate_confirm_chain на
    КАЖДУЮ строку (причина 40-60+ с на ~120 строках в проде) — теперь не
    должен вызывать её вообще, строки отдаются checked=false без
    blocked_reason."""
    import app.routers.purchase_paid_confirmations as ppc_module

    calls = {"n": 0}
    original = ppc_module._simulate_confirm_chain

    async def _counting(*args, **kwargs):
        calls["n"] += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(ppc_module, "_simulate_confirm_chain", _counting)

    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    # Без закрывающих документов — confirm/симуляция упёрлась бы в 'delivered'
    # (как в test_confirm_blocked_without_acceptance_docs), ровно поэтому
    # хороший кандидат убедиться, что список её вообще не запускает.
    import datetime
    p = Purchase(
        item_name="Товар", status="contracted", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-LST1", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    resp = await client.get(f"/api/subsidies/{sub.id}/paid-confirmations?status=pending", headers=approver_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    row = body["items"][0]
    assert row["checked"] is False
    assert row["blocked_reason"] is None
    assert calls["n"] == 0  # список НЕ вызвал симуляцию ни разу


@pytest.mark.asyncio
async def test_check_endpoint_returns_same_blocked_reason_as_old_list(db_session, client, test_org, contractor):
    """/check на pending-строке без закрывающих документов обязан отдать тот
    же blocked_reason, что раньше (до перф-доработки) отдавал список —
    см. test_confirm_blocked_without_acceptance_docs."""
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    import datetime
    p = Purchase(
        item_name="Товар", status="contracted", subsidy_id=sub.id,
        contractor_id=contractor.id, contract_price=Decimal("10000.00"),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pay = Payment(
        purchase_id=p.id, document_number="ПП-CHK1", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("10000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p.id)
    await db_session.commit()

    conf = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p.id)
    )).scalar_one()

    resp = await client.post(
        f"/api/subsidies/{sub.id}/paid-confirmations/check",
        json={"ids": [conf.id]}, headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == conf.id
    assert items[0]["blocked_reason"] is not None
    assert "Поставлено" in items[0]["blocked_reason"]

    # /check — чисто «сухой» прогон, статус закупки не должен поменяться.
    await db_session.refresh(p)
    assert p.status == "contracted"


@pytest.mark.asyncio
async def test_check_endpoint_limit_422(db_session, client, test_org, contractor):
    sub = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    resp = await client.post(
        f"/api/subsidies/{sub.id}/paid-confirmations/check",
        json={"ids": list(range(1, 22))}, headers=approver_headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_check_endpoint_ignores_other_subsidy_ids(db_session, client, test_org, contractor):
    """Строка подтверждения, принадлежащая ДРУГОЙ субсидии, переданная в
    ids — молча пропускается (не 403/404), ответ просто не содержит её."""
    sub_a = await _make_subsidy(db_session, test_org.id)
    sub_b = await _make_subsidy(db_session, test_org.id)
    approver_user, approver_headers = await _make_user(db_session, test_org.id)
    db_session.add(SubsidyApprover(
        subsidy_id=sub_a.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    db_session.add(SubsidyApprover(
        subsidy_id=sub_b.id, role_name="Директор", full_name=approver_user.full_name,
        user_id=approver_user.id,
    ))
    await db_session.commit()

    import datetime
    p_b = Purchase(
        item_name="Товар Б", status="delivered", subsidy_id=sub_b.id,
        contractor_id=contractor.id, contract_price=Decimal("5000.00"),
    )
    db_session.add(p_b)
    await db_session.commit()
    await db_session.refresh(p_b)

    pay = Payment(
        purchase_id=p_b.id, document_number="ПП-OTH1", payment_date=datetime.date(2026, 5, 1),
        amount=Decimal("5000.00"), matched_confirmed=True,
        payment_source="statement", confirmed_by_statement=True,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, p_b.id)
    await db_session.commit()

    conf_b = (await db_session.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id == p_b.id)
    )).scalar_one()

    # Запрашиваем проверку conf_b (субсидия B), но через эндпоинт субсидии A —
    # согласующий A не должен получить данные по чужой субсидии.
    resp = await client.post(
        f"/api/subsidies/{sub_a.id}/paid-confirmations/check",
        json={"ids": [conf_b.id, 999999]}, headers=approver_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
