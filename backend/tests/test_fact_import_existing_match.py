"""Похожие закупки в импорте факта (план breezy-mixing-lovelace.md, Часть А).

Собирает синтетический xlsx формата 'columns' — тот же приём, что в
test_fact_import_commit.py (переиспользован хелпер _build_ho_workbook/_row,
НЕ дублирован — импортирован оттуда, ПРАВИЛО №6)."""
import uuid
from io import BytesIO

import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

from tests.test_fact_import_commit import _build_ho_workbook, _row


@pytest.fixture
async def existing_match_setup(db_session, test_org):
    """Субсидия + категория + 2 плановые позиции + существующая закупка
    («заведена руками», без привязки позиций к плану — как 38 закупок
    владельца) с тем же поставщиком/суммой, что будет у файла импорта."""
    subsidy = Subsidy(name=f"FactImport-EM-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
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

    purchase = Purchase(subsidy_id=subsidy.id, status="paid", contractor_id=contractor.id,
                         total_nmck=240000, contract_price=240000, is_monthly_payment=False,
                         feo_category_id=cat.id)
    db_session.add(purchase)
    await db_session.flush()
    item1 = PurchaseItem(purchase_id=purchase.id, item_name="Стол офисный", quantity=10,
                          unit_price=20000, total_price=200000)
    item2 = PurchaseItem(purchase_id=purchase.id, item_name="Стул офисный", quantity=4,
                          unit_price=10000, total_price=40000)
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(purchase)
    await db_session.refresh(item1)
    await db_session.refresh(item2)
    return subsidy, cat, plan_item, contractor, purchase, item1, item2


async def _grant_edit(db_session):
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()


async def test_same_amount_match_detected_and_preselected(client, auth_headers, test_user, db_session, existing_match_setup):
    """🔵 Закупка из 15 позиций (здесь — 2, для скорости теста) против ОДНОЙ
    строки файла на ту же итоговую сумму = совпадение «та же», предвыбрано."""
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = existing_match_setup

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 240000, 240000, 240000, paid=240000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["groups"]) == 1
    group = data["groups"][0]
    assert group["needs_existing_decision"] is False
    assert len(group["existing_matches"]) == 1
    match = group["existing_matches"][0]
    assert match["kind"] == "same_amount"
    assert match["purchase_id"] == purchase.id
    assert len(match["items"]) == 2

    # Коммит БЕЗ явного decisions.existing_match — предвыбор «та же» должен
    # применяться сам (владелец: «предвыбрано»).
    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp2.status_code == 200, resp2.text
    out = resp2.json()
    assert out["purchases_created"] == 0
    assert out["existing_matches_linked"] == 1

    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1  # не создалась вторая закупка

    await db_session.refresh(item1)
    await db_session.refresh(item2)
    # Непривязанные позиции получили плановую — по умолчанию строка плана
    # из файла (единственная строка файла матчится на plan_item по имени
    # "Стол офисный"), иначе (item2, другое имя) тоже на неё же (file_row).
    assert item1.feo_planned_item_id == plan_item.id
    assert item2.feo_planned_item_id == plan_item.id
    assert item1.feo_category_id == cat.id


async def test_same_supplier_different_amount_needs_decision(client, auth_headers, test_user, db_session, existing_match_setup):
    """Тот же поставщик, другая сумма → «возможно», commit без решения — 400."""
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = existing_match_setup

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 999000, 999000, 999000, paid=999000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()["groups"][0]
    assert group["needs_existing_decision"] is True
    assert group["existing_matches"][0]["kind"] == "same_supplier"

    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp2.status_code == 400

    # Явное "другая" — создаёт как обычно.
    import json
    resp3 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"decisions": json.dumps({"existing_match": {group["key"]: {"purchase_id": purchase.id, "action": "new"}}})},
        headers=auth_headers,
    )
    assert resp3.status_code == 200, resp3.text
    assert resp3.json()["purchases_created"] == 1
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 2


async def test_create_planned_item_and_rollback_undoes_it(client, auth_headers, test_user, db_session, existing_match_setup):
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = existing_match_setup

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 240000, 240000, 240000, paid=240000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    group = resp.json()["groups"][0]

    import json
    decisions = {
        "existing_match": {
            group["key"]: {
                "purchase_id": purchase.id,
                "action": "same",
                "item_links": {str(item2.id): {"create_planned": True}},
            },
        },
    }
    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"decisions": json.dumps(decisions)},
        headers=auth_headers,
    )
    assert resp2.status_code == 200, resp2.text
    run_id = resp2.json()["run_id"]

    await db_session.refresh(item2)
    new_fpi_id = item2.feo_planned_item_id
    assert new_fpi_id is not None
    assert new_fpi_id != plan_item.id
    new_fpi = await db_session.get(FeoPlannedItem, new_fpi_id)
    assert new_fpi is not None
    assert new_fpi.name == "Стул офисный"

    resp3 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=false",
        headers=auth_headers,
    )
    assert resp3.status_code == 200, resp3.text
    assert resp3.json()["rolled_back"] is True

    await db_session.refresh(item2)
    assert item2.feo_planned_item_id is None
    assert (await db_session.get(FeoPlannedItem, new_fpi_id)) is None


async def test_already_bound_item_not_touched(client, auth_headers, test_user, db_session, existing_match_setup):
    """Уже привязанная позиция существующей закупки не трогается решением «та же»."""
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = existing_match_setup

    other_item = FeoPlannedItem(feo_category_id=cat.id, name="Стул офисный — старый план", amount=40000, is_active=True)
    db_session.add(other_item)
    await db_session.commit()
    item2.feo_planned_item_id = other_item.id
    item2.feo_category_id = cat.id
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 240000, 240000, 240000, paid=240000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])
    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp2.status_code == 200, resp2.text

    await db_session.refresh(item2)
    await db_session.refresh(item1)
    assert item2.feo_planned_item_id == other_item.id  # не изменилась
    assert item1.feo_planned_item_id == plan_item.id    # непривязанная получила план


async def test_stopped_purchase_excluded_from_matches(client, auth_headers, test_user, db_session, existing_match_setup):
    await _grant_edit(db_session)
    subsidy, cat, plan_item, contractor, purchase, item1, item2 = existing_match_setup
    from datetime import datetime, timezone
    purchase.stopped_at = datetime.now(timezone.utc)
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Мебель и инвентарь", 240000, 240000, 240000, paid=240000, status_raw="Оплачено",
             supplier="ООО ОФИСМАГ", item_name="Стол офисный"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()["groups"][0]
    assert group["existing_matches"] == []
    assert group["needs_existing_decision"] is False
