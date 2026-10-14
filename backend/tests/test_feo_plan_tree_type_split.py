"""Задача владельца (план ancient-prancing-music.md, раздел E, 2026-09-21):
«товары/услуги» по узлу дерева ФЭО — compute_feo_plan_tree.node несёт
plan_goods/plan_services/plan_unspecified, feo_goods/feo_services/
feo_unspecified, fact_goods/fact_services/fact_unspecified, плюс 4 независимых
контроля превышения (excess_plan_over_feo_goods/services,
excess_fact_over_plan_goods/services).

Проверяет:
  (1) plan_goods+plan_services+plan_unspecified == Σ активных FeoPlannedItem.amount
      узла (инвариант суммы, по образцу test_feo_plan_tree_scenarios.py).
  (2) feo_goods/feo_services — Σ feo_amount строк is_feo_breakdown=true по типу;
      feo_unspecified — явный FeoCategory.budget узла (нетипизированный).
  (3) excess_plan_over_feo_services срабатывает, когда план услуг выше ФЭО
      услуг, а excess_plan_over_feo_goods — НЕТ, когда feo_goods=0 (нет
      типизированного ФЭО по товарам).
  (4) fact_goods/fact_services — из позиций закупки (item_type), и
      excess_fact_over_plan_goods > 0, когда факт по товарам выше плана.
  (5) уровень субсидии (compute_subsidy_type_summary) — сумма корневых узлов.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TypeSplit-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(
    db_session, feo_category_id, name, amount, item_type=None,
    is_feo_breakdown=False, feo_amount=None, quantity=1,
):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        item_type=item_type,
        is_feo_breakdown=is_feo_breakdown,
        feo_amount=Decimal(str(feo_amount)) if feo_amount is not None else None,
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_purchase_item(
    db_session, subsidy_id, feo_category_id, item_name, item_type, amount,
    status="work_in_progress", over_plan=False, quantity=1,
):
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name=item_name,
        status=status,
        contract_price=Decimal(str(amount)),
        planned_total_price=Decimal(str(amount)),
        total_nmck=Decimal(str(amount)),
        nmck=Decimal(str(amount)),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name=item_name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(amount)),
        total_price=Decimal(str(amount)),
        feo_category_id=feo_category_id,
        item_type=item_type,
        over_plan=over_plan,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_plan_by_type_sums_to_items_total(db_session, test_org):
    """(1) plan_goods+services+unspecified == Σ активных плановых позиций узла."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — товары/услуги/без типа")
    await _make_planned_item(db_session, cat.id, "Ноутбук", 100_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Обслуживание", 40_000, item_type="услуга")
    await _make_planned_item(db_session, cat.id, "Монтаж", 10_000, item_type="работа")  # работа -> services
    await _make_planned_item(db_session, cat.id, "Без типа", 5_000, item_type=None)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan_goods"] == pytest.approx(100_000.0)
    assert node["plan_services"] == pytest.approx(50_000.0), "услуга (40к) + работа (10к) = 50к"
    assert node["plan_unspecified"] == pytest.approx(5_000.0)
    total = node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]
    assert total == pytest.approx(155_000.0)


@pytest.mark.asyncio
async def test_feo_by_type_from_breakdown_rows_and_explicit_budget_is_unspecified(db_session, test_org):
    """(2) feo_goods/feo_services — Σ feo_amount строк is_feo_breakdown=true по
    типу; отдельный узел с ЯВНЫМ FeoCategory.budget (без строк) — budget
    целиком уходит в feo_unspecified (нетипизированный бюджет категории)."""
    subsidy = await _make_subsidy(db_session, test_org.id)

    cat_typed = await _make_category(db_session, subsidy.id, name="Узел — типизированное ФЭО")
    await _make_planned_item(
        db_session, cat_typed.id, "Ноутбук (по ФЭО)", 90_000, item_type="товар",
        is_feo_breakdown=True, feo_amount=90_000,
    )
    await _make_planned_item(
        db_session, cat_typed.id, "Обслуживание (по ФЭО)", 30_000, item_type="услуга",
        is_feo_breakdown=True, feo_amount=30_000,
    )
    # Позиция БЕЗ is_feo_breakdown — не должна попасть в feo_goods/services.
    await _make_planned_item(db_session, cat_typed.id, "Просто план", 5_000, item_type="товар")

    cat_untyped = await _make_category(
        db_session, subsidy.id, name="Узел — нетипизированный бюджет", budget=Decimal("500000"),
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_typed = tree[cat_typed.id]
    assert node_typed["feo_goods"] == pytest.approx(90_000.0)
    assert node_typed["feo_services"] == pytest.approx(30_000.0)
    assert node_typed["feo_unspecified"] == pytest.approx(0.0)

    node_untyped = tree[cat_untyped.id]
    assert node_untyped["feo_goods"] == pytest.approx(0.0)
    assert node_untyped["feo_services"] == pytest.approx(0.0)
    assert node_untyped["feo_unspecified"] == pytest.approx(500_000.0)


@pytest.mark.asyncio
async def test_excess_plan_over_feo_only_fires_when_feo_typed_exists(db_session, test_org):
    """(3) План услуг (60к) выше ФЭО услуг (30к) -> excess_plan_over_feo_services
    > 0. ФЭО товаров типизировано не задано (0) -> excess_plan_over_feo_goods
    остаётся 0 даже при плане товаров > 0 (контроль не срабатывает без
    типизированного ФЭО, владелец: «на категории без типизированного ФЭО
    контроль не срабатывает»)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — план услуг выше ФЭО услуг")
    await _make_planned_item(
        db_session, cat.id, "Ноутбук", 20_000, item_type="товар",
    )  # товар без is_feo_breakdown -> feo_goods=0
    await _make_planned_item(
        db_session, cat.id, "Обслуживание по ФЭО", 30_000, item_type="услуга",
        is_feo_breakdown=True, feo_amount=30_000,
    )
    await _make_planned_item(
        db_session, cat.id, "Доп. услуга сверх ФЭО", 30_000, item_type="услуга",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan_services"] == pytest.approx(60_000.0)
    assert node["feo_services"] == pytest.approx(30_000.0)
    assert node["excess_plan_over_feo_services"] == pytest.approx(30_000.0)
    assert not node["excess_plan_over_feo_services_approved"]

    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["excess_plan_over_feo_goods"] == pytest.approx(0.0), (
        "без типизированного ФЭО по товарам контроль не должен подниматься"
    )


@pytest.mark.asyncio
async def test_excess_fact_over_plan_goods_from_purchase_items(db_session, test_org):
    """(4) Факт по товарам (80к, закупка work_in_progress) выше плана по
    товарам (50к) -> excess_fact_over_plan_goods > 0; факт по услугам в плане
    -> excess_fact_over_plan_services остаётся 0."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — факт товаров выше плана")
    await _make_planned_item(db_session, cat.id, "Ноутбуки (план)", 50_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Обслуживание (план)", 40_000, item_type="услуга")

    await _make_purchase_item(db_session, subsidy.id, cat.id, "Ноутбуки (факт)", "товар", 80_000)
    await _make_purchase_item(db_session, subsidy.id, cat.id, "Обслуживание (факт)", "услуга", 20_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["fact_goods"] == pytest.approx(80_000.0)
    assert node["fact_services"] == pytest.approx(20_000.0)
    assert node["excess_fact_over_plan_goods"] == pytest.approx(30_000.0)
    assert node["excess_fact_over_plan_services"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_subsidy_level_summary_sums_root_nodes(db_session, test_org):
    """(5) compute_subsidy_type_summary.totals — сумма КОРНЕВЫХ узлов дерева по
    типу (двух независимых категорий верхнего уровня)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Категория А")
    await _make_planned_item(db_session, cat_a.id, "Товар А", 100_000, item_type="товар")
    cat_b = await _make_category(db_session, subsidy.id, name="Категория Б")
    await _make_planned_item(db_session, cat_b.id, "Услуга Б", 40_000, item_type="услуга")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)

    assert summary["totals"]["plan_goods"] == pytest.approx(100_000.0)
    assert summary["totals"]["plan_services"] == pytest.approx(40_000.0)
    assert "plan_over_feo_goods" in summary["excess"]
    assert "fact_over_plan_services" in summary["excess"]


@pytest.mark.asyncio
async def test_order_substituted_plan_reconciles_by_type(db_session, test_org):
    """Исправление 2026-09-21 (боевой замер «ЦентрПоиск_2026»: split плана
    БЫЛ БОЛЬШЕ planned_tree на 18,8 млн) — когда узел заказан ПОЛНОСТЬЮ
    (qty > 0 and ordered_qty >= qty), node['plan'] замещается фактической
    суммой заказа (_order_substituted_plan) вместо Σ FeoPlannedItem.amount.
    Типовой split (plan_goods/services/unspecified) обязан замещаться ТЕМИ ЖЕ
    типизированными суммами заказа (ordered_goods/services из
    ordered_consumption_by_category), а не оставаться «сырой» Σ позиций плана —
    иначе split (140 000, сумма плановых позиций) расходится с node['display']
    (125 000, сумма РЕАЛЬНО заказанного — заказано дешевле плана, экономия
    высвобождена)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(
        db_session, subsidy.id, name="Узел — заказ замещает план", planned_quantity=Decimal("2"),
    )
    await _make_planned_item(db_session, cat.id, "Ноутбук (план)", 100_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Обслуживание (план)", 40_000, item_type="услуга")

    # Заказано ПОЛНОСТЬЮ (2 шт из 2), но ДЕШЕВЛЕ плана — экономия 15 000.
    await _make_purchase_item(
        db_session, subsidy.id, cat.id, "Ноутбук (заказ)", "товар", 90_000, status="ordered",
    )
    await _make_purchase_item(
        db_session, subsidy.id, cat.id, "Обслуживание (заказ)", "услуга", 35_000, status="ordered",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan"] == pytest.approx(125_000.0), "план замещён фактически заказанной суммой (экономия высвобождена)"
    assert node["display"] == pytest.approx(125_000.0), "budget не задан, over=0 -> display == plan"
    assert node["plan_goods"] == pytest.approx(90_000.0)
    assert node["plan_services"] == pytest.approx(35_000.0)
    assert node["plan_unspecified"] == pytest.approx(0.0)
    total_split = node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]
    assert total_split == pytest.approx(node["display"]), "Правило №6: split обязан суммироваться в scalar узла"


@pytest.mark.asyncio
async def test_explicit_budget_mismatched_with_plan_goes_entirely_unspecified(db_session, test_org):
    """ОТМЕНЕНО решение владельца 06.10.2026 (субсидия ХО id 75, «budget без
    typed-разбивки делится по долям плана») — владелец 14.10.2026 (субсидия
    «ДНР_Правильная» id 98, статья «Прочие расходы»): «я не приравнял
    плановую к ФЭО, я просто ввёл сумму — ты самовольно разбил, не надо».
    Категория с явным FeoCategory.budget, НЕ совпадающим с Σ плана её
    позиций (300 000 ≠ 150 000, хоть все позиции одного типа) -> весь budget
    ЦЕЛИКОМ в feo_unspecified, БЕЗ деления по типам; feo_split_explicit —
    None (подписи «из чего бюджет вида» в этом случае нет вообще)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — своя сумма", budget=Decimal("300000"))
    await _make_planned_item(db_session, cat.id, "Ноутбук", 100_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Принтер", 50_000, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["feo_services"] == pytest.approx(0.0)
    assert node["feo_unspecified"] == pytest.approx(300_000.0)
    assert node["feo_split_explicit"] is None


@pytest.mark.asyncio
async def test_explicit_budget_mismatched_with_budgeted_typed_child_no_negative_contribution(db_session, test_org):
    """ИСПРАВЛЕНИЕ (координатор, 14.10.2026, прод ФАДМ 2026_2 id 89, статья
    «Организация мероприятий») — родитель со СВОЕЙ суммой ФЭО, НЕ приравненной
    к своему плану (500 000, свой пул — план-позиция «Услуга родителя» 50 000,
    остаток для своего пула = 500000-100000(ФЭО ребёнка)=400000 ≠ 50000, не
    приравнено -> остаток целиком unspecified), ПЛЮС бюджетная typed-
    подкатегория (своё ФЭО 100 000, приравнено к своему плану, goods) —
    typed-часть ребёнка входит в разбивку родителя КАК ЕСТЬ (goods=100000),
    остаток 400 000 -> unspecified; Σ видов узла == budget родителя (600000
    не пишется явно — видно по budget=500000 родителя + 100000 ребёнка, но
    node['feo_X'] родителя — ТОЛЬКО 500000, т.к. сумма по дереву состоит из
    own(500000, не включает ребёнка в budget-поле, только в разбивку) — целевая
    проверка здесь: own-доля родителя по КАЖДОМУ виду ≥ 0 (не отрицательна),
    это и было боевым баг-репортом (товары -1 502 840 / услуги -1 998 925,60
    на реальных данных)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    parent = await _make_category(db_session, subsidy.id, name="Организация мероприятий", budget=Decimal("500000"))
    await _make_planned_item(db_session, parent.id, "Услуга родителя", 50_000, item_type="услуга")
    child = await _make_category(
        db_session, subsidy.id, parent_id=parent.id, name="Подкатегория — своё ФЭО (товары)", budget=Decimal("100000"),
    )
    await _make_planned_item(db_session, child.id, "Товар подкатегории", 100_000, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_parent = tree[parent.id]
    node_child = tree[child.id]

    assert node_child["feo_goods"] == pytest.approx(100_000.0)
    # Родитель: typed-часть ребёнка (100000 goods) входит как есть; остаток
    # (500000-100000=400000) не совпадает со своим пулом (50000 услуг) ->
    # остаток целиком unspecified.
    assert node_parent["feo_goods"] == pytest.approx(100_000.0)
    assert node_parent["feo_services"] == pytest.approx(0.0)
    assert node_parent["feo_unspecified"] == pytest.approx(400_000.0)
    total_parent = node_parent["feo_goods"] + node_parent["feo_services"] + node_parent["feo_payroll"] + node_parent["feo_unspecified"]
    assert total_parent == pytest.approx(500_000.0), "инвариант: Σ видов узла == его явный budget"

    # Цель координатора: own-доля родителя (node_parent − node_child по
    # КАЖДОМУ виду, см. feo_card_drill.py::_own_contribution) НЕ отрицательна.
    for k in ("feo_goods", "feo_services", "feo_payroll"):
        own = node_parent[k] - node_child[k]
        assert own >= -0.005, f"{k}: own-доля родителя отрицательна ({own})"


@pytest.mark.asyncio
async def test_explicit_budget_aligned_with_plan_splits_by_pool_shares(db_session, test_org):
    """Решение владельца 14.10.2026 — правило «доля плана» ОСТАЁТСЯ, но
    ТОЛЬКО когда budget узла РАВЕН Σ пула плановых позиций до копейки (узел
    «приравнял» ФЭО к плану). Смешанная категория (план 60к товары / 30к
    услуги / 10к работа->услуга / 5к без типа = 105к пула), budget == 105 000
    (== Σ пула) -> split = САМ пул по корзинам (не пропорция от чужой суммы),
    goods=60к, services=40к (услуга+работа), unspecified=5к — Σ частей ==
    budget точно до копейки, feo_split_explicit несёт тот же pool/aligned."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — приравнена к плану", budget=Decimal("105000"))
    await _make_planned_item(db_session, cat.id, "Товар", 60_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Услуга", 30_000, item_type="услуга")
    await _make_planned_item(db_session, cat.id, "Работа", 10_000, item_type="работа")  # -> услуга
    await _make_planned_item(db_session, cat.id, "Без типа", 5_000, item_type=None)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["feo_goods"] == pytest.approx(60_000.0)
    assert node["feo_services"] == pytest.approx(40_000.0)
    assert node["feo_unspecified"] == pytest.approx(5_000.0)
    total = node["feo_goods"] + node["feo_services"] + node["feo_unspecified"]
    assert total == pytest.approx(105_000.0), "инвариант: сумма частей == budget, до копейки"
    info = node["feo_split_explicit"]
    assert info is not None and info.get("aligned") is True


@pytest.mark.asyncio
async def test_feo_split_explicit_exposes_budget_and_pool_for_owner_caption(db_session, test_org):
    """Задача владельца «Б, продолжение» (13.10.2026) — окно «Свободно —
    товары/услуги» должно показать «из чего бюджет вида» (сумма ФЭО группы ×
    доля вида в плане, плюс строка «без типа»). node['feo_split_explicit']
    обязан нести ТЕ ЖЕ budget и pool, которыми _feo_by_kind реально поделил
    budget (ПРАВИЛО №6 — фронт не считает долю второй раз)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — ДНР5-подобная", budget=Decimal("1000000"))
    await _make_planned_item(db_session, cat.id, "Товар", 600_000, item_type="товар")
    await _make_planned_item(db_session, cat.id, "Услуга", 300_000, item_type="услуга")
    await _make_planned_item(db_session, cat.id, "Без типа", 100_000, item_type=None)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    info = node["feo_split_explicit"]
    assert info is not None
    assert info["budget"] == pytest.approx(1_000_000.0)
    assert info["pool"]["goods"] == pytest.approx(600_000.0)
    assert info["pool"]["services"] == pytest.approx(300_000.0)
    assert info["pool"]["unspecified"] == pytest.approx(100_000.0)
    total_pool = sum(info["pool"].values())
    assert total_pool == pytest.approx(1_000_000.0)
    # Доля товаров/услуг/без типа из ЭТОГО же pool обязана дать то же число,
    # что node['feo_goods']/['feo_services']/['feo_unspecified'] (сверка, что
    # подпись и реальный расчёт используют одни и те же числа).
    assert info["budget"] * info["pool"]["goods"] / total_pool == pytest.approx(node["feo_goods"])
    assert info["budget"] * info["pool"]["services"] / total_pool == pytest.approx(node["feo_services"])
    assert info["budget"] * info["pool"]["unspecified"] / total_pool == pytest.approx(node["feo_unspecified"])


@pytest.mark.asyncio
async def test_feo_split_explicit_is_none_when_no_own_budget(db_session, test_org):
    """Узел БЕЗ своей явной суммы ФЭО (budget=None) — подписи «из чего
    бюджет» не может быть вообще (нечего делить своей долей) — None, не 0/
    пустой словарь, чтобы фронт отличал «нет данных» от «доля 0%»."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — без своего ФЭО", budget=None)
    await _make_planned_item(db_session, cat.id, "Товар", 100_000, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["feo_split_explicit"] is None


@pytest.mark.asyncio
async def test_explicit_budget_outranks_own_breakdown_rows_even_if_they_disagree(db_session, test_org):
    """Категория с ОБОИМИ источниками — явный FeoCategory.budget И собственные
    is_feo_breakdown-строки с типом — budget узла ГЛАВНЕЕ (own_feo_by_kind в
    этой ветке не читается вообще, как и раньше). Боевой кейс «ДНР» (id 61,
    кат. 4853 «Ремонт ТС»): budget 863 979,59, Σ is_feo_breakdown-строк
    441 579,59 — РАСХОДЯТСЯ. Решение владельца 14.10.2026 (отменяет 06.10.2026
    «делить по долям строк») — budget (900к) != Σ плановых сумм тех же строк
    (100к) -> ТЕПЕРЬ целиком в unspecified (не делится по их долям), own
    typed-строки ФЭО не играют роли, когда budget узла задан явно и не
    совпадает с планом."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — budget и неполные строки ФЭО", budget=Decimal("900000"))
    await _make_planned_item(
        db_session, cat.id, "Товар (по ФЭО, неполная строка)", 70_000, item_type="товар",
        is_feo_breakdown=True, feo_amount=70_000,
    )
    await _make_planned_item(
        db_session, cat.id, "Услуга (по ФЭО, неполная строка)", 30_000, item_type="услуга",
        is_feo_breakdown=True, feo_amount=30_000,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["feo_services"] == pytest.approx(0.0)
    assert node["feo_unspecified"] == pytest.approx(900_000.0)
    total = node["feo_goods"] + node["feo_services"] + node["feo_unspecified"]
    assert total == pytest.approx(900_000.0), "инвариант: сумма частей == budget узла"


@pytest.mark.asyncio
async def test_explicit_budget_without_items_stays_unspecified(db_session, test_org):
    """Категория без собственных плановых позиций (и без строк ФЭО) с явным
    budget -> «без разбивки», budget целиком в feo_unspecified (не 0/0 «нет
    данных» — само число есть, просто не по типам)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — без позиций", budget=Decimal("777000"))

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["feo_goods"] == pytest.approx(0.0)
    assert node["feo_services"] == pytest.approx(0.0)
    assert node["feo_unspecified"] == pytest.approx(777_000.0)


@pytest.mark.asyncio
async def test_explicit_budget_split_excludes_subcategory_with_own_budget(db_session, test_org):
    """Родитель с явным budget и плановыми позициями «товар» в подкатегории,
    у которой СВОЙ явный budget — позиции подкатегории НЕ входят в ПУЛ
    родителя (владелец: «без двойного счёта по дереву»); подкатегория
    получает собственный split по СВОИМ позициям, И её typed-ФЭО (10 000,
    goods) входит в разбивку родителя КАК ЕСТЬ (ИСПРАВЛЕНИЕ, координатор
    14.10.2026, прод ФАДМ 2026_2 id 89 — иначе own-доля родителя в
    feo_card_drill.py::_own_contribution получает отрицательный вклад на
    typed-ФЭО ребёнка, см. docstring _feo_by_kind). Родительский budget
    60 000 = остаток 50 000 (приравнен к своему пулу «услуга родителя») +
    10 000 ребёнка."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    parent = await _make_category(db_session, subsidy.id, name="Родитель", budget=Decimal("60000"))
    await _make_planned_item(db_session, parent.id, "Услуга родителя", 50_000, item_type="услуга")
    child = await _make_category(
        db_session, subsidy.id, parent_id=parent.id, name="Подкатегория со своим budget", budget=Decimal("10000"),
    )
    await _make_planned_item(db_session, child.id, "Товар подкатегории", 10_000, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_parent = tree[parent.id]
    node_child = tree[child.id]

    # Подкатегория: свой budget, свой пул (товар) -> весь в товары.
    assert node_child["feo_goods"] == pytest.approx(10_000.0)
    assert node_child["feo_services"] == pytest.approx(0.0)
    # Родитель: остаток (60000-10000=50000) приравнен к своему пулу (услуга)
    # -> 50000 в услуги, ПЛЮС typed-ФЭО ребёнка (10000 товары) как есть —
    # node['feo_goods'] родителя КУМУЛЯТИВНО включает ребёнка (own-доля
    # родителя в feo_card_drill.py не должна уйти в минус).
    assert node_parent["feo_goods"] == pytest.approx(10_000.0)
    assert node_parent["feo_services"] == pytest.approx(50_000.0)
    own_parent_goods = node_parent["feo_goods"] - node_child["feo_goods"]
    own_parent_services = node_parent["feo_services"] - node_child["feo_services"]
    assert own_parent_goods == pytest.approx(0.0), "own-доля родителя по товарам НЕ отрицательна"
    assert own_parent_services == pytest.approx(50_000.0)


@pytest.mark.asyncio
async def test_subsidy_without_any_feo_stays_zero_by_type(db_session, test_org):
    """ОТМЕНЕНО решение владельца 06.10.2026 (прод — субсидия ХО id 75,
    «Бюджет (ФЭО) по типу = План по типу» для субсидии без сумм ФЭО) —
    владелец 07.10.2026 (план .planning/quick/2026-10-07-dnr-feo-cards/
    PLAN.md шаг 1, решение №3, найдено на субсидии «ДНР»): подмена плана
    бюджетом теряла позиции, привязанные прямо к статье с подкатегориями
    (см. докстринг _feo_by_kind) и маскировала «ФЭО не введено» как настоящий
    бюджет. СУБСИДИЯ ЦЕЛИКОМ без сумм ФЭО теперь честно 0/0 по каждому типу —
    «Бюджет (ФЭО)» не считается вовсе (feo_entered=False на карточке, см.
    subsidy_money_summary.py), план по типу — отдельное, непустое число."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat_a = await _make_category(db_session, subsidy.id, name="Статья А (без ФЭО)")
    await _make_planned_item(db_session, cat_a.id, "Товар", 70_000, item_type="товар")
    cat_b = await _make_category(db_session, subsidy.id, name="Статья Б (без ФЭО)")
    await _make_planned_item(db_session, cat_b.id, "Услуга", 30_000, item_type="услуга")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])

    assert tree[cat_a.id]["feo_goods"] == pytest.approx(0.0)
    assert tree[cat_a.id]["feo_services"] == pytest.approx(0.0)
    assert tree[cat_b.id]["feo_goods"] == pytest.approx(0.0)
    assert tree[cat_b.id]["feo_services"] == pytest.approx(0.0)

    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
    assert summary["totals"]["feo_goods"] == pytest.approx(0.0)
    assert summary["totals"]["feo_services"] == pytest.approx(0.0)
    # План по типу считается независимо и НЕ пуст — «Бюджет (ФЭО)» просто не
    # подставляется вместо него.
    assert summary["totals"]["plan_goods"] == pytest.approx(70_000.0)
    assert summary["totals"]["plan_services"] == pytest.approx(30_000.0)


@pytest.mark.asyncio
async def test_subsidy_with_partial_feo_does_not_fall_back_for_empty_category(db_session, test_org):
    """Боевой замер «ФАДМ 2026_2» (id 7320): субсидия с ЧАСТИЧНОЙ разбивкой —
    одна категория с явной is_feo_breakdown-строкой (реальное ФЭО), ДРУГАЯ
    категория ТОЙ ЖЕ субсидии без единой суммы ФЭО, но с планом. Фолбэк
    «бюджет по типу = план по типу» НЕ должен сработать для второй категории
    (иначе Σ типов превысит calculate_budgets_bulk — задвоение) — она
    остаётся «без разбивки» (feo_unspecified=0, т.к. budget тоже не задан),
    как и раньше."""
    from app.services.subsidy_budget import calculate_budgets_bulk

    subsidy = await _make_subsidy(db_session, test_org.id, budget=0)
    cat_typed = await _make_category(db_session, subsidy.id, name="Статья с ФЭО-строкой")
    await _make_planned_item(
        db_session, cat_typed.id, "Товар (по ФЭО)", 90_000, item_type="товар",
        is_feo_breakdown=True, feo_amount=90_000,
    )
    cat_empty = await _make_category(db_session, subsidy.id, name="Статья без ФЭО (сосед)")
    await _make_planned_item(db_session, cat_empty.id, "Услуга (план, без ФЭО)", 40_000, item_type="услуга")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])

    assert tree[cat_typed.id]["feo_goods"] == pytest.approx(90_000.0)
    assert tree[cat_empty.id]["feo_goods"] == pytest.approx(0.0)
    assert tree[cat_empty.id]["feo_services"] == pytest.approx(0.0), (
        "фолбэк на план НЕ срабатывает — у субсидии ЕСТЬ ФЭО (в соседней категории)"
    )

    totals = await subsidy_type_totals_for(db_session, subsidy.id)
    budget_scalar = (await calculate_budgets_bulk(db_session, [subsidy.id]))[subsidy.id]
    assert totals["feo_goods"] + totals["feo_services"] + totals["feo_unspecified"] == pytest.approx(budget_scalar), (
        "Правило №6: Σ частей не должна превышать calculate_budgets_bulk (никакого задвоения)"
    )


async def subsidy_type_totals_for(db_session, subsidy_id):
    from app.services.type_totals import subsidy_type_totals
    return (await subsidy_type_totals(db_session, [subsidy_id]))[subsidy_id]


@pytest.mark.asyncio
async def test_over_plan_purchase_item_included_in_type_split(db_session, test_org):
    """over_plan=true позиции закупки прибавляются к node['plan'] БЕЗУСЛОВНО
    (over, см. docstring compute_feo_plan_tree) — типовой split обязан
    прибавлять ТУ ЖЕ типизированную сумму (over_goods/services из
    plan_consumption_by_category), иначе split (только план, без over)
    расходится с node['display'] (план + over)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Узел — сверх плана")
    await _make_planned_item(db_session, cat.id, "Ноутбук (план)", 50_000, item_type="товар")

    await _make_purchase_item(
        db_session, subsidy.id, cat.id, "Доп. услуга сверх плана", "услуга", 20_000,
        status="work_in_progress", over_plan=True,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]

    assert node["plan"] == pytest.approx(50_000.0), "план БЕЗ over (over прибавляется отдельно к full_display)"
    assert node["over"] == pytest.approx(20_000.0)
    assert node["display"] == pytest.approx(70_000.0), "display = plan + over"
    assert node["plan_goods"] == pytest.approx(50_000.0)
    assert node["plan_services"] == pytest.approx(20_000.0), "over-строка типа «услуга» добавлена в plan_services"
    assert node["plan_unspecified"] == pytest.approx(0.0)
    total_split = node["plan_goods"] + node["plan_services"] + node["plan_unspecified"]
    assert total_split == pytest.approx(node["display"]), "Правило №6: split обязан суммироваться в scalar узла"
