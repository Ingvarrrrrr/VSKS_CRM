"""display_contractor_name (app/services/purchase_contractor_display.py) —
владелец, 30.09: «Если это авансовый отчёт, в столбце "Контрагент" должны
выводиться данные, кому его возмещать, а не у кого куплено» — и в реестре
закупок (GET /api/purchases/{id}, GET /api/purchases/), и в Excel-экспорте
(GET /api/purchases/export/excel). Один хелпер, оба читателя — ПРАВИЛО №6,
проверяем, что оба реально дают одно и то же ФИО на одних данных, а не только
что механизм где-то есть (см. VAULT-урок feedback_verify_user_scenario_not_mechanism).

Три случая:
  1. reimbursement_user_id задан → contractor_name = ФИО получателя возмещения,
     ВО ВСЕХ трёх читателях (helper напрямую, GET /{id}, экспорт).
  2. reimbursement_user_id пуст, service_note_by (автор/инициатор) задан →
     фолбэк на ФИО автора.
  3. Обычная (не авансовая) закупка — contractor_name не трогается хелпером
     (поведение как раньше, по шапке договора/contractor_id).
"""
import uuid
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models.purchase import Purchase
from app.services.purchase_contractor_display import display_contractor_name


async def _make_subsidy(db_session, test_org):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=1_000_000,
                require_planned_dates=False, org_id=test_org.id)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_user(db_session, test_org, full_name):
    from app.models.user import User
    from app.auth.jwt import hash_password
    username = f"test_user_{uuid.uuid4().hex[:8]}"
    u = User(
        username=username,
        password_hash=hash_password("testpass123"),
        role="employee",
        org_id=test_org.id,
        full_name=full_name,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_helper_prefers_reimbursement_then_author_then_none():
    advance = Purchase(purchase_method="advance", item_name="Аванс")
    single = Purchase(purchase_method="single", item_name="Обычная закупка")

    # 1) получатель возмещения задан — побеждает продавца и автора
    assert display_contractor_name(
        advance, contractor_name="ООО Продавец",
        reimbursement_user_name="Иванов И.И.", service_note_by_name="Петров П.П.",
    ) == "Иванов И.И."

    # 2) получателя нет — фолбэк на автора/инициатора
    assert display_contractor_name(
        advance, contractor_name="ООО Продавец",
        reimbursement_user_name=None, service_note_by_name="Петров П.П.",
    ) == "Петров П.П."

    # 3) ни того, ни другого нет — пусто (продавец из чеков сюда не подставляется)
    assert display_contractor_name(
        advance, contractor_name="ООО Продавец",
        reimbursement_user_name=None, service_note_by_name=None,
    ) is None

    # Обычная закупка — хелпер не трогает, отдаёт контрагента шапки как раньше
    assert display_contractor_name(
        single, contractor_name="ООО Продавец",
        reimbursement_user_name="Иванов И.И.", service_note_by_name="Петров П.П.",
    ) == "ООО Продавец"


@pytest.mark.asyncio
async def test_get_purchase_uses_reimbursement_user_name(client, db_session, test_org, auth_headers):
    recipient = await _make_user(db_session, test_org, "Сидоров С.С.")
    p = Purchase(
        item_name="Аванс на билеты",
        purchase_method="advance",
        status="planned",
        reimbursement_user_id=recipient.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["contractor_name"] == "Сидоров С.С."
    assert data["reimbursement_user_name"] == "Сидоров С.С."


@pytest.mark.asyncio
async def test_get_purchase_falls_back_to_author_when_no_reimbursement(client, db_session, test_org, auth_headers):
    author = await _make_user(db_session, test_org, "Кузнецов К.К.")
    p = Purchase(
        item_name="Аванс без получателя",
        purchase_method="advance",
        status="planned",
        reimbursement_user_id=None,
        service_note_by=author.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["contractor_name"] == "Кузнецов К.К."


@pytest.mark.asyncio
async def test_purchases_list_uses_reimbursement_user_name(client, db_session, test_org, admin_headers):
    # admin_headers (org_admin, org-lead) — список закупок фильтрует по видимости
    # (build_visibility_clause), закупка без assigned_user_id видна только
    # org-lead'ам (см. purchases.py::list_purchases, is_org_lead-фолбэк); тест
    # проверяет сериализацию contractor_name, а не саму видимость.
    recipient = await _make_user(db_session, test_org, "Морозова М.М.")
    subsidy = await _make_subsidy(db_session, test_org)
    p = Purchase(
        item_name="Аванс в списке",
        purchase_method="advance",
        status="planned",
        subsidy_id=subsidy.id,
        reimbursement_user_id=recipient.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.get("/api/purchases/", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = [r for r in resp.json() if r["id"] == p.id]
    assert len(rows) == 1
    assert rows[0]["contractor_name"] == "Морозова М.М."


@pytest.mark.asyncio
async def test_excel_export_uses_reimbursement_user_name(client, db_session, test_org, auth_headers):
    recipient = await _make_user(db_session, test_org, "Волкова В.В.")
    p = Purchase(
        item_name="Аванс для экспорта",
        purchase_method="advance",
        status="planned",
        reimbursement_user_id=recipient.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.get("/api/purchases/export/excel", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    wb = load_workbook(BytesIO(resp.content))
    ws = wb.active
    header = [c.value for c in ws[1]]
    col_idx = header.index("Контрагент")  # 0-based; openpyxl rows are 1-based cells
    values_by_item_name = {
        row[header.index("Наименование")]: row[col_idx]
        for row in ws.iter_rows(min_row=2, values_only=True)
    }
    assert values_by_item_name.get("Аванс для экспорта") == "Волкова В.В."
