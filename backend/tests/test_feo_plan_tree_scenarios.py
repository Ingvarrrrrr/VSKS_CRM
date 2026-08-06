"""ШАГ 0 (план «план ≠ факт», zany-fluttering-mountain.md): baseline + два кандидата
на боевые 16 760 000 у категории «Внедорожник повышенной проходимости».

Сценарий владельца (везде цена ЗА ЕДИНИЦУ):
  ФЭО: 2 ед × 4 000 000/ед = 8 000 000 (budget категории).
  План закупок: плановая позиция Great Wall POER — 2 шт × 4 000 000/ед = 8 000 000.
  Заявка: 2 шт × 4 000 000, ПРИВЯЗАНА к плановой позиции (feo_planned_item_id,
    over_plan=false) → согласование → закупка.
  По итогам закупки цена стала 4 190 000/ед (8 380 000 за 2 шт).

test_baseline_* воспроизводит это через ORM (тот же путь данных, что и реальный
approve заявки — см. app.routers.wishes._distribute_wish_to_purchases:605-624,
PurchaseItem.wish_item_id/feo_planned_item_id/over_plan копируются 1:1) и
подтверждает: с текущей формулой (feo_plan.py, exclude_planned_item_linked=True
для позиций, привязанных к FeoPlannedItem) правка цены позиции закупки НЕ
двигает plan_manual/display категории — сумма расходов по итогам закупки для
привязанной позиции полностью исключена из plan_consumption_by_category и
ordered_consumption_by_category. Подтверждено так же живым сценарием на
локальном docker-стенде через HTTP API (POST /api/wishes → submit → approve →
PUT цены → re-submit/approve): GET /api/feo-categories/plan-tree ДО и ПОСЛЕ
правки цены дал одинаковый display=8 000 000, excess_amount=0.

test_k1_* и test_k2_* воспроизводят оба независимых кандидата на боевые
16 760 000 (см. Context плана): K1 — сумма записана в поле «цена за единицу»
категории; K2 — под категорией две активные FeoPlannedItem по 8 380 000 (когда
planned_quantity/planned_amount категории не заполнены, план держится только на
уровне позиций — см. leaf_item_amt fallback в compute_feo_plan_tree). Оба дали
на локальном стенде через тот же живой API display=16 760 000,
excess_amount=8 760 000 — точное совпадение со скриншотом владельца.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.feo_plan import compute_feo_plan_tree


async def _make_subsidy(db_session, org_id, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
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


async def _make_planned_item(db_session, feo_category_id, name, quantity, amount, is_active=True):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        is_active=is_active,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_purchase_with_linked_item(
    db_session, subsidy_id, feo_category_id, feo_planned_item_id,
    quantity, unit_price, wish_item_id=None,
):
    """Строит Purchase+PurchaseItem как approve заявки (wishes.py:605-624) копирует
    их из WishItem: feo_planned_item_id + over_plan=False — именно эта комбинация
    исключает позицию из plan_consumption_by_category/ordered_consumption_by_category
    (exclude_planned_item_linked=True), что и проверяет этот тест. wish_item_id
    оставлен настраиваемым (по умолчанию None, чтобы не требовать реальной строки
    wish_items — FK на неё; сама формула compute_feo_plan_tree это поле не читает)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    total = Decimal(str(quantity)) * Decimal(str(unit_price))
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Great Wall POER",
        status="plan_schedule",
        planned_quantity=Decimal(str(quantity)),
        planned_total_price=total,
        total_nmck=total,
        nmck=total,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Great Wall POER",
        quantity=Decimal(str(quantity)),
        unit="шт",
        unit_price=Decimal(str(unit_price)),
        total_price=total,
        feo_category_id=feo_category_id,
        feo_planned_item_id=feo_planned_item_id,
        over_plan=False,
        wish_item_id=wish_item_id,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_baseline_plan_unaffected_by_linked_item_price(db_session, test_org):
    """Эталонный сценарий владельца: план = 8 000 000, не двигается правкой цены
    привязанной позиции закупки (4 000 000/ед → 4 190 000/ед)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    group = await _make_category(db_session, subsidy.id, name="Внедорожник повышенной проходимости")
    leaf = await _make_category(
        db_session, subsidy.id, parent_id=group.id,
        name="Great Wall POER (лист)",
        budget=Decimal("8000000"),
        feo_quantity=Decimal("2"),
        feo_amount=Decimal("4000000"),
        planned_quantity=Decimal("2"),
        planned_amount=Decimal("4000000"),
        unit="шт",
    )
    fpi = await _make_planned_item(db_session, leaf.id, "Great Wall POER", 2, 8_000_000)

    tree_before_purchase = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree_before_purchase[leaf.id]
    assert node["plan_manual"] == 8_000_000.0
    assert node["display"] == 8_000_000.0
    assert node["budget"] == 8_000_000.0
    assert node["excess_amount"] == 0.0

    purchase, item = await _make_purchase_with_linked_item(
        db_session, subsidy.id, leaf.id, fpi.id, quantity=2, unit_price=4_000_000,
    )

    tree_after_purchase = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree_after_purchase[leaf.id]
    assert node["display"] == 8_000_000.0
    assert node["excess_amount"] == 0.0

    # По итогам закупки цена стала 4 190 000/ед (8 380 000 за 2 шт) — как правил владелец.
    item.unit_price = Decimal("4190000")
    item.total_price = Decimal("8380000")
    await db_session.commit()

    tree_after_price_bump = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree_after_price_bump[leaf.id]
    assert node["plan_manual"] == 8_000_000.0, (
        "план обязан остаться 8 000 000 — привязанная позиция исключена из "
        "consumption через exclude_planned_item_linked=True"
    )
    assert node["display"] == 8_000_000.0
    assert node["excess_amount"] == 0.0
    assert node["budget"] == 8_000_000.0


@pytest.mark.asyncio
async def test_k1_sum_stored_in_per_unit_price_field(db_session, test_org):
    """К1: feo_categories.planned_amount хранит СУММУ (8 380 000) вместо цены за
    единицу при planned_quantity=2 → display = 2 × 8 380 000 = 16 760 000
    (точное совпадение с боевым скриншотом владельца)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    group = await _make_category(db_session, subsidy.id, name="Внедорожник повышенной проходимости")
    leaf = await _make_category(
        db_session, subsidy.id, parent_id=group.id,
        name="K1 — сумма в поле цены за ед.",
        budget=Decimal("8000000"),
        feo_quantity=Decimal("2"),
        feo_amount=Decimal("4000000"),
        planned_quantity=Decimal("2"),
        planned_amount=Decimal("8380000"),  # БАГ: сюда записали сумму, а не цену за ед.
        unit="шт",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 16_760_000.0
    assert node["display"] == 16_760_000.0
    assert node["budget"] == 8_000_000.0
    assert node["excess_amount"] == 8_760_000.0


@pytest.mark.asyncio
async def test_k2_duplicate_planned_items(db_session, test_org):
    """К2: под категорией ДВЕ активные FeoPlannedItem по 8 380 000 (исходная не
    деактивирована + созданная по фактической цене), categorization
    planned_quantity/planned_amount категории НЕ заполнены (план держится
    только на уровне позиций) → fallback на Σ FeoPlannedItem.amount = 16 760 000
    (точное совпадение с боевым скриншотом владельца)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    group = await _make_category(db_session, subsidy.id, name="Внедорожник повышенной проходимости")
    leaf = await _make_category(
        db_session, subsidy.id, parent_id=group.id,
        name="K2 — дубль плановых позиций",
        budget=Decimal("8000000"),
        feo_quantity=Decimal("2"),
        feo_amount=Decimal("4000000"),
        # planned_quantity/planned_amount намеренно не заданы (NULL) — план введён позициями.
        unit="шт",
    )
    await _make_planned_item(db_session, leaf.id, "Great Wall POER", 2, 8_380_000)
    await _make_planned_item(db_session, leaf.id, "Great Wall POER (факт)", 2, 8_380_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 16_760_000.0
    assert node["display"] == 16_760_000.0
    assert node["budget"] == 8_000_000.0
    assert node["excess_amount"] == 8_760_000.0
