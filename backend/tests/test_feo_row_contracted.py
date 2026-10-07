"""test_feo_row_contracted.py — строка дерева ФЭО «В закупках/Законтрактовано/
из них заказано/зарезервировано» ПО КАТЕГОРИИ (владелец, 06.10.2026, план
.planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаги 1-3).

Контрольные сценарии (разовый, авансовый, рамочный накопительный с заказами в
разных статусах, рамочный с суммой — лимит больше/меньше Σ заказов, голова и
заказы в разных категориях) + ДВА инварианта:
  1. Σ contracted по категориям субсидии (+ «без категории») ==
     contracted_total_by_subsidy(...)[subsidy_id]['amount'].
  2. Σ planned-purchase-totals.total по категориям (через feo_row_drill
     kind=in_purchases) == старому способу без задвоения головы.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_row_contracted import feo_row_contract_totals, feo_row_drill
from app.services.stage_cumulative import contracted_total_by_subsidy


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"RowContracted-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id, level=1, parent_id=None,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"), **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase(db_session, subsidy_id, *, status, **kwargs):
    from app.models.purchase import Purchase
    p = Purchase(subsidy_id=subsidy_id, status=status, item_name=f"P-{uuid.uuid4().hex[:6]}", **kwargs)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_single_purchase_contracted_and_ordered(db_session, test_org):
    """Разовый договор — закупка в статусе 'ordered': contracted (сумма
    закупки, т.к. recorded max_amount < actual => topup добирает до actual) И
    ordered несут ОДНУ и ту же сумму (committed_status_predicate для не-
    framework = SINGLE_COMMITTED_STATUSES, ordered входит)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Разовые")
    contract = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("50000"),
    )
    db_session.add(contract)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat.id,
        contract_price=Decimal("70000"), contract_id=contract.id,
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    assert totals[cat.id]["contracted"] == pytest.approx(70_000.0)  # topup: actual(70k) > recorded(50k)
    assert totals[cat.id]["ordered"] == pytest.approx(70_000.0)
    assert totals[cat.id]["reserved"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_advance_purchase_without_contract_is_committed_uncounted(db_session, test_org):
    """Авансовый — закупка без Contract вовсе, статус 'paid' (SINGLE_COMMITTED_STATUSES)
    — попадает в «законтрактовано» через committed_uncounted (причина 1
    stage_cumulative.py), категория — её собственная."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Авансовые")
    await _make_purchase(
        db_session, subsidy.id, status="paid", feo_category_id=cat.id,
        payment_amount=Decimal("12345"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    assert totals[cat.id]["contracted"] == pytest.approx(12_345.0)
    assert totals[cat.id]["ordered"] == pytest.approx(12_345.0)


@pytest.mark.asyncio
async def test_framework_cumulative_orders_in_different_statuses(db_session, test_org):
    """Рамочный накопительный: один заказ 'ordered' (входит в ordered+contracted),
    один 'contracted' (входит ТОЛЬКО в reserved — договор заключён, заказ как
    отдельная закупка ещё не оформлен, см. reserved_child_predicate)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Накопительный")
    contract = Contract(
        number=f"FC-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, status="active",
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat.id,
        purchase_contract_type="framework_cumulative", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat.id,
        purchase_contract_type="framework_cumulative", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("30000"),
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat.id,
        purchase_contract_type="framework_cumulative", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("20000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    # Правка 🟣 07.10.2026 (закрытие «экзотики»): contracted для cumulative
    # теперь = Σ(ordered+reserved) — будущий заказ (статус 'contracted', ещё
    # не оформлен отдельной закупкой) ТОЖЕ законтрактованные деньги.
    assert totals[cat.id]["contracted"] == pytest.approx(50_000.0)  # 30000 (ordered) + 20000 (reserved)
    assert totals[cat.id]["ordered"] == pytest.approx(30_000.0)
    assert totals[cat.id]["reserved"] == pytest.approx(20_000.0)
    assert totals[cat.id]["contracted"] >= totals[cat.id]["ordered"] + totals[cat.id]["reserved"] - 0.005


@pytest.mark.asyncio
async def test_framework_cumulative_future_reserved_order_in_its_own_category(db_session, test_org):
    """Правка 🟣 07.10.2026: будущий заказ накопительного (статус 'contracted'
    — договор на партию уже заключён, заказ как отдельная закупка ещё не
    оформлен) — ЗАКОНТРАКТОВАН, причём в СВОЕЙ категории (не категории
    головы), даже если она отличается от категории уже размещённых заказов."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat_head = await _make_category(db_session, subsidy.id, name="Категория головы (накопительный)")
    cat_future = await _make_category(db_session, subsidy.id, name="Категория будущего заказа")
    contract = Contract(
        number=f"FC2-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, status="active",
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_head.id,
        purchase_contract_type="framework_cumulative", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_future.id,
        purchase_contract_type="framework_cumulative", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("15000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    assert totals.get(cat_head.id, {"contracted": 0.0})["contracted"] == pytest.approx(0.0)
    assert totals[cat_future.id]["contracted"] == pytest.approx(15_000.0)
    assert totals[cat_future.id]["ordered"] == pytest.approx(0.0)
    assert totals[cat_future.id]["reserved"] == pytest.approx(15_000.0)


@pytest.mark.asyncio
async def test_framework_with_amount_limit_below_orders_head_and_orders_split_categories(db_session, test_org):
    """Рамочный с суммой, лимит МЕНЬШЕ Σ заказов, голова и заказ — в РАЗНЫХ
    категориях (прод-находка, пересмотр В3 владельцем 🔵 07.10.2026: заказы
    несут "законтрактовано" СВОЕЙ категории, остаток max(0, лимит−Σзаказов)
    (здесь 0, т.к. лимит < заказов) — в категорию головы, если он > 0)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat_head = await _make_category(db_session, subsidy.id, name="Статья договора")
    cat_order = await _make_category(db_session, subsidy.id, name="Статья заказа")
    contract = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("10000"),
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_head.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat_order.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("15000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    _empty = {"contracted": 0.0, "ordered": 0.0, "reserved": 0.0}
    # Остаток max(0, 10000-15000)=0 — категория головы не получает ничего.
    head_row = totals.get(cat_head.id, _empty)
    assert head_row["contracted"] == pytest.approx(0.0)
    assert head_row["ordered"] == pytest.approx(0.0)  # голова сама не заказ
    assert totals[cat_order.id]["contracted"] == pytest.approx(15_000.0)  # заказ несёт contracted СВОЕЙ категории
    assert totals[cat_order.id]["ordered"] == pytest.approx(15_000.0)
    # contracted ≥ ordered + reserved в КАЖДОЙ категории.
    for cid, v in totals.items():
        assert v["contracted"] >= v["ordered"] + v["reserved"] - 0.005


@pytest.mark.asyncio
async def test_framework_with_amount_head_without_category_falls_back_to_single_order_category(db_session, test_org):
    """Голова БЕЗ категории ФЭО (прод-находка: у 3 из 4 fwa голова в «Не
    определена») — остаток лимита падает в категорию заказов, если она у всех
    заказов контракта ОДНА."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat_order = await _make_category(db_session, subsidy.id, name="Единственная статья заказов")
    contract = Contract(
        number=f"FWA5-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("50000"),
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=None,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat_order.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("20000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    # Остаток 50000-20000=30000 падает в cat_order (единственная категория
    # заказов) — вместе с заказом 20000 итог 50000.
    assert totals[cat_order.id]["contracted"] == pytest.approx(50_000.0)
    assert totals[cat_order.id]["ordered"] == pytest.approx(20_000.0)
    assert totals.get(None, {"contracted": 0.0})["contracted"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_framework_with_amount_limit_above_orders(db_session, test_org):
    """Рамочный с суммой, лимит БОЛЬШЕ Σ заказов: contracted(голова) = лимит
    (greatest(limit, actual) = limit), ordered = фактическая Σ заказов."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat_head = await _make_category(db_session, subsidy.id, name="Статья договора 2")
    contract = Contract(
        number=f"FWA2-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("100000"),
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_head.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="delivered", feo_category_id=cat_head.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("40000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    assert totals[cat_head.id]["contracted"] == pytest.approx(100_000.0)
    assert totals[cat_head.id]["ordered"] == pytest.approx(40_000.0)


@pytest.mark.asyncio
async def test_contracted_sum_by_category_matches_contracted_total_by_subsidy(db_session, test_org):
    """ИНВАРИАНТ 1: Σ contracted по всем категориям (+ «без категории», ключ
    None) субсидии == contracted_total_by_subsidy(...)['amount'] — обе читают
    app.services.stage_cumulative.contracted_rows_by_category() (ПРАВИЛО №6)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    cat_a = await _make_category(db_session, subsidy.id, name="A")
    cat_b = await _make_category(db_session, subsidy.id, name="B")

    # single
    single = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("50000"),
    )
    db_session.add(single)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_a.id,
        contract_price=Decimal("50000"), contract_id=single.id,
    )

    # framework_with_amount — голова в B, заказ в A
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("200000"),
    )
    db_session.add(fwa)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_b.id,
        purchase_contract_type="framework_with_amount", contract_id=fwa.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat_a.id,
        purchase_contract_type="framework_with_amount", contract_id=fwa.id,
        parent_purchase_id=head.id, contract_price=Decimal("90000"),
    )

    # committed-закупка без контракта (без категории — "без категории")
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("777"))

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    by_category_sum = sum(v["contracted"] for v in totals.values())

    card_map = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert by_category_sum == pytest.approx(card_map[subsidy.id]["amount"])
    assert by_category_sum == pytest.approx(50_000.0 + 200_000.0 + 777.0)


@pytest.mark.asyncio
async def test_in_purchases_head_with_children_not_double_counted(db_session, test_org):
    """ШАГ 1: planned-purchase-totals (через feo_row_drill kind=in_purchases)
    не считает рамочную ГОЛОВУ с реально существующими заказами ПОВЕРХ самих
    заказов (aggregate_scope_expr()) — прод-кейс РЕЕ-2026-03134."""
    from app.models.contract import Contract
    from app.models.purchase_item import PurchaseItem
    from app.routers.feo_categories import _collect_subtree_ids

    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Техническое оснащение")
    contract = Contract(
        number=f"FWA3-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("207900"),
    )
    db_session.add(contract)
    await db_session.flush()

    head = await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        planned_total_price=Decimal("207900"),
    )
    pi_head = PurchaseItem(
        purchase_id=head.id, item_name="Лимит договора", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("207900"), total_price=Decimal("207900"), feo_category_id=cat.id,
    )
    db_session.add(pi_head)

    total_children = Decimal("0")
    for amt in (Decimal("30000"), Decimal("25000"), Decimal("20000")):
        child = await _make_purchase(
            db_session, subsidy.id, status="ordered", feo_category_id=cat.id,
            purchase_contract_type="framework_with_amount", contract_id=contract.id,
            parent_purchase_id=head.id, planned_total_price=amt,
        )
        pi = PurchaseItem(
            purchase_id=child.id, item_name="Заказ", quantity=Decimal("1"), unit="шт",
            unit_price=amt, total_price=amt, feo_category_id=cat.id,
        )
        db_session.add(pi)
        total_children += amt
    await db_session.commit()

    cat_ids = await _collect_subtree_ids(cat.id, db_session)
    drill = await feo_row_drill(db_session, subsidy_id=subsidy.id, cat_ids=cat_ids, kind="in_purchases")
    # Голова (207 900) исключена по aggregate_scope_expr() — только заказы.
    assert drill["total"] == pytest.approx(float(total_children))
    assert all(r["purchase_id"] != head.id for r in drill["rows"])


@pytest.mark.asyncio
async def test_unallocated_matches_row_contract_totals_when_head_and_orders_share_category(db_session, test_org):
    """unallocated = contracted − ordered − reserved (без своего SQL, см.
    ОПРЕДЕЛЕНИЯ плана) — сходится с drill (kind=unallocated, остаток
    рамочной ГОЛОВЫ) РОВНО в том случае, когда голова и её заказы лежат В
    ОДНОЙ категории (типовой случай). Если владелец разносит лимит и заказы
    по разным статьям (В3, решение 06.10.2026) — «не распределено» КАЖДОЙ
    отдельной статьи перестаёт быть равным остатку лимита головы (эта сумма
    «перетекает» в статью заказа как учтённое «заказано» без своего
    «законтрактовано» в ТОЙ ЖЕ статье) — ожидаемое следствие В3, не второй
    расчёт и не баг этого теста."""
    from app.models.contract import Contract
    from app.routers.feo_categories import _collect_subtree_ids

    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id, name="Одна статья на всё")
    contract = Contract(
        number=f"FWA4-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("100000"),
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("40000"),
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("10000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    row = totals[cat.id]
    unallocated_from_totals = row["contracted"] - row["ordered"] - row["reserved"]
    assert unallocated_from_totals == pytest.approx(50_000.0)  # 100000 - 40000 - 10000

    cat_ids = await _collect_subtree_ids(cat.id, db_session)
    drill = await feo_row_drill(db_session, subsidy_id=subsidy.id, cat_ids=cat_ids, kind="unallocated")
    assert drill["total"] == pytest.approx(unallocated_from_totals)


@pytest.mark.asyncio
async def test_unallocated_matches_row_contract_totals_for_any_subtree_with_split_categories(db_session, test_org):
    """ИСПРАВЛЕНИЕ пересмотра В3 (🔵 07.10.2026): голова рамочного-с-суммой и
    её заказ — в РАЗНЫХ категориях (типовой прод-кейс). Для КАЖДОЙ из двух
    категорий по отдельности drill(kind=unallocated) == contracted−ordered−reserved
    этой же категории из row-contract-totals — та самая проверка, которая
    раньше (до пересмотра) не сходилась (голова несла ВСЮ сумму, заказ — ничего)."""
    from app.models.contract import Contract
    from app.routers.feo_categories import _collect_subtree_ids

    subsidy = await _make_subsidy(db_session)
    cat_head = await _make_category(db_session, subsidy.id, name="Статья договора (сплит)")
    cat_order = await _make_category(db_session, subsidy.id, name="Статья заказа (сплит)")
    contract = Contract(
        number=f"FWA6-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("100000"),
    )
    db_session.add(contract)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_head.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", feo_category_id=cat_order.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("30000"),
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted", feo_category_id=cat_order.id,
        purchase_contract_type="framework_with_amount", contract_id=contract.id,
        parent_purchase_id=head.id, contract_price=Decimal("10000"),
    )

    totals = await feo_row_contract_totals(db_session, subsidy.id)
    # Заказы (ordered+reserved) = 40000, целиком в cat_order; остаток
    # 100000-40000=60000 — в cat_head (голова там же).
    assert totals[cat_order.id]["contracted"] == pytest.approx(40_000.0)
    assert totals[cat_order.id]["ordered"] == pytest.approx(30_000.0)
    assert totals[cat_order.id]["reserved"] == pytest.approx(10_000.0)
    assert totals[cat_head.id]["contracted"] == pytest.approx(60_000.0)
    assert totals[cat_head.id]["ordered"] == pytest.approx(0.0)
    assert totals[cat_head.id]["reserved"] == pytest.approx(0.0)

    for cat in (cat_head, cat_order):
        row = totals[cat.id]
        expected_unalloc = row["contracted"] - row["ordered"] - row["reserved"]
        assert expected_unalloc >= -0.005
        cat_ids = await _collect_subtree_ids(cat.id, db_session)
        drill = await feo_row_drill(db_session, subsidy_id=subsidy.id, cat_ids=cat_ids, kind="unallocated")
        assert drill["total"] == pytest.approx(expected_unalloc)
