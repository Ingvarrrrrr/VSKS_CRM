# -*- coding: utf-8 -*-
"""Прод-баг 01.10.2026 (закупка 974): сотрудник (role employee) создал
авансовый отчёт — он assigned_user_id/reimbursement_user_id/service_note_by
закупки, но create_purchase НЕ создаёт PurchaseMember (32 из 35 авансовых на
проде без членов). POST /api/purchases/{id}/files падал 403, хотя тот же
пользователь свободно редактирует закупку через _has_purchase_write_access
(routers/purchases.py), который пускает всех, кто ВИДИТ закупку.

Фикс (purchase_files.py::_check_upload_permission) — после проверок
ключ/member/approver добавлена проверка общего контура видимости
(ПРАВИЛО №6: build_visibility_clause из app.auth.visibility, не свой список
ролей). Закупка видна → загрузка разрешена.
"""
import pytest


async def _upload(client, headers, purchase_id: int, filename="check.pdf"):
    return await client.post(
        f"/api/purchases/{purchase_id}/files",
        headers=headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": (filename, b"%PDF-1.4 fake pdf content", "application/pdf")},
    )


@pytest.mark.asyncio
async def test_own_advance_purchase_upload_allowed_without_member_row(
    client, auth_headers, test_user, make_purchase,
):
    """Авансовый отчёт, где test_user — assigned_user_id/reimbursement_user_id/
    service_note_by, но НЕТ строки PurchaseMember/PurchaseApproval — видимость
    через build_visibility_clause (assigned_user_id/reimbursement_user_id in
    visible_uids) должна пустить загрузку."""
    p = await make_purchase(
        purchase_method="advance",
        assigned_user_id=test_user.id,
        reimbursement_user_id=test_user.id,
        service_note_by=test_user.id,
    )

    resp = await _upload(client, auth_headers, p.id)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_outsider_employee_without_visibility_gets_403(
    client, test_user, make_purchase, make_user,
):
    """Посторонний employee той же организации, не связанный с закупкой
    (не assigned/reimbursement/member/approver) — закупка ему не видна,
    загрузка должна остаться 403."""
    p = await make_purchase(
        purchase_method="advance",
        assigned_user_id=test_user.id,
        reimbursement_user_id=test_user.id,
        service_note_by=test_user.id,
    )

    outsider = await make_user(role="employee")
    from app.auth.jwt import create_access_token
    outsider_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': outsider.username, 'org_id': outsider.org_id})}"
    }

    resp = await _upload(client, outsider_headers, p.id)
    assert resp.status_code == 403, resp.text
