"""app.services.subsidy_summary_by_kind — лист «Сводная» экспорта плана-
графика (Задача А, владелец 07.10.2026) теперь читает уже готовые числа с
экрана субсидии, вместо второго расчёта. Тесты проверяют ИМЕННО инварианты из
задания: Σ по видам likely/nice/monthly обязаны совпадать с тем, что уже
показывает subsidy_money_summary (carточка «Можно перераспределить») и
contracted_not_ordered_need_level_split — не вторая формула, а разрез тех же
чисел по виду позиции.

Переиспользует фабрики test_feo_plan_tree_scenarios.py/test_money_committed.py
(ПРАВИЛО №6 — вторая копия фабрик не заводится)."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.stage_cumulative import (
    contracted_not_ordered_need_level_split,
    contracted_not_ordered_split_by_kind,
)
from app.services.subsidy_money_summary import subsidy_money_summary
from app.services.subsidy_paid_breakdown import paid_breakdown_by_subsidy
from app.services.delivered_unpaid_residual import delivered_unpaid_residual_by_subsidy
from app.services.subsidy_summary_by_kind import subsidy_summary_by_kind
from app.services.type_totals import subsidy_type_totals
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase

_KINDS = ("goods", "services", "payroll", "unspecified")


async def _make_reserved_child(db_session, subsidy_id, cat_id, planned_item_id, amount, item_type, need_level=None):
    """Заказ рамочного договора в статусе 'contracted' (договор заключён,
    заказ как отдельная закупка ещё не оформлен) — тот самый
    reserved_child_predicate(): status='contracted' + parent_purchase_id НЕ
    NULL. parent_purchase_id указывает на отдельную «голову» (сама голова
    бизнес-смысла в этом тесте не несёт, нужен только факт существования
    родителя под FK)."""
    head = Purchase(subsidy_id=subsidy_id, item_name="Рамочный договор (голова)", status="contracted")
    db_session.add(head)
    await db_session.flush()

    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=cat_id, item_name="Заказ рамочного договора",
        status="contracted", parent_purchase_id=head.id,
        contract_price=Decimal(str(amount)), item_type=item_type,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Заказ рамочного договора", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal(str(amount)), total_price=Decimal(str(amount)),
        feo_category_id=cat_id, feo_planned_item_id=planned_item_id, item_type=item_type,
    )
    db_session.add(pi)
    await db_session.commit()
    if need_level is not None:
        from app.models.feo_planned_item import FeoPlannedItem
        fpi = await db_session.get(FeoPlannedItem, planned_item_id)
        fpi.need_level = need_level
        await db_session.commit()
    return p


async def _make_paid_purchase(db_session, subsidy_id, cat_id, amount, item_type):
    """Закупка «по отметке оплачена» (subsidy_paid_breakdown читает
    payment_amount_declared), чтобы вызвать ненулевой paid-показатель."""
    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=cat_id, item_name="Оплаченная позиция",
        status="delivered", item_type=item_type, payment_amount_declared=Decimal(str(amount)),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Оплаченная позиция", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal(str(amount)), total_price=Decimal(str(amount)),
        feo_category_id=cat_id, item_type=item_type,
    )
    db_session.add(pi)
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_subsidy_summary_by_kind_sums_match_money_summary(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)

    cat_goods = await _make_category(db_session, subsidy.id, name="Товары", budget=Decimal("500000"))
    item_goods_nice = await _make_planned_item(db_session, cat_goods.id, "Товар хотелось бы", 1, 200_000)
    item_goods_nice.need_level = "nice_to_have"
    item_goods_likely = await _make_planned_item(db_session, cat_goods.id, "Товар скорее всего", 1, 300_000)
    await db_session.commit()

    cat_services = await _make_category(db_session, subsidy.id, name="Услуги", budget=Decimal("400000"))
    item_services = await _make_planned_item(db_session, cat_services.id, "Услуга", 1, 400_000)

    # Законтрактовано (ordered) по услуге, остаток — raw likely услуг.
    await _make_linked_purchase(
        db_session, subsidy.id, cat_services.id, item_services.id, 1, 150_000, status="ordered",
    )
    p_services = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.feo_planned_item_id == item_services.id)
    )).scalar_one()
    p_services.item_type = "услуга"
    await db_session.commit()

    # «Договор без заказа» (reserved child) на товар «скорее всего» — часть
    # его плана уходит в monthly, не в likely.
    await _make_reserved_child(
        db_session, subsidy.id, cat_goods.id, item_goods_likely.id, 100_000, "товар",
    )

    summary = await subsidy_summary_by_kind(db_session, subsidy.id)
    assert set(summary.keys()) == set(_KINDS)

    money = (await subsidy_money_summary(db_session, [subsidy.id]))[subsidy.id]
    contracted_split = await contracted_not_ordered_need_level_split(db_session, subsidy_ids=[subsidy.id])
    contracted_total = (
        contracted_split[subsidy.id]["nice"] + contracted_split[subsidy.id]["likely"]
    )

    sum_likely = sum(v["likely"] for v in summary.values())
    sum_nice = sum(v["nice"] for v in summary.values())
    sum_monthly = sum(v["monthly"] for v in summary.values())

    assert sum_likely == pytest.approx(money["not_committed_likely"], abs=0.01)
    assert sum_nice == pytest.approx(money["not_committed_nice"], abs=0.01)
    assert sum_monthly == pytest.approx(contracted_total, abs=0.01)

    # feo/plan/committed — ЧИТАЮТСЯ, не пересчитываются (совпадают byte-в-byte
    # с subsidy_type_totals/committed_by_kind).
    tt = (await subsidy_type_totals(db_session, [subsidy.id]))[subsidy.id]
    for k in _KINDS:
        assert summary[k]["feo"] == pytest.approx(tt[f"feo_{k}"], abs=0.01)
        assert summary[k]["plan"] == pytest.approx(tt[f"plan_{k}"], abs=0.01)
        assert summary[k]["committed"] == pytest.approx(money["committed_by_kind"][k], abs=0.01)


@pytest.mark.asyncio
async def test_subsidy_summary_by_kind_paid_and_delivered_unpaid_wired(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat = await _make_category(db_session, subsidy.id, name="Товары", budget=Decimal("100000"))

    await _make_paid_purchase(db_session, subsidy.id, cat.id, 70_000, "товар")

    summary = await subsidy_summary_by_kind(db_session, subsidy.id)
    paid_map = (await paid_breakdown_by_subsidy(db_session, [subsidy.id])).get(subsidy.id) or {}
    du_map = (await delivered_unpaid_residual_by_subsidy(db_session, [subsidy.id])).get(subsidy.id) or {}
    declared_by_kind = paid_map.get("declared_by_kind") or {}
    du_by_kind = du_map.get("by_kind") or {}

    for k in ("goods", "services", "unspecified"):
        assert summary[k]["paid"] == pytest.approx(declared_by_kind.get(k, 0.0), abs=0.01)
        assert summary[k]["delivered_unpaid"] == pytest.approx(du_by_kind.get(k, 0.0), abs=0.01)
    assert summary["payroll"]["paid"] == 0.0
    assert summary["goods"]["paid"] == pytest.approx(70_000.0, abs=0.01)


@pytest.mark.asyncio
async def test_contracted_not_ordered_split_by_kind_sums_match_need_level_split(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat_goods = await _make_category(db_session, subsidy.id, name="Товары", budget=Decimal("300000"))
    item_goods = await _make_planned_item(db_session, cat_goods.id, "Товар", 1, 200_000)
    cat_services = await _make_category(db_session, subsidy.id, name="Услуги", budget=Decimal("300000"))
    item_services = await _make_planned_item(db_session, cat_services.id, "Услуга", 1, 200_000)
    item_services.need_level = "nice_to_have"
    await db_session.commit()

    await _make_reserved_child(db_session, subsidy.id, cat_goods.id, item_goods.id, 80_000, "товар")
    await _make_reserved_child(db_session, subsidy.id, cat_services.id, item_services.id, 50_000, "услуга")

    split_by_kind = await contracted_not_ordered_split_by_kind(db_session, subsidy.id)
    need_level_split = (await contracted_not_ordered_need_level_split(db_session, subsidy_ids=[subsidy.id]))[subsidy.id]

    sum_nice = sum(v["nice"] for v in split_by_kind.values())
    sum_likely = sum(v["likely"] for v in split_by_kind.values())
    assert sum_nice == pytest.approx(need_level_split["nice"], abs=0.01)
    assert sum_likely == pytest.approx(need_level_split["likely"], abs=0.01)
    assert split_by_kind["services"]["nice"] == pytest.approx(50_000.0, abs=0.01)
    assert split_by_kind["goods"]["likely"] == pytest.approx(80_000.0, abs=0.01)
