"""Тесты владельца 08.10.2026 (прод ФАДМ 2026_2) — голова рамочного договора
не закупка, а организационная запись:

  1. gather_live_plan_graph_data (лист «План закупок», оба варианта — «по
     направлениям» и «по порядку» читают ОДНИ И ТЕ ЖЕ данные) не включает
     ГОЛОВУ рамочного договора (parent_purchase_id IS NULL, purchase_contract_
     type начинается с 'framework') ни в purchased_by_cat, ни в
     unlinked_purchases — её заказы (parent_purchase_id = голова) остаются.
  2. gather_contracts_sheet_data («Реестр договоров»): «Поставлено»/
     «Оплачено»/«Заказано по договору» строки головы — Σ заявок (без второго
     расчёта по статусу самой головы); «Статья ФЭО» — общая статья заявок,
     либо «Разные», если она различается между заявками."""
import uuid

import pytest
from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.services.plan_graph_export_contracts_sheet import gather_contracts_sheet_data
from app.services.plan_graph_export_data import gather_live_plan_graph_data


async def _make_subsidy(db_session, budget=5_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
        require_planned_dates=False, status="approved",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_cat(db_session, subsidy_id, level, parent_id=None, name="Статья"):
    cat = FeoCategory(subsidy_id=subsidy_id, parent_id=parent_id, level=level, name=name)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase(db_session, **kwargs) -> Purchase:
    defaults = dict(
        status="ordered", purchase_contract_type=None, parent_purchase_id=None,
        contract_id=None, contract_number=None, feo_category_id=None,
    )
    defaults.update(kwargs)
    p = Purchase(**defaults)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_framework_head_excluded_from_plan_rows(db_session):
    sub = await _make_subsidy(db_session)
    cat1 = await _make_cat(db_session, sub.id, 1, name="Направление")
    cat2 = await _make_cat(db_session, sub.id, 2, cat1.id, name="Тип")
    cat3 = await _make_cat(db_session, sub.id, 3, cat2.id, name="Статья")

    head = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat3.id,
        purchase_number=1093, status="ordered",
        purchase_contract_type="framework_with_amount",
        item_name="Рамочный договор на СТО",
    )
    order = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat3.id,
        purchase_number=1094, status="paid", parent_purchase_id=head.id,
        item_name="Заказ 1", planned_total_price=50000,
    )

    data = await gather_live_plan_graph_data(db_session, sub.id)

    head_names = {d["name"] for d in data["purchased_by_cat"].get(cat3.id, [])}
    head_names |= {d["name"] for d in data["unlinked_purchases"]}
    assert "Рамочный договор на СТО" not in head_names

    order_names = {d["name"] for d in data["purchased_by_cat"].get(cat3.id, [])}
    order_names |= {d["name"] for d in data["unlinked_purchases"]}
    assert "Заказ 1" in order_names


@pytest.mark.asyncio
async def test_contracts_sheet_head_sums_orders_and_category_path(db_session):
    sub = await _make_subsidy(db_session)
    cat_a = await _make_cat(db_session, sub.id, 3, name="Статья A")
    cat_b = await _make_cat(db_session, sub.id, 3, name="Статья B")

    head = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat_a.id,
        purchase_number=1093, status="ordered",
        purchase_contract_type="framework_with_amount",
        contract_number="2026 СТО", item_name="Рамочный договор",
    )
    order1 = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat_a.id,
        purchase_number=1094, order_number="1", status="paid",
        parent_purchase_id=head.id, planned_total_price=300000, item_name="Заказ 1",
    )
    order2 = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat_a.id,
        purchase_number=1095, order_number="2", status="delivered",
        parent_purchase_id=head.id, planned_total_price=205859.86, item_name="Заказ 2",
    )

    groups = await gather_contracts_sheet_data(db_session, sub.id)
    group = next(g for g in groups if g["head"]["purchase_number"] == 1093)
    h = group["head"]
    orders = group["orders"]

    # Волна 2 (владелец 08.10.2026): голова больше не несёт своё
    # "delivered"/"paid" — только "ordered" (Σ заявок, читает
    # contract_balances); факт — в строках заявок.
    assert h["ordered"] == pytest.approx(300000 + 205859.86)
    delivered_sum = sum(o["delivered"] for o in orders)
    paid_sum = sum(o["paid"] for o in orders)
    assert delivered_sum == pytest.approx(300000 + 205859.86)
    assert paid_sum == pytest.approx(300000.0)
    # Обе заявки в одной статье — у головы та же статья, не «Разные».
    assert h["category_path"] == "Статья A"

    # Разные статьи у заявок → у головы «Разные».
    order2.feo_category_id = cat_b.id
    await db_session.commit()
    groups2 = await gather_contracts_sheet_data(db_session, sub.id)
    group2 = next(g for g in groups2 if g["head"]["purchase_number"] == 1093)
    assert group2["head"]["category_path"] == "Разные"


@pytest.mark.asyncio
async def test_plan_sheet_contract_balance_column_shows_remaining(db_session):
    """Владелец 08.10.2026, часть C: столбец «Остаток по договору, ₽» листа
    «План закупок (по направлениям)» в строке заказа = остаток договора
    (max_amount 1000, заказы 300+200 → остаток 500) — через ЕДИНЫЙ источник
    app.services.contract_balances.contract_balances, не второй расчёт."""
    from app.models.contract import Contract
    from app.services.plan_graph_export_xlsx import build_live_plan_graph_xlsx

    sub = await _make_subsidy(db_session)
    cat1 = await _make_cat(db_session, sub.id, 1, name="Направление")
    cat2 = await _make_cat(db_session, sub.id, 2, cat1.id, name="Тип")
    cat3 = await _make_cat(db_session, sub.id, 3, cat2.id, name="Статья")

    contract = Contract(number="ДОГ-1", contract_type="framework_with_amount", max_amount=1000)
    db_session.add(contract)
    await db_session.commit()
    await db_session.refresh(contract)

    head = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat3.id,
        purchase_number=1, status="ordered",
        purchase_contract_type="framework_with_amount",
        contract_id=contract.id, contract_number=contract.number,
        item_name="Рамочный договор",
    )
    order1 = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat3.id,
        purchase_number=2, order_number="1", status="ordered",
        parent_purchase_id=head.id, planned_total_price=300, item_name="Заказ 1",
    )
    order2 = await _make_purchase(
        db_session, subsidy_id=sub.id, feo_category_id=cat3.id,
        purchase_number=3, order_number="2", status="ordered",
        parent_purchase_id=head.id, planned_total_price=200, item_name="Заказ 2",
    )

    data = await gather_live_plan_graph_data(db_session, sub.id)
    wb = build_live_plan_graph_xlsx(sub, "http://example.test", data)
    ws = wb["План закупок (по направлениям)"]

    headers = {cell.value: idx + 1 for idx, cell in enumerate(ws[3])}
    col = headers["Остаток по договору, ₽"]
    rows = list(ws.iter_rows(min_row=4, values_only=False))

    composition_col = headers["Состав закупки"]
    order1_row = next(r for r in rows if r[composition_col - 1].value == "Заказ 1")
    order2_row = next(r for r in rows if r[composition_col - 1].value == "Заказ 2")

    assert order1_row[col - 1].value == 500.0
    assert order2_row[col - 1].value == 500.0


@pytest.mark.asyncio
async def test_framework_head_without_orders_is_single_row_with_own_facts(db_session):
    """Владелец 09.10.2026, прод ФАДМ 2026_2, 3-й заход — РЕЕ-2026-03110
    (формально "голова" рамочного, но без заявок под ней) должна выводиться
    как разовый договор: Сумма заявки/Поставлено/Оплачено заполнены её
    собственной суммой, не пустые; SUM «Оплачено» по реестру = Σ всех
    оплаченных закупок фикстуры."""
    sub = await _make_subsidy(db_session)
    real_head = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=3095, status="paid",
        purchase_contract_type="framework_cumulative", contract_number="ДОГ-1168",
    )
    order = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=3096, order_number="1",
        status="paid", parent_purchase_id=real_head.id, planned_total_price=1000,
    )
    orphan_head_like = await _make_purchase(
        db_session, subsidy_id=sub.id, purchase_number=3110, status="paid",
        purchase_contract_type="framework_cumulative", contract_number="ДОГ-1168-б",
        planned_total_price=3500,
    )

    groups = await gather_contracts_sheet_data(db_session, sub.id)
    orphan_group = next(g for g in groups if g["head"]["purchase_number"] == 3110)
    assert orphan_group["orders"] == []
    h = orphan_group["head"]
    assert h.get("single_sum") == pytest.approx(3500.0)
    assert h.get("single_paid") == pytest.approx(3500.0)
    assert h.get("single_delivered") == pytest.approx(3500.0)

    total_paid = sum(
        (g["head"].get("single_paid") or 0.0) + sum(o["paid"] for o in g["orders"])
        for g in groups
    )
    assert total_paid == pytest.approx(1000.0 + 3500.0)
