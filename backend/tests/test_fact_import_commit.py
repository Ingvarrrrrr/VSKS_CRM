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
         status_raw=None, purchase_no=None, supplier=None, item_name=None, item_type=None):
    r = [None] * 28
    r[0] = "ХО_2026"
    r[5] = l3
    # item_name (опционально, test_fact_import_existing_match.py) — колонка
    # "Плановая позиция" (r[7]); без неё rows.py берёт имя строки из l3/l4
    # (см. rows.py:85 leaf_name fallback) — именно так работали прежние
    # тесты этого файла (level-3 текст совпадал с именем плановой позиции).
    if item_name is not None:
        r[7] = item_name
    # item_type (опционально, см. test_commit_normalizes_item_type_case ниже) —
    # колонка "Товар/услуга/работа" (r[8]), как в файле владельца («Товар»/
    # «Услуга» с большой буквы) — дефект (прод, «ХО (копия)», 05.10.2026):
    # commit.py писал это значение в purchase_items.item_type буквально.
    if item_type is not None:
        r[8] = item_type
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


async def test_commit_normalizes_item_type_case(client, auth_headers, test_user, db_session, subsidy_with_plan):
    """Дефект (прод, субсидия «ХО (копия)», 05.10.2026): файл несёт «Товар»/
    «Услуга» с большой буквы (как у владельца) — commit.py обязан записать
    purchase_items.item_type НОРМАЛИЗОВАННЫМ (normalize_item_type, ПРАВИЛО
    №6 — app/services/item_types.py), а не буквально текст файла, иначе любой
    потребитель, сравнивающий item_type строкой, относит позицию в «без
    типа» (см. app/services/item_type_split.py::kind_of — читает через ту же
    normalize_item_type, но сама запись в БД раньше нормализацию не проходила)."""
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook([
        _row("Аренда оборудования", 80000, 80000, 80000, paid=80000, status_raw="Оплачено",
             purchase_no="42", supplier="ООО Ромашка", item_type="Товар"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchases[0].id)
    )).scalars().all()
    assert len(items) == 1
    # Записано каноническое значение, не буквальный текст файла "Товар".
    assert items[0].item_type == "товар"

    from app.services.item_type_split import kind_of, KIND_GOODS
    assert kind_of(items[0].item_type) == KIND_GOODS


async def test_commit_work_in_progress_without_fact_uses_plan_amount(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """Дефект (прод, 05.10.2026, РЕЕ-2026-02795 и др.): строка «Ведётся работа»
    БЕЗ факта и БЕЗ законтрактованной суммы (только план: кол-во × цена) —
    commit.py брал amount = fact_amount ИЛИ contracted, оба None → total_price
    позиции записывался 0, хотя quantity/unit_price заполнялись из плана
    (50 × 8200) — несогласованная позиция «50×8200=0,00». planned_item_
    consumption/total_nmck после неё тоже считали 0. Фикс — фоллбэк на
    row.plan.amount, когда ни факта, ни договора нет (ПРАВИЛО №6: тот же
    принцип, что «план = НМЦД, пока факта нет» у обычного создания закупки)."""
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_combo = FeoPlannedItem(feo_category_id=cat.id, name="Комбинезоны", amount=410000, is_active=True)
    db_session.add(item_combo)
    await db_session.commit()

    # Строка собрана напрямую (не через _row) — нужны колонки «Плановое
    # количество»/«Плановая цена за единицу» (r[15]/r[16]), которые _row
    # никогда не заполняет (см. её докстринг выше); позиции факта (18-20) и
    # «Законтрактовано» (22) оставлены пустыми — именно это сочетание и
    # воспроизводит дефект.
    r = [None] * 28
    r[0] = "ХО_2026"
    r[5] = "Комбинезоны"
    r[15], r[16], r[17] = 50, 8200, 410000
    r[24] = "В работе"
    content = _build_ho_workbook([r])

    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["purchases_created"] == 1

    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.status == "work_in_progress"
    assert float(p.planned_total_price) == 410000
    assert float(p.total_nmck) == 410000

    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert len(items) == 1
    assert float(items[0].quantity) == 50
    assert float(items[0].unit_price) == 8200
    assert float(items[0].total_price) == 410000


def _build_ho_workbook_with_advance(rows: list) -> bytes:
    """Та же раскладка, что _build_ho_workbook, + колонка «Аванс (да/нет)»
    сразу после «Оплачено» (задача 2, владелец 05.10.2026) — индексы блока
    «Факт» сдвинуты на 1 (columns.py::TEMPLATE_HEADER)."""
    wb = Workbook()
    ws = wb.active
    header = [None] * 29
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
    header[22] = "Аванс (да/нет)"
    header[23] = "Законтрактовано"
    header[25] = "Правильный статус"
    header[26] = "№ Закупки"
    header[28] = "Поставщик "
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row_advance(l3, amount, fact_price, fact_amount, *, paid=None, advance=None,
                  contracted=None, status_raw=None, purchase_no=None, supplier=None):
    r = [None] * 29
    r[0] = "ХО_2026"
    r[5] = l3
    r[16], r[17] = fact_price, amount
    r[19], r[20] = fact_price, fact_amount
    r[21], r[22], r[23] = paid, advance, contracted
    r[25] = status_raw
    r[26], r[28] = purchase_no, supplier
    return r


async def test_commit_advance_sets_ordered_status_and_is_prepayment(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """Задача 2 (владелец, 05.10.2026): строка «Оплачено» + Аванс=да →
    закупка в статусе «Заказано» (ordered), is_prepayment=True, платёж «по
    отметке» всё равно создаётся (сумма зарезервирована, поставка ещё не
    отмечена)."""
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook_with_advance([
        _row_advance(
            "Аренда оборудования", 80000, 80000, 80000,
            paid=80000, advance="да", status_raw="Оплачено",
            purchase_no="42", supplier="ООО Ромашка",
        ),
    ])

    preview_resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()
    row = preview["rows"][0]
    assert row["status"] == "ordered"
    assert any("аванс" in w for w in row["warnings"]), row["warnings"]

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
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.status == "ordered"
    assert p.is_prepayment is True


async def test_commit_no_advance_keeps_paid_status(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """Аванс=нет (или пусто) — поведение не меняется: статус «Оплачено»,
    is_prepayment не выставляется."""
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()

    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    content = _build_ho_workbook_with_advance([
        _row_advance(
            "Аренда оборудования", 80000, 80000, 80000,
            paid=80000, advance="нет", status_raw="Оплачено",
            purchase_no="42", supplier="ООО Ромашка",
        ),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    from app.models.purchase import Purchase
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.status == "paid"
    assert not p.is_prepayment
