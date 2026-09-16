"""Владелец (2026-09-16): «Сделай вкладку ТЗ, только свёрнутая, как в закупке».

Новый эндпоинт GET /api/wishes/{wish_id}/documents/tech_spec (wish_documents.py)
генерирует Техническое задание .docx из позиций ЗАЯВКИ (до одобрения, ещё нет
покупки/договора) — тем же построителем items_list, что печатает ТЗ уже
подтверждённой закупки (_build_items_list_from_purchase_items,
services/documents/contexts.py — docstring там прямо говорит, что построитель
годится и для WishItem), и тем же приоритетом резолюции файла шаблона
(_resolve_doc_template_path, doc_type 'tech_spec' → contract_tz.docx).

Паттерн теста (client/auth_headers/db_session, skip если шаблона нет в
контейнере) — по образцу test_wish_service_note.py. Гоняется по одному узлу
(project_pytest_asyncio_loop_flake, память проекта)."""
from io import BytesIO

import pytest

from app.models.wish import Wish
from app.models.wish_item import WishItem


def _template_exists() -> bool:
    import os
    return os.path.exists("/app/templates/contract_tz.docx")


_SKIP_NO_TEMPLATE = pytest.mark.skipif(
    not _template_exists(),
    reason="contract_tz.docx not available in test environment — template-dependent test skipped",
)


@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_wish_tech_spec_returns_docx_with_item_names(client, db_session, auth_headers, test_org, test_user):
    """GET .../documents/tech_spec returns a parseable .docx containing item names."""
    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка для ТЗ 20260916",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id,
        item_name="Ноутбук тестовый для ТЗ",
        quantity=2,
        unit="шт",
        unit_price=50000,
        total_price=100000,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ct = resp.headers.get("content-type", "")
    assert "wordprocessingml" in ct

    from urllib.parse import unquote
    cd = unquote(resp.headers.get("content-disposition", ""))
    assert "ТЗ" in cd and cd.endswith(".docx"), f"unexpected Content-Disposition: {cd!r}"

    assert len(resp.content) > 1000, "response body too small — likely not a real .docx"

    from docx import Document as _DocxDoc
    doc = _DocxDoc(BytesIO(resp.content))
    full_text = "\n".join(
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    )
    assert "Ноутбук тестовый для ТЗ" in full_text, "item name not found in generated ТЗ"


@pytest.mark.asyncio
async def test_wish_tech_spec_404_for_missing_wish(client, auth_headers):
    resp = await client.get("/api/wishes/9999999/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wish_tech_spec_422_for_wish_without_items(client, db_session, auth_headers, test_org, test_user):
    w = Wish(
        org_id=test_org.id,
        title="Заявка без позиций 20260916",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 422
