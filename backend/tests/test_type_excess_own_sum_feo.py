"""Задача владельца (22.10.2026, прод, read-only замер — ложное превышение
«план по товарам (услугам) над ФЭО по товарам (услугам)» на уровне субсидии).

Статья ФЭО, введённая СВОЕЙ суммой (budget не совпал ни с Σ плановых позиций,
ни с планом с учётом договоров — item_type_split.pick_aligned_pool вернул
None), по правилу владельца 14.10.2026 НЕ делится по типу — всё её ФЭО
целиком уходит в "unspecified" (feo_plan_tree.py::_feo_by_kind). Типизированный
ПЛАН этой же статьи при этом остаётся в plan_goods узла+предков — контроль
«план по товарам над ФЭО по товарам» (compute_subsidy_type_summary) сравнивал
Σ plan_goods корней (С учётом этой статьи) с Σ feo_goods корней (БЕЗ неё) и
ложно срабатывал на суммах, которые уже и так ловит ОБЫЧНЫЙ контроль «план
над ФЭО» статьи (node['excess_amount'] — своя формула, своё согласование,
этим фиксом НЕ затронут).

Фикс — app.services.feo_type_excess_basis: excess_plan_over_feo_* (и узел, и
субсидия) теперь сравнивают feo_<kind> не с голым plan_<kind>, а с
plan_typed_<kind> = plan_<kind> минус Σ «своих сумм» (own-sum, не приравненных
к плану) по поддереву — см. её докстринг за полной формулой.

Проверяет:
  (A) статья с ФЭО, разбитым построчно (own_feo_by_kind) — plan_typed_goods ==
      plan_goods (своей суммы нет, exclusion пуст), контроль работает как и
      раньше.
  (B) статья «своя сумма» (budget=500, Σ позиций-товаров=600, не приравнено ни
      к одному пулу) рядом со статьёй (A) под одной субсидией — Σ plan_goods
      корней (ДО фикса) превышала Σ feo_goods на 600 (вся статья B); ПОСЛЕ
      фикса plan_over_feo_goods субсидии == 0 (её typed-план исключён
      целиком), а node['excess_amount'] статьи B (обычный контроль план/ФЭО)
      остаётся 100 (план 600 - ФЭО 500) — НЕ погашен фиксом.
  (C) та же статья (A) САМА ПО СЕБЕ: план товаров 100, ФЭО товаров (построчно)
      80 -> excess_plan_over_feo_goods == 20 остаётся (обычный типовой
      контроль статьи с НАСТОЯЩЕЙ typed-разбивкой ФЭО не тронут фиксом).
  (D) ДОРАБОТКА (координатор, 22.10.2026, вторая итерация замера прода) —
      own-sum статья, чей ПЛАН поднят ДОГОВОРОМ выше Σ плановых позиций
      (позиция-товар 100, закрыта договором на 150), ФЭО задано своей суммой
      120 (не совпадает ни с items_pool=100, ни с plan-with-contracts
      pool=150). Первая версия фикса исключала голый _plan_items_pool_by_kind
      (100, БЕЗ договора) — на проде (МИНПРОС_2026 id 51) недооценивала
      исключение там, где план узла поднят договором выше Σ позиций, оставляя
      ложный остаток. Теперь исключается ЕЁ ЖЕ plan_goods узла (после клэмпа
      budget'ом — см. feo_type_excess_basis.covered_plan_for_own_sum_node).

Фабрики (_make_subsidy/_make_category/_make_planned_item) — из
test_feo_plan_tree_type_split.py, _make_linked_purchase — из
test_money_committed.py, ПРАВИЛО №6, вторая копия не заводится.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять
КАЖДЫЙ тест ПО ОТДЕЛЬНОСТИ.
"""
from decimal import Decimal

import pytest

from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary
from tests.test_feo_plan_tree_type_split import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


@pytest.mark.asyncio
async def test_c_typed_feo_breakdown_excess_not_touched_by_fix(db_session, test_org):
    """(C) Статья БЕЗ явного budget (не own-sum вообще), ФЭО — построчная
    typed-разбивка (is_feo_breakdown=True): план товаров 100, ФЭО товаров 80
    -> excess_plan_over_feo_goods == 20 (exclusion пуст, plan_typed_goods ==
    plan_goods — фикс не меняет поведение обычных typed-категорий)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Статья — typed ФЭО построчно")
    await _make_planned_item(
        db_session, cat.id, "Товар (план)", 100, item_type="товар",
        is_feo_breakdown=True, feo_amount=80,
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["plan_goods"] == pytest.approx(100.0)
    assert node["plan_typed_goods"] == pytest.approx(100.0), "не own-sum -> exclusion==0 -> typed==plan"
    assert node["feo_goods"] == pytest.approx(80.0)
    assert node["excess_plan_over_feo_goods"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_ab_own_sum_article_excluded_from_subsidy_type_excess(db_session, test_org):
    """(A)+(B) Субсидия с двумя статьями:
      A — typed ФЭО построчно (план 100 товаров, ФЭО 80 товаров);
      B — «своя сумма» budget=500, Σ позиций-товаров=600, не приравнено ни к
          одному пулу (item_type_split.pick_aligned_pool -> None) -> ВСЁ её
          ФЭО уходит в unspecified, feo_goods(B)==0.

    ДО фикса: Σ plan_goods корней = 100+600=700, Σ feo_goods = 80+0=80 ->
    plan_over_feo_goods(субсидия) = 620 (ложное — статья B уже даёт свои 100
    через обычный excess_amount). ПОСЛЕ фикса: plan_typed_goods(B)==0 (вся
    своя сумма исключена), Σ plan_typed_goods = 100+0=100 == Σ feo_goods (80)
    + остаток... проверяем точный результат ниже."""
    subsidy = await _make_subsidy(db_session, test_org.id)

    cat_a = await _make_category(db_session, subsidy.id, name="Статья А — typed ФЭО")
    await _make_planned_item(
        db_session, cat_a.id, "Товар А (план)", 100, item_type="товар",
        is_feo_breakdown=True, feo_amount=80,
    )

    cat_b = await _make_category(db_session, subsidy.id, name="Статья Б — своя сумма", budget=Decimal("500"))
    await _make_planned_item(db_session, cat_b.id, "Товар Б (план)", 600, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_a = tree[cat_a.id]
    node_b = tree[cat_b.id]

    # Статья Б — своя сумма, НЕ приравненная ни к items_pool (600), ни к
    # plan-with-contracts pool (тоже 600, нет договоров) -> будет None и там,
    # и там (budget=500 не равен ни одному) -> весь budget в unspecified.
    assert node_b["feo_goods"] == pytest.approx(0.0)
    assert node_b["feo_unspecified"] == pytest.approx(500.0)
    assert node_b["plan_goods"] == pytest.approx(600.0)
    assert node_b["plan_typed_goods"] == pytest.approx(0.0), (
        "typed-план статьи Б целиком исключён — его ФЭО гарантированно в unspecified"
    )
    # Обычный контроль «план над ФЭО» статьи Б — НЕ погашен фиксом (своя
    # формула, своё согласование, excess_plan_over_feo_* его не замещает).
    assert node_b["excess_amount"] == pytest.approx(100.0), "план 600 - budget 500 = 100, обычный контроль цел"

    # Статья А не own-sum -> exclusion==0, typed==plan, контроль статьи цел.
    assert node_a["plan_typed_goods"] == pytest.approx(100.0)
    assert node_a["excess_plan_over_feo_goods"] == pytest.approx(20.0)
    # На статье Б feo_goods==0 -> контроль по типу НЕ срабатывает вовсе
    # (владелец: «на категории без типизированного ФЭО контроль не
    # срабатывает») — независимо от plan_typed_goods.
    assert node_b["excess_plan_over_feo_goods"] == pytest.approx(0.0)

    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
    assert summary["totals"]["plan_goods"] == pytest.approx(700.0), "голый план корней НЕ меняется фиксом"
    assert summary["totals"]["plan_typed_goods"] == pytest.approx(100.0), (
        "typed-базис: 100 (статья А) + 0 (статья Б, исключена целиком)"
    )
    assert summary["totals"]["feo_goods"] == pytest.approx(80.0)
    assert summary["excess"]["plan_over_feo_goods"]["amount"] == pytest.approx(20.0), (
        "раньше было бы max(700-80,0)=620 (ложное, статью Б двойной раз наказывало); "
        "теперь только реальный остаток статьи А (100-80=20)"
    )


@pytest.mark.asyncio
async def test_b_alone_zeroes_subsidy_plan_over_feo_goods(db_session, test_org):
    """(B) отдельно, без соседней typed-статьи: ЕДИНСТВЕННАЯ статья субсидии —
    «своя сумма», feo_goods субсидии == 0 -> контроль по типу вообще не
    срабатывает (bottom<=0, см. compute_subsidy_type_summary requires_positive_
    bottom=True) -> plan_over_feo_goods(субсидия) == 0 И до, и после фикса —
    инвариант «plan_goods/feo_goods итогов не меняются» на границе fix'а."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_b = await _make_category(db_session, subsidy.id, name="Статья Б — своя сумма (одна)", budget=Decimal("500"))
    await _make_planned_item(db_session, cat_b.id, "Товар Б (план)", 600, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
    assert summary["totals"]["plan_goods"] == pytest.approx(600.0)
    assert summary["totals"]["feo_goods"] == pytest.approx(0.0)
    assert summary["excess"]["plan_over_feo_goods"]["amount"] == pytest.approx(0.0)
    assert tree[cat_b.id]["excess_amount"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_d_own_sum_plan_raised_by_contract_excluded_from_subsidy_excess(db_session, test_org):
    """(D) Доработка координатора (22.10.2026, вторая итерация замера прода,
    см. docstring модуля) — own-sum статья Б, чей ПЛАН поднят ДОГОВОРОМ выше
    Σ плановых позиций (товар 100, закрыт договором на 150, qty полностью
    набрано -> plan/full_display==150), ФЭО задано своей суммой 120 (не
    совпадает ни с items_pool=100, ни с plan-with-contracts pool=150).

    Рядом — статья В, ВЫРОВНЕННАЯ (budget==Σ позиций=200, split по типу
    нормально) -> её typed-план == её ФЭО, не вносит перекоса в субсидию.

    excess_amount статьи Б (обычный контроль план/ФЭО, full_display-budget)
    == 30 (150-120) — НЕ погашен фиксом. plan_over_feo_goods субсидии == 0
    (своя сумма Б исключена ЦЕЛИКОМ от её же plan_goods, статья В сходится
    сама) — первая версия фикса (исключение по items_pool=100, без договора)
    оставляла бы здесь ложный остаток."""
    subsidy = await _make_subsidy(db_session, test_org.id)

    cat_b = await _make_category(
        db_session, subsidy.id, name="Статья Б — своя сумма, план поднят договором", budget=Decimal("120"),
    )
    fpi_b = await _make_planned_item(db_session, cat_b.id, "Товар Б (план)", 100, item_type="товар", quantity=1)
    await _make_linked_purchase(db_session, subsidy.id, cat_b.id, fpi_b.id, quantity=1, contract_price=150)

    cat_c = await _make_category(db_session, subsidy.id, name="Статья В — выровнена", budget=Decimal("200"))
    await _make_planned_item(db_session, cat_c.id, "Товар В (план)", 200, item_type="товар")

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_b = tree[cat_b.id]
    node_c = tree[cat_c.id]

    assert node_b["plan"] == pytest.approx(150.0), "план замещён договором (закрыт по количеству целиком)"
    assert node_b["excess_amount"] == pytest.approx(30.0), "150 - 120 = 30, обычный контроль план/ФЭО цел"
    assert node_b["feo_goods"] == pytest.approx(0.0), "своя сумма, не приравнена -> всё в без типа"
    assert node_b["plan_typed_goods"] == pytest.approx(0.0), "typed-план статьи Б целиком исключён"

    assert node_c["feo_goods"] == pytest.approx(200.0)
    assert node_c["plan_typed_goods"] == pytest.approx(200.0)

    summary = await compute_subsidy_type_summary(db_session, subsidy.id, tree)
    assert summary["excess"]["plan_over_feo_goods"]["amount"] == pytest.approx(0.0), (
        "первая версия фикса (исключение по items_pool, без договора) оставляла ложный остаток здесь"
    )
