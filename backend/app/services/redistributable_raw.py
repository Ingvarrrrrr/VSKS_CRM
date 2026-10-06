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

monthly_future_by_kind ниже — та же Σ, что dashboard_monthly_accrual.
compute_monthly_future_map (ПРАВИЛО №6, не вторая формула графика платежей:
читает compute_monthly_future_rows — построчный разбор, вынесенный ИЗ
compute_monthly_future_map специально под эту задачу), только раскладывает
сумму КАЖДОЙ закупки по товар/услуга через item_type_split.purchase_type_shares
(та же техника, что dashboard_type_split.py применяет к остальным этапам).

over_plan_categories_by_subsidy — красная строка карточки «по направлению
законтрактовано сверх плана»: читает committed/plan КОРНЕВЫХ узлов дерева
(compute_feo_plan_tree) — та же Σ committed/plan, что уже участвует в
planned_not_committed узла, вторая формула не вводится.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.committed_amounts import committed_by_planned_item, planned_item_contributions
from app.services.item_type_split import KIND_GOODS, KIND_SERVICES, KIND_UNSPECIFIED, kind_of
from app.services.plan_need_level import NEED_LEVEL_NICE_TO_HAVE, normalize_need_level


def _empty_kind_bucket() -> dict:
    return {KIND_GOODS: 0.0, KIND_SERVICES: 0.0, KIND_UNSPECIFIED: 0.0}


async def not_committed_raw_by_subsidy(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"nice_raw": float, "likely_raw": float, "by_kind": {goods,
    services, unspecified}}} — Σ по ВСЕМ активным FeoPlannedItem субсидии
    (любой категории дерева, без рекурсивного роллапа и БЕЗ клэмпа на
    отдельной позиции) — см. докстринг модуля за формулой `raw`."""
    result: dict[int, dict] = {
        sid: {"nice_raw": 0.0, "likely_raw": 0.0, "by_kind": _empty_kind_bucket()}
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    cat_rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.subsidy_id).where(FeoCategory.subsidy_id.in_(subsidy_ids))
    )).all()
    if not cat_rows:
        return result
    sid_by_cat = {r.id: r.subsidy_id for r in cat_rows}
    cat_ids = list(sid_by_cat.keys())

    items_q = (
        select(FeoPlannedItem.id, FeoPlannedItem.feo_category_id, FeoPlannedItem.need_level)
        .where(FeoPlannedItem.feo_category_id.in_(cat_ids))
        .where(FeoPlannedItem.is_active.is_(True))
    )
    rows = (await db.execute(items_q)).all()
    if not rows:
        return result

    contrib = await planned_item_contributions(db, cat_ids)
    committed_map = await committed_by_planned_item(db, [r.id for r in rows])

    for r in rows:
        info = contrib.get(r.id)
        if info is None:
            continue
        sid = sid_by_cat.get(r.feo_category_id)
        if sid not in result:
            continue
        committed_amt = (committed_map.get(r.id) or {}).get("amount", 0.0)
        raw = info["amount"] - committed_amt
        level = normalize_need_level(r.need_level)
        d = result[sid]
        if level == NEED_LEVEL_NICE_TO_HAVE:
            d["nice_raw"] += raw
        else:
            d["likely_raw"] += raw
        d["by_kind"][kind_of(info["item_type_effective"])] += raw
    return result


async def monthly_future_by_kind(db: AsyncSession, subsidy_ids: list[int]) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "by_kind": {...}}} — ИСПРАВЛЕНО (находка
    координатора 06.10.2026, двойной счёт): subsidy_money_summary.py читает
    ТОЛЬКО `amount` отсюда (сумма «ежемесячные до конца года» для отдельной
    строки карточки). `by_kind` здесь НЕ используется вызывающим кодом — сама
    ежемесячная сумма уже часть той же плановой позиции, что и так попадает в
    not_committed_raw_by_subsidy['by_kind'] (monthly-позиция = обычная
    FeoPlannedItem с need_level по умолчанию 'likely'), прибавлять её ПОВЕРХ
    было бы задвоением goods/services. `by_kind` оставлен в возврате на
    случай отдельного построчного drill (не требуется текущим планом), но
    use-case "товары/услуги карточки" его не трогает — см. докстринг
    модуля.

    См. докстринг
    модуля. subsidy_ids уже отфильтрованы по видимости вызывающим кодом
    (простой IN-фильтр здесь — та же техника, что остальные Σ-функции этого
    модуля, видимость не изобретается заново)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.services.dashboard_monthly_accrual import compute_monthly_future_rows
    from app.services.item_type_split import purchase_type_shares, split_amount_by_shares

    result: dict[int, dict] = {
        sid: {"amount": 0.0, "by_kind": _empty_kind_bucket()} for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    def _filter(q):
        return q.where(Purchase.subsidy_id.in_(subsidy_ids))

    rows = await compute_monthly_future_rows(db, _filter)
    if not rows:
        return result

    purchase_ids = [r["purchase_id"] for r in rows]
    items_by_purchase: dict[int, list] = {}
    item_rows = (await db.execute(
        select(PurchaseItem.purchase_id, PurchaseItem.item_type, PurchaseItem.total_price)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).all()
    for it in item_rows:
        items_by_purchase.setdefault(it.purchase_id, []).append(it)

    for r in rows:
        sid = r["subsidy_id"]
        if sid not in result:
            continue
        amount = r["amount"]
        shares = purchase_type_shares(items_by_purchase.get(r["purchase_id"], []))
        g, s, u = split_amount_by_shares(amount, shares)
        d = result[sid]
        d["amount"] += amount
        d["by_kind"][KIND_GOODS] += float(g)
        d["by_kind"][KIND_SERVICES] += float(s)
        d["by_kind"][KIND_UNSPECIFIED] += float(u)
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
