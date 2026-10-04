"""Задача 04.10.2026 («Помесячные платежи — разные месяцы»): тесты для
app/services/payment_service_period.py::resolve_service_period.

Run: docker compose -p vsks_crm exec -T backend_a pytest tests/test_payment_service_period.py -q
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.models.payment import Payment
from app.models.purchase import Purchase
from app.services.payment_service_period import resolve_service_period, service_period_conflict_detail


def _payment_like(purpose_text: str = "", parsed_documents: dict | None = None):
    """Duck-typed ParsedRow/BankPayment stand-in (см. payment_basis.py docstring) —
    только атрибуты, которые читает extract_basis()."""
    return SimpleNamespace(purpose_text=purpose_text, parsed_documents=parsed_documents or {})


async def _make_monthly_purchase(db_session, months: int = 12, start: date = date(2026, 1, 1)):
    p = Purchase(
        item_name="Уборка помещений",
        status="delivered",
        is_monthly_payment=True,
        monthly_payment_count=months,
        monthly_payment_amount=Decimal("10000.00"),
        service_start_date=start,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _confirm_payment(db_session, purchase_id: int, service_period: date, doc_number: str = "ПП-1"):
    pay = Payment(
        purchase_id=purchase_id,
        amount=Decimal("10000.00"),
        matched_confirmed=True,
        payment_source="statement",
        confirmed_by_statement=True,
        document_number=doc_number,
        payment_date=service_period,
        service_period=service_period,
    )
    db_session.add(pay)
    await db_session.commit()
    await db_session.refresh(pay)
    return pay


async def test_three_payments_without_act_take_first_three_free_months(db_session, test_org):
    """Три одинаковых платежа без акта на 12-месячную закупку с 01.2026 →
    01, 02, 03 — каждый следующий занимает первый ещё свободный месяц."""
    purchase = await _make_monthly_purchase(db_session)
    bp = _payment_like()

    r1 = await resolve_service_period(db_session, purchase, bp)
    assert r1.period == date(2026, 1, 1)
    assert r1.conflict is None
    await _confirm_payment(db_session, purchase.id, r1.period, "ПП-1")

    r2 = await resolve_service_period(db_session, purchase, bp)
    assert r2.period == date(2026, 2, 1)
    await _confirm_payment(db_session, purchase.id, r2.period, "ПП-2")

    r3 = await resolve_service_period(db_session, purchase, bp)
    assert r3.period == date(2026, 3, 1)


async def test_payment_with_act_date_takes_act_month(db_session, test_org):
    """Платёж с актом от 15.06.2026 → месяц 06.2026, независимо от свободных ранних месяцев."""
    purchase = await _make_monthly_purchase(db_session)
    bp = _payment_like(parsed_documents={"acts": [{"number": "БН", "date": "15.06.2026"}]})

    result = await resolve_service_period(db_session, purchase, bp)
    assert result.period == date(2026, 6, 1)
    assert result.conflict is None


async def test_second_payment_with_same_act_month_conflicts(db_session, test_org):
    """Второй платёж с актом за тот же месяц/номер → конфликт, платёж не создаётся молча."""
    purchase = await _make_monthly_purchase(db_session)
    bp = _payment_like(parsed_documents={"acts": [{"number": "БН", "date": "15.06.2026"}]})

    first = await resolve_service_period(db_session, purchase, bp)
    assert first.period == date(2026, 6, 1)
    await _confirm_payment(db_session, purchase.id, first.period, "ПП-акт-июнь")

    second = await resolve_service_period(db_session, purchase, bp)
    assert second.period is None
    assert second.conflict is not None
    assert "06.2026" in second.conflict
    assert "ПП-акт-июнь" in second.conflict
    # Задача 04.10.2026 (детализация 409): «месяц уже занят» — единственный вид
    # конфликта, где известен КОНКРЕТНЫЙ занятый месяц (см. resolve_service_period).
    assert second.occupied_period == date(2026, 6, 1)


def test_service_period_conflict_detail_shape():
    """service_period_conflict_detail — единственное место, где собирается
    структурированный 409 detail (ПРАВИЛО №6); оба роутера (bank_statements_registry.py,
    purchase_payment_matching.py) и оба исключения (ServicePeriodConflict,
    ServicePeriodAttachConflict) вызывают именно его, не собирают dict на месте."""
    detail = service_period_conflict_detail(
        "Закупка №5: не удалось однозначно определить месяц оказания — месяц 06.2026 уже оплачен платежом №ПП-1 от 15.06.2026",
        purchase_id=5,
        occupied_period=date(2026, 6, 1),
    )
    assert detail == {
        "code": "service_period_conflict",
        "purchase_id": 5,
        "message": "Закупка №5: не удалось однозначно определить месяц оказания — месяц 06.2026 уже оплачен платежом №ПП-1 от 15.06.2026",
        "occupied_period": "2026-06-01",
    }


def test_service_period_conflict_detail_without_purchase_id():
    """Race-backstop (IntegrityError на flush, app/services/purchase_payments.py) не
    привязан к одной закупке/месяцу — purchase_id/occupied_period уходят null,
    а не выдумываются."""
    detail = service_period_conflict_detail("Платёж №42 конфликтует с уже существующей записью")
    assert detail["code"] == "service_period_conflict"
    assert detail["purchase_id"] is None
    assert detail["occupied_period"] is None


async def test_service_period_conflict_exception_carries_structured_fields(db_session, test_org):
    """app/services/purchase_payments.py::create_payments_from_bank бросает
    ServicePeriodConflict с purchase_id/occupied_period, когда конфликт привязан
    к одной закупке — роутер строит 409 detail через service_period_conflict_detail
    без повторного парсинга текста (см. useServicePeriodConflict.ts на фронте)."""
    from app.services.purchase_payments import ServicePeriodConflict, create_payments_from_bank
    from app.models.bank_statement import BankPayment

    purchase = await _make_monthly_purchase(db_session, months=1, start=date(2026, 6, 1))
    await _confirm_payment(db_session, purchase.id, date(2026, 6, 1), "ПП-июнь")

    bp = BankPayment(
        amount=Decimal("10000.00"),
        payment_date=date(2026, 6, 20),
        payment_number="ПП-2",
        status="EXECUTED",
        purpose_text="",
    )
    db_session.add(bp)
    await db_session.commit()
    await db_session.refresh(bp)

    try:
        await create_payments_from_bank(db_session, bp.id, [purchase.id])
        assert False, "ожидался ServicePeriodConflict — все месяцы закупки заняты"
    except ServicePeriodConflict as exc:
        assert exc.purchase_id == purchase.id
        assert exc.occupied_period is None  # «все месяцы заняты», не «конкретный месяц взят»
        detail = service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period)
        assert detail["code"] == "service_period_conflict"
        assert detail["purchase_id"] == purchase.id
        assert detail["occupied_period"] is None


async def test_non_monthly_purchase_returns_none(db_session, test_org):
    """Не помесячная закупка → service_period всегда None, без конфликта."""
    purchase = Purchase(
        item_name="Разовая поставка",
        status="delivered",
        is_monthly_payment=False,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    bp = _payment_like()
    result = await resolve_service_period(db_session, purchase, bp)
    assert result.period is None
    assert result.conflict is None


async def test_all_months_occupied_conflicts(db_session, test_org):
    """Все месяцы 2-месячной закупки заняты подтверждёнными платежами →
    конфликт «все месяцы периода оказания уже оплачены»."""
    purchase = await _make_monthly_purchase(db_session, months=2, start=date(2026, 5, 1))
    await _confirm_payment(db_session, purchase.id, date(2026, 5, 1), "ПП-май")
    await _confirm_payment(db_session, purchase.id, date(2026, 6, 1), "ПП-июнь")

    bp = _payment_like()
    result = await resolve_service_period(db_session, purchase, bp)
    assert result.period is None
    assert "уже оплачены" in result.conflict
