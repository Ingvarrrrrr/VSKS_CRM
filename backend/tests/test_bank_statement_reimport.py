"""Дедуп повторной загрузки выписки — владелец, 05.10.2026 (находка после
живой проверки payment-control): legacy-строки без external_doc_id (загружены
ДО появления колонки «Идентификатор документа») задваивались при перезаливке
того же файла в новом формате, а статус старой строки не обновлялся.

См. app/services/bank_payment_dedup.py.
"""
import io
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase


def _xlsx_with_doc_id(payment_number, payment_date, amount, payee_inn, status, doc_id):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append([
        "НОМЕР ДОКУМЕНТА",
        "ДАТА ДОКУМЕНТА",
        "СТАТУС ДОКУМЕНТА",
        "СУММА",
        "ИНН ПЛАТЕЛЬЩИКА",
        "НАИМЕНОВАНИЕ ПЛАТЕЛЬЩИКА",
        "ИНН ПОЛУЧАТЕЛЯ",
        "НАИМЕНОВАНИЕ ПОЛУЧАТЕЛЯ",
        "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)",
        "ИДЕНТИФИКАТОР ДОКУМЕНТА",
    ])
    ws.append([
        payment_number, payment_date, status, amount,
        "1234567890", "ООО Рога", payee_inn, "ООО Копыта",
        "Договор 5 от 01.01.2026", doc_id,
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.mark.asyncio
async def test_legacy_row_merges_on_reimport_and_keeps_links(client, superadmin_headers, db_session, monkeypatch):
    """Legacy-строка без external_doc_id + новая с id, тем же payment_number/
    date/amount/payee_inn → склейка (merged_legacy), статус обновлён, связь
    Payment.bank_payment_id не потеряна."""
    import app.routers.bank_statements as bsr

    async def _fake_match(db, import_id):
        return 1, 0

    monkeypatch.setattr(bsr, "match_all_in_import", _fake_match)

    payee_inn = f"50{uuid.uuid4().int % 10**8:08d}"
    payment_number = f"P{_uid()}"
    amount = Decimal("12345.67")
    import datetime
    payment_date = datetime.date(2026, 1, 10)

    contractor = Contractor(name=f"Контрагент-{_uid()}", inn=payee_inn)
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    purchase = Purchase(
        item_name="Тест", status="contracted", contractor_id=contractor.id,
        contract_price=amount,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    legacy = BankPayment(
        payment_number=payment_number,
        payment_date=payment_date,
        amount=amount,
        payee_inn=payee_inn,
        status="НА ИСПОЛНЕНИИ ЦС",
        external_doc_id=None,
    )
    db_session.add(legacy)
    await db_session.commit()
    await db_session.refresh(legacy)

    payment = Payment(
        purchase_id=purchase.id, amount=amount, bank_payment_id=legacy.id,
        document_number=payment_number, matched_confirmed=True,
        confirmed_by_statement=True, payment_source="statement",
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    doc_id = f"DOC-{_uid()}"
    xlsx = _xlsx_with_doc_id(
        payment_number, "10.01.2026", float(amount), payee_inn, "ИСПОЛНЕН", doc_id,
    )

    resp = await client.post(
        "/api/payments/imports",
        files={"file": ("statement.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rows_imported"] == 0
    assert data["rows_merged_legacy"] == 1
    assert data["rows_updated"] == 1

    await db_session.refresh(legacy)
    assert legacy.external_doc_id == doc_id
    assert legacy.status == "ИСПОЛНЕН"

    still_linked = (await db_session.execute(
        select(Payment).where(Payment.id == payment.id)
    )).scalar_one()
    assert still_linked.bank_payment_id == legacy.id
    assert still_linked.confirmed_by_statement is True

    # Повторная загрузка ТОГО ЖЕ файла — теперь external_doc_id уже в БД,
    # ничего не изменилось → 0 inserted, unchanged=1.
    resp2 = await client.post(
        "/api/payments/imports",
        files={"file": ("statement.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=superadmin_headers,
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["rows_imported"] == 0
    assert data2["rows_unchanged"] == 1
    assert data2["rows_merged_legacy"] == 0

    rows = (await db_session.execute(
        select(BankPayment).where(BankPayment.external_doc_id == doc_id)
    )).scalars().all()
    assert len(rows) == 1  # не задвоилось
