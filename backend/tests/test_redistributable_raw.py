"""app.services.redistributable_raw — подстроки карточки «Можно
перераспределить» БЕЗ клэмпа дерева по направлениям (план sleepy-fluttering-
walrus.md, п.1, владелец 06.10.2026).

Контрольный пример владельца (живая находка на проде id=89, категория
«Организация мероприятий», см. отчёт задачи): позиция закупки физически
записана с feo_category_id НАПРАВЛЕНИЯ А (похоже, так завёл импорт), но её
feo_planned_item_id указывает на плановую позицию, которая на самом деле
лежит в НАПРАВЛЕНИИ Б. Committed дерева считается по Purchase/PurchaseItem.
feo_category_id (физическая метка — направление А), а contribution/
committed_by_planned_item — по самой плановой позиции (направление Б).
Направление А из-за этого видит "committed > свой план" (хотя его СОБСТВЕННЫЕ
nice-позиции ни копейкой не тронуты) — compute_feo_plan_tree поднимает «пол
плана» направления А до committed ЦЕЛИКОМ (plan_floor_added), и клэмп
not_committed_nice в [0, planned_not_committed=0] обнуляет nice направления А
полностью, пряча их честный план. Новая raw-формула считает remainder ПО
КАЖДОЙ ПОЗИЦИИ (contribution − committed_by_planned_item ЭТОЙ позиции,
app.services.committed_amounts.planned_item_contributions/
committed_by_planned_item — ПРАВИЛО №6, вторая формула не вводится) — nice-
позиции направления А остаются на своём полном плане независимо от чужого
перерасхода, привязанного к ЧУЖОЙ плановой позиции.

Переиспользует фабрики test_feo_plan_tree_scenarios.py/test_money_committed.py
(ПРАВИЛО №6 — вторая копия не заводится)."""
from decimal import Decimal

import pytest

from app.services.committed_amounts import subsidy_committed_totals
from app.services.feo_plan import compute_feo_plan_tree
from app.services.redistributable_raw import (
    not_committed_raw_by_subsidy,
    not_committed_raw_rows,
    over_plan_categories_by_subsidy,
)
from app.services.stage_cumulative import (
    contracted_not_ordered_by_subsidy,
    contracted_not_ordered_need_level_split,
)
from app.services.subsidy_money_summary import subsidy_money_summary
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_not_committed_raw_isolates_miscategorized_overspend(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=2_000_000)
    cat_a = await _make_category(db_session, subsidy.id, name="Направление А", budget=Decimal("500000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Направление Б", budget=Decimal("1000000"))

    item_nice_1 = await _make_planned_item(db_session, cat_a.id, "Прочие мат.затраты 1", 1, 400_000)
    item_nice_2 = await _make_planned_item(db_session, cat_a.id, "Прочие мат.затраты 2", 1, 100_000)
    item_nice_1.need_level = "nice_to_have"
    item_nice_2.need_level = "nice_to_have"
    item_b = await _make_planned_item(db_session, cat_b.id, "Костюм повседневный", 1, 1_000_000)
    await db_session.commit()

    # Закупка на 1 000 000 физически заведена с feo_category_id=А (ошибка
    # импорта на проде), но привязана (feo_planned_item_id) к плановой
    # позиции направления Б.
    await _make_linked_purchase(db_session, subsidy.id, cat_a.id, item_b.id, 1, 1_000_000)

    # ── Старая (клэмпнутая по узлу) формула: направление А видит committed=
    # 1 000 000 (по физической метке закупки), plan_floor_added поднимает его
    # "план" до committed ЦЕЛИКОМ → planned_not_committed=0 → nice клэмпится
    # в 0, хотя nice1/nice2 не задействованы НИ ОДНОЙ закупкой.
    committed_totals = await subsidy_committed_totals(db_session, [subsidy.id])
    assert committed_totals[subsidy.id]["committed"] == pytest.approx(1_000_000.0)
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree[cat_a.id]["not_committed_nice"] == pytest.approx(0.0)  # старый баг

    # ── Новая raw-формула: nice-позиции направления А остаются на полном
    # плане 500 000 (их СОБСТВЕННЫЙ committed_by_planned_item == 0) — ровно
    # то число, которое владелец сверяет по листу Excel.
    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    row = raw_map[subsidy.id]
    assert row["nice_raw"] == pytest.approx(500_000.0)


@pytest.mark.asyncio
async def test_not_committed_raw_matches_tree_total_without_miscategorization(db_session, test_org):
    """Без путаницы категорий (закупка и её плановая позиция — в ОДНОЙ
    категории, просто перезаконтрактована дороже плана и НЕ закрыта по
    количеству) raw-Σ обязана совпасть с planned_not_committed дерева —
    инвариант не меняется, когда plan_floor не вмешивается."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    cat = await _make_category(db_session, subsidy.id, name="Перерасход в своей категории", budget=Decimal("200000"))
    item = await _make_planned_item(db_session, cat.id, "Партия товара", 2, 200_000)  # 100 000/ед

    # Заказана только 1 из 2 единиц (количество НЕ закрыто — contribution
    # остаётся планом целиком, не committed), но по цене 900 000 за штуку.
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item.id, 1, 900_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["committed"] == pytest.approx(900_000.0)
    assert node["plan"] == pytest.approx(200_000.0)
    old_total = node["not_committed_nice"] + node["not_committed_likely"]
    assert old_total == pytest.approx(200_000.0 - 900_000.0)

    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    row = raw_map[subsidy.id]
    assert row["nice_raw"] + row["likely_raw"] == pytest.approx(old_total)

    # ── Красная строка «законтрактовано сверх плана» — ловит ИМЕННО этот
    # случай (без путаницы категорий, plan_floor не маскирует committed>plan).
    over = await over_plan_categories_by_subsidy(db_session, [subsidy.id])
    over_rows = over[subsidy.id]
    assert len(over_rows) == 1
    assert over_rows[0]["category_id"] == cat.id
    assert over_rows[0]["excess_amount"] == pytest.approx(700_000.0)


@pytest.mark.asyncio
async def test_unlinked_category_purchase_reduces_own_kind_raw(db_session, test_org):
    """ИСПРАВЛЕНО (D2, живая приёмка 21.10.2026, ХРО_2026 id 55): закупка
    привязана К СТАТЬЕ (Purchase/PurchaseItem.feo_category_id), но БЕЗ ЛЮБОЙ
    плановой позиции (PurchaseItem.feo_planned_item_id=None) — 3 закупки ФОТ
    ХРО_2026 («ЗП»/«Отчисления»/«Командировочные») заведены ровно так.
    committed такой закупки уже входит в «законтрактовано» дерева/субсидии
    (compute_feo_plan_tree/subsidy_committed_totals), но раньше не вычиталось
    из raw-разбивки по виду (ни в карточке, ни в расшифровке) — Σ строк была
    БОЛЬШЕ итога карточки ровно на эту сумму."""
    from app.models.feo_category import FeoCategory as _FC

    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    payroll_cat = await _make_category(db_session, subsidy.id, name="ФОТ", budget=Decimal("500000"))
    await db_session.execute(
        _FC.__table__.update().where(_FC.id == payroll_cat.id).values(is_payroll=True)
    )
    await db_session.commit()
    # quantity=5 (НЕ 1) — нарочно НЕ совпадает с quantity закупки ниже:
    # order_substituted_plan (feo_plan_tree.py, замещение «план → факт
    # договора» по СОВПАДАЮЩЕМУ количеству в категории, независимо от
    # feo_planned_item_id) иначе подменил бы node['plan'] категории на сумму
    # закупки САМ (другой, более старый механизм, не предмет этой правки) —
    # тест должен бить ТОЧНО по D2 (committed_by_planned_item/raw), не по
    # этому соседнему механизму.
    item_nice = await _make_planned_item(db_session, payroll_cat.id, "Резерв ФОТ", 5, 500_000)
    item_nice.need_level = "nice_to_have"
    await db_session.commit()

    # Закупка на статью ФОТ — НЕ привязана ни к одной плановой позиции.
    await _make_linked_purchase(db_session, subsidy.id, payroll_cat.id, None, 1, 200_000)

    rows_map = await not_committed_raw_rows(db_session, [subsidy.id])
    unlinked_rows = [r for r in rows_map[subsidy.id] if r["planned_item_id"] is None]
    assert len(unlinked_rows) == 1
    assert unlinked_rows[0]["kind"] == "payroll"
    assert unlinked_rows[0]["raw"] == pytest.approx(-200_000.0)

    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    row = raw_map[subsidy.id]
    # Плановая позиция ФОТ не тронута (её собственный committed_by_planned_item==0).
    assert row["nice_raw"] == pytest.approx(500_000.0)
    # Закупка без плановой позиции уходит в likely (своего вида — payroll),
    # отрицательной строкой — не задвоена со своей плановой позицией.
    assert row["likely_raw"] == pytest.approx(-200_000.0)
    assert row["by_kind"]["payroll"] == pytest.approx(300_000.0)  # 500 000 - 200 000

    # Карточка: redistributable_by_kind['payroll'] читает ТУ ЖЕ Σ (не вторая
    # формула) — тот же контракт «строка расшифровки = число карточки», что
    # test_redistributable_drill.py проверяет для обычных (линкованных)
    # позиций. Σ by_kind здесь без дополнительной «не запланировано»-надбавки
    # (budget==planned в этом фикстурном сценарии), поэтому сверяется напрямую.
    summary = await subsidy_money_summary(db_session, [subsidy.id])
    card = summary[subsidy.id]
    by_kind = card["redistributable_by_kind"]
    assert by_kind["payroll"] == pytest.approx(300_000.0)


@pytest.mark.asyncio
async def test_contracted_not_ordered_empty_without_framework_children(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    result = await contracted_not_ordered_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert result[subsidy.id] == 0.0


@pytest.mark.asyncio
async def test_over_plan_categories_empty_when_within_plan(db_session, test_org):
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    cat = await _make_category(db_session, subsidy.id, name="В рамках плана", budget=Decimal("500000"))
    item = await _make_planned_item(db_session, cat.id, "Товар", 1, 500_000)
    await _make_linked_purchase(db_session, subsidy.id, cat.id, item.id, 1, 100_000)

    over = await over_plan_categories_by_subsidy(db_session, [subsidy.id])
    assert over[subsidy.id] == []


@pytest.mark.asyncio
async def test_monthly_future_not_started_is_carved_out_of_likely_not_added_on_top(db_session, test_org):
    """ИЗМЕНЕНО (15.10.2026, план abstract-noodling-pelican.md, п.C) — поле
    переименовано contracted_not_ordered → monthly_future_not_started,
    источник переехал на app.services.monthly_future_payments. Сценарий:
    рамочный договор + дочерний заказ 'contracted' БЕЗ planned_payment_month/
    service_start_date — месяц определяется по порядку номеров (единственный
    заказ договора → декабрь года субсидии, 2026, что на дату прогона теста
    ещё НЕ наступило — заказ остаётся «ещё уйдёт помесячно, не начато»).
    monthly_future_not_started обязан быть ВЫРЕЗКОЙ из not_committed_likely/
    not_committed_nice (по need_level заказа), а не добавкой поверх, и
    redistributable_by_kind НЕ трогается (товары/услуги по-прежнему включают
    эту сумму — не второй расчёт, см. докстринг not_committed_raw_by_subsidy).

    Бюджет субсидии = плану (250 000), задан явно (ОТМЕНЕНО решение владельца
    06.10.2026 «бюджет = план без ФЭО» — владелец 07.10.2026, план
    .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 1: budget_basis
    больше НЕ подставляется из плана без ФЭО, поэтому тест задаёт бюджет
    РЕАЛЬНО, тем же числом, чтобы сохранить проверяемый инвариант
    redistributable_unplanned == 0 РОВНО, budget_basis == planned)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id, budget=250_000)
    cat = await _make_category(db_session, subsidy.id, name="Рамочный договор")
    item = await _make_planned_item(db_session, cat.id, "Услуга связи", 1, 250_000)
    item.item_type = "услуга"
    await db_session.commit()

    # Рамочная голова (сам договор) + дочерний заказ в статусе 'contracted'
    # (контракт заключён, заказ как отдельная закупка ещё НЕ создан) — ровно
    # находка координатора. Позиция заказа привязана к плановой позиции item
    # (need_level по умолчанию 'likely').
    head = Purchase(
        subsidy_id=subsidy.id, item_name="Рамочный договор",
        status="contracted", purchase_contract_type="framework_with_amount",
    )
    db_session.add(head)
    await db_session.flush()
    child = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Заказ по рамочному",
        status="contracted", purchase_contract_type="framework_with_amount",
        parent_purchase_id=head.id,
        contract_price=Decimal("250000"), total_nmck=Decimal("250000"), nmck=Decimal("250000"),
    )
    db_session.add(child)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=child.id, item_name="Услуга связи", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("250000"), total_price=Decimal("250000"), item_type="услуга",
        feo_category_id=cat.id, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    raw_map = await not_committed_raw_by_subsidy(db_session, [subsidy.id])
    # ИЗМЕНЕНО: месяц заказа (декабрь 2026) ещё не наступил — его raw ушёл
    # ЦЕЛИКОМ в monthly_future_not_started_raw, likely_raw теперь 0.
    assert raw_map[subsidy.id]["likely_raw"] == pytest.approx(0.0)
    assert raw_map[subsidy.id]["monthly_future_not_started_raw"] == pytest.approx(250_000.0)

    summary = await subsidy_money_summary(db_session, [subsidy.id])
    row = summary[subsidy.id]

    assert row["redistributable_unplanned"] == pytest.approx(0.0)
    assert row["monthly_future_not_started"] == pytest.approx(250_000.0)
    # Вырезка, не добавка: likely карточки = likely_raw МИНУС заказ целиком.
    assert row["not_committed_likely"] == pytest.approx(0.0)
    assert row["not_committed_nice"] == pytest.approx(0.0)

    # Σ by_kind == итогу (by_kind НЕ уменьшается вырезкой — по заданию).
    by_kind = row["redistributable_by_kind"]
    total_by_kind = by_kind["goods"] + by_kind["services"] + by_kind["unspecified"]
    assert total_by_kind == pytest.approx(row["redistributable"])
    assert by_kind["services"] == pytest.approx(250_000.0)
    assert by_kind["goods"] == pytest.approx(0.0)

    # Инвариант карточки: 4 строки складываются в итог ровно.
    assert row["redistributable_unplanned"] + row["not_committed_nice"] \
        + row["not_committed_likely"] + row["monthly_future_not_started"] \
        == pytest.approx(row["redistributable"])
