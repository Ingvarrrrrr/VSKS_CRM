"""GET/PUT дублей строк ТЗ закупки (routers/purchase_tz.py) и гейт генерации
документа (services/documents/stages_load.py::framework_contract_guard →
_require_tz_duplicates_resolved_for_doc), владелец 21.09, corrections-21-09.md
W3.

Паттерн теста (client/auth_headers/db_session, skip если шаблона нет в
контейнере) — по образцу test_wish_tech_spec_document.py.
"""
import os
from decimal import Decimal
from io import BytesIO

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


def _template_exists() -> bool:
    return os.path.exists("/app/templates/contract_tz.docx")


_SKIP_NO_TEMPLATE = pytest.mark.skipif(
    not _template_exists(),
    reason="contract_tz.docx not available in test environment — template-dependent test skipped",
)


async def _make_purchase_with_duplicates(db_session) -> Purchase:
    """Закупка с 2 дублями «Огнетушитель» (2 шт + 3 шт, разные категории ФЭО
    по духу теста — здесь просто разные строки) и 1 уникальной позицией."""
    p = Purchase(status="planned", item_type="goods", item_name="Test purchase TZ dup")
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Огнетушитель ОП-5", unit="шт",
        quantity=Decimal("2"), unit_price=Decimal("1000"), total_price=Decimal("2000"),
    ))
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="огнетушитель оп-5", unit="шт",
        quantity=Decimal("3"), unit_price=Decimal("1000"), total_price=Decimal("3000"),
    ))
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Стул офисный", unit="шт",
        quantity=Decimal("1"), unit_price=Decimal("5000"), total_price=Decimal("5000"),
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_get_tz_rows_reports_duplicate_group_unresolved(client, db_session, auth_headers):
    p = await _make_purchase_with_duplicates(db_session)
    resp = await client.get(f"/api/purchases/{p.id}/tz-rows", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["duplicate_groups"]) == 1
    group = body["duplicate_groups"][0]
    assert group["qty_sum"] == 5
    assert group["total_sum"] == 5000
    assert len(body["unresolved_keys"]) == 1
    # Без решения — строки как есть (3 строки), не склеены молча.
    assert len(body["rows"]) == 3


@pytest.mark.asyncio
async def test_put_tz_duplicates_merge_persists_and_resolves(client, db_session, auth_headers):
    p = await _make_purchase_with_duplicates(db_session)
    get_resp = await client.get(f"/api/purchases/{p.id}/tz-rows", headers=auth_headers)
    key = get_resp.json()["duplicate_groups"][0]["key"]

    put_resp = await client.put(
        f"/api/purchases/{p.id}/tz-duplicates",
        json={"decisions": {key: "merge"}},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["unresolved_keys"] == []
    assert body["decisions"][key] == "merge"
    # 1 смерженная строка (qty=5) + 1 уникальная = 2.
    assert len(body["rows"]) == 2
    merged_row = next(r for r in body["rows"] if r["item_name"].lower().startswith("огнетушитель"))
    assert merged_row["quantity"] == 5
    assert merged_row["total_price"] == 5000

    # Персистентность — повторный GET отдаёт то же decision.
    await db_session.refresh(p)
    assert p.tz_duplicate_decisions == {key: "merge"}
    get2 = await client.get(f"/api/purchases/{p.id}/tz-rows", headers=auth_headers)
    assert get2.json()["decisions"][key] == "merge"


@pytest.mark.asyncio
async def test_put_tz_duplicates_rejects_invalid_decision(client, db_session, auth_headers):
    p = await _make_purchase_with_duplicates(db_session)
    resp = await client.put(
        f"/api/purchases/{p.id}/tz-duplicates",
        json={"decisions": {"some-key": "delete"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_generate_document_409_when_duplicates_unresolved(client, db_session, auth_headers):
    p = await _make_purchase_with_duplicates(db_session)
    resp = await client.get(f"/api/purchases/{p.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "TZ_DUPLICATES_UNRESOLVED"
    assert "Огнетушитель" in body["message"] or "огнетушитель" in body["message"]


@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_generate_document_after_merge_has_one_summed_row(client, db_session, auth_headers):
    p = await _make_purchase_with_duplicates(db_session)
    get_resp = await client.get(f"/api/purchases/{p.id}/tz-rows", headers=auth_headers)
    key = get_resp.json()["duplicate_groups"][0]["key"]
    put_resp = await client.put(
        f"/api/purchases/{p.id}/tz-duplicates",
        json={"decisions": {key: "merge"}},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200, put_resp.text

    resp = await client.get(f"/api/purchases/{p.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    from docx import Document as _DocxDoc
    doc = _DocxDoc(BytesIO(resp.content))
    full_text = "\n".join(
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    )
    # Одна строка «Огнетушитель» (совпадает с представителем группы — первая
    # по порядку появления, "Огнетушитель ОП-5"), не две.
    assert full_text.lower().count("огнетушитель оп-5") == 1
    assert "5" in full_text  # суммарное количество 2+3=5, без ".0" (_fmt_quantity)
