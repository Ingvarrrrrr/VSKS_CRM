"""Задача B и A (план breezy-mixing-lovelace.md / владелец 07.10.2026):

  (A) ФОТ определяется по категории ФЭО плановой позиции (себя или предка
      с is_payroll=True), НЕ по словам в названии/пути строки файла.
  (B) Строка со статусом «Оплачено», чья плановая позиция уже лежит в
      СУЩЕСТВУЮЩЕЙ закупке (match.state == 'already_purchased') — не
      пропускается молча, а поднимает статус этой закупки и заводит платёж
      «по отметке»; новая закупка не создаётся. Откат возвращает всё как было.

Хелпер _build_ho_workbook/_row переиспользован из test_fact_import_commit.py
(ПРАВИЛО №6, тот же приём, что test_fact_import_existing_match.py)."""
import json
import uuid

import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.payment import Payment
from app.models.contract_item import ContractItem
from app.models.permission import RolePermission

from tests.test_fact_import_commit import _build_ho_workbook, _row


async def _grant_edit(db_session):
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()


# ---- Задача A: ФОТ по категории, не по словам в названии ------------------

async def test_payroll_determined_by_category_not_name(client, auth_headers, test_user, db_session, test_org):
    await _grant_edit(db_session)
    subsidy = Subsidy(name=f"Payroll-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat_normal = FeoCategory(subsidy_id=subsidy.id, level=3, name="Прочие расходы")
    cat_payroll_root = FeoCategory(subsidy_id=subsidy.id, level=3, name="ФОТ и иные выплаты персоналу", is_payroll=True)
    db_session.add_all([cat_normal, cat_payroll_root])
    await db_session.flush()
    # Статья-ПОТОМОК статьи is_payroll — сама не помечена, но наследует
    # признак по дереву (payroll_category_ids, feo_payroll.py).
    cat_payroll_child = FeoCategory(subsidy_id=subsidy.id, level=4, name="Страховые взносы", parent_id=cat_payroll_root.id)
    db_session.add(cat_payroll_child)
    await db_session.flush()

    # Оба названия содержат «страхов» — старый is_payroll_path сказал бы
    # True для обеих. Категория решает: первая — обычная статья, вторая —
    # потомок статьи ФОТ.
    item_normal = FeoPlannedItem(feo_category_id=cat_normal.id, name="Страхование от БПЛА", amount=10000, is_active=True)
    item_payroll = FeoPlannedItem(feo_category_id=cat_payroll_child.id, name="КАМАЗ (страховка)", amount=5000, is_active=True)
    db_session.add_all([item_normal, item_payroll])
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Прочие расходы", 10000, 10000, 10000, status_raw="Оплачено", item_name="Страхование от БПЛА"),
        _row("Страховые взносы", 5000, 5000, 5000, status_raw="Оплачено", item_name="КАМАЗ (страховка)"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    rows_by_name = {r["name"]: r for r in resp.json()["rows"]}
    assert rows_by_name["Страхование от БПЛА"]["is_payroll"] is False
    assert rows_by_name["КАМАЗ (страховка)"]["is_payroll"] is True


# ---- Задача B: already_purchased + «Оплачено» обновляет существующую -----

@pytest.fixture
async def already_purchased_setup(db_session, test_org):
    subsidy = Subsidy(name=f"FactImport-EU-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Мебель и инвентарь")
    db_session.add(cat)
    await db_session.flush()
    plan_item = FeoPlannedItem(feo_category_id=cat.id, name="Стол офисный", amount=240000, is_active=True)
    db_session.add(plan_item)

    contractor = Contractor(name="ООО «ОФИСМАГ»", org_id=test_org.id)
    db_session.add(contractor)
    await db_session.flush()

    # Закупка «в работе», БЕЗ договора — её плановая позиция уже привязана
    # (item1.feo_planned_item_id = plan_item.id), значит matching.py отдаст
    # этой строке файла match.state == 'already_purchased'.
    purchase = Purchase(subsidy_id=subsidy.id, status="work_in_progress", contractor_id=contractor.id,
                         is_monthly_payment=False, feo_category_id=cat.id)
    db_session.add(purchase)
    await db_session.flush()
    item1 = PurchaseItem(purchase_id=purchase.id, item_name="Стол офисный", quantity=10,
                          unit_price=24000, total_price=240000, feo_planned_item_id=plan_item.id,
                          feo_category_id=cat.id)
    item2 = PurchaseItem(purchase_id=purchase.id, item_name="Стул офисный", quantity=4,
                          unit_price=10000, total_price=40000)
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(purchase)
    return subsidy, cat, plan_item, contractor, purchase, item1, item2


async def test_already_purchased_paid_updates_existing_purchase(
    client, auth_headers, test_user, db_session, already_purchased_setup,
):
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = already_purchased_setup

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 240000, 240000, 240000, paid=240000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])

    preview_resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()
    row = preview["rows"][0]
    assert row["match"]["state"] == "already_purchased"
    assert row["skip"] is False
    assert row["existing_purchase"]["id"] == purchase.id
    assert preview["totals"]["existing_updates"] == 1
    # Не создаёт группу, которая считалась бы новой закупкой.
    assert preview["totals"]["purchases"] == 0
    eu = preview["existing_updates"][0]
    assert eu["purchase_id"] == purchase.id
    assert eu["status_to"] == "paid"
    assert eu["paid_add"] == 240000

    commit_resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert commit_resp.status_code == 200, commit_resp.text
    out = commit_resp.json()
    assert out["purchases_created"] == 0
    assert out["payments_created"] == 1
    run_id = out["run_id"]

    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1  # новая закупка не создана

    await db_session.refresh(purchase)
    assert purchase.status == "paid"
    assert purchase.contract_number_is_temporary is True
    assert purchase.contract_number

    cis = (await db_session.execute(select(ContractItem).where(ContractItem.purchase_id == purchase.id))).scalars().all()
    assert len(cis) == 2  # договорные позиции материализованы (item1 + item2)

    pays = (await db_session.execute(select(Payment).where(Payment.purchase_id == purchase.id))).scalars().all()
    assert len(pays) == 1
    assert float(pays[0].amount) == 240000
    assert pays[0].import_run_id == run_id

    # Откат — закупка должна вернуться как была.
    rb = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=false",
        headers=auth_headers,
    )
    assert rb.status_code == 200, rb.text
    assert rb.json()["rolled_back"] is True

    await db_session.refresh(purchase)
    assert purchase.status == "work_in_progress"
    assert purchase.contract_number is None

    pays_after = (await db_session.execute(select(Payment).where(Payment.purchase_id == purchase.id))).scalars().all()
    assert pays_after == []

    cis_after = (await db_session.execute(select(ContractItem).where(ContractItem.purchase_id == purchase.id))).scalars().all()
    assert cis_after == []
