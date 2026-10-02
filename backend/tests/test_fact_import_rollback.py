"""Откат прогона «Импорта факта»: без блокеров — всё созданное удаляется;
закупку правили после импорта (PurchaseEvent кроме 'fact_import') — блокер,
dry_run просто перечисляет его, ничего не удаляет."""
import uuid
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission


def _build_ho_workbook(rows: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    header = [None] * 28
    header[0] = "Субсидия"
    header[5] = "Уровень 3 (Тип расходов по ФЭО)"
    header[16], header[17] = "Плановая цена за единицу", "Сумма плана"
    header[18] = "Факт"
    header[21], header[22] = "Оплачено ", "Законтрактовано"
    header[24] = "Правильный статус"
    header[27] = "Поставщик "
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(l3, amount, fact_price, fact_amount, status_raw, supplier=None):
    r = [None] * 28
    r[0] = "ХО_2026"
    r[5] = l3
    r[16], r[17] = fact_price, amount
    r[19], r[20] = fact_price, fact_amount
    r[24] = status_raw
    r[27] = supplier
    return r


async def _setup(db_session, test_org):
    subsidy = Subsidy(name=f"FactImport-RB-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Аренда оборудования")
    db_session.add(cat)
    await db_session.flush()
    item = FeoPlannedItem(feo_category_id=cat.id, name="Аренда оборудования", amount=30000, is_active=True)
    db_session.add(item)
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()
    return subsidy


async def test_rollback_dry_run_then_execute_removes_everything(client, auth_headers, test_user, db_session, test_org):
    subsidy = await _setup(db_session, test_org)
    content = _build_ho_workbook([_row("Аренда оборудования", 30000, 30000, 30000, "Заключён", "ООО Аренда")])

    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    dry = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=true",
        headers=auth_headers,
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["can_rollback"] is True
    assert dry.json()["will_delete"]["purchases"] == 1

    from app.models.purchase import Purchase
    before = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(before) == 1

    real = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=false",
        headers=auth_headers,
    )
    assert real.status_code == 200, real.text
    assert real.json()["can_rollback"] is True

    after = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert after == []


async def test_rollback_blocked_when_purchase_touched_after_import(client, auth_headers, test_user, db_session, test_org):
    subsidy = await _setup(db_session, test_org)
    content = _build_ho_workbook([_row("Аренда оборудования", 30000, 30000, 30000, "Заключён", "ООО Аренда")])

    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    run_id = resp.json()["run_id"]

    from app.models.purchase_event import PurchaseEvent
    from app.models.fact_import_run import FactImportRun
    run = await db_session.get(FactImportRun, run_id)
    purchase_id = run.created_refs["purchase_ids"][0]
    db_session.add(PurchaseEvent(purchase_id=purchase_id, event_type="edited_manually", data={}))
    await db_session.commit()

    dry = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=true",
        headers=auth_headers,
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["can_rollback"] is False
    assert dry.json()["blockers"]

    from app.models.purchase import Purchase
    still_there = (await db_session.execute(select(Purchase).where(Purchase.id == purchase_id))).scalar_one_or_none()
    assert still_there is not None
