"""Двухстрочная шапка выписки («Реквизиты получателя»/«Реквизиты плательщика»
merged-ячейкой над колонками ИНН/КПП/Наименование) — баг 05.10.2026.

Прод-находка: PrintScroller_21-09-2026 11-22.xlsx — 1824 новых строки
bank_payments со всеми пустыми payee_name (payee_inn заполнен). Причина —
_extract_headers (bank_statement_parser_rows.py) схлопывал merged-заголовок
«РЕКВИЗИТЫ ПОЛУЧАТЕЛЯ» в единственный ключ без composite "(ИНН)"/"(КПП)"/
"(НАИМЕНОВАНИЕ)", потому что main уже был в HEADER_MAP (мэппится как
payee_block — fallback старого ОДНОстрочного формата). ИНН/КПП/Наименование
трёх под-колонок склеивались через "\n" в один raw-текст, а payee_block-ветка
_build_row вытаскивала из него регуляркой только ИНН — payee_name никогда не
заполнялся.

Фикс: BLOCK_FIELDS (bank_statement_parser_maps.py) — множество полей-
«контейнеров» (payer_block/payee_block), для которых _extract_headers НЕ
схлопывает merged-заголовок в main, а строит composite-ключ "MAIN (SUB)",
который уже совпадает с существующими записями HEADER_MAP
("РЕКВИЗИТЫ ПОЛУЧАТЕЛЯ (ИНН)" и т.п.) — однострочный формат (где sub реально
contamination от data row) не затронут, т.к. его поля не в BLOCK_FIELDS.

Второй тест — дедуп: повторная загрузка той же выписки, где у существующей
строки (без ИНН в однострочном old-формате — или пришедшей ДО фикса)
payee_name пуст, backfill через apply_mutable_fields (bank_payment_dedup.py
MUTABLE_FIELDS теперь включает payee_name/payee_kpp/payer_name/payer_kpp/
payer_account и т.п.) — без задвоения строки.
"""
import io
import uuid
from decimal import Decimal

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.services.bank_statement_parser import parse_workbook


def _uid():
    return uuid.uuid4().hex[:8]


def _two_row_header_xlsx(payment_number, payment_date, amount, status,
                          payee_inn, payee_kpp, payee_name, doc_id=None):
    """Строит xlsx с ДВУхстрочной шапкой: строка 1 — одиночные заголовки +
    merged «Реквизиты получателя» над 3 колонками; строка 2 — подзаголовки
    ИНН/КПП/Наименование под merged-блоком (под одиночными заголовками —
    пусто, как в реальном файле: merge по строкам 1-2, не по колонкам)."""
    wb = Workbook()
    ws = wb.active

    # Колонки: A=НОМЕР ДОКУМЕНТА, B=ДАТА ДОКУМЕНТА, C=СТАТУС ДОКУМЕНТА,
    # D=СУММА, E..G=РЕКВИЗИТЫ ПОЛУЧАТЕЛЯ (ИНН/КПП/Наименование),
    # H=ИДЕНТИФИКАТОР ДОКУМЕНТА.
    ws["A1"] = "НОМЕР ДОКУМЕНТА"
    ws["B1"] = "ДАТА ДОКУМЕНТА"
    ws["C1"] = "СТАТУС ДОКУМЕНТА"
    ws["D1"] = "СУММА"
    ws["E1"] = "РЕКВИЗИТЫ ПОЛУЧАТЕЛЯ"
    ws["H1"] = "ИДЕНТИФИКАТОР ДОКУМЕНТА"

    # Одиночные заголовки — merge по вертикали (1-2), как «Сумма» в реальном
    # файле: main==sub после _expand_merged_row, не contamination.
    for col in ("A", "B", "C", "D", "H"):
        ws.merge_cells(f"{col}1:{col}2")

    ws["E2"] = "ИНН"
    ws["F2"] = "КПП"
    ws["G2"] = "НАИМЕНОВАНИЕ"
    ws.merge_cells("E1:G1")

    ws.append([
        payment_number, payment_date, status, amount,
        payee_inn, payee_kpp, payee_name, doc_id,
    ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_two_row_header_fills_payee_name_inn_kpp():
    """Composite-разбор merged «Реквизиты получателя» → payee_inn/kpp/name
    все три заполнены, не только ИНН."""
    xlsx = _two_row_header_xlsx(
        "ПП-1", "10.01.2026", 1000, "ИСПОЛНЕН",
        "7701234567", "770101001", 'ООО "Ромашка"',
    )
    sheet_name, rows = parse_workbook(xlsx)
    assert len(rows) == 1
    row = rows[0]
    assert row.payee_inn == "7701234567"
    assert row.payee_kpp == "770101001"
    assert row.payee_name == 'ООО "Ромашка"'


def test_single_row_legacy_header_still_works():
    """Регрессия на фикс 07.05.2026 (6f94e38a): однострочный формат без
    sub-row (ДАТА ДОКУМЕНТА, НАЗНАЧЕНИЕ ПЛАТЕЖА и т.п. без merge) по-прежнему
    не ломается — BLOCK_FIELDS не трогает поля вне payer_block/payee_block."""
    wb = Workbook()
    ws = wb.active
    ws.append([
        "НОМЕР ДОКУМЕНТА", "ДАТА ДОКУМЕНТА", "СТАТУС ДОКУМЕНТА", "СУММА",
        "ИНН ПОЛУЧАТЕЛЯ", "НАИМЕНОВАНИЕ ПОЛУЧАТЕЛЯ",
        "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)",
    ])
    ws.append([
        "ПП-2", "11.01.2026", "ИСПОЛНЕН", 500,
        "7709876543", "ООО Ветер", "Договор 1 от 01.01.2026",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    sheet_name, rows = parse_workbook(buf.getvalue())
    assert len(rows) == 1
    row = rows[0]
    assert row.payee_inn == "7709876543"
    assert row.payee_name == "ООО Ветер"
    assert row.payment_date is not None
    assert row.purpose_text == "Договор 1 от 01.01.2026"


@pytest.mark.asyncio
async def test_reimport_backfills_empty_payee_name(client, superadmin_headers, db_session, monkeypatch):
    """Существующая строка с пустым payee_name (как 1824 прод-строки до
    фикса) + повторная загрузка той же выписки (теперь с правильно
    распарсенным payee_name, тем же external_doc_id) → payee_name
    дозаполняется (apply_mutable_fields), rows_updated=1, новых строк 0."""
    import app.routers.bank_statements as bsr

    async def _fake_match(db, import_id):
        return 1, 0

    monkeypatch.setattr(bsr, "match_all_in_import", _fake_match)

    payee_inn = f"50{uuid.uuid4().int % 10**8:08d}"
    payment_number = f"P{_uid()}"
    amount = Decimal("777.00")
    doc_id = f"DOC-{_uid()}"
    import datetime
    payment_date = datetime.date(2026, 1, 12)

    # Строка, уже загруженная (с тем же external_doc_id) ДО фикса —
    # payee_name/payee_kpp пусты, payee_inn есть (ровно симптом бага).
    existing = BankPayment(
        payment_number=payment_number,
        payment_date=payment_date,
        amount=amount,
        payee_inn=payee_inn,
        payee_kpp=None,
        payee_name=None,
        status="НА ИСПОЛНЕНИИ ЦС",
        external_doc_id=doc_id,
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    xlsx = _two_row_header_xlsx(
        payment_number, "12.01.2026", float(amount), "ИСПОЛНЕН",
        payee_inn, "770101001", 'ООО "Ромашка"', doc_id=doc_id,
    )

    resp = await client.post(
        "/api/payments/imports",
        files={"file": ("statement.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rows_imported"] == 0  # новых строк — 0
    assert data["rows_updated"] == 1

    await db_session.refresh(existing)
    assert existing.payee_name == 'ООО "Ромашка"'
    assert existing.payee_kpp == "770101001"
    assert existing.status == "ИСПОЛНЕН"

    rows = (await db_session.execute(
        select(BankPayment).where(BankPayment.external_doc_id == doc_id)
    )).scalars().all()
    assert len(rows) == 1  # не задвоилось
