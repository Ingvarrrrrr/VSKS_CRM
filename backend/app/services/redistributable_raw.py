"""redistributable_raw.py — подстроки карточки «Можно перераспределить» БЕЗ
обрезки по направлениям ФЭО (владелец, 06.10.2026, план sleepy-fluttering-
walrus.md, п.1).

Повод: compute_feo_plan_tree клэмпит not_committed_nice в [0, planned_not_committed]
НА КАЖДОМ УЗЛЕ (app.services.feo_plan_tree ~1412-1420,1545-1546) — правильная
защита для самого ДЕРЕВА (узел не должен показывать отрицательный остаток), но
при роллапе по субсидии дефицит одного направления (законтрактовано больше
плана) обнуляет СВОЙ "nice_to_have" и утаскивает избыток в "likely" ДРУГИХ
направлений — карточка расходится с простой Σ по листу Excel. Карточка здесь
читает те же исходные числа ПОЗИЦИЙ, но без клэмпа и без привязки к дереву
узлов — ровно так же пользователь сверяет лист сам (Σ по need_level всех
плановых позиций субсидии).

ПРАВИЛО №6 — НЕ вторая формула «вклада в план»/«законтрактовано»: contribution
берётся из committed_amounts.planned_item_contributions, законтрактованная
сумма отдельной позиции — из committed_amounts.committed_by_planned_item (ТЕ
ЖЕ две точки, что уже использует committed_amounts.leaf_items_not_committed_
by_need_level для СВОЕЙ разбивки по need_level, см. её докстринг — raw =
contribution - committed, БЕЗ клэмпа на 0 для отдельной позиции). Здесь тот же
raw агрегируется сразу на уровень субсидии (а не по дереву категорий) и
одновременно раскладывается по kind_of(item_type_effective) — та же функция
kind_of, что и dashboard_type_split.py/item_type_split.py.

ИСПРАВЛЕНО (находка координатора 06.10.2026): «ежемесячные/договоры без
заказа» для этой карточки больше НЕ считаются через is_monthly_payment-график
(monthly_future_by_kind/compute_monthly_future_map) — на проде id=89 разрыв
«Ведётся работа» − «Заказано» целиком состоял из дочерних заказов рамочных
договоров в статусе 'contracted' (is_monthly_payment=False у всех), график
платежей тут ни при чём. Источник — app.services.stage_cumulative.
contracted_not_ordered_by_subsidy/contracted_not_ordered_need_level_split
(ПРАВИЛО №6 — тот же effective_amount_expr(), что и остальные суммы этого
модуля); вызывается из subsidy_money_summary.py, не отсюда.

over_plan_categories_by_subsidy — красная строка карточки «по направлению
законтрактовано сверх плана»: читает committed/plan КОРНЕВЫХ узлов дерева
(compute_feo_plan_tree) — та же Σ committed/plan, что уже участвует в
planned_not_committed узла, вторая формула не вводится.

not_committed_raw_rows — ПОСТРОЧНАЯ версия (владелец, 06.10.2026, доп. задача
«расшифровка карточки по клику "Товары"/"Услуги"»): ОДНО место, где считается
`raw` одной плановой позиции (contribution − committed_by_planned_item). Обе
агрегатные функции модуля (not_committed_raw_by_subsidy) переиспользуют ЭТИ
строки, не считают raw заново (ПРАВИЛО №6) — not_committed_raw_by_subsidy
теперь просто суммирует not_committed_raw_rows по need_level/kind, поэтому
Σ строк диалога ВСЕГДА равна карточке «Можно перераспределить» (товары/
услуги) побайтово. Строки с |raw| < 0.005 не возвращаются («остаток 0» —
шум списка, не ошибка расчёта). Для позиций, по которым существует дочерний
заказ рамочного договора в статусе 'contracted' (тот же предикат, что
app.services.stage_cumulative.contracted_not_ordered_by_subsidy — договор
заключён, заказ как отдельная закупка ещё не оформлен), ставится флаг
`contracted_not_ordered=True` — фронт показывает отдельную подпись «нужности»
вместо хотелось бы/скорее всего, вторая сумма не считается.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.committed_amounts import committed_by_planned_item, planned_item_contributions
from app.services.item_type_split import empty_kind_dict, kind_of_by_category_id
from app.services.plan_need_level import NEED_LEVEL_NICE_TO_HAVE, normalize_need_level

_ZERO_EPS = 0.005


def _empty_kind_bucket() -> dict:
    return empty_kind_dict()


def _category_path(cat_id: Optional[int], cats: dict[int, dict]) -> str:
    """'Направление › Тип расходов › Позиция' — путь от корня до cat_id
    включительно, по parent_id (защита от циклов — не более глубины словаря)."""
    if cat_id is None or cat_id not in cats:
        return ""
    names: list[str] = []
    seen: set = set()
    cur = cat_id
    while cur is not None and cur in cats and cur not in seen:
        seen.add(cur)
        names.append(cats[cur]["name"] or "")
        cur = cats[cur]["parent_id"]
    return " › ".join(reversed(names))


async def not_committed_raw_rows(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, list[dict]]:
    """{subsidy_id: [{"planned_item_id","name","feo_category_id","category_path",
    "kind","need_level","contribution","committed","raw","contracted_not_ordered"}]}
    — см. докстринг модуля за формулой `raw` и условием фильтрации нулевых
    строк. `need_level` — 'nice_to_have'/'likely' (app.services.plan_need_level),
    нормализовано normalize_need_level."""
    result: dict[int, list[dict]] = {sid: [] for sid in subsidy_ids}
    if not subsidy_ids:
        return result

    cat_rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.subsidy_id, FeoCategory.parent_id, FeoCategory.name)
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )).all()
    if not cat_rows:
        return result
    sid_by_cat = {r.id: r.subsidy_id for r in cat_rows}
    cats = {r.id: {"parent_id": r.parent_id, "name": r.name} for r in cat_rows}
    cat_ids = list(sid_by_cat.keys())

    items_q = (
        select(
            FeoPlannedItem.id, FeoPlannedItem.feo_category_id,
            FeoPlannedItem.need_level, FeoPlannedItem.name,
        )
        .where(FeoPlannedItem.feo_category_id.in_(cat_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )
    rows = (await db.execute(items_q)).all()
    if not rows:
        return result

    item_ids = [r.id for r in rows]
    contrib = await planned_item_contributions(db, cat_ids)
    committed_map = await committed_by_planned_item(db, item_ids)
    # payroll-категории (своя или по предку, план .planning/quick/2026-10-07-
    # dnr-feo-cards/PLAN.md шаг 2) — ОДИН резолвер, ПРАВИЛО №6.
    from app.services.feo_payroll import payroll_category_ids
    _payroll_ids = await payroll_category_ids(db, subsidy_ids)

    # «Договор заключён, заказ ещё не создан» — ТОТ ЖЕ предикат, что
    # stage_cumulative.contracted_not_ordered_by_subsidy (status='contracted',
    # дочерний заказ рамочного договора, не остановлена), здесь — просто
    # множество planned_item_id, чьи заказы под него попадают (не вторая
    # сумма, флаг для отображения).
    flagged_ids: set = set()
    if item_ids:
        flag_rows = (await db.execute(
            select(PurchaseItem.feo_planned_item_id)
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(Purchase.status == "contracted")
            .where(Purchase.parent_purchase_id.isnot(None))
            .where(Purchase.stopped_at.is_(None))
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
            .distinct()
        )).all()
        flagged_ids = {r.feo_planned_item_id for r in flag_rows}

    for r in rows:
        info = contrib.get(r.id)
        if info is None:
            continue
        sid = sid_by_cat.get(r.feo_category_id)
        if sid not in result:
            continue
        committed_amt = (committed_map.get(r.id) or {}).get("amount", 0.0)
        raw = info["amount"] - committed_amt
        if abs(raw) < _ZERO_EPS:
            continue
        result[sid].append({
            "planned_item_id": r.id,
            "name": r.name,
            "feo_category_id": r.feo_category_id,
            "category_path": _category_path(r.feo_category_id, cats),
            "kind": kind_of_by_category_id(info["item_type_effective"], r.feo_category_id, _payroll_ids),
            "need_level": normalize_need_level(r.need_level),
            "contribution": info["amount"],
            "committed": committed_amt,
            "raw": raw,
            "contracted_not_ordered": r.id in flagged_ids,
        })
    return result


async def not_committed_raw_by_subsidy(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"nice_raw": float, "likely_raw": float, "by_kind": {goods,
    services, unspecified}}} — Σ not_committed_raw_rows по need_level/kind
    (ПРАВИЛО №6 — raw одной позиции считается ТОЛЬКО там, эта функция —
    чистая агрегация, не вторая формула)."""
    result: dict[int, dict] = {
        sid: {"nice_raw": 0.0, "likely_raw": 0.0, "by_kind": _empty_kind_bucket()}
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    rows_by_sid = await not_committed_raw_rows(db, subsidy_ids)
    for sid, rows in rows_by_sid.items():
        d = result.get(sid)
        if d is None:
            continue
        for row in rows:
            if row["need_level"] == NEED_LEVEL_NICE_TO_HAVE:
                d["nice_raw"] += row["raw"]
            else:
                d["likely_raw"] += row["raw"]
            d["by_kind"][row["kind"]] += row["raw"]
    return result


async def over_plan_categories_by_subsidy(
    db: AsyncSession, subsidy_ids: list[int], tree: Optional[dict] = None,
) -> dict[int, list]:
    """{subsidy_id: [{"category_id","name","excess_amount"}]} — КОРНЕВЫЕ узлы
    дерева ФЭО («направления») с committed (узел+поддерево) БОЛЬШЕ plan
    (узел+поддерево) — красная строка карточки. committed/plan узла читаются
    из compute_feo_plan_tree (ПРАВИЛО №6, та же Σ, что формирует
    node['planned_not_committed'] = plan - committed). `tree` можно передать
    готовым, если вызывающий код уже построил его для этих же subsidy_ids
    (dashboard_charts.py и subsidy_money_summary.py уже строят его для своих
    нужд — не гнать его второй раз)."""
    result: dict[int, list] = {sid: [] for sid in subsidy_ids}
    if not subsidy_ids:
        return result
    if tree is None:
        from app.services.feo_plan_tree import compute_feo_plan_tree
        tree = await compute_feo_plan_tree(db, subsidy_ids)

    over_cat_ids: list[int] = []
    excess_by_cat: dict[int, float] = {}
    sid_by_cat_excess: dict[int, int] = {}
    for cat_id, node in tree.items():
        if node.get("parent_id") is not None:
            continue
        sid = node.get("subsidy_id")
        if sid not in result:
            continue
        excess = float(node.get("committed", 0.0) or 0.0) - float(node.get("plan", 0.0) or 0.0)
        if excess > 0.005:
            over_cat_ids.append(cat_id)
            excess_by_cat[cat_id] = excess
            sid_by_cat_excess[cat_id] = sid

    if not over_cat_ids:
        return result

    name_rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(over_cat_ids))
    )).all()
    names = {r.id: r.name for r in name_rows}
    for cat_id in over_cat_ids:
        sid = sid_by_cat_excess[cat_id]
        result[sid].append({
            "category_id": cat_id,
            "name": names.get(cat_id),
            "excess_amount": excess_by_cat[cat_id],
        })
    return result
