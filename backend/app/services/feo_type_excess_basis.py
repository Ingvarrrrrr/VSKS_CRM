"""feo_type_excess_basis.py — typed-базис контролей «план по типу над ФЭО по
типу» (ПРАВИЛО №5/№6; задача владельца 22.10.2026, read-only замер прода).

Чистая арифметика без доступа к БД — feo_plan_tree.py вызывает функции отсюда
из _visit, передавая уже готовые числа узла (своего и прямых детей).

Повод: статья ФЭО, введённая СВОЕЙ суммой (budget не совпал ни с Σ плановых
позиций, ни с планом с учётом договоров — item_type_split.pick_aligned_pool
вернул None), по правилу владельца 14.10.2026 по типу НЕ делится — всё её
ФЭО целиком уходит в "unspecified". Типизированный ПЛАН этой же статьи при
этом остаётся в plan_goods/plan_services узла+предков — контроль «план по
товарам над ФЭО по товарам» сравнивал план (с учётом этой статьи) с ФЭО (без
неё) и ложно срабатывал на суммах, которые уже и так ловит ОБЫЧНЫЙ контроль
«план над ФЭО» статьи (excess_amount — НЕ трогается этим модулем).

ИСПРАВЛЕНИЕ (координатор, 22.10.2026, вторая итерация замера прода) — первая
версия исключала голый _plan_items_pool_by_kind (Σ amount плановых позиций,
БЕЗ договоров/пола/клэмпа budget), а не то число, что реально сидит в
plan_<kind> узла (_display_kind). На статьях, где план узла поднят ДОГОВОРОМ
выше Σ позиций (МИНПРОС_2026 id 51: позиций 0, план с договором 1 935 000) или
где budgeted-подкатегория сама клэмпнута своим бюджетом, пул недооценивал
исключение — часть ложного превышения оставалась (боевой замер показал
1 935 000 / 10 769 / 40 730 вместо 0). Исправлено: «покрытый план» own-sum
узла теперь берётся из ЕГО ЖЕ plan_<kind> (то самое число, которое идёт в
node['plan_goods'/'plan_services'] — _display_kind в feo_plan_tree.py, уже С
договорами/полом/клэмпом budget), а не из пула позиций.

Формула (повторяет структуру _feo_by_kind own-sum ветки, но для ПЛАНА, не
ФЭО): для own-sum узла N «покрытый план» = plan_<kind>(N) минус Σ
plan_<kind>(C) по ПРЯМЫМ детям C узла N со СВОИМ явным budget (их typed-план
уже либо корректно сопоставлен со своей ФЭО-разбивкой — если они выровнены,
либо сами войдут в сумму СВОЕЙ записью — если тоже own-sum, см. ниже про
рекурсию по поддереву). plan_<kind>(C) читается из уже посчитанного узла C
(result[C]['plan_goods'/'plan_services'] в feo_plan_tree.py) — он успевает
посчитаться раньше родителя (_visit обходит дерево снизу вверх, child_nodes =
[_visit(c) for c in kids] ДО вычисления узла-родителя).

exclusion(N) = covered(N) [0, если N не own-sum] + Σ exclusion(C) по ВСЕМ
прямым детям C (бюджетным и нет) — тот же rollup «узел + Σ по поддереву», что
и везде в feo_plan_tree.py (накапливается в _visit инкрементально, в своём
memo, т.к. каждый узел посещается ровно один раз, снизу вверх)."""
from __future__ import annotations

from typing import Dict, Iterable, List


def covered_plan_for_own_sum_node(
    plan_kind: Dict[str, float], budgeted_children_plan_kind: Dict[str, float], kinds: Iterable[str],
) -> Dict[str, float]:
    """covered(N) по каждому виду из `kinds` (обычно (KIND_GOODS, KIND_SERVICES)) —
    plan_<kind>(N) (его же node['plan_<kind>'], см. docstring модуля) минус Σ
    plan_<kind> ПРЯМЫХ детей N со своим явным budget. Клэмп >=0 — защита от
    округления/противоречивых данных, не инвариант."""
    return {
        k: max(float(plan_kind.get(k, 0.0) or 0.0) - float(budgeted_children_plan_kind.get(k, 0.0) or 0.0), 0.0)
        for k in kinds
    }


def rollup_exclusion_for_node(covered: Dict[str, float], children_exclusion: List[Dict[str, float]]) -> Dict[str, float]:
    """exclusion(N) = covered (уже {0,...}, если N не own-sum — см. docstring
    модуля) + Σ exclusion прямых детей (каждый — уже готовый результат ЭТОЙ
    же функции для ребёнка, вызывающий код передаёт их списком — простое
    суммирование по ключам, без обращения к дереву."""
    val: Dict[str, float] = dict(covered)
    for kv in children_exclusion:
        for k, v in kv.items():
            val[k] = val.get(k, 0.0) + v
    return val


def typed_plan_amount(plan_kind: Dict[str, float], exclusion_kind: Dict[str, float], kind: str) -> float:
    """plan_typed_<kind> узла = plan_<kind> (готовое число узла+поддерева,
    node['plan_<kind>']) минус exclusion того же вида (rollup_exclusion_for_node)
    — то самое число, которое РЕАЛЬНО сравнивается с feo_<kind> в
    excess_plan_over_feo_<kind> (feo_plan_tree.py) и в
    compute_subsidy_type_summary (сумма этого поля по корневым узлам). Клэмп
    >=0 — защита от округления, не инвариант."""
    return max(float(plan_kind.get(kind, 0.0) or 0.0) - float(exclusion_kind.get(kind, 0.0) or 0.0), 0.0)
