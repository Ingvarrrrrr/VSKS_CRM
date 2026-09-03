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
    """К1 — ПЕРЕПИСАН 2026-09-03 под действующую модель (см. задача 1, отчёт
    сессии). Что проверялось раньше: тест написан 2026-08-07 (коммит a8b6557)
    и до сих пор был построен на формуле «лист: plan_manual = planned_quantity ×
    planned_amount» — сценарий: feo_categories.planned_amount хранит СУММУ
    (8 380 000) вместо цены за единицу при planned_quantity=2, из-за чего
    произведение задваивало план: 2 × 8 380 000 = 16 760 000.

    Почему формула изменилась: коммитом f8d68bc (2026-08-13, «способ расчёта
    задаётся переключателем, а не угадывается по пустым полям») эта
    qty×amount-формула УДАЛЕНА из compute_feo_plan_tree. Поля
    planned_quantity/planned_amount листа больше НЕ участвуют в расчёте
    plan_manual вообще (planned_quantity используется только как ориентир
    количества для замещения «заказ вместо плана», сумма — никогда). Способ
    расчёта плана листа теперь задаётся явным полем FeoCategory.plan_source:
    'planned_items' (умолчание) — Σ активных FeoPlannedItem, 'manual_sum' —
    ОДНО число FeoCategory.manual_plan_amount (см. _manual_plan_for в
    feo_plan.py). Живых данных под старый сценарий (qty×amount с обоими
    непустыми полями при отсутствии FeoPlannedItem) в базе не осталось —
    миграция q5r6s7t8u9v0 перевела все 214 похожих листьев в 'manual_sum' с
    manual_plan_amount, совпадающим с planned_quantity×planned_amount до
    копейки (проверено отдельно, см. отчёт задачи 1).

    Что проверяется теперь: тот же смысл сценария владельца («число, которое
    должно было означать одно, по ошибке легло как весь план целиком, и план
    раздулся мимо бюджета») выражен ЧЕРЕЗ ДЕЙСТВУЮЩИЙ переключатель —
    plan_source='manual_sum' с manual_plan_amount, В КОТОРОЕ по ошибке внесли
    итоговую сумму 16 760 000 (а не то меньшее число, которое соответствовало
    бы плану 2×4 000 000). Числа боевого скриншота владельца (display
    16 760 000, excess_amount 8 760 000 при budget 8 000 000) сохранены как
    контрольные — 'manual_sum' без активных FeoPlannedItem не участвует в
    отдельном механизме excess_plan_over_manual (тот сравнивает Σ позиций с
    manual_plan_amount, тут позиций нет вовсе), поэтому раздувание плана
    проверяется тем же способом, что и раньше — excess_amount (план > budget
    узла)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    group = await _make_category(db_session, subsidy.id, name="Внедорожник повышенной проходимости")
    leaf = await _make_category(
        db_session, subsidy.id, parent_id=group.id,
        name="K1 — сумма вручную введена в manual_plan_amount по ошибке",
        budget=Decimal("8000000"),
        feo_quantity=Decimal("2"),
        feo_amount=Decimal("4000000"),
        plan_source="manual_sum",
        manual_plan_amount=Decimal("16760000"),  # БАГ: по ошибке весь итог, а не план 2×4 000 000
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


@pytest.mark.asyncio
async def test_find_excess_culprit_matches_compute_feo_plan_tree_planned_items(db_session, test_org):
    """Задача 2 (2026-09-03, отчёт сессии): find_excess_culprit (объясняет
    пользователю ПРИЧИНУ блокировки excess_amount — «вот эта закупка/позиция
    вывела план за рамки ФЭО») ДО этой задачи считал план листа СВОЕЙ
    собственной REMOVED-формулой (planned_quantity×planned_amount с фолбэком на
    Σ FeoPlannedItem по пустоте полей — та же формула, что убрали из
    compute_feo_plan_tree коммитом f8d68bc, см. докстринг test_k1_* выше) — то
    есть мог назвать пользователю цифру плана, НЕ совпадающую с той, из-за
    которой реально сработала блокировка в compute_feo_plan_tree/
    assert_no_unapproved_excess. Теперь обе функции читают план листа одной и
    той же формулой (feo_plan.py._leaf_plan_manual зеркалит
    compute_feo_plan_tree._manual_plan_for — прямой вызов последней невозможен,
    это closure внутри compute_feo_plan_tree, завязанный на батчевые словари
    всей субсидии).

    Этот тест — режим 'planned_items' (умолчание, план = Σ активных
    FeoPlannedItem): budget листа занижен настолько, что единственная плановая
    позиция сразу пересекает границу. Виновник ОБЯЗАН объяснить превышение ТОЙ
    ЖЕ суммой (cumulative_after), что compute_feo_plan_tree называет
    plan_manual — это и есть критерий приёмки задачи 2."""
    from app.services.feo_plan import find_excess_culprit

    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — план позициями (Ур.5)",
        budget=Decimal("1000000"),  # ниже плана — гарантирует пересечение первой же позицией
        unit="шт",
    )
    await _make_planned_item(db_session, leaf.id, "Позиция плана", 2, 4_000_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 4_000_000.0
    assert node["excess_amount"] > 0

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    assert culprit["cumulative_after"] == node["plan_manual"], (
        "find_excess_culprit обязан объяснять превышение ТОЙ ЖЕ суммой плана, "
        "что compute_feo_plan_tree.plan_manual — иначе виновник называет "
        "число, не совпадающее с тем, из-за которого реально сработала блокировка"
    )


@pytest.mark.asyncio
async def test_find_excess_culprit_matches_compute_feo_plan_tree_manual_sum(db_session, test_org):
    """Тот же критерий, что и в тесте выше (см. его докстринг) — режим
    'manual_sum' БЕЗ активных FeoPlannedItem и БЕЗ согласованного превышения:
    план листа — ОДНО ручное число (manual_plan_amount), find_excess_culprit
    обязан подставить синтетический контрибьютор «плановое значение категории»
    РОВНО с этой суммой (у него нет закупки-источника — само число не
    раскладывается на позиции), совпадающей с compute_feo_plan_tree.plan_manual."""
    from app.services.feo_plan import find_excess_culprit

    subsidy = await _make_subsidy(db_session, test_org.id)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — ручная сумма (Ур.5 нет)",
        budget=Decimal("1000000"),
        plan_source="manual_sum",
        manual_plan_amount=Decimal("16760000"),
        unit="шт",
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 16_760_000.0
    assert node["excess_amount"] > 0

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    assert culprit["purchase_id"] is None, "manual_sum без items не раскладывается на закупки"
    assert culprit["cumulative_after"] == node["plan_manual"], (
        "find_excess_culprit обязан объяснять превышение ТОЙ ЖЕ суммой плана, "
        "что compute_feo_plan_tree.plan_manual — иначе виновник называет "
        "число, не совпадающее с тем, из-за которого реально сработала блокировка"
    )
