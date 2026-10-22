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
шум списка, не ошибка расчёта).

ИЗМЕНЕНО (🟡/🟢/🔵 правки плана abstract-noodling-pelican.md, 15.10.2026, п.C):
committed_by_planned_item вызывается с month_aware=True — заказ рамочного
договора, чей месяц УЖЕ НАЧАЛСЯ, теперь committed (см. докстринг
committed_status_predicate), поэтому его доля автоматически уходит из `raw`
сюда НЕ попадая. Для позиций, по которым существует ещё НЕ начавшийся
(будущий месяц) заказ рамочного договора — app.services.monthly_future_payments.
framework_order_month_rows, источник 'framework_order', month > текущего —
ставится флаг `monthly_future_not_started=True` (было `contracted_not_ordered`,
переименовано по плану): not_committed_raw_by_subsidy ПОЛНОСТЬЮ исключает
такие строки из nice_raw/likely_raw/by_kind (их raw уходит в отдельную сумму
monthly_future_not_started_raw — строка 4 карточки «Можно перераспределить»,
«ещё уйдёт помесячно», см. docstring not_committed_raw_by_subsidy) — ТАК
ИНВАРИАНТ redistributable == not_planned + nice + likely + monthly_future_not_started
держится АЛГЕБРАИЧЕСКИ (Σ raw не меняется, просто одни строки идут в
отдельную сумму вместо nice/likely), а не сверкой двух независимых источников
(raw плановой позиции vs. effective_amount_expr заказа — эти две суммы в
общем случае НЕ обязаны совпадать копейка-в-копейку при расхождении плановой
цены и цены заказа, см. test_monthly_future_payments.py).
"""
from typing import Optional

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.committed_amounts import (
    committed_by_planned_item,
    committed_status_predicate,
    planned_item_contributions,
)
from app.services.feo_plan_fact import fact_amounts_for_rows
from app.services.item_type_split import ALL_KINDS, empty_kind_dict, kind_of_by_category_id
from app.services.plan_need_level import NEED_LEVEL_NICE_TO_HAVE, is_reserve_need_level, normalize_need_level
from app.services.purchase_amounts import aggregate_scope_expr

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


async def not_committed_raw_rows(
    db: AsyncSession, subsidy_ids: list[int], *, today=None,
) -> dict[int, list[dict]]:
    """{subsidy_id: [{"planned_item_id","name","feo_category_id","category_path",
    "kind","need_level","contribution","committed","raw","monthly_future_not_started"}]}
    — см. докстринг модуля за формулой `raw` и условием фильтрации нулевых
    строк. `need_level` — 'nice_to_have'/'likely' (app.services.plan_need_level),
    нормализовано normalize_need_level. `today` — параметр для тестов
    (по умолчанию date.today())."""
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
    # month_aware=True (🟢/🔵 правки, п.B/C) — заказ рамочного договора, чей
    # месяц уже начался, тоже committed — см. докстринг committed_by_planned_item.
    committed_map = await committed_by_planned_item(db, item_ids, month_aware=True)
    # payroll-категории (своя или по предку, план .planning/quick/2026-10-07-
    # dnr-feo-cards/PLAN.md шаг 2) — ОДИН резолвер, ПРАВИЛО №6.
    from app.services.feo_payroll import payroll_category_ids
    _payroll_ids = await payroll_category_ids(db, subsidy_ids)

    # «Ещё уйдёт помесячно, не начато» — ОДИН источник правила, см. докстринг
    # модуля: app.services.monthly_future_payments.framework_order_month_rows,
    # ТОЛЬКО source='framework_order' и ТОЛЬКО месяцы ПОСЛЕ текущего (started-
    # месяцы уже committed выше, в committed_by_planned_item). Здесь — просто
    # множество planned_item_id, чьи заказы под него попадают (флаг для
    # отображения и для исключения из nice/likely Σ ниже, не вторая сумма).
    from datetime import date as _date
    from app.services.monthly_future_payments import framework_order_month_rows as _fw_rows_fn

    flagged_ids: set = set()
    if item_ids:
        _today = today or _date.today()
        _cur_month = _date(_today.year, _today.month, 1)
        fw_rows = await _fw_rows_fn(db, subsidy_ids)
        future_purchase_ids = {
            r["purchase_id"] for r in fw_rows if r["month"] is not None and r["month"] > _cur_month
        }
        if future_purchase_ids:
            flag_rows = (await db.execute(
                select(PurchaseItem.feo_planned_item_id)
                .where(PurchaseItem.purchase_id.in_(future_purchase_ids))
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
            "monthly_future_not_started": r.id in flagged_ids,
            "purchase_id": None,
        })

    # ИСПРАВЛЕНО (D2, живая приёмка 21.10.2026, ХРО_2026 id 55): закупка может
    # быть законтрактована НАПРЯМУЮ НА СТАТЬЮ (Purchase.feo_category_id/
    # PurchaseItem.feo_category_id), БЕЗ ЛЮБОЙ привязки к плановой позиции
    # (PurchaseItem.feo_planned_item_id IS NULL — 3 закупки ФОТ ХРО_2026 на
    # 9 008 664,07, «ЗП»/«Отчисления»/«Командировочные», заведены ровно так).
    # subsidy_committed_totals/compute_feo_plan_tree УЖЕ учитывают эти деньги в
    # «законтрактовано» узла/субсидии целиком (committed_consumption_by_category
    # считает ВСЕ позиции узла, линкованные и нет), поэтому redistributable =
    # budget_basis − committed уже меньше на эту сумму — а raw выше (Σ по
    # плановым позициям, через committed_by_planned_item) её не видит вовсе:
    # ни одна плановая позиция не несёт её как свой committed. Поэтому Σ по
    # строкам (by_kind/nice/likely) была БОЛЬШЕ итога карточки ровно на неё.
    #
    # НАРОЧНО УЖЕ feo_planned_item_id IS NULL, а НЕ более широкое условие
    # «привязка невалидна/к чужой категории» (как у committed_consumption_by_
    # category(exclude_planned_item_linked=True), используется ПОРОГОМ
    # замещения плана, другая задача) — позиция, привязанная к СУЩЕСТВУЮЩЕЙ
    # активной плановой позиции (даже физически в другой категории, см.
    # test_not_committed_raw_isolates_miscategorized_overspend), УЖЕ полностью
    # учтена committed_by_planned_item на уровне ЭТОЙ позиции — добавлять её
    # здесь ещё раз было бы ЗАДВОЕНИЕМ (committed вычтен и из её raw, и из
    # синтетической строки чужой категории), а не недосчётом.
    #
    # Строка — ОТРИЦАТЕЛЬНАЯ, на категорию+вид (kind_of_by_category_id — ТОТ ЖЕ
    # классификатор, что и у позиций выше, payroll по категории ловится так же),
    # need_level='likely' (нет конкретной плановой позиции, чей need_level
    # читать — та же трактовка, что committed_consumption_by_category даёт
    # невалидной/отсутствующей привязке, см. её докстринг _valid_link). Строка
    # видна и в расшифровке (dashboard_redistributable_drill.py читает ТЕ ЖЕ
    # not_committed_raw_rows), и в агрегате (not_committed_raw_by_subsidy ниже
    # просто суммирует строки) — Σ снова РОВНО совпадает с redistributable.
    _unlinked_cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    _unlinked_stmt = (
        select(PurchaseItem, Purchase, _unlinked_cat_col.label("cat_id"))
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .join(FeoCategory, FeoCategory.id == _unlinked_cat_col)
        .outerjoin(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .where(PurchaseItem.feo_planned_item_id.is_(None))
        .where(committed_status_predicate(Purchase, subsidy_year_col=Subsidy.year))
        .where(Purchase.stopped_at.is_(None))
        .where(PurchaseItem.over_plan.is_(False))
        .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        .where(sqlor(Purchase.subsidy_id == FeoCategory.subsidy_id, Purchase.subsidy_id.is_(None)))
        .where(aggregate_scope_expr())
    )
    unlinked_rows = (await db.execute(_unlinked_stmt)).all()
    if unlinked_rows:
        fact_by_item = await fact_amounts_for_rows(db, unlinked_rows)
        bucket_by_cat: dict[int, dict] = {}
        for r2 in unlinked_rows:
            pi2 = r2.PurchaseItem
            fact_amount2 = fact_by_item.get(pi2.id)
            if fact_amount2 is None:
                amt2 = float(pi2.planned_total if pi2.planned_total is not None else (pi2.total_price or 0))
            else:
                amt2 = float(fact_amount2)
            kind2 = kind_of_by_category_id(pi2.item_type, r2.cat_id, _payroll_ids)
            bucket_by_cat.setdefault(r2.cat_id, _empty_kind_bucket())[kind2] += amt2
        for cat_id, bucket in bucket_by_cat.items():
            sid = sid_by_cat.get(cat_id)
            if sid not in result:
                continue
            for kind in ALL_KINDS:
                amt = bucket.get(kind, 0.0)
                if abs(amt) < _ZERO_EPS:
                    continue
                result[sid].append({
                    "planned_item_id": None,
                    "name": "Закупки без привязки к плановой позиции",
                    "feo_category_id": cat_id,
                    "category_path": _category_path(cat_id, cats),
                    "kind": kind,
                    "need_level": "likely",
                    "contribution": 0.0,
                    "committed": amt,
                    "raw": -amt,
                    "monthly_future_not_started": False,
                    "purchase_id": None,
                })
    return result


async def not_committed_raw_by_subsidy(
    db: AsyncSession, subsidy_ids: list[int], *, today=None,
) -> dict[int, dict]:
    """{subsidy_id: {"nice_raw": float, "likely_raw": float, "by_kind": {goods,
    services, unspecified}, "monthly_future_not_started_raw": float,
    "nice_payroll_raw", "likely_payroll_raw", "monthly_future_not_started_payroll_raw"}}
    — Σ not_committed_raw_rows по need_level/kind (ПРАВИЛО №6 — raw одной
    позиции считается ТОЛЬКО там, эта функция — чистая агрегация, не вторая
    формула).

    Строки с monthly_future_not_started=True исключены из nice_raw/likely_raw
    (их raw идёт в monthly_future_not_started_raw — строка 4 карточки «Можно
    перераспределить», держит инвариант redistributable == not_planned + nice
    + likely + monthly_future_not_started АЛГЕБРАИЧЕСКИ), НО остаются в
    `by_kind` (находка координатора 06.10.2026, не отменена: «Можно
    перераспределить по типам» — отдельная раскладка ВСЕЙ суммы redistributable
    по товар/услуга, она не делится на need_level/«ещё уйдёт» — иначе Σ
    by_kind разошлась бы с redistributable, см. test_redistributable_drill.py).

    *_payroll_raw (D7, живая приёмка 21.10.2026, ДНР id 61) — ТА ЖЕ Σ, но
    ТОЛЬКО по строкам kind=='payroll', параллельно nice_raw/likely_raw/
    monthly_future_not_started_raw (не вторая формула — тот же проход по
    строкам, что и выше, просто ещё один накопитель). Нужна
    payroll_visibility.scrub_payroll_from_dashboard_charts, чтобы вычесть
    payroll-долю подстрок карточки «Можно перераспределить» («не
    запланировано»/«хотелось бы»/«скорее всего»/«ещё уйдёт помесячно») у
    пользователя без subsidy.view_payroll — см. её докстринг."""
    result: dict[int, dict] = {
        sid: {
            "nice_raw": 0.0, "likely_raw": 0.0, "by_kind": _empty_kind_bucket(),
            "monthly_future_not_started_raw": 0.0,
            "nice_payroll_raw": 0.0, "likely_payroll_raw": 0.0,
            "monthly_future_not_started_payroll_raw": 0.0,
        }
        for sid in subsidy_ids
    }
    if not subsidy_ids:
        return result

    rows_by_sid = await not_committed_raw_rows(db, subsidy_ids, today=today)
    for sid, rows in rows_by_sid.items():
        d = result.get(sid)
        if d is None:
            continue
        for row in rows:
            d["by_kind"][row["kind"]] += row["raw"]
            is_payroll_row = row["kind"] == "payroll"
            if row["monthly_future_not_started"]:
                d["monthly_future_not_started_raw"] += row["raw"]
                if is_payroll_row:
                    d["monthly_future_not_started_payroll_raw"] += row["raw"]
                continue
            if is_reserve_need_level(row["need_level"]):  # 🟡 nice_to_have + unforeseen
                d["nice_raw"] += row["raw"]
                if is_payroll_row:
                    d["nice_payroll_raw"] += row["raw"]
            else:
                d["likely_raw"] += row["raw"]
                if is_payroll_row:
                    d["likely_payroll_raw"] += row["raw"]
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
