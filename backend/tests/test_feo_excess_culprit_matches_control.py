"""Владелец, Волна 1 п.13 (2026-09-13), дословно: «Написано, что сумма
6 645 234,8 — Запланировано, при этом 4 000 000 было запланировано в ФЭО.
Далее пишется, что надо убрать 2 645 234,48, то есть это означает, что на эту
сумму план превышает ФЭО субсидии. Но при этом дальше идёт справка, из-за чего
произошло превышение: „Bosch 36 pro“...» Со скриншота: «превышение
2 645 234,48 ₽ — требуется согласование», ниже «... добавила 28 560,00 ₽,
после неё выбрано 4 012 784,48 ₽ при ФЭО 4 000 000,00 ₽» — цифра в справке
(перебор на 12 784,48) НИКАК не била с плашкой (2 645 234,48).

ПРИЧИНА (см. подробный docstring app.services.feo_plan_excess.find_excess_culprit):
эта функция считала Σ контрибьюторов СВОЕЙ собственной, более узкой выборкой
(план листьев + over_plan-позиции), игнорируя (1) замещение «заказ вместо
плана» (compute_feo_plan_tree._own_plan_and_forecast/_order_substituted_plan)
и (2) собственные плановые позиции узлов-НЕ-листьев — из-за чего Σ её
контрибьюторов почти всегда была МЕНЬШЕ настоящей плановой суммы узла
(compute_feo_plan_tree.full_display = plan + over), на которую реально смотрит
и плашка «требуется согласование» (excess_amount), и контроль
assert_no_unapproved_excess. Эта правка сводит обе точки к ОДНОМУ источнику
(ПРАВИЛО №6) — тест проверяет, что плашка и справка теперь называют ОДНО И ТО
ЖЕ число превышения.

Фикстуры (_make_subsidy/_make_category/_make_planned_item) переиспользованы из
test_feo_plan_tree_scenarios.py — там уже есть узлы про find_excess_culprit,
новых фикстур не изобретаем.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ: pytest tests/test_feo_excess_culprit_matches_control.py::<name>.
"""
from decimal import Decimal

import pytest

from app.services.feo_plan import assert_no_unapproved_excess, compute_feo_plan_tree, find_excess_culprit
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


@pytest.mark.asyncio
async def test_a_excess_on_category_with_several_items_matches_control(db_session, test_org):
    """(а) Превышение на категории с несколькими плановыми позициями — сумма
    превышения из контроля (compute_feo_plan_tree.excess_amount, та же плашка
    «требуется согласование») и total_excess из справки (find_excess_culprit)
    ОБЯЗАНЫ совпасть. Числа взяты из боевого скриншота владельца: ФЭО
    4 000 000, план 6 645 234,48, превышение 2 645 234,48 — но первая позиция,
    после которой сумма вышла за границу, добавляет всего 28 560 (а не
    2 645 234,48, как ложно подразумевал старый текст)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    # Второй корневой узел с запасом — суммарный потолок субсидии
    # (PLAN_OVER_SUBSIDY_CEILING) не должен перекрыть узловую проверку раньше,
    # чем мы до неё доберёмся (тот же приём, что в test_excess_total_not_per_branch.py).
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("10000000"))
    leaf = await _make_category(
        db_session, subsidy.id, name="Категория ФЭО «Bosch 36 pro»", budget=Decimal("4000000"),
    )
    await _make_planned_item(db_session, leaf.id, "Позиция 1 (заведена первой)", 1, 3_980_000)
    await _make_planned_item(db_session, leaf.id, "Набор бит-отвёрток Bosch 36 PRO", 1, 28_560)
    await _make_planned_item(db_session, leaf.id, "Позиция 3 (заведена последней)", 1, 2_636_674.48)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == pytest.approx(6_645_234.48)
    assert node["excess_amount"] == pytest.approx(2_645_234.48)

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    # ГЛАВНОЕ требование п.13: число из справки ОБЯЗАНО совпасть с плашкой.
    assert culprit["total_excess"] == pytest.approx(node["excess_amount"]), (
        "справка обязана называть ТУ ЖЕ сумму превышения, что и плашка "
        "«требуется согласование» — иначе воспроизводится жалоба владельца"
    )
    assert culprit["total_plan_amount"] == pytest.approx(node["plan"] + node["over"])

    # Первая позиция за чертой — «Bosch» (28 560), а не итоговая сумма
    # превышения целиком (честная формулировка, не «виновник всего»).
    assert culprit["item_name"] == "Набор бит-отвёрток Bosch 36 PRO"
    assert culprit["amount_before"] == pytest.approx(3_980_000.0)
    assert culprit["amount_at_crossing"] == pytest.approx(28_560.0)
    assert culprit["cumulative_after"] == pytest.approx(4_008_560.0)
    # На МОМЕНТ пересечения перебор над ФЭО — всего 8 560 (cumulative_after −
    # budget), НАМНОГО меньше total_excess (2 645 234,48) — именно это
    # расхождение и запутывало владельца в старом тексте (справка называла
    # маленький «перебор при пересечении», выдавая его за итог).
    crossing_over_budget = culprit["cumulative_after"] - node["budget"]
    assert crossing_over_budget == pytest.approx(8_560.0)
    assert crossing_over_budget < culprit["total_excess"]


@pytest.mark.asyncio
async def test_b_order_substituting_plan_still_matches(db_session, test_org):
    """(б) Узел, где реальный заказ ПОЛНОСТЬЮ замещает план (задача владельца
    2026-08-05, «заказ вместо плана») — план узла становится фактической
    суммой заказа (ordered), а НЕ Σ плановых позиций. find_excess_culprit ДО
    этой правки вообще не знал о замещении и продолжал бы объяснять
    превышение через устаревшую Σ FeoPlannedItem — здесь проверяем, что после
    правки total_excess по-прежнему совпадает с excess_amount, а виновник —
    реальная позиция закупки (не плановая строка)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("1000000"))
    leaf = await _make_category(
        db_session, subsidy.id, name="Позиция, заказанная целиком", budget=Decimal("300000"),
        planned_quantity=Decimal("2"),
    )
    await _make_planned_item(db_session, leaf.id, "Плановая позиция (устаревшая цена)", 2, 400_000)

    # Реальный заказ, количество набрано ПОЛНОСТЬЮ (2 шт), цена выше плановой —
    # НЕ привязан к плановой позиции (feo_planned_item_id=None), именно такие
    # позиции формируют `ordered` в ordered_consumption_by_category.
    p = Purchase(
        subsidy_id=subsidy.id,
        feo_category_id=leaf.id,
        item_name="Реальный заказ (дороже плана)",
        status="ordered",
        contract_price=Decimal("450000"),
        planned_total_price=Decimal("450000"),
        total_nmck=Decimal("450000"),
        nmck=Decimal("450000"),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Реальный заказ (дороже плана)",
        quantity=Decimal("2"),
        unit="шт",
        unit_price=Decimal("225000"),
        total_price=Decimal("450000"),
        feo_category_id=leaf.id,
        feo_planned_item_id=None,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan"] == pytest.approx(450_000.0), "план обязан замениться фактом заказа (заказано целиком)"
    assert node["excess_amount"] == pytest.approx(150_000.0)

    culprit = await find_excess_culprit(db_session, leaf.id, node["budget"])
    assert culprit is not None
    assert culprit["total_excess"] == pytest.approx(node["excess_amount"]), (
        "замещение «заказ вместо плана» обязано учитываться и в справке — "
        "иначе она снова разойдётся с плашкой"
    )
    assert culprit["purchase_id"] == p.id, "виновник — реальная позиция заказа, а не устаревшая плановая строка"


@pytest.mark.asyncio
async def test_c_warning_text_carries_both_numbers(db_session, test_org):
    """(в) Текст предупреждения (assert_no_unapproved_excess, тот же сценарий,
    что и (а)) обязан явно называть И итоговое превышение (совпадающее с
    плашкой), И вклад первой позиции за чертой — не выдавая второе за причину
    первого."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_category(db_session, subsidy.id, name="Ветка с запасом", budget=Decimal("10000000"))
    leaf = await _make_category(
        db_session, subsidy.id, name="Категория ФЭО «Bosch 36 pro»", budget=Decimal("4000000"),
    )
    await _make_planned_item(db_session, leaf.id, "Позиция 1 (заведена первой)", 1, 3_980_000)
    await _make_planned_item(db_session, leaf.id, "Набор бит-отвёрток Bosch 36 PRO", 1, 28_560)
    await _make_planned_item(db_session, leaf.id, "Позиция 3 (заведена последней)", 1, 2_636_674.48)

    warnings = await assert_no_unapproved_excess(db_session, leaf.id)
    assert warnings, "перекос ветки обязан вернуться предупреждением (не блокирует, см. правку 2026-09-03)"
    w = warnings[0]
    assert w["code"] == "PLAN_EXCESS_OVER_FEO"
    assert w["excess_amount"] == pytest.approx(2_645_234.48)

    text = w["message"]
    # Итоговое превышение — той же величиной, что и excess_amount плашки
    # (формат f"{x:,.2f}" — точка-разделитель разрядов запятой, как и везде
    # в этом модуле, см. остальные warnings/HTTPException ниже по файлу).
    assert "2,645,234.48" in text, text
    # Вклад первой позиции за чертой — присутствует, но НЕ подан как причина
    # всего превышения целиком.
    assert "28,560.00" in text, text
    assert "4,008,560.00" in text, text
    assert "первая позиция" in text.lower(), text
    assert "не единственная причина" in text.lower() or "не причина всего" in text.lower(), text
