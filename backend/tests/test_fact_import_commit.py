"""End-to-end: POST /preview не пишет в БД, POST /commit создаёт закупку +
договор + платёж «по отметке» ОДНИМ прогоном, без согласований/уведомлений.

Собирает синтетический xlsx формата 'columns' (как ХО) прямо в памяти —
тот же порядок колонок, что в образце владельца (см. test_fact_import_rows.py
для буква-в-букву соответствия)."""
import uuid
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


def _build_ho_workbook(rows: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    header = [None] * 28
    header[0] = "Субсидия"
    header[4] = "Уровень 2 (Направление расходов по ФЭО)"
    header[5] = "Уровень 3 (Тип расходов по ФЭО)"
    header[6] = "Уровень 4 (Конкретизированный)"
    header[7] = "Плановая позиция (папка НЕ создаётся)"
    header[8] = "Товар/услуга/работа"
    header[14] = "Ед. изм. плана"
    header[15] = "Плановое количество"
    header[16] = "Плановая цена за единицу"
    header[17] = "Сумма плана"
    header[18] = "Факт"
    header[21] = "Оплачено "
    header[22] = "Законтрактовано"
    header[24] = "Правильный статус"
    header[25] = "№ Закупки"
    header[27] = "Поставщик "
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(l3, amount, fact_price, fact_amount, paid=None, contracted=None,
         status_raw=None, purchase_no=None, supplier=None, item_name=None):
    r = [None] * 28
    r[0] = "ХО_2026"
    r[5] = l3
    # item_name (опционально, test_fact_import_existing_match.py) — колонка
    # "Плановая позиция" (r[7]); без неё rows.py берёт имя строки из l3/l4
    # (см. rows.py:85 leaf_name fallback) — именно так работали прежние
    # тесты этого файла (level-3 текст совпадал с именем плановой позиции).
    if item_name is not None:
        r[7] = item_name
    r[16], r[17] = fact_price, amount
    r[19], r[20] = fact_price, fact_amount
    r[21], r[22] = paid, contracted
    r[24] = status_raw
    r[25], r[27] = purchase_no, supplier
    return r


@pytest.fixture
async def subsidy_with_plan(db_session, test_org):
    subsidy = Subsidy(name=f"FactImport-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Аренда оборудования")
    db_session.add(cat)
    await db_session.flush()
    item_paid = FeoPlannedItem(feo_category_id=cat.id, name="Аренда оборудования", amount=80000, is_active=True)
    item_wip = FeoPlannedItem(feo_category_id=cat.id, name="Ремонт оборудования", amount=50000, is_active=True)
    db_session.add_all([item_paid, item_wip])
    await db_session.commit()
    return subsidy, cat, item_paid, item_wip


async def test_preview_does_not_write(client, auth_headers, test_user, db_session, subsidy_with_plan):
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook([
        _row("Аренда оборудования", 80000, 80000, 80000, paid=80000, status_raw="Оплачено", purchase_no="42", supplier="ООО Ромашка"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["totals"]["purchases"] == 1
    assert data["totals"]["contract_amount"] == 80000

    from app.models.purchase import Purchase
    count = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert count == []


async def test_commit_creates_purchase_contract_and_payment(client, auth_headers, test_user, db_session, subsidy_with_plan):
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook([
        _row("Аренда оборудования", 80000, 80000, 80000, paid=80000, status_raw="Оплачено", purchase_no="42", supplier="ООО Ромашка"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["purchases_created"] == 1
    assert data["payments_created"] == 1

    from app.models.purchase import Purchase
    from app.models.payment import Payment
    from app.models.contract_item import ContractItem
    from app.models.plan_excess_approval import PlanExcessApproval

    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.status == "paid"
    assert p.contract_number_is_temporary is True
    assert float(p.contract_price) == 80000

    cis = (await db_session.execute(select(ContractItem).where(ContractItem.purchase_id == p.id))).scalars().all()
    assert len(cis) == 1
    assert float(cis[0].total) == 80000

    pays = (await db_session.execute(select(Payment).where(Payment.purchase_id == p.id))).scalars().all()
    assert len(pays) == 1
    assert pays[0].payment_source == "manual"
    assert pays[0].confirmed_by_statement is False
    assert pays[0].document_number is None
    assert float(pays[0].amount) == 80000

    excess = (await db_session.execute(select(PlanExcessApproval).where(PlanExcessApproval.subsidy_id == subsidy.id))).scalars().all()
    assert excess == []

    # Баг (соседняя сессия, прогон run_id=38 на проде-копии): PurchaseItem.
    # feo_category_id/Purchase.feo_category_id оставались NULL — дерево ФЭО
    # ищет категорию через COALESCE(PurchaseItem.feo_category_id, Purchase.
    # feo_category_id) с INNER JOIN на FeoCategory (committed_amounts.py) —
    # NULL в обеих колонках = закупка невидима в дереве.
    from app.models.purchase_item import PurchaseItem
    items = (await db_session.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == p.id))).scalars().all()
    assert len(items) == 1
    assert items[0].feo_category_id == cat.id
    assert p.feo_category_id == cat.id


async def test_commit_fact_visible_in_feo_plan_tree(client, auth_headers, test_user, db_session, subsidy_with_plan):
    """Коммит должен быть виден в compute_feo_plan_tree (committed/fact узла
    категории), не только в таблице purchases — иначе дерево ФЭО показывает
    0 законтрактовано при реально существующих деньгах (баг соседней сессии,
    прогон run_id=38)."""
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook([
        _row("Аренда оборудования", 80000, 80000, 80000, paid=80000, status_raw="Оплачено", purchase_no="42", supplier="ООО Ромашка"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree.get(cat.id)
    assert node is not None, f"Категория {cat.id} не найдена в дереве — импорт невидим"
    assert node["committed"] >= 80000 - 0.01, node
    assert node["fact"] >= 80000 - 0.01, node


async def test_commit_without_supplier_groups_by_category(client, auth_headers, test_user, db_session, subsidy_with_plan):
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook([
        _row("Ремонт оборудования", 50000, 50000, 50000, status_raw="В работе"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["purchases_created"] == 1

    from app.models.purchase import Purchase
    from app.models.contract_item import ContractItem
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.status == "work_in_progress"
    assert p.contract_price is None  # «в работе» без договора — владелец
    cis = (await db_session.execute(select(ContractItem).where(ContractItem.purchase_id == p.id))).scalars().all()
    assert cis == []
