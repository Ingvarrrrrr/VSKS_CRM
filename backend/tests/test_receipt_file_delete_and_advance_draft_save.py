# -*- coding: utf-8 -*-
"""Жалобы владельца (2026-09-16), авансовый отчёт (пример — закупка 914):

1. «Один из чеков не распознался, вроде как прикрепился — а как его удалить?»
   DELETE /api/purchases/{pid}/files/{fid} уже существовал (purchase_files.py),
   но кнопки удаления не было — добавлена в PurchaseReceiptsBlock.vue +
   deleteReceiptFile в usePurchaseReceipts.ts. Здесь проверяется сам эндпоинт
   (уже был, но не был покрыт тестом на этот сценарий): 200 + файл пропадает
   из БД, чужой/несуществующий файл — 403/404.

3. «Невозможно сохранить авансовый в качестве черновика, если чего-то не
   хватает». Единственная НАСТОЯЩАЯ серверная блокировка черновика авансового
   отчёта (formMode='advance_report', purchase_method='advance') —
   _check_budget в create_purchase/update_purchase (routers/purchases.py):
   раньше превышение бюджета субсидии возвращало 422 даже для авансового
   черновика. Теперь для purchase_method='advance' — только предупреждение
   (excess_warnings), сохранение проходит. Полная (блокирующая) проверка
   остаётся для обычных закупок — НЕ ослаблена (см. test_..._non_advance_still_blocks).
"""
import pytest
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select

from app.models.purchase_event import PurchaseMember
from app.models.purchase_file import PurchaseFile
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy


async def _add_member(db_session, purchase_id: int, user_id: int):
    db_session.add(PurchaseMember(purchase_id=purchase_id, user_id=user_id, role="member"))
    await db_session.commit()


async def _upload_receipt_file(client, auth_headers, purchase_id: int, filename="check.pdf"):
    resp = await client.post(
        f"/api/purchases/{purchase_id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": (filename, b"%PDF-1.4 fake pdf content", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Удаление файла чека
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_receipt_file_returns_200_and_removes_row(
    client, auth_headers, test_user, db_session, make_purchase,
):
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)
    uploaded = await _upload_receipt_file(client, auth_headers, p.id)

    resp = await client.delete(f"/api/purchases/{p.id}/files/{uploaded['id']}", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    row = await db_session.get(PurchaseFile, uploaded["id"])
    assert row is None


@pytest.mark.asyncio
async def test_delete_receipt_file_by_non_member_returns_403(
    client, auth_headers, test_user, db_session, make_purchase, make_user,
):
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)
    uploaded = await _upload_receipt_file(client, auth_headers, p.id)

    outsider = await make_user(role="employee")
    from app.auth.jwt import create_access_token
    outsider_headers = {"Authorization": f"Bearer {create_access_token({'sub': outsider.username, 'org_id': outsider.org_id})}"}

    resp = await client.delete(f"/api/purchases/{p.id}/files/{uploaded['id']}", headers=outsider_headers)
    assert resp.status_code == 403, resp.text

    # File must still be there — the 403 must not have deleted it.
    row = await db_session.get(PurchaseFile, uploaded["id"])
    assert row is not None


@pytest.mark.asyncio
async def test_delete_nonexistent_file_returns_404(client, auth_headers, test_user, db_session, make_purchase):
    p = await make_purchase()
    await _add_member(db_session, p.id, test_user.id)
    resp = await client.delete(f"/api/purchases/{p.id}/files/999999", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Черновик авансового отчёта сохраняется даже при превышении бюджета
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_budget_warns_instead_of_raising_when_raise_on_exceed_false(
    db_session, test_org,
):
    from app.routers.purchase_budget import _check_budget

    subsidy = Subsidy(name="Тестовая субсидия", year=2026, org_id=test_org.id, budget=1000)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    # Черновик авансового (raise_on_exceed=False) — предупреждение, не исключение.
    warning = await _check_budget(
        subsidy.id, Decimal("5000"), None, db_session, raise_on_exceed=False,
    )
    assert warning is not None
    assert warning["code"] == "BUDGET_EXCEEDED"

    # Обычная закупка (raise_on_exceed=True, по умолчанию) — по-прежнему 422.
    with pytest.raises(HTTPException) as exc_info:
        await _check_budget(subsidy.id, Decimal("5000"), None, db_session)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_advance_draft_saves_despite_exceeded_subsidy_budget(
    client, auth_headers, db_session, test_org,
):
    subsidy = Subsidy(name="Тестовая субсидия 2", year=2026, org_id=test_org.id, budget=100, status="approved")
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    payload = {
        "purchase_method": "advance",
        "subsidy_id": subsidy.id,
        "subject": "Авансовый — превышение бюджета",
        "items": [
            {
                "item_name": "Такси",
                "item_type": "услуга",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 50000,
                "total_price": 50000,
            }
        ],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    # Черновик обязан сохраниться, а не 422 — превышение только предупреждает.
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    warnings = body.get("excess_warnings") or []
    assert any(w.get("code") == "BUDGET_EXCEEDED" for w in warnings), warnings

    p = await db_session.get(Purchase, body["id"])
    assert p is not None


@pytest.mark.asyncio
async def test_non_advance_purchase_still_blocked_by_exceeded_budget(
    client, auth_headers, db_session, test_org,
):
    """ПРАВИЛО №6 / задача 2026-09-16 п.3: смягчение — ТОЛЬКО для черновика
    авансового отчёта (purchase_method='advance'). Обычная закупка
    (purchase_basis не 'service_note', purchase_method не 'advance') по-прежнему
    получает 422 при превышении бюджета субсидии — эта проверка НЕ ослаблена."""
    subsidy = Subsidy(name="Тестовая субсидия 3", year=2026, org_id=test_org.id, budget=100, status="approved")
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    payload = {
        "purchase_method": "single",
        "subsidy_id": subsidy.id,
        "subject": "Обычная закупка — превышение бюджета",
        "purchase_basis": "service_note",
        "items": [
            {
                "item_name": "Оборудование",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 50000,
                "total_price": 50000,
            }
        ],
    }
    # purchase_basis='service_note' would itself skip the budget check (see
    # create_purchase) — use context=service_note_delivery to pass the
    # is_advance/is_sn direct-creation gate while keeping purchase_basis
    # unset so _check_budget still runs.
    payload["purchase_basis"] = None
    resp = await client.post(
        "/api/purchases/?context=service_note_delivery", json=payload, headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
