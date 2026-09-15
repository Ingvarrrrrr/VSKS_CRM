"""Жалоба владельца (2026-09-15): «в авансовый отчёт нельзя загрузить чек,
только TIF». Покрывает две новые точки входа:

1. POST /purchases/{id}/receipts/import-html — распознавание чека из
   сохранённой HTML-страницы proverkacheka.com (services/receipts_parsing.py::
   _parse_proverkacheka_html_receipt, переиспользует существующий парсер
   таблицы позиций _extract_items_from_proverkacheka_html — ПРАВИЛО №6).
2. POST /purchases/{id}/files с file_type='receipt' — «файл чека» без
   автораспознавания (PDF/TIFF) и HTML, который не удалось разобрать;
   несколько файлов такого типа должны сосуществовать (MULTI_FILE_TYPES),
   в отличие от остальных file_type, где новый файл деактивирует старый.
"""
import pytest
from sqlalchemy import select

from app.models.purchase_event import PurchaseMember
from app.models.purchase_file import PurchaseFile
from app.models.purchase_item import PurchaseItem

# Синтетический фрагмент HTML в разметке proverkacheka.com — та же структура
# таблицы (классы b-check_item / b-check_vblock-first|last), что уже парсит
# _extract_items_from_proverkacheka_html, плюс шапка (ИНН/ФН/ФД/ФПД/дата/итог)
# по best-effort регуляркам _parse_proverkacheka_html_receipt.
PROVERKACHEKA_HTML = """
<html><body>
<div class="b-check_header">
  <div>ООО "Тестовый Продавец"</div>
  <div>ИНН 7707083893</div>
</div>
<table class="b-check_table">
  <tr class="b-check_item b-check_vblock-first">
    <td>1</td><td>Товар Один</td><td>100.00</td><td>2</td><td>200.00</td>
  </tr>
  <tr class="b-check_item b-check_vblock-last">
    <td colspan="5">НДС со ставкой 20%: 33.33</td>
  </tr>
  <tr class="b-check_item b-check_vblock-first">
    <td>2</td><td>Товар Два</td><td>50.00</td><td>1</td><td>50.00</td>
  </tr>
  <tr class="b-check_item b-check_vblock-last">
    <td colspan="5">НДС со ставкой 10%: 4.55</td>
  </tr>
</table>
<div class="b-check_footer">
  <div>Дата 05.09.2026 14:23</div>
  <div>ИТОГО 250.00</div>
  <div>ФН 9282440300065554</div>
  <div>ФД 12345</div>
  <div>ФПД 1234567890</div>
</div>
</body></html>
"""

NOT_A_RECEIPT_HTML = "<html><body><h1>Просто страница без таблицы товаров</h1></body></html>"


@pytest.mark.asyncio
async def test_import_html_recognized_creates_receipt_with_items(client, auth_headers, db_session, make_purchase):
    p = await make_purchase()
    resp = await client.post(
        f"/api/purchases/{p.id}/receipts/import-html",
        headers=auth_headers,
        files={"file": ("check.html", PROVERKACHEKA_HTML.encode("utf-8"), "text/html")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    receipt = data[0]
    assert receipt["source"] == "html_import"
    assert receipt["seller_inn"] == "7707083893"
    assert float(receipt["total_sum"]) == pytest.approx(250.0)

    # db_session и client используют одну и ту же transaction-scoped сессию
    # (см. conftest.client) — читаем PurchaseItem напрямую, без сериализации
    # PurchaseOutFull (там своя, не относящаяся к этой фиче, логика FEO/матчинга).
    items_q = await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )
    names = [it.item_name for it in items_q.scalars().all()]
    assert "Товар Один" in names
    assert "Товар Два" in names


@pytest.mark.asyncio
async def test_import_html_unrecognized_returns_400_with_clear_message(client, auth_headers, make_purchase):
    p = await make_purchase()
    resp = await client.post(
        f"/api/purchases/{p.id}/receipts/import-html",
        headers=auth_headers,
        files={"file": ("not_a_check.html", NOT_A_RECEIPT_HTML.encode("utf-8"), "text/html")},
    )
    assert resp.status_code == 400
    # Приложение оборачивает HTTPException в {code, message, details, correlation_id}
    # (см. app/__init__.py error handler) — не стандартный FastAPI {"detail": ...}.
    message = resp.json().get("message", "")
    assert "распознать" in message.lower()


@pytest.mark.asyncio
async def test_import_html_rejects_non_html_extension(client, auth_headers, make_purchase):
    p = await make_purchase()
    resp = await client.post(
        f"/api/purchases/{p.id}/receipts/import-html",
        headers=auth_headers,
        files={"file": ("check.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


async def _add_member(db_session, purchase_id: int, user_id: int):
    db_session.add(PurchaseMember(purchase_id=purchase_id, user_id=user_id, role="member"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_pdf_file_attaches_as_receipt(client, auth_headers, test_user, db_session, make_purchase):
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)
    resp = await client.post(
        f"/api/purchases/{p.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("check.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_type"] == "receipt"


@pytest.mark.asyncio
async def test_tiff_file_attaches_as_receipt(client, auth_headers, test_user, db_session, make_purchase):
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)
    resp = await client.post(
        f"/api/purchases/{p.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("check.tiff", b"fake tiff bytes", "image/tiff")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_type"] == "receipt"


@pytest.mark.asyncio
async def test_multiple_receipt_files_do_not_deactivate_each_other(client, auth_headers, test_user, db_session, make_purchase):
    """Обычные file_type деактивируют предыдущий файл того же типа при новой
    загрузке (см. upload_file) — для 'receipt' это неверно: несколько чеков
    закупки (PDF + PNG-без-QR и т.п.) должны остаться видимыми одновременно."""
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)

    r1 = await client.post(
        f"/api/purchases/{p.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("check1.pdf", b"pdf-bytes-one", "application/pdf")},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/api/purchases/{p.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("check2.tiff", b"tiff-bytes-two", "image/tiff")},
    )
    assert r2.status_code == 200, r2.text

    rows = (await db_session.execute(
        select(PurchaseFile).where(
            PurchaseFile.purchase_id == p.id,
            PurchaseFile.file_type == "receipt",
        )
    )).scalars().all()
    assert len(rows) == 2
    assert all(row.is_active for row in rows)
