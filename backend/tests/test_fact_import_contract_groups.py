"""Группировка по договору (владелец, 16.10.2026, шаг 2) — «группировка по
договору, внутри договора — по номерам заказов, делай как GoodsService»:
  - «Разовый» — одна закупка на всю группу (как раньше, не меняется);
  - «Рамочный накопительный» — голова (договор, без позиций) + дочерняя
    закупка на КАЖДЫЙ «Номер заказа» (order_no);
  - «Рамочный с суммой» — то же + лимит строки «Установка предельной суммы
    договора» идёт в Contract.max_amount/Purchase.contract_price головы;
  - настоящий номер/дата договора (не временный «ВРЕМ-…»), когда лист его
    дал;
  - откат прогона удаляет и голову, и все заказы.

Собирает синтетический xlsx (формат 'columns', как ХО) с добавленными
колонками группировки по договору (Тип договора/Номер заказа/ИНН/Номер
договора/Дата Договора) — см. test_fact_import_commit.py за буква-в-букву
соответствие базового layout."""
import uuid
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.historical_fact_import.contract_groups import build_source_key


def test_build_source_key_no_identity_falls_back_to_purchase_no():
    """Правка 16.10.2026 — прод-находка: строка без ИНН и без поставщика
    (supplier_fallback пуст), но с № закупки (D) — ключ строится по D с
    маркером «нет поставщика» (`-`), а не None, иначе при повторной заливке
    закупка без идентификатора задваивается (прод-пример: закупка 40999,
    № закупки D=130, без контрагента, субсидия 26121)."""
    assert build_source_key(None, "130") == "gs:-:130"


def test_build_source_key_no_identity_with_order_no():
    """То же для дочернего заказа рамочного договора — № заказа (E)
    дописывается в конец ключа, как и у ключей с identity."""
    assert build_source_key(None, "130", "1") == "gs:-:130:1"


def test_build_source_key_no_identity_and_no_purchase_no_is_none():
    """Без № закупки (D) identity всё равно не восстановить — None, как и
    раньше (ничего не меняется в этом случае)."""
    assert build_source_key(None, None) is None
    assert build_source_key(None, "") is None

# Базовый layout — как в test_fact_import_commit.py (28 колонок ХО), плюс
# 5 новых в конце под группировку по договору.
_CONTRACT_KIND_IDX = 28
_ORDER_NO_IDX = 29
_INN_IDX = 30
_CONTRACT_NUMBER_IDX = 31
_CONTRACT_DATE_IDX = 32
_WIDTH = 33


def _build_workbook(rows: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    header = [None] * _WIDTH
    header[0] = "Субсидия"
    header[5] = "Уровень 3 (Тип расходов по ФЭО)"
    header[7] = "Плановая позиция (папка НЕ создаётся)"
    header[15] = "Плановое количество"
    header[16] = "Плановая цена за единицу"
    header[17] = "Сумма плана"
    header[18] = "Факт"
    header[21] = "Оплачено "
    header[24] = "Правильный статус"
    header[25] = "№ Закупки"
    header[27] = "Поставщик "
    header[_CONTRACT_KIND_IDX] = "Тип договора"
    header[_ORDER_NO_IDX] = "Номер заказа внутри закупки"
    header[_INN_IDX] = "ИНН"
    header[_CONTRACT_NUMBER_IDX] = "Номер договора"
    header[_CONTRACT_DATE_IDX] = "Дата Договора"
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(item_name, amount, fact_amount, *, l3="Прочее", paid=None, status_raw="Оплачено",
         purchase_no=None, supplier=None, contract_kind=None, order_no=None, inn=None,
         contract_number=None, contract_date=None):
    r = [None] * _WIDTH
    r[0] = "ФАДМ_тест"
    r[5] = l3
    r[7] = item_name
    r[16], r[17] = amount, amount
    r[19], r[20] = amount, fact_amount
    r[21] = paid
    r[24] = status_raw
    r[25], r[27] = purchase_no, supplier
    r[_CONTRACT_KIND_IDX] = contract_kind
    r[_ORDER_NO_IDX] = order_no
    r[_INN_IDX] = inn
    r[_CONTRACT_NUMBER_IDX] = contract_number
    r[_CONTRACT_DATE_IDX] = contract_date
    return r


async def _grant_edit(db_session):
    from app.models.permission import RolePermission
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()


async def _make_subsidy(db_session, test_org) -> Subsidy:
    subsidy = Subsidy(name=f"ContractGroups-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    return subsidy


async def test_single_kind_is_one_flat_purchase_with_real_number(client, auth_headers, test_user, db_session, test_org):
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    content = _build_workbook([
        _row("Бензин", 10000, 10000, paid=10000, purchase_no="1", supplier="ООО Ромашка",
             contract_kind="Разовый", inn="7707049388", contract_number="ДОГОВОР 55", contract_date="01.02.2026"),
        _row("Масло", 2000, 2000, paid=2000, purchase_no="1", supplier="ООО Ромашка",
             contract_kind="Разовый", inn="7707049388", contract_number="ДОГОВОР 55", contract_date="01.02.2026"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchases_created"] == 1

    from app.models.purchase import Purchase
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.parent_purchase_id is None
    assert p.contract_number == "ДОГОВОР 55"
    assert p.contract_number_is_temporary is False


async def test_framework_cumulative_creates_head_and_three_orders(client, auth_headers, test_user, db_session, test_org):
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    kwargs = dict(purchase_no="10", supplier="ООО Рамка", contract_kind="Рамочный накопительный",
                  inn="7707049388", contract_number="Нет данных")
    content = _build_workbook([
        _row("Товар А", 1000, 1000, paid=1000, order_no="1", status_raw="Оплачено", **kwargs),
        _row("Товар Б", 2000, 2000, order_no="2", status_raw="Поставлено", **kwargs),
        _row("Товар В", 3000, 3000, order_no="3", status_raw="Заказано", **kwargs),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert resp.json()["purchases_created"] == 4  # 1 голова + 3 заказа

    from app.models.purchase import Purchase
    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy.id).order_by(Purchase.id)
    )).scalars().all()
    assert len(purchases) == 4
    head = next(p for p in purchases if p.parent_purchase_id is None)
    orders = [p for p in purchases if p.parent_purchase_id == head.id]
    assert len(orders) == 3
    assert head.purchase_contract_type == "framework_cumulative"
    # «Нет данных» — заглушка, не настоящий номер → временный.
    assert head.contract_number_is_temporary is True
    order_numbers = sorted(o.order_number for o in orders)
    assert order_numbers == ["1", "2", "3"]
    statuses = {o.order_number: o.status for o in orders}
    assert statuses["1"] == "paid"
    assert statuses["2"] == "delivered"
    assert statuses["3"] == "ordered"
    # Все заказы — один и тот же договор головы (contract_id общий).
    assert all(o.contract_id == head.contract_id for o in orders)


async def test_framework_with_amount_sets_contract_limit(client, auth_headers, test_user, db_session, test_org):
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    kwargs = dict(purchase_no="20", supplier="ООО Предрейсовый", contract_kind="Рамочный с суммой",
                  inn="7704351079", contract_number="ДОГОВОР 2026-1-Ф", contract_date="02.02.2026")
    content = _build_workbook([
        _row("Лимит договора", 500000, 500000, order_no="Установка предельной суммы договора",
             status_raw="Заключён", **kwargs),
        _row("Заказ 1", 100000, 100000, order_no="1", status_raw="Оплачено", **kwargs),
        _row("Заказ 2", 150000, 150000, order_no="2", status_raw="Поставлено", **kwargs),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchases_created"] == 3  # 1 голова + 2 заказа (строка-лимит — не заказ)

    from app.models.purchase import Purchase
    from app.models.contract import Contract
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    head = next(p for p in purchases if p.parent_purchase_id is None)
    orders = [p for p in purchases if p.parent_purchase_id == head.id]
    assert len(orders) == 2
    assert head.purchase_contract_type == "framework_with_amount"
    assert head.contract_number == "ДОГОВОР 2026-1-Ф"
    assert head.contract_number_is_temporary is False
    assert float(head.contract_price) == 500000
    contract = await db_session.get(Contract, head.contract_id)
    assert float(contract.max_amount) == 500000


async def test_rollback_removes_framework_head_and_orders(client, auth_headers, test_user, db_session, test_org):
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    kwargs = dict(purchase_no="30", supplier="ООО Откат", contract_kind="Рамочный накопительный",
                  inn="5031069379", contract_number="Нет данных")
    content = _build_workbook([
        _row("Товар 1", 1000, 1000, order_no="1", status_raw="Оплачено", **kwargs),
        _row("Товар 2", 2000, 2000, order_no="2", status_raw="Заказано", **kwargs),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert resp.json()["purchases_created"] == 3

    from app.models.purchase import Purchase
    before = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(before) == 3
    contract_id = next(p.contract_id for p in before if p.parent_purchase_id is None)

    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/runs/{run_id}/rollback?dry_run=false",
        headers=auth_headers,
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["can_rollback"] is True

    after = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert after == []

    from app.models.contract import Contract
    contract = await db_session.get(Contract, contract_id)
    assert contract is None


async def test_multi_category_group_sets_feo_per_item(client, auth_headers, test_user, db_session, test_org):
    """Владелец (16.10.2026): позиции ОДНОЙ группы («Разовый», одна закупка)
    из ДВУХ разных категорий ФЭО → Purchase.feo_per_item=True,
    feo_category_id=None (категория на каждой позиции своя, как ручная
    форма закупки в режиме «своя категория для каждого товара»). Одна
    категория на все позиции группы → feo_per_item=False, feo_category_id
    заполнен (как раньше)."""
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=3, name="Бензин категория")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=3, name="Масло категория")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()
    plan_a = FeoPlannedItem(feo_category_id=cat_a.id, name="Бензин товар", amount=10000, is_active=True)
    plan_b = FeoPlannedItem(feo_category_id=cat_b.id, name="Масло товар", amount=2000, is_active=True)
    db_session.add_all([plan_a, plan_b])
    await db_session.commit()

    content = _build_workbook([
        _row("Бензин товар", 10000, 10000, l3="Бензин категория", paid=10000,
             purchase_no="1", supplier="ООО Ромашка", contract_kind="Разовый",
             inn="7707049388", contract_number="ДОГОВОР 55", contract_date="01.02.2026"),
        _row("Масло товар", 2000, 2000, l3="Масло категория", paid=2000,
             purchase_no="1", supplier="ООО Ромашка", contract_kind="Разовый",
             inn="7707049388", contract_number="ДОГОВОР 55", contract_date="01.02.2026"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchases_created"] == 1

    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert len(purchases) == 1
    p = purchases[0]
    assert p.feo_per_item is True
    assert p.feo_category_id is None
    items = (await db_session.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == p.id))).scalars().all()
    item_cats = {it.feo_category_id for it in items}
    assert item_cats == {cat_a.id, cat_b.id}


async def test_single_category_group_keeps_feo_per_item_false(client, auth_headers, test_user, db_session, test_org):
    """Зеркало теста выше — ОДНА категория на все позиции группы →
    feo_per_item=False (как было, регрессия на обычный случай)."""
    await _grant_edit(db_session)
    subsidy = await _make_subsidy(db_session, test_org)
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Топливо категория")
    db_session.add(cat)
    await db_session.flush()
    plan = FeoPlannedItem(feo_category_id=cat.id, name="Бензин товар", amount=10000, is_active=True)
    db_session.add(plan)
    await db_session.commit()

    content = _build_workbook([
        _row("Бензин товар", 10000, 10000, l3="Топливо категория", paid=10000,
             purchase_no="1", supplier="ООО Ромашка", contract_kind="Разовый",
             inn="7707049388", contract_number="ДОГОВОР 55", contract_date="01.02.2026"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("t.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    from app.models.purchase import Purchase
    purchases = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    p = purchases[0]
    assert p.feo_per_item is False
    assert p.feo_category_id == cat.id
