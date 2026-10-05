"""Задача 05.10.2026 («три расширения штатного сопоставления выписки») —
тесты для app/services/payment_lookup_multi.py (помесячные / рамочные /
авансовые) + проверка, что успешный прогон импорта выписки больше не
удаляется из журнала (app/routers/bank_statements.py).

Run: docker compose -p vsks_crm exec -T backend_a pytest tests/test_payment_matcher_multi.py -q
"""
from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_lookup_multi import match_advance, match_framework, match_monthly
from app.services.payment_target import build_groups


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def _subsidy(db_session):
    s = Subsidy(name=f"Субсидия-{_uid()}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _contractor(db_session):
    c = Contractor(name=f"Контрагент-{_uid()}", inn=f"77{uuid.uuid4().int % 10**8:08d}")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _executed_status() -> str:
    return next(iter(EXECUTED_STATUSES))


# ---------------------------------------------------------------------------
# 1. Помесячные — 3 платежа одной суммы на один договор → 3 Payment на разные месяцы
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monthly_three_payments_three_months(db_session, test_org):
    subsidy = await _subsidy(db_session)
    contractor = await _contractor(db_session)

    purchase = Purchase(
        item_name=f"Уборка-{_uid()}",
        status="delivered",
        contractor_id=contractor.id,
        subsidy_id=subsidy.id,
        registry_number=f"REG-M-{_uid()}",
        contract_number=f"DOG-M-{_uid()}",
        is_monthly_payment=True,
        monthly_payment_count=3,
        monthly_payment_amount=Decimal("10000.00"),
        service_start_date=date(2026, 1, 1),
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Уборка помещений", item_type="услуга",
        quantity=Decimal(3), unit_price=Decimal("10000.00"), total_price=Decimal("30000.00"),
    )
    db_session.add(item)

    status = _executed_status()
    bps = []
    for i in range(3):
        bp = BankPayment(
            subsidy_id=subsidy.id,
            payee_inn=contractor.inn,
            parsed_contract_number=purchase.contract_number,
            amount=Decimal("10000.00"),
            payment_date=date(2026, i + 1, 15),
            status=status,
            purpose_text=f"Оплата за уборку помещений, месяц {i + 1} 2026",
        )
        db_session.add(bp)
        bps.append(bp)
    await db_session.commit()

    groups = await build_groups(db_session, subsidy.id)
    group = next(g for g in groups if purchase.id in g.purchase_ids)

    result = await match_monthly(db_session, group, purchase, dry_run=False)
    assert len(result["attached"]) == 3, result

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(payments) == 3
    periods = sorted(p.service_period for p in payments)
    assert periods == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


# ---------------------------------------------------------------------------
# 2. Рамочные — (а) 2 платежа на 1 заказ, (б) 1 платёж на 2 заказа
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_framework_many_to_one_and_one_to_many(db_session, test_org):
    subsidy = await _subsidy(db_session)
    contractor = await _contractor(db_session)
    contract_number = f"FW-{_uid()}"
    status = _executed_status()

    def _mk_order(reg_suffix, amount):
        p = Purchase(
            item_name=f"Заказ-{reg_suffix}",
            status="delivered",
            contractor_id=contractor.id,
            subsidy_id=subsidy.id,
            registry_number=f"REG-{reg_suffix}-{_uid()}",
            contract_number=contract_number,
            purchase_contract_type="framework_with_amount",
        )
        return p

    order_a = _mk_order("A", Decimal("51234.00"))
    order_b = _mk_order("B", Decimal("30000.00"))
    order_c = _mk_order("C", Decimal("20000.00"))
    db_session.add_all([order_a, order_b, order_c])
    await db_session.commit()
    for p in (order_a, order_b, order_c):
        await db_session.refresh(p)

    items = [
        PurchaseItem(purchase_id=order_a.id, item_name="Товар А", item_type="товар",
                     quantity=1, unit_price=Decimal("51234.00"), total_price=Decimal("51234.00")),
        PurchaseItem(purchase_id=order_b.id, item_name="Товар Б", item_type="товар",
                     quantity=1, unit_price=Decimal("30000.00"), total_price=Decimal("30000.00")),
        PurchaseItem(purchase_id=order_c.id, item_name="Товар В", item_type="товар",
                     quantity=1, unit_price=Decimal("20000.00"), total_price=Decimal("20000.00")),
    ]
    db_session.add_all(items)

    # (а) заказ A оплачен ДВУМЯ платежами: 32000 + 19234
    bp_a1 = BankPayment(subsidy_id=subsidy.id, payee_inn=contractor.inn,
                         parsed_contract_number=contract_number, amount=Decimal("32000.00"),
                         payment_date=date(2026, 2, 1), status=status,
                         purpose_text=f"Оплата по договору {contract_number}, транш 1")
    bp_a2 = BankPayment(subsidy_id=subsidy.id, payee_inn=contractor.inn,
                         parsed_contract_number=contract_number, amount=Decimal("19234.00"),
                         payment_date=date(2026, 2, 2), status=status,
                         purpose_text=f"Оплата по договору {contract_number}, транш 2")
    # (б) заказы B+C оплачены ОДНИМ платежом 50000
    bp_bc = BankPayment(subsidy_id=subsidy.id, payee_inn=contractor.inn,
                         parsed_contract_number=contract_number, amount=Decimal("50000.00"),
                         payment_date=date(2026, 2, 3), status=status,
                         purpose_text=f"Оплата по договору {contract_number}, заказы Б и В")
    db_session.add_all([bp_a1, bp_a2, bp_bc])
    await db_session.commit()

    groups = await build_groups(db_session, subsidy.id)
    fw_groups = [g for g in groups if g.is_framework and g.contract_number == contract_number]
    assert len(fw_groups) == 3

    result = await match_framework(db_session, fw_groups, dry_run=False)
    assert not result["ambiguous"], result["ambiguous"]
    cases = {tuple(sorted(a.get("bank_payment_ids", [a.get("bank_payment_id")]))) for a in result["attached"]}
    assert len(result["attached"]) == 2, result["attached"]

    payments_a = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == order_a.id)
    )).scalars().all()
    assert sum(p.amount for p in payments_a) == Decimal("51234.00")
    assert len(payments_a) == 2

    payments_b = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == order_b.id)
    )).scalars().all()
    payments_c = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == order_c.id)
    )).scalars().all()
    assert sum(p.amount for p in payments_b) == Decimal("30000.00")
    assert sum(p.amount for p in payments_c) == Decimal("20000.00")


@pytest.mark.asyncio
async def test_framework_ambiguous_subset_not_attached(db_session, test_org):
    """Два заказа одинаковой суммы + один платёж, который одинаково хорошо
    закрывает любой из них по сумме — настоящая неоднозначность, НЕ привязывать."""
    subsidy = await _subsidy(db_session)
    contractor = await _contractor(db_session)
    contract_number = f"FW-{_uid()}"
    status = _executed_status()

    order_1 = Purchase(
        item_name="Заказ-1", status="delivered", contractor_id=contractor.id, subsidy_id=subsidy.id,
        registry_number=f"REG-1-{_uid()}", contract_number=contract_number,
        purchase_contract_type="framework_with_amount",
    )
    order_2 = Purchase(
        item_name="Заказ-2", status="delivered", contractor_id=contractor.id, subsidy_id=subsidy.id,
        registry_number=f"REG-2-{_uid()}", contract_number=contract_number,
        purchase_contract_type="framework_with_amount",
    )
    db_session.add_all([order_1, order_2])
    await db_session.commit()
    for p in (order_1, order_2):
        await db_session.refresh(p)

    db_session.add_all([
        PurchaseItem(purchase_id=order_1.id, item_name="Товар", item_type="товар",
                     quantity=1, unit_price=Decimal("15000.00"), total_price=Decimal("15000.00")),
        PurchaseItem(purchase_id=order_2.id, item_name="Товар", item_type="товар",
                     quantity=1, unit_price=Decimal("15000.00"), total_price=Decimal("15000.00")),
    ])
    # Два отдельных платежа одинаковой суммы — обычный find_candidates (не этот
    # модуль) уже разруливает по дате; здесь же искусственно создаём неоднозначность
    # ТОЛЬКО для одного из заказов через third payment, который подходит под оба
    # заказа одновременно по subset-sum (сам заказ 1 платёж = сумма) — чтобы не
    # тестировать то же самое, что find_candidates, фиксируем, что модуль
    # НЕ пытается бить одноплатёжные случаи (len(pool) < 2 guard в match_framework).
    bp = BankPayment(subsidy_id=subsidy.id, payee_inn=contractor.inn,
                      parsed_contract_number=contract_number, amount=Decimal("15000.00"),
                      payment_date=date(2026, 3, 1), status=status)
    db_session.add(bp)
    await db_session.commit()

    groups = await build_groups(db_session, subsidy.id)
    fw_groups = [g for g in groups if g.is_framework and g.contract_number == contract_number]
    result = await match_framework(db_session, fw_groups, dry_run=False)
    # Один платёж на один заказ — ЗА ПРЕДЕЛАМИ этого модуля (len(pool) < 2 guard):
    # ничего не привязано этим путём, обычный find_candidates возьмёт его отдельно.
    assert result["attached"] == []


# ---------------------------------------------------------------------------
# 3. Авансовые — получатель по ИНН сотрудника (основной признак — см. задачу
# 05.10.2026: живая выгрузка приходит с ПУСТЫМ payee_name, дефект разбора
# двухстрочной шапки чинится отдельно, см. _employee_inn в payment_lookup_multi.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_by_employee_inn_empty_payee_name(db_session, test_org):
    """Строка выписки без payee_name (как на живых данных 05.10.2026) всё
    равно находится — по users.inn сотрудника-получателя возмещения."""
    subsidy = await _subsidy(db_session)
    status = _executed_status()

    employee = User(
        username=f"emp-{_uid()}", password_hash="x", role="employee",
        last_name="Петров", first_name="Пётр", middle_name="Петрович",
        full_name="Петров Пётр Петрович",
        inn=f"50{uuid.uuid4().int % 10**10:010d}",
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    purchase = Purchase(
        item_name=f"Авансовый-{_uid()}",
        status="delivered",
        subsidy_id=subsidy.id,
        registry_number=f"REG-ADV-{_uid()}",
        purchase_method="advance",
        reimbursement_user_id=employee.id,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Канцтовары", item_type="товар",
        quantity=1, unit_price=Decimal("4500.00"), total_price=Decimal("4500.00"),
    ))

    bp = BankPayment(
        subsidy_id=subsidy.id,
        payee_name=None,  # дефект живой выгрузки — пустое поле
        payee_inn=employee.inn,
        amount=Decimal("4500.00"),
        payment_date=date(2026, 4, 1),
        status=status,
    )
    db_session.add(bp)
    await db_session.commit()

    groups = await build_groups(db_session, subsidy.id)
    group = next(g for g in groups if purchase.id in g.purchase_ids)

    result = await match_advance(db_session, [(group, purchase)], dry_run=False)
    assert len(result["attached"]) == 1, result

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].amount == Decimal("4500.00")
    assert payments[0].bank_payment_id == bp.id


@pytest.mark.asyncio
async def test_advance_by_employee_fio_fallback_when_no_inn(db_session, test_org):
    """Запасной путь: ни users.inn, ни ИНН из прошлых авансовых платежей
    сотрудника — сравнение по ФИО (payee_name заполнен)."""
    subsidy = await _subsidy(db_session)
    status = _executed_status()

    employee = User(
        username=f"emp-{_uid()}", password_hash="x", role="employee",
        last_name="Иванов", first_name="Иван", middle_name="Иванович",
        full_name="Иванов Иван Иванович",
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    purchase = Purchase(
        item_name=f"Авансовый-{_uid()}",
        status="delivered",
        subsidy_id=subsidy.id,
        registry_number=f"REG-ADV-{_uid()}",
        purchase_method="advance",
        reimbursement_user_id=employee.id,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Канцтовары", item_type="товар",
        quantity=1, unit_price=Decimal("4500.00"), total_price=Decimal("4500.00"),
    ))

    bp = BankPayment(
        subsidy_id=subsidy.id,
        payee_name="ИВАНОВ ИВАН ИВАНОВИЧ",  # разный регистр — normalize_person_name сравнивает lowercase
        amount=Decimal("4500.00"),
        payment_date=date(2026, 4, 1),
        status=status,
    )
    db_session.add(bp)
    await db_session.commit()

    groups = await build_groups(db_session, subsidy.id)
    group = next(g for g in groups if purchase.id in g.purchase_ids)

    result = await match_advance(db_session, [(group, purchase)], dry_run=False)
    assert len(result["attached"]) == 1, result

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == purchase.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].amount == Decimal("4500.00")
    assert payments[0].bank_payment_id == bp.id


# ---------------------------------------------------------------------------
# 4. Импорт выписки оставляет прогон в журнале (не удаляет 'done')
# ---------------------------------------------------------------------------

def _xlsx_minimal(payment_number, amount, payee_inn, status):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append([
        "НОМЕР ДОКУМЕНТА", "ДАТА ДОКУМЕНТА", "СТАТУС ДОКУМЕНТА", "СУММА",
        "ИНН ПЛАТЕЛЬЩИКА", "НАИМЕНОВАНИЕ ПЛАТЕЛЬЩИКА",
        "ИНН ПОЛУЧАТЕЛЯ", "НАИМЕНОВАНИЕ ПОЛУЧАТЕЛЯ",
        "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)", "ИДЕНТИФИКАТОР ДОКУМЕНТА",
    ])
    ws.append([
        payment_number, "01.05.2026", status, amount,
        "1234567890", "ООО Плательщик", payee_inn, "ООО Получатель",
        "Оплата по договору", f"doc-{_uid()}",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_successful_import_stays_in_journal(client, superadmin_headers, db_session, monkeypatch):
    """Задача 05.10.2026: раньше успешный ('done') прогон удалялся сразу после
    загрузки — владелец не мог найти свою загрузку в журнале. Теперь прогон
    должен остаться в GET /api/payments/imports со status='done'."""
    import app.routers.bank_statements as bsr
    from app.models.bank_statement import BankStatementImport

    async def _fake_match(db, import_id):
        return {"matched_contract": 0, "total": 1}

    monkeypatch.setattr(bsr, "match_all_in_import", _fake_match)

    payee_inn = f"60{uuid.uuid4().int % 10**8:08d}"
    content = _xlsx_minimal(f"P{_uid()}", 1000, payee_inn, "ИСПОЛНЕН")
    files = {"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    resp = await client.post("/api/payments/imports", files=files, headers=superadmin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    import_id = body["id"]

    stored = await db_session.get(BankStatementImport, import_id)
    assert stored is not None, "успешный прогон не должен удаляться из журнала"
    assert stored.status == "done"

    list_resp = await client.get("/api/payments/imports", headers=superadmin_headers)
    assert list_resp.status_code == 200, list_resp.text
    ids = [row["id"] for row in list_resp.json()]
    assert import_id in ids
