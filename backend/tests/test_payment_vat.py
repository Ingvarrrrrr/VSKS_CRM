"""Сверка НДС закупки с НДС из выгрузки платежей (владелец, 2026-09-26).

Покрывает:
- app/services/payment_vat.py::parse_payment_vat на реальных формах текста
  назначения платежа (в т.ч. настоящие строки из локальной БД).
- app/services/purchase_vat_check.py::check_purchase_vat — mismatch (uniform),
  unknown_purchase_vat (с suggested), payments_disagree, ok.
- POST /api/purchases/{id}/align-vat-to-payments — реально меняет НДС закупки.

Запускать ПО ОДНОМУ файлу (флейк "different loop", см. conftest.py).
"""
from decimal import Decimal

import pytest

from app.services.payment_vat import parse_payment_vat
from app.services.purchase_vat_check import check_purchase_vat, PaymentSource, _purchase_payment_sources


# ---------------------------------------------------------------------------
# parse_payment_vat — без БД
# ---------------------------------------------------------------------------

def test_parse_real_form_amount_only_zero():
    # Реальная строка локальной БД (bank_payments.id=450) — "НДС0.00" без ставки.
    r = parse_payment_vat(
        "оплата за инструмент, звуковое и музык оформление мероприятия) НДС0.00",
        Decimal("1000.00"),
    )
    assert r["kind"] == "no_vat"
    assert r["vat_amount"] == Decimal("0")
    assert r["rate"] == Decimal("0")


def test_parse_real_form_amount_only_nonzero():
    # amount 122 000, НДС 22 000 → ставка 22% (владелец, пример из задачи).
    r = parse_payment_vat("оплата по договору №1 НДС 22000.00", Decimal("122000"))
    assert r["kind"] == "rate"
    assert r["rate"] == Decimal("22")
    assert r["vat_amount"] == Decimal("22000.00")


def test_parse_real_form_amount_only_20_percent():
    # amount 120 000, НДС 20 000 → ставка 20%.
    r = parse_payment_vat("оплата по договору №2 НДС 20000.00", Decimal("120000"))
    assert r["kind"] == "rate"
    assert r["rate"] == Decimal("20")


def test_parse_percent_with_amount():
    r = parse_payment_vat("оплата по акту, в т.ч. НДС 20% - 1000.00", Decimal("6000"))
    assert r["kind"] == "rate"
    assert r["rate"] == Decimal("20")
    assert r["vat_amount"] == Decimal("1000.00")


def test_parse_percent_in_parens():
    r = parse_payment_vat("оплата НДС (22%) 1234.56 за услуги", Decimal("6789.56"))
    assert r["kind"] == "rate"
    assert r["rate"] == Decimal("22")
    assert r["vat_amount"] == Decimal("1234.56")


def test_parse_no_vat_phrase():
    r = parse_payment_vat("Без НДС оплата за канцтовары", Decimal("500"))
    assert r["kind"] == "no_vat"
    assert r["vat_amount"] == Decimal("0")


def test_parse_not_subject_to_vat_phrase():
    r = parse_payment_vat("аренда помещения, НДС не облагается", Decimal("5000"))
    assert r["kind"] == "no_vat"


def test_parse_unrecognized():
    r = parse_payment_vat("оплата по договору №3 без указания налога", Decimal("100"))
    assert r["kind"] == "unknown"
    assert r["rate"] is None


# ---------------------------------------------------------------------------
# check_purchase_vat — на объектах-заглушках (без БД, чтобы не тянуть fixtures
# ради формы полей Payment/Purchase, объём проверки — по объёму правки,
# см. Lessons feedback_scope_tests_to_change).
# ---------------------------------------------------------------------------

class _FakePayment:
    def __init__(self, id, purpose, amount, date=None, number=None):
        self.id = id
        self.payment_purpose = purpose
        self.amount = amount
        self.payment_date = date
        self.document_number = number


class _FakePurchase:
    def __init__(self, vat_mode="uniform", vat_applicable=None, vat_rate=None, items=None):
        self.vat_mode = vat_mode
        self.vat_applicable = vat_applicable
        self.vat_rate = vat_rate
        self.items = items or []


def test_check_uniform_mismatch():
    # Закупка помечена "без НДС", но платёж содержит НДС 20%.
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=False, vat_rate=None)
    payments = [_FakePayment(1, "оплата НДС 20000.00", Decimal("120000"))]
    result = check_purchase_vat(purchase, payments)
    assert result["status"] == "mismatch"
    assert result["suggested"] == {"vat_applicable": True, "vat_rate": 20}


def test_check_unknown_purchase_vat_with_suggestion():
    # Закупка из плана — ставка вообще не указана; платежи согласны на 22%.
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=None, vat_rate=None)
    payments = [
        _FakePayment(1, "оплата НДС 22000.00", Decimal("122000")),
        _FakePayment(2, "оплата НДС 11000.00", Decimal("61000")),
    ]
    result = check_purchase_vat(purchase, payments)
    assert result["status"] == "unknown_purchase_vat"
    assert result["suggested"] == {"vat_applicable": True, "vat_rate": 22}


def test_check_payments_disagree():
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=None, vat_rate=None)
    payments = [
        _FakePayment(1, "оплата НДС 20000.00", Decimal("120000")),   # 20%
        _FakePayment(2, "оплата НДС 22000.00", Decimal("122000")),   # 22%
    ]
    result = check_purchase_vat(purchase, payments)
    assert result["status"] == "payments_disagree"
    assert result["suggested"] is None


def test_check_ok_when_rate_matches():
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=True, vat_rate=20)
    payments = [_FakePayment(1, "оплата НДС 20000.00", Decimal("120000"))]
    result = check_purchase_vat(purchase, payments)
    assert result["status"] == "ok"
    assert result["suggested"] is None


def test_check_no_payments():
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=True, vat_rate=20)
    result = check_purchase_vat(purchase, [])
    assert result["status"] == "no_payments"


def test_check_uses_unconfirmed_bank_payment_matcher_suggestion():
    # Доработка 2026-09-26: на проде подтверждённых Payment почти нет, но
    # BankPayment.matched_purchase_id (предложение авто-матчера) уже указывает
    # на закупку — сверка обязана учитывать и такие платежи, помечая confirmed=False.
    purchase = _FakePurchase(vat_mode="uniform", vat_applicable=False, vat_rate=None)
    sources = [PaymentSource(id=1, number="17", date=None, amount=Decimal("120000"),
                              purpose_text="оплата НДС 20000.00", confirmed=False)]
    result = check_purchase_vat(purchase, sources)
    assert result["status"] == "mismatch"
    assert result["suggested"] == {"vat_applicable": True, "vat_rate": 20}
    assert result["payments"][0]["confirmed"] is False


# ---------------------------------------------------------------------------
# Эндпоинт align-vat-to-payments — реально меняет НДС закупки (с БД).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_align_vat_endpoint_updates_purchase(client, auth_headers, db_session, make_purchase):
    from app.models.payment import Payment

    purchase = await make_purchase(vat_mode="uniform", vat_applicable=False, vat_rate=None)
    payment = Payment(
        purchase_id=purchase.id,
        payment_purpose="оплата по договору НДС 20000.00",
        amount=Decimal("120000"),
        matched_confirmed=True,
        payment_source="statement",
    )
    db_session.add(payment)
    await db_session.commit()

    check_resp = await client.get(f"/api/purchases/{purchase.id}/vat-payment-check", headers=auth_headers)
    assert check_resp.status_code == 200
    body = check_resp.json()
    assert body["status"] == "mismatch"
    assert body["suggested"] == {"vat_applicable": True, "vat_rate": 20}

    align_resp = await client.post(
        f"/api/purchases/{purchase.id}/align-vat-to-payments",
        json=body["suggested"],
        headers=auth_headers,
    )
    assert align_resp.status_code == 200, align_resp.text
    out = align_resp.json()
    assert out["vat_mode"] == "uniform"
    assert out["vat_applicable"] is True
    assert out["vat_rate"] == 20

    await db_session.refresh(purchase)
    assert purchase.vat_applicable is True
    assert purchase.vat_rate == 20


# ---------------------------------------------------------------------------
# _purchase_payment_sources — два источника, без двойного счёта.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sources_include_unconfirmed_bank_payment_suggestion(db_session, make_purchase):
    from app.models.bank_statement import BankPayment

    purchase = await make_purchase()
    bp = BankPayment(
        matched_purchase_id=purchase.id,
        purpose_text="оплата НДС 20000.00",
        amount=Decimal("120000"),
        payment_number="55",
    )
    db_session.add(bp)
    await db_session.commit()

    sources = await _purchase_payment_sources(db_session, purchase.id)
    assert len(sources) == 1
    assert sources[0].confirmed is False
    assert sources[0].id == bp.id


@pytest.mark.asyncio
async def test_sources_no_double_count_when_bank_payment_confirmed(db_session, make_purchase):
    # BankPayment уже подтверждён (есть Payment.bank_payment_id на него) —
    # matched_purchase_id остаётся выставленным матчером, но его нельзя
    # считать ВТОРОЙ раз рядом с подтверждённым Payment.
    from app.models.bank_statement import BankPayment
    from app.models.payment import Payment

    purchase = await make_purchase()
    bp = BankPayment(
        matched_purchase_id=purchase.id,
        purpose_text="оплата НДС 20000.00",
        amount=Decimal("120000"),
        payment_number="55",
        matched_confirmed=True,
    )
    db_session.add(bp)
    await db_session.flush()

    payment = Payment(
        purchase_id=purchase.id,
        bank_payment_id=bp.id,
        payment_purpose="оплата НДС 20000.00",
        amount=Decimal("120000"),
        matched_confirmed=True,
        payment_source="statement",
    )
    db_session.add(payment)
    await db_session.commit()

    sources = await _purchase_payment_sources(db_session, purchase.id)
    assert len(sources) == 1
    assert sources[0].confirmed is True
    assert sources[0].id == payment.id
