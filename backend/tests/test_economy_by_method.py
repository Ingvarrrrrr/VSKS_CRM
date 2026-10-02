"""GET /api/dashboard/economy-by-method (PLAN.md шаг 4, п. F, ревью 02.10.2026,
ИСПРАВЛЕНО 02.10.2026 — база экономии переведена на плановую позицию
FeoPlannedItem, см. app.services.purchase_economy docstring).

Расчёт целиком в app.services.purchase_economy.purchase_economy_by_method
(ПРАВИЛО №6) — этот тест проверяет только эндпоинт: форму ответа (method/
competitive_form/label/purchases/plan/fact/economy/economy_pct/
no_planned_price_items/unmeasured_by_reason/is_total) и группировку single vs
competitive.

ИСПРАВЛЕНО 02.10.2026 (приёмка владельца, дубль строки «Конкурентная»):
итоговая строка-псевдоспособ ("competitive", None) добавляется ТОЛЬКО когда
у конкурентных закупок ≥ 2 разных competitive_form — при одной форме раньше
выводились ОБЕ строки с одинаковыми числами.
"""
from decimal import Decimal

import pytest

from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase, _make_unlinked_purchase


@pytest.mark.asyncio
async def test_economy_by_method_groups_single_and_competitive(
    client, superadmin_headers, db_session, test_org,
):
    """Одна конкурентная форма (auction) — ОДНА строка, без дублирующего
    псевдоспособа ("competitive", None)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Способы закупки", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    # single: 100 000 план, 90 000 факт -> экономия 10 000.
    single_purchase, single_item = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, 1, 90_000, planned_total=Decimal("100000"),
    )
    single_purchase.purchase_method = "single"
    db_session.add(single_purchase)

    # competitive/auction: 100 000 план, 95 000 факт -> экономия 5 000.
    comp_purchase, comp_item = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, 1, 95_000, planned_total=Decimal("100000"),
    )
    comp_purchase.purchase_method = "competitive"
    comp_purchase.competitive_form = "auction"
    db_session.add(comp_purchase)
    await db_session.commit()

    resp = await client.get(
        "/api/dashboard/economy-by-method",
        params={"subsidy_id": subsidy.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    groups = {(g["method"], g["competitive_form"]): g for g in body}

    single_g = groups[("single", None)]
    assert single_g["purchases"] == 1
    assert single_g["plan"] == pytest.approx(100_000.0)
    assert single_g["fact"] == pytest.approx(90_000.0)
    assert single_g["economy"] == pytest.approx(10_000.0)
    assert single_g["label"] == "Единственный поставщик"
    assert single_g["no_planned_price_items"] == 0
    assert single_g["is_total"] is False

    auction_g = groups[("competitive", "auction")]
    assert auction_g["purchases"] == 1
    assert auction_g["economy"] == pytest.approx(5_000.0)
    assert auction_g["label"] == "Конкурентная: аукцион"
    assert auction_g["is_total"] is False

    # ИСПРАВЛЕНО: единственная форма конкурентной закупки -> НЕТ дублирующей
    # строки-итога ("competitive", None) с теми же числами.
    assert ("competitive", None) not in groups
    assert len(body) == 2


@pytest.mark.asyncio
async def test_economy_by_method_two_competitive_forms_add_total_row(
    client, superadmin_headers, db_session, test_org,
):
    """ДВЕ разных competitive_form -> обе подстроки + строка-итог
    «Конкурентная — всего» (is_total=True) с суммой их чисел."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Способы закупки", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    # auction: 100 000 план, 95 000 факт -> экономия 5 000.
    auction_purchase, _ = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, 1, 95_000, planned_total=Decimal("100000"),
    )
    auction_purchase.purchase_method = "competitive"
    auction_purchase.competitive_form = "auction"
    db_session.add(auction_purchase)

    # tender: 100 000 план, 90 000 факт -> экономия 10 000.
    tender_purchase, _ = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, 1, 90_000, planned_total=Decimal("100000"),
    )
    tender_purchase.purchase_method = "competitive"
    tender_purchase.competitive_form = "tender"
    db_session.add(tender_purchase)
    await db_session.commit()

    resp = await client.get(
        "/api/dashboard/economy-by-method",
        params={"subsidy_id": subsidy.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200
    groups = {(g["method"], g["competitive_form"]): g for g in resp.json()}

    assert groups[("competitive", "auction")]["is_total"] is False
    assert groups[("competitive", "tender")]["is_total"] is False

    comp_total = groups[("competitive", None)]
    assert comp_total["is_total"] is True
    assert comp_total["label"] == "Конкурентная — всего"
    assert comp_total["purchases"] == 2
    assert comp_total["economy"] == pytest.approx(15_000.0)


@pytest.mark.asyncio
async def test_economy_by_method_no_planned_price_items_counted(
    client, superadmin_headers, db_session, test_org,
):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Без плановой цены", budget=Decimal("1000000"))

    purchase, item = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 50_000, status="contracted")
    purchase.purchase_method = "advance"
    item.planned_total = None
    db_session.add_all([purchase, item])
    await db_session.commit()

    resp = await client.get(
        "/api/dashboard/economy-by-method",
        params={"subsidy_id": subsidy.id},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200
    groups = {(g["method"], g["competitive_form"]): g for g in resp.json()}
    advance_g = groups[("advance", None)]
    assert advance_g["no_planned_price_items"] == 1
    # ИСПРАВЛЕНО 02.10.2026 (приёмка ФАДМ_2026 — группа без НИ ОДНОЙ измеренной
    # позиции показывала 0 ₽, читалось как «экономии нет»): plan/fact/economy
    # группы — null, когда не измерена ни одна закупка группы (не Σ по
    # пустому множеству = 0).
    assert advance_g["plan"] is None
    assert advance_g["fact"] is None
    assert advance_g["economy"] is None
    assert advance_g["economy_pct"] is None
    assert advance_g["label"] == "Авансовый отчёт"
    # ИСПРАВЛЕНО 02.10.2026 (база экономии — плановая позиция): позиция без
    # привязки к FeoPlannedItem — причина 'unlinked', не 'no_plan_price'.
    assert advance_g["unmeasured_by_reason"]["unlinked"] == 1
    assert advance_g["unmeasured_by_reason"]["no_plan_price"] == 0
