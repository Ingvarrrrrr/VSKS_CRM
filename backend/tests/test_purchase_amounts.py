"""test_purchase_amounts.py — unit-тесты app/services/purchase_amounts.py.

По одному сценарию на каждую группу статусов из докстринга модуля (paid /
delivered / work_in_progress|contracted|ordered / до договора), плюс рамочная
голова, ноль-как-значение, все-NULL и явные edge-статусы (cancelled, легаси
'planned') — см. системный докстринг задачи и app/services/purchase_amounts.py.

Последний блок (DIVERGENCE_TABLE/test_documented_divergences_from_old_formulas)
воспроизводит четыре из девяти старых формул (2a/3/6/9 — единственные, которым
не нужен join на contract_items/purchase_items/contracts, т.е. считаются прямо
здесь, без похода в БД) и документирует тестом, на каких сценариях они
расходятся с effective. Полный список всех 9 формул с точными file:line и
фактическим замером на реальных данных — app/services/purchase_amounts_audit.py.
"""
import uuid

import pytest
from decimal import Decimal

from sqlalchemy import select

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.services.purchase_amounts import effective_amount_expr, load_purchase_amounts, purchase_amounts


# ---------------------------------------------------------------------------
# paid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paid_uses_payment_amount(db_session, make_purchase):
    p = await make_purchase(status="paid", payment_amount=Decimal("777.50"),
                             contract_price=Decimal("999"), planned_total_price=Decimal("111"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("777.50")
    assert amounts.effective_source == "payment_amount"


@pytest.mark.asyncio
async def test_paid_without_payment_amount_falls_back_to_contract_price(db_session, make_purchase):
    """Вторая волна решения владельца (2026-09-05): paid без payment_amount/
    payment_amount_declared/acceptance_doc_amount спускается до contract_price,
    а не сразу даёт None."""
    p = await make_purchase(status="paid", payment_amount=None, contract_price=Decimal("500"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("500")
    assert amounts.effective_source == "contract_price"


@pytest.mark.asyncio
async def test_paid_falls_back_to_payment_amount_declared(db_session, make_purchase):
    p = await make_purchase(status="paid", payment_amount=None,
                             payment_amount_declared=Decimal("321"), contract_price=Decimal("999"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("321")
    assert amounts.effective_source == "payment_amount_declared"


@pytest.mark.asyncio
async def test_paid_falls_all_the_way_to_planned_total_price(db_session, make_purchase):
    """Цепочка paid доходит до planned_total_price, если всё «более позднее» пусто."""
    p = await make_purchase(status="paid", planned_total_price=Decimal("4000"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("4000")
    assert amounts.effective_source == "planned_total_price"


@pytest.mark.asyncio
async def test_paid_all_amounts_null_gives_none(db_session, make_purchase):
    p = await make_purchase(status="paid")
    amounts = purchase_amounts(p)
    assert amounts.effective is None
    assert "payment_amount" in amounts.effective_source and "all NULL" in amounts.effective_source


# ---------------------------------------------------------------------------
# delivered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delivered_uses_acceptance_doc_amount(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_doc_amount=Decimal("321"),
                             contract_price=Decimal("999"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("321")
    assert amounts.effective_source == "acceptance_doc_amount"


@pytest.mark.asyncio
async def test_delivered_falls_back_to_contract_price(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_doc_amount=None, contract_price=Decimal("654"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("654")
    assert amounts.effective_source == "contract_price"


@pytest.mark.asyncio
async def test_delivered_both_null_gives_none(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_doc_amount=None, contract_price=None)
    amounts = purchase_amounts(p)
    assert amounts.effective is None


@pytest.mark.asyncio
async def test_delivered_falls_all_the_way_to_planned_total_price(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_doc_amount=None, contract_price=None,
                             planned_total_price=Decimal("2100"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("2100")
    assert amounts.effective_source == "planned_total_price"


# ---------------------------------------------------------------------------
# work_in_progress / contracted / ordered
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["work_in_progress", "contracted", "ordered"])
@pytest.mark.asyncio
async def test_contract_stage_uses_contract_price(db_session, make_purchase, status):
    p = await make_purchase(status=status, contract_price=Decimal("1500"), planned_total_price=Decimal("1000"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("1500")
    assert amounts.effective_source == "contract_price"


@pytest.mark.asyncio
async def test_contract_stage_falls_back_to_contract_items_sum(db_session, make_purchase, make_contract_item):
    p = await make_purchase(status="contracted", contract_price=None)
    await make_contract_item(purchase_id=p.id, total=Decimal("100"))
    await make_contract_item(purchase_id=p.id, total=Decimal("250"))
    amounts = purchase_amounts(p, contract_items_total=Decimal("350"))
    assert amounts.effective == Decimal("350")
    assert amounts.effective_source == "sum(contract_items.total)"


@pytest.mark.asyncio
async def test_contract_stage_no_contract_price_no_items_gives_none(db_session, make_purchase):
    p = await make_purchase(status="ordered", contract_price=None)
    amounts = purchase_amounts(p, contract_items_total=None)
    assert amounts.effective is None


@pytest.mark.asyncio
async def test_contract_stage_falls_back_to_planned_when_no_contract_price_and_no_items(
    db_session, make_purchase,
):
    """work_in_progress без contract_price и без contract_items — спускается до
    planned_total_price (кейс, явно запрошенный владельцем)."""
    p = await make_purchase(status="work_in_progress", contract_price=None,
                             planned_total_price=Decimal("3300"))
    amounts = purchase_amounts(p, contract_items_total=None)
    assert amounts.effective == Decimal("3300")
    assert amounts.effective_source == "planned_total_price"


@pytest.mark.asyncio
async def test_contract_stage_falls_all_the_way_to_purchase_items_sum(db_session, make_purchase):
    p = await make_purchase(status="contracted", contract_price=None, planned_total_price=None)
    amounts = purchase_amounts(p, contract_items_total=None, items_total=Decimal("777"))
    assert amounts.effective == Decimal("777")
    assert amounts.effective_source == "sum(purchase_items.total_price)"


@pytest.mark.asyncio
async def test_contract_stage_all_amounts_null_gives_none(db_session, make_purchase):
    """work_in_progress, всё пусто (contract_price/Σci/planned/Σpi) → None (владелец)."""
    p = await make_purchase(status="work_in_progress", contract_price=None, planned_total_price=None)
    amounts = purchase_amounts(p, contract_items_total=None, items_total=None)
    assert amounts.effective is None
    assert "all NULL" in amounts.effective_source


# ---------------------------------------------------------------------------
# до договора (wishes / plan_schedule / cancelled / легаси 'planned')
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["wishes", "plan_schedule"])
@pytest.mark.asyncio
async def test_before_contract_uses_planned_total_price(db_session, make_purchase, status):
    p = await make_purchase(status=status, planned_total_price=Decimal("4200"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("4200")
    assert amounts.effective_source == "planned_total_price"


@pytest.mark.asyncio
async def test_before_contract_falls_back_to_items_sum(db_session, make_purchase_with_items):
    p = await make_purchase_with_items(status="wishes", items_count=3, item_total=Decimal("50"))
    p.planned_total_price = None
    await db_session.commit()
    amounts = purchase_amounts(p, items_total=Decimal("150"))
    assert amounts.effective == Decimal("150")
    assert amounts.effective_source == "sum(purchase_items.total_price)"


@pytest.mark.asyncio
async def test_before_contract_all_null_gives_none(db_session, make_purchase):
    p = await make_purchase(status="plan_schedule", planned_total_price=None)
    amounts = purchase_amounts(p, items_total=None)
    assert amounts.effective is None


@pytest.mark.asyncio
async def test_cancelled_falls_into_before_contract_group(db_session, make_purchase):
    """cancelled не входит явно ни в одну из 4 групп владельца — докстринг
    purchase_amounts.py относит её к «до договора» (см. модуль)."""
    p = await make_purchase(status="cancelled", planned_total_price=Decimal("999"), contract_price=Decimal("1"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("999")
    assert amounts.effective_source == "planned_total_price"


@pytest.mark.asyncio
async def test_legacy_planned_status_falls_into_before_contract_group(db_session, make_purchase):
    """'planned' — легаси-статус (default тестовой фабрики make_purchase,
    conftest.py), отсутствует в STATUS_ORDER (purchases.py:584) — тоже «до
    договора» (см. докстринг purchase_amounts.py)."""
    p = await make_purchase(status="planned", planned_total_price=Decimal("777"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("777")
    assert amounts.effective_source == "planned_total_price"


# ---------------------------------------------------------------------------
# ноль — значение, а не «пусто»
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_is_a_value_not_empty(db_session, make_purchase):
    p = await make_purchase(status="wishes", planned_total_price=Decimal("0"))
    amounts = purchase_amounts(p)
    assert amounts.effective == Decimal("0")
    assert amounts.effective is not None
    assert amounts.effective_source == "planned_total_price"


@pytest.mark.asyncio
async def test_all_amounts_null(db_session, make_purchase):
    p = await make_purchase(status="wishes", planned_total_price=None, contract_price=None,
                             acceptance_doc_amount=None, payment_amount=None)
    amounts = purchase_amounts(p)
    assert amounts.plan is None and amounts.contract is None
    assert amounts.fact is None and amounts.paid is None
    assert amounts.effective is None


# ---------------------------------------------------------------------------
# Рамочная голова
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_framework_head_uses_contract_max_amount(db_session, make_purchase):
    c = Contract(number="Д-500", contract_type="framework_cumulative", max_amount=Decimal("600000"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    p = await make_purchase(
        status="ordered", contract_id=c.id, contract_price=Decimal("100"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )
    amounts = purchase_amounts(p, framework_max_amount=c.max_amount)
    assert amounts.effective == Decimal("600000")
    assert amounts.effective_source == "contract.max_amount"


@pytest.mark.asyncio
async def test_framework_head_without_max_amount_falls_back_to_stage(db_session, make_purchase):
    c = Contract(number="Д-501", contract_type="framework_with_amount", max_amount=None)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    p = await make_purchase(
        status="contracted", contract_id=c.id, contract_price=Decimal("42"),
        purchase_contract_type="framework_with_amount", parent_purchase_id=None,
    )
    amounts = purchase_amounts(p, framework_max_amount=None)
    assert amounts.effective == Decimal("42")
    assert amounts.effective_source == "contract_price"


@pytest.mark.asyncio
async def test_framework_child_is_not_head_ignores_max_amount(db_session, make_purchase):
    """parent_purchase_id NOT NULL — дочерняя, не голова; max_amount её не касается."""
    parent = await make_purchase(status="wishes")
    child = await make_purchase(
        status="contracted", contract_price=Decimal("999"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=parent.id,
    )
    amounts = purchase_amounts(child, framework_max_amount=Decimal("1000000"))
    assert amounts.effective == Decimal("999")
    assert amounts.effective_source == "contract_price"


# ---------------------------------------------------------------------------
# load_purchase_amounts — bulk-версия, без N+1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_purchase_amounts_bulk_matches_single(db_session, make_purchase, make_contract_item):
    p1 = await make_purchase(status="paid", payment_amount=Decimal("100"))
    p2 = await make_purchase(status="contracted", contract_price=None)
    await make_contract_item(purchase_id=p2.id, total=Decimal("55"))
    p3 = await make_purchase(status="wishes", planned_total_price=Decimal("10"))

    bulk = await load_purchase_amounts(db_session, [p1.id, p2.id, p3.id])
    assert bulk[p1.id].effective == Decimal("100")
    assert bulk[p2.id].effective == Decimal("55")
    assert bulk[p2.id].effective_source == "sum(contract_items.total)"
    assert bulk[p3.id].effective == Decimal("10")


@pytest.mark.asyncio
async def test_load_purchase_amounts_empty_list(db_session):
    assert await load_purchase_amounts(db_session, []) == {}


# ---------------------------------------------------------------------------
# effective_amount_expr() — SQL case() эквивалент (БЕЗ item-фолбэков, см.
# предупреждение в его докстринге; С 2026-09-06 — С рамочной головой, та же
# формула, что и purchase_amounts()). Сверка с purchase_amounts() ТОЛЬКО там,
# где обе формулы определены одинаково (главная колонка стадии не NULL, ЛИБО
# рамочная голова с max_amount) — там, где purchase_amounts() уходит в
# item-фолбэк, SQL-выражение по документированному дизайну расходится (NULL).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,field,value", [
    ("paid", "payment_amount", Decimal("55.5")),
    ("delivered", "acceptance_doc_amount", Decimal("77")),
    ("contracted", "contract_price", Decimal("88")),
    ("wishes", "planned_total_price", Decimal("99")),
])
@pytest.mark.asyncio
async def test_sql_expr_matches_python_when_primary_column_present(
    db_session, make_purchase, status, field, value
):
    p = await make_purchase(status=status, **{field: value})
    py = purchase_amounts(p)

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == p.id)
    )).scalar_one()
    sql_val = Decimal(str(row)) if row is not None else None
    assert sql_val == py.effective == value


@pytest.mark.asyncio
async def test_sql_expr_diverges_from_python_on_item_fallback(db_session, make_purchase, make_contract_item):
    p = await make_purchase(status="contracted", contract_price=None)
    await make_contract_item(purchase_id=p.id, total=Decimal("300"))
    py = purchase_amounts(p, contract_items_total=Decimal("300"))
    assert py.effective == Decimal("300")

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == p.id)
    )).scalar_one()
    assert row is None
    assert row != py.effective


# ---------------------------------------------------------------------------
# Рамочная голова: effective_amount_expr() (SQL) обязан давать РОВНО то же
# число, что purchase_amounts()/load_purchase_amounts() (Python) — правка
# владельца 2026-09-06 после прод-находки (id=773: SQL-агрегаты давали
# 47262.50 — сырой payment_amount головы, GET /api/purchases/773 давал
# 600000 — Contract.max_amount; два числа одного показателя, см. докстринг
# effective_amount_expr()).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sql_expr_matches_python_for_framework_head_with_max_amount(db_session, make_purchase):
    c = Contract(number="Д-700", contract_type="framework_cumulative", max_amount=Decimal("600000"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    p = await make_purchase(
        status="paid", payment_amount=Decimal("47262.50"), contract_id=c.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )
    py = purchase_amounts(p, framework_max_amount=c.max_amount)
    assert py.effective == Decimal("600000")

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == p.id)
    )).scalar_one()
    assert Decimal(str(row)) == py.effective == Decimal("600000")


@pytest.mark.asyncio
async def test_sql_expr_matches_python_for_framework_head_without_max_amount(db_session, make_purchase):
    """Голова БЕЗ Contract.max_amount (или без contract_id вовсе) — обе формулы
    проваливаются в обычную цепочку по стадии (contract_price здесь)."""
    c = Contract(number="Д-701", contract_type="framework_with_amount", max_amount=None)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    p = await make_purchase(
        status="contracted", contract_price=Decimal("42"), contract_id=c.id,
        purchase_contract_type="framework_with_amount", parent_purchase_id=None,
    )
    py = purchase_amounts(p, framework_max_amount=None)
    assert py.effective == Decimal("42")

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == p.id)
    )).scalar_one()
    assert Decimal(str(row)) == py.effective == Decimal("42")


@pytest.mark.asyncio
async def test_sql_expr_matches_python_framework_child_ignores_max_amount(db_session, make_purchase):
    """Дочерняя закупка (parent_purchase_id NOT NULL) — не голова, max_amount
    контракта её не касается ни в Python, ни в SQL."""
    c = Contract(number="Д-702", contract_type="framework_cumulative", max_amount=Decimal("999999"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    parent = await make_purchase(status="wishes")
    child = await make_purchase(
        status="contracted", contract_price=Decimal("777"), contract_id=c.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=parent.id,
    )
    py = purchase_amounts(child, framework_max_amount=Decimal("999999"))
    assert py.effective == Decimal("777")

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == child.id)
    )).scalar_one()
    assert Decimal(str(row)) == py.effective == Decimal("777")


@pytest.mark.asyncio
async def test_multiple_framework_heads_same_contract_get_no_max_amount(db_session, make_purchase):
    """Владелец (2026-09-06, прод-находка: contract_id=32 → 5 голов, 42 → 3):
    НЕСКОЛЬКО закупок с parent_purchase_id IS NULL на один contract_id — не
    должно быть так по построению рамочного механизма, но данные это не
    гарантируют. Ни Python (load_purchase_amounts), ни SQL
    (effective_amount_expr) не применяют Contract.max_amount ни к одной из
    них в этом случае — обе падают в обычную цепочку по стадии
    (contract_price для каждой)."""
    c = Contract(number="Д-800", contract_type="framework_cumulative", max_amount=Decimal("1000000"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    head1 = await make_purchase(
        status="contracted", contract_price=Decimal("111"), contract_id=c.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )
    head2 = await make_purchase(
        status="contracted", contract_price=Decimal("222"), contract_id=c.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )

    bulk = await load_purchase_amounts(db_session, [head1.id, head2.id])
    assert bulk[head1.id].effective == Decimal("111")
    assert bulk[head1.id].effective_source == "contract_price"
    assert bulk[head2.id].effective == Decimal("222")
    assert bulk[head2.id].effective_source == "contract_price"

    row1 = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == head1.id)
    )).scalar_one()
    row2 = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == head2.id)
    )).scalar_one()
    assert Decimal(str(row1)) == Decimal("111")
    assert Decimal(str(row2)) == Decimal("222")


@pytest.mark.asyncio
async def test_single_framework_head_still_gets_max_amount_after_uniqueness_check(
    db_session, make_purchase,
):
    """Контроль: гейт на уникальность головы не ломает обычный (единственная
    голова) случай — max_amount по-прежнему применяется, в Python и SQL."""
    c = Contract(number="Д-801", contract_type="framework_cumulative", max_amount=Decimal("500000"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    head = await make_purchase(
        status="contracted", contract_price=Decimal("111"), contract_id=c.id,
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )

    bulk = await load_purchase_amounts(db_session, [head.id])
    assert bulk[head.id].effective == Decimal("500000")
    assert bulk[head.id].effective_source == "contract.max_amount"

    row = (await db_session.execute(
        select(effective_amount_expr()).where(Purchase.id == head.id)
    )).scalar_one()
    assert Decimal(str(row)) == Decimal("500000")


# ---------------------------------------------------------------------------
# Документация расхождений со старыми формулами (2a/3/6/9 — единственные из
# 9, что считаются по сырым колонкам закупки без join'ов; полный список всех
# 9 формул и фактический замер на реальных данных — purchase_amounts_audit.py).
# ---------------------------------------------------------------------------

def _old_2a(p):
    """dashboard.py — COALESCE(contract_price, planned_total_price)."""
    return p.contract_price if p.contract_price is not None else p.planned_total_price


def _old_3(p):
    """purchase_export.py:278 — `nmck or planned_total_price or 0` (Python truthy)."""
    val = p.nmck if p.nmck else p.planned_total_price
    return val if val else Decimal("0")


def _old_6(p):
    """purchase_payments.py:103 — `contract_price or planned_total_price or 0` (Python truthy)."""
    if p.contract_price:
        return p.contract_price
    if p.planned_total_price:
        return p.planned_total_price
    return Decimal("0")


def _old_9(p):
    """subsidies.py:130-133 — Σ planned_total_price, КРОМЕ cancelled (None = формула
    не применяется к этой закупке вовсе, а не «совпадает» или «расходится»)."""
    if p.status == "cancelled":
        return None
    return p.planned_total_price if p.planned_total_price is not None else Decimal("0")


DIVERGENCE_TABLE = [
    # (status, kwargs, expected_effective, ожидаемые расходящиеся старые формулы)
    ("paid", dict(payment_amount=Decimal("500"), contract_price=Decimal("400")),
     Decimal("500"), {"2a", "3", "6", "9"}),
    ("delivered", dict(acceptance_doc_amount=Decimal("300"), contract_price=Decimal("200")),
     Decimal("300"), {"2a", "3", "6", "9"}),
    ("contracted", dict(contract_price=Decimal("150"), planned_total_price=Decimal("100")),
     Decimal("150"), {"3", "9"}),
    ("wishes", dict(planned_total_price=Decimal("70")),
     Decimal("70"), set()),
    # cancelled: formula 9 попросту не применяется (N/A) — effective всё равно
    # считается (40, «до договора»), поэтому численного расхождения 0 (не в
    # actual_divergent), но это НЕ «совпадение по смыслу» — задокументировано отдельно ниже.
    ("cancelled", dict(planned_total_price=Decimal("40")),
     Decimal("40"), set()),
]


@pytest.mark.parametrize("status,kwargs,expected_effective,expect_divergent", DIVERGENCE_TABLE)
@pytest.mark.asyncio
async def test_documented_divergences_from_old_formulas(
    db_session, make_purchase, status, kwargs, expected_effective, expect_divergent
):
    p = await make_purchase(status=status, **kwargs)
    eff = purchase_amounts(p).effective
    assert eff == expected_effective

    olds = {"2a": _old_2a(p), "3": _old_3(p), "6": _old_6(p), "9": _old_9(p)}
    actual_divergent = {name for name, val in olds.items() if val is not None and val != eff}
    assert actual_divergent == expect_divergent


@pytest.mark.asyncio
async def test_cancelled_formula_9_not_applicable_not_a_match(db_session, make_purchase):
    """Уточнение к последней строке DIVERGENCE_TABLE: для cancelled формула 9
    вообще не производит числа (её WHERE исключает cancelled) — это НЕ то же
    самое, что «формула 9 согласна с effective»."""
    p = await make_purchase(status="cancelled", planned_total_price=Decimal("40"))
    assert _old_9(p) is None
    assert purchase_amounts(p).effective == Decimal("40")


# ---------------------------------------------------------------------------
# aggregate_scope_expr() / in_aggregate_scope() — владелец (2026-09-06):
# рамочные договоры в ИТОГАХ по субсидии/категории ФЭО/дашборду. Разовый
# договор — как есть. Рамочный С ПРЕДЕЛЬНОЙ СУММОЙ: голова несёт
# «законтрактовано» целиком (max_amount), «заказано» — только дети → дети
# такой головы исключаются из Σ. Рамочный НАКОПИТЕЛЬНЫЙ (без предела):
# «заказано» = Σ детей → сама голова (без своей суммы) исключается из Σ.
# ---------------------------------------------------------------------------

async def _make_subsidy_for_agg(db_session, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"AggTestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
                require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest.mark.asyncio
async def test_aggregate_scope_capped_head_excludes_children(db_session, make_purchase):
    """Голова framework_with_amount с max_amount=600000 + два ребёнка
    (47262.50 и 10000, отправленные заявки) — Σ по субсидии = 600000
    (только голова; дети исключены — их деньги внутри потолка головы)."""
    from app.routers.subsidies import _calculate_spent
    from app.services.purchase_amounts import aggregate_scope_expr, in_aggregate_scope

    subsidy = await _make_subsidy_for_agg(db_session)
    c = Contract(number="Д-900", contract_type="framework_with_amount", max_amount=Decimal("600000"))
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    head = await make_purchase(
        status="contracted", subsidy_id=subsidy.id, contract_id=c.id,
        purchase_contract_type="framework_with_amount", parent_purchase_id=None,
    )
    child1 = await make_purchase(
        status="paid", subsidy_id=subsidy.id, contract_id=c.id, payment_amount=Decimal("47262.50"),
        purchase_contract_type="framework_with_amount", parent_purchase_id=head.id,
    )
    child2 = await make_purchase(
        status="ordered", subsidy_id=subsidy.id, contract_id=c.id, contract_price=Decimal("10000"),
        purchase_contract_type="framework_with_amount", parent_purchase_id=head.id,
    )

    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == Decimal("600000")

    # Python-side предикат согласен с SQL-стороной (parity)
    assert in_aggregate_scope(head, parent_max_amount=None, own_max_amount=Decimal("600000")) is True
    assert in_aggregate_scope(child1, parent_max_amount=Decimal("600000")) is False
    assert in_aggregate_scope(child2, parent_max_amount=Decimal("600000")) is False

    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Purchase.id, aggregate_scope_expr()).where(Purchase.id.in_([head.id, child1.id, child2.id]))
    )).all()
    scope_by_id = dict(rows)
    assert scope_by_id[head.id] is True
    assert scope_by_id[child1.id] is False
    assert scope_by_id[child2.id] is False


@pytest.mark.asyncio
async def test_aggregate_scope_uncapped_cumulative_head_excluded_children_included(
    db_session, make_purchase,
):
    """Накопительная голова (framework_cumulative, БЕЗ max_amount) + два
    ребёнка (10000 и 20000) — Σ по субсидии = 30000 (голова исключена —
    у неё нет своей суммы; дети — «заказано», входят целиком)."""
    from app.routers.subsidies import _calculate_spent
    from app.services.purchase_amounts import in_aggregate_scope

    subsidy = await _make_subsidy_for_agg(db_session)
    c = Contract(number="Д-901", contract_type="framework_cumulative", max_amount=None)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    head = await make_purchase(
        status="ordered", subsidy_id=subsidy.id, contract_id=c.id, contract_price=Decimal("999999"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )
    child1 = await make_purchase(
        status="ordered", subsidy_id=subsidy.id, contract_id=c.id, contract_price=Decimal("10000"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=head.id,
    )
    child2 = await make_purchase(
        status="ordered", subsidy_id=subsidy.id, contract_id=c.id, contract_price=Decimal("20000"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=head.id,
    )

    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == Decimal("30000")

    assert in_aggregate_scope(head, own_max_amount=None, has_children=True) is False
    assert in_aggregate_scope(child1, parent_max_amount=None) is True
    assert in_aggregate_scope(child2, parent_max_amount=None) is True

    from app.services.purchase_amounts import aggregate_scope_expr
    rows = (await db_session.execute(
        select(Purchase.id, aggregate_scope_expr()).where(Purchase.id.in_([head.id, child1.id, child2.id]))
    )).all()
    scope_by_id = dict(rows)
    assert scope_by_id[head.id] is False
    assert scope_by_id[child1.id] is True
    assert scope_by_id[child2.id] is True


@pytest.mark.asyncio
async def test_aggregate_scope_uncapped_cumulative_head_without_children_stays_in_scope(
    db_session, make_purchase,
):
    """Владелец (2026-09-06, уточнение после прод-находки): в текущих данных
    заказы под рамочным договором связаны ОБЩИМ contract_id, а НЕ через
    parent_purchase_id (эта FK-колонка занята несвязанной фичей «разбить
    закупку» и ни разу не используется для рамочных договоров — см. ⚠️ в
    докстринге in_aggregate_scope()). Поэтому накопительная голова БЕЗ
    единого реального ребёнка (has_children=False, текущая реальность на
    проде) — считается ОБЫЧНОЙ закупкой, своей суммой по стадии, Σ её НЕ
    теряет."""
    from app.routers.subsidies import _calculate_spent
    from app.services.purchase_amounts import in_aggregate_scope

    subsidy = await _make_subsidy_for_agg(db_session)
    c = Contract(number="Д-902", contract_type="framework_cumulative", max_amount=None)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    lone_head = await make_purchase(
        status="ordered", subsidy_id=subsidy.id, contract_id=c.id, contract_price=Decimal("55555"),
        purchase_contract_type="framework_cumulative", parent_purchase_id=None,
    )

    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == Decimal("55555")
    assert in_aggregate_scope(lone_head, own_max_amount=None, has_children=False) is True

    from app.services.purchase_amounts import aggregate_scope_expr
    row = (await db_session.execute(
        select(aggregate_scope_expr()).where(Purchase.id == lone_head.id)
    )).scalar_one()
    assert row is True


@pytest.mark.asyncio
async def test_aggregate_scope_single_purchase_unaffected(db_session, make_purchase):
    """Одиночная (не рамочная) закупка — предикат её не касается, Σ как обычно."""
    from app.routers.subsidies import _calculate_spent
    from app.services.purchase_amounts import in_aggregate_scope

    subsidy = await _make_subsidy_for_agg(db_session)
    p = await make_purchase(status="contracted", subsidy_id=subsidy.id, contract_price=Decimal("12345"))

    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == Decimal("12345")
    assert in_aggregate_scope(p) is True
