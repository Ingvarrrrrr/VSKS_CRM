"""Контрольные примеры владельца (02.10.2026, план
.planning/quick/2026-10-02-money-redistribution/PLAN.md) для модуля
«законтрактовано» (app.services.committed_amounts) и шага 2 («экономия
возвращается в Свободно», app.services.feo_plan_tree.compute_feo_plan_tree) +
шага 3 («экономия по закупке — только расчёт», app.services.purchase_economy).

Переиспользует фабрики из test_feo_plan_tree_scenarios.py (_make_subsidy/
_make_category/_make_planned_item) — ПРАВИЛО №6, вторая копия не заводится.
"""
from decimal import Decimal

import pytest

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.committed_amounts import committed_by_purchase, is_purchase_committed
from app.services.feo_plan import compute_feo_plan_tree
from app.services.purchase_economy import purchase_economy_bulk, purchase_economy_by_subsidy, purchase_economy_one
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


async def _make_linked_purchase(
    db_session, subsidy_id, feo_category_id, feo_planned_item_id,
    quantity, contract_price, status="contracted", planned_total=Decimal("100000"),
    purchase_contract_type=None,
):
    """Закупка с ОДНОЙ позицией, привязанной к плановой позиции
    (feo_planned_item_id) — статус/цена задаются напрямую (не через цепочку
    согласования заявки), т.к. тест проверяет только формулу «законтрактовано»/
    «экономия», а не сам процесс согласования."""
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Бензопила",
        status=status,
        contract_price=Decimal(str(contract_price)),
        total_nmck=Decimal(str(contract_price)),
        nmck=Decimal(str(contract_price)),
        purchase_contract_type=purchase_contract_type,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Бензопила",
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(contract_price)) / Decimal(str(quantity)),
        total_price=Decimal(str(contract_price)),
        planned_total=planned_total,
        feo_category_id=feo_category_id,
        feo_planned_item_id=feo_planned_item_id,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    await db_session.refresh(pi)
    return p, pi


async def _make_unlinked_purchase(
    db_session, subsidy_id, feo_category_id, quantity, contract_price,
    status="contracted", purchase_contract_type=None,
):
    """Та же закупка, но БЕЗ привязки к плановой позиции (feo_planned_item_id=None)
    — план узла держится на уровне категории (см. docstring теста 4)."""
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Бензопила",
        status=status,
        contract_price=Decimal(str(contract_price)),
        total_nmck=Decimal(str(contract_price)),
        nmck=Decimal(str(contract_price)),
        purchase_contract_type=purchase_contract_type,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Бензопила",
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(contract_price)) / Decimal(str(quantity)),
        total_price=Decimal(str(contract_price)),
        feo_category_id=feo_category_id,
        feo_planned_item_id=None,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(p)
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_1_single_item_not_closed_full_reserve(db_session, test_org):
    """Пример владельца 1: «Бензопила» 2×100 000; закупка 1 шт по договору
    101 000 (contracted), вторая не законтрактована → plan узла 200 000,
    committed 101 000, savings позиции = null (не закрыта), экономия закупки −1 000."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Бензопила (лист)", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    purchase, item = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, quantity=1, contract_price=101_000,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 200_000.0
    assert node["plan"] == 200_000.0
    assert node["committed"] == 101_000.0

    economy = await purchase_economy_one(db_session, purchase.id)
    assert economy == Decimal("-1000.00")


@pytest.mark.asyncio
async def test_2_both_items_closed_releases_savings(db_session, test_org):
    """Пример владельца 2: обе позиции законтрактованы (101 000 + 80 000) →
    plan узла 181 000 (Свободно выросло на 19 000), committed 181 000, экономия
    закупок суммарно 19 000."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Бензопила (лист)", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    p1, _i1 = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 101_000)
    p2, _i2 = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 80_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 181_000.0
    assert node["plan"] == 181_000.0
    assert node["committed"] == 181_000.0

    econ = await purchase_economy_bulk(db_session, [p1.id, p2.id])
    total_economy = sum(b["economy"] for b in econ.values() if b["economy"] is not None)
    assert total_economy == Decimal("19000.00")


@pytest.mark.asyncio
async def test_3_framework_head_not_committed_only_orders_are(db_session, test_org):
    """Пример владельца: рамочный договор — сам договор (contracted) НЕ
    занимает денег, занимает только заказ (ordered/delivered/paid)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Рамочный (лист)", budget=Decimal("1000000"))

    purchase, _item = await _make_unlinked_purchase(
        db_session, subsidy.id, leaf.id, quantity=1, contract_price=350_000,
        status="contracted", purchase_contract_type="framework_cumulative",
    )
    assert is_purchase_committed(purchase) is False
    committed = await committed_by_purchase(db_session, [purchase.id])
    assert committed[purchase.id] == 0.0

    purchase.status = "ordered"
    await db_session.commit()
    await db_session.refresh(purchase)
    assert is_purchase_committed(purchase) is True
    committed = await committed_by_purchase(db_session, [purchase.id])
    assert committed[purchase.id] == 350_000.0


@pytest.mark.asyncio
async def test_4_unlinked_purchases_release_savings_at_contracted(db_session, test_org):
    """Пример владельца 2, но для закупок БЕЗ привязки к плановой позиции (план
    держится на категории через FeoPlannedItem-ориентир количества, сами
    закупки заведены напрямую на категорию) — высвобождение срабатывает уже на
    «Договор» (contracted), не дожидаясь «Заказано» (порог committed, не
    ORDERED_STATUSES, см. committed_amounts.py)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Бензопила (категория, план)", budget=Decimal("1000000"))
    # Плановая позиция задаёт ОРИЕНТИР количества/суммы узла, но закупки ниже
    # на неё НЕ ссылаются (feo_planned_item_id=None) — «план — категория».
    await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    p1, _i1 = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 101_000, status="contracted")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan"] == 200_000.0, "одна из двух единиц ещё не законтрактована — план полностью резервируется"

    p2, _i2 = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 80_000, status="contracted")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan"] == 181_000.0, "обе единицы законтрактованы (contracted) — план замещён законтрактованной суммой"
    assert node["committed"] == 181_000.0


@pytest.mark.asyncio
async def test_5_monthly_item_never_substituted(db_session, test_org):
    """Ежемесячная плановая позиция (payment_mode='monthly') полностью
    законтрактована по количеству — план НЕ замещается (остаётся
    зарезервированным целиком), в отличие от одноразовой (one_time)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Ежемесячная услуга", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Аренда", 2, 200_000)
    fpi.payment_mode = "monthly"
    db_session.add(fpi)
    await db_session.commit()

    p1, _i1 = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 101_000)
    p2, _i2 = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 80_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 200_000.0, (
        "ежемесячная позиция не участвует в замещении savings — остаётся "
        "зарезервированной целиком, даже когда количество полностью законтрактовано"
    )

    # Шаг 3 плана (экономия, ИСПРАВЛЕНО 02.10.2026): ежемесячные позиции —
    # 'monthly', экономией НЕ меряются (п.2 докстринга purchase_economy.py).
    econ = await purchase_economy_bulk(db_session, [p1.id, p2.id])
    assert econ[p1.id]["economy"] is None
    assert econ[p1.id]["unmeasured_by_reason"]["monthly"] == 1
    assert econ[p2.id]["unmeasured_by_reason"]["monthly"] == 1


@pytest.mark.asyncio
async def test_6_economy_unlinked_item_is_not_zero(db_session, test_org):
    """ИСПРАВЛЕНО 02.10.2026 (база экономии — плановая позиция, не
    planned_total): позиция БЕЗ привязки к FeoPlannedItem — НЕ меряется (НЕ
    0), причина 'unlinked', не входит в сумму экономии закупки."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Без плановой цены", budget=Decimal("1000000"))

    purchase, _item = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 50_000, status="contracted")
    db_session.add(_item)
    await db_session.commit()

    bucket = (await purchase_economy_bulk(db_session, [purchase.id]))[purchase.id]
    assert bucket["economy"] is None, "нет ни одной измеримой позиции — считать нечего (не 0)"
    assert bucket["unmeasured_by_reason"]["unlinked"] == 1
    assert bucket["unmeasured_total"] == 1

    economy = await purchase_economy_one(db_session, purchase.id)
    assert economy is None


@pytest.mark.asyncio
async def test_6b_economy_no_plan_price_when_planned_item_has_no_quantity_or_unit_price(db_session, test_org):
    """Привязана к активной FeoPlannedItem, но у НЕЁ нет ни unit_price, ни
    (quantity>0 и amount) — нечем посчитать базу → 'no_plan_price', НЕ
    'unlinked' (привязка валидна, просто нечем мерить)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Плановая позиция без числа", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 0, 50_000)  # quantity=0 → доля не считается

    purchase, _item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 50_000)

    bucket = (await purchase_economy_bulk(db_session, [purchase.id]))[purchase.id]
    assert bucket["economy"] is None
    assert bucket["unmeasured_by_reason"]["no_plan_price"] == 1
    assert bucket["unmeasured_by_reason"]["unlinked"] == 0


@pytest.mark.asyncio
async def test_6c_economy_unit_price_base_used_when_set(db_session, test_org):
    """FeoPlannedItem.unit_price задан — база = unit_price × PurchaseItem.quantity
    (приоритет над amount/quantity-долей)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Цена за единицу", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 3, 300_000)
    fpi.unit_price = Decimal("90000")
    db_session.add(fpi)
    await db_session.commit()

    purchase, _item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 2, 170_000)

    bucket = (await purchase_economy_bulk(db_session, [purchase.id]))[purchase.id]
    assert bucket["economy"] == Decimal("10000.00"), "база 90 000×2=180 000, факт 170 000 → экономия 10 000"


@pytest.mark.asyncio
async def test_6d_composite_planned_item_economy_grouped_by_purchase(db_session, test_org):
    """Составная плановая позиция (is_composite=True, напр. «проживание» +
    «питание» на то же количество человек) — количество группы строк ОДНОЙ
    закупки = MAX (не Σ), факт группы = Σ строк, экономия считается на
    уровне (закупка, позиция), не по отдельным строкам."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Проживание и питание", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Проживание+питание", 10, 130_000)
    fpi.is_composite = True
    db_session.add(fpi)
    await db_session.commit()

    purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=leaf.id, item_name="Проживание и питание",
        status="contracted", contract_price=Decimal("115000"), total_nmck=Decimal("115000"),
        nmck=Decimal("115000"),
    )
    db_session.add(purchase)
    await db_session.flush()
    room = PurchaseItem(
        purchase_id=purchase.id, item_name="Проживание", quantity=Decimal("10"), unit="чел.",
        unit_price=Decimal("6000"), total_price=Decimal("60000"),
        feo_category_id=leaf.id, feo_planned_item_id=fpi.id, over_plan=False,
    )
    food = PurchaseItem(
        purchase_id=purchase.id, item_name="Питание", quantity=Decimal("10"), unit="чел.",
        unit_price=Decimal("5500"), total_price=Decimal("55000"),
        feo_category_id=leaf.id, feo_planned_item_id=fpi.id, over_plan=False,
    )
    db_session.add_all([room, food])
    await db_session.commit()

    bucket = (await purchase_economy_bulk(db_session, [purchase.id]))[purchase.id]
    assert bucket["economy"] == Decimal("15000.00"), "база 130 000×10/10=130 000, факт 60 000+55 000=115 000"
    assert bucket["items_considered"] == 2, "ДВЕ строки группы, но ОДНА экономия на группу"
    assert bucket["unmeasured_total"] == 0


@pytest.mark.asyncio
async def test_7_missing_fact_counts_committed_sum_not_quantity(db_session, test_org):
    """ИСПРАВЛЕНИЕ #1 (ревью 02.10.2026): позиция 2×100k, обе закупки
    contracted, у ОДНОЙ нет ни contract_price, ни ContractItem (фактическая
    сумма неизвестна) → план узла ОСТАЁТСЯ 200 000 (количество не набрано —
    позиция без факта не закрывает план), но committed = 101 000 (с фактом) +
    100 000 (planned_total — позиция уже занята договором) = 201 000, и
    committed_missing_fact_items = 1."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Бензопила (лист)", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)

    p1, _i1 = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 101_000)
    # Вторая — "законтрактована", но без суммы договора (владелец забыл внести
    # contract_price, ContractItem тоже не заведён).
    p2, i2 = await _make_linked_purchase(
        db_session, subsidy.id, leaf.id, fpi.id, 1, 1, planned_total=Decimal("100000"),
    )
    p2.contract_price = None
    p2.total_nmck = None
    p2.nmck = None
    db_session.add(p2)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan"] == 200_000.0, "количество не набрано (строка без факта не закрывает позицию) — план резервируется целиком"
    assert node["committed"] == pytest.approx(201_000.0), "101 000 (факт) + 100 000 (planned_total строки без факта)"

    from app.services.committed_amounts import committed_by_planned_item
    by_item = await committed_by_planned_item(db_session, [fpi.id])
    assert by_item[fpi.id]["quantity"] == 1.0, "количество строки без факта НЕ засчитано"
    assert by_item[fpi.id]["missing_fact_items"] == 1

    # Шаг 3 плана (экономия, ИСПРАВЛЕНО 02.10.2026): строка без факта — 'no_fact',
    # причём ПЕРЕД классификацией по привязке (нечем сравнивать, не
    # учитывается в экономии вообще — ни числом, ни причиной 'unlinked').
    econ = await purchase_economy_bulk(db_session, [p1.id, p2.id])
    assert econ[p1.id]["economy"] == Decimal("-1000.00"), "база 200000×1/2=100000, факт 101000"
    assert econ[p2.id]["economy"] is None
    assert econ[p2.id]["unmeasured_by_reason"]["no_fact"] == 1


@pytest.mark.asyncio
async def test_8_over_plan_included_in_committed_total_and_economy(db_session, test_org):
    """ИСПРАВЛЕНИЕ #2 (ревью 02.10.2026) + шаг 3 ИСПРАВЛЕНО (02.10.2026, база
    экономии — плановая позиция, не planned_total): над-плановая (over_plan=
    true) позиция — реальные деньги по договору, входит в ИТОГОВОЕ
    «законтрактовано» узла (committed), но НЕ участвует в замещении плана
    (plan узла не трогается над-плановой суммой). Экономия над-плановой
    строки считается ПО ПРАВИЛУ 1 (как у обычной), если она ПРИВЯЗАНА к
    плановой позиции (переплата видна отрицательной экономией); непривязанная
    над-плановая строка — 'unlinked' (не измеряется), как и везде."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Над планом", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 1, 100_000)
    fpi.unit_price = Decimal("100000")
    db_session.add(fpi)
    await db_session.commit()

    purchase, _item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 100_000)
    over_purchase, over_item = await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 90_000)
    over_item.over_plan = True
    db_session.add(over_item)
    unlinked_over_purchase, unlinked_over_item = await _make_unlinked_purchase(
        db_session, subsidy.id, leaf.id, quantity=1, contract_price=20_000, status="contracted",
    )
    unlinked_over_item.over_plan = True
    db_session.add(unlinked_over_item)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan"] == 100_000.0, "над-плановые позиции не расширяют план узла"
    assert node["committed"] == pytest.approx(210_000.0), (
        "100 000 (план) + 90 000 (над-план, привязан) + 20 000 (над-план, непривязан)"
    )

    econ = await purchase_economy_bulk(db_session, [purchase.id, over_purchase.id, unlinked_over_purchase.id])
    assert econ[purchase.id]["economy"] == Decimal("0.00")
    assert econ[over_purchase.id]["economy"] == Decimal("10000.00"), "план (unit_price) 100 000 − факт над-плана 90 000"
    assert econ[unlinked_over_purchase.id]["economy"] is None, "непривязана — не измеряется"
    assert econ[unlinked_over_purchase.id]["unmeasured_by_reason"]["unlinked"] == 1


@pytest.mark.asyncio
async def test_9_dashboard_invariant_remaining_plus_planned_not_committed_eq_redistributable(
    client, superadmin_headers, db_session, test_org,
):
    """Контракт API п. A (PLAN.md шаг 1-2): инвариант remaining +
    planned_not_committed == redistributable на GET /api/dashboard/charts
    subsidy_stats, для субсидии с и без законтрактованной позиции."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Инвариант", budget=Decimal("1000000"))
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 2, 200_000)
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 101_000)

    resp = await client.get("/api/dashboard/charts", headers=superadmin_headers)
    assert resp.status_code == 200
    stats = {s["id"]: s for s in resp.json()["subsidy_stats"]}
    row = stats[subsidy.id]
    assert row["committed"] == pytest.approx(101_000.0)
    assert row["remaining"] + row["planned_not_committed"] == pytest.approx(row["redistributable"])


@pytest.mark.asyncio
async def test_10_economy_total_null_when_subsidy_has_no_measured_purchases(db_session, test_org):
    """Приёмка по скриншотам ФАДМ_2026 (02.10.2026): субсидия, где ВСЕ
    законтрактованные позиции НЕ привязаны к плановой позиции (unlinked) —
    economy_total=None (нечего сравнивать ни по одной позиции), не 0 —
    0 читается как «экономии нет», а на деле «не посчитано» (purchase_economy.py
    docstring, GET /api/dashboard/charts subsidy_stats). Как только появляется
    хотя бы одна измеренная закупка — economy_total снова число."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Без привязки", budget=Decimal("1000000"))

    p1, i1 = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 50_000, status="contracted")
    p2, i2 = await _make_unlinked_purchase(db_session, subsidy.id, leaf.id, 1, 30_000, status="contracted")
    db_session.add_all([p1, i1, p2, i2])
    await db_session.commit()

    res = await purchase_economy_by_subsidy(db_session, [subsidy.id])
    row = res[subsidy.id]
    assert row["economy_total"] is None, "ни одна позиция не измерена — Σ пустого множества, не 0"
    assert row["economy_no_planned_price_items"] == 2
    assert row["economy_unmeasured_by_reason"]["unlinked"] == 2

    # Добавляем ОДНУ измеренную (привязанную) закупку в ту же субсидию —
    # economy_total становится числом Σ измеренных (непривязанные по-прежнему
    # не входят в сумму, но больше не гасят её в None).
    fpi = await _make_planned_item(db_session, leaf.id, "Бензопила", 1, 100_000)
    fpi.unit_price = Decimal("100000")
    db_session.add(fpi)
    await db_session.commit()
    await _make_linked_purchase(db_session, subsidy.id, leaf.id, fpi.id, 1, 90_000)

    res2 = await purchase_economy_by_subsidy(db_session, [subsidy.id])
    row2 = res2[subsidy.id]
    assert row2["economy_total"] == Decimal("10000.00")
    assert row2["economy_no_planned_price_items"] == 2
    assert row2["economy_unmeasured_by_reason"]["unlinked"] == 2
