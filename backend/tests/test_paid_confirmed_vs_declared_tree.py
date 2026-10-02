# -*- coding: utf-8 -*-
"""Решение владельца (02.10.2026): «Оплату может отметить сам закупщик... Нужна
отдельная величина — оплата подтверждена выпиской». Проверяет, что дерево ФЭО
(compute_feo_plan_tree) отдаёт по узлу ДВА поля — paid_marked («Оплачено (по
отметке)» = Σ payment_amount + payment_amount_declared) и paid_confirmed
(«Подтверждено выпиской» = Σ payment_amount), собранные
app.services.feo_plan_payments.paid_consumption_by_category и сложенные в
compute_feo_plan_tree так же, как существующие суммы узла (own + rollup детей).

Переиспользует фабрики _make_subsidy/_make_category из test_feo_plan_tree_scenarios.py
(ПРАВИЛО №6 — вторая копия не заводится).
"""
from decimal import Decimal

import pytest

from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan import compute_feo_plan_tree
from app.services.purchase_payments import recompute_purchase_payments
from tests.test_feo_plan_tree_scenarios import _make_category, _make_subsidy


async def _make_purchase_with_payment(
    db_session, subsidy_id, feo_category_id, amount, status="delivered",
):
    """Закупка с ОДНОЙ позицией (без привязки к плановой позиции — план узла
    держится на уровне категории, см. test_money_committed.py::_make_unlinked_purchase),
    статус 'delivered' — PLANNED_STATUSES, в т.ч. подходит под авто-переход
    recompute_purchase_payments (тот требует 'delivered' для перехода в 'paid',
    но здесь нас интересует только payment_amount/payment_amount_declared, сам
    статус после пересчёта не важен для дерева — PLANNED_STATUSES включает и
    'paid', и 'delivered')."""
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Товар",
        status=status,
        contract_price=Decimal(str(amount)),
        total_nmck=Decimal(str(amount)),
        nmck=Decimal(str(amount)),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Товар",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal(str(amount)),
        total_price=Decimal(str(amount)),
        feo_category_id=feo_category_id,
        feo_planned_item_id=None,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_paid_marked_vs_confirmed_in_feo_tree(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(
        db_session, subsidy.id, name="Категория с двумя закупками",
        budget=Decimal("1000"),
    )

    # Закупка 1 — платёж подтверждён выпиской (100).
    purchase_confirmed = await _make_purchase_with_payment(db_session, subsidy.id, leaf.id, 100)
    pay_confirmed = Payment(
        purchase_id=purchase_confirmed.id,
        amount=Decimal("100"),
        payment_source="statement",
        confirmed_by_statement=True,
        matched_confirmed=True,
    )
    db_session.add(pay_confirmed)
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase_confirmed.id)
    await db_session.commit()

    # Закупка 2 — ручная отметка, НЕ подтверждена выпиской (50).
    purchase_declared = await _make_purchase_with_payment(db_session, subsidy.id, leaf.id, 50)
    pay_declared = Payment(
        purchase_id=purchase_declared.id,
        amount=Decimal("50"),
        payment_source="manual",
        confirmed_by_statement=False,
    )
    db_session.add(pay_declared)
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase_declared.id)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["paid_marked"] == pytest.approx(150.0)
    assert node["paid_confirmed"] == pytest.approx(100.0)

    # Теперь ручной платёж закупки 2 подтверждается выпиской — paid_confirmed
    # должен подняться до 150 (paid_marked остаётся 150 — тот же платёж,
    # просто статус подтверждения поменялся).
    pay_declared.confirmed_by_statement = True
    pay_declared.payment_source = "statement"
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase_declared.id)
    await db_session.commit()

    tree_after = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_after = tree_after[leaf.id]
    assert node_after["paid_marked"] == pytest.approx(150.0)
    assert node_after["paid_confirmed"] == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_paid_marked_visible_for_planned_item_linked_purchase(db_session, test_org):
    """Дефект приёмки «Импорта факта» (02.10.2026): paid_consumption_by_category
    вызывалась с exclude_planned_item_linked=True без какого-либо довеска для
    привязанных к плановым позициям строк (в отличие от committed/leaf_items_
    committed_contribution, у плановых позиций нет собственной «оплаты») —
    «Оплачено» уходило в 0 для ЛЮБОЙ закупки с привязкой к активной плановой
    позиции СВОЕЙ категории. Проверяет, что после фикса (exclude_planned_item_
    linked=False в вызове из feo_plan_tree.py) оплата такой позиции видна в
    узле, без двойного счёта (единственная строка — единственный вклад)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(
        db_session, subsidy.id, name="Категория с привязанной позицией",
        budget=Decimal("1000"),
    )
    planned_item = FeoPlannedItem(
        feo_category_id=leaf.id,
        name="Плановая позиция",
        amount=Decimal("200"),
        is_active=True,
    )
    db_session.add(planned_item)
    await db_session.commit()
    await db_session.refresh(planned_item)

    purchase = Purchase(
        subsidy_id=subsidy.id,
        feo_category_id=leaf.id,
        item_name="Товар",
        status="delivered",
        contract_price=Decimal("80"),
        total_nmck=Decimal("80"),
        nmck=Decimal("80"),
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id,
        item_name="Товар",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal("80"),
        total_price=Decimal("80"),
        feo_category_id=leaf.id,
        feo_planned_item_id=planned_item.id,
        over_plan=False,
    )
    db_session.add(item)
    await db_session.commit()

    pay = Payment(
        purchase_id=purchase.id,
        amount=Decimal("80"),
        payment_source="manual",
        confirmed_by_statement=False,
    )
    db_session.add(pay)
    await db_session.commit()
    await recompute_purchase_payments(db_session, purchase.id)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["paid_marked"] == pytest.approx(80.0)
